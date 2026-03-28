# Test: On-Demand Low FPS Mode

## Changes Made

### 1. **Reduced FPS: 15 → 1 FPS** ⚡
- Camera now runs at **1 FPS** instead of 15 FPS
- **93% reduction** in continuous processing load
- Expected thermal improvement: **-20°C to -30°C**

### 2. **Thermal Protection** 🌡️
- **85°C Warning**: Adds 500ms cooldown delay
- **90°C Critical**: Refuses detection, sleeps 5 seconds
- Temperature logged on every detection call

### 3. **Clean Shutdown** ✅
- Added `shutdown_requested_` atomic flag
- Simplified shutdown sequence (no queue draining needed)
- Commented out log suppression (API compatibility)

### 4. **Stereo Depth: DEFAULT preset**
- Balanced performance vs thermal characteristics

---

## Test Plan

### Test 1: Quick Detection Test (2 minutes)
**Objective**: Verify detection still works at 1 FPS

```bash
# On RPi:
cd ~/pragati_ros2
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=false use_depthai:=true
```

**Expected behavior:**
- Pipeline initializes with "1 FPS (on-demand capture)"
- Detection requests complete in ~1000ms (vs previous ~125ms)
- Detections still found successfully
- Temperature starts at ~59°C

**Run for 2 minutes, then Ctrl+C**

### Test 2: Thermal Endurance Test (10 minutes)
**Objective**: Verify temperature stays low

```bash
# Same command, run for 10 minutes
```

**Monitor in log:**
- Temperature should stay < 75°C (vs previous 93.9°C)
- No "WARNING: Temperature" messages
- No "CRITICAL: Temperature" messages

**Success criteria:**
- Peak temp < 80°C (previous: 93.9°C)
- No thermal throttling

### Test 3: Shutdown Test
**Objective**: No USB errors on shutdown

```bash
# After 2-10 minutes, press Ctrl+C
```

**Expected output:**
```
[DepthAIManager] Shutting down...
[DepthAIManager] Closing device...
[DepthAIManager] Releasing resources...
[DepthAIManager] Shutdown complete
```

**Success criteria:**
- ✅ NO "Cannot find file descriptor by key" errors
- ✅ Clean exit

---

## Expected Results

| Metric | Before (15 FPS) | After (1 FPS) | Improvement |
|--------|----------------|---------------|-------------|
| **Idle Power** | 100% | ~7% | 93% reduction |
| **Peak Temp** | 93.9°C | <80°C | -14°C |
| **Detection Latency** | 125ms | ~1000ms | Slower |
| **Shutdown Errors** | YES | NO | Fixed |
| **Thermal Throttling** | Near limit | Safe margin | Safe |

---

## Trade-offs

### ✅ Pros:
1. **Massive thermal reduction**: -20°C to -30°C expected
2. **Clean shutdown**: No USB errors
3. **Production-safe**: Won't hit thermal limit in field
4. **Power efficient**: 93% less continuous processing

### ⚠️ Cons:
1. **Slower response**: ~1000ms vs 125ms per detection
   - **BUT**: For agricultural use case, this is acceptable
   - Cotton isn't moving, 1 second response is fine
   - Still faster than human reaction

---

## Quick Commands

### Start test on RPi:
```bash
ssh ubuntu@192.168.137.253
cd ~/pragati_ros2
source install/setup.bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py simulation_mode:=false use_depthai:=true
```

### Monitor from PC (optional):
```bash
ssh ubuntu@192.168.137.253 "journalctl -f | grep -E 'Temperature|DepthAIManager|cotton_detection'"
```

---

## Troubleshooting

### If detection fails:
- Check if camera is connected: `lsusb | grep Myriad`
- Check logs for initialization errors
- Verify model blob exists: `ls ~/pragati_ros2/install/cotton_detection_ros2/share/cotton_detection_ros2/models/`

### If temperature still high:
- Verify log says "1 FPS (on-demand capture)" not "15 FPS"
- Check if depth is enabled (adds heat)
- Consider adding physical heatsink

### If USB errors persist:
- Check DepthAI library version
- May need to add small delay before device.close()

---

## Next Steps After Testing

### If successful:
1. Document temperature curve over 1 hour
2. Test in hot environment (35°C ambient)
3. Commit changes with test results
4. Update production deployment guide

### If temperature still problematic:
1. Disable stereo depth when not needed
2. Add physical cooling (heatsink/fan)
3. Implement duty-cycle operation (detect 30s, sleep 5min)

---

**Ready to test!** 🚀
