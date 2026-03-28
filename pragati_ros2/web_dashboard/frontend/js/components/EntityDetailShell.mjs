/**
 * EntityDetailShell — Preact component for entity detail view.
 *
 * Reads entity ID and active sub-tab from URL hash, fetches entity data,
 * renders breadcrumb navigation, tab bar, stale-data indicator, and the
 * active sub-tab content.
 *
 * URL scheme: #/entity/{id}/status, #/entity/{id}/topics, etc.
 *
 * Tasks implemented:
 * - 5.1: Shell with tab bar + active sub-tab
 * - 5.3: Tab visibility by entity type (arm shows Motor Config placeholder)
 * - 5.4: Stale-data indicator when entity unreachable
 * - 5.5: Breadcrumb: Fleet > {Entity Name} > {Tab Name}
 * - 5.8: "Initializing..." placeholder before first health data
 * - 5.9: Per-subsystem health status via StatusHealthTab
 * - 8.1: Add 5 new ROS2 sub-tabs to ENTITY_TABS registry
 * - 8.2: Lazy-load sub-tab modules via dynamic import() with caching
 * - 8.3: Sub-tab lifecycle management (cleanup on switch/navigate)
 * - 8.4: ROS2-unavailable tab dimming
 * - 8.5: Pass entity context props to all sub-tabs
 *
 * @module components/EntityDetailShell
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useCallback,
    useRef,
    useMemo,
    useContext
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { StatusHealthTab } from "./StatusHealthTab.mjs";
import { registerTab } from "../tabRegistry.js";
import { formatAbsoluteTime } from "./EntityCard.mjs";
import { EditEntityModal } from "./EditEntityModal.mjs";
import { useConfirmDialog, ConfirmationDialog } from "./ConfirmationDialog.mjs";
import { ToastContext } from "../app.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Data refresh interval (ms). */
const POLL_INTERVAL_MS = 10000;

/** Seconds after which an entity is considered "stale" if last_seen is old. */
const STALE_THRESHOLD_S = 30;

/**
 * Tab definitions for the entity detail view.
 * `entityTypes` controls which entity types see this tab (null = all types).
 * Tabs with `placeholder: true` render a placeholder instead of a real component.
 *
 * @type {Array<{id: string, label: string, icon?: string, entityTypes: string[]|null, placeholder?: boolean, ros2Required?: boolean, importPath?: string}>}
 */
const ENTITY_TABS = [
    { id: "status", label: "Status & Health", icon: "\u2764\uFE0F", entityTypes: null },
    {
        id: "nodes",
        label: "Nodes",
        icon: "\uD83D\uDD35",
        entityTypes: null,
        ros2Required: true,
        importPath: "../tabs/entity/NodesSubTab.mjs",
    },
    {
        id: "topics",
        label: "Topics",
        icon: "\uD83D\uDCE1",
        entityTypes: null,
        ros2Required: true,
        importPath: "../tabs/entity/TopicsSubTab.mjs",
    },
    {
        id: "services",
        label: "Services",
        icon: "\uD83D\uDD27",
        entityTypes: null,
        ros2Required: true,
        importPath: "../tabs/entity/ServicesSubTab.mjs",
    },
    {
        id: "parameters",
        label: "Parameters",
        icon: "\uD83D\uDCCB",
        entityTypes: null,
        ros2Required: true,
        importPath: "../tabs/entity/ParametersSubTab.mjs",
    },
    {
        id: "logs",
        label: "Logs",
        icon: "\uD83D\uDCDC",
        entityTypes: null,
        importPath: "../tabs/entity/LogsSubTab.mjs",
    },
    {
        id: "rosbag",
        label: "Rosbag",
        icon: "\uD83C\uDFA5",
        entityTypes: null,
        importPath: "../tabs/entity/RosbagSubTab.mjs",
    },
    {
        id: "images",
        label: "Images",
        icon: "\uD83D\uDDBC\uFE0F",
        entityTypes: ["arm"],
        importPath: "../tabs/entity/ImagesSubTab.mjs",
    },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Parse entity detail route from hash.
 * Expects: /entity/{id}/{tab}
 *
 * @param {string} hash - The location.hash value (with or without #)
 * @returns {{entityId: string|null, subTab: string|null}}
 */
function parseEntityHash(hash) {
    const h = (hash || "").replace(/^#?\/?/, "");
    // Match: entity/{id}/{tab} or entity/{id}
    const match = h.match(/^entity\/([^/]+)(?:\/([^/]+))?$/);
    if (!match) return { entityId: null, subTab: null };
    return {
        entityId: decodeURIComponent(match[1]),
        subTab: match[2] ? decodeURIComponent(match[2]) : "status",
    };
}

/**
 * Format relative time for stale indicator.
 * @param {string|null} isoString
 * @returns {string}
 */
function formatTimeAgo(isoString) {
    if (!isoString) return "unknown";
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "unknown";

    const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (diffSec < 5) return "just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return d.toLocaleDateString();
}

/**
 * Check if entity data is stale.
 * @param {object|null} entityData
 * @returns {boolean}
 */
function isEntityStale(entityData) {
    if (!entityData) return false;
    // Explicitly offline
    if ((entityData.status || "").toLowerCase() === "offline") return true;
    // Check last_seen timestamp
    if (entityData.last_seen) {
        const d = new Date(entityData.last_seen);
        if (!isNaN(d.getTime())) {
            const diffSec = (Date.now() - d.getTime()) / 1000;
            return diffSec > STALE_THRESHOLD_S;
        }
    }
    return false;
}

/**
 * Get visible tabs for a given entity type (task 5.3).
 * @param {string|null} entityType
 * @returns {Array}
 */
function getVisibleTabs(entityType) {
    return ENTITY_TABS.filter((tab) => {
        if (tab.entityTypes === null) return true;
        return tab.entityTypes.includes(entityType || "");
    });
}

// ---------------------------------------------------------------------------
// Sub-tab lazy loading (task 8.2)
// ---------------------------------------------------------------------------

/** Cache for dynamically imported sub-tab modules, keyed by tab id. */
const _moduleCache = new Map();

/**
 * Lazily import a sub-tab module and cache it.
 * @param {{id: string, importPath: string}} tab
 * @returns {Promise<Function>} The default-exported component
 */
async function loadTabModule(tab) {
    if (_moduleCache.has(tab.id)) return _moduleCache.get(tab.id);
    const mod = await import(tab.importPath);
    const component = mod.default || mod;
    _moduleCache.set(tab.id, component);
    return component;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Breadcrumb navigation (task 5.5).
 * Fleet > {Entity Name} > {Tab Name}
 */
function Breadcrumb({ entityName, tabLabel }) {
    const navigateFleet = useCallback(() => {
        window.location.hash = "#fleet-overview";
    }, []);

    return html`
        <nav
            style=${{
                display: "flex",
                alignItems: "center",
                gap: "var(--spacing-xs)",
                marginBottom: "var(--spacing-md)",
                fontSize: "0.9rem",
                color: "var(--color-text-muted)",
            }}
            aria-label="Breadcrumb"
        >
            <a
                onClick=${navigateFleet}
                style=${{
                    cursor: "pointer",
                    color: "var(--color-accent)",
                    textDecoration: "none",
                }}
            >
                Fleet
            </a>
            <span>\u203A</span>
            <span style=${{ color: "var(--color-text-secondary)" }}>
                ${entityName || "Entity"}
            </span>
            <span>\u203A</span>
            <span style=${{ color: "var(--color-text-primary)", fontWeight: 500 }}>
                ${tabLabel || "Status"}
            </span>
        </nav>
    `;
}

/**
 * Tab bar for entity detail sub-tabs (task 5.1, 8.4).
 * Dims ros2Required tabs when ROS2 is unavailable.
 */
function EntityTabBar({ tabs, activeSubTab, entityId, ros2Available }) {
    const navigate = useCallback(
        (tabId) => {
            window.location.hash = `#/entity/${encodeURIComponent(entityId)}/${tabId}`;
        },
        [entityId]
    );

    const [ros2Message, setRos2Message] = useState(null);

    const handleTabClick = useCallback(
        (tab) => {
            if (tab.ros2Required && !ros2Available) {
                setRos2Message(tab.id);
                setTimeout(() => setRos2Message(null), 3000);
                return;
            }
            navigate(tab.id);
        },
        [ros2Available, navigate]
    );

    return html`
        <div style=${{ position: "relative" }}>
            <div
                style=${{
                    display: "flex",
                    gap: "2px",
                    borderBottom: "2px solid var(--color-border)",
                    marginBottom: "var(--spacing-lg)",
                }}
            >
                ${tabs.map((tab) => {
                    const isDimmed = tab.ros2Required && !ros2Available;
                    const isActive = activeSubTab === tab.id;
                    return html`
                        <button
                            key=${tab.id}
                            onClick=${() => handleTabClick(tab)}
                            title=${isDimmed
                                ? "ROS2 is not available on this entity"
                                : tab.label}
                            style=${{
                                padding: "var(--spacing-sm) var(--spacing-lg)",
                                border: "none",
                                borderBottom: isActive
                                    ? "2px solid var(--color-accent)"
                                    : "2px solid transparent",
                                background: isActive
                                    ? "var(--color-bg-tertiary)"
                                    : "transparent",
                                color: isActive
                                    ? "var(--color-accent)"
                                    : "var(--color-text-secondary)",
                                cursor: isDimmed ? "not-allowed" : "pointer",
                                fontSize: "0.9rem",
                                fontWeight: isActive ? 600 : 400,
                                opacity: isDimmed ? 0.4 : 1,
                                transition: "all 0.15s ease",
                                marginBottom: "-2px",
                            }}
                        >
                            ${tab.icon ? html`<span style=${{ marginRight: "4px" }}>${tab.icon}</span>` : null}
                            ${tab.label}
                        </button>
                    `;
                })}
            </div>
            ${ros2Message != null &&
            html`
                <div
                    style=${{
                        position: "absolute",
                        top: "100%",
                        left: "0",
                        marginTop: "var(--spacing-xs)",
                        padding: "var(--spacing-xs) var(--spacing-sm)",
                        background: "var(--color-bg-tertiary)",
                        border: "1px solid var(--color-border)",
                        borderRadius: "var(--radius-sm)",
                        fontSize: "0.8rem",
                        color: "var(--color-text-muted)",
                        zIndex: 10,
                    }}
                >
                    ROS2 is not available on this entity
                </div>
            `}
        </div>
    `;
}

/**
 * Stale-data overlay indicator (task 5.4).
 */
function StaleIndicator({ entityData }) {
    if (!isEntityStale(entityData)) return null;

    const lastSeenText = formatTimeAgo(entityData.last_seen);

    return html`
        <div
            style=${{
                background: "color-mix(in srgb, var(--color-error) 8%, transparent)",
                border: "1px solid var(--color-error)",
                borderRadius: "var(--radius-md)",
                padding: "var(--spacing-sm) var(--spacing-md)",
                marginBottom: "var(--spacing-md)",
                display: "flex",
                alignItems: "center",
                gap: "var(--spacing-sm)",
                fontSize: "0.85rem",
                color: "var(--color-error)",
            }}
        >
            <span style=${{ fontSize: "1.2em" }}>\u26A0\uFE0F</span>
            <span>
                <strong>Entity unreachable</strong> \u2014
                Last updated: ${lastSeenText}
            </span>
        </div>
    `;
}

/**
 * Placeholder for future/unimplemented tabs (task 5.3).
 */
function TabPlaceholder({ label }) {
    return html`
        <div
            style=${{
                textAlign: "center",
                padding: "var(--spacing-xl) 0",
                color: "var(--color-text-muted)",
            }}
        >
            <div style=${{ fontSize: "2em", marginBottom: "var(--spacing-sm)" }}>\uD83D\uDEA7</div>
            <div style=${{ fontSize: "1.1em" }}>${label}</div>
            <div style=${{ fontSize: "0.85em", marginTop: "var(--spacing-xs)" }}>
                Coming soon
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * EntityDetailShell — main shell component.
 * Reads entity ID from URL hash, fetches entity data, renders tab bar
 * and active sub-tab content.
 *
 * Tasks: 5.x (original), 8.1-8.5 (ROS2 sub-tabs, lazy loading, lifecycle).
 */
function EntityDetailShell() {
    // Parse route from hash
    const [route, setRoute] = useState(() => parseEntityHash(location.hash));
    const [entityData, setEntityData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const mountedRef = useRef(true);

    // Task 8.2: Lazy-loaded tab component state
    const [LazyTabComponent, setLazyTabComponent] = useState(null);
    const [tabLoading, setTabLoading] = useState(false);
    const [tabError, setTabError] = useState(null);

    // Task 8.3: Track cleanup function from active sub-tab
    const cleanupRef = useRef(null);

    // Reboot / Shutdown pending state for entity header
    const [hostActionPending, setHostActionPending] = useState(null);

    // Edit/Remove state
    const { showToast } = useContext(ToastContext);
    const [isEditModalOpen, setIsEditModalOpen] = useState(false);
    const { dialog: deleteDialog, doubleConfirm: confirmDelete } = useConfirmDialog();

    const handleDelete = async () => {
        const confirmed = await confirmDelete({
            title: "Delete Entity",
            message: `Are you sure you want to remove ${entityId} from the fleet? This will remove its configuration.`,
            confirmText: "Delete",
            dangerous: true,
            confirmWord: entityId,
            confirmWordPrompt: `Type the entity ID "${entityId}" to confirm:`
        });

        if (confirmed) {
            const resp = await safeFetch(`/api/entities/${encodeURIComponent(entityId)}`, {
                method: 'DELETE'
            });
            if (resp && !resp.error) {
                showToast(`Entity ${entityId} deleted`, 'success');
                window.location.hash = "#fleet-overview";
            }
        }
    };

    // Listen for hash changes to update route
    useEffect(() => {
        const onHashChange = () => {
            const parsed = parseEntityHash(location.hash);
            setRoute(parsed);
        };
        window.addEventListener("hashchange", onHashChange);
        return () => window.removeEventListener("hashchange", onHashChange);
    }, []);

    const { entityId, subTab } = route;

    // ---- Reboot / Shutdown handlers ---------------------------------------

    const handleReboot = useCallback(async () => {
        if (!entityId) return;
        const ok = window.confirm(
            `\u26A0\uFE0F REBOOT ${entityId}?\n\nThis will restart the device. It will be offline for ~60 seconds.`
        );
        if (!ok) return;
        setHostActionPending("reboot");
        try {
            const resp = await fetch(
                `/api/entities/${encodeURIComponent(entityId)}/system/reboot`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ token: "REBOOT" }),
                }
            );
            if (!mountedRef.current) return;
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                alert(err.detail || "Reboot failed");
            }
        } catch (e) {
            if (mountedRef.current) alert(`Reboot error: ${e.message}`);
        }
        if (mountedRef.current) setHostActionPending(null);
    }, [entityId]);

    const handleShutdown = useCallback(async () => {
        if (!entityId) return;
        const ok = window.confirm(
            `\uD83D\uDED1 SHUTDOWN ${entityId}?\n\nThis will power off the device. You must physically power it back on.`
        );
        if (!ok) return;
        setHostActionPending("shutdown");
        try {
            const resp = await fetch(
                `/api/entities/${encodeURIComponent(entityId)}/system/shutdown`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ token: "SHUTDOWN" }),
                }
            );
            if (!mountedRef.current) return;
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                alert(err.detail || "Shutdown failed");
            }
        } catch (e) {
            if (mountedRef.current) alert(`Shutdown error: ${e.message}`);
        }
        if (mountedRef.current) setHostActionPending(null);
    }, [entityId]);

    // ---- data fetching ----------------------------------------------------

    const fetchEntityData = useCallback(async () => {
        if (!entityId) return;

        const result = await safeFetch(
            `/api/entities/${encodeURIComponent(entityId)}`
        );

        if (!mountedRef.current) return;

        if (!result) {
            setError("Failed to fetch entity data");
            setLoading(false);
            return;
        }

        if (result.detail || result.error) {
            setError(result.detail || result.error);
            setLoading(false);
            return;
        }

        setEntityData(result);
        setError(null);
        setLoading(false);
    }, [entityId]);

    // Initial fetch + polling
    useEffect(() => {
        mountedRef.current = true;
        // Only show loading spinner on first load (no entityData yet).
        // On subsequent entityId changes, keep stale data visible to avoid
        // DOM teardown → "Initializing..." flash → rebuild layout jump.
        if (!entityData) {
            setLoading(true);
        }
        setError(null);
        fetchEntityData();

        return () => {
            mountedRef.current = false;
        };
    }, [fetchEntityData]);

    useEffect(() => {
        if (!entityId) return;
        const id = setInterval(fetchEntityData, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [fetchEntityData, entityId]);

    // ---- derived state ----------------------------------------------------

    const entityType = entityData ? entityData.entity_type : null;
    const entityName = entityData ? entityData.name || entityData.id : entityId;
    const visibleTabs = useMemo(() => getVisibleTabs(entityType), [entityType]);
    const activeTab = visibleTabs.find((t) => t.id === subTab) || visibleTabs[0];
    const activeTabLabel = activeTab ? activeTab.label : "Status";

    // Task 7.3: Redirect to status if URL tab is hidden for this entity type
    useEffect(() => {
        if (!entityType || !subTab || !entityId) return;
        const isVisible = visibleTabs.some((t) => t.id === subTab);
        if (!isVisible) {
            window.location.hash = `#/entity/${encodeURIComponent(entityId)}/status`;
        }
    }, [entityType, subTab, entityId, visibleTabs]);

    // Task 8.5: Derive ros2Available from entity data
    const ros2Available = entityData ? entityData.ros2_available !== false : false;

    // Task 8.5: Entity context props passed to all sub-tabs
    const entityContext = useMemo(
        () => ({
            entityId: entityId,
            entitySource: entityData ? entityData.source || "local" : "local",
            entityIp: entityData ? entityData.ip || null : null,
            ros2Available: ros2Available,
        }),
        [entityId, entityData, ros2Available]
    );

    // ---- Task 8.3: Lifecycle — cleanup on tab switch or entity change -----

    useEffect(() => {
        // When activeTab or entityId changes, cleanup previous sub-tab
        return () => {
            if (cleanupRef.current) {
                cleanupRef.current();
                cleanupRef.current = null;
            }
        };
    }, [activeTab, entityId]);

    // Cleanup on component unmount
    useEffect(() => {
        return () => {
            if (cleanupRef.current) {
                cleanupRef.current();
                cleanupRef.current = null;
            }
        };
    }, []);

    /**
     * Register a cleanup function from a sub-tab component.
     * Called by sub-tabs to register their teardown logic.
     */
    const registerCleanup = useCallback((fn) => {
        cleanupRef.current = fn;
    }, []);

    // ---- Task 8.2: Lazy load tab module when active tab changes -----------

    useEffect(() => {
        if (!activeTab) return;
        // Status tab is rendered inline — no lazy loading
        if (activeTab.id === "status") {
            setLazyTabComponent(null);
            setTabLoading(false);
            setTabError(null);
            return;
        }
        // Placeholder tabs don't have importPath
        if (activeTab.placeholder || !activeTab.importPath) {
            setLazyTabComponent(null);
            setTabLoading(false);
            setTabError(null);
            return;
        }
        // Lazy-load the module
        setTabLoading(true);
        setTabError(null);
        setLazyTabComponent(null);

        loadTabModule(activeTab)
            .then((component) => {
                if (!mountedRef.current) return;
                // Wrap in a function to prevent Preact from calling it as a state initializer
                setLazyTabComponent(() => component);
                setTabLoading(false);
            })
            .catch((err) => {
                if (!mountedRef.current) return;
                console.error(
                    `[EntityDetailShell] Failed to load tab "${activeTab.id}":`,
                    err
                );
                setTabError(
                    `Failed to load ${activeTab.label} tab. The module may not exist yet.`
                );
                setTabLoading(false);
            });
    }, [activeTab]);

    // ---- render -----------------------------------------------------------

    // No entity ID in URL
    if (!entityId) {
        return html`
            <div style=${{ padding: "var(--spacing-xl)", textAlign: "center" }}>
                <p style=${{ color: "var(--color-text-muted)" }}>
                    No entity selected. Return to
                    <a
                        onClick=${() => { window.location.hash = "#fleet-overview"; }}
                        style=${{ cursor: "pointer", color: "var(--color-accent)" }}
                    > Fleet Overview</a>.
                </p>
            </div>
        `;
    }

    // Error state
    if (error && !entityData) {
        return html`
            <${Breadcrumb} entityName=${entityId} tabLabel=${activeTabLabel} />
            <div style=${{
                padding: "var(--spacing-xl)",
                textAlign: "center",
                color: "var(--color-error)",
            }}>
                <div style=${{ fontSize: "2em", marginBottom: "var(--spacing-sm)" }}>\u274C</div>
                <div style=${{ fontSize: "1.1em" }}>${error}</div>
                <div style=${{ marginTop: "var(--spacing-md)" }}>
                    <a
                        onClick=${() => { window.location.hash = "#fleet-overview"; }}
                        style=${{ cursor: "pointer", color: "var(--color-accent)" }}
                    >
                        Back to Fleet
                    </a>
                </div>
            </div>
        `;
    }

    // Render sub-tab content
    let tabContent = null;
    if (activeTab) {
        if (activeTab.placeholder) {
            tabContent = html`<${TabPlaceholder} label=${activeTab.label} />`;
        } else if (activeTab.id === "status") {
            // Status tab rendered inline (no lazy loading)
            tabContent = html`
                <${StatusHealthTab}
                    entityId=${entityId}
                    entityData=${entityData}
                    loading=${loading}
                />
            `;
        } else if (tabLoading) {
            // Task 8.2: Show loading spinner while module is loading
            tabContent = html`
                <div
                    style=${{
                        textAlign: "center",
                        padding: "var(--spacing-xl) 0",
                        color: "var(--color-text-muted)",
                    }}
                >
                    <div
                        style=${{
                            display: "inline-block",
                            width: "24px",
                            height: "24px",
                            border: "3px solid var(--color-border)",
                            borderTopColor: "var(--color-accent)",
                            borderRadius: "50%",
                            animation: "spin 0.8s linear infinite",
                        }}
                    />
                    <div style=${{ marginTop: "var(--spacing-sm)", fontSize: "0.9rem" }}>
                        Loading ${activeTab.label}...
                    </div>
                </div>
            `;
        } else if (tabError) {
            // Task 8.2: Show error if module failed to load
            tabContent = html`
                <div
                    style=${{
                        textAlign: "center",
                        padding: "var(--spacing-xl) 0",
                        color: "var(--color-error)",
                    }}
                >
                    <div style=${{ fontSize: "2em", marginBottom: "var(--spacing-sm)" }}>\u26A0\uFE0F</div>
                    <div style=${{ fontSize: "1.1em" }}>${tabError}</div>
                </div>
            `;
        } else if (LazyTabComponent) {
            // Task 8.2 + 8.5: Render lazy-loaded component with entity context
            tabContent = html`
                <${LazyTabComponent}
                    ...${entityContext}
                    registerCleanup=${registerCleanup}
                />
            `;
        }
    }

    return html`
        <!-- Breadcrumb (task 5.5) -->
        <${Breadcrumb}
            entityName=${entityName}
            tabLabel=${activeTabLabel}
        />

        <!-- Entity header -->
        <div style=${{
            display: "flex",
            alignItems: "center",
            gap: "var(--spacing-md)",
            marginBottom: "var(--spacing-md)",
        }}>
            <h2 style=${{ margin: 0, fontSize: "1.5rem" }}>
                ${entityName}
            </h2>
            ${entityData && html`
                <span
                    style=${{
                        padding: "2px 10px",
                        borderRadius: "var(--radius-sm)",
                        fontSize: "0.75rem",
                        fontWeight: 500,
                        textTransform: "uppercase",
                        background:
                            (entityData.status || "").toLowerCase() === "online"
                                ? "color-mix(in srgb, var(--color-success) 15%, transparent)"
                                : "color-mix(in srgb, var(--color-error) 15%, transparent)",
                        color:
                            (entityData.status || "").toLowerCase() === "online"
                                ? "var(--color-success)"
                                : "var(--color-error)",
                    }}
                >
                    ${entityData.status || "unknown"}
                </span>
                <span style=${{
                    fontSize: "0.8rem",
                    color: "var(--color-text-muted)",
                    padding: "2px 8px",
                    background: "var(--color-bg-tertiary)",
                    borderRadius: "var(--radius-sm)",
                    textTransform: "capitalize",
                }}>
                    ${entityType || "unknown"}
                </span>
                ${entityData.last_seen && html`
                    <span style=${{
                        fontSize: "0.8rem",
                        color: "var(--color-text-muted)",
                    }}>
                        ${formatTimeAgo(entityData.last_seen)}${" \u00B7 "}${formatAbsoluteTime(entityData.last_seen)}
                    </span>
                `}
                <!-- Actions -->
                <div style=${{
                    display: "flex",
                    gap: "6px",
                    marginLeft: "auto",
                }}>
                    <button
                        title="Edit entity"
                        onClick=${() => setIsEditModalOpen(true)}
                        style=${{
                            background: "var(--color-bg-tertiary)",
                            border: "1px solid var(--color-border)",
                            borderRadius: "var(--radius-sm)",
                            padding: "4px 10px",
                            fontSize: "0.75rem",
                            cursor: "pointer",
                            color: "var(--color-text-primary)",
                        }}
                    >
                        \u270E Edit
                    </button>
                    <button
                        title="Delete entity"
                        onClick=${handleDelete}
                        style=${{
                            background: "var(--color-bg-tertiary)",
                            border: "1px solid var(--color-error)",
                            borderRadius: "var(--radius-sm)",
                            padding: "4px 10px",
                            fontSize: "0.75rem",
                            cursor: "pointer",
                            color: "var(--color-error)",
                        }}
                    >
                        \uD83D\uDDD1 Delete
                    </button>
                    <div style=${{ borderLeft: "1px solid var(--color-border)", margin: "0 4px" }}></div>

                    <button
                        class="system-reboot-btn"
                        title="Reboot device"
                        disabled=${hostActionPending != null}
                        onClick=${handleReboot}
                        style=${{
                            background: "var(--color-bg-tertiary)",
                            border: "1px solid var(--color-border)",
                            borderRadius: "var(--radius-sm)",
                            padding: "4px 10px",
                            fontSize: "0.75rem",
                            cursor: hostActionPending ? "not-allowed" : "pointer",
                            color: "var(--color-warning)",
                            opacity: hostActionPending === "reboot" ? "0.6" : "1",
                        }}
                    >
                        ${hostActionPending === "reboot" ? "\u23F3" : "\uD83D\uDD04"} Restart
                    </button>
                    <button
                        class="system-shutdown-btn"
                        title="Shutdown device"
                        disabled=${hostActionPending != null}
                        onClick=${handleShutdown}
                        style=${{
                            background: "var(--color-bg-tertiary)",
                            border: "1px solid var(--color-error)",
                            borderRadius: "var(--radius-sm)",
                            padding: "4px 10px",
                            fontSize: "0.75rem",
                            cursor: hostActionPending ? "not-allowed" : "pointer",
                            color: "var(--color-error)",
                            opacity: hostActionPending === "shutdown" ? "0.6" : "1",
                        }}
                    >
                        ${hostActionPending === "shutdown" ? "\u23F3" : "\u23FB"} Shutdown
                    </button>
                </div>
            `}
        </div>

        <!-- Stale-data indicator (task 5.4) -->
        <${StaleIndicator} entityData=${entityData} />

        <!-- Tab bar (task 5.1, 5.3, 8.4) -->
        <${EntityTabBar}
            tabs=${visibleTabs}
            activeSubTab=${activeTab ? activeTab.id : "status"}
            entityId=${entityId}
            ros2Available=${ros2Available}
        />

        <!-- Active tab content -->
        ${tabContent}

        <!-- Modals and Dialogs -->
        <${EditEntityModal}
            isOpen=${isEditModalOpen}
            onClose=${() => setIsEditModalOpen(false)}
            entity=${entityData}
            onEntityUpdated=${fetchEntityData}
        />
        ${deleteDialog}
    `;
}

// ---------------------------------------------------------------------------
// Register as a special tab in the registry (task 5.6)
// ---------------------------------------------------------------------------

registerTab("entity-detail", EntityDetailShell);

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export {
    EntityDetailShell,
    parseEntityHash,
    isEntityStale,
    getVisibleTabs,
    ENTITY_TABS,
    STALE_THRESHOLD_S,
};
