/**
 * Preact App Shell for Pragati Dashboard
 *
 * Provides:
 * - Hash-based tab routing with mount/unmount lifecycle
 * - WebSocket context for real-time data with heartbeat & exponential backoff
 * - Toast notification context
 * - Disconnect banner for connection resilience
 *
 * @module app
 */
import { h, render, createContext } from "preact";
import { createPortal } from "preact/compat";
import {
    useState,
    useEffect,
    useCallback,
    useContext,
    useRef,
    useMemo,
} from "preact/hooks";
import { html } from "htm/preact";
import { ToastNotification } from "./components/ToastNotification.mjs";
import { DisconnectBanner } from "./components/DisconnectBanner.mjs";
import { ConnectionIndicator } from "./components/ConnectionIndicator.mjs";
import { GroupedSidebar } from "./components/GroupedSidebar.mjs";
// roleConfig.mjs is no longer imported — sidebar is entity-centric (Phase 6)
import { tabRegistry, registerTab } from "./tabRegistry.js";

// Tab imports — each calls registerTab() from tabRegistry.js at module top-level.
// No circular dependency: tabs import from tabRegistry.js, not from app.js.
import "./tabs/NodesTab.mjs";
import "./tabs/ParametersTab.mjs";
import "./tabs/SettingsTab.mjs";
import "./tabs/SystemServicesTab.mjs";
import "./tabs/TopicsTab.mjs";
import "./tabs/ServicesTab.mjs";
import "./tabs/AlertsTab.mjs";
import "./tabs/HealthTab.mjs";
import "./tabs/SyncTab.mjs";
import "./tabs/BagManagerTab.mjs";
import "./tabs/FieldAnalysisTab.mjs";
import "./tabs/MultiArmTab.mjs";
import "./tabs/LaunchControlTab.mjs";
import "./tabs/StatisticsTab.mjs";
import "./tabs/MotorConfigTab.mjs";
import "./tabs/FileBrowserTab.mjs";
import "./tabs/LogViewerTab.mjs";
import "./tabs/OperationsTab.mjs";
import "./tabs/MonitoringTab.mjs";
import "./tabs/FleetOverview.mjs";
import "./components/EntityDetailShell.mjs";

// ---------------------------------------------------------------------------
// Contexts
// ---------------------------------------------------------------------------

/**
 * @type {import('preact').Context<{
 *   data: Object,
 *   send: Function,
 *   connected: boolean,
 *   disconnected: boolean
 * }>}
 */
export const WebSocketContext = createContext({
    data: {},
    send: () => {},
    connected: false,
    disconnected: false,
});

/** @type {import('preact').Context<{showToast: Function}>} */
export const ToastContext = createContext({ showToast: () => {} });

// ---------------------------------------------------------------------------
// Exponential backoff
// ---------------------------------------------------------------------------

/**
 * Calculate reconnect delay with exponential backoff.
 * Starts at 1s, doubles each attempt, capped at 30s.
 *
 * @param {number} attempt - Zero-based attempt number
 * @returns {number} Delay in milliseconds
 */
export function getBackoffDelay(attempt) {
    return Math.min(1000 * Math.pow(2, attempt), 30000);
}

// ---------------------------------------------------------------------------
// WebSocket Provider
// ---------------------------------------------------------------------------

const WS_PING_INTERVAL = 3000;
const WS_PONG_TIMEOUT = 5000;

/**
 * Manages a WebSocket connection to /ws with automatic reconnection,
 * heartbeat (ping/pong), exponential backoff, and visibility-aware polling.
 * Children can access data + send via useContext(WebSocketContext).
 */
function WebSocketProvider({ children }) {
    const [connected, setConnected] = useState(false);
    const [disconnected, setDisconnected] = useState(false);
    const [data, setData] = useState({});
    const [reconnectCountdown, setReconnectCountdown] = useState(0);
    const wsRef = useRef(null);
    const reconnectRef = useRef(null);
    const countdownRef = useRef(null);
    const pingRef = useRef(null);
    const pongCheckRef = useRef(null);
    const lastPongRef = useRef(Date.now());
    const attemptRef = useRef(0);
    const wasConnectedRef = useRef(false);
    const disconnectedRef = useRef(false);

    /** Stop all heartbeat timers. */
    const stopHeartbeat = useCallback(() => {
        if (pingRef.current) {
            clearInterval(pingRef.current);
            pingRef.current = null;
        }
        if (pongCheckRef.current) {
            clearTimeout(pongCheckRef.current);
            pongCheckRef.current = null;
        }
    }, []);

    /** Start heartbeat ping/pong cycle. */
    const startHeartbeat = useCallback(() => {
        stopHeartbeat();
        lastPongRef.current = Date.now();

        pingRef.current = setInterval(() => {
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                wsRef.current.send(JSON.stringify({ type: "ping" }));

                // Clear any previous pong-check timeout before creating a new one
                if (pongCheckRef.current) {
                    clearTimeout(pongCheckRef.current);
                    pongCheckRef.current = null;
                }

                // Check for pong timeout
                pongCheckRef.current = setTimeout(() => {
                    // Guard: don't trigger disconnect if already torn down
                    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
                        return;
                    }
                    const elapsed = Date.now() - lastPongRef.current;
                    if (elapsed >= WS_PONG_TIMEOUT) {
                        console.warn("[ws] pong timeout — marking disconnected");
                        setConnected(false);
                        setDisconnected(true);
                        disconnectedRef.current = true;
                        if (wsRef.current) {
                            wsRef.current.close();
                        }
                    }
                }, WS_PONG_TIMEOUT);
            }
        }, WS_PING_INTERVAL);
    }, [stopHeartbeat]);

    /** Stop reconnect countdown timer. */
    const stopCountdown = useCallback(() => {
        if (countdownRef.current) {
            clearInterval(countdownRef.current);
            countdownRef.current = null;
        }
        setReconnectCountdown(0);
    }, []);

    /** Schedule a reconnect with exponential backoff and countdown. */
    const scheduleReconnect = useCallback(
        (connectFn) => {
            const delay = getBackoffDelay(attemptRef.current);
            attemptRef.current += 1;

            // Start countdown
            let remaining = Math.ceil(delay / 1000);
            setReconnectCountdown(remaining);
            countdownRef.current = setInterval(() => {
                remaining -= 1;
                if (remaining <= 0) {
                    clearInterval(countdownRef.current);
                    countdownRef.current = null;
                    setReconnectCountdown(0);
                } else {
                    setReconnectCountdown(remaining);
                }
            }, 1000);

            reconnectRef.current = setTimeout(connectFn, delay);
        },
        []
    );

    const connect = useCallback(() => {
        if (wsRef.current && wsRef.current.readyState <= 1) return;
        // Don't connect if tab is hidden
        if (document.hidden) return;

        stopCountdown();

        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(`${proto}//${location.host}/ws`);

        ws.onopen = () => {
            const wasDisconnected = disconnectedRef.current || wasConnectedRef.current;
            setConnected(true);
            setDisconnected(false);
            disconnectedRef.current = false;
            attemptRef.current = 0;
            wasConnectedRef.current = true;
            console.log("[ws] connected");
            startHeartbeat();

            // On reconnection, request fresh data
            if (wasDisconnected) {
                try {
                    ws.send(JSON.stringify({ type: "refresh" }));
                } catch (_e) {
                    // Ignore send errors on fresh connection
                }
            }
        };

        ws.onmessage = (evt) => {
            try {
                const msg = JSON.parse(evt.data);
                // Handle pong responses
                if (msg.type === "pong") {
                    lastPongRef.current = Date.now();
                    return;
                }

                // Task 3.1: Envelope unwrapping — messages with meta.msg_type
                if (msg.meta && msg.meta.msg_type) {
                    const msgType = msg.meta.msg_type;
                    const payload = msg.data;
                    // Store by msg_type key AND as system_state for system_update
                    if (msgType === "system_update") {
                        setData((prev) => ({
                            ...prev,
                            [msgType]: payload,
                            system_state: payload,
                        }));
                    } else {
                        setData((prev) => ({ ...prev, [msgType]: payload }));
                    }
                    return;
                }

                // Task 3.2: Non-enveloped messages by type field
                if (msg.type === "system_state" || msg.type === "system_update") {
                    setData((prev) => ({ ...prev, system_state: msg.data || msg }));
                    return;
                }

                // Handshake messages — ignore
                if (msg.status === "connected") {
                    return;
                }

                // Other typed messages — store by type key
                if (msg.type) {
                    setData((prev) => ({ ...prev, [msg.type]: msg.data || msg }));
                    return;
                }

                // Fallback: merge unknown shape into state
                setData((prev) => ({ ...prev, ...msg }));
            } catch (e) {
                // Ignore non-JSON messages
            }
        };

        ws.onclose = () => {
            setConnected(false);
            setDisconnected(true);
            disconnectedRef.current = true;
            wsRef.current = null;
            stopHeartbeat();

            // Task 3.3: Clear real-time data on disconnect
            setData((prev) => ({
                ...prev,
                performance_update: null,
                health_update: null,
                alerts_update: null,
                system_state: null,
            }));

            scheduleReconnect(() => connect());
        };

        ws.onerror = () => {
            ws.close();
        };

        wsRef.current = ws;
    }, [startHeartbeat, stopHeartbeat, stopCountdown, scheduleReconnect]);

    const send = useCallback((msg) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(
                typeof msg === "string" ? msg : JSON.stringify(msg)
            );
        }
    }, []);

    // Visibility-aware connection management
    useEffect(() => {
        const onVisibility = () => {
            if (document.hidden) {
                // Tab hidden: stop heartbeat, clear reconnect timers
                stopHeartbeat();
                if (reconnectRef.current) {
                    clearTimeout(reconnectRef.current);
                    reconnectRef.current = null;
                }
                stopCountdown();
            } else {
                // Tab visible: reconnect if not connected
                if (
                    !wsRef.current ||
                    wsRef.current.readyState !== WebSocket.OPEN
                ) {
                    connect();
                } else {
                    startHeartbeat();
                }
            }
        };
        document.addEventListener("visibilitychange", onVisibility);
        return () =>
            document.removeEventListener("visibilitychange", onVisibility);
    }, [connect, startHeartbeat, stopHeartbeat, stopCountdown]);

    // Initial connection
    useEffect(() => {
        connect();
        return () => {
            stopHeartbeat();
            stopCountdown();
            clearTimeout(reconnectRef.current);
            if (wsRef.current) {
                wsRef.current.onclose = null; // prevent reconnect on intentional close
                wsRef.current.close();
            }
        };
    }, [connect, stopHeartbeat, stopCountdown]);

    const value = useMemo(
        () => ({ data, send, connected, disconnected, reconnectCountdown }),
        [data, send, connected, disconnected, reconnectCountdown]
    );

    return html`
        <${WebSocketContext.Provider} value=${value}>
            ${children}
        <//>
    `;
}

// ---------------------------------------------------------------------------
// Toast Provider
// ---------------------------------------------------------------------------

let _toastId = 0;

const TOAST_DURATIONS = {
    success: 5000,
    info: 5000,
    warning: 10000,
    error: 10000,
};

/**
 * Manages toast notifications. Children can call showToast via useContext(ToastContext).
 */
function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);

    const showToast = useCallback((message, severity = "info") => {
        const id = ++_toastId;
        const duration = TOAST_DURATIONS[severity] || 5000;

        setToasts((prev) => [...prev, { id, message, severity }]);

        setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== id));
        }, duration);

        return id;
    }, []);

    // Listen for safefetch:error events and show error toasts
    useEffect(() => {
        const handler = (e) => {
            const { message } = e.detail || {};
            if (message) {
                showToast(message, "error");
            }
        };
        window.addEventListener("safefetch:error", handler);
        return () => window.removeEventListener("safefetch:error", handler);
    }, [showToast]);

    const dismissToast = useCallback((id) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const value = useMemo(() => ({ showToast }), [showToast]);

    return html`
        <${ToastContext.Provider} value=${value}>
            ${children}
            <${ToastContainer} toasts=${toasts} onDismiss=${dismissToast} />
        <//>
    `;
}

/**
 * Renders stacked toasts at bottom-right.
 */
function ToastContainer({ toasts, onDismiss }) {
    if (!toasts.length) return null;

    return html`
        <div class="preact-toast-container" style=${{
            position: "fixed",
            bottom: "20px",
            right: "20px",
            zIndex: 10000,
            display: "flex",
            flexDirection: "column-reverse",
            gap: "8px",
            maxWidth: "400px",
        }}>
            ${toasts.map(
                (t) => html`
                    <${ToastNotification}
                        key=${t.id}
                        id=${t.id}
                        message=${t.message}
                        severity=${t.severity}
                        onDismiss=${onDismiss}
                    />
                `
            )}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// App Shell
// ---------------------------------------------------------------------------

/**
 * Test whether a hash string is an entity detail route.
 * Matches: /entity/{id} or /entity/{id}/{tab}
 * @param {string} hash - Hash without the '#' prefix
 * @returns {boolean}
 */
function isEntityDetailRoute(hash) {
    return /^\/?entity\/[^/]+/.test(hash);
}

/**
 * Main app shell component. Renders Preact tabs into section containers
 * based on the active hash route. Includes the DisconnectBanner overlay.
 */
function AppShell() {
    const [activeTab, setActiveTab] = useState(() => {
        const hash = location.hash.replace("#", "");
        // Entity detail routes map to the "entity-detail" section
        if (isEntityDetailRoute(hash)) return "entity-detail";
        return hash.replace("/", "") || "fleet-overview";
    });

    // Role-based filtering removed (Phase 6) — sidebar is entity-centric

    // Task 2.6: Set hash to #fleet-overview when no hash is present (default route)
    useEffect(() => {
        if (!location.hash || location.hash === "#" || location.hash === "#/") {
            location.hash = "fleet-overview";
        }
    }, []);

    // Listen for hash changes (browser back/forward + sidebar clicks)
    // Special handling for entity detail routes: #/entity/{id}/{tab}
    //
    // -----------------------------------------------------------------------
    // Legacy URL mapping (Task 6.4a)
    // -----------------------------------------------------------------------
    // Old bare-hash routes → new entity-scoped equivalents:
    //
    //   #overview          → stays as #overview (global System Overview)
    //   #nodes             → #/entity/local/nodes
    //   #topics            → #/entity/local/topics
    //   #services          → #/entity/local/services
    //   #parameters        → #/entity/local/parameters
    //   #health            → #/entity/local/health
    //   #motor-config      → #/entity/local/motor-config
    //   #statistics        → stays as #statistics (global)
    //   #analysis          → stays as #analysis (global)
    //   #bags              → stays as #bags (global)
    //   #alerts            → stays as #alerts (global)
    //   #settings          → stays as #settings (global)
    //   #launch-control    → stays as #launch-control (global)
    //   #safety            → stays as #safety (global)
    //   #sync-deploy       → stays as #sync-deploy (global)
    //   #systemd-services  → stays as #systemd-services (global)
    //   #multi-arm         → stays as #multi-arm (global)
    //   #fleet             → stays as #fleet (global, legacy Fleet Hub)
    //   #file-browser      → stays as #file-browser (global)
    //   #log-viewer        → stays as #log-viewer (global)
    // -----------------------------------------------------------------------

    /** Bare hash tabs that should redirect to entity-scoped routes (Task 6.4b, 8.6) */
    const LEGACY_ENTITY_TABS = useMemo(
        () =>
            new Set([
                "nodes",
                "topics",
                "services",
                "parameters",
                "health",
            ]),
        []
    );

    useEffect(() => {
        const onHashChange = () => {
            let hash = location.hash.replace("#", "");
            // Treat #/ as fleet-overview
            if (hash === "/") hash = "fleet-overview";
            if (!hash) return;

            // #logs → global LogViewerTab (not entity-scoped)
            if (hash === "logs") {
                location.hash = "log-viewer";
                return;
            }

            // Task 6.4b: Legacy entity-scoped tab fallback — redirect bare
            // hashes (e.g. #nodes) to the entity-scoped equivalent
            if (LEGACY_ENTITY_TABS.has(hash)) {
                location.hash = "/entity/local/" + hash;
                return;
            }

            // Legacy #overview redirect to fleet-overview (System Overview removed)
            if (hash === "overview" || hash === "safety") {
                location.hash = "fleet-overview";
                return;
            }

            // Motor Config is now a global standalone tool, not an entity sub-tab.
            // Redirect #/entity/*/motor-config to #motor-config.
            const motorConfigEntityMatch = hash.match(/^\/?entity\/[^/]+\/motor-config$/);
            if (motorConfigEntityMatch) {
                location.hash = "motor-config";
                return;
            }

            // Entity detail route: map to "entity-detail" section
            if (isEntityDetailRoute(hash)) {
                setActiveTab("entity-detail");
                return;
            }

            setActiveTab(hash);
        };
        window.addEventListener("hashchange", onHashChange);
        return () => window.removeEventListener("hashchange", onHashChange);
    }, [LEGACY_ENTITY_TABS]);

    // Toggle CSS visibility of sections
    useEffect(() => {
        // Toggle .active on content-section divs
        document.querySelectorAll(".content-section").forEach((section) => {
            const id = section.id.replace("-section", "");
            if (id === activeTab) {
                section.classList.add("active");
            } else {
                section.classList.remove("active");
            }
        });
    }, [activeTab]);

    // Unmount-on-switch: only render the active tab's portal.
    // Previous tab is unmounted (DOM removed), cleanup functions fire.
    const tabPortals = Object.keys(tabRegistry)
        .filter((sectionId) => sectionId === activeTab)
        .map((sectionId) => {
            const container = document.getElementById(
                `${sectionId}-section-preact`
            );
            if (!container) return null;

            const TabComponent = tabRegistry[sectionId];
            return createPortal(html`<${TabComponent} />`, container);
        })
        .filter(Boolean);

    // Render the GroupedSidebar into the sidebar mount point
    useEffect(() => {
        const sidebarMount = document.getElementById("grouped-sidebar");
        if (sidebarMount) {
            render(
                html`<${GroupedSidebar} activeTab=${activeTab} />`,
                sidebarMount
            );
        }
    }, [activeTab]);

    // -------------------------------------------------------------------
    // Task 4.2: Wire connection indicator into header
    // -------------------------------------------------------------------
    const { connected, disconnected, reconnectCountdown, send } =
        useContext(WebSocketContext);
    const { showToast } = useContext(ToastContext);

    useEffect(() => {
        const dot = document.getElementById("connection-indicator");
        const text = document.getElementById("connection-text");
        if (!dot || !text) return;

        if (connected) {
            dot.style.backgroundColor = "#22c55e";
            dot.className = "indicator connected";
            text.textContent = "Connected";
        } else if (disconnected && reconnectCountdown > 0) {
            dot.style.backgroundColor = "#f59e0b";
            dot.className = "indicator reconnecting";
            text.textContent = `Reconnecting in ${reconnectCountdown}s...`;
        } else if (disconnected) {
            dot.style.backgroundColor = "#ef4444";
            dot.className = "indicator disconnected";
            text.textContent = "Disconnected";
        } else {
            dot.style.backgroundColor = "#f59e0b";
            dot.className = "indicator connecting";
            text.textContent = "Connecting...";
        }
    }, [connected, disconnected, reconnectCountdown]);

    // -------------------------------------------------------------------
    // Task 4.3: Wire E-STOP buttons (entity + all) with confirmation,
    // persistent banner, disable when no entities online, and reset
    // -------------------------------------------------------------------

    // Track e-stopped entities for the banner
    const [estoppedEntities, setEstoppedEntities] = useState([]);
    // Track known entities for E-Stop All / disable logic
    const [knownEntities, setKnownEntities] = useState([]);

    // Poll entities for E-Stop All availability
    useEffect(() => {
        const loadEntities = async () => {
            try {
                const resp = await fetch("/api/entities");
                if (resp.ok) {
                    const data = await resp.json();
                    const list = Array.isArray(data) ? data : (data.entities || []);
                    setKnownEntities(list);
                }
            } catch (_) {
                // ignore
            }
        };
        loadEntities();
        const interval = setInterval(loadEntities, 10000);
        return () => clearInterval(interval);
    }, []);

    // Derive active entity from hash for E-Stop current entity
    const activeEntityId = useMemo(() => {
        const hash = location.hash.replace("#", "");
        const match = hash.match(/^\/?entity\/([^/]+)/);
        return match ? decodeURIComponent(match[1]) : null;
    }, [activeTab]);

    // Enable/disable E-Stop entity button based on active entity
    useEffect(() => {
        const btn = document.getElementById("estop-entity-btn");
        if (!btn) return;
        btn.disabled = !activeEntityId;
        btn.title = activeEntityId
            ? `E-Stop entity: ${activeEntityId} (Ctrl+Shift+X)`
            : "Navigate to an entity to use E-Stop";
    }, [activeEntityId]);

    // E-Stop current entity handler
    useEffect(() => {
        const btn = document.getElementById("estop-entity-btn");
        if (!btn) return;
        const handler = async () => {
            if (!activeEntityId) {
                showToast("No entity selected — navigate to an entity first", "warning");
                return;
            }
            const confirmed = confirm(
                `Emergency Stop entity "${activeEntityId}"?\n\nAll motors will be immediately disabled.`
            );
            if (!confirmed) return;

            try {
                const resp = await fetch(
                    `/api/entities/${encodeURIComponent(activeEntityId)}/estop`,
                    { method: "POST" }
                );
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                showToast(`E-Stop sent to ${activeEntityId}`, "warning");
                setEstoppedEntities((prev) => {
                    if (prev.includes(activeEntityId)) return prev;
                    return [...prev, activeEntityId];
                });
            } catch (err) {
                showToast(
                    `E-STOP failed for ${activeEntityId} — ${err.message}. Use physical E-STOP.`,
                    "error"
                );
            }
        };
        btn.addEventListener("click", handler);
        return () => btn.removeEventListener("click", handler);
    }, [activeEntityId, showToast]);

    // E-Stop All handler
    useEffect(() => {
        const btn = document.getElementById("estop-all-btn");
        if (!btn) return;
        const handler = async () => {
            const onlineEntities = knownEntities.filter((e) => e.status === "online");
            if (onlineEntities.length === 0) {
                showToast("No online entities to stop", "warning");
                return;
            }
            const confirmed = confirm(
                `Emergency Stop ALL ${onlineEntities.length} online entities?\n\nAll motors will be immediately disabled.`
            );
            if (!confirmed) return;

            const results = await Promise.allSettled(
                onlineEntities.map(async (entity) => {
                    const resp = await fetch(
                        `/api/entities/${encodeURIComponent(entity.id)}/estop`,
                        { method: "POST" }
                    );
                    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                    return entity.id;
                })
            );

            let successCount = 0;
            let failCount = 0;
            const newEstopped = [];
            const failures = [];
            results.forEach((result, i) => {
                if (result.status === "fulfilled") {
                    successCount++;
                    newEstopped.push(onlineEntities[i].id);
                } else {
                    failCount++;
                    failures.push(
                        `${onlineEntities[i].name || onlineEntities[i].id}: ${result.reason.message}`
                    );
                }
            });

            setEstoppedEntities((prev) => {
                const combined = new Set([...prev, ...newEstopped]);
                return [...combined];
            });

            if (failCount === 0) {
                showToast(
                    `E-Stop sent to ${successCount} entit${successCount === 1 ? "y" : "ies"}`,
                    "warning"
                );
            } else {
                showToast(
                    `E-Stop: ${successCount} succeeded, ${failCount} failed. ${failures.join("; ")}`,
                    "error"
                );
            }
        };
        btn.addEventListener("click", handler);
        return () => btn.removeEventListener("click", handler);
    }, [knownEntities, showToast]);

    // Disable E-Stop All when no entities online
    useEffect(() => {
        const btn = document.getElementById("estop-all-btn");
        if (!btn) return;
        const hasOnline = knownEntities.some((e) => e.status === "online");
        btn.disabled = !hasOnline;
        btn.title = hasOnline
            ? "E-Stop ALL entities (Ctrl+Shift+A)"
            : "No online entities to stop";
    }, [knownEntities]);

    // Persistent E-Stop banner
    useEffect(() => {
        const banner = document.getElementById("estop-banner");
        const entitiesSpan = document.getElementById("estop-banner-entities");
        if (!banner || !entitiesSpan) return;

        if (estoppedEntities.length === 0) {
            banner.style.display = "none";
            entitiesSpan.innerHTML = "";
            return;
        }

        banner.style.display = "flex";
        // Render entity names with per-entity reset buttons
        entitiesSpan.innerHTML = estoppedEntities
            .map(
                (id) =>
                    `<span class="estop-banner-entity">${id} ` +
                    `<button class="estop-reset-btn" data-entity-id="${id}" title="Reset E-Stop for ${id}">Reset</button>` +
                    `</span>`
            )
            .join(" ");

        // Wire reset buttons
        const resetHandler = async (e) => {
            const entityId = e.target.dataset.entityId;
            if (!entityId) return;
            try {
                const resp = await fetch("/api/safety/reset", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ entity_id: entityId }),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                showToast(`E-Stop reset for ${entityId}`, "success");
                setEstoppedEntities((prev) => prev.filter((id) => id !== entityId));
            } catch (err) {
                showToast(`Reset failed for ${entityId}: ${err.message}`, "error");
            }
        };

        const buttons = entitiesSpan.querySelectorAll(".estop-reset-btn");
        buttons.forEach((btn) => btn.addEventListener("click", resetHandler));
        return () => {
            buttons.forEach((btn) => btn.removeEventListener("click", resetHandler));
        };
    }, [estoppedEntities, showToast]);

    // -------------------------------------------------------------------
    // Task 4.4: Wire Refresh button
    // -------------------------------------------------------------------
    useEffect(() => {
        const refreshBtn = document.getElementById("refresh-btn");
        if (!refreshBtn) return;
        const handler = () => {
            if (connected) {
                send({ type: "refresh" });
            } else {
                window.location.reload();
            }
        };
        refreshBtn.addEventListener("click", handler);
        return () => refreshBtn.removeEventListener("click", handler);
    }, [connected, send]);

    // -------------------------------------------------------------------
    // Populate header #system-time (local clock, updates every 30s)
    // -------------------------------------------------------------------
    useEffect(() => {
        const el = document.getElementById("system-time");
        if (!el) return;
        const MONTHS = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ];
        const update = () => {
            const now = new Date();
            const mon = MONTHS[now.getMonth()];
            const day = now.getDate();
            const h = String(now.getHours()).padStart(2, "0");
            const m = String(now.getMinutes()).padStart(2, "0");
            el.textContent = `${mon} ${day}, ${h}:${m}`;
        };
        update();
        const id = setInterval(update, 30_000);
        return () => clearInterval(id);
    }, []);

    // Render the DisconnectBanner as a top-level overlay
    return html`<${DisconnectBanner} />${tabPortals}`;
}

// ---------------------------------------------------------------------------
// Root — wraps shell with providers
// ---------------------------------------------------------------------------

function Root() {
    return html`
        <${WebSocketProvider}>
            <${ToastProvider}>
                <${AppShell} />
            <//>
        <//>
    `;
}

// ---------------------------------------------------------------------------
// Mount
// ---------------------------------------------------------------------------

// Create a mount point for the Preact root (renders DisconnectBanner + manages contexts)
const mountEl = document.createElement("div");
mountEl.id = "preact-root";
document.body.appendChild(mountEl);

render(html`<${Root} />`, mountEl);

// Export for tests
export { AppShell, WebSocketProvider, ToastProvider };
// Re-export tab registry for convenience
export { tabRegistry, registerTab };
