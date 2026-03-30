## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|-----------|----------------------|
| 1. RED: Failing test | — | — |
| 2. GREEN: Implementation | 1 | — |
| 3. Verify & Commit | 2 | — |

---

## 1. RED: Write Failing Test [SEQUENTIAL]

- [x] 1.1 Add `from smart_reorder_scheduler import SmartReorderScheduler, FK_OFFSET` to
  imports in `web_ui/features/test_collision_diagnostics.py`
- [x] 1.2 Add `test_mode4_reorder_improves_gap()` function stub at the bottom of
  `test_collision_diagnostics.py` that:
  - builds a `step_map` from `_ARM1_POINTS` / `_ARM2_POINTS` globals (cam_z from index `[2]`)
  - calls `SmartReorderScheduler().reorder(step_map, arm1_steps, arm2_steps)`
  - asserts `reordered_min_j4_gap >= original_min_j4_gap`
  - skips via `pytest.skip()` when `paired_count < 2`
- [x] 1.3 Run the test and confirm it is RED (fails or errors) before proceeding:
  ```
  python3 -m pytest features/test_collision_diagnostics.py -s -v -k "reorder_improves_gap"
  ```

---

## 2. GREEN: Implement Before/After Table Printing [SEQUENTIAL]

- [x] 2.1 Add a `_print_reorder_table(title, step_map, paired_count, arm1_pts, arm2_pts)`
  helper (private, module-level) in `test_collision_diagnostics.py` that prints:
  - A header row: `Step │ arm1 cam_z │ arm1 j4 │ arm2 cam_z │ arm2 j4 │ j4 gap`
  - One row per step (0..N-1): paired steps show both arm values; solo tail rows
    show `---` in the missing arm's cam_z, j4, and gap columns with a `(solo armX)` label
  - A footer line: `  min paired gap: <X>m`
- [x] 2.2 Add a `_compute_min_gap(step_map, paired_count)` helper that returns the minimum
  j4 gap across only the paired steps (ignoring solo tail), using `FK_OFFSET - cam_z`
- [x] 2.3 Call the helpers from `test_mode4_reorder_improves_gap()`:
  - print BEFORE table with original `step_map`
  - print AFTER table with `reordered` step_map
  - print summary delta line:
    `Mode 4 reorder result: min_gap  <before>m → <after>m  (delta: <+/->Xm)`
- [x] 2.4 Run the full test again and confirm it is GREEN:
  ```
  python3 -m pytest features/test_collision_diagnostics.py -s -v -k "reorder_improves_gap"
  ```

---

## 3. Verify & Commit [SEQUENTIAL]

- [x] 3.1 Run the full `test_collision_diagnostics.py` to confirm no regressions in existing
  parametric tests:
  ```
  python3 -m pytest features/test_collision_diagnostics.py -s -v
  ```
- [x] 3.2 Inspect the printed before/after tables with `-s` to confirm:
  - Column alignment is readable
  - Solo tail rows display `---` correctly
  - Summary delta line is present and accurate
- [x] 3.3 Commit the change:
  ```
  feat: add mode4 reorder gap improvement test with before/after table
  ```
