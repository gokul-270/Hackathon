## ADDED Requirements

### Requirement: Run All Modes Endpoint Returns Five Summaries

The backend SHALL expose `POST /api/run/start-all-modes` that accepts `{scenario: dict, arm_pair: list, enable_phi_compensation: bool}`, dry-runs collision avoidance modes 0 through 4 without Gazebo motion, and returns a JSON response containing exactly 5 run summaries (one per mode).

#### Scenario: Endpoint returns 200 with five summaries

- **WHEN** the operator sends `POST /api/run/start-all-modes` with a valid scenario and arm pair
- **THEN** the backend returns HTTP 200
- **AND** the response body contains `summaries` as a list of exactly 5 dicts

#### Scenario: Summaries cover all five mode names

- **WHEN** the operator sends `POST /api/run/start-all-modes` with a valid payload
- **THEN** the set of `mode` values across the 5 summaries SHALL be `{unrestricted, baseline_j5_block_skip, geometry_block, sequential_pick, smart_reorder}`

#### Scenario: Invalid arm pair returns 422

- **WHEN** the operator sends `POST /api/run/start-all-modes` with an invalid arm pair (e.g. `["arm1", "arm99"]`)
- **THEN** the backend returns HTTP 422

### Requirement: Response Includes Comparison Markdown

The response from `POST /api/run/start-all-modes` SHALL include a `comparison_markdown` field containing the output of `MarkdownReporter.generate()` applied to the 5 run summaries.

#### Scenario: Comparison markdown contains report heading

- **WHEN** the all-modes run completes
- **THEN** the `comparison_markdown` field contains the text "Comparison Report"

#### Scenario: Comparison markdown contains recommendation section

- **WHEN** the all-modes run completes
- **THEN** the `comparison_markdown` field contains the text "Recommendation"

### Requirement: Response Includes Recommended Mode Name

The response from `POST /api/run/start-all-modes` SHALL include a `recommendation` field containing the name of the best mode as determined by `MarkdownReporter`'s decision tree.

#### Scenario: Recommendation names a valid mode

- **WHEN** the all-modes run completes
- **THEN** the `recommendation` field SHALL be one of: `unrestricted`, `baseline_j5_block_skip`, `geometry_block`, `sequential_pick`, `smart_reorder`

### Requirement: All Modes Report Download Endpoints

The backend SHALL expose `GET /api/run/report/all-modes/json` returning the 5 summaries as JSON, and `GET /api/run/report/all-modes/markdown` returning the comparison markdown as `text/plain`.

#### Scenario: JSON report returns 200 after completed run

- **WHEN** an all-modes run has completed
- **AND** the operator sends `GET /api/run/report/all-modes/json`
- **THEN** the backend returns HTTP 200 with a `summaries` list of 5 dicts

#### Scenario: JSON report returns 404 before any run

- **WHEN** no all-modes run has been performed
- **AND** the operator sends `GET /api/run/report/all-modes/json`
- **THEN** the backend returns HTTP 404

#### Scenario: Markdown report returns comparison table after run

- **WHEN** an all-modes run has completed
- **AND** the operator sends `GET /api/run/report/all-modes/markdown`
- **THEN** the backend returns HTTP 200 with content containing "Comparison Report" and "Recommendation"
