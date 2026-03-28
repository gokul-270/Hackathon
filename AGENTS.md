# Agent Instructions

Rules for AI coding assistants working in this repository.

## Commit Policy

**Every completed change or fix MUST be committed.** Work that is not committed is
considered lost. No exceptions.

**A commit is only allowed when the build is GREEN.**

- All relevant tests must pass before any commit is made
- Do NOT commit with known test failures, even "minor" ones
- Do NOT commit with `// TODO: fix tests` bypasses
- If tests cannot be run (no test runner available), state this explicitly and
  get user confirmation before committing

Commit message format:
```
feat: <what was added>
fix: <what was corrected>
chore: <non-code changes, config, artifacts>
```

## Red-Green-Refactor (Mandatory for Every Change)

Every code change — feature or bug fix — MUST follow this cycle. No exceptions.

```
RED      Write a failing test that captures the expected behaviour.
          Run it. Confirm it fails for the right reason.

GREEN    Write the MINIMUM code to make the test pass.
          Do not over-engineer. Make it pass, nothing more.

REFACTOR Clean up code and tests while keeping everything green.
          Commit only after refactor is clean and tests are green.
```

**Never write implementation code before writing a failing test.**
If you cannot write a test for a requirement, you do not understand it well
enough to implement it. Stop and clarify.

**Never commit on RED.** The commit gate is GREEN — all tests pass.

## Single Responsibility Principle for Tests

Every test case MUST test exactly ONE behaviour or scenario.

**Good — one assertion, one scenario:**
```python
def test_sequence_stops_when_estop_active():
    # only tests E-STOP stopping the sequence
```

**Bad — multiple unrelated assertions in one test:**
```python
def test_sequence():
    # tests start, stop, E-STOP, repeat count, and arm selection all at once
```

Rules:
- One test = one scenario = one failure reason
- Test name MUST describe the exact behaviour being tested
  (`test_<unit>_<condition>_<expected_result>`)
- No shared mutable state between tests
- If a test requires more than one `assert`, ask whether it should be split
- Setup/teardown may be shared via fixtures, but the scenario under test must
  be isolated

## Applies To All Code Layers

These rules apply equally to every layer in this project:

| Layer | Test Tool |
|---|---|
| ROS2 C++ nodes | `gtest` / `gmock` via `colcon test` |
| Python nodes / backend | `pytest` |
| Web UI (HTML/JS) | Playwright E2E tests |
| Shell scripts with logic | `bats` or `pytest` subprocess assertions |
