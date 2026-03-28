# Phase 2 Roadmap: Production-Ready System

**Part of:** [Pragati Production System Documentation](../README.md)

**Status:** In Development  
**Target:** Production Readiness

---

## 🎯 Overview

Phase 2 transforms the Pragati system from a proof-of-concept stop-and-go operation into a production-ready continuous picking system.

## 🚧 Current State (Phase 1)

⚠️ **NOT Production Ready**

- **Operation Mode:** Stop-and-Go (vehicle stops before picking)
- **Camera Mode:** On-demand triggered capture
- **Vehicle Control:** Manual control only
- **Throughput:** ~200-300 picks/hour
- **Issues:**
  - Low throughput (vehicle spends time stopped)
  - Delayed detection (trigger → capture → process)
  - Manual operation (operator fatigue)

## 🎯 Target State (Phase 2)

✅ **Production Ready**

- **Operation Mode:** Continuous motion (pick while moving)
- **Camera Mode:** Continuous streaming at 30 Hz
- **Vehicle Control:** Autonomous with manual override
- **Throughput:** ~1,800-2,000 picks/hour (8-10× improvement)
- **Benefits:**
  - No stopped time
  - Real-time detection
  - Temporal filtering for quality
  - Autonomous operation

---

## 📋 Critical Changes Required

### 1. Camera System: Triggered → Continuous Streaming

**Priority:** HIGH  
**Effort:** Medium (2-3 weeks)  
**Impact:** Enables continuous detection

**Changes:**
- Set `trigger_mode: "continuous"` in config
- Implement temporal filtering (multi-frame detection)
- Handle higher CPU load (4 cameras × 30 Hz)
- Optimize MQTT message rate

**Files:**
- `config/cotton_detection.yaml`
- `src/cotton_detection_ros2/src/cotton_detection_node.cpp`

---

### 2. Vehicle Control: Manual → Autonomous

**Priority:** HIGH  
**Effort:** High (3-4 weeks)  
**Impact:** Enables hands-free operation

**Changes:**
- Implement GPS waypoint navigation
- Implement row detection (vision or GPS-based)
- Add manual override mechanism (joystick priority)
- Implement velocity planning for smooth motion
- Field testing and tuning

**Files:**
- `src/vehicle_control/src/vehicle_controller.cpp` (new implementation)
- `config/vehicle_control.yaml`

---

### 3. Picking Workflow: Sequential → Predictive

**Priority:** HIGH  
**Effort:** Medium (2-3 weeks)  
**Impact:** Required for picking while moving

**Changes:**
- Implement position prediction algorithm
- Calibrate arm delay timing (~1.5s)
- Handle vehicle acceleration (not just constant velocity)
- Test prediction accuracy

**Implementation:**
```cpp
// Predict where cotton will be when arm reaches it
Point3D predicted_position;
predicted_position.x = cotton_pos.x + vehicle_vel.x * arm_delay;
predicted_position.y = cotton_pos.y + vehicle_vel.y * arm_delay;
predicted_position.z = cotton_pos.z;  // Height unchanged
```

---

## 🗓️ Implementation Timeline

### Week 1-2: Continuous Camera Streaming
- [ ] Update configuration files
- [ ] Test 4 cameras streaming simultaneously
- [ ] Implement temporal filtering
- [ ] Monitor CPU usage (target: <70%)
- [ ] Optimize MQTT publishing rate

### Week 3-6: Autonomous Vehicle Navigation
- [ ] Design waypoint navigation system
- [ ] Implement row detection algorithm
- [ ] Add manual override capability
- [ ] Integrate with vehicle control
- [ ] Field testing (critical!)

### Week 7-8: Predictive Picking
- [ ] Implement prediction algorithm
- [ ] Calibrate timing parameters
- [ ] Test accuracy while moving
- [ ] Tune for different speeds

### Week 9-11: Integration & Testing
- [ ] Integrate all Phase 2 components
- [ ] Full-day field testing
- [ ] Measure throughput and quality
- [ ] Iterate based on results
- [ ] Performance validation

### Week 12: Production Validation
- [ ] Final system validation
- [ ] Documentation updates
- [ ] Operator training
- [ ] Production deployment

---

## 📊 Success Criteria

### Performance Targets

| Metric | Phase 1 (Current) | Phase 2 (Target) |
|--------|-------------------|------------------|
| Operation Mode | Stop-and-go | Continuous |
| Picks per Hour | 200-300 | 1,800-2,000 |
| Detection Rate | On-demand | 30 Hz continuous |
| Vehicle Control | Manual | Autonomous |
| Operator Load | High (constant) | Low (monitoring) |

### Quality Targets

- **Detection accuracy:** >95% (currently ~90%)
- **False positives:** <3% (currently ~5%)
- **Missed cotton:** <5% (currently ~10%)
- **Successful picks:** >90% (currently ~85%)

---

## ⚠️ Risks & Mitigation

### Risk 1: Continuous Streaming Performance
**Impact:** High  
**Mitigation:** 
- Incremental testing (1 camera → 4 cameras)
- CPU profiling and optimization
- Reduce resolution if needed (416x416 is already optimized)

### Risk 2: Autonomous Navigation Safety
**Impact:** Critical  
**Mitigation:**
- Always maintain manual override
- Implement robust obstacle detection
- Start with low speeds (0.2 m/s)
- Extensive field testing before production

### Risk 3: Predictive Accuracy
**Impact:** Medium  
**Mitigation:**
- Calibrate with actual field data
- Add sensor fusion (IMU for acceleration)
- Implement adaptive prediction (learn from misses)

---

## 📚 Related Documentation

- [System Overview](../production-system/01-SYSTEM_OVERVIEW.md)
- [Production Readiness Status](../PRODUCTION_READINESS_GAP.md)
- [Consolidated Roadmap](../CONSOLIDATED_ROADMAP.md)

<!-- Phase 2 detailed docs (to be created):
- Multi-Cotton Detection (planned)
- Continuous Operation (planned)
- Autonomous Navigation (planned)
-->

---

**Timeline:** ~12 weeks  
**Status:** Planning/Early Development  
**Next Milestone:** Continuous camera streaming (Week 1-2)
