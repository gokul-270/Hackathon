/**
 * Shared utility functions for the Pragati Dashboard.
 *
 * This is the single source of truth — all duplicates in other files
 * (dashboard.js, field_analysis.js, bag_manager.js) should be removed
 * once migration is complete.
 *
 * @module utils
 */

/**
 * Escape HTML special characters to prevent XSS.
 * @param {string|null|undefined} str
 * @returns {string}
 */
export function escapeHtml(str) {
    if (str == null) return "";
    const s = String(str);
    if (s === "") return "";
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

/**
 * Format a byte count into a human-readable string.
 * @param {number|null|undefined} bytes
 * @returns {string}
 */
export function formatBytes(bytes) {
    if (bytes == null || isNaN(bytes)) return "--";
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    const idx = Math.min(i, units.length - 1);
    const val = bytes / Math.pow(1024, idx);
    return `${val.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

/**
 * Format a duration in seconds to a human-readable string.
 * @param {number|null|undefined} seconds
 * @returns {string}
 */
export function formatDuration(seconds) {
    if (seconds == null || isNaN(seconds)) return "--";
    const s = Math.floor(seconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const parts = [];
    if (h > 0) parts.push(`${h}h`);
    if (m > 0 || h > 0) parts.push(`${m}m`);
    parts.push(`${sec}s`);
    return parts.join(" ");
}

/**
 * Format an ISO date string for display.
 * @param {string|null|undefined} isoString
 * @returns {string}
 */
export function formatDate(isoString) {
    if (!isoString) return "--";
    try {
        const d = new Date(isoString);
        if (isNaN(d.getTime())) return "--";
        return d.toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
            hour: "numeric",
            minute: "2-digit",
            hour12: true,
        });
    } catch {
        return "--";
    }
}

/**
 * Fetch a URL and return parsed JSON, or null on any error.
 *
 * This is a safe wrapper that never throws. On HTTP errors or network
 * failures it logs to console, dispatches a ``safefetch:error`` CustomEvent
 * on ``window`` (so the toast system can display feedback), and returns null.
 *
 * The event detail contains ``{ url, status, message }``.
 *
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<any|null>}
 */
export async function safeFetch(url, options) {
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            const message = `HTTP ${response.status} for ${url}`;
            console.error(`safeFetch: ${message}`);
            window.dispatchEvent(
                new CustomEvent("safefetch:error", {
                    detail: {
                        url,
                        status: response.status,
                        message,
                    },
                })
            );
            return null;
        }
        try {
            return await response.json();
        } catch (parseErr) {
            const message = `JSON parse error for ${url}`;
            console.error(`safeFetch: ${message}:`, parseErr);
            window.dispatchEvent(
                new CustomEvent("safefetch:error", {
                    detail: { url, status: 0, message },
                })
            );
            return null;
        }
    } catch (networkErr) {
        const message = `Network error for ${url}`;
        console.error(`safeFetch: ${message}:`, networkErr);
        window.dispatchEvent(
            new CustomEvent("safefetch:error", {
                detail: { url, status: 0, message },
            })
        );
        return null;
    }
}

/**
 * Convert an array of objects to CSV text.
 * @param {Array<Object>} data
 * @returns {string}
 */
export function convertToCSV(data) {
    if (!data || data.length === 0) return "";

    function csvEscape(val) {
        if (val == null) return "";
        const s = String(val);
        if (
            s.includes('"') ||
            s.includes(",") ||
            s.includes("\n") ||
            s.includes("\r")
        ) {
            return '"' + s.replace(/"/g, '""') + '"';
        }
        return s;
    }

    const headers = Object.keys(data[0]);
    const headerRow = headers.map(csvEscape).join(",");
    const rows = data.map((row) =>
        headers.map((h) => csvEscape(row[h])).join(",")
    );
    return [headerRow, ...rows].join("\n");
}
