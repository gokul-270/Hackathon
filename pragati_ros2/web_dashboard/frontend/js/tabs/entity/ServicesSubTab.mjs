/**
 * ServicesSubTab — Preact sub-tab for browsing, calling, and tracking
 * ROS2 services on a specific entity.
 *
 * Features:
 *   - Service list table with search/filter and 10s auto-refresh
 *   - Service call form with JSON editor, confirmation dialog, response display
 *   - Session-scoped call history (last 20 calls) with replay
 *
 * Props (from entity shell):
 *   { entityId, entitySource, entityIp, ros2Available, registerCleanup }
 *
 * @module tabs/entity/ServicesSubTab
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useRef,
    useCallback,
    useMemo,
} from "preact/hooks";
import { html } from "htm/preact";
import { cachedEntityFetch } from "../../utils/cachedFetch.mjs";
import {
    CategoryFilterBar,
    classifyTopicOrService,
    filterByCategory,
} from "../../utils/categoryFilter.mjs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 10000;
const MAX_HISTORY = 20;
const PAGE_SIZE = 50;

/**
 * Service names containing these substrings get a warning badge.
 */
const DANGEROUS_KEYWORDS = ["emergency", "stop"];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Check if a service name looks dangerous (emergency/stop related).
 * @param {string} name
 * @returns {boolean}
 */
function isDangerousService(name) {
    const lower = name.toLowerCase();
    return DANGEROUS_KEYWORDS.some((kw) => lower.includes(kw));
}

/**
 * Pretty-print a JSON value, returning the string or an error message.
 * @param {*} value
 * @returns {string}
 */
function formatJson(value) {
    try {
        return JSON.stringify(value, null, 2);
    } catch {
        return String(value);
    }
}

/**
 * Validate a JSON string. Returns { ok, parsed, error }.
 * @param {string} text
 * @returns {{ ok: boolean, parsed: any, error: string|null }}
 */
function parseJsonSafe(text) {
    try {
        const parsed = JSON.parse(text);
        return { ok: true, parsed, error: null };
    } catch (e) {
        return { ok: false, parsed: null, error: e.message };
    }
}

/**
 * Format a timestamp for display in the history panel.
 * @param {number} ts - Unix timestamp in ms
 * @returns {string}
 */
function formatTimestamp(ts) {
    const d = new Date(ts);
    return d.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
    });
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
    container: {
        display: "flex",
        flexDirection: "column",
        gap: "16px",
    },
    searchBar: {
        display: "flex",
        alignItems: "center",
        gap: "8px",
        marginBottom: "4px",
    },
    searchInput: {
        flex: 1,
        padding: "8px 12px",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-sm, 4px)",
        background: "var(--color-bg-secondary, #1a1f2e)",
        color: "var(--color-text-primary, #e6e8eb)",
        fontSize: "0.9em",
    },
    serviceCount: {
        fontSize: "0.85em",
        color: "var(--color-text-muted, #8494a7)",
        whiteSpace: "nowrap",
    },
    table: {
        width: "100%",
        borderCollapse: "collapse",
        fontSize: "0.9em",
    },
    th: {
        textAlign: "left",
        padding: "8px 12px",
        borderBottom: "2px solid var(--color-border, #2d3748)",
        color: "var(--color-text-secondary, #8b92a7)",
        fontSize: "0.85em",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        position: "sticky",
        top: 0,
        background: "var(--color-bg-secondary, #1a1f2e)",
        zIndex: 1,
    },
    td: {
        padding: "8px 12px",
        borderBottom: "1px solid var(--color-border, #2d3748)",
    },
    serviceName: {
        fontFamily: "monospace",
        fontSize: "0.9em",
    },
    serviceType: {
        fontFamily: "monospace",
        fontSize: "0.85em",
        color: "var(--color-text-muted, #8494a7)",
    },
    rowClickable: {
        cursor: "pointer",
        transition: "background 0.15s",
    },
    rowSelected: {
        background: "var(--color-bg-tertiary, #242b3d)",
    },
    dangerBadge: {
        display: "inline-block",
        marginLeft: "6px",
        fontSize: "0.85em",
    },
    // Call form styles
    callPanel: {
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-md, 8px)",
        padding: "16px",
        background: "var(--color-bg-secondary, #1a1f2e)",
    },
    callPanelHeader: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "12px",
    },
    callPanelTitle: {
        fontSize: "1em",
        fontWeight: "600",
        color: "var(--color-text-primary, #e6e8eb)",
    },
    callPanelType: {
        fontSize: "0.85em",
        fontFamily: "monospace",
        color: "var(--color-text-muted, #8494a7)",
    },
    closeBtn: {
        background: "none",
        border: "none",
        color: "var(--color-text-muted, #8494a7)",
        cursor: "pointer",
        fontSize: "1.2em",
        padding: "4px 8px",
    },
    label: {
        display: "block",
        fontSize: "0.85em",
        color: "var(--color-text-secondary, #8b92a7)",
        marginBottom: "4px",
        fontWeight: "500",
    },
    jsonEditor: {
        width: "100%",
        minHeight: "100px",
        padding: "10px",
        fontFamily: "monospace",
        fontSize: "0.9em",
        background: "var(--color-bg-secondary, #1a1f2e)",
        color: "var(--color-text-primary, #e6e8eb)",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "4px",
        resize: "vertical",
        lineHeight: "1.4",
        boxSizing: "border-box",
    },
    jsonEditorError: {
        borderColor: "var(--color-error, #f55353)",
    },
    parseError: {
        fontSize: "0.8em",
        color: "var(--color-error, #f55353)",
        marginTop: "4px",
    },
    callButton: {
        padding: "8px 20px",
        background: "var(--color-accent, #4b8df7)",
        color: "var(--color-bg-primary, #0f1419)",
        border: "none",
        borderRadius: "4px",
        cursor: "pointer",
        fontWeight: "600",
        fontSize: "0.9em",
        marginTop: "12px",
    },
    callButtonDisabled: {
        opacity: 0.5,
        cursor: "not-allowed",
    },
    callButtonDanger: {
        background: "var(--color-error, #f55353)",
    },
    // Response display
    responsePanel: {
        marginTop: "12px",
        padding: "10px",
        background: "var(--color-bg-secondary, #1a1f2e)",
        borderRadius: "var(--radius-sm, 4px)",
        border: "1px solid var(--color-border, #2d3748)",
        maxHeight: "300px",
        overflow: "auto",
    },
    responseHeader: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "8px",
    },
    responseLabel: {
        fontSize: "0.85em",
        color: "var(--color-text-secondary, #8b92a7)",
        fontWeight: "500",
    },
    durationBadge: {
        fontSize: "0.8em",
        padding: "2px 8px",
        borderRadius: "10px",
        background: "var(--color-bg-tertiary, #242b3d)",
        color: "var(--color-text-muted, #8494a7)",
    },
    responseBody: {
        fontFamily: "monospace",
        fontSize: "0.85em",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        color: "var(--color-success, #22c55e)",
        lineHeight: "1.4",
    },
    responseError: {
        color: "var(--color-error, #f55353)",
    },
    spinner: {
        display: "inline-block",
        width: "16px",
        height: "16px",
        border: "2px solid var(--color-text-muted, #8494a7)",
        borderTopColor: "transparent",
        borderRadius: "50%",
        animation: "spin 0.8s linear infinite",
        marginRight: "8px",
        verticalAlign: "middle",
    },
    // Confirmation modal
    modalOverlay: {
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
    },
    modalContent: {
        background: "var(--color-bg-secondary, #1a1f2e)",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-md, 8px)",
        padding: "24px",
        maxWidth: "500px",
        width: "90%",
    },
    modalTitle: {
        fontSize: "1.05em",
        fontWeight: "600",
        color: "var(--color-text-primary, #e6e8eb)",
        marginBottom: "12px",
    },
    modalBody: {
        fontSize: "0.9em",
        color: "var(--color-text-secondary, #8b92a7)",
        marginBottom: "8px",
    },
    modalPreview: {
        fontFamily: "monospace",
        fontSize: "0.85em",
        background: "var(--color-bg-secondary, #1a1f2e)",
        padding: "8px",
        borderRadius: "var(--radius-sm, 4px)",
        maxHeight: "120px",
        overflow: "auto",
        color: "var(--color-text-primary, #e6e8eb)",
        marginBottom: "16px",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
    },
    modalActions: {
        display: "flex",
        justifyContent: "flex-end",
        gap: "8px",
    },
    modalCancel: {
        padding: "8px 16px",
        background: "var(--color-bg-tertiary, #242b3d)",
        color: "var(--color-text-primary, #e6e8eb)",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "4px",
        cursor: "pointer",
        fontSize: "0.9em",
    },
    modalConfirm: {
        padding: "8px 16px",
        background: "var(--color-accent, #4b8df7)",
        color: "var(--color-bg-primary, #0f1419)",
        border: "none",
        borderRadius: "4px",
        cursor: "pointer",
        fontWeight: "600",
        fontSize: "0.9em",
    },
    modalConfirmDanger: {
        background: "var(--color-error, #f55353)",
    },
    // History panel
    historyPanel: {
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-md, 8px)",
        padding: "16px",
        background: "var(--color-bg-secondary, #1a1f2e)",
    },
    historyTitle: {
        fontSize: "0.95em",
        fontWeight: "600",
        color: "var(--color-text-primary, #e6e8eb)",
        marginBottom: "12px",
    },
    historyItem: {
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "8px 10px",
        borderRadius: "4px",
        cursor: "pointer",
        transition: "background 0.15s",
        fontSize: "0.85em",
        borderLeft: "3px solid transparent",
    },
    historyItemSuccess: {
        borderLeftColor: "var(--color-success, #22c55e)",
    },
    historyItemFailure: {
        borderLeftColor: "var(--color-error, #f55353)",
    },
    historyTime: {
        color: "var(--color-text-muted, #8494a7)",
        whiteSpace: "nowrap",
        fontSize: "0.85em",
        fontFamily: "monospace",
    },
    historyService: {
        flex: 1,
        fontFamily: "monospace",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        color: "var(--color-text-primary, #e6e8eb)",
    },
    historyDuration: {
        color: "var(--color-text-muted, #8494a7)",
        whiteSpace: "nowrap",
        fontSize: "0.8em",
    },
    emptyState: {
        textAlign: "center",
        padding: "32px 16px",
        color: "var(--color-text-muted, #8494a7)",
    },
    emptyIcon: {
        fontSize: "2em",
        marginBottom: "8px",
    },
    emptyText: {
        fontSize: "0.95em",
    },
    emptySub: {
        fontSize: "0.85em",
        marginTop: "4px",
    },
    errorBanner: {
        padding: "10px 14px",
        background: "var(--badge-error-bg, rgba(239, 68, 68, 0.2))",
        border: "1px solid var(--color-error, #f55353)",
        borderRadius: "var(--radius-sm, 4px)",
        color: "var(--color-error, #f55353)",
        fontSize: "0.9em",
    },
    loadingText: {
        textAlign: "center",
        padding: "24px",
        color: "var(--color-text-muted, #8494a7)",
        fontSize: "0.9em",
    },
    actionBtn: {
        padding: "4px 10px",
        fontSize: "0.8em",
        background: "var(--color-bg-tertiary, #242b3d)",
        color: "var(--color-text-primary, #e6e8eb)",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "3px",
        cursor: "pointer",
    },
    skeleton: {
        padding: "16px",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
    },
    skeletonRow: {
        height: "18px",
        borderRadius: "var(--radius-sm, 4px)",
        background:
            "linear-gradient(90deg, var(--color-bg-tertiary, #242b3d) 25%, var(--color-bg-elevated, #334155) 50%, var(--color-bg-tertiary, #242b3d) 75%)",
        backgroundSize: "200% 100%",
        animation: "shimmer 1.5s infinite",
    },
    staleBadge: {
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "var(--radius-sm, 4px)",
        fontSize: "0.75rem",
        fontWeight: "600",
        color: "var(--color-warning, #f59e0b)",
        backgroundColor: "var(--badge-warning-bg, rgba(245, 158, 11, 0.2))",
        marginLeft: "8px",
    },
    retryBtn: {
        padding: "6px 16px",
        borderRadius: "var(--radius-sm, 4px)",
        border: "1px solid var(--color-border, #2d3748)",
        background: "var(--color-bg-secondary, #1a1f2e)",
        color: "var(--color-text-primary, #e6e8eb)",
        cursor: "pointer",
        fontSize: "0.85rem",
    },
    paginationBar: {
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        gap: "12px",
        padding: "8px 0",
        fontSize: "0.85rem",
        color: "var(--color-text-muted, #8494a7)",
    },
    pageBtn: {
        padding: "4px 12px",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-sm, 4px)",
        backgroundColor: "var(--color-bg-secondary, #1a1f2e)",
        color: "var(--color-text-primary, #e6e8eb)",
        cursor: "pointer",
        fontSize: "0.85rem",
    },
    pageBtnDisabled: {
        padding: "4px 12px",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-sm, 4px)",
        backgroundColor: "var(--color-bg-tertiary, #242b3d)",
        color: "var(--color-text-muted, #8494a7)",
        cursor: "not-allowed",
        fontSize: "0.85rem",
    },
};

// ---------------------------------------------------------------------------
// CSS keyframes injection (once)
// ---------------------------------------------------------------------------

let keyframesInjected = false;

function injectKeyframes() {
    if (keyframesInjected) return;
    keyframesInjected = true;
    const style = document.createElement("style");
    style.textContent = `
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        @keyframes shimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
    `;
    document.head.appendChild(style);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ServicesSubTab({
    entityId,
    entitySource,
    entityIp,
    ros2Available,
    registerCleanup,
}) {
    // ---- State ------------------------------------------------------------
    const [services, setServices] = useState([]);
    const [searchFilter, setSearchFilter] = useState("");
    const [categoryFilter, setCategoryFilter] = useState("all");
    const [selectedService, setSelectedService] = useState(null);
    const [requestJson, setRequestJson] = useState("{}");
    const [response, setResponse] = useState(null);
    const [calling, setCalling] = useState(false);
    const [callHistory, setCallHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showConfirm, setShowConfirm] = useState(false);
    const [stale, setStale] = useState(false);
    const [currentPage, setCurrentPage] = useState(1);

    const mountedRef = useRef(true);
    const intervalRef = useRef(null);
    const abortControllerRef = useRef(null);

    // Inject spinner keyframes on first render
    useEffect(() => {
        injectKeyframes();
    }, []);

    // ---- Data loading -----------------------------------------------------

    const loadServices = useCallback(async (bypass = false) => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        abortControllerRef.current = new AbortController();

        if (bypass) {
            setLoading(true);
            setError(null);
            setStale(false);
        }

        const result = await cachedEntityFetch(entityId, "ros2/services", {
            signal: abortControllerRef.current.signal,
            bypassCache: bypass,
        });

        if (!mountedRef.current) return;

        if (result) {
            const data = result.data?.services || (Array.isArray(result.data) ? result.data : []);
            setServices(data);
            setStale(result.stale);
            setError(null);
            setCurrentPage(1);
        } else {
            if (services.length === 0) {
                setError("Failed to load services");
            }
        }
        setLoading(false);
    }, [entityId, services.length]);

    // ---- Lifecycle --------------------------------------------------------

    useEffect(() => {
        mountedRef.current = true;
        abortControllerRef.current = new AbortController();
        loadServices();

        intervalRef.current = setInterval(
            () => loadServices(false),
            POLL_INTERVAL_MS,
        );

        return () => {
            mountedRef.current = false;
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
                intervalRef.current = null;
            }
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, [loadServices]);

    // Register cleanup with parent shell
    useEffect(() => {
        if (typeof registerCleanup === "function") {
            registerCleanup(() => {
                mountedRef.current = false;
                if (intervalRef.current) {
                    clearInterval(intervalRef.current);
                    intervalRef.current = null;
                }
                if (abortControllerRef.current) {
                    abortControllerRef.current.abort();
                }
            });
        }
    }, [registerCleanup]);

    // ---- Derived data -----------------------------------------------------

    const filteredServices = useMemo(() => {
        const byCategory = filterByCategory(services, categoryFilter, classifyTopicOrService);
        if (!searchFilter) return byCategory;
        const lower = searchFilter.toLowerCase();
        return byCategory.filter(
            (svc) =>
                svc.name.toLowerCase().includes(lower) ||
                (svc.type && svc.type.toLowerCase().includes(lower))
        );
    }, [services, searchFilter, categoryFilter]);

    const categoryCounts = useMemo(() => {
        return {
            all: services.length,
            pragati: services.filter((s) => classifyTopicOrService(s.name) === "pragati").length,
            dashboard: services.filter((s) => classifyTopicOrService(s.name) === "dashboard").length,
            system: services.filter((s) => classifyTopicOrService(s.name) === "system").length,
        };
    }, [services]);

    // ---- Pagination -------------------------------------------------------

    const totalPages = Math.max(
        1,
        Math.ceil(filteredServices.length / PAGE_SIZE),
    );
    const safePage = Math.min(currentPage, totalPages);
    const paginatedServices = useMemo(() => {
        const start = (safePage - 1) * PAGE_SIZE;
        return filteredServices.slice(start, start + PAGE_SIZE);
    }, [filteredServices, safePage]);

    // ---- Handlers ---------------------------------------------------------

    const handleSelectService = useCallback(
        (svc) => {
            if (
                selectedService &&
                selectedService.name === svc.name
            ) {
                // Deselect
                setSelectedService(null);
                setRequestJson("{}");
                setResponse(null);
            } else {
                setSelectedService(svc);
                setRequestJson("{}");
                setResponse(null);
            }
        },
        [selectedService]
    );

    const handleCallClick = useCallback(() => {
        // Validate JSON before showing confirmation
        const result = parseJsonSafe(requestJson);
        if (!result.ok) return; // Button should be disabled, but guard anyway
        setShowConfirm(true);
    }, [requestJson]);

    const handleConfirmCall = useCallback(async () => {
        if (!selectedService) return;
        setShowConfirm(false);
        setCalling(true);
        setResponse(null);

        const startTime = Date.now();
        const parsed = parseJsonSafe(requestJson);
        const requestBody = parsed.ok ? parsed.parsed : {};

        const url = `/api/entities/${encodeURIComponent(entityId)}/ros2/services/${encodeURIComponent(selectedService.name)}/call`;

        let result = null;
        let success = false;
        let errorMsg = null;

        try {
            const resp = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    service_type: selectedService.type || "",
                    request: requestBody,
                }),
            });

            const duration = Date.now() - startTime;

            if (resp.ok) {
                const body = await resp.json();
                result = { data: body, duration_ms: duration, status: resp.status };
                success = true;
            } else {
                let errBody = null;
                try {
                    errBody = await resp.json();
                } catch {
                    errBody = { detail: `HTTP ${resp.status}` };
                }
                const statusLabels = {
                    400: "Bad Request",
                    408: "Timeout",
                    503: "Service Unavailable",
                };
                const label =
                    statusLabels[resp.status] || `Error ${resp.status}`;
                errorMsg = `${label}: ${errBody.detail || errBody.message || JSON.stringify(errBody)}`;
                result = {
                    error: errorMsg,
                    duration_ms: duration,
                    status: resp.status,
                };
            }
        } catch (e) {
            const duration = Date.now() - startTime;
            errorMsg = `Network error: ${e.message}`;
            result = { error: errorMsg, duration_ms: duration, status: null };
        }

        if (!mountedRef.current) return;

        setResponse(result);
        setCalling(false);

        // Add to history
        const historyEntry = {
            timestamp: Date.now(),
            service: selectedService.name,
            serviceType: selectedService.type || "",
            request: requestBody,
            response: result,
            duration_ms: result.duration_ms,
            success,
        };

        setCallHistory((prev) => {
            const next = [historyEntry, ...prev];
            return next.slice(0, MAX_HISTORY);
        });
    }, [selectedService, requestJson, entityId]);

    const handleCancelConfirm = useCallback(() => {
        setShowConfirm(false);
    }, []);

    const handleReplayHistory = useCallback(
        (entry) => {
            // Find the service in current list, or create a stub
            const svc = services.find((s) => s.name === entry.service) || {
                name: entry.service,
                type: entry.serviceType,
            };
            setSelectedService(svc);
            setRequestJson(formatJson(entry.request));
            setResponse(null);
        },
        [services]
    );

    // ---- JSON validation for the editor -----------------------------------

    const jsonValidation = useMemo(
        () => parseJsonSafe(requestJson),
        [requestJson]
    );

    // ---- Render -----------------------------------------------------------

    // ROS2 not available guard
    if (ros2Available === false) {
        return html`
            <div style=${styles.emptyState}>
                <div style=${styles.emptyIcon}>🔌</div>
                <div style=${styles.emptyText}>ROS2 not available</div>
                <div style=${styles.emptySub}>
                    Service information requires an active ROS2 environment
                </div>
            </div>
        `;
    }

    return html`
        <div style=${styles.container}>
            ${renderServiceList()}
            ${selectedService && renderCallForm()}
            ${callHistory.length > 0 && renderHistory()}
            ${showConfirm && renderConfirmModal()}
        </div>
    `;

    // ---- Sub-renders (hoisted function declarations) ----------------------

    function renderServiceList() {
        return html`
            <div>
                <${CategoryFilterBar}
                    active=${categoryFilter}
                    onChange=${(v) => { setCategoryFilter(v); setCurrentPage(1); }}
                    counts=${categoryCounts}
                />
                <div style=${styles.searchBar}>
                    <input
                        type="text"
                        placeholder="Filter services..."
                        value=${searchFilter}
                        onInput=${(e) => setSearchFilter(e.target.value)}
                        style=${styles.searchInput}
                    />
                    <span style=${styles.serviceCount}>
                        ${filteredServices.length} / ${services.length}
                        ${stale
                            ? html`<span style=${styles.staleBadge}
                                  >Stale</span
                              >`
                            : null}
                    </span>
                </div>

                ${loading && services.length === 0
                    ? html`<div style=${styles.skeleton}>
                          ${Array.from(
                              { length: 8 },
                              (_, i) => html`
                                  <div
                                      key=${i}
                                      style=${{
                                          ...styles.skeletonRow,
                                          width: `${60 + Math.random() * 35}%`,
                                      }}
                                  />
                              `,
                          )}
                      </div>`
                    : error && services.length === 0
                      ? html`<div style=${styles.emptyState}>
                            <div
                                style=${{
                                    color: "var(--color-error, #f55353)",
                                    marginBottom: "8px",
                                }}
                            >
                                ${error}
                            </div>
                            <button
                                onClick=${() => loadServices(true)}
                                style=${styles.retryBtn}
                            >
                                Retry
                            </button>
                        </div>`
                      : filteredServices.length === 0
                        ? html`
                              <div style=${styles.emptyState}>
                                  <div style=${styles.emptyIcon}>
                                      \u{1F4CB}
                                  </div>
                                  <div style=${styles.emptyText}>
                                      ${services.length === 0
                                          ? "No services found"
                                          : "No services match filter"}
                                  </div>
                                  <div style=${styles.emptySub}>
                                      ${services.length === 0
                                          ? "No ROS2 services are available on this entity"
                                          : `Try a different search term`}
                                  </div>
                              </div>
                          `
                        : html`
                              <div
                                  style=${{
                                      overflowX: "auto",
                                      overflowY: "auto",
                                      maxHeight: "60vh",
                                      borderRadius: "var(--radius-md, 8px)",
                                      border: "1px solid var(--color-border, #2d3748)",
                                  }}
                              >
                              <table style=${styles.table}>
                                  <thead>
                                      <tr>
                                          <th style=${styles.th}>Name</th>
                                          <th style=${styles.th}>Type</th>
                                          <th style=${styles.th}>Actions</th>
                                      </tr>
                                  </thead>
                                  <tbody>
                                      ${paginatedServices.map(
                                          (svc) => html`
                                              <tr
                                                  key=${svc.name}
                                                  style=${{
                                                      ...styles.rowClickable,
                                                      ...(selectedService &&
                                                      selectedService.name ===
                                                          svc.name
                                                          ? styles.rowSelected
                                                          : {}),
                                                  }}
                                                  onClick=${() =>
                                                      handleSelectService(svc)}
                                              >
                                                  <td style=${styles.td}>
                                                      <span
                                                          style=${styles.serviceName}
                                                          >${svc.name}</span
                                                      >
                                                      ${isDangerousService(
                                                          svc.name,
                                                      )
                                                          ? html`<span
                                                                style=${styles.dangerBadge}
                                                                title="Potentially dangerous service"
                                                                >\u26A0\uFE0F</span
                                                            >`
                                                          : null}
                                                  </td>
                                                  <td style=${styles.td}>
                                                      <span
                                                          style=${styles.serviceType}
                                                          >${svc.type ||
                                                          "unknown"}</span
                                                      >
                                                  </td>
                                                  <td style=${styles.td}>
                                                      <button
                                                          style=${styles.actionBtn}
                                                          onClick=${(e) => {
                                                              e.stopPropagation();
                                                              handleSelectService(
                                                                  svc,
                                                              );
                                                          }}
                                                      >
                                                          ${selectedService &&
                                                          selectedService.name ===
                                                              svc.name
                                                              ? "Deselect"
                                                              : "Call"}
                                                      </button>
                                                  </td>
                                              </tr>
                                          `,
                                      )}
                                  </tbody>
                              </table>
                              </div>

                              ${filteredServices.length > PAGE_SIZE
                                  ? html`
                                        <div style=${styles.paginationBar}>
                                            <button
                                                style=${safePage <= 1
                                                    ? styles.pageBtnDisabled
                                                    : styles.pageBtn}
                                                disabled=${safePage <= 1}
                                                onClick=${() =>
                                                    setCurrentPage((p) =>
                                                        Math.max(1, p - 1),
                                                    )}
                                            >
                                                Prev
                                            </button>
                                            <span>
                                                Page ${safePage} of
                                                ${totalPages}
                                            </span>
                                            <button
                                                style=${safePage >= totalPages
                                                    ? styles.pageBtnDisabled
                                                    : styles.pageBtn}
                                                disabled=${safePage >=
                                                totalPages}
                                                onClick=${() =>
                                                    setCurrentPage((p) =>
                                                        Math.min(
                                                            totalPages,
                                                            p + 1,
                                                        ),
                                                    )}
                                            >
                                                Next
                                            </button>
                                        </div>
                                    `
                                  : null}

                              <div
                                  style=${{
                                      fontSize: "0.8rem",
                                      color: "var(--color-text-muted, #8494a7)",
                                      textAlign: "right",
                                      marginTop: "4px",
                                  }}
                              >
                                  ${filteredServices.length}
                                  service${filteredServices.length !== 1
                                      ? "s"
                                      : ""}
                                  ${searchFilter
                                      ? ` (filtered from ${services.length})`
                                      : ""}
                                  ${stale
                                      ? html`<span style=${styles.staleBadge}
                                            >Stale</span
                                        >`
                                      : null}
                                  ${stale || (error && services.length > 0)
                                      ? html`
                                            <button
                                                onClick=${() =>
                                                    loadServices(true)}
                                                style=${{
                                                    ...styles.retryBtn,
                                                    marginLeft: "8px",
                                                }}
                                            >
                                                Retry
                                            </button>
                                        `
                                      : null}
                              </div>
                          `}
            </div>
        `;
    }

    function renderCallForm() {
        const dangerous = isDangerousService(selectedService.name);

        return html`
            <div style=${styles.callPanel}>
                <div style=${styles.callPanelHeader}>
                    <div>
                        <div style=${styles.callPanelTitle}>
                            ${selectedService.name}
                            ${dangerous
                                ? html`<span
                                      style=${styles.dangerBadge}
                                      title="Potentially dangerous service"
                                      >⚠️</span
                                  >`
                                : null}
                        </div>
                        <div style=${styles.callPanelType}>
                            ${selectedService.type || "unknown type"}
                        </div>
                    </div>
                    <button
                        style=${styles.closeBtn}
                        onClick=${() => {
                            setSelectedService(null);
                            setRequestJson("{}");
                            setResponse(null);
                        }}
                        title="Close call form"
                    >
                        ✕
                    </button>
                </div>

                <label style=${styles.label}>Request JSON</label>
                <textarea
                    style=${{
                        ...styles.jsonEditor,
                        ...(!jsonValidation.ok
                            ? styles.jsonEditorError
                            : {}),
                    }}
                    value=${requestJson}
                    onInput=${(e) => setRequestJson(e.target.value)}
                    disabled=${calling}
                    spellcheck=${false}
                />
                ${!jsonValidation.ok
                    ? html`<div style=${styles.parseError}>
                          Invalid JSON: ${jsonValidation.error}
                      </div>`
                    : null}

                <button
                    style=${{
                        ...styles.callButton,
                        ...(calling || !jsonValidation.ok
                            ? styles.callButtonDisabled
                            : {}),
                        ...(dangerous ? styles.callButtonDanger : {}),
                    }}
                    onClick=${handleCallClick}
                    disabled=${calling || !jsonValidation.ok}
                >
                    ${calling
                        ? html`<span style=${styles.spinner}></span>Calling...`
                        : dangerous
                          ? "⚠️ Call Service"
                          : "Call Service"}
                </button>

                ${response && renderResponse()}
            </div>
        `;
    }

    function renderResponse() {
        const isError = !!response.error;
        return html`
            <div style=${styles.responsePanel}>
                <div style=${styles.responseHeader}>
                    <span style=${styles.responseLabel}>
                        ${isError ? "Error" : "Response"}
                    </span>
                    <span style=${styles.durationBadge}>
                        ${response.duration_ms}ms
                    </span>
                </div>
                <pre
                    style=${{
                        ...styles.responseBody,
                        ...(isError ? styles.responseError : {}),
                        margin: 0,
                    }}
                >${isError ? response.error : formatJson(response.data)}</pre>
            </div>
        `;
    }

    function renderHistory() {
        return html`
            <div style=${styles.historyPanel}>
                <div style=${styles.historyTitle}>
                    Call History (${callHistory.length})
                </div>
                ${callHistory.map(
                    (entry, i) => html`
                        <div
                            key=${`${entry.timestamp}-${i}`}
                            style=${{
                                ...styles.historyItem,
                                ...(entry.success
                                    ? styles.historyItemSuccess
                                    : styles.historyItemFailure),
                            }}
                            onClick=${() => handleReplayHistory(entry)}
                            title="Click to replay this request"
                        >
                            <span style=${styles.historyTime}>
                                ${formatTimestamp(entry.timestamp)}
                            </span>
                            <span style=${styles.historyService}>
                                ${entry.service}
                            </span>
                            <span style=${styles.historyDuration}>
                                ${entry.duration_ms}ms
                            </span>
                        </div>
                    `
                )}
            </div>
        `;
    }

    function renderConfirmModal() {
        const dangerous = isDangerousService(selectedService.name);
        return html`
            <div
                style=${styles.modalOverlay}
                onClick=${handleCancelConfirm}
            >
                <div
                    style=${styles.modalContent}
                    onClick=${(e) => e.stopPropagation()}
                >
                    <div style=${styles.modalTitle}>
                        ${dangerous ? "⚠️ " : ""}Confirm Service Call
                    </div>
                    <div style=${styles.modalBody}>
                        Call${" "}
                        <strong>${selectedService.name}</strong>${" "}
                        with this request?
                    </div>
                    <div style=${styles.modalPreview}>
                        ${requestJson}
                    </div>
                    <div style=${styles.modalActions}>
                        <button
                            style=${styles.modalCancel}
                            onClick=${handleCancelConfirm}
                        >
                            Cancel
                        </button>
                        <button
                            style=${{
                                ...styles.modalConfirm,
                                ...(dangerous
                                    ? styles.modalConfirmDanger
                                    : {}),
                            }}
                            onClick=${handleConfirmCall}
                        >
                            ${dangerous ? "⚠️ Call" : "Call"}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}
