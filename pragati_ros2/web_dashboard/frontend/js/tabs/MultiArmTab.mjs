/**
 * MultiArmTab — Preact component for the Multi-Arm Fleet tab.
 *
 * Shows a star topology: vehicle hub card at top, arm cards below with
 * visual connection lines. Supports real-time MQTT status, offline
 * detection, and arm restart commands.
 *
 * @module tabs/MultiArmTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useRef, useMemo } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { useConfirmDialog } from "../components/ConfirmationDialog.mjs";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Poll interval for arm list refresh (ms). */
const POLL_INTERVAL_MS = 3000;

/** Delay before attempting WebSocket reconnection (ms). */
const WS_RECONNECT_DELAY = 5000;

/** Restart timeout before marking as failed (ms). */
const RESTART_TIMEOUT_MS = 30000;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a heartbeat timestamp for display.
 * @param {string|number} heartbeat - ISO string or epoch ms
 * @returns {string} Human-readable relative time
 */
function formatHeartbeat(heartbeat) {
    if (!heartbeat) return "Never";
    const d = new Date(heartbeat);
    if (isNaN(d.getTime())) return "Invalid";

    const diffMs = Date.now() - d.getTime();
    const diffSec = Math.floor(diffMs / 1000);

    if (diffSec < 5) return "Just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    return d.toLocaleTimeString();
}

/**
 * Determine the CSS class for an arm's state.
 * @param {string} state
 * @returns {string}
 */
function stateClass(state) {
    const s = (state || "unknown").toLowerCase();
    if (s === "active" || s === "picking") return "arm-state-active";
    if (s === "error" || s === "estop") return "arm-state-error";
    return "arm-state-idle";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Vehicle hub card showing broker status, arm count, vehicle state (task 6.1).
 */
function VehicleHubCard({ vehicle, mqttConnected }) {
    const brokerCls = mqttConnected
        ? "broker-status broker-connected"
        : "broker-status broker-disconnected";
    const brokerLabel = mqttConnected ? "Broker: Connected" : "MQTT broker not connected";
    const armCount = vehicle
        ? `${vehicle.connected_arm_count || 0}/${vehicle.total_arm_count || 0} Arms Connected`
        : "0/0 Arms Connected";
    const vehicleState = vehicle ? (vehicle.state || "unknown") : "unknown";

    return html`
        <div class="vehicle-hub-card">
            <div class="vehicle-hub-header">
                <span class="vehicle-hub-icon">&#x1F69C;</span>
                <h3>Vehicle Hub</h3>
            </div>
            <div class="vehicle-hub-body">
                <div class="vehicle-info-row">
                    <span class=${brokerCls}></span>
                    <span>${brokerLabel}</span>
                </div>
                <div class="vehicle-info-row">
                    <span class="vehicle-arm-count">${armCount}</span>
                </div>
                <div class="vehicle-info-row">
                    <span class="vehicle-info-label">State:</span>
                    <span class="vehicle-state">${vehicleState}</span>
                </div>
            </div>
            ${!mqttConnected && html`
                <div class="vehicle-broker-banner">
                    MQTT Broker Disconnected — arm data may be stale
                </div>
            `}
        </div>
    `;
}

/**
 * MQTT connection status indicator.
 * @param {object} props
 * @param {boolean} props.connected
 */
function MqttIndicator({ connected }) {
    const cls = connected ? "mqtt-indicator mqtt-connected" : "mqtt-indicator mqtt-disconnected";
    const label = connected ? "MQTT: Connected" : "MQTT: Disconnected";

    return html`
        <div class="fleet-mqtt-status">
            <span class=${cls}></span>
            <span>${label}</span>
        </div>
    `;
}

/**
 * A single arm card showing status, heartbeat, cotton count, temp, and
 * connectivity badges (tasks 6.3, 6.4, 6.5, 6.6).
 */
function ArmCard({ arm, onDetails, onRestart, onEstop, isRestarting }) {
    const armId = arm.arm_id || arm.id || "unknown";
    const state = (arm.state || "unknown").toLowerCase();
    const connectivity = arm.connectivity || (arm.connected ? "connected" : "offline");
    const cottonCount = arm.cotton_count != null ? arm.cotton_count : "--";
    const temperature = arm.temperature_c != null ? `${arm.temperature_c}°C` : "--";
    const lastHeartbeat = arm.last_heartbeat
        ? formatHeartbeat(arm.last_heartbeat)
        : "Never";

    // Card classes based on connectivity
    let cardCls = "arm-card";
    if (connectivity === "offline") cardCls += " arm-card-offline";
    else if (connectivity === "stale") cardCls += " arm-card-stale";
    else cardCls += " arm-card-connected";

    // Badge
    let badge = null;
    if (connectivity === "offline") {
        badge = html`<span class="arm-badge arm-badge-offline">Offline</span>`;
    } else if (connectivity === "stale") {
        badge = html`<span class="arm-badge arm-badge-stale">Stale</span>`;
    }

    return html`
        <div class=${cardCls} data-arm-id=${armId}>
            <div class="arm-card-header">
                <span class="arm-id">Arm ${armId}</span>
                ${badge}
            </div>
            <div class="arm-card-body">
                <div class="arm-info-row">
                    <span class="arm-info-label">State:</span>
                    <span class="arm-state ${stateClass(state)}">${state}</span>
                </div>
                <div class="arm-info-row">
                    <span class="arm-info-label">Cotton:</span>
                    <span class="arm-cotton-count">${cottonCount}</span>
                </div>
                <div class="arm-info-row">
                    <span class="arm-info-label">Temp:</span>
                    <span class="arm-temperature">${temperature}</span>
                </div>
                <div class="arm-info-row">
                    <span class="arm-info-label">Heartbeat:</span>
                    <span class="arm-heartbeat">${lastHeartbeat}</span>
                </div>
                ${(connectivity === "offline" || connectivity === "stale") && html`
                    <div class="arm-info-row arm-last-seen">
                        <span class="arm-info-label">Last seen:</span>
                        <span>${lastHeartbeat}</span>
                    </div>
                `}
            </div>
            <div class="arm-card-actions">
                <button
                    class="btn btn-sm arm-details-btn"
                    title="View Details"
                    onClick=${() => onDetails(armId)}
                >Details</button>
                <button
                    class="btn btn-sm arm-restart-btn"
                    title="Restart"
                    disabled=${isRestarting}
                    onClick=${() => onRestart(armId)}
                >${isRestarting ? "Restarting..." : "Restart"}</button>
                <button
                    class="btn btn-sm btn-danger arm-estop-btn"
                    title="Emergency Stop"
                    onClick=${() => onEstop(armId)}
                >E-STOP</button>
            </div>
        </div>
    `;
}

/**
 * Visual connection lines from vehicle hub to arm cards (task 6.2).
 * Renders SVG lines. Arms with offline/stale get dashed/gray lines.
 */
function ConnectionLines({ arms }) {
    if (!arms || arms.length === 0) return null;

    const lineHeight = 40;
    const width = arms.length * 120;

    return html`
        <div class="connection-lines-container">
            <svg
                class="connection-lines-svg"
                width=${width}
                height=${lineHeight}
                viewBox="0 0 ${width} ${lineHeight}"
            >
                ${arms.map((arm, i) => {
                    const connectivity = arm.connectivity || (arm.connected ? "connected" : "offline");
                    const x = (i + 0.5) * (width / arms.length);
                    const strokeColor = connectivity === "offline" ? "#6b7280"
                        : connectivity === "stale" ? "#f59e0b"
                        : "#22c55e";
                    const dashArray = connectivity === "offline" ? "4,4"
                        : connectivity === "stale" ? "6,3"
                        : "none";
                    return html`
                        <line
                            x1=${width / 2} y1="0"
                            x2=${x} y2=${lineHeight}
                            stroke=${strokeColor}
                            stroke-width="2"
                            stroke-dasharray=${dashArray}
                        />
                    `;
                })}
            </svg>
        </div>
    `;
}

/**
 * Detail panel for a single arm.
 */
function ArmDetailPanel({ data, armId, loading, error, onClose }) {
    if (!data && !loading && !error) return null;

    return html`
        <div class="arm-detail-card">
            <div class="arm-detail-header">
                <h3>Arm ${armId} Details</h3>
                <button class="btn btn-sm" onClick=${onClose}>\u00D7</button>
            </div>
            ${loading && html`<div class="loading">Loading arm details...</div>`}
            ${error && html`<div class="empty-state">Error: ${error}</div>`}
            ${data && !loading && !error && html`
                <div class="arm-detail-info">
                    <div class="arm-info-row">
                        <span class="arm-info-label">State:</span>
                        <span class="arm-info-value">${data.state || "unknown"}</span>
                    </div>
                    <div class="arm-info-row">
                        <span class="arm-info-label">Connectivity:</span>
                        <span class="arm-info-value">
                            ${data.connectivity || (data.connected ? "Connected" : "Disconnected")}
                        </span>
                    </div>
                    <div class="arm-info-row">
                        <span class="arm-info-label">Cotton Count:</span>
                        <span class="arm-info-value">
                            ${data.cotton_count != null ? data.cotton_count : "--"}
                        </span>
                    </div>
                    <div class="arm-info-row">
                        <span class="arm-info-label">Temperature:</span>
                        <span class="arm-info-value">
                            ${data.temperature_c != null ? data.temperature_c + "°C" : "--"}
                        </span>
                    </div>
                    <div class="arm-info-row">
                        <span class="arm-info-label">IP Address:</span>
                        <span class="arm-info-value">
                            ${data.ip || data.address || "--"}
                        </span>
                    </div>
                    <div class="arm-info-row">
                        <span class="arm-info-label">Uptime:</span>
                        <span class="arm-info-value">${data.uptime || "--"}</span>
                    </div>
                    <div class="arm-info-row">
                        <span class="arm-info-label">Last Heartbeat:</span>
                        <span class="arm-info-value">
                            ${data.last_heartbeat
                                ? formatHeartbeat(data.last_heartbeat)
                                : "Never"}
                        </span>
                    </div>
                </div>
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function MultiArmTab() {
    const { showToast } = useToast();
    const { dialog, confirm } = useConfirmDialog();

    // -- fleet state --------------------------------------------------------
    const [arms, setArms] = useState([]);
    const [vehicle, setVehicle] = useState(null);
    const [mqttConnected, setMqttConnected] = useState(false);
    const [loading, setLoading] = useState(true);
    const [restartingArms, setRestartingArms] = useState({});

    // -- detail panel state -------------------------------------------------
    const [detailArmId, setDetailArmId] = useState(null);
    const [detailData, setDetailData] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailError, setDetailError] = useState(null);

    // -- refs for cleanup ---------------------------------------------------
    const mountedRef = useRef(true);
    const wsRef = useRef(null);
    const reconnectRef = useRef(null);

    // ---- data loading -----------------------------------------------------

    const loadArms = useCallback(async () => {
        try {
            const data = await safeFetch("/api/arms");

            if (!mountedRef.current) return;

            if (data && typeof data === "object" && !Array.isArray(data)) {
                // Backend returns dict keyed by arm_id — convert to array
                const armArray = Object.entries(data).map(([id, armData]) => ({
                    arm_id: id,
                    ...armData,
                }));
                setArms(armArray);
            } else if (data && Array.isArray(data)) {
                setArms(data);
            } else if (data && data.arms && Array.isArray(data.arms)) {
                setArms(data.arms);
            } else {
                setArms([]);
            }

            setLoading(false);
        } catch (_err) {
            if (mountedRef.current) setLoading(false);
        }
    }, []);

    const loadMqttStatus = useCallback(async () => {
        try {
            const data = await safeFetch("/api/mqtt/status");
            if (!mountedRef.current || !data) return;

            setMqttConnected(!!data.connected);
            if (data.vehicle) {
                setVehicle(data.vehicle);
            }
        } catch (_err) {
            // Ignore
        }
    }, []);

    // ---- WebSocket for real-time arm status --------------------------------

    const connectWs = useCallback(() => {
        // Close any existing connection
        if (wsRef.current) {
            wsRef.current.onmessage = null;
            wsRef.current.onerror = null;
            wsRef.current.onclose = null;
            wsRef.current.close();
            wsRef.current = null;
        }

        const wsHost = window.location.host;
        const wsUrl = `ws://${wsHost}/ws/arms/status`;

        try {
            const ws = new WebSocket(wsUrl);

            ws.onmessage = (event) => {
                if (!mountedRef.current) return;
                try {
                    const msg = JSON.parse(event.data);

                    // Snapshot — full arm dict from backend
                    if (msg.type === "snapshot" && msg.arms) {
                        const armMap = msg.arms;
                        if (typeof armMap === "object" && !Array.isArray(armMap)) {
                            const armArray = Object.entries(armMap).map(([id, d]) => ({
                                arm_id: id,
                                ...d,
                            }));
                            setArms(armArray);
                        } else if (Array.isArray(armMap)) {
                            setArms(armMap);
                        }
                    }

                    // Single arm change
                    if (msg.type === "change" && msg.arm_id) {
                        setArms((prev) => {
                            const idx = prev.findIndex(
                                (a) => (a.arm_id || a.id) === msg.arm_id
                            );
                            if (idx >= 0) {
                                const updated = [...prev];
                                updated[idx] = { ...updated[idx], ...msg.data };
                                return updated;
                            }
                            return [...prev, { arm_id: msg.arm_id, ...msg.data }];
                        });
                    }

                    // Arm status broadcast from MQTT bridge
                    if (msg.type === "arm_status" && msg.arm_id) {
                        setArms((prev) => {
                            const idx = prev.findIndex(
                                (a) => (a.arm_id || a.id) === msg.arm_id
                            );
                            const update = {
                                arm_id: msg.arm_id,
                                state: msg.state,
                                cotton_count: msg.cotton_count,
                                temperature_c: msg.temperature_c,
                                connectivity: msg.connectivity,
                                connected: msg.connected,
                                last_heartbeat: msg.last_heartbeat,
                            };
                            if (idx >= 0) {
                                const updated = [...prev];
                                updated[idx] = { ...updated[idx], ...update };
                                return updated;
                            }
                            return [...prev, update];
                        });

                        // Check if a restarting arm has come back
                        setRestartingArms((prev) => {
                            if (prev[msg.arm_id] && msg.connectivity === "connected") {
                                const next = { ...prev };
                                delete next[msg.arm_id];
                                return next;
                            }
                            return prev;
                        });
                    }

                    // MQTT connection status
                    if (msg.type === "mqtt_status") {
                        setMqttConnected(!!msg.mqtt_connected);
                    }

                    // Vehicle status
                    if (msg.type === "vehicle_status") {
                        setVehicle(msg);
                    }

                    // Legacy compat
                    if (msg.mqtt_connected !== undefined && msg.type !== "mqtt_status") {
                        setMqttConnected(!!msg.mqtt_connected);
                    }
                } catch (_e) {
                    // Ignore parse errors
                }
            };

            ws.onerror = () => {
                // onerror is always followed by onclose
            };

            ws.onclose = () => {
                wsRef.current = null;
                if (mountedRef.current) {
                    reconnectRef.current = setTimeout(
                        connectWs,
                        WS_RECONNECT_DELAY
                    );
                }
            };

            wsRef.current = ws;
        } catch (_err) {
            // WebSocket construction failed — will rely on polling
        }
    }, []);

    // ---- arm commands ------------------------------------------------------

    const viewArmDetails = useCallback(
        async (armId) => {
            setDetailArmId(armId);
            setDetailLoading(true);
            setDetailError(null);
            setDetailData(null);

            try {
                const data = await safeFetch(
                    `/api/arms/${encodeURIComponent(armId)}`
                );

                if (!mountedRef.current) return;

                if (!data) {
                    setDetailError("Failed to load arm details");
                } else {
                    setDetailData(data);
                }
            } catch (err) {
                if (mountedRef.current) {
                    setDetailError(err.message);
                }
            } finally {
                if (mountedRef.current) setDetailLoading(false);
            }
        },
        []
    );

    const restartArm = useCallback(
        async (armId) => {
            // Find the arm to check connectivity for confirmation wording
            const arm = arms.find((a) => (a.arm_id || a.id) === armId);
            const isOffline = arm && arm.connectivity === "offline";
            const message = isOffline
                ? `Arm "${armId}" is offline. Attempt restart? This may not succeed if the arm is unreachable.`
                : `Restart arm "${armId}"? This will briefly interrupt arm operations.`;

            const confirmed = await confirm({
                title: "Restart Arm",
                message,
                confirmText: "Restart",
                dangerous: true,
            });
            if (!confirmed) return;

            // Mark as restarting (task 6.6)
            setRestartingArms((prev) => ({ ...prev, [armId]: true }));

            try {
                const result = await safeFetch(
                    `/api/arms/${encodeURIComponent(armId)}/command`,
                    {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ command: "restart" }),
                    }
                );

                if (result && !result.error) {
                    showToast(`Arm ${armId} restart requested`, "success");

                    // 30s timeout for restart
                    setTimeout(() => {
                        setRestartingArms((prev) => {
                            if (prev[armId]) {
                                showToast(
                                    `Arm ${armId} restart timed out (30s)`,
                                    "warning"
                                );
                                const next = { ...prev };
                                delete next[armId];
                                return next;
                            }
                            return prev;
                        });
                    }, RESTART_TIMEOUT_MS);
                } else {
                    setRestartingArms((prev) => {
                        const next = { ...prev };
                        delete next[armId];
                        return next;
                    });
                    showToast(
                        (result && result.error) ||
                            `Failed to restart arm ${armId}`,
                        "error"
                    );
                }
            } catch (err) {
                setRestartingArms((prev) => {
                    const next = { ...prev };
                    delete next[armId];
                    return next;
                });
                showToast("Failed to restart arm: " + err.message, "error");
            }
        },
        [arms, confirm, showToast]
    );

    const estopArm = useCallback(
        async (armId) => {
            // No confirmation — safety critical, must be instant
            try {
                const result = await safeFetch(
                    `/api/arms/${encodeURIComponent(armId)}/command`,
                    {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ command: "estop" }),
                    }
                );

                if (result && !result.error) {
                    showToast(`E-STOP sent to arm ${armId}`, "warning");
                } else {
                    showToast(
                        (result && result.error) ||
                            `Failed to E-STOP arm ${armId}`,
                        "error"
                    );
                }
            } catch (err) {
                showToast("Failed to E-STOP arm: " + err.message, "error");
            }
        },
        [showToast]
    );

    const closeDetail = useCallback(() => {
        setDetailArmId(null);
        setDetailData(null);
        setDetailError(null);
        setDetailLoading(false);
    }, []);

    // ---- lifecycle ---------------------------------------------------------

    // Initial load + WebSocket connect
    useEffect(() => {
        mountedRef.current = true;
        loadArms();
        loadMqttStatus();
        connectWs();

        return () => {
            mountedRef.current = false;

            // Clean up WebSocket
            if (wsRef.current) {
                wsRef.current.onmessage = null;
                wsRef.current.onerror = null;
                wsRef.current.onclose = null;
                wsRef.current.close();
                wsRef.current = null;
            }

            // Clean up reconnect timer
            if (reconnectRef.current) {
                clearTimeout(reconnectRef.current);
                reconnectRef.current = null;
            }
        };
    }, [loadArms, loadMqttStatus, connectWs]);

    // Polling — 3-second interval with cleanup
    useEffect(() => {
        const id = setInterval(() => {
            loadArms();
            loadMqttStatus();
        }, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [loadArms, loadMqttStatus]);

    // ---- render ------------------------------------------------------------

    return html`
        <div class="fleet-overview-header">
            <h2>Multi-Arm Fleet</h2>
            <${MqttIndicator} connected=${mqttConnected} />
        </div>

        <${VehicleHubCard}
            vehicle=${vehicle}
            mqttConnected=${mqttConnected}
        />

        <${ConnectionLines} arms=${arms} />

        ${!mqttConnected ? html`
            <div class="no-broker-banner" style="background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--spacing-lg); text-align: center; margin-bottom: var(--spacing-md);">
                <div style="font-size: 1.5rem; margin-bottom: var(--spacing-sm);">&#x2139;&#xFE0F;</div>
                <div style="color: var(--text-primary); font-weight: 500; margin-bottom: var(--spacing-xs);">Multi-arm coordination is unavailable</div>
                <div style="color: var(--text-secondary); font-size: 0.875rem;">MQTT broker not connected. Arm status will appear when the broker is available.</div>
            </div>
        ` : ""}

        <div class="fleet-arm-cards" id="arm-cards-container">
            ${loading && html`<div class="loading">Loading arms...</div>`}
            ${!loading && arms.length === 0 && html`
                <div class="empty-state">No arms detected</div>
            `}
            ${!loading && arms.map(
                (arm) => {
                    const armId = arm.arm_id || arm.id || "unknown";
                    return html`
                        <${ArmCard}
                            key=${armId}
                            arm=${arm}
                            onDetails=${viewArmDetails}
                            onRestart=${restartArm}
                            onEstop=${estopArm}
                            isRestarting=${!!restartingArms[armId]}
                        />
                    `;
                }
            )}
        </div>

        ${detailArmId != null && html`
            <${ArmDetailPanel}
                data=${detailData}
                armId=${detailArmId}
                loading=${detailLoading}
                error=${detailError}
                onClose=${closeDetail}
            />
        `}

        ${dialog}
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("multi-arm", MultiArmTab);

export {
    MultiArmTab,
    ArmCard,
    ArmDetailPanel,
    MqttIndicator,
    VehicleHubCard,
    ConnectionLines,
    formatHeartbeat,
    stateClass,
};
