#!/usr/bin/env node
/**
 * Unit tests for cachedEntityFetch utility.
 * Run: node --test web_dashboard/frontend/test_cached_fetch.mjs
 *
 * Covers Tasks 3.1, 3.2, 3.3:
 *   3.1 - Cache hit/miss/stale scenarios
 *   3.2 - Abort signal behavior
 *   3.3 - Cache TTL expiry
 */

import { describe, it, beforeEach, afterEach, mock } from "node:test";
import assert from "node:assert/strict";

const {
    cachedEntityFetch,
    clearCache,
    getCacheSize,
    _getCacheMap,
} = await import("./js/utils/cachedFetch.mjs");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let originalFetch;

function mockFetchOk(data) {
    globalThis.fetch = mock.fn(() =>
        Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data }),
        }),
    );
}

function mockFetchFail(status = 500) {
    globalThis.fetch = mock.fn(() =>
        Promise.resolve({
            ok: false,
            status,
            json: () => Promise.resolve({ detail: "error" }),
        }),
    );
}

function mockFetchNetworkError(message = "Network down") {
    globalThis.fetch = mock.fn(() =>
        Promise.reject(new Error(message)),
    );
}

function mockFetchAbortError() {
    const err = new DOMException("The operation was aborted.", "AbortError");
    globalThis.fetch = mock.fn(() => Promise.reject(err));
}

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
    originalFetch = globalThis.fetch;
    clearCache();
});

afterEach(() => {
    globalThis.fetch = originalFetch;
});

// ===========================================================================
// 3.1 — Cache hit/miss/stale scenarios
// ===========================================================================

describe("cachedEntityFetch — cache hit/miss/stale (Task 3.1)", () => {
    it("cache miss triggers fetch and returns { data, stale: false }", async () => {
        const payload = [{ name: "/topic1" }];
        mockFetchOk(payload);

        const result = await cachedEntityFetch("ent1", "ros2/topics");

        assert.ok(result, "result should not be null");
        assert.deepEqual(result.data, payload);
        assert.equal(result.stale, false);
        assert.equal(globalThis.fetch.mock.calls.length, 1);
    });

    it("cache hit returns cached data without fetching", async () => {
        const payload = [{ name: "/node1" }];
        mockFetchOk(payload);

        // First call — populates cache
        await cachedEntityFetch("ent1", "ros2/nodes");
        assert.equal(globalThis.fetch.mock.calls.length, 1);

        // Second call — should hit cache
        const result = await cachedEntityFetch("ent1", "ros2/nodes");
        assert.deepEqual(result.data, payload);
        assert.equal(result.stale, false);
        // fetch should NOT have been called again
        assert.equal(globalThis.fetch.mock.calls.length, 1);
    });

    it("network failure with cache returns { data, stale: true }", async () => {
        const payload = [{ name: "/svc1" }];
        mockFetchOk(payload);

        // Populate cache
        await cachedEntityFetch("ent1", "ros2/services");

        // Expire cache by using bypassCache, then fail
        mockFetchNetworkError("Connection refused");

        const result = await cachedEntityFetch("ent1", "ros2/services", {
            bypassCache: true,
        });

        assert.ok(result, "result should not be null");
        assert.deepEqual(result.data, payload);
        assert.equal(result.stale, true);
    });

    it("network failure without cache returns null", async () => {
        mockFetchNetworkError("Connection refused");

        const result = await cachedEntityFetch("ent2", "ros2/topics");
        assert.equal(result, null);
    });

    it("HTTP error with cache returns stale data", async () => {
        const payload = [{ name: "/param_node" }];
        mockFetchOk(payload);

        await cachedEntityFetch("ent1", "ros2/parameters");

        mockFetchFail(503);
        const result = await cachedEntityFetch("ent1", "ros2/parameters", {
            bypassCache: true,
        });

        assert.ok(result);
        assert.deepEqual(result.data, payload);
        assert.equal(result.stale, true);
    });

    it("HTTP error without cache returns null", async () => {
        mockFetchFail(500);

        const result = await cachedEntityFetch("ent3", "ros2/nodes");
        assert.equal(result, null);
    });

    it("bypassCache forces a fresh fetch even with valid cache", async () => {
        const old = [{ name: "/old" }];
        const fresh = [{ name: "/fresh" }];
        mockFetchOk(old);

        await cachedEntityFetch("ent1", "ros2/topics");
        assert.equal(globalThis.fetch.mock.calls.length, 1);

        mockFetchOk(fresh);
        const result = await cachedEntityFetch("ent1", "ros2/topics", {
            bypassCache: true,
        });

        assert.deepEqual(result.data, fresh);
        assert.equal(result.stale, false);
        assert.equal(globalThis.fetch.mock.calls.length, 1); // new mock, 1 call
    });

    it("unwraps json.data if present, otherwise uses json directly", async () => {
        // Response with .data wrapper
        globalThis.fetch = mock.fn(() =>
            Promise.resolve({
                ok: true,
                json: () => Promise.resolve({ data: [1, 2, 3] }),
            }),
        );

        const r1 = await cachedEntityFetch("ent-a", "ros2/topics");
        assert.deepEqual(r1.data, [1, 2, 3]);

        clearCache();

        // Response WITHOUT .data wrapper
        globalThis.fetch = mock.fn(() =>
            Promise.resolve({
                ok: true,
                json: () => Promise.resolve([4, 5, 6]),
            }),
        );

        const r2 = await cachedEntityFetch("ent-b", "ros2/topics");
        assert.deepEqual(r2.data, [4, 5, 6]);
    });
});

// ===========================================================================
// 3.2 — Abort signal behavior
// ===========================================================================

describe("cachedEntityFetch — abort signal (Task 3.2)", () => {
    it("passes merged signal to fetch", async () => {
        mockFetchOk([]);

        const controller = new AbortController();
        await cachedEntityFetch("ent1", "ros2/nodes", {
            signal: controller.signal,
        });

        const fetchCall = globalThis.fetch.mock.calls[0];
        const fetchOptions = fetchCall.arguments[1];
        assert.ok(fetchOptions.signal, "signal should be passed to fetch");
        // The merged signal should be an AbortSignal instance
        assert.ok(fetchOptions.signal instanceof AbortSignal);
    });

    it("returns null when external signal is already aborted", async () => {
        mockFetchAbortError();

        const controller = new AbortController();
        controller.abort();

        const result = await cachedEntityFetch("ent-abort", "ros2/nodes", {
            signal: controller.signal,
        });

        // Should return null (no cache) since fetch was aborted
        assert.equal(result, null);
    });

    it("returns stale cache when signal aborts mid-flight", async () => {
        const payload = [{ name: "/cached_node" }];
        mockFetchOk(payload);

        // Populate cache
        await cachedEntityFetch("ent1", "ros2/nodes");

        // Now simulate abort error on next fetch
        mockFetchAbortError();

        const controller = new AbortController();
        controller.abort();

        const result = await cachedEntityFetch("ent1", "ros2/nodes", {
            signal: controller.signal,
            bypassCache: true,
        });

        assert.ok(result);
        assert.deepEqual(result.data, payload);
        assert.equal(result.stale, true);
    });

    it("constructs correct URL from entityId and path", async () => {
        mockFetchOk([]);

        await cachedEntityFetch("my-entity", "ros2/topics");

        const url = globalThis.fetch.mock.calls[0].arguments[0];
        assert.equal(url, "/api/entities/my-entity/ros2/topics");
    });

    it("URL-encodes entityId with special characters", async () => {
        mockFetchOk([]);

        await cachedEntityFetch("ent/with spaces", "ros2/nodes");

        const url = globalThis.fetch.mock.calls[0].arguments[0];
        assert.equal(url, "/api/entities/ent%2Fwith%20spaces/ros2/nodes");
    });
});

// ===========================================================================
// 3.3 — Cache TTL expiry
// ===========================================================================

describe("cachedEntityFetch — TTL expiry (Task 3.3)", () => {
    it("serves cache within TTL without re-fetching", async () => {
        const payload = [{ name: "/fast" }];
        mockFetchOk(payload);

        await cachedEntityFetch("ent1", "ros2/topics", { ttlMs: 60000 });
        assert.equal(globalThis.fetch.mock.calls.length, 1);

        // Immediately call again — should be cached
        const result = await cachedEntityFetch("ent1", "ros2/topics", {
            ttlMs: 60000,
        });
        assert.deepEqual(result.data, payload);
        assert.equal(result.stale, false);
        assert.equal(globalThis.fetch.mock.calls.length, 1);
    });

    it("re-fetches after TTL expires", async () => {
        const oldData = [{ name: "/old" }];
        mockFetchOk(oldData);

        // Use a very short TTL
        await cachedEntityFetch("ent-ttl", "ros2/services", { ttlMs: 1 });

        // Wait for TTL to expire
        await new Promise((resolve) => setTimeout(resolve, 10));

        const newData = [{ name: "/new" }];
        mockFetchOk(newData);

        const result = await cachedEntityFetch("ent-ttl", "ros2/services", {
            ttlMs: 1,
        });
        assert.deepEqual(result.data, newData);
        assert.equal(result.stale, false);
    });

    it("bypassCache ignores TTL", async () => {
        const data1 = [{ name: "/v1" }];
        mockFetchOk(data1);

        await cachedEntityFetch("ent1", "ros2/nodes", { ttlMs: 60000 });

        const data2 = [{ name: "/v2" }];
        mockFetchOk(data2);

        // bypassCache should fetch even though TTL hasn't expired
        const result = await cachedEntityFetch("ent1", "ros2/nodes", {
            ttlMs: 60000,
            bypassCache: true,
        });

        assert.deepEqual(result.data, data2);
        assert.equal(result.stale, false);
    });

    it("clearCache removes all entries", async () => {
        mockFetchOk([1]);
        await cachedEntityFetch("a", "ros2/x");
        await cachedEntityFetch("b", "ros2/y", { bypassCache: true });
        assert.equal(getCacheSize(), 2);

        clearCache();
        assert.equal(getCacheSize(), 0);
    });

    it("clearCache with entityId removes only that entity", async () => {
        mockFetchOk([1]);
        await cachedEntityFetch("a", "ros2/x");
        mockFetchOk([2]);
        await cachedEntityFetch("b", "ros2/y");
        assert.equal(getCacheSize(), 2);

        clearCache("a");
        assert.equal(getCacheSize(), 1);

        // "b" entry should still exist
        const cache = _getCacheMap();
        assert.ok(cache.has("b:ros2/y"));
    });
});
