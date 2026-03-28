/**
 * NodesTab — Preact component for the ROS2 Nodes tab.
 *
 * Migrated from vanilla JS as part of the incremental Preact migration
 * (task 6.1 of dashboard-frontend-migration).
 *
 * @module tabs/NodesTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useContext, useRef } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { WebSocketContext } from "../app.js";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5000;

/**
 * Patterns that classify a node as infrastructure (not user-facing).
 * @type {string[]}
 */
const INFRA_PATTERNS = [
    "robot_state_publisher",
    "joint_state_publisher",
    "transform_listener",
    "parameter_bridge",
    "_ros2cli_",
    "rviz",
    "rqt_",
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Classify a node name as 'infra' or 'main'.
 * @param {string} name
 * @returns {'infra'|'main'}
 */
function classifyNode(name) {
    const lower = (name || "").toLowerCase();
    for (const pattern of INFRA_PATTERNS) {
        if (lower.includes(pattern)) return "infra";
    }
    return "main";
}

/**
 * Determine the CSS color class for a metric bar based on percentage.
 * @param {number} pct - Percentage value (0-100)
 * @returns {string} CSS class name ('high', 'medium', or '')
 */
function metricBarClass(pct) {
    if (pct > 80) return "high";
    if (pct > 50) return "medium";
    return "";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * A single node card.
 *
 * @param {object} props
 * @param {string} props.name           - Node name
 * @param {object} props.node           - Node data from API
 * @param {string} props.category       - 'main' or 'infra'
 * @param {number} props.totalMemoryMb  - Total system memory for percentage calc
 */
function NodeCard({ name, node, category, totalMemoryMb }) {
    const status = (node.status || "unknown").toLowerCase();
    const healthPct = node.health && node.health.health_percentage != null
        ? Number(node.health.health_percentage)
        : 0;
    const cpuPct = node.cpu_percent != null ? Number(node.cpu_percent) : 0;
    const memoryMb = node.memory_mb != null ? Number(node.memory_mb) : 0;
    const memoryPct = totalMemoryMb > 0
        ? Math.min(100, (memoryMb / totalMemoryMb) * 100)
        : 0;

    return html`
        <div class="node-card" data-category=${category}>
            <div class="node-header">
                <div class="node-name">${name}</div>
                <span class="node-lifecycle-badge ${status}">${status}</span>
            </div>
            <div class="node-health-bar">Health: ${healthPct.toFixed(0)}%</div>
            <div class="node-metrics">
                <div class="metric-row">
                    <span class="metric-label">CPU</span>
                    <span class="metric-value">${cpuPct.toFixed(1)}%</span>
                </div>
                <div class="metric-bar">
                    <div
                        class="metric-bar-fill ${metricBarClass(cpuPct)}"
                        style=${{ width: `${Math.min(100, cpuPct)}%` }}
                    ></div>
                </div>
                <div class="metric-row">
                    <span class="metric-label">Memory</span>
                    <span class="metric-value">${memoryMb.toFixed(1)} MB</span>
                </div>
                <div class="metric-bar">
                    <div
                        class="metric-bar-fill ${metricBarClass(memoryPct)}"
                        style=${{ width: `${Math.min(100, memoryPct)}%` }}
                    ></div>
                </div>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function NodesTab() {
    const { data: wsData } = useContext(WebSocketContext);
    const systemState = wsData ? wsData.system_state : null;
    const ros2Available = systemState ? systemState.ros2_available : null;
    const isInitializing = systemState === null || systemState === undefined;

    const { showToast } = useToast();

    /** @type {[Object<string, Object>, Function]} */
    const [nodes, setNodes] = useState({});
    const [loading, setLoading] = useState(true);
    /** @type {[string|null, Function]} */
    const [error, setError] = useState(null);
    const [searchQuery, setSearchQuery] = useState("");
    const [category, setCategory] = useState("main");
    /** @type {[{memory_used_mb: number, memory_available_mb: number}|null, Function]} */
    const [perfData, setPerfData] = useState(null);

    const mountedRef = useRef(true);

    // ---- data loading -----------------------------------------------------

    const loadNodes = useCallback(async () => {
        // Try lifecycle endpoint first, fall back to basic /api/nodes
        let nodeData = await safeFetch("/api/nodes/lifecycle");
        if (nodeData && nodeData.nodes) {
            nodeData = nodeData.nodes;
        } else {
            // Fallback
            const fallback = await safeFetch("/api/nodes");
            nodeData = fallback || {};
        }

        // Fetch performance summary for memory totals
        const perf = await safeFetch("/api/performance/summary");

        if (!mountedRef.current) return;

        setNodes(nodeData);
        if (perf && perf.system) {
            setPerfData(perf.system);
        }
        setError(null);
        setLoading(false);
    }, []);

    // ---- filtering --------------------------------------------------------

    /**
     * Get filtered node entries based on category and search query.
     * @returns {Array<[string, Object]>}
     */
    const getFilteredNodes = useCallback(() => {
        return Object.entries(nodes).filter(([name]) => {
            // Category filter
            if (category !== "all") {
                const nodeCategory = classifyNode(name);
                if (nodeCategory !== category) return false;
            }
            // Text search
            if (searchQuery) {
                return name.toLowerCase().includes(searchQuery.toLowerCase());
            }
            return true;
        });
    }, [nodes, category, searchQuery]);

    // ---- lifecycle --------------------------------------------------------

    // Initial load
    useEffect(() => {
        mountedRef.current = true;
        loadNodes();
        return () => {
            mountedRef.current = false;
        };
    }, [loadNodes]);

    // Polling — 5-second interval with cleanup
    useEffect(() => {
        const id = setInterval(() => {
            loadNodes();
        }, POLL_INTERVAL_MS);

        return () => {
            clearInterval(id);
        };
    }, [loadNodes]);

    // ---- derived data -----------------------------------------------------

    const filteredNodes = getFilteredNodes();
    const totalMemoryMb = perfData
        ? (perfData.memory_used_mb || 0) + (perfData.memory_available_mb || 0)
        : 0;

    // ---- render -----------------------------------------------------------

    if (isInitializing) {
        return html`
            <div class="section-header">
                <h2>ROS2 Nodes</h2>
            </div>
            <div class="initializing-placeholder" style=${{
                textAlign: 'center',
                padding: 'var(--spacing-xl)',
                color: 'var(--text-secondary)',
            }}>
                <div style=${{ fontSize: '1.2em', marginBottom: 'var(--spacing-sm)' }}>Initializing...</div>
                <div style=${{ fontSize: '0.9em', color: 'var(--text-muted)' }}>Waiting for system state</div>
            </div>
        `;
    }

    if (ros2Available === false) {
        return html`
            <div class="section-header">
                <h2>ROS2 Nodes</h2>
            </div>
            <div class="no-ros2-placeholder" style=${{
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--spacing-xl)',
                textAlign: 'center',
                color: 'var(--text-secondary)',
            }}>
                <div style=${{ fontSize: '2em', marginBottom: 'var(--spacing-sm)' }}>🔌</div>
                <div style=${{ fontSize: '1.1em', marginBottom: 'var(--spacing-xs)' }}>ROS2 daemon not connected</div>
                <div style=${{ fontSize: '0.9em', color: 'var(--text-muted)' }}>Node information requires an active ROS2 environment</div>
            </div>
        `;
    }

    return html`
        <div class="section-header">
            <h2>ROS2 Nodes</h2>
            <div class="section-actions">
                <select
                    id="node-category-filter"
                    class="category-filter"
                    value=${category}
                    onChange=${(e) => setCategory(e.target.value)}
                >
                    <option value="main" selected=${category === "main"}>Main Nodes</option>
                    <option value="infra">Infrastructure</option>
                    <option value="all">All Nodes</option>
                </select>
                <input
                    id="node-search"
                    class="search-input"
                    type="text"
                    placeholder="Search nodes..."
                    value=${searchQuery}
                    onInput=${(e) => setSearchQuery(e.target.value)}
                />
            </div>
        </div>
        <div id="nodes-container" class="nodes-grid">
            ${loading && html`<div class="loading">Loading nodes...</div>`}
            ${error && html`<div class="error-state">${error}</div>`}
            ${!loading && !error && filteredNodes.length === 0 && html`
                <div class="empty-state">No nodes found</div>
            `}
            ${!loading && !error && filteredNodes.map(
                ([name, node]) => html`
                    <${NodeCard}
                        key=${name}
                        name=${name}
                        node=${node}
                        category=${classifyNode(name)}
                        totalMemoryMb=${totalMemoryMb}
                    />
                `
            )}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("nodes", NodesTab);

export { NodesTab, classifyNode, metricBarClass, INFRA_PATTERNS };
