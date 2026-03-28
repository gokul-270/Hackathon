# April Field Visit Preparation Plan — Gap Analysis & Realistic Assessment

**Created:** March 27, 2026
**Requested by:** Manohar (Project Owner)
**Prepared by:** Udayakumar (Execution Lead)
**Target Date:** Late April 2026 (25th-30th)
**Available Time:** ~4 weeks from today
**Team Size:** 13 people (see Team Composition below)

---

## Executive Summary

Manohar's April field visit targets represent a **product-level demonstration** across 7
workstreams: Simulation, Robotic Arm, End Effector, Cotton Transport, Vehicle Design,
Vehicle Autonomy, and Integrated Field Operation. The existing April Field Trial Plan
(APRIL_FIELD_TRIAL_PLAN_2026.md) targets a **focused engineering refinement** — 2 arms,
single row, >70% pick success rate.

The gap between these two scopes is substantial. This document provides an honest assessment
of what is achievable, what is a stretch, and what requires post-April timelines. It then
proposes a prioritized plan that maximizes demonstrable progress across all 7 workstreams
within the 4-week window.

### Current State Snapshot (March 27, 2026)

| Metric | Value |
|--------|-------|
| Pick success rate | 52.9% (March 25 trial) |
| Arms validated in field | 2 (arm_1, arm_2) |
| Arms in existence | 2 built, components for 5 more ordered (target: 5 total first) |
| Vehicle crashes | 0 (March 25 — eliminated) |
| Autonomy stack | RTK GPS hardware available. Arvind has done field runs + data capture + presentation. Zero ROS2/Nav2 integration code in repo. |
| Cotton transport | M2 roller motor ejects cotton at home position. Cotton drops into collection box. No further conveyance. |
| Simulation | Separate arm + vehicle Gazebo models. Vehicle sim with web dashboard working (port 8888). Configurable field generator exists. Vasanth's 3-arm + vehicle sim committed to repo (11 commits, `cbf78c3c7`). New `vehicle_arm_sim` package with merged URDF, web editor, testing UI. Code review identified 12 critical issues (security, URDF errors, no tests, 82 MB binary assets without git-lfs). |
| Pick cycle time (actual, median) | 4.5 - 5.1 seconds per successful pick |
| Pick cycle time (PRD target) | 2.0 seconds per pick |
| Reliability testing done | ~930 picks (single trial). No long-duration reliability test. |

### Progress Trajectory

| Trial | Date | Pick Rate | Arms | Key Milestone |
|-------|------|-----------|------|---------------|
| January | Jan 7-8 | 21.8% | 1 | First field trial |
| February | Feb 26 | 26.7% | 1 | MG6010 motors, single arm |
| March | Mar 25 | 52.9% | 2 | Two-arm, zero vehicle crashes |
| April target (existing plan) | Late Apr | >70% | 2 | Reachability + model + reliability |
| April target (Manohar's vision) | Late Apr | 80% | 6 | Full system + autonomy + transport |

### Key Correction: Arm Build Status

Components for 5 arms have been ordered. Current plan is to build 3 new arms first
(5 total), with 2 arms facing each side of a cotton row (4 active, 1 for testing/spare).
Physical arrangement: 2 arms face one row side, 2 arms face the other side.

**Vehicle + arm configuration:**
- 3 arms on vehicle: can be done without major changes if components available
- 4 arms on vehicle: requires frame adjustments and mounting modifications
- Arm assembly: Dhinesh is sole owner

**Component shipment tracking is needed** — see Appendix B for tracking template.

---

## Section 1: Manohar's Targets vs Reality — Column-by-Column Assessment

### 1.1 Simulation

| # | Manohar's Target | Current State | Feasibility by Late April |
|---|-----------------|---------------|--------------------------|
| SIM-1 | 6 Arm + Vehicle executable model in Gazebo (or ISAAC SIM) | 3-arm + vehicle simulation COMMITTED to repo (`cbf78c3c7`). New `vehicle_arm_sim` package with merged URDF (1819 lines), Gazebo launch, web-based URDF editor, 3-arm testing UI. Code review found: swapped steering topics (left↔right), duplicate link name in arm_top.urdf, no tests, 82 MB binary assets without git-lfs. 4-arm requires URDF extension + frame adjustments. | ACHIEVABLE for 3-arm model — committed and launchable after fixing URDF errors (steering swap, duplicate link). 4-arm extension needs 1-2 weeks. |
| SIM-2 | Simulation of vehicle in a single row | Vehicle Gazebo model exists with cotton field worlds (`cotton_field_with_plants.sdf`). 3 cotton plant models (small/medium/tall). Vehicle movement simulation with web dashboard integration EXISTS (port 8888, rosbridge 9090, virtual joystick, 14 movement patterns, sensor telemetry). New additions: RTK GPS simulator node (proper WGS-84 math, convergence state machine), EKF sensor fusion engine, front camera cotton detector (HSV, API-compatible with production), path corrector, simulation field editor UI. Code review found: backend has command injection vulnerability in subprocess calls, binds 0.0.0.0 with no auth. | ACHIEVABLE — vehicle-in-row simulation functional. RTK GPS sim and EKF add value for autonomy testing. Security fixes needed before field deployment. 2-3 days of integration + fixes. |
| SIM-3 | Basic plant model in field with variation in row spacing | Configurable row spacing and field configuration ALREADY EXISTS via `generate_cotton_field.py` (row spacing default 1.80m, plant spacing 0.70m, randomized variants, heightmap terrain). 3 plant model sizes available. | ACHIEVABLE — existing infrastructure covers this. Fine-tuning parameters and adding more plant variants. 1-2 days. |

**What Already Works (Simulation):**
- Vehicle Gazebo model (3-wheeled, velocity + Ackermann kinematics, 9 CAD meshes)
- 3-arm + vehicle merged URDF with Gazebo launch (committed, needs URDF fixes)
- RTK GPS simulator with convergence state machine (SEARCHING → NO_FIX → FLOAT → RTK_FIXED)
- EKF sensor fusion engine (6-state, Joseph form, fuses odom + IMU + GPS)
- Front camera cotton detector (HSV, API-compatible with production pipeline)
- Cotton field world generator with configurable row/plant spacing
- Simulation web UI (port 8888) with joystick, movement patterns, sensor display, recording
- Interactive URDF editor with 3D viewer (Three.js) and Gazebo sync
- 3-arm testing UI with cosine test sequence
- Main web dashboard (port 8090) with fleet management, MQTT bridge
- NavSat/GPS sensor in simulation (10Hz, Gazebo bridge to ROS2)
- AI-generated cotton plant meshes and soil terrain models

**Key Blockers (Updated After Code Review):**
- ~~Vasanth's 3-arm + vehicle simulation is NOT in the repo~~ — RESOLVED. Committed as `cbf78c3c7`.
- **URDF has swapped steering topics** — right wheel publishes to left topic and vice versa. Breaks driving.
- **Duplicate link name** in `arm_top.urdf` (`colle.box-holding-v1` appears twice) — invalid URDF.
- **J5 cosine fix was reverted** in latest commit — testing UI sends unclamped, incorrectly-computed joint values. Production C++ code is unaffected.
- **Security: all web UIs bind 0.0.0.0 with zero auth** — editor, testing UI, and vehicle backend. Path traversal vulnerability in mesh serving endpoint. Command injection in subprocess calls.
- **82 MB of binary meshes committed without git-lfs** — includes ~24.6 MB of exact duplicates across packages. Repo clone size inflated.
- **Zero tests** across all 11 commits — violates project TDD policy.
- **No OpenSpec change artifacts** — feature of this magnitude should have gone through structured workflow.
- **Pre-commit/pre-push hooks not installed** on Vasanth's machine — root file violations and large files were not caught.
- 3-arm on vehicle: works as-is if physical components are available (no major changes).
- 4-arm on vehicle: requires frame adjustments, mounting point changes, and possibly
  collision avoidance geometry updates.
- Physical arm layout decided: 2 arms per side of cotton row, 4 arms total on vehicle.
  This determines URDF arm placement geometry.

**Isaac Sim Migration Assessment:**

Dev team works on laptops (no NVIDIA GPU, but more capable than RPi). Current plan is
to continue with Gazebo through April.

| Factor | Gazebo (Current) | Isaac Sim |
|--------|-----------------|-----------|
| **GPU requirement** | None (CPU rendering OK) | NVIDIA GPU with CUDA mandatory (RTX 3070+ recommended) |
| **Dev hardware** | Runs on team laptops now | Team laptops lack NVIDIA GPUs — would need new hardware or cloud instances |
| **Migration effort** | N/A | Rewrite URDF→USD, recreate worlds, new sensor plugins, new physics config. Estimated 3-6 weeks. |
| **ROS2 integration** | Native (ros_gz bridge) | Supported via Isaac ROS bridge, but different API surface |
| **Cotton field assets** | Existing (3 plant models, field generator) | Must recreate or convert all assets to USD format |
| **Sim fidelity** | Adequate for motion planning, sensor testing | Better physics, photorealistic rendering, synthetic data generation |
| **When to migrate** | N/A | Post-April. Evaluate when NVIDIA hardware is available and sim fidelity becomes a bottleneck. |

**Verdict:** Gazebo stays for April. Isaac Sim migration is a 3-6 week project that requires
NVIDIA hardware the team doesn't have. Evaluate post-April when autonomy work matures and
high-fidelity synthetic data (for ML training) becomes a priority.

**Immediate Action:**
- ~~Vasanth must commit ALL simulation work to a branch TODAY~~ — DONE (`cbf78c3c7`).
- Fix URDF steering topic swap (swapped left↔right) — blocks basic driving test.
- Fix duplicate link name in arm_top.urdf — blocks URDF validation.
- Restore J5 cosine fix (reverted in latest commit) — testing UI sends wrong values.
- Set up git-lfs for mesh/texture files, deduplicate 24.6 MB of exact copies.
- Install pre-commit/pre-push hooks on Vasanth's dev machine.
- Bind web UIs to 127.0.0.1, sanitize subprocess inputs (security).
- Add basic tests (URDF validation, launch smoke test, joint limit boundary).
- Convert copy-paste 3-arm URDF to xacro macro for maintainability.
- Merge vehicle + arm URDF into a single model with 4 arm mount points.

**Recommended April Scope:**
- ~~Commit existing 3-arm + vehicle Gazebo model to repo (DAY 1)~~ — DONE
- Fix URDF critical issues: steering swap, duplicate link, restore J5 cosine fix (DAY 1-2)
- Security hardening: localhost binding, input sanitization (WEEK 1)
- Git-lfs setup + mesh deduplication (WEEK 1)
- Fine-tune existing vehicle-in-row simulation with web dashboard
- Extend from 3-arm to 4-arm model (convert to xacro macro)
- Verify and extend configurable plant/row spacing parameters
- Add basic tests (URDF parse, launch smoke, joint limits)

**Owner:** Vasanth + Navaneeth (simulation)

---

### 1.2 Robotic Arm

| # | Manohar's Target | Current State | Feasibility by Late April |
|---|-----------------|---------------|--------------------------|
| ARM-1 | Production-worthy arm | 2 arms built, 3 more being built (5 total target). MG6010 motors validated. Belt-driven J5. | See "Production-Worthy Arm Definition" below. |
| ARM-2 | 10,000 arm movements in 10 hours | ~930 pick attempts in 6-hour field trial. Lab testing has not run 10K continuous cycles. | See "Pick Cycle Target Analysis" below — tiered targets: 6K realistic, 8K stretch, 10K aspirational. |
| ARM-3 | 60 x 10,000 movement testing (reliability) | Zero long-duration reliability testing done. Max single test was ~930 picks. No test fixture, no automated test harness. Intent: 60 days continuous at 10K/day = 600K total movements for MTBF validation. | NOT READY TO START — we haven't done even a single 6K/10hr test yet. Must first achieve the 6K target (ARM-2) before starting reliability testing. April goal: achieve first 6K test, understand failure modes. 60-day test is a post-April milestone. |

#### Pick Cycle Target Analysis (Tiered: 6K / 8K / 10K)

| Tier | Target | Picks/10hr | Cycle Time Required | Assessment |
|------|--------|-----------|-------------------|------------|
| **REALISTIC (minimum)** | 6,000 | 6K | **6.0 seconds** | Achievable at CURRENT speed (6.1s avg). Minor tuning only. |
| **STRETCH** | 8,000 | 8K | **4.5 seconds** | Requires joint parallelization + delay reduction. |
| **ASPIRATIONAL** | 10,000 | 10K | **3.6 seconds** | Requires all optimizations + motor speed increase. |

| Metric | Value |
|--------|-------|
| Current actual (median, field) | **4.5 - 5.1 seconds** per successful pick |
| Current actual (average, field) | **~6.1 seconds** per successful pick |
| PRD target (PERF-ARM-001) | **2.0 seconds** per pick |
| April trial plan target | <5.0 seconds |

**At current speed (6.1s avg), 10 hours yields ~5,900 picks — just under the 6K minimum.**
The 6K realistic target is achievable with minimal optimization (reducing average from
6.1s to 6.0s). The stretch and aspirational targets require progressively more work.

Main time sinks and reduction opportunities:

| Phase | Current Time | Optimization | Potential Savings |
|-------|-------------|-------------|-------------------|
| Approach (J4→J3→J5 sequential) | ~1,650ms | Parallelize J3+J5 | 400-600ms |
| inter_joint_delay | 300ms | Reduce to 150ms with position feedback | 150ms |
| J5 hardcoded sleep | 200ms | Replace with position feedback | 100-200ms |
| ee_post_joint5_delay | 300ms | Reduce to 150ms | 150ms |
| Retreat (home return) | ~1,700ms | Faster motor velocity, parallel joints | 400-600ms |
| 7-pos J4 scanning overhead | ~2,100ms/cycle | Reduce to 5-pos, skip low-yield positions | 600ms |
| M2 eject duration | 300ms reverse + 200ms forward | Reduce if cotton clears faster | 100-200ms |
| **Total potential savings** | | | **2,000-2,500ms** |

**Optimized cycle time estimate: 3.5 - 4.0 seconds per pick.**

| Tier | Optimization Required | Effort | 10hr Yield |
|------|----------------------|--------|-----------|
| 6K REALISTIC | Minimal tuning (reduce outlier cycles) | 1-2 days | ~6,000-6,500 |
| 8K STRETCH | Joint parallelization + delay reduction | 3-5 days | ~8,000-9,000 |
| 10K ASPIRATIONAL | All above + motor speed + scan reduction | 5-7 days | ~9,000-10,300 |

**Recommendation:** Set 6K as the pass/fail bar for April. Anything above is bonus.
Track actual cycle time daily during lab testing and report the tier achieved.

#### 60-Day Reliability Test (ARM-3)

**We are NOT ready for the 60-day test.** We haven't completed even a single 6K/10hr
continuous test yet. The 60-day test requires first proving we can sustain 6K+ picks in
a single 10-hour session, understanding failure modes, and having a test fixture (EE-1).

Prerequisites before 60-day test can start:
1. Achieve 6K picks in 10 hours (ARM-2) — FIRST
2. EE test fixture built and validated (EE-1)
3. Understand and fix failure modes from first 6K test
4. Automated test harness (start/stop/log without human intervention)

The 60x10K target means 60 days of continuous operation at 10K picks/day to validate
that the arm can operate for 60 days without failure. This is an MTBF validation target.
(Note: with 6K realistic target, 60x6K = 360K total movements is the minimum bar.)

| Metric | Value (at 6K) | Value (at 10K) |
|--------|---------------|----------------|
| Total movements required | 360,000 | 600,000 |
| At 6.0s/pick | 600 hrs = 25 days (24/7) | N/A |
| At 3.6s/pick | N/A | 600 hrs = 25 days (24/7) |
| At 10hrs/day operation | 60 calendar days | 60 calendar days |
| Arms available for testing | 1-2 (others needed for field trial) |
| **Earliest completion** | **Late June 2026** (if started April 1) |

**April deliverable:** Achieve first 6K/10hr continuous test. Report failure modes and
first MTBF estimate. Do NOT start 60-day test until 6K/10hr is proven reliable.
60-day test is a June-July milestone.

#### Production-Worthy Arm — Parameters to Define

"Production-worthy" is currently undefined. Below are the **parameters** that must be
specified. Values are TBD — fill in after measurement, testing, and Manohar's review.

| # | Parameter | Unit | Current Measured | Suggested Target | How to Measure | Notes |
|---|-----------|------|-----------------|-----------------|---------------|-------|
| P1 | **Repeatability** | mm | Not measured | ±2mm | Repeated moves to same target, measure deviation | Determines pick consistency |
| P2 | **Cycle time** (sustained) | seconds/pick | 4.5-6.1s (field) | <6.0s (6K tier) | Average over 1000+ picks | 6.0s = 6K/10hr, 3.6s = 10K/10hr |
| P3 | **MTBF** (mean time between failures) | cycles | ~930 (max tested) | >10,000 | Run until failure, record count | What counts as "failure"? Define. |
| P4 | **Thermal** (motor temp at steady state) | °C | Not measured | <60°C | Thermocouple on motor housing after N hours | MG6010 max rated temp? |
| P5 | **Belt life** (J5 timing belt) | cycles | ~2500 est. (replaced in Feb) | >50,000 | Run until belt failure | Known wear item |
| P6 | **Weight** (complete arm assembly) | kg | Not measured | <5 kg | Weigh assembled arm | Affects vehicle payload |
| P7 | **Ingress protection** | IP rating | None (open electronics) | IP54 | Visual inspection + spray test | Field = dust + dew |
| P8 | **Connector type** | — | Mixed (soldered + crimped) | Tool-free maintenance | Standardize across arms | Field serviceability |
| P9 | **Assembly time** (parts → operational) | hours | Not measured | <2 hours | Time next arm build (arm_3) | Manufacturing scalability |
| P10 | **BOM completeness** | % documented | ~70% (informal) | 100% | Audit parts list | Reproducible builds |
| P11 | **QA acceptance test** | pass/fail checklist | Does not exist | Defined checklist | Create test procedure | Every arm passes before field |
| P12 | **EE pick success rate** (in fixture) | % | 52.9% (field, mixed) | >80% | Controlled fixture test (EE-1) | Isolate EE from reachability |
| P13 | **Motor stall current threshold** | A | 2.5A (config) | TBD (per motor characterization) | Characterize per motor | Safety + reliability |
| P14 | **CAN error rate** (per arm) | errors/hour | High (1.59M in session) | <100/hour | Monitor over 1hr operation | Reliability indicator |
| P15 | **Power consumption** (per arm, steady state) | W | Not measured (see POWER_BUDGET_ANALYSIS.md) | TBD | Ammeter on arm power supply | Battery sizing for multi-arm |

**Action items:**
1. Measure current values for all parameters during lab testing (Week 2-3)
2. Propose target values based on measurements + operational requirements
3. Present measured vs proposed to Manohar for sign-off
4. Parameters P1-P5, P12-P14 are measurable in lab now
5. Parameters P6-P11, P15 need structured testing/documentation effort

**Key Blockers:**
- Components for 5 arms ordered but shipment status unknown. Need tracking.
- Belt wear is the known mechanical weak point (J5 belt replaced during Feb trial). 10K
  cycles may expose belt failure. Need spare belts.
- Only 2 arms exist. Building 3 more requires assembly time (Dhinesh/Joel/Rajesh).
- Cycle time optimization is software work that can start immediately.

**Recommended April Scope:**
- Build 3 new arms (target: 5 total). Start assembly as soon as parts arrive.
- Run 1,000-cycle continuous lab test on existing 2 arms while building new ones.
- Implement cycle time optimizations (joint parallelization, delay reduction).
- Start 10K/10hr test once cycle time is <4.0s. Report results.
- Begin 60-day reliability test (runs into May-June).
- Present proposed "production-worthy" spec to Manohar for sign-off.

**Owner:** Gokul (lab testing + cycle time), Dhinesh/Joel/Rajesh (arm assembly),
Udayakumar (cycle time software optimization)

---

### 1.3 End Effector

| # | Manohar's Target | Current State | Feasibility by Late April |
|---|-----------------|---------------|--------------------------|
| EE-1 | Fixture for automatic testing of end effector | No test fixture exists. Testing is manual on cotton in field. | ACHIEVABLE — mechanical fixture design + fabrication. Needs cotton analog or real cotton samples. 1-2 weeks. |
| EE-2 | 10,000 picks testing (reliability test) | ~492 successful picks max (March trial). No automated pick testing. | STRETCH — depends on EE-1 fixture. If fixture ready by week 2, can run 10K picks in remaining 2 weeks (~7 picks/min = ~24 hours continuous). |
| EE-3 | 60 x 10,000 picking testing (reliability) | Zero. Intent: 60 days x 10K picks/day = 600K total for EE MTBF. | NOT ACHIEVABLE by April — same timeline as ARM-3. 60 days of testing = late June earliest. April deliverable: start the test, report first MTBF data. |

**Key Blockers:**
- EE roller seed jamming issue (GAP-EE-007) — cotton seeds getting stuck, pin size ~13mm.
  Must be resolved before any reliability test is meaningful.
- No suction/pressure feedback — picks are time-based only. Can't distinguish "picked
  cotton" from "missed" without visual inspection in lab.
- Fixture design is mechanical engineering (Dhinesh/Joel).

**Recommended April Scope:**
- Design and build basic EE test fixture (static cotton target, repeatable positioning)
- Resolve roller jamming issue (Joel/Dhinesh)
- Run 1,000-pick reliability test using fixture
- Document failure modes, pick success rate, and time-to-failure

**Owner:** Joel (fixture design), Dhinesh (fabrication), Gokul (test execution)

---

### 1.4 Cotton Transport

| # | Manohar's Target | Current State | Feasibility by Late April |
|---|-----------------|---------------|--------------------------|
| CT-1 | Mechanism to transport cotton to final collection unit | M2 roller motor ejects cotton at home position via reverse belt operation (300ms reverse + 200ms forward flush). Cotton drops into collection box below/beside arm. No automated conveyance beyond the drop point. M2 roller + gravity is the eject method (no pneumatic/compressor). | ACHIEVABLE for design — transport mechanism design can be completed by April. Fabrication is a stretch depending on Dhinesh's bandwidth. |
| CT-2 | Testing for 2 arm | Zero transport testing (only drop test). | ACHIEVABLE — if CT-1 mechanism exists. Run 2-arm pick-and-transport cycle in lab. |
| CT-3 | Testing for 6 arm | Only 2 arms exist. | NOT ACHIEVABLE — requires 6 physical arms + transport mechanism. |

**Key Blockers:**
- Need to define: Where does cotton go after the collection box? Gravity chute to central
  bin? Conveyor belt? Each option has different complexity, cost, and timeline.
- Collection box overshoot/undershoot issues documented in Feb trial — arm trajectory
  tuning may be needed when transport mechanism changes the drop target.
- Software side is simple: ROS2 service to trigger transport, sensor to detect bin-full.

**Current Cotton Flow:**
```
M1 picks cotton → Arm retreats to home → J3 tilts to eject position (-0.180 rot)
→ M2 runs REVERSE 300ms (belt ejects cotton) → M2 runs FORWARD 200ms (flush residual)
→ Cotton falls into collection box (gravity + trajectory)
```
No pneumatic/compressor mechanism exists. Only M2 roller + gravity.

**Recommended April Scope:**
- Design transport mechanism from collection box to central bin (gravity chute or simple
  conveyor — simplest option that works for 4-arm layout)
- Fabricate and mount on vehicle for 2-arm configuration (if time permits)
- Run 2-arm pick-transport cycle test
- Document transport mechanism design for scaling to 4+ arms

**Owner:** Dhinesh (mechanical design + fabrication), Amirtha (collection system).
Note: Nadimuthu is NOT ACTIVE — remove from task assignments. Dhinesh absorbs his work.

---

### 1.5 Vehicle Design

| # | Manohar's Target | Current State | Feasibility by Late April |
|---|-----------------|---------------|--------------------------|
| VD-1 | Vehicle with new wheel assembly | 3-wheel with 24" wheels, ODrive drive motors, MG6010 steering. CAN RX errors (1.59M in session). | DEPENDS — is "new wheel assembly" a design change or using existing? If new: NOT ACHIEVABLE (fabrication time). If optimizing existing: ACHIEVABLE. |
| VD-2 | Electrical vehicle tested for torque/speed/steering | Vehicle drives and steers. No formal torque/speed characterization. Peak currents measured (front 17.11A). Steering angles work but accuracy unverified for 90-degree turns. | ACHIEVABLE — add instrumented test protocol. Measure torque (current draw under load), max speed, steering accuracy. 3-5 days of testing. |
| VD-3 | Vehicle running 10 hours continuous (lab testing) | Max field runtime ~6 hours (March trial). Vehicle RPi hit 83.8C thermal throttle. | STRETCH — needs thermal management fix (V3), battery capacity unknown (GAP-PWR-001 CRITICAL), CAN error rate issue. Can attempt after thermal fix. |

**Key Blockers:**
- Battery type/capacity/voltage ALL UNSPECIFIED (GAP-PWR-001/002/003 — CRITICAL). Cannot
  plan 10-hour test without knowing battery capacity.
- Vehicle payload capacity unspecified (GAP-HW-001 — CRITICAL). Adding 6 arms + transport
  mechanism changes vehicle dynamics significantly.
- Max speed unspecified (GAP-HW-004 — CRITICAL).
- "New wheel assembly" — what does this mean specifically? Different wheel size? Hub motors?
  Suspension? Need Manohar/Dhinesh to clarify.

**Recommended April Scope:**
- Characterize current vehicle: measure torque, max speed, steering accuracy, battery life
- Fix vehicle RPi thermal management (heat sink/fan — V3)
- Run 4-hour continuous lab test as stepping stone to 10-hour
- If "new wheel assembly" means specific mechanical changes, start fabrication now

**Owner:** Amirtha (vehicle design + analysis, guided by Arul), Gokul (electrical testing).

**Reference:** Power budget analysis exists at `docs/project-notes/POWER_BUDGET_ANALYSIS.md`
(March 8, 2026). New data from March 25 field trial logs available at
`collected_logs/2026-03-25-field-trial-merged/` (1.9 GB: motor currents, CAN stats,
thermal data, 6548 camera images). Power budget should be updated with this new data.

---

### 1.6 Vehicle Autonomy

| # | Manohar's Target | Current State | Feasibility by Late April |
|---|-----------------|---------------|--------------------------|
| VA-1 | RTK waypoint capture with 20mm precision | RTK GPS hardware IS AVAILABLE. Arvind has run through the field, captured GPS data, and presented results. However, ZERO ROS2 integration code exists — no GPS driver node, no Nav2, no waypoint follower in the repo. Complete flow and vehicle integration needed. | STRETCH — hardware exists (removes biggest blocker). Need ROS2 driver node, data pipeline, waypoint follower, and vehicle integration. 3-4 weeks with focused effort. 20mm precision depends on RTK correction quality. |
| VA-2 | Vehicle moving with preloaded waypoints | No waypoint navigation in production code. cmd_vel interface exists. Arvind has field GPS data but no ROS2 pipeline. | ACHIEVABLE — GPS data exists, cmd_vel works. Build ROS2 GPS node → waypoint follower → cmd_vel pipeline. 2-3 weeks. |
| VA-3 | Vehicle with plant row sensing | Zero row sensing code. No lidar. No row detection algorithm. | NOT ACHIEVABLE in 4 weeks — requires sensor selection (lidar? camera?), procurement, mounting, driver integration, row detection algorithm development, and field testing. |

**Current State (Updated):**
- **RTK GPS hardware:** AVAILABLE (not a procurement blocker)
- **Field data:** Arvind has captured GPS data during field runs and presented findings
- **What's MISSING (software integration):**
  1. ROS2 GPS driver node (publish `sensor_msgs/NavSatFix` from hardware)
  2. Nav2 / waypoint following stack (localization, path planning, waypoint follower)
  3. Data pipeline to web dashboard (GPS position visible in dashboard)
  4. Vehicle integration (mount GPS on vehicle, wire up, coordinate transforms)
  5. Systematic bag file recording of GPS data for analysis and replay

**Key Blockers:**
- **NO ROS2 INTEGRATION.** Hardware exists and data has been captured, but nothing is in
  the ROS2 pipeline. The GPS data is not flowing through ROS2 topics.
- **NO NAV2 STACK.** The robot has no navigation stack, no localization, no path planner.
  Basic waypoint following requires at minimum: odometry source, localization (EKF), and
  a waypoint follower node.
- Arvind has done preliminary field work but the software deliverables (ROS2 nodes,
  integration code) are not in the repository.

**Recommended April Scope:**
- ROS2 GPS driver node publishing NavSatFix from RTK hardware (Week 1-2)
- GPS data visible in web dashboard (Week 2)
- Mount GPS on vehicle, establish coordinate transforms (Week 2)
- Basic waypoint follower node using GPS + cmd_vel (Week 2-3)
- Record GPS bag files during field runs for analysis (Week 3-4)
- Demo: vehicle follows 3-5 preloaded waypoints in field using RTK GPS
- Stretch: Nav2 integration with localization (EKF) for smoother path following

**Owner:** Arvind (ROS2 GPS integration + waypoint following — SOLE FOCUS),
Vasanth (Nav2 support if sim work completes early)

---

### 1.7 Cotton Picker in Field (Integrated System)

| # | Manohar's Target | Current State | Feasibility by Late April |
|---|-----------------|---------------|--------------------------|
| FI-1 | Vehicle with 6 arms and transport unit | 2 arms + vehicle. No transport unit. Components for 5 arms ordered, building 3 new (5 total). Physical layout: 2 arms per side of row (4 picking + 1 test/spare). | STRETCH for 4-arm demo — depends on arm build timeline and component delivery. |
| FI-2 | Running in straight rows with automatic stop-and-go | Manual stop-and-go works. No automatic row following or stop trigger. | STRETCH — simple stop-and-go based on timer or distance (no row sensing) is achievable with basic waypoint following (VA-2). |
| FI-3 | 80% picking of all bloomed cotton in a row | 52.9% pick success rate currently. 98.4% when reachable. | STRETCH — 80% requires solving reachability (46.2% rejection) AND detection model AND border filter. Existing plan targets >70%. 80% is possible but aggressive. |

**Key Blockers:**
- 80% pick rate requires: workspace reachability improvement (currently 46.2% rejection),
  resolved detection model, border filter fix, and optimal vehicle positioning. All are in
  the existing April plan.
- Automatic stop-and-go requires some form of position sensing or cotton detection trigger.
  Simplest version: stop every N meters, scan, pick, move forward.
- 6-arm integration requires 4 more physical arms + MQTT scaling + collision avoidance
  for 6 arms + vehicle structural analysis for payload.

**Recommended April Scope:**
- Target >70% pick rate with 2 arms (existing plan — achievable)
- Implement timer-based stop-and-go: vehicle moves X meters, stops, arms pick, vehicle
  moves again. No row sensing required.
- Demonstrate 2-arm + transport (if CT-1 mechanism built) in single-row operation
- 6-arm and 80% target deferred to subsequent trial

**Owner:** All (system integration), Udayakumar (software), Dhinesh (mechanical)

---

## Section 2: Consolidated Feasibility Matrix

| Target | Feasibility | Confidence | Key Dependency |
|--------|------------|------------|----------------|
| 3-arm Gazebo model | ACHIEVABLE | 95% | COMMITTED (`cbf78c3c7`). Needs URDF fixes (steering swap, duplicate link). |
| 4-arm Gazebo model | ACHIEVABLE | 65% | Extend 3-arm model, convert to xacro macro, needs frame adjustments |
| Vehicle-in-row simulation | ACHIEVABLE | 90% | Existing sim + new RTK GPS sim + EKF. Security fixes needed. |
| Plant model with row spacing | ACHIEVABLE | 95% | Already exists via generate_cotton_field.py |
| Isaac Sim migration | NOT FOR APRIL | — | No NVIDIA GPU on team laptops. Post-April evaluation. |
| Production-worthy arm (parameters defined) | ACHIEVABLE | 85% | Measure current values, present to Manohar |
| Production-worthy arm (built) | STRETCH | 40% | Component delivery + assembly time |
| 6K arm movements / 10hr (REALISTIC) | ACHIEVABLE | 80% | Near-current speed, minimal tuning |
| 8K arm movements / 10hr (STRETCH) | STRETCH | 50% | Joint parallelization + delay reduction |
| 10K arm movements / 10hr (ASPIRATIONAL) | STRETCH | 30% | All optimizations + motor speed increase |
| 60x10K reliability (start test) | NOT READY | 10% | Must first achieve 6K/10hr before starting reliability |
| 60x10K reliability (complete) | NOT FEASIBLE | 0% | 60 days of testing — June completion |
| EE test fixture | ACHIEVABLE | 70% | Joel/Dhinesh fabrication time |
| 10K picks test | STRETCH | 40% | Fixture + roller jamming fix |
| 60x10K picks (complete) | NOT FEASIBLE | 0% | 60 days — June completion |
| Transport mechanism (design) | ACHIEVABLE | 70% | Dhinesh availability |
| Transport mechanism (fabricated) | STRETCH | 40% | Dhinesh bandwidth (overloaded) |
| Transport test (2 arm) | ACHIEVABLE | 60% | Transport mechanism exists |
| Transport test (4+ arm) | STRETCH | 30% | Arms built + transport mechanism |
| New wheel assembly | UNKNOWN | — | Clarification needed from Manohar |
| Torque/speed/steering test | ACHIEVABLE | 80% | Test protocol + instrumentation |
| 10hr continuous test | STRETCH | 30% | Battery capacity, thermal management |
| RTK GPS ROS2 integration | ACHIEVABLE | 60% | Hardware exists. Arvind builds ROS2 pipeline. |
| RTK waypoint following (vehicle) | STRETCH | 45% | GPS node + waypoint follower + vehicle integration |
| RTK 20mm precision validated | STRETCH | 35% | Full pipeline + field calibration |
| GPS data in web dashboard | ACHIEVABLE | 70% | GPS node + dashboard subscription |
| Plant row sensing | NOT FEASIBLE | 0% | No sensor, no algorithm |
| 4 arms + transport in field | STRETCH | 30% | Arm build + transport + integration |
| Auto stop-and-go (timer-based) | STRETCH | 50% | Basic waypoint following |
| 80% pick rate | STRETCH | 30% | Reachability + model + positioning |

### Summary

| Category | Count |
|----------|-------|
| ACHIEVABLE (>60% confidence) | 12 items |
| STRETCH (30-60% confidence) | 12 items |
| NOT FEASIBLE by April | 3 items |
| NOT READY (prerequisites missing) | 1 item |
| NOT FOR APRIL (deferred) | 1 item |
| UNKNOWN (needs clarification) | 1 item |

---

## Section 3: Recommended 4-Week Plan

Given the gap analysis, here is a realistic plan that maximizes demonstrable progress
across all 7 workstreams while being honest about what cannot be completed.

### Week 1 (Mar 28 - Apr 3): Critical Fixes + Arm Build Start + Sim Recovery

**All Workstreams:**

| Task | Owner | Workstream | Priority |
|------|-------|-----------|----------|
| ~~Vasanth commits ALL existing sim work to repo~~ DONE (`cbf78c3c7`) | Vasanth | Simulation | ~~CRITICAL~~ DONE |
| **Fix URDF critical issues** (steering swap, duplicate link, restore J5 cosine fix) | Vasanth | Simulation | CRITICAL — DAY 1-2 |
| **Security hardening** (bind web UIs to localhost, sanitize subprocess inputs) | Vasanth | Simulation | CRITICAL — WEEK 1 |
| **Git-lfs setup** + mesh deduplication (24.6 MB duplicates) | Vasanth | Simulation | HIGH — WEEK 1 |
| **Install pre-commit/pre-push hooks** on Vasanth's dev machine | Vasanth | Simulation | HIGH — DAY 1 |
| Arvind commits field GPS data + starts ROS2 GPS driver node | Arvind | Autonomy | CRITICAL |
| Fill in component tracking table (Appendix B) | Dhinesh/Joel | All | CRITICAL |
| Resolve detection model (A3 — team decision) | Shwetha/Arun | Field Integration | CRITICAL |
| Startup zero-position verification (A1) | Udayakumar | Arm | CRITICAL |
| Stall escalation limit (A2) | Udayakumar | Arm | CRITICAL |
| Begin arm_3 assembly (if parts received) | Dhinesh | Arm | HIGH |
| Begin EE test fixture design | Joel | End Effector | HIGH |
| Define transport mechanism design | Dhinesh | Transport | HIGH |
| Vehicle RPi thermal management (V3) | Gokul | Vehicle | HIGH |
| Start cycle time optimization (joint parallelization) | Udayakumar | Arm | HIGH |

### Week 2 (Apr 4 - Apr 10): Lab Testing + Simulation + Arm Build

| Task | Owner | Workstream | Priority |
|------|-------|-----------|----------|
| Merge vehicle + arm URDF into 4-arm model | Vasanth/Navaneeth | Simulation | HIGH |
| Vehicle-in-row Gazebo world fine-tuning | Vasanth/Navaneeth | Simulation | HIGH |
| Measure base-to-base separation D (A4) | Dhinesh/Gokul | Arm/Field | HIGH |
| Border filter margin reduction (A6) | Udayakumar | Field Integration | HIGH |
| Begin 1000-cycle arm movement test in lab | Gokul | Arm | HIGH |
| Continue cycle time optimization (delay reduction) | Udayakumar | Arm | HIGH |
| Build EE test fixture | Joel/Dhinesh | End Effector | HIGH |
| Continue arm_3, arm_4 assembly | Dhinesh | Arm | HIGH |
| Begin transport mechanism fabrication | Dhinesh | Transport | HIGH |
| IMU + GPS ROS2 integration, mount on vehicle | Arvind | Autonomy | HIGH |
| Vehicle torque/speed characterization test | Amirtha/Gokul | Vehicle | MEDIUM |
| Train/validate chosen detection model | Shwetha/Arun | Field Integration | HIGH |

### Week 3 (Apr 11 - Apr 17): Integration + Reliability + Arm Build Complete

| Task | Owner | Workstream | Priority |
|------|-------|-----------|----------|
| Complete arm_3, arm_4, arm_5 assembly | Dhinesh | Arm | HIGH |
| Run EE reliability test (target 1000+ picks) | Joel/Gokul | End Effector | HIGH |
| Attempt 6K cycle test (target: 6K picks in 10hr) | Gokul | Arm | HIGH |
| Simple waypoint follower node (GPS + cmd_vel based) | Arvind | Autonomy | HIGH |
| Timer-based auto stop-and-go implementation | Udayakumar | Field Integration | HIGH |
| Attempt 4-hour continuous vehicle test | Amirtha/Gokul | Vehicle | MEDIUM |
| 2-arm + transport mechanism integration test | Dhinesh/Gokul | Transport/Field | HIGH |
| GPS data pipeline to web dashboard | Arvind | Autonomy | HIGH |
| Pre-flight validation script (S8) | Udayakumar | Software | HIGH |
| Deploy new detection model to both arms | Shwetha | Field Integration | HIGH |
| J4 action rejection fix (A7) | Udayakumar | Arm | MEDIUM |
| checkReachability() implementation (A17) | Udayakumar | Arm | MEDIUM |

### Week 4 (Apr 18 - Apr 24): Pre-Field Validation + Demo Prep

| Task | Owner | Workstream | Priority |
|------|-------|-----------|----------|
| Full pick cycle test with all available arms (target >70%) | All | Field Integration | CRITICAL |
| RTK waypoint following demo in field | Arvind | Autonomy | HIGH |
| 4-arm Gazebo simulation demo | Vasanth/Navaneeth | Simulation | HIGH |
| Multi-arm + transport end-to-end demo in lab | All | Transport/Field | HIGH |
| Vehicle steering accuracy validation | Amirtha/Gokul | Vehicle | HIGH |
| Cross-compile and deploy to all RPis | Udayakumar | Software | CRITICAL |
| Pre-field mechanical checklist (all arms) | Dhinesh | All | CRITICAL |
| Equipment and logistics prep | Amirtha | Logistics | HIGH |
| Component tracking update (what arrived, what didn't) | Dhinesh | All | HIGH |
| 6K/10hr test report (tier achieved) | Gokul | Arm | HIGH |
| Go/no-go decision | All | All | CRITICAL |

---

## Section 4: What We Can Demonstrate by Late April

### Realistic Demo Scenario (High Confidence)

**"3-4 arm cotton picker with improved pick rate, reliability data, and simulation"**

1. **Simulation:** 3-arm + vehicle Gazebo model (committed, needs URDF fixes). Extended to 4-arm.
   Vehicle driving through cotton row with configurable plant spacing (existing
   infrastructure, fine-tuned). RTK GPS simulator and EKF sensor fusion for autonomy
   testing in sim. Isaac Sim evaluated but deferred (no NVIDIA GPU).
2. **Arm:** 5 arms built. 6K+ cycle 10hr test results. Cycle time tracked across tiers
   (6K realistic / 8K stretch / 10K aspirational). Production-worthy parameters defined
   with measured values.
3. **End Effector:** Test fixture built. 1K+ pick reliability data. Roller jamming fix
   validated.
4. **Transport:** Transport mechanism design complete. Basic gravity chute or conveyor from
   collection box to central bin. 2-arm transport cycle demonstrated.
5. **Vehicle:** Torque, speed, and steering characterization data. 4-hour continuous test
   completed. Thermal management fix validated.
6. **Autonomy:** RTK GPS integrated as ROS2 node. Waypoint following demo in field using
   RTK data. GPS visible in web dashboard. Bag files recorded for analysis.
7. **Field Integration:** 2-4 arm single-row operation with >70% pick success rate.
   Timer-based stop-and-go (vehicle moves N meters between pick stations).

### Stretch Demo (If Everything Goes Well)

Add to the above:
- 8K-10K picks in 10 hours achieved (cycle time <4.5s sustained for 8K, <3.6s for 10K)
- 4-arm simultaneous field operation
- RTK waypoint following with <50mm precision
- 80% pick rate (if reachability + model improvements land as expected)
- Auto stop-and-go with distance-based triggering

### What Cannot Be Demonstrated in April

| Item | Reason | Realistic Timeline |
|------|--------|--------------------|
| 6 arms on vehicle | Building 5 total (4 active + 1 spare) | May 2026 for 6th arm |
| 60-day reliability test COMPLETE | Started in April, runs 60 days | Late June 2026 |
| Plant row sensing | No sensor, no algorithm | Jul-Aug 2026 |
| 80% pick with 6 arms | Requires 6 arms + transport + autonomy | Sep-Oct 2026 |
| 10-hour continuous vehicle test | Battery capacity unknown | May-Jun 2026 |
| Isaac Sim migration | No NVIDIA GPU on team laptops | Post-April, when hardware available |

---

## Section 5: Team Assignments (April Focus)

| Person | April Primary Focus | Workstream | Notes |
|--------|-------------------|-----------|-------|
| **Udayakumar** | Critical software fixes (A1, A2), cycle time optimization, auto stop-and-go, pre-flight script, integration | Arm, Field, Software | Existing plan CRITICAL items + stop-and-go + cycle time |
| **Dhinesh** | Arm assembly (SOLE OWNER of arm builds), EE fine-tuning, other mechanical fine-tuning as required | Arm, End Effector | Sole owner of arm_3/4/5 assembly. Fine-tuning work as needed. |
| **Gokul** | Lab arm reliability testing, vehicle thermal fix | Arm, Vehicle | Electrical + motor testing + 6K cycle tests |
| **Joel** | EE fixture design, roller jamming fix, IO boards for new arms | End Effector, Arm | Electronics focus |
| **Rajesh** | New arm electrical assembly, E-stop wiring, power systems | Arm, Vehicle | Electrical for arm builds |
| **Shwetha** | Detection model retraining + validation | Field Integration | MUST resolve model by week 2 |
| **Arun** | Detection model support, benchmark testing | Field Integration | Support Shwetha |
| **Vasanth** | Fix URDF critical issues (steering, duplicate link, J5 cosine), security hardening, git-lfs setup, extend to 4-arm, vehicle-in-row sim fine-tuning | Simulation | ~~Commit 3-arm demo DAY 1~~ DONE. Fix critical issues from code review. Extend to 4-arm. Works with Navaneeth. |
| **Navaneeth** | Simulation support (with Vasanth) + dynamic picking analysis | Simulation, Field Integration | Dual focus: simulation work + dynamic picking research |
| **Arvind** | ROS2 GPS driver node, waypoint follower, vehicle integration, dashboard GPS, bag recording | Autonomy | SOLE FOCUS: complete RTK-to-vehicle pipeline. Hardware exists — build the software. |
| **Amirtha** | Vehicle full design and analysis (with Arul guidance), field site logistics | Vehicle, Logistics | Vehicle design lead (guided by Arul). Also logistics + equipment. |
| **Arul** | Vehicle design guidance | Vehicle | Guides Amirtha on vehicle design and analysis decisions |
| **Manohar** | Decision gates, requirement clarification, field visit coordination | All | Project owner |

**Note:** Nadimuthu is NOT ACTIVE. Vehicle design + analysis handled by Amirtha (guided
by Arul). Arm assembly is Dhinesh's sole focus. Team is effectively 12 people + Arul
(guidance role).

### Critical Clarifications Needed from Manohar

1. **"Production-worthy arm"** — Parameters defined in Section 1.2 (15 parameters, values
   TBD). Manohar to review parameter list and confirm: are these the right parameters?
   Values to be filled after lab measurement in Week 2-3.
2. **"New wheel assembly"** — Is this a specific mechanical redesign? What changes from
   current 24" wheels with ODrive? Or is it the existing assembly being tested?
3. **Component delivery timeline** — When do parts for 5 arms arrive? What has shipped?
   What's still pending? See Appendix B for tracking template.
4. **Priority ranking** — If we can only demonstrate 4 of the 7 workstreams well, which 4
   matter most for the field visit?
5. **4-arm vs 6-arm for April** — Physical plan is 4 active arms (2 per side) + 1 spare.
   Manohar's table says 6. Is 4-arm acceptable for April demo?

---

## Section 6: Relationship to Existing April Field Trial Plan

The existing APRIL_FIELD_TRIAL_PLAN_2026.md (65 tasks across 4 phases) remains the
**engineering foundation**. Manohar's targets ADD new workstreams on top:

| Existing Plan Coverage | Manohar's New Items |
|----------------------|-------------------|
| 3 CRITICAL arm/detection fixes | Simulation workstream (NEW) |
| 17 HIGH priority refinements | Transport mechanism (NEW) |
| 30 MEDIUM priority improvements | Vehicle characterization (NEW) |
| 15 LOW priority items | RTK/Autonomy stack (NEW) |
| 2-arm field trial >70% | 6-arm + 80% + auto stop-and-go (EXPANDED) |

**Recommendation:** Execute the existing plan's CRITICAL and HIGH items as-is. Layer
Manohar's new items as parallel workstreams assigned to team members who are NOT blocked
on existing critical path items.

### Items That Serve Both Plans

| Task | Existing Plan | Manohar's Target | Synergy |
|------|--------------|-----------------|---------|
| Detection model resolution (A3) | CRITICAL | 80% pick rate | Same task |
| Reachability improvement (A4) | HIGH | 80% pick rate | Same task |
| Border filter fix (A6) | HIGH | 80% pick rate | Same task |
| Vehicle thermal fix (V3) | MEDIUM | 10hr test | Same task |
| Pre-flight script (S8) | HIGH | Reliability testing | Same task |

---

## Section 7: Risk Assessment for Expanded Scope

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Team spread too thin across 7 workstreams | HIGH | HIGH | Assign clear primary focus per person. Don't context-switch. |
| R2 | RTK software integration takes longer than expected | MEDIUM | HIGH | Hardware exists but ROS2 pipeline is from-scratch. Arvind must have daily deliverables. |
| R3 | Mechanical fabrication (fixture, transport, 3 new arms) takes longer than estimated | HIGH | HIGH | Start fabrication week 1. Dhinesh is sole arm assembly owner. Joel/Rajesh support electrically. |
| R4 | 80% pick rate not achievable with current arm geometry | MEDIUM | MEDIUM | Present honest data. 70% with clear path to 80% is respectable. |
| R5 | Autonomy integration incomplete (ROS2 pipeline from scratch, Arvind's code not in repo) | HIGH | HIGH | Daily standups for autonomy. Arvind commits code daily. Escalate week 2 if no ROS2 node running. |
| R6 | Existing CRITICAL fixes (A1, A2, A3) consume all software bandwidth | MEDIUM | HIGH | These are prerequisite for field demo regardless. Cannot be deprioritized. |
| R7 | Component delivery delayed — arms can't be built | HIGH | HIGH | Track shipments daily (Appendix B). Escalate with vendor immediately. |
| R8 | ~~Vasanth's uncommitted 3-arm sim work is lost~~ | ~~MEDIUM~~ | ~~HIGH~~ | ~~RESOLVED~~ — committed as `cbf78c3c7` (11 commits, 106 files). Code review identified 12 critical issues that need fixing (URDF errors, security, no tests, 82 MB binary assets). |
| R9 | Dhinesh stretched across arm assembly + EE fine-tuning | MEDIUM | HIGH | Prioritize arm assembly. Joel/Rajesh support electrically. Vehicle design handled by Amirtha/Arul. |

---

## Section 8: Honest Bottom Line

Manohar's April targets describe a **product demonstration** — 6 arms, autonomous
navigation, cotton transport, 80% pick rate, and 60-day reliability testing. The current
system is a **validated prototype** — 2 arms, manual operation, 52.9% pick rate.

**The full scope gap is approximately 3-6 months of development**, not 4 weeks.
However, the picture is better than it first appeared:

- Components for 5 arms are ordered (build 3 new → 5 total, 4 active on vehicle)
- 3-arm + vehicle simulation committed to repo (needs URDF fixes before it's fully functional)
- Vehicle + arm URDF merging done for 3 arms; 4-arm needs adjustments
- Vehicle sim + web dashboard + configurable field already working (fine-tuning only)
- RTK GPS hardware is available; Arvind has field data and presentation (ROS2 integration needed)
- 6K picks in 10 hours IS achievable at current speed (6.0s target vs 6.1s actual)
- 8K-10K achievable with cycle time optimizations (stretch/aspirational)
- 60x10K is correctly understood as a 60-day reliability test, not a single session

What we CAN demonstrate in 4 weeks:

| Workstream | Deliverable |
|-----------|-------------|
| **Simulation** | 3-arm + vehicle Gazebo model (committed, URDF fixes applied), extended to 4-arm, vehicle-in-row with configurable spacing, RTK GPS sim + EKF for autonomy testing |
| **Arm** | 5 built arms, 6K+ cycle reliability data, production-worthy parameters measured |
| **End Effector** | Test fixture, 1K+ pick reliability data, roller jamming fix |
| **Transport** | Mechanism design, 2-arm pick-transport cycle demo |
| **Vehicle** | Torque/speed/steering characterization, 4-hour continuous test |
| **Autonomy** | RTK GPS as ROS2 node, waypoint following demo in field, GPS in dashboard |
| **Field** | 2-4 arm single-row, >70% pick rate, timer-based stop-and-go |

The 60-day reliability test and full Nav2 autonomy are multi-month efforts that START in
April but complete later. The honest framing for Manohar: "April launches all 7 workstreams
with measurable progress. 6K picks demonstrated, RTK waypoint following working, 4-arm
model simulated and built. June delivers reliability data. Full autonomous navigation
lands in July."

---

## Appendix A: Reference Documents

| Document | Location |
|----------|----------|
| Existing April Field Trial Plan | `docs/project-notes/APRIL_FIELD_TRIAL_PLAN_2026.md` |
| March 25 Field Trial Report | `docs/project-notes/FIELD_TRIAL_REPORT_MAR25_2026.md` |
| March 25 Retrospective | `docs/project-notes/FIELD_TRIAL_RETROSPECTIVE_MAR25_2026.md` |
| Power Budget Analysis | `docs/project-notes/POWER_BUDGET_ANALYSIS.md` |
| Product Requirements Document | `docs/specifications/PRODUCT_REQUIREMENTS_DOCUMENT.md` |
| Technical Specification Document | `docs/specifications/TECHNICAL_SPECIFICATION_DOCUMENT.md` |
| Gap Tracking | `docs/specifications/GAP_TRACKING.md` |
| March 25 Field Trial Logs (1.9 GB) | `collected_logs/2026-03-25-field-trial-merged/` |

---

## Appendix B: Component Tracking for 5 New Arms

**Status:** Components ordered. Shipment tracking needed.

**Action:** Fill in this table with actual order details. Update weekly.

### Per-Arm Components (x5)

| Component | Qty/Arm | Total (x5) | Ordered? | Vendor | Order Date | Expected Delivery | Received? | Notes |
|-----------|---------|-----------|----------|--------|------------|-------------------|-----------|-------|
| MG6010E-i6 V3 motor | 3 | 15 | ? | ? | ? | ? | ? | Joints J3, J4, J5 |
| GM25-BK370 gear motor (EE) | 2 | 10 | ? | ? | ? | ? | ? | Cotton grab + eject |
| OAK-D Lite camera | 1 | 5 | ? | ? | ? | ? | ? | Luxonis |
| Raspberry Pi 4B (4GB) | 1 | 5 | ? | ? | ? | ? | ? | Ubuntu 24.04 |
| MicroSD card (32GB+) | 1 | 5 | ? | ? | ? | ? | ? | Pre-flash needed |
| MCP2515 CAN HAT | 1 | 5 | ? | ? | ? | ? | ? | SPI-to-CAN |
| IO board (custom) | 1 | 5 | ? | ? | ? | ? | ? | GPIO routing |
| Timing belt (J5) | 1+spare | 10 | ? | ? | ? | ? | ? | Known wear item |
| Arm structural frame | 1 set | 5 sets | ? | ? | ? | ? | ? | L3, L4, L5 links |
| Camera mount bracket | 1 | 5 | ? | ? | ? | ? | ? | Fixed mount |
| Wiring harness | 1 set | 5 sets | ? | ? | ? | ? | ? | Power + signal |
| 5V buck converter | 1 | 5 | ? | ? | ? | ? | ? | RPi power from 48V |
| LEDs (status) | 2 | 10 | ? | ? | ? | ? | ? | Green + Red |

### Shared Components

| Component | Qty | Ordered? | Vendor | Expected Delivery | Received? | Notes |
|-----------|-----|----------|--------|-------------------|-----------|-------|
| RTK GPS module (u-blox ZED-F9P) | 1 | AVAILABLE | ? | N/A | Yes | Hardware exists. Needs ROS2 integration. |
| RTK antenna (survey-grade) | 1 | AVAILABLE | ? | N/A | Yes | Hardware exists. |
| RTK base station or NTRIP sub | 1 | ? | ? | ? | ? | Check if available or needed |
| IMU module | 1 | ? | ? | ? | ? | For autonomy |
| Vehicle RPi heat sink/fan | 1 | ? | ? | ? | ? | Thermal fix V3 |
| Spare J5 belts | 5+ | ? | ? | ? | ? | Reliability testing |
| Spare EE motor assembly | 2 | ? | ? | ? | ? | Field spares |

### Build Progress Tracker

| Arm | Status | Assembly Start | Assembly Complete | Electrical Done | Software Loaded | CAN Verified | Camera Cal | Field Ready |
|-----|--------|---------------|-------------------|----------------|----------------|-------------|-----------|-------------|
| arm_1 | OPERATIONAL | Done | Done | Done | Done | Done | Done | Yes |
| arm_2 | OPERATIONAL | Done | Done | Done | Done | Done | Needs recal (A22: arm_2 border filter 3-4x higher than arm_1, suspect camera stereo calibration quality) | Yes (operational, suboptimal border filter) |
| arm_3 | NOT STARTED | ? | ? | ? | ? | ? | ? | ? |
| arm_4 | NOT STARTED | ? | ? | ? | ? | ? | ? | ? |
| arm_5 | NOT STARTED | ? | ? | ? | ? | ? | ? | ? |
