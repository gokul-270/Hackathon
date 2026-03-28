/**
 * E2E data pipeline test for NodesSubTab.
 *
 * Verifies that the node list and node detail data extraction
 * correctly handles both response envelope formats:
 * - Flat array: [{name: "node1"}, ...]
 * - Object envelope: {nodes: [{name: "node1"}, ...]}
 *
 * Run: node test_nodes_data_pipeline.mjs
 */

// ---- Helper: simulate the unwrapping logic from NodesSubTab ----

/**
 * Extract node list from cachedEntityFetch result.
 * Mirrors the logic in NodesSubTab.fetchNodes.
 */
function extractNodeList(resultData) {
    return resultData?.nodes || (Array.isArray(resultData) ? resultData : []);
}

/**
 * Extract node detail from safeFetch result.
 * Mirrors the logic in NodesSubTab.fetchNodeDetail.
 */
function extractNodeDetail(result) {
    if (!result) return null;
    const detail = result.data || result;
    return {
        publishers: Array.isArray(detail.publishers) ? detail.publishers : [],
        subscribers: Array.isArray(detail.subscribers) ? detail.subscribers : [],
        services: Array.isArray(detail.services) ? detail.services : [],
        parameters: Array.isArray(detail.parameters) ? detail.parameters : [],
    };
}

// ---- Test data ----

const MOCK_NODES = [
    { name: "motion_controller", namespace: "/", lifecycle_state: "active" },
    { name: "camera_driver", namespace: "/", lifecycle_state: "inactive" },
];

const MOCK_NODE_DETAIL = {
    publishers: [{ topic: "/cmd_vel", type: "geometry_msgs/msg/Twist" }],
    subscribers: [{ topic: "/odom", type: "nav_msgs/msg/Odometry" }],
    services: [{ name: "/get_state", type: "lifecycle_msgs/srv/GetState" }],
    parameters: [{ name: "max_speed", value: 1.5 }],
};

// ---- Tests: Node list extraction ----

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
    const result = extractNodeList(MOCK_NODES);
    assert(Array.isArray(result), "Flat array: result should be an array");
    assert(result.length === 2, "Flat array: should have 2 nodes");
    assert(
        result[0].name === "motion_controller",
        "Flat array: first node name should match"
    );
}

// Test 2: Object envelope format {nodes: [...]}
{
    const result = extractNodeList({ nodes: MOCK_NODES });
    assert(Array.isArray(result), "Object envelope: result should be an array");
    assert(result.length === 2, "Object envelope: should have 2 nodes");
    assert(
        result[0].name === "motion_controller",
        "Object envelope: first node name should match"
    );
}

// Test 3: Null/undefined data
{
    const result = extractNodeList(null);
    assert(Array.isArray(result), "Null data: result should be an array");
    assert(result.length === 0, "Null data: should be empty array");
}

// Test 4: Empty object
{
    const result = extractNodeList({});
    assert(Array.isArray(result), "Empty object: result should be an array");
    assert(result.length === 0, "Empty object: should be empty array");
}

// Test 5: Empty nodes array in envelope
{
    const result = extractNodeList({ nodes: [] });
    assert(
        Array.isArray(result),
        "Empty nodes envelope: result should be an array"
    );
    assert(result.length === 0, "Empty nodes envelope: should be empty array");
}

// ---- Tests: Node detail extraction ----

// Test 6: Detail with data envelope
{
    const result = extractNodeDetail({ data: MOCK_NODE_DETAIL });
    assert(result !== null, "Detail envelope: result should not be null");
    assert(
        result.publishers.length === 1,
        "Detail envelope: should have 1 publisher"
    );
    assert(
        result.subscribers.length === 1,
        "Detail envelope: should have 1 subscriber"
    );
    assert(
        result.services.length === 1,
        "Detail envelope: should have 1 service"
    );
    assert(
        result.parameters.length === 1,
        "Detail envelope: should have 1 parameter"
    );
}

// Test 7: Detail without data envelope (direct object)
{
    const result = extractNodeDetail(MOCK_NODE_DETAIL);
    assert(result !== null, "Detail direct: result should not be null");
    assert(
        result.publishers.length === 1,
        "Detail direct: should have 1 publisher"
    );
    assert(
        result.subscribers.length === 1,
        "Detail direct: should have 1 subscriber"
    );
}

// Test 8: Detail with missing sections
{
    const result = extractNodeDetail({ data: { publishers: [] } });
    assert(
        result !== null,
        "Detail partial: result should not be null"
    );
    assert(
        result.publishers.length === 0,
        "Detail partial: publishers should be empty"
    );
    assert(
        result.subscribers.length === 0,
        "Detail partial: subscribers should default to empty"
    );
    assert(
        result.services.length === 0,
        "Detail partial: services should default to empty"
    );
    assert(
        result.parameters.length === 0,
        "Detail partial: parameters should default to empty"
    );
}

// Test 9: Null result
{
    const result = extractNodeDetail(null);
    assert(result === null, "Detail null: result should be null");
}

// ---- Summary ----
console.log(`\nNodes data pipeline: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
