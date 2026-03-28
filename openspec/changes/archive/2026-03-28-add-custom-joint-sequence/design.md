## Context

The `testing_ui` currently offers two modes of arm control:
- **Manual sliders** — one joint at a time, no automation
- **Cosine test** — automated, but locked to the formula `J5 = adj / cos(θ)`

Neither supports replaying arbitrary, user-defined joint positions. The cosine
test (`runCosineTest` in `testing_ui.js`) already establishes the async
step-hold-step pattern, the `ARM_CONFIGS` topic map, `publishArmJoint`,
`updateSliderUI`, and E-STOP integration. The custom sequence player reuses all
of these — it is purely a frontend addition with no ROS2 or backend changes.

## Goals / Non-Goals

**Goals:**
- Add a "Custom Joint Sequence" section to the center panel (Option A: below
  E-STOP, above or alongside the cosine test section)
- Allow users to define arbitrary sequences of (J3, J4, J5, hold) steps in an
  editable table
- Publish to one selected arm (Arm 1, 2, or 3) per run
- Support repeat count (1–N) and continuous loop mode
- Abort immediately on E-STOP, with per-step status tracking
- Warn (but not block) when values exceed known joint limits

**Non-Goals:**
- Simultaneous multi-arm sequencing (one arm at a time, same as cosine test)
- Persisting sequences across page refreshes
- Server-side sequence storage or upload/download
- Trajectory interpolation between steps (discrete step-hold only)
- Changes to `testing_backend.py`, `launch_testing_ui.sh`, or any ROS2 node

## Decisions

### D1: Pure frontend — no backend changes

All joint publishing already flows through rosbridge via `publishArmJoint`.
The backend (`testing_backend.py`) has no role in arm joint control; it handles
spawn and E-STOP fallback only. Adding sequence logic there would introduce
unnecessary HTTP round-trips and coupling.

*Alternatives considered:* Backend sequence endpoint (rejected — adds latency,
requires rclpy node to hold state, breaks the existing rosbridge-direct pattern).

### D2: Reuse `runCosineTest` async/await pattern

The cosine test's `async function` + `await sleep()` loop is already proven in
production. The sequence player uses the identical structure:

```
async function runCustomSequence() {
    for (repeat 1..N or loop) {
        for each row in table {
            publishArmJoint(j3); publishArmJoint(j4); publishArmJoint(j5)
            updateSliderUI(...)
            await sleep(hold * 1000)
            check estopActive || sequenceAborted
        }
    }
}
```

This keeps the codebase consistent and avoids introducing timers or a separate
state machine.

### D3: Inline editable HTML table (not JSON/CSV paste)

A `<table>` with `<input type="number">` cells is the most direct mapping
of "rows of joint values". It gives immediate visual feedback, supports
add/remove row, and needs no parse step. For the sequence sizes typical in
bench testing (3–20 steps), a table is sufficient.

*Alternatives considered:* JSON textarea (faster for large sequences but
error-prone; no per-cell validation); CSV paste (similar issues). Could be
added later as an export/import feature without changing the core design.

### D4: Soft validation warnings, never block

Testers need to probe near-limit and over-limit behaviour in Gazebo. Blocking
prevents legitimate test cases. A yellow cell highlight + tooltip is sufficient
to signal out-of-range values without impeding execution.

Joint limits (from `JOINT_LIMITS` in `testing_backend.py` and slider `min/max`
in `testing_ui.html`):

| Joint | Min    | Max   | Unit |
|-------|--------|-------|------|
| J3    | −0.9   | 0.0   | rad  |
| J4    | −0.250 | 0.350 | m    |
| J5    | 0.0    | 0.450 | m    |

### D5: ARM_CONFIGS as the single source of arm→topic mapping

`ARM_CONFIGS` in `testing_ui.js` already maps `arm1/arm2/arm3` to their
respective topic triples. The sequence player reads `ARM_CONFIGS[selectedArm]`
directly — no new mapping table needed.

### D6: Repeat control — integer spinner + "∞" checkbox

A number input for repeat count (default 1, min 1) paired with a "Loop"
checkbox that, when checked, disables the number input and enables infinite
looping. This is the simplest UI that covers the two required modes without
ambiguity.

## Risks / Trade-offs

**Rosbridge delivery is best-effort** → Each step publishes once. For
reliability at very short hold durations (< 0.5 s), Gazebo may not settle at
the target position before the next command arrives. Mitigated by setting a
minimum hold of 0.1 s and documenting that meaningful mechanical settling
requires ≥ 1 s holds. No burst publishing (unlike E-STOP) — a single publish
per step is sufficient for position-controlled joints.

**Loop mode has no automatic exit** → If the user closes the browser tab
while looping, rosbridge disconnects and the last commanded position stays in
Gazebo. This is the same behaviour as a stale joystick command. Mitigated by
the existing E-STOP path on backend shutdown.

**Out-of-range commands reach Gazebo** → Gazebo joint controllers clamp at
URDF limits silently. The soft warning in the UI is the only user-facing
indicator. This is intentional (D4) and consistent with how the cosine test
already sends unclamped values at high θ angles.

**No persistence** → Sequences are lost on page refresh. Acceptable for the
current testing use case; a future export/import feature (JSON download/upload)
can be added without changing this design.

## Open Questions

- Should the sequence auto-home the selected arm (publish J3=J4=J5=0) before
  starting the first step, as the cosine test does? Currently not specified —
  left to implementer judgement (recommend: yes, with a 2 s settle, same as
  cosine test).
- Should rows support an optional "ramp time" in addition to "hold time"
  (i.e., how long to interpolate to the target)? Out of scope for now; flagged
  for a future enhancement if Gazebo joint controllers support it.
