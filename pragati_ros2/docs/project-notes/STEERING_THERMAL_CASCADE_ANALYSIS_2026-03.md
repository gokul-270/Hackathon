# Steering Motor Thermal Cascade — Root Cause Analysis (February 2026 Field Trial)

**Date:** March 2026
**Incident:** Feb 26, 2026 field trial — steering motor overheating across 3 sessions
**Log source:** `collected_logs/2026-02-26_16-21/target/` (vehicle RPi pragati11)
**Updated:** March 15, 2026 — corrected after deeper investigation (see Section 9)

---

## 1. Executive Summary

Steering motors (steering_left, steering_right, steering_front) experienced a progressive
thermal cascade across 3+ sessions on Feb 26, 2026 (13:29–14:15). The root cause is a
**combination of hardware/mechanical and software factors**:

- **Hardware:** The steering mechanism appears to have had physical resistance preventing
  wheel movement. The 1:300 gear ratio may NOT be self-locking (needs verification),
  requiring continuous holding current even when stationary.
- **Software (3 bugs):** (1) No motor_stop sent on position timeout — motor keeps pushing
  against obstruction indefinitely; (2) No motor_stop/clear_errors on node restart — new
  session inherits stuck motor state from previous session; (3) Init sequence sends motor_on
  before clear_errors, failing to reset error state.
- **Software (design):** 50Hz redundant command spam from joystick polling loop with no
  command deduplication.

Session 1 had virtually NO steering movement — the wheels were physically not turning.
The heat buildup was from holding current and pushing against mechanical resistance, not
from active steering.

---

## 2. Timeline — Multi-Session Thermal Cascade

### Session 1 (~13:29 – ~13:59, ~30 min)

| Metric | Value |
|--------|-------|
| steering_left commands received | **0** (zero commands) |
| steering_right commands received | **0** (zero commands) |
| steering_front commands received | 2,409 (mostly target 0.0000 = center) |
| Joystick steering input | 4 brief moments (~2 sec each) in 14 minutes |
| steering_left temp | 40°C → 43-44°C (idle holding current only, 0.03-0.08A) |
| steering_right temp | 42°C → 45-46°C (idle holding current only) |
| steering_front temp | 38°C → 51-52°C (3.32A peak, mostly holding at center) |
| User behavior | Pressed START 4 times in quick succession (~13:36-13:38) |

**Key insight:** Session 1 was NOT actively steering. The START button presses suggest the
operator thought the system wasn't responding and kept retrying. The heat buildup was
entirely from holding current, not from steering movement.

### Session 2 (~14:00 – ~14:10, ~10 min)

| Metric | Value |
|--------|-------|
| steering_left start state | 69-76°C, err_flags:8 (carried from Session 1) |
| steering_left commands | Zero — yet drew 3.8A continuous |
| steering_left peak temp | 80°C |
| steering_right temp | 52°C → 68°C |
| Init behavior | motor_on sent BEFORE clear_errors — error state not properly reset |

**Critical:** Session 2 started with steering_left in error state from Session 1. The init
sequence sent `motor_on` before `clear_errors`, so the firmware's active position target
from Session 1 was never cancelled. The motor continued pushing at 3.8A despite zero new
commands.

### Session 3 (~14:11 – ~14:15, ~3.8 min)

| Metric | Value |
|--------|-------|
| ALL three motors | Cascaded — err_flags:8 |
| steering_left | Started at 76°C, err_flags:8 immediately |
| steering_right | 65°C → tripped at 14:13 |
| steering_front | 55°C → 62°C → tripped at 14:14 |
| Current draws | 5.6–7.1A (higher than previous sessions) |
| Session | Abandoned after 3.8 minutes |

---

## 3. Root Causes

### RC-1: Steering wheels physically not turning (HARDWARE)

**Evidence:** Session 1 shows virtually no joystick steering input and only steering_front
received commands (all to center position). The 4 rapid START button presses suggest the
operator observed that steering wasn't responding. Only 313 of 7,577 commands across all
sessions reached their target position (4.1%), consistent with physical obstruction.

**Open question:** Is the 1:300 gear ratio self-locking? If YES, motors could be powered
off safely after reaching position (no backdriving risk). If NO, motors must maintain
holding current to prevent wheel drift. **This needs hardware/mechanical verification
before implementing motor_stop-based fixes.**

### RC-2: No motor_stop on position timeout (SOFTWARE BUG)

When the motor fails to reach its target position within the timeout period, the code
(`mg6010_controller_node.cpp:1818-1830`) logs a warning and clears the `motor_busy_flag_`,
but does NOT send motor_stop (0x81). The motor firmware continues pushing toward the
unreachable target, drawing continuous high current.

**What motor_stop (0x81) actually does:** It is a "hold current position" command — the
motor stays powered and PID stays active, but the active motion target is cleared. The
motor stops trying to reach a position it can't get to and instead holds where it currently
is. This significantly reduces current draw — holding at current position requires far less
current than actively pushing against a mechanical obstruction.

**Important:** 0x81 does NOT reduce power or release the motor. The LK motor firmware has
NO low-power hold mode. Only `motor_off` (0x80) releases torque, which would be dangerous
for gravity-loaded joints.

### RC-3: Broken init sequence on node restart (SOFTWARE BUG)

The init sequence (`mg6010_controller.cpp:170-198`) sends commands in the wrong order:

**Current (broken):**
```
motor_on (0x88) → read status → if error: clear_errors (0x9B) → set initialized=true
```

**Should be:**
```
motor_stop (0x81) → clear_errors (0x9B) → read status → verify clean → motor_on (0x88) → verify active
```

Problems:
1. `motor_on` before `clear_errors` — if motor has leftover thermal error, motor_on may
   fail or be ignored
2. No `motor_stop` first — old position target from previous session remains active in
   firmware
3. No verification after `clear_errors` — assumes errors cleared without checking

### RC-4: Smart polling skips stall detection (SOFTWARE BUG)

When a motor is in "busy" state (actively commanded), the smart polling logic in
`mg6010_controller_node.cpp:2089-2125` skips detailed position checking, missing the
stall condition where the motor is drawing high current but not moving.

### RC-5: 50Hz redundant command spam (SOFTWARE DESIGN)

The joystick polling loop (`vehicle_control_node.py`, `_joystick_loop`) sends commands
continuously even when the joystick is centered (deadband). No command deduplication exists
anywhere in the chain:

- **Source:** `_poll_joystick_blocking()` at line ~2204 sends `_send_steering_command(0.0)`
  on EVERY idle iteration (~20Hz), not just once
- **No deduplication:** `_call_joint_position_command()` at line 1266 always publishes
  regardless of whether target changed
- **Contrast with arm side:** yanthra_move uses event-driven single-command-then-wait,
  NOT continuous polling

**Note:** The refactored vehicle modules in `src/vehicle_control/core/` were designed with
better patterns (event-driven, rate-limited) but are NOT wired into the ROS2 node yet
(3/14 refactoring roadmap steps complete).

### RC-6: No motor_stop/clear_errors on shutdown (SOFTWARE GAP)

Shutdown (`shutdown_handler.cpp`) sends only `motor_off` (0x80) without first sending
`motor_stop` (0x81) or `clear_errors` (0x9B). The next session inherits whatever error
and motion state was present.

---

## 4. Arm Side Comparison

The arm side uses the **same mg6010_controller_node** code. Key differences:

| Aspect | Arm (yanthra_move) | Vehicle (vehicle_control) |
|--------|-------------------|--------------------------|
| Command model | Event-driven, single-command-then-wait | Continuous 50Hz polling loop |
| Motor stop usage | **Never** — no stop commands sent at all | `stop_all_motors()` on idle/error/shutdown transitions |
| Command rate | 10Hz (`control_frequency: 10.0`) | 50Hz (`control_frequency: 50.0`) |
| Thermal derating config | Explicit in `production.yaml` (65°C onset, 85°C limit) | **Not in** `vehicle_motors.yaml` — uses code defaults (same values) |
| Heat issue | Less severe (pick cycles are short, motors not held for 30 min) | Severe (steering holds position for entire session) |

**Important:** Thermal derating is handled at the mg6010_controller_node level (shared
code), NOT at the vehicle_control_node level. Both arm and vehicle get the same derating
behavior. The vehicle doesn't need separate thermal awareness — the motor controller
already has it.

---

## 5. Recommended Fixes (for March 25 field trial)

### Fix 1: Motor init/shutdown sequence fix (HIGH PRIORITY, ~3 hours)

In `mg6010_controller.cpp` `initialize()`:
1. Send `motor_stop` (0x81) first — cancel any active motion from previous session
2. Send `clear_errors` (0x9B) — clear leftover error flags
3. Read status — verify errors actually cleared
4. Send `motor_on` (0x88) — enable motor with clean state
5. Read status — confirm motor is active and healthy

In `shutdown_handler.cpp`:
1. Send `motor_stop` (0x81) before `motor_off` (0x80)
2. Send `clear_errors` (0x9B) after `motor_off` — clean slate for next session

- Risk: LOW — uses existing CAN commands in a better order
- Applies to both arm and vehicle (shared code)

### Fix 2: Motor stop on position timeout (HIGH PRIORITY, ~2 hours)

In `mg6010_controller_node.cpp` position timeout handler (~line 1818-1830):
When timeout fires (motor didn't reach target), send `motor_stop` (0x81) to cancel the
active motion target. This prevents the motor from continuing to push against mechanical
obstruction.

- Risk: LOW — 0x81 holds position, doesn't release torque
- Prevents the thermal cascade root cause

### Fix 3: Command deduplication (~2 hours)

In `vehicle_control_node.py` `_call_joint_position_command()` (~line 1266):
Compare new position against last sent position. Skip publish if within tolerance. This
is where ALL motor commands flow through, so it fixes steering and drive in one place.

- Risk: LOW — one comparison, skips redundant publishes
- Reduces CAN bus traffic by ~96%

### Fix 4: Add thermal_derating section to vehicle_motors.yaml (~30 min)

Make the thermal derating configuration explicit (currently uses code defaults with
identical values). This ensures any future default changes don't silently affect vehicle.

---

## 6. Hardware/Mechanical Investigation Needed

Before implementing motor-stop-based fixes, the following must be verified:

1. **Is the 1:300 gear ratio self-locking?** If the steering gearbox uses planetary gears
   (not self-locking), sending motor_stop followed by motor_off would allow the wheels to
   drift. If worm gears (self-locking), motor_off is safe after reaching position.
2. **What caused the physical steering obstruction in Session 1?** Mechanical binding,
   insufficient torque, linkage issue, or ground friction?
3. **Is holding current expected for the steering mechanism?** How much current is needed
   just to hold the wheels at a position against ground friction forces?

---

## 7. Log Sources

| Source | Path |
|--------|------|
| Vehicle RPi logs | `collected_logs/2026-02-26_16-21/target/` |
| ROS2 motor logs | `ros2_logs/vehicle/` — mg6010_controller_node across 9 launch sessions |
| Vehicle control logs | `ros2_logs/vehicle/` — vehicle_control (python3) logs |
| Field trial session log | `field_trial_logs/session_20260226_132905/vehicle_launch.log` (14MB) |

---

## 8. Owners

| Area | Owner |
|------|-------|
| V6/V7 (steering thermal) | Gokul |
| vehicle_control_node.py | Vehicle control team |
| mg6010_controller_node | Motor control team |
| Hardware/mechanical verification | Gokul / hardware team |

---

## 9. Corrections from Initial Analysis

This document was significantly revised after deeper investigation prompted by review
questions. Key corrections:

1. **Session 1 was NOT actively steering** — initial analysis assumed active steering
   generated heat. Logs show virtually no joystick input and only steering_front received
   commands (to center). Heat was from holding current only.
2. **motor_stop (0x81) does NOT reduce power** — initial analysis assumed stop would
   eliminate holding current. 0x81 holds position with full PID. It DOES help the stuck
   motor case (cancels active motion target), but doesn't reduce idle holding current.
3. **Thermal derating belongs at motor node, not vehicle node** — initial analysis
   recommended adding thermal awareness to vehicle_control_node.py. This is wrong —
   mg6010_controller_node already handles thermal derating for both arm and vehicle.
4. **Both arm and vehicle lack motor_stop** — initial analysis focused on vehicle. Arm side
   also never sends motor_stop after reaching position. Fix should go in the shared
   mg6010_controller code.
5. **Init sequence is the deeper bug** — initial analysis missed that the init order
   (motor_on before clear_errors) caused Session 2 to inherit Session 1's error state.
6. **Hardware/mechanical root cause added** — initial analysis focused purely on software.
   The physical steering obstruction is the primary trigger; software bugs amplified it.

---

## 10. Related Documents

- [Technical Debt Analysis](TECHNICAL_DEBT_ANALYSIS_2026-03-10.md) — TD-VEHICLE-001 through TD-VEHICLE-005
- [Thermal Failure Analysis and Remediation Plan](THERMAL_FAILURE_ANALYSIS_AND_REMEDIATION_PLAN.md) — prior thermal analysis
- [March Field Trial Plan](MARCH_FIELD_TRIAL_PLAN_2026.md) — V6/V7 listed as potential blockers
- [Vehicle Joystick to Motor Command Flow](VEHICLE_JOYSTICK_TO_MOTOR_COMMAND_FLOW_2025-12-19.md) — command flow reference
- [Motor Control Comprehensive Analysis](MOTOR_CONTROL_COMPREHENSIVE_ANALYSIS_2025-11-28.md) — motor firmware behavior
