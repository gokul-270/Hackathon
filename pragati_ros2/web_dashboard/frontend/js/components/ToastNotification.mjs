/**
 * ToastNotification — standalone Preact component for a single toast item.
 *
 * Extracted from the inline rendering in app.js ToastContainer so that other
 * components can import and reuse it.
 *
 * @module components/ToastNotification
 */
import { useContext } from "preact/hooks";
import { html } from "htm/preact";
import { ToastContext } from "../app.js";

// ---------------------------------------------------------------------------
// ToastNotification component
// ---------------------------------------------------------------------------

/**
 * Renders a single toast notification bar.
 * Styling is handled via CSS classes (.preact-toast, .preact-toast-<severity>)
 * defined in styles.css using CSS custom properties.
 *
 * @param {object} props
 * @param {number} props.id        - Unique toast identifier
 * @param {string} props.message   - Text displayed in the toast
 * @param {string} props.severity  - One of "success" | "warning" | "error" | "info"
 * @param {(id: number) => void} props.onDismiss - Callback to remove the toast
 * @returns {import('preact').VNode}
 */
export function ToastNotification({ id, message, severity, onDismiss }) {
    return html`
        <div class="preact-toast preact-toast-${severity}">
            <span>${message}</span>
            <button
                class="toast-dismiss"
                onClick=${() => onDismiss(id)}
            >
                \u00d7
            </button>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// useToast hook
// ---------------------------------------------------------------------------

/**
 * Convenience hook — returns `{ showToast }` from the nearest ToastProvider.
 *
 * @returns {{ showToast: (message: string, severity?: string) => number }}
 */
export function useToast() {
    return useContext(ToastContext);
}
