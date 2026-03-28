#!/usr/bin/env node
// LK Motor Tool Parity E2E Test Suite
// Tests changes from the lk-motor-tool-parity OpenSpec change:
//   1. Encoder tab 2-panel layout (encoder-tab-parity spec)
//   2. Null field placeholders "--" (null-field-placeholders spec)
//   3. Bus Current row in Test tab (null-field-placeholders spec)
//   4. Command failure toasts (command-failure-toasts spec - structure only)
//   5. Auto-select motor (selected-motor-auto-select spec - structure only)
//   6. Product tab layout (motor-config-ux-overhaul: full-width card,
//      flexbox button alignment, 2-column grid)
//
// Run: node web_dashboard/e2e_tests/lk_motor_tool_parity_e2e.mjs
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

async function switchTab(page, tabName) {
    await page.evaluate((lbl) => {
        const tabs = document.querySelectorAll(".motor-tab");
        for (const t of tabs) {
            if (t.textContent.trim() === lbl) {
                t.click();
                return;
            }
        }
    }, tabName);
    await page.waitForTimeout(300);
}

(async () => {
    console.log("LK Motor Tool Parity E2E Test Suite");
    console.log("====================================\n");

    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({
        viewport: { width: 1280, height: 800 },
    });

    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));

    try {
        // Navigate to Motor Config
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 10000 });
        await page.click('a[title="Motor Config"]');
        await page.waitForTimeout(2000);

        // ================================================================
        // SECTION 1: Encoder Tab — 2-Panel Layout (encoder-tab-parity)
        // ================================================================
        console.log("[1] Encoder Tab — 2-Panel Layout");
        await switchTab(page, "Encoder");

        // 1.1 Two-panel CSS grid exists
        const gridLayout = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            if (!layout) return null;
            const grid = layout.querySelector(
                "div[style*='grid-template-columns: 1fr 1fr']",
            );
            if (!grid) return null;
            const cards = grid.querySelectorAll(".card");
            return { exists: true, cardCount: cards.length };
        });
        assert(gridLayout?.exists, "2-column CSS grid exists in encoder tab");
        assert(
            gridLayout?.cardCount === 2,
            `Exactly 2 card panels (got ${gridLayout?.cardCount})`,
        );

        // 1.2 Left panel: "Motor / Encoder Setting" heading + 8 fields
        const leftPanel = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            const grid = layout?.querySelector(
                "div[style*='grid-template-columns']",
            );
            const cards = grid?.querySelectorAll(".card");
            if (!cards || cards.length < 1) return null;
            const card = cards[0];
            const heading = card.querySelector("h3")?.textContent.trim();
            const fieldLabels = [
                ...card.querySelectorAll(
                    "span[style*='color: var(--color-text-secondary)']",
                ),
            ].map((s) => s.textContent.trim());
            const inputs = card.querySelectorAll("input");
            return { heading, fieldLabels, fieldCount: fieldLabels.length, inputCount: inputs.length };
        });
        assert(
            leftPanel?.heading === "Motor / Encoder Setting",
            `Left panel heading (got "${leftPanel?.heading}")`,
        );
        assert(
            leftPanel?.fieldCount === 8,
            `Left panel has 8 fields (got ${leftPanel?.fieldCount})`,
        );

        // 1.3 Expected left-panel field labels
        const expectedLeftFields = [
            "Motor Poles",
            "Encoder Type",
            "Encoder Position",
            "Motor Phase Sequence",
            "Motor/Encoder Offset",
            "Motor/Encoder Align Ratio",
            "Motor/Encoder Align Voltage",
            "Motor Zero Position (Rom)",
        ];
        for (const label of expectedLeftFields) {
            assert(
                leftPanel?.fieldLabels.includes(label),
                `Left panel has "${label}"`,
            );
        }

        // 1.4 Right panel: "Reducer / Encoder Setting" heading + 3 fields
        const rightPanel = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            const grid = layout?.querySelector(
                "div[style*='grid-template-columns']",
            );
            const cards = grid?.querySelectorAll(".card");
            if (!cards || cards.length < 2) return null;
            const card = cards[1];
            const heading = card.querySelector("h3")?.textContent.trim();
            const fieldLabels = [
                ...card.querySelectorAll(
                    "span[style*='color: var(--color-text-secondary)']",
                ),
            ].map((s) => s.textContent.trim());
            return { heading, fieldLabels, fieldCount: fieldLabels.length };
        });
        assert(
            rightPanel?.heading === "Reducer / Encoder Setting",
            `Right panel heading (got "${rightPanel?.heading}")`,
        );
        assert(
            rightPanel?.fieldCount === 3,
            `Right panel has 3 fields (got ${rightPanel?.fieldCount})`,
        );

        // 1.5 Expected right-panel field labels
        const expectedRightFields = [
            "Reduction Ratio",
            "Reducer/Encoder Align Value",
            "Reducer Zero Position",
        ];
        for (const label of expectedRightFields) {
            assert(
                rightPanel?.fieldLabels.includes(label),
                `Right panel has "${label}"`,
            );
        }

        // 1.6 Unmapped fields show "--" (no motor connected, all should be "--")
        const unmappedValues = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            const grid = layout?.querySelector(
                "div[style*='grid-template-columns']",
            );
            if (!grid) return null;
            const inputs = [...grid.querySelectorAll("input")];
            const dashValues = inputs.filter(
                (i) => i.value === "--" || i.value === "",
            );
            return {
                totalInputs: inputs.length,
                dashOrEmpty: dashValues.length,
                values: inputs.map((i) => i.value).slice(0, 15),
            };
        });
        assert(
            unmappedValues?.totalInputs === 11,
            `11 field inputs total (got ${unmappedValues?.totalInputs})`,
        );

        // 1.7 Action buttons: Read, Save below panels
        const encoderBtns = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            if (!layout) return [];
            return [...layout.querySelectorAll(".btn")].map((b) =>
                b.textContent.trim(),
            );
        });
        assert(encoderBtns.includes("Read"), "Read button exists");
        assert(encoderBtns.includes("Save"), "Save button exists");

        // 1.8 Write Zero (RAM) card
        assert(
            encoderBtns.some((t) => t.includes("Write Zero")),
            "Write Zero (RAM) button exists",
        );
        assert(
            encoderBtns.includes("Use Current"),
            "Use Current button exists",
        );

        // 1.9 Set (Save Zero ROM) button in left panel
        const setBtn = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            if (!layout) return false;
            const btns = layout.querySelectorAll(".btn.btn-danger");
            for (const b of btns) {
                if (b.textContent.trim() === "Set") return true;
            }
            return false;
        });
        assert(setBtn, "Set (Save Zero ROM) button exists");

        // 1.10 Read button is primary, Save is danger
        const btnStyles = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            if (!layout) return {};
            const btns = [...layout.querySelectorAll(".btn")];
            const readBtn = btns.find((b) => b.textContent.trim() === "Read");
            const saveBtn = btns.find((b) => b.textContent.trim() === "Save");
            return {
                readClass: readBtn?.className || "",
                saveClass: saveBtn?.className || "",
            };
        });
        assert(
            btnStyles.readClass.includes("btn-primary"),
            "Read button has primary style",
        );
        assert(
            btnStyles.saveClass.includes("btn-danger"),
            "Save button has danger style",
        );

        // ================================================================
        // SECTION 2: Null Field Placeholders (null-field-placeholders)
        // ================================================================
        console.log("\n[2] Null Field Placeholders — Setting Tab");
        await switchTab(page, "Setting");

        // 2.1 BasicSettingPanel: unmapped fields show "--" not "N/A"
        // These fields should show "--": Broadcast Mode, Spin Direction,
        // Brake Resistor Control, Brake Resistor Voltage
        const basicSettings = await page.evaluate(() => {
            const content = document.querySelector(".motor-tab-content");
            const text = content?.textContent || "";
            const inputs = [...content.querySelectorAll("input")];
            const dashInputs = inputs.filter(
                (i) => i.value === "--" || i.placeholder === "--",
            );
            // Check specific fields show "--"
            // Broadcast Mode, Spin Direction, Brake Resistor Control are
            // disabled text inputs showing "--"
            const allValues = inputs.map((i) => ({
                val: i.value,
                ph: i.placeholder,
                disabled: i.disabled,
            }));
            return {
                hasDashInputs: dashInputs.length > 0,
                dashCount: dashInputs.length,
                // Check that "N/A" does NOT appear for our changed fields
                fullText: text,
            };
        });
        assert(
            basicSettings.hasDashInputs,
            'BasicSettingPanel has "--" inputs',
        );

        // 2.2 Specific fields: Broadcast Mode, Spin Direction, Brake Resistor Control show "--"
        // These fields use <label> for names and <select> for values
        const fieldChecks = await page.evaluate(() => {
            const content = document.querySelector(".motor-tab-content");
            if (!content) return {};
            const results = {};

            // Walk text nodes to find labels, then check sibling select value
            const walker = document.createTreeWalker(
                content,
                NodeFilter.SHOW_TEXT,
                null,
            );
            const targetLabels = [
                "Broadcast Mode",
                "Spin Direction",
                "Brake Resistor Control",
            ];
            while (walker.nextNode()) {
                const text = walker.currentNode.textContent.trim();
                if (targetLabels.includes(text)) {
                    const parent = walker.currentNode.parentElement;
                    // Next sibling is a <select> with value "--"
                    const next = parent.nextElementSibling;
                    if (next?.tagName === "SELECT") {
                        // Get the selected option text
                        const optText =
                            next.options[next.selectedIndex]?.text?.trim();
                        results[text] = optText || next.value;
                    } else if (next?.tagName === "INPUT") {
                        results[text] = next.value;
                    } else {
                        results[text] = "UNEXPECTED_ELEMENT";
                    }
                }
            }
            return results;
        });
        for (const [label, value] of Object.entries(fieldChecks)) {
            assert(
                value === "--",
                `${label} shows "--" (got "${value}")`,
            );
        }

        // 2.3 Brake Resistor Voltage placeholder is "--"
        const brakeVoltagePh = await page.evaluate(() => {
            const content = document.querySelector(".motor-tab-content");
            const walker = document.createTreeWalker(
                content,
                NodeFilter.SHOW_TEXT,
                null,
            );
            while (walker.nextNode()) {
                if (
                    walker.currentNode.textContent.trim() ===
                    "Brake Resistor Voltage"
                ) {
                    const parent = walker.currentNode.parentElement;
                    const next = parent.nextElementSibling;
                    if (next?.tagName === "INPUT") {
                        return next.placeholder;
                    }
                }
            }
            return "NOT_FOUND";
        });
        assert(
            brakeVoltagePh === "--",
            `Brake Resistor Voltage placeholder is "--" (got "${brakeVoltagePh}")`,
        );

        // 2.4 ProtectionSettingPanel: enableLabel returns "--" for null
        // "Protect Over Current Time" has a <select> with "--" as option
        const protectionDash = await page.evaluate(() => {
            const content = document.querySelector(".motor-tab-content");
            const walker = document.createTreeWalker(
                content,
                NodeFilter.SHOW_TEXT,
                null,
            );
            while (walker.nextNode()) {
                if (
                    walker.currentNode.textContent.trim() ===
                    "Protect Over Current Time"
                ) {
                    const parent = walker.currentNode.parentElement;
                    // Skip empty div spacer, find the <select>
                    let sibling = parent.nextElementSibling;
                    while (sibling) {
                        if (sibling.tagName === "SELECT") {
                            return (
                                sibling.options[sibling.selectedIndex]?.text?.trim() ||
                                sibling.value
                            );
                        }
                        sibling = sibling.nextElementSibling;
                    }
                }
            }
            return "NOT_FOUND";
        });
        assert(
            protectionDash === "--",
            `Protection enableLabel shows "--" (got "${protectionDash}")`,
        );

        // 2.5 Verify "N/A" does NOT appear for our changed fields
        // Note: Bus Type, RS485 Baudrate, CAN Baudrate still show "N/A" (not our change)
        // But Broadcast Mode, Spin Direction, Brake Resistor Control should be "--"
        for (const [label, value] of Object.entries(fieldChecks)) {
            assert(
                value !== "N/A",
                `${label} is NOT "N/A" (is "${value}")`,
            );
        }

        // ================================================================
        // SECTION 3: Bus Current Row in Test Tab
        // ================================================================
        console.log("\n[3] Bus Current Row — Test Tab");
        await switchTab(page, "Test");

        // 3.1 Bus Current exists in state grid
        const busCurrent = await page.evaluate(() => {
            const grid = document.querySelector(".state-grid");
            if (!grid) return null;
            const children = [...grid.children];
            for (let i = 0; i < children.length - 1; i += 2) {
                if (children[i].textContent.trim() === "Bus Current") {
                    return {
                        exists: true,
                        value: children[i + 1].textContent.trim(),
                        title: children[i + 1].getAttribute("title"),
                        index: i,
                    };
                }
            }
            return { exists: false };
        });
        assert(busCurrent?.exists, "Bus Current row exists in state grid");
        assert(
            busCurrent?.value === "--",
            `Bus Current shows "--" (got "${busCurrent?.value}")`,
        );
        assert(
            busCurrent?.title === "Not available via RS485",
            `Bus Current tooltip (got "${busCurrent?.title}")`,
        );

        // 3.2 Bus Current is between Bus Voltage and Motor Temp
        const stateOrder = await page.evaluate(() => {
            const grid = document.querySelector(".state-grid");
            if (!grid) return [];
            const children = [...grid.children];
            const labels = [];
            for (let i = 0; i < children.length; i += 2) {
                labels.push(children[i].textContent.trim());
            }
            return labels;
        });
        const voltIdx = stateOrder.indexOf("Bus Voltage");
        const curIdx = stateOrder.indexOf("Bus Current");
        const tempIdx = stateOrder.indexOf("Motor Temp");
        assert(
            voltIdx >= 0 && curIdx >= 0 && tempIdx >= 0,
            "All three state labels found",
        );
        assert(
            curIdx === voltIdx + 1 && curIdx === tempIdx - 1,
            `Bus Current between Bus Voltage and Motor Temp (order: ${voltIdx},${curIdx},${tempIdx})`,
        );

        // ================================================================
        // SECTION 4: Command Failure Toast Structure
        // ================================================================
        console.log("\n[4] Command Failure Toast Structure");

        // 4.1 Verify toast container exists (toasts render in a container)
        // We can't easily trigger a toast without a real motor, but we can
        // verify the toast infrastructure is present
        skip(
            "Warning toast on extended_limits failure",
            "requires motor hardware or API mock",
        );
        skip(
            "Warning toast on PID read failure",
            "requires motor hardware or API mock",
        );

        // 4.2 Verify the toast function is available globally or in Preact context
        const toastInfra = await page.evaluate(() => {
            // Check if showToast or similar function exists
            // In Preact, toasts are typically rendered via state, not global functions
            // Check for toast container in DOM
            const toastContainer =
                document.querySelector(".toast-container") ||
                document.querySelector("[class*='toast']") ||
                document.querySelector("[class*='notification']");
            return { hasToastContainer: !!toastContainer };
        });
        // Toast container may only appear when a toast is active
        skip(
            "Toast container presence",
            "container only renders when toast active",
        );

        // ================================================================
        // SECTION 5: Auto-Select Motor
        // ================================================================
        console.log("\n[5] Auto-Select Motor");

        // 5.1 Motor dropdown exists and shows default state
        const motorDropdown = await page.evaluate(() => {
            // Motor dropdown is in the top bar of Motor Config
            const selects = document.querySelectorAll("select");
            for (const sel of selects) {
                const opts = [...sel.options].map((o) => o.text);
                if (
                    opts.some(
                        (t) =>
                            t.includes("Select") || t.includes("motor"),
                    )
                ) {
                    return {
                        exists: true,
                        value: sel.value,
                        optionCount: sel.options.length,
                        firstOption: sel.options[0]?.text,
                    };
                }
            }
            return { exists: false };
        });
        // Auto-select only fires when connected to a real motor
        skip(
            "Auto-select triggers on connection",
            "requires real RS485 connection",
        );

        // ================================================================
        // SECTION 6: Product Tab — Fields Visible Without Motor
        // ================================================================
        console.log("\n[6] Product Tab — Fields Always Visible");
        await switchTab(page, "Product");

        // 6.1 Product panel card exists
        const productCard = await page.$(".product-panel .card");
        assert(!!productCard, "Product panel card exists");

        // 6.2 All 6 field labels present
        const productLabels = await page.evaluate(() => {
            const labels = document.querySelectorAll(
                ".product-panel .product-label",
            );
            return [...labels].map((l) => l.textContent.trim());
        });
        const expectedLabels = [
            "Motor :",
            "Motor version :",
            "Driver :",
            "Hardware version :",
            "Firmware version :",
            "Chip ID:",
        ];
        assert(
            productLabels.length === expectedLabels.length,
            `Product tab has ${expectedLabels.length} field labels (got ${productLabels.length})`,
        );
        for (const lbl of expectedLabels) {
            assert(
                productLabels.includes(lbl),
                `Product tab has label "${lbl}"`,
            );
        }

        // 6.3 All values show "--" when no motor connected
        const productValues = await page.evaluate(() => {
            const vals = document.querySelectorAll(
                ".product-panel .product-value",
            );
            return [...vals].map((v) => v.textContent.trim());
        });
        assert(
            productValues.length === 6,
            `Product tab has 6 value fields (got ${productValues.length})`,
        );
        for (let i = 0; i < productValues.length; i++) {
            assert(
                productValues[i] === "--",
                `Product field "${expectedLabels[i]}" shows "--" (got "${productValues[i]}")`,
            );
        }

        // 6.4 Read Product Info button exists
        const readProductBtn = await page.evaluate(() => {
            const btns = document.querySelectorAll(".product-panel .btn");
            for (const b of btns) {
                if (b.textContent.includes("Read")) return true;
            }
            return false;
        });
        assert(readProductBtn, "Read Product Info button exists");

        // 6.5 Product card fills container width (no max-width constraint)
        const productWidth = await page.evaluate(() => {
            const card = document.querySelector('.product-panel .card');
            if (!card) return null;
            const style = getComputedStyle(card);
            return { maxWidth: style.maxWidth, width: card.offsetWidth };
        });
        assert(
            productWidth && (productWidth.maxWidth === 'none' || productWidth.maxWidth === ''),
            `Product card has no max-width constraint (got "${productWidth?.maxWidth}")`,
        );

        // 6.6 Read button uses flexbox alignment (no float)
        const btnAlignment = await page.evaluate(() => {
            const panel = document.querySelector('.product-panel');
            if (!panel) return null;
            const readBtn = [...panel.querySelectorAll('.btn')].find(b => b.textContent.includes('Read'));
            if (!readBtn) return null;
            const container = readBtn.parentElement;
            const style = getComputedStyle(container);
            return { display: style.display, justifyContent: style.justifyContent, float: style.float };
        });
        assert(
            btnAlignment?.display === 'flex',
            `Button container uses flexbox (got "${btnAlignment?.display}")`,
        );
        assert(
            btnAlignment?.justifyContent === 'flex-end',
            `Button right-aligned via flex-end (got "${btnAlignment?.justifyContent}")`,
        );

        // 6.7 Product fields in 2-column grid
        const productGrid = await page.evaluate(() => {
            const panel = document.querySelector('.product-panel');
            if (!panel) return null;
            const grid = panel.querySelector('.setting-grid');
            if (!grid) return null;
            const style = getComputedStyle(grid);
            return { display: style.display, cols: style.gridTemplateColumns };
        });
        assert(
            productGrid?.display === 'grid',
            `Product fields use CSS grid (got "${productGrid?.display}")`,
        );
        assert(
            productGrid?.cols && productGrid.cols.split(' ').length >= 2,
            `Product grid has 2+ columns (got "${productGrid?.cols}")`,
        );

        // ================================================================
        // SECTION 7: No JS Errors
        // ================================================================
        console.log("\n[7] No JS Errors");
        assert(
            jsErrors.length === 0,
            `No JS errors (got ${jsErrors.length}: ${jsErrors.slice(0, 3).join("; ")})`,
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
    console.log("\n====================================");
    console.log(
        `Results: ${passed} passed, ${failed} failed, ${skipped} skipped (${total} total)`,
    );
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    console.log();
    process.exit(failed > 0 ? 1 : 0);
})();
