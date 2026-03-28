// Standalone implementation of camToJoint for unit testing.
// Must stay numerically identical to the camToJoint() function in testing_ui.js.
'use strict';

var CAM_SEQ_J5_OFFSET = 0.320;
var CAM_SEQ_J3_MIN    = -0.9;
var CAM_SEQ_J3_MAX    =  0.0;
var CAM_SEQ_J4_MIN    = -0.250;
var CAM_SEQ_J4_MAX    =  0.350;
var CAM_SEQ_J5_MIN    =  0.0;
var CAM_SEQ_J5_MAX    =  0.450;

function camToJoint(tf4x4, cam_x, cam_y, cam_z) {
    var arm = tf4x4.apply(cam_x, cam_y, cam_z);
    var ax = arm.x, ay = arm.y, az = arm.z;
    var r  = Math.sqrt(ax * ax + az * az);
    var j3 = (r > 1e-9) ? Math.asin(az / r) : 0.0;
    var j4 = ay;
    var j5 = r - CAM_SEQ_J5_OFFSET;
    if (j3 < CAM_SEQ_J3_MIN || j3 > CAM_SEQ_J3_MAX ||
        j4 < CAM_SEQ_J4_MIN || j4 > CAM_SEQ_J4_MAX ||
        j5 < CAM_SEQ_J5_MIN || j5 > CAM_SEQ_J5_MAX) {
        return { valid: false };
    }
    return { valid: true, j3: j3, j4: j4, j5: j5 };
}

module.exports = { camToJoint: camToJoint };

