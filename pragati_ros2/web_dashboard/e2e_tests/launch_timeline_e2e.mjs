#!/usr/bin/env node
// Launch Progress Timeline E2E Test Suite
// Validates the progress timeline renders, phase transitions work, adaptive
// polling toggles, confirmation dialog appears, and error/success states
// display correctly — all via mocked backend API + UI-driven interactions.
//
// Run: node web_dashboard/e2e_tests/launch_timeline_e2e.mjs
//
// Requires: npm install playwright (in this directory)
// Dashboard must be running on http://127.0.0.1:8090
//
// Updated for Preact + HTM ES-module frontend. All window.launchControl
// globals are gone — state is managed by Preact hooks internally. Tests
// now drive state changes via mocked API responses, UI clicks, and
// simulated WebSocket messages.

import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8090";
let passed = 0;
let failed = 0;
let skipped = 0;
const failures = [];

function assert(condition, name) {
    if (condition) {
        passed++;
        console.log(`  PASS  ${name}`);
    } else {
        failed++;
        failures.push(name);
        console.log(`  FAIL  ${name}`);
    }
}

function skip(name, reason) {
    skipped++;
    console.log(`  SKIP  ${name} (${reason})`);
}

// Helper: check element exists
async function exists(page, selector) {
    return page.evaluate((sel) => !!document.querySelector(sel), selector);
}

// Helper: check element is visible (display != none and element exists)
async function isVisible(page, selector) {
    return page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        return getComputedStyle(el).display !== "none";
    }, selector);
}

// Helper: get trimmed text content
async function getText(page, selector) {
    return page.evaluate((sel) => {
        const el = document.querySelector(sel);
        return el ? el.textContent.trim() : null;
    }, selector);
}

// Helper: navigate to section by hash (with .nav-item fallback)
async function navigateToSection(page, sectionName) {
    await page.evaluate((name) => {
        const link = document.querySelector(`.nav-item[data-section="${name}"]`);
        if (link) {
            link.click();
        } else {
            window.location.hash = '#' + name;
        }
    }, sectionName);
    await page.waitForTimeout(500);
}

// Helper: wait for Preact to render content into a section's -preact container
async function waitForPreactContent(page, sectionId, timeoutMs = 5000) {
    try {
        await page.waitForFunction(
            (id) => {
                const container = document.getElementById(`${id}-section-preact`);
                return container && container.children.length > 0;
            },
            sectionId,
            { timeout: timeoutMs },
        );
    } catch (_e) {
        // Fall back — content may already be visible
    }
}

// Helper: get CSS class list for a phase element by its label text
// Preact renders: <div class="launch-phase pending"><div class="phase-bar"/><div class="phase-label">Cleanup</div></div>
// No data-phase attribute — find by label text.
async function getPhaseClass(page, phaseLabel) {
    return page.evaluate((label) => {
        const labels = document.querySelectorAll(".launch-phase .phase-label");
        for (const el of labels) {
            if (el.textContent.trim() === label) {
                return el.parentElement ? el.parentElement.className : null;
            }
        }
        return null;
    }, phaseLabel);
}

// Helper: get computed background color of a phase bar by label text
async function getPhaseBarColor(page, phaseLabel) {
    return page.evaluate((label) => {
        const labels = document.querySelectorAll(".launch-phase .phase-label");
        for (const el of labels) {
            if (el.textContent.trim() === label) {
                const phaseEl = el.parentElement;
                if (!phaseEl) return null;
                const bar = phaseEl.querySelector(".phase-bar");
                return bar ? getComputedStyle(bar).backgroundColor : null;
            }
        }
        return null;
    }, phaseLabel);
}

// Helper: get computed opacity of a phase element by label text
async function getPhaseOpacity(page, phaseLabel) {
    return page.evaluate((label) => {
        const labels = document.querySelectorAll(".launch-phase .phase-label");
        for (const el of labels) {
            if (el.textContent.trim() === label) {
                return el.parentElement
                    ? getComputedStyle(el.parentElement).opacity
                    : null;
            }
        }
        return null;
    }, phaseLabel);
}

// Phase name → display label mapping
const PHASE_LABELS = {
    cleanup: "Cleanup",
    daemon_restart: "Daemon Restart",
    node_startup: "Node Startup",
    motor_homing: "Motor Homing",
    system_ready: "System Ready",
};

const PHASES = ["cleanup", "daemon_restart", "node_startup", "motor_homing", "system_ready"];

(async () => {
    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();

    // Collect JS errors
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));

    // Collect file 404s
    const notFound = [];
    page.on("response", (resp) => {
        if (resp.status() === 404) notFound.push(resp.url());
    });

    try {
        // ================================================================
        // Setup: Mock API routes before loading the page
        // ================================================================

        // Mock arm status — returns whatever mockArmStatus is set to
        // NOTE: component reads `status.status`, NOT `status.state`
        const mockArmStatus = { status: "stopped" };
        await page.route("**/api/launch/arm/status", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(mockArmStatus),
            });
        });

        // Mock vehicle status
        // NOTE: component reads `status.status`, NOT `status.state`
        await page.route("**/api/launch/vehicle/status", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ status: "stopped" }),
            });
        });

        // Mock vehicle subsystems
        await page.route("**/api/launch/vehicle/subsystems", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify([]),
            });
        });

        // Mock arm launch — returns success so the component triggers timeline
        await page.route("**/api/launch/arm", (route) => {
            if (route.request().method() === "POST") {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify({ status: "ok" }),
                });
            } else {
                route.continue();
            }
        });

        // Mock arm stop
        await page.route("**/api/launch/arm/stop", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ status: "ok" }),
            });
        });

        // Mock vehicle launch
        await page.route("**/api/launch/vehicle", (route) => {
            if (route.request().method() === "POST") {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify({ status: "ok" }),
                });
            } else {
                route.continue();
            }
        });

        // ================================================================
        // SECTION 0: Load dashboard and navigate to Launch Control
        // ================================================================
        console.log("[0] Loading dashboard");

        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });

        // Wait for Preact module to load
        await page.waitForTimeout(1000);

        assert(
            await exists(page, "#launch-control-section"),
            "Launch Control section exists in DOM",
        );

        await navigateToSection(page, "launch-control");
        await waitForPreactContent(page, "launch-control");

        assert(
            await isVisible(page, "#launch-control-section"),
            "Launch Control section is visible after navigation",
        );

        // Verify Preact rendered content
        const hasPreactContent = await page.evaluate(() => {
            const container = document.getElementById("launch-control-section-preact");
            return container && container.children.length > 0;
        });
        assert(hasPreactContent, "Launch Control Preact content is rendered");

        // ================================================================
        // SECTION 1: Initial state — timeline not visible (Scenario 10)
        // ================================================================
        console.log("\n[1] Timeline Initial State");

        // In Preact, the ProgressTimeline returns null when not visible,
        // so .launch-progress-timeline should NOT exist in the DOM
        assert(
            !(await exists(page, ".launch-progress-timeline")),
            "Arm progress timeline not in DOM by default (Scenario 10)",
        );

        // Launch panel structure should exist
        assert(
            await exists(page, ".launch-panel-header"),
            "Launch panel header exists",
        );

        assert(
            await exists(page, ".launch-status-indicator"),
            "Launch status indicator exists",
        );

        assert(
            await exists(page, ".launch-panel-buttons .btn.btn-primary"),
            "Launch button exists",
        );

        assert(
            await exists(page, ".launch-panel-buttons .btn.btn-danger"),
            "Stop button exists",
        );

        // Status should show "Stopped" initially (from mocked API)
        const initialStatusText = await page.evaluate(() => {
            const indicators = document.querySelectorAll(".launch-status-indicator");
            // First indicator is the arm panel
            return indicators.length > 0 ? indicators[0].textContent.trim() : null;
        });
        assert(
            initialStatusText === "Stopped",
            `Initial arm status shows "Stopped" (got "${initialStatusText}")`,
        );

        // ================================================================
        // SECTION 2: Confirmation dialog (Scenario 3)
        // ================================================================
        console.log("\n[2] Confirmation Dialog");

        // Click the Launch button on the arm panel (first .btn.btn-primary in panel-buttons)
        const armLaunchBtn = await page.$(".launch-panel-buttons .btn.btn-primary");
        if (armLaunchBtn) {
            await armLaunchBtn.click();
            await page.waitForTimeout(300);

            // Check confirmation dialog is visible
            const dialogVisible = await page.evaluate(() => {
                const overlay = document.querySelector(
                    ".modal-overlay[data-confirm-dialog]",
                );
                if (!overlay) return false;
                return getComputedStyle(overlay).display !== "none";
            });
            assert(dialogVisible, "Confirmation dialog appears on Launch click (Scenario 3)");

            // Check dialog has confirm and cancel buttons
            assert(
                await exists(page, ".confirm-dialog-confirm"),
                "Confirmation dialog has a confirm button",
            );
            assert(
                await exists(page, ".confirm-dialog-cancel"),
                "Confirmation dialog has a cancel button",
            );

            // Cancel the dialog to clean up (don't launch yet)
            const cancelBtn = await page.$(".confirm-dialog-cancel");
            if (cancelBtn) {
                await cancelBtn.click();
                await page.waitForTimeout(200);
            }

            // Verify dialog is dismissed
            const dialogGone = await page.evaluate(() => {
                const overlay = document.querySelector(
                    ".modal-overlay[data-confirm-dialog]",
                );
                return !overlay || getComputedStyle(overlay).display === "none";
            });
            assert(dialogGone, "Confirmation dialog dismissed after cancel");
        } else {
            skip("Confirmation dialog", "Launch button not found");
        }

        // ================================================================
        // SECTION 3: Launch triggers timeline (Scenario 5)
        // ================================================================
        console.log("\n[3] Launch Triggers Timeline");

        // Click Launch and confirm to trigger timeline
        const armLaunchBtn2 = await page.$(".launch-panel-buttons .btn.btn-primary");
        if (armLaunchBtn2) {
            await armLaunchBtn2.click();
            await page.waitForTimeout(300);

            // Confirm the dialog
            const confirmBtn = await page.$(".confirm-dialog-confirm");
            if (confirmBtn) {
                await confirmBtn.click();
                await page.waitForTimeout(500);

                // After successful launch, timeline should be visible
                assert(
                    await exists(page, ".launch-progress-timeline"),
                    "Timeline appears after launch confirm (Scenario 5)",
                );

                // Check all 5 phase elements exist
                const phaseCount = await page.evaluate(() => {
                    return document.querySelectorAll(".launch-phase").length;
                });
                // There may be 2 launch panels, so just check >= 5
                assert(phaseCount >= 5, `Timeline has at least 5 phase elements (got ${phaseCount})`);

                // Check phase labels
                const phaseLabels = await page.evaluate(() => {
                    // Get labels from the first timeline only
                    const timeline = document.querySelector(".launch-progress-timeline");
                    if (!timeline) return [];
                    return Array.from(timeline.querySelectorAll(".phase-label")).map((el) =>
                        el.textContent.trim(),
                    );
                });
                assert(phaseLabels.length === 5, `Timeline has 5 phase labels (got ${phaseLabels.length})`);
                assert(
                    phaseLabels[0] === "Cleanup",
                    `First phase label is "Cleanup" (got "${phaseLabels[0]}")`,
                );
                assert(
                    phaseLabels[4] === "System Ready",
                    `Last phase label is "System Ready" (got "${phaseLabels[4]}")`,
                );

                // All phases start as pending after launch (fresh state)
                for (const phase of PHASES) {
                    const cls = await getPhaseClass(page, PHASE_LABELS[phase]);
                    assert(
                        cls && cls.includes("pending"),
                        `Phase "${phase}" starts as pending after launch`,
                    );
                }

                // Elapsed timer starts near 0
                const elapsedText = await getText(page, ".launch-progress-elapsed");
                assert(
                    elapsedText && elapsedText.includes("0"),
                    `Elapsed timer starts near 0 (got "${elapsedText}")`,
                );

                // Estimated remaining shows total (15s = 5+2+1+7+0)
                const estText = await getText(page, ".launch-progress-estimated");
                assert(
                    estText && estText.includes("15"),
                    `Estimated remaining shows 15s (got "${estText}")`,
                );
            } else {
                skip("Launch triggers timeline", "Confirm button not found");
            }
        } else {
            skip("Launch triggers timeline", "Launch button not found");
        }

        // ================================================================
        // SECTION 4: Phase completion via status API (Scenario 6, 7, 8)
        // ================================================================
        console.log("\n[4] Phase Completion via Status API");

        // In the Preact component, phase transitions are driven by:
        // 1. WebSocket phase events → setArmPhases (individual phase updates)
        // 2. Status API polling → useEffect that auto-completes all phases
        //    when armStatus.state becomes "running"/"active"
        //
        // Since there's no real backend/WebSocket in E2E, we test the
        // completion flow by changing the mocked status API return value.
        // The component's useEffect detects "running" state and marks all
        // phases complete with finalLabel = "Complete".
        //
        // Individual phase-by-phase transitions would require injecting
        // WebSocket messages, which needs a real WS server or WS
        // interception — better tested in unit/integration tests.

        const timelineExists = await exists(page, ".launch-progress-timeline");
        if (timelineExists) {
            // Test: changing mock status to running triggers "Complete" flow
            // The component's useEffect watches armStatus — when it becomes
            // "running", it sets all phases to complete and finalLabel to "Complete"

            // Update the mock to return "running" status
            // NOTE: component reads `status.status`, NOT `status.state`
            await page.unroute("**/api/launch/arm/status");
            await page.route("**/api/launch/arm/status", (route) => {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify({ status: "running", pid: 12345 }),
                });
            });

            // Wait for the next poll cycle to pick up the new status
            // Poll is at POLL_FAST_MS (1000ms) after launch — wait up to 5s
            try {
                await page.waitForFunction(
                    () => {
                        const ind = document.querySelector(".launch-status-indicator");
                        return ind && ind.textContent.trim() === "Running";
                    },
                    { polling: 300, timeout: 5000 },
                );
            } catch (_) {
                // Status didn't change — assertions below will catch it
            }

            // After status becomes "running", useEffect marks all phases complete
            for (const phase of PHASES) {
                const cls = await getPhaseClass(page, PHASE_LABELS[phase]);
                assert(
                    cls && cls.includes("complete"),
                    `Phase "${phase}" marked complete when status is running (Scenario 8)`,
                );
            }

            // Estimated text should show "Complete"
            const estComplete = await getText(page, ".launch-progress-estimated");
            assert(
                estComplete === "Complete",
                `Estimated text shows "Complete" (got "${estComplete}") (Scenario 8)`,
            );

            // Status indicator should show "Running"
            const statusText = await page.evaluate(() => {
                const indicators = document.querySelectorAll(".launch-status-indicator");
                return indicators.length > 0 ? indicators[0].textContent.trim() : null;
            });
            assert(
                statusText === "Running",
                `Status indicator shows "Running" (got "${statusText}") (Scenario 4)`,
            );

            // Status indicator should have status-running class
            const statusCls = await page.evaluate(() => {
                const indicators = document.querySelectorAll(".launch-status-indicator");
                return indicators.length > 0 ? indicators[0].className : "";
            });
            assert(
                statusCls.includes("status-running"),
                `Status indicator has status-running class (got "${statusCls}") (Scenario 4)`,
            );
        } else {
            skip("Phase transitions (complete flow)", "Timeline not visible");
        }

        // ================================================================
        // SECTION 5: Error state via status API (Scenario 9)
        // ================================================================
        console.log("\n[5] Launch Error State");

        // To test error state, we need a fresh launch so the useEffect
        // can detect the transition. First, reset to stopped state.
        await page.unroute("**/api/launch/arm/status");
        await page.route("**/api/launch/arm/status", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ status: "stopped" }),
            });
        });
        await page.waitForTimeout(1500);

        // Launch again to get a fresh timeline
        const armLaunchBtn3 = await page.$(".launch-panel-buttons .btn.btn-primary");
        let launchedForError = false;
        if (armLaunchBtn3) {
            await armLaunchBtn3.click();
            await page.waitForTimeout(300);
            const confirmBtn = await page.$(".confirm-dialog-confirm");
            if (confirmBtn) {
                await confirmBtn.click();
                await page.waitForTimeout(500);
                launchedForError = true;
            }
        }

        if (launchedForError) {
            // Now simulate error status
            await page.unroute("**/api/launch/arm/status");
            await page.route("**/api/launch/arm/status", (route) => {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify({ status: "error" }),
                });
            });
            // Wait for error status to be picked up by polling
            try {
                await page.waitForFunction(
                    () => {
                        const el = document.querySelector(".launch-progress-estimated");
                        return el && el.textContent.trim() === "Failed";
                    },
                    { polling: 300, timeout: 5000 },
                );
            } catch (_) {
                // Status didn't change — assertions below will catch it
            }

            // After status becomes "error", useEffect sets finalLabel to "Failed"
            const estFailed = await getText(page, ".launch-progress-estimated");
            assert(
                estFailed === "Failed",
                `Estimated text shows "Failed" on error status (got "${estFailed}") (Scenario 9)`,
            );

            // Timeline should persist (still visible) after error
            assert(
                await exists(page, ".launch-progress-timeline"),
                "Timeline persists after error (Scenario 9)",
            );
        } else {
            skip("Error state", "Could not launch for error test");
        }

        // ================================================================
        // SECTION 6: Output terminal (Scenario 6 — output rendering)
        // ================================================================
        console.log("\n[6] Output Terminal");

        // The output terminal should exist in both launch panels
        assert(
            await exists(page, ".launch-output-terminal"),
            "Output terminal element exists",
        );

        assert(
            await exists(page, ".launch-output-panel"),
            "Output panel exists",
        );

        // Clear button should exist in output header
        const clearBtnText = await page.evaluate(() => {
            const header = document.querySelector(".launch-output-header");
            if (!header) return null;
            const btn = header.querySelector(".btn");
            return btn ? btn.textContent.trim() : null;
        });
        assert(
            clearBtnText === "Clear",
            `Output terminal has Clear button (got "${clearBtnText}")`,
        );

        // ================================================================
        // SECTION 7: Launch panel controls structure
        // ================================================================
        console.log("\n[7] Launch Panel Controls");

        // Debug mode checkbox exists
        const hasDebugCheckbox = await page.evaluate(() => {
            const labels = document.querySelectorAll(
                ".launch-param-toggles label",
            );
            for (const label of labels) {
                if (label.textContent.includes("Debug mode")) return true;
            }
            return false;
        });
        assert(hasDebugCheckbox, "Debug mode checkbox exists in arm panel");

        // Arm ID input exists
        const hasArmIdInput = await page.evaluate(() => {
            const labels = document.querySelectorAll(
                ".launch-param-toggles label",
            );
            for (const label of labels) {
                if (label.textContent.includes("Arm ID")) return true;
            }
            return false;
        });
        assert(hasArmIdInput, "Arm ID input exists in arm panel");

        // Both panels have launch and stop buttons
        const launchBtnCount = await page.evaluate(() => {
            return document.querySelectorAll(".launch-panel-buttons .btn.btn-primary").length;
        });
        assert(
            launchBtnCount >= 2,
            `Both panels have Launch buttons (got ${launchBtnCount})`,
        );

        const stopBtnCount = await page.evaluate(() => {
            return document.querySelectorAll(".launch-panel-buttons .btn.btn-danger").length;
        });
        assert(
            stopBtnCount >= 2,
            `Both panels have Stop buttons (got ${stopBtnCount})`,
        );

        // ================================================================
        // SECTION 8: Vehicle panel structure
        // ================================================================
        console.log("\n[8] Vehicle Panel Structure");

        // Vehicle panel should exist with its own header
        const panelTitles = await page.evaluate(() => {
            return Array.from(document.querySelectorAll(".launch-panel-header h3")).map(
                (el) => el.textContent.trim(),
            );
        });
        assert(
            panelTitles.includes("Arm Launch"),
            `Arm Launch panel title exists (got ${JSON.stringify(panelTitles)})`,
        );
        assert(
            panelTitles.includes("Vehicle Launch"),
            `Vehicle Launch panel title exists (got ${JSON.stringify(panelTitles)})`,
        );

        // Vehicle debug checkbox
        const vehicleDebugExists = await page.evaluate(() => {
            const panels = document.querySelectorAll(".card");
            for (const panel of panels) {
                const h3 = panel.querySelector("h3");
                if (h3 && h3.textContent.includes("Vehicle")) {
                    const labels = panel.querySelectorAll(
                        ".launch-param-toggles label",
                    );
                    for (const label of labels) {
                        if (label.textContent.includes("Debug mode")) return true;
                    }
                }
            }
            return false;
        });
        assert(vehicleDebugExists, "Vehicle panel has Debug mode checkbox");

        // Subsystem panel exists (may show empty state)
        assert(
            await exists(page, ".launch-subsystems-panel"),
            "Vehicle subsystem panel exists",
        );

        // ================================================================
        // SECTION 9: Phase bar CSS structure
        // ================================================================
        console.log("\n[9] Phase Bar CSS Structure");

        // Verify phase bars have the .phase-bar child element
        const phaseBarCount = await page.evaluate(() => {
            return document.querySelectorAll(".launch-phase .phase-bar").length;
        });
        assert(
            phaseBarCount >= 5,
            `Phase bars exist in timeline (got ${phaseBarCount})`,
        );

        // Verify phase labels have .phase-label class
        const phaseLabelCount = await page.evaluate(() => {
            return document.querySelectorAll(".launch-phase .phase-label").length;
        });
        assert(
            phaseLabelCount >= 5,
            `Phase labels exist in timeline (got ${phaseLabelCount})`,
        );

        // Verify timing section exists
        assert(
            await exists(page, ".launch-progress-timing"),
            "Timeline timing section exists",
        );
        assert(
            await exists(page, ".launch-progress-elapsed"),
            "Elapsed timer element exists",
        );
        assert(
            await exists(page, ".launch-progress-estimated"),
            "Estimated remaining element exists",
        );

        // ================================================================
        // SECTION 10: Adaptive polling behavior (Scenario 16, 17)
        // ================================================================
        console.log("\n[10] Adaptive Polling");

        // We can't directly read the pollMs state, but we can verify
        // the component polls at all by observing status API requests.
        // Verifying the exact fast/normal rate difference is fragile
        // in E2E due to timing of unroute/route cycles and Preact
        // state batching, so we assert only that polling IS active.

        // Ensure a working status route exists
        await page.unroute("**/api/launch/arm/status");
        await page.route("**/api/launch/arm/status", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ status: "stopped" }),
            });
        });

        // Observe that at least one status poll fires over 6 seconds
        // (proves the component's setInterval is alive)
        let pollCount = 0;
        const pollCounter = (req) => {
            if (req.url().includes("/api/launch/arm/status")) pollCount++;
        };
        page.on("request", pollCounter);
        await page.waitForTimeout(6000);
        page.removeListener("request", pollCounter);

        assert(
            pollCount >= 1,
            `Status polling is active (${pollCount} requests in 6s) (Scenario 16)`,
        );

        // ================================================================
        // SECTION 11: Stop button and dialog (Scenario 3)
        // ================================================================
        console.log("\n[11] Stop Button and Confirmation");

        // Click the Stop button (btn-danger) on the arm panel
        const armStopBtn = await page.$(".launch-panel-buttons .btn.btn-danger");
        if (armStopBtn) {
            await armStopBtn.click();
            await page.waitForTimeout(300);

            // Stop also shows a confirmation dialog
            const stopDialogVisible = await exists(
                page,
                ".modal-overlay[data-confirm-dialog]",
            );
            assert(
                stopDialogVisible,
                "Stop button shows confirmation dialog (Scenario 3)",
            );

            // Cancel to clean up
            const cancelBtn = await page.$(".confirm-dialog-cancel");
            if (cancelBtn) {
                await cancelBtn.click();
                await page.waitForTimeout(200);
            }
        } else {
            skip("Stop confirmation", "Stop button not found");
        }

        // ================================================================
        // SECTION 12: No JS errors or file 404s
        // ================================================================
        console.log("\n[12] Error Checks");

        assert(
            jsErrors.length === 0,
            `No JS errors on page (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join("; ")})`,
        );

        const file404s = notFound.filter(
            (url) => url.endsWith(".js") || url.endsWith(".css") || url.endsWith(".html"),
        );
        assert(
            file404s.length === 0,
            `No 404s for JS/CSS/HTML files (got ${file404s.length}: ${file404s.slice(0, 3).join("; ")})`,
        );
    } catch (err) {
        console.log(`\n  CRASH  ${err.message}`);
        failed++;
        failures.push(`CRASH: ${err.message}`);
    } finally {
        await browser.close();
    }

    // Summary
    const total = passed + failed + skipped;
    console.log("\n==========================");
    console.log(
        `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`,
    );
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    console.log();
    process.exit(failed > 0 ? 1 : 0);
})();
