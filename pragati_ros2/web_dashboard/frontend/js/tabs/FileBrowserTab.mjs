/**
 * FileBrowserTab — Preact component for browsing the filesystem.
 *
 * Provides a directory listing with navigation, breadcrumbs, and
 * file metadata display.
 *
 * Features:
 * - Directory listing with clickable navigation
 * - Breadcrumb path display
 * - Parent directory link (..)
 * - File name, type icon, size, and modified date
 * - Error handling for forbidden/not-found paths
 *
 * @module tabs/FileBrowserTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useRef } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format file size in human-readable form.
 * @param {number|null} size - Size in bytes
 * @returns {string}
 */
function formatSize(size) {
    if (size == null) return "--";
    if (size === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(size) / Math.log(1024));
    const val = size / Math.pow(1024, i);
    return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/**
 * Format an ISO 8601 date string for display.
 * @param {string|null} iso - ISO 8601 timestamp
 * @returns {string}
 */
function formatModified(iso) {
    if (!iso) return "--";
    try {
        return new Date(iso).toLocaleString();
    } catch {
        return iso;
    }
}

/**
 * Build breadcrumb segments from a path string.
 * @param {string} fullPath
 * @returns {Array<{name: string, path: string}>}
 */
function buildBreadcrumbs(fullPath) {
    if (!fullPath) return [];
    const parts = fullPath.split("/").filter(Boolean);
    const crumbs = [{ name: "/", path: "/" }];
    let accumulated = "";
    for (const part of parts) {
        accumulated += "/" + part;
        crumbs.push({ name: part, path: accumulated });
    }
    return crumbs;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Breadcrumb navigation bar.
 *
 * @param {object} props
 * @param {string} props.path - Current directory path
 * @param {(path: string) => void} props.onNavigate - Navigate handler
 */
function Breadcrumbs({ path, onNavigate }) {
    const crumbs = buildBreadcrumbs(path);

    return html`
        <div
            style=${{
                display: "flex",
                flexWrap: "wrap",
                gap: "var(--spacing-xs)",
                alignItems: "center",
                padding: "var(--spacing-sm) var(--spacing-md)",
                background: "var(--bg-tertiary)",
                borderRadius: "var(--radius-md)",
                marginBottom: "var(--spacing-md)",
                fontFamily: "monospace",
                fontSize: "0.9em",
            }}
        >
            ${crumbs.map(
                (crumb, i) => html`
                    ${i > 0 && html`<span style=${{ color: "var(--text-muted)" }}>/</span>`}
                    <a
                        href="#"
                        style=${{
                            color:
                                i === crumbs.length - 1
                                    ? "var(--text-primary)"
                                    : "var(--accent-color, #58a6ff)",
                            textDecoration: "none",
                            fontWeight: i === crumbs.length - 1 ? "bold" : "normal",
                            cursor: i === crumbs.length - 1 ? "default" : "pointer",
                        }}
                        onClick=${(e) => {
                            e.preventDefault();
                            if (i < crumbs.length - 1) onNavigate(crumb.path);
                        }}
                    >
                        ${crumb.name}
                    </a>
                `
            )}
        </div>
    `;
}

/**
 * Single entry row in the directory listing.
 *
 * @param {object} props
 * @param {object} props.entry - Entry object from API
 * @param {(path: string) => void} props.onNavigate - Navigate handler
 */
function EntryRow({ entry, onNavigate }) {
    const isDir = entry.type === "directory";
    const icon = isDir ? "\uD83D\uDCC1" : "\uD83D\uDCC4";

    return html`
        <tr
            style=${{
                cursor: isDir ? "pointer" : "default",
                borderBottom: "1px solid var(--border-color)",
            }}
            onClick=${() => {
                if (isDir) onNavigate(entry.path);
            }}
        >
            <td
                style=${{
                    padding: "var(--spacing-sm) var(--spacing-md)",
                    whiteSpace: "nowrap",
                }}
            >
                <span style=${{ marginRight: "var(--spacing-sm)" }}>${icon}</span>
                <span
                    style=${{
                        color: isDir
                            ? "var(--accent-color, #58a6ff)"
                            : "var(--text-primary)",
                        fontWeight: isDir ? "600" : "normal",
                    }}
                >
                    ${entry.name}
                </span>
            </td>
            <td
                style=${{
                    padding: "var(--spacing-sm) var(--spacing-md)",
                    textAlign: "right",
                    color: "var(--text-secondary)",
                }}
            >
                ${isDir ? "--" : formatSize(entry.size)}
            </td>
            <td
                style=${{
                    padding: "var(--spacing-sm) var(--spacing-md)",
                    color: "var(--text-secondary)",
                }}
            >
                ${formatModified(entry.modified)}
            </td>
        </tr>
    `;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

function FileBrowserTab() {
    const { showToast } = useToast();

    const [currentPath, setCurrentPath] = useState("");
    const [entries, setEntries] = useState([]);
    const [parentPath, setParentPath] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const mountedRef = useRef(true);

    // ---- data loading -----------------------------------------------------

    const loadDirectory = useCallback(
        async (path) => {
            setLoading(true);
            setError(null);

            const url = path
                ? `/api/filesystem/browse?path=${encodeURIComponent(path)}`
                : "/api/filesystem/browse";

            const data = await safeFetch(url);
            if (!mountedRef.current) return;

            if (!data) {
                setError("Connection error");
                setEntries([]);
                setParentPath(null);
                setLoading(false);
                return;
            }

            if (data.error) {
                setError(data.error);
                setEntries([]);
                setParentPath(null);
                setLoading(false);
                return;
            }

            setCurrentPath(data.path || path || "/");
            setEntries(data.entries || []);
            setParentPath(data.parent || null);
            setLoading(false);
        },
        []
    );

    const navigateTo = useCallback(
        (path) => {
            loadDirectory(path);
        },
        [loadDirectory]
    );

    // ---- lifecycle --------------------------------------------------------

    useEffect(() => {
        mountedRef.current = true;
        loadDirectory("");
        return () => {
            mountedRef.current = false;
        };
    }, [loadDirectory]);

    // ---- render -----------------------------------------------------------

    return html`
        <div class="section-header">
            <h2>File Browser</h2>
        </div>

        <${Breadcrumbs} path=${currentPath} onNavigate=${navigateTo} />

        ${loading && html`<p class="text-muted">Loading directory...</p>`}

        ${!loading &&
        error &&
        html`
            <div
                style=${{
                    padding: "var(--spacing-md)",
                    background: "var(--bg-tertiary)",
                    border: "1px solid var(--status-error, #dc3545)",
                    borderRadius: "var(--radius-md)",
                    color: "var(--status-error, #dc3545)",
                }}
            >
                ${error}
            </div>
        `}

        ${!loading &&
        !error &&
        html`
            <div style=${{ overflowX: "auto" }}>
                <table
                    style=${{
                        width: "100%",
                        borderCollapse: "collapse",
                        fontSize: "0.9em",
                    }}
                >
                    <thead>
                        <tr
                            style=${{
                                borderBottom: "2px solid var(--border-color)",
                                textAlign: "left",
                            }}
                        >
                            <th style=${{ padding: "var(--spacing-sm) var(--spacing-md)" }}>
                                Name
                            </th>
                            <th
                                style=${{
                                    padding: "var(--spacing-sm) var(--spacing-md)",
                                    textAlign: "right",
                                }}
                            >
                                Size
                            </th>
                            <th style=${{ padding: "var(--spacing-sm) var(--spacing-md)" }}>
                                Modified
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        ${parentPath != null &&
                        html`
                            <tr
                                style=${{
                                    cursor: "pointer",
                                    borderBottom: "1px solid var(--border-color)",
                                }}
                                onClick=${() => navigateTo(parentPath)}
                            >
                                <td
                                    style=${{
                                        padding: "var(--spacing-sm) var(--spacing-md)",
                                        color: "var(--accent-color, #58a6ff)",
                                        fontWeight: "600",
                                    }}
                                >
                                    ..
                                </td>
                                <td></td>
                                <td></td>
                            </tr>
                        `}
                        ${entries.length === 0 &&
                        parentPath == null &&
                        html`
                            <tr>
                                <td
                                    colspan="3"
                                    style=${{
                                        padding: "var(--spacing-lg)",
                                        textAlign: "center",
                                        color: "var(--text-muted)",
                                    }}
                                >
                                    Empty directory
                                </td>
                            </tr>
                        `}
                        ${entries.map(
                            (entry) => html`
                                <${EntryRow}
                                    key=${entry.path}
                                    entry=${entry}
                                    onNavigate=${navigateTo}
                                />
                            `
                        )}
                    </tbody>
                </table>
            </div>
        `}
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("file-browser", FileBrowserTab);

export default FileBrowserTab;
