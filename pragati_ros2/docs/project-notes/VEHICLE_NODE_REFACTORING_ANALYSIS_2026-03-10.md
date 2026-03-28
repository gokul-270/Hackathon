# Vehicle Control Node Refactoring Analysis

**Date:** 2026-03-10
**Status:** Analysis Only -- No Code Changes
**Scope:** Compare prior refactoring prototype, current monolith, and proposed decomposition

> **Update 2026-03-11:** TIER 1 CRITICAL thread safety is now resolved by
> `phase-2-critical-fixes` (commit d3e0885c). 3 `threading.Lock` instances added protecting
> 17+ shared attributes across all 3 threads. The god-class decomposition (TIER 3) remains
> pending. See `openspec/changes/archive/2026-03-11-phase-2-critical-fixes/` and
> `openspec/specs/vehicle-thread-safety/spec.md`.

---

## 1. Executive Summary

`vehicle_control_node.py` has grown from 783 lines (Sep 2025) to 3,754 lines (Mar 2026) --
a 4.8x increase over 6 months. A well-structured decomposed prototype exists in
`collected_logs/log3/refactored_example/` (from the ROS-1 era) but was **never committed
to git** (gitignored) and **never integrated** into the main codebase.

**Critical finding:** The `vehicle_control` package already contains **3,813 lines of
modular code** (`core/state_machine.py`, `core/safety_manager.py`, `core/vehicle_controller.py`,
etc.) that was written to replace the monolith's inline logic -- but **never wired in**.
The refactoring is primarily a wiring task, not a design task.

The Tech Debt Analysis (2026-03-10) classifies this as:
- **TIER 1 CRITICAL** (thread safety -- 3 threads, zero locks)
- **TIER 3 MODERATE** (god-class -- 92 methods, 11 subsystems)
- **Effort: XL** -- Planned for Phase 3 (~2-3 weeks), reduced by existing modules

A separate agent independently proposed the same decomposition with a 6-module split.
This document compares all three perspectives: the old prototype, the current state, and
the new proposal. It also covers ROS2 best practices gaps (Section 16), ODrive drivetrain
risks (Section 17), and a corrected risk summary (Section 18). **Recommendation: Wire in
existing modules first. C++ decision deferred pending real RPi CPU measurements -- the
claimed fix numbers were exaggerated. ODrive CAN fix (TD-1.8) must complete before
vehicle decomposition begins.**

---

## 2. Historical Timeline

| Date | Event | Lines | Notes |
|------|-------|------:|-------|
| Sep 19 2025 | Initial commit (as `ros2_vehicle_control_node.py`) | 783 | Pre-Phase-3 snapshot |
| ~Oct 2025 | Refactored example created (ROS-1 era, never committed) | ~2,500+ | `collected_logs/log3/refactored_example/` |
| Dec 4 2025 | ROS2 integration rewrite | 752 | Motor abstraction, YAML config |
| Dec 4 2025 | Renamed to `vehicle_control_node.py` | 775 | pigpio switch |
| Dec 9 2025 | Major refactor + diagnostics | 1,893 | +810 lines in one day |
| Dec 18 2025 | MCP3008 joystick | 2,238 | +345 |
| Jan 2026 | Gazebo simulation (by Vasanthakumar) | 2,724 | +486 |
| Feb 2026 | ODrive + timing instrumentation | 3,228 | +504 |
| Mar 8 2026 | GPIO consolidation | 3,541 | +743 (largest single growth) |
| Mar 10 2026 | CPU burn fix (surgical, not architectural) | 3,754 | Deferred decomposition; **CPU claims exaggerated** |

**WARNING: CPU burn fix numbers are unreliable.** The commit claimed "97.5% -> 7.3% CPU"
but actual RPi 4B measurements show the node is **still >50% CPU**. The 31 unit tests
verify code structure (correct functions called, correct timer periods) but do NOT measure
actual CPU usage. All performance numbers came from one-time manual `pidstat` measurements
with no automated regression test. The ODrive changes in the same commit have zero tests.
See Section 13 for full analysis.

**Key finding:** The refactored example was created during ROS-1 era. When the ROS2
migration happened (Dec 2025), the monolithic approach was used instead -- likely because
the ROS2 integration was a complete rewrite with different abstractions (rclpy, topics,
services) that didn't map directly to the ROS-1 decomposition.

**No refactoring branches ever existed.** All work done directly on `pragati_ros2` branch.

---

## 3. Three Decomposition Perspectives Compared

### 3A. Old Prototype (collected_logs/log3/refactored_example/)

**Architecture:** Python package with `core/`, `hardware/`, `config/`, `simulation/` subpackages.

| Module | File | Responsibility |
|--------|------|---------------|
| VehicleController | `core/vehicle_controller.py` | Main orchestrator with 11-state FSM |
| StateMachine | `core/state_machine.py` | State transitions, guards, history |
| SafetyManager | `core/safety_manager.py` | E-stop, watchdog, fault detection |
| MotorController | `hardware/motor_controller.py` | CAN bus motor abstraction |
| AdvancedSteering | `hardware/advanced_steering.py` | Ackermann kinematics, pivot modes |
| GPIOManager | `hardware/gpio_manager.py` | Pin abstraction, debouncing |
| TestFramework | `hardware/test_framework.py` | 35+ automated hardware tests |
| Constants | `config/constants.py` | Pins, IDs, enums, physical params |
| Simulation | `simulation/` | tkinter GUI, physics engine, matplotlib |

**Design Patterns:** Composition, state pattern (formal FSM), observer (callbacks),
factory (steering mode). **ROS version:** ROS-1 patterns (no rclpy, no topics/services).

**Strengths:**
- Clean separation of concerns
- Formal state machine with transition guards
- Dedicated safety manager
- 35+ hardware tests
- Simulation framework included

**Weaknesses:**
- ROS-1 era -- cannot be directly reused in ROS2
- No MQTT integration (was handled differently)
- No ROS2 lifecycle management
- No diagnostics/health monitoring (added later)
- Never battle-tested in production

### 3B. Current Monolith (vehicle_control_node.py, 3,754 lines)

**Architecture:** Single `ROS2VehicleControlNode(Node)` class, 92 methods.

| Functional Area | Lines | % |
|----------------|------:|--:|
| Drive/Steering/Velocity | ~605 | 16.1% |
| Diagnostics/Health/Thermal | ~469 | 12.5% |
| Joystick/Input | ~421 | 11.2% |
| GPIO/Switches/LEDs | ~370 | 9.9% |
| MQTT Communication | ~345 | 9.2% |
| ROS2 Setup | ~240 | 6.4% |
| Service Callbacks | ~208 | 5.5% |
| Motor Hardware Init | ~191 | 5.1% |
| Constructor | ~159 | 4.2% |
| Joint State Processing | ~91 | 2.4% |
| Stubs/Dead Code | ~84 | 2.2% |
| Control Loop/State | ~76 | 2.0% |
| Config Loading | ~65 | 1.7% |
| Shutdown/Cleanup | ~56 | 1.5% |
| Cotton/Arm Stubs | ~44 | 1.2% |
| Status Publishing | ~41 | 1.1% |
| main() + imports | ~180 | 4.8% |

**ROS2 Inventory:** 30 publishers, 13 subscribers, 12 service servers, 3 service clients,
7 timers, 3 threads (executor + joystick + MQTT), 0 locks.

**Complexity Hotspots:**
1. `__init__` -- 159 lines, 30+ instance variables
2. `_send_drive_position_incremental` -- 157 lines, 5 levels deep
3. `_process_physical_switches` -- 129 lines, edge detection + MQTT + shutdown
4. `_execute_shutdown` -- 117 lines, subprocess + thread spawn + multi-phase

**Known Issues:**
- Zero threading locks across 3 concurrent threads (TIER 1 CRITICAL)
- 19 `except: pass`/silent-swallow blocks (3 bare `except:` + 14 `except Exception: pass` +
  2 `except Exception:` without name binding); 11 of 14 silent pass are in
  shutdown/cleanup code. _Updated count: was 17, actual is 19. OpenSpec: `vehicle-exception-cleanup`_
- Unit conversions scattered across 4+ methods with magic numbers
- `drive_joints` list hardcoded in 7+ locations
- 84 lines of dead code (stub methods)
- MQTT broker address hardcoded (3 sites: L285, L289, L485). _OpenSpec: `tech-debt-quick-wins`_

### 3C. New Proposal (Agent-Suggested 6-Module Split)

| Module | Responsibility | Est. Lines |
|--------|---------------|----------:|
| JoystickManager | SPI thread, input processing, idle detection | ~400 |
| MQTTBridge | Connection, reconnect, message routing, selftest | ~300 |
| DriveController | Steering, velocity, position incremental moves | ~400 |
| GPIOProcessor | Physical switches, LEDs, status indicators | ~300 |
| ShutdownManager | Graceful shutdown, force-kill, cleanup | ~200 |
| VehicleControlNode (slim) | Orchestrator, state machine, control loop | ~800 |
| Remaining (diagnostics, IMU, etc.) | Small focused classes | ~1,300 |

---

## 4. Side-by-Side Comparison

### 4A. Module Mapping

| Concern | Old Prototype | Current Monolith | New Proposal |
|---------|--------------|-----------------|--------------|
| Orchestration | VehicleController | ROS2VehicleControlNode (all 92 methods) | VehicleControlNode (slim, ~800 lines) |
| State Machine | StateMachine (dedicated, 11 states) | Implicit in `current_state` enum | Embedded in slim orchestrator |
| Safety | SafetyManager (dedicated) | Scattered across callbacks | Not explicitly called out |
| Steering/Drive | AdvancedSteering + MotorController | 18+ methods (~605 lines) | DriveController (~400 lines) |
| GPIO | GPIOManager | 4+ methods (~370 lines) | GPIOProcessor (~300 lines) |
| Joystick | (not in prototype) | 7+ methods (~421 lines) | JoystickManager (~400 lines) |
| MQTT | (not in prototype) | 8+ methods (~345 lines) | MQTTBridge (~300 lines) |
| Shutdown | (part of safety) | `_execute_shutdown` + `shutdown` | ShutdownManager (~200 lines) |
| Diagnostics | (not in prototype) | 12+ methods (~469 lines) | Part of "remaining ~1,300" |
| IMU | (not in prototype) | Imported but minimal | Part of "remaining ~1,300" |
| Config | Constants module | YAML + defaults | Not specified |
| Simulation | Full sim package | (separate directory) | Not specified |
| Tests | 35+ hardware tests | 0 unit tests for node itself | Not specified |

### 4B. Architecture Style

| Aspect | Old Prototype | Current Monolith | New Proposal |
|--------|--------------|-----------------|--------------|
| Decomposition level | Python classes (same process) | Single class | Unclear (modules or nodes?) |
| Communication | Direct method calls | Self-referencing | ROS2 topics? Direct calls? |
| Threading model | Unclear from code | 3 threads, no locks | Not specified |
| ROS2 integration | None (ROS-1) | Full (topics, services, timers) | Assumed ROS2 |
| Testability | High (isolated classes) | Very low (no unit tests) | High (if properly isolated) |
| Deployment | Single process | Single process | Unclear |

---

## 5. Critical Design Decisions for Decomposition

### Decision 1: Same-Process Modules vs. Separate ROS2 Nodes

| Approach | Pros | Cons |
|----------|------|------|
| **Same-process modules** (composition) | No IPC overhead, shared memory, simpler deployment, gradual migration, single systemd unit | Still shares GIL, thread safety must be designed, tighter coupling |
| **Separate ROS2 nodes** (multi-process) | True isolation, independent restart, natural thread safety, independent testing | IPC latency (~1-5ms per hop), complex deployment, state synchronization overhead, 6+ processes on RPi 4B with 4GB RAM |

**Recommendation:** Same-process composition (like the old prototype) is the safer choice
for an RPi 4B with limited resources. The current vehicle_control_node already has external
module composition (GPIOManager, VehicleMotorController, etc.) -- the refactoring extends
this pattern to cover MQTT, joystick, diagnostics, and shutdown.

**Risk with multi-node:** The vehicle_control_node currently has 30 publishers, 13
subscribers, 12 services, 7 timers. Splitting into separate nodes multiplies the DDS
discovery overhead on a resource-constrained RPi 4B. The recent CPU burn fix (97.5% -> 7.3%)
was partly about reducing DDS overhead.

### Decision 2: Thread Ownership

| Current (Broken) | Option A: Locks | Option B: Thread-per-module |
|-------------------|-----------------|----------------------------|
| 3 threads share all state, no locks | Add `threading.Lock` to shared state | Each module owns its thread, communicates via queues |
| Relies on GIL (fragile) | Simple, incremental fix | Clean isolation, future-proof for free-threading (PEP 703) |
| Works today but unsafe | Effort: Medium | Effort: Large (part of decomposition) |

**Recommendation:** Thread-per-module is the right long-term answer, but adding locks first
(Phase 3 pre-work) prevents data races while the decomposition is planned.

### Decision 3: State Machine Formalization

The old prototype had a formal 11-state FSM with transition guards. The current monolith
uses a simple `VehicleState` enum with ad-hoc transitions. The new proposal doesn't address
this explicitly.

**Recommendation:** A formal state machine (even a lightweight one) should be part of the
decomposition. It eliminates an entire class of bugs (invalid state transitions) and makes
the orchestrator testable.

### Decision 4: What Stays in the Orchestrator

The new proposal estimates ~800 lines for the slim orchestrator. Based on the current
functional area analysis, the orchestrator would own:
- ROS2 setup (publishers, subscribers, services, timers): ~240 lines
- Control loop + state machine: ~76 lines (currently, more with formal FSM)
- Service callbacks (thin wrappers delegating to modules): ~208 lines
- Constructor (init subsystems): ~100 lines (reduced from 159)
- Status publishing: ~41 lines
- **Total: ~665-800 lines** -- this estimate is reasonable.

---

## 6. Pros and Cons Analysis

### Pros of Decomposition

1. **Testability** -- Each module can be unit-tested in isolation. Currently 0 unit tests
   exist for the node itself (92 methods, none tested).
2. **Thread safety** -- Module boundaries create natural points for synchronization.
   Thread-per-module eliminates shared mutable state.
3. **Maintainability** -- 3,754 lines with 92 methods in one class is a maintenance burden.
   New developers cannot reason about the full system.
4. **Build speed** -- Changes to GPIO don't require re-reading 3,754 lines of MQTT code.
   (Less relevant for Python than C++, but helps IDE/linter performance.)
5. **Independent evolution** -- MQTT reconnection logic can be improved without risk to
   steering calculations.
6. **Debugging** -- Stack traces point to specific modules rather than line 2,246 of a
   monolith.
7. **Prior art** -- Three prior decompositions succeeded (yanthra_move, cotton_detection,
   dashboard_server). Team has experience with the pattern.
8. **Technical debt reduction** -- Addresses TIER 1 (thread safety) and TIER 3 (god-class)
   simultaneously.
9. **Dead code elimination** -- 84 lines of stubs can be cleanly removed or properly
   placed in future module boundaries.

### Cons of Decomposition

1. **Risk of regression** -- The node has been field-tested in its current form. Any
   structural change risks introducing regressions, especially in timing-sensitive paths
   (joystick polling, drive position incremental moves, shutdown sequences).
2. **Effort: XL** -- 2-3 weeks estimated. This is substantial engineering time that
   competes with feature development (autonomous navigation, multi-arm coordination).
3. **Integration complexity** -- The current monolith's 30+ instance variables are
   interconnected. Untangling shared state requires careful analysis of every method's
   read/write set.
4. **Test gap** -- There are 0 unit tests for the current node. Decomposing without a
   test safety net means regressions won't be caught automatically. Tests must be written
   BEFORE refactoring (red-green-refactor per AGENTS.md).
5. **Deployment change** -- If multi-node: systemd service files, launch files, node
   lifecycle management all need updating. If same-process: simpler but still requires
   launch file changes.
6. **RPi resource constraints** -- RPi 4B has 4GB RAM. Multiple ROS2 nodes means
   multiple DDS participants, more memory, more CPU for discovery.
7. **Timing sensitivity** -- The CPU burn fix was a delicate timing adjustment. Decomposition
   changes the execution model and may reintroduce timing issues.
8. **MQTT thread interaction** -- The paho MQTT client runs its own thread. Moving it to a
   module still requires careful callback synchronization.
9. **Field trial proximity** -- If the next field trial is imminent, architectural changes
   are high-risk. The Tech Debt Analysis explicitly deferred this to Phase 3 for this reason.

---

## 7. Why the Old Prototype Was Not Carried Forward

Based on git history and document analysis, the most likely reasons are:

1. **ROS version mismatch** -- The prototype was written for ROS-1. The Dec 2025 ROS2
   integration was a complete rewrite using rclpy patterns (topics, services, lifecycle)
   that have no direct equivalent in the prototype's direct-call architecture.

2. **Never committed to git** -- The prototype lives in `collected_logs/` which is
   gitignored. It was never part of the tracked codebase, so it was invisible to anyone
   who didn't know to look there.

3. **Velocity of feature additions** -- Between Dec 2025 and Mar 2026, the node grew by
   ~3,000 lines of production-critical functionality (diagnostics, joystick, MQTT, GPIO,
   Gazebo, ODrive, thermal monitoring). Each feature was added surgically under time
   pressure (field trial deadlines). Stopping to decompose was never prioritized over
   shipping features.

4. **Different developer** -- The Gazebo simulation integration (+486 lines) was by
   Vasanthakumar, not the original developer. Multiple developers adding to a monolith
   without refactoring gates is a classic growth pattern.

5. **Explicit deferral** -- The CPU burn fix (Mar 10, 2026) explicitly listed
   "Restructuring vehicle_control_node into multiple smaller nodes" as out-of-scope,
   calling it "too risky pre-field-trial."

---

## 8. Architectural Impact Assessment

### If Decomposition is Done (Same-Process Composition)

| Impact Area | Before | After | Risk |
|-------------|--------|-------|------|
| File structure | 1 file, 3,754 lines | ~8-10 files, 300-800 lines each | LOW |
| Import graph | Flat (everything in one class) | Module imports with clear dependencies | LOW |
| Launch files | Single node launch | Same (single node, modules are internal) | NONE |
| Systemd service | Unchanged | Unchanged | NONE |
| ROS2 topics/services | 30 pub, 13 sub, 12 srv | Same external interface | NONE |
| Testing | 0 tests | One test file per module | HIGH (effort to write) |
| Thread model | 3 threads, no locks | Thread-per-module with queues | MEDIUM |
| Startup time | Single init | Sequential module init | LOW |
| Memory | Single object | Multiple objects, same process | NEGLIGIBLE |
| DDS overhead | Unchanged | Unchanged | NONE |

### If Decomposition is Done (Multi-Node Split)

| Impact Area | Before | After | Risk |
|-------------|--------|-------|------|
| File structure | 1 file | 6-10 files + launch files | MEDIUM |
| Launch files | Single node | Multi-node launch with composition | HIGH |
| Systemd service | 1 service | Depends on launch approach | MEDIUM |
| ROS2 topics/services | 30 pub, 13 sub | Additional internal topics for inter-module comms | HIGH |
| Memory | ~50MB (one Python process) | ~200-300MB (6 Python processes w/ ROS2) | HIGH on RPi |
| DDS overhead | 1 participant | 6 participants, cross-discovery | HIGH on RPi |
| Latency | In-process method calls | ~1-5ms per topic hop | MEDIUM |
| Independent restart | Not possible | Each node restartable | BENEFIT |
| Fault isolation | One crash kills all | Only affected node crashes | BENEFIT |

---

## 9. Comparison: New Proposal vs. Old Prototype vs. Current Code

### What the New Proposal Gets Right

1. **Module boundaries align with functional areas** -- JoystickManager (~400) vs actual
   joystick code (~421 lines). MQTTBridge (~300) vs actual MQTT code (~345). The estimates
   are grounded in reality.
2. **Slim orchestrator concept** -- Keeping the orchestrator at ~800 lines with delegation
   is the right pattern.
3. **Shutdown as a separate concern** -- Shutdown is complex (117 lines of multi-phase
   shutdown + 56 lines of cleanup) and deserves isolation.

### What the New Proposal Misses

1. **No formal state machine** -- The old prototype had an 11-state FSM. The new proposal
   doesn't mention state management explicitly. This is a missed opportunity.
2. **No safety manager** -- The old prototype had a dedicated SafetyManager (watchdog, fault
   detection, E-stop). The new proposal spreads safety across modules.
3. **No test strategy** -- Per AGENTS.md, tests must be written BEFORE refactoring (TDD).
   The proposal doesn't address how to test the 92 existing methods before moving them.
4. **No migration strategy** -- How to go from monolith to modules without a flag day.
   Strangler fig pattern? Feature flags? Parallel running?
5. **Line estimates for "remaining ~1,300"** -- Diagnostics (469 lines), joint state
   processing (91 lines), config (65 lines), status (41 lines), stubs (84 lines) = ~750
   lines. The 1,300 estimate may be high or includes portions of the orchestrator.
6. **Thread ownership model** -- Not specified. Which module owns which thread?
7. **Concurrency protocol** -- How do modules communicate? Callbacks? Queues? Shared refs?

### What the Old Prototype Had That Should Be Preserved

1. **Formal state machine with transition guards** -- Prevents invalid state transitions
2. **Safety as a first-class concern** -- Dedicated manager, not distributed
3. **Test framework** -- 35+ hardware tests built-in
4. **Clean separation of hardware abstraction** -- Motor + steering as distinct hardware modules
5. **Simulation framework** -- Standalone testing without hardware

---

## 10. Recommended Path Forward

**Key insight:** This is NOT a greenfield decomposition. 3,813 lines of modular code
already exist in `core/`, `utils/`, and `hardware/` but were never wired into the
monolith. The primary task is **connecting existing modules** and **removing inline
reimplementations**, not writing new modules from scratch.

### Phase 0: Pre-Refactoring Safety Net (3-5 days)

Before ANY structural changes:
1. Write integration tests for the current monolith's external behavior (ROS2 topics,
   services, state transitions, shutdown sequence)
2. Add threading locks to shared mutable state (TIER 1 CRITICAL fix, can be done
   independently)
3. Fix `system_diagnostics.py` (broken import of non-existent `RobustMotorController`) — _📋 OpenSpec: `tech-debt-quick-wins`; also deletes `debug_diagnostics.py` and 7 dead functions in `validate_system.py`_
4. Eliminate duplicate motor publisher paths (monolith's direct pubs vs ROS2MotorInterface)

### Phase 1: Wire In Existing Modules (1-2 weeks)

These modules are already written. The work is integration, not creation:
1. **Wire in `core/state_machine.py`** -- Replace inline `current_state` enum with the
   formal `VehicleStateMachine` (transition guards, history). Lowest risk, validates approach.
2. **Wire in `core/safety_manager.py`** -- Replace inline E-stop/watchdog logic with the
   existing `SafetyManager`. Medium risk (safety-critical path).
3. **Extract MQTT into `integration/mqtt_manager.py`** -- The ~345 lines of MQTT client
   management have no existing module yet. New file needed, but well-bounded.
4. **Wire in `core/vehicle_controller.py`** -- Replace inline control orchestration. Highest
   risk but biggest payoff (~500 lines removed from monolith).

### Phase 2: Extract Remaining Inline Code (1 week)

These need new modules:
1. **ShutdownManager** -- Extract `_execute_shutdown` + `shutdown` (~170 lines)
2. **DiagnosticsCollector** -- Extract health scoring, self-test, thermal monitoring (~470 lines)
3. **Delete dead code** -- Remove 84 lines of stubs, decide on `configuration_manager.py`,
   `circuit_breaker.py`, `velocity_kinematics_control.py`, `test_framework.py`

### Phase 3: Test Coverage (Concurrent with Phases 1-2)

For each wired-in module:
1. Write unit tests for the module in isolation
2. Write integration tests for module-to-orchestrator communication
3. Verify field-trial-equivalent scenarios pass

### Phase 4: Future Considerations (Not Now)

- C++ port -- NOT recommended (see Appendix D). Keep Python.
- Multi-node split -- only if RPi resources prove sufficient
- ROS2 lifecycle node integration

---

## 11. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Regression during refactoring | Integration tests BEFORE extraction; strangler fig (one module at a time) |
| Timing changes | Benchmark control loop timing before/after each extraction |
| Thread safety during migration | Add locks in Phase 0; remove when module owns its thread |
| Field trial deadline conflict | Refactoring is Phase 3 (post-field-trial); do NOT rush |
| State migration errors | Document all instance variable dependencies before moving |
| RPi performance impact | Benchmark on RPi 4B, not just dev workstation |

---

## 12. Decision Matrix

| Criterion | Weight | Do Nothing | Same-Process Split | Multi-Node Split |
|-----------|-------:|:----------:|:-----------------:|:---------------:|
| Risk to field trials | 25% | 5 (no risk) | 3 (medium risk) | 1 (high risk) |
| Testability improvement | 20% | 1 (untestable) | 5 (isolated modules) | 5 (isolated nodes) |
| Thread safety | 20% | 1 (broken) | 4 (module boundaries) | 5 (process isolation) |
| RPi resource impact | 15% | 5 (no change) | 5 (no change) | 2 (high overhead) |
| Maintainability | 10% | 1 (3,754-line god class) | 4 (8-10 focused files) | 5 (independent nodes) |
| Effort required | 10% | 5 (zero effort) | 3 (XL effort) | 1 (XXL effort) |
| **Weighted Score** | | **3.05** | **3.95** | **3.00** |

**Winner: Same-process module extraction** -- balances risk, testability, and resource
constraints. Multi-node split is not justified for an RPi 4B deployment.

---

## 13. CPU Burn Fix: Claims vs Reality

The Mar 10 2026 commit (`302a0ca7`) claimed "reduce CPU burn 97.5% -> 7.3% on RPi 4B."
**These numbers are exaggerated.** Actual RPi 4B measurements show >50% CPU.

### What Was Claimed

| Metric | Before (Claimed) | After (Claimed) | Method |
|--------|----------------:|----------------:|--------|
| CPU usage | 97.5% | 7.3% | Manual `pidstat` on one RPi |
| RPi temperature | 73.5C (projected 88-93C) | 57.5C | Manual sysfs read |
| Timer wakeup rate | ~75 Hz | ~22 Hz | Calculated |
| Throttle state | — | 0x0 | Manual `vcgencmd` |

### What Was Actually Fixed

The code changes are real and correct:
1. `rclpy.spin()` -> `spin_once(timeout=0.1)` + `sleep(0.05)` throttle
2. Timer frequencies reduced (75Hz -> 22Hz combined)
3. Batched GPIO reads (`read_bank1()` instead of 6x `read(pin)`)
4. RPi thermal self-monitoring added
5. ODrive `CAN_RAW_LOOPBACK` disable + `spin_once(100ms)`

### Why the Numbers Are Unreliable

1. **No automated performance test.** All 31 tests are mocked unit tests verifying code
   structure, not actual CPU usage. There is no test that measures `pidstat` output.
2. **One-time manual measurement.** The 7.3% came from one `pidstat` session on one RPi.
   No repeated measurement, no statistical confidence.
3. **ODrive changes untested.** The ODrive spin-loop fix and CAN loopback fix have zero
   automated tests (`src/odrive_control_ros2/` has no test directory at all).
4. **Actual field result: still >50% CPU.** The structural changes helped but did not
   achieve the claimed improvement on production hardware.

### Implication for C++ Decision

If the CPU fix had actually achieved 7.3%, Python would be fine for a 5Hz loop.
With >50% CPU on RPi 4B, the overhead of Python + rclpy + pigpio daemon IPC is
substantial and may justify C++ for hot paths. **This needs proper measurement
before deciding** -- profiling with `py-spy` to identify whether the time is in
rclpy spin, pigpio IPC, Python GC, or the actual callback logic.

---

## 14. Codebase-Wide Technical Debt Context

The vehicle_control_node refactoring does not exist in isolation. The Tech Debt Analysis
(2026-03-10) identified **40 items across 5 tiers** affecting ALL production nodes.
Understanding the full picture is essential for prioritization.

### System-Wide Stats

| Metric | Count |
|--------|------:|
| Total codebase | ~87,992 LOC across 13 production nodes |
| Critical safety issues | 8 |
| High reliability issues | 7 |
| Architectural issues (SOLID) | 9 |
| Maintainability issues | 8 |
| Cleanup items | 8 |
| **Total tech debt items** | **40** |

### God-Classes (Not Just Vehicle)

Vehicle_control_node is one of **FOUR** god-classes in the codebase:

| Node | Lines | Methods | Concern Count |
|------|------:|--------:|-------------:|
| mg6010_controller_node.cpp | 4,511 | 53 | 14 |
| vehicle_control_node.py | 3,754 | 92 | 11 |
| motion_controller.cpp | 3,783 | 30 | 7 (one method is 795 lines!) |
| odrive_service_node.cpp | 1,580 | 11 | 6 |

All four need decomposition. Doing vehicle alone without the others leaves 3 equally
problematic monoliths.

### Critical Items BEFORE Vehicle Refactoring

These TIER 1 items should be fixed before or alongside any refactoring:

| ID | Issue | Node | Fix Effort |
|----|-------|------|-----------|
| 1.1 | SingleThreadedExecutor starves thermal monitoring | cotton_detection | Small |
| 1.2 | Blocking motor service starves watchdog | mg6010_controller | Medium |
| 1.3 | Zero threading locks, 3 concurrent threads | **vehicle_control** | Large |
| 1.4 | Bare `except:` in emergency stop path | vehicle safety_manager | Tiny |
| 1.5 | Empty `catch(...){}` in motion controller | yanthra_move | Tiny |
| 1.6 | `pauseCamera()` state lie -- never sends command | cotton_detection | Tiny |
| 1.7 | Watchdog false-positive emergency stop | mg6010_controller | Tiny (one-line) |
| 1.8 | Silent CAN write failures in ODrive | odrive_control | Small |

### Architectural Issues Affecting Vehicle Refactoring

| ID | Issue | Impact on Refactoring |
|----|-------|----------------------|
| 5.1 | Motor node role via string matching | Vehicle/arm motor configs are tightly coupled |
| 5.4 | Code duplication (signal handlers, CAN init) | Refactored modules could consolidate |
| 5.7 | Dual source of truth for motor config | `constants.py` vs `vehicle_motors.yaml` must be resolved during refactoring |
| 5.5 | common_utils underutilized | Vehicle_control has its own logging_utils instead of using common_utils |
| 5.6 | Fail-fast principle violated | Refactoring should fix the 19 `except: pass`/silent-swallow blocks (OpenSpec: `vehicle-exception-cleanup`) |

### Phased Attack Order (Updated -- from Tech Debt Analysis, 5-Phase Plan)

| Phase | Timeline | Vehicle-Relevant Items |
|-------|----------|----------------------|
| **1: Pre-Field-Trial** | ~2 days | 1.4 (bare except in safety_manager), **1.8 (silent ODrive CAN writes)** |
| **2: Next Sprint** | ~1 week | 2.2 ✅, **2.3 ✅ (ODrive heartbeat timeout — bad11785)**, 2.7 (ODrive tests), 3.5 ✅ |
| **3: Planned Refactoring** | ~2-3 weeks | **1.3 (thread locks)**, 3.1 (decompose vehicle god-class), 5.1 (motor role arch) |
| **4: Architecture** | ~2 weeks | 5.4 (DRY consolidation), 5.5 (common_utils), 5.6 (fail-fast), 5.7 (dual config) |
| **5: Cleanup** | ~3 days | 4.3 (signal handler consolidation), 4.4 (dead EE timeout param — 📋 OpenSpec: `tech-debt-quick-wins`) |

**Critical dependency:** Phase 1 includes ODrive CAN write fix (1.8) -- this must be done
**before** vehicle refactoring, because the vehicle depends on the ODrive for drive wheels.
A silent CAN failure during vehicle testing would confound refactoring validation.

### Executor Architecture Comparison (from Tech Debt Analysis)

| Node | Executor | Callback Groups | Thread Safety | Starvation Risk |
|------|----------|:---------------:|:-------------:|:---------------:|
| cotton_detection | SingleThreaded | 0 (default) | Adequate (GIL) | **HIGH** (5s camera init) |
| mg6010_controller | SingleThreaded | 0 (default) | Adequate (`std::mutex`) | **CRITICAL** (blocking service) |
| motion_controller | SingleThreaded | 0 (default) | Adequate (`std::mutex`) | **MODERATE** (long trajectories) |
| odrive_service | SingleThreaded | 0 (default) | Good (`std::mutex`) | MINIMAL |
| **vehicle_control** | **SingleThreaded** | **0 (default)** | **NONE (3 threads, 0 locks)** | **HIGH (3 unmanaged threads)** |

Vehicle control is the **only production node** with zero thread safety. All C++ nodes use
`std::mutex`; even the Python cotton_detection node relies on the GIL (imperfect but present).
The vehicle node's 3 raw `threading.Thread` instances bypass both the executor and the GIL
for non-trivial shared state mutations.

---

## 15. Open Questions Requiring Decision

1. **CPU profiling first?** Before committing to any path, should we profile the actual
   >50% CPU usage with `py-spy` to understand WHERE the time is spent? This is a 1-hour
   task on the RPi that could fundamentally change the approach.

2. **Wire in existing modules vs. rewrite?** The ghost modules (3,813 lines) were written
   for a different version of the node. They may need significant updates to match the
   current monolith's behavior. Need to assess how much drift has occurred.

3. **Refactor then maybe C++, or C++ from the start?** Option A (refactor Python first)
   gives information before committing to C++. Option C (full C++ port) avoids doing the
   work twice but commits to 35-55 days with high risk.

4. **Scope: vehicle only or all god-classes?** Four god-classes exist. Fixing one while
   ignoring the others only partially addresses the problem. Should the refactoring be
   scoped to vehicle_control alone, or planned as a codebase-wide effort?

---

## 16. ROS2 Best Practices & Engineering Gap Analysis

This section compares Pragati's current architecture against ROS2 community best practices,
production-grade reference projects (Nav2, MoveIt2, ros2_control), and general robotics/software
engineering principles. The goal is not criticism -- it is to identify specific, actionable gaps
that compound into the tech debt documented in Sections 13-14.

### 16.1 Reference Architecture: How Nav2/MoveIt2 Structure Equivalent Complexity

Nav2 (Navigation2) manages more complexity than Pragati's vehicle control -- path planning,
costmaps, recovery behaviors, controller servers -- yet has **zero god-classes**. The key
structural differences:

| Dimension | Nav2 / MoveIt2 | Pragati (vehicle_control) |
|-----------|---------------|--------------------------|
| Lifecycle nodes | 100% of servers | 0% (zero lifecycle nodes in entire project) |
| Node composition | Component containers, multi-node executables | Monolithic single-node processes |
| Plugin architecture | 6+ plugin interfaces (planner, controller, recovery, costmap layers) | 0 plugin interfaces |
| Behavior trees | Core architecture (BT-CPP) for mission logic | Inline if/elif chains in 92-method monolith |
| Callback groups | MutuallyExclusive for state, Reentrant for reads | None declared (everything in default group) |
| Executor model | MultiThreadedExecutor with explicit callback groups | SingleThreadedExecutor everywhere |
| God-classes | 0 | 4 (vehicle_control, mg6010, motion_controller, odrive) |
| Parameter validation | `declare_parameter` with ranges, `on_set_parameters_callback` | Hardcoded constants, no runtime validation |
| Error escalation | Retry → degrade → isolate → stop → alert | Silent `except Exception: pass` |
| Hardware abstraction | ros2_control with HardwareInterface plugins | Direct pigpio/CAN calls inside node logic |

### 16.2 Lifecycle Nodes (REP-2010)

**What they are:** Managed nodes with states: Unconfigured → Inactive → Active → Finalized.
Transitions are explicit (`on_configure`, `on_activate`, `on_cleanup`, `on_shutdown`) and
can be orchestrated by a lifecycle manager.

**Why they matter for Pragati:**
- The vehicle node's 86-line `_initialize_hardware()` conflates configuration with activation.
  If GPIO init fails, the node is in an undefined state -- partially constructed, no clean teardown.
- Lifecycle nodes give you a **free shutdown path**: `on_deactivate` stops timers/publishers,
  `on_cleanup` releases hardware. Currently `_execute_shutdown` (117 lines) reimplements this
  ad-hoc with subprocess calls and thread joins.
- The `pauseCamera` state lie (Tech Debt #TD-CRIT-006) would not exist -- you either transition
  to Inactive (cameras stop) or stay Active (cameras run). No boolean flags lying about system
  state.
- Nav2's lifecycle manager can bring up/tear down the entire navigation stack in dependency
  order. Pragati's multi-arm system (1-6 RPis) has no equivalent orchestration.

**Gap:** 0% lifecycle node adoption. All 8 production nodes use basic `rclcpp::Node` or
`rclpy.node.Node`. This is the single highest-impact architectural gap.

### 16.3 Node Composition & The Thin Node Pattern

**What it is:** Each ROS2 node should be a thin wrapper around a testable library. The node
handles only ROS2 plumbing (subscriptions, publishers, timers, parameters). All business
logic lives in plain classes with no ROS2 dependency.

```
# Ideal structure (what Nav2 does)
class VehicleStateMachine:       # Pure Python/C++, no ROS2 imports, fully unit-testable
class SafetyManager:             # Pure Python/C++, no ROS2 imports, fully unit-testable
class VehicleControlNode(Node):  # Thin: wires ROS2 topics to the above classes
```

**Why it matters for Pragati:**
- The vehicle node's 92 methods mix ROS2 callbacks with GPIO reads, MQTT publishes, state
  machine transitions, and motor commands. You cannot test `_send_drive_position_incremental`
  (157 lines) without mocking 8+ ROS2 interfaces.
- The existing ghost modules (`core/state_machine.py`, `core/safety_manager.py`) actually
  follow this pattern -- they are pure Python classes. They just were never wired in.
- The 31 CPU-fix tests require extensive mocking precisely because the node is fat, not thin.
  With thin nodes, you unit-test the library classes directly (fast, no mocks), and only
  need a few integration tests for the ROS2 wiring.

**Gap:** Zero thin nodes in production. Every node embeds all logic directly.

### 16.4 Callback Groups & Executor Model

**What they are:** Callback groups control concurrency in multi-threaded executors:
- `MutuallyExclusiveCallbackGroup`: Only one callback at a time (protects shared state)
- `ReentrantCallbackGroup`: Multiple callbacks can run simultaneously (for independent reads)

**Current state in Pragati:**
- All production nodes use `SingleThreadedExecutor` (the default)
- The vehicle node spawns **3 additional threads** (`_poll_joystick_blocking`,
  `_process_physical_switches`, `_run_health_monitor`) outside the executor entirely
- These threads share state (`self.current_state`, `self.emergency_stop_active`,
  `self.is_moving`) with zero locks -- **Tech Debt #TD-CRIT-001**
- This is the worst of both worlds: single-threaded executor (so timer callbacks can't
  overlap) plus unmanaged threads (so state races happen anyway)

**What should happen:**
- Use `MultiThreadedExecutor`
- Put joystick polling, GPIO reading, and health monitoring in `ReentrantCallbackGroup`
  (they read independent hardware)
- Put state machine transitions and motor commands in `MutuallyExclusiveCallbackGroup`
  (they modify shared state)
- Eliminate raw `threading.Thread` entirely -- use ROS2 timers with appropriate callback groups
- On RPi 4B (4 cores): pin executor to cores 1-2 for ROS2 callbacks, core 3 for DDS, core 0
  for OS/kernel. This requires `taskset` or `cpu_affinity` in launch files.

**Gap:** No callback groups declared anywhere in the project. Thread safety is manual
(and broken).

### 16.5 Behavior Trees vs. Inline State Logic

**What they are:** Behavior Trees (BT-CPP in ROS2) separate mission logic from execution.
A tree of Action/Condition/Control nodes orchestrates what the robot does, while action
servers handle how.

**Why it matters:**
- The vehicle node's operational modes (IDLE → ARMED → MANUAL → AUTO → PICKING) are
  encoded as string comparisons in `_process_gpio_inputs` (90 lines) and scattered across
  multiple methods. Adding a new mode requires touching 5+ methods.
- The ghost `core/state_machine.py` (266 lines) is better -- it has formal states and
  transition guards -- but it's still a flat FSM. For cotton picking, the mission logic
  is hierarchical: navigate to row → scan for cotton → approach plant → pick → stow →
  next plant → end of row → next row.
- Nav2 uses BT-CPP for exactly this: the tree structure makes it trivial to add recovery
  behaviors, parallel monitoring (battery, obstacle, e-stop), and conditional branches.

**Pragmatic assessment:** Behavior trees are the right long-term architecture for the
picking mission, but introducing BT-CPP now (before the monolith is decomposed) would add
complexity without benefit. **Priority: decompose first, BT second.** The FSM in
`core/state_machine.py` is a reasonable intermediate step.

### 16.6 Hardware Abstraction (ros2_control)

**What it is:** ros2_control provides a standardized `HardwareInterface` plugin system.
Hardware drivers implement `read()` and `write()` methods. Controllers (PID, trajectory,
diff-drive) are loaded as plugins. The resource manager handles lifecycle.

**Current state in Pragati:**
- Motor commands go through `ROS2MotorInterface` (which publishes to topics) AND through
  direct `motor_position_pubs`/`motor_velocity_pubs` created in the vehicle node -- the
  **duplicate command path bug** (Section 5.3)
- GPIO is accessed via raw `pigpio` calls inside the vehicle node
- The MG6010 controller (4,511 lines) directly manages CAN bus frames
- No abstraction layer between "desired joint position" and "CAN frame bytes"

**What ros2_control would give:**
- Single `HardwareInterface` plugin per actuator type (MG6010, MG6012, ODrive)
- Standard `JointTrajectoryController` or `DiffDriveController` plugins
- Hardware lifecycle managed by the framework (not ad-hoc init/shutdown code)
- Gazebo simulation via `gazebo_ros2_control` plugin (currently Pragati maintains a
  separate simulation path)

**Pragmatic assessment:** Full ros2_control adoption is a large effort (especially for
the custom CAN bus protocol). However, even a thin HAL layer (without full ros2_control)
would eliminate the duplicate command path and centralize hardware access. This is
achievable during the vehicle node decomposition.

### 16.7 Error Handling & Graceful Degradation

**Best practice -- Error Escalation Hierarchy:**
```
RETRY (transient) → DEGRADE (drop non-critical) → ISOLATE (fence off subsystem)
→ STOP (safe halt) → ALERT (notify operator)
```

**Current state in Pragati:**
- Multiple `except Exception: pass` blocks (silent swallowing -- Tech Debt #TD-CRIT-005)
- No circuit breaker pattern in production (the ghost `utils/circuit_breaker.py` exists
  but is unused)
- No degraded mode definitions (what happens if MQTT fails? Joystick disconnects? One
  motor faults?)
- E-stop is all-or-nothing -- no partial isolation of a faulty arm
- The health monitor (`_run_health_monitor`) logs warnings but takes no corrective action

**What should exist:**
- Per-subsystem health states: HEALTHY → DEGRADED → FAULTED → ISOLATED
- Defined degradation policies: "If MQTT fails, continue in local-only mode"
- Circuit breaker on CAN bus communication (3 failures → open circuit → periodic retry)
- Watchdog with teeth: if health monitor detects stale data, transition to safe state
  (not just log a warning)
- `diagnostic_updater` integration for ROS2-standard health reporting

### 16.8 Testing Pyramid & Verification Practices

**Best practice testing pyramid for ROS2 robotics:**

```
        /‾‾‾‾‾‾\          Field tests (2%) - real hardware, real environment
       /  System  \         System tests (8%) - full stack, simulated or HIL
      / Integration \       Integration tests (20%) - multi-node, launch_testing
     /    Unit Tests  \     Unit tests (70%) - single class/function, fast
    /‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\
```

**Current state in Pragati:**
- 31 unit tests for vehicle node CPU fix -- all heavily mocked, verify structure not behavior
- C++ packages have gtest suites but coverage is unknown
- Zero `launch_testing` integration tests (multi-node startup, topic flow, lifecycle)
- Zero Hardware-in-the-Loop (HIL) tests
- Zero Software-in-the-Loop (SIL) tests with Gazebo
- Performance claims based on manual `pidstat` -- no automated regression benchmarks
- No property-based testing (e.g., hypothesis for fuzzing motor command ranges)

**What Nav2/MoveIt2 do:**
- `launch_testing` for every server: bring up nodes, send goals, verify results, tear down
- Integration tests that verify topic connections and QoS compatibility
- Parameterized tests across different configurations
- CI runs tests on every PR with coverage gates

**Key missing practice:** `launch_testing` for multi-node integration. This would catch
the duplicate publisher bug, the state race conditions, and the lifecycle gaps automatically.

### 16.9 Configuration Management

**Best practice:**
- All tunable parameters declared via `declare_parameter()` with type and range constraints
- `on_set_parameters_callback` for runtime validation
- Launch files pass parameters; YAML files provide defaults
- Single source of truth (no hardcoded values duplicated across files)

**Current state:**
- The ghost `utils/configuration_manager.py` (876 lines) implements YAML config with
  validation -- but is unused
- The vehicle node hardcodes timer periods, thresholds, motor IDs, GPIO pins as class
  constants
- Some values are duplicated between the vehicle node and motor controller
- No runtime parameter reconfiguration support

### 16.10 Quantitative Gap Summary

| Practice | Nav2/MoveIt2 | Pragati Current | Priority | Effort |
|----------|:------------:|:---------------:|:--------:|:------:|
| Lifecycle nodes | 100% | 0% | **P0** | M |
| Callback groups | All nodes | None | **P0** | S |
| Thin node pattern | Standard | 0 nodes | **P1** | L (part of decomposition) |
| Plugin architecture | 6+ interfaces | 0 | P2 | L |
| Behavior trees | Core arch | None | P3 | XL |
| ros2_control HAL | Standard | None | P2 | XL |
| Error escalation | 5-level | Silent catch | **P0** | M |
| launch_testing | All servers | 0 tests | **P1** | M |
| Parameter validation | Standard | Hardcoded | P2 | S |
| diagnostic_updater | Standard | None | P2 | S |
| QoS profiles | Explicit per topic | All defaults | P2 | S |

Priority: P0 = safety-critical/blocking, P1 = high-impact, P2 = significant, P3 = long-term.
Effort: S = days, M = 1-2 weeks, L = 2-4 weeks, XL = 1+ months.

### 16.11 Recommended Incremental Adoption Path

These are not additional tasks -- they integrate with the existing decomposition plan:

**Phase 1 (During vehicle node decomposition):**
1. Add callback groups to the decomposed vehicle nodes (zero cost if doing it from scratch)
2. Switch to `MultiThreadedExecutor` (one-line change per launch file)
3. Adopt thin node pattern -- the ghost modules already follow it, just wire them in
4. Replace `except Exception: pass` with error escalation in new code
5. Add `launch_testing` for the new multi-node vehicle control

**Phase 2 (After decomposition stabilizes):**
6. Convert vehicle control nodes to lifecycle nodes
7. Integrate `diagnostic_updater` for health reporting
8. Add circuit breaker to CAN bus communication (wire in ghost `circuit_breaker.py`)
9. Define explicit QoS profiles per topic based on reliability requirements

**Phase 3 (Long-term architecture):**
10. Evaluate ros2_control for motor hardware abstraction
11. Evaluate BT-CPP for picking mission orchestration
12. Plugin architecture for swappable detection/planning algorithms

### 16.12 What "Well-Engineered" Looks Like for This Robot

A well-engineered ROS2 cotton picking robot at Pragati's scale (single RPi 4B per arm,
CAN bus motors, OAK-D cameras) would have approximately this package structure:

```
pragati_bringup/          # Launch files, parameter YAML, system orchestration
pragati_description/      # URDF/xacro, meshes, joint definitions
pragati_interfaces/       # All custom msg/srv/action definitions
pragati_hardware/         # ros2_control HardwareInterface plugins (MG6010, MG6012, ODrive)
pragati_control/          # Controllers (diff_drive, arm joints) -- or use ros2_controllers
pragati_perception/       # Cotton detection, depth processing (thin node over library)
pragati_planning/         # Pick planning, motion planning (thin node over library)
pragati_navigation/       # Row following, waypoint navigation
pragati_behavior/         # BT-CPP trees for mission logic
pragati_safety/           # E-stop, watchdog, fault manager (lifecycle managed)
pragati_diagnostics/      # System health, thermal monitoring, diagnostic_updater
pragati_mqtt_bridge/      # Multi-arm communication bridge
pragati_simulation/       # Gazebo plugins, test worlds
```

Each package would have:
- Lifecycle-managed nodes
- Thin node + library separation
- Unit tests (gtest/pytest) + launch_testing integration tests
- Explicit callback groups and QoS profiles
- Parameter declarations with validation

This is the target architecture. The current 8-package structure with 4 god-classes
is roughly 30% of the way there.

### 16.13 RPi 4B Resource Budget

For a single RPi 4B (4 cores @ 1.8GHz, 8GB RAM) running one arm's full stack:

| Core | Assignment | Rationale |
|:----:|-----------|-----------|
| 0 | Linux kernel, DDS discovery, system services | Keep RT paths off core 0 |
| 1 | Motor control executor (CAN bus, joint controllers) | Highest frequency, lowest latency |
| 2 | Perception + planning (OAK-D, cotton detection) | GPU/VPU offload, CPU for pre/post |
| 3 | Vehicle control, safety, diagnostics, MQTT | Lower frequency orchestration |

**Per-process CPU budget:**
- Motor control: ≤25% of one core (100Hz timer callbacks)
- Perception: ≤50% of one core (30fps with VPU offload)
- Vehicle control: ≤15% of one core (5-10Hz orchestration -- currently **>50%**)
- Safety/diagnostics: ≤5% of one core
- DDS + system: ≤20% of one core

The vehicle node's current >50% CPU usage is **5x over budget** for its functional role.
This reinforces either the C++ port (Option B/C) or aggressive timer rationalization.

---

## 17. ODrive Drivetrain Dependency Risks

The ODrive node (`odrive_service_node.cpp`, 1,580 lines) is the vehicle's **drivetrain** --
it controls the drive wheels via CAN bus. The vehicle node sends velocity/position commands
that flow through ODrive to actual wheel motion. Yet the refactoring analysis (until now)
treated ODrive as a peripheral concern. The Tech Debt Analysis identifies **4 items** that
directly threaten vehicle reliability:

### 17.1 Silent CAN Write Failures (TD-CRIT-1.8)

**Finding:** `send_frame()` return value is discarded everywhere in `odrive_service_node.cpp`.
If the CAN bus write fails (loose connector, bus-off, buffer full), the node has no idea.
The vehicle thinks it sent a "move forward" command, but the wheels never received it.

**Vehicle impact:** The vehicle silently stops responding to drive commands. In a field,
the robot stalls mid-row with no error indication. The vehicle node's health monitor won't
detect this because it monitors its own internal state, not ODrive's CAN success rate.

**Fix:** Check `send_frame()` return, increment failure counter, trigger circuit breaker
after N consecutive failures. **Phase 1 (pre-field-trial), ~1 day effort.**

### 17.2 ~~No Heartbeat Timeout Detection (TD-HIGH-2.3)~~ ✅ RESOLVED

**Finding:** `odrive_service_node.cpp` tracks `last_heartbeat_time` but **never checks it
for staleness**. If the ODrive motor controller dies (power loss, firmware crash), the
timestamp goes stale silently. No alarm, no failsafe.

**Vehicle impact:** A dead drive motor is **invisible** to the system. If one of two drive
wheels dies, the vehicle veers or drifts with no indication. The vehicle node continues
sending commands to a dead actuator.

**Fix:** ~~Add a timer that checks `now() - last_heartbeat_time > threshold`. If stale,
publish diagnostic error and trigger vehicle node safe-stop. **Phase 2, ~0.5 day effort.**~~ **RESOLVED (bad11785, Mar 14):** 1Hz wall timer checks `last_heartbeat_time` with 2s timeout. Transition-based RCLCPP_ERROR on stale detection, RCLCPP_WARN on recovery. 9 gtests added.

### 17.3 Zero Automated Tests (TD-HIGH-2.7)

**Finding:** `odrive_service_node.cpp` has **zero test files**. The `src/odrive_control_ros2/`
directory has no `test/` subdirectory. Every change to the ODrive node is deployed to the
field with no automated verification.

**Vehicle impact:** The ODrive node is a **1,580-line untested dependency** of the vehicle.
Any refactoring of the vehicle-to-ODrive interface (which will happen during decomposition)
has no safety net.

**Fix:** Add gtest unit tests for CAN protocol encoding/decoding, heartbeat logic, and
stall detection. Add `launch_testing` integration test for vehicle→ODrive command flow.
**Phase 2, ~2-3 days effort.**

### 17.4 State Divergence Risk (TD-MOD-3.4)

**Finding:** `motion_in_progress_` flag tracks the same concept as `global_motion_state_ ==
EXECUTING` but they are set and cleared independently. If one is updated but not the other,
the node's internal state is inconsistent.

**Also:** `STALL_POSITION_THRESHOLD = 0.01m`, `STALL_ERROR_THRESHOLD = 0.1m`,
`STALL_CHECK_INTERVAL = 2.0s` are hardcoded constants (lines 1098-1100). Vehicle drive stall
detection tuning requires recompiling the ODrive node -- no runtime parameter adjustment.

**Vehicle impact:** State divergence could cause the vehicle to think it's moving when it's
stalled (or vice versa). Hardcoded stall thresholds cannot be tuned for different terrain
or load conditions without a rebuild.

### 17.5 Stale 6-Motor Mapping (vehicle_control package bug)

**Finding:** `vehicle_control/hardware/ros2_motor_interface.py` still maps **6 MG6010 motors**
(3 steering + 3 drive) even though drive wheels moved to ODrive. The `MAX_MOTORS = 6`
hardcoded value in `mg6010_controller_node.cpp` (line 83) also reflects the old layout.

**Vehicle impact:** The vehicle_control package maintains a phantom mapping for 3 drive
motors that no longer exist as MG6010 units. This is not actively harmful (ODrive handles
drive), but it creates confusion during refactoring and wastes resources publishing to
nonexistent motor topics.

**Fix:** Remove the 3 drive motor entries from `ros2_motor_interface.py`, update
`MAX_MOTORS` in mg6010 to 3 (or make it configurable). **Part of Phase 3 decomposition.**

### 17.6 Implications for Vehicle Refactoring

The ODrive findings change the refactoring approach:

1. **Phase 1 (1.8) must complete before vehicle decomposition begins.** Silent CAN failures
   would confound testing of the decomposed vehicle nodes.
2. **Phase 2 (~~2.3~~, 2.7) should overlap with early decomposition.** ~~Heartbeat timeout~~ ✅ (2.3 done, bad11785) and basic tests (2.7 pending) give confidence that the vehicle→ODrive interface works correctly.
3. **The vehicle→ODrive interface should be a first-class concern** in the decomposed design,
   not buried in the monolith. A dedicated `drive_controller` module (or node) should own
   the ODrive command path, health monitoring, and stall detection.
4. **Stall thresholds must become ROS2 parameters** before field trials on varied terrain.

---

## 18. Updated Risk Summary (Incorporating Tech Debt Cross-References)

### Exception Handler Risk Profile (Corrected)

The 19 silent exception-swallowing blocks in vehicle_control break down as:

| Category | Count | Lines | Risk |
|----------|:-----:|-------|------|
| Shutdown/cleanup code | 11 | 3607-3754 | **Low** -- `pass` in cleanup is defensible |
| Runtime safety paths | 3 | ~525, ~3333, ~3357 | **HIGH** -- silent failure in active operation |
| Runtime non-safety | 3 | ~292, ~383, ~3480 | **Medium** -- degraded behavior possible |
| Unbound exception var | 2 | (various) | **Medium** -- catches without `as e` lose error info |

_Updated: was 17, actual count is 19 (3 bare + 14 silent pass + 2 unbound). Line numbers approximate due to file shifts. OpenSpec: `vehicle-exception-cleanup` (4825be81)._

**Implication:** The runtime-path exceptions (8 total: 3 HIGH + 3 medium + 2 unbound) are the priority. The 11 shutdown
exceptions are lower risk and can be addressed during cleanup.

### Codebase-Wide Error Handling Context

- **~200+ exception handlers** across all production nodes
- **65%** log the error and continue with no recovery, state reset, retry, or escalation
- Vehicle control has **97 handlers** (nearly half the codebase total)
- The codebase systematically violates the fail-fast principle (Tech Debt #5.6)

### Additional Vehicle-Relevant Items Not Previously Covered

| Item | Summary | Impact |
|------|---------|--------|
| 2.6 | 20+ blocking `sleep_for` in motor service callbacks | Vehicle motor commands may block longer than expected |
| 4.3 | 5 duplicate signal handlers (vehicle is one of 5) | `vehicle_control_node.py:3679` reimplements what should be shared |
| 4.4 | Dead EE timeout parameter (`end_effector_runtime_` never read; active watchdog uses `ee_watchdog_timeout_sec`) | 📋 OpenSpec: `tech-debt-quick-wins` |
| 5.2 | mg6010 ISP violation (14 services + 3 actions) | Vehicle must depend on entire mg6010 service surface for 3 steering motors |

### Cross-Reference: Tech Debt "Honest Assessment"

The updated Tech Debt Analysis includes an honest assessment that frames the debt in context:

**What's genuinely urgent (short list):**
1. Executor starvation in mg6010 (1.2) -- affects vehicle motor commands
2. **Zero locks in vehicle_control (1.3)** -- "will bite eventually"
3. Silent CAN write failures in ODrive (1.8) -- affects vehicle drivetrain

**Three highest-ROI investments (from Tech Debt Analysis):**
1. Add callback groups to all nodes -- ~2 days, eliminates entire class of starvation bugs
2. ~~Add heartbeat/CAN failure detection to ODrive~~ ✅ Done (bad11785) -- prevents silent drivetrain death
3. Behavior tree for pick cycle -- ~1-2 weeks, transforms vehicle/arm maintainability

**What Pragati got right** (for balance): Package separation from day one, CAN bus abstraction
layer, YAML motor configurations, structured JSON logging, field-trial-driven development,
ODrive migration for drive wheels, separate RPi per arm architecture, pre-commit/pre-push hooks.

---

## 19. Cross-Reference: Vehicle Nodes Refactoring Roadmap (2026-03-11)

A separate analysis session produced a prescriptive refactoring roadmap:
`docs/architecture/vehicle_nodes_refactoring_roadmap.md` (530 lines, dated 2026-03-11).

This section integrates its unique findings and flags conflicts with this analysis.

### 19.1 New Bugs Found by the Roadmap

**Bug 1: `spin_until_future_complete` Deadlock (CRITICAL)**

The vehicle node calls `self.executor.spin_until_future_complete(future)` from within
callbacks (e.g., service calls to motor controller). On a SingleThreadedExecutor, this
**deadlocks** -- the executor is already spinning the current callback and cannot process
the response. This is a known ROS2 anti-pattern.

This bug is **not in the Tech Debt Analysis** and was missed by our analysis. It should be
added to Phase 1 (pre-field-trial) fixes -- it can cause the vehicle node to hang
indefinitely during motor operations.

**Fix:** Use `callback_groups` with `ReentrantCallbackGroup` for service clients, or switch
to async service calls (`call_async` + callback). The roadmap recommends the callback group
approach (MutuallyExclusive for control loop, Reentrant for service clients).

**~~Bug 2: ODrive `request_encoder_estimates` Data Race (CRITICAL)~~ ✅ RESOLVED**

`odrive_service_node.cpp::request_encoder_estimates()` ~~reads `odrive_states_` without
holding `state_mutex_`~~ now holds `state_mutex_` via `std::lock_guard<std::mutex>`.
Fixed in odrive-data-race-heartbeat-timeout (bad11785, Mar 14). 2 mutex-coverage gtests verify all access sites hold the lock.

~~This bug is **not in the Tech Debt Analysis** and was missed by our §17. It should be
added to Phase 2 (ODrive) fixes alongside the heartbeat timeout (2.3).~~ Added to Tech Debt item 2.3 and resolved.

### 19.2 ODrive Ghost Driver Pattern

**Key insight:** The ODrive package has the same "ghost module" pattern as vehicle_control.
`ODriveCanDriver` is a clean, well-factored CAN abstraction that already exists in the
package -- but the `odrive_service_node.cpp` **doesn't use it**. Instead, the node
reimplements CAN frame encoding/decoding inline.

This mirrors our Appendix B finding exactly: the good code is written, it just isn't wired in.
The roadmap's ODrive migration plan (10 steps, 4-5 weeks) centers on wiring `ODriveCanDriver`
into the node and extracting a `MotionStateMachine`, `CommandAggregator`, and
`MotorHealthMonitor`.

### 19.3 Concrete Design Artifacts (Not in This Analysis)

The roadmap provides two detailed class diagrams with method signatures:

1. **Vehicle target architecture** -- 10+ classes including `VehicleControlNode` (thin lifecycle
   node), `VehicleController`, `VehicleMotorController`, `SafetyManager`, `MQTTBridge`,
   `JoystickManager`, `GPIOManager`, `DiagnosticsPublisher`.
2. **ODrive target architecture** -- `ODriveServiceNode` (thin lifecycle node) →
   `ODriveCanDriver` + `MotionStateMachine` + `CommandAggregator` + `MotorHealthMonitor`.

These are implementation-ready design artifacts that complement our higher-level analysis.

### 19.4 Migration Tactic: Feature Flag for Motor Commands

The roadmap proposes a **feature flag** during the vehicle motor extraction step: both the
old inline motor path and the new `VehicleMotorController` run simultaneously, with a
flag to switch between them. This allows gradual rollover with instant rollback if the
new path misbehaves.

This is a smart risk mitigation tactic not present in our §10 (Recommended Path Forward).

### 19.5 Conflicts With This Analysis

| # | Topic | Roadmap | This Analysis | Assessment |
|---|-------|---------|---------------|------------|
| 1 | **Test-first discipline** | No test step before extraction | Phase 0: tests BEFORE refactoring (AGENTS.md TDD mandate) | **Roadmap violates project policy.** Must add test safety net. |
| 2 | **Effort estimate** | 8-10 weeks (vehicle only) | 3-4 weeks (vehicle only, excluding lifecycle) | Roadmap more realistic if LifecycleNode included. Our estimate is for wire-in-modules scope only. |
| 3 | **LifecycleNode timing** | Step 12 of migration (near end) | Deferred to future phase | Minor -- both agree it's last. Roadmap is more aggressive. |
| 4 | **ODrive→vehicle dependency** | Parallel P0/P1 workstreams | ODrive CAN fix (1.8) MUST complete before vehicle decomposition | **This analysis is safer.** Silent CAN failures confound refactoring validation. |
| 5 | **CPU burn reality** | Not mentioned anywhere | >50% CPU on RPi 4B; fix claims exaggerated (§13) | **Roadmap is unaware** of the performance reality. Affects Python viability. |
| 6 | **God-class scope** | 2 nodes (vehicle + ODrive) | 4 god-classes codebase-wide (§14) | **Roadmap is narrow.** Fixing 2 of 4 is incomplete. |

### 19.6 Recommendation

The two documents are **complementary, not competing**:
- **This analysis** provides the *why*, historical context, risk assessment, best practices
  gap analysis, and codebase-wide perspective.
- **The roadmap** provides the *how*, with concrete class diagrams, step-by-step migration
  plans, and specific API designs.

**Before executing the roadmap**, the following adjustments are needed:
1. Add Phase 0 (test safety net, 3-5 days) before any extraction step
2. Add ODrive CAN fix (1.8) as a hard prerequisite for vehicle decomposition
3. Add the `spin_until_future_complete` deadlock fix to Phase 1 pre-field-trial
4. ~~Add the ODrive `request_encoder_estimates` data race to the ODrive migration~~ ✅ Done (bad11785)
5. Acknowledge CPU burn reality -- if vehicle is still >50% CPU after refactoring,
   C++ hot paths (Appendix D, Option B) become necessary
6. Consider mg6010 and motion_controller god-classes in the broader plan

---

## Appendix A: File References

| Document | Path |
|----------|------|
| Current node | `src/vehicle_control/integration/vehicle_control_node.py` |
| Old prototype | `collected_logs/log3/refactored_example/` (gitignored, not committed) |
| Tech Debt Analysis | `docs/project-notes/TECHNICAL_DEBT_ANALYSIS_2026-03-10.md` |
| CPU Burn Fix (deferred decomposition) | `openspec/changes/archive/2026-03-10-fix-vehicle-cpu-thermal/` |
| Gap Tracking | `docs/specifications/GAP_TRACKING.md` |
| Prior refactoring: yanthra_move | `docs/project-notes/REFACTORING_COMPLETE.md` |
| Prior refactoring: cotton_detection | `src/cotton_detection_ros2/REFACTORING_NOTES.md` |
| Prior refactoring: dashboard | `openspec/changes/archive/2026-03-07-refactor-dashboard-server/` |
| Thermal failure analysis | `docs/project-notes/THERMAL_FAILURE_ANALYSIS_AND_REMEDIATION_PLAN.md` |
| Motor control analysis (2025) | `docs/project-notes/MOTOR_CONTROL_COMPREHENSIVE_ANALYSIS_2025-11-28.md` |
| ODrive service node | `src/odrive_control_ros2/src/odrive_service_node.cpp` |
| Vehicle motor interface | `src/vehicle_control/hardware/ros2_motor_interface.py` |

## Appendix B: The Ghost Modules -- 3,813 Lines Already Written But Never Wired In

A critical finding: the `vehicle_control` package already contains well-designed modular
code that was built to replace parts of the monolith, but **never connected**.

### Modules Actively Used by Monolith (3,284 lines)

| Module | Lines | Status |
|--------|------:|--------|
| `config/constants.py` | 223 | Imported, working |
| `hardware/gpio_manager.py` | 458 | Imported, working |
| `hardware/motor_controller.py` | 527 | Imported, working |
| `hardware/ros2_motor_interface.py` | 281 | Imported, working |
| `hardware/advanced_steering.py` | 369 | Imported indirectly |
| `hardware/mcp3008.py` | 209 | Imported, working |
| `utils/input_processing.py` | 460 | Imported, working |
| `utils/logging_utils.py` | 334 | Imported, working |
| `integration/imu_interface.py` | 290 | Imported, working |

### Modules Written But NEVER Used (3,813 lines -- Dead Weight)

| Module | Lines | What It Does | Why Unused |
|--------|------:|-------------|-----------|
| `core/state_machine.py` | 266 | Formal FSM with transition guards | Monolith uses inline `current_state` enum |
| `core/safety_manager.py` | 438 | E-stop, watchdog, fault detection | Monolith reimplements safety inline |
| `core/vehicle_controller.py` | 471 | Control orchestration | Monolith reimplements orchestration inline |
| `utils/configuration_manager.py` | 876 | YAML config with validation | Monolith loads YAML directly |
| `utils/circuit_breaker.py` | 291 | Failure counting, auto-recovery | Never imported anywhere |
| `hardware/velocity_kinematics_control.py` | 198 | Velocity-based control | Never imported anywhere |
| `hardware/test_framework.py` | 288 | 35+ hardware tests | Never imported anywhere |
| `integration/system_diagnostics.py` | 985 | sysfs reads, JSON generation | **Broken** -- imports non-existent `RobustMotorController`. _📋 OpenSpec: `tech-debt-quick-wins`_ |

### Critical Bugs Found

1. **Duplicate motor command paths** -- The monolith creates its own
   `motor_position_pubs`/`motor_velocity_pubs` AND uses `ROS2MotorInterface` which creates
   identical publishers. Two pathways to the same motors exist simultaneously.
2. **`system_diagnostics.py` is broken** -- Imports `RobustMotorController` which only
   exists in archive. Would crash if instantiated. _📋 OpenSpec: `tech-debt-quick-wins`_

### Implication for Refactoring

The refactoring is NOT a greenfield design exercise. Most of the modular code already
exists. The real task is **wiring in what's already built** and removing the inline
reimplementations from the monolith. This dramatically reduces the effort estimate.

---

## Appendix C: Authorship Analysis

### Commit Ownership

| Author | Commits on Node | Share | Role |
|--------|---------------:|------:|------|
| **Udaya Kumar** | 43 | ~80% | Architecture, ROS2 integration, hardening |
| **Gokul K** | 11 | ~20% | Hardware tuning, motor params, GPIO config |
| **Vasanthakumar A** | 0 (node), 3 (package) | — | Gazebo simulation integration |
| **Pragati Developer** | 1 | — | Initial seed commit |

### Key Timeline

- **Sep 2025:** Initial 783-line seed (Pragati Developer, bulk import)
- **Dec 4-9 2025:** Udaya wrote the entire ROS2 integration (15 commits in 5 days)
- **Dec 16-Jan 2026:** Collaborative phase -- Gokul pushes hardware changes, Udaya
  hardens immediately after (pair-style development)
- **Feb 2026:** ODrive integration, field trial readiness (Udaya primary)
- **Mar 2026:** GPIO consolidation, CPU burn fix (Udaya primary, one Gokul fix)

### The Revert Event

On Feb 24, Gokul synced vehicle/motor/odrive package updates (`96f3b143`). Udaya reverted
it the next day (`f9bdd4f2`), suggesting the sync introduced conflicts with field-trial
readiness work. This highlights the risk of changes without coordination.

---

## Appendix D: C++ vs Python Assessment

### Should vehicle_control_node be ported to C++?

**Recommendation: Decision deferred. Need real CPU measurements first.**

The previous analysis said "keep Python" based on the assumption that CPU burn was solved
(97.5% -> 7.3%). That claim is **exaggerated** -- actual RPi 4B measurements show >50% CPU.
This changes the calculus significantly.

| Factor | Assessment |
|--------|-----------|
| **Performance** | CPU burn NOT solved. Still >50% on RPi 4B. Python overhead is a real concern. |
| **Porting effort** | 35-55 engineering days for ~14,600 lines. |
| **Dependencies** | All Python libs have C++ equivalents (pigpio, paho-mqtt, yaml-cpp). No blockers. |
| **Risk** | HIGH regression risk on safety-critical vehicle control during port. |
| **Consistency** | All 4 other production nodes are C++. Python is the outlier. |
| **GIL concern** | 3 threads with zero locks rely on GIL. PEP 703 (free-threading) would break this. |

### Three Options

**Option A: Refactor Python first, measure, then decide (Recommended)**
- Wire in existing modules (2-3 weeks)
- Add threading locks and proper tests
- Measure CPU on RPi 4B with the refactored code
- If still >30% CPU: proceed to C++ port for hot paths
- If <20% CPU: stay Python

**Option B: Hybrid -- hot paths in C++, orchestration in Python**
- Port GPIO (10Hz, E-stop critical), MCP3008 joystick, and drive controller to C++
  as separate ROS2 nodes
- Keep MQTT, diagnostics, shutdown, orchestration in Python
- Effort: ~15-20 days (subset of full port)
- Risk: moderate (new IPC boundaries, but each piece is simpler)

**Option C: Full C++ port alongside refactoring**
- Do the decomposition AND port to C++ simultaneously
- Effort: 35-55 engineering days
- Risk: very high (two major changes at once, no safety net)
- Benefit: consistency with rest of codebase, no GIL concerns, lower CPU guaranteed

### Why C++ Was Right for Other Packages

| Package | Why C++ | Frequency | Justification |
|---------|---------|-----------|--------------|
| motor_control_ros2 | Real-time CAN bus | 100-1000Hz | GC pauses unacceptable |
| cotton_detection_ros2 | DepthAI C++ API, VPU pipeline | 30fps | Throughput-critical |
| yanthra_move | Tight motion control loops | 50-100Hz | Deterministic timing |
| odrive_control_ros2 | CAN bus motor commands | 100Hz+ | Low-latency critical |
| **vehicle_control** | **5Hz control loop, GPIO, joystick** | **5-10Hz** | **Unclear -- CPU still >50%** |

### Hardware Dependency Portability

Every Python dependency has a C++ equivalent already available:

| Python | C++ Equivalent | In Project Already? |
|--------|---------------|:--:|
| pigpio (GPIO) | `pigpiod_if2.h` | YES -- `motor_control_ros2/gpio_interface.cpp` |
| pigpio (SPI) | `pigpiod_if2.h spi_*` | Partial -- GPIO yes, SPI needs adding |
| paho-mqtt | `libpaho-mqttpp3` | NO -- new dependency |
| psutil | Read `/proc/self/stat` | Trivial |
| PyYAML | `yaml-cpp` or `nlohmann::json` | YES -- nlohmann used in cotton_detection |
| threading | `std::thread` + `std::mutex` | YES -- used throughout C++ packages |

**No blocking dependencies for C++ port.** The decision is purely about effort vs benefit.

---

## Appendix E: Current Node Method Inventory (92 Methods)

See Section 3B for the full functional area breakdown. Top 10 by complexity:

| Rank | Method | Lines | Why Complex |
|------|--------|------:|-------------|
| 1 | `__init__` | 159 | 30+ instance vars across 6 domains |
| 2 | `_send_drive_position_incremental` | 157 | 5-level nesting, blocking waits, joystick release |
| 3 | `_process_physical_switches` | 129 | Edge detection + MQTT + shutdown timer |
| 4 | `_execute_shutdown` | 117 | Subprocess + thread + multi-phase |
| 5 | `_run_startup_self_test` | 99 | 5-part sequential test |
| 6 | `_poll_joystick_blocking` | 97 | Normalization + idle + drive_stop |
| 7 | `_cmd_vel_callback` | 94 | Direction override + deadband + mode switch |
| 8 | `_motor_joint_states_callback` | 91 | Unit conversion + dual storage |
| 9 | `_process_gpio_inputs` | 90 | Auto mode + direction + physical switches |
| 10 | `_initialize_hardware` | 86 | Multi-subsystem init with fallbacks |
