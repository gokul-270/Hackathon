/**
 * LogsSubTab — Preact component for entity-level log browsing and live tail.
 *
 * Two modes:
 * - Journalctl mode (default): streams per-unit journald logs via SSE
 * - File browser mode: browse and tail log files from the entity
 *
 * Tasks implemented:
 * - 7.1: Split layout — file browser + log viewer
 * - 7.2: Log file browser (fetch, sort, select, refresh)
 * - 7.3: Live log tail viewer (SSE stream, auto-scroll, 5000-line FIFO buffer)
 * - 7.4: Severity filtering (DEBUG/INFO/WARN/ERROR/FATAL checkboxes, color coding)
 * - 7.5: Log text search (highlight, match count, up/down navigation)
 * - 7.6: Journald stream source (__journald__ path, priority mapping)
 * - dashboard-logs-fix 2.1-2.5: Mode switcher, journalctl default, fixed parsing
 *
 * @module tabs/entity/LogsSubTab
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useRef,
    useCallback,
    useMemo,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../../utils.js";
import { createLogStream } from "./StreamConnection.mjs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Maximum lines kept in the viewer buffer. */
const MAX_LINES = 5000;

/** Severity levels in display order. */
const SEVERITY_LEVELS = ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"];

/** Time preset definitions: label, duration in minutes. */
const TIME_PRESETS = [
    { label: "Last 10 min", minutes: 10 },
    { label: "Last 1 hr", minutes: 60 },
    { label: "Last 6 hr", minutes: 360 },
    { label: "Last 24 hr", minutes: 1440 },
];

/** Severity color map. */
const SEVERITY_COLORS = {
    DEBUG: "var(--color-text-muted, #8494a7)",
    INFO: "var(--color-text-primary, #e6e8eb)",
    WARN: "var(--color-warning, #f59e0b)",
    ERROR: "var(--color-error, #f55353)",
    FATAL: "var(--color-error, #f55353)",
};

/**
 * Map journald PRIORITY numbers to severity strings.
 * 0-2 = FATAL, 3 = ERROR, 4 = WARN, 5-6 = INFO, 7 = DEBUG
 */
const JOURNAL_PRIORITY_MAP = {
    0: "FATAL",
    1: "FATAL",
    2: "FATAL",
    3: "ERROR",
    4: "WARN",
    5: "INFO",
    6: "INFO",
    7: "DEBUG",
};

/** Allowed systemd units for journalctl streaming (mirrors agent allowlist). */
const JOURNAL_UNITS = [
    "arm_launch",
    "vehicle_launch",
    "pragati-agent",
    "pragati-dashboard",
    "pigpiod",
    "can-watchdog@can0",
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Compute an ISO 8601 timestamp for "minutes ago from now".
 * Used by time preset buttons to generate the `since` query parameter.
 * @param {number} minutes
 * @returns {string} ISO string e.g. "2024-01-15T10:30:00"
 */
function computeSinceISO(minutes) {
    const d = new Date(Date.now() - minutes * 60 * 1000);
    // Format as local ISO without timezone suffix (journalctl expects local)
    const pad = (n) => String(n).padStart(2, "0");
    return (
        `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
        `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    );
}

/**
 * Convert a datetime-local input value to ISO 8601 string.
 * Input format: "2024-01-15T10:30" → "2024-01-15T10:30:00"
 * @param {string} val
 * @returns {string}
 */
function datetimeLocalToISO(val) {
    if (!val) return "";
    // datetime-local gives "YYYY-MM-DDTHH:MM", append seconds
    return val.length === 16 ? val + ":00" : val;
}

/**
 * Format bytes to human-readable size (KB, MB, GB).
 * @param {number|null} bytes
 * @returns {string}
 */
function formatFileSize(bytes) {
    if (bytes == null) return "--";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) {
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

/**
 * Format ISO8601 timestamp to a short date/time string.
 * @param {string|null} isoStr
 * @returns {string}
 */
function formatModified(isoStr) {
    if (!isoStr) return "--";
    try {
        const d = new Date(isoStr);
        return d.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return isoStr;
    }
}

/**
 * Regex patterns for extracting severity from raw text log lines.
 */
const SEVERITY_REGEX_PATTERNS = [
    // ROS2 style: [node_name] [ERROR] or [WARN]
    /\[(FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG)\]/i,
    // Python logging / generic: level=error, level=warn, etc.
    /\blevel\s*=\s*(fatal|error|warn(?:ing)?|info|debug)\b/i,
    // Syslog-style: <3> or <err> etc. (less common in our context)
    /\b(FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG)\b/i,
];

/**
 * Regex patterns for extracting timestamps from raw text log lines.
 */
const TIMESTAMP_REGEX_PATTERNS = [
    // ISO 8601: 2024-01-15T10:30:45.123Z or 2024-01-15 10:30:45
    /(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)/,
    // Syslog: Jan 15 10:30:45
    /^([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})/,
    // Time only: 10:30:45.123
    /^(\d{2}:\d{2}:\d{2}(?:\.\d+)?)/,
];

/**
 * Normalize severity string to standard level name.
 * @param {string} raw
 * @returns {string}
 */
function normalizeSeverity(raw) {
    const upper = raw.toUpperCase();
    if (upper === "WARNING") return "WARN";
    if (SEVERITY_LEVELS.includes(upper)) return upper;
    return "INFO";
}

/**
 * Parse a log line to extract severity, timestamp, and message.
 *
 * For journalctl mode (isJournald=true): expects a JSON object with
 * MESSAGE, PRIORITY, _SYSTEMD_UNIT, __REALTIME_TIMESTAMP fields.
 *
 * For file mode (isJournald=false): handles both structured objects
 * and raw text strings. For raw text, attempts regex-based severity
 * and timestamp extraction before defaulting to INFO.
 *
 * @param {object|string} data - Parsed SSE message data (object or raw string)
 * @param {boolean} isJournald - Whether this is a journalctl stream
 * @returns {{severity: string, timestamp: string, message: string, source: string}}
 */
function parseLogEntry(data, isJournald) {
    if (isJournald && typeof data === "object" && data !== null) {
        const priority = parseInt(data.PRIORITY, 10);
        const journalSeverity =
            JOURNAL_PRIORITY_MAP[priority] != null
                ? JOURNAL_PRIORITY_MAP[priority]
                : "INFO";
        const message = data.MESSAGE || data.message || "";
        const unit = data._SYSTEMD_UNIT || "";

        // Also check message text for ROS2 log prefixes (e.g. [ERROR], [WARN])
        // which may be more specific than the journald PRIORITY level
        let severity = journalSeverity;
        for (const pattern of SEVERITY_REGEX_PATTERNS) {
            const match = message.match(pattern);
            if (match) {
                severity = normalizeSeverity(match[1]);
                break;
            }
        }

        // __REALTIME_TIMESTAMP is in microseconds
        let timestamp = "";
        if (data.__REALTIME_TIMESTAMP) {
            const ms = Math.floor(parseInt(data.__REALTIME_TIMESTAMP, 10) / 1000);
            try {
                timestamp = new Date(ms).toLocaleTimeString();
            } catch {
                timestamp = "";
            }
        } else if (data.timestamp) {
            timestamp = data.timestamp;
        }
        return { severity, timestamp, message, source: unit };
    }

    // Raw text string (from file tail or non-JSON SSE data)
    if (typeof data === "string") {
        const text = data;

        // Try to extract severity from common log patterns
        let severity = "INFO";
        for (const pattern of SEVERITY_REGEX_PATTERNS) {
            const match = text.match(pattern);
            if (match) {
                severity = normalizeSeverity(match[1]);
                break;
            }
        }

        // Try to extract timestamp
        let timestamp = "";
        for (const pattern of TIMESTAMP_REGEX_PATTERNS) {
            const match = text.match(pattern);
            if (match) {
                timestamp = match[1];
                break;
            }
        }

        return { severity, timestamp, message: text, source: "" };
    }

    // Structured object from file tail (legacy path, if agent ever sends JSON)
    if (typeof data === "object" && data !== null) {
        const severity = normalizeSeverity(
            data.severity || data.level || "INFO"
        );
        const timestamp = data.timestamp || "";
        const message = data.message || data.line || data.text || "";
        const source = data.source || data.node || "";
        return { severity, timestamp, message, source };
    }

    // Fallback for unexpected data types
    return { severity: "INFO", timestamp: "", message: String(data), source: "" };
}

/**
 * Escape special regex characters in a string.
 * @param {string} str
 * @returns {string}
 */
function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * File browser panel (left side) — shown only in file browser mode.
 *
 * @param {object} props
 * @param {Array} props.files - Log file list
 * @param {object|null} props.selectedFile - Currently selected file
 * @param {Function} props.onSelect - File selection callback
 * @param {Function} props.onRefresh - Refresh callback
 * @param {boolean} props.loading - Whether files are loading
 */
function FileBrowser({ files, selectedFile, onSelect, onRefresh, loading }) {
    return html`
        <div
            style=${{
                width: "250px",
                minWidth: "250px",
                borderRight: "1px solid var(--color-border, #2d3748)",
                display: "flex",
                flexDirection: "column",
                background: "var(--color-bg-secondary, #1a1f2e)",
            }}
        >
            <!-- Header -->
            <div
                style=${{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "8px 12px",
                    borderBottom: "1px solid var(--color-border, #2d3748)",
                    fontWeight: "bold",
                    fontSize: "0.9em",
                }}
            >
                <span>Log Files</span>
                <button
                    onClick=${onRefresh}
                    title="Refresh file list"
                    style=${{
                        background: "none",
                        border: "1px solid var(--color-border, #2d3748)",
                        borderRadius: "var(--radius-sm, 4px)",
                        color: "var(--color-text-primary, #e6e8eb)",
                        cursor: "pointer",
                        padding: "2px 6px",
                        fontSize: "0.85em",
                    }}
                >
                    \u21BB
                </button>
            </div>

            <!-- File list -->
            <div
                style=${{
                    flex: 1,
                    overflowY: "auto",
                    padding: "4px 0",
                }}
            >
                ${loading && html`
                    <div style=${{ padding: "12px",                         color: "var(--color-text-muted, #8494a7)", textAlign: "center" }}>
                        Loading...
                    </div>
                `}

                ${!loading && files.length === 0 && html`
                    <div style=${{
                        padding: "24px 12px",
                        color: "var(--color-text-muted, #8494a7)",
                        textAlign: "center",
                        fontSize: "0.9em",
                    }}>
                        No log files found
                    </div>
                `}

                ${!loading && files.map((file) => html`
                    <div
                        key=${file.path}
                        onClick=${() => onSelect(file)}
                        style=${{
                            padding: "6px 12px",
                            cursor: "pointer",
                            background:
                                selectedFile && selectedFile.path === file.path
                                    ? "var(--color-accent, #4b8df7)"
                                    : "transparent",
                            color:
                                selectedFile && selectedFile.path === file.path
                                    ? "#fff"
                                    : "var(--color-text-primary, #e6e8eb)",
                            borderBottom: "1px solid var(--color-border, #2d3748)",
                            transition: "background 0.15s",
                        }}
                        onMouseEnter=${(e) => {
                            if (
                                !selectedFile ||
                                selectedFile.path !== file.path
                            ) {
                                e.currentTarget.style.background =
                                    "var(--hover-bg, #2a3342)";
                            }
                        }}
                        onMouseLeave=${(e) => {
                            if (
                                !selectedFile ||
                                selectedFile.path !== file.path
                            ) {
                                e.currentTarget.style.background =
                                    "transparent";
                            }
                        }}
                    >
                        <div
                            style=${{
                                fontSize: "0.85em",
                                fontWeight: "500",
                                marginBottom: "2px",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                            }}
                            title=${file.name}
                        >
                            \uD83D\uDCC4 ${file.name}
                        </div>
                        <div
                            style=${{
                                fontSize: "0.75em",
                                color:
                                    selectedFile &&
                                    selectedFile.path === file.path
                                        ? "rgba(255,255,255,0.7)"
                                        : "var(--color-text-muted, #8494a7)",
                                display: "flex",
                                gap: "8px",
                            }}
                        >
                            <span>${formatFileSize(file.size_bytes)}</span>
                            <span>${formatModified(file.modified)}</span>
                        </div>
                    </div>
                `)}
            </div>
        </div>
    `;
}

/**
 * Severity filter checkbox row.
 *
 * @param {object} props
 * @param {object} props.severityFilter - Map of severity -> boolean
 * @param {Function} props.onToggle - Toggle callback (severity)
 */
function SeverityFilterRow({ severityFilter, onToggle }) {
    return html`
        <div
            style=${{
                display: "flex",
                gap: "12px",
                alignItems: "center",
                flexShrink: 0,
            }}
        >
            ${SEVERITY_LEVELS.map(
                (level) => html`
                    <label
                        key=${level}
                        style=${{
                            display: "flex",
                            alignItems: "center",
                            gap: "4px",
                            cursor: "pointer",
                            fontSize: "0.8em",
                            color: SEVERITY_COLORS[level],
                            fontWeight:
                                level === "FATAL" ? "bold" : "normal",
                        }}
                    >
                        <input
                            type="checkbox"
                            checked=${severityFilter[level]}
                            onChange=${() => onToggle(level)}
                            style=${{ cursor: "pointer" }}
                        />
                        ${level}
                    </label>
                `
            )}
        </div>
    `;
}

/**
 * Time preset button row.
 *
 * @param {object} props
 * @param {string|null} props.activePreset - Label of active preset or null
 * @param {Function} props.onSelect - Callback(presetLabel) or null to deselect
 */
function TimePresetRow({ activePreset, onSelect }) {
    return html`
        <div
            style=${{
                display: "flex",
                gap: "4px",
                alignItems: "center",
                flexShrink: 0,
            }}
        >
            ${TIME_PRESETS.map(
                (preset) => html`
                    <button
                        key=${preset.label}
                        onClick=${() =>
                            onSelect(
                                activePreset === preset.label
                                    ? null
                                    : preset.label,
                            )}
                        style=${{
                            padding: "3px 8px",
                            fontSize: "0.75em",
                            border: "1px solid var(--color-border, #2d3748)",
                            borderRadius: "var(--radius-sm, 4px)",
                            cursor: "pointer",
                            background:
                                activePreset === preset.label
                                    ? "var(--color-accent, #4b8df7)"
                                    : "transparent",
                            color:
                                activePreset === preset.label
                                    ? "#fff"
                                    : "var(--color-text-primary, #e6e8eb)",
                            fontWeight:
                                activePreset === preset.label
                                    ? "bold"
                                    : "normal",
                            transition: "background 0.15s, color 0.15s",
                        }}
                    >
                        ${preset.label}
                    </button>
                `,
            )}
        </div>
    `;
}

/**
 * Custom datetime range picker with From/To inputs.
 *
 * @param {object} props
 * @param {string} props.customSince - datetime-local value for "From"
 * @param {string} props.customUntil - datetime-local value for "To"
 * @param {Function} props.onSinceChange - Callback(value)
 * @param {Function} props.onUntilChange - Callback(value)
 * @param {boolean} props.hasError - Whether From >= To (validation error)
 */
function CustomDateTimeRange({
    customSince,
    customUntil,
    onSinceChange,
    onUntilChange,
    hasError,
}) {
    const inputStyle = {
        padding: "3px 6px",
        fontSize: "0.75em",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-sm, 4px)",
        background: "var(--color-bg-tertiary, #242b3d)",
        color: "var(--color-text-primary, #e6e8eb)",
        colorScheme: "dark",
    };

    const errorInputStyle = {
        ...inputStyle,
        borderColor: "var(--color-error, #f55353)",
    };

    return html`
        <div
            style=${{
                display: "flex",
                gap: "6px",
                alignItems: "center",
                flexShrink: 0,
                fontSize: "0.75em",
            }}
        >
            <span
                data-testid="time-from-label"
                style=${{ color: "var(--color-text-muted, #8494a7)" }}
            >
                From
            </span>
            <input
                type="datetime-local"
                value=${customSince}
                onInput=${(e) => onSinceChange(e.target.value)}
                style=${hasError ? errorInputStyle : inputStyle}
            />
            <span
                data-testid="time-until-label"
                style=${{ color: "var(--color-text-muted, #8494a7)" }}
            >
                To
            </span>
            <input
                type="datetime-local"
                value=${customUntil}
                onInput=${(e) => onUntilChange(e.target.value)}
                style=${hasError ? errorInputStyle : inputStyle}
            />
            ${hasError && html`
                <span
                    style=${{
                        color: "var(--color-error, #f55353)",
                        fontSize: "0.9em",
                    }}
                >
                    From must be before To
                </span>
            `}
        </div>
    `;
}

/**
 * Search bar with match count and navigation.
 *
 * @param {object} props
 * @param {string} props.searchText
 * @param {Function} props.onSearchChange
 * @param {number} props.matchCount
 * @param {number} props.searchIndex
 * @param {Function} props.onPrev
 * @param {Function} props.onNext
 */
function SearchBar({
    searchText,
    onSearchChange,
    matchCount,
    searchIndex,
    onPrev,
    onNext,
}) {
    return html`
        <div
            style=${{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                flexShrink: 0,
            }}
        >
            <input
                type="text"
                placeholder="Search logs..."
                value=${searchText}
                onInput=${(e) => onSearchChange(e.target.value)}
                style=${{
                    padding: "4px 8px",
                    fontSize: "0.8em",
                    border: "1px solid var(--color-border, #2d3748)",
                    borderRadius: "var(--radius-sm, 4px)",
                    background: "var(--color-bg-tertiary, #242b3d)",
                    color: "var(--color-text-primary, #e6e8eb)",
                    width: "160px",
                }}
            />
            ${searchText && html`
                <span
                    style=${{
                        fontSize: "0.75em",
                        color: "var(--color-text-muted, #8494a7)",
                        whiteSpace: "nowrap",
                    }}
                >
                    ${matchCount > 0
                        ? `${searchIndex + 1}/${matchCount}`
                        : "0 matches"}
                </span>
                <button
                    onClick=${onPrev}
                    disabled=${matchCount === 0}
                    title="Previous match"
                    style=${{
                        background: "none",
                        border: "1px solid var(--color-border, #2d3748)",
                        borderRadius: "var(--radius-sm, 4px)",
                        color: "var(--color-text-primary, #e6e8eb)",
                        cursor: "pointer",
                        padding: "2px 6px",
                        fontSize: "0.8em",
                    }}
                >
                    ▲
                </button>
                <button
                    onClick=${onNext}
                    disabled=${matchCount === 0}
                    title="Next match"
                    style=${{
                        background: "none",
                        border: "1px solid var(--color-border, #2d3748)",
                        borderRadius: "var(--radius-sm, 4px)",
                        color: "var(--color-text-primary, #e6e8eb)",
                        cursor: "pointer",
                        padding: "2px 6px",
                        fontSize: "0.8em",
                    }}
                >
                    ▼
                </button>
            `}
        </div>
    `;
}

/**
 * Mode switcher (Journalctl / Files).
 *
 * @param {object} props
 * @param {string} props.mode - "journal" or "file"
 * @param {Function} props.onSwitch
 */
function ModeSwitcher({ mode, onSwitch }) {
    const btnStyle = (active) => ({
        padding: "4px 10px",
        fontSize: "0.8em",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-sm, 4px)",
        cursor: "pointer",
        background: active ? "var(--color-accent, #4b8df7)" : "transparent",
        color: active ? "#fff" : "var(--color-text-primary, #e6e8eb)",
        fontWeight: active ? "bold" : "normal",
    });

    return html`
        <div
            style=${{
                display: "flex",
                gap: "4px",
                alignItems: "center",
                flexShrink: 0,
            }}
        >
            <button
                onClick=${() => onSwitch("journal")}
                style=${btnStyle(mode === "journal")}
                title="Stream journalctl logs from systemd services"
            >
                Journalctl
            </button>
            <button
                onClick=${() => onSwitch("file")}
                style=${btnStyle(mode === "file")}
                title="Browse and tail log files"
            >
                Files
            </button>
        </div>
    `;
}

/**
 * Journalctl unit selector dropdown.
 *
 * @param {object} props
 * @param {string} props.selectedUnit
 * @param {Function} props.onSelect
 */
function UnitSelector({ selectedUnit, onSelect }) {
    return html`
        <select
            value=${selectedUnit}
            onChange=${(e) => onSelect(e.target.value)}
            style=${{
                padding: "4px 8px",
                fontSize: "0.82em",
                border: "1px solid var(--color-border, #2d3748)",
                borderRadius: "var(--radius-sm, 4px)",
                background: "var(--color-bg-tertiary, #242b3d)",
                color: "var(--color-text-primary, #e6e8eb)",
                cursor: "pointer",
            }}
        >
            ${JOURNAL_UNITS.map(
                (unit) => html`
                    <option key=${unit} value=${unit}>${unit}</option>
                `
            )}
        </select>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * LogsSubTab — entity-level log browsing and live tail viewer.
 *
 * @param {object} props
 * @param {string} props.entityId
 * @param {string} props.entitySource
 * @param {string|null} props.entityIp
 * @param {boolean} props.ros2Available
 * @param {Function} [props.registerCleanup]
 */

// Module-level state preservation (survives unmount-on-switch)
const _savedLogsState = {};

export default function LogsSubTab({
    entityId,
    entitySource,
    entityIp,
    ros2Available,
    registerCleanup,
}) {
    // -- Mode state (journal or file) -- restored from module-level cache
    const [mode, setMode] = useState(_savedLogsState.mode || "journal");
    const [selectedUnit, setSelectedUnit] = useState(
        _savedLogsState.selectedUnit || JOURNAL_UNITS[0]
    );

    // -- File browser state --
    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState(null);
    const [filesLoading, setFilesLoading] = useState(false);

    // -- Log viewer state --
    const [logLines, setLogLines] = useState([]);
    const [streaming, setStreaming] = useState(false);
    const [fileLoading, setFileLoading] = useState(false);
    const [streamError, setStreamError] = useState(null);
    const [reconnectStatus, setReconnectStatus] = useState(null); // {attempt, delayMs} or null
    const [autoScroll, setAutoScroll] = useState(true);

    // -- Severity filter -- restored from module-level cache
    const [severityFilter, setSeverityFilter] = useState(
        _savedLogsState.severityFilter || {
            DEBUG: true,
            INFO: true,
            WARN: true,
            ERROR: true,
            FATAL: true,
        }
    );

    // -- Search -- restored from module-level cache
    const [searchText, setSearchText] = useState(_savedLogsState.searchText || "");
    const [searchIndex, setSearchIndex] = useState(0);

    // -- Time filter state -- restored from module-level cache
    const [activePreset, setActivePreset] = useState(
        _savedLogsState.activePreset || null
    );
    const [customSince, setCustomSince] = useState(
        _savedLogsState.customSince || ""
    );
    const [customUntil, setCustomUntil] = useState(
        _savedLogsState.customUntil || ""
    );

    // Computed: effective since/until values
    const effectiveTimeRange = useMemo(() => {
        // Custom range overrides preset
        if (customSince || customUntil) {
            return {
                since: customSince ? datetimeLocalToISO(customSince) : null,
                until: customUntil ? datetimeLocalToISO(customUntil) : null,
            };
        }
        // Preset computes since only
        if (activePreset) {
            const preset = TIME_PRESETS.find((p) => p.label === activePreset);
            if (preset) {
                return { since: computeSinceISO(preset.minutes), until: null };
            }
        }
        return { since: null, until: null };
    }, [activePreset, customSince, customUntil]);

    // Validate custom range: From must be before To
    const customRangeError = useMemo(() => {
        if (customSince && customUntil) {
            return new Date(customSince) >= new Date(customUntil);
        }
        return false;
    }, [customSince, customUntil]);

    // -- Refs --
    const viewerRef = useRef(null);
    const streamRef = useRef(null);
    const mountedRef = useRef(true);
    const matchElementsRef = useRef([]);

    // Ref to track latest state values for cleanup without triggering re-registration
    const stateRef = useRef({});
    stateRef.current = { mode, selectedUnit, severityFilter, searchText, activePreset, customSince, customUntil };

    // ---- Cleanup registration ----

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
        };
    }, []);

    const closeStream = useCallback(() => {
        if (streamRef.current) {
            streamRef.current.close();
            streamRef.current = null;
        }
        setStreaming(false);
        setFileLoading(false);
        setReconnectStatus(null);
    }, []);

    useEffect(() => {
        registerCleanup?.(() => {
            // Save filter state to module-level cache before cleanup.
            // Read from ref so this cleanup doesn't need to re-register
            // when filter state changes (which would kill the stream).
            const s = stateRef.current;
            _savedLogsState.mode = s.mode;
            _savedLogsState.selectedUnit = s.selectedUnit;
            _savedLogsState.severityFilter = s.severityFilter;
            _savedLogsState.searchText = s.searchText;
            _savedLogsState.activePreset = s.activePreset;
            _savedLogsState.customSince = s.customSince;
            _savedLogsState.customUntil = s.customUntil;
            closeStream();
        });
    }, [registerCleanup, closeStream]);

    // ---- Fetch log file list (file mode only) ----

    const fetchFiles = useCallback(async () => {
        setFilesLoading(true);
        const data = await safeFetch(`/api/entities/${entityId}/logs`);
        if (!mountedRef.current) return;

        if (data) {
            // Handle both envelope formats:
            // - {data: {files: [...]}} (double-wrapped from safeFetch + API envelope)
            // - {files: [...]} (if safeFetch unwraps outer envelope)
            // - {data: [...]} (flat array in data envelope)
            // - [...] (flat array directly)
            const filesPayload = data.data || data;
            const fileList = filesPayload.files || (Array.isArray(filesPayload) ? filesPayload : []);

            if (Array.isArray(fileList)) {
                // Sort by modified date, newest first; null dates go to end
                const sorted = [...fileList].sort((a, b) => {
                    if (!a.modified && !b.modified) return 0;
                    if (!a.modified) return 1;
                    if (!b.modified) return -1;
                    return new Date(b.modified) - new Date(a.modified);
                });
                // Filter out __journald__ synthetic entry (handled by journal mode)
                setFiles(sorted.filter((f) => f.path !== "__journald__"));
            } else {
                setFiles([]);
            }
        } else {
            setFiles([]);
        }
        setFilesLoading(false);
    }, [entityId]);

    // ---- Start stream helpers ----

    const startJournalStream = useCallback(
        (unit) => {
            closeStream();
            setLogLines([]);
            setAutoScroll(true);
            setStreamError(null);
            setFileLoading(true);

            let receivedFirst = false;
            const streamOpts = { mode: "journal" };
            // Pass time range to the SSE stream if not a validation error
            if (!customRangeError) {
                if (effectiveTimeRange.since) {
                    streamOpts.since = effectiveTimeRange.since;
                }
                if (effectiveTimeRange.until) {
                    streamOpts.until = effectiveTimeRange.until;
                }
            }
            const stream = createLogStream(entityId, unit, {
                ...streamOpts,
                onReconnecting: (attempt, delayMs) => {
                    if (!mountedRef.current) return;
                    setReconnectStatus({ attempt, delayMs });
                },
                onDisconnected: () => {
                    if (!mountedRef.current) return;
                    setReconnectStatus(null);
                    setStreamError("Stream to entity disconnected — click Retry to reconnect");
                    setStreaming(false);
                },
            });
            stream.onMessage((data) => {
                if (!mountedRef.current) return;
                setReconnectStatus(null);
                if (!receivedFirst) {
                    receivedFirst = true;
                    setFileLoading(false);
                }
                const entry = parseLogEntry(data, true);
                setLogLines((prev) => {
                    const next = [...prev, entry];
                    if (next.length > MAX_LINES) {
                        return next.slice(next.length - MAX_LINES);
                    }
                    return next;
                });
            });
            stream.onError(() => {
                if (!mountedRef.current) return;
                setFileLoading(false);
                setStreamError("Stream connection failed. The source may be unavailable.");
                setStreaming(false);
            });
            stream.connect();
            streamRef.current = stream;
            setStreaming(true);
        },
        [entityId, closeStream, effectiveTimeRange, customRangeError],
    );

    const startFileStream = useCallback(
        (file) => {
            closeStream();
            setLogLines([]);
            setAutoScroll(true);
            setStreamError(null);
            setFileLoading(true);

            let receivedFirst = false;
            const stream = createLogStream(entityId, file.path, {
                mode: "file",
                onReconnecting: (attempt, delayMs) => {
                    if (!mountedRef.current) return;
                    setReconnectStatus({ attempt, delayMs });
                },
                onDisconnected: () => {
                    if (!mountedRef.current) return;
                    setReconnectStatus(null);
                    setStreamError("Stream to entity disconnected — click Retry to reconnect");
                    setStreaming(false);
                },
            });
            stream.onMessage((data) => {
                if (!mountedRef.current) return;
                setReconnectStatus(null);
                if (!receivedFirst) {
                    receivedFirst = true;
                    setFileLoading(false);
                }
                const entry = parseLogEntry(data, false);
                setLogLines((prev) => {
                    const next = [...prev, entry];
                    if (next.length > MAX_LINES) {
                        return next.slice(next.length - MAX_LINES);
                    }
                    return next;
                });
            });
            stream.onError(() => {
                if (!mountedRef.current) return;
                setFileLoading(false);
                setStreamError("Stream connection failed. The log file may be unavailable.");
                setStreaming(false);
            });
            stream.connect();
            streamRef.current = stream;
            setStreaming(true);
        },
        [entityId, closeStream],
    );

    // ---- Auto-start journal stream on mount / unit change ----

    useEffect(() => {
        if (mode === "journal") {
            startJournalStream(selectedUnit);
        }
        // Cleanup on unmount or mode/unit change
        return () => {
            closeStream();
        };
    }, [mode, selectedUnit, entityId, effectiveTimeRange]); // eslint-disable-line react-hooks/exhaustive-deps

    // ---- Fetch files when switching to file mode ----

    useEffect(() => {
        if (mode === "file") {
            fetchFiles();
        }
    }, [mode, fetchFiles]);

    // ---- Mode switch handler ----

    const handleModeSwitch = useCallback(
        (newMode) => {
            if (newMode === mode) return;
            closeStream();
            setLogLines([]);
            setSearchText("");
            setSearchIndex(0);
            setSelectedFile(null);
            setStreamError(null);
            setMode(newMode);
        },
        [mode, closeStream],
    );

    // ---- Unit change handler ----

    const handleUnitChange = useCallback(
        (unit) => {
            setSelectedUnit(unit);
            setLogLines([]);
            setSearchText("");
            setSearchIndex(0);
        },
        [],
    );

    // ---- File selection handler ----

    const handleSelectFile = useCallback(
        (file) => {
            setSelectedFile(file);
            setSearchText("");
            setSearchIndex(0);
            startFileStream(file);
        },
        [startFileStream],
    );

    const handleStop = useCallback(() => {
        closeStream();
    }, [closeStream]);

    const handleRestart = useCallback(() => {
        if (mode === "journal") {
            startJournalStream(selectedUnit);
        } else if (selectedFile) {
            startFileStream(selectedFile);
        }
    }, [mode, selectedUnit, selectedFile, startJournalStream, startFileStream]);

    // ---- Auto-scroll ----

    useEffect(() => {
        if (autoScroll && viewerRef.current) {
            viewerRef.current.scrollTop = viewerRef.current.scrollHeight;
        }
    }, [logLines, autoScroll]);

    const handleViewerScroll = useCallback(() => {
        if (!viewerRef.current) return;
        const el = viewerRef.current;
        // Consider "at bottom" if within 50px of the bottom
        const atBottom =
            el.scrollHeight - el.scrollTop - el.clientHeight < 50;
        setAutoScroll(atBottom);
    }, []);

    const jumpToBottom = useCallback(() => {
        if (viewerRef.current) {
            viewerRef.current.scrollTop = viewerRef.current.scrollHeight;
        }
        setAutoScroll(true);
    }, []);

    // ---- Severity filtering ----

    const toggleSeverity = useCallback((level) => {
        setSeverityFilter((prev) => ({
            ...prev,
            [level]: !prev[level],
        }));
    }, []);

    const filteredLines = useMemo(() => {
        return logLines.filter((line) => severityFilter[line.severity]);
    }, [logLines, severityFilter]);

    // ---- File list filtering by time range (Task 4.4) ----

    const filteredFiles = useMemo(() => {
        const { since, until } = effectiveTimeRange;
        if (!since && !until) return files;

        const sinceDate = since ? new Date(since) : null;
        const untilDate = until ? new Date(until) : null;

        return files.filter((file) => {
            if (!file.modified) return false; // hide files with no modified date
            const fileDate = new Date(file.modified);
            if (sinceDate && fileDate < sinceDate) return false;
            if (untilDate && fileDate > untilDate) return false;
            return true;
        });
    }, [files, effectiveTimeRange]);

    // ---- Search ----

    const searchRegex = useMemo(() => {
        if (!searchText) return null;
        try {
            return new RegExp(escapeRegex(searchText), "gi");
        } catch {
            return null;
        }
    }, [searchText]);

    const matchingIndices = useMemo(() => {
        if (!searchRegex) return [];
        const indices = [];
        filteredLines.forEach((line, i) => {
            if (searchRegex.test(line.message)) {
                indices.push(i);
            }
            // Reset lastIndex since regex is global
            searchRegex.lastIndex = 0;
        });
        return indices;
    }, [filteredLines, searchRegex]);

    // Reset search index when matches or search text change
    useEffect(() => {
        setSearchIndex(0);
    }, [searchText, matchingIndices.length]);

    const navigateSearch = useCallback(
        (direction) => {
            if (matchingIndices.length === 0) return;
            let newIdx;
            if (direction === "next") {
                newIdx = (searchIndex + 1) % matchingIndices.length;
            } else {
                newIdx =
                    (searchIndex - 1 + matchingIndices.length) %
                    matchingIndices.length;
            }
            setSearchIndex(newIdx);

            // Scroll to matching line
            const lineIdx = matchingIndices[newIdx];
            const el = viewerRef.current;
            if (el) {
                const lineEl = el.querySelector(
                    `[data-line-index="${lineIdx}"]`
                );
                if (lineEl) {
                    lineEl.scrollIntoView({ block: "center", behavior: "smooth" });
                    setAutoScroll(false);
                }
            }
        },
        [searchIndex, matchingIndices],
    );

    /**
     * Highlight search matches in a text string.
     * Returns an array of VNodes with highlighted spans.
     *
     * @param {string} text
     * @returns {Array}
     */
    const highlightText = useCallback(
        (text) => {
            if (!searchRegex || !searchText) return [text];
            const parts = [];
            let lastIndex = 0;
            let match;
            // Need a fresh regex each call since it's global
            const re = new RegExp(escapeRegex(searchText), "gi");
            while ((match = re.exec(text)) !== null) {
                if (match.index > lastIndex) {
                    parts.push(text.slice(lastIndex, match.index));
                }
                parts.push(
                    html`<span
                        style=${{
                            background: "var(--color-warning, #f59e0b)",
                            color: "#000",
                            borderRadius: "2px",
                            padding: "0 1px",
                        }}
                    >
                        ${match[0]}
                    </span>`
                );
                lastIndex = re.lastIndex;
            }
            if (lastIndex < text.length) {
                parts.push(text.slice(lastIndex));
            }
            return parts.length > 0 ? parts : [text];
        },
        [searchRegex, searchText],
    );

    // ---- Determine current stream label ----
    const streamLabel = useMemo(() => {
        if (mode === "journal") return selectedUnit;
        if (selectedFile) return selectedFile.name;
        return "";
    }, [mode, selectedUnit, selectedFile]);

    // Whether the viewer should show content (journal always, file only when selected)
    const hasActiveSource = mode === "journal" || selectedFile != null;

    // ---- Render ----

    return html`
        <style>
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
        </style>
        <div
            style=${{
                display: "flex",
                flexDirection: "column",
                height: "calc(100vh - 200px)",
                minHeight: "400px",
                border: "1px solid var(--color-border, #2d3748)",
                borderRadius: "var(--radius-md, 8px)",
                overflow: "hidden",
            }}
        >
            <!-- Mode switcher toolbar -->
            <div
                style=${{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "6px 12px",
                    borderBottom: "1px solid var(--color-border, #2d3748)",
                    background: "var(--color-bg-secondary, #1a1f2e)",
                    gap: "12px",
                }}
            >
                <div style=${{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <${ModeSwitcher} mode=${mode} onSwitch=${handleModeSwitch} />
                    ${mode === "journal" && html`
                        <${UnitSelector}
                            selectedUnit=${selectedUnit}
                            onSelect=${handleUnitChange}
                        />
                    `}
                </div>
            </div>

            <!-- Time filter toolbar -->
            <div
                style=${{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "4px 12px",
                    borderBottom: "1px solid var(--color-border, #2d3748)",
                    background: "var(--color-bg-secondary, #1a1f2e)",
                    gap: "12px",
                    flexWrap: "wrap",
                }}
            >
                <${TimePresetRow}
                    activePreset=${activePreset}
                    onSelect=${(label) => {
                        setActivePreset(label);
                        // Clear custom range when selecting a preset
                        if (label) {
                            setCustomSince("");
                            setCustomUntil("");
                        }
                    }}
                />
                <${CustomDateTimeRange}
                    customSince=${customSince}
                    customUntil=${customUntil}
                    onSinceChange=${(val) => {
                        setCustomSince(val);
                        // Clear preset when using custom range
                        if (val) setActivePreset(null);
                    }}
                    onUntilChange=${(val) => {
                        setCustomUntil(val);
                        // Clear preset when using custom range
                        if (val) setActivePreset(null);
                    }}
                    hasError=${customRangeError}
                />
            </div>

            <!-- Main content area -->
            <div
                style=${{
                    display: "flex",
                    flex: 1,
                    minHeight: 0,
                }}
            >
                <!-- File browser panel (only in file mode) -->
                ${mode === "file" && html`
                    <${FileBrowser}
                        files=${filteredFiles}
                        selectedFile=${selectedFile}
                        onSelect=${handleSelectFile}
                        onRefresh=${fetchFiles}
                        loading=${filesLoading}
                    />
                `}

                <!-- Log viewer panel -->
                <div
                    style=${{
                        flex: 1,
                        display: "flex",
                        flexDirection: "column",
                        minWidth: 0,
                    }}
                >
                    ${hasActiveSource
                        ? html`
                              <!-- Toolbar: severity filter + search + stop -->
                              <div
                                  style=${{
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "space-between",
                                      padding: "6px 12px",
                                      borderBottom:
                                           "1px solid var(--color-border, #2d3748)",
                                      background: "var(--color-bg-secondary, #1a1f2e)",
                                      gap: "12px",
                                      flexWrap: "wrap",
                                  }}
                              >
                                  <${SeverityFilterRow}
                                      severityFilter=${severityFilter}
                                      onToggle=${toggleSeverity}
                                  />
                                  <div
                                      style=${{
                                          display: "flex",
                                          alignItems: "center",
                                          gap: "8px",
                                      }}
                                  >
                                      <${SearchBar}
                                          searchText=${searchText}
                                          onSearchChange=${setSearchText}
                                          matchCount=${matchingIndices.length}
                                          searchIndex=${searchIndex}
                                          onPrev=${() =>
                                              navigateSearch("prev")}
                                          onNext=${() =>
                                              navigateSearch("next")}
                                      />
                                      ${streaming && html`
                                          <button
                                              onClick=${handleStop}
                                              title="Stop streaming"
                                              style=${{
                                                  background: "var(--color-error, #f55353)",
                                                  border: "none",
                                                  borderRadius: "var(--radius-sm, 4px)",
                                                  color: "#fff",
                                                  cursor: "pointer",
                                                  padding: "4px 10px",
                                                  fontSize: "0.8em",
                                                  fontWeight: "bold",
                                              }}
                                          >
                                              Stop
                                          </button>
                                      `}
                                      ${!streaming && hasActiveSource && html`
                                          <button
                                              onClick=${handleRestart}
                                              title="Start streaming"
                                              style=${{
                                                  background: "var(--color-success, #22c55e)",
                                                  border: "none",
                                                  borderRadius: "var(--radius-sm, 4px)",
                                                  color: "#fff",
                                                  cursor: "pointer",
                                                  padding: "4px 10px",
                                                  fontSize: "0.8em",
                                                  fontWeight: "bold",
                                              }}
                                          >
                                              Start
                                          </button>
                                      `}
                                  </div>
                              </div>

                              <!-- Streaming status bar -->
                              <div
                                  style=${{
                                      padding: "4px 12px",
                                      fontSize: "0.75em",
                                      color: "var(--color-text-muted, #8494a7)",
                                      borderBottom:
                                           "1px solid var(--color-border, #2d3748)",
                                      background: "var(--color-bg-secondary, #1a1f2e)",
                                      display: "flex",
                                      justifyContent: "space-between",
                                  }}
                              >
                                  <span>
                                      ${streaming
                                          ? html`<span style=${{ color: "var(--color-success, #22c55e)" }}>\u25CF</span> Streaming: ${streamLabel}`
                                          : html`<span style=${{ color: "var(--color-text-muted, #8494a7)" }}>\u25CB</span> Stopped: ${streamLabel}`}
                                  </span>
                                  <span>${filteredLines.length} lines</span>
                              </div>

                              <!-- Log viewer area -->
                              <div
                                  ref=${viewerRef}
                                  onScroll=${handleViewerScroll}
                                  style=${{
                                      flex: 1,
                                      overflowY: "auto",
                                      background: "var(--color-bg-primary, #0f1419)",
                                      fontFamily:
                                          "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
                                      fontSize: "0.82em",
                                      lineHeight: "1.5",
                                      padding: "8px 0",
                                      position: "relative",
                                  }}
                              >
                                  ${fileLoading && filteredLines.length === 0 && html`
                                      <div
                                          style=${{
                                              padding: "40px 20px",
                                              textAlign: "center",
                                              color: "var(--color-text-muted, #8494a7)",
                                          }}
                                      >
                                          <div style=${{
                                              display: "inline-block",
                                              width: "20px",
                                              height: "20px",
                                              border: "2px solid var(--color-border, #2d3748)",
                                              borderTopColor: "var(--color-accent, #4b8df7)",
                                              borderRadius: "50%",
                                              animation: "spin 0.8s linear infinite",
                                              marginBottom: "8px",
                                          }}></div>
                                          <div>Connecting to stream...</div>
                                      </div>
                                  `}

                                  ${reconnectStatus && html`
                                      <div
                                          style=${{
                                              padding: "8px 12px",
                                              margin: "4px 8px",
                                              background: "var(--badge-warning-bg, rgba(245, 158, 11, 0.15))",
                                              border: "1px solid var(--color-warning, #f59e0b)",
                                              borderRadius: "var(--radius-sm, 4px)",
                                              color: "var(--color-warning, #f59e0b)",
                                              fontSize: "0.85em",
                                              display: "flex",
                                              alignItems: "center",
                                              gap: "8px",
                                          }}
                                      >
                                          <span style=${{ animation: "pulse 1.5s ease-in-out infinite" }}>●</span>
                                          Reconnecting... (attempt ${reconnectStatus.attempt}, retry in ${Math.round(reconnectStatus.delayMs / 1000)}s)
                                      </div>
                                  `}

                                  ${streamError && html`
                                      <div
                                          style=${{
                                              padding: "12px 16px",
                                              margin: "8px 12px",
                                              background: "var(--badge-error-bg, rgba(239, 68, 68, 0.2))",
                                              border: "1px solid var(--color-error, #f55353)",
                                              borderRadius: "var(--radius-sm, 4px)",
                                              color: "var(--color-error, #f55353)",
                                              fontSize: "0.9em",
                                              display: "flex",
                                              alignItems: "center",
                                              justifyContent: "space-between",
                                              gap: "8px",
                                          }}
                                      >
                                          <span>${streamError}</span>
                                          ${streamError.includes("Retry") && html`
                                              <button
                                                  onClick=${() => {
                                                      setStreamError(null);
                                                      if (mode === "journal" && selectedUnit) {
                                                          startJournalStream(selectedUnit);
                                                      } else if (mode === "file" && selectedFile) {
                                                          startFileStream(selectedFile);
                                                      }
                                                  }}
                                                  style=${{
                                                      padding: "4px 10px",
                                                      background: "var(--color-error, #f55353)",
                                                      color: "#fff",
                                                      border: "none",
                                                      borderRadius: "var(--radius-sm, 4px)",
                                                      cursor: "pointer",
                                                      fontSize: "0.85em",
                                                      flexShrink: 0,
                                                  }}
                                              >
                                                  Retry
                                              </button>
                                          `}
                                      </div>
                                  `}

                                  ${filteredLines.length === 0 && !streaming && !fileLoading && !streamError && html`
                                      <div
                                          style=${{
                                              padding: "40px 20px",
                                              textAlign: "center",
                                              color: "var(--color-text-muted, #8494a7)",
                                          }}
                                      >
                                          No log lines received
                                      </div>
                                  `}

                                  ${filteredLines.length === 0 && streaming && !fileLoading && html`
                                      <div
                                          style=${{
                                              padding: "40px 20px",
                                              textAlign: "center",
                                              color: "var(--color-text-muted, #8494a7)",
                                          }}
                                      >
                                          Waiting for log data...
                                      </div>
                                  `}

                                  ${filteredLines.map(
                                      (line, i) => html`
                                          <div
                                              key=${i}
                                              data-line-index=${i}
                                              style=${{
                                                  display: "flex",
                                                  padding: "1px 12px",
                                                  color:
                                                      SEVERITY_COLORS[
                                                          line.severity
                                                      ] || "var(--color-text-primary, #e6e8eb)",
                                                  fontWeight:
                                                      line.severity === "FATAL"
                                                          ? "bold"
                                                          : "normal",
                                                  background:
                                                      line.severity === "FATAL"
                                                          ? "rgba(245, 83, 83, 0.15)"
                                                          : matchingIndices.includes(
                                                                  i
                                                            ) &&
                                                              matchingIndices[
                                                                  searchIndex
                                                              ] === i
                                                            ? "rgba(245, 158, 11, 0.1)"
                                                            : "transparent",
                                                  gap: "8px",
                                                  minHeight: "20px",
                                              }}
                                          >
                                              ${line.timestamp && html`
                                                  <span
                                                      style=${{
                                                          color: "var(--color-text-muted, #8494a7)",
                                                          flexShrink: 0,
                                                          minWidth: "80px",
                                                      }}
                                                  >
                                                      ${line.timestamp}
                                                  </span>
                                              `}
                                              <span
                                                  style=${{
                                                      flexShrink: 0,
                                                      minWidth: "44px",
                                                      fontSize: "0.9em",
                                                      opacity: 0.7,
                                                  }}
                                              >
                                                  ${line.severity}
                                              </span>
                                              ${line.source && html`
                                                  <span
                                                      style=${{
                                                          color: "var(--color-accent, #4b8df7)",
                                                          flexShrink: 0,
                                                          maxWidth: "150px",
                                                          overflow: "hidden",
                                                          textOverflow: "ellipsis",
                                                          whiteSpace: "nowrap",
                                                      }}
                                                      title=${line.source}
                                                  >
                                                      ${line.source}
                                                  </span>
                                              `}
                                              <span
                                                  style=${{
                                                      flex: 1,
                                                      wordBreak: "break-word",
                                                      whiteSpace: "pre-wrap",
                                                  }}
                                              >
                                                  ${highlightText(line.message)}
                                              </span>
                                          </div>
                                      `
                                  )}
                              </div>

                              <!-- Jump to bottom button -->
                              ${!autoScroll && html`
                                  <button
                                      onClick=${jumpToBottom}
                                      style=${{
                                          position: "absolute",
                                          bottom: "24px",
                                          right: "24px",
                                          background: "var(--color-accent, #4b8df7)",
                                          color: "#fff",
                                          border: "none",
                                          borderRadius: "20px",
                                          padding: "6px 14px",
                                          fontSize: "0.8em",
                                          cursor: "pointer",
                                          boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                                          zIndex: 10,
                                      }}
                                  >
                                      \u2193 Jump to bottom
                                  </button>
                              `}
                          `
                        : html`
                              <!-- No source selected placeholder -->
                              <div
                                  style=${{
                                      flex: 1,
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "center",
                                      color: "var(--color-text-muted, #8494a7)",
                                      fontSize: "1.1em",
                                      background: "var(--color-bg-primary, #0f1419)",
                                  }}
                              >
                                  <div style=${{ textAlign: "center" }}>
                                      <div
                                          style=${{
                                              fontSize: "2.5em",
                                              marginBottom: "12px",
                                              opacity: 0.4,
                                          }}
                                      >
                                          \uD83D\uDCDC
                                      </div>
                                      <div>Select a log file to start viewing</div>
                                  </div>
                              </div>
                          `}
                </div>
            </div>
        </div>
    `;
}
