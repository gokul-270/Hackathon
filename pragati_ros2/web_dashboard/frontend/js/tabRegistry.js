/**
 * Tab registry — shared between app shell and tab modules.
 *
 * Extracted into its own module to break the circular dependency:
 *   app.js -> tabs/*.mjs -> app.js (for registerTab)
 *
 * Now: app.js -> tabRegistry.js (no cycle)
 *      tabs/*.mjs -> tabRegistry.js (no cycle)
 *
 * @module tabRegistry
 */

/**
 * Registry of Preact tab components.
 * Key = section id (matches data-section in sidebar), Value = component function.
 */
export const tabRegistry = {};

/**
 * Register a Preact tab component.
 * @param {string} sectionId - Matches the data-section attribute in sidebar nav
 * @param {Function} component - Preact component function
 */
export function registerTab(sectionId, component) {
    tabRegistry[sectionId] = component;
}
