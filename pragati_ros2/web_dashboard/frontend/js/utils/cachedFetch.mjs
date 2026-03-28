/**
 * cachedEntityFetch — shared fetch utility with AbortController-based
 * timeout, TTL cache, stale fallback, and external signal support.
 *
 * Eliminates duplicate timeout/cache/error logic across the 4 ROS2
 * introspection sub-tabs (Nodes, Topics, Services, Parameters).
 *
 * @module utils/cachedFetch
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Default fetch timeout in milliseconds. */
const DEFAULT_TIMEOUT_MS = 25000;

/** Default cache TTL in milliseconds. */
const DEFAULT_TTL_MS = 5000;

// ---------------------------------------------------------------------------
// Module-level cache
// ---------------------------------------------------------------------------

/**
 * In-memory cache keyed by `${entityId}:${path}`.
 * Each entry: { data: any, timestamp: number }
 * @type {Map<string, {data: any, timestamp: number}>}
 */
const _cache = new Map();

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Fetch data for an entity endpoint with timeout, caching, and stale fallback.
 *
 * Return contract:
 *   | Condition                        | Return value                    |
 *   |----------------------------------|---------------------------------|
 *   | Cache hit (within TTL)           | { data, stale: false }          |
 *   | Network success                  | { data, stale: false }          |
 *   | Network failure + cache exists   | { data, stale: true }           |
 *   | Network failure + no cache       | null                            |
 *
 * @param {string} entityId - Entity identifier
 * @param {string} path - API path suffix (e.g. "ros2/topics")
 * @param {object} [options]
 * @param {AbortSignal} [options.signal] - External abort signal (e.g. unmount)
 * @param {boolean} [options.bypassCache] - Skip cache lookup, force fetch
 * @param {number} [options.timeoutMs] - Override default 8s timeout
 * @param {number} [options.ttlMs] - Override default 5s cache TTL
 * @returns {Promise<{data: any, stale: boolean}|null>}
 */
export async function cachedEntityFetch(entityId, path, options = {}) {
    const {
        signal: externalSignal,
        bypassCache = false,
        timeoutMs = DEFAULT_TIMEOUT_MS,
        ttlMs = DEFAULT_TTL_MS,
    } = options;

    const cacheKey = `${entityId}:${path}`;

    // --- Cache check (skip if bypassCache) ---------------------------------
    if (!bypassCache) {
        const cached = _cache.get(cacheKey);
        if (cached && (Date.now() - cached.timestamp) < ttlMs) {
            return { data: cached.data, stale: false };
        }
    }

    // --- Build abort signal ------------------------------------------------
    const timeoutSignal = AbortSignal.timeout(timeoutMs);
    const signals = externalSignal
        ? [timeoutSignal, externalSignal]
        : [timeoutSignal];
    const mergedSignal = AbortSignal.any(signals);

    // --- Fetch -------------------------------------------------------------
    const url = `/api/entities/${encodeURIComponent(entityId)}/${path}`;

    try {
        const response = await fetch(url, { signal: mergedSignal });

        if (!response.ok) {
            console.error(
                `[cachedEntityFetch] HTTP ${response.status} for ${url}`
            );
            // Fall back to stale cache if available
            const stale = _cache.get(cacheKey);
            if (stale) {
                return { data: stale.data, stale: true };
            }
            return null;
        }

        const json = await response.json();
        const data = json.data !== undefined ? json.data : json;

        // Update cache
        _cache.set(cacheKey, { data, timestamp: Date.now() });

        return { data, stale: false };
    } catch (err) {
        // Don't log abort errors from unmount — they're expected
        if (err.name !== "AbortError") {
            console.error(
                `[cachedEntityFetch] Error fetching ${url}:`,
                err.message
            );
        }

        // Fall back to stale cache if available
        const stale = _cache.get(cacheKey);
        if (stale) {
            return { data: stale.data, stale: true };
        }
        return null;
    }
}

/**
 * Clear all cached entries for a specific entity, or all entries if no
 * entityId is provided. Useful when an entity is removed or reconnects.
 *
 * @param {string} [entityId] - If provided, only clear entries for this entity
 */
export function clearCache(entityId) {
    if (!entityId) {
        _cache.clear();
        return;
    }
    const prefix = `${entityId}:`;
    for (const key of _cache.keys()) {
        if (key.startsWith(prefix)) {
            _cache.delete(key);
        }
    }
}

/**
 * Get the current cache size (for testing / diagnostics).
 * @returns {number}
 */
export function getCacheSize() {
    return _cache.size;
}

/**
 * Expose the internal cache map for testing only.
 * @returns {Map}
 */
export function _getCacheMap() {
    return _cache;
}
