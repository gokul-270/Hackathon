# Integration Guide: Gherkin Spec Creation with OpenSpec

This document explains how to use the Gherkin Spec Creation skill within the OpenSpec workflow.

## Workflow Integration

### Where Gherkin Fits in OpenSpec

The Gherkin Spec Creation skill integrates into `openspec-new-change` workflow:

```
1. Start new change (openspec-new-change)
   ↓
2. Create Problem Statement artifact
   ↓
3. Create Design artifact
   ↓
4. **→ USE GHERKIN-SPEC-CREATION ←** Generate Gherkin scenarios
   ↓
5. Add Gherkin scenarios to Design artifact
   ↓
6. Create Implementation Tasks artifact
   ↓
7. Ready for implementation (subagent-driven-development)
```

## How to Use

### Step 1: Start an OpenSpec Change

```bash
openspec new change "add-user-authentication"
```

Create your Problem Statement and Design artifacts as normal.

### Step 2: Extract Feature Narrative

After completing the Design artifact, extract the feature narrative:

- **Feature Title** → Problem Statement title
- **Description** → Problem Statement description
- **Actors** → Users/personas from Design
- **Key Behaviors** → Requirements from Design
- **Edge Cases** → Constraints/edge cases from Design
- **Error Scenarios** → Error handling from Design

### Step 3: Use Gherkin Spec Creation Skill

Invoke the skill in your current session:

```
Use the gherkin-spec-creation skill to generate scenarios
```

Provide the feature narrative as structured input.

### Step 4: Generate Scenarios

The skill will:
1. Parse your narrative
2. Generate comprehensive Gherkin scenarios (batch)
3. Auto-validate against quality standards
4. Flag any issues for review

### Step 5: Embed in Design Artifact

Once scenarios are approved, add them to your Design artifact:

```markdown
## Acceptance Criteria (Gherkin)

[Paste approved Gherkin scenarios here]

All scenarios must pass before implementation is considered complete.
```

### Step 6: Commit to OpenSpec

```bash
git add openspec/changes/add-user-authentication/
git commit -m "feat: Add Gherkin scenarios to design artifact"
```

### Step 7: Continue with Implementation Tasks

Create your Implementation Tasks artifact with these scenarios as acceptance criteria:

```
Each task must produce code that passes the corresponding Gherkin scenarios.
```

## Example Workflow

### Input: Feature Request

```
Create a feature for exporting user data to CSV.
Users should be able to:
- Click export button
- Choose export location
- Receive success notification

Edge cases: 
- Special characters in data
- Directory doesn't exist

Errors:
- Disk full
- Permission denied
```

### Step 1: Extract Narrative

```
Feature Title: Export User Data to CSV
Description: Users can export their profile and activity data to a CSV file for personal records.
Actors: End User, Registered Member
Key Behaviors:
- Click export button
- Choose export location
- Success notification displayed
Edge Cases:
- Data contains special characters
- Export directory doesn't exist
Error Scenarios:
- Disk is full
- Permission denied
```

### Step 2: Use Gherkin Skill

Pass narrative to skill → generates 8 scenarios (1 happy path + 2 behaviors + 2 edge cases + 3 errors)

### Step 3: Validate Scenarios

Skill validates:
- ✅ Syntax (all Given/When/Then proper)
- ✅ Consistency ("export", "user", "CSV" used consistently)
- ✅ Coverage (all 6 narrative items addressed)
- ✅ Clarity (all specific, measurable)
- ✅ Atomicity (one behavior per scenario)

### Step 4: Embed in Design

```markdown
## Acceptance Criteria

### Gherkin Scenarios

Scenario: User successfully exports data to CSV
  Given user is logged in
  When user clicks "Export Data" button
  Then CSV file is created in default location

[... 7 more scenarios ...]

All scenarios must pass QA testing before feature is considered complete.
```

### Step 5: Implementation

Developers use these scenarios as test specifications. Each task implements functionality to make scenarios pass:

```
Task 1: Create CSV export infrastructure
  - Implement scenario: User successfully exports data
  
Task 2: Handle special characters
  - Implement scenario: Export escapes special characters
  
Task 3: Error handling
  - Implement scenarios: Export fails when disk full, Permission denied
```

## Integration with Implementation

### Using Scenarios as Test Specs

Once scenarios are in the Design artifact, they become acceptance criteria:

1. **QA Tests Against Scenarios** — Testers verify each scenario manually or via automation
2. **Developers Implement to Satisfy Scenarios** — Code must make scenarios pass
3. **TDD Follow-Up** — Developers write unit tests alongside implementation

### Scenario-to-Test Mapping

Each Gherkin scenario maps to tests:

```gherkin
Scenario: User successfully exports CSV file
  Given user is logged in
  When user clicks "Export Data" button
  Then CSV file is created in ~/Downloads

→ Implementation Task:
  - Unit test: export function returns file path
  - Integration test: button click triggers export
  - E2E test: user sees file in file system
```

## Using with Subagent-Driven Development

After all artifacts are complete, dispatch implementer subagent with scenarios:

```
Task: Export User Data to CSV

Reference these acceptance criteria (Gherkin scenarios):
[Paste all scenarios]

Each scenario must pass before this task is considered complete.
```

Subagent uses scenarios to:
- Understand requirements from user perspective
- Design testable implementation
- Write tests that satisfy scenarios
- Self-review against scenarios before committing

## Benefits of This Integration

**For Design:**
- Executable specifications prevent ambiguity
- Gherkin forces clarity and completeness
- Scenarios catch edge cases before coding

**For Implementation:**
- Clear, testable acceptance criteria
- Reduced back-and-forth with stakeholders
- Easier to verify feature is complete

**For QA:**
- Scenarios define exactly what to test
- Repeatable test cases
- Clear test coverage

**For Product:**
- Feature requirements are unambiguous
- Scope is explicit (no hidden behaviors)
- Easy to communicate to stakeholders

## Checklist for Integration

Before starting implementation:

- [ ] Feature narrative has been created
- [ ] Gherkin scenarios have been generated
- [ ] All scenarios validated against quality checklist
- [ ] Scenarios are embedded in Design artifact
- [ ] No red flags in scenario validation
- [ ] Implementation team understands scenarios
- [ ] Scenarios are version-controlled in OpenSpec

Ready to implement!
