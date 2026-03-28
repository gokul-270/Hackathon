/**
 * ParametersTab — Preact component for browsing, searching, and editing
 * ROS2 node parameters.
 *
 * Migrated from vanilla JS ParameterBrowser (parameter_browser.js) as part
 * of task 5.2 of the dashboard-frontend-migration.
 *
 * @module tabs/ParametersTab
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useCallback,
    useMemo,
    useRef,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a parameter value for display.
 * @param {*} value
 * @returns {string}
 */
function formatValue(value) {
    if (value === null || value === undefined) return "null";
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
 * Validate a value string against a ROS2 parameter type.
 * @param {string} value
 * @param {string} type
 * @returns {string|null} Error message or null if valid.
 */
function validateType(value, type) {
    const t = (type || "").toLowerCase();

    if (t === "integer" || t === "int") {
        if (!/^-?\d+$/.test(value.trim())) {
            return `Invalid integer value: "${value}"`;
        }
    } else if (t === "double" || t === "float") {
        if (isNaN(Number(value.trim())) || value.trim() === "") {
            return `Invalid numeric value: "${value}"`;
        }
    } else if (t === "bool" || t === "boolean") {
        const v = value.trim().toLowerCase();
        if (!["true", "false", "0", "1"].includes(v)) {
            return `Invalid boolean value: "${value}" (use true/false/0/1)`;
        }
    } else if (
        t === "byte_array" ||
        t === "bool_array" ||
        t === "integer_array" ||
        t === "double_array" ||
        t === "string_array"
    ) {
        try {
            const parsed = JSON.parse(value);
            if (!Array.isArray(parsed)) {
                return `Expected a JSON array for type "${type}"`;
            }
        } catch {
            return `Invalid JSON array: "${value}"`;
        }
    }
    return null;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Inline edit row — replaces the normal param-row content when editing.
 */
function ParamEditRow({ paramName, currentValue, paramType, onSave, onCancel }) {
    const [editValue, setEditValue] = useState(currentValue);
    const [hasError, setHasError] = useState(false);
    const inputRef = useRef(null);
    const { showToast } = useToast();

    useEffect(() => {
        if (inputRef.current) {
            inputRef.current.focus();
            inputRef.current.select();
        }
    }, []);

    const handleSave = useCallback(() => {
        const error = validateType(editValue, paramType);
        if (error) {
            setHasError(true);
            showToast(error, "error");
            return;
        }
        setHasError(false);
        onSave(editValue);
    }, [editValue, paramType, onSave, showToast]);

    const handleKeyDown = useCallback(
        (e) => {
            if (e.key === "Enter") handleSave();
            if (e.key === "Escape") onCancel();
        },
        [handleSave, onCancel]
    );

    return html`
        <div class="param-edit-row" style="grid-column: 1 / -1;">
            <span class="param-name">${paramName}</span>
            <input
                ref=${inputRef}
                class="param-edit-input${hasError ? " error" : ""}"
                type="text"
                value=${editValue}
                onInput=${(e) => {
                    setEditValue(e.target.value);
                    setHasError(false);
                }}
                onKeyDown=${handleKeyDown}
            />
            <button class="btn btn-sm param-save-btn" onClick=${handleSave}>
                Save
            </button>
            <button class="btn btn-sm param-cancel-btn" onClick=${onCancel}>
                Cancel
            </button>
        </div>
    `;
}

/**
 * A single parameter row — shows name, value, type, and edit button.
 * When editing === this param, shows the inline edit UI instead.
 */
function ParamRow({ nodeName, paramName, paramInfo, editing, onEdit, onSave, onCancel }) {
    const displayValue = formatValue(paramInfo.value);
    const displayType = paramInfo.type || "unknown";
    const isEditing =
        editing &&
        editing.node === nodeName &&
        editing.param === paramName;

    if (isEditing) {
        return html`
            <div class="param-row" data-param=${paramName}>
                <${ParamEditRow}
                    paramName=${paramName}
                    currentValue=${displayValue}
                    paramType=${displayType}
                    onSave=${onSave}
                    onCancel=${onCancel}
                />
            </div>
        `;
    }

    return html`
        <div class="param-row" data-param=${paramName}>
            <span class="param-name">${paramName}</span>
            <span class="param-value">${displayValue}</span>
            <span class="param-type">${displayType}</span>
            <button
                class="param-edit-btn"
                title="Edit parameter"
                onClick=${() => onEdit(nodeName, paramName)}
            >\u270E</button>
        </div>
    `;
}

/**
 * A collapsible node group — header + parameter rows.
 */
function NodeGroup({
    nodeName,
    nodeParams,
    expanded,
    searchQuery,
    editing,
    onToggle,
    onRefreshNode,
    onEdit,
    onSave,
    onCancel,
}) {
    const paramEntries = useMemo(() => {
        const entries = Object.entries(nodeParams).sort(([a], [b]) =>
            a.localeCompare(b)
        );
        if (!searchQuery) return entries;
        const lowerQ = searchQuery.toLowerCase();
        return entries.filter(([name]) =>
            name.toLowerCase().includes(lowerQ)
        );
    }, [nodeParams, searchQuery]);

    // Hide the entire group if search yields no matching params
    if (searchQuery && paramEntries.length === 0) return null;

    const count = paramEntries.length;
    const collapsed = !expanded;

    return html`
        <div class="param-node-group" data-node=${nodeName}>
            <div
                class="param-node-header${collapsed ? " collapsed" : ""}"
                data-node=${nodeName}
                onClick=${() => onToggle(nodeName)}
            >
                <span class="node-name">${nodeName}</span>
                <span class="param-count">${count} param${count !== 1 ? "s" : ""}</span>
                <button
                    class="param-node-refresh"
                    title="Refresh this node"
                    onClick=${(e) => {
                        e.stopPropagation();
                        onRefreshNode(nodeName);
                    }}
                >\u21BB</button>
                <span class="collapse-icon">\u25BC</span>
            </div>
            <div class="param-node-body${collapsed ? " collapsed" : ""}">
                ${paramEntries.map(
                    ([pName, pInfo]) => html`
                        <${ParamRow}
                            key=${pName}
                            nodeName=${nodeName}
                            paramName=${pName}
                            paramInfo=${pInfo}
                            editing=${editing}
                            onEdit=${onEdit}
                            onSave=${(value) => onSave(nodeName, pName, value)}
                            onCancel=${onCancel}
                        />
                    `
                )}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function ParametersTab() {
    const [params, setParams] = useState({});
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [expandedNodes, setExpandedNodes] = useState(new Set());
    const [editing, setEditing] = useState(null);
    const { showToast } = useToast();

    // -----------------------------------------------------------------------
    // Data fetching
    // -----------------------------------------------------------------------

    const loadAllParams = useCallback(async () => {
        setLoading(true);
        const data = await safeFetch("/api/parameters/all");
        if (data) {
            setParams(data);
            // Expand all nodes on first load if nothing is expanded yet
            setExpandedNodes((prev) => {
                if (prev.size === 0) {
                    return new Set(Object.keys(data));
                }
                return prev;
            });
        } else {
            showToast("Failed to load parameters", "error");
        }
        setLoading(false);
    }, [showToast]);

    useEffect(() => {
        loadAllParams();
    }, [loadAllParams]);

    // -----------------------------------------------------------------------
    // Actions
    // -----------------------------------------------------------------------

    const refreshNode = useCallback(
        async (nodeName) => {
            const data = await safeFetch("/api/parameters/all");
            if (data) {
                setParams(data);
            } else {
                showToast(`Failed to refresh node ${nodeName}`, "error");
            }
        },
        [showToast]
    );

    const saveParam = useCallback(
        async (node, param, value) => {
            const url = `/api/nodes/${encodeURIComponent(node)}/parameters/${encodeURIComponent(param)}`;
            const result = await safeFetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ value }),
            });

            if (result && !result.error) {
                showToast(`Parameter ${param} updated successfully`, "success");
                setEditing(null);
                await refreshNode(node);
                return true;
            }

            const msg = (result && result.error) || `Failed to update ${param}`;
            showToast(msg, "error");
            return false;
        },
        [showToast, refreshNode]
    );

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

    const startEdit = useCallback((node, param) => {
        setEditing({ node, param });
    }, []);

    const cancelEdit = useCallback(() => {
        setEditing(null);
    }, []);

    // -----------------------------------------------------------------------
    // Derived data
    // -----------------------------------------------------------------------

    const sortedNodeNames = useMemo(
        () => Object.keys(params).sort(),
        [params]
    );

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------

    return html`
        <div class="section-header">
            <h2>Parameters</h2>
            <div class="section-actions">
                <input
                    type="text"
                    class="search-input"
                    placeholder="Search parameters..."
                    value=${searchQuery}
                    onInput=${(e) => setSearchQuery(e.target.value)}
                />
                <button
                    class="btn btn-sm"
                    onClick=${loadAllParams}
                    disabled=${loading}
                >
                    Refresh All
                </button>
            </div>
        </div>

        <div class="parameter-tree">
            ${loading && sortedNodeNames.length === 0
                ? html`<div class="loading">Loading parameters...</div>`
                : sortedNodeNames.length === 0
                  ? html`<div class="empty-state">No parameters found</div>`
                  : sortedNodeNames.map(
                        (nodeName) => html`
                            <${NodeGroup}
                                key=${nodeName}
                                nodeName=${nodeName}
                                nodeParams=${params[nodeName]}
                                expanded=${expandedNodes.has(nodeName)}
                                searchQuery=${searchQuery}
                                editing=${editing}
                                onToggle=${toggleNode}
                                onRefreshNode=${refreshNode}
                                onEdit=${startEdit}
                                onSave=${saveParam}
                                onCancel=${cancelEdit}
                            />
                        `
                    )}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Register with the Preact app shell
// ---------------------------------------------------------------------------

registerTab("parameters", ParametersTab);

export { ParametersTab };
