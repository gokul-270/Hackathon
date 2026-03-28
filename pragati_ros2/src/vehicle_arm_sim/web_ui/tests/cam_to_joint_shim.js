// Standalone implementation of camToJoint for unit testing.
// Must stay numerically identical to the camToJoint() function in testing_ui.js.
'use strict';

// ─── Shared configuration object ────────────────────────────────────────────
var CAM_JOINT_CONFIG = {
    // Degenerate radius threshold (matches Python fk_chain denom > 1e-6)
    R_THRESHOLD: 1e-6,

    // Hardware offset: distance from yanthra_link to J5 origin (m)
    HARDWARE_OFFSET: 0.320,

    // Joint limits
    J3_MIN: -0.9,    // rad
    J3_MAX:  0.0,    // rad
    J4_MIN: -0.250,  // m
    J4_MAX:  0.350,  // m
    J5_MIN:  0.0,    // m
    J5_MAX:  0.450,  // m

    // Phi compensation
    PHI_ZONE1_MAX_DEG: 50.5,
    PHI_ZONE2_MAX_DEG: 60.0,
    PHI_ZONE1_OFFSET:  0.014,
    PHI_ZONE2_OFFSET:  0.0,
    PHI_ZONE3_OFFSET: -0.014,
    PHI_L5_SCALE:      0.5,
    PHI_JOINT5_MAX:    0.450,

    // URDF camera_link transform
    CAMERA_LINK_XYZ: [0.016845, 0.100461, -0.077129],
    CAMERA_LINK_RPY: [1.5708, 0.785398, 0.0],
};

function camToJoint(tf4x4, cam_x, cam_y, cam_z) {
    var arm = tf4x4.apply(cam_x, cam_y, cam_z);
    var ax = arm.x, ay = arm.y, az = arm.z;
    var r  = Math.sqrt(ax * ax + az * az);
    if (r < CAM_JOINT_CONFIG.R_THRESHOLD) { return null; }
    var j3 = (r > CAM_JOINT_CONFIG.R_THRESHOLD) ? Math.asin(az / r) : 0.0;
    var j4 = ay;
    var j5 = r - CAM_JOINT_CONFIG.HARDWARE_OFFSET;
    if (j3 < CAM_JOINT_CONFIG.J3_MIN || j3 > CAM_JOINT_CONFIG.J3_MAX ||
        j4 < CAM_JOINT_CONFIG.J4_MIN || j4 > CAM_JOINT_CONFIG.J4_MAX ||
        j5 < CAM_JOINT_CONFIG.J5_MIN || j5 > CAM_JOINT_CONFIG.J5_MAX) {
        return { valid: false };
    }
    return { valid: true, j3: j3, j4: j4, j5: j5 };
}

function phiCompensation(j3, j5) {
    var phiDeg = Math.abs(j3 * 180.0 / Math.PI);
    var baseOffset;
    if (phiDeg <= CAM_JOINT_CONFIG.PHI_ZONE1_MAX_DEG) {
        baseOffset = CAM_JOINT_CONFIG.PHI_ZONE1_OFFSET;
    } else if (phiDeg <= CAM_JOINT_CONFIG.PHI_ZONE2_MAX_DEG) {
        baseOffset = CAM_JOINT_CONFIG.PHI_ZONE2_OFFSET;
    } else {
        baseOffset = CAM_JOINT_CONFIG.PHI_ZONE3_OFFSET;
    }
    var l5Norm = Math.max(0.0, j5) / CAM_JOINT_CONFIG.PHI_JOINT5_MAX;
    var l5Scale = 1.0 + CAM_JOINT_CONFIG.PHI_L5_SCALE * l5Norm;
    var compRot = baseOffset * l5Scale;
    var compRad = compRot * 2.0 * Math.PI;
    return j3 + compRad;
}

function initCameraToArmTransform() {
    var xyz = CAM_JOINT_CONFIG.CAMERA_LINK_XYZ;
    var rpy = CAM_JOINT_CONFIG.CAMERA_LINK_RPY;
    var tx = xyz[0], ty = xyz[1], tz = xyz[2];
    var roll = rpy[0], pitch = rpy[1], yaw = rpy[2];

    var cr = Math.cos(roll), sr = Math.sin(roll);
    var cp = Math.cos(pitch), sp = Math.sin(pitch);
    var cy = Math.cos(yaw), sy = Math.sin(yaw);

    // Forward rotation R = Rz(yaw) @ Ry(pitch) @ Rx(roll)
    var r00 = cy*cp, r01 = cy*sp*sr - sy*cr, r02 = cy*sp*cr + sy*sr;
    var r10 = sy*cp, r11 = sy*sp*sr + cy*cr, r12 = sy*sp*cr - cy*sr;
    var r20 = -sp,   r21 = cp*sr,             r22 = cp*cr;

    // Forward transform: arm_xyz = R @ cam_xyz + t
    return {
        apply: function(x, y, z) {
            return {
                x: r00*x + r01*y + r02*z + tx,
                y: r10*x + r11*y + r12*z + ty,
                z: r20*x + r21*y + r22*z + tz,
            };
        }
    };
}

module.exports = {
    camToJoint: camToJoint,
    phiCompensation: phiCompensation,
    initCameraToArmTransform: initCameraToArmTransform,
    CAM_JOINT_CONFIG: CAM_JOINT_CONFIG,
};
