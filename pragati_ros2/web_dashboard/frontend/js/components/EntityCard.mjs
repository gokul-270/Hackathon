/**
 * EntityCard — Preact component for displaying a single entity in the fleet overview.
 *
 * Shows:
 * - Entity name and role badge (vehicle/arm)
 * - Online/offline status indicator (green/red dot)
 * - CPU, memory, temperature gauges (stat bars)
 * - ROS2 node count (or "—" when ros2_available is false)
 * - First error message (if any)
 * - Greyed-out metrics when entity is offline (stale data)
 *
 * Reuses existing CSS classes: .stat-card, .stat-bar, .stat-bar-fill,
 * .health-ok, .health-error, .health-unknown
 *
 * @module components/EntityCard
 */
import { h } from "preact";
import { useMemo } from "preact/hooks";
import { html } from "htm/preact";
import {
    deriveCardHealthSummary,
    healthBadgeClass,
} from "../utils/entityHealthSummary.mjs";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a last_seen timestamp into a relative time string.
 * @param {string|null} isoString
 * @returns {string}
 */
function formatLastSeen(isoString) {
    if (!isoString) return "Never";
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "Invalid";

    const diffMs = Date.now() - d.getTime();
    const diffSec = Math.floor(diffMs / 1000);

    if (diffSec < 5) return "Just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return d.toLocaleDateString();
}

/**
 * Format a last_seen timestamp into absolute "Mon DD, HH:MM".
 * @param {string|null} isoString
 * @returns {string}
 */
function formatAbsoluteTime(isoString) {
    if (!isoString) return "";
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "";
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const mon = months[d.getMonth()];
    const day = d.getDate();
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${mon} ${day}, ${hh}:${mm}`;
}

/**
 * Map entity_type to a display label for the role badge.
 * @param {string} entityType
 * @returns {string}
 */
function roleBadgeLabel(entityType) {
    switch ((entityType || "").toLowerCase()) {
        case "vehicle":
            return "Vehicle";
        case "arm":
            return "Arm";
        case "dev":
            return "Dev";
        default:
            return entityType || "Unknown";
    }
}

/**
 * Determine a color class hint for temperature.
 * @param {number|null} tempC
 * @returns {string} CSS color variable
 */
function tempColor(tempC) {
    if (tempC == null) return "var(--color-text-muted)";
    if (tempC >= 80) return "var(--color-error)";
    if (tempC >= 65) return "var(--color-warning)";
    return "var(--color-success)";
}

/**
 * Shorten a motor name for compact card display.
 * "joint5" -> "J5", "motor/joint3" -> "J3", "motor_1" -> "M1"
 */
function shortMotorName(name) {
    const jMatch = name.match(/joint\s*(\d+)/i);
    if (jMatch) return `J${jMatch[1]}`;
    const mMatch = name.match(/motor\s*[_-]?(\d+)/i);
    if (mMatch) return `M${mMatch[1]}`;
    // Vehicle motors: map exact production.yaml names to short labels
    const vehicleNames = {
        steering_left: "SL", steering_right: "SR", steering_front: "SF",
        drive_front: "DF", drive_left_back: "DLB", drive_right_back: "DRB",
    };
    if (vehicleNames[name.toLowerCase()]) return vehicleNames[name.toLowerCase()];
    // Fallback for any other drive/steering pattern
    const vehicleMatch = name.match(/^(drive|steering|steer)[_\s](.*)/i);
    if (vehicleMatch) {
        const type = vehicleMatch[1].toLowerCase().startsWith("s") ? "S" : "D";
        const pos = vehicleMatch[2].replace(/_/g, "").toUpperCase().slice(0, 3);
        return `${type}${pos}`;
    }
    return name.replace(/^motor\/?/i, "").trim() || name;
}

/**
 * Compact inline temperature line for motor + camera temps in entity cards.
 * Arms:    line 1: J3/J4/J5 motor temps   line 2: Cam temp
 * Vehicle: line 1: Steering motors        line 2: Drive motors
 */
function CompactTemperatures({ motorTemperatures, cameraTemperatureC, entityType, stale }) {
    const isArm = (entityType || "").toLowerCase() === "arm";
    const isVehicle = (entityType || "").toLowerCase() === "vehicle";
    const hasMotorTemps = motorTemperatures != null && typeof motorTemperatures === "object";
    const motorEntries = hasMotorTemps ? Object.entries(motorTemperatures) : [];
    const hasCameraTemp = isArm && cameraTemperatureC != null;

    if (!isArm && !isVehicle) return null;

    const dimStyle = { color: "var(--color-text-muted)", opacity: "0.4" };
    const mutedStyle = { color: "var(--color-text-muted)" };
    const sep = " \u2502 ";
    const rowStyle = {
        fontSize: "0.73rem",
        marginTop: "3px",
    };
    const wrapStyle = {
        display: "flex",
        flexDirection: "column",
        gap: "0px",
        marginTop: "4px",
        opacity: stale ? "0.5" : "1",
    };

    function tempSpan(temp) {
        return html`<span style=${{ color: tempColor(temp), fontWeight: "500" }}>
            ${temp != null ? `${temp.toFixed(0)}\u00B0C` : "N/A"}
        </span>`;
    }

    function motorRow(entries, placeholder) {
        if (entries.length > 0) {
            return html`<div style=${rowStyle}>
                <span style=${mutedStyle}>
                    ${entries.map(([name, temp], i) => html`
                        <span key=${name}>
                            <span>${shortMotorName(name)}: </span>
                            ${tempSpan(temp)}
                            ${i < entries.length - 1 ? sep : ""}
                        </span>
                    `)}
                </span>
            </div>`;
        }
        return html`<div style=${rowStyle}><span style=${dimStyle}>${placeholder}</span></div>`;
    }

    if (isArm) {
        const camRow = hasCameraTemp
            ? html`<div style=${rowStyle}>
                <span style=${mutedStyle}>Cam: ${tempSpan(cameraTemperatureC)}</span>
              </div>`
            : html`<div style=${rowStyle}><span style=${dimStyle}>Cam: N/A</span></div>`;

        return html`<div style=${wrapStyle}>
            ${motorRow(motorEntries, `J3: N/A${sep}J4: N/A${sep}J5: N/A`)}
            ${camRow}
        </div>`;
    }

    if (isVehicle) {
        const steeringEntries = motorEntries.filter(([n]) => n.toLowerCase().startsWith("steering"));
        const driveEntries    = motorEntries.filter(([n]) => n.toLowerCase().startsWith("drive"));
        return html`<div style=${wrapStyle}>
            ${motorRow(steeringEntries, `SL: N/A${sep}SR: N/A${sep}SF: N/A`)}
            ${motorRow(driveEntries,    `DF: N/A${sep}DLB: N/A${sep}DRB: N/A`)}
        </div>`;
    }

    return null;
}

/**
 * Determine bar fill color based on percentage.
 * @param {number} percent
 * @returns {string}
 */
function barColor(percent) {
    if (percent >= 90) return "var(--color-error)";
    if (percent >= 70) return "var(--color-warning)";
    return "var(--color-success)";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * A compact gauge bar for CPU/memory/temperature.
 * @param {object} props
 * @param {string} props.label
 * @param {number|null} props.value - Percentage or temperature value
 * @param {string} props.unit - Display unit (% or C)
 * @param {boolean} [props.stale=false] - Grey out when entity is offline
 */
function GaugeBar({ label, value, unit, stale = false }) {
    const displayValue = value != null ? `${value.toFixed(1)}${unit}` : "\u2014";
    const barPercent = unit === "\u00B0C"
        ? (value != null ? Math.min((value / 100) * 100, 100) : 0)
        : (value != null ? Math.min(value, 100) : 0);
    const fillColor = unit === "\u00B0C"
        ? tempColor(value)
        : barColor(barPercent);

    return html`
        <div style=${{
            marginBottom: "6px",
            opacity: stale ? "0.5" : "1",
        }}>
            <div style=${{
                display: "flex",
                justifyContent: "space-between",
                fontSize: "0.75rem",
                color: "var(--color-text-muted)",
                marginBottom: "2px",
            }}>
                <span>${label}</span>
                <span style=${{ color: stale ? "var(--color-text-muted)" : fillColor }}>
                    ${displayValue}
                </span>
            </div>
            <div class="stat-bar">
                <div
                    class="stat-bar-fill"
                    style=${{
                        width: `${barPercent}%`,
                        backgroundColor: stale ? "var(--color-text-muted)" : fillColor,
                        transition: "width 0.3s ease",
                    }}
                ></div>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

/**
 * EntityCard component.
 *
 * Supports two display modes:
 * - **Expanded** (default legacy): Full card with gauges, health summary, etc.
 * - **Collapsed**: Compact single-row header showing status dot, name, role
 *   badge, status label, and temperature. Click anywhere to toggle.
 *
 * When `collapsed` prop is provided, the card is controlled externally.
 * The `onToggleCollapse` callback fires when the user clicks to toggle.
 * The `onNavigate` callback fires when the user clicks the drill-down link
 * (only visible in expanded mode).
 *
 * @param {object} props
 * @param {object} props.entity - Entity data from /api/entities
 * @param {Function} [props.onClick] - Optional click handler for drill-down (legacy)
 * @param {boolean} [props.collapsed] - Whether card is in collapsed mode
 * @param {Function} [props.onToggleCollapse] - Called when user toggles collapse
 * @param {Function} [props.onNavigate] - Called when user clicks to navigate to detail
 * @param {boolean} [props.selected] - Whether this card is currently selected
 * @param {boolean} [props.selectionMode] - Whether selection mode is active
 * @param {Function} [props.onToggleSelect] - Callback receiving entity.id when checkbox is clicked
 */
function EntityCard({ entity, onClick, collapsed, onToggleCollapse, onNavigate, selected, selectionMode, onToggleSelect, disabled, onResumePolling }) {
    const isOnline = entity.status === "online";
    const isDegraded = entity.status === "degraded";
    const isUnknown = entity.status === "unknown" || !entity.status;
    const isOffline = !isOnline && !isDegraded && !isUnknown;
    const isSuspended = entity.polling_suspended === true;
    const metrics = entity.system_metrics || {};
    const ros2State = entity.ros2_state || {};
    const firstError = entity.errors && entity.errors.length > 0
        ? entity.errors[0]
        : null;

    const statusClass = isSuspended ? "health-suspended" : isOnline ? "health-ok" : isDegraded ? "health-warning" : "health-error";
    const statusLabel = isSuspended ? "Suspended" : isOnline ? "Online" : isDegraded ? "Degraded" : isUnknown ? "Unknown" : "Offline";
    const roleBadge = roleBadgeLabel(entity.entity_type);
    const lastSeen = formatLastSeen(entity.last_seen);
    const absTime = formatAbsoluteTime(entity.last_seen);

    // Prefer introspection node list length (if fetched) over heartbeat count.
    // FleetOverview may enrich entity data with ros2Nodes from introspection;
    // if present, its length is the authoritative count.
    const nodeCount = entity.ros2_available
        ? (entity.ros2Nodes != null
            ? entity.ros2Nodes.length
            : (ros2State.node_count != null ? ros2State.node_count : 0))
        : null;

    // Error message formatting
    const errorMessage = useMemo(() => {
        if (!firstError) return null;
        if (typeof firstError === "string") return firstError;
        return firstError.message || firstError.error || JSON.stringify(firstError);
    }, [firstError]);

    // Compact health summary for configured cards (D2, D3, D4)
    const healthSummary = useMemo(
        () => deriveCardHealthSummary(entity),
        [entity]
    );

    // Temperature for collapsed display
    const tempValue = metrics.temperature_c != null
        ? `${metrics.temperature_c.toFixed(0)}\u00B0C`
        : null;

    // Handle card click: toggle collapse if collapsible, else legacy onClick
    const handleCardClick = (e) => {
        // Don't toggle if clicking checkbox, detail link, or action button
        if (e.target.closest(".entity-card-checkbox") || e.target.closest(".entity-card-detail-link") || e.target.closest(".entity-card-action-btn")) {
            return;
        }
        if (onToggleCollapse) {
            onToggleCollapse(entity.id);
        } else if (onClick) {
            onClick();
        }
    };

    // ---- Collapsed mode: compact single row ----
    if (collapsed) {
        return html`
            <div
                class=${`stat-card entity-card--collapsed${selected ? " entity-card--selected" : ""}`}
                style=${{
                    cursor: "pointer",
                    position: "relative",
                    padding: "10px 16px",
                    minWidth: "0",
                    opacity: isOffline ? "0.85" : "1",
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    overflow: "hidden",
                }}
                onClick=${handleCardClick}
                title="Click to expand"
            >
                <!-- Chevron -->
                <span style=${{
                    fontSize: "0.65rem",
                    color: "var(--color-text-muted)",
                    flexShrink: "0",
                    transform: "rotate(-90deg)",
                    transition: "transform 0.15s ease",
                }}>${"\u25BC"}</span>

                <!-- Bulk selection checkbox -->
                ${selectionMode && html`
                    <input
                        type="checkbox"
                        class="entity-card-checkbox"
                        checked=${selected}
                        disabled=${disabled}
                        onClick=${(e) => {
                            e.stopPropagation();
                            if (!disabled) {
                                onToggleSelect && onToggleSelect(entity.id);
                            }
                        }}
                    />
                `}

                <!-- Status dot -->
                <span style=${{
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    backgroundColor: isOnline
                        ? "var(--color-success)"
                        : isSuspended
                            ? "#9e9e9e"
                            : "var(--color-error)",
                    flexShrink: "0",
                    display: "inline-block",
                }}></span>

                <!-- Name -->
                <span style=${{
                    fontWeight: "600",
                    fontSize: "0.9rem",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    flex: "1",
                    minWidth: "0",
                }}>
                    ${entity.name || entity.id}
                </span>

                <!-- Role badge -->
                <span style=${{
                    fontSize: "0.65rem",
                    padding: "1px 6px",
                    borderRadius: "8px",
                    backgroundColor: entity.entity_type === "vehicle"
                        ? "var(--color-accent)"
                        : entity.entity_type === "dev"
                            ? "var(--color-success)"
                            : "var(--color-warning)",
                    color: "#fff",
                    fontWeight: "600",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                    flexShrink: "0",
                }}>
                    ${roleBadge}
                </span>

                <!-- Status label -->
                <span class=${statusClass} style=${{
                    padding: "1px 6px",
                    borderRadius: "4px",
                    fontSize: "0.65rem",
                    flexShrink: "0",
                }}>
                    ${statusLabel}
                </span>

                <!-- Poll Now button (offline, degraded, or suspended entities) -->
                ${!isOnline && onResumePolling && html`
                    <button
                        class="entity-card-action-btn"
                        onClick=${(e) => {
                            e.stopPropagation();
                            onResumePolling(entity.id);
                        }}
                        title=${isSuspended ? "Resume polling for this entity" : "Trigger immediate poll"}
                        style=${{
                            fontSize: "0.7rem",
                            padding: "1px 5px",
                            borderRadius: "4px",
                            border: "1px solid var(--color-accent, #3b82f6)",
                            background: "transparent",
                            color: "var(--color-accent, #3b82f6)",
                            cursor: "pointer",
                            flexShrink: "0",
                            lineHeight: "1.4",
                        }}
                    >
                        ${isSuspended ? "\u25B6" : "\u21BB"}
                    </button>
                `}

                <!-- Temperature (if available) -->
                ${tempValue && html`
                    <span style=${{
                        fontSize: "0.75rem",
                        color: tempColor(metrics.temperature_c),
                        fontWeight: "500",
                        flexShrink: "0",
                        opacity: isOffline ? "0.5" : "1",
                    }}>
                        ${tempValue}
                    </span>
                `}
            </div>
        `;
    }

    // ---- Expanded mode: full card ----
    return html`
        <div
            class=${`stat-card${selected ? " entity-card--selected" : ""}`}
            style=${{
                cursor: onToggleCollapse ? "pointer" : (onClick ? "pointer" : "default"),
                position: "relative",
                padding: "16px",
                minWidth: "0",
                opacity: isOffline ? "0.85" : "1",
                flexDirection: "column",
                alignItems: "stretch",
            }}
            onClick=${handleCardClick}
        >
            <!-- Header: Name + Status + Role Badge -->
            <div style=${{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "12px",
                gap: "8px",
            }}>
                <div style=${{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    minWidth: "0",
                    flex: "1",
                }}>
                    <!-- Collapse chevron (only when collapsible) -->
                    ${onToggleCollapse && html`
                        <span style=${{
                            fontSize: "0.65rem",
                            color: "var(--color-text-muted)",
                            flexShrink: "0",
                            transition: "transform 0.15s ease",
                        }}>${"\u25BC"}</span>
                    `}
                    <!-- Bulk selection checkbox (inline before status dot) -->
                    ${selectionMode && html`
                        <input
                            type="checkbox"
                            class="entity-card-checkbox"
                            checked=${selected}
                            disabled=${disabled}
                            onClick=${(e) => {
                                e.stopPropagation();
                                if (!disabled) {
                                    onToggleSelect && onToggleSelect(entity.id);
                                }
                            }}
                        />
                    `}
                    <!-- Online/Offline indicator dot -->
                    <span style=${{
                        width: "10px",
                        height: "10px",
                        borderRadius: "50%",
                        backgroundColor: isOnline
                            ? "var(--color-success)"
                            : isSuspended
                                ? "#9e9e9e"
                                : "var(--color-error)",
                        flexShrink: "0",
                        display: "inline-block",
                    }}></span>
                    <span style=${{
                        fontWeight: "600",
                        fontSize: "0.95rem",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                    }}>
                        ${entity.name || entity.id}
                    </span>
                </div>
                <div style=${{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    flexShrink: "0",
                }}>
                    <!-- Detail link (only when collapsible — replaces the old onClick drill-down) -->
                    ${onNavigate && html`
                        <span
                            class="entity-card-detail-link"
                            onClick=${(e) => {
                                e.stopPropagation();
                                onNavigate();
                            }}
                            title="Open entity detail"
                            style=${{
                                fontSize: "0.75rem",
                                color: "var(--accent-primary, #3b82f6)",
                                cursor: "pointer",
                                textDecoration: "underline",
                                padding: "2px 4px",
                            }}
                        >
                            Detail
                        </span>
                    `}
                    <!-- Poll Now button (offline, degraded, or suspended entities) -->
                    ${!isOnline && onResumePolling && html`
                        <button
                            class="entity-card-action-btn"
                            onClick=${(e) => {
                                e.stopPropagation();
                                onResumePolling(entity.id);
                            }}
                            title=${isSuspended ? "Resume polling for this entity" : "Trigger immediate poll"}
                            style=${{
                                fontSize: "0.65rem",
                                padding: "2px 8px",
                                borderRadius: "4px",
                                border: "1px solid var(--color-accent, #3b82f6)",
                                background: "transparent",
                                color: "var(--color-accent, #3b82f6)",
                                cursor: "pointer",
                                lineHeight: "1.4",
                            }}
                        >
                            ${isSuspended ? "Resume" : "Poll Now"}
                        </button>
                    `}
                    <!-- Role badge -->
                    <span style=${{
                        fontSize: "0.7rem",
                        padding: "2px 8px",
                        borderRadius: "10px",
                        backgroundColor: entity.entity_type === "vehicle"
                            ? "var(--color-accent)"
                            : entity.entity_type === "dev"
                                ? "var(--color-success)"
                                : "var(--color-warning)",
                        color: "#fff",
                        fontWeight: "600",
                        textTransform: "uppercase",
                        letterSpacing: "0.5px",
                        flexShrink: "0",
                    }}>
                        ${roleBadge}
                    </span>
                </div>
            </div>

            <!-- Status line -->
            <div style=${{
                display: "flex",
                justifyContent: "space-between",
                fontSize: "0.75rem",
                color: "var(--color-text-muted)",
                marginBottom: "12px",
            }}>
                <span class=${statusClass} style=${{
                    padding: "1px 6px",
                    borderRadius: "4px",
                    fontSize: "0.7rem",
                }}>
                    ${statusLabel}
                </span>
                <span>Last seen: ${lastSeen}${absTime ? ` \u00B7 ${absTime}` : ""}</span>
            </div>

            <!-- Compact health summary: badge + layer dots + diagnostic -->
            <div class="entity-health-summary">
                <div style=${{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    flexWrap: "wrap",
                }}>
                    <span class=${`entity-health-badge ${healthBadgeClass(healthSummary.overall === 'online' ? 'healthy' : healthSummary.overall === 'degraded' ? 'degraded' : healthSummary.overall === 'unknown' ? 'unavailable' : 'error')}`}>
                        ${healthSummary.overall}
                    </span>
                    <div class="entity-health-layers">
                        ${healthSummary.layers.map((layer) => html`
                            <span
                                class=${`entity-health-layer entity-health-layer--${layer.status}`}
                                title=${layer.tooltip}
                            >
                                <span class="entity-health-layer-dot"></span>
                                <span>${layer.label}</span>
                            </span>
                        `)}
                    </div>
                </div>
                ${healthSummary.diagnostic && html`
                    <div class="entity-health-diagnostic">
                        ${healthSummary.diagnostic}
                    </div>
                `}
            </div>

            <!-- Gauges -->
            <${GaugeBar}
                label="CPU"
                value=${metrics.cpu_percent != null ? metrics.cpu_percent : null}
                unit="%"
                stale=${isOffline}
            />
            <${GaugeBar}
                label="Memory"
                value=${metrics.memory_percent != null ? metrics.memory_percent : null}
                unit="%"
                stale=${isOffline}
            />
            <${GaugeBar}
                label="Temp"
                value=${metrics.temperature_c != null ? metrics.temperature_c : null}
                unit=${"\u00B0C"}
                stale=${isOffline}
            />

            <!-- Motor + Camera temperatures (compact inline) -->
            <${CompactTemperatures}
                motorTemperatures=${metrics.motor_temperatures}
                cameraTemperatureC=${metrics.camera_temperature_c}
                entityType=${entity.entity_type}
                stale=${isOffline}
            />

            <!-- Node count -->
            <div style=${{
                display: "flex",
                justifyContent: "space-between",
                fontSize: "0.8rem",
                marginTop: "8px",
                paddingTop: "8px",
                borderTop: "1px solid var(--border-color)",
                opacity: isOffline ? "0.5" : "1",
            }}>
                <span style=${{ color: "var(--color-text-muted)" }}>ROS2 Nodes</span>
                <span style=${{ fontWeight: "600" }}>
                    ${nodeCount != null ? nodeCount : "\u2014"}
                </span>
            </div>

            <!-- IP address and hostname -->
            ${entity.ip && html`
                <div style=${{
                    fontSize: "0.7rem",
                    color: "var(--color-text-muted)",
                    marginTop: "4px",
                    textAlign: "right",
                }}>
                    ${(() => {
                        const showHost = entity.hostname && entity.hostname !== entity.name;
                        const prefix = entity.group_id && entity.slot
                            ? `${entity.group_id}/${entity.slot} · ${entity.ip}`
                            : entity.ip;
                        return showHost ? `${prefix} · ${entity.hostname}` : prefix;
                    })()}
                </div>
            `}

            <!-- First error (only shown when entity is not online) -->
            ${errorMessage && !isOnline && html`
                <div style=${{
                    marginTop: "8px",
                    padding: "6px 8px",
                    borderRadius: "var(--radius-sm, 4px)",
                    backgroundColor: "color-mix(in srgb, var(--color-error) 10%, transparent)",
                    border: "1px solid var(--color-error)",
                    fontSize: "0.72rem",
                    color: "var(--color-error)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                }}>
                    ${errorMessage}
                </div>
            `}
        </div>
    `;
}

export { EntityCard, GaugeBar, formatLastSeen, formatAbsoluteTime, roleBadgeLabel };
