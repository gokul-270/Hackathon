'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { camToJoint } = require('./cam_to_joint_shim.js');

// Helper: builds a mock tf4x4 whose apply() always returns the given arm-frame coords.
function mockTf(ax, ay, az) {
  return {
    apply(_x, _y, _z) {
      return { x: ax, y: ay, z: az };
    }
  };
}

// Pre-computed expected values for the "valid" fixture:
//   tf returns {x: -0.5, y: 0.1, z: -0.2}
//   r   = sqrt((-0.5)^2 + (-0.2)^2) = sqrt(0.25 + 0.04) = sqrt(0.29) ≈ 0.53852
//   J3  = asin(-0.2 / 0.53852)      ≈ -0.3805 rad   → within [-0.9, 0.0] ✓
//   J4  = 0.1                        → within [-0.25, 0.35] ✓
//   J5  = 0.53852 - 0.320            ≈  0.2185 m     → within [0.0, 0.45] ✓
const VALID_TF = mockTf(-0.5, 0.1, -0.2);

// ─── Test 3.2 ────────────────────────────────────────────────────────────────
// camToJoint with valid coords returns J3 in radians within [-0.9, 0.0]
test('camToJoint with valid coords returns J3 in radians within [-0.9, 0.0]', () => {
  assert.equal(typeof camToJoint, 'function', 'camToJoint must be a function (not implemented yet)');
  const result = camToJoint(VALID_TF, 0, 0, 0);
  assert.equal(result.valid, true, 'result.valid should be true for valid coords');
  assert.ok(
    result.j3 >= -0.9 && result.j3 <= 0.0,
    `result.j3 (${result.j3}) should be within [-0.9, 0.0]`
  );
});

// ─── Test 3.3 ────────────────────────────────────────────────────────────────
// camToJoint returns J4 equal to ay (direct passthrough of arm-frame y)
test('camToJoint returns J4 equal to ay (direct passthrough)', () => {
  assert.equal(typeof camToJoint, 'function', 'camToJoint must be a function (not implemented yet)');
  const result = camToJoint(VALID_TF, 0, 0, 0);
  assert.equal(result.valid, true, 'result.valid should be true for valid coords');
  // ay = 0.1 exactly
  assert.strictEqual(result.j4, 0.1, 'result.j4 must equal ay (0.1)');
});

// ─── Test 3.4 ────────────────────────────────────────────────────────────────
// camToJoint returns J5 = r - 0.320 where r = sqrt(ax^2 + az^2)
test('camToJoint returns J5 equal to r minus 0.320', () => {
  assert.equal(typeof camToJoint, 'function', 'camToJoint must be a function (not implemented yet)');
  const result = camToJoint(VALID_TF, 0, 0, 0);
  assert.equal(result.valid, true, 'result.valid should be true for valid coords');
  const expectedR  = Math.sqrt((-0.5) ** 2 + (-0.2) ** 2); // ≈ 0.53852
  const expectedJ5 = expectedR - 0.320;                     // ≈ 0.2185
  assert.ok(
    Math.abs(result.j5 - expectedJ5) < 1e-9,
    `result.j5 (${result.j5}) should ≈ ${expectedJ5}`
  );
});

// ─── Test 3.5 ────────────────────────────────────────────────────────────────
// camToJoint returns {valid: false} when J3 is outside [-0.9, 0.0]
// tf returns {x: 0.1, y: 0.0, z: 0.4}
//   r  = sqrt(0.01 + 0.16) = sqrt(0.17) ≈ 0.4123
//   J3 = asin(0.4 / 0.4123) ≈ asin(0.9701) ≈ +1.326 rad → outside [-0.9, 0.0] → invalid
test('camToJoint returns {valid: false} when J3 is outside limits', () => {
  assert.equal(typeof camToJoint, 'function', 'camToJoint must be a function (not implemented yet)');
  const invalidTf = mockTf(0.1, 0.0, 0.4);
  const result = camToJoint(invalidTf, 0, 0, 0);
  assert.strictEqual(result.valid, false, 'result.valid must be false when J3 is out of range');
});

// ─── Degenerate radius guard tests ──────────────────────────────────────────

// ─── Test 1.3 ────────────────────────────────────────────────────────────────
// camToJoint returns null when r < 1e-6 (degenerate radius, near-origin arm coords)
test('camToJoint returns null when r < 1e-6 (degenerate radius)', () => {
  // tf returns arm coords where ax~0, az~0 => r = sqrt(0+0) = 0 < 1e-6
  var degenerateTf = mockTf(0.0, 0.1, 0.0);
  var result = camToJoint(degenerateTf, 0, 0, 0);
  assert.strictEqual(result, null,
    'camToJoint should return null for degenerate radius (r < 1e-6)');
});

// ─── Test 1.5 ────────────────────────────────────────────────────────────────
// camToJoint r threshold for asin uses 1e-6 (not 1e-9): value between 1e-9 and
// 1e-6 should return null (degenerate), not proceed with asin
test('camToJoint r threshold uses 1e-6 not 1e-9 for degenerate guard', () => {
  // r = 5e-7 which is > 1e-9 but < 1e-6 — should be caught by 1e-6 guard
  var ax = 5e-7, az = 0.0;
  var tinyTf = mockTf(ax, 0.1, az);
  var result = camToJoint(tinyTf, 0, 0, 0);
  assert.strictEqual(result, null,
    'r=5e-7 is < 1e-6, should return null (would pass old 1e-9 threshold)');
});

// ─── Transform Tests ────────────────────────────────────────────────────────

const { initCameraToArmTransform } = require('./cam_to_joint_shim.js');

// ─── Test 1.1 ────────────────────────────────────────────────────────────────
// initCameraToArmTransform produces FORWARD transform matching Python _T_CAM_TO_ARM
test('initCameraToArmTransform produces forward transform matching Python _T_CAM_TO_ARM', () => {
  assert.equal(typeof initCameraToArmTransform, 'function',
    'initCameraToArmTransform must be exported');

  var tf = initCameraToArmTransform();
  assert.ok(tf && typeof tf.apply === 'function',
    'must return object with apply(x,y,z) method');

  // Python _T_CAM_TO_ARM forward transform of cam=(0.494, -0.001, 0.004):
  //   arm = R @ cam + t = (0.365449, 0.096461, -0.427147)
  // Tolerance 1e-4 for float precision
  var result = tf.apply(0.494, -0.001, 0.004);
  assert.ok(Math.abs(result.x - 0.365449) < 1e-4,
    `x: expected ~0.365449 got ${result.x}`);
  assert.ok(Math.abs(result.y - 0.096461) < 1e-4,
    `y: expected ~0.096461 got ${result.y}`);
  assert.ok(Math.abs(result.z - (-0.427147)) < 1e-4,
    `z: expected ~-0.427147 got ${result.z}`);

  // Also verify matrix structure: apply(0,0,0) should return translation [tx, ty, tz]
  var origin = tf.apply(0, 0, 0);
  assert.ok(Math.abs(origin.x - 0.016845) < 1e-6,
    `origin.x should be tx=0.016845, got ${origin.x}`);
  assert.ok(Math.abs(origin.y - 0.100461) < 1e-6,
    `origin.y should be ty=0.100461, got ${origin.y}`);
  assert.ok(Math.abs(origin.z - (-0.077129)) < 1e-6,
    `origin.z should be tz=-0.077129, got ${origin.z}`);
});

// ─── Test 1.7 ────────────────────────────────────────────────────────────────
// camToJoint with forward transform matches Python camera_to_arm + polar_decompose
// for all 5 real arm log data points
test('camToJoint matches Python output for 5 real arm log data points', () => {
  var tf = initCameraToArmTransform();

  // Real arm log data: cam coords -> expected Python polar_decompose output
  // Point 5 has j3=-0.9433 which is out of J3 range [-0.9, 0.0], so valid=false
  var logData = [
    { cam: [0.494, -0.001, 0.004], j3: -0.863085, j4: 0.096461, j5: 0.242145, valid: true },
    { cam: [0.525,  0.020, 0.008], j3: -0.823637, j4: 0.092461, j5: 0.271882, valid: true },
    { cam: [0.541,  0.014, 0.011], j3: -0.832490, j4: 0.089461, j5: 0.288124, valid: true },
    { cam: [0.541,  0.033, 0.063], j3: -0.801246, j4: 0.037461, j5: 0.287526, valid: true },
    { cam: [0.578, -0.060, 0.089], j3: -0.943320, j4: 0.011461, j5: 0.332570, valid: false },
  ];

  for (var i = 0; i < logData.length; i++) {
    var d = logData[i];
    var result = camToJoint(tf, d.cam[0], d.cam[1], d.cam[2]);
    assert.ok(result !== null, 'point ' + i + ': result should not be null');

    if (d.valid) {
      assert.strictEqual(result.valid, true,
        'point ' + i + ': expected valid=true');
      assert.ok(Math.abs(result.j3 - d.j3) < 1e-3,
        'point ' + i + ': j3 expected ' + d.j3 + ' got ' + result.j3);
      assert.ok(Math.abs(result.j4 - d.j4) < 1e-3,
        'point ' + i + ': j4 expected ' + d.j4 + ' got ' + result.j4);
      assert.ok(Math.abs(result.j5 - d.j5) < 1e-3,
        'point ' + i + ': j5 expected ' + d.j5 + ' got ' + result.j5);
    } else {
      assert.strictEqual(result.valid, false,
        'point ' + i + ': expected valid=false (j3 out of range)');
    }
  }
});

// ─── Phi Compensation Tests ─────────────────────────────────────────────────

const { phiCompensation } = require('./cam_to_joint_shim.js');

// ─── Test 7.1 ────────────────────────────────────────────────────────────────
// phiCompensation zone1 applies positive offset for phi_deg <= 50.5
test('phiCompensation zone1 applies positive offset for phi_deg <= 50.5', () => {
  assert.equal(typeof phiCompensation, 'function', 'phiCompensation must be exported');
  // j3 = -0.5 rad => phi_deg = 28.6 => Zone1
  var result = phiCompensation(-0.5, 0.1);
  var expected = -0.5 + 0.014 * (1.0 + 0.5 * (0.1 / 0.6)) * 2 * Math.PI;
  assert.ok(Math.abs(result - expected) < 1e-9, `result ${result} should be near ${expected}`);
});

// ─── Test 7.2 ────────────────────────────────────────────────────────────────
// phiCompensation zone2 applies zero offset for 50.5 < phi_deg <= 60
test('phiCompensation zone2 applies zero offset for 50.5 < phi_deg <= 60', () => {
  var result = phiCompensation(-0.93, 0.2);
  assert.ok(Math.abs(result - (-0.93)) < 1e-9, `result ${result} should be -0.93`);
});

// ─── Test 7.3 ────────────────────────────────────────────────────────────────
// phiCompensation zone3 applies negative offset for phi_deg > 60
test('phiCompensation zone3 applies negative offset for phi_deg > 60', () => {
  var result = phiCompensation(-1.06, 0.3);
  var expected = -1.06 + (-0.014) * (1.0 + 0.5 * (0.3 / 0.6)) * 2 * Math.PI;
  assert.ok(Math.abs(result - expected) < 1e-9, `result ${result} should be near ${expected}`);
});
