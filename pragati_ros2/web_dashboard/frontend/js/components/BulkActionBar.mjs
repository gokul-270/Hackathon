/**
 * BulkActionBar — Floating bar for fleet-wide bulk actions.
 *
 * Appears when one or more entities are selected in the sidebar.
 * Provides E-Stop, Restart ROS2, Reboot, Shutdown, and Collect Logs
 * actions plus quick-select shortcuts ("all arms", "all online").
 *
 * Reboot and Shutdown require confirmation via {@link useConfirmDialog}.
 * All other actions execute immediately on click.
 *
 * Per-entity progress is shown as status-colored dots during execution.
 * After completion, toast notifications summarise success/failure and
 * failed entities remain selected for retry.
 *
 * @module components/BulkActionBar
 */
import { h } from "preact";
import { useState, useCallback, useContext } from "preact/hooks";
import { html } from "htm/preact";
import { ToastContext } from "../app.js";
import { useConfirmDialog } from "./ConfirmationDialog.mjs";
import { executeBulkAction } from "../utils/bulkActions.js";

// ---------------------------------------------------------------------------
// Status-dot color mapping (used in per-entity progress display)
// ---------------------------------------------------------------------------

/** @type {Record<string, string>} */
const STATUS_DOT_CLASS = {
    pending: "bulk-progress__dot--pending",
    running: "bulk-progress__dot--running",
    fulfilled: "bulk-progress__dot--success",
    rejected: "bulk-progress__dot--failed",
};

// ---------------------------------------------------------------------------
// BulkActionBar component
// ---------------------------------------------------------------------------

/**
 * Floating bulk-action bar displayed when entities are selected.
 *
 * @param {object} props
 * @param {Set<string>}            props.selectedIds       - Currently selected entity IDs.
 * @param {Array<Object>}          props.entities          - Full entity array for filtering/names.
 * @param {() => void}             props.onDeselectAll     - Clear all selections.
 * @param {() => void}             props.onSelectAll       - Select every entity.
 * @param {() => void}             props.onClearSelection  - Alias for onDeselectAll.
 * @param {(ids: Set<string>) => void} props.onSelectionChange - Replace selection with new Set.
 * @param {boolean}                props.executing         - Whether a bulk action is in progress.
 * @param {(v: boolean) => void}   props.onExecutingChange - Toggle executing state in parent.
 * @returns {import('preact').VNode}
 */
function BulkActionBar({
    selectedIds,
    entities,
    onDeselectAll,
    onSelectAll,
    onClearSelection,
    onSelectionChange,
    executing,
    onExecutingChange,
}) {
    const { showToast } = useContext(ToastContext);
    const { dialog, confirm } = useConfirmDialog();

    /** @type {[Record<string, string>, Function]} Per-entity progress map */
    const [progress, setProgress] = useState(/** @type {Record<string, string>} */ ({}));

    const selectedCount = selectedIds.size;
    const totalCount = entities.length;
    const allSelected = totalCount > 0 && selectedCount === totalCount;

    // -------------------------------------------------------------------
    // Action execution
    // -------------------------------------------------------------------

    /**
     * Execute a bulk action with optional confirmation, progress tracking,
     * toast notifications, and partial-deselect on mixed results.
     *
     * @param {string} actionType - Registry key (e.g. "estop", "reboot").
     * @param {string} label      - Human-readable label for toasts.
     */
    async function handleAction(actionType, label) {
        const selectedEntities = entities.filter((e) => selectedIds.has(e.id));
        if (selectedEntities.length === 0) return;

        // -- Confirmation for destructive actions --

        if (actionType === "reboot") {
            const entityNames = selectedEntities.map((e) => e.name || e.id);
            const ok = await confirm({
                title: `Reboot ${selectedEntities.length} entities`,
                message: html`
                    <ul class="confirm-dialog-entity-list">
                        ${entityNames.map((n) => html`<li>${n}</li>`)}
                    </ul>
                `,
                confirmText: "Reboot",
                dangerous: true,
            });
            if (!ok) return;
        }

        if (actionType === "shutdown") {
            const entityNames = selectedEntities.map((e) => e.name || e.id);
            const ok = await confirm({
                title: `Shutdown ${selectedEntities.length} entities`,
                message: html`
                    <ul class="confirm-dialog-entity-list">
                        ${entityNames.map((n) => html`<li>${n}</li>`)}
                    </ul>
                    <div class="confirm-dialog-warning">
                        Shutdown entities will require physical access to restart.
                    </div>
                `,
                confirmText: "Shutdown",
                dangerous: true,
            });
            if (!ok) return;
        }

        // -- Execute --

        onExecutingChange(true);

        const initProgress = {};
        selectedEntities.forEach((e) => {
            initProgress[e.id] = "pending";
        });
        setProgress(initProgress);

        const results = await executeBulkAction(actionType, selectedEntities, {
            onProgress: (entityId, status) => {
                setProgress((prev) => ({ ...prev, [entityId]: status }));
            },
        });

        onExecutingChange(false);

        // -- Toast notifications --

        const succeeded = results.filter((r) => r.status === "fulfilled");
        const failed = results.filter((r) => r.status === "rejected");

        if (failed.length === 0) {
            showToast(`${label}: ${succeeded.length} entities`, "success");
        } else if (succeeded.length === 0) {
            const details = failed.map((f) => `${f.entityName} (${f.reason})`).join(", ");
            showToast(`${label} failed: ${details}`, "error");
        } else {
            const details = failed.map((f) => `${f.entityName} (${f.reason})`).join(", ");
            showToast(
                `${label}: ${succeeded.length} succeeded, ${failed.length} failed: ${details}`,
                "warning",
            );
        }

        // -- Update selection: keep failed entities selected for retry --

        if (failed.length > 0 && succeeded.length > 0) {
            const failedIds = new Set(failed.map((f) => f.entityId));
            onSelectionChange(failedIds);
        } else if (failed.length === 0) {
            onDeselectAll();
        }
        // If all failed, keep selection as-is for retry.

        // Clear progress dots after a brief delay.
        setTimeout(() => setProgress({}), 2000);
    }

    // -------------------------------------------------------------------
    // Quick-select shortcuts
    // -------------------------------------------------------------------

    const handleSelectAllArms = useCallback(() => {
        const armIds = new Set(entities.filter((e) => e.entity_type === "arm").map((e) => e.id));
        onSelectionChange(armIds);
    }, [entities, onSelectionChange]);

    const handleSelectAllOnline = useCallback(() => {
        const onlineIds = new Set(
            entities.filter((e) => e.status === "online").map((e) => e.id),
        );
        onSelectionChange(onlineIds);
    }, [entities, onSelectionChange]);

    // -------------------------------------------------------------------
    // Per-entity progress display
    // -------------------------------------------------------------------

    const progressKeys = Object.keys(progress);
    const showProgress = progressKeys.length > 0;
    const resolvedCount = progressKeys.filter(
        (id) => progress[id] === "fulfilled" || progress[id] === "rejected",
    ).length;

    // -------------------------------------------------------------------
    // Render
    // -------------------------------------------------------------------

    return html`
        <div class="bulk-action-bar">
            <!-- Select All / Deselect All toggle -->
            <div class="bulk-action-bar__section">
                <button
                    class="bulk-action-bar__button--shortcut"
                    disabled=${executing}
                    onClick=${allSelected ? onDeselectAll : onSelectAll}
                >
                    ${allSelected ? "Deselect All" : "Select All"}
                </button>
            </div>

            <!-- Selection count badge -->
            <span class="bulk-action-bar__count">
                ${selectedCount} of ${totalCount} selected
            </span>

            <span class="bulk-action-bar__divider"></span>

            <!-- Action buttons -->
            <div class="bulk-action-bar__section--actions">
                <button
                    class="bulk-action-bar__button--danger"
                    disabled=${executing}
                    onClick=${() => handleAction("estop", "E-Stop")}
                >
                    E-Stop
                </button>
                <button
                    class="bulk-action-bar__button--warning"
                    disabled=${executing}
                    onClick=${() => handleAction("restart-ros2", "Restart ROS2")}
                >
                    Restart ROS2
                </button>
                <button
                    class="bulk-action-bar__button--warning"
                    disabled=${executing}
                    onClick=${() => handleAction("reboot", "Reboot")}
                >
                    Reboot
                </button>
                <button
                    class="bulk-action-bar__button--danger-outline"
                    disabled=${executing}
                    onClick=${() => handleAction("shutdown", "Shutdown")}
                >
                    Shutdown
                </button>
                <button
                    class="bulk-action-bar__button--neutral"
                    disabled=${executing}
                    onClick=${() => handleAction("collect-logs", "Collect Logs")}
                >
                    Collect Logs
                </button>
                <button
                    class="bulk-action-bar__button--neutral"
                    disabled=${executing}
                    onClick=${() => handleAction("time-sync", "Time Sync")}
                >
                    Time Sync
                </button>
            </div>

            <span class="bulk-action-bar__divider"></span>

            <!-- Quick-select shortcuts -->
            <div class="bulk-action-bar__section--shortcuts">
                <button
                    class="bulk-action-bar__button--shortcut"
                    disabled=${executing}
                    onClick=${handleSelectAllArms}
                >
                    Select all arms
                </button>
                <button
                    class="bulk-action-bar__button--shortcut"
                    disabled=${executing}
                    onClick=${handleSelectAllOnline}
                >
                    Select all online
                </button>
            </div>

            ${showProgress &&
            html`
                <div class="bulk-progress">
                    <span class="bulk-progress__counter">
                        ${resolvedCount}/${progressKeys.length} complete
                    </span>
                    ${progressKeys.map(
                        (id) => html`
                            <span
                                class="bulk-progress__dot ${STATUS_DOT_CLASS[progress[id]] || ""}"
                                title="${id}: ${progress[id]}"
                            ></span>
                        `,
                    )}
                </div>
            `}

            ${dialog}
        </div>
    `;
}

export { BulkActionBar };
