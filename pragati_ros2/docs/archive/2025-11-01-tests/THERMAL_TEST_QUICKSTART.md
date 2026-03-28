# Thermal Test Quick Start Guide

## 🚀 Super Easy - One Command Test

Run everything automatically with one script!

### On Raspberry Pi:

```bash
ssh ubuntu@192.168.137.253
cd /home/ubuntu/pragati_ros2

# Run 20-minute test at 30 FPS with auto-triggers every 30 seconds
./run_thermal_test.sh 30 20 30

# It will automatically:
# 1. Launch ROS2 detection node
# 2. Start thermal monitoring (logs to CSV)
# 3. Auto-trigger detection every 30 seconds
# 4. Run for 20 minutes then stop
# 5. Save all results

# Just watch the temperature readings scroll by!
# Press Ctrl+C to stop early
```

### Arguments:

```bash
./run_thermal_test.sh [FPS] [DURATION_MIN] [TRIGGER_INTERVAL_SEC]

# Examples:
./run_thermal_test.sh 30 20 30  # 30 FPS, 20 min, trigger every 30s
./run_thermal_test.sh 15 15 20  # 15 FPS, 15 min, trigger every 20s
./run_thermal_test.sh 10 10 15  # 10 FPS, 10 min, trigger every 15s
```

---

## 📊 What You'll See

```
======================================================================
  🌡️  Comprehensive Thermal Test - OAK-D Lite
======================================================================

Test Configuration:
  FPS: 30
  Duration: 20 minutes
  Trigger Interval: 30 seconds

Output:
  📝 Thermal log: thermal_test_30fps_20251031_182500.csv

Starting in 5 seconds... Press Ctrl+C to cancel

======================================================================
  Starting Test Components
======================================================================

1️⃣  Launching Cotton Detection Node...
   PID: 12345
   ✅ Node started

2️⃣  Starting Thermal Monitor...
   PID: 12346
   ✅ Monitor started

3️⃣  Starting Auto-Trigger (40 triggers)...
   PID: 12347
   ✅ Auto-trigger started

======================================================================
  ⏳ Test Running
======================================================================

Test will run for 20 minutes
Monitoring...

❄️  2025-10-31 18:25:00 |     0s | Avg:  45.2°C | CSS:  44.8°C | MSS:  45.6°C | COOL
✅ 2025-10-31 18:25:10 |    10s | Avg:  52.3°C | CSS:  51.9°C | MSS:  52.7°C | COOL
✅ 2025-10-31 18:25:20 |    20s | Avg:  58.7°C | CSS:  58.2°C | MSS:  59.1°C | COOL
...
```

---

## 🎯 Manual Testing (3 Separate Terminals)

If you prefer to run components separately:

### Terminal 1: ROS2 Node

```bash
ssh ubuntu@192.168.137.253
cd /home/ubuntu/pragati_ros2
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
```

### Terminal 2: Thermal Monitor

```bash
ssh ubuntu@192.168.137.253
cd /home/ubuntu/pragati_ros2
./monitor_camera_thermal.py -i 10 -o test_30fps.csv
```

### Terminal 3: Auto-Trigger

```bash
ssh ubuntu@192.168.137.253
cd /home/ubuntu/pragati_ros2
source install/setup.bash
./auto_trigger_detections.py -i 30
```

---

## 📈 Analyzing Results

### Download CSV from RPi

```bash
# On your PC:
scp ubuntu@192.168.137.253:/home/ubuntu/pragati_ros2/thermal_test_*.csv ~/Downloads/
```

### Open in Excel/LibreOffice

1. Open CSV file
2. Select columns: `Elapsed_Seconds` and `Average_Temp_C`
3. Insert → Chart → Line Chart
4. Watch the temperature curve!

### Expected Curves

**30 FPS (current):**
```
Temp (°C)
80 |                    ___________⚠️
75 |              _____/
70 |         ____/
65 |    ____/
60 | __/
   +-------------------------------- Time
   0    5    10   15   20 (minutes)
   
Stabilizes at: 76-78°C (WARNING)
```

**15 FPS (recommended):**
```
Temp (°C)
80 |
75 |
70 |              ___________✅
65 |         ____/
60 |    ____/
   +-------------------------------- Time
   0    5    10   15   20 (minutes)
   
Stabilizes at: 65-68°C (NORMAL)
```

---

## 🔄 Testing Different FPS

### Test 1: 30 FPS (Current - Baseline)

```bash
# Edit config first (only needed for first test)
nano src/cotton_detection_ros2/config/cotton_detection_cpp.yaml
# Verify: camera_fps: 30

# Run test
./run_thermal_test.sh 30 20 30

# Let camera cool for 10 minutes after
sleep 600
```

### Test 2: 15 FPS (Recommended)

```bash
# Change FPS
nano src/cotton_detection_ros2/config/cotton_detection_cpp.yaml
# Change to: camera_fps: 15

# Run test
./run_thermal_test.sh 15 20 30

# Cool down
sleep 600
```

### Test 3: 10 FPS (Hot Environments)

```bash
# Change FPS
nano src/cotton_detection_ros2/config/cotton_detection_cpp.yaml
# Change to: camera_fps: 10

# Run test
./run_thermal_test.sh 10 20 30
```

---

## 🎛️ Auto-Trigger Options

The auto-trigger script has flexible options:

```bash
# Trigger every 30 seconds indefinitely
./auto_trigger_detections.py

# Trigger every 60 seconds
./auto_trigger_detections.py -i 60

# Trigger exactly 20 times then stop
./auto_trigger_detections.py -c 20

# Trigger every 15 seconds, 40 times (10 minutes)
./auto_trigger_detections.py -i 15 -c 40

# Help
./auto_trigger_detections.py --help
```

---

## 📊 Temperature Status Guide

| Emoji | Status | Temp | Meaning |
|-------|--------|------|---------|
| ❄️ | COOL | <60°C | Just started, optimal |
| ✅ | NORMAL | 60-70°C | **Target for field deployment** |
| 🌡️ | WARM | 70-75°C | Acceptable, monitor |
| ⚠️ | WARNING | 75-80°C | **Current @ 30 FPS** - too hot |
| 🔥 | THROTTLING | 80-85°C | Performance degrading |
| 🔴 | CRITICAL | >85°C | Risk of shutdown |

---

## ✅ Success Criteria

A test is successful when:

1. **Temperature stabilizes** (stops climbing) within 10 minutes
2. **Stable temp is in NORMAL zone** (<70°C)
3. **All detection triggers succeed** (check auto-trigger stats)
4. **Performance is acceptable** (latency <50ms per trigger)

---

## 🎯 Quick Decision

After running tests at different FPS:

| Test Result | Decision |
|-------------|----------|
| Stable at <70°C | ✅ Use this FPS |
| Stable at 70-75°C | ⚠️ Marginal - consider lower |
| Stable at >75°C | ❌ Too hot - reduce FPS |
| Never stabilizes | 🔴 Critical - hardware issue |

---

## 🔧 Troubleshooting

### Script won't start

```bash
# Make sure scripts are executable
chmod +x *.py *.sh

# Check ROS2 environment
source install/setup.bash
```

### Camera not detected

```bash
# Check USB connection
lsusb | grep 03e7

# Test with Python
python3 -c "import depthai as dai; print(dai.Device().getMxId())"
```

### Auto-trigger fails

```bash
# Check service is available
ros2 service list | grep detect

# Test manual trigger
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```

---

## 📁 Output Files

After each test, you'll have:

1. **thermal_test_XXfps_TIMESTAMP.csv** - Temperature data
2. **ros2_node_TIMESTAMP.log** - ROS2 node output
3. **thermal_monitor_TIMESTAMP.log** - Monitor output

Keep these for comparison!

---

## 🎉 Next Steps

1. **Run test at 30 FPS** (20 min) → baseline
2. **Cool camera** (10 min wait)
3. **Run test at 15 FPS** (20 min) → recommended
4. **Compare CSV files**
5. **Choose optimal FPS** for your environment
6. **Update production config**

---

## Summary

✅ **One command**: `./run_thermal_test.sh 30 20 30`  
✅ **Fully automated**: No manual triggering needed  
✅ **Easy analysis**: CSV output for Excel  
✅ **Safe testing**: Auto-stops after duration  
✅ **Clear results**: Temperature zones with emojis

**Start your test now!** 🚀
