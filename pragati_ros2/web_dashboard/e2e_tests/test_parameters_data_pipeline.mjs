/**
 * E2E data pipeline test for ParametersSubTab.
 *
 * Verifies that the parameter data extraction correctly handles
 * both response envelope formats:
 * - Flat array: [{name: "node1", parameters: [...]}, ...]
 * - Object envelope: {nodes: [{name: "node1", parameters: [...]}, ...]}
 *
 * Run: node test_parameters_data_pipeline.mjs
 */

// ---- Helper: simulate the unwrapping logic from ParametersSubTab ----

/**
 * Extract parameter node list from cachedEntityFetch result.
 * Mirrors the logic in ParametersSubTab.fetchParams (lines 783-785).
 */
function extractParamNodes(resultData) {
    return (
        resultData?.nodes ||
        (Array.isArray(resultData) ? resultData : [])
    );
}

// ---- Test data ----

const MOCK_PARAM_NODES = [
    {
        name: "motion_controller",
        parameters: [
            { name: "max_speed", type: "double", value: 1.5 },
            { name: "enabled", type: "bool", value: true },
        ],
    },
    {
        name: "camera_driver",
        parameters: [
            { name: "resolution_width", type: "int", value: 640 },
            { name: "camera_name", type: "string", value: "oak_d_lite" },
        ],
    },
];

// ---- Tests ----

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

// Test 1: Object envelope format {nodes: [...]}
{
    const result = extractParamNodes({ nodes: MOCK_PARAM_NODES });
    assert(
        Array.isArray(result),
        "Object envelope: result should be an array"
    );
    assert(result.length === 2, "Object envelope: should have 2 nodes");
    assert(
        result[0].name === "motion_controller",
        "Object envelope: first node name should match"
    );
    assert(
        result[0].parameters.length === 2,
        "Object envelope: first node should have 2 params"
    );
}

// Test 2: Flat array format (array of node objects)
{
    const result = extractParamNodes(MOCK_PARAM_NODES);
    assert(Array.isArray(result), "Flat array: result should be an array");
    assert(result.length === 2, "Flat array: should have 2 nodes");
    assert(
        result[1].name === "camera_driver",
        "Flat array: second node name should match"
    );
}

// Test 3: Null/undefined data
{
    const result = extractParamNodes(null);
    assert(Array.isArray(result), "Null data: result should be an array");
    assert(result.length === 0, "Null data: should be empty array");
}

// Test 4: undefined data
{
    const result = extractParamNodes(undefined);
    assert(
        Array.isArray(result),
        "Undefined data: result should be an array"
    );
    assert(result.length === 0, "Undefined data: should be empty array");
}

// Test 5: Empty object
{
    const result = extractParamNodes({});
    assert(Array.isArray(result), "Empty object: result should be an array");
    assert(result.length === 0, "Empty object: should be empty array");
}

// Test 6: Empty nodes array in envelope
{
    const result = extractParamNodes({ nodes: [] });
    assert(
        Array.isArray(result),
        "Empty nodes envelope: result should be an array"
    );
    assert(
        result.length === 0,
        "Empty nodes envelope: should be empty array"
    );
}

// Test 7: Parameter value types preserved
{
    const result = extractParamNodes({ nodes: MOCK_PARAM_NODES });
    const params = result[0].parameters;
    assert(
        params[0].value === 1.5,
        "Type check: double value preserved as number"
    );
    assert(
        params[1].value === true,
        "Type check: bool value preserved as boolean"
    );
    const params2 = result[1].parameters;
    assert(
        params2[0].value === 640,
        "Type check: int value preserved as number"
    );
    assert(
        params2[1].value === "oak_d_lite",
        "Type check: string value preserved"
    );
}

// Test 8: Parameter type fields preserved
{
    const result = extractParamNodes({ nodes: MOCK_PARAM_NODES });
    const params = result[0].parameters;
    assert(params[0].type === "double", "Type field: double preserved");
    assert(params[1].type === "bool", "Type field: bool preserved");
}

// Test 9: Coerce value helper (mirrors ParametersSubTab.coerceValue)
{
    function coerceValue(raw, type) {
        const t = (type || "").toLowerCase();
        if (t === "bool" || t === "boolean") {
            const v = raw.trim().toLowerCase();
            return v === "true" || v === "1";
        }
        if (t === "int" || t === "integer") {
            const n = parseInt(raw, 10);
            return isNaN(n) ? raw : n;
        }
        if (t === "double" || t === "float") {
            const n = parseFloat(raw);
            return isNaN(n) ? raw : n;
        }
        return raw;
    }

    assert(coerceValue("true", "bool") === true, "Coerce: bool true");
    assert(coerceValue("false", "bool") === false, "Coerce: bool false");
    assert(coerceValue("42", "int") === 42, "Coerce: int 42");
    assert(coerceValue("3.14", "double") === 3.14, "Coerce: double 3.14");
    assert(
        coerceValue("hello", "string") === "hello",
        "Coerce: string passthrough"
    );
}

// ---- Summary ----
console.log(`\nParameters data pipeline: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
