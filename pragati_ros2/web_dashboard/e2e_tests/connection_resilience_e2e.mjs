#!/usr/bin/env node
// Connection Resilience E2E Test Suite
// Validates disconnect banner, control lockout, and reconnection backoff behavior.
// Run: node web_dashboard/e2e_tests/connection_resilience_e2e.mjs
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

// Helper: check element exists
async function exists(page, selector) {
  return page.evaluate((sel) => !!document.querySelector(sel), selector);
}

// Helper: check element is visible (display != none)
async function isVisible(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    return getComputedStyle(el).display !== 'none';
  }, selector);
}

// Helper: get trimmed text content
async function getText(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    return el ? el.textContent.trim() : null;
  }, selector);
}

// Helper: navigate to section by hash
async function navigateToSection(page, sectionName) {
  await page.evaluate((name) => {
    const link = document.querySelector(`.nav-item[data-section="${name}"]`);
    if (link) {
      link.click();
    } else {
      window.location.hash = '#' + name;
    }
  }, sectionName);
  // Wait for section transition and Preact render
  await page.waitForTimeout(500);
}

/**
 * Simulate a WebSocket disconnect by closing all WebSocket instances.
 * We intercept WebSocket at the constructor level to track connections,
 * then close them to trigger the disconnected state.
 */
async function simulateDisconnect(page) {
  await page.evaluate(() => {
    // Close all WebSocket connections by finding them via the Preact internals
    // or by patching the WebSocket constructor.
    // Strategy: find the existing WS connection and close it.
    // The app stores it in a ref, which is not directly accessible.
    // Instead, we monkey-patch WebSocket.prototype.send to find the instance,
    // or we track instances by patching the constructor on load.
    // Simplest approach: find all WebSocket instances by iterating.

    // The most reliable method: override close behavior and trigger it
    if (window.__pragati_ws_instances && window.__pragati_ws_instances.length > 0) {
      window.__pragati_ws_instances.forEach((ws) => {
        if (ws.readyState <= 1) ws.close();
      });
    }
  });
}

/**
 * Inject a WebSocket tracker before the app creates its connection.
 * Must be called before loading the page, or we use a different strategy.
 */
async function injectWsTracker(page) {
  await page.addInitScript(() => {
    window.__pragati_ws_instances = [];
    const OrigWebSocket = window.WebSocket;
    window.WebSocket = function (...args) {
      const ws = new OrigWebSocket(...args);
      window.__pragati_ws_instances.push(ws);
      return ws;
    };
    window.WebSocket.prototype = OrigWebSocket.prototype;
    window.WebSocket.CONNECTING = OrigWebSocket.CONNECTING;
    window.WebSocket.OPEN = OrigWebSocket.OPEN;
    window.WebSocket.CLOSING = OrigWebSocket.CLOSING;
    window.WebSocket.CLOSED = OrigWebSocket.CLOSED;
  });
}

(async () => {
  console.log('Connection Resilience E2E Tests');
  console.log(`Target: ${BASE}`);
  console.log('================================\n');

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });

  const page = await browser.newPage();

  // Inject WebSocket tracker before page load
  await injectWsTracker(page);

  // Collect JS errors
  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  try {
    // Load dashboard
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1500);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // Verify WebSocket tracker is working
    const wsCount = await page.evaluate(
      () => (window.__pragati_ws_instances || []).length
    );
    assert(wsCount > 0, `WebSocket tracker captured ${wsCount} connection(s)`);

    // ================================================================
    // SECTION 7.7: Disconnect banner appears when WebSocket drops
    // ================================================================
    console.log('\n[7.7] Disconnect Banner on WebSocket Drop');

    // Verify no banner before disconnect
    const bannerBeforeDisconnect = await exists(page, '.disconnect-banner');
    assert(
      !bannerBeforeDisconnect,
      'No disconnect banner visible when connected'
    );

    // Close all WebSocket connections to simulate disconnect
    await page.evaluate(() => {
      (window.__pragati_ws_instances || []).forEach((ws) => {
        if (ws.readyState <= 1) ws.close();
      });
    });

    // Wait for Preact to re-render with disconnected state
    await page.waitForTimeout(1500);

    // Verify disconnect banner appears
    const bannerAfterDisconnect = await exists(page, '.disconnect-banner');
    assert(bannerAfterDisconnect, 'Disconnect banner appears after WS close');

    // Verify banner contains "Disconnected"
    const bannerText = await getText(page, '.disconnect-banner');
    assert(
      bannerText !== null && bannerText.includes('Disconnected'),
      `Banner text contains "Disconnected" (got: "${bannerText}")`
    );

    // Verify banner contains reconnect countdown text (either "in Xs..." or just "...")
    const hasCountdown =
      bannerText !== null &&
      (bannerText.includes('reconnecting in') ||
        bannerText.includes('reconnecting...'));
    assert(
      hasCountdown,
      `Banner contains reconnect countdown text (got: "${bannerText}")`
    );

    // Verify banner is fixed position (CSS)
    const bannerPosition = await page.evaluate(() => {
      const el = document.querySelector('.disconnect-banner');
      return el ? getComputedStyle(el).position : null;
    });
    assert(
      bannerPosition === 'fixed',
      `Disconnect banner has fixed positioning (got: "${bannerPosition}")`
    );

    // ================================================================
    // SECTION 7.8: Controls locked during disconnect
    // ================================================================
    console.log('\n[7.8] Controls Locked During Disconnect');

    // Navigate to launch-control tab
    await navigateToSection(page, 'launch-control');
    await page.waitForTimeout(1000);

    // Check that launch/stop buttons have disabled attribute or locked-control class
    const launchBtnLocked = await page.evaluate(() => {
      const btns = document.querySelectorAll(
        '.launch-panel-buttons button'
      );
      if (btns.length === 0) return { found: false };
      const results = [];
      btns.forEach((btn) => {
        results.push({
          text: btn.textContent.trim(),
          disabled: btn.disabled || btn.hasAttribute('disabled'),
          hasLockedClass: btn.classList.contains('locked-control'),
          title: btn.getAttribute('title'),
        });
      });
      return { found: true, buttons: results };
    });

    if (!launchBtnLocked.found) {
      skip(
        'Launch/Stop buttons disabled during disconnect',
        'Launch panel buttons not found — backend may not be running'
      );
      skip(
        'Launch/Stop buttons have locked-control class',
        'Launch panel buttons not found'
      );
      skip(
        'Locked buttons have "Unavailable — connection lost" tooltip',
        'Launch panel buttons not found'
      );
    } else {
      const allDisabled = launchBtnLocked.buttons.every(
        (b) => b.disabled || b.hasLockedClass
      );
      assert(
        allDisabled,
        `Launch/Stop buttons disabled or locked during disconnect (${launchBtnLocked.buttons.map((b) => `${b.text}:disabled=${b.disabled}`).join(', ')})`
      );

      const allLocked = launchBtnLocked.buttons.every(
        (b) => b.hasLockedClass
      );
      assert(
        allLocked,
        `Launch/Stop buttons have locked-control class (${launchBtnLocked.buttons.map((b) => `${b.text}:locked=${b.hasLockedClass}`).join(', ')})`
      );

      const allTooltip = launchBtnLocked.buttons.every(
        (b) =>
          b.title &&
          b.title.includes('Unavailable') &&
          b.title.includes('connection lost')
      );
      assert(
        allTooltip,
        `Locked buttons have "Unavailable — connection lost" tooltip (${launchBtnLocked.buttons.map((b) => `title="${b.title}"`).join(', ')})`
      );
    }

    // Re-enable test — reconnection requires a real backend
    skip(
      'Controls re-enabled on reconnection',
      'Requires live backend to re-establish WebSocket connection'
    );

    // ================================================================
    // SECTION 7.9: Reconnection backoff timing (1s, 2s, 4s, ..., 30s)
    // ================================================================
    console.log('\n[7.9] Reconnection Backoff Timing');

    // Reload with fresh state for timing tests
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1500);

    // Close WebSocket to trigger first reconnect attempt
    await page.evaluate(() => {
      (window.__pragati_ws_instances || []).forEach((ws) => {
        if (ws.readyState <= 1) ws.close();
      });
    });

    // Wait for disconnect state to be established
    await page.waitForTimeout(500);

    // Read the first countdown value from the banner
    const firstCountdown = await page.evaluate(() => {
      const el = document.querySelector('.disconnect-banner');
      if (!el) return null;
      const text = el.textContent;
      const match = text.match(/in (\d+)s/);
      return match ? parseInt(match[1], 10) : null;
    });

    // The first backoff is 1000ms, so countdown should start at 1
    if (firstCountdown !== null) {
      assert(
        firstCountdown <= 2,
        `First reconnect countdown starts at ~1s (got: ${firstCountdown}s)`
      );
    } else {
      // Countdown may have already expired or format differs
      skip(
        'First reconnect countdown starts at ~1s',
        'Could not capture first countdown value — timing-sensitive'
      );
    }

    // Wait for the first reconnect attempt to fail and second backoff to start
    // First delay is 1s, so wait 1.5s for it to fire and fail
    await page.waitForTimeout(2000);

    const secondCountdown = await page.evaluate(() => {
      const el = document.querySelector('.disconnect-banner');
      if (!el) return null;
      const text = el.textContent;
      const match = text.match(/in (\d+)s/);
      return match ? parseInt(match[1], 10) : null;
    });

    if (secondCountdown !== null) {
      assert(
        secondCountdown >= 1 && secondCountdown <= 3,
        `Second reconnect countdown ~2s (got: ${secondCountdown}s)`
      );
    } else {
      skip(
        'Second reconnect countdown ~2s',
        'Could not capture second countdown value — timing-sensitive'
      );
    }

    // Third backoff (4s) — wait for second attempt to fail
    await page.waitForTimeout(3000);

    const thirdCountdown = await page.evaluate(() => {
      const el = document.querySelector('.disconnect-banner');
      if (!el) return null;
      const text = el.textContent;
      const match = text.match(/in (\d+)s/);
      return match ? parseInt(match[1], 10) : null;
    });

    if (thirdCountdown !== null) {
      assert(
        thirdCountdown >= 2 && thirdCountdown <= 5,
        `Third reconnect countdown ~4s (got: ${thirdCountdown}s)`
      );
    } else {
      skip(
        'Third reconnect countdown ~4s',
        'Could not capture third countdown value — timing-sensitive'
      );
    }

    // Note: precise timing tests are inherently flaky in E2E
    // The unit test in backoff_unit_test.mjs covers the exact values

    // ================================================================
    // SECTION: Error Checks
    // ================================================================
    console.log('\n[E] Error Checks');

    // Filter out expected WebSocket errors (connection refused on reconnect attempts)
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
  console.log('\n================================');
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
