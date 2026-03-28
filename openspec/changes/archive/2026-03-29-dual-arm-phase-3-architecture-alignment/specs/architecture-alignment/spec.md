### Requirement: Runtime Structure Reflects Separate Arm Behavior

The implementation SHALL separate arm runtime responsibilities clearly enough to reflect the intended
dual-arm architecture instead of only relying on in-process object handoff.

#### Scenario: Arm runtimes operate as distinct runtime units
- **WHEN** the hackathon flow is launched
- **THEN** arm runtime responsibilities are separated into distinct runtime units

### Requirement: Peer-State Exchange Uses Explicit Runtime Transport

The peer-state exchange SHALL use an explicit runtime transport mechanism appropriate to the chosen
architecture.

#### Scenario: Peer state sent through runtime transport
- **WHEN** an arm publishes current and candidate joints
- **THEN** the peer arm receives them through the chosen runtime transport path
