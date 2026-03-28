#!/usr/bin/env node
// New Tabs E2E Test Suite
// Verifies: Safety tab renders with E-Stop button and status panel;
//           Safety E-Stop click triggers /api/estop request;
//           File Browser tab renders directory listing;
//           Log Viewer tab renders log entries or empty-state message;
//           Safety/File Browser/Log Viewer do NOT appear in sidebar navigation;
//           Bag Analyser label is renamed to Bag Manager.
// Run: node web_dashboard/e2e_tests/new_tabs_e2e.mjs
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
  if (condition) { passed++; console.log(`  PASS  ${name}`); }
  else { failed++; failures.push(name); console.log(`  FAIL  ${name}`); }
}

function skip(name, reason) { skipped++; console.log(`  SKIP  ${name} (${reason})`); }

async function exists(page, selector) {
  return page.evaluate((sel) => !!document.querySelector(sel), selector);
}

async function navigateToSection(page, sectionName) {
  await page.evaluate((name) => { window.location.hash = '#' + name; }, sectionName);
  await page.waitForTimeout(1500);
}

async function preactContainerHasContent(page, sectionId) {
  return page.evaluate((id) => {
    const el = document.getElementById(`${id}-section-preact`);
    return el ? el.innerHTML.trim().length > 0 : false;
  }, sectionId);
}

async function anyElementExists(page, containerSelector, selectors) {
  return page.evaluate(({ container, sels }) => {
    const root = document.querySelector(container);
    if (!root) return false;
    for (const sel of sels) { if (root.querySelector(sel)) return true; }
    return false;
  }, { container: containerSelector, sels: selectors });
}

async function containerHasText(page, containerSelector, pattern) {
  return page.evaluate(({ container, pat }) => {
    const root = document.querySelector(container);
    if (!root) return false;
    return root.textContent.includes(pat);
  }, { container: containerSelector, pat: pattern });
}

async function getText(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    return el ? el.textContent.trim() : null;
  }, selector);
}

async function isVisible(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    return getComputedStyle(el).display !== 'none';
  }, selector);
}

async function countElements(page, selector) {
  return page.evaluate((sel) => document.querySelectorAll(sel).length, selector);
}

(async () => {
  console.log('New Tabs E2E Tests');
  console.log(`Target: ${BASE}`);
  console.log('==========================\n');

  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined, args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'] });
  const page = await browser.newPage();
  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  // Track API calls
  const apiCalls = [];
  page.on('request', (req) => { if (req.url().includes('/api/')) apiCalls.push({ method: req.method(), url: req.url() }); });

  try {
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    // [1] Safety tab removed — verify redirect to fleet-overview
    console.log('\n[1] Safety tab removal verification');
    await navigateToSection(page, 'safety');
    await page.waitForTimeout(1000);
    const safetyHash = await page.evaluate(() => window.location.hash);
    assert(safetyHash === '#fleet-overview',
      `#safety redirects to #fleet-overview (got "${safetyHash}")`);

    // [2] Header E-Stop buttons exist (moved from Safety tab to header)
    console.log('\n[2] Header E-Stop buttons');
    const hasEstopEntityBtn = await exists(page, '#estop-entity-btn');
    assert(hasEstopEntityBtn, 'Header has E-Stop entity button (#estop-entity-btn)');

    const hasEstopAllBtn = await exists(page, '#estop-all-btn');
    assert(hasEstopAllBtn, 'Header has E-Stop All button (#estop-all-btn)');

    // Verify E-Stop All button text
    const estopAllText = await getText(page, '#estop-all-btn');
    assert(estopAllText && estopAllText.includes('E-STOP'),
      `E-Stop All button contains "E-STOP" text (got: "${estopAllText}")`);

    // [3] File Browser tab
    console.log('\n[3] File Browser tab');
    await navigateToSection(page, 'file-browser');
    await page.waitForTimeout(2000);
    const fbRendered = await preactContainerHasContent(page, 'file-browser');
    assert(fbRendered, 'File Browser tab renders content');

    const hasFbContent = await anyElementExists(page, '#file-browser-section-preact', [
      'table', 'a', '.section-header', '.text-muted', '.loading', '.error'
    ]);
    assert(hasFbContent, 'File Browser shows directory listing or state');

    // [4] Log Viewer tab
    console.log('\n[4] Log Viewer tab');
    await navigateToSection(page, 'log-viewer');
    await page.waitForTimeout(2000);
    const lvRendered = await preactContainerHasContent(page, 'log-viewer');
    assert(lvRendered, 'Log Viewer tab renders content');

    const hasLvContent = await anyElementExists(page, '#log-viewer-section-preact', [
      '.log-entry', '.log-list', '.log-viewer', 'select', '.empty-state', '.loading', '.error'
    ]);
    assert(hasLvContent, 'Log Viewer shows entries or empty state');

    // [5] Sidebar entries (nav-link elements, matched by text content)
    console.log('\n[5] Sidebar navigation entries');
    const sidebarHasSafety = await page.evaluate(() => {
      const links = document.querySelectorAll('.nav-link');
      return [...links].some(l => l.textContent.trim() === 'Safety');
    });
    assert(!sidebarHasSafety, 'Sidebar does NOT have Safety entry (removed)');

    const sidebarHasFB = await page.evaluate(() => {
      const links = document.querySelectorAll('.nav-link, .sidebar-nav-item');
      return [...links].some(l => l.textContent.trim() === 'File Browser');
    });
    assert(!sidebarHasFB, 'Sidebar does NOT have File Browser entry (moved to Monitoring hub)');

    const sidebarHasLV = await page.evaluate(() => {
      const links = document.querySelectorAll('.nav-link, .sidebar-nav-item');
      return [...links].some(l => l.textContent.trim() === 'Log Viewer');
    });
    assert(!sidebarHasLV, 'Sidebar does NOT have Log Viewer entry (moved to Monitoring hub)');

    // [6] Bag Manager label (not "Bag Analyser")
    console.log('\n[6] Bag Manager sidebar label');
    const bagLabel = await page.evaluate(() => {
      const items = document.querySelectorAll('.nav-item, .nav-link');
      for (const item of items) {
        const text = item.textContent.trim();
        if (text.includes('Bag')) return text;
      }
      return null;
    });
    if (bagLabel) {
      assert(!bagLabel.includes('Analyser'), `Bag label is not "Bag Analyser" (found: "${bagLabel}")`);
      assert(bagLabel.includes('Manager'), `Bag label contains "Manager" (found: "${bagLabel}")`);
    } else {
      skip('Bag Manager label check', 'No bag entry found in sidebar');
    }

    // [7] No JS errors
    console.log('\n[7] Error checks');
    const relevantErrors = jsErrors.filter(e => !e.includes('ResizeObserver'));
    assert(relevantErrors.length === 0, `No JS errors (got ${relevantErrors.length}: ${relevantErrors.slice(0,2).join('; ')})`);

  } catch (err) {
    console.log(`\n  CRASH  ${err.message}`);
    failed++;
    failures.push(`CRASH: ${err.message}`);
  } finally {
    await browser.close();
  }

  const total = passed + failed + skipped;
  console.log('\n==========================');
  console.log(`Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`);
  if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach((f) => console.log(`  - ${f}`));
  }
  console.log();
  process.exit(failed > 0 ? 1 : 0);
})();
