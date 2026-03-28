/**
 * ChartComponent — Preact wrapper for Chart.js lifecycle management.
 *
 * Creates a Chart.js instance on mount, updates datasets in-place on prop
 * changes (preserving animation continuity), and destroys the instance on
 * unmount. This prevents the memory leaks caused by Chart.js instances that
 * are never destroyed during tab navigation.
 *
 * @module components/ChartComponent
 */
import { useRef, useEffect, useMemo } from "preact/hooks";
import { html } from "htm/preact";
import Chart from "chart.js/auto";

// ---------------------------------------------------------------------------
// Default options
// ---------------------------------------------------------------------------

/** @type {import('chart.js').ChartOptions} */
const DEFAULT_OPTIONS = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
        duration: 300,
    },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Deep-merge source into target (target values win where both exist).
 * Arrays are replaced, not concatenated. Plain objects are recursed.
 *
 * @param {object} target - Base object (defaults)
 * @param {object} source - Override object (caller options)
 * @returns {object} New merged object
 */
function deepMerge(target, source) {
    if (!source) return { ...target };
    if (!target) return { ...source };

    const result = { ...target };

    for (const key of Object.keys(source)) {
        const srcVal = source[key];
        const tgtVal = target[key];

        if (
            srcVal !== null &&
            typeof srcVal === "object" &&
            !Array.isArray(srcVal) &&
            tgtVal !== null &&
            typeof tgtVal === "object" &&
            !Array.isArray(tgtVal)
        ) {
            result[key] = deepMerge(tgtVal, srcVal);
        } else {
            result[key] = srcVal;
        }
    }

    return result;
}

// ---------------------------------------------------------------------------
// ChartComponent
// ---------------------------------------------------------------------------

/**
 * Preact component that wraps a Chart.js canvas.
 *
 * @param {object} props
 * @param {string}              props.type       - Chart type: 'line', 'bar', 'doughnut', 'pie', etc.
 * @param {string[]}            props.labels     - X-axis labels
 * @param {object[]}            props.datasets   - Chart.js dataset objects
 * @param {object}              [props.options]   - Chart.js options merged over defaults
 * @param {object[]}            [props.plugins]   - Chart.js plugins array
 * @param {string}              [props.height]    - CSS height for the container (default '300px')
 * @param {string}              [props.className] - Extra CSS class on the wrapper div
 * @returns {import('preact').VNode}
 */
export function ChartComponent({
    type,
    labels,
    datasets,
    options,
    plugins,
    height = "300px",
    className = "",
}) {
    const canvasRef = useRef(null);
    const chartRef = useRef(null);

    // Merge caller options over defaults. Memoize to avoid re-computing on
    // every render when the options object reference is stable.
    const mergedOptions = useMemo(
        () => deepMerge(DEFAULT_OPTIONS, options),
        [options],
    );

    // -----------------------------------------------------------------------
    // Create / recreate chart when the chart TYPE changes.
    // Type changes require a full destroy + create because Chart.js cannot
    // change type on an existing instance.
    // -----------------------------------------------------------------------
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        // Destroy any existing chart before creating a new one
        if (chartRef.current) {
            chartRef.current.destroy();
            chartRef.current = null;
        }

        chartRef.current = new Chart(canvas, {
            type,
            data: {
                labels: labels || [],
                datasets: datasets || [],
            },
            options: mergedOptions,
            plugins: plugins || [],
        });

        // Cleanup: destroy chart on unmount or before type change
        return () => {
            if (chartRef.current) {
                chartRef.current.destroy();
                chartRef.current = null;
            }
        };
    }, [type]); // eslint-disable-line react-hooks/exhaustive-deps

    // -----------------------------------------------------------------------
    // Update data in-place when labels, datasets, or options change.
    // This preserves animation continuity — no destroy/recreate.
    // -----------------------------------------------------------------------
    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        // Update labels
        chart.data.labels = labels || [];

        // Update datasets in-place: reuse existing dataset objects where
        // possible so Chart.js can animate transitions smoothly.
        const current = chart.data.datasets;
        const incoming = datasets || [];

        for (let i = 0; i < incoming.length; i++) {
            if (i < current.length) {
                // Update existing dataset properties in-place
                Object.assign(current[i], incoming[i]);
            } else {
                // New dataset — append
                current.push(incoming[i]);
            }
        }

        // Remove excess datasets
        if (current.length > incoming.length) {
            current.splice(incoming.length);
        }

        // Merge and apply updated options
        chart.options = deepMerge(DEFAULT_OPTIONS, options);

        chart.update();
    }, [labels, datasets, options]);

    // -----------------------------------------------------------------------
    // Update plugins — requires destroy/recreate since Chart.js does not
    // support runtime plugin changes.
    // -----------------------------------------------------------------------
    useEffect(() => {
        const chart = chartRef.current;
        if (!chart) return;

        // Only recreate if we actually have a canvas and this isn't the
        // initial mount (which is handled by the type effect above).
        const canvas = canvasRef.current;
        if (!canvas) return;

        // Chart.js does not allow changing plugins after creation.
        // We must destroy and recreate.
        const currentData = {
            labels: chart.data.labels,
            datasets: chart.data.datasets,
        };

        chart.destroy();

        chartRef.current = new Chart(canvas, {
            type,
            data: currentData,
            options: deepMerge(DEFAULT_OPTIONS, options),
            plugins: plugins || [],
        });
    }, [plugins]); // eslint-disable-line react-hooks/exhaustive-deps

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------
    const wrapperClass = className
        ? `chart-component ${className}`
        : "chart-component";

    return html`
        <div class=${wrapperClass} style=${{ position: "relative", height }}>
            <canvas ref=${canvasRef}></canvas>
        </div>
    `;
}

// Re-export deepMerge for testing
export { deepMerge };
