# Spec: Arm Pair Selection

## Purpose

Defines how the operator selects which two arms participate in a collision avoidance
scenario run, and how the backend validates and applies that selection.

## Requirements

### Requirement: Operator selects arm pair before run

The UI SHALL provide a dropdown that lets the operator choose which two arms participate
in a run before pressing Start Run. Valid options are arm1+arm2, arm1+arm3, and
arm2+arm3. The default SHALL be arm1+arm2.

#### Scenario: Default arm pair is arm1+arm2

- **WHEN** the operator opens the Scenario Run panel
- **THEN** the arm pair dropdown shows arm1+arm2 selected by default

#### Scenario: Operator selects arm1+arm3

- **WHEN** the operator selects "arm1 + arm3" from the arm pair dropdown
- **AND** presses Start Run
- **THEN** the backend runs the scenario with arm1 as primary and arm3 as secondary

#### Scenario: Operator selects arm2+arm3

- **WHEN** the operator selects "arm2 + arm3" from the arm pair dropdown
- **AND** presses Start Run
- **THEN** the backend runs the scenario with arm2 as primary and arm3 as secondary

### Requirement: Backend validates arm pair

The backend SHALL reject any `arm_pair` value that does not consist of exactly two
distinct, known arm IDs. A known arm ID is any key present in `ARM_CONFIGS` (currently
arm1, arm2, arm3).

#### Scenario: Valid pair is accepted

- **WHEN** `POST /api/run/start` is called with `arm_pair: ["arm1", "arm3"]`
- **THEN** the backend accepts the request and starts the run with that pair

#### Scenario: Unknown arm ID rejected

- **WHEN** `POST /api/run/start` is called with `arm_pair: ["arm1", "arm99"]`
- **THEN** the backend returns HTTP 422 and does not start a run

#### Scenario: Duplicate arm IDs rejected

- **WHEN** `POST /api/run/start` is called with `arm_pair: ["arm1", "arm1"]`
- **THEN** the backend returns HTTP 422 and does not start a run

#### Scenario: Missing arm_pair defaults to arm1+arm2

- **WHEN** `POST /api/run/start` is called without an `arm_pair` field
- **THEN** the backend uses `["arm1", "arm2"]` and starts the run normally

### Requirement: Scenario arm IDs remapped to selected pair

The run pipeline SHALL remap scenario steps so that steps with `arm_id="arm1"` are
executed by the selected primary arm, and steps with `arm_id="arm2"` are executed by
the selected secondary arm. Existing scenario files require no modification.

#### Scenario: arm1+arm3 run remaps arm2 steps to arm3

- **GIVEN** a scenario with steps for arm_id="arm1" and arm_id="arm2"
- **WHEN** the operator starts a run with arm_pair=["arm1", "arm3"]
- **THEN** arm1 steps are executed by arm1 (no change)
- **AND** arm2 steps are executed by arm3 (remapped)
- **AND** Gazebo joint commands are published to arm3's topics
  (`/arm_joint3_copy1_cmd`, `/arm_joint4_copy1_cmd`, `/arm_joint5_copy1_cmd`)

#### Scenario: arm2+arm3 run remaps arm1 steps to arm2 and arm2 steps to arm3

- **GIVEN** a scenario with steps for arm_id="arm1" and arm_id="arm2"
- **WHEN** the operator starts a run with arm_pair=["arm2", "arm3"]
- **THEN** arm1 steps are executed by arm2 (remapped to primary)
- **AND** arm2 steps are executed by arm3 (remapped to secondary)
