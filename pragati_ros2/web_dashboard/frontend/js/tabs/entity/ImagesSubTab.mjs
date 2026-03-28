/**
 * ImagesSubTab — Browse detection images (input/output) on an entity.
 *
 * Features:
 * - Fetches image list from /api/entities/{id}/images
 * - Input / Output / All toggle filter
 * - Date filter: Today / Yesterday / All
 * - Sort: Newest first / Oldest first
 * - Group by date with date headers
 * - Grid of thumbnails with filename, size, timestamp
 * - Click to view full-size in a lightbox overlay
 * - Delete single image or bulk delete by date
 * - Auto-refresh every 10 seconds
 * - Empty-state messaging when no images found
 *
 * @module tabs/entity/ImagesSubTab
 */
import {
    useState,
    useEffect,
    useCallback,
    useMemo,
    useRef,
} from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch } from "../../utils.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 10000;

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
    container: {
        display: "flex",
        flexDirection: "column",
        gap: "12px",
    },
    toolbar: {
        display: "flex",
        alignItems: "center",
        gap: "8px",
        flexWrap: "wrap",
    },
    filterBtn: (active) => ({
        padding: "5px 14px",
        border: active ? "1px solid var(--color-accent, #4b8df7)" : "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-sm, 4px)",
        background: active ? "color-mix(in srgb, var(--color-accent, #4b8df7) 15%, transparent)" : "transparent",
        color: active ? "#fff" : "var(--color-text-primary, #e6e8eb)",
        cursor: "pointer",
        fontSize: "0.85em",
        fontWeight: active ? 600 : 400,
        transition: "all 0.15s ease",
    }),
    refreshBtn: {
        padding: "5px 12px",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-sm, 4px)",
        background: "transparent",
        color: "var(--color-text-primary, #e6e8eb)",
        cursor: "pointer",
        fontSize: "0.85em",
    },
    sortBtn: {
        padding: "5px 12px",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-sm, 4px)",
        background: "transparent",
        color: "var(--color-text-primary, #e6e8eb)",
        cursor: "pointer",
        fontSize: "0.85em",
    },
    deleteBtn: {
        padding: "3px 8px",
        border: "1px solid rgba(239, 68, 68, 0.4)",
        borderRadius: "var(--radius-sm, 4px)",
        background: "transparent",
        color: "#ef4444",
        cursor: "pointer",
        fontSize: "0.7em",
    },
    bulkDeleteBtn: {
        padding: "5px 14px",
        border: "1px solid rgba(239, 68, 68, 0.5)",
        borderRadius: "var(--radius-sm, 4px)",
        background: "rgba(239, 68, 68, 0.1)",
        color: "#ef4444",
        cursor: "pointer",
        fontSize: "0.85em",
        fontWeight: 500,
    },
    toolbarRight: {
        display: "flex",
        gap: "8px",
        alignItems: "center",
        marginLeft: "auto",
    },
    dateGroupHeader: {
        gridColumn: "1 / -1",
        fontSize: "0.85em",
        fontWeight: 600,
        color: "var(--color-text-muted, #8494a7)",
        padding: "8px 0 4px 0",
        borderBottom: "1px solid var(--color-border, #2d3748)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
    },
    confirmOverlay: {
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 10001,
    },
    confirmBox: {
        background: "var(--color-bg-secondary, #1a1f2e)",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-md, 8px)",
        padding: "24px",
        maxWidth: "400px",
        width: "90%",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
    },
    confirmTitle: {
        fontSize: "1em",
        fontWeight: 600,
        color: "#ef4444",
    },
    confirmText: {
        fontSize: "0.9em",
        color: "var(--color-text-primary, #e6e8eb)",
    },
    confirmActions: {
        display: "flex",
        gap: "8px",
        justifyContent: "flex-end",
    },
    confirmCancel: {
        padding: "6px 16px",
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-sm, 4px)",
        background: "transparent",
        color: "var(--color-text-primary, #e6e8eb)",
        cursor: "pointer",
        fontSize: "0.85em",
    },
    confirmDelete: {
        padding: "6px 16px",
        border: "none",
        borderRadius: "var(--radius-sm, 4px)",
        background: "#ef4444",
        color: "#fff",
        cursor: "pointer",
        fontSize: "0.85em",
        fontWeight: 600,
    },
    count: {
        fontSize: "0.85em",
        color: "var(--color-text-muted, #8494a7)",
    },
    grid: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
        gap: "12px",
    },
    card: {
        border: "1px solid var(--color-border, #2d3748)",
        borderRadius: "var(--radius-md, 8px)",
        overflow: "hidden",
        background: "var(--color-bg-secondary, #1a1f2e)",
        cursor: "pointer",
        transition: "border-color 0.15s, transform 0.1s",
    },
    cardHover: {
        borderColor: "var(--color-accent, #4b8df7)",
        transform: "translateY(-1px)",
    },
    thumb: {
        width: "100%",
        height: "140px",
        objectFit: "cover",
        display: "block",
        background: "var(--color-bg-tertiary, #242b3d)",
    },
    cardInfo: {
        padding: "6px 8px",
        fontSize: "0.75em",
        color: "var(--color-text-muted, #8494a7)",
        display: "flex",
        flexDirection: "column",
        gap: "2px",
    },
    cardName: {
        fontSize: "0.8em",
        fontWeight: 500,
        color: "var(--color-text-primary, #e6e8eb)",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
    },
    typeBadge: (type) => ({
        display: "inline-block",
        padding: "1px 6px",
        borderRadius: "3px",
        fontSize: "0.7em",
        fontWeight: 600,
        background: type === "input"
            ? "rgba(59, 130, 246, 0.2)"
            : "rgba(34, 197, 94, 0.2)",
        color: type === "input" ? "#93c5fd" : "#86efac",
    }),
    emptyState: {
        textAlign: "center",
        padding: "48px 24px",
        color: "var(--color-text-muted, #8494a7)",
    },
    loading: {
        textAlign: "center",
        padding: "48px 24px",
        color: "var(--color-text-muted, #8494a7)",
    },
    // Lightbox overlay
    overlay: {
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.85)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 10000,
        cursor: "pointer",
    },
    lightboxImg: {
        maxWidth: "90vw",
        maxHeight: "85vh",
        objectFit: "contain",
        borderRadius: "8px",
        boxShadow: "0 4px 30px rgba(0,0,0,0.5)",
    },
    lightboxInfo: {
        position: "fixed",
        bottom: "24px",
        left: "50%",
        transform: "translateX(-50%)",
        background: "rgba(0,0,0,0.7)",
        color: "#fff",
        padding: "8px 20px",
        borderRadius: "8px",
        fontSize: "0.85em",
        display: "flex",
        gap: "16px",
        alignItems: "center",
    },
    lightboxClose: {
        position: "fixed",
        top: "16px",
        right: "24px",
        background: "rgba(0,0,0,0.5)",
        color: "#fff",
        border: "none",
        borderRadius: "50%",
        width: "36px",
        height: "36px",
        fontSize: "1.2em",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
    },
    lightboxNav: {
        position: "fixed",
        top: "50%",
        transform: "translateY(-50%)",
        background: "rgba(0,0,0,0.5)",
        color: "#fff",
        border: "none",
        borderRadius: "50%",
        width: "40px",
        height: "40px",
        fontSize: "1.4em",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
    },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatSize(bytes) {
    if (bytes == null) return "--";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(isoStr) {
    if (!isoStr) return "";
    try {
        return new Date(isoStr).toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    } catch {
        return isoStr;
    }
}

function getDateKey(isoStr) {
    if (!isoStr) return "unknown";
    try {
        return new Date(isoStr).toLocaleDateString(undefined, {
            year: "numeric",
            month: "long",
            day: "numeric",
        });
    } catch {
        return "unknown";
    }
}

function isToday(isoStr) {
    if (!isoStr) return false;
    const d = new Date(isoStr);
    const now = new Date();
    return d.toDateString() === now.toDateString();
}

function isYesterday(isoStr) {
    if (!isoStr) return false;
    const d = new Date(isoStr);
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    return d.toDateString() === yesterday.toDateString();
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ImagesSubTab({
    entityId,
    entitySource,
    entityIp,
    ros2Available,
    registerCleanup,
}) {
    const [images, setImages] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState("all"); // "all" | "input" | "output"
    const [dateFilter, setDateFilter] = useState("all"); // "all" | "today" | "yesterday" | "custom"
    const [customDate, setCustomDate] = useState(""); // YYYY-MM-DD for custom date picker
    const [sortOrder, setSortOrder] = useState("newest"); // "newest" | "oldest"
    const [lightboxIdx, setLightboxIdx] = useState(null);
    const [confirmDialog, setConfirmDialog] = useState(null); // { title, message, onConfirm }
    const [deleting, setDeleting] = useState(false);
    const pollRef = useRef(null);
    const mountedRef = useRef(true);

    const baseUrl = `/api/entities/${entityId}`;

    // -- Fetch images -------------------------------------------------------

    const fetchImages = useCallback(async () => {
        const data = await safeFetch(`${baseUrl}/images`);
        if (!mountedRef.current) return;

        if (data) {
            const payload = data.data || data;
            const list = payload.images || (Array.isArray(payload) ? payload : []);
            setImages(list);
        }
        setLoading(false);
    }, [baseUrl]);

    // -- Lifecycle -----------------------------------------------------------

    useEffect(() => {
        mountedRef.current = true;
        fetchImages();
        pollRef.current = setInterval(fetchImages, POLL_INTERVAL_MS);

        const cleanup = () => {
            clearInterval(pollRef.current);
            pollRef.current = null;
        };

        if (registerCleanup) registerCleanup(cleanup);
        return () => {
            mountedRef.current = false;
            cleanup();
        };
    }, [fetchImages, registerCleanup]);

    // -- Filtered + sorted + grouped list ------------------------------------

    const filtered = useMemo(() => {
        let list = images;
        if (filter !== "all") {
            list = list.filter((img) => img.type === filter);
        }
        if (dateFilter === "today") {
            list = list.filter((img) => isToday(img.modified));
        } else if (dateFilter === "yesterday") {
            list = list.filter((img) => isYesterday(img.modified));
        } else if (dateFilter === "custom" && customDate) {
            list = list.filter((img) => {
                if (!img.modified) return false;
                const d = new Date(img.modified);
                const target = new Date(customDate + "T00:00:00");
                return d.toDateString() === target.toDateString();
            });
        }
        const sorted = [...list].sort((a, b) => {
            const da = a.modified || "";
            const db = b.modified || "";
            return sortOrder === "newest" ? db.localeCompare(da) : da.localeCompare(db);
        });
        return sorted;
    }, [images, filter, dateFilter, customDate, sortOrder]);

    const groupedByDate = useMemo(() => {
        const groups = [];
        let currentKey = null;
        let currentGroup = null;
        for (const img of filtered) {
            const key = getDateKey(img.modified);
            if (key !== currentKey) {
                currentKey = key;
                currentGroup = { date: key, images: [] };
                groups.push(currentGroup);
            }
            currentGroup.images.push(img);
        }
        return groups;
    }, [filtered]);

    // -- Image URL builder ---------------------------------------------------

    const imageUrl = useCallback(
        (img) => `${baseUrl}/images/${img.type}/${encodeURIComponent(img.name)}`,
        [baseUrl],
    );

    // -- Delete handlers ------------------------------------------------------

    const deleteImage = useCallback(
        (img) => {
            setConfirmDialog({
                title: "Delete image",
                message: `Delete "${img.name}"?`,
                onConfirm: async () => {
                    setConfirmDialog(null);
                    setDeleting(true);
                    await safeFetch(
                        `${baseUrl}/images/${img.type}/${encodeURIComponent(img.name)}`,
                        { method: "DELETE" },
                    );
                    setDeleting(false);
                    fetchImages();
                },
            });
        },
        [baseUrl, fetchImages],
    );

    const bulkDeleteByDate = useCallback(
        (dateStr, count) => {
            // Find the latest timestamp in this group + 1ms to include all
            const groupImages = filtered.filter(
                (img) => getDateKey(img.modified) === dateStr,
            );
            if (groupImages.length === 0) return;
            const filenames = groupImages.map((img) => img.name);

            setConfirmDialog({
                title: `Delete ${count} images`,
                message: `Delete all ${count} images from ${dateStr}? This cannot be undone.`,
                onConfirm: async () => {
                    setConfirmDialog(null);
                    setDeleting(true);
                    await safeFetch(`${baseUrl}/images/delete`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            filenames,
                            image_type: filter === "all" ? "all" : filter,
                        }),
                    });
                    setDeleting(false);
                    fetchImages();
                },
            });
        },
        [baseUrl, filtered, filter, fetchImages],
    );

    // -- Lightbox navigation -------------------------------------------------

    const openLightbox = useCallback((idx) => {
        setLightboxIdx(idx);
    }, []);

    const closeLightbox = useCallback(() => {
        setLightboxIdx(null);
    }, []);

    const prevImage = useCallback(
        (e) => {
            e.stopPropagation();
            setLightboxIdx((idx) =>
                idx != null ? (idx - 1 + filtered.length) % filtered.length : null,
            );
        },
        [filtered.length],
    );

    const nextImage = useCallback(
        (e) => {
            e.stopPropagation();
            setLightboxIdx((idx) =>
                idx != null ? (idx + 1) % filtered.length : null,
            );
        },
        [filtered.length],
    );

    // Keyboard navigation in lightbox
    useEffect(() => {
        if (lightboxIdx == null) return;
        const handler = (e) => {
            if (e.key === "Escape") closeLightbox();
            if (e.key === "ArrowLeft") prevImage(e);
            if (e.key === "ArrowRight") nextImage(e);
        };
        window.addEventListener("keydown", handler);
        return () => window.removeEventListener("keydown", handler);
    }, [lightboxIdx, closeLightbox, prevImage, nextImage]);

    // -- Render --------------------------------------------------------------

    if (loading) {
        return html`
            <div style=${styles.loading}>
                Loading images...
            </div>
        `;
    }

    const lightboxImage = lightboxIdx != null ? filtered[lightboxIdx] : null;

    return html`
        <div style=${styles.container}>
            <!-- Toolbar -->
            <div style=${styles.toolbar}>
                ${["all", "input", "output"].map(
                    (f) => html`
                        <button
                            key=${f}
                            style=${styles.filterBtn(filter === f)}
                            onClick=${() => setFilter(f)}
                        >
                            ${f === "all" ? "All" : f === "input" ? "\uD83D\uDCF7 Input" : "\uD83C\uDFAF Output"}
                        </button>
                    `,
                )}
                <span style=${{ width: "1px", height: "20px", background: "var(--color-border, #2d3748)", margin: "0 4px" }}></span>
                ${["all", "today", "yesterday"].map(
                    (d) => html`
                        <button
                            key=${d}
                            style=${styles.filterBtn(dateFilter === d)}
                            onClick=${() => { setDateFilter(d); setCustomDate(""); }}
                        >
                            ${d === "all" ? "All dates" : d === "today" ? "Today" : "Yesterday"}
                        </button>
                    `,
                )}
                <input
                    type="date"
                    value=${customDate}
                    onInput=${(e) => {
                        setCustomDate(e.target.value);
                        if (e.target.value) {
                            setDateFilter("custom");
                        } else {
                            setDateFilter("all");
                        }
                    }}
                    style=${{
                        padding: "4px 8px",
                        fontSize: "0.82em",
                        border: dateFilter === "custom"
                            ? "1px solid var(--color-accent, #4b8df7)"
                            : "1px solid var(--color-border, #2d3748)",
                        borderRadius: "var(--radius-sm, 4px)",
                        background: dateFilter === "custom"
                            ? "color-mix(in srgb, var(--color-accent, #4b8df7) 15%, transparent)"
                            : "var(--color-bg-tertiary, #242b3d)",
                        color: "var(--color-text-primary, #e6e8eb)",
                        colorScheme: "dark",
                    }}
                />
                <span style=${styles.count}>
                    ${filtered.length} image${filtered.length !== 1 ? "s" : ""}
                </span>
                <div style=${styles.toolbarRight}>
                    <button
                        style=${styles.sortBtn}
                        onClick=${() => setSortOrder((o) => o === "newest" ? "oldest" : "newest")}
                        title=${sortOrder === "newest" ? "Showing newest first" : "Showing oldest first"}
                    >
                        ${sortOrder === "newest" ? "\u2193 Newest" : "\u2191 Oldest"}
                    </button>
                    <button
                        style=${styles.refreshBtn}
                        onClick=${() => { setLoading(true); fetchImages(); }}
                        title="Refresh"
                    >
                        \u21BB Refresh
                    </button>
                </div>
            </div>

            <!-- Grid -->
            ${filtered.length === 0
                ? html`
                      <div style=${styles.emptyState}>
                          <div style=${{ fontSize: "2.5em", marginBottom: "12px", opacity: 0.4 }}>
                              \uD83D\uDDBC\uFE0F
                          </div>
                          <div>No ${filter === "all" ? "" : filter + " "}images found on this entity</div>
                          <div style=${{ fontSize: "0.85em", marginTop: "8px" }}>
                              Images are saved when detection is running with save_input_image / save_output_image enabled
                          </div>
                      </div>
                  `
                : html`
                      <div style=${styles.grid}>
                          ${groupedByDate.map(
                              (group) => html`
                                  <div key=${"hdr-" + group.date} style=${styles.dateGroupHeader}>
                                      <span>${group.date} (${group.images.length})</span>
                                      <button
                                          style=${styles.bulkDeleteBtn}
                                          disabled=${deleting}
                                          onClick=${() => bulkDeleteByDate(group.date, group.images.length)}
                                      >
                                          \uD83D\uDDD1 Delete ${group.images.length} images
                                      </button>
                                  </div>
                                  ${group.images.map(
                                      (img) => {
                                          const globalIdx = filtered.indexOf(img);
                                          return html`
                                              <div
                                                  key=${img.name}
                                                  style=${styles.card}
                                                  onClick=${() => openLightbox(globalIdx)}
                                                  onMouseEnter=${(e) => {
                                                      e.currentTarget.style.borderColor = "var(--color-accent, #4b8df7)";
                                                      e.currentTarget.style.transform = "translateY(-1px)";
                                                  }}
                                                  onMouseLeave=${(e) => {
                                                      e.currentTarget.style.borderColor = "var(--color-border, #2d3748)";
                                                      e.currentTarget.style.transform = "none";
                                                  }}
                                                  title=${img.name}
                                              >
                                                  <img
                                                      src=${imageUrl(img)}
                                                      alt=${img.name}
                                                      style=${styles.thumb}
                                                      loading="lazy"
                                                  />
                                                  <div style=${styles.cardInfo}>
                                                      <div style=${{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                                          <div style=${styles.cardName}>${img.name}</div>
                                                          <button
                                                              style=${styles.deleteBtn}
                                                              disabled=${deleting}
                                                              onClick=${(e) => {
                                                                  e.stopPropagation();
                                                                  deleteImage(img);
                                                              }}
                                                              title="Delete this image"
                                                          >
                                                              \u2715
                                                          </button>
                                                      </div>
                                                      <div style=${{ display: "flex", gap: "6px", alignItems: "center" }}>
                                                          <span style=${styles.typeBadge(img.type)}>${img.type}</span>
                                                          <span>${formatSize(img.size_bytes)}</span>
                                                      </div>
                                                      <div>${formatTime(img.modified)}</div>
                                                  </div>
                                              </div>
                                          `;
                                      },
                                  )}
                              `,
                          )}
                      </div>
                  `}

            <!-- Confirmation dialog -->
            ${confirmDialog && html`
                <div style=${styles.confirmOverlay} onClick=${() => setConfirmDialog(null)}>
                    <div style=${styles.confirmBox} onClick=${(e) => e.stopPropagation()}>
                        <div style=${styles.confirmTitle}>${confirmDialog.title}</div>
                        <div style=${styles.confirmText}>${confirmDialog.message}</div>
                        <div style=${styles.confirmActions}>
                            <button
                                style=${styles.confirmCancel}
                                onClick=${() => setConfirmDialog(null)}
                            >
                                Cancel
                            </button>
                            <button
                                style=${styles.confirmDelete}
                                onClick=${confirmDialog.onConfirm}
                            >
                                Delete
                            </button>
                        </div>
                    </div>
                </div>
            `}

            <!-- Lightbox overlay -->
            ${lightboxImage != null && html`
                <div style=${styles.overlay} onClick=${closeLightbox}>
                    <button
                        style=${styles.lightboxClose}
                        onClick=${closeLightbox}
                        title="Close"
                    >
                        \u2715
                    </button>
                    ${filtered.length > 1 && html`
                        <button
                            style=${{ ...styles.lightboxNav, left: "16px" }}
                            onClick=${prevImage}
                            title="Previous"
                        >
                            \u276E
                        </button>
                        <button
                            style=${{ ...styles.lightboxNav, right: "16px" }}
                            onClick=${nextImage}
                            title="Next"
                        >
                            \u276F
                        </button>
                    `}
                    <img
                        src=${imageUrl(lightboxImage)}
                        alt=${lightboxImage.name}
                        style=${styles.lightboxImg}
                        onClick=${(e) => e.stopPropagation()}
                    />
                    <div style=${styles.lightboxInfo}>
                        <span style=${styles.typeBadge(lightboxImage.type)}>
                            ${lightboxImage.type}
                        </span>
                        <span>${lightboxImage.name}</span>
                        <span>${formatSize(lightboxImage.size_bytes)}</span>
                        <span>${formatTime(lightboxImage.modified)}</span>
                        <span>${lightboxIdx + 1} / ${filtered.length}</span>
                    </div>
                </div>
            `}
        </div>
    `;
}
