/**
 * OperationsTab — Operations page for running sync.sh deployment and
 * maintenance operations against entity targets.
 *
 * Layout: target selector (top), operation button grid (middle),
 * progress + terminal output (bottom).
 *
 * Tasks: 3.1 (layout), 3.2 (target selector), 3.3 (button grid),
 *        3.4 (route), 6.2 (E2E wiring), 6.3 (availability check).
 *
 * @module tabs/OperationsTab
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useCallback,
    useRef,
    useMemo,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { registerTab } from "../tabRegistry.js";
import { TerminalOutput } from "../components/TerminalOutput.mjs";
import { OperationProgress } from "../components/OperationProgress.mjs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Navigation shortcuts — disabled; these were confusing when mixed with operations. */
const NAV_SHORTCUTS = [];

/** Group operations for the button grid. */
const OPERATION_GROUPS = [
    {
        name: "Deployment",
        ops: ["deploy-cross", "deploy-cross-restart", "deploy-local", "build", "quick-sync"],
    },
    {
        name: "Configuration",
        ops: ["provision", "set-role", "set-arm-identity", "set-mqtt-address"],
    },
    {
        name: "Maintenance",
        ops: ["collect-logs", "verify", "restart", "test-mqtt", "time-sync"],
    },
];

/** Icons per operation (Unicode). */
const OP_ICONS = {
    "deploy-cross": "\uD83D\uDE80",  // 🚀
    "deploy-cross-restart": "\uD83D\uDD04",  // 🔄
    "deploy-local": "\uD83D\uDCE6",  // 📦
    "build": "\uD83D\uDD28",         // 🔨
    "quick-sync": "\u26A1",          // ⚡
    "provision": "\uD83D\uDD27",     // 🔧
    "set-role": "\uD83C\uDFAD",      // 🎭
    "set-arm-identity": "\uD83E\uDD16", // 🤖
    "set-mqtt-address": "\uD83D\uDCE1", // 📡
    "collect-logs": "\uD83D\uDCCB",  // 📋
    "verify": "\u2705",              // ✅
    "restart": "\uD83D\uDD04",       // 🔄
    "test-mqtt": "\uD83E\uDDEA",     // 🧪
    "time-sync": "\u23F0",            // ⏰
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const STYLES = {
    container: {
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        padding: "16px",
        height: "100%",
        overflow: "auto",
    },
    banner: {
        background: "var(--color-error)",
        color: "#fff",
        padding: "12px 16px",
        borderRadius: "var(--radius-md)",
        fontWeight: "bold",
    },
    section: {
        background: "var(--color-bg-surface)",
        borderRadius: "var(--radius-md)",
        padding: "16px",
        border: "1px solid var(--color-border)",
    },
    sectionTitle: {
        margin: "0 0 12px 0",
        fontSize: "14px",
        fontWeight: 600,
        color: "var(--color-text-muted)",
        textTransform: "uppercase",
        letterSpacing: "0.5px",
    },
    targetRow: {
        display: "flex",
        flexWrap: "wrap",
        gap: "8px",
        alignItems: "center",
    },
    chip: {
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "4px 10px",
        borderRadius: "16px",
        fontSize: "13px",
        cursor: "pointer",
        border: "2px solid transparent",
        transition: "all 0.15s ease",
    },
    chipSelected: {
        borderColor: "var(--color-accent)",
        background: "color-mix(in srgb, var(--color-accent) 15%, transparent)",
        color: "#fff",
    },
    chipUnselected: {
        borderColor: "var(--color-border)",
        background: "transparent",
        color: "var(--color-text-muted)",
    },
    allChip: {
        fontWeight: "bold",
    },
    manualIpRow: {
        display: "flex",
        gap: "8px",
        alignItems: "center",
        marginTop: "8px",
    },
    input: {
        background: "var(--color-bg-tertiary)",
        border: "1px solid var(--color-border)",
        borderRadius: "6px",
        padding: "6px 10px",
        color: "var(--color-text-primary)",
        fontSize: "13px",
        outline: "none",
    },
    addBtn: {
        background: "var(--color-accent)",
        color: "#fff",
        border: "none",
        borderRadius: "6px",
        padding: "6px 14px",
        cursor: "pointer",
        fontSize: "13px",
    },
    grid: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
        gap: "8px",
    },
    groupLabel: {
        gridColumn: "1 / -1",
        fontSize: "12px",
        fontWeight: 600,
        color: "var(--color-text-muted)",
        textTransform: "uppercase",
        marginTop: "8px",
        marginBottom: "2px",
    },
    opBtn: {
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "4px",
        padding: "12px 8px",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--color-border)",
        background: "var(--color-bg-surface)",
        color: "var(--color-text-primary)",
        cursor: "pointer",
        fontSize: "13px",
        transition: "all 0.15s ease",
        textAlign: "center",
        minHeight: "70px",
    },
    opBtnDisabled: {
        opacity: 0.5,
        cursor: "not-allowed",
    },
    opBtnActive: {
        borderColor: "var(--color-accent)",
        background: "color-mix(in srgb, var(--color-accent) 10%, transparent)",
    },
    opIcon: {
        fontSize: "22px",
    },
    opLabel: {
        fontSize: "12px",
        fontWeight: 500,
    },
    paramBox: {
        background: "var(--color-bg-secondary)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-md)",
        padding: "12px 16px",
        display: "flex",
        gap: "12px",
        alignItems: "flex-end",
        flexWrap: "wrap",
    },
    paramField: {
        display: "flex",
        flexDirection: "column",
        gap: "4px",
    },
    paramLabel: {
        fontSize: "12px",
        color: "var(--color-text-muted)",
    },
    runBtn: {
        background: "var(--color-success)",
        color: "#fff",
        border: "none",
        borderRadius: "6px",
        padding: "8px 20px",
        cursor: "pointer",
        fontSize: "14px",
        fontWeight: 600,
    },
    cancelBtn: {
        background: "var(--color-error)",
        color: "#fff",
        border: "none",
        borderRadius: "6px",
        padding: "8px 20px",
        cursor: "pointer",
        fontSize: "14px",
        fontWeight: 600,
    },
    actionRow: {
        display: "flex",
        gap: "12px",
        alignItems: "center",
        flexWrap: "wrap",
    },
    statusText: {
        fontSize: "13px",
        color: "var(--color-text-muted)",
    },
    groupHeader: {
        display: "flex",
        alignItems: "center",
        gap: "6px",
        padding: "4px 0",
        cursor: "pointer",
        fontSize: "12px",
        fontWeight: 600,
        color: "var(--color-text-muted)",
        textTransform: "uppercase",
        letterSpacing: "0.5px",
        width: "100%",
    },
    statusDot: {
        display: "inline-block",
        width: "8px",
        height: "8px",
        borderRadius: "50%",
        flexShrink: 0,
    },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function OperationsTab() {
    const { showToast } = useToast();
    const mountedRef = useRef(true);

    // -- State: availability -----------------------------------------------
    const [available, setAvailable] = useState(null); // null=loading, true/false
    const [definitions, setDefinitions] = useState({});

    // -- State: entities / targets -----------------------------------------
    const [entities, setEntities] = useState([]);
    const [selectedIds, setSelectedIds] = useState(new Set());
    const [allSelected, setAllSelected] = useState(false);
    const [manualIp, setManualIp] = useState("");
    const [manualTargets, setManualTargets] = useState([]); // raw IPs added manually

    // -- State: operation --------------------------------------------------
    const [selectedOp, setSelectedOp] = useState(null);
    const [params, setParams] = useState({});
    const [operationId, setOperationId] = useState(null);
    const [running, setRunning] = useState(false);
    const [targets, setTargets] = useState([]); // per-target status from SSE
    const [isComplete, setIsComplete] = useState(false);

    // -- Cleanup on unmount ------------------------------------------------
    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
        };
    }, []);

    // -- Fetch availability and definitions on mount -----------------------
    useEffect(() => {
        async function load() {
            const [avail, defs, ents] = await Promise.all([
                safeFetch("/api/operations/available"),
                safeFetch("/api/operations/definitions"),
                safeFetch("/api/entities"),
            ]);
            if (!mountedRef.current) return;

            if (avail && typeof avail.available === "boolean") {
                setAvailable(avail.available);
            } else {
                setAvailable(false);
            }

            if (defs) {
                setDefinitions(defs);
            }

            if (Array.isArray(ents)) {
                setEntities(ents);
            } else if (ents && Array.isArray(ents.entities)) {
                setEntities(ents.entities);
            }
        }
        load();
    }, []);

    // -- Derived: group entities by group_id --------------------------------
    const groupedEntities = useMemo(() => {
        const groups = {};
        const ungrouped = [];
        for (const ent of entities) {
            // Skip only the local dev entity
            if (ent.source === "local" && ent.entity_type === "dev") continue;
            const gid = ent.group_id || null;
            if (gid) {
                if (!groups[gid]) groups[gid] = [];
                groups[gid].push(ent);
            } else {
                ungrouped.push(ent);
            }
        }
        return { groups, ungrouped };
    }, [entities]);

    // -- Target selection --------------------------------------------------
    const toggleTarget = useCallback(
        (id) => {
            setAllSelected(false);
            setSelectedIds((prev) => {
                const next = new Set(prev);
                if (next.has(id)) {
                    next.delete(id);
                } else {
                    next.add(id);
                }
                return next;
            });
        },
        []
    );

    const toggleAll = useCallback(() => {
        setAllSelected((prev) => {
            if (!prev) {
                setSelectedIds(new Set());
            }
            return !prev;
        });
    }, []);

    const toggleGroup = useCallback(
        (groupId) => {
            setAllSelected(false);
            const groupEnts = groupedEntities.groups[groupId] || [];
            const groupIds = groupEnts.map((e) => e.id);
            setSelectedIds((prev) => {
                const next = new Set(prev);
                const allIn = groupIds.every((id) => next.has(id));
                if (allIn) {
                    groupIds.forEach((id) => next.delete(id));
                } else {
                    groupIds.forEach((id) => next.add(id));
                }
                return next;
            });
        },
        [groupedEntities]
    );

    const addManualIp = useCallback(() => {
        const ip = manualIp.trim();
        if (!ip) return;
        // Basic IPv4 check
        if (!/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(ip)) {
            showToast("Invalid IP address format", "error");
            return;
        }
        setManualTargets((prev) =>
            prev.includes(ip) ? prev : [...prev, ip]
        );
        setManualIp("");
    }, [manualIp, showToast]);

    const removeManualIp = useCallback((ip) => {
        setManualTargets((prev) => prev.filter((t) => t !== ip));
    }, []);

    // Build target_ids for the API
    const targetIds = useMemo(() => {
        if (allSelected) return ["all"];
        const ids = [...selectedIds];
        return [...ids, ...manualTargets];
    }, [allSelected, selectedIds, manualTargets]);

    // -- Operation selection -----------------------------------------------
    const selectOp = useCallback(
        (opName) => {
            if (running) return;
            setSelectedOp((prev) => (prev === opName ? null : opName));
            setParams({});
        },
        [running]
    );

    const opParams = useMemo(() => {
        if (!selectedOp || !definitions[selectedOp]) return [];
        return definitions[selectedOp].params || [];
    }, [selectedOp, definitions]);

    // -- Run operation -----------------------------------------------------
    const runOperation = useCallback(async () => {
        if (!selectedOp || targetIds.length === 0) {
            showToast("Select an operation and at least one target", "error");
            return;
        }

        const body = {
            operation: selectedOp,
            target_ids: targetIds,
            params,
        };

        setRunning(true);
        setIsComplete(false);
        setTargets([]);

        const result = await safeFetch("/api/operations/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!mountedRef.current) return;

        if (result && result.operation_id) {
            setOperationId(result.operation_id);
            // Initialize target state from response
            if (Array.isArray(result.targets)) {
                setTargets(result.targets);
            }
            showToast(
                `Operation "${selectedOp}" started on ${targetIds.length} target(s)`,
                "success"
            );
        } else {
            setRunning(false);
            const detail =
                (result && result.detail) || "Failed to start operation";
            showToast(detail, "error");
        }
    }, [selectedOp, targetIds, params, showToast]);

    // -- Cancel operation --------------------------------------------------
    const cancelOperation = useCallback(async () => {
        if (!operationId) return;

        const result = await safeFetch(
            `/api/operations/${operationId}/cancel`,
            { method: "POST" }
        );

        if (!mountedRef.current) return;

        if (result) {
            showToast("Operation cancelled", "info");
        } else {
            showToast("Failed to cancel operation", "error");
        }
    }, [operationId, showToast]);

    // -- Handle SSE events from TerminalOutput -----------------------------
    const handleEvent = useCallback(
        (event) => {
            if (!mountedRef.current) return;

            if (event.event === "start") {
                setTargets((prev) =>
                    prev.map((t) =>
                        t.target_id === event.target
                            ? { ...t, status: "running" }
                            : t
                    )
                );
            } else if (event.event === "complete") {
                setTargets((prev) =>
                    prev.map((t) =>
                        t.target_id === event.target
                            ? {
                                  ...t,
                                  status:
                                      event.exit_code === 0
                                          ? "success"
                                          : "failed",
                                  exit_code: event.exit_code,
                              }
                            : t
                    )
                );
            } else if (event.event === "timeout") {
                setTargets((prev) =>
                    prev.map((t) =>
                        t.target_id === event.target
                            ? { ...t, status: "timeout" }
                            : t
                    )
                );
            } else if (event.event === "error") {
                setTargets((prev) =>
                    prev.map((t) =>
                        t.target_id === event.target
                            ? { ...t, status: "failed" }
                            : t
                    )
                );
            } else if (event.event === "cancelled") {
                setTargets((prev) =>
                    prev.map((t) =>
                        t.target_id === event.target
                            ? { ...t, status: "cancelled" }
                            : t
                    )
                );
            } else if (event.event === "operation_complete") {
                setIsComplete(true);
                setRunning(false);
                setOperationId(null);
            }
        },
        []
    );

    // -- Render: unavailable banner ----------------------------------------
    if (available === false) {
        return html`
            <div style=${STYLES.container}>
                <div style=${STYLES.banner}>
                    sync.sh not found on server. Operations are unavailable.
                    Ensure sync.sh exists at the repository root.
                </div>
            </div>
        `;
    }

    if (available === null) {
        return html`
            <div style=${STYLES.container}>
                <div style=${STYLES.statusText}>
                    Checking operations availability...
                </div>
            </div>
        `;
    }

    // -- Render ------------------------------------------------------------
    return html`
        <div style=${STYLES.container}>
            <!-- Target Selector -->
            <div style=${STYLES.section}>
                <h3 style=${STYLES.sectionTitle}>Targets</h3>
                <div style=${STYLES.targetRow}>
                    <div
                        style=${{
                            ...STYLES.chip,
                            ...STYLES.allChip,
                            ...(allSelected
                                ? STYLES.chipSelected
                                : STYLES.chipUnselected),
                        }}
                        onClick=${toggleAll}
                        title="Select all online, configured entities"
                    >
                        All
                    </div>
                </div>

                <!-- Grouped entities -->
                ${Object.entries(groupedEntities.groups).map(
                    ([groupId, groupEnts]) => {
                        const groupIds = groupEnts.map((e) => e.id);
                        const allGroupSelected = !allSelected && groupIds.every((id) => selectedIds.has(id));
                        return html`
                            <div key=${groupId} style=${{ marginTop: "8px" }}>
                                <div
                                    style=${STYLES.groupHeader}
                                    onClick=${() => toggleGroup(groupId)}
                                    title="Click to select/deselect entire group"
                                >
                                    <input
                                        type="checkbox"
                                        checked=${allSelected || allGroupSelected}
                                        readOnly
                                        style=${{ cursor: "pointer" }}
                                    />
                                    ${groupId}
                                    <span style=${{ fontWeight: "normal", opacity: 0.6 }}>
                                        (${groupEnts.length})
                                    </span>
                                </div>
                                <div style=${STYLES.targetRow}>
                                    ${groupEnts.map(
                                        (ent) => html`
                                            <div
                                                key=${ent.id}
                                                style=${{
                                                    ...STYLES.chip,
                                                    ...(allSelected || selectedIds.has(ent.id)
                                                        ? STYLES.chipSelected
                                                        : STYLES.chipUnselected),
                                                }}
                                                onClick=${() => toggleTarget(ent.id)}
                                                title=${ent.ip || "No IP"}
                                            >
                                                <span
                                                    style=${{
                                                        ...STYLES.statusDot,
                                                        background:
                                                            ent.status === "online"
                                                                ? "var(--color-success, #22c55e)"
                                                                : ent.status === "degraded"
                                                                  ? "var(--color-warning, #f59e0b)"
                                                                  : "var(--color-error, #ef4444)",
                                                    }}
                                                ></span>
                                                <span>${ent.name || ent.id}</span>
                                                ${ent.ip
                                                    ? html`<span
                                                          style=${{
                                                              fontSize: "11px",
                                                              opacity: 0.7,
                                                          }}
                                                          >(${ent.ip})</span
                                                      >`
                                                    : null}
                                            </div>
                                        `
                                    )}
                                </div>
                            </div>
                        `;
                    }
                )}

                <!-- Ungrouped entities -->
                ${groupedEntities.ungrouped.length > 0 && html`
                    <div style=${{ marginTop: "8px" }}>
                        <div style=${STYLES.groupHeader}>Ungrouped</div>
                        <div style=${STYLES.targetRow}>
                            ${groupedEntities.ungrouped.map(
                                (ent) => html`
                                    <div
                                        key=${ent.id}
                                        style=${{
                                            ...STYLES.chip,
                                            ...(selectedIds.has(ent.id) && !allSelected
                                                ? STYLES.chipSelected
                                                : STYLES.chipUnselected),
                                        }}
                                        onClick=${() => toggleTarget(ent.id)}
                                        title=${ent.ip || "No IP"}
                                    >
                                        <span
                                            style=${{
                                                ...STYLES.statusDot,
                                                background:
                                                    ent.status === "online"
                                                        ? "var(--color-success, #22c55e)"
                                                        : "var(--color-error, #ef4444)",
                                            }}
                                        ></span>
                                        <span>${ent.name || ent.id}</span>
                                    </div>
                                `
                            )}
                        </div>
                    </div>
                `}

                <!-- Manual IP targets -->
                ${manualTargets.length > 0 && html`
                    <div style=${{ ...STYLES.targetRow, marginTop: "8px" }}>
                        ${manualTargets.map(
                            (ip) => html`
                                <div
                                    key=${ip}
                                    style=${{
                                        ...STYLES.chip,
                                        ...STYLES.chipSelected,
                                    }}
                                >
                                    <span>${ip}</span>
                                    <span
                                        style=${{
                                            cursor: "pointer",
                                            marginLeft: "4px",
                                        }}
                                        onClick=${() => removeManualIp(ip)}
                                        >\u00D7</span
                                    >
                                </div>
                            `
                        )}
                    </div>
                `}
                <div style=${STYLES.manualIpRow}>
                    <input
                        type="text"
                        placeholder="Manual IP (e.g. 192.168.1.100)"
                        value=${manualIp}
                        onInput=${(e) => setManualIp(e.target.value)}
                        onKeyDown=${(e) =>
                            e.key === "Enter" && addManualIp()}
                        style=${{ ...STYLES.input, width: "220px" }}
                    />
                    <button style=${STYLES.addBtn} onClick=${addManualIp}>
                        Add
                    </button>
                </div>
            </div>

            <!-- Operation Button Grid -->
            <div style=${STYLES.section}>
                <h3 style=${STYLES.sectionTitle}>Operations</h3>
                <div style=${STYLES.grid}>
                    ${NAV_SHORTCUTS.map(
                        (nav) => html`
                            <button
                                key=${nav.id}
                                style=${{
                                    ...STYLES.opBtn,
                                    borderColor: "var(--color-accent)",
                                    background: "color-mix(in srgb, var(--color-accent) 8%, transparent)",
                                }}
                                onClick=${() => {
                                    window.location.hash = nav.id;
                                }}
                                title=${"Go to " + nav.label}
                            >
                                <span style=${STYLES.opIcon}>${nav.icon}</span>
                                <span style=${STYLES.opLabel}>${nav.label}</span>
                            </button>
                        `
                    )}
                    ${OPERATION_GROUPS.map(
                        (group) => html`
                            <div
                                key=${group.name}
                                style=${STYLES.groupLabel}
                            >
                                ${group.name}
                            </div>
                            ${group.ops.map((opName) => {
                                const defn = definitions[opName];
                                if (!defn) return null;
                                const isActive = selectedOp === opName;
                                const isDisabled = running;
                                return html`
                                    <button
                                        key=${opName}
                                        style=${{
                                            ...STYLES.opBtn,
                                            ...(isDisabled
                                                ? STYLES.opBtnDisabled
                                                : {}),
                                            ...(isActive
                                                ? STYLES.opBtnActive
                                                : {}),
                                        }}
                                        disabled=${isDisabled}
                                        onClick=${() => selectOp(opName)}
                                        title=${defn.description}
                                    >
                                        <span style=${STYLES.opIcon}>
                                            ${OP_ICONS[opName] || "\u2699"}
                                        </span>
                                        <span style=${STYLES.opLabel}>
                                            ${defn.label}
                                        </span>
                                    </button>
                                `;
                            })}
                        `
                    )}
                </div>
            </div>

            <!-- Parameter inputs + Run/Cancel buttons -->
            ${selectedOp
                ? html`
                      <div style=${STYLES.section}>
                          <div style=${STYLES.actionRow}>
                              ${opParams.length > 0
                                  ? html`
                                        <div style=${STYLES.paramBox}>
                                            ${opParams.map(
                                                (p) => html`
                                                    <div
                                                        key=${p}
                                                        style=${STYLES.paramField}
                                                    >
                                                        <label
                                                            style=${STYLES.paramLabel}
                                                            >${p}</label
                                                        >
                                                        ${p === "role"
                                                            ? html`
                                                                  <select
                                                                      style=${STYLES.input}
                                                                      value=${params.role ||
                                                                      ""}
                                                                      onChange=${(
                                                                          e
                                                                      ) =>
                                                                          setParams(
                                                                              (
                                                                                  prev
                                                                              ) => ({
                                                                                  ...prev,
                                                                                  role: e
                                                                                      .target
                                                                                      .value,
                                                                              })
                                                                          )}
                                                                  >
                                                                      <option
                                                                          value=""
                                                                      >
                                                                          Select...
                                                                      </option>
                                                                      <option
                                                                          value="arm"
                                                                      >
                                                                          arm
                                                                      </option>
                                                                      <option
                                                                          value="vehicle"
                                                                      >
                                                                          vehicle
                                                                      </option>
                                                                  </select>
                                                              `
                                                            : p === "arm_id"
                                                              ? html`
                                                                    <select
                                                                        style=${STYLES.input}
                                                                        value=${params.arm_id ||
                                                                        ""}
                                                                        onChange=${(
                                                                            e
                                                                        ) =>
                                                                            setParams(
                                                                                (
                                                                                    prev
                                                                                ) => ({
                                                                                    ...prev,
                                                                                    arm_id: parseInt(
                                                                                        e
                                                                                            .target
                                                                                            .value,
                                                                                        10
                                                                                    ),
                                                                                })
                                                                            )}
                                                                    >
                                                                        <option
                                                                            value=""
                                                                        >
                                                                            Select...
                                                                        </option>
                                                                        ${[
                                                                            1,
                                                                            2,
                                                                            3,
                                                                            4,
                                                                            5,
                                                                            6,
                                                                        ].map(
                                                                            (
                                                                                n
                                                                            ) =>
                                                                                html`<option
                                                                                    key=${n}
                                                                                    value=${n}
                                                                                >
                                                                                    Arm
                                                                                    ${n}
                                                                                </option>`
                                                                        )}
                                                                    </select>
                                                                `
                                                              : html`
                                                                    <input
                                                                        type="text"
                                                                        style=${STYLES.input}
                                                                        placeholder=${p}
                                                                        value=${params[
                                                                            p
                                                                        ] ||
                                                                        ""}
                                                                        onInput=${(
                                                                            e
                                                                        ) =>
                                                                            setParams(
                                                                                (
                                                                                    prev
                                                                                ) => ({
                                                                                    ...prev,
                                                                                    [p]: e
                                                                                        .target
                                                                                        .value,
                                                                                })
                                                                            )}
                                                                    />
                                                                `}
                                                    </div>
                                                `
                                            )}
                                        </div>
                                    `
                                  : null}
                              ${!running
                                  ? html`
                                        <button
                                            style=${{
                                                ...STYLES.runBtn,
                                                ...(targetIds.length === 0
                                                    ? { opacity: 0.5 }
                                                    : {}),
                                            }}
                                            disabled=${targetIds.length === 0}
                                            onClick=${runOperation}
                                        >
                                            Run
                                            ${definitions[selectedOp]
                                                ?.label || selectedOp}
                                        </button>
                                    `
                                  : html`
                                        <button
                                            style=${STYLES.cancelBtn}
                                            onClick=${cancelOperation}
                                        >
                                            Cancel
                                        </button>
                                        <span style=${STYLES.statusText}>
                                            Running...
                                        </span>
                                    `}
                          </div>
                      </div>
                  `
                : null}

            <!-- Progress badges -->
            ${targets.length > 0
                ? html`
                      <div style=${STYLES.section}>
                          <h3 style=${STYLES.sectionTitle}>Progress</h3>
                          <${OperationProgress}
                              targets=${targets}
                              isComplete=${isComplete}
                          />
                      </div>
                  `
                : null}

            <!-- Terminal output -->
            <div
                style=${{
                    ...STYLES.section,
                    flex: "1 1 auto",
                    minHeight: "300px",
                    display: "flex",
                    flexDirection: "column",
                }}
            >
                <h3 style=${STYLES.sectionTitle}>Output</h3>
                <${TerminalOutput}
                    operationId=${operationId}
                    onEvent=${handleEvent}
                    maxLines=${5000}
                />
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

registerTab("operations", OperationsTab);

export { OperationsTab };
