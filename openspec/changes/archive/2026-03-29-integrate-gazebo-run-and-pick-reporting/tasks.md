## Execution Plan

| Group | Depends On | Can Parallelize With |
| --- | --- | --- |
| 1 | None | None |
| 2 | 1 | None |
| 3 | 2 | 4 |
| 4 | 2 | 3 |
| 5 | 3, 4 | None |

## 1. [SEQUENTIAL] Define motion-backed execution seam

- [x] 1.1 Add a failing unit test for a new run-step executor abstraction that publishes Gazebo motion for an allowed arm-step
- [x] 1.2 Add a failing unit test proving a blocked arm-step does not publish Gazebo motion
- [x] 1.3 Implement the minimal executor module and publish adapter to make those tests pass
- [x] 1.4 Run the focused executor test file and confirm green
- [x] 1.5 Commit the green executor seam

## 2. [SEQUENTIAL] Wire controller and backend to execution flow

- [x] 2.1 Add a failing `RunController` test proving motion execution is invoked during `run()`
- [x] 2.2 Add a failing backend test proving `/api/run/start` triggers motion-backed execution through the controller path
- [x] 2.3 Add a failing controller test proving a paired step does not advance until both active arm outcomes are terminal
- [x] 2.4 Add a failing controller test proving a solo-tail step advances after the single active arm reaches terminal outcome
- [x] 2.5 Implement minimal controller and backend wiring to call the executor for allowed steps and honor terminal-outcome step advancement
- [x] 2.6 Run focused controller and backend tests and confirm green
- [x] 2.7 Commit the green controller/backend wiring

## 3. [PARALLEL with 4] Add explicit per-arm outcome reporting

- [x] 3.1 Add a failing `JsonReporter` test for `terminal_status` and `pick_completed` fields in step reports
- [x] 3.2 Add a failing `RunController` test proving completed, blocked, and skipped outcomes are emitted correctly
- [x] 3.3 Implement the minimal outcome model and reporter changes to satisfy those tests
- [x] 3.4 Run the focused reporter/controller tests and confirm green
- [x] 3.5 Commit the green outcome-reporting change

## 4. [PARALLEL with 3] Update run summaries and Markdown output

- [x] 4.1 Add a failing reporter test for completed-pick totals in run summary output
- [x] 4.2 Add a failing backend or E2E test proving `/api/run/report/markdown` includes completed-pick summary text
- [x] 4.3 Add a failing reporter test proving blocked and skipped remain combined while completed picks are summarized separately
- [x] 4.4 Implement the minimal JSON and Markdown summary changes to satisfy those tests
- [x] 4.5 Run the focused reporter/backend tests and confirm green
- [x] 4.6 Commit the green summary-output update

## 5. [SEQUENTIAL] Verify end-to-end regression coverage

- [x] 5.1 Add or update an end-to-end run-flow test that mocks Gazebo publish calls and verifies report fields after a motion-backed run
- [x] 5.2 Run the relevant `pytest` suites for run controller, backend run flow, reporter, and E2E coverage
- [x] 5.3 Fix any red tests while preserving prior behavior required by existing specs
- [x] 5.4 Confirm all targeted tests are green
- [x] 5.5 Commit the verified end-to-end change set
