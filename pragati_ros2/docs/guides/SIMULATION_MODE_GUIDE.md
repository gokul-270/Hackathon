# Simulation Mode Quickstart

> **📍 MOVED:** This content has been consolidated into the comprehensive testing guide.  
> **New Location:** [TESTING_AND_OFFLINE_OPERATION.md](TESTING_AND_OFFLINE_OPERATION.md)  
> **Date:** 2025-11-04  
> **Reason:** Consolidated with offline testing and system testing guides for better organization

**Quick Links:**
- [Complete Testing Guide](TESTING_AND_OFFLINE_OPERATION.md)
- [Part 3: C++ Node Simulation Mode](TESTING_AND_OFFLINE_OPERATION.md#part-3-c-node-simulation-mode)

---

## Legacy Content (For Reference)

**Last Updated:** 2025-10-14  
**Scope:** Cotton detection (C++ + legacy wrapper) and yanthra_move manipulator

---

## 1. Why Simulation Mode Matters

Simulation mode lets us validate ROS 2 interfaces, parameter flows, and motion logic without OAK-D Lite hardware or MG6010 drives connected. Use it to:

- Run CI-safe smoke tests that verify topics/services stay wired correctly.
- Exercise the motion controller before releasing to the lab.
- Provide reproducible examples for documentation and onboarding.

Each subsystem exposes a `simulation_mode` flag (or equivalent) that bypasses hardware-only routines while keeping the ROS graph active.

---

## 2. Build & Environment Prep

1. Build the relevant packages (DepthAI optional):
   ```bash
   colcon build --packages-select cotton_detection_ros2 yanthra_move \
       --cmake-args -DHAS_DEPTHAI=OFF
   source install/setup.bash
   ```
2. Set a clean log namespace (optional):
   ```bash
   export ROS_LOG_DIR=$(pwd)/logs/simulation_$(date +%Y%m%d_%H%M)
   mkdir -p "$ROS_LOG_DIR"
   ```

---

## 3. Cotton Detection (C++ Primary)

### Launch in pure simulation (no DepthAI)
```bash
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=true \
    use_depthai:=false \
    publish_debug_image:=false
```

What happens:
- Publishes deterministic synthetic detections on `/cotton_detection/results`.
- Skips DepthAI device enumeration and file-based outputs.
- Keeps diagnostics and TF publishers alive for downstream nodes.

### Smoke test the service contract
```bash
ros2 service call /cotton_detection/detect \
    cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
```
Expect a quick response and a fresh detection message on the results topic. Use `ros2 topic echo /cotton_detection/results --once` to confirm payload structure.

---

## 4. Cotton Detection (Legacy Python Wrapper)

The wrapper is still available for automation parity. Enable its built-in simulation flag:
```bash
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py \
    simulation_mode:=true \
    trigger_on_start:=true
```

Key behaviours:
- Generates the three canonical synthetic cotton boll coordinates.
- Emits `/cotton_detection/results` (Detection3DArray) and honors service calls.
- Skips spawning the DepthAI subprocess when `simulation_mode:=true`.

Use this path only when validating historical automation flows; new work should target the C++ node.

---

## 5. Yanthra Move Manipulator

### Launch in simulation-only mode
```bash
ros2 launch yanthra_move pragati_complete.launch.py \
    use_simulation:=true \
    continuous_operation:=false \
    enable_arm_client:=false
```

> This is the same launch sequence referenced in the root `README.md` quick-start section; keep both in lockstep when parameters change.

This mirrors the README instructions and:
- Avoids ODrive homing requests (no CAN required).
- Uses the cotton position provider injected from the detection subscription.
- Keeps TF + logging active while vacuum pump / GPIO stubs stay no-op.

### Coupling with cotton detection
To exercise the integration end-to-end, run the C++ detection node (Section 3) in a separate terminal before starting `yanthra_move`. The motion controller will:
- Pull synthetic detections through the provider callback.
- Execute the pick/park cycle with simulated delays.
- Log cycle metrics without engaging hardware.

When running the comprehensive validation suite (or `pragati_complete.launch.py`) without the web dashboard, remember to toggle the start switch manually once the launch stabilizes:

```bash
ros2 topic pub /start_switch/state std_msgs/Bool "data: true" --once
```

Skipping this publish will trigger the expected 5-second timeout that parks the arm, as captured in `~/pragati_test_output/integration/comprehensive_test_20251014_093408/system_launch.log`.

Monitor progress with:
```bash
ros2 topic hz /cotton_detection/results
ros2 topic echo /yanthra_move/arm_status --once
```

---

## 6. Optional: Automated Smoke Test

Add this snippet to CI or local scripts to ensure the simulation path stays healthy:
```bash
#!/usr/bin/env bash
set -euo pipefail
source install/setup.bash

ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
    simulation_mode:=true use_depthai:=false &
DET_PID=$!
trap "kill $DET_PID" EXIT

sleep 3
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
ros2 topic echo /cotton_detection/results --once --timeout 5

kill $DET_PID
wait $DET_PID 2>/dev/null || true
```

Document test outcomes in `test_output/integration/` (e.g., `test_output/integration/2025-10-13/simulation_smoke.log`) and archive the console output under `~/pragati_test_output/integration/` (latest run: `comprehensive_test_20251014_093408/`) so the status matrix can reference concrete evidence.

---

## 7. Comprehensive validation suite (simulation profile)

The comprehensive system suite now defaults to a simulation-friendly profile. It marks the MG6010 controller and legacy ODrive services as optional unless you override the behaviour.

### Run the full suite

```bash
./scripts/validation/comprehensive_test_suite.sh
```

The results land in `~/pragati_test_output/integration/` (latest: `comprehensive_test_20251014_095005/`). `runtime_system_state.txt` will highlight which nodes/services are intentionally absent in simulation.

### Re-enable strict MG6010 checks (optional)

```bash
export SIMULATION_EXPECTS_MG6010=1
./scripts/validation/comprehensive_test_suite.sh
```

Set the variable back to `0` (or unset it) to restore the default simulation tolerance once you finish hardware testing.

## 8. Next Steps

- Capture a short asciinema or screenshot of the simulation loop for onboarding.
- Layer in lightweight pytest coverage for the wrapper’s simulation helper.
- Wire this guide into `docs/README.md` and `docs/STATUS_REALITY_MATRIX.md` as the authoritative reference for software-only checks.
