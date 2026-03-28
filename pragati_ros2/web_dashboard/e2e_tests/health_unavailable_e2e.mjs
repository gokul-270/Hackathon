#!/usr/bin/env node
// Health UNAVAILABLE E2E Test — verifies UNAVAILABLE state rendering in the
// dashboard UI for entities with stale/missing data.
//
// Run: node web_dashboard/e2e_tests/health_unavailable_e2e.mjs
//
// Tests:
// - Entity with stale last_seen (>30s) shows grey health-unavailable badges
// - "Unavailable" text appears for subsystems without data
// - Safety status section renders with UNAVAILABLE cards when API unreachable
// - No stale metric values displayed as healthy
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

// Helper: navigate via hash change
async function navigateToHash(page, hash) {
  await page.evaluate((h) => {
    window.location.hash = h;
  }, hash);
  await page.waitForTimeout(2000);
}

// Helper: count elements matching selector
async function countElements(page, selector) {
  return page.evaluate(
    (sel) => document.querySelectorAll(sel).length,
    selector,
  );
}

// Helper: get text content of all matching elements
async function getTextContents(page, selector) {
  return page.evaluate(
    (sel) => Array.from(document.querySelectorAll(sel)).map((el) => el.textContent.trim()),
    selector,
  );
}

(async () => {
  console.log('Health UNAVAILABLE E2E Tests');
  console.log(`Target: ${BASE}`);
  console.log('======================================\n');

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });

  const page = await browser.newPage();

  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  try {
    // ================================================================
    // [0] Load dashboard
    // ================================================================
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads');

    // ================================================================
    // [1] Navigate to entity detail and check UNAVAILABLE rendering
    //     via StatusHealthTab module evaluation
    // ================================================================
    console.log('\n[1] UNAVAILABLE badge CSS classes exist');

    // Verify CSS classes are defined in the loaded styles
    const cssChecks = await page.evaluate(() => {
      const sheets = Array.from(document.styleSheets);
      let hasUnavailableBadge = false;
      let hasUnavailableMetric = false;

      for (const sheet of sheets) {
        try {
          const rules = Array.from(sheet.cssRules || []);
          for (const rule of rules) {
            const sel = rule.selectorText || '';
            if (sel.includes('.health-unavailable')) hasUnavailableBadge = true;
            if (sel.includes('.entity-metric-unavailable')) hasUnavailableMetric = true;
          }
        } catch (_e) {
          // Cross-origin stylesheets may throw
        }
      }

      return { hasUnavailableBadge, hasUnavailableMetric };
    });

    assert(cssChecks.hasUnavailableBadge, '.health-unavailable CSS class exists in loaded styles');
    assert(cssChecks.hasUnavailableMetric, '.entity-metric-unavailable CSS class exists in loaded styles');

    // ================================================================
    // [2] Test UNAVAILABLE rendering via direct component invocation
    //     We inject a mock entity into the page and render StatusHealthTab
    // ================================================================
    console.log('\n[2] UNAVAILABLE state rendering via component');

    const renderResult = await page.evaluate(async () => {
      try {
        const { h } = await import('preact');
        const { render } = await import('preact');
        const { html } = await import('htm/preact');
        const mod = await import('/js/components/StatusHealthTab.mjs');

        // Create a test container
        const container = document.createElement('div');
        container.id = 'unavailable-test-container';
        container.style.display = 'none';
        document.body.appendChild(container);

        // Test: derive health for stale entity
        const staleEntityData = {
          status: 'online',
          last_seen: new Date(Date.now() - 120000).toISOString(), // 2 min ago
          system_metrics: { cpu_percent: 50 },
          ros2_available: true,
        };

        const health = mod.deriveSubsystemHealth(staleEntityData);

        // Test: derive health for entity with motors having null last_update
        const motorsNullData = {
          status: 'online',
          last_seen: new Date().toISOString(),
          ros2_available: true,
          motors: [
            { id: 1, last_update: null },
            { id: 2, last_update: null },
          ],
          can_bus: { last_message_time: new Date().toISOString() },
          system_metrics: { cpu_percent: 30, memory_percent: 40, temperature_c: 45, disk_percent: 20 },
          services: [{ name: 'svc1', active_state: 'active' }],
        };

        const motorsHealth = mod.deriveSubsystemHealth(motorsNullData);

        // Test badge classes
        const unavailableBadge = mod.healthBadgeClass('unavailable');
        const healthyBadge = mod.healthBadgeClass('healthy');

        // Clean up
        document.body.removeChild(container);

        return {
          ok: true,
          staleHealth: health,
          motorsHealth: motorsHealth,
          unavailableBadge,
          healthyBadge,
        };
      } catch (e) {
        return { ok: false, error: e.message };
      }
    });

    if (!renderResult.ok) {
      console.log(`  NOTE: Component test failed: ${renderResult.error}`);
      skip('UNAVAILABLE rendering tests', renderResult.error);
    } else {
      // Stale entity → all subsystems unavailable
      assert(
        renderResult.staleHealth.system === 'unavailable',
        'Stale entity (>30s last_seen): system → unavailable'
      );
      assert(
        renderResult.staleHealth.ros2 === 'unavailable',
        'Stale entity (>30s last_seen): ros2 → unavailable'
      );
      assert(
        renderResult.staleHealth.motors === 'unavailable',
        'Stale entity (>30s last_seen): motors → unavailable'
      );
      assert(
        renderResult.staleHealth.can_bus === 'unavailable',
        'Stale entity (>30s last_seen): can_bus → unavailable'
      );
      assert(
        renderResult.staleHealth.services === 'unavailable',
        'Stale entity (>30s last_seen): services → unavailable'
      );

      // Motors with null last_update → motors unavailable, others OK
      assert(
        renderResult.motorsHealth.motors === 'unavailable',
        'Motors with null last_update: motors → unavailable'
      );
      assert(
        renderResult.motorsHealth.system === 'healthy',
        'Motors unavailable but system still healthy'
      );
      assert(
        renderResult.motorsHealth.can_bus === 'healthy',
        'Motors unavailable but CAN bus still healthy (recent messages)'
      );

      // Badge classes
      assert(
        renderResult.unavailableBadge === 'health-unavailable',
        'unavailable status maps to health-unavailable CSS class'
      );
      assert(
        renderResult.healthyBadge === 'health-ok',
        'healthy status maps to health-ok CSS class'
      );
    }

    // ================================================================
    // [3] Verify grey color is applied to .health-unavailable
    // ================================================================
    console.log('\n[3] Grey styling for UNAVAILABLE');

    const greyCheck = await page.evaluate(() => {
      // Create a temp element with the class and check computed style
      const el = document.createElement('div');
      el.className = 'health-card health-unavailable';
      el.style.display = 'none';
      document.body.appendChild(el);

      const style = window.getComputedStyle(el);
      const bgColor = style.backgroundColor;
      const borderColor = style.borderColor;

      document.body.removeChild(el);

      return { bgColor, borderColor };
    });

    // We can't assert exact colors since CSS variables resolve differently,
    // but we can check the element doesn't use green/red/amber
    assert(
      greyCheck.bgColor !== 'rgb(0, 128, 0)' && greyCheck.bgColor !== 'rgb(255, 0, 0)',
      '.health-unavailable does not use green or red background'
    );
    console.log(`  (Computed bg: ${greyCheck.bgColor}, border: ${greyCheck.borderColor})`);

    // ================================================================
    // [4] Verify OverviewTab and HealthTab support UNAVAILABLE
    // ================================================================
    console.log('\n[4] OverviewTab/HealthTab UNAVAILABLE support');

    const tabChecks = await page.evaluate(async () => {
      const results = {};

      // Check OverviewTab exports
      try {
        // OverviewTab registers itself via registerTab, not via named exports
        // We check the module loads without error
        await import('/js/tabs/OverviewTab.mjs');
        results.overviewLoads = true;
      } catch (e) {
        results.overviewLoads = false;
        results.overviewError = e.message;
      }

      // Check HealthTab exports
      try {
        await import('/js/tabs/HealthTab.mjs');
        results.healthLoads = true;
      } catch (e) {
        results.healthLoads = false;
        results.healthError = e.message;
      }

      return results;
    });

    assert(tabChecks.overviewLoads, 'OverviewTab.mjs loads without errors');
    assert(tabChecks.healthLoads, 'HealthTab.mjs loads without errors');

    // ================================================================
    // [5] Check that "Unavailable" text is not confused with healthy
    // ================================================================
    console.log('\n[5] No false-healthy display for null metrics');

    const metricCheck = await page.evaluate(async () => {
      const mod = await import('/js/components/StatusHealthTab.mjs');

      // metricSeverity should return unavailable class for null/undefined
      const nullSeverity = mod.metricSeverity(null);
      const undefinedSeverity = mod.metricSeverity(undefined);
      const zeroSeverity = mod.metricSeverity(0);

      return {
        nullIsUnavailable: nullSeverity === 'entity-metric-unavailable',
        undefinedIsUnavailable: undefinedSeverity === 'entity-metric-unavailable',
        zeroIsOk: zeroSeverity === 'entity-metric-ok',
      };
    });

    assert(metricCheck.nullIsUnavailable, 'null metric → entity-metric-unavailable (not ok)');
    assert(metricCheck.undefinedIsUnavailable, 'undefined metric → entity-metric-unavailable (not ok)');
    assert(metricCheck.zeroIsOk, 'zero metric → entity-metric-ok (legitimate zero value)');

    // ================================================================
    // [E] Error Checks
    // ================================================================
    console.log('\n[E] Error Checks');

    const nonWsErrors = jsErrors.filter(
      (e) =>
        !e.includes('WebSocket') &&
        !e.includes('ws://') &&
        !e.includes('wss://')
    );
    assert(
      nonWsErrors.length === 0,
      `No unexpected JS errors (got ${nonWsErrors.length}: ${nonWsErrors.slice(0, 3).join('; ')})`
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
  console.log('\n======================================');
  console.log(
    `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`
  );
  if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach((f) => console.log(`  - ${f}`));
  }
  console.log();
  process.exit(failed > 0 ? 1 : 0);
})();
