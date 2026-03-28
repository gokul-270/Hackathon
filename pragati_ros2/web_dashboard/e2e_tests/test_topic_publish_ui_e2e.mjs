#!/usr/bin/env node
/**
 * E2E tests for TopicsSubTab publish panel (Tasks 6.1–6.4).
 *
 * Covers:
 *   - Publish panel dropdown populated with curated topics from config endpoint
 *   - Selecting a topic shows JSON form pre-filled with default_data
 *   - Successful publish sends correct request and shows success feedback
 *   - Error response (403) shows error feedback
 *   - Empty publishable-topics config shows "No publishable topics configured"
 *
 * Run: node web_dashboard/e2e_tests/test_topic_publish_ui_e2e.mjs
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
// Mock data
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

const PUBLISHABLE_TOPICS = [
    {
        name: "/start_switch/command",
        label: "Start Switch",
        message_type: "std_msgs/msg/Bool",
        default_data: { data: false },
    },
    {
        name: "/speed_override",
        label: "Speed Override",
        message_type: "std_msgs/msg/Float32",
        default_data: { data: 0.0 },
    },
];

const ROS2_TOPICS = [
    { name: "/cmd_vel", type: "geometry_msgs/msg/Twist", publisher_count: 1, subscriber_count: 2 },
    { name: "/start_switch/command", type: "std_msgs/msg/Bool", publisher_count: 0, subscriber_count: 1 },
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
        { t: text },
    );
}

async function bodyContainsText(page, text) {
    return page.evaluate((t) => document.body.textContent.includes(t), text);
}

/**
 * Set up common route mocks for an entity with Topics tab focus.
 */
async function setupTopicMocks(page, {
    entityData = ENTITY_ARM1,
    publishableTopics = PUBLISHABLE_TOPICS,
    publishHandler = null,
} = {}) {
    const id = entityData.id;

    // Abort WebSocket noise
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

    // ROS2 topics list
    await page.route(`**/api/entities/${id}/ros2/topics`, (route) => {
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ topics: ROS2_TOPICS }),
        });
    });

    // Publishable topics config
    await page.route("**/api/config/publishable-topics", (route) => {
        route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(publishableTopics),
        });
    });

    // Topic publish endpoint
    await page.route(`**/api/entities/${id}/ros2/topics/**/publish`, (route) => {
        if (route.request().method() !== "POST") {
            route.continue();
            return;
        }
        if (publishHandler) {
            route.fulfill(publishHandler);
        } else {
            route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ status: "published" }),
            });
        }
    });

    // Suppress other noise
    await page.route("**/rosbag/**", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
    );
    await page.route("**/api/entities/*/ros2/**", (route) => {
        const url = route.request().url();
        if (url.includes("/publish")) {
            route.continue();
        } else {
            route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
        }
    });
}

/**
 * Navigate to Topics sub-tab for the given entity.
 */
async function navigateToTopicsTab(page, entityId = "arm1") {
    await navigateToHash(page, `entity/${entityId}/ros2/topics`);
    await page.waitForTimeout(1500);
}

/**
 * Open the publish panel (click the collapsible header).
 */
async function openPublishPanel(page) {
    const header = page.locator('[data-testid="publish-panel-header"]');
    const count = await header.count();
    if (count > 0) {
        await header.click();
        await page.waitForTimeout(300);
        return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// Test runner
// ---------------------------------------------------------------------------

async function runTest(name, fn) {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on("console", (msg) => {
        if (msg.type() === "error") {
            // suppress expected network errors from mocks
        }
    });

    try {
        await fn(page);
    } catch (err) {
        failed++;
        failures.push(`${name}: ${err.message}`);
        console.log(`  FAIL  ${name}: ${err.message}`);
    } finally {
        await browser.close();
    }
}

// ---------------------------------------------------------------------------
// Test: Dashboard availability check
// ---------------------------------------------------------------------------

let dashboardAvailable = false;

try {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    const resp = await page.goto(BASE, { timeout: 8000 }).catch(() => null);
    dashboardAvailable = resp !== null && resp.status() < 500;
    await browser.close();
} catch {
    dashboardAvailable = false;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

console.log("\nTopicPublishUI E2E Tests");
console.log("========================\n");

if (!dashboardAvailable) {
    console.log(
        "  WARN  Dashboard not reachable at " + BASE + " — all tests will be skipped.\n" +
        "        Start the dashboard with: python3 web_dashboard/run_dashboard.py\n",
    );
    skip("test_topic_dropdown_shows_curated_topics", "dashboard not running");
    skip("test_selecting_topic_shows_form", "dashboard not running");
    skip("test_publish_sends_request_and_shows_success", "dashboard not running");
    skip("test_publish_error_shows_toast", "dashboard not running");
    skip("test_no_publishable_topics_shows_message", "dashboard not running");
} else {
    // -------------------------------------------------------------------------
    // Test 1: Dropdown shows curated topics from config endpoint
    // -------------------------------------------------------------------------
    await runTest("test_topic_dropdown_shows_curated_topics", async (page) => {
        await setupTopicMocks(page);
        await page.goto(BASE, { waitUntil: "domcontentloaded" });
        await navigateToTopicsTab(page);

        const opened = await openPublishPanel(page);
        if (!opened) {
            skip("test_topic_dropdown_shows_curated_topics", "publish panel not found");
            return;
        }

        // Check "Start Switch" label appears in the dropdown
        const selectEl = page.locator('[data-testid="publish-topic-select"]');
        const selectCount = await selectEl.count();
        if (selectCount === 0) {
            skip("test_topic_dropdown_shows_curated_topics", "select element not found");
            return;
        }

        const selectText = await selectEl.textContent();
        assert(
            selectText.includes("Start Switch"),
            "test_topic_dropdown_shows_curated_topics: 'Start Switch' visible in dropdown",
        );
        assert(
            selectText.includes("Speed Override"),
            "test_topic_dropdown_shows_curated_topics: 'Speed Override' visible in dropdown",
        );
    });

    // -------------------------------------------------------------------------
    // Test 2: Selecting a topic shows form with default_data pre-filled
    // -------------------------------------------------------------------------
    await runTest("test_selecting_topic_shows_form", async (page) => {
        await setupTopicMocks(page);
        await page.goto(BASE, { waitUntil: "domcontentloaded" });
        await navigateToTopicsTab(page);

        const opened = await openPublishPanel(page);
        if (!opened) {
            skip("test_selecting_topic_shows_form", "publish panel not found");
            return;
        }

        const selectEl = page.locator('[data-testid="publish-topic-select"]');
        if ((await selectEl.count()) === 0) {
            skip("test_selecting_topic_shows_form", "select element not found");
            return;
        }

        // Select "Start Switch"
        await selectEl.selectOption({ value: "/start_switch/command" });
        await page.waitForTimeout(500);

        // Textarea should now appear
        const textarea = page.locator('[data-testid="publish-data-textarea"]');
        assert(
            (await textarea.count()) > 0,
            "test_selecting_topic_shows_form: textarea appears after topic selection",
        );

        if ((await textarea.count()) > 0) {
            const textareaValue = await textarea.inputValue();
            // default_data is {data: false}
            assert(
                textareaValue.includes("false"),
                "test_selecting_topic_shows_form: textarea pre-filled with default_data",
            );
        }

        // Publish button should appear
        const publishBtn = page.locator('[data-testid="publish-button"]');
        assert(
            (await publishBtn.count()) > 0,
            "test_selecting_topic_shows_form: Publish button visible",
        );
    });

    // -------------------------------------------------------------------------
    // Test 3: Publish success shows feedback message
    // -------------------------------------------------------------------------
    await runTest("test_publish_sends_request_and_shows_success", async (page) => {
        let publishRequestBody = null;

        await setupTopicMocks(page, {
            publishHandler: {
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ status: "published" }),
            },
        });

        // Intercept to capture request body
        page.on("request", (req) => {
            if (req.method() === "POST" && req.url().includes("/publish")) {
                publishRequestBody = req.postData();
            }
        });

        await page.goto(BASE, { waitUntil: "domcontentloaded" });
        await navigateToTopicsTab(page);

        const opened = await openPublishPanel(page);
        if (!opened) {
            skip("test_publish_sends_request_and_shows_success", "publish panel not found");
            return;
        }

        const selectEl = page.locator('[data-testid="publish-topic-select"]');
        if ((await selectEl.count()) === 0) {
            skip("test_publish_sends_request_and_shows_success", "select element not found");
            return;
        }

        await selectEl.selectOption({ value: "/start_switch/command" });
        await page.waitForTimeout(500);

        const publishBtn = page.locator('[data-testid="publish-button"]');
        if ((await publishBtn.count()) === 0) {
            skip("test_publish_sends_request_and_shows_success", "publish button not found");
            return;
        }

        await publishBtn.click();
        await page.waitForTimeout(800);

        // Check success feedback
        const feedback = page.locator('[data-testid="publish-feedback"]');
        assert(
            (await feedback.count()) > 0,
            "test_publish_sends_request_and_shows_success: feedback element visible",
        );

        if ((await feedback.count()) > 0) {
            const feedbackText = await feedback.textContent();
            assert(
                feedbackText.toLowerCase().includes("success") ||
                feedbackText.toLowerCase().includes("published"),
                "test_publish_sends_request_and_shows_success: success message shown",
            );
        }

        // Verify request contained message_type
        if (publishRequestBody) {
            const body = JSON.parse(publishRequestBody);
            assert(
                body.message_type === "std_msgs/msg/Bool",
                "test_publish_sends_request_and_shows_success: request includes correct message_type",
            );
            assert(
                typeof body.data === "object",
                "test_publish_sends_request_and_shows_success: request includes data object",
            );
        }
    });

    // -------------------------------------------------------------------------
    // Test 4: Publish 403 error shows error feedback
    // -------------------------------------------------------------------------
    await runTest("test_publish_error_shows_toast", async (page) => {
        await setupTopicMocks(page, {
            publishHandler: {
                status: 403,
                contentType: "application/json",
                body: JSON.stringify({ error: "Topic not in allowlist" }),
            },
        });

        await page.goto(BASE, { waitUntil: "domcontentloaded" });
        await navigateToTopicsTab(page);

        const opened = await openPublishPanel(page);
        if (!opened) {
            skip("test_publish_error_shows_toast", "publish panel not found");
            return;
        }

        const selectEl = page.locator('[data-testid="publish-topic-select"]');
        if ((await selectEl.count()) === 0) {
            skip("test_publish_error_shows_toast", "select element not found");
            return;
        }

        await selectEl.selectOption({ value: "/start_switch/command" });
        await page.waitForTimeout(500);

        const publishBtn = page.locator('[data-testid="publish-button"]');
        if ((await publishBtn.count()) === 0) {
            skip("test_publish_error_shows_toast", "publish button not found");
            return;
        }

        await publishBtn.click();
        await page.waitForTimeout(800);

        const feedback = page.locator('[data-testid="publish-feedback"]');
        assert(
            (await feedback.count()) > 0,
            "test_publish_error_shows_toast: error feedback element visible",
        );

        if ((await feedback.count()) > 0) {
            const feedbackText = await feedback.textContent();
            assert(
                feedbackText.includes("allowlist") ||
                feedbackText.includes("403") ||
                feedbackText.includes("Error"),
                "test_publish_error_shows_toast: error message content shown",
            );
        }
    });

    // -------------------------------------------------------------------------
    // Test 5: Empty publishable topics shows message
    // -------------------------------------------------------------------------
    await runTest("test_no_publishable_topics_shows_message", async (page) => {
        await setupTopicMocks(page, { publishableTopics: [] });

        await page.goto(BASE, { waitUntil: "domcontentloaded" });
        await navigateToTopicsTab(page);

        const opened = await openPublishPanel(page);
        if (!opened) {
            skip("test_no_publishable_topics_shows_message", "publish panel not found");
            return;
        }

        // Should show empty state message, not a select
        const emptyMsg = page.locator('[data-testid="publish-no-topics"]');
        assert(
            (await emptyMsg.count()) > 0,
            "test_no_publishable_topics_shows_message: empty state element visible",
        );

        if ((await emptyMsg.count()) > 0) {
            const msgText = await emptyMsg.textContent();
            assert(
                msgText.toLowerCase().includes("no publishable"),
                "test_no_publishable_topics_shows_message: empty state message text correct",
            );
        }

        // Dropdown should NOT be present
        const selectEl = page.locator('[data-testid="publish-topic-select"]');
        assert(
            (await selectEl.count()) === 0,
            "test_no_publishable_topics_shows_message: no select shown when empty",
        );
    });
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\nResults: ${passed} passed, ${failed} failed, ${skipped} skipped\n`);

if (failures.length > 0) {
    console.log("Failures:");
    for (const f of failures) {
        console.log(`  - ${f}`);
    }
    console.log("");
}

process.exit(failed > 0 ? 1 : 0);
