/**
 * ParametersSubTab -- Preact component for browsing, searching, and
 * inline-editing ROS2 node parameters within the entity detail view.
 *
 * Features:
 *   - Parameters grouped by node with collapsible sections (Task 5.1)
 *   - Inline editing with type-aware inputs and confirmation (Task 5.2)
 *   - Search and node filter (Task 5.3)
 *   - 10-second auto-refresh with changed-value highlighting
 *
 * @module tabs/entity/ParametersSubTab
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
import { cachedEntityFetch } from "../../utils/cachedFetch.mjs";
import { safeFetch } from "../../utils.js";
import { CategoryFilterBar, classifyNode, filterByCategory } from "../../utils/categoryFilter.mjs";

// ---------------------------------------------------------------------------
// Styles (inline)
// ---------------------------------------------------------------------------

const STYLES = {
    container: {
        fontFamily: "inherit",
        fontSize: "14px",
    },
    toolbar: {
        display: "flex",
        gap: "8px",
        alignItems: "center",
        marginBottom: "12px",
        flexWrap: "wrap",
    },
    searchInput: {
        padding: "6px 10px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        fontSize: "13px",
        flex: "1 1 200px",
        minWidth: "160px",
        outline: "none",
        background: "var(--color-bg-secondary)",
        color: "var(--color-text-primary)",
    },
    nodeSelect: {
        padding: "6px 10px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        fontSize: "13px",
        background: "var(--color-bg-secondary)",
        color: "var(--color-text-primary)",
        cursor: "pointer",
        minWidth: "160px",
    },
    refreshBtn: {
        padding: "6px 14px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        background: "var(--color-bg-tertiary)",
        color: "var(--color-text-primary)",
        cursor: "pointer",
        fontSize: "13px",
        whiteSpace: "nowrap",
    },
    nodeGroup: {
        marginBottom: "8px",
        border: "1px solid var(--color-border)",
        borderRadius: "6px",
        overflow: "hidden",
    },
    nodeHeader: {
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "8px 12px",
        background: "var(--color-bg-secondary)",
        cursor: "pointer",
        userSelect: "none",
        fontWeight: "bold",
        fontSize: "13px",
        color: "var(--color-text-primary)",
        borderBottom: "1px solid var(--color-border)",
    },
    nodeHeaderCollapsed: {
        borderBottom: "none",
    },
    arrow: {
        fontSize: "10px",
        width: "14px",
        display: "inline-block",
        transition: "transform 0.15s ease",
    },
    badge: {
        fontSize: "11px",
        background: "var(--color-bg-elevated)",
        color: "var(--color-text-primary)",
        borderRadius: "10px",
        padding: "1px 8px",
        fontWeight: "normal",
        marginLeft: "auto",
    },
    table: {
        width: "100%",
        borderCollapse: "collapse",
        fontSize: "13px",
        tableLayout: "fixed",
    },
    th: {
        textAlign: "left",
        padding: "6px 10px",
        background: "var(--color-bg-tertiary)",
        borderBottom: "1px solid var(--color-border)",
        fontWeight: 600,
        fontSize: "12px",
        color: "var(--color-text-secondary)",
    },
    td: {
        padding: "6px 10px",
        borderBottom: "1px solid var(--color-border)",
        verticalAlign: "middle",
        color: "var(--color-text-primary)",
    },
    tdHighlight: {
        padding: "6px 10px",
        borderBottom: "1px solid var(--color-border)",
        verticalAlign: "middle",
        background: "rgba(245, 158, 11, 0.15)",
        transition: "background 0.3s ease",
        color: "var(--color-text-primary)",
    },
    typeBadge: {
        fontSize: "11px",
        borderRadius: "3px",
        padding: "1px 6px",
        fontWeight: 500,
        display: "inline-block",
    },
    editBtn: {
        padding: "3px 10px",
        fontSize: "12px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        background: "var(--color-bg-tertiary)",
        color: "var(--color-text-primary)",
        cursor: "pointer",
    },
    editInput: {
        padding: "4px 8px",
        border: "1px solid var(--color-border)",
        borderRadius: "4px",
        fontSize: "13px",
        width: "100%",
        boxSizing: "border-box",
        outline: "none",
        background: "var(--color-bg-tertiary)",
        color: "var(--color-text-primary)",
        colorScheme: "dark",
    },
    saveBtn: {
        padding: "3px 10px",
        fontSize: "12px",
        border: "none",
        borderRadius: "var(--radius-sm)",
        background: "var(--color-success)",
        color: "#fff",
        cursor: "pointer",
        marginRight: "4px",
    },
    cancelBtn: {
        padding: "3px 10px",
        fontSize: "12px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        background: "var(--color-bg-elevated)",
        color: "var(--color-text-primary)",
        cursor: "pointer",
    },
    overlay: {
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 10000,
    },
    modal: {
        background: "var(--color-bg-surface)",
        borderRadius: "var(--radius-md)",
        padding: "24px",
        maxWidth: "440px",
        width: "90%",
        boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
        border: "1px solid var(--color-border)",
    },
    modalTitle: {
        margin: "0 0 12px 0",
        fontSize: "16px",
        color: "var(--color-text-primary)",
    },
    modalBody: {
        margin: "0 0 20px 0",
        fontSize: "14px",
        color: "var(--color-text-secondary)",
        wordBreak: "break-word",
    },
    modalActions: {
        display: "flex",
        gap: "8px",
        justifyContent: "flex-end",
    },
    toast: {
        position: "fixed",
        bottom: "20px",
        right: "20px",
        padding: "10px 20px",
        borderRadius: "6px",
        color: "#fff",
        fontSize: "14px",
        zIndex: 10001,
        boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
        transition: "opacity 0.3s ease",
    },
    loading: {
        padding: "24px",
        textAlign: "center",
        color: "var(--color-text-muted)",
    },
    empty: {
        padding: "24px",
        textAlign: "center",
        color: "var(--color-text-muted)",
        fontStyle: "italic",
    },
    unavailable: {
        padding: "24px",
        textAlign: "center",
        color: "var(--color-error)",
    },
    skeleton: {
        padding: "16px",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
    },
    skeletonRow: {
        height: "18px",
        borderRadius: "var(--radius-sm)",
        background:
            "linear-gradient(90deg, var(--color-bg-tertiary) 25%, var(--color-bg-secondary) 50%, var(--color-bg-tertiary) 75%)",
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
        padding: "6px 14px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        background: "var(--color-bg-tertiary)",
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
        padding: "6px 12px",
        fontSize: "12px",
        color: "var(--color-text-muted)",
        borderTop: "1px solid var(--color-border)",
    },
    pageBtn: {
        padding: "3px 10px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        backgroundColor: "var(--color-bg-surface)",
        color: "var(--color-text-primary)",
        cursor: "pointer",
        fontSize: "12px",
    },
    pageBtnDisabled: {
        padding: "3px 10px",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        backgroundColor: "var(--color-bg-secondary)",
        cursor: "not-allowed",
        fontSize: "12px",
        color: "var(--color-text-muted)",
    },
};

/** Map parameter type strings to badge colours (dark-theme compatible). */
const TYPE_COLORS = {
    string: { background: "rgba(75, 141, 247, 0.2)", color: "#6ba3f7" },
    double: { background: "rgba(34, 197, 94, 0.2)", color: "#4ade80" },
    float: { background: "rgba(34, 197, 94, 0.2)", color: "#4ade80" },
    int: { background: "rgba(245, 158, 11, 0.2)", color: "#fbbf24" },
    integer: { background: "rgba(245, 158, 11, 0.2)", color: "#fbbf24" },
    bool: { background: "rgba(168, 85, 247, 0.2)", color: "#c084fc" },
    boolean: { background: "rgba(168, 85, 247, 0.2)", color: "#c084fc" },
};

const REFRESH_INTERVAL_MS = 10_000;
const HIGHLIGHT_DURATION_MS = 2_000;
const PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Display-format a parameter value.
 * @param {*} value
 * @returns {string}
 */
function formatValue(value) {
    if (value === null || value === undefined) return "null";
    if (typeof value === "boolean") return value ? "true" : "false";
    if (typeof value === "object") {
        try {
            return JSON.stringify(value);
        } catch {
            return String(value);
        }
    }
    return String(value);
}

/**
 * Coerce an edited string value to the appropriate JS type based on the
 * parameter type declaration.
 * @param {string} raw
 * @param {string} type
 * @returns {*}
 */
function coerceValue(raw, type) {
    const t = (type || "").toLowerCase();
    if (t === "bool" || t === "boolean") {
        const v = raw.trim().toLowerCase();
        return v === "true" || v === "1";
    }
    if (t === "int" || t === "integer") {
        const n = parseInt(raw, 10);
        return isNaN(n) ? raw : n;
    }
    if (t === "double" || t === "float") {
        const n = parseFloat(raw);
        return isNaN(n) ? raw : n;
    }
    return raw;
}

/**
 * Build a stable key for a param to track value changes between fetches.
 * @param {string} nodeName
 * @param {string} paramName
 * @returns {string}
 */
function paramKey(nodeName, paramName) {
    return `${nodeName}::${paramName}`;
}

// ---------------------------------------------------------------------------
// Toast mini-component (self-contained to avoid hard dep on app.js context)
// ---------------------------------------------------------------------------

function InlineToast({ message, severity, onDone }) {
    const timerRef = useRef(null);

    useEffect(() => {
        timerRef.current = setTimeout(() => {
            onDone();
        }, 3000);
        return () => clearTimeout(timerRef.current);
    }, [onDone]);

    const bg =
        severity === "success"
            ? "var(--color-success)"
            : severity === "error"
              ? "var(--color-error)"
              : "var(--color-accent)";

    return html`
        <div style=${{ ...STYLES.toast, background: bg }}>${message}</div>
    `;
}

// ---------------------------------------------------------------------------
// Confirmation modal
// ---------------------------------------------------------------------------

function ConfirmModal({ title, body, onConfirm, onCancel }) {
    return html`
        <div style=${STYLES.overlay} onClick=${onCancel}>
            <div style=${STYLES.modal} onClick=${(e) => e.stopPropagation()}>
                <h3 style=${STYLES.modalTitle}>${title}</h3>
                <p style=${STYLES.modalBody}>${body}</p>
                <div style=${STYLES.modalActions}>
                    <button style=${STYLES.cancelBtn} onClick=${onCancel}>
                        Cancel
                    </button>
                    <button style=${STYLES.saveBtn} onClick=${onConfirm}>
                        Confirm
                    </button>
                </div>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Parameter row
// ---------------------------------------------------------------------------

function ParamRow({
    nodeName,
    param,
    isEditing,
    editValue,
    highlight,
    onStartEdit,
    onEditChange,
    onSave,
    onCancelEdit,
}) {
    const inputRef = useRef(null);
    const typeLower = (param.type || "unknown").toLowerCase();
    const typeColors = TYPE_COLORS[typeLower] || {
        background: "var(--color-bg-tertiary)",
        color: "var(--color-text-secondary)",
    };

    useEffect(() => {
        if (isEditing && inputRef.current) {
            inputRef.current.focus();
        }
    }, [isEditing]);

    const handleKeyDown = useCallback(
        (e) => {
            if (e.key === "Enter") onSave();
            if (e.key === "Escape") onCancelEdit();
        },
        [onSave, onCancelEdit],
    );

    const valueTd = highlight ? STYLES.tdHighlight : STYLES.td;

    const isBool =
        typeLower === "bool" || typeLower === "boolean";

    return html`
        <tr>
            <td style=${STYLES.td}>${param.name}</td>
            <td style=${STYLES.td}>
                <span
                    style=${{
                        ...STYLES.typeBadge,
                        ...typeColors,
                    }}
                    >${param.type || "unknown"}</span
                >
            </td>
            <td style=${{ ...valueTd, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "0" }}>
                ${isEditing
                    ? isBool
                        ? html`
                              <input
                                  ref=${inputRef}
                                  type="checkbox"
                                  checked=${editValue === "true" ||
                                  editValue === true}
                                  onChange=${(e) =>
                                      onEditChange(
                                          String(e.target.checked),
                                      )}
                              />
                          `
                        : typeLower === "int" ||
                            typeLower === "integer" ||
                            typeLower === "double" ||
                            typeLower === "float"
                          ? html`
                                <input
                                    ref=${inputRef}
                                    type="number"
                                    step=${typeLower === "int" ||
                                    typeLower === "integer"
                                        ? "1"
                                        : "any"}
                                    value=${editValue}
                                    onInput=${(e) =>
                                        onEditChange(e.target.value)}
                                    onKeyDown=${handleKeyDown}
                                    style=${STYLES.editInput}
                                />
                            `
                          : html`
                                <input
                                    ref=${inputRef}
                                    type="text"
                                    value=${editValue}
                                    onInput=${(e) =>
                                        onEditChange(e.target.value)}
                                    onKeyDown=${handleKeyDown}
                                    style=${STYLES.editInput}
                                />
                            `
                    : formatValue(param.value)}
            </td>
            <td style=${STYLES.td}>
                ${isEditing
                    ? html`
                          <button style=${STYLES.saveBtn} onClick=${onSave}>
                              Save
                          </button>
                          <button
                              style=${STYLES.cancelBtn}
                              onClick=${onCancelEdit}
                          >
                              Cancel
                          </button>
                      `
                    : html`
                          <button
                              style=${STYLES.editBtn}
                              onClick=${onStartEdit}
                              title="Edit parameter"
                          >
                              \u270E Edit
                          </button>
                      `}
            </td>
        </tr>
    `;
}

// ---------------------------------------------------------------------------
// Node group
// ---------------------------------------------------------------------------

function NodeGroup({
    node,
    expanded,
    searchFilter,
    editingParam,
    editValue,
    highlightedKeys,
    onToggle,
    onStartEdit,
    onEditChange,
    onSave,
    onCancelEdit,
    entityId,
}) {
    const [currentPage, setCurrentPage] = useState(1);
    const [loadedParams, setLoadedParams] = useState(node.parameters);
    const [paramLoading, setParamLoading] = useState(false);
    const fetchedRef = useRef(false);

    // Lazy-load parameters when node is expanded for the first time
    useEffect(() => {
        if (!expanded || fetchedRef.current) return;
        if (loadedParams && loadedParams.length > 0) {
            fetchedRef.current = true;
            return;
        }
        // parameters is null or empty — fetch on demand
        setParamLoading(true);
        const nodePath = node.name.startsWith("/") ? node.name.slice(1) : node.name;
        safeFetch(`/api/entities/${entityId}/ros2/parameters/${nodePath}`)
            .then((result) => {
                if (result) {
                    const data = result.data || result;
                    setLoadedParams(data.parameters || []);
                }
                setParamLoading(false);
                fetchedRef.current = true;
            })
            .catch(() => {
                setParamLoading(false);
                fetchedRef.current = true;
            });
    }, [expanded, entityId, node.name, loadedParams]);

    // Sync if parent pushes new params (e.g. from refresh)
    useEffect(() => {
        if (node.parameters && node.parameters.length > 0) {
            setLoadedParams(node.parameters);
        }
    }, [node.parameters]);

    const params = loadedParams || [];

    const filteredParams = useMemo(() => {
        if (!searchFilter) return params;
        const q = searchFilter.toLowerCase();
        return params.filter((p) =>
            p.name.toLowerCase().includes(q),
        );
    }, [params, searchFilter]);

    // Reset page when filter changes
    useEffect(() => {
        setCurrentPage(1);
    }, [searchFilter]);

    if (searchFilter && filteredParams.length === 0) return null;

    const totalPages = Math.max(
        1,
        Math.ceil(filteredParams.length / PAGE_SIZE),
    );
    const safePage = Math.min(currentPage, totalPages);
    const paginatedParams = filteredParams.slice(
        (safePage - 1) * PAGE_SIZE,
        safePage * PAGE_SIZE,
    );

    const headerStyle = expanded
        ? STYLES.nodeHeader
        : { ...STYLES.nodeHeader, ...STYLES.nodeHeaderCollapsed };

    return html`
        <div style=${STYLES.nodeGroup}>
            <div style=${headerStyle} onClick=${() => onToggle(node.name)}>
                <span
                    style=${{
                        ...STYLES.arrow,
                        transform: expanded
                            ? "rotate(90deg)"
                            : "rotate(0deg)",
                    }}
                    >\u25B6</span
                >
                <span>${node.name}</span>
                <span style=${STYLES.badge}
                    >${paramLoading ? "loading..." : `${filteredParams.length} param${filteredParams.length !== 1 ? "s" : ""}`}</span
                >
            </div>
            ${expanded && paramLoading
                ? html`<div style=${STYLES.loading}>Loading parameters...</div>`
                : null}
            ${expanded && !paramLoading
                ? html`
                      <table style=${STYLES.table}>
                          <thead>
                              <tr>
                                  <th style=${STYLES.th}>Name</th>
                                  <th style=${{ ...STYLES.th, width: "80px" }}>
                                      Type
                                  </th>
                                  <th style=${STYLES.th}>Value</th>
                                  <th style=${{ ...STYLES.th, width: "120px" }}>
                                      Action
                                  </th>
                              </tr>
                          </thead>
                          <tbody>
                              ${paginatedParams.map((p) => {
                                  const pk = paramKey(node.name, p.name);
                                  const isEditing =
                                      editingParam !== null &&
                                      editingParam.node === node.name &&
                                      editingParam.name === p.name;
                                  return html`
                                      <${ParamRow}
                                          key=${pk}
                                          nodeName=${node.name}
                                          param=${p}
                                          isEditing=${isEditing}
                                          editValue=${isEditing
                                              ? editValue
                                              : ""}
                                          highlight=${highlightedKeys.has(pk)}
                                          onStartEdit=${() =>
                                              onStartEdit(
                                                  node.name,
                                                  p.name,
                                                  p.value,
                                              )}
                                          onEditChange=${onEditChange}
                                          onSave=${onSave}
                                          onCancelEdit=${onCancelEdit}
                                      />
                                  `;
                              })}
                          </tbody>
                      </table>
                      ${filteredParams.length > PAGE_SIZE
                          ? html`
                                <div style=${STYLES.paginationBar}>
                                    <button
                                        style=${safePage <= 1
                                            ? STYLES.pageBtnDisabled
                                            : STYLES.pageBtn}
                                        disabled=${safePage <= 1}
                                        onClick=${(e) => {
                                            e.stopPropagation();
                                            setCurrentPage((p) =>
                                                Math.max(1, p - 1),
                                            );
                                        }}
                                    >
                                        Prev
                                    </button>
                                    <span>${safePage} / ${totalPages}</span>
                                    <button
                                        style=${safePage >= totalPages
                                            ? STYLES.pageBtnDisabled
                                            : STYLES.pageBtn}
                                        disabled=${safePage >= totalPages}
                                        onClick=${(e) => {
                                            e.stopPropagation();
                                            setCurrentPage((p) =>
                                                Math.min(totalPages, p + 1),
                                            );
                                        }}
                                    >
                                        Next
                                    </button>
                                </div>
                            `
                          : null}
                  `
                : null}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ParametersSubTab({
    entityId,
    entitySource,
    entityIp,
    ros2Available,
    registerCleanup,
}) {
    const [paramData, setParamData] = useState({ nodes: [] });
    const [searchFilter, setSearchFilter] = useState("");
    const [nodeFilter, setNodeFilter] = useState("");
    const [category, setCategory] = useState("pragati");
    const [expandedNodes, setExpandedNodes] = useState(new Set());
    const [editingParam, setEditingParam] = useState(null);
    const [editValue, setEditValue] = useState("");
    const [showConfirm, setShowConfirm] = useState(false);
    const [previousValues, setPreviousValues] = useState({});
    const [highlightedKeys, setHighlightedKeys] = useState(new Set());
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [toast, setToast] = useState(null);
    const [stale, setStale] = useState(false);
    const [error, setError] = useState(null);
    const refreshTimerRef = useRef(null);
    const highlightTimersRef = useRef([]);
    const isFirstLoad = useRef(true);
    const abortControllerRef = useRef(null);

    // -----------------------------------------------------------------------
    // Toast helper
    // -----------------------------------------------------------------------

    const showToast = useCallback((message, severity) => {
        setToast({ message, severity });
    }, []);

    const dismissToast = useCallback(() => {
        setToast(null);
    }, []);

    // -----------------------------------------------------------------------
    // Data fetching
    // -----------------------------------------------------------------------

    const fetchParams = useCallback(
        async (bypass = false) => {
            if (!entityId) return;

            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
            abortControllerRef.current = new AbortController();

            if (bypass) {
                setLoading(true);
                setError(null);
                setStale(false);
            }

            const result = await cachedEntityFetch(
                entityId,
                "ros2/parameters",
                {
                    signal: abortControllerRef.current.signal,
                    bypassCache: bypass,
                },
            );

            if (!result) {
                if (isFirstLoad.current) {
                    setLoading(false);
                    isFirstLoad.current = false;
                    setError("Failed to load parameters");
                }
                return;
            }

            // result.data may be { nodes: [...] } or just an array
            const nodes =
                result.data?.nodes ||
                (Array.isArray(result.data) ? result.data : []);
            setStale(result.stale);
            setError(null);

            // Detect changed values for highlighting
            setParamData((prev) => {
                const newValueMap = {};
                for (const node of nodes) {
                    const params = node.parameters || [];
                    for (const p of params) {
                        newValueMap[paramKey(node.name, p.name)] = formatValue(
                            p.value,
                        );
                    }
                }

                if (!isFirstLoad.current) {
                    const changedKeys = new Set();
                    for (const [key, val] of Object.entries(newValueMap)) {
                        const prevVal = previousValues[key];
                        if (prevVal !== undefined && prevVal !== val) {
                            changedKeys.add(key);
                        }
                    }

                    if (changedKeys.size > 0) {
                        setHighlightedKeys((prev) => {
                            const next = new Set(prev);
                            for (const k of changedKeys) next.add(k);
                            return next;
                        });

                        const timer = setTimeout(() => {
                            setHighlightedKeys((prev) => {
                                const next = new Set(prev);
                                for (const k of changedKeys) next.delete(k);
                                return next;
                            });
                        }, HIGHLIGHT_DURATION_MS);
                        highlightTimersRef.current.push(timer);
                    }
                }

                setPreviousValues(newValueMap);
                // Merge: preserve already-loaded parameters when the node
                // list refreshes (agent returns parameters: null for the
                // lightweight listing endpoint).
                return {
                    nodes: nodes.map((newNode) => {
                        if (newNode.parameters && newNode.parameters.length > 0) {
                            return newNode;
                        }
                        const existing = prev.nodes.find((n) => n.name === newNode.name);
                        if (existing && existing.parameters && existing.parameters.length > 0) {
                            return { ...newNode, parameters: existing.parameters };
                        }
                        return newNode;
                    }),
                };
            });

            if (isFirstLoad.current) {
                // Pre-fetch pragati node params in background (collapsed by default)
                const pragatiNodes = nodes.filter((n) => classifyNode(n.name) === "pragati");
                setExpandedNodes(new Set());
                isFirstLoad.current = false;

                // Fire parallel fetches for pragati nodes only
                if (pragatiNodes.length > 0) {
                    Promise.allSettled(
                        pragatiNodes.map(async (node) => {
                            const nodePath = node.name.startsWith("/") ? node.name.slice(1) : node.name;
                            const result = await safeFetch(`/api/entities/${entityId}/ros2/parameters/${nodePath}`);
                            if (result) {
                                const data = result.data || result;
                                return { name: node.name, parameters: data.parameters || [] };
                            }
                            return { name: node.name, parameters: [] };
                        })
                    ).then((results) => {
                        const fetchedMap = {};
                        for (const r of results) {
                            if (r.status === "fulfilled") {
                                fetchedMap[r.value.name] = r.value.parameters;
                            }
                        }
                        setParamData((prev) => ({
                            nodes: prev.nodes.map((n) =>
                                fetchedMap[n.name] !== undefined
                                    ? { ...n, parameters: fetchedMap[n.name] }
                                    : n
                            ),
                        }));
                    });
                }
            }

            setLoading(false);
        },
        [entityId, previousValues],
    );

    // Initial fetch and auto-refresh (node list only — lightweight)
    useEffect(() => {
        abortControllerRef.current = new AbortController();
        fetchParams();

        // Refresh node list periodically (not params — those are on-demand)
        refreshTimerRef.current = setInterval(
            () => fetchParams(false),
            REFRESH_INTERVAL_MS,
        );

        return () => {
            clearInterval(refreshTimerRef.current);
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
            for (const t of highlightTimersRef.current) {
                clearTimeout(t);
            }
        };
    }, [fetchParams]);

    // Register cleanup for parent shell
    useEffect(() => {
        if (registerCleanup) {
            registerCleanup(() => {
                clearInterval(refreshTimerRef.current);
                if (abortControllerRef.current) {
                    abortControllerRef.current.abort();
                }
                for (const t of highlightTimersRef.current) {
                    clearTimeout(t);
                }
            });
        }
    }, [registerCleanup]);

    // -----------------------------------------------------------------------
    // Editing
    // -----------------------------------------------------------------------

    const startEdit = useCallback((nodeName, paramName, currentValue) => {
        setEditingParam({ node: nodeName, name: paramName });
        setEditValue(formatValue(currentValue));
    }, []);

    const cancelEdit = useCallback(() => {
        setEditingParam(null);
        setEditValue("");
        setShowConfirm(false);
    }, []);

    const handleEditChange = useCallback((val) => {
        setEditValue(val);
    }, []);

    const requestSave = useCallback(() => {
        setShowConfirm(true);
    }, []);

    const confirmSave = useCallback(async () => {
        if (!editingParam) return;

        setShowConfirm(false);
        setSaving(true);

        // Find param type for coercion
        let paramType = "string";
        for (const node of paramData.nodes) {
            if (node.name === editingParam.node) {
                const p = node.parameters.find(
                    (pp) => pp.name === editingParam.name,
                );
                if (p) paramType = p.type || "string";
                break;
            }
        }

        const coerced = coerceValue(editValue, paramType);

        const nodePath = editingParam.node.startsWith("/")
            ? editingParam.node.slice(1)
            : editingParam.node;
        const url = `/api/entities/${encodeURIComponent(entityId)}/ros2/parameters/${encodeURIComponent(nodePath)}`;
        const body = JSON.stringify({
            params: [{ name: editingParam.name, value: coerced }],
        });

        try {
            const resp = await fetch(url, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body,
            });

            if (resp.ok) {
                showToast("Parameter updated", "success");
                setEditingParam(null);
                setEditValue("");
                // Refresh immediately to show new value
                await fetchParams();
            } else {
                let reason = `HTTP ${resp.status}`;
                try {
                    const errData = await resp.json();
                    if (errData.detail) reason = errData.detail;
                    else if (errData.error) reason = errData.error;
                } catch {
                    // keep the HTTP status reason
                }
                showToast(`Failed to update parameter: ${reason}`, "error");
            }
        } catch (err) {
            showToast(`Failed to update parameter: ${err.message}`, "error");
        } finally {
            setSaving(false);
        }
    }, [editingParam, editValue, entityId, paramData, showToast, fetchParams]);

    // -----------------------------------------------------------------------
    // Node toggle
    // -----------------------------------------------------------------------

    const toggleNode = useCallback((nodeName) => {
        setExpandedNodes((prev) => {
            const next = new Set(prev);
            if (next.has(nodeName)) {
                next.delete(nodeName);
            } else {
                next.add(nodeName);
            }
            return next;
        });
    }, []);

    // -----------------------------------------------------------------------
    // Derived data
    // -----------------------------------------------------------------------

    const nodeNames = useMemo(
        () => paramData.nodes.map((n) => n.name).sort(),
        [paramData.nodes],
    );

    const filteredNodes = useMemo(() => {
        let nodes = paramData.nodes;

        // Apply category filter
        nodes = filterByCategory(nodes, category, classifyNode);

        // Apply node filter
        if (nodeFilter) {
            nodes = nodes.filter((n) => n.name === nodeFilter);
        }

        // Sort by name
        return [...nodes].sort((a, b) => a.name.localeCompare(b.name));
    }, [paramData.nodes, nodeFilter, category]);

    const categoryCounts = useMemo(() => {
        const nodes = paramData.nodes;
        return {
            all: nodes.length,
            pragati: nodes.filter((n) => classifyNode(n.name) === "pragati").length,
            dashboard: nodes.filter((n) => classifyNode(n.name) === "dashboard").length,
            system: nodes.filter((n) => classifyNode(n.name) === "system").length,
        };
    }, [paramData.nodes]);

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------

    if (!ros2Available) {
        return html`
            <div style=${STYLES.unavailable}>
                ROS2 is not available on this entity.
            </div>
        `;
    }

    return html`
        <div style=${STYLES.container}>
            <!-- Category filter -->
            <${CategoryFilterBar}
                active=${category}
                onChange=${setCategory}
                counts=${categoryCounts}
            />

            <!-- Toolbar: search + node filter + refresh -->
            <div style=${STYLES.toolbar}>
                <input
                    type="text"
                    placeholder="Search parameters..."
                    value=${searchFilter}
                    onInput=${(e) => setSearchFilter(e.target.value)}
                    style=${STYLES.searchInput}
                />
                <select
                    value=${nodeFilter}
                    onChange=${(e) => setNodeFilter(e.target.value)}
                    style=${STYLES.nodeSelect}
                >
                    <option value="">All Nodes</option>
                    ${nodeNames.map(
                        (name) => html`
                            <option key=${name} value=${name}>${name}</option>
                        `,
                    )}
                </select>
                <button
                    style=${STYLES.refreshBtn}
                    onClick=${() => fetchParams(true)}
                    disabled=${loading}
                >
                    \u21BB Refresh
                </button>
                ${stale
                    ? html`<span style=${STYLES.staleBadge}>Stale</span>`
                    : null}
                ${(stale || error) && paramData.nodes.length > 0
                    ? html`
                          <button
                              style=${STYLES.retryBtn}
                              onClick=${() => fetchParams(true)}
                          >
                              Retry
                          </button>
                      `
                    : null}
            </div>

            <!-- Content -->
            ${loading && paramData.nodes.length === 0
                ? html`<div style=${STYLES.skeleton}>
                      <style>
                          @keyframes shimmer {
                              0% {
                                  background-position: 200% 0;
                              }
                              100% {
                                  background-position: -200% 0;
                              }
                          }
                      </style>
                      ${Array.from(
                          { length: 8 },
                          (_, i) => html`
                              <div
                                  key=${i}
                                  style=${{
                                      ...STYLES.skeletonRow,
                                      width: `${60 + Math.random() * 35}%`,
                                  }}
                              />
                          `,
                      )}
                  </div>`
                : error && paramData.nodes.length === 0
                  ? html`<div style=${STYLES.errorState}>
                        <div style=${{ marginBottom: "12px" }}>${error}</div>
                        <button
                            style=${STYLES.retryBtn}
                            onClick=${() => fetchParams(true)}
                        >
                            Retry
                        </button>
                    </div>`
                  : filteredNodes.length === 0
                    ? html`<div style=${STYLES.empty}>
                          No parameters found.
                      </div>`
                    : filteredNodes.map(
                          (node) => html`
                              <${NodeGroup}
                                  key=${node.name}
                                  node=${node}
                                  expanded=${expandedNodes.has(node.name)}
                                  searchFilter=${searchFilter}
                                  editingParam=${editingParam}
                                  editValue=${editValue}
                                  highlightedKeys=${highlightedKeys}
                                  onToggle=${toggleNode}
                                  onStartEdit=${startEdit}
                                  onEditChange=${handleEditChange}
                                  onSave=${requestSave}
                                  onCancelEdit=${cancelEdit}
                                  entityId=${entityId}
                              />
                          `,
                      )}

            <!-- Confirmation modal -->
            ${showConfirm && editingParam
                ? html`
                      <${ConfirmModal}
                          title="Confirm Parameter Change"
                          body=${`Set ${editingParam.name} on ${editingParam.node} to ${editValue}?`}
                          onConfirm=${confirmSave}
                          onCancel=${() => setShowConfirm(false)}
                      />
                  `
                : null}

            <!-- Toast notification -->
            ${toast
                ? html`
                      <${InlineToast}
                          message=${toast.message}
                          severity=${toast.severity}
                          onDone=${dismissToast}
                      />
                  `
                : null}
        </div>
    `;
}
