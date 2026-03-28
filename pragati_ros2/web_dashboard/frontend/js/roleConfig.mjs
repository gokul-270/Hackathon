/**
 * Role-based tab filtering configuration.
 *
 * Fetches the configured role from /api/config/role and provides
 * utilities to filter sidebar tab groups based on that role.
 *
 * @module roleConfig
 */
import { safeFetch } from "./utils.js";

// ---------------------------------------------------------------------------
// Role-to-tab mapping (Design decision D3)
// ---------------------------------------------------------------------------

/**
 * Maps each role to the set of tab IDs visible for that role.
 * - dev: null means ALL tabs are visible (no filtering).
 * - vehicle / arm: only the listed tab IDs are shown.
 *
 * @type {Object<string, Set<string>|null>}
 */
const ROLE_TAB_MAP = {
    dev: null,
    vehicle: new Set([
        "fleet-overview",
        "overview",
        "multi-arm",
        "launch-control",
        "safety",
        "nodes",
        "topics",
        "services",
        "parameters",
        "bags",
        "alerts",
        "settings",
        "systemd-services",
    ]),
    arm: new Set([
        "fleet-overview",
        "overview",
        "motor-config",
        "health",
        "launch-control",
        "safety",
        "nodes",
        "topics",
        "services",
        "parameters",
        "bags",
        "alerts",
        "settings",
        "systemd-services",
    ]),
};

// ---------------------------------------------------------------------------
// Role fetching
// ---------------------------------------------------------------------------

/**
 * Fetch the configured role from the backend.
 * Returns "dev" on any error (network failure, non-JSON response, etc.).
 *
 * @returns {Promise<string>} One of "dev", "vehicle", or "arm"
 */
async function fetchRole() {
    const data = await safeFetch("/api/config/role");
    if (data && data.role && ROLE_TAB_MAP.hasOwnProperty(data.role)) {
        return data.role;
    }
    console.warn("[roleConfig] Failed to fetch role, defaulting to dev");
    return "dev";
}

// ---------------------------------------------------------------------------
// Tab group filtering
// ---------------------------------------------------------------------------

/**
 * Filter TAB_GROUPS to only include tabs visible for the given role.
 *
 * For each group, items are filtered to those present in ROLE_TAB_MAP[role].
 * Groups with no remaining items after filtering are excluded entirely.
 * If the role is "dev" (map value is null), all groups are returned unfiltered.
 *
 * @param {string} role - One of "dev", "vehicle", or "arm"
 * @param {Array<{name: string, icon: string, items: Array<{id: string, label: string}>}>} tabGroups
 * @returns {Array<{name: string, icon: string, items: Array<{id: string, label: string}>}>}
 */
function getVisibleGroups(role, tabGroups) {
    const allowed = ROLE_TAB_MAP[role];

    // null means all tabs visible (dev role)
    if (allowed === null || allowed === undefined) {
        return tabGroups;
    }

    return tabGroups
        .map((group) => ({
            ...group,
            items: group.items.filter((item) => allowed.has(item.id)),
        }))
        .filter((group) => group.items.length > 0);
}

/**
 * Check whether a tab ID is allowed for the given role.
 *
 * @param {string} role - One of "dev", "vehicle", or "arm"
 * @param {string} tabId - Tab section ID to check
 * @returns {boolean}
 */
function isTabAllowed(role, tabId) {
    const allowed = ROLE_TAB_MAP[role];
    // null means all tabs visible (dev role)
    if (allowed === null || allowed === undefined) {
        return true;
    }
    return allowed.has(tabId);
}

export { ROLE_TAB_MAP, fetchRole, getVisibleGroups, isTabAllowed };
