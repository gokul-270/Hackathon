#!/usr/bin/env node
// Toast Notification E2E Test Suite
// Validates that toast notifications appear, auto-dismiss, manual dismiss,
// and support different severity types (success, error, info).
// Run: node web_dashboard/e2e_tests/toast_notification_e2e.mjs
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

// Helper: navigate to section by hash (with .nav-item fallback)
async function navigateToSection(page, sectionName) {
  await page.evaluate((name) => {
    const link = document.querySelector(`.nav-item[data-section="${name}"]`);
    if (link) {
      link.click();
    } else {
      window.location.hash = '#' + name;
    }
  }, sectionName);
  await page.waitForTimeout(500);
}

// Helper: count toast elements currently in the DOM
async function countToasts(page) {
  return page.evaluate(() =>
    document.querySelectorAll('.preact-toast').length
  );
}

// Helper: programmatically trigger a toast via the Preact app's exposed context.
// We inject into the Preact tree by calling showToast through the Settings tab's
// reset action, or directly via the ToastProvider if available. The most reliable
// way is to call window.__pragatiShowToast which we inject after finding the
// internal Preact fiber.
async function injectShowToast(page) {
  // The ToastProvider stores showToast in a Preact context.  We can reach it
  // by rendering a tiny helper component, or more practically by triggering
  // the Settings tab save action which calls showToast.  However, the cleanest
  // E2E approach is to evaluate inside the module system.  Since app.js exports
  // ToastContext and renders ToastProvider wrapping AppShell, the easiest
  // approach is to call the reset action on the Settings tab which triggers
  // showToast("Settings reset to defaults", "info").
  //
  // But for direct control we'll inject a global helper by importing the
  // module and extracting the context value.

  // Approach: dispatch a custom event that the ToastProvider listens to,
  // or simply invoke the Settings reset button which triggers a toast.
  // Let's first try the simplest route: navigate to Settings and use its
  // buttons.
  return true;
}

(async () => {
  console.log('Toast Notification E2E Tests');
  console.log(`Target: ${BASE}`);
  console.log('==========================\n');

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
    // Load dashboard
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    // ================================================================
    // SECTION 1: Toast container structure
    // ================================================================
    console.log('\n[1] Toast Container Structure');

    // Before any toasts, the container should not exist (renders null when empty)
    const containerBefore = await exists(page, '.preact-toast-container');
    assert(!containerBefore,
      'Toast container is absent when no toasts are shown');

    // ================================================================
    // SECTION 2: Trigger toast via Settings reset (info toast)
    // ================================================================
    console.log('\n[2] Trigger Info Toast via Settings Reset');

    // Navigate to Settings tab
    await navigateToSection(page, 'settings');
    await page.waitForTimeout(300);

    // Verify settings section is active
    const settingsActive = await page.evaluate(() => {
      const sections = document.querySelectorAll('.content-section');
      for (const s of sections) {
        if (getComputedStyle(s).display !== 'none') return s.id;
      }
      return null;
    });
    assert(settingsActive === 'settings-section',
      'Settings section is active');

    // Click the "Reset to Defaults" button — triggers showToast("Settings reset to defaults", "info")
    const resetBtn = await page.evaluate(() => {
      const buttons = document.querySelectorAll('#settings-section-preact button');
      for (const btn of buttons) {
        if (btn.textContent.includes('Reset')) return true;
      }
      return false;
    });

    if (resetBtn) {
      await page.evaluate(() => {
        const buttons = document.querySelectorAll('#settings-section-preact button');
        for (const btn of buttons) {
          if (btn.textContent.includes('Reset')) {
            btn.click();
            return;
          }
        }
      });
      await page.waitForTimeout(300);

      // Toast should appear
      const toastCount = await countToasts(page);
      assert(toastCount >= 1,
        `Info toast appears after Settings reset (count: ${toastCount})`);

      // Toast container should now exist
      const containerAfter = await exists(page, '.preact-toast-container');
      assert(containerAfter,
        'Toast container appears when toasts are shown');

      // Verify toast message content
      const toastText = await page.evaluate(() => {
        const toast = document.querySelector('.preact-toast');
        return toast ? toast.textContent.trim() : null;
      });
      assert(toastText && toastText.includes('Settings reset'),
        `Toast message contains "Settings reset" (got "${toastText}")`);

      // Verify it has the info severity class
      const hasInfoClass = await page.evaluate(() => {
        const toast = document.querySelector('.preact-toast-info');
        return !!toast;
      });
      assert(hasInfoClass,
        'Toast has preact-toast-info severity class');
    } else {
      skip('Info toast trigger', 'Reset button not found in Settings tab');
    }

    // Wait for auto-dismiss (info toasts have 5000ms duration)
    // Wait 6 seconds to be safe
    console.log('    (waiting for auto-dismiss: ~6s)');
    await page.waitForTimeout(6000);

    const toastsAfterAutoDismiss = await countToasts(page);
    assert(toastsAfterAutoDismiss === 0,
      `Info toast auto-dismisses after timeout (remaining: ${toastsAfterAutoDismiss})`);

    // ================================================================
    // SECTION 3: Trigger success toast via Settings save
    // ================================================================
    console.log('\n[3] Trigger Success Toast via Settings Save');

    // Mock the alerts/rules API endpoint so save succeeds
    await page.route('**/api/alerts/rules', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    // Click the "Save Settings" button — triggers showToast("Settings saved successfully", "success")
    const saveBtn = await page.evaluate(() => {
      const buttons = document.querySelectorAll('#settings-section-preact button');
      for (const btn of buttons) {
        if (btn.textContent.includes('Save')) return true;
      }
      return false;
    });

    if (saveBtn) {
      await page.evaluate(() => {
        const buttons = document.querySelectorAll('#settings-section-preact button');
        for (const btn of buttons) {
          if (btn.textContent.includes('Save')) {
            btn.click();
            return;
          }
        }
      });
      await page.waitForTimeout(500);

      const successToastExists = await page.evaluate(() => {
        return !!document.querySelector('.preact-toast-success');
      });
      assert(successToastExists,
        'Success toast appears after Settings save');

      const successText = await page.evaluate(() => {
        const toast = document.querySelector('.preact-toast-success');
        return toast ? toast.textContent.trim() : null;
      });
      assert(successText && successText.includes('saved successfully'),
        `Success toast message contains "saved successfully" (got "${successText}")`);

      // Verify success toast has green background color (#28a745 = rgb(40, 167, 69))
      const successBg = await page.evaluate(() => {
        const toast = document.querySelector('.preact-toast-success');
        return toast ? getComputedStyle(toast).backgroundColor : null;
      });
      assert(successBg === 'rgb(40, 167, 69)',
        `Success toast has green background (got "${successBg}")`);
    } else {
      skip('Success toast trigger', 'Save button not found in Settings tab');
    }

    // ================================================================
    // SECTION 4: Manual dismiss via close button
    // ================================================================
    console.log('\n[4] Manual Dismiss');

    // There should be a toast visible from the save action
    const toastsBeforeDismiss = await countToasts(page);
    if (toastsBeforeDismiss > 0) {
      // Click the close button (x) on the first toast
      await page.evaluate(() => {
        const closeBtn = document.querySelector('.preact-toast button');
        if (closeBtn) closeBtn.click();
      });
      await page.waitForTimeout(300);

      const toastsAfterDismiss = await countToasts(page);
      assert(toastsAfterDismiss < toastsBeforeDismiss,
        `Toast dismissed by clicking close button (before: ${toastsBeforeDismiss}, after: ${toastsAfterDismiss})`);
    } else {
      skip('Manual dismiss', 'No toasts visible to dismiss');
    }

    // ================================================================
    // SECTION 5: Error toast via programmatic injection
    // ================================================================
    console.log('\n[5] Error Toast (Programmatic)');

    // Inject showToast call directly via Preact internals.
    // The app.js module exports ToastContext. We can reach the provider's
    // showToast function by traversing the Preact fiber tree from #preact-root.
    const errorToastInjected = await page.evaluate(() => {
      // Walk Preact VDOM to find the ToastProvider's showToast
      // The preact-root element has __k (vnode) with the fiber tree
      const root = document.getElementById('preact-root');
      if (!root) return false;

      // Preact stores internal vnode on __k or _dom.__k
      function findShowToast(node) {
        if (!node) return null;
        // Check if this node's component state has showToast
        if (node.__c && node.__c.__v &&
            node.__c.props && node.__c.props.value &&
            typeof node.__c.props.value.showToast === 'function') {
          return node.__c.props.value.showToast;
        }
        // Recurse into children
        const children = node.__k || [];
        for (const child of children) {
          const found = findShowToast(child);
          if (found) return found;
        }
        return null;
      }

      const showToast = findShowToast(root.__k || root._children);
      if (showToast) {
        showToast('Test error message', 'error');
        return true;
      }

      // Fallback: dispatch a custom event that triggers a toast through
      // the Settings tab's save with a failing backend
      return false;
    });

    if (errorToastInjected) {
      await page.waitForTimeout(300);

      const errorToastExists = await page.evaluate(() => {
        return !!document.querySelector('.preact-toast-error');
      });
      assert(errorToastExists,
        'Error toast appears after programmatic trigger');

      // Error toast background should be red (#dc3545 = rgb(220, 53, 69))
      const errorBg = await page.evaluate(() => {
        const toast = document.querySelector('.preact-toast-error');
        return toast ? getComputedStyle(toast).backgroundColor : null;
      });
      assert(errorBg === 'rgb(220, 53, 69)',
        `Error toast has red background (got "${errorBg}")`);

      // Verify error toast message
      const errorText = await page.evaluate(() => {
        const toast = document.querySelector('.preact-toast-error');
        return toast ? toast.textContent.trim() : null;
      });
      assert(errorText && errorText.includes('Test error message'),
        `Error toast shows correct message (got "${errorText}")`);

      // Dismiss it
      await page.evaluate(() => {
        const toast = document.querySelector('.preact-toast-error');
        if (toast) {
          const btn = toast.querySelector('button');
          if (btn) btn.click();
        }
      });
      await page.waitForTimeout(300);
    } else {
      // Fallback: trigger error toast by making save fail
      console.log('    (fallback: triggering error via failed save)');

      // Remove the route mock so the real 404 endpoint is hit
      await page.unroute('**/api/alerts/rules');

      // Mock the endpoint to fail
      await page.route('**/api/alerts/rules', (route) => {
        route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'server error' }),
        });
      });

      // Click save to trigger error path
      await page.evaluate(() => {
        const buttons = document.querySelectorAll('#settings-section-preact button');
        for (const btn of buttons) {
          if (btn.textContent.includes('Save')) {
            btn.click();
            return;
          }
        }
      });
      await page.waitForTimeout(500);

      const errorExists = await page.evaluate(() => {
        return !!document.querySelector('.preact-toast-error');
      });
      assert(errorExists,
        'Error toast appears when save fails (fallback path)');
    }

    // ================================================================
    // SECTION 6: Multiple toasts stack
    // ================================================================
    console.log('\n[6] Multiple Toasts Stack');

    // Clear any existing toasts by waiting
    await page.waitForTimeout(6000);

    // Trigger multiple toasts quickly via Settings reset + save
    await page.evaluate(() => {
      const buttons = document.querySelectorAll('#settings-section-preact button');
      for (const btn of buttons) {
        if (btn.textContent.includes('Reset')) {
          btn.click();
          break;
        }
      }
    });
    await page.waitForTimeout(100);

    // Re-mock the save endpoint for success
    await page.unroute('**/api/alerts/rules');
    await page.route('**/api/alerts/rules', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    await page.evaluate(() => {
      const buttons = document.querySelectorAll('#settings-section-preact button');
      for (const btn of buttons) {
        if (btn.textContent.includes('Save')) {
          btn.click();
          break;
        }
      }
    });
    await page.waitForTimeout(500);

    const stackedCount = await countToasts(page);
    assert(stackedCount >= 2,
      `Multiple toasts can stack (count: ${stackedCount})`);

    // ================================================================
    // SECTION 7: No JS errors
    // ================================================================
    console.log('\n[7] Error Checks');

    assert(jsErrors.length === 0,
      `No JS errors during toast tests (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join('; ')})`);

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
  console.log(`Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`);
  if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach(f => console.log(`  - ${f}`));
  }
  console.log();
  process.exit(failed > 0 ? 1 : 0);
})();
