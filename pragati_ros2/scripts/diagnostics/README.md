# Diagnostics Scripts

This directory contains diagnostic and troubleshooting scripts for the Pragati ROS2 system.

## Available Scripts

### test_network_stability.sh

Tests network connection stability to identify problematic RPi units.

**Purpose:**
- Identify RPis with connectivity issues
- Measure packet loss to router
- Detect WiFi signal strength problems
- Verify power management configuration

**Usage:**
```bash
# Basic usage (default: 192.168.1.1, 5 minutes)
./test_network_stability.sh

# Custom router IP and duration
./test_network_stability.sh 192.168.1.1 300

# Quick 1-minute test
./test_network_stability.sh 192.168.1.1 60
```

**Output:**
- Real-time progress during ping test
- Packet loss percentage
- Verdict: HEALTHY / MONITOR / PROBLEM / CRITICAL
- WiFi signal strength and power management status
- Troubleshooting recommendations
- Detailed report saved to `/tmp/network_test_<hostname>_<timestamp>.txt`

**Interpretation:**
- `< 1% loss`: Healthy network
- `1-5% loss`: Minor issues, monitor
- `5-20% loss`: Significant problems, needs investigation
- `> 20% loss`: Critical issue, likely hardware fault

**Example Output:**
```
==============================================
Network Stability Test
==============================================
Target: 192.168.1.1
Duration: 300 seconds (300 pings)
Start time: Mon Feb 3 17:30:00 UTC 2026
==============================================

Running ping test to 192.168.1.1...
Progress: 100%

==============================================
Results Analysis
==============================================
Test Date: Mon Feb 3 17:35:00 UTC 2026
Hostname: vehicle-rpi
IP Address: 192.168.1.40
Target: 192.168.1.1
Duration: 300 seconds
Packet Loss: 0.3%
RTT Statistics: rtt min/avg/max/mdev = 1.234/2.567/8.901/1.234 ms
WiFi Signal: Signal level=-45 dBm
Power Management: Power Management:off

==============================================
Verdict
==============================================
✅ HEALTHY: Network stability is excellent (< 1% loss)
This RPi has no connectivity issues.
Packet Loss: 0.3%
```

**Related Documentation:**
- `docs/guides/TROUBLESHOOTING.md` - Network & Connectivity Issues section
- `docs/guides/hardware/RPi_POWER_MGMT_FIX_SUMMARY.md` - Power management fixes
- `docs/project-notes/CONNECTIVITY_LOGGING_TEST_PLAN.md` - Complete test procedures

### fleet_drift_report.py

Analyzes boot-timing v5 JSON captures to detect configuration drift across the Pragati RPi fleet.

**Usage:**
```bash
# Basic usage with default requirements.txt
python3 scripts/diagnostics/fleet_drift_report.py \
    --input-dir collected_logs/2026-03-05_v5/

# With explicit requirements file
python3 scripts/diagnostics/fleet_drift_report.py \
    --input-dir collected_logs/2026-03-05_v5/ \
    --requirements requirements.txt

# Save report to file (also prints to stdout)
python3 scripts/diagnostics/fleet_drift_report.py \
    --input-dir collected_logs/2026-03-05_v5/ \
    --output /tmp/fleet_drift_report.txt

# Verbose mode
python3 scripts/diagnostics/fleet_drift_report.py \
    --input-dir collected_logs/2026-03-05_v5/ \
    --verbose
```

**Prerequisites:**
- Python 3.12+ (stdlib only, no pip dependencies)
- Boot-timing v5+ JSON captures (collected via `sync.sh --collect-logs`)

**What It Checks:**

| Category | What | Severity |
|----------|------|----------|
| OS Version | Point release drift across fleet | WARN |
| Apt Packages | Missing expected packages, extra packages, inter-RPi diff | WARN/INFO |
| Pip Packages | Version constraint violations, inter-RPi version drift | WARN/INFO |
| Config.txt | CAN dtoverlay presence/absence vs role, parameter validation | ERROR/WARN |
| Services | Missing expected services, inter-RPi diff, null field handling | ERROR/WARN/INFO |

**Exit Codes:**
- `0`: No ERROR-level findings
- `1`: One or more ERROR-level findings, or input validation failure

**Running Tests:**
```bash
cd scripts/diagnostics
python3 -m pytest test_fleet_drift_report.py -v
```

## Common Use Cases

### 1. Identify Problematic RPi After Field Trial

Run the test on all RPis and compare results:

```bash
# On each RPi (Vehicle, Arm1, Arm2, etc.):
cd ~/pragati_ros2/scripts/diagnostics
./test_network_stability.sh 192.168.1.1 300

# View summary
cat /tmp/network_stability_summary.txt

# Compare packet loss across all units
# The RPi with highest loss is likely the problem unit
```

### 2. Verify Power Management Fix

Check if power management is causing issues:

```bash
# Before fix
./test_network_stability.sh
# Note packet loss percentage

# Apply power management fix
sudo iwconfig wlan0 power off
echo "wireless-power off" | sudo tee -a /etc/network/interfaces.d/wlan0

# Test again
./test_network_stability.sh
# Packet loss should be lower
```

### 3. Monitor Network Health Over Time

Run periodic tests and track trends:

```bash
# Run hourly test
*/60 * * * * /home/pi/pragati_ros2/scripts/diagnostics/test_network_stability.sh 192.168.1.1 60 >> /var/log/network_health.log 2>&1

# Analyze trends
grep "Packet Loss:" /var/log/network_health.log
```

## Troubleshooting

### Script fails with "bc: command not found"

Install bc:
```bash
sudo apt update
sudo apt install bc
```

### No WiFi information shown

**Cause:** Using Ethernet or WiFi interface not named `wlan0`
**Fix:** Script automatically handles this, shows "N/A" for Ethernet

### High packet loss on all RPis

**Likely Cause:** Router issue, not RPi-specific
**Fix:** Check router logs, test with external device, verify router configuration

### Permission denied errors

**Cause:** Script not executable
**Fix:**
```bash
chmod +x test_network_stability.sh
```

### test_dds_discovery_3node.sh

Validates ROS2 DDS discovery across 3 RPi nodes (vehicle + 2 arms) on the Windows Mobile
Hotspot network. Corresponds to V19 in the March 2026 Field Trial Plan.

**Purpose:**
- Phase 1: Verify DDS can discover nodes across RPis when sharing a domain (shared-domain)
- Phase 2: Verify production domain isolation holds (no cross-domain topic bleed)

**Usage:**
```bash
# Full 30-minute test (15 min per phase)
./test_dds_discovery_3node.sh

# Quick 4-minute dry run (2 min per phase)
./test_dds_discovery_3node.sh --quick
```

**Prerequisites:**
- 3 RPis on Windows Mobile Hotspot (192.168.137.x subnet)
- SSH keys set up for ubuntu@ on all RPis
- ROS2 Jazzy + CycloneDDS installed on all RPis
- Run from WSL (uses ssh.exe to reach hotspot subnet)

**Pass Criteria:**
- Phase 1: All 3 nodes discover each other's topics (3/3) at every check
- Phase 2: Each node sees only its own topic (1/1), zero cross-domain bleed

**Output:**
- Results saved to `/tmp/dds_discovery_test_<timestamp>/`
- Exit code 0 = PASS, 1 = FAIL

**Related:**
- `docs/project-notes/MARCH_FIELD_TRIAL_PLAN_2026.md` - V19 task

## Future Additions

Potential future diagnostic scripts:

1. **CAN Bus Health Check** - Test CAN communication with motors
2. **MQTT Connection Monitor** - Long-term MQTT stability monitoring
3. **Disk Space Analyzer** - Check log file growth and cleanup
4. **System Resource Monitor** - CPU/Memory/Temperature tracking
5. **Service Health Dashboard** - Combined status of all system services

---

**Created:** February 3, 2026
**Maintained by:** Pragati Robotics Team
**Related Issues:** January 2026 field trial connectivity problems
