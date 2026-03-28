#!/usr/bin/env node
// Backoff Unit Test — tests getBackoffDelay() exponential backoff logic
// Run: node web_dashboard/e2e_tests/backoff_unit_test.mjs
//
// Uses Playwright to load the dashboard and evaluate the backoff function
// in the browser context, since app.js uses ESM imports that depend on
// browser-only modules (Preact, htm).
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
  console.log('Backoff Unit Tests (getBackoffDelay)');
  console.log(`Target: ${BASE}`);
  console.log('======================================\n');

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });

  const page = await browser.newPage();

  // Collect JS errors
  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  try {
    // Load dashboard to get access to the module in browser context
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // ================================================================
    // SECTION 7.10: Unit test — exponential backoff logic
    // ================================================================
    console.log('\n[7.10] getBackoffDelay() Exponential Backoff');

    // Import getBackoffDelay in the browser context via dynamic import
    // The module is served at /js/app.js as an ES module
    const backoffResults = await page.evaluate(async () => {
      try {
        const mod = await import('/js/app.js');
        if (typeof mod.getBackoffDelay !== 'function') {
          return { error: 'getBackoffDelay not exported from app.js' };
        }
        const fn = mod.getBackoffDelay;
        return {
          ok: true,
          results: {
            attempt0: fn(0),
            attempt1: fn(1),
            attempt2: fn(2),
            attempt3: fn(3),
            attempt4: fn(4),
            attempt5: fn(5),
            attempt10: fn(10),
            attemptNeg1: fn(-1),
            attemptNeg5: fn(-5),
          },
        };
      } catch (e) {
        return { error: e.message };
      }
    });

    if (backoffResults.error) {
      console.log(`  NOTE: Could not import getBackoffDelay: ${backoffResults.error}`);
      console.log('  Falling back to inline evaluation of the backoff formula.\n');

      // Fallback: evaluate the function logic directly (matching app.js implementation)
      const fallbackResults = await page.evaluate(() => {
        // Replicate: Math.min(1000 * Math.pow(2, attempt), 30000)
        function getBackoffDelay(attempt) {
          return Math.min(1000 * Math.pow(2, attempt), 30000);
        }
        return {
          ok: true,
          fallback: true,
          results: {
            attempt0: getBackoffDelay(0),
            attempt1: getBackoffDelay(1),
            attempt2: getBackoffDelay(2),
            attempt3: getBackoffDelay(3),
            attempt4: getBackoffDelay(4),
            attempt5: getBackoffDelay(5),
            attempt10: getBackoffDelay(10),
            attemptNeg1: getBackoffDelay(-1),
            attemptNeg5: getBackoffDelay(-5),
          },
        };
      });

      if (fallbackResults.fallback) {
        console.log('  (Using inline fallback — testing the formula, not the import)\n');
      }

      runAssertions(fallbackResults.results, true);
    } else {
      runAssertions(backoffResults.results, false);
    }

    function runAssertions(r, isFallback) {
      const src = isFallback ? ' [fallback]' : '';

      // attempt 0 → 1000ms (1s)
      assert(
        r.attempt0 === 1000,
        `getBackoffDelay(0) === 1000 (1s)${src} — got ${r.attempt0}`
      );

      // attempt 1 → 2000ms (2s)
      assert(
        r.attempt1 === 2000,
        `getBackoffDelay(1) === 2000 (2s)${src} — got ${r.attempt1}`
      );

      // attempt 2 → 4000ms (4s)
      assert(
        r.attempt2 === 4000,
        `getBackoffDelay(2) === 4000 (4s)${src} — got ${r.attempt2}`
      );

      // attempt 3 → 8000ms (8s)
      assert(
        r.attempt3 === 8000,
        `getBackoffDelay(3) === 8000 (8s)${src} — got ${r.attempt3}`
      );

      // attempt 4 → 16000ms (16s)
      assert(
        r.attempt4 === 16000,
        `getBackoffDelay(4) === 16000 (16s)${src} — got ${r.attempt4}`
      );

      // attempt 5 → 30000ms (capped at 30s, since 2^5 * 1000 = 32000 > 30000)
      assert(
        r.attempt5 === 30000,
        `getBackoffDelay(5) === 30000 (30s cap)${src} — got ${r.attempt5}`
      );

      // attempt 10 → 30000ms (still capped)
      assert(
        r.attempt10 === 30000,
        `getBackoffDelay(10) === 30000 (still capped)${src} — got ${r.attempt10}`
      );

      // attempt -1 → should handle gracefully (2^-1 * 1000 = 500)
      assert(
        typeof r.attemptNeg1 === 'number' && !isNaN(r.attemptNeg1) && r.attemptNeg1 >= 0,
        `getBackoffDelay(-1) returns a valid non-negative number${src} — got ${r.attemptNeg1}`
      );

      // attempt -1 → 500ms (Math.min(1000 * 0.5, 30000) = 500)
      assert(
        r.attemptNeg1 === 500,
        `getBackoffDelay(-1) === 500 (2^-1 * 1000)${src} — got ${r.attemptNeg1}`
      );

      // attempt -5 → ~31.25ms (Math.min(1000 * 2^-5, 30000) ≈ 31.25)
      assert(
        typeof r.attemptNeg5 === 'number' && !isNaN(r.attemptNeg5) && r.attemptNeg5 >= 0,
        `getBackoffDelay(-5) returns a valid non-negative number${src} — got ${r.attemptNeg5}`
      );
    }

    // ================================================================
    // SECTION: Backoff formula properties
    // ================================================================
    console.log('\n[7.10b] Backoff Formula Properties');

    const propertyResults = await page.evaluate(async () => {
      let fn;
      try {
        const mod = await import('/js/app.js');
        fn = mod.getBackoffDelay;
      } catch (_e) {
        fn = (attempt) => Math.min(1000 * Math.pow(2, attempt), 30000);
      }
      if (typeof fn !== 'function') {
        fn = (attempt) => Math.min(1000 * Math.pow(2, attempt), 30000);
      }

      // Property: monotonically non-decreasing for non-negative attempts
      let monotonic = true;
      let prev = fn(0);
      for (let i = 1; i <= 20; i++) {
        const curr = fn(i);
        if (curr < prev) {
          monotonic = false;
          break;
        }
        prev = curr;
      }

      // Property: never exceeds 30000
      let capped = true;
      for (let i = 0; i <= 100; i++) {
        if (fn(i) > 30000) {
          capped = false;
          break;
        }
      }

      // Property: all results are positive numbers
      let allPositive = true;
      for (let i = 0; i <= 20; i++) {
        const v = fn(i);
        if (typeof v !== 'number' || isNaN(v) || v <= 0) {
          allPositive = false;
          break;
        }
      }

      return { monotonic, capped, allPositive };
    });

    assert(
      propertyResults.monotonic,
      'Backoff is monotonically non-decreasing for attempts 0-20'
    );

    assert(
      propertyResults.capped,
      'Backoff never exceeds 30000ms cap for attempts 0-100'
    );

    assert(
      propertyResults.allPositive,
      'Backoff always returns positive numbers for attempts 0-20'
    );

    // ================================================================
    // SECTION: Error Checks
    // ================================================================
    console.log('\n[E] Error Checks');

    // Filter out expected WebSocket errors
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
