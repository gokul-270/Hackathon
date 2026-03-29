# C4 Architecture Diagram — Sequential Pick + Smart Reorder

## Level 1: System Context

```
  +-----------+         +-------------------+        +---------+
  | Operator  | ------> | Web UI            | -----> | Gazebo  |
  | (Human)   |  HTTP   | (testing_ui.html) |  gz    | Sim     |
  +-----------+         +-------------------+        +---------+
                               |
                               | POST /api/run/start
                               v
                        +-------------------+
                        | Testing Backend   |
                        | (FastAPI)         |
                        +-------------------+
```

## Level 2: Container — Testing Backend

```
  +----------------------------------------------------------------+
  |  Testing Backend (testing_backend.py)                          |
  |                                                                |
  |  /api/run/start                                                |
  |    validates mode in {0,1,2,3,4}                               |
  |    creates RunController(mode, ...)                            |
  |    calls controller.run()                                      |
  |    returns JSON summary                                        |
  |                                                                |
  |  +----------------------------------------------------------+  |
  |  | RunController (run_controller.py)                        |  |
  |  |                                                          |  |
  |  |  BaselineMode ---- SequentialPickPolicy                  |  |
  |  |       |                  |                               |  |
  |  |       |            (contention detection,                |  |
  |  |       |             turn alternation)                    |  |
  |  |       |                                                  |  |
  |  |  SmartReorderScheduler                                   |  |
  |  |       |                                                  |  |
  |  |  (pre-run step reordering for Mode 4)                    |  |
  |  |                                                          |  |
  |  |  RunStepExecutor ----> Gazebo (gz topic publish)         |  |
  |  +----------------------------------------------------------+  |
  +----------------------------------------------------------------+
```

## Level 3: Component — RunController Step Dispatch

```
  FOR each step_id in sorted(step_map):
  +--------------------------------------------------+
  |  Compute candidate joints (FK)                   |
  |  Apply BaselineMode.apply_with_skip()            |
  |  Observe truth monitor                           |
  +--------------------------------------------------+
             |
             v
  +--------------------------------------------------+
  |  Mode 3 + contention?                            |
  |    YES: two-phase dispatch                       |
  |      1. executor.execute(winner_arm)             |
  |      2. wait for completion                      |
  |      3. executor.execute(loser_arm)              |
  |      4. wait for completion                      |
  |                                                  |
  |    NO: parallel dispatch                         |
  |      ThreadPoolExecutor(max_workers=2)           |
  |      submit both arms simultaneously             |
  +--------------------------------------------------+
             |
             v
  +--------------------------------------------------+
  |  Collect outcomes                                |
  |  Build StepReports (sorted by arm_id)            |
  |  Emit step_complete SSE events                   |
  +--------------------------------------------------+
```

## Level 3: Component — SmartReorderScheduler

```
  Input: step_map {step_id -> {arm_id -> Step}}
  +--------------------------------------------------+
  |  1. Extract arm1_steps and arm2_steps             |
  |  2. Compute j4 value for each step via FK        |
  |  3. Try all permutations of arm2 ordering        |
  |     (or greedy if N > 8)                         |
  |  4. For each permutation:                        |
  |       min_gap = min(|j4_arm1[i] - j4_arm2[i]|)  |
  |  5. Select permutation with max(min_gap)         |
  |  6. Reassign step_ids to new pairing             |
  +--------------------------------------------------+
  Output: reordered step_map
```
