# TODO Master List - Pragati ROS2 Project

**Last Updated:** 2025-10-15  
**Total Items:** ~2,540 (2,469 documented + 70 code)  
**Status:** Consolidated from 4 doc sources + code audit  
**Purpose:** Single source of truth for ALL planned work

---

## Executive Summary

### By Status
| Status | Count | Percentage | Action Required |
|--------|-------|------------|-----------------|
| ✅ **Already Done** | ~800 | 32% | Remove/Archive |
| ❌ **Obsolete** | ~600 | 24% | Archive |
| 🔧 **Active Backlog** | ~700 | 28% | Prioritize & Execute |
| 📋 **Future/Parked** | ~370 | 15% | Track for later |
| 🆕 **Code TODOs** | 70 | 3% | Extract & Prioritize |

### By Priority (Active Backlog Only)
| Priority | Count | Estimated Time | Dependencies |
|----------|-------|----------------|--------------|
| 🔴 **Critical** | ~150 | 18-22h | Hardware (motors, camera) |
| 🟠 **High** | ~200 | 20-30h | Mix of hardware/software |
| 🟡 **Medium** | ~250 | 40-60h | Software only |
| 🟢 **Low** | ~100 | 20-30h | Nice-to-haves |

### Quick Wins (≤2h each, no hardware deps)
1. Remove "already done" TODOs from docs (~800 items)
2. Fix date inconsistencies in READMEs
3. Create navigation INDEX.md
4. Archive obsolete TODOs
5. Document motor tuning parameters
6. Add FAQ sections to key docs
7. Create example code snippets
8. Update parameter documentation
9. Add troubleshooting guides
10. Document error recovery procedures

---

## What To Do Next - Action Plan

### Phase 1: Cleanup (1-2 days, immediate)
**Goal:** Remove noise, reveal actual work

1. **Archive "Already Done" items** (~800 items)
   - Source: `docs/TODO_CONSOLIDATED.md` Section 1
   - Action: Move to `docs/archive/2025-10/todos_completed.md`
   - Time: 4-6h

2. **Archive "Obsolete" items** (~600 items)
   - Source: `docs/TODO_CONSOLIDATED.md` Section 2 (ODrive, deprecated features)
   - Action: Move to `docs/archive/2025-10/todos_obsolete.md`
   - Time: 3-4h

3. **Fix documentation inconsistencies**
   - Fix future dates (Oct 6, 2025 → actual commit dates)
   - Fix 2024→2025 mismatches
   - Remove unvalidated "PRODUCTION READY" claims
   - Time: 2-3h

**Result:** ~1,100 actionable items remain (700 backlog + 370 future + 70 code)

### Phase 2: Hardware Validation (Critical Path)
**Goal:** Unblock all hardware-dependent work  
**Dependency:** MG6010 motors, OAK-D Lite camera, GPIO setup

#### Motor Control Hardware (Priority: CRITICAL)
**Time:** 18-22h with hardware

1. **MG6010 Hardware Integration** (8-10h)
   - CAN interface setup and validation (250kbps)
   - Motor communication testing
   - Position/velocity/torque control validation
   - Multi-motor coordination
   - Safety limit verification
   - Source: `docs/TODO_CONSOLIDATED.md` "Hardware Validation"

2. **Safety Monitor Hardware Testing** (4-6h)
   - GPIO ESTOP implementation
   - Emergency LED signaling
   - Real temperature/voltage monitoring
   - CAN ESTOP command verification
   - Source: 9 code TODOs in `src/motor_control_ros2/`

3. **Motor Tuning & Calibration** (6-8h)
   - PID parameter optimization
   - Control loop frequency tuning
   - Response time measurement
   - Create `MOTOR_TUNING_GUIDE.md`
   - Source: `docs/project-management/GAP_ANALYSIS_OCT2025.md`

#### Cotton Detection Hardware (Priority: CRITICAL)
**Time:** 12-18h with hardware

1. **DepthAI Camera Integration** (6-8h)
   - Device connection status monitoring
   - Runtime FPS updates
   - Temperature monitoring from device API
   - Camera calibration from EEPROM
   - Spatial coordinate extraction validation
   - Source: 4 code TODOs in `src/cotton_detection_ros2/depthai_manager.cpp`

2. **Field Testing with Cotton** (4-6h)
   - Test with real cotton plants
   - Measure detection accuracy
   - Test various lighting conditions
   - Test multiple distances/angles
   - Calibrate HSV thresholds
   - Source: `docs/project-management/REMAINING_TASKS.md` Phase 1.6

3. **Performance Benchmarking** (2-4h)
   - Measure detection latency
   - Frame rate testing
   - CPU/memory profiling
   - Compare C++ vs Python wrapper
   - Source: `docs/project-management/REMAINING_TASKS.md` Phase 3.8

#### Yanthra Move Hardware (Priority: HIGH)
**Time:** 8-12h with hardware

1. **GPIO Implementation** (4-6h)
   - Vacuum pump control
   - Camera LED control
   - Status LED control
   - Keyboard monitoring (manual control)
   - Source: 6 code TODOs in `src/yanthra_move/src/yanthra_move_system.cpp`

2. **Calibration & Tuning** (2-4h)
   - Joint homing position verification
   - Position offset adjustments
   - Replace hard-coded 0.001 values
   - Verify motor state checks
   - Source: 23 code TODOs in `src/yanthra_move/src/` (aruco_detect, calibrate)

3. **Integration Testing** (2-3h)
   - End-to-end cotton picking workflow
   - Coordinate transformation validation
   - Detection → movement integration
   - Source: `docs/project-management/REMAINING_TASKS.md` Phase 3.6

**Phase 2 Total:** 38-52h (can be parallelized with hardware setup)

### Phase 3: Software Improvements (No hardware deps)
**Goal:** Quality, documentation, testing  
**Time:** 1-2 weeks

#### Documentation (Priority: HIGH)
**Time:** 8-12h

1. **Consolidate per-module docs** (covered in main consolidation plan)
   - Motor Control: 15 docs → 1 README
   - Cotton Detection: 3 docs → 1 README + OFFLINE_TESTING
   - Yanthra Move: Archive 2 meta docs

2. **Create missing guides** (4-6h)
   - MOTOR_TUNING_GUIDE.md
   - FAQ sections (troubleshooting, common issues)
   - Example code snippets
   - Source: `docs/TODO_CONSOLIDATED.md` Category 3

3. **API Documentation** (2-3h)
   - Verify documented APIs match code
   - Add usage examples
   - Document all ROS2 topics/services/params
   - Source: `docs/project-management/REMAINING_TASKS.md`

4. **Architecture Diagrams** (2-3h)
   - System architecture visualization
   - Data flow diagrams
   - Component interaction diagrams
   - Source: `docs/TODO_CONSOLIDATED.md` Category 3

#### Testing & Validation (Priority: MEDIUM)
**Time:** 8-12h

1. **Unit Tests** (4-6h)
   - CottonDetector tests
   - ImageProcessor tests
   - YOLODetector tests
   - Parameter validation tests
   - Coverage target: 70%+
   - Source: `docs/project-management/REMAINING_TASKS.md` Phase 3.5

2. **Integration Tests** (2-3h)
   - Motor + camera coordination
   - Detection → movement workflow
   - Multi-component interaction
   - Source: `docs/TODO_CONSOLIDATED.md` Category 3

3. **Regression Testing** (2-3h)
   - Automated test suite enhancement
   - CI/CD integration scripts
   - Pre-commit hooks
   - Build verification tests
   - Source: `docs/project-management/REMAINING_TASKS.md` Phase 6.4

#### Performance Optimization (Priority: MEDIUM)
**Time:** 6-10h

1. **Control Loop Optimization** (2-3h)
   - Optimize control frequency
   - Reduce latency in detection pipeline
   - Profile CPU usage
   - Benchmark communication overhead
   - Source: `docs/TODO_CONSOLIDATED.md` Category 3

2. **Memory Optimization** (2-3h)
   - Reduce allocations
   - Image buffer pooling
   - Smart pointer optimization
   - Memory leak detection
   - Source: `docs/project-management/REMAINING_TASKS.md` Phase 4.6

3. **Threading Optimization** (2-4h)
   - Parallel HSV and YOLO detection
   - Thread pool for image processing
   - Lock-free data structures
   - Source: `docs/project-management/REMAINING_TASKS.md` Phase 4.5

#### Error Handling & Recovery (Priority: MEDIUM)
**Time:** 4-6h

1. **Robustness Improvements** (2-3h)
   - Automatic reconnection
   - Improved error messages
   - Recovery strategies
   - Error statistics logging
   - Source: `docs/TODO_CONSOLIDATED.md` Category 3

2. **Fault Scenario Testing** (2-3h)
   - Test edge cases
   - Timeout handling
   - Connection loss recovery
   - Invalid data handling
   - Source: `docs/TODO_CONSOLIDATED.md` Category 3

**Phase 3 Total:** 26-40h (can start immediately, no hardware deps)

### Phase 4: Advanced Features (Future/Optional)
**Goal:** Enhancements beyond MVP  
**Time:** 3-6 months  
**Priority:** BACKLOG

#### Phase 2 & 3 Features (DepthAI) (~200 items)
- Direct DepthAI integration (bypassing Python wrapper)
- Pure C++ detection pipeline
- Runtime parameter reconfiguration
- ROI (Region of Interest) support
- Dynamic reconfigure for HSV thresholds
- Batch processing for YOLO

#### System Enhancements (~100 items)
- Web dashboard for monitoring
- Remote telemetry
- Data logging and analysis
- Advanced path planning
- Multi-robot coordination
- Auto-calibration routines

#### Research & Exploration (~70 items)
- AI-based control
- Vision transformers for detection
- Alternative sensor evaluation
- Performance benchmarking vs competitors

**Phase 4 Total:** Defer to product roadmap (6-12+ months out)

---

## Detailed Breakdown by Area

### 1. Cotton Detection (Priority: HIGH)

#### Critical (Hardware-Dependent)
1. **DepthAI Device Integration** - 4 TODOs
   - Check device connection status (`depthai_manager.cpp:166`)
   - Runtime FPS updates (`depthai_manager.cpp:329`)
   - Device temperature monitoring (`depthai_manager.cpp:399`)
   - Camera calibration from EEPROM (`depthai_manager.cpp:473`)
   - **Time:** 4-6h | **Dependency:** OAK-D Lite hardware

2. **Spatial Coordinate Extraction** - Phase 1.5
   - Extract X, Y, Z from stereo depth
   - Map depth to bounding boxes
   - Validate coordinate accuracy
   - Handle edge cases (depth unavailable, out of range)
   - **Time:** 2-3h | **Dependency:** Hardware

3. **Field Testing** - Phase 1.6
   - Test with real cotton plants
   - Verify detection accuracy
   - Test lighting conditions
   - Test distance/angle variations
   - **Time:** 4-6h | **Dependency:** Cotton samples

4. **Performance Benchmarking** - Phase 3.8
   - Measure detection latency
   - Frame rate measurement
   - CPU/memory profiling
   - Compare C++ vs Python wrapper
   - **Time:** 2h | **Dependency:** Hardware

#### High (Software)
1. **Wrapper Deprecation**
   - Complete calibration export in C++ (✅ Done)
   - Validate hardware with C++ path
   - Retire Python wrapper
   - Update all documentation
   - **Time:** 4-6h after hardware validation

2. **Runtime Configuration**
   - Implement DepthAI runtime config
   - Confidence threshold adjustment
   - ROI configuration
   - FPS adjustment
   - **Time:** 4-6h

3. **Lifecycle Node**
   - Implement full lifecycle interface
   - State management
   - Diagnostics integration
   - **Time:** 3-4h

#### Medium (Testing & Docs)
1. **Unit Tests** - Phase 3.5
   - CottonDetector tests
   - ImageProcessor tests
   - YOLODetector tests
   - Parameter validation tests
   - **Time:** 3-4h | **Coverage:** 70%+

2. **Integration Tests** - Phase 3.6
   - Test with Yanthra system
   - Coordinate transformation verification
   - End-to-end workflow validation
   - **Time:** 2-3h | **Dependency:** Yanthra integration

3. **Documentation** - Phase 5
   - Example code snippets (`examples/`)
   - FAQ documentation
   - Video tutorials (optional)
   - **Time:** 2-4h

#### Low (Optional Enhancements)
1. **Dynamic Reconfigure** - Phase 4.1
   - Runtime parameter adjustment
   - HSV threshold tuning UI
   - Detection mode switching
   - **Time:** 3-4h

2. **Region of Interest** - Phase 4.2
   - Define detection ROI
   - Ignore regions outside ROI
   - Reduce false positives
   - **Time:** 2-3h

3. **Batch Processing** - Phase 4.4
   - Process multiple frames together
   - Batch YOLO inference
   - **Time:** 2h

**Cotton Detection Subtotal:** ~50-75h (25-35h critical, 12-18h high, 8-12h medium, 5-10h low)

---

### 2. Motor Control (Priority: CRITICAL)

#### Critical (Hardware-Dependent)
1. **MG6010 Hardware Validation** - 9 code TODOs
   - Implement temperature reading (`generic_motor_controller.cpp:1118`)
   - CAN ESTOP command (`safety_monitor.cpp:564`)
   - GPIO shutdown (`safety_monitor.cpp:573`)
   - Error LED signaling (`safety_monitor.cpp:583`)
   - Velocity/effort reading (`generic_hw_interface.cpp:346, 355`)
   - Velocity/torque control modes (`generic_hw_interface.cpp:399`)
   - MG6010 CAN write implementation (`generic_hw_interface.cpp:420`)
   - MG6010 CAN initialization (`generic_hw_interface.cpp:534`)
   - **Time:** 8-10h | **Dependency:** MG6010 motors, CAN interface, GPIO

2. **Motor Communication Testing**
   - Verify 250kbps CAN bitrate
   - Test position control accuracy
   - Test velocity control
   - Test torque control
   - Multi-motor coordination
   - **Time:** 4-6h | **Dependency:** Hardware

3. **Safety System Validation**
   - Test emergency stop mechanisms
   - Verify safety limits (position, velocity, temperature)
   - Test communication timeout handling
   - Test voltage monitoring
   - Test error recovery
   - **Time:** 3-4h | **Dependency:** Hardware

4. **Motor Tuning** - Gap Analysis Task
   - PID parameter optimization
   - Control loop frequency tuning
   - Response time optimization
   - Error threshold adjustment
   - **Time:** 4-6h | **Dependency:** Hardware

#### High (Documentation & Configuration)
1. **Create MOTOR_TUNING_GUIDE.md** - Gap Analysis HIGH
   - Document PID tuning procedure
   - Explain parameter effects
   - Provide tuning examples
   - Add troubleshooting tips
   - **Time:** 2-3h

2. **Service Interface Exposure**
   - Expose motor tuning services
   - Document service APIs
   - Create client examples
   - **Time:** 2-3h

3. **Consolidate Documentation**
   - Merge 15 docs → 1 authoritative README
   - Update status claims
   - Fix date inconsistencies
   - Archive peripheral docs
   - **Time:** 1-2 days (covered in main consolidation)

#### Medium (Testing & Monitoring)
1. **System Health Aggregator**
   - Create system_monitor node
   - Aggregate diagnostics
   - Publish health status
   - Alert on critical errors
   - **Time:** 3-4h

2. **Long-Duration Testing**
   - Stability testing (hours)
   - Load testing (multiple operations)
   - Memory leak detection
   - Performance degradation monitoring
   - **Time:** 2-3h | **Dependency:** Hardware

3. **Integration Tests**
   - Motor + camera coordination
   - Multi-motor synchronization
   - Full robot integration
   - **Time:** 2-3h | **Dependency:** Full hardware

#### Low (Enhancements)
1. **ODrive Cleanup**
   - Deprecate file-based communication
   - Remove cotton_details.txt usage
   - Archive ODrive-specific code
   - **Time:** 2-3h

2. **Configuration Management**
   - Centralized config files
   - Parameter validation
   - Config version tracking
   - **Time:** 2-3h

**Motor Control Subtotal:** ~40-60h (19-26h critical, 6-9h high, 7-10h medium, 4-6h low)

---

### 3. Yanthra Move (Priority: HIGH)

#### Critical (Hardware-Dependent)
1. **GPIO Hardware Implementation** - 6 code TODOs
   - Vacuum pump control (`yanthra_move_system.cpp:111`)
   - Camera LED control (`yanthra_move_system.cpp:138`)
   - Status LED control (`yanthra_move_system.cpp:153`)
   - Keyboard monitoring setup (`yanthra_move_system.cpp:60`)
   - Keyboard monitoring cleanup (`yanthra_move_system.cpp:95`)
   - **Time:** 4-6h | **Dependency:** GPIO hardware, wiring

2. **Calibration & Tuning** - 23 code TODOs
   - Joint homing position verification (multiple files)
   - Replace hard-coded 0.001 values with calibrated offsets
   - Motor state verification checks
   - ROS2 executor pattern updates (replace ros::spinOnce)
   - Jerky motion fixes
   - **Time:** 4-6h | **Dependency:** Hardware

3. **Integration Testing** - Phase 3.6
   - End-to-end cotton picking workflow
   - Coordinate transformation validation
   - Detection → movement → actuation
   - **Time:** 2-3h | **Dependency:** Full system

#### High (Software Improvements)
1. **ROS2 Migration Cleanup**
   - Replace remaining ros::spinOnce patterns
   - Implement proper ROS2 shutdown
   - Update executor patterns
   - **Time:** 2-3h

2. **Cotton Detection Service Update** - Code TODO
   - Port cotton_detection service calls to ROS2
   - Use topic-based detection results
   - Remove legacy service dependencies
   - **Time:** 2-3h

3. **Arm Status Functionality** - Code TODO
   - Implement proper arm status reporting
   - Add telemetry publishing
   - Status service enhancement
   - **Time:** 2-3h

#### Medium (Enhancement & Monitoring)
1. **Logging Enhancement** - Code TODO
   - Implement timestamped log files
   - Structured logging
   - Log rotation
   - **Time:** 2-3h

2. **Documentation Updates**
   - Archive DOCS_CLEANUP_SUMMARY.md
   - Archive LEGACY_COTTON_DETECTION_DEPRECATED.md
   - Update README with validation status
   - **Time:** 1-2h

**Yanthra Move Subtotal:** ~25-35h (10-15h critical, 6-9h high, 3-5h medium)

---

### 4. Documentation (Priority: HIGH)

#### Consolidation (Main Plan)
1. **Cotton Detection** - 4-6h
2. **Motor Control** - 1-2 days
3. **Yanthra Move** - 1-2h
4. **Root Docs** - 3-4h
5. **Archive Strategy** - 4-6h
6. **Navigation & Links** - 2-3h

**Total:** 2.5-4 days (covered in main consolidation plan)

#### Additional Documentation (~200 TODOs from docs/TODO_CONSOLIDATED.md)
1. **Usage Examples** (2-3h)
   - Add to README files
   - Create examples/ directory
   - Code snippets for common tasks

2. **Troubleshooting Guides** (2-3h)
   - Common issues and solutions
   - "How do I..." guides
   - Error message reference

3. **Architecture Documentation** (2-3h)
   - System diagrams
   - Data flow visualization
   - Component interactions

4. **API Documentation** (2-3h)
   - Complete API reference
   - Parameter descriptions
   - Return value documentation

5. **FAQ Sections** (2-3h)
   - Per-module FAQs
   - Setup FAQs
   - Troubleshooting FAQs

**Documentation Subtotal:** 10-15h (beyond consolidation)

---

### 5. Testing & Validation (Priority: MEDIUM)

#### Unit Testing (~70 TODOs from docs/TODO_CONSOLIDATED.md)
1. **Protocol Tests** (2-3h)
   - MG6010 protocol encoding/decoding
   - CAN frame construction
   - Error handling

2. **Component Tests** (3-4h)
   - CottonDetector
   - ImageProcessor
   - YOLODetector
   - SafetyMonitor

3. **Parameter Validation** (1-2h)
   - Config file parsing
   - Parameter range validation
   - Invalid input handling

**Testing Subtotal:** 8-12h

---

### 6. Performance & Optimization (Priority: MEDIUM)

#### Performance (~100 TODOs from docs/TODO_CONSOLIDATED.md)
1. **Control Loop Optimization** (2-3h)
   - Frequency tuning
   - Latency reduction
   - CPU profiling

2. **Detection Pipeline** (2-3h)
   - HSV optimization
   - YOLO inference speed
   - Image preprocessing

3. **Memory Optimization** (2-3h)
   - Buffer pooling
   - Smart pointer optimization
   - Leak detection

4. **Threading** (2-4h)
   - Parallel detection
   - Thread pool
   - Lock-free structures

**Performance Subtotal:** 8-13h

---

### 7. Error Handling & Recovery (Priority: MEDIUM)

#### Robustness (~80 TODOs from docs/TODO_CONSOLIDATED.md)
1. **Connection Management** (2-3h)
   - Auto-reconnection
   - Timeout handling
   - Graceful degradation

2. **Error Reporting** (2-3h)
   - Improved messages
   - Error statistics
   - Diagnostics aggregation

3. **Recovery Strategies** (1-2h)
   - Non-critical fault recovery
   - State restoration
   - Partial functionality modes

**Error Handling Subtotal:** 5-8h

---

## Hardware Dependency Matrix

| Task Category | Hardware Needed | Can Start Now | Estimated Time |
|---------------|-----------------|---------------|----------------|
| **Motor Control Validation** | MG6010 motors, CAN, GPIO | ❌ | 19-26h |
| **Cotton Detection Validation** | OAK-D Lite, cotton samples | ❌ | 10-18h |
| **Yanthra Move GPIO** | GPIO hardware, wiring | ❌ | 10-15h |
| **Documentation Consolidation** | None | ✅ | 2.5-4 days |
| **Unit Testing** | None | ✅ | 8-12h |
| **Performance Optimization** | None (some features) | ✅ | 8-13h |
| **Error Handling** | None | ✅ | 5-8h |
| **Cleanup (remove done/obsolete)** | None | ✅ | 7-10h |

**Total Hardware-Dependent:** 39-59h  
**Total Can Start Now:** 4-6 days (not including consolidation overlap)

---

## Critical Path (Hardware Required)

### Prerequisite: Hardware Setup
1. **MG6010 Motors**
   - CAN interface setup (250kbps)
   - Power supply (48V)
   - Wiring and connections
   - GPIO pins for emergency stop/LEDs

2. **OAK-D Lite Camera**
   - USB connection
   - Mounting hardware
   - Calibration targets

3. **Yanthra Platform**
   - GPIO wiring (pump, LEDs, switches)
   - Full assembly
   - Safety mechanisms

### Critical Path Tasks (In Order)
1. **Motor Communication** (8-10h)
   - Verify CAN communication
   - Test basic motor commands
   - Validate safety systems

2. **Cotton Detection Hardware** (6-8h)
   - DepthAI device integration
   - Spatial coordinate validation
   - Detection accuracy testing

3. **GPIO Implementation** (4-6h)
   - Vacuum pump control
   - LED signaling
   - Switch monitoring

4. **System Integration** (4-6h)
   - Motor + camera coordination
   - Full picking workflow
   - End-to-end validation

5. **Tuning & Optimization** (6-10h)
   - PID parameters
   - Detection thresholds
   - Motion profiles

**Total Critical Path:** 28-40h with hardware

---

## Sources Referenced

### Documentation Sources
1. **docs/TODO_CONSOLIDATED.md** (2,469 items)
   - Section 1: Already Done (~800)
   - Section 2: Obsolete (~600)
   - Section 3: Still Relevant (~700)
   - Section 4: Future Work (~369)

2. **docs/project-management/REMAINING_TASKS.md** (19/41 remaining)
   - 7 hardware-dependent (critical)
   - 5 can do now (medium)
   - 7 optional enhancements

3. **docs/project-management/GAP_ANALYSIS_OCT2025.md** (10 tasks)
   - 4 fully complete
   - 4 partially complete
   - 2 not started

4. **docs/STATUS_REALITY_MATRIX.md** (backlog tracking)
   - Validation gaps
   - Documentation updates
   - Hardware dependencies

### Code Sources
1. **src/cotton_detection_ros2/** (4 TODOs)
   - `depthai_manager.cpp` - Hardware integration TODOs

2. **src/motor_control_ros2/** (9 TODOs)
   - `safety_monitor.cpp` - Hardware safety TODOs
   - `generic_hw_interface.cpp` - CAN implementation TODOs
   - `generic_motor_controller.cpp` - Temperature reading TODO

3. **src/yanthra_move/** (29 TODOs)
   - `yanthra_move_system.cpp` - GPIO implementation TODOs
   - `yanthra_move_aruco_detect.cpp` - Calibration TODOs
   - `yanthra_move_calibrate.cpp` - Position/ROS2 TODOs

4. **src/cotton_detection_ros2/scripts/** (28 TODOs)
   - Mostly in deprecated/legacy scripts
   - Coordinate system hacks
   - Calibration values
   - File path parameters

---

## Extraction Artifacts

For detailed analysis, see:
- **Code TODOs:** `docs/_code_todos_2025-10-15.txt` (70 lines)
- **Doc Signals:** `docs/_doc_signals_2025-10-15.txt` (100 lines, status/date inconsistencies)
- **Doc Checklists:** `docs/_doc_checklist_2025-10-15.txt` (500 lines, all checkbox items)
- **File Inventory:** `docs/_inventory_2025-10-15.txt` (213 markdown files)

---

## Next Steps - Immediate Actions

### This Week (No Hardware)
1. ✅ Complete documentation consolidation (2.5-4 days) - IN PROGRESS
2. Remove "already done" TODOs from docs (4-6h)
3. Archive obsolete TODOs (3-4h)
4. Fix date/status inconsistencies (2-3h)
5. Create MOTOR_TUNING_GUIDE.md stub (1-2h)

### Next Week (No Hardware)
6. Write unit tests for core components (8-12h)
7. Implement error handling improvements (5-8h)
8. Add example code snippets (2-3h)
9. Create FAQ sections (2-3h)
10. Performance profiling and optimization (8-13h)

### When Hardware Available
11. Motor Control hardware validation (19-26h)
12. Cotton Detection hardware testing (10-18h)
13. Yanthra Move GPIO implementation (10-15h)
14. System integration and tuning (10-16h)
15. Long-duration stability testing (4-8h)

---

## Tracking & Updates

**How to Update This Document:**
1. Mark completed items with ✅
2. Move completed items to archive with date
3. Add new TODOs with proper categorization
4. Update time estimates based on actual effort
5. Adjust priorities as requirements change
6. Link to evidence (commits, test results, documentation)

**Review Schedule:**
- Weekly: Update status, adjust priorities
- After hardware sessions: Update validation status
- Monthly: Archive completed work, refresh estimates
- Quarterly: Major review and re-prioritization

---

**Last Updated:** 2025-10-15  
**Next Review:** After hardware availability confirmation  
**Owner:** Development Team  
**Status:** Active backlog tracking

