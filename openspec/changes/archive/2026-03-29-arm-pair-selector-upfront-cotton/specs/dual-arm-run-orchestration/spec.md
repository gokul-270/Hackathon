# Spec: Dual-Arm Run Orchestration (delta)

## Purpose

Changes to support a configurable arm pair (any two of arm1/arm2/arm3) instead of the
hardcoded arm1+arm2 pairing. Scenario arm_ids are remapped to the selected pair at load time.

## ADDED Requirements

### Requirement: Configurable arm pair replaces hardcoded arm1+arm2

The RunController SHALL accept an `arm_pair` parameter specifying which two arms participate
in a run. The first arm is the primary (replaces "arm1" scenario slots) and the second is the
secondary (replaces "arm2" scenario slots). The default SHALL be ("arm1", "arm2").

#### Scenario: Default arm pair produces unchanged behaviour

- **GIVEN** RunController instantiated with no arm_pair argument
- **WHEN** a scenario with arm1 and arm2 steps is run
- **THEN** arm1 steps execute on arm1 and arm2 steps execute on arm2

#### Scenario: arm_pair=("arm1","arm3") remaps arm2 slots to arm3

- **GIVEN** RunController instantiated with arm_pair=("arm1","arm3")
- **WHEN** a scenario with arm_id="arm2" steps is loaded
- **THEN** those steps are executed by arm3

#### Scenario: arm_pair=("arm2","arm3") remaps arm1 to arm2 and arm2 to arm3

- **GIVEN** RunController instantiated with arm_pair=("arm2","arm3")
- **WHEN** a scenario with arm_id="arm1" and arm_id="arm2" steps is loaded
- **THEN** arm1 steps are executed by arm2 and arm2 steps are executed by arm3
