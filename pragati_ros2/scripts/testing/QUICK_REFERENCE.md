# Testing Quick Reference

## 🚀 Quick Start

### Launch Full System
```bash
# Launch all nodes (motor, detection, control)
./launch_all.sh

# Stop all nodes
./stop_all.sh

# Emergency motor stop (safety)
./emergency_motor_stop.sh
```

## 🧪 Integration Tests (Recommended)

### Automated Testing
```bash
# Run N automated detection + movement cycles
./scripts/testing/integration/auto_cycles.sh 10

# Full end-to-end pipeline (detection → motors)
./scripts/testing/integration/full_pipeline.sh

# Test automatic flow (detection → yanthra → motors)
./scripts/testing/integration/automatic_flow.sh

# Manual system test (step-by-step)
./scripts/testing/integration/manual_system_test.sh
```

## 📷 Detection Tests

### Quick Tests
```bash
# Quick single detection
./scripts/testing/detection/quick_test.py

# Auto-trigger detection in loop
./scripts/testing/detection/auto_trigger.py

# Loop testing (N cycles)
./scripts/testing/detection/loop_test.sh 10
```

### Performance & Diagnostics
```bash
# Measure detection latency
./scripts/testing/detection/latency_test.sh

# Service call latency test
./scripts/testing/detection/service_latency.py

# Camera diagnostics
./scripts/testing/detection/camera_diagnostics.sh

# Test C++ node specifically
./scripts/testing/detection/cpp_node_test.sh

# Offline image testing
./scripts/testing/detection/offline_test.sh /path/to/images
```

## ⚙️ Motor Tests

```bash
# Basic motor testing on RPI
./scripts/testing/motor/test_motors.sh

# Motor command API test
./scripts/testing/motor/test_commands.py

# Motor commanding integration
./scripts/testing/motor/test_commanding.sh

# Run motor test on RPI
./scripts/testing/motor/run_test_rpi.sh
```

## 🔥 Stress & Thermal Tests

```bash
# Thermal stress test (fps, duration_min, log_interval_sec)
./scripts/testing/stress/thermal_test.sh 30 20 30

# Monitor camera temperature continuously
./scripts/testing/stress/monitor_thermal.py -i 10 -o thermal.csv

# Background stress test
./scripts/testing/stress/background_test.sh

# Full stress test suite
./scripts/testing/stress/full_stress.sh
```

## 🛠️ Utilities

### Diagnostics
```bash
# Analyze system logs and check status
./scripts/utils/analyze_logs.sh

# Check joint states
./scripts/utils/check_joints.sh

# System status overview
./scripts/utils/system_status.sh

# Monitor ROS2 commands
./scripts/utils/monitor_commands.sh

# Quick motor check
./scripts/utils/quick_motor_check.sh
```

### Camera
```bash
# Capture and view camera feed from RPI
./capture_and_view.sh

# Direct camera view capture
./capture_view.sh
```

## 📦 Deployment & Setup

```bash
# Setup and test on RPI
./scripts/deployment/rpi_setup_and_test.sh

# Setup DepthAI C++ on RPI
./scripts/deployment/rpi_setup_depthai.sh

# Verify RPI setup
./scripts/deployment/rpi_verify.sh

# Deploy complete system to RPI (recommended)
./sync.sh --build

# Deploy cross-compiled binaries
./build.sh rpi           # Cross-compile first
./sync.sh --deploy-cross # Deploy binaries

# Install dependencies
./scripts/setup/install_deps.sh
```

## 📝 Build & Operations

```bash
# Build workspace
./build.sh

# Build on RPI
./build_rpi.sh
```

---

## 🎯 Recommended Testing Workflow

1. **Initial Setup**:
   ```bash
   ./build.sh
   ./scripts/setup/install_deps.sh
   ```

2. **Launch System**:
   ```bash
   ./launch_all.sh
   ```

3. **Run Integration Tests**:
   ```bash
   # Quick 5-cycle test
   ./scripts/testing/integration/auto_cycles.sh 5
   ```

4. **Monitor & Debug**:
   ```bash
   ./scripts/utils/analyze_logs.sh
   ./scripts/utils/system_status.sh
   ```

5. **Shutdown**:
   ```bash
   ./stop_all.sh
   ```

## ⚠️ Safety

Always have emergency stop ready:
```bash
./emergency_motor_stop.sh
```

---

**Note**: All paths are relative to workspace root (`~/pragati_ros2/`)
