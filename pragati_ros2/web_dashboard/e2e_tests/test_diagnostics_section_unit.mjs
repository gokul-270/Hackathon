#!/usr/bin/env node
// Diagnostics Section Unit Test — tests DiagnosticsSection UI behavior
// Run: node web_dashboard/e2e_tests/test_diagnostics_section_unit.mjs
//
// Uses Playwright to load the module in a browser context, then mocks
// the fetch API to verify diagnostics section renders correctly, triggers
// the API call on button click, and the export button downloads JSON.
//
// Requires: npm install playwright (in this directory)
// Dashboard must be running on http://127.0.0.1:8090

import { chromium } from 'playwright';

const BASE = 'http://127.0.0.1:8090';
let passed = 0;
let failed = 0;
const failures = [];

function assert(condition, name) {
  if (condition) {
    passed++;
    console.log(`  PASS  ${name}`);
  } else {
    failed++;
    failures.push(name);
    console.log(`  FAIL  ${name}`);
  }
}

(async () => {
  console.log('DiagnosticsSection Unit Tests');
  console.log(`Target: ${BASE}`);
  console.log('====================================\n');

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });

  const page = await browser.newPage();
  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  try {
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    // ================================================================
    // Test: DiagnosticsSection can be imported
    // ================================================================
    console.log('[1] Import DiagnosticsSection from StatusHealthTab.mjs');
    const importResult = await page.evaluate(async () => {
      try {
        const mod = await import('/js/components/StatusHealthTab.mjs');
        return { ok: typeof mod.DiagnosticsSection === 'function' };
      } catch (e) {
        return { ok: false, error: e.message };
      }
    });
    assert(importResult.ok, 'DiagnosticsSection can be imported from StatusHealthTab.mjs');
    if (!importResult.ok) {
      console.log(`  Import error: ${importResult.error}`);
    }

    // ================================================================
    // Test: DiagnosticsSection renders collapsed by default
    // ================================================================
    console.log('\n[2] DiagnosticsSection renders collapsed by default');
    const renderResult = await page.evaluate(async () => {
      try {
        const { DiagnosticsSection } = await import('/js/components/StatusHealthTab.mjs');
        const { render } = await import('preact');
        const { html } = await import('htm/preact');

        const container = document.createElement('div');
        container.id = 'diag-test-collapsed';
        document.body.appendChild(container);

        render(html`<${DiagnosticsSection} />`, container);
        await new Promise((r) => setTimeout(r, 100));

        // Should have Diagnostics heading
        const heading = container.querySelector('h3');
        const hasHeading = heading && heading.textContent.includes('Diagnostics');

        // Should NOT have results yet (no data)
        const hasResults = !!container.querySelector('[data-testid="diagnostics-results"]');

        // Should NOT have run button visible (collapsed)
        const hasRunBtn = Array.from(container.querySelectorAll('button')).some(
          (b) => b.textContent.includes('Run Diagnostics')
        );

        return { hasHeading, hasResults, hasRunBtn };
      } catch (e) {
        return { error: e.message };
      }
    });
    assert(!renderResult.error, `DiagnosticsSection renders without error — ${renderResult.error || 'ok'}`);
    assert(renderResult.hasHeading, 'Diagnostics heading is present');
    assert(!renderResult.hasResults, 'No results rendered in collapsed state');
    assert(!renderResult.hasRunBtn, 'Run button not visible in collapsed state');

    // ================================================================
    // Test: Clicking the header expands the section and shows Run button
    // ================================================================
    console.log('\n[3] Clicking header expands section and shows Run Diagnostics button');
    const expandResult = await page.evaluate(async () => {
      try {
        const { DiagnosticsSection } = await import('/js/components/StatusHealthTab.mjs');
        const { render } = await import('preact');
        const { html } = await import('htm/preact');

        const container = document.createElement('div');
        container.id = 'diag-test-expand';
        document.body.appendChild(container);

        render(html`<${DiagnosticsSection} />`, container);
        await new Promise((r) => setTimeout(r, 100));

        // Click the heading to expand
        const heading = container.querySelector('h3');
        if (!heading) return { error: 'No heading found' };
        heading.closest('div[style]').click();
        await new Promise((r) => setTimeout(r, 200));

        const hasRunBtn = Array.from(container.querySelectorAll('button')).some(
          (b) => b.textContent.includes('Run Diagnostics')
        );
        return { hasRunBtn };
      } catch (e) {
        return { error: e.message };
      }
    });
    assert(!expandResult.error, `Expand click works — ${expandResult.error || 'ok'}`);
    assert(expandResult.hasRunBtn, 'Run Diagnostics button visible after expand');

    // ================================================================
    // Test: Run Diagnostics button triggers fetch to /api/diagnostics/run
    // ================================================================
    console.log('\n[4] Run Diagnostics button triggers API call to /api/diagnostics/run');
    const apiCallResult = await page.evaluate(async () => {
      try {
        const { DiagnosticsSection } = await import('/js/components/StatusHealthTab.mjs');
        const { render } = await import('preact');
        const { html } = await import('htm/preact');

        // Mock fetch to capture calls
        const fetchCalls = [];
        const mockResponse = {
          entities: [
            {
              entity_id: 'arm1',
              entity_name: 'Arm 1 RPi',
              overall: 'pass',
              checks: {
                agent_http: { status: 'pass', latency_ms: 45, message: 'Agent responded in 45ms', fix_hint: null },
                ros2: { status: 'pass', latency_ms: null, message: 'ROS2 nodes visible', fix_hint: null },
                systemd: { status: 'pass', latency_ms: 30, message: 'sudoers configured correctly', fix_hint: null },
                mqtt: { status: 'pass', latency_ms: null, message: 'MQTT connection active', fix_hint: null },
              },
            },
          ],
        };

        const origFetch = globalThis.fetch;
        globalThis.fetch = async (url, opts) => {
          fetchCalls.push(url);
          if (url === '/api/diagnostics/run') {
            return {
              ok: true,
              status: 200,
              json: async () => mockResponse,
              text: async () => JSON.stringify(mockResponse),
            };
          }
          return origFetch(url, opts);
        };

        const container = document.createElement('div');
        container.id = 'diag-test-api';
        document.body.appendChild(container);

        render(html`<${DiagnosticsSection} />`, container);
        await new Promise((r) => setTimeout(r, 100));

        // Expand
        const heading = container.querySelector('h3');
        heading.closest('div[style]').click();
        await new Promise((r) => setTimeout(r, 200));

        // Click Run Diagnostics
        const runBtn = Array.from(container.querySelectorAll('button')).find(
          (b) => b.textContent.includes('Run Diagnostics')
        );
        if (!runBtn) return { error: 'Run button not found after expand' };
        runBtn.click();
        await new Promise((r) => setTimeout(r, 500));

        // Restore fetch
        globalThis.fetch = origFetch;

        const apiCalled = fetchCalls.some((u) => u === '/api/diagnostics/run');
        return { apiCalled, fetchCalls };
      } catch (e) {
        return { error: e.message };
      }
    });
    assert(!apiCallResult.error, `API call test runs — ${apiCallResult.error || 'ok'}`);
    assert(apiCallResult.apiCalled, 'Run Diagnostics button triggers GET /api/diagnostics/run');

    // ================================================================
    // Test: Results display with correct color coding after run
    // ================================================================
    console.log('\n[5] Results display with per-entity cards after run');
    const resultsDisplayResult = await page.evaluate(async () => {
      try {
        const { DiagnosticsSection } = await import('/js/components/StatusHealthTab.mjs');
        const { render } = await import('preact');
        const { html } = await import('htm/preact');

        const mockResponse = {
          entities: [
            {
              entity_id: 'arm1',
              entity_name: 'Arm 1 RPi',
              overall: 'pass',
              checks: {
                agent_http: { status: 'pass', latency_ms: 45, message: 'Agent responded in 45ms', fix_hint: null },
                ros2: { status: 'fail', latency_ms: null, message: 'ROS2 introspection unavailable', fix_hint: 'Check ROS2 is running' },
                systemd: { status: 'pass', latency_ms: 30, message: 'sudoers configured correctly', fix_hint: null },
                mqtt: { status: 'skip', latency_ms: null, message: 'MQTT status: unknown', fix_hint: null },
              },
            },
          ],
        };

        const origFetch = globalThis.fetch;
        globalThis.fetch = async (url, opts) => {
          if (url === '/api/diagnostics/run') {
            return {
              ok: true,
              status: 200,
              json: async () => mockResponse,
              text: async () => JSON.stringify(mockResponse),
            };
          }
          return origFetch(url, opts);
        };

        const container = document.createElement('div');
        container.id = 'diag-test-results';
        document.body.appendChild(container);

        render(html`<${DiagnosticsSection} />`, container);
        await new Promise((r) => setTimeout(r, 100));

        // Expand and run
        const heading = container.querySelector('h3');
        heading.closest('div[style]').click();
        await new Promise((r) => setTimeout(r, 200));

        const runBtn = Array.from(container.querySelectorAll('button')).find(
          (b) => b.textContent.includes('Run Diagnostics')
        );
        runBtn.click();
        await new Promise((r) => setTimeout(r, 500));

        globalThis.fetch = origFetch;

        // Check results rendered
        const resultsDiv = container.querySelector('[data-testid="diagnostics-results"]');
        const entityName = resultsDiv ? resultsDiv.textContent.includes('Arm 1 RPi') : false;
        const hasExportBtn = Array.from(container.querySelectorAll('button')).some(
          (b) => b.textContent.includes('Export JSON')
        );
        // Fix hint should be visible for failed ROS2 check
        const fixHintVisible = container.textContent.includes('Check ROS2 is running');

        return { hasResults: !!resultsDiv, entityName, hasExportBtn, fixHintVisible };
      } catch (e) {
        return { error: e.message };
      }
    });
    assert(!resultsDisplayResult.error, `Results display test runs — ${resultsDisplayResult.error || 'ok'}`);
    assert(resultsDisplayResult.hasResults, 'diagnostics-results container rendered after run');
    assert(resultsDisplayResult.entityName, 'Entity name (Arm 1 RPi) appears in results');
    assert(resultsDisplayResult.hasExportBtn, 'Export JSON button appears after results load');
    assert(resultsDisplayResult.fixHintVisible, 'Fix hint text visible for failed check');

    // ================================================================
    // Test: Export JSON button triggers file download with timestamp filename
    // ================================================================
    console.log('\n[6] Export JSON button triggers download with timestamp filename');
    const exportResult = await page.evaluate(async () => {
      try {
        // Check that the exportJson callback creates a blob URL and clicks an anchor
        let downloadAttempted = false;
        let downloadFilename = '';

        const origCreateObjectURL = URL.createObjectURL;
        URL.createObjectURL = (blob) => {
          downloadAttempted = true;
          return 'blob:mock';
        };

        const origcreateElement = document.createElement.bind(document);
        document.createElement = (tag) => {
          const el = origCreateElement(tag);
          if (tag === 'a') {
            el.click = () => {
              downloadFilename = el.download;
            };
          }
          return el;
        };

        const { DiagnosticsSection } = await import('/js/components/StatusHealthTab.mjs');
        const { render } = await import('preact');
        const { html } = await import('htm/preact');

        const mockResponse = {
          entities: [{
            entity_id: 'arm1', entity_name: 'Arm 1', overall: 'pass',
            checks: {
              agent_http: { status: 'pass', latency_ms: 10, message: 'ok', fix_hint: null },
              ros2: { status: 'pass', latency_ms: null, message: 'ok', fix_hint: null },
              systemd: { status: 'pass', latency_ms: 10, message: 'ok', fix_hint: null },
              mqtt: { status: 'pass', latency_ms: null, message: 'ok', fix_hint: null },
            },
          }],
        };

        const origFetch = globalThis.fetch;
        globalThis.fetch = async (url) => {
          if (url === '/api/diagnostics/run') {
            return { ok: true, status: 200, json: async () => mockResponse, text: async () => JSON.stringify(mockResponse) };
          }
          return origFetch(url);
        };

        const container = document.createElement('div');
        document.body.appendChild(container);
        render(html`<${DiagnosticsSection} />`, container);
        await new Promise((r) => setTimeout(r, 100));

        // Expand and run
        container.querySelector('h3').closest('div[style]').click();
        await new Promise((r) => setTimeout(r, 150));
        const runBtn = Array.from(container.querySelectorAll('button')).find(b => b.textContent.includes('Run Diagnostics'));
        runBtn.click();
        await new Promise((r) => setTimeout(r, 400));

        globalThis.fetch = origFetch;

        // Click Export JSON
        const exportBtn = Array.from(container.querySelectorAll('button')).find(b => b.textContent.includes('Export JSON'));
        if (exportBtn) exportBtn.click();
        await new Promise((r) => setTimeout(r, 100));

        URL.createObjectURL = origCreateObjectURL;
        document.createElement = origCreateElement;

        const filenameHasTimestamp = downloadFilename.startsWith('diagnostics-') && downloadFilename.endsWith('.json');
        return { downloadAttempted, filenameHasTimestamp, filename: downloadFilename };
      } catch (e) {
        return { error: e.message };
      }
    });
    assert(!exportResult.error, `Export test runs — ${exportResult.error || 'ok'}`);
    assert(exportResult.downloadAttempted, 'Export JSON triggers blob URL creation (download initiated)');
    assert(exportResult.filenameHasTimestamp, `Download filename has timestamp format: diagnostics-<ts>.json (got: ${exportResult.filename})`);

    // ================================================================
    // JS error check
    // ================================================================
    console.log('\n[7] No uncaught JS errors during tests');
    assert(jsErrors.length === 0, `No uncaught JS errors — found: ${jsErrors.join('; ')}`);

  } finally {
    await browser.close();
  }

  // ================================================================
  // Summary
  // ================================================================
  console.log('\n====================================');
  console.log(`Results: ${passed} passed, ${failed} failed`);
  if (failures.length > 0) {
    console.log('\nFailed tests:');
    failures.forEach((f) => console.log(`  - ${f}`));
  }

  process.exit(failed > 0 ? 1 : 0);
})();
