# Thermal Testing Guide - OAK-D Lite Camera

## Overview

This guide shows how to run long-term thermal tests with automatic logging to compare different FPS settings and find the optimal configuration for field deployment.

---

## Test Script: `monitor_camera_thermal.py`

**Purpose**: Continuously monitor and log camera temperature to CSV for analysis

**Features**:
- ✅ Logs temperature every 5 seconds (configurable)
- ✅ CSV output for Excel/analysis
- ✅ Real-time console display with status indicators
- ✅ Graceful shutdown with Ctrl+C
- ✅ Logs all temperature zones (CSS, MSS, UPA, DSS)

---

## Running Tests on Raspberry Pi

### Test 1: Current Settings (30 FPS with HIGH_ACCURACY)

```bash
ssh ubuntu@192.168.137.253
cd /home/ubuntu/pragati_ros2

# Terminal 1: Start thermal monitor
./monitor_camera_thermal.py -i 10 -o test1_30fps_high_accuracy.csv

# Wait for camera to connect, then in Terminal 2 (new SSH session):
# Launch ROS2 node
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Let it run for 15-20 minutes
# Monitor console output for temperature trend
# Press Ctrl+C in Terminal 1 when done

# Result will be saved to: test1_30fps_high_accuracy.csv
```

### Test 2: Reduced FPS (15 FPS with HIGH_ACCURACY)

```bash
# Stop ROS2 node from Test 1
pkill -f cotton_detection_node

# Let camera cool for 10 minutes
sleep 600

# Edit config to use 15 FPS
nano src/cotton_detection_ros2/config/cotton_detection_cpp.yaml
# Change: camera_fps: 15

# Terminal 1: Start new thermal monitor
./monitor_camera_thermal.py -i 10 -o test2_15fps_high_accuracy.csv

# Terminal 2: Launch ROS2 node
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Let it run for 15-20 minutes
# Press Ctrl+C when done
```

### Test 3: Lower FPS (10 FPS with HIGH_ACCURACY)

```bash
# Stop and cool
pkill -f cotton_detection_node
sleep 600

# Edit config to use 10 FPS
nano src/cotton_detection_ros2/config/cotton_detection_cpp.yaml
# Change: camera_fps: 10

# Monitor and launch
./monitor_camera_thermal.py -i 10 -o test3_10fps_high_accuracy.csv

# In another terminal:
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Run for 15-20 minutes
```

---

## Monitoring Script Options

```bash
# Basic usage (default: 5 second interval)
./monitor_camera_thermal.py

# Custom interval (e.g., every 10 seconds)
./monitor_camera_thermal.py -i 10

# Custom output file
./monitor_camera_thermal.py -o my_test.csv

# Both
./monitor_camera_thermal.py -i 10 -o thermal_test_30fps.csv
```

---

## What You'll See

### Console Output

```
======================================================================
  🌡️  OAK-D Lite Camera Thermal Monitor
======================================================================
  📊 Interval: 10 seconds
  📝 Log file: test1_30fps_high_accuracy.csv
  ⏸️  Press Ctrl+C to stop
======================================================================

📷 Connecting to camera...
✅ Connected to: 18443010513F671200
   USB: 3.0 (5Gbps)
📝 Logging to: test1_30fps_high_accuracy.csv

📊 Temperature Readings:

   Timestamp          | Time  | Average  | CSS     | MSS     | Status
----------------------------------------------------------------------
❄️  2025-10-31 18:20:00 |     0s | Avg:  45.2°C | CSS:  44.8°C | MSS:  45.6°C | COOL
✅ 2025-10-31 18:20:10 |    10s | Avg:  52.3°C | CSS:  51.9°C | MSS:  52.7°C | COOL
✅ 2025-10-31 18:20:20 |    20s | Avg:  58.7°C | CSS:  58.2°C | MSS:  59.1°C | COOL
✅ 2025-10-31 18:20:30 |    30s | Avg:  64.5°C | CSS:  64.0°C | MSS:  64.9°C | NORMAL
🌡️  2025-10-31 18:20:40 |    40s | Avg:  69.1°C | CSS:  68.6°C | MSS:  69.5°C | NORMAL
🌡️  2025-10-31 18:20:50 |    50s | Avg:  72.8°C | CSS:  72.3°C | MSS:  73.2°C | WARM
⚠️  2025-10-31 18:21:00 |    60s | Avg:  75.4°C | CSS:  74.9°C | MSS:  75.8°C | WARNING
⚠️  2025-10-31 18:21:10 |    70s | Avg:  77.2°C | CSS:  76.7°C | MSS:  77.6°C | WARNING
🔥 2025-10-31 18:21:20 |    80s | Avg:  78.9°C | CSS:  78.4°C | MSS:  79.3°C | WARNING
...
```

### CSV Output

The CSV file will contain:

```csv
Timestamp,Elapsed_Seconds,Average_Temp_C,CSS_Temp_C,MSS_Temp_C,UPA_Temp_C,DSS_Temp_C,Status
2025-10-31 18:20:00,0,45.2,44.8,45.6,45.0,45.3,COOL
2025-10-31 18:20:10,10,52.3,51.9,52.7,52.1,52.5,COOL
2025-10-31 18:20:20,20,58.7,58.2,59.1,58.5,58.9,COOL
2025-10-31 18:20:30,30,64.5,64.0,64.9,64.3,64.7,NORMAL
...
```

---

## Temperature Status Zones

| Status | Temperature | Emoji | Meaning |
|--------|-------------|-------|---------|
| **COOL** | <60°C | ❄️ | Optimal, just started |
| **NORMAL** | 60-70°C | ✅ | Good for continuous operation |
| **WARM** | 70-75°C | 🌡️ | Acceptable, monitor |
| **WARNING** | 75-80°C | ⚠️ | Close to throttling |
| **THROTTLING** | 80-85°C | 🔥 | Performance degrading |
| **CRITICAL** | >85°C | 🔴 | Risk of shutdown |

---

## Analyzing Results

### 1. Download CSV Files from RPi

```bash
# On your PC:
scp ubuntu@192.168.137.253:/home/ubuntu/pragati_ros2/test*.csv ~/Downloads/
```

### 2. Open in Excel/LibreOffice

- Create line chart with time on X-axis, temperature on Y-axis
- Compare different FPS settings
- Look for stabilization point

### 3. Key Metrics to Compare

| Metric | Target |
|--------|--------|
| **Stabilized Temp** | <70°C (NORMAL zone) |
| **Time to Stabilize** | <10 minutes |
| **Peak Temp** | <75°C |
| **Average Temp** | 65-70°C |

### 4. Expected Results

| FPS | Expected Stable Temp | Status | Recommendation |
|-----|---------------------|--------|----------------|
| 30 | 76-78°C | ⚠️ WARNING | Too hot for continuous outdoor use |
| 20 | 70-72°C | 🌡️ WARM | Acceptable with good ventilation |
| 15 | 65-68°C | ✅ NORMAL | **Recommended for field deployment** |
| 10 | 60-65°C | ✅ NORMAL | Best for hot environments |

---

## Quick Comparison Script

After collecting all test logs, you can compare them:

```python
# compare_thermal_tests.py
import pandas as pd
import matplotlib.pyplot as plt

# Load all test results
test1 = pd.read_csv('test1_30fps_high_accuracy.csv')
test2 = pd.read_csv('test2_15fps_high_accuracy.csv')
test3 = pd.read_csv('test3_10fps_high_accuracy.csv')

# Plot comparison
plt.figure(figsize=(12, 6))
plt.plot(test1['Elapsed_Seconds'], test1['Average_Temp_C'], label='30 FPS', linewidth=2)
plt.plot(test2['Elapsed_Seconds'], test2['Average_Temp_C'], label='15 FPS', linewidth=2)
plt.plot(test3['Elapsed_Seconds'], test3['Average_Temp_C'], label='10 FPS', linewidth=2)

# Add temperature zones
plt.axhline(y=70, color='green', linestyle='--', alpha=0.5, label='Normal limit')
plt.axhline(y=75, color='orange', linestyle='--', alpha=0.5, label='Warm limit')
plt.axhline(y=80, color='red', linestyle='--', alpha=0.5, label='Throttling starts')

plt.xlabel('Time (seconds)')
plt.ylabel('Temperature (°C)')
plt.title('OAK-D Lite Thermal Comparison: FPS Settings')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('thermal_comparison.png', dpi=150)
print("✅ Comparison chart saved: thermal_comparison.png")
```

---

## Recommendation Process

### Step 1: Run All Tests

Run tests at 30, 20, 15, and 10 FPS for 15-20 minutes each.

### Step 2: Analyze Stabilization

Find the temperature where it stabilizes (stops climbing significantly).

### Step 3: Choose FPS

Select the **highest FPS** that keeps temperature in **NORMAL zone** (<70°C).

### Step 4: Verify Detection Performance

Ensure detection accuracy and latency are acceptable at chosen FPS.

### Example Decision Matrix:

```
Test Results:
- 30 FPS → 78°C (WARNING) → ❌ Too hot
- 20 FPS → 72°C (WARM) → ⚠️ Marginal
- 15 FPS → 68°C (NORMAL) → ✅ GOOD
- 10 FPS → 63°C (NORMAL) → ✅ GOOD (overkill)

Decision: Use 15 FPS for optimal balance
- Fast enough for responsive detection
- Cool enough for continuous outdoor operation
- Provides thermal headroom for hot days
```

---

## Field Deployment Settings

Based on test results, create production config:

```yaml
# Recommended for hot outdoor environment
depthai:
  camera_fps: 15  # Balanced: performance + thermal
  enable_depth: true  # Required for 3D positions
  
# Disable image saving for production
save_input_image: false
save_output_image: false
```

---

## Continuous Monitoring in Production

For field deployment, consider periodic thermal checks:

```python
# Add to your ROS2 node or create separate monitor node
import rclpy
from rclpy.node import Node

class ThermalGuard(Node):
    def __init__(self):
        super().__init__('thermal_guard')
        self.timer = self.create_timer(60.0, self.check_temperature)  # Every 60s
        
    def check_temperature(self):
        temp = self.get_camera_temp()
        if temp > 80:
            self.get_logger().warn(f'🔥 Camera hot: {temp}°C - reducing FPS')
            # Automatically reduce FPS or pause detection
        elif temp < 65:
            self.get_logger().info(f'❄️ Camera cool: {temp}°C - can increase FPS')
```

---

## Summary

✅ **Use `monitor_camera_thermal.py` for long-term testing**  
✅ **Run 15-20 minute tests at different FPS settings**  
✅ **Compare CSV logs to find optimal FPS**  
✅ **Target: <70°C stable temperature**  
✅ **Recommended for field: 15 FPS**

**Files**:
- `monitor_camera_thermal.py` - Monitoring script
- `test*.csv` - Test results
- `THERMAL_TESTING_GUIDE.md` - This guide

**Next**: Run the tests and share the CSV results for analysis!
