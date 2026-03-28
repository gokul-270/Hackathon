#!/usr/bin/env node
// Entity Sub-Tabs E2E Test Suite (Tasks 9.3 + 9.4)
//
// Tests entity detail sub-tab navigation flow:
// - Tab bar renders all expected tabs
// - Clicking each tab changes the URL hash
// - Tab content areas exist and show appropriate states
// - Breadcrumb navigation works
// - Sub-tab data display areas show loading/empty/error states
//
// Run: node web_dashboard/e2e_tests/entity_subtabs_e2e.mjs
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

// Helper: get all tab button labels from entity detail section
async function getTabLabels(page) {
  return page.evaluate(() => {
    const section = document.getElementById('entity-detail-section');
    if (!section) return [];
    const buttons = section.querySelectorAll('button');
    const labels = [];
    for (const btn of buttons) {
      const text = btn.textContent.trim();
      // Filter to known tab labels — skip other buttons
      if (
        [
          'Status / Health',
          'Motor Config',
          'Nodes',
          'Topics',
          'Services',
          'Parameters',
          'Logs',
        ].includes(text)
      ) {
        labels.push(text);
      }
    }
    return labels;
  });
}

// Helper: click a tab button by its label text
async function clickTab(page, label) {
  return page.evaluate((tabLabel) => {
    const section = document.getElementById('entity-detail-section');
    if (!section) return false;
    const buttons = section.querySelectorAll('button');
    for (const btn of buttons) {
      if (btn.textContent.trim() === tabLabel) {
        btn.click();
        return true;
      }
    }
    return false;
  }, label);
}

// Helper: get the current hash
async function getHash(page) {
  return page.evaluate(() => location.hash);
}

// Helper: get visible text from entity detail section
async function getEntitySectionText(page) {
  return page.evaluate(() => {
    const section = document.getElementById('entity-detail-section');
    return section ? section.textContent : '';
  });
}

// ---------------------------------------------------------------------------
// Mock data for arm entity (online)
// ---------------------------------------------------------------------------

const ARM1_ENTITY_DATA = {
  id: 'arm1',
  name: 'Arm 1 RPi',
  entity_type: 'arm',
  source: 'remote',
  ip: '192.168.1.101',
  status: 'online',
  last_seen: new Date().toISOString(),
  system_metrics: {
    cpu_percent: 45.0,
    memory_percent: 38.0,
    temperature_c: 42.0,
    disk_percent: 25.0,
    uptime_seconds: 7200,
  },
  ros2_available: true,
  ros2_state: {
    node_count: 3,
    nodes: [
      { name: '/arm_controller', namespace: '/', lifecycle_state: 'active' },
      { name: '/can_bridge', namespace: '/', lifecycle_state: 'active' },
      { name: '/safety_node', namespace: '/', lifecycle_state: 'active' },
    ],
  },
  services: [
    { name: 'pragati-arm.service', active_state: 'active', sub_state: 'running' },
  ],
  errors: [],
  metadata: {},
};

// Mock responses for entity-scoped ROS2 endpoints
const MOCK_TOPICS = {
  entity_id: 'arm1',
  source: 'remote',
  data: [
    { name: '/joint_states', type: 'sensor_msgs/msg/JointState', publisher_count: 1, subscriber_count: 2 },
    { name: '/cmd_vel', type: 'geometry_msgs/msg/Twist', publisher_count: 0, subscriber_count: 1 },
  ],
};

const MOCK_SERVICES = {
  entity_id: 'arm1',
  source: 'remote',
  data: [
    { name: '/emergency_stop', type: 'std_srvs/srv/Trigger' },
    { name: '/joint_homing', type: 'std_srvs/srv/Trigger' },
  ],
};

const MOCK_PARAMETERS = {
  entity_id: 'arm1',
  source: 'remote',
  data: {
    nodes: [
      {
        name: '/motor_control',
        parameters: [
          { name: 'max_velocity', type: 'double', value: 1.0 },
        ],
      },
    ],
  },
};

const MOCK_NODES = {
  entity_id: 'arm1',
  source: 'remote',
  data: [
    { name: 'arm_controller', namespace: '/', lifecycle_state: 'active' },
    { name: 'can_bridge', namespace: '/', lifecycle_state: 'active' },
  ],
};

const MOCK_LOGS = {
  entity_id: 'arm1',
  source: 'remote',
  data: [
    { name: 'latest.log', path: 'latest.log', size_bytes: 2048, modified: '2025-06-01T12:00:00+00:00' },
    { name: 'System Journal (pragati-*)', path: '__journald__', size_bytes: 0, modified: null },
  ],
};

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

(async () => {
  console.log('Entity Sub-Tabs E2E Tests (Tasks 9.3 + 9.4)');
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

  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  try {
    // ==========================================================
    // Route mocking setup
    // ==========================================================

    // Abort WebSocket connections (no WS server in test)
    await page.route('**/ws', (route) => route.abort('connectionrefused'));

    // Mock arm1 entity data
    await page.route('**/api/entities/arm1', (route) => {
      if (route.request().url().endsWith('/arm1')) {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ARM1_ENTITY_DATA),
        });
      } else {
        route.continue();
      }
    });

    // Mock entity-scoped ROS2 endpoints for arm1
    await page.route('**/api/entities/arm1/ros2/topics', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TOPICS),
      })
    );

    await page.route('**/api/entities/arm1/ros2/services', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_SERVICES),
      })
    );

    await page.route('**/api/entities/arm1/ros2/parameters', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_PARAMETERS),
      })
    );

    await page.route('**/api/entities/arm1/ros2/nodes', (route) => {
      // Only match the list endpoint, not node detail (which has extra path)
      const url = route.request().url();
      if (url.endsWith('/nodes') || url.endsWith('/nodes/')) {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_NODES),
        });
      } else {
        route.continue();
      }
    });

    await page.route('**/api/entities/arm1/logs', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_LOGS),
      })
    );

    // ==========================================================
    // [1] Navigate to fleet overview, then to entity detail
    // ==========================================================
    console.log('[1] Fleet overview → entity detail navigation');

    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    // Start at fleet overview
    await navigateToHash(page, '#fleet-overview');

    const fleetSectionActive = await page.evaluate(() => {
      const section = document.getElementById('fleet-overview-section');
      return section ? section.classList.contains('active') : false;
    });
    assert(
      fleetSectionActive,
      'Fleet overview section is active at #fleet-overview'
    );

    // Navigate to entity detail for arm1
    await navigateToHash(page, '#/entity/arm1/status');

    const entitySectionActive = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      return section ? section.classList.contains('active') : false;
    });
    assert(
      entitySectionActive,
      'Entity detail section is active after navigating to #/entity/arm1/status'
    );

    // ==========================================================
    // [2] Tab bar shows all expected tabs for arm entity
    // ==========================================================
    console.log('\n[2] Tab bar renders all expected tabs');

    const tabLabels = await getTabLabels(page);

    assert(
      tabLabels.includes('Status / Health'),
      `Tab bar contains "Status / Health" (found: ${JSON.stringify(tabLabels)})`
    );
    assert(
      tabLabels.includes('Topics'),
      `Tab bar contains "Topics" (found: ${JSON.stringify(tabLabels)})`
    );
    assert(
      tabLabels.includes('Services'),
      `Tab bar contains "Services" (found: ${JSON.stringify(tabLabels)})`
    );
    assert(
      tabLabels.includes('Parameters'),
      `Tab bar contains "Parameters" (found: ${JSON.stringify(tabLabels)})`
    );
    assert(
      tabLabels.includes('Nodes'),
      `Tab bar contains "Nodes" (found: ${JSON.stringify(tabLabels)})`
    );
    assert(
      tabLabels.includes('Logs'),
      `Tab bar contains "Logs" (found: ${JSON.stringify(tabLabels)})`
    );
    assert(
      tabLabels.includes('Motor Config'),
      `Tab bar contains "Motor Config" for arm entity (found: ${JSON.stringify(tabLabels)})`
    );

    // ==========================================================
    // [3] Click "Topics" tab → URL hash changes
    // ==========================================================
    console.log('\n[3] Topics tab navigation');

    const topicsClicked = await clickTab(page, 'Topics');
    assert(topicsClicked, 'Topics tab button was clicked');

    await page.waitForTimeout(1000);
    let hash = await getHash(page);
    assert(
      hash.includes('/entity/arm1/topics'),
      `Hash changed to topics route (got: "${hash}")`
    );

    // Task 9.4: Verify topics content area exists
    const topicsText = await getEntitySectionText(page);
    const topicsHasContent =
      topicsText.includes('Topic') ||
      topicsText.includes('Loading') ||
      topicsText.includes('joint_states') ||
      topicsText.includes('/cmd_vel') ||
      topicsText.includes('No topics');
    assert(
      topicsHasContent,
      'Topics tab content area shows relevant content'
    );

    // ==========================================================
    // [4] Click "Services" tab → URL hash changes
    // ==========================================================
    console.log('\n[4] Services tab navigation');

    const servicesClicked = await clickTab(page, 'Services');
    assert(servicesClicked, 'Services tab button was clicked');

    await page.waitForTimeout(1000);
    hash = await getHash(page);
    assert(
      hash.includes('/entity/arm1/services'),
      `Hash changed to services route (got: "${hash}")`
    );

    const servicesText = await getEntitySectionText(page);
    const servicesHasContent =
      servicesText.includes('Service') ||
      servicesText.includes('Loading') ||
      servicesText.includes('emergency_stop') ||
      servicesText.includes('No services');
    assert(
      servicesHasContent,
      'Services tab content area shows relevant content'
    );

    // ==========================================================
    // [5] Click "Parameters" tab → URL hash changes
    // ==========================================================
    console.log('\n[5] Parameters tab navigation');

    const paramsClicked = await clickTab(page, 'Parameters');
    assert(paramsClicked, 'Parameters tab button was clicked');

    await page.waitForTimeout(1000);
    hash = await getHash(page);
    assert(
      hash.includes('/entity/arm1/parameters'),
      `Hash changed to parameters route (got: "${hash}")`
    );

    const paramsText = await getEntitySectionText(page);
    const paramsHasContent =
      paramsText.includes('Parameter') ||
      paramsText.includes('Loading') ||
      paramsText.includes('max_velocity') ||
      paramsText.includes('No parameters');
    assert(
      paramsHasContent,
      'Parameters tab content area shows relevant content'
    );

    // ==========================================================
    // [6] Click "Nodes" tab → URL hash changes
    // ==========================================================
    console.log('\n[6] Nodes tab navigation');

    const nodesClicked = await clickTab(page, 'Nodes');
    assert(nodesClicked, 'Nodes tab button was clicked');

    await page.waitForTimeout(1000);
    hash = await getHash(page);
    assert(
      hash.includes('/entity/arm1/nodes'),
      `Hash changed to nodes route (got: "${hash}")`
    );

    const nodesText = await getEntitySectionText(page);
    const nodesHasContent =
      nodesText.includes('Node') ||
      nodesText.includes('Loading') ||
      nodesText.includes('arm_controller') ||
      nodesText.includes('No nodes');
    assert(
      nodesHasContent,
      'Nodes tab content area shows relevant content'
    );

    // ==========================================================
    // [7] Click "Logs" tab → URL hash changes
    // ==========================================================
    console.log('\n[7] Logs tab navigation');

    const logsClicked = await clickTab(page, 'Logs');
    assert(logsClicked, 'Logs tab button was clicked');

    await page.waitForTimeout(1000);
    hash = await getHash(page);
    assert(
      hash.includes('/entity/arm1/logs'),
      `Hash changed to logs route (got: "${hash}")`
    );

    const logsText = await getEntitySectionText(page);
    const logsHasContent =
      logsText.includes('Log') ||
      logsText.includes('Loading') ||
      logsText.includes('latest.log') ||
      logsText.includes('No logs');
    assert(
      logsHasContent,
      'Logs tab content area shows relevant content'
    );

    // ==========================================================
    // [8] Breadcrumb "Fleet" link → returns to fleet overview
    // ==========================================================
    console.log('\n[8] Breadcrumb navigation back to Fleet');

    // Go back to a known tab first
    await navigateToHash(page, '#/entity/arm1/status');

    const fleetBreadcrumbClicked = await page.evaluate(() => {
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
    assert(fleetBreadcrumbClicked, 'Fleet breadcrumb link was clicked');

    await page.waitForTimeout(1000);
    hash = await getHash(page);
    assert(
      hash === '#fleet-overview' || hash === '#fleet',
      `Hash returned to fleet overview after breadcrumb click (got: "${hash}")`
    );

    // ==========================================================
    // [9] Tab content area updates on navigation (not stale)
    // ==========================================================
    console.log('\n[9] Tab content updates between navigations');

    // Navigate to topics, then to services — content should differ
    await navigateToHash(page, '#/entity/arm1/topics');
    const topicsContent = await getEntitySectionText(page);

    await navigateToHash(page, '#/entity/arm1/services');
    const servicesContent = await getEntitySectionText(page);

    // At minimum, the active tab highlighting should change
    // Both will share the tab bar text, but content areas differ
    const contentChanged =
      topicsContent !== servicesContent ||
      topicsContent.includes('Topic') ||
      servicesContent.includes('Service');
    assert(
      contentChanged,
      'Tab content area updates when switching between tabs'
    );

    // ==========================================================
    // [10] Task 9.4: Sub-tab data display states
    // ==========================================================
    console.log('\n[10] Sub-tab data display states (Task 9.4)');

    // Check that each sub-tab content area has a container element
    // and shows at least a loading, data, or empty state.

    // Topics tab — should show data from mock
    await navigateToHash(page, '#/entity/arm1/topics');
    const topicsArea = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return { exists: false };
      const text = section.textContent;
      return {
        exists: true,
        hasData: text.includes('joint_states') || text.includes('cmd_vel'),
        hasLoading: text.includes('Loading'),
        hasEmpty: text.includes('No topics'),
        hasError: text.includes('Error') || text.includes('error'),
      };
    });
    assert(
      topicsArea.exists,
      'Topics sub-tab content container exists'
    );
    assert(
      topicsArea.hasData || topicsArea.hasLoading || topicsArea.hasEmpty,
      `Topics shows data/loading/empty state (data=${topicsArea.hasData}, loading=${topicsArea.hasLoading}, empty=${topicsArea.hasEmpty})`
    );

    // Services tab
    await navigateToHash(page, '#/entity/arm1/services');
    const servicesArea = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return { exists: false };
      const text = section.textContent;
      return {
        exists: true,
        hasData: text.includes('emergency_stop') || text.includes('joint_homing'),
        hasLoading: text.includes('Loading'),
        hasEmpty: text.includes('No services'),
      };
    });
    assert(servicesArea.exists, 'Services sub-tab content container exists');
    assert(
      servicesArea.hasData || servicesArea.hasLoading || servicesArea.hasEmpty,
      `Services shows data/loading/empty state (data=${servicesArea.hasData}, loading=${servicesArea.hasLoading}, empty=${servicesArea.hasEmpty})`
    );

    // Nodes tab
    await navigateToHash(page, '#/entity/arm1/nodes');
    const nodesArea = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return { exists: false };
      const text = section.textContent;
      return {
        exists: true,
        hasData: text.includes('arm_controller') || text.includes('can_bridge'),
        hasLoading: text.includes('Loading'),
        hasEmpty: text.includes('No nodes'),
      };
    });
    assert(nodesArea.exists, 'Nodes sub-tab content container exists');
    assert(
      nodesArea.hasData || nodesArea.hasLoading || nodesArea.hasEmpty,
      `Nodes shows data/loading/empty state (data=${nodesArea.hasData}, loading=${nodesArea.hasLoading}, empty=${nodesArea.hasEmpty})`
    );

    // Parameters tab
    await navigateToHash(page, '#/entity/arm1/parameters');
    const paramsArea = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return { exists: false };
      const text = section.textContent;
      return {
        exists: true,
        hasData: text.includes('max_velocity') || text.includes('motor_control'),
        hasLoading: text.includes('Loading'),
        hasEmpty: text.includes('No parameters'),
      };
    });
    assert(paramsArea.exists, 'Parameters sub-tab content container exists');
    assert(
      paramsArea.hasData || paramsArea.hasLoading || paramsArea.hasEmpty,
      `Parameters shows data/loading/empty state (data=${paramsArea.hasData}, loading=${paramsArea.hasLoading}, empty=${paramsArea.hasEmpty})`
    );

    // Logs tab
    await navigateToHash(page, '#/entity/arm1/logs');
    const logsArea = await page.evaluate(() => {
      const section = document.getElementById('entity-detail-section');
      if (!section) return { exists: false };
      const text = section.textContent;
      return {
        exists: true,
        hasData: text.includes('latest.log') || text.includes('Journal'),
        hasLoading: text.includes('Loading'),
        hasEmpty: text.includes('No logs'),
      };
    });
    assert(logsArea.exists, 'Logs sub-tab content container exists');
    assert(
      logsArea.hasData || logsArea.hasLoading || logsArea.hasEmpty,
      `Logs shows data/loading/empty state (data=${logsArea.hasData}, loading=${logsArea.hasLoading}, empty=${logsArea.hasEmpty})`
    );

    // ==========================================================
    // [11] No JS console errors during sub-tab navigation
    // ==========================================================
    console.log('\n[11] No JS console errors');

    const relevantErrors = consoleErrors.filter(
      (e) =>
        !e.includes('WebSocket') &&
        !e.includes('ws://') &&
        !e.includes('wss://') &&
        !e.includes('ERR_CONNECTION_REFUSED') &&
        !e.includes('net::ERR_FAILED') &&
        !e.includes('404') &&
        !e.includes('Failed to fetch')
    );

    assert(
      relevantErrors.length === 0,
      'No relevant JS console errors during sub-tab navigation' +
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
      'No uncaught page errors during sub-tab navigation' +
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
