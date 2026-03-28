#!/usr/bin/env node
/**
 * E2E tests for ServicesSubTab service call UI (Tasks 7.1+7.5+7.7).
 *
 * Covers:
 *   - Service list rendered from API data
 *   - Empty state message
 *   - Service call form appearance on selection
 *   - Successful call response display
 *   - Timeout error (408) handling
 *   - Generic error response handling
 *   - Response history accumulation (last 10)
 *   - History cleared on entity switch
 *
 * Run: node web_dashboard/e2e_tests/test_service_call_ui_e2e.mjs
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
    },
    ros2_available: true,
    ros2_state: { node_count: 1, nodes: [] },
    services: [{ name: "pragati-arm.service", active_state: "active", sub_state: "running" }],
    errors: [],
    metadata: {},
};

const ENTITY_ARM2 = {
    id: "arm2",
    name: "Arm 2",
    source: "remote",
    ip: "192.168.1.102",
    status: "online",
    last_seen: new Date().toISOString(),
    system_metrics: {
        cpu_percent: 15.0,
        memory_percent: 25.0,
        temperature_c: 38.0,
        disk_percent: 12.0,
        uptime_seconds: 1800,
    },
    ros2_available: true,
    ros2_state: { node_count: 1, nodes: [] },
    services: [{ name: "pragati-arm.service", active_state: "active", sub_state: "running" }],
    errors: [],
    metadata: {},
};

const ROS2_SERVICES = [
    { name: "/joint_homing", type: "std_srvs/srv/Trigger" },
    { name: "/emergency_stop", type: "std_srvs/srv/Trigger" },
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

async function pageContainsText(page, text) {
    return page.evaluate((t) => document.body.textContent.includes(t), text);
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

/**
 * Set up common route mocks for an entity.
 * @param {import('playwright').Page} page
 * @param {object} entityData - entity JSON to return from /api/entities/{id}
 * @param {Array} ros2Services - services array to return from /ros2/services
 * @param {object|null} serviceCallHandler - optional { status, body } override for POST call
 */
async function setupEntityMocks(page, entityData, ros2Services, serviceCallHandler = null) {
    const id = entityData.id;

    // Abort WebSocket so no real-time noise
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

    // ROS2 services list
    await page.route(`**/api/entities/${id}/ros2/services`, (route) => {
        const url = route.request().url();
        const method = route.request().method();

        // GET /ros2/services → return list
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
            body: JSON.stringify({ data: { publishers: [], subscribers: [], services: [], clients: [] } }),
        })
    );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

(async () => {
    console.log("Service Call UI E2E Tests (Tasks 7.1+7.5+7.7)");
    console.log(`Target: ${BASE}`);
    console.log("========================================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    try {
        // ==================================================================
        // Test: test_services_listed_for_entity
        // ==================================================================
        console.log("--- test_services_listed_for_entity ---");
        {
            const page = await browser.newPage();
            const consoleErrors = [];
            page.on("console", (msg) => {
                if (msg.type() === "error") consoleErrors.push(msg.text());
            });

            try {
                await setupEntityMocks(page, ENTITY_ARM1, ROS2_SERVICES);
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");

                const hasJointHoming = await sectionContainsText(page, "/joint_homing");
                assert(hasJointHoming, "test_services_listed_for_entity: /joint_homing visible");

                const hasEmergencyStop = await sectionContainsText(page, "/emergency_stop");
                assert(hasEmergencyStop, "test_services_listed_for_entity: /emergency_stop visible");

                const hasType = await sectionContainsText(page, "std_srvs/srv/Trigger");
                assert(hasType, "test_services_listed_for_entity: service type visible");
            } catch (e) {
                assert(false, `test_services_listed_for_entity: exception — ${e.message}`);
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_no_services_shows_message
        // ==================================================================
        console.log("\n--- test_no_services_shows_message ---");
        {
            const page = await browser.newPage();
            try {
                await setupEntityMocks(page, ENTITY_ARM1, []);
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");

                const hasNoServices = await sectionContainsText(page, "No services");
                assert(hasNoServices, "test_no_services_shows_message: 'No services' message shown");
            } catch (e) {
                assert(false, `test_no_services_shows_message: exception — ${e.message}`);
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_service_call_form_shown_on_select
        // ==================================================================
        console.log("\n--- test_service_call_form_shown_on_select ---");
        {
            const page = await browser.newPage();
            try {
                await setupEntityMocks(page, ENTITY_ARM1, ROS2_SERVICES);
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");

                // Wait for the service list to load and click /joint_homing row
                await page.waitForTimeout(1000);

                // Click the Call button in the /joint_homing row
                const callBtn = page.locator("text=/joint_homing").first();
                await callBtn.click();
                await page.waitForTimeout(500);

                // Verify call form with textarea pre-populated as {}
                const hasTextarea = await page.evaluate(() => {
                    const textareas = document.querySelectorAll("textarea");
                    for (const ta of textareas) {
                        if (ta.value.trim() === "{}") return true;
                    }
                    return false;
                });
                assert(hasTextarea, "test_service_call_form_shown_on_select: textarea pre-populated with {}");

                // Verify Call Service button is present
                const hasCallServiceBtn = await sectionContainsText(page, "Call Service");
                assert(hasCallServiceBtn, "test_service_call_form_shown_on_select: Call Service button visible");

                // Verify service name shown as header in call panel
                const hasServiceHeader = await sectionContainsText(page, "/joint_homing");
                assert(hasServiceHeader, "test_service_call_form_shown_on_select: service name shown in call form");
            } catch (e) {
                assert(false, `test_service_call_form_shown_on_select: exception — ${e.message}`);
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_service_call_success_shows_response
        // ==================================================================
        console.log("\n--- test_service_call_success_shows_response ---");
        {
            const page = await browser.newPage();
            try {
                await setupEntityMocks(page, ENTITY_ARM1, ROS2_SERVICES, {
                    status: 200,
                    body: { success: true, message: "Done" },
                });
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");
                await page.waitForTimeout(1000);

                // Select /joint_homing
                await page.locator("text=/joint_homing").first().click();
                await page.waitForTimeout(500);

                // Click "Call Service" (may have confirmation modal)
                const callServiceBtn = page.locator("button", { hasText: "Call Service" }).first();
                await callServiceBtn.click();
                await page.waitForTimeout(500);

                // Handle potential confirmation modal
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
                assert(hasSuccess, "test_service_call_success_shows_response: response contains 'true'");

                const hasDone = await sectionContainsText(page, "Done");
                assert(hasDone, "test_service_call_success_shows_response: response contains 'Done'");
            } catch (e) {
                assert(false, `test_service_call_success_shows_response: exception — ${e.message}`);
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

                const callServiceBtn = page.locator("button", { hasText: "Call Service" }).first();
                await callServiceBtn.click();
                await page.waitForTimeout(500);

                // Handle confirmation modal if present
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
                assert(hasTimeout, "test_service_call_timeout_shows_message: timeout message shown");

                // Call button re-enabled (not disabled)
                const callBtnEnabled = await page.evaluate(() => {
                    const buttons = Array.from(document.querySelectorAll("button"));
                    const callBtn = buttons.find(
                        (b) =>
                            b.textContent.includes("Call Service") ||
                            b.textContent.includes("⚠️ Call Service")
                    );
                    return callBtn ? !callBtn.disabled : false;
                });
                assert(callBtnEnabled, "test_service_call_timeout_shows_message: Call button re-enabled after timeout");
            } catch (e) {
                assert(false, `test_service_call_timeout_shows_message: exception — ${e.message}`);
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_service_call_error_shown_and_retry_enabled
        // ==================================================================
        console.log("\n--- test_service_call_error_shown_and_retry_enabled ---");
        {
            const page = await browser.newPage();
            try {
                await setupEntityMocks(page, ENTITY_ARM1, ROS2_SERVICES, {
                    status: 500,
                    body: { detail: "Internal Server Error" },
                });
                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");
                await page.waitForTimeout(1000);

                await page.locator("text=/joint_homing").first().click();
                await page.waitForTimeout(500);

                const callServiceBtn = page.locator("button", { hasText: "Call Service" }).first();
                await callServiceBtn.click();
                await page.waitForTimeout(500);

                // Handle confirmation modal if present
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
                assert(hasError, "test_service_call_error_shown_and_retry_enabled: error message shown");

                const callBtnEnabled = await page.evaluate(() => {
                    const buttons = Array.from(document.querySelectorAll("button"));
                    const callBtn = buttons.find(
                        (b) =>
                            b.textContent.includes("Call Service") ||
                            b.textContent.includes("⚠️ Call Service")
                    );
                    return callBtn ? !callBtn.disabled : false;
                });
                assert(callBtnEnabled, "test_service_call_error_shown_and_retry_enabled: Call button re-enabled after error");
            } catch (e) {
                assert(false, `test_service_call_error_shown_and_retry_enabled: exception — ${e.message}`);
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_response_history_accumulates
        // ==================================================================
        console.log("\n--- test_response_history_accumulates ---");
        {
            const page = await browser.newPage();
            let callCount = 0;
            try {
                await setupEntityMocks(page, ENTITY_ARM1, ROS2_SERVICES);

                // Override service call to return different responses each time
                await page.route("**/api/entities/arm1/ros2/services/**", (route) => {
                    const url = route.request().url();
                    const method = route.request().method();
                    if (method === "POST" && url.includes("/call")) {
                        callCount++;
                        route.fulfill({
                            status: 200,
                            contentType: "application/json",
                            body: JSON.stringify({ success: true, call_number: callCount }),
                        });
                    } else {
                        route.continue();
                    }
                });

                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");
                await page.waitForTimeout(1000);

                // Make first call
                await page.locator("text=/joint_homing").first().click();
                await page.waitForTimeout(500);

                async function doServiceCall(page) {
                    const callServiceBtn = page.locator("button", { hasText: "Call Service" }).first();
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
                    await page.waitForTimeout(1000);
                }

                await doServiceCall(page);
                await doServiceCall(page);

                // History panel should be visible with at least 2 entries
                const historyCount = await page.evaluate(() => {
                    const section = document.getElementById("entity-detail-section");
                    if (!section) return 0;
                    const text = section.textContent;
                    return (text.match(/Call History/g) || []).length;
                });
                assert(historyCount >= 1, "test_response_history_accumulates: Call History panel visible");

                // Check that at least 2 history entries shown (by looking for time pattern)
                const historyEntries = await page.evaluate(() => {
                    const section = document.getElementById("entity-detail-section");
                    if (!section) return 0;
                    // Count elements that show a time (HH:MM:SS pattern)
                    const allText = section.textContent;
                    const timeMatches = allText.match(/\d{2}:\d{2}:\d{2}/g);
                    return timeMatches ? timeMatches.length : 0;
                });
                assert(historyEntries >= 2, "test_response_history_accumulates: at least 2 history entries shown");
            } catch (e) {
                assert(false, `test_response_history_accumulates: exception — ${e.message}`);
            } finally {
                await page.close();
            }
        }

        // ==================================================================
        // Test: test_response_history_cleared_on_entity_switch
        // ==================================================================
        console.log("\n--- test_response_history_cleared_on_entity_switch ---");
        {
            const page = await browser.newPage();
            try {
                // Set up both entities
                await page.route("**/ws", (route) => route.abort("connectionrefused"));

                await page.route("**/api/entities", (route) => {
                    const url = route.request().url();
                    if (/\/api\/entities$/.test(url) || /\/api\/entities\?/.test(url)) {
                        route.fulfill({
                            status: 200,
                            contentType: "application/json",
                            body: JSON.stringify([ENTITY_ARM1, ENTITY_ARM2]),
                        });
                    } else {
                        route.continue();
                    }
                });

                await page.route("**/api/entities/arm1", (route) => {
                    const url = route.request().url();
                    if (url.endsWith("/arm1") || url.endsWith("/arm1/")) {
                        route.fulfill({
                            status: 200,
                            contentType: "application/json",
                            body: JSON.stringify(ENTITY_ARM1),
                        });
                    } else {
                        route.continue();
                    }
                });

                await page.route("**/api/entities/arm2", (route) => {
                    const url = route.request().url();
                    if (url.endsWith("/arm2") || url.endsWith("/arm2/")) {
                        route.fulfill({
                            status: 200,
                            contentType: "application/json",
                            body: JSON.stringify(ENTITY_ARM2),
                        });
                    } else {
                        route.continue();
                    }
                });

                await page.route("**/rosbag/**", (route) =>
                    route.fulfill({
                        status: 200,
                        contentType: "application/json",
                        body: JSON.stringify([]),
                    })
                );

                // arm1 services list
                await page.route("**/api/entities/arm1/ros2/services", (route) => {
                    const url = route.request().url();
                    const method = route.request().method();
                    if (
                        method === "GET" &&
                        (url.endsWith("/ros2/services") || url.includes("/ros2/services?"))
                    ) {
                        route.fulfill({
                            status: 200,
                            contentType: "application/json",
                            body: JSON.stringify({ data: ROS2_SERVICES }),
                        });
                    } else {
                        route.continue();
                    }
                });

                // arm2 services list (empty)
                await page.route("**/api/entities/arm2/ros2/services", (route) => {
                    const url = route.request().url();
                    const method = route.request().method();
                    if (
                        method === "GET" &&
                        (url.endsWith("/ros2/services") || url.includes("/ros2/services?"))
                    ) {
                        route.fulfill({
                            status: 200,
                            contentType: "application/json",
                            body: JSON.stringify({ data: [] }),
                        });
                    } else {
                        route.continue();
                    }
                });

                // arm1 service call
                await page.route("**/api/entities/arm1/ros2/services/**", (route) => {
                    const url = route.request().url();
                    const method = route.request().method();
                    if (method === "POST" && url.includes("/call")) {
                        route.fulfill({
                            status: 200,
                            contentType: "application/json",
                            body: JSON.stringify({ success: true, message: "Done" }),
                        });
                    } else {
                        route.continue();
                    }
                });

                // Suppress other ROS2 endpoints for both entities
                for (const id of ["arm1", "arm2"]) {
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

                await page.goto(BASE);
                await page.waitForTimeout(1000);
                await navigateToHash(page, "#/entity/arm1/services");
                await page.waitForTimeout(1000);

                // Make a call on arm1
                await page.locator("text=/joint_homing").first().click();
                await page.waitForTimeout(500);

                const callServiceBtn = page.locator("button", { hasText: "Call Service" }).first();
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
                await page.waitForTimeout(1000);

                // Verify history is present on arm1
                const arm1HasHistory = await sectionContainsText(page, "Call History");
                assert(arm1HasHistory, "test_response_history_cleared_on_entity_switch: history present on arm1");

                // Switch to arm2
                await navigateToHash(page, "#/entity/arm2/services");
                await page.waitForTimeout(1500);

                // History should be gone (arm2 has fresh state)
                const arm2HasHistory = await sectionContainsText(page, "Call History");
                assert(
                    !arm2HasHistory,
                    "test_response_history_cleared_on_entity_switch: history cleared after switching to arm2"
                );
            } catch (e) {
                assert(false, `test_response_history_cleared_on_entity_switch: exception — ${e.message}`);
            } finally {
                await page.close();
            }
        }
    } finally {
        await browser.close();
    }

    // ---------------------------------------------------------------------------
    // Summary
    // ---------------------------------------------------------------------------
    console.log("\n========================================");
    console.log(`Results: ${passed} passed, ${failed} failed, ${skipped} skipped`);
    if (failures.length > 0) {
        console.log("\nFailed tests:");
        for (const f of failures) {
            console.log(`  - ${f}`);
        }
    }
    console.log("========================================");
    process.exit(failed > 0 ? 1 : 0);
})();
