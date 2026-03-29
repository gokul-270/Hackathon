# Gherkin Spec Creation Skill

A comprehensive skill for creating well-formed Gherkin BDD scenarios during the OpenSpec feature specification process.

## Overview

**gherkin-spec-creation** transforms feature narratives into comprehensive, validated Gherkin scenarios that serve as executable specifications. The skill guides users through:

1. **Parsing** feature narratives to identify behaviors
2. **Generating** batch Gherkin scenarios (happy path + edge cases + errors)
3. **Validating** scenarios against quality standards
4. **Embedding** approved scenarios into spec artifacts

## When to Use

Use this skill when:
- ✅ Creating a new feature spec during `openspec-new-change` workflow
- ✅ You have a feature narrative (user story + acceptance criteria)
- ✅ You need comprehensive BDD scenarios that cover all behaviors
- ✅ Scenarios will be part of the design specification
- ✅ You want automated quality validation of your scenarios

## Quick Start

### 1. Prepare Feature Narrative

Structure your feature description using the provided template:

```
Feature Title: Export Configuration to JSON
Actors: System Administrator, Team Lead
Key Behaviors:
- Export configuration to file
- Choose export location  
- Success notification
Edge Cases:
- Special characters in config
- Directory doesn't exist
Error Scenarios:
- Disk is full
- Permission denied
```

See `feature-narrative-template.md` for complete template.

### 2. Invoke the Skill

Use this skill to generate scenarios:

```
Use gherkin-spec-creation skill to generate Gherkin scenarios for:
[Your feature narrative]
```

### 3. Review Generated Scenarios

The skill generates ALL scenarios in batch format, validates them, and flags any issues:

```gherkin
Scenario: User successfully exports configuration
  Given configuration is loaded
  When user clicks Export button
  Then JSON file is created

Scenario: Export handles special characters
  Given configuration contains special characters
  When user exports
  Then special characters are properly escaped in JSON

[... more scenarios ...]
```

### 4. Validate Results

Skill auto-validates against:
- ✅ **Syntax** — Proper Given/When/Then format
- ✅ **Consistency** — Consistent domain language
- ✅ **Coverage** — All behaviors, edge cases, errors addressed
- ✅ **Clarity** — Specific and measurable outcomes
- ✅ **Atomicity** — One behavior per scenario

### 5. Embed in Design Artifact

Add approved scenarios to your OpenSpec Design artifact:

```markdown
## Gherkin Acceptance Criteria

[Paste validated scenarios]

All scenarios must pass before feature is considered complete.
```

## Files Included

| File | Purpose |
|------|---------|
| **SKILL.md** | Main skill documentation with Gherkin principles, workflow, examples |
| **feature-narrative-template.md** | Template for structuring feature input |
| **gherkin-quality-checklist.md** | Systematic validation rules for scenarios |
| **example-scenarios.md** | Real-world examples (file export, authentication, shopping cart) |
| **INTEGRATION.md** | How to use this skill within OpenSpec workflow |

## Key Features

### Comprehensive Workflow

```
Parse Narrative → Identify Behaviors → Generate Scenarios (Batch)
    ↓
Auto-Validate → Flag Issues → User Reviews → Embed in Spec
```

### Quality Validation

The embedded quality checklist validates:

1. **Syntax** — All Given/When/Then proper format, single action in When
2. **Consistency** — Terminology used uniformly across all scenarios
3. **Coverage** — All narrative behaviors, edge cases, errors represented
4. **Clarity** — All Given/When/Then specific and measurable
5. **Atomicity** — Each scenario tests exactly one behavior

### Red Flags Detection

Automatically flags:
- Missing Given/When/Then
- Multiple actions in When clause
- Too many assertions in Then
- Inconsistent terminology
- Vague outcomes
- Coverage gaps

## Integration with OpenSpec

This skill fits into the `openspec-new-change` workflow:

```
1. Create Problem Statement
2. Create Design artifact
3. **→ USE GHERKIN-SPEC-CREATION ←** Generate Gherkin scenarios
4. Add Gherkin to Design artifact
5. Create Implementation Tasks
6. Ready for implementation
```

See `INTEGRATION.md` for detailed workflow integration.

## Example Usage

### Input

```
Feature Title: Delete User Account
Description: Users can permanently delete their account and all data
Actors: End User, Admin
Key Behaviors:
- User initiates deletion
- User confirms via email
- Account permanently removed
Edge Cases:
- User has dependent accounts
- User has active subscriptions
Error Scenarios:
- Verification code expires
- Email delivery fails
```

### Generated Output

```gherkin
Scenario: User successfully initiates account deletion
  Given user is logged in
  When user clicks "Delete Account" button
  Then confirmation dialog appears: "This action cannot be undone"

Scenario: User confirms deletion via email verification
  Given user initiated account deletion
  When user clicks verification link in email
  Then account deletion is confirmed
    And account is immediately removed

[9 more scenarios covering edge cases and errors...]
```

### Validation Results

✅ **All checks pass:**
- Syntax: 10/10 scenarios valid
- Consistency: All terminology consistent
- Coverage: 3 behaviors + 3 edge cases + 3 errors = 10 scenarios (100%)
- Clarity: All scenarios specific and measurable
- Atomicity: Each scenario tests one behavior

## Common Patterns

### Happy Path Scenario

```gherkin
Scenario: User successfully [action]
  Given [precondition]
  When user [action]
  Then [expected outcome]
```

### Edge Case Scenario

```gherkin
Scenario: [Action] handles [special situation]
  Given [precondition with special condition]
  When user [action]
  Then [expected handling of special case]
```

### Error Scenario

```gherkin
Scenario: [Action] fails when [error condition]
  Given [error condition exists]
  When user attempts [action]
  Then error message "[specific error]" appears
```

## Best Practices

✅ **DO:**
- One behavior per scenario
- Use domain language (user perspective)
- Include all edge cases and errors
- Make outcomes specific and measurable
- Use consistent terminology throughout

❌ **DON'T:**
- Multiple actions in When clause
- Too many assertions in Then
- Over-specify Given preconditions
- Use technical jargon or implementation details
- Mix terminology for same concept

## Validation Checklist Quick Reference

Use this checklist to validate scenarios:

- [ ] All scenarios have Given/When/Then
- [ ] When has exactly one action (no "and")
- [ ] Then assertions are specific (not vague)
- [ ] Same terms used consistently throughout
- [ ] All narrative behaviors covered
- [ ] All edge cases covered
- [ ] All error scenarios covered
- [ ] Each scenario tests one behavior
- [ ] No vague terms ("something", "happens", "works")
- [ ] No red flags present

## Elixir Cucumber Compatibility

Generated scenarios are compatible with Elixir Cucumber syntax. During implementation, scenarios can be extracted to `.feature` files:

```bash
# Scenarios in design artifact can be copied to:
features/user_account/delete_account.feature

# Then run with Cucumber:
mix cucumber features/user_account/delete_account.feature
```

## Troubleshooting

**Problem: Scenario is too vague**
- Solution: Make Given/When/Then specific with exact values and outcomes

**Problem: Too many assertions in Then**
- Solution: Create separate scenario for each assertion

**Problem: Multiple actions in When**
- Solution: Use When/And only for additional data, not separate actions

**Problem: Terminology inconsistent**
- Solution: Create terminology table and use terms consistently

**Problem: Edge cases missing**
- Solution: Review narrative for mentioned special situations

## Support & Contribution

This skill is part of the GTron Part Configurator project and follows OpenCode standards.

**To contribute:**
1. Follow the writing-skills TDD methodology
2. Test thoroughly with pressure scenarios
3. Validate against existing examples
4. Submit with clear rationale

## License

This skill is part of the GTron Part Configurator project.

---

**Ready to use the skill?** Load it in your OpenCode session:

```
/load-skill gherkin-spec-creation
```

Then provide your feature narrative to get started!
