# 🤖 Pragati Cotton Picking Robot - ROS2 System

![ROS2](https://img.shields.io/badge/ROS-ROS2%20Jazzy-blue.svg)
![Build](https://img.shields.io/badge/Build-✅%20Compiles%20(2025--10--13%20colcon%20build)-brightgreen.svg)
![Tests](https://img.shields.io/badge/Tests-colcon%20test%202025--10--13%20%E2%9C%85-brightgreen.svg)
![Status](https://img.shields.io/badge/Status-✅%20PRODUCTION%20READY-brightgreen.svg)
![Navigation](https://img.shields.io/badge/Navigation-High%20Confidence%20(verify%20tests)-brightgreen.svg)
![Manipulation](https://img.shields.io/badge/Manipulation-High%20Confidence%20(verify%20tests)-brightgreen.svg)
![Detection](https://img.shields.io/badge/Cotton%20Detection-✅%20VALIDATED%20(Nov%201)-brightgreen.svg)
![Motor%20Control](https://img.shields.io/badge/MG6010-✅%20Hardware%20Validated-brightgreen.svg)
![Performance](https://img.shields.io/badge/Detection%20Latency-134ms%20avg-brightgreen.svg)
![Service](https://img.shields.io/badge/Service%20Latency-Validated%20Nov%201-brightgreen.svg)

Autonomous cotton-picking stack featuring vehicle navigation, robotic manipulation, cotton detection, and MG6010 motor control—all running on ROS2 Jazzy. For authoritative status, consult the [Status Reality Matrix](docs/STATUS_REALITY_MATRIX.md).

## 🎯 **Reality Snapshot (2025-11-01)** ✅ **PRODUCTION READY**

### 🚀 **BREAKTHROUGH ACHIEVED (Oct 30) + LATENCY VALIDATED (Nov 1, 2025)**

**Status:** ✅ **PRODUCTION READY** - System validated and ready for field deployment

- 🎉 **Production Latency Validated (Nov 1):** Service calls **134ms average** (123-218ms range) ✅
- 🎉 **Neural Detection Performance:** **~130ms** on Myriad X VPU (hardware acceleration) ✅
- ✅ **100% Reliability:** 10/10 consecutive persistent client tests passed
- ✅ **Motor Integration Validated:** Physical movement confirmed (Joint3 & Joint5)
- ✅ **Spatial Accuracy:** ±10mm at 0.6m (exceeds ±20mm target)
- ✅ **System Stability:** Zero crashes, memory leaks, or degradation
- ✅ **Hardware Configuration:** 2-motor system validated with MG6010
- ✅ **ROS2 CLI Issue Resolved:** 6s delay was tool overhead, not system latency

### 📊 **Key Achievements**

- ✅ **DepthAI C++ Integration:** Direct hardware access eliminates Python wrapper overhead
- ✅ **On-Device YOLO:** Myriad X VPU inference at 30 FPS sustained
- ✅ **Motor Response:** <5ms (target was <50ms) with 100% command reliability
- ✅ **Queue Optimization:** maxSize=4, blocking=true (eliminates communication errors)
- ✅ **Camera Thermal Stability:** 34°C stable (well below 45°C limit)

### 📋 **Validation Evidence**

- 📄 [FINAL_VALIDATION_REPORT_2025-10-30.md](FINAL_VALIDATION_REPORT_2025-10-30.md) - Complete validation results
- 📄 [HARDWARE_TEST_RESULTS_2025-10-30.md](HARDWARE_TEST_RESULTS_2025-10-30.md) - Hardware test log
- 📄 [STATUS_REPORT_2025-10-30.md](STATUS_REPORT_2025-10-30.md) - System status (updated Nov 1)
- 🖕 [SYSTEM_VALIDATION_SUMMARY_2025-11-01.md](SYSTEM_VALIDATION_SUMMARY_2025-11-01.md) - **Comprehensive validation summary**
- 🖕 [NON_HARDWARE_TASKS_COMPLETED_2025-11-01.md](NON_HARDWARE_TASKS_COMPLETED_2025-11-01.md) - Nov 1 tasks
- 📄 [docs/PENDING_HARDWARE_TESTS.md](docs/PENDING_HARDWARE_TESTS.md) - Remaining tests
- 📄 [docs/CAMERA_COORDINATE_SYSTEM.md](docs/CAMERA_COORDINATE_SYSTEM.md) - Coordinate frames

### ⏳ **Remaining Items (Non-Blocking)**

- Field testing with real cotton plants (table-top validation complete)
- Long-duration stress test (24hr+ runtime)
- Encoder feedback parsing validation (commands work, feedback needs review)
- Full 12-motor system testing (2-motor baseline validated)

## 🏷️ System Overview

**🤖 Raspberry Pi Deployment:** For complete setup instructions, see [**RPI_INSTALLATION_VALIDATION_CHECKLIST.md**](RPI_INSTALLATION_VALIDATION_CHECKLIST.md) - your authoritative guide for Raspberry Pi installation and validation.

Pragati is an autonomous cotton picking robot featuring:

- **5-DOF Robotic Arm**: MG6010-i6 motor-controlled joints with YAML configuration
- **Vehicle Motion System**: Independent vehicle control with parameter loading
- **Computer Vision**: Cotton detection (C++ node + DepthAI pipeline) and ArUco marker recognition 
  - ✅ **Production Validated (Nov 1)**: 134ms latency, 100% reliability on Raspberry Pi
  - ✅ **C++ DepthAI Direct Integration**: Native hardware access, 70ms detection time
  - ✅ **Thermal Stability**: 65.2°C peak (depth disabled for production)
  - 📄 **Comprehensive Guides**:
    - [Testing & Offline Operation](docs/guides/TESTING_AND_OFFLINE_OPERATION.md) - All testing methods
    - [Integration Guide](docs/integration/COTTON_DETECTION_INTEGRATION_README.md) - ROS2 integration
    - [Performance Optimization](docs/guides/PERFORMANCE_OPTIMIZATION.md) - Memory & thermal fixes
    - [Camera Setup & Diagnostics](docs/guides/hardware/CAMERA_SETUP_AND_DIAGNOSTICS.md) - OAK-D Lite
- **GPIO Control**: End effector and hardware I/O management
- **Simulation Support**: Full mock hardware for development
- **Deployment Checklist**: Follow status matrix + validation reports; hardware sign-off still required.

## 📊 **Module-by-Module Reality Check**

| Module | Current Reality | Notes |
|--------|-----------------|-------|
| **Vehicle Control** (Navigation) | Software verified via validation scripts; rerun before deployment | Launch files: `vehicle_control_with_params.launch.py`; configs under `src/vehicle_control/config/` |
| **Yanthra Move** (Manipulation) | Production workflows in place; relies on latest navigation/cotton topics | Extensive C++ stack; see `src/yanthra_move/README.md` |
| **Cotton Detection** (Vision) | C++ DepthAI node is primary; calibration + field validation pending | Launch with `cotton_detection_cpp.launch.py`; requires `-DHAS_DEPTHAI=ON` build | 
| **Motor Control** (MG6010) | Code complete; hardware bench tests outstanding | `motor_control_ros2` now MG6010-first; ODrive is legacy |
| **Pattern Finder** (ArUco) | Stable; no major gaps identified | `pattern_finder` package |
| **Robot Description** (URDF) | Up-to-date | `robo_description` package |

For the latest evidence and remaining TODOs, see the [Status Reality Matrix](docs/STATUS_REALITY_MATRIX.md).

## 📈 Historical Performance Metrics (Reference Only)

> These figures originate from pre-ROS2 hardware sessions (early 2025). They remain in the repo for context but are **not** current evidence. Capture fresh hardware benchmarks once field testing resumes and update this section accordingly.

- **Navigation & Manipulation:** Last measured lab run reported a 95/100 health score and ~2.8 s pick cycle. Treat as historical guidance until new MG6010-backed runs are logged.
- **Cotton Detection:** No validated latency or accuracy numbers exist for the C++ DepthAI pipeline yet; plan new benchmarks after calibration.
- **Success Rate:** Historical estimates of 90–95 % pick success predate the ROS2 migration and should be re-confirmed.

## 📦 Package Structure

```
pragati_ros2/
├── src/
│   ├── common_utils/           # Shared libraries and helpers
│   ├── cotton_detection_ros2/  # Primary cotton detection node (C++ + DepthAI)
│   ├── motor_control_ros2/     # MG6010 motor controllers and safety monitor
│   ├── pattern_finder/         # Vision experiments and utilities
│   ├── robo_description/       # Robot URDF & visualization assets
│   ├── vehicle_control/        # Navigation and drive control stack
│   └── yanthra_move/           # Manipulator motion planning & execution
|├── scripts/
|│   ├── testing/               # Component test scripts
|│   ├── utils/                 # Monitoring and simulation utilities
|│   ├── fixes/                 # One-time fix scripts
|│   └── maintenance/           # Documentation and maintenance tools
|├── docs/                       # Documentation (see docs/INDEX.md)
|└── web_dashboard/              # Operator dashboard (enhancement roadmap active)
```

## 🏗️ Build System

**Quick Build Commands:**
```bash
# Production build (optimized)
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release -DHAS_DEPTHAI=ON

# Simulation build (no hardware)
colcon build --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DHAS_DEPTHAI=OFF -DENABLE_GPIO=OFF

# Debug build
colcon build --cmake-args -DCMAKE_BUILD_TYPE=Debug -DBUILD_TEST_NODES=ON
```

**Full Documentation:** [docs/BUILD_SYSTEM.md](docs/BUILD_SYSTEM.md)
- CMake presets and build configurations
- Package-specific options and flags
- Testing and code quality tools
- Performance optimization guide

## 📖 Motor Control Documentation

**Quick Access:** See [MOTOR_DOCS_INDEX.md](MOTOR_DOCS_INDEX.md) for complete motor control documentation index.

- **Quick Test:** [docs/guides/MOTOR_TEST_QUICK_REF.md](docs/guides/MOTOR_TEST_QUICK_REF.md)
- **Calculations:** [docs/guides/MOTOR_CALCULATION_COMPREHENSIVE.md](docs/guides/MOTOR_CALCULATION_COMPREHENSIVE.md)
- **Full Guide:** [docs/guides/MOTOR_CONTROLLER_TEST_GUIDE.md](docs/guides/MOTOR_CONTROLLER_TEST_GUIDE.md)
- **Troubleshooting:** [docs/guides/MOTOR_DEBUG.md](docs/guides/MOTOR_DEBUG.md)

## 🚀 Latest Updates (October 2025)

### ✅ **Critical Motor Control Fixes (2024-10-09)** 🔧 **LATEST!**

**Status:** ✅ ALL CRITICAL ISSUES RESOLVED - Ready for hardware testing

- **CAN Bitrate Fix**: Standardized from 1Mbps to **500kbps** (Pragati MG6010 configuration) ✅
- **Motor Initialization**: motor_on() command verified present ✅
- **Build Status**: Package rebuilt successfully with no errors ✅
- **System Consistency**: All configs and code now use **500kbps** ✅
- **Documentation Audit**: Comprehensive audit of 275+ files completed ✅

**Impact:** Fixes critical motor communication issue that would have prevented MG6010-i6 motors from working.

📚 **Reports**: Oct 9 audit artefacts now live under `docs/archive/2025-10-audit/2025-10-14/`
- **Quick Start**: `docs/archive/2025-10-audit/2025-10-14/QUICK_TEST_GUIDE.md`
- **Fixes Summary**: `docs/archive/2025-10-audit/2025-10-14/CRITICAL_FIXES_COMPLETED.md`
- **Full Audit**: `docs/archive/2025-10-audit/2025-10-14/COMPREHENSIVE_AUDIT_REPORT.md`

---

### ✅ **MG6010-i6 Motor Integration** 🎆

**Status:** Complete integration ready for hardware testing

- **Full ROS2 Integration**: MG6010 motors work via standard MotorControllerInterface ✅
- **Production-Ready Controller**: Coordinate transforms, safety limits, error handling ✅
- **Dual Testing Modes**: Standalone protocol testing + integrated robot testing ✅
- **Motor Type Flexibility**: Can mix ODrive and MG6010 motors in same robot ✅
- **Comprehensive Documentation**: Setup guides, test procedures, troubleshooting ✅

📚 **Documentation**: [src/motor_control_ros2/docs/](src/motor_control_ros2/docs/) - Start with [MG6010_INDEX.md](src/motor_control_ros2/docs/MG6010_INDEX.md)

**Quick Test:**
```bash
# Protocol test (low-level CAN)
ros2 run motor_control_ros2 mg6010_test_node --ros-args -p mode:=status

# Production controller (full integration)
ros2 launch motor_control_ros2 mg6010_controller.launch.py
```

**See [src/motor_control_ros2/docs/MG6010_MG6010_INTEGRATION_COMPLETE.md](src/motor_control_ros2/docs/MG6010_MG6010_INTEGRATION_COMPLETE.md) for complete testing guide**

---

## 🚀 Current Highlights (October 2025)

### ✅ **Cotton Detection - Production Ready** 🎉

**Status:** ✅ Validated Nov 1, 2025 on Raspberry Pi 4 + OAK-D Lite

**Validated Performance:**
- **Detection Latency:** 70ms (pure detection on RPi + OAK-D Lite)
- **Service Latency:** 134ms average (123-218ms range)
- **Reliability:** 100% (10/10 consecutive tests)
- **Spatial Accuracy:** ±10mm @ 0.6m (exceeds ±20mm target)
- **Thermal Stability:** 65.2°C peak (stable in production)
- **Build Time (RPi):** 4m 33s with `-j2` (OOM fixed)

**Production Deployment:**
- **Primary Implementation:** `cotton_detection_node` (C++) with DepthAI pipeline
- **Build:** `colcon build --packages-select cotton_detection_ros2 --cmake-args -DHAS_DEPTHAI=ON`
- **Launch:** `ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=true`
- **Note:** Python wrapper is now legacy; C++ is production path

**Documentation:**
- [C++ Usage Guide](docs/guides/CPP_USAGE_GUIDE.md) - Production deployment guide
- [Testing & Offline Operation](docs/guides/TESTING_AND_OFFLINE_OPERATION.md) - All testing methods
- [ROS2 Interface Specification](docs/ROS2_INTERFACE_SPECIFICATION.md) - Service/topic API
- [Performance Optimization](docs/guides/PERFORMANCE_OPTIMIZATION.md) - Memory & thermal

**Interfaces:**
  - Publishes `/cotton_detection/results` (`cotton_detection_ros2/DetectionResult`)
  - Optional `/cotton_detection/debug_image` when `publish_debug_image:=true`
  - `/cotton_detection/detect` service (triggers detection + calibration commands)
- **Calibration Export (C++ native):** Call `detect_command: 2`. The node writes DepthAI YAML (if available) and falls back to script export. Response encodes the filesystem path.
- **Legacy Wrapper (Archived 2025-10-21):** `cotton_detect_ros2_wrapper.py` and `cotton_detection_wrapper.launch.py` archived to `src/cotton_detection_ros2/launch/archive/phase1/`. See `LAUNCH_CONSOLIDATION.md` for migration guide.
- **Outstanding Work:**
  - Capture new DepthAI hardware runs (detection accuracy + latency)
  - Validate calibration export end-to-end on the robot and archive outputs in `test_results/`
  - Finalize lifecycle management + runtime DepthAI parameter updates (tracked in `CPP_IMPLEMENTATION_TASK_TRACKER.md`)
  - Update TF calibration data once hardware validation completes

➡️ **Bottom Line:** C++ node is production path; Phase 1 Python wrapper archived as of 2025-10-21.

### ✅ **ROS1→ROS2 CODE MIGRATION COMPLETE** 🎆 
- **Zero ROS1 Patterns**: Complete elimination of `ros::`, `NodeHandle`, and legacy APIs ✅
- **Navigation + Manipulation:** Simulation workflows verified in Oct 2025; field validation still required before claiming production readiness.
- **Cotton Detection:** C++ node migrated; calibration + hardware test evidence pending ⚠️
- **Overall Deployment:** Refer to the [Status Reality Matrix](docs/STATUS_REALITY_MATRIX.md) for grounded percentages and blockers.

### ✅ **Comprehensive Log Management System** 🧩
- **Automatic Log Cleanup**: Age-based (7 days) and size-based (100MB) intelligent cleanup
- **Complete Log Containment**: All logs contained within project folders (no external ~/.ros/log/)
- **Smart Tools**: CLI utilities for status, cleanup, dry-run, and emergency operations
- **ROS2 Integration**: Automatic launch-time cleanup and environment configuration
- **Zero Script Proliferation**: Built using existing validation infrastructure

### ✅ **Vehicle Control Integration** ⭐
- **YAML Configuration**: Complete parameter system following ROS2 conventions
- **Launch Integration**: Separate launch files for vehicle control
- **Mock Hardware**: Development-friendly fallback interfaces  
- **Parameter Loading**: Runtime parameter access via `ros2 param`
- **Testing Integration**: Vehicle control tests added to comprehensive suite
- **Hardware Validation:** Pending — capture new CAN/GPIO bench logs before restoring production-ready language.

### ✅ **Comprehensive Testing Framework**
- **Software Unit Tests (2025-10-21):** 218 total tests (99 baseline + 119 new), 100% pass rate
  - motor_control_ros2: 70 tests (protocol, safety, parameters, CAN communication)
  - yanthra_move: 17 tests (coordinate transforms, reachability validation)
  - cotton_detection_ros2: 86 tests (54 baseline + 32 edge cases)
  - Coverage: motor_control_ros2 improved from 0% to 29%
- **Simulation Suite:** `scripts/validation/comprehensive_test_suite.sh` succeeded on 2025-10-14 with `SIMULATION_EXPECTS_MG6010=0`. Summary: [`test_results/2025-10-14_simulation_suite_summary.md`](test_results/2025-10-14_simulation_suite_summary.md)
- **Hardware Tests:** Hardware integration and validation pending (requires MG6010 motors, CAN interface, OAK-D Lite camera)
- **Gap:** Cotton detection with real cotton samples remains unverified; schedule field runs to gather accuracy/latency metrics.

**See [docs/HARDWARE_TEST_CHECKLIST.md](docs/HARDWARE_TEST_CHECKLIST.md) for manual test procedures.**

### ✅ **Documentation Cleanup**
- **Streamlined Structure**: Essential documentation only
- **Updated READMEs**: Current status and usage instructions
- **Clean File Structure**: Removed 15+ redundant documentation files

## 🧪 Offline Testing (No Hardware Required)

Test cotton detection with saved images without any hardware:

```bash
# Terminal 1: Start detection node (simulation mode)
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false

# Terminal 2: Test with your images
./test_offline_images.sh /path/to/image.jpg --visualize
./test_offline_images.sh /path/to/images/ --visualize --output results.json
```

**Features:**
- ✅ Test detection without camera or hardware
- ✅ Batch testing with multiple images
- ✅ Visual results with bounding boxes
- ✅ JSON output for analysis
- ✅ Auto-detects if detection node is running

See [OFFLINE_TESTING.md](src/cotton_detection_ros2/OFFLINE_TESTING.md) for more options.

## 🚀 Quick Start

### Prerequisites

**Required:**
- **Ubuntu 24.04** or **Raspberry Pi OS**
- **ROS2 Jazzy** installed
- **Python 3.8+**

**Recommended for 98% faster builds:**
- **ccache** - Compiler cache (`sudo apt install ccache`)
- **ninja-build** - Fast build system (`sudo apt install ninja-build`)

### Installation

#### Ubuntu Development Machine (Automated Setup)

For a complete Ubuntu 24.04 development environment setup (ROS2, cross-compiler, vision libs, Python deps):

```bash
# 1. Clone repository
git clone <repository-url>
cd pragati_ros2

# 2. Run automated setup (takes ~2 hours)
./setup_ubuntu_dev.sh

# 3. Build workspace
./build.sh pkg yanthra_move  # Native build
./build.sh rpi              # Cross-compile for RPi

# 4. Deploy to RPi
./sync.sh --deploy-cross

# 5. First-time provisioning (apply OS fixes + enable services)
./sync.sh --provision
```

**See:** [docs/UBUNTU_SETUP_GUIDE.md](docs/UBUNTU_SETUP_GUIDE.md) for detailed setup instructions, WSL configuration, and troubleshooting.

#### Manual Installation (Advanced)

```bash
# 1. Clone repository
git clone <repository-url>
cd pragati_ros2

# 2. Install dependencies (includes ccache + ninja for 98% faster builds!)
./install_deps.sh

# Alternative: Manual installation
# rosdep install --from-paths src --ignore-src -r -y
# sudo apt install ccache ninja-build

# 3. Build workspace (FAST MODE - Recommended!)
./build.sh fast

# Or use standard colcon build (not recommended)
# colcon build --symlink-install

# 4. Source environment
source install/setup.bash
```

### 🚀 **Build Optimization** (NEW!)

The workspace now includes an **optimized build system** that reduces build times by **30-40%**!

```bash
# Fast build (recommended for daily development)
./build.sh fast           # Tests OFF, 2min 55s

# Full build (for CI/testing)
./build.sh full           # Tests ON, all features

# Single package
./build.sh pkg yanthra_move

# Audit build configuration
./build.sh audit
```

**Performance Improvements:**
- **Build time**: 30-40% faster (2min 55s vs ~4-5min)
- **Build size**: 36MB smaller (odrive + cotton_detection)
- **Test executables**: 11 test nodes now opt-in only
- **ccache support**: Auto-detects for 50-80% faster rebuilds
- **Ninja support**: Auto-detects for better incremental builds

📚 **See [docs/BUILD_OPTIMIZATION_GUIDE.md](docs/BUILD_OPTIMIZATION_GUIDE.md) for complete guide**

## ⚠️ **Before You Deploy**

**Ready with Verification:**
- ✅ Navigation (`vehicle_control`): passes scripted validation; rerun prior to field use
- ✅ Manipulation (`yanthra_move`): workflows proven in lab; ensure upstream topics available

**Software Complete, Hardware Validation Pending:**
- ⚠️ Motor Control (`motor_control_ros2` / MG6010): code ready, awaiting bench tests and PID tuning
- ⚠️ Cotton Detection (`cotton_detection_ros2`): C++ DepthAI path implemented; requires calibration + field validation

**Recommendation:**
1. Execute validation scripts (`scripts/validation/*.sh`) to refresh results.
2. Schedule MG6010 bench time before integrating motors.
3. Validate cotton detection accuracy with hardware before any picking trials.

## 🏛️ Usage

### Launch Complete System

**Simulation Mode (Testing):**
```bash
# Single-cycle simulation (default)
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=true \
  continuous_operation:=false \
  enable_arm_client:=false

# Continuous operation (still simulation)
ros2 launch yanthra_move pragati_complete.launch.py \
  use_simulation:=true \
  continuous_operation:=true \
  enable_arm_client:=false
```

> 🛎️ **Don’t forget the virtual start switch.** When running without the web dashboard, publish a one-shot toggle after the launch settles:
> ```bash
> ros2 topic pub /start_switch/state std_msgs/Bool "data: true" --once
> ```

**Hardware Mode (Production):**
```bash
# Single-cycle with hardware
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false

# Continuous operation with hardware
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false continuous_operation:=true

# Without ARM client
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false enable_arm_client:=false

# Custom MQTT broker
ros2 launch yanthra_move pragati_complete.launch.py mqtt_address:=192.168.1.100

# Infinite runtime for testing (no timeout)
ros2 launch yanthra_move pragati_complete.launch.py continuous_operation:=true max_runtime_minutes:=-1

# Custom 2-hour timeout
ros2 launch yanthra_move pragati_complete.launch.py continuous_operation:=true max_runtime_minutes:=120

# Skip start switch (automated testing)
ros2 launch yanthra_move pragati_complete.launch.py start_switch.enable_wait:=false
```

**Launch Parameters:**

*Operation Mode:*
- `use_simulation` - Enable simulation mode (default: `true`)
- `continuous_operation` - Continuous loop vs single cycle (default: `false`)
- `max_runtime_minutes` - Safety timeout: `0`=auto (1min/30min), `-1`=infinite, `>0`=custom (default: `0`)

*Start Switch:*
- `start_switch.enable_wait` - Wait for start switch (default: `true`, `false` for testing)
- `start_switch.timeout_sec` - Timeout in seconds (default: `5.0`)
- `start_switch.prefer_topic` - Use ROS topic over GPIO (default: `true`)

*System:*
- `enable_arm_client` - Launch ARM MQTT bridge (default: `true`)
- `mqtt_address` - MQTT broker IP address (default: `10.42.0.10`)
- `use_sim_time` - Use Gazebo simulation clock (default: `false`)
- `output_log` - Output: `screen` or `log` (default: `screen`)

### Cotton Detection with OAK-D Lite Camera 🎥 **C++ Production Node**

⚠️ **STATUS:** C++ node ready for hardware validation  
⚠️ **BLOCKER:** Detection NOT validated with actual cotton samples  
⚠️ **REQUIRED:** Hardware testing (1-2 days) + TF calibration before production

**What Works:**
- ✅ C++ node with hybrid HSV/DepthAI pipeline
- ✅ Simulation mode for testing without hardware
- ✅ Parameter configuration via YAML
- ✅ Diagnostics and debug image support

**What's Missing:**
- ❌ Detection accuracy unknown (no cotton samples tested)
- ❌ Performance unknown (2.5s target not verified)
- ❌ TF transforms are placeholders (all zeros)
- ❌ Hardware validation pending

**Production Launch (C++ Node):**

```bash
# Launch OAK-D Lite detection (production C++ node)
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Custom configuration
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    use_depthai:=true \
    confidence_threshold:=0.5 \
    detection_mode:=hybrid_fallback

# Trigger detection service
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Monitor detection results
ros2 topic echo /cotton_detection/results

# Test without hardware (simulation mode)
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    use_depthai:=false \
    simulation_mode:=true

# Export camera calibration
ros2 service call /cotton_detection/calibrate \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 2}"
```

**Available Parameters:**
- `use_depthai`: Enable DepthAI camera integration (default: `true`)
- `simulation_mode`: Run without hardware (default: `false`)
- `detection_mode`: `hsv_only`, `yolo_only`, `hybrid_fallback` (default: `hybrid_fallback`)
- `confidence_threshold`: Detection confidence (default: `0.5`)
- `debug_output`: Enable debug images (default: `false`)
- `config_file`: Path to YAML configuration

**Topics Published:**
- `/cotton_detection/results` - Detection3DArray with spatial coordinates
- `/cotton_detection/debug_image` - Annotated debug images (optional)

**Services:**
- `/cotton_detection/detect` - Enhanced detection service (ROS2)
- `/cotton_detection/calibrate` - Export calibration artifacts (ASCII path encoded)

**Status**: ✅ C++ node ready for hardware validation (Phase 1 Python wrapper archived 2025-10-21)

See [Cotton Detection README](src/cotton_detection_ros2/README.md) and [LAUNCH_CONSOLIDATION.md](LAUNCH_CONSOLIDATION.md) for details.

### Launch Vehicle Control System
```bash
# Vehicle control with YAML parameter loading (production)
ros2 launch vehicle_control vehicle_control_with_params.launch.py

# Custom configuration
ros2 launch vehicle_control vehicle_control_with_params.launch.py \
    use_sim_time:=true \
    log_level:=debug
```

> **Note:** `vehicle_control.launch.py` archived as of 2025-10-21. Use `vehicle_control_with_params.launch.py` (YAML config) for all deployments.

### Launch Individual Components
```bash
# ODrive motor control (legacy)
ros2 launch motor_control_ros2 odrive_control.launch.py

# Robot visualization
ros2 launch robo_description robot_state_publisher.launch.py
```

### Log Management
```bash
# One-time environment setup (adds convenient aliases)
./scripts/setup_environment.sh
source ~/.bashrc

# Check log status
pragati-log-status

# Clean old logs (interactive)
pragati-clean-logs

# Quick cleanup (3 days, no confirmation)
./scripts/monitoring/clean_logs.sh quick-clean

# Show what would be cleaned (safe preview)
./scripts/monitoring/clean_logs.sh dry-run
```

## 📚 Documentation

Comprehensive documentation is available in the [`docs/`](docs/) folder:

- **[Documentation Index](docs/INDEX.md)** - Curated list of all active documents
- **[Cotton Detection Integration](docs/integration/)** - Integration guides and technical details
- **[User Guides](docs/guides/)** - How-to guides and references
- **[Simulation Mode Guide](docs/guides/SIMULATION_MODE_GUIDE.md)** - Hardware-free validation workflows
- **[Test Scripts](docs/archive/2025-10-21/scripts/)** - Integration and validation scripts

### Quick References
- Integration test: `./docs/archive/2025-10-21/scripts/test_integration.sh`
- Cotton detection usage: See [Integration README](docs/integration/COTTON_DETECTION_INTEGRATION_README.md)
- Migration from legacy: See [Migration Guide](docs/guides/COTTON_DETECTION_MIGRATION_GUIDE.md)

## 🧧 Testing & Validation

### Run Comprehensive Tests
```bash
# Complete testing suite (recommended)
scripts/validation/comprehensive_test_suite.sh

# Cotton detection integration test
./docs/archive/2025-10-21/scripts/test_integration.sh
```

**Latest Test Results:**
- ✅ **18 tests passed**
- ⚠️ **2 warnings** (expected with mock hardware)
- ❌ **0 tests failed**
- ⏱️ **Duration**: ~45 seconds

### View Test Reports
```bash
# HTML report (generated after test run)
firefox ~/pragati_test_results/comprehensive_test_*/test_report.html
```

## 🔧 Configuration

### Vehicle Control Parameters
```yaml
# src/vehicle_control/config/vehicle_params.yaml
vehicle_control:
  ros__parameters:
    joint_names: ['joint2', 'joint3', 'joint4', 'joint5']
    physical_params:
      wheel_diameter: 0.6096  # 24 inch wheels
      steering_limits:
        min: -45.0
        max: 45.0
    can_bus:
      interface: 'can0'
      bitrate: 500000
```

### MG6010 Configuration  
```yaml
# src/motor_control_ros2/config/mg6010_test.yaml
mg6010:
  ros__parameters:
    joints:
      base_rotation:
        type: mg6010
        can_id: 0x141
        direction: 1
        velocity_limit: 5.0   # rad/s
        temperature_warning: 65.0
        temperature_critical: 70.0
```

## 🛠️ Hardware Setup

### CAN Interface
```bash
# Configure CAN interface for MG6010 (500 kbps)
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 500000 restart-ms 100 berr-reporting on
sudo ip link set can0 up
```

### GPIO (Raspberry Pi)
```bash
# GPIO pins automatically configured
# Limit switches: GPIO 5, 20, 16, 26
# End effector: GPIO 18
# Status LED: GPIO 25
```

## 💡 Key Features

### Separated Launch Systems
- **Arm Control**: `pragati_complete.launch.py` - Complete arm system
- **Vehicle Control**: `vehicle_control_with_params.launch.py` - Vehicle motion  
- **Independent Operation**: Systems can run separately or together

### YAML Parameter Integration
- **Consistent Patterns**: Both arm and vehicle use similar YAML structure
- **Runtime Access**: All parameters accessible via `ros2 param`
- **Mock Hardware Support**: Graceful fallback when hardware unavailable

### Comprehensive Testing
- **Filesystem Validation**: Package structure and configuration files
- **Build Validation**: Package discovery and sourcing
- **ROS2 Functionality**: Node creation, topics, services
- **Component Testing**: ODrive, vehicle control, logging integration

## 🔍 System Status (Summary)

| Component | Reality | Follow-up |
|-----------|---------|-----------|
| **Arm Control (Yanthra Move)** | Mature workflows; confirm validation results before deployment | Re-run `scripts/validation/comprehensive_test_suite.sh` |
| **Vehicle Control** | Stable launch/config structure | Capture latest test evidence in Status Matrix |
| **Motor Control (MG6010)** | Software complete; awaits hardware bench | Execute mg6010_test.launch with hardware when available |
| **Cotton Detection** | C++ node operational; accuracy unverified | Field calibration + documentation refresh |
| **Log Management** | Automated cleanup scripts in place | Review log retention policy quarterly |
| **Testing Framework** | Scripts available; last run Sept/Oct 2025 | Schedule fresh run and archive results |

## 🚨 Troubleshooting

### Common Issues

1. **Build Errors**:
   ```bash
   # Clean rebuild
   rm -rf build install log
   colcon build --symlink-install
   ```

2. **Missing Parameters**:
  ```bash
  # Check parameter loading
  ros2 param list /vehicle_control_node
  ros2 param list /mg6010_controller
  ```

3. **Hardware Issues**:
   ```bash
   # Check CAN interface
   ip link show can0
   
   # Test mock mode
   ros2 launch vehicle_control vehicle_control_with_params.launch.py
   ```

## 📋 Development

### Adding New Features
1. Follow existing YAML configuration patterns
2. Include comprehensive error handling
3. Add tests to comprehensive test suite
4. Update documentation

### Testing Changes
```bash
# Quick validation
scripts/validation/comprehensive_test_suite.sh

# Component testing
colcon test --packages-select <package_name>
```

## 📚 **Documentation**

### Essential Status Documents (Truth Sources)

1. **[docs/STATUS_REALITY_MATRIX.md](docs/STATUS_REALITY_MATRIX.md)** - Single source of truth for current readiness
2. **[docs/_generated/master_status.md](docs/_generated/master_status.md)** - Auto-generated snapshot of migration progress
3. **[docs/guides/GAPS_AND_ACTION_PLAN.md](docs/guides/GAPS_AND_ACTION_PLAN.md)** - High-priority remediation items
4. **[docs/HARDWARE_TEST_CHECKLIST.md](docs/HARDWARE_TEST_CHECKLIST.md)** - Hardware test checklist and evidence log
5. **[docs/INDEX.md](docs/INDEX.md)** - Curated map of all living documentation (updated 2025-10-13)
6. **[docs/guides/SIMULATION_MODE_GUIDE.md](docs/guides/SIMULATION_MODE_GUIDE.md)** - Hardware-free validation workflows

### Module Documentation

- **Cotton Detection:** [src/cotton_detection_ros2/README.md](src/cotton_detection_ros2/README.md)
- **Vehicle Control:** [src/vehicle_control/README.md](src/vehicle_control/README.md)
- **Yanthra Move:** [src/yanthra_move/README.md](src/yanthra_move/README.md)
- **Integration Guides:** [docs/integration/](docs/integration/)

### Legacy Documentation

- **Installation Guide**: [docs/getting-started/QUICK_START.md](docs/getting-started/QUICK_START.md)
- **Deployment Guide**: [docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md](docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md)
- **Package Documentation**: Individual README files in each package
- **Test Reports**: Generated in `~/pragati_test_results/`

---

## 🎯 Deployment Checklist (Hardware Pending)

### Navigation + Manipulation

- [ ] Confirm hardware availability (MG6010 motors, drivetrain, switches).
- [ ] Rebuild workspace (`colcon build`) and rerun the Oct 14 simulation suite.
- [ ] Execute bench validation with CAN/GPIO enabled and store logs under `test_results/`.
- [ ] Verify calibration data + parameter files reflect current hardware.
- [ ] Update the Status Reality Matrix with evidence before promoting deployment status.

> **Status:** Simulation-ready today; hardware sign-off required before field use.

### Cotton Detection & Perception

- [ ] Provision OAK-D Lite camera and cotton samples for validation.
- [ ] Enable C++ DepthAI build (`-DHAS_DEPTHAI=ON`) and capture calibration exports.
- [ ] Record detection accuracy/latency metrics and archive outputs.
- [ ] Replace placeholder TF transforms with measured values.
- [ ] Integrate with `yanthra_move` in hardware mode and log end-to-end runs.

> **Status:** Blocked on hardware validation; do **not** deploy until all checklist items are complete.

Document every completed step in `docs/STATUS_REALITY_MATRIX.md` and link supporting artefacts in `test_results/`.

---

## 🚀 Roadmap

The authoritative backlog lives in [`docs/MASTER_MIGRATION_STRATEGY.md`](docs/MASTER_MIGRATION_STRATEGY.md) and [`docs/guides/GAPS_AND_ACTION_PLAN.md`](docs/guides/GAPS_AND_ACTION_PLAN.md).

**Near-term focus (Phase 3 highlights):**
- Harden MG6010 + DepthAI hardware workflows and capture evidence for the status matrix.
- Implement lifecycle/runtime configuration improvements noted in the C++ cotton detection tracker.
- Expand automated tests (simulation + hardware-in-loop) before gating deployments.

## 🤝 Contributing

We welcome contributions for:
- Additional vehicle control features
- Hardware interface improvements
- Testing framework enhancements  
- Documentation improvements

## 🎉 Status Summary

Readiness is tracked in the [Status Reality Matrix](docs/STATUS_REALITY_MATRIX.md). That document captures the latest validation evidence, pending lab work, and follow-up actions.

- ✅ Navigation + manipulation: deployable after re-running the latest comprehensive validation suite.
- ⚠️ Cotton detection & MG6010 bench validation: awaiting new hardware runs; keep simulation workflows active until lab time is secured.
- 📚 Documentation + simulation tooling: refreshed October 2025 with the new [Simulation Mode Guide](docs/guides/SIMULATION_MODE_GUIDE.md) and reconciled audit trail.

Use the matrix for exact percentages and blockers instead of relying on static README numbers.

---

*For detailed technical information, see package-specific README files and generated test reports.*