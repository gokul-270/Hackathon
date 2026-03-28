# Archive Files - Historical References

**Date:** 2025-10-29

## About This Archive

The `docs/archive/` directory contains historical documentation and reports from the development and migration of the Pragati ROS2 system.

## Node Rename (2025-10-29)

On 2025-10-29, we renamed the production motor controller node:
- **Old:** `mg6010_integrated_test_node`
- **New:** `mg6010_controller_node`

### Why Archive Files Still Reference Old Names

Archive files are **intentionally left unchanged** to preserve historical accuracy. They document:
- Past decisions and reasoning
- Development progression
- Historical test results
- Migration steps taken

These files serve as a historical record and should not be used as current documentation.

### For Current Documentation

Always refer to:
- **Active guides:** `docs/guides/`
- **Package README:** `src/motor_control_ros2/README.md`
- **Quick reference:** `src/motor_control_ros2/QUICK_REFERENCE.md`
- **Node comparison:** `src/motor_control_ros2/README_NODES.md`
- **Root README:** `/README.md`

### Archive Contents Include

Files in `docs/archive/` may contain references to:
- Old node names (`mg6010_integrated_test_node`)
- Old launch files (`mg6010_integrated.launch.py`)
- Historical implementations
- Past testing approaches
- Migration documentation

**These are correct for their historical context** and should not be "fixed" to match current naming.

## Current Node Names (October 2025)

### Protocol Test Node
- **Name:** `mg6010_test_node`
- **Purpose:** Low-level CAN protocol testing
- **Launch:** `ros2 launch motor_control_ros2 mg6010_test.launch.py`

### Production Controller Node
- **Name:** `mg6010_controller_node` ← **Current production name**
- **Purpose:** Production motor controller with full ROS integration
- **Launch:** `ros2 launch motor_control_ros2 mg6010_controller.launch.py`

### Historical Name (Pre-October 2025)
- **Old Name:** `mg6010_integrated_test_node` ← **No longer used**
- **Renamed:** 2025-10-29 for clarity

---

**If you see references to old names in archive files, this is expected and correct for historical documentation.**

**For current usage, always use `mg6010_controller_node`.**
