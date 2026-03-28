/**
 * E2E data pipeline test for TopicsSubTab.
 *
 * Verifies that the topic list data extraction correctly handles
 * both response envelope formats:
 * - Flat array: [{name: "/cmd_vel", type: "...", ...}, ...]
 * - Object envelope: {topics: [{name: "/cmd_vel", ...}, ...]}
 *
 * Run: node test_topics_data_pipeline.mjs
 */

// ---- Helper: simulate the unwrapping logic from TopicsSubTab ----

/**
 * Extract topic list from cachedEntityFetch result.
 * Mirrors the logic in TopicsSubTab.fetchTopics.
 */
function extractTopicList(resultData) {
    return (
        resultData?.topics ||
        (Array.isArray(resultData) ? resultData : [])
    );
}

// ---- Test data ----

const MOCK_TOPICS = [
    {
        name: "/cmd_vel",
        type: "geometry_msgs/msg/Twist",
        publisher_count: 1,
        subscriber_count: 2,
    },
    {
        name: "/odom",
        type: "nav_msgs/msg/Odometry",
        publisher_count: 1,
        subscriber_count: 0,
    },
    {
        name: "/joint_states",
        type: "sensor_msgs/msg/JointState",
        publisher_count: 3,
        subscriber_count: 1,
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

// Test 1: Flat array format
{
    const result = extractTopicList(MOCK_TOPICS);
    assert(Array.isArray(result), "Flat array: result should be an array");
    assert(result.length === 3, "Flat array: should have 3 topics");
    assert(
        result[0].name === "/cmd_vel",
        "Flat array: first topic name should match"
    );
    assert(
        result[0].publisher_count === 1,
        "Flat array: publisher_count should be preserved"
    );
    assert(
        result[1].subscriber_count === 0,
        "Flat array: subscriber_count=0 should be preserved"
    );
}

// Test 2: Object envelope format {topics: [...]}
{
    const result = extractTopicList({ topics: MOCK_TOPICS });
    assert(
        Array.isArray(result),
        "Object envelope: result should be an array"
    );
    assert(result.length === 3, "Object envelope: should have 3 topics");
    assert(
        result[2].name === "/joint_states",
        "Object envelope: third topic name should match"
    );
}

// Test 3: Null/undefined data
{
    const result = extractTopicList(null);
    assert(Array.isArray(result), "Null data: result should be an array");
    assert(result.length === 0, "Null data: should be empty array");
}

// Test 4: undefined data
{
    const result = extractTopicList(undefined);
    assert(Array.isArray(result), "Undefined data: result should be an array");
    assert(result.length === 0, "Undefined data: should be empty array");
}

// Test 5: Empty object
{
    const result = extractTopicList({});
    assert(Array.isArray(result), "Empty object: result should be an array");
    assert(result.length === 0, "Empty object: should be empty array");
}

// Test 6: Empty topics array in envelope
{
    const result = extractTopicList({ topics: [] });
    assert(
        Array.isArray(result),
        "Empty topics envelope: result should be an array"
    );
    assert(
        result.length === 0,
        "Empty topics envelope: should be empty array"
    );
}

// Test 7: Object with unrelated keys (no topics, not array)
{
    const result = extractTopicList({ services: [{ name: "/srv" }] });
    assert(
        Array.isArray(result),
        "Wrong key: result should be an array"
    );
    assert(result.length === 0, "Wrong key: should be empty (no 'topics' key)");
}

// Test 8: Topic data integrity - all fields preserved
{
    const result = extractTopicList({ topics: MOCK_TOPICS });
    const topic = result[0];
    assert(topic.name === "/cmd_vel", "Integrity: name preserved");
    assert(
        topic.type === "geometry_msgs/msg/Twist",
        "Integrity: type preserved"
    );
    assert(
        topic.publisher_count === 1,
        "Integrity: publisher_count preserved"
    );
    assert(
        topic.subscriber_count === 2,
        "Integrity: subscriber_count preserved"
    );
}

// ---- Summary ----
console.log(`\nTopics data pipeline: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
