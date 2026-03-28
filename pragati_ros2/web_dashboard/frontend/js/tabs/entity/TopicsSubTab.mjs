/**
 * TopicsSubTab — Entity-scoped ROS2 topics browser with echo panel.
 *
 * Features:
 * - Fetch topics from /api/entities/{id}/ros2/topics
 * - Searchable/filterable topic table (Name, Type, Pubs, Subs)
 * - 10-second auto-refresh
 * - Click-to-echo panel using StreamConnection (SSE)
 * - Last 100 messages, newest first, formatted JSON
 * - Connection status indicator
 *
 * @module tabs/entity/TopicsSubTab
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
import { safeFetch } from "../../utils.js";
import { cachedEntityFetch } from "../../utils/cachedFetch.mjs";
import {
    CategoryFilterBar,
    classifyTopicOrService,
    filterByCategory,
} from "../../utils/categoryFilter.mjs";
import { createTopicStream } from "./StreamConnection.mjs";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 10000;
const MAX_ECHO_MESSAGES = 100;
const PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
    container: {
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-md, 12px)",
    },
    publishPanel: {
        background: "var(--color-bg-secondary, #1a1f2e)",
        borderRadius: "var(--radius-md, 8px)",
        border: "1px solid var(--color-border, #2d3748)",
        overflow: "hidden",
    },
    publishHeader: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 12px",
        background: "var(--color-bg-tertiary, #242b3d)",
        borderBottom: "1px solid var(--color-border, #2d3748)",
        cursor: "pointer",
        userSelect: "none",
    },
    publishTitle: {
        fontSize: "0.85rem",
        fontWeight: 600,
        color: "var(--color-text-primary, #e6e8eb)",
    },
    publishBody: {
        padding: "12px",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
    },
    publishSelect: {
        width: "100%",
        padding: "8px 10px",
        borderRadius: "var(--radius-sm, 4px)",
        border: "1px solid var(--color-border, #2d3748)",
        background: "var(--color-bg-tertiary, #242b3d)",
        color: "var(--color-text-primary, #e6e8eb)",
        fontSize: "0.9rem",
        outline: "none",
        cursor: "pointer",
    },
    publishTextarea: {
        width: "100%",
        minHeight: "100px",
        padding: "8px 10px",
        borderRadius: "var(--radius-sm, 4px)",
        border: "1px solid var(--color-border, #2d3748)",
        background: "var(--color-bg-tertiary, #242b3d)",
        color: "var(--color-success, #22c55e)",
        fontFamily: "monospace",
        fontSize: "0.85rem",
        outline: "none",
        resize: "vertical",
        boxSizing: "border-box",
    },
    publishBtn: {
        alignSelf: "flex-start",
        padding: "6px 18px",
        borderRadius: "var(--radius-sm, 4px)",
        border: "none",
        background: "var(--color-accent, #4b8df7)",
        color: "#fff",
        cursor: "pointer",
        fontSize: "0.85rem",
        fontWeight: 600,
    },
    publishBtnDisabled: {
        alignSelf: "flex-start",
        padding: "6px 18px",
        borderRadius: "var(--radius-sm, 4px)",
        border: "none",
        background: "var(--color-bg-elevated, #334155)",
        color: "var(--color-text-muted, #8494a7)",
        cursor: "not-allowed",
        fontSize: "0.85rem",
        fontWeight: 600,
    },
    publishFeedbackSuccess: {
        padding: "6px 12px",
        borderRadius: "var(--radius-sm, 4px)",
        background: "rgba(34, 197, 94, 0.15)",
        color: "var(--color-success, #22c55e)",
        fontSize: "0.85rem",
        fontWeight: 500,
    },
    publishFeedbackError: {
        padding: "6px 12px",
        borderRadius: "var(--radius-sm, 4px)",
        background: "rgba(245, 83, 83, 0.15)",
        color: "var(--color-error, #f55353)",
        fontSize: "0.85rem",
        fontWeight: 500,
    },
    publishEmptyMsg: {
        fontSize: "0.85rem",
        color: "var(--color-text-muted, #8494a7)",
        fontStyle: "italic",
    },
    searchInput: {
        width: "100%",
        padding: "8px 12px",
        borderRadius: "var(--radius-sm, 4px)",
        border: "1px solid var(--color-border, #2d3748)",
        background: "var(--color-bg-secondary, #1a1f2e)",
        color: "var(--color-text-primary, #e6e8eb)",
        fontSize: "0.9rem",
        outline: "none",
        boxSizing: "border-box",
    },
    table: {
        width: "100%",
        borderCollapse: "collapse",
        fontSize: "0.85rem",
    },
    th: {
        textAlign: "left",
        padding: "8px 12px",
        borderBottom: "2px solid var(--color-border, #2d3748)",
        color: "var(--color-text-secondary, #8b92a7)",
        fontWeight: 600,
        fontSize: "0.8rem",
        textTransform: "uppercase",
        letterSpacing: "0.5px",
        position: "sticky",
        top: 0,
        background: "var(--color-bg-secondary, #1a1f2e)",
        zIndex: 1,
    },
    td: {
        padding: "8px 12px",
        borderBottom: "1px solid var(--color-border, #2d3748)",
        color: "var(--color-text-primary, #e6e8eb)",
    },
    topicName: {
        fontFamily: "monospace",
        fontSize: "0.85rem",
        cursor: "pointer",
        color: "var(--color-accent, #4b8df7)",
    },
    topicType: {
        fontFamily: "monospace",
        fontSize: "0.8rem",
        color: "var(--color-text-muted, #8494a7)",
    },
    countBadge: {
        display: "inline-block",
        minWidth: "24px",
        textAlign: "center",
        padding: "2px 6px",
        borderRadius: "4px",
        fontSize: "0.8rem",
        fontWeight: 600,
    },
    echoPanel: {
        background: "var(--color-bg-secondary, #1a1f2e)",
        borderRadius: "var(--radius-md, 8px)",
        border: "1px solid var(--color-border, #2d3748)",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
    },
    echoHeader: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 12px",
        borderBottom: "1px solid var(--color-border, #2d3748)",
        background: "var(--color-bg-tertiary, #242b3d)",
    },
    echoTitle: {
        fontFamily: "monospace",
        fontSize: "0.85rem",
        color: "var(--color-success, #22c55e)",
        fontWeight: 600,
    },
    echoControls: {
        display: "flex",
        alignItems: "center",
        gap: "8px",
    },
    echoBadge: {
        padding: "2px 8px",
        borderRadius: "4px",
        fontSize: "0.75rem",
        fontWeight: 500,
    },
    stopBtn: {
        padding: "4px 12px",
        borderRadius: "var(--radius-sm, 4px)",
        border: "1px solid var(--color-error, #f55353)",
        background: "var(--badge-error-bg, rgba(239, 68, 68, 0.2))",
        color: "var(--color-error, #f55353)",
        cursor: "pointer",
        fontSize: "0.8rem",
        fontWeight: 500,
    },
    echoBody: {
        maxHeight: "400px",
        overflowY: "auto",
        padding: "8px",
        fontFamily: "monospace",
        fontSize: "0.8rem",
    },
    echoMsg: {
        padding: "4px 8px",
        borderBottom: "1px solid var(--color-border, #2d3748)",
        whiteSpace: "pre-wrap",
        wordBreak: "break-all",
    },
    echoTimestamp: {
        color: "var(--color-text-muted, #8494a7)",
        fontSize: "0.75rem",
        marginRight: "8px",
    },
    echoData: {
        color: "var(--color-success, #22c55e)",
    },
    emptyState: {
        textAlign: "center",
        padding: "var(--spacing-xl, 32px)",
        color: "var(--color-text-muted, #8494a7)",
    },
    loading: {
        textAlign: "center",
        padding: "var(--spacing-xl, 32px)",
        color: "var(--color-text-muted, #8494a7)",
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
        background: "linear-gradient(90deg, var(--color-bg-tertiary, #242b3d) 25%, var(--color-bg-elevated, #334155) 50%, var(--color-bg-tertiary, #242b3d) 75%)",
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
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a timestamp for the echo panel.
 * @param {number|string|undefined} ts
 * @returns {string}
 */
function formatTimestamp(ts) {
    if (!ts) {
        return new Date().toLocaleTimeString("en-US", { hour12: false });
    }
    const d = ts instanceof Date ? ts : new Date(ts);
    return d.toLocaleTimeString("en-US", { hour12: false });
}

/**
 * Attempt pretty-print of JSON data, fall back to toString.
 * @param {any} data
 * @returns {string}
 */
function formatEchoData(data) {
    if (data == null) return "null";
    if (typeof data === "string") return data;
    try {
        return JSON.stringify(data, null, 2);
    } catch {
        return String(data);
    }
}

/**
 * Row background color for alternating rows.
 * @param {number} index
 * @param {boolean} isSelected
 * @returns {string}
 */
function rowBg(index, isSelected) {
    if (isSelected) return "rgba(75, 141, 247, 0.15)";
    return index % 2 === 0 ? "transparent" : "rgba(255, 255, 255, 0.02)";
}

/**
 * Connection status label + color.
 * @param {"connecting"|"connected"|"error"|"closed"|null} status
 * @returns {{label: string, color: string}}
 */
function statusInfo(status) {
    switch (status) {
        case "connecting":
            return { label: "Connecting...", color: "var(--color-warning, #f59e0b)" };
        case "connected":
            return { label: "Connected", color: "var(--color-success, #22c55e)" };
        case "error":
            return { label: "Error", color: "var(--color-error, #f55353)" };
        case "closed":
            return { label: "Closed", color: "var(--color-text-muted, #8494a7)" };
        default:
            return { label: "Idle", color: "var(--color-text-muted, #8494a7)" };
    }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TopicsSubTab({
    entityId,
    entitySource,
    entityIp,
    ros2Available,
    registerCleanup,
}) {
    const [topics, setTopics] = useState([]);
    const [searchFilter, setSearchFilter] = useState("");
    const [categoryFilter, setCategoryFilter] = useState("all");
    const [selectedTopic, setSelectedTopic] = useState(null);
    const [echoMessages, setEchoMessages] = useState([]);
    const [streamRef, setStreamRef] = useState(null);
    const [connectionStatus, setConnectionStatus] = useState(null);
    const [reconnectStatus, setReconnectStatus] = useState(null); // {attempt, delayMs} or null
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [stale, setStale] = useState(false);
    const [currentPage, setCurrentPage] = useState(1);

    // Publish panel state
    const [publishTopics, setPublishTopics] = useState([]);
    const [selectedPublishTopic, setSelectedPublishTopic] = useState(null);
    const [publishData, setPublishData] = useState("{}");
    const [publishFeedback, setPublishFeedback] = useState(null);
    const [isPublishing, setIsPublishing] = useState(false);
    const [publishPanelOpen, setPublishPanelOpen] = useState(false);

    const mountedRef = useRef(true);
    const refreshTimerRef = useRef(null);
    const echoBodyRef = useRef(null);
    const abortControllerRef = useRef(null);

    // ---- Fetch topic list --------------------------------------------------

    const fetchTopics = useCallback(async (bypass = false) => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        abortControllerRef.current = new AbortController();

        if (bypass) {
            setLoading(true);
            setError(null);
            setStale(false);
        }

        const result = await cachedEntityFetch(entityId, "ros2/topics", {
            signal: abortControllerRef.current.signal,
            bypassCache: bypass,
        });

        if (!mountedRef.current) return;

        if (result) {
            const data = result.data?.topics || (Array.isArray(result.data) ? result.data : []);
            setTopics(data);
            setStale(result.stale);
            setError(null);
            setCurrentPage(1);
        } else {
            if (topics.length === 0) {
                setError("Failed to load topics");
            }
        }
        setLoading(false);
    }, [entityId, topics.length]);

    // ---- Lifecycle: mount, refresh, cleanup --------------------------------

    useEffect(() => {
        mountedRef.current = true;
        abortControllerRef.current = new AbortController();
        fetchTopics();

        refreshTimerRef.current = setInterval(() => fetchTopics(false), REFRESH_INTERVAL_MS);

        return () => {
            mountedRef.current = false;
            if (refreshTimerRef.current) {
                clearInterval(refreshTimerRef.current);
                refreshTimerRef.current = null;
            }
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, [fetchTopics]);

    // ---- Register cleanup with shell ---------------------------------------

    useEffect(() => {
        if (typeof registerCleanup === "function") {
            registerCleanup(() => {
                if (streamRef) {
                    streamRef.close();
                }
                if (refreshTimerRef.current) {
                    clearInterval(refreshTimerRef.current);
                    refreshTimerRef.current = null;
                }
                if (abortControllerRef.current) {
                    abortControllerRef.current.abort();
                }
            });
        }
    }, [streamRef, registerCleanup]);

    // ---- Close stream on unmount -------------------------------------------

    useEffect(() => {
        return () => {
            if (streamRef) {
                streamRef.close();
            }
        };
    }, [streamRef]);

    // ---- Start echo stream -------------------------------------------------

    const startEcho = useCallback(
        (topic) => {
            // Close existing stream
            if (streamRef) {
                streamRef.close();
            }

            setSelectedTopic(topic);
            setEchoMessages([]);
            setConnectionStatus("connecting");
            setReconnectStatus(null);

            const stream = createTopicStream(entityId, topic.name, {
                entitySource: entitySource || "local",
                hz: 10,
                onReconnecting: (attempt, delayMs) => {
                    if (!mountedRef.current) return;
                    setReconnectStatus({ attempt, delayMs });
                    setConnectionStatus("reconnecting");
                },
                onDisconnected: () => {
                    if (!mountedRef.current) return;
                    setReconnectStatus(null);
                    setConnectionStatus("error");
                },
            });

            stream.onMessage((data) => {
                if (!mountedRef.current) return;
                setConnectionStatus("connected");
                setReconnectStatus(null);
                setEchoMessages((prev) => {
                    const msg = {
                        id: Date.now() + Math.random(),
                        timestamp: new Date(),
                        data: data,
                    };
                    const next = [msg, ...prev];
                    if (next.length > MAX_ECHO_MESSAGES) {
                        next.length = MAX_ECHO_MESSAGES;
                    }
                    return next;
                });
            });

            stream.connect();
            setStreamRef(stream);
        },
        [entityId, entitySource, streamRef],
    );

    // ---- Stop echo stream --------------------------------------------------

    const stopEcho = useCallback(() => {
        if (streamRef) {
            streamRef.close();
            setStreamRef(null);
        }
        setConnectionStatus("closed");
        setReconnectStatus(null);
    }, [streamRef]);

    // ---- Fetch publishable topics config -----------------------------------

    useEffect(() => {
        fetch("/api/config/publishable-topics")
            .then((r) => r.json())
            .then((list) => { if (mountedRef.current) setPublishTopics(list); })
            .catch(() => { if (mountedRef.current) setPublishTopics([]); });
    }, []);

    // ---- Publish panel handlers --------------------------------------------

    const handleTopicSelect = useCallback((topicName) => {
        const topic = publishTopics.find((t) => t.name === topicName) || null;
        setSelectedPublishTopic(topic);
        setPublishData(topic ? JSON.stringify(topic.default_data ?? {}, null, 2) : "{}");
        setPublishFeedback(null);
    }, [publishTopics]);

    const handlePublish = useCallback(async () => {
        if (!selectedPublishTopic) return;
        setIsPublishing(true);
        setPublishFeedback(null);
        try {
            const data = JSON.parse(publishData);
            const encoded = encodeURIComponent(selectedPublishTopic.name);
            const resp = await fetch(
                `/api/entities/${entityId}/ros2/topics/${encoded}/publish`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        message_type: selectedPublishTopic.message_type,
                        data,
                    }),
                },
            );
            if (resp.ok) {
                setPublishFeedback({ type: "success", message: "Published successfully" });
            } else {
                let msg = `Error ${resp.status}`;
                try {
                    const body = await resp.json();
                    msg = body.error || body.detail || msg;
                } catch { /* ignore */ }
                setPublishFeedback({ type: "error", message: msg });
            }
        } catch (e) {
            setPublishFeedback({ type: "error", message: e.message });
        } finally {
            setIsPublishing(false);
        }
    }, [entityId, selectedPublishTopic, publishData]);

    // ---- Filtered + sorted topic list --------------------------------------

    const filteredTopics = useMemo(() => {
        if (!topics || topics.length === 0) return [];
        const byCategory = filterByCategory(topics, categoryFilter, classifyTopicOrService);
        const q = searchFilter.toLowerCase().trim();
        const filtered = q
            ? byCategory.filter(
                  (t) =>
                      (t.name || "").toLowerCase().includes(q) ||
                      (t.type || "").toLowerCase().includes(q),
              )
            : byCategory;

        return [...filtered].sort((a, b) =>
            (a.name || "").localeCompare(b.name || ""),
        );
    }, [topics, searchFilter, categoryFilter]);

    const categoryCounts = useMemo(() => {
        return {
            all: topics.length,
            pragati: topics.filter((t) => classifyTopicOrService(t.name) === "pragati").length,
            dashboard: topics.filter((t) => classifyTopicOrService(t.name) === "dashboard").length,
            system: topics.filter((t) => classifyTopicOrService(t.name) === "system").length,
        };
    }, [topics]);

    // ---- Pagination --------------------------------------------------------

    const totalPages = Math.max(1, Math.ceil(filteredTopics.length / PAGE_SIZE));
    const safePage = Math.min(currentPage, totalPages);
    const paginatedTopics = useMemo(() => {
        const start = (safePage - 1) * PAGE_SIZE;
        return filteredTopics.slice(start, start + PAGE_SIZE);
    }, [filteredTopics, safePage]);

    // ---- Render: ROS2 unavailable ------------------------------------------

    if (ros2Available === false) {
        return html`
            <div style=${styles.ros2Unavailable}>
                <div style=${{ fontSize: "2em", marginBottom: "8px" }}>
                    \u{1F50C}
                </div>
                <div style=${{ fontSize: "1.1em", marginBottom: "4px" }}>
                    ROS2 Not Available
                </div>
                <div
                    style=${{
                        fontSize: "0.9em",
                        color: "var(--color-text-muted, #8494a7)",
                    }}
                >
                    Topic information requires an active ROS2 environment on
                    this entity.
                </div>
            </div>
        `;
    }

    // ---- Render: Loading ---------------------------------------------------

    if (loading && topics.length === 0) {
        return html`
            <div style=${styles.skeleton}>
                <style>
                    @keyframes shimmer {
                        0% { background-position: 200% 0; }
                        100% { background-position: -200% 0; }
                    }
                </style>
                ${Array.from({ length: 8 }, (_, i) => html`
                    <div key=${i} style=${{
                        ...styles.skeletonRow,
                        width: `${60 + Math.random() * 35}%`,
                    }} />
                `)}
            </div>
        `;
    }

    // ---- Render: connection status info ------------------------------------

    const connInfo = statusInfo(connectionStatus);

    // ---- Render: main layout -----------------------------------------------

    return html`
        <div style=${styles.container}>
            <!-- Category filter -->
            <${CategoryFilterBar}
                active=${categoryFilter}
                onChange=${(v) => { setCategoryFilter(v); setCurrentPage(1); }}
                counts=${categoryCounts}
            />

            <!-- Search filter -->
            <input
                type="text"
                placeholder="Filter topics by name or type..."
                value=${searchFilter}
                onInput=${(e) => setSearchFilter(e.target.value)}
                style=${styles.searchInput}
            />

            ${error && topics.length === 0
                ? html`
                      <div style=${styles.emptyState}>
                          <div
                              style=${{
                                  color: "var(--color-error, #f55353)",
                                  marginBottom: "8px",
                              }}
                          >
                              ${error}
                          </div>
                          <button
                              onClick=${() => fetchTopics(true)}
                              style=${styles.retryBtn}
                          >
                              Retry
                          </button>
                      </div>
                  `
                : filteredTopics.length === 0
                  ? html`
                        <div style=${styles.emptyState}>
                            ${searchFilter
                                ? `No topics matching "${searchFilter}"`
                                : "No topics found"}
                        </div>
                    `
                  : html`
                        <!-- Topic table -->
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
                                        <th
                                            style=${{
                                                ...styles.th,
                                                textAlign: "center",
                                            }}
                                        >
                                            Pub
                                        </th>
                                        <th
                                            style=${{
                                                ...styles.th,
                                                textAlign: "center",
                                            }}
                                        >
                                            Sub
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${paginatedTopics.map(
                                        (t, i) => html`
                                            <tr
                                                key=${t.name}
                                                onClick=${() => startEcho(t)}
                                                style=${{
                                                    cursor: "pointer",
                                                    background: rowBg(
                                                        i,
                                                        selectedTopic &&
                                                            selectedTopic.name ===
                                                                t.name,
                                                    ),
                                                    transition:
                                                        "background 0.15s",
                                                }}
                                                onMouseEnter=${(e) => {
                                                    if (
                                                        !(
                                                            selectedTopic &&
                                                            selectedTopic.name ===
                                                                t.name
                                                        )
                                                    ) {
                                                        e.currentTarget.style.background =
                                                            "rgba(255, 255, 255, 0.05)";
                                                    }
                                                }}
                                                onMouseLeave=${(e) => {
                                                    e.currentTarget.style.background =
                                                        rowBg(
                                                            i,
                                                            selectedTopic &&
                                                                selectedTopic.name ===
                                                                    t.name,
                                                        );
                                                }}
                                            >
                                                <td style=${styles.td}>
                                                    <span
                                                        style=${styles.topicName}
                                                    >
                                                        ${t.name}
                                                    </span>
                                                </td>
                                                <td style=${styles.td}>
                                                    <span
                                                        style=${styles.topicType}
                                                    >
                                                        ${t.type || "unknown"}
                                                    </span>
                                                </td>
                                                <td
                                                    style=${{
                                                        ...styles.td,
                                                        textAlign: "center",
                                                    }}
                                                >
                                                    <span
                                                        style=${{
                                                            ...styles.countBadge,
                                                            background:
                                                                (t.publisher_count ||
                                                                    0) > 0
                                                                    ? "rgba(34, 197, 94, 0.15)"
                                                                    : "rgba(139, 146, 167, 0.1)",
                                                            color:
                                                                (t.publisher_count ||
                                                                    0) > 0
                                                                    ? "var(--color-success, #22c55e)"
                                                                    : "var(--color-text-muted, #8494a7)",
                                                        }}
                                                    >
                                                        ${t.publisher_count ??
                                                        "--"}
                                                    </span>
                                                </td>
                                                <td
                                                    style=${{
                                                        ...styles.td,
                                                        textAlign: "center",
                                                    }}
                                                >
                                                    <span
                                                        style=${{
                                                            ...styles.countBadge,
                                                            background:
                                                                (t.subscriber_count ||
                                                                    0) > 0
                                                                    ? "rgba(75, 141, 247, 0.15)"
                                                                    : "rgba(139, 146, 167, 0.1)",
                                                            color:
                                                                (t.subscriber_count ||
                                                                    0) > 0
                                                                    ? "var(--color-accent, #4b8df7)"
                                                                    : "var(--color-text-muted, #8494a7)",
                                                        }}
                                                    >
                                                        ${t.subscriber_count ??
                                                        "--"}
                                                    </span>
                                                </td>
                                            </tr>
                                        `,
                                    )}
                                </tbody>
                            </table>
                        </div>

                        <!-- Pagination -->
                        ${filteredTopics.length > PAGE_SIZE ? html`
                            <div style=${styles.paginationBar}>
                                <button
                                    style=${safePage <= 1 ? styles.pageBtnDisabled : styles.pageBtn}
                                    disabled=${safePage <= 1}
                                    onClick=${() => setCurrentPage((p) => Math.max(1, p - 1))}
                                >
                                    Prev
                                </button>
                                <span>Page ${safePage} of ${totalPages}</span>
                                <button
                                    style=${safePage >= totalPages ? styles.pageBtnDisabled : styles.pageBtn}
                                    disabled=${safePage >= totalPages}
                                    onClick=${() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                                >
                                    Next
                                </button>
                            </div>
                        ` : null}

                        <!-- Topic count summary -->
                        <div
                            style=${{
                                fontSize: "0.8rem",
                                color: "var(--color-text-muted, #8494a7)",
                                textAlign: "right",
                            }}
                        >
                            ${filteredTopics.length} topic${filteredTopics.length !== 1 ? "s" : ""}
                            ${searchFilter
                                ? ` (filtered from ${topics.length})`
                                : ""}
                            ${stale ? html`<span style=${styles.staleBadge}>Stale</span>` : null}
                            ${stale || (error && topics.length > 0) ? html`
                                <button
                                    onClick=${() => fetchTopics(true)}
                                    style=${{ ...styles.retryBtn, marginLeft: "8px" }}
                                >
                                    Retry
                                </button>
                            ` : null}
                        </div>
                    `}

            <!-- Echo panel -->
            ${selectedTopic &&
            html`
                <div style=${styles.echoPanel}>
                    <div style=${styles.echoHeader}>
                        <div
                            style=${{
                                display: "flex",
                                alignItems: "center",
                                gap: "8px",
                            }}
                        >
                            <span style=${styles.echoTitle}>
                                ${selectedTopic.name}
                            </span>
                            <span
                                style=${{
                                    ...styles.echoBadge,
                                    background: "rgba(75, 141, 247, 0.15)",
                                    color: "var(--color-accent, #4b8df7)",
                                }}
                            >
                                10 Hz
                            </span>
                        </div>
                        <div style=${styles.echoControls}>
                            <!-- Connection status -->
                            <span
                                style=${{
                                    display: "flex",
                                    alignItems: "center",
                                    fontSize: "0.8rem",
                                }}
                            >
                                <span
                                    style=${{
                                        ...styles.statusDot,
                                        background: connInfo.color,
                                    }}
                                />
                                <span style=${{ color: connInfo.color }}>
                                    ${connInfo.label}
                                </span>
                            </span>
                            <!-- Message count -->
                            <span
                                style=${{
                                    ...styles.echoBadge,
                                    background: "rgba(139, 146, 167, 0.15)",
                                    color: "var(--color-text-secondary, #8b92a7)",
                                }}
                            >
                                ${echoMessages.length} msg${echoMessages.length !== 1 ? "s" : ""}
                            </span>
                            <!-- Stop button -->
                            <button
                                onClick=${stopEcho}
                                style=${styles.stopBtn}
                            >
                                Stop
                            </button>
                        </div>
                    </div>
                    <div ref=${echoBodyRef} style=${styles.echoBody}>
                                      ${reconnectStatus && html`
                                          <div
                                              style=${{
                                                  padding: "8px 12px",
                                                  margin: "4px 0",
                                                  background: "var(--badge-warning-bg, rgba(245, 158, 11, 0.15))",
                                                  border: "1px solid var(--color-warning, #f59e0b)",
                                                  borderRadius: "var(--radius-sm, 4px)",
                                                  color: "var(--color-warning, #f59e0b)",
                                                  fontSize: "0.85em",
                                                  display: "flex",
                                                  alignItems: "center",
                                                  gap: "8px",
                                              }}
                                          >
                                              <span style=${{ animation: "pulse 1.5s ease-in-out infinite" }}>●</span>
                                              Reconnecting... (attempt ${reconnectStatus.attempt}, retry in ${Math.round(reconnectStatus.delayMs / 1000)}s)
                                          </div>
                                      `}
                                      ${echoMessages.length === 0
                                          ? html`
                                                <div
                                                    style=${{
                                                        textAlign: "center",
                                                        color: "var(--color-text-muted, #8494a7)",
                                                        padding: "24px",
                                                    }}
                                                >
                                                    ${connectionStatus === "connecting"
                                                        ? "Waiting for messages..."
                                                        : connectionStatus === "reconnecting"
                                                          ? "Stream interrupted — reconnecting..."
                                                          : connectionStatus === "error"
                                                            ? html`
                                                                  Stream to ${selectedTopic?.name} disconnected.
                                                                  <button
                                                                      onClick=${() => startEcho(selectedTopic)}
                                                                      style=${{ marginLeft: "8px", cursor: "pointer" }}
                                                                  >Retry</button>
                                                              `
                                                            : "No messages yet"}
                                                </div>
                                            `
                            : echoMessages.map(
                                  (msg) => html`
                                      <div key=${msg.id} style=${styles.echoMsg}>
                                          <span style=${styles.echoTimestamp}>
                                              [${formatTimestamp(
                                                  msg.timestamp,
                                              )}]
                                          </span>
                                          <span style=${styles.echoData}>
                                              ${formatEchoData(msg.data)}
                                          </span>
                                      </div>
                                  `,
                              )}
                    </div>
                </div>
            `}

            <!-- Publish Topic panel -->
            <div style=${styles.publishPanel}>
                <div
                    style=${styles.publishHeader}
                    onClick=${() => setPublishPanelOpen((v) => !v)}
                    data-testid="publish-panel-header"
                >
                    <span style=${styles.publishTitle}>Publish Topic</span>
                    <span style=${{ fontSize: "0.75rem", color: "var(--color-text-muted, #8494a7)" }}>
                        ${publishPanelOpen ? "\u25B2" : "\u25BC"}
                    </span>
                </div>
                ${publishPanelOpen && html`
                    <div style=${styles.publishBody} data-testid="publish-panel-body">
                        ${publishTopics.length === 0
                            ? html`<span style=${styles.publishEmptyMsg} data-testid="publish-no-topics">No publishable topics configured</span>`
                            : html`
                                <select
                                    style=${styles.publishSelect}
                                    value=${selectedPublishTopic?.name ?? ""}
                                    onChange=${(e) => handleTopicSelect(e.target.value)}
                                    data-testid="publish-topic-select"
                                >
                                    <option value="">Select a topic...</option>
                                    ${publishTopics.map((t) => html`
                                        <option key=${t.name} value=${t.name}>
                                            ${t.label || t.name}
                                        </option>
                                    `)}
                                </select>

                                ${selectedPublishTopic && html`
                                    <textarea
                                        style=${styles.publishTextarea}
                                        value=${publishData}
                                        onInput=${(e) => {
                                            setPublishData(e.target.value);
                                            setPublishFeedback(null);
                                        }}
                                        data-testid="publish-data-textarea"
                                        spellcheck="false"
                                        autocomplete="off"
                                    />
                                    <button
                                        style=${isPublishing ? styles.publishBtnDisabled : styles.publishBtn}
                                        disabled=${isPublishing}
                                        onClick=${handlePublish}
                                        data-testid="publish-button"
                                    >
                                        ${isPublishing ? "Publishing..." : "Publish"}
                                    </button>
                                `}

                                ${publishFeedback && html`
                                    <div
                                        style=${publishFeedback.type === "success"
                                            ? styles.publishFeedbackSuccess
                                            : styles.publishFeedbackError}
                                        data-testid="publish-feedback"
                                        role="status"
                                    >
                                        ${publishFeedback.message}
                                    </div>
                                `}
                            `}
                    </div>
                `}
            </div>
        </div>
    `;
}
