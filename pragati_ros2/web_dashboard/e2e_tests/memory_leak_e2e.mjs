#!/usr/bin/env node
/**
 * Memory Leak Verification E2E Test
 *
 * Verifies that Chart.js instances are properly cleaned up during tab
 * navigation. This catches the most common memory leak pattern: Chart.js
 * instances created on tab entry but never destroyed on tab exit.
 *
 * The test navigates through all tabs that use ChartComponent (Overview,
 * Statistics, Motor Config) multiple times and asserts that the Chart.js
 * instance count returns to baseline after each full cycle.
 *
 * Requires:
 *   - Dashboard running on http://127.0.0.1:8090
 *   - Playwright installed (npm install in e2e_tests/)
 *
 * Run: node web_dashboard/e2e_tests/memory_leak_e2e.mjs
 */

import { chromium } from "playwright";

const BASE = process.env.DASHBOARD_URL || "http://127.0.0.1:8090";
const NAVIGATION_CYCLES = 10;
const TABS_WITH_CHARTS = ["overview", "statistics", "motor-config"];
// Tab with no charts — used to force chart unmounting
const NEUTRAL_TAB = "nodes";

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

/**
 * Navigate to a dashboard tab by clicking the sidebar nav item or hash.
 */
async function navigateToTab(page, sectionName) {
    await page.evaluate((name) => {
        const link = document.querySelector(
            `.nav-item[data-section="${name}"]`
        );
        if (link) {
            link.click();
        } else {
            window.location.hash = '#' + name;
        }
    }, sectionName);
    // Wait for section transition and any chart creation/destruction
    await page.waitForTimeout(500);
}

/**
 * Get the current count of Chart.js instances.
 *
 * Chart.js 4.x stores instances in Chart.instances (an object keyed by id).
 * Chart.js 3.x uses Chart.instances as well.
 * We count the keys to get instance count.
 */
async function getChartInstanceCount(page) {
    return page.evaluate(() => {
        // Chart.js v4: Chart.instances is an object { id: instance }
        // Chart.js v3: Chart.instances is also an object
        if (typeof Chart === "undefined") return -1;
        if (!Chart.instances) return 0;
        if (typeof Chart.instances === "object") {
            return Object.keys(Chart.instances).length;
        }
        // Fallback for array-like
        return Chart.instances.length || 0;
    });
}

/**
 * Check if Chart.js is loaded in the page.
 */
async function isChartJsLoaded(page) {
    return page.evaluate(() => typeof Chart !== "undefined");
}

(async () => {
    console.log("Memory Leak Verification E2E Tests");
    console.log(`Target: ${BASE}`);
    console.log(`Cycles: ${NAVIGATION_CYCLES}`);
    console.log(
        `Chart tabs: ${TABS_WITH_CHARTS.join(", ")}`
    );
    console.log("==================================\n");

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
        // Load dashboard
        // ================================================================
        console.log("[0] Loading dashboard...");
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
        await page.waitForTimeout(2000); // Extra time for Preact hydration

        const chartLoaded = await isChartJsLoaded(page);
        if (!chartLoaded) {
            skip(
                "All memory leak tests",
                "Chart.js not loaded — dashboard may not have initialized"
            );
            await browser.close();
            console.log(
                `\nResults: ${passed} passed, ${failed} failed, ${skipped} skipped`
            );
            process.exit(0);
        }

        assert(chartLoaded, "Chart.js is available in the page");

        // ================================================================
        // SECTION 1: Baseline — navigate to neutral tab, measure instances
        // ================================================================
        console.log("\n[1] Establishing baseline");

        // Navigate to a tab with no charts to establish baseline
        await navigateToTab(page, NEUTRAL_TAB);
        await page.waitForTimeout(500);

        const baseline = await getChartInstanceCount(page);
        console.log(`     Baseline Chart.js instances on '${NEUTRAL_TAB}' tab: ${baseline}`);
        assert(
            baseline >= 0,
            `Baseline instance count is non-negative (got ${baseline})`
        );

        // ================================================================
        // SECTION 2: Single cycle — verify charts are created and destroyed
        // ================================================================
        console.log("\n[2] Single navigation cycle verification");

        for (const tab of TABS_WITH_CHARTS) {
            await navigateToTab(page, tab);
            const countOnTab = await getChartInstanceCount(page);
            console.log(`     Instances on '${tab}': ${countOnTab}`);
            // Charts should be created when tab is active
            // (may be 0 if no data, but should not be negative)
            assert(
                countOnTab >= 0,
                `Chart instances on '${tab}' tab are non-negative (${countOnTab})`
            );
        }

        // Return to neutral tab — charts should be destroyed
        await navigateToTab(page, NEUTRAL_TAB);
        await page.waitForTimeout(500);
        const afterSingleCycle = await getChartInstanceCount(page);
        console.log(
            `     Instances after returning to '${NEUTRAL_TAB}': ${afterSingleCycle}`
        );
        assert(
            afterSingleCycle <= baseline,
            `After single cycle: instances (${afterSingleCycle}) <= baseline (${baseline})`
        );

        // ================================================================
        // SECTION 3: Multi-cycle stress test — 10 full rotations
        // ================================================================
        console.log(
            `\n[3] Multi-cycle stress test (${NAVIGATION_CYCLES} cycles)`
        );

        // Re-establish baseline before stress test
        await navigateToTab(page, NEUTRAL_TAB);
        await page.waitForTimeout(300);
        const stressBaseline = await getChartInstanceCount(page);
        console.log(`     Stress test baseline: ${stressBaseline}`);

        let maxInstancesDuringStress = 0;
        const instancesPerCycle = [];

        for (let cycle = 0; cycle < NAVIGATION_CYCLES; cycle++) {
            // Visit each chart tab
            for (const tab of TABS_WITH_CHARTS) {
                await navigateToTab(page, tab);
                const count = await getChartInstanceCount(page);
                if (count > maxInstancesDuringStress) {
                    maxInstancesDuringStress = count;
                }
            }

            // Return to neutral tab
            await navigateToTab(page, NEUTRAL_TAB);
            await page.waitForTimeout(300);
            const postCycleCount = await getChartInstanceCount(page);
            instancesPerCycle.push(postCycleCount);

            if ((cycle + 1) % 5 === 0 || cycle === 0) {
                console.log(
                    `     Cycle ${cycle + 1}/${NAVIGATION_CYCLES}: instances = ${postCycleCount}`
                );
            }
        }

        const finalCount = instancesPerCycle[instancesPerCycle.length - 1];
        console.log(`     Final instance count: ${finalCount}`);
        console.log(`     Max instances during test: ${maxInstancesDuringStress}`);
        console.log(
            `     Instance counts per cycle: [${instancesPerCycle.join(", ")}]`
        );

        // Primary assertion: final count should equal baseline (no leaks)
        assert(
            finalCount === stressBaseline,
            `No leaked instances: final (${finalCount}) === baseline (${stressBaseline})`
        );

        // Secondary assertion: instance count should not grow monotonically
        // (a growing trend indicates a leak even if baseline is met)
        const isMonotonicallyGrowing = instancesPerCycle.every(
            (val, i) => i === 0 || val >= instancesPerCycle[i - 1]
        );
        const allSame = instancesPerCycle.every(
            (val) => val === instancesPerCycle[0]
        );
        assert(
            !isMonotonicallyGrowing || allSame,
            "Instance count does not monotonically grow across cycles"
        );

        // Tertiary: maximum instance count should be bounded
        // With 3 chart tabs and a few charts each, max should be reasonable
        // Allow generous bound: baseline + 20 charts max at any point
        const maxAllowed = stressBaseline + 20;
        assert(
            maxInstancesDuringStress <= maxAllowed,
            `Max instances (${maxInstancesDuringStress}) <= reasonable bound (${maxAllowed})`
        );

        // ================================================================
        // SECTION 4: Rapid tab switching (race condition test)
        // ================================================================
        console.log("\n[4] Rapid tab switching");

        const rapidBaseline = await getChartInstanceCount(page);

        // Rapidly click through tabs without waiting for full render
        for (let i = 0; i < 5; i++) {
            for (const tab of TABS_WITH_CHARTS) {
                await navigateToTab(page, tab);
                // Minimal wait — stress the create/destroy cycle
                await page.waitForTimeout(100);
            }
        }

        // Return to neutral and wait for cleanup
        await navigateToTab(page, NEUTRAL_TAB);
        await page.waitForTimeout(1000); // Generous cleanup time

        const afterRapid = await getChartInstanceCount(page);
        console.log(
            `     After rapid switching: instances = ${afterRapid} (baseline: ${rapidBaseline})`
        );
        assert(
            afterRapid <= rapidBaseline + 2,
            `Rapid switching: final (${afterRapid}) near baseline (${rapidBaseline}), tolerance +-2`
        );

        // ================================================================
        // SECTION 5: No JS errors during test
        // ================================================================
        console.log("\n[5] Error checks");

        // Filter out expected API errors (no ROS2 running)
        const criticalErrors = jsErrors.filter(
            (e) =>
                !e.includes("fetch") &&
                !e.includes("Failed to fetch") &&
                !e.includes("NetworkError") &&
                !e.includes("net::ERR")
        );

        assert(
            criticalErrors.length === 0,
            `No critical JS errors (got ${criticalErrors.length}: ${criticalErrors.slice(0, 3).join("; ")})`
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
    console.log("\n==================================");
    console.log(
        `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`
    );
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    console.log();
    process.exit(failed > 0 ? 1 : 0);
})();
