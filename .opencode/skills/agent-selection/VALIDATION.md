# Validation Scenarios for Agent Selection

These scenarios apply RED/GREEN/REFACTOR testing to the `agent-selection` skill.

## RED-Phase Evidence

Without the skill, baseline subagents made these exact moves:
- `Use 3 model categories.`
- `Task 1: small/fast code-reading model`
- `Task 3: large/high-reliability procedural model`
- `Always return an array, even for one item.`
- `status`, `route`, and `error` fields were added to the schema
- `fail clearly on duplicates, gaps, or out-of-range references`
- `Ambiguous points I would likely leave unspecified unless forced by a spec:`

These scenarios make those failure modes concrete and verify the skill closes them.

Validation rule for `reason`:
- exact string match is required only for the invalid-or-empty fallback reason: `invalid or empty task description defaults to routine handling`
- for all other scenarios, the expected `reason` text is an approved example of the required rationale, not the only valid wording

## Baseline Tier Coverage

### Scenario 1: `basic` route

**Input**

```json
[
  {
    "subtask": "Read the README and write a three-paragraph summary."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Read the README and write a three-paragraph summary.",
    "tier": "basic",
    "modelLabel": "Clause Haiku 4.5",
    "reason": "bounded summary task with low ambiguity and low risk",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

The task is narrow, concrete, and low-risk, so the lowest tier is appropriate.

### Scenario 2: `standard` route

**Input**

```json
[
  {
    "subtask": "Add a cancel button to the modal dialog and wire it to close the modal."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Add a cancel button to the modal dialog and wire it to close the modal.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine UI feature with clear requirements and limited scope",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

This is routine implementation work with clear success criteria and limited spread.

### Scenario 3: `advanced` route

**Input**

```json
[
  {
    "subtask": "Analyze the validation logic across the form module, API handlers, and database layer; propose a unified refactor to eliminate duplication."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Analyze the validation logic across the form module, API handlers, and database layer; propose a unified refactor to eliminate duplication.",
    "tier": "advanced",
    "modelLabel": "GPT-5.4",
    "reason": "task spans multiple components and requires non-trivial synthesis",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

The task spans multiple layers and asks for synthesis rather than a simple bounded change.

### Scenario 4: `expert` route

**Input**

```json
[
  {
    "subtask": "Customers report sporadic checkout timeouts with no clear pattern. Analyze the payment service, gateway, and database interaction, identify the root cause, and propose a safe fix strategy."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Customers report sporadic checkout timeouts with no clear pattern. Analyze the payment service, gateway, and database interaction, identify the root cause, and propose a safe fix strategy.",
    "tier": "expert",
    "modelLabel": "Claude Opus 4.6",
    "reason": "unclear root cause and high failure cost require deep diagnostic reasoning",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

This is difficult debugging with unclear cause and unusually costly mistakes, so `expert` is justified.

### Scenario 5: `specialized` route

**Input**

```json
[
  {
    "subtask": "Write BDD scenarios using the gherkin-spec-creation workflow, following the required tool order, domain framing, and validation sequence exactly."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Write BDD scenarios using the gherkin-spec-creation workflow, following the required tool order, domain framing, and validation sequence exactly.",
    "tier": "specialized",
    "modelLabel": "GPT-5.4",
    "reason": "workflow-sensitive task where process discipline matters more than raw reasoning escalation",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

The main challenge is tool ordering and workflow adherence, not deeper reasoning strength.

## Adjacent-Tier Boundaries

### Scenario 6: `standard` side of `standard` vs `advanced`

**Input**

```json
[
  {
    "subtask": "Rename the `validateEmail` function to `isValidEmail` and update its two callers."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Rename the `validateEmail` function to `isValidEmail` and update its two callers.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine refactor with clear scope and little ambiguity",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

The scope is bounded and mechanical, so `standard` beats `advanced`.

### Scenario 7: `advanced` side of `standard` vs `advanced`

**Input**

```json
[
  {
    "subtask": "The user service and auth middleware handle password resets inconsistently. Analyze both implementations and design a unified approach that preserves backward compatibility."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "The user service and auth middleware handle password resets inconsistently. Analyze both implementations and design a unified approach that preserves backward compatibility.",
    "tier": "advanced",
    "modelLabel": "GPT-5.4",
    "reason": "cross-file analysis and non-trivial synthesis outweigh routine implementation",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Backward compatibility plus cross-component synthesis pushes this into `advanced`.

### Scenario 8: `advanced` side of `advanced` vs `specialized`

**Input**

```json
[
  {
    "subtask": "Analyze validation across three services and propose a moderate refactor."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Analyze validation across three services and propose a moderate refactor.",
    "tier": "advanced",
    "modelLabel": "GPT-5.4",
    "reason": "multi-file reasoning and synthesis dominate over workflow concerns",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

This task is harder because of synthesis, not because of a strict process.

### Scenario 9: `specialized` side of `advanced` vs `specialized`

**Input**

```json
[
  {
    "subtask": "Execute the gherkin-spec-creation workflow with exact tool ordering, domain framing, and scenario validation."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Execute the gherkin-spec-creation workflow with exact tool ordering, domain framing, and scenario validation.",
    "tier": "specialized",
    "modelLabel": "GPT-5.4",
    "reason": "process discipline and tool ordering are the primary routing concern",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

The challenge is execution profile and ordered workflow, so `specialized` is the correct tie-break.

### Scenario 10: `advanced` side of `advanced` vs `expert`

**Input**

```json
[
  {
    "subtask": "Trace behavior across several modules and propose a moderate refactor."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Trace behavior across several modules and propose a moderate refactor.",
    "tier": "advanced",
    "modelLabel": "GPT-5.4",
    "reason": "cross-file reasoning is required, but the task does not reach expert-level risk or diagnostic difficulty",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

The task needs synthesis, but not architecture-level or high-stakes debugging judgment.

### Scenario 11: `expert` side of `advanced` vs `expert`

**Input**

```json
[
  {
    "subtask": "Debug a workflow-heavy production incident where the cause is unclear and mistakes are costly."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Debug a workflow-heavy production incident where the cause is unclear and mistakes are costly.",
    "tier": "expert",
    "modelLabel": "Claude Opus 4.6",
    "reason": "high-risk reasoning and unclear root cause dominate even though the workflow is strict",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Failure cost and reasoning difficulty dominate workflow sensitivity, so `expert` wins.

## Non-Happy-Path and Contract Scenarios

### Scenario 12: `null` subtask fallback

**Input**

```json
[
  {
    "subtask": null
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "<null>",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "invalid or empty task description defaults to routine handling",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Invalid subtasks still produce valid fallback records.

### Scenario 13: empty input array

**Input**

```json
[]
```

**Expected Output**

```json
[]
```

**Reasoning**

If the parent provides no subtasks, the skill returns an empty array and no routing notes.

### Scenario 14: no explicit indexes synthesize positional indexes

**Input**

```json
[
  {
    "subtask": "Summarize file A."
  },
  {
    "subtask": "Summarize file B."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Summarize file A.",
    "tier": "basic",
    "modelLabel": "Clause Haiku 4.5",
    "reason": "task is narrow and low-risk",
    "dispatchMode": "recommendation-only"
  },
  {
    "index": 1,
    "subtask": "Summarize file B.",
    "tier": "basic",
    "modelLabel": "Clause Haiku 4.5",
    "reason": "task is narrow and low-risk",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

When `index` is absent, the skill synthesizes 0-based positional indexes.

### Scenario 15: valid indexes are preserved

**Input**

```json
[
  {
    "index": 10,
    "subtask": "Summarize file A."
  },
  {
    "index": 12,
    "subtask": "Summarize file B."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 10,
    "subtask": "Summarize file A.",
    "tier": "basic",
    "modelLabel": "Clause Haiku 4.5",
    "reason": "task is narrow and low-risk",
    "dispatchMode": "recommendation-only"
  },
  {
    "index": 12,
    "subtask": "Summarize file B.",
    "tier": "basic",
    "modelLabel": "Clause Haiku 4.5",
    "reason": "task is narrow and low-risk",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Valid non-negative, non-duplicate indexes must be preserved as-is.

### Scenario 15A: mixed present and missing indexes

**Input**

```json
[
  {
    "index": 10,
    "subtask": "Summarize file A."
  },
  {
    "subtask": "Summarize file B."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 10,
    "subtask": "Summarize file A.",
    "tier": "basic",
    "modelLabel": "Clause Haiku 4.5",
    "reason": "task is narrow and low-risk",
    "dispatchMode": "recommendation-only"
  },
  {
    "index": 1,
    "subtask": "Summarize file B.",
    "tier": "basic",
    "modelLabel": "Clause Haiku 4.5",
    "reason": "task is narrow and low-risk",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

When indexes are valid where present and omitted elsewhere, preserve the explicit ones and synthesize positional indexes only for missing entries.

### Scenario 16: numeric subtask fallback

**Input**

```json
[
  {
    "subtask": 42
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "<number>",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "invalid or empty task description defaults to routine handling",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Numbers are non-string inputs, so they map to a deterministic placeholder and standard fallback.

### Scenario 17: object subtask fallback

**Input**

```json
[
  {
    "subtask": { "description": "Do something" }
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "<object>",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "invalid or empty task description defaults to routine handling",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Objects are invalid task descriptions but must still return correlation-stable output.

### Scenario 18: array subtask fallback

**Input**

```json
[
  {
    "subtask": ["one", "two"]
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "<array>",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "invalid or empty task description defaults to routine handling",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Arrays are invalid task descriptions and must be coerced to a type-name placeholder.

### Scenario 19: boolean subtask fallback

**Input**

```json
[
  {
    "subtask": true
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "<boolean>",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "invalid or empty task description defaults to routine handling",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Other non-string values should use deterministic type placeholders too.

### Scenario 20: empty-string subtask fallback

**Input**

```json
[
  {
    "subtask": ""
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "invalid or empty task description defaults to routine handling",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Empty strings are preserved as strings, but still use the standard fallback route.

### Scenario 21: whitespace-only subtask fallback

**Input**

```json
[
  {
    "subtask": "   "
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "   ",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "invalid or empty task description defaults to routine handling",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Whitespace-only strings stay unchanged rather than being converted to a placeholder.

### Scenario 22: duplicate indexes synthesize positional indexes

**Input**

```json
[
  {
    "index": 0,
    "subtask": "Update helper A and adjust one caller."
  },
  {
    "index": 0,
    "subtask": "Update helper B and adjust one caller."
  },
  {
    "index": 2,
    "subtask": "Update helper C and adjust one caller."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Update helper A and adjust one caller.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine update task with clear scope and limited ambiguity",
    "dispatchMode": "recommendation-only"
  },
  {
    "index": 1,
    "subtask": "Update helper B and adjust one caller.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine update task with clear scope and limited ambiguity",
    "dispatchMode": "recommendation-only"
  },
  {
    "index": 2,
    "subtask": "Update helper C and adjust one caller.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine update task with clear scope and limited ambiguity",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Duplicate indexes invalidate the full provided index set, so the output falls back to 0-based positional indexes.

### Scenario 23: malformed non-integer indexes synthesize positional indexes

**Input**

```json
[
  {
    "index": "zero",
    "subtask": "Update helper A and adjust one caller."
  },
  {
    "index": 1,
    "subtask": "Update helper B and adjust one caller."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Update helper A and adjust one caller.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine update task with clear scope and limited ambiguity",
    "dispatchMode": "recommendation-only"
  },
  {
    "index": 1,
    "subtask": "Update helper B and adjust one caller.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine update task with clear scope and limited ambiguity",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Any malformed provided index invalidates the provided index set, so output falls back to positional synthesis.

### Scenario 24: negative indexes synthesize positional indexes

**Input**

```json
[
  {
    "index": -1,
    "subtask": "Update helper A and adjust one caller."
  },
  {
    "index": 2,
    "subtask": "Update helper B and adjust one caller."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Update helper A and adjust one caller.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine update task with clear scope and limited ambiguity",
    "dispatchMode": "recommendation-only"
  },
  {
    "index": 1,
    "subtask": "Update helper B and adjust one caller.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine update task with clear scope and limited ambiguity",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Negative indexes are malformed because indexes must be non-negative integers.

### Scenario 25: non-integer numeric indexes synthesize positional indexes

**Input**

```json
[
  {
    "index": 1.5,
    "subtask": "Update helper A and adjust one caller."
  },
  {
    "index": 2,
    "subtask": "Update helper B and adjust one caller."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Update helper A and adjust one caller.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine update task with clear scope and limited ambiguity",
    "dispatchMode": "recommendation-only"
  },
  {
    "index": 1,
    "subtask": "Update helper B and adjust one caller.",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "routine update task with clear scope and limited ambiguity",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Numeric but non-integer indexes are malformed and trigger positional synthesis for the full array.

### Scenario 26: missing `subtask` field falls back as null

**Input**

```json
[
  {
    "index": 0
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "<null>",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "invalid or empty task description defaults to routine handling",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

If `subtask` is omitted entirely, the skill treats it like a missing value and still returns a valid fallback record.

### Scenario 27: non-object input item falls back from raw item type

**Input**

```json
[
  null,
  true
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "<null>",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "invalid or empty task description defaults to routine handling",
    "dispatchMode": "recommendation-only"
  },
  {
    "index": 1,
    "subtask": "<boolean>",
    "tier": "standard",
    "modelLabel": "GPT-5.3 Codex",
    "reason": "invalid or empty task description defaults to routine handling",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Non-object items are malformed inputs for this contract, so the skill still emits stable fallback records instead of failing.

### Scenario 28: malformed optional parent fields are ignored

**Input**

```json
[
  {
    "index": 0,
    "subtask": "Summarize this file.",
    "subagentType": 99,
    "dispatchConstraints": "strict"
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Summarize this file.",
    "tier": "basic",
    "modelLabel": "Clause Haiku 4.5",
    "reason": "task is narrow and low-risk",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Malformed optional parent fields must be ignored while classification proceeds from `subtask` alone.

### Scenario 29: availability is not checked

**Pressure Prompt**

```text
The runtime does not expose per-model availability checks. Produce routing output for this subtask array anyway and do not block on runtime inspection.
```

**Input**

```json
[
  {
    "subtask": "Trace behavior across several modules and propose a moderate refactor."
  }
]
```

**Expected Output**

```json
[
  {
    "index": 0,
    "subtask": "Trace behavior across several modules and propose a moderate refactor.",
    "tier": "advanced",
    "modelLabel": "GPT-5.4",
    "reason": "cross-file reasoning is required, but the task does not reach expert-level risk or diagnostic difficulty",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Availability is explicitly out of scope in this repo, so the skill still emits recommendation-only routing output.

### Scenario 30: unknown fields are ignored while valid indexes are preserved

**Input**

```json
[
  {
    "index": 10,
    "subtask": "Summarize file A.",
    "extraField": true,
    "subagentType": "explore",
    "dispatchConstraints": { "priority": "low" }
  },
  {
    "index": 12,
    "subtask": "Summarize file B.",
    "notes": "ignore me"
  }
]
```

**Expected Output**

```json
[
  {
    "index": 10,
    "subtask": "Summarize file A.",
    "tier": "basic",
    "modelLabel": "Clause Haiku 4.5",
    "reason": "task is narrow and low-risk",
    "dispatchMode": "recommendation-only"
  },
  {
    "index": 12,
    "subtask": "Summarize file B.",
    "tier": "basic",
    "modelLabel": "Clause Haiku 4.5",
    "reason": "task is narrow and low-risk",
    "dispatchMode": "recommendation-only"
  }
]
```

**Reasoning**

Unknown fields must be ignored, valid indexes must be preserved, and output order must remain stable.

## Pressure Prompts

### Pressure Prompt A: reject invented routing labels

```text
IMPORTANT: This is a real parent-skill scenario. You must return routing records for these subtasks.

Do not invent categories like small/fast, balanced-orchestrator, or high-reliability procedural model.
Use only the approved routing labels.
```

**Expected behavior**
- uses only `basic`, `standard`, `advanced`, `expert`, and `specialized`
- maps them only to the approved model labels

### Pressure Prompt B: reject envelope schemas

```text
IMPORTANT: The parent skill consumes your output mechanically.

Do not return wrapper objects such as {"status": ...}, do not add `route` or `error`, and do not add prose before or after the data.
Return only the routing array.
```

**Expected behavior**
- returns a raw JSON array only
- each item contains exactly the six approved fields

### Pressure Prompt C: reject dispatch takeover

```text
IMPORTANT: You are classifying only. The parent skill still owns dispatch.

Do not choose a new subagent type, do not rewrite the subtasks, and do not change parent-model inheritance.
```

**Expected behavior**
- returns routing records only
- leaves dispatch strategy, subagent type, and parent-model inheritance untouched

### Pressure Prompt D: reject top-level non-array misuse

```text
IMPORTANT: This skill's contract expects an array of subtask objects.

If the caller tries to pass a top-level scalar, object, or wrapper object directly, do not invent a normalization rule inside this skill. Treat that as caller misuse of the contract boundary.
```

**Expected behavior**
- the skill documentation makes clear that top-level normalization is caller responsibility
- validation does not invent repo-local normalization rules for non-array top-level input

## Review Checklist

- output is always an array, never a single object
- routing records contain exactly `index`, `subtask`, `tier`, `modelLabel`, `reason`, and `dispatchMode`
- invented tiers such as `small/fast` fail review
- extra fields such as `status`, `route`, and `error` fail review
- invalid inputs never cause a thrown failure or dropped record
- duplicate or malformed indexes synthesize positional indexes
- `dispatchMode` is always `recommendation-only`
- `specialized` is used for workflow sensitivity, not prestige
- the parent still dispatches the original subtasks unchanged

## Source of Truth

See `docs/superpowers/specs/2026-03-28-agent-selection-design.md`.
