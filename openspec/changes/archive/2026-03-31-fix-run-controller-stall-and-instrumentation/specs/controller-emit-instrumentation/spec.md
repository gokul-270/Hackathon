## ADDED Requirements

### Requirement: Controller emit path is fully logged
The RunController SHALL emit a structured `logger` call at each of the following
transitions during `execute_run()`:
1. Before `ThreadPoolExecutor.submit()` for a reachable step (DEBUG)
2. After the executor future resolves (DEBUG)
3. Before `step_complete` is emitted (DEBUG)
4. After `step_complete` is emitted (DEBUG)
5. When a step is skipped as unreachable — before the skip-path `step_complete` (INFO)
6. After the run summary is built, before returning to the backend (DEBUG)

The backend (`testing_backend.py`) SHALL emit a structured `logger` call:
7. Immediately before `run_complete` is emitted via the event bus (INFO)
8. Immediately after `_event_bus.close()` is called (INFO)

All calls use the module-level `logger = logging.getLogger(__name__)`. Step-level
calls use `logger.debug()`; run-level calls use `logger.info()`.

#### Scenario: Reachable step emits four log calls
- **WHEN** a reachable step completes execution
- **THEN** four logger entries appear in order: dispatched, executor-returned, step_complete-emitting, step_complete-emitted

#### Scenario: Unreachable step emits one log call before skip-path step_complete
- **WHEN** a step is determined unreachable by the FK limit check
- **THEN** a logger.info entry appears before the skip-path `step_complete` emit

#### Scenario: Run end emits two log calls in backend
- **WHEN** `execute_run()` returns to `testing_backend.py`
- **THEN** a logger.info entry appears before `run_complete` emit, and another after `_event_bus.close()`
