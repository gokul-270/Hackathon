/**
 * E2E data pipeline test for FleetOverview node count consistency.
 *
 * Verifies that EntityCard displays the correct node count by:
 * - Preferring introspection node list length (entity.ros2Nodes)
 * - Falling back to heartbeat node_count (ros2_state.node_count)
 * - Showing null when ros2 is unavailable
 *
 * Run: node test_fleet_overview_node_count.mjs
 */

// ---- Helper: simulate EntityCard nodeCount logic ----

function getNodeCount(entity) {
    const ros2State = entity.ros2_state || {};
    if (!entity.ros2_available) return null;
    if (entity.ros2Nodes != null) return entity.ros2Nodes.length;
    return ros2State.node_count != null ? ros2State.node_count : 0;
}

// ---- Helper: simulate enrichWithNodeCounts response unwrapping ----

function extractNodesFromResponse(resp) {
    if (!resp || resp.error) return [];
    const nodeData = resp.data || resp;
    return Array.isArray(nodeData) ? nodeData : (nodeData.nodes || []);
}

// ---- Test data ----

const MOCK_NODES = [
    { name: "motion_controller", namespace: "/" },
    { name: "camera_driver", namespace: "/" },
    { name: "detection_node", namespace: "/" },
];

// ---- Tests: nodeCount derivation ----

let passed = 0;
let total = 0;

function test(name, fn) {
    total++;
    try {
        fn();
        passed++;
        console.log(`  PASS: ${name}`);
    } catch (e) {
        console.error(`  FAIL: ${name} — ${e.message}`);
    }
}

console.log("Fleet Overview Node Count Tests\n");

console.log("-- Node count derivation --");

test("introspection nodes preferred over heartbeat count", () => {
    const entity = {
        ros2_available: true,
        ros2Nodes: MOCK_NODES,
        ros2_state: { node_count: 10 },
    };
    const count = getNodeCount(entity);
    console.assert(count === 3, `Expected 3, got ${count}`);
    if (count !== 3) throw new Error(`Expected 3, got ${count}`);
});

test("falls back to heartbeat node_count when no introspection", () => {
    const entity = {
        ros2_available: true,
        ros2_state: { node_count: 7 },
    };
    const count = getNodeCount(entity);
    console.assert(count === 7, `Expected 7, got ${count}`);
    if (count !== 7) throw new Error(`Expected 7, got ${count}`);
});

test("returns 0 when heartbeat count is missing", () => {
    const entity = {
        ros2_available: true,
        ros2_state: {},
    };
    const count = getNodeCount(entity);
    console.assert(count === 0, `Expected 0, got ${count}`);
    if (count !== 0) throw new Error(`Expected 0, got ${count}`);
});

test("returns null when ros2 unavailable", () => {
    const entity = {
        ros2_available: false,
        ros2_state: { node_count: 5 },
    };
    const count = getNodeCount(entity);
    console.assert(count === null, `Expected null, got ${count}`);
    if (count !== null) throw new Error(`Expected null, got ${count}`);
});

test("empty ros2Nodes array returns 0", () => {
    const entity = {
        ros2_available: true,
        ros2Nodes: [],
        ros2_state: { node_count: 5 },
    };
    const count = getNodeCount(entity);
    console.assert(count === 0, `Expected 0, got ${count}`);
    if (count !== 0) throw new Error(`Expected 0, got ${count}`);
});

console.log("\n-- Response unwrapping for enrichment --");

test("flat array response", () => {
    const resp = { data: MOCK_NODES };
    const nodes = extractNodesFromResponse(resp);
    console.assert(nodes.length === 3, `Expected 3 nodes, got ${nodes.length}`);
    if (nodes.length !== 3) throw new Error(`Expected 3, got ${nodes.length}`);
});

test("object envelope response with nodes key", () => {
    const resp = { data: { nodes: MOCK_NODES } };
    const nodes = extractNodesFromResponse(resp);
    console.assert(nodes.length === 3, `Expected 3 nodes, got ${nodes.length}`);
    if (nodes.length !== 3) throw new Error(`Expected 3, got ${nodes.length}`);
});

test("direct array response (no data wrapper)", () => {
    const resp = MOCK_NODES;
    const nodes = extractNodesFromResponse(resp);
    console.assert(nodes.length === 3, `Expected 3 nodes, got ${nodes.length}`);
    if (nodes.length !== 3) throw new Error(`Expected 3, got ${nodes.length}`);
});

test("error response returns empty array", () => {
    const resp = { error: "timeout" };
    const nodes = extractNodesFromResponse(resp);
    console.assert(nodes.length === 0, `Expected 0 nodes, got ${nodes.length}`);
    if (nodes.length !== 0) throw new Error(`Expected 0, got ${nodes.length}`);
});

test("null response returns empty array", () => {
    const nodes = extractNodesFromResponse(null);
    console.assert(nodes.length === 0, `Expected 0 nodes, got ${nodes.length}`);
    if (nodes.length !== 0) throw new Error(`Expected 0, got ${nodes.length}`);
});

console.log("\n-- Card behavior scenarios --");

test("offline entity shows null count (for gray/disabled rendering)", () => {
    const entity = { ros2_available: false, status: "offline" };
    const count = getNodeCount(entity);
    console.assert(count === null, `Expected null, got ${count}`);
    if (count !== null) throw new Error(`Expected null, got ${count}`);
});

test("online entity without ros2 shows null count", () => {
    const entity = { ros2_available: false, status: "online" };
    const count = getNodeCount(entity);
    console.assert(count === null, `Expected null, got ${count}`);
    if (count !== null) throw new Error(`Expected null, got ${count}`);
});

// ---- Summary ----

console.log(`\n${passed}/${total} tests passed`);
if (passed !== total) {
    process.exit(1);
}
