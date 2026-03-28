// Playwright UI tests for Pragati Web UI
// Run with: npx playwright test --config=playwright.config.js

const { test, expect } = require('@playwright/test');

// Helper: navigate and wait for backend WebSocket to connect
async function loadAndConnect(page) {
    await page.goto('/');
    // Wait for backend-dot to get 'connected' class
    await page.waitForSelector('#backend-dot.connected', { timeout: 10000 });
}

// ════════════════════════════════════════════════════════════════════
// 10.1 — Page Load, Pattern Selection & Execution
// ════════════════════════════════════════════════════════════════════

test.describe('Page load and connection [10.1]', () => {
    test('Test 1: Page loads and backend connects', async ({ page }) => {
        await page.goto('/');
        await page.waitForSelector('#backend-dot.connected', { timeout: 10000 });

        // Verify page title
        await expect(page).toHaveTitle('Pragati Robot Control');

        // Backend dot should be connected
        const backendDot = page.locator('#backend-dot');
        await expect(backendDot).toHaveClass(/connected/);
    });
});

test.describe('Pattern rendering [10.1]', () => {
    test('Test 2: Pattern buttons rendered by category', async ({ page }) => {
        await loadAndConnect(page);

        // Wait for pattern buttons to appear
        await page.waitForSelector('.pattern-btn', { timeout: 5000 });

        // Letter patterns category should contain letter_P and letter_R
        const letterBtns = page.locator('#letter-patterns .pattern-btn');
        await expect(letterBtns).toHaveCount(2);

        const letterP = page.locator('#letter-patterns .pattern-btn[data-pattern="letter_P"]');
        await expect(letterP).toBeVisible();

        const letterR = page.locator('#letter-patterns .pattern-btn[data-pattern="letter_R"]');
        await expect(letterR).toBeVisible();

        // Geometric category should contain circle
        const geoBtns = page.locator('#geometric-patterns .pattern-btn');
        await expect(geoBtns).toHaveCount(1);

        const circle = page.locator('#geometric-patterns .pattern-btn[data-pattern="circle"]');
        await expect(circle).toBeVisible();

        // Field category should contain zigzag
        const fieldBtns = page.locator('#field-patterns .pattern-btn');
        await expect(fieldBtns).toHaveCount(1);

        const zigzag = page.locator('#field-patterns .pattern-btn[data-pattern="zigzag"]');
        await expect(zigzag).toBeVisible();
    });
});

test.describe('Pattern selection [10.1]', () => {
    test('Test 3: Pattern selection highlights button', async ({ page }) => {
        await loadAndConnect(page);
        await page.waitForSelector('.pattern-btn', { timeout: 5000 });

        const circleBtn = page.locator('.pattern-btn[data-pattern="circle"]');
        await circleBtn.click();

        // Button should have 'selected' class
        await expect(circleBtn).toHaveClass(/selected/);

        // Start button should be enabled
        const startBtn = page.locator('#exec-start-btn');
        await expect(startBtn).not.toBeDisabled();
    });
});

test.describe('Pattern execution [10.1]', () => {
    test('Test 4: Start pattern shows progress updates', async ({ page }) => {
        await loadAndConnect(page);
        await page.waitForSelector('.pattern-btn', { timeout: 5000 });

        // Select pattern
        await page.locator('.pattern-btn[data-pattern="circle"]').click();

        // Click Start
        await page.locator('#exec-start-btn').click();

        // Wait for status to show executing or completed
        await page.waitForFunction(
            () => {
                const text = document.getElementById('exec-status-text').textContent;
                return text.includes('Executing') || text.includes('Completed') || text.includes('Starting');
            },
            { timeout: 5000 }
        );

        // Wait for progress bar to change width (mock sends 50% then 100%)
        await page.waitForFunction(
            () => {
                const fill = document.getElementById('exec-progress-fill');
                return fill.style.width && fill.style.width !== '0%';
            },
            { timeout: 5000 }
        );

        // Eventually should reach completed
        await page.waitForFunction(
            () => document.getElementById('exec-status-text').textContent === 'Completed',
            { timeout: 5000 }
        );
    });
});

test.describe('Speed scale [10.1]', () => {
    test('Test 11: Speed scale slider updates value', async ({ page }) => {
        await loadAndConnect(page);

        const valueLabel = page.locator('#speed-scale-value');

        // Set slider value via JS and dispatch input event (fill() doesn't work on range inputs)
        await page.evaluate(() => {
            const slider = document.getElementById('speed-scale-slider');
            slider.value = '1.50';
            slider.dispatchEvent(new Event('input', { bubbles: true }));
        });

        // The label updates immediately via the input event handler in app.js
        await expect(valueLabel).toHaveText('1.50x');
    });
});

// ════════════════════════════════════════════════════════════════════
// 10.2 — Joystick Suppression & Pause/Resume
// ════════════════════════════════════════════════════════════════════

test.describe('Joystick suppression [10.2]', () => {
    test('Test 5: Joystick suppressed during execution', async ({ page }) => {
        await loadAndConnect(page);
        await page.waitForSelector('.pattern-btn', { timeout: 5000 });

        // Select and start pattern
        await page.locator('.pattern-btn[data-pattern="circle"]').click();
        await page.locator('#exec-start-btn').click();

        // Joystick zone should get 'suppressed' class
        const joystickZone = page.locator('#joystick-zone');
        await expect(joystickZone).toHaveClass(/suppressed/, { timeout: 3000 });

        // Wait for completion — joystick should be un-suppressed
        await page.waitForFunction(
            () => document.getElementById('exec-status-text').textContent === 'Completed',
            { timeout: 5000 }
        );

        await expect(joystickZone).not.toHaveClass(/suppressed/);
    });
});

test.describe('Pause/Resume [10.2]', () => {
    test('Test 13: Pause and Resume toggles', async ({ page }) => {
        await loadAndConnect(page);
        await page.waitForSelector('.pattern-btn', { timeout: 5000 });

        // Select and start
        await page.locator('.pattern-btn[data-pattern="circle"]').click();
        await page.locator('#exec-start-btn').click();

        // Wait for executing state (pause button enabled)
        const pauseBtn = page.locator('#exec-pause-btn');
        await expect(pauseBtn).not.toBeDisabled({ timeout: 3000 });

        // Click Pause
        await pauseBtn.click();

        // Button text should change to "Resume"
        await expect(pauseBtn).toHaveText('Resume');

        // Click Resume
        await pauseBtn.click();

        // Button text should change back to "Pause"
        await expect(pauseBtn).toHaveText('Pause');
    });
});

// ════════════════════════════════════════════════════════════════════
// 10.3 — Drawing Canvas
// ════════════════════════════════════════════════════════════════════

test.describe('Drawing canvas [10.3]', () => {
    test('Test 6: Drawing on canvas enables Execute button', async ({ page }) => {
        await loadAndConnect(page);

        const canvas = page.locator('#draw-canvas');
        const executeBtn = page.locator('#draw-execute-btn');

        // Execute button starts disabled
        await expect(executeBtn).toBeDisabled();

        // Get canvas bounding box
        const box = await canvas.boundingBox();
        if (!box) throw new Error('Canvas not visible');

        // Draw a stroke: mousedown, multiple mousemoves, mouseup
        const startX = box.x + box.width * 0.2;
        const startY = box.y + box.height * 0.5;
        const endX = box.x + box.width * 0.8;
        const endY = box.y + box.height * 0.5;

        await page.mouse.move(startX, startY);
        await page.mouse.down();
        // Draw several points to ensure we have >= 2 points
        for (let i = 1; i <= 5; i++) {
            const x = startX + (endX - startX) * (i / 5);
            const y = startY + (endY - startY) * (i / 5);
            await page.mouse.move(x, y);
        }
        await page.mouse.up();

        // Execute button should now be enabled
        await expect(executeBtn).not.toBeDisabled();
    });

    test('Test 7: Execute draw sends path and shows execution', async ({ page }) => {
        await loadAndConnect(page);

        const canvas = page.locator('#draw-canvas');
        const executeBtn = page.locator('#draw-execute-btn');

        // Draw a stroke
        const box = await canvas.boundingBox();
        if (!box) throw new Error('Canvas not visible');

        const startX = box.x + box.width * 0.3;
        const startY = box.y + box.height * 0.4;
        const endX = box.x + box.width * 0.7;
        const endY = box.y + box.height * 0.6;

        await page.mouse.move(startX, startY);
        await page.mouse.down();
        for (let i = 1; i <= 5; i++) {
            await page.mouse.move(
                startX + (endX - startX) * (i / 5),
                startY + (endY - startY) * (i / 5)
            );
        }
        await page.mouse.up();

        // Click Execute
        await executeBtn.click();

        // Status should show execution started
        await page.waitForFunction(
            () => {
                const text = document.getElementById('exec-status-text').textContent;
                return text.includes('Executing') || text.includes('Completed') || text.includes('drawing');
            },
            { timeout: 5000 }
        );
    });
});

// ════════════════════════════════════════════════════════════════════
// 10.4 — Recording
// ════════════════════════════════════════════════════════════════════

test.describe('Recording [10.4]', () => {
    test('Test 8: Record button toggles recording state', async ({ page }) => {
        await loadAndConnect(page);

        const recordBtn = page.locator('#record-btn');
        const recIndicator = page.locator('#rec-indicator');
        const recStatusText = page.locator('#rec-status-text');

        // Initial state: rec-idle
        await expect(recordBtn).toHaveClass(/rec-idle/);

        // Click to start recording
        await recordBtn.click();

        // Should switch to recording state
        await expect(recordBtn).toHaveClass(/rec-recording/, { timeout: 3000 });
        await expect(recIndicator).toHaveClass(/rec-active/);

        // Click to stop recording
        await recordBtn.click();

        // Should switch back to idle
        await expect(recordBtn).toHaveClass(/rec-idle/, { timeout: 3000 });

        // Wait for recording_verified message with file info
        await page.waitForFunction(
            () => {
                const text = document.getElementById('rec-status-text').textContent;
                return text.includes('test.ogv') || text.includes('KB');
            },
            { timeout: 3000 }
        );
    });
});

// ════════════════════════════════════════════════════════════════════
// 10.5 — E-STOP & Stop
// ════════════════════════════════════════════════════════════════════

test.describe('E-STOP [10.5]', () => {
    test('Test 9: E-STOP during pattern execution', async ({ page }) => {
        await loadAndConnect(page);
        await page.waitForSelector('.pattern-btn', { timeout: 5000 });

        // Select and start pattern
        await page.locator('.pattern-btn[data-pattern="circle"]').click();
        await page.locator('#exec-start-btn').click();

        // Wait for joystick to be suppressed (proves execution started)
        const joystickZone = page.locator('#joystick-zone');
        await expect(joystickZone).toHaveClass(/suppressed/, { timeout: 3000 });

        // Click E-STOP
        await page.locator('#estop-btn').click();

        // E-STOP sends stop_pattern to backend, which releases cmd_vel
        // Joystick should be un-suppressed
        await expect(joystickZone).not.toHaveClass(/suppressed/, { timeout: 3000 });
    });
});

test.describe('Stop button [10.5]', () => {
    test('Test 12: Stop button stops execution', async ({ page }) => {
        await loadAndConnect(page);
        await page.waitForSelector('.pattern-btn', { timeout: 5000 });

        // Select and start
        await page.locator('.pattern-btn[data-pattern="circle"]').click();
        await page.locator('#exec-start-btn').click();

        // Wait for execution to be in progress
        const stopBtn = page.locator('#exec-stop-btn');
        await expect(stopBtn).not.toBeDisabled({ timeout: 3000 });

        // Click Stop
        await stopBtn.click();

        // Status should show stopped or return to idle
        await page.waitForFunction(
            () => {
                const text = document.getElementById('exec-status-text').textContent;
                return text.includes('Stopped') || text.includes('Stopping') || text === 'Idle';
            },
            { timeout: 5000 }
        );
    });
});

// ════════════════════════════════════════════════════════════════════
// 10.6 — Auto-Record
// ════════════════════════════════════════════════════════════════════

test.describe('Auto-record [10.6]', () => {
    test('Test 10: Auto-record checkbox', async ({ page }) => {
        await loadAndConnect(page);

        const checkbox = page.locator('#auto-record-checkbox');

        // Check it
        await checkbox.check();
        await expect(checkbox).toBeChecked();

        // Backend responds with auto_record_status — checkbox stays checked
        // Give time for roundtrip
        await page.waitForTimeout(200);
        await expect(checkbox).toBeChecked();

        // Uncheck it
        await checkbox.uncheck();
        await expect(checkbox).not.toBeChecked();
    });
});

// ════════════════════════════════════════════════════════════════════
// 11.1 — Robot Control Panel — Teleport
// ════════════════════════════════════════════════════════════════════

test.describe('Robot Control — Teleport [11.1]', () => {
    test('Test 14: Robot control panel exists', async ({ page }) => {
        await loadAndConnect(page);

        const panel = page.locator('#control-panel');
        await expect(panel).toBeVisible();

        const teleportBtns = page.locator('.teleport-btn');
        await expect(teleportBtns).toHaveCount(3);
    });

    test('Test 15: Teleport preset button sends message and shows result', async ({ page }) => {
        await loadAndConnect(page);

        const startBtn = page.locator('.teleport-btn[data-target="start"]');
        await startBtn.click();

        // Wait for teleport status to show completion
        await page.waitForFunction(
            () => {
                const text = document.getElementById('teleport-status').textContent;
                return text.includes('Teleport complete') || text.includes('complete');
            },
            { timeout: 5000 }
        );

        // Button should be re-enabled after response
        await expect(startBtn).not.toBeDisabled();
    });

    test('Test 16: Custom teleport toggle shows/hides inputs', async ({ page }) => {
        await loadAndConnect(page);

        const customInputs = page.locator('#teleport-custom-inputs');

        // Initially hidden
        await expect(customInputs).toHaveClass(/hidden/);

        // Click toggle to show
        await page.locator('#teleport-custom-toggle').click();
        await expect(customInputs).not.toHaveClass(/hidden/);

        // Click toggle to hide again
        await page.locator('#teleport-custom-toggle').click();
        await expect(customInputs).toHaveClass(/hidden/);
    });

    test('Test 17: Custom teleport validates inputs', async ({ page }) => {
        await loadAndConnect(page);

        // Show custom inputs
        await page.locator('#teleport-custom-toggle').click();

        // Clear all inputs
        await page.locator('#teleport-x').fill('');
        await page.locator('#teleport-y').fill('');
        await page.locator('#teleport-yaw').fill('');

        // Click Go
        await page.locator('#teleport-go-btn').click();

        // Should show validation error
        const errorEl = page.locator('#teleport-error');
        await expect(errorEl).toContainText('Invalid');
    });

    test('Test 18: Custom teleport with valid inputs sends message', async ({ page }) => {
        await loadAndConnect(page);

        // Show custom inputs
        await page.locator('#teleport-custom-toggle').click();

        // Fill valid values
        await page.locator('#teleport-x').fill('5.0');
        await page.locator('#teleport-y').fill('3.0');
        await page.locator('#teleport-yaw').fill('90');

        // Click Go
        await page.locator('#teleport-go-btn').click();

        // Wait for completion
        await page.waitForFunction(
            () => {
                const text = document.getElementById('teleport-status').textContent;
                return text.includes('complete');
            },
            { timeout: 5000 }
        );
    });
});

// ════════════════════════════════════════════════════════════════════
// 11.2 — Robot Control — Precision Movement
// ════════════════════════════════════════════════════════════════════

test.describe('Robot Control — Precision Movement [11.2]', () => {
    test('Test 19: Precision movement buttons exist', async ({ page }) => {
        await loadAndConnect(page);

        const precisionBtns = page.locator('.precision-btn');
        await expect(precisionBtns).toHaveCount(5);
    });

    test('Test 20: Precision move button sends message and shows progress', async ({ page }) => {
        await loadAndConnect(page);

        // Click forward 1m
        await page.locator('.precision-btn[data-action="forward_1m"]').click();

        // Wait for progress to show completion (mock sends 0→50→100 over 800ms)
        await page.waitForFunction(
            () => {
                const text = document.getElementById('precision-progress-text').textContent;
                return text.includes('100') || text.includes('Done') || text.includes('Completed');
            },
            { timeout: 5000 }
        );
    });

    test('Test 21: Cancel button appears during precision move', async ({ page }) => {
        await loadAndConnect(page);

        const cancelBtn = page.locator('#precision-cancel-btn');

        // Initially hidden
        await expect(cancelBtn).toHaveClass(/hidden/);

        // Start a precision move
        await page.locator('.precision-btn[data-action="forward_5m"]').click();

        // Cancel button should appear
        await expect(cancelBtn).not.toHaveClass(/hidden/, { timeout: 3000 });

        // Click cancel
        await cancelBtn.click();

        // Should show cancelled
        await page.waitForFunction(
            () => {
                const text = document.getElementById('precision-progress-text').textContent;
                return text.includes('Cancelled');
            },
            { timeout: 5000 }
        );
    });

    test('Test 22: Precision buttons disabled during move', async ({ page }) => {
        await loadAndConnect(page);

        // Start a precision move
        await page.locator('.precision-btn[data-action="forward_10m"]').click();

        // Brief wait for state to propagate
        await page.waitForTimeout(50);

        // All precision buttons should be disabled during move
        const precisionBtns = page.locator('.precision-btn');
        const count = await precisionBtns.count();
        for (let i = 0; i < count; i++) {
            await expect(precisionBtns.nth(i)).toBeDisabled();
        }

        // Wait for completion
        await page.waitForFunction(
            () => {
                const text = document.getElementById('precision-progress-text').textContent;
                return text.includes('100') || text.includes('Done') || text.includes('Completed');
            },
            { timeout: 5000 }
        );

        // Buttons should be re-enabled
        for (let i = 0; i < count; i++) {
            await expect(precisionBtns.nth(i)).not.toBeDisabled();
        }
    });
});

// ════════════════════════════════════════════════════════════════════
// 11.3 — Sensor Dashboard
// ════════════════════════════════════════════════════════════════════

test.describe('Sensor Dashboard [11.3]', () => {
    test('Test 23: Sensor panel exists and is always visible', async ({ page }) => {
        await loadAndConnect(page);

        const sensorPanel = page.locator('#sensor-panel');
        await expect(sensorPanel).toBeVisible();

        // Sensor sub-panels should be visible without any interaction
        await expect(page.locator('#imu-panel')).toBeVisible();
        await expect(page.locator('#gps-panel')).toBeVisible();
    });

    test('Test 24: Pattern panel collapses and expands', async ({ page }) => {
        await loadAndConnect(page);

        const patternPanel = page.locator('#pattern-panel');
        const patternContent = page.locator('#pattern-panel-content');

        // Pattern panel starts expanded
        await expect(patternContent).toBeVisible();

        // Click to collapse
        await page.locator('#pattern-panel-toggle').click();
        await expect(patternPanel).toHaveClass(/collapsed/);
        await expect(patternContent).not.toBeVisible();

        // Click to expand again
        await page.locator('#pattern-panel-toggle').click();
        await expect(patternPanel).not.toHaveClass(/collapsed/);
        await expect(patternContent).toBeVisible();
    });

    test('Test 25: Sensor sub-panels exist', async ({ page }) => {
        await loadAndConnect(page);

        await expect(page.locator('#imu-panel')).toBeVisible();
        await expect(page.locator('#gps-panel')).toBeVisible();
        await expect(page.locator('#odom-panel')).toBeVisible();
        await expect(page.locator('#camera-panel')).toBeVisible();
    });

    test('Test 26: IMU sensor value elements exist', async ({ page }) => {
        await loadAndConnect(page);

        await expect(page.locator('#imu-roll')).toBeVisible();
        await expect(page.locator('#imu-pitch')).toBeVisible();
        await expect(page.locator('#imu-yaw')).toBeVisible();
        await expect(page.locator('#imu-gyro-x')).toBeVisible();
        await expect(page.locator('#imu-gyro-y')).toBeVisible();
        await expect(page.locator('#imu-gyro-z')).toBeVisible();
        await expect(page.locator('#imu-accel-x')).toBeVisible();
        await expect(page.locator('#imu-accel-y')).toBeVisible();
        await expect(page.locator('#imu-accel-z')).toBeVisible();
    });

    test('Test 27: GPS sensor value elements exist', async ({ page }) => {
        await loadAndConnect(page);

        await expect(page.locator('#gps-lat')).toBeVisible();
        await expect(page.locator('#gps-lon')).toBeVisible();
        await expect(page.locator('#gps-alt')).toBeVisible();
    });

    test('Test 28: Odom sensor value elements exist', async ({ page }) => {
        await loadAndConnect(page);

        await expect(page.locator('#odom-x')).toBeVisible();
        await expect(page.locator('#odom-y')).toBeVisible();
        await expect(page.locator('#odom-heading')).toBeVisible();
        await expect(page.locator('#odom-lin-vel')).toBeVisible();
        await expect(page.locator('#odom-ang-vel')).toBeVisible();
    });

    test('Test 29: Camera feed element exists', async ({ page }) => {
        await loadAndConnect(page);

        await expect(page.locator('#camera-feed')).toBeVisible();
    });
});

// ════════════════════════════════════════════════════════════════════
// 11.4 — Odometry Trail
// ════════════════════════════════════════════════════════════════════

test.describe('Odometry Trail [11.4]', () => {
    test('Test 30: Odom trail canvas exists', async ({ page }) => {
        await loadAndConnect(page);

        const canvas = page.locator('#odom-trail-canvas');
        await expect(canvas).toBeVisible();

        // Check canvas dimensions
        await expect(canvas).toHaveAttribute('width', '250');
        await expect(canvas).toHaveAttribute('height', '250');
    });

    test('Test 31: Clear trail button exists and is clickable', async ({ page }) => {
        await loadAndConnect(page);

        const clearBtn = page.locator('#odom-trail-clear');
        await expect(clearBtn).toBeVisible();

        // Click should not throw
        await clearBtn.click();
    });
});

// ════════════════════════════════════════════════════════════════════
// 11.5 — E-STOP disables robot controls
// ════════════════════════════════════════════════════════════════════

test.describe('E-STOP disables robot controls [11.5]', () => {
    test('Test 32: E-STOP disables teleport and precision buttons', async ({ page }) => {
        await loadAndConnect(page);

        // Activate E-STOP
        await page.locator('#estop-btn').click();

        // All teleport buttons should be disabled
        const teleportBtns = page.locator('.teleport-btn');
        const teleportCount = await teleportBtns.count();
        for (let i = 0; i < teleportCount; i++) {
            await expect(teleportBtns.nth(i)).toBeDisabled();
        }

        // Teleport Go button should be disabled
        await expect(page.locator('#teleport-go-btn')).toBeDisabled();

        // All precision buttons should be disabled
        const precisionBtns = page.locator('.precision-btn');
        const precisionCount = await precisionBtns.count();
        for (let i = 0; i < precisionCount; i++) {
            await expect(precisionBtns.nth(i)).toBeDisabled();
        }

        // Deactivate E-STOP
        await page.locator('#estop-btn').click();

        // All buttons should be re-enabled
        for (let i = 0; i < teleportCount; i++) {
            await expect(teleportBtns.nth(i)).not.toBeDisabled();
        }
        await expect(page.locator('#teleport-go-btn')).not.toBeDisabled();
        for (let i = 0; i < precisionCount; i++) {
            await expect(precisionBtns.nth(i)).not.toBeDisabled();
        }
    });
});