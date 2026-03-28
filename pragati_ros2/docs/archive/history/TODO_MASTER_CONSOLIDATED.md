# TODO Master List - Consolidated


**Last Updated:** 2025-11-01  
> **📌 AUTHORITY:** This is the **authoritative active TODO list**.
> 
> - **Purpose:** Actionable, deduplicated work items
> - **Source:** Consolidated from TODO_MASTER.md on 2025-10-15
> - **Maintenance:** Update this file for active work
> - **Historical Reference:** See `TODO_MASTER.md` for comprehensive backlog context
> - **✅ Milestone:** Hardware validation complete Oct 30, 2025
> - **✅ Milestone:** Detection latency validated Nov 1, 2025 (134ms avg)

**Generated:** 2025-10-15 17:47:58  
**Last Updated:** 2025-11-01 (Detection latency validation + docs update)  
**Total Active Items:** 113 (17 completed Oct 30 - Nov 1)  
**Archived:** 17 completed (Oct 30 breakthrough + Nov 1 validation)

---

## Summary

|||| Status | Count |
||--------|-------|
||| ✅ Completed (Oct 30 - Nov 1) | 17 |
||| Backlog | 36 |
||| Future/Parked | 7 |
||| Code TODOs | 70 |
||| **Total Active** | **113** |

### Code TODOs by Package (2025-10-21 Recount)

| Package | TODO Count | Primary Areas |
|---------|-----------|---------------|
| motor_control_ros2 | 9 | Hardware implementation, temperature reading, GPIO, safety |
| yanthra_move | 60 | Calibration, homing, ArUco detection, position offsets |
| cotton_detection_ros2 | 1 | Minor cleanup |
| **Total** | **70** | Full list: docs/_reports/2025-10-21/code_todos_complete.txt |

---

## ✅ Completed (Oct 30 - Nov 1, 2025)

### Hardware Validation Breakthrough (Oct 30)

**Completed Items:**
- ✅ **[HW-blocked] Hardware Validation** - Detection & motor control validated (Oct 29-30)
- ✅ **[HW-blocked] DepthAI C++ Integration** - 0-2ms detection achieved (was 7-8s)
- ✅ **[HW-blocked] MG6010 Hardware Validation** - 2-motor system tested, <5ms response
- ✅ **[HW-blocked] Spatial Coordinate Extraction** - ±10mm accuracy validated
- ✅ **[HW-blocked] Detection Pipeline Performance** - 30 FPS sustained, 100% reliability
- ✅ **[HW-blocked] Motor Command Delivery** - 100% reliability with `--times 3 --rate 2`
- ✅ **[HW-blocked] Queue Communication Errors** - Fixed with maxSize=4, blocking=true
- ✅ **[HW-blocked] Motor Count Mismatch** - Updated to 2-motor configuration
- ✅ **[HW-blocked] Position Control Validation** - Physical movement confirmed
- ✅ **[HW-blocked] Detection Accuracy Measurement** - ±10mm at 0.6m
- ✅ **[HW-blocked] DepthAI Pipeline Testing** - Camera & VPU operational
- ✅ **[HW-blocked] Device Connection Monitoring** - USB 3.0, 5Gbps confirmed
- ✅ **[HW-blocked] Performance Benchmarking** - All targets exceeded
- ✅ **[HW-blocked] System Integration** - Zero crashes, stable operation
- ✅ **[HW-blocked] Safety Systems Validation** - Thermal & stability confirmed

**Evidence:** See `../FINAL_VALIDATION_REPORT_2025-10-30.md`

### Detection Latency Validation (Nov 1)

**Completed Items:**
- ✅ **[SW-only] Detection Service Latency Measurement** - 134ms avg (123-218ms range)
  - Created persistent ROS2 client test tool (eliminates CLI overhead)
  - Validated true production latency vs 6s CLI tool artifact
  - 100% success rate over 10 consecutive calls
  - Evidence: Built and tested `test_persistent_client` on RPi

- ✅ **[SW-only] Documentation Updates** - Nov 1, 2025
  - Updated `PENDING_HARDWARE_TESTS.md` with latency validation results
  - Removed obsolete CottonDetect.py test (replaced by C++ integration)
  - Updated `STATUS_REPORT_2025-10-30.md` with Nov 1 findings
  - Created `CAMERA_COORDINATE_SYSTEM.md` (coordinate frame documentation)
  - Resolved ROS2 CLI hang misconception (tool overhead, not actual issue)

**Evidence:** See `docs/PENDING_HARDWARE_TESTS.md` and `STATUS_REPORT_2025-10-30.md`

**Total Completed:** 17 major items (15 hardware + 2 software validation)

---

## Active Backlog

### Medium Priority (53 items)

- [ ] **[T-PR2-2025-10-003b7095]** [SW-only] Master List - Pragati ROS2 Project
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:1`

- [ ] **[T-PR2-2025-10-a153ae54]** [SW-only] | 🆕 **Code s** | 70 | 3% | Extract & Prioritize |
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:25`

- [ ] **[T-PR2-2025-10-14445b2a]** [SW-only] - Source: `docs/_CONSOLIDATED.md` Section 1
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:55`

- [ ] **[T-PR2-2025-10-02b74809]** [HW-blocked] - Source: `docs/_CONSOLIDATED.md` "Hardware Validation"
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:85`

- [ ] **[T-PR2-2025-10-db199279]** [HW-assist] - Source: 9 code s in `src/motor_control_ros2/`
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:92`

- [ ] **[T-PR2-2025-10-e8e1873e]** [HW-assist] - Source: 4 code s in `src/cotton_detection_ros2/depthai_manager.cpp`
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:110`

- [ ] **[T-PR2-2025-10-3d4d123c]** [HW-assist] - Source: 6 code s in `src/yanthra_move/src/yanthra_move_system.cpp`
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:135`

- [ ] **[T-PR2-2025-10-361f8ac0]** [HW-assist] - Source: 23 code s in `src/yanthra_move/src/` (aruco_detect, calibrate)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:142`

- [ ] **[T-PR2-2025-10-047148c4]** [SW-only] - Source: `docs/_CONSOLIDATED.md` Category 3
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:168`

- [ ] **[T-PR2-2025-10-d013489c]** [SW-only] 1. **DepthAI Device Integration** - 4 s
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:284`

- [ ] **[T-PR2-2025-10-929fe95c]** [HW-blocked] 1. **MG6010 Hardware Validation** - 9 code s
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:378`

- [ ] **[T-PR2-2025-10-3b086617]** [HW-blocked] 1. **GPIO Hardware Implementation** - 6 code s
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:474`

- [ ] **[T-PR2-2025-10-31c44813]** [SW-only] 2. **Calibration & Tuning** - 23 code s
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:482`

- [ ] **[T-PR2-2025-10-e2d0790b]** [HW-assist] 2. **Cotton Detection Service Update** - Code
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:503`

- [ ] **[T-PR2-2025-10-ad4b7ca7]** [SW-only] 3. **Arm Status Functionality** - Code
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:509`

- [ ] **[T-PR2-2025-10-2581fa66]** [SW-only] 1. **Logging Enhancement** - Code
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:516`

- [ ] **[T-PR2-2025-10-11e144a3]** [SW-only] Additional Documentation (~200 s from docs/_CONSOLIDATED.md)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:544`

- [ ] **[T-PR2-2025-10-a281b073]** [SW-only] Unit Testing (~70 s from docs/_CONSOLIDATED.md)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:576`

- [ ] **[T-PR2-2025-10-4a999612]** [SW-only] Performance (~100 s from docs/_CONSOLIDATED.md)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:599`

- [ ] **[T-PR2-2025-10-d6a0c528]** [SW-only] Robustness (~80 s from docs/_CONSOLIDATED.md)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:626`

- [ ] **[T-PR2-2025-10-4beb882b]** [SW-only] 1. **docs/_CONSOLIDATED.md** (2,469 items)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:716`

- [ ] **[T-PR2-2025-10-079a7836]** [HW-assist] 1. **src/cotton_detection_ros2* (4 s)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:738`

- [ ] **[T-PR2-2025-10-155a2721]** [HW-blocked] - `depthai_manager.cpp` - Hardware integration s
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:739`

- [ ] **[T-PR2-2025-10-5da0713f]** [HW-assist] 2. **src/motor_control_ros2* (9 s)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:741`

- [ ] **[T-PR2-2025-10-e8ae0e94]** [HW-blocked] - `safety_monitor.cpp` - Hardware safety s
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:742`

- [ ] **[T-PR2-2025-10-592fa2cd]** [HW-assist] - `generic_hw_interface.cpp` - CAN implementation s
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:743`

- [ ] **[T-PR2-2025-10-c37fc971]** [HW-assist] - `generic_motor_controller.cpp` - Temperature reading
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:744`

- [ ] **[T-PR2-2025-10-fee641b3]** [HW-assist] 3. **src/yanthra_move* (29 s)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:746`

- [ ] **[T-PR2-2025-10-9fff6208]** [HW-assist] - `yanthra_move_system.cpp` - GPIO implementation s
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:747`

- [ ] **[T-PR2-2025-10-9be551ab]** [HW-assist] - `yanthra_move_aruco_detect.cpp` - Calibration s
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:748`

- [ ] **[T-PR2-2025-10-57c03a18]** [HW-assist] - `yanthra_move_calibrate.cpp` - Position/ROS2 s
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:749`

- [ ] **[T-PR2-2025-10-0e15c0ff]** [HW-assist] 4. **src/cotton_detection_ros2/scripts* (28 s)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:751`

- [ ] **[T-PR2-2025-10-29b35612]** [SW-only] - **Code s:** `docs/_code_todos_2025-10-15.txt` (70 lines)
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:762`

- [ ] **[T-PR2-2025-10-dbd3f88e]** [SW-only] 3. Add new s with proper categorization
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:799`

- [ ] **[T-PR2-2025-10-64a84bab]** [SW-only] > Note: This list is being consolidated into `docs/_MASTER.md`.
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:3`

- [ ] **[T-PR2-2025-10-5c377190]** [HW-blocked] **1.5 Spatial coordinate extraction** (needs hardware)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:25`

- [ ] **[T-PR2-2025-10-3f3978f0]** [HW-blocked] **1.6 Hardware testing** (needs hardware)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:26`

- [ ] **[T-PR2-2025-10-0ba62d9b]** [HW-assist] **2.4 Multi-camera support** (SKIPPED - not needed)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:32`

- [ ] **[T-PR2-2025-10-c97c96e6]** [SW-only] **3.5 Unit tests** (needs time)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:39`

- [ ] **[T-PR2-2025-10-fd9364cf]** [HW-blocked] **3.6 Integration tests** (needs hardware)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:40`

- [ ] **[T-PR2-2025-10-e06c28ff]** [HW-blocked] **3.8 Performance benchmarks** (needs hardware)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:42`

- [ ] **[T-PR2-2025-10-3fbaba48]** [SW-only] **5.5 Example code snippets** (quick task)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:59`

- [ ] **[T-PR2-2025-10-e5973ead]** [SW-only] **5.7 FAQ documentation** (quick task)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:61`

- [ ] **[T-PR2-2025-10-faa168b2]** [SW-only] **5.9 Release notes** (end of project)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:63`

- [ ] **[T-PR2-2025-10-89d08283]** [HW-blocked] **6.2 Hardware validation** (needs hardware)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:67`

- [ ] **[T-PR2-2025-10-e5abdf07]** [HW-blocked] **6.3 Performance testing** (needs hardware)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:68`

- [ ] **[T-PR2-2025-10-20eae3ad]** [SW-only] > Note: Overall production readiness is tracked in `docs/PRODUCTION_READINESS_GAP.md` and the active
  - **Component:** documentation
  - **Source:** `docs/project-management/COMPLETION_CHECKLIST.md:3`

- [ ] **[T-PR2-2025-10-cf0f7d16]** [HW-blocked] Hardware testing on Raspberry Pi (pending)
  - **Component:** documentation
  - **Source:** `docs/project-management/COMPLETION_CHECKLIST.md:257`

- [ ] **[T-PR2-2025-10-ed77e5ff]** [HW-blocked] Field testing with actual cotton (pending)
  - **Component:** documentation
  - **Source:** `docs/project-management/COMPLETION_CHECKLIST.md:258`

- [ ] **[T-PR2-2025-10-a4a79d4a]** [SW-only] All joints reach commanded positions (±0.5°)
  - **Component:** documentation
  - **Source:** `docs/project-management/IMPLEMENTATION_PLAN_OCT2025.md:452`

- [ ] **[T-PR2-2025-10-879259d3]** [HW-assist] Camera detects ArUco marker at 0.5m distance
  - **Component:** documentation
  - **Source:** `docs/project-management/IMPLEMENTATION_PLAN_OCT2025.md:453`

- [ ] **[T-PR2-2025-10-fcde604a]** [HW-assist] Pick accuracy: cotton location error < 10mm
  - **Component:** documentation
  - **Source:** `docs/project-management/IMPLEMENTATION_PLAN_OCT2025.md:454`

- [ ] **[T-PR2-2025-10-b32f03dd]** [SW-only] No error messages in logs
  - **Component:** documentation
  - **Source:** `docs/project-management/IMPLEMENTATION_PLAN_OCT2025.md:455`

---

## Future / Parked Items

- [ ] **[T-PR2-2025-10-b516a9eb]** > - Active backlog, future/parked, and code s remain here as the authoritative source.
  - **Component:** documentation
  - **Source:** `docs/TODO_MASTER.md:12`

- [ ] **[T-PR2-2025-10-7edf35f2]** **4.1 Dynamic reconfigure** (optional)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:47`

- [ ] **[T-PR2-2025-10-0021142a]** **4.2 Region of interest** (optional)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:48`

- [ ] **[T-PR2-2025-10-a1f26b6c]** **4.4 Batch processing** (optional)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:50`

- [ ] **[T-PR2-2025-10-47f1a2a9]** **4.5 Multi-threading optimization** (optional)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:51`

- [ ] **[T-PR2-2025-10-c4400332]** **4.6 Memory optimization** (optional)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:52`

- [ ] **[T-PR2-2025-10-0069ad92]** **5.6 Video tutorials** (optional)
  - **Component:** documentation
  - **Source:** `docs/project-management/REMAINING_TASKS.md:60`

---

## Code TODOs

### Cotton-Detection

- [ ] **[T-PR2-2025-10-a5ef3f47]** //  Check device connection status using DepthAI device API
  - **Source:** `src/cotton_detection_ros2/src/depthai_manager.cpp:166`
  - **Details:** `// TODO(hardware): Check device connection status using DepthAI device API`

- [ ] **[T-PR2-2025-10-e9122082]** //  Update FPS at runtime without reinitialization
  - **Source:** `src/cotton_detection_ros2/src/depthai_manager.cpp:329`
  - **Details:** `// TODO(hardware): Update FPS at runtime without reinitialization`

- [ ] **[T-PR2-2025-10-45a4744e]** //  Get actual device temperature from DepthAI API
  - **Source:** `src/cotton_detection_ros2/src/depthai_manager.cpp:399`
  - **Details:** `// TODO(hardware): Get actual device temperature from DepthAI API`

- [ ] **[T-PR2-2025-10-06995f99]** //  Get camera calibration from DepthAI device EEPROM
  - **Source:** `src/cotton_detection_ros2/src/depthai_manager.cpp:473`
  - **Details:** `// TODO(hardware): Get camera calibration from DepthAI device EEPROM`

- [ ] **[T-PR2-2025-10-eb2907a3]** These values should come from URDF or calibration
  - **Source:** `src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py:266`
  - **Details:** `# TODO: These values should come from URDF or calibration`

- [ ] **[T-PR2-2025-10-e10b65ad]** t_base_to_camera.transform.translation.x = 0.0    Get from calibration
  - **Source:** `src/cotton_detection_ros2/scripts/cotton_detect_ros2_wrapper.py:272`
  - **Details:** `t_base_to_camera.transform.translation.x = 0.0  # TODO: Get from calibration`

- [ ] **[T-PR2-2025-10-5720ab81]** y_muliplication_factor = -1   Hack for Coordinate System Unsync between OAK and Yanthra
  - **Source:** `src/cotton_detection_ros2/scripts/OakDTools/ArucoDetectYanthra.py:144`
  - **Details:** `y_muliplication_factor = -1  # Hack for Coordinate System Unsync between OAK and Yanthra TODO`

- [ ] **[T-PR2-2025-10-f0554122]** pass down parent PID or find a reliable
  - **Source:** `src/cotton_detection_ros2/scripts/OakDTools/CottonDetect_WorkingCode_6Apr2023.py:290`
  - **Details:** `## TODO pass down parent PID or find a reliable`

- [ ] **[T-PR2-2025-10-7eb21a4a]** We have to indicate it to yanthra
  - **Source:** `src/cotton_detection_ros2/scripts/OakDTools/CottonDetect.py:412`
  - **Details:** `#TODO:We have to indicate it to yanthra`

### Motor-Control

- [ ] **[T-PR2-2025-10-be359447]** // - OD_MOTOR_TEMPERATURE ( - motor winding temperature)
  - **Source:** `src/motor_control_ros2/src/generic_motor_controller.cpp:1111`
  - **Details:** `// - OD_MOTOR_TEMPERATURE (TBD - motor winding temperature)`

- [ ] **[T-PR2-2025-10-ac86e730]** // - OD_DRIVER_TEMPERATURE ( - driver board temperature)
  - **Source:** `src/motor_control_ros2/src/generic_motor_controller.cpp:1112`
  - **Details:** `// - OD_DRIVER_TEMPERATURE (TBD - driver board temperature)`

- [ ] **[T-PR2-2025-10-ac44580c]** //  Implement actual temperature reading when MG6010 protocol documentation
  - **Source:** `src/motor_control_ros2/src/generic_motor_controller.cpp:1118`
  - **Details:** `// TODO: Implement actual temperature reading when MG6010 protocol documentation`

- [ ] **[T-PR2-2025-10-9a98f40c]** //  Implement actual CAN ESTOP command:
  - **Source:** `src/motor_control_ros2/src/safety_monitor.cpp:564`
  - **Details:** `// TODO(hardware): Implement actual CAN ESTOP command:`

- [ ] **[T-PR2-2025-10-9773775a]** //  Implement GPIO shutdown:
  - **Source:** `src/motor_control_ros2/src/safety_monitor.cpp:573`
  - **Details:** `// TODO(hardware): Implement GPIO shutdown:`

- [ ] **[T-PR2-2025-10-9c2eace8]** //  Implement error LED:
  - **Source:** `src/motor_control_ros2/src/safety_monitor.cpp:583`
  - **Details:** `// TODO(hardware): Implement error LED:`

- [ ] **[T-PR2-2025-10-16397bf6]** //  Add velocity and effort reading when controller API available
  - **Source:** `src/motor_control_ros2/src/generic_hw_interface.cpp:346`
  - **Details:** `// TODO(hardware): Add velocity and effort reading when controller API available`

- [ ] **[T-PR2-2025-10-40a2f3d5]** //  Implement MG6010/MG4040 CAN reading when hardware available
  - **Source:** `src/motor_control_ros2/src/generic_hw_interface.cpp:355`
  - **Details:** `// TODO(hardware): Implement MG6010/MG4040 CAN reading when hardware available`

- [ ] **[T-PR2-2025-10-df730a75]** //  Add velocity and effort/torque control mode switching
  - **Source:** `src/motor_control_ros2/src/generic_hw_interface.cpp:399`
  - **Details:** `// TODO(hardware): Add velocity and effort/torque control mode switching`

- [ ] **[T-PR2-2025-10-421b19c9]** //  Implement MG6010/MG4040 CAN writing when hardware available
  - **Source:** `src/motor_control_ros2/src/generic_hw_interface.cpp:420`
  - **Details:** `// TODO(hardware): Implement MG6010/MG4040 CAN writing when hardware available`

- [ ] **[T-PR2-2025-10-ab811013]** //  Implement MG6010/MG4040 CAN initialization when hardware available
  - **Source:** `src/motor_control_ros2/src/generic_hw_interface.cpp:534`
  - **Details:** `// TODO(hardware): Implement MG6010/MG4040 CAN initialization when hardware available`

### Yanthra-Move

- [ ] **[T-PR2-2025-10-b0257aa0]** //  Port cotton_detection service to ROS2 or wrap as needed
  - **Source:** `src/yanthra_move/src/yanthra_move_aruco_detect.cpp:401`
  - **Details:** `// TODO: Port cotton_detection service to ROS2 or wrap as needed`

- [ ] **[T-PR2-2025-10-7a91107a]** joint_move_4.move_joint(joint4_homing_position, WAIT);  //  move it to joint4_homing_position
  - **Source:** `src/yanthra_move/src/yanthra_move_aruco_detect.cpp:683`
  - **Details:** `joint_move_4.move_joint(joint4_homing_position, WAIT);  // TODO(developer) move it to joint4_homing_position`

- [ ] **[T-PR2-2025-10-ddfeb26d]** joint_move_5.move_joint(joint5_homing_position, WAIT);   // Move joint5 fully back  change 0.001 to 
  - **Source:** `src/yanthra_move/src/yanthra_move_aruco_detect.cpp:721`
  - **Details:** `joint_move_5.move_joint(joint5_homing_position, WAIT);   // Move joint5 fully back TODO change 0.001 to joint_zero_poses[joint3_cnt]`

- [ ] **[T-PR2-2025-10-7e9d4321]** //  check whether the motor is still on or not
  - **Source:** `src/yanthra_move/src/yanthra_move_aruco_detect.cpp:806`
  - **Details:** `// TODO(developer) check whether the motor is still on or not`

- [ ] **[T-PR2-2025-10-630697c5]** joint_move_5.move_joint(joint5_homing_position, WAIT);  //  This homing Position is different from I
  - **Source:** `src/yanthra_move/src/yanthra_move_aruco_detect.cpp:991`
  - **Details:** `joint_move_5.move_joint(joint5_homing_position, WAIT);  // TODO(developer) This homing Position is different from Initialisation homing position but both can be same`

- [ ] **[T-PR2-2025-10-b1e0bfe9]** //  Implement keyboard monitoring for manual control
  - **Source:** `src/yanthra_move/src/yanthra_move_system.cpp:60`
  - **Details:** `// TODO(hardware): Implement keyboard monitoring for manual control`

- [ ] **[T-PR2-2025-10-1e06dd1f]** //  Implement keyboard monitoring cleanup
  - **Source:** `src/yanthra_move/src/yanthra_move_system.cpp:95`
  - **Details:** `// TODO(hardware): Implement keyboard monitoring cleanup`

- [ ] **[T-PR2-2025-10-344d2282]** //  Implement vacuum pump GPIO control
  - **Source:** `src/yanthra_move/src/yanthra_move_system.cpp:111`
  - **Details:** `// TODO(hardware): Implement vacuum pump GPIO control`

- [ ] **[T-PR2-2025-10-7f9d9c04]** //  Implement camera LED GPIO control
  - **Source:** `src/yanthra_move/src/yanthra_move_system.cpp:138`
  - **Details:** `// TODO(hardware): Implement camera LED GPIO control`

- [ ] **[T-PR2-2025-10-35d7095a]** //  Implement status LED GPIO control
  - **Source:** `src/yanthra_move/src/yanthra_move_system.cpp:153`
  - **Details:** `// TODO(hardware): Implement status LED GPIO control`

- [ ] **[T-PR2-2025-10-4ca26660]** //  Implement timestamped log file creation
  - **Source:** `src/yanthra_move/src/yanthra_move_system.cpp:170`
  - **Details:** `// TODO(enhancement): Implement timestamped log file creation`

- [ ] **[T-PR2-2025-10-eeace150]** //  Implement proper arm status functionality
  - **Source:** `src/yanthra_move/src/yanthra_move_system.cpp:2043`
  - **Details:** `// TODO: Implement proper arm status functionality`

- [ ] **[T-PR2-2025-10-7ff000eb]** // ros::spinOnce(); //  Replace with ROS2 executor pattern
  - **Source:** `src/yanthra_move/src/yanthra_move_calibrate.cpp:395`
  - **Details:** `// ros::spinOnce(); // TODO: Replace with ROS2 executor pattern`

- [ ] **[T-PR2-2025-10-da299398]** // rclcpp::shutdown(); //  Implement proper ROS2 shutdown
  - **Source:** `src/yanthra_move/src/yanthra_move_calibrate.cpp:403`
  - **Details:** `// rclcpp::shutdown(); // TODO: Implement proper ROS2 shutdown`

- [ ] **[T-PR2-2025-10-37cbbb93]** joint_move_3.move_joint(joint3_homing_position, WAIT);  //  change 0.001 to joint_zero_poses[joint3_
  - **Source:** `src/yanthra_move/src/yanthra_move_calibrate.cpp:679`
  - **Details:** `joint_move_3.move_joint(joint3_homing_position, WAIT);  // TODO(developer) change 0.001 to joint_zero_poses[joint3_cnt]`

- [ ] **[T-PR2-2025-10-67eb5d7c]** joint_move_5.move_joint(r-0.025, WAIT);     //  Jerky Motion  // Author Mani
  - **Source:** `src/yanthra_move/src/yanthra_move_calibrate.cpp:794`
  - **Details:** `joint_move_5.move_joint(r-0.025, WAIT);     // TODO(developer) Jerky Motion  // Author Mani`

- [ ] **[T-PR2-2025-10-387c49e5]** include <sensor_msgs/msg/JointState.hpp> // MR
  - **Source:** `src/yanthra_move/include/yanthra_move/joint_move_sensor_msgs.h:27`
  - **Details:** `#include <sensor_msgs/msg/JointState.hpp> // TODO:MR`

- [ ] **[T-PR2-2025-10-931c660c]** sensor_msgs::msg::JointState joint_state;// MR
  - **Source:** `src/yanthra_move/include/yanthra_move/joint_move_sensor_msgs.h:79`
  - **Details:** `sensor_msgs::msg::JointState joint_state;// TODO:MR`

- [ ] **[T-PR2-2025-10-ad6fd455]** joint_status = nh.subscribe(name + "state", 10, &joint_move::joint_state_cb, this);// MR
  - **Source:** `src/yanthra_move/include/yanthra_move/joint_move_sensor_msgs.h:99`
  - **Details:** `joint_status = nh.subscribe(name + "state", 10, &joint_move::joint_state_cb, this);// TODO:MR`

- [ ] **[T-PR2-2025-10-5b72d8a5]** //  this write  Routine need not be called for every write
  - **Source:** `src/yanthra_move/include/yanthra_move/joint_move_sensor_msgs.h:220`
  - **Details:** `// TODO this write  Routine need not be called for every write`

- [ ] **[T-PR2-2025-10-4db67f24]** //  Need a seperate function where we pass the motorid/jointid and the
  - **Source:** `src/yanthra_move/include/yanthra_move/joint_move_sensor_msgs.h:223`
  - **Details:** `// TODO Need a seperate function where we pass the motorid/jointid and the`

- [ ] **[T-PR2-2025-10-767d5d7c]** define THETA_MIN  (-2.3561925)  // -135 deg  URDF limit is -110 deg
  - **Source:** `src/yanthra_move/include/yanthra_move/yanthra_move_calibrate.h:82`
  - **Details:** `#define THETA_MIN  (-2.3561925)  // -135 deg TODO URDF limit is -110 deg`

- [ ] **[T-PR2-2025-10-4089d85c]** define THETA_MAX  (2.3561925)   // 135 deg   URDF limit is +110 deg
  - **Source:** `src/yanthra_move/include/yanthra_move/yanthra_move_calibrate.h:83`
  - **Details:** `#define THETA_MAX  (2.3561925)   // 135 deg  TODO URDF limit is +110 deg`

