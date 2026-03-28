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
