# C++ Implementation Task Tracker

**Project:** Cotton Detection C++ Node with DepthAI Integration  
**Start Date:** October 8, 2025  
**Target Completion:** November 26, 2025 (7 weeks)

---

## Progress Overview

| Phase | Tasks | Completed | In Progress | Not Started | % Complete |
|-------|-------|-----------|-------------|-------------|------------|
| Phase 0: Python Stability | 5 | 5 | 0 | 0 | 100% |
| Phase 1: DepthAI Integration | 8 | 5 | 0 | 3 | 63% |
| Phase 2: Camera & Transforms | 6 | 0 | 0 | 6 | 0% |
| Phase 3: Features & Quality | 9 | 0 | 0 | 9 | 0% |
| Phase 4: Testing | 7 | 0 | 0 | 7 | 0% |
| Phase 5: Deployment | 6 | 0 | 0 | 6 | 0% |
| **TOTAL** | **41** | **10** | **0** | **31** | **24%** |

---

## Phase 0: Python Stability (Week 1, Parallel)

**Goal:** Keep Python wrapper stable during C++ development  
**Duration:** 1 week (can run in parallel with Phase 1 setup)  
**Priority:** P0 - Critical

| ID | Task | Status | Assignee | Start | Complete | Notes |
|----|------|--------|----------|-------|----------|-------|
| 0.1 | Fix subprocess STDOUT/STDERR deadlock | ✅ Complete | Uday | Oct 8 | Oct 8 | Redirect to log file |
| 0.2 | Fix signal handler race conditions | ✅ Complete | Uday | Oct 8 | Oct 8 | Use threading.Event |
| 0.3 | Implement atomic file writes | ✅ Complete | Uday | Oct 8 | Oct 8 | tempfile + os.replace |
| 0.4 | Add subprocess auto-restart logic | ✅ Complete | Uday | Oct 8 | Oct 8 | Exponential backoff |
| 0.5 | Expose simulation_mode in launch | ✅ Complete | Uday | Oct 8 | Oct 8 | Add launch parameter |

**Exit Criteria:**
- [ ] Python wrapper runs without deadlocks for 1 hour
- [ ] Signal handling thread-safe (verified with race detector)
- [ ] File writes atomic (tested with kill -9 during write)
- [ ] Subprocess auto-restarts on crash (tested 10 crashes)
- [ ] Simulation mode accessible via launch file

---

## Phase 1: DepthAI Integration (Week 2-4)

**Goal:** Integrate depthai-core C++ API into cotton detection node  
**Duration:** 3 weeks  
**Priority:** P0 - Critical Path

**Phase 1 Prep (Completed):**
- ✅ Installed `ros-jazzy-depthai` package (v2.30.0)
- ✅ Located headers in `/opt/ros/jazzy/include/depthai/`
- ✅ Studied DepthAI C++ API patterns and examples
- ✅ Designed `DepthAIManager` class interface
- ✅ Created comprehensive integration guide

| ID | Task | Status | Assignee | Start | Complete | Files | Notes |
|----|------|--------|----------|-------|----------|-------|-------|
| 1.0 | Install & study DepthAI C++ API | ✅ Complete | Uday | Oct 8 | Oct 8 | `PHASE1_DEPTHAI_CPP_INTEGRATION_GUIDE.md` | Pre-built package |
| 1.1 | Create DepthAIManager header & skeleton | ✅ Complete | Uday | Oct 8 | Oct 8 | `depthai_manager.{hpp,cpp}` | PImpl pattern, 235 lines header, 363 lines impl |
| 1.2 | Implement full DepthAI pipeline | ✅ Complete | Uday | Oct 8 | Oct 8 | `depthai_manager.cpp` | Pipeline, device conn, detection retrieval |
| 1.3 | Integrate into CottonDetectionNode | ✅ Complete | Uday | Oct 8 | Oct 8 | `cotton_detection_node.*` | Added members, init/shutdown methods |
| 1.4 | Update CMakeLists for DepthAI | ✅ Complete | Uday | Oct 8 | Oct 8 | `CMakeLists.txt` | Linked depthai_manager library |
| 1.5 | Add DepthAI config parameters | ✅ Complete | Uday | Oct 8 | Oct 8 | `cotton_detection_node.cpp` | 10 DepthAI ROS2 parameters |
| 1.6 | Test with OAK-D Lite hardware | 🔄 Ready | - | Oct 9 | - | Hardware | Awaiting camera arrival |
| 1.7 | Handle DepthAI exceptions/errors | ✅ Complete | Uday | Oct 8 | Oct 8 | `depthai_manager.cpp` | Try-catch, graceful fallback |
| 1.8 | Add performance benchmarking | ✅ Complete | Uday | Oct 8 | Oct 8 | `cotton_detection_node.cpp` | Integrated with PerformanceMonitor |

**Exit Criteria:**
- [ ] depthai-core library compiles with node
- [ ] DepthAIManager can initialize OAK-D Lite camera
- [ ] Spatial detection returns valid (x,y,z) coordinates
- [ ] No memory leaks (verified with valgrind)
- [ ] Graceful error handling when camera disconnected
- [ ] Detection latency < 100ms

**Key Deliverables:**
- `include/cotton_detection_ros2/depthai_manager.hpp` (~200 lines)
- `src/depthai_manager.cpp` (~500 lines)
- Updated `cotton_detection_node.cpp` integration (~100 lines added)

---

## Phase 2: Camera & Coordinate System (Week 5)

**Goal:** Proper TF transforms and calibration from DepthAI  
**Duration:** 1 week  
**Priority:** P1 - High

| ID | Task | Status | Assignee | Start | Complete | Files | Notes |
|----|------|--------|----------|-------|----------|-------|-------|
| 2.1 | Support both camera modes | ⬜ Not Started | - | - | - | `cotton_detection_node.cpp` | Direct vs subscriber |
| 2.2 | Add TF2 transform publisher | ⬜ Not Started | - | - | - | `cotton_detection_node.*` | Static transforms |
| 2.3 | Load calibration from DepthAI | ⬜ Not Started | - | - | - | `depthai_manager.cpp` | Intrinsics/extrinsics |
| 2.4 | Add calibration export service | ⬜ Not Started | - | - | - | `cotton_detection_node.cpp` | YAML export |
| 2.5 | Verify coordinate transforms | ⬜ Not Started | - | - | - | Test script | Accuracy check |
| 2.6 | Add camera info publisher | ⬜ Not Started | - | - | - | `cotton_detection_node.cpp` | sensor_msgs/CameraInfo |

**Exit Criteria:**
- [ ] Node works with `camera_mode: depthai_direct`
- [ ] Node works with `camera_mode: ros_subscriber`
- [ ] TF tree shows camera → base_link transform
- [ ] Calibration service exports to YAML successfully
- [ ] Detection coordinates match Python wrapper (< 5mm error)

---

## Phase 3: Features & Quality (Week 6)

**Goal:** Feature parity with Python wrapper + quality improvements  
**Duration:** 1 week  
**Priority:** P2 - Medium

| ID | Task | Status | Assignee | Start | Complete | Files | Notes |
|----|------|--------|----------|-------|----------|-------|-------|
| 3.1 | Add confidence scores to output | ⬜ Not Started | - | - | - | `DetectionResult.msg`, node | Real confidence |
| 3.2 | Add diagnostics publisher | ⬜ Not Started | - | - | - | `cotton_detection_node.*` | Health monitoring |
| 3.3 | Add simulation mode | ⬜ Not Started | - | - | - | `cotton_detection_node.cpp` | Synthetic data |
| 3.4 | Create launch file | ⬜ Not Started | - | - | - | `launch/cotton_detection_cpp.launch.py` | New launch |
| 3.5 | Add config YAML file | ⬜ Not Started | - | - | - | `config/cotton_detection_cpp.yaml` | Default params |
| 3.6 | Update documentation | ⬜ Not Started | - | - | - | `docs/` | Usage guide |
| 3.7 | Add usage examples | ⬜ Not Started | - | - | - | `docs/EXAMPLES.md` | Code examples |
| 3.8 | Multi-camera support prep | ⬜ Not Started | - | - | - | `depthai_manager.*` | Device ID param |
| 3.9 | Add parameter validation | ⬜ Not Started | - | - | - | `cotton_detection_node.cpp` | Range checks |

**Exit Criteria:**
- [ ] Confidence scores published in DetectionResult
- [ ] Diagnostics appear in `/diagnostics` topic
- [ ] Simulation mode generates synthetic detections
- [ ] Launch file works with all parameters
- [ ] Documentation complete and reviewed

---

## Phase 4: Testing & Validation (Week 7)

**Goal:** Comprehensive testing and performance validation  
**Duration:** 1 week  
**Priority:** P1 - High

| ID | Task | Status | Assignee | Start | Complete | Files | Notes |
|----|------|--------|----------|-------|----------|-------|-------|
| 4.1 | Unit tests for DepthAIManager | ⬜ Not Started | - | - | - | `test/depthai_manager_test.cpp` | Mock camera |
| 4.2 | Integration tests with hardware | ⬜ Not Started | - | - | - | `test/integration_test.cpp` | Real camera |
| 4.3 | Performance benchmarking | ⬜ Not Started | - | - | - | `test/benchmark.cpp` | Latency/FPS |
| 4.4 | Accuracy comparison vs Python | ⬜ Not Started | - | - | - | Test script | Side-by-side |
| 4.5 | Stress testing (24hr run) | ⬜ Not Started | - | - | - | Hardware | Stability |
| 4.6 | Memory leak testing (valgrind) | ⬜ Not Started | - | - | - | Test script | Memory profiling |
| 4.7 | Thread safety testing | ⬜ Not Started | - | - | - | Test script | ThreadSanitizer |

**Exit Criteria:**
- [ ] Unit test coverage > 80%
- [ ] All integration tests pass
- [ ] Performance: Detection < 100ms, FPS > 15
- [ ] Accuracy: Within 5% of Python wrapper
- [ ] 24-hour run with no crashes or memory leaks

---

## Phase 5: Migration & Deployment (Week 8)

**Goal:** Deploy C++ node as primary, deprecate Python  
**Duration:** 1 week  
**Priority:** P0 - Critical

| ID | Task | Status | Assignee | Start | Complete | Files | Notes |
|----|------|--------|----------|-------|----------|-------|-------|
| 5.1 | Side-by-side testing (C++ vs Python) | ⬜ Not Started | - | - | - | Both nodes | Parallel run |
| 5.2 | Update system launch files | ⬜ Not Started | - | - | - | Main launch | Switch to C++ |
| 5.3 | Create migration guide | ⬜ Not Started | - | - | - | `docs/CPP_MIGRATION_GUIDE.md` | Step-by-step |
| 5.4 | Deprecate Python wrapper | ⬜ Not Started | - | - | - | Python files | Add warnings |
| 5.5 | Update CI/CD for C++ node | ⬜ Not Started | - | - | - | `.github/workflows/` | Build/test |
| 5.6 | Field deployment | ⬜ Not Started | - | - | - | Hardware | Production |

**Exit Criteria:**
- [ ] C++ and Python produce identical results on test set
- [ ] System launch uses C++ by default
- [ ] Migration guide tested by independent reviewer
- [ ] Python wrapper marked deprecated (warnings in logs)
- [ ] CI/CD builds and tests C++ node
- [ ] Production deployment successful for 48 hours

---

## Weekly Schedule

### Week 1 (Oct 8-14)
- **Phase 0:** All 5 Python critical fixes
- **Phase 1 Prep:** Install depthai-core, study examples, design DepthAIManager

### Week 2 (Oct 15-21)
- **Phase 1:** Tasks 1.1, 1.2 (Header + implementation)

### Week 3 (Oct 22-28)
- **Phase 1:** Tasks 1.3, 1.4, 1.5 (Integration + CMake)

### Week 4 (Oct 29 - Nov 4)
- **Phase 1:** Tasks 1.6, 1.7 (Hardware testing + error handling)

### Week 5 (Nov 5-11)
- **Phase 2:** All 5 camera & transform tasks

### Week 6 (Nov 12-18)
- **Phase 3:** All 7 features & quality tasks

### Week 7 (Nov 19-25)
- **Phase 4:** All 5 testing tasks

### Week 8 (Nov 26 - Dec 2)
- **Phase 5:** All 6 deployment tasks

---

## Code Complexity Guidelines

**To keep code manageable and maintainable:**

### File Size Limits
- **Header files:** Max 300 lines
- **Implementation files:** Max 600 lines
- **Single function:** Max 50 lines (target: 20 lines)

### Refactoring Rules
1. **If file > 600 lines:** Split into multiple files
2. **If function > 50 lines:** Extract helper functions
3. **If class has > 10 methods:** Consider splitting responsibilities
4. **If cyclomatic complexity > 10:** Simplify logic

### Module Structure (Keep Simple)
```
depthai_manager/
  ├── depthai_manager.hpp         (~200 lines - main interface)
  ├── depthai_manager.cpp         (~500 lines - implementation)
  └── depthai_config.hpp          (~100 lines - config structs)
```

**If DepthAIManager grows too large, refactor into:**
```
depthai_manager/
  ├── manager.hpp                 (Main interface)
  ├── manager.cpp                 (Orchestration)
  ├── pipeline_builder.cpp        (Pipeline setup)
  ├── frame_processor.cpp         (Frame handling)
  └── calibration_handler.cpp     (Calibration)
```

---

## Risk Tracking

| Risk | Probability | Impact | Mitigation | Status |
|------|-------------|--------|------------|--------|
| DepthAI C++ API learning curve | Medium | High | Study examples first, prototype | ⬜ Monitoring |
| Performance not meeting target | Low | High | Profile early, optimize | ⬜ Monitoring |
| Hardware compatibility issues | Low | Medium | Test continuously on RPi4 | ⬜ Monitoring |
| Code complexity grows too large | Medium | Medium | Enforce file size limits | ⬜ Monitoring |
| Breaking ROS2 interface | Low | High | Keep compatible, add new features | ⬜ Monitoring |

---

## Decision Log

| Date | Decision | Rationale | Impact |
|------|----------|-----------|--------|
| 2025-10-08 | Focus on C++ over Python improvements | Python will be deprecated, C++ 90% complete | 6-7 week time savings |
| 2025-10-08 | Keep file sizes small (< 600 lines) | Maintainability and readability | Better code quality |
| 2025-10-08 | Support both camera modes (direct + subscriber) | Flexibility for testing and deployment | Additional complexity |

---

## Notes & Lessons Learned

### Week 1
- [ ] Document any depthai-core API surprises
- [ ] Note performance bottlenecks discovered

### Week 2-4
- [ ] Track any deviations from Python behavior
- [ ] Document refactoring decisions

### Week 5-8
- [ ] Record deployment issues
- [ ] Document migration pain points

---

## Quick Status Update Template

**Week X Update (Date):**
- **Completed:** Task IDs
- **In Progress:** Task IDs
- **Blocked:** None / Task IDs (reason)
- **Next Week:** Task IDs
- **Risks:** Any new risks identified
- **Notes:** Key learnings or decisions

---

## Legend

- ⬜ Not Started
- 🏗️ In Progress
- ✅ Complete
- ⚠️ Blocked
- ❌ Cancelled

**Last Updated:** October 8, 2025  
**Next Review:** October 15, 2025
