## ADDED Requirements

### Requirement: Reorder Gap Improvement Assertion
The test SHALL run `SmartReorderScheduler.reorder()` against the real cam-point data
loaded from `arm1.csv` and `arm2.csv`, and assert that the minimum j4 gap across all
paired steps after reordering is greater than or equal to the minimum j4 gap before
reordering.

#### Scenario: Gap is preserved or improved with real CSV data
- **WHEN** `arm1.csv` and `arm2.csv` each contain at least 2 rows
- **THEN** `reordered_min_j4_gap >= original_min_j4_gap`

#### Scenario: Test skips when fewer than 2 pairs available
- **WHEN** `min(len(arm1_points), len(arm2_points)) < 2`
- **THEN** the test calls `pytest.skip()` with a message indicating more rows are needed

#### Scenario: Degenerate case where all cam_z values are identical
- **WHEN** all arm1 and arm2 cam_z values are equal
- **THEN** both original and reordered min gaps are 0 and the assertion passes (`0 >= 0`)

---

### Requirement: Before/After Diagnostic Table Output
The test SHALL print two fixed-width tables to stdout (visible with `-s`): one showing
the original step pairing order and one showing the reordered step pairing order. Each
table SHALL include per-step arm1 cam_z, arm1 j4, arm2 cam_z, arm2 j4, and j4 gap
columns. A summary line SHALL follow each table showing the minimum gap and a final
delta line comparing before and after.

#### Scenario: BEFORE table printed with original pairing
- **WHEN** the test runs
- **THEN** a BEFORE table is printed showing each step in original CSV row order with
  arm1 cam_z, arm1 j4, arm2 cam_z, arm2 j4, and j4 gap

#### Scenario: AFTER table printed with reordered pairing
- **WHEN** the test runs
- **THEN** an AFTER table is printed showing each step in the reordered pairing with
  the same columns as the BEFORE table

#### Scenario: Solo tail rows appear with dashes for missing arm
- **WHEN** `arm1.csv` and `arm2.csv` have different row counts
- **THEN** unmatched steps appear in both tables with `---` in the missing arm's
  cam_z, j4, and gap columns, and a label indicating `(solo arm1)` or `(solo arm2)`

#### Scenario: Summary delta line shows gap change
- **WHEN** the test runs
- **THEN** a summary line is printed showing
  `min_gap_before=<X>m  →  min_gap_after=<Y>m  (delta: <+/->Zm)`
