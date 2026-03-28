#!/usr/bin/env node
// Entity Detail Shell E2E Test Suite (Task 5.7)
//
// Tests the EntityDetailShell component: tab bar, breadcrumb navigation,
// stale-data overlay, initializing placeholder, and StatusHealthTab rendering.
//
// Run: node web_dashboard/e2e_tests/entity_detail_e2e.mjs
//
// Requires: npm install playwright (in e2e_tests directory)
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

// Helper: navigate via hash change
async function navigateToHash(page, hash) {
  await page.evaluate((h) => {
    window.location.hash = h;
  }, hash);
  await page.waitForTimeout(2000);
}

// Helper: get text content of first matching element
async function getTextContent(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    return el ? el.textContent.trim() : null;
  }, selector);
}

// Helper: count elements matching selector
async function countElements(page, selector) {
  return page.evaluate(
    (sel) => document.querySelectorAll(sel).length,
    selector
  );
}

// ---------------------------------------------------------------------------
// Mock data for arm entity (online) — used in tab navigation test
// ---------------------------------------------------------------------------

const ARM1_ONLINE_ENTITY_DATA = {
  id: 'arm1',
  name: 'Arm 1 RPi',
  entity_type: 'arm',
  source: 'remote',
  ip: '192.168.1.101',
  status: 'online',
  last_seen: new Date().toISOString(),
  system_metrics: {
    cpu_percent: 50.0,
    memory_percent: 40.0,
    temperature_c: 45.0,
    disk_percent: 30.0,
    uptime_seconds: 3600,
  },
  ros2_available: true,
  ros2_state: {
    node_count: 2,
    nodes: [
      {
        name: '/arm_controller',
        namespace: '/',
        lifecycle_state: 'active',
      },
      {
        name: '/can_bridge',
        namespace: '/',
        lifecycle_state: 'active',
      },
    ],
  },
  services: [
    {
      name: 'pragati-arm.service',
      active_state: 'active',
      sub_state: 'running',
    },
  ],
  errors: [],
  metadata: {},
};

const ARM1_OFFLINE_ENTITY_DATA = {
  id: 'arm1',
  name: 'Arm 1 RPi',
  entity_type: 'arm',
  source: 'remote',
  ip: '192.168.1.101',
  status: 'offline',
  last_seen: '2024-01-01T00:00:00Z',
  system_metrics: {
    cpu_percent: null,
    memory_percent: null,
    temperature_c: null,
    disk_percent: null,
    uptime_seconds: null,
  },
  ros2_available: false,
  ros2_state: null,
  services: [],
  errors: [],
  metadata: {},
};

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

(async () => {
  console.log('Entity Detail Shell E2E Tests (Task 5.7)');
  console.log(`Target: ${BASE}`);
  console.log('==========================\n');

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });

  const page = await browser.newPage();

  // Collect JS console errors
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  // Also collect uncaught page errors
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  try {
    // ==========================================================
    // Minimal route setup — only intercept what we need to mock
    // Let real API serve /api/entities, /api/entities/local, etc.
    // ==========================================================

    // Abort WebSocket connections (no WS server in test)
    await page.route('**/ws', (route) => route.abort('connectionrefused'));

    // ==========================================================
    // [1] Entity detail loads for local entity (uses REAL API)
    // ==========================================================
    console.log('[1] Entity detail loads for local entity');

    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    await navigateToHash(page, '#/entity/local/status');

    // Verify #entity-detail-section has class "active"
    const sectionActive = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      return section ? section.classList.contains('active') : false;
    });
    assert(sectionActive, 'Entity detail section has .active class');

    // Verify entity name is displayed (real API returns "Local Machine")
    const entityDetailText = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      return section ? section.textContent : '';
    });
    assert(
      entityDetailText.includes('Local Machine'),
      'Entity detail shows entity name "Local Machine"'
    );

    // ==========================================================
    // [2] Status tab renders system metrics (uses REAL API)
    // ==========================================================
    console.log('\n[2] Status tab renders system metrics');

    // Look for stat-card elements (MetricGauge component)
    const statCardCount = await countElements(
      page,
      '#entity-detail-section .stat-card'
    );
    assert(
      statCardCount >= 3,
      `System metric gauge cards rendered (found ${statCardCount}, expected >= 3)`
    );

    // Look for stats-grid container
    const statsGridCount = await countElements(
      page,
      '#entity-detail-section .stats-grid'
    );
    assert(
      statsGridCount >= 1,
      `Stats grid container rendered (found ${statsGridCount})`
    );

    // Verify CPU metric label is present (value is dynamic from real API)
    const hasCpuLabel = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return false;
      const cards = section.querySelectorAll('.stat-card');
      for (const card of cards) {
        if (card.textContent.includes('CPU')) return true;
      }
      return false;
    });
    assert(hasCpuLabel, 'CPU metric gauge card is present');

    // Verify memory metric label
    const hasMemLabel = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return false;
      const cards = section.querySelectorAll('.stat-card');
      for (const card of cards) {
        if (card.textContent.includes('Memory')) return true;
      }
      return false;
    });
    assert(hasMemLabel, 'Memory metric gauge card is present');

    // ==========================================================
    // [3] ROS2 section renders (local has ros2_available=false)
    // ==========================================================
    console.log('\n[3] ROS2 section state');

    // Local entity has ros2_available=false, so ROS2 section should show
    // an unavailable/empty state rather than a node list
    const ros2SectionText = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      return section ? section.textContent : '';
    });

    // The heading "ROS2 Nodes" should still be present
    const hasRos2Heading = ros2SectionText.includes('ROS2 Nodes') ||
      ros2SectionText.includes('ROS2');
    assert(hasRos2Heading, 'ROS2 section heading is present');

    // Since ros2_available=false, verify it shows "not available" or similar
    // OR no node rows are rendered (0 nodes is also valid)
    const ros2NodeRows = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return -1;
      const tables = section.querySelectorAll('.data-table');
      for (const table of tables) {
        const rows = table.querySelectorAll('tbody tr');
        if (rows.length > 0) {
          // Check if this is the ROS2 table by looking for node-like content
          const firstCell = rows[0]?.querySelector('td');
          if (firstCell && firstCell.textContent.startsWith('/')) {
            return rows.length;
          }
        }
      }
      return 0;
    });
    assert(
      ros2NodeRows === 0 ||
        ros2SectionText.includes('not available') ||
        ros2SectionText.includes('unavailable') ||
        ros2SectionText.includes('No nodes') ||
        ros2SectionText.includes('No ROS2'),
      `ROS2 section shows unavailable state or empty (node rows: ${ros2NodeRows})`
    );

    // ==========================================================
    // [4] Systemd section renders (local has services=[])
    // ==========================================================
    console.log('\n[4] Systemd service section state');

    // Local entity has empty services array
    const hasSvcHeading =
      ros2SectionText.includes('Systemd Services') ||
      ros2SectionText.includes('Systemd') ||
      ros2SectionText.includes('Services');
    assert(hasSvcHeading, 'Systemd Services section heading is present');

    // With empty services, expect "No services" or empty table
    const svcTableRows = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return 0;
      const tables = section.querySelectorAll('.data-table');
      for (const table of tables) {
        if (table.textContent.includes('.service')) {
          return table.querySelectorAll('tbody tr').length;
        }
      }
      return 0;
    });
    assert(
      svcTableRows === 0 ||
        ros2SectionText.includes('No services') ||
        ros2SectionText.includes('No systemd'),
      `Systemd section shows empty state or no services (rows: ${svcTableRows})`
    );

    // ==========================================================
    // [5] Tab bar renders
    // ==========================================================
    console.log('\n[5] Tab bar renders');

    // Wait for Preact to render the tab bar
    await page.waitForFunction(
      () => {
        const section = document.getElementById('entity-detail-section');
        if (!section) return false;
        const buttons = section.querySelectorAll('button');
        for (const btn of buttons) {
          if (btn.textContent.includes('Status')) return true;
        }
        return false;
      },
      { timeout: 10000 }
    );

    // Helper function to extract tab labels from button text (handles emoji icons)
    const tabButtons = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return [];
      const buttons = section.querySelectorAll('button');
      const tabs = [];
      // Tab buttons have emoji icons prepended (e.g., "❤️Status & Health")
      // Use .includes() to match the label portion
      const expectedLabels = [
        'Status & Health',
        'Nodes',
        'Topics',
        'Services',
        'Parameters',
        'Logs',
        'Rosbag',
      ];
      for (const btn of buttons) {
        const text = btn.textContent.trim();
        for (const label of expectedLabels) {
          if (text.includes(label)) {
            tabs.push(label);
            break;
          }
        }
      }
      return tabs;
    });
    assert(
      tabButtons.includes('Status & Health'),
      `Tab bar contains "Status & Health" tab (found: ${JSON.stringify(tabButtons)})`
    );
    assert(
      tabButtons.length >= 1,
      `Tab bar has at least 1 tab button (found ${tabButtons.length})`
    );

    // ==========================================================
    // [6] Tab navigation — arm entity tabs work
    // NOTE: Motor Config is a GLOBAL sidebar tab, not per-entity
    // ==========================================================
    console.log('\n[6] Tab navigation for arm entity');

    // Mock arm1 as online for this test
    await page.route('**/api/entities/arm1', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ARM1_ONLINE_ENTITY_DATA),
      })
    );

    await navigateToHash(page, '#/entity/arm1/status');

    // Wait for Preact to render the tab bar
    await page.waitForFunction(
      () => {
        const section = document.getElementById('entity-detail-section');
        if (!section) return false;
        const buttons = section.querySelectorAll('button');
        for (const btn of buttons) {
          if (btn.textContent.includes('Status')) return true;
        }
        return false;
      },
      { timeout: 10000 }
    );

    // Arm entity should show same tabs (Motor Config is a global sidebar tab)
    const armTabButtons = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return [];
      const buttons = section.querySelectorAll('button');
      const tabs = [];
      const expectedLabels = [
        'Status & Health',
        'Nodes',
        'Topics',
        'Services',
        'Parameters',
        'Logs',
        'Rosbag',
      ];
      for (const btn of buttons) {
        const text = btn.textContent.trim();
        for (const label of expectedLabels) {
          if (text.includes(label)) {
            tabs.push(label);
            break;
          }
        }
      }
      return tabs;
    });
    assert(
      armTabButtons.includes('Status & Health'),
      `Arm entity tab bar contains "Status & Health" tab (found: ${JSON.stringify(armTabButtons)})`
    );
    assert(
      armTabButtons.length >= 1,
      `Arm entity tab bar has at least 1 tab button (found ${armTabButtons.length})`
    );

    // ==========================================================
    // [7] Breadcrumb navigation (uses REAL API for local entity)
    // ==========================================================
    console.log('\n[7] Breadcrumb navigation');

    // Unroute arm1 mock so it doesn't affect other tests
    await page.unroute('**/api/entities/arm1');

    await navigateToHash(page, '#/entity/local/status');

    // Verify breadcrumb contains Fleet link, entity name, and tab name
    const breadcrumbText = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return '';
      const nav = section.querySelector('nav[aria-label="Breadcrumb"]');
      return nav ? nav.textContent.trim() : '';
    });
    assert(
      breadcrumbText.includes('Fleet'),
      `Breadcrumb contains "Fleet" (got: "${breadcrumbText}")`
    );
    assert(
      breadcrumbText.includes('Local Machine'),
      `Breadcrumb contains entity name "Local Machine" (got: "${breadcrumbText}")`
    );
    assert(
      breadcrumbText.includes('Status'),
      `Breadcrumb contains tab name "Status" (got: "${breadcrumbText}")`
    );

    // Click "Fleet" in breadcrumb to navigate back
    const fleetLinkClicked = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return false;
      const nav = section.querySelector('nav[aria-label="Breadcrumb"]');
      if (!nav) return false;
      const links = nav.querySelectorAll('a');
      for (const link of links) {
        if (link.textContent.trim() === 'Fleet') {
          link.click();
          return true;
        }
      }
      return false;
    });
    assert(fleetLinkClicked, 'Fleet breadcrumb link was clicked');

    await page.waitForTimeout(1000);

    // Verify hash changed to fleet overview
    const hashAfterBreadcrumb = await page.evaluate(() => location.hash);
    assert(
      hashAfterBreadcrumb === '#fleet-overview' ||
        hashAfterBreadcrumb === '#fleet',
      `Hash navigated to fleet page after breadcrumb click (got: "${hashAfterBreadcrumb}")`
    );

    // ==========================================================
    // [8] Stale indicator for offline entity
    // ==========================================================
    console.log('\n[8] Stale indicator for offline entity');

    // Mock arm1 as offline
    await page.route('**/api/entities/arm1', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ARM1_OFFLINE_ENTITY_DATA),
      })
    );

    await navigateToHash(page, '#/entity/arm1/status');

    const staleText = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return '';
      return section.textContent;
    });
    assert(
      staleText.includes('Entity unreachable') ||
        staleText.includes('offline') ||
        staleText.includes('Offline') ||
        staleText.includes('unreachable'),
      `Stale/offline indicator shown for offline entity (found relevant text: ${staleText.includes('unreachable') || staleText.includes('offline')})`
    );

    // Verify entity status badge shows offline state
    const hasOfflineBadge = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return false;
      return (
        section.textContent.includes('offline') ||
        section.textContent.includes('Offline')
      );
    });
    assert(hasOfflineBadge, 'Offline entity shows "offline" status');

    // Clean up arm1 route
    await page.unroute('**/api/entities/arm1');

    // ==========================================================
    // [9] Initializing state — entity data not yet loaded
    // ==========================================================
    console.log('\n[9] Initializing state');

    // Route a fake entity with a long delay to simulate loading
    await page.route('**/api/entities/fake-slow-entity', (route) => {
      // Don't fulfill — let the component show "Initializing..."
      // We'll check before the response arrives
      setTimeout(() => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'fake-slow-entity',
            name: 'Slow Entity',
            entity_type: 'arm',
            source: 'remote',
            ip: '10.0.0.99',
            status: 'unknown',
            last_seen: null,
            system_metrics: {
              cpu_percent: null,
              memory_percent: null,
              temperature_c: null,
              disk_percent: null,
              uptime_seconds: null,
            },
            ros2_available: false,
            ros2_state: null,
            services: [],
            errors: [],
            metadata: {},
          }),
        });
      }, 10000); // Long delay — we check at 500ms
    });

    await navigateToHash(page, '#/entity/fake-slow-entity/status');

    // Wait briefly — the component should show "Initializing..." before data arrives
    await page.waitForTimeout(500);

    const initializingText = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return '';
      return section.textContent;
    });
    assert(
      initializingText.includes('Initializing') ||
        initializingText.includes('Loading'),
      `Initializing placeholder shown before data arrives (text snippet: "${initializingText.substring(0, 100)}")`
    );

    // Verify the initializing-placeholder class is present
    const hasInitPlaceholder = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return false;
      return section.querySelector('.initializing-placeholder') !== null;
    });
    assert(
      hasInitPlaceholder,
      'Initializing placeholder element with .initializing-placeholder class exists'
    );

    // Clean up
    await page.unroute('**/api/entities/fake-slow-entity');

    // ==========================================================
    // [10] Subsystem health badges render (uses REAL API)
    // ==========================================================
    console.log('\n[10] Subsystem health badges');

    await navigateToHash(page, '#/entity/local/status');

    // Check for health-card elements (SubsystemHealthRow)
    const healthCardCount = await countElements(
      page,
      '#entity-detail-section .health-card'
    );
    assert(
      healthCardCount >= 3,
      `Subsystem health badges rendered (found ${healthCardCount}, expected >= 3)`
    );

    // Verify specific subsystem labels
    const hasSystemBadge = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return false;
      const cards = section.querySelectorAll('.health-card');
      for (const card of cards) {
        if (card.textContent.includes('System')) return true;
      }
      return false;
    });
    assert(hasSystemBadge, 'System subsystem health badge rendered');

    const hasRos2Badge = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return false;
      const cards = section.querySelectorAll('.health-card');
      for (const card of cards) {
        if (card.textContent.includes('ROS2')) return true;
      }
      return false;
    });
    assert(hasRos2Badge, 'ROS2 subsystem health badge rendered');

    // ==========================================================
    // [11] No JS console errors
    // ==========================================================
    console.log('\n[11] No JS console errors');

    // Filter out expected errors: WebSocket, connection refused, 404 for mocked entities
    const relevantErrors = consoleErrors.filter(
      (e) =>
        !e.includes('WebSocket') &&
        !e.includes('ws://') &&
        !e.includes('wss://') &&
        !e.includes('ERR_CONNECTION_REFUSED') &&
        !e.includes('net::ERR_FAILED') &&
        !e.includes('404') &&
        !e.includes('Failed to fetch') &&
        !e.includes('fake-slow-entity')
    );

    assert(
      relevantErrors.length === 0,
      'No relevant JS console errors during entity detail usage' +
        (relevantErrors.length > 0
          ? ` (got ${relevantErrors.length}: ${relevantErrors.slice(0, 3).join('; ')})`
          : '')
    );

    const relevantPageErrors = pageErrors.filter(
      (e) =>
        !e.includes('WebSocket') &&
        !e.includes('ERR_CONNECTION_REFUSED') &&
        !e.includes('404') &&
        !e.includes('fetch')
    );
    assert(
      relevantPageErrors.length === 0,
      'No uncaught page errors during entity detail usage' +
        (relevantPageErrors.length > 0
          ? ` (got ${relevantPageErrors.length}: ${relevantPageErrors.slice(0, 3).join('; ')})`
          : '')
    );
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
  console.log(
    `Results: ${passed} passed, ${failed} failed, ` +
      `${skipped} skipped (${total} total)`
  );
  if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach((f) => console.log(`  - ${f}`));
  }
  console.log();
  process.exit(failed > 0 ? 1 : 0);
})();
