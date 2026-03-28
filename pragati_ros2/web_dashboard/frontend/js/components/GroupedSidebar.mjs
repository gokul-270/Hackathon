/**
 * GroupedSidebar — Preact component for entity-centric sidebar navigation.
 *
 * Renders:
 * - A "Fleet Overview" link at the top (navigates to #fleet-overview)
 * - Entity list fetched from /api/entities, each as a flat link (no expand/collapse)
 * - Static global nav items: Operations, Monitoring, Motor Config, Settings
 *
 * Entity links show a status dot (green/yellow/red for online/degraded/offline)
 * and navigate directly to the entity's Status & Health tab.
 * Sub-tab navigation is handled by the content area tab bar (EntityDetailShell).
 *
 * @module components/GroupedSidebar
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useRef } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";

// ---------------------------------------------------------------------------
// Static (global) tab groups — kept below the entity list
// ---------------------------------------------------------------------------

/**
 * Global nav items — rendered as flat sidebar links (no group headers).
 * Operations and Monitoring are hub pages; Motor Config is standalone bench tool;
 * Settings is direct.
 */
const GLOBAL_NAV_ITEMS = [
    { id: "operations", label: "Operations", icon: "\u26A1" },    // ⚡
    { id: "monitoring", label: "Monitoring", icon: "\uD83D\uDCCA" }, // 📊
    { id: "motor-config", label: "Motor Config", icon: "\uD83C\uDF9B" }, // 🎛
    { id: "settings", label: "Settings", icon: "\u2699\uFE0F" },    // ⚙️
];

// ---------------------------------------------------------------------------
// localStorage key
// ---------------------------------------------------------------------------

const SIDEBAR_COLLAPSED_KEY = "sidebar-collapsed";

/**
 * Get icon and number suffix for an entity based on its id/role.
 * @param {object} entity
 * @returns {{ icon: string, number: string }}
 */
function getEntityIcon(entity) {
    const id = (entity.id || "").toLowerCase();
    const role = (entity.role || entity.entity_type || "").toLowerCase();
    if (role === "arm" || id.startsWith("arm")) {
        const match = id.match(/(\d+)/);
        return { icon: "\uD83E\uDDBE", number: match ? match[1] : "" }; // 🦾
    }
    if (role === "vehicle" || id.startsWith("vehicle")) {
        return { icon: "\uD83D\uDE9C", number: "" }; // 🚜
    }
    if (role === "dev" || id === "local") {
        return { icon: "\uD83D\uDCBB", number: "" }; // 💻
    }
    return { icon: "\uD83E\uDD16", number: "" }; // 🤖
}

/**
 * Parse the current URL hash to extract entity route info.
 * @param {string} hash - Hash without '#' prefix
 * @returns {{ entityId: string|null, entityTab: string|null }}
 */
function parseEntityRoute(hash) {
    const match = hash.match(/^\/?entity\/([^/]+)(?:\/([^/]+))?/);
    if (match) {
        return { entityId: match[1], entityTab: match[2] || "status" };
    }
    return { entityId: null, entityTab: null };
}

/**
 * Check if a tab id matches a global nav item.
 * @param {string} tabId
 * @returns {boolean}
 */
function isGlobalNavTab(tabId) {
    return GLOBAL_NAV_ITEMS.some((item) => item.id === tabId);
}

/**
 * Get status dot color for an entity status.
 * @param {string} status
 * @returns {string} CSS color value
 */
function statusDotColor(status) {
    switch (status) {
        case "online":
            return "var(--color-success)";
        case "degraded":
            return "var(--color-warning)";
        case "offline":
        default:
            return "var(--color-error)";
    }
}

/**
 * Compute time drift between server and entity.
 * Returns { driftSec, isWarning } where isWarning is true if drift > 5s.
 * @param {object} entity
 * @returns {{ driftSec: number|null, isWarning: boolean }}
 */
function computeTimeDrift(entity) {
    if (!entity.last_seen) return { driftSec: null, isWarning: false };
    const lastSeen = new Date(entity.last_seen);
    if (isNaN(lastSeen.getTime())) return { driftSec: null, isWarning: false };
    const driftSec = Math.abs(Math.floor((Date.now() - lastSeen.getTime()) / 1000));
    return { driftSec, isWarning: driftSec > 5 };
}

/**
 * Format drift seconds for display.
 * @param {number|null} driftSec
 * @returns {string}
 */
function formatDrift(driftSec) {
    if (driftSec === null) return "";
    if (driftSec < 60) return `${driftSec}s`;
    if (driftSec < 3600) return `${Math.floor(driftSec / 60)}m`;
    return `${Math.floor(driftSec / 3600)}h`;
}

// ---------------------------------------------------------------------------
// Entity polling interval
// ---------------------------------------------------------------------------

const ENTITY_POLL_INTERVAL = 10000;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * GroupedSidebar component.
 *
 * @param {object} props
 * @param {string} props.activeTab - Currently active tab id (or "entity-detail")
 */
function GroupedSidebar({ activeTab }) {
    const [entities, setEntities] = useState([]);
    const [collapsed, setCollapsed] = useState(() => {
        try {
            return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
        } catch { return false; }
    });

    // Track which entity groups are collapsed in the sidebar
    const SIDEBAR_GROUPS_KEY = "sidebar-groups-collapsed";
    const [collapsedEntityGroups, setCollapsedEntityGroups] = useState(() => {
        try {
            const stored = localStorage.getItem(SIDEBAR_GROUPS_KEY);
            return stored ? new Set(JSON.parse(stored)) : new Set();
        } catch { return new Set(); }
    });

    const toggleEntityGroup = useCallback((groupKey) => {
        setCollapsedEntityGroups((prev) => {
            const next = new Set(prev);
            if (next.has(groupKey)) {
                next.delete(groupKey);
            } else {
                next.add(groupKey);
            }
            try { localStorage.setItem(SIDEBAR_GROUPS_KEY, JSON.stringify([...next])); } catch {}
            return next;
        });
    }, []);

    const mountedRef = useRef(true);

    // Parse the current hash for entity-route highlighting.
    // We track this via state + hashchange listener so the sidebar
    // re-renders when the user navigates between different entities
    // (activeTab stays "entity-detail" for all entity routes).
    const [activeEntityId, setActiveEntityId] = useState(() => {
        return parseEntityRoute(location.hash.replace("#", "")).entityId;
    });

    useEffect(() => {
        const syncEntityId = () => {
            const { entityId } = parseEntityRoute(location.hash.replace("#", ""));
            setActiveEntityId(entityId);
        };
        window.addEventListener("hashchange", syncEntityId);
        // Also sync on mount / activeTab change in case we missed an update
        syncEntityId();
        return () => window.removeEventListener("hashchange", syncEntityId);
    }, [activeTab]);

    // -----------------------------------------------------------------------
    // Fetch entities on mount + poll every 10s
    // -----------------------------------------------------------------------
    const loadEntities = useCallback(async () => {
        const data = await safeFetch("/api/entities");
        if (!mountedRef.current) return;
        if (data === null) return;

        const entityList = Array.isArray(data)
            ? data
            : (data.entities || []);
        setEntities(entityList);
    }, []);

    useEffect(() => {
        mountedRef.current = true;
        loadEntities();
        const interval = setInterval(loadEntities, ENTITY_POLL_INTERVAL);
        return () => {
            mountedRef.current = false;
            clearInterval(interval);
        };
    }, [loadEntities]);

    // -----------------------------------------------------------------------
    // Propagate collapsed state to parent <aside> via CSS class
    // -----------------------------------------------------------------------
    useEffect(() => {
        const aside = document.querySelector("aside.sidebar");
        if (!aside) return;
        if (collapsed) {
            aside.classList.add("sidebar-collapsed");
        } else {
            aside.classList.remove("sidebar-collapsed");
        }
    }, [collapsed]);

    // -----------------------------------------------------------------------
    // Keyboard shortcut: Ctrl+B toggles sidebar
    // -----------------------------------------------------------------------
    useEffect(() => {
        const handler = (e) => {
            if (e.ctrlKey && e.key === "b") {
                e.preventDefault();
                toggleSidebar();
            }
        };
        window.addEventListener("keydown", handler);
        return () => window.removeEventListener("keydown", handler);
    }, []);

    const toggleSidebar = useCallback(() => {
        setCollapsed((prev) => {
            const next = !prev;
            try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next)); } catch {}
            return next;
        });
    }, []);

    const navigate = useCallback((hash) => {
        window.location.hash = "#" + hash;
    }, []);

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------
    return html`
        <nav class="sidebar-nav${collapsed ? " sidebar-nav-collapsed" : ""}">
            <!-- Collapse toggle bar -->
            <div class="sidebar-toggle-bar" onClick=${toggleSidebar}
                 title=${collapsed ? "Expand sidebar (Ctrl+B)" : "Collapse sidebar (Ctrl+B)"}>
                <span class="sidebar-toggle-icon${collapsed ? " collapsed" : ""}">
                    <span class="toggle-bar"></span>
                    <span class="toggle-bar"></span>
                    <span class="toggle-bar"></span>
                </span>
                ${!collapsed && html`<span class="sidebar-toggle-label">Navigation</span>`}
            </div>

            <!-- Fleet Overview -->
            <a
                class="sidebar-overview${activeTab === "fleet-overview" ? " active" : ""}"
                onClick=${() => navigate("fleet-overview")}
                title="Fleet Overview"
            >
                <span class="nav-icon">${"\uD83C\uDF10"}</span>
                ${!collapsed && html`<span class="nav-label-text">Fleet Overview</span>`}
            </a>

            <!-- Entities grouped by group_id -->
            ${(() => {
                if (entities.length === 0) return null;

                // Separate local/control-plane from remote entities
                const localEntities = entities.filter(
                    (e) => e.source === "local" || e.id === "local"
                );
                const remoteEntities = entities.filter(
                    (e) => e.source !== "local" && e.id !== "local"
                        && e.source !== "discovered" && e.source !== "mdns_discovered"
                );

                // Group remote entities by group_id
                const grouped = remoteEntities.reduce((acc, entity) => {
                    const key = entity.group_id || "unassigned";
                    if (!acc[key]) acc[key] = [];
                    acc[key].push(entity);
                    return acc;
                }, {});

                const preferredOrder = ["tabletop-lab", "machine-1"];
                const groupKeys = Object.keys(grouped).sort((a, b) => {
                    if (a === "unassigned") return 1;
                    if (b === "unassigned") return -1;
                    const ia = preferredOrder.indexOf(a);
                    const ib = preferredOrder.indexOf(b);
                    if (ia !== -1 || ib !== -1) {
                        if (ia === -1) return 1;
                        if (ib === -1) return -1;
                        return ia - ib;
                    }
                    return a.localeCompare(b);
                });

                // Helper to render a single entity link
                const renderEntityLink = (entity) => {
                    const isActiveEntity = activeEntityId === entity.id;
                    const isLocal = entity.source === "local" || entity.id === "local";
                    const { driftSec, isWarning } = isLocal
                        ? { driftSec: null, isWarning: false }
                        : computeTimeDrift(entity);
                    const { icon: entityIcon, number: entityNum } = getEntityIcon(entity);

                    if (collapsed) {
                        return html`
                            <a
                                key=${entity.id}
                                class="sidebar-entity-icon${isActiveEntity ? " active" : ""}"
                                onClick=${() => navigate("/entity/" + entity.id + "/status")}
                                title=${entity.name || entity.id}
                            >
                                <span class="entity-icon-badge">
                                    <span>${entityIcon}</span>
                                    ${entityNum && html`<sub class="entity-num">${entityNum}</sub>`}
                                </span>
                                <span class="entity-status-dot" style=${{
                                    backgroundColor: statusDotColor(entity.status),
                                }}></span>
                            </a>
                        `;
                    }

                    return html`
                        <a
                            key=${entity.id}
                            class="sidebar-entity-link${isActiveEntity ? " active" : ""}"
                            onClick=${() => navigate("/entity/" + entity.id + "/status")}
                            title=${entity.name || entity.id}
                        >
                            <span class="entity-header-left">
                                <span class="entity-icon-inline">${entityIcon}</span>
                                ${entityNum && html`<sub class="entity-num-inline">${entityNum}</sub>`}
                                <span class="entity-status-dot-inline" style=${{
                                    backgroundColor: statusDotColor(entity.status),
                                }}></span>
                                <span class="entity-name-text">
                                    ${entity.name || entity.id}
                                </span>
                                ${driftSec !== null && html`
                                    <span
                                        class="entity-drift-badge${isWarning ? " drift-warning" : ""}"
                                        title=${`Time drift: ${driftSec}s`}
                                    >
                                        ${formatDrift(driftSec)}
                                    </span>
                                `}
                            </span>
                        </a>
                    `;
                };

                // Helper to render a group section
                const renderGroup = (groupKey, groupEntities) => {
                    const isGroupCollapsed = collapsedEntityGroups.has(groupKey);
                    const label = groupKey === "unassigned"
                        ? "Unassigned"
                        : groupKey === "__control_plane__"
                            ? "Control Plane"
                            : groupKey;

                    if (collapsed) {
                        // Icon-only sidebar: just render entities flat, no headers
                        return groupEntities.map(renderEntityLink);
                    }

                    return html`
                        <div key=${groupKey} style=${{ marginTop: "2px" }}>
                            <div
                                class="sidebar-group-header"
                                onClick=${() => toggleEntityGroup(groupKey)}
                                title=${isGroupCollapsed ? "Expand " + label : "Collapse " + label}
                                style=${{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "4px",
                                    padding: "4px 12px",
                                    fontSize: "0.7rem",
                                    fontWeight: "600",
                                    textTransform: "uppercase",
                                    letterSpacing: "0.05em",
                                    color: "var(--color-text-muted)",
                                    cursor: "pointer",
                                    userSelect: "none",
                                    opacity: "0.8",
                                }}
                            >
                                <span style=${{
                                    display: "inline-block",
                                    transition: "transform 0.15s ease",
                                    transform: isGroupCollapsed ? "rotate(-90deg)" : "rotate(0deg)",
                                    fontSize: "0.55rem",
                                }}>${"\u25BC"}</span>
                                <span>${label}</span>
                                <span style=${{
                                    fontSize: "0.65rem",
                                    backgroundColor: "var(--color-bg-tertiary, rgba(255,255,255,0.08))",
                                    padding: "0 5px",
                                    borderRadius: "8px",
                                    marginLeft: "auto",
                                }}>${groupEntities.length}</span>
                            </div>
                            ${!isGroupCollapsed && groupEntities.map(renderEntityLink)}
                        </div>
                    `;
                };

                return html`
                    ${localEntities.length > 0 && renderGroup("__control_plane__", localEntities)}
                    ${groupKeys.map((key) => renderGroup(key, grouped[key]))}
                `;
            })()}

            <!-- Separator before global nav -->
            ${!collapsed && html`<div class="sidebar-divider"></div>`}

            <!-- Global nav items (flat) -->
            ${GLOBAL_NAV_ITEMS.map(
                (item) => html`
                    <a
                        key=${item.id}
                        class="sidebar-nav-item${activeTab === item.id ? " active" : ""}"
                        onClick=${() => navigate(item.id)}
                        title=${item.label}
                    >
                        <span class="nav-icon">${item.icon}</span>
                        ${!collapsed && html`<span class="nav-label-text">${item.label}</span>`}
                    </a>
                `
            )}
        </nav>
    `;
}

export { GroupedSidebar, GLOBAL_NAV_ITEMS };
