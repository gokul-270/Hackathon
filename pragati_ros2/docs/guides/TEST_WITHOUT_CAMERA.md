# Testing Complete System Without Camera

> **📍 MOVED:** This content has been consolidated into the comprehensive testing guide.  
> **New Location:** [TESTING_AND_OFFLINE_OPERATION.md](TESTING_AND_OFFLINE_OPERATION.md)  
> **Date:** 2025-11-04  
> **Reason:** Consolidated with offline testing and simulation guides for better organization

**Quick Links:**
- [Complete Testing Guide](TESTING_AND_OFFLINE_OPERATION.md)
- [Part 2: Complete System Simulation](TESTING_AND_OFFLINE_OPERATION.md#part-2-complete-system-simulation)

---

## Legacy Content (For Reference)

## Overview
This guide shows how to test the complete Pragati picking system without a physical camera using simulated cotton detections.

## Correct Flow

```
1. Start fake cotton detection publisher (keeps publishing continuously)
   ↓
2. Launch main system (yanthra_move)
   ↓
3. System initializes and waits for START_SWITCH
   ↓
4. Send START_SWITCH signal
   ↓
5. System reads cotton detections from fake publisher
   ↓
6. System performs picking operation
   ↓
7. System returns to waiting for START_SWITCH (loop continues)
```

## Prerequisites

```bash
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash
```

## Step-by-Step Procedure

### Terminal 1: Start Fake Cotton Detection Publisher

```bash
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash
python3 publish_fake_cotton.py
```

**Expected output:**
```
============================================================
Fake Cotton Detection Publisher
============================================================

This will continuously publish fake cotton detections
at position (0.3, 0.0, 0.5) meters

Flow:
  1. This script publishes detections continuously
  2. Launch main system in another terminal
  3. System waits for start switch
  4. Send start switch signal
  5. System reads these detections and picks cotton

============================================================

[INFO] [fake_cotton_publisher]: Fake cotton detection publisher started
[INFO] [fake_cotton_publisher]: Publishing to: /cotton_detection/results at 1 Hz
[INFO] [fake_cotton_publisher]: Press Ctrl+C to stop
[INFO] [fake_cotton_publisher]: Published cotton at (0.30, 0.00, 0.50)
```

**Leave this running!** It will continuously publish detections at 1 Hz.

### Terminal 2: Launch Main System

```bash
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash
ros2 launch yanthra_move pragati_complete.launch.py
```

**Wait for initialization** (about 15-20 seconds). Look for:
```
[INFO] [yanthra_move]: ⏳ Waiting for START_SWITCH signal to begin cotton detection process...
[INFO] [yanthra_move]: ⏳ Waiting infinitely for START_SWITCH (timeout disabled with -1)
```

### Terminal 3: Send Start Switch Signal

Once you see the system waiting for START_SWITCH:

```bash
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash
ros2 topic pub --once /start_switch/command std_msgs/msg/Bool "{data: true}"
```

**Expected behavior:**
1. System receives START_SWITCH signal
2. System reads cotton detection from Terminal 1's publisher
3. System performs picking operation:
   - Calculates trajectory
   - Moves arm to cotton position
   - Picks cotton
   - Returns to parking position
4. System completes cycle and waits for START_SWITCH again

### To Trigger Another Cycle

Just send the START_SWITCH signal again:
```bash
ros2 topic pub --once /start_switch/command std_msgs/msg/Bool "{data: true}"
```

### To Stop

**Terminal 1:** Press `Ctrl+C` to stop fake cotton publisher

**Terminal 2:** Press `Ctrl+C` to stop main system, OR run emergency stop:
```bash
./emergency_motor_stop.sh
```

## Verification

### Check cotton detections are being published:
```bash
ros2 topic echo /cotton_detection/results
```

Should show continuous detections at 1 Hz.

### Check system is waiting for start switch:
```bash
ros2 topic list | grep start_switch
```

Should show:
- `/start_switch/command`
- `/start_switch/state`

### Monitor system operation:
Watch the logs in Terminal 2 for:
- ✅ Cotton detection received
- ✅ Motion planning
- ✅ Arm movement commands
- ✅ Cycle completion
- ✅ Return to waiting for START_SWITCH

## Current Configuration

From `src/yanthra_move/config/production.yaml`:
- `continuous_operation: true` - Keeps running, waits for start switch after each cycle
- `start_switch.enable_wait: true` - Waits for start switch before each cycle
- `start_switch.timeout_sec: -1.0` - Infinite wait (no timeout)
- `start_switch.prefer_topic: true` - Uses topic for start switch
- `simulation_mode: true` - No real hardware needed

## Troubleshooting

### No detections received by yanthra_move?
- Check Terminal 1 is still running
- Verify topic: `ros2 topic list | grep cotton_detection`
- Echo the topic: `ros2 topic echo /cotton_detection/results`

### System doesn't respond to start switch?
- Check config: `start_switch.enable_wait: true`
- Verify topic exists: `ros2 topic list | grep start_switch`
- Check logs in Terminal 2 for "Waiting for START_SWITCH"

### Motors moving in simulation?
- This is normal - simulation mode sends commands but doesn't require hardware
- Check logs for motion commands being issued
- On real hardware, motors would actually move

### Want to change cotton position?
Edit `publish_fake_cotton.py` line 44-46:
```python
cotton.position.x = 0.3  # forward distance (meters)
cotton.position.y = 0.0  # sideways offset (meters)  
cotton.position.z = 0.5  # height (meters)
```

## Summary

**Correct flow:**
1. Fake publisher runs continuously (Terminal 1)
2. Main system launches and waits (Terminal 2)
3. You trigger with start switch (Terminal 3)
4. System picks using detections from fake publisher
5. System returns to waiting
6. Repeat from step 3

**Key point:** The fake cotton publisher must be running BEFORE or ALONGSIDE the main system, not after the start switch.
