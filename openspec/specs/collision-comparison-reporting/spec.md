### Requirement: Emit JSON Baseline Replay Summary

The system SHALL emit JSON per-step and per-run outputs for the baseline replay release.

#### Scenario: JSON output generated after run
- **WHEN** the replay run completes
- **THEN** JSON step and run summaries are produced

### Requirement: Produce Three-Mode Markdown Comparison

The system SHALL produce a Markdown comparison report for unrestricted replay, baseline replay, and
geometry block replay.

#### Scenario: Markdown report emitted after three-mode run set
- **WHEN** the three-mode run set completes
- **THEN** a Markdown comparison report is produced
