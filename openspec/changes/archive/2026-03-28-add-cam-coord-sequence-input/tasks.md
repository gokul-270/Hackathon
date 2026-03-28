## Execution Plan

| Group | Label | Depends On | Can Parallelize With |
|-------|-------|------------|----------------------|
| 1 | SEQUENTIAL | — | — |
| 2 | SEQUENTIAL | 1 | — |
| 3 | PARALLEL | 2 | 4 |
| 4 | PARALLEL | 2 | 3 |
| 5 | SEQUENTIAL | 3, 4 | — |
| 6 | SEQUENTIAL | 5 | — |

---

## 1. Tests — Backend marker endpoints [SEQUENTIAL]

- [x] 1.1 Read `testing_backend.py` to understand existing endpoint patterns and the `gz service` subprocess call style
- [x] 1.2 Write `test_cam_markers_backend.py`: test `POST /api/cam_markers/place` returns 200 and calls `gz service` with correct SDF when given valid cam coords (mock subprocess)
- [x] 1.3 Write test: `POST /api/cam_markers/place` returns 422 when cam coords are missing
- [x] 1.4 Write test: `POST /api/cam_markers/clear` returns 200 and calls `gz service remove` for each previously placed marker name
- [x] 1.5 Write test: `POST /api/cam_markers/clear` returns 200 with empty list (no markers placed)
- [x] 1.6 Write test: FK world-frame computation returns expected (wx, wy, wz) for known (cam_x, cam_y, cam_z) input (assert against hand-computed reference values)
- [x] 1.7 Run tests — confirm all 6 fail (RED)

## 2. Implementation — Backend marker endpoints [SEQUENTIAL]

- [x] 2.1 Extract FK world-frame constants from `vehicle_arm_merged.urdf` (base-to-world XYZ offsets for the fixed joints in the chain: world → base_link → link2 → link4 → link3 → yanthra_link → camera_link)
- [x] 2.2 Add `cam_to_world(cam_x, cam_y, cam_z) → (wx, wy, wz)` helper function to `testing_backend.py` using extracted FK constants
- [x] 2.3 Add in-memory marker name list (module-level list) to `testing_backend.py`
- [x] 2.4 Implement `POST /api/cam_markers/place` endpoint: validate input, call `cam_to_world`, build sphere SDF string, call `gz service /world/empty/create`, append marker name to list, return 200 + name
- [x] 2.5 Implement `POST /api/cam_markers/clear` endpoint: iterate marker list, call `gz service /world/empty/remove` for each, clear list, return 200
- [x] 2.6 Run backend tests — confirm all pass (GREEN)
- [x] 2.7 Refactor: extract SDF template string to a module-level constant; ensure no duplication

## 3. Tests — JS cam-to-joint math [PARALLEL with 4]

- [x] 3.1 Create `tests/test_cam_to_joint.js` (or `.test.js`) using the existing Playwright test setup or a lightweight Node runner (check for `package.json` / `playwright.config.js` in `web_ui/`)
- [x] 3.2 Write test: `camToJoint(tf4x4, 0.5, 0.1, 0.3)` returns J3 in radians within [−0.9, 0.0]
- [x] 3.3 Write test: `camToJoint` returns J4 = ay (direct passthrough within [-0.250, 0.350])
- [x] 3.4 Write test: `camToJoint` returns J5 = r − 0.320 within [0.0, 0.450]
- [x] 3.5 Write test: `camToJoint` returns `{valid: false}` when computed J3 is outside [−0.9, 0.0]
- [x] 3.6 Run tests — confirm all fail (RED)

## 4. Tests — Playwright E2E for UI panel [PARALLEL with 3]

- [x] 4.1 Locate or create `playwright.config.js` for the testing UI (port 8081)
- [x] 4.2 Write E2E test: "Add Position" button appends a new row with cam_x, cam_y, cam_z inputs
- [x] 4.3 Write E2E test: "Remove" button on a row deletes that row
- [x] 4.4 Write E2E test: "Run Sequence" with empty table shows "No positions in sequence" warning
- [x] 4.5 Write E2E test: "Run Sequence" with TF not ready shows "TF not ready" error
- [x] 4.6 Write E2E test: out-of-range computed row is highlighted red and excluded from execution
- [x] 4.7 Run E2E tests — confirm all fail (RED)

## 5. Implementation — JS math + UI panel [SEQUENTIAL]

- [x] 5.1 Add `camToJoint(tf4x4, cam_x, cam_y, cam_z)` function to `testing_ui.js` (TF apply, polar decomp, joint limits check)
- [x] 5.2 Subscribe to `/tf_static` in `testing_ui.js` via roslib; extract `camera_link → yanthra_link` matrix; set `tfReady` flag
- [x] 5.3 Add Cotton Position Sequence section markup to `testing_ui.html`: panel header, table with cam_x/cam_y/cam_z columns, "Add Position" / "Place Markers" / "Clear Markers" / "Run Sequence" / "Stop" buttons
- [x] 5.4 Add section styles to `testing_ui.css` (panel card, out-of-range row highlight in red, active row highlight during playback)
- [x] 5.5 Implement "Add Position" and "Remove" row handlers in `testing_ui.js`
- [x] 5.6 Implement "Place Markers" handler: for each row compute joints (validate), call `POST /api/cam_markers/place` with cam coords, show marker name in row
- [x] 5.7 Implement "Clear Markers" handler: call `POST /api/cam_markers/clear`, clear marker name display in all rows
- [x] 5.8 Implement "Run Sequence" handler: validate all rows (highlight invalids, abort if any), iterate rows with `await sleep(dwellMs)`, send joint commands via existing `/api/joint_command`, highlight active row, handle stop flag
- [x] 5.9 Implement "Stop" button handler setting the stop flag
- [x] 5.10 Run JS unit tests and E2E tests — confirm all pass (GREEN)
- [x] 5.11 Refactor: extract sequence runner to a separate named function; remove any inline magic numbers (use named constants for joint limits and J5 offset)

## 6. Commit [SEQUENTIAL]

- [x] 6.1 Run full test suite (`pytest` for backend, Playwright for E2E) — confirm GREEN
- [x] 6.2 Commit all changed files with message `feat: add Cotton Position Sequence Player with cam-coord input and Gazebo markers`
