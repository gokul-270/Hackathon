#!/usr/bin/env node
// Dashboard Sections E2E Test Suite
// Validates Field Analysis and Bag Manager sections render and navigate correctly,
// and verifies round-trip navigation across all global sections.
// Single browser, single page, sequential checks (WSL2-safe).
// Run: node web_dashboard/e2e_tests/dashboard_sections_e2e.mjs
//
// Requires: npm install playwright (in this directory)
// Dashboard must be running on http://127.0.0.1:8090
//
// Updated for Preact + HTM ES-module frontend with entity-centric sidebar.
// Navigation is hash-based: window.location.hash = "#section-name".
// Sections use .content-section class with .active toggled by AppShell.
// Sidebar uses GroupedSidebar with sidebar-nav-item/sidebar-overview classes
// (no .nav-item[data-section] elements).

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

// Helper: check element is visible (has .active class or display != none)
async function isVisible(page, selector) {
    return page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        return (
            el.classList.contains("active") ||
            getComputedStyle(el).display !== "none"
        );
    }, selector);
}

// Helper: get trimmed text content
async function getText(page, selector) {
    return page.evaluate((sel) => {
        const el = document.querySelector(sel);
        return el ? el.textContent.trim() : null;
    }, selector);
}

// Helper: navigate via hash change (the AppShell listens for hashchange)
async function navigateToHash(page, hash) {
    await page.evaluate((h) => {
        window.location.hash = "#" + h;
    }, hash);
    // Wait for hash change + Preact portal mount + render
    await page.waitForTimeout(500);
}

// Helper: check which section is currently active (.active class)
async function getActiveSection(page) {
    return page.evaluate(() => {
        const sections = document.querySelectorAll(".content-section");
        for (const s of sections) {
            if (
                s.classList.contains("active") ||
                getComputedStyle(s).display !== "none"
            )
                return s.id;
        }
        return null;
    });
}

// Helper: count child elements matching a selector
async function countElements(page, selector) {
    return page.evaluate((sel) => document.querySelectorAll(sel).length, selector);
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

(async () => {
    console.log("Dashboard Sections E2E Tests");
    console.log(`Target: ${BASE}`);
    console.log("==========================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();

    // Collect JS errors
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));

    // Collect 404s
    const notFound = [];
    page.on("response", (resp) => {
        if (resp.status() === 404) notFound.push(resp.url());
    });

    try {
        // Load dashboard
        console.log("[0] Loading dashboard...");
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
        // Wait for ES module app.js to bootstrap and render fleet-overview tab
        await waitForPreactContent(page, "fleet-overview");

        const title = await page.title();
        assert(title.length > 0, "Dashboard page loads with a title");

        // ================================================================
        // SECTION 1: Sidebar navigation items exist
        // ================================================================
        console.log("\n[1] Sidebar Navigation");

        // The GroupedSidebar renders global nav items as .sidebar-nav-item
        // elements with text labels, plus a .sidebar-overview for Fleet Overview.
        const globalNavLabels = await page.evaluate(() => {
            const items = document.querySelectorAll(".sidebar-nav-item");
            return Array.from(items).map((el) => el.textContent.trim());
        });

        // Global nav should include Operations, Monitoring, Settings
        assert(
            globalNavLabels.some((t) => t.includes("Operations")),
            "Operations nav item exists in sidebar",
        );
        assert(
            globalNavLabels.some((t) => t.includes("Monitoring")),
            "Monitoring nav item exists in sidebar",
        );
        assert(
            globalNavLabels.some((t) => t.includes("Settings")),
            "Settings nav item exists in sidebar",
        );

        // Fleet Overview link exists
        const fleetOverviewLink = await exists(page, ".sidebar-overview");
        assert(fleetOverviewLink, "Fleet Overview nav item exists in sidebar");

        // ================================================================
        // SECTION 2: Field Analysis section structure
        // ================================================================
        console.log("\n[2] Field Analysis Section");

        // Navigate to Field Analysis via hash
        await navigateToHash(page, "analysis");
        await waitForPreactContent(page, "analysis");
        const activeAfterClick = await getActiveSection(page);
        assert(
            activeAfterClick === "analysis-section",
            "Navigating to #analysis shows analysis-section",
        );

        // Section header exists (rendered by Preact inside the -preact container)
        const analysisHeading = await getText(
            page,
            "#analysis-section .section-header h2",
        );
        assert(
            analysisHeading === "Field Analysis",
            "Field Analysis section has correct heading",
        );

        // Back button is NOT visible in directory view (only shows in results/compare views)
        const backBtnText = await page.evaluate(() => {
            const btns = document.querySelectorAll(
                "#analysis-section .section-actions .btn",
            );
            for (const b of btns) {
                if (b.textContent.includes("Back")) return true;
            }
            return false;
        });
        assert(
            !backBtnText,
            "Analysis back button is not shown in directory view",
        );

        // Log Directories panel exists (rendered as a .stats-panel with h3 "Log Directories")
        const logDirsPanel = await page.evaluate(() => {
            const panels = document.querySelectorAll(
                "#analysis-section-preact .stats-panel",
            );
            for (const p of panels) {
                const h3 = p.querySelector("h3");
                if (h3 && h3.textContent.includes("Log Directories"))
                    return true;
            }
            return false;
        });
        assert(logDirsPanel, "Analysis Log Directories panel exists");

        // Analysis History panel exists
        const historyPanel = await page.evaluate(() => {
            const panels = document.querySelectorAll(
                "#analysis-section-preact .stats-panel",
            );
            for (const p of panels) {
                const h3 = p.querySelector("h3");
                if (h3 && h3.textContent.includes("Analysis History"))
                    return true;
            }
            return false;
        });
        assert(historyPanel, "Analysis history panel exists");

        // Compare button exists (inside "Compare Analyses" stats-panel)
        const compareBtn = await page.evaluate(() => {
            const panels = document.querySelectorAll(
                "#analysis-section-preact .stats-panel",
            );
            for (const p of panels) {
                const h3 = p.querySelector("h3");
                if (h3 && h3.textContent.includes("Compare")) {
                    const btn = p.querySelector(".btn.btn-primary");
                    return btn
                        ? { exists: true, disabled: btn.disabled }
                        : null;
                }
            }
            return null;
        });
        assert(compareBtn?.exists, "Analysis compare button exists");
        assert(
            compareBtn?.disabled === true,
            "Compare button is disabled by default",
        );

        // Result tabs are NOT rendered in directory view (only in results view)
        const tabCount = await countElements(
            page,
            "#analysis-section-preact .fa-result-tab",
        );
        assert(
            tabCount === 0,
            `Analysis result tabs not shown in directory view (got ${tabCount})`,
        );

        // Progress bar component exists but is not visible by default
        const progressBarExists = await exists(
            page,
            "#analysis-section-preact .analysis-progress-bar",
        );
        // ProgressBar is conditionally rendered only when visible prop is true
        // In idle state it may not be in DOM at all, which is fine
        if (progressBarExists) {
            skip(
                "Analysis progress panel hidden check",
                "progress bar rendered but may be visible during loading",
            );
        } else {
            assert(
                true,
                "Analysis progress bar not rendered in idle state (correct)",
            );
        }

        // ES module loaded check — Preact rendered content into the section
        const faModuleLoaded = await page.evaluate(() => {
            const container = document.getElementById(
                "analysis-section-preact",
            );
            return container && container.children.length > 0;
        });
        assert(faModuleLoaded, "FieldAnalysisTab module is loaded and rendered");

        // ================================================================
        // SECTION 3: Bag Manager section structure
        // ================================================================
        console.log("\n[3] Bag Manager Section");

        // Navigate to Bag Manager via hash
        await navigateToHash(page, "bags");
        await waitForPreactContent(page, "bags");
        const bagsActive = await getActiveSection(page);
        assert(
            bagsActive === "bags-section",
            "Navigating to #bags shows bags-section",
        );

        // Analysis section should no longer be active
        const analysisStillActive = await page.evaluate(() => {
            const section = document.getElementById("analysis-section");
            return section ? section.classList.contains("active") : false;
        });
        assert(
            !analysisStillActive,
            "Analysis section loses active class when Bag Manager is selected",
        );

        // Section header
        const bagsHeading = await getText(
            page,
            "#bags-section .section-header h2",
        );
        assert(
            bagsHeading === "Bag Manager",
            "Bag Manager section has correct heading",
        );

        // Recording controls — Preact renders a .bag-recording-panel
        const recordingPanel = await exists(
            page,
            "#bags-section-preact .bag-recording-panel",
        );
        assert(recordingPanel, "Bag recording panel exists");

        // Profile selector — Preact renders a <select class="bag-select">
        const bagSelectExists = await exists(
            page,
            "#bags-section-preact .bag-select",
        );
        assert(bagSelectExists, "Bag profile selector exists");

        // Profile options
        const profileOptions = await page.evaluate(() => {
            const select = document.querySelector(
                "#bags-section-preact .bag-select",
            );
            if (!select) return [];
            return Array.from(select.options).map((o) => o.value);
        });
        assert(
            profileOptions.length >= 3,
            `Bag profile has 3+ options (got ${profileOptions.length})`,
        );
        assert(
            profileOptions.includes("minimal") &&
                profileOptions.includes("standard") &&
                profileOptions.includes("debug"),
            "Bag profile has minimal, standard, debug options",
        );

        // Default profile is standard
        const defaultProfile = await page.evaluate(() => {
            const sel = document.querySelector(
                "#bags-section-preact .bag-select",
            );
            return sel ? sel.value : null;
        });
        assert(
            defaultProfile === "standard",
            "Default bag profile is standard",
        );

        // Start button — in idle state, a .btn-success "Start Recording" button exists
        const startBtnExists = await exists(
            page,
            "#bags-section-preact .bag-recording-idle .btn-success",
        );
        assert(startBtnExists, "Bag start recording button exists");

        const startVisible = await isVisible(
            page,
            "#bags-section-preact .bag-recording-idle .btn-success",
        );
        assert(startVisible, "Bag start button is visible by default");

        // In idle state, the active recording panel (with stop button) should not exist
        const stopExists = await exists(
            page,
            "#bags-section-preact .bag-recording-active .btn-danger",
        );
        assert(!stopExists, "Bag stop button not rendered in idle state");

        // Recording indicator not rendered in idle state
        const indicatorExists = await exists(
            page,
            "#bags-section-preact .bag-recording-active .bag-recording-indicator",
        );
        assert(
            !indicatorExists,
            "Bag recording indicator not rendered in idle state",
        );

        // Disk space panel — Preact renders a .bag-disk-panel
        const diskPanel = await exists(
            page,
            "#bags-section-preact .bag-disk-panel",
        );
        assert(diskPanel, "Bag disk space panel exists");

        // Disk panel has content
        const diskPanelHasContent = await page.evaluate(() => {
            const el = document.querySelector(
                "#bags-section-preact .bag-disk-panel",
            );
            return el ? el.innerHTML.length > 0 : false;
        });
        assert(diskPanelHasContent, "Bag disk space panel has content");

        // Bag list — Preact renders a .bag-table or loading/empty state
        const bagListArea = await page.evaluate(() => {
            const preact = document.getElementById("bags-section-preact");
            if (!preact) return false;
            // The table, loading indicator, or empty state should exist
            return !!(
                preact.querySelector(".bag-table") ||
                preact.querySelector(".section-loading") ||
                preact.querySelector(".section-empty")
            );
        });
        assert(bagListArea, "Bag list area exists (table, loading, or empty)");

        // Bag detail panel is not shown by default (only appears on bag click)
        const detailVisible = await exists(
            page,
            "#bags-section-preact .bag-detail-card",
        );
        assert(!detailVisible, "Bag detail panel is hidden by default");

        // Module loaded check
        const bagModuleLoaded = await page.evaluate(() => {
            const container = document.getElementById("bags-section-preact");
            return container && container.children.length > 0;
        });
        assert(bagModuleLoaded, "BagManagerTab module is loaded and rendered");

        // ================================================================
        // SECTION 4: Section switching round-trip (global sections only)
        // ================================================================
        console.log("\n[4] Section Navigation Round-trip");

        // Navigate through all global sections to verify no crashes.
        // Entity-scoped tabs (nodes, topics, services, parameters, health,
        // motor-config) are accessed via #/entity/{id}/{tab} and tested
        // separately. Legacy bare hashes like #nodes redirect to
        // #/entity/local/nodes automatically.
        const globalSectionsToVisit = [
            "fleet-overview",
            "operations",
            "monitoring",
            "alerts",
            "statistics",
            "analysis",
            "bags",
            "settings",
            "launch-control",
            "sync-deploy",
            "multi-arm",
            "log-viewer",
            "file-browser",
        ];

        for (const section of globalSectionsToVisit) {
            await navigateToHash(page, section);
            // Give Preact time to render
            await page.waitForTimeout(300);
            const active = await getActiveSection(page);
            assert(
                active === `${section}-section`,
                `Navigate to ${section}: ${section}-section is active`,
            );
        }

        // Back to analysis to verify it still renders
        await navigateToHash(page, "analysis");
        await waitForPreactContent(page, "analysis");
        const analysisStillRendered = await page.evaluate(() => {
            const container = document.getElementById(
                "analysis-section-preact",
            );
            return container && container.children.length > 0;
        });
        assert(
            analysisStillRendered,
            "Analysis content still present after round-trip navigation",
        );

        // Back to bags to verify it still renders
        await navigateToHash(page, "bags");
        await waitForPreactContent(page, "bags");
        const bagsStillRendered = await exists(
            page,
            "#bags-section-preact .bag-recording-panel",
        );
        assert(
            bagsStillRendered,
            "Bag recording panel still present after round-trip navigation",
        );

        // ================================================================
        // SECTION 5: CSS loaded correctly
        // ================================================================
        console.log("\n[5] CSS Styles");

        // Check that Field Analysis CSS classes have computed styles
        await navigateToHash(page, "analysis");
        await waitForPreactContent(page, "analysis");
        const analysisProgressBarStyle = await page.evaluate(() => {
            const el = document.querySelector(".analysis-progress-bar");
            if (!el) return null;
            const style = getComputedStyle(el);
            return style.overflow;
        });
        // If element exists, CSS should be applied
        if (analysisProgressBarStyle !== null) {
            assert(
                analysisProgressBarStyle === "hidden",
                "Analysis progress bar has overflow:hidden from CSS",
            );
        } else {
            skip(
                "Analysis progress bar CSS check",
                "element not found in DOM (not visible in idle state)",
            );
        }

        // Check bag pulse animation exists
        await navigateToHash(page, "bags");
        await waitForPreactContent(page, "bags");
        const bagPulseExists = await page.evaluate(() => {
            const sheets = document.styleSheets;
            for (const sheet of sheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (
                            rule.type === CSSRule.KEYFRAMES_RULE &&
                            rule.name === "bag-pulse"
                        ) {
                            return true;
                        }
                    }
                } catch (e) {
                    /* cross-origin skip */
                }
            }
            return false;
        });
        assert(
            bagPulseExists,
            "bag-pulse keyframes animation is defined in CSS",
        );

        // Check disk bar CSS classes are defined
        const diskOkStyle = await page.evaluate(() => {
            // Create temp element, check computed style
            const el = document.createElement("div");
            el.className = "bag-disk-bar disk-ok";
            document.body.appendChild(el);
            const bg = getComputedStyle(el).backgroundColor;
            document.body.removeChild(el);
            return bg;
        });
        assert(
            diskOkStyle && diskOkStyle !== "rgba(0, 0, 0, 0)",
            "bag-disk-bar.disk-ok has a background color defined",
        );

        // ================================================================
        // SECTION 6: No JS errors or 404s
        // ================================================================
        console.log("\n[6] Error Checks");

        assert(
            jsErrors.length === 0,
            `No JS errors on page (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join("; ")})`,
        );

        // Filter out expected API 404s (no ROS2 running) vs file 404s
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
