## MODIFIED Requirements

### Requirement: Synchronize Dual-Arm Replay Steps

The system SHALL execute each arm's step list in a dedicated thread. Arms SHALL run
independently without step synchronisation: one arm advancing to its next step SHALL
NOT wait for the peer arm to finish its current step. Within a single arm thread,
steps SHALL be processed sequentially. `RunController.run()` SHALL return only after
all arm threads have completed or been aborted by E-STOP.

Collision avoidance mode logic, peer-state exchange, and truth-monitor observation
remain per-step but use the peer's **latest published** candidate state (which may
correspond to a different step index in the peer's sequence) rather than a
guaranteed same-step-id synchronisation point.

Step report results SHALL be appended to the reporter by each arm thread as steps
complete. Final report order may interleave arm1 and arm2 step entries; consumers
SHALL NOT assume strict arm1-before-arm2 ordering within the step_reports list.

#### Scenario: arm1 does not wait for arm2 at each step boundary
- **GIVEN** arm1 has 3 steps and arm2 has 5 steps with equal per-step timing
- **WHEN** arm1 finishes step 0
- **THEN** arm1 starts step 1 immediately, regardless of arm2's current animation progress

#### Scenario: run() returns only after all arm threads are terminal
- **GIVEN** arm1 finishes in ~8 s and arm2 finishes in ~14 s
- **WHEN** run() is called
- **THEN** run() does not return until arm2 also completes (total ~14 s, not ~8 s)

#### Scenario: step reports contain all steps from both arms
- **GIVEN** arm1 has 3 steps and arm2 has 5 steps
- **WHEN** run() returns
- **THEN** the step_reports list contains exactly 8 entries (3 arm1 + 5 arm2)
