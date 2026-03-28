#!/usr/bin/env node
// System Stats E2E Test Suite
//
// Tests enhanced system gauges (CPU, memory, temp, disk) with sparklines,
// threshold visualization, disk breakdown, and collapsible process table.
//
// Run: node web_dashboard/e2e_tests/system_stats_e2e.mjs
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

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const ARM1_ENTITY_DATA = {
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
    ros2_state: { node_count: 2, nodes: [] },
    services: [],
    errors: [],
    metadata: {},
};

const MOCK_SYSTEM_STATS = {
    entity_id: "arm1",
    source: "remote",
    data: {
        cpu_percent: 45.2,
        memory_used: 1073741824, // 1 GB
        memory_total: 4294967296, // 4 GB
        disk_used: 5368709120, // 5 GB
        disk_total: 32212254720, // 30 GB
        cpu_temp: 42.5,
    },
};

const MOCK_SYSTEM_PROCESSES = {
    entity_id: "arm1",
    source: "remote",
    data: [
        {
            pid: 1234,
            name: "python3",
            cpu_percent: 25.3,
            memory_mb: 150.5,
            status: "running",
        },
        {
            pid: 5678,
            name: "ros2_node",
            cpu_percent: 15.1,
            memory_mb: 85.2,
            status: "running",
        },
        {
            pid: 9012,
            name: "can_bridge",
            cpu_percent: 8.7,
            memory_mb: 45.0,
            status: "sleeping",
        },
    ],
};

const MOCK_SAFETY_STATUS = {
    estop_active: false,
    can_connected: true,
    active_arms: 1,
    last_estop: null,
};

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

(async () => {
    console.log("System Stats E2E Tests");
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

        // Abort WebSocket connections
        await page.route("**/ws", (route) =>
            route.abort("connectionrefused")
        );

        // Mock system stats endpoint (register BEFORE entity detail)
        await page.route(
            "**/api/entities/arm1/system/stats",
            (route) => {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify(MOCK_SYSTEM_STATS),
                });
            }
        );

        // Mock system processes endpoint
        await page.route(
            "**/api/entities/arm1/system/processes",
            (route) => {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify(MOCK_SYSTEM_PROCESSES),
                });
            }
        );

        // Mock safety status
        await page.route("**/api/safety/status", (route) => {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(MOCK_SAFETY_STATUS),
            });
        });

        // Mock entity list
        await page.route("**/api/entities", (route) => {
            const url = route.request().url();
            if (url.endsWith("/entities") || url.endsWith("/entities/")) {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify([ARM1_ENTITY_DATA]),
                });
            } else {
                route.continue();
            }
        });

        // Mock arm1 entity detail (must not intercept sub-paths)
        await page.route("**/api/entities/arm1", (route) => {
            const url = route.request().url();
            if (url.endsWith("/arm1") || url.endsWith("/arm1/")) {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify(ARM1_ENTITY_DATA),
                });
            } else {
                route.continue();
            }
        });

        // ==========================================================
        // Navigate to entity Status tab
        // ==========================================================
        console.log("[1] Navigate to entity status tab and verify gauges");

        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
        await page.waitForTimeout(1000);

        await navigateToHash(page, "#/entity/arm1/status");

        // Wait for stats to load
        await page.waitForTimeout(3000);

        // ==========================================================
        // [6.1] Enhanced system gauges render
        // ==========================================================

        // 1. Stats grid exists with stat cards
        const statsGridExists = await page.evaluate(() => {
            const grid = document.querySelector(".stats-grid");
            return grid !== null;
        });
        assert(statsGridExists, "Stats grid container (.stats-grid) exists");

        const statCardCount = await page.evaluate(() => {
            const cards = document.querySelectorAll(".stat-card");
            return cards.length;
        });
        assert(
            statCardCount >= 4,
            `At least 4 stat cards rendered (found: ${statCardCount})`
        );

        // 2. Gauge labels
        const sectionText = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            return section ? section.textContent : "";
        });
        assert(
            sectionText.includes("CPU Usage"),
            'Gauge label "CPU Usage" is visible'
        );
        assert(
            sectionText.includes("Memory Usage"),
            'Gauge label "Memory Usage" is visible'
        );
        assert(
            sectionText.includes("Temperature"),
            'Gauge label "Temperature" is visible'
        );
        assert(
            sectionText.includes("Disk Usage"),
            'Gauge label "Disk Usage" is visible'
        );

        // 3. Gauge values from mock data
        assert(
            sectionText.includes("45.2"),
            'CPU value "45.2" from mock stats is displayed'
        );
        assert(
            sectionText.includes("42.5"),
            'Temperature value "42.5" from mock stats is displayed'
        );

        // 4. Threshold bands
        const thresholdBarCount = await page.evaluate(() => {
            const bars = document.querySelectorAll(".threshold-bar");
            return bars.length;
        });
        assert(
            thresholdBarCount >= 4,
            `Threshold bars exist in stat cards (found: ${thresholdBarCount})`
        );

        // 5. Sparkline elements (placeholder or SVG)
        const sparklineElements = await page.evaluate(() => {
            const svgs = document.querySelectorAll(".sparkline-svg");
            const placeholders = document.querySelectorAll(
                ".sparkline-placeholder"
            );
            return { svgs: svgs.length, placeholders: placeholders.length };
        });
        assert(
            sparklineElements.svgs + sparklineElements.placeholders >= 4,
            `Sparkline elements present (SVGs: ${sparklineElements.svgs}, placeholders: ${sparklineElements.placeholders})`
        );

        // 6. Disk breakdown shows GB
        assert(
            sectionText.includes("GB"),
            'Disk breakdown shows "GB" unit'
        );
        assert(
            sectionText.includes("used"),
            'Disk breakdown shows "used" text'
        );

        console.log("\n[2] System Metrics heading");

        assert(
            sectionText.includes("System Metrics"),
            '"System Metrics" heading is visible'
        );

        // ==========================================================
        // [6.2] Process table interaction
        // ==========================================================
        console.log("\n[3] Process table interaction");

        // 1. Toggle visible
        const toggleExists = await page.evaluate(() => {
            const toggle = document.querySelector(".process-table-toggle");
            return toggle !== null;
        });
        assert(toggleExists, "Process table toggle exists");

        // 2. Default collapsed — no table visible
        const tableVisibleBefore = await page.evaluate(() => {
            const table = document.querySelector("table.process-table");
            return table !== null;
        });
        assert(
            !tableVisibleBefore,
            "Process table is collapsed by default (no table element)"
        );

        // 3. Click to expand
        await page.evaluate(() => {
            const toggle = document.querySelector(".process-table-toggle");
            if (toggle) toggle.click();
        });
        await page.waitForTimeout(500);

        const tableVisibleAfter = await page.evaluate(() => {
            const table = document.querySelector("table.process-table");
            return table !== null;
        });
        assert(
            tableVisibleAfter,
            "Process table is visible after clicking toggle"
        );

        // 4. Table columns
        const columnHeaders = await page.evaluate(() => {
            const ths = document.querySelectorAll(
                "table.process-table thead th"
            );
            return Array.from(ths).map((th) => th.textContent.trim());
        });
        assert(
            columnHeaders.includes("PID"),
            `Table has PID column (headers: ${JSON.stringify(columnHeaders)})`
        );
        assert(
            columnHeaders.includes("Name"),
            "Table has Name column"
        );
        assert(
            columnHeaders.includes("CPU%"),
            "Table has CPU% column"
        );
        assert(
            columnHeaders.includes("Memory (MB)"),
            "Table has Memory (MB) column"
        );
        assert(
            columnHeaders.includes("Status"),
            "Table has Status column"
        );

        // 5. Table data from mock
        const tableText = await page.evaluate(() => {
            const table = document.querySelector("table.process-table");
            return table ? table.textContent : "";
        });
        assert(
            tableText.includes("python3"),
            'Table shows "python3" process name'
        );
        assert(
            tableText.includes("25.3"),
            'Table shows "25.3" CPU% for python3'
        );
        assert(
            tableText.includes("ros2_node"),
            'Table shows "ros2_node" process name'
        );

        // 6. Row count
        const rowCount = await page.evaluate(() => {
            const rows = document.querySelectorAll(
                "table.process-table tbody tr"
            );
            return rows.length;
        });
        assert(
            rowCount === 3,
            `Table has 3 data rows (found: ${rowCount})`
        );

        // 7. Collapse on click
        await page.evaluate(() => {
            const toggle = document.querySelector(".process-table-toggle");
            if (toggle) toggle.click();
        });
        await page.waitForTimeout(500);

        const tableVisibleAfterCollapse = await page.evaluate(() => {
            const table = document.querySelector("table.process-table");
            return table !== null;
        });
        assert(
            !tableVisibleAfterCollapse,
            "Process table is hidden after collapsing"
        );

        // ==========================================================
        // [8] No JS console errors
        // ==========================================================
        console.log("\n[4] No JS console errors");

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
            "No relevant JS console errors" +
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
            "No uncaught page errors" +
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
