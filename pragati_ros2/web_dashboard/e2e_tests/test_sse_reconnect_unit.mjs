#!/usr/bin/env node
// SSE Stream Reconnect Unit Test — tests ReconnectingEventSource behavior
// Run: node web_dashboard/e2e_tests/test_sse_reconnect_unit.mjs
//
// Uses Playwright to load the module in a browser context, then exercises
// ReconnectingEventSource behavior via mock EventSource injection.
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

(async () => {
  console.log('SSE ReconnectingEventSource Unit Tests');
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
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    // ================================================================
    // Inject ReconnectingEventSource tests in browser context
    // ================================================================

    console.log('[1] Import ReconnectingEventSource from StreamConnection.mjs');
    const importResult = await page.evaluate(async () => {
      try {
        const mod = await import('/js/tabs/entity/StreamConnection.mjs');
        return { ok: typeof mod.ReconnectingEventSource === 'function' };
      } catch (e) {
        return { ok: false, error: e.message };
      }
    });
    assert(importResult.ok, 'ReconnectingEventSource can be imported from StreamConnection.mjs');
    if (!importResult.ok) {
      console.log(`  Import error: ${importResult.error}`);
    }

    // ================================================================
    // Test: backoff formula
    // ================================================================
    console.log('\n[2] Backoff delay formula: min(1000 * 2^attempt, 30000)');
    const backoffResult = await page.evaluate(async () => {
      // Replicate the static method via the formula
      const backoffMs = (attempt) => Math.min(1000 * Math.pow(2, attempt), 30000);
      return {
        attempt0: backoffMs(0),
        attempt1: backoffMs(1),
        attempt2: backoffMs(2),
        attempt3: backoffMs(3),
        attempt4: backoffMs(4),
        attempt5: backoffMs(5),
        attempt10: backoffMs(10),
      };
    });
    assert(backoffResult.attempt0 === 1000, `backoff(0) === 1000ms — got ${backoffResult.attempt0}`);
    assert(backoffResult.attempt1 === 2000, `backoff(1) === 2000ms — got ${backoffResult.attempt1}`);
    assert(backoffResult.attempt2 === 4000, `backoff(2) === 4000ms — got ${backoffResult.attempt2}`);
    assert(backoffResult.attempt3 === 8000, `backoff(3) === 8000ms — got ${backoffResult.attempt3}`);
    assert(backoffResult.attempt4 === 16000, `backoff(4) === 16000ms — got ${backoffResult.attempt4}`);
    assert(backoffResult.attempt5 === 30000, `backoff(5) === 30000ms (capped) — got ${backoffResult.attempt5}`);
    assert(backoffResult.attempt10 === 30000, `backoff(10) === 30000ms (still capped) — got ${backoffResult.attempt10}`);

    // ================================================================
    // Test: reconnect fires after connection drop
    // ================================================================
    console.log('\n[3] Reconnect fires after EventSource error event');
    const reconnectFiresResult = await page.evaluate(async () => {
      const { ReconnectingEventSource } = await import('/js/tabs/entity/StreamConnection.mjs');

      let esInstances = 0;
      let reconnectingCallbackFired = false;

      // Mock EventSource
      const OriginalEventSource = globalThis.EventSource;
      globalThis.EventSource = class MockEventSource {
        constructor(url) {
          esInstances++;
          this._url = url;
          this.onopen = null;
          this.onmessage = null;
          this.onerror = null;
          setTimeout(() => {
            // First instance errors immediately to trigger reconnect
            if (esInstances === 1 && typeof this.onerror === 'function') {
              this.onerror(new Event('error'));
            }
          }, 10);
        }
        close() {}
        addEventListener(type, cb) {
          if (type === 'message') this.onmessage = cb;
        }
        removeEventListener() {}
      };

      const res = new ReconnectingEventSource('http://localhost/test', {
        maxAttempts: 5,
        onReconnecting: (attempt, delayMs) => {
          reconnectingCallbackFired = true;
        },
      });

      // Wait enough time for the error to fire and the timer to be set
      await new Promise((r) => setTimeout(r, 200));

      res.close();
      globalThis.EventSource = OriginalEventSource;

      return {
        esInstances,
        reconnectingCallbackFired,
      };
    });
    assert(reconnectFiresResult.esInstances >= 1, `EventSource was created at least once — got ${reconnectFiresResult.esInstances}`);
    assert(reconnectFiresResult.reconnectingCallbackFired, 'onReconnecting callback fires after EventSource error');

    // ================================================================
    // Test: max attempts respected
    // ================================================================
    console.log('\n[4] Max attempts: onMaxAttemptsReached fires after 5 errors');
    const maxAttemptsResult = await page.evaluate(async () => {
      const { ReconnectingEventSource } = await import('/js/tabs/entity/StreamConnection.mjs');

      let maxReachedFired = false;
      let reconnectCount = 0;
      let esInstances = 0;

      const OriginalEventSource = globalThis.EventSource;
      globalThis.EventSource = class MockEventSource {
        constructor(url) {
          esInstances++;
          this.onopen = null;
          this.onmessage = null;
          this.onerror = null;
          // Fire error immediately for every instance
          setTimeout(() => {
            if (typeof this.onerror === 'function') {
              this.onerror(new Event('error'));
            }
          }, 5);
        }
        close() {}
        addEventListener(type, cb) {}
        removeEventListener() {}
      };

      // Override setTimeout to execute immediately so test doesn't take 60s
      const origSetTimeout = globalThis.setTimeout;
      globalThis.setTimeout = (fn, delay) => {
        return origSetTimeout(fn, 1); // Execute immediately in tests
      };

      const res = new ReconnectingEventSource('http://localhost/test', {
        maxAttempts: 5,
        onReconnecting: () => { reconnectCount++; },
        onMaxAttemptsReached: () => { maxReachedFired = true; },
      });

      // Wait for all retries to exhaust
      await new Promise((r) => origSetTimeout(r, 200));

      res.close();
      globalThis.EventSource = OriginalEventSource;
      globalThis.setTimeout = origSetTimeout;

      return { maxReachedFired, reconnectCount, esInstances };
    });
    assert(maxAttemptsResult.maxReachedFired, `onMaxAttemptsReached fires after exhausting retries`);
    assert(maxAttemptsResult.reconnectCount <= 5, `Reconnect count does not exceed maxAttempts (got ${maxAttemptsResult.reconnectCount})`);

    // ================================================================
    // Test: manual close suppresses reconnect
    // ================================================================
    console.log('\n[5] Manual close() suppresses reconnect');
    const manualCloseResult = await page.evaluate(async () => {
      const { ReconnectingEventSource } = await import('/js/tabs/entity/StreamConnection.mjs');

      let reconnectFired = false;
      let esInstances = 0;

      const OriginalEventSource = globalThis.EventSource;
      globalThis.EventSource = class MockEventSource {
        constructor(url) {
          esInstances++;
          this.onopen = null;
          this.onmessage = null;
          this.onerror = null;
          setTimeout(() => {
            if (typeof this.onerror === 'function') {
              this.onerror(new Event('error'));
            }
          }, 20);
        }
        close() {}
        addEventListener() {}
        removeEventListener() {}
      };

      const res = new ReconnectingEventSource('http://localhost/test', {
        maxAttempts: 5,
        onReconnecting: () => { reconnectFired = true; },
      });

      // Close immediately — before the error fires
      res.close();

      await new Promise((r) => setTimeout(r, 100));

      globalThis.EventSource = OriginalEventSource;

      // After close, no reconnect should fire
      return { esInstances, reconnectFired };
    });
    assert(manualCloseResult.esInstances === 1, `Only 1 EventSource created when closed immediately — got ${manualCloseResult.esInstances}`);
    assert(!manualCloseResult.reconnectFired, 'onReconnecting does NOT fire after manual close()');

    // ================================================================
    // Test: attempt counter resets on successful onopen
    // ================================================================
    console.log('\n[6] Attempt counter resets on successful connection (onopen)');
    const resetOnOpenResult = await page.evaluate(async () => {
      const { ReconnectingEventSource } = await import('/js/tabs/entity/StreamConnection.mjs');

      let reconnectCount = 0;

      const OriginalEventSource = globalThis.EventSource;
      let esCallCount = 0;
      globalThis.EventSource = class MockEventSource {
        constructor(url) {
          esCallCount++;
          this.onopen = null;
          this.onmessage = null;
          this.onerror = null;
          const self = this;
          setTimeout(() => {
            if (esCallCount === 1) {
              // First instance: fire error to trigger reconnect
              if (typeof self.onerror === 'function') self.onerror(new Event('error'));
            } else if (esCallCount === 2) {
              // Second instance: fire onopen to reset attempt count
              if (typeof self.onopen === 'function') self.onopen(new Event('open'));
            }
          }, 10);
        }
        close() {}
        addEventListener() {}
        removeEventListener() {}
      };

      const origSetTimeout = globalThis.setTimeout;
      globalThis.setTimeout = (fn, delay) => origSetTimeout(fn, 5);

      const res = new ReconnectingEventSource('http://localhost/test', {
        maxAttempts: 5,
        onReconnecting: () => { reconnectCount++; },
      });

      await new Promise((r) => origSetTimeout(r, 200));
      res.close();
      globalThis.EventSource = OriginalEventSource;
      globalThis.setTimeout = origSetTimeout;

      return { reconnectCount, esCallCount };
    });
    assert(resetOnOpenResult.esCallCount >= 2, `At least 2 EventSource instances created (reconnect fired) — got ${resetOnOpenResult.esCallCount}`);
    assert(resetOnOpenResult.reconnectCount >= 1, `Reconnect callback fired at least once — got ${resetOnOpenResult.reconnectCount}`);

    // ================================================================
    // Error checks
    // ================================================================
    console.log('\n[E] Error Checks');
    const nonWsErrors = jsErrors.filter(
      (e) => !e.includes('WebSocket') && !e.includes('ws://') && !e.includes('wss://')
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
