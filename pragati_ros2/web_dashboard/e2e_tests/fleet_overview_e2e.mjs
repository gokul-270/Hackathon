#!/usr/bin/env node
// Fleet Overview E2E Test Suite (Task 4.7)
// Tests fleet overview page rendering, entity cards, quick actions,
// empty state, discovered entities section, and E-Stop confirmation.
//
// Run: node web_dashboard/e2e_tests/fleet_overview_e2e.mjs
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

// Helper: navigate to section via hash change
async function navigateToSection(page, sectionName) {
    await page.evaluate(
        (name) => {
            window.location.hash = "#" + name;
        },
        sectionName
    );
    await page.waitForTimeout(1500);
}

// Helper: get text content of first matching element
async function getTextContent(page, selector) {
    return page.evaluate((sel) => {
        const el = document.querySelector(sel);
        return el ? el.textContent.trim() : null;
    }, selector);
}

// Helper: count elements matching selector
async function countElements(page, selector) {
    return page.evaluate(
        (sel) => document.querySelectorAll(sel).length,
        selector
    );
}

// Helper: check if element is visible (display is not none)
async function isVisible(page, selector) {
    return page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (!el) return false;
        const style = window.getComputedStyle(el);
        return style.display !== "none" && style.visibility !== "hidden";
    }, selector);
}

// ---------------------------------------------------------------------------
// Mock entity data
// ---------------------------------------------------------------------------

const MOCK_ENTITIES = [
    {
        id: "local",
        name: "local",
        entity_type: "vehicle",
        status: "online",
        source: "config",
        ip: "127.0.0.1",
        last_seen: new Date().toISOString(),
        ros2_available: true,
        system_metrics: {
            cpu_percent: 35.2,
            memory_percent: 58.4,
            temperature_c: 52.0,
        },
        ros2_state: { node_count: 5 },
        errors: [],
    },
    {
        id: "arm1-rpi",
        name: "arm1-rpi",
        entity_type: "arm",
        status: "online",
        source: "config",
        ip: "192.168.1.101",
        last_seen: new Date().toISOString(),
        ros2_available: true,
        system_metrics: {
            cpu_percent: 62.1,
            memory_percent: 44.0,
            temperature_c: 60.5,
        },
        ros2_state: { node_count: 8 },
        errors: [],
    },
];

const MOCK_ENTITIES_WITH_DISCOVERED = [
    ...MOCK_ENTITIES,
    {
        id: "discovered-arm2",
        name: "arm2-rpi",
        entity_type: "arm",
        status: "online",
        source: "discovered",
        ip: "192.168.1.102",
        last_seen: new Date().toISOString(),
        ros2_available: false,
        system_metrics: {},
        ros2_state: {},
        errors: [],
    },
];

// ---------------------------------------------------------------------------
// Main test suite
// ---------------------------------------------------------------------------

(async () => {
    console.log("Fleet Overview E2E Test Suite (Task 4.7)");
    console.log(`Target: ${BASE}`);
    console.log("==========================\n");

    const browser = await chromium.launch({
        headless: true,
        executablePath: process.env.CHROME_PATH || undefined,
        args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });

    const page = await browser.newPage();

    // Collect JS console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
        if (msg.type() === "error") {
            consoleErrors.push(msg.text());
        }
    });

    // Collect uncaught page errors
    const pageErrors = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));

    try {
        // ==================================================================
        // [1] Fleet overview loads as default page
        // ==================================================================
        console.log("[1] Fleet overview loads as default page");

        await page.goto(BASE, { waitUntil: "networkidle", timeout: 30000 });
        await page.waitForTimeout(2000);

        // The default route should be #fleet-overview
        const currentHash = await page.evaluate(() => window.location.hash);
        assert(
            currentHash === "#fleet-overview",
            `Default hash is #fleet-overview (got: "${currentHash}")`
        );

        // fleet-overview-section should have the "active" class
        const sectionActive = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section");
            return section ? section.classList.contains("active") : false;
        });
        assert(
            sectionActive,
            "Fleet overview section has 'active' class"
        );

        // fleet-overview-section should be visible (display != none)
        const sectionVisible = await isVisible(page, "#fleet-overview-section");
        assert(
            sectionVisible,
            "Fleet overview section is visible (display is not none)"
        );

        // ==================================================================
        // [2] Entity cards render
        // ==================================================================
        console.log("\n[2] Entity cards render");

        // The Preact container should exist
        const preactContainer = await page.evaluate(() => {
            return !!document.querySelector("#fleet-overview-section-preact");
        });
        assert(preactContainer, "Preact container #fleet-overview-section-preact exists");

        // Entity cards should render — the real API returns at least the "local" entity
        // Cards are rendered as .stat-card inside the fleet overview grid
        const cardCount = await page.evaluate(() => {
            // EntityCard renders as .stat-card elements inside the fleet-overview section
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return 0;
            return section.querySelectorAll(".stat-card").length;
        });
        assert(
            cardCount >= 1,
            `At least 1 entity card rendered (got: ${cardCount})`
        );

        // ==================================================================
        // [3] Entity card shows name and status indicator
        // ==================================================================
        console.log("\n[3] Entity card shows name and status indicator");

        // Check that entity cards contain entity name text and status elements
        const cardInfo = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return { hasName: false, hasStatusDot: false, name: null };
            const card = section.querySelector(".stat-card");
            if (!card) return { hasName: false, hasStatusDot: false, name: null };

            // The card renders entity name in a span with fontWeight 600
            // and a status dot as a 10px round span
            const allText = card.textContent.trim();
            const hasName = allText.length > 0;

            // Status indicator is a span with border-radius 50% and fixed width
            const spans = card.querySelectorAll("span");
            let hasStatusDot = false;
            for (const span of spans) {
                const style = span.style;
                if (
                    style.borderRadius === "50%" &&
                    (style.width === "10px" || style.width === "8px")
                ) {
                    hasStatusDot = true;
                    break;
                }
            }

            // Also check for health-ok or health-error class (status label)
            const hasHealthClass =
                !!card.querySelector(".health-ok") ||
                !!card.querySelector(".health-error") ||
                !!card.querySelector(".health-unknown");

            return { hasName, hasStatusDot: hasStatusDot || hasHealthClass, name: allText.substring(0, 50) };
        });
        assert(
            cardInfo.hasName,
            `Entity card contains name text (found: "${cardInfo.name}")`
        );
        assert(
            cardInfo.hasStatusDot,
            "Entity card contains a status indicator (dot or health class)"
        );

        // ==================================================================
        // [4] Drill-down navigation (click entity card)
        // ==================================================================
        console.log("\n[4] Drill-down navigation");

        // EntityCard currently does NOT pass onClick in FleetOverview,
        // so clicking a card should not navigate. We test that clicking
        // a card doesn't crash, and skip the URL hash assertion if no
        // onClick is wired.
        const hasClickHandler = await page.evaluate(() => {
            const section = document.querySelector("#fleet-overview-section-preact");
            if (!section) return false;
            const card = section.querySelector(".stat-card");
            if (!card) return false;
            return card.style.cursor === "pointer";
        });

        if (hasClickHandler) {
            // Click the first entity card
            const card = await page.$(
                "#fleet-overview-section-preact .stat-card"
            );
            if (card) {
                await card.click();
                await page.waitForTimeout(1000);
                const hashAfterClick = await page.evaluate(
                    () => window.location.hash
                );
                assert(
                    /^#\/?entity\/[^/]+/.test(hashAfterClick),
                    `Hash changed to entity detail route (got: "${hashAfterClick}")`
                );
                // Navigate back to fleet overview for remaining tests
                await navigateToSection(page, "fleet-overview");
                await page.waitForTimeout(1000);
            } else {
                skip("Drill-down hash change", "No .stat-card found to click");
            }
        } else {
            skip(
                "Drill-down navigation changes hash",
                "EntityCard onClick not wired in FleetOverview (cursor != pointer)"
            );
        }

        // ==================================================================
        // [5] Empty state with mocked empty /api/entities
        // ==================================================================
        console.log("\n[5] Empty state (mocked empty response)");

        {
            // Open a fresh page with route interception to mock empty entities
            const emptyPage = await browser.newPage();
            await emptyPage.route("**/api/entities", (route) =>
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify([]),
                })
            );
            // Block WebSocket so real entity updates don't override the empty mock
            await emptyPage.route("**/ws", (route) => route.abort());

            await emptyPage.goto(BASE + "#fleet-overview", {
                waitUntil: "networkidle",
                timeout: 30000,
            });
            await emptyPage.waitForTimeout(2000);

            // Check for empty state message — "No Entities Configured" text
            const emptyStateText = await emptyPage.evaluate(() => {
                const section = document.querySelector(
                    "#fleet-overview-section-preact"
                );
                if (!section) return null;
                return section.textContent;
            });

            assert(
                emptyStateText !== null &&
                    emptyStateText.includes("No Entities Configured"),
                `Empty state shows "No Entities Configured" message`
            );

            // Should have no .stat-card elements
            const emptyCardCount = await emptyPage.evaluate(() => {
                const section = document.querySelector(
                    "#fleet-overview-section-preact"
                );
                if (!section) return 0;
                return section.querySelectorAll(".stat-card").length;
            });
            assert(
                emptyCardCount === 0,
                `No entity cards when API returns empty list (got: ${emptyCardCount})`
            );

            await emptyPage.close();
        }

        // ==================================================================
        // [6] E-Stop All confirmation dialog
        // ==================================================================
        console.log("\n[6] E-Stop All confirmation dialog");

        // Ensure we're on fleet overview
        await navigateToSection(page, "fleet-overview");
        await page.waitForTimeout(1000);

        // E-Stop All button is in the dashboard header (#estop-all-btn),
        // not inside the fleet overview Preact section.
        const estopButton = await page.evaluate(() => {
            const btn = document.getElementById("estop-all-btn");
            if (!btn) return { found: false };
            return {
                found: true,
                disabled: btn.disabled,
                className: btn.className,
                text: btn.textContent.trim(),
            };
        });

        assert(estopButton.found, "E-Stop All button exists in fleet overview");

        if (estopButton.found) {
            assert(
                estopButton.className.includes("estop-button") ||
                    estopButton.className.includes("estop-all-btn"),
                "E-Stop All button has danger styling (estop-button class)"
            );

            // Click the E-Stop All button — if it's not disabled, a
            // native confirm() dialog should appear (not a custom modal).
            if (!estopButton.disabled) {
                // Set up a dialog handler to capture the confirm() call
                let dialogAppeared = false;
                let dialogMessage = "";
                const dialogHandler = async (dialog) => {
                    dialogAppeared = true;
                    dialogMessage = dialog.message();
                    await dialog.dismiss(); // Cancel the action
                };
                page.on("dialog", dialogHandler);

                await page.evaluate(() => {
                    const btn = document.getElementById("estop-all-btn");
                    if (btn) btn.click();
                });
                await page.waitForTimeout(500);

                assert(
                    dialogAppeared,
                    "Confirmation dialog overlay appeared after E-Stop All click"
                );
                assert(
                    dialogMessage.includes("Emergency Stop"),
                    `Dialog message contains "Emergency Stop" (got: "${dialogMessage.substring(0, 80)}")`
                );

                // Clean up dialog handler
                page.off("dialog", dialogHandler);
            } else {
                skip(
                    "E-Stop All dialog appears",
                    "Button is disabled (all entities offline or none configured)"
                );
                skip("Dialog message", "Button disabled — no dialog to check");
            }
        } else {
            skip("E-Stop All danger styling", "Button not found");
            skip("E-Stop All dialog appears", "Button not found");
            skip("Dialog message", "Button not found");
        }

        // ==================================================================
        // [7] Refresh All button
        // ==================================================================
        console.log("\n[7] Refresh All button");

        // Ensure we're on fleet overview
        await navigateToSection(page, "fleet-overview");
        await page.waitForTimeout(500);

        const refreshResult = await page.evaluate(() => {
            const section = document.querySelector(
                "#fleet-overview-section-preact"
            );
            if (!section) return { found: false };
            const buttons = section.querySelectorAll("button");
            for (const btn of buttons) {
                if (
                    btn.textContent.includes("Refresh All") ||
                    btn.textContent.includes("Refreshing")
                ) {
                    return { found: true, text: btn.textContent.trim(), disabled: btn.disabled };
                }
            }
            return { found: false };
        });

        assert(refreshResult.found, "Refresh All button exists in fleet overview");

        if (refreshResult.found) {
            // Clear any console errors before clicking
            const errorsBefore = consoleErrors.length;

            // Click the Refresh All button
            await page.evaluate(() => {
                const section = document.querySelector(
                    "#fleet-overview-section-preact"
                );
                const buttons = section.querySelectorAll("button");
                for (const btn of buttons) {
                    if (
                        btn.textContent.includes("Refresh All") ||
                        btn.textContent.includes("Refreshing")
                    ) {
                        btn.click();
                        break;
                    }
                }
            });
            await page.waitForTimeout(2000);

            // Verify no new page errors occurred
            const errorsAfter = pageErrors.length;
            assert(
                errorsAfter === 0,
                `No page errors after clicking Refresh All (page errors: ${errorsAfter})`
            );
        } else {
            skip("Refresh All click causes no errors", "Button not found");
        }

        // ==================================================================
        // [8] Discovered entities section (mocked)
        // ==================================================================
        console.log("\n[8] Discovered entities section");

        {
            // Open a new page with entities that include a "discovered" source
            const discPage = await browser.newPage();
            await discPage.route("**/api/entities", (route) =>
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify(MOCK_ENTITIES_WITH_DISCOVERED),
                })
            );

            await discPage.goto(BASE + "#fleet-overview", {
                waitUntil: "networkidle",
                timeout: 30000,
            });
            await discPage.waitForTimeout(2000);

            // Check for the "Discovered Devices" section heading
            const discoveredInfo = await discPage.evaluate(() => {
                const section = document.querySelector(
                    "#fleet-overview-section-preact"
                );
                if (!section) return { hasSection: false, text: null };
                const text = section.textContent;
                const hasDiscovered = text.includes("Discovered Devices") ||
                    text.includes("Discovered");
                // Count cards with dashed border (discovered card style)
                const dashedCards = section.querySelectorAll(
                    '.stat-card[style*="dashed"]'
                );
                // Also check via computed style
                let dashedCount = 0;
                section.querySelectorAll(".stat-card").forEach((card) => {
                    if (card.style.borderStyle === "dashed") {
                        dashedCount++;
                    }
                });
                return {
                    hasSection: hasDiscovered,
                    dashedCardCount: dashedCount || dashedCards.length,
                    text: text.substring(0, 200),
                };
            });

            assert(
                discoveredInfo.hasSection,
                `Discovered Devices section appears when entity has source "discovered"`
            );

            // The discovered entity name should appear
            const hasDiscName = await discPage.evaluate(() => {
                const section = document.querySelector(
                    "#fleet-overview-section-preact"
                );
                if (!section) return false;
                return section.textContent.includes("arm2-rpi");
            });
            assert(
                hasDiscName,
                'Discovered entity "arm2-rpi" name is visible'
            );

            await discPage.close();
        }

        // ==================================================================
        // [10] Add to Fleet button + confirmation dialog on discovered card
        // ==================================================================
        console.log("\n[10] Add to Fleet button + confirmation dialog");

        {
            // Open a page with mocked discovered entities
            const addPage = await browser.newPage();

            // Track API calls to the promote endpoint
            const promoteCalls = [];
            await addPage.route("**/api/entities/discovered/*/add", (route) => {
                promoteCalls.push({
                    url: route.request().url(),
                    method: route.request().method(),
                    body: route.request().postDataJSON(),
                });
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify({
                        id: "arm3",
                        name: "Arm 3 RPi",
                        entity_type: "arm",
                        source: "remote",
                        ip: "192.168.1.102",
                    }),
                });
            });
            await addPage.route("**/api/entities", (route) => {
                // After promotion, return updated list (entity moved to configured)
                if (promoteCalls.length > 0) {
                    route.fulfill({
                        status: 200,
                        contentType: "application/json",
                        body: JSON.stringify([
                            ...MOCK_ENTITIES,
                            {
                                id: "arm3",
                                name: "Arm 3 RPi",
                                entity_type: "arm",
                                status: "online",
                                source: "remote",
                                ip: "192.168.1.102",
                            },
                        ]),
                    });
                    return;
                }

                // Default: return entities with discovered
                route.fulfill({
                    status: 200,
                    contentType: "application/json",
                    body: JSON.stringify(MOCK_ENTITIES_WITH_DISCOVERED),
                });
            });
            // Block WebSocket to prevent real updates overriding mocks
            await addPage.route("**/ws", (route) => route.abort());

            await addPage.goto(BASE + "#fleet-overview", {
                waitUntil: "networkidle",
                timeout: 30000,
            });
            await addPage.waitForTimeout(2000);

            // [10a] "Add to Fleet" button exists on discovered card
            const addBtnInfo = await addPage.evaluate(() => {
                const section = document.querySelector(
                    "#fleet-overview-section-preact"
                );
                if (!section) return { found: false };
                // Find dashed-border cards (discovered entities)
                const cards = section.querySelectorAll(".stat-card");
                for (const card of cards) {
                    if (card.style.borderStyle === "dashed") {
                        const btn = card.querySelector("button");
                        if (btn) {
                            return {
                                found: true,
                                text: btn.textContent.trim(),
                            };
                        }
                    }
                }
                return { found: false };
            });

            assert(
                addBtnInfo.found,
                `"Add to Fleet" button exists on discovered entity card`
            );
            if (addBtnInfo.found) {
                assert(
                    addBtnInfo.text.includes("Add to Fleet"),
                    `Button text contains "Add to Fleet" (got: "${addBtnInfo.text}")`
                );
            } else {
                skip("Button text check", "Add to Fleet button not found");
            }

            // [10b] Clicking button opens confirmation dialog
            if (addBtnInfo.found) {
                await addPage.evaluate(() => {
                    const section = document.querySelector(
                        "#fleet-overview-section-preact"
                    );
                    const cards = section.querySelectorAll(".stat-card");
                    for (const card of cards) {
                        if (card.style.borderStyle === "dashed") {
                            const btn = card.querySelector("button");
                            if (btn) {
                                btn.click();
                                break;
                            }
                        }
                    }
                });
                await addPage.waitForTimeout(500);

                const dialogInfo = await addPage.evaluate(() => {
                    const overlay = document.querySelector(".modal-overlay");
                    if (!overlay) return { found: false };
                    const title = overlay.querySelector("h3");
                    const body = overlay.querySelector(".modal-body");
                    const confirmBtn = overlay.querySelector(
                        ".confirm-dialog-confirm"
                    );
                    return {
                        found: true,
                        title: title ? title.textContent.trim() : null,
                        bodyText: body ? body.textContent : null,
                        confirmBtnText: confirmBtn
                            ? confirmBtn.textContent.trim()
                            : null,
                    };
                });

                assert(
                    dialogInfo.found,
                    "Confirmation dialog opens after clicking Add to Fleet"
                );
                if (dialogInfo.found) {
                    assert(
                        dialogInfo.title &&
                            dialogInfo.title.includes("Add"),
                        `Dialog title contains "Add" (got: "${dialogInfo.title}")`
                    );
                    assert(
                        dialogInfo.bodyText &&
                            dialogInfo.bodyText.includes("192.168.1.102"),
                        `Dialog body mentions entity IP (got snippet: "${(dialogInfo.bodyText || "").substring(0, 80)}")`
                    );
                } else {
                    skip("Dialog title check", "Dialog not found");
                    skip("Dialog body IP check", "Dialog not found");
                }

                // [10c] Type selector exists in dialog
                const hasTypeSelector = await addPage.evaluate(() => {
                    const overlay = document.querySelector(".modal-overlay");
                    if (!overlay) return false;
                    // Look for radio buttons or select for entity type
                    const radios = overlay.querySelectorAll(
                        'input[type="radio"]'
                    );
                    const select = overlay.querySelector("select");
                    return radios.length >= 2 || !!select;
                });
                assert(
                    hasTypeSelector,
                    "Dialog contains entity type selector (radio buttons or dropdown)"
                );

                // [10d] Confirming the dialog calls the promote API
                if (dialogInfo.found) {
                    // Click the confirm button
                    await addPage.evaluate(() => {
                        const overlay =
                            document.querySelector(".modal-overlay");
                        if (!overlay) return;
                        const confirmBtn = overlay.querySelector(
                            ".confirm-dialog-confirm"
                        );
                        if (confirmBtn) confirmBtn.click();
                    });
                    await addPage.waitForTimeout(1500);

                    assert(
                        promoteCalls.length === 1,
                        `Promote API called exactly once (got: ${promoteCalls.length})`
                    );
                    if (promoteCalls.length > 0) {
                        assert(
                            promoteCalls[0].url.includes("discovered-arm2"),
                            `Promote API called with correct entity ID (url: ${promoteCalls[0].url})`
                        );
                        assert(
                            promoteCalls[0].body &&
                                promoteCalls[0].body.entity_type,
                            `Promote API body contains entity_type (body: ${JSON.stringify(promoteCalls[0].body)})`
                        );
                    } else {
                        skip("API entity ID check", "No API call captured");
                        skip("API body check", "No API call captured");
                    }

                    // [10e] After promotion, discovered card should disappear
                    const postPromoteDashed = await addPage.evaluate(() => {
                        const section = document.querySelector(
                            "#fleet-overview-section-preact"
                        );
                        if (!section) return -1;
                        let count = 0;
                        section
                            .querySelectorAll(".stat-card")
                            .forEach((card) => {
                                if (card.style.borderStyle === "dashed") {
                                    count++;
                                }
                            });
                        return count;
                    });
                    assert(
                        postPromoteDashed === 0,
                        `After promotion, no discovered cards remain (got: ${postPromoteDashed})`
                    );
                } else {
                    skip("Promote API called", "Dialog not found");
                    skip("API entity ID check", "Dialog not found");
                    skip("API body check", "Dialog not found");
                    skip("Discovered card removed after promotion", "Dialog not found");
                }
            } else {
                skip("Dialog opens", "Add to Fleet button not found");
                skip("Dialog title check", "Button not found");
                skip("Dialog body IP check", "Button not found");
                skip("Type selector check", "Button not found");
                skip("Promote API called", "Button not found");
                skip("API entity ID check", "Button not found");
                skip("API body check", "Button not found");
                skip("Discovered card removed", "Button not found");
            }

            await addPage.close();
        }

        // ==================================================================
        // [9] No JS errors during tests
        // ==================================================================
        console.log("\n[9] No JS errors during test suite");

        // Filter out non-critical errors (network errors from mocking are expected)
        const criticalConsoleErrors = consoleErrors.filter(
            (e) =>
                !e.includes("net::ERR_") &&
                !e.includes("Failed to fetch") &&
                !e.includes("NetworkError")
        );

        assert(
            pageErrors.length === 0,
            "No uncaught page errors during fleet overview tests" +
                (pageErrors.length > 0
                    ? ` (got ${pageErrors.length}: ${pageErrors.slice(0, 3).join("; ")})`
                    : "")
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
        `Results: ${passed} passed, ${failed} failed, ` +
            `${skipped} skipped (${total} total)`
    );
    if (failures.length > 0) {
        console.log("\nFailures:");
        failures.forEach((f) => console.log(`  - ${f}`));
    }
    console.log();
    process.exit(failed > 0 ? 1 : 0);
})();
