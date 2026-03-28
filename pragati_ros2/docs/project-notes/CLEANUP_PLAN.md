# Script Cleanup & Organization Plan

## Current Situation

**Root Directory**: 53 shell/python scripts (scattered, hard to find)
**scripts/testing/**: 5 existing scripts
**test_suite/**: 29 scripts (phase-based integration tests)

## Problem
- Too many test scripts in root directory
- Unclear which scripts to use for common tasks
- Duplicate/obsolete scripts coexist with active ones
- No clear organization by purpose

## Solution
Reorganize into **purpose-based** directory structure while keeping frequently-used scripts accessible.

---

## Proposed Structure

```
pragati_ros2/
├── Root (frequently used operations)
│   ├── build.sh, build_rpi.sh
│   ├── launch_all.sh, stop_all.sh
│   ├── emergency_motor_stop.sh ⚠️ (safety critical)
│   └── capture_and_view.sh, capture_view.sh
│
├── scripts/
│   ├── testing/
│   │   ├── detection/       ← Cotton detection tests
│   │   ├── integration/     ← Full system tests (MOST IMPORTANT)
│   │   ├── motor/           ← Motor controller tests
│   │   └── stress/          ← Thermal & endurance tests
│   │
│   ├── utils/               ← Diagnostic utilities
│   ├── deployment/          ← RPI setup & sync
│   └── setup/               ← Dependency installation
│
└── archive/obsolete_tests/  ← Archived one-time scripts
```

---

## File Mapping

### ✅ KEEP IN ROOT (7 files)
Essential, frequently-used operational scripts:
- `build.sh`, `build_rpi.sh`
- `launch_all.sh`, `stop_all.sh`
- `emergency_motor_stop.sh` ⚠️
- `capture_and_view.sh`, `capture_view.sh`

### 🧪 INTEGRATION TESTS (4 files → scripts/testing/integration/)
**These are the most important for daily testing!**

| Current | New Location | Purpose |
|---------|-------------|---------|
| `auto_test_cycles.sh` | `scripts/testing/integration/auto_cycles.sh` | Automated N-cycle detection+movement test |
| `test_automatic_flow.sh` | `scripts/testing/integration/automatic_flow.sh` | Tests detection→yanthra→motors flow |
| `test_full_pipeline.sh` | `scripts/testing/integration/full_pipeline.sh` | Complete end-to-end pipeline with logging |
| `integrated_test.sh` | `scripts/testing/integration/manual_system_test.sh` | Manual step-by-step system test |

### 📷 DETECTION TESTS (9 files → scripts/testing/detection/)
Cotton detection specific tests:

| Current | New Location | Purpose |
|---------|-------------|---------|
| `quick_detection_test.py` | `scripts/testing/detection/quick_test.py` | Quick single detection |
| `auto_trigger_detections.py` | `scripts/testing/detection/auto_trigger.py` | Auto-triggered loop testing |
| `test_cotton_detect_loop.sh` | `scripts/testing/detection/loop_test.sh` | Loop detection test |
| `test_detection_latency.sh` | `scripts/testing/detection/latency_test.sh` | Measure detection latency |
| `test_service_latency.py` | `scripts/testing/detection/service_latency.py` | Service call timing |
| `test_cpp_detection.sh` | `scripts/testing/detection/cpp_node_test.sh` | C++ node specific test |
| `test_offline_images.sh` | `scripts/testing/detection/offline_test.sh` | Offline image detection |
| `test_camera_diagnostics.sh` | `scripts/testing/detection/camera_diagnostics.sh` | Camera health check |
| `test_detection_joint_positions.py` | `scripts/testing/integration/detection_to_joints.py` | Detection→joint mapping |

### ⚙️ MOTOR TESTS (4 files → scripts/testing/motor/)
Motor controller tests:

| Current | New Location | Purpose |
|---------|-------------|---------|
| `test_motors_rpi.sh` | `scripts/testing/motor/test_motors.sh` | Basic motor test on RPI |
| `test_motor_commands.py` | `scripts/testing/motor/test_commands.py` | Motor command API test |
| `test_motor_commanding.sh` | `scripts/testing/motor/test_commanding.sh` | Motor commanding integration |
| `run_motor_test_rpi.sh` | `scripts/testing/motor/run_test_rpi.sh` | Run motor test remotely |

### 🔥 STRESS & THERMAL TESTS (4 files → scripts/testing/stress/)
Performance and endurance testing:

| Current | New Location | Purpose |
|---------|-------------|---------|
| `monitor_camera_thermal_v2.py` | `scripts/testing/stress/monitor_thermal.py` | Monitor camera temperature |
| `run_thermal_test.sh` | `scripts/testing/stress/thermal_test.sh` | Thermal stress test script |
| `stress_test_background.sh` | `scripts/testing/stress/background_test.sh` | Background stress testing |
| `full_stress_test.sh` | `scripts/testing/stress/full_stress.sh` | Full stress test suite |

### 🛠️ UTILITIES (7 files → scripts/utils/)
Diagnostic and monitoring utilities:

| Current | New Location | Purpose |
|---------|-------------|---------|
| `analyze_test_logs.sh` | `scripts/utils/analyze_logs.sh` | Log analysis utility |
| `check_joint_states.sh` | `scripts/utils/check_joints.sh` | Joint state checker |
| `check_system_status.sh` | `scripts/utils/system_status.sh` | System status overview |
| `monitor_commands.sh` | `scripts/utils/monitor_commands.sh` | Monitor ROS2 commands |
| `quick_motor_check.sh` | `scripts/utils/quick_motor_check.sh` | Quick motor diagnostic |
| `simple_monitor.sh` | `scripts/utils/simple_monitor.sh` | Simple system monitor |
| `debug_start_switch.sh` | `scripts/utils/debug_start_switch.sh` | Debug START switch |

### 📦 DEPLOYMENT & SETUP (7 files → scripts/deployment/ & scripts/setup/)
RPI setup, sync, and deployment:

| Current | New Location | Purpose |
|---------|-------------|---------|
| `rpi_setup_and_test.sh` | `scripts/deployment/rpi_setup_and_test.sh` | Setup and test on RPI |
| `rpi_setup_depthai_cpp.sh` | `scripts/deployment/rpi_setup_depthai.sh` | DepthAI C++ setup |
| `rpi_verify_setup.sh` | `scripts/deployment/rpi_verify.sh` | Verify RPI setup |
| `sync_to_rpi.sh` | `scripts/deployment/sync_to_rpi.sh` | Sync code to RPI |
| `sync_camera_diagnostics_to_rpi.sh` | `scripts/deployment/sync_camera_diagnostics.sh` | Sync camera diagnostics |
| `sync.sh` | Root | Unified deployment script | KEEP - Primary deployment tool |
| `install_deps.sh` | `scripts/setup/install_deps.sh` | Install dependencies |

### 📦 ARCHIVE (9 files → archive/obsolete_tests/)
Obsolete one-time fix/validation scripts:

| Current | Reason for Archiving |
|---------|---------------------|
| `test_cotton_detection_fixes.sh` | One-time validation for specific fixes |
| `test_critical_fixes.sh` | One-time validation for critical patches |
| `test_cpp_with_cotton.sh` | Duplicate of cpp_detection (obsolete) |
| `validate_timing.sh` | Redundant with latency_test.sh |
| `test_rpi_manual.sh` | Unclear purpose (obsolete) |
| `monitor_camera_thermal.py` | Superseded by v2 |
| `test.sh` | Generic test wrapper (replaced) |
| `apply_build_improvements.sh` | One-time build optimization |
| `apply_performance_fixes.sh` | One-time performance patches |

---

## Execution Steps

1. **Backup** (automatic in script)
   - Creates `archive/obsolete_tests/` for old scripts

2. **Create Structure** (automatic)
   ```bash
   scripts/testing/{detection,integration,stress,motor}/
   scripts/utils/
   scripts/deployment/
   scripts/setup/
   archive/obsolete_tests/
   ```

3. **Move Files** (categorized)
   - Integration tests → `scripts/testing/integration/`
   - Detection tests → `scripts/testing/detection/`
   - Motor tests → `scripts/testing/motor/`
   - Stress tests → `scripts/testing/stress/`
   - Utilities → `scripts/utils/`
   - Deployment → `scripts/deployment/`
   - Obsolete → `archive/obsolete_tests/`

4. **Generate Documentation**
   - Creates `scripts/testing/QUICK_REFERENCE.md`
   - Comprehensive command guide with examples

---

## Usage After Cleanup

### Quick Start
```bash
# Launch system
./launch_all.sh

# Run 10 automated test cycles
./scripts/testing/integration/auto_cycles.sh 10

# Check status
./scripts/utils/system_status.sh

# Stop system
./stop_all.sh
```

### Safety
```bash
# Emergency stop (always accessible)
./emergency_motor_stop.sh
```

---

## Benefits

✅ **Clear Organization**: Find scripts by purpose (testing/utils/deployment)
✅ **Reduced Clutter**: Root directory only has 7 essential scripts
✅ **No Duplication**: Obsolete scripts archived, not deleted
✅ **Easy Discovery**: QUICK_REFERENCE.md with all commands
✅ **Safety**: Critical scripts (emergency_motor_stop.sh) stay in root
✅ **Workflow-Oriented**: Integration tests prominently placed
✅ **Reversible**: All files moved, not deleted (can undo if needed)

---

## Execution

### Preview Changes (Dry-Run)
```bash
./CLEANUP_SCRIPTS.sh --dry-run
```

### Execute Cleanup
```bash
./CLEANUP_SCRIPTS.sh
```

**Estimated Time**: ~1 second
**Files Affected**: 42 moved, 9 archived, 7 remain in root

---

## Post-Cleanup Tasks

1. ✅ Review `scripts/testing/QUICK_REFERENCE.md`
2. ✅ Test key integration scripts in new locations
3. ✅ Update any external documentation referencing old paths
4. ✅ Update CI/CD pipelines if they reference scripts
5. ✅ Inform team members of new structure

---

## Rollback Plan

If needed, files can be moved back manually:
```bash
# Example: restore from archive
mv archive/obsolete_tests/test.sh .

# Example: move back to root
mv scripts/testing/integration/auto_cycles.sh auto_test_cycles.sh
```

All original filenames are preserved in their new locations (or renamed for clarity).
