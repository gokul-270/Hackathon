/**
 * ConnectionIndicator — displays a colored dot + status text for WebSocket
 * connection state.
 *
 * States:
 * - Connected: green dot (#22c55e), text "Connected"
 * - Reconnecting (disconnected, countdown > 0): amber (#f59e0b), "Reconnecting in Xs..."
 * - Disconnected: red dot (#ef4444), text "Disconnected"
 * - Connecting (initial, neither connected nor disconnected): amber, "Connecting..."
 *
 * @module components/ConnectionIndicator
 */
import { h } from "preact";
import { useContext } from "preact/hooks";
import { html } from "htm/preact";
import { WebSocketContext } from "../app.js";

const DOT_STYLE = {
    display: "inline-block",
    width: "8px",
    height: "8px",
    borderRadius: "50%",
};

/**
 * ConnectionIndicator component.
 * Consumes WebSocketContext to derive connection state.
 */
function ConnectionIndicator() {
    const { connected, disconnected, reconnectCountdown } =
        useContext(WebSocketContext);

    let color = "var(--color-error)"; // red — disconnected
    let text = "Disconnected";
    let className = "indicator disconnected";

    if (connected) {
        color = "var(--color-success)";
        text = "Connected";
        className = "indicator connected";
    } else if (disconnected && reconnectCountdown > 0) {
        color = "var(--color-warning)";
        text = `Reconnecting in ${reconnectCountdown}s...`;
        className = "indicator reconnecting";
    } else if (!disconnected && !connected) {
        color = "var(--color-warning)";
        text = "Connecting...";
        className = "indicator connecting";
    }

    return html`
        <span
            class=${className}
            id="connection-indicator"
            style=${{ ...DOT_STYLE, backgroundColor: color }}
        ></span>
        <span id="connection-text">${text}</span>
    `;
}

export { ConnectionIndicator };
