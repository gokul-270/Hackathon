# Cotton Detection Implementation Roadmap
**Version**: 1.0  
**Date**: 2025-11-05  
**Status**: Planning - No Code Changes Yet  
**Related**: `COTTON_PICKING_POSITION_ACCURACY_REQUIREMENTS.md`

---

## ⚠️ CRITICAL: Current System Status

**YOUR WORKING CODE IS SAFE**  
- ✅ All documentation only - no code modifications
- ✅ Tomorrow's tests will use existing stable code
- ✅ Implementation phases start AFTER validation
- ✅ Every change will be feature-flagged (can disable instantly)

---

## Phase 0: Baseline & Measurement (This Week - Documentation Only)

**Goal**: Understand current performance without changing anything

### Tasks (Documentation/Measurement Only):
1. ✅ **Requirements documented** (DONE)
2. ⏱️ **Run timing measurements** (your action)
   ```bash
   # Use the script created earlier
   ./scripts/testing/measure_pick_timing.sh
   ```
3. 📊 **Collect field images** (your action)
   - 20+ images with labels: sun/shade, green/dried, wet/dry, time
   - Store in `data/field_tests/2025-11-05/`
4. 🌡️ **Verify temperature logging**
   ```bash
   ros2 run cotton_detection_ros2 cotton_detection_node \
     --ros-args -p performance.verbose_timing:=true \
     | grep -i temperature
   ```
5. 📐 **Measure position accuracy** (ArUco markers)
   - Use existing ArUco test mode
   - Measure actual vs expected positions
   - Determine ±cm tolerance needed

**Deliverables**:
- [ ] Timing breakdown spreadsheet
- [ ] Field image dataset with metadata
- [ ] Temperature log analysis
- [ ] Position accuracy baseline report
- [ ] Current system capabilities summary

**Duration**: 2-3 days (your availability)  
**Risk**: ZERO (no code changes)

---

## Phase 1: Environmental Robustness (Week 2-3)

**Goal**: Handle sun, heat, merged detections WITHOUT breaking existing functionality

### 1.1 Code Structure (Backward Compatible)

**New Files** (none - modify existing only):
- Modify: `src/cotton_detection_ros2/src/depthai_manager.cpp`
- Modify: `src/cotton_detection_ros2/include/cotton_detection_ros2/depthai_manager.hpp`
- Modify: `src/cotton_detection_ros2/config/cotton_detection_cpp.yaml`

**New Parameters** (all default to current behavior):
```yaml
# Add to cotton_detection_cpp.yaml
depthai:
  # Thermal Management (disabled by default)
  thermal_management:
    enable: false  # ⚠️ MUST BE FALSE initially
    check_period_sec: 2.0
    hysteresis_degC: 1.0
    thresholds: [70.0, 75.0, 80.0]  # Normal, Warm, Hot, Critical
    fps_levels: [30, 20, 15, 10]
  
  # Exposure Adaptation (disabled by default)
  exposure_control:
    enable: false  # ⚠️ MUST BE FALSE initially
    glare_detection: false
    saturation_threshold: 0.30
    target_mean_luma: 0.35
    min_exposure_us: 1000
    max_exposure_us: 30000
    min_iso: 100
    max_iso: 800
  
  # Detection Filtering (disabled by default)
  detection_filter:
    enable: false  # ⚠️ MUST BE FALSE initially
    min_3d_separation_m: 0.05
    bbox_min_area_px: 200
    bbox_aspect_range: [0.5, 2.0]
    depth_consistency_sigma_m: 0.02
```

### 1.2 Implementation Strategy

**Step 1: Add Logging Only** (1 day)
```cpp
// In depthai_manager.cpp
// ONLY ADD LOGS - NO BEHAVIOR CHANGES

// Log temperature every 2 seconds
void DepthAIManager::Impl::logThermalMetrics() {
    if (!thermal_logging_enabled_) return;  // Feature flag
    
    auto temp = getTemperature();  // Existing function
    RCLCPP_INFO(get_logger(), 
        "[THERMAL] Temperature: %.1f°C, FPS: %d (no throttling active)", 
        temp, current_fps_);
}

// Log lighting metrics every 5 seconds
void DepthAIManager::Impl::logLightingMetrics() {
    if (!exposure_logging_enabled_) return;  // Feature flag
    
    // Compute histogram on last frame (cheap operation)
    auto hist = computeHistogram(last_frame_);  // New helper
    float saturation_ratio = hist.bright_pixels / hist.total_pixels;
    float mean_luma = hist.mean_value / 255.0f;
    
    RCLCPP_INFO(get_logger(),
        "[LIGHTING] Saturation: %.2f, Mean Luma: %.2f (no adaptation active)",
        saturation_ratio, mean_luma);
}

// Log detection quality every detection
void DepthAIManager::Impl::logDetectionQuality(const std::vector<Detection>& dets) {
    if (!detection_logging_enabled_) return;  // Feature flag
    
    int too_close_count = countMergedDetections(dets);  // New helper
    int bad_bbox_count = countInvalidBBoxes(dets);      // New helper
    
    RCLCPP_INFO(get_logger(),
        "[DETECTION] Total: %zu, MergedPairs: %d, BadBBox: %d (no filtering active)",
        dets.size(), too_close_count, bad_bbox_count);
}
```

**Step 2: Add Feature-Flagged Logic** (2-3 days)
```cpp
// ONLY EXECUTE IF FEATURE ENABLED

void DepthAIManager::Impl::thermalCheck() {
    if (!thermal_management_enabled_) return;  // ⚠️ SAFETY: Disabled by default
    
    float temp = getTemperature();
    int target_fps = selectFPSBand(temp);  // New helper
    
    if (target_fps != current_fps_) {
        RCLCPP_WARN(get_logger(), 
            "[THERMAL] Temperature %.1f°C → Throttling FPS %d → %d",
            temp, current_fps_, target_fps);
        
        // Send control message to camera
        dai::CameraControl ctrl;
        ctrl.setFrameRate(target_fps);
        sendCameraControl(ctrl);  // New helper
        
        current_fps_ = target_fps;
    }
}
```

### 1.3 Testing Procedure

**Before Field Deployment**:
1. **Compile with features DISABLED** (default)
   ```bash
   colcon build --packages-select cotton_detection_ros2
   ```
2. **Verify existing tests pass**
   ```bash
   colcon test --packages-select cotton_detection_ros2
   ```
3. **Run existing system for 1 hour** (smoke test)
   - Verify no regressions
   - Check log output looks normal
   - Confirm detection still works

**Enable ONE Feature at a Time**:
```bash
# Test thermal management only
ros2 param set /cotton_detection_node depthai.thermal_management.enable true

# Monitor for 30 minutes
ros2 topic echo /diagnostics | grep -i thermal

# If stable, enable next feature
ros2 param set /cotton_detection_node depthai.exposure_control.enable true
```

**Rollback Procedure** (if anything breaks):
```bash
# Instant disable via parameter
ros2 param set /cotton_detection_node depthai.thermal_management.enable false
ros2 param set /cotton_detection_node depthai.exposure_control.enable false
ros2 param set /cotton_detection_node depthai.detection_filter.enable false

# Or restart with defaults
ros2 service call /cotton_detection_node/reset_parameters std_srvs/srv/Trigger
```

---

## Phase 2: Position Accuracy (Week 4-5)

**After Phase 1 is stable in field**

### 2.1 Staleness Check
```yaml
operations:
  enable_staleness_check: false  # Default OFF
  max_detection_age_ms: 1000
  redetect_before_grasp_ms: 200
```

### 2.2 TF Transformation
```yaml
transforms:
  enable_tf_transform: false  # Default OFF
  source_frame: "camera_link"
  target_frame: "base_link"
```

### 2.3 FoV-Aware Detection
```yaml
operations:
  pause_during_pick: false  # Default OFF
  detect_only_at_home: false  # Default OFF
```

**Same Testing Strategy**: Feature flags, one at a time, with rollback

---

## Phase 3: Mobile Operation (Month 3-5)

**Far Future - Separate Planning Session**

---

## Risk Mitigation

### Critical Safeguards

1. **All Features Disabled by Default**
   ```yaml
   # In cotton_detection_cpp.yaml
   # EVERY new feature has enable: false
   ```

2. **Runtime Parameter Control**
   ```bash
   # Can enable/disable without restart
   ros2 param set /node feature.enable true/false
   ```

3. **Logging Before Action**
   ```cpp
   // Always log BEFORE changing behavior
   RCLCPP_INFO("About to do X...");
   doX();
   RCLCPP_INFO("X completed successfully");
   ```

4. **Graceful Degradation**
   ```cpp
   try {
       newFeature();
   } catch (const std::exception& e) {
       RCLCPP_ERROR("Feature failed: %s - DISABLING", e.what());
       feature_enabled_ = false;  // Auto-disable on error
       return useOldBehavior();   // Fallback
   }
   ```

5. **Version Tagging**
   ```bash
   # Before starting Phase 1
   git tag v1.0-stable-baseline
   git push origin v1.0-stable-baseline
   
   # Work on feature branch
   git checkout -b feature/thermal-management
   ```

---

## Development Workflow

### For Each Feature:

1. **Branch**
   ```bash
   git checkout -b feature/name-of-feature
   ```

2. **Implement with Feature Flag**
   - Add parameters with `enable: false`
   - Add logging
   - Add actual logic behind flag
   - Add tests

3. **Test in Isolation**
   ```bash
   # Build
   colcon build --packages-select cotton_detection_ros2
   
   # Test with feature DISABLED (should be identical to before)
   ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
   
   # Test with feature ENABLED
   ros2 param set /node feature.enable true
   ```

4. **Code Review**
   - Review changes
   - Verify feature flag works
   - Confirm defaults preserve old behavior

5. **Merge to Main**
   ```bash
   git checkout main
   git merge feature/name-of-feature
   git tag v1.1-with-thermal-management
   ```

6. **Deploy to Test System**
   - Deploy with features DISABLED
   - Run for 24 hours
   - Enable one feature
   - Monitor for issues

7. **Deploy to Production**
   - Only after field testing passes
   - Keep features DISABLED initially
   - Enable gradually over days

---

## Timeline

```
Week 1 (Current):
├─ Requirements documented ✅
├─ TODO list created ✅
├─ Roadmap created ✅
└─ YOUR TESTS (using current code) ⏳

Week 2:
├─ Baseline measurements
├─ Field image collection
└─ Position accuracy baseline

Week 3:
├─ Phase 1: Logging only (feature flags OFF)
├─ Compile & test
└─ Verify no regressions

Week 4:
├─ Phase 1: Enable thermal management (field test)
├─ Phase 1: Enable exposure control (field test)
└─ Phase 1: Enable detection filtering (field test)

Week 5:
├─ Phase 1 validation
├─ Tune thresholds
└─ Production deployment (features OFF initially)

Week 6-7:
├─ Phase 2 planning
├─ Phase 2: Staleness check
└─ Phase 2: TF transformation

Month 3-5:
└─ Phase 3: Mobile operation (separate plan)
```

---

## Emergency Procedures

### If Tomorrow's Tests Fail

**NOT RELATED TO THIS PLANNING** (we made no code changes)

But for future reference:

### If New Features Cause Issues

1. **Instant Disable**
   ```bash
   ros2 param set /node depthai.thermal_management.enable false
   ros2 param set /node depthai.exposure_control.enable false
   ros2 param set /node depthai.detection_filter.enable false
   ```

2. **Revert to Baseline**
   ```bash
   git checkout v1.0-stable-baseline
   colcon build --packages-select cotton_detection_ros2
   ```

3. **Log Analysis**
   ```bash
   # Find what went wrong
   grep -i error ~/.ros/log/latest/*.log
   grep -i "THERMAL\|EXPOSURE\|FILTER" ~/.ros/log/latest/*.log
   ```

---

## Success Criteria

### Phase 0 (Measurement):
- [ ] Timing data collected
- [ ] Field images labeled
- [ ] Temperature baseline established
- [ ] Position accuracy measured

### Phase 1 (Environmental Robustness):
- [ ] Features compile with defaults (OFF)
- [ ] Existing tests pass
- [ ] No regressions in field for 24h (features OFF)
- [ ] Each feature tested individually
- [ ] All features work together
- [ ] Field validation: morning, noon, evening
- [ ] No thermal shutdowns
- [ ] Glare handled gracefully
- [ ] Fewer merged detections

### Phase 2 (Position Accuracy):
- [ ] Position staleness < 1 second
- [ ] TF transformation working
- [ ] Pick success rate > 85%
- [ ] FoV-aware detection reduces occlusion

---

## Contact & Support

**If You Need Help During Tests**:
- Document has all context
- TODO list has step-by-step tasks
- No code changes made yet (system safe)

**Before Making Changes**:
- Review this roadmap
- Start with Phase 0 (measurement)
- Never skip feature flags
- Always test disabled state first

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-05  
**Next Review**: After Phase 0 measurements complete

---

**REMEMBER**: Your working code is unchanged. Tomorrow's tests use current stable system. All improvements are planned, documented, and feature-flagged for safe deployment.
