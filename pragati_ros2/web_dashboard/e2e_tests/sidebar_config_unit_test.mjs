#!/usr/bin/env node
// Sidebar Config Unit Test (Task 8.1)
// Validates GLOBAL_NAV_ITEMS structure, tab ordering logic, and entity type filtering.
// Run: node web_dashboard/e2e_tests/sidebar_config_unit_test.mjs
//
// Uses Playwright to load the dashboard and import GroupedSidebar ESM module
// in the browser context (modules depend on browser-only Preact/HTM).
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

(async () => {
  console.log('Sidebar Config Unit Tests (Task 8.1)');
  console.log(`Target: ${BASE}`);
  console.log('======================================\n');

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
    // Load dashboard to get access to modules in browser context
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // Import GLOBAL_NAV_ITEMS from GroupedSidebar module
    const navItems = await page.evaluate(async () => {
      const mod = await import('/js/components/GroupedSidebar.mjs');
      const items = mod.GLOBAL_NAV_ITEMS;
      if (!items) return null;
      return items.map(i => ({ id: i.id, label: i.label, icon: i.icon }));
    });

    // ================================================================
    // 8.1.1: GLOBAL_NAV_ITEMS structure validation
    // ================================================================
    console.log('\n[8.1.1] GLOBAL_NAV_ITEMS structure');

    assert(navItems !== null, 'GLOBAL_NAV_ITEMS is exported and importable');
    assert(Array.isArray(navItems), 'GLOBAL_NAV_ITEMS is an array');
    assert(navItems.length === 3, `Exactly 3 global nav items (got ${navItems ? navItems.length : 0})`);

    // Verify item order
    assert(
      navItems[0].id === 'operations',
      `First item is "operations" (got "${navItems[0].id}")`
    );
    assert(
      navItems[1].id === 'monitoring',
      `Second item is "monitoring" (got "${navItems[1].id}")`
    );
    assert(
      navItems[2].id === 'settings',
      `Third item is "settings" (got "${navItems[2].id}")`
    );

    // Verify each item has icon and label
    for (const item of navItems) {
      assert(
        typeof item.icon === 'string' && item.icon.length > 0,
        `Item "${item.id}" has a non-empty icon`
      );
      assert(
        typeof item.label === 'string' && item.label.length > 0,
        `Item "${item.id}" has a non-empty label`
      );
    }

    // ================================================================
    // 8.1.2: Operations nav item
    // ================================================================
    console.log('\n[8.1.2] Operations nav item');

    const ops = navItems.find(i => i.id === 'operations');
    assert(ops.label === 'Operations', `Operations label = "Operations"`);

    // ================================================================
    // 8.1.3: Monitoring nav item
    // ================================================================
    console.log('\n[8.1.3] Monitoring nav item');

    const mon = navItems.find(i => i.id === 'monitoring');
    assert(mon.label === 'Monitoring', `Monitoring label = "Monitoring"`);

    // ================================================================
    // 8.1.4: Settings nav item
    // ================================================================
    console.log('\n[8.1.4] Settings nav item');

    const settings = navItems.find(i => i.id === 'settings');
    assert(settings.label === 'Settings', `Settings label = "Settings"`);

    // ================================================================
    // 8.1.5: Total item count
    // ================================================================
    console.log('\n[8.1.5] Total item count');

    assert(navItems.length === 3, `Total global nav items = 3 (got ${navItems.length})`);

    // ================================================================
    // 8.1.6: No duplicate tab IDs
    // ================================================================
    console.log('\n[8.1.6] No duplicate tab IDs');

    const allIds = navItems.map(i => i.id);
    const uniqueIds = new Set(allIds);
    assert(
      uniqueIds.size === allIds.length,
      `No duplicate tab IDs (${allIds.length} total, ${uniqueIds.size} unique)`
    );

    // ================================================================
    // 8.1.7: No "safety" or "overview" tab in nav items
    // ================================================================
    console.log('\n[8.1.7] Removed tabs not present');

    assert(
      !allIds.includes('safety'),
      'No "safety" tab ID in nav items'
    );
    assert(
      !allIds.includes('overview'),
      'No "overview" tab ID in nav items'
    );
    assert(
      !allIds.includes('system-overview'),
      'No "system-overview" tab ID in nav items'
    );
    assert(
      !allIds.includes('launch-control'),
      'No "launch-control" tab ID in nav items (accessed via Operations hub)'
    );
    assert(
      !allIds.includes('sync-deploy'),
      'No "sync-deploy" tab ID in nav items (accessed via Operations hub)'
    );

    // ================================================================
    // 8.1.8: Entity tab ordering (from rendered sidebar)
    // ================================================================
    console.log('\n[8.1.8] Entity tab ordering (ENTITY_TABS)');

    // ENTITY_TABS is not exported but we can verify via the rendered sidebar
    // when entities are present. If no entities, check the module constant directly.
    const entityTabs = await page.evaluate(async () => {
      // Try reading ENTITY_TABS from the module source
      const resp = await fetch('/js/components/GroupedSidebar.mjs');
      const src = await resp.text();
      // Parse ENTITY_TABS from source — look for the array definition
      const match = src.match(/const ENTITY_TABS\s*=\s*\[([\s\S]*?)\];/);
      if (!match) return null;
      const ids = [];
      const re = /id:\s*"([^"]+)"/g;
      let m;
      while ((m = re.exec(match[1])) !== null) {
        ids.push(m[1]);
      }
      return ids;
    });

    assert(entityTabs !== null, 'ENTITY_TABS definition found in module source');
    if (entityTabs) {
      const expectedEntityTabs = [
        'status', 'nodes', 'topics', 'services', 'parameters',
        'system', 'logs', 'rosbag', 'motor-config',
      ];
      assert(
        entityTabs.length === expectedEntityTabs.length,
        `ENTITY_TABS has ${expectedEntityTabs.length} items (got ${entityTabs.length})`
      );
      for (let i = 0; i < expectedEntityTabs.length; i++) {
        assert(
          entityTabs[i] === expectedEntityTabs[i],
          `ENTITY_TABS[${i}] = "${expectedEntityTabs[i]}" (got "${entityTabs[i]}")`
        );
      }
    }

    // ================================================================
    // 8.1.9: EntityDetailShell tab ordering matches
    // ================================================================
    console.log('\n[8.1.9] EntityDetailShell ENTITY_TABS matches sidebar');

    const shellTabs = await page.evaluate(async () => {
      const resp = await fetch('/js/components/EntityDetailShell.mjs');
      const src = await resp.text();
      const match = src.match(/const ENTITY_TABS\s*=\s*\[([\s\S]*?)\];/);
      if (!match) return null;
      const ids = [];
      const re = /id:\s*"([^"]+)"/g;
      let m;
      while ((m = re.exec(match[1])) !== null) {
        ids.push(m[1]);
      }
      return ids;
    });

    assert(shellTabs !== null, 'EntityDetailShell ENTITY_TABS definition found');
    if (entityTabs && shellTabs) {
      assert(
        JSON.stringify(entityTabs) === JSON.stringify(shellTabs),
        `EntityDetailShell ENTITY_TABS matches GroupedSidebar ENTITY_TABS`
      );
    }

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
  console.log('\n======================================');
  console.log(`Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`);
  if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach(f => console.log(`  - ${f}`));
  }
  console.log();
}
