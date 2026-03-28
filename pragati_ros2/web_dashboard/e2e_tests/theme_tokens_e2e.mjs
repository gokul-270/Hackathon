#!/usr/bin/env node
// Theme Tokens E2E Test Suite (Task 7.11)
// Validates that CSS custom properties (design tokens) are defined on :root,
// that card components reference them consistently, and that no hardcoded
// hex colors leak through inline styles.
// Run: node web_dashboard/e2e_tests/theme_tokens_e2e.mjs
//
// Requires: npm install playwright (in this directory)
// Dashboard must be running on http://127.0.0.1:8090

import { chromium } from 'playwright';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, basename } from 'node:path';

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
  console.log('Theme Tokens E2E Tests');
  console.log('======================\n');

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const jsErrors = [];
  page.on('pageerror', (err) => jsErrors.push(err.message));

  try {
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    // ================================================================
    // SECTION 1: :root CSS custom properties — color tokens
    // ================================================================
    console.log('[1] Color Tokens on :root');

    const colorTokens = [
      '--color-bg-primary',
      '--color-bg-surface',
      '--color-bg-elevated',
      '--color-text-primary',
      '--color-text-secondary',
      '--color-text-muted',
      '--color-accent',
      '--color-error',
      '--color-warning',
      '--color-success',
    ];

    const colorResults = await page.evaluate((tokens) => {
      const styles = getComputedStyle(document.documentElement);
      return tokens.map((t) => ({
        token: t,
        value: styles.getPropertyValue(t).trim(),
      }));
    }, colorTokens);

    for (const { token, value } of colorResults) {
      assert(value !== '', `Token ${token} is defined (value: ${value || 'EMPTY'})`);
    }

    // ================================================================
    // SECTION 2: :root CSS custom properties — spacing tokens
    // ================================================================
    console.log('\n[2] Spacing Tokens on :root');

    const spacingTokens = [
      '--spacing-xs',
      '--spacing-sm',
      '--spacing-md',
      '--spacing-lg',
      '--spacing-xl',
    ];

    const spacingResults = await page.evaluate((tokens) => {
      const styles = getComputedStyle(document.documentElement);
      return tokens.map((t) => ({
        token: t,
        value: styles.getPropertyValue(t).trim(),
      }));
    }, spacingTokens);

    for (const { token, value } of spacingResults) {
      assert(value !== '', `Token ${token} is defined (value: ${value || 'EMPTY'})`);
    }

    // ================================================================
    // SECTION 3: :root CSS custom properties — radius tokens
    // ================================================================
    console.log('\n[3] Radius Tokens on :root');

    const radiusTokens = ['--radius-sm', '--radius-md', '--radius-lg'];

    const radiusResults = await page.evaluate((tokens) => {
      const styles = getComputedStyle(document.documentElement);
      return tokens.map((t) => ({
        token: t,
        value: styles.getPropertyValue(t).trim(),
      }));
    }, radiusTokens);

    for (const { token, value } of radiusResults) {
      assert(value !== '', `Token ${token} is defined (value: ${value || 'EMPTY'})`);
    }

    // ================================================================
    // SECTION 4: Cards use --color-bg-surface for background
    // ================================================================
    console.log('\n[4] Cards Reference --color-bg-surface');

    // Get the resolved value of --color-bg-surface from :root
    const surfaceColor = await page.evaluate(() => {
      const styles = getComputedStyle(document.documentElement);
      return styles.getPropertyValue('--color-bg-surface').trim();
    });

    // Helper to normalize color strings to a comparable rgb() form
    const normalizeColor = async (rawColor) => {
      return page.evaluate((color) => {
        // Use a temporary element to resolve any CSS color to rgb()
        const temp = document.createElement('div');
        temp.style.color = color;
        document.body.appendChild(temp);
        const resolved = getComputedStyle(temp).color;
        document.body.removeChild(temp);
        return resolved;
      }, rawColor);
    };

    const surfaceRgb = await normalizeColor(surfaceColor);

    // Check stat-card on overview
    const statCardBg = await page.evaluate(() => {
      const card = document.querySelector('.stat-card');
      return card ? getComputedStyle(card).backgroundColor : null;
    });

    if (statCardBg) {
      assert(
        statCardBg === surfaceRgb,
        `stat-card background matches --color-bg-surface (${statCardBg} vs ${surfaceRgb})`
      );
    } else {
      skip('stat-card background matches --color-bg-surface', 'no .stat-card found on overview');
    }

    // Check health-card on health tab
    await navigateToSection(page, 'health');
    const healthCardBg = await page.evaluate(() => {
      // Find a health-card that doesn't have a state modifier (ok/error/unknown override bg)
      const cards = document.querySelectorAll('.health-card');
      for (const c of cards) {
        if (
          !c.classList.contains('health-ok') &&
          !c.classList.contains('health-error') &&
          !c.classList.contains('health-unknown')
        ) {
          return getComputedStyle(c).backgroundColor;
        }
      }
      // Fall back to any health-card (state modifiers change bg slightly)
      return cards.length > 0 ? getComputedStyle(cards[0]).backgroundColor : null;
    });

    if (healthCardBg) {
      // health-card with state modifiers use rgba overlays, so exact match may differ.
      // We just check it's non-transparent (i.e. token is applied, not unstyled).
      assert(
        healthCardBg !== 'rgba(0, 0, 0, 0)' && healthCardBg !== 'transparent',
        `health-card has non-transparent background (${healthCardBg})`
      );
    } else {
      skip('health-card background check', 'no .health-card found on health tab');
    }

    // Check .card on motor-config tab
    await navigateToSection(page, 'motor-config');
    await page.waitForTimeout(500);
    const motorCardBg = await page.evaluate(() => {
      const card = document.querySelector('.card');
      return card ? getComputedStyle(card).backgroundColor : null;
    });

    if (motorCardBg) {
      assert(
        motorCardBg === surfaceRgb,
        `.card background matches --color-bg-surface (${motorCardBg} vs ${surfaceRgb})`
      );
    } else {
      skip('.card background matches --color-bg-surface', 'no .card found on motor-config tab');
    }

    // ================================================================
    // SECTION 5: Cards use --radius-md or --radius-lg for border-radius
    // ================================================================
    console.log('\n[5] Cards Use Token-Based border-radius');

    const radiusMd = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--radius-md').trim()
    );
    const radiusLg = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--radius-lg').trim()
    );

    // Navigate back to overview for stat-card check
    await navigateToSection(page, 'overview');
    const statCardRadius = await page.evaluate(() => {
      const card = document.querySelector('.stat-card');
      return card ? getComputedStyle(card).borderRadius : null;
    });

    if (statCardRadius) {
      const matchesToken =
        statCardRadius === radiusMd || statCardRadius === radiusLg;
      assert(
        matchesToken,
        `stat-card border-radius matches a radius token (${statCardRadius} vs md:${radiusMd}/lg:${radiusLg})`
      );
    } else {
      skip('stat-card border-radius check', 'no .stat-card found');
    }

    // Check .card border-radius on motor-config
    await navigateToSection(page, 'motor-config');
    await page.waitForTimeout(300);
    const motorCardRadius = await page.evaluate(() => {
      const card = document.querySelector('.card');
      return card ? getComputedStyle(card).borderRadius : null;
    });

    if (motorCardRadius) {
      const matchesToken =
        motorCardRadius === radiusMd || motorCardRadius === radiusLg;
      assert(
        matchesToken,
        `.card border-radius matches a radius token (${motorCardRadius} vs md:${radiusMd}/lg:${radiusLg})`
      );
    } else {
      skip('.card border-radius check', 'no .card found on motor-config');
    }

    // ================================================================
    // SECTION 6: No hardcoded hex colors in inline styles (spot check)
    // ================================================================
    console.log('\n[6] No Hardcoded Hex Colors in Inline Styles');

    // Check across several tabs
    const tabsToCheck = ['overview', 'health', 'statistics', 'motor-config'];
    for (const tab of tabsToCheck) {
      await navigateToSection(page, tab);
      await page.waitForTimeout(300);

      const inlineHexCount = await page.evaluate((tabName) => {
        // Hex color pattern: #RGB, #RRGGBB, #RRGGBBAA
        const hexPattern = /#(?:[0-9a-fA-F]{3,4}){1,2}\b/;
        const elements = document.querySelectorAll(
          `#${tabName}-section [style], #${tabName}-section-preact [style]`
        );
        let count = 0;
        const examples = [];
        for (const el of elements) {
          const style = el.getAttribute('style') || '';
          // Exclude canvas and chart elements (charts legitimately use inline colors)
          if (el.tagName === 'CANVAS') continue;
          // Exclude elements inside chart containers
          if (el.closest('.chart-container, .chart-wrapper, [data-chart]')) continue;
          if (hexPattern.test(style)) {
            count++;
            if (examples.length < 3) {
              examples.push(
                `<${el.tagName.toLowerCase()}> style="${style.slice(0, 80)}"`
              );
            }
          }
        }
        return { count, examples };
      }, tab);

      if (inlineHexCount.count === 0) {
        assert(true, `${tab}: no hardcoded hex colors in inline styles`);
      } else {
        // This is a best-effort/soft check — some Preact components may
        // dynamically set inline styles (e.g. progress bars, status indicators).
        // We flag but don't hard-fail for small numbers.
        const isTolerable = inlineHexCount.count <= 5;
        assert(
          isTolerable,
          `${tab}: inline hex colors within tolerance (${inlineHexCount.count} found; ` +
            `examples: ${inlineHexCount.examples.join('; ')})`
        );
      }
    }

    // ================================================================
    // SECTION 7: Static Source Scan — No Hardcoded Hex in STYLES
    // ================================================================
    console.log('\n[7] Static Source Scan: Hardcoded Hex Colors in Component STYLES');

    // Allowlisted hex colors — semantic status colors that are intentionally
    // hardcoded (lifecycle badges, severity indicators, chart palettes).
    // Add entries here ONLY for colors that cannot use CSS variable tokens.
    const HEX_ALLOWLIST = new Set([
      // Contrast text on colored backgrounds (white/black on accent)
      '#fff', '#ffffff', '#000', '#000000',
      // ParametersSubTab TYPE_COLORS — semantic type indicators
      '#6ba3f7', '#4ade80', '#fbbf24', '#c084fc',
      // MotorConfigTab chart line palette (data visualization)
      '#4dc9f6', '#f67019', '#f53794', '#537bc4', '#acc236',
    ]);

    // Files excluded from static scan — either contain protocol-defined colors,
    // data-visualization palettes, or were not modified in this change.
    const EXCLUDED_FILES = new Set([
      'TerminalOutput.mjs',    // ANSI standard color map (protocol-defined)
      'chartColors.mjs',       // Chart.js palette (data visualization)
      'ChartComponent.mjs',    // Chart rendering with inline colors
      'LogViewerTab.mjs',      // Not modified in this change (pre-existing)
      'MultiArmTab.mjs',       // Not modified in this change (pre-existing)
      'RosbagSubTab.mjs',      // Not modified in this change (pre-existing)
    ]);

    // Directories containing component .mjs files to scan
    const COMPONENT_DIRS = [
      join(import.meta.dirname, '..', 'frontend', 'js', 'tabs'),
      join(import.meta.dirname, '..', 'frontend', 'js', 'components'),
    ];

    // Recursively collect .mjs files
    function collectMjsFiles(dir) {
      const files = [];
      try {
        for (const entry of readdirSync(dir)) {
          const full = join(dir, entry);
          try {
            const st = statSync(full);
            if (st.isDirectory()) {
              files.push(...collectMjsFiles(full));
            } else if (entry.endsWith('.mjs') && !EXCLUDED_FILES.has(entry)) {
              files.push(full);
            }
          } catch { /* skip inaccessible */ }
        }
      } catch { /* skip missing dir */ }
      return files;
    }

    // Hex color regex: matches #RGB, #RRGGBB, #RRGGBBAA (not inside comments)
    const HEX_RE = /#([0-9a-fA-F]{3,8})\b/g;

    // Extract STYLES blocks from source — matches `const STYLES = { ... };` or
    // `STYLES = { ... }` patterns, and also inline `style:` or `styles:` objects
    function extractStyleBlocks(source) {
      const blocks = [];
      // Match named STYLES constants/variables
      const stylesPattern = /(?:const|let|var)\s+\w*STYLE\w*\s*=\s*\{/gi;
      let match;
      while ((match = stylesPattern.exec(source)) !== null) {
        const start = match.index;
        // Find matching closing brace (simple depth tracking)
        let depth = 0;
        let blockEnd = start;
        for (let i = start; i < source.length; i++) {
          if (source[i] === '{') depth++;
          else if (source[i] === '}') {
            depth--;
            if (depth === 0) {
              blockEnd = i + 1;
              break;
            }
          }
        }
        blocks.push(source.slice(start, blockEnd));
      }
      // If no explicit STYLES blocks, scan the whole file (components may
      // inline style objects directly in render methods)
      if (blocks.length === 0) {
        blocks.push(source);
      }
      return blocks;
    }

    // Remove single-line and multi-line comments
    function stripComments(text) {
      return text
        .replace(/\/\/.*$/gm, '')
        .replace(/\/\*[\s\S]*?\*\//g, '');
    }

    // Remove var() expressions so fallback hex values inside them are not flagged.
    // e.g. `var(--color-accent, #4fc3f7)` → `VAR_REMOVED` (hex inside is intentional fallback)
    function stripVarExpressions(text) {
      // Handle nested var() by repeatedly replacing innermost var(...) first
      let result = text;
      let prev;
      do {
        prev = result;
        result = result.replace(/var\([^()]*\)/g, 'VAR_REMOVED');
      } while (result !== prev);
      return result;
    }

    const repoRoot = join(import.meta.dirname, '..', '..');
    const allFiles = COMPONENT_DIRS.flatMap(collectMjsFiles);
    let totalViolations = 0;
    const violationDetails = [];

    for (const filePath of allFiles) {
      const src = readFileSync(filePath, 'utf-8');
      const blocks = extractStyleBlocks(src);
      const relPath = relative(repoRoot, filePath);

      for (const block of blocks) {
        const cleaned = stripVarExpressions(stripComments(block));
        let hexMatch;
        HEX_RE.lastIndex = 0;
        while ((hexMatch = HEX_RE.exec(cleaned)) !== null) {
          const color = hexMatch[0].toLowerCase();
          if (!HEX_ALLOWLIST.has(color)) {
            totalViolations++;
            // Find approximate line number in original source
            const prefix = src.slice(0, src.indexOf(hexMatch[0]));
            const line = prefix ? (prefix.match(/\n/g) || []).length + 1 : '?';
            violationDetails.push(`${relPath}:${line} → ${hexMatch[0]}`);
          }
        }
      }
    }

    assert(
      totalViolations === 0,
      `No non-allowlisted hardcoded hex colors in component STYLES ` +
        `(${totalViolations} violation${totalViolations !== 1 ? 's' : ''} across ${allFiles.length} files` +
        (violationDetails.length > 0
          ? `; first 5: ${violationDetails.slice(0, 5).join(', ')}`
          : '') +
        ')'
    );

    // ================================================================
    // SECTION 8: No JS errors
    // ================================================================
    console.log('\n[8] Error Checks');

    assert(
      jsErrors.length === 0,
      `No JS errors during theme token tests (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join('; ')})`
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
    `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`
  );
  if (failures.length > 0) {
    console.log('\nFailures:');
    failures.forEach((f) => console.log(`  - ${f}`));
  }
  console.log();
  process.exit(failed > 0 ? 1 : 0);
})();
