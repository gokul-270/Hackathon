#!/usr/bin/env node
// Fleet Health Auto-Refresh E2E Tests
// Tests: fleet tab auto-refresh with changing data, no JS console errors.
// Run: node web_dashboard/e2e_tests/fleet_health_e2e.mjs
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

// Helper: navigate to tab via hash change
async function navigateToSection(page, sectionName) {
  await page.evaluate((name) => {
    window.location.hash = '#' + name;
  }, sectionName);
  await page.waitForTimeout(1500);
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
// Mock data — changes between first and second call
// ---------------------------------------------------------------------------

const ROLE_RESPONSE = { role: 'dev' };

/**
 * First response: arm1-rpi online with 12 picks, arm2-rpi offline.
 */
const FLEET_STATUS_FIRST = {
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

/**
 * Second response: arm1-rpi pick count increased, arm2-rpi came online,
 * vehicle CPU jumped.
 */
const FLEET_STATUS_SECOND = {
  members: [
    {
      name: 'vehicle-rpi',
      role: 'vehicle',
      ip: '192.168.1.100',
      status: 'online',
      cpu_percent: 78.5,
      memory_percent: 65.3,
      last_seen: '2025-01-01T00:01:00Z',
      operational_state: null,
      pick_count: 0,
    },
    {
      name: 'arm1-rpi',
      role: 'arm',
      ip: '192.168.1.101',
      status: 'online',
      cpu_percent: 60.2,
      memory_percent: 44.8,
      last_seen: '2025-01-01T00:01:00Z',
      operational_state: 'PICKING',
      pick_count: 18,
    },
    {
      name: 'arm2-rpi',
      role: 'arm',
      ip: '192.168.1.102',
      status: 'online',
      cpu_percent: 32.0,
      memory_percent: 28.5,
      last_seen: '2025-01-01T00:01:00Z',
      operational_state: 'IDLE',
      pick_count: 3,
    },
  ],
};

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

(async () => {
  console.log('Fleet Health Auto-Refresh E2E Tests');
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
    // Route setup — counter-based mock that returns different
    // data on first vs subsequent calls
    // ==========================================================
    let fleetCallCount = 0;

    await page.route('**/api/config/role', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ROLE_RESPONSE),
      })
    );

    await page.route('**/api/fleet/status', (route) => {
      fleetCallCount++;
      const data =
        fleetCallCount <= 1
          ? FLEET_STATUS_FIRST
          : FLEET_STATUS_SECOND;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(data),
      });
    });

    // ==========================================================
    // [1] Fleet tab auto-refreshes with changing data
    // ==========================================================
    console.log('[1] Fleet tab auto-refresh');

    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    // Navigate to fleet tab — triggers initial load
    await navigateToSection(page, 'fleet');
    await page.waitForTimeout(1000);

    // --- Snapshot BEFORE auto-refresh ---

    // arm1-rpi pick count should be 12 initially
    const arm1PicksBefore = await page.evaluate(() => {
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
      arm1PicksBefore === '12',
      `Initial arm1-rpi pick count is 12 (got: "${arm1PicksBefore}")`
    );

    // arm2-rpi should be offline initially
    const arm2OfflineBefore = await page.evaluate(() => {
      const cards = document.querySelectorAll('.fleet-rpi-card');
      for (const card of cards) {
        const nameEl = card.querySelector('.fleet-rpi-name');
        if (nameEl && nameEl.textContent.trim() === 'arm2-rpi') {
          return !!card.querySelector('.fleet-status-offline');
        }
      }
      return false;
    });
    assert(
      arm2OfflineBefore,
      'arm2-rpi is offline before auto-refresh'
    );

    // --- Wait for auto-refresh ---
    // FleetTab polls every FLEET_POLL_INTERVAL_MS (10000ms).
    // Wait 12 seconds to ensure at least one poll fires.
    console.log(
      '    (waiting 12s for auto-refresh poll cycle...)'
    );
    await page.waitForTimeout(12000);

    // --- Snapshot AFTER auto-refresh ---

    // arm1-rpi pick count should now be 18
    const arm1PicksAfter = await page.evaluate(() => {
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
      arm1PicksAfter === '18',
      `After refresh arm1-rpi pick count is 18 (got: "${arm1PicksAfter}")`
    );

    // arm2-rpi should now be online (status changed in second response)
    const arm2OnlineAfter = await page.evaluate(() => {
      const cards = document.querySelectorAll('.fleet-rpi-card');
      for (const card of cards) {
        const nameEl = card.querySelector('.fleet-rpi-name');
        if (nameEl && nameEl.textContent.trim() === 'arm2-rpi') {
          return !!card.querySelector('.fleet-status-online');
        }
      }
      return false;
    });
    assert(
      arm2OnlineAfter,
      'arm2-rpi is online after auto-refresh'
    );

    // arm2-rpi operational state should change from ERROR to IDLE
    const arm2StateAfter = await page.evaluate(() => {
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
      arm2StateAfter === 'IDLE',
      `arm2-rpi state changed to "IDLE" after refresh (got: "${arm2StateAfter}")`
    );

    // Verify the mock was actually called more than once (auto-refresh fired)
    assert(
      fleetCallCount >= 2,
      `Fleet status endpoint called ${fleetCallCount} times (expected >= 2)`
    );

    // Fleet summary text should update (online count changed 2/3 -> 3/3)
    const summaryAfter = await getTextContent(
      page, '.fleet-summary'
    );
    assert(
      summaryAfter !== null && summaryAfter.includes('3/3'),
      `Fleet summary shows 3/3 online after refresh (got: "${summaryAfter}")`
    );

    // ==========================================================
    // [2] No JS console errors on fleet tab
    // ==========================================================
    console.log('\n[2] No JS console errors on fleet tab');

    assert(
      consoleErrors.length === 0,
      'No console.error messages during fleet tab usage' +
        (consoleErrors.length > 0
          ? ` (got ${consoleErrors.length}: ${consoleErrors.slice(0, 3).join('; ')})`
          : '')
    );

    assert(
      pageErrors.length === 0,
      'No uncaught page errors during fleet tab usage' +
        (pageErrors.length > 0
          ? ` (got ${pageErrors.length}: ${pageErrors.slice(0, 3).join('; ')})`
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
