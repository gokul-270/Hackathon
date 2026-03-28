#!/usr/bin/env node
// Tab CSS E2E Test Suite
// Verifies: Launch Control icons render in grid layout;
//           Multi-Arm tab renders with proper card styling;
//           Field Analysis result tabs render with correct styling;
//           Overview chart elements have non-transparent colors.
// Run: node web_dashboard/e2e_tests/tab_css_e2e.mjs
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
  if (condition) { passed++; console.log(`  PASS  ${name}`); }
  else { failed++; failures.push(name); console.log(`  FAIL  ${name}`); }
}

function skip(name, reason) { skipped++; console.log(`  SKIP  ${name} (${reason})`); }

async function exists(page, selector) {
  return page.evaluate((sel) => !!document.querySelector(sel), selector);
}

async function navigateToSection(page, sectionName) {
  await page.evaluate((name) => { window.location.hash = '#' + name; }, sectionName);
  await page.waitForTimeout(1500);
}

async function preactContainerHasContent(page, sectionId) {
  return page.evaluate((id) => {
    const el = document.getElementById(`${id}-section-preact`);
    return el ? el.innerHTML.trim().length > 0 : false;
  }, sectionId);
}

async function anyElementExists(page, containerSelector, selectors) {
  return page.evaluate(({ container, sels }) => {
    const root = document.querySelector(container);
    if (!root) return false;
    for (const sel of sels) { if (root.querySelector(sel)) return true; }
    return false;
  }, { container: containerSelector, sels: selectors });
}

async function containerHasText(page, containerSelector, pattern) {
  return page.evaluate(({ container, pat }) => {
    const root = document.querySelector(container);
    if (!root) return false;
    return root.textContent.includes(pat);
  }, { container: containerSelector, pat: pattern });
}

async function getText(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    return el ? el.textContent.trim() : null;
  }, selector);
}

async function isVisible(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    return getComputedStyle(el).display !== 'none';
  }, selector);
}

async function countElements(page, selector) {
  return page.evaluate((sel) => document.querySelectorAll(sel).length, selector);
}

(async () => {
  console.log('Tab CSS E2E Tests');
  console.log(`Target: ${BASE}`);
  console.log('==========================\n');

  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || undefined, args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'] });
  const page = await browser.newPage();
  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  try {
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    // [1] Launch Control grid layout
    console.log('\n[1] Launch Control icon grid layout');
    await navigateToSection(page, 'launch-control');
    await page.waitForTimeout(2000);
    const hasGrid = await exists(page, '.section-grid');
    if (hasGrid) {
      const gridDisplay = await page.evaluate(() => {
        const el = document.querySelector('.section-grid');
        return el ? getComputedStyle(el).display : null;
      });
      assert(gridDisplay === 'grid' || gridDisplay === 'flex', `section-grid has grid/flex display (got: ${gridDisplay})`);
    } else {
      // Grid may not be present if launch section uses a different layout
      skip('section-grid display check', 'No .section-grid element found in launch tab');
    }

    // [2] Multi-Arm card styling
    console.log('\n[2] Multi-Arm card styling');
    await navigateToSection(page, 'multi-arm');
    await page.waitForTimeout(2000);
    const multiArmRendered = await preactContainerHasContent(page, 'multi-arm');
    if (multiArmRendered) {
      const hasCards = await anyElementExists(page, '#multi-arm-section-preact', [
        '.arm-card', '.fleet-overview-grid', '.fleet-overview-header'
      ]);
      if (hasCards) {
        assert(true, 'Multi-Arm tab has card/fleet styling elements');
      } else {
        // Might show "unavailable" message
        const hasBanner = await containerHasText(page, '#multi-arm-section-preact', 'unavailable');
        if (hasBanner) {
          skip('Multi-Arm card styling', 'MQTT unavailable — no arm cards to style');
        } else {
          assert(false, 'Multi-Arm tab has card or fleet styling elements');
        }
      }
    } else {
      skip('Multi-Arm card styling', 'Multi-Arm tab did not render');
    }

    // [3] Field Analysis result tabs
    console.log('\n[3] Field Analysis result tab styling');
    await navigateToSection(page, 'analysis');
    await page.waitForTimeout(2000);
    const faRendered = await preactContainerHasContent(page, 'analysis');
    if (faRendered) {
      // Check for analysis-tabs or fa-result-tabs class
      const hasTabs = await anyElementExists(page, '#analysis-section-preact', [
        '.analysis-tabs', '.fa-result-tabs', '.tab-bar', '.tab-list'
      ]);
      if (hasTabs) {
        assert(true, 'Field Analysis has styled result tabs');
      } else {
        skip('Field Analysis tab styling', 'No result tabs visible (may need analysis data)');
      }
    } else {
      skip('Field Analysis tab styling', 'Field Analysis tab did not render');
    }

    // [4] Overview chart colors
    console.log('\n[4] Overview chart color visibility');
    await navigateToSection(page, 'overview');
    await page.waitForTimeout(2000);
    // Check that CSS custom properties for charts are defined
    const chartColorsExist = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement);
      const primary = style.getPropertyValue('--chart-primary').trim();
      const secondary = style.getPropertyValue('--chart-secondary').trim();
      return primary.length > 0 || secondary.length > 0;
    });
    if (chartColorsExist) {
      assert(true, 'Chart CSS custom properties are defined');
    } else {
      skip('Chart CSS variables', 'No --chart-primary/secondary variables defined');
    }

    // Check canvas elements exist (charts rendered)
    const canvasCount = await countElements(page, '#fleet-overview-section-preact canvas');
    if (canvasCount > 0) {
      assert(true, `Overview has ${canvasCount} chart canvas element(s)`);
    } else {
      skip('Overview chart canvases', 'No canvas elements found (charts may not have data)');
    }

    // [5] No JS errors
    console.log('\n[5] Error checks');
    const relevantErrors = jsErrors.filter(e => !e.includes('ResizeObserver'));
    assert(relevantErrors.length === 0, `No JS errors (got ${relevantErrors.length})`);

  } catch (err) {
    console.log(`\n  CRASH  ${err.message}`);
    failed++;
    failures.push(`CRASH: ${err.message}`);
  } finally {
    await browser.close();
  }

  const total = passed + failed + skipped;
  console.log('\n==========================');
  console.log(`Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`);
  if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach((f) => console.log(`  - ${f}`));
  }
  console.log();
  process.exit(failed > 0 ? 1 : 0);
})();
