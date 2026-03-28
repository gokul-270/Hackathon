/**
 * RosbagSubTab — Entity-scoped rosbag recording, playback, and management.
 *
 * Features:
 * - Recording controls with profile selection and live status
 * - Bag list table with size, duration, topics, download
 * - Playback controls per bag
 * - Auto-polling recording status every 2 seconds
 * - Disk usage warnings
 *
 * @module tabs/entity/RosbagSubTab
 */
import {
    useState,
    useEffect,
    useCallback,
    useMemo,
    useRef,
} from "preact/hooks";
import { html } from "htm/preact";
import {
    safeFetch,
    formatBytes,
    formatDuration,
    formatDate,
} from "../../utils.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 2000;
const RECORDING_PROFILES = ["default", "motor_debug", "navigation", "full"];
const DISK_WARNING_MB = 500;

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
    container: {
        display: "flex",
        flexDirection: "column",
        gap: "16px",
    },
    section: {
        background: "var(--bg-secondary, #1a1a2e)",
        border: "1px solid var(--border-color, #333)",
        borderRadius: "8px",
        padding: "16px",
    },
    sectionTitle: {
        margin: "0 0 12px 0",
        fontSize: "1rem",
        fontWeight: 600,
        color: "var(--text-primary, #e0e0e0)",
    },
    controlRow: {
        display: "flex",
        alignItems: "center",
        gap: "10px",
        flexWrap: "wrap",
    },
    select: {
        padding: "6px 10px",
        borderRadius: "6px",
        border: "1px solid var(--border-color, #333)",
        background: "var(--bg-tertiary, #16213e)",
        color: "var(--text-primary, #e0e0e0)",
        fontSize: "0.85rem",
        outline: "none",
    },
    btnGreen: {
        padding: "6px 14px",
        borderRadius: "6px",
        border: "none",
        background: "#22c55e",
        color: "#fff",
        fontWeight: 600,
        fontSize: "0.85rem",
        cursor: "pointer",
    },
    btnRed: {
        padding: "6px 14px",
        borderRadius: "6px",
        border: "none",
        background: "#ef4444",
        color: "#fff",
        fontWeight: 600,
        fontSize: "0.85rem",
        cursor: "pointer",
    },
    btnBlue: {
        padding: "6px 14px",
        borderRadius: "6px",
        border: "none",
        background: "#3b82f6",
        color: "#fff",
        fontWeight: 600,
        fontSize: "0.85rem",
        cursor: "pointer",
    },
    btnDisabled: {
        padding: "6px 14px",
        borderRadius: "6px",
        border: "none",
        background: "#555",
        color: "#999",
        fontWeight: 600,
        fontSize: "0.85rem",
        cursor: "not-allowed",
    },
    btnSmall: {
        padding: "4px 10px",
        borderRadius: "4px",
        border: "none",
        fontWeight: 600,
        fontSize: "0.8rem",
        cursor: "pointer",
    },
    indicator: {
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "8px 12px",
        borderRadius: "6px",
        background: "rgba(239, 68, 68, 0.1)",
        border: "1px solid rgba(239, 68, 68, 0.3)",
        fontSize: "0.85rem",
        color: "#fca5a5",
    },
    playbackIndicator: {
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "8px 12px",
        borderRadius: "6px",
        background: "rgba(59, 130, 246, 0.1)",
        border: "1px solid rgba(59, 130, 246, 0.3)",
        fontSize: "0.85rem",
        color: "#93c5fd",
    },
    pulsingDot: {
        width: "10px",
        height: "10px",
        borderRadius: "50%",
        background: "#ef4444",
        animation: "rosbag-pulse 1s ease-in-out infinite",
    },
    diskWarning: {
        color: "#fbbf24",
        fontWeight: 600,
        fontSize: "0.85rem",
    },
    diskOk: {
        color: "var(--text-secondary, #aaa)",
        fontSize: "0.85rem",
    },
    table: {
        width: "100%",
        borderCollapse: "collapse",
        fontSize: "0.85rem",
    },
    th: {
        textAlign: "left",
        padding: "8px 12px",
        borderBottom: "2px solid var(--border-color, #333)",
        color: "var(--text-secondary, #aaa)",
        fontWeight: 600,
        fontSize: "0.8rem",
        textTransform: "uppercase",
        letterSpacing: "0.5px",
    },
    td: {
        padding: "8px 12px",
        borderBottom: "1px solid var(--border-color, #222)",
        color: "var(--text-primary, #e0e0e0)",
    },
    mono: {
        fontFamily: "monospace",
        fontSize: "0.85rem",
    },
    statusLine: {
        fontSize: "0.85rem",
        padding: "6px 10px",
        borderRadius: "4px",
        background: "rgba(239, 68, 68, 0.1)",
        color: "#fca5a5",
        border: "1px solid rgba(239, 68, 68, 0.3)",
    },
    emptyState: {
        textAlign: "center",
        padding: "24px",
        color: "var(--text-secondary, #aaa)",
        fontSize: "0.9rem",
    },
};

// Keyframe animation injected once into the document
const PULSE_STYLE_ID = "rosbag-pulse-keyframes";
function ensurePulseAnimation() {
    if (document.getElementById(PULSE_STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = PULSE_STYLE_ID;
    style.textContent = `
        @keyframes rosbag-pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
    `;
    document.head.appendChild(style);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format MB value for display. */
function formatMB(mb) {
    if (mb == null || isNaN(mb)) return "--";
    if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
    return `${mb.toFixed(1)} MB`;
}

/** Format seconds into mm:ss or hh:mm:ss for timer display. */
function formatTimer(seconds) {
    if (seconds == null || isNaN(seconds)) return "00:00";
    const s = Math.floor(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const mm = String(m).padStart(2, "0");
    const ss = String(sec).padStart(2, "0");
    if (h > 0) {
        const hh = String(h).padStart(2, "0");
        return `${hh}:${mm}:${ss}`;
    }
    return `${mm}:${ss}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RosbagSubTab({
    entityId,
    entitySource,
    entityIp,
    ros2Available,
    registerCleanup,
}) {
    // -- State: Recording --
    const [profile, setProfile] = useState("default");
    const [recording, setRecording] = useState(false);
    const [recordStatus, setRecordStatus] = useState(null);
    const [recordLoading, setRecordLoading] = useState(false);

    // -- State: Bag list --
    const [bags, setBags] = useState([]);
    const [bagsLoading, setBagsLoading] = useState(false);

    // -- State: Playback --
    const [playingBag, setPlayingBag] = useState(null);
    const [playLoading, setPlayLoading] = useState(false);

    // -- State: Error --
    const [error, setError] = useState(null);

    const pollRef = useRef(null);
    const baseUrl = `/api/entities/${entityId}/rosbag`;

    // Inject pulse animation CSS
    useEffect(() => {
        ensurePulseAnimation();
    }, []);

    // ------------------------------------------------------------------
    // API helpers
    // ------------------------------------------------------------------

    const apiGet = useCallback(
        async (path) => {
            const result = await safeFetch(`${baseUrl}${path}`);
            if (result == null) return null;
            return result.data != null ? result.data : result;
        },
        [baseUrl]
    );

    const apiPost = useCallback(
        async (path, body) => {
            const result = await safeFetch(`${baseUrl}${path}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: body != null ? JSON.stringify(body) : undefined,
            });
            if (result == null) return null;
            return result.data != null ? result.data : result;
        },
        [baseUrl]
    );

    // ------------------------------------------------------------------
    // Fetch bag list
    // ------------------------------------------------------------------

    const fetchBags = useCallback(async () => {
        setBagsLoading(true);
        try {
            const data = await apiGet("/list");
            if (data && Array.isArray(data)) {
                setBags(data);
            } else if (data && Array.isArray(data.bags)) {
                setBags(data.bags);
            }
        } catch (err) {
            console.error("RosbagSubTab: failed to fetch bags", err);
            setError("Failed to load bag list.");
        } finally {
            setBagsLoading(false);
        }
    }, [apiGet]);

    // ------------------------------------------------------------------
    // Poll recording status
    // ------------------------------------------------------------------

    const pollRecordStatus = useCallback(async () => {
        try {
            const data = await apiGet("/record/status");
            if (data) {
                setRecordStatus(data);
                setRecording(!!data.recording);
            }
        } catch (err) {
            console.error("RosbagSubTab: poll error", err);
        }
    }, [apiGet]);

    // Start polling on mount; clean up on unmount
    useEffect(() => {
        // Initial fetch
        pollRecordStatus();

        pollRef.current = setInterval(pollRecordStatus, POLL_INTERVAL_MS);

        const cleanup = () => {
            if (pollRef.current) {
                clearInterval(pollRef.current);
                pollRef.current = null;
            }
        };

        if (registerCleanup) {
            registerCleanup(cleanup);
        }

        return cleanup;
    }, [pollRecordStatus, registerCleanup]);

    // Fetch bags on mount
    useEffect(() => {
        fetchBags();
    }, [fetchBags]);

    // ------------------------------------------------------------------
    // Recording actions
    // ------------------------------------------------------------------

    const handleStartRecording = useCallback(async () => {
        setRecordLoading(true);
        setError(null);
        try {
            const result = await apiPost("/record/start", { profile });
            if (result != null) {
                setRecording(true);
            } else {
                setError("Failed to start recording.");
            }
        } catch (err) {
            setError("Failed to start recording.");
        } finally {
            setRecordLoading(false);
        }
    }, [apiPost, profile]);

    const handleStopRecording = useCallback(async () => {
        if (!confirm("Stop recording?")) return;
        setRecordLoading(true);
        setError(null);
        try {
            const result = await apiPost("/record/stop");
            if (result != null) {
                setRecording(false);
                setRecordStatus(null);
                // Refresh bag list after stop
                setTimeout(fetchBags, 1000);
            } else {
                setError("Failed to stop recording.");
            }
        } catch (err) {
            setError("Failed to stop recording.");
        } finally {
            setRecordLoading(false);
        }
    }, [apiPost, fetchBags]);

    // ------------------------------------------------------------------
    // Playback actions
    // ------------------------------------------------------------------

    const handlePlay = useCallback(
        async (bagName) => {
            if (recording) return;
            setPlayLoading(true);
            setError(null);
            try {
                const result = await apiPost("/play/start", {
                    bag_name: bagName,
                });
                if (result != null) {
                    setPlayingBag(bagName);
                } else {
                    setError("Failed to start playback.");
                }
            } catch (err) {
                setError("Failed to start playback.");
            } finally {
                setPlayLoading(false);
            }
        },
        [apiPost, recording]
    );

    const handleStopPlayback = useCallback(async () => {
        setPlayLoading(true);
        setError(null);
        try {
            const result = await apiPost("/play/stop");
            if (result != null) {
                setPlayingBag(null);
            } else {
                setError("Failed to stop playback.");
            }
        } catch (err) {
            setError("Failed to stop playback.");
        } finally {
            setPlayLoading(false);
        }
    }, [apiPost]);

    // ------------------------------------------------------------------
    // Download
    // ------------------------------------------------------------------

    const handleDownload = useCallback(
        (bagName) => {
            const url = `${baseUrl}/download/${encodeURIComponent(bagName)}`;
            window.open(url, "_blank");
        },
        [baseUrl]
    );

    // ------------------------------------------------------------------
    // Derived state
    // ------------------------------------------------------------------

    const diskLow = useMemo(() => {
        if (!recordStatus || recordStatus.disk_remaining_mb == null) {
            return false;
        }
        return recordStatus.disk_remaining_mb < DISK_WARNING_MB;
    }, [recordStatus]);

    // ------------------------------------------------------------------
    // Render: Recording section
    // ------------------------------------------------------------------

    function renderRecordingSection() {
        return html`
            <div style=${styles.section}>
                <h3 style=${styles.sectionTitle}>Recording</h3>

                <div style=${styles.controlRow}>
                    <label
                        style=${{
                            fontSize: "0.85rem",
                            color: "var(--text-secondary, #aaa)",
                        }}
                    >
                        Profile:
                    </label>
                    <select
                        style=${styles.select}
                        value=${profile}
                        onChange=${(e) => setProfile(e.target.value)}
                        disabled=${recording}
                    >
                        ${RECORDING_PROFILES.map(
                            (p) => html`<option value=${p}>${p}</option>`
                        )}
                    </select>

                    ${recording
                        ? html`
                              <button
                                  style=${recordLoading
                                      ? styles.btnDisabled
                                      : styles.btnRed}
                                  onClick=${handleStopRecording}
                                  disabled=${recordLoading}
                              >
                                  ${recordLoading
                                      ? "Stopping..."
                                      : "Stop Recording"}
                              </button>
                          `
                        : html`
                              <button
                                  style=${recordLoading
                                      ? styles.btnDisabled
                                      : styles.btnGreen}
                                  onClick=${handleStartRecording}
                                  disabled=${recordLoading}
                              >
                                  ${recordLoading
                                      ? "Starting..."
                                      : "Start Recording"}
                              </button>
                          `}

                    ${recordStatus &&
                    recordStatus.disk_remaining_mb != null
                        ? html`
                              <span
                                  style=${diskLow
                                      ? styles.diskWarning
                                      : styles.diskOk}
                              >
                                  Disk:
                                  ${formatMB(recordStatus.disk_remaining_mb)}
                                  remaining
                                  ${diskLow ? " (LOW!)" : ""}
                              </span>
                          `
                        : null}
                </div>

                ${recording && recordStatus
                    ? html`
                          <div style=${{ marginTop: "12px" }}>
                              <div style=${styles.indicator}>
                                  <span style=${styles.pulsingDot}></span>
                                  <span style=${{ fontWeight: 600 }}>
                                      REC
                                  </span>
                                  <span>
                                      ${formatTimer(recordStatus.duration_s)}
                                  </span>
                                  <span style=${{ color: "#aaa" }}>|</span>
                                  <span>
                                      ~${formatMB(
                                          recordStatus.estimated_size_mb
                                      )}
                                  </span>
                                  ${recordStatus.profile
                                      ? html`
                                            <span
                                                style=${{ color: "#aaa" }}
                                            >
                                                |
                                            </span>
                                            <span style=${styles.mono}>
                                                ${recordStatus.profile}
                                            </span>
                                        `
                                      : null}
                              </div>
                          </div>
                      `
                    : null}
            </div>
        `;
    }

    // ------------------------------------------------------------------
    // Render: Bag list section
    // ------------------------------------------------------------------

    function renderBagListSection() {
        return html`
            <div style=${styles.section}>
                <div
                    style=${{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: "12px",
                    }}
                >
                    <h3 style=${{ ...styles.sectionTitle, margin: 0 }}>
                        Recorded Bags
                    </h3>
                    <button
                        style=${bagsLoading ? styles.btnDisabled : styles.btnBlue}
                        onClick=${fetchBags}
                        disabled=${bagsLoading}
                    >
                        ${bagsLoading ? "Loading..." : "Refresh"}
                    </button>
                </div>

                ${playingBag
                    ? html`
                          <div
                              style=${{
                                  ...styles.playbackIndicator,
                                  marginBottom: "12px",
                              }}
                          >
                              <span>Playing:</span>
                              <span style=${styles.mono}>${playingBag}</span>
                              <button
                                  style=${{
                                      ...styles.btnSmall,
                                      background: "#ef4444",
                                      color: "#fff",
                                      marginLeft: "8px",
                                  }}
                                  onClick=${handleStopPlayback}
                                  disabled=${playLoading}
                              >
                                  ${playLoading
                                      ? "Stopping..."
                                      : "Stop Playback"}
                              </button>
                          </div>
                      `
                    : null}

                ${bags.length === 0
                    ? html`
                          <div style=${styles.emptyState}>
                              ${bagsLoading
                                  ? "Loading bags..."
                                  : "No recorded bags found."}
                          </div>
                      `
                    : html`
                          <div style=${{ overflowX: "auto" }}>
                              <table style=${styles.table}>
                                  <thead>
                                      <tr>
                                          <th style=${styles.th}>Name</th>
                                          <th style=${styles.th}>Size</th>
                                          <th style=${styles.th}>Duration</th>
                                          <th style=${styles.th}>Topics</th>
                                          <th style=${styles.th}>Messages</th>
                                          <th style=${styles.th}>Created</th>
                                          <th style=${styles.th}>Actions</th>
                                      </tr>
                                  </thead>
                                  <tbody>
                                      ${bags.map(
                                          (bag) => html`
                                              <tr key=${bag.name}>
                                                  <td
                                                      style=${{
                                                          ...styles.td,
                                                          ...styles.mono,
                                                      }}
                                                  >
                                                      ${bag.name || "--"}
                                                  </td>
                                                  <td style=${styles.td}>
                                                      ${bag.size != null
                                                          ? formatBytes(
                                                                bag.size
                                                            )
                                                          : bag.size_mb != null
                                                            ? formatMB(
                                                                  bag.size_mb
                                                              )
                                                            : "--"}
                                                  </td>
                                                  <td style=${styles.td}>
                                                      ${bag.duration != null
                                                          ? formatDuration(
                                                                bag.duration
                                                            )
                                                          : bag.duration_s !=
                                                              null
                                                            ? formatDuration(
                                                                  bag.duration_s
                                                              )
                                                            : "--"}
                                                  </td>
                                                  <td style=${styles.td}>
                                                      ${bag.topics != null
                                                          ? Array.isArray(
                                                                  bag.topics
                                                              )
                                                              ? bag.topics
                                                                    .length
                                                              : bag.topics
                                                          : "--"}
                                                  </td>
                                                  <td style=${styles.td}>
                                                      ${bag.messages != null
                                                          ? bag.messages.toLocaleString()
                                                          : bag.message_count !=
                                                              null
                                                            ? bag.message_count.toLocaleString()
                                                            : "--"}
                                                  </td>
                                                  <td style=${styles.td}>
                                                      ${formatDate(
                                                          bag.created ||
                                                              bag.created_at ||
                                                              bag.start_time
                                                      )}
                                                  </td>
                                                  <td style=${styles.td}>
                                                      ${renderBagActions(bag)}
                                                  </td>
                                              </tr>
                                          `
                                      )}
                                  </tbody>
                              </table>
                          </div>
                      `}
            </div>
        `;
    }

    // ------------------------------------------------------------------
    // Render: Bag row actions
    // ------------------------------------------------------------------

    function renderBagActions(bag) {
        const isPlaying = playingBag === bag.name;
        const playDisabled = recording || playLoading;
        const playTitle = recording
            ? "Stop recording first"
            : isPlaying
              ? "Currently playing"
              : "Play this bag";

        return html`
            <div style=${{ display: "flex", gap: "6px" }}>
                ${isPlaying
                    ? html`
                          <button
                              style=${{
                                  ...styles.btnSmall,
                                  background: "#ef4444",
                                  color: "#fff",
                              }}
                              onClick=${handleStopPlayback}
                              disabled=${playLoading}
                              title="Stop playback"
                          >
                              Stop
                          </button>
                      `
                    : html`
                          <button
                              style=${{
                                  ...styles.btnSmall,
                                  background: playDisabled ? "#555" : "#3b82f6",
                                  color: playDisabled ? "#999" : "#fff",
                                  cursor: playDisabled
                                      ? "not-allowed"
                                      : "pointer",
                              }}
                              onClick=${() =>
                                  !playDisabled && handlePlay(bag.name)}
                              disabled=${playDisabled}
                              title=${playTitle}
                          >
                              Play
                          </button>
                      `}

                <button
                    style=${{
                        ...styles.btnSmall,
                        background: "#6366f1",
                        color: "#fff",
                    }}
                    onClick=${() => handleDownload(bag.name)}
                    title="Download bag (tar.gz)"
                >
                    Download
                </button>
            </div>
        `;
    }

    // ------------------------------------------------------------------
    // Render: Main
    // ------------------------------------------------------------------

    return html`
        <div style=${styles.container}>
            ${error
                ? html`
                      <div style=${styles.statusLine}>
                          ${error}
                          <button
                              style=${{
                                  marginLeft: "10px",
                                  background: "transparent",
                                  border: "none",
                                  color: "#fca5a5",
                                  cursor: "pointer",
                                  fontWeight: 600,
                              }}
                              onClick=${() => setError(null)}
                          >
                              Dismiss
                          </button>
                      </div>
                  `
                : null}

            ${renderRecordingSection()} ${renderBagListSection()}
        </div>
    `;
}
