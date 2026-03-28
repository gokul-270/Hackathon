# Connectivity & Logging Test Plan
**Created:** February 3, 2026  
**Purpose:** Validate improved logging and network connectivity diagnostics for Pragati ROS2 system

---

## Overview

This document outlines testing procedures for recently implemented improvements to connectivity logging and network diagnostics. These improvements address issues encountered during the January 2026 field trial where logs were overwritten and connectivity issues couldn't be properly debugged.

**Related Issues:**
- MQTT reconnection events not logged (`docs/project-notes/FEBRUARY_FIELD_TRIAL_PLAN_2026.md` line 65)
- Log file overwrites preventing historical debugging (`openspec/changes/requirements-audit-jan-2026/tasks.md` line 164)
- Intermittent RPi network connectivity issues (January 2026 field trial)

---

## Changes Made

### 1. **Timestamped Logging** (ARM_client.py & vehicle_mqtt_bridge.py)

**What Changed:**
- Log files now use timestamps: `arm_client_YYYYMMDD_HHMMSS.log`
- Log rotation keeps last 10 files automatically
- Both file and console logging enabled
- Log file location announced at startup

**Why:**
- Previous logs used fixed filename `arm_client.log` → overwrote on every restart
- Made it impossible to debug past failures
- User reported: "logging was per date and time, but this was overwriting to the same file"

### 2. **Enhanced MQTT Reconnection Logging**

**What Changed:**
- Track connection count (initial + reconnects)
- Track reconnection count separately
- Log reconnection events as WARNING (highly visible)
- Log format: "MQTT RECONNECTED successfully (reconnect #N, total connections: M)"

**Why:**
- Auto-reconnect was already implemented but not visible in logs
- Operators couldn't tell if disconnections were happening
- Made debugging MQTT issues impossible without real-time monitoring

### 3. **Network Stability Test Script**

**What Added:**
- New script: `scripts/diagnostics/test_network_stability.sh`
- Tests network connectivity to router for 5 minutes
- Calculates packet loss percentage
- Provides verdict: HEALTHY / MONITOR / PROBLEM / CRITICAL
- Includes WiFi signal strength and power management status

**Why:**
- User reported specific RPi had connectivity issues
- No systematic way to identify faulty hardware vs configuration
- Needed repeatable test to run on all RPis

---

## Test Plan

### Phase 1: Logging Functionality Tests

#### Test 1.1: Timestamped Log File Creation

**Objective:** Verify logs are created with timestamps and don't overwrite

**Prerequisites:**
- Access to RPi running ARM_client.py or vehicle_mqtt_bridge.py

**Steps:**
```bash
# 1. Check existing logs
ls -lh ~/pragati_ros2/logs/

# 2. Start ARM_client (or vehicle_mqtt_bridge)
cd ~/pragati_ros2
ros2 launch motor_control_ros2 arm_client.launch.py

# 3. Stop after 5 seconds (Ctrl+C)

# 4. Check log file was created
ls -lh ~/pragati_ros2/logs/
# Expected: File like arm_client_20260203_173045.log

# 5. Check log contains startup message
tail -20 ~/pragati_ros2/logs/arm_client_*.log
# Expected: "ARM_client started. Logging to: /path/to/file"

# 6. Start again
ros2 launch motor_control_ros2 arm_client.launch.py

# 7. Stop after 5 seconds

# 8. Verify two separate log files exist
ls -lh ~/pragati_ros2/logs/
```

**Expected Results:**
- ✅ Each startup creates a new timestamped log file
- ✅ Old logs are preserved (not overwritten)
- ✅ Startup message shows log file path

**Pass/Fail Criteria:**
- PASS: Two distinct log files with different timestamps exist
- FAIL: Only one log file, or file was overwritten

---

#### Test 1.2: Log Rotation

**Objective:** Verify old logs are automatically removed after 10 files

**Prerequisites:**
- Access to RPi
- Able to start/stop ARM_client multiple times

**Steps:**
```bash
# 1. Clean logs directory
rm -f ~/pragati_ros2/logs/arm_client_*.log

# 2. Start and stop ARM_client 12 times (creates 12 log files)
for i in {1..12}; do
    echo "Starting iteration $i..."
    timeout 3 ros2 launch motor_control_ros2 arm_client.launch.py || true
    sleep 1
done

# 3. Count log files
ls ~/pragati_ros2/logs/arm_client_*.log | wc -l
# Expected: 10 (oldest 2 should be deleted)

# 4. Check oldest files were removed
ls -lt ~/pragati_ros2/logs/arm_client_*.log
# Should show only 10 most recent files
```

**Expected Results:**
- ✅ Exactly 10 log files remain
- ✅ Oldest files automatically deleted
- ✅ Most recent 10 files preserved

**Pass/Fail Criteria:**
- PASS: Exactly 10 files, newest ones preserved
- FAIL: More than 10 files, or wrong files deleted

---

### Phase 2: MQTT Reconnection Logging Tests

#### Test 2.1: MQTT Initial Connection Logging

**Objective:** Verify initial MQTT connection is logged correctly

**Prerequisites:**
- MQTT broker running on vehicle RPi
- ARM_client not running

**Steps:**
```bash
# 1. Start ARM_client with logging
ros2 launch motor_control_ros2 arm_client.launch.py

# 2. Wait for MQTT connection (2-5 seconds)

# 3. Check log for initial connection message
grep "MQTT Connected" ~/pragati_ros2/logs/arm_client_*.log | tail -1
# Expected: "MQTT Connected successfully (initial connection)"

# 4. Verify connection counter
grep "total connections:" ~/pragati_ros2/logs/arm_client_*.log | tail -1
# Expected: "total connections: 1"
```

**Expected Results:**
- ✅ Log shows "initial connection"
- ✅ Connection count is 1
- ✅ No reconnection count in message

**Pass/Fail Criteria:**
- PASS: Logs show initial connection with count=1
- FAIL: Shows reconnection or wrong count

---

#### Test 2.2: MQTT Reconnection Logging

**Objective:** Verify MQTT reconnection events are logged with counters

**Prerequisites:**
- MQTT broker running
- ARM_client running and connected

**Steps:**
```bash
# 1. Verify ARM_client is connected
# Check in ARM_client terminal or log:
tail -f ~/pragati_ros2/logs/arm_client_*.log | grep "MQTT Connected"

# 2. Simulate network disconnect - restart MQTT broker
sudo systemctl restart mosquitto

# 3. Wait 5-10 seconds for auto-reconnect

# 4. Check for reconnection in log
grep "RECONNECTED" ~/pragati_ros2/logs/arm_client_*.log
# Expected: "MQTT RECONNECTED successfully (reconnect #1, total connections: 2)"

# 5. Repeat disconnect/reconnect 2 more times
sudo systemctl restart mosquitto
sleep 10
sudo systemctl restart mosquitto
sleep 10

# 6. Check reconnection counts
grep "RECONNECTED" ~/pragati_ros2/logs/arm_client_*.log
# Expected to see:
# - reconnect #1, total connections: 2
# - reconnect #2, total connections: 3
# - reconnect #3, total connections: 4
```

**Expected Results:**
- ✅ Each reconnection logged with incrementing counters
- ✅ Reconnection count increases: #1, #2, #3, etc.
- ✅ Total connection count increases: 2, 3, 4, etc.
- ✅ Log level is WARNING (visible in production logs)

**Pass/Fail Criteria:**
- PASS: All reconnections logged with correct incrementing counters
- FAIL: Missing reconnection events or incorrect counters

---

#### Test 2.3: MQTT Disconnect Logging

**Objective:** Verify unexpected disconnections are logged

**Prerequisites:**
- ARM_client connected to MQTT broker

**Steps:**
```bash
# 1. Monitor log in real-time
tail -f ~/pragati_ros2/logs/arm_client_*.log &

# 2. Stop MQTT broker (simulates network failure)
sudo systemctl stop mosquitto

# 3. Check for disconnect message in log
grep "UNEXPECTED DISCONNECT" ~/pragati_ros2/logs/arm_client_*.log | tail -1
# Expected: "MQTT UNEXPECTED DISCONNECT (code=X). Auto-reconnect will attempt..."

# 4. Restart broker
sudo systemctl start mosquitto

# 5. Verify reconnection logged
sleep 10
grep "RECONNECTED" ~/pragati_ros2/logs/arm_client_*.log | tail -1
```

**Expected Results:**
- ✅ Disconnect logged immediately
- ✅ Message mentions auto-reconnect
- ✅ Shows previous reconnect count
- ✅ Reconnection logged after broker restart

**Pass/Fail Criteria:**
- PASS: Both disconnect and reconnect events logged
- FAIL: Missing disconnect or reconnect events

---

### Phase 3: Network Stability Tests

#### Test 3.1: Network Stability Script - Healthy RPi

**Objective:** Verify script correctly identifies healthy network

**Prerequisites:**
- RPi with good WiFi/network connectivity
- Router accessible at known IP

**Steps:**
```bash
# 1. Run network stability test
cd ~/pragati_ros2/scripts/diagnostics
./test_network_stability.sh 192.168.1.1 60  # 1-minute test for speed

# 2. Wait for test completion

# 3. Check verdict
cat /tmp/network_stability_summary.txt
# Expected: Verdict: HEALTHY

# 4. Check packet loss
# Expected: < 1%

# 5. Verify report saved
ls -lh /tmp/network_test_*
```

**Expected Results:**
- ✅ Test completes successfully
- ✅ Packet loss < 1%
- ✅ Verdict: HEALTHY
- ✅ Summary and detailed reports saved

**Pass/Fail Criteria:**
- PASS: Verdict HEALTHY, packet loss < 1%
- FAIL: Higher packet loss or script errors

---

#### Test 3.2: Network Stability Script - Multiple RPis

**Objective:** Compare network stability across all RPis to identify problematic unit

**Prerequisites:**
- Access to all RPis (Vehicle, Arm1, Arm2, etc.)
- All connected to same router

**Steps:**
```bash
# Run on each RPi (use SSH or script below):

# 1. Create test script to run on all RPis
cat > test_all_rpis.sh << 'EOF'
#!/bin/bash
RPIS=("192.168.1.40" "192.168.1.41" "192.168.1.42")  # Vehicle, Arm1, Arm2
ROUTER="192.168.1.1"

for rpi in "${RPIS[@]}"; do
    echo "Testing $rpi..."
    ssh pi@$rpi "cd ~/pragati_ros2/scripts/diagnostics && ./test_network_stability.sh $ROUTER 60"
    ssh pi@$rpi "cat /tmp/network_stability_summary.txt"
    echo "---"
done
EOF

chmod +x test_all_rpis.sh
./test_all_rpis.sh

# 2. Compare packet loss across all units
# Expected: One RPi will have significantly higher loss

# 3. Document which RPi has issues
```

**Expected Results:**
- ✅ Script runs on all RPis
- ✅ Results show relative network health
- ✅ Problem RPi identified by higher packet loss
- ✅ Results saved on each RPi

**Pass/Fail Criteria:**
- PASS: Can compare results and identify outlier RPi
- FAIL: Script fails or results inconsistent

---

#### Test 3.3: Network Stability Script - Power Management Check

**Objective:** Verify script detects power management issues

**Prerequisites:**
- RPi with WiFi
- Root access

**Steps:**
```bash
# 1. Enable WiFi power management (simulate problem)
sudo iwconfig wlan0 power on

# 2. Run network stability test
cd ~/pragati_ros2/scripts/diagnostics
./test_network_stability.sh 192.168.1.1 300  # 5-minute test

# 3. Check power management in results
cat /tmp/network_stability_summary.txt | grep "Power Management"
# Expected: Shows "Power Management:on"

# 4. Disable power management (apply fix)
sudo iwconfig wlan0 power off

# 5. Run test again
./test_network_stability.sh 192.168.1.1 300

# 6. Compare packet loss
# Expected: Lower packet loss with power management off
```

**Expected Results:**
- ✅ Power management status shown in results
- ✅ Packet loss higher with power mgmt ON
- ✅ Packet loss lower with power mgmt OFF
- ✅ Script provides troubleshooting recommendation

**Pass/Fail Criteria:**
- PASS: Script detects power management state, packet loss improves when disabled
- FAIL: No detection or no improvement

---

### Phase 4: End-to-End Integration Tests

#### Test 4.1: Full System Connectivity Test

**Objective:** Verify complete system operates with new logging under real conditions

**Prerequisites:**
- Full Pragati system running (vehicle + arms)
- MQTT broker running
- All nodes launched

**Steps:**
```bash
# 1. Start entire system
# Vehicle RPi:
ros2 launch vehicle_control vehicle.launch.py &
python3 ~/pragati_ros2/scripts/vehicle_mqtt_bridge.py &

# ARM RPis (on each):
ros2 launch motor_control_ros2 arm_client.launch.py &

# 2. Let system run for 10 minutes

# 3. Simulate network issues
# On vehicle RPi:
sudo systemctl restart mosquitto
sleep 30
sudo systemctl restart mosquitto

# 4. Check logs on all units
# Vehicle:
grep -E "RECONNECT|DISCONNECT" ~/pragati_ros2/logs/vehicle_mqtt_bridge_*.log

# Arms:
grep -E "RECONNECT|DISCONNECT" ~/pragati_ros2/logs/arm_client_*.log

# 5. Verify system continues operating
# Send test commands, check arm status

# 6. Review all log files
ls -lh ~/pragati_ros2/logs/
```

**Expected Results:**
- ✅ All nodes create timestamped log files
- ✅ Disconnections/reconnections logged on all units
- ✅ System recovers automatically
- ✅ Multiple log files preserved
- ✅ No data loss or overwrites

**Pass/Fail Criteria:**
- PASS: All logs preserved, reconnections visible, system recovers
- FAIL: Missing logs, overwrites, system fails to recover

---

#### Test 4.2: Log Analysis After Field Operation

**Objective:** Verify logs can be used to diagnose past issues

**Prerequisites:**
- System has been running for at least a day
- Some network interruptions occurred

**Steps:**
```bash
# 1. Collect all log files
mkdir -p ~/log_analysis_$(date +%Y%m%d)
cp ~/pragati_ros2/logs/arm_client_*.log ~/log_analysis_$(date +%Y%m%d)/
cp ~/pragati_ros2/logs/vehicle_mqtt_bridge_*.log ~/log_analysis_$(date +%Y%m%d)/

# 2. Analyze reconnection patterns
cd ~/log_analysis_$(date +%Y%m%d)/
grep "RECONNECTED" *.log | wc -l
# Count total reconnections across all logs

# 3. Find longest disconnect period
grep -E "DISCONNECT|RECONNECT" *.log | sort
# Manually calculate time between disconnect and reconnect

# 4. Identify problematic times
grep "ERROR\|WARNING" *.log | cut -d' ' -f1-2 | uniq -c | sort -n
# Show error/warning frequency by time

# 5. Check correlation with network tests
cat /tmp/network_test_*.txt
# Compare with any saved network stability test results
```

**Expected Results:**
- ✅ Can retrieve logs from multiple sessions
- ✅ Can count reconnection events
- ✅ Can identify patterns (time of day, frequency)
- ✅ Can correlate with network test results
- ✅ Logs provide actionable debugging info

**Pass/Fail Criteria:**
- PASS: Logs enable root cause analysis and pattern identification
- FAIL: Insufficient data or corrupted logs

---

## Success Criteria

### Must Have (P0):
- ✅ No log overwrites - all sessions preserved
- ✅ MQTT reconnections visible in logs
- ✅ Network test script identifies problem RPi
- ✅ System recovers automatically from disconnections

### Should Have (P1):
- ✅ Log rotation works (keeps last 10)
- ✅ Reconnection counters accurate
- ✅ Network test provides actionable recommendations

### Nice to Have (P2):
- ✅ Automated log analysis tools
- ✅ Dashboard showing reconnection history
- ✅ Alerting on excessive reconnections

---

## Known Limitations

1. **Log Storage:** With 10 files per component, log storage could grow large. Monitor disk usage.
   - Mitigation: Reduce retention to 7 files if needed, or add size-based rotation

2. **Clock Synchronization:** Timestamps only useful if RPi clocks are synchronized
   - Mitigation: Ensure NTP is configured on all RPis

3. **Network Test Accuracy:** Short duration tests may miss intermittent issues
   - Mitigation: Run extended tests (30+ minutes) for thorough assessment

4. **MQTT Broker Issues:** If broker itself has problems, clients can't log it
   - Mitigation: Monitor broker logs separately

---

## Troubleshooting Test Failures

### Issue: Logs still overwrite
**Cause:** Old version of code still deployed  
**Fix:** Verify code changes deployed, restart nodes

### Issue: No reconnection messages in logs
**Cause:** Disconnections not occurring, or debug logging disabled  
**Fix:** Check `DEBUG` flag is True, simulate disconnections

### Issue: Network test shows high loss on all RPis
**Cause:** Router issues or network congestion, not RPi-specific  
**Fix:** Test router with external device, check router logs

### Issue: Log rotation not working
**Cause:** Permission issues or `glob` module error  
**Fix:** Check directory permissions, verify Python glob module available

---

## Related Documentation

- `docs/MQTT_VEHICLE_ARM_INTEGRATION.md` - MQTT setup and logging section
- `docs/guides/TROUBLESHOOTING.md` - Network & connectivity troubleshooting
- `docs/guides/hardware/RPi_POWER_MGMT_FIX_SUMMARY.md` - Power management fixes
- `docs/project-notes/FEBRUARY_FIELD_TRIAL_PLAN_2026.md` - Known issues from January trial
- `openspec/changes/requirements-audit-jan-2026/tasks.md` - Requirements and gaps

---

## Test Log Template

```
Test ID: ___________
Date: ___________
Tester: ___________
System Under Test: ___________

Test Result: [ ] PASS  [ ] FAIL  [ ] BLOCKED

Notes:


Issues Found:


Follow-up Actions:


```

---

**Version:** 1.0  
**Last Updated:** February 3, 2026  
**Next Review:** After first field trial with new logging
