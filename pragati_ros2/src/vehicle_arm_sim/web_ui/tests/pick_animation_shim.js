'use strict';

// Standalone testable implementation of pick animation functions.
// Must stay behaviourally identical to the animation code in testing_ui.js.

// Arm topic configs — mirrors ARM_CONFIGS in testing_ui.js
var ARM_CONFIGS = {
    arm1: { j3: '/joint3_cmd',          j4: '/joint4_cmd',          j5: '/joint5_cmd'          },
    arm2: { j3: '/joint3_copy_cmd',     j4: '/joint4_copy_cmd',     j5: '/joint5_copy_cmd'     },
    arm3: { j3: '/arm_joint3_copy1_cmd', j4: '/arm_joint4_copy1_cmd', j5: '/arm_joint5_copy1_cmd' },
};

// Hold durations (ms) after each animation step
var HOLD_J4_LATERAL = 800;
var HOLD_J3_TILT    = 800;
var HOLD_J5_EXTEND  = 1400;
var HOLD_J5_RETRACT = 800;
var HOLD_J3_HOME    = 800;
var HOLD_J4_HOME    = 900;

// Gap between triple-publish repetitions
var TRIPLE_PUBLISH_GAP = 500;

/**
 * Publish a joint command 3 times with 500ms gaps for reliable delivery.
 * @param {string} topic - ROS topic name
 * @param {number} value - Joint command value
 * @param {object} deps - { publishArmJoint, sleep }
 */
async function triplePublish(topic, value, deps) {
    for (var i = 0; i < 3; i++) {
        deps.publishArmJoint(topic, value);
        if (i < 2) {
            await deps.sleep(TRIPLE_PUBLISH_GAP);
        }
    }
}

/**
 * Execute the full pick animation sequence for one cotton on one arm.
 * Steps: J4→J3→J5(extend)→mark-picked→J5(retract)→J3(home)→J4(home)
 * @param {string} armKey - 'arm1', 'arm2', or 'arm3'
 * @param {string} cottonName - e.g. 'cotton_0'
 * @param {number} j3 - target J3 value (rad)
 * @param {number} j4 - target J4 value (m)
 * @param {number} j5 - target J5 value (m)
 * @param {object} deps - { publishArmJoint, sleep, updateSliderUI, fetch, estopActive, pickAborted }
 */
async function executePickAnimation(armKey, cottonName, j3, j4, j5, deps) {
    var cfg = ARM_CONFIGS[armKey];
    if (!cfg) { throw new Error('Unknown arm: ' + armKey); }

    // Helper to check abort conditions
    function shouldAbort() {
        // Support both property access and getter
        var estop = typeof deps.estopActive === 'function' ? deps.estopActive() : deps.estopActive;
        var abort = typeof deps.pickAborted === 'function' ? deps.pickAborted() : deps.pickAborted;
        return estop || abort;
    }

    // Step 1: J4 lateral
    if (shouldAbort()) return;
    await triplePublish(cfg.j4, j4, deps);
    await deps.sleep(HOLD_J4_LATERAL);

    // Step 2: J3 tilt
    if (shouldAbort()) return;
    await triplePublish(cfg.j3, j3, deps);
    await deps.sleep(HOLD_J3_TILT);

    // Step 3: J5 extend
    if (shouldAbort()) return;
    await triplePublish(cfg.j5, j5, deps);
    await deps.sleep(HOLD_J5_EXTEND);

    // Step 4: mark-picked
    if (shouldAbort()) return;
    await deps.fetch('/api/cotton/' + cottonName + '/mark-picked', {
        method: 'POST',
    });

    // Step 5: J5 retract
    if (shouldAbort()) return;
    await triplePublish(cfg.j5, 0, deps);
    await deps.sleep(HOLD_J5_RETRACT);

    // Step 6: J3 home
    if (shouldAbort()) return;
    await triplePublish(cfg.j3, 0, deps);
    await deps.sleep(HOLD_J3_HOME);

    // Step 7: J4 home
    if (shouldAbort()) return;
    await triplePublish(cfg.j4, 0, deps);
    await deps.sleep(HOLD_J4_HOME);
}

module.exports = {
    triplePublish: triplePublish,
    executePickAnimation: executePickAnimation,
    ARM_CONFIGS: ARM_CONFIGS,
};
