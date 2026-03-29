## ADDED Requirements

### Requirement: Arm pair selection in run UI

The UI SHALL provide an arm pair selector in the Scenario Run panel. The selected pair
SHALL be included in the run start request sent to the backend.

#### Scenario: Arm pair dropdown present in Scenario Run panel

- **WHEN** the operator views the Scenario Run section of the UI
- **THEN** an "Arm Pair" dropdown is visible above the Mode dropdown
- **AND** the dropdown offers options: "arm1 + arm2", "arm1 + arm3", "arm2 + arm3"
- **AND** "arm1 + arm2" is selected by default

#### Scenario: Selected arm pair sent in run start request

- **WHEN** the operator selects "arm1 + arm3" from the arm pair dropdown
- **AND** presses Start Run
- **THEN** the frontend sends `arm_pair: ["arm1", "arm3"]` in the POST /api/run/start body
