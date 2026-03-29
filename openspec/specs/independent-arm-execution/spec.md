# Spec: Independent Arm Execution

## Purpose

Defines how arms execute their step lists independently in dedicated threads without peer synchronisation, including per-arm state tracking and thread-safe shared resources.

## Requirements

### Requirement: Arms execute their step lists independently without peer synchronisation

In unrestricted mode each arm SHALL process its own step list sequentially in a
dedicated thread, advancing to the next step as soon as its current pick animation
reaches a terminal outcome. One arm SHALL NOT block or wait for the peer arm to
finish its current step before advancing.

#### Scenario: arm1 advances to its next step while arm2 is still animating
- **WHEN** arm1 finishes its step-0 animation and arm2 is still mid-animation for step-0
- **THEN** arm1 immediately starts its step-1 animation without waiting for arm2

#### Scenario: arm with fewer steps finishes while peer continues
- **GIVEN** arm1 has 3 steps and arm2 has 5 steps
- **WHEN** arm1 completes its third pick
- **THEN** arm1 terminates its thread while arm2 continues processing its remaining steps
- **AND** arm2 runs steps 3 and 4 unimpeded

#### Scenario: both arms execute step-0 concurrently at run start
- **WHEN** the run starts and both arms have a step at index 0
- **THEN** both arm threads start their step-0 animations simultaneously (within ~50 ms of each other)

### Requirement: Mode logic uses the peer arm's latest published candidate state

Each arm thread SHALL publish its own candidate joints to a shared peer transport at
the start of each step. It SHALL then read the peer's latest published state (which
may correspond to a different step index) before applying mode logic.  If the peer
has not yet published any state, peer_state SHALL be treated as None.

#### Scenario: peer state is available — mode logic uses it
- **GIVEN** arm2 has published candidate joints j4=0.030 for its current step
- **WHEN** arm1 computes mode logic for its current step with j4=0.050
- **THEN** mode logic receives peer j4=0.030 and evaluates the lateral gap (0.020 m)

#### Scenario: peer has not published yet — mode logic treats peer as absent
- **GIVEN** arm2 has not yet published any state
- **WHEN** arm1 applies mode logic for its first step
- **THEN** peer_state is None and mode logic treats the arm as solo

### Requirement: Peer transport and reporter are thread-safe for concurrent arm threads

The `LocalPeerTransport` and `JsonReporter` SHALL serialise concurrent reads and
writes from different arm threads using a threading Lock.  No arm step report SHALL
be lost or corrupted due to a race condition.

#### Scenario: concurrent publish from two arm threads does not corrupt transport state
- **WHEN** arm1 and arm2 both call transport.publish() at the same time
- **THEN** both packets are stored and each arm can retrieve the other's packet without data corruption

#### Scenario: concurrent add_step calls do not lose step reports
- **WHEN** arm1 and arm2 both call reporter.add_step() at the same time
- **THEN** both step reports appear in the final run summary

### Requirement: prev_joints tracking is per-arm-thread with no shared state

Each arm thread SHALL maintain its own `prev_joints` dict initialised to safe-home.
Updates to one arm's prev_joints SHALL NOT affect the other arm's prev_joints.

#### Scenario: arm1 prev_joints update does not affect arm2
- **WHEN** arm1 executes a step that updates its j4 to 0.050 m
- **THEN** arm2's prev_joints remain at their last recorded value

### Requirement: Run completes only after all arm threads reach terminal state

`RunController.run()` SHALL block until every arm thread has processed all of its
steps (or been aborted by E-STOP). The returned summary SHALL include step reports
from all arms.

#### Scenario: run() returns after the last arm thread finishes
- **GIVEN** arm1 finishes in ~8 s and arm2 finishes in ~14 s
- **WHEN** run() is called
- **THEN** run() returns after arm2 finishes (~14 s), not after arm1 finishes (~8 s)
