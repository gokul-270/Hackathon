/**
 * StatusHealthTab — Entity-scoped status/health tab for the Entity Detail Shell.
 *
 * Shows:
 * - System metrics gauges (CPU, memory, temperature, disk) with progress bars
 * - ROS2 node list table with lifecycle state (ros2_available-aware)
 * - Systemd service list with start/stop/restart controls (API key for mutations)
 * - Per-subsystem health status (healthy/degraded/error/unavailable)
 * - "Initializing..." placeholder before first health data arrives
 *
 * @module components/StatusHealthTab
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useCallback,
    useContext,
    useMemo,
    useRef,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch, formatDuration } from "../utils.js";
import { ToastContext } from "../app.js";
import {
    CAN_STALE_THRESHOLD_S,
    ENTITY_STALE_THRESHOLD_S,
    THRESHOLDS,
    SUBSYSTEMS,
    isTimestampStale,
    healthBadgeClass,
    deriveSubsystemHealth,
    deriveCardHealthSummary,
} from "../utils/entityHealthSummary.mjs";

// ---------------------------------------------------------------------------
// Constants (local to this module)
// ---------------------------------------------------------------------------

/** Polling interval for system stats and processes (ms). */
const STATS_POLL_INTERVAL_MS = 10000;

/** Maximum sparkline data points to retain. */
const SPARKLINE_MAX_POINTS = 30;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Clamp a number to 0-100 for progress bar widths.
 * @param {number|null|undefined} val
 * @returns {number}
 */
function clampPercent(val) {
    if (val == null || isNaN(val)) return 0;
    return Math.max(0, Math.min(100, val));
}

/**
 * CSS color class for a metric based on percentage thresholds.
 * Returns grey class for null/undefined metrics (UNAVAILABLE).
 * @param {number|null|undefined} pct
 * @returns {string}
 */
function metricSeverity(pct) {
    if (pct == null || isNaN(pct)) return "entity-metric-unavailable";
    if (pct > 90) return "entity-metric-critical";
    if (pct > 70) return "entity-metric-warning";
    return "entity-metric-ok";
}

/**
 * Temperature severity thresholds (Celsius).
 * @param {number} temp
 * @returns {string}
 */
function tempSeverity(temp) {
    if (temp > 80) return "entity-metric-critical";
    if (temp > 65) return "entity-metric-warning";
    return "entity-metric-ok";
}

// healthBadgeClass is imported from ../utils/entityHealthSummary.mjs

/**
 * CSS class for a lifecycle state badge.
 * @param {string} state
 * @returns {string}
 */
function lifecycleBadgeClass(state) {
    const s = (state || "unknown").toLowerCase();
    if (s === "active") return "node-lifecycle-active";
    if (s === "inactive") return "node-lifecycle-inactive";
    if (s === "unconfigured") return "node-lifecycle-unconfigured";
    if (s === "finalized") return "node-lifecycle-finalized";
    return "node-lifecycle-unknown";
}

/**
 * CSS class for systemd service active_state.
 * @param {string} state
 * @returns {string}
 */
function serviceStateClass(state) {
    const s = (state || "unknown").toLowerCase();
    if (s === "active" || s === "running") return "service-status-active";
    if (s === "failed") return "service-status-failed";
    if (s === "activating" || s === "deactivating")
        return "service-status-activating";
    return "service-status-inactive";
}

// isTimestampStale is imported from ../utils/entityHealthSummary.mjs

// deriveSubsystemHealth is imported from ../utils/entityHealthSummary.mjs

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Mini sparkline SVG showing recent data points.
 * @param {object} props
 * @param {number[]} props.data - Array of numeric values
 * @param {number} [props.max] - Max value for Y-axis scaling (default 100)
 * @param {string} [props.color] - Stroke color
 */
function Sparkline({ data, max = 100, color = "var(--accent-primary)" }) {
    if (!data || data.length < 2) {
        return html`
            <div class="sparkline-placeholder" style=${{
                height: "24px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "0.7rem",
                color: "var(--text-muted)",
            }}>
                Collecting data...
            </div>
        `;
    }

    const width = 120;
    const height = 24;
    const padding = 1;
    const effectiveMax = max || 100;
    const stepX = (width - 2 * padding) / (data.length - 1);

    const points = data
        .map((v, i) => {
            const x = padding + i * stepX;
            const clamped = Math.max(0, Math.min(v, effectiveMax));
            const y = height - padding - ((clamped / effectiveMax) * (height - 2 * padding));
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(" ");

    return html`
        <svg class="sparkline-svg" width=${width} height=${height}
            viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"
            style=${{ display: "block", marginTop: "4px" }}>
            <polyline
                points=${points}
                fill="none"
                stroke=${color}
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
            />
        </svg>
    `;
}

/**
 * A single metric gauge card with sparkline and threshold bands.
 */
function MetricGauge({ icon, label, value, unit, percent, severityFn, sparklineData, sparklineMax, thresholds, extra }) {
    const pct = clampPercent(percent);
    const severity = severityFn ? severityFn(percent) : metricSeverity(pct);
    const isUnavailable = value == null;
    const displayValue = isUnavailable
        ? null
        : (typeof value === "number" ? value.toFixed(1) : value);

    const th = thresholds || {};

    return html`
        <div class="stat-card">
            <div class="stat-icon">${icon}</div>
            <div class="stat-content">
                <div class="stat-label">${label}</div>
                <div class="stat-value" style=${{ fontSize: "1.5rem" }}>
                    ${isUnavailable
                        ? html`<span style=${{ fontSize: "0.85rem", color: "var(--text-muted)" }}>No sensor</span>`
                        : html`${displayValue}${unit ? html`<span style=${{ fontSize: "0.8rem", color: "var(--text-secondary)", marginLeft: "4px" }}>${unit}</span>` : null}`
                    }
                </div>
                <div class="stat-bar threshold-bar" style=${{ opacity: isUnavailable ? 0.3 : 1 }}>
                    ${th.warning != null ? html`
                        <div class="threshold-band threshold-warning"
                            style=${{ left: `${th.warning}%`, width: `${(th.critical || 100) - th.warning}%` }}></div>
                    ` : null}
                    ${th.critical != null ? html`
                        <div class="threshold-band threshold-critical"
                            style=${{ left: `${th.critical}%`, width: `${100 - th.critical}%` }}></div>
                    ` : null}
                    <div
                        class="stat-bar-fill ${isUnavailable ? '' : severity}"
                        style=${{ width: `${isUnavailable ? 0 : pct}%`, position: "relative", zIndex: 1 }}
                    ></div>
                </div>
                <${Sparkline}
                    data=${isUnavailable ? [] : sparklineData}
                    max=${sparklineMax || 100}
                    color=${severity === "entity-metric-critical" ? "var(--accent-error, #ef4444)" :
                           severity === "entity-metric-warning" ? "var(--accent-warning, #f59e0b)" :
                           "var(--accent-primary)"}
                />
                ${extra || null}
            </div>
        </div>
    `;
}

/**
 * Format a motor name for compact display.
 * "motor/joint5" -> "J5", "joint3" -> "J3", "motor_1" -> "M1", fallback to name.
 */
function shortMotorName(name) {
    const jMatch = name.match(/joint\s*(\d+)/i);
    if (jMatch) return `J${jMatch[1]}`;
    const mMatch = name.match(/motor\s*[_-]?(\d+)/i);
    if (mMatch) return `M${mMatch[1]}`;
    return name.replace(/^motor\/?/i, "").trim() || name;
}

/**
 * Hardware temperature display for motor and camera diagnostics.
 *
 * Shows per-joint motor temperatures in compact inline format and camera
 * temperature (arm entities only). The section is always visible with N/A
 * placeholders when data is unavailable.
 *
 * @param {object} props
 * @param {object|null} props.motorTemperatures - Map of motor name -> temp (C), or null
 * @param {number|null} props.cameraTemperatureC - Camera temperature in C, or null
 * @param {string} props.entityType - "arm" or "vehicle"
 */
function TemperatureSection({ motorTemperatures, cameraTemperatureC, entityType }) {
    const isArm = (entityType || "").toLowerCase() === "arm";
    const hasMotorTemps = motorTemperatures != null && typeof motorTemperatures === "object";
    const motorEntries = hasMotorTemps ? Object.entries(motorTemperatures) : [];

    // Determine motor row severity from worst (hottest) motor
    const motorSeverity = (() => {
        if (!hasMotorTemps || motorEntries.length === 0) return "entity-metric-unavailable";
        const maxTemp = Math.max(...motorEntries.map(([, t]) => (t != null ? t : 0)));
        return tempSeverity(maxTemp);
    })();

    // Compact inline: "J3: 42° | J4: 45° | J5: 38°"
    const motorDisplay = hasMotorTemps && motorEntries.length > 0
        ? motorEntries
              .map(([name, temp]) => {
                  const label = shortMotorName(name);
                  const val = temp != null ? `${temp.toFixed(0)}\u00B0C` : "N/A";
                  return `${label}: ${val}`;
              })
              .join("  \u2502  ")
        : "N/A \u2014 no motor data";

    // Camera severity
    const cameraSeverity = cameraTemperatureC != null
        ? tempSeverity(cameraTemperatureC)
        : "entity-metric-unavailable";
    const cameraDisplay = cameraTemperatureC != null
        ? `${cameraTemperatureC.toFixed(1)}\u00B0C`
        : "N/A";

    return html`
        <div style=${{ marginBottom: "var(--spacing-lg)" }}>
            <h3 style=${{ marginBottom: "var(--spacing-sm)", color: "var(--text-primary)" }}>
                \uD83C\uDF21\uFE0F Hardware Temperatures
            </h3>
            <div style=${{
                display: "flex",
                flexDirection: "column",
                gap: "var(--spacing-xs)",
            }}>
                <!-- Motor temperatures row (always shown) -->
                <div
                    class="stat-card ${motorSeverity}"
                    style=${{
                        padding: "var(--spacing-sm) var(--spacing-md)",
                        display: "flex",
                        alignItems: "center",
                        gap: "var(--spacing-md)",
                    }}
                >
                    <span style=${{ fontSize: "0.75rem", color: "var(--text-secondary)", minWidth: "80px" }}>
                        Motors
                    </span>
                    <span style=${{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)" }}>
                        ${motorDisplay}
                    </span>
                </div>
                <!-- Camera temperature row (arm entities only) -->
                ${isArm ? html`
                    <div
                        class="stat-card ${cameraSeverity}"
                        style=${{
                            padding: "var(--spacing-sm) var(--spacing-md)",
                            display: "flex",
                            alignItems: "center",
                            gap: "var(--spacing-md)",
                        }}
                    >
                        <span style=${{ fontSize: "0.75rem", color: "var(--text-secondary)", minWidth: "80px" }}>
                            Camera
                        </span>
                        <span style=${{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)" }}>
                            ${cameraDisplay}
                        </span>
                    </div>
                ` : null}
            </div>
        </div>
    `;
}

/**
 * Disk usage breakdown showing used/total in human-readable format.
 */
function DiskBreakdown({ used, total }) {
    if (used == null || total == null) return null;

    const formatBytes = (bytes) => {
        if (bytes == null) return "\u2014";
        const gb = bytes / (1024 * 1024 * 1024);
        return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
    };

    return html`
        <div class="disk-breakdown" style=${{
            fontSize: "0.8rem",
            color: "var(--text-secondary)",
            marginTop: "var(--spacing-xs)",
            textAlign: "center",
        }}>
            ${formatBytes(used)} / ${formatBytes(total)} used
        </div>
    `;
}

/**
 * Collapsible process table showing top 15 processes by CPU usage.
 */
function ProcessTable({ processes, loading: processLoading, error: processError }) {
    const [expanded, setExpanded] = useState(false);

    const toggleExpanded = useCallback(() => {
        setExpanded((prev) => !prev);
    }, []);

    const rows = processes || [];

    return html`
        <div style=${{ marginBottom: "var(--spacing-lg)" }}>
            <div
                class="process-table-toggle"
                onClick=${toggleExpanded}
                style=${{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--spacing-sm)",
                    cursor: "pointer",
                    padding: "var(--spacing-sm) 0",
                    userSelect: "none",
                }}
            >
                <span style=${{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.2s", display: "inline-block" }}>
                    \u25B6
                </span>
                <h3 style=${{ margin: 0, color: "var(--text-primary)" }}>
                    Top Processes
                    <span style=${{
                        fontSize: "0.8rem",
                        color: "var(--text-muted)",
                        marginLeft: "var(--spacing-sm)",
                    }}>(${rows.length})</span>
                </h3>
            </div>
            ${expanded ? html`
                ${processLoading && rows.length === 0 ? html`
                    <div class="loading-skeleton" style=${{ padding: "var(--spacing-md)", textAlign: "center", color: "var(--text-muted)" }}>
                        Loading processes...
                    </div>
                ` : processError && rows.length === 0 ? html`
                    <div style=${{ padding: "var(--spacing-md)", textAlign: "center", color: "var(--text-muted)" }}>
                        Failed to load process data
                    </div>
                ` : rows.length === 0 ? html`
                    <div class="empty-state" style=${{ padding: "var(--spacing-md)" }}>
                        No process data available
                    </div>
                ` : html`
                    <div style=${{ overflowX: "auto" }}>
                        <table class="data-table process-table" style=${{ width: "100%", borderCollapse: "collapse" }}>
                            <thead>
                                <tr>
                                    <th style=${{ textAlign: "left", padding: "var(--spacing-sm) var(--spacing-md)" }}>PID</th>
                                    <th style=${{ textAlign: "left", padding: "var(--spacing-sm) var(--spacing-md)" }}>Name</th>
                                    <th style=${{ textAlign: "right", padding: "var(--spacing-sm) var(--spacing-md)" }}>CPU%</th>
                                    <th style=${{ textAlign: "right", padding: "var(--spacing-sm) var(--spacing-md)" }}>Memory (MB)</th>
                                    <th style=${{ textAlign: "left", padding: "var(--spacing-sm) var(--spacing-md)" }}>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${rows.map(
                                    (proc) => html`
                                        <tr key=${proc.pid} style=${{ borderBottom: "1px solid var(--border-color)" }}>
                                            <td style=${{
                                                padding: "var(--spacing-sm) var(--spacing-md)",
                                                fontFamily: "monospace",
                                                fontSize: "0.85rem",
                                            }}>${proc.pid}</td>
                                            <td style=${{
                                                padding: "var(--spacing-sm) var(--spacing-md)",
                                                fontFamily: "monospace",
                                                fontSize: "0.85rem",
                                                maxWidth: "200px",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                                whiteSpace: "nowrap",
                                            }}>${proc.name}</td>
                                            <td style=${{
                                                padding: "var(--spacing-sm) var(--spacing-md)",
                                                textAlign: "right",
                                                fontFamily: "monospace",
                                                fontSize: "0.85rem",
                                            }}>${(proc.cpu_percent || 0).toFixed(1)}</td>
                                            <td style=${{
                                                padding: "var(--spacing-sm) var(--spacing-md)",
                                                textAlign: "right",
                                                fontFamily: "monospace",
                                                fontSize: "0.85rem",
                                            }}>${(proc.memory_mb || 0).toFixed(1)}</td>
                                            <td style=${{
                                                padding: "var(--spacing-sm) var(--spacing-md)",
                                                fontSize: "0.85rem",
                                                color: "var(--text-secondary)",
                                            }}>${proc.status}</td>
                                        </tr>
                                    `
                                )}
                            </tbody>
                        </table>
                    </div>
                `}
                ${processError && rows.length > 0 ? html`
                    <div class="stale-data-indicator" style=${{
                        fontSize: "0.75rem",
                        color: "var(--accent-warning, #f59e0b)",
                        padding: "var(--spacing-xs) var(--spacing-md)",
                    }}>
                        Data may be stale
                    </div>
                ` : null}
            ` : null}
        </div>
    `;
}

/**
 * Per-subsystem health status badge row (task 5.9).
 */
function SubsystemHealthRow({ subsystems, healthMap }) {
    return html`
        <div style=${{
            display: "flex",
            flexWrap: "wrap",
            gap: "var(--spacing-sm)",
            marginBottom: "var(--spacing-lg)",
        }}>
            ${subsystems.map(
                (sub) => {
                    const status = healthMap[sub.key] || "unavailable";
                    const badgeClass = healthBadgeClass(status);
                    return html`
                        <div
                            key=${sub.key}
                            class="health-card ${badgeClass}"
                            style=${{
                                padding: "var(--spacing-sm) var(--spacing-md)",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "var(--spacing-xs)",
                                borderRadius: "var(--radius-md)",
                                fontSize: "0.85rem",
                            }}
                        >
                            <span>${sub.icon}</span>
                            <span style=${{ fontWeight: 500 }}>${sub.label}</span>
                            <span style=${{
                                textTransform: "capitalize",
                                opacity: 0.85,
                            }}>${status}</span>
                        </div>
                    `;
                }
            )}
        </div>
    `;
}

/**
 * Format a timestamp string for display in safety cards.
 * @param {string|null} ts - ISO 8601 timestamp or null
 * @returns {string}
 */
function formatLastEstop(ts) {
    if (!ts) return "Never";
    try {
        return new Date(ts).toLocaleString();
    } catch {
        return ts;
    }
}

/**
 * Safety status section — migrated from SafetyTab (task 3.1).
 *
 * Shows 4 read-only status cards: E-Stop Status, Active Arms, CAN Bus,
 * and Last E-Stop. Polls /api/safety/status every 3 seconds independently
 * of the entity data polling managed by EntityDetailShell.
 *
 * Missing/unavailable data renders with grey UNAVAILABLE styling.
 */
const SAFETY_POLL_INTERVAL_MS = 3000;

function SafetyStatusSection() {
    const [safetyStatus, setSafetyStatus] = useState(null);
    const [safetyLoading, setSafetyLoading] = useState(true);
    const mountedRef = useRef(true);

    const loadSafetyStatus = useCallback(async () => {
        const data = await safeFetch("/api/safety/status");
        if (!mountedRef.current) return;
        if (data) {
            setSafetyStatus(data);
        }
        setSafetyLoading(false);
    }, []);

    useEffect(() => {
        mountedRef.current = true;
        loadSafetyStatus();
        return () => {
            mountedRef.current = false;
        };
    }, [loadSafetyStatus]);

    useEffect(() => {
        const id = setInterval(loadSafetyStatus, SAFETY_POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [loadSafetyStatus]);

    if (safetyLoading) {
        return html`
            <div style=${{ marginBottom: "var(--spacing-lg)" }}>
                <h3 style=${{ marginBottom: "var(--spacing-sm)", color: "var(--text-primary)" }}>
                    Safety Status
                </h3>
                <p class="text-muted">Loading safety status...</p>
            </div>
        `;
    }

    if (!safetyStatus) {
        return html`
            <div style=${{ marginBottom: "var(--spacing-lg)" }}>
                <h3 style=${{ marginBottom: "var(--spacing-sm)", color: "var(--text-primary)" }}>
                    Safety Status
                </h3>
                <div class="health-grid" style=${{ marginTop: "var(--spacing-md)" }}>
                    <div class="health-card health-unavailable">
                        <h3>E-Stop Status</h3>
                        <div class="health-status">Unavailable</div>
                    </div>
                    <div class="health-card health-unavailable">
                        <h3>Active Arms</h3>
                        <div class="health-status">Unavailable</div>
                    </div>
                    <div class="health-card health-unavailable">
                        <h3>CAN Bus</h3>
                        <div class="health-status">Unavailable</div>
                    </div>
                    <div class="health-card health-unavailable">
                        <h3>Last E-Stop</h3>
                        <div class="health-status">Unavailable</div>
                    </div>
                </div>
            </div>
        `;
    }

    // Detect placeholder/dev-mode data:
    // - CAN disconnected + no real hardware = likely dev machine
    // - active_arms is hardcoded to 1 in dev mode
    const isDevMode = !safetyStatus.can_connected;

    const estopClass = safetyStatus.estop_active ? "health-error" : "health-ok";
    const estopLabel = safetyStatus.estop_active ? "ACTIVE" : "Clear";
    const canClass = safetyStatus.can_connected ? "health-ok" : "health-error";
    const canLabel = safetyStatus.can_connected ? "Connected" : "Disconnected";

    return html`
        <div style=${{ marginBottom: "var(--spacing-lg)" }}>
            <h3 style=${{ marginBottom: "var(--spacing-sm)", color: "var(--text-primary)", display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
                Safety Status
                ${isDevMode && html`
                    <span style=${{
                        fontSize: "0.7rem",
                        fontWeight: 500,
                        padding: "2px 8px",
                        borderRadius: "var(--radius-sm)",
                        background: "rgba(158, 158, 158, 0.15)",
                        color: "var(--text-muted)",
                        textTransform: "uppercase",
                        letterSpacing: "0.03em",
                    }}>Dev Mode</span>
                `}
            </h3>
            ${isDevMode && html`
                <div style=${{
                    fontSize: "0.8rem",
                    color: "var(--text-muted)",
                    marginBottom: "var(--spacing-sm)",
                    fontStyle: "italic",
                }}>
                    No CAN hardware detected. Safety values may be placeholders.
                </div>
            `}
            <div class="health-grid" style=${{ marginTop: "var(--spacing-md)", opacity: isDevMode ? "0.7" : "1" }}>
                <div class="health-card ${estopClass}">
                    <h3>E-Stop Status</h3>
                    <div class="health-status">${estopLabel}</div>
                </div>
                <div class="health-card ${isDevMode ? "health-unknown" : "health-ok"}">
                    <h3>Active Arms</h3>
                    <div class="health-status">${isDevMode ? "\u2014" : safetyStatus.active_arms}</div>
                </div>
                <div class="health-card ${canClass}">
                    <h3>CAN Bus</h3>
                    <div class="health-status">${canLabel}</div>
                </div>
                <div class="health-card health-unknown">
                    <h3>Last E-Stop</h3>
                    <div class="health-status" style=${{ fontSize: "0.9em" }}>
                        ${formatLastEstop(safetyStatus.last_estop)}
                    </div>
                </div>
            </div>
        </div>
    `;
}

/**
 * ROS2 node count summary (task 5.2b).
 * Full node list is in the dedicated Nodes sub-tab; this section shows
 * only the aggregate count from the entity heartbeat to avoid duplicating
 * an API fetch.
 */
function NodeListSection({ entityData }) {
    const ros2Available = entityData ? entityData.ros2_available : null;
    const ros2State = entityData ? entityData.ros2_state : null;

    if (ros2Available === false) {
        return html`
            <div style=${{
                background: "var(--bg-tertiary)",
                border: "1px solid var(--border-color)",
                borderRadius: "var(--radius-md)",
                padding: "var(--spacing-lg)",
                textAlign: "center",
                color: "var(--text-secondary)",
                marginBottom: "var(--spacing-lg)",
            }}>
                <div style=${{ fontSize: "1.5em", marginBottom: "var(--spacing-xs)" }}>\uD83D\uDD0C</div>
                <div>ROS2 is not running on this entity</div>
            </div>
        `;
    }

    const nodeCount =
        ros2Available == null ? null : ros2State ? ros2State.node_count || 0 : null;
    const topicCount = ros2State ? ros2State.topic_count || 0 : null;
    const serviceCount = ros2State ? ros2State.service_count || 0 : null;

    return html`
        <div style=${{ marginBottom: "var(--spacing-lg)" }}>
            <h3 style=${{ marginBottom: "var(--spacing-sm)", color: "var(--text-primary)" }}>
                \uD83D\uDD27 ROS2 Overview
            </h3>
            <div style=${{
                display: "flex",
                gap: "var(--spacing-md)",
                flexWrap: "wrap",
            }}>
                ${[
                    { label: "Nodes", count: nodeCount, icon: "\uD83D\uDFE2" },
                    { label: "Topics", count: topicCount, icon: "\uD83D\uDCE1" },
                    { label: "Services", count: serviceCount, icon: "\u2699\uFE0F" },
                ].map(
                    (item) => html`
                        <div
                            key=${item.label}
                            style=${{
                                background: "var(--bg-tertiary)",
                                border: "1px solid var(--border-color)",
                                borderRadius: "var(--radius-md)",
                                padding: "var(--spacing-sm) var(--spacing-lg)",
                                textAlign: "center",
                                minWidth: "100px",
                            }}
                        >
                            <div style=${{ fontSize: "1.5rem", fontWeight: 600, color: "var(--text-primary)" }}>
                                ${item.count != null ? item.count : "\u2014"}
                            </div>
                            <div style=${{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                                ${item.icon} ${item.label}
                            </div>
                        </div>
                    `
                )}
            </div>
            <div style=${{
                marginTop: "var(--spacing-sm)",
                fontSize: "0.8rem",
                color: "var(--text-muted)",
            }}>
                See the Nodes, Topics, and Services tabs for full details.
            </div>
        </div>
    `;
}

/**
 * Systemd service list with start/stop/restart controls (task 5.2c).
 * Requires API key for mutations.
 */
function ServiceListSection({ entityId, entityData }) {
    const { showToast } = useContext(ToastContext);
    const [actionInProgress, setActionInProgress] = useState(() => new Set());

    const services = entityData ? entityData.services || [] : [];

    const performAction = useCallback(
        async (serviceName, action) => {
            setActionInProgress((prev) => {
                const next = new Set(prev);
                next.add(`${serviceName}-${action}`);
                return next;
            });

            try {
                const url = `/api/entities/${encodeURIComponent(entityId)}/systemd/services/${encodeURIComponent(serviceName)}/${action}`;
                const result = await safeFetch(url, { method: "POST" });

                if (result && !result.error) {
                    showToast(
                        `Service ${serviceName} ${action} successful`,
                        "success"
                    );
                } else {
                    const errMsg =
                        (result && result.detail) ||
                        (result && result.error) ||
                        `Failed to ${action} ${serviceName}`;
                    showToast(errMsg, "error");
                }
            } catch (err) {
                showToast(
                    `Failed to ${action} ${serviceName}: ${err.message}`,
                    "error"
                );
            } finally {
                setActionInProgress((prev) => {
                    const next = new Set(prev);
                    next.delete(`${serviceName}-${action}`);
                    return next;
                });
            }
        },
        [entityId, showToast]
    );

    if (services.length === 0) {
        return html`
            <div style=${{ marginBottom: "var(--spacing-lg)" }}>
                <h3 style=${{ marginBottom: "var(--spacing-sm)", color: "var(--text-primary)" }}>
                    \uD83D\uDCE6 Systemd Services
                </h3>
                <div class="empty-state" style=${{ padding: "var(--spacing-md)" }}>
                    No services reported
                </div>
            </div>
        `;
    }

    return html`
        <div style=${{ marginBottom: "var(--spacing-lg)" }}>
            <h3 style=${{ marginBottom: "var(--spacing-sm)", color: "var(--text-primary)" }}>
                \uD83D\uDCE6 Systemd Services
                <span style=${{
                    fontSize: "0.8rem",
                    color: "var(--text-muted)",
                    marginLeft: "var(--spacing-sm)",
                }}>(${services.length})</span>
            </h3>
            <div style=${{ overflowX: "auto" }}>
                <table class="data-table" style=${{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                        <tr>
                            <th style=${{ textAlign: "left", padding: "var(--spacing-sm) var(--spacing-md)" }}>Service</th>
                            <th style=${{ textAlign: "left", padding: "var(--spacing-sm) var(--spacing-md)" }}>State</th>
                            <th style=${{ textAlign: "left", padding: "var(--spacing-sm) var(--spacing-md)" }}>Sub-state</th>
                            <th style=${{ textAlign: "center", padding: "var(--spacing-sm) var(--spacing-md)" }}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${services.map(
                            (svc) => {
                                const name = svc.name || "unknown";
                                const isBusy =
                                    actionInProgress.has(`${name}-start`) ||
                                    actionInProgress.has(`${name}-stop`) ||
                                    actionInProgress.has(`${name}-restart`);

                                return html`
                                    <tr key=${name} style=${{ borderBottom: "1px solid var(--border-color)" }}>
                                        <td style=${{
                                            padding: "var(--spacing-sm) var(--spacing-md)",
                                            fontFamily: "monospace",
                                            fontSize: "0.85rem",
                                        }}>
                                            ${name}
                                        </td>
                                        <td style=${{ padding: "var(--spacing-sm) var(--spacing-md)" }}>
                                            <span
                                                class="service-status-dot ${serviceStateClass(svc.active_state)}"
                                                style=${{
                                                    display: "inline-block",
                                                    width: "8px",
                                                    height: "8px",
                                                    borderRadius: "50%",
                                                    marginRight: "6px",
                                                }}
                                            ></span>
                                            ${svc.active_state || "unknown"}
                                        </td>
                                        <td style=${{
                                            padding: "var(--spacing-sm) var(--spacing-md)",
                                            color: "var(--text-secondary)",
                                            fontSize: "0.85rem",
                                        }}>
                                            ${svc.sub_state || "\u2014"}
                                        </td>
                                        <td style=${{
                                            padding: "var(--spacing-sm) var(--spacing-md)",
                                            textAlign: "center",
                                        }}>
                                            <div style=${{ display: "flex", gap: "4px", justifyContent: "center" }}>
                                                <button
                                                    class="btn btn-sm"
                                                    disabled=${isBusy}
                                                    onClick=${() => performAction(name, "start")}
                                                    title="Start service"
                                                    style=${{ fontSize: "0.75rem", padding: "2px 8px" }}
                                                >
                                                    Start
                                                </button>
                                                <button
                                                    class="btn btn-sm"
                                                    disabled=${isBusy}
                                                    onClick=${() => performAction(name, "stop")}
                                                    title="Stop service"
                                                    style=${{ fontSize: "0.75rem", padding: "2px 8px" }}
                                                >
                                                    Stop
                                                </button>
                                                <button
                                                    class="btn btn-sm"
                                                    disabled=${isBusy}
                                                    onClick=${() => performAction(name, "restart")}
                                                    title="Restart service"
                                                    style=${{ fontSize: "0.75rem", padding: "2px 8px" }}
                                                >
                                                    ${actionInProgress.has(`${name}-restart`)
                                                        ? "..."
                                                        : "Restart"}
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Diagnostics section
// ---------------------------------------------------------------------------

/**
 * DiagnosticsSection — collapsible active diagnostics panel.
 *
 * Collapsed by default. "Run Diagnostics" button probes all entities via
 * GET /api/diagnostics/run and displays color-coded per-entity, per-check
 * results with fix hints and an Export JSON button.
 *
 * Capability: active-fleet-diagnostics (dashboard-reliability-hardening)
 */
function DiagnosticsSection() {
    const [expanded, setExpanded] = useState(false);
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState(null);
    const [error, setError] = useState(null);
    const { showToast } = useContext(ToastContext);

    const runDiagnostics = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await safeFetch("/api/diagnostics/run");
            setResults(data);
        } catch (err) {
            setError(err.message || "Diagnostics failed");
            showToast(`Diagnostics error: ${err.message}`, "error");
        } finally {
            setLoading(false);
        }
    }, [showToast]);

    const exportJson = useCallback(() => {
        if (!results) return;
        const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
        const filename = `diagnostics-${ts}.json`;
        const blob = new Blob([JSON.stringify(results, null, 2)], {
            type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }, [results]);

    const toggleExpanded = useCallback(() => {
        setExpanded((v) => !v);
    }, []);

    /** Render a single check row. */
    function CheckRow({ label, check }) {
        const statusColor =
            check.status === "pass"
                ? "var(--status-online)"
                : check.status === "fail"
                  ? "var(--status-error)"
                  : "var(--text-muted)";
        const statusIcon =
            check.status === "pass" ? "●" : check.status === "fail" ? "●" : "○";

        return html`
            <div style=${{
                display: "flex",
                flexDirection: "column",
                gap: "2px",
                paddingBottom: "var(--spacing-xs)",
            }}>
                <div style=${{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
                    <span style=${{ color: statusColor, fontSize: "0.75rem" }}>${statusIcon}</span>
                    <span style=${{ fontSize: "0.85rem", fontWeight: 500 }}>${label}</span>
                    ${check.latency_ms != null && html`
                        <span style=${{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            ${check.latency_ms}ms
                        </span>
                    `}
                </div>
                <div style=${{
                    marginLeft: "calc(0.75rem + var(--spacing-sm))",
                    fontSize: "0.78rem",
                    color: "var(--text-secondary)",
                }}>
                    ${check.message}
                </div>
                ${check.status === "fail" && check.fix_hint && html`
                    <div style=${{
                        marginLeft: "calc(0.75rem + var(--spacing-sm))",
                        fontSize: "0.75rem",
                        color: "var(--status-warning)",
                        fontStyle: "italic",
                    }}>
                        Fix: ${check.fix_hint}
                    </div>
                `}
            </div>
        `;
    }

    /** Render a single entity card with 4 check rows. */
    function EntityDiagCard({ result }) {
        const overallColor =
            result.overall === "pass"
                ? "var(--status-online)"
                : result.overall === "fail"
                  ? "var(--status-error)"
                  : "var(--text-muted)";

        return html`
            <div style=${{
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                padding: "var(--spacing-md)",
                marginBottom: "var(--spacing-sm)",
            }}>
                <div style=${{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--spacing-sm)",
                    marginBottom: "var(--spacing-sm)",
                }}>
                    <span style=${{ color: overallColor, fontSize: "0.85rem" }}>●</span>
                    <strong style=${{ fontSize: "0.9rem" }}>${result.entity_name}</strong>
                    <span style=${{
                        fontSize: "0.75rem",
                        color: "var(--text-muted)",
                        fontFamily: "monospace",
                    }}>${result.entity_id}</span>
                </div>
                <${CheckRow} label="Agent HTTP" check=${result.checks.agent_http} />
                <${CheckRow} label="ROS2" check=${result.checks.ros2} />
                <${CheckRow} label="Systemd" check=${result.checks.systemd} />
                <${CheckRow} label="MQTT" check=${result.checks.mqtt} />
            </div>
        `;
    }

    return html`
        <div style=${{ marginBottom: "var(--spacing-lg)" }}>
            <!-- Header row with toggle -->
            <div
                style=${{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    cursor: "pointer",
                    userSelect: "none",
                    marginBottom: "var(--spacing-sm)",
                }}
                onClick=${toggleExpanded}
            >
                <h3 style=${{ margin: 0, color: "var(--text-primary)" }}>
                    ${expanded ? "▼" : "▶"} Diagnostics
                </h3>
                <span style=${{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                    ${expanded ? "collapse" : "expand"}
                </span>
            </div>

            ${expanded && html`
                <div>
                    <!-- Action row: Run + Export -->
                    <div style=${{
                        display: "flex",
                        gap: "var(--spacing-sm)",
                        marginBottom: "var(--spacing-md)",
                        alignItems: "center",
                    }}>
                        <button
                            class="btn btn-sm btn-primary"
                            onClick=${runDiagnostics}
                            disabled=${loading}
                        >
                            ${loading ? "Probing entities..." : "Run Diagnostics"}
                        </button>
                        ${results && html`
                            <button
                                class="btn btn-sm btn-secondary"
                                onClick=${exportJson}
                            >
                                Export JSON
                            </button>
                        `}
                    </div>

                    <!-- Loading spinner -->
                    ${loading && html`
                        <div style=${{
                            display: "flex",
                            alignItems: "center",
                            gap: "var(--spacing-sm)",
                            color: "var(--text-muted)",
                            fontSize: "0.85rem",
                            marginBottom: "var(--spacing-sm)",
                        }}>
                            <span class="spinner-sm"></span>
                            Probing entities...
                        </div>
                    `}

                    <!-- Error state -->
                    ${error && !loading && html`
                        <div class="error-state" style=${{ padding: "var(--spacing-sm)" }}>
                            ${error}
                        </div>
                    `}

                    <!-- Results per entity -->
                    ${results && !loading && html`
                        <div data-testid="diagnostics-results">
                            ${results.entities && results.entities.map((r) =>
                                html`<${EntityDiagCard} key=${r.entity_id} result=${r} />`
                            )}
                            ${(!results.entities || results.entities.length === 0) && html`
                                <div class="empty-state" style=${{ padding: "var(--spacing-md)" }}>
                                    No entities configured
                                </div>
                            `}
                        </div>
                    `}
                </div>
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * StatusHealthTab — main status/health view for an entity.
 *
 * Enhanced with entity-scoped system stats polling, sparklines,
 * threshold visualization, disk breakdown, and process table.
 *
 * @param {object} props
 * @param {string} props.entityId - Entity ID from URL hash
 * @param {object|null} props.entityData - Full entity data object
 * @param {boolean} props.loading - Whether initial data is still loading
 */
function StatusHealthTab({ entityId, entityData, loading }) {
    const healthSummary = useMemo(
        () => deriveCardHealthSummary(entityData),
        [entityData]
    );

    // Derive subsystem health (task 5.9)
    const healthMap = useMemo(
        () => deriveSubsystemHealth(entityData),
        [entityData]
    );

    // --- System stats polling state ---
    const [systemStats, setSystemStats] = useState(null);
    const [statsLoading, setStatsLoading] = useState(true);
    const [statsError, setStatsError] = useState(false);

    // --- Process list state ---
    const [processes, setProcesses] = useState([]);
    const [processLoading, setProcessLoading] = useState(true);
    const [processError, setProcessError] = useState(false);

    // --- Sparkline history ---
    const cpuHistoryRef = useRef([]);
    const memHistoryRef = useRef([]);
    const tempHistoryRef = useRef([]);
    const diskHistoryRef = useRef([]);
    // Force re-render when history changes
    const [historyVersion, setHistoryVersion] = useState(0);

    // --- Polling for system stats ---
    useEffect(() => {
        if (!entityId) return;

        let cancelled = false;

        const fetchStats = async () => {
            const url = `/api/entities/${encodeURIComponent(entityId)}/system/stats`;
            const result = await safeFetch(url);

            if (cancelled) return;

            if (result && result.data) {
                const data = result.data;
                setSystemStats(data);
                setStatsLoading(false);
                setStatsError(false);

                // Append to sparkline histories
                const pushHistory = (ref, value) => {
                    if (value != null && !isNaN(value)) {
                        ref.current = [...ref.current.slice(-(SPARKLINE_MAX_POINTS - 1)), value];
                    }
                };
                const memPct = data.memory_total > 0
                    ? (data.memory_used / data.memory_total) * 100
                    : 0;
                const diskPct = data.disk_total > 0
                    ? (data.disk_used / data.disk_total) * 100
                    : 0;

                pushHistory(cpuHistoryRef, data.cpu_percent);
                pushHistory(memHistoryRef, memPct);
                pushHistory(tempHistoryRef, data.cpu_temp);
                pushHistory(diskHistoryRef, diskPct);
                setHistoryVersion((v) => v + 1);
            } else {
                setStatsError(true);
                setStatsLoading(false);
            }
        };

        fetchStats();
        const intervalId = setInterval(fetchStats, STATS_POLL_INTERVAL_MS);

        return () => {
            cancelled = true;
            clearInterval(intervalId);
        };
    }, [entityId]);

    // --- Polling for processes ---
    useEffect(() => {
        if (!entityId) return;

        let cancelled = false;

        const fetchProcesses = async () => {
            const url = `/api/entities/${encodeURIComponent(entityId)}/system/processes`;
            const result = await safeFetch(url);

            if (cancelled) return;

            if (result && result.data) {
                setProcesses(result.data);
                setProcessLoading(false);
                setProcessError(false);
            } else {
                setProcessError(true);
                setProcessLoading(false);
            }
        };

        fetchProcesses();
        const intervalId = setInterval(fetchProcesses, STATS_POLL_INTERVAL_MS);

        return () => {
            cancelled = true;
            clearInterval(intervalId);
        };
    }, [entityId]);

    // Task 5.8: "Initializing..." placeholder only on truly first load
    // (before any entityData has ever arrived). During re-fetches, keep
    // showing stale data to avoid DOM teardown flash.
    if (loading && !entityData) {
        return html`
            <div class="initializing-placeholder" style=${{
                textAlign: "center",
                padding: "var(--spacing-xl) 0",
                color: "var(--text-secondary)",
            }}>
                <div style=${{ fontSize: "2em", marginBottom: "var(--spacing-sm)" }}>\u23F3</div>
                <div style=${{ fontSize: "1.2em", marginBottom: "var(--spacing-xs)" }}>
                    Initializing...
                </div>
                <div style=${{ fontSize: "0.9em", color: "var(--text-muted)" }}>
                    Waiting for health data from entity
                </div>
            </div>
        `;
    }

    // Compute gauge values from system stats endpoint (new) or fallback to entityData
    const stats = systemStats;
    const hasFreshStats = stats != null;

    const cpuPct = hasFreshStats ? stats.cpu_percent : (entityData.system_metrics || {}).cpu_percent;
    const memPct = hasFreshStats && stats.memory_total > 0
        ? (stats.memory_used / stats.memory_total) * 100
        : (entityData.system_metrics || {}).memory_percent;
    const tempC = hasFreshStats ? stats.cpu_temp : (entityData.system_metrics || {}).temperature_c;
    const diskPct = hasFreshStats && stats.disk_total > 0
        ? (stats.disk_used / stats.disk_total) * 100
        : (entityData.system_metrics || {}).disk_percent;
    const uptime = (entityData.system_metrics || {}).uptime_seconds;

    return html`
        <div class="entity-health-summary" style=${{ marginBottom: "var(--spacing-lg)" }}>
            <div style=${{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                flexWrap: "wrap",
            }}>
                <span class=${`entity-health-badge ${healthBadgeClass(healthSummary.overall === 'online' ? 'healthy' : healthSummary.overall === 'degraded' ? 'degraded' : healthSummary.overall === 'unknown' ? 'unavailable' : 'error')}`}>
                    ${healthSummary.overall}
                </span>
                <div class="entity-health-layers">
                    ${healthSummary.layers.map((layer) => html`
                        <span
                            class=${`entity-health-layer entity-health-layer--${layer.status}`}
                            title=${layer.key === "network"
                                ? `Ping reachability to poll target: ${layer.tooltip}`
                                : layer.tooltip}
                        >
                            <span class="entity-health-layer-dot"></span>
                            <span>${layer.label}</span>
                        </span>
                    `)}
                </div>
            </div>
            ${healthSummary.diagnostic && html`
                <div class="entity-health-diagnostic">
                    ${healthSummary.diagnostic}
                </div>
            `}
        </div>

        <!-- Per-subsystem health badges (task 5.9) -->
        <${SubsystemHealthRow}
            subsystems=${SUBSYSTEMS}
            healthMap=${healthMap}
        />

        <!-- System metrics gauges -->
        <div style=${{ marginBottom: "var(--spacing-lg)" }}>
            <h3 style=${{ marginBottom: "var(--spacing-sm)", color: "var(--text-primary)" }}>
                System Metrics
                ${uptime != null
                    ? html`<span style=${{
                          fontSize: "0.8rem",
                          color: "var(--text-muted)",
                          marginLeft: "var(--spacing-sm)",
                      }}>Uptime: ${formatDuration(uptime)}</span>`
                    : null}
                ${statsError && hasFreshStats ? html`
                    <span class="stale-data-indicator" style=${{
                        fontSize: "0.75rem",
                        color: "var(--accent-warning, #f59e0b)",
                        marginLeft: "var(--spacing-sm)",
                    }}>Data may be stale</span>
                ` : null}
                ${statsLoading ? html`
                    <span style=${{
                        fontSize: "0.75rem",
                        color: "var(--text-muted)",
                        marginLeft: "var(--spacing-sm)",
                    }}>Loading...</span>
                ` : null}
            </h3>
            <div class="stats-grid">
                <${MetricGauge}
                    icon="\uD83D\uDCBB"
                    label="CPU Usage"
                    value=${cpuPct}
                    unit="%"
                    percent=${cpuPct}
                    thresholds=${THRESHOLDS.cpu}
                    sparklineData=${cpuHistoryRef.current}
                    sparklineMax=${100}
                />
                <${MetricGauge}
                    icon="\uD83E\uDDE0"
                    label="Memory Usage"
                    value=${memPct}
                    unit="%"
                    percent=${memPct}
                    thresholds=${THRESHOLDS.memory}
                    sparklineData=${memHistoryRef.current}
                    sparklineMax=${100}
                />
                <${MetricGauge}
                    icon="\uD83C\uDF21\uFE0F"
                    label="Temperature"
                    value=${tempC}
                    unit="\u00B0C"
                    percent=${tempC != null ? (tempC / 100) * 100 : 0}
                    severityFn=${tempSeverity}
                    thresholds=${THRESHOLDS.temp}
                    sparklineData=${tempHistoryRef.current}
                    sparklineMax=${100}
                />
                <${MetricGauge}
                    icon="\uD83D\uDCBE"
                    label="Disk Usage"
                    value=${diskPct}
                    unit="%"
                    percent=${diskPct}
                    thresholds=${THRESHOLDS.disk}
                    sparklineData=${diskHistoryRef.current}
                    sparklineMax=${100}
                    extra=${hasFreshStats ? html`
                        <${DiskBreakdown}
                            used=${stats.disk_used}
                            total=${stats.disk_total}
                        />
                    ` : null}
                />
            </div>
        </div>

        <!-- Hardware Temperature Section (motor + camera temps) -->
        ${(() => {
            const metrics = entityData ? entityData.system_metrics : null;
            const motorTemps = metrics ? metrics.motor_temperatures : null;
            const cameraTemp = metrics ? metrics.camera_temperature_c : null;
            const eType = entityData ? entityData.entity_type : "";
            return html`
                <${TemperatureSection}
                    motorTemperatures=${motorTemps}
                    cameraTemperatureC=${cameraTemp}
                    entityType=${eType}
                />
            `;
        })()}

        <!-- Process table -->
        <${ProcessTable}
            processes=${processes}
            loading=${processLoading}
            error=${processError}
        />

        <!-- Safety Status Cards (task 3.1 — migrated from SafetyTab) -->
        <${SafetyStatusSection} />

        <!-- ROS2 Node List (task 5.2b) -->
        <${NodeListSection} entityData=${entityData} />

        <!-- Systemd Service List (task 5.2c) -->
        <${ServiceListSection}
            entityId=${entityId}
            entityData=${entityData}
        />

        <!-- Active Diagnostics (dashboard-reliability-hardening) -->
        <${DiagnosticsSection} />
    `;
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export {
    StatusHealthTab,
    MetricGauge,
    Sparkline,
    DiskBreakdown,
    ProcessTable,
    SubsystemHealthRow,
    SafetyStatusSection,
    NodeListSection,
    ServiceListSection,
    DiagnosticsSection,
    TemperatureSection,
    deriveSubsystemHealth,
    isTimestampStale,
    healthBadgeClass,
    metricSeverity,
    tempSeverity,
    SUBSYSTEMS,
    THRESHOLDS,
    SPARKLINE_MAX_POINTS,
    CAN_STALE_THRESHOLD_S,
    ENTITY_STALE_THRESHOLD_S,
};
