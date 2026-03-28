# Spec: Joint Sequence Player

## Purpose

The Custom Joint Sequence Player allows operators to define, configure, and execute an ordered sequence of arm joint position steps from the UI. It provides controls for arm selection, repeat behaviour, and safety guards (E-STOP and rosbridge connection).

## Requirements

### Requirement: User can define a custom joint sequence
The system SHALL provide an editable table where the user can define an ordered
list of arm joint position steps. Each step SHALL contain values for J3 (rad),
J4 (m), J5 (m), and a hold duration (seconds). The table SHALL support adding
and removing rows dynamically.

#### Scenario: Add a row to the sequence table
- **WHEN** the user clicks the "Add Row" button
- **THEN** a new row is appended to the table with default values (J3=0, J4=0, J5=0, hold=2.0)

#### Scenario: Remove a row from the sequence table
- **WHEN** the user clicks the delete button on a row
- **THEN** that row is removed from the table and the remaining rows renumber

#### Scenario: Edit a cell value
- **WHEN** the user types a numeric value into any cell of a row
- **THEN** the cell accepts the value and it is used during sequence execution

### Requirement: User can select the target arm
The system SHALL provide a dropdown to select which arm (Arm 1, Arm 2, or Arm 3)
the sequence publishes to. The selection SHALL map to the corresponding
rosbridge topics (`/joint*_cmd`, `/joint*_copy_cmd`, `/arm_joint*_copy1_cmd`).

#### Scenario: Arm 1 selected
- **WHEN** the user selects "Arm 1" and starts the sequence
- **THEN** all publish calls use `/joint3_cmd`, `/joint4_cmd`, `/joint5_cmd`

#### Scenario: Arm 2 selected
- **WHEN** the user selects "Arm 2" and starts the sequence
- **THEN** all publish calls use `/joint3_copy_cmd`, `/joint4_copy_cmd`, `/joint5_copy_cmd`

#### Scenario: Arm 3 selected
- **WHEN** the user selects "Arm 3" and starts the sequence
- **THEN** all publish calls use `/arm_joint3_copy1_cmd`, `/arm_joint4_copy1_cmd`, `/arm_joint5_copy1_cmd`

### Requirement: User can configure repeat behaviour
The system SHALL provide a repeat control that accepts either a positive integer
(run N times) or a "loop" mode (run continuously until stopped). The default
SHALL be 1 (run once).

#### Scenario: Run once
- **WHEN** repeat is set to 1 and the sequence finishes all steps
- **THEN** the sequence stops automatically and the Start button re-enables

#### Scenario: Run N times
- **WHEN** repeat is set to N > 1 and the last step of a pass completes
- **THEN** the sequence restarts from step 1 until N passes are done, then stops

#### Scenario: Loop mode
- **WHEN** repeat is set to "loop" and the last step completes
- **THEN** the sequence restarts from step 1 and continues until the user clicks Stop

### Requirement: System executes sequence steps in order
The system SHALL iterate through table rows in order (top to bottom), publish
J3, J4, and J5 to the selected arm's topics, update the slider UI to reflect
the current step values, and wait for the row's hold duration before advancing.

#### Scenario: Step executes and advances
- **WHEN** a step begins execution
- **THEN** J3, J4, J5 values are published to the selected arm's rosbridge topics,
  the arm sliders update to reflect those values, and the system waits for hold duration seconds before moving to the next step

#### Scenario: Progress display during execution
- **WHEN** a step is executing
- **THEN** the progress bar advances proportionally and the label shows "Step N/M — holding Xs"

#### Scenario: Current step is highlighted
- **WHEN** a step is executing
- **THEN** the corresponding table row is visually highlighted (active-step class)

### Requirement: Sequence aborts immediately on E-STOP
The system SHALL check the E-STOP state before each step and after each hold
period. If E-STOP is active, the sequence SHALL stop immediately without
publishing further joint commands.

#### Scenario: E-STOP triggered during hold
- **WHEN** E-STOP is activated while the sequence is holding at a step
- **THEN** the sequence exits the hold early, marks the current step as aborted,
  and halts without publishing any further commands

#### Scenario: E-STOP already active at start
- **WHEN** the user clicks Start while E-STOP is active
- **THEN** the sequence does not start and logs an error message

#### Scenario: E-STOP triggered between steps
- **WHEN** E-STOP is activated between two steps
- **THEN** the next step is not executed and the sequence halts

### Requirement: Sequence cannot start without rosbridge connection
The system SHALL prevent sequence execution if rosbridge is not connected, and
SHALL display an error in the log area.

#### Scenario: Start attempted without connection
- **WHEN** the user clicks Start and rosbridge is not connected
- **THEN** execution does not begin and a log message "Cannot run sequence — rosbridge not connected" appears

### Requirement: Input values outside joint limits trigger a warning
The system SHALL compare each row's J3, J4, J5 values against the known joint
limits and display a visible warning on out-of-range cells. Execution SHALL
still be permitted (soft warning, not a block) so testers can intentionally
probe limit behaviour.

#### Scenario: J3 value below minimum
- **WHEN** the user enters a J3 value less than −0.9 rad
- **THEN** that cell is highlighted in warning colour and a tooltip shows the valid range

#### Scenario: J5 value above maximum
- **WHEN** the user enters a J5 value greater than 0.45 m
- **THEN** that cell is highlighted in warning colour and a tooltip shows the valid range

#### Scenario: Out-of-range value does not block execution
- **WHEN** the sequence contains an out-of-range value and the user clicks Start
- **THEN** the sequence executes and publishes the out-of-range value as entered
