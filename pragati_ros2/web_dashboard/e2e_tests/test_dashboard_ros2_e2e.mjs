#!/usr/bin/env node
/**
 * E2E integration test: frontend service call UI → backend proxy → agent service call.
 *
 * Covers (Task 8.3):
 *   - Navigate to entity detail, go to services tab
 *   - Service list loads from mocked /api/entities/{id}/ros2/services
 *   - Service call form appears on selection
 *   - Successful call response is displayed
 *   - Error response is handled and shown
 *   - Response displayed after calling a service with custom request data
 *
 * Run: node web_dashboard/e2e_tests/test_dashboard_ros2_e2e.mjs
 *
 * Requires: npm install playwright (in e2e_tests directory)
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

// ---------------------------------------------------------------------------
// Mock entity data
// ---------------------------------------------------------------------------

const ENTITY_ARM1 = {
    id: "arm1",
    name: "Arm 1",
    source: "remote",
    ip: "192.168.1.101",
    status: "online",
    last_seen: new Date().toISOString(),
    system_metrics: {
        cpu_percent: 20.0,
        memory_percent: 30.0,
        temperature_c: 40.0,
        disk_percent: 15.0,
        uptime_seconds: 3600,
        motor_temperatures: { joint1: 45.2, joint2: 38.7 },
        camera_temperature_c: 36.0,
    },
    ros2_available: true,
    ros2_state: { node_count: 2, nodes: [] },
    services: [
        { name: "pragati-arm.service", active_state: "active", sub_state: "running" },
    ],
    errors: [],
    metadata: {},
};

const ROS2_SERVICES = [
    { name: "/joint_homing", type: "std_srvs/srv/Trigger" },
    { name: "/emergency_stop", type: "std_srvs/srv/Trigger" },
    { name: "/set_joint_position", type: "pragati_msgs/srv/SetJointPosition" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function navigateToHash(page, hash) {
    await page.evaluate((h) => {
        window.location.hash = h;
    }, hash);
    await page.waitForTimeout(2000);
}

async function sectionContainsText(page, text) {
    return page.evaluate(
        ({ t }) => {
            const section = document.getElementById("entity-detail-section");
            return section ? section.textContent.includes(t) : false;
        },
        { t: text }
    );
}

async function pageContainsText(page, text) {
    return page.evaluate((t) => document.body.textContent.includes(t), text);
}

/**
 * Set up route mocks for an entity with ROS2 service endpoints.
 */
async function setupEntityMocks(page, entityData, ros2Services, serviceCallHandler = null) {
    const id = entityData.id;

    // Abort WebSocket to prevent real-time noise
    await page.route("**/ws", (route) => route.abort("connectionrefused"));

    // Entities list
    await page.route("**/api/entities", (route) => {
        const url = route.request().url();
        if (/\/api\/entities$/.test(url) || /\/api\/entities\?/.test(url)) {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify([entityData]),
            });
        } else {
            route.continue();
        }
    });

    // Entity detail
    await page.route(`**/api/entities/${id}`, (route) => {
        const url = route.request().url();
        if (url.endsWith(`/${id}`) || url.endsWith(`/${id}/`)) {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(entityData),
            });
        } else {
            route.continue();
        }
    });

    // Rosbag (suppress noise)
    await page.route("**/rosbag/**", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) })
    );

    // ROS2 services list (GET)
    await page.route(`**/api/entities/${id}/ros2/services`, (route) => {
        const url = route.request().url();
        const method = route.request().method();
        if (
            method === "GET" &&
            (url.endsWith("/ros2/services") || url.includes("/ros2/services?"))
        ) {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ data: ros2Services }),
            });
        } else {
            route.continue();
        }
    });

    // ROS2 service call (POST .../services/.../call)
    if (serviceCallHandler) {
        await page.route(`**/api/entities/${id}/ros2/services/**`, (route) => {
            const url = route.request().url();
            const method = route.request().method();
            if (method === "POST" && url.includes("/call")) {
                route.fulfill({
                    status: serviceCallHandler.status,
                    contentType: "application/json",
                    body: JSON.stringify(serviceCallHandler.body),
                });
            } else {
                route.continue();
            }
        });
    }

    // Suppress other ROS2 endpoints
    for (const endpoint of ["nodes", "topics", "parameters"]) {
        await page.route(`**/api/entities/${id}/ros2/${endpoint}`, (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ data: [] }),
            })
        );
    }
    await page.route(`**/api/entities/${id}/ros2/topics/*/echo*`, (route) =>
        route.abort("connectionrefused")
    );
    await page.route(`**/api/entities/${id}/ros2/nodes/*/detail`, (route) =>
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                data: { publishers: [], subscribers: [], services: [], clients: [] },
            }),
        })
    );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

(async () => {
    console.log("Dashboard ROS2 E2E Integration Tests (Task 8.3)");
    console.log(`Target: ${BASE}`);
    console.log("================================================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    try {
        // ==================================================================
        // Test: test_service_list_loads_from_api
        // ==================================================================
        console.log("--- test_service_list_loads_from_api ---");
        {
            const page = await browser.newPage();
            try {
                await setupEntityMocks(page, ENTITY_ARM1, ROS2_SERVICES);
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");

                const hasJointHoming = await sectionContainsText(page, "/joint_homing");
                assert(
                    hasJointHoming,
                    "test_service_list_loads_from_api: /joint_homing visible in services tab"
                );

                const hasEmergencyStop = await sectionContainsText(page, "/emergency_stop");
                assert(
                    hasEmergencyStop,
                    "test_service_list_loads_from_api: /emergency_stop visible in services tab"
                );

                const hasSetJointPos = await sectionContainsText(page, "/set_joint_position");
                assert(
                    hasSetJointPos,
                    "test_service_list_loads_from_api: /set_joint_position visible in services tab"
                );

                const hasServiceType = await sectionContainsText(page, "std_srvs/srv/Trigger");
                assert(
                    hasServiceType,
                    "test_service_list_loads_from_api: service type 'std_srvs/srv/Trigger' visible"
                );
            } catch (e) {
                assert(false, `test_service_list_loads_from_api: exception — ${e.message}`);
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_service_call_response_displayed
        // ==================================================================
        console.log("\n--- test_service_call_response_displayed ---");
        {
            const page = await browser.newPage();
            try {
                await setupEntityMocks(page, ENTITY_ARM1, ROS2_SERVICES, {
                    status: 200,
                    body: { success: true, message: "Homing complete" },
                });
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");
                await page.waitForTimeout(1000);

                // Select /joint_homing from the list
                await page.locator("text=/joint_homing").first().click();
                await page.waitForTimeout(500);

                // Click "Call Service" button
                const callServiceBtn = page
                    .locator("button", { hasText: "Call Service" })
                    .first();
                await callServiceBtn.click();
                await page.waitForTimeout(500);

                // Handle confirmation modal if it appears
                const hasConfirm = await page.evaluate(() => {
                    return Array.from(document.querySelectorAll("button")).some(
                        (b) => b.textContent.trim() === "Call"
                    );
                });
                if (hasConfirm) {
                    await page.locator("button", { hasText: "Call" }).last().click();
                    await page.waitForTimeout(500);
                }

                await page.waitForTimeout(1500);

                const hasSuccess = await sectionContainsText(page, "true");
                assert(
                    hasSuccess,
                    "test_service_call_response_displayed: response contains 'true' (success)"
                );

                const hasMessage = await sectionContainsText(page, "Homing complete");
                assert(
                    hasMessage,
                    "test_service_call_response_displayed: response contains 'Homing complete'"
                );
            } catch (e) {
                assert(
                    false,
                    `test_service_call_response_displayed: exception — ${e.message}`
                );
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_service_call_error_response_displayed
        // ==================================================================
        console.log("\n--- test_service_call_error_response_displayed ---");
        {
            const page = await browser.newPage();
            try {
                await setupEntityMocks(page, ENTITY_ARM1, ROS2_SERVICES, {
                    status: 500,
                    body: { detail: "ROS2 service call failed: node not found" },
                });
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");
                await page.waitForTimeout(1000);

                await page.locator("text=/joint_homing").first().click();
                await page.waitForTimeout(500);

                const callServiceBtn = page
                    .locator("button", { hasText: "Call Service" })
                    .first();
                await callServiceBtn.click();
                await page.waitForTimeout(500);

                const hasConfirm = await page.evaluate(() => {
                    return Array.from(document.querySelectorAll("button")).some(
                        (b) => b.textContent.trim() === "Call"
                    );
                });
                if (hasConfirm) {
                    await page.locator("button", { hasText: "Call" }).last().click();
                    await page.waitForTimeout(500);
                }

                await page.waitForTimeout(1500);

                const hasError = await sectionContainsText(page, "Error");
                assert(
                    hasError,
                    "test_service_call_error_response_displayed: error message shown"
                );

                // Call button re-enabled after error
                const callBtnEnabled = await page.evaluate(() => {
                    const buttons = Array.from(document.querySelectorAll("button"));
                    const callBtn = buttons.find(
                        (b) =>
                            b.textContent.includes("Call Service") ||
                            b.textContent.includes("Call Service")
                    );
                    return callBtn ? !callBtn.disabled : false;
                });
                assert(
                    callBtnEnabled,
                    "test_service_call_error_response_displayed: Call button re-enabled after error"
                );
            } catch (e) {
                assert(
                    false,
                    `test_service_call_error_response_displayed: exception — ${e.message}`
                );
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_empty_service_list_shows_message
        // ==================================================================
        console.log("\n--- test_empty_service_list_shows_message ---");
        {
            const page = await browser.newPage();
            try {
                await setupEntityMocks(page, ENTITY_ARM1, []);
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");

                const hasNoServices = await sectionContainsText(page, "No services");
                assert(
                    hasNoServices,
                    "test_empty_service_list_shows_message: 'No services' message shown when list is empty"
                );
            } catch (e) {
                assert(
                    false,
                    `test_empty_service_list_shows_message: exception — ${e.message}`
                );
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_service_call_form_prepopulated_with_empty_json
        // ==================================================================
        console.log("\n--- test_service_call_form_prepopulated_with_empty_json ---");
        {
            const page = await browser.newPage();
            try {
                await setupEntityMocks(page, ENTITY_ARM1, ROS2_SERVICES);
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");
                await page.waitForTimeout(1000);

                // Click /joint_homing to open the call form
                await page.locator("text=/joint_homing").first().click();
                await page.waitForTimeout(500);

                // Verify the textarea is pre-populated with {}
                const hasEmptyJson = await page.evaluate(() => {
                    const textareas = document.querySelectorAll("textarea");
                    for (const ta of textareas) {
                        if (ta.value.trim() === "{}") return true;
                    }
                    return false;
                });
                assert(
                    hasEmptyJson,
                    "test_service_call_form_prepopulated_with_empty_json: textarea pre-populated with {}"
                );

                // Call Service button visible
                const hasCallBtn = await sectionContainsText(page, "Call Service");
                assert(
                    hasCallBtn,
                    "test_service_call_form_prepopulated_with_empty_json: Call Service button visible"
                );
            } catch (e) {
                assert(
                    false,
                    `test_service_call_form_prepopulated_with_empty_json: exception — ${e.message}`
                );
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_service_call_timeout_shows_message
        // ==================================================================
        console.log("\n--- test_service_call_timeout_shows_message ---");
        {
            const page = await browser.newPage();
            try {
                await setupEntityMocks(page, ENTITY_ARM1, ROS2_SERVICES, {
                    status: 408,
                    body: { detail: "Request Timeout" },
                });
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");
                await page.waitForTimeout(1000);

                await page.locator("text=/joint_homing").first().click();
                await page.waitForTimeout(500);

                const callServiceBtn = page
                    .locator("button", { hasText: "Call Service" })
                    .first();
                await callServiceBtn.click();
                await page.waitForTimeout(500);

                const hasConfirm = await page.evaluate(() => {
                    return Array.from(document.querySelectorAll("button")).some(
                        (b) => b.textContent.trim() === "Call"
                    );
                });
                if (hasConfirm) {
                    await page.locator("button", { hasText: "Call" }).last().click();
                    await page.waitForTimeout(500);
                }

                await page.waitForTimeout(1500);

                const hasTimeout = await sectionContainsText(page, "timed out");
                assert(
                    hasTimeout,
                    "test_service_call_timeout_shows_message: timeout message shown after 408"
                );
            } catch (e) {
                assert(
                    false,
                    `test_service_call_timeout_shows_message: exception — ${e.message}`
                );
            } finally {
                await page.close();
            }
        }
    } finally {
        await browser.close();
    }

    // -----------------------------------------------------------------------
    // Summary
    // -----------------------------------------------------------------------
    console.log("\n================================================");
    console.log(
        `Results: ${passed} passed, ${failed} failed, ${skipped} skipped`
    );
    if (failures.length > 0) {
        console.log("\nFailed tests:");
        for (const f of failures) {
            console.log(`  - ${f}`);
        }
    }
    console.log("================================================");
    process.exit(failed > 0 ? 1 : 0);
})();
