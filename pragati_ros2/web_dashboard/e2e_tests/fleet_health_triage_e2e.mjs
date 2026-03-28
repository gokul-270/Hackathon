#!/usr/bin/env node
// Fleet Health Triage E2E Test — Task 4.1
//
// Tests the operator triage workflow:
// 1. Unhealthy card shows issue cue on fleet overview
// 2. Card click drills into entity detail
// 3. Selection checkbox behavior preserved
//
// Run: node web_dashboard/e2e_tests/fleet_health_triage_e2e.mjs
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

const NOW_ISO = new Date().toISOString();

const MOCK_ENTITIES = [
    {
        id: "vehicle-triage",
        name: "vehicle-triage",
        entity_type: "vehicle",
        status: "online",
        source: "config",
        ip: "192.168.1.10",
        last_seen: NOW_ISO,
        ros2_available: true,
        system_metrics: { cpu_percent: 92, memory_percent: 40, temperature_c: 45 },
        ros2_state: { node_count: 5 },
        services: [{ name: "svc1", active_state: "failed" }],
        errors: [{ message: "CAN bus timeout on motor 3" }],
    },
    {
        id: "arm-healthy",
        name: "arm-healthy",
        entity_type: "arm",
        status: "online",
        source: "config",
        ip: "192.168.1.11",
        last_seen: NOW_ISO,
        ros2_available: true,
        system_metrics: { cpu_percent: 25, memory_percent: 30, temperature_c: 40 },
        ros2_state: { node_count: 3 },
        services: [{ name: "svc1", active_state: "active" }],
        errors: [],
    },
];

(async () => {
    console.log("Fleet Health Triage E2E Test (Task 4.1)");
    console.log(`Target: ${BASE}`);
    console.log("======================================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));

    await page.route("**/api/entities", (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(MOCK_ENTITIES),
        })
    );
    await page.route("**/ws", (route) => route.abort());
    await page.route("**/api/ros2/nodes*", (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
        })
    );

    try {
        await page.goto(BASE + "#fleet-overview", {
            waitUntil: "networkidle",
            timeout: 30000,
        });
        await page.waitForTimeout(2000);

        // 1. Unhealthy card shows issue cue on fleet overview
        console.log("[1] Unhealthy card triage visibility");

        const triageCard = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const cards = section.querySelectorAll(".stat-card");
            for (const card of cards) {
                if (card.textContent.includes("vehicle-triage")) {
                    const badge = card.querySelector(".entity-health-badge");
                    const issueCue = card.querySelector(".entity-health-issue-cue");
                    const chips = card.querySelectorAll(".entity-health-chip");
                    return {
                        badgeClass: badge ? badge.className : null,
                        badgeText: badge ? badge.textContent.trim() : null,
                        issueCueText: issueCue ? issueCue.textContent.trim() : null,
                        chipCount: chips.length,
                    };
                }
            }
            return null;
        });

        assert(
            triageCard &&
                triageCard.badgeClass &&
                triageCard.badgeClass.includes("health-error"),
            "Unhealthy card badge shows error state"
        );
        assert(
            triageCard &&
                triageCard.issueCueText &&
                triageCard.issueCueText.includes("CAN bus timeout"),
            `Issue cue shows primary error (got: "${triageCard?.issueCueText}")`
        );
        assert(
            triageCard && triageCard.chipCount === 3,
            "Unhealthy card shows 3 subsystem chips"
        );

        // 2. Card click drills into entity detail
        console.log("\n[2] Card click drill-down");

        await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            const cards = section.querySelectorAll(".stat-card");
            for (const card of cards) {
                if (card.textContent.includes("vehicle-triage")) {
                    card.click();
                    break;
                }
            }
        });
        await page.waitForTimeout(1500);

        const hash = await page.evaluate(() => window.location.hash);
        assert(
            hash.includes("entity-detail") || hash.includes("vehicle-triage"),
            `Card click navigates to entity detail (hash: "${hash}")`
        );

        // 3. Navigate back and verify selection checkbox behavior
        console.log("\n[3] Selection checkbox preserved after navigation");

        await page.evaluate(() => {
            window.location.hash = "#fleet-overview";
        });
        await page.waitForTimeout(2000);

        const checkboxResult = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const checkbox = section.querySelector(".entity-card-checkbox");
            if (!checkbox) return { found: false };

            // Click to select
            checkbox.click();
            return new Promise((resolve) => {
                setTimeout(() => {
                    const selected = section.querySelectorAll(".entity-card--selected");
                    resolve({
                        found: true,
                        selectedCount: selected.length,
                    });
                }, 500);
            });
        });

        assert(
            checkboxResult && checkboxResult.found,
            "Checkbox found after navigation back"
        );
        assert(
            checkboxResult && checkboxResult.selectedCount > 0,
            "Selection works after drill-down and return"
        );

        // 4. Healthy card contrast
        console.log("\n[4] Healthy card contrast");

        const healthyCheck = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return null;
            const cards = section.querySelectorAll(".stat-card");
            for (const card of cards) {
                if (card.textContent.includes("arm-healthy")) {
                    const badge = card.querySelector(".entity-health-badge");
                    const issueCue = card.querySelector(".entity-health-issue-cue");
                    return {
                        badgeClass: badge ? badge.className : null,
                        hasIssueCue: !!issueCue,
                    };
                }
            }
            return null;
        });

        assert(
            healthyCheck &&
                healthyCheck.badgeClass &&
                healthyCheck.badgeClass.includes("health-ok"),
            "Healthy card badge shows ok state"
        );
        assert(
            healthyCheck && !healthyCheck.hasIssueCue,
            "Healthy card has no issue cue"
        );

        // Error checks
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
            `No unexpected JS errors (got ${nonWsErrors.length})`
        );
    } catch (err) {
        console.log(`\n  CRASH  ${err.message}`);
        failed++;
        failures.push(`CRASH: ${err.message}`);
    } finally {
        await browser.close();
    }

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
