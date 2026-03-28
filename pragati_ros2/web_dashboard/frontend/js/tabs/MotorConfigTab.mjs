/**
 * MotorConfigTab — Preact component for the Motor Config tab.
 *
 * Migrated from vanilla JS (motor_config.js, 3562 lines) as part of task 8.2
 * of dashboard-frontend-migration.
 *
 * Sub-components:
 *   - MotorSelector — motor dropdown + status badge
 *   - SafetyBar — e-stop, oscillation, session status, limit override
 *   - PIDPanel — gain sliders, read/apply/save/revert, step size
 *   - StepTestPanel — step response config + run + progress
 *   - AutoTunePanel — Z-N auto-suggest, rule comparison, apply suggestion
 *   - ProfilePanel — load/save gain profiles
 *   - WizardPanel — guided 3-loop tuning wizard
 *   - MetricsPanel — performance metrics grid
 *   - SessionLog — log entries + export
 *   - CommandsPanel — motor commands tab (torque/speed/angle)
 *   - BasicSettingPanel — read-only basic config (driver ID, bus, baudrates)
 *   - ProtectionSettingPanel — read-only protection thresholds/enables
 *   - LimitsSettingPanel — writable limits (torque, speed, angle, ramps)
 *   - EncoderPanel — encoder read/write/zero
 *   - StatePanel — live motor state display
 *   - MotorChartsPanel — live chart + step response charts
 *
 * @module tabs/MotorConfigTab
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useCallback,
    useRef,
    useMemo,
    useContext,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { ChartComponent } from "../components/ChartComponent.mjs";
import {
    useConfirmDialog,
    ConfirmationDialog,
} from "../components/ConfirmationDialog.mjs";
import { registerTab } from "../tabRegistry.js";
import { WebSocketContext } from "../app.js";
import { getChartColor } from "../utils/chartColors.mjs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GAIN_KEYS = [
    { key: "angle_kp", label: "Angle Kp", loop: "angle", param: "kp" },
    { key: "angle_ki", label: "Angle Ki", loop: "angle", param: "ki" },
    { key: "angle_kd", label: "Angle Kd", loop: "angle", param: "kd" },
    { key: "speed_kp", label: "Speed Kp", loop: "speed", param: "kp" },
    { key: "speed_ki", label: "Speed Ki", loop: "speed", param: "ki" },
    { key: "speed_kd", label: "Speed Kd", loop: "speed", param: "kd" },
    { key: "current_kp", label: "Current Kp", loop: "current", param: "kp" },
    { key: "current_ki", label: "Current Ki", loop: "current", param: "ki" },
    { key: "current_kd", label: "Current Kd", loop: "current", param: "kd" },
];

/**
 * Lazily resolve motor chart colors from CSS custom properties.
 * Must be called after DOM is ready (inside a component render/effect).
 * @returns {object}
 */
function getMotorChartColors() {
    return {
        position: getChartColor("--chart-position"),
        velocity: getChartColor("--chart-velocity"),
        current: getChartColor("--chart-current"),
        setpoint: getChartColor("--chart-setpoint"),
        error: getChartColor("--chart-error"),
        grid: getChartColor("--chart-motor-grid"),
        text: getChartColor("--chart-motor-text"),
        bg: getChartColor("--chart-motor-bg"),
    };
}

/** Metric thresholds: pass < warn, else fail */
const METRIC_THRESHOLDS = {
    rise_time: { pass: 0.5, warn: 1.0, unit: "s", fmt: 2 },
    settling_time: { pass: 1.0, warn: 2.0, unit: "s", fmt: 2 },
    overshoot_percent: { pass: 10, warn: 25, unit: "%", fmt: 1 },
    steady_state_error: { pass: 0.5, warn: 1.0, unit: "\u00b0", fmt: 2 },
    iae: { pass: null, warn: null, unit: "", fmt: 3 },
    ise: { pass: null, warn: null, unit: "", fmt: 3 },
    itse: { pass: null, warn: null, unit: "", fmt: 3 },
};

const MAX_LIVE_POINTS_DEFAULT = 100;
const MAX_OVERLAYS = 5;
const OVERLAY_COLORS = [
    "#4dc9f6",  // cyan
    "#f67019",  // orange
    "#f53794",  // pink
    "#537bc4",  // blue
    "#acc236",  // lime
];
const MAX_LOG_ENTRIES = 50;
const NODE_CHECK_INTERVAL_MS = 10000;
const WS_MAX_RETRIES = 10;
const WS_RECONNECT_DELAY = 5000;

const RULE_DISPLAY_NAMES = {
    classic_pid: "Classic PID",
    pi: "PI",
    p_only: "P-only",
    pessen: "Pessen",
    no_overshoot: "No Overshoot",
    some_overshoot: "Some Overshoot",
};

/** Command mode names for display */
const MODE_NAMES = [
    "Torque (0xA1)",
    "Speed (0xA2)",
    "Multi-turn Angle (0xA3)",
    "Multi-turn Angle+Speed (0xA4)",
    "Single-turn Angle (0xA5)",
    "Single-turn Angle+Speed (0xA6)",
    "Increment Angle (0xA7)",
    "Increment Angle+Speed (0xA8)",
];

/** Validation ranges per command mode */
const CMD_RANGES = {
    0: { value: [-2000, 2000], unit: "mA" },
    1: { value: [-900, 900], unit: "dps" },
    2: { value: [-21474836, 21474836], unit: "deg" },
    3: {
        value: [-21474836, 21474836],
        unit: "deg",
        max_speed: [0, 900],
    },
    4: { value: [0, 359.99], unit: "deg", direction: true },
    5: {
        value: [0, 359.99],
        unit: "deg",
        direction: true,
        max_speed: [0, 900],
    },
    6: { value: [-21474836, 21474836], unit: "deg" },
    7: {
        value: [-21474836, 21474836],
        unit: "deg",
        max_speed: [0, 900],
    },
};

/** Step sizes per command mode type */
const CMD_STEP_SIZES = {
    0: [50, 200],
    1: [1, 10],
    2: [1, 10],
    3: [1, 10],
    4: [1, 10],
    5: [1, 10],
    6: [1, 10],
    7: [1, 10],
};

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------

/**
 * API call helper that prepends the origin and parses JSON.
 * @param {string} path
 * @param {string} [method='GET']
 * @param {object} [body]
 * @returns {Promise<any>}
 */
async function api(path, method, body) {
    const opts = {
        method: method || "GET",
        headers: { "Content-Type": "application/json" },
    };
    if (body) opts.body = JSON.stringify(body);
    const base = window.location.origin;
    return safeFetch(`${base}${path}`, opts);
}

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

/** Escape HTML entities for safe display. */
function esc(val) {
    if (val == null) return "";
    return String(val)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

/** Convert hex color to rgba with alpha. */
function fadeColor(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
}

/** Clamp a gain value to limits if available. */
function clampGain(key, value, gainLimits, limitOverride) {
    if (!gainLimits || limitOverride) return value;
    const gd = GAIN_KEYS.find((g) => g.key === key);
    if (!gd) return value;
    const limits = gainLimits[gd.loop]?.[gd.param];
    if (!limits) return value;
    return Math.max(limits.min, Math.min(limits.max, value));
}

/** Download JSON data as a file. */
function downloadJson(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/** Download CSV string as a file. */
function downloadCsv(csv, filename) {
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/** Classify a metric value as 'pass', 'warn', or 'fail'. */
function metricClass(key, val) {
    const th = METRIC_THRESHOLDS[key];
    if (!th || th.pass == null || val == null) return "";
    if (val < th.pass) return "pass";
    if (val < th.warn) return "warn";
    return "fail";
}

/** Format a metric value. */
function metricFmt(key, val) {
    if (val == null) return "--";
    const th = METRIC_THRESHOLDS[key];
    const fmt = th?.fmt ?? 2;
    const unit = th?.unit ?? "";
    return `${Number(val).toFixed(fmt)}${unit}`;
}

// ---------------------------------------------------------------------------
// Sub-component: MotorSelector
// ---------------------------------------------------------------------------

function MotorSelector({
    motors, selectedMotor, onSelect, motorStatus, onRead, disabled,
    transport, onTransportChange, transportInfo,
    connInfo, editMotorId, onEditMotorId, editBaudrate, onEditBaudrate,
    editPort, onEditPort,
    onUpdateConnection, onConnect, onDisconnect,
    showToast, disconnected, onRefresh, refreshing,
    onMotorStateChange,
}) {
    const onChange = useCallback(
        (e) => onSelect(e.target.value),
        [onSelect],
    );

    const connected = connInfo?.connected || false;
    const hasChanges = (editMotorId !== connInfo?.motor_id) || (editBaudrate !== connInfo?.baudrate) || (editPort !== (connInfo?.serial_port || ''));

    // Comm error counter (polled every 5s)
    const [commErrors, setCommErrors] = useState(0);
    useEffect(() => {
        const timer = setInterval(async () => {
            try {
                const resp = await api("/api/motor/serial_log?limit=0");
                setCommErrors(resp.comm_errors || 0);
            } catch {}
        }, 5000);
        return () => clearInterval(timer);
    }, []);

    // Serial port auto-detection
    const [detectedPorts, setDetectedPorts] = useState([]);
    const [showPortDropdown, setShowPortDropdown] = useState(false);
    const portRef = useRef(null);

    const fetchPorts = useCallback(async () => {
        try {
            const resp = await api("/api/motor/serial_ports");
            setDetectedPorts(resp.ports || []);
        } catch {}
    }, []);

    // Fetch on mount
    useEffect(() => { fetchPorts(); }, []);

    // Close dropdown on outside click
    useEffect(() => {
        const handler = (e) => {
            if (portRef.current && !portRef.current.contains(e.target)) {
                setShowPortDropdown(false);
            }
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, []);

    // Motor Off — send lifecycle off (action=1 integer)
    const motorOff = useCallback(async () => {
        if (!selectedMotor) return;
        try {
            const data = await api(`/api/motor/${selectedMotor.motor_id}/lifecycle`, "POST", { action: 1 });
            showToast("Motor Off", "success");
            if (data?.success && onMotorStateChange) onMotorStateChange("OFF");
        } catch (e) { showToast("Motor Off failed", "error"); }
    }, [selectedMotor, showToast, onMotorStateChange]);

    // Motor On — send lifecycle on (action=0 integer, not string)
    const motorOn = useCallback(async () => {
        if (!selectedMotor) return;
        try {
            const data = await api(`/api/motor/${selectedMotor.motor_id}/lifecycle`, "POST", { action: 0 });
            showToast("Motor On", "success");
            if (data?.success && onMotorStateChange) onMotorStateChange("RUNNING");
        } catch (e) { showToast("Motor On failed", "error"); }
    }, [selectedMotor, showToast, onMotorStateChange]);

    return html`
        <div class="pid-motor-selector card">
            <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 8px 0;">
                <!-- Serial port (combo: dropdown + manual entry) -->
                <label ref=${portRef} style="display: flex; align-items: center; gap: 4px; font-size: 0.85em; color: var(--color-text-secondary); position: relative;">
                    Port
                    <div style="position: relative; display: inline-block;">
                        <input type="text" value=${editPort}
                            placeholder="/dev/ttyUSB0"
                            onInput=${(e) => onEditPort(e.target.value)}
                            onFocus=${() => { fetchPorts(); setShowPortDropdown(true); }}
                            style="width: 160px; padding: 4px 24px 4px 6px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-bg-secondary); color: var(--color-text-primary); font-family: monospace; font-size: 0.85em;" />
                        <button onClick=${() => { fetchPorts(); setShowPortDropdown(!showPortDropdown); }}
                            style="position: absolute; right: 2px; top: 50%; transform: translateY(-50%); background: none; border: none; color: var(--color-text-secondary); cursor: pointer; padding: 2px 4px; font-size: 0.75em;"
                            title="Detect serial ports">▼</button>
                        ${showPortDropdown && detectedPorts.length > 0 && html`
                            <div style="position: absolute; top: 100%; left: 0; right: 0; z-index: 100; background: var(--color-bg-secondary); border: 1px solid var(--color-border); border-radius: 4px; margin-top: 2px; max-height: 150px; overflow-y: auto; box-shadow: 0 4px 12px rgba(0,0,0,0.4);">
                                ${detectedPorts.map(p => html`
                                    <div key=${p.port}
                                        onClick=${() => { onEditPort(p.port); setShowPortDropdown(false); document.activeElement?.blur(); }}
                                        style="padding: 6px 8px; cursor: pointer; font-family: monospace; font-size: 0.85em; border-bottom: 1px solid var(--color-border);"
                                        onMouseEnter=${(e) => e.target.style.background = 'var(--hover-bg)'}
                                        onMouseLeave=${(e) => e.target.style.background = 'transparent'}>
                                        <div style="color: var(--color-text-primary);">${p.port}</div>
                                        ${p.description && html`<div style="font-size: 0.8em; color: var(--color-text-muted);">${p.description}</div>`}
                                    </div>
                                `)}
                            </div>
                        `}
                        ${showPortDropdown && detectedPorts.length === 0 && html`
                            <div style="position: absolute; top: 100%; left: 0; right: 0; z-index: 100; background: var(--color-bg-secondary); border: 1px solid var(--color-border); border-radius: 4px; margin-top: 2px; padding: 8px; font-size: 0.8em; color: var(--color-text-muted); text-align: center;">
                                No ports detected — type manually
                            </div>
                        `}
                    </div>
                </label>

                <!-- Baudrate -->
                <label style="display: flex; align-items: center; gap: 4px; font-size: 0.85em; color: var(--color-text-secondary);">
                    Baudrate
                    <select value=${editBaudrate} onChange=${(e) => onEditBaudrate(Number(e.target.value))}
                        style="padding: 4px 6px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-bg-secondary); color: var(--color-text-primary); font-family: monospace; font-size: 0.85em;"
                        disabled=${!connInfo?.serial_port}>
                        ${[9600, 19200, 38400, 57600, 115200, 230400, 460800, 500000].map(
                            (b) => html`<option key=${b} value=${b} style="background: var(--color-bg-secondary); color: var(--color-text-primary);">${b}</option>`
                        )}
                    </select>
                </label>

                <!-- Motor ID -->
                <label style="display: flex; align-items: center; gap: 4px; font-size: 0.85em; color: var(--color-text-secondary);">
                    ID
                    <input type="number" min="1" max="32" step="1" value=${editMotorId}
                        onChange=${(e) => onEditMotorId(Math.max(1, Math.min(32, Number(e.target.value))))}
                        class="motor-number-input"
                        disabled=${!connInfo?.serial_port} />
                </label>

                <!-- Transport selector + badge (near connection controls) -->
                <select
                    class="pid-select"
                    value=${transport}
                    onChange=${(e) => onTransportChange(e.target.value)}
                    style="max-width: 90px; padding: 3px 4px; font-size: 0.82em;"
                >
                    <option value="auto">Auto</option>
                    <option value="rs485">RS485</option>
                    <option value="ros2">ROS2</option>
                </select>
                <span class=${`pid-status-badge ${
                    transportInfo.active === 'rs485' ? 'status-active' :
                    transportInfo.active === 'ros2' ? 'status-active' : 'status-inactive'
                }`} style="font-size: 0.75em;">
                    ${transportInfo.active || 'none'}
                </span>

                <!-- Apply changes button (only if motor_id or baud changed) -->
                ${hasChanges && html`
                    <button class="btn btn-primary" onClick=${onUpdateConnection}
                        style="padding: 4px 10px; font-size: 0.8em;">
                        Apply
                    </button>
                `}

                <!-- Connect / Disconnect -->
                ${connected
                    ? html`<button class="btn btn-danger" onClick=${onDisconnect}
                        style="padding: 4px 14px; font-size: 0.85em; font-weight: 600;">
                        DISCONNECT</button>`
                    : html`<button class="btn btn-success" onClick=${onConnect}
                        style="padding: 4px 14px; font-size: 0.85em; font-weight: 600;"
                        disabled=${!connInfo?.serial_port}>
                        CONNECT</button>`
                }

                <!-- Connection status indicator -->
                <span title=${
                    connected
                        ? (connInfo?.verified ? 'Motor responding on bus (verified via product_info)' : 'Serial port open but motor not yet verified — click ↻ to verify')
                        : 'Serial port not connected'
                } style="font-size: 0.8em; padding: 2px 8px; border-radius: 4px; font-weight: 600; ${
                    connected && connInfo?.verified
                        ? 'background: color-mix(in srgb, var(--color-success) 13%, transparent); color: var(--color-success); border: 1px solid color-mix(in srgb, var(--color-success) 27%, transparent);'
                        : connected
                            ? 'background: color-mix(in srgb, var(--color-warning) 13%, transparent); color: var(--color-warning); border: 1px solid color-mix(in srgb, var(--color-warning) 27%, transparent);'
                            : 'background: color-mix(in srgb, var(--color-danger) 13%, transparent); color: var(--color-danger); border: 1px solid color-mix(in srgb, var(--color-danger) 27%, transparent);'
                }">
                    ${connected ? (connInfo?.verified ? 'Connected' : 'Connected (unverified)') : 'Disconnected'}
                </span>

                <!-- Divider -->
                <span style="width:1px; height:20px; background:var(--color-border);"></span>

                <!-- Motor Off / Motor On / Motor Reboot -->
                <button class="btn" onClick=${motorOff} disabled=${!selectedMotor || disconnected}
                    style="background:var(--color-danger); color:white; font-weight:600; padding:4px 10px; border:none; border-radius:4px; font-size:0.82em;">
                    Motor Off</button>
                <button class="btn" onClick=${motorOn} disabled=${!selectedMotor || disconnected}
                    style="background:var(--color-success); color:white; font-weight:600; padding:4px 10px; border:none; border-radius:4px; font-size:0.82em;">
                    Motor On</button>
                <button class="btn" onClick=${async () => {
                    if (!selectedMotor || disconnected) return;
                    if (!window.confirm("Reboot motor " + selectedMotor.motor_id + "? This will briefly power cycle.")) return;
                    try {
                        await api("/api/motor/" + selectedMotor.motor_id + "/lifecycle", "POST", { action: 3 });
                        showToast("Rebooting...", "success");
                    } catch { showToast("Reboot failed", "error"); }
                }} disabled=${!selectedMotor || disconnected}
                    style="background:var(--color-warning); color:#000; font-weight:600; padding:4px 10px; border:none; border-radius:4px; font-size:0.82em;">
                    Motor Reboot</button>

                <!-- Comm Error counter (right-aligned) -->
                <span style="display:flex; align-items:center; gap:8px; margin-left:auto;">
                    <button onClick=${onRefresh} disabled=${refreshing}
                        title="Refresh connection, transport, and motor list"
                        style="background:none; border:1px solid var(--color-border); border-radius:4px; padding:3px 7px; cursor:pointer; color:var(--color-text-secondary); font-size:0.85em; display:flex; align-items:center; gap:4px; ${refreshing ? 'opacity:0.5;' : ''}">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="${refreshing ? 'animation:spin 1s linear infinite;' : ''}"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
                    </button>
                    <span style="font-size:0.8em; color:var(--color-text-secondary);">
                        Comm Error : ${commErrors}
                    </span>
                </span>
            </div>

        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: SafetyBar
// ---------------------------------------------------------------------------

function SafetyBar({
    eStopActive,
    oscillationWarning,
    sessionStatus,
    limitOverride,
    onLimitOverrideChange,
    nodeStatus,
    nodeMessage,
    autonomousMode,
}) {
    return html`
        <div class="pid-safety-bar card">
            <span class=${`pid-estop-status ${eStopActive ? "estop-active" : "estop-clear"}`}>
                ${eStopActive ? "E-STOP ACTIVE" : "E-Stop: Clear"}
            </span>
            ${oscillationWarning &&
            html`<span class="pid-warning">Oscillation Warning</span>`}
            <span class="pid-session-info">${sessionStatus || "No active session"}</span>
            <label class="pid-override-toggle">
                <input
                    type="checkbox"
                    checked=${limitOverride}
                    onChange=${(e) => onLimitOverrideChange(e.target.checked)}
                />
                ${" "}Override Limits
            </label>
        </div>
        ${!nodeStatus &&
        html`
            <div class="pid-node-banner" style="display:flex;">
                <span class="warning-icon">\u26A0</span>
                <span>${nodeMessage || "Motor control nodes not detected"}</span>
            </div>
        `}
        ${autonomousMode &&
        html`
            <div class="pid-autonomous-banner" style="display:flex;">
                <span class="warning-icon">\u26A0</span>
                <span>Arm is in autonomous mode - tuning not recommended</span>
            </div>
        `}
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: GainSlider
// ---------------------------------------------------------------------------

function GainSlider({
    gainDef,
    value,
    lastReadValue,
    gainLimits,
    limitOverride,
    stepSize,
    disabled,
    onChange,
}) {
    const { key, label, loop, param } = gainDef;
    const limits = gainLimits?.[loop]?.[param];
    const min = limits?.min ?? 0;
    const max = limits?.max ?? 1000;

    const changed = lastReadValue != null && lastReadValue !== value;

    // Color based on limit proximity
    const range = max - min;
    const pct = range > 0 ? (value - min) / range : 0;
    let borderColor = getChartColor("--gain-normal");
    if (pct >= 0.95 || pct <= 0.05) borderColor = getChartColor("--gain-danger");
    else if (pct >= 0.85 || pct <= 0.15) borderColor = getChartColor("--gain-warning");

    const onRangeInput = useCallback(
        (e) => {
            const v = Number(e.target.value);
            onChange(key, v);
        },
        [key, onChange],
    );

    const onNumChange = useCallback(
        (e) => {
            const v = clampGain(key, Number(e.target.value), gainLimits, limitOverride);
            onChange(key, v);
        },
        [key, gainLimits, limitOverride, onChange],
    );

    return html`
        <div class="pid-slider-group" style=${{ borderLeftColor: borderColor }}>
            <label>
                <span class="pid-slider-name">${label}</span>
            </label>
            <div class="pid-slider-row">
                <input
                    type="range"
                    min=${min}
                    max=${max}
                    step="1"
                    value=${value}
                    disabled=${disabled}
                    onInput=${onRangeInput}
                />
                <input
                    type="number"
                    class=${`pid-slider-value ${changed ? "changed" : ""}`}
                    min=${min}
                    max=${max}
                    step=${stepSize}
                    value=${value}
                    disabled=${disabled}
                    onChange=${onNumChange}
                />
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: PIDPanel
// ---------------------------------------------------------------------------

function PIDPanel({
    gains,
    lastReadGains,
    gainLimits,
    limitOverride,
    disabled,
    onGainChange,
    onApplyRam,
    onSaveRom,
    onRevert,
    stepSize,
    onStepSizeChange,
}) {
    const gainsChanged = useMemo(() => {
        if (!lastReadGains || !gains) return false;
        return GAIN_KEYS.some((g) => lastReadGains[g.key] !== gains[g.key]);
    }, [gains, lastReadGains]);

    return html`
        <div class="pid-gain-panel card">
            <h3>PID Gains</h3>
            <div class="pid-step-size">
                Step:
                <select
                    class="pid-select-small"
                    value=${stepSize}
                    onChange=${(e) => onStepSizeChange(Number(e.target.value))}
                >
                    <option value="1">1</option>
                    <option value="5">5</option>
                    <option value="10">10</option>
                </select>
            </div>
            <div class="pid-sliders">
                ${GAIN_KEYS.map(
                    (g) => html`
                        <${GainSlider}
                            key=${g.key}
                            gainDef=${g}
                            value=${gains?.[g.key] ?? 0}
                            lastReadValue=${lastReadGains?.[g.key]}
                            gainLimits=${gainLimits}
                            limitOverride=${limitOverride}
                            stepSize=${stepSize}
                            disabled=${disabled}
                            onChange=${onGainChange}
                        />
                    `,
                )}
            </div>
            <div class="pid-gain-actions">
                <button class="btn btn-primary" disabled=${disabled} onClick=${onApplyRam}>
                    Apply to RAM
                </button>
                <button class="btn btn-warning" disabled=${disabled} onClick=${onSaveRom}>
                    Save to ROM
                </button>
                <button
                    class="btn btn-secondary"
                    disabled=${disabled || !gainsChanged}
                    onClick=${onRevert}
                >
                    Revert
                </button>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: StepTestPanel
// ---------------------------------------------------------------------------

function StepTestPanel({
    disabled,
    stepSize,
    stepDuration,
    onStepSizeChange,
    onDurationChange,
    onRunStepTest,
    running,
    progressPct,
    progressText,
}) {
    return html`
        <div class="pid-step-panel card">
            <h3>Step Response Test</h3>
            <div class="pid-step-config">
                <label>
                    Step Size (deg):
                    <input
                        type="number"
                        class="pid-input"
                        value=${stepSize}
                        min="1"
                        max="90"
                        onInput=${(e) => onStepSizeChange(Number(e.target.value))}
                    />
                </label>
                <label>
                    Duration (s):
                    <input
                        type="number"
                        class="pid-input"
                        value=${stepDuration}
                        min="1"
                        max="30"
                        step="0.5"
                        onInput=${(e) => onDurationChange(Number(e.target.value))}
                    />
                </label>
            </div>
            <button
                class="btn btn-primary"
                disabled=${disabled || running}
                onClick=${onRunStepTest}
            >
                Run Step Test
            </button>
            ${running &&
            html`
                <div class="pid-progress">
                    <div class="pid-progress-bar">
                        <div class="pid-progress-fill" style=${{ width: `${progressPct}%` }}></div>
                    </div>
                    <span>${progressText || "0%"}</span>
                </div>
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: AutoTunePanel
// ---------------------------------------------------------------------------

function AutoTunePanel({
    disabled,
    selectedRule,
    onRuleChange,
    onAutoSuggest,
    onCompareRules,
    suggestedGains,
    allRuleSuggestions,
    currentGains,
    onApplySuggestion,
}) {
    const rules = allRuleSuggestions ? Object.keys(allRuleSuggestions) : [];

    return html`
        <div class="pid-autotune-panel card">
            <h3>Auto-Suggest (Z-N)</h3>
            <div class="pid-autotune-controls">
                <select
                    class="pid-select"
                    value=${selectedRule}
                    onChange=${(e) => onRuleChange(e.target.value)}
                >
                    <option value="classic_pid">Classic PID</option>
                    <option value="pi">PI</option>
                    <option value="p_only">P-only</option>
                    <option value="pessen">Pessen</option>
                    <option value="no_overshoot">No Overshoot</option>
                    <option value="some_overshoot">Some Overshoot</option>
                </select>
                <button class="btn btn-secondary" disabled=${disabled} onClick=${onAutoSuggest}>
                    Auto-Suggest Gains
                </button>
                <button class="btn btn-secondary" disabled=${disabled} onClick=${onCompareRules}>
                    Compare Rules
                </button>
            </div>
            ${suggestedGains &&
            html`
                <div style="display:block;">
                    <table>
                        <thead>
                            <tr>
                                <th>Parameter</th>
                                <th>Current</th>
                                <th>Suggested</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${GAIN_KEYS.map((g) => {
                                const cur = currentGains?.[g.key] ?? "--";
                                const sug = suggestedGains[g.key] ?? "--";
                                const diff =
                                    sug !== "--" && cur !== "--" ? sug - cur : 0;
                                const arrow =
                                    diff > 0 ? "\u2191" : diff < 0 ? "\u2193" : "";
                                return html`
                                    <tr>
                                        <td>${g.label}</td>
                                        <td>${cur}</td>
                                        <td>${sug} ${arrow}</td>
                                    </tr>
                                `;
                            })}
                        </tbody>
                    </table>
                    <button
                        class="btn btn-primary"
                        style="margin-top:8px;"
                        onClick=${onApplySuggestion}
                    >
                        Apply Suggestion
                    </button>
                </div>
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: RuleComparisonTable
// ---------------------------------------------------------------------------

function RuleComparisonTable({ allRuleSuggestions, selectedRule, onRuleSelect }) {
    if (!allRuleSuggestions) return null;
    const rules = Object.keys(allRuleSuggestions);
    if (rules.length === 0) return null;

    return html`
        <div class="pid-rule-comparison card">
            <h3>Tuning Rule Comparison</h3>
            <div>
                <table>
                    <thead>
                        <tr>
                            <th>Rule</th>
                            ${GAIN_KEYS.map((g) => html`<th key=${g.key}>${g.label}</th>`)}
                        </tr>
                    </thead>
                    <tbody>
                        ${rules.map((rule) => {
                            const gains = allRuleSuggestions[rule];
                            return html`
                                <tr
                                    key=${rule}
                                    class=${rule === selectedRule ? "selected" : ""}
                                    onClick=${() => onRuleSelect(rule)}
                                    style="cursor:pointer;"
                                >
                                    <td>${RULE_DISPLAY_NAMES[rule] || rule}</td>
                                    ${GAIN_KEYS.map(
                                        (g) =>
                                            html`<td key=${g.key}>
                                                ${gains?.[g.key] != null ? gains[g.key] : "--"}
                                            </td>`,
                                    )}
                                </tr>
                            `;
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: ProfilePanel
// ---------------------------------------------------------------------------

function ProfilePanel({
    disabled,
    profiles,
    selectedProfile,
    onProfileSelect,
    onLoad,
    onSave,
}) {
    return html`
        <div class="pid-profile-panel card">
            <h3>Gain Profiles</h3>
            <div class="pid-profile-controls">
                <select
                    class="pid-select"
                    value=${selectedProfile}
                    onChange=${(e) => onProfileSelect(e.target.value)}
                >
                    <option value="">Select profile...</option>
                    ${profiles.map(
                        (p) => html`
                            <option key=${p.name} value=${p.name} title=${p.description || ""}>
                                ${p.name}
                            </option>
                        `,
                    )}
                </select>
                <button class="btn btn-secondary" disabled=${disabled} onClick=${onLoad}>
                    Load
                </button>
                <button class="btn btn-secondary" disabled=${disabled} onClick=${onSave}>
                    Save As...
                </button>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: WizardPanel
// ---------------------------------------------------------------------------

function WizardPanel({ disabled, wizardStep, wizardLocks, onNext, onToggleLock, onStart, onFinish }) {
    const loopOrder = ["current", "speed", "angle"];
    const loopLabels = ["Current Loop", "Speed Loop", "Angle Loop"];

    const btnLabel =
        wizardStep === 0
            ? "Start Guided Tuning"
            : wizardStep >= 3
              ? "Finish"
              : "Next Step";

    const onBtnClick = useCallback(() => {
        if (wizardStep === 0) onStart();
        else if (wizardStep >= 3) onFinish();
        else onNext();
    }, [wizardStep, onStart, onFinish, onNext]);

    return html`
        <div class="pid-wizard-panel card">
            <h3>Guided Tuning</h3>
            <div class="pid-wizard-steps">
                ${loopOrder.map((loop, idx) => {
                    const stepNum = idx + 1;
                    let cls = "pid-wizard-step";
                    if (stepNum === wizardStep) cls += " active";
                    if (wizardLocks[loop]) cls += " complete";
                    return html`
                        <div key=${loop} class=${cls} onClick=${() => onToggleLock(loop)}>
                            <span class="pid-wizard-indicator">${stepNum}</span>
                            ${" "}${loopLabels[idx]}
                            ${wizardLocks[loop] &&
                            html`<span class="pid-wizard-lock">\uD83D\uDD12</span>`}
                        </div>
                    `;
                })}
            </div>
            <button class="btn btn-secondary" disabled=${disabled} onClick=${onBtnClick}>
                ${btnLabel}
            </button>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: MetricsPanel
// ---------------------------------------------------------------------------

function MetricsPanel({ metrics }) {
    const items = [
        { id: "rise_time", label: "Rise Time" },
        { id: "settling_time", label: "Settling Time" },
        { id: "overshoot_percent", label: "Overshoot" },
        { id: "steady_state_error", label: "SS Error" },
        { id: "iae", label: "IAE" },
        { id: "ise", label: "ISE" },
        { id: "itse", label: "ITSE" },
    ];

    return html`
        <div class="pid-metrics-panel card">
            <h3>Performance Metrics</h3>
            <div class="pid-metrics-grid">
                ${items.map(
                    (item) => html`
                        <div
                            key=${item.id}
                            class=${`pid-metric ${metricClass(item.id, metrics?.[item.id])}`}
                        >
                            <span class="label">${item.label}</span>
                            <span class="value">${metricFmt(item.id, metrics?.[item.id])}</span>
                        </div>
                    `,
                )}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: SessionLog
// ---------------------------------------------------------------------------

function SessionLog({ log, onExport }) {
    return html`
        <div class="pid-session-log card">
            <h3>Session Log</h3>
            <div class="pid-log-entries">
                ${log.length === 0
                    ? html`<p class="pid-log-empty">No events yet</p>`
                    : log.map(
                          (e, i) => html`
                              <div
                                  key=${i}
                                  class=${`pid-log-entry ${
                                      {
                                          error: "pid-log-error",
                                          warn: "pid-log-warn",
                                          success: "pid-log-success",
                                          info: "",
                                      }[e.level] || ""
                                  }`}
                              >
                                  <span class="pid-log-time">
                                      ${new Date(e.time).toLocaleTimeString()}
                                  </span>
                                  <span class="pid-log-message">${e.message}</span>
                              </div>
                          `,
                      )}
            </div>
            <button
                class="btn btn-small"
                disabled=${log.length === 0}
                onClick=${onExport}
            >
                Export Log (JSON)
            </button>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: CommandsPanel
// ---------------------------------------------------------------------------

function CommandsPanel({
    selectedMotor,
    eStopActive,
    lastMotorState,
    showToast,
    addLog,
    disconnected,
    onLogEntry,
    onMotorStateChange,
}) {
    const [mode, setMode] = useState(0);
    const [cmdValue, setCmdValue] = useState(0);
    const [direction, setDirection] = useState(0);
    const [maxSpeed, setMaxSpeed] = useState(0);
    const [sending, setSending] = useState(false);

    const { dialog, confirm } = useConfirmDialog();

    const range = CMD_RANGES[mode] || CMD_RANGES[0];
    const steps = CMD_STEP_SIZES[mode] || [50, 500];

    const motorState = (lastMotorState?.motor_state || "unknown").toUpperCase();

    // Validation
    let validationMsg = "";
    let sendDisabled = false;
    if (disconnected) {
        validationMsg = "Connection lost \u2014 commands blocked";
        sendDisabled = true;
    } else if (!selectedMotor) {
        validationMsg = "Select a motor first";
        sendDisabled = true;
    } else if (eStopActive) {
        validationMsg = "E-Stop is active \u2014 commands blocked";
        sendDisabled = true;
    } else {
        if (isNaN(cmdValue) || cmdValue < range.value[0] || cmdValue > range.value[1]) {
            validationMsg = `Value must be ${range.value[0]} to ${range.value[1]}`;
            sendDisabled = true;
        }
        if (range.max_speed) {
            if (!isNaN(maxSpeed) && (maxSpeed < range.max_speed[0] || maxSpeed > range.max_speed[1])) {
                validationMsg +=
                    (validationMsg ? "; " : "") +
                    `Max speed must be ${range.max_speed[0]} to ${range.max_speed[1]}`;
                sendDisabled = true;
            }
        }
    }

    const running = motorState === "RUNNING";
    const motorSelected = !!selectedMotor;

    const sendCommand = useCallback(async () => {
        if (!selectedMotor) return;
        setSending(true);
        const body = {
            mode: mode,
            value: cmdValue,
            max_speed: maxSpeed,
            direction,
        };
        const data = await api(
            `/api/motor/${selectedMotor.motor_id}/command`,
            "POST",
            body,
        );
        const entry = {
            time: new Date().toLocaleTimeString(),
            action: MODE_NAMES[mode] || `Mode ${mode}`,
            detail: `value=${cmdValue}`,
            success: data?.success || false,
            info: data?.success
                ? `${data.temperature}\u00b0C | ${(data.torque_current || 0).toFixed(2)}A | ${data.speed}dps`
                : "",
            error: data?.error_message || "",
        };
        if (onLogEntry) onLogEntry(entry);
        if (!data) {
            showToast("Command request failed", "error");
        } else if (data.success) {
            showToast("Command sent", "success");
        } else {
            showToast(data.error_message || "Command failed", "error");
        }
        setSending(false);
    }, [selectedMotor, mode, cmdValue, maxSpeed, direction, showToast, onLogEntry]);

    const lifecycleAction = useCallback(
        async (action) => {
            if (!selectedMotor) return;
            const names = ["Motor ON", "Motor OFF", "STOP", "Reboot"];
            const name = names[action] || `Action ${action}`;

            if (eStopActive && (action === 0 || action === 3)) {
                showToast("Blocked during E-Stop", "error");
                return;
            }
            if (action === 3) {
                const ok = await confirm({
                    title: "Reboot Motor",
                    message: `Reboot motor ${selectedMotor.motor_id}? This will briefly power cycle.`,
                    dangerous: true,
                    confirmText: "Reboot",
                });
                if (!ok) return;
            }
            const data = await api(
                `/api/motor/${selectedMotor.motor_id}/lifecycle`,
                "POST",
                { action },
            );
            if (!data) {
                showToast(`${name}: request failed`, "error");
            } else if (data.success) {
                showToast(`${name}: success`, "success");
                // Update motor state immediately for button enable/disable
                if (onMotorStateChange) {
                    const stateNames = { 0: "RUNNING", 1: "OFF", 2: "STOPPED" };
                    const newState = stateNames[action];
                    if (newState) onMotorStateChange(newState);
                }
            } else {
                showToast(data.error_message || `${name} failed`, "error");
            }
        },
        [selectedMotor, eStopActive, showToast, confirm, onMotorStateChange],
    );

    const adjustValue = useCallback(
        (step) => {
            const newVal = Math.max(
                range.value[0],
                Math.min(range.value[1], cmdValue + step),
            );
            setCmdValue(newVal);
        },
        [cmdValue, range],
    );

    const motorRestore = useCallback(async () => {
        if (!selectedMotor) return;
        try {
            await api(`/api/motor/${selectedMotor.motor_id}/restore`, "POST");
            showToast("Motor restored", "success");
        } catch (e) {
            showToast("Motor restore failed", "error");
        }
    }, [selectedMotor, showToast]);

    // Reset value when mode changes
    useEffect(() => {
        setCmdValue(0);
        setMaxSpeed(0);
        setDirection(0);
    }, [mode]);

    // Which fields are active per mode (matching LK Motor Tool behavior)
    const isTorqueMode = mode === 0;
    const isSpeedMode = mode === 1;
    const isAngleMode = mode >= 2;
    const hasMaxSpeed = !!range.max_speed; // modes 3,5,7
    const hasDirection = !!range.direction; // modes 4,5

    return html`
        <div class="commands-layout">
            ${dialog}

            <div class="command-panel card">
                <h3>Motor Commands</h3>
                <div class="command-mode-select">
                    <label>Control Mode:</label>
                    <select
                        class="pid-select"
                        value=${mode}
                        onChange=${(e) => setMode(parseInt(e.target.value))}
                    >
                        ${MODE_NAMES.map(
                            (name, i) => html`<option key=${i} value=${i}>${name}</option>`,
                        )}
                    </select>
                </div>

                <div class="command-fields-lk">
                    <!-- Torque Current: enabled only in Torque mode -->
                    <div class=${`command-field-lk${isTorqueMode ? "" : " field-disabled"}`}>
                        <label>Torque Current</label>
                        <div class="field-input-row">
                            <input
                                type="number"
                                class=${`pid-input${isTorqueMode && sendDisabled && selectedMotor && !eStopActive ? " input-error" : ""}`}
                                min=${-2000}
                                max=${2000}
                                value=${isTorqueMode ? cmdValue : 0}
                                disabled=${!isTorqueMode}
                                onInput=${(e) => setCmdValue(parseFloat(e.target.value) || 0)}
                            />
                            <span class="field-unit">mA</span>
                        </div>
                        ${isTorqueMode && html`<span class="range-hint">-2000 to 2000</span>`}
                    </div>

                    <!-- Speed: enabled in Speed mode, also used as Max Speed for angle+speed modes -->
                    <div class=${`command-field-lk${isSpeedMode || hasMaxSpeed ? "" : " field-disabled"}`}>
                        <label>${isSpeedMode ? "Speed" : hasMaxSpeed ? "Max Speed" : "Speed"}</label>
                        <div class="field-input-row">
                            <input
                                type="number"
                                class="pid-input"
                                min=${isSpeedMode ? -90000 : 0}
                                max=${90000}
                                value=${isSpeedMode ? cmdValue : maxSpeed}
                                disabled=${!isSpeedMode && !hasMaxSpeed}
                                onInput=${(e) => {
                                    const v = parseFloat(e.target.value) || 0;
                                    if (isSpeedMode) setCmdValue(v);
                                    else setMaxSpeed(v);
                                }}
                                placeholder=${hasMaxSpeed && !isSpeedMode ? "0 = no limit" : ""}
                            />
                            <span class="field-unit">dps</span>
                        </div>
                        ${isSpeedMode && html`<span class="range-hint">-90000 to 90000</span>`}
                        ${hasMaxSpeed && !isSpeedMode && html`<span class="range-hint">0 to 90000</span>`}
                    </div>

                    <!-- Angle: enabled in all angle modes (2-7) -->
                    <div class=${`command-field-lk${isAngleMode ? "" : " field-disabled"}`}>
                        <label>Angle</label>
                        <div class="field-input-row">
                            <input
                                type="number"
                                class=${`pid-input${isAngleMode && sendDisabled && selectedMotor && !eStopActive ? " input-error" : ""}`}
                                min=${range.value[0]}
                                max=${range.value[1]}
                                value=${isAngleMode ? cmdValue : 0}
                                disabled=${!isAngleMode}
                                onInput=${(e) => setCmdValue(parseFloat(e.target.value) || 0)}
                            />
                            <span class="field-unit">deg</span>
                        </div>
                        ${isAngleMode && html`<span class="range-hint">${range.value[0]} to ${range.value[1]}</span>`}
                        ${hasDirection && html`
                            <div class="rev-checkbox-row">
                                <input type="checkbox" id="rev-check"
                                    checked=${direction === 1}
                                    onChange=${(e) => setDirection(e.target.checked ? 1 : 0)} />
                                <label for="rev-check">Rev</label>
                            </div>
                        `}
                    </div>
                </div>

                <div class="command-step-buttons">
                    ${steps.map(
                        (s) => html`
                            <button
                                key=${"p" + s}
                                class="step-btn"
                                onClick=${() => adjustValue(s)}
                            >
                                +${s}
                            </button>
                            <button
                                key=${"m" + s}
                                class="step-btn"
                                onClick=${() => adjustValue(-s)}
                            >
                                -${s}
                            </button>
                        `,
                    )}
                    <button
                        class=${`btn btn-primary${disconnected ? " locked-control" : ""}`}
                        disabled=${sendDisabled || sending || disconnected}
                        title=${disconnected ? "Unavailable \u2014 connection lost" : ""}
                        onClick=${sendCommand}
                    >
                        Send
                    </button>
                </div>

                ${validationMsg && html`<span class="validation-message">${validationMsg}</span>`}

                <div class="motor-stop-restore-row">
                    <button
                        class=${`btn btn-warning${disconnected ? " locked-control" : ""}`}
                        disabled=${!motorSelected || !running || disconnected}
                        title=${disconnected ? "Unavailable \u2014 connection lost" : ""}
                        onClick=${() => lifecycleAction(2)}
                    >
                        Motor Stop
                    </button>
                    <button
                        class=${`btn btn-secondary${disconnected ? " locked-control" : ""}`}
                        disabled=${!motorSelected || disconnected}
                        title=${disconnected ? "Unavailable \u2014 connection lost" : ""}
                        onClick=${motorRestore}
                    >
                        Motor Restore
                    </button>
                </div>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Helper: check if a value is the "N/A (RS485)" sentinel from backend
// ---------------------------------------------------------------------------
const isNA = (v) => typeof v === "string" && v.startsWith("N/A");

// ---------------------------------------------------------------------------
// Sub-component: BasicSettingPanel
// ---------------------------------------------------------------------------

function BasicSettingPanel({ selectedMotor, showToast, disconnected, readAllTrigger, fullConfig }) {
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(false);

    const readConfig = useCallback(async () => {
        if (!selectedMotor) return;
        setLoading(true);
        try {
            const resp = await api(`/api/motor/${selectedMotor.motor_id}/ext_config`);
            setConfig(resp);
        } catch (e) {
            showToast("Failed to read config", "error");
        }
        setLoading(false);
    }, [selectedMotor, showToast]);

    // Trigger read when readAllTrigger changes (from "Read Setting" button)
    useEffect(() => {
        if (readAllTrigger > 0) readConfig();
    }, [readAllTrigger]);

    const bs = config?.basic_setting || {};
    // CMD 0x14 basic_setting supplement (brake_resistor_voltage, current_ramp)
    const fc_bs = fullConfig?.basic_setting || {};
    // CMD 0x14 limits_setting supplement
    const fc_ls = fullConfig?.limits_setting || {};

    // Brake resistor voltage: prefer 0x14, fallback to 0x16
    const brakeVoltage = fc_bs.brake_resistor_voltage != null
        ? fc_bs.brake_resistor_voltage
        : (isNA(bs.brake_resistor_voltage) ? bs.brake_resistor_voltage : bs.brake_resistor_voltage);

    return html`
        <div style="margin-bottom:12px;">
            <div class="setting-section-header">
                <h3>Basic Setting</h3>
                <button class="btn btn-sm" onClick=${readConfig} disabled=${!selectedMotor || loading}>
                    ${loading ? "Reading..." : "Read"}
                </button>
            </div>
            <div class="setting-grid" style="grid-template-columns:auto 1fr; font-size:0.9em;">
                <label class="motor-setting-label">Driver ID</label>
                <input type="number" value=${bs.driver_id ?? ""} disabled
                    class="setting-input-readonly" style="width:100px;" />

                <label class="motor-setting-label">Bus Type</label>
                <select disabled class="setting-input-readonly" style="width:100px;">
                    <option>${bs.bus_type ?? "N/A"}</option>
                </select>

                <label class="motor-setting-label">RS485 Baudrate</label>
                <select disabled class="setting-input-readonly" style="width:100px;">
                    <option>${bs.rs485_baudrate ?? "N/A"}</option>
                </select>

                <label class="motor-setting-label">CAN Baudrate</label>
                <select disabled class="setting-input-readonly" style="width:100px;">
                    <option>${bs.can_baudrate ?? "N/A"}</option>
                </select>

                <label class="motor-setting-label">Broadcast Mode</label>
                <select disabled class="setting-input-readonly" style="width:100px;">
                    <option>${isNA(bs.broadcast_mode) ? bs.broadcast_mode : bs.broadcast_mode != null ? (bs.broadcast_mode ? "ON" : "OFF") : "--"}</option>
                </select>

                <label class="motor-setting-label">Spin Direction</label>
                <select disabled class="setting-input-readonly" style="width:100px;">
                    <option>${isNA(bs.spin_direction) ? bs.spin_direction : bs.spin_direction != null ? (bs.spin_direction ? "Reverse" : "Normal") : "--"}</option>
                </select>

                <label class="motor-setting-label">Brake Resistor Control</label>
                <select disabled class="setting-input-readonly" style="width:100px;">
                    <option>${isNA(bs.brake_resistor_control) ? bs.brake_resistor_control : bs.brake_resistor_control != null ? (bs.brake_resistor_control ? "Enable" : "Disable") : "--"}</option>
                </select>

                <label class="motor-setting-label">Brake Resistor Voltage</label>
                <input type="text" value=${brakeVoltage ?? ""} disabled placeholder="--"
                    class="setting-input-readonly" style="width:100px;" />
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: ProtectionSettingPanel
// ---------------------------------------------------------------------------

function ProtectionSettingPanel({ selectedMotor, showToast, disconnected, readAllTrigger, fullConfig }) {
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(false);

    const readConfig = useCallback(async () => {
        if (!selectedMotor) return;
        setLoading(true);
        try {
            const resp = await api(`/api/motor/${selectedMotor.motor_id}/ext_config`);
            setConfig(resp);
        } catch (e) {
            showToast("Failed to read protection config", "error");
        }
        setLoading(false);
    }, [selectedMotor, showToast]);

    // Trigger read when readAllTrigger changes (from "Read Setting" button)
    useEffect(() => {
        if (readAllTrigger > 0) readConfig();
    }, [readAllTrigger]);

    const ps_ext = config?.protection_setting || {};
    // CMD 0x14 protection data (preferred source for RS485)
    const ps14 = fullConfig?.protection_setting || {};

    // Helper: prefer 0x14 value, fallback to ext_config value
    const pref = (key14, keyExt) => {
        const v14 = ps14[key14];
        if (v14 != null) return v14;
        const vExt = ps_ext[keyExt || key14];
        return vExt;
    };

    // Format enable value from CMD 0x14 (string) or ext_config string
    const fmtEnable = (key14, keyExt) => {
        const v14 = ps14[key14];
        if (v14 != null) {
            // CMD 0x14 now returns strings from _decode_enable_byte:
            // "Disable", "Enable (recoverable)", "Enable (not recoverable)"
            if (v14 === "Disable") return "disable";
            if (v14 === "Enable (recoverable)") return "enable_recoverable";
            if (v14 === "Enable (not recoverable)") return "enable_not_recoverable";
            // Unknown or unexpected — pass through for enableValue() to handle
            return v14;
        }
        return ps_ext[keyExt || key14];
    };

    // Every protection field has BOTH a numeric threshold AND an enable dropdown,
    // matching the LK Motor Tool V2.36 layout exactly.
    // Special cases: Over Current Time has numeric only, Short Circuit has dropdown only.
    const protFields = [
        { label: "Protect Motor Temperature", threshold: pref("motor_temp_limit", "motor_temp_threshold"), enable: fmtEnable("motor_temp_enable") },
        { label: "Protect Driver Temperature", threshold: pref("driver_temp_limit", "driver_temp_threshold"), enable: fmtEnable("driver_temp_enable") },
        { label: "Protect Under Voltage", threshold: pref("under_voltage", "under_voltage_threshold"), enable: fmtEnable("under_voltage_enable") },
        { label: "Protect Over Voltage", threshold: pref("over_voltage", "over_voltage_threshold"), enable: fmtEnable("over_voltage_enable") },
        { label: "Protect Over Current", threshold: pref("over_current", "over_current_threshold"), enable: fmtEnable("over_current_enable") },
        { label: "Protect Over Current Time", threshold: pref("over_current_time"), enable: null, numericOnly: true },
        { label: "Protect Short Circuit", threshold: null, enable: fmtEnable("short_circuit_enable"), dropdownOnly: true },
        { label: "Protect Stall", threshold: pref("stall_threshold"), enable: fmtEnable("stall_enable") },
        { label: "Protect Lost Input Time", threshold: pref("lost_input_time"), enable: fmtEnable("lost_input_enable") },
    ];

    const enableOptions = [
        { value: "", label: "--" },
        { value: "disable", label: "Disable" },
        { value: "enable_recoverable", label: "Enable (recoverable)" },
        { value: "enable_not_recoverable", label: "Enable (not recoverable)" },
    ];

    const enableValue = (val) => {
        if (val == null || isNA(val)) return "";
        if (val === "disable" || val === false) return "disable";
        if (val === "enable_recoverable") return "enable_recoverable";
        if (val === "enable_not_recoverable" || val === "enable") return "enable_not_recoverable";
        return "";
    };

    return html`
        <div class="protection-settings-card" style="margin-bottom:12px;">
            <div class="setting-section-header">
                <h3>Protection Setting</h3>
            </div>
            <div class="setting-grid" style="grid-template-columns:1fr auto auto; gap:4px 8px; font-size:0.85em;">
                ${protFields.map(f => html`
                    <label class="motor-setting-label" key=${f.label}>${f.label}</label>
                    ${f.dropdownOnly ? html`
                        <div></div>
                    ` : isNA(f.threshold) ? html`
                        <input type="text" value="N/A (RS485)" disabled
                            class="setting-input-readonly" style="width:80px; text-align:right; font-size:0.8em; color:var(--color-text-secondary);" />
                    ` : html`
                        <input type="number" value=${f.threshold ?? ""} disabled placeholder="--"
                            class="setting-input-readonly" style="width:80px; text-align:right;" />
                    `}
                    ${f.numericOnly ? html`
                        <div></div>
                    ` : isNA(f.enable) ? html`
                        <select disabled class="setting-input-readonly" style="min-width:160px; color:var(--color-text-secondary);">
                            <option>N/A (RS485)</option>
                        </select>
                    ` : html`
                        <select disabled class="setting-input-readonly" style="min-width:160px;">
                            ${enableOptions.map(opt => html`
                                <option value=${opt.value} selected=${enableValue(f.enable) === opt.value}>${opt.label}</option>
                            `)}
                        </select>
                    `}
                `)}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: EncoderPanel
// ---------------------------------------------------------------------------

function EncoderPanel({ selectedMotor, lastMotorState, showToast, disconnected, readAllTrigger, extConfig }) {
    const [encoderData, setEncoderData] = useState(null);
    const [readTime, setReadTime] = useState(0);
    const [zeroValue, setZeroValue] = useState("");
    const [comparison, setComparison] = useState(null);
    const [reading, setReading] = useState(false);
    const lastRomWriteRef = useRef(0);
    // CMD 0x16 extended config data (encoder_setting section)
    const [extEncoderData, setExtEncoderData] = useState(null);

    // Merge extConfig from parent (read_all_settings) into extEncoderData
    // whenever extConfig changes — always merge so derived fields like
    // motor_poles and reduction_ratio are never lost
    useEffect(() => {
        if (extConfig?.encoder_setting) {
            setExtEncoderData(prev => ({
                ...prev,
                ...extConfig.encoder_setting,
            }));
        }
    }, [extConfig]);

    const { dialog, confirm, doubleConfirm } = useConfirmDialog();

    const readEncoder = useCallback(async () => {
        if (!selectedMotor) return;
        setReading(true);
        // Read both 0x90 encoder and 0x16 ext_config in parallel
        const [data, extResp] = await Promise.all([
            api(`/api/motor/${selectedMotor.motor_id}/encoder`),
            api(`/api/motor/${selectedMotor.motor_id}/ext_config`).catch(() => null),
        ]);
        if (data?.success) {
            setEncoderData(data);
            setReadTime(Date.now());
        } else {
            showToast(data?.error_message || "Encoder read failed", "error");
        }
        if (extResp?.encoder_setting) {
            // Merge with existing data to preserve motor_poles and
            // reduction_ratio injected by read_all_settings
            setExtEncoderData(prev => ({
                ...prev,
                ...extResp.encoder_setting,
                // Keep derived fields from read_all_settings if the
                // individual ext_config endpoint didn't provide them
                motor_poles: extResp.encoder_setting.motor_poles ?? prev?.motor_poles,
                reduction_ratio: extResp.encoder_setting.reduction_ratio ?? prev?.reduction_ratio,
                encoder_type: extResp.encoder_setting.encoder_type ?? prev?.encoder_type,
                motor_phase_sequence: extResp.encoder_setting.motor_phase_sequence ?? prev?.motor_phase_sequence,
            }));
        }
        setReading(false);
    }, [selectedMotor, showToast]);

    // Auto-read when readAllTrigger fires
    useEffect(() => {
        if (readAllTrigger > 0) readEncoder();
    }, [readAllTrigger, readEncoder]);

    const useCurrentValue = useCallback(() => {
        if (encoderData?.raw_value != null) {
            setZeroValue(String(encoderData.raw_value));
        }
    }, [encoderData]);

    const writeZeroRam = useCallback(async () => {
        if (!selectedMotor) return;
        const val = parseInt(zeroValue);
        if (isNaN(val) || val < 0 || val > 65535) {
            showToast("Invalid encoder value (0-65535)", "error");
            return;
        }
        // Stale check
        if (Date.now() - readTime > 10000) {
            showToast("Encoder data stale \u2014 auto-refreshing...", "warning");
            await readEncoder();
        }
        const ok = await confirm({
            title: "Write Encoder Zero",
            message: `Write encoder zero offset to RAM?\nValue: ${val}\nMotor ID: ${selectedMotor.motor_id}`,
            dangerous: true,
            confirmText: "Write",
        });
        if (!ok) return;
        const data = await api(
            `/api/motor/${selectedMotor.motor_id}/encoder/zero`,
            "POST",
            { mode: 0, encoder_value: val, confirmation_token: "CONFIRM_ENCODER_ZERO" },
        );
        if (data?.success) {
            showToast("Encoder zero written to RAM", "success");
            setComparison({ before: data.before, after: data.after });
            await readEncoder();
        } else {
            showToast(data?.error_message || "Write failed", "error");
        }
    }, [selectedMotor, zeroValue, readTime, readEncoder, showToast, confirm]);

    const saveZeroRom = useCallback(async () => {
        if (!selectedMotor) return;
        const speed = Math.abs(lastMotorState?.speed_dps || 0);
        if (speed > 1) {
            showToast("Motor is in motion \u2014 stop motor before saving zero to ROM", "error");
            return;
        }
        if (lastRomWriteRef.current && Date.now() - lastRomWriteRef.current < 30000) {
            const ok = await confirm({
                title: "Recent ROM Write",
                message: "You wrote to ROM less than 30 seconds ago. Are you sure you want to write again?",
                dangerous: true,
            });
            if (!ok) return;
        }
        if (Date.now() - readTime > 10000) {
            showToast("Encoder data stale \u2014 auto-refreshing...", "warning");
            await readEncoder();
        }
        const ok = await doubleConfirm({
            title: "\u26A0 Save Current Position as Zero to ROM",
            message:
                `Motor ID: ${selectedMotor.motor_id}\n` +
                `Joint: ${selectedMotor.joint_name || "unknown"}\n` +
                `Current raw encoder: ${encoderData?.raw_value || "unknown"}\n\n` +
                `This permanently sets the current position as the zero reference.`,
            dangerous: true,
            confirmText: "Save to ROM",
            confirmWord: "CONFIRM",
        });
        if (!ok) return;
        const data = await api(
            `/api/motor/${selectedMotor.motor_id}/encoder/zero`,
            "POST",
            { mode: 1, encoder_value: 0, confirmation_token: "CONFIRM_ENCODER_ZERO" },
        );
        if (data?.success) {
            lastRomWriteRef.current = Date.now();
            showToast("Zero position saved to ROM", "success");
            setComparison({ before: data.before, after: data.after });
            await readEncoder();
        } else {
            showToast(data?.error_message || "ROM write failed", "error");
        }
    }, [selectedMotor, lastMotorState, readTime, readEncoder, encoderData, showToast, confirm, doubleConfirm]);

    const writeRamValid =
        !!selectedMotor &&
        !isNaN(parseInt(zeroValue)) &&
        parseInt(zeroValue) >= 0 &&
        parseInt(zeroValue) <= 65535;

    const [advancedOpen, setAdvancedOpen] = useState(false);

    const labelStyle = "font-size:0.85em; color:var(--color-text-secondary);";
    const spinnerInputStyle = "padding:3px 6px; background:var(--color-bg-primary); color:var(--color-text-primary); border:1px solid var(--color-border); border-radius:3px 0 0 3px; width:80px; text-align:right; border-right:none; -moz-appearance:textfield;";
    const spinnerBtnStyle = "display:flex; align-items:center; justify-content:center; width:20px; border:1px solid var(--color-border); background:var(--color-bg-tertiary); color:var(--color-text-secondary); cursor:pointer; font-size:0.7em; padding:0; line-height:1;";
    const readOnlyField = "padding:3px 6px; background:var(--color-bg-tertiary); color:var(--color-text-secondary); border:1px solid var(--color-border); border-radius:3px; width:110px; text-align:left;";
    const inlineBtnStyle = "padding:2px 12px; font-size:0.82em; min-width:50px;";
    const offsetValue = encoderData?.offset != null ? String(encoderData.offset) : "--";

    // Reusable number spinner matching LK Motor Tool style (input + up/down buttons)
    const NumberSpinner = ({ value, step, disabled, title }) => html`
        <div style="display:inline-flex; align-items:stretch; height:26px;" title=${title || ""}>
            <input type="text" value=${value} disabled=${disabled} style=${spinnerInputStyle} />
            <div style="display:flex; flex-direction:column; width:20px;">
                <button disabled=${disabled} style=${spinnerBtnStyle + "border-bottom:none; border-radius:0 3px 0 0; height:13px;"}
                    title=${disabled ? title : `Increment by ${step}`}
                >\u25B2</button>
                <button disabled=${disabled} style=${spinnerBtnStyle + "border-radius:0 0 3px 0; height:13px;"}
                    title=${disabled ? title : `Decrement by ${step}`}
                >\u25BC</button>
            </div>
        </div>
    `;

    return html`
        <div class="encoder-layout" style="display:flex; flex-direction:column; gap:16px;">
            ${dialog}

            <!-- Main 2-panel row (matches LK Motor Tool V2.36 Encoder tab) -->
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px;">

                <!-- Left Panel: Motor / Encoder Setting -->
                <div class="card" style="padding:12px;">
                    <h3 style="margin:0 0 10px 0; color:var(--color-accent-primary); font-style:italic; font-size:1.05em;">Motor / Encoder Setting</h3>
                    <div style="display:grid; grid-template-columns:auto 1fr; gap:8px 16px; align-items:center;">
                        <span style=${labelStyle}>Motor Poles</span>
                        <${NumberSpinner} value=${extEncoderData?.motor_poles ?? "--"} step=${1} disabled=${true}
                            title=${extEncoderData?.motor_poles ? "Derived from motor model" : "Not available"} />

                        <span style=${labelStyle}>Encoder Type</span>
                        <input type="text" value=${extEncoderData?.encoder_type ?? "--"} disabled style=${readOnlyField}
                            title=${extEncoderData?.encoder_type ? `Raw: ${extEncoderData.encoder_type_raw ?? "?"}` : "Not available"} />

                        <span style=${labelStyle}>Encoder Position</span>
                        <input type="text" value=${extEncoderData?.encoder_position != null ? (extEncoderData.encoder_position === 1 ? "Reverse" : "Normal") : "--"} disabled style=${readOnlyField}
                            title=${extEncoderData?.encoder_position != null ? `Raw: ${extEncoderData.encoder_position}` : "Not available"} />

                        <span style=${labelStyle}>Motor Phase Sequence</span>
                        <input type="text" value=${extEncoderData?.motor_phase_sequence ?? "--"} disabled style=${readOnlyField}
                            title=${extEncoderData?.motor_phase_sequence ? `Raw: ${extEncoderData.motor_phase_seq_raw ?? "?"}` : "Not available"} />

                        <span style=${labelStyle}>Motor/Encoder Offset</span>
                        <input type="text" value=${extEncoderData?.encoder_offset != null ? String(extEncoderData.encoder_offset) : offsetValue} disabled style=${readOnlyField} />

                        <span style=${labelStyle}>Motor/Encoder Align Ratio</span>
                        <input type="text" value=${extEncoderData?.align_ratio != null ? String(extEncoderData.align_ratio) : "--"} disabled style=${readOnlyField} />

                        <span style=${labelStyle}>Motor/Encoder Align Voltage</span>
                        <div style="display:flex; align-items:center; gap:6px;">
                            <${NumberSpinner} value=${extEncoderData?.align_voltage != null ? extEncoderData.align_voltage : "--"} step=${0.01} disabled=${true} />
                            <button class="btn btn-sm btn-secondary" disabled style=${inlineBtnStyle}
                                title="Align command not available over RS485"
                            >Align</button>
                        </div>

                        <span style=${labelStyle}>Motor Zero Position (Rom)</span>
                        <div style="display:flex; align-items:center; gap:6px;">
                            <input type="text" value=${encoderData?.raw_value != null ? String(encoderData.raw_value) : "--"} disabled style=${readOnlyField} />
                            <button
                                class=${`btn btn-sm btn-danger${disconnected ? " locked-control" : ""}`}
                                disabled=${!selectedMotor || disconnected}
                                title=${disconnected ? "Unavailable \u2014 connection lost" : "Save current position as zero (ROM)"}
                                onClick=${saveZeroRom}
                                style=${inlineBtnStyle}
                            >Set</button>
                        </div>
                    </div>
                </div>

                <!-- Right Panel: Reducer / Encoder Setting + Save/Read buttons -->
                <div style="display:flex; flex-direction:column; gap:16px;">
                    <div class="card" style="padding:12px;">
                        <h3 style="margin:0 0 10px 0; color:var(--color-accent-primary); font-style:italic; font-size:1.05em;">Reducer / Encoder Setting</h3>
                        <div style="display:grid; grid-template-columns:auto 1fr; gap:8px 16px; align-items:center;">
                            <span style=${labelStyle}>Reduction Ratio</span>
                            <${NumberSpinner} value=${extEncoderData?.reduction_ratio ?? "--"} step=${1} disabled=${true}
                                title=${extEncoderData?.reduction_ratio ? "Derived from motor model" : "Not available"} />

                            <span style=${labelStyle}>Reducer/Encoder Align Value</span>
                            <div style="display:flex; align-items:center; gap:6px;">
                                <input type="text" value=${extEncoderData?.reducer_align_value != null ? String(extEncoderData.reducer_align_value) : "--"} disabled style=${readOnlyField} />
                                <button class="btn btn-sm btn-secondary" disabled style=${inlineBtnStyle}
                                    title="Clear command not available over RS485"
                                >Clear</button>
                            </div>

                            <span style=${labelStyle}>Reducer Zero Position</span>
                            <div style="display:flex; align-items:center; gap:6px;">
                                <input type="text" value=${extEncoderData?.reducer_zero_position != null ? String(extEncoderData.reducer_zero_position) : "--"} disabled style=${readOnlyField} />
                                <button class="btn btn-sm btn-secondary" disabled style=${inlineBtnStyle}
                                    title="Set command not available over RS485"
                                >Set</button>
                            </div>
                        </div>
                    </div>

                    <!-- Save / Read buttons at bottom-right (matches LK Motor Tool) -->
                    <div style="display:flex; flex-direction:column; gap:8px; align-items:flex-end; margin-top:auto;">
                        <button
                            class=${`btn btn-primary${disconnected ? " locked-control" : ""}`}
                            disabled=${!selectedMotor || disconnected}
                            title=${disconnected ? "Unavailable \u2014 connection lost" : "Save encoder config to ROM"}
                            onClick=${saveZeroRom}
                            style="width:140px; padding:8px 16px; font-size:0.95em;"
                        >Save</button>
                        <button
                            class=${`btn btn-secondary${disconnected ? " locked-control" : ""}`}
                            disabled=${!selectedMotor || reading || disconnected}
                            title=${disconnected ? "Unavailable \u2014 connection lost" : "Read encoder data (0x90)"}
                            onClick=${readEncoder}
                            style="width:140px; padding:8px 16px; font-size:0.95em;"
                        >Read</button>
                    </div>
                </div>
            </div>

            <!-- Advanced: Write Zero (RAM) + Comparison (collapsible) -->
            <div class="card" style="padding:0; overflow:hidden;">
                <button
                    class="btn btn-sm"
                    onClick=${() => setAdvancedOpen(!advancedOpen)}
                    style="width:100%; padding:8px 12px; text-align:left; background:var(--color-bg-secondary); border:none; border-bottom:${advancedOpen ? "1px solid var(--color-border)" : "none"}; cursor:pointer; display:flex; align-items:center; gap:6px; font-size:0.85em; color:var(--color-text-secondary);"
                >
                    <span style="font-size:0.7em;">${advancedOpen ? "\u25BC" : "\u25B6"}</span>
                    Advanced: Write Encoder Zero (RAM)
                </button>
                ${advancedOpen && html`
                    <div style="padding:12px; display:flex; flex-direction:column; gap:12px;">
                        <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                            <div style="display:flex; align-items:center; gap:4px;">
                                <span style="font-size:0.85em; font-weight:600;">Write Zero</span>
                                <span class="ram-badge">RAM</span>
                            </div>
                            <input
                                type="number"
                                class="pid-input"
                                min="0"
                                max="65535"
                                placeholder="0-65535"
                                value=${zeroValue}
                                onInput=${(e) => setZeroValue(e.target.value)}
                                style="width:120px;"
                            />
                            <button class="btn btn-sm btn-secondary" onClick=${useCurrentValue}
                                style="font-size:0.8em;">Use Current</button>
                            <button
                                class=${`btn btn-sm btn-warning${disconnected ? " locked-control" : ""}`}
                                disabled=${!writeRamValid || disconnected}
                                title=${disconnected ? "Unavailable \u2014 connection lost" : "Write encoder zero offset to RAM"}
                                onClick=${writeZeroRam}
                                style="font-size:0.8em; padding:5px 12px;"
                            >Write Zero</button>
                        </div>

                        ${comparison && html`
                            <div class="encoder-comparison" style="margin-top:0;">
                                <h4 style="margin:0 0 6px 0; font-size:0.9em;">Encoder Zero Result</h4>
                                <div class="encoder-compare-grid">
                                    <div class="compare-col">
                                        <h4>Before</h4>
                                        <div>Raw: ${comparison.before?.raw_value}</div>
                                        <div>Offset: ${comparison.before?.offset}</div>
                                        <div>Original: ${comparison.before?.original_value}</div>
                                    </div>
                                    <div class="compare-arrow">\u2192</div>
                                    <div class="compare-col">
                                        <h4>After</h4>
                                        <div>Raw: ${comparison.after?.raw_value}</div>
                                        <div>Offset: ${comparison.after?.offset}</div>
                                        <div>Original: ${comparison.after?.original_value}</div>
                                    </div>
                                </div>
                            </div>
                        `}
                    </div>
                `}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: SettingPIDPanel (compact PID for Setting tab — matches LK Tool)
// ---------------------------------------------------------------------------

function SettingPIDPanel({ selectedMotor, showToast, disconnected, readAllTrigger, fullConfig }) {
    const loops = ["angle", "speed", "current"];
    const [pid, setPid] = useState({ angle: { kp: "", ki: "" }, speed: { kp: "", ki: "" }, current: { kp: "", ki: "" } });
    const [loading, setLoading] = useState(false);

    const readAll = useCallback(async () => {
        if (!selectedMotor) return;
        setLoading(true);

        // Try CMD 0x14 fullConfig first (preferred for RS485)
        const p14 = fullConfig?.pid_setting;
        if (p14 && p14.angle_kp != null) {
            setPid({
                angle: { kp: p14.angle_kp ?? "", ki: p14.angle_ki ?? "" },
                speed: { kp: p14.speed_kp ?? "", ki: p14.speed_ki ?? "" },
                current: { kp: p14.current_kp ?? "", ki: p14.current_ki ?? "" },
            });
            setLoading(false);
            return;
        }

        // Fallback: try individual PID read endpoint
        try {
            const resp = await api(`/api/pid/read/${selectedMotor.motor_id}`);
            if (resp?.gains && Object.keys(resp.gains).length > 0) {
                const g = resp.gains;
                setPid({
                    angle: { kp: g.angle_kp ?? "", ki: g.angle_ki ?? "" },
                    speed: { kp: g.speed_kp ?? "", ki: g.speed_ki ?? "" },
                    current: { kp: g.current_kp ?? "", ki: g.current_ki ?? "" },
                });
            } else {
                // PID read not supported over RS485 — show N/A
                const na = { kp: "N/A", ki: "N/A" };
                setPid({ angle: na, speed: na, current: na });
            }
        } catch (e) {
            // PID read may not be supported on all firmware/transports
            const na = { kp: "N/A", ki: "N/A" };
            setPid({ angle: na, speed: na, current: na });
        }
        setLoading(false);
    }, [selectedMotor, showToast, fullConfig]);

    // Trigger read when readAllTrigger changes (from "Read Setting" button)
    useEffect(() => {
        if (readAllTrigger > 0) readAll();
    }, [readAllTrigger]);

    const writeLoop = useCallback(async (loop) => {
        if (!selectedMotor) return;
        const vals = pid[loop];
        try {
            const body = {};
            body[loop + "_kp"] = parseInt(vals.kp) || 0;
            body[loop + "_ki"] = parseInt(vals.ki) || 0;
            const resp = await api(`/api/pid/write/${selectedMotor.motor_id}`, "POST", body);
            showToast(resp?.success ? `${loop} PID set (RAM)` : `Failed to set ${loop} PID`,
                resp?.success ? "success" : "error");
        } catch (e) {
            showToast(`Failed to set ${loop} PID`, "error");
        }
    }, [selectedMotor, showToast, pid]);

    const onChange = useCallback((loop, field, value) => {
        setPid(prev => ({
            ...prev,
            [loop]: { ...prev[loop], [field]: value },
        }));
    }, []);

    // Check if PID values are N/A (not readable over RS485)
    const pidIsNA = pid.angle.kp === "N/A";

    return html`
        <div style="margin-bottom:12px;">
            <div class="setting-section-header" style="margin-bottom:6px;">
                <h3>PID Setting</h3>
                ${pidIsNA ? html`<span style="font-size:0.75em; color:var(--color-text-secondary); margin-left:8px;">N/A — PID read unavailable</span>` : null}
            </div>
            <div class="setting-grid" style="grid-template-columns: auto auto auto auto; gap:4px 8px; font-size:0.85em; align-items:center;">
                <div></div>
                <span style="text-align:center; font-weight:600; color:var(--color-text-secondary);">Kp</span>
                <span style="text-align:center; font-weight:600; color:var(--color-text-secondary);">Ki</span>
                <div></div>
                ${loops.map(loop => {
                    const loopNA = pid[loop].kp === "N/A";
                    return html`
                    <label class="motor-setting-label" key=${loop} style="text-transform:capitalize;">${loop}</label>
                    <input type=${loopNA ? "text" : "number"} value=${pid[loop].kp}
                        onInput=${(e) => onChange(loop, "kp", e.target.value)}
                        class=${loopNA ? "setting-input-readonly" : "setting-input"} style="width:70px; text-align:right;${loopNA ? ' color:var(--color-text-secondary); font-size:0.8em;' : ''}"
                        disabled=${disconnected || loopNA} />
                    <input type=${loopNA ? "text" : "number"} value=${pid[loop].ki}
                        onInput=${(e) => onChange(loop, "ki", e.target.value)}
                        class=${loopNA ? "setting-input-readonly" : "setting-input"} style="width:70px; text-align:right;${loopNA ? ' color:var(--color-text-secondary); font-size:0.8em;' : ''}"
                        disabled=${disconnected || loopNA} />
                    <button class="btn btn-sm" onClick=${() => writeLoop(loop)}
                        disabled=${disconnected} style="font-size:0.78em; padding:3px 8px; white-space:nowrap;">SET RAM</button>
                `})}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: LimitsSettingPanel
// ---------------------------------------------------------------------------

function LimitsSettingPanel({ selectedMotor, showToast, disconnected, readAllTrigger, fullConfig }) {
    const [maxTorque, setMaxTorque] = useState("");
    const [maxSpeed, setMaxSpeed] = useState("");
    const [maxAngle, setMaxAngle] = useState("");
    const [speedRamp, setSpeedRamp] = useState("");
    const [currentRamp, setCurrentRamp] = useState("");
    const [loading, setLoading] = useState(false);

    const NA = "N/A";

    const readAll = useCallback(async () => {
        if (!selectedMotor) return;
        setLoading(true);
        let gotAny = false;

        // Try CMD 0x14 fullConfig first (preferred for RS485)
        const ls14 = fullConfig?.limits_setting;
        if (ls14 && ls14.max_torque_current != null) {
            setMaxTorque(String(ls14.max_torque_current));
            if (ls14.max_speed != null) setMaxSpeed(String(ls14.max_speed));
            if (ls14.max_angle != null) setMaxAngle(String(ls14.max_angle));
            if (ls14.speed_ramp != null) setSpeedRamp(String(ls14.speed_ramp));
            if (ls14.current_ramp != null) setCurrentRamp(String(ls14.current_ramp));
            setLoading(false);
            return;
        }

        // Fallback: try individual limit endpoints
        try {
            const [limitsResp, extResp] = await Promise.all([
                api(`/api/motor/${selectedMotor.motor_id}/limits`).catch(() => null),
                api(`/api/motor/${selectedMotor.motor_id}/extended_limits`).catch(() => null),
            ]);
            if (limitsResp?.success && limitsResp.max_torque_ratio != null) {
                setMaxTorque(String(limitsResp.max_torque_ratio));
                gotAny = true;
            }
            if (extResp && extResp._success !== false) {
                if (extResp.max_speed_dps != null) { setMaxSpeed(String(extResp.max_speed_dps)); gotAny = true; }
                if (extResp.max_angle_deg != null) { setMaxAngle(String(extResp.max_angle_deg)); gotAny = true; }
                if (extResp.speed_ramp != null) { setSpeedRamp(String(extResp.speed_ramp)); gotAny = true; }
                if (extResp.current_ramp != null) { setCurrentRamp(String(extResp.current_ramp)); gotAny = true; }
            }
        } catch (e) {
            // Limits commands not supported on this firmware over RS485
        }
        // If nothing was read, mark all fields as N/A
        if (!gotAny) {
            setMaxTorque(NA); setMaxSpeed(NA); setMaxAngle(NA);
            setSpeedRamp(NA); setCurrentRamp(NA);
        }
        setLoading(false);
    }, [selectedMotor, showToast, fullConfig]);

    // Trigger read when readAllTrigger changes (from "Read Setting" button)
    useEffect(() => {
        if (readAllTrigger > 0) readAll();
    }, [readAllTrigger]);

    const writeParam = useCallback(async (endpoint, value) => {
        if (!selectedMotor) return;
        try {
            const resp = await api(endpoint, "PUT", { value: parseFloat(value) });
            showToast(resp?.success ? "Set OK" : "Failed", resp?.success ? "success" : "error");
        } catch (e) {
            showToast("Failed", "error");
        }
    }, [selectedMotor, showToast]);

    const writeExt = useCallback(async (param, value, scale = 1) => {
        if (!selectedMotor) return;
        try {
            const resp = await api(
                `/api/motor/${selectedMotor.motor_id}/extended_limits/${param}`,
                "PUT",
                { value: parseFloat(value) * scale },
            );
            showToast(resp?.success ? `${param} set` : `Failed`, resp?.success ? "success" : "error");
        } catch (e) {
            showToast("Failed", "error");
        }
    }, [selectedMotor, showToast]);

    const limitsNA = maxTorque === NA;
    const naStyle = "width:120px; color:var(--color-text-secondary); font-size:0.85em;";

    return html`
        <div style="margin-bottom:12px;">
            <div class="setting-section-header">
                <h3>Limits Setting</h3>
                ${limitsNA ? html`<span style="font-size:0.75em; color:var(--color-text-secondary); margin-left:8px;">N/A — limits read unavailable</span>` : null}
            </div>
            <div class="setting-grid" style="grid-template-columns:auto auto auto; gap:6px 10px; font-size:0.9em;">
                <label class="motor-setting-label">Max Torque Current</label>
                <input type=${maxTorque === NA ? "text" : "number"} min="0" max="2000" value=${maxTorque}
                    onInput=${(e) => setMaxTorque(e.target.value)} disabled=${disconnected || maxTorque === NA}
                    class=${maxTorque === NA ? "setting-input-readonly" : "setting-input"} style=${maxTorque === NA ? naStyle : "width:120px;"} />
                <button class="btn btn-sm" disabled=${disconnected || !maxTorque || maxTorque === NA}
                    onClick=${() => writeParam(`/api/motor/${selectedMotor.motor_id}/limits/max_torque_current`, maxTorque)}>SET RAM</button>

                <label class="motor-setting-label">Max Speed</label>
                <input type=${maxSpeed === NA ? "text" : "number"} value=${maxSpeed}
                    onInput=${(e) => setMaxSpeed(e.target.value)} disabled=${disconnected || maxSpeed === NA}
                    class=${maxSpeed === NA ? "setting-input-readonly" : "setting-input"} style=${maxSpeed === NA ? naStyle : "width:120px;"} />
                <button class="btn btn-sm" disabled=${disconnected || !maxSpeed || maxSpeed === NA}
                    onClick=${() => writeExt("max_speed", maxSpeed, 100)}>SET RAM</button>

                <label class="motor-setting-label">Max Angle</label>
                <input type=${maxAngle === NA ? "text" : "number"} value=${maxAngle}
                    onInput=${(e) => setMaxAngle(e.target.value)} disabled=${disconnected || maxAngle === NA}
                    class=${maxAngle === NA ? "setting-input-readonly" : "setting-input"} style=${maxAngle === NA ? naStyle : "width:120px;"} />
                <button class="btn btn-sm" disabled=${disconnected || !maxAngle || maxAngle === NA}
                    onClick=${() => writeExt("max_angle", maxAngle, 100)}>SET RAM</button>

                <label class="motor-setting-label">Speed Ramp</label>
                <input type=${speedRamp === NA ? "text" : "number"} value=${speedRamp}
                    onInput=${(e) => setSpeedRamp(e.target.value)} disabled=${disconnected || speedRamp === NA}
                    class=${speedRamp === NA ? "setting-input-readonly" : "setting-input"} style=${speedRamp === NA ? naStyle : "width:120px;"} />
                <button class="btn btn-sm" disabled=${disconnected || !speedRamp || speedRamp === NA}
                    onClick=${() => writeExt("speed_ramp", speedRamp)}>SET RAM</button>

                <label class="motor-setting-label">Current Ramp</label>
                <input type=${currentRamp === NA ? "text" : "number"} value=${currentRamp}
                    onInput=${(e) => setCurrentRamp(e.target.value)} disabled=${disconnected || currentRamp === NA}
                    class=${currentRamp === NA ? "setting-input-readonly" : "setting-input"} style=${currentRamp === NA ? naStyle : "width:120px;"} />
                <button class="btn btn-sm" disabled=${disconnected || !currentRamp || currentRamp === NA}
                    onClick=${() => writeExt("current_ramp", currentRamp)}>SET RAM</button>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: ProductPanel
// ---------------------------------------------------------------------------

function ProductPanel({ selectedMotor, showToast, firmwareVersion, productInfo, readAllTrigger }) {
    const [info, setInfo] = useState(null);
    const [loading, setLoading] = useState(false);

    // Seed from productInfo passed by parent (from read_all_settings)
    useEffect(() => {
        if (productInfo) setInfo(productInfo);
    }, [productInfo]);

    const readInfo = useCallback(async () => {
        if (!selectedMotor) return;
        setLoading(true);
        try {
            const resp = await api(`/api/motor/${selectedMotor.motor_id}/product_info`);
            setInfo(resp);
        } catch (e) {
            showToast("Failed to read product info", "error");
        }
        setLoading(false);
    }, [selectedMotor, showToast]);

    // Auto-read when readAllTrigger fires
    useEffect(() => {
        if (readAllTrigger > 0) readInfo();
    }, [readAllTrigger, readInfo]);

    return html`
        <div class="product-panel">
            <div class="card" style="overflow: hidden;">
                <div class="setting-grid" style="grid-template-columns: 1fr 1fr; margin-bottom: 24px;">
                    <div class="product-field">
                        <span class="product-label">Motor :</span>
                        <span class="product-value">${info?.motor_name || "--"}</span>
                    </div>
                    <div class="product-field">
                        <span class="product-label">Motor version :</span>
                        <span class="product-value">${info?.motor_version || "--"}</span>
                    </div>
                    <div class="product-field">
                        <span class="product-label">Driver :</span>
                        <span class="product-value">${info?.driver_name || "--"}</span>
                    </div>
                    <div class="product-field">
                        <span class="product-label">Hardware version :</span>
                        <span class="product-value">${info?.hardware_version || "--"}</span>
                    </div>
                    <div class="product-field">
                        <span class="product-label">Firmware version :</span>
                        <span class="product-value">${info?.firmware_version || firmwareVersion?.firmware_build_hex || "--"}</span>
                    </div>
                    <div class="product-field">
                        <span class="product-label">Chip ID:</span>
                        <span class="product-value" style="font-family: monospace; color: var(--color-error);">
                            ${info?.motor_serial_id || "--"}
                        </span>
                    </div>
                </div>

                <div style="display: flex; justify-content: flex-end;">
                    <button class="btn" onClick=${readInfo} disabled=${!selectedMotor || loading}>
                        ${loading ? "Reading..." : "Read Info"}
                    </button>
                </div>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: ErrorFlagsPanel
// ---------------------------------------------------------------------------

function ErrorFlagsPanel({ errorFlags }) {
    const flags = [
        { key: "under_voltage", abbr: "UVP", name: "Under Voltage" },
        { key: "over_voltage", abbr: "OVP", name: "Over Voltage" },
        { key: "driver_over_temp", abbr: "DTP", name: "Driver Over Temp" },
        { key: "motor_over_temp", abbr: "MTP", name: "Motor Over Temp" },
        { key: "over_current", abbr: "OCP", name: "Over Current" },
        { key: "short_circuit", abbr: "SCP", name: "Short Circuit" },
        { key: "stall", abbr: "MSP", name: "Motor Stall" },
        { key: "lost_input_timeout", abbr: "LIP", name: "Lost Input" },
    ];
    return html`
        <div class="error-flags-vertical">
            ${flags.map(f => {
                const active = errorFlags?.[f.key] || false;
                return html`
                    <label key=${f.key} class=${`error-flag-item${active ? " error-flag-active" : ""}`}>
                        <input type="checkbox" checked=${active} disabled />
                        <span class="error-flag-abbr">${f.abbr}</span>
                        <span class="error-flag-name">${f.name}</span>
                    </label>
                `;
            })}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: TestStatePanel
// ---------------------------------------------------------------------------

function TestStatePanel({ selectedMotor, eStopActive, showToast, disconnected, onLogEntry }) {
    const [stateData, setStateData] = useState(null);
    const [multiAngle, setMultiAngle] = useState("--");
    const [singleAngle, setSingleAngle] = useState("--");

    const motorSelected = !!selectedMotor;

    const readDetailedState = useCallback(async () => {
        if (!selectedMotor) return;
        try {
            const resp = await api(`/api/motor/${selectedMotor.motor_id}/state_detailed`);
            setStateData(resp);
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Read State (All)", detail: "", success: true, info: "", error: "" });
        } catch (e) {
            showToast("Failed to read state", "error");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Read State (All)", detail: "", success: false, info: "", error: String(e) });
        }
    }, [selectedMotor, showToast, onLogEntry]);

    // Individual state readers — each reads only its own state and merges into stateData
    const readState = useCallback(async (stateNum) => {
        if (!selectedMotor) return;
        try {
            const resp = await api(`/api/motor/${selectedMotor.motor_id}/state/${stateNum}`);
            const key = `state${stateNum}`;
            if (resp[key]) {
                setStateData(prev => ({ ...prev, [key]: resp[key] }));
            }
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: `Read State ${stateNum}`, detail: "", success: true, info: "", error: "" });
        } catch (e) {
            showToast(`Failed to read state ${stateNum}`, "error");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: `Read State ${stateNum}`, detail: "", success: false, info: "", error: String(e) });
        }
    }, [selectedMotor, showToast, onLogEntry]);

    const brakeAction = useCallback(async (action) => {
        if (!selectedMotor) return;
        const label = action === 0 ? "Brake" : "Brake Release";
        try {
            await api(`/api/motor/${selectedMotor.motor_id}/brake`, "POST", { action });
            showToast(label + " OK", "success");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: label, detail: "", success: true, info: "", error: "" });
        } catch (e) {
            showToast("Brake command failed", "error");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: label, detail: "", success: false, info: "", error: String(e) });
        }
    }, [selectedMotor, showToast, onLogEntry]);

    const readMultiTurnAngle = useCallback(async () => {
        if (!selectedMotor) return;
        try {
            const resp = await api(`/api/motor/${selectedMotor.motor_id}/angle/multi_turn`);
            if (resp.multi_turn_deg != null) setMultiAngle(resp.multi_turn_deg.toFixed(2) + "\u00b0");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Read Multi Loop Angle", detail: resp.multi_turn_deg != null ? resp.multi_turn_deg.toFixed(2) + "\u00b0" : "", success: true, info: "", error: "" });
        } catch (e) {
            showToast("Failed to read multi-turn angle", "error");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Read Multi Loop Angle", detail: "", success: false, info: "", error: String(e) });
        }
    }, [selectedMotor, showToast, onLogEntry]);

    const readSingleTurnAngle = useCallback(async () => {
        if (!selectedMotor) return;
        try {
            const resp = await api(`/api/motor/${selectedMotor.motor_id}/angle/single_turn`);
            if (resp.single_turn_deg != null) setSingleAngle(resp.single_turn_deg.toFixed(2) + "\u00b0");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Read Single Loop Angle", detail: resp.single_turn_deg != null ? resp.single_turn_deg.toFixed(2) + "\u00b0" : "", success: true, info: "", error: "" });
        } catch (e) {
            showToast("Failed to read single-turn angle", "error");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Read Single Loop Angle", detail: "", success: false, info: "", error: String(e) });
        }
    }, [selectedMotor, showToast, onLogEntry]);

    const clearMultiTurn = useCallback(async () => {
        if (!selectedMotor) return;
        try {
            await api(`/api/motor/${selectedMotor.motor_id}/clear_multi_turn`, "POST");
            showToast("Multi-turn angle cleared", "success");
            readMultiTurnAngle();
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Clear Motor Loops", detail: "", success: true, info: "", error: "" });
        } catch (e) {
            showToast("Failed to clear multi-turn", "error");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Clear Motor Loops", detail: "", success: false, info: "", error: String(e) });
        }
    }, [selectedMotor, showToast, readMultiTurnAngle, onLogEntry]);

    const setZeroRam = useCallback(async () => {
        if (!selectedMotor) return;
        try {
            await api(`/api/motor/${selectedMotor.motor_id}/set_zero_ram`, "POST");
            showToast("Motor zero set (RAM)", "success");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Set Motor Zero (RAM)", detail: "", success: true, info: "", error: "" });
        } catch (e) {
            showToast("Failed to set zero", "error");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Set Motor Zero (RAM)", detail: "", success: false, info: "", error: String(e) });
        }
    }, [selectedMotor, showToast, onLogEntry]);

    const clearErrors = useCallback(async () => {
        if (!selectedMotor) return;
        try {
            await api("/api/motor/" + selectedMotor.motor_id + "/errors/clear", "POST");
            showToast("Errors cleared", "success");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Clear Error", detail: "", success: true, info: "", error: "" });
        } catch (e) {
            showToast("Failed to clear errors", "error");
            if (onLogEntry) onLogEntry({ time: new Date().toLocaleTimeString(), action: "Clear Error", detail: "", success: false, info: "", error: String(e) });
        }
    }, [selectedMotor, showToast, onLogEntry]);

    const s1 = stateData?.state1 || {};
    const s2 = stateData?.state2 || {};
    const s3 = stateData?.state3 || {};

    return html`
        <div style="display:flex; flex-direction:column; gap:8px;">
            <!-- State card: 3-column — values | buttons | error flags -->
            <div class="card" style="padding:12px;">
                <h3 style="margin:0 0 8px 0;">State</h3>
                <div class="state-error-inline">
                    <div class="test-state-grid">
                        <div class="test-state-row"><span class="test-state-label">Bus Voltage</span><span class="test-state-value">${s1.voltage_v != null ? s1.voltage_v.toFixed(1) + " V" : "--"}</span></div>
                        <div class="test-state-row"><span class="test-state-label">Bus Current</span><span class="test-state-value" title="Not available via RS485">--</span></div>
                        <div class="test-state-row"><span class="test-state-label">Motor Temp</span><span class="test-state-value">${s1.temperature_c != null ? s1.temperature_c + "\u00b0C" : "--"}</span></div>
                        <div class="test-state-row"><span class="test-state-label">Torque Current</span><span class="test-state-value">${s2.torque_current_a != null ? s2.torque_current_a.toFixed(3) + " A" : "--"}</span></div>
                        <div class="test-state-row"><span class="test-state-label">Speed</span><span class="test-state-value">${s2.speed_dps != null ? s2.speed_dps + " dps" : "--"}</span></div>
                        <div class="test-state-row"><span class="test-state-label">Encoder</span><span class="test-state-value">${s2.encoder_position != null ? s2.encoder_position : "--"}</span></div>
                        <div class="test-state-row"><span class="test-state-label">IA</span><span class="test-state-value">${s3.phase_current_a?.[0] != null ? s3.phase_current_a[0].toFixed(3) + " A" : "--"}</span></div>
                        <div class="test-state-row"><span class="test-state-label">IB</span><span class="test-state-value">${s3.phase_current_a?.[1] != null ? s3.phase_current_a[1].toFixed(3) + " A" : "--"}</span></div>
                        <div class="test-state-row"><span class="test-state-label">IC</span><span class="test-state-value">${s3.phase_current_a?.[2] != null ? s3.phase_current_a[2].toFixed(3) + " A" : "--"}</span></div>
                    </div>
                    <!-- Middle: state read + brake buttons -->
                    <div class="state-buttons-column">
                        <button class="btn btn-sm" onClick=${() => readState(1)} disabled=${disconnected}>Read State 1</button>
                        <button class="btn btn-sm" onClick=${() => readState(2)} disabled=${disconnected}>Read State 2</button>
                        <button class="btn btn-sm" onClick=${() => readState(3)} disabled=${disconnected}>Read State 3</button>
                        <button class="btn btn-sm" onClick=${clearErrors} disabled=${disconnected}>Clear Error</button>
                        <hr style="border:none; border-top:1px solid var(--border-color); margin:4px 0; width:100%;" />
                        <button class="btn btn-sm" onClick=${() => brakeAction(0)} disabled=${disconnected}>Brake</button>
                        <button class="btn btn-sm" onClick=${() => brakeAction(1)} disabled=${disconnected}>Brake Release</button>
                    </div>
                    <!-- Right: error flags -->
                    <div class="error-flags-column">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                            <span style="font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-muted);">Error Flags</span>
                        </div>
                        <${ErrorFlagsPanel} errorFlags=${s1.error_flags} />
                    </div>
                </div>
            </div>

            <!-- Angle & Motor card -->
            <div class="card" style="padding:12px;">
                <h3 style="margin:0 0 8px 0;">Angle & Motor</h3>
                <div class="angle-motor-grid">
                    <button class="btn btn-sm" style="white-space:nowrap;" onClick=${readMultiTurnAngle} disabled=${!motorSelected || disconnected}>Read Multi Loop Angle</button>
                    <span class="angle-value-display">${multiAngle}</span>
                    <button class="btn btn-sm" style="white-space:nowrap;" onClick=${clearMultiTurn} disabled=${!motorSelected || disconnected}>Clear Motor Loops</button>

                    <button class="btn btn-sm" style="white-space:nowrap;" onClick=${readSingleTurnAngle} disabled=${!motorSelected || disconnected}>Read Single Loop Angle</button>
                    <span class="angle-value-display">${singleAngle}</span>
                    <button class="btn btn-sm" style="white-space:nowrap;" onClick=${setZeroRam} disabled=${!motorSelected || disconnected}>Set Motor Zero (RAM)</button>
                </div>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: SerialMonitorPanel
// ---------------------------------------------------------------------------

function SerialMonitorPanel({ selectedMotor }) {
    const [frames, setFrames] = useState([]);
    const [autoScroll, setAutoScroll] = useState(true);
    const [paused, setPaused] = useState(false);
    const logRef = useRef(null);
    const wsRef = useRef(null);
    const lineCounterRef = useRef(0);
    const pausedRef = useRef(false);

    // Keep pausedRef in sync
    useEffect(() => { pausedRef.current = paused; }, [paused]);

    useEffect(() => {
        // Connect WebSocket for serial log
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${location.host}/api/motor/ws/serial_log`;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === "ping") return; // keepalive
            if (pausedRef.current) return; // discard frames while paused
            lineCounterRef.current += 1;
            const lineNum = lineCounterRef.current;
            setFrames((prev) => {
                const next = [...prev, { ...data, lineNum }];
                return next.length > 500 ? next.slice(-500) : next;
            });
        };

        ws.onerror = () => {};
        ws.onclose = () => {};

        return () => { ws.close(); };
    }, []);

    useEffect(() => {
        if (autoScroll && logRef.current) {
            logRef.current.scrollTop = logRef.current.scrollHeight;
        }
    }, [frames, autoScroll]);

    const clearLog = useCallback(async () => {
        setFrames([]);
        lineCounterRef.current = 0;
        try { await api("/api/motor/serial_log", "DELETE"); } catch {}
    }, []);

    return html`
        <div class="serial-monitor card" style="display:flex; flex-direction:column; height: 100%; min-width:0; overflow:hidden;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <h3 style="margin:0;">Serial Monitor</h3>
                <div style="display:flex; gap:8px; align-items:center;">
                    ${paused && html`<span style="font-size:11px; color:var(--color-warning); font-weight:600;">Paused</span>`}
                    <label style="font-size:12px;">
                        <input type="checkbox" checked=${autoScroll}
                            onChange=${(e) => setAutoScroll(e.target.checked)} />
                        Auto-scroll
                    </label>
                    <button class="btn btn-sm" onClick=${() => setPaused(p => !p)}
                        style=${paused ? "background:var(--color-warning); color:#000;" : ""}>
                        ${paused ? "Resume" : "Pause"}
                    </button>
                    <button class="btn btn-sm" onClick=${clearLog}>Clear Text</button>
                </div>
            </div>
            <div ref=${logRef} class="serial-log-area"
                style="flex:1; overflow-y:auto; overflow-x:auto; background:var(--color-bg-primary); color:var(--color-text-primary); font-family:monospace; font-size:11px; padding:8px; border-radius:4px; min-height:300px; max-height:500px;">
                ${frames.map((f, i) => html`
                    <div key=${i} style="color: ${f.dir === 'TX' ? 'var(--color-success)' : 'var(--color-warning)'}; white-space: nowrap;">
                        <span style="display:inline-block; width:5ch; text-align:right; color:var(--color-text-muted); margin-right:4px;">${String(f.lineNum).padStart(5)}</span>| ${f.dir}: ${f.hex}
                    </div>
                `)}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Sub-component: MotorChartsPanel
//
// Uses ChartComponent for proper Chart.js lifecycle.
// Chart data stored in refs to avoid re-render on every WS message.
// We trigger re-renders with a counter at 5Hz (every 200ms).
// ---------------------------------------------------------------------------

function MotorChartsPanel({
    liveChartData,
    stepChartData,
    chartTimeWindow,
    onTimeWindowChange,
    onCaptureSnapshot,
    onClearSnapshots,
    onToggleCurrentMode,
    onExportCsv,
    onExportData,
    onClearResults,
    hasStepData,
    snapshotCount,
    currentChartMode,
}) {
    const timeWindows = [10, 30, 60, 120];

    // Shared dark-theme chart options
    const darkScaleOpts = {
        ticks: { color: getMotorChartColors().text },
        grid: { color: getMotorChartColors().grid },
    };

    // Live chart options
    const liveOptions = useMemo(
        () => ({
            animation: false,
            plugins: { legend: { labels: { color: getMotorChartColors().text } } },
            scales: {
                x: darkScaleOpts,
                yPos: {
                    type: "linear",
                    position: "left",
                    title: { display: true, text: "Position (deg)", color: getMotorChartColors().text },
                    ...darkScaleOpts,
                },
                yVel: {
                    type: "linear",
                    position: "right",
                    title: { display: true, text: "Velocity (deg/s)", color: getMotorChartColors().text },
                    ticks: { color: getMotorChartColors().text },
                    grid: { drawOnChartArea: false },
                },
            },
        }),
        [],
    );

    // Step chart options factory
    const stepChartOptions = useCallback(
        (yTitle) => ({
            animation: false,
            plugins: { legend: { labels: { color: getMotorChartColors().text } } },
            scales: {
                x: {
                    title: { display: true, text: "Time (s)", color: getMotorChartColors().text },
                    ...darkScaleOpts,
                },
                y: {
                    title: { display: true, text: yTitle, color: getMotorChartColors().text },
                    ...darkScaleOpts,
                },
            },
        }),
        [],
    );

    const posOpts = useMemo(() => stepChartOptions("Position (deg)"), [stepChartOptions]);
    const errOpts = useMemo(() => stepChartOptions("Error (deg)"), [stepChartOptions]);
    const velOpts = useMemo(() => stepChartOptions("Velocity (deg/s)"), [stepChartOptions]);
    const curOpts = useMemo(() => stepChartOptions("Current (A)"), [stepChartOptions]);

    return html`
        <div class="motor-charts-panel">
            <div class="chart-controls-bar">
                <div class="chart-time-buttons">
                    ${timeWindows.map(
                        (tw) => html`
                            <button
                                key=${tw}
                                class=${`chart-time-btn ${tw === chartTimeWindow ? "active" : ""}`}
                                onClick=${() => onTimeWindowChange(tw)}
                            >
                                ${tw}s
                            </button>
                        `,
                    )}
                </div>
                <div class="chart-action-buttons">
                    <button class="btn btn-sm btn-secondary" onClick=${onCaptureSnapshot}>
                        Capture
                    </button>
                    <button
                        class="btn btn-sm btn-secondary"
                        disabled=${snapshotCount === 0}
                        onClick=${onClearSnapshots}
                    >
                        Clear Snaps
                    </button>
                    <button class="btn btn-sm btn-secondary" onClick=${onToggleCurrentMode}>
                        ${currentChartMode === "torque" ? "Phase" : "Torque"}
                    </button>
                    <button class="btn btn-sm btn-secondary" onClick=${onExportCsv}>
                        CSV
                    </button>
                </div>
            </div>

            <div class="pid-live-chart card">
                <h3>Live Motor Data</h3>
                <${ChartComponent}
                    type="line"
                    labels=${liveChartData.labels}
                    datasets=${liveChartData.datasets}
                    options=${liveOptions}
                    height="300px"
                />
            </div>

            <div class="pid-step-charts card">
                <h3>Step Response</h3>
                <div class="pid-step-charts-grid">
                    <${ChartComponent}
                        type="line"
                        labels=${stepChartData.position.labels}
                        datasets=${stepChartData.position.datasets}
                        options=${posOpts}
                        height="200px"
                    />
                    <${ChartComponent}
                        type="line"
                        labels=${stepChartData.error.labels}
                        datasets=${stepChartData.error.datasets}
                        options=${errOpts}
                        height="200px"
                    />
                    <${ChartComponent}
                        type="line"
                        labels=${stepChartData.velocity.labels}
                        datasets=${stepChartData.velocity.datasets}
                        options=${velOpts}
                        height="200px"
                    />
                    <${ChartComponent}
                        type="line"
                        labels=${stepChartData.current.labels}
                        datasets=${stepChartData.current.datasets}
                        options=${curOpts}
                        height="200px"
                    />
                </div>
                <div class="pid-chart-actions">
                    <button
                        class="btn btn-small"
                        disabled=${!hasStepData}
                        onClick=${onExportData}
                    >
                        Export Data (JSON)
                    </button>
                    <button class="btn btn-small" onClick=${onClearResults}>
                        Clear Results
                    </button>
                </div>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component: MotorConfigTab
// ---------------------------------------------------------------------------

function MotorConfigTab() {
    const { showToast } = useToast();
    const { dialog: mainDialog, confirm: mainConfirm } = useConfirmDialog();
    const { disconnected: wsDisconnected } = useContext(WebSocketContext);

    // --- Core state ---
    const [motors, setMotors] = useState([]);
    const [selectedMotor, setSelectedMotor] = useState(null);
    const [motorStatus, setMotorStatus] = useState("");
    const [nodesAvailable, setNodesAvailable] = useState(false);
    const [nodeMessage, setNodeMessage] = useState("");
    const [loading, setLoading] = useState(false);

    // --- Safety state ---
    const [eStopActive, setEStopActive] = useState(false);
    const [oscillationWarning, setOscillationWarning] = useState(false);
    const [autonomousMode, setAutonomousMode] = useState(false);
    const [limitOverride, setLimitOverride] = useState(false);

    // --- Transport state ---
    const [transport, setTransport] = useState('auto');
    const [transportInfo, setTransportInfo] = useState({ active: 'none', rs485_available: false, ros2_available: false });

    // --- Connection state ---
    const [connInfo, setConnInfo] = useState({ serial_port: null, baudrate: null, motor_id: 1, connected: false, verified: false });
    const [refreshing, setRefreshing] = useState(false);
    const [editMotorId, setEditMotorId] = useState(1);
    const [editBaudrate, setEditBaudrate] = useState(115200);
    const [editPort, setEditPort] = useState('');

    // --- PID state ---
    const [gains, setGains] = useState({});
    const [lastReadGains, setLastReadGains] = useState(null);
    const [gainLimits, setGainLimits] = useState(null);
    const [stepSize, setStepSize] = useState(5);

    // --- Step test state ---
    const [testStepSize, setTestStepSize] = useState(10);
    const [testDuration, setTestDuration] = useState(3);
    const [stepTestRunning, setStepTestRunning] = useState(false);
    const [stepTestProgress, setStepTestProgress] = useState(0);
    const [stepTestProgressText, setStepTestProgressText] = useState("");
    const stepTestResultsRef = useRef([]);

    // --- Auto-tune state ---
    const [selectedRule, setSelectedRule] = useState("classic_pid");
    const [suggestedGains, setSuggestedGains] = useState(null);
    const [allRuleSuggestions, setAllRuleSuggestions] = useState(null);
    const [showRuleComparison, setShowRuleComparison] = useState(false);

    // --- Profile state ---
    const [profiles, setProfiles] = useState([]);
    const [selectedProfile, setSelectedProfile] = useState("");

    // --- Wizard state ---
    const [wizardStep, setWizardStep] = useState(0);
    const [wizardLocks, setWizardLocks] = useState({
        current: false,
        speed: false,
        angle: false,
    });

    // --- Tab state ---
    const [activeTab, setActiveTab] = useState("setting");

    // --- Read-all trigger: increment to tell all Setting sub-panels to re-read ---
    const [readAllTrigger, setReadAllTrigger] = useState(0);

    // --- Full config from CMD 0x14 (shared across Setting panels) ---
    const [fullConfig, setFullConfig] = useState(null);

    // --- Extended config from CMD 0x16 (for EncoderPanel, BasicSettingPanel) ---
    const [extConfig, setExtConfig] = useState(null);

    // --- Firmware version from CMD 0x1F ---
    const [firmwareVersion, setFirmwareVersion] = useState(null);

    // --- Product info from CMD 0x12 (for ProductPanel auto-fill) ---
    const [productInfo, setProductInfo] = useState(null);

    // --- Session log ---
    const [sessionLog, setSessionLog] = useState([]);

    // --- Test tab activity log (persistent, copyable) ---
    const [testHistory, setTestHistory] = useState([]);

    const addTestLogEntry = useCallback((entry) => {
        setTestHistory((prev) => [entry, ...prev].slice(0, 100));
    }, []);

    // --- Chart state ---
    const [chartTimeWindow, setChartTimeWindow] = useState(30);
    const [currentChartMode, setCurrentChartMode] = useState("torque");
    const [snapshotCount, setSnapshotCount] = useState(0);

    // Live chart data managed in refs + update counter
    const liveLabelsRef = useRef([]);
    const liveDatasetsRef = useRef([
        {
            label: "Position (deg)",
            data: [],
            borderColor: getMotorChartColors().position,
            backgroundColor: "transparent",
            yAxisID: "yPos",
            pointRadius: 0,
            borderWidth: 1.5,
            tension: 0.2,
        },
        {
            label: "Velocity (deg/s)",
            data: [],
            borderColor: getMotorChartColors().velocity,
            backgroundColor: "transparent",
            yAxisID: "yVel",
            pointRadius: 0,
            borderWidth: 1.5,
            tension: 0.2,
        },
    ]);
    const snapshotDatasetsRef = useRef([]);
    const [liveChartTick, setLiveChartTick] = useState(0);

    // Step chart data
    const [stepChartData, setStepChartData] = useState({
        position: { labels: [], datasets: [
            { label: "Setpoint", data: [], borderColor: getMotorChartColors().setpoint, backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5, tension: 0.2 },
            { label: "Actual", data: [], borderColor: getMotorChartColors().position, backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5, tension: 0.2 },
        ] },
        error: { labels: [], datasets: [
            { label: "Error", data: [], borderColor: getMotorChartColors().error, backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5, tension: 0.2 },
        ] },
        velocity: { labels: [], datasets: [
            { label: "Velocity", data: [], borderColor: getMotorChartColors().velocity, backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5, tension: 0.2 },
        ] },
        current: { labels: [], datasets: [
            { label: "Current", data: [], borderColor: getMotorChartColors().current, backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5, tension: 0.2 },
        ] },
    });

    // --- Metrics ---
    const [metrics, setMetrics] = useState(null);

    // --- WebSocket refs ---
    const wsRef = useRef(null);
    const wsReconnectRef = useRef(null);
    const wsReconnectAttemptsRef = useRef(0);
    const motorStateBufferRef = useRef([]);
    const lastMotorStateRef = useRef({});
    const lastDataTimestampRef = useRef(Date.now());
    const maxLivePointsRef = useRef(MAX_LIVE_POINTS_DEFAULT);

    // --- Step test poll timer ---
    const stepTestPollRef = useRef(null);
    const activeStepTestIdRef = useRef(null);

    // --- Intervals ---
    const nodeCheckRef = useRef(null);
    const chartUpdateRef = useRef(null);

    // Track wsDisconnected in a ref for use inside mount-only event handlers
    const wsDisconnectedRef = useRef(wsDisconnected);
    useEffect(() => {
        wsDisconnectedRef.current = wsDisconnected;
    }, [wsDisconnected]);

    // Expose lastMotorState as state for sub-components that need reactive updates
    const [lastMotorState, setLastMotorState] = useState({});

    // Callback for child components to update motor_state after lifecycle actions
    const handleMotorStateChange = useCallback((newState) => {
        setLastMotorState((prev) => ({ ...prev, motor_state: newState }));
        lastMotorStateRef.current.motor_state = newState;
    }, []);

    // -----------------------------------------------------------------------
    // Logging helper
    // -----------------------------------------------------------------------
    const addLog = useCallback((level, message) => {
        setSessionLog((prev) => {
            const entry = { time: new Date().toISOString(), level, message };
            const next = [entry, ...prev];
            if (next.length > MAX_LOG_ENTRIES) next.pop();
            return next;
        });
    }, []);

    // -----------------------------------------------------------------------
    // Node availability check
    // -----------------------------------------------------------------------
    const checkNodes = useCallback(async () => {
        const maxAttempts = 5;
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                setLoading(true);
                const resp = await api("/api/pid/motors");
                if (!resp || resp.error) {
                    setNodesAvailable(false);
                    setNodeMessage(resp?.error || "Motor control nodes not detected");
                    return;
                }
                setMotors(resp.motors || []);
                setNodesAvailable(true);
                setNodeMessage("");
                return;
            } catch (err) {
                if (attempt < maxAttempts) {
                    await new Promise((r) => setTimeout(r, 3000));
                    continue;
                }
                setNodesAvailable(false);
                setNodeMessage(`ROS2 nodes not running \u2014 retries exhausted (${err.message})`);
            } finally {
                setLoading(false);
            }
        }
    }, []);

    // Check autonomous mode
    const checkAutonomousMode = useCallback(() => {
        const dashStatus = window.dashboardStatus || window.dashboard?.data?.health;
        const isAuto =
            dashStatus?.autonomous_mode || dashStatus?.arm_mode === "autonomous" || false;
        setAutonomousMode(isAuto);
    }, []);

    // -----------------------------------------------------------------------
    // Transport fetch / update
    // -----------------------------------------------------------------------
    const fetchTransport = useCallback(async () => {
        try {
            const resp = await fetch('/api/motor/transport');
            if (resp.ok) {
                const data = await resp.json();
                setTransport(data.preference || 'auto');
                setTransportInfo(data);
            }
        } catch (e) {
            console.warn('Failed to fetch transport info:', e);
        }
    }, []);

    const handleTransportChange = useCallback(async (newPref) => {
        try {
            const resp = await fetch('/api/motor/transport', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ preference: newPref }),
            });
            if (resp.ok) {
                const data = await resp.json();
                setTransport(data.preference);
                setTransportInfo(prev => ({ ...prev, ...data }));
                // Refresh motor list since it may change with transport
                checkNodes();
            }
        } catch (e) {
            console.warn('Failed to set transport:', e);
        }
    }, []);

    // -----------------------------------------------------------------------
    // Connection fetch / actions
    // -----------------------------------------------------------------------
    const fetchConnection = useCallback(async () => {
        try {
            const resp = await fetch('/api/motor/connection');
            if (resp.ok) {
                const data = await resp.json();
                setConnInfo(data);
                if (data.motor_id != null) setEditMotorId(data.motor_id);
                if (data.baudrate != null) setEditBaudrate(data.baudrate);
                if (data.serial_port != null) setEditPort(data.serial_port);
            }
        } catch (e) {
            console.warn('Failed to fetch connection info:', e);
        }
    }, []);

    const handleUpdateConnection = useCallback(async () => {
        try {
            const body = {};
            if (editMotorId !== connInfo.motor_id) body.motor_id = editMotorId;
            if (editBaudrate !== connInfo.baudrate) body.baudrate = editBaudrate;
            if (editPort !== (connInfo.serial_port || '')) body.serial_port = editPort;
            if (Object.keys(body).length === 0) return;
            const resp = await fetch('/api/motor/connection', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (resp.ok) {
                const data = await resp.json();
                setConnInfo(data);
                addLog('success', `Connection updated: motor_id=${data.motor_id}, baud=${data.baudrate}`);
            } else {
                const err = await resp.json().catch(() => ({}));
                addLog('error', err.detail || 'Failed to update connection');
            }
        } catch (e) {
            addLog('error', `Update failed: ${e.message}`);
        }
    }, [editMotorId, editBaudrate, editPort, connInfo, addLog]);

    // -----------------------------------------------------------------------
    // Product info probe — verifies actual motor communication
    // (Must be defined before handleConnect/refreshAll which reference it)
    // -----------------------------------------------------------------------
    const probeMotorConnection = useCallback(async (motorId) => {
        if (!motorId) return false;
        try {
            const resp = await fetch(`/api/motor/${motorId}/product_info`);
            if (resp.ok) {
                const data = await resp.json();
                // If we got a valid product_info response, the motor is really there
                return !!(data && !data.error);
            }
            return false;
        } catch {
            return false;
        }
    }, []);

    const handleConnect = useCallback(async () => {
        try {
            const resp = await fetch('/api/motor/connect', { method: 'POST' });
            if (resp.ok) {
                const data = await resp.json();
                setConnInfo(prev => ({ ...prev, connected: data.connected, verified: false }));
                addLog('success', data.message);
                checkNodes();
                // Probe to verify actual motor communication
                if (data.connected) {
                    const motorId = connInfo.motor_id;
                    if (motorId) {
                        const verified = await probeMotorConnection(motorId);
                        setConnInfo(prev => ({ ...prev, verified }));
                        if (verified) {
                            // Run full LK Motor Tool connect sequence
                            addLog('info', 'Reading all motor settings (0x1F\u21920x12\u21920x16\u21920x14\u21920x10)...');
                            try {
                                const allSettings = await api(`/api/motor/${motorId}/read_all_settings`, "POST");
                                // Store CMD 0x14 full_config for settings panels
                                if (allSettings?.full_config) {
                                    setFullConfig(allSettings.full_config);
                                }
                                // Store firmware version from CMD 0x1F
                                if (allSettings?.firmware_version) {
                                    setFirmwareVersion(allSettings.firmware_version);
                                }
                                // Store product info from CMD 0x12
                                if (allSettings?.product_info) {
                                    setProductInfo(allSettings.product_info);
                                }
                                // Store extended config from CMD 0x16
                                if (allSettings?.ext_config) {
                                    setExtConfig(allSettings.ext_config);
                                }
                                // Check heartbeat (CMD 0x10)
                                if (allSettings?.heartbeat?.alive) {
                                    addLog('success', 'Motor heartbeat confirmed');
                                }
                                if (allSettings?._failed?.length > 0) {
                                    addLog('warn', `Some reads failed: ${allSettings._failed.join(', ')}`);
                                }
                            } catch (e) {
                                addLog('warn', `read_all_settings failed: ${e.message}`);
                            }
                            // Trigger individual panel reads as fallback/supplement
                            setReadAllTrigger(prev => prev + 1);
                        } else {
                            addLog('warn', `Serial connected but motor ${motorId} not responding on bus`);
                        }
                    }
                }
            } else {
                const err = await resp.json().catch(() => ({}));
                addLog('error', err.detail || 'Connect failed');
            }
        } catch (e) {
            addLog('error', `Connect failed: ${e.message}`);
        }
    }, [addLog, connInfo.motor_id, probeMotorConnection, setReadAllTrigger]);

    const handleDisconnect = useCallback(async () => {
        try {
            const resp = await fetch('/api/motor/disconnect', { method: 'POST' });
            if (resp.ok) {
                const data = await resp.json();
                setConnInfo(prev => ({ ...prev, connected: data.connected, verified: false }));
                addLog('warn', data.message);
            } else {
                const err = await resp.json().catch(() => ({}));
                addLog('error', err.detail || 'Disconnect failed');
            }
        } catch (e) {
            addLog('error', `Disconnect failed: ${e.message}`);
        }
    }, [addLog]);

    // -----------------------------------------------------------------------
    // Refresh all — called by the refresh button in MotorSelector
    // -----------------------------------------------------------------------
    const refreshAll = useCallback(async () => {
        setRefreshing(true);
        try {
            // Run transport + connection fetch in parallel
            await Promise.all([fetchTransport(), fetchConnection()]);
            // Then check nodes (discovers motors on the bus)
            await checkNodes();
            // After checkNodes, probe the current motor to verify connection
            const currentMotorId = connInfo.motor_id;
            if (connInfo.connected && currentMotorId) {
                const verified = await probeMotorConnection(currentMotorId);
                setConnInfo(prev => ({ ...prev, verified }));
                if (verified) {
                    addLog('success', `Motor ${currentMotorId} verified via product_info`);
                } else {
                    addLog('warn', `Motor ${currentMotorId}: serial connected but motor not responding`);
                }
            }
        } catch (e) {
            addLog('error', `Refresh failed: ${e.message}`);
        } finally {
            setRefreshing(false);
        }
    }, [fetchTransport, fetchConnection, checkNodes, connInfo.motor_id, connInfo.connected, probeMotorConnection, addLog]);

    // -----------------------------------------------------------------------
    // Initialize on mount
    // -----------------------------------------------------------------------
    useEffect(() => {
        checkNodes();
        checkAutonomousMode();
        fetchTransport();
        fetchConnection();

        // Periodic node check
        nodeCheckRef.current = setInterval(() => {
            // Only re-check when nodes aren't available yet
            setNodesAvailable((avail) => {
                if (!avail) checkNodes();
                return avail;
            });
        }, NODE_CHECK_INTERVAL_MS);

        // Chart update tick at 5Hz
        chartUpdateRef.current = setInterval(() => {
            setLiveChartTick((t) => t + 1);
        }, 200);

        // Visibility change handler
        const onVisibility = () => {
            if (document.hidden) {
                if (nodeCheckRef.current) {
                    clearInterval(nodeCheckRef.current);
                    nodeCheckRef.current = null;
                }
            } else {
                // Only resume node polling when WS is connected
                if (!nodeCheckRef.current && !wsDisconnectedRef.current) {
                    nodeCheckRef.current = setInterval(() => {
                        setNodesAvailable((avail) => {
                            if (!avail) checkNodes();
                            return avail;
                        });
                    }, NODE_CHECK_INTERVAL_MS);
                }
            }
        };
        document.addEventListener("visibilitychange", onVisibility);

        return () => {
            document.removeEventListener("visibilitychange", onVisibility);
            if (nodeCheckRef.current) clearInterval(nodeCheckRef.current);
            if (chartUpdateRef.current) clearInterval(chartUpdateRef.current);
            if (stepTestPollRef.current) clearInterval(stepTestPollRef.current);
            // Stop RS485 polling when component unmounts
            api("/api/motor/polling/stop", "POST").catch(() => {});
            disconnectWs();
        };
    }, []);

    // -----------------------------------------------------------------------
    // WebSocket connection
    // -----------------------------------------------------------------------
    const disconnectWs = useCallback(() => {
        if (wsReconnectRef.current) {
            clearTimeout(wsReconnectRef.current);
            wsReconnectRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current.onclose = null;
            wsRef.current.onerror = null;
            wsRef.current.close();
            wsRef.current = null;
        }
    }, []);

    const connectWs = useCallback(
        (motorId, useFallback) => {
            const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
            const endpoint = useFallback ? "/ws/pid/motor_state" : "/api/motor/ws/state";
            const url = `${protocol}//${window.location.host}${endpoint}`;

            let ws;
            try {
                ws = new WebSocket(url);
            } catch {
                if (!useFallback) {
                    addLog("warn", "Primary WS failed, trying fallback");
                    connectWs(motorId, true);
                    return;
                }
                return;
            }

            ws.onopen = () => {
                wsReconnectAttemptsRef.current = 0;
                ws.send(JSON.stringify({ subscribe: motorId }));
                addLog("info", "WebSocket connected for motor state" + (useFallback ? " (fallback)" : ""));
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    onMotorStateMsg(data, motorId);
                } catch {
                    // ignore parse errors
                }
            };

            ws.onerror = () => {
                if (!useFallback && wsReconnectAttemptsRef.current === 0) {
                    addLog("warn", "Primary WS endpoint error, trying fallback");
                    connectWs(motorId, true);
                    return;
                }
            };

            ws.onclose = () => {
                if (wsReconnectAttemptsRef.current >= WS_MAX_RETRIES) {
                    addLog("error", `WebSocket reconnection failed after ${WS_MAX_RETRIES} attempts`);
                    return;
                }
                wsReconnectAttemptsRef.current++;
                wsReconnectRef.current = setTimeout(() => {
                    connectWs(motorId, useFallback);
                }, WS_RECONNECT_DELAY);
            };

            wsRef.current = ws;
        },
        [addLog],
    );

    // Process incoming motor state WS message
    const onMotorStateMsg = useCallback(
        (data, subscribedMotorId) => {
            // Filter for selected motor
            if (
                data.motor_id != null &&
                String(data.motor_id) !== String(subscribedMotorId)
            ) {
                return;
            }

            // Buffer for oscillation detection
            const buf = motorStateBufferRef.current;
            buf.push(data);
            if (buf.length > maxLivePointsRef.current) buf.shift();

            // Live chart data
            const now = Date.now();
            if (now - lastDataTimestampRef.current > 2000) {
                // Gap detection: insert null
                liveLabelsRef.current.push("");
                liveDatasetsRef.current[0].data.push(null);
                liveDatasetsRef.current[1].data.push(null);
            }
            lastDataTimestampRef.current = now;

            const t =
                data.timestamp != null
                    ? Number(data.timestamp).toFixed(1)
                    : new Date().toLocaleTimeString();
            liveLabelsRef.current.push(t);
            liveDatasetsRef.current[0].data.push(data.position_deg);
            liveDatasetsRef.current[1].data.push(data.velocity_dps);

            // Keep rolling window
            const maxPts = maxLivePointsRef.current;
            while (liveLabelsRef.current.length > maxPts) {
                liveLabelsRef.current.shift();
                liveDatasetsRef.current.forEach((ds) => ds.data.shift());
            }
            // Also trim snapshots in sync
            snapshotDatasetsRef.current.forEach((ds) => {
                while (ds.data.length > maxPts) ds.data.shift();
            });

            // Store enriched motor state
            const ms = lastMotorStateRef.current;
            Object.assign(ms, {
                temperature_c: data.temperature_c,
                torque_current_a: data.torque_current_a,
                speed_dps: data.speed_dps,
                encoder_position: data.encoder_position,
                voltage_v: data.voltage_v,
                multi_turn_deg: data.multi_turn_deg,
                single_turn_deg: data.single_turn_deg,
                phase_current_a: data.phase_current_a,
                error_flags: data.error_flags,
                motor_state: data.motor_state,
            });
            // Update reactive state periodically via the tick mechanism
            // We update it less frequently to avoid excessive re-renders
            setLastMotorState({ ...ms });

            // E-stop detection
            if (data.estop != null) {
                setEStopActive(!!data.estop);
            }

            // Oscillation detection: 7+ velocity sign changes in last 10 samples
            if (buf.length >= 10) {
                const last10 = buf.slice(-10);
                let signChanges = 0;
                for (let i = 1; i < last10.length; i++) {
                    const prev = last10[i - 1].velocity_dps || 0;
                    const curr = last10[i].velocity_dps || 0;
                    if ((prev > 0 && curr < 0) || (prev < 0 && curr > 0)) signChanges++;
                }
                setOscillationWarning(signChanges >= 7);
            }
        },
        [],
    );

    // -----------------------------------------------------------------------
    // Motor selection handler
    // -----------------------------------------------------------------------
    const onMotorSelect = useCallback(
        async (motorId) => {
            if (!motorId) {
                setSelectedMotor(null);
                setMotorStatus("");
                disconnectWs();
                return;
            }
            const motor = motors.find((m) => String(m.motor_id) === String(motorId));
            if (!motor) return;

            setSelectedMotor(motor);
            setMotorStatus("online");
            addLog("info", `Selected motor: ${motor.joint_name} (${motor.motor_id})`);

            // Load gain limits
            try {
                const limResp = await api(`/api/pid/limits/${motor.motor_type}`);
                if (limResp?.gain_limits) setGainLimits(limResp.gain_limits);
            } catch (e) {
                addLog("error", `Failed to load gain limits: ${e.message}`);
            }

            // Read current gains
            await readGains(motor);

            // Load profiles
            await loadProfiles(motor.motor_type);

            // Connect WebSocket
            disconnectWs();
            wsReconnectAttemptsRef.current = 0;
            connectWs(motor.motor_id);
        },
        [motors, disconnectWs, connectWs, addLog],
    );

    // Auto-select connected motor when motors array populates after connection
    useEffect(() => {
        if (selectedMotor) return; // already selected
        if (!connInfo.connected || !motors.length) return;
        const match = motors.find((m) => String(m.motor_id) === String(connInfo.motor_id));
        if (match) onMotorSelect(match.motor_id);
    }, [motors, connInfo.connected, connInfo.motor_id, selectedMotor, onMotorSelect]);

    // -----------------------------------------------------------------------
    // PID operations
    // -----------------------------------------------------------------------
    const readGains = useCallback(
        async (motor) => {
            const m = motor || selectedMotor;
            if (!m) return;
            setLoading(true);
            try {
                const resp = await api(`/api/pid/read/${m.motor_id}`);
                if (!resp?.success) {
                    addLog("error", resp?.error || "Failed to read PID gains");
                    return;
                }
                setGains({ ...resp.gains });
                setLastReadGains({ ...resp.gains });
                addLog("success", `Read gains from motor ${m.motor_id}`);
            } catch (err) {
                addLog("error", `Read failed: ${err.message}`);
            } finally {
                setLoading(false);
            }
        },
        [selectedMotor, addLog],
    );

    const onGainChange = useCallback((key, value) => {
        setGains((prev) => ({ ...prev, [key]: value }));
    }, []);

    const applyToRam = useCallback(async () => {
        if (!selectedMotor || eStopActive) return;
        try {
            const resp = await api(
                `/api/pid/write/${selectedMotor.motor_id}`,
                "POST",
                gains,
            );
            if (!resp?.success) {
                addLog("error", resp?.error || "Failed to apply gains");
                return;
            }
            setLastReadGains({ ...gains });
            addLog("success", `Applied gains to RAM (motor ${selectedMotor.motor_id})`);
            showToast("Gains applied to RAM", "success");
        } catch (err) {
            addLog("error", `Apply failed: ${err.message}`);
        }
    }, [selectedMotor, eStopActive, gains, addLog, showToast]);

    const saveToRom = useCallback(async () => {
        if (!selectedMotor || eStopActive) return;
        const ok = await mainConfirm({
            title: "Save to ROM",
            message: "This permanently saves gains to motor ROM. Continue?",
            dangerous: true,
            confirmText: "Save to ROM",
        });
        if (!ok) return;
        const body = { ...gains, confirmation_token: "CONFIRM_ROM_WRITE" };
        try {
            const resp = await api(
                `/api/pid/save/${selectedMotor.motor_id}`,
                "POST",
                body,
            );
            if (!resp?.success) {
                addLog("error", resp?.error || "Failed to save to ROM");
                return;
            }
            addLog("warn", `Saved gains to ROM (motor ${selectedMotor.motor_id})`);
            showToast("Gains saved to ROM permanently", "warning");
        } catch (err) {
            addLog("error", `ROM save failed: ${err.message}`);
        }
    }, [selectedMotor, eStopActive, gains, addLog, showToast, mainConfirm]);

    const revertGains = useCallback(() => {
        if (!lastReadGains) return;
        setGains({ ...lastReadGains });
        addLog("info", "Reverted gains to last-read values");
    }, [lastReadGains, addLog]);

    // -----------------------------------------------------------------------
    // Profile operations
    // -----------------------------------------------------------------------
    const loadProfiles = useCallback(async (motorType) => {
        try {
            const resp = await api(`/api/pid/profiles/${motorType}`);
            setProfiles(resp?.profiles || []);
        } catch (err) {
            addLog("error", `Failed to load profiles: ${err.message}`);
        }
    }, [addLog]);

    const loadProfile = useCallback(async () => {
        if (!selectedProfile || !selectedMotor) return;
        try {
            const resp = await api(
                `/api/pid/profiles/${selectedMotor.motor_type}/${selectedProfile}`,
            );
            if (!resp?.gains) {
                addLog("error", "Failed to load profile");
                return;
            }
            if (resp.motor_type && resp.motor_type !== selectedMotor.motor_type) {
                const ok = await mainConfirm({
                    title: "Motor Type Mismatch",
                    message: `Profile is for ${resp.motor_type} but selected motor is ${selectedMotor.motor_type}. Load anyway?`,
                });
                if (!ok) return;
            }
            setGains({ ...resp.gains });
            addLog("info", `Loaded profile: ${selectedProfile}`);
            showToast(`Profile "${selectedProfile}" loaded`, "info");
        } catch (err) {
            addLog("error", `Load profile failed: ${err.message}`);
        }
    }, [selectedProfile, selectedMotor, addLog, showToast, mainConfirm]);

    const saveProfile = useCallback(async () => {
        if (!selectedMotor) return;
        const name = prompt("Enter profile name:");
        if (!name?.trim()) return;
        const description = prompt("Description (optional):");
        try {
            const resp = await api("/api/pid/profiles/save", "POST", {
                name: name.trim(),
                motor_type: selectedMotor.motor_type,
                gains,
                description: description || undefined,
            });
            if (!resp?.success) {
                addLog("error", "Failed to save profile");
                return;
            }
            addLog("success", `Saved profile: ${name.trim()}`);
            showToast("Profile saved", "success");
            await loadProfiles(selectedMotor.motor_type);
        } catch (err) {
            addLog("error", `Save profile failed: ${err.message}`);
        }
    }, [selectedMotor, gains, addLog, showToast, loadProfiles]);

    // -----------------------------------------------------------------------
    // Step test operations
    // -----------------------------------------------------------------------
    const runStepTest = useCallback(async () => {
        if (!selectedMotor || eStopActive || activeStepTestIdRef.current) return;

        addLog("info", `Starting step test: ${testStepSize}deg, ${testDuration}s`);
        setStepTestRunning(true);
        setStepTestProgress(0);
        setStepTestProgressText("Starting...");

        try {
            const resp = await api(
                `/api/pid/step_test/${selectedMotor.motor_id}`,
                "POST",
                { step_size_degrees: testStepSize, duration_seconds: testDuration },
            );
            if (!resp?.test_id) {
                addLog("error", "Failed to start step test");
                setStepTestRunning(false);
                return;
            }
            activeStepTestIdRef.current = resp.test_id;

            // Poll for results
            const startTime = Date.now();
            const totalMs = testDuration * 1000;
            stepTestPollRef.current = setInterval(async () => {
                const elapsed = Date.now() - startTime;
                const pct = Math.min(95, Math.round((elapsed / totalMs) * 100));
                setStepTestProgress(pct);
                setStepTestProgressText("Running...");

                try {
                    const pollResp = await api(
                        `/api/pid/step_test/${selectedMotor.motor_id}/result/${activeStepTestIdRef.current}`,
                    );
                    if (pollResp?.status === "completed") {
                        clearInterval(stepTestPollRef.current);
                        stepTestPollRef.current = null;
                        activeStepTestIdRef.current = null;
                        setStepTestProgress(100);
                        setStepTestProgressText("Complete");
                        setTimeout(() => setStepTestRunning(false), 1000);

                        if (pollResp.result) {
                            const results = stepTestResultsRef.current;
                            results.push(pollResp.result);
                            if (results.length > MAX_OVERLAYS) results.shift();
                            plotStepResult();
                            if (pollResp.result.metrics) {
                                setMetrics(pollResp.result.metrics);
                            }
                            addLog("success", "Step test completed");
                        }
                    } else if (pollResp?.status === "failed") {
                        clearInterval(stepTestPollRef.current);
                        stepTestPollRef.current = null;
                        activeStepTestIdRef.current = null;
                        setStepTestRunning(false);
                        addLog("error", "Step test failed");
                    }
                } catch {
                    // Continue polling on transient errors
                }
            }, 500);
        } catch (err) {
            addLog("error", `Step test error: ${err.message}`);
            setStepTestRunning(false);
        }
    }, [selectedMotor, eStopActive, testStepSize, testDuration, addLog]);

    // Plot step result onto step charts
    const plotStepResult = useCallback(() => {
        const allResults = stepTestResultsRef.current;
        if (!allResults.length) return;

        const count = allResults.length;
        // Use longest timestamps for labels
        let longestTs = [];
        for (const r of allResults) {
            if ((r.timestamps || []).length > longestTs.length) {
                longestTs = r.timestamps;
            }
        }
        const labels = longestTs.map((t) => Number(t).toFixed(2));

        // Latest result for setpoint
        const latest = allResults[count - 1];
        const sp = latest.setpoint ?? 0;

        // Build per-run datasets
        const posDatasets = [
            {
                label: "Setpoint",
                data: longestTs.map(() => sp),
                borderColor: getMotorChartColors().setpoint,
                backgroundColor: "transparent",
                pointRadius: 0,
                borderWidth: 1.5,
                borderDash: [6, 3],
                tension: 0.2,
            },
        ];
        const errDatasets = [];
        const velDatasets = [];
        const curDatasets = [];

        allResults.forEach((r, i) => {
            const color = OVERLAY_COLORS[i % OVERLAY_COLORS.length];
            const alpha = count === 1 ? 1.0 : 0.3 + 0.7 * (i / (count - 1));
            const lineColor = fadeColor(color, alpha);
            const runLabel = count > 1 ? `Run ${i + 1}` : "";
            const positions = r.positions || [];
            const errorArr = positions.map((p) => p - (r.setpoint ?? 0));

            posDatasets.push({
                label: runLabel ? `${runLabel} Actual` : "Actual",
                data: positions,
                borderColor: lineColor,
                backgroundColor: "transparent",
                pointRadius: 0,
                borderWidth: i === count - 1 ? 2 : 1.5,
                tension: 0.2,
            });
            errDatasets.push({
                label: runLabel ? `${runLabel} Error` : "Error",
                data: errorArr,
                borderColor: lineColor,
                backgroundColor: "transparent",
                pointRadius: 0,
                borderWidth: i === count - 1 ? 2 : 1.5,
                tension: 0.2,
            });
            velDatasets.push({
                label: runLabel ? `${runLabel} Velocity` : "Velocity",
                data: r.velocities || [],
                borderColor: lineColor,
                backgroundColor: "transparent",
                pointRadius: 0,
                borderWidth: i === count - 1 ? 2 : 1.5,
                tension: 0.2,
            });
            curDatasets.push({
                label: runLabel ? `${runLabel} Current` : "Current",
                data: r.currents || [],
                borderColor: lineColor,
                backgroundColor: "transparent",
                pointRadius: 0,
                borderWidth: i === count - 1 ? 2 : 1.5,
                tension: 0.2,
            });
        });

        setStepChartData({
            position: { labels, datasets: posDatasets },
            error: { labels, datasets: errDatasets },
            velocity: { labels, datasets: velDatasets },
            current: { labels, datasets: curDatasets },
        });
    }, []);

    // -----------------------------------------------------------------------
    // Auto-tune operations
    // -----------------------------------------------------------------------
    const autoSuggestGains = useCallback(async () => {
        if (stepTestResultsRef.current.length === 0) {
            addLog("error", "Run a step test first before auto-tuning");
            showToast("Run a step test first before auto-tuning", "error");
            return;
        }
        const latest = stepTestResultsRef.current[stepTestResultsRef.current.length - 1];
        try {
            const resp = await api("/api/pid/autotune/analyze", "POST", {
                timestamps: latest.timestamps,
                positions: latest.positions,
                setpoint: latest.setpoint,
                motor_id: selectedMotor?.motor_id,
            });
            if (!resp?.success || !resp.suggested_gains) {
                addLog("error", "Auto-tune analysis failed");
                return;
            }
            setAllRuleSuggestions(resp.suggested_gains);
            setSuggestedGains(resp.suggested_gains[selectedRule] || null);
            addLog("success", "Auto-tune analysis complete");
        } catch (err) {
            addLog("error", `Auto-tune error: ${err.message}`);
        }
    }, [selectedMotor, selectedRule, addLog, showToast]);

    const onRuleChange = useCallback(
        (rule) => {
            setSelectedRule(rule);
            if (allRuleSuggestions?.[rule]) {
                setSuggestedGains(allRuleSuggestions[rule]);
            }
        },
        [allRuleSuggestions],
    );

    const applySuggestion = useCallback(() => {
        if (!suggestedGains) return;
        setGains({ ...suggestedGains });
        addLog("info", "Applied suggested gains to sliders (not yet written to motor)");
        showToast("Suggestion applied to sliders", "info");
    }, [suggestedGains, addLog, showToast]);

    // -----------------------------------------------------------------------
    // Wizard operations
    // -----------------------------------------------------------------------
    const startWizard = useCallback(() => {
        setWizardStep(1);
        setWizardLocks({ current: false, speed: false, angle: false });
        addLog("info", "Started guided tuning wizard");
    }, [addLog]);

    const wizardNext = useCallback(() => {
        setWizardStep((s) => Math.min(s + 1, 3));
    }, []);

    const finishWizard = useCallback(() => {
        setWizardStep(0);
        addLog("success", "Guided tuning completed");
    }, [addLog]);

    const toggleWizardLock = useCallback(
        (loop) => {
            setWizardLocks((prev) => {
                const next = { ...prev, [loop]: !prev[loop] };
                addLog("info", `${loop} loop ${next[loop] ? "locked" : "unlocked"}`);
                return next;
            });
        },
        [addLog],
    );

    // -----------------------------------------------------------------------
    // Chart time window
    // -----------------------------------------------------------------------
    const onTimeWindowChange = useCallback((seconds) => {
        setChartTimeWindow(seconds);
        maxLivePointsRef.current = seconds * 10;
    }, []);

    // -----------------------------------------------------------------------
    // Chart snapshot operations
    // -----------------------------------------------------------------------
    const captureSnapshot = useCallback(() => {
        if (snapshotCount >= MAX_OVERLAYS) {
            showToast(`Max ${MAX_OVERLAYS} snapshots`, "warning");
            return;
        }
        const newSnaps = liveDatasetsRef.current
            .filter((ds) => !ds._isSnapshot)
            .map((ds) => ({
                label: `${ds.label} [snap ${snapshotCount + 1}]`,
                data: [...ds.data],
                borderColor: fadeColor(ds.borderColor, 0.3),
                backgroundColor: "transparent",
                borderWidth: 1,
                borderDash: [4, 4],
                pointRadius: 0,
                _isSnapshot: true,
            }));
        snapshotDatasetsRef.current.push(...newSnaps);
        setSnapshotCount((c) => c + 1);
        showToast(`Snapshot ${snapshotCount + 1} captured`, "info");
    }, [snapshotCount, showToast]);

    const clearSnapshots = useCallback(() => {
        snapshotDatasetsRef.current = [];
        setSnapshotCount(0);
        showToast("Snapshots cleared", "info");
    }, [showToast]);

    const toggleCurrentMode = useCallback(() => {
        setCurrentChartMode((m) => {
            const next = m === "torque" ? "phase" : "torque";
            showToast(`Current mode: ${next}`, "info");
            return next;
        });
    }, [showToast]);

    // -----------------------------------------------------------------------
    // Export operations
    // -----------------------------------------------------------------------
    const exportCsv = useCallback(() => {
        const labels = liveLabelsRef.current;
        if (!labels.length) {
            showToast("No chart data to export", "warning");
            return;
        }
        const datasets = liveDatasetsRef.current.filter((ds) => !ds._isSnapshot);
        const headers = ["timestamp", ...datasets.map((ds) => ds.label)];
        const rows = [headers.join(",")];
        for (let i = 0; i < labels.length; i++) {
            const row = [labels[i]];
            datasets.forEach((ds) => {
                row.push(ds.data[i] != null ? ds.data[i] : "");
            });
            rows.push(row.join(","));
        }
        const csv = rows.join("\n");
        downloadCsv(
            csv,
            `motor_chart_${new Date().toISOString().replace(/[:.]/g, "-")}.csv`,
        );
    }, [showToast]);

    const exportStepData = useCallback(() => {
        const results = stepTestResultsRef.current;
        if (results.length === 0) {
            showToast("No step test data to export", "error");
            return;
        }
        const latest = results[results.length - 1];
        const exportData = {
            timestamp: new Date().toISOString(),
            motor: selectedMotor
                ? {
                      motor_id: selectedMotor.motor_id,
                      joint_name: selectedMotor.joint_name,
                      motor_type: selectedMotor.motor_type,
                  }
                : null,
            pid_gains: gains,
            step_test: {
                step_size_degrees: testStepSize,
                duration_seconds: testDuration,
            },
            result: {
                timestamps: latest.timestamps,
                positions: latest.positions,
                velocities: latest.velocities,
                currents: latest.currents,
                setpoint: latest.setpoint,
                metrics: latest.metrics || null,
            },
        };
        downloadJson(
            exportData,
            `pid_step_data_${selectedMotor?.motor_id || "unknown"}_${Date.now()}.json`,
        );
        addLog("info", "Exported step test data");
    }, [selectedMotor, gains, testStepSize, testDuration, addLog, showToast]);

    const exportSessionLog = useCallback(() => {
        if (sessionLog.length === 0) {
            showToast("No log entries to export", "error");
            return;
        }
        downloadJson(
            {
                exported_at: new Date().toISOString(),
                motor: selectedMotor
                    ? { motor_id: selectedMotor.motor_id, joint_name: selectedMotor.joint_name }
                    : null,
                entries: sessionLog,
            },
            `pid_session_log_${Date.now()}.json`,
        );
        addLog("info", "Exported session log");
    }, [sessionLog, selectedMotor, addLog, showToast]);

    const clearStepResults = useCallback(() => {
        stepTestResultsRef.current = [];
        setMetrics(null);
        setStepChartData({
            position: { labels: [], datasets: [] },
            error: { labels: [], datasets: [] },
            velocity: { labels: [], datasets: [] },
            current: { labels: [], datasets: [] },
        });
        addLog("info", "Cleared step response results");
    }, [addLog]);

    // -----------------------------------------------------------------------
    // Build live chart data for render (from refs, using tick counter)
    // -----------------------------------------------------------------------
    const liveChartData = useMemo(() => {
        // This recalculates when liveChartTick changes (5Hz)
        void liveChartTick;
        const allDatasets = [
            ...liveDatasetsRef.current,
            ...snapshotDatasetsRef.current,
        ];
        return {
            labels: [...liveLabelsRef.current],
            datasets: allDatasets.map((ds) => ({ ...ds, data: [...ds.data] })),
        };
    }, [liveChartTick]);

    // -----------------------------------------------------------------------
    // Controls enabled logic
    // -----------------------------------------------------------------------
    const controlsDisabled = !nodesAvailable || !selectedMotor || eStopActive || wsDisconnected;
    const hasStepData = stepTestResultsRef.current.length > 0;

    // -----------------------------------------------------------------------
    // Tab switching — no auto-polling; all reads are manual
    // -----------------------------------------------------------------------
    const switchTab = useCallback((tabName) => {
        setActiveTab(tabName);
    }, []);

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------
    return html`
        <div>
            ${mainDialog}

            <${MotorSelector}
                motors=${motors}
                selectedMotor=${selectedMotor}
                onSelect=${onMotorSelect}
                motorStatus=${motorStatus}
                onRead=${() => readGains()}
                disabled=${controlsDisabled}
                transport=${transport}
                onTransportChange=${handleTransportChange}
                transportInfo=${transportInfo}
                connInfo=${connInfo}
                editMotorId=${editMotorId}
                onEditMotorId=${setEditMotorId}
                editBaudrate=${editBaudrate}
                onEditBaudrate=${setEditBaudrate}
                editPort=${editPort}
                onEditPort=${setEditPort}
                onUpdateConnection=${handleUpdateConnection}
                onConnect=${handleConnect}
                onDisconnect=${handleDisconnect}
                showToast=${showToast}
                disconnected=${wsDisconnected}
                onRefresh=${refreshAll}
                refreshing=${refreshing}
                onMotorStateChange=${handleMotorStateChange}
            />

            <!-- Tab Bar -->
            <div class="motor-config-tabs">
                ${["setting", "encoder", "product", "test", "tuning"].map(
                    (tab) => html`
                        <button
                            key=${tab}
                            class=${`motor-tab ${activeTab === tab ? "active" : ""}`}
                            onClick=${() => switchTab(tab)}
                        >
                            ${{
                                setting: "Setting",
                                encoder: "Encoder",
                                product: "Product",
                                test: "Test",
                                tuning: "PID Tuning",
                            }[tab]}
                        </button>
                    `,
                )}
            </div>

            <!-- Tab Content Container -->
            <div class="motor-tab-content">
                <div style="display:${activeTab === "setting" ? "block" : "none"}">
                    <div class="setting-tab-grid">
                        <div>
                            <${BasicSettingPanel}
                                selectedMotor=${selectedMotor}
                                showToast=${showToast}
                                disconnected=${wsDisconnected}
                                readAllTrigger=${readAllTrigger}
                                fullConfig=${fullConfig}
                            />

                            <${LimitsSettingPanel}
                                selectedMotor=${selectedMotor}
                                showToast=${showToast}
                                disconnected=${wsDisconnected}
                                readAllTrigger=${readAllTrigger}
                                fullConfig=${fullConfig}
                            />
                        </div>

                        <div>
                            <${ProtectionSettingPanel}
                                selectedMotor=${selectedMotor}
                                showToast=${showToast}
                                disconnected=${wsDisconnected}
                                readAllTrigger=${readAllTrigger}
                                fullConfig=${fullConfig}
                            />
                        </div>

                        <div class="setting-action-col">
                            <${SettingPIDPanel}
                                selectedMotor=${selectedMotor}
                                showToast=${showToast}
                                disconnected=${wsDisconnected}
                                readAllTrigger=${readAllTrigger}
                                fullConfig=${fullConfig}
                            />
                            <div class="setting-action-btns">
                                <button class="btn" onClick=${() => {
                                    if (!selectedMotor) return;
                                    setReadAllTrigger(prev => prev + 1);
                                }} disabled=${!selectedMotor || wsDisconnected}>Read Setting</button>
                                <button class="btn" onClick=${async () => {
                                    if (!selectedMotor) return;
                                    try {
                                        await api("/api/motor/" + selectedMotor.motor_id + "/lifecycle", "POST", { action: 4 });
                                        showToast("Settings saved to ROM", "success");
                                    } catch { showToast("Save failed", "error"); }
                                }} disabled=${!selectedMotor || wsDisconnected}>Save Setting</button>
                                <button class="btn" onClick=${async () => {
                                    if (!selectedMotor) return;
                                    try {
                                        await api("/api/motor/" + selectedMotor.motor_id + "/restore", "POST");
                                        showToast("Settings reset", "success");
                                    } catch { showToast("Reset failed", "error"); }
                                }} disabled=${!selectedMotor || wsDisconnected}>Reset Setting</button>
                            </div>
                        </div>
                    </div>
                </div>

                <div style="display:${activeTab === "encoder" ? "block" : "none"}">
                    <${EncoderPanel}
                        selectedMotor=${selectedMotor}
                        lastMotorState=${lastMotorState}
                        showToast=${showToast}
                        disconnected=${wsDisconnected}
                        readAllTrigger=${readAllTrigger}
                        extConfig=${extConfig}
                    />
                </div>

                <div style="display:${activeTab === "product" ? "block" : "none"}">
                    <${ProductPanel}
                        selectedMotor=${selectedMotor}
                        showToast=${showToast}
                        firmwareVersion=${firmwareVersion}
                        productInfo=${productInfo}
                        readAllTrigger=${readAllTrigger}
                    />
                </div>

                <div style="display:${activeTab === "test" ? "block" : "none"}">
                    <div class="test-tab-layout">
                        <div class="test-tab-column">
                            <${CommandsPanel}
                                selectedMotor=${selectedMotor}
                                eStopActive=${eStopActive}
                                lastMotorState=${lastMotorState}
                                showToast=${showToast}
                                addLog=${addLog}
                                disconnected=${wsDisconnected}
                                onLogEntry=${addTestLogEntry}
                                onMotorStateChange=${handleMotorStateChange}
                            />
                        </div>
                        <div class="test-tab-column">
                            <${TestStatePanel}
                                selectedMotor=${selectedMotor}
                                eStopActive=${eStopActive}
                                showToast=${showToast}
                                disconnected=${wsDisconnected}
                                onLogEntry=${addTestLogEntry}
                            />
                        </div>
                        <div class="test-tab-column test-tab-serial">
                            <${SerialMonitorPanel}
                                selectedMotor=${selectedMotor}
                            />
                        </div>
                        <div class="test-tab-log">
                            <div class="response-history card">
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <h3>
                                        Command Log
                                        <span class="badge">${testHistory.length}</span>
                                    </h3>
                                    ${testHistory.length > 0 && html`
                                        <button class="btn btn-sm" onClick=${() => setTestHistory([])}>Clear</button>
                                    `}
                                </div>
                                <div class="history-list">
                                    ${testHistory.length === 0
                                        ? html`<div class="empty-state">No commands sent yet</div>`
                                        : testHistory.map(
                                              (e, i) => html`
                                                  <div key=${i} class="history-entry">
                                                      <span class="history-timestamp">${e.time}</span>
                                                      <span class="history-mode">${e.action}</span>
                                                      ${e.detail && html` \u2192 ${e.detail}`}
                                                      <span class=${e.success ? "history-success" : "history-fail"}>
                                                          ${e.success ? "\u2713" : "\u2717"}
                                                      </span>
                                                      ${e.success && e.info
                                                          ? html`<span class="history-detail">${e.info}</span>`
                                                          : !e.success && e.error
                                                          ? html`<span class="history-fail">${e.error}</span>`
                                                          : null}
                                                  </div>
                                              `,
                                          )}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div style="display:${activeTab === "tuning" ? "block" : "none"}">
                    <${SafetyBar}
                        eStopActive=${eStopActive}
                        oscillationWarning=${oscillationWarning}
                        sessionStatus=${selectedMotor ? `Motor: ${selectedMotor.joint_name}` : "No active session"}
                        limitOverride=${limitOverride}
                        onLimitOverrideChange=${(v) => {
                            setLimitOverride(v);
                            addLog("warn", `Limit override ${v ? "enabled" : "disabled"}`);
                        }}
                        nodeStatus=${nodesAvailable}
                        nodeMessage=${nodeMessage}
                        autonomousMode=${autonomousMode}
                    />
                    <div class="pid-tuning-layout">
                        <div class="pid-controls-column">
                            <${PIDPanel}
                                gains=${gains}
                                lastReadGains=${lastReadGains}
                                gainLimits=${gainLimits}
                                limitOverride=${limitOverride}
                                disabled=${controlsDisabled}
                                onGainChange=${onGainChange}
                                onApplyRam=${applyToRam}
                                onSaveRom=${saveToRom}
                                onRevert=${revertGains}
                                stepSize=${stepSize}
                                onStepSizeChange=${setStepSize}
                            />

                            <${StepTestPanel}
                                disabled=${controlsDisabled}
                                stepSize=${testStepSize}
                                stepDuration=${testDuration}
                                onStepSizeChange=${setTestStepSize}
                                onDurationChange=${setTestDuration}
                                onRunStepTest=${runStepTest}
                                running=${stepTestRunning}
                                progressPct=${stepTestProgress}
                                progressText=${stepTestProgressText}
                            />

                            <${AutoTunePanel}
                                disabled=${controlsDisabled || !hasStepData}
                                selectedRule=${selectedRule}
                                onRuleChange=${onRuleChange}
                                onAutoSuggest=${autoSuggestGains}
                                onCompareRules=${() => setShowRuleComparison(true)}
                                suggestedGains=${suggestedGains}
                                allRuleSuggestions=${allRuleSuggestions}
                                currentGains=${gains}
                                onApplySuggestion=${applySuggestion}
                            />

                            <${ProfilePanel}
                                disabled=${controlsDisabled}
                                profiles=${profiles}
                                selectedProfile=${selectedProfile}
                                onProfileSelect=${setSelectedProfile}
                                onLoad=${loadProfile}
                                onSave=${saveProfile}
                            />

                            <${WizardPanel}
                                disabled=${controlsDisabled}
                                wizardStep=${wizardStep}
                                wizardLocks=${wizardLocks}
                                onNext=${wizardNext}
                                onToggleLock=${toggleWizardLock}
                                onStart=${startWizard}
                                onFinish=${finishWizard}
                            />
                        </div>

                        <div class="pid-results-column">
                            <${MetricsPanel} metrics=${metrics} />

                            ${showRuleComparison &&
                            html`
                                <${RuleComparisonTable}
                                    allRuleSuggestions=${allRuleSuggestions}
                                    selectedRule=${selectedRule}
                                    onRuleSelect=${onRuleChange}
                                />
                            `}

                            <${SessionLog} log=${sessionLog} onExport=${exportSessionLog} />
                        </div>
                    </div>

                    <${MotorChartsPanel}
                        liveChartData=${liveChartData}
                        stepChartData=${stepChartData}
                        chartTimeWindow=${chartTimeWindow}
                        onTimeWindowChange=${onTimeWindowChange}
                        onCaptureSnapshot=${captureSnapshot}
                        onClearSnapshots=${clearSnapshots}
                        onToggleCurrentMode=${toggleCurrentMode}
                        onExportCsv=${exportCsv}
                        onExportData=${exportStepData}
                        onClearResults=${clearStepResults}
                        hasStepData=${hasStepData}
                        snapshotCount=${snapshotCount}
                        currentChartMode=${currentChartMode}
                    />
                </div>
            </div>

        </div>
    `;
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

registerTab("motor-config", MotorConfigTab);

export default MotorConfigTab;
