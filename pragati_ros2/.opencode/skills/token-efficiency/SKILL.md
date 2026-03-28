---
name: token-efficiency
description: Enforce token-efficient behavior during OpenSpec workflows and general coding. Load alongside any OpenSpec skill to reduce redundant reads and output waste.
license: MIT
metadata:
  author: pragati
  version: "1.0"
---

# Token Efficiency Skill

## When This Applies

This skill MUST be followed alongside any OpenSpec skill (apply, verify, archive, ff,
continue, explore, sync-specs). Its rules are mandatory and override default behavior
where conflicts exist.

## Mandatory Rules

### 1. Context Deduplication

Before reading ANY file, check if its content already exists in the conversation:
- Was it read by a prior skill invocation in this session?
- Was it returned as part of `openspec instructions` output?
- Was it created/written by you earlier in this conversation?

If YES to any: use the existing content. Do NOT re-read the file.

### 2. Selective Reading

- **tasks.md**: To check completion status, grep for `- [` instead of reading the full
  file. Only read the full file when you need task descriptions for implementation context.
- **specs/*/spec.md**: To check requirement coverage, grep for `### Requirement:` headers.
  Only read full spec when implementing or verifying specific requirements.
- **proposal.md**: Almost never needs re-reading during apply/verify. Skip unless a task
  explicitly references proposal context.
- **design.md**: Read only the Decisions section when implementing. Skip Context/Goals
  sections unless they contain implementation-relevant constraints.

### 3. Output Discipline

- Never display full artifact content to the terminal unless the user explicitly asks
  (e.g., "show me the proposal").
- Progress updates should be one-liners: "Task 3/7 complete: <10-word description>"
- Verification reports: show the summary scorecard table and CRITICAL issues only.
  Show WARNING/SUGGESTION details only if the user asks for the full report.
- Do NOT echo back file content after writing it. A one-line confirmation is sufficient.

### 4. TodoWrite Efficiency

- Batch completions: after finishing a group of related tasks, mark them all done in
  one TodoWrite call rather than one call per task.
- Use compact descriptions (under 10 words per item).
- When a skill doesn't explicitly call for TodoWrite but has >5 tracked steps, use it
  with the batching rule.

### 5. Subagent Delegation

- **Verify step in opsx-apply**: ALWAYS dispatch as a Task subagent. The verify skill
  re-reads all artifacts and searches the codebase -- this must not happen in the main
  implementation context.
- **Archive sync assessment**: When opsx-archive reads delta specs to assess sync state,
  pass that content to the sync skill rather than having sync re-read the same files.
  Include relevant content in the subagent prompt.

### 6. Skill Loading Guards

- Never load openspec-onboard unless the user explicitly asks for onboarding/tutorial.
- Never load openspec-explore unless the user explicitly invokes /opsx-explore.
- Do not chain multiple OpenSpec skills in one session. Prefer: skill -> commit -> new
  session -> next skill.

### 7. CLI Output Reuse

- `openspec status` and `openspec instructions` return JSON with context, templates,
  and file paths. Extract and use what you need from the JSON -- do not re-read files
  that the CLI output already provided content for.
- In opsx-ff, track completed artifacts locally instead of re-running `openspec status`
  after every artifact creation.
