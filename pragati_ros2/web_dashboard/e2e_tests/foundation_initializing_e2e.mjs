#!/usr/bin/env node
/**
 * Foundation Initializing State E2E Test (Group 8, Task 8.3)
 *
 * Verifies the "Initializing..." transient state that appears before the first
 * system_state WebSocket message arrives. Each Preact tab (Overview, Nodes,
 * Topics, Services, Health) checks `systemState === null` and renders an
 * "Initializing..." placeholder until the first message sets it.
 *
 * Strategy: Load the page with `waitUntil: 'domcontentloaded'` (NOT networkidle)
 * and immediately check for the initializing state before WebSocket data arrives.
 * This is inherently timing-sensitive — if the system_state arrives very fast
 * on a fast machine, we may miss the initializing state. We assert that the
 * section shows EITHER "Initializing..." OR proper post-initialization content
 * (no-ROS2 banner / real data), but never blank/zero.
 *
 * After waiting for data, we verify the transition to a proper state.
 *
 * Run: node web_dashboard/e2e_tests/foundation_initializing_e2e.mjs
 *
 * Requires: npm install playwright (in this directory)
 * Dashboard must be running on http://127.0.0.1:8090
 */
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

// Helper: navigate to a tab via hash change (sidebar uses hash navigation)
async function navigateToSection(page, sectionName) {
    await page.evaluate((name) => {
        window.location.hash = "#" + name;
    }, sectionName);
    await page.waitForTimeout(500);
}

// Helper: get text content of a section
async function getSectionText(page, sectionId) {
    return page.evaluate((id) => {
        const section = document.getElementById(id);
        return section ? section.textContent : "";
    }, sectionId);
}

// Helper: wait for Preact to render content into a section's -preact container
async function waitForPreactContent(page, sectionId, timeoutMs = 8000) {
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
    console.log("Foundation Initializing State E2E Tests (Group 8, Task 8.3)");
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

    try {
        // ================================================================
        // SECTION 1: Capture initializing state on overview tab
        // ================================================================
        console.log("[1] Fleet Overview — Initializing State (race with WebSocket)");

        // Load page quickly — domcontentloaded fires before WebSocket data arrives
        await page.goto(BASE + "#fleet-overview", {
            waitUntil: "domcontentloaded",
            timeout: 30000,
        });
        // Brief pause for Preact to mount and render initial state
        await page.waitForTimeout(500);

        // Try to capture the initializing state.
        // This is timing-sensitive: on fast machines, system_state may arrive
        // before we can check. We accept either state as valid.
        const earlyOverviewText = await getSectionText(page, "fleet-overview-section");

        const caughtInitializing = earlyOverviewText.includes("Initializing");
        const caughtPostInit =
            earlyOverviewText.includes("ROS2") ||
            earlyOverviewText.includes("CPU") ||
            earlyOverviewText.includes("Fleet Overview") ||
            earlyOverviewText.includes("Fleet");

        if (caughtInitializing) {
            console.log('    (caught "Initializing..." state)');
            assert(
                true,
                'Fleet Overview shows "Initializing..." before system_state arrives',
            );
        } else if (caughtPostInit) {
            console.log(
                "    (system_state arrived before check — verifying post-init content)",
            );
            skip(
                'Fleet Overview "Initializing..." state',
                "system_state arrived too fast to catch transient state",
            );
        } else {
            // Neither initializing nor real content — something is wrong
            assert(
                false,
                `Fleet Overview shows initializing or real content, not blank (got: "${earlyOverviewText.slice(0, 120)}")`,
            );
        }

        // Verify the section is not completely empty
        assert(
            earlyOverviewText.length > 0,
            "Fleet Overview section has content (not blank)",
        );

        // ================================================================
        // SECTION 2: Wait for transition from initializing to real state
        // ================================================================
        console.log("\n[2] Fleet Overview — Post-Initialization Transition");

        // Wait for WebSocket data to arrive and Preact to re-render
        await waitForPreactContent(page, "fleet-overview");
        await page.waitForTimeout(5000);

        const finalOverviewText = await getSectionText(
            page,
            "fleet-overview-section",
        );
        assert(
            !finalOverviewText.includes("Initializing"),
            'Fleet Overview transitioned away from "Initializing..." state',
        );
        assert(
            finalOverviewText.includes("CPU") ||
                finalOverviewText.includes("Fleet Overview") ||
                finalOverviewText.includes("Fleet"),
            "Fleet Overview shows real content after initialization (CPU stats or Fleet Overview heading)",
        );

        // Verify stat cards show proper values (not blank, not "0%" for CPU/Memory)
        const statValues = await page.evaluate(() => {
            const cards = document.querySelectorAll(
                "#fleet-overview-section-preact .stat-card",
            );
            const result = {};
            for (const card of cards) {
                const label = card.querySelector(".stat-label");
                const value = card.querySelector(".stat-value");
                if (label && value) {
                    result[label.textContent.trim()] = value.textContent.trim();
                }
            }
            return result;
        });

        if (statValues["CPU Usage"]) {
            assert(
                statValues["CPU Usage"] !== "0.0%" &&
                    statValues["CPU Usage"] !== "",
                `CPU stat card shows non-zero value after init (got: "${statValues["CPU Usage"]}")`,
            );
        }
        if (statValues["Memory Usage"]) {
            assert(
                statValues["Memory Usage"] !== "0.0%" &&
                    statValues["Memory Usage"] !== "",
                `Memory stat card shows non-zero value after init (got: "${statValues["Memory Usage"]}")`,
            );
        }
        if (statValues["Active Nodes"]) {
            // Should be "N/A" (no ROS2) or a number, never blank
            assert(
                statValues["Active Nodes"] !== "",
                `Active Nodes stat card has a value after init (got: "${statValues["Active Nodes"]}")`,
            );
        }
        if (statValues["Topics"]) {
            assert(
                statValues["Topics"] !== "",
                `Topics stat card has a value after init (got: "${statValues["Topics"]}")`,
            );
        }

        // ================================================================
        // SECTION 3: Other tabs also transition properly
        // (nodes, topics, services, health are now entity sub-tabs)
        // ================================================================
        console.log("\n[3] Other Tabs — Post-Initialization State (entity-scoped)");

        // Entity sub-tabs: navigate via entity-scoped routes and check
        // #entity-detail-section instead of old standalone section IDs
        const entitySubTabs = [
            { route: "/entity/local/nodes", label: "Nodes" },
            { route: "/entity/local/topics", label: "Topics" },
            { route: "/entity/local/services", label: "Services" },
            { route: "/entity/local/status", label: "Status (health)" },
        ];

        for (const tab of entitySubTabs) {
            await page.evaluate((r) => {
                window.location.hash = "#" + r;
            }, tab.route);
            await page.waitForTimeout(2000);

            const tabText = await getSectionText(
                page,
                "entity-detail-section",
            );
            assert(
                !tabText.includes("Initializing"),
                `${tab.label} tab is not stuck in "Initializing..." state`,
            );
            const tabHasContent =
                tabText.includes("ROS2 daemon not connected") ||
                tabText.includes(tab.label) ||
                tabText.includes("Health") ||
                tabText.includes("Status") ||
                tabText.length > 10;
            assert(
                tabHasContent,
                `${tab.label} tab shows proper content after init (placeholder or data)`,
            );
        }

        // ================================================================
        // SECTION 4: Error Checks
        // ================================================================
        console.log("\n[4] Error Checks");

        const nonWsErrors = jsErrors.filter(
            (e) =>
                !e.includes("WebSocket") &&
                !e.includes("ws://") &&
                !e.includes("wss://"),
        );
        assert(
            nonWsErrors.length === 0,
            `No unexpected JS errors (got ${nonWsErrors.length}: ${nonWsErrors.slice(0, 3).join("; ")})`,
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
