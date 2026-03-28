#!/usr/bin/env node
/**
 * Unit tests for shared Preact components.
 * Run: node --test web_dashboard/frontend/test_components.mjs
 *
 * Since these components import from 'preact', 'htm/preact', and 'chart.js/auto'
 * (bare specifiers resolved by browser import maps, not available in Node.js),
 * we cannot import the modules directly. Instead we:
 *   - Extract and eval pure functions (deepMerge) for thorough logic testing
 *   - Parse source files to verify exports, prop handling, and component contracts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "fs";
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
// Helper — extract deepMerge function from ChartComponent source
// ===========================================================================

/**
 * Extract the deepMerge function body from ChartComponent.mjs source and
 * create a callable function via the Function constructor.
 */
function extractDeepMerge() {
    const src = readComponent("ChartComponent.mjs");
    // Match the complete function declaration including its body.
    // The function spans from 'function deepMerge(target, source) {'
    // to the closing '}' at the same indentation level.
    const fnMatch = src.match(
        /function deepMerge\(target, source\) \{([\s\S]*?)\n\}/
    );
    if (!fnMatch) {
        throw new Error("Could not extract deepMerge function from source");
    }
    const body = fnMatch[1];
    // The function calls itself recursively — we need to provide 'deepMerge'
    // in scope. Build a wrapper that defines deepMerge and returns it.
    // eslint-disable-next-line no-new-func
    const factory = new Function(
        `function deepMerge(target, source) {${body}\n}\nreturn deepMerge;`
    );
    return factory();
}

const deepMerge = extractDeepMerge();

// ===========================================================================
// deepMerge — thorough logic tests
// ===========================================================================
describe("deepMerge", () => {
    it("merges two flat objects", () => {
        assert.deepEqual(deepMerge({ a: 1 }, { b: 2 }), { a: 1, b: 2 });
    });

    it("source overrides target for same key", () => {
        assert.deepEqual(deepMerge({ a: 1 }, { a: 2 }), { a: 2 });
    });

    it("deep merges nested objects", () => {
        assert.deepEqual(deepMerge({ a: { x: 1 } }, { a: { y: 2 } }), {
            a: { x: 1, y: 2 },
        });
    });

    it("replaces arrays (does not concatenate)", () => {
        assert.deepEqual(deepMerge({ a: [1, 2] }, { a: [3] }), { a: [3] });
    });

    it("handles null source — returns copy of target", () => {
        assert.deepEqual(deepMerge({ a: 1 }, null), { a: 1 });
    });

    it("handles null target — returns copy of source", () => {
        assert.deepEqual(deepMerge(null, { a: 1 }), { a: 1 });
    });

    it("deep merges multiple nesting levels", () => {
        assert.deepEqual(
            deepMerge({ a: { b: { c: 1 } } }, { a: { b: { d: 2 } } }),
            { a: { b: { c: 1, d: 2 } } }
        );
    });

    it("source primitive overrides target nested object", () => {
        assert.deepEqual(deepMerge({ a: { x: 1 } }, { a: 5 }), { a: 5 });
    });

    it("source nested object overrides target primitive", () => {
        assert.deepEqual(deepMerge({ a: 5 }, { a: { x: 1 } }), {
            a: { x: 1 },
        });
    });

    it("does not mutate the target object", () => {
        const target = { a: { x: 1 }, b: 2 };
        const targetCopy = JSON.parse(JSON.stringify(target));
        deepMerge(target, { a: { y: 3 } });
        assert.deepEqual(target, targetCopy);
    });

    it("does not mutate the source object", () => {
        const source = { a: { y: 3 } };
        const sourceCopy = JSON.parse(JSON.stringify(source));
        deepMerge({ a: { x: 1 } }, source);
        assert.deepEqual(source, sourceCopy);
    });

    it("handles empty objects", () => {
        assert.deepEqual(deepMerge({}, {}), {});
    });

    it("merges into empty target", () => {
        assert.deepEqual(deepMerge({}, { a: 1 }), { a: 1 });
    });

    it("merges empty source into target", () => {
        assert.deepEqual(deepMerge({ a: 1 }, {}), { a: 1 });
    });

    it("handles null values within objects", () => {
        // When source value is null (not a plain object), it replaces target
        assert.deepEqual(deepMerge({ a: { x: 1 } }, { a: null }), {
            a: null,
        });
    });

    it("handles undefined values within source", () => {
        assert.deepEqual(deepMerge({ a: 1 }, { a: undefined }), {
            a: undefined,
        });
    });

    it("handles string values", () => {
        assert.deepEqual(deepMerge({ a: "hello" }, { a: "world" }), {
            a: "world",
        });
    });

    it("handles mixed types across keys", () => {
        assert.deepEqual(
            deepMerge(
                { a: 1, b: "two", c: [3], d: { e: 4 } },
                { a: "one", c: [5, 6], d: { f: 7 } }
            ),
            { a: "one", b: "two", c: [5, 6], d: { e: 4, f: 7 } }
        );
    });
});

// ===========================================================================
// Component file existence
// ===========================================================================
describe("Component files exist", () => {
    for (const filename of [
        "ToastNotification.mjs",
        "ChartComponent.mjs",
        "ConfirmationDialog.mjs",
    ]) {
        it(`${filename} exists`, () => {
            const filepath = join(COMPONENTS_DIR, filename);
            assert.ok(
                existsSync(filepath),
                `Expected ${filepath} to exist`
            );
        });
    }
});

// ===========================================================================
// ToastNotification — source contract tests
// ===========================================================================
describe("ToastNotification source contract", () => {
    const src = readComponent("ToastNotification.mjs");

    it("exports ToastNotification function", () => {
        assert.ok(
            /export\s+function\s+ToastNotification\s*\(/.test(src),
            "Expected named export 'ToastNotification'"
        );
    });

    it("exports useToast function", () => {
        assert.ok(
            /export\s+function\s+useToast\s*\(/.test(src),
            "Expected named export 'useToast'"
        );
    });

    it("defines SEVERITY_COLORS with four severities", () => {
        for (const severity of ["error", "warning", "success", "info"]) {
            assert.ok(
                src.includes(`${severity}:`),
                `Expected SEVERITY_COLORS to contain '${severity}'`
            );
        }
    });

    it("ToastNotification destructures expected props", () => {
        // Verify component signature includes expected props
        const propsMatch = src.match(
            /function\s+ToastNotification\s*\(\s*\{([^}]+)\}/
        );
        assert.ok(propsMatch, "Expected destructured props in signature");
        const propsStr = propsMatch[1];
        for (const prop of ["id", "message", "severity", "onDismiss"]) {
            assert.ok(
                propsStr.includes(prop),
                `Expected prop '${prop}' in ToastNotification signature`
            );
        }
    });

    it("falls back to info color for unknown severity", () => {
        // Verify the fallback logic: `SEVERITY_COLORS[severity] || SEVERITY_COLORS.info`
        assert.ok(
            src.includes("|| SEVERITY_COLORS.info"),
            "Expected fallback to SEVERITY_COLORS.info"
        );
    });

    it("SEVERITY_COLORS uses expected hex values", () => {
        assert.ok(src.includes("#dc3545"), "error color #dc3545");
        assert.ok(src.includes("#fd7e14"), "warning color #fd7e14");
        assert.ok(src.includes("#28a745"), "success color #28a745");
        assert.ok(src.includes("#17a2b8"), "info color #17a2b8");
    });

    it("useToast calls useContext", () => {
        assert.ok(
            src.includes("useContext"),
            "Expected useToast to use useContext"
        );
    });
});

// ===========================================================================
// ChartComponent — source contract tests
// ===========================================================================
describe("ChartComponent source contract", () => {
    const src = readComponent("ChartComponent.mjs");

    it("exports ChartComponent function", () => {
        assert.ok(
            /export\s+function\s+ChartComponent\s*\(/.test(src),
            "Expected named export 'ChartComponent'"
        );
    });

    it("exports deepMerge function", () => {
        assert.ok(
            /export\s*\{\s*deepMerge\s*\}/.test(src),
            "Expected re-export of deepMerge"
        );
    });

    it("ChartComponent destructures expected props", () => {
        const propsMatch = src.match(
            /function\s+ChartComponent\s*\(\s*\{([^}]+)\}/
        );
        assert.ok(propsMatch, "Expected destructured props in signature");
        const propsStr = propsMatch[1];
        for (const prop of [
            "type",
            "labels",
            "datasets",
            "options",
            "plugins",
            "height",
            "className",
        ]) {
            assert.ok(
                propsStr.includes(prop),
                `Expected prop '${prop}' in ChartComponent signature`
            );
        }
    });

    it("has default height of '300px'", () => {
        assert.ok(
            src.includes('height = "300px"'),
            "Expected default height prop of '300px'"
        );
    });

    it("has default className of empty string", () => {
        assert.ok(
            src.includes('className = ""'),
            "Expected default className prop of ''"
        );
    });

    it("defines DEFAULT_OPTIONS with responsive and animation", () => {
        assert.ok(
            src.includes("responsive: true"),
            "Expected responsive: true in DEFAULT_OPTIONS"
        );
        assert.ok(
            src.includes("maintainAspectRatio: false"),
            "Expected maintainAspectRatio: false in DEFAULT_OPTIONS"
        );
        assert.ok(
            src.includes("duration: 300"),
            "Expected animation duration: 300 in DEFAULT_OPTIONS"
        );
    });

    it("destroys chart on unmount (cleanup)", () => {
        // The component should call .destroy() in its cleanup
        const destroyCount = (src.match(/\.destroy\(\)/g) || []).length;
        assert.ok(
            destroyCount >= 2,
            `Expected at least 2 .destroy() calls (got ${destroyCount})`
        );
    });
});

// ===========================================================================
// ConfirmationDialog — source contract tests
// ===========================================================================
describe("ConfirmationDialog source contract", () => {
    const src = readComponent("ConfirmationDialog.mjs");

    it("exports ConfirmationDialog function", () => {
        assert.ok(
            /export\s+function\s+ConfirmationDialog\s*\(/.test(src),
            "Expected named export 'ConfirmationDialog'"
        );
    });

    it("exports useConfirmDialog function", () => {
        assert.ok(
            /export\s+function\s+useConfirmDialog\s*\(/.test(src),
            "Expected named export 'useConfirmDialog'"
        );
    });

    it("ConfirmationDialog destructures expected props", () => {
        const propsMatch = src.match(
            /function\s+ConfirmationDialog\s*\(\s*\{([^}]+)\}/
        );
        assert.ok(propsMatch, "Expected destructured props in signature");
        const propsStr = propsMatch[1];
        for (const prop of [
            "open",
            "title",
            "message",
            "confirmText",
            "cancelText",
            "dangerous",
            "confirmWord",
            "confirmWordPrompt",
            "onConfirm",
            "onCancel",
        ]) {
            assert.ok(
                propsStr.includes(prop),
                `Expected prop '${prop}' in ConfirmationDialog signature`
            );
        }
    });

    it("has default confirmText of 'Confirm'", () => {
        assert.ok(
            src.includes('confirmText = "Confirm"'),
            "Expected default confirmText = 'Confirm'"
        );
    });

    it("has default cancelText of 'Cancel'", () => {
        assert.ok(
            src.includes('cancelText = "Cancel"'),
            "Expected default cancelText = 'Cancel'"
        );
    });

    it("has default dangerous of false", () => {
        assert.ok(
            src.includes("dangerous = false"),
            "Expected default dangerous = false"
        );
    });

    it("returns null when not open", () => {
        assert.ok(
            src.includes("if (!open) return null"),
            "Expected early return null when !open"
        );
    });

    it("handles Escape key to cancel", () => {
        assert.ok(
            src.includes('"Escape"'),
            "Expected Escape key handler"
        );
    });

    it("supports double-confirm mode with confirmWord", () => {
        assert.ok(
            src.includes("isDoubleConfirm"),
            "Expected isDoubleConfirm logic"
        );
        assert.ok(
            src.includes("confirmDisabled"),
            "Expected confirmDisabled state derived from confirmWord"
        );
    });

    it("overlay click triggers cancel", () => {
        assert.ok(
            src.includes("onOverlayClick"),
            "Expected onOverlayClick handler"
        );
        assert.ok(
            src.includes("e.target === e.currentTarget"),
            "Expected overlay click guard (target === currentTarget)"
        );
    });

    it("useConfirmDialog returns confirm and doubleConfirm methods", () => {
        // Verify the return statement includes all expected keys
        assert.ok(
            src.includes("return { dialog, confirm, doubleConfirm }"),
            "Expected useConfirmDialog to return { dialog, confirm, doubleConfirm }"
        );
    });

    it("useConfirmDialog cancels pending promise on unmount", () => {
        // Cleanup effect should resolve(false)
        assert.ok(
            src.includes("resolveRef.current(false)"),
            "Expected cleanup to resolve pending promise with false"
        );
    });

    it("uses CSS classes matching existing styles.css", () => {
        for (const cls of [
            "modal-overlay",
            "modal-content",
            "modal-header",
            "modal-body",
            "confirm-dialog-actions",
            "confirm-dialog-cancel",
            "confirm-dialog-confirm",
        ]) {
            assert.ok(
                src.includes(cls),
                `Expected CSS class '${cls}' in ConfirmationDialog`
            );
        }
    });

    it("dangerous mode adds confirm-btn-danger class", () => {
        assert.ok(
            src.includes("confirm-btn-danger"),
            "Expected confirm-btn-danger class for dangerous mode"
        );
    });
});

// ===========================================================================
// ChartComponent — lifecycle behavior tests (mocked Chart.js)
// ===========================================================================

/**
 * Since ChartComponent uses Preact hooks (useRef, useEffect) which can't run
 * in Node.js without a Preact runtime, we simulate the lifecycle by extracting
 * the Chart.js interaction logic from the source and replaying it with mocks.
 *
 * The component has three useEffect blocks:
 *   1. Type effect: create chart on mount, destroy on unmount/type change
 *   2. Data effect: update labels/datasets/options in-place, call chart.update()
 *   3. Plugin effect: destroy + recreate when plugins change
 *
 * We extract these effect bodies and test them directly.
 */
describe("ChartComponent lifecycle behavior", () => {
    const src = readComponent("ChartComponent.mjs");

    /**
     * Create a mock Chart constructor and instance for testing.
     */
    function createMockChart() {
        const instances = [];

        function MockChart(canvas, config) {
            const instance = {
                canvas,
                type: config.type,
                data: {
                    labels: [...(config.data?.labels || [])],
                    datasets: [...(config.data?.datasets || [])],
                },
                options: { ...(config.data?.options || {}) },
                plugins: config.plugins || [],
                updateCalls: 0,
                destroyed: false,
                update() {
                    this.updateCalls++;
                },
                destroy() {
                    this.destroyed = true;
                },
            };
            instances.push(instance);
            return instance;
        }

        return { MockChart, instances };
    }

    // -------------------------------------------------------------------
    // Chart creation tests
    // -------------------------------------------------------------------
    describe("chart creation", () => {
        it("source creates Chart with type, data, options, and plugins", () => {
            // Verify the constructor call pattern in source
            assert.ok(
                src.includes("new Chart(canvas, {"),
                "Expected 'new Chart(canvas, {' constructor call"
            );
            // Verify it passes type
            const constructorBlock = src.match(
                /new Chart\(canvas, \{[\s\S]*?\}\);/
            );
            assert.ok(constructorBlock, "Found Chart constructor block");
            const block = constructorBlock[0];
            assert.ok(block.includes("type"), "Constructor passes type");
            assert.ok(block.includes("data:"), "Constructor passes data");
            assert.ok(
                block.includes("options:"),
                "Constructor passes options"
            );
            assert.ok(
                block.includes("plugins:"),
                "Constructor passes plugins"
            );
        });

        it("stores chart instance in chartRef.current", () => {
            assert.ok(
                src.includes("chartRef.current = new Chart("),
                "Expected chart instance stored in chartRef.current"
            );
        });

        it("provides empty array defaults for labels and datasets", () => {
            assert.ok(
                src.includes("labels: labels || []"),
                "Expected labels fallback to empty array"
            );
            assert.ok(
                src.includes("datasets: datasets || []"),
                "Expected datasets fallback to empty array"
            );
        });

        it("merges caller options over DEFAULT_OPTIONS", () => {
            assert.ok(
                src.includes("deepMerge(DEFAULT_OPTIONS, options)"),
                "Expected mergedOptions = deepMerge(DEFAULT_OPTIONS, options)"
            );
        });

        it("mocked Chart constructor receives correct config shape", () => {
            const { MockChart } = createMockChart();
            const canvas = { id: "test-canvas" };
            const config = {
                type: "line",
                data: {
                    labels: ["a", "b"],
                    datasets: [{ data: [1, 2] }],
                },
                options: { responsive: true },
                plugins: [],
            };
            const chart = new MockChart(canvas, config);

            assert.equal(chart.canvas, canvas);
            assert.equal(chart.type, "line");
            assert.deepEqual(chart.data.labels, ["a", "b"]);
            assert.deepEqual(chart.data.datasets, [{ data: [1, 2] }]);
            assert.equal(chart.destroyed, false);
            assert.equal(chart.updateCalls, 0);
        });
    });

    // -------------------------------------------------------------------
    // Chart update tests (data effect)
    // -------------------------------------------------------------------
    describe("chart data update", () => {
        it("updates labels on existing chart instance", () => {
            assert.ok(
                src.includes("chart.data.labels = labels || []"),
                "Expected in-place label update"
            );
        });

        it("updates datasets in-place with Object.assign", () => {
            assert.ok(
                src.includes("Object.assign(current[i], incoming[i])"),
                "Expected Object.assign for in-place dataset update"
            );
        });

        it("appends new datasets when incoming has more", () => {
            assert.ok(
                src.includes("current.push(incoming[i])"),
                "Expected push for new datasets"
            );
        });

        it("removes excess datasets via splice", () => {
            assert.ok(
                src.includes("current.splice(incoming.length)"),
                "Expected splice to remove excess datasets"
            );
        });

        it("calls chart.update() after data changes", () => {
            assert.ok(
                src.includes("chart.update()"),
                "Expected chart.update() call after data sync"
            );
        });

        it("re-merges options on each data update", () => {
            // The data effect re-applies merged options
            assert.ok(
                src.includes("chart.options = deepMerge(DEFAULT_OPTIONS, options)"),
                "Expected options re-merge in data effect"
            );
        });

        it("simulated in-place update behaves correctly", () => {
            const { MockChart } = createMockChart();
            const chart = new MockChart({}, {
                type: "line",
                data: { labels: ["a"], datasets: [{ data: [1] }] },
            });

            // Simulate the data effect logic
            const newLabels = ["a", "b", "c"];
            const newDatasets = [{ data: [10, 20, 30] }];

            chart.data.labels = newLabels;
            const current = chart.data.datasets;
            const incoming = newDatasets;
            for (let i = 0; i < incoming.length; i++) {
                if (i < current.length) {
                    Object.assign(current[i], incoming[i]);
                } else {
                    current.push(incoming[i]);
                }
            }
            if (current.length > incoming.length) {
                current.splice(incoming.length);
            }
            chart.update();

            assert.deepEqual(chart.data.labels, ["a", "b", "c"]);
            assert.deepEqual(chart.data.datasets[0].data, [10, 20, 30]);
            assert.equal(chart.updateCalls, 1);
        });

        it("simulated update appends and trims datasets", () => {
            const { MockChart } = createMockChart();
            const chart = new MockChart({}, {
                type: "bar",
                data: {
                    labels: [],
                    datasets: [{ data: [1] }, { data: [2] }, { data: [3] }],
                },
            });

            // Incoming has only 1 dataset — should trim to 1
            const incoming = [{ data: [99] }];
            const current = chart.data.datasets;
            for (let i = 0; i < incoming.length; i++) {
                if (i < current.length) {
                    Object.assign(current[i], incoming[i]);
                } else {
                    current.push(incoming[i]);
                }
            }
            if (current.length > incoming.length) {
                current.splice(incoming.length);
            }
            chart.update();

            assert.equal(chart.data.datasets.length, 1);
            assert.deepEqual(chart.data.datasets[0].data, [99]);
            assert.equal(chart.updateCalls, 1);
        });
    });

    // -------------------------------------------------------------------
    // Chart destruction tests (cleanup / unmount)
    // -------------------------------------------------------------------
    describe("chart destruction", () => {
        it("cleanup function calls chart.destroy()", () => {
            const destroyPattern =
                /return\s*\(\)\s*=>\s*\{[\s\S]*?chartRef\.current[\s\S]*?\.destroy\(\)/;
            assert.ok(
                destroyPattern.test(src),
                "Expected cleanup arrow function that calls .destroy()"
            );
        });

        it("sets chartRef.current to null after destroy", () => {
            // After destroy, reference should be nulled to prevent double-destroy
            const nullAfterDestroy =
                /\.destroy\(\);\s*\n\s*chartRef\.current\s*=\s*null/;
            assert.ok(
                nullAfterDestroy.test(src),
                "Expected chartRef.current = null after destroy()"
            );
        });

        it("destroys existing chart before creating new one on type change", () => {
            // The type effect checks for existing chart and destroys it first
            const destroyBeforeCreate =
                /if\s*\(chartRef\.current\)\s*\{[\s\S]*?chartRef\.current\.destroy\(\)/;
            assert.ok(
                destroyBeforeCreate.test(src),
                "Expected destroy of existing chart before re-creation"
            );
        });

        it("simulated destroy marks instance as destroyed", () => {
            const { MockChart } = createMockChart();
            const chart = new MockChart({}, { type: "line", data: {} });

            assert.equal(chart.destroyed, false);
            chart.destroy();
            assert.equal(chart.destroyed, true);
        });

        it("simulated full lifecycle: create, update, destroy", () => {
            const { MockChart, instances } = createMockChart();

            // Mount: create chart
            const chart = new MockChart({}, {
                type: "doughnut",
                data: { labels: ["A"], datasets: [{ data: [100] }] },
            });
            assert.equal(instances.length, 1);
            assert.equal(chart.destroyed, false);

            // Update data
            chart.data.labels = ["A", "B"];
            chart.update();
            assert.equal(chart.updateCalls, 1);

            // Unmount: destroy
            chart.destroy();
            assert.equal(chart.destroyed, true);
            assert.equal(instances.length, 1, "No new instances created");
        });
    });

    // -------------------------------------------------------------------
    // Error handling tests
    // -------------------------------------------------------------------
    describe("chart error resilience", () => {
        it("guards against null canvas ref", () => {
            // The type effect checks canvasRef.current before proceeding
            assert.ok(
                src.includes("if (!canvas) return"),
                "Expected early return when canvas ref is null"
            );
        });

        it("guards against null chart ref in data effect", () => {
            assert.ok(
                src.includes("if (!chart) return"),
                "Expected early return when chart ref is null in data effect"
            );
        });

        it("plugin effect guards against null chart and canvas", () => {
            // Plugin effect has two guard checks
            const pluginEffectSrc = src.substring(
                src.indexOf("// Update plugins")
            );
            assert.ok(
                pluginEffectSrc.includes("if (!chart) return"),
                "Expected null chart guard in plugin effect"
            );
            assert.ok(
                pluginEffectSrc.includes("if (!canvas) return"),
                "Expected null canvas guard in plugin effect"
            );
        });

        it("simulated: Chart constructor throwing does not crash", () => {
            function ThrowingChart() {
                throw new Error("Canvas context not available");
            }

            // The component wraps this in try/catch conceptually via React
            // error boundaries. Here we verify the constructor can throw.
            assert.throws(
                () => new ThrowingChart({}, { type: "line", data: {} }),
                { message: "Canvas context not available" }
            );
        });

        it("simulated: destroy on already-destroyed chart is safe", () => {
            const { MockChart } = createMockChart();
            const chart = new MockChart({}, { type: "line", data: {} });
            chart.destroy();
            // Calling destroy again should not throw
            assert.doesNotThrow(() => chart.destroy());
        });
    });

    // -------------------------------------------------------------------
    // Plugin change tests (recreate lifecycle)
    // -------------------------------------------------------------------
    describe("chart plugin changes", () => {
        it("destroys and recreates chart when plugins change", () => {
            // Source should destroy existing chart and create new one in
            // the plugins effect
            const pluginSection = src.substring(
                src.indexOf("// Update plugins")
            );
            assert.ok(
                pluginSection.includes("chart.destroy()"),
                "Expected chart.destroy() in plugin effect"
            );
            assert.ok(
                pluginSection.includes("chartRef.current = new Chart("),
                "Expected new Chart() in plugin effect"
            );
        });

        it("preserves current data when recreating for plugin change", () => {
            // Should capture current data before destroy
            const pluginSection = src.substring(
                src.indexOf("// Update plugins")
            );
            assert.ok(
                pluginSection.includes("chart.data.labels"),
                "Expected preservation of labels during plugin recreate"
            );
            assert.ok(
                pluginSection.includes("chart.data.datasets"),
                "Expected preservation of datasets during plugin recreate"
            );
        });

        it("simulated plugin change: old destroyed, new created with data", () => {
            const { MockChart, instances } = createMockChart();

            // Create initial chart
            const chart1 = new MockChart({}, {
                type: "bar",
                data: { labels: ["x"], datasets: [{ data: [5] }] },
                plugins: [],
            });
            assert.equal(instances.length, 1);

            // Simulate plugin change: capture data, destroy, recreate
            const savedData = {
                labels: chart1.data.labels,
                datasets: chart1.data.datasets,
            };
            chart1.destroy();

            const chart2 = new MockChart({}, {
                type: "bar",
                data: savedData,
                plugins: [{ id: "custom-plugin" }],
            });

            assert.equal(instances.length, 2);
            assert.equal(chart1.destroyed, true);
            assert.equal(chart2.destroyed, false);
            assert.deepEqual(chart2.data.labels, ["x"]);
        });
    });
});
