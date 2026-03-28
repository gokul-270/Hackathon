# Master Migration Strategy: OAK-D Lite Integration

**Authored:** 2025-01-06  
**Last Reviewed:** 2025-10-13  
**Project:** Pragati ROS2 Cotton Picking Robot  
**Camera:** Luxonis OAK-D Lite  
**ROS Version:** ROS 2 Jazzy  
**Status (Oct 2025):** ✅ **Phase 1 & 2 complete; Phase 3 execution in progress**

---

## Document Purpose

This is the **SINGLE SOURCE OF TRUTH** for the OAK-D Lite camera migration strategy. It consolidates:
1. Problem analysis
2. Approach selection with rationale
3. Task breakdown (19 TODO items)
4. Execution plan with timeline
5. Decision tracking

---

## Executive Summary

### Reality Check (Oct 2025)

- ✅ Python wrapper (Phase 1) shipped Oct 2024 and remains available as legacy fallback.
- ✅ Native C++ node with optional DepthAI pipeline (Phase 2) is now the production default (`cotton_detection_node`).
- ⚠️ DepthAI runtime reconfigure and hardware validation still outstanding before full wrapper retirement (calibration export now ships in the C++ node).
- ⚠️ Field validation with OAK-D Lite pending new hardware access; documentation updated to reflect gap.

### Original Problem Statement (Jan 2025)

During ROS1 → ROS2 migration, the camera system was **incorrectly changed**:

| Component | ROS1 (Working) | ROS2 (Current - Wrong) | Impact |
|-----------|----------------|------------------------|--------|
| **Hardware** | Luxonis OAK-D Lite | Intel RealSense D415 | ❌ Camera non-functional |
| **SDK** | DepthAI Python | librealsense2 C++ | ❌ Wrong library |
| **AI Processing** | On-device (Myriad X VPU) | CPU-based | ❌ Lost hardware acceleration |
| **Code** | 38 Python files | C++ stubs | ❌ Working code not migrated |

### What We Kept (ROS2 Improvements)

✅ **DO NOT TOUCH - These are excellent:**
- Modern C++17 architecture (83% code reduction: 3,610 → 600 lines)
- Smart pointers and RAII (zero memory leaks)
- 20% performance improvement (2.8s vs 3.5s cycle time)
- Enhanced service interfaces (dual compatibility)
- Structured error handling with taxonomy
- Type-safe parameter system
- Graceful shutdown (10ms vs hangs)
- Production testing framework
- Professional documentation

### Solution Path (Reconciled)

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

---

## Strategy Selection Rationale

### Why Hybrid Approach (Not Pure Migration)

#### ✅ **Chosen: Hybrid Approach - Quick Path → Medium Path → Full Path**

**Rationale:**
1. **Preserves ROS2 work** - 83% code reduction, 20% performance gains maintained
2. **Reuses working code** - 38 Python files from ROS1 unchanged (reuse-first rule)
3. **Fastest to production** - 1-2 weeks vs 3-6 months for pure C++
4. **Lowest risk** - Proven ROS1 camera code + proven ROS2 architecture
5. **Future-ready** - Clear upgrade path to pure C++ later

#### ❌ **Rejected: Complete Rewrite**

**Why not:**
- 3-6 months timeline
- High risk of introducing new bugs
- Loses proven ROS1 camera code
- ROS2 improvements could be broken during rewrite
- No immediate value to user

#### ❌ **Rejected: Keep ROS2 As-Is (Wrong Camera)**

**Why not:**
- Camera literally doesn't work
- Wrong hardware (D415 vs OAK-D Lite)
- Lost on-device AI processing
- Cannot deliver cotton picking functionality

---

## Three-Phase Migration Path

### ✅ Phase 1: Quick Path (Delivered Oct 2024)

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

**Timeline:** 1-2 weeks

### ✅ Phase 2: Medium Path (Delivered Oct 2025)

**Goal:** Native ROS2 implementation while preserving DepthAI benefits

**Outcome (Oct 2025):**
- `cotton_detection_node` (C++) is production default with hybrid HSV/YOLO pipeline.
- DepthAI integration available via `-DHAS_DEPTHAI=ON`; diagnostics + simulation implemented.
- Documentation (README, Interface Spec, Migration Guide) aligned with new architecture.

**Follow-up:**
- Validate calibration export + restart health checks on hardware and update automation hooks.
- Capture on-hardware validation logs to confirm performance targets.

**Timeline:** Completed alongside documentation refresh (2025-10-13 update).

### 🚀 Phase 3: Full Path (Active)

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

**Timeline:** 1-2 months after Phase 1

### 🚀 Phase 3: Full Path (Month 4-6) - **LONG-TERM**

**Goal:** Pure C++ production-grade implementation

**Approach:**
- Port DepthAI pipeline to C++ using depthai-core
- Maintain same ROS2 interfaces
- Full optimization and profiling

**Outcome:**
- ✅ Single language (C++)
- ✅ Maximum performance
- ✅ Easier maintenance long-term

**Timeline:** 3-6 months after Phase 2

---

## Task Breakdown: 19 TODO Items Mapped to Phases

### Task Tracker (Updated Oct 2025)

`✅` = complete `⚠️` = in progress `⬜` = backlog / not started

#### Foundation & Infrastructure

| Task | Status | Notes |
|------|--------|-------|
| 1. Freeze baseline and audit both repos | ✅ | Historical snapshots captured (Oct 2024). |
| 2. Side-by-side code and feature comparison | ✅ | `OAK_D_LITE_MIGRATION_ANALYSIS.md` maintained. |
| 3. Architecture decision & migration strategy | ✅ | This doc; kept as living strategy. |
| 4. Remove RealSense artifacts / add DepthAI flags | ✅ | RealSense references removed; `HAS_DEPTHAI` available. |
| 5. Add DepthAI dependencies | ✅ | DepthAI SDK + ROS deps installed (see `install_deps.sh`). |

#### Implementation Deliverables

| Task | Status | Notes |
|------|--------|-------|
| 6. Quick path wrapper implementation | ✅ | Legacy Python wrapper shipped; now marked fallback. |
| 7. Interface specification | ✅ | `docs/ROS2_INTERFACE_SPECIFICATION.md` (rev 2025-10-13). |
| 8. CMake integration (Python + C++) | ✅ | Mixed build handled; C++ node primary. |
| 9. package.xml dependency updates | ✅ | Includes rclcpp, DepthAI conditionals, etc. |
| 10. URDF camera updates | ✅ | OAK-D dimensions applied in robot description. |
| 11. Camera calibration assets | ⚠️ | C++ node now exports calibration; finalize docs + hardware validation before marking complete. |
| 12. Launch files | ✅ | `cotton_detection_cpp.launch.py` + wrapper launch maintained. |
| 13. Model / asset management | ✅ | YOLO blobs packaged under `share/cotton_detection_ros2`. |
| 14. Testing & validation plan | ⚠️ | Scripts exist; awaiting new hardware run to refresh evidence. |
| 15. Documentation alignment | ✅ | README + status matrix updated Oct 2025. |

#### Phase 3 & Beyond

| Task | Status | Notes |
|------|--------|-------|
| 16. DepthAI runtime reconfiguration (C++) | ⚠️ | TODOs tracked in `depthai_manager.cpp`. |
| 17. Calibration export inside C++ node | ✅ | Implemented Oct 2025 with DepthAI-first export + script fallback. |
| 18. Lifecycle + diagnostics hardening | ⚠️ | Diagnostics present; lifecycle node backlog. |
| 19. Performance benchmarking (2.5s target) | ⬜ | Schedule after hardware validation resumes. |

#### Foundation Tasks (Days 1-3)

**Task 1: Freeze baseline and audit both repos**
- **Status:** TODO #1
- **Purpose:** Document current state before changes
- **Action:** 
  ```bash
  # Backup current state
  cd /home/uday/Downloads
  tar -czf pragati_ros1_baseline_$(date +%Y%m%d).tar.gz pragati/
  tar -czf pragati_ros2_baseline_$(date +%Y%m%d).tar.gz pragati_ros2/
  
  # Document versions
  echo "ROS 2 Jazzy" > pragati_ros2/BASELINE_VERSION.txt
  python3 --version >> pragati_ros2/BASELINE_VERSION.txt
  ros2 --version >> pragati_ros2/BASELINE_VERSION.txt
  ```
- **Deliverable:** `BASELINE_SNAPSHOT.md` with inventory

**Task 2: Side-by-side code and feature comparison**
- **Status:** TODO #2
- **Purpose:** Clear mapping ROS1 → ROS2
- **Deliverable:** Already created as `OAK_D_LITE_MIGRATION_ANALYSIS.md`
- **Action:** ✅ COMPLETE (sections cover this)

**Task 3: Architecture decision and migration strategy**
- **Status:** TODO #3
- **Purpose:** Choose path with rationale
- **Deliverable:** This document (MASTER_MIGRATION_STRATEGY.md)
- **Action:** ✅ COMPLETE

**Task 4: Remove RealSense artifacts and set up DepthAI build flags**
- **Status:** TODO #4
- **Purpose:** Clean build system
- **Files to modify:**
  - `src/cotton_detection_ros2/CMakeLists.txt`
  - `src/cotton_detection_ros2/src/cotton_detection_node.cpp`
  - `src/cotton_detection_ros2/include/cotton_detection_ros2/*.hpp`
- **Action:**
  ```cmake
  # Remove these lines:
  # option(HAS_REALSENSE "Enable RealSense camera support" OFF)
  # find_package(realsense2 QUIET)
  
  # Add these lines:
  option(HAS_DEPTHAI "Enable DepthAI camera support" ON)
  find_package(depthai QUIET)
  if(HAS_DEPTHAI)
    target_compile_definitions(cotton_detection_node PUBLIC HAS_DEPTHAI=1)
  endif()
  ```
- **Deliverable:** Build with DepthAI flag, no RealSense references

**Task 5: Add DepthAI ROS to the ROS2 Jazzy workspace**
- **Status:** TODO #5
- **Purpose:** Install dependencies
- **Action:**
  ```bash
  # System packages
  sudo apt install -y \
    ros-jazzy-vision-msgs \
    ros-jazzy-sensor-msgs \
    ros-jazzy-image-transport \
    ros-jazzy-cv-bridge \
    ros-jazzy-diagnostic-updater \
    python3-opencv
  
  # Python DepthAI SDK
  pip3 install depthai --user
  
  # Optional: depthai-ros for Phase 2
  # cd /home/uday/Downloads/pragati_ros2/src
  # git clone https://github.com/luxonis/depthai-ros.git -b ros2
  ```
- **Deliverable:** All dependencies installed

#### Implementation Tasks (Days 4-7)

**Task 6: Quick path implementation**
- **Status:** TODO #6
- **Purpose:** Minimal wrapper around ROS1 code
- **Files to create:**
  ```
  src/cotton_detection_ros2/
  ├── scripts/
  │   ├── OakDTools/           # COPY from ROS1
  │   │   ├── CottonDetect.py
  │   │   └── [37 other files]
  │   └── cotton_detect_ros2_node.py  # NEW wrapper
  └── models/
      └── yolov8v2.blob        # COPY from ROS1
  ```
- **Key code (wrapper skeleton):**
  ```python
  #!/usr/bin/env python3
  import rclpy
  from rclpy.node import Node
  from vision_msgs.msg import Detection3DArray, Detection3D
  from cotton_detection_ros2.srv import CottonDetection
  
  # Import existing ROS1 code
  from OakDTools import CottonDetect
  
  class CottonDetectROS2Node(Node):
      def __init__(self):
          super().__init__('cotton_detect_depthai')
          
          # Keep ROS2 service interface
          self.service_ = self.create_service(
              CottonDetection, 
              'cotton_detection/detect',
              self.handle_detection
          )
          
          # Publisher for detections
          self.pub_ = self.create_publisher(
              Detection3DArray,
              'cotton_detection/results',
              10
          )
          
          # Initialize DepthAI pipeline
          self.depthai_pipeline_ = CottonDetect.initialize_pipeline()
      
      def handle_detection(self, request, response):
          # Call ROS1 detection code
          detections = CottonDetect.detect_cotton(self.depthai_pipeline_)
          
          # Convert to ROS2 messages
          response.data = self.convert_to_legacy_format(detections)
          response.success = len(detections) > 0
          response.message = f"Detected {len(detections)} cotton"
          
          # Also publish to topic
          self.publish_detections(detections)
          
          return response
  ```
- **Deliverable:** Working detection via ROS2 service

**Task 7: Topic, service, and message interface specification**
- **Status:** TODO #7
- **Purpose:** Define ROS API contracts
- **Deliverable:** Interface spec (already in TODO details)
- **Action:** Keep existing ROS2 services, add DepthAI backend

**Task 8: CMakeLists.txt modifications**
- **Status:** TODO #8
- **Purpose:** Build system for Python + C++
- **Action:**
  ```cmake
  find_package(ament_cmake_python REQUIRED)
  
  # Install Python module
  ament_python_install_package(${PROJECT_NAME}_py)
  
  # Install Python scripts
  install(PROGRAMS
    scripts/cotton_detect_ros2_node.py
    DESTINATION lib/${PROJECT_NAME}
  )
  
  # Install Python dependencies (OakDTools)
  install(DIRECTORY scripts/OakDTools
    DESTINATION share/${PROJECT_NAME}/scripts
  )
  
  # Install models
  install(DIRECTORY models/
    DESTINATION share/${PROJECT_NAME}/models
  )
  ```
- **Deliverable:** Builds with Python support

**Task 9: Package.xml dependency updates**
- **Status:** TODO #9
- **Purpose:** Declare all dependencies
- **Action:** Add rclpy, vision_msgs, sensor_msgs
- **Deliverable:** All deps declared

**Task 10: URDF camera.xacro updates**
- **Status:** TODO #10
- **Purpose:** Correct camera specifications
- **File:** `src/robo_description/urdf/calibrated_urdf/camera.xacro`
- **Changes:**
  ```xml
  <!-- OLD: Intel RealSense 415 -->
  <!-- NEW: Luxonis OAK-D Lite -->
  <xacro:property name="camera_width" value="0.097"/>   <!-- 97mm -->
  <xacro:property name="camera_height" value="0.020"/>  <!-- 20mm -->
  <xacro:property name="camera_depth" value="0.020"/>   <!-- 20mm -->
  <xacro:property name="camera_mass" value="0.060"/>    <!-- 60g -->
  <xacro:property name="baseline" value="0.075"/>       <!-- 7.5cm -->
  ```
- **Deliverable:** Accurate URDF

**Task 11: Camera calibration and camera info**
- **Status:** ⚠️ In Progress (#11)
- **Purpose:** Use OAK-D factory calibration
- **Action:** C++ node now exports calibration YAML; verify outputs on hardware and update camera_info assets accordingly.
- **Deliverable:** camera_info YAML files + documented calibration workflow

**Task 12: Launch files**
- **Status:** TODO #12
- **Purpose:** Single-command startup
- **File:** `src/cotton_detection_ros2/launch/cotton_detection_depthai.launch.py`
- **Content:**
  ```python
  from launch import LaunchDescription
  from launch_ros.actions import Node
  
  def generate_launch_description():
      return LaunchDescription([
          Node(
              package='cotton_detection_ros2',
              executable='cotton_detect_ros2_node.py',
              name='cotton_detection',
              parameters=[{
                  'blob_path': '/path/to/yolov8v2.blob',
                  'usb_mode': 'usb2',
                  'confidence_threshold': 0.5,
                  'iou_threshold': 0.5,
              }],
              output='screen'
          )
      ])
  ```
- **Deliverable:** Working launch file

**Task 13: Model and asset management**
- **Status:** TODO #13
- **Purpose:** Organize YOLO blob
- **Action:** Copy `yolov8v2.blob` to `models/`
- **Deliverable:** Deterministic paths

**Task 14: Testing and validation plan**
- **Status:** TODO #14
- **Purpose:** Verify functionality
- **Tests:**
  - Device detection
  - USB2 mode stability
  - Blob loading
  - Spatial detection accuracy
  - Service call latency
  - Coordinate transformation
- **Deliverable:** Test report with pass/fail

**Task 15: Documentation correction checklist**
- **Status:** TODO #15
- **Purpose:** Fix incorrect docs
- **Files to update:**
  - `docs/analysis/ros1_vs_ros2_comparison/detection_comparison.md`
  - `docs/analysis/ros1_vs_ros2_comparison/hardware_interface_comparison.md`
  - `docs/guides/CAMERA_INTEGRATION_GUIDE.md`
- **Action:** Add disclaimer:
  ```markdown
  > **⚠️ DOCUMENTATION CORRECTION**: Previous versions incorrectly 
  > referenced Intel RealSense D415. The actual camera is **Luxonis 
  > OAK-D Lite** with DepthAI SDK. See MASTER_MIGRATION_STRATEGY.md.
  ```
- **Deliverable:** Corrected documentation

### 🔄 Phase 2 Tasks (Items 16) - **FUTURE**

**Task 16: Medium path - Hybrid with depthai-ros**
- **Status:** TODO #16
- **Purpose:** Standardize camera driver
- **When:** After Phase 1 complete and stable
- **Action:** Integrate official depthai-ros package
- **Deliverable:** Standard ROS2 camera topics

### 🚀 Phase 3 Tasks (Item 17) - **LONG-TERM**

**Task 17: Full path - Pure C++**
- **Status:** TODO #17
- **Purpose:** Production-grade single-language
- **When:** After Phase 2 complete
- **Action:** Port to C++ with depthai-core
- **Deliverable:** Optimized C++ node

### 📊 Cross-Phase Tasks (Items 18-19)

**Task 18: Risk management and rollout**
- **Status:** TODO #18
- **Purpose:** Mitigate failures
- **Action:** Stage on bench robot, fallback plan
- **Applies to:** All phases

**Task 19: Acceptance criteria**
- **Status:** TODO #19
- **Purpose:** Sign-off criteria
- **Criteria:**
  - Functional parity with ROS1
  - Performance ≤10% delta
  - Stability (multi-hour test)
  - Documentation complete
- **Applies to:** All phases

---

## Execution Timeline

### Week 1: Foundation (Days 1-3)

**Day 1: Baseline and Cleanup**
- [ ] Task 1: Freeze baseline (backup repos)
- [ ] Task 2: Document comparison (use existing analysis)
- [ ] Task 3: Strategy decision (this document)
- [ ] Task 4: Remove RealSense, add DepthAI flag
- [ ] **Deliverable:** Clean build system

**Day 2: Dependencies and Setup**
- [ ] Task 5: Install DepthAI SDK and ROS packages
- [ ] Task 9: Update package.xml
- [ ] Task 8: Modify CMakeLists.txt
- [ ] Task 13: Copy model blob
- [ ] **Deliverable:** Build infrastructure ready

**Day 3: Code Integration**
- [ ] Task 6: Copy OakDTools, create wrapper
- [ ] Task 7: Implement service interface
- [ ] Task 10: Update URDF
- [ ] Task 12: Create launch file
- [ ] **Deliverable:** Buildable node

### Week 2: Testing and Validation (Days 4-7)

**Day 4: Hardware Testing**
- [ ] Task 14: Device detection test
- [ ] Task 14: USB2 mode test
- [ ] Task 14: Blob loading test
- [ ] **Deliverable:** Hardware confirmed working

**Day 5: Integration Testing**
- [ ] Task 14: Service call test
- [ ] Task 14: Spatial detection test
- [ ] Task 14: yanthra_move integration test
- [ ] **Deliverable:** End-to-end working

**Day 6: Performance Testing**
- [ ] Task 14: Cycle time measurement
- [ ] Task 14: Memory leak check
- [ ] Task 14: Long-running stability test
- [ ] **Deliverable:** Performance validated

**Day 7: Documentation and Completion**
- [ ] Task 11: Validate C++ calibration export on hardware + update camera_info assets
- [ ] Task 15: Fix documentation
- [ ] Task 19: Acceptance criteria check
- [ ] **Deliverable:** Phase 1 complete

---

## Success Criteria

### Phase 1 Complete When:

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

✅ **Documentation:**
- [ ] RealSense references corrected
- [ ] OAK-D Lite specs documented
- [ ] Integration guide updated
- [ ] Test report generated

---

## Risk Management

### High-Priority Risks

| Risk | Impact | Probability | Mitigation | Owner |
|------|--------|-------------|------------|-------|
| **Breaking ROS2 improvements** | High | Medium | Keep interfaces isolated, thorough testing | Dev |
| **USB2 bandwidth issues** | Medium | Medium | Match ROS1 config exactly, test early | Dev |
| **Performance regression** | High | Low | Benchmark each step, rollback plan | Dev |
| **DepthAI SDK incompatibility** | Medium | Low | Pin version, test on bench first | Dev |

### Rollback Plan

If Phase 1 fails after Day 3:
1. Revert CMakeLists.txt changes
2. Keep ROS2 service stubs
3. Continue with offline mode
4. Schedule detailed investigation

---

## Decision Log

### Decision 1: Hybrid Approach Selected
- **Date:** 2025-01-06
- **Decision:** Use Phase 1 (Quick Path) → Phase 2 (Medium) → Phase 3 (Full C++)
- **Rationale:** 
  - Preserves ROS2 work
  - Reuses ROS1 camera code
  - Fastest to production
  - Lowest risk
  - Future-ready
- **Alternatives Rejected:**
  - Complete rewrite: Too slow (3-6 months)
  - Keep as-is: Camera doesn't work

### Decision 2: Keep ROS2 Service Architecture
- **Date:** 2025-01-06
- **Decision:** Do not modify YanthraMoveSystem or existing services
- **Rationale:**
  - Working well (20% performance improvement)
  - Camera integration is separate concern
  - Reduces risk of breaking working code
- **Impact:** Python wrapper bridges to existing interfaces

### Decision 3: Reuse ROS1 Python Code
- **Date:** 2025-01-06
- **Decision:** Copy all 38 Python files unchanged
- **Rationale:**
  - Aligns with reuse-first rule
  - Proven to work
  - Faster than porting to C++
- **Impact:** Mixed Python/C++ temporarily

---

## Next Actions

### Immediate (Today)
1. Read and approve this strategy document
2. Confirm approach with stakeholders
3. Begin Task 1: Baseline backup

### This Week
- Execute Days 1-3 foundation tasks
- Complete code integration
- Start hardware testing

### Next Week
- Complete testing and validation
- Fix documentation
- Sign-off Phase 1

---

## References

### Related Documents
1. `OAK_D_LITE_MIGRATION_ANALYSIS.md` - Problem analysis and technical details
2. `OAK_D_LITE_HYBRID_MIGRATION_PLAN.md` - Hybrid approach details
3. `ros2_improvements_validated.md` - ROS2 achievements to preserve
4. `implementation_achievements.md` - Current system status

### External Resources
1. [Luxonis OAK-D Lite Product Page](https://shop.luxonis.com/products/oak-d-lite-1)
2. [DepthAI Python SDK Docs](https://docs.luxonis.com/projects/api/en/latest/)
3. [depthai-ros GitHub](https://github.com/luxonis/depthai-ros)

---

## Approval and Sign-off

**Strategy Approved By:** _______________ Date: ___________

**Phase 1 Ready to Execute:** Yes ☐ No ☐

**Comments:**
_________________________________________________________________
_________________________________________________________________

---

**Document Version:** 1.0  
**Last Updated:** 2025-01-06  
**Status:** Ready for Execution  
**Next Review:** After Phase 1 completion

