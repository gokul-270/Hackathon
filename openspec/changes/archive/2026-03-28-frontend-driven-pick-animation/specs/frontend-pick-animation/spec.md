## ADDED Requirements

### Requirement: Triple-publish joint command

The `triplePublish(topic, value)` async helper function SHALL publish the given value to the given ROS2 topic 3 times with 500ms gaps between publishes using `publishArmJoint()`. The function SHALL return a Promise that resolves after the third publish completes. This matches the reliability pattern used by `runCosineTest()` homing.

#### Scenario: Three publishes with 500ms spacing

- **WHEN** `triplePublish("/joint3_cmd", -0.3)` is called
- **THEN** `publishArmJoint("/joint3_cmd", -0.3)` is called 3 times
- **AND** each call is separated by approximately 500ms (±50ms)
- **AND** the total elapsed time is approximately 1000ms (±100ms)

#### Scenario: Uses publishArmJoint not gz topic

- **WHEN** `triplePublish` is called with any topic and value
- **THEN** the value is published via `publishArmJoint()` (rosbridge WebSocket pathway)
- **AND** no subprocess or `gz topic` command is invoked

### Requirement: Six-step pick animation sequence

The `executePickAnimation(armKey, cottonName, j3, j4, j5)` async function SHALL execute a 6-step animation sequence in strict order. Each step consists of a triple-publish to the arm's joint topic followed by `updateSliderUI()` and a hold delay. The steps SHALL be:

| Step | Joint | Value | Hold (ms) |
|------|-------|-------|-----------|
| 1 | J4 | j4 (lateral) | 800 |
| 2 | J3 | j3 (tilt) | 800 |
| 3 | J5 | j5 (extend) | 1400 |
| 4 | J5 | 0.0 (retract) | 800 |
| 5 | J3 | 0.0 (home) | 800 |
| 6 | J4 | 0.0 (home) | 900 |

After step 3 (J5 extend), the function SHALL call `POST /api/cotton/{cottonName}/mark-picked` before proceeding to step 4.

#### Scenario: Complete pick animation for arm1

- **WHEN** `executePickAnimation("arm1", "cotton_0", -0.3, 0.1, 0.25)` is called
- **THEN** step 1 publishes `0.1` to `/joint4_cmd` via triple-publish, updates sliders, waits 800ms
- **AND** step 2 publishes `-0.3` to `/joint3_cmd` via triple-publish, updates sliders, waits 800ms
- **AND** step 3 publishes `0.25` to `/joint5_cmd` via triple-publish, updates sliders, waits 1400ms
- **AND** `POST /api/cotton/cotton_0/mark-picked` is called after step 3
- **AND** step 4 publishes `0.0` to `/joint5_cmd` via triple-publish, updates sliders, waits 800ms
- **AND** step 5 publishes `0.0` to `/joint3_cmd` via triple-publish, updates sliders, waits 800ms
- **AND** step 6 publishes `0.0` to `/joint4_cmd` via triple-publish, updates sliders, waits 900ms

#### Scenario: Slider UI updates at each step

- **WHEN** step 2 (J3 tilt) completes its triple-publish for arm1
- **THEN** `updateSliderUI("arm1", j3Val, currentJ4, currentJ5)` is called with the current joint values
- **AND** the arm1 J3 slider DOM element reflects the new value

#### Scenario: Total animation duration

- **WHEN** `executePickAnimation` runs to completion without abort
- **THEN** total elapsed time is approximately 11.5 seconds (±1s)

### Requirement: Abort and E-STOP check at each step

Module-level `pickRunning` and `pickAborted` boolean variables SHALL track animation state. Before each step's triple-publish, `executePickAnimation()` SHALL check `pickAborted || estopActive`. If either is true, the function SHALL stop immediately without publishing further commands, and SHALL NOT call mark-picked if step 3 has not yet completed.

#### Scenario: E-STOP during step 2

- **WHEN** `executePickAnimation` is executing step 2 (J3 tilt)
- **AND** `estopActive` becomes `true` before step 3 begins
- **THEN** steps 3–6 are not executed
- **AND** `mark-picked` is NOT called
- **AND** the cotton remains with status `"spawned"`

#### Scenario: Abort during step 5

- **WHEN** `executePickAnimation` has completed step 3 (J5 extend) and mark-picked
- **AND** `pickAborted` is set to `true` during step 5
- **THEN** step 6 is not executed
- **AND** the cotton status is `"picked"` (mark-picked already called)

#### Scenario: pickRunning state transitions

- **WHEN** `executePickAnimation` starts
- **THEN** `pickRunning` is `true`
- **AND** when the animation completes (normally or via abort)
- **THEN** `pickRunning` is `false`

### Requirement: Status UI updates during animation

The frontend SHALL update the cotton status display text at each animation step to show the current phase. The phase names SHALL be: `"j4_lateral"`, `"j3_tilt"`, `"j5_extend"`, `"mark_picked"`, `"j5_retract"`, `"j3_home"`, `"j4_home"`.

#### Scenario: Status text during single pick

- **WHEN** `executePickAnimation` enters step 2
- **THEN** the status display shows "Picking cotton_0: j3_tilt" (or equivalent)

#### Scenario: Status text on completion

- **WHEN** `executePickAnimation` completes all 6 steps
- **THEN** the status display shows "Pick complete" (or equivalent)

#### Scenario: Status text on abort

- **WHEN** `executePickAnimation` is aborted during step 4
- **THEN** the status display shows "Pick aborted" (or equivalent)

### Requirement: Refactored cottonPick single-pick flow

The `cottonPick()` function SHALL call `POST /api/cotton/pick` to get compute-only joint values, then call `executePickAnimation()` with the returned values. If the response indicates the target is unreachable (`reachable: false`), the function SHALL show a red error toast and NOT start the animation.

#### Scenario: Successful single pick

- **WHEN** the user clicks the Pick button with a spawned cotton selected
- **THEN** `POST /api/cotton/pick` returns `{status: "ready", j3, j4, j5, arm, cotton_name, reachable: true}`
- **AND** `executePickAnimation(arm, cotton_name, j3, j4, j5)` is called
- **AND** the Pick button is disabled during animation

#### Scenario: Unreachable target

- **WHEN** the user clicks Pick and the backend returns `{reachable: false}`
- **THEN** a red error toast is shown with the reason
- **AND** no animation is started
- **AND** the Pick button remains enabled

### Requirement: Refactored cottonPickAll parallel flow

The `cottonPickAll()` function SHALL call `POST /api/cotton/pick-all` to get per-arm grouped joint values, then launch parallel async animations per arm via `Promise.all()`. Within each arm, cottons SHALL be picked sequentially. A helper `pickArmCottons(armKey, cottons)` SHALL loop through the arm's cotton list, calling `executePickAnimation()` for each.

#### Scenario: Two arms pick simultaneously

- **WHEN** arm1 has 2 cottons and arm3 has 1 cotton
- **AND** `cottonPickAll()` is called
- **THEN** arm1 and arm3 animations run concurrently via `Promise.all()`
- **AND** arm1 picks cotton_0 then cotton_1 sequentially
- **AND** arm3 picks cotton_2
- **AND** total time is approximately 2 × 11.5s = 23s (arm1 takes longer)

#### Scenario: Pick-all with nothing to pick

- **WHEN** all cottons are already picked and `cottonPickAll()` is called
- **THEN** the backend returns `{status: "nothing_to_pick"}`
- **AND** a status message indicates nothing to pick
- **AND** no animation is started

#### Scenario: Pick-all button disabled during animation

- **WHEN** pick-all animation is running
- **THEN** both the Pick and Pick All buttons are disabled
- **AND** they re-enable after all arms complete

### Requirement: Remove frontend polling code

The `pollPickStatus()` function, `pollPickAllStatus()` function, `_pickPollInterval` variable, and `_pickAllPollInterval` variable SHALL be removed from the frontend codebase. No `setInterval`-based polling for pick status SHALL exist.

#### Scenario: No polling functions exist

- **WHEN** the frontend code is inspected
- **THEN** no function named `pollPickStatus` or `pollPickAllStatus` exists
- **AND** no variable named `_pickPollInterval` or `_pickAllPollInterval` exists

#### Scenario: No setInterval for pick status

- **WHEN** the frontend code is searched for `setInterval` calls related to pick status
- **THEN** no such calls exist
