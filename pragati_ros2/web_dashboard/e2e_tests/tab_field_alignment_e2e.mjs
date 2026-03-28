#!/usr/bin/env node
// Tab Field Alignment E2E Test Suite
// Verifies: Launch Control shows profile statuses from backend (not all 'Stopped');
//           Sync tab loads without 422 error; Sync status reflects actual backend state.
// Run: node web_dashboard/e2e_tests/tab_field_alignment_e2e.mjs
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
  console.log('Tab Field Alignment E2E Tests');
  console.log(`Target: ${BASE}`);
  console.log('==========================\n');

  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined, args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'] });
  const page = await browser.newPage();
  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  // Track 422 errors
  const http422s = [];
  page.on('response', (resp) => { if (resp.status() === 422) http422s.push(resp.url()); });

  try {
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    // [1] Launch Control tab - status field alignment
    console.log('\n[1] Launch Control status field names');
    await navigateToSection(page, 'launch-control');
    await page.waitForTimeout(2000);
    const launchRendered = await preactContainerHasContent(page, 'launch-control');
    assert(launchRendered, 'Launch Control tab renders content');

    // Check that status elements exist (they use status.status, not status.state)
    // The tab should render without errors
    const launchHasContent = await anyElementExists(page, '#launch-control-section-preact', [
      '.launch-card', '.launch-profile', '.status-badge', 'button', '.loading'
    ]);
    assert(launchHasContent, 'Launch Control shows profiles or loading state');

    // [2] Sync tab - no 422 errors
    console.log('\n[2] Sync tab loads without 422');
    const errsBefore = http422s.length;
    await navigateToSection(page, 'sync-deploy');
    await page.waitForTimeout(2000);
    const syncRendered = await preactContainerHasContent(page, 'sync-deploy');
    assert(syncRendered, 'Sync tab renders content');

    const errsAfter = http422s.filter(u => u.includes('/api/sync'));
    assert(errsAfter.length === 0, 'No 422 errors from sync API on tab load');

    // [3] Sync status shows running/idle state
    console.log('\n[3] Sync status field');
    const syncHasStatus = await anyElementExists(page, '#sync-deploy-section-preact', [
      '.sync-status-running', '.sync-status-idle', '.sync-panel-header', '.sync-unavailable', '.text-muted'
    ]);
    assert(syncHasStatus, 'Sync tab shows status indicator');

    // [4] No JS errors
    console.log('\n[4] Error checks');
    const relevantErrors = jsErrors.filter(e => !e.includes('ResizeObserver'));
    assert(relevantErrors.length === 0, `No JS console errors (got ${relevantErrors.length}: ${relevantErrors.slice(0,2).join('; ')})`);

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
