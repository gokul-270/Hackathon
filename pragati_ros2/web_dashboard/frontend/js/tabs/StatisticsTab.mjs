/**
 * StatisticsTab — Preact component for the Statistics + History tab.
 *
 * Combines the Operation Statistics section (session management, cotton
 * detection stats, camera stats, motor stats, vehicle stats, session history)
 * and the Historical Data section (resource charts, cotton picking trends,
 * aggregated metrics table, CSV export) into a single Preact component with
 * two sub-tabs.
 *
 * Migrated from vanilla JS as part of the incremental Preact migration
 * (task 7.2 of dashboard-frontend-migration).
 *
 * @module tabs/StatisticsTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useRef, useMemo } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch, formatDuration, convertToCSV, escapeHtml } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { ChartComponent } from "../components/ChartComponent.mjs";
import { registerTab } from "../tabRegistry.js";
import { getChartColor } from "../utils/chartColors.mjs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5000;

/** Time range options for historical data. */
const TIME_RANGES = [
    { value: "1h", label: "Last Hour", hours: 1 },
    { value: "6h", label: "Last 6 Hours", hours: 6 },
    { value: "24h", label: "Last 24 Hours", hours: 24 },
    { value: "7d", label: "Last 7 Days", hours: 168 },
    { value: "30d", label: "Last 30 Days", hours: 720 },
];

/**
 * Lazily resolve dark-theme chart scale/legend colors from CSS custom properties.
 * Must be called after DOM is ready (inside component render/useMemo).
 * @returns {{ labelColor: string, tickColor: string, gridColor: string }}
 */
function getChartTheme() {
    return {
        labelColor: getChartColor("--color-text-primary"),
        tickColor: getChartColor("--color-text-muted"),
        gridColor: getChartColor("--border-color"),
    };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Determine battery bar color based on percentage.
 * @param {number} pct
 * @returns {string} CSS color
 */
function batteryColor(pct) {
    if (pct < 20) return getChartColor("--color-error");
    if (pct < 50) return getChartColor("--color-warning");
    return getChartColor("--color-success");
}

/**
 * Determine motor status classification.
 * @param {object} motor
 * @returns {{ statusClass: string, statusIcon: string }}
 */
function motorStatus(motor) {
    const temp = motor.temperature || 0;
    const current = motor.current || 0;
    const errors = motor.errors || 0;

    if (errors > 0) return { statusClass: "error", statusIcon: "X" };
    if (temp > 60 || current > 3000) return { statusClass: "warning", statusIcon: "!" };
    return { statusClass: "ok", statusIcon: "OK" };
}

/**
 * Trigger a browser file download from a string.
 * @param {string} content - File content
 * @param {string} filename - Download filename
 * @param {string} mimeType - MIME type
 */
function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * A small stat card used in stat-cards-row layouts.
 * @param {object} props
 * @param {string|number} props.value
 * @param {string} props.label
 * @param {string} [props.className] - Extra CSS class (e.g. 'success', 'danger')
 * @param {boolean} [props.sensorless] - Show "Requires sensor integration" notice
 * @param {import('preact').ComponentChildren} [props.children] - Optional extra content (e.g. progress bar)
 */
function MiniStatCard({ value, label, className = "", sensorless = false, children }) {
    const cls = ["mini-stat-card", className, sensorless ? "sensorless-card" : ""]
        .filter(Boolean)
        .join(" ");

    return html`
        <div class=${cls}>
            <div class="mini-stat-value">${value}</div>
            <div class="mini-stat-label">${label}</div>
            ${children}
            ${sensorless && html`<div class="sensor-notice">Requires sensor integration</div>`}
        </div>
    `;
}

/**
 * Motor card for the motor stats grid.
 * @param {object} props
 * @param {string} props.motorId
 * @param {object} props.motor
 */
function MotorCard({ motorId, motor }) {
    const temp = motor.temperature || 0;
    const current = motor.current || 0;
    const errors = motor.errors || 0;
    const { statusClass, statusIcon } = motorStatus(motor);

    return html`
        <div class="motor-card ${statusClass}">
            <div class="motor-header">
                <div class="motor-name">Motor ${escapeHtml(String(motorId))}</div>
                <div class="motor-status">${statusIcon}</div>
            </div>
            <div class="motor-metrics">
                <div class="motor-metric">
                    <span class="motor-metric-label">Temperature</span>
                    <span class="motor-metric-value">${temp.toFixed(1)}°C</span>
                </div>
                <div class="motor-metric">
                    <span class="motor-metric-label">Current</span>
                    <span class="motor-metric-value">${current.toFixed(0)} mA</span>
                </div>
                <div class="motor-metric">
                    <span class="motor-metric-label">Errors</span>
                    <span class="motor-metric-value">${errors}</span>
                </div>
            </div>
        </div>
    `;
}

/**
 * Session history table.
 * @param {object} props
 * @param {Array} props.sessions
 */
function SessionHistoryTable({ sessions }) {
    if (!sessions || sessions.length === 0) {
        return html`<div class="empty-state">No session history available</div>`;
    }

    return html`
        <table class="history-table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Duration</th>
                    <th>Picked</th>
                    <th>Success Rate</th>
                    <th>Distance</th>
                    <th>Battery Used</th>
                </tr>
            </thead>
            <tbody>
                ${sessions.map(
                    (s) => html`
                        <tr key=${s.start_time}>
                            <td>${new Date(s.start_time * 1000).toLocaleString()}</td>
                            <td>${formatDuration(s.duration_seconds)}</td>
                            <td>${s.cottons_picked}</td>
                            <td>${(s.success_rate || 0).toFixed(1)}%</td>
                            <td>${(s.distance_traveled || 0).toFixed(1)}m</td>
                            <td>${(s.battery_consumed || 0).toFixed(1)}%</td>
                        </tr>
                    `
                )}
            </tbody>
        </table>
    `;
}

// ---------------------------------------------------------------------------
// Operation Statistics Sub-Tab
// ---------------------------------------------------------------------------

/**
 * Operation Statistics panel — session management, live stats, session history.
 * @param {object} props
 * @param {object|null} props.sessionData - Current session data from API
 * @param {object|null} props.motorData - Motor health data
 * @param {Array} props.sessionHistory - Session history list
 * @param {Function} props.onStartSession
 * @param {Function} props.onEndSession
 */
function OperationStatsPanel({
    sessionData,
    motorData,
    sessionHistory,
    onStartSession,
    onEndSession,
}) {
    const active = sessionData && sessionData.active && sessionData.stats;
    const stats = active ? sessionData.stats : null;

    // Compute operation time if active
    const operationTime = active && sessionData.start_time
        ? formatDuration(Date.now() / 1000 - sessionData.start_time)
        : "00:00:00";

    const avgCycleTime = active && stats && stats.cycle_count > 0
        ? ((Date.now() / 1000 - sessionData.start_time) / stats.cycle_count).toFixed(1) + "s"
        : "0s";

    // Battery info
    const hasBattery = active && stats && stats.battery_end != null && stats.battery_end !== 100;
    const batteryPct = hasBattery ? stats.battery_end : 0;

    const hasDistance = active && stats && stats.distance_traveled != null && stats.distance_traveled > 0;

    const motors = motorData && motorData.motors ? Object.entries(motorData.motors) : [];

    return html`
        <!-- Session Controls -->
        <div class="stats-panel" id="current-session-panel">
            <h3>Current Session</h3>
            ${!active && html`
                <div class="session-inactive">
                    <p>No active session</p>
                    <button class="btn" onClick=${onStartSession}>Start New Session</button>
                </div>
            `}
            ${active && html`
                <div class="stat-cards-row">
                    <${MiniStatCard} value=${stats.images_captured} label="Images Captured" />
                    <${MiniStatCard} value=${stats.cottons_detected} label="Cottons Detected" />
                    <${MiniStatCard}
                        value=${stats.cottons_picked}
                        label="Successfully Picked"
                        className="success"
                    />
                    <${MiniStatCard}
                        value=${stats.cottons_failed}
                        label="Failed Attempts"
                        className="danger"
                    />
                    <${MiniStatCard}
                        value=${stats.success_rate.toFixed(1) + "%"}
                        label="Success Rate"
                    />
                </div>
            `}
        </div>

        <!-- Camera Stats (only when session active) -->
        ${active && html`
            <div class="stats-panel">
                <h3>Camera Performance</h3>
                <div class="stat-cards-row">
                    <${MiniStatCard}
                        value=${stats.camera_fps_avg.toFixed(1)}
                        label="Average FPS"
                    />
                    <${MiniStatCard}
                        value=${stats.camera_frames_dropped}
                        label="Frames Dropped"
                    />
                    <${MiniStatCard}
                        value=${stats.camera_connected ? "Connected" : "Disconnected"}
                        label="Connection"
                    />
                    <${MiniStatCard}
                        value=${stats.camera_temp ? stats.camera_temp.toFixed(1) + "°C" : "--°C"}
                        label="Temperature"
                    />
                </div>
            </div>
        `}

        <!-- Motor Stats -->
        ${motors.length > 0 && html`
            <div class="stats-panel">
                <h3>Motor Status</h3>
                <div class="motors-grid">
                    ${motors.map(
                        ([id, motor]) => html`
                            <${MotorCard} key=${id} motorId=${id} motor=${motor} />
                        `
                    )}
                </div>
            </div>
        `}

        <!-- Vehicle Stats (only when session active) -->
        ${active && html`
            <div class="stats-panel">
                <h3>Vehicle Status</h3>
                <div class="stat-cards-row">
                    <${MiniStatCard}
                        value=${hasBattery ? batteryPct.toFixed(1) + "%" : "N/A"}
                        label="Battery Level"
                        sensorless=${!hasBattery}
                    >
                        ${hasBattery && html`
                            <div class="mini-progress">
                                <div
                                    class="mini-progress-fill"
                                    style=${{
                                        width: batteryPct + "%",
                                        backgroundColor: batteryColor(batteryPct),
                                    }}
                                ></div>
                            </div>
                        `}
                    <//>
                    <${MiniStatCard}
                        value=${hasDistance ? stats.distance_traveled.toFixed(1) + " m" : "N/A"}
                        label="Distance Traveled"
                        sensorless=${!hasDistance}
                    />
                    <${MiniStatCard} value=${operationTime} label="Operation Time" />
                    <${MiniStatCard} value=${avgCycleTime} label="Avg Cycle Time" />
                </div>
            </div>
        `}

        <!-- Session History Table -->
        <div class="stats-panel">
            <h3>Session History</h3>
            <${SessionHistoryTable} sessions=${sessionHistory} />
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Historical Data Sub-Tab
// ---------------------------------------------------------------------------

/**
 * Historical data panel — resource charts, cotton trends, aggregated metrics, CSV export.
 * @param {object} props
 * @param {string} props.range - Active time range value
 * @param {Function} props.onRangeChange
 * @param {object|null} props.historicalData - From /api/history/decimated
 * @param {Array} props.cottonSessions - From /api/session/history
 * @param {Function} props.onExport
 * @param {boolean} props.exporting
 */
function HistoricalDataPanel({
    range,
    onRangeChange,
    historicalData,
    cottonSessions,
    onExport,
    exporting,
}) {
    // ---- System resource chart data ----
    const resourceLabels = useMemo(() => {
        if (!historicalData || !historicalData.metrics) return [];
        return historicalData.metrics.map(
            (m) => new Date(m.timestamp * 1000).toLocaleTimeString()
        );
    }, [historicalData]);

    const resourceDatasets = useMemo(() => {
        if (!historicalData || !historicalData.metrics) return [];
        return [
            {
                label: "CPU %",
                data: historicalData.metrics.map((m) => m.cpu_percent || 0),
                borderColor: getChartColor("--chart-cpu"),
                backgroundColor: getChartColor("--chart-cpu-bg"),
                tension: 0.4,
                fill: true,
            },
            {
                label: "Memory %",
                data: historicalData.metrics.map((m) => m.memory_percent || 0),
                borderColor: getChartColor("--chart-memory"),
                backgroundColor: getChartColor("--chart-memory-bg"),
                tension: 0.4,
                fill: true,
            },
        ];
    }, [historicalData]);

    const resourceOptions = useMemo(
        () => ({
            plugins: { legend: { labels: { color: getChartTheme().labelColor } } },
            scales: {
                x: {
                    ticks: { color: getChartTheme().tickColor },
                    grid: { color: getChartTheme().gridColor },
                },
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { color: getChartTheme().tickColor },
                    grid: { color: getChartTheme().gridColor },
                },
            },
        }),
        []
    );

    // ---- Cotton history chart data ----
    const sortedSessions = useMemo(() => {
        if (!cottonSessions || cottonSessions.length === 0) return [];
        return [...cottonSessions].sort((a, b) => a.start_time - b.start_time);
    }, [cottonSessions]);

    const cottonLabels = useMemo(
        () =>
            sortedSessions.map((s) =>
                new Date(s.start_time * 1000).toLocaleDateString()
            ),
        [sortedSessions]
    );

    const cottonDatasets = useMemo(() => {
        if (sortedSessions.length === 0) return [];
        return [
            {
                label: "Detected",
                data: sortedSessions.map((s) => s.cottons_detected || 0),
                borderColor: getChartColor("--chart-cpu"),
                backgroundColor: getChartColor("--chart-cpu-bg"),
                tension: 0.3,
                fill: false,
            },
            {
                label: "Picked",
                data: sortedSessions.map((s) => s.cottons_picked || 0),
                borderColor: getChartColor("--chart-memory"),
                backgroundColor: getChartColor("--chart-memory-bg"),
                tension: 0.3,
                fill: false,
            },
            {
                label: "Success %",
                data: sortedSessions.map((s) => s.success_rate || 0),
                borderColor: getChartColor("--color-warning"),
                backgroundColor: getChartColor("--chart-warning-bg"),
                tension: 0.3,
                fill: false,
                yAxisID: "y1",
            },
        ];
    }, [sortedSessions]);

    const cottonOptions = useMemo(
        () => ({
            plugins: { legend: { labels: { color: getChartTheme().labelColor } } },
            scales: {
                x: {
                    ticks: { color: getChartTheme().tickColor },
                    grid: { color: getChartTheme().gridColor },
                },
                y: {
                    beginAtZero: true,
                    position: "left",
                    title: { display: true, text: "Count", color: getChartTheme().tickColor },
                    ticks: { color: getChartTheme().tickColor },
                    grid: { color: getChartTheme().gridColor },
                },
                y1: {
                    beginAtZero: true,
                    max: 100,
                    position: "right",
                    title: { display: true, text: "Success %", color: getChartTheme().tickColor },
                    ticks: { color: getChartTheme().tickColor },
                    grid: { drawOnChartArea: false },
                },
            },
        }),
        []
    );

    // ---- Aggregated metrics ----
    const aggregated = useMemo(() => {
        if (!historicalData || !historicalData.metrics || historicalData.metrics.length === 0) {
            return null;
        }
        const metrics = historicalData.metrics;
        const avgCpu = (
            metrics.reduce((sum, m) => sum + (m.cpu_percent || 0), 0) / metrics.length
        ).toFixed(1);
        const maxCpu = Math.max(...metrics.map((m) => m.cpu_percent || 0)).toFixed(1);
        const avgMem = (
            metrics.reduce((sum, m) => sum + (m.memory_percent || 0), 0) / metrics.length
        ).toFixed(1);
        const maxMem = Math.max(...metrics.map((m) => m.memory_percent || 0)).toFixed(1);
        return { avgCpu, maxCpu, avgMem, maxMem };
    }, [historicalData]);

    const hasResourceData = resourceLabels.length > 0;
    const hasCottonData = sortedSessions.length > 0;

    return html`
        <!-- Time Range Selector -->
        <div class="section-actions" style=${{ marginBottom: "16px" }}>
            <select
                class="select-input"
                value=${range}
                onChange=${(e) => onRangeChange(e.target.value)}
            >
                ${TIME_RANGES.map(
                    (r) => html`
                        <option key=${r.value} value=${r.value}>${r.label}</option>
                    `
                )}
            </select>
            <button
                class="btn btn-sm"
                onClick=${onExport}
                disabled=${exporting}
            >
                ${exporting ? "Exporting..." : "Export Data"}
            </button>
        </div>

        <!-- System Resource History Chart -->
        <div class="charts-grid">
            <div class="chart-card">
                <div class="card-header">
                    <h3>System Resource History</h3>
                </div>
                ${hasResourceData
                    ? html`
                          <${ChartComponent}
                              type="line"
                              labels=${resourceLabels}
                              datasets=${resourceDatasets}
                              options=${resourceOptions}
                              height="300px"
                          />
                      `
                    : html`<div class="section-empty">No data available for selected range</div>`}
            </div>

            <!-- Cotton Picking Trends Chart -->
            <div class="chart-card">
                <div class="card-header">
                    <h3>Cotton Picking Trends</h3>
                </div>
                ${hasCottonData
                    ? html`
                          <${ChartComponent}
                              type="line"
                              labels=${cottonLabels}
                              datasets=${cottonDatasets}
                              options=${cottonOptions}
                              height="300px"
                          />
                      `
                    : html`<div class="section-empty">No session data available</div>`}
            </div>
        </div>

        <!-- Aggregated Performance Metrics -->
        <div class="stats-panel">
            <h3>Performance Metrics Over Time</h3>
            ${aggregated
                ? html`
                      <div class="stat-cards-row">
                          <${MiniStatCard} value=${aggregated.avgCpu + "%"} label="Average CPU" />
                          <${MiniStatCard} value=${aggregated.maxCpu + "%"} label="Peak CPU" />
                          <${MiniStatCard} value=${aggregated.avgMem + "%"} label="Average Memory" />
                          <${MiniStatCard} value=${aggregated.maxMem + "%"} label="Peak Memory" />
                      </div>
                  `
                : html`<div class="section-empty">No historical data available</div>`}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

function StatisticsTab() {
    const { showToast } = useToast();
    const mountedRef = useRef(true);

    // ---- Sub-tab state ----
    // Default to "history" sub-tab when navigated via #history URL
    const [activeSubTab, setActiveSubTab] = useState(() => {
        const hash = location.hash.replace("#", "");
        return hash === "history" ? "history" : "operations";
    });

    // Sync sub-tab when hash changes (e.g. sidebar click to #history)
    useEffect(() => {
        function onHashChange() {
            const hash = location.hash.replace("#", "");
            if (hash === "history") setActiveSubTab("history");
            else if (hash === "statistics") setActiveSubTab("operations");
        }
        window.addEventListener("hashchange", onHashChange);
        return () => window.removeEventListener("hashchange", onHashChange);
    }, []);

    // ---- Operation Statistics state ----
    const [sessionData, setSessionData] = useState(null);
    const [motorData, setMotorData] = useState(null);
    const [sessionHistory, setSessionHistory] = useState([]);

    // ---- Historical Data state ----
    const [historyRange, setHistoryRange] = useState("24h");
    const [historicalData, setHistoricalData] = useState(null);
    const [cottonSessions, setCottonSessions] = useState([]);
    const [exporting, setExporting] = useState(false);

    // ---- Loading state ----
    const [loading, setLoading] = useState(true);

    // ---- Data fetching callbacks ----

    const loadSessionData = useCallback(async () => {
        const data = await safeFetch("/api/session/current");
        if (!mountedRef.current) return;
        if (data && !data.error) setSessionData(data);
    }, []);

    const loadMotorData = useCallback(async () => {
        const data = await safeFetch("/api/health/motors");
        if (!mountedRef.current) return;
        if (data && !data.error) setMotorData(data);
    }, []);

    const loadSessionHistory = useCallback(async () => {
        const data = await safeFetch("/api/session/history?limit=10");
        if (!mountedRef.current) return;
        if (data && data.sessions) setSessionHistory(data.sessions);
    }, []);

    const loadHistoricalData = useCallback(
        async (range) => {
            const r = range || historyRange;
            const hours = TIME_RANGES.find((t) => t.value === r)?.hours || 24;
            const data = await safeFetch(
                `/api/history/decimated?hours=${hours}&points=500`
            );
            if (!mountedRef.current) return;
            if (data && !data.error) setHistoricalData(data);
        },
        [historyRange]
    );

    const loadCottonSessions = useCallback(async () => {
        const data = await safeFetch("/api/session/history?limit=20");
        if (!mountedRef.current) return;
        if (data && data.sessions) setCottonSessions(data.sessions);
    }, []);

    // ---- Combined data loader ----

    const loadAll = useCallback(async () => {
        await Promise.all([
            loadSessionData(),
            loadMotorData(),
            loadSessionHistory(),
            loadHistoricalData(),
            loadCottonSessions(),
        ]);
        if (mountedRef.current) setLoading(false);
    }, [loadSessionData, loadMotorData, loadSessionHistory, loadHistoricalData, loadCottonSessions]);

    // ---- Session actions ----

    const handleStartSession = useCallback(async () => {
        const data = await safeFetch("/api/session/start", { method: "POST" });
        if (!data) {
            showToast("Failed to start session", "error");
            return;
        }
        if (data.success) {
            showToast("Operation session started!", "success");
            await loadSessionData();
        } else {
            showToast(data.error || "Failed to start session", "error");
        }
    }, [showToast, loadSessionData]);

    const handleEndSession = useCallback(async () => {
        const data = await safeFetch("/api/session/end", { method: "POST" });
        if (!data) {
            showToast("Failed to end session", "error");
            return;
        }
        if (data.success) {
            showToast("Session ended and saved!", "success");
            await Promise.all([loadSessionData(), loadSessionHistory()]);
        } else {
            showToast(data.error || "Failed to end session", "error");
        }
    }, [showToast, loadSessionData, loadSessionHistory]);

    // ---- Export handler ----

    const handleExport = useCallback(async () => {
        setExporting(true);
        try {
            const now = Date.now() / 1000;
            const hours = TIME_RANGES.find((t) => t.value === historyRange)?.hours || 24;
            const start_time = now - hours * 3600;
            const end_time = now;

            const data = await safeFetch(
                `/api/history/metrics?start_time=${start_time}&end_time=${end_time}`
            );
            if (!data) {
                showToast("Failed to export data", "error");
                return;
            }
            if (data.error || !data.metrics || data.metrics.length === 0) {
                showToast("No data to export", "warning");
                return;
            }

            const csv = convertToCSV(data.metrics);
            downloadFile(
                csv,
                `dashboard_history_${historyRange}_${Date.now()}.csv`,
                "text/csv"
            );
            showToast("Data exported successfully!", "success");
        } finally {
            if (mountedRef.current) setExporting(false);
        }
    }, [historyRange, showToast]);

    // ---- Range change handler ----

    const handleRangeChange = useCallback(
        (newRange) => {
            setHistoryRange(newRange);
            loadHistoricalData(newRange);
        },
        [loadHistoricalData]
    );

    // ---- Lifecycle ----

    // Initial load
    useEffect(() => {
        mountedRef.current = true;
        loadAll();
        return () => {
            mountedRef.current = false;
        };
    }, [loadAll]);

    // Polling — refresh data relevant to active sub-tab
    useEffect(() => {
        const id = setInterval(() => {
            if (activeSubTab === "operations") {
                loadSessionData();
                loadMotorData();
            } else {
                loadHistoricalData();
            }
        }, POLL_INTERVAL_MS);

        return () => clearInterval(id);
    }, [activeSubTab, loadSessionData, loadMotorData, loadHistoricalData]);

    // ---- Render ----

    if (loading) {
        return html`<div class="loading">Loading statistics...</div>`;
    }

    return html`
        <div class="section-header">
            <h2>Statistics & History</h2>
            <div class="section-actions">
                ${activeSubTab === "operations" && html`
                    <button class="btn btn-sm" onClick=${handleStartSession}>
                        Start Session
                    </button>
                    <button class="btn btn-sm" onClick=${handleEndSession}>
                        End Session
                    </button>
                `}
            </div>
        </div>

        <!-- Sub-tab navigation -->
        <div class="sub-tab-bar">
            <button
                class="sub-tab-btn${activeSubTab === "operations" ? " active" : ""}"
                onClick=${() => setActiveSubTab("operations")}
            >
                Current Session
            </button>
            <button
                class="sub-tab-btn${activeSubTab === "history" ? " active" : ""}"
                onClick=${() => setActiveSubTab("history")}
            >
                History
            </button>
        </div>

        <!-- Sub-tab content -->
        ${activeSubTab === "operations" && html`
            <${OperationStatsPanel}
                sessionData=${sessionData}
                motorData=${motorData}
                sessionHistory=${sessionHistory}
                onStartSession=${handleStartSession}
                onEndSession=${handleEndSession}
            />
        `}
        ${activeSubTab === "history" && html`
            <${HistoricalDataPanel}
                range=${historyRange}
                onRangeChange=${handleRangeChange}
                historicalData=${historicalData}
                cottonSessions=${cottonSessions}
                onExport=${handleExport}
                exporting=${exporting}
            />
        `}
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("statistics", StatisticsTab);
registerTab("history", StatisticsTab);

export {
    StatisticsTab,
    OperationStatsPanel,
    HistoricalDataPanel,
    MiniStatCard,
    MotorCard,
    SessionHistoryTable,
    TIME_RANGES,
};
