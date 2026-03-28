### Requirement: Emit JSON Baseline Replay Summary

The system SHALL emit JSON per-step and per-run outputs for the baseline replay release.

#### Scenario: JSON output generated after run
- **WHEN** the replay run completes
- **THEN** JSON step and run summaries are produced

### Requirement: Produce Final Four-Mode Recommendation

The system SHALL produce a final recommendation across unrestricted replay, baseline replay,
geometry block, and overlap wait.

#### Scenario: Recommendation prefers zero collisions first
- **WHEN** four-mode results are available
- **THEN** the report recommends a zero-collision mode before comparing raw success counts

### Requirement: Summarize Blocked And Skipped Together

The final summary SHALL combine blocked and skipped picks in the high-level report summary.

#### Scenario: Blocked and skipped combined in summary
- **WHEN** the final run summary is generated
- **THEN** blocked and skipped picks appear as one combined summary count
