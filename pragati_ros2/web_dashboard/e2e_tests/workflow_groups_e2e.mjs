#!/usr/bin/env node
// Workflow Groups E2E Test (Task 8.2)
// Validates Operations, Monitoring, System groups render correct items,
// group collapse/expand persists, and navigation between groups works.
// Run: node web_dashboard/e2e_tests/workflow_groups_e2e.mjs
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

// Helper: check element is visible
async function isVisible(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    return getComputedStyle(el).display !== 'none';
  }, selector);
}

// Helper: get active content section id
async function getActiveSection(page) {
  return page.evaluate(() => {
    const sections = document.querySelectorAll('.content-section');
    for (const s of sections) {
      if (s.classList.contains('active') || getComputedStyle(s).display !== 'none') return s.id;
    }
    return null;
  });
}

// Helper: find a global nav item by name (global nav uses .sidebar-nav-item, not groups)
function findGlobalNavItemScript(navName) {
  return `
    (() => {
      const items = document.querySelectorAll('.sidebar-nav-item');
      for (const item of items) {
        if (item.textContent.includes('${navName}')) return item;
      }
      return null;
    })()
  `;
}

(async () => {
  console.log('Workflow Groups E2E Tests (Task 8.2)');
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
    // Load dashboard — clear localStorage to start fresh
    console.log('[0] Loading dashboard (clearing localStorage)...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // ================================================================
    // 8.2.1: All three global nav items render with correct labels
    // ================================================================
    console.log('\n[8.2.1] Global nav items render correctly');

    const navItemData = await page.evaluate(() => {
      const items = document.querySelectorAll('.sidebar-nav-item');
      return Array.from(items).map(item => ({
        label: item.textContent.trim(),
        hasIcon: !!item.querySelector('.nav-icon'),
        hasLabelText: !!item.querySelector('.nav-label-text'),
      }));
    });

    // Operations
    assert(
      navItemData.some(i => i.label.includes('Operations')),
      'Operations nav item renders'
    );

    // Monitoring
    assert(
      navItemData.some(i => i.label.includes('Monitoring')),
      'Monitoring nav item renders'
    );

    // Settings
    assert(
      navItemData.some(i => i.label.includes('Settings')),
      'Settings nav item renders'
    );

    // Verify exactly 3 nav items
    assert(
      navItemData.length === 3,
      `Exactly 3 global nav items (got ${navItemData.length})`
    );

    // Verify each has icon and label text spans
    for (const item of navItemData) {
      assert(item.hasIcon, `"${item.label}" has .nav-icon span`);
      assert(item.hasLabelText, `"${item.label}" has .nav-label-text span`);
    }

    // ================================================================
    // 8.2.2: Global nav items are flat <a> elements (no group wrappers)
    // ================================================================
    console.log('\n[8.2.2] Nav items are flat elements');

    const flatStates = await page.evaluate(() => {
      const items = document.querySelectorAll('.sidebar-nav-item');
      return Array.from(items).map(item => ({
        label: item.textContent.trim(),
        tagName: item.tagName.toLowerCase(),
        insideSidebarGroup: !!item.closest('.sidebar-group'),
        hasChevron: !!item.querySelector('.chevron, .expand-icon, svg'),
      }));
    });

    for (const item of flatStates) {
      assert(item.tagName === 'a', `${item.label} is an <a> element`);
      assert(!item.insideSidebarGroup, `${item.label} is NOT inside a .sidebar-group`);
      assert(!item.hasChevron, `${item.label} has no chevron`);
    }

    // Verify no .sidebar-group-flat class exists (concept removed)
    const flatGroupCount = await page.evaluate(() => {
      return document.querySelectorAll('.sidebar-group-flat').length;
    });
    assert(flatGroupCount === 0, `No .sidebar-group-flat elements exist (got ${flatGroupCount})`);

    // ================================================================
    // 8.2.3: Nav items persist across reload
    // ================================================================
    console.log('\n[8.2.3] Nav items persistence across reload');

    // Reload page
    await page.reload({ waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    // Verify all 3 global nav items still present after reload
    const afterReload = await page.evaluate(() => {
      const items = document.querySelectorAll('.sidebar-nav-item');
      return Array.from(items).map(item => item.textContent.trim());
    });

    assert(afterReload.some(l => l.includes('Operations')),
      'Operations nav item visible after reload');
    assert(afterReload.some(l => l.includes('Monitoring')),
      'Monitoring nav item visible after reload');
    assert(afterReload.some(l => l.includes('Settings')),
      'Settings nav item visible after reload');

    // ================================================================
    // 8.2.4: Navigation — clicking nav items switches sections
    // ================================================================
    console.log('\n[8.2.4] Navigation between nav items');

    // Click "Monitoring" nav item
    await page.evaluate(() => {
      const items = document.querySelectorAll('.sidebar-nav-item');
      for (const item of items) {
        if (item.textContent.trim().includes('Monitoring')) {
          item.click();
          break;
        }
      }
    });
    await page.waitForTimeout(500);

    const monitoringSection = await getActiveSection(page);
    assert(
      monitoringSection === 'monitoring-section',
      `Clicking "Monitoring" activates monitoring-section (got "${monitoringSection}")`
    );

    // Click "Settings" nav item
    await page.evaluate(() => {
      const items = document.querySelectorAll('.sidebar-nav-item');
      for (const item of items) {
        if (item.textContent.trim().includes('Settings')) {
          item.click();
          break;
        }
      }
    });
    await page.waitForTimeout(500);

    const settingsSection = await getActiveSection(page);
    assert(
      settingsSection === 'settings-section',
      `Clicking "Settings" activates settings-section (got "${settingsSection}")`
    );

    // Click "Operations" nav item
    await page.evaluate(() => {
      const items = document.querySelectorAll('.sidebar-nav-item');
      for (const item of items) {
        if (item.textContent.trim().includes('Operations')) {
          item.click();
          break;
        }
      }
    });
    await page.waitForTimeout(500);

    const opsSection = await getActiveSection(page);
    assert(
      opsSection === 'operations-section',
      `Clicking "Operations" activates operations-section (got "${opsSection}")`
    );

    // ================================================================
    // 8.2.5: Active nav item gets "active" class
    // ================================================================
    console.log('\n[8.2.5] Active nav item highlighting');

    // Navigate to monitoring
    await page.evaluate(() => { window.location.hash = '#monitoring'; });
    await page.waitForTimeout(500);

    const activeNavItem = await page.evaluate(() => {
      const active = document.querySelector('.sidebar-nav-item.active');
      return active ? active.textContent.trim() : null;
    });
    assert(
      activeNavItem !== null && activeNavItem.includes('Monitoring'),
      `Active nav item is "Monitoring" (got "${activeNavItem}")`
    );

    // Navigate to settings
    await page.evaluate(() => { window.location.hash = '#settings'; });
    await page.waitForTimeout(500);

    const settingsActiveItem = await page.evaluate(() => {
      const active = document.querySelector('.sidebar-nav-item.active');
      return active ? active.textContent.trim() : null;
    });
    assert(
      settingsActiveItem !== null && settingsActiveItem.includes('Settings'),
      `Active nav item is "Settings" (got "${settingsActiveItem}")`
    );

    // ================================================================
    // 8.2.6: Global nav items remain visible after entity navigation
    // ================================================================
    console.log('\n[8.2.6] Nav items stay visible after entity navigation');

    // Navigate to an entity route via hash
    await page.evaluate(() => { window.location.hash = '#/entity/local/status'; });
    await page.waitForTimeout(500);

    // Verify all 3 global nav items are still present
    const navItemsAfterEntityNav = await page.evaluate(() => {
      return document.querySelectorAll('.sidebar-nav-item').length;
    });
    assert(
      navItemsAfterEntityNav === 3,
      `3 global nav items remain visible after entity navigation (got ${navItemsAfterEntityNav})`
    );

    // ================================================================
    // 8.2.7: Fleet Overview link is separate from groups
    // ================================================================
    console.log('\n[8.2.7] Fleet Overview link');

    const fleetOverviewExists = await page.evaluate(() => {
      return !!document.querySelector('.sidebar-overview');
    });
    assert(fleetOverviewExists, 'Fleet Overview link exists (.sidebar-overview)');

    // Click Fleet Overview
    await page.evaluate(() => {
      const link = document.querySelector('.sidebar-overview');
      if (link) link.click();
    });
    await page.waitForTimeout(500);

    const foSection = await getActiveSection(page);
    assert(
      foSection === 'fleet-overview-section',
      `Fleet Overview click activates fleet-overview-section (got "${foSection}")`
    );

    // ================================================================
    // Error Checks
    // ================================================================
    console.log('\n[9] Error Checks');

    assert(
      jsErrors.length === 0,
      `No JS errors during tests (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join('; ')})`
    );

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
