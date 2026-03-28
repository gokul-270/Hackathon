# Cotton Detection Migration to ROS2 Topics - Implementation Guide

## Status: 8/18 Tasks Complete ✅

This guide provides detailed instructions for completing the remaining 10 tasks to migrate from file/service-based cotton detection to pure ROS2 topic-based architecture.

---

## ✅ COMPLETED TASKS (8/18)

### Task 1: Create cleanup branch and inventory ✅
- Branch created: `feature/ros2-direct-cotton-detection`
- Inventory completed of all cotton detection references

### Task 2: Centralize subscription in YanthraMoveSystem ✅  
- Design decision: Subscribe ONLY in YanthraMoveSystem
- MotionController consumes via internal buffer (dependency injection)

### Task 3: Add ROS2 subscription in YanthraMoveSystem ✅
- File: `src/yanthra_move/src/yanthra_move_system.cpp`
- Subscription created to `/cotton_detection/results`
- Thread-safe buffer with mutex protection
- Provider callback for MotionController access
- Type-erased storage to avoid header pollution

### Task 4: Update MotionController to consume from buffer provider ✅
- Files: `src/yanthra_move/include/yanthra_move/core/motion_controller.hpp`, `src/yanthra_move/src/core/motion_controller.cpp`
- Provider-based initialize signature landed; extern usage removed
- Operational cycle now pulls optional vectors via injected lambda with graceful fallbacks

### Task 5: Remove file-based stub get_cotton_coordinates ✅
- Legacy stub deleted from `yanthra_move_system.cpp`
- Topic-backed cache + mutexed buffer now authoritative source

### Task 6: Remove robust service client ✅
- `robust_cotton_detection_client.cpp` moved out of build (archived under `src/yanthra_move/archive/legacy/`)
- CMakeLists/package manifest already exclude the legacy target

### Task 7: Disable legacy bridge script ✅
- `cotton_detection_bridge.py` archived; setup entry points and launch files cleaned
- README now calls out wrapper-only legacy usage

### Task 11: Wire MotionController to provider in YanthraMoveSystem ✅
- `initializeModularComponents()` injects provider callback during controller startup
- Motion controller now fully decoupled from file system artifacts

---

## 🔄 REMAINING TASKS (10/18)

### Task 8: Verify cotton_detection_ros2 publishing
**Status:** Needs verification  
**Files to check:**
- `src/cotton_detection_ros2/src/cotton_detection_node.cpp`

**Verification checklist:**

1. Confirm publish_detection_result() called after all detection paths
2. Verify message structure matches:
   - `positions[]` array of CottonPosition
   - `total_count`
   - `detection_successful`
   - `processing_time_ms`
   - `header` with timestamp
3. Topic name: `/cotton_detection/results`
4. QoS settings:
   - Reliability: Reliable
   - History: KeepLast(10)
   - Durability: Volatile

---

### Task 9: Add offline/camera mode parameters
**Status:** Needs implementation  
**Files to modify:**
- `src/cotton_detection_ros2/config/cotton_detection_params.yaml`
- `src/cotton_detection_ros2/src/cotton_detection_node.cpp`

**Changes needed:**

1. **In params.yaml**, add:
```yaml
cotton_detection_node:
  ros__parameters:
    # Existing params...
    
    # Mode selection
    mode: "camera"  # Options: "camera", "offline"
    
    # Camera mode
    camera_topic: "/camera/image_raw"
    
    # Offline mode
    image_directory: "/data/cotton_images"
    offline_processing_rate_hz: 1.0
```

2. **In cotton_detection_node.cpp**, implement mode switching logic

---

### Task 10: Keep essential detection service
**Status:** Needs implementation  
**Files to modify:**
- `src/cotton_detection_ros2/src/cotton_detection_node.cpp`

**Changes needed:**

1. Keep `/cotton_detection/detect` service for manual testing
2. Remove `/cotton_detection/detect_cotton_srv` (legacy)
3. Ensure service also publishes to `/cotton_detection/results`

---

### Task 12: Clean up legacy service integrations
**Status:** Needs review  
**Files to check:**
- `src/yanthra_move/src/yanthra_move_aruco_detect.cpp`
- `src/yanthra_move/src/yanthra_move_calibrate.cpp`

**Changes needed:**

1. Remove or deprecate legacy cotton detection service calls
2. Add comments indicating deprecated status
3. Consider removing these files to archive if unused

---

### Task 13: Update CMakeLists.txt dependencies ✅
**Status:** COMPLETED (done in Task 3)  
Already added cotton_detection_ros2 to:
- `find_package()`
- `YANTHRA_DEPENDENCIES` list
- `package.xml`

---

### Task 14: Update launch files
**Status:** Needs implementation  
**Files to modify:**
- All cotton_detection_ros2 launch files
- All yanthra_move launch files

**Changes needed:**

1. Remove all cotton_detection_bridge references
2. Add mode parameter examples:
```python
# Camera mode example
DeclareLaunchArgument('mode', default_value='camera'),
DeclareLaunchArgument('camera_topic', default_value='/camera/image_raw'),

# Offline mode example  
DeclareLaunchArgument('mode', default_value='offline'),
DeclareLaunchArgument('image_directory', default_value='/data/images'),
```

---

### Task 15: Test offline mode end-to-end
**Status:** Ready for testing after Tasks 4-14  
**Test commands:**

```bash
# Build
colcon build --symlink-install
source install/setup.bash

# Launch offline mode
ros2 launch cotton_detection_ros2 cotton_detection.launch.py \
  mode:=offline \
  image_directory:=/path/to/test/images

# Launch yanthra_move
ros2 launch yanthra_move yanthra_move.launch.py

# Verify
ros2 topic echo /cotton_detection/results
ros2 topic hz /cotton_detection/results
```

**Verification checklist:**
- [ ] DetectionResult messages published
- [ ] MotionController receives positions
- [ ] Logs show buffer updates
- [ ] System handles zero detections gracefully
- [ ] System handles many detections correctly

---

### Task 16: Test camera mode end-to-end
**Status:** Ready for testing after Tasks 4-14  
**Test commands:**

```bash
# Launch camera source
ros2 run usb_cam usb_cam_node_exe --ros-args \
  -p video_device:=/dev/video0

# Launch detection (camera mode)
ros2 launch cotton_detection_ros2 cotton_detection.launch.py \
  mode:=camera \
  camera_topic:=/camera/image_raw

# Launch yanthra_move  
ros2 launch yanthra_move yanthra_move.launch.py

# Monitor
ros2 topic hz /cotton_detection/results
ros2 topic echo /cotton_detection/results --no-arr
```

---

### Task 17: Validate QoS and message loss resilience
**Status:** Ready for testing after Task 16  
**Test scenarios:**

1. **Late join test:**
   - Start cotton_detection first
   - Wait 10 seconds
   - Start yanthra_move
   - Verify it receives detections

2. **Message rate test:**
   ```bash
   ros2 topic hz /cotton_detection/results
   ros2 topic bw /cotton_detection/results
   ```

3. **No detection timeout:**
   - Stop cotton_detection
   - Verify yanthra_move logs timeout warnings
   - Verify graceful degradation

---

### Task 18: Finalize cleanup and documentation
**Status:** Final step  
**Tasks:**

1. **Remove unused files:**
   - Archive or delete bridge script
   - Archive or delete robust client
   - Archive unused calibration tools

2. **Update README files:**
   - Document topic-based architecture
   - Add mode parameter examples
   - Update launch command examples

3. **Update CHANGELOG:**
   ```markdown
   ## [2.0.0] - 2025-01-XX
   ### Breaking Changes
   - Removed file-based cotton_detection_bridge.py
   - Removed service-based robust_cotton_detection_client
   - Migrated to pure ROS2 topic architecture
   
   ### Added
   - Direct ROS2 topic subscription in YanthraMoveSystem
   - Thread-safe buffer with provider pattern
   - Offline and camera mode support in cotton_detection
   ```

4. **Run linters:**
   ```bash
   ament_cpplint src/yanthra_move/src/core/motion_controller.cpp
   ament_cpplint src/yanthra_move/src/yanthra_move_system.cpp
   ```

5. **Final build test:**
   ```bash
   colcon build --packages-select yanthra_move cotton_detection_ros2
   colcon test --packages-select yanthra_move cotton_detection_ros2
   ```

---

## Quick Reference Commands

### Build and Source
```bash
cd /home/uday/Downloads/pragati_ros2
colcon build --symlink-install --packages-select yanthra_move cotton_detection_ros2
source install/setup.bash
```

### Run Tests
```bash
# Unit tests
colcon test --packages-select yanthra_move

# Integration test - offline
ros2 launch yanthra_move test_offline_detection.launch.py

# Integration test - camera
ros2 launch yanthra_move test_camera_detection.launch.py
```

### Debug Commands
```bash
# Monitor topic
ros2 topic echo /cotton_detection/results

# Check topic info
ros2 topic info /cotton_detection/results -v

# Monitor logs
ros2 run rqt_console rqt_console
```

---

## Implementation Order Recommendation

1. **Phase 1: Core Integration (Tasks 4-6)**
   - Update MotionController to use provider
   - Remove file-based stub
   - Remove robust client
   - **Test:** Verify compilation

2. **Phase 2: Legacy Cleanup (Tasks 7, 12)**
   - Remove/archive bridge script
   - Clean up legacy tools
   - **Test:** Verify no broken dependencies

3. **Phase 3: Cotton Detection Enhancement (Tasks 8-10)**
   - Verify publishing behavior
   - Add offline/camera modes
   - Clean up service interface
   - **Test:** Test cotton_detection standalone

4. **Phase 4: System Integration (Tasks 11, 14)**
   - Wire MotionController in YanthraMoveSystem
   - Update launch files
   - **Test:** End-to-end offline mode

5. **Phase 5: Validation (Tasks 15-17)**
   - Test offline mode thoroughly
   - Test camera mode thoroughly
   - Validate QoS and resilience

6. **Phase 6: Documentation (Task 18)**
   - Update all documentation
   - Run linters and CI
   - Create PR for review

---

## Success Criteria

- ✅ No compilation errors or warnings
- ✅ All unit tests pass
- ✅ Offline mode works end-to-end
- ✅ Camera mode works end-to-end
- ✅ System handles zero detections gracefully
- ✅ System handles high detection rates
- ✅ Late-join scenarios work correctly
- ✅ Documentation is complete and accurate
- ✅ No legacy code paths remain active
- ✅ Code passes linter checks

---

## Estimated Time

- Phase 1: 2-3 hours
- Phase 2: 1-2 hours
- Phase 3: 3-4 hours
- Phase 4: 2-3 hours
- Phase 5: 3-4 hours
- Phase 6: 1-2 hours

**Total: 12-18 hours** of focused development time

---

## Current Branch Status

```bash
git branch
# * feature/ros2-direct-cotton-detection

git status
# On branch feature/ros2-direct-cotton-detection
# Modified files:
#   - src/yanthra_move/include/yanthra_move/yanthra_move_system.hpp
#   - src/yanthra_move/src/yanthra_move_system.cpp
#   - src/yanthra_move/CMakeLists.txt
#   - src/yanthra_move/package.xml
```

**Next Step:** Start with Task 4 - Update MotionController to use the provider callback.

---

*This guide was generated on 2025-09-30. For questions or issues, refer to the design documentation in the repository.*