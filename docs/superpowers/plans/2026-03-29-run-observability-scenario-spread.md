# Run Observability & Scenario Spread — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cam coords to StepReport, spread scenario cam_z values for visual separation, and stream per-step run events via SSE to the frontend log panel.

**Architecture:** Three independent improvements executed in dependency order: C (StepReport fields) → A (scenario spread) → B (SSE logging). Part C is the smallest and has no dependencies. Part A is independent. Part B depends on C being done (uses cam coords from StepReport context) and adds the new `RunEventBus` module.

**Tech Stack:** Python 3.12, FastAPI, `threading.Condition`, `collections.deque`, `dataclasses`, SSE (`text/event-stream`), vanilla JS `EventSource`.

---

## Task 1: Add cam_x/cam_y/cam_z to StepReport (Part C)

**Files:**
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/json_reporter.py`
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/run_controller.py:329-353`
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/test_json_reporter.py`

- [ ] **Step 1.1: Write the failing test for cam coords in StepReport serialization**

Add this test to `test_json_reporter.py` (after the existing `make_step` fixture and before the first test):

```python
def test_step_report_cam_coords_appear_in_serialized_output():
    """StepReport cam_x/cam_y/cam_z fields must serialize via asdict()."""
    from dataclasses import asdict
    step = make_step(cam_x=0.65, cam_y=-0.001, cam_z=0.150)
    d = asdict(step)
    assert d["cam_x"] == 0.65
    assert d["cam_y"] == -0.001
    assert d["cam_z"] == 0.150
```

Note: `make_step` will need to accept `**kwargs` — update it:
```python
def make_step(**kwargs):
    defaults = dict(
        step_id=1, arm_id="arm_a", mode="unrestricted",
        candidate_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        applied_joints={"j3": 0.1, "j4": 0.2, "j5": 0.3},
        j5_blocked=False, near_collision=False, collision=False,
        min_j4_distance=None,
    )
    defaults.update(kwargs)
    return StepReport(**defaults)
```

- [ ] **Step 1.2: Run the test to verify it fails**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_json_reporter.py::test_step_report_cam_coords_appear_in_serialized_output -v
```

Expected: FAIL with `TypeError: StepReport.__init__() got an unexpected keyword argument 'cam_x'`

- [ ] **Step 1.3: Add cam_x/cam_y/cam_z fields to StepReport**

In `json_reporter.py`, after the `executed_in_gazebo` field (line 23), add:

```python
    cam_x: Optional[float] = None
    cam_y: Optional[float] = None
    cam_z: Optional[float] = None
```

The `Optional` import is already present.

- [ ] **Step 1.4: Run the test to verify it passes**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_json_reporter.py::test_step_report_cam_coords_appear_in_serialized_output -v
```

Expected: PASS

- [ ] **Step 1.5: Write the failing test for RunController populating cam coords**

Add this test to `test_run_controller.py` (find the section with StepReport-related tests):

```python
def test_run_controller_step_reports_include_cam_coords():
    """StepReport entries must include cam_x/cam_y/cam_z from the scenario step."""
    ctrl = RunController(mode=0)
    ctrl.load_scenario({
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.150},
        ]
    })
    summary = ctrl.run()
    reports = summary["step_reports"]
    assert len(reports) == 1
    assert reports[0]["cam_x"] == 0.65
    assert reports[0]["cam_y"] == -0.001
    assert reports[0]["cam_z"] == 0.150
```

- [ ] **Step 1.6: Run the test to verify it fails**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_run_controller.py::test_run_controller_step_reports_include_cam_coords -v
```

Expected: FAIL with `AssertionError` (cam_x/cam_y/cam_z are None, not the expected values)

- [ ] **Step 1.7: Wire cam coords in RunController.run() when constructing StepReport**

In `run_controller.py`, in the `self._reporter.add_step(StepReport(...))` call (around line 329), add the three cam fields. Find the block:

```python
                self._reporter.add_step(
                    StepReport(
                        step_id=step_id,
                        arm_id=arm_id,
                        mode=mode_name,
                        candidate_joints={
                            "j3": own_cand["j3"],
                            "j4": own_cand["j4"],
                            "j5": own_cand["j5"],
                        },
                        applied_joints={
                            "j3": own_applied["j3"],
                            "j4": own_applied["j4"],
                            "j5": own_applied["j5"],
                        },
                        j5_blocked=j5_blocked,
                        near_collision=near_col,
                        collision=col,
                        min_j4_distance=min_j4_dist,
                        skipped=own_skipped,
                        terminal_status=outcome["terminal_status"],
                        pick_completed=outcome["pick_completed"],
                        executed_in_gazebo=outcome["executed_in_gazebo"],
                    )
                )
```

Replace with:

```python
                own_step = arm_steps[arm_id]
                self._reporter.add_step(
                    StepReport(
                        step_id=step_id,
                        arm_id=arm_id,
                        mode=mode_name,
                        candidate_joints={
                            "j3": own_cand["j3"],
                            "j4": own_cand["j4"],
                            "j5": own_cand["j5"],
                        },
                        applied_joints={
                            "j3": own_applied["j3"],
                            "j4": own_applied["j4"],
                            "j5": own_applied["j5"],
                        },
                        j5_blocked=j5_blocked,
                        near_collision=near_col,
                        collision=col,
                        min_j4_distance=min_j4_dist,
                        skipped=own_skipped,
                        terminal_status=outcome["terminal_status"],
                        pick_completed=outcome["pick_completed"],
                        executed_in_gazebo=outcome["executed_in_gazebo"],
                        cam_x=own_step.cam_x,
                        cam_y=own_step.cam_y,
                        cam_z=own_step.cam_z,
                    )
                )
```

Note: `own_step = arm_steps[arm_id]` already exists as `args["step"]` in the `arm_execute_args` dict (line 287). Use `args["step"]` instead of a new `own_step` variable:

```python
                cam_step = arm_execute_args[arm_id]["step"]
```

And pass `cam_x=cam_step.cam_x, cam_y=cam_step.cam_y, cam_z=cam_step.cam_z`.

- [ ] **Step 1.8: Run all json_reporter and run_controller tests**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_json_reporter.py test_run_controller.py -v -k "not test_run_report_markdown"
```

Expected: all PASS

- [ ] **Step 1.9: Run the full test suite to confirm no regressions**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest -x -k "not test_run_report_markdown" -q
```

Expected: all existing tests pass (currently 432)

- [ ] **Step 1.10: Commit Part C**

```bash
git add pragati_ros2/src/vehicle_arm_sim/web_ui/json_reporter.py \
        pragati_ros2/src/vehicle_arm_sim/web_ui/run_controller.py \
        pragati_ros2/src/vehicle_arm_sim/web_ui/test_json_reporter.py \
        pragati_ros2/src/vehicle_arm_sim/web_ui/test_run_controller.py
git commit -m "feat: add cam_x/cam_y/cam_z fields to StepReport and wire in RunController"
```

---

## Task 2: Spread Scenario cam_z Values (Part A)

**Files:**
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/scenarios/geometry_pack.json`
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/scenarios/contention_pack.json`
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/test_geometry_scenario_pack.py`
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/test_contention_scenario_pack.py`

### FK verification (do this first, before writing any tests)

Before writing tests, compute the actual world positions and j4 gaps for candidate cam_z
values by running this script in the web_ui directory:

```python
# Run: python3 -c "exec(open('/tmp/verify_camz.py').read())"
import sys; sys.path.insert(0, '.')
from fk_chain import camera_to_world_fk, camera_to_arm, polar_decompose, ARM_CONFIGS
import math

def world_pos(arm_id, cam_z, cam_x=0.65, cam_y=-0.001):
    cfg = ARM_CONFIGS[arm_id]
    return camera_to_world_fk(cam_x, cam_y, cam_z, j3=0.0, j4=0.0, arm_config=cfg)

def j4_val(cam_z, cam_x=0.65, cam_y=-0.001):
    ax, ay, az = camera_to_arm(cam_x, cam_y, cam_z, j4_pos=0.0)
    return polar_decompose(ax, ay, az)["j4"]

# Test candidate values
for cz in [0.050, 0.100, 0.150, 0.200, 0.250, 0.300]:
    j4 = j4_val(cz)
    wx, wy, wz = world_pos("arm1", cz)
    print(f"cam_z={cz:.3f}  j4={j4:.4f}  world=({wx:.3f},{wy:.3f},{wz:.3f})")
```

Use the computed values to select cam_z entries that satisfy:
- All j4 values within [−0.250, 0.350]
- Any two cam_z values for the same arm produce world positions ≥ 5 cm apart
  (`sqrt((wx1−wx2)²+(wy1−wy2)²+(wz1−wz2)²) >= 0.05`)
- Required collision/safe gap constraints (see below)

### Collision/safe gap rule

Given arm1 cam_z `a` and arm2 cam_z `b` at the same step_id:
- j4_arm1 = j4_val(a), j4_arm2 = j4_val(b)
- gap = |j4_arm1 − j4_arm2|
- **colliding**: gap < 0.05
- **safe**: gap > 0.08

To get a **colliding** pair: choose arm1 and arm2 cam_z values that differ by ~0.030 m or less
(this produces a j4 gap < 0.05). Example: arm1=0.050, arm2=0.070 → gap ≈ 0.020.

To get a **safe** pair: choose cam_z values that differ by ≥ 0.130 m.
Example: arm1=0.050, arm2=0.200 → gap ≈ 0.150.

### Proposed geometry_pack.json cam_z values

These must be verified via the FK script above before committing. The goal:
- arm1 steps (3 total): cam_z values spread across ~0.05–0.25 (e.g. 0.050, 0.150, 0.250)
- arm2 steps (5 total): cam_z values spread across ~0.05–0.30 (e.g. 0.070, 0.100, 0.200, 0.250, 0.300)
- Step 0 (paired): arm1=0.050, arm2=0.070 → colliding (gap ≈ 0.020)
- Step 1 (paired): arm1=0.150, arm2=0.300 → safe (gap > 0.08)
- Step 2 (paired): arm1=0.050, arm2=0.070 → colliding (gap ≈ 0.020)  [overlap-heavy]

Adjust values based on FK verification output to ensure all constraints pass.

### Proposed contention_pack.json cam_z values

- arm1 steps (4 total): cam_z spread (e.g. 0.050, 0.100, 0.150, 0.250)
- arm2 steps (6 total): cam_z spread (e.g. 0.060, 0.120, 0.200, 0.260, 0.290, 0.320)
- Step 0 (paired): arm1=0.050, arm2=0.060 → colliding
- Step 1 (paired): arm1=0.100, arm2=0.120 → colliding
- Step 2 (paired): arm1=0.150, arm2=0.200 → to be measured
- Step 3 (paired): arm1=0.250, arm2=0.060 → safe (large gap)

- [ ] **Step 2.1: Run the FK verification script**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && python3 - <<'EOF'
import sys; sys.path.insert(0, '.')
from fk_chain import camera_to_world_fk, camera_to_arm, polar_decompose, ARM_CONFIGS
import math

def world_pos(arm_id, cam_z, cam_x=0.65, cam_y=-0.001):
    cfg = ARM_CONFIGS[arm_id]
    return camera_to_world_fk(cam_x, cam_y, cam_z, j3=0.0, j4=0.0, arm_config=cfg)

def j4_val(cam_z, cam_x=0.65, cam_y=-0.001):
    ax, ay, az = camera_to_arm(cam_x, cam_y, cam_z, j4_pos=0.0)
    return polar_decompose(ax, ay, az)["j4"]

print("--- cam_z → j4 mapping ---")
for cz in [0.050, 0.070, 0.100, 0.130, 0.150, 0.200, 0.250, 0.300, 0.320]:
    j4 = j4_val(cz)
    wx, wy, wz = world_pos("arm1", cz)
    print(f"cam_z={cz:.3f}  j4={j4:.4f}  world=({wx:.3f},{wy:.3f},{wz:.3f})")

print()
print("--- pairwise j4 gaps for candidate paired steps ---")
pairs = [(0.050, 0.070), (0.050, 0.200), (0.100, 0.130), (0.150, 0.300), (0.250, 0.060)]
for a, b in pairs:
    gap = abs(j4_val(a) - j4_val(b))
    print(f"arm1={a:.3f} arm2={b:.3f}  gap={gap:.4f}  {'COLLIDING' if gap<0.05 else 'SAFE' if gap>0.08 else 'near'}")
EOF
```

Record the output — use it to finalize the cam_z values in steps 2.3 and 2.4.

- [ ] **Step 2.2: Write the failing world-spread test for geometry_pack**

Add to `test_geometry_scenario_pack.py`:

```python
def test_geometry_pack_arm1_cotton_positions_are_spread_at_least_5cm_apart():
    """Each pair of arm1 cotton world positions must be >= 5 cm apart."""
    import math
    from fk_chain import camera_to_world_fk, ARM_CONFIGS
    steps = _load_geometry_pack()["steps"]
    arm1_steps = [s for s in steps if s["arm_id"] == "arm1"]
    cfg = ARM_CONFIGS["arm1"]
    positions = [
        camera_to_world_fk(s["cam_x"], s["cam_y"], s["cam_z"], j3=0.0, j4=0.0, arm_config=cfg)
        for s in arm1_steps
    ]
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            wx1, wy1, wz1 = positions[i]
            wx2, wy2, wz2 = positions[j]
            dist = math.sqrt((wx1-wx2)**2 + (wy1-wy2)**2 + (wz1-wz2)**2)
            assert dist >= 0.05, (
                f"arm1 steps {i} and {j} are only {dist:.4f} m apart "
                f"(cam_z: {arm1_steps[i]['cam_z']}, {arm1_steps[j]['cam_z']})"
            )


def test_geometry_pack_arm2_cotton_positions_are_spread_at_least_5cm_apart():
    """Each pair of arm2 cotton world positions must be >= 5 cm apart."""
    import math
    from fk_chain import camera_to_world_fk, ARM_CONFIGS
    steps = _load_geometry_pack()["steps"]
    arm2_steps = [s for s in steps if s["arm_id"] == "arm2"]
    cfg = ARM_CONFIGS["arm2"]
    positions = [
        camera_to_world_fk(s["cam_x"], s["cam_y"], s["cam_z"], j3=0.0, j4=0.0, arm_config=cfg)
        for s in arm2_steps
    ]
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            wx1, wy1, wz1 = positions[i]
            wx2, wy2, wz2 = positions[j]
            dist = math.sqrt((wx1-wx2)**2 + (wy1-wy2)**2 + (wz1-wz2)**2)
            assert dist >= 0.05, (
                f"arm2 steps {i} and {j} are only {dist:.4f} m apart "
                f"(cam_z: {arm2_steps[i]['cam_z']}, {arm2_steps[j]['cam_z']})"
            )
```

Also add similar tests to `test_contention_scenario_pack.py` (replace `_load_geometry_pack` with `_load_contention_pack` and arm counts accordingly).

- [ ] **Step 2.3: Run the new tests to confirm they fail**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_geometry_scenario_pack.py::test_geometry_pack_arm1_cotton_positions_are_spread_at_least_5cm_apart \
                  test_geometry_scenario_pack.py::test_geometry_pack_arm2_cotton_positions_are_spread_at_least_5cm_apart \
                  test_contention_scenario_pack.py::test_contention_pack_arm1_cotton_positions_are_spread_at_least_5cm_apart \
                  test_contention_scenario_pack.py::test_contention_pack_arm2_cotton_positions_are_spread_at_least_5cm_apart -v
```

Expected: FAIL (current cam_z values cluster within < 5 cm)

- [ ] **Step 2.4: Update geometry_pack.json with spread cam_z values**

Using the FK verification output from Step 2.1, replace `geometry_pack.json`.
The new file must satisfy all existing test constraints (verified in Step 2.6).

Example values (adjust to verified output — the key is that arm1 steps use widely
separated cam_z values, and arm2 steps use widely separated cam_z values):

```json
{
  "description": "Geometry pack: asymmetric independent-arm scenarios mixing colliding and safe positions",
  "steps": [
    {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.050},
    {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.070},
    {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.150},
    {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.300},
    {"step_id": 2, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.250},
    {"step_id": 2, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.100},
    {"step_id": 3, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.200},
    {"step_id": 4, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.250}
  ]
}
```

Verify that:
- arm1 cam_z values {0.050, 0.150, 0.250} produce world positions >= 5 cm apart
- arm2 cam_z values {0.070, 0.300, 0.100, 0.200, 0.250} produce world positions >= 5 cm apart
- step 0 (0.050 vs 0.070): j4 gap < 0.05 → colliding ✓
- step 1 (0.150 vs 0.300): j4 gap > 0.08 → safe ✓
- step 2 (0.250 vs 0.100): measure gap, must be overlap-heavy (< 0.12) for 2 of 3 paired steps

Adjust the exact values based on FK output until all constraints are satisfied.

- [ ] **Step 2.5: Update contention_pack.json with spread cam_z values**

```json
{
  "description": "Contention pack: asymmetric independent-arm scenarios for overlap-zone contention",
  "steps": [
    {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.050},
    {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.070},
    {"step_id": 1, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.150},
    {"step_id": 1, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.170},
    {"step_id": 2, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.050},
    {"step_id": 2, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.300},
    {"step_id": 3, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.250},
    {"step_id": 3, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.070},
    {"step_id": 4, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.230},
    {"step_id": 5, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.130}
  ]
}
```

arm1 cam_z: {0.050, 0.150, 0.050, 0.250} — note step_ids 0 and 2 reuse cam_z=0.050
which is intentional (same cotton position, second pick attempt). If the test requires
all arm1 positions to be spread, use 0.050, 0.150, 0.100, 0.250 for step_ids 0–3.

Adjust based on FK output to ensure all constraints pass.

- [ ] **Step 2.6: Run all scenario pack tests**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_geometry_scenario_pack.py test_contention_scenario_pack.py -v
```

Expected: all PASS. If any structural test fails (collision/safe gap), adjust cam_z values
and re-run. The FK script output from Step 2.1 provides all the data needed.

- [ ] **Step 2.7: Run the full test suite**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest -x -k "not test_run_report_markdown" -q
```

Expected: all pass (count will be +4 from the new spread tests)

- [ ] **Step 2.8: Commit Part A**

```bash
git add pragati_ros2/src/vehicle_arm_sim/web_ui/scenarios/geometry_pack.json \
        pragati_ros2/src/vehicle_arm_sim/web_ui/scenarios/contention_pack.json \
        pragati_ros2/src/vehicle_arm_sim/web_ui/test_geometry_scenario_pack.py \
        pragati_ros2/src/vehicle_arm_sim/web_ui/test_contention_scenario_pack.py
git commit -m "feat: spread cam_z values for visual cotton separation in scenario files"
```

---

## Task 3: RunEventBus Module (Part B — foundation)

**Files:**
- Create: `pragati_ros2/src/vehicle_arm_sim/web_ui/run_event_bus.py`
- Create: `pragati_ros2/src/vehicle_arm_sim/web_ui/test_run_event_bus.py`

- [ ] **Step 3.1: Write the failing tests for RunEventBus**

Create `test_run_event_bus.py`:

```python
"""Tests for RunEventBus — thread-safe event bus for run observability."""
import threading
import time

import pytest


def test_run_event_bus_emit_and_subscribe_delivers_event():
    """An emitted event must be delivered to a waiting subscriber."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    received = []

    def consume():
        for evt in bus.subscribe():
            received.append(evt)
            break  # consume one then stop

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)  # let subscriber block
    bus.emit({"type": "test", "value": 42})
    t.join(timeout=1.0)
    assert received == [{"type": "test", "value": 42}]


def test_run_event_bus_close_unblocks_subscriber():
    """Calling close() must cause subscribe() to stop yielding."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    received = []

    def consume():
        for evt in bus.subscribe():
            received.append(evt)

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)
    bus.close()
    t.join(timeout=1.0)
    assert not t.is_alive(), "subscribe() did not stop after close()"


def test_run_event_bus_emit_multiple_events_in_order():
    """Multiple emitted events must be delivered in emission order."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    received = []

    def consume():
        for evt in bus.subscribe():
            received.append(evt["n"])
            if evt["n"] == 2:
                break

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)
    bus.emit({"type": "x", "n": 0})
    bus.emit({"type": "x", "n": 1})
    bus.emit({"type": "x", "n": 2})
    t.join(timeout=1.0)
    assert received == [0, 1, 2]


def test_run_event_bus_reset_clears_state_and_allows_new_subscriptions():
    """After reset(), a new subscribe() must work normally."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    bus.emit({"type": "old"})
    bus.close()
    bus.reset()

    received = []

    def consume():
        for evt in bus.subscribe():
            received.append(evt)
            break

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)
    bus.emit({"type": "new"})
    t.join(timeout=1.0)
    assert received == [{"type": "new"}]


def test_run_event_bus_is_thread_safe_under_concurrent_emitters():
    """100 concurrent emitters must all deliver without data loss."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    received = []
    stop = threading.Event()

    def consume():
        for evt in bus.subscribe():
            received.append(evt)
            if stop.is_set() and len(received) >= 100:
                break

    t = threading.Thread(target=consume)
    t.start()
    time.sleep(0.01)

    emitters = []
    for i in range(100):
        e = threading.Thread(target=bus.emit, args=({"type": "x", "n": i},))
        emitters.append(e)
    for e in emitters:
        e.start()
    for e in emitters:
        e.join()

    stop.set()
    bus.close()
    t.join(timeout=2.0)
    assert len(received) == 100
```

- [ ] **Step 3.2: Run the tests to verify they fail**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_run_event_bus.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'run_event_bus'`

- [ ] **Step 3.3: Implement RunEventBus**

Create `run_event_bus.py`:

```python
"""Thread-safe event bus for streaming run observability events."""
import collections
import threading
from typing import Generator


class RunEventBus:
    """Thread-safe in-memory event bus for per-step run events.

    Producers call emit(). Consumers iterate subscribe() which blocks until
    new events arrive or close() is called.
    """

    def __init__(self) -> None:
        self._lock = threading.Condition(threading.Lock())
        self._queue: collections.deque = collections.deque()
        self._closed = False

    def emit(self, event: dict) -> None:
        """Append an event and notify all waiting subscribers."""
        with self._lock:
            self._queue.append(event)
            self._lock.notify_all()

    def subscribe(self) -> Generator[dict, None, None]:
        """Yield events as they arrive. Returns when close() is called."""
        cursor = 0
        while True:
            with self._lock:
                while cursor >= len(self._queue) and not self._closed:
                    self._lock.wait()
                while cursor < len(self._queue):
                    yield self._queue[cursor]
                    cursor += 1
                if self._closed:
                    return

    def close(self) -> None:
        """Signal all subscribers to stop. Idempotent."""
        with self._lock:
            self._closed = True
            self._lock.notify_all()

    def reset(self) -> None:
        """Clear all events and re-arm for the next run."""
        with self._lock:
            self._queue.clear()
            self._closed = False
```

- [ ] **Step 3.4: Run the tests to verify they pass**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_run_event_bus.py -v
```

Expected: all 5 PASS

- [ ] **Step 3.5: Run the full suite**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest -x -k "not test_run_report_markdown" -q
```

Expected: all pass

---

## Task 4: Wire EventBus into RunController (Part B — emission)

**Files:**
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/run_controller.py`
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/test_run_controller.py`

- [ ] **Step 4.1: Write the failing test for RunController event emission**

Add to `test_run_controller.py`:

```python
def test_run_controller_emits_step_start_and_complete_events():
    """RunController must emit step_start and step_complete events per arm per step."""
    from run_event_bus import RunEventBus
    bus = RunEventBus()
    ctrl = RunController(mode=0, event_bus=bus)
    ctrl.load_scenario({
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.150},
            {"step_id": 0, "arm_id": "arm2", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.300},
        ]
    })
    ctrl.run()
    bus.close()

    events = list(bus._queue)
    types = [e["type"] for e in events]
    assert "step_start" in types
    assert "step_complete" in types
    assert "run_complete" in types

    step_starts = [e for e in events if e["type"] == "step_start"]
    assert len(step_starts) == 2  # one per arm
    arm_ids_started = {e["arm_id"] for e in step_starts}
    assert "arm1" in arm_ids_started
    assert "arm2" in arm_ids_started

    run_complete = next(e for e in events if e["type"] == "run_complete")
    assert "total_steps" in run_complete


def test_run_controller_emits_no_events_when_no_event_bus():
    """RunController with no event_bus must not raise — events are silently dropped."""
    ctrl = RunController(mode=0)  # no event_bus
    ctrl.load_scenario({
        "steps": [
            {"step_id": 0, "arm_id": "arm1", "cam_x": 0.65, "cam_y": -0.001, "cam_z": 0.150},
        ]
    })
    summary = ctrl.run()  # must not raise
    assert "total_steps" in summary
```

- [ ] **Step 4.2: Run to confirm failure**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_run_controller.py::test_run_controller_emits_step_start_and_complete_events \
                  test_run_controller.py::test_run_controller_emits_no_events_when_no_event_bus -v
```

Expected: FAIL with `TypeError: RunController.__init__() got an unexpected keyword argument 'event_bus'`

- [ ] **Step 4.3: Add event_bus parameter to RunController.__init__**

In `run_controller.py`, add the import at the top (after existing imports):

```python
from typing import Optional
# If Optional already imported, just add:
# (it is already imported via the existing Optional[float] usage)
```

Add `run_event_bus` import:
```python
# At the top of run_controller.py, after the existing imports:
try:
    from run_event_bus import RunEventBus as _RunEventBus
except ImportError:
    _RunEventBus = None
```

Add `event_bus` parameter to `__init__`:
```python
    def __init__(
        self,
        mode: int = BaselineMode.UNRESTRICTED,
        executor: Optional[object] = None,
        arm_pair: tuple = ("arm1", "arm2"),
        spawn_fn=None,
        remove_fn=None,
        event_bus=None,
    ) -> None:
```

Store it:
```python
        self._event_bus = event_bus
```

Add a helper method to `RunController`:
```python
    def _emit(self, event: dict) -> None:
        """Emit an event to the bus if one is configured. No-op otherwise."""
        if self._event_bus is not None:
            self._event_bus.emit(event)
```

- [ ] **Step 4.4: Emit step_start, step_complete, and run_complete from run()**

In `run_controller.py`, in the `run()` method:

**Before** the `with ThreadPoolExecutor(max_workers=2) as pool:` executor dispatch block
(after `arm_execute_args` is fully built, around line 290), add per-arm step_start emission:

```python
            # Emit step_start event for each active arm
            for arm_id in sorted(arm_execute_args.keys()):
                args = arm_execute_args[arm_id]
                self._emit({
                    "type": "step_start",
                    "arm_id": arm_id,
                    "step_id": step_id,
                    "target_j3": round(args["applied"]["j3"], 4),
                    "target_j4": round(args["applied"]["j4"], 4),
                    "target_j5": round(args["applied"]["j5"], 4),
                    "mode": mode_name,
                })
```

**After** the StepReport recording loop (after the `prev_joints` update block, still inside
the `for step_id in sorted(step_map.keys()):` loop), add per-arm step_complete emission:

```python
            # Emit step_complete event for each active arm
            for arm_id in sorted(arm_execute_args.keys()):
                outcome = outcomes[arm_id]
                self._emit({
                    "type": "step_complete",
                    "arm_id": arm_id,
                    "step_id": step_id,
                    "terminal_status": outcome["terminal_status"],
                    "pick_completed": outcome["pick_completed"],
                    "collision": col,
                    "near_collision": near_col,
                    "skipped": skipped_flags.get(arm_id, False),
                })
```

**After** `self._last_summary = ...` (the last line of `run()` before `return`), add:

```python
        self._emit({
            "type": "run_complete",
            "total_steps": total_steps,
            "collisions": self._last_summary.get("steps_with_collision", 0),
            "completed_picks": self._last_summary.get("completed_picks", 0),
        })
```

- [ ] **Step 4.5: Run the new tests**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_run_controller.py::test_run_controller_emits_step_start_and_complete_events \
                  test_run_controller.py::test_run_controller_emits_no_events_when_no_event_bus -v
```

Expected: PASS

- [ ] **Step 4.6: Run the full test suite**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest -x -k "not test_run_report_markdown" -q
```

Expected: all pass

---

## Task 5: SSE Endpoint and cotton_spawn Emission (Part B — transport)

**Files:**
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_backend.py`

- [ ] **Step 5.1: Write the failing test for SSE endpoint**

Add to `test_testing_backend.py` (find the section with `run_start` tests):

```python
def test_run_events_endpoint_returns_event_stream_content_type():
    """GET /api/run/events must return text/event-stream content type."""
    from fastapi.testclient import TestClient
    from testing_backend import app
    with TestClient(app) as client:
        # Use stream=True to avoid blocking on the full response
        with client.stream("GET", "/api/run/events") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            # Close immediately — just verifying headers
```

- [ ] **Step 5.2: Run to confirm failure**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_testing_backend.py::test_run_events_endpoint_returns_event_stream_content_type -v
```

Expected: FAIL with 404 or attribute error (endpoint does not exist yet)

- [ ] **Step 5.3: Add the event bus and SSE endpoint to testing_backend.py**

In `testing_backend.py`, after the existing imports (near the top), add:

```python
from fastapi.responses import StreamingResponse
from run_event_bus import RunEventBus
```

Near the module-level state variables (where `_run_state`, `_current_run_result` etc. are
defined), add:

```python
_event_bus: RunEventBus = RunEventBus()
```

Add the SSE endpoint (place it near the other `/api/run/` endpoints):

```python
@app.get("/api/run/events")
async def run_events():
    """SSE stream of per-step run events. Opens before POST /api/run/start."""
    async def _generator():
        import json as _json
        import asyncio
        loop = asyncio.get_event_loop()
        gen = _event_bus.subscribe()
        try:
            while True:
                try:
                    event = await loop.run_in_executor(None, next, gen)
                    yield f"data: {_json.dumps(event)}\n\n"
                    if event.get("type") == "run_complete":
                        return
                except StopIteration:
                    return
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 5.4: Emit cotton_spawn from _run_spawn_cotton**

In `_run_spawn_cotton` (line 974), after `_gz_spawn_model(name, sdf, wx, wy, wz, world_name)` (line 996), add:

```python
    _event_bus.emit({
        "type": "cotton_spawn",
        "arm_id": arm_id,
        "step_id": -1,  # step_id not available here; caller context sets it
        "cam_x": cam_x,
        "cam_y": cam_y,
        "cam_z": cam_z,
        "world_x": round(wx, 4),
        "world_y": round(wy, 4),
        "world_z": round(wz, 4),
        "model_name": name,
    })
```

Note: `step_id` is not directly available in `_run_spawn_cotton` since it's called via
`RunController._spawn_one`. To carry step_id through, update `_run_spawn_cotton` to accept
an optional `step_id: int = -1` parameter and pass it from `RunController._spawn_one`.

Update `_run_spawn_cotton` signature:
```python
def _run_spawn_cotton(
    arm_id: str,
    cam_x: float,
    cam_y: float,
    cam_z: float,
    j4_pos: float,
    step_id: int = -1,
) -> str:
```

Update `RunController._spawn_one` (inside `run()`) to pass step_id:
```python
        def _spawn_one(item):
            step_id, arm_id, step = item
            try:
                model_name = self._spawn_fn(arm_id, step.cam_x, step.cam_y, step.cam_z, 0.0, step_id)
            except Exception:
                model_name = ""
            return (step_id, arm_id), model_name
```

Also update `run_start` to wire the event bus into the controller:

```python
    controller = RunController(
        req.mode,
        executor=executor,
        arm_pair=tuple(req.arm_pair),
        spawn_fn=_run_spawn_cotton,
        remove_fn=_run_remove_cotton,
        event_bus=_event_bus,
    )
```

And reset + wire the run_id for the run_complete event:

```python
    _event_bus.reset()
    # ... existing controller setup ...
    summary = await asyncio.to_thread(controller.run)
    # After run, emit run_complete with run_id
    # (run_complete is emitted by RunController.run() already, but run_id is only known here)
```

To include `run_id` in `run_complete`, pass run_id to RunController or emit a second
event from the endpoint. The simplest approach: emit a supplementary `run_complete` event
from `run_start` after `controller.run()` finishes, which includes `run_id`. The controller's
`run_complete` already carries `total_steps`, `collisions`, `completed_picks` — the endpoint
adds `run_id`:

```python
    _event_bus.emit({
        "type": "run_complete",
        "run_id": run_id,
        "total_steps": summary.get("total_steps", 0),
        "collisions": summary.get("steps_with_collision", 0),
        "completed_picks": summary.get("completed_picks", 0),
    })
    _event_bus.close()
```

Remove the `run_complete` emission from `RunController.run()` — it's now the endpoint's
responsibility to emit the final event with run_id.

- [ ] **Step 5.5: Run the SSE test**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest test_testing_backend.py::test_run_events_endpoint_returns_event_stream_content_type -v
```

Expected: PASS

- [ ] **Step 5.6: Run the full suite**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest -x -k "not test_run_report_markdown" -q
```

Expected: all pass

---

## Task 6: Frontend EventSource Consumer (Part B — frontend)

**Files:**
- Modify: `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.js`

Frontend changes are not covered by Python pytest. Playwright E2E tests would be needed
for full coverage, but per the design the SSE delivery is unit-tested at the backend level.
The frontend change is mechanical — wire EventSource to the existing `log()` function.

- [ ] **Step 6.1: Update setupRunFlow() in testing_ui.js**

Find `function setupRunFlow()` (line 1468). Replace the `startBtn.addEventListener('click', async () => {` block with the version below. The only changes are:
- Open EventSource before fetch
- Add onmessage handler
- Close EventSource in both success and error paths

```javascript
        startBtn.addEventListener('click', async () => {
            statusEl.textContent = 'Starting run...';
            reportLinks.style.display = 'none';

            // Resolve scenario data
            let scenarioData = null;

            // 1. Check file input first
            const fileInput = document.getElementById('run-scenario-file');
            if (fileInput && fileInput.files.length > 0) {
                try {
                    const text = await fileInput.files[0].text();
                    scenarioData = JSON.parse(text);
                } catch (e) {
                    statusEl.textContent = 'Error: could not parse JSON file.';
                    return;
                }
            }

            // 2. Fall back to preset select
            if (!scenarioData) {
                const presetSelect = document.getElementById('run-scenario-select');
                const preset = presetSelect ? presetSelect.value : '';
                if (preset) {
                    const presetMap = {
                        contention: '/scenarios/contention_pack.json',
                        geometry: '/scenarios/geometry_pack.json',
                    };
                    try {
                        const resp = await fetch(presetMap[preset]);
                        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                        scenarioData = await resp.json();
                    } catch (e) {
                        statusEl.textContent = `Error: could not load preset scenario.`;
                        return;
                    }
                }
            }

            if (!scenarioData) {
                statusEl.textContent = 'Error: no scenario selected.';
                return;
            }

            const modeSelect = document.getElementById('run-mode-select');
            const mode = modeSelect ? parseInt(modeSelect.value, 10) : 0;

            const armPairSelect = document.getElementById('run-arm-pair-select');
            const armPair = armPairSelect ? armPairSelect.value.split(',') : ['arm1', 'arm2'];

            // Open SSE stream before starting the run so we catch all events
            var evtSource = new EventSource('/api/run/events');
            evtSource.onmessage = function(e) {
                try {
                    var evt = JSON.parse(e.data);
                    if (evt.type === 'cotton_spawn') {
                        log(
                            'Spawn: ' + evt.arm_id + ' step' + evt.step_id +
                            ' cam(' + evt.cam_x.toFixed(3) + ',' + evt.cam_y.toFixed(3) + ',' + evt.cam_z.toFixed(3) + ')' +
                            ' \u2192 world(' + evt.world_x.toFixed(3) + ',' + evt.world_y.toFixed(3) + ',' + evt.world_z.toFixed(3) + ')',
                            'success'
                        );
                    } else if (evt.type === 'step_start') {
                        log(
                            'Step: ' + evt.arm_id + ' step' + evt.step_id +
                            ' \u2192 j3=' + evt.target_j3.toFixed(3) +
                            ' j4=' + evt.target_j4.toFixed(3) +
                            ' j5=' + evt.target_j5.toFixed(3) +
                            ' [' + evt.mode + ']'
                        );
                    } else if (evt.type === 'step_complete') {
                        var cls = evt.pick_completed ? 'success' : 'warn';
                        log(
                            'Done: ' + evt.arm_id + ' step' + evt.step_id +
                            ' ' + evt.terminal_status +
                            ' pick=' + evt.pick_completed,
                            cls
                        );
                    } else if (evt.type === 'run_complete') {
                        log(
                            'Run complete: ' + evt.total_steps + ' steps, ' +
                            evt.collisions + ' collisions, ' +
                            evt.completed_picks + ' picks',
                            'success'
                        );
                        evtSource.close();
                    }
                } catch (err) {
                    log('SSE parse error: ' + err.message, 'error');
                }
            };
            evtSource.onerror = function() {
                evtSource.close();
            };

            try {
                const resp = await fetch('/api/run/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode, scenario: scenarioData, arm_pair: armPair }),
                });
                if (!resp.ok) {
                    evtSource.close();
                    const err = await resp.text();
                    statusEl.textContent = `Run failed: ${err}`;
                    return;
                }
                const data = await resp.json();
                statusEl.textContent = `Run complete (id: ${data.run_id})`;
                jsonLink.href = '/api/run/report/json';
                mdLink.href = '/api/run/report/markdown';
                reportLinks.style.display = '';
            } catch (e) {
                evtSource.close();
                statusEl.textContent = `Error: ${e.message}`;
            }
        });
```

- [ ] **Step 6.2: Verify no Python tests were broken**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest -x -k "not test_run_report_markdown" -q
```

Expected: all pass (JS changes don't affect Python tests)

---

## Task 7: Final Integration and Commit (Part B complete)

- [ ] **Step 7.1: Run the complete test suite one final time**

```bash
cd pragati_ros2/src/vehicle_arm_sim/web_ui && \
python3 -m pytest -k "not test_run_report_markdown" -q
```

Note the final test count. Expected: all pass.

- [ ] **Step 7.2: Verify test file list for commit**

```bash
git diff --name-only
```

Expected files changed:
- `pragati_ros2/src/vehicle_arm_sim/web_ui/run_event_bus.py` (new)
- `pragati_ros2/src/vehicle_arm_sim/web_ui/test_run_event_bus.py` (new)
- `pragati_ros2/src/vehicle_arm_sim/web_ui/run_controller.py`
- `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_backend.py`
- `pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.js`

- [ ] **Step 7.3: Commit Part B**

```bash
git add pragati_ros2/src/vehicle_arm_sim/web_ui/run_event_bus.py \
        pragati_ros2/src/vehicle_arm_sim/web_ui/test_run_event_bus.py \
        pragati_ros2/src/vehicle_arm_sim/web_ui/run_controller.py \
        pragati_ros2/src/vehicle_arm_sim/web_ui/testing_backend.py \
        pragati_ros2/src/vehicle_arm_sim/web_ui/testing_ui.js
git commit -m "feat: add RunEventBus, SSE endpoint, and per-step run logging"
```

---

## Task 8: Commit design doc and plan

- [ ] **Step 8.1: Commit design artifacts**

```bash
git add docs/superpowers/specs/2026-03-29-run-observability-scenario-spread-design.md \
        docs/superpowers/plans/2026-03-29-run-observability-scenario-spread.md
git commit -m "chore: add design and plan for run observability and scenario spread"
```
