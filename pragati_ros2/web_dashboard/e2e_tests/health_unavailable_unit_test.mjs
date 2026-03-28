#!/usr/bin/env node
// Health UNAVAILABLE Unit Tests — tests deriveSubsystemHealth(), metricSeverity(),
// healthBadgeClass(), and isTimestampStale() from StatusHealthTab.mjs
//
// Run: node web_dashboard/e2e_tests/health_unavailable_unit_test.mjs
//
// Uses Playwright to load the dashboard and evaluate exported functions
// in the browser context (ESM modules depend on browser-only Preact).
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
  console.log('Health UNAVAILABLE Unit Tests');
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
    console.log('[0] Loading dashboard...');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000);

    const title = await page.title();
    assert(title.length > 0, 'Dashboard page loads with a title');

    // ================================================================
    // Try to import StatusHealthTab module functions
    // ================================================================
    console.log('\n[1] Importing StatusHealthTab module...');

    const importResult = await page.evaluate(async () => {
      try {
        const mod = await import('/js/components/StatusHealthTab.mjs');
        const exports = Object.keys(mod);
        return { ok: true, exports };
      } catch (e) {
        return { ok: false, error: e.message };
      }
    });

    if (!importResult.ok) {
      console.log(`  FAIL  Could not import StatusHealthTab: ${importResult.error}`);
      failed++;
      failures.push('Module import failed');
      return;
    }

    assert(importResult.ok, 'StatusHealthTab module imports successfully');
    console.log(`  Exports: ${importResult.exports.join(', ')}`);

    // ================================================================
    // SECTION: healthBadgeClass()
    // ================================================================
    console.log('\n[2] healthBadgeClass()');

    const badgeResults = await page.evaluate(async () => {
      const mod = await import('/js/components/StatusHealthTab.mjs');
      const fn = mod.healthBadgeClass;
      return {
        healthy: fn('healthy'),
        degraded: fn('degraded'),
        error: fn('error'),
        unavailable: fn('unavailable'),
        UNAVAILABLE: fn('UNAVAILABLE'),
        null_input: fn(null),
        undefined_input: fn(undefined),
        empty_string: fn(''),
        unknown_value: fn('foobar'),
      };
    });

    assert(badgeResults.healthy === 'health-ok', 'healthBadgeClass("healthy") === "health-ok"');
    assert(badgeResults.degraded === 'health-unknown', 'healthBadgeClass("degraded") === "health-unknown"');
    assert(badgeResults.error === 'health-error', 'healthBadgeClass("error") === "health-error"');
    assert(badgeResults.unavailable === 'health-unavailable', 'healthBadgeClass("unavailable") === "health-unavailable"');
    assert(badgeResults.UNAVAILABLE === 'health-unavailable', 'healthBadgeClass("UNAVAILABLE") === "health-unavailable" (case insensitive)');
    assert(badgeResults.null_input === 'health-unavailable', 'healthBadgeClass(null) === "health-unavailable" (fallback)');
    assert(badgeResults.undefined_input === 'health-unavailable', 'healthBadgeClass(undefined) === "health-unavailable" (fallback)');
    assert(badgeResults.empty_string === 'health-unavailable', 'healthBadgeClass("") === "health-unavailable" (fallback)');
    assert(badgeResults.unknown_value === 'health-unavailable', 'healthBadgeClass("foobar") === "health-unavailable" (fallback)');

    // ================================================================
    // SECTION: metricSeverity()
    // ================================================================
    console.log('\n[3] metricSeverity()');

    const severityResults = await page.evaluate(async () => {
      const mod = await import('/js/components/StatusHealthTab.mjs');
      const fn = mod.metricSeverity;
      return {
        null_input: fn(null),
        undefined_input: fn(undefined),
        nan_input: fn(NaN),
        zero: fn(0),
        fifty: fn(50),
        seventy: fn(70),
        seventy_one: fn(71),
        ninety: fn(90),
        ninety_one: fn(91),
        hundred: fn(100),
      };
    });

    assert(severityResults.null_input === 'entity-metric-unavailable', 'metricSeverity(null) === "entity-metric-unavailable"');
    assert(severityResults.undefined_input === 'entity-metric-unavailable', 'metricSeverity(undefined) === "entity-metric-unavailable"');
    assert(severityResults.nan_input === 'entity-metric-unavailable', 'metricSeverity(NaN) === "entity-metric-unavailable"');
    assert(severityResults.zero === 'entity-metric-ok', 'metricSeverity(0) === "entity-metric-ok"');
    assert(severityResults.fifty === 'entity-metric-ok', 'metricSeverity(50) === "entity-metric-ok"');
    assert(severityResults.seventy === 'entity-metric-ok', 'metricSeverity(70) === "entity-metric-ok"');
    assert(severityResults.seventy_one === 'entity-metric-warning', 'metricSeverity(71) === "entity-metric-warning"');
    assert(severityResults.ninety === 'entity-metric-warning', 'metricSeverity(90) === "entity-metric-warning"');
    assert(severityResults.ninety_one === 'entity-metric-critical', 'metricSeverity(91) === "entity-metric-critical"');
    assert(severityResults.hundred === 'entity-metric-critical', 'metricSeverity(100) === "entity-metric-critical"');

    // ================================================================
    // SECTION: isTimestampStale()
    // ================================================================
    console.log('\n[4] isTimestampStale()');

    const staleResults = await page.evaluate(async () => {
      const mod = await import('/js/components/StatusHealthTab.mjs');
      const fn = mod.isTimestampStale;
      const now = Date.now();
      return {
        null_input: fn(null, 30),
        undefined_input: fn(undefined, 30),
        empty_string: fn('', 30),
        invalid_string: fn('not-a-date', 30),
        recent_iso: fn(new Date(now - 5000).toISOString(), 30),
        old_iso: fn(new Date(now - 60000).toISOString(), 30),
        recent_epoch_ms: fn(now - 5000, 30),
        old_epoch_ms: fn(now - 60000, 30),
        recent_epoch_s: fn(Math.floor((now - 5000) / 1000), 30),
        old_epoch_s: fn(Math.floor((now - 60000) / 1000), 30),
        zero_threshold: fn(new Date(now - 1000).toISOString(), 0),
      };
    });

    assert(staleResults.null_input === true, 'isTimestampStale(null, 30) === true');
    assert(staleResults.undefined_input === true, 'isTimestampStale(undefined, 30) === true');
    assert(staleResults.empty_string === true, 'isTimestampStale("", 30) === true (invalid date)');
    assert(staleResults.invalid_string === true, 'isTimestampStale("not-a-date", 30) === true');
    assert(staleResults.recent_iso === false, 'isTimestampStale(5s ago ISO, 30) === false');
    assert(staleResults.old_iso === true, 'isTimestampStale(60s ago ISO, 30) === true');
    assert(staleResults.recent_epoch_ms === false, 'isTimestampStale(5s ago epoch ms, 30) === false');
    assert(staleResults.old_epoch_ms === true, 'isTimestampStale(60s ago epoch ms, 30) === true');
    assert(staleResults.recent_epoch_s === false, 'isTimestampStale(5s ago epoch s, 30) === false');
    assert(staleResults.old_epoch_s === true, 'isTimestampStale(60s ago epoch s, 30) === true');
    assert(staleResults.zero_threshold === true, 'isTimestampStale(1s ago, threshold=0) === true');

    // ================================================================
    // SECTION: deriveSubsystemHealth()
    // ================================================================
    console.log('\n[5] deriveSubsystemHealth()');

    const deriveResults = await page.evaluate(async () => {
      const mod = await import('/js/components/StatusHealthTab.mjs');
      const fn = mod.deriveSubsystemHealth;
      const now = Date.now();
      const recentIso = new Date(now - 2000).toISOString();
      const staleIso = new Date(now - 60000).toISOString();

      // --- Test: null entityData ---
      const nullEntity = fn(null);

      // --- Test: entity offline ---
      const offlineEntity = fn({
        status: 'offline',
        last_seen: recentIso,
      });

      // --- Test: entity stale (last_seen > 30s) ---
      const staleEntity = fn({
        status: 'online',
        last_seen: staleIso,
      });

      // --- Test: motors all have null last_update ---
      const motorsUnavailable = fn({
        status: 'online',
        last_seen: recentIso,
        ros2_available: true,
        motors: [
          { id: 1, last_update: null },
          { id: 2, last_update: null },
        ],
        can_bus: { last_message_time: recentIso },
        system_metrics: { cpu_percent: 30, memory_percent: 40, temperature_c: 45, disk_percent: 20 },
        services: [],
      });

      // --- Test: CAN bus stale (>10s) ---
      const canStale = fn({
        status: 'online',
        last_seen: recentIso,
        ros2_available: true,
        motors: [{ id: 1, last_update: recentIso }],
        can_bus: { last_message_time: new Date(now - 15000).toISOString() },
        system_metrics: { cpu_percent: 30, memory_percent: 40, temperature_c: 45, disk_percent: 20 },
        services: [],
      });

      // --- Test: CAN bus null message time ---
      const canNull = fn({
        status: 'online',
        last_seen: recentIso,
        ros2_available: true,
        motors: [{ id: 1, last_update: recentIso }],
        can_bus: {},
        system_metrics: { cpu_percent: 30, memory_percent: 40, temperature_c: 45, disk_percent: 20 },
        services: [],
      });

      // --- Test: ros2_available false ---
      const ros2Unavailable = fn({
        status: 'online',
        last_seen: recentIso,
        ros2_available: false,
        system_metrics: { cpu_percent: 30, memory_percent: 40, temperature_c: 45, disk_percent: 20 },
        services: [{ name: 'svc1', active_state: 'active' }],
      });

      // --- Test: healthy entity (all good) ---
      const healthyEntity = fn({
        status: 'online',
        last_seen: recentIso,
        ros2_available: true,
        ros2_state: { node_count: 5, nodes: [] },
        motors: [{ id: 1, last_update: recentIso }],
        can_bus: { last_message_time: recentIso },
        system_metrics: { cpu_percent: 30, memory_percent: 40, temperature_c: 45, disk_percent: 20 },
        services: [{ name: 'svc1', active_state: 'active' }],
      });

      // --- Test: no system_metrics ---
      const noMetrics = fn({
        status: 'online',
        last_seen: recentIso,
        ros2_available: true,
        ros2_state: { node_count: 1, nodes: [] },
        motors: [{ id: 1, last_update: recentIso }],
        can_bus: { last_message_time: recentIso },
        services: [{ name: 'svc1', active_state: 'active' }],
      });

      // --- Test: system error (high cpu) ---
      const systemError = fn({
        status: 'online',
        last_seen: recentIso,
        ros2_available: true,
        ros2_state: { node_count: 1, nodes: [] },
        motors: [{ id: 1, last_update: recentIso }],
        can_bus: { last_message_time: recentIso },
        system_metrics: { cpu_percent: 95, memory_percent: 40, temperature_c: 45, disk_percent: 20 },
        services: [{ name: 'svc1', active_state: 'active' }],
      });

      // --- Test: services with failures ---
      const servicesFailed = fn({
        status: 'online',
        last_seen: recentIso,
        ros2_available: true,
        ros2_state: { node_count: 1, nodes: [] },
        motors: [{ id: 1, last_update: recentIso }],
        can_bus: { last_message_time: recentIso },
        system_metrics: { cpu_percent: 30, memory_percent: 40, temperature_c: 45, disk_percent: 20 },
        services: [
          { name: 'svc1', active_state: 'failed' },
          { name: 'svc2', active_state: 'active' },
        ],
      });

      return {
        nullEntity,
        offlineEntity,
        staleEntity,
        motorsUnavailable,
        canStale,
        canNull,
        ros2Unavailable,
        healthyEntity,
        noMetrics,
        systemError,
        servicesFailed,
      };
    });

    // null entityData → all unavailable
    assert(deriveResults.nullEntity.system === 'unavailable', 'null entityData → system unavailable');
    assert(deriveResults.nullEntity.ros2 === 'unavailable', 'null entityData → ros2 unavailable');
    assert(deriveResults.nullEntity.motors === 'unavailable', 'null entityData → motors unavailable');
    assert(deriveResults.nullEntity.can_bus === 'unavailable', 'null entityData → can_bus unavailable');
    assert(deriveResults.nullEntity.services === 'unavailable', 'null entityData → services unavailable');

    // offline entity → all unavailable
    assert(deriveResults.offlineEntity.system === 'unavailable', 'offline entity → system unavailable');
    assert(deriveResults.offlineEntity.motors === 'unavailable', 'offline entity → motors unavailable');

    // stale entity (>30s) → all unavailable
    assert(deriveResults.staleEntity.system === 'unavailable', 'stale entity (>30s) → system unavailable');
    assert(deriveResults.staleEntity.can_bus === 'unavailable', 'stale entity (>30s) → can_bus unavailable');

    // motors with null last_update → motors unavailable
    assert(deriveResults.motorsUnavailable.motors === 'unavailable', 'motors with null last_update → motors unavailable');
    assert(deriveResults.motorsUnavailable.system === 'healthy', 'motors unavailable but system still healthy (has metrics)');

    // CAN bus stale (>10s) → can_bus unavailable
    assert(deriveResults.canStale.can_bus === 'unavailable', 'CAN bus stale (>10s) → can_bus unavailable');
    assert(deriveResults.canStale.system === 'healthy', 'CAN stale but system still healthy');

    // CAN bus null message time → can_bus unavailable
    assert(deriveResults.canNull.can_bus === 'unavailable', 'CAN bus null last_message → can_bus unavailable');

    // ros2_available false → ros2, motors, can_bus unavailable
    assert(deriveResults.ros2Unavailable.ros2 === 'unavailable', 'ros2_available=false → ros2 unavailable');
    assert(deriveResults.ros2Unavailable.motors === 'unavailable', 'ros2_available=false → motors unavailable');
    assert(deriveResults.ros2Unavailable.can_bus === 'unavailable', 'ros2_available=false → can_bus unavailable');
    assert(deriveResults.ros2Unavailable.system === 'healthy', 'ros2_available=false but system still healthy');

    // healthy entity → all healthy
    assert(deriveResults.healthyEntity.system === 'healthy', 'healthy entity → system healthy');
    assert(deriveResults.healthyEntity.ros2 === 'healthy', 'healthy entity → ros2 healthy');
    assert(deriveResults.healthyEntity.motors === 'healthy', 'healthy entity → motors healthy');
    assert(deriveResults.healthyEntity.can_bus === 'healthy', 'healthy entity → can_bus healthy');
    assert(deriveResults.healthyEntity.services === 'healthy', 'healthy entity → services healthy');

    // no system_metrics → system unavailable
    assert(deriveResults.noMetrics.system === 'unavailable', 'no system_metrics → system unavailable');
    assert(deriveResults.noMetrics.ros2 === 'healthy', 'no system_metrics but ros2 still healthy');

    // system error (high cpu)
    assert(deriveResults.systemError.system === 'error', 'cpu >90% → system error');

    // services with mixed failures → degraded
    assert(deriveResults.servicesFailed.services === 'degraded', 'one failed + one active service → services degraded');

    // ================================================================
    // SECTION: Constants exported correctly
    // ================================================================
    console.log('\n[6] Exported constants');

    const constResults = await page.evaluate(async () => {
      const mod = await import('/js/components/StatusHealthTab.mjs');
      return {
        CAN_STALE_THRESHOLD_S: mod.CAN_STALE_THRESHOLD_S,
        ENTITY_STALE_THRESHOLD_S: mod.ENTITY_STALE_THRESHOLD_S,
        SUBSYSTEMS_length: mod.SUBSYSTEMS ? mod.SUBSYSTEMS.length : -1,
        hasSafetyStatusSection: typeof mod.SafetyStatusSection === 'function',
      };
    });

    assert(constResults.CAN_STALE_THRESHOLD_S === 10, 'CAN_STALE_THRESHOLD_S === 10');
    assert(constResults.ENTITY_STALE_THRESHOLD_S === 30, 'ENTITY_STALE_THRESHOLD_S === 30');
    assert(constResults.SUBSYSTEMS_length === 5, 'SUBSYSTEMS has 5 entries');
    assert(constResults.hasSafetyStatusSection, 'SafetyStatusSection is exported');

    // ================================================================
    // SECTION: Error Checks
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
