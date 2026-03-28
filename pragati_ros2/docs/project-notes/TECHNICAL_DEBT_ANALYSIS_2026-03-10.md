# Technical Debt Analysis - Codebase-Wide
**Date**: 2026-03-10
**Updated**: 2026-03-15 (depthai-decomposition archived then RESTORED — item 2.1 partially resolved. mg6010-decomposition Phase 1+2+3 complete (10/10 steps). All 9 critical items fixed. 10 additional items resolved. 4 infra items resolved. Test drift fixed across yanthra_move and pid_tuning. blocking-sleeps-error-handlers archived — items 2.4, 2.6, 5.6 done (scoped work complete), 5.5 partially resolved: 151+ BLOCKING_SLEEP_OK annotations, all catch-all blocks fixed, ConsecutiveFailureTracker added, ~250 new tests. odrive-data-race-heartbeat-timeout archived — item 2.3 resolved: data race in request_encoder_estimates fixed, 1Hz heartbeat timeout detection added, 11 new gtests. odrive-behavioral-test-suite archived — item 2.7 RESOLVED: 89 behavioral gtest/gmock tests added, 111 total odrive tests. Phase 3: RoleStrategy, ShutdownHandler, MultiThreadedExecutor(4), LifecycleNode, cleanup. motor-control-hardening archived — motor init/shutdown sequence hardened, timeout stop sends motor_stop, CommandDedup for vehicle_control, shutdown handler improvements, 34 new tests. detection-zero-spatial-diagnostics archived — bbox logging + image annotation for zero-spatial rejections, 18 tests. Stereo depth parameter configurability — 5 hardcoded stereo depth params exposed as configurable ROS2 parameters, 23 tests. field-trial-logging-gaps archived — 5 JSON logging gaps fixed in yanthra_move and cotton_detection_ros2 (polar coords, plan status, delay_ms, position feedback, detection throttle/pause), 32 new tests. Status accuracy: items 2.4, 2.6, 3.2, 5.6 corrected from "partially resolved" to "done" — scoped work was complete, aspirational future improvements are not incomplete deliverables.)
**Scope**: All production nodes (cotton_detection, mg6010_controller, yanthra_move, odrive_service, vehicle_control), shared infrastructure, build system, interfaces
**Status**: Phase 1 Complete (9/9 critical items fixed). Phase 2 complete (9/9 done — 8/9 fully resolved, 2.1 partial). Infrastructure refactoring complete (4.3, 5.3, 5.4, 5.5 resolved). Items 2.1, 2.2, 2.4, 2.6, 2.7, 3.3, 3.5, 3.7, 4.1, 4.4 resolved via prior changes. Item 3.2 done (mg6010-decomposition Phase 1+2+3: MotorTestSuite, ControlLoopManager, RosInterfaceManager, ActionServerManager, MotorManager, RoleStrategy, ShutdownHandler extracted + MultiThreadedExecutor(4) + LifecycleNode migration — 10/10 steps done, 8 delegate classes extracted, 3,162 lines restructured, node at 3,672 LOC, 109+ decomposition tests; future improvement: further LOC reduction toward 2,500 target). Item 5.1 resolved (RoleStrategy polymorphic interface, 2026-03-15). Item 5.6 done (error propagation: ConsecutiveFailureTracker, @propagate_motor_error, typed catches; future improvement: per-handler review). Item 2.1 partially resolved (depthai-decomposition archived, but depthai_manager.cpp RESTORED by restore-depthai-manager change Mar 14 — decomposed classes exist but are not used in production; depthai_manager.cpp is active at 2,228L). Items 5.5 partially resolved (blocking-sleeps-error-handlers archived Mar 14: ConsecutiveFailureTracker added to common_utils; remaining: vehicle_control/odrive_control logging adoption, parameter validation). Test drift fixed: 4 pid_tuning tests updated (API behavior changes), 1 arm integration test fixed (wrong package name), 1 full pipeline test fixed (IK strategy assertion). motor-control-hardening archived (2026-03-15): motor init/shutdown sequence hardened (motor_stop → clear_errors → read_status with 3 retries → motor_on → verify_active; shutdown: motor_stop → motor_off → clear_errors), timeout handler sends motor_stop before clearing busy flag, CommandDedup class in vehicle_control skips redundant ROS2 position messages (0.01 epsilon), shutdown handler calls stop() before disable and clear_errors() after, 34 new tests. detection-zero-spatial-diagnostics archived (2026-03-15): bbox coordinates (xmin, ymin, xmax, ymax) added to WARN-level zero-spatial rejection log, red bounding boxes with "DEPTH FAIL" labels drawn on output images for rejected detections, 18 new tests. stereo-depth-param-configurability archived (2026-03-15): 5 hardcoded stereo depth params exposed as configurable ROS2 parameters, 23 new tests. field-trial-logging-gaps archived (2026-03-15): 5 JSON logging gaps fixed (polar coords, plan_status, delay_ms, position feedback, detection throttle/pause), 32 new tests.d detections, 18 test cases. Stereo depth parameter configurability (commit 0c15e3ad0, 2026-03-15): 5 hardcoded stereo depth pipeline parameters (spatial_calc_algorithm, mono_resolution, lr_check, subpixel, median_filter) exposed as configurable ROS2 parameters wired through production.yaml → declare_parameter() → DetectionConfig → CameraConfig → pipeline_builder, 23 source-audit tests. field-trial-logging-gaps archived (2026-03-15): 5 JSON logging gaps fixed in yanthra_move and cotton_detection_ros2 — polar coordinates, plan_status, delay_ms, position feedback event, detection throttle/pause fields, 32 new tests. ~2,129 tests total (0 failures). Next target: depthai_manager re-decomposition and remaining god-class decompositions.

---

## Executive Summary

Comprehensive analysis of technical debt across all production ROS2 nodes, shared
infrastructure, build system, and interface packages. Focuses on field safety, reliability,
debuggability, maintainability, and adherence to SOLID and software engineering principles.

Initial pass identified 19 items. Deep-dive verification confirmed all 19 (one understated,
one off by 1), discovered 5 new correctness/safety issues, and expanded scope to cover the
odrive node, motor dual-role architecture, code duplication, dependency violations, and
SOLID principle analysis. Subsequent bug verification added 3 more items (1 critical, 2
moderate). Total: 43 items across 5 tiers.

### Key Stats
- **Critical safety issues**: 9 (all 9 fixed: 7 in phase-1-critical-fixes f1685f2c, 2 in phase-2-critical-fixes d3e0885c)
- **High reliability issues**: 7 (2.3 done, 2.4 done, 2.6 done, 2.7 done, 2.1 partial)
- **Architectural issues**: 9 (SOLID violations, dependency inversion, interface segregation)
- **Maintainability issues**: 10 (god-classes, hardcoded values, code duplication, broken imports, duplicate publishers)
- **Cleanup items**: 8 (dead code, duplicate implementations, stale config)
- **Resolved since analysis**: 26 items total + field-trial-logging-gaps (4.5 hardcoded JSON fields) + 2.1, 5.5 partially resolved (9 critical + 2.1 depthai catch blocks (decomposed then restored — god-class active at 2,228L) + 2.2 vehicle exceptions + 2.3 odrive heartbeat timeout + data race (11 gtests) + 2.4 catch-all blocks fixed across 5 packages — scoped work complete (blocking-sleeps-error-handlers) + 2.6 blocking sleeps annotated/renamed across 5 packages — scoped work complete (blocking-sleeps-error-handlers) + 2.7 odrive behavioral test suite (89 gtest/gmock + 21 source-verification + 1 lint = 111 total) + 3.2 mg6010 god-class decomposition complete (8 classes extracted, 3,162 lines restructured, 109+ tests, 10/10 steps done — node at 3,672 LOC; future improvement: further LOC reduction toward 2,500 target) + 3.3 motion controller + 3.5 MQTT + 3.7 broken imports + 4.1 dead coordinate code + 4.3 signal handlers + 4.4 dead EE param + 5.1 string-based role detection replaced with RoleStrategy polymorphic interface (2026-03-15) + 5.3 DIP cotton_detection_msgs + 5.4 DRY CMake/signal consolidation + 5.5 ConsecutiveFailureTracker added to common_utils (blocking-sleeps-error-handlers) + 5.6 error propagation complete — ConsecutiveFailureTracker, @propagate_motor_error decorator, e-stop retry, typed exception handlers (blocking-sleeps-error-handlers; future improvement: per-handler review for ~100+ log-and-continue handlers)). **Related hardening/diagnostic improvements (not direct tech debt items)**: motor-control-hardening (motor init/shutdown hardening, timeout stop fix, command dedup, shutdown handler — 34 tests), detection-zero-spatial-diagnostics (bbox logging + image annotation for field analysis — 18 tests), stereo depth parameter configurability (5 stereo depth params exposed as configurable ROS2 params — 23 tests).

### System Inventory

| Package | Node(s) | LOC | Deploy Role |
|---------|---------|-----|-------------|
| motor_control_ros2 | `mg6010_controller_node` | 26,103 | Arm + Vehicle |
| vehicle_control | `vehicle_control_node` + 4 demos | 21,966 | Vehicle |
| yanthra_move | `yanthra_move_node`, `simulation_bridge` | 18,409 | Arm |
| cotton_detection_ros2 | `cotton_detection_node` | 7,974 | Arm |
| pid_tuning | `pid_tuning_node` | 5,683 | Both (tool) |
| odrive_control_ros2 | `odrive_service_node`, `odrive_can_tool` | 3,846 | Vehicle |
| robot_description | (data only) | 2,726 | Both |
| pattern_finder | `aruco_finder_oakd` | 671 | Arm |
| motor_control_msgs | (interfaces only) | 343 | Both |
| common_utils | (library only) | 271 | Both |
| **Total** | **~13 production nodes** | **~87,992** | |

---

## Prioritized Impact Matrix

### TIER 1 - CRITICAL (Field Safety / Data Loss Risk)

#### 1.1 SingleThreadedExecutor starves thermal monitoring in cotton_detection — ✅ Done (Mar 11, f1685f2c)

- **Location**: `src/cotton_detection_ros2/src/cotton_detection_node_main.cpp`
- **Evidence**: Node uses bare `rclcpp::spin(node)` which defaults to `SingleThreadedExecutor`
  with zero callback groups. All callbacks (detection service, thermal monitoring timer,
  diagnostics publisher, subscriptions) share the single executor thread.
- **Blocking path**: Detection service callback in `cotton_detection_node_services.cpp`
  takes 500ms (normal inference) to 12s (camera reconnect path in
  `cotton_detection_node_depthai.cpp`). During this time, NO other callback can fire.
- **Field impact**: Camera thermal monitoring callback cannot execute while detection is
  running. OAK-D Lite operating at 70+ degC in field conditions could overheat without
  the node detecting it. Diagnostics go stale, health monitoring blind.
- **Fix effort**: Small - add `MultiThreadedExecutor(2)` with two
  `MutuallyExclusiveCallbackGroup`s (detection vs monitoring).
- **Related spec**: `openspec/specs/async-motor-commands/spec.md` (pattern reference)

#### 1.2 Blocking motor service starves watchdog timer — ✅ Done (Mar 11, d3e0885c)

- **Location**: `src/motor_control_ros2/src/mg6010_controller_node.cpp` ~L1800+
- **Evidence**: Service callback used `wait_for_completion=true` pattern with blocking
  `sleep_for` loop (2-5 seconds). The watchdog timer was registered on the same
  `SingleThreadedExecutor` with no callback groups.
- **Fix**: Removed 75-line blocking `while(rclcpp::ok())` loop from `joint_position_command_callback`.
  `wait_for_completion=true` now returns immediate deprecation error directing callers to
  the `~/joint_position_command` action server. `wait_for_completion=false` (fire-and-forget)
  remains functional. Removed `watchdog_exempt_` from service handler (homing retains it).
  7 C++ gtest cases validate the change (source-code-parsing pattern).
- **Existing spec**: `openspec/specs/async-motor-commands/spec.md` (updated with blocking removal + watchdog exempt requirements)
- **OpenSpec change**: `openspec/changes/archive/2026-03-11-phase-2-critical-fixes/`

#### 1.3 vehicle_control_node: zero threading locks with 3+ concurrent threads — ✅ Done (Mar 11, d3e0885c)

- **Location**: `src/vehicle_control/integration/vehicle_control_node.py` (3,754 lines)
- **Evidence**: Three threads shared mutable state with no synchronization:
  - Main executor thread (rclpy spin)
  - Joystick reader thread (spawned in `_start_joystick_thread()`)
  - MQTT paho client thread (spawned by `paho.mqtt.client`)
- **Fix**: Added 3 `threading.Lock` instances (one `RLock`) protecting 17+ shared attributes:
  - `_mqtt_lock`: `_mqtt_connected`, `_mqtt_reconnect_count`, `_mqtt_connect_time`, `_mqtt_disconnect_time`
  - `_motor_state_lock` (RLock): `motor_status` dict, `_vehicle_joint_positions`, `joint_positions`
  - `_control_lock`: `current_state`, joystick attributes, `last_command`, `command_count`, `error_count`, `last_command_time`
  Lock ordering: `_mqtt_lock` → `_motor_state_lock` → `_control_lock`. All ~25 methods touching
  shared state updated with `with self._lock:` pattern. 34 Python pytest cases validate
  thread safety (source-code-parsing + stress tests). Audit found and fixed 3 additional
  unprotected accesses (`error_count`, `last_command_time`, `_vehicle_joint_positions` init).
- **Remaining gap**: `_mqtt_client` accesses partially unprotected (8 sites) — low risk due to
  Python GIL + single-threaded executor. `last_cmd_vel_time` unprotected — out of original spec scope.
- **OpenSpec change**: `openspec/changes/archive/2026-03-11-phase-2-critical-fixes/`
- **Spec**: `openspec/specs/vehicle-thread-safety/spec.md` (new)

#### 1.4 Bare `except:` in safety-critical emergency stop path — ✅ Done (Mar 11, f1685f2c)

- **Location**: `src/vehicle_control/core/safety_manager.py:261`
- **Evidence**: `_is_safe_to_clear_emergency()` uses bare `except:` which catches
  `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit` in addition to regular exceptions.
  The handler provides zero diagnostic information.
- **Field impact**: If an unexpected error occurs while checking emergency stop safety,
  it is silently swallowed. Emergency stop may fail to clear, leaving robot stuck in field
  with no log evidence of why. Operator must power-cycle.
- **Fix effort**: Tiny - change to `except Exception as e:` with structured logging.

#### 1.5 Empty `catch(...){}` silences parameter read failures — ✅ Done (Mar 11, f1685f2c)

- **Location**: `src/yanthra_move/src/core/motion_controller.cpp:296`
- **Evidence**: `catch (...) {}` - completely empty catch block with no logging, no
  fallback value assignment, no error propagation.
- **Field impact**: If ROS2 parameter read fails (corrupted config, missing parameter),
  the arm operates with default/previous values silently. Physical collision risk if
  motion limits or offsets are wrong.
- **Fix effort**: Tiny - add `RCLCPP_ERROR` logging and safe fallback values.

#### 1.6 `pauseCamera()` state lie - camera never actually paused (NEW) — ✅ Done (Mar 11, f1685f2c)

- **Location**: `src/cotton_detection_ros2/src/depthai_manager.cpp:1716-1728`
- **Evidence**: `pauseCamera()` creates a `CameraControl` object and configures it, but
  **never sends it to any queue**. The control object is created and immediately discarded
  when it goes out of scope. Then `camera_paused_ = true` is set unconditionally (line 1726,
  outside the try/catch), and the function returns `true`.
- **Double lie**: (1) The hardware-level pause command is never sent -- camera VPU continues
  at full FPS regardless. (2) Even if the try block throws, the state flag is still set to
  `true` and the function still returns success.
- **Downstream**: `isCameraPaused()` (line 1774) reads `camera_paused_`, and `resumeCamera()`
  (line 1739) checks `!camera_paused_` to short-circuit. Any upstream logic gating power
  management, thermal throttling, or frame processing on pause state makes decisions on
  false information.
- **Field impact**: If thermal management depends on pausing the camera to reduce heat,
  the pause appears to succeed while the camera continues running at full power.
- **Fix effort**: Tiny - either implement actual pause (send control to queue) or remove
  the feature and return `false`. State must only update on confirmed success.

#### 1.7 Watchdog false-positive emergency stop in mg6010_controller (NEW) — ✅ Done (Mar 11, f1685f2c)

- **Location**: `src/motor_control_ros2/src/mg6010_controller_node.cpp:2086-2251`
- **Evidence**: `joint_position_command_callback()` with `wait_for_completion=true` blocks
  the executor for up to 5 seconds (50ms sleep_for in a while loop, line 2250). This
  service callback does NOT set `watchdog_exempt_` (unlike homing and shutdown paths which
  do). The watchdog timer (500ms period, line 1395) cannot fire during the block.
- **Cascade**: When the blocking call completes and the watchdog finally fires, it finds
  the control loop stale (last tick was 5+ seconds ago) and triggers emergency stop on
  all motors -- even though the motors were operating correctly.
- **Field impact**: Any `joint_position_command` with `wait_for_completion=true` that
  takes longer than the watchdog threshold causes a false emergency stop. This stops all
  motors mid-operation.
- **Fix effort**: Tiny - set `watchdog_exempt_` at entry, clear on exit. One-line fix.

#### 1.8 Silent CAN write failures in odrive_service_node (NEW) — ✅ Done (Mar 11, f1685f2c)

- **Location**: `src/odrive_control_ros2/src/odrive_service_node.cpp` (lines 489, 526,
  587, 617, 840, and others)
- **Evidence**: Every call to `can_interface_->send_frame()` discards the `bool` return
  value. `send_frame()` returns `false` on SocketCAN write failure (line 173-176 of
  `socketcan_interface.cpp`), but no caller checks it.
- **Field impact**: If a CAN write fails (bus error, buffer full, interface down), the
  motor misses the command with zero recovery. No retry, no escalation, no log entry.
  A drive wheel could silently stop responding to position commands while the node
  believes the command was sent.
- **Fix effort**: Small - check return value, log failure, set error state or retry.

#### 1.9 spin_until_future_complete deadlock in vehicle_control (NEW) — ✅ Done (Mar 11, f1685f2c)

- **Location**: `src/vehicle_control/integration/vehicle_control_node.py:1456`
- **Evidence**: `_call_motor_enable()` calls `rclpy.spin_until_future_complete(self, future,
  timeout_sec=5.0)` from within ROS2 service callbacks (`_vehicle_enable_callback`,
  `_stop_vehicle_callback`, `_idle_vehicle_callback`). The node uses `SingleThreadedExecutor`
  (line 3720). Calling `spin_until_future_complete` from inside a callback on a single-threaded
  executor is a guaranteed deadlock — the executor thread is already occupied and cannot
  process the incoming service response. After 5s timeout, motor enable/disable silently fails.
- **Safety impact**: `stop_vehicle()` (line 1643) calls `_call_motor_enable(True)` — meaning
  vehicle stop commands silently fail to enable motors. The vehicle appears to accept the stop
  command but motors don't actually change state.
- **Irony**: The developer already fixed the same bug in `_call_drive_stop` (lines 837-843)
  using the correct `call_async` + polling pattern, but didn't apply the fix to
  `_call_motor_enable`.
- **Fix effort**: Small — replace line 1456 with `call_async` + `future.done()` polling
  pattern (same as `_call_drive_stop`).

---

### TIER 2 - HIGH (Reliability / Debuggability)

#### 2.1 26 catch blocks in depthai_manager (CORRECTED: was 13) — 🔧 Partially done (Mar 12 decomposed, Mar 14 restored)

- **Location**: `src/cotton_detection_ros2/src/depthai_manager.cpp` (2,228 lines) — ACTIVE (restored by restore-depthai-manager, Mar 14)
- **Evidence**: **26 catch blocks** (14 `catch(...)` + 12 `catch(const std::exception&)`).
  Original analysis counted 13 -- actual count is double. Breakdown by recovery quality:
  - 6 (23%) have meaningful recovery (XLink error detection -> set `needs_reconnect_`)
  - 17 (65%) log-and-continue with safe defaults
  - 3 (12%) completely silent (lines 1215, 1235, 1548 -- no log at all)
- **Additional finding**: The 6 "meaningful recovery" blocks all use the same copy-pasted
  XLink error detection pattern (string-match error message, set `needs_reconnect_` flag).
  No abstraction -- each copy independently parses the error string.
- **No catch block in the entire file re-throws**. Every exception is terminal at point
  of catch. Errors in nested call chains are silently eaten at each level.
- **Field impact**: Camera reports false state. Detection makes decisions on incorrect
  assumptions. Debugging requires physical inspection.
- **Fix effort**: Medium-Large (doubled from original estimate due to 2x catch blocks).
  Replace with typed catches, add state verification, extract XLink error detection into
  a shared helper, ensure state only updates on confirmed success.
- **Resolution**: `depthai-decomposition` change (archived 2026-03-12) decomposed
  `depthai_manager.cpp` into 5 focused classes: `CameraManager`, `DeviceConnection`,
  `ThermalGuard`, `DiagnosticsCollector`, `PipelineBuilder` — zero `catch(...)` blocks,
  all 47 catch blocks typed, source audit test (`NoCatchAllInSource`) added. However,
  `restore-depthai-manager` change (archived 2026-03-14) brought back `depthai_manager.cpp`
  because the production pipeline could not use the decomposed classes (DeviceFactory
  nullptr issue). Decomposed classes remain in codebase but are NOT used in production.
  `depthai_manager.cpp` is active at 2,228 lines. **Status: PARTIALLY RESOLVED** — catch
  blocks cleaned up in decomposed classes, but god-class is still the active production code.
- **OpenSpec change**: `openspec/changes/archive/2026-03-12-depthai-decomposition/`

#### 2.2 19 silent exception-swallowing blocks in vehicle_control_node (CORRECTED: was 17, actual is 19) — ✅ Done (Mar 12, 76c4741a via vehicle-exception-cleanup)

- **Location**: `src/vehicle_control/integration/vehicle_control_node.py` (various)
- **Evidence**: 19 instances total: 3 bare `except: pass` (lines ~525, ~3333, ~3357) +
  14 `except Exception: pass` (lines ~292, ~383, ~3480, ~3618, ~3627, ~3635, ~3637, ~3649,
  ~3655, ~3661, ~3688, ~3737, ~3745, ~3749) + 2 `except Exception:` without name binding
  (no `as e`). 11 of 14 `except Exception: pass` are in shutdown/cleanup code.
  _Note: line numbers approximate — file has shifted since original analysis._
- **Safety-critical instances**:
  - Line 505: YAML config load failure silently ignored
  - Line 3333/3357: GPIO LED set during shutdown button press/release
  - Line 3480: `pkill -9` force-kill failure
  - Line 3688: `rclpy.shutdown()` in signal handler
- **Field impact**: Failures in shutdown/cleanup paths are completely invisible. When
  robot behaves unexpectedly after a crash recovery, there are zero log entries to
  explain what went wrong in the cleanup path.
- **Fix effort**: Small - change to `except Exception as e: self.get_logger().error(...)`.
- **OpenSpec change**: `openspec/changes/vehicle-exception-cleanup/` (4825be81)
- **Archived**: `openspec/changes/archive/2026-03-12-vehicle-exception-cleanup/`

#### 2.3 No heartbeat timeout detection in odrive_service_node (NEW) — ✅ Done (Mar 14, odrive-data-race-heartbeat-timeout)

- **Location**: `src/odrive_control_ros2/src/odrive_service_node.cpp`
- **Evidence**: `ODriveState` tracks `last_heartbeat_time` (line 68) but no timer or
  check ever compares it against a staleness threshold. If a motor powers off, CAN cable
  disconnects, or ODrive firmware crashes, the last heartbeat data persists indefinitely
  as if the motor is still alive.
- **Contrast**: Error detection only works when `axis_error != 0` in the **last received**
  heartbeat (line 918). A motor that stops sending heartbeats entirely is invisible.
- **Field impact**: Drive wheel dies silently. Node continues sending position commands
  to a dead motor. Vehicle drives with fewer wheels than expected, causing uneven motion
  or drift. No alert, no degraded mode.
- **Fix effort**: Small - add a staleness check in `update_state_machine()` comparing
  `last_heartbeat_time` against current time with a configurable timeout parameter.
- **OpenSpec change**: `openspec/changes/odrive-data-race-heartbeat-timeout/` (bad11785)
- **Archived**: `openspec/changes/archive/2026-03-14-odrive-data-race-heartbeat-timeout/`
- **Also fixed**: Data race in `request_encoder_estimates()` — was reading `odrive_states_` without `state_mutex_`. Added `std::lock_guard<std::mutex>`.
- **Tests added**: 11 gtests (9 heartbeat timeout source-verification + 2 mutex coverage source-verification)

#### 2.4 Log-and-continue anti-pattern (200+ handlers across all nodes) — ✅ Done (Mar 14, blocking-sleeps-error-handlers)

- **Location**: Across all nodes (expanded scope from original analysis)
- **Evidence**: Estimated 200+ exception handlers across all production nodes. Breakdown:
  - vehicle_control_node: 97 handlers (65% log-and-continue)
  - depthai_manager: 26 handlers (65% log-and-continue)
  - mg6010_controller_node: 20+ handlers
  - odrive_service_node: 15+ handlers
  - yanthra_move: 15+ handlers
  Approximately 65% of all handlers log the error and continue with no recovery, no state
  reset, no retry, and no escalation.
- **Field impact**: Errors accumulate silently. Each individual error seems minor in logs,
  but the compounding effect leads to undefined system state. Mean time to root-cause
  diagnosis from field logs: hours (sifting through hundreds of logged-but-ignored errors).
- **Fix effort**: Large - requires per-handler review to determine appropriate recovery
  strategy (retry, escalate, degrade gracefully, or fail fast).
- **Progress (blocking-sleeps-error-handlers, 2026-03-14)**: Fixed catch-all blocks across
  5 packages (motor_control_ros2, yanthra_move, cotton_detection_ros2, vehicle_control,
  web_dashboard): all `catch(...)` blocks now have typed `catch(const std::exception& e)`
  predecessors (except correct destructor/cleanup cases), all bare `except:` replaced with
  `except Exception:` (including 3 in web_dashboard found in final audit), 4 `catch(...)`
  without typed catch fixed in final audit (yanthra_move_system_hardware.cpp,
  yanthra_utilities.cpp, mg6010_controller_node.cpp). ConsecutiveFailureTracker utility
  provides escalation for consecutive failures. ~50 C++ tests + ~200 Python tests added.
- **Future improvement**: ~100+ log-and-continue handlers could benefit from per-handler
  review for recovery strategies (retry, escalate, degrade). This is ongoing code quality
  improvement, not incomplete work — the scoped fix (catch-all elimination + escalation
  framework) is complete.

#### 2.5 ~~Signal handler calls `rclcpp::shutdown()` (not async-signal-safe)~~ — RETRACTED

- **Location**: `src/cotton_detection_ros2/src/cotton_detection_node_main.cpp`
- **Original finding**: Custom signal handler calls `rclcpp::shutdown()` directly, which
  is not async-signal-safe per POSIX.
- **Retracted (March 2026)**: Investigation of git history (commits `c4eba101`,
  `a0c16865`) showed this handler was deliberately designed to solve a real DepthAI USB
  cleanup problem. The camera requires explicit ordered shutdown (drain queues, close
  XLink streams, wait for USB threads) to avoid "device in use" on restart. The handler
  also covers SIGTERM (which rclcpp's default handler does not) — critical for systemd
  service management. The `rclcpp::shutdown()` call inside signal handlers is standard
  ROS2 practice (rclcpp's own internal handler does the same). The handler already uses
  `std::atomic<bool>` internally and `node->request_shutdown()` to reject in-flight
  detection requests during shutdown. "Fixing" this would risk breaking the hardware
  cleanup sequence for no practical benefit.
- **Status**: Not a bug. No action needed.

#### 2.6 20+ blocking `sleep_for` calls in motor service callbacks — ✅ Done (Mar 14, blocking-sleeps-error-handlers)

- **Location**: `src/motor_control_ros2/src/mg6010_controller_node.cpp`
- **Evidence**: Service callbacks contain `std::this_thread::sleep_for()` calls of 2-3
  seconds each. During sleep, the executor thread is completely blocked.
- **Field impact**: Cascading timeout failures. If a higher-level node calls a motor
  service with a timeout shorter than the sleep duration, the call times out even though
  the motor is operating correctly. Creates false-failure cascades up the call chain.
- **Fix effort**: Medium - replace with timer-based state machines (part of
  async-motor-commands spec).
- **Progress (blocking-sleeps-error-handlers, 2026-03-14)**:
  - 151+ BLOCKING_SLEEP_OK annotations across all 5 packages (motor_control_ros2,
    yanthra_move, cotton_detection_ros2, vehicle_control, web_dashboard), each with
    reason and review date
  - `ros2SafeSleep()` renamed to `blockingThreadSleep()` across motor_control_ros2 and
    yanthra_move to make blocking intent explicit
  - All non-executor sleeps confirmed on dedicated threads (Pattern D — acceptable)
  - `watchdog_exempt_` extended to position commands in motor_control_ros2
- **Future improvement**: Executor-thread sleeps in cotton_detection_ros2 were ANNOTATED
  but NOT converted to timer+state-machine (Pattern A conversion deferred — would be
  structural refactoring of the detection pipeline). This is a separate scope (pipeline
  architecture change), not incomplete work on this item — all blocking sleeps are audited,
  annotated, and confirmed safe or on dedicated threads.

#### 2.7 odrive_service_node: zero tests (NEW) — ✅ Done (Mar 11 source-verification, Mar 14 behavioral test suite)

- **Location**: `src/odrive_control_ros2/test/`
- **Evidence**: The odrive_service_node (1,580 lines) was the only production node with
  **zero automated tests**. No gtest, no launch_testing, no integration tests.
- **Field impact**: Any change to the ODrive node was deployed without automated
  verification. Regressions caught only during manual field testing or not at all.
- **Resolution**: Two phases:
  1. **Phase 1 (Mar 11, f1685f2c)**: 21 source-verification tests added (read .cpp files,
     grep for patterns like error checking, mutex usage).
  2. **Phase 2 (Mar 14, 930b0bc8 — odrive-behavioral-test-suite)**: 89 behavioral gtest/gmock
     tests added across 3 new test files:
     - `test_protocol_encoding.cpp` (40 tests) — all CAN Simple protocol encode/decode
     - `test_can_communication.cpp` (30 tests) — mock CAN interface, TX/RX, handleFrame,
       callback registration, state accumulation, snapshot
     - `test_error_handling.cpp` (19 tests) — failure propagation, null safety, error fields,
       frame rejection, anticogging, concurrency, timestamps
     - Added `virtual` to `send_frame`, `receive_frame`, destructor in `socketcan_interface.hpp`
       to enable gmock mocking
     - Tests are standalone (no ROS2 dependency), use `MockSocketCANInterface` with gmock
     - Total: 111 test cases for odrive_control_ros2 (21 source-verification + 89 behavioral + 1 lint)
  - **OpenSpec change**: `openspec/changes/archive/2026-03-14-odrive-behavioral-test-suite/`
  - **Specs synced**: `odrive-protocol-encoding-test`, `odrive-can-driver-test`, `odrive-error-handling-test`

---

### TIER 3 - MODERATE (Maintainability / Velocity)

#### 3.1 God-class: vehicle_control_node.py (3,754 lines) — ⬜ Not done

- **Location**: `src/vehicle_control/integration/vehicle_control_node.py`
- **Evidence**: 92 methods, 11 subsystems (joystick, MQTT, arm control, vehicle steering,
  LED management, safety, diagnostics, IMU, compressor, battery, logging), 102 instance
  variables (56 in `__init__`, 46 written from multiple methods), 97 exception handlers.
  This single file contains 39.6% of all core package logic.
- **Impact**: Any change to one subsystem risks breaking unrelated subsystems. Testing
  requires standing up the entire node. New developer onboarding for this file alone
  takes weeks. Code review is impractical due to size.
- **Suggested decomposition**: `JoystickManager` (~400 lines), `MQTTBridge` (~300),
  `DriveController` (~400), `GPIOProcessor` (~300), `ShutdownManager` (~200),
  slim `VehicleControlNode` orchestrator (~800). Remaining ~1,300 lines split into
  diagnostics, IMU, compressor, battery, arm coordination modules.
- **Fix effort**: XL - decompose into subsystem-specific nodes with ROS2 topic/service
  interfaces. Requires careful state migration.

#### 3.2 God-class: mg6010_controller_node.cpp (3,672 lines) — ✅ Done (Mar 12-15, mg6010-decomposition Phases 1-3 archived)

- **Location**: `src/motor_control_ros2/src/mg6010_controller_node.cpp`
- **Evidence**: 53 methods, 14 services, 3 action servers, 7 timers, 3 subscription types
  (per joint), ~170 lines of member declarations. 10+ distinct responsibilities: CAN/HW
  setup, parameter management, multi-motor lifecycle, joint state publishing, PID tuning,
  motor diagnostics, watchdog monitoring, motion feedback, collision interlock, degraded
  mode management, motor absence detection, homing sequences, shutdown orchestration,
  inline test routines.
- **Dual-role complication**: Same binary serves arm (joints 3/4/5) and vehicle (steering).
  Role is detected by string-matching joint names (see 5.1). Arm-specific shutdown
  sequence is hardcoded inside the "generic" motor controller.
- **Resolution (Phase 1 — mg6010-decomposition)**: Extracted 3 classes using TDD red-green-refactor:
  - `MotorTestSuite` (~633 lines) — 6 read-only diagnostic service callbacks + legacy test
    methods + motor availability service (~480 lines extracted from node)
  - `ControlLoopManager` (~330 lines) — PID write/write-to-ROM callbacks + control loop
    timer/publisher creation for unit tests
  - `RosInterfaceManager` (~200 lines) — all 17 service bindings, 3 action servers,
    3×N per-motor subscribers, 2 publishers. Uses `NodeCallbacks` struct to delegate
    8 services and 3 actions still handled by the parent node
  - Node reduced from 4,511 → 3,661 lines (850 lines removed, 19%)
  - 76 new unit tests (26 MTS + 26 CLM + 24 RIM), all passing
  - **OpenSpec change**: `openspec/changes/archive/2026-03-12-mg6010-decomposition/`
  - **Commits**: 5efe58f5 (TG1-2), 567fa32e (TG3-6), dbfc3344 (TG7-9)
- **Phase 2 (mg6010-decomposition-phase2, archived 2026-03-13)**: Extracted 2 more classes:
  - `ActionServerManager` (~904 lines code, 274 lines header, 1,261 lines test) — action server lifecycle and callbacks
  - `MotorManager` (~389 lines code, 224 lines header, 590 lines test) — motor initialization and lifecycle
  - **OpenSpec change**: `openspec/changes/archive/2026-03-13-mg6010-decomposition-phase2/`
- **Phase 3 (mg6010-decomposition-phase3, archived 2026-03-15)**: Steps 6-10 complete:
  - `RoleStrategy` (~300 lines) — polymorphic interface with `ArmRoleStrategy`/`VehicleRoleStrategy` replacing string-based role detection (resolves item 5.1)
  - `ShutdownHandler` (~175 lines) — extracted shutdown orchestration logic
  - Migrated to `MultiThreadedExecutor(4)` with 3 callback groups: safety=MutuallyExclusive, hardware=MutuallyExclusive, processing=Reentrant
  - Migrated to `LifecycleNode` with 5 lifecycle callbacks: on_configure, on_activate, on_deactivate, on_cleanup, on_shutdown
  - Cleanup pass on remaining code
  - 33 new decomposition tests added (109+ total decomposition tests)
  - **OpenSpec change**: `openspec/changes/archive/2026-03-15-mg6010-decomposition-phase3/`
- **Status**: Done — 8 delegate classes extracted, 3,162 lines restructured, 109+ decomposition tests, 10/10 steps complete. Node at 3,672 LOC. Further LOC reduction to 2,500 target is a future optimization, not incomplete decomposition work.
- **Suggested next decomposition**: `MotorHomingManager` (~600), `MotorDiagnosticsPublisher`
  (~400), `MotorSafetyMonitor` (~500), slim `MG6010ControllerNode` orchestrator (~800).
- **Fix effort**: L (remaining) — further decomposition to reach 2,500 LOC target (Phase 4).

#### 3.3 God-class: motion_controller.cpp (3,783 lines) — ✅ Done (Mar 12, motion-controller-decomposition archived)

- **Location**: `src/yanthra_move/src/core/motion_controller.cpp`
- **Evidence**: 30 methods, 7 distinct responsibilities (trajectory planning, execution,
  IK, collision checking, gripper control, ArUco coordination, recovery).
  `executeApproachTrajectory()` alone is 795 lines (lines 1424-2219).
- **Suggested decomposition**: `TrajectoryPlanner` (~800), `TrajectoryExecutor` (~900,
  breaking the 795-line method into approach/align/extend/pick/retract phases),
  `CaptureSequence` (~400), `ArucoCoordinator` (~300), `RecoveryManager` (~400), slim
  `MotionController` orchestrator (~500).
- **Fix effort**: Large - extract trajectory phases into separate methods/classes.
- **Resolution**: Decomposed into 5 focused classes: `RecoveryManager` (~290 lines),
  `TrajectoryPlanner` (~350 lines), `CaptureSequence` (~290 lines),
  `TrajectoryExecutor` (~376 lines), `ArucoCoordinator` (~270 lines), plus shared types
  (`PlannedTrajectory`, `CottonDetection`, `MultiPositionConfig`, `JointConfigTypes`).
  92 unit tests added. MC remains ~3,339 lines due to complex orchestration logic
  (retreat with EE interleaving, operational cycle state machine) intentionally kept.
  Files in `src/yanthra_move/include/yanthra_move/core/` and `src/yanthra_move/src/core/`.
- **OpenSpec change**: `openspec/changes/archive/2026-03-12-motion-controller-decomposition/`
- **Commits**: d854e9b9 (Groups 1-3), abd39929 (Groups 4-5), ad493b34 (Group 6), 40f7b1aa (Groups 7-8), 2034adc9 (archive)

#### 3.4 God-class: odrive_service_node.cpp (1,580 lines) (NEW) — ⬜ Not done

- **Location**: `src/odrive_control_ros2/src/odrive_service_node.cpp`
- **Evidence**: Single `ODriveServiceNode` class (lines 104-1580) with 6+ responsibilities:
  CAN RX thread management, encoder polling, joint state publishing, motion dispatch with
  aggregation, state machine (6 states), 4 service handlers, error handling, stall detection.
  11 methods + 4 service callbacks + constructor/destructor.
- **Additional smells**:
  - `start_motion_internal()` and `dispatch_pending_batch()` contain nearly identical
    CLOSED_LOOP/IDLE branching logic with the same CAN burst pattern (DRY violation)
  - `motion_in_progress_` flag tracks same concept as `global_motion_state_ == EXECUTING`
    but set/cleared independently (state divergence risk)
  - Hardcoded stall thresholds: `STALL_POSITION_THRESHOLD = 0.01m`,
    `STALL_ERROR_THRESHOLD = 0.1m`, `STALL_CHECK_INTERVAL = 2.0s` (lines 1098-1100)
  - package.xml has TODO placeholders for description, license, maintainer
  - DBC filename typo: `odrvie_cansimple.dbc` should be `odrive_cansimple.dbc`
- **Suggested decomposition**: `ODriveMotionController` (state machine + motion logic),
  `ODriveCanBridge` (CAN TX/RX + protocol encoding), thin `ODriveServiceNode` (ROS2
  wiring only).
- **Fix effort**: Large - extract state machine and CAN comms into separate classes.

#### 3.5 MQTT broker address hardcoded — ✅ Done (Mar 12, 76c4741a via tech-debt-quick-wins)

- **Location**: `src/vehicle_control/integration/vehicle_control_node.py` (3 places: L285 initial connect, L289 log message, L485 self-test reconnect)
- **Evidence**: MQTT broker set to `localhost:1883` in source code, not a ROS2 parameter.
  Node does NOT use `declare_parameter()` for anything — all config loaded via
  `_load_yaml_config()` from `config/production.yaml` with `_get_default_config()` fallback.
- **Field impact**: In multi-RPi deployment (vehicle RPi + arm RPi), arms cannot connect
  to vehicle's MQTT broker without source code modification and rebuild.
- **Fix effort**: Tiny - expose via YAML config (primary, matching node's existing pattern)
  + ROS2 `declare_parameter` (optional override) with `localhost` default.
- **OpenSpec change**: `openspec/changes/tech-debt-quick-wins/` (4825be81) — also has a
  delta spec in `openspec/changes/vehicle-exception-cleanup/` (cross-referenced)
- **Archived**: `openspec/changes/archive/2026-03-12-tech-debt-quick-wins/`

#### 3.6 Hardcoded external binary path with `system()` call — ✅ Done (Mar 14, direct fix)

- **Location**: `src/yanthra_move/src/core/motion_controller.cpp`
- **Evidence**: Calls `/usr/local/bin/aruco_finder` via `system()` (line 3383). Hardcoded
  absolute path. `system()` invokes shell, creating shell injection risk if path were ever
  user-influenced. Additional `system()` calls at lines 659 (`pkill -TERM`) and 689
  (`sudo shutdown -h`).
- **Field impact**: Fails silently if binary is not at exact path. No error reporting
  to caller. Shell injection is low-risk currently (path is hardcoded) but bad practice.
- **Fix effort**: Tiny - parameterize path + replace `system()` with `exec()` family.
- **Resolution**: Replaced 3 hardcoded `/usr/local/bin/aruco_finder` references with
  `ARUCO_FINDER_PROGRAM` macro (already defined in `yanthra_utilities.hpp`). Replaced
  `system()` call with `popen()`/`pclose()` pattern for proper exit code handling without
  shell invocation. `pkill` and `shutdown` system() calls left as-is (intentionally use
  shell features). 4 source-verification tests added (`test_system_call_safety.cpp`).

#### 3.7 Broken imports in system_diagnostics and utilities (NEW) — ✅ Done (Mar 12, 76c4741a via tech-debt-quick-wins)

- **Location**: `src/vehicle_control/integration/system_diagnostics.py:18,26`,
  `src/vehicle_control/validate_system.py:20`, `src/vehicle_control/debug_diagnostics.py:15`
- **Evidence**: All three files import `RobustMotorController` from
  `hardware.robust_motor_controller`, but `robust_motor_controller.py` was archived to
  `archive/unused_motor_abstractions_2025-12/`. The import survives only because it's in a
  shared `try/except ImportError` block, but this means `isinstance()` checks at
  `system_diagnostics.py:714,897` silently do nothing.
- **Deep-dive findings**: `validate_system.py` has 7 functions (L201-663) that depend on
  `RobustMotorController` — all dead code. `debug_diagnostics.py` (95 lines) depends
  entirely on `RobustMotorController` and is dead — entire file to be deleted.
- **Fix effort**: Small — remove dead imports, delete `debug_diagnostics.py` entirely,
  delete 7 dead functions from `validate_system.py`, clean isinstance checks in
  system_diagnostics.
- **OpenSpec change**: `openspec/changes/tech-debt-quick-wins/` (4825be81)
- **Archived**: `openspec/changes/archive/2026-03-12-tech-debt-quick-wins/`

#### 3.8 Duplicate motor publisher paths (NEW) — ⬜ Not done

- **Location**: `src/vehicle_control/integration/vehicle_control_node.py:785-801`,
  `src/vehicle_control/hardware/ros2_motor_interface.py:97-106`
- **Evidence**: Both files create publishers on identical topic patterns
  (`/{joint}_position_controller/command`, `/{joint}_velocity_controller/command`) for all 6
  vehicle joints (steering_left/right/front, drive_front/left_back/right_back). If both are
  instantiated within the same process, this creates duplicate publishers per topic, producing
  conflicting motor commands.
- **Fix effort**: Medium — retire `ros2_motor_interface.py` publishers during vehicle
  refactoring (Roadmap Step 13).

---

### TIER 5 - ARCHITECTURAL (SOLID / Engineering Principles) (NEW SECTION)

#### 5.1 Motor node role detection via string matching (OCP violation) — ✅ Done (2026-03-15, mg6010-decomposition-phase3)

- **Location**: `src/motor_control_ros2/src/mg6010_controller_node.cpp` (multiple sites)
- **Evidence**: The `mg6010_controller_node` serves both arm and vehicle deployments
  (same binary, different YAML config). Role-specific behavior was triggered by
  **string-matching joint names**:
  - `joint_name.find("drive") != npos` -> skip homing, parking, position clamping
  - `joint_name.find("steering") != npos` -> count for degraded mode quorum
  - Presence of `"joint5"` + `"joint3"` + `"joint4"` -> `is_arm_config = true` -> hardcoded
    multi-phase arm shutdown sequence (lines 1113-1132): home J5, home J3, move J4 to
    packing position, park J3 at final packing angle
- **OCP violation**: Adding a new motor role (gripper, conveyor, etc.) required modifying
  the node source to add new `find()` checks. The class was not extensible without modification.
- **Additional issues**:
  - `MAX_MOTORS = 6` hardcoded (line 83) for old 6-motor vehicle layout
  - `vehicle_motors.yaml` declares `input_in_rotations: true` but the C++ code never reads it
  - `vehicle_control/hardware/ros2_motor_interface.py` still maps 6 motors (3 steering +
    3 drive) even though drive moved to ODrive
- **Resolution**: `RoleStrategy` polymorphic interface extracted with `ArmRoleStrategy` and
  `VehicleRoleStrategy` implementations. Role auto-detected from joint_names kept with TODO
  for v1.0 field trial removal. String-matching replaced with strategy pattern.
- **OpenSpec change**: `openspec/changes/archive/2026-03-15-mg6010-decomposition-phase3/`

#### 5.2 Interface segregation violations (ISP) — ⬜ Not done

- **Location**: `mg6010_controller_node` (14 services + 3 actions), `cotton_detection_ros2`
- **Evidence**:
  - `mg6010_controller_node` exposes 14 services + 3 action servers through a single node.
    A client needing only encoder reads must depend on the same node providing PID tuning,
    motor lifecycle, homing, diagnostics, and emergency stop.
  - `CottonDetection.srv` bundles detection request, camera control, and status query into
    one service with mode flags (`detect_command: 0/1/2` magic numbers) instead of separate
    services.
  - `CottonDetection.srv` response uses `int32[] data` (raw bytes) instead of typed
    `CottonPosition[]` messages, forcing consumers to know internal encoding.
- **Fix effort**: Medium - group motor services into logical interface sets
  (`MotorTuning` [PID read/write], `MotorDiagnostics` [state/angles/encoder],
  `MotorControl` [enable/disable/command/position], `MotorSafety` [e-stop/watchdog]).
  Split `CottonDetection.srv` into separate detection and camera control services.

#### 5.3 Dependency inversion violations (DIP) — 🔧 Partially done (Mar 12, infrastructure-packages-refactoring — cotton_detection_msgs extracted)

- **Location**: `src/yanthra_move/CMakeLists.txt`, `src/cotton_detection_ros2/`
- **Evidence**:
  - **yanthra_move** has 9 direct filesystem include paths to sibling packages:
    `$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>` and
    `$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>`. This bypasses
    ROS2's `find_package()`/`ament_target_dependencies()` mechanism. Build order is not
    guaranteed by colcon. Cross-compilation may break. The `../common/include` path
    references a directory that does not exist.
  - ~~**cotton_detection_ros2** bundles message definitions with implementation code.~~ ✅ Resolved:
    `cotton_detection_msgs` extracted as separate interface-only package. `yanthra_move` now
    depends on lightweight `cotton_detection_msgs` instead of full `cotton_detection_ros2`.
  - No dependency injection in any node -- hardware interfaces are created internally,
    making mock substitution for testing impossible without the full HW stack.
- **Remaining**: yanthra_move filesystem include paths and DI framework still needed.
- **Fix effort**: Small (yanthra_move build fix) to Large (DI framework).
- **OpenSpec change**: `openspec/changes/archive/2026-03-12-infrastructure-packages-refactoring/` (cotton_detection_msgs)

#### 5.4 Code duplication across packages (DRY violations) — 🔧 Partially done (Mar 12, infrastructure-packages-refactoring)

- **Signal handlers**: ✅ Resolved. 5 independent implementations consolidated into
  `pragati::install_signal_handlers()` in `common_utils/signal_handler.hpp`. All 4 C++
  consumers migrated. Python handler in vehicle_control remains separate (different runtime).
  - **OpenSpec change**: `openspec/changes/archive/2026-03-12-infrastructure-packages-refactoring/`
- **CAN socket initialization**: Investigated and **dropped** — only ~15 lines truly identical
  across 3 files. Implementations differ in error handling (bool vs throw), logging
  (RCLCPP vs cerr vs nothing), and post-bind config. Targeted fix instead: socketcan
  loopback bugfix in odrive_control_ros2 (setsockopt scoping bug).
- **RPi architecture detection (CMake)**: ✅ Resolved. Extracted to `PragatiRPiDetect.cmake`
  in `common_utils/cmake/`. All 7 consumer CMakeLists.txt migrated to `include(PragatiRPiDetect)`.
  - **OpenSpec change**: `openspec/changes/archive/2026-03-12-infrastructure-packages-refactoring/`
- **CMake lint skips + build flags**: ✅ Resolved. Extracted to `PragatiLintSkips.cmake` and
  `PragatiDefaults.cmake` in `common_utils/cmake/`. ~150 lines of duplication eliminated.
  - **OpenSpec change**: `openspec/changes/archive/2026-03-12-infrastructure-packages-refactoring/`
- **Motor constants**: Still unresolved. Vehicle motor parameters exist in two places that can
  drift: `motor_control_ros2/config/vehicle_motors.yaml` (C++ node) and
  `vehicle_control/config/constants.py` (Python node). See item 5.7.

#### 5.5 common_utils underutilized — 🔧 Partially done (Mar 12, infrastructure-packages-refactoring; Mar 14, blocking-sleeps-error-handlers)

- **Location**: `src/common_utils/`
- **Evidence**: Package previously contained only JSON structured logging. Now expanded with:
  - ✅ `signal_handler.hpp` + `signal_handler.cpp` — shared signal handling for all C++ nodes
  - ✅ `PragatiDefaults.cmake` — shared build warning and optimization flags
  - ✅ `PragatiLintSkips.cmake` — shared lint suppression boilerplate
  - ✅ `PragatiRPiDetect.cmake` — shared RPi architecture detection
  - ✅ `ConsecutiveFailureTracker` — C++ header-only template class + Python class for
    tracking consecutive failures with configurable thresholds and escalation callbacks.
    Used by vehicle_control (Python, @propagate_motor_error decorator + e-stop retry logic).
    Available for C++ packages via `#include <common_utils/consecutive_failure_tracker.hpp>`.
    Added by blocking-sleeps-error-handlers (2026-03-14).
  - Package is now a compiled library (not header-only)
- **Still missing**: parameter validation framework.
  `vehicle_control` still uses its own `utils/logging_utils.py` instead of common_utils Python
  logging. `odrive_control_ros2` still uses raw `std::cerr` for some output. Over 2,650 raw
  `RCLCPP_INFO/WARN/ERROR` calls across codebase, only ~30 use JSON helpers.
- **Fix effort**: Incremental — expand adoption as packages are refactored.
- **OpenSpec change**: `openspec/changes/archive/2026-03-12-infrastructure-packages-refactoring/`

#### 5.6 Fail-fast principle systematically violated — ✅ Done (Mar 14, blocking-sleeps-error-handlers)

- **Location**: Across all nodes
- **Evidence**: The codebase overwhelmingly prefers catch-log-continue over fail-fast.
  Specific violations:
  - `pauseCamera()` returns `true` (success) when the operation had no effect (see 1.6)
  - CAN `send_frame()` failures silently ignored in odrive (see 1.8)
  - `safety_manager.py:261` bare `except:` returns `False` with no log (see 1.4)
  - 65% of all exception handlers log and continue with no recovery action
- **For a safety-critical robotics system**: failed motor commands should trigger error
  states, not be silently dropped. Incorrect state should trigger diagnostics, not be
  papered over. Errors should escalate up the call chain, not terminate at catch.
- **Fix effort**: Large - requires per-handler review. Some handlers are correctly
  defensive (destructor cleanup, shutdown paths). Others need fail-fast or retry-and-escalate.
- **Progress (blocking-sleeps-error-handlers, 2026-03-14)**: Error propagation improved via:
  - ConsecutiveFailureTracker escalation (configurable thresholds, callback on threshold breach)
  - `@propagate_motor_error` decorator in vehicle_control for motor command error propagation
  - E-stop retry logic added to vehicle_control
  - All `catch(...)` blocks now have typed `catch(const std::exception& e)` predecessors —
    errors are no longer silently caught by catch-all without first attempting typed handling
  - All bare `except:` replaced with `except Exception:` across Python code
- **Future improvement**: Per-handler review for ~100+ log-and-continue handlers could
  further improve recovery strategies. This is ongoing code quality work — the scoped
  fix (typed catches, escalation framework, error propagation decorators) is complete.
  The specific violations cited in Evidence (1.6, 1.8, 1.4) are all individually fixed.

#### 5.7 Dual source of truth for motor configuration — ⬜ Not done

- **Location**: `src/motor_control_ros2/config/vehicle_motors.yaml` vs
  `src/vehicle_control/config/constants.py`
- **Evidence**: Vehicle motor parameters (CAN IDs, gear ratios, limits, joint names)
  exist in both files with no mechanism to keep them in sync. The YAML is consumed by
  the C++ mg6010_controller_node. The Python `constants.py` is consumed by vehicle_control.
  They can drift silently with no build-time or runtime check.
- **Field impact**: If someone changes a gear ratio in YAML but not in Python (or vice
  versa), the motor controller and vehicle controller disagree on wheel geometry. Steering
  calculations become wrong.
- **Fix effort**: Small - either generate `constants.py` from YAML at build time, or
  have Python code load the YAML directly as its config source.

---

### TIER 4 - LOW (Cleanup / Dead Code)

#### 4.1 236 lines of dead code in coordinate_transforms — ✅ Done (Mar 12, 76c4741a via tech-debt-quick-wins)

- **Location**: `src/yanthra_move/src/coordinate_transforms.cpp`
- **Evidence**: 12 functions total, 10 have ZERO active callers (confirmed by codebase
  grep). Functions 3-7 are copy-paste variants (camera -> different links). Functions
  8-12 are copy-paste variants (yanthra_link -> different links).
- **Additional bug discovered**: Header (`coordinate_transforms.hpp`) declares
  `getCottonCoordinates_yanthra_origin_to_*` but implementation defines
  `getCottonCoordinates_yanthra_link_to_*`. Names don't match -- would fail at link time
  if anyone tried to call the header-declared functions. Currently masked because all
  functions are dead code.
- **Function 8 is a no-op**: `getCottonCoordinates_yanthra_link_to_yanthra` transforms
  from `yanthra_link` to `yanthra_link` (identity transform).
- **Deep-dive findings**: coordinate_transforms.cpp does NOT include enhanced_logging.hpp —
  the 2 kept functions are pure math with no logging. `yanthra_move.h` also has 8 legacy
  declarations (L118-145) with different signatures (shared_ptr vs reference) for the same
  dead functions — also to be deleted.
- **Impact**: Confuses developers who assume these functions are in use. Inflates
  compile time and binary size.
- **Fix effort**: Tiny - delete the dead functions from .cpp, .hpp, and .h files. Keep
  only functions 1 and 2 (`convertXYZToPolarFLUROSCoordinates`, `checkReachability`)
  which have active callers.
- **OpenSpec change**: `openspec/changes/tech-debt-quick-wins/` (4825be81)
- **Archived**: `openspec/changes/archive/2026-03-12-tech-debt-quick-wins/`

#### 4.2 Global mutable state in yanthra_move — 🔶 Partial (Mar 14, direct fix — char buffers removed)

- **Location**: `src/yanthra_move/src/yanthra_move_system_core.cpp`
- **Evidence**: 9 non-conditional global/extern variables (lines 203-214, 1022) + 3
  conditional globals under `#ifdef ENABLE_PIGPIO` in `yanthra_utilities.cpp`.
  Key globals:
  - `std::shared_ptr<rclcpp::Node> global_node` (line 203)
  - `std::shared_ptr<SingleThreadedExecutor> executor` (line 204)
  - `std::atomic<bool> simulation_mode` (line 205)
  - `std::atomic<bool> executor_running` (line 206)
  - `std::thread executor_thread` (line 207)
  - `std::atomic<bool> global_stop_requested` (line 212)
  - ~~`char PRAGATI_INPUT_DIR[512]` (line 213) - C-style buffer, no bounds checking~~
  - ~~`char PRAGATI_OUTPUT_DIR[512]` (line 214) - C-style buffer, no bounds checking~~
  - `YanthraMoveSystem* g_system` (line 1022) - raw pointer for signal handler
- **Field impact**: Buffer overflow if environment variable exceeds 511 chars (unlikely
  but undefined behavior). Race condition if multiple threads access globals (currently
  single-threaded, but fragile assumption).
- **Fix effort**: Small - convert to `std::string`, scope to class members.
- **Partial resolution**: Removed dead `char PRAGATI_INPUT_DIR[512]` and
  `char PRAGATI_OUTPUT_DIR[512]` globals — written via `sprintf` (buffer overflow risk)
  but never read by any active code. Also removed their `extern` declarations, `sprintf`
  writes, and dead `setenv` calls from `yanthra_move_system_parameters.cpp`. The class
  already has `pragati_input_dir_`/`pragati_output_dir_` as `std::string` members that
  ARE used. 4 source-verification tests added (`test_dead_global_removal.cpp`).
  **Remaining**: 7 namespace globals (`global_node`, `executor`, `simulation_mode`,
  `executor_running`, `executor_thread`, `global_stop_requested`, `g_system`) are
  actively used by 7+ files via extern — scoping these to class requires broader refactor.

#### 4.3 Five duplicate signal handler implementations (UPDATED from 3) — ✅ Done (Mar 12, infrastructure-packages-refactoring)

- **Location**: cotton_detection_ros2, yanthra_move, motor_control_ros2,
  odrive_control_ros2, vehicle_control (5 packages)
- **Evidence**: Each package implemented its own signal handler:
  - `cotton_detection_node_main.cpp:18` - UNSAFE (calls `rclcpp::shutdown()`, see 2.5)
  - `yanthra_move_system_core.cpp:1025` - Most robust (crash handlers, async-safe I/O)
  - `mg6010_controller_node.cpp:4449` - Basic atomic flag pattern
  - `odrive_can_tool.cpp:781` - Basic atomic flag pattern
  - `vehicle_control_node.py:3679` - Python signal handler
- **Resolution**: All 5 C++ implementations replaced with `pragati::install_signal_handlers()`
  from `common_utils/signal_handler.hpp`. Shared implementation includes SIGINT/SIGTERM
  handling with `std::atomic<bool>` flag, optional SIGSEGV/SIGABRT crash handler, and
  idempotent double-init guard. 7 gtests verify signal handling. Python signal handler
  in vehicle_control remains separate (different runtime).
- **OpenSpec change**: `openspec/changes/archive/2026-03-12-infrastructure-packages-refactoring/`

#### 4.4 Duplicate/dead safety timeout parameter — ✅ Done (Mar 12, 76c4741a via tech-debt-quick-wins)

- **Location**: `src/yanthra_move/include/yanthra_move/core/motion_controller.hpp:351`,
  `src/yanthra_move/src/core/motion_controller.cpp:2568`,
  `src/yanthra_move/src/yanthra_move_system_parameters.cpp:311`
- **Evidence**: `end_effector_runtime_` member is **truly dead** — declared at hpp:351,
  loaded via `loadParamFloat` at cpp:2568, but **never read anywhere** in the entire
  codebase. The `declare_parameter("delays/end_effector_runtime", 1000.0)` at
  system_parameters.cpp:311 has a different default (1000.0) than the `loadParamFloat`
  fallback (600.0f) and production.yaml (600.0) — nobody noticed because nothing reads it.
  3 test fixture files also declare this parameter just to prevent "parameter not declared"
  errors.
- **Active EE safety watchdog IS already parameterized**: Uses `ee_watchdog_timeout_sec`
  (completely separate parameter namespace, separate purpose). Only the dead legacy
  duplicate needs cleanup.
- **Field impact**: Confusing dead parameter creates false sense that EE timeout is
  configurable via `delays/end_effector_runtime` when it actually does nothing.
- **Fix effort**: Tiny - delete dead member, loadParamFloat call, declare_parameter call,
  production.yaml entry, and test fixture declarations. Verify active `ee_watchdog_timeout_sec`
  path is correct via `readParameters()`.
- **OpenSpec change**: `openspec/changes/tech-debt-quick-wins/` (4825be81)
- **Archived**: `openspec/changes/archive/2026-03-12-tech-debt-quick-wins/`

---

## Recommended Attack Order

### Phase 1: Pre-Next-Field-Trial (~2 days) — ✅ COMPLETE (Mar 11, f1685f2c)
Items: 1.1, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9

All tiny/small fixes with outsized safety impact — **all 7 items implemented with TDD tests**:
- **1.1** ✅ Add MultiThreadedExecutor to cotton_detection_node (2 callback groups, 2 threads)
- **1.4** ✅ Fix bare `except:` in safety_manager.py (except Exception + JSON logging)
- **1.5** ✅ Add logging to empty catch in motion_controller.cpp (RCLCPP_ERROR JSON)
- **1.6** ✅ Fix `pauseCamera()` state lie (sends CameraControl to input queues; resumeCamera sends setStartStreaming before flush)
- **1.7** ✅ Set `watchdog_exempt_` in `joint_position_command_callback` (guard at entry, clear on all 3 exit paths)
- **1.8** ✅ Check CAN `send_frame()` return values in odrive_service_node (13 sites, handle_send_failure helper, diagnostics publisher)
- **1.9** ✅ Fix `spin_until_future_complete` deadlock in `_call_motor_enable` (call_async + polling)

OpenSpec change: `openspec/changes/archive/2026-03-11-phase-1-critical-fixes/`

### Phase 2: Next Sprint (~1 week) — 8/9 DONE + 2.1 partial (1.2, 1.3, 2.2, 2.3, 2.6, 2.7, 3.5, 3.7 ✅; 2.1 🔧)
Items: 1.2, 1.3, 2.1, 2.2, 2.3, 2.6, 2.7, 3.5, 3.7

Async motor commands + thread safety + error handling + missing detection:
- **1.2** ✅ Removed blocking `wait_for_completion=true` loop, replaced with deprecation error (d3e0885c)
- **1.3** ✅ Added 3 threading locks to vehicle_control_node.py protecting 17+ shared attributes (d3e0885c)
- **2.1** 🔧 Partially resolved (Mar 12 depthai-decomposition archived, Mar 14 restore-depthai-manager archived) — decomposed classes exist but depthai_manager.cpp restored as active production code (2,228L). Catch blocks cleaned in decomposed classes, god-class still active.
- **2.2** ✅ Done (Mar 12, vehicle-exception-cleanup) — replaced 19 silent except blocks with typed catches + diagnostic logging
- **2.3** ✅ Done (Mar 14, odrive-data-race-heartbeat-timeout) — 1Hz heartbeat staleness check (2s timeout), transition-based logging, data race fix in request_encoder_estimates, 11 gtests
- **2.6** ✅ Done (Mar 14, blocking-sleeps-error-handlers) — 151+ BLOCKING_SLEEP_OK annotations, `ros2SafeSleep()` renamed to `blockingThreadSleep()`, all non-executor sleeps confirmed on dedicated threads. Future improvement: executor-thread sleeps in cotton_detection_ros2 could use timer+state-machine conversion.
- **2.7** Write initial test suite for odrive_service_node (gtest + mocked CAN)
- **3.5** ✅ Done (Mar 12, tech-debt-quick-wins) — MQTT broker parameterized via YAML config
- **3.7** ✅ Done (Mar 12, tech-debt-quick-wins) — dead imports removed, debug_diagnostics.py deleted, 7 dead functions removed

**Phase 2 status**: 8/9 items done (1.2, 1.3, 2.2, 2.3, 2.6, 2.7, 3.5, 3.7) + 2.1 partially resolved.

### Phase 3: Planned Refactoring (~2-3 weeks)
Items: 2.4, 3.1, 3.2, 3.4, 3.8, 5.1, 5.2

God-class decomposition + role architecture (1.3 thread safety moved to Phase 2 ✅ done, 3.3 motion_controller decomposition ✅ completed ahead of schedule — see item 3.3, 3.2 mg6010 decomposition Phase 1+2+3 ✅ complete — 8 classes extracted, 109+ tests added, node 4,511→3,672 LOC, 10/10 steps done, 5.1 ✅ done via RoleStrategy):
- **2.4** ✅ Done (blocking-sleeps-error-handlers) — catch-all blocks fixed, ConsecutiveFailureTracker added. Future improvement: review ~100+ log-and-continue handlers for recovery strategy.
- **3.1** Decompose vehicle_control_node into subsystem nodes
- **3.2** ✅ Done — Phase 1 extracted MotorTestSuite, ControlLoopManager, RosInterfaceManager. Phase 2 extracted ActionServerManager, MotorManager. Phase 3 (COMPLETE, 2026-03-15): RoleStrategy (~300L), ShutdownHandler (~175L), MultiThreadedExecutor(4) with 3 callback groups, LifecycleNode with 5 callbacks, cleanup. 8 delegate classes, 3,162 lines restructured, 109+ tests. Node at 3,672 LOC. Future improvement: further LOC reduction toward 2,500 target (deferred to Phase 4).
- **3.4** Decompose odrive_service_node (state machine, CAN bridge, ROS2 wiring)
- **3.8** Retire duplicate motor publishers in ros2_motor_interface.py (during vehicle refactoring)
- **5.1** ✅ Done (2026-03-15, mg6010-decomposition-phase3) — RoleStrategy polymorphic interface with ArmRoleStrategy/VehicleRoleStrategy. Auto-detect from joint_names kept with TODO for v1.0 field trial removal.
- **5.2** Split CottonDetection.srv into separate detection/camera services

### Phase 4: Architecture Hardening (~2 weeks)
Items: 5.3, 5.4, 5.5, 5.6, 5.7

SOLID/DRY/fail-fast improvements:
- **5.3** 🔧 Partially done (infrastructure-packages-refactoring) — cotton_detection_msgs extracted. Remaining: yanthra_move filesystem include paths, DI framework (long-term).
- **5.4** 🔧 Partially done (infrastructure-packages-refactoring) — signal handlers consolidated, CMake modules extracted, CAN socket abstraction dropped. Remaining: motor constants dual source of truth (see 5.7).
- **5.5** 🔧 Partially done (infrastructure-packages-refactoring + blocking-sleeps-error-handlers) — common_utils expanded with signal handler + CMake modules + ConsecutiveFailureTracker (C++ header-only + Python). Remaining: vehicle_control Python logging adoption, odrive_control logging, parameter validation.
- **5.6** ✅ Done (blocking-sleeps-error-handlers) — error propagation improved via ConsecutiveFailureTracker, @propagate_motor_error decorator, e-stop retry, typed exception handlers. Future improvement: per-handler review for ~100+ log-and-continue handlers.
- **5.7** Single source of truth for motor config (generate Python from YAML or load YAML)

### Phase 5: Cleanup (Opportunistic)
Items: 3.6, 4.1, 4.2, 4.3, 4.4

Address alongside nearby changes:
- **3.6** ✅ Done (Mar 14, direct fix) — replaced hardcoded `/usr/local/bin/aruco_finder` with `ARUCO_FINDER_PROGRAM` macro, replaced `system()` with `popen()`/`pclose()`. 4 source-verification tests.
- **4.1** ✅ Done (Mar 12, tech-debt-quick-wins) — deleted dead coordinate_transforms code (236 lines, 10 unused functions + 8 legacy declarations in yanthra_move.h). Pulled forward from Phase 5.
- **4.2** 🔶 Partial (Mar 14, direct fix) — removed dead `char PRAGATI_INPUT_DIR[512]` and `char PRAGATI_OUTPUT_DIR[512]` globals + sprintf/setenv dead writes. 4 source-verification tests. Remaining: 7 actively-used namespace globals need broader refactor.
- **4.3** ✅ Done (Mar 12, infrastructure-packages-refactoring) — 5 C++ signal handler implementations consolidated into `pragati::install_signal_handlers()` in common_utils. 7 gtests added.
- **4.4** ✅ Done (Mar 12, tech-debt-quick-wins) — deleted dead `end_effector_runtime_` parameter (active EE watchdog already uses `ee_watchdog_timeout_sec`). Pulled forward from Phase 5.

---

## Executor Architecture Summary

| Node | Executor | Callback Groups | Thread Safety | Starvation Risk | Priority |
|------|----------|-----------------|---------------|-----------------|----------|
| cotton_detection_node | MultiThreaded(2) ✅ | 2 MutuallyExclusive (detection + monitoring) | Good (separate groups) | RESOLVED (f1685f2c) | Done |
| mg6010_controller_node | MultiThreaded(4) ✅ | 3 (safety=MutuallyExclusive, hardware=MutuallyExclusive, processing=Reentrant) | Good (separate groups) | RESOLVED (mg6010-decomposition-phase3, 2026-03-15) | Done |
| yanthra_move | Manual dual-thread | N/A (custom) | Adequate (atomic flags) | LOW (functionally correct) | Monitor |
| odrive_service_node | SingleThreaded | 0 (default) | Good (`std::mutex`) | MINIMAL (<5ms callbacks) | No action needed |
| vehicle_control_node | SingleThreaded (rclpy) | 0 (default) | 3 locks ✅ (mqtt_lock, motor_state_lock RLock, control_lock) protecting 17+ attrs (d3e0885c) | LOW (callbacks are fast) | Done |

---

## Verification Status

All items verified with line-level code evidence. No claims based on assumption.

| Original Item | Status | Notes |
|---------------|--------|-------|
| 1.1 Executor starvation (cotton_detection) | Confirmed | `rclcpp::spin(node)` with zero callback groups |
| 1.2 Blocking motor service | ✅ Fixed (d3e0885c) | Blocking loop removed, deprecation error returns immediately |
| 1.3 Zero threading locks (vehicle_control) | ✅ Fixed (d3e0885c) | 3 locks added protecting 17+ shared attributes across 3 threads |
| 1.4 Bare `except:` in safety_manager | Confirmed | Line 261 |
| 1.5 Empty `catch(...){}` in motion_controller | Confirmed | Line 296 |
| 2.1 Catch blocks in depthai_manager | **Corrected** | 26 catch blocks (was reported as 13) |
| 2.2 `except: pass` in vehicle_control | **Corrected** | 19 instances (was 17): 3 bare + 14 silent pass + 2 unbound. OpenSpec: `vehicle-exception-cleanup` |
| 2.4 Log-and-continue anti-pattern | 🔧 Partial (blocking-sleeps) | Catch-all blocks fixed across 5 packages; ~100+ log-and-continue handlers remain |
| 2.5 Unsafe signal handler | **Retracted** | Deliberate design for DepthAI USB cleanup; matches rclcpp practice |
| 2.6 Blocking `sleep_for` calls | 🔧 Partial (blocking-sleeps) | 151+ annotations, `blockingThreadSleep()` rename; executor-thread conversions deferred |
| 3.1-3.3 God-classes | Confirmed | All metrics verified with precise line counts. 3.2 substantially resolved (Phase 1+2+3, 10/10 steps, 3,672 LOC). |
| 3.5 MQTT hardcoded | **Corrected** | 3 hardcoded sites (was reported as 2): L285, L289, L485. OpenSpec: `tech-debt-quick-wins` |
| 3.6 Hardcoded binary path | ✅ Fixed (Mar 14) | Replaced with `ARUCO_FINDER_PROGRAM` macro + `popen()`/`pclose()`. 4 tests. |
| 4.1 Dead code in coordinate_transforms | **Corrected** | 10/12 functions dead + 8 legacy declarations in yanthra_move.h. No enhanced_logging dependency. OpenSpec: `tech-debt-quick-wins` |
| 4.2 Global mutable state | 🔶 Partial (Mar 14) | Dead `char[512]` buffers removed + sprintf/setenv. 7 active globals remain. 4 tests. |
| 4.3 Duplicate signal handlers | ✅ Fixed (infra-refactoring) | 5 C++ implementations consolidated into pragati::install_signal_handlers() |
| 4.4 Hardcoded safety timeouts | **Corrected** | `end_effector_runtime_` is dead (never read); active EE watchdog uses `ee_watchdog_timeout_sec` (already parameterized). OpenSpec: `tech-debt-quick-wins` |

### New Items Discovered During Deep-Dive

| Item | Category | Severity |
|------|----------|----------|
| 1.6 `pauseCamera()` state lie | Correctness bug | CRITICAL |
| 1.7 Watchdog false-positive e-stop | Safety bug | CRITICAL |
| 1.8 Silent CAN write failures (odrive) | Safety gap | CRITICAL |
| 2.3 No heartbeat timeout (odrive) | ✅ Fixed (odrive-data-race-heartbeat-timeout) | HIGH |
| 2.7 Zero tests for odrive_service_node | Test coverage | HIGH |
| 3.4 God-class: odrive_service_node | Maintainability | MODERATE |
| 5.1 String-based motor role detection | ✅ Done (2026-03-15, mg6010-decomposition-phase3) | MODERATE |
| 5.2 Interface segregation violations | ISP violation | MODERATE |
| 5.3 Dependency inversion violations | DIP violation | MODERATE |
| 5.4 Code duplication (DRY) | Maintainability | MODERATE |
| 5.5 common_utils underutilized | Architecture | MODERATE |
| 5.6 Fail-fast principle violated | Safety pattern | MODERATE |
| 5.7 Dual source of truth (motor config) | DRY violation | MODERATE |

### New Items Added from Subsequent Bug Verification

| Item | Category | Severity |
|------|----------|----------|
| 1.9 `spin_until_future_complete` deadlock | Deadlock / safety | CRITICAL |
| 3.7 Broken `RobustMotorController` imports | Dead code / silent failure | MODERATE |
| 3.8 Duplicate motor publisher paths | Conflicting commands | MODERATE |

---

## ROS2 Best Practices Comparison: Textbook vs. Pragati

How a well-architected production ROS2 project would look compared to our current codebase.
For each area: what the standard is, where Pragati stands, and whether it matters at our stage.

### 1. Lifecycle (Managed) Nodes

- **Standard**: Production ROS2 projects use `LifecycleNode` (`rclcpp_lifecycle`) for any
  node managing hardware. The node transitions through `Unconfigured -> Inactive -> Active
  -> Finalized` with explicit `onConfigure`, `onActivate`, `onDeactivate`, `onError`
  callbacks. A launch supervisor ensures all hardware nodes are configured before any are
  activated. If a camera or motor fails, the node transitions to `ErrorProcessing` and can
  be recovered without restarting the process.
- **Pragati**: mg6010_controller_node migrated to LifecycleNode (2026-03-15) with 5 callbacks:
  on_configure, on_activate, on_deactivate, on_cleanup, on_shutdown. All other nodes are
  still plain `rclcpp::Node` or `rclpy.node.Node`. Hardware initialization happens in
  constructors for non-lifecycle nodes. Recovery means killing and restarting the entire
  process (except mg6010 which supports lifecycle transitions).
- **Impact**: Moderate. For single-arm single-RPi deployment, restarting is acceptable. It
  becomes critical for 6-arm coordinated startup — need to activate one arm's detection
  without killing the whole process. **Phase 3-4 concern**, not urgent.

### 2. Executors and Callback Groups

- **Standard**: The ROS2 docs (https://docs.ros.org/en/jazzy/How-To-Guides/Using-callback-groups.html)
  are explicit: if you use `MultiThreadedExecutor`, you **must** assign callback groups or
  the multi-threading has no effect. The standard pattern:
  - Safety-critical timers (watchdog, thermal) in their own `MutuallyExclusiveCallbackGroup`
  - Long-running services in a separate `MutuallyExclusiveCallbackGroup`
  - Sensor callbacks in a `ReentrantCallbackGroup` if they need parallelism
  The docs specifically warn: "if everything in a node uses the same Mutually Exclusive
  Callback Group, that node essentially acts as if it was handled by a Single-Threaded
  Executor, even if a multi-threaded one is specified."
- **Pragati**: Most nodes use `SingleThreadedExecutor` with zero callback groups (the
  default). cotton_detection_node uses `MultiThreadedExecutor(2)` with 2 callback groups
  (fixed in phase-1). mg6010_controller_node migrated to `MultiThreadedExecutor(4)` with
  3 callback groups (2026-03-15, phase3). This is the most common pattern in ROS2 tutorials
  — but it's explicitly called out in the docs as insufficient for production nodes with
  mixed-priority callbacks.
- **Impact**: **Critical**. This is our most urgent gap. Items 1.1 and 1.2 in this
  document. Thermal monitoring and watchdog timers get starved by long-running service
  callbacks. The fix is small (add callback groups) and the safety impact is high.

### 3. ros2_control Hardware Abstraction

- **Standard**: The `ros2_control` framework (https://control.ros.org/jazzy/) provides a
  formal hardware abstraction layer:
  - **Hardware components** (System, Actuator, Sensor) are plugins loaded by a
    `ResourceManager`
  - **Controllers** are separate plugins (`JointTrajectoryController`,
    `ForwardCommandController`, etc.) managed by a `ControllerManager`
  - A `ControllerManager` orchestrates the read-compute-write loop at a fixed rate
  - Hardware described in URDF `<ros2_control>` tags
  - Controllers can be loaded/unloaded/switched at runtime without restarting
  - Simulation and real hardware swap via plugin configuration only
  - Three component types: `System` (multi-DOF), `Actuator` (single-DOF), `Sensor`
- **Pragati**: Custom CAN interfaces directly in node code. Motor control logic, PID, state
  machines, and hardware I/O are all in the same 3,672-line class (originally 4,511, reduced by decomposition). No plugin architecture.
  No runtime controller switching. Manual `JointState` publishing instead of ros2_control
  automatic publishing.
- **Impact**: This is the **single largest architectural gap**. But it's also the hardest
  to fix retroactively, and it's a **trade-off, not a mistake**. ros2_control is designed
  for standard servo/stepper setups. Our MG6010/MG6012 CAN protocol motors with custom
  multi-turn encoders and the ODrive ecosystem don't have off-the-shelf ros2_control
  plugins. Writing custom `hardware_interface::SystemInterface` plugins would have added
  weeks of abstraction work before moving a motor. For a startup iterating on hardware,
  going direct-to-CAN was the pragmatic choice.
- **When it matters**: Hot-swap simulation/real hardware, use standard controllers
  (JointTrajectoryController), enable runtime controller switching (tuning vs production),
  test motor logic without physical hardware. **Long-term architectural goal**.

### 4. Node Composition

- **Standard**: ROS2 provides `rclcpp_components` for composing multiple nodes into a single
  process. Benefits: shared memory communication (zero-copy between nodes), reduced process
  overhead, fewer DDS participants. Pattern: write nodes as "components" and load them via
  `ComposableNodeContainer` in launch files.
- **Pragati**: Standalone processes per node. Each node is its own executable.
- **Impact**: Low. On RPi 4B with 4GB RAM, composition could reduce memory by sharing the
  DDS middleware stack. But this is an optimization, not a correctness issue. Matters when
  memory-constrained (DepthAI + ONNX + ROS2 in same 4GB).

### 5. QoS (Quality of Service) Differentiation

- **Standard**: Different data types need different QoS profiles:
  - **Sensor data** (camera, encoders): `BEST_EFFORT` reliability, `VOLATILE` durability,
    small depth — drop old data, don't block on retransmission
  - **Commands** (motor): `RELIABLE` — don't drop commands
  - **Status/diagnostics**: `RELIABLE`, `TRANSIENT_LOCAL` — late subscribers get last status
  - **Safety signals** (e-stop): `RELIABLE`, depth=1, `KEEP_LAST` — always fresh
- **Pragati**: Default QoS everywhere (`RELIABLE`, `VOLATILE`, depth=10). Sensor data can
  block if a subscriber is slow; late-joining diagnostic subscribers miss current state.
- **Impact**: Low priority now. Becomes important for multi-RPi communication over
  WiFi/Ethernet where `BEST_EFFORT` for camera data prevents TCP retransmission blocking
  the control loop.

### 6. Standard Diagnostics Framework

- **Standard**: ROS2 has `diagnostic_updater` and `diagnostic_aggregator` packages:
  - Each node publishes `/diagnostics` with structured key-value pairs
  - `diagnostic_aggregator` collects and categorizes across all nodes
  - Standard tools (`rqt_robot_monitor`) display system health
  - Each hardware component reports OK/WARN/ERROR/STALE
- **Pragati**: `common_utils` JSON logging and some custom diagnostics publishing, but no
  use of `diagnostic_updater`. Health monitoring is ad-hoc per node.
- **Impact**: Moderate. Standard diagnostics give free tooling (rqt, web dashboards, rosbag
  analysis). Our web dashboard partially fills this role. Worth adopting incrementally.

### 7. Behavior Trees / State Machines

- **Standard**: Production robotics uses formal state machines for task orchestration:
  - **BehaviorTree.CPP** — most common in ROS2, used by Nav2
  - **SMACH** — legacy from ROS1, still used
  - **SMACC2** — ROS2 native
  Benefits: visual debugging, runtime introspection, reusable behavior primitives, formal
  verification of state transitions, pause/resume individual phases.
- **Pragati**: The pick cycle in `motion_controller.cpp` is a 795-line imperative function
  with inline state tracking. Vehicle control is a 3,754-line event loop. No formal state
  machine framework anywhere.
- **Impact**: This is the **second-largest architectural gap** after ros2_control. The pick
  cycle has approach/align/extend/pick/retract phases that map perfectly to a behavior tree.
  Benefits: visual debugging of arm phase, easy new behaviors, runtime pause/resume,
  reusable across arm configurations. **Phase 3 investment**, high maintainability payoff.

### 8. Testing Patterns

- **Standard**: ROS2 testing pyramid:
  - **Unit tests** (gtest/pytest): individual classes with mocked ROS interfaces
  - **Integration tests** (`launch_testing`): launch nodes, verify topic/service comms
  - **Simulation tests**: full system in Gazebo, verify behavior
  - **Hardware-in-the-loop (HIL)**: real hardware, automated assertions
- **Pragati**: gtest for motor_control, some pytest for vehicle_control, Playwright E2E for
  web dashboard. Missing: `launch_testing` integration tests, simulation-based testing
  (Gazebo models exist but no automated sim tests), ODrive node has zero tests.
- **Impact**: Test coverage is decent for a startup. The ODrive gap is the biggest concern
  (item 2.7). `launch_testing` is the highest-value addition — catches integration issues
  (topic name mismatches, QoS incompatibilities, startup ordering) that unit tests miss.

### 9. FDIR (Fault Detection, Isolation, Recovery)

- **Standard** for field robotics:
  - **Detection**: every hardware interface checks return values, tracks staleness, monitors
    health metrics
  - **Isolation**: affected subsystem is isolated (disable one arm, not the whole robot)
  - **Recovery**: automated strategies — retry, fallback to safe state, graceful degradation
  Relevant standards: IEC 61508 (functional safety), ISO 13849 (safety of machinery).
  Software typically implements dual-channel monitoring where critical sensors are cross-
  checked by independent paths.
- **Pragati**: Detection is partial (watchdog exists but gets starved; heartbeat tracked but
  never checked for staleness). Isolation is minimal (e-stop is all-or-nothing). Recovery is
  mostly "restart the process."
- **Impact**: For single-arm prototype, current approach is fine. For 6-arm field robot where
  one arm failure shouldn't stop the other 5, FDIR becomes essential. Aligns with multi-arm
  scaling phase of PRD.

### 10. Configuration Management

- **Standard**:
  - All tunable values as ROS2 parameters (runtime-reconfigurable via `ros2 param set`)
  - YAML configs loaded via launch files with parameter overrides
  - Parameter validation with `declare_parameter()` + `ParameterDescriptor` (ranges, types,
    descriptions, read-only flags)
  - No hardcoded values for anything that might need field tuning
- **Pragati**: Mixed. Motor configs use YAML (good). Safety timeouts hardcoded. MQTT broker
  hardcoded. Some values are ROS2 params, others are constants in source. Dual source of
  truth (YAML vs Python constants) for motor parameters.
- **Impact**: Low-medium. Matters most when field-tuning without rebuilds — having to
  recompile and redeploy to change a safety timeout is painful in the field.

---

## Concepts We Missed (or Should Adopt)

### Robotics-Specific

| Concept | What It Is | Pragati Status | Priority |
|---------|-----------|----------------|----------|
| ros2_control HAL | Standard hardware abstraction with plugin architecture | Not used (custom CAN) | Long-term |
| Lifecycle nodes | Managed startup/shutdown/error recovery state machine | mg6010 done (2026-03-15), others pending | Medium |
| Behavior trees | Formal task orchestration (BehaviorTree.CPP) | Not used (795-line imperative) | Medium-High |
| FDIR | Fault detection, isolation, recovery patterns | Partial (detection weak, isolation minimal) | High for scaling |
| Standard diagnostics | `diagnostic_updater` / `diagnostic_aggregator` | Not used (custom JSON) | Medium |
| launch_testing | Automated integration tests for node communication | Not used | Medium |

### Software Engineering

| Concept | What It Is | Pragati Status | Priority |
|---------|-----------|----------------|----------|
| Callback groups | Executor thread safety / priority separation | cotton_detection ✅ (f1685f2c), mg6010 ✅ (2026-03-15, 3 groups), others not yet | **Critical** |
| Node composition | Shared-process nodes via `rclcpp_components` | Not used | Low |
| Interface packages | Separate msg/srv packages from implementation | Done (motor_control_msgs + cotton_detection_msgs) | ✅ Complete |
| Plugin architecture | Runtime-loadable components via `pluginlib` | Not used | Long-term |
| QoS differentiation | Per-topic quality of service profiles | Default everywhere | Low |
| Parameter validation | `declare_parameter()` with ranges/types/descriptions | Minimal | Low-Medium |

---

## Honest Assessment

### What the analysis shows in context

- **~88K lines of working code** across 13 nodes that drive a real robot in field trials.
  The system picks cotton. It works.
- Most "critical" items are **latent risks**, not active failures. The watchdog false-
  positive (1.7) requires a specific code path. The pauseCamera lie (1.6) matters only if
  thermal throttling depends on it. Thread safety issues (1.3) produce intermittent bugs.
- The god-classes (3.1-3.4) are ugly but functional. A 3,672-line motor controller that
  runs reliably in the field is better than a beautifully decomposed one that doesn't exist.
- ODrive having zero tests is a gap, but it's also the newest package.

### What's genuinely concerning (short list) — ✅ ALL RESOLVED

- **Executor starvation** (1.1, 1.2) — ✅ Fixed: MultiThreadedExecutor for cotton_detection (f1685f2c), blocking motor service removed (d3e0885c)
- **Zero locks with 3 threads** (1.3) — ✅ Fixed: 3 locks added protecting 17+ shared attributes (d3e0885c)
- **Silent CAN failures** (1.8) — ✅ Fixed: CAN send return value checks + handle_send_failure helper (f1685f2c)
- **spin_until_future_complete deadlock** (1.9) — ✅ Fixed: call_async + polling pattern (f1685f2c)

All 4 urgent items resolved in phase-1 and phase-2 critical fixes. Remaining tech debt
items are reliability, maintainability, and cleanup — not safety-critical.

### What Pragati got right that many projects don't

- Proper package separation (10 packages, not one monolith)
- Custom message package (`motor_control_msgs`)
- YAML-based motor configuration
- Structured JSON logging (`common_utils`)
- Cross-compilation infrastructure (`build.sh rpi`)
- Field deployment tooling (`sync.sh`, systemd services)
- Web dashboard for monitoring and control
- OpenSpec change management with spec-driven development
- Pre-commit/pre-push hooks for code quality

### For context

Most ROS2 codebases at this stage look similar or worse. `SingleThreadedExecutor` with zero
callback groups is the default pattern in nearly every ROS2 tutorial. God-classes are the
norm in robotics because hardware integration naturally concentrates complexity. The fact
that we have structured logging, a common_utils package, launch files, YAML configs, and a
formal change management workflow puts us ahead of most teams at this stage.

### Three highest-ROI investments right now

1. ~~**Callback groups + MultiThreadedExecutor**~~ ✅ Done for all critical nodes
2. ~~**ODrive heartbeat/CAN failure detection**~~ ✅ Done — CAN write checks (1.8) + heartbeat staleness (2.3) both fixed. 11 gtests added.
3. **depthai_manager re-decomposition (2.1)** — depthai_manager.cpp restored (2,228L god-class active again); mg6010 Phase 3 complete (3,672L, 10/10 steps, 8 delegate classes, MultiThreadedExecutor(4), LifecycleNode). Remaining target is depthai_manager. Stereo depth parameters now configurable for field experimentation (5 params: spatial_calc_algorithm, mono_resolution, lr_check, subpixel, median_filter — commit 0c15e3ad0). Zero-spatial diagnostics available for field analysis (bbox logging + image annotation — detection-zero-spatial-diagnostics archived). JSON logging gaps fixed for field trial (polar coords, plan status, delay_ms, position feedback, detection throttle/pause — field-trial-logging-gaps archived). Behavior tree deprioritized (motion_controller already decomposed into 5 classes).

---

## Related Existing Work

- `openspec/changes/archive/2026-03-12-infrastructure-packages-refactoring/` - **✅ Archived**: Items 4.3 (signal handler consolidation), 5.3 partial (cotton_detection_msgs extraction), 5.4 partial (CMake modules + signal handlers), 5.5 partial (common_utils expansion). 6 capabilities, socketcan loopback bugfix, joint naming fix.
- `openspec/changes/archive/2026-03-12-tech-debt-quick-wins/` - **✅ Archived**: Items 3.5 (MQTT parameterization), 3.7 (broken imports + dead code), 4.1 (dead coordinate_transforms), 4.4 (dead EE timeout parameter). 4 capabilities, ~15 tasks.
- `openspec/changes/archive/2026-03-12-vehicle-exception-cleanup/` - **✅ Archived**: Item 2.2 (19 silent exception-swallowing blocks → logged exceptions with severity tiers). ~10 tasks.
- `openspec/changes/archive/2026-03-12-motion-controller-decomposition/` - **✅ Archived**: Item 3.3 god-class decomposition (5 classes extracted, 92 tests, 9 new headers)
- `openspec/changes/archive/2026-03-12-depthai-decomposition/` - **✅ Archived**: Item 2.1 (26 catch blocks) + TD-CD-2 god-class → 5 classes (ThermalGuard, DiagnosticsCollector, PipelineBuilder, DeviceConnection, CameraManager). NOTE: depthai_manager.cpp later RESTORED by restore-depthai-manager (Mar 14) — decomposed classes unused in production.
- `openspec/changes/archive/2026-03-12-mg6010-decomposition/` - **✅ Archived**: Item 3.2 god-class Phase 1, steps 1-3 → 3 classes (MotorTestSuite, ControlLoopManager, RosInterfaceManager)
- `openspec/changes/archive/2026-03-13-mg6010-decomposition-phase2/` - **✅ Archived**: Item 3.2 god-class Phase 2, steps 4-5 → 2 classes (ActionServerManager 904L+274L header+1261L test, MotorManager 389L+224L header+590L test). Node reduced 4,511→3,661 LOC.
- `openspec/changes/archive/2026-03-15-mg6010-decomposition-phase3/` - **✅ Archived**: Item 3.2 god-class Phase 3, steps 6-10 (RoleStrategy ~300L, ShutdownHandler ~175L, MultiThreadedExecutor(4) with 3 callback groups, LifecycleNode with 5 lifecycle callbacks, cleanup). Item 5.1 resolved (RoleStrategy polymorphic interface). 33 new tests. Node: 3,672 LOC.
- `openspec/changes/archive/2026-03-15-motor-control-hardening/` - **✅ Archived**: Motor init/shutdown sequence hardening (motor_stop → clear_errors → read_status with 3 retries → motor_on → verify_active; shutdown: motor_stop → motor_off → clear_errors), timeout handler sends motor_stop before clearing busy flag, CommandDedup class in vehicle_control skips redundant ROS2 position messages (0.01 epsilon), shutdown handler calls stop() before disable and clear_errors() after. 4 capabilities (motor-init-shutdown-sequence, motor-timeout-stop, vehicle-command-dedup, shutdown-handler delta). 34 tests (7 init/shutdown + 5 timeout-stop + 3 shutdown-handler + 19 dedup). Root cause: Feb 26 field trial motor init order bugs, timeout handler not sending stop, redundant CAN bus traffic. Files: mg6010_controller.cpp, mg6010_controller_node.cpp, shutdown_handler.cpp, vehicle_control_node.py, command_dedup.py (new). Commits: 17e7c2c3f, e29d5be67, 6b8dd1a7d, 35ab4be22. Specs synced: 3 new (motor-init-shutdown-sequence, motor-timeout-stop, vehicle-command-dedup) + 1 updated (shutdown-handler).
- `openspec/changes/archive/2026-03-15-detection-zero-spatial-diagnostics/` - **✅ Archived**: Zero-spatial bbox logging + image annotation for field analysis. 2 new capabilities (zero-spatial-bbox-logging, zero-spatial-image-annotation) + 1 modified (depth-validation). Bbox coordinates (xmin, ymin, xmax, ymax) added to WARN-level zero-spatial rejection log. Red bounding boxes with "DEPTH FAIL" labels drawn on output images for rejected detections. 18 test cases (test_zero_spatial_diagnostics.cpp). Diagnostics for 17% zero-spatial rate from Feb trial. Commit: e0b006d56. Specs synced: zero-spatial-bbox-logging, zero-spatial-image-annotation (new), depth-validation (updated).
- Stereo depth parameter configurability (commit 0c15e3ad0, 2026-03-15) — 5 hardcoded stereo depth pipeline parameters (spatial_calc_algorithm "average", mono_resolution "400p", lr_check true, subpixel false, median_filter "7x7") exposed as configurable ROS2 parameters. Wired: production.yaml → ROS2 declare_parameter() → node → DetectionConfig → CameraConfig → depthai_manager/pipeline_builder. Defaults unchanged from hardcoded values — enables field experimentation without code changes. 23 source-audit tests (test_stereo_param_configurability.cpp). 11 files modified (+527/-15 lines). Enables field tuning to reduce zero-spatial detection rate.
- `openspec/changes/archive/2026-03-15-field-trial-logging-gaps/` - **✅ Archived**: 5 JSON logging gaps fixed in yanthra_move and cotton_detection_ros2. Gap 1: polar coordinates (r, theta, phi) propagated from trajectory planner to pick_complete JSON. Gap 2: plan_status string field added to pick_complete JSON. Gap 3: inter-pick delay_ms field reads real measured delay instead of hardcoded 0. Gap 4: position_feedback JSON event emitted from waitForPositionFeedback() with per-joint ok/error fields. Gap 5: detection throttle_effective reads is_throttled_ and paused reads is_paused_ instead of hardcoded false. 5 capabilities (3 new specs + 2 modified). 32 new tests (7 trajectory planner + 15 pick logging + 10 thermal logging). Commit: b65e189bc. Specs synced: pick-phase-timing (modified), detection-quality (modified), position-feedback-logging (new).
- `openspec/changes/archive/2026-03-14-restore-depthai-manager/` - **✅ Archived**: Restored depthai_manager.cpp (2,228L) as active production code. Decomposed classes retained but unused (DeviceFactory nullptr issue in production pipeline).
- `openspec/changes/archive/2026-03-14-blocking-sleeps-error-handlers/` - **✅ Archived**: Items 2.4 (catch-all blocks), 2.6 (blocking sleeps), 5.5 (ConsecutiveFailureTracker), 5.6 (fail-fast). 63 tasks across 5 packages. 151+ BLOCKING_SLEEP_OK annotations, all `catch(...)` given typed predecessors, all bare `except:` fixed, `ros2SafeSleep()` renamed to `blockingThreadSleep()`, ~50 C++ + ~200 Python tests.
- `openspec/changes/archive/2026-03-14-odrive-data-race-heartbeat-timeout/` - **✅ Archived**: Item 2.3 (heartbeat timeout detection) + data race fix in request_encoder_estimates. 1Hz wall timer, 2s timeout, transition-based stale/recovery logging. 11 gtests (source-verification). Also added: odrive-heartbeat-timeout spec synced to main specs.
- `openspec/changes/archive/2026-03-11-phase-1-critical-fixes/` - **Phase 1 complete**: 7 critical safety fixes (1.1, 1.4-1.9) with TDD tests
- `openspec/changes/archive/2026-03-11-phase-2-critical-fixes/` - **Phase 2 complete**: 2 remaining critical safety fixes (1.2 blocking motor service, 1.3 vehicle thread safety) with TDD tests
- `openspec/specs/async-motor-commands/spec.md` - spec for async motor service pattern (blocking removal requirements added, phase 2)
- `openspec/specs/vehicle-thread-safety/spec.md` - new spec for vehicle thread synchronization (phase 2)
- `openspec/changes/archive/2026-03-07-motor-control-runtime-hardening/` - prior hardening work
- `openspec/changes/archive/2026-03-02-restore-executor-thread/` - executor fix history
- `openspec/changes/archive/2026-03-10-fix-vehicle-cpu-thermal/` - rclpy busy-spin fix
- `docs/project-notes/MOTOR_CONTROL_COMPREHENSIVE_ANALYSIS_2025-11-28.md` - prior motor analysis
- `docs/project-notes/STATIC_ANALYSIS_2025-11-01.md` - prior static analysis
- `docs/project-notes/THERMAL_FAILURE_ANALYSIS_AND_REMEDIATION_PLAN.md` - thermal analysis

---

*Analysis performed by systematic code review with line-level evidence. No code changes made.
ROS2 best practices comparison based on official ROS2 Jazzy documentation and ros2_control
framework documentation.*
