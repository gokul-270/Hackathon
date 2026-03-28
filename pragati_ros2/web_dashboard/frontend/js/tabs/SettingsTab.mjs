/**
 * SettingsTab — Preact component for the Dashboard Settings tab.
 *
 * Migrated from vanilla JS (dashboard.js) as part of the incremental
 * Preact migration (task 5.1).
 *
 * @module tabs/SettingsTab
 */
import { h } from "preact";
import { useState, useEffect, useCallback } from "preact/hooks";
import { html } from "htm/preact";
import { safeFetch, formatDuration } from "../utils.js";
import { useToast } from "../components/ToastNotification.mjs";
import { registerTab } from "../tabRegistry.js";

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

/** @type {Record<string, any>} */
const DEFAULT_SETTINGS = {
    refreshInterval: 5000,
    theme: "dark",
    showToasts: true,
    cpuThreshold: 80,
    memoryThreshold: 85,
    motorTempThreshold: 70,
    batteryThreshold: 20,
    soundAlerts: true,
    dataRetention: 7,
    sessionLimit: 10,
};

const STORAGE_KEY = "dashboard_settings";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function SettingsTab() {
    const { showToast } = useToast();

    const [settings, setSettings] = useState(() => loadSettings());
    const [systemInfo, setSystemInfo] = useState(null);
    const [dirty, setDirty] = useState(false);

    // ---- helpers ----------------------------------------------------------

    function loadSettings() {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stored) {
                return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) };
            }
        } catch (e) {
            console.error("[SettingsTab] failed to parse stored settings:", e);
        }
        return { ...DEFAULT_SETTINGS };
    }

    const loadSystemInfo = useCallback(async () => {
        const data = await safeFetch("/api/system/info");
        if (data) {
            setSystemInfo(data);
        }
    }, []);

    // ---- mount ------------------------------------------------------------

    useEffect(() => {
        loadSystemInfo();
    }, [loadSystemInfo]);

    // ---- actions ----------------------------------------------------------

    const updateSetting = useCallback((key, value) => {
        setSettings((prev) => ({ ...prev, [key]: value }));
        setDirty(true);
    }, []);

    const saveSettings = useCallback(async () => {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));

            // Push alert rules to backend
            await safeFetch("/api/alerts/rules", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    cpuThreshold: settings.cpuThreshold,
                    memoryThreshold: settings.memoryThreshold,
                    motorTempThreshold: settings.motorTempThreshold,
                    batteryThreshold: settings.batteryThreshold,
                    soundAlerts: settings.soundAlerts,
                }),
            });

            setDirty(false);
            showToast("Settings saved successfully", "success");
        } catch (e) {
            console.error("[SettingsTab] save error:", e);
            showToast("Failed to save settings", "error");
        }
    }, [settings, showToast]);

    const resetSettings = useCallback(() => {
        localStorage.removeItem(STORAGE_KEY);
        setSettings({ ...DEFAULT_SETTINGS });
        setDirty(false);
        showToast("Settings reset to defaults", "info");
    }, [showToast]);

    // ---- render -----------------------------------------------------------

    return html`
        <div class="section-header">
            <h2>Dashboard Settings</h2>
            <div class="section-actions">
                <button class="btn btn-sm" onClick=${saveSettings}>
                    \u{1F4BE} Save Settings
                </button>
                <button class="btn btn-sm" onClick=${resetSettings}>
                    \u{1F504} Reset to Defaults
                </button>
            </div>
        </div>

        <!-- General Settings -->
        <div class="settings-panel">
            <h3>\u2699\uFE0F General Settings</h3>
            <div class="settings-group">
                <div class="setting-item">
                    <label class="setting-label">
                        <span>Dashboard Update Interval</span>
                        <small>How often to refresh dashboard data</small>
                    </label>
                    <select
                        class="select-input"
                        value=${String(settings.refreshInterval)}
                        onChange=${(e) =>
                            updateSetting(
                                "refreshInterval",
                                Number(e.target.value)
                            )}
                    >
                        <option value="1000">1 second</option>
                        <option value="2000">2 seconds</option>
                        <option value="5000">5 seconds</option>
                        <option value="10000">10 seconds</option>
                    </select>
                </div>

                <div class="setting-item">
                    <label class="setting-label">
                        <span>Theme</span>
                        <small>Dashboard color theme</small>
                    </label>
                    <select
                        class="select-input"
                        value=${settings.theme}
                        onChange=${(e) =>
                            updateSetting("theme", e.target.value)}
                    >
                        <option value="dark">Dark</option>
                        <option value="light">Light (Coming Soon)</option>
                    </select>
                </div>

                <div class="setting-item">
                    <label class="setting-label">
                        <span>Show Toast Notifications</span>
                        <small>Display popup notifications for events</small>
                    </label>
                    <input
                        type="checkbox"
                        checked=${settings.showToasts}
                        onChange=${(e) =>
                            updateSetting("showToasts", e.target.checked)}
                    />
                </div>
            </div>
        </div>

        <!-- Alert Settings -->
        <div class="settings-panel">
            <h3>\u26A0\uFE0F Alert Settings</h3>
            <div class="settings-group">
                <div class="setting-item">
                    <label class="setting-label">
                        <span>CPU Alert Threshold</span>
                        <small>Alert when CPU usage exceeds (%)</small>
                    </label>
                    <input
                        type="number"
                        class="number-input"
                        value=${settings.cpuThreshold}
                        min="50"
                        max="100"
                        step="5"
                        onChange=${(e) =>
                            updateSetting(
                                "cpuThreshold",
                                Number(e.target.value)
                            )}
                    />
                </div>

                <div class="setting-item">
                    <label class="setting-label">
                        <span>Memory Alert Threshold</span>
                        <small>Alert when memory usage exceeds (%)</small>
                    </label>
                    <input
                        type="number"
                        class="number-input"
                        value=${settings.memoryThreshold}
                        min="50"
                        max="100"
                        step="5"
                        onChange=${(e) =>
                            updateSetting(
                                "memoryThreshold",
                                Number(e.target.value)
                            )}
                    />
                </div>

                <div class="setting-item">
                    <label class="setting-label">
                        <span>Motor Temperature Threshold</span>
                        <small>Alert when motor temperature exceeds (\u00B0C)</small>
                    </label>
                    <input
                        type="number"
                        class="number-input"
                        value=${settings.motorTempThreshold}
                        min="50"
                        max="100"
                        step="5"
                        onChange=${(e) =>
                            updateSetting(
                                "motorTempThreshold",
                                Number(e.target.value)
                            )}
                    />
                </div>

                <div class="setting-item">
                    <label class="setting-label">
                        <span>Battery Low Threshold</span>
                        <small>Alert when battery drops below (%)</small>
                    </label>
                    <input
                        type="number"
                        class="number-input"
                        value=${settings.batteryThreshold}
                        min="10"
                        max="50"
                        step="5"
                        onChange=${(e) =>
                            updateSetting(
                                "batteryThreshold",
                                Number(e.target.value)
                            )}
                    />
                </div>

                <div class="setting-item">
                    <label class="setting-label">
                        <span>Sound Alerts</span>
                        <small>Play sound for critical alerts</small>
                    </label>
                    <input
                        type="checkbox"
                        checked=${settings.soundAlerts}
                        onChange=${(e) =>
                            updateSetting("soundAlerts", e.target.checked)}
                    />
                </div>
            </div>
        </div>

        <!-- Data Retention -->
        <div class="settings-panel">
            <h3>\u{1F4BE} Data Retention</h3>
            <div class="settings-group">
                <div class="setting-item">
                    <label class="setting-label">
                        <span>Historical Data Retention</span>
                        <small>How long to keep historical data</small>
                    </label>
                    <select
                        class="select-input"
                        value=${String(settings.dataRetention)}
                        onChange=${(e) =>
                            updateSetting(
                                "dataRetention",
                                Number(e.target.value)
                            )}
                    >
                        <option value="1">1 day</option>
                        <option value="3">3 days</option>
                        <option value="7">7 days</option>
                        <option value="30">30 days</option>
                    </select>
                </div>

                <div class="setting-item">
                    <label class="setting-label">
                        <span>Session History Limit</span>
                        <small>Number of recent sessions to display</small>
                    </label>
                    <input
                        type="number"
                        class="number-input"
                        value=${settings.sessionLimit}
                        min="5"
                        max="50"
                        step="5"
                        onChange=${(e) =>
                            updateSetting(
                                "sessionLimit",
                                Number(e.target.value)
                            )}
                    />
                </div>
            </div>
        </div>

        <!-- System Information -->
        <div class="settings-panel">
            <h3>\u2139\uFE0F System Information</h3>
            <div class="info-grid">
                <div class="info-item">
                    <span class="info-label">Dashboard Version</span>
                    <span class="info-value">
                        ${systemInfo?.dashboard_version ?? "--"}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">Backend Status</span>
                    <span class="info-value">
                        ${systemInfo ? "Connected" : "--"}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">ROS2 Distribution</span>
                    <span class="info-value">
                        ${systemInfo?.ros_distro ?? "--"}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">WebSocket Status</span>
                    <span class="info-value">
                        ${systemInfo ? "Active" : "--"}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">Hostname</span>
                    <span class="info-value">
                        ${systemInfo?.hostname ?? "--"}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">Platform</span>
                    <span class="info-value">
                        ${systemInfo?.platform ?? "--"}
                    </span>
                </div>
                <div class="info-item">
                    <span class="info-label">Server Uptime</span>
                    <span class="info-value">
                        ${systemInfo?.uptime_seconds != null
                            ? formatDuration(systemInfo.uptime_seconds)
                            : "--"}
                    </span>
                </div>
            </div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Register with the app shell
// ---------------------------------------------------------------------------

registerTab("settings", SettingsTab);

export { SettingsTab, DEFAULT_SETTINGS, STORAGE_KEY };
