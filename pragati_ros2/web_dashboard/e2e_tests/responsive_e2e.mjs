#!/usr/bin/env node
// Responsive Layout E2E Test Suite (Task 7.12)
// Validates that Motor Config sub-tabs don't overflow at 1024px viewport,
// sidebar group headers stay contained, and card grids reflow properly.
// Run: node web_dashboard/e2e_tests/responsive_e2e.mjs
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
  // Wait for section transition and Preact render
  await page.waitForTimeout(500);
}

(async () => {
  console.log('Responsive Layout E2E Tests');
  console.log('===========================\n');

  const browser = await chromium.launch({ headless: true });
  const jsErrors = [];

  try {
    // ================================================================
    // SECTION 1: Motor Config tabs at 1024x768
    // ================================================================
    console.log('[1] Motor Config Tabs — 1024x768 viewport');

    const page1024 = await browser.newPage();
    await page1024.setViewportSize({ width: 1024, height: 768 });
    page1024.on('pageerror', (err) => jsErrors.push(err.message));

    await page1024.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page1024.waitForTimeout(1000);

    // Navigate to motor-config
    await navigateToSection(page1024, 'motor-config');
    await page1024.waitForTimeout(500);

    const motorTabBarExists = await exists(page1024, '.motor-config-tabs');

    if (motorTabBarExists) {
      // Check that the tab bar does not horizontally overflow
      const tabBarOverflow = await page1024.evaluate(() => {
        const tabBar = document.querySelector('.motor-config-tabs');
        if (!tabBar) return { found: false };
        return {
          found: true,
          scrollWidth: tabBar.scrollWidth,
          clientWidth: tabBar.clientWidth,
          isOverflowing: tabBar.scrollWidth > tabBar.clientWidth + 1, // 1px tolerance
        };
      });

      assert(
        !tabBarOverflow.isOverflowing,
        `Motor config tab bar does not overflow at 1024px ` +
          `(scrollW=${tabBarOverflow.scrollWidth}, clientW=${tabBarOverflow.clientWidth})`
      );

      // Check all motor tab buttons are visible (not clipped)
      const tabButtonsVisible = await page1024.evaluate(() => {
        const tabBar = document.querySelector('.motor-config-tabs');
        if (!tabBar) return { found: false };
        const barRect = tabBar.getBoundingClientRect();
        const buttons = tabBar.querySelectorAll('.motor-tab');
        const results = [];
        for (const btn of buttons) {
          const btnRect = btn.getBoundingClientRect();
          const isVisible =
            btnRect.right <= barRect.right + 2 && // 2px tolerance
            btnRect.left >= barRect.left - 2;
          results.push({
            text: btn.textContent.trim(),
            isVisible,
            left: Math.round(btnRect.left),
            right: Math.round(btnRect.right),
          });
        }
        return {
          found: true,
          count: buttons.length,
          barRight: Math.round(barRect.right),
          buttons: results,
        };
      });

      if (tabButtonsVisible.found && tabButtonsVisible.count > 0) {
        const allVisible = tabButtonsVisible.buttons.every((b) => b.isVisible);
        assert(
          allVisible,
          `All ${tabButtonsVisible.count} motor tab buttons visible at 1024px` +
            (!allVisible
              ? ` (clipped: ${tabButtonsVisible.buttons
                  .filter((b) => !b.isVisible)
                  .map((b) => b.text)
                  .join(', ')})`
              : '')
        );
      } else {
        skip('Motor tab buttons visibility', 'no .motor-tab buttons found');
      }

      // Verify flex-wrap is applied (from the @media rule)
      const flexWrap = await page1024.evaluate(() => {
        const tabBar = document.querySelector('.motor-config-tabs');
        return tabBar ? getComputedStyle(tabBar).flexWrap : null;
      });

      assert(
        flexWrap === 'wrap',
        `Motor config tab bar has flex-wrap: wrap at 1024px (got: ${flexWrap})`
      );
    } else {
      skip('Motor config tab bar overflow', 'no .motor-config-tabs element found');
      skip('Motor tab buttons visibility', 'no .motor-config-tabs element found');
      skip('Motor config tab bar flex-wrap', 'no .motor-config-tabs element found');
    }

    // ================================================================
    // SECTION 2: Motor Config tabs at 768x1024 (tablet portrait)
    // ================================================================
    console.log('\n[2] Motor Config Tabs — 768x1024 viewport');

    await page1024.setViewportSize({ width: 768, height: 1024 });
    await page1024.waitForTimeout(500);

    // Re-navigate to force layout recalc
    await navigateToSection(page1024, 'overview');
    await page1024.waitForTimeout(200);
    await navigateToSection(page1024, 'motor-config');
    await page1024.waitForTimeout(500);

    const motorTabBar768 = await exists(page1024, '.motor-config-tabs');

    if (motorTabBar768) {
      const tabBarOverflow768 = await page1024.evaluate(() => {
        const tabBar = document.querySelector('.motor-config-tabs');
        if (!tabBar) return { found: false };
        return {
          found: true,
          scrollWidth: tabBar.scrollWidth,
          clientWidth: tabBar.clientWidth,
          isOverflowing: tabBar.scrollWidth > tabBar.clientWidth + 1,
        };
      });

      assert(
        !tabBarOverflow768.isOverflowing,
        `Motor config tab bar does not overflow at 768px ` +
          `(scrollW=${tabBarOverflow768.scrollWidth}, clientW=${tabBarOverflow768.clientWidth})`
      );
    } else {
      skip('Motor config tab bar overflow at 768px', 'no .motor-config-tabs element found');
    }

    // ================================================================
    // SECTION 3: Sidebar group headers at 1024px
    // ================================================================
    console.log('\n[3] Sidebar Group Headers — 1024x768 viewport');

    await page1024.setViewportSize({ width: 1024, height: 768 });
    await page1024.waitForTimeout(300);

    const sidebarHeadersOverflow = await page1024.evaluate(() => {
      // Check both entity group headers (.sidebar-group-header), global nav items (.sidebar-nav-item), and legacy group labels (.sidebar-group-label)
      const headers = document.querySelectorAll('.sidebar-group-header, .sidebar-nav-item, .sidebar-group-label');
      if (headers.length === 0) return { found: false };
      const results = [];
      for (const hdr of headers) {
        const hdrRect = hdr.getBoundingClientRect();
        const parent = hdr.parentElement;
        const parentRect = parent ? parent.getBoundingClientRect() : hdrRect;
        results.push({
          text: hdr.textContent.trim().slice(0, 30),
          isOverflowing: hdrRect.right > parentRect.right + 2,
          scrollOverflow: hdr.scrollWidth > hdr.clientWidth + 1,
        });
      }
      return { found: true, count: headers.length, headers: results };
    });

    if (sidebarHeadersOverflow.found) {
      const anyOverflow = sidebarHeadersOverflow.headers.some(
        (h) => h.isOverflowing || h.scrollOverflow
      );
      assert(
        !anyOverflow,
        `Sidebar group headers don't overflow at 1024px ` +
          `(${sidebarHeadersOverflow.count} headers checked` +
          (anyOverflow
            ? `; overflowing: ${sidebarHeadersOverflow.headers
                .filter((h) => h.isOverflowing || h.scrollOverflow)
                .map((h) => h.text)
                .join(', ')}`
            : '') +
          ')'
      );
    } else {
      skip('Sidebar group headers overflow', 'no .sidebar-group-header, .sidebar-nav-item, or .sidebar-group-label elements found');
    }

    // Verify overflow: hidden is set on sidebar-group-header (entity groups)
    const sidebarHeaderOverflowCSS = await page1024.evaluate(() => {
      const hdr = document.querySelector('.sidebar-group-header');
      return hdr ? getComputedStyle(hdr).overflow : null;
    });

    if (sidebarHeaderOverflowCSS !== null) {
      assert(
        sidebarHeaderOverflowCSS === 'hidden',
        `Sidebar group header has overflow: hidden (got: ${sidebarHeaderOverflowCSS})`
      );
    } else {
      skip('Sidebar group header overflow CSS', 'no .sidebar-group-header found (entity groups may not be present)');
    }

    // ================================================================
    // SECTION 4: Card grids at 1024px
    // ================================================================
    console.log('\n[4] Card Grid Layout — 1024x768 viewport');

    // Check stats-grid on overview
    await navigateToSection(page1024, 'overview');
    await page1024.waitForTimeout(300);

    const statsGridLayout = await page1024.evaluate(() => {
      const grid = document.querySelector('.stats-grid');
      if (!grid) return { found: false };
      const style = getComputedStyle(grid);
      const cols = style.gridTemplateColumns;
      // Count the number of column tracks
      const colCount = cols ? cols.split(/\s+/).filter((c) => c && c !== 'none').length : 0;
      return { found: true, columns: cols, colCount };
    });

    if (statsGridLayout.found) {
      assert(
        statsGridLayout.colCount >= 2,
        `Stats grid has >= 2 columns at 1024px (got ${statsGridLayout.colCount}: ${statsGridLayout.columns})`
      );
    } else {
      skip('Stats grid column check', 'no .stats-grid found on overview');
    }

    // Check health-grid
    await navigateToSection(page1024, 'health');
    await page1024.waitForTimeout(300);

    const healthGridLayout = await page1024.evaluate(() => {
      const grid = document.querySelector('.health-grid');
      if (!grid) return { found: false };
      const style = getComputedStyle(grid);
      const cols = style.gridTemplateColumns;
      const colCount = cols ? cols.split(/\s+/).filter((c) => c && c !== 'none').length : 0;
      return { found: true, columns: cols, colCount };
    });

    if (healthGridLayout.found) {
      assert(
        healthGridLayout.colCount >= 2,
        `Health grid has >= 2 columns at 1024px (got ${healthGridLayout.colCount})`
      );
    } else {
      skip('Health grid column check', 'no .health-grid found on health tab');
    }

    // ================================================================
    // SECTION 5: Sub-tab bar (used by Statistics, Launch Control) at 1024px
    // ================================================================
    console.log('\n[5] Sub-tab Bars — 1024x768 viewport');

    await navigateToSection(page1024, 'statistics');
    await page1024.waitForTimeout(500);

    const subTabBarOverflow = await page1024.evaluate(() => {
      const bars = document.querySelectorAll('.sub-tab-bar');
      if (bars.length === 0) return { found: false };
      const results = [];
      for (const bar of bars) {
        results.push({
          scrollWidth: bar.scrollWidth,
          clientWidth: bar.clientWidth,
          isOverflowing: bar.scrollWidth > bar.clientWidth + 1,
          flexWrap: getComputedStyle(bar).flexWrap,
        });
      }
      return { found: true, count: bars.length, bars: results };
    });

    if (subTabBarOverflow.found) {
      const anyOverflow = subTabBarOverflow.bars.some((b) => b.isOverflowing);
      assert(
        !anyOverflow,
        `Sub-tab bars don't overflow at 1024px (${subTabBarOverflow.count} bars checked)`
      );

      // Check flex-wrap is applied
      const allWrapped = subTabBarOverflow.bars.every((b) => b.flexWrap === 'wrap');
      assert(
        allWrapped,
        `Sub-tab bars have flex-wrap: wrap at 1024px`
      );
    } else {
      skip('Sub-tab bar overflow', 'no .sub-tab-bar elements found on statistics');
      skip('Sub-tab bar flex-wrap', 'no .sub-tab-bar elements found on statistics');
    }

    // ================================================================
    // SECTION 6: No JS errors
    // ================================================================
    console.log('\n[6] Error Checks');

    assert(
      jsErrors.length === 0,
      `No JS errors during responsive tests (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join('; ')})`
    );

    await page1024.close();
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
    `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`
  );
  if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach((f) => console.log(`  - ${f}`));
  }
  console.log();
  process.exit(failed > 0 ? 1 : 0);
})();
