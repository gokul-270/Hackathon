#!/usr/bin/env node
// Entity Sidebar E2E Test Suite (Task 6.5 + flat sidebar + Motor Config extraction)
// Validates entity-centric sidebar: entity list rendering as flat links,
// active entity highlighting, fleet overview link, global nav items (4),
// legacy URL fallbacks, time drift badge.
// Run: node web_dashboard/e2e_tests/entity_sidebar_e2e.mjs
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

// Helper: get trimmed text content
async function getText(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    return el ? el.textContent.trim() : null;
  }, selector);
}

(async () => {
  console.log('Entity Sidebar E2E Tests');
  console.log(`Target: ${BASE}`);
  console.log('=============================================\n');

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });

  const page = await browser.newPage();

  // Collect JS errors
  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  // Global timeout
  const timeout = setTimeout(async () => {
    console.log('\n  CRASH  Global timeout (45s) exceeded');
    failed++;
    failures.push('CRASH: Global timeout (45s) exceeded');
    await browser.close();
    printSummary();
    process.exit(1);
  }, 45000);

  try {
    // Load dashboard and wait for rendering
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // ================================================================
    // 6.5.1: Entity list renders as flat links in sidebar
    // ================================================================
    console.log('\n[6.5.1] Entity list renders as flat links in sidebar');

    const hasSidebarNav = await exists(page, '.sidebar-nav');
    assert(hasSidebarNav, 'Sidebar nav container (.sidebar-nav) exists');

    // Entities are rendered as flat .sidebar-entity-link elements (no groups)
    const entityLinks = await page.evaluate(() => {
      const links = document.querySelectorAll('.sidebar-nav .sidebar-entity-link');
      const names = [];
      for (const l of links) {
        names.push(l.textContent.trim());
      }
      return names;
    });
    assert(entityLinks.length >= 1,
      `At least 1 entity link in sidebar (got ${entityLinks.length}: ${entityLinks.join(', ')})`);

    // Check that "local" entity is present (either as name or id)
    const hasLocal = entityLinks.some(
      (h) => h.toLowerCase().includes('local')
    );
    assert(hasLocal, 'Local entity present in sidebar entity list');

    // Verify NO .sidebar-group elements exist (entities are flat, not grouped)
    const sidebarGroupCount = await page.evaluate(() => {
      return document.querySelectorAll('.sidebar-nav .sidebar-group').length;
    });
    assert(sidebarGroupCount === 0,
      `No .sidebar-group elements in sidebar (got ${sidebarGroupCount})`);

    // ================================================================
    // 6.5.2: Flat entity links (no expand/collapse)
    // ================================================================
    console.log('\n[6.5.2] Flat entity links (no expand/collapse)');

    // No expand/collapse headers — entities are clickable flat links
    const entityGroupHeaders = await page.evaluate(() => {
      return document.querySelectorAll('.sidebar-nav .sidebar-group-header').length;
    });
    assert(entityGroupHeaders === 0,
      `No .sidebar-group-header elements (got ${entityGroupHeaders})`);

    // No chevrons on entity links
    const chevronCount = await page.evaluate(() => {
      return document.querySelectorAll('.sidebar-nav .sidebar-entity-link .chevron').length;
    });
    assert(chevronCount === 0,
      `No chevrons on entity links (got ${chevronCount})`);

    // Each entity link has a status dot
    const entityLinksWithDot = await page.evaluate(() => {
      const links = document.querySelectorAll('.sidebar-nav .sidebar-entity-link');
      let count = 0;
      for (const l of links) {
        if (l.querySelector('.entity-status-dot-inline')) count++;
      }
      return count;
    });
    assert(entityLinksWithDot === entityLinks.length,
      `All entity links have status dots (${entityLinksWithDot}/${entityLinks.length})`);

    // No entity sub-tabs in sidebar (sub-tabs are in EntityDetailShell tab bar)
    const sidebarSubTabs = await page.evaluate(() => {
      return document.querySelectorAll('.sidebar-nav .sidebar-group-items .nav-link').length;
    });
    assert(sidebarSubTabs === 0,
      `No entity sub-tab links in sidebar (got ${sidebarSubTabs})`);

    // Clicking an entity link navigates to #/entity/{id}/status
    const firstEntityNavigated = await page.evaluate(() => {
      const link = document.querySelector('.sidebar-nav .sidebar-entity-link');
      if (!link) return null;
      link.click();
      return window.location.hash;
    });
    await page.waitForTimeout(500);
    const entityHash = await page.evaluate(() => window.location.hash);
    assert(
      entityHash.includes('/entity/') && entityHash.includes('/status'),
      `Clicking entity link navigates to entity/status route (got "${entityHash}")`
    );

    // ================================================================
    // 6.5.3: Active entity highlighting
    // ================================================================
    console.log('\n[6.5.3] Active entity highlighting');

    // Navigate to entity/local/status
    await page.goto(`${BASE}/#/entity/local/status`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    // Verify the "local" entity link has .active class
    const localEntityActive = await page.evaluate(() => {
      const links = document.querySelectorAll('.sidebar-nav .sidebar-entity-link');
      for (const l of links) {
        if (l.textContent.toLowerCase().includes('local')) {
          return l.classList.contains('active');
        }
      }
      return false;
    });
    assert(localEntityActive,
      'Local entity link has .active class on #/entity/local/status');

    // ================================================================
    // 6.5.5: Fleet Overview link
    // ================================================================
    console.log('\n[6.5.5] Fleet Overview link');

    // Verify Fleet Overview link exists
    const fleetOverviewExists = await page.evaluate(() => {
      const links = document.querySelectorAll('.sidebar-nav .sidebar-overview');
      for (const l of links) {
        if (l.textContent.includes('Fleet Overview')) return true;
      }
      return false;
    });
    assert(fleetOverviewExists,
      'Fleet Overview link exists in sidebar');

    // Click Fleet Overview and verify navigation
    await page.evaluate(() => {
      const links = document.querySelectorAll('.sidebar-nav .sidebar-overview');
      for (const l of links) {
        if (l.textContent.includes('Fleet Overview')) {
          l.click();
          return;
        }
      }
    });
    await page.waitForTimeout(1000);

    const fleetOverviewHash = await page.evaluate(() => window.location.hash);
    assert(fleetOverviewHash === '#fleet-overview',
      `Fleet Overview navigates to #fleet-overview (got "${fleetOverviewHash}")`);

    // ================================================================
    // 6.5.6: System Overview removed — verify redirect
    // ================================================================
    console.log('\n[6.5.6] System Overview removed');

    // Verify System Overview link does NOT exist in sidebar
    const systemOverviewExists = await page.evaluate(() => {
      const links = document.querySelectorAll('.sidebar-nav .sidebar-overview');
      for (const l of links) {
        if (l.textContent.includes('System Overview')) return true;
      }
      return false;
    });
    assert(!systemOverviewExists,
      'System Overview link does NOT exist in sidebar (removed)');

    // Verify #overview redirects to #fleet-overview
    await page.goto(`${BASE}/#overview`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    const overviewRedirectHash = await page.evaluate(() => window.location.hash);
    assert(overviewRedirectHash === '#fleet-overview',
      `#overview redirects to #fleet-overview (got "${overviewRedirectHash}")`);

    // ================================================================
    // 6.5.7: Global nav items — Operations, Monitoring, Motor Config, Settings
    // ================================================================
    console.log('\n[6.5.7] Global nav items render');

    const globalNavItemLabels = await page.evaluate(() => {
      const items = document.querySelectorAll('.sidebar-nav .sidebar-nav-item');
      return Array.from(items).map(el => el.textContent.trim());
    });

    const expectedNavItems = ['Operations', 'Monitoring', 'Motor Config', 'Settings'];
    for (const name of expectedNavItems) {
      const found = globalNavItemLabels.some((g) => g.includes(name));
      assert(found, `Global nav item "${name}" renders in sidebar`);
    }
    assert(globalNavItemLabels.length === 4,
      `Exactly 4 global nav items (got ${globalNavItemLabels.length}: ${globalNavItemLabels.join(', ')})`);

    // Verify old groups are NOT present
    const oldGroups = ['Robot', 'Data', 'ROS2'];
    for (const name of oldGroups) {
      const found = globalNavItemLabels.some((g) => g === name);
      assert(!found, `Old group "${name}" does NOT render in sidebar`);
    }

    // ================================================================
    // 6.5.8: Legacy URL fallback (#nodes -> #/entity/local/nodes)
    // ================================================================
    console.log('\n[6.5.8] Legacy URL fallback (#nodes)');

    await page.goto(`${BASE}/#nodes`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    const nodesRedirectHash = await page.evaluate(() => window.location.hash);
    assert(
      nodesRedirectHash === '#/entity/local/nodes',
      `#nodes redirects to #/entity/local/nodes (got "${nodesRedirectHash}")`
    );

    // ================================================================
    // 6.5.9: Legacy URL fallback (#topics -> #/entity/local/topics)
    // ================================================================
    console.log('\n[6.5.9] Legacy URL fallback (#topics)');

    await page.goto(`${BASE}/#topics`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    const topicsRedirectHash = await page.evaluate(() => window.location.hash);
    assert(
      topicsRedirectHash === '#/entity/local/topics',
      `#topics redirects to #/entity/local/topics (got "${topicsRedirectHash}")`
    );

    // ================================================================
    // 6.5.10: Non-entity route stays unchanged (#settings)
    // ================================================================
    console.log('\n[6.5.10] Non-entity route stays unchanged');

    await page.goto(`${BASE}/#settings`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(2000);

    const settingsHash = await page.evaluate(() => window.location.hash);
    assert(
      settingsHash === '#settings',
      `#settings stays at #settings (got "${settingsHash}")`
    );

    // ================================================================
    // 6.5.11: No entity hide/show toggle (removed)
    // ================================================================
    console.log('\n[6.5.11] No entity hide/show toggle (removed)');

    // Verify no eye-toggle buttons exist in sidebar
    const eyeToggleExists = await page.evaluate(() => {
      return document.querySelectorAll('.entity-eye-toggle').length;
    });
    assert(eyeToggleExists === 0,
      `No eye-toggle buttons in sidebar (got ${eyeToggleExists})`);

    // Verify no hidden-entities group exists
    const hiddenGroupExists = await exists(page, '.sidebar-hidden-group');
    assert(!hiddenGroupExists,
      'No hidden entities group (.sidebar-hidden-group) in sidebar');

    // ================================================================
    // 6.5.12: Time drift badge
    // ================================================================
    console.log('\n[6.5.12] Time drift badge');

    // Time drift badge appears on entity links when |server_time - entity_time| > 5s
    // In dev/test, the local entity usually has minimal drift, so we just check
    // that the drift badge element class exists in the DOM structure
    const driftBadgeClass = await page.evaluate(() => {
      const badges = document.querySelectorAll('.entity-drift-badge');
      return badges.length;
    });
    // Drift badge may or may not be visible depending on actual entity times
    if (driftBadgeClass > 0) {
      assert(true, `Time drift badges rendered (${driftBadgeClass} found)`);
    } else {
      skip('Time drift badges rendered', 'no entities with >5s drift in test environment');
    }

    // ================================================================
    // 6.5.13: Motor Config is global nav, not entity sub-tab
    // ================================================================
    console.log('\n[6.5.13] Motor Config is global nav item');

    // #motor-config should stay as a global route (not redirect to entity)
    await page.goto(`${BASE}/#motor-config`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    const motorConfigHash = await page.evaluate(() => window.location.hash);
    assert(
      motorConfigHash === '#motor-config',
      `#motor-config stays at #motor-config (got "${motorConfigHash}")`
    );

    // #/entity/local/motor-config should redirect to #motor-config
    await page.goto(`${BASE}/#/entity/local/motor-config`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    const entityMotorHash = await page.evaluate(() => window.location.hash);
    assert(
      entityMotorHash === '#motor-config',
      `#/entity/local/motor-config redirects to #motor-config (got "${entityMotorHash}")`
    );

    // ================================================================
    // Error checks
    // ================================================================
    console.log('\n[E] Error checks');

    assert(jsErrors.length === 0,
      `No JS errors during tests (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join('; ')})`);

  } catch (err) {
    console.log(`\n  CRASH  ${err.message}`);
    failed++;
    failures.push(`CRASH: ${err.message}`);
  } finally {
    clearTimeout(timeout);
    await browser.close();
  }

  printSummary();
  process.exit(failed > 0 ? 1 : 0);
})();

function printSummary() {
  const total = passed + failed + skipped;
  console.log('\n=============================================');
  console.log(`Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`);
  if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach((f) => console.log(`  - ${f}`));
  }
  console.log();
}
