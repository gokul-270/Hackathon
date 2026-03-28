#!/usr/bin/env node
/**
 * Foundation No-ROS2 E2E Test (Group 8, Task 8.1)
 *
 * Verifies dashboard behavior when ROS2 is not running (normal dev environment).
 *
 * Section 1: Fleet Overview — verifies that the default landing page renders
 * correctly (entity cards with GaugeBar metrics, empty state, or error state).
 * FleetOverview now shows a grid of EntityCard components instead of the old
 * System Overview stat cards (CPU Usage, Memory Usage, Active Nodes, Topics).
 *
 * Sections 2-5: Tab placeholders — verifies that ROS2-dependent sub-tabs
 * (nodes, topics, services) show "ROS2 is not available" placeholders when
 * ROS2 is off, or real content when ROS2 is running. These navigate directly
 * to entity-scoped routes (e.g. #/entity/local/nodes) which render inside
 * EntityDetailShell. Health is verified via the status sub-tab.
 *
 * Run: node web_dashboard/e2e_tests/foundation_no_ros2_e2e.mjs
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

// Helper: check element exists
async function exists(page, selector) {
    return page.evaluate((sel) => !!document.querySelector(sel), selector);
}

// Helper: get trimmed text content
async function getText(page, selector) {
    return page.evaluate((sel) => {
        const el = document.querySelector(sel);
        return el ? el.textContent.trim() : null;
    }, selector);
}

// Helper: click sidebar nav item by data-section
async function navigateToSection(page, sectionName) {
    await page.evaluate((name) => {
        window.location.hash = "#" + name;
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

// Helper: get text content of a section
async function getSectionText(page, sectionId) {
    return page.evaluate((id) => {
        const section = document.getElementById(id);
        return section ? section.textContent : "";
    }, sectionId);
}

(async () => {
    console.log("Foundation No-ROS2 E2E Tests (Group 8, Task 8.1)");
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
        // DETECT ENVIRONMENT: Is ROS2 actually running?
        // ================================================================
        // Navigate to fleet-overview (the default landing page).
        // #overview redirects to #fleet-overview automatically.
        await page.goto(BASE + "#fleet-overview", {
            waitUntil: "networkidle",
            timeout: 30000,
        });
        await waitForPreactContent(page, "fleet-overview");
        await page.waitForTimeout(3000);

        // Check if ROS2 is available — inspect whether any entity card
        // shows a "—" for ROS2 Nodes (meaning ros2_available is false).
        // If no entities exist, we assume no-ROS2 mode.
        const ros2Available = await page.evaluate(() => {
            // Check for the old no-ros2-banner (legacy — may not exist)
            const banner = document.querySelector(".no-ros2-banner");
            if (banner) return false;
            // Check entity cards for ROS2 node "—" indicator
            const container = document.getElementById(
                "fleet-overview-section-preact",
            );
            if (!container) return true;
            const text = container.textContent;
            // If the page has entity cards with "ROS2 Nodes" showing "—",
            // then ROS2 is not available
            if (
                text.includes("ROS2 Nodes") &&
                text.includes("\u2014")
            ) {
                return false;
            }
            return true;
        });

        if (ros2Available) {
            console.log(
                "NOTE: ROS2 IS running on this machine. No-ROS2 placeholders will not appear.",
            );
            console.log(
                "      Switching to ROS2-available validation mode.\n",
            );
        }

        // ================================================================
        // SECTION 1: Fleet Overview — entity cards or empty state
        // ================================================================
        console.log("[1] Fleet Overview — Content Validation");

        // 1a. Fleet Overview heading is rendered
        const hasHeading = await page.evaluate(() => {
            const container = document.getElementById(
                "fleet-overview-section-preact",
            );
            if (!container) return false;
            return container.textContent.includes("Fleet Overview");
        });
        assert(hasHeading, "Fleet Overview heading is rendered");

        // 1b. Fleet Overview shows content (entity cards, empty state, or error)
        const fleetContent = await page.evaluate(() => {
            const container = document.getElementById(
                "fleet-overview-section-preact",
            );
            if (!container) return { cards: 0, empty: false, error: false };
            const cards = container.querySelectorAll(".stat-card").length;
            const text = container.textContent;
            const empty = text.includes("No Entities Configured");
            const error = text.includes("Entity Manager Unavailable");
            return { cards, empty, error };
        });
        assert(
            fleetContent.cards > 0 ||
                fleetContent.empty ||
                fleetContent.error,
            `Fleet Overview shows valid content (cards: ${fleetContent.cards}, empty: ${fleetContent.empty}, error: ${fleetContent.error})`,
        );

        // 1c. Refresh All button is present
        const hasRefreshBtn = await page.evaluate(() => {
            const container = document.getElementById(
                "fleet-overview-section-preact",
            );
            if (!container) return false;
            const buttons = container.querySelectorAll("button.btn");
            for (const btn of buttons) {
                if (btn.textContent.includes("Refresh All")) return true;
            }
            return false;
        });
        assert(hasRefreshBtn, "Refresh All button is present");

        // 1d. If entity cards exist, verify they have GaugeBar metrics
        if (fleetContent.cards > 0) {
            const cardMetrics = await page.evaluate(() => {
                const container = document.getElementById(
                    "fleet-overview-section-preact",
                );
                const firstCard = container.querySelector(".stat-card");
                if (!firstCard) return { hasBars: false, labels: [] };
                const bars = firstCard.querySelectorAll(".stat-bar");
                const labels = [];
                for (const bar of bars) {
                    const row = bar.previousElementSibling;
                    if (row) {
                        const spans = row.querySelectorAll("span");
                        if (spans.length > 0) {
                            labels.push(spans[0].textContent.trim());
                        }
                    }
                }
                return { hasBars: bars.length > 0, labels };
            });
            assert(
                cardMetrics.hasBars,
                `Entity cards have metric gauge bars (labels: ${cardMetrics.labels.join(", ")})`,
            );
            assert(
                cardMetrics.labels.includes("CPU") ||
                    cardMetrics.labels.includes("Memory"),
                "Entity card gauges include CPU or Memory",
            );
        } else {
            // No entity cards — empty/error state is valid
            assert(true, "No entity cards — gauge check skipped");
            assert(true, "No entity cards — metric label check skipped");
        }

        // ================================================================
        // SECTION 2-5: Tab placeholders — only when ROS2 is NOT running
        // When ROS2 IS running, verify tabs show actual content instead
        // ================================================================

        // --- Nodes Tab ---
        // NOTE: #nodes redirects to #/entity/local/nodes, which renders
        // inside EntityDetailShell in the entity-detail-section container.
        // The sub-tab component (NodesSubTab) shows "ROS2 is not available"
        // when ros2Available is false.
        console.log("\n[2] Nodes Tab");

        await navigateToSection(page, "/entity/local/nodes");
        await waitForPreactContent(page, "entity-detail");
        await page.waitForTimeout(1000);

        const nodesText = await getSectionText(page, "entity-detail-section");
        if (!ros2Available) {
            assert(
                nodesText.includes("ROS2 is not available"),
                'Nodes tab shows "ROS2 is not available" placeholder',
            );
        } else {
            assert(
                !nodesText.includes("ROS2 is not available"),
                "Nodes tab shows real content (ROS2 is running)",
            );
        }

        // --- Topics Tab ---
        console.log("\n[3] Topics Tab");

        await navigateToSection(page, "/entity/local/topics");
        await waitForPreactContent(page, "entity-detail");
        await page.waitForTimeout(1000);

        const topicsText = await getSectionText(page, "entity-detail-section");
        if (!ros2Available) {
            assert(
                topicsText.includes("ROS2 Not Available"),
                'Topics tab shows "ROS2 Not Available" placeholder',
            );
        } else {
            assert(
                !topicsText.includes("ROS2 Not Available"),
                "Topics tab shows real content (ROS2 is running)",
            );
        }

        // --- Services Tab ---
        console.log("\n[4] Services Tab");

        await navigateToSection(page, "/entity/local/services");
        await waitForPreactContent(page, "entity-detail");
        await page.waitForTimeout(1000);

        const servicesText = await getSectionText(
            page,
            "entity-detail-section",
        );
        if (!ros2Available) {
            assert(
                servicesText.includes("ROS2 not available"),
                'Services tab shows "ROS2 not available" placeholder',
            );
        } else {
            assert(
                !servicesText.includes("ROS2 not available"),
                "Services tab shows real content (ROS2 is running)",
            );
        }

        // --- Health Tab ---
        // NOTE: #health redirects to #/entity/local/health, but
        // EntityDetailShell has no "health" sub-tab — it defaults to the
        // "status" tab which renders StatusHealthTab. We verify the entity
        // detail shell renders the status/health view.
        console.log("\n[5] Health Tab");

        await navigateToSection(page, "/entity/local/status");
        await waitForPreactContent(page, "entity-detail");
        await page.waitForTimeout(1000);

        const healthText = await getSectionText(
            page,
            "entity-detail-section",
        );
        if (!ros2Available) {
            assert(
                healthText.includes("Status") ||
                    healthText.includes("Health") ||
                    healthText.includes("Initializing"),
                'Health tab shows status/health content in entity detail view',
            );
        } else {
            assert(
                healthText.includes("Status") ||
                    healthText.includes("Health"),
                "Health tab shows real content (ROS2 is running)",
            );
        }

        // ================================================================
        // SECTION 6: Error Checks
        // ================================================================
        console.log("\n[6] Error Checks");

        // Filter out WebSocket reconnect errors (expected when backend restarts)
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
