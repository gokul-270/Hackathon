/**
 * Chart.js ESM wrapper
 *
 * The UMD bundle (chart.umd.js) is loaded via a <script> tag in index.html
 * before any ES modules run. This wrapper re-exports window.Chart so that
 * application code can use ES module imports:
 *
 *   import { Chart } from 'chart.js/auto';
 */
const Chart = window.Chart;
export { Chart };
export default Chart;
