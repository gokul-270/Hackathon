## Context

The existing run flow in `vehicle_arm_sim/web_ui` is split into two disconnected paths. `RunController` loads a scenario, computes candidate joints, applies mode logic, and produces report records entirely in process. Separately, `testing_backend.py` contains Gazebo joint publishing and pick animation helpers used by manual cotton-pick endpoints. The hackathon plan expects these paths to be unified so that a scenario run both moves the arms in Gazebo and produces explicit completion-aware reports.

Current constraints:
- The hackathon demo needs a fast, low-risk integration path.
- Existing tests already treat `RunController` as the orchestration center.
- The current report model has blocked/skipped information but no first-class completion outcome.

```mermaid
flowchart TD
    A[UI Start Run] --> B[/api/run/start]
    B --> C[RunController]
    C --> D[RunStepExecutor]
    D --> E[Gazebo joint publish]
    D --> F[ArmStepOutcome]
    F --> G[JsonReporter]
    G --> H[JSON / Markdown report]
```

## Goals / Non-Goals

**Goals:**
- Make the scenario-run path publish real Gazebo arm motion for allowed steps.
- Add explicit per-arm terminal outcomes that the controller and reporter can store.
- Surface `pick_completed` and completed-pick totals in JSON and Markdown outputs.
- Keep the change testable with TDD and limit blast radius to the existing `web_ui` runtime path.

**Non-Goals:**
- Replacing the current truth monitor with simulator-observed joint feedback.
- Rebuilding the scenario schema for generalized cotton-model addressing.
- Refactoring the whole backend into distributed runtime processes.

## MoSCoW

- **Must Have**: motion-backed run execution, explicit per-arm outcomes, completed-pick reporting, regression tests.
- **Should Have**: a dedicated execution adapter module so controller logic stays testable.
- **Could Have**: best-effort cotton-removal hook after successful scenario-run completion.
- **Won't Have**: simulator-feedback-based completion gating in this change.

## Decisions

### Decision 1: Add a dedicated execution adapter between orchestration and Gazebo

Create a small execution unit (for example `run_step_executor.py`) that accepts an arm id, candidate/applied joints, and step context, then performs the Gazebo motion sequence. This keeps `RunController` focused on orchestration while making execution mockable in tests.

Alternatives considered:
- Call `_publish_joint_gz(...)` directly from `RunController`: simpler, but couples orchestration to backend publishing details and makes tests harder.
- Move orchestration into `testing_backend.py`: rejected because it would collapse test boundaries and make controller unit tests weaker.

### Decision 2: Use a hybrid source of truth for Phase 1

In this change, run reports remain based on controller-known applied joints and explicit execution outcomes emitted by the executor. We will not block this hackathon change on simulator-feedback observation. This keeps delivery fast while still making completion explicit and no longer inferred.

Alternatives considered:
- Pure simulator truth: better fidelity, but too much new plumbing for the current scope.
- Command dispatch alone means completion: fastest, but too weak to support the planned demo narrative.

### Decision 3: Introduce explicit arm-step terminal outcomes

Add a reportable outcome model for each arm-step with fields such as `terminal_status`, `pick_completed`, and `executed_in_gazebo`. `blocked` and `skipped` remain first-class outcomes instead of being inferred only from `j5_blocked` and mode-specific behavior.

Alternatives considered:
- Keep inferring completion from `not blocked and not skipped`: rejected because it still leaves the report without a real completion concept.

### Decision 4: Preserve current truth-monitor semantics for collision metrics

`TruthMonitor` continues to measure planner-independent geometric proximity from candidate joints during this change. The new completion metrics augment the report rather than replacing current collision metrics.

## Risks / Trade-offs

- **Execution timing drift** -> Mitigation: encapsulate timing in the executor and cover it with focused unit tests around publish order and outcome emission.
- **Controller/report coupling grows** -> Mitigation: add a discrete outcome model and keep reporter updates localized.
- **Backend tests become flaky if they depend on real Gazebo** -> Mitigation: mock the executor or Gazebo publish function in backend tests.
- **Markdown/JSON contract drift** -> Mitigation: add regression tests for new summary keys and per-step outcome fields.

## Migration Plan

1. Add the executor abstraction and tests without changing external API shape.
2. Wire `RunController` and `/api/run/start` to use the executor.
3. Extend the report schema with explicit completion outcome fields.
4. Update backend and report tests, then validate the run endpoints.
5. Optionally add a best-effort cotton-removal hook if the executor already has enough step context.

Rollback is code-only: revert the executor wiring and report schema additions to restore report-only replay behavior.

## Open Questions

- Whether the first motion-backed version should always home each arm after each completed step, or only preserve the current applied joints between paired steps.
- Whether the optional cotton-removal hook should land in the same implementation commit or a follow-up green commit after motion/reporting are stable.
