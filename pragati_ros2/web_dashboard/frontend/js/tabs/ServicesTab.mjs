/**
 * ServicesTab — Preact component for browsing and filtering ROS2 services.
 *
 * Migrated from vanilla JS as part of task 6.2 of the
 * dashboard-frontend-migration.
 *
 * @module tabs/ServicesTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useContext, useMemo, useRef } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { WebSocketContext } from "../app.js";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5000;

/**
 * Service name suffixes that indicate infrastructure (parameter management,
 * type introspection) rather than application-level services.
 */
const INFRA_SUFFIXES = [
    "/describe_parameters",
    "/get_parameter_types",
    "/get_parameters",
    "/list_parameters",
    "/set_parameters",
    "/set_parameters_atomically",
    "/get_type_description",
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Classify a service as "main" or "infra".
 * @param {string} name
 * @returns {"main"|"infra"}
 */
function classifyService(name) {
    return INFRA_SUFFIXES.some((s) => name.endsWith(s)) ? "infra" : "main";
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function ServicesTab() {
    const { data: wsData } = useContext(WebSocketContext);
    const systemState = wsData ? wsData.system_state : null;
    const ros2Available = systemState ? systemState.ros2_available : null;
    const isInitializing = systemState === null || systemState === undefined;

    const [services, setServices] = useState({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchQuery, setSearchQuery] = useState("");
    const [category, setCategory] = useState("main");
    const mountedRef = useRef(true);

    // ---- data loading -----------------------------------------------------

    const loadServices = useCallback(async () => {
        const data = await safeFetch("/api/services");
        if (!mountedRef.current) return;

        if (data) {
            setServices(data);
            setError(null);
        } else {
            setError("Failed to load services");
        }
        setLoading(false);
    }, []);

    // ---- lifecycle --------------------------------------------------------

    useEffect(() => {
        mountedRef.current = true;
        loadServices();
        return () => {
            mountedRef.current = false;
        };
    }, [loadServices]);

    useEffect(() => {
        const id = setInterval(loadServices, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [loadServices]);

    // ---- derived data -----------------------------------------------------

    const filteredServices = useMemo(() => {
        const entries = Object.entries(services).sort(([a], [b]) =>
            a.localeCompare(b)
        );
        const lowerQ = searchQuery.toLowerCase();

        return entries.filter(([name]) => {
            // Category filter
            if (category !== "all") {
                const cat = classifyService(name);
                if (cat !== category) return false;
            }
            // Text search
            if (lowerQ && !name.toLowerCase().includes(lowerQ)) return false;
            return true;
        });
    }, [services, searchQuery, category]);

    // ---- render -----------------------------------------------------------

    if (isInitializing) {
        return html`
            <div class="section-header">
                <h2>ROS2 Services</h2>
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
                <h2>ROS2 Services</h2>
            </div>
            <div class="no-ros2-placeholder" style=${{
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--spacing-xl)',
                textAlign: 'center',
                color: 'var(--text-secondary)',
            }}>
                <div style=${{ fontSize: '2em', marginBottom: 'var(--spacing-sm)' }}>🔌</div>
                <div style=${{ fontSize: '1.1em', marginBottom: 'var(--spacing-xs)' }}>ROS2 daemon not connected</div>
                <div style=${{ fontSize: '0.9em', color: 'var(--text-muted)' }}>Service information requires an active ROS2 environment</div>
            </div>
        `;
    }

    return html`
        <div class="section-header">
            <h2>ROS2 Services</h2>
            <div class="section-actions">
                <select
                    class="category-filter"
                    value=${category}
                    onChange=${(e) => setCategory(e.target.value)}
                >
                    <option value="main">Main</option>
                    <option value="infra">Infrastructure</option>
                    <option value="all">All</option>
                </select>
                <input
                    type="text"
                    class="search-input"
                    placeholder="Search services..."
                    value=${searchQuery}
                    onInput=${(e) => setSearchQuery(e.target.value)}
                />
            </div>
        </div>

        <div class="services-list">
            ${loading && Object.keys(services).length === 0
                ? html`<div class="loading">Loading services...</div>`
                : error && Object.keys(services).length === 0
                  ? html`<div class="empty-state">${error}</div>`
                  : filteredServices.length === 0
                    ? html`<div class="empty-state">No services found</div>`
                    : filteredServices.map(
                          ([name, info]) => html`
                              <div
                                  key=${name}
                                  class="service-item service-clickable"
                                  data-category=${classifyService(name)}
                                  data-service=${name}
                              >
                                  <span class="service-name">${name}</span>
                                  <span class="service-type">
                                      ${info.type || "unknown"}
                                  </span>
                              </div>
                          `
                      )}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Register with the Preact app shell
// ---------------------------------------------------------------------------

registerTab("services", ServicesTab);

export { ServicesTab };
