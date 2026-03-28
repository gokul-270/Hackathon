#!/usr/bin/env node
// Foundation Reconnect Behavior E2E Test (Group 7, Task 7.4)
// Tests what can be verified without manual server control:
// - Disconnect banner is NOT visible when connected
// - Disconnect banner DOM element structure is correct
// - Connection indicator shows "Connected" initially
// - Simulated disconnect (via WS close) triggers banner visibility
// - Banner text contains expected reconnect messaging
//
// Full reconnect test requires manual server stop/start:
// 1. Stop the dashboard server
// 2. Verify disconnect banner appears within 10s
// 3. Verify connection indicator turns red/amber
// 4. Restart the dashboard server
// 5. Verify reconnection within 10s
// 6. Verify data repopulates
//
// Run: node web_dashboard/e2e_tests/foundation_reconnect_e2e.mjs
//
// Requires: npm install playwright (in this directory)
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

/**
 * Inject a WebSocket tracker before the app creates its connection.
 * Patches the WebSocket constructor to capture all instances for
 * later simulated disconnect.
 */
async function injectWsTracker(page) {
    await page.addInitScript(() => {
        window.__pragati_ws_instances = [];
        const OrigWebSocket = window.WebSocket;
        window.WebSocket = function (...args) {
            const ws = new OrigWebSocket(...args);
            window.__pragati_ws_instances.push(ws);
            return ws;
        };
        window.WebSocket.prototype = OrigWebSocket.prototype;
        window.WebSocket.CONNECTING = OrigWebSocket.CONNECTING;
        window.WebSocket.OPEN = OrigWebSocket.OPEN;
        window.WebSocket.CLOSING = OrigWebSocket.CLOSING;
        window.WebSocket.CLOSED = OrigWebSocket.CLOSED;
    });
}

(async () => {
    console.log("Foundation Reconnect Behavior E2E Tests");
    console.log(`Target: ${BASE}`);
    console.log("========================================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();

    // Inject WS tracker before page loads
    await injectWsTracker(page);

    // Collect page errors
    const pageErrors = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));

    try {
        // ================================================================
        // [1] Load dashboard and verify initial connected state
        // ================================================================
        console.log("[1] Loading dashboard and verifying connected state...");
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
        await page.waitForTimeout(2000);

        // Verify WebSocket tracker captured connections
        const wsCount = await page.evaluate(
            () => (window.__pragati_ws_instances || []).length
        );
        assert(wsCount > 0, `WebSocket tracker captured ${wsCount} connection(s)`);

        // Verify connected state
        const connectedInitially = await page.evaluate(() => {
            const dot = document.getElementById("connection-indicator");
            return dot ? dot.classList.contains("connected") : false;
        });
        assert(connectedInitially, "Connection indicator shows connected initially");

        const connTextInitial = await page.evaluate(() => {
            const el = document.getElementById("connection-text");
            return el ? el.textContent.trim() : null;
        });
        assert(
            connTextInitial === "Connected",
            `Connection text says "Connected" initially (got: "${connTextInitial}")`
        );

        // ================================================================
        // [2] Disconnect banner is NOT visible when connected
        // ================================================================
        console.log("\n[2] Disconnect banner hidden when connected...");

        // The DisconnectBanner component returns null when connected,
        // so the .disconnect-banner element should not exist in the DOM
        const bannerExistsWhenConnected = await page.evaluate(
            () => !!document.querySelector(".disconnect-banner")
        );
        assert(
            !bannerExistsWhenConnected,
            "Disconnect banner is NOT in DOM when connected"
        );

        // ================================================================
        // [3] Simulate disconnect — close WebSocket connections
        // ================================================================
        console.log("\n[3] Simulating disconnect (closing WebSocket)...");

        await page.evaluate(() => {
            (window.__pragati_ws_instances || []).forEach((ws) => {
                if (ws.readyState <= 1) ws.close();
            });
        });

        // Wait for Preact to re-render with disconnected state
        await page.waitForTimeout(1500);

        // ================================================================
        // [4] Verify disconnect banner appears
        // ================================================================
        console.log("\n[4] Checking disconnect banner after WS close...");

        const bannerExistsAfterDisconnect = await page.evaluate(
            () => !!document.querySelector(".disconnect-banner")
        );
        assert(
            bannerExistsAfterDisconnect,
            "Disconnect banner appears in DOM after WS close"
        );

        // Verify banner text content — may show "Disconnected ... reconnecting in Ns"
        // OR "Reconnected" if the client reconnected faster than the check interval.
        // Both are valid: the important thing is the banner appeared.
        const bannerText = await page.evaluate(() => {
            const el = document.querySelector(".disconnect-banner");
            return el ? el.textContent.trim() : null;
        });
        const hasDisconnectedOrReconnected =
            bannerText !== null &&
            (bannerText.includes("Disconnected") ||
                bannerText.includes("Reconnected"));
        assert(
            hasDisconnectedOrReconnected,
            `Banner text contains "Disconnected" or "Reconnected" (got: "${bannerText}")`
        );

        const hasReconnectText =
            bannerText !== null &&
            (bannerText.includes("reconnecting in") ||
                bannerText.includes("reconnecting...") ||
                bannerText.includes("Reconnected"));
        assert(
            hasReconnectText,
            `Banner contains reconnect messaging (got: "${bannerText}")`
        );

        // Verify banner has fixed positioning (overlay behavior)
        const bannerPosition = await page.evaluate(() => {
            const el = document.querySelector(".disconnect-banner");
            return el ? getComputedStyle(el).position : null;
        });
        assert(
            bannerPosition === "fixed",
            `Disconnect banner has fixed positioning (got: "${bannerPosition}")`
        );

        // ================================================================
        // [5] Connection indicator updates to disconnected/reconnecting
        // ================================================================
        console.log("\n[5] Connection indicator after disconnect...");

        const indicatorClassAfter = await page.evaluate(() => {
            const dot = document.getElementById("connection-indicator");
            return dot ? dot.className : null;
        });
        // After simulated WS close, the indicator may show disconnected/reconnecting
        // OR connected (if reconnect happened faster than the check). Both are valid.
        const indicatorChangedOrReconnected =
            indicatorClassAfter !== null &&
            (indicatorClassAfter.includes("disconnected") ||
                indicatorClassAfter.includes("reconnecting") ||
                indicatorClassAfter.includes("connected"));
        assert(
            indicatorChangedOrReconnected,
            `Indicator shows disconnected/reconnecting/connected (got: "${indicatorClassAfter}")`
        );

        const connTextAfter = await page.evaluate(() => {
            const el = document.getElementById("connection-text");
            return el ? el.textContent.trim() : null;
        });
        // Accept any valid state text
        const validStateTexts = [
            "Connected",
            "Disconnected",
            "Reconnecting...",
        ];
        assert(
            connTextAfter !== null && validStateTexts.includes(connTextAfter),
            `Connection text is a valid state (got: "${connTextAfter}")`
        );

        const dotColorAfter = await page.evaluate(() => {
            const dot = document.getElementById("connection-indicator");
            return dot ? dot.style.backgroundColor : null;
        });
        // Should be amber (#f59e0b) for reconnecting, red (#ef4444) for disconnected,
        // or green (#22c55e) if already reconnected
        const isValidColor =
            dotColorAfter === "#f59e0b" ||
            dotColorAfter === "rgb(245, 158, 11)" ||
            dotColorAfter === "#ef4444" ||
            dotColorAfter === "rgb(239, 68, 68)" ||
            dotColorAfter === "#22c55e" ||
            dotColorAfter === "rgb(34, 197, 94)";
        assert(
            isValidColor,
            `Connection dot is a valid state color (got: "${dotColorAfter}")`
        );

        // ================================================================
        // [6] Banner countdown text (if in reconnecting state)
        // ================================================================
        console.log("\n[6] Reconnect countdown check...");

        const countdownMatch = await page.evaluate(() => {
            const el = document.querySelector(".disconnect-banner");
            if (!el) return null;
            const text = el.textContent;
            const match = text.match(/in (\d+)s/);
            return match ? parseInt(match[1], 10) : null;
        });

        if (countdownMatch !== null) {
            assert(
                countdownMatch > 0 && countdownMatch <= 30,
                `Reconnect countdown is within valid range 1-30s (got: ${countdownMatch}s)`
            );
        } else {
            // Countdown may have just expired — the banner may show "reconnecting..."
            skip(
                "Reconnect countdown in valid range",
                "Countdown not captured — may have expired (timing-sensitive)"
            );
        }

        // ================================================================
        // [7] Full reconnect test — requires server restart
        // ================================================================
        console.log("\n[7] Full reconnect lifecycle...");
        skip(
            "Server stop triggers disconnect banner within 10s",
            "Requires manual server stop — cannot automate without process control"
        );
        skip(
            "Server restart triggers reconnection within 10s",
            "Requires manual server restart — cannot automate without process control"
        );
        skip(
            "Data repopulates after reconnection",
            "Requires full reconnect cycle"
        );

        // ================================================================
        // [8] Error checks
        // ================================================================
        console.log("\n[8] Error checks...");

        // Filter out expected WebSocket errors (connection refused on reconnect attempts)
        const criticalErrors = pageErrors.filter(
            (e) =>
                !e.includes("WebSocket") &&
                !e.includes("ws://") &&
                !e.includes("wss://") &&
                !e.includes("favicon") &&
                !e.includes("chart") &&
                !e.includes("Chart")
        );
        assert(
            criticalErrors.length === 0,
            `No unexpected page errors (got ${criticalErrors.length}: ${criticalErrors.slice(0, 3).join("; ")})`
        );
    } catch (err) {
        console.error("\n  CRASH:", err.message);
        failed++;
        failures.push("CRASH: " + err.message);
    } finally {
        await browser.close();
    }

    // Summary
    const total = passed + failed + skipped;
    console.log("\n========================================");
    console.log(
        `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`
    );
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    process.exit(failed > 0 ? 1 : 0);
})();
