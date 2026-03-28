/**
 * Bulk action execution utility for the Pragati Dashboard.
 *
 * Provides a registry-driven approach to executing fleet-wide or
 * per-entity actions (e-stop, reboot, log collection, etc.) against
 * the backend API. All HTTP calls go through {@link safeFetch} so
 * errors are surfaced via the toast system rather than thrown.
 *
 * @module utils/bulkActions
 */

import { safeFetch } from "../utils.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Polling interval (ms) for async job status checks. */
const JOB_POLL_INTERVAL_MS = 2000;

/** Maximum number of polling attempts before giving up on a job. */
const JOB_POLL_MAX_ATTEMPTS = 150; // 5 minutes at 2 s intervals

// ---------------------------------------------------------------------------
// Service-name mapping
// ---------------------------------------------------------------------------

/**
 * Map an entity to the systemd service name used by the restart-ros2 action.
 *
 * @param {{ entity_type: string }} entity - Entity object with at least `entity_type`.
 * @returns {string|null} Service name, or `null` if the entity type is unrecognised.
 *
 * @example
 * getServiceName({ entity_type: "arm" });     // "arm_launch"
 * getServiceName({ entity_type: "vehicle" }); // "vehicle_launch"
 * getServiceName({ entity_type: "foo" });     // null
 */
export function getServiceName(entity) {
    switch (entity.entity_type) {
        case "arm":
            return "arm_launch";
        case "vehicle":
            return "vehicle_launch";
        default:
            return null;
    }
}

// ---------------------------------------------------------------------------
// Action registry
// ---------------------------------------------------------------------------

/**
 * @typedef {Object} ActionDefinition
 * @property {(entity: Object) => string} endpoint  - Returns the URL path for this entity.
 * @property {string}                     method    - HTTP method (e.g. "POST").
 * @property {((entity: Object) => Object)|undefined} body - Optional body builder.
 * @property {string}                     label     - Human-readable action name for UI/logging.
 */

/**
 * Registry mapping action-type strings to their API definitions.
 *
 * Every entry satisfies {@link ActionDefinition}. The `endpoint` function
 * receives the full entity object so it can reference `entity.id`,
 * `entity.entity_type`, etc.
 *
 * **Note:** `collect-logs` is a fleet-wide action handled as a special case
 * inside {@link executeBulkAction}; it is listed here only for label lookup.
 *
 * @type {Record<string, ActionDefinition>}
 */
const ACTION_REGISTRY = {
    estop: {
        endpoint: (entity) => `/api/entities/${entity.id}/estop`,
        method: "POST",
        body: undefined,
        label: "Emergency Stop",
    },

    "restart-ros2": {
        endpoint: (entity) => {
            const svc = getServiceName(entity);
            return `/api/entities/${entity.id}/system/services/${svc}/restart`;
        },
        method: "POST",
        body: undefined,
        label: "Restart ROS2",
    },

    reboot: {
        endpoint: (entity) => `/api/entities/${entity.id}/system/reboot`,
        method: "POST",
        body: () => ({ token: "REBOOT" }),
        label: "Reboot",
    },

    shutdown: {
        endpoint: (entity) => `/api/entities/${entity.id}/system/shutdown`,
        method: "POST",
        body: () => ({ token: "SHUTDOWN" }),
        label: "Shutdown",
    },

    "collect-logs": {
        // Fleet-wide — endpoint/body are not used per-entity.
        endpoint: () => "/api/fleet/logs",
        method: "POST",
        body: undefined,
        label: "Collect Logs",
    },

    "time-sync": {
        // Uses the operations API to run sync.sh --time-sync per entity.
        endpoint: () => "/api/operations/run",
        method: "POST",
        body: (entity) => ({
            operation: "time-sync",
            target_ids: [entity.id],
            params: {},
        }),
        label: "Time Sync",
    },
};

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Execute a single per-entity action via safeFetch.
 *
 * @param {ActionDefinition} action - Resolved action from the registry.
 * @param {Object}           entity - Entity object (must have `.id` and `.name`).
 * @returns {Promise<{ entityId: string, entityName: string, status: "fulfilled"|"rejected", value?: any, reason?: string }>}
 * @private
 */
async function executeOneEntity(action, entity) {
    const url = action.endpoint(entity);
    const fetchOpts = { method: action.method };

    if (typeof action.body === "function") {
        fetchOpts.headers = { "Content-Type": "application/json" };
        fetchOpts.body = JSON.stringify(action.body(entity));
    }

    const result = await safeFetch(url, fetchOpts);

    if (result === null) {
        return {
            entityId: entity.id,
            entityName: entity.name ?? entity.id,
            status: "rejected",
            reason: `${action.label} failed for ${entity.name ?? entity.id}`,
        };
    }

    return {
        entityId: entity.id,
        entityName: entity.name ?? entity.id,
        status: "fulfilled",
        value: result,
    };
}

/**
 * Poll an async job until it reaches a terminal state.
 *
 * @param {string} jobId - Job identifier returned by the initial POST.
 * @returns {Promise<Object|null>} Final job payload, or `null` if polling
 *          failed or timed out.
 * @private
 */
async function pollJobUntilComplete(jobId) {
    const url = `/api/fleet/jobs/${jobId}`;

    for (let attempt = 0; attempt < JOB_POLL_MAX_ATTEMPTS; attempt++) {
        const job = await safeFetch(url);

        if (job === null) {
            // Network / server error — stop polling.
            return null;
        }

        // Terminal states: "complete", "completed", "failed", "error".
        const state = (job.status ?? job.state ?? "").toLowerCase();
        if (
            state === "complete" ||
            state === "completed" ||
            state === "failed" ||
            state === "error"
        ) {
            return job;
        }

        // Wait before next poll.
        await new Promise((resolve) => setTimeout(resolve, JOB_POLL_INTERVAL_MS));
    }

    // Exceeded max attempts.
    return null;
}

/**
 * Handle the fleet-wide collect-logs action.
 *
 * 1. POST /api/fleet/logs once to start the job.
 * 2. Poll GET /api/fleet/jobs/{job_id} every 2 s until complete.
 * 3. Map results back to the selected entities.
 *
 * @param {Array<Object>} entities - Selected entities (for result mapping).
 * @param {{ onProgress?: (entityId: string, status: string) => void }} options
 * @returns {Promise<Array<{ entityId: string, entityName: string, status: "fulfilled"|"rejected", value?: any, reason?: string }>>}
 * @private
 */
async function executeCollectLogs(entities, options) {
    const onProgress = options?.onProgress;

    // Notify all entities as "pending".
    if (onProgress) {
        for (const entity of entities) {
            onProgress(entity.id, "pending");
        }
    }

    // Single fleet-wide POST.
    const postResult = await safeFetch("/api/fleet/logs", { method: "POST" });

    if (postResult === null) {
        return entities.map((entity) => {
            if (onProgress) onProgress(entity.id, "rejected");
            return {
                entityId: entity.id,
                entityName: entity.name ?? entity.id,
                status: "rejected",
                reason: "Failed to start log collection job",
            };
        });
    }

    const jobId = postResult.job_id ?? postResult.jobId;
    if (!jobId) {
        return entities.map((entity) => {
            if (onProgress) onProgress(entity.id, "rejected");
            return {
                entityId: entity.id,
                entityName: entity.name ?? entity.id,
                status: "rejected",
                reason: "Server did not return a job_id for log collection",
            };
        });
    }

    // Notify all entities that the job is running.
    if (onProgress) {
        for (const entity of entities) {
            onProgress(entity.id, "running");
        }
    }

    // Poll until terminal.
    const finalJob = await pollJobUntilComplete(jobId);

    if (finalJob === null) {
        return entities.map((entity) => {
            if (onProgress) onProgress(entity.id, "rejected");
            return {
                entityId: entity.id,
                entityName: entity.name ?? entity.id,
                status: "rejected",
                reason: "Log collection job timed out or polling failed",
            };
        });
    }

    const jobState = (finalJob.status ?? finalJob.state ?? "").toLowerCase();
    const succeeded = jobState === "complete" || jobState === "completed";

    return entities.map((entity) => {
        const status = succeeded ? "fulfilled" : "rejected";
        if (onProgress) onProgress(entity.id, status);
        return {
            entityId: entity.id,
            entityName: entity.name ?? entity.id,
            status,
            ...(succeeded
                ? { value: finalJob }
                : { reason: `Log collection job ${jobState}: ${finalJob.error ?? "unknown error"}` }),
        };
    });
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Execute a bulk action across one or more entities.
 *
 * Actions are looked up in the internal registry by `actionType`. Per-entity
 * actions are fanned out in parallel via `Promise.allSettled`. The fleet-wide
 * `collect-logs` action is handled as a special case (single POST + job
 * polling).
 *
 * @param {string}        actionType - Key in the action registry (e.g. "estop", "reboot").
 * @param {Array<Object>} entities   - Array of entity objects. Each must have at least
 *                                     `{ id: string, name?: string, entity_type?: string }`.
 * @param {Object}        [options]
 * @param {(entityId: string, status: string) => void} [options.onProgress]
 *        Optional callback invoked as each entity's result becomes available.
 *        `status` is one of "pending", "running", "fulfilled", or "rejected".
 *
 * @returns {Promise<Array<{
 *   entityId:    string,
 *   entityName:  string,
 *   status:      "fulfilled"|"rejected",
 *   value?:      any,
 *   reason?:     string
 * }>>} One result object per entity, in the same order as `entities`.
 *
 * @example
 * const results = await executeBulkAction("estop", selectedEntities, {
 *     onProgress(entityId, status) {
 *         console.log(`${entityId}: ${status}`);
 *     },
 * });
 * const failures = results.filter(r => r.status === "rejected");
 */
export async function executeBulkAction(actionType, entities, options) {
    const action = ACTION_REGISTRY[actionType];
    if (!action) {
        return entities.map((entity) => ({
            entityId: entity.id,
            entityName: entity.name ?? entity.id,
            status: "rejected",
            reason: `Unknown action type: ${actionType}`,
        }));
    }

    if (!entities || entities.length === 0) {
        return [];
    }

    // ---- Fleet-wide special case: collect-logs ----
    if (actionType === "collect-logs") {
        return executeCollectLogs(entities, options ?? {});
    }

    // ---- Per-entity fan-out ----
    const onProgress = options?.onProgress;

    // Mark all as pending.
    if (onProgress) {
        for (const entity of entities) {
            onProgress(entity.id, "pending");
        }
    }

    const promises = entities.map(async (entity) => {
        // Pre-flight validation for restart-ros2.
        if (actionType === "restart-ros2") {
            const svc = getServiceName(entity);
            if (svc === null) {
                const result = {
                    entityId: entity.id,
                    entityName: entity.name ?? entity.id,
                    status: /** @type {const} */ ("rejected"),
                    reason: `Unknown entity type "${entity.entity_type}" — cannot determine ROS2 service name`,
                };
                if (onProgress) onProgress(entity.id, "rejected");
                return result;
            }
        }

        if (onProgress) onProgress(entity.id, "running");

        const result = await executeOneEntity(action, entity);

        if (onProgress) onProgress(entity.id, result.status);
        return result;
    });

    // Promise.allSettled guarantees we never short-circuit on failure.
    const settled = await Promise.allSettled(promises);

    // Unwrap — our inner promises never reject (safeFetch never throws),
    // so every settlement is "fulfilled" at the Promise.allSettled level.
    // The actual per-entity success/failure is encoded in the result object.
    return settled.map((outcome) => {
        if (outcome.status === "fulfilled") {
            return outcome.value;
        }
        // Defensive: should not happen, but handle gracefully.
        return {
            entityId: "unknown",
            entityName: "unknown",
            status: /** @type {const} */ ("rejected"),
            reason: String(outcome.reason),
        };
    });
}
