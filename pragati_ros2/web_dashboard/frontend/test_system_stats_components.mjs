#!/usr/bin/env node
/**
 * Unit tests for StatusHealthTab system stats components.
 * Run: node --test web_dashboard/frontend/test_system_stats_components.mjs
 *
 * Since these components import from 'preact', 'htm/preact' (bare specifiers
 * resolved by browser import maps, not available in Node.js), we cannot import
 * the modules directly. Instead we:
 *   - Extract and eval pure functions (metricSeverity, tempSeverity, clampPercent)
 *   - Parse source files to verify exports, prop handling, and component contracts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const COMPONENTS_DIR = join(__dirname, "js", "components");

// ===========================================================================
// Helper — read component source
// ===========================================================================

function readComponent(filename) {
    const filepath = join(COMPONENTS_DIR, filename);
    return readFileSync(filepath, "utf-8");
}

// ===========================================================================
// Helper — extract pure functions from StatusHealthTab source
// ===========================================================================

function extractFunction(src, name, args) {
    const pattern = new RegExp(
        `function ${name}\\(${args}\\) \\{([\\s\\S]*?)\\n\\}`
    );
    const match = src.match(pattern);
    if (!match) {
        throw new Error(`Could not extract function '${name}' from source`);
    }
    const body = match[1];
    const factory = new Function(
        `function ${name}(${args}) {${body}\n}\nreturn ${name};`
    );
    return factory();
}

const src = readComponent("StatusHealthTab.mjs");

const clampPercent = extractFunction(src, "clampPercent", "val");
const metricSeverity = extractFunction(src, "metricSeverity", "pct");
const tempSeverity = extractFunction(src, "tempSeverity", "temp");

// ===========================================================================
// 5.1 — Sparkline history accumulation
// ===========================================================================
describe("Sparkline history accumulation", () => {
    it("SPARKLINE_MAX_POINTS constant is 30", () => {
        assert.ok(
            src.includes("const SPARKLINE_MAX_POINTS = 30"),
            "Expected SPARKLINE_MAX_POINTS = 30"
        );
    });

    it("Sparkline function is exported", () => {
        assert.ok(
            /export\s*\{[^}]*Sparkline[^}]*\}/.test(src),
            "Expected Sparkline in export block"
        );
    });

    it("Sparkline shows placeholder for <2 data points", () => {
        assert.ok(
            src.includes("Collecting data..."),
            "Expected 'Collecting data...' placeholder text"
        );
    });

    it("Sparkline checks data.length < 2 for placeholder", () => {
        assert.ok(
            src.includes("data.length < 2"),
            "Expected data.length < 2 guard"
        );
    });

    it("Sparkline generates SVG polyline for sufficient data", () => {
        assert.ok(
            src.includes("<polyline"),
            "Expected <polyline in Sparkline SVG output"
        );
        assert.ok(
            src.includes("sparkline-svg"),
            "Expected sparkline-svg CSS class on SVG element"
        );
    });

    it("pushHistory clips array to SPARKLINE_MAX_POINTS", () => {
        // Simulate the pushHistory logic from StatusHealthTab:
        //   ref.current = [...ref.current.slice(-(SPARKLINE_MAX_POINTS - 1)), value];
        const SPARKLINE_MAX_POINTS = 30;
        const ref = { current: [] };

        const pushHistory = (r, value) => {
            if (value != null && !isNaN(value)) {
                r.current = [
                    ...r.current.slice(-(SPARKLINE_MAX_POINTS - 1)),
                    value,
                ];
            }
        };

        // Push 35 values
        for (let i = 1; i <= 35; i++) {
            pushHistory(ref, i);
        }

        assert.equal(
            ref.current.length,
            SPARKLINE_MAX_POINTS,
            `Expected ${SPARKLINE_MAX_POINTS} points, got ${ref.current.length}`
        );
        // Oldest values should be dropped: first element should be 6 (35 - 30 + 1)
        assert.equal(
            ref.current[0],
            6,
            `Expected first element to be 6, got ${ref.current[0]}`
        );
        assert.equal(
            ref.current[ref.current.length - 1],
            35,
            "Expected last element to be 35"
        );
    });

    it("pushHistory ignores null values", () => {
        const SPARKLINE_MAX_POINTS = 30;
        const ref = { current: [1, 2, 3] };

        const pushHistory = (r, value) => {
            if (value != null && !isNaN(value)) {
                r.current = [
                    ...r.current.slice(-(SPARKLINE_MAX_POINTS - 1)),
                    value,
                ];
            }
        };

        pushHistory(ref, null);
        assert.equal(ref.current.length, 3, "Null should not be appended");
        assert.deepEqual(ref.current, [1, 2, 3]);
    });

    it("pushHistory ignores NaN values", () => {
        const SPARKLINE_MAX_POINTS = 30;
        const ref = { current: [1, 2] };

        const pushHistory = (r, value) => {
            if (value != null && !isNaN(value)) {
                r.current = [
                    ...r.current.slice(-(SPARKLINE_MAX_POINTS - 1)),
                    value,
                ];
            }
        };

        pushHistory(ref, NaN);
        assert.equal(ref.current.length, 2, "NaN should not be appended");
    });

    it("pushHistory ignores undefined values", () => {
        const SPARKLINE_MAX_POINTS = 30;
        const ref = { current: [10] };

        const pushHistory = (r, value) => {
            if (value != null && !isNaN(value)) {
                r.current = [
                    ...r.current.slice(-(SPARKLINE_MAX_POINTS - 1)),
                    value,
                ];
            }
        };

        pushHistory(ref, undefined);
        assert.equal(
            ref.current.length,
            1,
            "Undefined should not be appended"
        );
    });

    it("pushHistory works correctly at boundary (exactly MAX_POINTS)", () => {
        const SPARKLINE_MAX_POINTS = 30;
        const ref = { current: [] };

        const pushHistory = (r, value) => {
            if (value != null && !isNaN(value)) {
                r.current = [
                    ...r.current.slice(-(SPARKLINE_MAX_POINTS - 1)),
                    value,
                ];
            }
        };

        // Push exactly 30 values
        for (let i = 1; i <= 30; i++) {
            pushHistory(ref, i);
        }
        assert.equal(ref.current.length, 30);
        assert.equal(ref.current[0], 1);
        assert.equal(ref.current[29], 30);

        // Push one more — should drop first
        pushHistory(ref, 31);
        assert.equal(ref.current.length, 30);
        assert.equal(ref.current[0], 2);
        assert.equal(ref.current[29], 31);
    });

    it("source contains pushHistory with SPARKLINE_MAX_POINTS guard", () => {
        assert.ok(
            src.includes("SPARKLINE_MAX_POINTS - 1"),
            "Expected slice using SPARKLINE_MAX_POINTS - 1"
        );
    });

    it("Sparkline uses viewBox and preserveAspectRatio", () => {
        assert.ok(
            src.includes('preserveAspectRatio="none"'),
            "Expected preserveAspectRatio='none' on SVG"
        );
        assert.ok(
            src.includes("viewBox="),
            "Expected viewBox attribute on SVG"
        );
    });
});

// ===========================================================================
// 5.2 — Threshold calculations
// ===========================================================================
describe("Threshold calculations — metricSeverity", () => {
    it("returns unavailable for null", () => {
        assert.equal(metricSeverity(null), "entity-metric-unavailable");
    });

    it("returns unavailable for undefined", () => {
        assert.equal(metricSeverity(undefined), "entity-metric-unavailable");
    });

    it("returns unavailable for NaN", () => {
        assert.equal(metricSeverity(NaN), "entity-metric-unavailable");
    });

    it("returns ok for 50%", () => {
        assert.equal(metricSeverity(50), "entity-metric-ok");
    });

    it("returns ok for 0%", () => {
        assert.equal(metricSeverity(0), "entity-metric-ok");
    });

    it("returns warning for 75% (>70)", () => {
        assert.equal(metricSeverity(75), "entity-metric-warning");
    });

    it("returns critical for 95% (>90)", () => {
        assert.equal(metricSeverity(95), "entity-metric-critical");
    });

    it("returns ok at boundary 70% (NOT >70)", () => {
        assert.equal(metricSeverity(70), "entity-metric-ok");
    });

    it("returns warning at boundary 90% (>70 but NOT >90)", () => {
        assert.equal(metricSeverity(90), "entity-metric-warning");
    });

    it("returns critical for 100%", () => {
        assert.equal(metricSeverity(100), "entity-metric-critical");
    });

    it("returns warning for 71% (just above threshold)", () => {
        assert.equal(metricSeverity(71), "entity-metric-warning");
    });

    it("returns critical for 91% (just above threshold)", () => {
        assert.equal(metricSeverity(91), "entity-metric-critical");
    });
});

describe("Threshold calculations — tempSeverity", () => {
    it("returns ok for 40C", () => {
        assert.equal(tempSeverity(40), "entity-metric-ok");
    });

    it("returns ok at boundary 65C (NOT >65)", () => {
        assert.equal(tempSeverity(65), "entity-metric-ok");
    });

    it("returns warning for 70C (>65)", () => {
        assert.equal(tempSeverity(70), "entity-metric-warning");
    });

    it("returns warning at boundary 80C (NOT >80)", () => {
        assert.equal(tempSeverity(80), "entity-metric-warning");
    });

    it("returns critical for 85C (>80)", () => {
        assert.equal(tempSeverity(85), "entity-metric-critical");
    });

    it("returns ok for 0C", () => {
        assert.equal(tempSeverity(0), "entity-metric-ok");
    });

    it("returns critical for 100C", () => {
        assert.equal(tempSeverity(100), "entity-metric-critical");
    });
});

describe("Threshold calculations — clampPercent", () => {
    it("returns 0 for null", () => {
        assert.equal(clampPercent(null), 0);
    });

    it("returns 0 for undefined", () => {
        assert.equal(clampPercent(undefined), 0);
    });

    it("returns 0 for NaN", () => {
        assert.equal(clampPercent(NaN), 0);
    });

    it("clamps negative values to 0", () => {
        assert.equal(clampPercent(-10), 0);
    });

    it("clamps values above 100 to 100", () => {
        assert.equal(clampPercent(150), 100);
    });

    it("passes through 50", () => {
        assert.equal(clampPercent(50), 50);
    });

    it("passes through 0", () => {
        assert.equal(clampPercent(0), 0);
    });

    it("passes through 100", () => {
        assert.equal(clampPercent(100), 100);
    });
});

describe("THRESHOLDS constant", () => {
    it("defines cpu thresholds", () => {
        assert.ok(src.includes("cpu: { warning: 70, critical: 90 }"));
    });

    it("defines memory thresholds", () => {
        assert.ok(src.includes("memory: { warning: 80, critical: 95 }"));
    });

    it("defines temp thresholds", () => {
        assert.ok(src.includes("temp: { warning: 65, critical: 80 }"));
    });

    it("defines disk thresholds", () => {
        assert.ok(src.includes("disk: { warning: 70, critical: 90 }"));
    });

    it("THRESHOLDS is exported", () => {
        assert.ok(
            /export\s*\{[^}]*THRESHOLDS[^}]*\}/.test(src),
            "Expected THRESHOLDS in export block"
        );
    });
});

describe("MetricGauge threshold visualization", () => {
    it("uses threshold-bar CSS class", () => {
        assert.ok(
            src.includes("threshold-bar"),
            "Expected threshold-bar class"
        );
    });

    it("uses threshold-band CSS class", () => {
        assert.ok(
            src.includes("threshold-band"),
            "Expected threshold-band class"
        );
    });

    it("uses threshold-warning CSS class", () => {
        assert.ok(
            src.includes("threshold-warning"),
            "Expected threshold-warning class"
        );
    });

    it("uses threshold-critical CSS class", () => {
        assert.ok(
            src.includes("threshold-critical"),
            "Expected threshold-critical class"
        );
    });

    it("MetricGauge receives thresholds prop", () => {
        const propsMatch = src.match(
            /function MetricGauge\(\s*\{([^}]+)\}/
        );
        assert.ok(propsMatch, "Expected destructured props in MetricGauge");
        assert.ok(
            propsMatch[1].includes("thresholds"),
            "Expected thresholds prop in MetricGauge"
        );
    });

    it("MetricGauge receives sparklineData prop", () => {
        const propsMatch = src.match(
            /function MetricGauge\(\s*\{([^}]+)\}/
        );
        assert.ok(propsMatch);
        assert.ok(
            propsMatch[1].includes("sparklineData"),
            "Expected sparklineData prop in MetricGauge"
        );
    });
});

// ===========================================================================
// 5.3 — Process table sorting and truncation
// ===========================================================================
describe("ProcessTable source contract", () => {
    it("ProcessTable function is exported", () => {
        assert.ok(
            /export\s*\{[^}]*ProcessTable[^}]*\}/.test(src),
            "Expected ProcessTable in export block"
        );
    });

    it("ProcessTable renders process-table-toggle", () => {
        assert.ok(
            src.includes("process-table-toggle"),
            "Expected process-table-toggle CSS class"
        );
    });

    it("ProcessTable shows 'No process data available' for empty list", () => {
        assert.ok(
            src.includes("No process data available"),
            "Expected empty state message"
        );
    });

    it("ProcessTable shows 'Loading processes...' when loading", () => {
        assert.ok(
            src.includes("Loading processes..."),
            "Expected loading message"
        );
    });

    it("ProcessTable shows 'Failed to load process data' on error", () => {
        assert.ok(
            src.includes("Failed to load process data"),
            "Expected error message"
        );
    });

    it("table has PID column header", () => {
        assert.ok(src.includes(">PID</th>"), "Expected PID column header");
    });

    it("table has Name column header", () => {
        assert.ok(
            src.includes(">Name</th>"),
            "Expected Name column header"
        );
    });

    it("table has CPU% column header", () => {
        assert.ok(
            src.includes(">CPU%</th>"),
            "Expected CPU% column header"
        );
    });

    it("table has Memory (MB) column header", () => {
        assert.ok(
            src.includes(">Memory (MB)</th>"),
            "Expected Memory (MB) column header"
        );
    });

    it("table has Status column header", () => {
        assert.ok(
            src.includes(">Status</th>"),
            "Expected Status column header"
        );
    });

    it("formats cpu_percent with toFixed(1)", () => {
        assert.ok(
            src.includes("cpu_percent || 0).toFixed(1)"),
            "Expected cpu_percent formatted with toFixed(1)"
        );
    });

    it("formats memory_mb with toFixed(1)", () => {
        assert.ok(
            src.includes("memory_mb || 0).toFixed(1)"),
            "Expected memory_mb formatted with toFixed(1)"
        );
    });

    it("shows stale data indicator", () => {
        assert.ok(
            src.includes("Data may be stale"),
            "Expected 'Data may be stale' indicator"
        );
    });

    it("uses proc.pid as row key", () => {
        assert.ok(
            src.includes("key=${proc.pid}"),
            "Expected key=${proc.pid} on table rows"
        );
    });

    it("fetches from /system/processes URL", () => {
        assert.ok(
            src.includes("/system/processes"),
            "Expected /system/processes URL in source"
        );
    });

    it("ProcessTable starts collapsed (useState(false))", () => {
        // Verify expanded state default is false
        const processTableSrc = src.substring(
            src.indexOf("function ProcessTable(")
        );
        const useStateMatch = processTableSrc.match(
            /const \[expanded, setExpanded\] = useState\(false\)/
        );
        assert.ok(
            useStateMatch,
            "Expected useState(false) for expanded state in ProcessTable"
        );
    });

    it("ProcessTable uses process-table CSS class on table", () => {
        assert.ok(
            src.includes("process-table"),
            "Expected process-table CSS class"
        );
    });

    it("ProcessTable has toggle arrow with rotation", () => {
        assert.ok(
            src.includes("rotate(90deg)"),
            "Expected rotate(90deg) for expanded arrow"
        );
        assert.ok(
            src.includes("rotate(0deg)"),
            "Expected rotate(0deg) for collapsed arrow"
        );
    });

    it("ProcessTable heading says 'Top Processes'", () => {
        assert.ok(
            src.includes("Top Processes"),
            "Expected 'Top Processes' heading"
        );
    });
});
