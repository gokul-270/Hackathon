#!/usr/bin/env node
// Grouped Sidebar E2E Test Suite (Tasks 7.1–7.6)
// Validates grouped sidebar structure, expand/collapse persistence,
// fleet-overview default landing, sub-tab switchers, and removed standalone tabs.
// Run: node web_dashboard/e2e_tests/grouped_sidebar_e2e.mjs
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

// Helper: check element is visible (display != none)
async function isVisible(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    return getComputedStyle(el).display !== 'none';
  }, selector);
}

// Helper: get trimmed text content
async function getText(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    return el ? el.textContent.trim() : null;
  }, selector);
}

// Helper: click a nav-link by hash navigation
async function navigateToSection(page, sectionName) {
  await page.evaluate((name) => {
    window.location.hash = '#' + name;
  }, sectionName);
  await page.waitForTimeout(500);
}

// Helper: get the currently active content section id
async function getActiveSection(page) {
  return page.evaluate(() => {
    const sections = document.querySelectorAll('.content-section');
    for (const s of sections) {
      if (s.classList.contains('active') || getComputedStyle(s).display !== 'none') return s.id;
    }
    return null;
  });
}

(async () => {
  console.log('Grouped Sidebar E2E Tests (Tasks 7.1–7.6)');
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
    console.log('\n  CRASH  Global timeout (30s) exceeded');
    failed++;
    failures.push('CRASH: Global timeout (30s) exceeded');
    await browser.close();
    printSummary();
    process.exit(1);
  }, 30000);

  try {
    // Load dashboard
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // ================================================================
    // 7.1: Sidebar displays grouped navigation with correct structure
    // ================================================================
    console.log('\n[7.1] Sidebar grouped navigation structure');

    // Verify Fleet Overview link exists
    const hasFleetOverview = await exists(page, '.sidebar-overview');
    assert(hasFleetOverview, 'Sidebar has Fleet Overview link (.sidebar-overview)');

    // Verify 4 global nav items exist (flat <a> elements with .sidebar-nav-item)
    const navItemLabels = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('.sidebar-nav-item'))
        .map(el => el.textContent.trim());
    });
    assert(navItemLabels.length === 4,
      `Sidebar has 4 global nav items (got ${navItemLabels.length}: ${navItemLabels.join(', ')})`);

    // Verify nav item names: Operations, Monitoring, Motor Config, Settings
    const expectedNavItems = ['Operations', 'Monitoring', 'Motor Config', 'Settings'];
    for (const name of expectedNavItems) {
      const found = navItemLabels.some(h => h.includes(name));
      assert(found, `Nav item "${name}" exists`);
    }

    // Verify each nav item has .nav-icon and .nav-label-text spans
    const navItemStructure = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('.sidebar-nav-item')).map(item => ({
        label: item.textContent.trim(),
        hasIcon: !!item.querySelector('.nav-icon'),
        hasLabelText: !!item.querySelector('.nav-label-text'),
      }));
    });
    for (const item of navItemStructure) {
      assert(item.hasIcon, `Nav item "${item.label}" has .nav-icon span`);
      assert(item.hasLabelText, `Nav item "${item.label}" has .nav-label-text span`);
    }

    // Verify total global navigation items = 4 (flat nav items, no sub-items)
    assert(navItemLabels.length === 4,
      `Total global nav items = 4 (got ${navItemLabels.length})`);

    // ================================================================
    // 7.2: Global nav items are flat <a> elements (no groups, no collapse)
    // ================================================================
    console.log('\n[7.2] Global nav items are flat (no group wrappers)');

    // Verify global nav items are direct <a> elements, not wrapped in .sidebar-group
    const navItemInfo = await page.evaluate(() => {
      const items = document.querySelectorAll('.sidebar-nav-item');
      return Array.from(items).map(item => ({
        label: item.textContent.trim(),
        tagName: item.tagName.toLowerCase(),
        insideSidebarGroup: !!item.closest('.sidebar-group'),
        hasChevron: !!item.querySelector('.chevron, .expand-icon, svg'),
      }));
    });

    for (const item of navItemInfo) {
      assert(item.tagName === 'a',
        `"${item.label}" nav item is an <a> element`);
      assert(!item.insideSidebarGroup,
        `"${item.label}" nav item is NOT inside a .sidebar-group`);
      assert(!item.hasChevron,
        `"${item.label}" nav item has no chevron`);
    }

    // Verify no .sidebar-group-flat class exists (concept removed)
    const flatGroupCount = await page.evaluate(() => {
      return document.querySelectorAll('.sidebar-group-flat').length;
    });
    assert(flatGroupCount === 0,
      `No .sidebar-group-flat elements exist (got ${flatGroupCount})`);

    // Verify sidebar collapse toggle bar exists
    const hasCollapseBtn = await page.evaluate(() => {
      return !!document.querySelector('.sidebar-toggle-bar');
    });
    assert(hasCollapseBtn,
      'Sidebar has a .sidebar-toggle-bar');

    // Reload and verify nav items still present
    await page.reload({ waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    const navItemsAfterReload = await page.evaluate(() => {
      return document.querySelectorAll('.sidebar-nav-item').length;
    });
    assert(navItemsAfterReload === 4,
      `4 global nav items still present after reload (got ${navItemsAfterReload})`);

    // ================================================================
    // 7.3: Fleet Overview is default landing page
    // ================================================================
    console.log('\n[7.3] Fleet Overview is default landing page');

    // Navigate to base URL with no hash
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    // Verify fleet-overview section is visible
    const fleetOverviewVisible = await isVisible(page, '#fleet-overview-section');
    assert(fleetOverviewVisible,
      'Fleet overview section is visible on default landing');

    // Verify URL hash is "fleet-overview"
    const landingHash = await page.evaluate(() => window.location.hash);
    assert(landingHash === '#fleet-overview',
      `Landing URL hash is #fleet-overview (got "${landingHash}")`);

    // Verify the active content section is fleet-overview-section
    const activeSection = await getActiveSection(page);
    assert(activeSection === 'fleet-overview-section',
      `Active content section is fleet-overview-section (got "${activeSection}")`);

    // ================================================================
    // 7.4: Statistics sub-tab switcher (Current Session / History)
    // ================================================================
    console.log('\n[7.4] Statistics sub-tab switcher');

    // Navigate to #statistics
    await page.goto(`${BASE}/#statistics`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });

    // Wait for the Preact StatisticsTab to finish loading and render the sub-tab bar.
    // The component starts with a loading spinner until all API calls resolve/fail.
    await page.waitForSelector('#statistics-section .sub-tab-bar', { timeout: 10000 })
      .catch(() => {});

    // Verify statistics section is active
    const statsActive = await getActiveSection(page);
    assert(statsActive === 'statistics-section',
      `Statistics section is active (got "${statsActive}")`);

    // Verify sub-tab bar exists
    const statsSubTabBar = await page.evaluate(() => {
      const section = document.getElementById('statistics-section');
      if (!section) return false;
      return !!section.querySelector('.sub-tab-bar');
    });
    assert(statsSubTabBar,
      'Statistics section has a sub-tab bar');

    // Verify sub-tab buttons: "Current Session" and "History"
    const statsSubTabLabels = await page.evaluate(() => {
      const section = document.getElementById('statistics-section');
      if (!section) return [];
      return Array.from(section.querySelectorAll('.sub-tab-btn'))
        .map(btn => btn.textContent.trim());
    });
    assert(
      statsSubTabLabels.includes('Current Session'),
      `Statistics has "Current Session" sub-tab (got [${statsSubTabLabels}])`
    );
    assert(
      statsSubTabLabels.includes('History'),
      `Statistics has "History" sub-tab (got [${statsSubTabLabels}])`
    );

    // Verify "Current Session" is active by default when navigated via #statistics
    const statsDefaultSubTab = await page.evaluate(() => {
      const section = document.getElementById('statistics-section');
      if (!section) return null;
      const active = section.querySelector('.sub-tab-btn.active');
      return active ? active.textContent.trim() : null;
    });
    assert(statsDefaultSubTab === 'Current Session',
      `Default active sub-tab is "Current Session" (got "${statsDefaultSubTab}")`);

    // Click "History" sub-tab
    await page.evaluate(() => {
      const section = document.getElementById('statistics-section');
      if (!section) return;
      const btns = section.querySelectorAll('.sub-tab-btn');
      for (const btn of btns) {
        if (btn.textContent.trim() === 'History') {
          btn.click();
          break;
        }
      }
    });
    await page.waitForTimeout(500);

    // Verify "History" sub-tab is now active
    const statsHistoryActive = await page.evaluate(() => {
      const section = document.getElementById('statistics-section');
      if (!section) return null;
      const active = section.querySelector('.sub-tab-btn.active');
      return active ? active.textContent.trim() : null;
    });
    assert(statsHistoryActive === 'History',
      `After click, "History" sub-tab is active (got "${statsHistoryActive}")`);

    // Navigate to #history directly
    await page.goto(`${BASE}/#history`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // Verify Statistics section loads (history maps to statistics tab)
    const historyRouteSection = await getActiveSection(page);
    assert(historyRouteSection === 'statistics-section'
      || historyRouteSection === 'history-section',
      `#history route loads Statistics section (got "${historyRouteSection}")`);

    // Verify History sub-tab is active when navigated via #history
    const historyDirectSubTab = await page.evaluate(() => {
      // Check in whichever section is visible
      const visible = document.querySelector(
        '.content-section.active .sub-tab-btn.active, ' +
        '.content-section:not([style*="display: none"]) .sub-tab-btn.active'
      );
      return visible ? visible.textContent.trim() : null;
    });
    assert(historyDirectSubTab === 'History',
      `#history route activates History sub-tab (got "${historyDirectSubTab}")`);

    // ================================================================
    // 7.5: Launch Control accessible via hash (no longer a sidebar item)
    // ================================================================
    console.log('\n[7.5] Launch Control accessible via hash navigation');

    // Navigate to #launch-control via hash (not sidebar — it's now an icon tile in Operations tab)
    await page.goto(`${BASE}/#launch-control`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    // Verify launch-control section is active
    const lcActive = await getActiveSection(page);
    assert(lcActive === 'launch-control-section',
      `#launch-control hash activates launch-control-section (got "${lcActive}")`);

    // Verify sub-tab bar exists in launch control section
    const lcSubTabBar = await page.evaluate(() => {
      const section = document.getElementById('launch-control-section');
      if (!section) return false;
      return !!section.querySelector('.sub-tab-bar');
    });
    assert(lcSubTabBar,
      'Launch Control section has a sub-tab bar');

    // Verify sub-tab buttons: "Launch" and "Services"
    const lcSubTabLabels = await page.evaluate(() => {
      const section = document.getElementById('launch-control-section');
      if (!section) return [];
      return Array.from(section.querySelectorAll('.sub-tab-btn'))
        .map(btn => btn.textContent.trim());
    });
    assert(
      lcSubTabLabels.includes('Launch'),
      `Launch Control has "Launch" sub-tab (got [${lcSubTabLabels}])`
    );
    assert(
      lcSubTabLabels.includes('Services'),
      `Launch Control has "Services" sub-tab (got [${lcSubTabLabels}])`
    );

    // Verify "Launch" is active by default
    const lcDefaultSubTab = await page.evaluate(() => {
      const section = document.getElementById('launch-control-section');
      if (!section) return null;
      const active = section.querySelector('.sub-tab-btn.active');
      return active ? active.textContent.trim() : null;
    });
    assert(lcDefaultSubTab === 'Launch',
      `Default active sub-tab is "Launch" (got "${lcDefaultSubTab}")`);

    // Verify launch-control is NOT in the sidebar nav items
    const lcInSidebar = await page.evaluate(() => {
      const navItems = document.querySelectorAll('.sidebar-nav-item');
      for (const item of navItems) {
        if (item.textContent.trim() === 'Launch Control') return true;
      }
      return false;
    });
    assert(!lcInSidebar,
      'Launch Control is NOT a sidebar nav item (moved to Operations icon tile)');

    // ================================================================
    // 7.6: No standalone Safety, History, or System Services tabs
    // ================================================================
    console.log('\n[7.6] No standalone Safety, History, or System Services tabs');

    // Get all sidebar global nav item labels
    const allNavLabels = await page.evaluate(() => {
      const navItems = document.querySelectorAll('.sidebar-nav-item');
      return Array.from(navItems).map(item => item.textContent.trim());
    });

    // Verify no standalone "Safety" nav item (removed — Safety tab deleted)
    const hasStandaloneSafety = allNavLabels.some(
      label => label === 'Safety'
    );
    assert(!hasStandaloneSafety,
      'No standalone "Safety" item in sidebar global nav items');

    // Verify no standalone "History" nav item
    const hasStandaloneHistory = allNavLabels.some(
      label => label === 'History'
    );
    assert(!hasStandaloneHistory,
      'No standalone "History" item in sidebar nav items');

    // Verify no "System Services" or "Systemd Services" nav item
    const hasSystemServices = allNavLabels.some(
      label => label === 'System Services' || label === 'Systemd Services'
    );
    assert(!hasSystemServices,
      'No "System Services" or "Systemd Services" item in sidebar nav items');

    // Verify no "Launch Control" or "Sync/Deploy" sidebar nav items (moved to Operations icon tiles)
    const hasLaunchControl = allNavLabels.some(
      label => label === 'Launch Control'
    );
    assert(!hasLaunchControl,
      'No "Launch Control" item in sidebar nav items (moved to Operations icon tile)');

    const hasSyncDeploy = allNavLabels.some(
      label => label === 'Sync/Deploy'
    );
    assert(!hasSyncDeploy,
      'No "Sync/Deploy" item in sidebar nav items (moved to Operations icon tile)');

    // Verify #history route loads the Statistics tab (not a standalone tab)
    await page.goto(`${BASE}/#history`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    const historyRouteActive = await getActiveSection(page);
    assert(
      historyRouteActive === 'statistics-section'
        || historyRouteActive === 'history-section',
      `#history route loads Statistics tab (got "${historyRouteActive}")`
    );

    // Verify #systemd-services redirects to launch-control
    await page.goto(`${BASE}/#systemd-services`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    const sysServicesRouteActive = await getActiveSection(page);
    const currentHash = await page.evaluate(() => window.location.hash);
    assert(
      sysServicesRouteActive === 'launch-control-section'
        || currentHash === '#launch-control',
      `#systemd-services redirects to launch-control (section: "${sysServicesRouteActive}", hash: "${currentHash}")`
    );

    // Verify #overview redirects to fleet-overview (System Overview removed)
    await page.goto(`${BASE}/#overview`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    const overviewRedirectHash = await page.evaluate(() => window.location.hash);
    assert(
      overviewRedirectHash === '#fleet-overview',
      `#overview redirects to #fleet-overview (got "${overviewRedirectHash}")`
    );

    // Verify #safety redirects to fleet-overview (Safety tab removed)
    await page.goto(`${BASE}/#safety`, {
      waitUntil: 'networkidle',
      timeout: 15000,
    });
    await page.waitForTimeout(1000);

    const safetyRedirectHash = await page.evaluate(() => window.location.hash);
    assert(
      safetyRedirectHash === '#fleet-overview',
      `#safety redirects to #fleet-overview (got "${safetyRedirectHash}")`
    );

    // ================================================================
    // Error Checks
    // ================================================================
    console.log('\n[8] Error Checks');

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
    failures.forEach(f => console.log(`  - ${f}`));
  }
  console.log();
}
