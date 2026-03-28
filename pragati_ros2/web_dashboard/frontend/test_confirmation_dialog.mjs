import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const sourceFile = join(__dirname, "js", "components", "ConfirmationDialog.mjs");
const source = readFileSync(sourceFile, "utf8");

describe("ConfirmationDialog source validation", () => {
    it("should export ConfirmationDialog", () => {
        assert.match(source, /export\s+function\s+ConfirmationDialog/);
    });

    it("should export useConfirmDialog", () => {
        assert.match(source, /export\s+function\s+useConfirmDialog/);
    });
});

describe("ConfirmationDialog entity list rendering", () => {
    it("should check if message is a string type", () => {
        assert.match(source, /typeof\s+message\s*===\s*["']string["']/);
    });

    it("should wrap string messages in <p> tags", () => {
        // When message is a string, it should be wrapped in <p>
        assert.match(source, /html`<p>\$\{message\}<\/p>`/);
    });

    it("should render non-string messages directly (VNodes)", () => {
        // Non-string messages (VNodes) should be passed through without <p> wrapping
        // This is the "else" branch of the typeof check
        assert.match(source, /typeof\s+message\s*===\s*["']string["']\s*\?\s*html/);
    });
});

describe("ConfirmationDialog modal structure", () => {
    it("should use modal-overlay class", () => {
        assert.match(source, /modal-overlay/);
    });

    it("should use modal-content class", () => {
        assert.match(source, /modal-content/);
    });

    it("should use modal-header class", () => {
        assert.match(source, /modal-header/);
    });

    it("should use modal-body class", () => {
        assert.match(source, /modal-body/);
    });
});

describe("ConfirmationDialog confirm/cancel behavior", () => {
    it("should have confirm and cancel buttons", () => {
        assert.match(source, /confirm-dialog-confirm/);
        assert.match(source, /confirm-dialog-cancel/);
    });

    it("should support dangerous mode with red button", () => {
        assert.match(source, /confirm-btn-danger/);
    });

    it("should handle Escape key for cancel", () => {
        assert.match(source, /Escape/);
    });

    it("should handle overlay click for cancel", () => {
        assert.match(source, /e\.target\s*===\s*e\.currentTarget/);
    });
});

describe("ConfirmationDialog double-confirm mode", () => {
    it("should support confirmWord prop", () => {
        assert.match(source, /confirmWord/);
    });

    it("should disable confirm button until word matches", () => {
        assert.match(source, /confirmDisabled/);
    });

    it("should have text input for word confirmation", () => {
        assert.match(source, /confirm-dialog-input/);
    });
});

describe("useConfirmDialog hook", () => {
    it("should return dialog, confirm, and doubleConfirm", () => {
        assert.match(source, /return\s*\{\s*dialog\s*,\s*confirm\s*,\s*doubleConfirm\s*\}/);
    });

    it("should resolve promise with true on confirm", () => {
        assert.match(source, /resolve\(true\)/);
    });

    it("should resolve promise with false on cancel", () => {
        assert.match(source, /resolve\(false\)/);
    });

    it("should clean up on unmount", () => {
        // Resolves pending promise as false on unmount
        assert.match(source, /resolveRef\.current\(false\)/);
    });
});
