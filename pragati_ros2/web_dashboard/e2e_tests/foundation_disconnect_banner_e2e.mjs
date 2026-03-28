#!/usr/bin/env node
/**
 * Foundation Disconnect Banner E2E Test (Group 8, Task 8.2)
 *
 * Verifies disconnect banner positioning and z-index layering relative to the
 * dashboard header. The banner should sit at top: 73px (below header) with
 * z-index: 10000, while the header has z-index: 10001. Also verifies the
 * E-STOP button is present and not obscured by overlays.
 *
 * NOTE: Testing the actual "banner appears on disconnect" behavior requires
 * killing the backend server mid-test, which is covered by
 * connection_resilience_e2e.mjs. This test focuses on CSS/layout correctness
 * and the hidden state when the connection is healthy.
 *
 * Run: node web_dashboard/e2e_tests/foundation_disconnect_banner_e2e.mjs
 *
 * Requires: npm install playwright (in this directory)
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

// Helper: check element exists
async function exists(page, selector) {
    return page.evaluate((sel) => !!document.querySelector(sel), selector);
}

(async () => {
    console.log("Foundation Disconnect Banner E2E Tests (Group 8, Task 8.2)");
    console.log(`Target: ${BASE}`);
    console.log("==========================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();

    // Collect JS errors
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));

    try {
        // Load dashboard and wait for connection to be established
        console.log("[0] Loading dashboard...");
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
        await page.waitForTimeout(2000);

        const title = await page.title();
        assert(title.length > 0, "Dashboard page loads with a title");

        // ================================================================
        // SECTION 1: Disconnect banner NOT visible when connected
        // ================================================================
        console.log("\n[1] Banner Hidden When Connected");

        const bannerExists = await exists(page, ".disconnect-banner");
        assert(
            !bannerExists,
            "Disconnect banner is not in DOM when WebSocket is connected",
        );

        // ================================================================
        // SECTION 2: Disconnect banner CSS rules (position, top, z-index)
        // ================================================================
        console.log("\n[2] Disconnect Banner CSS Rules");

        // The .disconnect-banner class is defined in styles.css even when no
        // element exists in the DOM. We can verify the CSS rule by creating a
        // temporary element and reading its computed style.
        const bannerStyles = await page.evaluate(() => {
            const el = document.createElement("div");
            el.className = "disconnect-banner";
            // Must be in the DOM for getComputedStyle to work
            document.body.appendChild(el);
            const cs = getComputedStyle(el);
            const result = {
                position: cs.position,
                top: cs.top,
                zIndex: parseInt(cs.zIndex, 10) || 0,
                left: cs.left,
                right: cs.right,
            };
            document.body.removeChild(el);
            return result;
        });

        assert(
            bannerStyles.position === "fixed",
            `Disconnect banner has position: fixed (got: "${bannerStyles.position}")`,
        );
        assert(
            bannerStyles.top === "73px",
            `Disconnect banner has top: 73px (got: "${bannerStyles.top}")`,
        );
        assert(
            bannerStyles.zIndex === 10000,
            `Disconnect banner has z-index: 10000 (got: ${bannerStyles.zIndex})`,
        );
        assert(
            bannerStyles.left === "0px",
            `Disconnect banner has left: 0 (got: "${bannerStyles.left}")`,
        );
        assert(
            bannerStyles.right === "0px",
            `Disconnect banner has right: 0 (got: "${bannerStyles.right}")`,
        );

        // ================================================================
        // SECTION 3: Header z-index is higher than banner z-index
        // ================================================================
        console.log("\n[3] Header Z-Index Layering");

        const headerStyles = await page.evaluate(() => {
            const header = document.querySelector(".dashboard-header");
            if (!header) return null;
            const cs = getComputedStyle(header);
            return {
                zIndex: parseInt(cs.zIndex, 10) || 0,
                position: cs.position,
            };
        });

        assert(headerStyles !== null, "Dashboard header element exists");
        if (headerStyles) {
            assert(
                headerStyles.zIndex === 10001,
                `Header has z-index: 10001 (got: ${headerStyles.zIndex})`,
            );
            assert(
                headerStyles.zIndex > bannerStyles.zIndex,
                `Header z-index (${headerStyles.zIndex}) > banner z-index (${bannerStyles.zIndex})`,
            );
            assert(
                headerStyles.position === "sticky",
                `Header has position: sticky (got: "${headerStyles.position}")`,
            );
        }

        // ================================================================
        // SECTION 4: E-STOP buttons exist and are clickable (dual-button layout)
        // ================================================================
        console.log("\n[4] E-STOP Button Accessibility");

        const estopInfo = await page.evaluate(() => {
            // Check for E-STOP All button (always present)
            const btn = document.getElementById("estop-all-btn");
            if (!btn) return null;
            const cs = getComputedStyle(btn);
            const rect = btn.getBoundingClientRect();
            return {
                exists: true,
                visible: cs.display !== "none" && cs.visibility !== "hidden",
                text: btn.textContent.trim(),
                width: rect.width,
                height: rect.height,
                disabled: btn.disabled,
            };
        });

        assert(estopInfo !== null, "E-STOP All button exists in DOM (#estop-all-btn)");
        if (estopInfo) {
            assert(
                estopInfo.visible,
                "E-STOP All button is visible (not display:none or visibility:hidden)",
            );
            assert(
                estopInfo.text.includes("E-STOP"),
                `E-STOP All button text contains "E-STOP" (got: "${estopInfo.text}")`,
            );
            assert(
                estopInfo.width > 0 && estopInfo.height > 0,
                `E-STOP All button has non-zero dimensions (${estopInfo.width}x${estopInfo.height})`,
            );

            // Verify E-STOP All is not blocked by any overlay at its center point
            const estopClickable = await page.evaluate(() => {
                const btn = document.getElementById("estop-all-btn");
                if (!btn) return false;
                const rect = btn.getBoundingClientRect();
                const cx = rect.left + rect.width / 2;
                const cy = rect.top + rect.height / 2;
                const topEl = document.elementFromPoint(cx, cy);
                // The top element should be the button itself or a child of it
                return topEl === btn || btn.contains(topEl);
            });
            assert(
                estopClickable,
                "E-STOP All button is the topmost element at its center (not blocked by overlay)",
            );
        }

        // Also verify entity E-Stop button exists
        const estopEntityExists = await page.evaluate(
            () => !!document.getElementById("estop-entity-btn")
        );
        assert(estopEntityExists, "E-STOP entity button exists in DOM (#estop-entity-btn)");

        // ================================================================
        // SECTION 5: Connection indicator shows connected state
        // ================================================================
        console.log("\n[5] Connection Indicator");

        const indicatorInfo = await page.evaluate(() => {
            const dot = document.getElementById("connection-indicator");
            const text = document.getElementById("connection-text");
            if (!dot || !text) return null;
            return {
                dotExists: true,
                textContent: text.textContent.trim(),
                dotClasses: dot.className,
            };
        });

        assert(
            indicatorInfo !== null,
            "Connection indicator elements exist (#connection-indicator, #connection-text)",
        );
        if (indicatorInfo) {
            // When connected, indicator should show "Connected" text
            // (may vary: "Connected", "Connected to ws://...")
            const isConnected =
                indicatorInfo.textContent.includes("Connected") ||
                indicatorInfo.textContent.includes("connected");
            assert(
                isConnected,
                `Connection text shows connected state (got: "${indicatorInfo.textContent}")`,
            );
        }

        // ================================================================
        // SECTION 6: Error Checks
        // ================================================================
        console.log("\n[6] Error Checks");

        const nonWsErrors = jsErrors.filter(
            (e) =>
                !e.includes("WebSocket") &&
                !e.includes("ws://") &&
                !e.includes("wss://"),
        );
        assert(
            nonWsErrors.length === 0,
            `No unexpected JS errors (got ${nonWsErrors.length}: ${nonWsErrors.slice(0, 3).join("; ")})`,
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
        `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`,
    );
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    console.log();
    process.exit(failed > 0 ? 1 : 0);
})();
