### MODIFIED Requirement: Compute Candidate Joints In Arm Nodes

The camera-coordinate sequence flow SHALL compute candidate joints inside each arm node at runtime
from camera/cotton points.

#### Scenario: Arm node computes runtime candidate joints
- **WHEN** an arm receives its active target point
- **THEN** it computes its own candidate `j4`, `j3`, and `j5` values
