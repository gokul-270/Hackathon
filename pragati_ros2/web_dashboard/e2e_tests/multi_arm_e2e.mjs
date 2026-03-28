#!/usr/bin/env node
// Multi-Arm Tab E2E Tests
// DEPRECATED: Tests for the legacy multi-arm fleet view (replaced by entity-centric fleet overview).
// The fleet overview now uses entity cards from /api/entities instead of fleet_health polling.
// See openspec/changes/dashboard-entity-core/ for fleet_overview_e2e.mjs.
// Tests: vehicle hub display, arm cards with live data,
//        offline detection, restart action with confirmation
// Run: node web_dashboard/e2e_tests/multi_arm_e2e.mjs
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

// Helper: click sidebar nav item by data-section
async function navigateToSection(page, sectionName) {
  await page.evaluate((name) => {
    const link = document.querySelector(
      `.nav-item[data-section="${name}"]`
    );
    if (link) link.click();
  }, sectionName);
  // Wait for section transition and Preact render
  await page.waitForTimeout(800);
}

// Helper: check if Preact container has rendered content
async function preactContainerHasContent(page, sectionId) {
  return page.evaluate((id) => {
    const el = document.getElementById(
      `${id}-section-preact`
    );
    return el ? el.innerHTML.trim().length > 0 : false;
  }, sectionId);
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

(async () => {
  console.log('Multi-Arm Tab E2E Tests');
  console.log(`Target: ${BASE}`);
  console.log('==========================\n');

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: [
      '--no-sandbox',
      '--disable-gpu',
      '--disable-dev-shm-usage',
    ],
  });

  const page = await browser.newPage();

  // Collect JS errors
  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  try {
    // ============================================================
    // [0] Load dashboard
    // ============================================================
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, {
      waitUntil: 'networkidle',
      timeout: 30000,
    });
    await page.waitForTimeout(1000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard loads with a title');

    // ============================================================
    // [1] Navigate to multi-arm tab (Task 7.6)
    // ============================================================
    console.log('\n[1] Navigate to Multi-Arm tab');
    await navigateToSection(page, 'multi-arm');

    const activeSection = await page.evaluate(() => {
      const sections = document.querySelectorAll(
        '.content-section'
      );
      for (const s of sections) {
        if (getComputedStyle(s).display !== 'none') {
          return s.id;
        }
      }
      return null;
    });
    assert(
      activeSection === 'multi-arm-section',
      'Multi-arm section is active'
    );

    // ============================================================
    // [2] Preact container rendered (Task 7.6)
    // ============================================================
    console.log('\n[2] Preact container rendered');
    const hasContent = await preactContainerHasContent(
      page, 'multi-arm'
    );
    assert(
      hasContent,
      'Preact container #multi-arm-section-preact has content'
    );

    // ============================================================
    // [3] Vehicle hub card (Task 7.6)
    // ============================================================
    console.log('\n[3] Vehicle hub card');
    const hubExists = await exists(page, '.vehicle-hub-card');
    assert(hubExists, 'Vehicle hub card is displayed');

    const mqttIndicator = await exists(
      page, '.mqtt-indicator'
    );
    assert(
      mqttIndicator,
      'MQTT broker status indicator exists'
    );

    // Broker indicator should be either connected or disconnected
    const mqttConnected = await exists(
      page, '.mqtt-connected'
    );
    const mqttDisconnected = await exists(
      page, '.mqtt-disconnected'
    );
    assert(
      mqttConnected || mqttDisconnected,
      'MQTT indicator shows connected or disconnected state'
    );

    // Hub should display "Arms Connected" text
    const hubText = await getTextContent(
      page, '.vehicle-hub-card'
    );
    assert(
      hubText && hubText.includes('Arms Connected'),
      'Vehicle hub shows arms connected count'
    );

    // ============================================================
    // [4] Connection lines SVG (Task 7.6)
    // ============================================================
    console.log('\n[4] Connection lines SVG');
    // SVG lines only render when arms are present
    const svgExists = await exists(
      page, '.connection-lines-svg'
    );
    const armCount = await countElements(page, '.arm-card');
    if (armCount > 0) {
      assert(
        svgExists,
        'Connection lines SVG rendered with arm cards'
      );
    } else {
      skip(
        'Connection lines SVG rendered',
        'no arm cards present — SVG only renders with arms'
      );
    }

    // ============================================================
    // [5] Arm cards container (Task 7.6)
    // ============================================================
    console.log('\n[5] Arm cards container');
    const armCardsContainer = await exists(
      page, '.fleet-arm-cards'
    );
    assert(
      armCardsContainer,
      'Arm cards container (.fleet-arm-cards) exists'
    );

    // Either arm cards are shown OR the empty message
    if (armCount > 0) {
      assert(true, `Found ${armCount} arm card(s)`);
    } else {
      const emptyMsg = await page.evaluate(() => {
        const container = document.querySelector(
          '.fleet-arm-cards'
        );
        if (!container) return false;
        return container.textContent.includes(
          'No arms detected'
        );
      });
      assert(
        emptyMsg,
        'No arms — shows "No arms detected" message'
      );
    }

    // ============================================================
    // [6] Arm card structure (Task 7.6)
    // ============================================================
    console.log('\n[6] Arm card structure');
    if (armCount > 0) {
      // Verify arm card internal elements
      const hasHeader = await exists(
        page, '.arm-card .arm-card-header'
      );
      assert(hasHeader, 'Arm card has header element');

      const hasArmId = await exists(
        page, '.arm-card .arm-id'
      );
      assert(hasArmId, 'Arm card shows arm ID');

      const hasStateBadge = await exists(
        page, '.arm-card .arm-state'
      );
      assert(hasStateBadge, 'Arm card has state badge');

      const hasBody = await exists(
        page, '.arm-card .arm-card-body'
      );
      assert(hasBody, 'Arm card has body with data fields');

      // Check for connectivity badge classes
      const hasConnBadge = await page.evaluate(() => {
        const cards = document.querySelectorAll('.arm-card');
        for (const card of cards) {
          if (
            card.classList.contains('arm-card-connected') ||
            card.classList.contains('arm-card-offline') ||
            card.classList.contains('arm-card-stale')
          ) return true;
        }
        return false;
      });
      assert(
        hasConnBadge,
        'Arm card has connectivity class'
      );
    } else {
      skip(
        'Arm card structure checks',
        'no arm cards present — MQTT may not be running'
      );
    }

    // ============================================================
    // [7] Restart button presence (Task 7.7)
    // ============================================================
    console.log('\n[7] Restart button (Task 7.7)');
    if (armCount > 0) {
      const restartBtnExists = await exists(
        page, '.arm-card .arm-restart-btn'
      );
      assert(
        restartBtnExists,
        'Arm cards have restart button (.arm-restart-btn)'
      );

      const restartBtnCount = await countElements(
        page, '.arm-restart-btn'
      );
      assert(
        restartBtnCount === armCount,
        `Each arm card has a restart button ` +
        `(${restartBtnCount}/${armCount})`
      );

      const btnText = await getTextContent(
        page, '.arm-restart-btn'
      );
      assert(
        btnText === 'Restart',
        `Restart button shows "Restart" text ` +
        `(got: "${btnText}")`
      );
    } else {
      skip(
        'Restart button checks',
        'no arm cards present — MQTT may not be running'
      );
    }

    // ============================================================
    // [8] Restart confirmation flow (Task 7.7)
    // ============================================================
    console.log('\n[8] Restart confirmation flow (Task 7.7)');
    if (armCount > 0) {
      // Before clicking, verify no dialog overlay
      const dialogBefore = await exists(
        page, '.modal-overlay[data-confirm-dialog]'
      );
      assert(
        !dialogBefore,
        'No confirmation dialog visible before restart click'
      );

      // Click the first arm's restart button
      await page.click('.arm-restart-btn');
      await page.waitForTimeout(500);

      // Confirm dialog should appear
      const dialogAfter = await exists(
        page, '.modal-overlay[data-confirm-dialog]'
      );
      assert(
        dialogAfter,
        'Confirmation dialog appears after restart click'
      );

      // Dialog should contain expected elements
      if (dialogAfter) {
        const dialogTitle = await getTextContent(
          page, '.modal-header'
        );
        assert(
          dialogTitle && dialogTitle.includes('Restart'),
          `Dialog title contains "Restart" ` +
          `(got: "${dialogTitle}")`
        );

        const confirmBtn = await exists(
          page, '.confirm-dialog-confirm'
        );
        assert(
          confirmBtn,
          'Dialog has confirm button'
        );

        const cancelBtn = await exists(
          page, '.confirm-dialog-cancel'
        );
        assert(
          cancelBtn,
          'Dialog has cancel button'
        );

        // Click cancel to dismiss without triggering restart
        await page.click('.confirm-dialog-cancel');
        await page.waitForTimeout(300);

        const dialogGone = !(await exists(
          page, '.modal-overlay[data-confirm-dialog]'
        ));
        assert(
          dialogGone,
          'Dialog dismissed after clicking cancel'
        );

        // Restart button should still show "Restart"
        // (not "Restarting..." since we cancelled)
        const btnTextAfterCancel = await getTextContent(
          page, '.arm-restart-btn'
        );
        assert(
          btnTextAfterCancel === 'Restart',
          'Button still shows "Restart" after cancel'
        );
      }
    } else {
      skip(
        'Restart confirmation flow',
        'no arm cards present — MQTT may not be running'
      );
    }

    // ============================================================
    // [9] Error checks
    // ============================================================
    console.log('\n[9] Error checks');
    assert(
      jsErrors.length === 0,
      'No JS errors during multi-arm tests' +
      (jsErrors.length > 0
        ? ` (got ${jsErrors.length}: ` +
          `${jsErrors.slice(0, 3).join('; ')})`
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
    failures.forEach(f => console.log(`  - ${f}`));
  }
  console.log();
  process.exit(failed > 0 ? 1 : 0);
})();
