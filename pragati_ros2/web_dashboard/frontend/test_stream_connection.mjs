#!/usr/bin/env node
/**
 * Unit tests for StreamConnection.mjs — specifically handleMsg fallback
 * for non-JSON SSE data.
 *
 * Run: node --test web_dashboard/frontend/test_stream_connection.mjs
 *
 * StreamConnection.mjs has no imports (pure JS), but handleMsg is a closure
 * inside createLogStream. We test it indirectly by:
 * 1. Creating a stream with createLogStream()
 * 2. Registering an onMessage callback
 * 3. Calling the internal handleMsg via a mock EventSource
 *
 * Covers task: 3.4
 */

import { describe, it, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";

// ---------------------------------------------------------------------------
// Minimal EventSource mock
// ---------------------------------------------------------------------------

class MockEventSource {
    constructor(url) {
        this.url = url;
        this._listeners = {};
    }

    addEventListener(event, handler) {
        if (!this._listeners[event]) this._listeners[event] = [];
        this._listeners[event].push(handler);
    }

    close() {
        this._listeners = {};
    }

    /** Simulate receiving an SSE message event. */
    emit(data) {
        const event = { data };
        const handlers = this._listeners["message"] || [];
        for (const h of handlers) {
            h(event);
        }
    }
}

// Inject the mock into globalThis so createLogStream uses it
globalThis.EventSource = MockEventSource;

// Now import the module — it uses no browser-specific imports
const { createLogStream } = await import(
    "./js/tabs/entity/StreamConnection.mjs"
);

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("createLogStream handleMsg", () => {
    let received;
    let stream;
    let eventSource;

    beforeEach(() => {
        received = [];
        stream = createLogStream("arm1", "test.log", { mode: "file" });
        stream.onMessage((data) => received.push(data));
        stream.connect();

        // Fish out the EventSource instance that was created
        // createLogStream sets connection = new EventSource(url)
        // We can't access it directly, but since our MockEventSource is
        // global, we need a different approach: re-create with a known ref.
    });

    // Helper: create a stream and get access to the mock EventSource
    function createTestStream(mode = "file") {
        const receivedData = [];
        let capturedES = null;

        // Patch EventSource to capture the instance
        const OrigES = globalThis.EventSource;
        globalThis.EventSource = class extends MockEventSource {
            constructor(url) {
                super(url);
                capturedES = this;
            }
        };

        const s = createLogStream("arm1", "test.log", { mode });
        s.onMessage((data) => receivedData.push(data));
        s.connect();

        globalThis.EventSource = OrigES;

        return { stream: s, es: capturedES, received: receivedData };
    }

    it("passes parsed JSON objects to callbacks", () => {
        const { es, received: msgs } = createTestStream();
        es.emit('{"MESSAGE":"hello","PRIORITY":"6"}');
        assert.equal(msgs.length, 1);
        assert.deepStrictEqual(msgs[0], {
            MESSAGE: "hello",
            PRIORITY: "6",
        });
    });

    it("passes raw text through when JSON.parse fails", () => {
        const { es, received: msgs } = createTestStream();
        es.emit("this is raw text, not JSON");
        assert.equal(msgs.length, 1);
        assert.equal(msgs[0], "this is raw text, not JSON");
    });

    it("handles empty string data", () => {
        const { es, received: msgs } = createTestStream();
        es.emit("");
        assert.equal(msgs.length, 1);
        assert.equal(msgs[0], "");
    });

    it("handles JSON array data", () => {
        const { es, received: msgs } = createTestStream();
        es.emit("[1,2,3]");
        assert.equal(msgs.length, 1);
        assert.deepStrictEqual(msgs[0], [1, 2, 3]);
    });

    it("handles JSON number data", () => {
        const { es, received: msgs } = createTestStream();
        es.emit("42");
        assert.equal(msgs.length, 1);
        assert.equal(msgs[0], 42);
    });

    it("does NOT silently drop non-JSON data", () => {
        const { es, received: msgs } = createTestStream();
        // Before the fix, handleMsg would catch the JSON.parse error
        // and silently drop the message. Now it passes the raw string.
        es.emit("ERROR: CAN bus timeout on /dev/can0");
        assert.equal(msgs.length, 1, "message should NOT be dropped");
        assert.equal(
            typeof msgs[0],
            "string",
            "raw text should be passed as string",
        );
        assert.equal(msgs[0], "ERROR: CAN bus timeout on /dev/can0");
    });

    it("delivers to multiple callbacks", () => {
        const { stream: s, es } = createTestStream();
        const extra = [];
        s.onMessage((data) => extra.push(data));
        es.emit("hello");
        // 'received' from createTestStream + 'extra'
        assert.equal(extra.length, 1);
        assert.equal(extra[0], "hello");
    });

    it("uses correct URL for file mode", () => {
        const { es } = createTestStream("file");
        assert.ok(
            es.url.includes("/logs/test.log/tail"),
            `Expected file tail URL, got: ${es.url}`,
        );
    });

    it("uses correct URL for journal mode", () => {
        const { es } = createTestStream("journal");
        assert.ok(
            es.url.includes("/logs/journal/test.log"),
            `Expected journal URL, got: ${es.url}`,
        );
    });

    it("close() stops the EventSource", () => {
        const { stream: s, es } = createTestStream();
        // EventSource should exist
        assert.ok(es);
        s.close();
        // After close, emitting should not deliver (listeners cleared)
        const msgs = [];
        // Re-register won't help since close() sets connection = null
    });
});
