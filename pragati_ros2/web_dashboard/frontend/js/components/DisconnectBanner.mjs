/**
 * DisconnectBanner — shows a fixed banner when WebSocket connection is lost.
 *
 * Behavior:
 * - When disconnected: shows "Disconnected — reconnecting in Xs..." with countdown
 * - When reconnected after disconnect: shows "Reconnected" (green) for 2 seconds
 * - Non-dismissible (no close button)
 *
 * @module components/DisconnectBanner
 */
import { h } from "preact";
import { useState, useEffect, useRef, useContext } from "preact/hooks";
import { html } from "htm/preact";
import { WebSocketContext } from "../app.js";

const RECONNECTED_DISPLAY_MS = 2000;

/**
 * Disconnect banner component.
 * Consumes WebSocketContext to read connection state.
 */
function DisconnectBanner() {
    const { disconnected, connected, reconnectCountdown } =
        useContext(WebSocketContext);

    const [showReconnected, setShowReconnected] = useState(false);
    const wasDisconnectedRef = useRef(false);
    const reconnectedTimerRef = useRef(null);

    // Track transitions from disconnected -> connected
    useEffect(() => {
        if (disconnected) {
            wasDisconnectedRef.current = true;
            // Clear any pending reconnected timer
            if (reconnectedTimerRef.current) {
                clearTimeout(reconnectedTimerRef.current);
                reconnectedTimerRef.current = null;
            }
            setShowReconnected(false);
        } else if (connected && wasDisconnectedRef.current) {
            // Just reconnected after being disconnected
            wasDisconnectedRef.current = false;
            setShowReconnected(true);
            reconnectedTimerRef.current = setTimeout(() => {
                setShowReconnected(false);
                reconnectedTimerRef.current = null;
            }, RECONNECTED_DISPLAY_MS);
        }

        return () => {
            if (reconnectedTimerRef.current) {
                clearTimeout(reconnectedTimerRef.current);
            }
        };
    }, [disconnected, connected]);

    // Nothing to show
    if (!disconnected && !showReconnected) return null;

    if (showReconnected) {
        return html`
            <div class="disconnect-banner reconnected">
                Reconnected
            </div>
        `;
    }

    const countdownText =
        reconnectCountdown > 0
            ? ` in ${reconnectCountdown}s...`
            : "...";

    return html`
        <div class="disconnect-banner">
            Disconnected — reconnecting${countdownText}
        </div>
    `;
}

export { DisconnectBanner };
