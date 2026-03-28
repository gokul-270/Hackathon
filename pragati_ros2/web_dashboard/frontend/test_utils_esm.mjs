#!/usr/bin/env node
/**
 * Unit tests for shared utility functions (ES module version).
 * Run: node --test web_dashboard/frontend/test_utils_esm.mjs
 */

import { describe, it, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";

// We import from the ES module directly. Since utils.js uses only standard
// JS (no DOM APIs except fetch in safeFetch), it runs in Node.js natively.

// Dynamic import so we can test the module cleanly
const {
    escapeHtml,
    formatBytes,
    formatDuration,
    formatDate,
    safeFetch,
    convertToCSV,
} = await import("./js/utils.js");

// ===========================================================================
// escapeHtml
// ===========================================================================
describe("escapeHtml", () => {
    it("returns empty string for null", () => {
        assert.equal(escapeHtml(null), "");
    });

    it("returns empty string for undefined", () => {
        assert.equal(escapeHtml(undefined), "");
    });

    it("returns empty string for empty string", () => {
        assert.equal(escapeHtml(""), "");
    });

    it("escapes HTML special characters", () => {
        assert.equal(
            escapeHtml('<script>alert("xss")</script>'),
            "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;"
        );
    });

    it("escapes ampersand", () => {
        assert.equal(escapeHtml("foo & bar"), "foo &amp; bar");
    });

    it("escapes single quotes", () => {
        assert.equal(escapeHtml("it's"), "it&#39;s");
    });

    it("passes through safe strings unchanged", () => {
        assert.equal(escapeHtml("hello world"), "hello world");
    });

    it("coerces numbers to string", () => {
        assert.equal(escapeHtml(42), "42");
    });
});

// ===========================================================================
// formatBytes
// ===========================================================================
describe("formatBytes", () => {
    it("returns '--' for null", () => {
        assert.equal(formatBytes(null), "--");
    });

    it("returns '--' for undefined", () => {
        assert.equal(formatBytes(undefined), "--");
    });

    it("returns '--' for NaN", () => {
        assert.equal(formatBytes(NaN), "--");
    });

    it("returns '0 B' for zero", () => {
        assert.equal(formatBytes(0), "0 B");
    });

    it("formats bytes", () => {
        assert.equal(formatBytes(500), "500 B");
    });

    it("formats kilobytes", () => {
        assert.equal(formatBytes(1024), "1.0 KB");
    });

    it("formats megabytes", () => {
        assert.equal(formatBytes(1048576), "1.0 MB");
    });

    it("formats gigabytes", () => {
        assert.equal(formatBytes(1073741824), "1.0 GB");
    });

    it("formats with one decimal", () => {
        assert.equal(formatBytes(1536), "1.5 KB");
    });
});

// ===========================================================================
// formatDuration
// ===========================================================================
describe("formatDuration", () => {
    it("returns '--' for null", () => {
        assert.equal(formatDuration(null), "--");
    });

    it("returns '--' for undefined", () => {
        assert.equal(formatDuration(undefined), "--");
    });

    it("returns '--' for NaN", () => {
        assert.equal(formatDuration(NaN), "--");
    });

    it("formats seconds only", () => {
        assert.equal(formatDuration(45), "45s");
    });

    it("formats minutes and seconds", () => {
        assert.equal(formatDuration(125), "2m 5s");
    });

    it("formats hours, minutes, and seconds", () => {
        assert.equal(formatDuration(3661), "1h 1m 1s");
    });

    it("formats zero seconds", () => {
        assert.equal(formatDuration(0), "0s");
    });

    it("floors fractional seconds", () => {
        assert.equal(formatDuration(1.9), "1s");
    });
});

// ===========================================================================
// formatDate
// ===========================================================================
describe("formatDate", () => {
    it("returns '--' for null", () => {
        assert.equal(formatDate(null), "--");
    });

    it("returns '--' for undefined", () => {
        assert.equal(formatDate(undefined), "--");
    });

    it("returns '--' for empty string", () => {
        assert.equal(formatDate(""), "--");
    });

    it("returns '--' for invalid date", () => {
        assert.equal(formatDate("not-a-date"), "--");
    });

    it("formats a valid ISO date string", () => {
        const result = formatDate("2025-01-15T10:30:00Z");
        // Result format depends on locale, but should contain the date parts
        assert.ok(result.includes("Jan"), `Expected 'Jan' in '${result}'`);
        assert.ok(result.includes("15"), `Expected '15' in '${result}'`);
        assert.ok(result.includes("2025"), `Expected '2025' in '${result}'`);
    });
});

// ===========================================================================
// safeFetch
// ===========================================================================
describe("safeFetch", () => {
    let originalFetch;

    beforeEach(() => {
        originalFetch = globalThis.fetch;
    });

    it("returns parsed JSON on success", async () => {
        const mockData = { status: "ok", count: 42 };
        globalThis.fetch = mock.fn(() =>
            Promise.resolve({
                ok: true,
                json: () => Promise.resolve(mockData),
            })
        );

        const result = await safeFetch("/api/test");
        assert.deepEqual(result, mockData);

        globalThis.fetch = originalFetch;
    });

    it("returns null on HTTP error", async () => {
        globalThis.fetch = mock.fn(() =>
            Promise.resolve({
                ok: false,
                status: 500,
            })
        );

        const result = await safeFetch("/api/test");
        assert.equal(result, null);

        globalThis.fetch = originalFetch;
    });

    it("returns null on network error", async () => {
        globalThis.fetch = mock.fn(() =>
            Promise.reject(new Error("Network down"))
        );

        const result = await safeFetch("/api/test");
        assert.equal(result, null);

        globalThis.fetch = originalFetch;
    });

    it("returns null on JSON parse error", async () => {
        globalThis.fetch = mock.fn(() =>
            Promise.resolve({
                ok: true,
                json: () => Promise.reject(new SyntaxError("Unexpected token")),
            })
        );

        const result = await safeFetch("/api/test");
        assert.equal(result, null);

        globalThis.fetch = originalFetch;
    });

    it("passes options through to fetch", async () => {
        const mockFn = mock.fn(() =>
            Promise.resolve({
                ok: true,
                json: () => Promise.resolve({}),
            })
        );
        globalThis.fetch = mockFn;

        const opts = { method: "POST", body: "{}" };
        await safeFetch("/api/test", opts);
        assert.equal(mockFn.mock.calls[0].arguments[1], opts);

        globalThis.fetch = originalFetch;
    });
});

// ===========================================================================
// convertToCSV
// ===========================================================================
describe("convertToCSV", () => {
    it("returns empty string for null", () => {
        assert.equal(convertToCSV(null), "");
    });

    it("returns empty string for empty array", () => {
        assert.equal(convertToCSV([]), "");
    });

    it("converts single row", () => {
        const result = convertToCSV([{ name: "a", value: 1 }]);
        assert.equal(result, "name,value\na,1");
    });

    it("converts multiple rows", () => {
        const result = convertToCSV([
            { x: 1, y: 2 },
            { x: 3, y: 4 },
        ]);
        assert.equal(result, "x,y\n1,2\n3,4");
    });

    it("escapes values with commas", () => {
        const result = convertToCSV([{ name: "a,b" }]);
        assert.equal(result, 'name\n"a,b"');
    });

    it("escapes values with quotes", () => {
        const result = convertToCSV([{ name: 'say "hi"' }]);
        assert.equal(result, 'name\n"say ""hi"""');
    });

    it("handles null values", () => {
        const result = convertToCSV([{ name: null }]);
        assert.equal(result, "name\n");
    });
});
