# Spec: Per-Arm Cotton Colour

## Purpose

Defines how cotton ball models are coloured by arm identity at spawn time so arms are visually distinguishable in Gazebo.

## Requirements

### Requirement: Cotton colour at spawn time is determined by arm identity

The system SHALL spawn cotton ball models with arm-specific colours:
arm1 cottons SHALL use red (RGBA 1 0 0 1) and arm2 cottons SHALL use
blue (RGBA 0 0 1 1). Colour SHALL be applied to both ambient and diffuse
material channels in the SDF so the distinction is visible in Gazebo's
default lighting.

#### Scenario: arm1 cotton spawns as red
- **WHEN** spawn_fn is called for arm1
- **THEN** the SDF sent to Gazebo contains `<ambient>1 0 0 1</ambient>` and `<diffuse>1 0 0 1</diffuse>`

#### Scenario: arm2 cotton spawns as blue
- **WHEN** spawn_fn is called for arm2
- **THEN** the SDF sent to Gazebo contains `<ambient>0 0 1 1</ambient>` and `<diffuse>0 0 1 1</diffuse>`

#### Scenario: colour is consistent for all steps of the same arm
- **GIVEN** arm1 has 3 cotton steps
- **WHEN** all three cottons are spawned
- **THEN** all three SDF strings contain the red material definition

### Requirement: Unknown arm_id falls back to white

If `spawn_fn` is called with an arm_id that is not arm1 or arm2 (e.g. arm3),
the cotton SHALL spawn with white colour (RGBA 1 1 1 1) as a safe default.

#### Scenario: arm3 cotton spawns as white fallback
- **WHEN** spawn_fn is called with arm_id="arm3"
- **THEN** the SDF contains `<ambient>1 1 1 1</ambient>`
