/**
 * FieldAnalysisTab — Preact component for field log analysis.
 *
 * Migrated from vanilla JS (field_analysis.js) as part of task 7.4 of the
 * dashboard-frontend-migration.
 *
 * Provides log directory browsing, analysis execution with live progress
 * (WebSocket + polling fallback), result visualization (summary, motors,
 * detection, failures, timeline), and side-by-side comparison of runs.
 *
 * @module tabs/FieldAnalysisTab
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useCallback,
    useMemo,
    useRef,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch, formatBytes, formatDuration, formatDate } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { registerTab } from "../tabRegistry.js";
import { getChartColor } from "../utils/chartColors.mjs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 30000;
const PROGRESS_POLL_MS = 2000;
const PROGRESS_TIMEOUT_MS = 300000; // 5 minutes

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------

/**
 * Call the analysis API. Returns parsed JSON or throws on error.
 * @param {string} path - Path appended to /api/analysis
 * @param {string} [method='GET']
 * @param {Object|null} [body=null]
 * @returns {Promise<Object>}
 */
async function analysisApi(path, method = "GET", body = null) {
    const opts = { method, headers: {} };
    if (body) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
    }
    if (method === "GET") {
        // GET requests: use safeFetch (null on error is fine for listing)
        const data = await safeFetch(`/api/analysis${path}`, opts);
        if (data === null) {
            throw new Error(`API request failed: GET /api/analysis${path}`);
        }
        return data;
    }
    // POST/PUT/DELETE: use raw fetch to capture server error details
    const response = await fetch(`/api/analysis${path}`, opts);
    if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
            const errBody = await response.json();
            detail = errBody.detail || JSON.stringify(errBody);
        } catch {
            // ignore parse failures
        }
        throw new Error(detail);
    }
    return await response.json();
}

// ---------------------------------------------------------------------------
// Utility helpers (local to this module)
// ---------------------------------------------------------------------------

/** Return a colour for health scores. */
function getHealthColor(score) {
    if (score == null || isNaN(score)) return getChartColor("--color-text-muted");
    if (score >= 0.8) return getChartColor("--color-success");
    if (score >= 0.5) return getChartColor("--color-warning");
    return getChartColor("--color-error");
}

/** CSS class for comparison deltas. */
function getDeltaClass(value, higherIsBetter = true) {
    if (value == null || value === 0) return "delta-neutral";
    const positive = higherIsBetter ? value > 0 : value < 0;
    return positive ? "delta-positive" : "delta-negative";
}

/** Truncate a job ID for display. */
function truncateId(id) {
    if (!id) return "--";
    return id.length > 12 ? id.substring(0, 12) + "..." : id;
}

/** Format a timestamp for the timeline.
 *  Handles both Unix epoch seconds (float) and ISO strings.
 */
function formatTimestamp(ts, tsHuman) {
    // Prefer pre-formatted human-readable string from analyzer
    if (tsHuman) return tsHuman;
    if (!ts) return "--:--:--";
    try {
        // If numeric and looks like Unix seconds (>1e9), convert to ms
        const ms = typeof ts === "number" && ts > 1e9 ? ts * 1000 : ts;
        const d = new Date(ms);
        if (isNaN(d.getTime())) return String(ts);
        return d.toLocaleTimeString("en-US", { hour12: false });
    } catch {
        return String(ts);
    }
}

/** Badge style for log levels. */
function levelBadgeStyle(level) {
    switch ((level || "").toUpperCase()) {
        case "ERROR":
            return "background:var(--badge-error-bg);color:var(--badge-error-color)";
        case "WARN":
        case "WARNING":
            return "background:var(--badge-warning-bg);color:var(--badge-warning-color)";
        case "INFO":
            return "background:var(--badge-info-bg);color:var(--badge-info-color)";
        case "DEBUG":
            return "background:var(--badge-debug-bg);color:var(--badge-debug-color)";
        default:
            return "background:var(--badge-debug-bg);color:var(--badge-debug-color)";
    }
}

/** Severity colour for critical issues. */
function severityColor(sev) {
    switch ((sev || "").toLowerCase()) {
        case "critical":
            return "var(--accent-danger)";
        case "high":
            return "var(--color-severity-high)";
        case "medium":
            return "var(--accent-warning)";
        default:
            return "var(--accent-info)";
    }
}

/** Status badge colours. */
const STATUS_COLORS = {
    completed: "background:var(--badge-success-bg);color:var(--badge-success-color)",
    running: "background:var(--badge-info-bg);color:var(--badge-info-color)",
    failed: "background:var(--badge-error-bg);color:var(--badge-error-color)",
    pending: "background:var(--badge-debug-bg);color:var(--badge-debug-color)",
};

/** Lazily resolve delta colours for comparison from CSS custom properties. */
function getDeltaColors() {
    return {
        "delta-positive": getChartColor("--color-success"),
        "delta-negative": getChartColor("--color-error"),
        "delta-neutral": getChartColor("--color-text-muted"),
    };
}

// ---------------------------------------------------------------------------
// Views — enum-like for managing which view is active
// ---------------------------------------------------------------------------

const VIEW_DIRECTORY = "directory";
const VIEW_RESULTS = "results";
const VIEW_COMPARE = "compare";

// ---------------------------------------------------------------------------
// Sub-components: Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }) {
    const style = STATUS_COLORS[status] || STATUS_COLORS.pending;
    return html`
        <span
            class="fa-badge"
            style="${style};padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:600"
        >
            ${status || "unknown"}
        </span>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Progress bar
// ---------------------------------------------------------------------------

function ProgressBar({ visible, percent, message }) {
    if (!visible) return null;

    return html`
        <div class="stats-panel" style="margin-bottom:var(--spacing-lg)">
            <h3>Analysis Progress</h3>
            <div
                class="analysis-progress-bar"
                style="height:8px;background:var(--bg-tertiary);border-radius:4px;overflow:hidden;margin-bottom:var(--spacing-sm)"
            >
                <div
                    class="fa-progress-fill"
                    style="height:100%;width:${percent != null ? percent : 0}%;background:var(--accent-primary);border-radius:4px;transition:width 0.3s ease"
                ></div>
            </div>
            <p
                class="fa-progress-text"
                style="font-size:0.8125rem;color:var(--text-secondary);margin:0"
            >
                ${percent != null ? `${percent}% — ` : ""}${message || ""}
            </p>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Mini stat card
// ---------------------------------------------------------------------------

function MiniStat({ value, label, variant }) {
    const cls = variant ? ` ${variant}` : "";
    return html`
        <div class="mini-stat-card${cls}">
            <div class="mini-stat-value">${value}</div>
            <div class="mini-stat-label">${label}</div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Inline directory picker (for browsing arbitrary paths)
// ---------------------------------------------------------------------------

function InlineDirectoryPicker({ visible, onSelect, onClose, disabled }) {
    const [currentPath, setCurrentPath] = useState("/home");
    const [entries, setEntries] = useState([]);
    const [parentPath, setParentPath] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const loadDirectory = useCallback(async (path) => {
        setLoading(true);
        setError(null);
        const url = `/api/filesystem/browse?path=${encodeURIComponent(path)}&dirs_only=true`;
        const data = await safeFetch(url);
        if (!data) {
            setError("Connection error");
            setEntries([]);
            setParentPath(null);
            setLoading(false);
            return;
        }
        if (data.error) {
            setError(data.error);
            setEntries([]);
            setParentPath(null);
            setLoading(false);
            return;
        }
        setCurrentPath(data.path || path || "/");
        setEntries(data.entries || []);
        setParentPath(data.parent || null);
        setLoading(false);
    }, []);

    useEffect(() => {
        if (visible) loadDirectory(currentPath);
    }, [visible]);

    const breadcrumbs = useMemo(() => {
        if (!currentPath) return [];
        const parts = currentPath.split("/").filter(Boolean);
        return parts.map((part, i) => ({
            name: part,
            path: "/" + parts.slice(0, i + 1).join("/"),
        }));
    }, [currentPath]);

    const fmtDate = (ts) => {
        if (!ts) return "";
        try {
            const d = new Date(ts);
            if (isNaN(d.getTime())) return "";
            return d.toLocaleDateString();
        } catch {
            return "";
        }
    };

    if (!visible) return null;

    return html`
        <div
            style=${{
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-md)",
                background: "var(--bg-tertiary)",
                padding: "var(--spacing-md)",
                marginTop: "var(--spacing-sm)",
                marginBottom: "var(--spacing-md)",
            }}
        >
            <!-- Header: breadcrumbs + close -->
            <div
                style=${{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "var(--spacing-sm)",
                    gap: "var(--spacing-sm)",
                }}
            >
                <div
                    style=${{
                        display: "flex",
                        flexWrap: "wrap",
                        alignItems: "center",
                        gap: "2px",
                        fontSize: "0.8rem",
                        color: "var(--text-secondary)",
                        minWidth: 0,
                        overflow: "hidden",
                    }}
                >
                    <span
                        style=${{ cursor: "pointer", color: "var(--accent-color)" }}
                        onClick=${() => loadDirectory("/")}
                    >/</span>
                    ${breadcrumbs.map(
                        (bc, i) => html`
                            <span style=${{ color: "var(--text-secondary)" }}>${" > "}</span>
                            <span
                                style=${{
                                    cursor: "pointer",
                                    color:
                                        i === breadcrumbs.length - 1
                                            ? "var(--text-primary)"
                                            : "var(--accent-color)",
                                    fontWeight:
                                        i === breadcrumbs.length - 1 ? "600" : "normal",
                                }}
                                onClick=${() => loadDirectory(bc.path)}
                            >${bc.name}</span>
                        `
                    )}
                </div>
                <button
                    class="btn btn-sm"
                    style=${{
                        background: "transparent",
                        border: "none",
                        color: "var(--text-secondary)",
                        cursor: "pointer",
                        fontSize: "1rem",
                        padding: "2px 6px",
                        lineHeight: "1",
                        flexShrink: "0",
                    }}
                    onClick=${onClose}
                    title="Close browser"
                >✕</button>
            </div>

            <!-- Directory listing -->
            <div
                style=${{
                    maxHeight: "240px",
                    overflowY: "auto",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-md)",
                    background: "var(--bg-secondary)",
                }}
            >
                ${loading && html`
                    <div style=${{
                        padding: "var(--spacing-md)",
                        textAlign: "center",
                        color: "var(--text-secondary)",
                    }}>Loading...</div>
                `}
                ${error && html`
                    <div style=${{
                        padding: "var(--spacing-md)",
                        color: "var(--danger-color, #e74c3c)",
                    }}>${error}</div>
                `}
                ${!loading && !error && html`
                    ${parentPath != null && html`
                        <div
                            style=${{
                                display: "flex",
                                justifyContent: "space-between",
                                padding: "var(--spacing-sm) var(--spacing-md)",
                                cursor: "pointer",
                                borderBottom: "1px solid var(--border-color)",
                                color: "var(--text-secondary)",
                            }}
                            onClick=${() => loadDirectory(parentPath)}
                        >
                            <span>..</span>
                        </div>
                    `}
                    ${entries.map(
                        (entry) => html`
                            <div
                                style=${{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    padding: "var(--spacing-sm) var(--spacing-md)",
                                    cursor: "pointer",
                                    borderBottom: "1px solid var(--border-color)",
                                    color: "var(--text-primary)",
                                }}
                                onClick=${() => loadDirectory(entry.path)}
                            >
                                <span style=${{ fontWeight: "500" }}>${entry.name}/</span>
                                <span
                                    style=${{
                                        fontSize: "0.75rem",
                                        color: "var(--text-secondary)",
                                        flexShrink: "0",
                                        marginLeft: "var(--spacing-md)",
                                    }}
                                >${fmtDate(entry.modified)}</span>
                            </div>
                        `
                    )}
                    ${!parentPath && entries.length === 0 && html`
                        <div style=${{
                            padding: "var(--spacing-md)",
                            color: "var(--text-secondary)",
                            textAlign: "center",
                        }}>No subdirectories</div>
                    `}
                `}
            </div>

            <!-- Select button -->
            <div style=${{ marginTop: "var(--spacing-sm)", textAlign: "right" }}>
                <button
                    class="btn btn-sm btn-primary"
                    disabled=${disabled || loading}
                    onClick=${() => onSelect(currentPath)}
                >
                    Select This Directory
                </button>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Log directory card
// ---------------------------------------------------------------------------

function LogDirCard({ dir, onAnalyze, disabled }) {
    const name = dir.name || dir.directory || "--";
    return html`
        <div class="card fa-log-dir-card" style="margin-bottom:var(--spacing-md)">
            <div
                style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--spacing-sm)"
            >
                <div>
                    <span style="font-weight:600;color:var(--text-primary)">${name}</span>
                    ${dir.arm_id != null &&
                    html`
                        <span
                            class="fa-badge"
                            style="background:var(--badge-info-bg);color:var(--badge-info-color);padding:2px 8px;border-radius:4px;font-size:0.7rem;font-weight:600;margin-left:8px"
                        >
                            Arm ${dir.arm_id}
                        </span>
                    `}
                </div>
                <button
                    class="btn btn-sm btn-primary"
                    disabled=${disabled}
                    onClick=${() => onAnalyze(dir.name || dir.directory || dir.path)}
                >
                    Analyze
                </button>
            </div>
            <div
                style="display:flex;gap:var(--spacing-lg);font-size:0.8125rem;color:var(--text-secondary)"
            >
                <span>Date: ${formatDate(dir.date || dir.created)}</span>
                <span>Size: ${formatBytes(dir.size_bytes || dir.size)}</span>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: History table
// ---------------------------------------------------------------------------

function HistoryTable({
    jobs,
    compareSelected,
    onToggleCompare,
    onViewAnalysis,
}) {
    if (jobs.length === 0) {
        return html`
            <div class="empty-state">
                <p>No analysis runs yet.</p>
                <p
                    style="color:var(--text-muted);font-size:0.8125rem;margin-top:0.5rem"
                >
                    Select a log directory above and click Analyze.
                </p>
            </div>
        `;
    }

    return html`
        <div class="history-table">
            <table>
                <thead>
                    <tr>
                        <th style="width:30px"></th>
                        <th>Job ID</th>
                        <th>Log Directory</th>
                        <th>Date</th>
                        <th>Status</th>
                        <th>Success Rate</th>
                        <th>Total Picks</th>
                    </tr>
                </thead>
                <tbody>
                    ${jobs.map((job) => {
                        const completed = job.status === "completed";
                        const isChecked = compareSelected.includes(job.job_id);
                        return html`
                            <tr
                                key=${job.job_id}
                                class="fa-history-row"
                                style=${completed ? "cursor:pointer" : ""}
                                onClick=${completed
                                    ? () => onViewAnalysis(job.job_id)
                                    : undefined}
                            >
                                <td>
                                    ${completed &&
                                    html`
                                        <input
                                            type="checkbox"
                                            class="fa-compare-check"
                                            checked=${isChecked}
                                            onClick=${(e) => {
                                                e.stopPropagation();
                                                onToggleCompare(job.job_id);
                                            }}
                                        />
                                    `}
                                </td>
                                <td title=${job.job_id}>
                                    ${truncateId(job.job_id)}
                                </td>
                                <td>
                                    ${job.log_directory || job.log_dir || "--"}
                                </td>
                                <td>
                                    ${formatDate(
                                        job.created || job.date || job.started_at
                                    )}
                                </td>
                                <td><${StatusBadge} status=${job.status} /></td>
                                <td>
                                    ${job.success_rate != null
                                        ? (job.success_rate * 100).toFixed(1) + "%"
                                        : "--"}
                                </td>
                                <td>
                                    ${job.total_picks != null
                                        ? job.total_picks
                                        : "--"}
                                </td>
                            </tr>
                        `;
                    })}
                </tbody>
            </table>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Result tab bar
// ---------------------------------------------------------------------------

const RESULT_TABS = [
    { id: "summary", label: "Summary" },
    { id: "motors", label: "Motors" },
    { id: "detection", label: "Detection" },
    { id: "failures", label: "Failures" },
    { id: "timeline", label: "Timeline" },
];

function ResultTabBar({ activeTab, onSwitch }) {
    return html`
        <div class="analysis-tabs">
            ${RESULT_TABS.map(
                (tab) => html`
                    <button
                        key=${tab.id}
                        class="fa-result-tab ${activeTab === tab.id ? "active" : ""}"
                        onClick=${() => onSwitch(tab.id)}
                    >
                        ${tab.label}
                    </button>
                `
            )}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Summary pane
// ---------------------------------------------------------------------------

function SummaryPane({ data, loading, error }) {
    if (loading) {
        return html`<div class="section-loading">Loading summary...</div>`;
    }
    if (error) {
        return html`<div class="section-error">Failed to load summary: ${error}</div>`;
    }
    if (!data) return null;

    if (data.status === "running" || data.status === "pending") {
        return html`
            <div class="empty-state">
                <p>Analysis in progress...</p>
                <p
                    style="color:var(--text-muted);font-size:0.8125rem;margin-top:0.5rem"
                >
                    Results will appear when the analysis completes.
                </p>
            </div>
        `;
    }

    const healthColor = getHealthColor(data.overall_health);
    const healthPct =
        data.overall_health != null
            ? (data.overall_health * 100).toFixed(0)
            : "--";

    return html`
        <!-- Health Banner -->
        <div
            class="card"
            style="border-left:4px solid ${healthColor};margin-bottom:var(--spacing-lg)"
        >
            <div
                style="display:flex;align-items:center;gap:var(--spacing-lg)"
            >
                <div style="text-align:center;min-width:100px">
                    <div
                        style="font-size:2.5rem;font-weight:700;color:${healthColor}"
                    >
                        ${healthPct}${healthPct !== "--" ? "%" : ""}
                    </div>
                    <div
                        style="font-size:0.75rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px"
                    >
                        Overall Health
                    </div>
                </div>
                <div style="flex:1">
                    <div
                        style="height:8px;background:var(--bg-tertiary);border-radius:4px;overflow:hidden"
                    >
                        <div
                            style="height:100%;width:${data.overall_health != null
                                ? data.overall_health * 100
                                : 0}%;background:${healthColor};border-radius:4px;transition:width 0.3s ease"
                        ></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Session Stats -->
        <div class="stat-cards-row" style="margin-bottom:var(--spacing-lg)">
            <${MiniStat}
                value=${formatDuration(data.duration || data.session_duration)}
                label="Duration"
            />
            <${MiniStat}
                value=${data.total_picks != null ? data.total_picks : "--"}
                label="Total Picks"
            />
            <${MiniStat}
                value=${data.success_rate != null
                    ? (data.success_rate * 100).toFixed(1) + "%"
                    : "--"}
                label="Success Rate"
                variant=${data.success_rate >= 0.8
                    ? "success"
                    : data.success_rate >= 0.5
                      ? ""
                      : "danger"}
            />
            <${MiniStat}
                value=${data.error_count != null ? data.error_count : "--"}
                label="Errors"
                variant=${data.error_count > 0 ? "danger" : ""}
            />
        </div>

        <!-- Key Findings -->
        <${FindingsList} findings=${data.key_findings} />

        <!-- Critical Issues -->
        <${CriticalIssuesList} issues=${data.critical_issues} />
    `;
}

function FindingsList({ findings }) {
    if (!findings || findings.length === 0) return null;
    return html`
        <div class="card" style="margin-bottom:var(--spacing-lg)">
            <h3>Key Findings</h3>
            <ul
                style="list-style:none;padding:0;display:flex;flex-direction:column;gap:var(--spacing-sm)"
            >
                ${findings.map(
                    (f, i) => html`
                        <li
                            key=${i}
                            style="padding:var(--spacing-sm) var(--spacing-md);background:var(--bg-tertiary);border-radius:6px;font-size:0.875rem;color:var(--text-primary)"
                        >
                            ${f}
                        </li>
                    `
                )}
            </ul>
        </div>
    `;
}

function CriticalIssuesList({ issues }) {
    if (!issues || issues.length === 0) return null;
    return html`
        <div class="card">
            <h3>Critical Issues</h3>
            <div
                style="display:flex;flex-direction:column;gap:var(--spacing-sm)"
            >
                ${issues.map(
                    (issue, i) => html`
                        <div
                            key=${i}
                            class="alert-item"
                            style="border-left-color:${severityColor(issue.severity)}"
                        >
                            <div class="alert-content">
                                <div class="alert-title">
                                    ${issue.title || issue.message || "--"}
                                </div>
                                ${issue.description &&
                                html`
                                    <div class="alert-message">
                                        ${issue.description}
                                    </div>
                                `}
                            </div>
                            <span
                                class="fa-badge"
                                style="background:${severityColor(issue.severity)}22;color:${severityColor(issue.severity)};padding:2px 8px;border-radius:4px;font-size:0.7rem;font-weight:600"
                            >
                                ${issue.severity || "info"}
                            </span>
                        </div>
                    `
                )}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Motors pane
// ---------------------------------------------------------------------------

function MotorsPane({ data, loading, error }) {
    if (loading) {
        return html`<div class="section-loading">Loading motor data...</div>`;
    }
    if (error) {
        return html`<div class="section-error">Failed to load motor data: ${error}</div>`;
    }
    if (!data) return null;

    const motors = data.motors || data.joints || [];
    if (motors.length === 0) {
        return html`<div class="empty-state">No motor data available.</div>`;
    }

    return html`
        <div class="motors-grid">
            ${motors.map(
                (m, i) => html`<${MotorCard} key=${i} motor=${m} />`
            )}
        </div>
    `;
}

function MotorCard({ motor: m }) {
    const healthScore = m.health_score != null ? m.health_score : null;
    const healthColor = getHealthColor(healthScore);
    const healthPct =
        healthScore != null ? (healthScore * 100).toFixed(0) : "--";

    return html`
        <div class="motor-card">
            <div class="motor-header">
                <span class="motor-name">${m.joint_id || m.joint_name || "--"}</span>
                <span
                    style="font-size:0.8125rem;font-weight:600;color:${healthColor}"
                >
                    ${healthPct}${healthPct !== "--" ? "%" : ""}
                </span>
            </div>

            <!-- Health bar -->
            <div
                style="height:6px;background:var(--bg-primary);border-radius:3px;overflow:hidden;margin-bottom:var(--spacing-sm)"
            >
                <div
                    style="height:100%;width:${healthScore != null
                        ? healthScore * 100
                        : 0}%;background:${healthColor};border-radius:3px;transition:width 0.3s ease"
                ></div>
            </div>

            <${MotorMetric} label="Temperature" data=${m.temperature} unit="\u00B0C" />
            <${MotorMetric} label="Current" data=${m.current} unit="A" />

            ${m.position_error != null &&
            html`
                <div class="motor-metric">
                    <span class="motor-metric-label">Position Error</span>
                    <span class="motor-metric-value">
                        ${Number(m.position_error).toFixed(2)}\u00B0
                    </span>
                </div>
            `}

            ${m.error_flags &&
            m.error_flags.length > 0 &&
            html`
                <div style="margin-top:var(--spacing-sm)">
                    ${m.error_flags.map(
                        (flag, i) => html`
                            <span
                                key=${i}
                                class="fa-badge"
                                style="background:var(--badge-error-bg);color:var(--badge-error-color);padding:1px 6px;border-radius:3px;font-size:0.7rem;margin-right:4px"
                            >
                                ${flag}
                            </span>
                        `
                    )}
                </div>
            `}
        </div>
    `;
}

function MotorMetric({ label, data, unit }) {
    if (!data) return null;

    if (typeof data === "object") {
        return html`
            <div class="motor-metric">
                <span class="motor-metric-label">${label}</span>
                <span class="motor-metric-value">
                    ${data.avg != null ? Number(data.avg).toFixed(1) : "--"}
                    <span style="color:var(--text-muted);font-size:0.75rem">avg</span>
                    / ${data.max != null ? Number(data.max).toFixed(1) : "--"}
                    <span style="color:var(--text-muted);font-size:0.75rem">max</span>
                    ${unit}
                </span>
            </div>
        `;
    }

    return html`
        <div class="motor-metric">
            <span class="motor-metric-label">${label}</span>
            <span class="motor-metric-value">${Number(data).toFixed(1)}${unit}</span>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Detection pane
// ---------------------------------------------------------------------------

function DetectionPane({ data, loading, error }) {
    if (loading) {
        return html`<div class="section-loading">Loading detection data...</div>`;
    }
    if (error) {
        return html`<div class="section-error">Failed to load detection data: ${error}</div>`;
    }
    if (!data) return null;

    const acceptRate =
        data.acceptance_rate != null
            ? (data.acceptance_rate * 100).toFixed(1)
            : "--";
    const borderSkip =
        data.border_skip_rate != null
            ? (data.border_skip_rate * 100).toFixed(1)
            : "--";

    return html`
        <!-- Key Metrics -->
        <div class="stat-cards-row" style="margin-bottom:var(--spacing-lg)">
            <${MiniStat}
                value="${acceptRate}${acceptRate !== "--" ? "%" : ""}"
                label="Acceptance Rate"
                variant="success"
            />
            <${MiniStat}
                value="${borderSkip}${borderSkip !== "--" ? "%" : ""}"
                label="Border Skip Rate"
            />
        </div>

        <!-- Timing Stats -->
        <${TimingStats} timing=${data.timing} />

        <!-- Confidence Distribution -->
        <${ConfidenceDistribution} dist=${data.confidence_distribution} />
    `;
}

function TimingStats({ timing }) {
    if (!timing) return null;
    return html`
        <div class="card" style="margin-bottom:var(--spacing-lg)">
            <h3>Timing Stats</h3>
            <div class="stat-cards-row">
                <${MiniStat}
                    value=${timing.avg != null ? timing.avg.toFixed(1) + "ms" : "--"}
                    label="Average"
                />
                <${MiniStat}
                    value=${timing.p95 != null ? timing.p95.toFixed(1) + "ms" : "--"}
                    label="P95"
                />
                <${MiniStat}
                    value=${timing.max != null ? timing.max.toFixed(1) + "ms" : "--"}
                    label="Max"
                />
            </div>
        </div>
    `;
}

function ConfidenceDistribution({ dist }) {
    if (!dist || Object.keys(dist).length === 0) return null;

    const entries = Object.entries(dist);
    const maxVal = Math.max(...entries.map(([, v]) => v), 1);

    return html`
        <div class="card">
            <h3>Confidence Distribution</h3>
            <div
                style="display:flex;flex-direction:column;gap:var(--spacing-sm)"
            >
                ${entries.map(
                    ([bucket, count]) => html`
                        <div
                            key=${bucket}
                            style="display:flex;align-items:center;gap:var(--spacing-md)"
                        >
                            <span
                                style="min-width:80px;font-size:0.8125rem;color:var(--text-secondary);text-align:right"
                            >
                                ${bucket}
                            </span>
                            <div
                                style="flex:1;height:20px;background:var(--bg-tertiary);border-radius:4px;overflow:hidden;position:relative"
                            >
                                <div
                                    style="height:100%;width:${(count / maxVal) * 100}%;background:linear-gradient(90deg,var(--accent-primary),var(--accent-info));border-radius:4px;transition:width 0.3s ease"
                                ></div>
                            </div>
                            <span
                                style="min-width:40px;font-size:0.8125rem;color:var(--text-primary);font-weight:500"
                            >
                                ${count}
                            </span>
                        </div>
                    `
                )}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Failures pane
// ---------------------------------------------------------------------------

function FailuresPane({ data, loading, error }) {
    if (loading) {
        return html`<div class="section-loading">Loading failure data...</div>`;
    }
    if (error) {
        return html`<div class="section-error">Failed to load failure data: ${error}</div>`;
    }
    if (!data) return null;

    return html`
        <!-- Emergency Shutdowns & Recovery -->
        <div class="stat-cards-row" style="margin-bottom:var(--spacing-lg)">
            <${MiniStat}
                value=${data.emergency_shutdowns != null ? data.emergency_shutdowns : "--"}
                label="Emergency Shutdowns"
                variant=${data.emergency_shutdowns > 0 ? "danger" : ""}
            />
            <${MiniStat}
                value=${data.recovery_overhead != null
                    ? data.recovery_overhead.toFixed(1) + "%"
                    : "--"}
                label="Recovery Overhead"
            />
        </div>

        <${FailureByPhase} phases=${data.failure_by_phase} />
        <${TopFailureReasons} reasons=${data.top_failure_reasons} />
        <${ShutdownDetails} details=${data.shutdown_details} />
    `;
}

function FailureByPhase({ phases }) {
    if (!phases || Object.keys(phases).length === 0) return null;

    const entries = Object.entries(phases);
    const maxVal = Math.max(...entries.map(([, v]) => v), 1);

    return html`
        <div class="card" style="margin-bottom:var(--spacing-lg)">
            <h3>Failures by Phase</h3>
            <div
                style="display:flex;flex-direction:column;gap:var(--spacing-sm)"
            >
                ${entries.map(
                    ([phase, count]) => html`
                        <div
                            key=${phase}
                            style="display:flex;align-items:center;gap:var(--spacing-md)"
                        >
                            <span
                                style="min-width:120px;font-size:0.8125rem;color:var(--text-secondary);text-align:right"
                            >
                                ${phase}
                            </span>
                            <div
                                style="flex:1;height:20px;background:var(--bg-tertiary);border-radius:4px;overflow:hidden"
                            >
                                <div
                                    style="height:100%;width:${(count / maxVal) * 100}%;background:linear-gradient(90deg,var(--gradient-failure-start),var(--gradient-failure-end));border-radius:4px;transition:width 0.3s ease"
                                ></div>
                            </div>
                            <span
                                style="min-width:40px;font-size:0.8125rem;color:var(--text-primary);font-weight:500"
                            >
                                ${count}
                            </span>
                        </div>
                    `
                )}
            </div>
        </div>
    `;
}

function TopFailureReasons({ reasons }) {
    if (!reasons || reasons.length === 0) return null;
    return html`
        <div class="card" style="margin-bottom:var(--spacing-lg)">
            <h3>Top Failure Reasons</h3>
            <div
                style="display:flex;flex-direction:column;gap:var(--spacing-xs)"
            >
                ${reasons.map((r, i) => {
                    const reason =
                        typeof r === "string" ? r : r.reason || r.message || "--";
                    const count = typeof r === "object" ? r.count : null;
                    return html`
                        <div
                            key=${i}
                            style="display:flex;align-items:center;gap:var(--spacing-md);padding:var(--spacing-sm) var(--spacing-md);background:var(--bg-tertiary);border-radius:6px"
                        >
                            <span
                                style="font-weight:700;color:var(--text-muted);min-width:24px"
                            >
                                ${i + 1}.
                            </span>
                            <span
                                style="flex:1;font-size:0.875rem;color:var(--text-primary)"
                            >
                                ${reason}
                            </span>
                            ${count != null &&
                            html`
                                <span
                                    style="font-size:0.8125rem;color:var(--text-secondary);font-weight:600"
                                >
                                    ${count}x
                                </span>
                            `}
                        </div>
                    `;
                })}
            </div>
        </div>
    `;
}

function ShutdownDetails({ details }) {
    if (!details || details.length === 0) return null;
    return html`
        <div class="card">
            <h3>Shutdown Details</h3>
            <div
                style="display:flex;flex-direction:column;gap:var(--spacing-sm)"
            >
                ${details.map(
                    (d, i) => html`
                        <div key=${i} class="alert-item critical">
                            <div class="alert-content">
                                <div class="alert-title">
                                    ${d.reason || d.message || "Emergency Shutdown"}
                                </div>
                                <div class="alert-time">
                                    ${formatDate(d.timestamp || d.time)}
                                </div>
                            </div>
                        </div>
                    `
                )}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Timeline pane
// ---------------------------------------------------------------------------

function TimelinePane({ data, loading, error }) {
    const [activeFilter, setActiveFilter] = useState("ALL");

    // Stabilize events reference to prevent useMemo infinite loop
    const events = useMemo(
        () => (data ? data.events || data.timeline || [] : []),
        [data]
    );
    const total = data ? data.total || events.length : 0;
    const truncated = total > events.length;

    const filteredEvents = useMemo(() => {
        if (activeFilter === "ALL") return events;
        return events.filter(
            (ev) => (ev.level || "INFO").toUpperCase() === activeFilter
        );
    }, [events, activeFilter]);

    if (loading) {
        return html`<div class="section-loading">Loading timeline...</div>`;
    }
    if (error) {
        return html`<div class="section-error">Failed to load timeline: ${error}</div>`;
    }
    if (!data) return null;

    return html`
        <!-- Level Filters -->
        <div
            style="display:flex;gap:var(--spacing-sm);margin-bottom:var(--spacing-md)"
        >
            ${["ALL", "ERROR", "WARN", "INFO"].map(
                (level) => html`
                    <button
                        key=${level}
                        class="btn btn-sm ${activeFilter === level
                            ? "btn-primary"
                            : "btn-secondary"}"
                        onClick=${() => setActiveFilter(level)}
                    >
                        ${level}
                    </button>
                `
            )}
        </div>

        ${truncated &&
        html`
            <div
                style="font-size:0.8125rem;color:var(--text-muted);margin-bottom:var(--spacing-sm)"
            >
                Showing ${events.length} of ${total} events
            </div>
        `}

        <!-- Event List -->
        <div
            class="fa-timeline-list"
            style="max-height:500px;overflow-y:auto;display:flex;flex-direction:column;gap:2px"
        >
            ${filteredEvents.length === 0
                ? html`<div class="empty-state">No events to display.</div>`
                : filteredEvents.map(
                      (ev, i) => html`<${TimelineEvent} key=${i} event=${ev} />`
                  )}
        </div>
    `;
}

function TimelineEvent({ event: ev }) {
    const level = (ev.level || "INFO").toUpperCase();
    const style = levelBadgeStyle(level);
    // Analyzer uses "event" field for text; fall back to "message"
    const text = ev.event || ev.message || "";

    return html`
        <div
            class="fa-timeline-event"
            style="padding:var(--spacing-sm) var(--spacing-md);background:var(--bg-card);border:1px solid var(--border-color);border-radius:6px;display:flex;align-items:center;gap:var(--spacing-md);font-size:0.8125rem"
        >
            <span
                style="color:var(--text-muted);font-family:'Courier New',monospace;min-width:170px;flex-shrink:0"
            >
                ${formatTimestamp(ev.timestamp, ev.timestamp_human)}
            </span>
            ${ev.node &&
            html`
                <span
                    class="fa-badge"
                    style="background:var(--bg-tertiary);color:var(--text-secondary);padding:1px 6px;border-radius:3px;font-size:0.7rem;flex-shrink:0"
                >
                    ${ev.node}
                </span>
            `}
            <span
                class="fa-badge"
                style="${style};padding:1px 6px;border-radius:3px;font-size:0.7rem;font-weight:600;flex-shrink:0"
            >
                ${level}
            </span>
            ${ev.event_type &&
            html`
                <span
                    style="color:var(--text-secondary);font-weight:500;flex-shrink:0"
                >
                    ${ev.event_type}
                </span>
            `}
            <span
                style="color:var(--text-primary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                title=${text}
            >
                ${text}
            </span>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-components: Comparison view
// ---------------------------------------------------------------------------

function CompareView({ data, loading, error, jobA, jobB, onBack }) {
    if (loading) {
        return html`<div class="section-loading">Loading comparison...</div>`;
    }
    if (error) {
        return html`<div class="section-error">Failed to compare: ${error}</div>`;
    }
    if (!data) return null;

    const a = data.a || data.job_a || {};
    const b = data.b || data.job_b || {};

    return html`
        <div
            style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--spacing-lg)"
        >
            <h3 style="color:var(--text-primary);font-size:1.25rem">
                Analysis Comparison
            </h3>
            <button class="btn btn-sm btn-secondary" onClick=${onBack}>
                Back to Directory
            </button>
        </div>

        <div
            style="display:grid;grid-template-columns:auto 1fr auto 1fr;gap:var(--spacing-sm);align-items:center;margin-bottom:var(--spacing-lg);font-size:0.8125rem;color:var(--text-secondary)"
        >
            <span style="font-weight:600">A:</span>
            <span>${a.log_directory || a.job_id || jobA || "--"}</span>
            <span style="font-weight:600">B:</span>
            <span>${b.log_directory || b.job_id || jobB || "--"}</span>
        </div>

        <${CompareSection}
            title="Pick Performance"
            rows=${[
                compareRow("Success Rate", a.success_rate, b.success_rate, true, fmtPct),
                compareRow("Total Picks", a.total_picks, b.total_picks, true),
                compareRow("Errors", a.error_count, b.error_count, false),
            ]}
        />

        <${CompareSection}
            title="Motor Health"
            rows=${[
                compareRow("Avg Health", a.avg_motor_health, b.avg_motor_health, true, fmtPct),
                compareRow("Max Temperature", a.max_temperature, b.max_temperature, false, fmtTemp),
            ]}
        />

        <${CompareSection}
            title="Detection Performance"
            rows=${[
                compareRow("Acceptance Rate", a.acceptance_rate, b.acceptance_rate, true, fmtPct),
                compareRow("Avg Latency", a.avg_latency, b.avg_latency, false, fmtMs),
            ]}
        />

        <${CompareSection}
            title="Session Health"
            rows=${[
                compareRow("Overall Health", a.overall_health, b.overall_health, true, fmtPct),
                compareRow("Duration", a.duration, b.duration, false, (v) => formatDuration(v)),
                compareRow("Emergency Stops", a.emergency_shutdowns, b.emergency_shutdowns, false),
            ]}
        />
    `;
}

/** Format helpers for comparison */
function fmtPct(v) {
    return v != null ? (v * 100).toFixed(1) + "%" : "--";
}

function fmtTemp(v) {
    return v != null ? v.toFixed(1) + "\u00B0C" : "--";
}

function fmtMs(v) {
    return v != null ? v.toFixed(1) + "ms" : "--";
}

/** Build a comparison row data object. */
function compareRow(label, valA, valB, higherIsBetter, fmt) {
    const format = fmt || ((v) => (v != null ? String(v) : "--"));
    const delta = valA != null && valB != null ? valB - valA : null;
    const deltaClass =
        delta != null ? getDeltaClass(delta, higherIsBetter) : "delta-neutral";
    const deltaColor = getDeltaColors()[deltaClass] || getChartColor("--color-text-muted");
    const deltaStr =
        delta != null ? (delta > 0 ? "+" : "") + Number(delta).toFixed(2) : "";

    return { label, valA, valB, format, deltaColor, deltaStr };
}

function CompareSection({ title, rows }) {
    return html`
        <div class="card" style="margin-bottom:var(--spacing-lg)">
            <h3>${title}</h3>
            <div
                style="display:flex;flex-direction:column;gap:var(--spacing-sm)"
            >
                ${rows.map(
                    (row, i) => html`
                        <div
                            key=${i}
                            style="display:grid;grid-template-columns:140px 1fr 80px 1fr;gap:var(--spacing-md);align-items:center;padding:var(--spacing-xs) 0;border-bottom:1px solid var(--border-color)"
                        >
                            <span
                                style="font-size:0.8125rem;color:var(--text-secondary)"
                            >
                                ${row.label}
                            </span>
                            <span
                                style="font-size:0.875rem;color:var(--text-primary);font-weight:500;font-family:'Courier New',monospace"
                            >
                                ${row.format(row.valA)}
                            </span>
                            <span
                                style="font-size:0.8125rem;font-weight:600;color:${row.deltaColor};text-align:center"
                            >
                                ${row.deltaStr}
                            </span>
                            <span
                                style="font-size:0.875rem;color:var(--text-primary);font-weight:500;font-family:'Courier New',monospace"
                            >
                                ${row.format(row.valB)}
                            </span>
                        </div>
                    `
                )}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

// Module-level state preservation (survives unmount-on-switch)
const _savedAnalysisState = {};

function FieldAnalysisTab() {
    const { showToast } = useToast();
    const mountedRef = useRef(true);

    // -- View state -- restored from module-level cache
    const [currentView, setCurrentView] = useState(
        _savedAnalysisState.currentView || VIEW_DIRECTORY
    );
    const [currentJobId, setCurrentJobId] = useState(
        _savedAnalysisState.currentJobId || null
    );

    // Refs for saving state on cleanup (avoids stale closure)
    const currentViewRef = useRef(currentView);
    const currentJobIdRef = useRef(currentJobId);
    useEffect(() => { currentViewRef.current = currentView; }, [currentView]);
    useEffect(() => { currentJobIdRef.current = currentJobId; }, [currentJobId]);

    // -- Directory view state --
    const [logDirs, setLogDirs] = useState(null);
    const [logDirsError, setLogDirsError] = useState(null);
    const [logDirsWarning, setLogDirsWarning] = useState(null);
    const [history, setHistory] = useState(null);
    const [historyError, setHistoryError] = useState(null);
    const [analysisRunning, setAnalysisRunning] = useState(false);
    const [browseOpen, setBrowseOpen] = useState(false);

    // -- Progress state --
    const [progressVisible, setProgressVisible] = useState(false);
    const [progressPct, setProgressPct] = useState(0);
    const [progressMsg, setProgressMsg] = useState("");

    // -- Compare state --
    const [compareSelected, setCompareSelected] = useState([]);
    const [compareData, setCompareData] = useState(null);
    const [compareLoading, setCompareLoading] = useState(false);
    const [compareError, setCompareError] = useState(null);

    // -- Result sub-tab state --
    const [resultTab, setResultTab] = useState("summary");

    // -- Result data (per sub-tab) --
    const [summaryData, setSummaryData] = useState(null);
    const [summaryLoading, setSummaryLoading] = useState(false);
    const [summaryError, setSummaryError] = useState(null);

    const [motorsData, setMotorsData] = useState(null);
    const [motorsLoading, setMotorsLoading] = useState(false);
    const [motorsError, setMotorsError] = useState(null);

    const [detectionData, setDetectionData] = useState(null);
    const [detectionLoading, setDetectionLoading] = useState(false);
    const [detectionError, setDetectionError] = useState(null);

    const [failuresData, setFailuresData] = useState(null);
    const [failuresLoading, setFailuresLoading] = useState(false);
    const [failuresError, setFailuresError] = useState(null);

    const [timelineData, setTimelineData] = useState(null);
    const [timelineLoading, setTimelineLoading] = useState(false);
    const [timelineError, setTimelineError] = useState(null);

    // -- Refs for cleanup --
    const wsRef = useRef(null);
    const pollerRef = useRef(null);
    const pollerTimeoutRef = useRef(null);
    const viewAnalysisRef = useRef(null);

    // ---- data loading --------------------------------------------------

    const loadLogDirectories = useCallback(async () => {
        try {
            const data = await analysisApi("/log-dirs");
            if (!mountedRef.current) return;
            const dirs = data.directories || data.log_dirs || [];
            setLogDirs(dirs);
            setLogDirsWarning(data.warning || null);
            setLogDirsError(null);
        } catch (err) {
            if (!mountedRef.current) return;
            setLogDirsError(err.message);
        }
    }, []);

    const loadAnalysisHistory = useCallback(async () => {
        try {
            const data = await analysisApi("/history");
            if (!mountedRef.current) return;
            const jobs = data.jobs || data.history || [];
            setHistory(jobs);
            setHistoryError(null);
        } catch (err) {
            if (!mountedRef.current) return;
            setHistoryError(err.message);
        }
    }, []);

    const loadAll = useCallback(async () => {
        await Promise.all([loadLogDirectories(), loadAnalysisHistory()]);
    }, [loadLogDirectories, loadAnalysisHistory]);

    // ---- WebSocket / polling progress ----------------------------------

    const cleanupProgress = useCallback(() => {
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        if (pollerRef.current) {
            clearInterval(pollerRef.current);
            pollerRef.current = null;
        }
        if (pollerTimeoutRef.current) {
            clearTimeout(pollerTimeoutRef.current);
            pollerTimeoutRef.current = null;
        }
    }, []);

    const onAnalysisComplete = useCallback(
        (jobId) => {
            cleanupProgress();
            setProgressVisible(true);
            setProgressPct(100);
            setProgressMsg("Analysis complete");
            setTimeout(() => {
                if (!mountedRef.current) return;
                setProgressVisible(false);
                setAnalysisRunning(false);
            }, 1500);
            // Switch to results view (use ref to avoid stale closure)
            if (viewAnalysisRef.current) viewAnalysisRef.current(jobId);
            loadAnalysisHistory();
        },
        [cleanupProgress, loadAnalysisHistory]
    );

    const onAnalysisFailed = useCallback(
        (errorMsg) => {
            cleanupProgress();
            setProgressVisible(false);
            setAnalysisRunning(false);
            showToast(
                `Analysis failed: ${errorMsg || "Unknown error"}`,
                "error"
            );
            loadAnalysisHistory();
        },
        [cleanupProgress, showToast, loadAnalysisHistory]
    );

    const pollProgressFallback = useCallback(
        (jobId) => {
            pollerRef.current = setInterval(async () => {
                try {
                    const data = await analysisApi(`/${jobId}/summary`);
                    if (
                        data.status === "completed" ||
                        data.overall_health != null
                    ) {
                        onAnalysisComplete(jobId);
                    } else if (data.status === "failed") {
                        onAnalysisFailed("Analysis failed");
                    }
                } catch {
                    // Keep polling on transient errors
                }
            }, PROGRESS_POLL_MS);

            // Safety stop after 5 minutes
            pollerTimeoutRef.current = setTimeout(() => {
                if (pollerRef.current) {
                    clearInterval(pollerRef.current);
                    pollerRef.current = null;
                }
            }, PROGRESS_TIMEOUT_MS);
        },
        [onAnalysisComplete, onAnalysisFailed]
    );

    const connectProgress = useCallback(
        (jobId) => {
            cleanupProgress();

            const proto =
                location.protocol === "https:" ? "wss:" : "ws:";
            const url = `${proto}//${location.host}/api/analysis/ws/progress?job_id=${encodeURIComponent(jobId)}`;

            let ws;
            try {
                ws = new WebSocket(url);
            } catch (err) {
                console.error("WebSocket creation failed:", err);
                pollProgressFallback(jobId);
                return;
            }

            wsRef.current = ws;

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    const pct =
                        msg.progress != null ? Math.round(msg.progress) : null;
                    const text = msg.message || msg.status || "";

                    if (pct != null && mountedRef.current) {
                        setProgressVisible(true);
                        setProgressPct(pct);
                        setProgressMsg(text);
                    }

                    if (msg.status === "completed") {
                        onAnalysisComplete(jobId);
                    } else if (msg.status === "failed") {
                        onAnalysisFailed(msg.error || "Unknown error");
                    }
                } catch {
                    // Ignore non-JSON messages
                }
            };

            ws.onerror = () => {
                wsRef.current = null;
                pollProgressFallback(jobId);
            };

            ws.onclose = () => {
                wsRef.current = null;
            };
        },
        [cleanupProgress, pollProgressFallback, onAnalysisComplete, onAnalysisFailed]
    );

    // ---- actions -------------------------------------------------------

    const runAnalysis = useCallback(
        async (logDirectory) => {
            setAnalysisRunning(true);
            setProgressVisible(true);
            setProgressPct(0);
            setProgressMsg("Starting analysis...");

            try {
                const data = await analysisApi("/run", "POST", {
                    log_directory: logDirectory,
                });
                setCurrentJobId(data.job_id);
                if (data.status === "completed") {
                    // Cached result — skip progress, go straight to results
                    setProgressVisible(false);
                    setAnalysisRunning(false);
                    if (viewAnalysisRef.current) viewAnalysisRef.current(data.job_id);
                    loadAnalysisHistory();
                } else {
                    connectProgress(data.job_id);
                }
            } catch (err) {
                if (err.message && (err.message.includes("409") || err.message.includes("already_running"))) {
                    showToast(
                        "Analysis already running for this directory",
                        "info"
                    );
                } else {
                    showToast(
                        `Failed to start analysis: ${err.message}`,
                        "error"
                    );
                }
                setProgressVisible(false);
                setAnalysisRunning(false);
            }
        },
        [connectProgress, showToast, loadAnalysisHistory]
    );

    const viewAnalysis = useCallback(
        async (jobId) => {
            setCurrentJobId(jobId);
            setCurrentView(VIEW_RESULTS);
            setResultTab("summary");

            // Reset all result panes
            setSummaryData(null);
            setSummaryLoading(true);
            setSummaryError(null);
            setMotorsData(null);
            setMotorsLoading(true);
            setMotorsError(null);
            setDetectionData(null);
            setDetectionLoading(true);
            setDetectionError(null);
            setFailuresData(null);
            setFailuresLoading(true);
            setFailuresError(null);
            setTimelineData(null);
            setTimelineLoading(true);
            setTimelineError(null);

            // Load all result tabs in parallel
            const loaders = [
                analysisApi(`/${jobId}/summary`)
                    .then((d) => {
                        if (mountedRef.current) {
                            setSummaryData(d);
                            setSummaryLoading(false);
                        }
                    })
                    .catch((e) => {
                        if (mountedRef.current) {
                            setSummaryError(e.message);
                            setSummaryLoading(false);
                        }
                    }),
                analysisApi(`/${jobId}/motors`)
                    .then((d) => {
                        if (mountedRef.current) {
                            setMotorsData(d);
                            setMotorsLoading(false);
                        }
                    })
                    .catch((e) => {
                        if (mountedRef.current) {
                            setMotorsError(e.message);
                            setMotorsLoading(false);
                        }
                    }),
                analysisApi(`/${jobId}/detection`)
                    .then((d) => {
                        if (mountedRef.current) {
                            setDetectionData(d);
                            setDetectionLoading(false);
                        }
                    })
                    .catch((e) => {
                        if (mountedRef.current) {
                            setDetectionError(e.message);
                            setDetectionLoading(false);
                        }
                    }),
                analysisApi(`/${jobId}/failures`)
                    .then((d) => {
                        if (mountedRef.current) {
                            setFailuresData(d);
                            setFailuresLoading(false);
                        }
                    })
                    .catch((e) => {
                        if (mountedRef.current) {
                            setFailuresError(e.message);
                            setFailuresLoading(false);
                        }
                    }),
                analysisApi(`/${jobId}/timeline`)
                    .then((d) => {
                        if (mountedRef.current) {
                            setTimelineData(d);
                            setTimelineLoading(false);
                        }
                    })
                    .catch((e) => {
                        if (mountedRef.current) {
                            setTimelineError(e.message);
                            setTimelineLoading(false);
                        }
                    }),
            ];

            await Promise.all(loaders);
        },
        []
    );

    // Keep viewAnalysisRef in sync with latest viewAnalysis callback
    useEffect(() => {
        viewAnalysisRef.current = viewAnalysis;
    }, [viewAnalysis]);

    const backToDirectory = useCallback(() => {
        setCurrentJobId(null);
        setCurrentView(VIEW_DIRECTORY);
    }, []);

    // ---- compare -------------------------------------------------------

    const toggleCompare = useCallback(
        (jobId) => {
            setCompareSelected((prev) => {
                if (prev.includes(jobId)) {
                    return prev.filter((id) => id !== jobId);
                }
                if (prev.length >= 2) {
                    showToast("Select at most 2 analyses to compare", "warning");
                    return prev;
                }
                return [...prev, jobId];
            });
        },
        [showToast]
    );

    const runCompare = useCallback(async () => {
        if (compareSelected.length !== 2) {
            showToast(
                "Select exactly 2 completed analyses to compare",
                "warning"
            );
            return;
        }

        setCurrentView(VIEW_COMPARE);
        setCompareLoading(true);
        setCompareError(null);
        setCompareData(null);

        try {
            const data = await analysisApi(
                `/compare?a=${encodeURIComponent(compareSelected[0])}&b=${encodeURIComponent(compareSelected[1])}`
            );
            if (mountedRef.current) {
                setCompareData(data);
                setCompareLoading(false);
            }
        } catch (err) {
            if (mountedRef.current) {
                setCompareError(err.message);
                setCompareLoading(false);
            }
        }
    }, [compareSelected, showToast]);

    // ---- lifecycle -----------------------------------------------------

    // Initial load + cleanup
    useEffect(() => {
        mountedRef.current = true;
        loadAll();
        return () => {
            mountedRef.current = false;
            // Save view state to module-level cache before cleanup
            _savedAnalysisState.currentView = currentViewRef.current;
            _savedAnalysisState.currentJobId = currentJobIdRef.current;
            cleanupProgress();
        };
    }, [loadAll, cleanupProgress]);

    // 30s polling for directory + history when on directory view
    useEffect(() => {
        if (currentView !== VIEW_DIRECTORY) return;
        const id = setInterval(loadAll, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [currentView, loadAll]);

    // ---- render --------------------------------------------------------

    if (currentView === VIEW_COMPARE) {
        return html`
            <div class="section-header">
                <h2>Field Analysis</h2>
                <div class="section-actions">
                    <button
                        class="btn btn-sm"
                        onClick=${backToDirectory}
                    >
                        Back to Directories
                    </button>
                </div>
            </div>
            <${CompareView}
                data=${compareData}
                loading=${compareLoading}
                error=${compareError}
                jobA=${compareSelected[0]}
                jobB=${compareSelected[1]}
                onBack=${backToDirectory}
            />
        `;
    }

    if (currentView === VIEW_RESULTS) {
        return html`
            <div class="section-header">
                <h2>Field Analysis</h2>
                <div class="section-actions">
                    <button
                        class="btn btn-sm"
                        onClick=${backToDirectory}
                    >
                        Back to Directories
                    </button>
                </div>
            </div>

            <${ProgressBar}
                visible=${progressVisible}
                percent=${progressPct}
                message=${progressMsg}
            />

            <${ResultTabBar}
                activeTab=${resultTab}
                onSwitch=${setResultTab}
            />

            ${resultTab === "summary" &&
            html`
                <${SummaryPane}
                    data=${summaryData}
                    loading=${summaryLoading}
                    error=${summaryError}
                />
            `}
            ${resultTab === "motors" &&
            html`
                <${MotorsPane}
                    data=${motorsData}
                    loading=${motorsLoading}
                    error=${motorsError}
                />
            `}
            ${resultTab === "detection" &&
            html`
                <${DetectionPane}
                    data=${detectionData}
                    loading=${detectionLoading}
                    error=${detectionError}
                />
            `}
            ${resultTab === "failures" &&
            html`
                <${FailuresPane}
                    data=${failuresData}
                    loading=${failuresLoading}
                    error=${failuresError}
                />
            `}
            ${resultTab === "timeline" &&
            html`
                <${TimelinePane}
                    data=${timelineData}
                    loading=${timelineLoading}
                    error=${timelineError}
                />
            `}
        `;
    }

    // -- Directory view (default) --
    return html`
        <div class="section-header">
            <h2>Field Analysis</h2>
        </div>

        <${ProgressBar}
            visible=${progressVisible}
            percent=${progressPct}
            message=${progressMsg}
        />

        <!-- Log Directories -->
        <div class="stats-panel">
            <div
                style="display:flex;justify-content:space-between;align-items:center"
            >
                <h3>Log Directories</h3>
                <button
                    class="btn btn-sm btn-secondary"
                    onClick=${() => setBrowseOpen(!browseOpen)}
                    disabled=${analysisRunning}
                >
                    ${browseOpen ? "Close Browser" : "Browse..."}
                </button>
            </div>
            ${browseOpen &&
            html`
                <${InlineDirectoryPicker}
                    visible=${browseOpen}
                    onSelect=${(path) => {
                        setBrowseOpen(false);
                        runAnalysis(path);
                    }}
                    onClose=${() => setBrowseOpen(false)}
                    disabled=${analysisRunning}
                />
            `}
            <${LogDirList}
                dirs=${logDirs}
                error=${logDirsError}
                warning=${logDirsWarning}
                onAnalyze=${runAnalysis}
                disabled=${analysisRunning}
            />
        </div>

        <!-- Analysis History -->
        <div class="stats-panel">
            <h3>Analysis History</h3>
            <${HistorySection}
                history=${history}
                historyError=${historyError}
                compareSelected=${compareSelected}
                onToggleCompare=${toggleCompare}
                onViewAnalysis=${viewAnalysis}
            />
        </div>

        <!-- Compare Controls -->
        <div class="stats-panel">
            <h3>Compare Analyses</h3>
            <p
                class="analysis-compare-hint"
                style="font-size:0.8125rem;color:var(--text-secondary);margin-bottom:var(--spacing-sm)"
            >
                Select two completed analyses from the history above to
                compare.
            </p>
            <button
                class="btn btn-primary"
                disabled=${compareSelected.length !== 2}
                onClick=${runCompare}
            >
                Compare Selected
            </button>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Directory sub-components
// ---------------------------------------------------------------------------

function LogDirList({ dirs, error, warning, onAnalyze, disabled }) {
    if (error) {
        return html`
            <div class="section-error">
                Failed to load log directories: ${error}
            </div>
        `;
    }

    if (dirs === null) {
        return html`
            <div class="section-loading">Loading log directories...</div>
        `;
    }

    if (dirs.length === 0) {
        return html`
            <div class="empty-state">
                <p>No log directories found.</p>
                ${warning &&
                html`
                    <p
                        style="color:var(--text-muted);font-size:0.8125rem;margin-top:0.5rem"
                    >
                        ${warning}
                    </p>
                `}
                <p
                    style="color:var(--text-muted);font-size:0.8125rem;margin-top:0.5rem"
                >
                    Run a field session to generate logs, or browse for an
                    existing log directory.
                </p>
            </div>
        `;
    }

    return html`
        <div class="analysis-dirs-grid">
            ${dirs.map(
                (dir, i) => html`
                    <${LogDirCard}
                        key=${dir.name || dir.directory || i}
                        dir=${dir}
                        onAnalyze=${onAnalyze}
                        disabled=${disabled}
                    />
                `
            )}
        </div>
    `;
}

function HistorySection({
    history,
    historyError,
    compareSelected,
    onToggleCompare,
    onViewAnalysis,
}) {
    if (historyError) {
        return html`
            <div class="section-error">
                Failed to load history: ${historyError}
            </div>
        `;
    }

    if (history === null) {
        return html`
            <div class="section-loading">Loading analysis history...</div>
        `;
    }

    return html`
        <${HistoryTable}
            jobs=${history}
            compareSelected=${compareSelected}
            onToggleCompare=${onToggleCompare}
            onViewAnalysis=${onViewAnalysis}
        />
    `;
}

// ---------------------------------------------------------------------------
// Register with the Preact app shell
// ---------------------------------------------------------------------------

registerTab("analysis", FieldAnalysisTab);

export { FieldAnalysisTab };
