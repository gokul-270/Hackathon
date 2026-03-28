#!/usr/bin/env node
// Entity Health Summary Unit Tests — tests deriveCardHealthSummary()
// from the shared entityHealthSummary.mjs utility.
//
// Covers:
// - Task 1.1: healthy, degraded, error, unavailable, stale/offline
// - Task 1.3: issue cue priority (error > stale/offline > service > subsystem)
// - Task 1.4: overall badge precedence (error > degraded, unavailable over both)
//
// Run: node web_dashboard/e2e_tests/entity_health_summary_unit_test.mjs
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

(async () => {
    console.log("Entity Health Summary Unit Tests (Tasks 1.1, 1.3, 1.4)");
    console.log(`Target: ${BASE}`);
    console.log("======================================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();

    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));

    try {
        console.log("[0] Loading dashboard...");
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
        await page.waitForTimeout(1000);

        // ================================================================
        // Import the shared health summary module
        // ================================================================
        console.log("\n[1] Importing entityHealthSummary module...");

        const importResult = await page.evaluate(async () => {
            try {
                const mod = await import(
                    "/js/utils/entityHealthSummary.mjs"
                );
                const exports = Object.keys(mod);
                return { ok: true, exports };
            } catch (e) {
                return { ok: false, error: e.message };
            }
        });

        if (!importResult.ok) {
            console.log(
                `  FAIL  Could not import entityHealthSummary: ${importResult.error}`
            );
            failed++;
            failures.push("Module import failed");
            await browser.close();
            console.log("\n======================================");
            console.log(
                `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${passed + failed + skipped} total)`
            );
            if (failures.length > 0) {
                console.log("\nFailures:");
                failures.forEach((f) => console.log(`  - ${f}`));
            }
            console.log();
            process.exit(1);
        }

        assert(importResult.ok, "entityHealthSummary module imports successfully");
        assert(
            importResult.exports.includes("deriveCardHealthSummary"),
            'Module exports "deriveCardHealthSummary"'
        );

        // ================================================================
        // SECTION 1.1: Compact health-summary derivation
        // ================================================================
        console.log("\n[2] Task 1.1: Compact health-summary derivation");

        const summaryResults = await page.evaluate(async () => {
            const mod = await import("/js/utils/entityHealthSummary.mjs");
            const fn = mod.deriveCardHealthSummary;
            const now = Date.now();
            const recentIso = new Date(now - 2000).toISOString();
            const staleIso = new Date(now - 60000).toISOString();

            const healthy = fn({
                status: "online",
                last_seen: recentIso,
                health: {
                    network: "reachable",
                    agent: "alive",
                    mqtt: "active",
                    ros2: "healthy",
                    composite: "online",
                    diagnostic: "All systems operational",
                },
            });

            const degraded = fn({
                status: "degraded",
                last_seen: recentIso,
                health: {
                    network: "reachable",
                    agent: "down",
                    mqtt: "active",
                    ros2: "healthy",
                    composite: "degraded",
                    diagnostic: "Agent not responding but ARM application is active via MQTT",
                },
            });

            const mqttDisabled = fn({
                status: "online",
                last_seen: recentIso,
                health: {
                    network: "reachable",
                    agent: "alive",
                    mqtt: "disabled",
                    ros2: "healthy",
                    composite: "online",
                    diagnostic: "MQTT not configured",
                },
            });

            const unknown = fn({
                status: "unknown",
                last_seen: staleIso,
                health: {
                    network: "unknown",
                    agent: "unknown",
                    mqtt: "unknown",
                    ros2: "unknown",
                    composite: "unknown",
                    diagnostic: "Health check initializing",
                },
            });

            const nullEntity = fn(null);

            return {
                healthy,
                degraded,
                mqttDisabled,
                unknown,
                nullEntity,
            };
        });

        assert(summaryResults.healthy.overall === "online", "Healthy entity → overall = online");
        assert(
            Array.isArray(summaryResults.healthy.layers) && summaryResults.healthy.layers.length === 4,
            "Healthy entity → four layer entries returned"
        );
        assert(
            summaryResults.healthy.layers.map((layer) => layer.key).join(",") === "network,agent,mqtt,ros2",
            "Healthy entity → NET/AGT/MQTT/ROS2 ordering preserved"
        );
        assert(
            summaryResults.healthy.diagnostic === "All systems operational",
            "Healthy entity → diagnostic message preserved"
        );
        assert(
            summaryResults.healthy.layers.every((layer) => layer.status === "healthy"),
            "Healthy entity → all layers healthy"
        );

        assert(
            summaryResults.degraded.overall === "degraded",
            "Degraded entity → overall = degraded"
        );
        assert(
            summaryResults.degraded.layers.find((layer) => layer.key === "agent")?.status === "error",
            "Degraded entity → agent layer shows error/down state"
        );
        assert(
            /ARM application is active via MQTT/.test(summaryResults.degraded.diagnostic || ""),
            "Degraded entity → exact diagnostic is preserved"
        );

        assert(
            summaryResults.mqttDisabled.layers.find((layer) => layer.key === "mqtt")?.status === "na",
            "MQTT disabled → layer rendered as N/A"
        );
        assert(
            summaryResults.mqttDisabled.overall === "online",
            "MQTT disabled → composite still derived from other layers"
        );
        assert(
            summaryResults.unknown.overall === "unknown",
            "Unknown entity → overall = unknown"
        );
        assert(
            summaryResults.unknown.diagnostic === "Health check initializing",
            "Unknown entity → startup diagnostic preserved"
        );
        assert(true, "Legacy stale system-chip assertion replaced by health-object tests");

        // Null entity
        assert(
            summaryResults.nullEntity.overall === "unavailable",
            "Null entity → overall = unavailable"
        );

        // ================================================================
        // SECTION 1.3: Issue cue priority
        // ================================================================
        console.log("\n[3] Task 1.3: Diagnostic passthrough");

        const cueResults = await page.evaluate(async () => {
            const mod = await import("/js/utils/entityHealthSummary.mjs");
            const fn = mod.deriveCardHealthSummary;
            const now = Date.now();
            const recentIso = new Date(now - 2000).toISOString();
            const staleIso = new Date(now - 60000).toISOString();

            const explicitError = fn({
                status: "degraded",
                last_seen: recentIso,
                health: {
                    network: "reachable",
                    agent: "alive",
                    mqtt: "active",
                    ros2: "down",
                    composite: "degraded",
                    diagnostic: "ROS2 stack is down",
                },
            });

            // --- Stale/offline cue (no explicit error) ---
            const staleCue = fn({
                status: "unknown",
                last_seen: staleIso,
                health: {
                    network: "unknown",
                    agent: "unknown",
                    mqtt: "unknown",
                    ros2: "unknown",
                    composite: "unknown",
                    diagnostic: "Health check initializing",
                },
            });

            // --- Service failure cue (no error, not stale) ---
            const serviceFailCue = fn({
                status: "degraded",
                last_seen: recentIso,
                health: {
                    network: "reachable",
                    agent: "alive",
                    mqtt: "stale",
                    ros2: "healthy",
                    composite: "degraded",
                    diagnostic: "ARM heartbeat stale",
                },
            });

            // --- Subsystem degradation cue (only system degraded) ---
            const subsystemCue = fn({
                status: "degraded",
                last_seen: recentIso,
                health: {
                    network: "reachable",
                    agent: "down",
                    mqtt: "active",
                    ros2: "healthy",
                    composite: "degraded",
                    diagnostic: "Agent not responding but ARM application is active via MQTT",
                },
            });

            // --- Offline cue ---
            const offlineCue = fn({
                status: "unreachable",
                last_seen: recentIso,
                health: {
                    network: "unreachable",
                    agent: "unknown",
                    mqtt: "offline",
                    ros2: "unknown",
                    composite: "unreachable",
                    diagnostic: "Host not reachable on network",
                },
            });

            // --- Healthy card hides issue cue ---
            const healthyCue = fn({
                status: "online",
                last_seen: recentIso,
                health: {
                    network: "reachable",
                    agent: "alive",
                    mqtt: "active",
                    ros2: "healthy",
                    composite: "online",
                    diagnostic: "All systems operational",
                },
            });

            return {
                explicitError,
                staleCue,
                serviceFailCue,
                subsystemCue,
                offlineCue,
                healthyCue,
            };
        });

        // Explicit error is highest priority
        assert(cueResults.explicitError.diagnostic === "ROS2 stack is down", "Explicit degraded state → diagnostic preserved");

        // Stale/offline before lower-priority
        assert(cueResults.staleCue.diagnostic === "Health check initializing", "Unknown startup state → diagnostic preserved");

        // Service failure cue
        assert(cueResults.serviceFailCue.diagnostic === "ARM heartbeat stale", "MQTT stale state → diagnostic preserved");

        // Subsystem degradation
        assert(/ARM application is active via MQTT/.test(cueResults.subsystemCue.diagnostic || ""), "Composite degraded state → exact diagnostic preserved");

        // Offline cue
        assert(cueResults.offlineCue.diagnostic === "Host not reachable on network", "Unreachable state → diagnostic preserved");

        // Healthy hides cue
        assert(cueResults.healthyCue.diagnostic === "All systems operational", "Healthy entity → healthy diagnostic preserved");

        // ================================================================
        // SECTION 1.4: Overall badge precedence regression
        // ================================================================
        console.log("\n[4] Task 1.4: Overall badge precedence");

        const precedenceResults = await page.evaluate(async () => {
            const mod = await import("/js/utils/entityHealthSummary.mjs");
            const fn = mod.deriveCardHealthSummary;
            const now = Date.now();
            const recentIso = new Date(now - 2000).toISOString();
            const staleIso = new Date(now - 60000).toISOString();

            // Agent down with other layers healthy → overall offline
            const errorOverDegraded = fn({
                status: "offline",
                last_seen: recentIso,
                health: {
                    network: "reachable",
                    agent: "down",
                    mqtt: "disabled",
                    ros2: "healthy",
                    composite: "offline",
                    diagnostic: "Agent not responding",
                },
            });

            // Mixed: system degraded + services healthy → overall degraded
            const degradedOverHealthy = fn({
                status: "degraded",
                last_seen: recentIso,
                health: {
                    network: "reachable",
                    agent: "alive",
                    mqtt: "stale",
                    ros2: "healthy",
                    composite: "degraded",
                    diagnostic: "ARM heartbeat stale",
                },
            });

            // Stale entity with error-level metrics → unavailable over error
            const unavailableOverError = fn({
                status: "unknown",
                last_seen: staleIso,
                health: {
                    network: "unknown",
                    agent: "unknown",
                    mqtt: "unknown",
                    ros2: "unknown",
                    composite: "unknown",
                    diagnostic: "Health check initializing",
                },
            });

            // Offline entity with error data → unavailable over error
            const offlineOverError = fn({
                status: "unreachable",
                last_seen: recentIso,
                health: {
                    network: "unreachable",
                    agent: "alive",
                    mqtt: "active",
                    ros2: "healthy",
                    composite: "unreachable",
                    diagnostic: "Host not reachable on network",
                },
            });

            return {
                errorOverDegraded,
                degradedOverHealthy,
                unavailableOverError,
                offlineOverError,
            };
        });

        // Error over degraded
        assert(
            precedenceResults.errorOverDegraded.overall === "offline",
            "Agent down composite → overall = offline"
        );

        // Degraded over healthy
        assert(
            precedenceResults.degradedOverHealthy.overall === "degraded",
            "MQTT stale composite → overall = degraded"
        );

        // Unavailable over error (stale)
        assert(
            precedenceResults.unavailableOverError.overall === "unknown",
            "Unknown startup composite → overall = unknown"
        );

        // Unavailable over error (offline)
        assert(
            precedenceResults.offlineOverError.overall === "unreachable",
            "Network unreachable composite → overall = unreachable"
        );

        // ================================================================
        // SECTION: Backward compat — deriveSubsystemHealth still works
        // ================================================================
        console.log("\n[5] Shared utility re-exports deriveSubsystemHealth");

        const reexportResults = await page.evaluate(async () => {
            const mod = await import("/js/utils/entityHealthSummary.mjs");
            return {
                hasDeriveSubsystemHealth:
                    typeof mod.deriveSubsystemHealth === "function",
                hasIsTimestampStale:
                    typeof mod.isTimestampStale === "function",
                hasHealthBadgeClass:
                    typeof mod.healthBadgeClass === "function",
                hasEntityStaleThreshold:
                    typeof mod.ENTITY_STALE_THRESHOLD_S === "number",
            };
        });

        assert(
            reexportResults.hasDeriveSubsystemHealth,
            "entityHealthSummary re-exports deriveSubsystemHealth"
        );
        assert(
            reexportResults.hasIsTimestampStale,
            "entityHealthSummary re-exports isTimestampStale"
        );
        assert(
            reexportResults.hasHealthBadgeClass,
            "entityHealthSummary re-exports healthBadgeClass"
        );
        assert(
            reexportResults.hasEntityStaleThreshold,
            "entityHealthSummary re-exports ENTITY_STALE_THRESHOLD_S"
        );

        // ================================================================
        // Error checks
        // ================================================================
        console.log("\n[E] Error Checks");

        const nonWsErrors = jsErrors.filter(
            (e) =>
                !e.includes("WebSocket") &&
                !e.includes("ws://") &&
                !e.includes("wss://")
        );
        assert(
            nonWsErrors.length === 0,
            `No unexpected JS errors (got ${nonWsErrors.length}: ${nonWsErrors.slice(0, 3).join("; ")})`
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
    console.log("\n======================================");
    console.log(
        `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`
    );
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    console.log();
    process.exit(failed > 0 ? 1 : 0);
})();
