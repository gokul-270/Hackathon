#!/usr/bin/env node
// Header E-Stop E2E Test (Task 8.3)
// Validates header E-Stop buttons: click triggers POST, confirmation dialog,
// visual feedback (button state, banner), E-Stop All concurrent execution,
// disabled state when no entities online.
// Run: node web_dashboard/e2e_tests/header_estop_e2e.mjs
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
  console.log('Header E-Stop E2E Tests (Task 8.3)');
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
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // ================================================================
    // 8.3.1: E-Stop buttons exist in header
    // ================================================================
    console.log('\n[8.3.1] E-Stop buttons exist in header');

    const entityBtn = await page.evaluate(() => {
      const btn = document.getElementById('estop-entity-btn');
      if (!btn) return null;
      return {
        exists: true,
        text: btn.textContent.trim(),
        disabled: btn.disabled,
        className: btn.className,
        inHeader: !!btn.closest('.dashboard-header'),
      };
    });

    assert(entityBtn !== null && entityBtn.exists, 'E-Stop entity button exists (#estop-entity-btn)');
    assert(entityBtn && entityBtn.inHeader, 'E-Stop entity button is inside header');
    assert(entityBtn && entityBtn.text.includes('E-STOP'), 'E-Stop entity button contains "E-STOP" text');
    assert(
      entityBtn && entityBtn.className.includes('estop-entity-btn'),
      'E-Stop entity button has estop-entity-btn class'
    );

    const allBtn = await page.evaluate(() => {
      const btn = document.getElementById('estop-all-btn');
      if (!btn) return null;
      return {
        exists: true,
        text: btn.textContent.trim(),
        disabled: btn.disabled,
        className: btn.className,
        inHeader: !!btn.closest('.dashboard-header'),
      };
    });

    assert(allBtn !== null && allBtn.exists, 'E-Stop All button exists (#estop-all-btn)');
    assert(allBtn && allBtn.inHeader, 'E-Stop All button is inside header');
    assert(allBtn && allBtn.text.includes('E-STOP ALL'), 'E-Stop All button contains "E-STOP ALL" text');
    assert(
      allBtn && allBtn.className.includes('estop-all-btn'),
      'E-Stop All button has estop-all-btn class'
    );

    // ================================================================
    // 8.3.2: E-Stop entity button disabled when no entity selected
    // ================================================================
    console.log('\n[8.3.2] E-Stop entity disabled when no entity selected');

    // Navigate to a global tab (no entity selected)
    await page.evaluate(() => { window.location.hash = '#fleet-overview'; });
    await page.waitForTimeout(500);

    const entityBtnDisabled = await page.evaluate(() => {
      const btn = document.getElementById('estop-entity-btn');
      return btn ? btn.disabled : null;
    });
    assert(
      entityBtnDisabled === true,
      'E-Stop entity button is disabled on fleet-overview (no entity selected)'
    );

    // Verify tooltip indicates no entity selected
    const entityBtnTitle = await page.evaluate(() => {
      const btn = document.getElementById('estop-entity-btn');
      return btn ? btn.title : null;
    });
    assert(
      entityBtnTitle && entityBtnTitle.toLowerCase().includes('navigate'),
      `E-Stop entity tooltip indicates no entity (got "${entityBtnTitle}")`
    );

    // ================================================================
    // 8.3.3: E-Stop entity button enabled when entity selected
    // ================================================================
    console.log('\n[8.3.3] E-Stop entity enabled when entity selected');

    // Navigate to an entity route
    await page.evaluate(() => { window.location.hash = '#/entity/test-arm/status'; });
    await page.waitForTimeout(500);

    const entityBtnAfterNav = await page.evaluate(() => {
      const btn = document.getElementById('estop-entity-btn');
      if (!btn) return null;
      return { disabled: btn.disabled, title: btn.title };
    });
    assert(
      entityBtnAfterNav && entityBtnAfterNav.disabled === false,
      'E-Stop entity button is enabled when entity selected'
    );
    assert(
      entityBtnAfterNav && entityBtnAfterNav.title.includes('test-arm'),
      `E-Stop entity tooltip mentions entity name (got "${entityBtnAfterNav?.title}")`
    );

    // ================================================================
    // 8.3.4: E-Stop entity triggers confirmation + POST
    // ================================================================
    console.log('\n[8.3.4] E-Stop entity confirmation + POST');

    // Track network requests
    const estopRequests = [];
    await page.route('**/api/entities/*/estop', async (route) => {
      estopRequests.push({
        url: route.request().url(),
        method: route.request().method(),
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    // Handle confirm dialog — accept it
    page.once('dialog', async (dialog) => {
      assert(dialog.type() === 'confirm', 'E-Stop shows confirm dialog');
      assert(
        dialog.message().includes('test-arm'),
        `Confirm dialog mentions entity "test-arm" (got "${dialog.message().substring(0, 80)}...")`
      );
      await dialog.accept();
    });

    // Click E-Stop entity button
    await page.click('#estop-entity-btn');
    await page.waitForTimeout(1000);

    assert(
      estopRequests.length > 0,
      `POST to /api/entities/test-arm/estop was made (${estopRequests.length} request(s))`
    );
    if (estopRequests.length > 0) {
      assert(
        estopRequests[0].method === 'POST',
        `E-Stop request uses POST method (got ${estopRequests[0].method})`
      );
      assert(
        estopRequests[0].url.includes('/api/entities/test-arm/estop'),
        `E-Stop URL targets correct entity (${estopRequests[0].url})`
      );
    }

    // ================================================================
    // 8.3.5: E-Stop banner appears after successful E-Stop
    // ================================================================
    console.log('\n[8.3.5] E-Stop banner appears');

    const bannerState = await page.evaluate(() => {
      const banner = document.getElementById('estop-banner');
      if (!banner) return null;
      return {
        display: getComputedStyle(banner).display,
        visible: banner.style.display !== 'none',
        text: banner.textContent.trim(),
      };
    });

    assert(bannerState !== null, 'E-Stop banner element exists');
    assert(
      bannerState && bannerState.visible,
      'E-Stop banner is visible after E-Stop'
    );
    assert(
      bannerState && bannerState.text.includes('test-arm'),
      `E-Stop banner mentions "test-arm" (got "${bannerState?.text?.substring(0, 80)}")`
    );
    assert(
      bannerState && bannerState.text.includes('Emergency Stop'),
      'E-Stop banner shows "Emergency Stop" text'
    );

    // ================================================================
    // 8.3.6: E-Stop entity — cancel confirmation does NOT send request
    // ================================================================
    console.log('\n[8.3.6] E-Stop entity cancel does not POST');

    const requestCountBefore = estopRequests.length;

    // Handle confirm dialog — reject it
    page.once('dialog', async (dialog) => {
      assert(dialog.type() === 'confirm', 'Cancel: confirm dialog shown');
      await dialog.dismiss();
    });

    await page.click('#estop-entity-btn');
    await page.waitForTimeout(500);

    assert(
      estopRequests.length === requestCountBefore,
      `No additional POST after cancelling (before: ${requestCountBefore}, after: ${estopRequests.length})`
    );

    // ================================================================
    // 8.3.7: E-Stop All — with mock entities
    // ================================================================
    console.log('\n[8.3.7] E-Stop All concurrent execution');

    // Mock /api/entities to return online entities
    await page.route('**/api/entities', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          entities: [
            { id: 'arm-1', name: 'Arm 1', status: 'online' },
            { id: 'arm-2', name: 'Arm 2', status: 'online' },
            { id: 'arm-3', name: 'Arm 3', status: 'offline' },
          ],
        }),
      });
    });

    // Reload to pick up mocked entities
    await page.reload({ waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500);

    // Re-route estop requests
    const allEstopRequests = [];
    await page.route('**/api/entities/*/estop', async (route) => {
      allEstopRequests.push({
        url: route.request().url(),
        method: route.request().method(),
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    // E-Stop All button should be enabled (2 online entities)
    const allBtnEnabled = await page.evaluate(() => {
      const btn = document.getElementById('estop-all-btn');
      return btn ? !btn.disabled : null;
    });
    assert(
      allBtnEnabled === true,
      'E-Stop All button is enabled when online entities exist'
    );

    // Handle confirm dialog for E-Stop All
    page.once('dialog', async (dialog) => {
      assert(
        dialog.message().includes('2'),
        `E-Stop All dialog mentions 2 online entities (got "${dialog.message().substring(0, 80)}...")`
      );
      await dialog.accept();
    });

    // Click E-Stop All
    await page.click('#estop-all-btn');
    await page.waitForTimeout(1500);

    // Should send POSTs to both online entities (arm-1 and arm-2, NOT arm-3)
    assert(
      allEstopRequests.length === 2,
      `E-Stop All sent 2 requests (one per online entity, got ${allEstopRequests.length})`
    );

    const estopUrls = allEstopRequests.map(r => r.url);
    assert(
      estopUrls.some(u => u.includes('arm-1')),
      'E-Stop All sent request for arm-1'
    );
    assert(
      estopUrls.some(u => u.includes('arm-2')),
      'E-Stop All sent request for arm-2'
    );
    assert(
      !estopUrls.some(u => u.includes('arm-3')),
      'E-Stop All did NOT send request for offline arm-3'
    );

    // ================================================================
    // 8.3.8: E-Stop All banner shows both entities
    // ================================================================
    console.log('\n[8.3.8] E-Stop All banner shows both entities');

    const allBannerState = await page.evaluate(() => {
      const banner = document.getElementById('estop-banner');
      if (!banner) return null;
      return {
        visible: banner.style.display !== 'none',
        text: banner.textContent.trim(),
        entityCount: document.querySelectorAll('.estop-banner-entity').length,
      };
    });

    assert(
      allBannerState && allBannerState.visible,
      'E-Stop banner visible after E-Stop All'
    );
    assert(
      allBannerState && allBannerState.text.includes('arm-1'),
      'Banner contains arm-1'
    );
    assert(
      allBannerState && allBannerState.text.includes('arm-2'),
      'Banner contains arm-2'
    );

    // ================================================================
    // 8.3.9: E-Stop All disabled when no entities online
    // ================================================================
    console.log('\n[8.3.9] E-Stop All disabled when no entities online');

    // Mock /api/entities to return only offline entities
    await page.unroute('**/api/entities');
    await page.route('**/api/entities', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          entities: [
            { id: 'arm-1', name: 'Arm 1', status: 'offline' },
            { id: 'arm-2', name: 'Arm 2', status: 'offline' },
          ],
        }),
      });
    });

    // Reload to pick up new mock
    await page.reload({ waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500);

    const allBtnDisabled = await page.evaluate(() => {
      const btn = document.getElementById('estop-all-btn');
      if (!btn) return null;
      return { disabled: btn.disabled, title: btn.title };
    });
    assert(
      allBtnDisabled && allBtnDisabled.disabled === true,
      'E-Stop All button is disabled when no entities online'
    );
    assert(
      allBtnDisabled && allBtnDisabled.title.toLowerCase().includes('no online'),
      `Disabled tooltip says "no online" (got "${allBtnDisabled?.title}")`
    );

    // ================================================================
    // Error Checks
    // ================================================================
    console.log('\n[9] Error Checks');

    // Filter out expected errors from mocked routes
    const realErrors = jsErrors.filter(e =>
      !e.includes('fetch') && !e.includes('NetworkError')
    );
    assert(
      realErrors.length === 0,
      `No unexpected JS errors (got ${realErrors.length}: ${realErrors.slice(0, 3).join('; ')})`
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
