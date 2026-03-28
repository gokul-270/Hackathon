/**
 * MonitoringTab — Hub page with icon tiles linking to monitoring sub-pages.
 *
 * Similar to OperationsTab's NAV_SHORTCUTS pattern. Each tile navigates
 * to the corresponding tab via hash routing.
 *
 * @module tabs/MonitoringTab
 */
import { h } from "preact";
import { html } from "htm/preact";
import { useCallback } from "preact/hooks";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Monitoring sub-pages
// ---------------------------------------------------------------------------

const MONITORING_ITEMS = [
    { id: "alerts", label: "Alerts", icon: "\uD83D\uDD14", desc: "Active alerts & history" },
    { id: "statistics", label: "Statistics", icon: "\uD83D\uDCC8", desc: "System & performance metrics" },
    { id: "analysis", label: "Field Analysis", icon: "\uD83C\uDF3E", desc: "Field trial data analysis" },
    { id: "log-viewer", label: "Log Viewer", icon: "\uD83D\uDCDC", desc: "Centralized log viewer" },
    { id: "file-browser", label: "File Browser", icon: "\uD83D\uDCC2", desc: "Browse entity file systems" },
    { id: "bags", label: "Bag Manager", icon: "\uD83D\uDCBE", desc: "ROS2 bag recording & playback" },
];

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const STYLES = {
    container: {
        padding: "var(--spacing-lg)",
    },
    heading: {
        fontSize: "1.5rem",
        fontWeight: "600",
        color: "var(--text-primary)",
        marginBottom: "var(--spacing-sm)",
    },
    subtitle: {
        fontSize: "0.9rem",
        color: "var(--text-secondary)",
        marginBottom: "var(--spacing-xl)",
    },
    grid: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
        gap: "var(--spacing-lg)",
    },
    tile: {
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--spacing-xl) var(--spacing-lg)",
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: "var(--radius-lg, 12px)",
        cursor: "pointer",
        transition: "background 0.15s, border-color 0.15s, transform 0.15s",
        textDecoration: "none",
        minHeight: "120px",
    },
    tileIcon: {
        fontSize: "2rem",
        marginBottom: "var(--spacing-sm)",
    },
    tileLabel: {
        fontSize: "0.95rem",
        fontWeight: "600",
        color: "var(--text-primary)",
        marginBottom: "4px",
    },
    tileDesc: {
        fontSize: "0.8rem",
        color: "var(--text-secondary)",
        textAlign: "center",
    },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function MonitoringTab() {
    const navigate = useCallback((id) => {
        window.location.hash = "#" + id;
    }, []);

    return html`
        <div style=${STYLES.container}>
            <div style=${STYLES.heading}>\uD83D\uDCCA Monitoring</div>
            <div style=${STYLES.subtitle}>
                System monitoring, logs, and analysis tools
            </div>
            <div style=${STYLES.grid}>
                ${MONITORING_ITEMS.map(
                    (item) => html`
                        <div
                            key=${item.id}
                            class="monitoring-tile"
                            style=${STYLES.tile}
                            onClick=${() => navigate(item.id)}
                            onMouseEnter=${(e) => {
                                e.currentTarget.style.background =
                                    "var(--hover-bg)";
                                e.currentTarget.style.borderColor =
                                    "var(--accent-primary)";
                                e.currentTarget.style.transform =
                                    "translateY(-2px)";
                            }}
                            onMouseLeave=${(e) => {
                                e.currentTarget.style.background =
                                    "var(--bg-secondary)";
                                e.currentTarget.style.borderColor =
                                    "var(--border-color)";
                                e.currentTarget.style.transform = "none";
                            }}
                        >
                            <span style=${STYLES.tileIcon}>${item.icon}</span>
                            <span style=${STYLES.tileLabel}>${item.label}</span>
                            <span style=${STYLES.tileDesc}>${item.desc}</span>
                        </div>
                    `
                )}
            </div>
        </div>
    `;
}

registerTab("monitoring", MonitoringTab);
export default MonitoringTab;
