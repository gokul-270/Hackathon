#!/usr/bin/env node
// Entity Detail Shell Tab Bar Visibility E2E Test Suite (Task 8.7)
//
// Tests entity detail shell tab bar visibility rules:
// - Motor Config visible for arm entities
// - Motor Config visible for vehicle entities (entityTypes: null)
// - Rosbag visible for all entity types
//
// Run: node web_dashboard/e2e_tests/test_entity_tab_visibility.mjs
//
// Requires: npm install playwright (in e2e_tests directory)
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

// Helper: navigate via hash change
async function navigateToHash(page, hash) {
    await page.evaluate((h) => {
        window.location.hash = h;
    }, hash);
    await page.waitForTimeout(2000);
}

// Helper: get all tab button labels from entity detail section
async function getTabLabels(page) {
    return page.evaluate(() => {
        const section = document.getElementById("entity-detail-section");
        if (!section) return [];
        const buttons = section.querySelectorAll("button");
        const labels = [];
        for (const btn of buttons) {
            const text = btn.textContent.trim();
            // Filter to known entity detail tab labels
            if (
                [
                    "Status & Health",
                    "Status / Health",
                    "Motor Config",
                    "Rosbag",
                    "Nodes",
                    "Topics",
                    "Services",
                    "Parameters",
                    "Logs",
                ].includes(text)
            ) {
                labels.push(text);
            }
        }
        return labels;
    });
}

// Helper: get current hash
async function getHash(page) {
    return page.evaluate(() => location.hash);
}

// ---------------------------------------------------------------------------
// Mock entity data
// ---------------------------------------------------------------------------

const ARM_ENTITY_DATA = {
    id: "arm1",
    name: "Arm 1 RPi",
    entity_type: "arm",
    source: "remote",
    ip: "192.168.1.101",
    status: "online",
    last_seen: new Date().toISOString(),
    system_metrics: {
        cpu_percent: 45.0,
        memory_percent: 38.0,
        temperature_c: 42.0,
        disk_percent: 25.0,
        uptime_seconds: 7200,
    },
    ros2_available: true,
    ros2_state: {
        node_count: 2,
        nodes: [
            {
                name: "/arm_controller",
                namespace: "/",
                lifecycle_state: "active",
            },
            {
                name: "/can_bridge",
                namespace: "/",
                lifecycle_state: "active",
            },
        ],
    },
    services: [
        {
            name: "pragati-arm.service",
            active_state: "active",
            sub_state: "running",
        },
    ],
    errors: [],
    metadata: {},
};

const VEHICLE_ENTITY_DATA = {
    id: "vehicle1",
    name: "Vehicle Controller",
    entity_type: "vehicle",
    source: "remote",
    ip: "192.168.1.100",
    status: "online",
    last_seen: new Date().toISOString(),
    system_metrics: {
        cpu_percent: 30.0,
        memory_percent: 25.0,
        temperature_c: 38.0,
        disk_percent: 20.0,
        uptime_seconds: 3600,
    },
    ros2_available: true,
    ros2_state: {
        node_count: 1,
        nodes: [
            {
                name: "/vehicle_controller",
                namespace: "/",
                lifecycle_state: "active",
            },
        ],
    },
    services: [],
    errors: [],
    metadata: {},
};

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

(async () => {
    console.log("Entity Detail Shell Tab Bar Visibility E2E Tests (Task 8.7)");
    console.log(`Target: ${BASE}`);
    console.log("==========================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();

    // Collect JS console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
        if (msg.type() === "error") {
            consoleErrors.push(msg.text());
        }
    });

    const pageErrors = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));

    try {
        // ==========================================================
        // Route mocking setup
        // ==========================================================

        // Abort WebSocket connections (no WS server in test)
        await page.route("**/ws", (route) =>
            route.abort("connectionrefused")
        );

        // Mock arm1 entity data
        await page.route("**/api/entities/arm1", (route) => {
            if (route.request().url().endsWith("/arm1")) {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify(ARM_ENTITY_DATA),
                });
            } else {
                route.continue();
            }
        });

        // Mock vehicle1 entity data
        await page.route("**/api/entities/vehicle1", (route) => {
            if (route.request().url().endsWith("/vehicle1")) {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify(VEHICLE_ENTITY_DATA),
                });
            } else {
                route.continue();
            }
        });

        // Mock rosbag endpoints so they don't cause errors
        await page.route("**/rosbag/record/status", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({
                    recording: false,
                    profile: null,
                    duration_s: 0,
                    estimated_size_mb: 0,
                    disk_remaining_mb: 50000,
                }),
            })
        );

        await page.route("**/rosbag/list", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify([]),
            })
        );

        // ==========================================================
        // Load dashboard
        // ==========================================================
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
        await page.waitForTimeout(1000);

        // ==========================================================
        // [1] Motor Config visible for arm entity
        // ==========================================================
        console.log("[1] Motor Config visible for arm entity");

        await navigateToHash(page, "#/entity/arm1/status");

        const armTabs = await getTabLabels(page);
        assert(
            armTabs.includes("Motor Config"),
            `Arm entity tab bar contains "Motor Config" (found: ${JSON.stringify(armTabs)})`
        );

        // Verify it's a clickable button (not dimmed/disabled)
        const motorConfigBtn = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return null;
            const buttons = section.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Motor Config") {
                    return {
                        disabled: btn.disabled,
                        opacity: getComputedStyle(btn).opacity,
                        cursor: getComputedStyle(btn).cursor,
                    };
                }
            }
            return null;
        });
        assert(
            motorConfigBtn !== null && !motorConfigBtn.disabled,
            "Motor Config tab button is enabled for arm entity"
        );

        // ==========================================================
        // [2] Motor Config visible for vehicle entity (entityTypes: null)
        // ==========================================================
        console.log("\n[2] Motor Config visible for vehicle entity");

        await navigateToHash(page, "#/entity/vehicle1/status");

        const vehicleTabs = await getTabLabels(page);
        assert(
            vehicleTabs.includes("Motor Config"),
            `Vehicle entity tab bar contains "Motor Config" (found: ${JSON.stringify(vehicleTabs)})`
        );

        // ==========================================================
        // [3] Motor Config clickable on vehicle entity
        // ==========================================================
        console.log("\n[3] Motor Config clickable on vehicle entity");

        // Navigate vehicle to motor-config — should stay (no redirect)
        await navigateToHash(page, "#/entity/vehicle1/motor-config");

        await page.waitForTimeout(1500);

        const hashAfterNav = await getHash(page);
        assert(
            hashAfterNav.includes("/entity/vehicle1/motor-config"),
            `Vehicle navigating to motor-config stays on motor-config (got: "${hashAfterNav}")`
        );

        // ==========================================================
        // [4] Rosbag visible for all entity types
        // ==========================================================
        console.log("\n[4] Rosbag visible for all entity types");

        // Check arm
        await navigateToHash(page, "#/entity/arm1/status");
        const armTabsRosbag = await getTabLabels(page);
        assert(
            armTabsRosbag.includes("Rosbag"),
            `Arm entity tab bar contains "Rosbag" (found: ${JSON.stringify(armTabsRosbag)})`
        );

        // Check vehicle
        await navigateToHash(page, "#/entity/vehicle1/status");
        const vehicleTabsRosbag = await getTabLabels(page);
        assert(
            vehicleTabsRosbag.includes("Rosbag"),
            `Vehicle entity tab bar contains "Rosbag" (found: ${JSON.stringify(vehicleTabsRosbag)})`
        );

        // ==========================================================
        // [5] Arm entity has all expected tabs
        // ==========================================================
        console.log("\n[5] Arm entity has all expected tabs");

        await navigateToHash(page, "#/entity/arm1/status");
        const allArmTabs = await getTabLabels(page);

        // Arm should have: Status, Topics, Services, Parameters, Nodes,
        //                  Logs, Motor Config, Rosbag
        const expectedArmTabs = [
            "Motor Config",
            "Rosbag",
            "Topics",
            "Services",
            "Parameters",
            "Nodes",
            "Logs",
        ];
        for (const tab of expectedArmTabs) {
            assert(
                allArmTabs.includes(tab),
                `Arm entity has "${tab}" tab (found: ${JSON.stringify(allArmTabs)})`
            );
        }

        // Status tab — may appear as "Status & Health" or "Status / Health"
        const hasStatusTab = allArmTabs.some(
            (t) => t.includes("Status") && t.includes("Health")
        );
        assert(
            hasStatusTab,
            `Arm entity has "Status & Health" tab (found: ${JSON.stringify(allArmTabs)})`
        );

        // ==========================================================
        // [6] Vehicle entity has all expected tabs (including Motor Config)
        // ==========================================================
        console.log("\n[6] Vehicle entity has all expected tabs");

        await navigateToHash(page, "#/entity/vehicle1/status");
        const allVehicleTabs = await getTabLabels(page);

        // Vehicle should have same tabs as arm now (Motor Config for all)
        const expectedVehicleTabs = [
            "Motor Config",
            "Rosbag",
            "Topics",
            "Services",
            "Parameters",
            "Nodes",
            "Logs",
        ];
        for (const tab of expectedVehicleTabs) {
            assert(
                allVehicleTabs.includes(tab),
                `Vehicle entity has "${tab}" tab (found: ${JSON.stringify(allVehicleTabs)})`
            );
        }

        // ==========================================================
        // [7] Tab click navigates correctly
        // ==========================================================
        console.log("\n[7] Tab click navigation");

        await navigateToHash(page, "#/entity/arm1/status");

        // Click Rosbag tab
        const rosbagClicked = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return false;
            const buttons = section.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Rosbag") {
                    btn.click();
                    return true;
                }
            }
            return false;
        });
        assert(rosbagClicked, "Rosbag tab button was clicked");

        await page.waitForTimeout(1000);
        let hash = await getHash(page);
        assert(
            hash.includes("/entity/arm1/rosbag"),
            `Hash changed to rosbag route after tab click (got: "${hash}")`
        );

        // Click Motor Config tab
        const motorConfigClicked = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return false;
            const buttons = section.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Motor Config") {
                    btn.click();
                    return true;
                }
            }
            return false;
        });
        assert(motorConfigClicked, "Motor Config tab button was clicked");

        await page.waitForTimeout(1000);
        hash = await getHash(page);
        assert(
            hash.includes("/entity/arm1/motor-config"),
            `Hash changed to motor-config route after tab click (got: "${hash}")`
        );

        // ==========================================================
        // [8] No JS errors
        // ==========================================================
        console.log("\n[8] No JS console errors");

        const relevantErrors = consoleErrors.filter(
            (e) =>
                !e.includes("WebSocket") &&
                !e.includes("ws://") &&
                !e.includes("wss://") &&
                !e.includes("ERR_CONNECTION_REFUSED") &&
                !e.includes("net::ERR_FAILED") &&
                !e.includes("404") &&
                !e.includes("Failed to fetch") &&
                !e.includes("rosbag")
        );
        assert(
            relevantErrors.length === 0,
            "No relevant JS console errors during tab visibility tests" +
                (relevantErrors.length > 0
                    ? ` (got ${relevantErrors.length}: ${relevantErrors.slice(0, 3).join("; ")})`
                    : "")
        );

        const relevantPageErrors = pageErrors.filter(
            (e) =>
                !e.includes("WebSocket") &&
                !e.includes("ERR_CONNECTION_REFUSED") &&
                !e.includes("404") &&
                !e.includes("fetch")
        );
        assert(
            relevantPageErrors.length === 0,
            "No uncaught page errors during tab visibility tests" +
                (relevantPageErrors.length > 0
                    ? ` (got ${relevantPageErrors.length}: ${relevantPageErrors.slice(0, 3).join("; ")})`
                    : "")
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
        `Results: ${passed} passed, ${failed} failed, ` +
            `${skipped} skipped (${total} total)`
    );
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    console.log();
    process.exit(failed > 0 ? 1 : 0);
})();
