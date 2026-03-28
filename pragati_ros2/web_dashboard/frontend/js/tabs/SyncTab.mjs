/**
 * SyncTab — Preact component for the Sync & Deploy tab.
 *
 * Migrated from vanilla JS (sync_control.js) as part of the incremental
 * Preact migration (task 6.4).
 *
 * @module tabs/SyncTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useRef } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { useConfirmDialog } from "../components/ConfirmationDialog.mjs";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 3000;
const TIMER_INTERVAL_MS = 1000;
const MAX_OUTPUT_LINES = 1000;

/** @type {Array<{value: string, label: string}>} */
const OPERATIONS = [
    { value: "deploy-cross", label: "Deploy Cross-compiled" },
    { value: "deploy-local", label: "Deploy Local Build" },
    { value: "build", label: "Sync Source & Build" },
    { value: "provision", label: "Provision Target" },
    { value: "collect-logs", label: "Collect Logs" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Validate an IPv4 address (4 octets, 0-255, no leading zeros).
 * @param {string} ip
 * @returns {boolean}
 */
function validateIp(ip) {
    if (!ip) return false;
    const parts = ip.split(".");
    if (parts.length !== 4) return false;
    return parts.every((part) => {
        const num = parseInt(part, 10);
        return !isNaN(num) && num >= 0 && num <= 255 && String(num) === part;
    });
}

/**
 * Format elapsed seconds as MM:SS.
 * @param {number} seconds
 * @returns {string}
 */
function formatElapsed(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function SyncTab() {
    const { showToast } = useToast();
    const { dialog, confirm, doubleConfirm } = useConfirmDialog();

    // ---- state -----------------------------------------------------------

    const [available, setAvailable] = useState(/** @type {boolean|null} */ (null));
    const [recentIps, setRecentIps] = useState(/** @type {string[]} */ ([]));
    const [operation, setOperation] = useState("");
    const [targetIp, setTargetIp] = useState("");
    const [status, setStatus] = useState("idle");
    const [output, setOutput] = useState(/** @type {string[]} */ ([]));
    const [elapsed, setElapsed] = useState(0);
    const [running, setRunning] = useState(false);

    // ---- refs ------------------------------------------------------------

    const wsRef = useRef(/** @type {WebSocket|null} */ (null));
    const pollRef = useRef(/** @type {number|null} */ (null));
    const timerRef = useRef(/** @type {number|null} */ (null));
    const outputRef = useRef(/** @type {HTMLDivElement|null} */ (null));
    const mountedRef = useRef(true);

    // ---- cleanup on unmount ----------------------------------------------

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
            closeWs();
            stopPolling();
            stopTimer();
        };
    }, []);

    // ---- data loading on mount -------------------------------------------

    useEffect(() => {
        checkAvailability();
        loadConfig();
    }, []);

    // ---- auto-scroll output ----------------------------------------------

    useEffect(() => {
        if (outputRef.current) {
            outputRef.current.scrollTop = outputRef.current.scrollHeight;
        }
    }, [output]);

    // ---- API functions ---------------------------------------------------

    async function checkAvailability() {
        const data = await safeFetch("/api/sync/available");
        if (!mountedRef.current) return;
        setAvailable(!!(data && data.available));
    }

    async function loadConfig() {
        const data = await safeFetch("/api/sync/config");
        if (!mountedRef.current) return;
        if (data && Array.isArray(data.target_ips)) {
            setRecentIps(data.target_ips);
        }
    }

    /**
     * Save a recently-used IP to the server config.
     * @param {string} ip
     * @param {string[]} currentIps
     */
    async function saveRecentIp(ip, currentIps) {
        const updated = [ip, ...currentIps.filter((i) => i !== ip)].slice(0, 5);
        if (mountedRef.current) setRecentIps(updated);
        await safeFetch("/api/sync/config", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_ips: updated }),
        });
    }

    // ---- WebSocket output streaming --------------------------------------

    function connectWs() {
        closeWs();
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${proto}//${location.host}/ws/sync/output`;

        try {
            const ws = new WebSocket(wsUrl);

            ws.onmessage = (event) => {
                if (!mountedRef.current) return;
                let text;
                try {
                    const data = JSON.parse(event.data);
                    text = data.text || data.line || String(event.data);
                } catch (_e) {
                    text = String(event.data);
                }
                setOutput((prev) => {
                    const next = [...prev, text];
                    if (next.length > MAX_OUTPUT_LINES) {
                        return next.slice(next.length - MAX_OUTPUT_LINES);
                    }
                    return next;
                });
            };

            ws.onerror = () => {
                console.error("[SyncTab] WS error");
            };

            ws.onclose = () => {
                console.log("[SyncTab] WS closed");
            };

            wsRef.current = ws;
        } catch (err) {
            console.error("[SyncTab] failed to create WS:", err);
        }
    }

    function closeWs() {
        if (wsRef.current) {
            wsRef.current.onmessage = null;
            wsRef.current.onerror = null;
            wsRef.current.onclose = null;
            wsRef.current.close();
            wsRef.current = null;
        }
    }

    // ---- status polling --------------------------------------------------

    function startPolling() {
        stopPolling();
        pollRef.current = setInterval(() => pollStatus(), POLL_INTERVAL_MS);
    }

    function stopPolling() {
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }
    }

    async function pollStatus() {
        const data = await safeFetch("/api/sync/status");
        if (!mountedRef.current) return;
        if (data && typeof data.running === "boolean") {
            setStatus(data.running ? "running" : "idle");
            if (!data.running) {
                stopPolling();
                stopTimer();
                setRunning(false);
            }
        }
    }

    // ---- elapsed timer ---------------------------------------------------

    function startTimer() {
        stopTimer();
        setElapsed(0);
        const startTime = Date.now();
        timerRef.current = setInterval(() => {
            if (!mountedRef.current) return;
            setElapsed(Math.floor((Date.now() - startTime) / 1000));
        }, TIMER_INTERVAL_MS);
    }

    function stopTimer() {
        if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }
    }

    // ---- actions ---------------------------------------------------------

    const runSync = useCallback(async () => {
        if (!operation) {
            showToast("Please select an operation", "error");
            return;
        }
        if (!targetIp || !validateIp(targetIp)) {
            showToast("Please enter a valid IP address", "error");
            return;
        }

        // Confirmation dialog — double-confirm for provision
        let confirmed;
        if (operation === "provision") {
            confirmed = await doubleConfirm({
                title: "Provision Target",
                message:
                    `This will apply OS-level changes to ${targetIp}. ` +
                    "This operation modifies system configuration and installs packages.",
                confirmWord: "PROVISION",
                confirmWordPrompt: "Type PROVISION to confirm",
                confirmText: "Provision",
                dangerous: true,
            });
        } else {
            confirmed = await confirm({
                title: `Run Sync: ${operation}`,
                message: `Run "${operation}" against ${targetIp}?`,
                confirmText: "Run",
                dangerous: false,
            });
        }
        if (!confirmed) return;

        // Clear previous output
        setOutput([]);

        const result = await safeFetch("/api/sync/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ operation, target_ip: targetIp }),
        });

        if (result && !result.error) {
            showToast(`Sync "${operation}" started`, "success");
            saveRecentIp(targetIp, recentIps);
            setRunning(true);
            setStatus("running");
            connectWs();
            startPolling();
            startTimer();
        } else {
            showToast(
                (result && result.error) || "Failed to start sync",
                "error",
            );
        }
    }, [operation, targetIp, recentIps, showToast, confirm, doubleConfirm]);

    const cancelSync = useCallback(async () => {
        const result = await safeFetch("/api/sync/cancel", {
            method: "POST",
        });

        if (result && !result.error) {
            showToast("Sync cancelled", "info");
            stopTimer();
            setRunning(false);
        } else {
            showToast(
                (result && result.error) || "Failed to cancel sync",
                "error",
            );
        }
    }, [showToast]);

    const clearOutput = useCallback(() => {
        setOutput([]);
    }, []);

    const onRecentIpChange = useCallback(
        (e) => {
            const val = e.target.value;
            if (val) {
                setTargetIp(val);
                e.target.value = "";
            }
        },
        [],
    );

    // ---- status indicator class ------------------------------------------

    const statusClass =
        status === "running"
            ? "sync-status-running"
            : status === "completed"
              ? "sync-status-idle"
              : status === "failed"
                ? "sync-status-running"
                : "sync-status-idle";

    const statusLabel =
        status === "running"
            ? "Running"
            : status === "completed"
              ? "Completed"
              : status === "failed"
                ? "Failed"
                : "Idle";

    // ---- render ----------------------------------------------------------

    // Loading state
    if (available === null) {
        return html`<div class="text-muted">Checking sync availability...</div>`;
    }

    // Unavailable state
    if (!available) {
        return html`
            <div class="sync-unavailable">
                <p>sync.sh is not available on this server.</p>
                <p>
                    Sync operations require the sync.sh script to be present
                    in the repository root.
                </p>
            </div>
            ${dialog}
        `;
    }

    // Available — full UI
    return html`
        <div class="sync-panel-header">
            <h3>Sync Control</h3>
            <span class=${statusClass}>${statusLabel}</span>
        </div>
        <div class="sync-panel-controls">
            <div class="sync-form-row">
                <label for="sync-operation-preact">Operation:</label>
                <select
                    id="sync-operation-preact"
                    class="sync-select"
                    value=${operation}
                    onChange=${(e) => setOperation(e.target.value)}
                >
                    <option value="">-- Select --</option>
                    ${OPERATIONS.map(
                        (op) => html`
                            <option value=${op.value}>${op.label}</option>
                        `,
                    )}
                </select>
            </div>
            <div class="sync-form-row">
                <label for="sync-target-ip-preact">Target IP:</label>
                <div class="sync-ip-group">
                    <input
                        type="text"
                        id="sync-target-ip-preact"
                        placeholder="192.168.1.x"
                        class="sync-input"
                        value=${targetIp}
                        onInput=${(e) => setTargetIp(e.target.value.trim())}
                    />
                    <select
                        class="sync-select sync-recent-ips-select"
                        onChange=${onRecentIpChange}
                    >
                        <option value="">Recent IPs...</option>
                        ${recentIps.map(
                            (ip) => html`
                                <option value=${ip}>${ip}</option>
                            `,
                        )}
                    </select>
                </div>
            </div>
            <div class="sync-panel-buttons">
                ${running
                    ? html`
                          <button
                              class="btn btn-danger"
                              onClick=${cancelSync}
                          >
                              Cancel
                          </button>
                      `
                    : html`
                          <button
                              class="btn btn-primary"
                              onClick=${runSync}
                          >
                              Run
                          </button>
                      `}
            </div>
            ${running &&
            html`
                <div class="sync-elapsed">
                    Elapsed: <span>${formatElapsed(elapsed)}</span>
                </div>
            `}
        </div>
        <div class="sync-output-panel">
            <div class="sync-output-header">
                <span>Output</span>
                <button class="btn btn-sm" onClick=${clearOutput}>
                    Clear
                </button>
            </div>
            <div class="sync-output-terminal" ref=${outputRef}>
                ${output.map(
                    (line, i) => html`
                        <div class="output-line" key=${i}>${line}</div>
                    `,
                )}
            </div>
        </div>
        ${dialog}
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("sync-deploy", SyncTab);

export { SyncTab };
