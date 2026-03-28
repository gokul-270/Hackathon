/**
 * ConfirmationDialog — Preact port of the vanilla JS confirmation dialog.
 *
 * Provides both a declarative `<ConfirmationDialog>` component and a
 * `useConfirmDialog()` hook that preserves the Promise-based API of the
 * original `window.confirmationDialog` singleton.
 *
 * CSS classes match the existing styles.css definitions (modal-overlay,
 * modal-content, modal-header, modal-body, confirm-dialog-actions, etc.)
 * so no stylesheet changes are needed.
 *
 * @module components/ConfirmationDialog
 */
import { h } from "preact";
import { useState, useEffect, useCallback, useRef } from "preact/hooks";
import { html } from "htm/preact";

// ---------------------------------------------------------------------------
// ConfirmationDialog component
// ---------------------------------------------------------------------------

/**
 * Declarative confirmation dialog rendered as a modal overlay.
 *
 * @param {object} props
 * @param {boolean}   props.open              - Whether the dialog is visible
 * @param {string}    props.title             - Dialog title
 * @param {string}    props.message           - Body message
 * @param {string}    [props.confirmText='Confirm'] - Confirm button label
 * @param {string}    [props.cancelText='Cancel']   - Cancel button label
 * @param {boolean}   [props.dangerous=false] - If true, confirm button is red
 * @param {string}    [props.confirmWord]     - If set, enables double-confirm mode
 * @param {string}    [props.confirmWordPrompt] - Prompt text above input
 * @param {() => void} props.onConfirm       - Called when user confirms
 * @param {() => void} props.onCancel        - Called when user cancels
 * @returns {import('preact').VNode|null}
 */
export function ConfirmationDialog({
    open,
    title,
    message,
    confirmText = "Confirm",
    cancelText = "Cancel",
    dangerous = false,
    confirmWord,
    confirmWordPrompt,
    onConfirm,
    onCancel,
}) {
    const [inputValue, setInputValue] = useState("");
    const inputRef = useRef(null);

    // Determine whether we are in double-confirm mode
    const isDoubleConfirm = typeof confirmWord === "string" && confirmWord.length > 0;
    const confirmDisabled = isDoubleConfirm && inputValue.trim() !== confirmWord;

    // Default prompt text for double-confirm mode
    const promptText =
        confirmWordPrompt || (isDoubleConfirm ? `Type ${confirmWord} to confirm` : "");

    // -----------------------------------------------------------------------
    // Reset input whenever the dialog opens or the confirmWord changes
    // -----------------------------------------------------------------------
    useEffect(() => {
        if (open) {
            setInputValue("");
        }
    }, [open, confirmWord]);

    // -----------------------------------------------------------------------
    // Auto-focus the input in double-confirm mode
    // -----------------------------------------------------------------------
    useEffect(() => {
        if (open && isDoubleConfirm && inputRef.current) {
            inputRef.current.focus();
        }
    }, [open, isDoubleConfirm]);

    // -----------------------------------------------------------------------
    // Escape key cancels the dialog
    // -----------------------------------------------------------------------
    useEffect(() => {
        if (!open) return;

        /** @param {KeyboardEvent} e */
        function onKeydown(e) {
            if (e.key === "Escape") {
                e.stopPropagation();
                onCancel && onCancel();
            }
        }

        document.addEventListener("keydown", onKeydown);
        return () => document.removeEventListener("keydown", onKeydown);
    }, [open, onCancel]);

    // -----------------------------------------------------------------------
    // Clicking overlay background cancels
    // -----------------------------------------------------------------------
    /** @param {MouseEvent} e */
    const onOverlayClick = useCallback(
        (e) => {
            if (e.target === e.currentTarget) {
                onCancel && onCancel();
            }
        },
        [onCancel],
    );

    // -----------------------------------------------------------------------
    // Render nothing when closed
    // -----------------------------------------------------------------------
    if (!open) return null;

    // -----------------------------------------------------------------------
    // Confirm button class list
    // -----------------------------------------------------------------------
    const confirmBtnClass =
        "btn confirm-dialog-confirm" + (dangerous ? " confirm-btn-danger" : "");

    return html`
        <div
            class="modal-overlay"
            data-confirm-dialog="true"
            onClick=${onOverlayClick}
        >
            <div class="modal-content">
                <div class="modal-header">
                    <h3>${title}</h3>
                </div>
                <div class="modal-body">
                    ${typeof message === "string" ? html`<p>${message}</p>` : message}
                    ${isDoubleConfirm &&
                    html`
                        <p class="confirm-dialog-word-prompt">${promptText}</p>
                        <input
                            type="text"
                            class="confirm-dialog-input"
                            placeholder=${confirmWord}
                            autocomplete="off"
                            spellcheck=${false}
                            ref=${inputRef}
                            value=${inputValue}
                            onInput=${(/** @type {Event} */ e) =>
                                setInputValue(/** @type {HTMLInputElement} */ (e.target).value)}
                        />
                    `}
                    <div class="confirm-dialog-actions">
                        <button
                            class="btn confirm-dialog-cancel"
                            onClick=${onCancel}
                        >
                            ${cancelText}
                        </button>
                        <button
                            class=${confirmBtnClass}
                            disabled=${confirmDisabled}
                            onClick=${onConfirm}
                        >
                            ${confirmText}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// useConfirmDialog hook — Promise-based API
// ---------------------------------------------------------------------------

/**
 * @typedef {object} ConfirmOptions
 * @property {string}  title                   - Dialog title
 * @property {string}  [message='']            - Body message
 * @property {string}  [confirmText='Confirm'] - Confirm button label
 * @property {string}  [cancelText='Cancel']   - Cancel button label
 * @property {boolean} [dangerous=false]       - Red confirm button
 */

/**
 * @typedef {ConfirmOptions & {
 *   confirmWord?: string,
 *   confirmWordPrompt?: string,
 * }} DoubleConfirmOptions
 */

/**
 * Hook that provides a Promise-based confirmation API similar to the
 * original `window.confirmationDialog` singleton.
 *
 * Usage:
 * ```js
 * const { dialog, confirm, doubleConfirm } = useConfirmDialog();
 *
 * // Render `dialog` somewhere in your JSX tree
 * // Call confirm() or doubleConfirm() to show the dialog
 *
 * const ok = await confirm({ title: 'Delete?', dangerous: true });
 * const ok2 = await doubleConfirm({ title: 'Shutdown', confirmWord: 'SHUTDOWN' });
 * ```
 *
 * @returns {{
 *   dialog: import('preact').VNode|null,
 *   confirm: (options: ConfirmOptions) => Promise<boolean>,
 *   doubleConfirm: (options: DoubleConfirmOptions) => Promise<boolean>,
 * }}
 */
export function useConfirmDialog() {
    const [state, setState] = useState(/** @type {null|object} */ (null));
    const resolveRef = useRef(/** @type {((v: boolean) => void)|null} */ (null));

    // Stable callbacks ---------------------------------------------------

    const onConfirm = useCallback(() => {
        const resolve = resolveRef.current;
        resolveRef.current = null;
        setState(null);
        if (resolve) resolve(true);
    }, []);

    const onCancel = useCallback(() => {
        const resolve = resolveRef.current;
        resolveRef.current = null;
        setState(null);
        if (resolve) resolve(false);
    }, []);

    // Clean up on unmount — resolve pending promise as cancelled ----------
    useEffect(() => {
        return () => {
            if (resolveRef.current) {
                resolveRef.current(false);
                resolveRef.current = null;
            }
        };
    }, []);

    // Public methods ------------------------------------------------------

    /**
     * Show a simple confirmation dialog.
     * @param {ConfirmOptions} options
     * @returns {Promise<boolean>}
     */
    const confirm = useCallback(
        (options) =>
            new Promise((resolve) => {
                // Cancel any existing dialog first
                if (resolveRef.current) {
                    resolveRef.current(false);
                }
                resolveRef.current = resolve;
                setState({
                    open: true,
                    title: options.title || "Confirm",
                    message: options.message || "",
                    confirmText: options.confirmText || "Confirm",
                    cancelText: options.cancelText || "Cancel",
                    dangerous: !!options.dangerous,
                    confirmWord: undefined,
                    confirmWordPrompt: undefined,
                });
            }),
        [],
    );

    /**
     * Show a double-confirmation dialog requiring the user to type a word.
     * @param {DoubleConfirmOptions} options
     * @returns {Promise<boolean>}
     */
    const doubleConfirm = useCallback(
        (options) =>
            new Promise((resolve) => {
                // Cancel any existing dialog first
                if (resolveRef.current) {
                    resolveRef.current(false);
                }
                resolveRef.current = resolve;
                setState({
                    open: true,
                    title: options.title || "Confirm",
                    message: options.message || "",
                    confirmText: options.confirmText || "Confirm",
                    cancelText: options.cancelText || "Cancel",
                    dangerous: !!options.dangerous,
                    confirmWord: options.confirmWord || "CONFIRM",
                    confirmWordPrompt: options.confirmWordPrompt || undefined,
                });
            }),
        [],
    );

    // Build the dialog element --------------------------------------------

    const dialog = state
        ? html`
              <${ConfirmationDialog}
                  open=${state.open}
                  title=${state.title}
                  message=${state.message}
                  confirmText=${state.confirmText}
                  cancelText=${state.cancelText}
                  dangerous=${state.dangerous}
                  confirmWord=${state.confirmWord}
                  confirmWordPrompt=${state.confirmWordPrompt}
                  onConfirm=${onConfirm}
                  onCancel=${onCancel}
              />
          `
        : null;

    return { dialog, confirm, doubleConfirm };
}
