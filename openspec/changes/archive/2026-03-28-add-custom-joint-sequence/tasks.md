## Execution Plan

| Group | Depends On | Can Parallelize With |
|-------|------------|----------------------|
| 1     | —          | —                    |
| 2     | 1          | 3                    |
| 3     | 1          | 2                    |
| 4     | 2, 3       | —                    |

---

## 1. HTML Structure [SEQUENTIAL]

- [x] 1.1 Add `<section class="section custom-seq-section">` to the center panel
  in `testing_ui.html`, below the E-STOP section and above the cosine test section
- [x] 1.2 Add arm selector dropdown (`<select id="seq-arm-select">`) with options
  Arm 1, Arm 2, Arm 3
- [x] 1.3 Add repeat control: number input `<input id="seq-repeat-count">` (default 1,
  min 1) and a "Loop" checkbox `<input id="seq-loop">` that disables the number input
  when checked
- [x] 1.4 Add the sequence table with columns: #, J3 (rad), J4 (m), J5 (m),
  Hold (s), Delete — with `<thead>` and an empty `<tbody id="seq-table-body">`
- [x] 1.5 Add "Add Row" button `<button id="seq-btn-add-row">`,
  "Start" button `<button id="seq-btn-start">`, and
  "Stop" button `<button id="seq-btn-stop" disabled>`
- [x] 1.6 Add progress bar `<div id="seq-progress">` and label
  `<span id="seq-progress-label">` (hidden by default, same pattern as cosine test)

## 2. CSS Styles [PARALLEL with 3]

- [x] 2.1 Add `.custom-seq-section` layout styles to `testing_ui.css` — match
  existing `.arm-test-section` spacing and panel width behaviour
- [x] 2.2 Style the sequence table: compact row height, alternating row background,
  `.active-step` highlight class (reuse cosine test colour), `.warn-cell` yellow
  highlight for out-of-range values
- [x] 2.3 Style the number inputs inside table cells: `width: 70px`, no spinners on
  Firefox, consistent font size with the rest of the panel
- [x] 2.4 Style the repeat control row: inline flex, gap between the count input
  and the Loop checkbox label

## 3. JavaScript — Sequence Logic [PARALLEL with 2]

- [x] 3.1 Add `SEQ_JOINT_LIMITS` constant object in `testing_ui.js` mirroring the
  existing `JOINT_LIMITS` from the backend:
  `{ j3: { min: -0.9, max: 0.0 }, j4: { min: -0.25, max: 0.35 }, j5: { min: 0.0, max: 0.45 } }`
- [x] 3.2 Implement `seqAddRow(j3, j4, j5, hold)` — appends a new `<tr>` to
  `#seq-table-body` with editable `<input type="number">` cells and a delete button;
  defaults to `(0, 0, 0, 2.0)` when called with no arguments
- [x] 3.3 Implement `seqValidateRow(tr)` — checks each cell against `SEQ_JOINT_LIMITS`,
  adds/removes `warn-cell` class, sets tooltip showing valid range; returns array of
  warning strings (empty if clean)
- [x] 3.4 Attach `input` event listener on `#seq-table-body` to call `seqValidateRow`
  on the parent `<tr>` whenever any cell value changes
- [x] 3.5 Implement `seqReadRows()` — reads all `<tr>` rows from `#seq-table-body`
  and returns array of `{ j3, j4, j5, hold }` objects parsed as floats
- [x] 3.6 Implement `async runCustomSequence()` — main execution loop:
  reads arm selection from `#seq-arm-select` (maps to `ARM_CONFIGS[arm]`),
  reads rows via `seqReadRows()`, reads repeat count / loop flag,
  guards against empty table / rosbridge disconnected / estopActive,
  iterates passes × steps calling `publishArmJoint` + `updateSliderUI` + `await sleep`,
  checks `seqAborted || estopActive` before each step and after each hold,
  updates progress bar and row highlight (`active-step`) per step,
  marks each completed step `✅ Done` or `🛑 Aborted` in the status cell
- [x] 3.7 Add auto-home before first step: publish J3=J4=J5=0 to the selected arm
  3× with 500 ms between bursts, then `await sleep(2000)` — same pattern as
  `runCosineTest`; log "Homing selected arm before sequence..."
- [x] 3.8 Wire `#seq-btn-start` → `runCustomSequence()`,
  `#seq-btn-stop` → set `seqAborted = true`,
  `#seq-btn-add-row` → `seqAddRow()`,
  `#seq-loop` change → toggle disabled state of `#seq-repeat-count`

## 4. Integration & Verification [SEQUENTIAL]

- [x] 4.1 Add `seqAddRow()` call (×3 default rows) inside the existing `init()`
  function so the table is pre-populated on page load — gives users an immediate
  example to edit rather than an empty table
- [x] 4.2 Verify E-STOP abort: manually activate E-STOP mid-sequence in the browser
  and confirm the sequence halts without publishing further commands and logs
  "E-STOP ACTIVATED" (existing E-STOP path, no new code needed — just verify)
- [x] 4.3 Verify arm topic routing: with rosbridge connected, run a 1-step sequence
  on each arm and confirm the correct topics receive the publish
  (`/joint3_cmd` for Arm 1, `/joint3_copy_cmd` for Arm 2,
  `/arm_joint3_copy1_cmd` for Arm 3) by watching the log output
- [x] 4.4 Verify out-of-range warning: enter J3 = −1.5 (below −0.9 limit) and
  confirm the cell turns yellow and shows a tooltip, but Start is not blocked
- [x] 4.5 Verify repeat count: set repeat = 2 with a 2-step sequence and confirm
  the sequence runs exactly 4 step executions then stops automatically
- [x] 4.6 Verify loop mode: enable Loop checkbox, start a 2-step sequence, confirm
  it cycles continuously, then click Stop and confirm it halts cleanly
- [x] 4.7 Update the cache-busting version query strings on `testing_ui.css` and
  `testing_ui.js` `<script>` / `<link>` tags in `testing_ui.html` to force
  browser reload after deployment
