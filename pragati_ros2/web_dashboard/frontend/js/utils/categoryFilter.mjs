/**
 * Category filter utility for Nodes, Topics, and Services sub-tabs.
 *
 * Categories:
 *   - "all"       : No filter (show everything)
 *   - "pragati"   : Pragati Core nodes/topics/services
 *   - "dashboard" : Dashboard backend nodes/topics/services
 *   - "system"    : Everything else (ROS2 infra, rosout, parameter_events, etc.)
 */
import { html } from "htm/preact";

// ---------------------------------------------------------------------------
// Node name patterns
// ---------------------------------------------------------------------------

/** Pragati production node names (exact match after stripping namespace). */
const PRAGATI_NODE_NAMES = new Set([
    "motor_control",
    "cotton_detection_node",
    "yanthra_move",
    "arm_client_node",
    "vehicle_motor_control",
    "vehicle_control_node",
    "odrive_service_node",
    "vehicle_mqtt_bridge",
    "robot_state_publisher",
    "joint_state_publisher",
]);

/** Prefixes that identify dashboard-backend nodes. */
const DASHBOARD_NODE_PREFIXES = [
    "web_dashboard_",
    "motor_config_api_bridge",
    "pid_tuning_api_bridge",
];

// ---------------------------------------------------------------------------
// Topic / service name patterns
// ---------------------------------------------------------------------------

/** Topic/service substrings considered Pragati Core.
 * Matched with `includes()` so namespaced names like
 * `/arm1/motor_state` or `/vehicle1/cmd_vel` are caught.
 */
const PRAGATI_TOPIC_SUBSTRINGS = [
    "/motor_",
    "/joint_",
    "/cotton_",
    "/vehicle_",
    "/odrive_",
    "/cmd_vel",
    "/tf",
    "/robot_description",
    "/yanthra_",
    "/status",
    "/emergency_stop",
    "/mqtt_",
];

/** Namespace regex patterns that indicate Pragati entities. */
const PRAGATI_NAMESPACE_RE = /^\/(arm[0-9]+|vehicle[0-9]*|yanthra_move)\//;

/** Topic/service prefixes considered Dashboard. */
const DASHBOARD_TOPIC_PREFIXES = [
    "/web_dashboard",
    "/dashboard_",
    "/pid_tuning",
    "/motor_config_api",
];

// ---------------------------------------------------------------------------
// Classification helpers
// ---------------------------------------------------------------------------

/** Strip leading namespace (e.g. "/ns/node" -> "node"). */
function baseName(fullName) {
    if (!fullName) return "";
    const parts = fullName.split("/").filter(Boolean);
    return parts[parts.length - 1] || fullName;
}

/**
 * Classify a **node** name into a category.
 * @param {string} name - Fully qualified node name (e.g. "/motor_control")
 * @returns {"pragati"|"dashboard"|"system"}
 */
export function classifyNode(name) {
    const base = baseName(name);
    if (PRAGATI_NODE_NAMES.has(base)) return "pragati";
    for (const pfx of DASHBOARD_NODE_PREFIXES) {
        if (base.startsWith(pfx)) return "dashboard";
    }
    return "system";
}

/**
 * Classify a **topic or service** name into a category.
 * Uses `includes()` for pragati substrings so namespaced names
 * like `/arm1/motor_state` are correctly classified.
 * @param {string} name - Fully qualified topic/service name
 * @returns {"pragati"|"dashboard"|"system"}
 */
export function classifyTopicOrService(name) {
    if (!name) return "system";
    for (const pfx of DASHBOARD_TOPIC_PREFIXES) {
        if (name.startsWith(pfx)) return "dashboard";
    }
    // Check namespace pattern first (e.g. /arm1/..., /vehicle1/...)
    if (PRAGATI_NAMESPACE_RE.test(name)) return "pragati";
    for (const sub of PRAGATI_TOPIC_SUBSTRINGS) {
        if (name.includes(sub)) return "pragati";
    }
    return "system";
}

/**
 * Apply category filter to an array of items.
 * @param {Array} items   - Array of objects with a `.name` property
 * @param {string} category - "all" | "pragati" | "dashboard" | "system"
 * @param {function} classifyFn - classifyNode or classifyTopicOrService
 * @returns {Array} filtered items
 */
export function filterByCategory(items, category, classifyFn) {
    if (category === "all") return items;
    return items.filter((item) => classifyFn(item.name) === category);
}

// ---------------------------------------------------------------------------
// UI Component
// ---------------------------------------------------------------------------

const CATEGORIES = [
    { key: "all", label: "All" },
    { key: "pragati", label: "Pragati" },
    { key: "dashboard", label: "Dashboard" },
    { key: "system", label: "System" },
];

const barStyle = {
    display: "flex",
    gap: "6px",
    marginBottom: "8px",
};

function btnStyle(active) {
    return {
        padding: "4px 12px",
        border: active ? "1px solid #58a6ff" : "1px solid #444",
        borderRadius: "4px",
        background: active ? "#1a3a5c" : "transparent",
        color: active ? "#58a6ff" : "#aaa",
        cursor: "pointer",
        fontSize: "12px",
        fontWeight: active ? "600" : "400",
        transition: "all 0.15s ease",
    };
}

/**
 * Preact component: a row of toggle buttons for category filtering.
 *
 * Props:
 *   - active {string}       Current category key
 *   - onChange {function}    Called with new category key
 *   - counts {object|null}  Optional { all, pragati, dashboard, system } counts
 */
export function CategoryFilterBar({ active, onChange, counts }) {
    return html`
        <div style=${barStyle}>
            ${CATEGORIES.map(
                (cat) => html`
                    <button
                        key=${cat.key}
                        style=${btnStyle(active === cat.key)}
                        onClick=${() => onChange(cat.key)}
                    >
                        ${cat.label}${counts
                            ? html`<span style=${{ opacity: 0.6, marginLeft: "4px" }}
                                  >(${counts[cat.key]})</span
                              >`
                            : null}
                    </button>
                `,
            )}
        </div>
    `;
}
