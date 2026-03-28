# Vehicle Control – Reality Snapshot (2025-10-14)

**Status:** ⚠️ Software aligned; hardware validation pending  
**Primary audience:** Engineers bringing up the Pragati drive platform  
**Source of truth:** Keep this README consistent with `docs/STATUS_REALITY_MATRIX.md` and the reconciliation plan in `docs/cleanup/DOCUMENTATION_RECONCILIATION_PLAN.md`.

This package hosts the ROS 2/Python implementation of the Pragati vehicle controller. The code builds, launches, and exposes the expected ROS 2 interfaces, but we have **not rerun full bench testing since the 2025 C++ migration work**. Treat any “production-ready” language in older documents as historical—until new hardware runs are captured, the system remains in a validation state.

## What’s Working Today

- ✅ `vehicle_control.integration.ros2_vehicle_control_node` launches via `ros2 launch vehicle_control vehicle_control_with_params.launch.py`.
- ✅ Core modules (`core/vehicle_controller.py`, `core/state_machine.py`, `hardware/motor_controller.py`) mirror the legacy architecture with Python implementations.
- ✅ Safety manager + watchdog hooks exist and run in simulation.
- ✅ Simulation/demo scripts (`demo.py`, `simple_demo.py`, `simulation/run_simulation.py`) exercise the control loops without hardware.

## Known Limitations & Follow-ups

- 🚧 **Hardware IO** depends on ODrive, GPIO, and CAN interfaces that haven’t been revalidated since the ROS 2 port. Expect wiring/config updates and CAN timeout tuning during bring-up.
- 🚧 **Test coverage** is minimal (`tests/test_enhanced_system.py` only); the README previously referenced “35+ tests,” which no longer exists. Expand automated coverage before claiming production readiness.
- 🚧 **Documentation drift** still exists in archived reports. Keep this README synced with the status matrix and strip marketing claims elsewhere.
- 🚧 **Performance metrics** (cycle times, success rates) were never re-measured after the port. Treat old numbers as placeholders until new logs are recorded.

Track these items in the status matrix (Section 1) and `docs/MASTER_MIGRATION_STRATEGY.md`.

## Quick Start (Simulation First)

```bash
cd /path/to/pragati_ros2
colcon build --packages-select vehicle_control
source install/setup.bash

# Launch the ROS 2 node with simulation-friendly defaults
ros2 launch vehicle_control vehicle_control_with_params.launch.py \
  use_sim_time:=false \
  log_level:=info

# Or run standalone demos (no ROS graph required)
python src/vehicle_control/demo.py
python src/vehicle_control/simple_demo.py
```

The default `config/production.yaml` assumes CAN at 500 kbps and simulation-safe velocity limits. Flip `simulation_mode` and GPIO flags carefully when heading towards hardware.

## 🎮 Gazebo Simulation

A comprehensive Gazebo simulation is integrated that uses **velocity-based kinematics** matching the real robot control algorithms!

### Quick Start
```bash
# Build the package
cd ~/pragati_ros2
colcon build --packages-select vehicle_control
source install/setup.bash

# Launch Gazebo simulation with joystick control
ros2 launch vehicle_control gazebo_with_joy.launch.py

# Or launch without joystick
ros2 launch vehicle_control gazebo.launch.py

# Launch the Web UI joystick (in a separate terminal)
cd src/vehicle_control/simulation/gazebo/web_ui
./launch_web_ui.sh
# Then open http://localhost:8888 in your browser
```

### Control Methods

**Joystick Control** (requires `ros-jazzy-joy`):
- Left Stick Y: Forward/Backward
- Right Stick X: Rotate Left/Right
- Button A: Turbo Mode (2x speed)
- Button B: Emergency Stop

**Web UI Joystick** (browser-based, no physical joystick needed):

Requires `ros-jazzy-rosbridge-suite`:
```bash
sudo apt install ros-jazzy-rosbridge-suite
```

Launch (in a separate terminal after Gazebo is running):
```bash
cd ~/pragati_ros2/src/vehicle_control/simulation/gazebo/web_ui
chmod +x launch_web_ui.sh
./launch_web_ui.sh            # starts HTTP server (port 8888) + rosbridge (port 9090)
# Use --no-bridge if rosbridge is already running elsewhere
```

Open `http://localhost:8888` in your browser (or `http://<WSL_IP>:8888` from Windows).

- Virtual on-screen joystick — drag to send velocity commands
- E-Stop button — immediate emergency stop
- Speed modes — Slow (0.2 m/s), Medium (0.5 m/s), Fast (1.0 m/s)
- Live telemetry — steering angles, wheel velocities, joint states

**Command Line Control**:
```bash
# Drive forward
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}, angular: {z: 0.0}}"

# Rotate in place
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.0}, angular: {z: 0.5}}"
```

### Features
- ✅ Uses **same velocity-based kinematics** as real robot
- ✅ Accurate 3-wheel vehicle model (correct URDF)
- ✅ Realistic physics with Gazebo Harmonic
- ✅ Cotton field environment
- ✅ Joystick and keyboard teleop support
- ✅ **Web UI joystick** with live telemetry (`simulation/gazebo/web_ui/`)

### Documentation
- [Implementation Details](simulation/gazebo/IMPLEMENTATION.md)
- [URDF Fix Documentation](simulation/gazebo/ORIGIN_FIX.md)
- [Terrain Features](simulation/gazebo/TERRAIN_FEATURES.md)

## Hardware Bring-up Checklist

1. **ODrive/CAN** – Confirm MG6010 CAN services are running (250 kbps), or update the motor controller stubs to match the latest firmware.
2. **GPIO** – Wire emergency stop and status LEDs, then implement/verify the callbacks in `hardware/gpio_manager.py`.
3. **Safety integration** – Ensure the safety monitor package publishes the expected topics/services before relying on automatic shutdown paths.
4. **State machine verification** – Exercise manual/automatic transitions on hardware and capture logs under `test_results/`.
5. **Regression evidence** – Store bench results and link them in the status matrix before restoring “production-ready” claims anywhere else.

## ROS 2 Interfaces

| Type | Name | Purpose |
|------|------|---------|
| Node | `vehicle_control_node` | Top-level Python node (see `integration/ros2_vehicle_control_node.py`). |
| Topic (pub) | `/vehicle_control/debug` | Diagnostic information from the control loop. |
| Service | `/vehicle_control/enable` | Enables/disables the control loop (see integration node). |

Python APIs remain under `core/` and `hardware/`; consult the module docstrings for exact signatures.

## Validation Snapshot (2025-10-14)

- ✅ Builds with `colcon build --packages-select vehicle_control`.
- ✅ Launch file starts the ROS 2 node; simulation demos run on a developer workstation.
- ⚠️ No automated hardware-in-the-loop tests; single pytest file exercises high-level flows only.
- ❌ No updated CAN/GPIO bench logs since the ROS 2 migration. Field testing required.

## Related Documentation

- `docs/STATUS_REALITY_MATRIX.md` – authoritative status row for vehicle control.
- `docs/MASTER_MIGRATION_STRATEGY.md` – tracks outstanding Phase 3 actions (vehicle control + cotton detection integration).
- `docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md` – update as hardware bring-up steps evolve.
- `docs/cleanup/DOCUMENTATION_RECONCILIATION_PLAN.md` – continuing cleanup checklist.

---

Maintainers: update this README whenever validation status or hardware configuration changes. Link to evidence (logs, test outputs) to keep the documentation credible.

## Historical Notes

Earlier migration comparison tables and marketing material overstated hardware readiness. Those documents now live in `docs/archive/` for provenance only. For the current truth source, rely on:

- `docs/STATUS_REALITY_MATRIX.md` (Vehicle Control row) – up-to-date reconciliation with code/tests.
- `docs/cleanup/DOCUMENTATION_RECONCILIATION_PLAN.md` – ongoing cleanup backlog.
- `docs/MASTER_MIGRATION_STRATEGY.md` – remaining Phase 3 tasks for vehicle control.

## 📄 License & Support

This project is licensed under the MIT License.

**Last Updated**: 2025-10-14  
**Version**: 2.1.0 (ROS-1 → ROS-2 port; hardware validation pending)  
**Python Compatibility**: 3.8+  
**Hardware**: Raspberry Pi 4, ODrive Controllers, CAN Bus Interface
**ROS Compatibility**: ROS-2 Jazzy (tested), Iron/Humble (legacy support)
