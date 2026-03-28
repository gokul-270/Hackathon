# Pattern Finder – Reality Snapshot (2025-10-13)

**Status:** ⚠️ Legacy utility kept for reference | **ROS 2 integration:** Not yet ported  
**Owner:** Vision/Calibration team  

This package contains the legacy ArUco marker detection utility that was used during ROS 1 calibration flows. The current C++ implementation (`src/aruco_finder.cpp`) still relies on hard-coded paths under `/home/ubuntu` and an external RealSense capture script. It is **not integrated with the ROS 2 graph** and has not been exercised since the ROS 2 migration.

> Keep this README aligned with `docs/STATUS_REALITY_MATRIX.md` (add a row if missing) and the cleanup checklist in `docs/cleanup/DOCUMENTATION_RECONCILIATION_PLAN.md`.

## What exists today

- ✅ Standalone executable that captures a frame + point cloud (`RS_CAPTURE_S640_PROGRAM`) and locates a DICT_6X6_250 ArUco marker (ID 23, 800 px).
- ✅ Writes detected 3D corner coordinates to `/home/ubuntu/.ros/centroid.txt` and saves a debug image to `/home/ubuntu/outputs/`.
- ✅ Includes a generated marker image (`marker_image.jpg`) for printing.

## Critical gaps

- 🚧 **Hard-coded paths:** Input/output directories and capture scripts assume a specific `/home/ubuntu` layout. Portability work is required before reuse.
- 🚧 **No ROS 2 node:** The executable is a plain `main()`; no publishers/subscribers or parameters are exposed. Integrating with ROS 2 would require a rewrite around `rclcpp`.
- 🚧 **Hardware/runtime validation:** No CI or test harness exists. The utility has not been verified since 2024, and RealSense dependencies are untracked.
- 🚧 **Build integration:** The package builds with `colcon` but is excluded from regular launch files; confirm whether it should remain part of the workspace or move to an archive.

Track remediation items in `docs/STATUS_REALITY_MATRIX.md` and the reconciliation plan.

## Suggested next steps

1. Decide whether to retire the legacy utility or port it to ROS 2 (e.g., convert to a node that publishes centroid poses).
2. If keeping it:
   - Replace hard-coded paths with parameters or environment variables.
   - Wrap capture logic in a configurable interface; document hardware prerequisites.
   - Add at least a smoke test (e.g., run against recorded bag/PCD data).
3. Update documentation once decisions are made—either archive the package or describe the ROS 2 integration points.

## Quick reference

| Item | Location |
|------|----------|
| Executable source | `src/aruco_finder.cpp` |
| Marker asset | `marker_image.jpg` |
| Default output | `/home/ubuntu/.ros/centroid.txt` |
| Capture script | `/home/ubuntu/scripts/rs_capture_s640` (external) |

---

If you remove or replace this package, update the reconciliation plan and the doc inventory snapshot so automated checks stay green.
