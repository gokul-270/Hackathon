#!/usr/bin/env node
// Journalctl Time Filters E2E Test Suite (Phase 4 — Tasks 82-85)
//
// Tests the time-range filtering feature in the Logs sub-tab:
// - Preset button rendering and activation
// - Custom datetime picker validation (From < To)
// - Time filter composing with severity filter
// - File list filtering by modification timestamp
//
// Run: node web_dashboard/e2e_tests/test_journalctl_time_filters.mjs
//
// Requires: npm install playwright (in e2e_tests directory)
// Dashboard must be running on http://127.0.0.1:8090 with at least
// one remote entity configured.

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

// Helper: navigate via hash change
async function navigateToHash(page, hash) {
    await page.evaluate((h) => {
        window.location.hash = h;
    }, hash);
    await page.waitForTimeout(2000);
}

// Helper: find the first entity ID from the sidebar
async function findFirstEntityId(page) {
    return page.evaluate(() => {
        const links = document.querySelectorAll(
            'a[href*="entity/"], [data-entity-id]',
        );
        for (const link of links) {
            const href = link.getAttribute("href") || "";
            const match = href.match(/entity\/([^/]+)/);
            if (match) return match[1];
            const dataId = link.getAttribute("data-entity-id");
            if (dataId) return dataId;
        }
        const hashLinks = document.querySelectorAll("[onclick]");
        for (const el of hashLinks) {
            const onclick = el.getAttribute("onclick") || "";
            const match = onclick.match(/entity\/([^'"]+)/);
            if (match) return match[1];
        }
        return null;
    });
}

// Helper: click a sub-tab by label text within entity detail section
async function clickSubTab(page, label) {
    return page.evaluate((tabLabel) => {
        const section = document.getElementById("entity-detail-section");
        if (!section) return false;
        const buttons = section.querySelectorAll("button");
        for (const btn of buttons) {
            if (btn.textContent.trim() === tabLabel) {
                btn.click();
                return true;
            }
        }
        return false;
    }, label);
}

async function run() {
    console.log("\n=== Journalctl Time Filters E2E Tests ===\n");

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
        viewport: { width: 1400, height: 900 },
    });
    const page = await context.newPage();

    // Suppress console noise from the dashboard
    page.on("pageerror", () => {});

    try {
        // ------------------------------------------------------------------
        // 1. Load dashboard and navigate to Logs tab
        // ------------------------------------------------------------------
        console.log("--- Setup ---");
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 15000 });
        await page.waitForTimeout(3000);

        const entityId = await findFirstEntityId(page);
        if (!entityId) {
            skip("All tests", "No entity found in sidebar — is an agent connected?");
            await browser.close();
            printSummary();
            return;
        }
        console.log(`  Found entity: ${entityId}`);

        await navigateToHash(page, `#entity/${entityId}`);
        await page.waitForTimeout(2000);

        const clickedLogs = await clickSubTab(page, "Logs");
        if (!clickedLogs) {
            skip("All tests", "Could not find Logs tab button");
            await browser.close();
            printSummary();
            return;
        }
        await page.waitForTimeout(2000);

        // ------------------------------------------------------------------
        // 2. Time Preset Buttons
        // ------------------------------------------------------------------
        console.log("\n--- Time Preset Buttons ---");

        const presetButtons = await page.evaluate(() => {
            const buttons = document.querySelectorAll("button");
            const presets = [];
            for (const btn of buttons) {
                const text = btn.textContent.trim();
                if (
                    text === "Last 10 min" ||
                    text === "Last 1 hr" ||
                    text === "Last 6 hr" ||
                    text === "Last 24 hr"
                ) {
                    presets.push({
                        text,
                        hasAccentBg:
                            btn.style.background.includes("accent") ||
                            btn.style.backgroundColor.includes("75, 141, 247"),
                    });
                }
            }
            return presets;
        });

        assert(
            presetButtons.length === 4,
            `All 4 time preset buttons render (found ${presetButtons.length})`,
        );

        const presetLabels = presetButtons.map((b) => b.text);
        assert(
            presetLabels.includes("Last 10 min"),
            "Preset 'Last 10 min' exists",
        );
        assert(
            presetLabels.includes("Last 1 hr"),
            "Preset 'Last 1 hr' exists",
        );
        assert(
            presetLabels.includes("Last 6 hr"),
            "Preset 'Last 6 hr' exists",
        );
        assert(
            presetLabels.includes("Last 24 hr"),
            "Preset 'Last 24 hr' exists",
        );

        // Initially none should be highlighted
        assert(
            presetButtons.every((b) => !b.hasAccentBg),
            "No preset button is highlighted initially",
        );

        // ------------------------------------------------------------------
        // 3. Preset Button Activation
        // ------------------------------------------------------------------
        console.log("\n--- Preset Activation ---");

        // Click "Last 1 hr"
        const clickedPreset = await page.evaluate(() => {
            const buttons = document.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Last 1 hr") {
                    btn.click();
                    return true;
                }
            }
            return false;
        });
        await page.waitForTimeout(500);

        assert(clickedPreset, "Clicked 'Last 1 hr' preset button");

        // Verify "Last 1 hr" is now highlighted
        const last1hrActive = await page.evaluate(() => {
            const buttons = document.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Last 1 hr") {
                    const bg = btn.style.background || btn.style.backgroundColor || "";
                    return (
                        bg.includes("accent") ||
                        bg.includes("4b8df7") ||
                        bg.includes("75, 141, 247")
                    );
                }
            }
            return false;
        });
        assert(last1hrActive, "'Last 1 hr' button is highlighted after click");

        // Click again to deselect
        const deselected = await page.evaluate(() => {
            const buttons = document.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Last 1 hr") {
                    btn.click();
                    return true;
                }
            }
            return false;
        });
        await page.waitForTimeout(500);

        const last1hrDeselected = await page.evaluate(() => {
            const buttons = document.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Last 1 hr") {
                    const bg = btn.style.background || btn.style.backgroundColor || "";
                    // Should NOT be highlighted
                    return !(
                        bg.includes("accent") ||
                        bg.includes("4b8df7") ||
                        bg.includes("75, 141, 247")
                    );
                }
            }
            return false;
        });
        assert(
            deselected && last1hrDeselected,
            "Clicking active preset again deselects it",
        );

        // ------------------------------------------------------------------
        // 4. Custom Datetime Picker
        // ------------------------------------------------------------------
        console.log("\n--- Custom Datetime Picker ---");

        const datetimeInputs = await page.evaluate(() => {
            const inputs = document.querySelectorAll(
                'input[type="datetime-local"]',
            );
            return inputs.length;
        });
        assert(
            datetimeInputs === 2,
            `Two datetime-local inputs render (found ${datetimeInputs})`,
        );

        // Check "From" and "To" labels exist near the inputs
        const hasFromToLabels = await page.evaluate(() => {
            const labels = document.querySelectorAll(
                'label, span, [data-testid="time-from-label"], [data-testid="time-until-label"]',
            );
            let hasFrom = false;
            let hasTo = false;
            for (const el of labels) {
                const text = el.textContent.trim().toLowerCase();
                if (text === "from" || text === "from:") hasFrom = true;
                if (text === "to" || text === "to:") hasTo = true;
            }
            return hasFrom && hasTo;
        });
        assert(hasFromToLabels, "From and To labels exist near datetime inputs");

        // Validate From < To: set From > To and check for error indication
        const fromToValidation = await page.evaluate(() => {
            const inputs = document.querySelectorAll(
                'input[type="datetime-local"]',
            );
            if (inputs.length < 2) return "no_inputs";

            // Set From to a later date than To
            const fromInput = inputs[0];
            const toInput = inputs[1];

            // Set To first, then From to a later time
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype,
                "value",
            ).set;

            nativeInputValueSetter.call(toInput, "2024-01-15T10:00");
            toInput.dispatchEvent(new Event("input", { bubbles: true }));
            toInput.dispatchEvent(new Event("change", { bubbles: true }));

            nativeInputValueSetter.call(fromInput, "2024-01-15T12:00");
            fromInput.dispatchEvent(new Event("input", { bubbles: true }));
            fromInput.dispatchEvent(new Event("change", { bubbles: true }));

            return "set";
        });
        await page.waitForTimeout(500);

        // Check for visual error indicator (red border, error text, etc.)
        if (fromToValidation === "set") {
            const hasValidationError = await page.evaluate(() => {
                // Look for error indicators: red border on input,
                // error message text, or disabled state
                const inputs = document.querySelectorAll(
                    'input[type="datetime-local"]',
                );
                for (const input of inputs) {
                    const style = input.style;
                    if (
                        style.borderColor === "var(--color-error, #f55353)" ||
                        style.borderColor.includes("f55353") ||
                        style.border.includes("error")
                    ) {
                        return true;
                    }
                }
                // Also check for error message text
                const errorEls = document.querySelectorAll(
                    '[style*="color: var(--color-error"]',
                );
                return errorEls.length > 0;
            });
            assert(
                hasValidationError,
                "From > To shows validation error indicator",
            );
        } else {
            skip("From > To validation", "Could not set datetime inputs");
        }

        // ------------------------------------------------------------------
        // 5. Time Filter + Severity Filter Composition
        // ------------------------------------------------------------------
        console.log("\n--- Filter Composition ---");

        // Activate a preset
        await page.evaluate(() => {
            const buttons = document.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Last 10 min") {
                    btn.click();
                    return;
                }
            }
        });
        await page.waitForTimeout(500);

        // Severity checkboxes should still be present and functional
        const severityStillPresent = await page.evaluate(() => {
            const labels = document.querySelectorAll("label");
            let count = 0;
            for (const label of labels) {
                const text = label.textContent.trim();
                if (
                    ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"].includes(text)
                ) {
                    const cb = label.querySelector('input[type="checkbox"]');
                    if (cb) count++;
                }
            }
            return count === 5;
        });
        assert(
            severityStillPresent,
            "Severity filters still present with time filter active",
        );

        // ------------------------------------------------------------------
        // 6. File Mode — Time Filter on File List
        // ------------------------------------------------------------------
        console.log("\n--- File Mode Time Filter ---");

        // Switch to Files mode
        const switchedToFiles = await page.evaluate(() => {
            const buttons = document.querySelectorAll("button");
            for (const btn of buttons) {
                if (btn.textContent.trim() === "Files") {
                    btn.click();
                    return true;
                }
            }
            return false;
        });
        await page.waitForTimeout(2000);

        if (switchedToFiles) {
            // Time preset buttons should still be visible in file mode
            const presetsInFileMode = await page.evaluate(() => {
                const buttons = document.querySelectorAll("button");
                let count = 0;
                for (const btn of buttons) {
                    const text = btn.textContent.trim();
                    if (
                        text === "Last 10 min" ||
                        text === "Last 1 hr" ||
                        text === "Last 6 hr" ||
                        text === "Last 24 hr"
                    ) {
                        count++;
                    }
                }
                return count;
            });
            assert(
                presetsInFileMode === 4,
                `Time presets visible in file mode (found ${presetsInFileMode})`,
            );
        } else {
            skip("File mode time filter", "Could not switch to Files mode");
        }
    } catch (err) {
        console.error(`\n  ERROR: ${err.message}`);
        failed++;
        failures.push(`Uncaught: ${err.message}`);
    } finally {
        await browser.close();
    }

    printSummary();
}

function printSummary() {
    console.log("\n=== Summary ===");
    console.log(`  Passed:  ${passed}`);
    console.log(`  Failed:  ${failed}`);
    console.log(`  Skipped: ${skipped}`);
    if (failures.length > 0) {
        console.log("\n  Failures:");
        for (const f of failures) {
            console.log(`    - ${f}`);
        }
    }
    console.log();
    process.exit(failed > 0 ? 1 : 0);
}

run().catch((err) => {
    console.error(`Fatal: ${err.message}`);
    process.exit(2);
});
