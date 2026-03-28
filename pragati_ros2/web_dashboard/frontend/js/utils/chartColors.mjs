/**
 * Read CSS custom properties at runtime for Chart.js configuration.
 * Chart.js doesn't support CSS var() references, so we read computed values.
 *
 * @module utils/chartColors
 */

/** Hardcoded fallbacks for chart colors if CSS variables are undefined. */
const CHART_COLOR_FALLBACKS = {
    "--color-accent": "#3b82f6",
    "--color-error": "#ef4444",
    "--color-warning": "#f59e0b",
    "--color-success": "#22c55e",
    "--color-text-primary": "#e2e8f0",
    "--color-text-secondary": "#94a3b8",
    "--color-text-muted": "#64748b",
    "--color-bg-surface": "#1e293b",
    "--color-bg-elevated": "#334155",
    "--chart-primary": "#3b82f6",
    "--chart-secondary": "#8b5cf6",
    "--chart-tertiary": "#06b6d4",
    "--chart-quaternary": "#f59e0b",
    "--chart-grid": "rgba(148, 163, 184, 0.15)",
    "--chart-text": "#94a3b8",
};

/**
 * Read a single CSS custom property value from :root.
 * Must be called after DOM is ready.
 * Falls back to a hardcoded default if the CSS variable is undefined.
 * @param {string} tokenName - CSS custom property name (e.g. '--color-accent')
 * @returns {string} The computed color value
 */
function getChartColor(tokenName) {
    const value = getComputedStyle(document.documentElement)
        .getPropertyValue(tokenName)
        .trim();
    return value || CHART_COLOR_FALLBACKS[tokenName] || "";
}

/**
 * Read all common theme tokens at once.
 * Must be called after DOM is ready (inside component mount/render).
 * @returns {object} Map of semantic names to resolved color strings
 */
function getChartColors() {
    return {
        accent: getChartColor("--color-accent"),
        error: getChartColor("--color-error"),
        warning: getChartColor("--color-warning"),
        success: getChartColor("--color-success"),
        textPrimary: getChartColor("--color-text-primary"),
        textSecondary: getChartColor("--color-text-secondary"),
        textMuted: getChartColor("--color-text-muted"),
        bgSurface: getChartColor("--color-bg-surface"),
        bgElevated: getChartColor("--color-bg-elevated"),
    };
}

export { getChartColor, getChartColors };
