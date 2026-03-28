/**
 * E2E data pipeline test for LogsSubTab.
 *
 * Verifies that the file list data extraction correctly handles
 * multiple response envelope formats, sorts by modified date,
 * and filters out the __journald__ synthetic entry.
 *
 * Run: node test_logs_data_pipeline.mjs
 */

// ---- Helper: simulate the unwrapping + sort + filter logic from LogsSubTab ----

/**
 * Extract, sort, and filter log file list from safeFetch result.
 * Mirrors the logic in LogsSubTab.fetchFiles.
 *
 * @param {*} data - The result from safeFetch (already unwrapped from outer envelope)
 * @returns {Array} Sorted and filtered file list
 */
function extractFileList(data) {
    if (!data) return [];

    // Handle both envelope formats:
    // - {data: {files: [...]}} (double-wrapped)
    // - {files: [...]} (single envelope)
    // - {data: [...]} (flat array in data)
    // - [...] (flat array directly)
    const filesPayload = data.data || data;
    const fileList =
        filesPayload.files || (Array.isArray(filesPayload) ? filesPayload : []);

    if (!Array.isArray(fileList)) return [];

    // Sort by modified date, newest first; null dates go to end
    const sorted = [...fileList].sort((a, b) => {
        if (!a.modified && !b.modified) return 0;
        if (!a.modified) return 1;
        if (!b.modified) return -1;
        return new Date(b.modified) - new Date(a.modified);
    });

    // Filter out __journald__ synthetic entry
    return sorted.filter((f) => f.path !== "__journald__");
}

// ---- Test data ----

const MOCK_FILES = [
    {
        name: "arm_launch.log",
        path: "/var/log/pragati/arm_launch.log",
        size_bytes: 10240,
        modified: "2025-03-10T14:30:00Z",
    },
    {
        name: "motor_debug.log",
        path: "/var/log/pragati/motor_debug.log",
        size_bytes: 5120,
        modified: "2025-03-12T08:15:00Z",
    },
    {
        name: "can_bus.log",
        path: "/var/log/pragati/can_bus.log",
        size_bytes: 2048,
        modified: "2025-03-11T22:00:00Z",
    },
];

const MOCK_FILES_WITH_JOURNALD = [
    ...MOCK_FILES,
    {
        name: "__journald__",
        path: "__journald__",
        size_bytes: 0,
        modified: null,
    },
];

// ---- Test harness ----

let passed = 0;
let failed = 0;

function assert(condition, message) {
    if (condition) {
        passed++;
    } else {
        failed++;
        console.error(`FAIL: ${message}`);
    }
}

// ---- Tests ----

// Test 1: {data: {files: [...]}} double-wrapped format
{
    const result = extractFileList({ data: { files: MOCK_FILES } });
    assert(Array.isArray(result), "Double-wrapped: result should be an array");
    assert(result.length === 3, "Double-wrapped: should have 3 files");
}

// Test 2: {files: [...]} single envelope format
{
    const result = extractFileList({ files: MOCK_FILES });
    assert(Array.isArray(result), "Single envelope: result should be an array");
    assert(result.length === 3, "Single envelope: should have 3 files");
}

// Test 3: Flat array format
{
    const result = extractFileList(MOCK_FILES);
    assert(Array.isArray(result), "Flat array: result should be an array");
    assert(result.length === 3, "Flat array: should have 3 files");
}

// Test 4: Sort by modified date, newest first
{
    const result = extractFileList({ files: MOCK_FILES });
    assert(
        result[0].name === "motor_debug.log",
        "Sort: newest file (Mar 12) should be first"
    );
    assert(
        result[1].name === "can_bus.log",
        "Sort: middle file (Mar 11) should be second"
    );
    assert(
        result[2].name === "arm_launch.log",
        "Sort: oldest file (Mar 10) should be third"
    );
}

// Test 5: Null modified dates sort to end
{
    const filesWithNull = [
        { name: "a.log", path: "/a.log", modified: null },
        {
            name: "b.log",
            path: "/b.log",
            modified: "2025-03-12T08:15:00Z",
        },
        { name: "c.log", path: "/c.log", modified: null },
    ];
    const result = extractFileList({ files: filesWithNull });
    assert(
        result[0].name === "b.log",
        "Null dates: file with date should be first"
    );
    assert(
        result[1].name === "a.log" || result[1].name === "c.log",
        "Null dates: null-date files should be at end"
    );
}

// Test 6: Empty response produces empty file list
{
    const result = extractFileList(null);
    assert(Array.isArray(result), "Null data: result should be an array");
    assert(result.length === 0, "Null data: should be empty array");
}

// Test 7: Undefined response produces empty file list
{
    const result = extractFileList(undefined);
    assert(Array.isArray(result), "Undefined data: result should be an array");
    assert(result.length === 0, "Undefined data: should be empty array");
}

// Test 8: Empty object produces empty file list
{
    const result = extractFileList({});
    assert(Array.isArray(result), "Empty object: result should be an array");
    assert(result.length === 0, "Empty object: should be empty array");
}

// Test 9: Empty files array in envelope
{
    const result = extractFileList({ files: [] });
    assert(
        Array.isArray(result),
        "Empty files envelope: result should be an array"
    );
    assert(
        result.length === 0,
        "Empty files envelope: should be empty array"
    );
}

// Test 10: __journald__ entry is filtered out
{
    const result = extractFileList({ files: MOCK_FILES_WITH_JOURNALD });
    assert(
        result.length === 3,
        "__journald__ filter: should have 3 files (journald removed)"
    );
    assert(
        result.every((f) => f.path !== "__journald__"),
        "__journald__ filter: no file should have __journald__ path"
    );
}

// Test 11: Only __journald__ in list produces empty result
{
    const result = extractFileList({
        files: [{ name: "__journald__", path: "__journald__", modified: null }],
    });
    assert(
        result.length === 0,
        "Only __journald__: should produce empty array"
    );
}

// Test 12: File data integrity — all fields preserved
{
    const result = extractFileList({ files: [MOCK_FILES[0]] });
    const file = result[0];
    assert(file.name === "arm_launch.log", "Integrity: name preserved");
    assert(
        file.path === "/var/log/pragati/arm_launch.log",
        "Integrity: path preserved"
    );
    assert(file.size_bytes === 10240, "Integrity: size_bytes preserved");
    assert(
        file.modified === "2025-03-10T14:30:00Z",
        "Integrity: modified preserved"
    );
}

// ---- Summary ----
console.log(`\nLogs data pipeline: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
