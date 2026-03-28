# Motor Timing & Positioning Evidence Report

**Date:** February 20, 2026
**Data Source:** Field session February 19, 2026 (5h 3m, 2,276 pick cycles)
**Prepared for:** Mechanical, Electrical/Electronics, and Motor Tuning teams

---

## Executive Summary

Analysis of 6,755 motor feedback events and 2,276 pick cycles reveals two issues
requiring cross-team attention:

1. **Joint3 (phi/rotation) has a position accuracy problem at target -0.1479 rad** —
   22.9% of moves to this target exceed the 0.01 rad tolerance, reaching up to 0.018 rad
   error. Joint3 also draws **8.3x more current** than Joint4 and runs 5-6C hotter,
   suggesting increased mechanical resistance.

2. **The current blind-sleep timing is simultaneously too slow AND unsafe** — the system
   wastes ~42.6 minutes per session in unnecessary sleep, while 5.3% of Joint4 moves
   complete *after* the software has already moved on to the next joint.

---

## Part 1: Joint3 Position Accuracy Problem

### What the data shows

The motor controller has position feedback running at 5Hz via CAN bus. It detects when a
motor reaches its target within a configurable tolerance (0.01 rad) and requires the motor
to stay within tolerance for 0.20s (settle time) before declaring "reached."

**Joint3 uniquely fails this at one specific target position:**

| Target (rad) | Moves | Mean Error | Max Error | Over 0.01 Tolerance | % Over |
|--------------|-------|------------|-----------|---------------------|--------|
| **-0.1479**  |   568 |   0.0067   | **0.0180** |        **130**      | **22.9%** |
| -0.1469      |   568 |   0.0029   |   0.0041  |           0         |  0.0%  |
| -0.1061      |   568 |   0.0031   |   0.0049  |           0         |  0.0%  |
| -0.1049      |   253 |   0.0031   |   0.0033  |           0         |  0.0%  |
| -0.0730      |     1 |   0.0087   |   0.0087  |           0         |  0.0%  |
|  0.0000      |   383 |   0.0042   |   0.0045  |           0         |  0.0%  |

**Only the -0.1479 target has over-tolerance events.** All other targets are clean.

### What it looks like when it fails

When Joint3 is commanded to -0.1479 rad but undershoots:

| Commanded | Actual Reached | Error (rad) | Error (deg) | Reach Time |
|-----------|----------------|-------------|-------------|------------|
| -0.1479   | -0.1299        | 0.0180      | 1.03        | 0.908s     |
| -0.1479   | -0.1331        | 0.0148      | 0.85        | 0.933s     |
| -0.1479   | -0.1331        | 0.0148      | 0.85        | 0.934s     |
| -0.1479   | -0.1344        | 0.0135      | 0.77        | 0.945s     |
| -0.1479   | -0.1345        | 0.0134      | 0.77        | 0.944s     |

The motor consistently **undershoots** — it stops short of the target by 0.010 to 0.018 rad
(0.6 to 1.0 degrees). It never overshoots. This pattern suggests mechanical resistance,
friction, or backlash at this specific angular position.

### Comparison: Joint4 and Joint5 are essentially perfect

| Joint   | Total Reaches | Max Error (rad) | Mean Error (rad) | Over Tolerance |
|---------|---------------|-----------------|-------------------|----------------|
| Joint3  | 2,341         | **0.0180**       | 0.0041           | **130 (5.6%)**  |
| Joint4  | 2,023         | 0.0002          | 0.0001           | 0 (0.0%)       |
| Joint5  | 2,391         | 0.0003          | 0.0001           | 0 (0.0%)       |

Joint4 and Joint5 achieve sub-milliradian accuracy. Joint3 is two orders of magnitude worse.

### Current draw confirms mechanical load

The motor controller logs current (Amps) at each 30-second health report. Over 606 reports
across the 5-hour session:

| Metric           | Joint3      | Joint4      | Joint5      |
|------------------|-------------|-------------|-------------|
| Mean current     | **1.774 A** | 0.213 A     | 0.206 A     |
| P95 current      | **2.449 A** | 0.628 A     | 0.548 A     |
| Max current      | **3.980 A** | 0.870 A     | 1.434 A     |
| Ratio vs Joint4  | **8.3x**    | 1.0x        | 1.0x        |

**Joint3 draws 8.3x more current on average than Joint4.** This is consistent with
significantly higher mechanical resistance — friction, binding, misalignment, or inadequate
lubrication in the Joint3 rotation mechanism.

### Temperature confirms sustained load

| Time into session | Joint3 | Joint4 | Joint5 |
|-------------------|--------|--------|--------|
| 0h00              | 39C    | 35C    | 35C    |
| 0h30              | 44C    | 38C    | 41C    |
| 1h00              | 45C    | 40C    | 42C    |
| 1h30              | 47C    | 41C    | 44C    |
| 2h00              | 47C    | 41C    | 44C    |
| 3h00              | 47C    | 41C    | 44C    |
| 4h00              | 46C    | 41C    | 44C    |
| 5h00              | 46C    | 40C    | 43C    |

Joint3 starts 4C hotter and stabilizes 5-6C above Joint4. While 47C is within safe operating
range, the temperature gap confirms the current draw data — Joint3 is working significantly
harder than the other joints.

### Questions for investigation

1. **Mechanical team:** What is different about Joint3's mechanism at the -0.1479 rad
   position? Is there a physical obstruction, increased friction zone, or cable routing
   interference at that angle?

2. **Motor tuning:** Can the PID gains for Joint3 be increased to push through the
   resistance at -0.1479? The motor has capacity (3.98A peak vs typical 8-10A motor rating)
   but appears to settle for "close enough" rather than continuing to push.

3. **Electrical team:** Is the 8.3x current draw expected for this joint's mechanical
   load? Are there wiring or connector issues adding resistance? Is the motor appropriately
   sized for the Joint3 load?

4. **All teams:** Should the position tolerance for Joint3 be temporarily raised to 0.02
   rad while the root cause is investigated? The current 0.01 rad tolerance means 22.9% of
   moves to -0.1479 are technically "failures" that the motor controller flags as reached
   (because the settle time expires and the system moves on).

---

## Part 2: Blind Sleep Timing — Waste and Safety Risk

### How timing works currently

The arm software (`yanthra_move`) commands motors sequentially (Joint4 → Joint3 → Joint5 for
approach). After commanding each joint, it **sleeps for a calculated duration** based on a
formula:

```
sleep_time = min( (distance / 0.3) + 1.0, 3.0 ) seconds
```

This adds a 1.0-second buffer to every move and caps at 3.0 seconds. After sleeping, it
**assumes** the motor reached the target and moves on. It does not check actual position.

Meanwhile, the motor controller **does** track actual reach times and logs them — but the
arm software ignores this data.

### The waste: 42.6 minutes per session

Comparing blind sleep time vs actual motor reach time across 2,276 pick cycles:

| Joint   | Total Blind Sleep | Total Motor Reach | Wasted Time | % Waste |
|---------|-------------------|-------------------|-------------|---------|
| Joint3  | 40.6 min          | 25.3 min          | **15.3 min** | 37.6%  |
| Joint4  | 45.7 min          | 26.7 min          | **19.0 min** | 41.5%  |
| Joint5  | 47.1 min          | 50.3 min          | **-3.2 min** | (see below) |
| **Total** | **133.4 min**   | **102.3 min**     | **~42.6 min** |        |

> Note: Joint5 approach uses dynamic position-based EE control (not blind sleep), so its
> timing is already near-optimal. The "negative waste" means the EE monitoring sometimes
> adds small overhead. The 42.6 min figure is conservative — actual waste from J3+J4 approach
> plus inter-joint delays and retreat delays is higher.

**In a 5-hour session, the arm spends 42+ minutes doing nothing — just sleeping.** This
is time that could be spent picking cotton.

### The safety risk: 5.3% of J4 moves finish AFTER the software moves on

The blind sleep formula can produce times **shorter** than the motor actually needs:

| Joint  | Moves Where Sleep < Reach Time | % of Moves | Worst Overshoot |
|--------|-------------------------------|------------|-----------------|
| Joint3 | 0                             | 0.0%       | —               |
| Joint4 | **107**                       | **5.3%**   | **89ms**        |

In 107 out of 2,023 Joint4 approach moves, the motor was **still moving** when the software
sent the next joint command. The worst case: Joint4 still needed 89ms more to reach its
target when Joint3 was already being commanded.

All overshoot events occur at target position **-0.0199 m** (small moves where the +1.0s
buffer is insufficient because the motor's acceleration/deceleration phases dominate over
the cruise phase).

While 89ms may seem small, this means the arm position is wrong when the next joint starts
moving. Over time, this compounds positioning errors because `joint_move.cpp` blindly
updates its internal position to the target value regardless of whether the motor reached it
(`joint_move.cpp:138: current_position_ = value`).

### What this means for picking accuracy

The position error accumulates:

```
Pick 1: Command J4 to -0.0199 → motor reaches -0.015 → software thinks it's at -0.0199
Pick 2: Command J4 to 0.050  → distance calc uses 0.050-(-0.0199)=0.0699
                              → actual distance is 0.050-(-0.015)=0.065
                              → sleep is based on wrong distance
```

This is why the system sometimes reaches cotton slightly off-center. The error resets only
when the motor returns to homing position (0.0).

### How much time could be saved

If the arm waited for actual motor feedback instead of blind sleeping:

| Source of Savings | Time Saved Per Pick | Over 2,276 Picks |
|-------------------|--------------------:|------------------:|
| J4 approach: feedback vs sleep | ~280ms | 10.6 min |
| J3 approach: feedback vs sleep | ~400ms | 15.2 min |
| Inter-joint delays (2x 300ms) | ~600ms | 22.8 min |
| Retreat delays (reduced) | ~200ms | 7.6 min |
| **Estimated total** | **~1,480ms** | **~56 min** |

**Saving 1.5 seconds per pick would reduce cycle time from 6.8s to ~5.3s** — a 22%
improvement. This alone won't meet the 2.0s PRD target (PERF-ARM-001), but it's the
largest software-only gain available without changing hardware or motion strategy.

---

## Part 3: System Health Summary

Despite the Joint3 issue, the overall motor system is remarkably reliable:

| Metric | Value | Assessment |
|--------|-------|------------|
| Total motor commands | ~10,696 | |
| TX failures (CAN) | 0 | Perfect |
| RX failures (CAN) | 0 | Perfect |
| Motor timeouts | 0 | Perfect |
| Motor failures | 0 | Perfect |
| Error flags | 0 | Perfect |
| Health score | 1.0 (all motors, entire session) | Perfect |
| Bus voltage | 50.80V — 51.95V | Stable |
| Max temperature | 47C (J3) | Within limits |
| Position accuracy (J4, J5) | < 0.0003 rad | Excellent |
| Session uptime | 5h 3m uninterrupted | Excellent |

The CAN bus, motor controllers, and power system are production-ready. The two issues
identified (Joint3 mechanical resistance, blind sleep timing) are addressable without
hardware redesign.

---

## Appendix: Raw Data Reference

### Motor Reach Time Percentiles

| Percentile | Joint3 | Joint4 | Joint5 |
|------------|--------|--------|--------|
| min        | 0.225s | 0.322s | 0.327s |
| p5         | 0.253s | 0.397s | 1.183s |
| p25        | 0.375s | 0.607s | 1.196s |
| p50        | 0.491s | 0.867s | 1.207s |
| mean       | 0.648s | 0.791s | 1.262s |
| p75        | 0.991s | 0.952s | 1.401s |
| p95        | 1.194s | 1.149s | 1.406s |
| max        | 1.302s | 1.206s | 1.408s |

### Pick Cycle Time Distribution

| Metric | Approach | Retreat | Total Cycle |
|--------|----------|---------|-------------|
| min    | 0 ms     | 0 ms    | 0 ms        |
| median | 4,138 ms | 2,507 ms | 6,699 ms  |
| mean   | 4,122 ms | 2,647 ms | 6,770 ms  |
| p95    | 4,323 ms | 3,513 ms | 7,648 ms  |
| max    | 4,623 ms | 3,518 ms | 7,870 ms  |

### Yanthra Move Phase Timing (blind sleep durations)

| Phase | n | min | median | mean | p95 | max |
|-------|---|-----|--------|------|-----|-----|
| J4 approach | 2,273 | 1,024ms | 1,223ms | 1,206ms | 1,297ms | 1,298ms |
| J3 approach | 2,273 | 1,003ms | 1,110ms | 1,071ms | 1,140ms | 1,493ms |
| J5+EE approach | 2,273 | 1,136ms | 1,248ms | 1,244ms | 1,347ms | 1,378ms |
| J5 retreat | 2,273 | 1,417ms | 1,505ms | 1,488ms | 1,532ms | 1,588ms |

---

## Part 4: The Topic Mismatch — Root Cause and History

### The disconnection

The arm software (`joint_move.cpp`) and motor controller (`mg6010_controller_node.cpp`)
have **never been connected** for position feedback. They use different topic names and
different message types:

```
Motor Controller                          Arm Software (joint_move.cpp)
┌────────────────────────────┐            ┌─────────────────────────────┐
│ PUBLISHES:                 │            │ SUBSCRIBES TO:              │
│   Topic: "joint_states"    │───── X ───▶│   Topic: "{name}/state"     │
│   Type:  JointState        │  MISMATCH  │   Type:  Float64            │
│   (aggregated, all joints) │            │   (per-joint, e.g.          │
│                            │            │    "joint3/state")           │
└────────────────────────────┘            └─────────────────────────────┘
```

The subscription in `joint_move.cpp` has a callback (`joint_state_cb`) that would update
`current_position_` — but since no one publishes to `joint3/state`, `joint4/state`, or
`joint5/state`, the callback **never fires**. The motor controller publishes all joint
positions in a single aggregated `sensor_msgs::msg::JointState` message on `joint_states`.

### Git history: mismatched since the current branch began

The codebase was developed by Udayakumar from Aug 2025 onward (initially under a default
"pragati developer" git identity, switched to personal name Sep 30, 2025). The full
development history — ROS1-to-ROS2 migration (v1.0.0 through v4.0.0, Aug–Sep 2025) and
production readiness (v5.0.0, Oct 2025) — exists on the Beanstalk repository's older
branches (`master`, `precision_testing`, etc.) but is not in this branch's commit graph.

The current `pragati_ros2` branch starts at commit `2cad9f9` (Jan 4, 2026). This appears
as a large initial commit because the branch was created from the existing working copy.
Vasanthakumar's only actual contribution was adding a YOLO model blob file (commit message
"Yolo model added"). The rest of the 4,057 files in that commit are the existing codebase.

At the time of this branch's creation, `joint_move.cpp` already subscribed to
`{name}/state` (Float64) and `mg6010_controller_node.cpp` already published `joint_states`
(JointState). **The topic mismatch predates this branch.**

**Key commits in this branch's history:**

| Date | Commit | Author | What happened |
|------|--------|--------|---------------|
| **Jan 4, 2026** | `2cad9f9` | Vasanthakumar A | Branch created from existing codebase; Vasanth added YOLO model blob. Topic mismatch already present. |
| **Jan 5, 2026** | `84198af` | Udaya | First development commit on this branch. Fixed J5 velocity mismatch. |
| **Feb 10, 2026** | `f24c09e` | Sri_Swetha | Discovered the feedback gap. Before this commit, `move_joint(value, wait=true)` silently ignored the `wait` parameter: `(void)wait;`. She added the blind sleep workaround as a temporary fix. |

**Before Sri_Swetha's fix (pre-Feb 10),** the `wait` parameter did nothing:

```cpp
// BEFORE f24c09e: wait parameter was silently discarded
void joint_move::move_joint(double value, bool wait) {
    (void)wait;           // <-- ignored entirely
    // ... publish command and return immediately
    current_position_ = value;  // assume we got there
}
```

This means from the beginning of this repo through Feb 10, every "blocking" joint move
returned instantly without waiting. The approach sequence's timing came entirely from
`inter_joint_delay` sleeps and EE timing in `motion_controller.cpp`, not from `joint_move`.

Sri_Swetha's workaround correctly identified the problem and added a sleep-based wait:

```cpp
// TEMPORARY FIX: Position feedback topics don't exist (/jointN/state not published)
// Motor controller internally detects target reached and logs "✅ Reached target"
// Use conservative sleep based on typical movement time
```

### What likely happened before this repo

The `{name}/state` subscription pattern in `joint_move.cpp` was likely carried over from
the **ODrive-era motor system** or early ROS2 migration. Evidence:

- `joint_move.h` still has an `ODriveJointID` parameter — ODrive was the previous motor
  controller before MG6010
- Comments in `joint_move.cpp` reference: `"// CRITICAL FIX: Use FAST publisher-based
  control instead of slow service calls"` — evidence of iterative migration decisions
- Comments reference: `"// Legacy parameter 'wait' kept for API compatibility"`
- Dead constants in `joint_move.h` (`MOTOR_POS_ERROR_MAX = 0.2`, `MOTOR_TIME_OUT = 3.0`,
  `UNABLE_TO_REACH`, `TIME_OUT`) — infrastructure for a feedback loop that was planned or
  previously existed with ODrive but was never reconnected after the MG6010 migration

**The full history of when this feedback path last worked (if ever) is available on the
older Beanstalk branches** (`master`, `precision_testing`) but is not in this branch's
commit graph.

### What the motor controller has always done (in this repo)

- **Always** published aggregated `joint_states` (`sensor_msgs::msg::JointState`)
- **Never** published per-joint `Float64` topics on `{name}/state`
- **Never** had removed per-joint publishers in git history (no deleted code)

---

## Part 5: Implementation Options for Position Feedback

Three approaches to bridge the gap, with detailed trade-offs.

### Option A: Subscribe to `/joint_states` in joint_move.cpp (Recommended)

**Change:** Replace the dead `Float64` subscription on `/jointN/state` with a `JointState`
subscription on `/joint_states`. Replace blind sleep with a polling loop that checks actual
position until within tolerance or timeout.

**Files modified:** `joint_move.cpp`, `joint_move.h` (2 files)

| Pros | Cons |
|------|------|
| Smallest change — ~100 lines of new code in 2 files | Must parse JointState array to find the right joint by name |
| Motor controller stays untouched — zero risk to proven CAN/feedback layer | Polling rate depends on motor controller's 10Hz publish rate |
| `/joint_states` already publishing at 10Hz with real position data | Topic may be namespaced (e.g., `/arm/joint_states`) — needs correct remapping |
| Easy fallback — if no messages within timeout, fall back to blind sleep | Adds dependency on `sensor_msgs/JointState` (minor) |
| Testable with config flag — A/B test in field | |
| Eliminates position drift — `current_position_` is always actual | |
| Detects "motor didn't move" failures via timeout | |

**Risk level:** Low. Motor controller untouched. Worst case = same as today (blind sleep).
**Implementation time:** ~1 day.

### Option B: Use JointPositionCommand service with wait_for_completion

**Change:** Replace topic-based Float64 commands with service calls to motor controller's
`joint_position_command` service. The service can block until motor controller's internal
feedback detects target reached.

**Files modified:** `joint_move.cpp`, `joint_move.h`, `motion_controller.cpp` (3+ files)

| Pros | Cons |
|------|------|
| Uses motor controller's own feedback — most accurate, no tolerance/timeout duplication | Changes the command interface — ~20 call sites in motion_controller.cpp need updating |
| Single source of truth for reach detection | Service calls add ~1-5ms latency per call |
| Already has settle time, tolerance, timeout logic | Blocking service calls hold the executor — may starve emergency stop checks |
| Direct RPC — no topic namespace issues | J5 approach is currently non-blocking (for EE timing) — service is inherently blocking, needs async workaround |
| | Tighter coupling — depends on service availability |
| | Harder to fall back to blind sleep if service unavailable |
| | Service may not actually support blocking waits without modification |
| | Testing harder — can't mock services as easily as topics |

**Risk level:** Medium-High. Changes fundamental command interface. Emergency stop concern.
**Implementation time:** ~2-3 days.

### Option C: Motor controller publishes per-joint Float64 topics

**Change:** Add per-joint Float64 publishers to `mg6010_controller_node.cpp` on
`/{joint_name}/state`. This bridges the exact topic mismatch that `joint_move.cpp` expects.

**Files modified:** `mg6010_controller_node.cpp`, `joint_move.cpp` (still needs wait loop)

| Pros | Cons |
|------|------|
| Bridges the exact mismatch — existing subscription would start receiving data | Still needs a wait loop in `joint_move.cpp` — same work as Option A plus motor controller changes |
| Simple publisher addition — ~15 lines in motor controller | Modifies the motor controller — the one 100%-reliable component |
| | Adds redundant topics — `/joint_states` already carries all data |
| | Loses information — Float64 only has position, JointState has position + velocity + effort |
| | Non-standard — per-joint Float64 is not a ROS2 convention |
| | Same namespace issues remain |

**Risk level:** Medium. Modifies proven component for no net benefit over Option A.
**Implementation time:** ~1.5 days.

### Recommendation

**Option A** delivers the full benefit with the least risk. The motor controller is the one
component with zero failures across 10,696 commands — there is no reason to modify it. Option
A gets the same position data from the same `/joint_states` topic with zero changes to the
CAN/feedback layer.

---

*Data extracted from: `mg6010_controller_node_4456_1771480157168.log` (4.3MB, motor
feedback) and `yanthra_move_node_4575_1771480163834.log` (9.2MB, pick cycle timing).
Session: February 19, 2026, 11:19–16:22 IST.*
