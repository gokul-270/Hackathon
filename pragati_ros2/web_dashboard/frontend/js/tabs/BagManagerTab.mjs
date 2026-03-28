/**
 * BagManagerTab — Preact component for ROS2 bag recording and management.
 *
 * Migrated from vanilla JS as part of task 6.5 of the
 * dashboard-frontend-migration.
 *
 * @module tabs/BagManagerTab
 */
import { h } from "preact";
import {
    useState,
    useEffect,
    useCallback,
    useMemo,
    useRef,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch, formatBytes, formatDuration, formatDate } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { useConfirmDialog } from "../components/ConfirmationDialog.mjs";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 30000;
const TIMER_INTERVAL_MS = 1000;
const ASSUMED_TOTAL_DISK_BYTES = 64 * 1024 * 1024 * 1024; // 64 GB

/** Disk space thresholds in bytes */
const DISK_GREEN_THRESHOLD = 10 * 1024 * 1024 * 1024; // 10 GB
const DISK_YELLOW_THRESHOLD = 2 * 1024 * 1024 * 1024; // 2 GB

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Normalize a bag object from the API — field names vary between backends.
 * @param {Object} raw
 * @returns {Object}
 */
function normalizeBag(raw) {
    return {
        name: raw.name,
        date: raw.start_time || raw.date || null,
        duration: raw.duration_seconds ?? raw.duration ?? null,
        size: raw.size_bytes ?? raw.size ?? null,
        messages: raw.message_count ?? raw.messages ?? null,
        topics: raw.topic_count ?? raw.topics ?? null,
        format: raw.storage_format || raw.format || "--",
    };
}

/**
 * Return a CSS class for the disk space colour.
 * @param {number} availableBytes
 * @returns {string}
 */
function diskBarColorClass(availableBytes) {
    if (availableBytes >= DISK_GREEN_THRESHOLD) return "bag-disk-green";
    if (availableBytes >= DISK_YELLOW_THRESHOLD) return "bag-disk-yellow";
    return "bag-disk-red";
}

/**
 * Format elapsed seconds as HH:MM:SS.
 * @param {number} totalSec
 * @returns {string}
 */
function formatElapsed(totalSec) {
    const s = Math.max(0, Math.floor(totalSec));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return [h, m, sec].map((v) => String(v).padStart(2, "0")).join(":");
}

// ---------------------------------------------------------------------------
// Sort comparator
// ---------------------------------------------------------------------------

/**
 * Build a comparator for bag objects.
 * @param {string} column
 * @param {boolean} asc
 * @returns {(a: Object, b: Object) => number}
 */
function bagComparator(column, asc) {
    return (a, b) => {
        let va = a[column];
        let vb = b[column];

        // Treat null/undefined as smallest
        if (va == null && vb == null) return 0;
        if (va == null) return asc ? -1 : 1;
        if (vb == null) return asc ? 1 : -1;

        // String comparison for name/format/date
        if (typeof va === "string" && typeof vb === "string") {
            const cmp = va.localeCompare(vb);
            return asc ? cmp : -cmp;
        }

        // Numeric
        const cmp = va - vb;
        return asc ? cmp : -cmp;
    };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Recording controls panel — idle state with profile selector + start button,
 * or active state with pulse indicator, info, and stop button.
 */
function RecordingPanel({
    recording,
    selectedProfile,
    onProfileChange,
    onStart,
    onStop,
    elapsedSeconds,
}) {
    if (recording && recording.active) {
        return html`
            <div class="stats-panel">
                <h3>Recording Control</h3>
                <div class="bag-recording-panel bag-recording-active">
                    <div class="bag-recording-indicator">
                        <span class="bag-pulse-dot"></span>
                        <span class="bag-recording-label">Recording</span>
                    </div>
                    <div class="bag-recording-info">
                        <div class="bag-info-row">
                            <span class="bag-info-label">Duration:</span>
                            <span class="bag-info-value">
                                ${formatElapsed(elapsedSeconds)}
                            </span>
                        </div>
                        <div class="bag-info-row">
                            <span class="bag-info-label">Profile:</span>
                            <span class="bag-info-value">
                                <span class="bag-badge">${recording.profile || "standard"}</span>
                            </span>
                        </div>
                        ${recording.estimatedSize != null &&
                        html`
                            <div class="bag-info-row">
                                <span class="bag-info-label">Est. Size:</span>
                                <span class="bag-info-value">
                                    ${formatBytes(recording.estimatedSize)}
                                </span>
                            </div>
                        `}
                    </div>
                    <button class="btn btn-danger" onClick=${onStop}>
                        Stop Recording
                    </button>
                </div>
            </div>
        `;
    }

    return html`
        <div class="stats-panel">
            <h3>Recording Control</h3>
            <div class="bag-recording-panel bag-recording-idle">
                <div class="bag-profile-selector">
                    <label>Profile:</label>
                    <select
                        class="bag-select"
                        value=${selectedProfile}
                        onChange=${(e) => onProfileChange(e.target.value)}
                    >
                        <option value="minimal">Minimal</option>
                        <option value="standard">Standard</option>
                        <option value="debug">Debug</option>
                    </select>
                </div>
                <button class="btn btn-success" onClick=${onStart}>
                    Start Recording
                </button>
            </div>
        </div>
    `;
}

/**
 * Disk space panel with a colour-coded bar.
 */
function DiskSpacePanel({ diskSpace }) {
    if (!diskSpace) {
        return html`
            <div class="stats-panel">
                <h3>Disk Space</h3>
                <div class="bag-disk-panel">
                    <span class="section-loading">Checking disk space...</span>
                </div>
            </div>
        `;
    }

    const { available, total } = diskSpace;
    const usedPct = total > 0 ? ((total - available) / total) * 100 : 0;
    const colorClass = diskBarColorClass(available);

    return html`
        <div class="stats-panel">
            <h3>Disk Space</h3>
            <div class="bag-disk-panel">
                <div class="bag-disk-info">
                    ${formatBytes(available)} available of ${formatBytes(total)}
                </div>
                <div class="bag-disk-bar-container">
                    <div
                        class="bag-disk-bar ${colorClass}"
                        style="width: ${Math.min(usedPct, 100).toFixed(1)}%"
                    ></div>
                </div>
                ${available < DISK_YELLOW_THRESHOLD &&
                html`
                    <div class="bag-disk-warning">
                        Low disk space — recording may fail
                    </div>
                `}
            </div>
        </div>
    `;
}

/**
 * Sortable column header.
 */
function SortHeader({ label, column, sortColumn, sortAsc, onSort }) {
    const active = sortColumn === column;
    const arrow = active ? (sortAsc ? " \u25B2" : " \u25BC") : "";

    return html`
        <th
            class="bag-sortable"
            onClick=${() => onSort(column)}
            style="cursor: pointer"
        >
            ${label}${arrow}
        </th>
    `;
}

/**
 * Bag detail panel showing topic information.
 */
function BagDetailPanel({ selectedBag, onClose }) {
    if (!selectedBag) return null;

    const { name, detail } = selectedBag;

    return html`
        <div class="bag-detail-card">
            <div class="bag-detail-header">
                <h3>${name}</h3>
                <button class="btn btn-sm bag-detail-close" onClick=${onClose}>
                    Close
                </button>
            </div>
            ${detail
                ? html`
                      <div class="bag-detail-meta">
                          <div class="bag-info-row">
                              <span class="bag-info-label">Start:</span>
                              <span class="bag-info-value">
                                  ${formatDate(detail.start_time)}
                              </span>
                          </div>
                          <div class="bag-info-row">
                              <span class="bag-info-label">End:</span>
                              <span class="bag-info-value">
                                  ${formatDate(detail.end_time)}
                              </span>
                          </div>
                          <div class="bag-info-row">
                              <span class="bag-info-label">Duration:</span>
                              <span class="bag-info-value">
                                  ${formatDuration(detail.duration_seconds ?? detail.duration)}
                              </span>
                          </div>
                      </div>
                      ${detail.topics && detail.topics.length > 0
                          ? html`
                                <div class="bag-detail-topics">
                                    <h4>Topics</h4>
                                    <table class="bag-topic-table">
                                        <thead>
                                            <tr>
                                                <th>Topic</th>
                                                <th>Type</th>
                                                <th>Messages</th>
                                                <th>Frequency</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${detail.topics.map(
                                                (t) => html`
                                                    <tr key=${t.name || t.topic}>
                                                        <td>${t.name || t.topic}</td>
                                                        <td>${t.type || "--"}</td>
                                                        <td>
                                                            ${t.message_count ?? t.messages ?? "--"}
                                                        </td>
                                                        <td>
                                                            ${t.frequency != null
                                                                ? `${t.frequency.toFixed(1)} Hz`
                                                                : "--"}
                                                        </td>
                                                    </tr>
                                                `
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            `
                          : html`
                                <div class="section-empty">
                                    No topic information available
                                </div>
                            `}
                  `
                : html`<div class="section-loading">Loading details...</div>`}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function BagManagerTab() {
    const { showToast } = useToast();
    const { dialog, confirm } = useConfirmDialog();

    // State
    const [recording, setRecording] = useState(null);
    const [bags, setBags] = useState([]);
    const [diskSpace, setDiskSpace] = useState(null);
    const [loading, setLoading] = useState(true);
    const [selectedBag, setSelectedBag] = useState(null);
    const [sortColumn, setSortColumn] = useState("date");
    const [sortAsc, setSortAsc] = useState(false);
    const [selectedProfile, setSelectedProfile] = useState("standard");
    const [elapsedSeconds, setElapsedSeconds] = useState(0);

    const mountedRef = useRef(true);

    // ---- data loading -----------------------------------------------------

    const loadRecordingStatus = useCallback(async () => {
        const data = await safeFetch("/api/bags/record/status");
        if (!mountedRef.current || !data) return;

        const isActive = !!(data.active || data.recording);
        setRecording({
            active: isActive,
            profile: data.profile || null,
            startTime: data.start_time || null,
            estimatedSize: data.estimated_size_bytes ?? null,
        });

        // Extract disk space from the same response if available
        if (data.disk_space_remaining_bytes != null) {
            const available = data.disk_space_remaining_bytes;
            setDiskSpace({
                available,
                total: ASSUMED_TOTAL_DISK_BYTES,
                used: ASSUMED_TOTAL_DISK_BYTES - available,
            });
        }

        // Compute elapsed from start_time
        if (isActive && data.start_time) {
            const startMs =
                typeof data.start_time === "number"
                    ? data.start_time * 1000
                    : new Date(data.start_time).getTime();
            if (!isNaN(startMs)) {
                setElapsedSeconds(Math.floor((Date.now() - startMs) / 1000));
            }
        } else if (!isActive) {
            setElapsedSeconds(0);
        }
    }, []);

    const loadBagList = useCallback(async () => {
        const data = await safeFetch("/api/bags/list");
        if (!mountedRef.current) return;

        if (data) {
            const rawBags = Array.isArray(data) ? data : data.bags || [];
            setBags(rawBags.map(normalizeBag));
        }
        setLoading(false);
    }, []);

    const loadAll = useCallback(async () => {
        await Promise.all([loadRecordingStatus(), loadBagList()]);
    }, [loadRecordingStatus, loadBagList]);

    // ---- actions ----------------------------------------------------------

    const startRecording = useCallback(
        async (profile) => {
            const data = await safeFetch("/api/bags/record/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ profile }),
            });

            if (data) {
                showToast(`Recording started (${profile})`, "success");
                await loadRecordingStatus();
            } else {
                showToast("Failed to start recording", "error");
            }
        },
        [showToast, loadRecordingStatus]
    );

    const stopRecording = useCallback(async () => {
        const data = await safeFetch("/api/bags/record/stop", {
            method: "POST",
        });

        if (data) {
            showToast("Recording stopped", "success");
            setElapsedSeconds(0);
            await loadAll();
        } else {
            showToast("Failed to stop recording", "error");
        }
    }, [showToast, loadAll]);

    const deleteBag = useCallback(
        async (name) => {
            const ok = await confirm({
                title: "Delete Bag",
                message: `Are you sure you want to delete "${name}"? This cannot be undone.`,
                confirmText: "Delete",
                dangerous: true,
            });

            if (!ok) return;

            const data = await safeFetch(`/api/bags/${encodeURIComponent(name)}`, {
                method: "DELETE",
            });

            if (data !== null) {
                showToast(`Bag "${name}" deleted`, "success");
                // Close detail panel if viewing the deleted bag
                setSelectedBag((prev) =>
                    prev && prev.name === name ? null : prev
                );
                await loadBagList();
            } else {
                showToast(`Failed to delete "${name}"`, "error");
            }
        },
        [confirm, showToast, loadBagList]
    );

    const downloadBag = useCallback((name) => {
        const a = document.createElement("a");
        a.href = `/api/bags/${encodeURIComponent(name)}/download`;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }, []);

    const viewBagDetail = useCallback(async (name) => {
        // Show panel immediately with loading state
        setSelectedBag({ name, detail: null });

        const data = await safeFetch(
            `/api/bags/${encodeURIComponent(name)}/info`
        );

        if (!mountedRef.current) return;

        if (data) {
            setSelectedBag({ name, detail: data });
        } else {
            setSelectedBag((prev) =>
                prev && prev.name === name
                    ? { name, detail: { error: true } }
                    : prev
            );
        }
    }, []);

    const closeBagDetail = useCallback(() => {
        setSelectedBag(null);
    }, []);

    // ---- sorting ----------------------------------------------------------

    const handleSort = useCallback(
        (column) => {
            if (sortColumn === column) {
                setSortAsc((prev) => !prev);
            } else {
                setSortColumn(column);
                setSortAsc(true);
            }
        },
        [sortColumn]
    );

    const sortedBags = useMemo(
        () => [...bags].sort(bagComparator(sortColumn, sortAsc)),
        [bags, sortColumn, sortAsc]
    );

    // ---- lifecycle --------------------------------------------------------

    // Initial load + cleanup
    useEffect(() => {
        mountedRef.current = true;
        loadAll();
        return () => {
            mountedRef.current = false;
        };
    }, [loadAll]);

    // 30s polling for list + recording status
    useEffect(() => {
        const id = setInterval(loadAll, POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [loadAll]);

    // 1s timer for recording duration
    useEffect(() => {
        if (!recording || !recording.active) return;

        const id = setInterval(() => {
            setElapsedSeconds((prev) => prev + 1);
        }, TIMER_INTERVAL_MS);

        return () => clearInterval(id);
    }, [recording && recording.active]);

    // ---- render -----------------------------------------------------------

    return html`
        <div class="section-header">
            <h2>Bag Manager</h2>
        </div>

        <${RecordingPanel}
            recording=${recording}
            selectedProfile=${selectedProfile}
            onProfileChange=${setSelectedProfile}
            onStart=${() => startRecording(selectedProfile)}
            onStop=${stopRecording}
            elapsedSeconds=${elapsedSeconds}
        />

        <${DiskSpacePanel} diskSpace=${diskSpace} />

        <div class="stats-panel">
            <h3>Recorded Bags</h3>

            ${loading
                ? html`<div class="section-loading">Loading bags...</div>`
                : sortedBags.length === 0
                  ? html`<div class="section-empty">No recorded bags found</div>`
                  : html`
                        <table class="bag-table">
                            <thead>
                                <tr>
                                    <${SortHeader}
                                        label="Name"
                                        column="name"
                                        sortColumn=${sortColumn}
                                        sortAsc=${sortAsc}
                                        onSort=${handleSort}
                                    />
                                    <${SortHeader}
                                        label="Date"
                                        column="date"
                                        sortColumn=${sortColumn}
                                        sortAsc=${sortAsc}
                                        onSort=${handleSort}
                                    />
                                    <${SortHeader}
                                        label="Duration"
                                        column="duration"
                                        sortColumn=${sortColumn}
                                        sortAsc=${sortAsc}
                                        onSort=${handleSort}
                                    />
                                    <${SortHeader}
                                        label="Size"
                                        column="size"
                                        sortColumn=${sortColumn}
                                        sortAsc=${sortAsc}
                                        onSort=${handleSort}
                                    />
                                    <${SortHeader}
                                        label="Messages"
                                        column="messages"
                                        sortColumn=${sortColumn}
                                        sortAsc=${sortAsc}
                                        onSort=${handleSort}
                                    />
                                    <${SortHeader}
                                        label="Topics"
                                        column="topics"
                                        sortColumn=${sortColumn}
                                        sortAsc=${sortAsc}
                                        onSort=${handleSort}
                                    />
                                    <${SortHeader}
                                        label="Format"
                                        column="format"
                                        sortColumn=${sortColumn}
                                        sortAsc=${sortAsc}
                                        onSort=${handleSort}
                                    />
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${sortedBags.map(
                                    (bag) => html`
                                        <tr
                                            key=${bag.name}
                                            class="bag-row"
                                            onClick=${() => viewBagDetail(bag.name)}
                                            style="cursor: pointer"
                                        >
                                            <td class="bag-name-cell">
                                                ${bag.name}
                                            </td>
                                            <td>${formatDate(bag.date)}</td>
                                            <td>
                                                ${formatDuration(bag.duration)}
                                            </td>
                                            <td>${formatBytes(bag.size)}</td>
                                            <td>
                                                ${bag.messages != null
                                                    ? bag.messages.toLocaleString()
                                                    : "--"}
                                            </td>
                                            <td>
                                                ${bag.topics != null
                                                    ? bag.topics
                                                    : "--"}
                                            </td>
                                            <td>
                                                <span class="bag-format-badge">
                                                    ${bag.format}
                                                </span>
                                            </td>
                                            <td class="bag-actions-cell">
                                                <button
                                                    class="btn btn-sm bag-download-btn"
                                                    onClick=${(e) => {
                                                        e.stopPropagation();
                                                        downloadBag(bag.name);
                                                    }}
                                                    title="Download"
                                                >
                                                    Download
                                                </button>
                                                <button
                                                    class="btn btn-sm btn-danger bag-delete-btn"
                                                    onClick=${(e) => {
                                                        e.stopPropagation();
                                                        deleteBag(bag.name);
                                                    }}
                                                    title="Delete"
                                                >
                                                    Delete
                                                </button>
                                            </td>
                                        </tr>
                                    `
                                )}
                            </tbody>
                        </table>
                    `}
        </div>

        <${BagDetailPanel}
            selectedBag=${selectedBag}
            onClose=${closeBagDetail}
        />

        ${dialog}
    `;
}

// ---------------------------------------------------------------------------
// Register with the Preact app shell
// ---------------------------------------------------------------------------

registerTab("bags", BagManagerTab);

export { BagManagerTab };
