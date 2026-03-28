/**
 * NodesSubTab — Preact component for the ROS2 Nodes sub-tab within
 * an entity detail view.
 *
 * Features:
 *   - Node list with lifecycle state badges and 10s auto-refresh
 *   - Search filtering
 *   - Expandable node detail panel (publishers, subscribers, services, params)
 *   - Lifecycle transition controls (state-aware valid transitions)
 *   - Node restart via systemd service mapping
 *
 * @module tabs/entity/NodesSubTab
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useRef,
    useCallback,
    useMemo,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../../utils.js";
import { cachedEntityFetch } from "../../utils/cachedFetch.mjs";
import {
    CategoryFilterBar,
    classifyNode,
    filterByCategory,
} from "../../utils/categoryFilter.mjs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 10000;
const PAGE_SIZE = 50;

/**
 * Valid lifecycle transitions per state.
 * @type {Object<string, string[]>}
 */
const VALID_TRANSITIONS = {
    unconfigured: ["configure"],
    inactive: ["activate", "shutdown", "cleanup"],
    active: ["deactivate", "shutdown"],
    finalized: ["cleanup"],
};

/**
 * Badge colors for lifecycle states.
 * @type {Object<string, string>}
 */
const LIFECYCLE_COLORS = {
    active: "var(--color-success)",
    inactive: "var(--color-text-secondary)",
    unconfigured: "var(--color-warning)",
    finalized: "var(--color-error)",
};

/**
 * Button colors for lifecycle transitions.
 * @type {Object<string, string>}
 */
const TRANSITION_COLORS = {
    configure: "var(--color-accent)",
    activate: "var(--color-success)",
    deactivate: "var(--color-warning)",
    shutdown: "var(--color-error)",
    cleanup: "var(--color-text-secondary)",
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
    container: {
        display: "flex",
        flexDirection: "column",
        gap: "12px",
    },
    searchInput: {
        width: "100%",
        padding: "8px 12px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        fontSize: "14px",
        boxSizing: "border-box",
        background: "var(--color-bg-secondary)",
        color: "var(--color-text-primary)",
        outline: "none",
    },
    table: {
        width: "100%",
        borderCollapse: "collapse",
        fontSize: "14px",
    },
    th: {
        textAlign: "left",
        padding: "8px 12px",
        borderBottom: "2px solid var(--color-border)",
        fontWeight: "600",
        color: "var(--color-text-secondary)",
        backgroundColor: "var(--color-bg-secondary)",
    },
    td: {
        padding: "8px 12px",
        borderBottom: "1px solid var(--color-border)",
        verticalAlign: "middle",
        color: "var(--color-text-primary)",
    },
    clickableRow: {
        cursor: "pointer",
    },
    badge: (color) => ({
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "12px",
        fontSize: "12px",
        fontWeight: "600",
        color: "#fff",
        backgroundColor: color,
    }),
    detailPanel: {
        backgroundColor: "var(--color-bg-secondary)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        padding: "16px",
        margin: "0 12px 8px 12px",
    },
    detailSection: {
        marginBottom: "12px",
    },
    detailSectionTitle: {
        fontWeight: "600",
        fontSize: "13px",
        color: "var(--color-text-secondary)",
        marginBottom: "4px",
        borderBottom: "1px solid var(--color-border)",
        paddingBottom: "4px",
    },
    detailItem: {
        fontSize: "13px",
        padding: "2px 0",
        color: "var(--color-text-primary)",
        fontFamily: "monospace",
    },
    emptyDetail: {
        fontSize: "13px",
        color: "var(--color-text-muted)",
        fontStyle: "italic",
    },
    transitionBtn: (color) => ({
        padding: "3px 10px",
        fontSize: "12px",
        fontWeight: "500",
        border: "none",
        borderRadius: "3px",
        cursor: "pointer",
        color: "#fff",
        backgroundColor: color,
        marginRight: "4px",
        marginBottom: "4px",
    }),
    restartBtn: {
        padding: "3px 10px",
        fontSize: "12px",
        fontWeight: "500",
        border: "none",
        borderRadius: "3px",
        cursor: "pointer",
        color: "#fff",
        backgroundColor: "var(--color-warning)",
        marginRight: "4px",
    },
    restartBtnDisabled: {
        padding: "3px 10px",
        fontSize: "12px",
        fontWeight: "500",
        border: "none",
        borderRadius: "3px",
        cursor: "not-allowed",
        color: "var(--color-text-muted)",
        backgroundColor: "var(--color-bg-elevated)",
        marginRight: "4px",
        opacity: 0.6,
    },
    actionsCell: {
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "2px",
    },
    overlay: {
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
    },
    dialog: {
        backgroundColor: "var(--color-bg-surface)",
        borderRadius: "var(--radius-md)",
        padding: "24px",
        maxWidth: "400px",
        width: "90%",
        boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
        border: "1px solid var(--color-border)",
    },
    dialogTitle: {
        fontSize: "16px",
        fontWeight: "600",
        marginBottom: "12px",
        color: "var(--color-text-primary)",
    },
    dialogBody: {
        fontSize: "14px",
        color: "var(--color-text-secondary)",
        marginBottom: "20px",
    },
    dialogActions: {
        display: "flex",
        justifyContent: "flex-end",
        gap: "8px",
    },
    dialogCancel: {
        padding: "6px 16px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        backgroundColor: "var(--color-bg-tertiary)",
        color: "var(--color-text-primary)",
        cursor: "pointer",
        fontSize: "13px",
    },
    dialogConfirm: (color) => ({
        padding: "6px 16px",
        border: "none",
        borderRadius: "var(--radius-sm)",
        backgroundColor: color,
        color: "#fff",
        cursor: "pointer",
        fontSize: "13px",
        fontWeight: "500",
    }),
    loading: {
        textAlign: "center",
        padding: "24px",
        color: "var(--color-text-muted)",
    },
    emptyState: {
        textAlign: "center",
        padding: "24px",
        color: "var(--color-text-muted)",
    },
    unavailable: {
        textAlign: "center",
        padding: "24px",
        color: "var(--color-text-muted)",
        backgroundColor: "var(--color-bg-secondary)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
    },
    headerRow: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "8px",
    },
    nodeCount: {
        fontSize: "13px",
        color: "var(--color-text-muted)",
    },
    skeleton: {
        padding: "12px",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
    },
    skeletonRow: {
        height: "18px",
        borderRadius: "var(--radius-sm)",
        background: "linear-gradient(90deg, var(--color-bg-tertiary) 25%, var(--color-bg-secondary) 50%, var(--color-bg-tertiary) 75%)",
        backgroundSize: "200% 100%",
        animation: "shimmer 1.5s infinite",
    },
    staleBadge: {
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "var(--radius-sm)",
        fontSize: "11px",
        fontWeight: "600",
        color: "var(--color-warning)",
        backgroundColor: "rgba(245, 158, 11, 0.15)",
        marginLeft: "8px",
    },
    retryBtn: {
        padding: "6px 16px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        backgroundColor: "var(--color-bg-tertiary)",
        color: "var(--color-text-primary)",
        cursor: "pointer",
        fontSize: "13px",
    },
    errorState: {
        textAlign: "center",
        padding: "24px",
        color: "var(--color-error)",
    },
    paginationBar: {
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        gap: "12px",
        padding: "8px 0",
        fontSize: "13px",
        color: "var(--color-text-muted)",
    },
    pageBtn: {
        padding: "4px 12px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        backgroundColor: "var(--color-bg-surface)",
        color: "var(--color-text-primary)",
        cursor: "pointer",
        fontSize: "13px",
    },
    pageBtnDisabled: {
        padding: "4px 12px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        backgroundColor: "var(--color-bg-secondary)",
        cursor: "not-allowed",
        fontSize: "13px",
        color: "var(--color-text-muted)",
    },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Convert a ROS2 node name to a systemd service name.
 * "motion_controller" → "pragati-motion-controller"
 *
 * Returns null if the node name contains characters that make mapping
 * ambiguous (e.g. ros2cli internal nodes).
 *
 * @param {string} nodeName
 * @returns {string|null}
 */
function nodeToServiceName(nodeName) {
    if (!nodeName) return null;
    // Strip leading slash if present
    let name = nodeName.replace(/^\//, "");
    // Skip nodes that look like internal / infrastructure
    if (name.startsWith("_") || name.includes("ros2cli")) return null;
    // Replace underscores with hyphens, prepend "pragati-"
    const service = "pragati-" + name.replace(/_/g, "-");
    return service;
}

/**
 * Show a simple inline toast-like message. Since sub-tabs may not have
 * access to the app-level ToastContext, we fall back to console + a
 * temporary DOM element.
 */
function showSimpleToast(message, severity) {
    // Try to find existing toast container from the main app
    const existing = document.querySelector(".preact-toast-container");
    if (existing) {
        const toast = document.createElement("div");
        toast.className = `preact-toast preact-toast-${severity}`;
        toast.innerHTML =
            `<span>${message}</span>` +
            `<button class="toast-dismiss" style="margin-left:8px;cursor:pointer;border:none;background:none;font-size:16px;">\u00d7</button>`;
        existing.appendChild(toast);
        toast.querySelector("button").onclick = () => toast.remove();
        setTimeout(() => toast.remove(), 4000);
        return;
    }
    // Fallback: console
    if (severity === "error") {
        console.error(`[NodesSubTab] ${message}`);
    } else {
        console.log(`[NodesSubTab] ${message}`);
    }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Confirmation dialog overlay.
 */
function ConfirmDialog({ title, message, confirmLabel, confirmColor, onConfirm, onCancel }) {
    return html`
        <div style=${styles.overlay} onClick=${onCancel}>
            <div style=${styles.dialog} onClick=${(e) => e.stopPropagation()}>
                <div style=${styles.dialogTitle}>${title}</div>
                <div style=${styles.dialogBody}>${message}</div>
                <div style=${styles.dialogActions}>
                    <button style=${styles.dialogCancel} onClick=${onCancel}>
                        Cancel
                    </button>
                    <button
                        style=${styles.dialogConfirm(confirmColor || "var(--color-accent)")}
                        onClick=${onConfirm}
                    >
                        ${confirmLabel || "Confirm"}
                    </button>
                </div>
            </div>
        </div>
    `;
}

/**
 * Detail panel shown when a node row is expanded.
 */
function NodeDetailPanel({ detail, loading: isLoading }) {
    if (isLoading) {
        return html`
            <tr>
                <td colspan="4">
                    <div style=${styles.detailPanel}>
                        <div style=${styles.loading}>Loading node details...</div>
                    </div>
                </td>
            </tr>
        `;
    }

    if (!detail) {
        return html`
            <tr>
                <td colspan="4">
                    <div style=${styles.detailPanel}>
                        <div style=${styles.emptyDetail}>
                            Failed to load node details.
                        </div>
                    </div>
                </td>
            </tr>
        `;
    }

    const sections = [
        { key: "publishers", label: "Publishers", fields: ["topic", "type"] },
        { key: "subscribers", label: "Subscribers", fields: ["topic", "type"] },
        { key: "services", label: "Services", fields: ["name", "type"] },
        { key: "parameters", label: "Parameters", fields: ["name", "value"] },
    ];

    return html`
        <tr>
            <td colspan="4" style=${{ padding: 0 }}>
                <div style=${styles.detailPanel}>
                    ${sections.map(
                        (section) => html`
                            <div style=${styles.detailSection} key=${section.key}>
                                <div style=${styles.detailSectionTitle}>
                                    ${section.label}
                                    ${" "}(${(detail[section.key] || []).length})
                                </div>
                                ${(detail[section.key] || []).length === 0
                                    ? html`<div style=${styles.emptyDetail}>None</div>`
                                    : (detail[section.key] || []).map(
                                          (item, i) => html`
                                              <div style=${styles.detailItem} key=${i}>
                                                  ${section.fields
                                                      .map((f) => item[f] ?? "")
                                                      .join(" — ")}
                                              </div>
                                          `
                                      )}
                            </div>
                        `
                    )}
                </div>
            </td>
        </tr>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * NodesSubTab — entity-scoped ROS2 node list with detail, lifecycle
 * controls, and restart capability.
 *
 * @param {object} props
 * @param {string} props.entityId
 * @param {string} props.entitySource - "local" | "remote"
 * @param {string} props.entityIp
 * @param {boolean} props.ros2Available
 * @param {function} props.registerCleanup
 */
export default function NodesSubTab({
    entityId,
    entitySource,
    entityIp,
    ros2Available,
    registerCleanup,
}) {
    const [nodes, setNodes] = useState([]);
    const [searchFilter, setSearchFilter] = useState("");
    const [categoryFilter, setCategoryFilter] = useState("all");
    const [expandedNode, setExpandedNode] = useState(null);
    const [nodeDetail, setNodeDetail] = useState(null);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [showConfirm, setShowConfirm] = useState(null);
    const [loading, setLoading] = useState(true);
    const [stale, setStale] = useState(false);
    const [fetchError, setFetchError] = useState(false);
    const [currentPage, setCurrentPage] = useState(1);
    const mountedRef = useRef(true);
    const abortControllerRef = useRef(null);

    // ---- Data fetching ----------------------------------------------------

    const fetchNodes = useCallback(async (bypass = false) => {
        // Create a new AbortController for this fetch cycle
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        abortControllerRef.current = new AbortController();

        if (bypass) {
            setLoading(true);
            setFetchError(false);
            setStale(false);
        }

        const result = await cachedEntityFetch(entityId, "ros2/nodes", {
            signal: abortControllerRef.current.signal,
            bypassCache: bypass,
        });

        if (!mountedRef.current) return;

        if (result) {
            const data = result.data?.nodes || (Array.isArray(result.data) ? result.data : []);
            setNodes(data);
            setStale(result.stale);
            setFetchError(false);
            setCurrentPage(1);
        } else {
            // Total failure — no cache, no network
            if (nodes.length === 0) {
                setFetchError(true);
            }
        }
        setLoading(false);
    }, [entityId, nodes.length]);

    const fetchNodeDetail = useCallback(
        async (nodeName) => {
            setLoadingDetail(true);
            setNodeDetail(null);
            const result = await safeFetch(
                `/api/entities/${encodeURIComponent(entityId)}/ros2/nodes/${encodeURIComponent(nodeName)}`
            );
            if (!mountedRef.current) return;
            if (result) {
                // Unwrap envelope: result may be {data: {publishers:[], ...}} or direct detail
                const detail = result.data || result;
                // Normalize: ensure each section is an array
                setNodeDetail({
                    publishers: Array.isArray(detail.publishers) ? detail.publishers : [],
                    subscribers: Array.isArray(detail.subscribers) ? detail.subscribers : [],
                    services: Array.isArray(detail.services) ? detail.services : [],
                    parameters: Array.isArray(detail.parameters) ? detail.parameters : [],
                });
            }
            setLoadingDetail(false);
        },
        [entityId]
    );

    // ---- Lifecycle & polling ----------------------------------------------

    useEffect(() => {
        mountedRef.current = true;
        abortControllerRef.current = new AbortController();
        fetchNodes();

        const intervalId = setInterval(() => fetchNodes(false), POLL_INTERVAL_MS);

        const cleanup = () => {
            mountedRef.current = false;
            clearInterval(intervalId);
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };

        if (typeof registerCleanup === "function") {
            registerCleanup(cleanup);
        }

        return cleanup;
    }, [fetchNodes, registerCleanup]);

    // ---- Expand / collapse ------------------------------------------------

    const handleRowClick = useCallback(
        (nodeName) => {
            if (expandedNode === nodeName) {
                setExpandedNode(null);
                setNodeDetail(null);
            } else {
                setExpandedNode(nodeName);
                fetchNodeDetail(nodeName);
            }
        },
        [expandedNode, fetchNodeDetail]
    );

    // ---- Lifecycle transitions --------------------------------------------

    const handleLifecycleTransition = useCallback(
        async (nodeName, transition) => {
            const result = await safeFetch(
                `/api/entities/${encodeURIComponent(entityId)}/ros2/nodes/${encodeURIComponent(nodeName)}/lifecycle/${encodeURIComponent(transition)}`,
                { method: "POST" }
            );
            if (!mountedRef.current) return;
            if (result) {
                showSimpleToast(
                    `Lifecycle transition '${transition}' sent to ${nodeName}`,
                    "success"
                );
                fetchNodes();
                // Refresh detail if this node is expanded
                if (expandedNode === nodeName) {
                    fetchNodeDetail(nodeName);
                }
            } else {
                showSimpleToast(
                    `Failed to send '${transition}' to ${nodeName}`,
                    "error"
                );
            }
            setShowConfirm(null);
        },
        [entityId, expandedNode, fetchNodes, fetchNodeDetail]
    );

    // ---- Restart ----------------------------------------------------------

    const handleRestart = useCallback(
        async (nodeName) => {
            const serviceName = nodeToServiceName(nodeName);
            if (!serviceName) {
                showSimpleToast(
                    `Cannot determine service name for ${nodeName}`,
                    "error"
                );
                setShowConfirm(null);
                return;
            }
            const result = await safeFetch(
                `/api/entities/${encodeURIComponent(entityId)}/systemd/services/${encodeURIComponent(serviceName)}/restart`,
                { method: "POST" }
            );
            if (!mountedRef.current) return;
            if (result) {
                showSimpleToast(
                    `Restart sent for service ${serviceName}`,
                    "success"
                );
                // Delay refresh to give the service time to restart
                setTimeout(() => {
                    if (mountedRef.current) fetchNodes();
                }, 3000);
            } else {
                showSimpleToast(
                    `Failed to restart service ${serviceName}`,
                    "error"
                );
            }
            setShowConfirm(null);
        },
        [entityId, fetchNodes]
    );

    // ---- Confirm dialog handler -------------------------------------------

    const handleConfirmAction = useCallback(() => {
        if (!showConfirm) return;
        if (showConfirm.type === "lifecycle") {
            handleLifecycleTransition(showConfirm.node, showConfirm.transition);
        } else if (showConfirm.type === "restart") {
            handleRestart(showConfirm.node);
        }
    }, [showConfirm, handleLifecycleTransition, handleRestart]);

    // ---- Filtering --------------------------------------------------------

    const filteredNodes = useMemo(() => {
        const byCategory = filterByCategory(nodes, categoryFilter, classifyNode);
        if (!searchFilter) return byCategory;
        const query = searchFilter.toLowerCase();
        return byCategory.filter(
            (n) =>
                (n.name || "").toLowerCase().includes(query) ||
                (n.namespace || "").toLowerCase().includes(query)
        );
    }, [nodes, searchFilter, categoryFilter]);

    const categoryCounts = useMemo(() => {
        return {
            all: nodes.length,
            pragati: nodes.filter((n) => classifyNode(n.name) === "pragati").length,
            dashboard: nodes.filter((n) => classifyNode(n.name) === "dashboard").length,
            system: nodes.filter((n) => classifyNode(n.name) === "system").length,
        };
    }, [nodes]);

    // ---- Pagination -------------------------------------------------------

    const totalPages = Math.max(1, Math.ceil(filteredNodes.length / PAGE_SIZE));
    const safePage = Math.min(currentPage, totalPages);
    const paginatedNodes = useMemo(() => {
        const start = (safePage - 1) * PAGE_SIZE;
        return filteredNodes.slice(start, start + PAGE_SIZE);
    }, [filteredNodes, safePage]);

    // ---- Render -----------------------------------------------------------

    if (!ros2Available) {
        return html`
            <div style=${styles.unavailable}>
                ROS2 is not available on this entity. Node information
                requires an active ROS2 environment.
            </div>
        `;
    }

    if (loading && nodes.length === 0) {
        return html`
            <div style=${styles.skeleton}>
                <style>
                    @keyframes shimmer {
                        0% { background-position: 200% 0; }
                        100% { background-position: -200% 0; }
                    }
                </style>
                ${Array.from({ length: 8 }, (_, i) => html`
                    <div key=${i} style=${{
                        ...styles.skeletonRow,
                        width: `${60 + Math.random() * 35}%`,
                    }} />
                `)}
            </div>
        `;
    }

    if (fetchError && nodes.length === 0) {
        return html`
            <div style=${styles.errorState}>
                <div style=${{ marginBottom: "12px" }}>
                    Failed to load nodes. The entity may be unreachable.
                </div>
                <button
                    style=${styles.retryBtn}
                    onClick=${() => fetchNodes(true)}
                >
                    Retry
                </button>
            </div>
        `;
    }

    const isRemote = entitySource === "remote";

    return html`
        <div style=${styles.container}>
            <!-- Header -->
            <div style=${styles.headerRow}>
                <span style=${styles.nodeCount}>
                    ${filteredNodes.length} node${filteredNodes.length !== 1 ? "s" : ""}
                    ${searchFilter ? ` matching "${searchFilter}"` : ""}
                    ${stale ? html`<span style=${styles.staleBadge}>Stale</span>` : null}
                </span>
                ${stale || fetchError ? html`
                    <button style=${styles.retryBtn} onClick=${() => fetchNodes(true)}>
                        Retry
                    </button>
                ` : null}
            </div>

            <!-- Category filter -->
            <${CategoryFilterBar}
                active=${categoryFilter}
                onChange=${(v) => { setCategoryFilter(v); setCurrentPage(1); }}
                counts=${categoryCounts}
            />

            <!-- Search -->
            <input
                type="text"
                placeholder="Search nodes by name or namespace..."
                style=${styles.searchInput}
                value=${searchFilter}
                onInput=${(e) => setSearchFilter(e.target.value)}
            />

            <!-- Table -->
            ${filteredNodes.length === 0
                ? html`
                      <div style=${styles.emptyState}>
                          ${searchFilter
                              ? "No nodes match your search."
                              : "No nodes found on this entity."}
                      </div>
                  `
                : html`
                      <table style=${styles.table}>
                          <thead>
                              <tr>
                                  <th style=${styles.th}>Name</th>
                                  <th style=${styles.th}>Namespace</th>
                                  <th style=${styles.th}>Lifecycle State</th>
                                  <th style=${styles.th}>Actions</th>
                              </tr>
                          </thead>
                          <tbody>
                              ${paginatedNodes.map((node) => {
                                  const name = node.name || "";
                                  const ns = node.namespace || "/";
                                  const lcState = node.lifecycle_state;
                                  const isExpanded = expandedNode === name;
                                  const hasLifecycle = lcState != null;
                                  const stateKey = hasLifecycle
                                      ? lcState.toLowerCase()
                                      : null;
                                  const badgeColor = stateKey
                                      ? LIFECYCLE_COLORS[stateKey] || "var(--color-text-secondary)"
                                      : null;
                                  const transitions = stateKey
                                      ? VALID_TRANSITIONS[stateKey] || []
                                      : [];
                                  const serviceName = nodeToServiceName(name);
                                  const canRestart = isRemote && serviceName != null;

                                  return html`
                                      <tr
                                          key=${name}
                                          style=${{
                                              ...styles.clickableRow,
                                              backgroundColor: isExpanded
                                                  ? "var(--color-bg-tertiary)"
                                                  : "transparent",
                                          }}
                                          onClick=${() => handleRowClick(name)}
                                      >
                                          <td style=${styles.td}>
                                              <strong>${name}</strong>
                                          </td>
                                          <td style=${styles.td}>${ns}</td>
                                          <td style=${styles.td}>
                                              ${hasLifecycle
                                                  ? html`
                                                        <span
                                                            style=${styles.badge(
                                                                badgeColor
                                                            )}
                                                        >
                                                            ${lcState}
                                                        </span>
                                                    `
                                                  : html`
                                                        <span
                                                            style=${{
                                                                color: "var(--color-text-muted)",
                                                                fontSize: "13px",
                                                            }}
                                                        >
                                                            N/A
                                                        </span>
                                                    `}
                                          </td>
                                          <td
                                              style=${{
                                                  ...styles.td,
                                              }}
                                              onClick=${(e) =>
                                                  e.stopPropagation()}
                                          >
                                              <div style=${styles.actionsCell}>
                                                  ${transitions.map(
                                                      (t) => html`
                                                          <button
                                                              key=${t}
                                                              style=${styles.transitionBtn(
                                                                  TRANSITION_COLORS[
                                                                      t
                                                                  ] || "var(--color-text-secondary)"
                                                              )}
                                                              onClick=${(e) => {
                                                                  e.stopPropagation();
                                                                  setShowConfirm({
                                                                      type: "lifecycle",
                                                                      node: name,
                                                                      transition:
                                                                          t,
                                                                  });
                                                              }}
                                                              title=${`${t} node`}
                                                          >
                                                              ${t}
                                                          </button>
                                                      `
                                                  )}
                                                  ${isRemote
                                                      ? html`
                                                            <button
                                                                style=${canRestart
                                                                    ? styles.restartBtn
                                                                    : styles.restartBtnDisabled}
                                                                disabled=${!canRestart}
                                                                onClick=${(e) => {
                                                                    e.stopPropagation();
                                                                    if (
                                                                        canRestart
                                                                    ) {
                                                                        setShowConfirm(
                                                                            {
                                                                                type: "restart",
                                                                                node: name,
                                                                            }
                                                                        );
                                                                    }
                                                                }}
                                                                title=${canRestart
                                                                    ? `Restart service ${serviceName}`
                                                                    : "Cannot determine service name"}
                                                            >
                                                                \u21bb Restart
                                                            </button>
                                                        `
                                                      : null}
                                              </div>
                                          </td>
                                      </tr>
                                      ${isExpanded
                                          ? html`
                                                <${NodeDetailPanel}
                                                    detail=${nodeDetail}
                                                    loading=${loadingDetail}
                                                />
                                            `
                                          : null}
                                  `;
                              })}
                          </tbody>
                      </table>
                      ${filteredNodes.length > PAGE_SIZE ? html`
                          <div style=${styles.paginationBar}>
                              <button
                                  style=${safePage <= 1 ? styles.pageBtnDisabled : styles.pageBtn}
                                  disabled=${safePage <= 1}
                                  onClick=${() => setCurrentPage((p) => Math.max(1, p - 1))}
                              >
                                  Prev
                              </button>
                              <span>Page ${safePage} of ${totalPages}</span>
                              <button
                                  style=${safePage >= totalPages ? styles.pageBtnDisabled : styles.pageBtn}
                                  disabled=${safePage >= totalPages}
                                  onClick=${() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                              >
                                  Next
                              </button>
                          </div>
                      ` : null}
                  `}

            <!-- Confirmation dialog -->
            ${showConfirm
                ? html`
                      <${ConfirmDialog}
                          title=${showConfirm.type === "lifecycle"
                              ? `Lifecycle Transition: ${showConfirm.transition}`
                              : "Restart Node Service"}
                          message=${showConfirm.type === "lifecycle"
                              ? `Are you sure you want to send '${showConfirm.transition}' to node '${showConfirm.node}'?`
                              : `Are you sure you want to restart the systemd service for node '${showConfirm.node}' (${nodeToServiceName(showConfirm.node)})?`}
                          confirmLabel=${showConfirm.type === "lifecycle"
                              ? showConfirm.transition
                              : "Restart"}
                          confirmColor=${showConfirm.type === "lifecycle"
                              ? TRANSITION_COLORS[showConfirm.transition] ||
                                "var(--color-accent)"
                              : "var(--color-warning)"}
                          onConfirm=${handleConfirmAction}
                          onCancel=${() => setShowConfirm(null)}
                      />
                  `
                : null}
        </div>
    `;
}
