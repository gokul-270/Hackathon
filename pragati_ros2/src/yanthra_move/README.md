yanthra_move_node
# Yanthra Move – ROS 2 Manipulation Stack (Reality Snapshot)

**Last Updated:** 2025-11-01  
**Status:** ✅ Core Systems Validated - GPIO Integration Remaining  
**Validation:** Software [yes], Sim [yes], Bench [motors validated Oct 30], GPIO [~90 min remaining], Field [recommended]
**Hardware:** GPIO (pump, LEDs, switches), motor controllers  
**Test Coverage:** 17 coordinate transform unit tests (pure math validated)

**Default mode:** Simulation-first | **Hardware I/O:** Partially stubbed (see Known Gaps below)

Yanthra Move is the ROS 2 port of Pragati’s cotton-picking manipulator. The code base compiles and runs in simulation, subscribes to the C++ cotton detection pipeline, and exposes ROS 2 services/topics for orchestration. Hardware control hooks for pumps, LEDs, and limit switches are still stubs in `src/yanthra_move_system.cpp`, so full production deployment depends on follow-up work and field revalidation.

> **Source of truth:** Keep this README aligned with `docs/STATUS_REALITY_MATRIX.md` and the reconciliation plan in `docs/cleanup/DOCUMENTATION_RECONCILIATION_PLAN.md`.

## What Works Today

- ✅ **ROS 2 node + launch files** – `yanthra_move_node` launches via `launch/pragati_complete.launch.py` with multi-threaded executor support.
- ✅ **Motion planning pipeline** – `core/motion_controller.cpp` handles the picking sequence and consumes cotton detections from `/cotton_detection/results`.
- ✅ **Simulation mode** – `config/production.yaml` sets `simulation_mode: true` by default so the node can run without hardware.
- ✅ **Status service** – `/yanthra_move/current_arm_status` reports health/telemetry for higher-level supervisors.
- ✅ **MG6010 integration hooks** – Interfaces to `motor_control_ros2` services exist (homing, idle) and remain compatible with the latest MG defaults.

## Status Update (Nov 1, 2025)

**✅ Motor Control:** Validated Oct 30, 2025 - 2-motor system (Joint3, Joint5) functional  
**✅ Cotton Detection:** Validated Nov 1, 2025 - 134ms service latency  
**⏳ GPIO Integration:** ~90 min remaining for vacuum pump, LEDs, switches  
**⏳ System Integration:** ~90 min field validation with full assembly

## Critical Limitations & TODOs

- 🚧 **GPIO drivers are placeholders** – Functions like `VacuumPump()`, `camera_led()`, and start/stop switch handling are TODOs (see `yanthra_move_system_core.cpp` lines 60–170). ~90 min hardware work required.
- ✅ **Motor control validated** – Oct 30, 2025: 2-motor system operational, <5ms response time
- 🚧 **Full system integration pending** – ~90 min for GPIO wiring + end-to-end testing
- 🚧 **Parameter hygiene** – YAML defaults match ROS1 migration; confirm against current joint offsets and MG6010 tuning

Track these items in:
- **[docs/TODO_MASTER.md](../../docs/TODO_MASTER.md)** – All 29 code TODOs and planned work
- **[docs/status/STATUS_TRACKER.md](../../docs/status/STATUS_TRACKER.md)** – Project status tracking
- **[docs/STATUS_REALITY_MATRIX.md](../../docs/STATUS_REALITY_MATRIX.md)** – Evidence-based validation tracker

## Quick Start (Simulation)

```bash
cd /path/to/pragati_ros2
colcon build --packages-select yanthra_move
source install/setup.bash

# Run in simulation mode (no hardware required)
ros2 run yanthra_move yanthra_move_node \
  --ros-args --params-file src/yanthra_move/config/production.yaml \
  -p simulation_mode:=true
```

Launch files mirror the ROS1 orchestration but default to a single cycle:

```bash
ros2 launch yanthra_move pragati_complete.launch.py \
  continuous_operation:=false  # change to true only after validating watchdogs
```

Passing `continuous_operation:=true` or `-p max_runtime_minutes:=120` relies on the safety shutdown logic in `runMainOperationLoop()`; test in sim before hardware.

## Hardware Bring-Up Checklist

1. **Enable hardware interfaces** – Set `simulation_mode:=false`, `enable_gpio:=true`, and `enable_camera:=true` in the parameter file or launch overrides.
2. **Verify MG6010 services** – Ensure `motor_control_ros2` brings the CAN interface up at 250 kbps and exposes `/joint_homing` and `/joint_idle`.
3. **Wire start/stop switches** – Implement the TODOs for start/stop monitoring or supply ROS topic shims that match the expected callbacks.
4. **Integrate vacuum + lighting** – Replace the TODO stubs with `pragati_hardware` drivers (or GPIO utilities) and document wiring.
5. **Capture logs** – Store operator logs under `test_results/` and update the status matrix with the run date.

## Interfaces (Current Contract)

| Type | Name | Description |
|------|------|-------------|
| Topic (pub) | `/joint{2,3,4,5}_position_controller/command` | Trajectory/position commands issued per joint. |
| Topic (pub) | `/shutdown_switch/state`, `/start_switch/state` | Current switch status (simulation publishes defaults). |
| Topic (sub) | `/cotton_detection/results` | Consumes detections from `cotton_detection_ros2`. |
| Service (srv) | `/yanthra_move/current_arm_status` | Returns system health snapshot. |
| Service (client) | `/joint_homing`, `/joint_idle` | Delegates homing/idle requests to the motor controller stack. |

Parameters live under the `yanthra_move` namespace (see `config/production.yaml`). Key flags include:

- `simulation_mode` (bool) – bypasses GPIO + camera bring-up.
- `continuous_operation` (bool) – loop until stopped; defaults to single-cycle.
- `max_runtime_minutes` (int) – watchdog timer; `-1` disables (testing only).
- `start_switch.*` (flat notation) – configuration for start switch semantics.

## Validation Snapshot (2025-10-21)

- ✅ Builds locally with `colcon build --packages-select yanthra_move` (simulation).
- ✅ Launches in simulation and consumes synthetic cotton detections.
- ✅ **17 coordinate transform unit tests added (Software Sprint, Oct 2025)** covering XYZ→polar conversion, reachability, boundary conditions.
- ⚠️ Controller and TF2-dependent integration tests deferred to hardware phase.
- ❌ No post-DepthAI hardware run recorded. Field test + log capture required before updating production badges.

## Roadmap Excerpts

Refer to `docs/MASTER_MIGRATION_STRATEGY.md` (Phase 3) and `docs/STATUS_REALITY_MATRIX.md` for the canonical backlog. Highest-priority follow-ups:

1. Implement GPIO/pump/LED drivers and integrate with Safety Monitor telemetry.
2. Record end-to-end hardware run with the C++ cotton pipeline and DepthAI enabled.
3. Add targeted integration tests (simulation harness or hardware-in-loop) prior to enabling CI gates.
4. Document parameter tuning workflow and runtime overrides once the hardware defaults are confirmed.

## Related Documentation

### Current Status & Planning
- **[docs/TODO_MASTER.md](../../docs/TODO_MASTER.md)** – Complete work backlog (2,540 items across all modules)
- **[docs/status/STATUS_TRACKER.md](../../docs/status/STATUS_TRACKER.md)** – Project phase/tier completion status
- **[docs/STATUS_REALITY_MATRIX.md](../../docs/STATUS_REALITY_MATRIX.md)** – Evidence-based validation tracker

### Historical & Governance
- `docs/MASTER_MIGRATION_STRATEGY.md` – Status of remaining migration phases
- `docs/maintenance/DOC_MAINTENANCE_POLICY.md` – Documentation governance rules
- `docs/archive/2025-10/yanthra_move/` – Archived meta docs from this consolidation

---

Maintainers: please update this README every time the code, hardware validation status, or parameter defaults change. Link evidence (logs, test outputs) in the status matrix to keep the documentation trustworthy.

## FAQ (Quick Reference)

### Q: Getting 'Service not available' errors?
A:
1. Check if yanthra_move node is running: `ros2 node list | grep yanthra`
2. Verify motor_control services available: `ros2 service list | grep motor`
3. Ensure simulation_mode matches your setup
4. Check parameter file loaded correctly

### Q: Motion planning fails - joints won't move?
A:
- Simulation mode enabled? Set `simulation_mode:=false` for hardware
- Motors homed? Run `ros2 service call /joint_homing ...`
- Check joint limits in config match physical hardware
- Verify cotton detection results publishing: `ros2 topic echo /cotton_detection/results`

### Q: How do I test without physical hardware?
A:
```bash
# Run in full simulation (no hardware needed)
ros2 run yanthra_move yanthra_move_node --ros-args -p simulation_mode:=true

# Publish fake cotton detections for testing
ros2 topic pub /cotton_detection/results ...
```

### Q: GPIO errors (pump, LEDs, switches)?
A: GPIO implementation is stubbed (TODO in yanthra_move_system_core.cpp lines 60-170). You need to:
1. Implement actual GPIO drivers
2. Wire physical GPIO pins
3. Test with `enable_gpio:=true`

### Q: Coordinate transforms failing?
A:
- Check TF2 tree published: `ros2 run tf2_tools view_frames`
- Verify base_link frame exists
- Check joint offsets in config match calibration
- See coordinate transform tests for validation

### Q: Start/stop switches not working?
A: Switch monitoring is TODO. Workarounds:
- Use ROS service calls instead of physical switches
- Publish to switch topics manually for testing
- Implement switch callbacks (see TODOs in source)

### Q: Safety timeouts too aggressive?
A: Adjust in config:
```yaml
yanthra_move:
  watchdog_timeout_sec: 5.0
```

### Q: Continuous operation vs single cycle?
A:
- **Single cycle** (default): Processes one cotton then stops
- **Continuous** (`continuous_operation:=true`): Loops until stopped
- ⚠️ Only enable continuous after validating safety watchdogs!

### Q: MG6010 integration not working?
A: Ensure motor_control_ros2 is running:
```bash
ros2 service list | grep motor_control
ros2 service call /joint_homing ...  # Should respond
```

**More FAQ:** See main FAQ.md in docs/guides/ for system-wide questions.

