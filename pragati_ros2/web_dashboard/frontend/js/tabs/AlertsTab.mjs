/**
 * AlertsTab — Preact component for the Alerts & Notifications tab.
 *
 * Migrated from vanilla JS as part of the incremental Preact migration
 * (task 6.3).
 *
 * @module tabs/AlertsTab
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a unix timestamp (seconds) to a locale string.
 * @param {number} timestamp - Unix seconds
 * @returns {string}
 */
function formatTimestamp(timestamp) {
    if (!timestamp) return "--";
    return new Date(timestamp * 1000).toLocaleString();
}

/**
 * Normalize API response to an array of alerts.
 * The endpoint returns `{ alerts: [...] }`.
 * @param {any} data
 * @returns {Array<Object>}
 */
function normalizeAlerts(data) {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.alerts)) return data.alerts;
    return [];
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * A single alert item.
 *
 * @param {object} props
 * @param {object}  props.alert   - Alert object from API
 * @param {boolean} props.busy    - Whether an action is in progress
 * @param {(alertId: string) => void} props.onAcknowledge
 */
function AlertItem({ alert, busy, onAcknowledge }) {
    const severity = alert.severity || "info";

    return html`
        <div class="alert-item ${severity}">
            <div class="alert-content">
                <div class="alert-title">${alert.rule_name}</div>
                <div class="alert-message">${alert.message}</div>
                <div class="alert-time">${formatTimestamp(alert.timestamp)}</div>
            </div>
            <button
                class="btn btn-sm"
                disabled=${busy}
                onClick=${() => onAcknowledge(alert.alert_id)}
            >
                Acknowledge
            </button>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function AlertsTab() {
    const { showToast } = useToast();
    const { data: wsData } = useContext(WebSocketContext);

    /** @type {[Array<Object>, Function]} */
    const [alerts, setAlerts] = useState([]);
    const [loading, setLoading] = useState(true);
    /** @type {[Set<string>, Function]} */
    const [busyIds, setBusyIds] = useState(() => new Set());

    // Refs for cleanup
    const mountedRef = useRef(true);

    // ---- data loading -----------------------------------------------------

    const loadAlerts = useCallback(async () => {
        const data = await safeFetch("/api/alerts/active");
        if (!mountedRef.current) return;

        setAlerts(normalizeAlerts(data));
        setLoading(false);
    }, []);

    // ---- WebSocket updates ------------------------------------------------

    useEffect(() => {
        if (wsData && wsData.alerts_update) {
            const updated = normalizeAlerts(wsData.alerts_update);
            if (updated.length > 0 || wsData.alerts_update.alerts) {
                setAlerts(updated);
                setLoading(false);
            }
        }
    }, [wsData]);

    // ---- actions ----------------------------------------------------------

    const acknowledgeAlert = useCallback(
        async (alertId) => {
            setBusyIds((prev) => {
                const next = new Set(prev);
                next.add(alertId);
                return next;
            });

            try {
                const result = await safeFetch(
                    `/api/alerts/${encodeURIComponent(alertId)}/acknowledge`,
                    { method: "POST" }
                );
                if (result && result.success) {
                    showToast("Alert acknowledged", "success");
                } else {
                    showToast("Failed to acknowledge alert", "error");
                }
            } catch (err) {
                showToast("Failed to acknowledge alert: " + err.message, "error");
            } finally {
                setBusyIds((prev) => {
                    const next = new Set(prev);
                    next.delete(alertId);
                    return next;
                });
                if (mountedRef.current) {
                    await loadAlerts();
                }
            }
        },
        [showToast, loadAlerts]
    );

    const clearAllAlerts = useCallback(async () => {
        if (alerts.length === 0) return;

        const allIds = alerts.map((a) => a.alert_id);
        setBusyIds(new Set(allIds));

        let successCount = 0;
        let failCount = 0;

        for (const alertId of allIds) {
            try {
                const result = await safeFetch(
                    `/api/alerts/${encodeURIComponent(alertId)}/clear`,
                    { method: "POST" }
                );
                if (result && result.success) {
                    successCount++;
                } else {
                    failCount++;
                }
            } catch {
                failCount++;
            }
        }

        if (failCount === 0) {
            showToast(`Cleared ${successCount} alert(s)`, "success");
        } else {
            showToast(
                `Cleared ${successCount}, failed ${failCount} alert(s)`,
                "warning"
            );
        }

        setBusyIds(new Set());
        if (mountedRef.current) {
            await loadAlerts();
        }
    }, [alerts, showToast, loadAlerts]);

    // ---- lifecycle --------------------------------------------------------

    // Initial load + cleanup
    useEffect(() => {
        mountedRef.current = true;
        loadAlerts();
        return () => {
            mountedRef.current = false;
        };
    }, [loadAlerts]);

    // Polling — 5-second interval with cleanup
    useEffect(() => {
        const id = setInterval(() => {
            loadAlerts();
        }, POLL_INTERVAL_MS);

        return () => {
            clearInterval(id);
        };
    }, [loadAlerts]);

    // ---- render -----------------------------------------------------------

    return html`
        <div class="section-header">
            <h2>Alerts & Notifications</h2>
            <div class="section-actions">
                <button
                    class="btn btn-sm"
                    onClick=${clearAllAlerts}
                    disabled=${alerts.length === 0}
                >
                    Clear All
                </button>
            </div>
        </div>

        <div class="alerts-list">
            ${loading && html`<p class="text-muted">Loading alerts...</p>`}
            ${!loading &&
            alerts.length === 0 &&
            html`<div class="empty-state">No active alerts</div>`}
            ${alerts.map(
                (alert) => html`
                    <${AlertItem}
                        key=${alert.alert_id}
                        alert=${alert}
                        busy=${busyIds.has(alert.alert_id)}
                        onAcknowledge=${acknowledgeAlert}
                    />
                `
            )}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("alerts", AlertsTab);

export { AlertsTab };
