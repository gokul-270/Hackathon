# Simulated Camera Testing - Quick Reference

**Purpose:** Test yanthra arm without camera hardware  
**Location:** `/home/uday/Downloads/pragati_ros2/scripts/testing/`

---

## 🚀 Quick Commands

```bash
# Convenience wrapper (easiest)
./scripts/testing/simulate_cotton_detection.sh              # Single detection
./scripts/testing/simulate_cotton_detection.sh continuous   # Continuous
./scripts/testing/simulate_cotton_detection.sh custom 0.3 0.0 0.5

# Python script (more options)
python3 scripts/testing/test_cotton_detection_publisher.py --single
python3 scripts/testing/test_cotton_detection_publisher.py --continuous --rate 2.0
python3 scripts/testing/test_cotton_detection_publisher.py --custom 0.4 0.0 0.6 --count 1

# Test scenarios (comprehensive)
python3 scripts/testing/test_detection_scenarios.py                # All scenarios
python3 scripts/testing/test_detection_scenarios.py boundaries     # Specific scenario
```

---

## 📊 Monitoring

```bash
# View detections
ros2 topic echo /cotton_detection/results

# Check rate
ros2 topic hz /cotton_detection/results

# Verify yanthra subscribed
ros2 topic info /cotton_detection/results
```

---

## 🧪 Testing Workflow

### Terminal 1: Launch yanthra
```bash
ros2 launch yanthra_move pragati_complete.launch.py simulation_mode:=true
```

### Terminal 2: Publish detections
```bash
./scripts/testing/simulate_cotton_detection.sh continuous
```

### Terminal 3: Monitor
```bash
ros2 topic echo /cotton_detection/results --field total_count
```

---

## 📐 Coordinate System

**Camera Frame (`camera_link`):**
- **X**: Forward (0.15-0.6m typical)
- **Y**: Right+ / Left- (-0.3 to +0.3m)
- **Z**: Up (0.3-0.8m)

**Example Safe Positions:**
```python
(0.3, 0.0, 0.5)    # Center, 30cm forward, 50cm up
(0.25, 0.1, 0.45)  # Slight right
(0.35, -0.05, 0.55) # Slight left, higher
```

---

## 🎯 Test Scenarios

| Scenario | Command | Tests |
|----------|---------|-------|
| Progressive | `test_detection_scenarios.py progressive` | 1→10 positions |
| Boundaries | `test_detection_scenarios.py boundaries` | Workspace edges |
| Confidence | `test_detection_scenarios.py confidence` | 0.5→1.0 confidence |
| Empty | `test_detection_scenarios.py empty` | Zero detections |
| Circular | `test_detection_scenarios.py circular` | Circle pattern |
| Grid | `test_detection_scenarios.py grid` | 3x3 grid |
| Alternating | `test_detection_scenarios.py alternating` | Dense↔sparse |
| Rapid | `test_detection_scenarios.py rapid` | Fast consecutive |

---

## 🔧 Common Use Cases

### Debug Inverse Kinematics
```bash
# Test boundary positions
./scripts/testing/simulate_cotton_detection.sh custom 0.6 0.3 0.7  # Far, high, right
./scripts/testing/simulate_cotton_detection.sh custom 0.15 0.0 0.3 # Near, low
```

### Load Testing
```bash
# Progressive load
python3 scripts/testing/test_detection_scenarios.py progressive

# Continuous stress test
./scripts/testing/simulate_cotton_detection.sh continuous 10  # 10 Hz
```

### Empty Detection Handling
```bash
python3 scripts/testing/test_detection_scenarios.py empty
```

### Confidence Threshold Testing
```bash
python3 scripts/testing/test_detection_scenarios.py confidence
```

---

## 📚 Full Documentation

See `docs/guides/SIMULATED_CAMERA_TESTING.md` for:
- Complete API reference
- Message format details
- Advanced testing patterns
- Troubleshooting guide
- Integration with hardware tests

---

## ✅ Integration with Testing Matrix

| Phase 0 Test | Can Simulate? | Notes |
|--------------|---------------|-------|
| 0.12 Camera launch | ❌ | Needs hardware |
| 0.13 Detection service | ❌ | Needs camera |
| 0.14 Auto-reconnect | ❌ | Needs USB |
| 0.15 No-cotton behavior | ✅ | Use empty scenario |
| 0.19 Arm launch | ✅ | Independent |
| 0.20 TF tree | ✅ | Independent |
| 0.21 Arm status | ✅ | Independent |

**Workflow:**
1. Test arm logic with simulation (this guide)
2. Validate hardware with camera (when available)

---

## 🐛 Quick Troubleshooting

**yanthra not receiving?**
```bash
ros2 topic info /cotton_detection/results  # Check subscribers
ros2 node list | grep yanthra              # Check node running
```

**Positions unreachable?**
```bash
# Use safer positions
./scripts/testing/simulate_cotton_detection.sh custom 0.25 0.0 0.4
```

**Want to see yanthra logs?**
```bash
ros2 launch yanthra_move pragati_complete.launch.py \
  simulation_mode:=true \
  --log-level yanthra_move_system:=debug
```

---

**Updated:** December 10, 2025  
**Related:** `JANUARY_FIELD_TRIAL_TESTING_MATRIX.md`, `CAMERA_INTEGRATION_GUIDE.md`
