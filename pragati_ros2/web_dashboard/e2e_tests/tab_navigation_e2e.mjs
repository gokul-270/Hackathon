#!/usr/bin/env node
// Tab Navigation E2E Test Suite
// Validates hash-based routing, browser back button, mount/unmount lifecycle,
// global tab navigation, and legacy URL redirects.
// Run: node web_dashboard/e2e_tests/tab_navigation_e2e.mjs
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

// Helper: check element is visible (display != none, has .active class)
async function isVisible(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    return el.classList.contains('active') || getComputedStyle(el).display !== 'none';
  }, selector);
}

// Helper: navigate via hash
async function navigateToHash(page, hash) {
  await page.evaluate((h) => {
    window.location.hash = '#' + h;
  }, hash);
  await page.waitForTimeout(500);
}

// Helper: check which section is currently active
async function getActiveSection(page) {
  return page.evaluate(() => {
    const sections = document.querySelectorAll('.content-section');
    for (const s of sections) {
      if (s.classList.contains('active') || getComputedStyle(s).display !== 'none') return s.id;
    }
    return null;
  });
}

// Helper: get innerHTML length of a Preact container
async function getPreactContainerContentLength(page, sectionId) {
  return page.evaluate((id) => {
    const el = document.getElementById(`${id}-section-preact`);
    return el ? el.innerHTML.length : 0;
  }, sectionId);
}

(async () => {
  console.log('Tab Navigation E2E Tests');
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

  try {
    // Load dashboard
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // ================================================================
    // SECTION 1: Global tab hash navigation
    // ================================================================
    console.log('\n[1] Global Tab Hash Navigation');

    // These are global tabs (not entity-scoped) — they stay as bare hashes
    const globalTabs = [
      { hash: 'settings', sectionId: 'settings-section', label: 'Settings' },
      { hash: 'alerts', sectionId: 'alerts-section', label: 'Alerts' },
      { hash: 'statistics', sectionId: 'statistics-section', label: 'Statistics' },
      { hash: 'launch-control', sectionId: 'launch-control-section', label: 'Launch Control' },
      { hash: 'sync-deploy', sectionId: 'sync-deploy-section', label: 'Sync/Deploy' },
      { hash: 'analysis', sectionId: 'analysis-section', label: 'Field Analysis' },
      { hash: 'bags', sectionId: 'bags-section', label: 'Bag Manager' },
      { hash: 'fleet-overview', sectionId: 'fleet-overview-section', label: 'Fleet Overview' },
    ];

    for (const tab of globalTabs) {
      await navigateToHash(page, tab.hash);
      const active = await getActiveSection(page);
      assert(active === tab.sectionId,
        `Navigate to #${tab.hash}: ${tab.sectionId} becomes active (got "${active}")`);
    }

    // ================================================================
    // SECTION 2: Legacy entity-scoped hashes redirect
    // ================================================================
    console.log('\n[2] Legacy Entity-Scoped Hash Redirects');

    // These bare hashes should redirect to #/entity/local/{tab}
    const legacyEntityTabs = [
      { hash: 'nodes', redirect: '#/entity/local/nodes', label: 'Nodes' },
      { hash: 'topics', redirect: '#/entity/local/topics', label: 'Topics' },
      { hash: 'services', redirect: '#/entity/local/services', label: 'Services' },
      { hash: 'parameters', redirect: '#/entity/local/parameters', label: 'Parameters' },
      { hash: 'health', redirect: '#/entity/local/status', label: 'Health' },
      { hash: 'motor-config', redirect: '#/entity/local/motor-config', label: 'Motor Config' },
    ];

    for (const tab of legacyEntityTabs) {
      await page.goto(`${BASE}/#${tab.hash}`, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(1000);
      const resultHash = await page.evaluate(() => window.location.hash);
      assert(resultHash === tab.redirect,
        `#${tab.hash} redirects to ${tab.redirect} (got "${resultHash}")`);
    }

    // Legacy #overview and #safety redirect to #fleet-overview
    await page.goto(`${BASE}/#overview`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);
    const overviewRedirect = await page.evaluate(() => window.location.hash);
    assert(overviewRedirect === '#fleet-overview',
      `#overview redirects to #fleet-overview (got "${overviewRedirect}")`);

    await page.goto(`${BASE}/#safety`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);
    const safetyRedirect = await page.evaluate(() => window.location.hash);
    assert(safetyRedirect === '#fleet-overview',
      `#safety redirects to #fleet-overview (got "${safetyRedirect}")`);

    // ================================================================
    // SECTION 3: Browser back button navigation
    // ================================================================
    console.log('\n[3] Browser Back Button');

    // Navigate to a clean starting point
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(500);

    // Navigate: fleet-overview -> settings -> alerts -> statistics
    await navigateToHash(page, 'settings');
    await navigateToHash(page, 'alerts');
    await navigateToHash(page, 'statistics');

    const beforeBack = await getActiveSection(page);
    assert(beforeBack === 'statistics-section',
      'Before back: statistics-section is active');

    // Go back — should return to alerts
    await page.goBack();
    await page.waitForTimeout(500);

    const afterBack1 = await getActiveSection(page);
    assert(afterBack1 === 'alerts-section',
      'After first back: alerts-section is active');

    // Go back again — should return to settings
    await page.goBack();
    await page.waitForTimeout(500);

    const afterBack2 = await getActiveSection(page);
    assert(afterBack2 === 'settings-section',
      'After second back: settings-section is active');

    // ================================================================
    // SECTION 4: Mount/unmount — Preact container lifecycle
    // ================================================================
    console.log('\n[4] Mount/Unmount Lifecycle');

    // Navigate to settings — Preact container should have content
    await navigateToHash(page, 'settings');
    await page.waitForTimeout(300);

    const settingsContent = await getPreactContainerContentLength(page, 'settings');
    assert(settingsContent > 0,
      'Settings Preact container has content when active');

    // Navigate away — settings Preact container should be emptied (unmounted)
    await navigateToHash(page, 'alerts');
    await page.waitForTimeout(300);

    const settingsAfterLeave = await getPreactContainerContentLength(page, 'settings');
    assert(settingsAfterLeave === 0,
      'Settings Preact container is empty after navigating away (unmounted)');

    const alertsContent = await getPreactContainerContentLength(page, 'alerts');
    assert(alertsContent > 0,
      'Alerts Preact container has content when active');

    // Navigate to statistics — alerts should unmount, statistics should mount
    await navigateToHash(page, 'statistics');
    await page.waitForTimeout(300);

    const alertsAfterLeave = await getPreactContainerContentLength(page, 'alerts');
    assert(alertsAfterLeave === 0,
      'Alerts Preact container is empty after navigating away (unmounted)');

    const statisticsContent = await getPreactContainerContentLength(page, 'statistics');
    assert(statisticsContent > 0,
      'Statistics Preact container has content when active');

    // ================================================================
    // SECTION 5: Global tabs all have sections
    // ================================================================
    console.log('\n[5] Global Tabs Have Content Sections');

    // These are the global tabs that should have corresponding content sections
    const globalTabSections = [
      'fleet-overview', 'settings', 'alerts', 'statistics',
      'launch-control', 'sync-deploy', 'analysis', 'bags',
      'operations', 'log-viewer', 'file-browser',
    ];

    for (const tab of globalTabSections) {
      const sectionExists = await exists(page, `#${tab}-section`);
      assert(sectionExists,
        `Content section #${tab}-section exists`);
    }

    // ================================================================
    // SECTION 6: Round-trip navigation — global tabs only
    // ================================================================
    console.log('\n[6] Round-trip Navigation (global tabs)');

    const roundTripTabs = [
      'fleet-overview', 'settings', 'alerts', 'statistics',
      'launch-control', 'sync-deploy', 'analysis', 'bags',
    ];

    for (const tab of roundTripTabs) {
      await navigateToHash(page, tab);
      const active = await getActiveSection(page);
      assert(active === `${tab}-section`,
        `Round-trip: ${tab}-section activates correctly`);
    }

    // Navigate back to fleet-overview to verify stability
    await navigateToHash(page, 'fleet-overview');
    const finalActive = await getActiveSection(page);
    assert(finalActive === 'fleet-overview-section',
      'Round-trip complete: fleet-overview-section is active again');

    // ================================================================
    // SECTION 7: No JS errors
    // ================================================================
    console.log('\n[7] Error Checks');

    assert(jsErrors.length === 0,
      `No JS errors during navigation (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join('; ')})`);

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
