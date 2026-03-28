#!/usr/bin/env node
// E-Stop Reset E2E Test (Task 8.4)
// Validates reset button in banner calls POST /api/safety/reset,
// entity removed from banner on success, banner clears when all entities reset.
// Run: node web_dashboard/e2e_tests/estop_reset_e2e.mjs
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
  console.log('E-Stop Reset E2E Tests (Task 8.4)');
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
    console.log('\n  CRASH  Global timeout (60s) exceeded');
    failed++;
    failures.push('CRASH: Global timeout (60s) exceeded');
    await browser.close();
    printSummary();
    process.exit(1);
  }, 60000);

  try {
    console.log('[0] Loading dashboard with mock entities...');

    // Mock /api/entities to return 3 online entities
    await page.route('**/api/entities', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          entities: [
            { id: 'arm-1', name: 'Arm 1', status: 'online' },
            { id: 'arm-2', name: 'Arm 2', status: 'online' },
            { id: 'arm-3', name: 'Arm 3', status: 'online' },
          ],
        }),
      });
    });

    // Mock E-Stop endpoints
    await page.route('**/api/entities/*/estop', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    // Track reset requests
    const resetRequests = [];
    await page.route('**/api/safety/reset', async (route) => {
      const body = route.request().postData();
      resetRequests.push({
        url: route.request().url(),
        method: route.request().method(),
        body: body,
        parsedBody: body ? JSON.parse(body) : null,
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // ================================================================
    // Setup: E-Stop All entities to populate the banner
    // ================================================================
    console.log('\n[Setup] E-Stop All entities to populate banner');

    // Wait for entities to be polled and E-Stop All to be enabled
    await page.waitForTimeout(1000);

    // Handle confirm dialog
    page.once('dialog', async (dialog) => {
      await dialog.accept();
    });

    // Click E-Stop All
    const allBtnReady = await page.evaluate(() => {
      const btn = document.getElementById('estop-all-btn');
      return btn ? !btn.disabled : false;
    });

    if (!allBtnReady) {
      skip('E-Stop All not enabled (entities may not have loaded)', 'no online entities detected');
      // Try individual E-Stop via entity navigation as fallback
      console.log('  Falling back to individual E-Stops...');

      // E-Stop arm-1
      await page.evaluate(() => { window.location.hash = '#/entity/arm-1/status'; });
      await page.waitForTimeout(500);
      page.once('dialog', async (dialog) => { await dialog.accept(); });
      await page.click('#estop-entity-btn');
      await page.waitForTimeout(500);

      // E-Stop arm-2
      await page.evaluate(() => { window.location.hash = '#/entity/arm-2/status'; });
      await page.waitForTimeout(500);
      page.once('dialog', async (dialog) => { await dialog.accept(); });
      await page.click('#estop-entity-btn');
      await page.waitForTimeout(500);

      // E-Stop arm-3
      await page.evaluate(() => { window.location.hash = '#/entity/arm-3/status'; });
      await page.waitForTimeout(500);
      page.once('dialog', async (dialog) => { await dialog.accept(); });
      await page.click('#estop-entity-btn');
      await page.waitForTimeout(500);
    } else {
      await page.click('#estop-all-btn');
      await page.waitForTimeout(1000);
    }

    // ================================================================
    // 8.4.1: Banner shows all e-stopped entities with reset buttons
    // ================================================================
    console.log('\n[8.4.1] Banner shows e-stopped entities with reset buttons');

    const bannerInitial = await page.evaluate(() => {
      const banner = document.getElementById('estop-banner');
      if (!banner) return null;
      const entities = document.querySelectorAll('.estop-banner-entity');
      const resetBtns = document.querySelectorAll('.estop-reset-btn');
      return {
        visible: banner.style.display !== 'none',
        entityCount: entities.length,
        entityTexts: Array.from(entities).map(e => e.textContent.trim()),
        resetBtnCount: resetBtns.length,
        resetBtnEntityIds: Array.from(resetBtns).map(b => b.dataset.entityId),
      };
    });

    assert(
      bannerInitial && bannerInitial.visible,
      'E-Stop banner is visible after E-Stop All'
    );
    assert(
      bannerInitial && bannerInitial.entityCount >= 2,
      `Banner shows at least 2 e-stopped entities (got ${bannerInitial?.entityCount})`
    );
    assert(
      bannerInitial && bannerInitial.resetBtnCount >= 2,
      `Banner has at least 2 reset buttons (got ${bannerInitial?.resetBtnCount})`
    );

    // Each reset button has a data-entity-id
    if (bannerInitial) {
      for (const entityId of bannerInitial.resetBtnEntityIds) {
        assert(
          entityId && entityId.length > 0,
          `Reset button has data-entity-id="${entityId}"`
        );
      }
    }

    // ================================================================
    // 8.4.2: Clicking reset sends POST /api/safety/reset with entity_id
    // ================================================================
    console.log('\n[8.4.2] Reset button sends POST /api/safety/reset');

    const entitiesBefore = bannerInitial ? bannerInitial.entityCount : 0;
    const requestsBefore = resetRequests.length;

    // Click the first reset button (should be arm-1 or whichever is first)
    const firstEntityId = await page.evaluate(() => {
      const btn = document.querySelector('.estop-reset-btn');
      return btn ? btn.dataset.entityId : null;
    });

    assert(firstEntityId !== null, `Found reset button for entity: ${firstEntityId}`);

    if (firstEntityId) {
      await page.click('.estop-reset-btn');
      await page.waitForTimeout(1000);

      // Verify POST was sent
      assert(
        resetRequests.length > requestsBefore,
        `POST /api/safety/reset was sent (${resetRequests.length} total, was ${requestsBefore})`
      );

      if (resetRequests.length > requestsBefore) {
        const req = resetRequests[resetRequests.length - 1];
        assert(
          req.method === 'POST',
          `Reset request uses POST method (got ${req.method})`
        );
        assert(
          req.url.includes('/api/safety/reset'),
          `Reset URL is /api/safety/reset (got ${req.url})`
        );
        assert(
          req.parsedBody && req.parsedBody.entity_id === firstEntityId,
          `Request body contains entity_id="${firstEntityId}" (got ${JSON.stringify(req.parsedBody)})`
        );
      }

      // ================================================================
      // 8.4.3: Entity removed from banner after reset
      // ================================================================
      console.log('\n[8.4.3] Entity removed from banner after reset');

      const bannerAfterReset = await page.evaluate((removedId) => {
        const banner = document.getElementById('estop-banner');
        if (!banner) return null;
        const entities = document.querySelectorAll('.estop-banner-entity');
        const entityTexts = Array.from(entities).map(e => e.textContent.trim());
        return {
          visible: banner.style.display !== 'none',
          entityCount: entities.length,
          entityTexts,
          containsRemovedEntity: entityTexts.some(t => t.includes(removedId)),
        };
      }, firstEntityId);

      assert(
        bannerAfterReset && bannerAfterReset.entityCount < entitiesBefore,
        `Banner entity count decreased (was ${entitiesBefore}, now ${bannerAfterReset?.entityCount})`
      );
      assert(
        bannerAfterReset && !bannerAfterReset.containsRemovedEntity,
        `Entity "${firstEntityId}" no longer in banner`
      );
    }

    // ================================================================
    // 8.4.4: Reset remaining entities — banner clears completely
    // ================================================================
    console.log('\n[8.4.4] Banner clears when all entities reset');

    // Click all remaining reset buttons one by one.
    // After each click the useEffect re-renders innerHTML, so we must
    // wait for the DOM to stabilise before clicking again.
    // Note: when the last entity is reset, the banner hides (display:none)
    // and the buttons are removed from DOM. So we check for the button
    // disappearing (either removed from DOM or banner hidden).
    let remainingEntities = await page.evaluate(() => {
      return document.querySelectorAll('.estop-reset-btn').length;
    });

    let maxIterations = 10; // safety limit
    while (remainingEntities > 0 && maxIterations > 0) {
      const nextEntityId = await page.evaluate(() => {
        const btn = document.querySelector('.estop-reset-btn');
        return btn ? btn.dataset.entityId : null;
      });

      if (!nextEntityId) break;

      // Click via evaluate to bypass Playwright's visibility check —
      // the button may become invisible (banner hidden) immediately
      // after the handler runs if it's the last entity.
      await page.evaluate(() => {
        const btn = document.querySelector('.estop-reset-btn');
        if (btn) btn.click();
      });

      // Wait for entity to be removed from banner or banner to hide
      try {
        await page.waitForFunction(
          (eid) => {
            // Button gone from DOM, or banner hidden — either is success
            const banner = document.getElementById('estop-banner');
            if (banner && banner.style.display === 'none') return true;
            const btns = document.querySelectorAll('.estop-reset-btn');
            for (const b of btns) {
              if (b.dataset.entityId === eid) return false;
            }
            return true;
          },
          nextEntityId,
          { polling: 200, timeout: 5000 }
        );
      } catch (_) {
        // timeout — continue to retry
      }

      remainingEntities = await page.evaluate(() => {
        return document.querySelectorAll('.estop-reset-btn').length;
      });
      maxIterations--;
    }

    // Poll for up to 3s until all entity pills are removed from the banner.
    // This avoids flaky failures when the DOM re-render from the last reset
    // hasn't completed by the time we assert.
    let bannerFinal;
    try {
      await page.waitForFunction(
        () => document.querySelectorAll('.estop-banner-entity').length === 0,
        { polling: 200, timeout: 5000 }
      );
    } catch (_) {
      // timeout — will be caught by the assertions below
    }
    bannerFinal = await page.evaluate(() => {
      const banner = document.getElementById('estop-banner');
      if (!banner) return null;
      return {
        display: banner.style.display,
        hidden: banner.style.display === 'none',
        entityCount: document.querySelectorAll('.estop-banner-entity').length,
      };
    });

    assert(
      bannerFinal && bannerFinal.hidden,
      'E-Stop banner is hidden after all entities reset'
    );
    assert(
      bannerFinal && bannerFinal.entityCount === 0,
      `No entity pills remain in banner (got ${bannerFinal?.entityCount})`
    );

    // ================================================================
    // 8.4.5: Reset request sends correct Content-Type
    // ================================================================
    console.log('\n[8.4.5] Reset request format');

    if (resetRequests.length > 0) {
      // All reset requests should have entity_id in body
      for (let i = 0; i < resetRequests.length; i++) {
        const req = resetRequests[i];
        assert(
          req.parsedBody && typeof req.parsedBody.entity_id === 'string',
          `Reset request ${i + 1} has string entity_id in body`
        );
      }
    }

    // ================================================================
    // 8.4.6: Reset failure handling (mock 500 response)
    // ================================================================
    console.log('\n[8.4.6] Reset failure handling');

    // First, E-Stop an entity again to populate the banner
    await page.evaluate(() => { window.location.hash = '#/entity/arm-1/status'; });
    await page.waitForTimeout(500);

    page.once('dialog', async (dialog) => { await dialog.accept(); });
    await page.click('#estop-entity-btn');
    await page.waitForTimeout(1000);

    // Verify banner is back
    const bannerBackVisible = await page.evaluate(() => {
      const banner = document.getElementById('estop-banner');
      return banner ? banner.style.display !== 'none' : false;
    });
    assert(bannerBackVisible, 'Banner visible again after new E-Stop');

    // Now mock reset to fail
    await page.unroute('**/api/safety/reset');
    await page.route('**/api/safety/reset', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Reset failed' }),
      });
    });

    // Click reset — should fail gracefully
    const entityCountBeforeFail = await page.evaluate(() => {
      return document.querySelectorAll('.estop-banner-entity').length;
    });

    await page.click('.estop-reset-btn');
    await page.waitForTimeout(1000);

    // Entity should still be in banner (not removed on failure)
    const entityCountAfterFail = await page.evaluate(() => {
      return document.querySelectorAll('.estop-banner-entity').length;
    });
    assert(
      entityCountAfterFail === entityCountBeforeFail,
      `Entity stays in banner on reset failure (before: ${entityCountBeforeFail}, after: ${entityCountAfterFail})`
    );

    // Banner should still be visible
    const bannerStillVisible = await page.evaluate(() => {
      const banner = document.getElementById('estop-banner');
      return banner ? banner.style.display !== 'none' : false;
    });
    assert(bannerStillVisible, 'Banner remains visible after failed reset');

    // ================================================================
    // Error Checks
    // ================================================================
    console.log('\n[9] Error Checks');

    // Filter out expected errors from mocked failing routes
    const realErrors = jsErrors.filter(e =>
      !e.includes('fetch') && !e.includes('NetworkError') && !e.includes('500')
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
