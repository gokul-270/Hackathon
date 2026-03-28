# Project Agent Instructions

Rules and conventions for AI coding assistants working on this project.

## Project Context

- **Project:** Pragati Cotton Picking Robot
- **Tech stack:** ROS2 Jazzy, C++, Python, Ubuntu 24.04
- **Hardware:** Raspberry Pi 4B, OAK-D Lite cameras, MG6010/MG6012 motors, CAN bus
- **Domain:** Agricultural robotics - autonomous cotton harvesting
- **Architecture:** Distributed multi-arm system (1-6 arms), each with dedicated RPi 4B
- **Communication:** ROS2 topics/services within arm, MQTT between arms
- **Build:** colcon with ccache optimization

### Key Documentation

- `docs/specifications/PRODUCT_REQUIREMENTS_DOCUMENT.md` (PRD)
- `docs/specifications/TECHNICAL_SPECIFICATION_DOCUMENT.md` (TSD)
- `docs/specifications/VALIDATION_MATRIX.md` (requirement traceability)
- `docs/specifications/GAP_TRACKING.md` (tracked gaps)

## Git Commit Policy

**Never leave work uncommitted.** Planning artifacts and implementation code have been lost
due to uncommitted changes being wiped. Follow these mandatory checkpoints:

1. **After all change artifacts are finalized** - one clean commit for the entire change
   ```
   chore: create <change-name> change artifacts (proposal, specs, design, tasks)
   ```
2. **Before stopping/pausing an implementation session** - one commit for all work done
   ```
   feat/fix: implement <change-name> <brief description>
   ```
3. **After archiving a change** - commit the archive and spec sync
   ```
   chore: sync specs and archive <change-name> change
   ```

Do NOT commit after each individual artifact or each individual task. Keep commit history clean
with one commit per logical boundary.

## OpenSpec Workflow

This project uses [OpenSpec](https://github.com/anomalyco/openspec) for structured change management.
Configuration is in `openspec/config.yaml`.

### Change Lifecycle

```
/opsx-new or /opsx-ff  -->  create artifacts  -->  impact analysis  -->  REVIEW  -->  fix issues  -->  COMMIT  -->  implement  -->  VERIFY  -->  fix warnings  -->  archive  -->  COMMIT
```

**REVIEW before COMMIT is mandatory for artifacts.** Two review passes:

1. **Self-review during drafting** — after writing each artifact, re-read it and check for
   internal consistency (numbers match, scenarios are testable, no vague language). Fix
   inline before moving to the next artifact. This is lightweight and inline.
2. **Cross-artifact review before commit** — after ALL artifacts are written, dispatch a
   subagent to verify consistency across the full set:
   - Every spec scenario has a corresponding test task in tasks.md
   - Numbers (frequencies, thresholds, timeouts) are consistent across proposal, specs,
     design, and tasks
   - Every capability in proposal.md has a matching spec file
   - Every task references a capability
   - Delta specs for MODIFIED capabilities note whether the base spec is implemented or not
   - No missing edge cases or fallback scenarios
   - Impact analysis exists and is consistent with specs and design

   Fix all CRITICAL issues. Then commit.

**Impact analysis is mandatory before artifact commit.** After all artifacts are written
and before the cross-artifact review, create `impact-analysis.md` in the change directory.
This document is the reviewer's primary tool for understanding what the change does to the
running system. Do NOT commit artifacts without it.

Required sections (all mandatory, use "None" or "No change" where appropriate):

1. **Before / After Behavior** — Table with columns: `Item | Before (current) | After`.
   State what the system actually does differently. If the success path is unchanged, say so
   explicitly. This is the most important section — it forces you to articulate what changes
   at runtime, not just what code changes.

2. **Performance Impact** — Table with columns: `Item | CPU | Memory | Latency`.
   "None" is a valid and expected answer for most items. If a change adds a thread, a timer,
   or a polling loop, quantify the cost (e.g., "+1 sleeping thread, ~0 when idle"). Do not
   hand-wave — state the specific mechanism and its cost.

3. **Unchanged Behavior** — Explicit list of what stays the same: APIs, topics, services,
   parameters, config files, protocols, launch files. This reassures the reviewer that the
   change does not have hidden side effects. If everything is unchanged, say "No API, config,
   or protocol changes."

4. **Risk Assessment** — Honest list of what could go wrong. For each risk: what is it, how
   likely, what is the mitigation. If a change is truly zero-risk (e.g., adding logging to an
   empty catch block), say so and explain why. Do not list risks that don't apply just to fill
   space.

5. **Blast Radius** — Packages modified, files touched, approximate lines changed. This is
   a quick-reference for the reviewer to gauge scope. Already partially covered in
   proposal.md's Impact section, but must be restated here for standalone readability.

**Impact analysis and cross-artifact review feed into each other.** The cross-artifact
review should verify that the impact analysis is consistent with the specs and design — if
a spec adds a new topic, the impact analysis must mention it. If the impact analysis claims
"no API changes," the specs must not define new services.

**VERIFY → fix → archive → COMMIT is one atomic sequence.** After implementation is
complete, run `openspec-verify-change` to catch field-name mismatches, spec divergences,
and missing scenario coverage. Fix all CRITICAL and actionable WARNING issues. Then
archive (sync specs + move to archive). Then commit everything — implementation, fixes,
spec sync, and archive — as one clean commit. This ensures verification is never skipped
and fixes are never committed separately from the work they correct.

### Artifact Sequence (spec-driven schema)

1. **proposal.md** - Why, what changes, capabilities, impact
2. **specs/<capability>/spec.md** - One spec per capability (Given/When/Then format)
3. **design.md** - Technical decisions, architecture, approach
4. **tasks.md** - Checkboxed implementation tasks (1-2 hour chunks)

### Rules

- Reference PRD/TSD requirement IDs (FR-DET-001, PERF-ARM-001, etc.)
- Include hardware vs software distinction in tasks
- Mark dependencies between tasks
- Include performance targets from PRD in specs

## Testing Policy — Red-Green-Refactor (Mandatory)

**Every code change MUST follow red-green-refactor.** No exceptions. No "I'll add tests later."

```
RED:      Write a failing test that describes the expected behavior
GREEN:    Write the MINIMAL code to make the test pass
REFACTOR: Clean up while keeping tests green
```

### Rules

1. **Test FIRST, code SECOND.** Never write implementation code without a failing test.
   If you cannot write a test for it, you do not understand the requirement well enough.
2. **No commit without corresponding test changes.** Every `feat:` or `fix:` commit MUST
   include test additions or modifications. If a commit touches implementation code but not
   test code, it is rejected.
3. **Bug fixes MUST include a regression test.** Write a test that reproduces the bug (RED),
   then fix the bug (GREEN). This prevents the bug from recurring.
4. **Deleted code requires deleted or updated tests.** If you remove functionality, update
   or remove the tests that covered it. Do NOT delete test files without ensuring coverage
   is preserved elsewhere.
5. **Run tests before committing.** Verify that all relevant tests pass. Do NOT commit
   code with known test failures.
6. **Tests are not optional for any stack.** This applies equally to:
   - **C++ (ROS2 nodes):** Use `gtest`/`gmock`. Run via `colcon test` or `./build.sh full`.
   - **Python backend:** Use `pytest`. Run via `pytest <test_file>`.
   - **Web frontend:** Use Playwright E2E tests. Run via `node <test_file>`.
   - **Scripts/tools:** If it has logic, it needs tests. Use pytest or bash test assertions.

### What Counts as a Test

- Unit tests (single function/class, mocked dependencies)
- Integration tests (multiple components, real or test doubles)
- E2E tests (full system or subsystem, browser or CLI)
- Property-based tests (fuzz inputs)

What does NOT count: manual testing, "I ran it and it worked," or print statements.

### Test File Locations

| Stack | Test location | Framework |
|-------|--------------|-----------|
| C++ ROS2 packages | `src/<pkg>/test/` | gtest, gmock, launch_testing |
| Python backend | `web_dashboard/backend/test_*.py` | pytest, FastAPI TestClient |
| Frontend E2E | `web_dashboard/e2e_tests/` | Playwright |
| Python scripts | `scripts/tests/` or co-located `test_*.py` | pytest |

### Enforcement

- **OpenSpec specs define Given/When/Then scenarios.** Every scenario MUST have a
  corresponding automated test before the change can be archived. `openspec-verify-change`
  checks for this.
- **Pre-push hook** runs linting. Future: add test execution to pre-push.
- **CI pipeline** runs `colcon test`. Future: add dashboard test jobs.

## User Interaction

- **Always ask questions in MCQ format.** When asking the user for a decision or clarification,
  present options as a multiple-choice list -- never open-ended. Include a recommended option
  marked with "(Recommended)" and a brief description for each choice. This reduces back-and-forth
  and keeps sessions focused.
- **Prompt for build mode before file changes.** When a task will require file modifications
  (edits, code changes, document updates), ask the user to switch to build mode BEFORE
  accumulating extensive analysis. Do not dump a wall of planned changes in plan mode --
  instead, summarize findings concisely and prompt: "This requires file edits. Ready to
  switch to build mode?" This avoids wasted context and keeps the session efficient.

## Coding Conventions

### C++ (ROS2 Nodes)

- Follow ROS2 C++ style guide
- Use `rclcpp` lifecycle nodes where appropriate
- Structured JSON logging for field instrumentation
- All motor/hardware interfaces go through CAN bus abstraction
- **Naming (enforced by `.clang-tidy`):** Classes `CamelCase`, functions `camelBack`, variables `lower_case`, private members `lower_case_` (trailing underscore), constants `UPPER_CASE`
- No automatic C++ formatting -- `.clang-tidy` is advisory only (WarningsAsErrors is empty)

### Python (Scripts, Tools, Tests)

- Python 3.12+ (Ubuntu 24.04)
- Use `rclpy` for ROS2 Python nodes
- Scripts should have `--help` documentation
- Auto-formatted by `black` and `isort` on commit (pre-commit hook)
- **Max line length: 100** (enforced by flake8 on pre-push, ignores E203/W503)
- **Always use `python3`, never `python`.** On Ubuntu 24.04 there is no `python` symlink —
  only `python3` exists. All commands (running scripts, invoking pytest, shebang lines) MUST
  use `python3` explicitly. Same applies to `pip3` vs `pip`.

### Build

- `./build.sh fast` - dev builds (tests disabled, symlink install)
- `./build.sh full` - CI builds (tests enabled)
- `./build.sh pkg <name>` - build a single package
- `./build.sh arm` - arm-role packages only
- `./build.sh vehicle` - vehicle-role packages only
- `./build.sh rpi` - cross-compile for RPi 4
- Pre-commit hooks are installed automatically on first build

**Build rules:**
- **NEVER run builds inside subagents** — builds must only run in the main session.
  Subagents cannot observe build output interactively and may miss errors or time out.
- **Use `--clean` when headers, CMake config, or file structure changed:**
  - Native: `./build.sh --clean fast`, `./build.sh --clean pkg <name>`
  - Cross-compile: `./build.sh --clean rpi`
  - `--clean` removes `build/`/`install/` (or `build_rpi/`/`install_rpi/` for rpi mode)
    and rebuilds from scratch, preventing stale header/artifact issues

### Deployment

- **Always use `./sync.sh`** for deploying to RPi -- never use raw `rsync` or `scp`
- `./sync.sh --deploy-cross --ip <IP>` - deploy cross-compiled ARM binaries from `install_rpi/`
- `./sync.sh --deploy-local --ip <IP>` - deploy locally-built x86 binaries from `install/`
- `./sync.sh --build --ip <IP>` - sync source and trigger native build on RPi
- `./sync.sh --provision --ip <IP>` - apply OS fixes and install systemd services
- `./sync.sh --collect-logs --ip <IP>` - pull field trial logs from RPi
- See `./sync.sh --help` for all options

### Web Dashboard

- **Default port is 8090** -- port 8080 conflicts with other services (e.g. Gazebo).
  Do NOT change defaults back to 8080 in any file.
- Port is configurable at launch: `--port <PORT>`, ROS2 `port:=<PORT>`, or
  env var `PRAGATI_DASHBOARD_SERVER_PORT=<PORT>`
- Config source of truth: `web_dashboard/config/dashboard.yaml` (`server.port`)
- When launching for testing, use port 8090 unless the user specifies otherwise

### Setup Scripts (Single Source of Truth)

There are exactly **two** setup scripts. No others should exist or be created:

- `./setup_ubuntu_dev.sh` - Dev workstation setup (WSL2 / Ubuntu desktop)
  - Calls modular scripts in `scripts/setup/modules/00-07_*.sh`
- `./setup_raspberry_pi.sh` - RPi target setup (Ubuntu 24.04 Server ARM64)

**Rules:**
- Any new system dependency (apt package, pip package, tool) MUST be added to **both** scripts
- Do NOT create alternative setup scripts (quickstart, install_deps, etc.) -- they drift
  and cause "works on my machine" bugs. Legacy ones have been archived.
- The modular scripts in `scripts/setup/modules/` are the implementation for dev setup;
  edit those, not the orchestrator
- `setup_raspberry_pi.sh` is monolithic (RPi provisioning has different flow); edit it directly

### WSL2 Environment

The dev workstation runs Ubuntu 24.04 under WSL2. SSH keys, known_hosts, and the SSH
agent are configured on the **Windows side**, so always use Windows OpenSSH:

- **Always use `ssh.exe`, never `/usr/bin/ssh`.** The Windows SSH at
  `/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe` has the correct keys, known_hosts, and
  agent. The Linux `/usr/bin/ssh` does NOT have keys configured and will fail with
  permission denied or host key errors. When running SSH commands (including inside
  scripts), ensure `ssh.exe` is used.
- **`sync.sh` uses SSH internally.** If `sync.sh` fails with host key errors, permission
  denied, or "known_hosts" mismatches, the first thing to check is whether it's picking
  up `/usr/bin/ssh` instead of `ssh.exe`. Fix: ensure the Windows OpenSSH path comes
  before `/usr/bin` in `$PATH`, or set `export GIT_SSH=ssh.exe`.
- **Git SSH transport:** Set `GIT_SSH_COMMAND="ssh.exe"` if git operations fail with
  host-key or auth errors.

## Parallel Execution Policy

**Always use parallel subagents for independent tasks.** This is the default execution strategy.

- When multiple tasks have no shared state or sequential dependencies, dispatch them concurrently using parallel subagents or parallel tool calls in a single message
- Never serialize work that can be parallelized — it wastes time and degrades throughput
- Common parallel patterns for this project:
  - Reading multiple files/specs simultaneously
  - Running build + lint + test checks at the same time
  - Creating independent OpenSpec artifacts (multiple capability specs)
  - Searching the codebase across multiple directories or patterns
  - Cross-compiling (RPi target) while running native tests
- Only serialize when there is a true data dependency (output of A is input to B)
- When in doubt: can these run at the same time without one needing the other's result? If yes, parallelize.

## Context Window Management

Large tasks cause context compaction (conversation history truncation), which loses progress.
Follow these rules to stay within context limits:

- **Delegate file-heavy work to subagents** — reading, splitting, or refactoring large files
  (500+ lines) should happen in a subagent, not the main session
- **Keep the main session lean** — use it for coordination, status tracking, and user
  interaction; avoid reading entire large files here
- **Break multi-phase work into subagent calls** — each subagent gets its own context window,
  so parallelizing phases prevents any single context from overflowing
- **Commit between phases** — if a phase completes, commit immediately so progress is never
  lost to compaction
- **Checkpoint session state to a file** — TodoWrite state is lost on compaction. Before
  any long-running session (implementation, multi-artifact creation), write current progress
  to `openspec/changes/<change-name>/.session-state.md` with: completed tasks, in-progress
  tasks, pending tasks, key decisions made, and any blocked items. Update this file at each
  phase boundary. On session resume (or after compaction), read this file first to restore
  context. Delete the file when the change is archived.
- **Subagents must complete their analysis before returning** — a subagent that hits context
  limits must summarize its findings so far and return actionable results, NOT silently
  compact and lose progress. If a subagent's task is too large for one pass, break it into
  smaller subtasks dispatched as separate subagent calls. Never dispatch a single subagent
  to analyze multiple large files (500+ lines each) in one call — split by file or section.

## Token Efficiency

Tokens are expensive. Every file read, tool output, and terminal display adds to the bill.
Follow these rules to minimize waste:

### Artifact Reading
- **Never re-read a file already in conversation context.** Before issuing a Read call,
  check if the file's content already appeared earlier in this conversation (from a prior
  read, skill invocation, or tool output). If it did, use that content directly.
- **Read selectively.** When checking task completion, grep for `- [` instead of reading
  the entire tasks.md. When checking requirement IDs, grep for `### Requirement:` instead
  of reading the entire spec.
- **Summarize, don't echo.** After reading an artifact, extract only the information needed
  for the current step. Never output full artifact content to the terminal unless the user
  explicitly asks to see it.

### Terminal Output
- **Do not narrate file writes.** When writing or editing files, do NOT echo the content
  to the terminal. The file write itself is the deliverable. A one-line status like
  "Wrote spec for X" is sufficient — do not preview, repeat, or explain the content unless
  the user asks.
- **Batch status updates.** Instead of announcing each file individually ("Now writing
  spec 1... Done. Now writing spec 2..."), write files silently and report once at the end:
  "Wrote 4 specs, design, and tasks."
- **No planning monologues.** Do not output multi-paragraph explanations of what you are
  about to do. Plan internally, execute, report results. The user sees the files.
- **Critical-only terminal output.** Reserve terminal output for: decisions needing user
  input, errors/warnings, phase completion summaries, and final results. Everything else
  is noise.

### TodoWrite
- **Batch status updates.** When completing multiple tasks in a sequence, update all their
  statuses in a single TodoWrite call rather than one call per task.
- **Keep descriptions under 10 words.** Long descriptions waste tokens on every rewrite.

### OpenSpec Workflow
- **Delegate verify to a subagent.** When opsx-apply reaches the verify step, dispatch
  verification as a Task subagent so the verification context (re-reading all artifacts +
  codebase searches) doesn't bloat the main session.
- **One skill invocation per session.** Prefer running opsx-ff/apply/verify/archive in
  separate sessions (commit between them) rather than chaining multiple OpenSpec commands
  in one long conversation.
- **Never load openspec-onboard unless explicitly requested.** It is a 529-line tutorial.

## What NOT to Do

- Do not commit build artifacts (`build/`, `install/`, `log/`, `build_rpi/`, `install_rpi/`)
- Do not commit machine-specific configs (`configs/`)
- Do not modify `.opencode/` internal files (bun.lock, package.json, node_modules)
- Do not force-push to main
- Do not skip pre-commit hooks
- Do not create files in the repo root (strict allowlist enforced by pre-push hook):
  - Allowed `.md`: only `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md`
  - Allowed `.sh`: only `build.sh`, `sync.sh`, `setup_*.sh`, `emergency_motor_stop.sh`
  - Allowed `.txt`: only `requirements.txt`
  - **No `.py` files in root ever** -- use `scripts/`
- Do not leave trailing whitespace or missing final newlines (rejected by pre-push hook)
- Do not commit empty (0-byte) files
- Do not hardcode absolute paths -- use script-relative `REPO_ROOT` or env vars (e.g. `$RPI_SYSROOT`)
