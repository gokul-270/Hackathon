#!/usr/bin/env node
// Foundation WebSocket Stability E2E Test (Group 7, Task 7.1)
// Verifies WebSocket connects, stays connected for 15s with zero disconnects,
// connection indicator shows green "Connected", and no WS console errors.
// Run: node web_dashboard/e2e_tests/foundation_websocket_e2e.mjs
//
// Requires: npm install playwright (in this directory)
// Dashboard must be running on http://127.0.0.1:8090

import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8090";
let passed = 0;
let failed = 0;
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

(async () => {
    console.log("Foundation WebSocket Stability E2E Tests");
    console.log(`Target: ${BASE}`);
    console.log("=========================================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();

    // Collect console errors related to WebSocket
    const wsConsoleErrors = [];
    const allConsoleErrors = [];
    page.on("console", (msg) => {
        if (msg.type() === "error") {
            const text = msg.text();
            allConsoleErrors.push(text);
            if (
                text.toLowerCase().includes("websocket") ||
                text.includes("ws://") ||
                text.includes("wss://")
            ) {
                wsConsoleErrors.push(text);
            }
        }
    });

    // Track page errors (uncaught exceptions)
    const pageErrors = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));

    try {
        // ================================================================
        // [1] Load dashboard and establish connection
        // ================================================================
        console.log("[1] Loading dashboard and verifying connection...");
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });

        // Wait for WebSocket to connect and Preact to render
        await page.waitForTimeout(2000);

        // ================================================================
        // [2] Check connection indicator — should be green "Connected"
        // ================================================================
        console.log("\n[2] Connection indicator checks...");

        const indicatorHasConnected = await page.evaluate(() => {
            const dot = document.getElementById("connection-indicator");
            return dot ? dot.classList.contains("connected") : false;
        });
        assert(
            indicatorHasConnected,
            'Connection indicator has "connected" class'
        );

        const indicatorNotDisconnected = await page.evaluate(() => {
            const dot = document.getElementById("connection-indicator");
            return dot ? !dot.classList.contains("disconnected") : false;
        });
        assert(
            indicatorNotDisconnected,
            'Connection indicator does not have "disconnected" class'
        );

        const connectionText = await page.evaluate(() => {
            const el = document.getElementById("connection-text");
            return el ? el.textContent.trim() : null;
        });
        assert(
            connectionText === "Connected",
            `Connection text says "Connected" (got: "${connectionText}")`
        );

        const dotColor = await page.evaluate(() => {
            const dot = document.getElementById("connection-indicator");
            return dot ? dot.style.backgroundColor : null;
        });
        assert(
            dotColor === "#22c55e" || dotColor === "rgb(34, 197, 94)",
            `Connection dot is green (got: "${dotColor}")`
        );

        // ================================================================
        // [3] Hold connection for 15s, checking stability
        // ================================================================
        console.log("\n[3] Stability check — holding connection for 15s...");

        const HOLD_DURATION_MS = 15000;
        const CHECK_INTERVAL_MS = 3000;
        let disconnectCount = 0;
        const checks = Math.floor(HOLD_DURATION_MS / CHECK_INTERVAL_MS);

        for (let i = 0; i < checks; i++) {
            await page.waitForTimeout(CHECK_INTERVAL_MS);
            const elapsed = (i + 1) * CHECK_INTERVAL_MS;
            const stillConnected = await page.evaluate(() => {
                const dot = document.getElementById("connection-indicator");
                return dot ? dot.classList.contains("connected") : false;
            });
            if (!stillConnected) {
                disconnectCount++;
                console.log(`    [${elapsed / 1000}s] DISCONNECTED`);
            } else {
                console.log(`    [${elapsed / 1000}s] still connected`);
            }
        }

        assert(
            disconnectCount === 0,
            `Zero disconnects over ${HOLD_DURATION_MS / 1000}s (got ${disconnectCount})`
        );

        // Re-check connection indicator after hold period
        const stillConnectedFinal = await page.evaluate(() => {
            const dot = document.getElementById("connection-indicator");
            return dot ? dot.classList.contains("connected") : false;
        });
        assert(
            stillConnectedFinal,
            "Connection indicator still green after hold period"
        );

        const finalText = await page.evaluate(() => {
            const el = document.getElementById("connection-text");
            return el ? el.textContent.trim() : null;
        });
        assert(
            finalText === "Connected",
            `Connection text still "Connected" after hold (got: "${finalText}")`
        );

        // ================================================================
        // [4] Console error checks
        // ================================================================
        console.log("\n[4] Console error checks...");

        assert(
            wsConsoleErrors.length === 0,
            `No WebSocket console errors (got ${wsConsoleErrors.length}: ${wsConsoleErrors.slice(0, 3).join("; ")})`
        );

        // Filter out known benign errors (e.g. favicon 404, chart library warnings)
        const criticalPageErrors = pageErrors.filter(
            (e) =>
                !e.includes("favicon") &&
                !e.includes("chart") &&
                !e.includes("Chart")
        );
        assert(
            criticalPageErrors.length === 0,
            `No critical page errors (got ${criticalPageErrors.length}: ${criticalPageErrors.slice(0, 3).join("; ")})`
        );
    } catch (err) {
        console.error("\n  CRASH:", err.message);
        failed++;
        failures.push("CRASH: " + err.message);
    } finally {
        await browser.close();
    }

    console.log(`\nResults: ${passed} passed, ${failed} failed`);
    if (failures.length) {
        console.log("Failures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    process.exit(failed > 0 ? 1 : 0);
})();
