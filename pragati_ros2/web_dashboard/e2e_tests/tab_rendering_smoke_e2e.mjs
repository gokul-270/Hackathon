#!/usr/bin/env node
// Per-Tab Rendering Smoke E2E Test Suite
// Navigates to every migrated Preact tab and verifies that each renders
// at least one key element into its Preact container.
// Run: node web_dashboard/e2e_tests/tab_rendering_smoke_e2e.mjs
//
// Requires: npm install playwright (in this directory)
// Dashboard must be running on http://127.0.0.1:8090

import { chromium } from 'playwright';

const BASE = 'http://127.0.0.1:8090';
let passed = 0;
let failed = 0;
let skipped = 0;
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

function skip(name, reason) {
  skipped++;
  console.log(`  SKIP  ${name} (${reason})`);
}

// Helper: check element exists
async function exists(page, selector) {
  return page.evaluate((sel) => !!document.querySelector(sel), selector);
}

// Helper: navigate to tab via hash change (sidebar uses hash navigation)
async function navigateToSection(page, sectionName) {
  await page.evaluate((name) => {
    window.location.hash = "#" + name;
  }, sectionName);
  // Wait for hash change, portal mount, and Preact render
  await page.waitForTimeout(1500);
}

// Helper: check if a Preact container has rendered content
async function preactContainerHasContent(page, sectionId) {
  return page.evaluate((id) => {
    const el = document.getElementById(`${id}-section-preact`);
    return el ? el.innerHTML.trim().length > 0 : false;
  }, sectionId);
}

// Helper: check if any of several selectors exist within a container
async function anyElementExists(page, containerSelector, selectors) {
  return page.evaluate(({ container, sels }) => {
    const root = document.querySelector(container);
    if (!root) return false;
    for (const sel of sels) {
      if (root.querySelector(sel)) return true;
    }
    return false;
  }, { container: containerSelector, sels: selectors });
}

// Helper: check for text content matching a pattern within a container
async function containerHasText(page, containerSelector, pattern) {
  return page.evaluate(({ container, pat }) => {
    const root = document.querySelector(container);
    if (!root) return false;
    return root.textContent.includes(pat);
  }, { container: containerSelector, pat: pattern });
}

/**
 * Tab smoke test definitions.
 * Each entry: { section, label, container, checks }
 * checks = array of { type, args, name }
 *   type: 'element' (any of selectors exists), 'text' (text pattern in container),
 *         'content' (container has any rendered content)
 */
const TAB_SMOKE_TESTS = [
  {
    section: 'fleet-overview',
    label: 'Fleet Overview',
    container: '#fleet-overview-section-preact',
    checks: [
      { type: 'element', args: ['.stat-card', '.stats-grid', '.loading'], name: 'stat cards or loading indicator' },
      { type: 'content', args: [], name: 'container has rendered content' },
    ],
  },
  {
    section: 'alerts',
    label: 'Alerts',
    container: '#alerts-section-preact',
    checks: [
      { type: 'element', args: ['.alerts-list', '.alert-item', '.empty-state', '.loading', '.text-muted'], name: 'alerts list or empty state' },
      { type: 'text', args: ['Alert'], name: 'contains "Alert" text' },
    ],
  },
  {
    section: 'statistics',
    label: 'Statistics',
    container: '#statistics-section-preact',
    checks: [
      { type: 'element', args: ['.stat-cards-row', '.stats-panel', '.chart-card', '.loading', '.empty-state'], name: 'stat cards or chart' },
      { type: 'content', args: [], name: 'container has rendered content' },
    ],
  },
  {
    section: 'analysis',
    label: 'Field Analysis',
    container: '#analysis-section-preact',
    checks: [
      { type: 'element', args: ['.fa-log-dir-card', '.card', '.stats-panel', '.loading', '.empty-state'], name: 'directory browser or analysis controls' },
      { type: 'content', args: [], name: 'container has rendered content' },
    ],
  },
  {
    section: 'bags',
    label: 'Bag Manager',
    container: '#bags-section-preact',
    checks: [
      { type: 'element', args: ['.bag-recording-panel', '.stats-panel', '.loading'], name: 'bag list or recording controls' },
      { type: 'content', args: [], name: 'container has rendered content' },
    ],
  },
  {
    section: 'settings',
    label: 'Settings',
    container: '#settings-section-preact',
    checks: [
      { type: 'element', args: ['.settings-panel', '.settings-group', '.setting-item'], name: 'settings form inputs' },
      { type: 'element', args: ['select', 'input', '.select-input', '.number-input'], name: 'form input elements' },
    ],
  },
  {
    section: 'launch-control',
    label: 'Launch Control',
    container: '#launch-control-section-preact',
    checks: [
      { type: 'element', args: ['.launch-panel-header', '.section-grid', '.loading', '.launch-panel-controls'], name: 'launch panels' },
      { type: 'content', args: [], name: 'container has rendered content' },
    ],
  },
  {
    section: 'sync-deploy',
    label: 'Sync',
    container: '#sync-deploy-section-preact',
    checks: [
      { type: 'element', args: ['.sync-panel-header', '.sync-panel-controls', '.sync-panel-buttons', '.sync-unavailable', '.text-muted'], name: 'sync operation buttons' },
      { type: 'content', args: [], name: 'container has rendered content' },
    ],
  },
  {
    section: 'multi-arm',
    label: 'Multi-Arm',
    container: '#multi-arm-section-preact',
    checks: [
      { type: 'element', args: ['.arm-card', '#arm-cards-container', '.fleet-arm-cards', '.loading', '.empty-state'], name: 'arm cards or loading state' },
      { type: 'content', args: [], name: 'container has rendered content' },
    ],
  },
  {
    section: 'operations',
    label: 'Operations',
    container: '#operations-section-preact',
    checks: [
      { type: 'element', args: ['button', 'h3', 'input', 'select', 'div > div'], name: 'operation buttons or grid' },
      { type: 'content', args: [], name: 'container has rendered content' },
    ],
  },
  {
    section: 'log-viewer',
    label: 'Log Viewer',
    container: '#log-viewer-section-preact',
    checks: [
      { type: 'element', args: ['.log-entry', '.log-list', '.log-viewer', 'select', '.empty-state', '.loading', '.error'], name: 'log entries or empty state' },
      { type: 'content', args: [], name: 'container has rendered content' },
    ],
  },
  {
    section: 'file-browser',
    label: 'File Browser',
    container: '#file-browser-section-preact',
    checks: [
      { type: 'element', args: ['table', 'a', '.section-header', '.text-muted', '.loading', '.error'], name: 'directory listing or state' },
      { type: 'content', args: [], name: 'container has rendered content' },
    ],
  },
];

(async () => {
  console.log('Per-Tab Rendering Smoke E2E Tests');
  console.log(`Target: ${BASE}`);
  console.log('==========================\n');

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });

  const page = await browser.newPage();

  // Collect JS errors
  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  // Collect 404s
  const notFound = [];
  page.on('response', (resp) => {
    if (resp.status() === 404) notFound.push(resp.url());
  });

  try {
    // Load dashboard
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // ================================================================
    // PER-TAB SMOKE TESTS
    // ================================================================

    for (let i = 0; i < TAB_SMOKE_TESTS.length; i++) {
      const tab = TAB_SMOKE_TESTS[i];
      const sectionNum = i + 1;
      console.log(`\n[${sectionNum}] ${tab.label} Tab`);

      // Navigate to the tab
      await navigateToSection(page, tab.section);

      // Verify section is active
      const activeSection = await page.evaluate(() => {
        const sections = document.querySelectorAll('.content-section');
        for (const s of sections) {
          if (getComputedStyle(s).display !== 'none') return s.id;
        }
        return null;
      });
      assert(activeSection === `${tab.section}-section`,
        `${tab.label}: section is active`);

      // Verify Preact container has content
      const hasContent = await preactContainerHasContent(page, tab.section);
      assert(hasContent,
        `${tab.label}: Preact container has rendered content`);

      // Run tab-specific checks
      for (const check of tab.checks) {
        if (check.type === 'element') {
          const found = await anyElementExists(page, tab.container, check.args);
          assert(found,
            `${tab.label}: ${check.name}`);
        } else if (check.type === 'text') {
          const found = await containerHasText(page, tab.container, check.args[0]);
          assert(found,
            `${tab.label}: ${check.name}`);
        } else if (check.type === 'content') {
          // Already checked above, but verify again for completeness
          assert(hasContent,
            `${tab.label}: ${check.name}`);
        }
      }
    }

    // ================================================================
    // SECTION: History Tab (legacy redirect — should go to statistics)
    // ================================================================
    console.log(`\n[${TAB_SMOKE_TESTS.length + 1}] History Tab (legacy redirect)`);

    await navigateToSection(page, 'history');
    const historyHash = await page.evaluate(() => window.location.hash);
    const historyActive = await page.evaluate(() => {
      const sections = document.querySelectorAll('.content-section');
      for (const s of sections) {
        if (getComputedStyle(s).display !== 'none') return s.id;
      }
      return null;
    });
    // history is a legacy redirect — it may land on statistics-section or history-section
    assert(historyActive === 'statistics-section' || historyActive === 'history-section',
      `History: redirects to statistics or activates correctly (got "${historyActive}")`);

    // ================================================================
    // ERROR CHECKS
    // ================================================================
    console.log(`\n[${TAB_SMOKE_TESTS.length + 2}] Error Checks`);

    assert(jsErrors.length === 0,
      `No JS errors during smoke tests (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join('; ')})`);

    const file404s = notFound.filter(url =>
      url.endsWith('.js') || url.endsWith('.css') || url.endsWith('.html'));
    assert(file404s.length === 0,
      `No 404s for JS/CSS/HTML files (got ${file404s.length}: ${file404s.slice(0, 3).join('; ')})`);

  } catch (err) {
    console.log(`\n  CRASH  ${err.message}`);
    failed++;
    failures.push(`CRASH: ${err.message}`);
  } finally {
    await browser.close();
  }

  // Summary
  const total = passed + failed + skipped;
  console.log('\n==========================');
  console.log(`Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`);
  if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach(f => console.log(`  - ${f}`));
  }
  console.log();
  process.exit(failed > 0 ? 1 : 0);
})();
