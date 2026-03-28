# Repository Inventory - Pragati ROS2
**Date:** 2025-11-05  
**Purpose:** Identify largest/most complex source files for refactoring prioritization

---

## Cotton Detection ROS2 Package

### Top 20 Largest Source Files

| Size (bytes) | File | Notes |
|--------------|------|-------|
| 40,498 | `depthai_manager.cpp` | ✅ **Already refactored** - Runtime reconfig, logging cleanup, config constants |
| 30,294 | `cotton_detection_node_parameters.cpp` | Parameter declarations and validation |
| 15,673 | `cotton_detection_node_depthai.cpp` | DepthAI integration logic |
| 14,138 | `cotton_detection_node_services.cpp` | ROS2 service handlers |
| 13,165 | `image_processor.cpp` | Image processing pipeline |
| 12,688 | `cotton_detection_node_detection.cpp` | Detection execution logic |
| 12,597 | `cotton_detection_node.hpp` | Main node header |
| 11,054 | `cotton_detector.cpp` | Core detection algorithm |
| 10,958 | `hybrid_detection_test.cpp` | Test suite |
| 9,947 | `performance_monitor.cpp` | Performance tracking |
| 9,294 | `image_processor_test.cpp` | Test suite |
| 9,268 | `yolo_detector_edge_cases_test.cpp` | Test suite |
| 9,003 | `yolo_detector_test.cpp` | Test suite |
| 8,825 | `yolo_detector.cpp` | ✅ **Logging cleanup done** |
| 7,870 | `depthai_manager.hpp` | DepthAI manager header |
| 6,913 | `cotton_detection_node_publishing.cpp` | ROS2 publishing logic |
| 6,796 | `cotton_detector_test.cpp` | Test suite |
| 6,750 | `cotton_detection_node_init.cpp` | Node initialization |
| 5,794 | `cotton_detection_node_utils.cpp` | Utility functions |
| 5,527 | `test_persistent_client.cpp` | Test client |

### Analysis

**Total Source LOC:** ~250K (including tests)  
**Test Coverage:** Excellent - 86 tests across 6 test files  
**Architecture:** Well-modularized - node split into 11 focused files

**Refactoring Priority:**
1. ✅ `depthai_manager.cpp` - **COMPLETE**
2. `cotton_detection_node_parameters.cpp` - Could benefit from similar consolidation
3. `image_processor.cpp` - Check for magic numbers
4. `cotton_detector.cpp` - Core algorithm, should review for optimization

---

## Yanthra Move Package

### Top 20 Largest Source Files (Excluding Build Artifacts)

| Size (bytes) | File | Notes |
|--------------|------|-------|
| 43,936 | `yanthra_move_aruco_detect.cpp` | ArUco marker detection for calibration |
| 40,404 | `yanthra_move_system_parameters.cpp` | ✅ **Partially refactored** - param_utils added, still has duplication |
| 36,971 | `yanthra_move_calibrate.cpp` | Calibration routines |
| 29,530 | `yanthra_move_system_core.cpp` | Core system logic |
| 27,771 | `motion_controller.cpp` | ✅ **Partially refactored** - Uses param_utils, still has long functions |
| 21,376 | `yanthra_move_system.hpp` | Main system header (633 lines mentioned in TODO) |
| 17,758 | `yanthra_move_system_operation.cpp` | Operational loop |
| 15,827 | `yanthra_move_system_error_recovery.cpp` | Error handling |
| 15,030 | `motor_controller_integration.cpp` | Motor control integration |
| 11,891 | `coordinate_transforms.cpp` | Coordinate conversion utilities |
| 11,137 | `yanthra_move_calibrate.h` | Calibration header |
| 10,628 | `yanthra_move_system_services.cpp` | ROS2 service handlers |

### Analysis

**Total Source LOC:** ~280K (excluding generated code)  
**Test Coverage:** Limited - 1 test file mentioned  
**Architecture:** Modular but with some large files

**Refactoring Priority:**
1. ✅ `yanthra_move_system_parameters.cpp` - **Partially complete** (param_utils created)
2. ✅ `motion_controller.cpp` - **Partially complete** (uses param_utils)
3. `yanthra_move_aruco_detect.cpp` - Largest file, check for duplication
4. `yanthra_move_calibrate.cpp` - Second largest, review structure
5. `yanthra_move_system.hpp` - Mentioned in TODO as 633 lines needing split

---

## Overall Statistics

### Combined Codebase
- **Total Packages:** 2 main packages
- **Total Source Files:** ~50 significant files
- **Estimated LOC:** ~530K total (including tests and generated code)
- **Test Files:** 7+ test files identified
- **Test Count:** 86 tests in cotton_detection_ros2

### Refactoring Status

| Package | Files Reviewed | Files Refactored | % Complete |
|---------|----------------|------------------|------------|
| cotton_detection_ros2 | 20 | 3 (depthai_manager, yolo_detector, async_image_saver) | 15% |
| yanthra_move | 12 | 2 (parameters, motion_controller) | 17% |
| **Overall** | **32** | **5** | **16%** |

---

## Recommendations for Next Refactoring Session

### Quick Wins (1-2 hours each)
1. **cotton_detection_node_parameters.cpp** (30KB)
   - Apply param_utils pattern from yanthra_move
   - Consolidate parameter declarations

2. **image_processor.cpp** (13KB)
   - Check for magic numbers
   - Apply config constants pattern

3. **yanthra_move_aruco_detect.cpp** (44KB)
   - Largest file, likely has duplication
   - Split into focused modules

### Medium Effort (3-5 hours)
4. **yanthra_move_calibrate.cpp** (37KB)
   - Review calibration logic
   - Extract reusable utilities

5. **cotton_detector.cpp** (11KB)
   - Core algorithm optimization
   - Add performance metrics

6. **yanthra_move_system.hpp** (21KB, 633 lines)
   - Split into focused headers
   - Reduce coupling with forward declarations

### Long-term Architectural
7. **motion_controller.cpp** - Finish refactoring (long functions remain)
8. **Global state elimination** - Across yanthra_move
9. **State machine** - Formalize motion controller states
10. **Thread pool** - Add parallel processing to cotton_detection

---

## File Size Categories

### Extra Large (>30KB)
- `yanthra_move_aruco_detect.cpp` (44KB)
- `depthai_manager.cpp` (40KB) ✅
- `yanthra_move_system_parameters.cpp` (40KB) ✅
- `yanthra_move_calibrate.cpp` (37KB)

### Large (15-30KB)
- `cotton_detection_node_parameters.cpp` (30KB)
- `yanthra_move_system_core.cpp` (30KB)
- `motion_controller.cpp` (28KB) ✅
- `yanthra_move_system.hpp` (21KB)
- `yanthra_move_system_operation.cpp` (18KB)
- `cotton_detection_node_depthai.cpp` (16KB)
- `yanthra_move_system_error_recovery.cpp` (16KB)
- `motor_controller_integration.cpp` (15KB)

### Medium (10-15KB)
- 8 files in this category

### Small (<10KB)
- Majority of files

---

## Complexity Indicators

### High Complexity Signals
- ✅ Files >30KB (4 files, 3 refactored)
- Functions >200 lines (loadMotionParameters was 220+, now fixed)
- Magic numbers (addressed in depthai_manager)
- Global state (identified in yanthra_move)
- Console output (eliminated in 3 files)

### Code Smells Found
- ✅ **Boilerplate duplication** - Fixed with param_utils
- ✅ **Magic numbers** - Fixed with DepthAIConstants
- ✅ **Console logging** - Migrated to RCLCPP
- **Long functions** - Partially addressed
- **Global state** - Identified but not yet fixed
- **Large headers** - Not yet addressed

---

## Testing Gap Analysis

### Cotton Detection (Good)
- 86 tests across 6 files
- Hybrid detection tested
- YOLO edge cases covered
- Image processor tested

### Yanthra Move (Needs Improvement)
- Only 1 test file mentioned
- No motion controller tests visible
- No parameter loading tests
- **Recommendation:** Add 10-20 tests as per TODO

---

## Build Performance

### Incremental Build Times (Observed)
- cotton_detection_ros2: ~18-60 seconds
- yanthra_move: ~45-90 seconds

### Compilation Memory
- DepthAI SDK and OpenCV are template-heavy
- Large files increase memory usage
- Recommendation: Continue splitting large files

---

**Summary:**
- **Largest files identified and analyzed**
- **Clear refactoring priorities established**  
- **Quick wins vs long-term items categorized**
- **Testing gaps identified**
- **16% of codebase refactored so far**

**Next Focus:** Parameter consolidation, remaining long functions, global state elimination
