# Logging & Reliability Enhancements Plan
**Date:** 2025-12-18
**Based on:** 8-hour endurance test analysis
**Target:** Field trial readiness

## Code Review Findings

### Current Implementation Gaps (Verified from Source)

1. **`isHealthy()` always returns `true`** (depthai_manager.cpp:358)
   ```cpp
   bool DepthAIManager::isHealthy() const {
       // For now, assume healthy if initialized and device object exists
       return true;  // <-- PROBLEM: Never checks frame delivery!
   }
   ```

2. **Reconnection only triggers on X_LINK_ERROR exception**
   - `needs_reconnect_` flag set only in catch blocks
   - `getRGBFrame()` returning empty Mat (timeout) does NOT set flag
   - This is why 7.5hr failure wasn't detected

3. **No consecutive timeout tracking**
   - Existing: `frame_wait_total_ms_`, `frame_wait_count_`, `frame_wait_max_ms_`
   - Missing: `consecutive_frame_timeouts_` counter

4. **Missing from stats (stats_log_callback)**
   - Last successful frame timestamp
   - Frame rate (new frames per period)
   - Consecutive timeout count
   - Reconnection count

### What's Already Good
- Frame wait avg/max tracking exists
- Temperature monitoring works
- X_LINK_ERROR reconnection with exponential backoff (when triggered)
- USB speed warning at startup

## Priority Matrix

| Priority | Enhancement | Node | Effort | Impact |
|----------|-------------|------|--------|--------|
| P0-CRITICAL | Consecutive timeout detection | cotton_detection | 2h | Prevents silent failure |
| P0-CRITICAL | Fix isHealthy() to check frame delivery | depthai_manager | 1h | Accurate health status |
| P1-HIGH | Last frame timestamp tracking | cotton_detection | 1h | Early warning |
| P1-HIGH | Add setNeedsReconnection() method | depthai_manager | 30m | Enable external trigger |
| P2-MEDIUM | Detection data age | yanthra_move | 1h | Better diagnostics |
| P2-MEDIUM | Camera watchdog | new node/launch | 2h | Auto-recovery |
| P3-LOW | Motor summary stats | motor_control | 1h | Nice to have |

---

## P0-CRITICAL: Consecutive Timeout Detection

### Problem
Camera can stop delivering frames without throwing X_LINK_ERROR. Current recovery only triggers on X_LINK_ERROR.

### Root Cause (from logs)
```
Request #1228: detect=101ms  ← Timeout warning #1
Request #1229: detect=100ms  ← Timeout warning #2
Request #1230: RGB frame timeout → Complete failure (never recovered)
```

### Implementation

**File 1:** `src/cotton_detection_ros2/include/cotton_detection_ros2/cotton_detection_node.hpp`

```cpp
// Add to private members (around line 200):
    // Frame timeout tracking for degradation detection
    std::atomic<int> consecutive_frame_timeouts_{0};
    static constexpr int MAX_CONSECUTIVE_TIMEOUTS = 3;
    std::chrono::steady_clock::time_point last_successful_frame_time_{std::chrono::steady_clock::now()};
    std::atomic<uint64_t> total_reconnects_{0};
```

**File 2:** `src/cotton_detection_ros2/src/cotton_detection_node_services.cpp`

In `process_detection_request()`, after the RGB frame save attempt (around line 180):

```cpp
// After: cv::Mat frame = depthai_manager_->getRGBFrame(std::chrono::milliseconds(100));

if (frame.empty()) {
    int timeouts = consecutive_frame_timeouts_.fetch_add(1) + 1;
    auto time_since_success = std::chrono::duration_cast<std::chrono::seconds>(
        std::chrono::steady_clock::now() - last_successful_frame_time_
    ).count();
    
    RCLCPP_WARN(this->get_logger(), 
        "⚠️ Frame timeout %d/%d (last success: %lds ago)",
        timeouts, MAX_CONSECUTIVE_TIMEOUTS, time_since_success);
    
    if (timeouts >= MAX_CONSECUTIVE_TIMEOUTS) {
        RCLCPP_ERROR(this->get_logger(), 
            "❌ Camera degraded - %d consecutive frame timeouts, forcing reconnection",
            timeouts);
        
        // Force reconnection by setting the flag directly on Impl
        // Need to add setNeedsReconnection() method - see File 3
        depthai_manager_->forceReconnection();
        consecutive_frame_timeouts_.store(0);
    }
} else {
    // Success - reset counter and update timestamp
    if (consecutive_frame_timeouts_.load() > 0) {
        RCLCPP_INFO(this->get_logger(), "✅ Frame received - resetting timeout counter");
    }
    consecutive_frame_timeouts_.store(0);
    last_successful_frame_time_ = std::chrono::steady_clock::now();
}
```

**File 3:** `src/cotton_detection_ros2/src/depthai_manager.cpp`

Add new method (after `clearReconnectFlag()`):

```cpp
void DepthAIManager::forceReconnection() {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    pImpl_->needs_reconnect_ = true;
    pImpl_->log(LogLevel::WARN, "🔄 Reconnection forced due to consecutive frame timeouts");
}
```

**File 4:** `src/cotton_detection_ros2/include/cotton_detection_ros2/depthai_manager.hpp`

Add declaration (around line 180):

```cpp
    /**
     * @brief Force reconnection (for external timeout detection)
     * 
     * Use when consecutive frame timeouts indicate degraded camera state
     * even without X_LINK_ERROR exception.
     */
    void forceReconnection();
```

### Testing
```bash
# Simulate by disconnecting USB briefly during run
# Verify reconnection triggers after 3 failed frame requests
# Check logs for: "Camera degraded - forcing reconnection"
```

---

## P0-CRITICAL: Frame Staleness Health Check

### Problem
Health check reports "CONNECTED & HEALTHY" even when no frames received for minutes.

### Implementation

**File:** `src/cotton_detection_ros2/src/cotton_detection_node_lifecycle.cpp`

```cpp
// Modify getCameraHealthStatus() or add new method:

std::string getCameraHealthStatus() const {
    if (!depthai_manager_ || !depthai_manager_->isInitialized()) {
        return "❌ NOT INITIALIZED";
    }
    
    // Check frame freshness
    auto now = std::chrono::steady_clock::now();
    auto time_since_frame = std::chrono::duration_cast<std::chrono::seconds>(
        now - last_successful_frame_time_
    ).count();
    
    if (time_since_frame > 60) {
        return "❌ DEAD (no frames for " + std::to_string(time_since_frame) + "s)";
    } else if (time_since_frame > 30) {
        return "⚠️ STALE (last frame " + std::to_string(time_since_frame) + "s ago)";
    } else if (consecutive_frame_timeouts_ > 0) {
        return "⚠️ DEGRADED (" + std::to_string(consecutive_frame_timeouts_) + " timeouts)";
    } else {
        return "✅ CONNECTED & HEALTHY";
    }
}

// Update stats logging to use new method:
RCLCPP_INFO(this->get_logger(), "📷 Camera: %s", getCameraHealthStatus().c_str());
```

---

## P1-HIGH: Enhanced Stats Logging

### Current Output
```
📷 Camera: ✅ CONNECTED & HEALTHY
🌡️  Temp: 48.5°C | Frames: 1229
🔍 Requests: 1229 | Success: 1228 | WithCotton: 0 (0.0%)
⏱️  Latency: avg=47.7ms, min=11.5ms, max=110.2ms
📷 Frame wait: avg=42ms, max=101ms (n=1230)
💾 Memory: 243 MB
```

### Enhanced Output
```
📷 Camera: ✅ HEALTHY | Last frame: 2s ago | Rate: 10/min
🌡️  Temp: 48.5°C | Frames: 1229 (+5 in 30s)
🔍 Requests: 1229 | Success: 1228 | Timeouts: 0 | WithCotton: 0 (0.0%)
⏱️  Latency: avg=47.7ms, min=11.5ms, max=110.2ms
📷 Frame wait: avg=42ms, max=101ms (n=1230) | Stale flushed: avg=2
🔄 Queue: det=0/2, rgb=1/2, depth=0/2 | Drops: 0
💾 Memory: 243 MB | Reconnects: 0
```

### Implementation

**File:** `src/cotton_detection_ros2/src/cotton_detection_node_lifecycle.cpp`

```cpp
// Add tracking members
int frames_in_period_{0};
int timeouts_in_period_{0};
int total_reconnects_{0};
std::chrono::steady_clock::time_point period_start_;

// In logPeriodicStats():
void logPeriodicStats() {
    auto now = std::chrono::steady_clock::now();
    auto period_duration = std::chrono::duration_cast<std::chrono::seconds>(
        now - period_start_
    ).count();
    
    auto time_since_frame = std::chrono::duration_cast<std::chrono::seconds>(
        now - last_successful_frame_time_
    ).count();
    
    float frame_rate = (period_duration > 0) ? 
        (frames_in_period_ * 60.0f / period_duration) : 0;
    
    RCLCPP_INFO(this->get_logger(), 
        "📷 Camera: %s | Last frame: %lds ago | Rate: %.0f/min",
        getCameraHealthStatus().c_str(),
        time_since_frame,
        frame_rate);
    
    RCLCPP_INFO(this->get_logger(),
        "🌡️  Temp: %.1f°C | Frames: %d (+%d in %lds)",
        getTemperature(),
        total_frames_,
        frames_in_period_,
        period_duration);
    
    RCLCPP_INFO(this->get_logger(),
        "🔍 Requests: %d | Success: %d | Timeouts: %d | WithCotton: %.1f%%",
        total_requests_,
        successful_requests_,
        timeouts_in_period_,
        cotton_detection_rate_ * 100);
    
    RCLCPP_INFO(this->get_logger(),
        "🔄 Reconnects: %d | Consecutive timeouts: %d/%d",
        total_reconnects_,
        consecutive_frame_timeouts_,
        MAX_CONSECUTIVE_TIMEOUTS);
    
    // Reset period counters
    frames_in_period_ = 0;
    timeouts_in_period_ = 0;
    period_start_ = now;
}
```

---

## P2-MEDIUM: Yanthra Move Detection Data Age

### Current Issue
```
⚠️  Timeout waiting for fresh detection data
```
Doesn't indicate how old the last data was or how long it waited.

### Enhanced Output
```
⚠️  Timeout waiting for detection (waited 200ms, last data 45s old)
📊 Detection subscription: last_msg=45s ago, total=1229, rate=2.5/min
```

### Implementation

**File:** `src/yanthra_move/src/yanthra_move_system_core.cpp`

```cpp
// Add tracking
std::chrono::steady_clock::time_point last_detection_msg_time_;
int detection_msgs_received_{0};

// In detection callback:
void cottonDetectionCallback(const CottonDetectionResult::SharedPtr msg) {
    last_detection_msg_time_ = std::chrono::steady_clock::now();
    detection_msgs_received_++;
    // ... existing code
}

// In waitForDetection or similar:
auto time_since_detection = std::chrono::duration_cast<std::chrono::milliseconds>(
    std::chrono::steady_clock::now() - last_detection_msg_time_
).count();

if (timeout_reached) {
    RCLCPP_WARN(this->get_logger(),
        "⚠️  Timeout waiting for detection (waited %dms, last data %ldms old)",
        wait_time_ms,
        time_since_detection);
}

// In periodic stats:
RCLCPP_INFO(this->get_logger(),
    "📊 Detection sub: last_msg=%lds ago, total=%d",
    time_since_detection / 1000,
    detection_msgs_received_);
```

---

## P2-MEDIUM: Camera Watchdog (New)

### Concept
System-level watchdog that monitors camera output and triggers restart if stale.

### Option A: Launch File Timer

```python
# In launch/pragati_bringup.launch.py
from launch.actions import TimerAction, ExecuteProcess

def generate_launch_description():
    # ... existing nodes ...
    
    camera_watchdog = TimerAction(
        period=60.0,  # Check every 60 seconds
        actions=[
            ExecuteProcess(
                cmd=['ros2', 'topic', 'echo', '/cotton_detection/results', 
                     '--once', '--timeout', '5'],
                on_exit=[
                    # If timeout (exit code != 0), restart camera node
                    LogInfo(msg='Camera watchdog: checking health...'),
                ]
            )
        ]
    )
```

### Option B: Dedicated Watchdog Node

```python
# scripts/camera_watchdog.py
import rclpy
from rclpy.node import Node
from cotton_detection_ros2.msg import CottonDetectionResult
import subprocess

class CameraWatchdog(Node):
    def __init__(self):
        super().__init__('camera_watchdog')
        self.last_msg_time = self.get_clock().now()
        self.timeout_sec = 60.0
        
        self.subscription = self.create_subscription(
            CottonDetectionResult,
            '/cotton_detection/results',
            self.detection_callback,
            10)
        
        self.timer = self.create_timer(10.0, self.check_health)
    
    def detection_callback(self, msg):
        self.last_msg_time = self.get_clock().now()
    
    def check_health(self):
        elapsed = (self.get_clock().now() - self.last_msg_time).nanoseconds / 1e9
        if elapsed > self.timeout_sec:
            self.get_logger().error(
                f'Camera stale for {elapsed:.0f}s - restarting node')
            subprocess.run(['ros2', 'lifecycle', 'set', 
                          'cotton_detection_node', 'shutdown'])
            subprocess.run(['ros2', 'lifecycle', 'set', 
                          'cotton_detection_node', 'configure'])
            subprocess.run(['ros2', 'lifecycle', 'set', 
                          'cotton_detection_node', 'activate'])
```

---

## P3-LOW: Motor Control Summary

### Enhancement
Add periodic high-level summary (every 30 minutes or on shutdown):

```cpp
void logMotorSummary() {
    RCLCPP_INFO(this->get_logger(),
        "═══════════════════════════════════════════════════════");
    RCLCPP_INFO(this->get_logger(),
        "📊 MOTOR CONTROL SUMMARY (uptime: %s)", formatUptime().c_str());
    RCLCPP_INFO(this->get_logger(),
        "═══════════════════════════════════════════════════════");
    
    for (const auto& [name, motor] : motors_) {
        RCLCPP_INFO(this->get_logger(),
            "  %s: health=%.0f%% | temp_avg=%.1f°C | cmds=%d | errors=%d",
            name.c_str(),
            motor.health_percent,
            motor.avg_temperature,
            motor.total_commands,
            motor.error_count);
    }
    
    RCLCPP_INFO(this->get_logger(),
        "  ⚡ Power: avg=%.1fV | min=%.1fV | max=%.1fV",
        avg_voltage_, min_voltage_, max_voltage_);
}
```

---

## Implementation Checklist

### Phase 1: Critical (Before Field Trial)
- [ ] Add consecutive_frame_timeouts_ counter
- [ ] Implement forced reconnection on 3 consecutive timeouts
- [ ] Update getCameraHealthStatus() with frame age check
- [ ] Test with USB disconnect simulation

### Phase 2: High Priority (Field Trial Ready)
- [ ] Add frames_in_period_ tracking
- [ ] Add timeouts_in_period_ tracking
- [ ] Update logPeriodicStats() with enhanced format
- [ ] Test stats output format

### Phase 3: Medium Priority (Post Field Trial)
- [ ] Add detection age tracking to yanthra_move
- [ ] Implement camera watchdog node
- [ ] Add to launch file

### Phase 4: Low Priority (Nice to Have)
- [ ] Add motor summary logging
- [ ] Add shutdown summary for all nodes

---

## Testing Commands

```bash
# Test camera health reporting
ros2 topic echo /cotton_detection/results --once

# Monitor stats
ros2 topic echo /cotton_detection/stats

# Simulate camera failure (disconnect USB)
# Verify reconnection triggers and stats update correctly

# Check watchdog
ros2 run pragati_ros2 camera_watchdog
```

---

## Notes

- All changes should maintain backward compatibility
- Stats format changes should be documented in CHANGELOG
- Consider adding Prometheus/Grafana metrics for long-term monitoring
- USB 3.0 migration is hardware priority alongside these software changes
