#!/usr/bin/env node
// Temperature Display E2E Tests — Tasks 3.1–3.6
//
// Tests that entity health cards display motor and camera temperatures
// from system_metrics, handle null values gracefully, and show camera
// temperature only for arm entities.
//
// Run: node web_dashboard/e2e_tests/test_temperature_display_e2e.mjs
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

// Helper: navigate to entity detail via hash change
async function navigateToEntity(page, entityId) {
    await page.evaluate((id) => {
        window.location.hash = `#/entity/${id}/status`;
    }, entityId);
    await page.waitForTimeout(2000);
}

// ---------------------------------------------------------------------------
// Mock entity data
// ---------------------------------------------------------------------------

const NOW_ISO = new Date().toISOString();

/** Arm entity with motor temperatures AND camera temperature */
const ARM_WITH_ALL_TEMPS = {
    id: "arm-temp-test",
    name: "arm-temp-test",
    entity_type: "arm",
    status: "online",
    source: "config",
    ip: "192.168.1.20",
    last_seen: NOW_ISO,
    ros2_available: true,
    system_metrics: {
        cpu_percent: 30,
        memory_percent: 40,
        temperature_c: 45,
        motor_temperatures: {
            joint1: 45.2,
            joint2: 50.1,
            joint3: 38.7,
        },
        camera_temperature_c: 52.3,
    },
    ros2_state: { node_count: 4 },
    health: {
        network: "reachable",
        agent: "alive",
        mqtt: "active",
        ros2: "healthy",
        composite: "online",
        diagnostic: "All systems operational",
    },
    services: [],
    errors: [],
};

/** Vehicle entity with motor temperatures but NO camera temperature (null) */
const VEHICLE_NO_CAMERA_TEMP = {
    id: "vehicle-temp-test",
    name: "vehicle-temp-test",
    entity_type: "vehicle",
    status: "online",
    source: "config",
    ip: "192.168.1.21",
    last_seen: NOW_ISO,
    ros2_available: true,
    system_metrics: {
        cpu_percent: 20,
        memory_percent: 30,
        temperature_c: 38,
        motor_temperatures: {
            left_wheel: 38.0,
            right_wheel: 41.2,
        },
        camera_temperature_c: null,
    },
    ros2_state: { node_count: 2 },
    health: {
        network: "reachable",
        agent: "alive",
        mqtt: "active",
        ros2: "healthy",
        composite: "online",
        diagnostic: "All systems operational",
    },
    services: [],
    errors: [],
};

/** Entity with all temperature fields null */
const ENTITY_NULL_TEMPS = {
    id: "arm-null-temps",
    name: "arm-null-temps",
    entity_type: "arm",
    status: "online",
    source: "config",
    ip: "192.168.1.22",
    last_seen: NOW_ISO,
    ros2_available: true,
    system_metrics: {
        cpu_percent: 25,
        memory_percent: 35,
        temperature_c: null,
        motor_temperatures: null,
        camera_temperature_c: null,
    },
    ros2_state: { node_count: 3 },
    health: {
        network: "reachable",
        agent: "alive",
        mqtt: "active",
        ros2: "healthy",
        composite: "online",
        diagnostic: "All systems operational",
    },
    services: [],
    errors: [],
};

// ---------------------------------------------------------------------------
// Test 1: Arm entity shows motor and camera temperatures
// ---------------------------------------------------------------------------

async function test_arm_entity_shows_motor_and_camera_temperatures(browser) {
    const testName = "test_arm_entity_shows_motor_and_camera_temperatures";
    console.log(`\n[${testName}]`);

    const context = await browser.newContext();
    const page = await context.newPage();

    try {
        // Mock /api/entities to return our arm entity
        await page.route("**/api/entities", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify([ARM_WITH_ALL_TEMPS]),
            });
        });

        // Mock individual entity endpoint
        await page.route(`**/api/entities/arm-temp-test`, (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(ARM_WITH_ALL_TEMPS),
            });
        });

        // Mock system stats endpoint (no fresh stats — use entity system_metrics)
        await page.route(`**/api/entities/arm-temp-test/system/stats`, (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ data: null }),
            });
        });

        await page.route(`**/api/entities/arm-temp-test/system/processes`, (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ data: [] }),
            });
        });

        await page.route("**/api/safety/status", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ estop_active: false, can_connected: false, active_arms: 0, last_estop: null }),
            });
        });

        await page.goto(BASE);
        await page.waitForTimeout(1000);
        await navigateToEntity(page, "arm-temp-test");

        const bodyText = await page.evaluate(() => document.body.innerText);

        // Motor temperatures should be visible in compact format: "J1: 45°C │ J2: 50°C │ J3: 39°C"
        assert(bodyText.includes("J1") || bodyText.includes("45"), "joint1 motor temp visible (J1)");
        assert(bodyText.includes("J2") || bodyText.includes("50"), "joint2 motor temp visible (J2)");
        assert(bodyText.includes("J3") || bodyText.includes("39"), "joint3 motor temp visible (J3)");

        // Camera temperature should be visible (arm entity)
        assert(bodyText.includes("Camera") && bodyText.includes("52.3"), "camera temperature visible for arm");

        // Temperature section heading
        const hasDegree = bodyText.includes("°C") || bodyText.includes("Hardware Temperatures");
        assert(hasDegree, "temperature unit or section heading visible");
    } catch (err) {
        failed++;
        failures.push(testName + ": " + err.message);
        console.log(`  FAIL  ${testName}: ${err.message}`);
    } finally {
        await context.close();
    }
}

// ---------------------------------------------------------------------------
// Test 2: Vehicle entity shows motor temps but NOT camera temperature
// ---------------------------------------------------------------------------

async function test_vehicle_entity_shows_motor_temps_no_camera(browser) {
    const testName = "test_vehicle_entity_shows_motor_temps_no_camera";
    console.log(`\n[${testName}]`);

    const context = await browser.newContext();
    const page = await context.newPage();

    try {
        await page.route("**/api/entities", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify([VEHICLE_NO_CAMERA_TEMP]),
            });
        });

        await page.route(`**/api/entities/vehicle-temp-test`, (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(VEHICLE_NO_CAMERA_TEMP),
            });
        });

        await page.route(`**/api/entities/vehicle-temp-test/system/stats`, (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ data: null }),
            });
        });

        await page.route(`**/api/entities/vehicle-temp-test/system/processes`, (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ data: [] }),
            });
        });

        await page.route("**/api/safety/status", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ estop_active: false, can_connected: false, active_arms: 0, last_estop: null }),
            });
        });

        await page.goto(BASE);
        await page.waitForTimeout(1000);
        await navigateToEntity(page, "vehicle-temp-test");

        const bodyText = await page.evaluate(() => document.body.innerText);

        // Motor temperatures should be visible in compact format
        assert(
            bodyText.includes("left_wheel") || bodyText.includes("38"),
            "left_wheel motor temp visible"
        );
        assert(
            bodyText.includes("right_wheel") || bodyText.includes("41"),
            "right_wheel motor temp visible"
        );

        // Camera row should NOT appear at all for vehicle entities
        // (not just hidden when null — the row itself is absent)
        const hasCameraLabel = /Camera/.test(bodyText.split("Hardware Temperatures")[1] || "");
        assert(!hasCameraLabel, "camera row NOT shown for vehicle entity");
    } catch (err) {
        failed++;
        failures.push(testName + ": " + err.message);
        console.log(`  FAIL  ${testName}: ${err.message}`);
    } finally {
        await context.close();
    }
}

// ---------------------------------------------------------------------------
// Test 3: Null temperature fields show N/A or dash
// ---------------------------------------------------------------------------

async function test_null_temperatures_show_na(browser) {
    const testName = "test_null_temperatures_show_na";
    console.log(`\n[${testName}]`);

    const context = await browser.newContext();
    const page = await context.newPage();

    try {
        await page.route("**/api/entities", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify([ENTITY_NULL_TEMPS]),
            });
        });

        await page.route(`**/api/entities/arm-null-temps`, (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(ENTITY_NULL_TEMPS),
            });
        });

        await page.route(`**/api/entities/arm-null-temps/system/stats`, (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ data: null }),
            });
        });

        await page.route(`**/api/entities/arm-null-temps/system/processes`, (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ data: [] }),
            });
        });

        await page.route("**/api/safety/status", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ estop_active: false, can_connected: false, active_arms: 0, last_estop: null }),
            });
        });

        await page.goto(BASE);
        await page.waitForTimeout(1000);
        await navigateToEntity(page, "arm-null-temps");

        const bodyText = await page.evaluate(() => document.body.innerText);

        // Section should always be visible even with null temps
        assert(bodyText.includes("Hardware Temperatures"), "temperature section visible when all temps null");

        // Motors row should show N/A
        assert(bodyText.includes("N/A"), "N/A shown when motor_temperatures is null");

        // No spurious motor temp values
        const hasSpuriousMotorTemp = /J\d+:\s*\d+°C/.test(bodyText);
        assert(!hasSpuriousMotorTemp, "no spurious motor temp values when motor_temperatures is null");

        // Camera row should show N/A (arm entity), not an actual value
        const hasCameraTempValue = /Camera\s*\n?\s*\d+\.\d+°C/.test(bodyText);
        assert(!hasCameraTempValue, "no camera temperature value shown when camera_temperature_c is null");
    } catch (err) {
        failed++;
        failures.push(testName + ": " + err.message);
        console.log(`  FAIL  ${testName}: ${err.message}`);
    } finally {
        await context.close();
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

(async () => {
    const browser = await chromium.launch({ headless: true });

    try {
        await test_arm_entity_shows_motor_and_camera_temperatures(browser);
        await test_vehicle_entity_shows_motor_temps_no_camera(browser);
        await test_null_temperatures_show_na(browser);
    } finally {
        await browser.close();
    }

    console.log(`\n${"─".repeat(60)}`);
    console.log(`Results: ${passed} passed, ${failed} failed, ${skipped} skipped`);

    if (failures.length > 0) {
        console.log("\nFailed tests:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }

    process.exit(failures.length > 0 ? 1 : 0);
})();
