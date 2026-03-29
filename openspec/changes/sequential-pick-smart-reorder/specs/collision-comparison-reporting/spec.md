## MODIFIED Requirements

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

## RENAMED Requirements

### Requirement: Summarize Blocked And Skipped Together

- **FROM**: References to `overlap_zone_wait` in summary and mode names
- **TO**: References to `sequential_pick` for mode 3 and `smart_reorder` for mode 4
