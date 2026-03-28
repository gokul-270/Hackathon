# Robot Description – Change Log & Validation Notes

**Last Updated:** 2025-10-14  
**Maintainers:** Systems & Documentation Team

---

## ✅ Current Snapshot

- `data/pragati_robot_description.urdf` matches the CAD export from 2025-10-12.
- `ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true` verifies the TF tree with
  the updated URDF (see `test_output/integration/2025-10-14_simulation_suite_summary.md`).
- No outstanding TODOs for link/joint naming; next hardware calibration will refresh transforms.

## 🆕 2025-10-14

- Recorded the simulation TF validation after the documentation cleanup push.
- Archived previous audit artefacts under `docs/archive/2025-10-audit/2025-10-14/`.
- Added governance note to `CONTRIBUTING.md` requesting TF validation whenever the URDF changes.

## 📋 Maintenance Checklist

1. Update `data/pragati_robot_description.urdf` when CAD or frame offsets change.
2. Re-run the simulation TF validation (`ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=true`).
3. Capture the resulting log or screenshot in `test_output/integration/<date>_tf_validation/`.
4. Record a short summary in this changelog (date + evidence path).
5. Reference the update inside `docs/STATUS_REALITY_MATRIX.md` if status changes.

## 🔭 Upcoming Tasks

- Refresh static transforms with measured hardware values after the next field calibration.
- Explore auto-generated joint limit exports from CAD to reduce manual edits.

---

For historical URDF versions, consult Git history or the snapshots under `docs/archive/2025-10-artifacts/`.
