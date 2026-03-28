#!/usr/bin/env node
// Verify 3-column layouts for Setting, Test, Encoder tabs + connection bar Reboot button.
// Run: node web_dashboard/e2e_tests/verify_3col_layout_e2e.mjs
// Dashboard must be running on http://127.0.0.1:8090

import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8090";
let passed = 0;
let failed = 0;
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

async function switchTab(page, tabName) {
    const labelMap = {
        setting: "Setting",
        encoder: "Encoder",
        product: "Product",
        test: "Test",
        pid: "PID Tuning",
    };
    const label = labelMap[tabName] || tabName;
    await page.evaluate((lbl) => {
        const tabs = document.querySelectorAll(".motor-tab");
        for (const t of tabs) {
            if (t.textContent.trim() === lbl) {
                t.click();
                return;
            }
        }
    }, label);
    await page.waitForTimeout(300);
}

async function waitForPreactContent(page, sectionId, timeoutMs = 5000) {
    try {
        await page.waitForFunction(
            (id) => {
                const container = document.getElementById(`${id}-section-preact`);
                return container && container.children.length > 0;
            },
            sectionId,
            { timeout: timeoutMs },
        );
    } catch (_e) {
        // content may already be visible
    }
}

(async () => {
    console.log("3-Column Layout Verification");
    console.log("============================\n");

    const browser = await chromium.launch({ headless: true });
    // Use 1920x1080 to ensure 3-col layouts are not collapsed by responsive breakpoints
    const page = await browser.newPage({
        viewport: { width: 1920, height: 1080 },
    });

    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));

    try {
        await page.goto(BASE, { waitUntil: "networkidle", timeout: 10000 });

        // Navigate to Motor Config
        await page.click('a[title="Motor Config"]');
        await waitForPreactContent(page, "motor-config");
        await page.waitForTimeout(500);

        // ================================================================
        // 1. Connection Bar — Reboot button + element order
        // ================================================================
        console.log("[1] Connection Bar");

        const connBar = await page.evaluate(() => {
            const bar = document.querySelector(".pid-motor-selector");
            if (!bar) return null;

            const buttons = [...bar.querySelectorAll("button")];
            const btnTexts = buttons.map((b) => b.textContent.trim());

            // Check Reboot button exists
            const rebootBtn = buttons.find((b) => b.textContent.trim() === "Motor Reboot");
            const motorOffBtn = buttons.find((b) => b.textContent.trim() === "Motor Off");
            const motorOnBtn = buttons.find((b) => b.textContent.trim() === "Motor On");

            // Check order: Motor Off before Motor On before Reboot
            const offIdx = btnTexts.indexOf("Motor Off");
            const onIdx = btnTexts.indexOf("Motor On");
            const rebootIdx = btnTexts.indexOf("Motor Reboot");

            // Check dividers (vertical bars)
            const dividers = [...bar.querySelectorAll("span")].filter(
                (s) => s.style.width === "1px" && s.style.height === "20px",
            );

            // Check transport selector exists
            const transportSelect = bar.querySelector("select.pid-select");

            // Check comm error
            const commSpan = [...bar.querySelectorAll("span")].find((s) =>
                s.textContent.includes("Comm Error"),
            );

            // Check Transport+badge appears before CONNECT button using DOM position
            const transportRect = transportSelect?.getBoundingClientRect();
            const connectBtn = buttons.find(
                (b) => b.textContent.trim() === "CONNECT" || b.textContent.trim() === "DISCONNECT",
            );
            const connectRect = connectBtn?.getBoundingClientRect();
            // Transport should be to the left of CONNECT (lower x position in LTR layout)
            const transportBeforeConnect =
                transportRect && connectRect && transportRect.left < connectRect.left;

            return {
                hasReboot: !!rebootBtn,
                hasMotorOff: !!motorOffBtn,
                hasMotorOn: !!motorOnBtn,
                orderCorrect: offIdx < onIdx && onIdx < rebootIdx,
                rebootBgColor: rebootBtn ? getComputedStyle(rebootBtn).backgroundColor : null,
                dividerCount: dividers.length,
                hasTransport: !!transportSelect,
                hasCommError: !!commSpan,
                allBtnTexts: btnTexts,
                transportBeforeConnect,
            };
        });

        assert(connBar !== null, "Connection bar exists");
        assert(connBar?.hasReboot, "Reboot button in connection bar");
        assert(connBar?.hasMotorOff, "Motor Off button in connection bar");
        assert(connBar?.hasMotorOn, "Motor On button in connection bar");
        assert(connBar?.orderCorrect, "Button order: Motor Off < Motor On < Reboot");
        assert(connBar?.dividerCount >= 1, "At least 1 divider in connection bar");
        assert(connBar?.hasTransport, "Transport selector in connection bar");
        assert(connBar?.transportBeforeConnect, "Transport selector appears before CONNECT button");
        assert(connBar?.hasCommError, "Comm Error counter in connection bar");

        // ================================================================
        // 2. Setting Tab — 3-column layout
        // ================================================================
        console.log("\n[2] Setting Tab — 3-column layout");

        await switchTab(page, "setting");

        const settingLayout = await page.evaluate(() => {
            const grid = document.querySelector(".setting-tab-grid");
            if (!grid) return null;

            const cs = getComputedStyle(grid);
            const cols = cs.gridTemplateColumns;
            const children = [...grid.children];

            // Check for setting-action-col (3rd column)
            const actionCol = grid.querySelector(".setting-action-col");

            // Get positions of children to verify 3 columns
            const positions = children.map((c) => ({
                left: c.offsetLeft,
                width: c.offsetWidth,
                top: c.offsetTop,
            }));

            // Check action buttons exist
            const actionBtns = actionCol
                ? [...actionCol.querySelectorAll(".setting-action-btns button")].map((b) => b.textContent.trim())
                : [];

            // Check PID Setting is in col 3
            const hasPIDInCol3 = actionCol
                ? actionCol.textContent.includes("PID Setting")
                : false;

            return {
                childCount: children.length,
                gridCols: cols,
                hasActionCol: !!actionCol,
                actionBtns,
                hasPIDInCol3,
                positions,
                // Check that col3 is to the right of col2
                threeColsVisible:
                    children.length >= 3 &&
                    children[2].offsetLeft > children[1].offsetLeft &&
                    children[1].offsetLeft > children[0].offsetLeft,
            };
        });

        assert(settingLayout !== null, "Setting tab grid exists");
        assert(settingLayout?.childCount === 3, `Setting tab has 3 children (got ${settingLayout?.childCount})`);
        assert(settingLayout?.hasActionCol, "Setting tab has action column (.setting-action-col)");
        assert(settingLayout?.threeColsVisible, "Setting tab: 3 columns side-by-side");
        assert(
            settingLayout?.actionBtns?.includes("Read Setting"),
            "Action col has Read Setting button",
        );
        assert(
            settingLayout?.actionBtns?.includes("Save Setting"),
            "Action col has Save Setting button",
        );
        assert(
            settingLayout?.actionBtns?.includes("Reset Setting"),
            "Action col has Reset Setting button",
        );
        assert(settingLayout?.hasPIDInCol3, "PID Setting is in column 3");

        // Reboot should NOT be in setting tab anymore
        const rebootInSetting = await page.evaluate(() => {
            const grid = document.querySelector(".setting-tab-grid");
            if (!grid) return false;
            const btns = [...grid.querySelectorAll("button")];
            return btns.some((b) => b.textContent.trim().toLowerCase().includes("reboot"));
        });
        assert(!rebootInSetting, "Reboot button NOT in Setting tab (moved to connection bar)");

        // ================================================================
        // 3. Test Tab — 3-column layout
        // ================================================================
        console.log("\n[3] Test Tab — 3-column layout");

        await switchTab(page, "test");

        const testLayout = await page.evaluate(() => {
            const layout = document.querySelector(".test-tab-layout");
            if (!layout) return null;

            const cs = getComputedStyle(layout);
            const cols = cs.gridTemplateColumns;
            const children = [...layout.querySelectorAll(":scope > .test-tab-column")];

            const positions = children.map((c) => ({
                left: c.offsetLeft,
                width: c.offsetWidth,
            }));

            // Check for serial monitor in 3rd column
            const serialMonitor = children[2]?.querySelector(".serial-monitor");

            // Check no bottom bar
            const bottomBar = document.querySelector(".test-bottom-bar");

            return {
                colCount: children.length,
                gridCols: cols,
                threeColsVisible:
                    children.length >= 3 &&
                    children[2].offsetLeft > children[1].offsetLeft &&
                    children[1].offsetLeft > children[0].offsetLeft,
                hasSerialInCol3: !!serialMonitor,
                hasBottomBar: !!bottomBar,
                positions,
            };
        });

        assert(testLayout !== null, "Test tab layout exists");
        assert(testLayout?.colCount === 3, `Test tab has 3 columns (got ${testLayout?.colCount})`);
        assert(testLayout?.threeColsVisible, "Test tab: 3 columns side-by-side");
        assert(testLayout?.hasSerialInCol3, "Serial Monitor in 3rd column");

        // Check TestStatePanel content in column 2
        const testCol2 = await page.evaluate(() => {
            const layout = document.querySelector(".test-tab-layout");
            if (!layout) return null;
            const cols = [...layout.querySelectorAll(":scope > .test-tab-column")];
            if (cols.length < 2) return null;
            const col2 = cols[1];
            const text = col2.textContent;
            return {
                hasState: text.includes("State") || text.includes("Bus Voltage"),
                hasAngle: text.includes("Angle") || text.includes("Multi Loop"),
                hasBrake: text.includes("Brake"),
            };
        });

        assert(testCol2?.hasState, "Test col 2 has State section");
        assert(testCol2?.hasAngle, "Test col 2 has Angle section");
        assert(testCol2?.hasBrake, "Test col 2 has Brake section");

        // ================================================================
        // 4. Encoder Tab — 3-column layout
        // ================================================================
        console.log("\n[4] Encoder Tab — 3-column layout");

        await switchTab(page, "encoder");

        const encoderLayout = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            if (!layout) return null;

            const cs = getComputedStyle(layout);
            const cols = cs.gridTemplateColumns;
            const children = [...layout.children].filter(
                (c) => c.nodeType === 1 && getComputedStyle(c).display !== "none",
            );

            // Filter out the dialog element and comparison (conditional)
            const mainChildren = children.filter(
                (c) =>
                    !c.classList.contains("encoder-comparison") &&
                    c.tagName !== "DIALOG" &&
                    !c.querySelector("dialog"),
            );

            const positions = mainChildren.map((c) => ({
                left: c.offsetLeft,
                width: c.offsetWidth,
                tag: c.tagName,
                cls: c.className,
            }));

            // Col 1 should have "Motor / Encoder Setting"
            const col1Text = mainChildren[0]?.textContent || "";
            // Col 2 should have "Reducer / Encoder Setting"
            const col2Text = mainChildren[1]?.textContent || "";
            // Col 3 should have Read/Save/Write Zero buttons
            const col3Btns = mainChildren[2]
                ? [...mainChildren[2].querySelectorAll("button")].map((b) => b.textContent.trim())
                : [];

            return {
                childCount: mainChildren.length,
                gridCols: cols,
                hasMotorEncoder: col1Text.includes("Motor / Encoder"),
                hasReducerEncoder: col2Text.includes("Reducer / Encoder"),
                col3Btns,
                threeColsVisible:
                    mainChildren.length >= 3 &&
                    mainChildren[2].offsetLeft > mainChildren[1].offsetLeft &&
                    mainChildren[1].offsetLeft > mainChildren[0].offsetLeft,
                positions,
            };
        });

        assert(encoderLayout !== null, "Encoder layout exists");
        assert(encoderLayout?.childCount >= 3, `Encoder has 3+ children (got ${encoderLayout?.childCount})`);
        assert(encoderLayout?.hasMotorEncoder, "Encoder col 1: Motor / Encoder Setting");
        assert(encoderLayout?.hasReducerEncoder, "Encoder col 2: Reducer / Encoder Setting");
        assert(encoderLayout?.threeColsVisible, "Encoder tab: 3 columns side-by-side");
        assert(
            encoderLayout?.col3Btns?.some((t) => t === "Read"),
            "Encoder col 3 has Read button",
        );
        assert(
            encoderLayout?.col3Btns?.some((t) => t === "Save"),
            "Encoder col 3 has Save button",
        );
        assert(
            encoderLayout?.col3Btns?.some((t) => t.includes("Write Zero")),
            "Encoder col 3 has Write Zero button",
        );

        // ================================================================
        // 5. PID Setting — table layout
        // ================================================================
        console.log("\n[5] PID Setting — table layout");

        await switchTab(page, "setting");

        const pidLayout = await page.evaluate(() => {
            // Find the PID Setting section (uses setting-grid, not table)
            const headers = [...document.querySelectorAll("h3")];
            const pidH3 = headers.find((h) => h.textContent.trim() === "PID Setting");
            if (!pidH3) return null;
            // Walk up to find the container that holds both the header and the grid
            let container = pidH3.parentElement;
            while (container && !container.querySelector(".setting-grid")) {
                container = container.parentElement;
            }
            if (!container) return null;

            // PID uses a CSS grid with columns: label | Kp | Ki | SET RAM
            const grid = container.querySelector(".setting-grid");
            const inputs = grid ? [...grid.querySelectorAll('input[type="number"]')] : [];
            const setButtons = grid ? [...grid.querySelectorAll("button")].filter(b => b.textContent.trim() === "SET RAM") : [];
            const labels = grid ? [...grid.querySelectorAll(".motor-setting-label")] : [];

            return {
                hasGrid: !!grid,
                inputCount: inputs.length,
                setButtonCount: setButtons.length,
                labelCount: labels.length,
                labelTexts: labels.map(l => l.textContent.trim()),
            };
        });

        assert(pidLayout !== null, "PID Setting section exists");
        assert(pidLayout?.hasGrid, "PID Setting uses grid layout");
        assert(pidLayout?.inputCount === 6, `PID has 6 inputs (3 Kp + 3 Ki) (got ${pidLayout?.inputCount})`);
        assert(pidLayout?.setButtonCount === 3, `PID has 3 SET RAM buttons (got ${pidLayout?.setButtonCount})`);

        // ================================================================
        // 5b. Protection Setting — dropdown enum for each parameter
        // ================================================================
        console.log("\n[5b] Protection Setting — dropdown enums");

        const protLayout = await page.evaluate(() => {
            const headers = [...document.querySelectorAll("h3")];
            const protH3 = headers.find((h) => h.textContent.trim() === "Protection Setting");
            if (!protH3) return null;
            const container = protH3.closest(".protection-settings-card");
            if (!container) return null;

            const selects = [...container.querySelectorAll("select")];
            const numericInputs = [...container.querySelectorAll('input[type="number"]')];

            // Check that selects have the right options
            const selectOptions = selects.length > 0
                ? [...selects[0].querySelectorAll("option")].map(o => o.textContent.trim())
                : [];

            return {
                selectCount: selects.length,
                numericCount: numericInputs.length,
                selectOptions,
            };
        });

        // 8 params have dropdowns (all except Over Current Time which is numeric only)
        assert(protLayout?.selectCount === 8, `Protection has 8 dropdowns (got ${protLayout?.selectCount})`);
        // 8 params have numeric inputs (all except Short Circuit which is dropdown only)
        assert(protLayout?.numericCount === 8, `Protection has 8 numeric inputs (got ${protLayout?.numericCount})`);
        // Check dropdown options include the full enum
        assert(
            protLayout?.selectOptions?.includes("Enable (recoverable)") &&
            protLayout?.selectOptions?.includes("Enable (not recoverable)") &&
            protLayout?.selectOptions?.includes("Disable"),
            "Protection dropdowns have full enum options",
        );

        // ================================================================
        // 6. Setting tab 3-col at smaller viewport (1024px laptop width)
        // ================================================================
        console.log("\n[6] Setting Tab — 3-col at 1024px viewport");

        await page.setViewportSize({ width: 1024, height: 768 });
        await page.waitForTimeout(300);
        await switchTab(page, "setting");

        const settingSmall = await page.evaluate(() => {
            const grid = document.querySelector(".setting-tab-grid");
            if (!grid) return null;
            const cs = getComputedStyle(grid);
            const children = [...grid.children];
            return {
                gridCols: cs.gridTemplateColumns,
                threeColsVisible:
                    children.length >= 3 &&
                    children[2].offsetLeft > children[1].offsetLeft &&
                    children[1].offsetLeft > children[0].offsetLeft,
            };
        });

        assert(
            settingSmall?.threeColsVisible,
            "Setting tab: still 3 columns at 1024px viewport",
        );

        // Also test at 800px — should collapse to single column (responsive breakpoint at 900px)
        await page.setViewportSize({ width: 800, height: 900 });
        await page.waitForTimeout(300);
        await switchTab(page, "setting");

        const settingTiny = await page.evaluate(() => {
            const grid = document.querySelector(".setting-tab-grid");
            if (!grid) return null;
            const cs = getComputedStyle(grid);
            const children = [...grid.children];
            // At 800px, columns should be stacked (single column)
            const allSameLeft = children.every(c => c.offsetLeft === children[0].offsetLeft);
            return {
                gridCols: cs.gridTemplateColumns,
                stackedSingleCol: allSameLeft,
            };
        });

        assert(
            settingTiny?.stackedSingleCol,
            "Setting tab: collapses to single column at 800px viewport",
        );

        // Restore viewport
        await page.setViewportSize({ width: 1920, height: 1080 });
        await page.waitForTimeout(200);

        // ================================================================
        // 7. JS Errors check
        // ================================================================
        console.log("\n[7] JavaScript Errors");
        assert(jsErrors.length === 0, `No JS errors (got ${jsErrors.length}: ${jsErrors.join("; ")})`);

    } catch (e) {
        console.error("FATAL:", e.message);
        failed++;
        failures.push("FATAL: " + e.message);
    } finally {
        await browser.close();
    }

    console.log(`\n${"=".repeat(40)}`);
    console.log(`PASS: ${passed}  FAIL: ${failed}`);
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    process.exit(failed > 0 ? 1 : 0);
})();
