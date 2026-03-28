/**
 * FleetOverview — Preact component for the Fleet Overview home page.
 *
 * Displays:
 * - Quick-action bar: Refresh All
 * - Responsive grid of EntityCard components (configured entities)
 * - "Discovered" section for mDNS-discovered unconfigured entities
 * - Empty state when no entities are configured
 * - Error state when entity manager is unavailable
 *
 * Data source:
 * - HTTP: GET /api/entities (initial load + polling fallback)
 * - WebSocket: entity_state_changed messages for real-time updates
 * - POST /api/entities/{id}/estop for per-entity emergency stop
 *
 * @module tabs/FleetOverview
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useCallback,
    useContext,
    useRef,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { WebSocketContext, ToastContext } from "../app.js";
import { registerTab } from "../tabRegistry.js";
import { EntityCard } from "../components/EntityCard.mjs";
import { BulkActionBar } from "../components/BulkActionBar.mjs";
import { AddEntityModal } from "../components/AddEntityModal.mjs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 10000;

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Quick-action bar with Refresh All button.
 * E-Stop All has been moved to the dashboard header.
 * @param {object} props
 * @param {Function} props.onRefresh - Called when Refresh All is clicked
 * @param {boolean} props.refreshing - True while refresh is in progress
 */
function QuickActionBar({ onRefresh, refreshing, onAddEntity }) {
    return html`
        <div style=${{
            display: "flex",
            gap: "8px",
            alignItems: "center",
            flexWrap: "wrap",
        }}>
            <button
                class="btn btn-outline"
                onClick=${onAddEntity}
                style=${{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "6px 14px",
                    fontSize: "0.85rem",
                }}
            >
                <span style=${{ fontSize: "1.1rem", lineHeight: "1" }}>+</span> Add Entity
            </button>
            <button
                class="btn"
                onClick=${onRefresh}
                disabled=${refreshing}
                style=${{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "6px 14px",
                    fontSize: "0.85rem",
                }}
            >
                <span style=${{
                    display: "inline-block",
                    animation: refreshing ? "spin 1s linear infinite" : "none",
                }}>${"\u21BB"}</span>
                ${refreshing ? "Refreshing..." : "Refresh All"}
            </button>
        </div>
    `;
}

/**
 * Empty state displayed when no entities are configured.
 */
function EmptyState() {
    return html`
        <div style=${{
            textAlign: "center",
            padding: "60px 20px",
            color: "var(--color-text-muted)",
        }}>
            <div style=${{ fontSize: "3rem", marginBottom: "16px" }}>${"\uD83D\uDD0D"}</div>
            <h3 style=${{
                margin: "0 0 8px 0",
                color: "var(--color-text-primary)",
            }}>No Entities Configured</h3>
            <p style=${{ margin: "0 0 16px 0", maxWidth: "400px", marginInline: "auto" }}>
                No robot entities have been configured yet. Add entities via the
                configuration file or wait for mDNS discovery to find devices on
                the network.
            </p>
            <p style=${{ fontSize: "0.8rem", margin: "0" }}>
                Check <code>configs/entities.yaml</code> or the Settings tab to configure entities.
            </p>
        </div>
    `;
}

/**
 * Error banner when entity manager is unavailable.
 * @param {object} props
 * @param {string} props.message - Error description
 * @param {Function} props.onRetry - Retry callback
 */
function ErrorBanner({ message, onRetry }) {
    return html`
        <div style=${{
            background: "var(--bg-tertiary)",
            border: "1px solid var(--color-error, #ef4444)",
            borderRadius: "var(--radius-md, 8px)",
            padding: "var(--spacing-md, 16px)",
            marginBottom: "var(--spacing-md, 16px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            flexWrap: "wrap",
        }}>
            <div style=${{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                color: "var(--color-error, #ef4444)",
            }}>
                <span style=${{ fontSize: "1.2em" }}>${"\u26A0\uFE0F"}</span>
                <div>
                    <div style=${{ fontWeight: "600" }}>Entity Manager Unavailable</div>
                    <div style=${{
                        fontSize: "0.8rem",
                        color: "var(--color-text-muted)",
                        marginTop: "2px",
                    }}>
                        ${message || "Could not fetch entity data from the backend."}
                    </div>
                </div>
            </div>
            <button
                class="btn"
                onClick=${onRetry}
                style=${{
                    padding: "4px 12px",
                    fontSize: "0.8rem",
                    flexShrink: "0",
                }}
            >
                Retry
            </button>
        </div>
    `;
}

/**
 * Discovered entity card for mDNS-discovered unconfigured entities.
 * Minimal display: hostname, IP, source badge, and "Add to Fleet" button.
 * @param {object} props
 * @param {object} props.entity - Discovered entity data
 * @param {(entity: object) => void} [props.onAddToFleet] - Called when user clicks Add to Fleet
 */
function DiscoveredCard({ entity, onAddToFleet }) {
    return html`
        <div class="stat-card" style=${{
            padding: "12px 16px",
            borderStyle: "dashed",
            opacity: "0.8",
        }}>
            <div style=${{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "8px",
            }}>
                <div style=${{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    minWidth: "0",
                    flex: "1",
                }}>
                    <span style=${{
                        width: "8px",
                        height: "8px",
                        borderRadius: "50%",
                        backgroundColor: "var(--accent-warning, #f59e0b)",
                        flexShrink: "0",
                        display: "inline-block",
                    }}></span>
                    <span style=${{
                        fontWeight: "500",
                        fontSize: "0.9rem",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                    }}>
                        ${entity.name || entity.id || "Unknown Device"}
                    </span>
                </div>
                <span style=${{
                    fontSize: "0.65rem",
                    padding: "2px 6px",
                    borderRadius: "8px",
                    backgroundColor: "var(--bg-tertiary)",
                    border: "1px solid var(--border-color)",
                    color: "var(--color-text-muted)",
                    flexShrink: "0",
                }}>
                    Discovered
                </span>
            </div>
            ${entity.ip && html`
                <div style=${{
                    fontSize: "0.75rem",
                    color: "var(--color-text-muted)",
                    marginTop: "6px",
                }}>
                    IP: ${entity.ip}
                </div>
            `}
            ${entity.entity_type && html`
                <div style=${{
                    fontSize: "0.75rem",
                    color: "var(--color-text-muted)",
                    marginTop: "2px",
                }}>
                    Type: ${entity.entity_type}
                </div>
            `}
            ${onAddToFleet && html`
                <button
                    style=${{
                        marginTop: "8px",
                        padding: "4px 10px",
                        fontSize: "0.75rem",
                        border: "1px solid var(--accent-primary, #3b82f6)",
                        borderRadius: "6px",
                        backgroundColor: "transparent",
                        color: "var(--accent-primary, #3b82f6)",
                        cursor: "pointer",
                        width: "100%",
                    }}
                    onClick=${(e) => {
                        e.stopPropagation();
                        onAddToFleet(entity);
                    }}
                >
                    Add to Fleet
                </button>
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

function FleetOverview() {
    const { data: wsData } = useContext(WebSocketContext);
    const { showToast } = useContext(ToastContext);
    const mountedRef = useRef(true);

    // State
    const [entities, setEntities] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [refreshing, setRefreshing] = useState(false);

    // Add-to-fleet confirmation dialog state
    const [promoteTarget, setPromoteTarget] = useState(null); // entity to promote
    const [promoteType, setPromoteType] = useState("arm");    // selected type
    const [promoteGroup, setPromoteGroup] = useState("machine-1");
    const [promoteSlot, setPromoteSlot] = useState("arm-1");

    // Bulk selection state
    const [selectedIds, setSelectedIds] = useState(new Set());
    const [bulkExecuting, setBulkExecuting] = useState(false);

    // Add Entity modal state
    const [isAddEntityModalOpen, setIsAddEntityModalOpen] = useState(false);

    // Collapse state per group — stored as a Set of collapsed group keys.
    // Persist to localStorage so collapse survives page reload.
    const COLLAPSE_KEY = "fleet-overview-collapsed-groups";
    const [collapsedGroups, setCollapsedGroups] = useState(() => {
        try {
            const stored = localStorage.getItem(COLLAPSE_KEY);
            return stored ? new Set(JSON.parse(stored)) : new Set();
        } catch { return new Set(); }
    });

    const toggleGroupCollapse = useCallback((groupKey) => {
        setCollapsedGroups((prev) => {
            const next = new Set(prev);
            if (next.has(groupKey)) {
                next.delete(groupKey);
            } else {
                next.add(groupKey);
            }
            try { localStorage.setItem(COLLAPSE_KEY, JSON.stringify([...next])); } catch {}
            return next;
        });
    }, []);

    // Collapse state per entity card — collapsed by default.
    // Stores the set of EXPANDED card IDs (since collapsed is default).
    const CARD_COLLAPSE_KEY = "fleet-overview-expanded-cards";
    const [expandedCards, setExpandedCards] = useState(() => {
        try {
            const stored = localStorage.getItem(CARD_COLLAPSE_KEY);
            return stored ? new Set(JSON.parse(stored)) : new Set();
        } catch { return new Set(); }
    });

    const toggleCardCollapse = useCallback((entityId) => {
        setExpandedCards((prev) => {
            const next = new Set(prev);
            if (next.has(entityId)) {
                next.delete(entityId);
            } else {
                next.add(entityId);
            }
            try { localStorage.setItem(CARD_COLLAPSE_KEY, JSON.stringify([...next])); } catch {}
            return next;
        });
    }, []);

    // ---- Data fetching ----

    const loadEntities = useCallback(async () => {
        const data = await safeFetch("/api/entities");
        if (!mountedRef.current) return;

        if (data === null) {
            setError("Could not connect to entity manager. Check backend status.");
            setLoading(false);
            return;
        }

        if (data.error) {
            setError(data.error);
            setLoading(false);
            return;
        }

        // data can be an array directly or { entities: [...] }
        const entityList = Array.isArray(data)
            ? data
            : (data.entities || []);
        setEntities(entityList);
        setError(null);
        setLoading(false);

        // Enrich online entities with introspection node counts so
        // the card's "ROS2 Nodes" number matches the entity-detail
        // Nodes tab (which uses the introspection endpoint).
        // Fire-and-forget — UI already shows heartbeat counts while
        // introspection data loads in the background.
        enrichWithNodeCounts(entityList);
    }, []);

    /**
     * For each online entity with ros2_available, fetch the introspection
     * node list and merge the count back into state.  This ensures the
     * EntityCard node count matches the Nodes tab.
     */
    const enrichWithNodeCounts = useCallback(async (entityList) => {
        const online = entityList.filter(
            (e) => e.ros2_available && e.status === "online"
        );
        if (online.length === 0) return;

        const results = await Promise.allSettled(
            online.map(async (e) => {
                const resp = await safeFetch(
                    `/api/entities/${encodeURIComponent(e.id)}/ros2/nodes`
                );
                if (!resp || resp.error) return null;
                // Response shape: { entity_id, source, data: [...] | { nodes: [...] } }
                const nodeData = resp.data || resp;
                const nodes = Array.isArray(nodeData)
                    ? nodeData
                    : (nodeData.nodes || []);
                return { id: e.id, ros2Nodes: nodes };
            })
        );

        if (!mountedRef.current) return;

        const enriched = {};
        for (const r of results) {
            if (r.status === "fulfilled" && r.value) {
                enriched[r.value.id] = r.value.ros2Nodes;
            }
        }

        if (Object.keys(enriched).length === 0) return;

        setEntities((prev) =>
            prev.map((e) =>
                enriched[e.id] != null
                    ? { ...e, ros2Nodes: enriched[e.id] }
                    : e
            )
        );
    }, []);

    // ---- WebSocket real-time updates ----

    useEffect(() => {
        if (!wsData) return;

        // Listen for entity_state_changed messages
        if (wsData.entity_state_changed) {
            const updated = wsData.entity_state_changed;
            if (updated && updated.id) {
                setEntities((prev) => {
                    const idx = prev.findIndex((e) => e.id === updated.id);
                    if (idx >= 0) {
                        const next = [...prev];
                        next[idx] = { ...next[idx], ...updated };
                        return next;
                    }
                    // New entity — append
                    return [...prev, updated];
                });
            }
        }

        // Listen for entity_removed
        if (wsData.entity_removed) {
            const removed = wsData.entity_removed;
            if (removed && removed.id) {
                setEntities((prev) => prev.filter(e => e.id !== removed.id));
            }
        }

        // Listen for entity_updated
        if (wsData.entity_updated) {
            const updated = wsData.entity_updated;
            if (updated && updated.id) {
                setEntities((prev) => {
                    return prev.map(e => e.id === updated.id ? { ...e, ...updated } : e);
                });
            }
        }

        // Listen for entity_added (manual addition)
        if (wsData.entity_added) {
            const added = wsData.entity_added;
            if (added && added.id) {
                setEntities((prev) => {
                    const existing = prev.find((e) => e.id === added.id);
                    if (!existing) {
                        return [...prev, added];
                    }
                    return prev;
                });
            }
        }

        // Listen for entity_discovered for mDNS entities
        if (wsData.entity_discovered) {
            const discovered = wsData.entity_discovered;
            if (discovered && discovered.id) {
                setEntities((prev) => {
                    const existing = prev.find((e) => e.id === discovered.id);
                    if (!existing) {
                        return [...prev, discovered];
                    }
                    return prev;
                });
            }
        }
    }, [wsData]);

    // ---- Lifecycle ----

    useEffect(() => {
        mountedRef.current = true;
        loadEntities();
        return () => {
            mountedRef.current = false;
        };
    }, [loadEntities]);

    // ---- Polling ----

    useEffect(() => {
        const id = setInterval(loadEntities, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [loadEntities]);

    // ---- Actions ----

    const handleRefresh = useCallback(async () => {
        setRefreshing(true);
        await loadEntities();
        if (mountedRef.current) {
            setRefreshing(false);
            showToast("Fleet data refreshed", "info");
        }
    }, [loadEntities, showToast]);

    const handleResumePolling = useCallback(async (entityId) => {
        try {
            const response = await fetch(
                `/api/entities/${encodeURIComponent(entityId)}/resume-polling`,
                { method: "POST" }
            );
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                const msg = payload?.detail || `Failed with HTTP ${response.status}`;
                showToast(typeof msg === "string" ? msg : JSON.stringify(msg), "error");
                return;
            }
            const data = await response.json();
            if (data.was_suspended) {
                showToast(`Resumed polling for ${entityId}`, "success");
            } else {
                showToast(`${entityId} was not suspended`, "info");
            }
            await loadEntities();
        } catch (err) {
            showToast(`Network error: ${err.message}`, "error");
        }
    }, [loadEntities, showToast]);

    // ---- Add to Fleet (promote discovered entity) ----

    const handleAddToFleetClick = useCallback((entity) => {
        setPromoteTarget(entity);
        setPromoteType("arm"); // reset to default
        setPromoteGroup("machine-1");
        setPromoteSlot("arm-1");
    }, []);

    const handlePromoteConfirm = useCallback(async () => {
        if (!promoteTarget) return;
        const entity = promoteTarget;
        const slotValid = promoteType === "vehicle"
            ? promoteSlot === "vehicle"
            : /^arm-[1-9][0-9]*$/.test(promoteSlot);
        if (!promoteGroup || !promoteSlot || !slotValid) {
            showToast(
                promoteType === "vehicle"
                    ? "Vehicle slot must be vehicle"
                    : "Arm slot must be arm-N (e.g. arm-3)",
                "error"
            );
            return;
        }
        try {
            const response = await fetch(
                `/api/entities/discovered/${encodeURIComponent(entity.id)}/add`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        entity_type: promoteType,
                        group_id: promoteGroup,
                        slot: promoteSlot,
                    }),
                }
            );

            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                const detail = payload?.detail || {};
                const msg = typeof detail === "string"
                    ? detail
                    : (detail.error || `Failed with HTTP ${response.status}`);
                showToast(msg, "error");
                return;
            }

            setPromoteTarget(null);
            showToast(
                `Added ${entity.name || entity.ip || entity.id} to ${promoteGroup}/${promoteSlot}`,
                "success"
            );
            await loadEntities();
        } catch {
            showToast("Failed to add discovered candidate", "error");
        }
    }, [promoteTarget, promoteType, promoteGroup, promoteSlot, showToast, loadEntities]);

    const handlePromoteCancel = useCallback(() => {
        setPromoteTarget(null);
    }, []);

    // ---- Derived data ----

    // Split entities into configured vs discovered
    const configuredEntities = entities.filter(
        (e) => e.source !== "mdns_discovered" && e.source !== "discovered"
    );
    const discoveredEntities = entities.filter(
        (e) => e.source === "mdns_discovered" || e.source === "discovered"
    );

    const localControlPlaneEntities = configuredEntities.filter(
        (e) => e.source === "local" || e.id === "local"
    );
    const approvedEntities = configuredEntities.filter(
        (e) => !localControlPlaneEntities.some((local) => local.id === e.id)
    );

    const preferredGroupOrder = ["tabletop-lab", "machine-1"];
    const groupedApproved = approvedEntities.reduce((acc, entity) => {
        const key = entity.group_id || "unassigned";
        if (!acc[key]) {
            acc[key] = [];
        }
        acc[key].push(entity);
        return acc;
    }, {});

    const orderedGroupKeys = Object.keys(groupedApproved).sort((a, b) => {
        const ia = preferredGroupOrder.indexOf(a);
        const ib = preferredGroupOrder.indexOf(b);
        if (ia !== -1 || ib !== -1) {
            if (ia === -1) return 1;
            if (ib === -1) return -1;
            return ia - ib;
        }
        return a.localeCompare(b);
    });

    // ---- Bulk selection callbacks ----

    const handleToggleSelect = useCallback((entityId) => {
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (next.has(entityId)) {
                next.delete(entityId);
            } else {
                next.add(entityId);
            }
            return next;
        });
    }, []);

    const handleSelectAll = useCallback(() => {
        const allIds = new Set(configuredEntities.map((e) => e.id));
        setSelectedIds(allIds);
    }, [configuredEntities]);

    const handleDeselectAll = useCallback(() => {
        setSelectedIds(new Set());
    }, []);

    const handleSelectionChange = useCallback((newSelectedIds) => {
        setSelectedIds(newSelectedIds);
    }, []);

    // ---- Stale selection cleanup ----
    // Remove selected IDs that no longer exist in the entity list

    useEffect(() => {
        const entityIds = new Set(configuredEntities.map((e) => e.id));
        setSelectedIds((prev) => {
            let changed = false;
            const next = new Set();
            for (const id of prev) {
                if (entityIds.has(id)) {
                    next.add(id);
                } else {
                    changed = true;
                }
            }
            return changed ? next : prev;
        });
    }, [configuredEntities]);

    // ---- Render ----

    if (loading) {
        return html`
            <div class="loading" style=${{ textAlign: "center", padding: "var(--spacing-xl, 40px)" }}>
                Loading fleet data...
            </div>
        `;
    }

    return html`
        <div class="section-header" style=${{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "12px",
        }}>
            <h2 style=${{ margin: "0" }}>Fleet Overview</h2>
            <${QuickActionBar}
                onRefresh=${handleRefresh}
                refreshing=${refreshing}
                onAddEntity=${() => setIsAddEntityModalOpen(true)}
            />
        </div>

        <div style=${{
            marginTop: "8px",
            fontSize: "0.8rem",
            color: "var(--color-text-muted)",
        }}>
            P0 scope: compare/copy workflows and full auth rollout remain deferred.
        </div>

        <!-- Error banner -->
        ${error && html`
            <${ErrorBanner}
                message=${error}
                onRetry=${handleRefresh}
            />
        `}

        <!-- Configured entities grid -->
        ${!error && configuredEntities.length === 0 && discoveredEntities.length === 0 && html`
            <${EmptyState} />
        `}

        ${localControlPlaneEntities.length > 0 && html`
            <div style=${{ marginTop: "16px" }}>
                <h3 style=${{
                    fontSize: "1rem",
                    color: "var(--color-text-muted)",
                    marginBottom: "10px",
                }}>
                    Control Plane Host
                </h3>
                <div style=${{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                    gap: "16px",
                }}>
                    ${localControlPlaneEntities.map(
                        (entity) => html`
                            <${EntityCard}
                                key=${entity.id}
                                entity=${entity}
                                collapsed=${!expandedCards.has(entity.id)}
                                onToggleCollapse=${toggleCardCollapse}
                                onNavigate=${() => {
                                    window.location.hash = "#/entity/" + encodeURIComponent(entity.id) + "/status";
                                }}
                                selected=${selectedIds.has(entity.id)}
                                selectionMode=${true}
                                disabled=${bulkExecuting}
                                onToggleSelect=${handleToggleSelect}
                                onResumePolling=${handleResumePolling}
                            />
                        `
                    )}
                </div>
            </div>
        `}

        ${orderedGroupKeys.map((groupKey) => {
            const isCollapsed = collapsedGroups.has(groupKey);
            const groupEntities = groupedApproved[groupKey];
            const groupLabel = groupKey === "unassigned" ? "Unassigned Members" : `Group: ${groupKey}`;
            const hasSuspended = groupEntities.some((e) => e.polling_suspended);
            return html`
                <div style=${{ marginTop: "16px" }} key=${groupKey}>
                    <h3
                        onClick=${() => toggleGroupCollapse(groupKey)}
                        style=${{
                            fontSize: "1rem",
                            color: "var(--color-text-muted)",
                            marginBottom: isCollapsed ? "0" : "10px",
                            cursor: "pointer",
                            userSelect: "none",
                            display: "flex",
                            alignItems: "center",
                            gap: "6px",
                        }}
                        title=${isCollapsed ? "Click to expand" : "Click to collapse"}
                    >
                        <span style=${{
                            display: "inline-block",
                            transition: "transform 0.15s ease",
                            transform: isCollapsed ? "rotate(-90deg)" : "rotate(0deg)",
                            fontSize: "0.75rem",
                        }}>${"\u25BC"}</span>
                        ${groupLabel}
                        <span style=${{
                            fontSize: "0.75rem",
                            backgroundColor: "var(--bg-tertiary)",
                            padding: "1px 7px",
                            borderRadius: "10px",
                            marginLeft: "4px",
                        }}>${groupEntities.length}</span>
                        ${hasSuspended && html`
                            <button
                                onClick=${(e) => {
                                    e.stopPropagation();
                                    const realGroup = groupKey === "unassigned" ? "" : groupKey;
                                    fetch(
                                        "/api/entities/resume-polling" + (realGroup ? `?group_id=${encodeURIComponent(realGroup)}` : ""),
                                        { method: "POST" }
                                    )
                                        .then((r) => r.json())
                                        .then((data) => {
                                            showToast(
                                                `Resumed polling for ${data.count} entity(s)`,
                                                data.count > 0 ? "success" : "info"
                                            );
                                            loadEntities();
                                        })
                                        .catch((err) => showToast(`Error: ${err.message}`, "error"));
                                }}
                                style=${{
                                    fontSize: "0.65rem",
                                    padding: "1px 8px",
                                    borderRadius: "4px",
                                    border: "1px solid var(--color-accent, #3b82f6)",
                                    background: "transparent",
                                    color: "var(--color-accent, #3b82f6)",
                                    cursor: "pointer",
                                    marginLeft: "4px",
                                    lineHeight: "1.4",
                                }}
                                title="Resume polling for all suspended entities in this group"
                            >
                                Resume All
                            </button>
                        `}
                    </h3>
                    ${!isCollapsed && html`
                        <div style=${{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                            gap: "16px",
                        }}>
                            ${groupEntities.map(
                                (entity) => html`
                                    <${EntityCard}
                                        key=${entity.id}
                                        entity=${entity}
                                        collapsed=${!expandedCards.has(entity.id)}
                                        onToggleCollapse=${toggleCardCollapse}
                                        onNavigate=${() => {
                                            window.location.hash = "#/entity/" + encodeURIComponent(entity.id) + "/status";
                                        }}
                                        selected=${selectedIds.has(entity.id)}
                                        selectionMode=${true}
                                        disabled=${bulkExecuting}
                                        onToggleSelect=${handleToggleSelect}
                                        onResumePolling=${handleResumePolling}
                                    />
                                `
                            )}
                        </div>
                    `}
                </div>
            `;
        })}

        <!-- Discovered (unconfigured) entities section -->
        ${discoveredEntities.length > 0 && html`
            <div style=${{ marginTop: "32px" }}>
                <h3 style=${{
                    fontSize: "1rem",
                    color: "var(--color-text-muted)",
                    marginBottom: "12px",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                }}>
                    <span>${"\uD83D\uDD0E"}</span>
                    Discovered Devices
                    <span style=${{
                        fontSize: "0.75rem",
                        backgroundColor: "var(--bg-tertiary)",
                        padding: "2px 8px",
                        borderRadius: "10px",
                    }}>
                        ${discoveredEntities.length}
                    </span>
                </h3>
                <div style=${{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                    gap: "12px",
                }}>
                    ${discoveredEntities.map(
                        (entity) => html`
                            <${DiscoveredCard}
                                key=${entity.id}
                                entity=${entity}
                                onAddToFleet=${handleAddToFleetClick}
                            />
                        `
                    )}
                </div>
            </div>
        `}

        <!-- Add to Fleet confirmation dialog -->
        ${promoteTarget && html`
            <div class="modal-overlay" onClick=${(e) => {
                if (e.target === e.currentTarget) handlePromoteCancel();
            }}>
                <div class="modal-content">
                    <div class="modal-header">
                        <h3>Add Device to Fleet?</h3>
                    </div>
                    <div class="modal-body">
                        <p>
                            Add <strong>${promoteTarget.name || promoteTarget.id}</strong>
                            (${promoteTarget.ip || "unknown IP"}) to your fleet
                            configuration. This will persist the device in config.env.
                        </p>
                        <div style=${{ marginTop: "12px" }}>
                            <label style=${{ fontWeight: "500", fontSize: "0.85rem" }}>Device type:</label>
                            <div style=${{ display: "flex", gap: "16px", marginTop: "6px" }}>
                                <label style=${{ display: "flex", alignItems: "center", gap: "4px", cursor: "pointer" }}>
                                    <input type="radio" name="promote-type" value="arm"
                                        checked=${promoteType === "arm"}
                                        onChange=${() => {
                                            setPromoteType("arm");
                                            setPromoteSlot("arm-1");
                                        }}
                                    /> Arm
                                </label>
                                <label style=${{ display: "flex", alignItems: "center", gap: "4px", cursor: "pointer" }}>
                                    <input type="radio" name="promote-type" value="vehicle"
                                        checked=${promoteType === "vehicle"}
                                        onChange=${() => {
                                            setPromoteType("vehicle");
                                            setPromoteSlot("vehicle");
                                        }}
                                    /> Vehicle
                                </label>
                            </div>
                        </div>
                        <div style=${{ marginTop: "12px" }}>
                            <label style=${{ fontWeight: "500", fontSize: "0.85rem" }}>Target group:</label>
                            <input
                                type="text"
                                list="promote-group-suggestions"
                                value=${promoteGroup}
                                onInput=${(e) => setPromoteGroup(e.target.value)}
                                style=${{ marginLeft: "8px" }}
                            />
                            <datalist id="promote-group-suggestions">
                                <option value="tabletop-lab"></option>
                                <option value="machine-1"></option>
                            </datalist>
                        </div>
                        <div style=${{ marginTop: "12px" }}>
                            <label style=${{ fontWeight: "500", fontSize: "0.85rem" }}>Target slot:</label>
                            ${promoteType === "vehicle"
                                ? html`
                                    <select
                                        value=${promoteSlot}
                                        onChange=${(e) => setPromoteSlot(e.target.value)}
                                        style=${{ marginLeft: "8px" }}
                                    >
                                        <option value="vehicle">vehicle</option>
                                    </select>
                                `
                                : html`
                                    <input
                                        type="text"
                                        list="promote-slot-suggestions"
                                        value=${promoteSlot}
                                        onInput=${(e) => setPromoteSlot(e.target.value)}
                                        style=${{ marginLeft: "8px" }}
                                    />
                                    <datalist id="promote-slot-suggestions">
                                        <option value="arm-1"></option>
                                        <option value="arm-2"></option>
                                        <option value="arm-3"></option>
                                        <option value="arm-4"></option>
                                        <option value="arm-5"></option>
                                        <option value="arm-6"></option>
                                    </datalist>
                                `}
                        </div>
                        <div class="confirm-dialog-actions">
                            <button class="btn confirm-dialog-cancel" onClick=${handlePromoteCancel}>
                                Cancel
                            </button>
                            <button class="btn confirm-dialog-confirm" onClick=${handlePromoteConfirm}>
                                Add to Fleet
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `}

        <!-- Add Entity Modal -->
        <${AddEntityModal}
            isOpen=${isAddEntityModalOpen}
            onClose=${() => setIsAddEntityModalOpen(false)}
            onEntityAdded=${(newEntity) => {
                // Optionally handle here if websocket is slow,
                // but websocket should handle it anyway.
                // We'll update state just to be instantly responsive.
                setEntities((prev) => {
                    if (prev.find(e => e.id === newEntity.id)) return prev;
                    return [...prev, newEntity];
                });
            }}
            existingEntities=${configuredEntities}
        />

        <!-- Bulk Action Bar -->
        ${selectedIds.size > 0 && html`
            <${BulkActionBar}
                selectedIds=${selectedIds}
                entities=${configuredEntities}
                onSelectAll=${handleSelectAll}
                onDeselectAll=${handleDeselectAll}
                onClearSelection=${handleDeselectAll}
                onSelectionChange=${handleSelectionChange}
                executing=${bulkExecuting}
                onExecutingChange=${setBulkExecuting}
            />
        `}
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("fleet-overview", FleetOverview);

export { FleetOverview };
