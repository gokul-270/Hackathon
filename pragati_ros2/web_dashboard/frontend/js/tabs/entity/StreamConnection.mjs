/**
 * StreamConnection — dual-transport abstraction for topic echo streaming.
 *
 * Local entity: WebSocket to /ws/entities/{id}/ros2/topics/{name}/echo
 * Remote entity: EventSource (SSE) to /api/entities/{id}/ros2/topics/{name}/echo
 *
 * Both transports present the same chainable API:
 *   createTopicStream(entityId, topicName, opts)
 *     .onMessage(cb)
 *     .connect()        // returns the api itself
 *     .close()
 *
 * SSE streams use ReconnectingEventSource for automatic reconnect with
 * exponential backoff, visibility awareness, and persistent failure handling.
 *
 * @module tabs/entity/StreamConnection
 */

// ---------------------------------------------------------------------------
// ReconnectingEventSource — wraps EventSource with exponential backoff
// ---------------------------------------------------------------------------

/**
 * ReconnectingEventSource wraps the native EventSource with:
 * - Exponential backoff: min(1000 * 2^attempt, 30000) ms — 1s/2s/4s/8s/16s/30s cap
 * - Max 5 reconnect attempts before giving up
 * - Attempt counter reset on successful connection (onopen)
 * - Visibility-aware: pauses timer when tab is hidden, reconnects immediately on visible
 * - Manual close (user navigates away) does NOT trigger reconnect
 * - Reconnect state exposed via onReconnecting / onMaxAttemptsReached callbacks
 *
 * @param {string} url — SSE endpoint URL
 * @param {object} [opts]
 * @param {number} [opts.maxAttempts=5]
 * @param {Function} [opts.onReconnecting] — called with (attempt, delayMs) on each retry schedule
 * @param {Function} [opts.onMaxAttemptsReached] — called when all retries exhausted
 */
export class ReconnectingEventSource {
    /** @type {EventSource|null} */
    #es = null;

    /** @type {number} */
    #attempt = 0;

    /** @type {number|null} retryTimer id */
    #timer = null;

    /** @type {boolean} true if close() was called deliberately */
    #manuallyClosed = false;

    /** @type {boolean} true while waiting for retry */
    #reconnecting = false;

    /** @type {Map<string, Function[]>} event type → callbacks */
    #listeners = new Map();

    /** @type {Function[]} message callbacks */
    #messageCallbacks = [];

    /** @type {Function[]} error callbacks */
    #errorCallbacks = [];

    /** @type {Function|null} */
    #onReconnecting = null;

    /** @type {Function|null} */
    #onMaxAttemptsReached = null;

    /** @type {number} */
    #maxAttempts;

    /** @type {string} */
    #url;

    /** @type {Function} visibility change handler (stored for removal) */
    #visibilityHandler = null;

    constructor(url, { maxAttempts = 5, onReconnecting = null, onMaxAttemptsReached = null } = {}) {
        this.#url = url;
        this.#maxAttempts = maxAttempts;
        this.#onReconnecting = onReconnecting;
        this.#onMaxAttemptsReached = onMaxAttemptsReached;

        this.#visibilityHandler = () => {
            if (document.visibilityState === "visible" && this.#reconnecting) {
                // Tab became visible while waiting to reconnect — reconnect immediately
                this.#cancelTimer();
                this.#doConnect();
            }
        };
        document.addEventListener("visibilitychange", this.#visibilityHandler);

        this.#doConnect();
    }

    /** Backoff delay in ms for a given attempt index. */
    static #backoffMs(attempt) {
        return Math.min(1000 * Math.pow(2, attempt), 30000);
    }

    #doConnect() {
        this.#reconnecting = false;

        const es = new EventSource(this.#url);
        this.#es = es;

        es.onopen = () => {
            // Successful connection — reset attempt counter
            this.#attempt = 0;
        };

        es.onmessage = (event) => {
            for (const cb of this.#messageCallbacks) {
                cb(event);
            }
        };

        es.onerror = (event) => {
            if (this.#manuallyClosed) {
                // User navigated away — do not reconnect
                return;
            }

            // Close the failed EventSource (suppress its own reconnect)
            es.close();
            this.#es = null;

            if (this.#attempt >= this.#maxAttempts) {
                // All retries exhausted
                for (const cb of this.#errorCallbacks) {
                    cb(event);
                }
                if (this.#onMaxAttemptsReached) {
                    this.#onMaxAttemptsReached();
                }
                return;
            }

            const delayMs = ReconnectingEventSource.#backoffMs(this.#attempt);
            this.#attempt++;
            this.#reconnecting = true;

            if (this.#onReconnecting) {
                this.#onReconnecting(this.#attempt, delayMs);
            }

            if (document.visibilityState === "hidden") {
                // Tab is hidden — wait for visibility event instead of scheduling timer
                return;
            }

            this.#timer = setTimeout(() => {
                this.#timer = null;
                if (!this.#manuallyClosed) {
                    this.#doConnect();
                }
            }, delayMs);
        };

        // Re-attach any custom event listeners (e.g. "message" type is handled above)
        for (const [type, cbs] of this.#listeners) {
            for (const cb of cbs) {
                es.addEventListener(type, cb);
            }
        }
    }

    #cancelTimer() {
        if (this.#timer !== null) {
            clearTimeout(this.#timer);
            this.#timer = null;
        }
    }

    /**
     * Register a callback for EventSource "message" events.
     * @param {Function} cb
     */
    addEventListener(type, cb) {
        if (type === "message") {
            this.#messageCallbacks.push(cb);
        } else {
            if (!this.#listeners.has(type)) {
                this.#listeners.set(type, []);
            }
            this.#listeners.get(type).push(cb);
            if (this.#es) {
                this.#es.addEventListener(type, cb);
            }
        }
    }

    /**
     * Remove a previously-registered callback.
     * @param {string} type
     * @param {Function} cb
     */
    removeEventListener(type, cb) {
        if (type === "message") {
            const idx = this.#messageCallbacks.indexOf(cb);
            if (idx !== -1) this.#messageCallbacks.splice(idx, 1);
        } else {
            const cbs = this.#listeners.get(type);
            if (cbs) {
                const idx = cbs.indexOf(cb);
                if (idx !== -1) cbs.splice(idx, 1);
            }
            if (this.#es) {
                this.#es.removeEventListener(type, cb);
            }
        }
    }

    /**
     * Add a callback for error events (fires only on max-attempts exhaustion).
     * @param {Function} cb
     */
    addErrorCallback(cb) {
        this.#errorCallbacks.push(cb);
    }

    /**
     * Close the stream permanently. No reconnect will occur after this call.
     */
    close() {
        this.#manuallyClosed = true;
        this.#cancelTimer();
        this.#reconnecting = false;
        if (this.#es) {
            this.#es.close();
            this.#es = null;
        }
        if (this.#visibilityHandler) {
            document.removeEventListener("visibilitychange", this.#visibilityHandler);
            this.#visibilityHandler = null;
        }
    }

    /** @returns {boolean} true while waiting to retry */
    get isReconnecting() {
        return this.#reconnecting;
    }
}

// ---------------------------------------------------------------------------
// Topic echo stream
// ---------------------------------------------------------------------------

/**
 * Create a topic-echo stream for the given entity + topic.
 *
 * @param {string} entityId
 * @param {string} topicName
 * @param {object}  [opts]
 * @param {string}  [opts.entitySource="local"]
 * @param {number}  [opts.hz=10]  Decimation rate in Hz
 * @param {Function} [opts.onReconnecting]  Called with (attempt, delayMs) on retry schedule
 * @param {Function} [opts.onDisconnected]  Called after max attempts exhausted
 * @returns {{onMessage: Function, connect: Function, close: Function}}
 */
export function createTopicStream(
    entityId,
    topicName,
    { entitySource = "local", hz = 10, onReconnecting = null, onDisconnected = null } = {},
) {
    let connection = null;
    const callbacks = [];

    function handleMsg(event) {
        try {
            const data =
                typeof event.data === "string"
                    ? JSON.parse(event.data)
                    : event.data;
            for (let i = 0; i < callbacks.length; i++) {
                callbacks[i](data);
            }
        } catch (err) {
            console.error("[StreamConnection] Failed to parse message:", err);
        }
    }

    function onMessage(cb) {
        callbacks.push(cb);
        return api;
    }

    function close() {
        if (connection) {
            if (typeof connection.close === "function") {
                connection.close();
            }
            if (typeof connection.removeEventListener === "function") {
                connection.removeEventListener("message", handleMsg);
            }
            connection = null;
        }
    }

    function connect() {
        // Close any existing connection first
        close();

        const encodedTopic = encodeURIComponent(topicName);
        const url =
            `/api/entities/${entityId}/ros2/topics/` +
            `${encodedTopic}/echo?hz=${hz}`;

        // Use ReconnectingEventSource for both local and remote to get auto-reconnect
        connection = new ReconnectingEventSource(url, {
            onReconnecting,
            onMaxAttemptsReached: onDisconnected,
        });
        connection.addEventListener("message", handleMsg);

        return api;
    }

    const api = { onMessage, close, connect };
    return api;
}

// ---------------------------------------------------------------------------
// Log tail stream
// ---------------------------------------------------------------------------

/**
 * Create a log-tail stream for the given entity + log name.
 *
 * Supports two modes via the `mode` option:
 * - "file" (default): streams from /api/entities/{id}/logs/{name}/tail
 * - "journal": streams from /api/entities/{id}/logs/journal/{unit}
 *
 * Optional `since` and `until` query parameters can be passed to filter
 * journalctl output by time range (ISO 8601 or relative strings).
 *
 * The handleMsg callback tries JSON.parse first; on failure it passes
 * the raw text string directly to the onMessage callback so that file-tail
 * SSE events (which are plain text, not JSON) are not silently dropped.
 *
 * @param {string} entityId
 * @param {string} logName   Log file path (mode=file) or systemd unit name (mode=journal)
 * @param {object}  [opts]
 * @param {string}  [opts.mode="file"]  "file" or "journal"
 * @param {string|null}  [opts.since=null]  Start time filter (ISO or relative)
 * @param {string|null}  [opts.until=null]  End time filter (ISO or relative)
 * @param {Function} [opts.onReconnecting]  Called with (attempt, delayMs) on retry schedule
 * @param {Function} [opts.onDisconnected]  Called after max attempts exhausted
 * @returns {{onMessage: Function, onError: Function, connect: Function, close: Function}}
 */
export function createLogStream(
    entityId,
    logName,
    { mode = "file", since = null, until = null, onReconnecting = null, onDisconnected = null } = {},
) {
    let connection = null;
    const callbacks = [];

    function handleMsg(event) {
        let data;
        try {
            data =
                typeof event.data === "string"
                    ? JSON.parse(event.data)
                    : event.data;
        } catch {
            // Non-JSON data (e.g. raw text from file tail) — pass through
            // as a plain string so parseLogEntry can handle it.
            data = event.data;
        }
        for (let i = 0; i < callbacks.length; i++) {
            callbacks[i](data);
        }
    }

    function onMessage(cb) {
        callbacks.push(cb);
        return api;
    }

    const errorCallbacks = [];

    function onError(cb) {
        errorCallbacks.push(cb);
        return api;
    }

    function close() {
        if (connection) {
            if (typeof connection.close === "function") {
                connection.close();
            }
            connection = null;
        }
    }

    function connect() {
        close();

        let url;
        if (mode === "journal") {
            const encodedUnit = encodeURIComponent(logName);
            url = `/api/entities/${entityId}/logs/journal/${encodedUnit}`;
        } else {
            const encodedLog = encodeURIComponent(logName);
            url = `/api/entities/${entityId}/logs/${encodedLog}/tail`;
        }

        // Append time filter query parameters if provided
        const params = new URLSearchParams();
        if (since) params.set("since", since);
        if (until) params.set("until", until);
        const qs = params.toString();
        if (qs) url += (url.includes("?") ? "&" : "?") + qs;

        // Use ReconnectingEventSource for auto-reconnect with exponential backoff
        connection = new ReconnectingEventSource(url, {
            onReconnecting,
            onMaxAttemptsReached: () => {
                if (onDisconnected) {
                    onDisconnected();
                }
                for (let i = 0; i < errorCallbacks.length; i++) {
                    errorCallbacks[i](new Event("error"));
                }
            },
        });
        connection.addEventListener("message", handleMsg);

        return api;
    }

    const api = { onMessage, onError, close, connect };
    return api;
}
