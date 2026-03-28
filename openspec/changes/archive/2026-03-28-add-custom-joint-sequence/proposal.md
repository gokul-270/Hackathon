## Why

The testing UI has no way to run a user-defined sequence of arm joint positions.
Testers must either drag sliders manually or rely on the cosine test (which is
formula-locked to `J5 = adj/cos(θ)`). A custom sequence player lets testers
script arbitrary joint movements per arm for repeatable, timed experiments —
critical for validating arm reach, hold stability, and multi-position workflows.

## What Changes

- Add a "Custom Joint Sequence" section to the center panel of `testing_ui.html`
  (placed below the E-STOP section, alongside the existing cosine test section)
- Each sequence step specifies J3 (rad), J4 (m), J5 (m), and hold duration (sec)
- Steps are defined via an in-browser editable table with Add Row / Remove Row controls
- Target arm selected per run: Arm 1, Arm 2, or Arm 3 (one at a time)
- Repeat count configurable: 1–N times or loop continuously until stopped
- Slider UI stays in sync with the currently executing step
- E-STOP integration: sequence aborts immediately when E-STOP is active
- Progress bar and per-step status indicators (same pattern as cosine test)

## Capabilities

### New Capabilities

- `joint-sequence-player`: Browser-side sequence player that publishes
  user-defined joint positions (J3, J4, J5) to a selected arm via rosbridge
  at user-specified hold intervals. Supports repeat/loop, live progress
  display, and immediate E-STOP abort.

### Modified Capabilities

(none — no existing specs to modify)

## Impact

- `web_ui/testing_ui.html`: new `<section>` in center panel
- `web_ui/testing_ui.js`: ~150 lines new sequence logic (reuses existing
  `publishArmJoint`, `sleep`, `ARM_CONFIGS`, `estopActive`, `updateSliderUI` —
  no new external dependencies)
- `web_ui/testing_ui.css`: styles for sequence table and numeric inputs
- No changes to `testing_backend.py`, `launch_testing_ui.sh`,
  `kinematics_node.py`, or `vehicle_arm.launch.py`
