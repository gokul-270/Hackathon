/**
 * SystemServicesTab — Preact component for the Systemd Services tab.
 *
 * Migrated from vanilla JS (service_manager.js) as part of the incremental
 * Preact migration (task 5.3).
 *
 * Now exports a reusable `ServicePanel` component that can be embedded in
 * other tabs (e.g. Launch Control "Services" sub-tab). The standalone
 * SystemServicesTab redirects users to Launch Control.
 *
 * @module tabs/SystemServicesTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useRef, useMemo } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { useConfirmDialog } from "../components/ConfirmationDialog.mjs";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5000;

/**
 * Keywords for context-based service filtering.
 * A service whose name contains any keyword for a context is shown under
 * that context. Services matching NEITHER context appear in BOTH.
 */
const CONTEXT_KEYWORDS = {
    arm: ["arm", "pragati-arm"],
    vehicle: ["vehicle", "pragati-vehicle"],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Map active_state to a CSS status class suffix.
 * @param {string} state
 * @returns {string}
 */
function statusClass(state) {
    const s = (state || "unknown").toLowerCase();
    if (s === "active" || s === "running") return "service-status-active";
    if (s === "failed") return "service-status-failed";
    if (s === "activating" || s === "deactivating")
        return "service-status-activating";
    return "service-status-inactive";
}

/**
 * Normalize API response to an array of services.
 * The endpoint may return a plain array or `{ services: [...] }`.
 * @param {any} data
 * @returns {Array<Object>}
 */
function normalizeServices(data) {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.services)) return data.services;
    return [];
}

/**
 * Test whether a service name matches a given context.
 * @param {string} serviceName
 * @param {string} context - "arm" or "vehicle"
 * @returns {boolean}
 */
function matchesContext(serviceName, context) {
    const name = serviceName.toLowerCase();
    const keywords = CONTEXT_KEYWORDS[context];
    if (!keywords) return false;
    return keywords.some((kw) => name.includes(kw));
}

/**
 * Test whether a service name matches ANY known context.
 * @param {string} serviceName
 * @returns {boolean}
 */
function matchesAnyContext(serviceName) {
    return Object.keys(CONTEXT_KEYWORDS).some((ctx) =>
        matchesContext(serviceName, ctx)
    );
}

/**
 * Filter services by context.
 * - If contextFilter is null/undefined, return all services (no filtering).
 * - If contextFilter is "arm" or "vehicle", return services matching that
 *   context PLUS services matching neither context (shared/common services).
 *
 * @param {Array<Object>} services
 * @param {string|null} contextFilter
 * @returns {Array<Object>}
 */
function filterServicesByContext(services, contextFilter) {
    if (!contextFilter) return services;
    return services.filter((svc) => {
        const name = svc.name || "";
        // Include if it matches the requested context
        if (matchesContext(name, contextFilter)) return true;
        // Include if it matches NO context (shared/common service)
        if (!matchesAnyContext(name)) return true;
        // Exclude (belongs to a different context)
        return false;
    });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * A single service card.
 *
 * @param {object} props
 * @param {object}   props.service         - Service object from API
 * @param {boolean}  props.busy            - Whether an action is in progress
 * @param {boolean}  [props.disconnected=false] - WebSocket disconnected; locks actions
 * @param {(name: string) => void} props.onStart
 * @param {(name: string) => void} props.onStop
 * @param {(name: string) => void} props.onRestart
 * @param {(name: string, enabled: boolean) => void} props.onToggleEnable
 * @param {(name: string) => void} props.onViewLogs
 */
function ServiceCard({
    service,
    busy,
    disconnected = false,
    onStart,
    onStop,
    onRestart,
    onToggleEnable,
    onViewLogs,
}) {
    const name = service.name || "unknown";
    const state = (
        service.state ||
        service.active_state ||
        "unknown"
    ).toLowerCase();
    const enabled =
        service.enabled || service.unit_file_state === "enabled";

    const lockout = busy || disconnected;
    const lockTitle = disconnected ? "Unavailable \u2014 connection lost" : undefined;
    const lockClass = disconnected ? " locked-control" : "";

    return html`
        <div class="service-card" data-service=${name}>
            <div class="service-card-header">
                <span class="service-status-dot ${statusClass(state)}"></span>
                <span class="service-name">${name}</span>
                <span class="service-state">${state}</span>
            </div>
            <div class="service-card-actions">
                <button
                    class="btn btn-sm service-start-btn${lockClass}"
                    disabled=${lockout}
                    title=${lockTitle}
                    onClick=${() => onStart(name)}
                >
                    Start
                </button>
                <button
                    class="btn btn-sm service-stop-btn${lockClass}"
                    disabled=${lockout}
                    title=${lockTitle}
                    onClick=${() => onStop(name)}
                >
                    Stop
                </button>
                <button
                    class="btn btn-sm service-restart-btn${lockClass}"
                    disabled=${lockout}
                    title=${lockTitle}
                    onClick=${() => onRestart(name)}
                >
                    Restart
                </button>
                <label class="service-enable-toggle">
                    <input
                        type="checkbox"
                        class="service-enable-cb${lockClass}"
                        checked=${enabled}
                        disabled=${lockout}
                        title=${lockTitle}
                        onChange=${() => onToggleEnable(name, !enabled)}
                    />
                    <span class="service-enable-label">
                        ${enabled ? "Enabled" : "Disabled"}
                    </span>
                </label>
                <button
                    class="btn btn-sm service-logs-btn"
                    disabled=${busy}
                    onClick=${() => onViewLogs(name)}
                >
                    Logs
                </button>
            </div>
        </div>
    `;
}

/**
 * Log panel displayed below the service grid.
 *
 * @param {object} props
 * @param {string}  props.name  - Service name
 * @param {string}  props.logs  - Log text
 * @param {() => void} props.onClose
 */
function LogPanel({ name, logs, onClose }) {
    return html`
        <div id="service-log-panel">
            <div class="service-log-header">
                <h3 id="service-log-title">Logs: ${name}</h3>
                <button
                    id="service-log-close"
                    class="btn btn-secondary"
                    onClick=${onClose}
                >
                    Close
                </button>
            </div>
            <pre id="service-log-content" class="service-log-content">
${logs || "No logs available"}</pre
            >
        </div>
    `;
}

// ---------------------------------------------------------------------------
// ServicePanel — reusable component for embedding in other tabs
// ---------------------------------------------------------------------------

/**
 * Reusable service management panel.
 *
 * Renders the service grid with start/stop/restart/enable/logs controls.
 * Manages its own polling and state.
 *
 * @param {object} props
 * @param {string|null} [props.contextFilter] - "arm" or "vehicle" to filter services, null for all
 * @param {boolean}     [props.active=true]   - Whether this panel is visible; polling pauses when false
 * @param {boolean}     [props.disconnected=false] - WebSocket disconnected state; locks action buttons
 */
function ServicePanel({ contextFilter = null, active = true, disconnected = false }) {
    const { showToast } = useToast();
    const { dialog, confirm } = useConfirmDialog();

    /** @type {[Array<Object>, Function]} */
    const [services, setServices] = useState([]);
    const [loading, setLoading] = useState(true);
    /** @type {[{name: string, logs: string}|null, Function]} */
    const [logPanel, setLogPanel] = useState(null);
    /** @type {[Set<string>, Function]} */
    const [actionInProgress, setActionInProgress] = useState(
        () => new Set()
    );

    // Refs for cleanup
    const mountedRef = useRef(true);

    // ---- helpers ----------------------------------------------------------

    const markBusy = useCallback((name) => {
        setActionInProgress((prev) => {
            const next = new Set(prev);
            next.add(name);
            return next;
        });
    }, []);

    const markIdle = useCallback((name) => {
        setActionInProgress((prev) => {
            const next = new Set(prev);
            next.delete(name);
            return next;
        });
    }, []);

    // ---- data loading -----------------------------------------------------

    const loadServices = useCallback(async () => {
        const data = await safeFetch("/api/systemd/services");
        if (!mountedRef.current) return;

        setServices(normalizeServices(data));
        setLoading(false);
    }, []);

    // ---- context-filtered service list ------------------------------------

    const filteredServices = useMemo(
        () => filterServicesByContext(services, contextFilter),
        [services, contextFilter]
    );

    // ---- actions ----------------------------------------------------------

    const startService = useCallback(
        async (name) => {
            const ok = await confirm({
                title: "Start Service",
                message: `Start service "${name}"?`,
                confirmText: "Start",
                dangerous: false,
            });
            if (!ok) return;

            markBusy(name);
            try {
                const result = await safeFetch(
                    `/api/systemd/services/${encodeURIComponent(name)}/start`,
                    { method: "POST" }
                );
                if (result && !result.error) {
                    showToast(`Service ${name} started`, "success");
                } else {
                    showToast(
                        (result && result.error) ||
                            `Failed to start ${name}`,
                        "error"
                    );
                }
            } catch (err) {
                showToast("Failed to start service: " + err.message, "error");
            } finally {
                markIdle(name);
                await loadServices();
            }
        },
        [confirm, markBusy, markIdle, showToast, loadServices]
    );

    const stopService = useCallback(
        async (name) => {
            const ok = await confirm({
                title: "Stop Service",
                message: `Stop service "${name}"? This may interrupt running processes.`,
                confirmText: "Stop",
                dangerous: true,
            });
            if (!ok) return;

            markBusy(name);
            try {
                const result = await safeFetch(
                    `/api/systemd/services/${encodeURIComponent(name)}/stop`,
                    { method: "POST" }
                );
                if (result && !result.error) {
                    showToast(`Service ${name} stopped`, "success");
                } else {
                    showToast(
                        (result && result.error) ||
                            `Failed to stop ${name}`,
                        "error"
                    );
                }
            } catch (err) {
                showToast("Failed to stop service: " + err.message, "error");
            } finally {
                markIdle(name);
                await loadServices();
            }
        },
        [confirm, markBusy, markIdle, showToast, loadServices]
    );

    const restartService = useCallback(
        async (name) => {
            const ok = await confirm({
                title: "Restart Service",
                message: `Restart service "${name}"? This will briefly interrupt the service.`,
                confirmText: "Restart",
                dangerous: true,
            });
            if (!ok) return;

            markBusy(name);
            try {
                const result = await safeFetch(
                    `/api/systemd/services/${encodeURIComponent(name)}/restart`,
                    { method: "POST" }
                );
                if (result && !result.error) {
                    showToast(`Service ${name} restarted`, "success");
                } else {
                    showToast(
                        (result && result.error) ||
                            `Failed to restart ${name}`,
                        "error"
                    );
                }
            } catch (err) {
                showToast(
                    "Failed to restart service: " + err.message,
                    "error"
                );
            } finally {
                markIdle(name);
                await loadServices();
            }
        },
        [confirm, markBusy, markIdle, showToast, loadServices]
    );

    const toggleEnable = useCallback(
        async (name, shouldEnable) => {
            const action = shouldEnable ? "enable" : "disable";
            markBusy(name);
            try {
                const result = await safeFetch(
                    `/api/systemd/services/${encodeURIComponent(name)}/${action}`,
                    { method: "POST" }
                );
                if (result && !result.error) {
                    showToast(
                        `Service ${name} ${action}d`,
                        "success"
                    );
                } else {
                    showToast(
                        (result && result.error) ||
                            `Failed to ${action} ${name}`,
                        "error"
                    );
                }
            } catch (err) {
                showToast(
                    `Failed to ${action} service: ` + err.message,
                    "error"
                );
            } finally {
                markIdle(name);
                await loadServices();
            }
        },
        [markBusy, markIdle, showToast, loadServices]
    );

    const viewLogs = useCallback(async (name) => {
        setLogPanel({ name, logs: "Loading logs..." });
        try {
            const data = await safeFetch(
                `/api/systemd/services/${encodeURIComponent(name)}/logs`
            );
            if (!mountedRef.current) return;

            let logText = "No logs available";
            if (data && data.logs) {
                logText = data.logs;
            } else if (data && typeof data === "string") {
                logText = data;
            }
            setLogPanel({ name, logs: logText });
        } catch (err) {
            if (!mountedRef.current) return;
            setLogPanel({
                name,
                logs: "Failed to load logs: " + err.message,
            });
        }
    }, []);

    const closeLogs = useCallback(() => {
        setLogPanel(null);
    }, []);

    // ---- lifecycle --------------------------------------------------------

    // Mount/unmount tracking
    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
        };
    }, []);

    // Initial load + reload when becoming active
    useEffect(() => {
        if (active) {
            loadServices();
        }
    }, [active, loadServices]);

    // Polling — only when active
    useEffect(() => {
        if (!active) return;

        const id = setInterval(() => {
            loadServices();
        }, POLL_INTERVAL_MS);

        return () => {
            clearInterval(id);
        };
    }, [active, loadServices]);

    // Close log panel when becoming inactive
    useEffect(() => {
        if (!active) {
            setLogPanel(null);
        }
    }, [active]);

    // ---- render -----------------------------------------------------------

    return html`
        <div class="section-grid" id="service-list-container">
            ${loading && html`<p class="text-muted">Loading services...</p>`}
            ${!loading &&
            filteredServices.length === 0 &&
            html`<div class="empty-state">No services found</div>`}
            ${filteredServices.map(
                (svc) => html`
                    <${ServiceCard}
                        key=${svc.name}
                        service=${svc}
                        busy=${actionInProgress.has(svc.name)}
                        disconnected=${disconnected}
                        onStart=${startService}
                        onStop=${stopService}
                        onRestart=${restartService}
                        onToggleEnable=${toggleEnable}
                        onViewLogs=${viewLogs}
                    />
                `
            )}
        </div>

        ${logPanel &&
        html`
            <${LogPanel}
                name=${logPanel.name}
                logs=${logPanel.logs}
                onClose=${closeLogs}
            />
        `}

        ${dialog}
    `;
}

// ---------------------------------------------------------------------------
// Standalone tab (backward compat — redirects to Launch Control)
// ---------------------------------------------------------------------------

/**
 * Standalone SystemServicesTab.
 * When accessed directly via #systemd-services, redirects the user to the
 * Launch Control tab. Kept for backward compatibility with bookmarks/URLs.
 */
function SystemServicesTab() {
    useEffect(() => {
        // Redirect to launch-control tab
        window.location.hash = "#launch-control";
    }, []);

    return html`
        <p class="text-muted">
            Redirecting to Launch Control...
        </p>
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("systemd-services", SystemServicesTab);

export { SystemServicesTab, ServicePanel };
