/**
 * LaunchControlTab — Preact component for the Launch Control tab.
 *
 * Migrated from vanilla JS (launch_control.js) as part of the incremental
 * Preact migration (task 7.3).
 *
 * Features:
 * - Arm and Vehicle launch panels with start/stop controls
 * - WebSocket-based terminal output streaming
 * - Phase progress timeline with elapsed/estimated timing
 * - Vehicle subsystem status cards
 * - Adaptive polling (fast during transitions, slow at steady state)
 * - "Launch" / "Services" sub-tab switcher per panel
 * - Context-filtered systemd service management (arm/vehicle)
 *
 * @module tabs/LaunchControlTab
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
import { useConfirmDialog } from "../components/ConfirmationDialog.mjs";
import { registerTab } from "../tabRegistry.js";
import { ServicePanel } from "./SystemServicesTab.mjs";
import { WebSocketContext } from "../app.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_NORMAL_MS = 5000;
const POLL_FAST_MS = 1000;
const MAX_OUTPUT_LINES = 500;

/** Phase definitions for the progress timeline. */
const PHASES = [
    { name: "cleanup", label: "Cleanup", duration: 5 },
    { name: "daemon_restart", label: "Daemon Restart", duration: 2 },
    { name: "node_startup", label: "Node Startup", duration: 1 },
    { name: "motor_homing", label: "Motor Homing", duration: 7 },
    { name: "system_ready", label: "System Ready", duration: 0 },
];

const STEADY_STATES = ["running", "active", "stopped", "inactive", ""];

/** Sub-tab definitions for Launch Control panels. */
const SUB_TABS = [
    { id: "launch", label: "Launch" },
    { id: "services", label: "Services" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Map a process state string to a CSS status class and display label.
 * @param {Object|null} status
 * @returns {{ cls: string, label: string }}
 */
function getStatusDisplay(status) {
    if (!status || !status.status) {
        return { cls: "status-stopped", label: "Stopped" };
    }
    const state = status.status.toLowerCase();
    if (state === "running" || state === "active") {
        return { cls: "status-running", label: "Running" };
    }
    if (state === "stopping") {
        return { cls: "status-stopping", label: "Stopping" };
    }
    if (state === "error" || state === "failed") {
        return { cls: "status-error", label: "Error" };
    }
    return { cls: "status-stopped", label: "Stopped" };
}

/**
 * Map a subsystem state to a CSS class.
 * @param {string} state
 * @returns {string}
 */
function subsystemStatusClass(state) {
    const s = (state || "unknown").toLowerCase();
    if (s === "running" || s === "active") return "status-running";
    if (s === "error" || s === "failed") return "status-error";
    if (s === "starting") return "status-stopping";
    return "status-stopped";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Sub-tab switcher bar.
 *
 * @param {object} props
 * @param {string} props.activeSubTab - Currently active sub-tab id
 * @param {(id: string) => void} props.onSwitch - Handler when a sub-tab is clicked
 */
function SubTabBar({ activeSubTab, onSwitch }) {
    return html`
        <div class="sub-tab-bar">
            ${SUB_TABS.map(
                (tab) => html`
                    <button
                        key=${tab.id}
                        class="sub-tab-btn${activeSubTab === tab.id ? " active" : ""}"
                        onClick=${() => onSwitch(tab.id)}
                    >
                        ${tab.label}
                    </button>
                `
            )}
        </div>
    `;
}

/**
 * Progress timeline showing launch phases with elapsed/estimated times.
 *
 * @param {object} props
 * @param {Object<string,string>} props.phaseStatuses - Map of phase name to status
 * @param {boolean} props.visible - Whether the timeline is shown
 * @param {number|null} props.startTime - Timestamp when launch started
 * @param {string|null} props.finalLabel - "Complete" or "Failed" or null
 */
function ProgressTimeline({ phaseStatuses, visible, startTime, finalLabel }) {
    const [elapsed, setElapsed] = useState(0);

    useEffect(() => {
        if (!visible || !startTime) {
            setElapsed(0);
            return;
        }
        // Update elapsed every 500ms
        const tick = () => {
            setElapsed((Date.now() - startTime) / 1000);
        };
        tick();
        const id = setInterval(tick, 500);
        return () => clearInterval(id);
    }, [visible, startTime]);

    if (!visible) return null;

    // Calculate estimated remaining from incomplete phases
    let remaining = 0;
    for (const phase of PHASES) {
        const st = phaseStatuses[phase.name] || "pending";
        if (st !== "complete" && st !== "error" && st !== "skipped") {
            remaining += phase.duration;
        }
    }

    const estimatedText = finalLabel || `Est. remaining: ${remaining}s`;

    return html`
        <div class="launch-progress-timeline">
            <div class="launch-progress-phases">
                ${PHASES.map(
                    (phase) => html`
                        <div
                            class="launch-phase ${phaseStatuses[phase.name] ||
                            "pending"}"
                            key=${phase.name}
                        >
                            <div class="phase-bar"></div>
                            <div class="phase-label">${phase.label}</div>
                        </div>
                    `
                )}
            </div>
            <div class="launch-progress-timing">
                <span class="launch-progress-elapsed">
                    Elapsed: ${Math.round(elapsed * 10) / 10}s
                </span>
                <span class="launch-progress-estimated">
                    ${estimatedText}
                </span>
            </div>
        </div>
    `;
}

/**
 * Terminal output panel for a launch process.
 *
 * @param {object} props
 * @param {Array<{text: string, stream: string}>} props.lines - Output lines
 * @param {() => void} props.onClear - Clear handler
 */
function OutputTerminal({ lines, onClear }) {
    const termRef = useRef(null);

    // Auto-scroll to bottom when new lines arrive
    useEffect(() => {
        if (termRef.current) {
            termRef.current.scrollTop = termRef.current.scrollHeight;
        }
    }, [lines.length]);

    return html`
        <div class="launch-output-panel">
            <div class="launch-output-header">
                <span>Terminal Output</span>
                <button class="btn btn-sm" onClick=${onClear}>Clear</button>
            </div>
            <div class="launch-output-terminal" ref=${termRef}>
                ${lines.map(
                    (line, i) => html`
                        <div
                            key=${i}
                            class="output-line ${line.stream === "stderr"
                                ? "stderr-line"
                                : ""}"
                        >
                            ${line.text}
                        </div>
                    `
                )}
            </div>
        </div>
    `;
}

/**
 * Vehicle subsystem status cards.
 *
 * @param {object} props
 * @param {Array|null} props.subsystems
 */
function SubsystemPanel({ subsystems }) {
    if (!subsystems || !Array.isArray(subsystems) || subsystems.length === 0) {
        return html`
            <div class="launch-subsystems-panel">
                <div class="empty-state">No subsystem data</div>
            </div>
        `;
    }

    return html`
        <div class="launch-subsystems-panel">
            ${subsystems.map(
                (sub) => html`
                    <div class="launch-subsystem-card" key=${sub.name}>
                        <span class="launch-subsystem-name">
                            ${sub.name || "unknown"}
                        </span>
                        <span
                            class="launch-status-indicator ${subsystemStatusClass(
                                sub.status
                            )}"
                        >
                            ${(sub.status || "unknown").toLowerCase()}
                        </span>
                    </div>
                `
            )}
        </div>
    `;
}

/**
 * A single launch panel (arm or vehicle) with sub-tab switcher.
 *
 * @param {object} props
 * @param {string} props.title - Panel title ("Arm Launch" or "Vehicle Launch")
 * @param {string} props.contextFilter - "arm" or "vehicle" for service filtering
 * @param {Object|null} props.status - Current process status
 * @param {Array<{text: string, stream: string}>} props.outputLines
 * @param {Object<string,string>} props.phaseStatuses - Phase status map
 * @param {boolean} props.timelineVisible
 * @param {number|null} props.timelineStart
 * @param {string|null} props.timelineFinal
 * @param {boolean} props.busy
 * @param {() => void} props.onLaunch
 * @param {() => void} props.onStop
 * @param {() => void} props.onClearOutput
 * @param {string} props.activeSubTab - "launch" or "services"
 * @param {(id: string) => void} props.onSubTabSwitch
 * @param {boolean} props.disconnected - WebSocket disconnected state
 * @param {import('preact').ComponentChildren} [props.children] - Extra controls
 * @param {import('preact').ComponentChildren} [props.extraContent] - e.g. subsystem panel
 */
function LaunchPanel({
    title,
    contextFilter,
    status,
    outputLines,
    phaseStatuses,
    timelineVisible,
    timelineStart,
    timelineFinal,
    busy,
    onLaunch,
    onStop,
    onClearOutput,
    activeSubTab,
    onSubTabSwitch,
    disconnected,
    children,
    extraContent,
}) {
    const { cls, label } = getStatusDisplay(status);
    const lockout = busy || disconnected;
    const lockTitle = disconnected ? "Unavailable \u2014 connection lost" : undefined;
    const lockClass = disconnected ? " locked-control" : "";

    return html`
        <div class="card">
            <div class="launch-panel-header">
                <h3>${title}</h3>
                <span class="launch-status-indicator ${cls}">${label}</span>
            </div>
            <${SubTabBar}
                activeSubTab=${activeSubTab}
                onSwitch=${onSubTabSwitch}
            />
            ${activeSubTab === "launch" && html`
                <div class="launch-panel-controls">
                    <div class="launch-param-toggles">${children}</div>
                    <div class="launch-panel-buttons">
                        <button
                            class="btn btn-primary${lockClass}"
                            disabled=${lockout}
                            title=${lockTitle}
                            onClick=${onLaunch}
                        >
                            Launch
                        </button>
                        <button
                            class="btn btn-danger${lockClass}"
                            disabled=${lockout}
                            title=${lockTitle}
                            onClick=${onStop}
                        >
                            Stop
                        </button>
                    </div>
                </div>
                ${extraContent}
                <${OutputTerminal}
                    lines=${outputLines}
                    onClear=${onClearOutput}
                />
                <${ProgressTimeline}
                    phaseStatuses=${phaseStatuses}
                    visible=${timelineVisible}
                    startTime=${timelineStart}
                    finalLabel=${timelineFinal}
                />
            `}
            ${activeSubTab === "services" && html`
                <${ServicePanel}
                    contextFilter=${contextFilter}
                    active=${true}
                    disconnected=${disconnected}
                />
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Custom hooks
// ---------------------------------------------------------------------------

/**
 * Hook to manage a WebSocket connection for launch output streaming.
 * Returns output lines array and a clear function.
 *
 * @param {string} name - "arm" or "vehicle"
 * @param {boolean} shouldConnect - Whether to establish a connection
 * @param {(phase: string, status: string) => void} onPhaseEvent - Phase event handler
 * @returns {{ lines: Array<{text: string, stream: string}>, clearLines: () => void }}
 */
function useLaunchOutputWs(name, shouldConnect, onPhaseEvent) {
    const [lines, setLines] = useState([]);
    const wsRef = useRef(null);
    const onPhaseRef = useRef(onPhaseEvent);

    // Keep the ref current without triggering reconnects
    useEffect(() => {
        onPhaseRef.current = onPhaseEvent;
    }, [onPhaseEvent]);

    useEffect(() => {
        if (!shouldConnect) return;

        const wsHost = window.location.host;
        const wsUrl = `ws://${wsHost}/ws/launch/${name}/output`;

        let ws;
        try {
            ws = new WebSocket(wsUrl);
        } catch (err) {
            console.error(
                `LaunchControlTab: failed to create WS for ${name}:`,
                err
            );
            return;
        }

        ws.onmessage = (event) => {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (_e) {
                data = null;
            }

            // Phase event — update progress timeline
            if (data && data.type === "phase") {
                if (data.phase && data.status && onPhaseRef.current) {
                    onPhaseRef.current(data.phase, data.status);
                }
                return;
            }

            // Structured output message
            let text, stream;
            if (data && data.type === "output") {
                text = data.data || "";
                stream = data.stream || "stdout";
            } else {
                // Legacy / fallback
                text =
                    (data && (data.text || data.line)) ||
                    String(event.data);
                stream = (data && data.stream) || "stdout";
            }

            setLines((prev) => {
                const next = [...prev, { text, stream }];
                // Evict oldest if over limit
                while (next.length > MAX_OUTPUT_LINES) {
                    next.shift();
                }
                return next;
            });
        };

        ws.onerror = (err) => {
            console.error(`LaunchControlTab WS error (${name}):`, err);
        };

        ws.onclose = () => {
            console.log(`LaunchControlTab WS closed (${name})`);
        };

        wsRef.current = ws;

        return () => {
            if (ws) {
                ws.onmessage = null;
                ws.onerror = null;
                ws.onclose = null;
                ws.close();
            }
            wsRef.current = null;
        };
    }, [name, shouldConnect]);

    const clearLines = useCallback(() => {
        setLines([]);
    }, []);

    return { lines, clearLines };
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function LaunchControlTab() {
    const { showToast } = useToast();
    const { dialog, confirm } = useConfirmDialog();
    const { disconnected } = useContext(WebSocketContext);

    // ---- State ----

    // Sub-tab state for arm and vehicle panels
    const [armSubTab, setArmSubTab] = useState("launch");
    const [vehicleSubTab, setVehicleSubTab] = useState("launch");

    // Arm state
    const [armStatus, setArmStatus] = useState(null);
    const [armDebug, setArmDebug] = useState(false);
    const [armId, setArmId] = useState(1);
    const [armBusy, setArmBusy] = useState(false);
    const [armWsActive, setArmWsActive] = useState(false);
    const [armPhases, setArmPhases] = useState({});
    const [armTimelineVisible, setArmTimelineVisible] = useState(false);
    const [armTimelineStart, setArmTimelineStart] = useState(null);
    const [armTimelineFinal, setArmTimelineFinal] = useState(null);

    // Vehicle state
    const [vehicleStatus, setVehicleStatus] = useState(null);
    const [vehicleDebug, setVehicleDebug] = useState(false);
    const [vehicleBusy, setVehicleBusy] = useState(false);
    const [vehicleWsActive, setVehicleWsActive] = useState(false);
    const [vehiclePhases, setVehiclePhases] = useState({});
    const [vehicleTimelineVisible, setVehicleTimelineVisible] =
        useState(false);
    const [vehicleTimelineStart, setVehicleTimelineStart] = useState(null);
    const [vehicleTimelineFinal, setVehicleTimelineFinal] = useState(null);
    const [vehicleSubsystems, setVehicleSubsystems] = useState(null);

    // Polling interval
    const [pollMs, setPollMs] = useState(POLL_NORMAL_MS);

    // Refs
    const mountedRef = useRef(true);

    // ---- Phase event handlers ----

    const onArmPhase = useCallback((phase, status) => {
        setArmPhases((prev) => ({ ...prev, [phase]: status }));
    }, []);

    const onVehiclePhase = useCallback((phase, status) => {
        setVehiclePhases((prev) => ({ ...prev, [phase]: status }));
    }, []);

    // ---- WebSocket output ----

    const {
        lines: armOutputLines,
        clearLines: clearArmOutput,
    } = useLaunchOutputWs("arm", armWsActive, onArmPhase);

    const {
        lines: vehicleOutputLines,
        clearLines: clearVehicleOutput,
    } = useLaunchOutputWs("vehicle", vehicleWsActive, onVehiclePhase);

    // ---- Status fetching ----

    const fetchArmStatus = useCallback(async () => {
        try {
            const status = await safeFetch("/api/launch/arm/status");
            if (!mountedRef.current) return;
            setArmStatus(status);
        } catch (_err) {
            // Silently ignore — will retry on next poll
        }
    }, []);

    const fetchVehicleStatus = useCallback(async () => {
        try {
            const status = await safeFetch("/api/launch/vehicle/status");
            if (!mountedRef.current) return;
            setVehicleStatus(status);
        } catch (_err) {
            // Silently ignore
        }
    }, []);

    const fetchVehicleSubsystems = useCallback(async () => {
        try {
            const data = await safeFetch(
                "/api/launch/vehicle/subsystems"
            );
            if (!mountedRef.current) return;
            setVehicleSubsystems(data);
        } catch (_err) {
            // Silently ignore
        }
    }, []);

    // ---- Check if we should restore normal polling ----

    useEffect(() => {
        if (pollMs === POLL_NORMAL_MS) return;

        const armState = (
            (armStatus && armStatus.status) ||
            ""
        ).toLowerCase();
        const vehState = (
            (vehicleStatus && vehicleStatus.status) ||
            ""
        ).toLowerCase();

        if (
            STEADY_STATES.includes(armState) &&
            STEADY_STATES.includes(vehState)
        ) {
            setPollMs(POLL_NORMAL_MS);
        }
    }, [armStatus, vehicleStatus, pollMs]);

    // ---- Actions ----

    const launchArm = useCallback(async () => {
        const ok = await confirm({
            title: "Launch Arm",
            message: "Start the arm launch process?",
            confirmText: "Launch",
            dangerous: false,
        });
        if (!ok) return;

        setArmBusy(true);
        try {
            const params = { arm_id: armId };
            if (armDebug) params.debug = true;

            const result = await safeFetch("/api/launch/arm", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(params),
            });

            if (result && !result.error) {
                showToast("Arm launch started", "success");
                setArmWsActive(true);
                setPollMs(POLL_FAST_MS);
                // Reset and show timeline
                setArmPhases({});
                setArmTimelineFinal(null);
                setArmTimelineVisible(true);
                setArmTimelineStart(Date.now());
                await fetchArmStatus();
            } else {
                showToast(
                    (result && result.error) || "Failed to launch arm",
                    "error"
                );
            }
        } catch (err) {
            showToast("Failed to launch arm: " + err.message, "error");
        } finally {
            setArmBusy(false);
        }
    }, [confirm, armId, armDebug, showToast, fetchArmStatus]);

    const stopArm = useCallback(async () => {
        const ok = await confirm({
            title: "Stop Arm",
            message:
                "Stop the arm launch process? This will terminate all arm nodes.",
            confirmText: "Stop",
            dangerous: true,
        });
        if (!ok) return;

        setArmBusy(true);
        try {
            const result = await safeFetch("/api/launch/arm/stop", {
                method: "POST",
            });

            if (result && !result.error) {
                showToast("Arm stop requested", "success");
                setPollMs(POLL_FAST_MS);
                await fetchArmStatus();
            } else {
                showToast(
                    (result && result.error) || "Failed to stop arm",
                    "error"
                );
            }
        } catch (err) {
            showToast("Failed to stop arm: " + err.message, "error");
        } finally {
            setArmBusy(false);
        }
    }, [confirm, showToast, fetchArmStatus]);

    const launchVehicle = useCallback(async () => {
        const ok = await confirm({
            title: "Launch Vehicle",
            message: "Start the vehicle launch process?",
            confirmText: "Launch",
            dangerous: false,
        });
        if (!ok) return;

        setVehicleBusy(true);
        try {
            const params = {};
            if (vehicleDebug) params.debug = true;

            const result = await safeFetch("/api/launch/vehicle", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(params),
            });

            if (result && !result.error) {
                showToast("Vehicle launch started", "success");
                setVehicleWsActive(true);
                setPollMs(POLL_FAST_MS);
                // Reset and show timeline
                setVehiclePhases({});
                setVehicleTimelineFinal(null);
                setVehicleTimelineVisible(true);
                setVehicleTimelineStart(Date.now());
                await fetchVehicleStatus();
            } else {
                showToast(
                    (result && result.error) ||
                        "Failed to launch vehicle",
                    "error"
                );
            }
        } catch (err) {
            showToast(
                "Failed to launch vehicle: " + err.message,
                "error"
            );
        } finally {
            setVehicleBusy(false);
        }
    }, [confirm, vehicleDebug, showToast, fetchVehicleStatus]);

    const stopVehicle = useCallback(async () => {
        const ok = await confirm({
            title: "Stop Vehicle",
            message:
                "Stop the vehicle launch process? This will terminate all vehicle nodes.",
            confirmText: "Stop",
            dangerous: true,
        });
        if (!ok) return;

        setVehicleBusy(true);
        try {
            const result = await safeFetch("/api/launch/vehicle/stop", {
                method: "POST",
            });

            if (result && !result.error) {
                showToast("Vehicle stop requested", "success");
                setPollMs(POLL_FAST_MS);
                await fetchVehicleStatus();
            } else {
                showToast(
                    (result && result.error) ||
                        "Failed to stop vehicle",
                    "error"
                );
            }
        } catch (err) {
            showToast(
                "Failed to stop vehicle: " + err.message,
                "error"
            );
        } finally {
            setVehicleBusy(false);
        }
    }, [confirm, showToast, fetchVehicleStatus]);

    // ---- Detect timeline completion/failure from status ----

    useEffect(() => {
        if (!armTimelineVisible) return;
        const state = (
            (armStatus && armStatus.status) ||
            ""
        ).toLowerCase();
        if (state === "running" || state === "active") {
            // Mark all phases complete
            const allComplete = {};
            for (const p of PHASES) allComplete[p.name] = "complete";
            setArmPhases(allComplete);
            setArmTimelineFinal("Complete");
        } else if (state === "error" || state === "failed") {
            setArmTimelineFinal("Failed");
        }
    }, [armStatus, armTimelineVisible]);

    useEffect(() => {
        if (!vehicleTimelineVisible) return;
        const state = (
            (vehicleStatus && vehicleStatus.status) ||
            ""
        ).toLowerCase();
        if (state === "running" || state === "active") {
            const allComplete = {};
            for (const p of PHASES) allComplete[p.name] = "complete";
            setVehiclePhases(allComplete);
            setVehicleTimelineFinal("Complete");
        } else if (state === "error" || state === "failed") {
            setVehicleTimelineFinal("Failed");
        }
    }, [vehicleStatus, vehicleTimelineVisible]);

    // ---- Lifecycle: initial fetch + polling ----

    useEffect(() => {
        mountedRef.current = true;
        fetchArmStatus();
        fetchVehicleStatus();
        return () => {
            mountedRef.current = false;
        };
    }, [fetchArmStatus, fetchVehicleStatus]);

    // Adaptive polling
    useEffect(() => {
        const id = setInterval(() => {
            fetchArmStatus();
            fetchVehicleStatus();
        }, pollMs);
        return () => clearInterval(id);
    }, [pollMs, fetchArmStatus, fetchVehicleStatus]);

    // ---- Render ----

    return html`
        <h2>Launch Control</h2>
        <div class="section-grid">
            <${LaunchPanel}
                title="Arm Launch"
                contextFilter="arm"
                status=${armStatus}
                outputLines=${armOutputLines}
                phaseStatuses=${armPhases}
                timelineVisible=${armTimelineVisible}
                timelineStart=${armTimelineStart}
                timelineFinal=${armTimelineFinal}
                busy=${armBusy}
                onLaunch=${launchArm}
                onStop=${stopArm}
                onClearOutput=${clearArmOutput}
                activeSubTab=${armSubTab}
                onSubTabSwitch=${setArmSubTab}
                disconnected=${disconnected}
            >
                <label>
                    <input
                        type="checkbox"
                        checked=${armDebug}
                        onChange=${(e) => setArmDebug(e.target.checked)}
                    />
                    ${" "}Debug mode
                </label>
                <label>
                    <input
                        type="number"
                        value=${armId}
                        min="1"
                        max="6"
                        class="motor-number-input"
                        onChange=${(e) =>
                            setArmId(parseInt(e.target.value, 10) || 1)}
                    />
                    ${" "}Arm ID
                </label>
            <//>

            <${LaunchPanel}
                title="Vehicle Launch"
                contextFilter="vehicle"
                status=${vehicleStatus}
                outputLines=${vehicleOutputLines}
                phaseStatuses=${vehiclePhases}
                timelineVisible=${vehicleTimelineVisible}
                timelineStart=${vehicleTimelineStart}
                timelineFinal=${vehicleTimelineFinal}
                busy=${vehicleBusy}
                onLaunch=${launchVehicle}
                onStop=${stopVehicle}
                onClearOutput=${clearVehicleOutput}
                activeSubTab=${vehicleSubTab}
                onSubTabSwitch=${setVehicleSubTab}
                disconnected=${disconnected}
                extraContent=${html`<${SubsystemPanel}
                    subsystems=${vehicleSubsystems}
                />`}
            >
                <label>
                    <input
                        type="checkbox"
                        checked=${vehicleDebug}
                        onChange=${(e) =>
                            setVehicleDebug(e.target.checked)}
                    />
                    ${" "}Debug mode
                </label>
            <//>
        </div>

        ${dialog}
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("launch-control", LaunchControlTab);

export { LaunchControlTab };
