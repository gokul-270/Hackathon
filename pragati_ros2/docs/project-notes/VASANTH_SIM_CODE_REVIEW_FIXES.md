# Vasanth's Simulation Code — Prioritized Fix List

**Date:** March 27, 2026
**Reviewer:** Udayakumar (via code review of commits `e8a4ea7..cbf78c3c7`)
**Scope:** 11 commits, 106 files, ~241K lines across `vehicle_arm_sim`, `vehicle_control`, `yanthra_move`

---

## Priority 1: CRITICAL (Must fix before April field trial)

### P1-1. Install pre-commit/pre-push hooks
- **What:** Run `pre-commit install && pre-commit install --hook-type pre-push`
- **Why:** Root file violations and 82 MB binary commits were not caught because hooks weren't installed
- **Effort:** 5 minutes
- **Verify:** `pre-commit run --all-files` should show root clutter and large file checks

### P1-2. Fix URDF steering topic swap
- **File:** `src/vehicle_arm_sim/urdf/vehicle_arm_merged.urdf`
- **What:** `base-plate-right` joint publishes to `/steering/left` and vice versa. Steering is inverted.
- **Fix:** Swap the topic names so right joint → `/steering/right`, left joint → `/steering/left`
- **Verify:** Launch Gazebo, send steering command, confirm correct wheel turns

### P1-3. Fix duplicate link name in arm_top.urdf
- **File:** `src/vehicle_arm_sim/arm_top_urdf/arm_top.urdf`
- **What:** Link `colle.box-holding-v1` defined twice (lines 22 and 41). Invalid URDF.
- **Fix:** Rename one instance or merge the definitions
- **Verify:** `check_urdf arm_top.urdf` passes without errors

### P1-4. Fix CMakeLists.txt install errors
- **File:** `src/vehicle_arm_sim/CMakeLists.txt`
- **What:** Installs `config/` directory that doesn't exist. Doesn't install `arm_top_urdf/` which is needed at runtime.
- **Fix:** Remove `config/` install line. Add `arm_top_urdf/` install if needed, or move its contents.
- **Verify:** `colcon build --packages-select vehicle_arm_sim` succeeds cleanly

### P1-5. Security: Bind web UIs to localhost
- **Files:** `src/vehicle_arm_sim/web_ui/editor_backend.py`, `src/vehicle_arm_sim/web_ui/testing_backend.py`, `src/vehicle_control/simulation/gazebo/web_ui/backend.py`
- **What:** All bind to `0.0.0.0` with CORS `*` and zero authentication. Anyone on the network can control joints, trigger E-STOP, and browse the filesystem.
- **Fix:** Change `host="0.0.0.0"` to `host="127.0.0.1"`. Restrict CORS origins. Add parameter/env var to opt into network binding when needed.
- **Verify:** Backend only accessible from localhost by default

### P1-6. Security: Fix path traversal in mesh serving
- **File:** `src/vehicle_arm_sim/web_ui/editor_backend.py`
- **What:** `/api/serve-external-mesh` serves files from arbitrary paths filtered only by extension. Attacker can read any `.stl`, `.obj`, `.png` on the system.
- **Fix:** Restrict served paths to the package's `meshes/` directory. Validate that resolved path starts with allowed prefix.
- **Verify:** Request for `../../etc/passwd.stl` is rejected

### P1-7. Security: Fix command injection in vehicle backend
- **File:** `src/vehicle_control/simulation/gazebo/web_ui/backend.py`
- **What:** Plant names from WebSocket messages interpolated into `subprocess.run` shell commands without sanitization.
- **Fix:** Use list-form `subprocess.run()` (no `shell=True`). Validate/sanitize plant names (alphanumeric + underscore only).
- **Verify:** Plant name with `;rm -rf /` is rejected or safely handled

### P1-8. Restore J5 cosine fix
- **File:** `src/vehicle_arm_sim/web_ui/testing_ui.js` (~line 643-658)
- **What:** Commit `b21ada438` correctly fixed J5 computation to use actual (clamped) J3 angle. Commit `cbf78c3c7` reverted this AND removed all joint clamping. Testing UI now sends out-of-range values.
- **Fix:** Restore the intermediate version: clamp J3 first, compute J5 from clamped angle, clamp J5.
- **Verify:** Cosine test at 75 degrees: J3 should clamp to -0.9 rad, J5 should be computed from 0.9 rad (not 1.309 rad)

---

## Priority 2: HIGH (Fix within Week 1)

### P2-1. Set up git-lfs for binary assets
- **What:** 82 MB of STL/OBJ/PNG files committed directly to git. Every clone downloads full history.
- **Fix:** Create `.gitattributes` tracking `*.stl`, `*.STL`, `*.obj`, `*.png` (in mesh dirs), `*.mtl` via git-lfs. Run `git lfs migrate import` to rewrite history (coordinate with team).
- **Effort:** 1-2 hours (including team coordination for force push)

### P2-2. Deduplicate mesh files (~24.6 MB of exact copies)
- **What:** Same textures/meshes copied across `vehicle_arm_sim/meshes/`, `vehicle_control/simulation/gazebo/meshes/`, and `vehicle_arm_sim/arm_top_urdf/meshes/`.
- **Fix:** Keep one canonical copy per mesh. Use symlinks or shared directory. Remove `cotton_plant_texture_original.png` (6.2 MB x4 copies — keep only the optimized version).
- **Verify:** All URDF/SDF mesh references still resolve after deduplication

### P2-3. Remove unused mesh files
- **What:** 7+ mesh files in `vehicle_arm_sim/meshes/` not referenced by the main URDF: `yanthra_link.STL`, `link5_origin.STL`, `link7.STL`, `camera_link.STL`, `camera_mount_link.STL`, `base_link.STL`, `ee_link.STL`
- **Fix:** Verify these are truly unused, then remove or move to an `archive/` directory
- **Verify:** `colcon build` + Gazebo launch still work after removal

### P2-4. Remove debug marker links from URDF
- **What:** Debug links (`jointt`, `jointt2`, `jointt4`, `jointt5`, and `_copy` variants) baked into production URDF
- **Fix:** Remove or make conditional via xacro parameter
- **Verify:** URDF validates, Gazebo launch works

### P2-5. Fix web UI CDN dependencies (offline fallback)
- **Files:** `src/vehicle_arm_sim/web_ui/testing_ui.html`, other HTML files
- **What:** CDN dependencies (roslib.js, nipplejs) with no local fallback. Field testing may lack internet.
- **Fix:** Bundle/vendor these libraries locally. Add them to the package.
- **Verify:** Web UIs work with no internet connection

### P2-6. Fix centroid.txt comment bug
- **File:** `src/yanthra_move/web_ui/arm_sim_bridge.py` (~line 259-261)
- **What:** Bridge writes `# comment` lines in centroid.txt. C++ reader uses `>>` which fails on `#` — zero detections will be read.
- **Fix:** Either remove comment lines from bridge output, or add comment-skipping logic to C++ reader
- **Verify:** Trigger Start in sim produces non-zero detections

### P2-7. Fix HARDWARE_OFFSET discrepancy
- **File:** `src/yanthra_move/web_ui/arm_sim_bridge.py`
- **What:** Uses `0.320` at line 96-98 and `0.290` at line 301 within the same file
- **Fix:** Use a single constant. Determine correct value (config says 0.290, C++ default is 0.320).
- **Verify:** Approach computation uses consistent offset

---

## Priority 3: MEDIUM (Fix within Week 2)

### P3-1. Add basic tests
- **What:** Zero tests across 11 commits. Mandatory per project TDD policy.
- **Tests needed:**
  - URDF validation test (parse URDF, check no errors)
  - Launch file smoke test (launch and verify nodes come up)
  - Joint limit boundary test (all joints within declared limits)
  - Web UI backend unit test (endpoint responses)
- **Framework:** gtest for C++, pytest for Python, launch_testing for ROS2

### P3-2. Convert URDF to xacro with arm macro
- **What:** 3 arms are copy-pasted with copy-suffix naming (`arm_link*`, `arm_link*_copy`, `arm_link*_copy1`). Error-prone and unmaintainable.
- **Fix:** Create xacro macro with arm index parameter. Generate arms programmatically.
- **Benefit:** Adding arm 4-6 becomes trivial. Eliminates copy-paste drift.

### P3-3. Align visual/collision geometry origins
- **What:** Several links have visual origins offset but collision at (0,0,0). Physics contacts won't match visuals.
- **Fix:** Set collision origin to match visual origin for affected links

### P3-4. Standardize Gazebo plugin filenames
- **What:** Mixed bare names (`gz-sim-joint-state-publisher-system`) and `.so` suffix (`libgz-sim-joint-position-controller-system.so`). Fragile across Gazebo versions.
- **Fix:** Use consistent style (prefer bare names for Harmonic+)

### P3-5. Fix port conflict (editor defaults to 8080)
- **File:** `src/vehicle_arm_sim/web_ui/editor_backend.py`
- **What:** Editor defaults to port 8080, which conflicts with Gazebo and project convention (8090)
- **Fix:** Change default to 8090 or a non-conflicting port

### P3-6. Migrate deprecated FastAPI lifecycle hooks
- **Files:** `testing_backend.py`, `backend.py`
- **What:** Uses `@app.on_event("startup")`/`@app.on_event("shutdown")` — deprecated
- **Fix:** Migrate to FastAPI lifespan context manager

### P3-7. Extract shared geo constants
- **Files:** `src/vehicle_control/simulation/gazebo/nodes/rtk_gps_simulator.py`, `web_ui/ekf_engine.py`
- **What:** WGS-84 constants (`a`, `e2`, reference lat/lon) duplicated
- **Fix:** Extract to shared `geo_constants.py` module

### P3-8. Add RNG seed parameter to RTK GPS simulator
- **File:** `src/vehicle_control/simulation/gazebo/nodes/rtk_gps_simulator.py`
- **What:** `random.Random()` instantiated without seed — simulations non-reproducible
- **Fix:** Add `seed` ROS2 parameter, default to a fixed value

### P3-9. Fix fragile project root detection
- **File:** `src/vehicle_control/simulation/gazebo/web_ui/backend.py`
- **What:** `_PROJECT_ROOT = Path(__file__).resolve().parents[4]` — breaks if file moves
- **Fix:** Use environment variable or `ament_index` package path lookup

### P3-10. Remove `colcon build` from WebSocket API
- **File:** `src/vehicle_control/simulation/gazebo/web_ui/backend.py`
- **What:** Any WebSocket client can trigger `colcon build` without safeguards
- **Fix:** Remove this capability or require explicit confirmation

---

## Priority 4: LOW (Track for later)

### P4-1. Decimate wheel STL meshes
- **What:** Wheel STLs are 6.9 MB each — likely over-tessellated for simulation
- **Fix:** Decimate to <1 MB per wheel using MeshLab or Blender
- **Benefit:** Faster Gazebo loading, smaller repo

### P4-2. Verify Meshy AI mesh licensing
- **What:** AI-generated meshes from Meshy AI — verify licensing terms for commercial/field use
- **Action:** Check Meshy AI terms of service for the plan used

### P4-3. Remove `GAZEBO_SIMULATION_COMPLETE.md` from docs/
- **What:** AI session artifact ("I've successfully created...") — not documentation
- **Action:** Delete `docs/GAZEBO_SIMULATION_COMPLETE.md` (content duplicated in sim guide)

### P4-4. Split monolith package
- **What:** `vehicle_arm_sim` is a monolith (URDF + launch + 2 web UIs + world + meshes)
- **Action:** Consider splitting into simulation package, web tools, and mesh assets

---

## Checklist Summary

| Priority | Items | Status |
|----------|-------|--------|
| P1 CRITICAL | 8 items | All pending |
| P2 HIGH | 7 items | All pending |
| P3 MEDIUM | 10 items | All pending |
| P4 LOW | 4 items | All pending |
| **Total** | **29 items** | |

**Recommended sequence:** P1-1 (hooks) → P1-2 (steering) → P1-3 (duplicate link) → P1-4 (CMake) → P1-8 (J5 cosine) → P1-5/6/7 (security) → P2-1 (git-lfs) → P2-2/3 (dedup) → rest
