### Requirement: Parser And Controller Share The Same Paired-Step Contract

The scenario parser and controller SHALL support the same paired-step scenario format without bypasses
or inconsistent duplicate-step handling.

#### Scenario: Paired-step scenario validated and executed consistently
- **WHEN** a valid paired-step scenario is loaded
- **THEN** both parser and controller accept the same structure and execute it consistently

### Requirement: Wait Mode Waits Before Skipping

The overlap wait behavior SHALL wait according to the configured timeout model before skipping a pick.

#### Scenario: Wait happens before skip
- **WHEN** overlap contention occurs
- **THEN** the system waits according to the configured timeout before marking the pick skipped

### Requirement: Final Recommendation Names The Winning Mode

The final comparison report SHALL name the actual winning mode instead of using hardcoded mode text.

#### Scenario: Recommendation text reflects true winner
- **WHEN** final mode comparison is generated
- **THEN** the report names the actual recommended mode
