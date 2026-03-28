# System Migration Guide

**Last Updated:** October 21, 2025  
**Consolidated From:** MASTER_MIGRATION_STRATEGY.md, ODRIVE_TO_MG6010_MIGRATION.md, COTTON_DETECTION_MIGRATION_GUIDE.md

---

## Overview

This guide consolidates three major system migrations in the Pragati ROS2 cotton-picking robot:

1. **OAK-D Lite Camera Integration** - Restoring correct camera hardware and DepthAI functionality
2. **ODrive to MG6010 Motor Controllers** - Transitioning to integrated CAN-based servo motors
3. **Cotton Detection ROS2 Topics** - Migrating from file/service-based to pure topic architecture

Each migration preserves existing ROS2 improvements while modernizing specific subsystems.

---

## Migration 1: OAK-D Lite Camera Integration

**Status:** ✅ Phase 1 & 2 Complete; Phase 3 In Progress  
**Hardware:** Luxonis OAK-D Lite  
**ROS Version:** ROS 2 Jazzy

### Problem Statement

During ROS1 → ROS2 migration, the camera system was incorrectly changed:

| Component | ROS1 (Working) | ROS2 (Current - Wrong) | Impact |
|-----------|----------------|------------------------|--------|
| **Hardware** | Luxonis OAK-D Lite | Intel RealSense D415 | ❌ Camera non-functional |
| **SDK** | DepthAI Python | librealsense2 C++ | ❌ Wrong library |
| **AI Processing** | On-device (Myriad X VPU) | CPU-based | ❌ Lost hardware acceleration |
| **Code** | 38 Python files | C++ stubs | ❌ Working code not migrated |

### What We Preserved

✅ **DO NOT TOUCH - These are excellent:**
- Modern C++17 architecture (83% code reduction: 3,610 → 600 lines)
- Smart pointers and RAII (zero memory leaks)
- 20% performance improvement (2.8s vs 3.5s cycle time)
- Enhanced service interfaces (dual compatibility)
- Structured error handling with taxonomy
- Type-safe parameter system
- Graceful shutdown (10ms vs hangs)
- Production testing framework

### Solution: Hybrid Architecture

**Strategy:** Preserve ALL ROS2 improvements + Restore OAK-D Lite functionality

```
┌────────────────────────────────────────────────────────────┐
│           HYBRID ARCHITECTURE APPROACH                      │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  ROS2 Layer (Keep)              Camera Layer (Restore)     │
│  ═════════════════              ══════════════════         │
│  ✅ YanthraMoveSystem    ←→     ✅ DepthAI Pipeline       │
│  ✅ Service interfaces   ←→     ✅ OAK-D Python code      │
│  ✅ Parameter system     ←→     ✅ YOLO on-device blob    │
│  ✅ Error taxonomy       ←→     ✅ USB2 configuration     │
│  ✅ Performance monitor  ←→     ✅ Spatial detection      │
│  ✅ Testing framework    ←→     ✅ 3D coordinates         │
│                                                             │
│  Interface: ROS2 services bridge to DepthAI Python wrapper │
└────────────────────────────────────────────────────────────┘
```

### Three-Phase Migration

#### ✅ Phase 1: Quick Path (Delivered Oct 2024)

**Goal:** Restore camera functionality with minimal code changes

**Approach:**
- Copy 38 Python files from ROS1 OakDTools
- Create minimal ROS2 Python wrapper (rclpy)
- Bridge to existing ROS2 service interfaces
- Preserve ALL ROS2 improvements

**Outcome:**
- ✅ Camera working with on-device YOLO
- ✅ All ROS2 services unchanged
- ✅ Performance maintained (≤2.8s cycle time)
- ✅ Zero memory leaks preserved

#### ✅ Phase 2: Medium Path (Delivered Oct 2025)

**Goal:** Native ROS2 implementation while preserving DepthAI benefits

**Outcome:**
- `cotton_detection_node` (C++) is production default with hybrid HSV/YOLO pipeline
- DepthAI integration available via `-DHAS_DEPTHAI=ON`
- Diagnostics + simulation implemented
- Documentation aligned with new architecture

**Follow-up:**
- Validate calibration export + restart health checks on hardware
- Capture on-hardware validation logs to confirm performance targets

#### 🚀 Phase 3: Full Path (Active)

**Goal:** Modernize integration while keeping on-device AI

**Approach:**
- Integrate official depthai-ros package
- Use standard ROS2 camera topics
- Keep YOLO on-device processing
- Remove file-based I/O

**Outcome:**
- ✅ Standard ROS2 camera driver
- ✅ Better ecosystem integration
- ✅ Idiomatic ROS2 patterns

### Task Tracker (Updated Oct 2025)

`✅` = complete | `⚠️` = in progress | `⬜` = backlog

#### Foundation & Infrastructure

| Task | Status | Notes |
|------|--------|-------|
| 1. Freeze baseline and audit both repos | ✅ | Historical snapshots captured (Oct 2024) |
| 2. Side-by-side code and feature comparison | ✅ | `OAK_D_LITE_MIGRATION_ANALYSIS.md` maintained |
| 3. Architecture decision & migration strategy | ✅ | This doc; kept as living strategy |
| 4. Remove RealSense artifacts / add DepthAI flags | ✅ | RealSense references removed; `HAS_DEPTHAI` available |
| 5. Add DepthAI dependencies | ✅ | DepthAI SDK + ROS deps installed (see `install_deps.sh`) |

#### Implementation Deliverables

| Task | Status | Notes |
|------|--------|-------|
| 6. Quick path wrapper implementation | ✅ | Legacy Python wrapper shipped; now marked fallback |
| 7. Interface specification | ✅ | `docs/ROS2_INTERFACE_SPECIFICATION.md` (rev 2025-10-13) |
| 8. CMake integration (Python + C++) | ✅ | Mixed build handled; C++ node primary |
| 9. package.xml dependency updates | ✅ | Includes rclcpp, DepthAI conditionals, etc. |
| 10. URDF camera updates | ✅ | OAK-D dimensions applied in robot description |
| 11. Camera calibration assets | ⚠️ | C++ node exports calibration; finalize docs + hardware validation |
| 12. Launch files | ✅ | `cotton_detection_cpp.launch.py` + wrapper launch maintained |
| 13. Model / asset management | ✅ | YOLO blobs packaged under `share/cotton_detection_ros2` |
| 14. Testing & validation plan | ⚠️ | Scripts exist; awaiting hardware run to refresh evidence |
| 15. Documentation alignment | ✅ | README + status matrix updated Oct 2025 |

#### Phase 3 & Beyond

| Task | Status | Notes |
|------|--------|-------|
| 16. DepthAI runtime reconfiguration (C++) | ⚠️ | TODOs tracked in `depthai_manager.cpp` |
| 17. Calibration export inside C++ node | ✅ | Implemented Oct 2025 with DepthAI-first export + script fallback |
| 18. Lifecycle + diagnostics hardening | ⚠️ | Diagnostics present; lifecycle node backlog |
| 19. Performance benchmarking (2.5s target) | ⬜ | Schedule after hardware validation resumes |

### Success Criteria

✅ **Functional:**
- [ ] OAK-D Lite detected and initialized
- [ ] YOLO blob loads and runs on-device
- [ ] Spatial detections published via ROS2 service
- [ ] Coordinate transformation matches ROS1 (±10%)

✅ **Performance:**
- [ ] Cycle time ≤ 2.8s (ROS2 benchmark maintained)
- [ ] Detection latency < 100ms
- [ ] No memory leaks detected
- [ ] Graceful shutdown < 1s

✅ **Architecture:**
- [ ] All ROS2 service interfaces unchanged
- [ ] Performance monitoring still functions
- [ ] Error handling taxonomy preserved
- [ ] Smart pointers and RAII maintained

---

## Migration 2: ODrive to MG6010 Motor Controllers

**Date:** October 10, 2025  
**Status:** ✅ Phase 1 Complete  
**Hardware:** MG6010-i6 CAN Motors

### Why MG6010?

1. **Integrated Design**: Motor + Encoder + Driver in one unit
2. **Simplified Wiring**: CAN bus communication (2 wires vs. multiple ODrive connections)
3. **Cost Effective**: Lower cost per motor unit
4. **Proven Technology**: Successfully used in similar agricultural robots
5. **Better Integration**: Native CAN protocol support

### Migration Phases

#### ✅ Phase 1: Minimal-Change Swap (CURRENT)

**Goal:** Get the system operational with minimal code changes

**Strategy:**
- Reuse existing `mg6010_test_node` executable
- Replace ODrive references in launch files
- Use inline parameters or existing config files
- **NO new node implementations** (honors user preference)

**Status:** 
- ✅ Build configuration updated
- ✅ Launch files fixed
- ✅ CAN interface configured
- ✅ Documentation updated

#### Phase 2: Production Stabilization (OPTIONAL - FUTURE)

**Goal:** Create production-ready service node interface

**Options:**
- **Option A (Preferred):** Create CMake alias for `mg6010_test_node` → `mg6010_service_node`
  - No new code required
  - Simple install-time aliasing
  - Maintains backward compatibility
  
- **Option B (If needed):** Thin wrapper service node
  - Reuses existing library components
  - Only if Option A proves insufficient

**Timeline:** Defer until Phase 1 validated and running

### Technical Details

#### Hardware Configuration

| Component | ODrive (Legacy) | MG6010-i6 (Current) |
|-----------|-----------------|---------------------|
| Interface | USB/UART | CAN Bus |
| Baud Rate | 115200 (serial) | 500 kbps (CAN) |
| Protocol | ODrive ASCII | LK-TECH CAN V2.35 |
| Wiring | Complex | Simple (2-wire CAN) |
| Node ID | N/A | 0x140 + motor_id |

#### Software Changes

**Launch Files Updated:**
1. `src/yanthra_move/launch/pragati_complete.launch.py`
   - Removed: `odrive_service_node`
   - Added: `mg6010_controller` (using mg6010_test_node)
   
2. `src/motor_control_ros2/launch/hardware_interface.launch.py`
   - Updated node references
   - Added CAN configuration parameters

**Configuration Files:**
- Using: `motor_control_ros2/config/mg6010_test.yaml`
- CAN Interface: `can0`
- Bitrate: `500000` (500 kbps)

**Build System:**
- CMake flag: `-DBUILD_TEST_NODES=ON`
- Reason: mg6010_test_node is in test targets by default

### CAN Bus Setup

#### Hardware Requirements:
- CAN interface (e.g., USB-CAN adapter, built-in CAN)
- 120Ω termination resistors at bus ends
- 24V power supply for motors

#### Software Configuration:

```bash
# Configure CAN interface
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up

# Verify status
ip -details link show can0

# Monitor traffic (optional)
candump can0
```

#### Persistence (Optional):
Create `/etc/systemd/network/80-can.network`:
```ini
[Match]
Name=can0

[CAN]
BitRate=500K
```

### Node Mapping

**Old (ODrive):**
```python
Node(
    package="motor_control_ros2",
    executable="odrive_service_node",
    name="odrive_service_node",
    parameters=[odrive_config_file],
)
```

**New (MG6010):**
```python
Node(
    package="motor_control_ros2",
    executable="mg6010_test_node",
    name="mg6010_controller",
    parameters=[{
        'can_interface': 'can0',
        'baud_rate': 500000,
        'motor_id': 1,
        'test_mode': 'status'
    }],
)
```

### Topic Mapping

| Function | ODrive Topics | MG6010 Topics |
|----------|---------------|---------------|
| Command | `/odrive/command` | `/mg6010/command` |
| Status | `/odrive/status` | `/mg6010/status` |
| Position | `/odrive/position` | `/mg6010/position` |
| Velocity | `/odrive/velocity` | `/mg6010/velocity` |

### Rollback Plan

If issues arise with MG6010:

1. **Stop the system:**
   ```bash
   ros2 node kill --all
   ```

2. **Revert launch files:**
   ```bash
   git checkout src/yanthra_move/launch/pragati_complete.launch.py
   git checkout src/motor_control_ros2/launch/hardware_interface.launch.py
   ```

3. **Rebuild without test nodes:**
   ```bash
   colcon build --cmake-args -DBUILD_TEST_NODES=OFF
   ```

4. **Restore ODrive (if hardware available):**
   - Reconnect ODrive controllers
   - Launch with legacy configuration

### Validation Commands

```bash
# Check nodes
ros2 node list | grep mg6010

# Check topics
ros2 topic list | grep mg6010

# Check parameters
ros2 param list /mg6010_controller

# Verify CAN
ip -details link show can0
candump can0  # Should see traffic when motors active
```

### Performance Comparison

| Metric | ODrive | MG6010 |
|--------|--------|--------|
| Latency | ~50ms | ~10ms |
| Reliability | Moderate | High |
| Setup Time | 30 min | 10 min |
| Wiring Complexity | High | Low |
| Cost per Motor | $$ | $ |

---

## Migration 3: Cotton Detection ROS2 Topics

**Status:** 8/18 Tasks Complete ✅

### Migration Overview

Migrate from file/service-based cotton detection to pure ROS2 topic-based architecture.

### Architecture Change

```
OLD: File/Service-Based
┌─────────────┐     ┌──────────┐     ┌─────────────┐
│   Camera    │────>│  Files   │────>│   Service   │
│             │     │  (CSV)   │     │   Client    │
└─────────────┘     └──────────┘     └─────────────┘

NEW: Pure ROS2 Topics
┌─────────────┐     ┌──────────┐     ┌─────────────┐
│   Camera    │────>│  Topic   │────>│ Subscriber  │
│             │     │ (Stream) │     │  (Buffer)   │
└─────────────┘     └──────────┘     └─────────────┘
```

### ✅ COMPLETED TASKS (8/18)

#### Task 1: Create cleanup branch and inventory ✅
- Branch created: `feature/ros2-direct-cotton-detection`
- Inventory completed of all cotton detection references

#### Task 2: Centralize subscription in YanthraMoveSystem ✅  
- Design decision: Subscribe ONLY in YanthraMoveSystem
- MotionController consumes via internal buffer (dependency injection)

#### Task 3: Add ROS2 subscription in YanthraMoveSystem ✅
- File: `src/yanthra_move/src/yanthra_move_system.cpp`
- Subscription created to `/cotton_detection/results`
- Thread-safe buffer with mutex protection
- Provider callback for MotionController access
- Type-erased storage to avoid header pollution

#### Task 4: Update MotionController to consume from buffer provider ✅
- Files: `src/yanthra_move/include/yanthra_move/core/motion_controller.hpp`, `src/yanthra_move/src/core/motion_controller.cpp`
- Provider-based initialize signature landed; extern usage removed
- Operational cycle now pulls optional vectors via injected lambda with graceful fallbacks

#### Task 5: Remove file-based stub get_cotton_coordinates ✅
- Legacy stub deleted from `yanthra_move_system.cpp`
- Topic-backed cache + mutexed buffer now authoritative source

#### Task 6: Remove robust service client ✅
- `robust_cotton_detection_client.cpp` moved out of build (archived under `src/yanthra_move/archive/legacy/`)
- CMakeLists/package manifest already exclude the legacy target

#### Task 7: Disable legacy bridge script ✅
- `cotton_detection_bridge.py` archived; setup entry points and launch files cleaned
- README now calls out wrapper-only legacy usage

#### Task 11: Wire MotionController to provider in YanthraMoveSystem ✅
- `initializeModularComponents()` injects provider callback during controller startup
- Motion controller now fully decoupled from file system artifacts

### 🔄 REMAINING TASKS (10/18)

#### Task 8: Verify cotton_detection_ros2 publishing
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

#### Task 9: Add offline/camera mode parameters
**Status:** Needs implementation  
**Files to modify:**
- `src/cotton_detection_ros2/config/cotton_detection_params.yaml`
- `src/cotton_detection_ros2/src/cotton_detection_node.cpp`

**Changes needed:**

```yaml
cotton_detection_node:
  ros__parameters:
    # Mode selection
    mode: "camera"  # Options: "camera", "offline"
    
    # Camera mode
    camera_topic: "/camera/image_raw"
    
    # Offline mode
    image_directory: "/data/cotton_images"
    offline_processing_rate_hz: 1.0
```

#### Task 10: Keep essential detection service
**Status:** Needs implementation  
**Files to modify:**
- `src/cotton_detection_ros2/src/cotton_detection_node.cpp`

**Changes needed:**
1. Keep `/cotton_detection/detect` service for manual testing
2. Remove `/cotton_detection/detect_cotton_srv` (legacy)
3. Ensure service also publishes to `/cotton_detection/results`

#### Task 12: Clean up legacy service integrations
**Status:** Needs review  
**Files to check:**
- `src/yanthra_move/src/yanthra_move_aruco_detect.cpp`
- `src/yanthra_move/src/yanthra_move_calibrate.cpp`

**Changes needed:**
1. Remove or deprecate legacy cotton detection service calls
2. Add comments indicating deprecated status
3. Consider removing these files to archive if unused

#### Task 14: Update launch files
**Status:** Needs implementation  
**Files to modify:**
- All cotton_detection_ros2 launch files
- All yanthra_move launch files

**Changes needed:**
1. Remove all cotton_detection_bridge references
2. Add mode parameter examples

#### Tasks 15-18: Testing and Documentation
- Task 15: Test offline mode end-to-end
- Task 16: Test camera mode end-to-end
- Task 17: Validate QoS and message loss resilience
- Task 18: Finalize cleanup and documentation

### Implementation Order Recommendation

1. **Phase 1: Core Integration (Tasks 4-6)** ✅ COMPLETE
2. **Phase 2: Legacy Cleanup (Tasks 7, 12)** ✅ PARTIAL
3. **Phase 3: Cotton Detection Enhancement (Tasks 8-10)**
4. **Phase 4: System Integration (Tasks 11, 14)** ✅ PARTIAL
5. **Phase 5: Validation (Tasks 15-17)**
6. **Phase 6: Documentation (Task 18)**

### Success Criteria

- ✅ No compilation errors or warnings
- ✅ All unit tests pass
- ⬜ Offline mode works end-to-end
- ⬜ Camera mode works end-to-end
- ⬜ System handles zero detections gracefully
- ⬜ System handles high detection rates
- ⬜ Late-join scenarios work correctly
- ⬜ Documentation is complete and accurate
- ✅ No legacy code paths remain active
- ⬜ Code passes linter checks

---

## Common Migration Patterns

### Pattern 1: Hardware Abstraction Layer
All three migrations follow HAL pattern:
```
Application Layer
      ↓
  ROS2 Interface (Topics/Services)
      ↓
Hardware Abstraction Layer
      ↓
Physical Hardware (Camera/Motors/Detection)
```

### Pattern 2: Phased Rollout
1. **Quick Path:** Minimal changes, functional system
2. **Medium Path:** Hybrid approach with improved integration
3. **Full Path:** Complete modernization

### Pattern 3: Fallback Strategy
All migrations maintain:
- Git-based rollback capability
- Legacy code archived (not deleted)
- Documentation of old configuration
- Testing at each phase

---

## Cross-Cutting Concerns

### Build System
All migrations require CMake updates:
- Conditional compilation flags (`HAS_DEPTHAI`, `BUILD_TEST_NODES`)
- Dependency management in package.xml
- Launch file updates

### Testing Strategy
Each migration includes:
- Unit tests (component level)
- Integration tests (system level)
- Hardware validation (field testing)
- Performance benchmarking

### Documentation
All migrations update:
- Interface specifications
- Launch file examples
- Configuration guides
- Troubleshooting sections

---

## References

### OAK-D Lite Migration
- `OAK_D_LITE_MIGRATION_ANALYSIS.md` - Problem analysis
- `docs/ROS2_INTERFACE_SPECIFICATION.md` - Interface spec
- [Luxonis OAK-D Lite](https://shop.luxonis.com/products/oak-d-lite-1)
- [DepthAI Python SDK](https://docs.luxonis.com/projects/api/en/latest/)

### MG6010 Migration
- `src/motor_control_ros2/README.md` - Consolidated docs
- `docs/archive/2025-10/motor_control/` - Pre-consolidation docs
- LK-TECH CAN Protocol V2.35 specification
- `src/motor_control_ros2/src/mg6010_test_node.cpp` - Test node source

### Cotton Detection Migration
- `feature/ros2-direct-cotton-detection` branch
- Topic interface: `/cotton_detection/results`
- `src/yanthra_move/src/yanthra_move_system.cpp` - Subscription implementation

---

**Consolidated:** October 21, 2025  
**Archival Note:** Original guides moved to `docs/archive/2025-10-phase2/`  
**Migration Status:** Camera (Phase 2 Complete) | Motors (Phase 1 Complete) | Detection (Phase 1 In Progress)
