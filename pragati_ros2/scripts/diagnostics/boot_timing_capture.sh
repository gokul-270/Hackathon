#!/usr/bin/env bash
# boot_timing_capture.sh — Capture boot and service startup timing data
#
# Runs once after each boot via boot_timing.service (oneshot).
# Writes JSON to ~/pragati_ros2/logs/boot_timing_<YYYYMMDD>_<HHMMSS>.json
# Collected automatically by: ./sync.sh --collect-logs (pulls ~/pragati_ros2/logs/)
#
# Usage (manual):
#   bash scripts/diagnostics/boot_timing_capture.sh
#
# Data captured:
#   - OS boot: kernel time, userspace time, total, critical chain, blame (full)
#   - Problem services: failed units, stuck (activating) units, blocking jobs
#   - Pragati services: launch service, pigpiod, can-watchdog, network-wait timestamps
#   - Hardware: memory, swap, disk I/O, SD card health, CAN interface status, CPU temp
#   - Process snapshot: top 25 processes by CPU at capture time
#   - ROS2 milestones: node first-log, MQTT connected, motor homing done
#   - Launcher internals: CAN setup, SPI wait, ROS2 source, sleep durations
#   - Environment context (v3): throttle state, disk free, USB devices, network
#     interfaces, ROS2 env vars, journal errors, dmesg warnings, package versions,
#     CPU info, kernel modules, enabled services, boot config, OOM events,
#     ROS2 workspace packages

set -euo pipefail

LOGS_DIR="${HOME}/pragati_ros2/logs"
mkdir -p "$LOGS_DIR"

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
export OUTPUT_FILE="${LOGS_DIR}/boot_timing_${TIMESTAMP}.json"

# Collect everything in python3 — it can call subprocess and write JSON cleanly.
python3 << 'PYEOF'
import json
import os
import subprocess
import re
import socket
from datetime import datetime

def run(cmd, timeout=10):
    """Run shell command, return stdout or empty string on failure."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""

def svc_prop(svc, prop):
    """Get a single systemd service property."""
    out = run(f"systemctl show {svc} --property={prop} 2>/dev/null")
    if "=" in out:
        return out.split("=", 1)[1]
    return ""

def first_journal_match(unit, pattern, timeout=10):
    """Get first journalctl line matching pattern for current boot."""
    out = run(
        f"journalctl -b -u {unit} --no-pager -o short-iso 2>/dev/null"
        f" | grep -m1 -iE '{pattern}'",
        timeout=timeout,
    )
    return out

# ── System info ──────────────────────────────────────────────────────────
hostname = socket.gethostname()
captured_at = datetime.now().isoformat()

# Role detection
role = "unknown"
launch_svc = ""
if run("systemctl is-enabled arm_launch.service 2>/dev/null") == "enabled":
    role = "arm"
    launch_svc = "arm_launch.service"
elif run("systemctl is-enabled vehicle_launch.service 2>/dev/null") == "enabled":
    role = "vehicle"
    launch_svc = "vehicle_launch.service"

# ARM_ID from /etc/default/pragati-arm
arm_id = ""
try:
    with open("/etc/default/pragati-arm") as f:
        for line in f:
            if line.startswith("ARM_ID="):
                arm_id = line.strip().split("=", 1)[1].strip('"').strip("'")
except FileNotFoundError:
    arm_id = os.environ.get("ARM_ID", "")

# Uptime
try:
    with open("/proc/uptime") as f:
        uptime_s = float(f.read().split()[0])
except Exception:
    uptime_s = 0.0

# Boot ID
boot_id = run("journalctl --list-boots -n1 -o json 2>/dev/null | python3 -c \"import json,sys; d=json.loads(sys.stdin.read()); print(d[-1].get('boot_id','') if isinstance(d,list) else d.get('boot_id',''))\" 2>/dev/null")

# ── OS boot timing ──────────────────────────────────────────────────────
boot_time_output = run("systemd-analyze time --no-pager 2>/dev/null")
kernel_s = None
userspace_s = None
total_s = None
boot_finished = False

if "Startup finished" in boot_time_output:
    boot_finished = True
    m = re.search(r'([\d.]+)s \(kernel\)', boot_time_output)
    if m:
        kernel_s = float(m.group(1))
    m = re.search(r'([\d.]+)s \(userspace\)', boot_time_output)
    if m:
        userspace_s = float(m.group(1))
    m = re.search(r'= ([\d.]+)s', boot_time_output)
    if m:
        total_s = float(m.group(1))

# Fallback: if boot hasn't "finished", extract partial data from other sources
if kernel_s is None:
    # Try extracting kernel time from dmesg — look for userspace handoff
    dmesg_line = run("dmesg 2>/dev/null | grep -m1 'Freeing unused kernel'")
    if dmesg_line:
        m = re.match(r'\[\s*([\d.]+)\]', dmesg_line)
        if m:
            kernel_s = float(m.group(1))

if total_s is None:
    # Use /proc/uptime as a proxy — time since kernel start to now
    # This is captured early in the script so is close to boot-complete
    total_s = round(uptime_s, 3) if uptime_s > 0 else None

if userspace_s is None and kernel_s is not None and total_s is not None:
    # Derive userspace as total minus kernel
    userspace_s = round(total_s - kernel_s, 3)

critical_chain = run("systemd-analyze critical-chain --no-pager 2>/dev/null", timeout=30)
blame_full = run("systemd-analyze blame --no-pager 2>/dev/null")

# If boot not finished, record what's blocking
blocking_jobs = ""
if not boot_finished:
    blocking_jobs = run("systemctl list-jobs --no-pager 2>/dev/null")

# Failed services (always capture — not just when boot is unfinished)
failed_units = run("systemctl list-units --state=failed --no-pager --no-legend 2>/dev/null")

# Stuck services (activating state — these may be hung)
activating_units = run("systemctl list-units --state=activating --no-pager --no-legend 2>/dev/null")

# Running process snapshot (top CPU/memory consumers at capture time)
process_list = run(
    "ps aux --sort=-%cpu --no-headers 2>/dev/null | head -25"
)

# ── Service timing ──────────────────────────────────────────────────────
services = {}
svc_list = [launch_svc, "pigpiod.service", "can-watchdog@can0.service",
            "NetworkManager-wait-online.service", "boot_timing.service"]
if role == "vehicle":
    svc_list.append("mosquitto.service")
for svc in svc_list:
    if not svc:
        continue
    active_state = svc_prop(svc, "ActiveState")
    # Skip if service doesn't exist
    load_state = svc_prop(svc, "LoadState")
    if load_state == "not-found":
        continue
    services[svc] = {
        "active_state": active_state or None,
        "inactive_exit_ts": svc_prop(svc, "InactiveExitTimestamp") or None,
        "active_enter_ts": svc_prop(svc, "ActiveEnterTimestamp") or None,
        "exec_main_start_ts": svc_prop(svc, "ExecMainStartTimestamp") or None,
        "exec_main_exit_ts": svc_prop(svc, "ExecMainExitTimestamp") or None,
    }

    # Compute service startup duration if both timestamps available
    ixt = svc_prop(svc, "InactiveExitTimestampMonotonic")
    aet = svc_prop(svc, "ActiveEnterTimestampMonotonic")
    if ixt and aet:
        try:
            duration_us = int(aet) - int(ixt)
            # Guard: skip negative durations (e.g. boot_timing.service measuring itself)
            if duration_us >= 0 and svc != "boot_timing.service":
                services[svc]["startup_duration_s"] = round(duration_us / 1_000_000, 3)
            else:
                services[svc]["startup_duration_s"] = None
        except ValueError:
            pass

# Add launch_status for each launch service (Bug 5: detect failed/inactive services)
launch_status = {}
for svc in [launch_svc]:
    if not svc:
        continue
    is_active = run(f"systemctl is-active {svc} 2>/dev/null").strip()
    launch_status[svc] = is_active or "unknown"
    # Also check sub-result for oneshot services
    exit_code = svc_prop(svc, "ExecMainStatus")
    if exit_code:
        launch_status[f"{svc}_exit_code"] = exit_code

# ── Hardware state ──────────────────────────────────────────────────────
hardware = {}

# 1.7: Memory and swap from /proc/meminfo
try:
    meminfo = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0].rstrip(":")
                meminfo[key] = int(parts[1])  # value in kB
    total_mb = round(meminfo.get("MemTotal", 0) / 1024, 1)
    avail_mb = round(meminfo.get("MemAvailable", 0) / 1024, 1)
    used_mb = round(total_mb - avail_mb, 1)
    hardware["memory_mb"] = {"total": total_mb, "used": used_mb, "available": avail_mb}
    swap_total = round(meminfo.get("SwapTotal", 0) / 1024, 1)
    swap_free = round(meminfo.get("SwapFree", 0) / 1024, 1)
    hardware["swap_mb"] = {"total": swap_total, "used": round(swap_total - swap_free, 1)}
except Exception:
    hardware["memory_mb"] = None
    hardware["swap_mb"] = None

# 1.7: CPU temperature
try:
    with open("/sys/class/thermal/thermal_zone0/temp") as f:
        hardware["cpu_temp_c"] = round(int(f.read().strip()) / 1000, 1)
except Exception:
    hardware["cpu_temp_c"] = None

# 1.8: Disk I/O from /proc/diskstats — auto-detect boot device
root_dev = ""  # initialized here so system_info section can access it
try:
    root_dev = run("lsblk -no PKNAME $(findmnt -n -o SOURCE /) 2>/dev/null").strip()
    if not root_dev:
        # Fallback: try to extract from /proc/cmdline or default
        root_dev = run("lsblk -no PKNAME /dev/$(mountpoint -d / 2>/dev/null | sed 's/:.*//') 2>/dev/null").strip()
    if not root_dev:
        root_dev = "mmcblk0"
    disk_io = None
    with open("/proc/diskstats") as f:
        for line in f:
            fields = line.split()
            if len(fields) >= 14 and fields[2] == root_dev:
                disk_io = {
                    "device": root_dev,
                    "reads_completed": int(fields[3]),
                    "writes_completed": int(fields[7]),
                    "read_sectors": int(fields[5]),
                    "write_sectors": int(fields[9]),
                }
                break
    hardware["disk_io"] = disk_io
except Exception:
    hardware["disk_io"] = None

# 1.9: CAN interface status
try:
    can_json = run("ip -j link show can0 2>/dev/null")
    if can_json:
        import json as _json
        can_data = _json.loads(can_json)
        can_state = can_data[0].get("operstate", "UNKNOWN") if can_data else "UNKNOWN"
        # Get bitrate from detailed output
        can_detail = run("ip -d link show can0 2>/dev/null")
        bitrate = None
        m = re.search(r'bitrate\s+(\d+)', can_detail)
        if m:
            bitrate = int(m.group(1))
        # Get error counters from stats
        can_stats = run("ip -s link show can0 2>/dev/null")
        tx_errors = 0
        rx_errors = 0
        # Parse "TX: ... errors <N>" and "RX: ... errors <N>"
        lines = can_stats.splitlines()
        for i, ln in enumerate(lines):
            if ln.strip().startswith("TX:"):
                # Next line has the values
                if i + 1 < len(lines):
                    vals = lines[i + 1].split()
                    # Format: bytes packets errors dropped carrier collsns
                    if len(vals) >= 3:
                        tx_errors = int(vals[2])
            elif ln.strip().startswith("RX:"):
                if i + 1 < len(lines):
                    vals = lines[i + 1].split()
                    if len(vals) >= 3:
                        rx_errors = int(vals[2])
        hardware["can0"] = {
            "state": can_state,
            "bitrate": bitrate,
            "tx_errors": tx_errors,
            "rx_errors": rx_errors,
        }
    else:
        hardware["can0"] = None
except Exception:
    hardware["can0"] = None

# 1.10: SPI readiness
hardware["spi_ready"] = os.path.exists("/dev/spidev0.1")

# ── Launcher internals ─────────────────────────────────────────────────
launcher_internals = {}
try:
    if role == "arm":
        launcher_msgs = [
            ("launcher_started", "ROS2 ARM Control Launcher Script"),
            ("can_setup_begin", "Setting up CAN interface"),
            ("source_begin", "Sourcing ROS2 environment"),
            ("ros2_launch_invoked", "Starting ROS2 ARM Control"),
        ]
    elif role == "vehicle":
        launcher_msgs = [
            ("launcher_started", "ROS2 Vehicle Launcher Script"),
            ("can_setup_begin", "Setting up CAN interface"),
            ("source_begin", "Sourcing ROS2 environment"),
            ("ros2_launch_invoked", "Starting ROS2 Vehicle Control"),
        ]
    else:
        launcher_msgs = []

    def extract_iso_ts(journal_line):
        """Extract ISO timestamp from journalctl short-iso output."""
        if not journal_line:
            return None
        parts = journal_line.split(" ", 1)
        return parts[0] if parts else None

    for key, msg in launcher_msgs:
        line = run(
            f"journalctl -b -u {launch_svc} --output=short-iso --no-pager 2>/dev/null"
            f" | grep -m1 -F '{msg}'",
            timeout=10,
        )
        launcher_internals[key] = extract_iso_ts(line)

    # Compute pre-launch overhead
    start_ts = launcher_internals.get("launcher_started")
    launch_ts = launcher_internals.get("ros2_launch_invoked")
    if start_ts and launch_ts:
        try:
            t0 = datetime.fromisoformat(start_ts.rstrip())
            t1 = datetime.fromisoformat(launch_ts.rstrip())
            launcher_internals["pre_launch_overhead_s"] = round((t1 - t0).total_seconds(), 3)
        except Exception:
            launcher_internals["pre_launch_overhead_s"] = None
    else:
        launcher_internals["pre_launch_overhead_s"] = None
except Exception:
    launcher_internals = None

# ── ROS2 node milestones ────────────────────────────────────────────────
ros2_milestones = {}
if launch_svc:
    # First log line per known node
    node_names = [
        "robot_state_publisher",
        "joint_state_publisher",
        "mg6010_controller_node",
        "cotton_detection_node",
        "ARM_client",
        "yanthra_move_node",
        "vehicle_control_node",
    ]
    node_first_lines = {}
    for node in node_names:
        line = first_journal_match(launch_svc, f"\\[{node}")
        if line:
            # Extract just the timestamp (first ISO token)
            parts = line.split(" ", 1)
            node_first_lines[node] = parts[0] if parts else line

    ros2_milestones["node_first_log_ts"] = node_first_lines or None

    # Key milestones
    ros2_milestones["mqtt_connected"] = (
        first_journal_match(launch_svc, "MQTT.*connect|Connected to MQTT|on_connect.*connected") or None
    )
    ros2_milestones["motor_homing_done"] = (
        first_journal_match(launch_svc, "Initialization and homing completed|homing completed successfully") or None
    )
    ros2_milestones["first_pick_cycle"] = (
        first_journal_match(launch_svc, "Starting pick cycle|CYCLE.*START|scan_cycle_start") or None
    )
    ros2_milestones["arm_status_ready"] = (
        first_journal_match(launch_svc, "ARM STATUS.*ready|arm status.*ready|ARM_STATUS.*ready") or None
    )
    # Use tail -1 to get the LAST "Initialized" line (e.g. "3/3" not "0/3")
    motors_init_line = run(
        f"journalctl -b -u {launch_svc} --no-pager -o short-iso 2>/dev/null"
        f" | grep -iE 'Initialized.*motors' | tail -1",
        timeout=10,
    )
    ros2_milestones["motors_initialized"] = motors_init_line or None
    ros2_milestones["depthai_pipeline_ready"] = (
        first_journal_match(launch_svc, "Pipeline ready") or None
    )
    ros2_milestones["arm_service_available"] = (
        first_journal_match(launch_svc, "Arm status service is available") or None
    )

    # 1.14: Vehicle-specific milestones
    if role == "vehicle":
        vehicle_msgs = [
            ("odrive_ready", "ODrive service node started successfully"),
            ("mqtt_connected_vehicle", "MQTT Connected to broker"),
            ("mqtt_bridge_running", "Vehicle MQTT Bridge is running"),
            ("vehicle_control_initialized", "ROS2 Vehicle Control Node initialized"),
        ]
        for key, msg in vehicle_msgs:
            line = run(
                f"journalctl -b -u {launch_svc} --output=short-iso --no-pager 2>/dev/null"
                f" | grep -m1 -F '{msg}'",
                timeout=10,
            )
            if line:
                parts = line.split(" ", 1)
                ros2_milestones[key] = parts[0] if parts else None
            else:
                ros2_milestones[key] = None

        # Self-test result: capture whichever occurs first (PASSED or ISSUES DETECTED)
        self_test_passed = run(
            f"journalctl -b -u {launch_svc} --output=short-iso --no-pager 2>/dev/null"
            f" | grep -m1 -F 'STARTUP SELF-TEST: PASSED'",
            timeout=10,
        )
        self_test_issues = run(
            f"journalctl -b -u {launch_svc} --output=short-iso --no-pager 2>/dev/null"
            f" | grep -m1 -F 'STARTUP SELF-TEST: ISSUES DETECTED'",
            timeout=10,
        )
        if self_test_passed and self_test_issues:
            # Pick whichever timestamp is earlier
            ts_p = self_test_passed.split(" ", 1)[0]
            ts_i = self_test_issues.split(" ", 1)[0]
            try:
                dt_p = datetime.fromisoformat(ts_p)
                dt_i = datetime.fromisoformat(ts_i)
                if dt_p <= dt_i:
                    ros2_milestones["self_test_result"] = {"timestamp": ts_p, "result": "PASSED"}
                else:
                    ros2_milestones["self_test_result"] = {"timestamp": ts_i, "result": "ISSUES DETECTED"}
            except Exception:
                ros2_milestones["self_test_result"] = {"timestamp": ts_p, "result": "PASSED"}
        elif self_test_passed:
            ts_p = self_test_passed.split(" ", 1)[0]
            ros2_milestones["self_test_result"] = {"timestamp": ts_p, "result": "PASSED"}
        elif self_test_issues:
            ts_i = self_test_issues.split(" ", 1)[0]
            ros2_milestones["self_test_result"] = {"timestamp": ts_i, "result": "ISSUES DETECTED"}
        else:
            ros2_milestones["self_test_result"] = None

    # 1.15: Per-motor homing capture (ARM role)
    if role == "arm":
        motor_homing = []
        for joint_num in [3, 4, 5]:
            joint_label = f"joint {joint_num}"
            homing_entry = {"joint": f"joint{joint_num}", "start": None, "end": None, "duration_s": None}
            try:
                # Actual journal format has emoji prefixes:
                #   "🔄 Homing Sequence: Starting homing for joint 3"
                #   "✅ Homing sequence completed for joint 3"
                # Use substring matching that works regardless of emoji prefix
                start_line = run(
                    f"journalctl -b -u {launch_svc} --output=short-iso --no-pager 2>/dev/null"
                    f" | grep -m1 'Starting homing for {joint_label}'",
                    timeout=10,
                )
                end_line = run(
                    f"journalctl -b -u {launch_svc} --output=short-iso --no-pager 2>/dev/null"
                    f" | grep -m1 'Homing sequence completed for {joint_label}'",
                    timeout=10,
                )
                if start_line:
                    homing_entry["start"] = start_line.split(" ", 1)[0]
                if end_line:
                    homing_entry["end"] = end_line.split(" ", 1)[0]
                if homing_entry["start"] and homing_entry["end"]:
                    try:
                        t0 = datetime.fromisoformat(homing_entry["start"])
                        t1 = datetime.fromisoformat(homing_entry["end"])
                        homing_entry["duration_s"] = round((t1 - t0).total_seconds(), 3)
                    except Exception:
                        pass
            except Exception:
                pass
            motor_homing.append(homing_entry)
        ros2_milestones["motor_homing"] = motor_homing

# ── Known delays inventory (static reference data) ─────────────────────
known_delays = None
try:
    if role == "arm":
        known_delays = [
            {"location": "pragati_complete.launch.py", "target": "motor+detection", "delay_s": 0.3, "type": "TimerAction"},
            {"location": "pragati_complete.launch.py", "target": "ARM_client", "delay_s": 5.0, "type": "TimerAction"},
            {"location": "pragati_complete.launch.py", "target": "yanthra_move", "delay_s": 7.0, "type": "TimerAction"},
            {"location": "arm_launch.service", "target": "ExecStartPre", "delay_s": 1.0, "type": "blind_sleep"},
            {"location": "mg6010_controller_node.cpp", "target": "zero_position_per_motor", "delay_s": 2.0, "type": "homing_sleep"},
            {"location": "mg6010_controller_node.cpp", "target": "verify_per_motor", "delay_s": 0.2, "type": "homing_sleep"},
            {"location": "mg6010_controller_node.cpp", "target": "final_position_per_motor", "delay_s": 3.0, "type": "homing_sleep"},
            {"location": "gpio_control_functions.cpp:269", "target": "led_blink", "delay_s": 3.0, "type": "hardware_init"},
            {"location": "yanthra_move_system_hardware.cpp:122", "target": "hardware_init", "delay_s": 1.0, "type": "hardware_init"},
            {"location": "cotton_detection_node_depthai.cpp:116", "target": "camera_warmup", "delay_s": 1.0, "type": "software_init"},
        ]
    elif role == "vehicle":
        known_delays = [
            {"location": "vehicle_complete.launch.py", "target": "motor+odrive", "delay_s": 0.3, "type": "TimerAction"},
            {"location": "vehicle_complete.launch.py", "target": "mqtt_bridge", "delay_s": 5.0, "type": "TimerAction"},
            {"location": "vehicle_complete.launch.py", "target": "vehicle_control", "delay_s": 25.0, "type": "TimerAction"},
            {"location": "vehicle_launch.service", "target": "ExecStartPre", "delay_s": 1.0, "type": "blind_sleep"},
            {"location": "vehicle_mqtt_bridge.py:360", "target": "startup_sleep", "delay_s": 2.0, "type": "software_init"},
            {"location": "odrive_service_node.cpp:269", "target": "can_stabilization", "delay_s": 0.5, "type": "hardware_init"},
        ]
except Exception:
    known_delays = None

# ── System info collection ──────────────────────────────────────────────
system_info = {}
system_info["os_version"] = run("lsb_release -ds 2>/dev/null") or run("grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '\"'") or None
system_info["kernel_version"] = run("uname -r") or None

# Boot media type detection (uses same root_dev detected in disk_io section)
boot_device = root_dev if root_dev else "unknown"
system_info["boot_device"] = boot_device
if boot_device.startswith("mmcblk"):
    system_info["boot_media_type"] = "sd"
elif boot_device.startswith("sd") or boot_device.startswith("nvme"):
    system_info["boot_media_type"] = "usb_ssd"
else:
    system_info["boot_media_type"] = "unknown"

system_info["systemd_default_target"] = run("systemctl get-default 2>/dev/null") or None
try:
    with open("/sys/devices/system/cpu/cpufreq/policy0/scaling_governor") as f:
        system_info["cpu_governor"] = f.read().strip()
except Exception:
    system_info["cpu_governor"] = None

# dtoverlay/dtparam config from boot config
dt_config = run("grep -E '^(dtoverlay|dtparam)' /boot/firmware/config.txt 2>/dev/null")
system_info["dtoverlay_config"] = dt_config or None

# Total RAM in MB (already parsed in hardware section)
try:
    system_info["total_ram_mb"] = total_mb
except NameError:
    system_info["total_ram_mb"] = None

system_info["hostname"] = hostname
snap_count_raw = run("snap list 2>/dev/null | tail -n +2 | wc -l")
try:
    system_info["snap_count"] = int(snap_count_raw)
except (ValueError, TypeError):
    system_info["snap_count"] = 0

# 1c.9: CPU model and frequency info
# Try x86 style first
cpu_model = run("grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2-").strip()
if not cpu_model:
    # ARM: try 'Model' field (gives "Raspberry Pi 4 Model B Rev 1.5" etc.)
    cpu_model = run("grep -m1 '^Model' /proc/cpuinfo 2>/dev/null | cut -d: -f2-").strip()
if not cpu_model:
    # Fallback: device-tree model
    cpu_model = run("cat /proc/device-tree/model 2>/dev/null").strip().rstrip('\x00')
system_info["cpu_model"] = cpu_model if cpu_model else None
cpu_freq_cur = None
cpu_freq_min = None
cpu_freq_max = None
try:
    with open("/sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq") as f:
        cpu_freq_cur = int(f.read().strip()) // 1000  # kHz to MHz
    with open("/sys/devices/system/cpu/cpufreq/policy0/scaling_min_freq") as f:
        cpu_freq_min = int(f.read().strip()) // 1000
    with open("/sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq") as f:
        cpu_freq_max = int(f.read().strip()) // 1000
except Exception:
    pass
system_info["cpu_freq_mhz"] = {"current": cpu_freq_cur, "min": cpu_freq_min, "max": cpu_freq_max}

# ── Environment context (1c enhancements) ──────────────────────────────

# 1c.1: RPi throttle state (vcgencmd get_throttled)
# Bit field: under-voltage, freq capped, throttled, soft temp limit
throttle_raw = run("vcgencmd get_throttled 2>/dev/null")
throttle_hex = None
if throttle_raw and "=" in throttle_raw:
    throttle_hex = throttle_raw.split("=", 1)[1].strip()

# 1c.2: Disk free space
disk_free_raw = run("df -h / 2>/dev/null | tail -1")
disk_free = None
if disk_free_raw:
    cols = disk_free_raw.split()
    if len(cols) >= 6:
        disk_free = {
            "filesystem": cols[0],
            "size": cols[1],
            "used": cols[2],
            "available": cols[3],
            "use_percent": cols[4],
            "mount": cols[5],
        }

# 1c.3: USB device listing
usb_devices_raw = run("lsusb 2>/dev/null")
usb_devices = usb_devices_raw.splitlines() if usb_devices_raw else []

# 1c.4: Network interface state
net_interfaces_raw = run("ip -brief addr show 2>/dev/null")
net_interfaces = net_interfaces_raw.splitlines() if net_interfaces_raw else []

# 1c.5: ROS2 environment variables
# The boot_timing.service runs as user ubuntu but doesn't source ROS2 setup,
# so env vars like ROS_DOMAIN_ID, AMENT_PREFIX_PATH etc. won't be set in os.environ.
# Source the setup files first, then capture the relevant vars.
ros2_env = {}
ros2_env_output = run("bash -c 'source /opt/ros/jazzy/setup.bash 2>/dev/null; source /home/ubuntu/pragati_ws/install/setup.bash 2>/dev/null; source $HOME/pragati_ros2/install/setup.bash 2>/dev/null; env | grep -E \"^(ROS_|AMENT_|COLCON_|PYTHONPATH|LD_LIBRARY)\"' 2>/dev/null")
if ros2_env_output:
    for line in ros2_env_output.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            ros2_env[k] = v

# 1c.6: Journal boot errors (priority err and above)
journal_errors_raw = run("journalctl -b -p err --no-pager -o short 2>/dev/null", timeout=15)
journal_errors = journal_errors_raw.splitlines() if journal_errors_raw else []
# Cap at 100 lines to avoid bloating JSON
if len(journal_errors) > 100:
    journal_errors = journal_errors[:100] + [f"... truncated ({len(journal_errors)} total lines)"]

# 1c.7: dmesg warnings/errors
dmesg_errors_raw = run("dmesg --level=warn,err,crit,alert,emerg --no-pager 2>/dev/null || sudo dmesg -l warn,err 2>/dev/null", timeout=15)
dmesg_errors = dmesg_errors_raw.splitlines() if dmesg_errors_raw else []
# Cap at last 50 lines to keep JSON size reasonable
if len(dmesg_errors) > 50:
    dmesg_errors = dmesg_errors[-50:]
    dmesg_errors.insert(0, f"... showing last 50 of {len(dmesg_errors) + 50} total lines")

# 1c.8: Key package versions
packages = {}
pkg_list = [
    ("depthai", "python3 -c 'import depthai; print(depthai.__version__)' 2>/dev/null"),
    ("pigpio_apt", "dpkg-query -W -f='${Version}' pigpio 2>/dev/null"),
    ("pigpio_python", "python3 -c 'import pigpio; print(pigpio.__version__ if hasattr(pigpio, \"__version__\") else \"installed\")' 2>/dev/null"),
    ("ros_jazzy_ros2launch", "dpkg-query -W -f='${Version}' ros-jazzy-ros2launch 2>/dev/null"),
    ("ros_jazzy_rclcpp", "dpkg-query -W -f='${Version}' ros-jazzy-rclcpp 2>/dev/null"),
    ("ros_jazzy_rclpy", "dpkg-query -W -f='${Version}' ros-jazzy-rclpy 2>/dev/null"),
    ("mosquitto", "dpkg-query -W -f='${Version}' mosquitto 2>/dev/null"),
    ("python3", "python3 --version 2>/dev/null"),
]
for name, cmd in pkg_list:
    ver = run(cmd)
    packages[name] = ver if ver else None

# 1c.10: Kernel modules
lsmod_raw = run("lsmod 2>/dev/null")
kernel_modules = lsmod_raw.splitlines() if lsmod_raw else []

# 1c.11: All enabled systemd services (needs longer timeout — slow on loaded systems)
# NOTE: Always produces a list (possibly empty []), never None.
# Using "if enabled_services else None" here caused a bug where the vehicle's
# empty result (from timeout) became null in JSON, breaking fleet drift comparison.
enabled_services_raw = run("systemctl list-unit-files --state=enabled --type=service --no-pager --no-legend 2>/dev/null", timeout=30)
enabled_services = []
if enabled_services_raw:
    for line in enabled_services_raw.splitlines():
        parts = line.split()
        if parts:
            enabled_services.append(parts[0])

# 1c.12: Full /boot/firmware/config.txt content
boot_config_raw = None
for cfg_path in ["/boot/firmware/config.txt", "/boot/config.txt"]:
    try:
        with open(cfg_path) as f:
            boot_config_raw = f.read().strip()
        break
    except FileNotFoundError:
        continue

# 1c.13: Kernel OOM events check
oom_events_raw = run("dmesg 2>/dev/null | grep -i 'Out of memory\\|oom-killer\\|oom_reaper'", timeout=10)
oom_events = oom_events_raw.splitlines() if oom_events_raw else []

# 1c.14: ROS2 workspace packages listing
ros2_packages = None
workspace_share = os.path.expanduser("~/pragati_ros2/install/share")
if os.path.isdir(workspace_share):
    try:
        ros2_packages = sorted([
            d for d in os.listdir(workspace_share)
            if os.path.isdir(os.path.join(workspace_share, d))
            and not d.startswith(".")
        ])
    except Exception:
        ros2_packages = None

# 1c.16: Full package inventory for cross-RPi comparison
apt_packages = None
try:
    apt_raw = run("dpkg-query -W -f='${Package}=${Version}\\n' 2>/dev/null", timeout=30)
    apt_packages = sorted(apt_raw.strip().splitlines()) if apt_raw and apt_raw.strip() else None
except Exception:
    pass

pip_packages = None
try:
    pip_raw = run("pip3 list --format=freeze 2>/dev/null", timeout=15)
    pip_packages = sorted(pip_raw.strip().splitlines()) if pip_raw and pip_raw.strip() else None
except Exception:
    pass

snap_list = []
try:
    snap_raw = run("snap list --color=never 2>/dev/null", timeout=10)
    if snap_raw and snap_raw.strip():
        lines = snap_raw.strip().splitlines()
        # Skip header line ("Name  Version  Rev  ...")
        snap_list = lines[1:] if len(lines) > 1 else []
except Exception:
    pass

python_version = run("python3 --version 2>/dev/null") or None
if python_version:
    python_version = python_version.strip()

# ── Assemble and write ──────────────────────────────────────────────────
data = {
    "schema_version": "v5",
    "captured_at": captured_at,
    "boot_id": boot_id or None,
    "hostname": hostname,
    "role": role,
    "arm_id": arm_id or None,
    "uptime_s": round(uptime_s, 1),
    "system_info": system_info,
    "os_boot": {
        "finished": boot_finished,
        "kernel_s": kernel_s,
        "userspace_s": userspace_s,
        "total_s": total_s,
        "critical_chain": critical_chain or None,
        "blame": blame_full or None,
        "blocking_jobs": blocking_jobs or None,
        "failed_units": failed_units or None,
        "activating_units": activating_units or None,
    },
    "services": services,
    "launch_status": launch_status,
    "hardware": hardware,
    "process_snapshot": process_list or None,
    "launcher_internals": launcher_internals,
    "node_milestones": ros2_milestones,
    "known_delays": known_delays,
    "environment": {
        "throttle_state": throttle_hex,
        "disk_free": disk_free,
        "usb_devices": usb_devices,
        "network_interfaces": net_interfaces,
        "ros2_env": ros2_env if ros2_env else None,
        "journal_boot_errors": journal_errors if journal_errors else None,
        "dmesg_warnings_errors": dmesg_errors if dmesg_errors else None,
        "key_packages": packages if packages else None,
        "kernel_modules": kernel_modules if kernel_modules else None,
        "enabled_services": enabled_services,
        "boot_firmware_config": boot_config_raw,
        "oom_events": oom_events if oom_events else None,
        "ros2_workspace_packages": ros2_packages,
        "apt_packages": apt_packages,
        "pip_packages": pip_packages,
        "snap_list": snap_list,
        "python_version": python_version,
    },
}

outfile = os.environ["OUTPUT_FILE"]
with open(outfile, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")

print(f"Boot timing captured -> {outfile}")
PYEOF

echo "Done: ${OUTPUT_FILE}"
