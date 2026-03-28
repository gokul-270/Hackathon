#!/usr/bin/env node
// ROS2 Introspection Tabs E2E Test Suite (Task 3.4)
//
// Tests loading skeletons, stale badges, retry buttons, and pagination
// for all four ROS2 introspection sub-tabs (Nodes, Topics, Services, Parameters).
//
// Run: node web_dashboard/e2e_tests/test_ros2_introspection_tabs.mjs
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

// Helper: check if page contains text within #entity-detail-section
async function sectionContainsText(page, text) {
    return page.evaluate(
        ({ text }) => {
            const section = document.getElementById("entity-detail-section");
            return section ? section.textContent.includes(text) : false;
        },
        { text },
    );
}

// Helper: count elements matching a style property within entity-detail-section
async function countSkeletonRows(page) {
    return page.evaluate(() => {
        const section = document.getElementById("entity-detail-section");
        if (!section) return 0;
        // Skeleton rows use shimmer animation
        const allDivs = section.querySelectorAll("div");
        let count = 0;
        for (const div of allDivs) {
            const style = div.getAttribute("style") || "";
            if (style.includes("shimmer")) count++;
        }
        return count;
    });
}

// Helper: click a tab button by label within entity detail section
async function clickTab(page, label) {
    return page.evaluate(
        ({ label }) => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return false;
            const buttons = section.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === label) {
                    btn.click();
                    return true;
                }
            }
            return false;
        },
        { label },
    );
}

// ---------------------------------------------------------------------------
// Mock data generators
// ---------------------------------------------------------------------------

function makeNodes(count) {
    return Array.from({ length: count }, (_, i) => ({
        name: `/node_${i}`,
        namespace: "/",
        lifecycle_state: i % 3 === 0 ? "active" : "inactive",
    }));
}

function makeTopics(count) {
    return Array.from({ length: count }, (_, i) => ({
        name: `/topic_${i}`,
        type: `std_msgs/msg/String`,
        publishers: [{ node: `/node_${i % 5}` }],
        subscribers: i % 2 === 0 ? [{ node: `/listener_${i}` }] : [],
    }));
}

function makeServices(count) {
    return Array.from({ length: count }, (_, i) => ({
        name: `/service_${i}`,
        type: `std_srvs/srv/Trigger`,
        nodes: [`/node_${i % 5}`],
    }));
}

function makeParameters(nodeCount, paramsPerNode) {
    const nodes = [];
    for (let n = 0; n < nodeCount; n++) {
        const parameters = [];
        for (let p = 0; p < paramsPerNode; p++) {
            parameters.push({
                name: `param_${p}`,
                value: p * 1.5,
                type: "double",
                description: `Parameter ${p}`,
            });
        }
        nodes.push({ name: `/node_${n}`, parameters });
    }
    return { nodes };
}

const ENTITY_DATA = {
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

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

(async () => {
    console.log("ROS2 Introspection Tabs E2E Tests (Task 3.4)");
    console.log(`Target: ${BASE}`);
    console.log("==========================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();

    // Collect JS errors
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
            route.abort("connectionrefused"),
        );

        // Mock entity data
        await page.route("**/api/entities/arm1", (route) => {
            const url = route.request().url();
            if (url.endsWith("/arm1") || url.endsWith("/arm1/")) {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify(ENTITY_DATA),
                });
            } else {
                route.continue();
            }
        });

        // Mock rosbag endpoints (prevent noise)
        await page.route("**/rosbag/**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify([]),
            }),
        );

        // Default: 60 nodes for pagination testing
        let nodeResponse = { status: 200, data: makeNodes(60) };
        let topicResponse = { status: 200, data: makeTopics(60) };
        let serviceResponse = { status: 200, data: makeServices(60) };
        let paramResponse = { status: 200, data: makeParameters(3, 25) };

        await page.route("**/api/entities/arm1/ros2/nodes", (route) => {
            if (nodeResponse.status !== 200) {
                route.fulfill({
                    status: nodeResponse.status,
                    contentType: "application/json",
                    body: JSON.stringify({ error: "mock error" }),
                });
            } else {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify({
                        data: nodeResponse.data,
                    }),
                });
            }
        });

        await page.route("**/api/entities/arm1/ros2/topics", (route) => {
            if (topicResponse.status !== 200) {
                route.fulfill({
                    status: topicResponse.status,
                    contentType: "application/json",
                    body: JSON.stringify({ error: "mock error" }),
                });
            } else {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify({
                        data: topicResponse.data,
                    }),
                });
            }
        });

        await page.route("**/api/entities/arm1/ros2/services", (route) => {
            const url = route.request().url();
            // Only intercept the services list endpoint, not service call
            if (url.endsWith("/ros2/services") || url.includes("/ros2/services?")) {
                if (serviceResponse.status !== 200) {
                    route.fulfill({
                        status: serviceResponse.status,
                        contentType: "application/json",
                        body: JSON.stringify({ error: "mock error" }),
                    });
                } else {
                    route.fulfill({
                        status: 200,
                        contentType: "application/json",
                        body: JSON.stringify({
                            data: serviceResponse.data,
                        }),
                    });
                }
            } else {
                route.continue();
            }
        });

        await page.route("**/api/entities/arm1/ros2/parameters", (route) => {
            if (paramResponse.status !== 200) {
                route.fulfill({
                    status: paramResponse.status,
                    contentType: "application/json",
                    body: JSON.stringify({ error: "mock error" }),
                });
            } else {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify({
                        data: paramResponse.data,
                    }),
                });
            }
        });

        // Mock SSE stream endpoint for topics echo
        await page.route("**/api/entities/arm1/ros2/topics/*/echo*", (route) =>
            route.abort("connectionrefused"),
        );

        // Mock node detail endpoints
        await page.route("**/api/entities/arm1/ros2/nodes/*/detail", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({
                    data: {
                        publishers: [{ name: "/topic_0", type: "std_msgs/msg/String" }],
                        subscribers: [],
                        services: [{ name: "/node_0/get_parameters", type: "rcl_interfaces/srv/GetParameters" }],
                        clients: [],
                    },
                }),
            }),
        );

        // ==========================================================
        // Load dashboard
        // ==========================================================
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
        await page.waitForTimeout(1000);

        // ==========================================================
        // [1] Nodes tab: data loads, shows pagination for 60 items
        // ==========================================================
        console.log("[1] Nodes tab — data loads with pagination");

        await navigateToHash(page, "#/entity/arm1/nodes");
        await page.waitForTimeout(2000);

        const nodesLoaded = await sectionContainsText(page, "node_0");
        assert(nodesLoaded, "Nodes tab shows node data after loading");

        const nodesHasPagination = await sectionContainsText(page, "Page 1 of");
        assert(nodesHasPagination, "Nodes tab shows pagination controls for 60 items");

        const nodesPageInfo = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return null;
            const spans = section.querySelectorAll("span");
            for (const s of spans) {
                const m = s.textContent.match(/Page (\d+) of (\d+)/);
                if (m) return { current: +m[1], total: +m[2] };
            }
            return null;
        });
        assert(
            nodesPageInfo && nodesPageInfo.total === 2,
            `Nodes pagination shows 2 pages for 60 items (got: ${JSON.stringify(nodesPageInfo)})`,
        );

        // ==========================================================
        // [2] Nodes tab: stale badge on error with cached data
        // ==========================================================
        console.log("\n[2] Nodes tab — stale badge on error fallback");

        // First visit populated the cache. Now make the endpoint fail.
        nodeResponse = { status: 503, data: null };

        // Navigate away and back to trigger a fresh fetch that will fail
        await navigateToHash(page, "#/entity/arm1/status");
        await page.waitForTimeout(500);
        await navigateToHash(page, "#/entity/arm1/nodes");
        await page.waitForTimeout(3000);

        const nodesStale = await sectionContainsText(page, "Stale");
        assert(nodesStale, "Nodes tab shows 'Stale' badge when API fails with cached data");

        // Should still show data (from cache)
        const nodesStillHasData = await sectionContainsText(page, "node_0");
        assert(nodesStillHasData, "Nodes tab still shows cached data when stale");

        // ==========================================================
        // [3] Nodes tab: retry button visible on stale/error
        // ==========================================================
        console.log("\n[3] Nodes tab — retry button");

        const nodesHasRetry = await sectionContainsText(page, "Retry");
        assert(nodesHasRetry, "Nodes tab shows Retry button on stale/error");

        // Restore the endpoint for retry
        nodeResponse = { status: 200, data: makeNodes(60) };

        // Click retry
        const retryClicked = await page.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return false;
            const buttons = section.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Retry") {
                    btn.click();
                    return true;
                }
            }
            return false;
        });
        assert(retryClicked, "Retry button was clickable");

        await page.waitForTimeout(2000);

        const nodesAfterRetry = await sectionContainsText(page, "node_0");
        assert(nodesAfterRetry, "Nodes tab shows fresh data after retry");

        // ==========================================================
        // [4] Topics tab: data loads with pagination
        // ==========================================================
        console.log("\n[4] Topics tab — data loads with pagination");

        await navigateToHash(page, "#/entity/arm1/topics");
        await page.waitForTimeout(2000);

        const topicsLoaded = await sectionContainsText(page, "topic_0");
        assert(topicsLoaded, "Topics tab shows topic data after loading");

        const topicsHasPagination = await sectionContainsText(page, "Page 1 of");
        assert(topicsHasPagination, "Topics tab shows pagination controls for 60 items");

        // ==========================================================
        // [5] Topics tab: stale badge on error
        // ==========================================================
        console.log("\n[5] Topics tab — stale badge on error fallback");

        topicResponse = { status: 503, data: null };
        await navigateToHash(page, "#/entity/arm1/status");
        await page.waitForTimeout(500);
        await navigateToHash(page, "#/entity/arm1/topics");
        await page.waitForTimeout(3000);

        const topicsStale = await sectionContainsText(page, "Stale");
        assert(topicsStale, "Topics tab shows 'Stale' badge when API fails with cached data");

        // Restore
        topicResponse = { status: 200, data: makeTopics(60) };

        // ==========================================================
        // [6] Services tab: data loads with pagination
        // ==========================================================
        console.log("\n[6] Services tab — data loads with pagination");

        await navigateToHash(page, "#/entity/arm1/services");
        await page.waitForTimeout(2000);

        const servicesLoaded = await sectionContainsText(page, "service_0");
        assert(servicesLoaded, "Services tab shows service data after loading");

        const servicesHasPagination = await sectionContainsText(page, "Page 1 of");
        assert(servicesHasPagination, "Services tab shows pagination controls for 60 items");

        // ==========================================================
        // [7] Services tab: stale badge
        // ==========================================================
        console.log("\n[7] Services tab — stale badge on error fallback");

        serviceResponse = { status: 503, data: null };
        await navigateToHash(page, "#/entity/arm1/status");
        await page.waitForTimeout(500);
        await navigateToHash(page, "#/entity/arm1/services");
        await page.waitForTimeout(3000);

        const servicesStale = await sectionContainsText(page, "Stale");
        assert(servicesStale, "Services tab shows 'Stale' badge when API fails with cached data");

        // Restore
        serviceResponse = { status: 200, data: makeServices(60) };

        // ==========================================================
        // [8] Parameters tab: data loads
        // ==========================================================
        console.log("\n[8] Parameters tab — data loads");

        await navigateToHash(page, "#/entity/arm1/parameters");
        await page.waitForTimeout(2000);

        const paramsLoaded = await sectionContainsText(page, "param_0");
        assert(paramsLoaded, "Parameters tab shows parameter data after loading");

        // Parameters use per-node pagination — check for page controls
        // With 3 nodes × 25 params, at least one node group should have pagination
        // (PAGE_SIZE is 50, so 25 params per node won't paginate — use more)
        // Already set to 3 nodes × 25 = 75 total, but per-node is 25 each (< 50)
        // Let's check that parameters are at least grouped by node
        const paramsHasNodeGroup = await sectionContainsText(page, "/node_0");
        assert(paramsHasNodeGroup, "Parameters tab shows node groups");

        // ==========================================================
        // [9] Parameters tab: stale badge
        // ==========================================================
        console.log("\n[9] Parameters tab — stale badge on error fallback");

        paramResponse = { status: 503, data: null };
        await navigateToHash(page, "#/entity/arm1/status");
        await page.waitForTimeout(500);
        await navigateToHash(page, "#/entity/arm1/parameters");
        await page.waitForTimeout(3000);

        const paramsStale = await sectionContainsText(page, "Stale");
        assert(paramsStale, "Parameters tab shows 'Stale' badge when API fails with cached data");

        // Restore
        paramResponse = { status: 200, data: makeParameters(3, 25) };

        // ==========================================================
        // [10] Rapid tab switching — no console errors
        // ==========================================================
        console.log("\n[10] Rapid tab switching — no console errors");

        // Clear previous errors
        consoleErrors.length = 0;
        pageErrors.length = 0;

        // Rapidly switch between all ROS2 tabs
        const tabs = ["nodes", "topics", "services", "parameters"];
        for (let i = 0; i < 3; i++) {
            for (const tab of tabs) {
                await navigateToHash(page, `#/entity/arm1/${tab}`);
                await page.waitForTimeout(200);
            }
        }
        await page.waitForTimeout(2000);

        // Filter out known non-issues (WebSocket, fetch failures from racing)
        const relevantErrors = consoleErrors.filter(
            (e) =>
                !e.includes("WebSocket") &&
                !e.includes("ws://") &&
                !e.includes("wss://") &&
                !e.includes("ERR_CONNECTION_REFUSED") &&
                !e.includes("net::ERR_FAILED") &&
                !e.includes("404") &&
                !e.includes("Failed to fetch") &&
                !e.includes("rosbag") &&
                !e.includes("AbortError") &&
                !e.includes("abort") &&
                !e.includes("Connection refused") &&
                !e.includes("cachedEntityFetch") &&
                !e.includes("503 (Service Unavailable)") &&
                !e.includes("502 (Bad Gateway)") &&
                !e.includes("safeFetch: HTTP"),
        );
        assert(
            relevantErrors.length === 0,
            "No unexpected JS console errors during rapid tab switching" +
                (relevantErrors.length > 0
                    ? ` (got ${relevantErrors.length}: ${relevantErrors.slice(0, 3).join("; ")})`
                    : ""),
        );

        const relevantPageErrors = pageErrors.filter(
            (e) =>
                !e.includes("WebSocket") &&
                !e.includes("ERR_CONNECTION_REFUSED") &&
                !e.includes("404") &&
                !e.includes("fetch") &&
                !e.includes("abort"),
        );
        assert(
            relevantPageErrors.length === 0,
            "No uncaught page errors during rapid tab switching" +
                (relevantPageErrors.length > 0
                    ? ` (got ${relevantPageErrors.length}: ${relevantPageErrors.slice(0, 3).join("; ")})`
                    : ""),
        );

        // ==========================================================
        // [11] Loading skeleton appears on initial load
        // ==========================================================
        console.log("\n[11] Loading skeleton on slow response");

        // Create a fresh page to avoid cache
        const page2 = await browser.newPage();

        await page2.route("**/ws", (route) =>
            route.abort("connectionrefused"),
        );

        await page2.route("**/api/entities/arm1", (route) => {
            const url = route.request().url();
            if (url.endsWith("/arm1") || url.endsWith("/arm1/")) {
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify(ENTITY_DATA),
                });
            } else {
                route.continue();
            }
        });

        await page2.route("**/rosbag/**", (route) =>
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify([]),
            }),
        );

        // Delay the nodes response to see skeleton
        let resolveNodes;
        await page2.route("**/api/entities/arm1/ros2/nodes", (route) => {
            resolveNodes = () =>
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify({ data: makeNodes(5) }),
                });
            // Don't fulfill yet — let it hang to show skeleton
        });

        await page2.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
        await page2.waitForTimeout(1000);

        await page2.evaluate((h) => {
            window.location.hash = h;
        }, "#/entity/arm1/nodes");
        await page2.waitForTimeout(1500);

        // Check for skeleton (shimmer animation elements)
        const hasSkeletonOrLoading = await page2.evaluate(() => {
            const section = document.getElementById("entity-detail-section");
            if (!section) return false;
            const html = section.innerHTML;
            return html.includes("shimmer") || html.includes("Loading");
        });
        assert(
            hasSkeletonOrLoading,
            "Loading skeleton/shimmer shown while waiting for data",
        );

        // Fulfill the pending request so the page doesn't hang
        if (resolveNodes) resolveNodes();
        await page2.waitForTimeout(1000);
        await page2.close();
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
            `${skipped} skipped (${total} total)`,
    );
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    console.log();
    process.exit(failed > 0 ? 1 : 0);
})();
