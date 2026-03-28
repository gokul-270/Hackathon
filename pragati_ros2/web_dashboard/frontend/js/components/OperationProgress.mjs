/**
 * OperationProgress — displays per-entity status badges for multi-target
 * operations (deploy, sync, provision, etc.) and a batch completion summary.
 *
 * Tasks 5.1: Per-entity status badges with color-coded status indicators.
 * Tasks 5.2: Batch completion summary bar when all targets finish.
 *
 * @module components/OperationProgress
 */
import { h } from "preact";
import { useMemo } from "preact/hooks";
import { html } from "htm/preact";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** @type {Record<string, string>} Status to color mapping */
const STATUS_COLORS = {
    pending: "var(--color-text-muted)",
    running: "var(--color-accent)",
    success: "var(--color-success)",
    failed: "var(--color-error)",
    cancelled: "var(--color-warning)",
    timeout: "var(--color-warning)",
};

/** @type {Record<string, string>} Human-readable status labels */
const STATUS_LABELS = {
    pending: "Pending",
    running: "Running",
    success: "Success",
    failed: "Failed",
    cancelled: "Cancelled",
    timeout: "Timeout",
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const CONTAINER_STYLE = {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    width: "100%",
};

const BADGE_ROW_STYLE = {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px",
    alignItems: "center",
};

const BADGE_BASE_STYLE = {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    padding: "4px 10px",
    borderRadius: "4px",
    fontSize: "12px",
    fontFamily: "monospace",
    color: "#fff",
    lineHeight: "1.4",
    whiteSpace: "nowrap",
    transition: "box-shadow 0.2s ease",
};

const PULSE_KEYFRAMES = `
@keyframes op-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
`;

const PULSE_DOT_STYLE = {
    display: "inline-block",
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    backgroundColor: "#fff",
    animation: "op-pulse 1.2s ease-in-out infinite",
};

const SUMMARY_BASE_STYLE = {
    padding: "6px 12px",
    borderRadius: "4px",
    fontSize: "13px",
    fontWeight: "600",
    color: "#fff",
    textAlign: "center",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Single status badge for one target entity.
 *
 * @param {object} props
 * @param {string} props.target_id - Entity identifier (e.g. "arm-1")
 * @param {string} props.ip        - IP address of the target
 * @param {string} props.status    - One of pending|running|success|failed|cancelled|timeout
 */
function StatusBadge({ target_id, ip, status }) {
    const bgColor = STATUS_COLORS[status] || STATUS_COLORS.pending;
    const label = STATUS_LABELS[status] || status;
    const isRunning = status === "running";

    const badgeStyle = {
        ...BADGE_BASE_STYLE,
        backgroundColor: bgColor,
        boxShadow: isRunning ? `0 0 0 2px ${bgColor}44, 0 0 8px ${bgColor}66` : "none",
    };

    return html`
        <span style=${badgeStyle} title="${target_id} (${ip}) — ${label}">
            ${isRunning && html`<span style=${PULSE_DOT_STYLE}></span>`}
            <span style=${{ fontWeight: 600 }}>${target_id}</span>
            <span style=${{ opacity: 0.75, fontSize: "11px" }}>${ip}</span>
            <span style=${{
                backgroundColor: "rgba(0,0,0,0.2)",
                padding: "1px 5px",
                borderRadius: "3px",
                fontSize: "10px",
                textTransform: "uppercase",
                letterSpacing: "0.5px",
            }}>${label}</span>
        </span>
    `;
}

/**
 * Batch completion summary shown when all targets have finished.
 *
 * @param {object} props
 * @param {object} props.counts - { total, success, failed, cancelled, timeout }
 */
function CompletionSummary({ counts }) {
    const { total, success, failed, cancelled, timeout } = counts;

    let bgColor;
    if (failed > 0) {
        bgColor = STATUS_COLORS.failed;
    } else if (success === total) {
        bgColor = STATUS_COLORS.success;
    } else {
        bgColor = STATUS_COLORS.timeout;
    }

    const parts = [];
    parts.push(`${success}/${total} succeeded`);
    if (failed > 0) parts.push(`${failed} failed`);
    if (cancelled > 0) parts.push(`${cancelled} cancelled`);
    if (timeout > 0) parts.push(`${timeout} timed out`);

    const summaryStyle = { ...SUMMARY_BASE_STYLE, backgroundColor: bgColor };

    return html`
        <div style=${summaryStyle}>${parts.join(", ")}</div>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * OperationProgress — renders a row of per-target status badges and,
 * once all targets are done, a batch completion summary bar.
 *
 * @param {object} props
 * @param {Array<{target_id: string, ip: string, status: string, exit_code?: number}>} props.targets
 *   Array of target status objects.
 * @param {boolean} props.isComplete
 *   True when the entire operation has finished (no pending/running targets).
 * @returns {import('preact').VNode}
 */
function OperationProgress({ targets = [], isComplete = false }) {
    const counts = useMemo(() => {
        const c = { total: targets.length, success: 0, failed: 0, cancelled: 0, timeout: 0 };
        for (const t of targets) {
            if (t.status === "success") c.success++;
            else if (t.status === "failed") c.failed++;
            else if (t.status === "cancelled") c.cancelled++;
            else if (t.status === "timeout") c.timeout++;
        }
        return c;
    }, [targets]);

    if (targets.length === 0) {
        return html`<div style=${{ color: "var(--color-text-muted)", fontSize: "13px" }}>No targets</div>`;
    }

    return html`
        <style>${PULSE_KEYFRAMES}</style>
        <div style=${CONTAINER_STYLE}>
            <div style=${BADGE_ROW_STYLE}>
                ${targets.map(
                    (t) => html`
                        <${StatusBadge}
                            key=${t.target_id}
                            target_id=${t.target_id}
                            ip=${t.ip}
                            status=${t.status}
                        />
                    `,
                )}
            </div>
            ${isComplete && html`<${CompletionSummary} counts=${counts} />`}
        </div>
    `;
}

export { OperationProgress };
