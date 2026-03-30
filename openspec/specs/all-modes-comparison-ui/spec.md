## ADDED Requirements

### Requirement: Run All Modes Button Visible In Scenario Run Section

The testing UI SHALL display a "Run All Modes" button in the Scenario Run section, positioned below the existing "Start Run" button.

#### Scenario: Button present in Scenario Run panel

- **WHEN** the operator views the Scenario Run section of the testing UI
- **THEN** a button labelled "Run All Modes" is visible below the "Start Run" button

### Requirement: Button Uses Same Scenario Source As Start Run

The "Run All Modes" button SHALL resolve the scenario using the same logic as "Start Run": file input takes priority over preset selector. If neither is selected, an error message SHALL be displayed.

#### Scenario: File input takes priority over preset

- **WHEN** the operator has loaded a JSON file via the file input
- **AND** has also selected a preset from the dropdown
- **AND** clicks "Run All Modes"
- **THEN** the file input scenario SHALL be used for the all-modes run

#### Scenario: Error shown when no scenario selected

- **WHEN** neither a file input nor a preset is selected
- **AND** the operator clicks "Run All Modes"
- **THEN** a status message SHALL display "Error: no scenario selected."

### Requirement: Modal Displays Colourful Comparison Table On Completion

When the all-modes run completes, the UI SHALL display a modal popup containing a comparison table with one row per mode (5 rows total). Table columns SHALL include Mode, Total Steps, Near-Collisions, Collisions, Blocked+Skipped, and Completed Picks. Cells SHALL be colour-coded: green for zero-collision values, red for collision values greater than zero, and amber for near-collision values greater than zero when collisions are zero. The row for the recommended mode SHALL be visually highlighted.

#### Scenario: Table has five rows with one per mode

- **WHEN** the all-modes run completes and the modal opens
- **THEN** the comparison table SHALL contain exactly 5 data rows
- **AND** each row SHALL correspond to one of the 5 collision avoidance modes

#### Scenario: Zero collision cells are green and collision cells are red

- **WHEN** the comparison table is displayed
- **THEN** cells in the Collisions column with value 0 SHALL have a green background
- **AND** cells in the Collisions column with value greater than 0 SHALL have a red background

#### Scenario: Near collision cells are amber when no collisions

- **WHEN** the comparison table is displayed
- **AND** a mode has near-collision steps greater than 0 but collision steps equal to 0
- **THEN** cells in the Near-Collisions column for that mode SHALL have an amber background

#### Scenario: Recommended mode row is highlighted

- **WHEN** the comparison table is displayed
- **THEN** the row corresponding to the recommended mode SHALL be visually highlighted with a distinct border or background colour

#### Scenario: Recommendation text displayed below table

- **WHEN** the modal is displayed after an all-modes run
- **THEN** the recommendation text from the comparison report SHALL be displayed below the table

### Requirement: Modal Has Report Download Links

The modal SHALL contain download links for the JSON report and the Markdown comparison report, pointing to `GET /api/run/report/all-modes/json` and `GET /api/run/report/all-modes/markdown` respectively.

#### Scenario: Download links point to correct endpoints

- **WHEN** the modal is displayed after an all-modes run
- **THEN** a "Download JSON Report" link SHALL point to `/api/run/report/all-modes/json`
- **AND** a "Download Markdown Report" link SHALL point to `/api/run/report/all-modes/markdown`
