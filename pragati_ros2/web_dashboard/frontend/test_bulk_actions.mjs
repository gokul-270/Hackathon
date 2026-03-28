#!/usr/bin/env node
/**
 * Unit tests for bulkActions.js utility.
 * Run: node --test web_dashboard/frontend/test_bulk_actions.mjs
 *
 * Since bulkActions.js imports safeFetch from ../utils.js (which uses browser
 * globals like fetch/toast), we cannot import the module directly in Node.js.
 * Instead we read the source, strip the import, inject a mock safeFetch via
 * the Function constructor, and test the extracted functions.
 */

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// ---------------------------------------------------------------------------
// Load and evaluate bulkActions.js with a mock safeFetch
// ---------------------------------------------------------------------------

const sourceFile = join(__dirname, "js", "utils", "bulkActions.js");
const rawSource = readFileSync(sourceFile, "utf8");

// Strip the import line and export keywords so we get plain declarations.
const strippedSource = rawSource
    .replace(/import\s*\{[^}]*\}\s*from\s*["'][^"']*["']\s*;/g, "")
    .replace(/export\s+/g, "");

/**
 * Build a fresh module scope with the given safeFetch mock injected.
 * Returns { getServiceName, executeBulkAction }.
 */
function createModule(safeFetchImpl) {
    // Wrap the source so `safeFetch` resolves to our mock.
    // Return the two public functions.
    const wrapper = [
        "return (async function(__safeFetch) {",
        "  const safeFetch = __safeFetch;",
        strippedSource,
        "  return { getServiceName, executeBulkAction };",
        "})(__safeFetchArg);",
    ].join("\n");

    // eslint-disable-next-line no-new-func
    const factory = new Function("__safeFetchArg", wrapper);
    return factory(safeFetchImpl);
}

// Default module with a no-op safeFetch (overridden per-test as needed).
let mod;
let mockSafeFetch;

// ===========================================================================
// getServiceName
// ===========================================================================

describe("getServiceName", () => {
    beforeEach(async () => {
        mockSafeFetch = () => Promise.resolve(null);
        mod = await createModule(mockSafeFetch);
    });

    it("returns 'arm_launch' for entity_type 'arm'", () => {
        assert.equal(mod.getServiceName({ entity_type: "arm" }), "arm_launch");
    });

    it("returns 'vehicle_launch' for entity_type 'vehicle'", () => {
        assert.equal(
            mod.getServiceName({ entity_type: "vehicle" }),
            "vehicle_launch",
        );
    });

    it("returns null for unknown entity_type", () => {
        assert.equal(mod.getServiceName({ entity_type: "drone" }), null);
    });

    it("returns null when entity_type is missing", () => {
        assert.equal(mod.getServiceName({}), null);
    });
});

// ===========================================================================
// ACTION_REGISTRY validation (tested indirectly via executeBulkAction)
// ===========================================================================

describe("action registry", () => {
    beforeEach(async () => {
        mockSafeFetch = () => Promise.resolve({ ok: true });
        mod = await createModule(mockSafeFetch);
    });

    it("estop generates correct endpoint URL", async () => {
        let capturedUrl;
        mod = await createModule((url) => {
            capturedUrl = url;
            return Promise.resolve({ ok: true });
        });

        await mod.executeBulkAction("estop", [
            { id: "arm-1", name: "Arm 1", entity_type: "arm" },
        ]);

        assert.equal(capturedUrl, "/api/entities/arm-1/estop");
    });

    it("reboot sends correct body with REBOOT token", async () => {
        let capturedOpts;
        mod = await createModule((_url, opts) => {
            capturedOpts = opts;
            return Promise.resolve({ ok: true });
        });

        await mod.executeBulkAction("reboot", [
            { id: "arm-1", name: "Arm 1" },
        ]);

        assert.equal(capturedOpts.method, "POST");
        assert.deepEqual(JSON.parse(capturedOpts.body), { token: "REBOOT" });
    });

    it("shutdown sends correct body with SHUTDOWN token", async () => {
        let capturedOpts;
        mod = await createModule((_url, opts) => {
            capturedOpts = opts;
            return Promise.resolve({ ok: true });
        });

        await mod.executeBulkAction("shutdown", [
            { id: "arm-1", name: "Arm 1" },
        ]);

        assert.deepEqual(JSON.parse(capturedOpts.body), { token: "SHUTDOWN" });
    });

    it("restart-ros2 generates correct service URL for arm", async () => {
        let capturedUrl;
        mod = await createModule((url) => {
            capturedUrl = url;
            return Promise.resolve({ ok: true });
        });

        await mod.executeBulkAction("restart-ros2", [
            { id: "arm-2", name: "Arm 2", entity_type: "arm" },
        ]);

        assert.equal(
            capturedUrl,
            "/api/entities/arm-2/system/services/arm_launch/restart",
        );
    });

    it("restart-ros2 generates correct service URL for vehicle", async () => {
        let capturedUrl;
        mod = await createModule((url) => {
            capturedUrl = url;
            return Promise.resolve({ ok: true });
        });

        await mod.executeBulkAction("restart-ros2", [
            { id: "v-1", name: "Vehicle 1", entity_type: "vehicle" },
        ]);

        assert.equal(
            capturedUrl,
            "/api/entities/v-1/system/services/vehicle_launch/restart",
        );
    });
});

// ===========================================================================
// executeBulkAction — success / failure / partial
// ===========================================================================

describe("executeBulkAction — per-entity actions", () => {
    it("returns empty array for empty entities", async () => {
        mod = await createModule(() => Promise.resolve({ ok: true }));
        const results = await mod.executeBulkAction("estop", []);
        assert.deepEqual(results, []);
    });

    it("returns empty array when entities is null-ish", async () => {
        mod = await createModule(() => Promise.resolve({ ok: true }));
        const results = await mod.executeBulkAction("estop", null);
        assert.deepEqual(results, []);
    });

    it("all succeed: every result has status 'fulfilled'", async () => {
        mod = await createModule(() =>
            Promise.resolve({ status: "ok" }),
        );

        const entities = [
            { id: "a1", name: "Arm 1", entity_type: "arm" },
            { id: "a2", name: "Arm 2", entity_type: "arm" },
        ];
        const results = await mod.executeBulkAction("estop", entities);

        assert.equal(results.length, 2);
        for (const r of results) {
            assert.equal(r.status, "fulfilled");
            assert.deepEqual(r.value, { status: "ok" });
        }
    });

    it("all fail (safeFetch returns null): every result is 'rejected'", async () => {
        mod = await createModule(() => Promise.resolve(null));

        const entities = [
            { id: "a1", name: "Arm 1" },
            { id: "a2", name: "Arm 2" },
        ];
        const results = await mod.executeBulkAction("estop", entities);

        assert.equal(results.length, 2);
        for (const r of results) {
            assert.equal(r.status, "rejected");
            assert.ok(r.reason.includes("failed for"));
        }
    });

    it("partial failure: mix of fulfilled and rejected", async () => {
        let callIndex = 0;
        mod = await createModule(() => {
            callIndex++;
            // First call succeeds, second fails
            return callIndex === 1
                ? Promise.resolve({ status: "ok" })
                : Promise.resolve(null);
        });

        const entities = [
            { id: "a1", name: "Arm 1" },
            { id: "a2", name: "Arm 2" },
        ];
        const results = await mod.executeBulkAction("estop", entities);

        assert.equal(results.length, 2);
        const statuses = results.map((r) => r.status);
        assert.ok(statuses.includes("fulfilled"));
        assert.ok(statuses.includes("rejected"));
    });

    it("unknown action type: all entities rejected", async () => {
        mod = await createModule(() => Promise.resolve({ ok: true }));

        const entities = [{ id: "a1", name: "Arm 1" }];
        const results = await mod.executeBulkAction("nonexistent", entities);

        assert.equal(results.length, 1);
        assert.equal(results[0].status, "rejected");
        assert.ok(results[0].reason.includes("Unknown action type"));
    });

    it("restart-ros2 with unknown entity_type rejects that entity", async () => {
        mod = await createModule(() => Promise.resolve({ ok: true }));

        const entities = [
            { id: "x1", name: "Mystery", entity_type: "unknown_thing" },
        ];
        const results = await mod.executeBulkAction("restart-ros2", entities);

        assert.equal(results.length, 1);
        assert.equal(results[0].status, "rejected");
        assert.ok(results[0].reason.includes("Unknown entity type"));
    });

    it("uses entity.id as entityName when name is missing", async () => {
        mod = await createModule(() => Promise.resolve({ ok: true }));

        const results = await mod.executeBulkAction("estop", [
            { id: "arm-no-name" },
        ]);

        assert.equal(results[0].entityName, "arm-no-name");
        assert.equal(results[0].entityId, "arm-no-name");
    });
});

// ===========================================================================
// executeBulkAction — onProgress callback
// ===========================================================================

describe("executeBulkAction — onProgress", () => {
    it("calls onProgress with 'pending', then 'running', then final status", async () => {
        mod = await createModule(() => Promise.resolve({ ok: true }));

        const progressLog = [];
        await mod.executeBulkAction(
            "estop",
            [{ id: "a1", name: "Arm 1" }],
            {
                onProgress(entityId, status) {
                    progressLog.push({ entityId, status });
                },
            },
        );

        // Should see: pending -> running -> fulfilled
        assert.ok(progressLog.length >= 3, `Expected >= 3 calls, got ${progressLog.length}`);
        assert.equal(progressLog[0].status, "pending");
        assert.equal(progressLog[1].status, "running");
        assert.equal(progressLog[progressLog.length - 1].status, "fulfilled");
    });

    it("calls onProgress with 'rejected' when safeFetch returns null", async () => {
        mod = await createModule(() => Promise.resolve(null));

        const progressLog = [];
        await mod.executeBulkAction(
            "estop",
            [{ id: "a1", name: "Arm 1" }],
            {
                onProgress(entityId, status) {
                    progressLog.push({ entityId, status });
                },
            },
        );

        const finalStatus = progressLog[progressLog.length - 1].status;
        assert.equal(finalStatus, "rejected");
    });

    it("restart-ros2 with bad entity_type reports 'rejected' via onProgress", async () => {
        mod = await createModule(() => Promise.resolve({ ok: true }));

        const progressLog = [];
        await mod.executeBulkAction(
            "restart-ros2",
            [{ id: "x1", name: "X", entity_type: "bad" }],
            {
                onProgress(entityId, status) {
                    progressLog.push({ entityId, status });
                },
            },
        );

        const statuses = progressLog.map((p) => p.status);
        assert.ok(statuses.includes("rejected"));
    });
});

// ===========================================================================
// executeBulkAction — collect-logs special handling
// ===========================================================================

describe("executeBulkAction — collect-logs", () => {
    it("sends single fleet-wide POST, not per-entity", async () => {
        const calls = [];
        mod = await createModule((url, opts) => {
            calls.push({ url, method: opts?.method });
            return Promise.resolve({ job_id: "j-1" });
        });

        // Override: second call is the poll which returns completed.
        let callCount = 0;
        mod = await createModule((url, opts) => {
            callCount++;
            calls.push({ url, method: opts?.method ?? "GET" });
            if (callCount === 1) {
                // Initial POST
                return Promise.resolve({ job_id: "j-1" });
            }
            // Poll response — terminal state
            return Promise.resolve({ status: "completed" });
        });

        await mod.executeBulkAction("collect-logs", [
            { id: "a1", name: "Arm 1" },
            { id: "a2", name: "Arm 2" },
        ]);

        // First call should be the fleet POST
        assert.equal(calls[0].url, "/api/fleet/logs");
        assert.equal(calls[0].method, "POST");
        // Second call should be a poll
        assert.equal(calls[1].url, "/api/fleet/jobs/j-1");
    });

    it("all entities fulfilled when job completes successfully", async () => {
        let callCount = 0;
        mod = await createModule(() => {
            callCount++;
            if (callCount === 1) return Promise.resolve({ job_id: "j-1" });
            return Promise.resolve({ status: "completed" });
        });

        const results = await mod.executeBulkAction("collect-logs", [
            { id: "a1", name: "Arm 1" },
            { id: "a2", name: "Arm 2" },
        ]);

        assert.equal(results.length, 2);
        for (const r of results) {
            assert.equal(r.status, "fulfilled");
        }
    });

    it("all entities rejected when initial POST fails", async () => {
        mod = await createModule(() => Promise.resolve(null));

        const results = await mod.executeBulkAction("collect-logs", [
            { id: "a1", name: "Arm 1" },
        ]);

        assert.equal(results.length, 1);
        assert.equal(results[0].status, "rejected");
        assert.ok(results[0].reason.includes("Failed to start"));
    });

    it("all entities rejected when POST returns no job_id", async () => {
        mod = await createModule(() =>
            Promise.resolve({ message: "accepted" }),
        );

        const results = await mod.executeBulkAction("collect-logs", [
            { id: "a1", name: "Arm 1" },
        ]);

        assert.equal(results.length, 1);
        assert.equal(results[0].status, "rejected");
        assert.ok(results[0].reason.includes("job_id"));
    });

    it("all entities rejected when job ends in 'failed' state", async () => {
        let callCount = 0;
        mod = await createModule(() => {
            callCount++;
            if (callCount === 1) return Promise.resolve({ job_id: "j-2" });
            return Promise.resolve({ status: "failed", error: "disk full" });
        });

        const results = await mod.executeBulkAction("collect-logs", [
            { id: "a1", name: "Arm 1" },
        ]);

        assert.equal(results.length, 1);
        assert.equal(results[0].status, "rejected");
        assert.ok(results[0].reason.includes("failed"));
    });

    it("onProgress reports pending -> running -> fulfilled for successful job", async () => {
        let callCount = 0;
        mod = await createModule(() => {
            callCount++;
            if (callCount === 1) return Promise.resolve({ job_id: "j-3" });
            return Promise.resolve({ status: "complete" });
        });

        const progressLog = [];
        await mod.executeBulkAction(
            "collect-logs",
            [{ id: "a1", name: "Arm 1" }],
            {
                onProgress(entityId, status) {
                    progressLog.push({ entityId, status });
                },
            },
        );

        const statuses = progressLog.map((p) => p.status);
        assert.ok(statuses.includes("pending"));
        assert.ok(statuses.includes("running"));
        assert.ok(statuses.includes("fulfilled"));
    });
});
