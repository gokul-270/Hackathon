# depthai_manager Decomposition — Defer Decision (March 2026)

## 1. Executive Summary

The `depthai_manager.cpp` god-class (2,228 lines) was decomposed on March 12, 2026 into
modular classes (`ThermalGuard`, `PipelineBuilder`, `CameraManager`, etc.) but the
decomposition was **reverted on March 14** because the `RealDevice` adapter implementing
the `IDevice` interface was never written. `DetectionEngine` passed `nullptr` as the
`DeviceFactory`, breaking all camera connections. The decomposed classes exist in-repo but
are unused. Re-decomposition requires 5–8 engineering days and carries HIGH risk before
the March 25 field trial. Decision: **DEFER to post-trial.**

## 2. Why the Decomposition Was Reverted

**What happened (March 12–14, 2026):**

1. `depthai_manager.cpp` was split into modular classes with clean interfaces
2. An `IDevice` interface was created in `device_connection.hpp`
3. `DetectionEngine` was updated to use the new `CameraManager` (633 lines) instead of
   `DepthaiManager`
4. **BUT:** `RealDevice` (the production adapter that wraps the actual OAK-D Lite hardware)
   was never implemented
5. `DetectionEngine` passed `nullptr` as the `DeviceFactory` parameter
6. Result: camera connection failed immediately on startup — no detections possible
7. The entire decomposition was reverted to restore the monolithic `depthai_manager.cpp`

**Root cause of the failed decomposition:** The `IDevice` interface has a design gap — it
uses `void*` for the output queue type, which loses type safety. The `RealDevice` adapter
would need to bridge between DepthAI's strongly-typed `dai::DataOutputQueue` and this
`void*` interface. This is non-trivial and was left as "TODO" during the decomposition
sprint.

## 3. Current State of the Code

| File | Lines | Status |
|------|-------|--------|
| `src/cotton_detection_ros2/src/depthai_manager.cpp` | 2,228 | **ACTIVE** — production camera backend |
| `src/cotton_detection_ros2/src/camera_manager.cpp` | 633 | UNUSED — decomposed but deprecated |
| `src/cotton_detection_ros2/include/.../device_connection.hpp` | ~100 | UNUSED — IDevice interface with void* gap |
| `src/cotton_detection_ros2/src/detection_engine.cpp` | ~800 | ACTIVE — uses depthai_manager directly |

The decomposed files remain in the repo but are not compiled or linked. They serve as a
starting point for the post-trial re-decomposition.

## 4. Risk Assessment for Pre-Trial Decomposition

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| RealDevice adapter fails on hardware | HIGH | MEDIUM | Requires physical RPi + OAK-D testing |
| void* queue interface causes runtime crashes | HIGH | HIGH | Needs proper type-safe bridge design |
| Behavioral regression in camera init/recovery | HIGH | MEDIUM | 2,228 lines of subtle state management |
| Insufficient testing time before March 25 | CRITICAL | HIGH | Only ~10 days available |
| Team bandwidth consumed on refactoring vs fixes | HIGH | HIGH | Steering fix and pick filter are higher priority |

**Estimated effort for re-decomposition: 5–8 engineering days**

- Design proper `IDevice` interface without `void*` (1–2 days)
- Implement `RealDevice` adapter with full DepthAI SDK integration (2–3 days)
- Integration testing on RPi with OAK-D Lite hardware (1–2 days)
- Regression testing of detection pipeline (1 day)

## 5. Decision

**DEFER to post-trial.** Reasons:

1. The monolithic `depthai_manager.cpp` works correctly in production
2. 5–8 days of effort is too much risk for 10 days before field trial
3. Motor init/shutdown sequence fix and steering thermal investigation are higher priority
4. The decomposed code is preserved in-repo for post-trial work
5. No field trial requirement depends on this decomposition

## 6. Post-Trial Plan

After March 25:

1. Design type-safe device interface (replace `void*` with proper generics or variant)
2. Implement `RealDevice` adapter with full test coverage
3. Add `MockDevice` for unit testing (the original motivation for decomposition)
4. Migrate `DetectionEngine` to use `CameraManager`
5. Verify on hardware before merging
6. Delete the monolithic `depthai_manager.cpp` only after full regression passes

## 7. Related Documents

- `openspec/changes/archive/2026-03-14-restore-depthai-manager/` — revert change artifacts
- `openspec/changes/archive/2026-03-12-depthai-decomposition/` — original decomposition change
- `docs/project-notes/TECHNICAL_DEBT_ANALYSIS_2026-03-10.md` — TD-DETECT-001 (depthai god class)
- `docs/project-notes/ARM_NODE_REFACTORING_ROADMAP_2026-03-10.md` — broader refactoring plan
- `docs/project-notes/DEPTHAI_ARCHITECTURE_DECISION_2025-11-28.md` — original architecture decisions

## 8. Owners

- depthai_manager decomposition: Detection team
- Code review: Udayakumar (Execution Lead)
