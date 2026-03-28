#!/usr/bin/env node
// Fleet Tab E2E Tests
// Tests: RPi card rendering, online/offline indicators, drill-down links,
//        sync/logs action buttons, empty fleet state, arm operational data.
// Run: node web_dashboard/e2e_tests/fleet_tab_e2e.mjs
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

// Helper: check element exists
async function exists(page, selector) {
  return page.evaluate(
    (sel) => !!document.querySelector(sel),
    selector
  );
}

// Helper: navigate to tab via hash change
async function navigateToSection(page, sectionName) {
  await page.evaluate((name) => {
    window.location.hash = '#' + name;
  }, sectionName);
  await page.waitForTimeout(1500);
}

// Helper: count elements matching selector
async function countElements(page, selector) {
  return page.evaluate(
    (sel) => document.querySelectorAll(sel).length,
    selector
  );
}

// Helper: get text content of first matching element
async function getTextContent(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    return el ? el.textContent.trim() : null;
  }, selector);
}

// Helper: get text content of all matching elements
async function getAllTextContents(page, selector) {
  return page.evaluate((sel) => {
    return Array.from(document.querySelectorAll(sel)).map(
      (el) => el.textContent.trim()
    );
  }, selector);
}

// Helper: check if Preact container has rendered content
async function preactContainerHasContent(page, sectionId) {
  return page.evaluate((id) => {
    const el = document.getElementById(`${id}-section-preact`);
    return el ? el.innerHTML.trim().length > 0 : false;
  }, sectionId);
}

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const FLEET_STATUS_POPULATED = {
  members: [
    {
      name: 'vehicle-rpi',
      role: 'vehicle',
      ip: '192.168.1.100',
      status: 'online',
      cpu_percent: 45.2,
      memory_percent: 62.1,
      last_seen: '2025-01-01T00:00:00Z',
      operational_state: null,
      pick_count: 0,
    },
    {
      name: 'arm1-rpi',
      role: 'arm',
      ip: '192.168.1.101',
      status: 'online',
      cpu_percent: 55.0,
      memory_percent: 40.0,
      last_seen: '2025-01-01T00:00:00Z',
      operational_state: 'PICKING',
      pick_count: 12,
    },
    {
      name: 'arm2-rpi',
      role: 'arm',
      ip: '192.168.1.102',
      status: 'offline',
      cpu_percent: null,
      memory_percent: null,
      last_seen: '2025-01-01T00:00:00Z',
      operational_state: 'ERROR',
      pick_count: 3,
    },
  ],
};

const FLEET_STATUS_EMPTY = { members: [] };

const ROLE_RESPONSE = { role: 'dev' };

// ---------------------------------------------------------------------------
// Route setup helpers
// ---------------------------------------------------------------------------

/**
 * Install mock routes for populated fleet.
 * Returns a function to uninstall the routes.
 */
async function setupPopulatedFleetRoutes(page) {
  await page.route('**/api/config/role', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ROLE_RESPONSE),
    })
  );
  await page.route('**/api/fleet/status', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(FLEET_STATUS_POPULATED),
    })
  );
}

/**
 * Install mock routes for empty fleet.
 */
async function setupEmptyFleetRoutes(page) {
  await page.route('**/api/config/role', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(ROLE_RESPONSE),
    })
  );
  await page.route('**/api/fleet/status', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(FLEET_STATUS_EMPTY),
    })
  );
}

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

(async () => {
  console.log('Fleet Tab E2E Tests');
  console.log(`Target: ${BASE}`);
  console.log('==========================\n');

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });

  try {
    // ==========================================================
    // PART A — Populated fleet tests
    // ==========================================================
    console.log('[A] Populated fleet tests');

    const pageA = await browser.newPage();
    const jsErrorsA = [];
    pageA.on('pageerror', (err) => jsErrorsA.push(err.message));

    await setupPopulatedFleetRoutes(pageA);

    await pageA.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await pageA.waitForTimeout(1000);

    // Navigate to fleet tab
    await navigateToSection(pageA, 'fleet');

    // Wait for fleet data to render (route is mocked, but Preact needs time)
    await pageA.waitForTimeout(1000);

    // ----------------------------------------------------------
    // [1] Fleet tab renders RPi cards with correct names and roles
    // ----------------------------------------------------------
    console.log('\n[1] RPi cards render with names and roles');

    const cardCount = await countElements(pageA, '.fleet-rpi-card');
    assert(
      cardCount === 3,
      `Fleet tab renders 3 RPi cards (got ${cardCount})`
    );

    const names = await getAllTextContents(pageA, '.fleet-rpi-name');
    assert(
      names.includes('vehicle-rpi'),
      'Card for vehicle-rpi is rendered'
    );
    assert(
      names.includes('arm1-rpi'),
      'Card for arm1-rpi is rendered'
    );
    assert(
      names.includes('arm2-rpi'),
      'Card for arm2-rpi is rendered'
    );

    const roleBadges = await getAllTextContents(pageA, '.fleet-role-badge');
    assert(
      roleBadges.some((r) => r.toLowerCase() === 'vehicle'),
      'Vehicle role badge is displayed'
    );
    assert(
      roleBadges.filter((r) => r.toLowerCase() === 'arm').length === 2,
      'Two arm role badges are displayed'
    );

    // ----------------------------------------------------------
    // [2] Offline RPi shows offline indicator
    // ----------------------------------------------------------
    console.log('\n[2] Offline RPi shows offline indicator');

    const offlineDots = await countElements(
      pageA, '.fleet-status-offline'
    );
    assert(
      offlineDots >= 1,
      `At least one offline status dot exists (got ${offlineDots})`
    );

    // Verify arm2-rpi card specifically has offline indicator
    const arm2Offline = await pageA.evaluate(() => {
      const cards = document.querySelectorAll('.fleet-rpi-card');
      for (const card of cards) {
        const nameEl = card.querySelector('.fleet-rpi-name');
        if (nameEl && nameEl.textContent.trim() === 'arm2-rpi') {
          return !!card.querySelector('.fleet-status-offline');
        }
      }
      return false;
    });
    assert(arm2Offline, 'arm2-rpi card has offline status dot');

    // ----------------------------------------------------------
    // [3] Online RPi shows online indicator
    // ----------------------------------------------------------
    console.log('\n[3] Online RPi shows online indicator');

    const onlineDots = await countElements(
      pageA, '.fleet-status-online'
    );
    assert(
      onlineDots >= 1,
      `At least one online status dot exists (got ${onlineDots})`
    );

    // Verify vehicle-rpi card has online indicator
    const vehicleOnline = await pageA.evaluate(() => {
      const cards = document.querySelectorAll('.fleet-rpi-card');
      for (const card of cards) {
        const nameEl = card.querySelector('.fleet-rpi-name');
        if (nameEl && nameEl.textContent.trim() === 'vehicle-rpi') {
          return !!card.querySelector('.fleet-status-online');
        }
      }
      return false;
    });
    assert(vehicleOnline, 'vehicle-rpi card has online status dot');

    // ----------------------------------------------------------
    // [4] Drill-down link exists with correct href
    // ----------------------------------------------------------
    console.log('\n[4] Drill-down via card header click');

    // The FleetTab opens drill-down via window.open on header click.
    // Verify that the card header is clickable (has cursor pointer style)
    // and that clicking it triggers navigation to the correct URL.
    const headerClickable = await pageA.evaluate(() => {
      const header = document.querySelector('.fleet-rpi-card-header');
      if (!header) return false;
      const style = getComputedStyle(header);
      return style.cursor === 'pointer';
    });
    assert(
      headerClickable,
      'Card header is clickable (cursor: pointer)'
    );

    // Intercept window.open to verify drill-down URL
    const drillDownUrl = await pageA.evaluate(() => {
      return new Promise((resolve) => {
        const origOpen = window.open;
        window.open = (url) => {
          resolve(url);
          window.open = origOpen;
        };
        // Click the first card header (vehicle-rpi, ip 192.168.1.100)
        const header = document.querySelector(
          '.fleet-rpi-card-header'
        );
        if (header) header.click();
        // Fallback in case click does not trigger window.open
        setTimeout(() => resolve(null), 2000);
      });
    });
    assert(
      drillDownUrl === 'http://192.168.1.100:8090',
      `Drill-down opens correct URL (got: "${drillDownUrl}")`
    );

    // ----------------------------------------------------------
    // [5] "Sync All" button exists and is clickable
    // ----------------------------------------------------------
    console.log('\n[5] Sync All button');

    const syncBtnExists = await exists(pageA, '.fleet-sync-btn');
    assert(syncBtnExists, '"Sync All" button exists');

    const syncBtnText = await getTextContent(
      pageA, '.fleet-sync-btn'
    );
    assert(
      syncBtnText === 'Sync All',
      `Sync button text is "Sync All" (got: "${syncBtnText}")`
    );

    const syncBtnDisabled = await pageA.evaluate(() => {
      const btn = document.querySelector('.fleet-sync-btn');
      return btn ? btn.disabled : true;
    });
    assert(
      !syncBtnDisabled,
      'Sync All button is not disabled (clickable)'
    );

    // ----------------------------------------------------------
    // [6] "Collect Logs" button exists and is clickable
    // ----------------------------------------------------------
    console.log('\n[6] Collect Logs button');

    const logsBtnExists = await exists(pageA, '.fleet-logs-btn');
    assert(logsBtnExists, '"Collect Logs" button exists');

    const logsBtnText = await getTextContent(
      pageA, '.fleet-logs-btn'
    );
    assert(
      logsBtnText === 'Collect Logs',
      `Logs button text is "Collect Logs" (got: "${logsBtnText}")`
    );

    const logsBtnDisabled = await pageA.evaluate(() => {
      const btn = document.querySelector('.fleet-logs-btn');
      return btn ? btn.disabled : true;
    });
    assert(
      !logsBtnDisabled,
      'Collect Logs button is not disabled (clickable)'
    );

    // ----------------------------------------------------------
    // [8] Arm cards show operational state
    // ----------------------------------------------------------
    console.log('\n[8] Arm cards show operational state');

    const arm1State = await pageA.evaluate(() => {
      const cards = document.querySelectorAll('.fleet-rpi-card');
      for (const card of cards) {
        const nameEl = card.querySelector('.fleet-rpi-name');
        if (nameEl && nameEl.textContent.trim() === 'arm1-rpi') {
          const rows = card.querySelectorAll('.fleet-rpi-info-row');
          for (const row of rows) {
            const label = row.querySelector(
              '.fleet-rpi-info-label'
            );
            if (label && label.textContent.trim() === 'State:') {
              const value = row.querySelector(
                '.fleet-rpi-info-value'
              );
              return value ? value.textContent.trim() : null;
            }
          }
        }
      }
      return null;
    });
    assert(
      arm1State === 'PICKING',
      `arm1-rpi shows operational state "PICKING" (got: "${arm1State}")`
    );

    const arm2State = await pageA.evaluate(() => {
      const cards = document.querySelectorAll('.fleet-rpi-card');
      for (const card of cards) {
        const nameEl = card.querySelector('.fleet-rpi-name');
        if (nameEl && nameEl.textContent.trim() === 'arm2-rpi') {
          const rows = card.querySelectorAll('.fleet-rpi-info-row');
          for (const row of rows) {
            const label = row.querySelector(
              '.fleet-rpi-info-label'
            );
            if (label && label.textContent.trim() === 'State:') {
              const value = row.querySelector(
                '.fleet-rpi-info-value'
              );
              return value ? value.textContent.trim() : null;
            }
          }
        }
      }
      return null;
    });
    assert(
      arm2State === 'ERROR',
      `arm2-rpi shows operational state "ERROR" (got: "${arm2State}")`
    );

    // Vehicle card should NOT show State row (not an arm)
    const vehicleHasState = await pageA.evaluate(() => {
      const cards = document.querySelectorAll('.fleet-rpi-card');
      for (const card of cards) {
        const nameEl = card.querySelector('.fleet-rpi-name');
        if (
          nameEl &&
          nameEl.textContent.trim() === 'vehicle-rpi'
        ) {
          const rows = card.querySelectorAll('.fleet-rpi-info-row');
          for (const row of rows) {
            const label = row.querySelector(
              '.fleet-rpi-info-label'
            );
            if (label && label.textContent.trim() === 'State:') {
              return true;
            }
          }
        }
      }
      return false;
    });
    assert(
      !vehicleHasState,
      'Vehicle card does NOT show operational state row'
    );

    // ----------------------------------------------------------
    // [9] Arm cards show pick count
    // ----------------------------------------------------------
    console.log('\n[9] Arm cards show pick count');

    const arm1Picks = await pageA.evaluate(() => {
      const cards = document.querySelectorAll('.fleet-rpi-card');
      for (const card of cards) {
        const nameEl = card.querySelector('.fleet-rpi-name');
        if (nameEl && nameEl.textContent.trim() === 'arm1-rpi') {
          const rows = card.querySelectorAll('.fleet-rpi-info-row');
          for (const row of rows) {
            const label = row.querySelector(
              '.fleet-rpi-info-label'
            );
            if (label && label.textContent.trim() === 'Picks:') {
              const value = row.querySelector(
                '.fleet-rpi-info-value'
              );
              return value ? value.textContent.trim() : null;
            }
          }
        }
      }
      return null;
    });
    assert(
      arm1Picks === '12',
      `arm1-rpi shows pick count 12 (got: "${arm1Picks}")`
    );

    const arm2Picks = await pageA.evaluate(() => {
      const cards = document.querySelectorAll('.fleet-rpi-card');
      for (const card of cards) {
        const nameEl = card.querySelector('.fleet-rpi-name');
        if (nameEl && nameEl.textContent.trim() === 'arm2-rpi') {
          const rows = card.querySelectorAll('.fleet-rpi-info-row');
          for (const row of rows) {
            const label = row.querySelector(
              '.fleet-rpi-info-label'
            );
            if (label && label.textContent.trim() === 'Picks:') {
              const value = row.querySelector(
                '.fleet-rpi-info-value'
              );
              return value ? value.textContent.trim() : null;
            }
          }
        }
      }
      return null;
    });
    assert(
      arm2Picks === '3',
      `arm2-rpi shows pick count 3 (got: "${arm2Picks}")`
    );

    await pageA.close();

    // ==========================================================
    // PART B — Empty fleet test
    // ==========================================================
    console.log('\n\n[B] Empty fleet test');

    // [7] When fleet is empty: shows "No fleet configured" message
    console.log('\n[7] Empty fleet shows message');

    const pageB = await browser.newPage();
    const jsErrorsB = [];
    pageB.on('pageerror', (err) => jsErrorsB.push(err.message));

    await setupEmptyFleetRoutes(pageB);

    await pageB.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await pageB.waitForTimeout(1000);

    await navigateToSection(pageB, 'fleet');
    await pageB.waitForTimeout(1000);

    const emptyMsg = await pageB.evaluate(() => {
      const el = document.querySelector('.fleet-empty');
      return el ? el.textContent.trim() : null;
    });
    assert(
      emptyMsg !== null &&
        emptyMsg.includes('No fleet configured'),
      `Empty fleet shows "No fleet configured" message (got: "${emptyMsg}")`
    );

    const noCards = await countElements(pageB, '.fleet-rpi-card');
    assert(
      noCards === 0,
      `No RPi cards rendered when fleet is empty (got ${noCards})`
    );

    await pageB.close();

    // ==========================================================
    // Error summary
    // ==========================================================
    console.log('\n[10] Error checks');
    assert(
      jsErrorsA.length === 0,
      'No JS errors during populated fleet tests' +
        (jsErrorsA.length > 0
          ? ` (got ${jsErrorsA.length}: ${jsErrorsA.slice(0, 3).join('; ')})`
          : '')
    );
    assert(
      jsErrorsB.length === 0,
      'No JS errors during empty fleet test' +
        (jsErrorsB.length > 0
          ? ` (got ${jsErrorsB.length}: ${jsErrorsB.slice(0, 3).join('; ')})`
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
