/**
 * TopicsTab — Preact component for browsing and filtering ROS2 topics.
 *
 * Migrated from vanilla JS as part of task 6.2 of the
 * dashboard-frontend-migration.
 *
 * @module tabs/TopicsTab
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
 * Topic names (or prefixes) considered infrastructure rather than
 * application-level topics.
 */
const INFRA_PATTERNS = [
    "/parameter_events",
    "/rosout",
    "/tf",
    "/tf_static",
    "/robot_description",
    "/clock",
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Classify a topic as "main" or "infra".
 * @param {string} name
 * @returns {"main"|"infra"}
 */
function classifyTopic(name) {
    return INFRA_PATTERNS.some((p) => name === p || name.startsWith(p + "/"))
        ? "infra"
        : "main";
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function TopicsTab() {
    const { data: wsData } = useContext(WebSocketContext);
    const systemState = wsData ? wsData.system_state : null;
    const ros2Available = systemState ? systemState.ros2_available : null;
    const isInitializing = systemState === null || systemState === undefined;

    const [topics, setTopics] = useState({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchQuery, setSearchQuery] = useState("");
    const [category, setCategory] = useState("main");
    const mountedRef = useRef(true);

    // ---- data loading -----------------------------------------------------

    const loadTopics = useCallback(async () => {
        const data = await safeFetch("/api/topics");
        if (!mountedRef.current) return;

        if (data) {
            setTopics(data);
            setError(null);
        } else {
            setError("Failed to load topics");
        }
        setLoading(false);
    }, []);

    // ---- lifecycle --------------------------------------------------------

    useEffect(() => {
        mountedRef.current = true;
        loadTopics();
        return () => {
            mountedRef.current = false;
        };
    }, [loadTopics]);

    useEffect(() => {
        const id = setInterval(loadTopics, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [loadTopics]);

    // ---- derived data -----------------------------------------------------

    const filteredTopics = useMemo(() => {
        const entries = Object.entries(topics).sort(([a], [b]) =>
            a.localeCompare(b)
        );
        const lowerQ = searchQuery.toLowerCase();

        return entries.filter(([name]) => {
            // Category filter
            if (category !== "all") {
                const cat = classifyTopic(name);
                if (cat !== category) return false;
            }
            // Text search
            if (lowerQ && !name.toLowerCase().includes(lowerQ)) return false;
            return true;
        });
    }, [topics, searchQuery, category]);

    // ---- render -----------------------------------------------------------

    if (isInitializing) {
        return html`
            <div class="section-header">
                <h2>ROS2 Topics</h2>
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
                <h2>ROS2 Topics</h2>
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
                <div style=${{ fontSize: '0.9em', color: 'var(--text-muted)' }}>Topic information requires an active ROS2 environment</div>
            </div>
        `;
    }

    return html`
        <div class="section-header">
            <h2>ROS2 Topics</h2>
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
                    placeholder="Search topics..."
                    value=${searchQuery}
                    onInput=${(e) => setSearchQuery(e.target.value)}
                />
            </div>
        </div>

        <div class="topics-list">
            ${loading && Object.keys(topics).length === 0
                ? html`<div class="loading">Loading topics...</div>`
                : error && Object.keys(topics).length === 0
                  ? html`<div class="empty-state">${error}</div>`
                  : filteredTopics.length === 0
                    ? html`<div class="empty-state">No topics found</div>`
                    : filteredTopics.map(
                          ([name, info]) => html`
                              <div
                                  key=${name}
                                  class="topic-item"
                                  data-category=${classifyTopic(name)}
                              >
                                  <div class="topic-header">
                                      <div
                                          class="topic-name topic-echo-link"
                                          role="button"
                                          tabindex="0"
                                          data-topic=${name}
                                      >
                                          ${name}
                                      </div>
                                      <div class="topic-type">
                                          ${info.type || "unknown"}
                                      </div>
                                  </div>
                              </div>
                          `
                      )}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Register with the Preact app shell
// ---------------------------------------------------------------------------

registerTab("topics", TopicsTab);

export { TopicsTab };
