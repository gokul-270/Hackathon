/**
 * LogViewerTab — Preact component for viewing ROS2 log entries.
 *
 * Provides a scrollable log viewer with level filtering and
 * auto-refresh.
 *
 * Features:
 * - Scrollable log entry list
 * - Level filter dropdown (populated from metadata endpoint)
 * - Colored level badges (ERROR=red, WARN=amber, INFO=blue, DEBUG=gray)
 * - Auto-refresh every 5 seconds
 * - Limit to 100 entries
 *
 * @module tabs/LogViewerTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useRef } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5000;
const DEFAULT_LIMIT = 100;

/**
 * Map log level strings to badge colors.
 * @type {Object<string, {bg: string, fg: string}>}
 */
const LEVEL_COLORS = {
    ERROR: { bg: "#dc3545", fg: "#fff" },
    FATAL: { bg: "#dc3545", fg: "#fff" },
    WARN: { bg: "#f0ad4e", fg: "#000" },
    WARNING: { bg: "#f0ad4e", fg: "#000" },
    INFO: { bg: "#0d6efd", fg: "#fff" },
    DEBUG: { bg: "#6c757d", fg: "#fff" },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Get badge style for a log level.
 * @param {string} level
 * @returns {object} Inline style object
 */
function levelBadgeStyle(level) {
    const upper = (level || "").toUpperCase();
    const colors = LEVEL_COLORS[upper] || { bg: "#6c757d", fg: "#fff" };
    return {
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "4px",
        fontSize: "0.8em",
        fontWeight: "bold",
        background: colors.bg,
        color: colors.fg,
        minWidth: "50px",
        textAlign: "center",
    };
}

/**
 * Format a timestamp string for display.
 * @param {string} ts - Timestamp string
 * @returns {string}
 */
function formatTimestamp(ts) {
    if (!ts) return "--";
    try {
        return new Date(ts).toLocaleTimeString();
    } catch {
        return ts;
    }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Single log entry row.
 *
 * @param {object} props
 * @param {object} props.entry - Log entry from API
 */
function LogEntry({ entry }) {
    return html`
        <div
            style=${{
                display: "flex",
                gap: "var(--spacing-sm)",
                alignItems: "flex-start",
                padding: "var(--spacing-sm) var(--spacing-md)",
                borderBottom: "1px solid var(--border-color)",
                fontFamily: "monospace",
                fontSize: "0.85em",
                lineHeight: "1.4",
            }}
        >
            <span
                style=${{
                    flexShrink: "0",
                    color: "var(--text-muted)",
                    minWidth: "80px",
                }}
            >
                ${formatTimestamp(entry.timestamp)}
            </span>
            <span style=${levelBadgeStyle(entry.level)}>
                ${(entry.level || "").toUpperCase()}
            </span>
            <span
                style=${{
                    flexShrink: "0",
                    color: "var(--accent-color, #58a6ff)",
                    minWidth: "120px",
                    maxWidth: "180px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                }}
                title=${entry.node_name || ""}
            >
                ${entry.node_name || "--"}
            </span>
            <span
                style=${{
                    flex: "1",
                    color: "var(--text-primary)",
                    wordBreak: "break-word",
                }}
            >
                ${entry.message}
            </span>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function LogViewerTab() {
    const { showToast } = useToast();

    const [logs, setLogs] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [levels, setLevels] = useState([]);
    const [selectedLevel, setSelectedLevel] = useState("");

    const mountedRef = useRef(true);

    // ---- metadata loading -------------------------------------------------

    const loadMetadata = useCallback(async () => {
        const data = await safeFetch("/api/logs/metadata");
        if (!mountedRef.current) return;

        if (data && Array.isArray(data.levels)) {
            setLevels(data.levels);
        }
    }, []);

    // ---- log loading ------------------------------------------------------

    const loadLogs = useCallback(async () => {
        let url = `/api/logs?limit=${DEFAULT_LIMIT}&offset=0`;
        if (selectedLevel) {
            url += `&levels=${encodeURIComponent(selectedLevel)}`;
        }

        const data = await safeFetch(url);
        if (!mountedRef.current) return;

        if (data) {
            setLogs(data.logs || []);
            setTotal(data.total || 0);
        }
        setLoading(false);
    }, [selectedLevel]);

    // ---- lifecycle --------------------------------------------------------

    useEffect(() => {
        mountedRef.current = true;
        loadMetadata();
        loadLogs();
        return () => {
            mountedRef.current = false;
        };
    }, [loadMetadata, loadLogs]);

    // Polling — 5-second interval with cleanup
    useEffect(() => {
        const id = setInterval(() => {
            loadLogs();
        }, POLL_INTERVAL_MS);

        return () => {
            clearInterval(id);
        };
    }, [loadLogs]);

    // Reload when filter changes
    useEffect(() => {
        setLoading(true);
        loadLogs();
    }, [selectedLevel, loadLogs]);

    // ---- render -----------------------------------------------------------

    return html`
        <div class="section-header">
            <h2>Log Viewer</h2>
            <div class="section-actions">
                <select
                    style=${{
                        padding: "var(--spacing-xs) var(--spacing-sm)",
                        borderRadius: "var(--radius-sm)",
                        border: "1px solid var(--border-color)",
                        background: "var(--bg-secondary)",
                        color: "var(--text-primary)",
                        fontSize: "0.9em",
                    }}
                    value=${selectedLevel}
                    onChange=${(e) => setSelectedLevel(e.target.value)}
                >
                    <option value="">All Levels</option>
                    ${levels.map(
                        (level) => html`
                            <option key=${level} value=${level}>${level}</option>
                        `
                    )}
                </select>
                <span
                    style=${{
                        color: "var(--text-muted)",
                        fontSize: "0.85em",
                        marginLeft: "var(--spacing-sm)",
                    }}
                >
                    ${total} total
                </span>
            </div>
        </div>

        ${loading && html`<p class="text-muted">Loading logs...</p>`}

        ${!loading &&
        logs.length === 0 &&
        html`
            <div class="empty-state">
                No log entries${selectedLevel ? ` for level "${selectedLevel}"` : ""}
            </div>
        `}

        ${!loading &&
        logs.length > 0 &&
        html`
            <div
                style=${{
                    maxHeight: "600px",
                    overflowY: "auto",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-md)",
                    background: "var(--bg-secondary)",
                }}
            >
                ${logs.map(
                    (entry, i) => html`
                        <${LogEntry} key=${i} entry=${entry} />
                    `
                )}
            </div>
        `}
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("log-viewer", LogViewerTab);

export default LogViewerTab;
