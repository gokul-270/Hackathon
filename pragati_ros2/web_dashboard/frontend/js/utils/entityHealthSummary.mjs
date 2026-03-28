/**
 * entityHealthSummary — Shared entity health derivation utilities.
 *
 * Extracted from StatusHealthTab.mjs (Design Decision D1) so both EntityCard.mjs
 * and StatusHealthTab.mjs consume the same health logic from one source of truth.
 *
 * Exports:
 * - deriveCardHealthSummary(entityData) — compact card-level rollup
 * - deriveSubsystemHealth(entityData) — full 5-subsystem breakdown
 * - isTimestampStale(timestamp, thresholdSeconds) — staleness check
 * - healthBadgeClass(status) — CSS class for health badge
 * - ENTITY_STALE_THRESHOLD_S, CAN_STALE_THRESHOLD_S, THRESHOLDS, SUBSYSTEMS
 *
 * @module utils/entityHealthSummary
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Staleness thresholds for UNAVAILABLE detection.
 * CAN bus: no messages within this many seconds → UNAVAILABLE.
 * Entity: last_seen older than this many seconds → UNAVAILABLE.
 */
export const CAN_STALE_THRESHOLD_S = 10;
export const ENTITY_STALE_THRESHOLD_S = 30;

/** Threshold bands for gauges. */
export const THRESHOLDS = {
    cpu: { warning: 70, critical: 90 },
    memory: { warning: 80, critical: 95 },
    temp: { warning: 65, critical: 80 },
    disk: { warning: 70, critical: 90 },
};

/**
 * Subsystem definitions for per-subsystem health display.
 * @type {Array<{key: string, label: string, icon: string, ros2Dependent: boolean}>}
 */
export const SUBSYSTEMS = [
    { key: "system", label: "System", icon: "\uD83D\uDCBB", ros2Dependent: false },
    { key: "ros2", label: "ROS2", icon: "\uD83D\uDD27", ros2Dependent: true },
    { key: "motors", label: "Motors", icon: "\u2699\uFE0F", ros2Dependent: true },
    { key: "can_bus", label: "CAN Bus", icon: "\uD83D\uDD0C", ros2Dependent: true },
    { key: "services", label: "Services", icon: "\uD83D\uDCE6", ros2Dependent: false },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Check whether a timestamp is stale (older than thresholdSeconds from now).
 * Returns true if the timestamp is null/undefined or older than the threshold.
 * @param {string|number|null|undefined} timestamp - ISO string, epoch ms, or epoch seconds
 * @param {number} thresholdSeconds
 * @returns {boolean}
 */
export function isTimestampStale(timestamp, thresholdSeconds) {
    if (timestamp == null) return true;
    let epochMs;
    if (typeof timestamp === "string") {
        epochMs = new Date(timestamp).getTime();
    } else if (typeof timestamp === "number") {
        // Heuristic: if < 1e12, it's epoch seconds; otherwise epoch ms
        epochMs = timestamp < 1e12 ? timestamp * 1000 : timestamp;
    } else {
        return true;
    }
    if (isNaN(epochMs)) return true;
    return (Date.now() - epochMs) / 1000 > thresholdSeconds;
}

/**
 * CSS class for subsystem health status badge.
 * Maps the 4-state health model to CSS classes:
 *   healthy     → health-ok (green)
 *   degraded    → health-unknown (amber)
 *   error       → health-error (red)
 *   unavailable → health-unavailable (grey)
 *
 * @param {string} status
 * @returns {string}
 */
export function healthBadgeClass(status) {
    const s = (status || "unavailable").toLowerCase();
    if (s === "healthy") return "health-ok";
    if (s === "degraded") return "health-unknown";
    if (s === "error") return "health-error";
    if (s === "unavailable") return "health-unavailable";
    return "health-unavailable"; // unknown / fallback
}

/**
 * Derive per-subsystem health status from entity data.
 *
 * IMPORTANT — Frontend is the single source of truth for dashboard health
 * presentation thresholds. Backend thresholds in health_monitoring_service.py
 * (e.g. temp >70 = CRITICAL) serve local RPi alerting only and are
 * intentionally different from the values here. Do NOT synchronise them.
 *
 * UNAVAILABLE precedence: if we have no current data for a subsystem,
 * any threshold evaluation is meaningless (e.g. temp=0 from a disconnected
 * motor is not "healthy"). UNAVAILABLE checks therefore run BEFORE metric
 * threshold evaluation. The check order is:
 *   1. Is last_update / last message timestamp null? → UNAVAILABLE
 *   2. Is data stale (age exceeds timeout)?          → UNAVAILABLE
 *   3. Evaluate metric thresholds                    → healthy/degraded/error
 *
 * @param {object|null} entityData - Full entity data
 * @returns {Object<string, string>}
 */
export function deriveSubsystemHealth(entityData) {
    if (!entityData) {
        return {
            system: "unavailable",
            ros2: "unavailable",
            motors: "unavailable",
            can_bus: "unavailable",
            services: "unavailable",
        };
    }

    const health = {};

    // --- Entity-level UNAVAILABLE check ---
    const entityOffline =
        (entityData.status || "").toLowerCase() === "offline";
    const entityStale = isTimestampStale(
        entityData.last_seen,
        ENTITY_STALE_THRESHOLD_S
    );

    if (entityOffline || entityStale) {
        return {
            system: "unavailable",
            ros2: "unavailable",
            motors: "unavailable",
            can_bus: "unavailable",
            services: "unavailable",
        };
    }

    // --- System health: based on metrics thresholds ---
    const m = entityData.system_metrics;
    if (m) {
        if (m.cpu_percent > 90 || m.memory_percent > 95 || m.temperature_c > 80) {
            health.system = "error";
        } else if (
            m.cpu_percent > 70 ||
            m.memory_percent > 80 ||
            m.temperature_c > 65
        ) {
            health.system = "degraded";
        } else {
            health.system = "healthy";
        }
    } else {
        health.system = "unavailable";
    }

    // --- ROS2 health: depends on ros2_available ---
    if (entityData.ros2_available === false) {
        health.ros2 = "unavailable";
    } else if (entityData.ros2_state) {
        const nodeCount = entityData.ros2_state.node_count || 0;
        health.ros2 = nodeCount > 0 ? "healthy" : "degraded";
    } else {
        health.ros2 = "unavailable";
    }

    // --- Motors: UNAVAILABLE if last_update is null/stale ---
    if (entityData.ros2_available === false) {
        health.motors = "unavailable";
    } else {
        const motors = entityData.motors || [];
        if (motors.length > 0) {
            const allUnavailable = motors.every(
                (motor) => motor.last_update == null
            );
            if (allUnavailable) {
                health.motors = "unavailable";
            } else {
                const motorErrors = (entityData.errors || []).filter(
                    (e) => (e.subsystem || "").toLowerCase() === "motors"
                );
                health.motors =
                    motorErrors.length > 0 ? "error" : "healthy";
            }
        } else {
            const motorErrors = (entityData.errors || []).filter(
                (e) => (e.subsystem || "").toLowerCase() === "motors"
            );
            health.motors =
                motorErrors.length > 0 ? "error" : "healthy";
        }
    }

    // --- CAN Bus: UNAVAILABLE if no messages within CAN_STALE_THRESHOLD_S ---
    if (entityData.ros2_available === false) {
        health.can_bus = "unavailable";
    } else {
        const canData = entityData.can_bus || {};
        const canLastMessage = canData.last_message_time || canData.last_message;
        if (isTimestampStale(canLastMessage, CAN_STALE_THRESHOLD_S)) {
            health.can_bus = "unavailable";
        } else {
            const canErrors = (entityData.errors || []).filter(
                (e) => (e.subsystem || "").toLowerCase() === "can_bus"
            );
            health.can_bus = canErrors.length > 0 ? "error" : "healthy";
        }
    }

    // --- Services: based on systemd service states ---
    const svcs = entityData.services || [];
    if (svcs.length === 0) {
        health.services = "unavailable";
    } else {
        const failedCount = svcs.filter(
            (s) => (s.active_state || "").toLowerCase() === "failed"
        ).length;
        if (failedCount > 0) {
            health.services = failedCount === svcs.length ? "error" : "degraded";
        } else {
            health.services = "healthy";
        }
    }

    return health;
}

// ---------------------------------------------------------------------------
// Card-level health summary (Design Decisions D2, D3, D4)
// ---------------------------------------------------------------------------

/** Health state severity for worst-state comparison. Higher = worse. */
const HEALTH_SEVERITY = {
    online: 0,
    healthy: 0,
    degraded: 1,
    unknown: 1,
    error: 2,
    offline: 2,
    unreachable: 2,
    unavailable: 3,
};

function mapLayerStatus(layerKey, value) {
    const normalized = (value || "unknown").toLowerCase();
    if (layerKey === "mqtt" && normalized === "disabled") {
        return "na";
    }
    if (["reachable", "alive", "active", "healthy", "online", "local"].includes(normalized)) {
        return "healthy";
    }
    if (["degraded", "stale", "initializing", "unknown", "broker_down"].includes(normalized)) {
        return "degraded";
    }
    if (["down", "offline", "unreachable", "error"].includes(normalized)) {
        return "error";
    }
    return "degraded";
}

/**
 * Derive a compact card-level health summary from entity data.
 *
 * Returns an object with:
 *   - overall:  worst state among System, ROS2, Services (D3).
 *               Unavailable wins for stale/offline entities.
 *   - system:   system subsystem health
 *   - ros2:     ros2 subsystem health
 *   - services: services subsystem health
 *   - issueCue: single-line issue text or null (D4).
 *               Priority: explicit error > stale/offline > service failure > subsystem degradation.
 *
 * @param {object|null} entityData - Full entity data from API/WebSocket
 * @returns {{ overall: string, system: string, ros2: string, services: string, issueCue: string|null }}
 */
export function deriveCardHealthSummary(entityData) {
    if (!entityData) {
        return {
            overall: "unavailable",
            layers: [],
            diagnostic: null,
        };
    }

    const backendHealth = entityData.health || {};
    const layers = [
        { key: "network", label: "PING", raw: backendHealth.network },
        { key: "agent", label: "AGT", raw: backendHealth.agent },
        { key: "mqtt", label: "MQTT", raw: backendHealth.mqtt },
        { key: "ros2", label: "ROS2", raw: backendHealth.ros2 },
    ].map((layer) => ({
        ...layer,
        status: mapLayerStatus(layer.key, layer.raw),
        tooltip: layer.key === "mqtt" && (layer.raw || "").toLowerCase() === "disabled"
            ? "N/A"
            : String(layer.raw || "unknown"),
    }));

    return {
        overall: (backendHealth.composite || entityData.status || "unknown").toLowerCase(),
        layers,
        diagnostic: backendHealth.diagnostic || null,
    };
}
