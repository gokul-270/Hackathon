# Archived Code - yanthra_move

**Date Archived:** November 9, 2025  
**Reason:** ROS1 → ROS2 migration cleanup and monolithic → modular architecture refactor

---

## ⚠️ IMPORTANT: This Code is NOT COMPILED

All files in this directory are **legacy code** that is **NOT part of the active build**.

## Contents

### legacy_implementations/ (4 files, 2,675 lines)

#### yanthra_move_aruco_detect.cpp (1,086 lines)
- **What:** Legacy monolithic ArUco marker detection + cotton picking implementation (ROS1)
- **Status:** ❌ NOT COMPILED
- **Replaced by:** `motion_controller.cpp:1012-1057` (modern 45-line implementation)
- **⚠️ DANGER:** Contains `system("sudo poweroff")` calls - DO NOT USE OR COPY
- **ROS1 patterns:** Global variables, `ros::ServiceClient`, manual spin

#### yanthra_move_calibrate.cpp (909 lines)
- **What:** Legacy joint calibration routines (ROS1)
- **Status:** ❌ NOT COMPILED
- **Replaced by:** `arm_calibration: true` parameter (possibly)
- **Note:** Check if current system has calibration functionality before extracting

#### motor_controller_integration.cpp (421 lines)
- **What:** Abstraction layer for ODrive/MG6010 motor control with direct CAN access
- **Status:** ❌ NOT COMPILED
- **Replaced by:** `motor_control_ros2` service architecture
- **Better design:** Service-based ROS2 approach vs direct CAN control

#### performance_monitor.cpp (259 lines)
- **What:** System resource monitoring (CPU, memory, disk) with ROS2 diagnostics
- **Status:** ❌ NOT COMPILED
- **Use case:** Could be resurrected as optional monitoring node
- **Note:** Standalone implementation - could be moved to `common_utils` package if needed

---

### unused_headers/ (4 files, 582 lines)

#### yanthra_move_clean.h (149 lines)
- Legacy header with multiple include guards (malformed)
- Mode configuration macros (CALIBRATIONMODE, TEST140MODE, etc.)
- Not included anywhere in active code

#### yanthra_move_compatibility.hpp (53 lines)
- Compatibility layer for monolithic → modular transition
- Forward declarations for global variables
- Bridge layer no longer needed

#### yanthra_move_calibrate.h (130 lines)
- Header for `yanthra_move_calibrate.cpp`
- Function declarations for calibration routines

#### joint_move_sensor_msgs.h (250 lines)
- Sensor message utilities
- Not referenced in current code

---

## Current Active Architecture (Nov 2025)

**Modern Code (ACTIVE - COMPILED):**
```
src/yanthra_move_system_core.cpp           761 lines  ✅
src/yanthra_move_system_parameters.cpp     788 lines  ✅
src/yanthra_move_system_services.cpp       244 lines  ✅
src/yanthra_move_system_error_recovery.cpp 361 lines  ✅
src/yanthra_move_system_hardware.cpp       118 lines  ✅
src/yanthra_move_system_operation.cpp      358 lines  ✅
src/core/motion_controller.cpp           1,059 lines  ✅
src/coordinate_transforms.cpp               233 lines  ✅
src/joint_move.cpp                          177 lines  ✅
src/yanthra_utilities.cpp                   175 lines  ✅
src/transform_cache.cpp                     205 lines  ✅
```

**Total Active:** ~4,800 lines  
**Total Archived:** ~2,800 lines  
**Reduction:** 39% of codebase cleaned up

---

## Why Keep This Archive?

**Historical reference:**
- Understanding evolution of the system
- Extract algorithms if needed
- Document what was tried and replaced

**Not for production use:**
- Contains unsafe code (poweroff calls)
- ROS1 patterns incompatible with ROS2
- Superseded by better architecture

---

## If You Need Something From Here

### ✅ ArUco Detection
**Already working!** See `motion_controller.cpp:1012-1057`
```cpp
std::vector<geometry_msgs::msg::Point> MotionController::executeArucoDetection() {
    system("/usr/local/bin/aruco_finder --debug-images");
    // Reads centroid.txt and returns positions
}
```

### ❓ Calibration
Check if `arm_calibration: true` parameter in `config/production.yaml` works.  
If not, extract needed routines from `yanthra_move_calibrate.cpp`.

### ❓ Performance Monitoring
Consider resurrecting `performance_monitor.cpp` as standalone node if needed.  
Could be moved to `common_utils` package.

### ❓ Motor Control Integration
**Not needed.** Current service-based architecture is cleaner.  
See `motor_control_ros2` package instead.

---

## Can This Be Deleted?

**Recommendation:** Keep for 6-12 months, then evaluate.

**Why keep:**
- Reference for "why did we do it this way?"
- Extract algorithms if needed
- New team members can see evolution

**When to delete:**
- After confirming all functionality is replicated
- After 6+ months with no need to reference
- Never reference it? Then archive is working!

---

## Questions?

See main code review document: `/home/uday/Downloads/pragati_ros2/YANTHRA_MOVE_CODE_REVIEW.md`

**Last Updated:** November 9, 2025
