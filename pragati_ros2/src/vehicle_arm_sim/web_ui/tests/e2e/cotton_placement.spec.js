// @ts-check
const { test, expect } = require('@playwright/test');

// E2E tests for the Cotton Placement section (ported from yanthra_move).

test('Cotton Placement section is visible on page load', async ({ page }) => {
  await page.goto('/');
  const section = page.locator('#cotton-placement-section');
  await expect(section).toBeVisible({ timeout: 3000 });
});

test('Spawn Cotton button exists and is clickable', async ({ page }) => {
  await page.goto('/');
  const btn = page.locator('#cotton-spawn-btn');
  await expect(btn).toBeVisible({ timeout: 2000 });
  await expect(btn).toBeEnabled();
});

test('Compute Approach button shows results panel', async ({ page }) => {
  await page.goto('/');
  await page.route('/api/cotton/compute', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        arm_x: -0.1, arm_y: 0.05, arm_z: -0.08,
        r: 0.128, theta: 0.05, phi: -0.675,
        j3: -0.675, j4: 0.05, j5: 0.0,
        j3_raw: -0.675, j4_raw: 0.05, j5_raw: -0.192,
        reachable: false, phi_compensated: false,
      }),
    });
  });
  await page.locator('#cotton-compute-btn').click();
  const resultsPanel = page.locator('#cotton-compute-results');
  await expect(resultsPanel).toBeVisible({ timeout: 2000 });
});

test('Pick Cotton button exists and is clickable', async ({ page }) => {
  await page.goto('/');
  const btn = page.locator('#cotton-pick-btn');
  await expect(btn).toBeVisible({ timeout: 2000 });
  await expect(btn).toBeEnabled();
});

test('Spawn unreachable cotton shows error message in log', async ({ page }) => {
  await page.goto('/');
  // Mock spawn endpoint to return 400 (unreachable)
  await page.route('/api/cotton/spawn', async route => {
    await route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: 'Unreachable: J3=-1.200 rad out of range [-0.9, 0.0]',
      }),
    });
  });
  await page.locator('#cotton-spawn-btn').click();
  // Should show error in log area with 'error' class
  const logArea = page.locator('#log-area');
  const errorEntry = logArea.locator('.log-error');
  await expect(errorEntry.first()).toBeVisible({ timeout: 3000 });
  await expect(errorEntry.first()).toContainText('Unreachable');
});

test('Cotton table shows spawned cottons', async ({ page }) => {
  await page.goto('/');
  // Mock spawn to succeed and list to return cottons
  await page.route('/api/cotton/spawn', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        cotton_name: 'cotton_0',
        world_x: 1.0, world_y: 2.0, world_z: 0.5,
      }),
    });
  });
  await page.route('/api/cotton/list', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        cottons: [
          { name: 'cotton_0', cam_x: 0.494, cam_y: -0.001, cam_z: 0.004, arm: 'arm1', status: 'spawned' },
          { name: 'cotton_1', cam_x: 0.525, cam_y: 0.020, cam_z: 0.008, arm: 'arm1', status: 'spawned' },
        ],
      }),
    });
  });
  await page.locator('#cotton-spawn-btn').click();
  const table = page.locator('#cotton-table-container');
  await expect(table).toBeVisible({ timeout: 3000 });
  const rows = page.locator('#cotton-table-body tr');
  await expect(rows).toHaveCount(2);
});

test('Remove All clears cotton table', async ({ page }) => {
  await page.goto('/');
  // First show a populated table by mocking list
  await page.route('/api/cotton/list', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ cottons: [] }),
    });
  });
  await page.route('/api/cotton/remove-all', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', removed: 2 }),
    });
  });
  await page.locator('#cotton-remove-all-btn').click();
  const table = page.locator('#cotton-table-container');
  await expect(table).toBeHidden({ timeout: 3000 });
});

test('Pick All button starts pick-all sequence', async ({ page }) => {
  await page.goto('/');
  await page.route('/api/cotton/pick-all', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'picking', total: 2 }),
    });
  });
  await page.route('/api/cotton/pick/status', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        in_progress: false,
        status: 'done',
      }),
    });
  });
  await page.route('/api/cotton/list', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ cottons: [] }),
    });
  });
  await page.locator('#cotton-pick-all-btn').click();
  const logArea = page.locator('#log-area');
  const successEntry = logArea.locator('.log-success');
  await expect(successEntry.last()).toContainText('Pick-all', { timeout: 3000 });
});
