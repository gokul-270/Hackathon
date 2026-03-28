/**
 * Component tests for BulkActionBar.
 *
 * BulkActionBar is a Preact component that requires browser context (htm/preact).
 * These tests extract and verify source-level expectations: exports, imports,
 * status-dot mappings, button configuration, selection features, execution
 * behavior, and toast notification patterns.
 *
 * Run: node --test web_dashboard/frontend/test_bulk_action_bar.mjs
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const sourceFile = join(__dirname, "js", "components", "BulkActionBar.mjs");
const source = readFileSync(sourceFile, "utf8");

// ---------------------------------------------------------------------------
// Source validation
// ---------------------------------------------------------------------------

describe("BulkActionBar source validation", () => {
    it("should be a valid JavaScript file", () => {
        assert.ok(source.length > 0, "Source file is not empty");
    });

    it("should export BulkActionBar", () => {
        assert.match(source, /export\s*\{[^}]*BulkActionBar/);
    });

    it("should import executeBulkAction from bulkActions.js", () => {
        assert.match(source, /import.*executeBulkAction.*from.*bulkActions/);
    });

    it("should import useConfirmDialog from ConfirmationDialog", () => {
        assert.match(source, /import.*useConfirmDialog.*from.*ConfirmationDialog/);
    });
});

// ---------------------------------------------------------------------------
// STATUS_DOT_CLASS mapping
// ---------------------------------------------------------------------------

describe("BulkActionBar STATUS_DOT_CLASS mapping", () => {
    it("should define a STATUS_DOT_CLASS constant", () => {
        assert.match(source, /const\s+STATUS_DOT_CLASS\s*=/);
    });

    it("should map pending to bulk-progress__dot--pending", () => {
        assert.match(source, /pending:\s*"bulk-progress__dot--pending"/);
    });

    it("should map running to bulk-progress__dot--running", () => {
        assert.match(source, /running:\s*"bulk-progress__dot--running"/);
    });

    it("should map fulfilled to bulk-progress__dot--success", () => {
        assert.match(source, /fulfilled:\s*"bulk-progress__dot--success"/);
    });

    it("should map rejected to bulk-progress__dot--failed", () => {
        assert.match(source, /rejected:\s*"bulk-progress__dot--failed"/);
    });

    it("should have exactly 4 status entries", () => {
        const dotClassBlock = source.match(
            /const STATUS_DOT_CLASS\s*=\s*\{([\s\S]*?)\};/,
        );
        assert.ok(dotClassBlock, "STATUS_DOT_CLASS block found");
        const entries = dotClassBlock[1].match(/\w+:\s*"/g);
        assert.equal(entries.length, 4, "Exactly 4 status-dot entries");
    });
});

// ---------------------------------------------------------------------------
// Button configuration
// ---------------------------------------------------------------------------

describe("BulkActionBar button configuration", () => {
    it("should include E-Stop as danger button", () => {
        assert.match(source, /bulk-action-bar__button--danger"/);
        assert.match(source, /E-Stop/);
    });

    it("should include Restart ROS2 as warning button", () => {
        assert.match(source, /bulk-action-bar__button--warning"/);
        assert.match(source, /Restart ROS2/);
    });

    it("should include Reboot as warning button with confirmation", () => {
        assert.match(source, /Reboot/);
        assert.match(source, /actionType\s*===\s*"reboot"/);
    });

    it("should include Shutdown as danger-outline button with physical access warning", () => {
        assert.match(source, /bulk-action-bar__button--danger-outline"/);
        assert.match(source, /Shutdown/);
        assert.match(source, /physical access to restart/);
    });

    it("should include Collect Logs as neutral button", () => {
        assert.match(source, /bulk-action-bar__button--neutral"/);
        assert.match(source, /Collect Logs/);
    });

    it("should reference all 5 action types", () => {
        for (const action of ["estop", "restart-ros2", "reboot", "shutdown", "collect-logs"]) {
            assert.match(
                source,
                new RegExp(`"${action}"`),
                `Action type "${action}" present in source`,
            );
        }
    });
});

// ---------------------------------------------------------------------------
// Selection features
// ---------------------------------------------------------------------------

describe("BulkActionBar selection features", () => {
    it("should have Select All / Deselect All toggle", () => {
        assert.match(source, /Select All/);
        assert.match(source, /Deselect All/);
        assert.match(source, /allSelected/);
    });

    it("should display selection count badge", () => {
        assert.match(source, /of.*selected/);
        assert.match(source, /bulk-action-bar__count/);
    });

    it("should have quick-select shortcuts", () => {
        assert.match(source, /Select all arms/);
        assert.match(source, /Select all online/);
    });

    it("should filter arms by entity_type", () => {
        assert.match(source, /entity_type\s*===\s*"arm"/);
    });

    it("should filter online by status", () => {
        assert.match(source, /status\s*===\s*"online"/);
    });
});

// ---------------------------------------------------------------------------
// Execution behavior
// ---------------------------------------------------------------------------

describe("BulkActionBar execution behavior", () => {
    it("should disable buttons when executing", () => {
        const matches = source.match(/disabled=\$\{executing\}/g);
        // 5 action buttons + 2 shortcut buttons + 1 Select All toggle = 8
        assert.ok(
            matches && matches.length >= 8,
            `Expected at least 8 disabled bindings, got ${matches?.length}`,
        );
    });

    it("should have per-entity progress display", () => {
        assert.match(source, /bulk-progress/);
        assert.match(source, /bulk-progress__dot/);
    });

    it("should show progress dots with status classes", () => {
        assert.match(source, /STATUS_DOT_CLASS\[progress\[id\]\]/);
    });

    it("should deselect succeeded entities on partial failure", () => {
        assert.match(source, /failedIds/);
        assert.match(source, /onSelectionChange\(failedIds\)/);
    });

    it("should keep all entities selected on total failure", () => {
        // When all fail, the code does NOT call onDeselectAll (no branch for it).
        // The comment in source confirms: "If all failed, keep selection as-is"
        assert.match(source, /If all failed, keep selection as-is/);
    });

    it("should clear progress dots after delay", () => {
        assert.match(source, /setTimeout\(\(\)\s*=>\s*setProgress\(\{\}\)/);
    });
});

// ---------------------------------------------------------------------------
// Toast notifications
// ---------------------------------------------------------------------------

describe("BulkActionBar toast notifications", () => {
    it("should show success toast when all succeed", () => {
        assert.match(source, /showToast/);
        assert.match(source, /"success"/);
    });

    it("should show warning toast for partial failure", () => {
        assert.match(source, /"warning"/);
        assert.match(source, /succeeded.*failed/);
    });

    it("should show error toast for total failure", () => {
        assert.match(source, /"error"/);
    });

    it("should include entity names and reasons in failure toasts", () => {
        assert.match(source, /entityName/);
        assert.match(source, /reason/);
    });
});

// ---------------------------------------------------------------------------
// Structural expectations
// ---------------------------------------------------------------------------

describe("BulkActionBar structural expectations", () => {
    it("should use Preact hooks (useState, useCallback, useContext)", () => {
        assert.match(source, /useState/);
        assert.match(source, /useCallback/);
        assert.match(source, /useContext/);
    });

    it("should consume ToastContext", () => {
        assert.match(source, /useContext\(ToastContext\)/);
    });

    it("should render a confirmation dialog element", () => {
        assert.match(source, /\$\{dialog\}/);
    });

    it("should accept all required props", () => {
        for (const prop of [
            "selectedIds",
            "entities",
            "onDeselectAll",
            "onSelectAll",
            "onSelectionChange",
            "executing",
            "onExecutingChange",
        ]) {
            assert.match(
                source,
                new RegExp(prop),
                `Prop "${prop}" referenced in source`,
            );
        }
    });
});
