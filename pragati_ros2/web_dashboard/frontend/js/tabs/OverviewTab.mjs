/**
 * OverviewTab — Preact component for the System Overview landing page.
 *
 * Displays:
 * - System stats cards (CPU, Memory, Active Nodes, Topics)
 * - CPU & Memory Trends chart (rolling 30-point line chart)
 * - Top Resource Consumers chart (bar chart of top 5 nodes by CPU)
 * - System health cards (Motors, CAN Bus, Safety, Detection)
 * - System info (hostname, platform, uptime, ROS2 distro, connectivity)
 *
 * Consumes real-time data via WebSocketContext and falls back to HTTP
 * polling when WebSocket data is unavailable.
 *
 * Migrated from vanilla JS (dashboard.js) as part of the incremental
 * Preact migration (task 8.1 of dashboard-frontend-migration).
 *
 * @module tabs/OverviewTab
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useCallback,
    useContext,
    useRef,
    useMemo,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch, formatBytes, formatDuration } from "../utils.js";
import { ChartComponent } from "../components/ChartComponent.mjs";
import { WebSocketContext } from "../app.js";
import { registerTab } from "../tabRegistry.js";
import { getChartColor } from "../utils/chartColors.mjs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5000;
const SYSTEM_INFO_POLL_MS = 30000;
const MAX_CHART_POINTS = 30;

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
 * Determine health card CSS class from status string.
 * Supports the 4-state model: healthy, degraded/warning, error/critical, unavailable.
 * @param {string|undefined} status
 * @returns {string}
 */
function healthClass(status) {
    if (!status) return "health-unavailable";
    const s = status.toLowerCase();
    if (s === "ok" || s === "healthy") return "health-ok";
    if (s === "unavailable") return "health-unavailable";
    if (s === "unknown") return "health-unknown";
    return "health-error";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * A stat card displaying a value with optional progress bar.
 * @param {object} props
 * @param {string} props.icon - Emoji icon
 * @param {string} props.label
 * @param {string|number} props.value
 * @param {string} [props.subtitle] - Small text below the value
 * @param {number} [props.barPercent] - If provided, renders a progress bar
 */
function StatCard({ icon, label, value, subtitle, barPercent }) {
    return html`
        <div class="stat-card">
            <div class="stat-icon">${icon}</div>
            <div class="stat-content">
                <div class="stat-label">${label}</div>
                <div class="stat-value">${value}</div>
                ${barPercent != null &&
                html`
                    <div class="stat-bar">
                        <div
                            class="stat-bar-fill"
                            style=${{ width: `${Math.min(barPercent, 100)}%` }}
                        ></div>
                    </div>
                `}
                ${subtitle != null &&
                barPercent == null &&
                html` <div class="stat-mini">${subtitle}</div> `}
            </div>
        </div>
    `;
}

/**
 * A health status card for a subsystem.
 * @param {object} props
 * @param {string} props.id - CSS id for the card
 * @param {string} props.icon - Emoji icon
 * @param {string} props.label
 * @param {object|null} props.subsystem - Health data for this subsystem
 */
function HealthCard({ id, icon, label, subsystem }) {
    const status = subsystem ? subsystem.status || "Unknown" : "Unavailable";
    const cls = healthClass(subsystem ? subsystem.status : null);

    return html`
        <div id=${id} class="health-card ${cls}">
            <div class="health-icon">${icon}</div>
            <div class="health-info">
                <div class="health-label">${label}</div>
                <div class="health-status">${status}</div>
            </div>
        </div>
    `;
}

/**
 * System info row — hostname, platform, uptime, ROS2 distro, connectivity.
 * @param {object} props
 * @param {object|null} props.info - System info from /api/system/info
 * @param {boolean} props.wsConnected - WebSocket connection state
 */
function SystemInfoPanel({ info, wsConnected }) {
    const hostname = info ? info.hostname || "--" : "--";
    const platform = info ? info.platform || "--" : "--";
    const rosDistro = info ? info.ros_distro || "Unknown" : "--";
    const version = info ? info.dashboard_version || "1.0.0" : "--";

    let uptimeText = "--";
    if (info && info.uptime_seconds) {
        const secs = info.uptime_seconds;
        const h = Math.floor(secs / 3600);
        const m = Math.floor((secs % 3600) / 60);
        uptimeText = h > 0 ? `${h}h ${m}m` : `${m}m`;
    }

    return html`
        <div class="stats-panel">
            <h3>System Information</h3>
            <div class="info-grid" style=${{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                gap: "12px",
            }}>
                <div class="info-item">
                    <span class="info-label">Hostname</span>
                    <span class="info-value">${hostname}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Platform</span>
                    <span class="info-value">${platform}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Uptime</span>
                    <span class="info-value">${uptimeText}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">ROS2 Distro</span>
                    <span class="info-value">${rosDistro}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Dashboard</span>
                    <span class="info-value">v${version}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">Backend</span>
                    <span class="info-value" style=${{
                        color: info
                            ? "var(--color-success)"
                            : "var(--color-error)",
                    }}>
                        ${info ? "Connected" : "Disconnected"}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">WebSocket</span>
                    <span class="info-value" style=${{
                        color: wsConnected
                            ? "var(--color-success)"
                            : "var(--color-error)",
                    }}>
                        ${wsConnected ? "Connected" : "Disconnected"}
                    </span>
                </div>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

function OverviewTab() {
    const { data: wsData, connected: wsConnected } = useContext(WebSocketContext);
    const mountedRef = useRef(true);

    // ---- State ----
    const [perfData, setPerfData] = useState(null);
    const [healthData, setHealthData] = useState(null);
    const [systemInfo, setSystemInfo] = useState(null);
    const [loading, setLoading] = useState(true);
    const [themeKey, setThemeKey] = useState(0);

    // Rolling chart data — kept in a ref to avoid re-renders on every push,
    // then synced to state for ChartComponent props.
    const chartDataRef = useRef({ labels: [], cpu: [], mem: [] });
    const [chartLabels, setChartLabels] = useState([]);
    const [chartCpu, setChartCpu] = useState([]);
    const [chartMem, setChartMem] = useState([]);

    // ---- Theme change observer (for chart reactivity) ----
    useEffect(() => {
        const observer = new MutationObserver(() => {
            setThemeKey((k) => k + 1);
        });
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["class", "data-theme"],
        });
        return () => observer.disconnect();
    }, []);

    // ---- Append a data point to the rolling chart ----
    const pushChartPoint = useCallback((cpuVal, memVal) => {
        const cd = chartDataRef.current;
        const now = new Date().toLocaleTimeString();

        cd.labels.push(now);
        cd.cpu.push(cpuVal);
        cd.mem.push(memVal);

        // Keep last MAX_CHART_POINTS points
        if (cd.labels.length > MAX_CHART_POINTS) {
            cd.labels.shift();
            cd.cpu.shift();
            cd.mem.shift();
        }

        // Sync to state (new arrays so ChartComponent sees a change)
        setChartLabels([...cd.labels]);
        setChartCpu([...cd.cpu]);
        setChartMem([...cd.mem]);
    }, []);

    // ---- Data fetching callbacks ----

    const loadPerformance = useCallback(async () => {
        const data = await safeFetch("/api/performance/summary");
        if (!mountedRef.current) return;
        if (data && !data.error) {
            setPerfData(data);
            if (data.system) {
                pushChartPoint(
                    data.system.cpu_percent || 0,
                    data.system.memory_percent || 0
                );
            }
        }
    }, [pushChartPoint]);

    const loadHealth = useCallback(async () => {
        const data = await safeFetch("/api/health/system");
        if (!mountedRef.current) return;
        if (data && !data.error) setHealthData(data);
    }, []);

    const loadSystemInfo = useCallback(async () => {
        const data = await safeFetch("/api/system/info");
        if (!mountedRef.current) return;
        if (data) setSystemInfo(data);
    }, []);

    // ---- Combined initial loader ----

    const loadAll = useCallback(async () => {
        await Promise.all([loadPerformance(), loadHealth(), loadSystemInfo()]);
        if (mountedRef.current) setLoading(false);
    }, [loadPerformance, loadHealth, loadSystemInfo]);

    // ---- WebSocket data consumption ----

    useEffect(() => {
        if (!wsData) return;

        // performance_update messages
        if (wsData.performance_update) {
            const payload = wsData.performance_update;
            if (payload && !payload.error) {
                setPerfData(payload);
                if (payload.system) {
                    pushChartPoint(
                        payload.system.cpu_percent || 0,
                        payload.system.memory_percent || 0
                    );
                }
            }
        }

        // health_update messages
        if (wsData.health_update) {
            const payload = wsData.health_update;
            if (payload && !payload.error) {
                setHealthData(payload);
            }
        }
    }, [wsData, pushChartPoint]);

    // ---- Lifecycle: initial load ----

    useEffect(() => {
        mountedRef.current = true;
        loadAll();
        return () => {
            mountedRef.current = false;
        };
    }, [loadAll]);

    // ---- Polling fallback for performance + health ----

    useEffect(() => {
        if (wsConnected) return; // WebSocket active — skip HTTP polling
        const id = setInterval(() => {
            loadPerformance();
            loadHealth();
        }, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [loadPerformance, loadHealth, wsConnected]);

    // ---- Slower poll for system info (hostname, uptime, etc.) ----

    useEffect(() => {
        const id = setInterval(loadSystemInfo, SYSTEM_INFO_POLL_MS);
        return () => clearInterval(id);
    }, [loadSystemInfo]);

    // ---- ROS2 availability from system_state ----

    const systemState = wsData ? wsData.system_state : null;
    const ros2Available = systemState ? systemState.ros2_available : null;
    const isInitializing = systemState === null || systemState === undefined;

    // ---- Derived values ----

    const cpuPercent = perfData && perfData.system
        ? perfData.system.cpu_percent || 0
        : 0;
    const memPercent = perfData && perfData.system
        ? perfData.system.memory_percent || 0
        : 0;
    // Show null (not 0) when ROS2 unavailable
    const nodeCount = ros2Available === false ? null
        : (perfData && perfData.nodes ? perfData.nodes.total || 0 : 0);
    const topicCount = ros2Available === false ? null
        : (perfData && perfData.topics ? perfData.topics.total || 0 : 0);

    // Top CPU consumers for bar chart
    const topNodes = perfData && perfData.nodes && perfData.nodes.top_cpu
        ? perfData.nodes.top_cpu.slice(0, 5)
        : [];

    // ---- Chart data (memoized) ----

    // CPU & Memory Trends (line chart)
    const systemChartDatasets = useMemo(
        () => [
            {
                label: "CPU %",
                data: chartCpu,
                borderColor: getChartColor("--chart-cpu"),
                backgroundColor: getChartColor("--chart-cpu-bg"),
                tension: 0.4,
                fill: true,
            },
            {
                label: "Memory %",
                data: chartMem,
                borderColor: getChartColor("--chart-memory"),
                backgroundColor: getChartColor("--chart-memory-bg"),
                tension: 0.4,
                fill: true,
            },
        ],
        [chartCpu, chartMem, themeKey]
    );

    const systemChartOptions = useMemo(
        () => ({
            plugins: {
                legend: { labels: { color: getChartTheme().labelColor } },
            },
            scales: {
                x: {
                    display: false,
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
        [themeKey]
    );

    // Top Resource Consumers (bar chart)
    const nodesChartLabels = useMemo(
        () => topNodes.map((n) => n.name),
        [topNodes]
    );

    const nodesChartDatasets = useMemo(
        () => [
            {
                label: "CPU %",
                data: topNodes.map((n) => n.cpu),
                backgroundColor: getChartColor("--chart-cpu-bg-solid"),
                borderColor: getChartColor("--chart-cpu"),
                borderWidth: 1,
            },
        ],
        [topNodes]
    );

    const nodesChartOptions = useMemo(
        () => ({
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: {
                    ticks: { color: getChartTheme().tickColor },
                    grid: { color: getChartTheme().gridColor },
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: getChartTheme().tickColor },
                    grid: { color: getChartTheme().gridColor },
                },
            },
        }),
        [themeKey]
    );

    // ---- Render ----

    if (isInitializing && loading) {
        return html`<div class="loading" style=${{ textAlign: 'center', padding: 'var(--spacing-xl)' }}>
            <div style=${{ fontSize: '1.2em', marginBottom: 'var(--spacing-sm)' }}>Initializing...</div>
            <div style=${{ fontSize: '0.9em', color: 'var(--text-muted)' }}>Waiting for system state</div>
        </div>`;
    }

    if (loading) {
        return html`<div class="loading">Loading system overview...</div>`;
    }

    return html`
        <div class="section-header">
            <h2>System Overview</h2>
        </div>

        ${ros2Available === false && html`
            <div class="no-ros2-banner" style=${{
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--accent-warning)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--spacing-md)',
                marginBottom: 'var(--spacing-md)',
                color: 'var(--accent-warning)',
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--spacing-sm)',
            }}>
                <span style=${{ fontSize: '1.2em' }}>⚠️</span>
                <span>ROS2 is not running — showing system metrics only. Node and topic data unavailable.</span>
            </div>
        `}

        <!-- Stats Grid -->
        <div class="stats-grid">
            <${StatCard}
                icon="🖥️"
                label="CPU Usage"
                value="${cpuPercent.toFixed(1)}%"
                barPercent=${cpuPercent}
            />
            <${StatCard}
                icon="💾"
                label="Memory Usage"
                value="${memPercent.toFixed(1)}%"
                barPercent=${memPercent}
            />
            <${StatCard}
                icon="🔷"
                label="Active Nodes"
                value=${nodeCount === null ? 'N/A' : nodeCount}
                subtitle=${nodeCount === null ? 'Unavailable' : 'Running'}
            />
            <${StatCard}
                icon="📡"
                label="Topics"
                value=${topicCount === null ? 'N/A' : topicCount}
                subtitle=${topicCount === null ? 'Unavailable' : 'Active'}
            />
        </div>

        <!-- Charts Row -->
        <div class="charts-grid">
            <div class="chart-card">
                <div class="card-header">
                    <h3>CPU & Memory Trends</h3>
                    <span class="card-subtitle">Last 60 seconds</span>
                </div>
                <${ChartComponent}
                    type="line"
                    labels=${chartLabels}
                    datasets=${systemChartDatasets}
                    options=${systemChartOptions}
                    height="300px"
                />
            </div>

            <div class="chart-card">
                <div class="card-header">
                    <h3>Top Resource Consumers</h3>
                    <span class="card-subtitle">CPU Usage</span>
                </div>
                ${topNodes.length > 0
                    ? html`
                          <${ChartComponent}
                              type="bar"
                              labels=${nodesChartLabels}
                              datasets=${nodesChartDatasets}
                              options=${nodesChartOptions}
                              height="300px"
                          />
                      `
                    : html`<div class="section-empty" style=${{
                          height: "300px",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                      }}>No node data available</div>`}
            </div>
        </div>

        <!-- Health Status Cards -->
        <div class="stats-panel">
            <h3>Subsystem Health</h3>
            <div class="health-grid" style=${{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                gap: "12px",
                marginTop: "12px",
            }}>
                <${HealthCard}
                    id="motors-health"
                    icon="⚙️"
                    label="Motors"
                    subsystem=${healthData ? healthData.motors : null}
                />
                <${HealthCard}
                    id="can-health"
                    icon="🔌"
                    label="CAN Bus"
                    subsystem=${healthData ? healthData.can_bus : null}
                />
                <${HealthCard}
                    id="safety-health"
                    icon="🛡️"
                    label="Safety"
                    subsystem=${healthData ? healthData.safety : null}
                />
                <${HealthCard}
                    id="detection-health"
                    icon="📷"
                    label="Detection"
                    subsystem=${healthData ? healthData.detection : null}
                />
            </div>
        </div>

        <!-- System Information -->
        <${SystemInfoPanel}
            info=${systemInfo}
            wsConnected=${wsConnected}
        />
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("overview", OverviewTab);

export { OverviewTab, StatCard, HealthCard, SystemInfoPanel };
