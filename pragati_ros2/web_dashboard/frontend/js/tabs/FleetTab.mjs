/**
 * FleetTab — Preact component for the Fleet Hub tab.
 *
 * Shows RPi fleet members as cards with CPU/memory bars, status indicators,
 * and drill-down links. Supports fleet-wide sync and log collection jobs.
 *
 * @module tabs/FleetTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useRef } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Poll interval for fleet status (ms). */
const FLEET_POLL_INTERVAL_MS = 10000;

/** Poll interval for active job progress (ms). */
const JOB_POLL_INTERVAL_MS = 3000;

/** Dashboard port for drill-down links. */
const DASHBOARD_PORT = 8090;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a last_seen timestamp for display.
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
 * CSS class for a status indicator dot.
 * @param {string} status
 * @returns {string}
 */
function statusDotClass(status) {
    const s = (status || "unknown").toLowerCase();
    if (s === "online") return "fleet-status-dot fleet-status-online";
    if (s === "offline") return "fleet-status-dot fleet-status-offline";
    return "fleet-status-dot fleet-status-unknown";
}

/**
 * Clamp a number to 0–100 for progress bar width.
 * @param {number|null|undefined} val
 * @returns {number}
 */
function clampPercent(val) {
    if (val == null || isNaN(val)) return 0;
    return Math.max(0, Math.min(100, val));
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * CPU/Memory progress bar.
 * @param {object} props
 * @param {string} props.label
 * @param {number|null} props.percent
 */
function ResourceBar({ label, percent }) {
    const value = clampPercent(percent);
    const barClass = value > 90
        ? "fleet-resource-fill fleet-resource-critical"
        : value > 70
            ? "fleet-resource-fill fleet-resource-warning"
            : "fleet-resource-fill";

    return html`
        <div class="fleet-resource-bar">
            <div class="fleet-resource-label">
                <span>${label}</span>
                <span>${percent != null ? `${percent.toFixed(1)}%` : "--"}</span>
            </div>
            <div class="fleet-resource-track">
                <div class=${barClass} style="width: ${value}%"></div>
            </div>
        </div>
    `;
}

/**
 * A single RPi fleet member card.
 */
function RpiCard({ member, onDrillDown }) {
    const status = (member.status || "unknown").toLowerCase();
    const isArm = (member.role || "").toLowerCase() === "arm";

    return html`
        <div class="fleet-rpi-card">
            <div
                class="fleet-rpi-card-header"
                onClick=${() => onDrillDown(member)}
                title="Open dashboard on ${member.name}"
                style="cursor: pointer;"
            >
                <div class="fleet-rpi-card-title">
                    <span class=${statusDotClass(status)}></span>
                    <span class="fleet-rpi-name">${member.name || "Unknown"}</span>
                </div>
                <span class="fleet-role-badge fleet-role-${(member.role || "unknown").toLowerCase()}">
                    ${member.role || "unknown"}
                </span>
            </div>
            <div class="fleet-rpi-card-body">
                <div class="fleet-rpi-info-row">
                    <span class="fleet-rpi-info-label">IP:</span>
                    <span class="fleet-rpi-info-value">${member.ip || "--"}</span>
                </div>
                <div class="fleet-rpi-info-row">
                    <span class="fleet-rpi-info-label">Status:</span>
                    <span class="fleet-rpi-info-value">${status}</span>
                </div>
                <div class="fleet-rpi-info-row">
                    <span class="fleet-rpi-info-label">Last seen:</span>
                    <span class="fleet-rpi-info-value">${formatLastSeen(member.last_seen)}</span>
                </div>
                <${ResourceBar} label="CPU" percent=${member.cpu_percent} />
                <${ResourceBar} label="Memory" percent=${member.memory_percent} />
                ${isArm && html`
                    <div class="fleet-rpi-info-row">
                        <span class="fleet-rpi-info-label">State:</span>
                        <span class="fleet-rpi-info-value">
                            ${member.operational_state || "--"}
                        </span>
                    </div>
                    <div class="fleet-rpi-info-row">
                        <span class="fleet-rpi-info-label">Picks:</span>
                        <span class="fleet-rpi-info-value">
                            ${member.pick_count != null ? member.pick_count : "--"}
                        </span>
                    </div>
                `}
            </div>
        </div>
    `;
}

/**
 * Job progress display — shows per-member status during sync/logs jobs.
 */
function JobProgress({ job }) {
    if (!job) return null;

    const typeLabel = job.type === "sync" ? "Sync" : "Log Collection";
    const members = job.members || {};
    const memberNames = Object.keys(members);
    const completedCount = memberNames.filter(
        (n) => members[n].status === "completed" || members[n].status === "failed"
    ).length;
    const totalCount = memberNames.length;
    const percent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

    return html`
        <div class="fleet-job-progress">
            <div class="fleet-job-header">
                <span class="fleet-job-title">${typeLabel} Job</span>
                <span class="fleet-job-status fleet-job-status-${job.status}">
                    ${job.status}
                </span>
            </div>
            <div class="fleet-resource-track">
                <div
                    class="fleet-resource-fill"
                    style="width: ${percent}%"
                ></div>
            </div>
            <div class="fleet-job-detail">
                ${percent}% (${completedCount}/${totalCount} members)
            </div>
            <div class="fleet-job-members">
                ${memberNames.map((name) => {
                    const m = members[name];
                    return html`
                        <div class="fleet-job-member" key=${name}>
                            <span class="fleet-job-member-name">${name}</span>
                            <span class="fleet-job-member-status fleet-job-member-${m.status}">
                                ${m.status}
                            </span>
                            ${m.status === "failed" && m.output && html`
                                <span class="fleet-job-member-error" title=${m.output}>
                                    Error
                                </span>
                            `}
                        </div>
                    `;
                })}
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function FleetTab() {
    const { showToast } = useToast();

    // -- fleet state --------------------------------------------------------
    const [members, setMembers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // -- job state ----------------------------------------------------------
    const [activeJob, setActiveJob] = useState(null);
    const [jobSubmitting, setJobSubmitting] = useState(false);

    // -- refs for cleanup ---------------------------------------------------
    const mountedRef = useRef(true);
    const jobPollRef = useRef(null);

    // ---- data loading -----------------------------------------------------

    const loadFleetStatus = useCallback(async () => {
        const result = await safeFetch("/api/fleet/status");

        if (!mountedRef.current) return;

        if (!result) {
            setError("Failed to fetch fleet status");
            setLoading(false);
            return;
        }

        if (result.error) {
            setError(result.error);
            setLoading(false);
            return;
        }

        setMembers(result.members || []);
        setError(null);
        setLoading(false);
    }, []);

    // ---- job polling ------------------------------------------------------

    const pollJob = useCallback(async (jobId) => {
        const result = await safeFetch(`/api/fleet/jobs/${encodeURIComponent(jobId)}`);

        if (!mountedRef.current) return;

        if (!result) {
            // Lost contact with job — stop polling
            setActiveJob(null);
            return;
        }

        setActiveJob(result);

        // Stop polling when job is terminal
        if (result.status === "completed" || result.status === "partial_failure") {
            if (jobPollRef.current) {
                clearInterval(jobPollRef.current);
                jobPollRef.current = null;
            }
            const label = result.type === "sync" ? "Sync" : "Log collection";
            if (result.status === "completed") {
                showToast(`${label} completed successfully`, "success");
            } else {
                showToast(`${label} completed with failures`, "warning");
            }
        }
    }, [showToast]);

    const startJobPolling = useCallback((jobId) => {
        // Clear any existing job poll
        if (jobPollRef.current) {
            clearInterval(jobPollRef.current);
        }
        // Initial poll
        pollJob(jobId);
        // Continue polling
        jobPollRef.current = setInterval(() => pollJob(jobId), JOB_POLL_INTERVAL_MS);
    }, [pollJob]);

    // ---- actions ----------------------------------------------------------

    const handleSyncAll = useCallback(async () => {
        if (jobSubmitting || (activeJob && activeJob.status === "running")) return;

        setJobSubmitting(true);
        const result = await safeFetch("/api/fleet/sync", { method: "POST" });

        if (!mountedRef.current) return;
        setJobSubmitting(false);

        if (!result || !result.job_id) {
            showToast("Failed to start sync job", "error");
            return;
        }

        showToast("Sync job started", "info");
        setActiveJob({ job_id: result.job_id, type: "sync", status: "running", members: {} });
        startJobPolling(result.job_id);
    }, [jobSubmitting, activeJob, showToast, startJobPolling]);

    const handleCollectLogs = useCallback(async () => {
        if (jobSubmitting || (activeJob && activeJob.status === "running")) return;

        setJobSubmitting(true);
        const result = await safeFetch("/api/fleet/logs", { method: "POST" });

        if (!mountedRef.current) return;
        setJobSubmitting(false);

        if (!result || !result.job_id) {
            showToast("Failed to start log collection", "error");
            return;
        }

        showToast("Log collection started", "info");
        setActiveJob({ job_id: result.job_id, type: "logs", status: "running", members: {} });
        startJobPolling(result.job_id);
    }, [jobSubmitting, activeJob, showToast, startJobPolling]);

    const handleDrillDown = useCallback((member) => {
        if (!member.ip) {
            showToast("No IP address available for this member", "warning");
            return;
        }
        const status = (member.status || "unknown").toLowerCase();
        if (status === "offline") {
            showToast(
                `${member.name} is offline — dashboard may not be reachable`,
                "warning"
            );
        }
        window.open(`http://${member.ip}:${DASHBOARD_PORT}`, "_blank");
    }, [showToast]);

    // ---- lifecycle --------------------------------------------------------

    // Initial load
    useEffect(() => {
        mountedRef.current = true;
        loadFleetStatus();

        return () => {
            mountedRef.current = false;
            if (jobPollRef.current) {
                clearInterval(jobPollRef.current);
                jobPollRef.current = null;
            }
        };
    }, [loadFleetStatus]);

    // Periodic fleet status polling
    useEffect(() => {
        const id = setInterval(loadFleetStatus, FLEET_POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [loadFleetStatus]);

    // ---- render -----------------------------------------------------------

    const jobIsRunning = activeJob && activeJob.status === "running";
    const onlineCount = members.filter(
        (m) => (m.status || "").toLowerCase() === "online"
    ).length;

    return html`
        <div class="fleet-container">
            <div class="fleet-header">
                <h2>Fleet Hub</h2>
                <span class="fleet-summary">
                    ${members.length > 0
                        ? `${onlineCount}/${members.length} online`
                        : ""}
                </span>
            </div>

            <div class="fleet-actions">
                <button
                    class="btn fleet-sync-btn"
                    onClick=${handleSyncAll}
                    disabled=${jobSubmitting || jobIsRunning}
                >
                    ${jobSubmitting ? "Starting..." : "Sync All"}
                </button>
                <button
                    class="btn fleet-logs-btn"
                    onClick=${handleCollectLogs}
                    disabled=${jobSubmitting || jobIsRunning}
                >
                    ${jobSubmitting ? "Starting..." : "Collect Logs"}
                </button>
            </div>

            ${activeJob && html`<${JobProgress} job=${activeJob} />`}

            ${loading && html`<div class="loading">Loading fleet status...</div>`}

            ${!loading && error && html`
                <div class="fleet-error">${error}</div>
            `}

            ${!loading && !error && members.length === 0 && html`
                <div class="fleet-empty">
                    No fleet configured. Add fleet members to dashboard.yaml.
                </div>
            `}

            ${!loading && !error && members.length > 0 && html`
                <div class="fleet-rpi-grid">
                    ${members.map(
                        (member) => html`
                            <${RpiCard}
                                key=${member.name || member.ip}
                                member=${member}
                                onDrillDown=${handleDrillDown}
                            />
                        `
                    )}
                </div>
            `}
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("fleet", FleetTab);

export default FleetTab;
