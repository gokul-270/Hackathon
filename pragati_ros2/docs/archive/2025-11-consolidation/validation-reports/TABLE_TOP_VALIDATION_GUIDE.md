# Table-Top Validation Quick Reference Guide

ℹ️ **HISTORICAL DOCUMENT - Archived Nov 4, 2025**

**Original Date:** 2025-10-10  
**Status at Time:** Ready for Testing  
**Superseded By:** [TESTING_AND_OFFLINE_OPERATION.md](../../../guides/TESTING_AND_OFFLINE_OPERATION.md)

**Historical Context:**  
This guide provided procedures for table-top validation of integrated camera + motor system. The validation approach outlined here was successfully executed and evolved into the comprehensive testing framework now documented in TESTING_AND_OFFLINE_OPERATION.md. The Nov 1, 2025 validation proved the system production-ready with 134ms service latency and 100% reliability.

**Outcome:** ✅ Table-top validation successful, system validated Nov 1, 2025  
**Current Status:** Production Ready - Testing consolidated

---

## 🎯 Original Purpose
Validate integrated camera (OAK-D Lite) + motor (MG6010-i6) system before adding remaining 2 motors.

**Status:**
- ✅ Motor standalone tested (yesterday) - basic functions working
- ✅ Camera standalone tested (yesterday) - detecting cotton
- ⏳ Integrated system testing - **READY TO RUN**

---

## 🔧 Pre-Flight Checklist

### Hardware Setup
- [ ] **Motor (MG6010-i6)**
  - Securely mounted with clear range of motion
  - Powered on (48V per vendor spec)
  - CAN transceiver connected to Raspberry Pi
  - Emergency stop accessible
  
- [ ] **Camera (OAK-D Lite)**
  - Connected to Raspberry Pi via USB
  - USB2 mode will be forced by script
  - Verify with: `lsusb | grep -i luxonis`

- [ ] **Cotton Sample**
  - Placed within camera view
  - Distance: 0.15m to 1.0m from camera
  - Lateral position: within ±0.3m of camera center

### Software Prerequisites
```bash
# Verify ROS 2 workspace is built
ls /home/uday/Downloads/pragati_ros2/install/setup.bash

# Check DepthAI
python3 -c "import depthai; print(depthai.__version__)"

# Test CAN interface (run with sudo)
sudo ip link set can0 up type can bitrate 250000
ip -details link show can0
```

---

## 🚀 Running the Validation

### Simple Execution
```bash
cd /home/uday/Downloads/pragati_ros2
./scripts/validation/system/run_table_top_validation.sh
```

That's it! The script will:
1. Set up CAN and motor driver
2. Launch cotton detection node
3. Run 4 test categories automatically
4. Generate comprehensive reports

### What to Expect

**Phase 1: Hardware Bringup (30-60 seconds)**
```
✓ ROS 2 workspace sourced
✓ CAN interface can0 is UP
✓ Motor topics detected
✓ Cotton detection topic ready: /cotton_detection/results
✓ Rosbag recording started
```

**Phase 2: Running Tests (2-3 minutes)**
```
TEST 1: Cotton Detection Integration
  ✓ Detection test completed
  ✓ Detection results received within 2.0s
  ✓ Detection message structure looks valid

TEST 2: Motor Position Control
  ✓ Motor test completed
  ✓ Motor position control validated

TEST 3: Camera-Motor Coordination (3 cycles)
  Coordination cycle 1/3...
    Detection triggered
    ✓ Joint states active
  ✓ Camera-motor coordination validated

TEST 4: Repeatability (5 cycles)
  ✓ Cycle 1: PASS
  ✓ Cycle 2: PASS
  ...
  Repeatability success rate: 100.0% (5/5)
  ✓ Repeatability target met (≥80%)
```

**Phase 3: Summary**
```
╔════════════════════════════════════════════════════════════════╗
║         PRAGATI TABLE-TOP VALIDATION SUMMARY                   ║
╚════════════════════════════════════════════════════════════════╝

TEST RESULTS:
─────────────────────────────────────────────────────────────────
 1. Cotton Detection Integration:     ✓ PASS
 2. Motor Position Control:            ✓ PASS
 3. Camera-Motor Coordination:         ✓ PASS
 4. Repeatability:                     ✓ PASS
 5. Offline Image-Based Testing:       ✓ PASS (or ⊘ SKIP if no images)
─────────────────────────────────────────────────────────────────

OVERALL: 5/5 tests passed (100.0%)

✓ VALIDATION SUCCESSFUL - Ready to add remaining motors!
```

---

## 📏 Success Criteria

### Test 1: Cotton Detection Integration
- ✅ Results received within 2.0s
- ✅ Coordinates within table-top ranges:
  - x, y: [-0.30, 0.30] meters
  - z: [0.15, 1.00] meters

### Test 2: Motor Position Control
- ✅ Motor responds to position commands
- ✅ Tests use existing `comprehensive_can_motor_test.sh`

### Test 3: Camera-Motor Coordination
- ✅ Detection triggers successfully
- ✅ Motor/joint systems respond
- ✅ At least 2 out of 3 cycles successful

### Test 4: Repeatability
- ✅ Success rate ≥ 80% (4 out of 5 cycles)

### Test 5: Offline Image-Based Testing (NEW!)
- ✅ Tests saved images from `inputs/` or similar folders
- ✅ Validates detection on known images
- ✅ Generates detection results JSON
- ⚠️ Auto-skipped if no images found (not a failure)

---

## 📱 Output Files

**IMPORTANT:** All results are now saved **INSIDE the project directory** for persistence:

All results saved to `pragati_ros2/validation_logs/table_top_<timestamp>/`:

```
pragati_ros2/validation_logs/table_top_20251010_083000/
├── summary.txt                  # Human-readable summary ⭐
├── summary.json                 # Machine-readable results
├── run.log                      # Complete execution log
├── test1_detection.log          # Cotton detection test
├── test1_result.yaml            # Detection message capture
├── test2_motor.log              # Motor position test
├── test3_coord.log              # Coordination test
├── test4_repeat.log             # Repeatability test
├── repeatability.csv            # Per-cycle results
├── test5_offline.log            # Offline image test (NEW!)
├── offline_results.json         # Offline detection results (NEW!)
├── motor_launch.log             # Motor driver output
├── detect_launch.log            # Detection node output
├── rosbag/                      # Recorded ROS topics
└── rosbag.log
```

**Start here:** `summary.txt`

---

## 🔍 Troubleshooting

### Problem: Motor node fails to start
```bash
# Check motor launch log
cat validation_logs/table_top_*/motor_launch.log

# Verify CAN interface
sudo ip link show can0
dmesg | grep -i can | tail -20
```

### Problem: Detection topic not found
```bash
# Check detection log
cat validation_logs/table_top_*/detect_launch.log

# Verify camera connection
lsusb | grep -i luxonis

# Check ROS topics manually
ros2 topic list | grep cotton
```

### Problem: Tests fail
1. **Review individual test logs** in output directory
2. **Check the summary** for specific failure reasons
3. **Inspect rosbag** for message flow issues:
   ```bash
   ros2 bag info validation_logs/table_top_*/rosbag
   ```

### Problem: Offline test not running
```bash
# The offline test looks for images in these locations:
# - pragati_ros2/inputs/
# - pragati_ros2/data/inputs/
# - pragati_ros2/test_images/
# - ~/pragati/inputs/

# To enable offline testing, copy your test image:
mkdir -p inputs
cp /path/to/your/cotton_image.jpg inputs/

# Or create a symlink:
ln -s /path/to/image/folder inputs
```

### Common Issues

| Issue | Solution |
|-------|----------|
| CAN errors | Check termination resistors, verify bitrate 250kbps |
| Camera timeout | Ensure OAK-D Lite powered, try different USB port |
| Motor not responding | Verify power (24V), check CAN wiring |
| Detection coordinates out of range | Adjust cotton position, check camera view |

---

## ✅ After Successful Validation

### Next Steps:
1. **Add second motor** to table-top setup
2. **Update motor configuration** (motor ID, CAN ID)
3. **Run validation again** with 2 motors
4. **Repeat for third motor**
5. **Proceed to full system integration**

### Scaling to Multiple Motors:

The validation script can be adapted for multiple motors by:
- Changing `MOTOR_ID` variable at top of script
- Running test for each motor individually first
- Then testing coordinated multi-motor movement

---

## 📖 Technical Details

### Script Architecture
```
scripts/validation/system/run_table_top_validation.sh
├── Reuses existing test scripts (per user preference)
│   ├── test_cotton_detection.py
│   ├── comprehensive_can_motor_test.sh
│   └── mg6010_test.launch.py
├── Orchestrates test sequence
├── Collects metrics and logs
└── Generates comprehensive reports
```

### Configuration Variables
Located at top of `scripts/validation/system/run_table_top_validation.sh`:
```bash
CAN_IF="can0"                    # CAN interface
CAN_BITRATE="250000"             # 250kbps for MG6010-i6
MOTOR_ID="1"                     # Motor CAN ID
DETECTION_TIMEOUT_S="2.0"        # Detection timeout (USB2)
MOTOR_TOL_DEG="2.0"              # Position tolerance
REPEAT_CYCLES="5"                # Repeatability cycles
```

Adjust these if your setup differs.

---

## 🎓 Understanding the Tests

### Test 1: Cotton Detection Integration
**What it tests:** Can the camera detect cotton and publish results to ROS?

**How it works:**
1. Runs `test_cotton_detection.py` 
2. Waits for message on `/cotton_detection/results`
3. Validates coordinate ranges

**Pass criteria:** Results within 2.0s, coordinates reasonable

---

### Test 2: Motor Position Control
**What it tests:** Can the motor move to commanded positions?

**How it works:**
1. Runs `comprehensive_can_motor_test.sh` or `complete_motor_test.sh`
2. Tests multiple position commands
3. Verifies motor reaches targets

**Pass criteria:** Motor responds to position commands

---

### Test 3: Camera-Motor Coordination
**What it tests:** Do both systems work together?

**How it works:**
1. Triggers detection
2. Observes both detection results and joint states
3. Repeats 3 times

**Pass criteria:** ≥ 2 out of 3 cycles successful

---

### Test 4: Repeatability
**What it tests:** Is the system reliable over multiple cycles?

**How it works:**
1. Runs 5 consecutive detection cycles
2. Tracks success/failure of each
3. Calculates success rate

**Pass criteria:** ≥ 80% success rate (4/5 cycles)

---

### Test 5: Offline Image-Based Testing
**What it tests:** Can the system detect cotton in saved images?

**How it works:**
1. Searches for images in standard locations (`inputs/`, `data/inputs/`, etc.)
2. Runs `test_with_images.py` on found images
3. Generates detection results JSON
4. Validates that images were processed

**Pass criteria:** Images processed successfully (auto-skipped if no images found)

**To enable:**
```bash
# Copy your test images to inputs folder
mkdir -p inputs
cp /path/to/cotton_image.jpg inputs/
```

---

## 📞 Support

### If All Tests Pass
🎉 **Congratulations!** Your table-top setup is validated and ready for motor expansion.

### If Tests Fail
1. Check `/tmp/table_top_validation_*/summary.txt` for details
2. Review individual test logs for specific failures
3. Verify hardware connections
4. Run standalone tests again to isolate issues
5. Check this guide's troubleshooting section

### Script Customization
The script is designed to be easy to modify:
- All configuration at top of file
- Clear test functions
- Extensive logging
- Reuses existing test infrastructure

---

## 📝 Notes

- **Reuses existing scripts:** No code duplication per user preference
- **Non-destructive:** All outputs to `/tmp/`, original workspace untouched
- **Automatic cleanup:** Background processes killed on exit
- **Comprehensive logging:** Every action logged with timestamps
- **Rosbag recording:** All ROS messages captured for later analysis

**Script location:** `/home/uday/Downloads/pragati_ros2/scripts/validation/system/run_table_top_validation.sh`

**Documentation:** This guide

---

## 🚦 Quick Start Summary

```bash
# 1. Hardware check (manual)
#    ✓ Motor powered and secure
#    ✓ Camera connected
#    ✓ Cotton sample in view

# 2. Run validation
cd /home/uday/Downloads/pragati_ros2
./scripts/validation/system/run_table_top_validation.sh

# 3. Check results
#    Look for "VALIDATION SUCCESSFUL" message
#    Review validation_logs/table_top_*/summary.txt

# 4. If successful, proceed to add more motors!
```

---

**Last Updated:** 2025-10-10
**Version:** 1.0
**Status:** Ready for testing
