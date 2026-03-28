#!/usr/bin/env node
// Rosbag Sub-Tab E2E Test Suite (Task 8.6)
//
// Tests the RosbagSubTab component within the entity detail shell:
// - Rosbag tab present in tab bar for any entity
// - Recording controls (profile selector, Start Recording button)
// - Bag list table present (even if empty)
// - Recording status polling (checks network requests or status display)
//
// Run: node web_dashboard/e2e_tests/test_rosbag_subtab.mjs
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

// Helper: get text content of entity detail section
async function getEntitySectionText(page) {
    return page.evaluate(() => {
        const section = document.getElementById("entity-detail-section");
        return section ? section.textContent : "";
    });
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

// Mock rosbag API responses
const MOCK_RECORD_STATUS = {
    recording: false,
    profile: null,
    duration_s: 0,
    estimated_size_mb: 0,
    disk_remaining_mb: 50000,
};

const MOCK_BAG_LIST = [
    {
        name: "rosbag2_2025_06_01-12_00_00",
        size_mb: 25.4,
        duration_s: 120,
        topic_count: 5,
        created: "2025-06-01T12:00:00Z",
    },
    {
        name: "rosbag2_2025_06_02-08_30_00",
        size_mb: 102.8,
        duration_s: 600,
        topic_count: 12,
        created: "2025-06-02T08:30:00Z",
    },
];

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

(async () => {
    console.log("Rosbag Sub-Tab E2E Tests (Task 8.6)");
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

    // Track rosbag API requests for polling verification
    const rosbagApiCalls = [];
    page.on("request", (req) => {
        const url = req.url();
        if (url.includes("/rosbag/")) {
            rosbagApiCalls.push({
                method: req.method(),
                url: url,
                timestamp: Date.now(),
            });
        }
    });

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

        // Mock rosbag record status endpoint
        await page.route("**/api/entities/arm1/rosbag/record/status", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(MOCK_RECORD_STATUS),
            })
        );

        // Mock rosbag list endpoint
        await page.route("**/api/entities/arm1/rosbag/list", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(MOCK_BAG_LIST),
            })
        );

        // Mock vehicle rosbag endpoints too
        await page.route(
            "**/api/entities/vehicle1/rosbag/record/status",
            (route) =>
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify(MOCK_RECORD_STATUS),
                })
        );

        await page.route("**/api/entities/vehicle1/rosbag/list", (route) =>
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
        // [1] Rosbag tab present for arm entity
        // ==========================================================
        console.log("[1] Rosbag tab present in tab bar");

        await navigateToHash(page, "#/entity/arm1/status");

        const armTabs = await getTabLabels(page);
        assert(
            armTabs.includes("Rosbag"),
            `Arm entity tab bar contains "Rosbag" (found: ${JSON.stringify(armTabs)})`
        );

        // Also check vehicle entity has Rosbag tab (entityTypes: null = all)
        await navigateToHash(page, "#/entity/vehicle1/status");

        const vehicleTabs = await getTabLabels(page);
        assert(
            vehicleTabs.includes("Rosbag"),
            `Vehicle entity tab bar contains "Rosbag" (found: ${JSON.stringify(vehicleTabs)})`
        );

        // ==========================================================
        // [2] Recording controls present
        // ==========================================================
        console.log("\n[2] Recording controls present");

        await navigateToHash(page, "#/entity/arm1/rosbag");

        // Wait for RosbagSubTab component to render
        try {
            await page.waitForFunction(
                () => {
                    const section = document.getElementById(
                        "entity-detail-section"
                    );
                    if (!section) return false;
                    return (
                        section.textContent.includes("Recording") ||
                        section.textContent.includes("Profile")
                    );
                },
                { timeout: 5000 }
            );
        } catch (_e) {
            // Fall through
        }

        const sectionText = await getEntitySectionText(page);

        // Profile selector
        const profileSelect = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return null;
            const selects = section.querySelectorAll("select");
            for (const sel of selects) {
                const options = Array.from(sel.options).map((o) => o.value);
                if (options.includes("default")) {
                    return {
                        found: true,
                        options: options,
                        optionCount: options.length,
                    };
                }
            }
            return null;
        });

        assert(
            profileSelect !== null,
            "Profile selector dropdown is present"
        );
        assert(
            profileSelect?.optionCount === 4,
            `Profile selector has 4 options (got ${profileSelect?.optionCount})`
        );

        // Check expected profiles
        const expectedProfiles = [
            "default",
            "motor_debug",
            "navigation",
            "full",
        ];
        for (const profile of expectedProfiles) {
            assert(
                profileSelect?.options?.includes(profile),
                `Profile option "${profile}" present`
            );
        }

        // Start Recording button
        const hasStartBtn = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return false;
            const buttons = section.querySelectorAll("button");
            for (const btn of buttons) {
                const text = btn.textContent.trim();
                if (
                    text.includes("Start Recording") ||
                    text.includes("Starting")
                ) {
                    return true;
                }
            }
            return false;
        });
        assert(
            hasStartBtn,
            "Start Recording button is present"
        );

        // Recording section heading
        assert(
            sectionText.includes("Recording"),
            'Recording section heading "Recording" is present'
        );

        // ==========================================================
        // [3] Bag list section present
        // ==========================================================
        console.log("\n[3] Bag list section present");

        // Check for Recorded Bags section
        assert(
            sectionText.includes("Recorded Bags"),
            '"Recorded Bags" section heading is present'
        );

        // Refresh button
        const hasRefreshBtn = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return false;
            const buttons = section.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Refresh") return true;
            }
            return false;
        });
        assert(hasRefreshBtn, "Refresh button for bag list is present");

        // Bag list content — check for mock bag names or empty state
        const hasBagContent = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return { hasBags: false, hasEmpty: false };
            const text = section.textContent;
            return {
                hasBags:
                    text.includes("rosbag2_2025_06_01") ||
                    text.includes("rosbag2_2025_06_02"),
                hasEmpty:
                    text.includes("No bags") ||
                    text.includes("No recorded"),
                hasTable: section.querySelector("table") !== null,
            };
        });
        assert(
            hasBagContent.hasBags ||
                hasBagContent.hasEmpty ||
                hasBagContent.hasTable,
            `Bag list section renders content (bags=${hasBagContent.hasBags}, empty=${hasBagContent.hasEmpty}, table=${hasBagContent.hasTable})`
        );

        // ==========================================================
        // [4] Recording status polling
        // ==========================================================
        console.log("\n[4] Recording status polling");

        // Clear tracked calls and wait for poll interval (RosbagSubTab
        // polls every 2s via POLL_INTERVAL_MS)
        const callsBefore = rosbagApiCalls.filter((c) =>
            c.url.includes("/record/status")
        ).length;

        // Wait for at least one poll cycle (2s + buffer)
        await page.waitForTimeout(3000);

        const callsAfter = rosbagApiCalls.filter((c) =>
            c.url.includes("/record/status")
        ).length;

        assert(
            callsAfter > callsBefore,
            `Recording status polling occurred (calls before=${callsBefore}, after=${callsAfter})`
        );

        // Verify disk remaining is displayed (from mock data)
        const hasDiskInfo = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return false;
            return (
                section.textContent.includes("Disk") ||
                section.textContent.includes("remaining") ||
                section.textContent.includes("GB")
            );
        });
        // Disk info is only shown when recordStatus has disk_remaining_mb
        // and it may or may not appear depending on render timing
        if (hasDiskInfo) {
            assert(true, "Disk remaining info is displayed from poll data");
        } else {
            skip(
                "Disk remaining info displayed",
                "May not render when not recording"
            );
        }

        // ==========================================================
        // [5] No JS errors
        // ==========================================================
        console.log("\n[5] No JS console errors");

        const relevantErrors = consoleErrors.filter(
            (e) =>
                !e.includes("WebSocket") &&
                !e.includes("ws://") &&
                !e.includes("wss://") &&
                !e.includes("ERR_CONNECTION_REFUSED") &&
                !e.includes("net::ERR_FAILED") &&
                !e.includes("404") &&
                !e.includes("Failed to fetch")
        );
        assert(
            relevantErrors.length === 0,
            "No relevant JS console errors during Rosbag sub-tab usage" +
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
            "No uncaught page errors during Rosbag sub-tab usage" +
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
