# Shutdown Errors & Temperature Fix Plan

## Problem 1: Shutdown USB Errors ❌

### Root Cause
```
F: [global] [589702] [EventRead00Thr] usbPlatformRead:999
Cannot find file descriptor by key: 55
```

**What's Really Happening:**
1. When Ctrl+C is pressed, ROS2 starts immediate destruction
2. Destructor `~DepthAIManager()` calls `shutdown()`
3. BUT: `shutdown()` tries to acquire mutex lock
4. **Race condition**: If getDetections() is running, mutex is locked
5. Destructor proceeds to destroy device while threads are still active
6. USB reader threads crash looking for destroyed file descriptors

**Why It Matters:**
- Indicates improper thread cleanup
- Could cause memory leaks
- Could corrupt USB state requiring device reconnect
- Not production-safe

### Fix Strategy

#### Option A: Try-lock with timeout in destructor (RECOMMENDED)
```cpp
DepthAIManager::~DepthAIManager() {
    // Set shutdown flag first
    if (pImpl_) {
        pImpl_->shutdown_requested_.store(true);
    }
    
    // Try to acquire lock with timeout
    std::unique_lock<std::mutex> lock(pImpl_->mutex_, std::defer_lock);
    if (lock.try_lock_for(std::chrono::milliseconds(500))) {
        shutdownInternal();  // Does actual cleanup without lock
    } else {
        // Force shutdown if lock can't be acquired
        std::cerr << "[DepthAIManager] Force shutdown - couldn't acquire lock" << std::endl;
        forceShutdown();  // Aggressive cleanup
    }
}
```

#### Option B: Lower-level DepthAI logging suppression
```cpp
void DepthAIManager::shutdown() {
    // Suppress DepthAI internal logging before shutdown
    dai::setLogLevel(dai::LogLevel::OFF);
    
    // ... existing shutdown code ...
}
```

#### Option C: Atomic shutdown flag to stop threads first
```cpp
class Impl {
    std::atomic<bool> shutdown_requested_{false};
};

// In getDetections():
if (pImpl_->shutdown_requested_.load()) {
    return std::nullopt;  // Exit immediately
}
```

---

## Problem 2: Temperature Increase ⚠️

### The Data
```
Time (s)  | Temp (°C) | Rate
----------|-----------|------
0         | 59.1      | Baseline
167       | 80.4      | +0.13°C/s
300       | 85.4      | +0.09°C/s
460       | 92.0      | +0.07°C/s
657       | 93.9      | Plateau
```

**Analysis:**
- **59.1°C → 93.9°C** in 11 minutes (34.8°C increase)
- Rate decreases over time (thermal equilibrium)
- Peak: **93.9°C** sustained
- OAK-D Lite rated to **~95°C** junction temperature

### Why This IS a Problem for Production

#### 1. **Continuous Operation Risk**
- Your test: 11 minutes
- Production: Could be hours/days
- If temperature plateaus at 94°C, you're at thermal limit
- Any ambient temperature increase → thermal throttling

#### 2. **Thermal Throttling Effects**
- At 90°C+: Camera may reduce FPS (15 → 10 → 5 FPS)
- At 95°C+: Possible emergency shutdown
- Latency may increase
- Detection accuracy may degrade

#### 3. **Hardware Longevity**
- Running at 90°C+ continuously reduces MTBF
- Expected life: 100,000 hours @ 70°C vs 10,000 hours @ 90°C

#### 4. **Field Deployment Issues**
- If ambient temp is 35°C+ (agricultural field in summer)
- Device starts at 59°C + 35°C ambient = **94°C baseline**
- Immediate thermal throttling

### Root Causes

1. **Continuous Stereo Depth Processing**
   ```cpp
   stereo->setDefaultProfilePreset(dai::node::StereoDepth::PresetMode::HIGH_ACCURACY);
   ```
   - Stereo depth is computationally expensive
   - VPU running at 100% load
   - Generates most heat

2. **15 FPS Continuous Streaming**
   - Camera streams even when not detecting
   - 218 frames over 671s = continuous operation
   - No idle time for cooling

3. **No Thermal Management**
   - No active cooling
   - OAK-D Lite is fanless design
   - Relies on passive heatsink + airflow

### Solutions

#### Solution 1: Reduce Stereo Depth Quality (QUICK FIX)
```cpp
// Change from HIGH_ACCURACY to HIGH_DENSITY (lower power)
stereo->setDefaultProfilePreset(dai::node::StereoDepth::PresetMode::HIGH_DENSITY);

// Or reduce median filter (less compute)
stereo->setMedianFilter(dai::MedianFilter::KERNEL_5x5);  // Instead of 7x7
```
**Expected impact:** -5 to -10°C

#### Solution 2: Dynamic FPS Throttling (RECOMMENDED)
```cpp
// Only stream at 15 FPS during active detection
// Drop to 1 FPS idle monitoring

void setDetectionMode(bool active) {
    if (active) {
        camRgb->setFps(15);  // Full speed
    } else {
        camRgb->setFps(1);   // Idle - 93% duty cycle reduction
    }
}
```
**Expected impact:** -15 to -20°C at idle

#### Solution 3: Disable Depth When Not Needed
```cpp
// Only enable stereo depth during actual detection calls
// Keep RGB-only streaming for monitoring

bool needs_depth = (detection_mode == SPATIAL);
stereo->setOutputDepth(needs_depth);
```
**Expected impact:** -10 to -15°C

#### Solution 4: Hardware - Add Heatsink/Fan
- **Passive heatsink:** -5 to -10°C
- **5V mini fan:** -15 to -25°C
- **Required for 24/7 operation in hot climates**

#### Solution 5: Duty Cycle Operation
```python
# For agricultural use:
# - Detect for 30 seconds
# - Sleep for 5 minutes
# - Repeat

Duty cycle: 30s / 330s = 9% 
Thermal improvement: ~50% lower average temp
```

### Recommended Implementation Priority

#### Phase 1: Software Quick Wins (THIS WEEK)
```cpp
// 1. Lower stereo quality
stereo->setDefaultProfilePreset(dai::node::StereoDepth::PresetMode::HIGH_DENSITY);

// 2. Add temperature monitoring
float temp = device->getChipTemperature().average;
if (temp > 85.0) {
    RCLCPP_WARN(logger_, "High temperature: %.1f°C - reducing FPS", temp);
    camRgb->setFps(5);  // Throttle
}
```

#### Phase 2: Dynamic Power Management (NEXT SPRINT)
```cpp
class ThermalManager {
    void update() {
        float temp = getTemperature();
        
        if (temp > 90.0) {
            // Emergency: drop to minimum
            setFps(1);
            disableDepth();
        } else if (temp > 85.0) {
            // Warning: reduce load
            setFps(5);
        } else if (temp < 75.0) {
            // Normal: full speed
            setFps(15);
        }
    }
};
```

#### Phase 3: Hardware Solution (FOR PRODUCTION)
- Add aluminum heatsink to OAK-D Lite
- Consider 5V fan for enclosed deployments
- Cost: $5-10 per unit

---

## Implementation Plan

### Step 1: Fix Shutdown (1 hour)
1. Add atomic shutdown flag
2. Add try-lock with timeout to destructor
3. Suppress DepthAI logging on shutdown
4. Test: No more USB errors on Ctrl+C

### Step 2: Add Thermal Monitoring (2 hours)
1. Add temperature reading to status updates
2. Log temperature warnings
3. Add thermal state to performance reports
4. Test: Verify temperature tracking

### Step 3: Implement Thermal Throttling (3 hours)
1. Add ThermalManager class
2. Reduce stereo quality preset
3. Dynamic FPS based on temperature
4. Test: Verify max temp stays < 85°C

### Step 4: Production Validation (1 day)
1. 4-hour endurance test
2. Test in 35°C ambient environment
3. Measure steady-state temperature
4. Validate no thermal throttling occurs

---

## Expected Results

### Before (Current):
- Shutdown: ❌ USB errors flood console
- Temperature: ⚠️ 93.9°C peak (thermal limit)
- Production ready: ❌ NO

### After (With Fixes):
- Shutdown: ✅ Clean exit, no errors
- Temperature: ✅ <80°C steady state
- Production ready: ✅ YES

---

## Test Validation Criteria

### Shutdown Test
```bash
# Run for 5 minutes, then Ctrl+C
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py

# Expected output:
[DepthAIManager] Shutting down...
[DepthAIManager] Draining queues...
[DepthAIManager] Closing device connection...
[DepthAIManager] Releasing queues...
[DepthAIManager] Shutdown complete

# ✅ NO "Cannot find file descriptor" errors
```

### Thermal Test
```bash
# Run for 1 hour with continuous detection
# Monitor temperature every minute

Expected max temperature: <80°C
Expected steady-state: 75-78°C
No thermal throttling warnings
```

---

## Conclusion

Both issues are **production blockers** that need fixing:

1. **Shutdown errors**: Indicates thread safety issues - MUST FIX
2. **Temperature**: 93.9°C is too close to thermal limit - MUST OPTIMIZE

**Estimated effort:** 1-2 days to implement all fixes
**Risk if not fixed:** System failures in production deployment

**Priority: HIGH** 🔴
