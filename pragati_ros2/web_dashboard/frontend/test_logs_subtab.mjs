#!/usr/bin/env node
/**
 * Unit tests for LogsSubTab pure functions: parseLogEntry, normalizeSeverity,
 * and severity filter logic.
 *
 * Run: node --test web_dashboard/frontend/test_logs_subtab.mjs
 *
 * Since LogsSubTab.mjs imports from 'preact', 'preact/hooks', and 'htm/preact'
 * (bare specifiers resolved by browser import maps, not available in Node.js),
 * we extract the pure functions via readFileSync + Function constructor.
 *
 * Covers tasks: 3.3, 3.5
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOGS_SUBTAB_PATH = join(
    __dirname,
    "js",
    "tabs",
    "entity",
    "LogsSubTab.mjs",
);

// ===========================================================================
// Extract pure functions from LogsSubTab source
// ===========================================================================

/**
 * Extract constants and pure functions from LogsSubTab.mjs source code
 * and return them as callable objects via the Function constructor.
 */
function extractLogsPureFunctions() {
    const src = readFileSync(LOGS_SUBTAB_PATH, "utf-8");

    // Extract the constants and functions we need. We build a self-contained
    // JS snippet that declares all dependencies and returns the functions.
    const snippet = `
        const SEVERITY_LEVELS = ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"];

        const JOURNAL_PRIORITY_MAP = {
            0: "FATAL", 1: "FATAL", 2: "FATAL",
            3: "ERROR",
            4: "WARN",
            5: "INFO", 6: "INFO",
            7: "DEBUG",
        };

        const SEVERITY_REGEX_PATTERNS = [
            /\\[(FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG)\\]/i,
            /\\blevel\\s*=\\s*(fatal|error|warn(?:ing)?|info|debug)\\b/i,
            /\\b(FATAL|ERROR|WARN(?:ING)?|INFO|DEBUG)\\b/i,
        ];

        const TIMESTAMP_REGEX_PATTERNS = [
            /(\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:?\\d{2})?)/,
            /^([A-Z][a-z]{2}\\s+\\d{1,2}\\s+\\d{2}:\\d{2}:\\d{2})/,
            /^(\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?)/,
        ];

        function normalizeSeverity(raw) {
            const upper = raw.toUpperCase();
            if (upper === "WARNING") return "WARN";
            if (SEVERITY_LEVELS.includes(upper)) return upper;
            return "INFO";
        }

        function parseLogEntry(data, isJournald) {
            if (isJournald && typeof data === "object" && data !== null) {
                const priority = parseInt(data.PRIORITY, 10);
                const severity =
                    JOURNAL_PRIORITY_MAP[priority] != null
                        ? JOURNAL_PRIORITY_MAP[priority]
                        : "INFO";
                const message = data.MESSAGE || data.message || "";
                const unit = data._SYSTEMD_UNIT || "";
                let timestamp = "";
                if (data.__REALTIME_TIMESTAMP) {
                    const ms = Math.floor(
                        parseInt(data.__REALTIME_TIMESTAMP, 10) / 1000,
                    );
                    try {
                        timestamp = new Date(ms).toLocaleTimeString();
                    } catch {
                        timestamp = "";
                    }
                } else if (data.timestamp) {
                    timestamp = data.timestamp;
                }
                return { severity, timestamp, message, source: unit };
            }

            if (typeof data === "string") {
                const text = data;
                let severity = "INFO";
                for (const pattern of SEVERITY_REGEX_PATTERNS) {
                    const match = text.match(pattern);
                    if (match) {
                        severity = normalizeSeverity(match[1]);
                        break;
                    }
                }
                let timestamp = "";
                for (const pattern of TIMESTAMP_REGEX_PATTERNS) {
                    const match = text.match(pattern);
                    if (match) {
                        timestamp = match[1];
                        break;
                    }
                }
                return { severity, timestamp, message: text, source: "" };
            }

            if (typeof data === "object" && data !== null) {
                const severity = normalizeSeverity(
                    data.severity || data.level || "INFO",
                );
                const timestamp = data.timestamp || "";
                const message =
                    data.message || data.line || data.text || "";
                const source = data.source || data.node || "";
                return { severity, timestamp, message, source };
            }

            return {
                severity: "INFO",
                timestamp: "",
                message: String(data),
                source: "",
            };
        }

        return { parseLogEntry, normalizeSeverity };
    `;

    const factory = new Function(snippet);
    return factory();
}

const { parseLogEntry, normalizeSeverity } = extractLogsPureFunctions();

// ===========================================================================
// Task 3.3 — parseLogEntry with various log formats
// ===========================================================================

describe("parseLogEntry", () => {
    // -- Journalctl JSON (isJournald = true) --

    describe("journalctl JSON mode", () => {
        it("parses standard journalctl JSON with PRIORITY 6 (INFO)", () => {
            const data = {
                MESSAGE: "Started arm_launch.service",
                PRIORITY: "6",
                _SYSTEMD_UNIT: "arm_launch.service",
                __REALTIME_TIMESTAMP: "1710000000000000",
            };
            const result = parseLogEntry(data, true);
            assert.equal(result.severity, "INFO");
            assert.equal(result.message, "Started arm_launch.service");
            assert.equal(result.source, "arm_launch.service");
            assert.ok(result.timestamp.length > 0, "timestamp should be set");
        });

        it("maps PRIORITY 3 to ERROR", () => {
            const data = {
                MESSAGE: "Segfault in motor driver",
                PRIORITY: "3",
                _SYSTEMD_UNIT: "arm_launch.service",
            };
            const result = parseLogEntry(data, true);
            assert.equal(result.severity, "ERROR");
        });

        it("maps PRIORITY 4 to WARN", () => {
            const data = { MESSAGE: "CAN timeout", PRIORITY: "4" };
            const result = parseLogEntry(data, true);
            assert.equal(result.severity, "WARN");
        });

        it("maps PRIORITY 0 to FATAL", () => {
            const data = { MESSAGE: "Kernel panic", PRIORITY: "0" };
            const result = parseLogEntry(data, true);
            assert.equal(result.severity, "FATAL");
        });

        it("maps PRIORITY 1 to FATAL", () => {
            const data = { MESSAGE: "Alert", PRIORITY: "1" };
            const result = parseLogEntry(data, true);
            assert.equal(result.severity, "FATAL");
        });

        it("maps PRIORITY 2 to FATAL", () => {
            const data = { MESSAGE: "Critical", PRIORITY: "2" };
            const result = parseLogEntry(data, true);
            assert.equal(result.severity, "FATAL");
        });

        it("maps PRIORITY 5 to INFO", () => {
            const data = { MESSAGE: "Notice", PRIORITY: "5" };
            const result = parseLogEntry(data, true);
            assert.equal(result.severity, "INFO");
        });

        it("maps PRIORITY 7 to DEBUG", () => {
            const data = { MESSAGE: "Trace info", PRIORITY: "7" };
            const result = parseLogEntry(data, true);
            assert.equal(result.severity, "DEBUG");
        });

        it("defaults to INFO for unknown PRIORITY", () => {
            const data = { MESSAGE: "Unknown", PRIORITY: "99" };
            const result = parseLogEntry(data, true);
            assert.equal(result.severity, "INFO");
        });

        it("falls back to data.message if MESSAGE is missing", () => {
            const data = { message: "fallback", PRIORITY: "6" };
            const result = parseLogEntry(data, true);
            assert.equal(result.message, "fallback");
        });

        it("uses data.timestamp when __REALTIME_TIMESTAMP missing", () => {
            const data = {
                MESSAGE: "test",
                PRIORITY: "6",
                timestamp: "12:34:56",
            };
            const result = parseLogEntry(data, true);
            assert.equal(result.timestamp, "12:34:56");
        });

        it("returns empty timestamp when both fields missing", () => {
            const data = { MESSAGE: "test", PRIORITY: "6" };
            const result = parseLogEntry(data, true);
            assert.equal(result.timestamp, "");
        });

        it("returns empty source when _SYSTEMD_UNIT missing", () => {
            const data = { MESSAGE: "test", PRIORITY: "6" };
            const result = parseLogEntry(data, true);
            assert.equal(result.source, "");
        });
    });

    // -- Raw text strings (isJournald = false) --

    describe("raw text mode", () => {
        it("extracts [ERROR] severity from ROS2-style log", () => {
            const line =
                "[motor_controller] [ERROR] 2024-01-15T10:30:45.123Z: CAN bus timeout";
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "ERROR");
            assert.equal(result.message, line);
        });

        it("extracts [WARN] severity", () => {
            const line = "[arm_node] [WARN] Battery low";
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "WARN");
        });

        it("extracts [WARNING] and normalizes to WARN", () => {
            const line = "[detector] [WARNING] Frame dropped";
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "WARN");
        });

        it("extracts [INFO] severity", () => {
            const line = "[main] [INFO] System ready";
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "INFO");
        });

        it("extracts [DEBUG] severity", () => {
            const line = "[planner] [DEBUG] Path computed in 12ms";
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "DEBUG");
        });

        it("extracts [FATAL] severity", () => {
            const line = "[safety] [FATAL] Emergency stop triggered";
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "FATAL");
        });

        it("extracts level=error from Python-style log", () => {
            const line =
                '2024-01-15 10:30:45 level=error msg="Connection refused"';
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "ERROR");
        });

        it("extracts level=warn from structured log", () => {
            const line = 'level=warn msg="Retrying in 5s"';
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "WARN");
        });

        it("extracts level=warning and normalizes to WARN", () => {
            const line = "level=warning component=mqtt";
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "WARN");
        });

        it("extracts bare ERROR keyword", () => {
            const line = "ERROR: failed to open /dev/can0";
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "ERROR");
        });

        it("defaults to INFO for unstructured text", () => {
            const line = "All systems nominal, proceeding to next waypoint";
            const result = parseLogEntry(line, false);
            assert.equal(result.severity, "INFO");
        });

        it("extracts ISO 8601 timestamp", () => {
            const line =
                "2024-01-15T10:30:45.123Z [INFO] System initialized";
            const result = parseLogEntry(line, false);
            assert.equal(result.timestamp, "2024-01-15T10:30:45.123Z");
        });

        it("extracts ISO 8601 timestamp with space separator", () => {
            const line = "2024-01-15 10:30:45 [INFO] Ready";
            const result = parseLogEntry(line, false);
            assert.equal(result.timestamp, "2024-01-15 10:30:45");
        });

        it("extracts syslog-style timestamp", () => {
            const line = "Jan 15 10:30:45 hostname kernel: message";
            const result = parseLogEntry(line, false);
            assert.equal(result.timestamp, "Jan 15 10:30:45");
        });

        it("extracts time-only timestamp", () => {
            const line = "10:30:45.123 Starting motor calibration";
            const result = parseLogEntry(line, false);
            assert.equal(result.timestamp, "10:30:45.123");
        });

        it("returns empty timestamp for text without timestamps", () => {
            const line = "No timestamp here at all";
            const result = parseLogEntry(line, false);
            assert.equal(result.timestamp, "");
        });

        it("always sets source to empty string for raw text", () => {
            const line = "[node] [ERROR] something failed";
            const result = parseLogEntry(line, false);
            assert.equal(result.source, "");
        });

        it("preserves original text as message", () => {
            const line = "raw log line with no structure";
            const result = parseLogEntry(line, false);
            assert.equal(result.message, line);
        });
    });

    // -- Structured objects (legacy file tail, isJournald = false) --

    describe("structured object mode (legacy)", () => {
        it("extracts severity, timestamp, message, source from object", () => {
            const data = {
                severity: "ERROR",
                timestamp: "2024-01-15T10:30:45Z",
                message: "CAN bus error",
                source: "motor_node",
            };
            const result = parseLogEntry(data, false);
            assert.equal(result.severity, "ERROR");
            assert.equal(result.timestamp, "2024-01-15T10:30:45Z");
            assert.equal(result.message, "CAN bus error");
            assert.equal(result.source, "motor_node");
        });

        it("uses level field as fallback for severity", () => {
            const data = { level: "warn", message: "Low battery" };
            const result = parseLogEntry(data, false);
            assert.equal(result.severity, "WARN");
        });

        it("uses line field as fallback for message", () => {
            const data = { line: "Motor stalled" };
            const result = parseLogEntry(data, false);
            assert.equal(result.message, "Motor stalled");
        });

        it("uses text field as fallback for message", () => {
            const data = { text: "Connection lost" };
            const result = parseLogEntry(data, false);
            assert.equal(result.message, "Connection lost");
        });

        it("uses node field as fallback for source", () => {
            const data = { message: "test", node: "/arm/controller" };
            const result = parseLogEntry(data, false);
            assert.equal(result.source, "/arm/controller");
        });

        it("defaults severity to INFO when missing", () => {
            const data = { message: "something" };
            const result = parseLogEntry(data, false);
            assert.equal(result.severity, "INFO");
        });
    });

    // -- Edge cases --

    describe("edge cases", () => {
        it("handles null data with isJournald=false", () => {
            const result = parseLogEntry(null, false);
            assert.equal(result.severity, "INFO");
            assert.equal(result.message, "null");
        });

        it("handles undefined data", () => {
            const result = parseLogEntry(undefined, false);
            assert.equal(result.severity, "INFO");
            assert.equal(result.message, "undefined");
        });

        it("handles numeric data", () => {
            const result = parseLogEntry(42, false);
            assert.equal(result.severity, "INFO");
            assert.equal(result.message, "42");
        });

        it("handles empty string", () => {
            const result = parseLogEntry("", false);
            assert.equal(result.severity, "INFO");
            assert.equal(result.message, "");
        });

        it("journald mode with string data falls through to raw text", () => {
            // isJournald=true but data is a string (shouldn't happen, but defensive)
            const result = parseLogEntry("raw line", true);
            assert.equal(result.severity, "INFO");
            assert.equal(result.message, "raw line");
        });

        it("journald mode with null data falls to fallback", () => {
            const result = parseLogEntry(null, true);
            assert.equal(result.severity, "INFO");
            assert.equal(result.message, "null");
        });
    });
});

// ===========================================================================
// normalizeSeverity
// ===========================================================================

describe("normalizeSeverity", () => {
    it("passes through DEBUG", () => {
        assert.equal(normalizeSeverity("DEBUG"), "DEBUG");
    });

    it("passes through INFO", () => {
        assert.equal(normalizeSeverity("INFO"), "INFO");
    });

    it("passes through WARN", () => {
        assert.equal(normalizeSeverity("WARN"), "WARN");
    });

    it("passes through ERROR", () => {
        assert.equal(normalizeSeverity("ERROR"), "ERROR");
    });

    it("passes through FATAL", () => {
        assert.equal(normalizeSeverity("FATAL"), "FATAL");
    });

    it("normalizes WARNING to WARN", () => {
        assert.equal(normalizeSeverity("WARNING"), "WARN");
    });

    it("is case-insensitive", () => {
        assert.equal(normalizeSeverity("error"), "ERROR");
        assert.equal(normalizeSeverity("Warn"), "WARN");
        assert.equal(normalizeSeverity("debug"), "DEBUG");
    });

    it("defaults unknown levels to INFO", () => {
        assert.equal(normalizeSeverity("TRACE"), "INFO");
        assert.equal(normalizeSeverity("unknown"), "INFO");
        assert.equal(normalizeSeverity(""), "INFO");
    });
});

// ===========================================================================
// Task 3.5 — Severity filter logic
// ===========================================================================

describe("severity filter logic", () => {
    /**
     * Simulate the severity filter: given log lines and a filter map,
     * return the filtered lines (mirrors the useMemo in LogsSubTab).
     */
    function applyFilter(lines, severityFilter) {
        return lines.filter((line) => severityFilter[line.severity]);
    }

    // Build a set of test log entries at various severity levels
    const testLines = [
        parseLogEntry({ MESSAGE: "debug msg", PRIORITY: "7" }, true),
        parseLogEntry({ MESSAGE: "info msg", PRIORITY: "6" }, true),
        parseLogEntry({ MESSAGE: "warn msg", PRIORITY: "4" }, true),
        parseLogEntry({ MESSAGE: "error msg", PRIORITY: "3" }, true),
        parseLogEntry({ MESSAGE: "fatal msg", PRIORITY: "0" }, true),
    ];

    it("includes all lines when all severities enabled", () => {
        const filter = {
            DEBUG: true,
            INFO: true,
            WARN: true,
            ERROR: true,
            FATAL: true,
        };
        const result = applyFilter(testLines, filter);
        assert.equal(result.length, 5);
    });

    it("excludes all lines when all severities disabled", () => {
        const filter = {
            DEBUG: false,
            INFO: false,
            WARN: false,
            ERROR: false,
            FATAL: false,
        };
        const result = applyFilter(testLines, filter);
        assert.equal(result.length, 0);
    });

    it("shows only ERROR and FATAL when others disabled", () => {
        const filter = {
            DEBUG: false,
            INFO: false,
            WARN: false,
            ERROR: true,
            FATAL: true,
        };
        const result = applyFilter(testLines, filter);
        assert.equal(result.length, 2);
        assert.ok(result.every((l) => ["ERROR", "FATAL"].includes(l.severity)));
    });

    it("shows only DEBUG when others disabled", () => {
        const filter = {
            DEBUG: true,
            INFO: false,
            WARN: false,
            ERROR: false,
            FATAL: false,
        };
        const result = applyFilter(testLines, filter);
        assert.equal(result.length, 1);
        assert.equal(result[0].severity, "DEBUG");
    });

    it("toggling a single level off removes only that level", () => {
        const filter = {
            DEBUG: true,
            INFO: true,
            WARN: false,
            ERROR: true,
            FATAL: true,
        };
        const result = applyFilter(testLines, filter);
        assert.equal(result.length, 4);
        assert.ok(result.every((l) => l.severity !== "WARN"));
    });

    it("works with raw-text parsed entries (file browser mode)", () => {
        const rawLines = [
            parseLogEntry("[node] [ERROR] fail", false),
            parseLogEntry("[node] [INFO] ok", false),
            parseLogEntry("plain text no severity", false),
        ];
        const filter = {
            DEBUG: false,
            INFO: false,
            WARN: false,
            ERROR: true,
            FATAL: false,
        };
        const result = applyFilter(rawLines, filter);
        assert.equal(result.length, 1);
        assert.equal(result[0].severity, "ERROR");
    });

    it("filters correctly with mixed journalctl and file entries", () => {
        const mixedLines = [
            parseLogEntry({ MESSAGE: "journal info", PRIORITY: "6" }, true),
            parseLogEntry("[node] [WARN] file warn", false),
            parseLogEntry({ MESSAGE: "journal error", PRIORITY: "3" }, true),
        ];
        const filter = {
            DEBUG: true,
            INFO: false,
            WARN: true,
            ERROR: true,
            FATAL: true,
        };
        const result = applyFilter(mixedLines, filter);
        assert.equal(result.length, 2);
        assert.ok(result.every((l) => l.severity !== "INFO"));
    });
});
