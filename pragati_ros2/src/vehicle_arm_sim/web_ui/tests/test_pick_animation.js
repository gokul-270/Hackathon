'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const {
  triplePublish,
  executePickAnimation,
  ARM_CONFIGS,
} = require('./pick_animation_shim.js');

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Collects calls to publishArmJoint for assertion. */
function mockPublish() {
  var calls = [];
  function publish(topic, value) {
    calls.push({ topic: topic, value: value });
  }
  return { publish: publish, calls: calls };
}

/** Mock sleep that records requested durations but resolves instantly. */
function mockSleep() {
  var durations = [];
  function fakeSleep(ms) {
    durations.push(ms);
    return Promise.resolve();
  }
  return { sleep: fakeSleep, durations: durations };
}

/** Mock updateSliderUI that records calls. */
function mockSliderUI() {
  var calls = [];
  function update(arm, j3, j4, j5) {
    calls.push({ arm: arm, j3: j3, j4: j4, j5: j5 });
  }
  return { update: update, calls: calls };
}

/** Mock fetch for mark-picked POST. */
function mockFetch(status, body) {
  var calls = [];
  function fakeFetch(url, opts) {
    calls.push({ url: url, opts: opts });
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status: status,
      json: function () { return Promise.resolve(body); },
    });
  }
  return { fetch: fakeFetch, calls: calls };
}

// ─── 5.1: triplePublish ─────────────────────────────────────────────────────

test('triplePublish calls publishArmJoint 3 times with same topic and value', async () => {
  var pub = mockPublish();
  var slp = mockSleep();
  await triplePublish('/joint3_cmd', 0.5, {
    publishArmJoint: pub.publish,
    sleep: slp.sleep,
  });
  assert.equal(pub.calls.length, 3, 'should call publishArmJoint 3 times');
  pub.calls.forEach(function (c) {
    assert.equal(c.topic, '/joint3_cmd');
    assert.equal(c.value, 0.5);
  });
});

test('triplePublish waits 500ms between each publish', async () => {
  var pub = mockPublish();
  var slp = mockSleep();
  await triplePublish('/joint4_cmd', -0.1, {
    publishArmJoint: pub.publish,
    sleep: slp.sleep,
  });
  // 2 sleep calls between 3 publishes
  assert.equal(slp.durations.length, 2, 'should sleep twice between 3 publishes');
  slp.durations.forEach(function (d) {
    assert.equal(d, 500, 'each gap should be 500ms');
  });
});

// ─── 5.3: executePickAnimation step order ───────────────────────────────────

test('executePickAnimation executes 7 steps in correct joint order', async () => {
  var pub = mockPublish();
  var slp = mockSleep();
  var ui = mockSliderUI();
  var ft = mockFetch(200, { status: 'ok' });

  await executePickAnimation('arm1', 'cotton_0', -0.5, 0.1, 0.3, {
    publishArmJoint: pub.publish,
    sleep: slp.sleep,
    updateSliderUI: ui.update,
    fetch: ft.fetch,
    estopActive: false,
    pickAborted: false,
  });

  // Extract unique topic sequences from publish calls.
  // Each step = 3 publishes to same topic.
  // Expected order: J4, J3, J5(extend), [mark-picked], J5(retract), J3(home), J4(home)
  var topics = [];
  for (var i = 0; i < pub.calls.length; i += 3) {
    topics.push(pub.calls[i].topic);
  }
  var cfg = ARM_CONFIGS.arm1;
  assert.deepEqual(topics, [
    cfg.j4,  // step 1: J4 lateral
    cfg.j3,  // step 2: J3 tilt
    cfg.j5,  // step 3: J5 extend
    cfg.j5,  // step 5: J5 retract
    cfg.j3,  // step 6: J3 home
    cfg.j4,  // step 7: J4 home
  ], 'topics should follow J4→J3→J5→J5→J3→J4 order');
});

test('executePickAnimation uses correct topic names for arm2', async () => {
  var pub = mockPublish();
  var slp = mockSleep();
  var ui = mockSliderUI();
  var ft = mockFetch(200, { status: 'ok' });

  await executePickAnimation('arm2', 'cotton_1', -0.3, 0.05, 0.2, {
    publishArmJoint: pub.publish,
    sleep: slp.sleep,
    updateSliderUI: ui.update,
    fetch: ft.fetch,
    estopActive: false,
    pickAborted: false,
  });

  var cfg = ARM_CONFIGS.arm2;
  // First 3 publishes should be to arm2's J4 topic
  assert.equal(pub.calls[0].topic, cfg.j4);
  assert.equal(pub.calls[1].topic, cfg.j4);
  assert.equal(pub.calls[2].topic, cfg.j4);
});

// ─── 5.4: mark-picked called after J5 extend ───────────────────────────────

test('executePickAnimation calls mark-picked POST after J5 extend step', async () => {
  var pub = mockPublish();
  var slp = mockSleep();
  var ui = mockSliderUI();
  var ft = mockFetch(200, { status: 'ok' });

  await executePickAnimation('arm1', 'cotton_0', -0.5, 0.1, 0.3, {
    publishArmJoint: pub.publish,
    sleep: slp.sleep,
    updateSliderUI: ui.update,
    fetch: ft.fetch,
    estopActive: false,
    pickAborted: false,
  });

  assert.equal(ft.calls.length, 1, 'should call fetch exactly once (mark-picked)');
  assert.equal(ft.calls[0].url, '/api/cotton/cotton_0/mark-picked');
  assert.equal(ft.calls[0].opts.method, 'POST');
});

// ─── 5.5: abort before mark-picked ─────────────────────────────────────────

test('executePickAnimation aborts on pickAborted flag — no mark-picked call', async () => {
  var pub = mockPublish();
  var slp = mockSleep();
  var ui = mockSliderUI();
  var ft = mockFetch(200, { status: 'ok' });

  // pickAborted is checked as a getter so the test can control when it triggers
  var abortAfterCalls = 0;
  var deps = {
    publishArmJoint: function (topic, value) {
      pub.publish(topic, value);
      abortAfterCalls++;
    },
    sleep: slp.sleep,
    updateSliderUI: ui.update,
    fetch: ft.fetch,
    get estopActive() { return false; },
    get pickAborted() { return abortAfterCalls >= 3; }, // abort after first triple-publish
  };

  await executePickAnimation('arm1', 'cotton_0', -0.5, 0.1, 0.3, deps);

  // Should have aborted early — no mark-picked call
  assert.equal(ft.calls.length, 0, 'mark-picked should not be called when aborted before J5 extend');
  // Should have fewer than full 18 publishes (6 steps × 3)
  assert.ok(pub.calls.length < 18, 'should stop early: got ' + pub.calls.length + ' publishes');
});

// ─── 5.6: abort on estopActive ──────────────────────────────────────────────

test('executePickAnimation aborts on estopActive flag', async () => {
  var pub = mockPublish();
  var slp = mockSleep();
  var ui = mockSliderUI();
  var ft = mockFetch(200, { status: 'ok' });

  var abortAfterCalls = 0;
  var deps = {
    publishArmJoint: function (topic, value) {
      pub.publish(topic, value);
      abortAfterCalls++;
    },
    sleep: slp.sleep,
    updateSliderUI: ui.update,
    fetch: ft.fetch,
    get estopActive() { return abortAfterCalls >= 3; }, // estop after first step
    get pickAborted() { return false; },
  };

  await executePickAnimation('arm1', 'cotton_0', -0.5, 0.1, 0.3, deps);

  assert.equal(ft.calls.length, 0, 'mark-picked should not be called when estop active');
  assert.ok(pub.calls.length < 18, 'should stop early');
});

// ─── 5.7: joint values are correct ─────────────────────────────────────────

test('executePickAnimation publishes correct joint values in each step', async () => {
  var pub = mockPublish();
  var slp = mockSleep();
  var ui = mockSliderUI();
  var ft = mockFetch(200, { status: 'ok' });

  var j3 = -0.5, j4 = 0.1, j5 = 0.3;
  await executePickAnimation('arm1', 'cotton_0', j3, j4, j5, {
    publishArmJoint: pub.publish,
    sleep: slp.sleep,
    updateSliderUI: ui.update,
    fetch: ft.fetch,
    estopActive: false,
    pickAborted: false,
  });

  // Step 1: J4 = j4 value (lateral)
  assert.equal(pub.calls[0].value, j4, 'step 1: J4 should be j4 value');
  // Step 2: J3 = j3 value (tilt)
  assert.equal(pub.calls[3].value, j3, 'step 2: J3 should be j3 value');
  // Step 3: J5 = j5 value (extend)
  assert.equal(pub.calls[6].value, j5, 'step 3: J5 should be j5 value (extend)');
  // Step 5: J5 = 0 (retract)
  assert.equal(pub.calls[9].value, 0, 'step 5: J5 should be 0 (retract)');
  // Step 6: J3 = 0 (home)
  assert.equal(pub.calls[12].value, 0, 'step 6: J3 should be 0 (home)');
  // Step 7: J4 = 0 (home)
  assert.equal(pub.calls[15].value, 0, 'step 7: J4 should be 0 (home)');
});

// ─── 7.1–7.2: Polling code removed from testing_ui.js ──────────────────────
// These tests verify that the old polling functions are removed from the source.

const fs = require('node:fs');
const path = require('node:path');
const uiSource = fs.readFileSync(
  path.join(__dirname, '..', 'testing_ui.js'), 'utf8'
);

test('no pollPickStatus function in testing_ui.js', () => {
  assert.ok(
    !uiSource.includes('function pollPickStatus'),
    'testing_ui.js still contains pollPickStatus — must be removed'
  );
});

test('no pollPickAllStatus function in testing_ui.js', () => {
  assert.ok(
    !uiSource.includes('function pollPickAllStatus'),
    'testing_ui.js still contains pollPickAllStatus — must be removed'
  );
});

test('no _pickPollInterval variable in testing_ui.js', () => {
  assert.ok(
    !uiSource.includes('_pickPollInterval'),
    'testing_ui.js still contains _pickPollInterval — must be removed'
  );
});

test('no _pickAllPollInterval variable in testing_ui.js', () => {
  assert.ok(
    !uiSource.includes('_pickAllPollInterval'),
    'testing_ui.js still contains _pickAllPollInterval — must be removed'
  );
});

test('testing_ui.js contains triplePublish function', () => {
  assert.ok(
    uiSource.includes('function triplePublish') || uiSource.includes('async function triplePublish'),
    'testing_ui.js must contain triplePublish function'
  );
});

test('testing_ui.js contains executePickAnimation function', () => {
  assert.ok(
    uiSource.includes('function executePickAnimation') || uiSource.includes('async function executePickAnimation'),
    'testing_ui.js must contain executePickAnimation function'
  );
});
