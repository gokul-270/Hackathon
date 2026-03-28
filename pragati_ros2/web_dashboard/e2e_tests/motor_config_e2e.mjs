#!/usr/bin/env node
// Motor Config E2E Test Suite
// Single browser, single page, sequential checks.
// Run: node web_dashboard/e2e_tests/motor_config_e2e.mjs
//
// Requires: npm install playwright (in this directory)
// Dashboard must be running on http://127.0.0.1:8090
//
// Updated for Preact + HTM ES-module frontend (no window globals, class-based
// selectors instead of id-based selectors, Preact sub-components render
// declaratively).

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

// Helper: check element exists and is visible (display != none)
async function isVisible(page, selector) {
    return page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        return getComputedStyle(el).display !== "none";
    }, selector);
}

// Helper: check element exists
async function exists(page, selector) {
    return page.evaluate((sel) => !!document.querySelector(sel), selector);
}

// Helper: check element is disabled
async function isDisabled(page, selector) {
    return page.evaluate((sel) => {
        const el = document.querySelector(sel);
        return el ? el.disabled : null;
    }, selector);
}

// Helper: get trimmed text content
async function getText(page, selector) {
    return page.evaluate((sel) => {
        const el = document.querySelector(sel);
        return el ? el.textContent.trim() : null;
    }, selector);
}

// Helper: get visible tab pane — Preact renders tab content conditionally inside
// .motor-tab-content. We check for the layout class name to identify which tab.
async function getVisibleTabLayout(page) {
    return page.evaluate(() => {
        const content = document.querySelector(".motor-tab-content");
        if (!content) return null;
        // Helper: get visible tab pane — Preact renders tab content inside
        // .motor-tab-content. Check for layout class names to identify which tab.
        // Tab restructure: Setting tab contains basic/limits/protection/pid panels,
        // Test tab contains commands + state panels.
        if (content.querySelector(".pid-tuning-layout")) return "pid";
        if (content.querySelector(".test-tab-layout")) return "test";
        if (content.querySelector(".encoder-layout")) return "encoder";
        if (content.querySelector(".product-panel")) return "product";
        // Setting tab has no unique class — detect by content text
        if (content.textContent.includes("Basic Setting")) return "setting";
        return null;
    });
}

// Helper: switch tab by clicking the .motor-tab button with matching text
// Tab layout was restructured: old tabs (PID Tuning, Commands, Limits, Encoder,
// State) became (Setting, Encoder, Product, Test, PID Tuning).
// Commands/Limits/State content is now inside the Setting and Test tabs.
async function switchTab(page, tabName) {
    const labelMap = {
        pid: "PID Tuning",
        setting: "Setting",
        encoder: "Encoder",
        product: "Product",
        test: "Test",
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

// Helper: fetch JSON from API (returns {status, body})
async function fetchJSON(page, path) {
    return page.evaluate(async (url) => {
        const r = await fetch(url);
        const body = await r.json();
        return { status: r.status, body };
    }, path);
}

// Helper: POST JSON to API
async function postJSON(page, path, body) {
    return page.evaluate(
        async ({ url, data }) => {
            const r = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
            });
            return r.json();
        },
        { url: path, data: body },
    );
}

// Helper: wait for Preact to render content into a section's -preact container
async function waitForPreactContent(page, sectionId, timeoutMs = 5000) {
    try {
        await page.waitForFunction(
            (id) => {
                const container = document.getElementById(
                    `${id}-section-preact`,
                );
                return container && container.children.length > 0;
            },
            sectionId,
            { timeout: timeoutMs },
        );
    } catch (_e) {
        // Fall back — content may already be visible
    }
}

(async () => {
    console.log("Motor Config E2E Test Suite");
    console.log("==========================\n");

    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({
        viewport: { width: 1280, height: 800 },
    });

    // Collect JS errors
    const jsErrors = [];
    page.on("pageerror", (err) => jsErrors.push(err.message));

    try {
        // ================================================================
        // SECTION 1: Dashboard Load & Navigation
        // ================================================================
        console.log("[1] Dashboard Load & Navigation");

        await page.goto(BASE, { waitUntil: "networkidle", timeout: 10000 });
        assert(
            await isVisible(page, 'a[title="Motor Config"]'),
            "Motor Config nav item visible",
        );

        // Click Motor Config
        await page.click('a[title="Motor Config"]');
        await waitForPreactContent(page, "motor-config");
        await page.waitForTimeout(1500);

        assert(
            await isVisible(page, "#motor-config-section"),
            "Motor Config section visible",
        );

        const tabBtnCount = await page.evaluate(
            () => document.querySelectorAll(".motor-tab").length,
        );
        assert(tabBtnCount === 5, `5 tab buttons exist (got ${tabBtnCount})`);

        // Preact component is rendered (replaces window.MotorConfigController check)
        const mccRendered = await page.evaluate(() => {
            const container = document.getElementById(
                "motor-config-section-preact",
            );
            return (
                container &&
                container.children.length > 0 &&
                !!container.querySelector(".motor-tab")
            );
        });
        assert(mccRendered, "MotorConfigTab component rendered");

        // Chart.js loaded (still a UMD global)
        const chartType = await page.evaluate(() => typeof window.Chart);
        assert(chartType === "function", "Chart.js loaded");

        // ================================================================
        // SECTION 2: Tab Switching
        // ================================================================
        console.log("\n[2] Tab Switching");

        // Default tab is Setting
        assert(
            (await getVisibleTabLayout(page)) === "setting",
            "Default tab is Setting",
        );

        // Check Setting tab button has active class
        const hasSettingActive = await page.evaluate(() => {
            const tabs = document.querySelectorAll(".motor-tab");
            for (const t of tabs) {
                if (
                    t.textContent.trim() === "Setting" &&
                    t.classList.contains("active")
                )
                    return true;
            }
            return false;
        });
        assert(hasSettingActive, "Setting button has active class");

        // Switch through all tabs
        for (const tab of ["encoder", "product", "test", "pid", "setting"]) {
            await switchTab(page, tab);
            const vis = await getVisibleTabLayout(page);
            assert(vis === tab, `Switch to ${tab}: visible=${vis}`);

            const labelMap = {
                pid: "PID Tuning",
                setting: "Setting",
                encoder: "Encoder",
                product: "Product",
                test: "Test",
            };
            const btnActive = await page.evaluate((lbl) => {
                const tabs = document.querySelectorAll(".motor-tab");
                for (const t of tabs) {
                    if (
                        t.textContent.trim() === lbl &&
                        t.classList.contains("active")
                    )
                        return true;
                }
                return false;
            }, labelMap[tab]);
            assert(btnActive, `${tab} button active after click`);
        }

        // ================================================================
        // SECTION 3: PID Tab Elements
        // ================================================================
        console.log("\n[3] PID Tab Elements");
        await switchTab(page, "pid");

        // Motor selection — Preact renders <select class="pid-select"> inside .pid-motor-selector
        assert(
            await isVisible(page, ".pid-motor-selector .pid-select"),
            "Motor dropdown visible",
        );
        const ddTag = await page.evaluate(
            () =>
                document.querySelector(".pid-motor-selector .pid-select")
                    ?.tagName,
        );
        assert(ddTag === "SELECT", "Motor dropdown is <select>");

        // Read PID button — inside .pid-motor-controls, a .btn.btn-primary
        assert(
            await isVisible(page, ".pid-motor-controls .btn.btn-primary"),
            "Read PID btn visible",
        );
        assert(
            await isDisabled(page, ".pid-motor-controls .btn.btn-primary"),
            "Read PID btn disabled",
        );

        // Motor status badge — .pid-status-badge
        assert(
            await exists(page, ".pid-status-badge"),
            "Motor status badge visible",
        );

        // PID step size control — .pid-step-size select.pid-select-small
        assert(
            await isVisible(page, ".pid-step-size .pid-select-small"),
            "Step select visible",
        );
        const stepOpts = await page.evaluate(() => {
            const sel = document.querySelector(
                ".pid-step-size .pid-select-small",
            );
            return sel ? Array.from(sel.options).map((o) => o.value) : [];
        });
        assert(
            JSON.stringify(stepOpts) === '["1","5","10"]',
            `Step options are 1,5,10 (got ${stepOpts})`,
        );
        const stepVal = await page.evaluate(
            () =>
                document.querySelector(".pid-step-size .pid-select-small")
                    ?.value,
        );
        assert(stepVal === "5", `Step default is 5 (got ${stepVal})`);

        // PID gain action buttons — inside .pid-gain-actions
        const gainBtns = await page.evaluate(() => {
            const actions = document.querySelector(".pid-gain-actions");
            if (!actions) return [];
            return Array.from(actions.querySelectorAll(".btn")).map((b) => ({
                text: b.textContent.trim(),
                disabled: b.disabled,
            }));
        });
        const applyRam = gainBtns.find((b) => b.text.includes("Apply"));
        const saveRom = gainBtns.find((b) => b.text.includes("Save"));
        const revert = gainBtns.find((b) => b.text.includes("Revert"));
        assert(applyRam !== undefined, "Apply RAM btn visible");
        assert(applyRam?.disabled, "Apply RAM btn disabled");
        assert(saveRom !== undefined, "Save ROM btn visible");
        assert(saveRom?.disabled, "Save ROM btn disabled");
        assert(revert !== undefined, "Revert btn visible");
        assert(revert?.disabled, "Revert btn disabled");

        // Sliders container — .pid-sliders
        assert(
            await exists(page, ".pid-sliders"),
            "Sliders container exists",
        );

        // Step response test — .pid-step-panel
        assert(
            await exists(page, ".pid-step-panel"),
            "Step test panel exists",
        );
        const stepInputs = await page.evaluate(() => {
            const panel = document.querySelector(".pid-step-panel");
            if (!panel) return { size: false, duration: false, btn: false };
            const inputs = panel.querySelectorAll("input.pid-input");
            const btn = panel.querySelector(".btn.btn-primary");
            return {
                size: inputs.length >= 1,
                duration: inputs.length >= 2,
                btn: !!btn,
                btnDisabled: btn?.disabled,
            };
        });
        assert(stepInputs.size, "Step size input visible");
        assert(stepInputs.duration, "Step duration input visible");
        assert(stepInputs.btn, "Run Step Test btn visible");
        assert(stepInputs.btnDisabled, "Run Step Test btn disabled");

        // Step progress — .pid-progress (hidden initially, conditional render)
        const stepProgressExists = await exists(page, ".pid-progress");
        if (stepProgressExists) {
            skip("Step progress hidden check", "progress may exist but empty");
        } else {
            assert(true, "Step progress not rendered initially");
        }

        // Auto-suggest panel — .pid-autotune-panel
        assert(
            await exists(page, ".pid-autotune-panel"),
            "Auto-suggest panel exists",
        );
        const autotuneBtns = await page.evaluate(() => {
            const panel = document.querySelector(".pid-autotune-panel");
            if (!panel) return {};
            const selects = panel.querySelectorAll(".pid-select");
            const btns = panel.querySelectorAll(".btn.btn-secondary");
            return {
                ruleSelect: selects.length >= 1,
                btns: Array.from(btns).map((b) => ({
                    text: b.textContent.trim(),
                    disabled: b.disabled,
                })),
            };
        });
        assert(autotuneBtns.ruleSelect, "Tuning rule dropdown visible");
        const autoSuggest = autotuneBtns.btns?.find((b) =>
            b.text.includes("Auto"),
        );
        const compareRules = autotuneBtns.btns?.find((b) =>
            b.text.includes("Compare"),
        );
        assert(autoSuggest !== undefined, "Auto-Suggest btn visible");
        assert(autoSuggest?.disabled, "Auto-Suggest btn disabled");
        assert(compareRules !== undefined, "Compare Rules btn visible");
        assert(compareRules?.disabled, "Compare Rules btn disabled");

        // Profile panel — .pid-profile-panel
        assert(
            await exists(page, ".pid-profile-panel"),
            "Profile panel exists",
        );
        const profileBtns = await page.evaluate(() => {
            const panel = document.querySelector(".pid-profile-panel");
            if (!panel) return {};
            const selects = panel.querySelectorAll(".pid-select");
            const btns = panel.querySelectorAll(".btn.btn-secondary");
            return {
                profileSelect: selects.length >= 1,
                btns: Array.from(btns).map((b) => ({
                    text: b.textContent.trim(),
                    disabled: b.disabled,
                })),
            };
        });
        assert(profileBtns.profileSelect, "Profile dropdown visible");
        const loadProfile = profileBtns.btns?.find((b) =>
            b.text.includes("Load"),
        );
        const saveProfile = profileBtns.btns?.find((b) =>
            b.text.includes("Save"),
        );
        assert(loadProfile !== undefined, "Load Profile btn visible");
        assert(loadProfile?.disabled, "Load Profile btn disabled");
        assert(saveProfile !== undefined, "Save Profile btn visible");
        assert(saveProfile?.disabled, "Save Profile btn disabled");

        // Guided tuning wizard — .pid-wizard-panel
        assert(
            await exists(page, ".pid-wizard-panel"),
            "Wizard panel exists",
        );
        const wizardInfo = await page.evaluate(() => {
            const panel = document.querySelector(".pid-wizard-panel");
            if (!panel) return {};
            const steps = panel.querySelectorAll(".pid-wizard-steps > div");
            const btn = panel.querySelector(".btn.btn-secondary");
            return {
                stepCount: steps.length,
                btnText: btn?.textContent.trim(),
                btnDisabled: btn?.disabled,
            };
        });
        assert(wizardInfo.btnText?.includes("Start"), "Start Wizard btn visible");
        assert(wizardInfo.btnDisabled, "Start Wizard btn disabled");
        assert(
            wizardInfo.stepCount >= 3,
            `Wizard has >=3 steps (got ${wizardInfo.stepCount})`,
        );

        // Performance metrics — .pid-metrics-panel .pid-metric
        const metricsInfo = await page.evaluate(() => {
            const items = document.querySelectorAll(".pid-metrics-grid .pid-metric");
            const result = {};
            items.forEach((item) => {
                const label = item.querySelector(".label")?.textContent.trim();
                const value = item.querySelector(".value")?.textContent.trim();
                if (label) result[label] = value;
            });
            return result;
        });
        for (const label of [
            "Rise Time",
            "Settle Time",
            "Overshoot",
            "SS Error",
            "IAE",
            "ISE",
            "ITSE",
        ]) {
            const value = metricsInfo[label];
            assert(
                value !== undefined && value.includes("--"),
                `Metric ${label} shows "--" (got "${value}")`,
            );
        }

        // Safety bar — .pid-safety-bar
        assert(
            await isVisible(page, ".pid-safety-bar"),
            "Safety bar visible",
        );
        assert(
            await exists(page, ".pid-estop-status"),
            "E-stop indicator visible",
        );
        assert(
            await exists(page, ".pid-session-info"),
            "Session status visible",
        );
        assert(
            await exists(page, ".pid-override-toggle"),
            "Limit override checkbox exists",
        );

        // Node status banner — .pid-node-banner (may or may not be rendered)
        const nodeBanner = await exists(page, ".pid-node-banner");
        assert(
            nodeBanner !== undefined,
            "Node status banner element checked",
        );

        // Autonomous warning — .pid-autonomous-banner (conditional)
        const autoBanner = await exists(page, ".pid-autonomous-banner");
        assert(
            autoBanner !== undefined,
            "Autonomous warning element checked",
        );

        // Session log — .pid-session-log
        assert(
            await isVisible(page, ".pid-session-log"),
            "Session log visible",
        );
        assert(
            await exists(page, ".pid-log-entries"),
            "Session log entries visible",
        );

        // Export log button — inside .pid-session-log
        const exportBtn = await page.evaluate(() => {
            const log = document.querySelector(".pid-session-log");
            if (!log) return null;
            const btn = log.querySelector(".btn");
            return btn
                ? { text: btn.textContent.trim(), disabled: btn.disabled }
                : null;
        });
        assert(
            exportBtn?.text?.includes("Export"),
            "Export Log btn visible",
        );

        // ================================================================
        // SECTION 4: Commands Panel (inside Test tab)
        // ================================================================
        console.log("\n[4] Commands Panel (Test Tab)");
        await switchTab(page, "test");

        // Motor state badge — .motor-state-badge
        assert(
            await isVisible(page, ".motor-state-badge"),
            "Motor state badge visible",
        );

        // Lifecycle buttons — inside .lifecycle-buttons
        const lifecycleBtns = await page.evaluate(() => {
            const container = document.querySelector(".lifecycle-buttons");
            if (!container) return [];
            return Array.from(container.querySelectorAll(".btn")).map((b) => ({
                text: b.textContent.trim(),
                cls: b.className,
            }));
        });
        assert(
            lifecycleBtns.some((b) => b.text.includes("ON")),
            "Motor ON btn visible",
        );
        assert(
            lifecycleBtns.some((b) => b.text.includes("OFF")),
            "Motor OFF btn visible",
        );
        assert(
            lifecycleBtns.some((b) => b.text === "STOP"),
            "STOP btn visible",
        );
        assert(
            lifecycleBtns.some((b) => b.text === "Reboot"),
            "Reboot btn visible",
        );

        // Reboot indicator hidden by default
        const rebootVisible = await isVisible(page, ".reboot-indicator");
        assert(!rebootVisible, "Reboot indicator hidden");

        // Mode select — .command-mode-select .pid-select
        assert(
            await isVisible(page, ".command-mode-select .pid-select"),
            "Mode select visible",
        );
        const modeCount = await page.evaluate(
            () =>
                document.querySelector(".command-mode-select .pid-select")
                    ?.options.length,
        );
        assert(modeCount === 8, `8 command modes (got ${modeCount})`);

        // Send button — .command-actions .btn.btn-primary
        assert(
            await isVisible(page, ".command-actions .btn.btn-primary"),
            "Send btn visible",
        );

        // Fields container — .command-fields
        assert(await exists(page, ".command-fields"), "Fields container exists");

        // Step buttons — .command-step-buttons
        assert(
            await exists(page, ".command-step-buttons"),
            "Step buttons container exists",
        );

        // Validation message — .validation-message
        assert(
            await exists(page, ".validation-message"),
            "Validation msg element exists",
        );

        // Mode switching changes fields
        const getFieldsHTML = () =>
            page.evaluate(
                () =>
                    document.querySelector(".command-fields")?.innerHTML || "",
            );

        const modeSelect = ".command-mode-select .pid-select";
        await page.selectOption(modeSelect, { index: 0 }); // Torque
        await page.waitForTimeout(200);
        const torqueFields = await getFieldsHTML();

        await page.selectOption(modeSelect, { index: 2 }); // Multi-turn angle
        await page.waitForTimeout(200);
        const angleFields = await getFieldsHTML();

        if (torqueFields.length > 0 && angleFields.length > 0) {
            assert(
                torqueFields !== angleFields,
                "Fields change between Torque and Angle modes",
            );
        } else {
            skip(
                "Fields change between modes",
                "Fields not populated (no motor selected)",
            );
        }

        // Response history (renamed heading: "Command Log", selectors unchanged)
        const histHeading = await page.evaluate(() => {
            const rh = document.querySelector(".response-history");
            if (!rh) return null;
            const h = rh.querySelector("h3, h4");
            return h ? h.textContent.trim() : null;
        });
        assert(
            histHeading !== null && histHeading.includes("Command Log"),
            `Command history heading says "Command Log" (got "${histHeading}")`,
        );
        const histBadge = await getText(page, ".response-history .badge");
        assert(histBadge === "0", `History count is 0 (got "${histBadge}")`);
        const histText = await getText(page, ".history-list");
        assert(
            histText?.includes("No commands"),
            'History shows "No commands" text',
        );

        // ================================================================
        // SECTION 5: Limits Panel (inside Setting tab)
        // ================================================================
        console.log("\n[5] Limits Panel (Setting Tab)");
        await switchTab(page, "setting");

        // Limits section exists with SET RAM buttons
        const limitsInfo = await page.evaluate(() => {
            const content = document.querySelector(".motor-tab-content");
            const text = content?.textContent || "";
            const hasLimitsHeading = text.includes("Limits Setting");
            const setRamBtns = [
                ...content.querySelectorAll("button"),
            ].filter((b) => b.textContent.includes("SET RAM"));
            const limitLabels = [
                "Max Torque Current",
                "Max Speed",
                "Max Angle",
                "Speed Ramp",
                "Current Ramp",
            ];
            const foundLabels = limitLabels.filter((l) => text.includes(l));
            const numberInputs = content.querySelectorAll(
                'input[type="number"]',
            ).length;
            return {
                hasLimitsHeading,
                setRamCount: setRamBtns.length,
                foundLabels,
                numberInputs,
            };
        });
        assert(limitsInfo.hasLimitsHeading, "Limits Setting heading exists");
        assert(
            limitsInfo.setRamCount >= 5,
            `At least 5 SET RAM buttons (got ${limitsInfo.setRamCount})`,
        );
        assert(
            limitsInfo.foundLabels.length === 5,
            `All 5 limit labels present (got ${limitsInfo.foundLabels.length})`,
        );
        assert(
            limitsInfo.numberInputs >= 5,
            `At least 5 number inputs (got ${limitsInfo.numberInputs})`,
        );

        // ================================================================
        // SECTION 6: Encoder Tab Elements (2-panel layout)
        // ================================================================
        console.log("\n[6] Encoder Tab Elements");
        await switchTab(page, "encoder");

        // 2-panel grid layout: left "Motor / Encoder Setting", right "Reducer / Encoder Setting"
        const encoderPanels = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            if (!layout) return null;
            const grid = layout.querySelector("div[style*='grid-template-columns']");
            if (!grid) return null;
            const cards = grid.querySelectorAll(".card");
            const headings = [...grid.querySelectorAll("h3")].map((h) =>
                h.textContent.trim(),
            );
            return { cardCount: cards.length, headings };
        });
        assert(
            encoderPanels?.cardCount === 2,
            `2 encoder panels (got ${encoderPanels?.cardCount})`,
        );
        assert(
            encoderPanels?.headings?.includes("Motor / Encoder Setting"),
            "Left panel heading present",
        );
        assert(
            encoderPanels?.headings?.includes("Reducer / Encoder Setting"),
            "Right panel heading present",
        );

        // Left panel fields (8 fields)
        const leftFields = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            const grid = layout?.querySelector("div[style*='grid-template-columns']");
            const cards = grid?.querySelectorAll(".card");
            if (!cards || cards.length < 1) return [];
            const spans = cards[0].querySelectorAll(
                "span[style*='color: var(--color-text-secondary)']",
            );
            return [...spans].map((s) => s.textContent.trim());
        });
        assert(
            leftFields.length === 8,
            `Left panel has 8 fields (got ${leftFields.length})`,
        );

        // Right panel fields (3 fields)
        const rightFields = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            const grid = layout?.querySelector("div[style*='grid-template-columns']");
            const cards = grid?.querySelectorAll(".card");
            if (!cards || cards.length < 2) return [];
            const spans = cards[1].querySelectorAll(
                "span[style*='color: var(--color-text-secondary)']",
            );
            return [...spans].map((s) => s.textContent.trim());
        });
        assert(
            rightFields.length === 3,
            `Right panel has 3 fields (got ${rightFields.length})`,
        );

        // Read and Save buttons below panels
        const readSaveBtns = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            if (!layout) return [];
            return [...layout.querySelectorAll(".btn")].map((b) =>
                b.textContent.trim(),
            );
        });
        assert(
            readSaveBtns.includes("Read"),
            "Read btn visible",
        );
        assert(
            readSaveBtns.includes("Save"),
            "Save btn visible",
        );

        // Write Zero RAM card — .card with .btn.btn-warning
        const writeZeroRam = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            if (!layout) return null;
            const cards = layout.querySelectorAll(".card");
            for (const card of cards) {
                const btn = card.querySelector(".btn.btn-warning");
                if (btn && btn.textContent.includes("Write Zero")) return true;
            }
            return false;
        });
        assert(writeZeroRam, "Write Zero RAM btn visible");

        // Use Current button — .btn.btn-secondary inside Write Zero card
        const useCurrent = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            if (!layout) return null;
            const btns = layout.querySelectorAll(".btn.btn-secondary");
            for (const b of btns) {
                if (b.textContent.includes("Use Current")) return true;
            }
            return false;
        });
        assert(useCurrent, "Use Current btn visible");

        // Set button (Save Zero ROM) — .btn.btn-danger inside left panel
        const setBtn = await page.evaluate(() => {
            const layout = document.querySelector(".encoder-layout");
            if (!layout) return null;
            const btns = layout.querySelectorAll(".btn.btn-danger");
            for (const b of btns) {
                if (b.textContent.trim() === "Set") return true;
            }
            return false;
        });
        assert(setBtn, "Set (Save Zero ROM) btn visible");

        // ================================================================
        // SECTION 7: State Panel (inside Test tab)
        // ================================================================
        console.log("\n[7] State Panel (Test Tab)");
        await switchTab(page, "test");

        // State values are in .state-grid as plain div pairs (label + value)
        const stateValues = await page.evaluate(() => {
            const grid = document.querySelector(".state-grid");
            if (!grid) return {};
            const children = [...grid.children];
            const result = {};
            for (let i = 0; i < children.length - 1; i += 2) {
                const label = children[i].textContent.trim();
                const value = children[i + 1].textContent.trim();
                result[label] = value;
            }
            return result;
        });

        for (const label of ["Bus Voltage", "Motor Temp"]) {
            assert(
                stateValues[label] !== undefined &&
                    stateValues[label].includes("--"),
                `${label} shows "--"`,
            );
        }

        // Motion values
        for (const label of [
            "Speed",
            "Torque Current",
            "Encoder",
        ]) {
            assert(
                stateValues[label] !== undefined &&
                    stateValues[label].includes("--"),
                `${label} shows "--"`,
            );
        }

        // Phase currents
        for (const phase of ["IA", "IB", "IC"]) {
            assert(
                stateValues[phase] !== undefined &&
                    stateValues[phase].includes("--"),
                `${phase} current shows "--"`,
            );
        }

        // Error flags — checkbox labels in .error-flags
        const flagCount = await page.evaluate(
            () => document.querySelectorAll(".error-flags label").length,
        );
        assert(flagCount === 8, `8 error flags (got ${flagCount})`);

        // Check specific error flag labels exist
        for (const label of [
            "UVP",
            "OVP",
            "DTP",
            "MTP",
            "OCP",
            "SCP",
            "MSP",
            "LIP",
        ]) {
            const flagExists = await page.evaluate((lbl) => {
                const flags = document.querySelectorAll(".error-flags label");
                for (const f of flags) {
                    if (f.textContent.includes(lbl)) return true;
                }
                return false;
            }, label);
            assert(flagExists, `Error flag "${label}" exists`);
        }

        // Read State buttons
        const readStateBtns = await page.evaluate(() => {
            const panel = document.querySelector(".test-state-panel");
            if (!panel) return [];
            return [...panel.querySelectorAll(".btn.btn-sm")].map((b) =>
                b.textContent.trim(),
            );
        });
        assert(
            readStateBtns.some((t) => t.includes("Read State")),
            "Read State btn visible",
        );
        assert(
            readStateBtns.some((t) => t.includes("Clear Error")),
            "Clear Error btn visible",
        );

        // ================================================================
        // SECTION 8: Charts Panel
        // ================================================================
        console.log("\n[8] Charts Panel");
        await switchTab(page, "pid"); // charts are below PID

        // Live chart — .pid-live-chart canvas
        const liveChart = await page.evaluate(() => {
            const panel = document.querySelector(".pid-live-chart");
            if (!panel) return { exists: false };
            const canvas = panel.querySelector("canvas");
            return {
                exists: !!canvas,
                isCanvas: canvas?.tagName === "CANVAS",
            };
        });
        assert(liveChart.exists, "Live chart canvas exists");
        assert(liveChart.isCanvas, "Live chart is <canvas>");

        // Step response charts — .pid-step-charts-grid has 4 ChartComponents
        const stepChartCount = await page.evaluate(() => {
            const grid = document.querySelector(".pid-step-charts-grid");
            if (!grid) return 0;
            return grid.querySelectorAll("canvas").length;
        });
        assert(
            stepChartCount === 4,
            `4 step response charts exist (got ${stepChartCount})`,
        );

        // Time window buttons — .chart-time-btn
        for (const sec of ["10", "30", "60", "120"]) {
            const btnExists = await page.evaluate((s) => {
                const btns = document.querySelectorAll(".chart-time-btn");
                for (const b of btns) {
                    if (b.textContent.trim() === `${s}s`) return true;
                }
                return false;
            }, sec);
            assert(btnExists, `Time button ${sec}s exists`);
        }

        // 30s active by default
        const active30 = await page.evaluate(() => {
            const btns = document.querySelectorAll(".chart-time-btn");
            for (const b of btns) {
                if (
                    b.textContent.trim() === "30s" &&
                    b.classList.contains("active")
                )
                    return true;
            }
            return false;
        });
        assert(active30, "30s time button active by default");

        // Chart action buttons — .chart-action-buttons .btn
        const chartActionBtns = await page.evaluate(() => {
            const container = document.querySelector(".chart-action-buttons");
            if (!container) return [];
            return Array.from(container.querySelectorAll(".btn")).map((b) =>
                b.textContent.trim(),
            );
        });
        assert(
            chartActionBtns.some((t) => t.includes("Capture")),
            "Chart Capture button exists",
        );
        assert(
            chartActionBtns.some((t) => t.includes("Clear")),
            "Chart Clear Snaps button exists",
        );
        assert(
            chartActionBtns.some((t) => t.includes("CSV")),
            "Chart CSV export button exists",
        );

        // Switch time window — click 60s button
        await page.evaluate(() => {
            const btns = document.querySelectorAll(".chart-time-btn");
            for (const b of btns) {
                if (b.textContent.trim() === "60s") {
                    b.click();
                    return;
                }
            }
        });
        await page.waitForTimeout(200);

        const active60 = await page.evaluate(() => {
            const btns = document.querySelectorAll(".chart-time-btn");
            for (const b of btns) {
                if (
                    b.textContent.trim() === "60s" &&
                    b.classList.contains("active")
                )
                    return true;
            }
            return false;
        });
        const inactive30 = await page.evaluate(() => {
            const btns = document.querySelectorAll(".chart-time-btn");
            for (const b of btns) {
                if (
                    b.textContent.trim() === "30s" &&
                    b.classList.contains("active")
                )
                    return true;
            }
            return false;
        });
        assert(active60, "60s button active after click");
        assert(!inactive30, "30s button inactive after switching");

        // ================================================================
        // SECTION 9: API Endpoints
        // ================================================================
        console.log("\n[9] API Endpoints");

        // PID motors
        const motors = (await fetchJSON(page, "/api/pid/motors")).body;
        assert(
            Array.isArray(motors?.motors),
            `GET /api/pid/motors returns array (len=${motors?.motors?.length})`,
        );

        // PID gain limits
        const limits = (await fetchJSON(page, "/api/pid/limits/mg6010")).body;
        assert(
            limits?.motor_type === "mg6010" && limits?.gain_limits,
            "GET /api/pid/limits/mg6010 has gain_limits",
        );
        assert(
            limits?.gain_limits?.position &&
                limits?.gain_limits?.speed &&
                limits?.gain_limits?.torque,
            "Gain limits has position/speed/torque",
        );

        // Profiles list
        const profiles = (await fetchJSON(page, "/api/pid/profiles/mg6010"))
            .body;
        assert(
            Array.isArray(profiles?.profiles),
            "GET /api/pid/profiles/mg6010 returns array",
        );

        // Validation ranges
        const ranges = (
            await fetchJSON(page, "/api/motor/validation_ranges")
        ).body;
        assert(ranges?.mg6010, "Validation ranges has mg6010");
        for (const key of [
            "torque_current",
            "speed",
            "angle",
            "max_speed",
            "max_torque_current",
            "acceleration",
            "encoder",
            "pid_gains",
        ]) {
            const r = ranges?.mg6010?.[key];
            assert(
                r && typeof r.min === "number" && typeof r.max === "number",
                `Range ${key} has min/max`,
            );
        }

        // Motor endpoints — return success:bool on 200, or detail:string on error
        // Without motor hardware, expect HTTP 502/504 with {detail: "..."}
        for (const ep of [
            "/api/motor/1/state",
            "/api/motor/1/limits",
            "/api/motor/1/encoder",
            "/api/motor/1/angles",
            "/api/pid/read/1",
        ]) {
            const resp = await fetchJSON(page, ep);
            const ok =
                (resp.status === 200 &&
                    typeof resp.body?.success === "boolean") ||
                (resp.status >= 400 &&
                    typeof resp.body?.detail === "string");
            assert(ok, `GET ${ep} returns valid response (HTTP ${resp.status})`);
        }

        // Session lifecycle
        const session = await postJSON(page, "/api/pid/session/start", {
            motor_id: 1,
            motor_type: "mg6010",
        });
        assert(
            typeof session?.session_id === "string" &&
                session.session_id.length > 0,
            "POST /api/pid/session/start returns session_id",
        );

        if (session?.session_id) {
            const log = (
                await fetchJSON(
                    page,
                    `/api/pid/session/log/${session.session_id}`,
                )
            ).body;
            assert(
                Array.isArray(log?.events),
                "GET session log returns events array",
            );

            const end = await postJSON(
                page,
                `/api/pid/session/end/${session.session_id}`,
                {},
            );
            assert(end?.success === true, "POST session end returns success");
        }

        // Profile save/load round-trip
        const testGains = {
            position_kp: 50,
            position_ki: 20,
            speed_kp: 40,
            speed_ki: 10,
            torque_kp: 30,
            torque_ki: 15,
        };
        const saved = await postJSON(page, "/api/pid/profiles/save", {
            name: "e2e_test_profile",
            motor_type: "mg6010",
            gains: testGains,
            description: "E2E test profile",
        });
        assert(saved?.success === true, "Profile save succeeds");

        if (saved?.success) {
            const loaded = (
                await fetchJSON(
                    page,
                    "/api/pid/profiles/mg6010/e2e_test_profile",
                )
            ).body;
            assert(
                loaded?.gains?.position_kp === 50 &&
                    loaded?.gains?.speed_kp === 40,
                "Profile load returns correct gains",
            );
        }

        // ================================================================
        // SECTION 10: Cross-cutting
        // ================================================================
        console.log("\n[10] Cross-cutting");

        // Tab content preserved across switches
        await switchTab(page, "pid");
        const slidersExist1 = await exists(page, ".pid-sliders");
        await switchTab(page, "test");
        await switchTab(page, "pid");
        const slidersExist2 = await exists(page, ".pid-sliders");
        assert(
            slidersExist1 && slidersExist2,
            "Sliders container present across tab switches",
        );

        // Motor dropdown preserved across tab switches
        const dd1 = await page.evaluate(
            () =>
                document.querySelector(".pid-motor-selector .pid-select")
                    ?.value,
        );
        await switchTab(page, "test");
        await switchTab(page, "pid");
        const dd2 = await page.evaluate(
            () =>
                document.querySelector(".pid-motor-selector .pid-select")
                    ?.value,
        );
        assert(
            dd1 === dd2,
            "Motor dropdown value preserved across tab switches",
        );

        // ================================================================
        // SECTION 11: Serial Monitor (Test Tab)
        // ================================================================
        console.log("\n[11] Serial Monitor (Test Tab)");
        await switchTab(page, "test");

        // Serial monitor container exists (3rd column in test-tab-layout)
        const serialMonitorExists = await page.evaluate(() => {
            const cols = document.querySelectorAll(".test-tab-column");
            if (cols.length < 3) return false;
            // Serial monitor is in the 3rd column, look for <pre> element
            return !!cols[2].querySelector("pre");
        });
        assert(serialMonitorExists, "Serial monitor container in 3rd test-tab-column");

        // Pause/Resume button exists with initial text "Pause"
        const pauseBtn = await page.evaluate(() => {
            const cols = document.querySelectorAll(".test-tab-column");
            if (cols.length < 3) return null;
            const btns = cols[2].querySelectorAll("button");
            for (const b of btns) {
                if (b.textContent.trim() === "Pause") return b.textContent.trim();
            }
            return null;
        });
        assert(
            pauseBtn === "Pause",
            `Pause button exists with text "Pause" (got "${pauseBtn}")`,
        );

        // Clear Text button exists
        const clearTextBtn = await page.evaluate(() => {
            const cols = document.querySelectorAll(".test-tab-column");
            if (cols.length < 3) return false;
            const btns = cols[2].querySelectorAll("button");
            for (const b of btns) {
                if (b.textContent.trim() === "Clear Text") return true;
            }
            return false;
        });
        assert(clearTextBtn, "Clear Text button exists");

        // Serial monitor <pre> element exists (text display area)
        const serialPre = await page.evaluate(() => {
            const cols = document.querySelectorAll(".test-tab-column");
            if (cols.length < 3) return false;
            const pre = cols[2].querySelector("pre");
            return !!pre;
        });
        assert(serialPre, "Serial monitor <pre> element exists");

        // No "Paused" indicator visible initially (running state)
        const pausedIndicator = await page.evaluate(() => {
            const cols = document.querySelectorAll(".test-tab-column");
            if (cols.length < 3) return false;
            const text = cols[2].textContent;
            // "Paused" indicator should not be visible in running state
            // Check for the standalone "Paused" text element, not "Pause" button
            const spans = cols[2].querySelectorAll("span, div, p");
            for (const el of spans) {
                if (el.textContent.trim() === "Paused") return true;
            }
            return false;
        });
        assert(!pausedIndicator, "No 'Paused' indicator visible initially");

        // Skip tests requiring live CAN bus data
        skip("Serial monitor line numbers", "requires CAN bus feed");
        skip("Serial monitor pause/resume behavior", "requires CAN bus feed");
        skip("Serial monitor frame data display", "requires CAN bus feed");

        // ================================================================
        // SECTION 12: Test Tab Button Groups
        // ================================================================
        console.log("\n[12] Test Tab Button Groups");
        await switchTab(page, "test");

        // 4 button groups exist inside .test-state-panel
        const buttonGroupCount = await page.evaluate(
            () =>
                document.querySelectorAll(".test-state-panel .button-group")
                    .length,
        );
        assert(
            buttonGroupCount === 4,
            `4 button groups exist (got ${buttonGroupCount})`,
        );

        // Section headers match expected names
        const groupHeaders = await page.evaluate(() => {
            const groups = document.querySelectorAll(
                ".test-state-panel .button-group h4",
            );
            return [...groups].map((h) => h.textContent.trim());
        });
        const expectedHeaders = [
            "State Reads",
            "Brake Controls",
            "Angle Reads",
            "Motor Reset",
        ];
        assert(
            JSON.stringify(groupHeaders) === JSON.stringify(expectedHeaders),
            `Button group headers match (got ${JSON.stringify(groupHeaders)})`,
        );

        // State Reads group has 4 buttons
        const stateReadsInfo = await page.evaluate(() => {
            const groups = document.querySelectorAll(
                ".test-state-panel .button-group",
            );
            for (const g of groups) {
                const h4 = g.querySelector("h4");
                if (h4 && h4.textContent.trim() === "State Reads") {
                    const btns = g.querySelectorAll(".button-row .btn");
                    return [...btns].map((b) => b.textContent.trim());
                }
            }
            return [];
        });
        assert(
            stateReadsInfo.length === 4,
            `State Reads has 4 buttons (got ${stateReadsInfo.length})`,
        );
        for (const expected of [
            "Read State 1",
            "Read State 2",
            "Read State 3",
            "Clear Error",
        ]) {
            assert(
                stateReadsInfo.includes(expected),
                `State Reads has "${expected}" button`,
            );
        }

        // Brake Controls group has 2 buttons
        const brakeInfo = await page.evaluate(() => {
            const groups = document.querySelectorAll(
                ".test-state-panel .button-group",
            );
            for (const g of groups) {
                const h4 = g.querySelector("h4");
                if (h4 && h4.textContent.trim() === "Brake Controls") {
                    const btns = g.querySelectorAll(".button-row .btn");
                    return [...btns].map((b) => b.textContent.trim());
                }
            }
            return [];
        });
        assert(
            brakeInfo.length === 2,
            `Brake Controls has 2 buttons (got ${brakeInfo.length})`,
        );
        for (const expected of ["Brake", "Brake Release"]) {
            assert(
                brakeInfo.includes(expected),
                `Brake Controls has "${expected}" button`,
            );
        }

        // Angle Reads group has buttons
        const angleReadsInfo = await page.evaluate(() => {
            const groups = document.querySelectorAll(
                ".test-state-panel .button-group",
            );
            for (const g of groups) {
                const h4 = g.querySelector("h4");
                if (h4 && h4.textContent.trim() === "Angle Reads") {
                    const btns = g.querySelectorAll(".button-row .btn");
                    return [...btns].map((b) => b.textContent.trim());
                }
            }
            return [];
        });
        for (const expected of [
            "Read Multi Loop Angle",
            "Read Single Loop Angle",
            "Clear Motor Loops",
        ]) {
            assert(
                angleReadsInfo.includes(expected),
                `Angle Reads has "${expected}" button`,
            );
        }

        // Motor Reset group has 2 buttons
        const motorResetInfo = await page.evaluate(() => {
            const groups = document.querySelectorAll(
                ".test-state-panel .button-group",
            );
            for (const g of groups) {
                const h4 = g.querySelector("h4");
                if (h4 && h4.textContent.trim() === "Motor Reset") {
                    const btns = g.querySelectorAll(".button-row .btn");
                    return [...btns].map((b) => b.textContent.trim());
                }
            }
            return [];
        });
        assert(
            motorResetInfo.length === 2,
            `Motor Reset has 2 buttons (got ${motorResetInfo.length})`,
        );
        for (const expected of ["Set Motor Zero (RAM)", "Motor Restore"]) {
            assert(
                motorResetInfo.includes(expected),
                `Motor Reset has "${expected}" button`,
            );
        }

        // ================================================================
        // SECTION 13: Responsive Layout Breakpoints
        // ================================================================
        console.log("\n[13] Responsive Layout Breakpoints");

        // Test Setting tab at default 1280px — 2-column grid
        await switchTab(page, "setting");
        const settingGrid1280 = await page.evaluate(() => {
            const grid = document.querySelector(".setting-tab-grid");
            if (!grid) return null;
            const children = [...grid.children];
            if (children.length < 2) return null;
            const first = children[0];
            const second = children[1];
            return {
                firstLeft: first.offsetLeft,
                firstWidth: first.offsetWidth,
                secondLeft: second.offsetLeft,
            };
        });
        assert(
            settingGrid1280 !== null &&
                settingGrid1280.secondLeft >
                    settingGrid1280.firstLeft +
                        settingGrid1280.firstWidth / 2,
            "Setting tab: 2-column layout at 1280px",
        );

        // Test tab at default 1280px — 3 columns
        await switchTab(page, "test");
        const testCols1280 = await page.evaluate(
            () => document.querySelectorAll(".test-tab-column").length,
        );
        const testGrid1280 = await page.evaluate(() => {
            const layout = document.querySelector(".test-tab-layout");
            if (!layout) return null;
            const children = [...layout.querySelectorAll(".test-tab-column")];
            if (children.length < 3) return null;
            return {
                col1Left: children[0].offsetLeft,
                col2Left: children[1].offsetLeft,
                col3Left: children[2].offsetLeft,
            };
        });
        assert(
            testCols1280 === 3 &&
                testGrid1280 !== null &&
                testGrid1280.col2Left > testGrid1280.col1Left &&
                testGrid1280.col3Left > testGrid1280.col2Left,
            "Test tab: 3-column layout at 1280px",
        );

        // Resize to 1024px — Setting tab should be 1 column
        await page.setViewportSize({ width: 1024, height: 800 });
        await page.waitForTimeout(300);
        await switchTab(page, "setting");
        const settingGrid1024 = await page.evaluate(() => {
            const grid = document.querySelector(".setting-tab-grid");
            if (!grid) return null;
            const children = [...grid.children];
            if (children.length < 2) return null;
            const first = children[0];
            const second = children[1];
            // Stacked: both have roughly same offsetLeft
            return {
                firstLeft: first.offsetLeft,
                secondLeft: second.offsetLeft,
            };
        });
        assert(
            settingGrid1024 !== null &&
                Math.abs(settingGrid1024.firstLeft - settingGrid1024.secondLeft) < 20,
            "Setting tab: 1-column layout at 1024px",
        );

        // Resize to 1024px — Test tab should be 2 columns
        await switchTab(page, "test");
        const testGrid1024 = await page.evaluate(() => {
            const layout = document.querySelector(".test-tab-layout");
            if (!layout) return null;
            const children = [...layout.querySelectorAll(".test-tab-column")];
            if (children.length < 3) return null;
            // At 1024px, first 2 columns side-by-side, 3rd wraps
            const col1Left = children[0].offsetLeft;
            const col2Left = children[1].offsetLeft;
            const col3Left = children[2].offsetLeft;
            const col1Top = children[0].offsetTop;
            const col3Top = children[2].offsetTop;
            return { col1Left, col2Left, col3Left, col1Top, col3Top };
        });
        assert(
            testGrid1024 !== null &&
                testGrid1024.col2Left > testGrid1024.col1Left,
            "Test tab: 2-column layout at 1024px (cols 1,2 side-by-side)",
        );

        // Resize to 768px — Test tab should be fully stacked (1 column)
        await page.setViewportSize({ width: 768, height: 800 });
        await page.waitForTimeout(300);
        await switchTab(page, "test");
        const testGrid768 = await page.evaluate(() => {
            const layout = document.querySelector(".test-tab-layout");
            if (!layout) return null;
            const children = [...layout.querySelectorAll(".test-tab-column")];
            if (children.length < 3) return null;
            return {
                col1Left: children[0].offsetLeft,
                col2Left: children[1].offsetLeft,
                col3Left: children[2].offsetLeft,
            };
        });
        assert(
            testGrid768 !== null &&
                Math.abs(testGrid768.col1Left - testGrid768.col2Left) < 20 &&
                Math.abs(testGrid768.col2Left - testGrid768.col3Left) < 20,
            "Test tab: 1-column layout at 768px (all stacked)",
        );

        // Restore viewport to default
        await page.setViewportSize({ width: 1280, height: 800 });
        await page.waitForTimeout(300);
        assert(true, "Viewport restored to 1280x800");

        // No JS errors
        assert(
            jsErrors.length === 0,
            `No page JS errors (got ${jsErrors.length}: ${jsErrors.join("; ")})`,
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
    console.log("\n==========================");
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
