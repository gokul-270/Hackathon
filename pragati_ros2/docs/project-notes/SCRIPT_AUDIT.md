# Test Script Audit & Consolidation Plan

**Problem**: Too many overlapping test scripts causing confusion and duplicate functionality.

**Date**: 2025-11-02

---

## 📊 Current Scripts Analysis

### ✅ **KEEP - Production/Essential Scripts**

| Script | Purpose | Status |
|--------|---------|--------|
| `run_thermal_test.sh` | Comprehensive thermal testing with monitoring | **ESSENTIAL** - Used for stress testing |
| `auto_trigger_detections.py` | Automated periodic detection triggering | **ESSENTIAL** - Core test tool |
| `monitor_camera_thermal_v2.py` | Camera temperature and health monitoring | **ESSENTIAL** - Thermal monitoring |
| `capture_and_view.sh` | Capture camera frame and view locally | **USEFUL** - Visual verification |

### ⚠️ **CONSOLIDATE - Overlapping Functionality**

#### Detection Testing (5 scripts doing similar things):
- `auto_test_cycles.sh` - Detection + motor movement cycles
- `test_cotton_detect_loop.sh` - Detection loop with display
- `quick_detection_test.py` - Quick latency test
- `test_detection_latency.sh` - Measure service latency
- `test_service_latency.py` - Another latency test

**→ CONSOLIDATE INTO**: `test_detection.sh` (single comprehensive tool)

#### System Integration Testing (4 scripts):
- `test_automatic_flow.sh` - Full system test
- `test_full_pipeline.sh` - End-to-end test
- `test_motor_commanding.sh` - Motor + detection
- `test_detection_joint_positions.py` - Detection to motors

**→ CONSOLIDATE INTO**: `test_integrated_system.sh` (unified integration test)

#### Component-Specific Tests (Keep but organize):
- `test_cpp_detection.sh` - C++ node specific
- `test_offline_images.sh` - Offline testing
- `test_motors_rpi.sh` - Motor-only testing
- `test_motor_commands.py` - Motor command testing

**→ ORGANIZE INTO**: `tests/` directory by component

###  ❌ **ARCHIVE/DELETE - Obsolete**

| Script | Reason | Action |
|--------|--------|--------|
| `test_cotton_detection_fixes.sh` | One-time fix validation | Archive |
| `test_critical_fixes.sh` | One-time fix validation | Archive |
| `test_cpp_with_cotton.sh` | Duplicate of test_cpp_detection.sh | Delete |
| `test_rpi_manual.sh` | Unclear purpose, likely obsolete | Delete |
| `monitor_camera_thermal.py` | Superseded by v2 | Delete |
| `validate_timing.sh` | Redundant with latency tests | Delete |

---

## 🎯 Proposed New Structure

```
pragati_ros2/
├── README.md                          # Main documentation
├── TESTING.md                         # Testing guide (NEW)
│
├── scripts/                           # Production scripts
│   ├── launch_system.sh              # Start all nodes
│   ├── stop_system.sh                # Stop all nodes
│   ├── capture_view.sh               # Camera capture
│   └── monitor_thermal.py            # Thermal monitoring
│
├── tests/                             # Organized test scripts
│   ├── detection/
│   │   ├── test_detection.sh         # Unified detection test
│   │   ├── test_latency.py           # Latency measurement
│   │   └── test_offline.sh           # Offline image testing
│   │
│   ├── motors/
│   │   ├── test_motors.sh            # Motor-only tests
│   │   └── test_motor_commands.py    # Motor command API
│   │
│   ├── integration/
│   │   ├── test_system.sh            # Full system integration
│   │   └── test_auto_cycles.sh       # Automated cycle testing
│   │
│   └── stress/
│       ├── thermal_test.sh           # Thermal stress test
│       └── endurance_test.sh         # Long-duration test
│
└── archive/                           # Old/obsolete scripts
    └── fixes/                         # Historical fix validation scripts
```

---

## 📝 Consolidation Actions

### 1. Create Unified Detection Test (`tests/detection/test_detection.sh`)

Combines functionality from:
- `quick_detection_test.py`
- `test_cotton_detect_loop.sh`
- `test_detection_latency.sh`

Features:
- Quick single test
- Loop testing with N cycles
- Latency measurement
- Position display
- Statistics summary

### 2. Create Unified Integration Test (`tests/integration/test_system.sh`)

Combines:
- `test_automatic_flow.sh`
- `test_full_pipeline.sh`
- `auto_test_cycles.sh`

Features:
- Pre-flight checks
- Full system validation
- Automated cycles
- Motor movement verification
- Summary report

### 3. Create Master Testing Guide (`TESTING.md`)

Documents:
- When to use each script
- Quick reference commands
- Troubleshooting guide
- Expected results

---

## 🚀 Implementation Plan

### Phase 1: Create New Structure (Priority 1)
1. Create `tests/` directory structure
2. Create `TESTING.md` guide
3. Create consolidated test scripts

### Phase 2: Move & Archive (Priority 2)
4. Move obsolete scripts to `archive/`
5. Organize remaining scripts into `tests/`
6. Update documentation references

### Phase 3: Cleanup (Priority 3)
7. Delete true duplicates
8. Update README with new structure
9. Test all consolidated scripts

---

## 📖 Quick Reference (After Cleanup)

### For Development/Testing:
```bash
# Test detection only
./tests/detection/test_detection.sh --cycles 5

# Test full system
./tests/integration/test_system.sh

# Stress test (thermal)
./tests/stress/thermal_test.sh 30 20 30  # 30fps, 20min, 30s interval
```

### For Production:
```bash
# Start system
./scripts/launch_system.sh

# Monitor health
./scripts/monitor_thermal.py

# Stop system
./scripts/launch_system.sh
```

---

## ✅ Success Criteria

- ✅ Reduced from ~20 scripts to ~10 organized scripts
- ✅ Clear purpose for each script
- ✅ No functional duplication
- ✅ Easy to find the right tool for the job
- ✅ Single source of truth documentation

---

**Next Step**: Get user approval, then execute cleanup plan.
