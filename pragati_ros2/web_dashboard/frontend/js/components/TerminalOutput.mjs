/**
 * TerminalOutput — Preact component for rendering ANSI-colored terminal
 * output with SSE streaming.
 *
 * Features:
 * - ANSI SGR escape code parsing (colors, bold, dim, italic, underline)
 * - Auto-scroll with scroll-lock (pauses when user scrolls up)
 * - SSE EventSource connection for streaming operation output
 * - Line buffer with configurable maxLines cap
 *
 * @module components/TerminalOutput
 */
import { h } from "preact";
import { useState, useEffect, useRef, useCallback } from "preact/hooks";
import { html } from "htm/preact";

// ---------------------------------------------------------------------------
// ANSI color maps
// ---------------------------------------------------------------------------

/** Standard foreground colors (SGR 30-37). */
const FG_COLORS = {
    30: "#000000", // black
    31: "#cd3131", // red
    32: "#0dbc79", // green
    33: "#e5e510", // yellow
    34: "#2472c8", // blue
    35: "#bc3fbc", // magenta
    36: "#11a8cd", // cyan
    37: "#e5e5e5", // white
};

/** Bright foreground colors (SGR 90-97). */
const FG_BRIGHT = {
    90: "#666666", // bright black (gray)
    91: "#f14c4c", // bright red
    92: "#23d18b", // bright green
    93: "#f5f543", // bright yellow
    94: "#3b8eea", // bright blue
    95: "#d670d6", // bright magenta
    96: "#29b8db", // bright cyan
    97: "#ffffff", // bright white
};

/** Standard background colors (SGR 40-47). */
const BG_COLORS = {
    40: "#000000",
    41: "#cd3131",
    42: "#0dbc79",
    43: "#e5e510",
    44: "#2472c8",
    45: "#bc3fbc",
    46: "#11a8cd",
    47: "#e5e5e5",
};

/** Bright background colors (SGR 100-107). */
const BG_BRIGHT = {
    100: "#666666",
    101: "#f14c4c",
    102: "#23d18b",
    103: "#f5f543",
    104: "#3b8eea",
    105: "#d670d6",
    106: "#29b8db",
    107: "#ffffff",
};

// ---------------------------------------------------------------------------
// ANSI SGR parser
// ---------------------------------------------------------------------------

/**
 * Regex matching a single ANSI CSI escape sequence.
 * Captures the parameter bytes (digits and semicolons) between ESC[ and the
 * final byte. Non-CSI escape sequences are matched by the fallback branch
 * and stripped.
 */
const ANSI_RE = /\x1b\[([0-9;]*)([A-Za-z])|\x1b[^[]\S*/g;

/**
 * Parse an ANSI-encoded string and return an array of { text, style } spans.
 *
 * Supported SGR codes:
 * - 0: reset all
 * - 1: bold, 2: dim, 3: italic, 4: underline
 * - 30-37 / 90-97: foreground color
 * - 40-47 / 100-107: background color
 *
 * @param {string} line - Raw line potentially containing ANSI escapes
 * @returns {Array<{ text: string, style: object }>}
 */
function parseAnsi(line) {
    const spans = [];
    let currentStyle = {};
    let lastIndex = 0;

    ANSI_RE.lastIndex = 0;
    let match;

    while ((match = ANSI_RE.exec(line)) !== null) {
        // Push any text before this escape
        if (match.index > lastIndex) {
            const text = line.slice(lastIndex, match.index);
            if (text) {
                spans.push({ text, style: { ...currentStyle } });
            }
        }
        lastIndex = ANSI_RE.lastIndex;

        // Non-SGR sequences (final byte !== 'm') are stripped silently
        if (match[2] !== "m") continue;

        const params = match[1];
        if (!params || params === "0") {
            // Reset
            currentStyle = {};
            continue;
        }

        const codes = params.split(";");
        for (let i = 0; i < codes.length; i++) {
            const code = parseInt(codes[i], 10);
            if (isNaN(code) || code === 0) {
                currentStyle = {};
            } else if (code === 1) {
                currentStyle.fontWeight = "bold";
            } else if (code === 2) {
                currentStyle.opacity = "0.7";
            } else if (code === 3) {
                currentStyle.fontStyle = "italic";
            } else if (code === 4) {
                currentStyle.textDecoration = "underline";
            } else if (FG_COLORS[code]) {
                currentStyle.color = FG_COLORS[code];
            } else if (FG_BRIGHT[code]) {
                currentStyle.color = FG_BRIGHT[code];
            } else if (BG_COLORS[code]) {
                currentStyle.backgroundColor = BG_COLORS[code];
            } else if (BG_BRIGHT[code]) {
                currentStyle.backgroundColor = BG_BRIGHT[code];
            }
            // Unrecognized codes are silently ignored
        }
    }

    // Remaining text after last escape
    if (lastIndex < line.length) {
        const text = line.slice(lastIndex);
        if (text) {
            spans.push({ text, style: { ...currentStyle } });
        }
    }

    // If line was empty or only escapes, still return at least one span
    if (spans.length === 0) {
        spans.push({ text: "", style: {} });
    }

    return spans;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const CONTAINER_STYLE = {
    backgroundColor: "var(--color-bg-primary)",
    color: "var(--color-text-primary)",
    fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', 'Monaco', monospace",
    fontSize: "13px",
    lineHeight: "1.4",
    padding: "8px 12px",
    borderRadius: "var(--radius-sm)",
    overflow: "auto",
    position: "relative",
    height: "400px",
    whiteSpace: "pre-wrap",
    wordBreak: "break-all",
    border: "1px solid var(--color-border)",
};

const LINE_STYLE = {
    minHeight: "1.4em",
};

const STDERR_LINE_STYLE = {
    ...LINE_STYLE,
    color: "var(--color-error)",
};

const SCROLL_BTN_STYLE = {
    position: "absolute",
    bottom: "12px",
    right: "12px",
    padding: "4px 12px",
    backgroundColor: "var(--color-accent)",
    color: "#ffffff",
    border: "none",
    borderRadius: "12px",
    cursor: "pointer",
    fontSize: "12px",
    fontFamily: "inherit",
    boxShadow: "0 2px 6px rgba(0,0,0,0.4)",
    zIndex: "10",
    opacity: "0.9",
    transition: "opacity 150ms",
};

const WRAPPER_STYLE = {
    position: "relative",
};

const STATUS_LINE_STYLE = {
    padding: "4px 12px",
    fontSize: "12px",
    color: "var(--color-text-secondary)",
    backgroundColor: "var(--color-bg-primary)",
    borderTop: "1px solid var(--color-border)",
    borderBottomLeftRadius: "var(--radius-sm)",
    borderBottomRightRadius: "var(--radius-sm)",
    fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
};

// ---------------------------------------------------------------------------
// TerminalOutput component
// ---------------------------------------------------------------------------

/**
 * Renders ANSI-colored terminal output with SSE streaming support.
 *
 * @param {object} props
 * @param {string|null} props.operationId - Operation ID to stream; null = no connection
 * @param {(event: object) => void} [props.onEvent] - Callback for lifecycle events
 * @param {number} [props.maxLines=5000] - Maximum lines to retain in buffer
 * @returns {import('preact').VNode}
 */
function TerminalOutput({ operationId, onEvent, maxLines = 5000 }) {
    const [lines, setLines] = useState([]);
    const [scrollLocked, setScrollLocked] = useState(false);
    const [connectionStatus, setConnectionStatus] = useState("idle");

    const containerRef = useRef(null);
    const autoScrollRef = useRef(true);
    const onEventRef = useRef(onEvent);
    const maxLinesRef = useRef(maxLines);

    // Keep refs current without triggering reconnects
    useEffect(() => {
        onEventRef.current = onEvent;
    }, [onEvent]);

    useEffect(() => {
        maxLinesRef.current = maxLines;
    }, [maxLines]);

    // -------------------------------------------------------------------
    // Scroll tracking
    // -------------------------------------------------------------------

    /**
     * Determine whether the container is scrolled to the bottom
     * (within a small tolerance).
     */
    const isAtBottom = useCallback(() => {
        const el = containerRef.current;
        if (!el) return true;
        return el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    }, []);

    /**
     * Handle user scroll events. If the user scrolls away from the bottom,
     * pause auto-scroll. If they scroll back to the bottom, resume.
     */
    const onScroll = useCallback(() => {
        const atBottom = isAtBottom();
        autoScrollRef.current = atBottom;
        setScrollLocked(!atBottom);
    }, [isAtBottom]);

    /**
     * Programmatically scroll to the bottom and resume auto-scroll.
     */
    const scrollToBottom = useCallback(() => {
        const el = containerRef.current;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
        autoScrollRef.current = true;
        setScrollLocked(false);
    }, []);

    // -------------------------------------------------------------------
    // Auto-scroll on new lines
    // -------------------------------------------------------------------

    useEffect(() => {
        if (autoScrollRef.current && containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [lines.length]);

    // -------------------------------------------------------------------
    // Append helper
    // -------------------------------------------------------------------

    /**
     * Append one or more lines to the buffer, respecting maxLines cap.
     * @param {Array<{ text: string, stream: string }>} newLines
     */
    const appendLines = useCallback((newLines) => {
        setLines((prev) => {
            const combined = prev.concat(newLines);
            const limit = maxLinesRef.current;
            if (combined.length > limit) {
                return combined.slice(combined.length - limit);
            }
            return combined;
        });
    }, []);

    // -------------------------------------------------------------------
    // SSE EventSource connection
    // -------------------------------------------------------------------

    useEffect(() => {
        if (!operationId) {
            setConnectionStatus("idle");
            return;
        }

        setConnectionStatus("connecting");

        const url = `/api/operations/${encodeURIComponent(operationId)}/stream`;
        let es;
        let closed = false;

        try {
            es = new EventSource(url);
        } catch (err) {
            console.error("[TerminalOutput] Failed to create EventSource:", err);
            setConnectionStatus("error");
            return;
        }

        es.onopen = () => {
            if (!closed) {
                setConnectionStatus("connected");
            }
        };

        es.onmessage = (event) => {
            if (closed) return;

            let data;
            try {
                data = JSON.parse(event.data);
            } catch (_e) {
                // Non-JSON message — treat as plain text output
                appendLines([{ text: event.data, stream: "stdout" }]);
                return;
            }

            const eventType = data.event;

            switch (eventType) {
                case "output":
                    appendLines([{
                        text: data.line || "",
                        stream: data.stream || "stdout",
                    }]);
                    break;

                case "start":
                    appendLines([{
                        text: `--- Starting: ${data.target || "unknown"} ---`,
                        stream: "stdout",
                    }]);
                    if (onEventRef.current) {
                        onEventRef.current(data);
                    }
                    break;

                case "complete":
                    appendLines([{
                        text: `--- Complete: ${data.target || "unknown"} `
                            + `(exit code: ${data.exit_code}) ---`,
                        stream: data.exit_code === 0 ? "stdout" : "stderr",
                    }]);
                    if (onEventRef.current) {
                        onEventRef.current(data);
                    }
                    break;

                case "timeout":
                    appendLines([{
                        text: `--- Timeout: ${data.target || "unknown"} ---`,
                        stream: "stderr",
                    }]);
                    if (onEventRef.current) {
                        onEventRef.current(data);
                    }
                    break;

                case "error":
                    appendLines([{
                        text: `--- Error: ${data.target || "unknown"}: `
                            + `${data.detail || "unknown error"} ---`,
                        stream: "stderr",
                    }]);
                    if (onEventRef.current) {
                        onEventRef.current(data);
                    }
                    break;

                case "operation_complete":
                    appendLines([{
                        text: "--- Operation complete ---",
                        stream: "stdout",
                    }]);
                    setConnectionStatus("complete");
                    if (onEventRef.current) {
                        onEventRef.current(data);
                    }
                    // Server should close the stream, but close our end too
                    es.close();
                    break;

                default:
                    // Forward any unrecognized event types to the callback
                    if (onEventRef.current) {
                        onEventRef.current(data);
                    }
                    break;
            }
        };

        es.onerror = () => {
            if (closed) return;
            // EventSource will auto-reconnect for transient errors.
            // If readyState is CLOSED, the server ended the stream.
            if (es.readyState === EventSource.CLOSED) {
                setConnectionStatus((prev) =>
                    prev === "complete" ? "complete" : "disconnected"
                );
            } else {
                setConnectionStatus("reconnecting");
            }
        };

        return () => {
            closed = true;
            es.close();
        };
    }, [operationId, appendLines]);

    // -------------------------------------------------------------------
    // Render a single line with parsed ANSI spans
    // -------------------------------------------------------------------

    const renderLine = useCallback((line, index) => {
        const isStderr = line.stream === "stderr";
        const spans = parseAnsi(line.text);
        const baseStyle = isStderr ? STDERR_LINE_STYLE : LINE_STYLE;

        // Fast path: single span with no ANSI styling
        if (spans.length === 1 && Object.keys(spans[0].style).length === 0) {
            return html`
                <div key=${index} style=${baseStyle}>${spans[0].text}</div>
            `;
        }

        return html`
            <div key=${index} style=${baseStyle}>
                ${spans.map(
                    (span, si) =>
                        Object.keys(span.style).length > 0
                            ? html`<span key=${si} style=${span.style}>${span.text}</span>`
                            : span.text
                )}
            </div>
        `;
    }, []);

    // -------------------------------------------------------------------
    // Render
    // -------------------------------------------------------------------

    const showScrollBtn = scrollLocked && lines.length > 0;

    return html`
        <div style=${WRAPPER_STYLE}>
            <div
                ref=${containerRef}
                style=${CONTAINER_STYLE}
                onScroll=${onScroll}
            >
                ${lines.length === 0 && connectionStatus === "idle"
                    ? html`<div style=${{ color: "var(--color-text-muted)", fontStyle: "italic" }}>
                          No output yet
                      </div>`
                    : lines.length === 0 && connectionStatus === "connecting"
                      ? html`<div style=${{ color: "var(--color-text-muted)", fontStyle: "italic" }}>
                            Connecting...
                        </div>`
                      : lines.map(renderLine)}
            </div>
            ${showScrollBtn && html`
                <button
                    style=${SCROLL_BTN_STYLE}
                    onClick=${scrollToBottom}
                    onMouseOver=${(e) => { e.currentTarget.style.opacity = "1"; }}
                    onMouseOut=${(e) => { e.currentTarget.style.opacity = "0.9"; }}
                >
                    Scroll to bottom
                </button>
            `}
            ${connectionStatus !== "idle" && html`
                <div style=${STATUS_LINE_STYLE}>
                    ${connectionStatus === "connecting" && "Connecting..."}
                    ${connectionStatus === "connected" && "Connected — streaming"}
                    ${connectionStatus === "reconnecting" && "Reconnecting..."}
                    ${connectionStatus === "disconnected" && "Disconnected"}
                    ${connectionStatus === "complete" && "Stream complete"}
                    ${connectionStatus === "error" && "Connection error"}
                    ${lines.length > 0 && ` \u2014 ${lines.length} lines`}
                </div>
            `}
        </div>
    `;
}

export { TerminalOutput };
