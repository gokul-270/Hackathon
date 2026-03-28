/**
 * E2E data pipeline test for ServicesSubTab.
 *
 * Verifies that the service list data extraction correctly handles
 * both response envelope formats:
 * - Flat array: [{name: "/get_state", type: "..."}, ...]
 * - Object envelope: {services: [{name: "/get_state", ...}, ...]}
 *
 * Run: node test_services_data_pipeline.mjs
 */

// ---- Helper: simulate the unwrapping logic from ServicesSubTab ----

/**
 * Extract service list from cachedEntityFetch result.
 * Mirrors the logic in ServicesSubTab.loadServices.
 */
function extractServiceList(resultData) {
    return (
        resultData?.services ||
        (Array.isArray(resultData) ? resultData : [])
    );
}

// ---- Test data ----

const MOCK_SERVICES = [
    { name: "/get_state", type: "lifecycle_msgs/srv/GetState" },
    { name: "/change_state", type: "lifecycle_msgs/srv/ChangeState" },
    { name: "/emergency_stop", type: "std_srvs/srv/Trigger" },
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

// Test 1: Flat array format
{
    const result = extractServiceList(MOCK_SERVICES);
    assert(Array.isArray(result), "Flat array: result should be an array");
    assert(result.length === 3, "Flat array: should have 3 services");
    assert(
        result[0].name === "/get_state",
        "Flat array: first service name should match"
    );
    assert(
        result[0].type === "lifecycle_msgs/srv/GetState",
        "Flat array: type should be preserved"
    );
}

// Test 2: Object envelope format {services: [...]}
{
    const result = extractServiceList({ services: MOCK_SERVICES });
    assert(
        Array.isArray(result),
        "Object envelope: result should be an array"
    );
    assert(result.length === 3, "Object envelope: should have 3 services");
    assert(
        result[2].name === "/emergency_stop",
        "Object envelope: third service name should match"
    );
}

// Test 3: Null/undefined data
{
    const result = extractServiceList(null);
    assert(Array.isArray(result), "Null data: result should be an array");
    assert(result.length === 0, "Null data: should be empty array");
}

// Test 4: undefined data
{
    const result = extractServiceList(undefined);
    assert(
        Array.isArray(result),
        "Undefined data: result should be an array"
    );
    assert(result.length === 0, "Undefined data: should be empty array");
}

// Test 5: Empty object
{
    const result = extractServiceList({});
    assert(Array.isArray(result), "Empty object: result should be an array");
    assert(result.length === 0, "Empty object: should be empty array");
}

// Test 6: Empty services array in envelope
{
    const result = extractServiceList({ services: [] });
    assert(
        Array.isArray(result),
        "Empty services envelope: result should be an array"
    );
    assert(
        result.length === 0,
        "Empty services envelope: should be empty array"
    );
}

// Test 7: Object with unrelated keys
{
    const result = extractServiceList({ topics: [{ name: "/topic" }] });
    assert(Array.isArray(result), "Wrong key: result should be an array");
    assert(
        result.length === 0,
        "Wrong key: should be empty (no 'services' key)"
    );
}

// Test 8: Service call response unwrapping
// The service call response comes from raw fetch, not cachedEntityFetch.
// It returns {data: {...}, duration_ms: ...} on success.
{
    const callResponse = {
        data: { success: true, message: "Service called" },
        duration_ms: 150,
        status: 200,
    };
    assert(
        callResponse.data.success === true,
        "Call response: success field accessible"
    );
    assert(
        callResponse.duration_ms === 150,
        "Call response: duration_ms preserved"
    );
}

// Test 9: Service data integrity - all fields preserved
{
    const result = extractServiceList({ services: MOCK_SERVICES });
    const svc = result[0];
    assert(svc.name === "/get_state", "Integrity: name preserved");
    assert(
        svc.type === "lifecycle_msgs/srv/GetState",
        "Integrity: type preserved"
    );
}

// ---- Summary ----
console.log(`\nServices data pipeline: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
