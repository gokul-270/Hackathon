import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const sourceFile = join(__dirname, "js", "tabs", "FleetOverview.mjs");
const source = readFileSync(sourceFile, "utf8");

describe("FleetOverview bulk selection imports", () => {
    it("should import BulkActionBar component", () => {
        assert.match(source, /import\s*\{[^}]*BulkActionBar[^}]*\}\s*from/);
    });

    it("should still import EntityCard component", () => {
        assert.match(source, /import\s*\{[^}]*EntityCard[^}]*\}\s*from/);
    });
});

describe("FleetOverview selection state", () => {
    it("should initialize selectedIds as empty Set", () => {
        assert.match(source, /useState\(new\s+Set\(\)\)/);
    });

    it("should have bulkExecuting state", () => {
        assert.match(source, /bulkExecuting/);
    });

    it("should have handleToggleSelect callback", () => {
        assert.match(source, /handleToggleSelect/);
    });

    it("should have handleSelectAll callback", () => {
        assert.match(source, /handleSelectAll/);
    });

    it("should have handleDeselectAll callback", () => {
        assert.match(source, /handleDeselectAll/);
    });

    it("should have handleSelectionChange callback", () => {
        assert.match(source, /handleSelectionChange/);
    });

    it("should toggle by adding/removing from Set", () => {
        // The toggle implementation should create a new Set and add/delete
        assert.match(source, /next\.has\(entityId\)/);
        assert.match(source, /next\.delete\(entityId\)/);
        assert.match(source, /next\.add\(entityId\)/);
    });

    it("should select all from configuredEntities", () => {
        assert.match(source, /configuredEntities\.map/);
    });
});

describe("FleetOverview stale ID cleanup", () => {
    it("should have useEffect for cleaning stale selections", () => {
        // Should check entity IDs against selectedIds
        assert.match(source, /entityIds\.has\(id\)/);
    });

    it("should only update state if IDs were actually removed", () => {
        assert.match(source, /changed\s*\?\s*next\s*:\s*prev/);
    });
});

describe("FleetOverview EntityCard selection props", () => {
    it("should pass selected prop to EntityCard", () => {
        assert.match(source, /selected=\$\{selectedIds\.has\(entity\.id\)\}/);
    });

    it("should pass selectionMode prop to EntityCard", () => {
        assert.match(source, /selectionMode=\$\{true\}/);
    });

    it("should pass onToggleSelect prop to EntityCard", () => {
        assert.match(source, /onToggleSelect=\$\{handleToggleSelect\}/);
    });

    it("should still pass onClick for navigation", () => {
        assert.match(source, /onClick=\$\{[\s\S]*?entity\.id[\s\S]*?\}/);
    });
});

describe("FleetOverview BulkActionBar integration", () => {
    it("should render BulkActionBar when selectedIds is non-empty", () => {
        assert.match(source, /selectedIds\.size\s*>\s*0/);
        assert.match(source, /BulkActionBar/);
    });

    it("should pass selectedIds to BulkActionBar", () => {
        assert.match(source, /selectedIds=\$\{selectedIds\}/);
    });

    it("should pass entities to BulkActionBar", () => {
        assert.match(source, /entities=\$\{configuredEntities\}/);
    });

    it("should pass onSelectAll to BulkActionBar", () => {
        assert.match(source, /onSelectAll=\$\{handleSelectAll\}/);
    });

    it("should pass onDeselectAll to BulkActionBar", () => {
        assert.match(source, /onDeselectAll=\$\{handleDeselectAll\}/);
    });

    it("should pass executing state to BulkActionBar", () => {
        assert.match(source, /executing=\$\{bulkExecuting\}/);
    });

    it("should pass onExecutingChange to BulkActionBar", () => {
        assert.match(source, /onExecutingChange=\$\{setBulkExecuting\}/);
    });
});
