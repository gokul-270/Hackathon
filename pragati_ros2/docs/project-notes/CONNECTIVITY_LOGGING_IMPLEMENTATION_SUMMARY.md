# Connectivity & Logging Improvements - Implementation Summary

**Date:** February 3, 2026
**Status:** Implementation Complete - Ready for Testing
**Issue:** Connectivity problems and log overwrites from January 2026 field trial

---

## Problem Statement

During the January 2026 field trial, we encountered three critical issues:

1. **Log File Overwrites:** "all the ros nodes logging was per date and time, but this was overwriting to the same file and hence also we couldn't get the logs"
   - Made it impossible to debug past failures
   - Lost historical data on every restart

2. **MQTT Reconnection Visibility:** Auto-reconnect was implemented but events weren't logged
   - Operators couldn't see disconnection/reconnection patterns
   - Made debugging MQTT issues impossible without real-time monitoring

3. **Network Connectivity Issues:** "one of the rpi was not connecting to this router also, i think this rpi has some issue particularly"
   - No systematic way to identify faulty hardware
   - Couldn't differentiate hardware vs configuration problems

---

## Solutions Implemented

### 1. Timestamped Logging with Rotation

**Files Modified:**
- `launch/ARM_client.py` (lines 32-57)
- `scripts/vehicle_mqtt_bridge.py` (lines 1-68)

**Changes:**
```python
# OLD (ARM_client.py line 35):
LOG_FILE = os.path.join(LOG_DIR, 'arm_client.log')  # Fixed filename!

# NEW (lines 32-57):
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
LOG_FILE = os.path.join(LOG_DIR, f'arm_client_{timestamp}.log')

# Log rotation: keep last 10 files
import glob
log_files = sorted(glob.glob(os.path.join(LOG_DIR, 'arm_client_*.log')))
if len(log_files) > 10:
    for old_log in log_files[:-10]:
        os.remove(old_log)
```

**Benefits:**
- ✅ Every restart creates new timestamped log file
- ✅ Historical logs preserved (last 10 sessions)
- ✅ Can debug issues that happened hours/days ago
- ✅ Log file location announced at startup
- ✅ Automatic cleanup prevents disk space issues

**Log File Examples:**
```
~/pragati_ros2/logs/arm_client_20260203_083015.log
~/pragati_ros2/logs/arm_client_20260203_101422.log
~/pragati_ros2/logs/arm_client_20260203_143056.log
~/pragati_ros2/logs/vehicle_mqtt_bridge_20260203_083020.log
```

---

### 2. Enhanced MQTT Reconnection Tracking

**Files Modified:**
- `launch/ARM_client.py` (lines 104-112, 135-168, 221-228)
- `scripts/vehicle_mqtt_bridge.py` (lines 104-112, 127-157, 184-194)

**Changes:**

**Added Global Counters:**
```python
# Track connection events (lines 110-112)
mqtt_connection_count = 0  # Total connections (initial + reconnects)
mqtt_reconnect_count = 0   # Only reconnections (excludes initial)
```

**Enhanced on_connect Callback:**
```python
# OLD:
log_info("MQTT Connected successfully")

# NEW (lines 135-150):
mqtt_connection_count += 1
is_reconnect = mqtt_connection_count > 1

if is_reconnect:
    mqtt_reconnect_count += 1
    logger.warning(f"MQTT RECONNECTED successfully (reconnect #{mqtt_reconnect_count}, total connections: {mqtt_connection_count})")
else:
    logger.info("MQTT Connected successfully (initial connection)")
```

**Enhanced on_disconnect Callback:**
```python
# OLD:
printINFO(f"MQTT Unexpected disconnect (code={rc}). Will attempt reconnection...")

# NEW (lines 221-228):
logger.warning(f"MQTT UNEXPECTED DISCONNECT (code={rc}). Auto-reconnect will attempt to restore connection... (previous reconnects: {mqtt_reconnect_count})")
```

**Benefits:**
- ✅ Every reconnection logged as WARNING (highly visible)
- ✅ Can count reconnection frequency
- ✅ Can identify patterns (time-based, event-triggered)
- ✅ Operators can see system stability at a glance
- ✅ Debugging MQTT issues no longer requires real-time monitoring

**Example Log Output:**
```
2026-02-03 08:30:15 [INFO] MQTT Connected successfully (initial connection)
2026-02-03 09:15:22 [WARNING] MQTT UNEXPECTED DISCONNECT (code=7). Auto-reconnect will attempt... (previous reconnects: 0)
2026-02-03 09:15:27 [WARNING] MQTT RECONNECTED successfully (reconnect #1, total connections: 2)
2026-02-03 11:43:08 [WARNING] MQTT UNEXPECTED DISCONNECT (code=7). Auto-reconnect will attempt... (previous reconnects: 1)
2026-02-03 11:43:13 [WARNING] MQTT RECONNECTED successfully (reconnect #2, total connections: 3)
```

---

### 3. Network Stability Diagnostic Script

**New File Created:**
- `scripts/diagnostics/test_network_stability.sh` (209 lines)

**Features:**
- Pings router for configurable duration (default 5 minutes)
- Calculates packet loss percentage
- Provides health verdict: HEALTHY / MONITOR / PROBLEM / CRITICAL
- Shows WiFi signal strength
- Checks power management status
- Provides troubleshooting recommendations
- Saves detailed report with timestamp

**Usage:**
```bash
# Default (192.168.1.1, 5 minutes)
./test_network_stability.sh

# Custom router and duration
./test_network_stability.sh 192.168.1.1 300

# Quick 1-minute test
./test_network_stability.sh 192.168.1.1 60
```

**Verdict Criteria:**
- **< 1% loss:** HEALTHY ✅
- **1-5% loss:** MONITOR ⚠️
- **5-20% loss:** PROBLEM ❌
- **> 20% loss:** CRITICAL 🔥

**Benefits:**
- ✅ Systematic way to identify problematic RPi
- ✅ Repeatable test for all units
- ✅ Clear pass/fail criteria
- ✅ Detects power management issues
- ✅ Actionable troubleshooting steps included

**Example Output:**
```
==============================================
Verdict
==============================================
❌ PROBLEM: High packet loss detected (5-20% loss)
This RPi has significant connectivity issues.
Recommendation: Check power management, WiFi driver, signal strength
Packet Loss: 12.3%
```

---

### 4. Documentation Updates

**Files Modified:**
- `docs/MQTT_VEHICLE_ARM_INTEGRATION.md` - Added "Log Files & Debugging" section (after line 523)
- `docs/guides/TROUBLESHOOTING.md` - Added "Network & Connectivity Issues" section (after line 530)

**New Files Created:**
- `docs/project-notes/CONNECTIVITY_LOGGING_TEST_PLAN.md` - Comprehensive test plan (34 tests)
- `scripts/diagnostics/README.md` - Diagnostic scripts documentation

**Documentation Coverage:**
- ✅ Log file locations and naming conventions
- ✅ How to find and analyze reconnection events
- ✅ Network diagnostic procedures
- ✅ RPi identification workflow
- ✅ Power management troubleshooting
- ✅ Test procedures for all improvements

---

## Files Changed Summary

### Code Changes (2 files):
1. ✅ `launch/ARM_client.py`
   - Added timestamped logging (lines 32-57)
   - Added reconnection tracking (lines 110-112)
   - Enhanced on_connect callback (lines 135-168)
   - Enhanced on_disconnect callback (lines 221-228)

2. ✅ `scripts/vehicle_mqtt_bridge.py`
   - Added timestamped logging (lines 1-68)
   - Added reconnection tracking (lines 110-112)
   - Enhanced on_connect callback (lines 127-157)
   - Enhanced on_disconnect callback (lines 184-194)

### New Scripts (1 file):
3. ✅ `scripts/diagnostics/test_network_stability.sh`
   - Network stability testing tool (209 lines, executable)

### Documentation (4 files):
4. ✅ `docs/MQTT_VEHICLE_ARM_INTEGRATION.md`
   - Added "Log Files & Debugging" section

5. ✅ `docs/guides/TROUBLESHOOTING.md`
   - Added "Network & Connectivity Issues" section (150+ lines)

6. ✅ `docs/project-notes/CONNECTIVITY_LOGGING_TEST_PLAN.md`
   - Comprehensive test plan (34 test cases)

7. ✅ `scripts/diagnostics/README.md`
   - Diagnostic scripts documentation

---

## Testing Plan

### Phase 1: Logging Functionality (3 tests)
- Test 1.1: Timestamped log file creation
- Test 1.2: Log rotation (10 file limit)
- Test 1.3: Verify no overwrites

### Phase 2: MQTT Reconnection Logging (3 tests)
- Test 2.1: Initial connection logging
- Test 2.2: Reconnection event logging
- Test 2.3: Disconnect event logging

### Phase 3: Network Stability (3 tests)
- Test 3.1: Script on healthy RPi
- Test 3.2: Compare across multiple RPis
- Test 3.3: Power management detection

### Phase 4: Integration (2 tests)
- Test 4.1: Full system connectivity test
- Test 4.2: Log analysis after field operation

**See:** `docs/project-notes/CONNECTIVITY_LOGGING_TEST_PLAN.md` for detailed procedures

---

## Deployment Checklist

### Pre-Deployment:
- [ ] Review code changes with team
- [ ] Run syntax checks on Python files
- [ ] Test network script on development machine
- [ ] Verify log directory paths exist on target RPis

### Deployment:
- [ ] Deploy updated `ARM_client.py` to all ARM RPis
- [ ] Deploy updated `vehicle_mqtt_bridge.py` to vehicle RPi
- [ ] Deploy `test_network_stability.sh` to all RPis
- [ ] Set execute permissions on network test script
- [ ] Create log directories if not exist: `mkdir -p ~/pragati_ros2/logs`

### Post-Deployment:
- [ ] Restart ARM_client on all ARM RPis
- [ ] Restart vehicle_mqtt_bridge on vehicle RPi
- [ ] Verify new timestamped logs created
- [ ] Run network stability test on all RPis
- [ ] Document baseline packet loss for each RPi
- [ ] Run Phase 1 & 2 tests from test plan

### Field Trial Preparation:
- [ ] Ensure all RPis have synchronized clocks (NTP)
- [ ] Document expected packet loss baselines
- [ ] Train operators on log locations
- [ ] Prepare log collection procedure
- [ ] Schedule mid-trial network tests

---

## Known Limitations & Mitigations

1. **Log Storage Growth**
   - **Limitation:** 10 files per component could consume significant disk space
   - **Mitigation:** Monitor disk usage, reduce to 7 files if needed, or add size-based rotation

2. **Clock Synchronization**
   - **Limitation:** Timestamps only useful if RPi clocks synchronized
   - **Mitigation:** Configure NTP on all RPis, verify sync before deployment

3. **Network Test Duration**
   - **Limitation:** Short tests may miss intermittent issues
   - **Mitigation:** Run extended tests (30+ minutes) for thorough assessment

4. **MQTT Broker Logging**
   - **Limitation:** Client logs don't capture broker-side issues
   - **Mitigation:** Monitor mosquitto logs separately on vehicle RPi

---

## Success Metrics

### Immediate (Post-Deployment):
- ✅ No log overwrites occur
- ✅ All reconnection events visible in logs
- ✅ Network test identifies problem RPi (if exists)
- ✅ System recovers automatically from disconnections

### Short-term (First Week):
- ✅ Can analyze past issues using historical logs
- ✅ Reconnection patterns identified
- ✅ Network baselines established for all RPis
- ✅ Operators comfortable with new tools

### Long-term (Next Field Trial):
- ✅ Faster issue diagnosis (hours vs days)
- ✅ Proactive identification of failing hardware
- ✅ Reduced downtime from connectivity issues
- ✅ Complete audit trail for all connectivity events

---

## Rollback Plan

If issues arise with new changes:

1. **Immediate Rollback (Code):**
   ```bash
   # Restore old ARM_client.py and vehicle_mqtt_bridge.py
   git checkout HEAD~1 launch/ARM_client.py scripts/vehicle_mqtt_bridge.py

   # Restart services
   # (on each RPi)
   pkill -f ARM_client
   pkill -f vehicle_mqtt_bridge
   # Restart normally
   ```

2. **Partial Rollback (Keep Logging, Revert Reconnection Tracking):**
   - Comment out reconnection counter logic
   - Keep timestamped logging
   - Preserves log retention benefits

3. **Documentation Rollback:**
   - Not necessary - documentation additions don't affect runtime

---

## Related Issues & References

**Issue References:**
- `docs/project-notes/FEBRUARY_FIELD_TRIAL_PLAN_2026.md` line 65 - MQTT reconnect logging needed
- `openspec/changes/requirements-audit-jan-2026/tasks.md` line 164 - Log file overwrite issue
- `docs/project-notes/PRODUCTION_ISSUES_2025-11-23.md` section 1.10 - WiFi issues

**Related Documentation:**
- `docs/MQTT_VEHICLE_ARM_INTEGRATION.md` - MQTT architecture and setup
- `docs/guides/hardware/RPi_POWER_MGMT_FIX_SUMMARY.md` - Power management fixes (Oct 2025)
- `docs/ARM_CLIENT_TESTING.md` - ARM_client testing procedures

**Code References:**
- Auto-reconnect implementation: `ARM_client.py:482` (`reconnect_delay_set()`)
- MQTT callbacks: `ARM_client.py:131-228`, `vehicle_mqtt_bridge.py:127-194`

---

## Next Steps

1. **Code Review** - Team review of changes
2. **Development Testing** - Run tests on dev environment
3. **Deployment** - Push to all RPis following checklist
4. **Validation** - Execute Phase 1 & 2 of test plan
5. **Baseline Collection** - Run network tests, document baselines
6. **Field Trial** - Monitor during next operation
7. **Post-Trial Analysis** - Analyze logs, measure effectiveness
8. **Iteration** - Adjust log retention, test duration based on results

---

**Author:** OpenCode AI Assistant
**Reviewed by:** [Pending]
**Approved by:** [Pending]
**Deployment Date:** [Pending]

---

## Questions?

Contact the Pragati Robotics team or refer to:
- `docs/guides/TROUBLESHOOTING.md` - Troubleshooting procedures
- `docs/project-notes/CONNECTIVITY_LOGGING_TEST_PLAN.md` - Detailed test procedures
- `scripts/diagnostics/README.md` - Diagnostic tools usage
