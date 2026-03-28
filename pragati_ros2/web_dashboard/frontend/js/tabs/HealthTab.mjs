/**
 * HealthTab — Preact component for the System Health tab.
 *
 * Migrated from vanilla JS as part of the incremental Preact migration
 * (task 7.1 of dashboard-frontend-migration).
 *
 * @module tabs/HealthTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useContext, useRef } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { WebSocketContext } from "../app.js";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5000;

/**
 * Subsystem definitions for health cards.
 * Each entry maps a subsystem key (from the API response) to its display info.
 * @type {Array<{key: string, label: string, icon: string}>}
 */
const SUBSYSTEMS = [
    { key: "motors", label: "Motors", icon: "\u2699\uFE0F" },
    { key: "can_bus", label: "CAN Bus", icon: "\uD83D\uDD0C" },
    { key: "safety", label: "Safety", icon: "\uD83D\uDEE1\uFE0F" },
    { key: "detection", label: "Detection", icon: "\uD83D\uDC41\uFE0F" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Determine the CSS class for a health status string.
 *
 * Maps API status values to the existing CSS classes:
 *   healthy/ok   -> health-ok
 *   unavailable  -> health-unavailable (grey)
 *   unknown      -> health-unknown
 *   anything else (warning/error/critical) -> health-error
 *
 * @param {string} status - Status string from the API
 * @returns {string} CSS class name
 */
function statusClass(status) {
    const s = (status || "unknown").toLowerCase();
    if (s === "ok" || s === "healthy") return "health-ok";
    if (s === "unavailable") return "health-unavailable";
    if (s === "unknown") return "health-unknown";
    return "health-error";
}

/**
 * Human-readable label for a status value.
 * @param {string} status
 * @returns {string}
 */
function statusLabel(status) {
    if (!status) return "Unavailable";
    return status.charAt(0).toUpperCase() + status.slice(1);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * A single health card for a subsystem.
 *
 * @param {object} props
 * @param {string} props.icon        - Emoji icon
 * @param {string} props.label       - Display name
 * @param {object|null} props.data   - Subsystem data from the API (has .status)
 * @param {string|null} props.error  - Error message (overrides data display)
 */
function HealthCard({ icon, label, data, error }) {
    let status = "unavailable";
    let displayText = "Unavailable";

    if (error) {
        status = "error";
        displayText = error;
    } else if (data) {
        status = data.status || "unavailable";
        displayText = statusLabel(status);
    }

    const cardClass = `health-card ${statusClass(status)}`;

    return html`
        <div class=${cardClass}>
            <h3>${icon} ${label}</h3>
            <div class="health-status">${displayText}</div>
        </div>
    `;
}

/**
 * Overall status summary bar.
 *
 * @param {object} props
 * @param {string} props.overallStatus - The overall_status from the API
 * @param {object|null} props.summary  - The summary counts from the API
 */
function OverallStatus({ overallStatus, summary }) {
    if (!overallStatus) return null;

    const badgeClass = `health-overall-badge ${statusClass(overallStatus)}`;

    return html`
        <div class="health-overall">
            <span class=${badgeClass}>
                System: ${statusLabel(overallStatus)}
            </span>
            ${summary && html`
                <span class="health-summary-counts">
                    ${summary.healthy > 0 && html`
                        <span class="health-count healthy">${summary.healthy} healthy</span>
                    `}
                    ${summary.warnings > 0 && html`
                        <span class="health-count warning">${summary.warnings} warning</span>
                    `}
                    ${summary.errors > 0 && html`
                        <span class="health-count error">${summary.errors} error</span>
                    `}
                    ${summary.critical_issues > 0 && html`
                        <span class="health-count critical">${summary.critical_issues} critical</span>
                    `}
                </span>
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function HealthTab() {
    const { data: wsData } = useContext(WebSocketContext);
    const systemState = wsData ? wsData.system_state : null;
    const ros2Available = systemState ? systemState.ros2_available : null;
    const isInitializing = systemState === null || systemState === undefined;

    /** @type {[object|null, Function]} */
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    /** @type {[string|null, Function]} */
    const [error, setError] = useState(null);

    const mountedRef = useRef(true);

    // ---- data loading -----------------------------------------------------

    const loadHealth = useCallback(async () => {
        const result = await safeFetch("/api/health/system");

        if (!mountedRef.current) return;

        if (!result) {
            setError("Connection error");
            setData(null);
            setLoading(false);
            return;
        }

        if (result.error) {
            setError(result.error);
            setData(null);
            setLoading(false);
            return;
        }

        setData(result);
        setError(null);
        setLoading(false);
    }, []);

    // ---- lifecycle --------------------------------------------------------

    // Initial load
    useEffect(() => {
        mountedRef.current = true;
        loadHealth();
        return () => {
            mountedRef.current = false;
        };
    }, [loadHealth]);

    // Polling — 5-second interval with cleanup
    useEffect(() => {
        const id = setInterval(() => {
            loadHealth();
        }, POLL_INTERVAL_MS);

        return () => {
            clearInterval(id);
        };
    }, [loadHealth]);

    // ---- render -----------------------------------------------------------

    if (isInitializing) {
        return html`
            <div class="section-header">
                <h2>System Health</h2>
            </div>
            <div class="initializing-placeholder" style=${{
                textAlign: 'center',
                padding: 'var(--spacing-xl)',
                color: 'var(--text-secondary)',
            }}>
                <div style=${{ fontSize: '1.2em', marginBottom: 'var(--spacing-sm)' }}>Initializing...</div>
                <div style=${{ fontSize: '0.9em', color: 'var(--text-muted)' }}>Waiting for system state</div>
            </div>
        `;
    }

    if (ros2Available === false) {
        return html`
            <div class="section-header">
                <h2>System Health</h2>
            </div>
            <div class="no-ros2-placeholder" style=${{
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--spacing-xl)',
                textAlign: 'center',
                color: 'var(--text-secondary)',
            }}>
                <div style=${{ fontSize: '2em', marginBottom: 'var(--spacing-sm)' }}>🛡️</div>
                <div style=${{ fontSize: '1.1em', marginBottom: 'var(--spacing-xs)' }}>Health monitoring requires ROS2</div>
                <div style=${{ fontSize: '0.9em', color: 'var(--text-muted)' }}>Connect to a ROS2 environment to view subsystem health</div>
            </div>
        `;
    }

    return html`
        <h2>System Health</h2>
        ${loading && html`<div class="loading">Loading health data...</div>`}
        ${!loading && error && !data && html`
            <div class="health-grid">
                ${SUBSYSTEMS.map(
                    (sub) => html`
                        <${HealthCard}
                            key=${sub.key}
                            icon=${sub.icon}
                            label=${sub.label}
                            data=${null}
                            error=${error}
                        />
                    `
                )}
            </div>
        `}
        ${!loading && data && html`
            <${OverallStatus}
                overallStatus=${data.overall_status}
                summary=${data.summary}
            />
            <div class="health-grid">
                ${SUBSYSTEMS.map(
                    (sub) => html`
                        <${HealthCard}
                            key=${sub.key}
                            icon=${sub.icon}
                            label=${sub.label}
                            data=${data[sub.key]}
                            error=${null}
                        />
                    `
                )}
            </div>
        `}
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("health", HealthTab);

export { HealthTab, statusClass, statusLabel, SUBSYSTEMS };
