# Field Trial Metrics Report: 2026-03-25

**Trial Date:** March 25, 2026
**Location:** Machine-1 (3 devices: arm_1, arm_2, vehicle)
**Log Source:** `collected_logs/2026-03-25/machine-1/`

> **Clock Drift Notice:** All afternoon timestamps (after 12:40 lunch shutdown) are ~85 min
> behind actual IST. Morning sessions are accurate. `fake-hwclock` restored stale time on
> reboot; provisioning (which syncs NTP) was not re-run. Within-session durations are
> unaffected since both endpoints share the same drift. The arm_2 session 6 (18:05–18:11)
> was a lab sanity test with NTP-corrected clock. arm_2 session 7 (~14:55–~15:05) is a
> phantom session with drifted clock.

---

## 1. Session Management

### Session Counts

| Device | ROS2 Launch Sessions | App Sessions | Restarts |
|--------|---------------------|-------------|----------|
| arm_1 | 4 | 4 | 3 |
| arm_2 | 7 | 7 | 6 |
| vehicle | 4 | 4 | 3 |
| **Total** | **15** | **15** | **12** |

### Session Timeline

**arm_1** (4 sessions: 1 morning + 3 afternoon) — Morning timestamps are accurate; afternoon sessions drifted ~85 min behind actual IST
| # | Start (log) | Actual Start (est.) | End (log) | Duration | Notes |
|---|-------------|---------------------|-----------|----------|-------|
| 1 | 10:47:28 | — (morning, correct) | 12:39:59 | 112.5 min | Morning session (recovered from journalctl); start switch at 10:49:55, active picking 10:49:56–12:36:21 (~106 min); shutdown via MQTT at 12:39:17 |
| 2 | 12:40:45 | ~14:06 | 13:40:01 | 59.3 min | Normal operation |
| 3 | 13:40:31 | ~15:06 | 14:55:24 | 74.9 min | Ended via shutdown command |
| 4 | 14:56:02 | ~16:21 | 15:00:00 | 4.0 min | Brief final session |

**arm_2** (7 sessions, turbulent) — Sessions 4-5 are afternoon (drifted); session 6 is NTP-corrected (lab); session 7 is a phantom session
| # | Start (log) | Actual Start (est.) | End (log) | Duration | Notes |
|---|-------------|---------------------|-----------|----------|-------|
| 1 | 10:49:45 | — (morning, correct) | 11:10:36 | 20.9 min | Early testing |
| 2 | 11:11:06 | — (morning, correct) | 11:12:38 | 1.5 min | Very short — quick restart |
| 3 | 11:13:08 | — (morning, correct) | 12:39:46 | 86.6 min | Longest session |
| 4 | 12:41:50 | ~14:07 | 13:36:55 | 55.1 min | Normal operation |
| 5 | 13:37:26 | ~15:03 | 14:56:00 | 78.6 min | Normal operation |
| 6 | 18:05:49 | — (NTP-corrected, lab test) | 18:11:06 | 5.3 min | Lab sanity test; YOLOv5 model |
| 7 | 14:55:00 | ~16:20 | ~15:05:00 | ~10 min | Phantom session; 0 picks; yanthra_move shut down mid-session |

**vehicle** (4 sessions) — Sessions 2-4 are afternoon (drifted)
| # | Start (log) | Actual Start (est.) | End (log) | Duration | Notes |
|---|-------------|---------------------|-----------|----------|-------|
| 1 | 10:44:25 | — (morning, correct) | 12:40:40 | 116.2 min | Long morning session |
| 2 | 12:43:57 | ~14:09 | 14:58:43 | 134.8 min | Long afternoon session |
| 3 | 15:00:55 | ~16:26 | 15:03:25 | 2.5 min | Brief final session |
| 4 | 15:11:00 | ~16:36 | ~15:41:00 | ~30 min | E-stop; CAN bus dead; all motors UNAVAILABLE; 0 picks |

### Evidence

- arm_1 launch.log: `ros2_logs/arm1/2026-03-25-{12-40-29,13-40-19,14-55-45}-*/launch.log`; morning session recovered from `collected_logs/2026-03-26/machine-1/arm_1/morning_journal_arm1.txt`
- arm_2 launch.log: `ros2_logs/arm2/2026-03-25-{10-49-31,11-10-54,11-12-55,12-41-32,13-37-13,14-55-53}-*/launch.log`
- vehicle launch.log: `ros2_logs/vehicle/2026-03-25-{10-44-10,12-43-43,15-00-40}-*/launch.log`
- App log timestamps: `app_logs/arm_client_arm1_*.log`, `app_logs/arm_client_arm2_*.log`, `app_logs/vehicle_mqtt_bridge_*.log`

---

## 2. Deployment & Boot

### Provisioning

All 3 devices passed provisioning on first try:

| Device | Steps | Applied | Skipped | Result |
|--------|-------|---------|---------|--------|
| arm_1 | 12/12 | 4 | 8 | OK |
| arm_2 | 12/12 | 4 | 8 | OK |
| vehicle | 15/15 | 7 | 8 | OK |

**Evidence:**
- `arm_1/provision_logs/provision_20260325_104727.log`
- `arm_2/provision_logs/provision_20260325_104514.log`
- `vehicle/provision_logs/provision_20260325_104310.log`

### Boot-to-Ready Timing

⚠️ All afternoon session timestamps below are from drifted clocks (~85 min behind actual IST). Boot *durations* are accurate.

| Device | Session | OS Boot | arm_launch | Motors Init | Arm Ready | Total Boot→Ready |
|--------|---------|---------|------------|-------------|-----------|-----------------|
| arm_1 | 2 (12:40 log / ~14:06 actual) | 30.25s | 1.15s | 12:40:47 | 12:40:48 | ~31s |
| arm_1 | 4 (14:55 log / ~16:21 actual) | 29.39s | 1.29s | 14:56:04 | 14:56:05 | ~31s |
| arm_2 | 4 (12:41 log / ~14:07 actual) | 80.0s* | 1.19s | — | — | >80s |
| arm_2 | 6 (18:05, NTP-corrected) | 28.11s | 1.09s | 18:05:51 | 18:05:52 | ~29s |
| vehicle | 2 (12:42 log / ~14:08 actual) | 54.4s | — | — | — | ~55s |
| vehicle | 3 (14:59 log / ~16:25 actual) | 52.6s | — | — | — | ~53s |

*arm_2 session 4 boot had `NetworkManager-wait-online.service` FAILED (60s timeout), inflating boot time. The service is non-critical.

**Vehicle boots slower than arms:** ~53s vs ~30s due to vehicle running more services (15 provisioning steps vs 12).

**Evidence:**
- `arm_1/app_logs/boot_timing_20260325_124052.json` (lines 27-37: os_boot)
- `arm_1/app_logs/boot_timing_20260325_145609.json` (lines 27-37: os_boot, lines 118-133: milestones)
- `arm_2/app_logs/boot_timing_20260325_124118.json` (lines 27-37: os_boot; line 35: NM failed)
- `arm_2/app_logs/boot_timing_20260325_180606.json` (os_boot 28.11s)
- `vehicle/app_logs/boot_timing_20260325_124244.json` (os_boot 54.4s)
- `vehicle/app_logs/boot_timing_20260325_145947.json` (os_boot 52.6s)

### arm_2 Session 5→6 Gap & Model Switch

arm_2's last ROS2 launch directory was created at drifted `14:55:53` (actual ~16:21), but processes didn't start until NTP-corrected `18:05:43`. The **apparent 3hr 10min gap in log timestamps** is misleading — it is an artifact of the clock jumping forward when NTP corrected the time after reboot on WiFi. The actual gap was **~1h 45min**: field wrap-up (~16:21 actual), transport from field to lab, lab setup, WiFi connection (triggering NTP sync), then lab sanity test at 18:05.

The boot_timing at 18:06 shows a fresh OS boot (uptime 70.1s), confirming a **full system reboot** at the lab (not a power cycle in the field).

After reboot, the model switched from `yolov112.blob` (YOLOv11, 2-class) to `best_openvino_2022.1_6shave.blob` (YOLOv5, 1-class). The launch command shows `depthai_num_classes:=1` instead of `2`.

**Evidence:**
- arm_2 launch.log session 6: `ros2_logs/arm2/2026-03-25-14-55-53-*/launch.log` (timestamps show gap)
- `arm_2/app_logs/boot_timing_20260325_180606.json` (uptime_s: 70.1, confirming fresh boot)
- `arm_2/field_trial_logs/session_20260325_145543/arm_client.log` (model: `best_openvino_2022.1_6shave.blob`)
- `arm_2/app_logs/boot_timing_20260325_124118.json` line 110 (process snapshot shows `depthai_model_path:=.../best_openvino_2022.1_6shave.blob depthai_num_classes:=1`)

---

## 3. Operator Interventions

### Identified Interventions

| Time (log) | Actual Time (est.) | Device | Type | Evidence |
|------------|-------------------|--------|------|----------|
| ~11:10 | ~11:10 (morning, correct) | arm_2 | Restart | Session 1→2 transition (30s gap) |
| ~11:12 | ~11:12 (morning, correct) | arm_2 | Restart | Session 2→3 transition (30s gap, session 2 only 1.5min) |
| ~12:40 | ~14:06 | arm_2 | Lunch shutdown / afternoon reboot | Session 3→4 transition; `fake-hwclock` restored stale 12:40 time |
| ~12:40 | ~14:06 | arm_1 | Afternoon restart (after morning session) | arm_1's morning session (10:47:28–12:39:59) recovered from journalctl (`collected_logs/2026-03-26/machine-1/arm_1/morning_journal_arm1.txt`). Morning data now incorporated. WATCHDOG at 10:47 shows no MQTT for 17h+ (arm_1 running since previous day but disconnected from broker). Shutdown via MQTT at 12:39:17. |
| ~13:37 | ~15:03 | arm_2 | Restart | Session 4→5 (mg6010/yanthra_move exited cleanly first) |
| ~13:40 | ~15:06 | arm_1 | Restart | Session 2→3 (clean disconnect from MQTT first) |
| ~14:55 | ~16:20 | all | Coordinated restart / field wrap-up | All 3 devices restarted within ~2min window |
| ~14:55–18:05 | ~16:20–18:05 | arm_2 | Transport + lab reboot | Session 5 ended at field wrap-up (~16:20 actual). arm_2 transported to lab, rebooted on WiFi (NTP corrected clock), lab sanity test at 18:05. Not a power cycle — gap is transport + setup time. |

### Process Clean Exits (Graceful Shutdowns)

| Device | Session | Process | Indicates |
|--------|---------|---------|-----------|
| arm_2 | 3 (11:12) | mg6010_controller_node, yanthra_move_node | Graceful arm shutdown |
| arm_2 | 5 (13:37) | mg6010_controller_node, yanthra_move_node | Graceful arm shutdown |
| vehicle | 1 (10:44) | vehicle_control_node | vehicle_control exited, other nodes continued |
| vehicle | 2 (12:43) | vehicle_control_node | vehicle_control exited, other nodes continued |

**Evidence:**
- arm_2 session 3 launch.log: `mg6010_controller_node-3: process has finished cleanly [pid 28361]`, `yanthra_move_node-6: process has finished cleanly [pid 28488]`
- arm_2 session 5 launch.log: similar clean exits for pids 21414, 21546
- vehicle session 1 launch.log: `vehicle_control_node-4: process has finished cleanly [pid 11988]`
- vehicle session 2 launch.log: `vehicle_control_node-4: process has finished cleanly [pid 3332]`

**No node crashes detected.** No `process has died`, `SIGSEGV`, `SIGKILL`, or non-zero return codes found in any launch.log.

---

## 4. Tooling Effectiveness

### Field Trial Manager Monitoring Tools

| Tool | arm_1 | arm_2 | vehicle | Status |
|------|-------|-------|---------|--------|
| **fix_verification.log** | Active | Active | Active | **Working** — found CAN watchdog MISSING on multiple devices |
| **can_stats.log** | 1081+ lines | Active | Active | **Working** — 60s sampling interval |
| **process_memory.log** | 133-162 lines | Active | Active | **Working** |
| **disk_monitor.log** | 166-172 lines | Active | Active | **Working** |
| **ethtool_stats.log** | 3136 lines (s2), 112 (s4) | 3024 lines (s4), 224 (s6) | 3136 lines (s1), 112 (s3) | **Working** — NIC stats collected |
| **network_monitor.log** | HEADER ONLY | HEADER ONLY | HEADER ONLY | **BROKEN** — never collected any data |
| **mosquitto_broker.log** | 2 lines | 2 lines | 2 lines | **Minimal** — only systemd start/started |
| **dmesg_network.log** | 0 lines | 107/51 lines | 0 lines | **Partial** — only arm_2 captured dmesg output |
| **vehicle_launch.log** | N/A | N/A | 620,521 / 7,242 lines | **Working** — but session 1 is excessively large |

### Fix Verification Findings

CAN watchdog was found **MISSING** on:
- arm_1 (all sessions)
- arm_2 (session starting 12:41)
- vehicle (all sessions)

**Evidence:** `*/field_trial_logs/*/fix_verification.log` across all devices

### Tooling Gaps

1. **network_monitor.log is completely non-functional** — header written but no data collected on any device, any session. This tool needs investigation/repair.
2. **mosquitto_broker.log captures nothing useful** — only 2 systemd lines per session. Should capture broker stats (connections, messages, errors).
3. **dmesg_network.log inconsistent** — works on arm_2 but produces 0 lines on arm_1 and vehicle. Likely a permissions issue (`sudo dmesg` requires password on some devices).
4. **vehicle_launch.log session 1 is 620K lines** — suggests stdout/stderr from vehicle ROS2 nodes is being captured verbatim (including the ~30K odrive errors). Needs log rotation or filtering.

---

## 5. Uptime & Reliability

### Per-Device Uptime

| Device | Active Time | Wall Clock | Sessions | Uptime % | Longest Session |
|--------|------------|------------|----------|----------|-----------------|
| arm_1 | 250.6 min (4.2h) | ~338 min (5.6h)§ | 4 | 74.1%§ | 112.5 min |
| arm_2 | 257.9 min (4.3h) | 441.3 min (7.4h)† | 7 | 58.5%† | 86.6 min |
| vehicle | 283.5 min (4.7h) | 289.0 min (4.8h)‡ | 4 | 98.1% | 134.8 min |
| **Total** | **792.1 min (13.2h)** | — | **15** | — | — |

§arm_1 wall clock: spans from morning 10:47:28 (accurate) to drifted afternoon 15:00:00 (actual ~16:25 IST), giving ~338 min actual span. The ~85 min lunch/reboot gap between morning session end (12:39:59) and afternoon restart (~14:06 actual) is included in the denominator. Excluding this gap, arm_1 operational uptime was ~99% (250.6 / 253 min).

†arm_2 wall clock: The 441.3 min (7.4h) span from morning 10:49 to NTP-corrected 18:11 is numerically correct (morning timestamps are accurate and session 6 is NTP-corrected). However, arm_2 was NOT running continuously — the ~1h 45min transport gap (field to lab) is included in the denominator. The 58.5% uptime figure is therefore unfairly deflated; excluding the ~105 min transport gap, arm_2 operational uptime was ~77% (or ~96% excluding both transport and lunch shutdown). Session 7 (~10 min, phantom session with 0 picks) is included in active time.

‡vehicle wall clock: The logged span is 10:44 to drifted 15:41 (Session 4 end), but actual end time was ~17:06 IST. Real wall clock span is ~6.4 hours (382 min). Uptime % against actual wall clock: 283.5/382 = ~74.2%. Session 4 (~30 min, E-stop / CAN bus dead, 0 picks) is included in active time.

### Error Rates (per device-hour)

| Device | Node | Session | Errors/hr | Warns/hr | Primary Error Type |
|--------|------|---------|-----------|----------|-------------------|
| **vehicle** | odrive_service_node | S2 (2.25h) | **13,024** | 129 | ODrive motor errors (0x00000100, 0x04000000) |
| **vehicle** | odrive_service_node | S1 (1.94h) | 267 | 103 | Same error codes, lower rate |
| **vehicle** | mg6010_controller_node | S1 (1.94h) | 705 | 2,852 | Steering stalls (steering_front: 98%) |
| **vehicle** | mg6010_controller_node | S2 (2.25h) | 745 | 2,349 | Steering stalls |
| **vehicle** | vehicle_control_node | S1/S2 | 8-10 | 308-357 | — |
| **arm_1** | all nodes | all (4 sessions) | ~2 | ~370 | Morning: 6 errors, 1325 warns in 1.9h; Afternoon: joint command rejections (WARN) |
| **arm_2** | cotton_detection | S3 (1.4h) | 3 | — | Camera USB disconnect at 12:22 — XLink error, 17.1s detection downtime |
| **arm_2** | yanthra_move | S3 (1.4h) | — | 473 | Joint4 action REJECTED/failed |

### Error Characterization

**ODrive Errors (vehicle, 29,260 in session 2):**
- `0x00000100`: 24,099 occurrences — all 3 drive motors (front, left_back, right_back)
- `0x04000000`: 4,883 occurrences — primarily drive_right_back
- `0x00001000`: 37 occurrences
- `0x42000000`: 6 occurrences
- `0x00001100`: 4 occurrences
- These errors trigger `ERROR_STATE` transitions repeatedly. The 50ms polling interval with 3 motors means ~60 error log lines per second during fault conditions.

**MG6010 Steering Stalls (vehicle, ~1,500/session):**
- 98% from `steering_front` motor
- Pattern: current exceeds 6.40A threshold with near-zero position delta → stall detection → zero current command
- Typical stall current: 6.5-14.7A
- This suggests the front steering motor encounters persistent mechanical resistance

**Arm Warnings (arm_1/arm_2):**
- `joint_position_command action: REJECTED` — motor already has active command (timing overlap)
- Collision interlock disabled warnings (expected, per configuration)
- arm_2 session 3: joint4 actions repeatedly rejected/failed — possible motor or encoder issue

### Application-Level Reliability

**Zero application-level errors** across all app logs (arm_client, vehicle_mqtt_bridge) for all sessions on all devices. The application layer (Python MQTT bridges) was completely stable.

**Evidence:**
- All `arm_client_arm*.log` and `vehicle_mqtt_bridge_*.log` files — grep for ERROR returns 0 matches
- All ROS2 node log files in `ros2_logs/` directories

---

## 6. Communication (MQTT)

### Message Volume

| Device | Direction | Total Messages | Sessions |
|--------|-----------|---------------|----------|
| arm_1 | Publish (ArmStatus) | 3,744 | 1187 + 1170 + 1331 + 56 |
| arm_2 | Publish (ArmStatus) | 4,589 | 354 + 33 + 1638 + 1113 + 1380 + 71 |
| vehicle | Receive (ArmStatus) | 7,926 | 3580 + 4274 + 72 |
| **Total** | — | **~8,300** | — |

arm_1 + arm_2 published 8,333 messages; vehicle received 7,926. The difference reflects vehicle not receiving all arm_1 morning messages (arm_1 morning session had 0 MQTT disconnections but vehicle may not have been subscribed for the full duration), plus timing of connection/disconnection and possible retained messages.

### MQTT Disconnections

| Device | Session | Time (log) | Actual Time (est.) | Type | Code | Cause |
|--------|---------|------------|-------------------|------|------|-------|
| vehicle | 1 | 12:40:18 | ~14:06 | Unexpected | 7 | Keepalive timeout |
| vehicle | 2 | 14:58:15 | ~16:23 | Unexpected | 7 | Keepalive timeout |
| arm_1 | 4 | — | — | Unexpected | 7 | After vehicle shutdown_switch |
| arm_1 | 2 | 13:40:00 | ~15:05 | Clean | 0 | Session end |
| arm_2 | 5 | 14:55:51 | ~16:21 | Unexpected | 7 | Keepalive timeout |
| arm_2 | 7 | 18:15:29 | — (lab test) | Unexpected | 7 | Keepalive timeout |
| arm_2 | various | various | various | Clean | 0 | Session transitions |

**5 unexpected disconnections** (code=7, keepalive timeout) across the entire trial. The original 3 occurred near session boundaries (system shutdown side effect). The 2 newly identified disconnects: arm_1 S4 was triggered after the vehicle shutdown_switch event; arm_2 S7 was a keepalive timeout at 18:15:29 during a lab test. arm_1's morning session had 0 MQTT disconnections.

### MQTT Message Rate

- arm_1 morning (112.5 min): 1187 msgs → **10.6 msg/min** (~1 every 6s)
- arm_1 session 2 (59.3 min): 1170 msgs → **19.7 msg/min** (~1 every 3s)
- arm_1 session 3 (74.9 min): 1331 msgs → **17.8 msg/min**
- arm_2 session 3 (86.6 min): 1638 msgs → **18.9 msg/min**
- Afternoon sessions show consistent ~18-20 msg/min rate; arm_1 morning session was lower at ~10.6 msg/min

**Evidence:**
- `arm_1/app_logs/arm_client_arm1_*.log` — grep for "Published" or "mqtt" publish lines
- `arm_2/app_logs/arm_client_arm2_*.log` — same
- `vehicle/app_logs/vehicle_mqtt_bridge_*.log` — grep for "ArmStatus" receive lines

---

## 7. Data Collection

### Storage Summary

| Device | Total Size | Images | ROS2 Logs | App Logs | Other |
|--------|-----------|--------|-----------|----------|-------|
| arm_1 | 176 MB† | 165 MB | ~8 MB | ~1 MB | ~2 MB |
| arm_2 | 294 MB | 257 MB | ~30 MB | ~2 MB | ~5 MB |
| vehicle | 684 MB | 0 MB | ~140 MB | ~1 MB | ~543 MB* |
| **Total** | **1.15 GB†** | **422 MB** | **~178 MB** | **~4 MB** | **~550 MB** |

†arm_1 storage reflects only the collected log files on disk. The morning session's 858 detection images and 853 output images were recovered from journalctl and are not included in the on-disk storage totals.

*Vehicle "other" is dominated by the 1.6M-line syslog (from field_trial_logs) and 620K-line vehicle_launch.log.

### Image Collection

| Device | Input Images | Output Images | Delta | Notes |
|--------|-------------|---------------|-------|-------|
| arm_1 | 2,077 | 2,067 | -10 | Morning: 858 input / 853 output; Afternoon: 1,219 input / 1,214 output |
| arm_2 | 2,047 | 2,046 | -1 | Near-perfect processing |
| **Total** | **4,124** | **4,113** | **-11** | **99.7% image processing rate** |

### Image Collection Rate

- arm_1: 2,077 images / 250.6 min = **8.3 images/min**
- arm_2: 2,047 images / 247.9 min = **8.3 images/min**
- Consistent ~8 images/min (one every ~7 seconds); arm_1 morning session: 858 / 112.5 min = 7.6 images/min

### ROS2 Log Volume (vehicle problem)

The vehicle's ROS2 logs are disproportionately large due to the high error rates:
- `odrive_service_node` session 2 log: contains 29,260 ERROR lines
- `mg6010_controller_node` sessions: ~1,500 ERROR + ~5,400 WARN lines each
- `vehicle_launch.log` session 1: 620,521 lines

This creates a data collection problem: vehicle ROS2 logs are ~35x larger per hour than arm logs.

### Model Configuration

| Device | Sessions 1-5 Model | Session 6 Model |
|--------|-------------------|-----------------|
| arm_1 | `yolov112.blob` (YOLOv11, 2-class) | — |
| arm_2 | `yolov112.blob` (YOLOv11, 2-class) | `best_openvino_2022.1_6shave.blob` (YOLOv5, 1-class) |

**Evidence:**
- `arm_1/app_logs/arm_client_arm1_*.log` — model path in startup logs
- `arm_2/app_logs/boot_timing_20260325_124118.json` line 110 — process snapshot shows model path
- `arm_2/field_trial_logs/session_20260325_145543/arm_client.log` — confirms YOLOv5 blob loaded

---

## 8. Picking Performance

### Pick Attempts & Success Rate

| Device | Sessions | Pick Attempts | Successful | Failed | Success Rate |
|--------|----------|--------------|------------|--------|-------------|
| arm_1 | 4 (1 morning + 3 afternoon) | 408 | 214 | 194 | 52.5% |
| arm_2 | 7 | 522 | 278 | 244 | 53.3% |
| **Total** | **15** | **930** | **492** | **438** | **52.9%** |

arm_1 morning session: 223 pick_complete events (100 success, 123 failure, 44.8% success rate).
arm_1 afternoon sessions: 185 pick_complete events.

### Motion Planning Status

| Status | arm_1 Morning | arm_1 Afternoon | arm_2 | Total |
|--------|--------------|----------------|-------|-------|
| OK | 104 (46.6%) | — | — | — |
| COLLISION_BLOCKED | 81 (36.3%) | — | — | 315 (combined) |
| OUT_OF_REACH | 36 (16.1%) | — | — | — |
| JOINT_LIMIT_EXCEEDED | 2 (0.9%) | — | — | — |

arm_1 morning session completed 143 cycles with 223 total pick_complete events.

### Detection Performance

| Device | Detection Requests | With Cotton | Detection Rate |
|--------|-------------------|-------------|---------------|
| arm_1 morning | 858 | 216 | 25.2% |
| arm_1 total | 2,077 | — | — |
| arm_2 total | 2,047 | — | — |

### Camera Health

| Device | Session | Camera Temp | Camera Reconnects |
|--------|---------|------------|-------------------|
| arm_1 | Morning | 66.7°C | 1 |
| arm_2 | S1 (morning) | 62.5°C | 0 |
| arm_2 | S3 (morning) | 66.4°C | **1** (17.1s downtime at 12:22, XLink error) |
| arm_2 | S5 (afternoon) | **69.6°C** | 0 |

### Picking Throughput

- **Total device-hours**: ~13.2h (792.1 min across 15 sessions)
- **Picks per device-hour**: 930 / 13.2 = ~70.5 attempts/hr
- **Successful picks per device-hour**: 492 / 13.2 = ~37.3 picks/hr

---

## Summary of Key Findings

### What Worked Well
1. **Provisioning**: 100% first-try pass rate across all devices
2. **Application layer**: Zero errors in MQTT bridge code across 13.2 hours of operation
3. **arm_1 stability**: 4 sessions (1 morning + 3 afternoon), ~99% operational uptime (excluding lunch gap), consistent behavior
4. **MQTT communication**: Consistent 18-20 msg/min, 5 unexpected disconnects (3 at session boundaries, 2 from log audit: arm_1 S4 post-shutdown, arm_2 S7 lab keepalive timeout)
5. **Image processing**: 99.7% throughput (4,113 of 4,124 processed)
6. **Boot timing**: Arms boot to ready in ~30s, consistent across sessions
7. **Field trial monitoring**: can_stats, process_memory, disk_monitor, ethtool_stats all functional

### What Needs Attention
1. **Vehicle ODrive errors**: 29,260 errors in session 2 (13,024/hr). Error codes 0x00000100 and 0x04000000 dominate — needs hardware investigation
2. **Vehicle steering stalls**: Front steering motor stalling at 6.5-14.7A, 98% of mg6010 errors — mechanical issue
3. **arm_2 instability**: 7 sessions (vs arm_1's 4), including a phantom session 7 (~10 min, 0 picks, yanthra_move died mid-session) and ~1h 45min transport gap from field to lab with model switch
4. **network_monitor.log broken**: Zero data collected on any device — tool needs repair
5. **Vehicle log volume**: 620K-line session logs, 140MB ROS2 logs — needs log rotation/filtering
6. **CAN watchdog missing**: Detected by fix_verification on arm_1, arm_2, and vehicle
7. **mosquitto_broker.log useless**: Only captures systemd start events, not broker metrics
