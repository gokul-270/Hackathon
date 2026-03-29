### Requirement: Emit JSON Baseline Replay Summary

The system SHALL emit JSON per-step and per-run outputs for the baseline replay release, including explicit arm-step terminal outcomes and completed-pick totals.

#### Scenario: JSON output generated after run
- **WHEN** the replay run completes
- **THEN** JSON step and run summaries are produced
- **AND** each step summary includes explicit terminal outcome information for each active arm

### Requirement: Produce Final Four-Mode Recommendation

The system SHALL produce a final recommendation across all available modes. When five run summaries are supplied (unrestricted, baseline_j5_block_skip, geometry_block, sequential_pick, smart_reorder), the report heading SHALL read "Five-Mode Collision Comparison Report". When four summaries are supplied, the heading SHALL read "Four-Mode". When three, "Three-Mode". The recommendation logic (zero collisions first, then highest successful picks) is unchanged.

#### Scenario: Recommendation prefers zero collisions first

- **WHEN** multi-mode results are available
- **THEN** the report recommends a zero-collision mode before comparing raw success counts

#### Scenario: Five-mode report produces five-mode heading

- **WHEN** five run summaries are supplied (one per mode 0-4)
- **THEN** the report heading contains "Five-Mode"
- **AND** all five mode names appear in the comparison table

#### Scenario: Four-mode report still produces four-mode heading

- **WHEN** four run summaries are supplied
- **THEN** the report heading contains "Four-Mode"

#### Scenario: Blocked plus skipped column present for four or more modes

- **WHEN** four or more run summaries are supplied
- **THEN** the comparison table includes a "Blocked+Skipped" column

### Requirement: Summarize Blocked And Skipped Together

The final summary SHALL combine blocked and skipped picks in the high-level report summary while also exposing completed-pick totals separately.

#### Scenario: Blocked and skipped combined in summary
- **WHEN** the final run summary is generated
- **THEN** blocked and skipped picks appear as one combined summary count
- **AND** completed picks appear as a separate summary count
