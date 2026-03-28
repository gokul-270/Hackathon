#!/usr/bin/env node
// Role-Based Tab Filtering E2E Test Suite
// Validates that the entity-centric sidebar renders correctly for each dashboard
// role (dev, vehicle, arm) and that legacy hash redirects work as expected.
//
// Current state (Phase 7): roleConfig.mjs is no longer imported by app.js.
// GroupedSidebar renders flat entity links (no expand/collapse groups) and 4
// global nav items: Operations, Monitoring, Motor Config, Settings.
// Motor Config is a standalone global tool, not an entity sub-tab.
//
// This test verifies:
//   - Sidebar structure (Fleet Overview, flat entity links, global nav items)
//   - Legacy hash redirects (#nodes -> #/entity/local/nodes, etc.)
//   - Motor Config as global route (#motor-config stays, not redirected to entity)
//   - Hash navigation for global routes (operations, monitoring, motor-config, settings)
//
// Uses Playwright route interception to mock /api/config/role and /api/entities.
//
// Run: node web_dashboard/e2e_tests/role_tab_filtering_e2e.mjs
//
// Requires: npm install playwright (in this directory)
// Dashboard must be running on http://127.0.0.1:8090

import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8090";
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

// Helper: check element is visible (display != none, visibility != hidden)
async function isVisible(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return false;
    const style = getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden";
  }, selector);
}

// Helper: get text of the Fleet Overview link (.sidebar-overview)
async function getFleetOverviewText(page) {
  return page.evaluate(() => {
    const el = document.querySelector(".sidebar-overview");
    return el ? el.textContent.trim() : null;
  });
}

// Helper: get all global nav item labels (.sidebar-nav-item)
async function getGlobalNavLabels(page) {
  return page.evaluate(() => {
    return Array.from(document.querySelectorAll(".sidebar-nav-item")).map((el) =>
      el.textContent.trim()
    );
  });
}

// Helper: get all flat entity link texts (.sidebar-entity-link)
async function getEntityLinkTexts(page) {
  return page.evaluate(() => {
    return Array.from(
      document.querySelectorAll(".sidebar-entity-link")
    ).map((el) => el.textContent.trim());
  });
}

// Helper: get all sidebar labels (Fleet Overview + entity links + global nav items)
async function getAllSidebarLabels(page) {
  return page.evaluate(() => {
    const labels = [];
    // Fleet Overview link
    const overview = document.querySelector(".sidebar-overview");
    if (overview) labels.push(overview.textContent.trim());
    // Entity links (flat)
    const entityLinks = document.querySelectorAll(".sidebar-entity-link");
    for (const link of entityLinks) {
      labels.push(link.textContent.trim());
    }
    // Global nav items
    const navItems = document.querySelectorAll(".sidebar-nav-item");
    for (const item of navItems) {
      labels.push(item.textContent.trim());
    }
    return labels;
  });
}

// Helper: get the currently active content section id
async function getActiveSection(page) {
  return page.evaluate(() => {
    const sections = document.querySelectorAll(".content-section");
    for (const s of sections) {
      if (
        s.classList.contains("active") ||
        getComputedStyle(s).display !== "none"
      )
        return s.id;
    }
    return null;
  });
}

// Helper: get current hash
async function getHash(page) {
  return page.evaluate(() => window.location.hash);
}

// Helper: set role via /api/config/role mock and reload.
// Also mocks /api/entities to provide a test entity so sidebar entity links render.
async function setRoleAndReload(page, role) {
  // Clear existing routes
  await page.unroute("**/api/config/role");
  await page.unroute("**/api/entities");

  // Mock role endpoint
  await page.route("**/api/config/role", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ role }),
    });
  });

  // Mock entities endpoint to provide a test arm entity
  await page.route("**/api/entities", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "arm1",
          name: "Arm 1",
          role: "arm",
          status: "online",
          source: "local",
          last_seen: new Date().toISOString(),
        },
      ]),
    });
  });

  // Navigate to base URL (fresh load)
  await page.goto(BASE, { waitUntil: "networkidle", timeout: 15000 });
  // Wait for Preact render + entity fetch + sidebar rebuild
  await page.waitForTimeout(1500);
}

(async () => {
  console.log("Role-Based Tab Filtering E2E Tests");
  console.log(`Target: ${BASE}`);
  console.log("=============================================\n");

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || undefined,
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
  });

  const page = await browser.newPage();

  // Collect JS errors
  const jsErrors = [];
  page.on("pageerror", (err) => jsErrors.push(err.message));

  // Global timeout
  const timeout = setTimeout(async () => {
    console.log("\n  CRASH  Global timeout (60s) exceeded");
    failed++;
    failures.push("CRASH: Global timeout (60s) exceeded");
    await browser.close();
    printSummary();
    process.exit(1);
  }, 60000);

  try {
    // ==================================================================
    // Test 1: Dev role — sidebar shows full structure
    // ==================================================================
    console.log("[1] Dev role — sidebar shows full structure");

    await setRoleAndReload(page, "dev");

    // 1a. Fleet Overview link exists
    const devFleetOverview = await getFleetOverviewText(page);
    assert(
      devFleetOverview !== null && devFleetOverview.includes("Fleet Overview"),
      'Dev role: Fleet Overview link is visible'
    );

    // 1b. All 4 global nav items visible
    const devGlobalNav = await getGlobalNavLabels(page);
    const expectedGlobalNav = ["Operations", "Monitoring", "Motor Config", "Settings"];
    for (const label of expectedGlobalNav) {
      const found = devGlobalNav.some((l) => l.includes(label));
      assert(found, `Dev role: "${label}" global nav item is visible`);
    }
    assert(
      devGlobalNav.length === 4,
      `Dev role: exactly 4 global nav items (got ${devGlobalNav.length})`
    );

    // 1c. Flat entity link exists (from mocked entity)
    const devEntityLinks = await getEntityLinkTexts(page);
    assert(
      devEntityLinks.length >= 1,
      `Dev role: at least 1 entity link (got ${devEntityLinks.length})`
    );
    const hasArm1 = devEntityLinks.some((h) => h.includes("Arm 1"));
    assert(hasArm1, 'Dev role: "Arm 1" entity link exists');

    // 1d. No sidebar-group elements (flat structure)
    const devSidebarGroups = await page.evaluate(() => {
      return document.querySelectorAll('.sidebar-group').length;
    });
    assert(devSidebarGroups === 0,
      `Dev role: no .sidebar-group elements (got ${devSidebarGroups})`);

    // 1e. Hash navigation to #fleet-overview works
    await page.evaluate(() => {
      window.location.hash = "#fleet-overview";
    });
    await page.waitForTimeout(800);

    const devFleetHash = await getHash(page);
    assert(
      devFleetHash === "#fleet-overview",
      `Dev role: #fleet-overview hash is retained (got "${devFleetHash}")`
    );

    const devFleetSection = await getActiveSection(page);
    assert(
      devFleetSection === "fleet-overview-section",
      `Dev role: fleet-overview section is active (got "${devFleetSection}")`
    );

    // ==================================================================
    // Test 2: Vehicle role — sidebar renders same structure (no role filtering)
    // ==================================================================
    console.log("\n[2] Vehicle role — sidebar structure");

    await setRoleAndReload(page, "vehicle");

    // 2a. Fleet Overview link still visible (role filtering is removed)
    const vehicleFleetOverview = await getFleetOverviewText(page);
    assert(
      vehicleFleetOverview !== null &&
        vehicleFleetOverview.includes("Fleet Overview"),
      "Vehicle role: Fleet Overview link is visible (no role filtering)"
    );

    // 2b. All 4 global nav items visible
    const vehicleGlobalNav = await getGlobalNavLabels(page);
    for (const label of expectedGlobalNav) {
      const found = vehicleGlobalNav.some((l) => l.includes(label));
      assert(found, `Vehicle role: "${label}" global nav item is visible`);
    }

    // 2c. Entity link exists
    const vehicleEntityLinks = await getEntityLinkTexts(page);
    assert(
      vehicleEntityLinks.length >= 1,
      `Vehicle role: entity links present (got ${vehicleEntityLinks.length})`
    );

    // ==================================================================
    // Test 3: Vehicle role — legacy hash redirects
    // ==================================================================
    console.log("\n[3] Vehicle role — legacy hash redirects");

    // 3a. #nodes (legacy entity tab) redirects to #/entity/local/nodes
    await page.evaluate(() => {
      window.location.hash = "#nodes";
    });
    await page.waitForTimeout(800);

    const vehicleNodesHash = await getHash(page);
    assert(
      vehicleNodesHash === "#/entity/local/nodes",
      `Vehicle role: #nodes redirected to entity route (got "${vehicleNodesHash}")`
    );

    // 3b. #motor-config stays as global route (not redirected to entity)
    await page.evaluate(() => {
      window.location.hash = "#motor-config";
    });
    await page.waitForTimeout(800);

    const vehicleMotorHash = await getHash(page);
    assert(
      vehicleMotorHash === "#motor-config",
      `Vehicle role: #motor-config stays as global route (got "${vehicleMotorHash}")`
    );

    // 3c. #overview redirects to #fleet-overview (legacy redirect)
    await page.evaluate(() => {
      window.location.hash = "#overview";
    });
    await page.waitForTimeout(800);

    const vehicleOverviewHash = await getHash(page);
    assert(
      vehicleOverviewHash === "#fleet-overview",
      `Vehicle role: #overview redirected to #fleet-overview (got "${vehicleOverviewHash}")`
    );

    // 3d. #safety redirects to #fleet-overview (legacy redirect)
    await page.evaluate(() => {
      window.location.hash = "#safety";
    });
    await page.waitForTimeout(800);

    const vehicleSafetyHash = await getHash(page);
    assert(
      vehicleSafetyHash === "#fleet-overview",
      `Vehicle role: #safety redirected to #fleet-overview (got "${vehicleSafetyHash}")`
    );

    // 3e. #operations stays (global route, not redirected)
    await page.evaluate(() => {
      window.location.hash = "#operations";
    });
    await page.waitForTimeout(800);

    const vehicleOpsHash = await getHash(page);
    assert(
      vehicleOpsHash === "#operations",
      `Vehicle role: #operations is retained (got "${vehicleOpsHash}")`
    );

    // 3f. #settings stays (global route)
    await page.evaluate(() => {
      window.location.hash = "#settings";
    });
    await page.waitForTimeout(800);

    const vehicleSettingsHash = await getHash(page);
    assert(
      vehicleSettingsHash === "#settings",
      `Vehicle role: #settings is retained (got "${vehicleSettingsHash}")`
    );

    // ==================================================================
    // Test 4: Arm role — sidebar structure
    // ==================================================================
    console.log("\n[4] Arm role — sidebar structure");

    await setRoleAndReload(page, "arm");

    // 4a. Fleet Overview link visible (no role filtering)
    const armFleetOverview = await getFleetOverviewText(page);
    assert(
      armFleetOverview !== null && armFleetOverview.includes("Fleet Overview"),
      "Arm role: Fleet Overview link is visible (no role filtering)"
    );

    // 4b. All 4 global nav items visible
    const armGlobalNav = await getGlobalNavLabels(page);
    for (const label of expectedGlobalNav) {
      const found = armGlobalNav.some((l) => l.includes(label));
      assert(found, `Arm role: "${label}" global nav item is visible`);
    }

    // 4c. Entity link exists
    const armEntityLinks = await getEntityLinkTexts(page);
    assert(
      armEntityLinks.length >= 1,
      `Arm role: entity links present (got ${armEntityLinks.length})`
    );

    // ==================================================================
    // Test 5: Arm role — legacy hash redirects
    // ==================================================================
    console.log("\n[5] Arm role — legacy hash redirects");

    // 5a. #health (legacy entity tab) redirects to #/entity/local/status
    await page.evaluate(() => {
      window.location.hash = "#health";
    });
    await page.waitForTimeout(800);

    const armHealthHash = await getHash(page);
    assert(
      armHealthHash === "#/entity/local/status",
      `Arm role: #health redirected to entity route (got "${armHealthHash}")`
    );

    // 5b. #parameters (legacy entity tab) redirects to #/entity/local/parameters
    await page.evaluate(() => {
      window.location.hash = "#parameters";
    });
    await page.waitForTimeout(800);

    const armParamsHash = await getHash(page);
    assert(
      armParamsHash === "#/entity/local/parameters",
      `Arm role: #parameters redirected to entity route (got "${armParamsHash}")`
    );

    // 5c. #topics (legacy entity tab) redirects to #/entity/local/topics
    await page.evaluate(() => {
      window.location.hash = "#topics";
    });
    await page.waitForTimeout(800);

    const armTopicsHash = await getHash(page);
    assert(
      armTopicsHash === "#/entity/local/topics",
      `Arm role: #topics redirected to entity route (got "${armTopicsHash}")`
    );

    // 5d. #monitoring stays (global route)
    await page.evaluate(() => {
      window.location.hash = "#monitoring";
    });
    await page.waitForTimeout(800);

    const armMonitoringHash = await getHash(page);
    assert(
      armMonitoringHash === "#monitoring",
      `Arm role: #monitoring is retained (got "${armMonitoringHash}")`
    );

    // 5e. #logs (legacy entity tab) redirects to #/entity/local/logs
    await page.evaluate(() => {
      window.location.hash = "#logs";
    });
    await page.waitForTimeout(800);

    const armLogsHash = await getHash(page);
    assert(
      armLogsHash === "#/entity/local/logs",
      `Arm role: #logs redirected to entity route (got "${armLogsHash}")`
    );

    // 5f. #motor-config stays as global route (Motor Config is standalone tool)
    await page.evaluate(() => {
      window.location.hash = "#motor-config";
    });
    await page.waitForTimeout(800);

    const armMotorHash = await getHash(page);
    assert(
      armMotorHash === "#motor-config",
      `Arm role: #motor-config stays as global route (got "${armMotorHash}")`
    );

    // ==================================================================
    // Test 6: Role switch — sidebar remains consistent (no filtering)
    // ==================================================================
    console.log("\n[6] Role switch — sidebar remains consistent");

    // Start with vehicle role
    await setRoleAndReload(page, "vehicle");
    const vehicleGlobalNav2 = await getGlobalNavLabels(page);
    const vehicleHasMotorConfig = vehicleGlobalNav2.some((l) =>
      l.includes("Motor Config")
    );
    assert(
      vehicleHasMotorConfig,
      "Vehicle role (pre-switch): Motor Config visible in global nav"
    );

    // Switch to arm role
    await setRoleAndReload(page, "arm");
    const armGlobalNav2 = await getGlobalNavLabels(page);
    const armHasMotorConfig = armGlobalNav2.some((l) =>
      l.includes("Motor Config")
    );
    assert(
      armHasMotorConfig,
      "Arm role (post-switch): Motor Config still visible in global nav"
    );

    // Switch to dev role
    await setRoleAndReload(page, "dev");
    const devGlobalNav2 = await getGlobalNavLabels(page);
    const devHasMotorConfig = devGlobalNav2.some((l) =>
      l.includes("Motor Config")
    );
    assert(
      devHasMotorConfig,
      "Dev role (post-switch): Motor Config still visible in global nav"
    );

    // Verify global nav is consistent across all switches
    assert(
      devGlobalNav2.length === 4,
      `Dev role (post-switch): still 4 global nav items (got ${devGlobalNav2.length})`
    );

    // ==================================================================
    // Test 7: Default route and initial load behavior
    // ==================================================================
    console.log("\n[7] Default route and initial load behavior");

    // 7a. Loading with no hash defaults to #fleet-overview
    await page.goto(BASE, { waitUntil: "networkidle", timeout: 15000 });
    await page.waitForTimeout(1500);

    const defaultHash = await getHash(page);
    assert(
      defaultHash === "#fleet-overview",
      `Default route: no hash -> #fleet-overview (got "${defaultHash}")`
    );

    // 7b. Loading with #overview redirects to #fleet-overview
    await page.goto(`${BASE}/#overview`, {
      waitUntil: "networkidle",
      timeout: 15000,
    });
    await page.waitForTimeout(1500);

    const overviewRedirectHash = await getHash(page);
    assert(
      overviewRedirectHash === "#fleet-overview",
      `Initial load: #overview -> #fleet-overview (got "${overviewRedirectHash}")`
    );

    // 7c. Loading with #nodes redirects to #/entity/local/nodes
    await page.goto(`${BASE}/#nodes`, {
      waitUntil: "networkidle",
      timeout: 15000,
    });
    await page.waitForTimeout(1500);

    const nodesRedirectHash = await getHash(page);
    assert(
      nodesRedirectHash === "#/entity/local/nodes",
      `Initial load: #nodes -> #/entity/local/nodes (got "${nodesRedirectHash}")`
    );

    // 7d. Loading with #operations stays on #operations
    await page.goto(`${BASE}/#operations`, {
      waitUntil: "networkidle",
      timeout: 15000,
    });
    await page.waitForTimeout(1500);

    const opsLoadHash = await getHash(page);
    assert(
      opsLoadHash === "#operations",
      `Initial load: #operations retained (got "${opsLoadHash}")`
    );

    // 7e. Loading with #fleet-overview stays on #fleet-overview
    await page.goto(`${BASE}/#fleet-overview`, {
      waitUntil: "networkidle",
      timeout: 15000,
    });
    await page.waitForTimeout(1500);

    const fleetLoadHash = await getHash(page);
    assert(
      fleetLoadHash === "#fleet-overview",
      `Initial load: #fleet-overview retained (got "${fleetLoadHash}")`
    );

    // 7f. Loading with #motor-config stays on #motor-config (global route)
    await page.goto(`${BASE}/#motor-config`, {
      waitUntil: "networkidle",
      timeout: 15000,
    });
    await page.waitForTimeout(1500);

    const motorLoadHash = await getHash(page);
    assert(
      motorLoadHash === "#motor-config",
      `Initial load: #motor-config retained (got "${motorLoadHash}")`
    );

    // ==================================================================
    // Test 8: Error checks
    // ==================================================================
    console.log("\n[8] Error checks");

    assert(
      jsErrors.length === 0,
      `No JS errors during tests (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join("; ")})`
    );
  } catch (err) {
    console.log(`\n  CRASH  ${err.message}`);
    failed++;
    failures.push(`CRASH: ${err.message}`);
  } finally {
    clearTimeout(timeout);
    await browser.close();
  }

  printSummary();
  process.exit(failed > 0 ? 1 : 0);
})();

function printSummary() {
  const total = passed + failed + skipped;
  console.log("\n=============================================");
  console.log(
    `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`
  );
  if (failures.length > 0) {
    console.log("\nFailures:");
    failures.forEach((f) => console.log(`  - ${f}`));
  }
  console.log();
}
