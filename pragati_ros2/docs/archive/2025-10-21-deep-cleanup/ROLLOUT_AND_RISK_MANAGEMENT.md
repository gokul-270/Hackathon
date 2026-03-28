> **Archived:** 2025-10-21
> **Reason:** Premature Phase 2 planning

# Rollout Strategy and Risk Management

**Project**: Pragati Cotton Picking Robot - OAK-D Lite Migration  
**Phase**: Phase 1 Deployment  
**Risk Level**: LOW (proven code reuse + comprehensive testing)  
**Date**: October 2025

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Deployment Strategy](#deployment-strategy)
3. [Risk Assessment](#risk-assessment)
4. [Fallback Procedures](#fallback-procedures)
5. [Compatibility Matrix](#compatibility-matrix)
6. [Recovery Procedures](#recovery-procedures)
7. [Monitoring and Validation](#monitoring-and-validation)

---

## Executive Summary

### Deployment Readiness

**Current Status**: ✅ **Phase 1 Complete - Ready for Hardware Deployment**

| Component | Status | Risk Level |
|-----------|--------|------------|
| **Build System** | ✅ Complete | 🟢 LOW |
| **ROS2 Integration** | ✅ Complete | 🟢 LOW |
| **ROS1 Scripts** | ✅ Verified (38/38) | 🟢 LOW |
| **Documentation** | ✅ Comprehensive | 🟢 LOW |
| **Testing Plan** | ✅ Documented | 🟢 LOW |
| **Hardware Validation** | ⏳ Pending Camera | 🟡 MEDIUM |

### Overall Risk Assessment

**Risk Level**: 🟢 **LOW**

**Rationale**:
- Reuses proven ROS1 detection code (zero modifications)
- All ROS2 improvements preserved
- Comprehensive testing plan in place
- Multiple fallback options available
- Clear rollback procedure defined

---

## Deployment Strategy

### Phase 1: Staged Rollout

#### Stage 1: Benchtop Testing (Duration: 1-2 days) ⏳

**Objective**: Validate hardware integration in controlled environment

**Steps**:
1. Connect OAK-D Lite camera
2. Run hardware detection tests (Test 1.1-1.4 from TESTING_AND_VALIDATION_PLAN.md)
3. Verify USB2 stability with 5m cable
4. Measure detection accuracy with test targets
5. Record baseline performance metrics

**Success Criteria**:
- Camera detected and initialized
- Detection accuracy within ±5cm
- USB2 mode stable (99% success rate)
- No USB errors in 100-iteration test

**Go/No-Go Decision**: 
- ✅ **GO**: Proceed to Stage 2
- ❌ **NO-GO**: Debug issues, re-test Stage 1

---

#### Stage 2: Robot Integration (Duration: 2-3 days) ⏳

**Objective**: Integrate with full robot stack

**Steps**:
1. Mount camera on robot arm
2. Calibrate camera TF transforms
3. Test with arm control (yanthra_move)
4. Validate end-to-end detection → motion workflow
5. Test with actual cotton targets

**Success Criteria**:
- TF frames correct
- Detection triggers arm motion
- Spatial coordinates accurate in robot frame
- Full workflow completes successfully

**Go/No-Go Decision**:
- ✅ **GO**: Proceed to Stage 3
- ❌ **NO-GO**: Debug integration, re-test Stage 2

---

#### Stage 3: Field Trial (Duration: 1 week) ⏳

**Objective**: Validate in production environment

**Steps**:
1. Deploy robot to cotton field (controlled area)
2. Run supervised cotton picking trials
3. Monitor system stability over multiple hours
4. Collect performance data
5. Compare with ROS1 baseline (if available)

**Success Criteria**:
- Multi-hour stability (>99% uptime)
- Detection accuracy meets requirements
- Cotton picking success rate acceptable
- No critical issues observed

**Go/No-Go Decision**:
- ✅ **GO**: Approve for production deployment
- ❌ **NO-GO**: Address issues, extend field trial

---

#### Stage 4: Production Deployment (Duration: Ongoing) ⏳

**Objective**: Full production rollout

**Steps**:
1. Deploy to all robots (if multiple)
2. Establish monitoring and maintenance schedule
3. Collect long-term performance data
4. Iterate on Phase 2 enhancements

**Success Criteria**:
- System meets all production requirements
- Stakeholders satisfied with performance
- Maintenance schedule established

---

## Risk Assessment

### Technical Risks

#### Risk 1: Hardware Compatibility

**Risk**: OAK-D Lite camera not compatible with ROS2 Jazzy environment

**Likelihood**: 🟢 **LOW** (DepthAI SDK 3.0.0 explicitly supports Python 3.10+)

**Impact**: 🔴 **HIGH** (Blocks Phase 1 entirely)

**Mitigation**:
- DepthAI 3.0.0 installed in Python venv
- Ubuntu 24.04 + Python 3.10 tested
- ROS1 system proves hardware works

**Fallback**: Use ROS1 system temporarily while debugging

**Status**: ⏳ Awaiting hardware confirmation

---

#### Risk 2: USB2 Bandwidth Insufficient

**Risk**: USB2 mode cannot support required resolution/frame rate

**Likelihood**: 🟢 **LOW** (ROS1 system proves USB2 works)

**Impact**: 🟡 **MEDIUM** (May need USB3 mode or resolution adjustment)

**Mitigation**:
- ROS1 used USB2 successfully
- Testing plan includes USB2 validation
- USB3 mode available as fallback

**Fallback**: Switch to USB3 mode with shorter cables

**Status**: ⏳ Awaiting hardware validation

---

#### Risk 3: Detection Accuracy Degradation

**Risk**: ROS2 wrapper introduces errors in coordinate transformation

**Likelihood**: 🟢 **LOW** (Wrapper only parses text file, no coordinate math)

**Impact**: 🔴 **HIGH** (Affects cotton picking success)

**Mitigation**:
- Wrapper uses simple text parsing
- No coordinate transformations in wrapper
- Testing plan includes accuracy validation

**Fallback**: Debug coordinate parsing, compare with ROS1 output

**Status**: ⏳ Awaiting hardware validation

---

#### Risk 4: ROS2 Service Timeout

**Risk**: Wrapper service times out before detection completes

**Likelihood**: 🟡 **MEDIUM** (File-based communication adds latency)

**Impact**: 🟡 **MEDIUM** (Detection fails, must retry)

**Mitigation**:
- Timeout set to 10 seconds (generous)
- CottonDetect.py typically completes in <2 seconds
- Timeout configurable via parameter

**Fallback**: Increase timeout parameter, optimize CottonDetect.py

**Status**: Awaiting hardware measurement

---

### Operational Risks

#### Risk 5: USB Cable Disconnection in Field

**Risk**: Long USB cable disconnects due to robot motion

**Likelihood**: 🟡 **MEDIUM** (Depends on cable routing and quality)

**Impact**: 🔴 **HIGH** (Detection fails, requires manual intervention)

**Mitigation**:
- USB2 mode more stable than USB3
- Use high-quality, flexible cable
- Proper cable routing and strain relief
- Testing includes cable movement tests

**Fallback**: Use shorter cable with USB extension, or relocate computer closer

**Status**: Requires field testing

---

#### Risk 6: DepthAI Pipeline Crash

**Risk**: CottonDetect.py crashes, hangs, or produces errors

**Likelihood**: 🟢 **LOW** (ROS1 system proves stability)

**Impact**: 🔴 **HIGH** (Detection unavailable until restart)

**Mitigation**:
- Using unmodified ROS1 code (proven stable)
- Wrapper includes error handling
- Automatic retry on failure

**Fallback**: Restart wrapper node (auto-restarts CottonDetect.py)

**Status**: Monitoring required during deployment

---

#### Risk 7: Performance Degradation Over Time

**Risk**: System slows down after extended operation

**Likelihood**: 🟡 **MEDIUM** (Memory leaks, resource exhaustion possible)

**Impact**: 🟡 **MEDIUM** (Reduced efficiency, may need restart)

**Mitigation**:
- Multi-hour stability testing planned
- Memory monitoring in testing plan
- Graceful restart procedure available

**Fallback**: Scheduled restarts (e.g., every 8 hours)

**Status**: Requires multi-hour testing

---

### Integration Risks

#### Risk 8: ROS2 Message Compatibility

**Risk**: vision_msgs format incompatible with downstream nodes

**Likelihood**: 🟢 **LOW** (Standard ROS2 message type)

**Impact**: 🟡 **MEDIUM** (May need message conversion)

**Mitigation**:
- Using standard vision_msgs/Detection3DArray
- Legacy service maintains ROS1 format
- Testing plan includes integration tests

**Fallback**: Create message converter node

**Status**: Requires integration testing

---

#### Risk 9: TF Frame Mismatch

**Risk**: Camera frames don't match robot URDF expectations

**Likelihood**: 🟡 **MEDIUM** (URDF migration may have errors)

**Impact**: 🔴 **HIGH** (Coordinate transforms incorrect)

**Mitigation**:
- URDF updated for OAK-D Lite
- Frame naming follows REP-103
- Testing plan includes TF validation

**Fallback**: Manual TF calibration, URDF corrections

**Status**: Requires URDF integration testing

---

## Fallback Procedures

### Fallback Level 1: Parameter Tuning (Immediate)

**When to Use**: Minor performance issues, configuration tweaks

**Procedure**:
```bash
# Adjust confidence threshold
ros2 param set /cotton_detect_ros2_wrapper confidence_threshold 0.6

# Increase timeout
ros2 param set /cotton_detect_ros2_wrapper detection_timeout 15.0

# Switch to USB3 mode
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py usb_mode:=usb3
```

**Impact**: Low - Minimal changes, no restart required

---

### Fallback Level 2: Node Restart (Quick)

**When to Use**: Wrapper node errors, pipeline hangs, temporary failures

**Procedure**:
```bash
# Kill wrapper node
ros2 node list | grep cotton_detect
ros2 lifecycle set /cotton_detect_ros2_wrapper shutdown

# Restart wrapper
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py
```

**Impact**: Medium - Brief downtime (~10 seconds), loses in-flight detections

---

### Fallback Level 3: Alternative Blob (Medium)

**When to Use**: YOLO model issues, accuracy problems

**Procedure**:
```bash
# Switch to alternative YOLO blob
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py \
    blob_path:=yolov8.blob

# Or use optimized blob
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py \
    blob_path:=best_openvino_2022.1_6shave.blob
```

**Impact**: Medium - Different accuracy/performance characteristics

---

### Fallback Level 4: System Rebuild (Slow)

**When to Use**: Corrupted installation, dependency issues

**Procedure**:
```bash
cd /home/uday/Downloads/pragati_ros2

# Clean rebuild
rm -rf build install log
colcon build

# Reinstall dependencies if needed
source venv/bin/activate
pip install --upgrade depthai
```

**Impact**: High - Significant downtime (~5-10 minutes)

---

### Fallback Level 5: ROS1 System (Emergency)

**When to Use**: Critical Phase 1 failure, production deadline

**Procedure**:
```bash
# Switch to ROS1 workspace
cd /home/uday/Downloads/pragati
source devel/setup.bash

# Launch ROS1 cotton detection
roslaunch cotton_detect cotton_detect.launch
```

**Impact**: Very High - Loses all ROS2 improvements, requires system reconfiguration

**Note**: ROS1 system remains available as safety net

---

## Compatibility Matrix

### ROS2 Jazzy Compatibility ✅

| Component | Version | Status | Notes |
|-----------|---------|--------|-------|
| **Ubuntu** | 24.04 LTS | ✅ Supported | Jazzy's target platform |
| **Python** | 3.10+ | ✅ Supported | System Python 3.12 |
| **DepthAI** | 3.0.0 | ✅ Supported | In venv, compatible with Python 3.10+ |
| **OpenCV** | 4.x | ✅ Supported | ROS2 Jazzy includes compatible version |
| **vision_msgs** | Jazzy | ✅ Supported | Standard ROS2 package |

---

### Hardware Compatibility ✅

| Hardware | Model | Status | Notes |
|----------|-------|--------|-------|
| **Camera** | OAK-D Lite (DM9095) | ✅ Supported | DepthAI SDK 3.0.0 compatible |
| **USB Mode** | USB 2.0 | ✅ Supported | 480 Mbps, 5m max cable |
| **USB Mode** | USB 3.0 | ✅ Supported | 5 Gbps, 3m max cable (fallback) |
| **Host Computer** | x86_64 | ✅ Supported | Ubuntu 24.04 compatible |
| **Host Computer** | ARM64 | ✅ Supported | DepthAI supports ARM (if needed) |

---

### Software Compatibility ✅

| Software | ROS1 | ROS2 Phase 1 | ROS2 Phase 2 (Future) |
|----------|------|--------------|----------------------|
| **Detection Code** | Python (OakDTools) | Python (same code) | Python (enhanced) or C++ |
| **ROS Interface** | Signal-based | Service-based | Service + topics |
| **Communication** | File I/O | File I/O | Direct pipeline |
| **Messages** | None | vision_msgs | vision_msgs + camera_info |
| **Parameters** | Hardcoded | ROS2 parameters | ROS2 parameters |

---

## Recovery Procedures

### Scenario 1: Wrapper Node Crashes

**Symptoms**:
- Service calls fail
- Node not listed in `ros2 node list`
- ROS2 logs show segfault or exception

**Recovery Steps**:
1. Check logs: `ros2 log view` or `journalctl -f`
2. Identify error cause
3. Restart wrapper node: `ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py`
4. If persistent, check script syntax: `python3 -m py_compile scripts/cotton_detect_ros2_wrapper.py`
5. If still failing, rebuild: `colcon build --packages-select cotton_detection_ros2`

**Prevention**: Monitor node health, implement auto-restart in systemd service

---

### Scenario 2: Camera Disconnected

**Symptoms**:
- `lsusb` doesn't show camera
- "Device not found" errors
- DepthAI SDK cannot connect

**Recovery Steps**:
1. Physically replug USB cable
2. Check dmesg: `dmesg | tail -50`
3. Check USB permissions: `ls -l /dev/bus/usb/*/*` (ensure rw permissions)
4. Verify udev rules: `ls /etc/udev/rules.d/*luxonis*`
5. Restart wrapper node after camera reconnects

**Prevention**: Use high-quality cable, proper strain relief, monitor USB logs

---

### Scenario 3: Detection Timeout

**Symptoms**:
- Service call times out
- "Detection timeout" in logs
- cotton_details.txt not created

**Recovery Steps**:
1. Check if CottonDetect.py is running: `ps aux | grep CottonDetect`
2. Check output directory permissions: `ls -ld /tmp/cotton_detection_output`
3. Increase timeout: `ros2 param set /cotton_detect_ros2_wrapper detection_timeout 20.0`
4. Check for CottonDetect.py errors: `journalctl | grep CottonDetect`
5. Restart wrapper if needed

**Prevention**: Set adequate timeout (10-15 seconds), monitor script execution time

---

### Scenario 4: Incorrect Detection Coordinates

**Symptoms**:
- Detections present but coordinates wrong
- Robot arm moves to incorrect positions
- cotton_details.txt shows unexpected values

**Recovery Steps**:
1. Verify cotton_details.txt format: `cat /tmp/cotton_detection_output/cotton_details.txt`
2. Check coordinate parsing in wrapper: Review line 200-230 of wrapper script
3. Verify TF frames: `ros2 run tf2_ros tf2_echo base_link camera_rgb_optical_frame`
4. Re-run calibration: `cd config/cameras/oak_d_lite && python3 export_calibration.py`
5. Check for camera mounting changes

**Prevention**: Regular calibration checks, TF frame validation

---

### Scenario 5: System-wide Failure

**Symptoms**:
- Multiple nodes failing
- ROS2 daemon not responding
- System unresponsive

**Recovery Steps**:
1. Stop all ROS2 nodes: `killall -9 ros2`
2. Kill ROS2 daemon: `ros2 daemon stop`
3. Restart ROS2 daemon: `ros2 daemon start`
4. Re-source workspace: `source install/setup.bash`
5. Restart individual nodes one by one
6. If persistent, reboot system

**Prevention**: Monitor system resources, avoid resource exhaustion

---

## Monitoring and Validation

### Key Metrics to Monitor

#### Performance Metrics
- **Detection Latency**: < 2 seconds (Phase 1 target)
- **Service Success Rate**: > 99%
- **USB Disconnections**: 0 per hour
- **Memory Usage**: Stable (< 10% growth per hour)
- **CPU Usage**: < 50% average

#### Quality Metrics
- **Detection Accuracy**: ±5cm spatial accuracy at 1.0-1.5m
- **False Positive Rate**: < 5%
- **False Negative Rate**: < 10%
- **Confidence Scores**: > 0.5 for valid detections

---

### Monitoring Tools

#### System Monitoring
```bash
# Monitor CPU/Memory
htop

# Monitor USB connectivity
watch -n 1 'lsusb | grep 03e7:2485'

# Monitor USB errors
dmesg -w | grep -i usb

# Monitor disk space
df -h
```

#### ROS2 Monitoring
```bash
# Monitor node status
ros2 node list
watch -n 1 'ros2 node list'

# Monitor service availability
ros2 service list | grep cotton_detection

# Monitor topic rates
ros2 topic hz /cotton_detection/results

# Monitor parameter values
ros2 param list /cotton_detect_ros2_wrapper
```

#### DepthAI Monitoring
```python
#!/usr/bin/env python3
import depthai as dai
import time

while True:
    try:
        with dai.Device() as device:
            print(f"Camera connected: {device.getMxId()}")
            print(f"USB Speed: {device.getUsbSpeed()}")
            print(f"Device temperature: {device.getChipTemperature()}")
            time.sleep(5)
    except Exception as e:
        print(f"Camera not available: {e}")
        time.sleep(5)
```

---

### Validation Checklist

#### Daily Validation (During Deployment)
- [ ] Camera connectivity check
- [ ] Detection service responsive
- [ ] USB mode correct (USB2)
- [ ] No USB errors in dmesg
- [ ] Node memory usage normal
- [ ] Detection accuracy spot check

#### Weekly Validation
- [ ] Full detection accuracy test (10 targets)
- [ ] Multi-hour stability test (4+ hours)
- [ ] USB cable inspection
- [ ] Camera calibration verification
- [ ] Performance metrics review
- [ ] Log file analysis

#### Monthly Validation
- [ ] Complete system audit
- [ ] Compare performance with baseline
- [ ] Review and update documentation
- [ ] Plan Phase 2 enhancements
- [ ] Assess need for maintenance

---

## Deployment Checklist

### Pre-Deployment ✅
- [x] All code built successfully
- [x] All 38 ROS1 scripts verified present
- [x] Documentation complete
- [x] Testing plan documented
- [x] USB2 configuration verified
- [x] URDF updated for OAK-D Lite
- [x] Calibration export tool ready

### Hardware Deployment ⏳
- [ ] OAK-D Lite camera available
- [ ] USB cable (5m, high-quality)
- [ ] Mounting hardware for camera
- [ ] Backup ROS1 system accessible
- [ ] Test cotton targets prepared

### Stage 1: Benchtop ⏳
- [ ] Camera detected and initialized
- [ ] Calibration exported
- [ ] Detection accuracy validated
- [ ] USB2 stability confirmed
- [ ] Baseline metrics recorded

### Stage 2: Robot Integration ⏳
- [ ] Camera mounted on robot
- [ ] TF frames validated
- [ ] Full stack launches successfully
- [ ] Detection → motion workflow tested
- [ ] Integration issues resolved

### Stage 3: Field Trial ⏳
- [ ] Supervised field deployment
- [ ] Multi-hour stability confirmed
- [ ] Performance meets requirements
- [ ] Stakeholders satisfied
- [ ] Production readiness approved

---

## Conclusion

### Deployment Confidence: 🟢 **HIGH**

**Reasons**:
1. ✅ Proven ROS1 code reused (zero modifications)
2. ✅ All ROS2 improvements preserved
3. ✅ Comprehensive testing plan
4. ✅ Multiple fallback options
5. ✅ Clear rollback to ROS1 if needed

### Next Steps

1. ⏳ **Obtain OAK-D Lite camera**
2. ⏳ **Execute Stage 1** (benchtop testing)
3. ⏳ **Execute Stage 2** (robot integration)
4. ⏳ **Execute Stage 3** (field trial)
5. ⏳ **Production deployment**

### Success Criteria

**Phase 1 is successful if**:
- ✅ Camera integrates with ROS2
- ✅ Detection accuracy matches ROS1
- ✅ System stable for multi-hour operation
- ✅ Stakeholders approve for production

**Phase 2 readiness**:
- After Phase 1 proven successful
- Direct DepthAI pipeline integration
- Enhanced real-time streaming
- Continuous detection mode

---

**Document Version**: 1.0  
**Risk Level**: 🟢 LOW  
**Deployment Status**: ✅ Ready for Hardware Testing  
**Next Review**: After Stage 1 completion
