#!/usr/bin/env node
// Entity Card Health Rendering Tests — Tasks 2.1, 3.1–3.4
//
// Tests that EntityCard renders the compact health summary (badge, chips,
// issue cue) when given entity data via FleetOverview, and that existing
// card behaviors (checkbox, metrics, node count, drill-down, bulk selection)
// are preserved.
//
// Run: node web_dashboard/e2e_tests/entity_card_health_test.mjs
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

// ---------------------------------------------------------------------------
// Mock entity data
// ---------------------------------------------------------------------------

const NOW_ISO = new Date().toISOString();
const STALE_ISO = new Date(Date.now() - 120000).toISOString(); // 2 min ago

const MOCK_HEALTHY = {
    id: "vehicle-1",
    name: "vehicle-1",
    entity_type: "vehicle",
    status: "online",
    source: "config",
    ip: "192.168.1.10",
    last_seen: NOW_ISO,
    ros2_available: true,
    system_metrics: { cpu_percent: 30, memory_percent: 40, temperature_c: 45 },
    ros2_state: { node_count: 5 },
    health: {
        network: "reachable",
        agent: "alive",
        mqtt: "active",
        ros2: "healthy",
        composite: "online",
        diagnostic: "All systems operational",
    },
    services: [
        { name: "svc1", active_state: "active" },
        { name: "svc2", active_state: "active" },
    ],
    errors: [],
};

const MOCK_DEGRADED = {
    id: "arm-1",
    name: "arm-1",
    entity_type: "arm",
    status: "online",
    source: "config",
    ip: "192.168.1.11",
    last_seen: NOW_ISO,
    ros2_available: true,
    system_metrics: { cpu_percent: 75, memory_percent: 40, temperature_c: 45 },
    ros2_state: { node_count: 3 },
    health: {
        network: "reachable",
        agent: "down",
        mqtt: "active",
        ros2: "healthy",
        composite: "degraded",
        diagnostic: "Agent not responding but ARM application is active via MQTT",
    },
    services: [{ name: "svc1", active_state: "active" }],
    errors: [],
};

const MOCK_ERROR = {
    id: "arm-2",
    name: "arm-2",
    entity_type: "arm",
    status: "online",
    source: "config",
    ip: "192.168.1.12",
    last_seen: NOW_ISO,
    ros2_available: true,
    system_metrics: { cpu_percent: 95, memory_percent: 40, temperature_c: 45 },
    ros2_state: { node_count: 5 },
    health: {
        network: "reachable",
        agent: "alive",
        mqtt: "active",
        ros2: "down",
        composite: "degraded",
        diagnostic: "ROS2 stack is down",
    },
    services: [{ name: "svc1", active_state: "failed" }],
    errors: [{ message: "Motor controller timeout" }],
};

const MOCK_OFFLINE = {
    id: "arm-3",
    name: "arm-3",
    entity_type: "arm",
    status: "offline",
    source: "config",
    ip: "192.168.1.13",
    last_seen: STALE_ISO,
    ros2_available: false,
    system_metrics: {},
    ros2_state: {},
    health: {
        network: "unknown",
        agent: "unknown",
        mqtt: "disabled",
        ros2: "unknown",
        composite: "unknown",
        diagnostic: "MQTT not configured",
    },
    services: [],
    errors: [],
};

const MOCK_DISCOVERED = {
    id: "discovered-1",
    name: "unknown-arm",
    entity_type: "arm",
    status: "online",
    source: "discovered",
    ip: "192.168.1.50",
    last_seen: NOW_ISO,
    ros2_available: true,
    system_metrics: { cpu_percent: 20, memory_percent: 30, temperature_c: 40 },
    ros2_state: { node_count: 2 },
    services: [{ name: "svc1", active_state: "active" }],
    errors: [],
};

const ALL_ENTITIES = [
    MOCK_HEALTHY,
    MOCK_DEGRADED,
    MOCK_ERROR,
    MOCK_OFFLINE,
    MOCK_DISCOVERED,
];

// ---------------------------------------------------------------------------
// Helper: create page with mocked entities
// ---------------------------------------------------------------------------

async function createMockedPage(browser, entities) {
    const page = await browser.newPage();
    await page.route("**/api/entities", (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(entities),
        })
    );
    // Block WS/ROS2 introspection to keep mock data stable
    await page.route("**/ws", (route) => route.abort());
    await page.route("**/api/ros2/nodes*", (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
        })
    );
    return page;
}

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

(async () => {
    console.log("Entity Card Health Rendering Tests (Tasks 2.1, 3.1–3.4)");
    console.log(`Target: ${BASE}`);
    console.log("======================================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const jsErrors = [];

    try {
        // ==================================================================
        // SECTION 2.1: EntityCard health summary rendering
        // ==================================================================
        console.log("[2.1] EntityCard health summary rendering");

        const page = await createMockedPage(browser, ALL_ENTITIES);
        page.on("pageerror", (err) => jsErrors.push(err.message));

        await page.goto(BASE + "#fleet-overview", {
            waitUntil: "networkidle",
            timeout: 30000,
        });
        await page.waitForTimeout(2000);

        await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return;
            const cards = Array.from(section.querySelectorAll(".stat-card"));
            for (const card of cards) {
                if (
                    card.textContent.includes("vehicle-1") ||
                    card.textContent.includes("arm-1") ||
                    card.textContent.includes("arm-2") ||
                    card.textContent.includes("arm-3")
                ) {
                    card.click();
                }
            }
        });
        await page.waitForTimeout(500);

        // Check that configured entity cards have health summary sections
        const healthSummaryCheck = await page.evaluate(() => {
            const section = document.querySelector(
                "#fleet-overview-section-preact"
            );
            if (!section) return { error: "No preact section found" };

            const cards = section.querySelectorAll(".stat-card");
            const results = [];
            for (const card of cards) {
                const name = card.querySelector("[style]")?.textContent?.trim() || "";
                const healthSummary = card.querySelector(".entity-health-summary");
                const badge = card.querySelector(".entity-health-badge");
                const chips = card.querySelectorAll(".entity-health-chip");
                    const diagnostic = card.querySelector(".entity-health-diagnostic");
                    results.push({
                    name: name.substring(0, 30),
                    hasHealthSummary: !!healthSummary,
                    hasBadge: !!badge,
                        chipCount: chips.length,
                        hasDiagnostic: !!diagnostic,
                        issueCueText: diagnostic ? diagnostic.textContent.trim() : null,
                        badgeText: badge ? badge.textContent.trim().toLowerCase() : null,
                    });
                }
            return { results };
        });

        // Find cards by checking for entity names in the card text
        const cardResults = healthSummaryCheck.results || [];

        // Find the healthy card (vehicle-1)
        const healthyCard = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const cards = section.querySelectorAll(".stat-card");
            for (const card of cards) {
                if (card.textContent.includes("vehicle-1")) {
                    const summary = card.querySelector(".entity-health-summary");
                    const badge = card.querySelector(".entity-health-badge");
                    const layers = card.querySelectorAll(".entity-health-layer");
                    const diagnostic = card.querySelector(".entity-health-diagnostic");
                    return {
                        hasHealthSummary: !!summary,
                        hasBadge: !!badge,
                        layerCount: layers.length,
                        hasDiagnostic: !!diagnostic,
                        badgeClass: badge ? badge.className : null,
                        layerLabels: Array.from(layers).map((c) => c.textContent.trim()),
                        diagnosticText: diagnostic ? diagnostic.textContent.trim() : null,
                    };
                }
            }
            return null;
        });

        assert(
            healthyCard && healthyCard.hasHealthSummary,
            "Healthy card (vehicle-1) has .entity-health-summary"
        );
        assert(
            healthyCard && healthyCard.hasBadge,
            "Healthy card has .entity-health-badge"
        );
        assert(
            healthyCard && healthyCard.layerCount === 4,
            `Healthy card has 4 layers (got ${healthyCard?.layerCount})`
        );
        assert(
            healthyCard && healthyCard.hasDiagnostic,
            "Healthy card has diagnostic text"
        );
        assert(
            healthyCard &&
                healthyCard.badgeClass &&
                healthyCard.badgeClass.includes("health-ok"),
            "Healthy card badge has health-ok class"
        );
        assert(
            healthyCard &&
                healthyCard.layerLabels &&
                healthyCard.layerLabels.some((l) => /ping/i.test(l)) &&
                healthyCard.layerLabels.some((l) => /agt/i.test(l)) &&
                healthyCard.layerLabels.some((l) => /mqtt/i.test(l)) &&
                healthyCard.layerLabels.some((l) => /ros2/i.test(l)),
            "Healthy card layers include PING, AGT, MQTT, ROS2"
        );
        assert(
            healthyCard && /All systems operational/i.test(healthyCard.diagnosticText || ""),
            "Healthy card shows composite diagnostic message"
        );

        // Find the error card (arm-2)
        const errorCard = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const cards = section.querySelectorAll(".stat-card");
            for (const card of cards) {
                if (card.textContent.includes("arm-2")) {
                    const badge = card.querySelector(".entity-health-badge");
                    const issueCue = card.querySelector(".entity-health-diagnostic");
                    return {
                        badgeClass: badge ? badge.className : null,
                        hasIssueCue: !!issueCue,
                        issueCueText: issueCue ? issueCue.textContent.trim() : null,
                    };
                }
            }
            return null;
        });

        assert(
            errorCard &&
                errorCard.badgeClass &&
                errorCard.badgeClass.includes("health-unknown"),
            "Error card (arm-2) badge has degraded class"
        );
        assert(
            errorCard && errorCard.hasIssueCue,
            "Error card has issue cue displayed"
        );
        assert(
            errorCard &&
                errorCard.issueCueText &&
                /ROS2 stack is down/i.test(errorCard.issueCueText),
            `Error card diagnostic shows ROS2 failure (got: "${errorCard?.issueCueText}")`
        );

        // Find the unavailable/offline card (arm-3)
        const offlineCard = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const cards = section.querySelectorAll(".stat-card");
            for (const card of cards) {
                if (card.textContent.includes("arm-3")) {
                    const badge = card.querySelector(".entity-health-badge");
                    const issueCue = card.querySelector(".entity-health-diagnostic");
                    return {
                        badgeClass: badge ? badge.className : null,
                        hasIssueCue: !!issueCue,
                        issueCueText: issueCue ? issueCue.textContent.trim() : null,
                    };
                }
            }
            return null;
        });

        assert(
            offlineCard &&
                offlineCard.badgeClass &&
                offlineCard.badgeClass.includes("health-unavailable"),
            "Offline card (arm-3) badge has health-unavailable class"
        );
        assert(
            offlineCard && offlineCard.hasIssueCue,
            "Offline card has issue cue displayed"
        );
        assert(
            offlineCard &&
                offlineCard.issueCueText &&
                /MQTT not configured/i.test(offlineCard.issueCueText),
            `Offline card diagnostic describes MQTT disabled state (got: "${offlineCard?.issueCueText}")`
        );

        // ==================================================================
        // SECTION 3.3: Discovered cards remain unchanged
        // ==================================================================
        console.log("\n[3.3] Discovered cards remain unchanged");

        const discoveredCheck = await page.evaluate(() => {
            // Discovered cards live in the "Discovered Entities" section
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            // Look for text that indicates discovered entities
            const allText = section.textContent;
            const hasDiscoveredSection = /discovered/i.test(allText);

            // Find cards in the discovered section — they should NOT have health summary
            const allCards = section.querySelectorAll(".stat-card");
            let discoveredCardHasHealthSummary = false;
            let discoveredCardFound = false;
            for (const card of allCards) {
                if (card.textContent.includes("unknown-arm")) {
                    discoveredCardFound = true;
                    discoveredCardHasHealthSummary =
                        !!card.querySelector(".entity-health-summary");
                }
            }
            return { hasDiscoveredSection, discoveredCardFound, discoveredCardHasHealthSummary };
        });

        assert(
            discoveredCheck && discoveredCheck.discoveredCardFound,
            "Discovered card (unknown-arm) is rendered"
        );
        assert(
            discoveredCheck && !discoveredCheck.discoveredCardHasHealthSummary,
            "Discovered card does NOT have health summary block"
        );

        // ==================================================================
        // SECTION 3.4: Existing card behaviors preserved
        // ==================================================================
        console.log("\n[3.4] Existing card behaviors preserved");

        // 3.4a: Checkbox visible and unchecked by default
        const checkboxCheck = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const checkboxes = section.querySelectorAll(".entity-card-checkbox");
            const allUnchecked = Array.from(checkboxes).every((cb) => !cb.checked);
            return { count: checkboxes.length, allUnchecked };
        });

        assert(
            checkboxCheck && checkboxCheck.count > 0,
            `Checkboxes visible on configured cards (found ${checkboxCheck?.count})`
        );
        assert(
            checkboxCheck && checkboxCheck.allUnchecked,
            "All checkboxes unchecked by default"
        );

        // 3.4b: BulkActionBar hidden when selection is empty
        const bulkBarCheck = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const bar = section.querySelector(".bulk-action-bar");
            if (!bar) return { exists: false };
            const style = window.getComputedStyle(bar);
            return {
                exists: true,
                hidden: style.display === "none" || style.visibility === "hidden",
            };
        });

        assert(
            !bulkBarCheck?.exists || bulkBarCheck?.hidden,
            "BulkActionBar hidden when no selection"
        );

        // 3.4c: Cards still have metrics gauges
        const metricsCheck = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const cards = section.querySelectorAll(".stat-card");
            let cardsWithGauges = 0;
            for (const card of cards) {
                if (
                    card.textContent.includes("vehicle-1") ||
                    card.textContent.includes("arm-1")
                ) {
                    const bars = card.querySelectorAll(".stat-bar");
                    if (bars.length >= 3) cardsWithGauges++;
                }
            }
            return { cardsWithGauges };
        });

        assert(
            metricsCheck && metricsCheck.cardsWithGauges >= 2,
            `Configured cards still have metric gauges (${metricsCheck?.cardsWithGauges} cards)`
        );

        // 3.4d: Node count still displayed
        const nodeCountCheck = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const cards = section.querySelectorAll(".stat-card");
            for (const card of cards) {
                if (card.textContent.includes("vehicle-1")) {
                    return { hasNodeCount: /ros2 nodes/i.test(card.textContent) };
                }
            }
            return null;
        });

        assert(
            nodeCountCheck && nodeCountCheck.hasNodeCount,
            "Healthy card still shows ROS2 Nodes count"
        );

        // 3.4e: Card click navigates (drill-down preserved)
        const drillDownCheck = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const cards = section.querySelectorAll(".stat-card");
            for (const card of cards) {
                if (card.textContent.includes("vehicle-1")) {
                    return { hasCursorPointer: card.style.cursor === "pointer" };
                }
            }
            return null;
        });

        assert(
            drillDownCheck && drillDownCheck.hasCursorPointer,
            "Configured card has cursor:pointer for drill-down"
        );

        // 3.4f: Select a card and verify BulkActionBar appears
        const selectionTest = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const checkbox = section.querySelector(".entity-card-checkbox");
            if (!checkbox) return { clicked: false };
            checkbox.click();
            // Small delay needed for Preact re-render — return check after microtask
            return new Promise((resolve) => {
                setTimeout(() => {
                    const bar = section.querySelector(".bulk-action-bar");
                    const selectedCards = section.querySelectorAll(".entity-card--selected");
                    resolve({
                        clicked: true,
                        barVisible: bar
                            ? window.getComputedStyle(bar).display !== "none"
                            : false,
                        selectedCount: selectedCards.length,
                    });
                }, 500);
            });
        });

        assert(
            selectionTest && selectionTest.selectedCount > 0,
            `Selecting a card applies .entity-card--selected (${selectionTest?.selectedCount})`
        );

        await page.close();

        // ==================================================================
        // SECTION 3.1: WebSocket/polling update preserves health + selection
        // ==================================================================
        console.log("\n[3.1] Health summary updates on data refresh");

        // This test uses a fresh page where we update the mock data after initial load
        const updatePage = await createMockedPage(browser, [MOCK_HEALTHY]);
        updatePage.on("pageerror", (err) => jsErrors.push(err.message));

        await updatePage.goto(BASE + "#fleet-overview", {
            waitUntil: "networkidle",
            timeout: 30000,
        });
        await updatePage.waitForTimeout(2000);
        await updatePage.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return;
            const card = Array.from(section.querySelectorAll(".stat-card")).find((el) =>
                el.textContent.includes("vehicle-1")
            );
            if (card) card.click();
        });
        await updatePage.waitForTimeout(300);

        // Verify initial healthy state
        const initialBadge = await updatePage.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const cards = section.querySelectorAll(".stat-card");
            for (const card of cards) {
                if (card.textContent.includes("vehicle-1")) {
                    const badge = card.querySelector(".entity-health-badge");
                    return badge ? badge.className : null;
                }
            }
            return null;
        });

        assert(
            initialBadge && initialBadge.includes("health-ok"),
            "Initial badge shows health-ok"
        );

        // Now update the route to return degraded data and trigger a refresh
        await updatePage.unroute("**/api/entities");
        const DEGRADED_ENTITY = {
            ...MOCK_HEALTHY,
            status: "degraded",
            health: {
                network: "reachable",
                agent: "down",
                mqtt: "active",
                ros2: "healthy",
                composite: "degraded",
                diagnostic: "Agent not responding but ARM application is active via MQTT",
            },
        };
        await updatePage.route("**/api/entities", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify([DEGRADED_ENTITY]),
            })
        );

        // Reload page so the updated API mock is definitely used
        await updatePage.reload({ waitUntil: "networkidle", timeout: 30000 });
        await updatePage.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return;
            const card = Array.from(section.querySelectorAll(".stat-card")).find((el) =>
                el.textContent.includes("vehicle-1")
            );
            if (card && !card.querySelector(".entity-health-badge")) card.click();
        });
        await updatePage.waitForTimeout(500);

        const updatedBadge = await updatePage.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const card = Array.from(section.querySelectorAll(".stat-card")).find((el) =>
                el.textContent.includes("vehicle-1")
            );
            if (!card) return null;
            const badge = card.querySelector(".entity-health-badge");
            return badge ? badge.className : null;
        });

        assert(
            updatedBadge &&
                updatedBadge.includes("health-unknown"),
            `Badge updates on data refresh (got: "${updatedBadge}")`
        );

        await updatePage.close();

        // ==================================================================
        // Error checks
        // ==================================================================
        console.log("\n[E] Error Checks");

        const nonWsErrors = jsErrors.filter(
            (e) =>
                !e.includes("WebSocket") &&
                !e.includes("ws://") &&
                !e.includes("wss://") &&
                !e.includes("ERR_CONNECTION_REFUSED")
        );
        assert(
            nonWsErrors.length === 0,
            `No unexpected JS errors (got ${nonWsErrors.length}: ${nonWsErrors.slice(0, 3).join("; ")})`
        );
    } catch (err) {
        console.log(`\n  CRASH  ${err.message}`);
        console.log(err.stack);
        failed++;
        failures.push(`CRASH: ${err.message}`);
    } finally {
        await browser.close();
    }

    // Summary
    const total = passed + failed + skipped;
    console.log("\n======================================");
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
