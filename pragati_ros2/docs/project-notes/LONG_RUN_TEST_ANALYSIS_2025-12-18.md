# Long-Run Test Analysis - 8 Hour Endurance Test
**Date:** 2025-12-18
**Test Duration:** 8.04 hours (planned: 10 hours)
**Test Type:** Simulated cotton positions without actual cotton (arm movement stress test)

## Executive Summary

Successfully ran arm for 8+ hours with **1400 cycles completed** and **0 motor failures**. Camera experienced USB communication issues requiring improved fault detection for production readiness.

### Key Results
| Metric | Value | Status |
|--------|-------|--------|
| Total Runtime | 8.04 hours | Good |
| Arm Cycles | 1400 | Excellent |
| Motor Health | 100% (0 failures) | Excellent |
| Cotton Picked (simulated) | 4908 positions | Good |
| Camera Uptime | ~93% (7.5h healthy) | Needs improvement |
| X_LINK_ERROR Recovery | 1/1 successful | Good |

---

## Test Configuration

```yaml
System:
  Camera: OAK-D Lite (USB 2.0 - suboptimal)
  USB Speed: 480 Mbps (USB 2.0)
  Model: yolov8v2.blob
  Resolution: 416x416 @ 30 FPS
  
Arm:
  continuous_operation: true
  simulation_mode: false
  end_effector_enable: true
  
Detection:
  fallback_positions: 4 (used when 0 cotton detected)
  confidence_threshold: 0.50
```

---

## Timeline of Events

| Time (hrs) | Event | Impact |
|------------|-------|--------|
| 0.00 | Test started | Camera connected at USB 2.0 |
| 2.91 | **X_LINK_ERROR** | USB communication failure |
| 2.91 + 10s | Recovery successful | Camera reconnected (attempt 1/3) |
| 7.29 | Last normal detection | detect=4ms |
| 7.30 | **Detection timeout starts** | detect=101ms (2 consecutive) |
| 7.51 | **RGB frame failure** | Camera stops providing frames |
| 8.04 | Manual stop (Ctrl+C) | All nodes shutdown cleanly |

---

## X_LINK_ERROR Analysis

### Occurrence Details
- **Total occurrences:** 8 error messages (all from single incident at 2.91 hours)
- **Streams affected:** detections, rgb
- **Recovery time:** ~10 seconds
- **Recovery attempts:** 1 (succeeded on first try)

### Recovery Log
```
[2.91h] X_LINK_ERROR detected - reconnection required
[2.91h] 🔄 Reconnection attempt 1/3...
[2.91h] Step 1/3: Shutting down existing connection...
[2.91h] Step 2/3: Waiting for USB re-enumeration (2 seconds)...
[2.91h] Step 3/3: Reinitializing device...
[2.91h] ✅ Reconnection successful!
[2.91h] Pipeline ready (flushed 2 frames)
```

**Conclusion:** Automatic recovery worked perfectly for X_LINK_ERROR. Camera resumed normal operation after reconnection.

---

## Second Failure Analysis (7.5 hours) - CRITICAL

### Why Recovery Didn't Trigger
The camera entered a **degraded state** where:
1. Detection queue still returned results (empty, but no error)
2. RGB frame queue stopped delivering frames (timeout, but no exception)
3. **No X_LINK_ERROR was thrown** - recovery logic never triggered
4. Health check reported "CONNECTED & HEALTHY" (false positive!)

### Gradual Degradation Evidence
```
Request #1227 (7:29:47): detect=4ms   ← Normal (frame ready)
Request #1228 (7:30:10): detect=101ms ← TIMEOUT - WARNING SIGN #1
Request #1229 (7:30:32): detect=100ms ← TIMEOUT - WARNING SIGN #2  
Request #1230 (7:30:55): detect=101ms, frame=101ms, save=0ms ← COMPLETE FAILURE
```

**Key Insight:** There were 2 consecutive detection timeouts (~20 seconds) before RGB frame failure. This pattern is detectable!

### Frame Count Analysis
```
Runtime 7:29:05 → Frames: 1229 (incrementing normally)
Runtime 7:30:05 → Frames: 1229 (STOPPED incrementing)
Runtime 8:02:05 → Frames: 1229 (never recovered)
```

---

## Timing & Queue Behavior Analysis

### Queue Configuration
```cpp
// From depthai_manager.cpp
detection_queue_ = device_->getOutputQueue("detections", 2, false);
rgb_queue_ = device_->getOutputQueue("rgb", 2, false);
// queue_size=2, blocking=false (non-blocking with drop policy)
```

### Timeout Settings
```cpp
// Default timeout: 1000ms (1 second)
// Polling interval: 2ms
// Actual observed timeout: ~101ms (custom implementation)
getDetections(std::chrono::milliseconds timeout = 1000);
getRGBFrame(std::chrono::milliseconds timeout = 1000);
```

### Timing Distribution (1400 requests)
| Detect Time | Count | Percentage | Notes |
|-------------|-------|------------|-------|
| 4-69ms | ~1100 | 78.6% | Normal operation |
| 70-99ms | ~166 | 11.9% | Slight delays |
| 100-102ms | 134 | 9.6% | Timeout (after 7.5hr) |

### Are We Getting Fresh Images?
**Yes, during normal operation:**
- Frame freshness mechanism flushes 2 stale frames per request
- Wait time averages 42ms (within 1 frame period at 30 FPS)
- Max wait time: 101ms (hits timeout only during degraded state)

### NN Queue Behavior
- **Input:** Non-blocking (`setBlocking(false)`, `setQueueSize(2)`)
- **Behavior:** Drops frames if processing is slow (good for real-time)
- **Performance:** Consistent ~33ms inference time when camera healthy

---

## Temperature Analysis

| Time Period | Temp Range | Status |
|-------------|------------|--------|
| 0-1 hour | 42.5-49.5°C | Normal |
| 1-3 hours | 49-54.6°C | Peak (before X_LINK) |
| 3-7 hours | 47-52°C | Stable after recovery |
| 7-8 hours | 48-51°C | Normal (not thermal issue) |

**Max Temperature:** 54.6°C (well below 70°C warning threshold)
**Conclusion:** Temperature was NOT a factor in either failure.

---

## Arm Performance Analysis

### Motor Health (Perfect!)
```
All joints throughout 8 hours:
- Health: 100%
- Failures: 0
- Temperature: 27-30°C
- Voltage: 55.3-55.6V stable
```

### Cycle Statistics
- **Total cycles:** 1400
- **Successful:** 1400 (100%)
- **With movement:** Depends on fallback positions
- **Average cycle time:** 20.6 seconds

---

## Recommended Improvements

### 1. CRITICAL: Partial Failure Detection (Cotton Detection Node)

**Problem:** Camera can enter degraded state without throwing X_LINK_ERROR

**Solution:** Add consecutive timeout detection
```cpp
// In cotton_detection_node_depthai.cpp
static int consecutive_frame_timeouts_ = 0;
const int MAX_CONSECUTIVE_TIMEOUTS = 3;

// After getRGBFrame returns empty:
if (frame.empty()) {
    consecutive_frame_timeouts_++;
    if (consecutive_frame_timeouts_ >= MAX_CONSECUTIVE_TIMEOUTS) {
        RCLCPP_ERROR(get_logger(), 
            "❌ Camera degraded - %d consecutive frame timeouts, forcing reconnection",
            consecutive_frame_timeouts_);
        needs_reconnection_ = true;  // Trigger recovery
    }
} else {
    consecutive_frame_timeouts_ = 0;  // Reset on success
}
```

**Priority:** HIGH - Must fix before field trial

### 2. Enhanced Health Check (Cotton Detection Node)

**Current issue:** Reports "CONNECTED & HEALTHY" even when frames stopped

**Solution:** Add frame delivery rate to health metrics
```cpp
// Track frame freshness
std::chrono::steady_clock::time_point last_successful_frame_time_;
int frames_in_last_minute_ = 0;

// In health check:
auto time_since_frame = now - last_successful_frame_time_;
if (time_since_frame > 30s) {
    camera_status = "⚠️ STALE (no frames for " + to_string(time_since_frame) + ")";
}

// In stats output:
RCLCPP_INFO(..., "📷 Camera: %s | Last frame: %ds ago", 
    camera_status, time_since_frame.count());
```

**Priority:** HIGH

### 3. Improved Stats Logging (Cotton Detection Node)

**Add to periodic stats:**
```cpp
// Current stats
"🌡️  Temp: 48.5°C | Frames: 1229"

// Enhanced stats
"🌡️  Temp: 48.5°C | Frames: 1229 (+5 in 30s) | Last: 2s ago"
"📊 Frame rate: 10/min | Timeouts: 0 | Recovery: 0"
"🔄 Queue: det=0/2, rgb=1/2 | Drops: 0"
```

**Priority:** MEDIUM

### 4. Watchdog Timer (System Level)

**Add to launch file or systemd:**
```python
# In launch file - restart camera node if no frames for 60s
watchdog_timer = Node(
    package='pragati_ros2',
    executable='camera_watchdog',
    parameters=[{
        'topic': '/cotton_detection/results',
        'timeout_sec': 60.0,
        'action': 'restart_node'
    }]
)
```

**Priority:** MEDIUM

### 5. Motor Control Node Logging Improvements

**Current:** Logs are good, but could add:
```cpp
// Add periodic summary
"📊 MOTOR SUMMARY (8h): cycles=1400, errors=0, avg_temp=28.5°C"
"⚡ Power: avg=55.4V, min=55.3V, max=55.6V"
"🎯 Position accuracy: 100% reached target"
```

**Priority:** LOW (motors performed perfectly)

### 6. Yanthra Move Node Improvements

**Add detection data freshness logging:**
```cpp
// Current
"⚠️  Timeout waiting for fresh detection data"

// Enhanced  
"⚠️  Timeout waiting for detection (waited 200ms, last data 45s ago)"
"📊 Detection data age: 0.5s (fresh) / 45s (stale)"
```

**Priority:** MEDIUM

---

## Hardware Recommendations

1. **USB 3.0 Required** - Currently running USB 2.0 (known issue, planned fix)
2. **Powered USB hub** - For stable power delivery during long runs
3. **Shorter USB cable** - <2m recommended for signal integrity
4. **Ferrite cores** - Add to USB cable for EMI reduction

---

## Action Items for Field Trial

### Must Fix (Before Trial)
- [ ] Implement consecutive timeout detection (triggers at 3 timeouts)
- [ ] Fix health check to detect stale frames
- [ ] Switch to USB 3.0 port

### Should Fix
- [ ] Enhanced stats logging with frame age
- [ ] Add queue depth to periodic stats
- [ ] Implement camera watchdog timer

### Nice to Have
- [ ] Motor summary logging
- [ ] Detection data age logging in yanthra_move

---

## Raw Log Files

Location: `/home/uday/Downloads/2025-12-18-09-03-56-102269-ubuntu-desktop-3541/`

| File | Size | Content |
|------|------|---------|
| cotton_detection_node_*.log | 3 MB | Camera/detection logs |
| yanthra_move_node_*.log | 40 MB | Arm movement logs |
| mg6010_controller_node_*.log | 6.6 MB | Motor control logs |
| launch.log | 1.6 KB | Launch events |

---

## Conclusion

This 8-hour test was extremely valuable:
1. **Arm reliability:** PROVEN - 1400 cycles, 0 failures
2. **Motor reliability:** PROVEN - 100% health throughout
3. **Camera X_LINK recovery:** PROVEN - Works correctly
4. **Camera partial failure:** DISCOVERED - New failure mode needs fix

The arm is production-ready. The camera integration needs the partial-failure detection fix before field deployment.
