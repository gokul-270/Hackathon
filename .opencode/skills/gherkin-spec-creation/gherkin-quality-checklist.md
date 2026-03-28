# Gherkin Quality Checklist

Systematic validation rules for Gherkin scenarios. Use this checklist to validate every scenario.

## 1. Syntax Validation

Every scenario must have exactly this structure:

```
Scenario: [Title]
  Given [initial state]
  When [user action]
  Then [expected outcome]
```

### Checklist

- [ ] **Scenario keyword present** — Starts with `Scenario:`
- [ ] **Title is present and clear** — Describes what the scenario tests
- [ ] **Given clause present** — Establishes preconditions (what must be true first)
- [ ] **When clause present** — Contains exactly ONE user action
- [ ] **Then clause present** — Describes expected outcome
- [ ] **When has no "And"** — Single action, not multiple
- [ ] **Proper indentation** — Given/When/Then are indented consistently
- [ ] **And/But keywords correct** — Used to extend Given/When/Then, not within clause

### Valid Examples

✅ Simple scenario:
```gherkin
Scenario: User exports configuration
  Given configuration is loaded
  When user clicks Export button
  Then JSON file is created
```

✅ Multiple preconditions:
```gherkin
Scenario: Export escapes special characters
  Given configuration is loaded
    And configuration contains special characters
  When user exports to JSON
  Then special characters are properly escaped
```

✅ Multiple verifications:
```gherkin
Scenario: Export succeeds with notifications
  Given configuration is loaded
  When user clicks Export button
  Then JSON file is created
    And success notification appears
    And export button becomes disabled
```

### Invalid Examples

❌ Multiple actions in When:
```gherkin
Scenario: User exports configuration
  Given configuration is loaded
  When user clicks Export button and selects location
  Then JSON file is created
```
**Fix:** Split into two scenarios OR move "selects location" to Given

❌ Too many assertions in Then:
```gherkin
Scenario: User exports
  Given configuration is loaded
  When user exports
  Then file is created and notification shows and history updated and analytics logged and
        email sent and backup triggered and thumbnail generated
```
**Fix:** Keep Then to 1-3 related assertions. Split other behaviors into separate scenarios.

## 2. Domain Language Consistency

All scenarios must use the same terminology for the same concepts.

### Checklist

- [ ] **Key terms are defined** — Create glossary if feature has >5 unique terms
- [ ] **Same term used consistently** — Don't mix "save" and "export" for same action
- [ ] **Technical jargon avoided** — Use user perspective, not implementation details
- [ ] **Acronyms consistent** — If using acronym, define on first use: "Two-Factor Authentication (2FA)"
- [ ] **No ambiguous pronouns** — Don't use "it" without clear reference
- [ ] **Tense is consistent** — Use present tense: "is created" not "was created"

### Terminology Table

Create this if feature has many domain terms:

| Term | Definition | Used In Scenarios |
|------|-----------|-------------------|
| Configuration | All system settings combined | All scenarios |
| Export | Save configuration to file | Export scenarios |
| Administrator | User with full system permissions | Admin-focused scenarios |

### Consistency Violations

❌ Inconsistent terms:
```gherkin
Scenario 1: User saves configuration
Scenario 2: User exports configuration
Scenario 3: User writes config to file
```
**Fix:** Choose ONE term: "export" and use consistently. Update all scenarios.

❌ Technical language:
```gherkin
Scenario: REST endpoint serializes config
  Given in-memory config object
  When POST /api/config/export called
  Then application/json response with schema v2
```
**Fix:** Write from user perspective:
```gherkin
Scenario: User exports configuration to JSON file
  Given configuration is loaded
  When user clicks Export button
  Then JSON file is created with all settings
```

## 3. Coverage Completeness

Feature spec must cover happy path, edge cases, AND error conditions.

### Checklist

- [ ] **Happy path scenarios exist** — Normal successful execution covered
- [ ] **Every key behavior has scenario** — All items from narrative Key Behaviors section addressed
- [ ] **All edge cases have scenarios** — Each item from Edge Cases section has a scenario
- [ ] **All error scenarios exist** — Each item from Error Scenarios section has corresponding scenario
- [ ] **No duplicate scenarios** — Each scenario tests distinct behavior
- [ ] **No missing behaviors** — Narrative doesn't mention any behavior not in scenarios

### Coverage Examples

**Feature Narrative Lists:**

Key Behaviors:
- Export configuration
- Choose export location
- Receive success notification

Edge Cases:
- Special characters in config
- Directory doesn't exist
- Configuration very large

Error Scenarios:
- Disk is full
- Permission denied
- File already exists

**Valid Coverage (All covered):**

```gherkin
Scenario: User successfully exports configuration
  Given configuration is loaded
  When user clicks Export button
  Then JSON file is created

Scenario: User selects custom export location
  Given configuration is loaded
  When user selects custom directory
  Then JSON file is created in selected location

Scenario: Export success notification displays
  Given configuration is loaded
  When user exports
  Then success notification "Configuration exported successfully" appears

Scenario: Export with special characters
  Given configuration contains special characters
  When user exports
  Then special characters are properly escaped in JSON

Scenario: Export creates directory if missing
  Given selected export directory doesn't exist
  When user exports
  Then directory is created automatically

Scenario: Export handles very large configuration
  Given configuration contains 1000+ settings
  When user exports
  Then all settings are included in JSON file

Scenario: Export fails when disk is full
  Given disk has no free space
  When user attempts export
  Then error "Insufficient disk space" is shown

Scenario: Export blocked by permission denial
  Given user lacks write permissions on directory
  When user attempts export
  Then error "Permission denied" is shown

Scenario: Export prompts for overwrite
  Given file already exists at target location
  When user exports
  Then dialog appears: "File exists. Overwrite?"
```

**Invalid Coverage (Gaps exist):**

```gherkin
Scenario: User exports configuration
  Given configuration is loaded
  When user clicks Export button
  Then JSON file is created
```

**Issues:**
- ❌ No scenarios for "Choose export location" (Key Behavior missing)
- ❌ No notification scenario (Key Behavior missing)
- ❌ No special character scenario (Edge Case missing)
- ❌ No error scenarios (All Error Scenarios missing)

**Fix:** Add scenarios for each missing behavior, edge case, and error.

## 4. Clarity and Testability

Scenarios must be clear enough for QA to test and developers to implement against.

### Checklist

- [ ] **Precondition is achievable** — Given state can be set up in test (not vague)
- [ ] **Action is observable** — When action can be verified to have occurred
- [ ] **Outcome is measurable** — Then result can be verified (not subjective)
- [ ] **No vague terms** — "Something", "stuff", "things" never appear
- [ ] **Specific values where needed** — "JSON file" not just "file"; "error message exactly says..." not "error appears"
- [ ] **Time dependencies clear** — If timing matters, state it: "within 5 seconds"
- [ ] **State transitions explicit** — What changes between Given and Then

### Clear vs Unclear Examples

❌ Unclear:
```gherkin
Scenario: User exports configuration
  Given configuration exists
  When user does export thing
  Then something happens
```
**Issues:**
- "configuration exists" — too vague (what state?)
- "does export thing" — not specific (which action?)
- "something happens" — unmeasurable (what exactly?)

✅ Clear:
```gherkin
Scenario: User successfully exports configuration to selected location
  Given configuration is fully loaded with 50 settings
  When user clicks "Export Configuration" button and selects ~/backups/config.json
  Then file ~/backups/config.json is created within 2 seconds
    And file contains valid JSON with all 50 settings
    And success notification displays: "Configuration exported successfully"
```

❌ Unmeasurable outcome:
```gherkin
Scenario: Export is fast
  Given configuration is loaded
  When user exports
  Then export completes quickly
```
**Fix:** Make measurable:
```gherkin
Scenario: Export completes within acceptable time
  Given configuration with 1000 settings
  When user exports to local disk
  Then file is created within 5 seconds
```

## 5. One Behavior Per Scenario (Atomicity)

Each scenario should test ONE distinct behavior, not multiple combined.

### Checklist

- [ ] **Scenario title describes ONE behavior** — Not "User exports and validates and shares"
- [ ] **One primary assertion in Then** — Main verification is single concept
- [ ] **Related verifications grouped** — Multiple "And" clauses OK if verifying same outcome
- [ ] **No behavior chains** — Scenario doesn't say "then user does next thing"

### Good Atomicity

✅ Each scenario is independent:

```gherkin
Scenario: Export creates file at specified location
  Given configuration is loaded
  When user exports to ~/backups/config.json
  Then file exists at ~/backups/config.json

Scenario: Export file contains all configuration values
  Given configuration with 50 settings
  When user exports
  Then exported JSON contains all 50 settings

Scenario: Export file is valid JSON
  Given configuration is loaded
  When user exports
  Then exported file is valid JSON parseable by standard tools
```

Each scenario can run independently, tests one concept, and produces focused feedback.

❌ Poor atomicity (too many behaviors):

```gherkin
Scenario: User exports configuration
  Given configuration is loaded
  When user clicks Export button
  Then file is created
    And file is valid JSON
    And file contains all settings
    And success notification appears
    And user can see export in history
    And email confirmation is sent
    And backup is triggered
    And analytics are updated
```

**Fix:** Create separate scenarios for each behavior. This scenario tests 7 different things!

```gherkin
Scenario: Export creates valid JSON file with all settings
  Given configuration with 50 settings is loaded
  When user exports
  Then valid JSON file is created containing all 50 settings

Scenario: Export displays success notification
  Given configuration is loaded
  When user exports
  Then success notification appears: "Configuration exported successfully"

Scenario: Export is recorded in export history
  Given configuration is loaded
  When user exports
  Then export appears in export history with timestamp

[etc. - one scenario per behavior]
```

## Validation Workflow

### Run Checklist Systematically

1. **Syntax Validation** — Every scenario passes syntax rules
2. **Consistency Check** — All terminology consistent, no mixing
3. **Coverage Review** — All narrative behaviors, edges, errors represented
4. **Clarity Audit** — Every Given/When/Then is measurable and achievable
5. **Atomicity Check** — Each scenario tests one behavior

### Red Flags (Stop and Fix Immediately)

- ❌ Scenario missing Given, When, or Then
- ❌ When clause has multiple actions
- ❌ Then has 5+ assertions (split into scenarios)
- ❌ Same term used 3+ different ways in same feature
- ❌ Scenario is not testable (vague outcome)
- ❌ Narrative lists behavior not in any scenario
- ❌ Only happy path, no edge cases or errors
- ❌ Scenario description doesn't match what it tests

### Approval Criteria

✅ Scenarios are APPROVED when:
- All syntax rules followed
- Terminology is consistent
- Coverage is complete (key behaviors + edge cases + errors)
- All scenarios are clear and testable
- Each scenario tests exactly one behavior
- No red flags present

## Example Validation

### Feature: Export Configuration

**Narrative:**
```
Key Behaviors: Export, Choose Location, Success Notification
Edge Cases: Special Chars, Missing Directory, Large Config
Error Scenarios: Disk Full, Permission Denied, File Exists
```

**Generated Scenarios:**

```gherkin
Scenario: User successfully exports configuration
  Given configuration is loaded
  When user clicks Export button
  Then JSON file is created

Scenario: User selects custom export location
  Given configuration is loaded
  When user selects ~/backups as export location
  Then JSON file is created at ~/backups/config.json

Scenario: Export displays success notification
  Given configuration is loaded
  When user exports
  Then notification "Configuration exported successfully" appears

Scenario: Export handles special characters in config
  Given configuration contains special characters (quotes, newlines, unicode)
  When user exports
  Then special characters are properly escaped in JSON file

Scenario: Export creates missing directory
  Given selected export directory does not exist
  When user exports
  Then directory is created
    And JSON file is created in new directory

Scenario: Export handles very large configuration
  Given configuration with 1000+ settings
  When user exports to local disk
  Then all settings are present in exported JSON file

Scenario: Export fails when disk is full
  Given disk has no free space
  When user attempts export
  Then error message "Insufficient disk space" appears

Scenario: Export blocked by insufficient permissions
  Given selected directory is read-only
  When user attempts export
  Then error message "Permission denied: cannot write to directory" appears

Scenario: Export prompts when file already exists
  Given configuration is loaded
    And file already exists at export location
  When user exports to that location
  Then dialog appears: "File already exists. Overwrite?"
```

**Validation Results:**

| Check | Result | Notes |
|-------|--------|-------|
| Syntax | ✅ PASS | All scenarios have Given/When/Then |
| Consistency | ✅ PASS | "Export", "configuration", "user" used consistently |
| Coverage | ✅ PASS | All 3 behaviors + 3 edge cases + 3 errors = 9 scenarios |
| Clarity | ✅ PASS | All Given/When/Then are specific and measurable |
| Atomicity | ✅ PASS | Each scenario tests one behavior |

**Status: APPROVED**
