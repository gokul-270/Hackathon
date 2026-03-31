## ADDED Requirements

### Requirement: Repeated reruns always complete
The RunController SHALL complete every run (emit `run_complete`) regardless of how
many consecutive reruns of the same scenario are initiated. Specifically, three
consecutive reruns with all-unreachable steps SHALL each produce a `run_complete`
event within 30 seconds.

#### Scenario: Third consecutive rerun receives run_complete
- **WHEN** the same scenario (with at least one unreachable step) is run three times in sequence
- **THEN** each run emits `run_complete` and the third run does not stall

#### Scenario: Unreachable tail step still emits step_complete
- **WHEN** the final step in a run is unreachable
- **THEN** `step_complete` is still emitted for that step with `terminal_status = "unreachable"`
- **AND** execution continues to emit `run_complete` afterward
