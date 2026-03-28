## MODIFIED Requirements

### Requirement: Emit JSON Baseline Replay Summary

The system SHALL emit JSON per-step and per-run outputs for the baseline replay release, including explicit arm-step terminal outcomes and completed-pick totals.

#### Scenario: JSON output generated after run
- **WHEN** the replay run completes
- **THEN** JSON step and run summaries are produced
- **AND** each step summary includes explicit terminal outcome information for each active arm

### Requirement: Summarize Blocked And Skipped Together

The final summary SHALL combine blocked and skipped picks in the high-level report summary while also exposing completed-pick totals separately.

#### Scenario: Blocked and skipped combined in summary
- **WHEN** the final run summary is generated
- **THEN** blocked and skipped picks appear as one combined summary count
- **AND** completed picks appear as a separate summary count
