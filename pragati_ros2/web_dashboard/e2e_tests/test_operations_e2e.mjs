#!/usr/bin/env node
// Operations Page E2E Test Suite (Task 7.2)
// Validates the Operations page UI: navigation, target selector, operation
// grid, parameter inputs, and availability banner.
// Single browser, single page, sequential checks (WSL2-safe).
// Run: node web_dashboard/e2e_tests/test_operations_e2e.mjs
//
// Requires: npm install playwright (in this directory)
// Dashboard must be running on http://127.0.0.1:8090

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

// Helper: check element is visible (display != none)
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

// Helper: check which section is currently visible
async function getActiveSection(page) {
    return page.evaluate(() => {
        const sections = document.querySelectorAll(".content-section");
        for (const s of sections) {
            if (getComputedStyle(s).display !== "none") return s.id;
        }
        return null;
    });
}

// Helper: count child elements matching a selector
async function countElements(page, selector) {
    return page.evaluate(
        (sel) => document.querySelectorAll(sel).length,
        selector,
    );
}

// Helper: wait for Preact to render content into a section's -preact container
async function waitForPreactContent(page, sectionId, timeoutMs = 5000) {
    try {
        await page.waitForFunction(
            (id) => {
                const container = document.getElementById(
                    `${id}-section-preact`,
                );
                return container && container.children.length > 0;
            },
            sectionId,
            { timeout: timeoutMs },
        );
    } catch (_e) {
        // Fall back - content may already be visible
    }
}

// Helper: navigate to a section by clicking the sidebar nav-item
async function navigateToSection(page, sectionName) {
    await page.evaluate((name) => {
        const link = document.querySelector(
            `.nav-item[data-section="${name}"]`,
        );
        if (link) link.click();
    }, sectionName);
    await page.waitForTimeout(500);
}

(async () => {
    console.log("Operations Page E2E Test Suite (Task 7.2)");
    console.log(`Target: ${BASE}`);
    console.log("=============================================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage({
        viewport: { width: 1280, height: 800 },
    });

    // Collect JS errors
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));

    // Collect 404s
    const notFound = [];
    page.on("response", (resp) => {
        if (resp.status() === 404) notFound.push(resp.url());
    });

    // Global timeout
    const timeout = setTimeout(async () => {
        console.log("\n  CRASH  Global timeout (30s) exceeded");
        failed++;
        failures.push("CRASH: Global timeout (30s) exceeded");
        await browser.close();
        printSummary();
        process.exit(1);
    }, 30000);

    try {
        // Load dashboard
        console.log("[0] Loading dashboard...");
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 15000 });
        await page.waitForTimeout(1000);

        const title = await page.title();
        assert(title.length > 0, "Dashboard page loads with a title");

        // ================================================================
        // 1: Navigate to Operations page
        // ================================================================
        console.log("\n[1] Navigate to Operations page");

        // Verify Operations nav item exists in the sidebar
        // GroupedSidebar renders <a class="sidebar-nav-item" onClick=...>
        // without an href attribute, so match by class + text content.
        const opsNavExists = await page.evaluate(() => {
            const items = document.querySelectorAll(".sidebar-nav-item");
            return Array.from(items).some((el) =>
                el.textContent.includes("Operations"),
            );
        });
        assert(opsNavExists, "Operations nav item exists in sidebar");

        // Navigate via hash - reliable regardless of sidebar structure
        await page.goto(`${BASE}/#operations`, {
            waitUntil: "networkidle",
            timeout: 15000,
        });
        await waitForPreactContent(page, "operations");
        await page.waitForTimeout(500);

        // Verify operations-section is the active content section
        const activeSection = await getActiveSection(page);
        assert(
            activeSection === "operations-section",
            `Operations section is active (got "${activeSection}")`,
        );

        // Verify operations-section is visible
        assert(
            await isVisible(page, "#operations-section"),
            "Operations section is visible",
        );

        // Verify Preact content rendered into the mount point
        const preactRendered = await page.evaluate(() => {
            const container = document.getElementById(
                "operations-section-preact",
            );
            return container && container.children.length > 0;
        });
        assert(
            preactRendered,
            "OperationsTab Preact component rendered into mount point",
        );

        // The page should have section headings (h3 elements).
        // When sync.sh is unavailable, only the error banner renders.
        const sectionTitles = await page.evaluate(() => {
            const container = document.getElementById(
                "operations-section-preact",
            );
            if (!container) return [];
            const headings = container.querySelectorAll("h3");
            return Array.from(headings).map((h) => h.textContent.trim());
        });

        // Check sync.sh availability to decide test path
        const syncAvailable = await page.evaluate(async () => {
            try {
                const resp = await fetch("/api/operations/available");
                const data = await resp.json();
                return data.available === true;
            } catch (_e) {
                return false;
            }
        });

        if (!syncAvailable) {
            // ============================================================
            // 6: Availability banner - sync.sh not available
            // ============================================================
            console.log(
                "\n[6] Availability banner (sync.sh not available)",
            );

            const bannerText = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return null;
                return container.textContent.trim();
            });
            assert(
                bannerText && bannerText.includes("sync.sh"),
                'Unavailability banner mentions "sync.sh"',
            );
            assert(
                bannerText &&
                    (bannerText.includes("unavailable") ||
                        bannerText.includes("not found")),
                'Unavailability banner mentions "unavailable" or "not found"',
            );

            // The banner should have error styling (red background #dc3545)
            const bannerBg = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return null;
                // The banner is the first div > div with inline style
                const banner = container.querySelector("div > div");
                if (!banner) return null;
                return getComputedStyle(banner).backgroundColor;
            });
            // #dc3545 = rgb(220, 53, 69)
            assert(
                bannerBg &&
                    (bannerBg.includes("220") ||
                        bannerBg.includes("dc3545")),
                "Unavailability banner has red background styling",
            );

            skip(
                "Target selector renders entities",
                "sync.sh not available - UI shows error banner only",
            );
            skip(
                "Select a target",
                "sync.sh not available - UI shows error banner only",
            );
            skip(
                "Operation grid shows 12 buttons",
                "sync.sh not available - UI shows error banner only",
            );
            skip(
                "Select an operation (set-role params)",
                "sync.sh not available - UI shows error banner only",
            );
        } else {
            // sync.sh IS available - full UI tests

            assert(
                sectionTitles.some((t) => t.includes("Targets")),
                'Page has "Targets" section heading',
            );
            assert(
                sectionTitles.some((t) => t.includes("Operations")),
                'Page has "Operations" section heading',
            );
            assert(
                sectionTitles.some((t) => t.includes("Output")),
                'Page has "Output" section heading',
            );

            // ============================================================
            // 2: Target selector renders entities
            // ============================================================
            console.log("\n[2] Target selector renders entities");

            // "All" chip should always be present
            const allChipExists = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return false;
                const divs = container.querySelectorAll("div");
                for (const d of divs) {
                    if (
                        d.textContent.trim() === "All" &&
                        d.style.cursor === "pointer"
                    ) {
                        return true;
                    }
                }
                return false;
            });
            assert(allChipExists, '"All" target chip is present');

            // Entity chips should be clickable divs with cursor:pointer
            // The actual count depends on what the /api/entities/ endpoint
            // returns, so we just verify the structure exists
            const entityChipCount = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return 0;
                // Entity chips are styled divs with cursor:pointer and
                // borderRadius:16px (chip style)
                const divs = container.querySelectorAll("div");
                let count = 0;
                for (const d of divs) {
                    if (
                        d.style.cursor === "pointer" &&
                        d.style.borderRadius === "16px"
                    ) {
                        count++;
                    }
                }
                return count;
            });
            // At minimum, the "All" chip exists (count >= 1)
            assert(
                entityChipCount >= 1,
                `Target chips rendered (got ${entityChipCount}, at least "All")`,
            );

            // Manual IP input field exists
            const manualIpInput = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return false;
                const input = container.querySelector(
                    'input[placeholder*="Manual IP"]',
                );
                return !!input;
            });
            assert(
                manualIpInput,
                "Manual IP address input field exists",
            );

            // Add button for manual IP exists
            const addBtnExists = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return false;
                const buttons = container.querySelectorAll("button");
                for (const b of buttons) {
                    if (b.textContent.trim() === "Add") return true;
                }
                return false;
            });
            assert(addBtnExists, '"Add" button for manual IP exists');

            // ============================================================
            // 3: Select a target
            // ============================================================
            console.log("\n[3] Select a target");

            // Click the "All" chip
            await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return;
                const divs = container.querySelectorAll("div");
                for (const d of divs) {
                    if (
                        d.textContent.trim() === "All" &&
                        d.style.cursor === "pointer"
                    ) {
                        d.click();
                        return;
                    }
                }
            });
            await page.waitForTimeout(300);

            // Verify "All" chip gets selected styling (borderColor #0d6efd)
            const allChipSelected = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return false;
                const divs = container.querySelectorAll("div");
                for (const d of divs) {
                    if (
                        d.textContent.trim() === "All" &&
                        d.style.cursor === "pointer"
                    ) {
                        // Check for selected border color
                        return (
                            d.style.borderColor === "rgb(13, 110, 253)" ||
                            d.style.borderColor === "#0d6efd"
                        );
                    }
                }
                return false;
            });
            assert(
                allChipSelected,
                '"All" chip shows selected styling after click',
            );

            // Toggle "All" off by clicking again
            await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return;
                const divs = container.querySelectorAll("div");
                for (const d of divs) {
                    if (
                        d.textContent.trim() === "All" &&
                        d.style.cursor === "pointer"
                    ) {
                        d.click();
                        return;
                    }
                }
            });
            await page.waitForTimeout(300);

            const allChipDeselected = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return false;
                const divs = container.querySelectorAll("div");
                for (const d of divs) {
                    if (
                        d.textContent.trim() === "All" &&
                        d.style.cursor === "pointer"
                    ) {
                        // After toggle-off, border should NOT be #0d6efd
                        return (
                            d.style.borderColor !== "rgb(13, 110, 253)" &&
                            d.style.borderColor !== "#0d6efd"
                        );
                    }
                }
                return false;
            });
            assert(
                allChipDeselected,
                '"All" chip loses selected styling after second click',
            );

            // ============================================================
            // 4: Operation grid shows buttons
            // ============================================================
            console.log("\n[4] Operation grid shows operation buttons");

            // Count operation buttons (buttons inside the grid with op styling)
            const opButtons = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return [];
                // Operation buttons are <button> elements with minHeight:70px
                const btns = container.querySelectorAll("button");
                const ops = [];
                for (const b of btns) {
                    if (b.style.minHeight === "70px") {
                        ops.push(b.textContent.trim());
                    }
                }
                return ops;
            });

            // The grid renders buttons only for operations whose definitions
            // were returned by /api/operations/definitions. All 12 should be
            // present if the API is working correctly.
            assert(
                opButtons.length >= 12,
                `Operation grid has >= 12 buttons (got ${opButtons.length})`,
            );

            // Verify expected operation labels are present
            const expectedLabels = [
                "Deploy (cross-compiled)",
                "Deploy (local)",
                "Build on RPi",
                "Quick sync",
                "Provision",
                "Set role",
                "Set arm identity",
                "Set MQTT address",
                "Collect logs",
                "Verify",
                "Restart services",
                "Test MQTT",
            ];
            for (const label of expectedLabels) {
                const found = opButtons.some((text) => text.includes(label));
                assert(found, `Operation button "${label}" exists`);
            }

            // Verify group labels (Deployment, Configuration, Maintenance)
            const groupLabels = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return [];
                // Group labels have gridColumn "1 / -1" and text-transform
                // uppercase - they are divs inside the grid
                const divs = container.querySelectorAll("div");
                const labels = [];
                for (const d of divs) {
                    if (
                        d.style.gridColumn === "1 / -1" &&
                        d.style.textTransform === "uppercase"
                    ) {
                        labels.push(d.textContent.trim());
                    }
                }
                return labels;
            });
            assert(
                groupLabels.includes("Deployment"),
                'Operation group "Deployment" label exists',
            );
            assert(
                groupLabels.includes("Configuration"),
                'Operation group "Configuration" label exists',
            );
            assert(
                groupLabels.includes("Maintenance"),
                'Operation group "Maintenance" label exists',
            );

            // ============================================================
            // 5: Select an operation - parameter inputs
            // ============================================================
            console.log(
                "\n[5] Select an operation & parameter inputs",
            );

            // Click the "Set role" operation button
            await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return;
                const btns = container.querySelectorAll("button");
                for (const b of btns) {
                    if (
                        b.style.minHeight === "70px" &&
                        b.textContent.includes("Set role")
                    ) {
                        b.click();
                        return;
                    }
                }
            });
            await page.waitForTimeout(300);

            // Verify the button gets active/selected styling (borderColor #0d6efd)
            const setRoleBtnActive = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return false;
                const btns = container.querySelectorAll("button");
                for (const b of btns) {
                    if (
                        b.style.minHeight === "70px" &&
                        b.textContent.includes("Set role")
                    ) {
                        return b.style.borderColor === "rgb(13, 110, 253)" ||
                            b.style.borderColor === "#0d6efd";
                    }
                }
                return false;
            });
            assert(
                setRoleBtnActive,
                '"Set role" button shows active styling after click',
            );

            // Verify parameter inputs appear - "set-role" has a "role" param
            // which renders as a <select> dropdown with arm/vehicle options
            const roleSelectInfo = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return null;
                // Look for a <select> inside the parameter area
                const selects = container.querySelectorAll("select");
                for (const sel of selects) {
                    const options = Array.from(sel.options).map(
                        (o) => o.value,
                    );
                    if (
                        options.includes("arm") &&
                        options.includes("vehicle")
                    ) {
                        return {
                            exists: true,
                            options: options,
                            optionCount: options.length,
                        };
                    }
                }
                return null;
            });
            assert(
                roleSelectInfo && roleSelectInfo.exists,
                "Role dropdown appears for set-role operation",
            );
            assert(
                roleSelectInfo &&
                    roleSelectInfo.options.includes("arm") &&
                    roleSelectInfo.options.includes("vehicle"),
                'Role dropdown has "arm" and "vehicle" options',
            );

            // Verify a "Run" button appears when an operation is selected
            const runBtnExists = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return false;
                const btns = container.querySelectorAll("button");
                for (const b of btns) {
                    if (
                        b.textContent.trim().includes("Run") &&
                        b.style.minHeight !== "70px"
                    ) {
                        return true;
                    }
                }
                return false;
            });
            assert(
                runBtnExists,
                '"Run" button appears when operation is selected',
            );

            // Verify a parameter label "role" is shown
            const roleLabel = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return false;
                const labels = container.querySelectorAll("label");
                for (const l of labels) {
                    if (l.textContent.trim() === "role") return true;
                }
                return false;
            });
            assert(
                roleLabel,
                'Parameter label "role" is shown for set-role operation',
            );

            // Deselect by clicking the same operation button again
            await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return;
                const btns = container.querySelectorAll("button");
                for (const b of btns) {
                    if (
                        b.style.minHeight === "70px" &&
                        b.textContent.includes("Set role")
                    ) {
                        b.click();
                        return;
                    }
                }
            });
            await page.waitForTimeout(300);

            // After deselection, Run button should disappear
            const runBtnGone = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return true;
                const btns = container.querySelectorAll("button");
                for (const b of btns) {
                    if (
                        b.textContent.trim().includes("Run") &&
                        b.style.minHeight !== "70px"
                    ) {
                        return false;
                    }
                }
                return true;
            });
            assert(
                runBtnGone,
                '"Run" button disappears when operation is deselected',
            );

            // Now test a non-parameterized operation (e.g., "Verify")
            await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return;
                const btns = container.querySelectorAll("button");
                for (const b of btns) {
                    if (
                        b.style.minHeight === "70px" &&
                        b.textContent.includes("Verify")
                    ) {
                        b.click();
                        return;
                    }
                }
            });
            await page.waitForTimeout(300);

            // No parameter dropdown should appear (Verify has no params)
            const noParamSelect = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return true;
                // Check if a parameter box with select/input is visible
                // The paramBox has a specific flex layout
                const selects = container.querySelectorAll("select");
                for (const sel of selects) {
                    const options = Array.from(sel.options).map(
                        (o) => o.value,
                    );
                    if (
                        options.includes("arm") &&
                        options.includes("vehicle")
                    ) {
                        return false; // role dropdown still showing
                    }
                }
                return true;
            });
            assert(
                noParamSelect,
                "No role dropdown for non-parameterized Verify operation",
            );

            // Run button should exist for Verify too
            const runBtnForVerify = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return false;
                const btns = container.querySelectorAll("button");
                for (const b of btns) {
                    const text = b.textContent.trim();
                    if (
                        text.includes("Run") &&
                        text.includes("Verify") &&
                        b.style.minHeight !== "70px"
                    ) {
                        return true;
                    }
                }
                return false;
            });
            assert(
                runBtnForVerify,
                '"Run Verify" button shown for Verify operation',
            );

            // Deselect Verify
            await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return;
                const btns = container.querySelectorAll("button");
                for (const b of btns) {
                    if (
                        b.style.minHeight === "70px" &&
                        b.textContent.includes("Verify")
                    ) {
                        b.click();
                        return;
                    }
                }
            });
            await page.waitForTimeout(200);

            // ============================================================
            // 6: Availability banner (sync.sh IS available)
            // ============================================================
            console.log(
                "\n[6] Availability banner (sync.sh available)",
            );

            // When sync.sh is available, no error banner should be shown
            const errorBannerText = await page.evaluate(() => {
                const container = document.getElementById(
                    "operations-section-preact",
                );
                if (!container) return null;
                return container.textContent;
            });
            assert(
                !errorBannerText ||
                    !errorBannerText.includes("not found"),
                'No "not found" error banner when sync.sh is available',
            );
        }

        // ================================================================
        // 7: API endpoints respond
        // ================================================================
        console.log("\n[7] API endpoint checks");

        // /api/operations/available
        const availResp = await page.evaluate(async () => {
            const r = await fetch("/api/operations/available");
            return { status: r.status, body: await r.json() };
        });
        assert(
            availResp.status === 200 &&
                typeof availResp.body.available === "boolean",
            `GET /api/operations/available returns {available: bool} (HTTP ${availResp.status})`,
        );

        // /api/operations/definitions
        const defsResp = await page.evaluate(async () => {
            const r = await fetch("/api/operations/definitions");
            return { status: r.status, body: await r.json() };
        });
        assert(
            defsResp.status === 200,
            `GET /api/operations/definitions returns HTTP 200`,
        );
        const defKeys = Object.keys(defsResp.body);
        assert(
            defKeys.length === 12,
            `Definitions has 12 operations (got ${defKeys.length})`,
        );
        // Each definition should have label, description, params
        const firstDef = defsResp.body[defKeys[0]];
        assert(
            firstDef &&
                typeof firstDef.label === "string" &&
                typeof firstDef.description === "string" &&
                Array.isArray(firstDef.params),
            "Each definition has label, description, and params array",
        );

        // /api/operations/active
        const activeResp = await page.evaluate(async () => {
            const r = await fetch("/api/operations/active");
            return { status: r.status, body: await r.json() };
        });
        assert(
            activeResp.status === 200,
            `GET /api/operations/active returns HTTP 200`,
        );

        // ================================================================
        // 8: Section switching round-trip
        // ================================================================
        console.log("\n[8] Section navigation round-trip");

        // Navigate away to fleet-overview, then back to operations
        await page.goto(`${BASE}/#fleet-overview`, {
            waitUntil: "networkidle",
            timeout: 15000,
        });
        await page.waitForTimeout(500);

        const overviewActive = await getActiveSection(page);
        assert(
            overviewActive === "fleet-overview-section",
            "Fleet overview section is active after navigating away",
        );

        // Navigate back to operations
        await page.goto(`${BASE}/#operations`, {
            waitUntil: "networkidle",
            timeout: 15000,
        });
        await waitForPreactContent(page, "operations");
        await page.waitForTimeout(500);

        const opsActiveAgain = await getActiveSection(page);
        assert(
            opsActiveAgain === "operations-section",
            "Operations section is active after returning",
        );

        // Verify Preact content still renders after round-trip
        const preactStillRendered = await page.evaluate(() => {
            const container = document.getElementById(
                "operations-section-preact",
            );
            return container && container.children.length > 0;
        });
        assert(
            preactStillRendered,
            "OperationsTab still rendered after round-trip navigation",
        );

        // ================================================================
        // 9: Error checks
        // ================================================================
        console.log("\n[9] Error checks");

        assert(
            jsErrors.length === 0,
            `No JS errors on page (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join("; ")})`,
        );

        // Filter out expected API 404s vs file 404s
        const file404s = notFound.filter(
            (url) =>
                url.endsWith(".js") ||
                url.endsWith(".mjs") ||
                url.endsWith(".css") ||
                url.endsWith(".html"),
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
        clearTimeout(timeout);
        await browser.close();
    }

    printSummary();
    process.exit(failed > 0 ? 1 : 0);
})();

function printSummary() {
    const total = passed + failed + skipped;
    console.log("\n=============================================");
    console.log(
        `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`,
    );
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    console.log();
}
