---
name: openspec-apply-change
description: Implement tasks from an OpenSpec change. Use when the user wants to start implementing, continue implementation, or work through tasks.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.1.1"
---

Implement tasks from an OpenSpec change.

**Input**: Optionally specify a change name. If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

**Steps**

1. **Select the change**

   If a name is provided, use it. Otherwise:
   - Infer from conversation context if the user mentioned a change
   - Auto-select if only one active change exists
   - If ambiguous, run `openspec list --json` to get available changes and use the **AskUserQuestion tool** to let the user select

   Always announce: "Using change: <name>" and how to override (e.g., `/opsx-apply <other>`).

2. **Check status to understand the schema**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse the JSON to understand:
   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - Which artifact contains the tasks (typically "tasks" for spec-driven, check status for others)

3. **Get apply instructions**

   ```bash
   openspec instructions apply --change "<name>" --json
   ```

   This returns:
   - Context file paths (varies by schema - could be proposal/specs/design/tasks or spec/tests/implementation/docs)
   - Progress (total, complete, remaining)
   - Task list with status
   - Dynamic instruction based on current state

   **Handle states:**
   - If `state: "blocked"` (missing artifacts): show message, suggest using openspec-continue-change
   - If `state: "all_done"`: congratulate, suggest archive
   - Otherwise: proceed to implementation

4. **Read context files**

   Read the files listed in `contextFiles` from the apply instructions output.
   The files depend on the schema being used:
   - **spec-driven**: proposal, specs, design, tasks
   - Other schemas: follow the contextFiles from CLI output

   **Context deduplication**: Before reading each file, check if its content is already
   in the conversation from a prior skill invocation or earlier read. Skip files already
   in context. For tasks.md, if you only need completion status, grep for `- [` instead
   of reading the full file. For proposal.md, skip unless a task explicitly references it.

5. **Show current progress**

   Display:
   - Schema being used
   - Progress: "N/M tasks complete"
   - Remaining tasks overview
   - Dynamic instruction from CLI

6. **Implement tasks (loop until done or blocked)**

   For each pending task:
   - Show which task is being worked on
   - Make the code changes required
   - Keep changes minimal and focused
   - Mark task complete in the tasks file: `- [ ]` → `- [x]`
   - Continue to next task

   **Pause if:**
   - Task is unclear → ask for clarification
   - Implementation reveals a design issue → suggest updating artifacts
   - Error or blocker encountered → report and wait for guidance
   - User interrupts

7. **On completion, verify before committing**

   **Verify checkpoint (MANDATORY when all tasks are done):** Before committing, dispatch
   `openspec-verify-change` as a **Task subagent** to avoid re-reading all artifacts in
   the main context. The subagent will return a verification report with a summary scorecard
   and any CRITICAL/WARNING issues. Fix all CRITICAL issues found by verify. Then commit
   the clean result -- not implementation first, fixes second.

   Skip verify only when pausing mid-implementation (not all tasks done) — in that case, commit directly to avoid losing work.

8. **Archive and commit (atomic sequence)**

   **When all tasks are done and verify passes**, the remaining steps are one atomic sequence:

   1. **Fix** all CRITICAL and actionable WARNING issues from verify
   2. **Archive** the change: sync delta specs to main specs, move change to `openspec/changes/archive/YYYY-MM-DD-<name>/`
   3. **Commit** everything — implementation, fixes, spec sync, and archive — as one clean commit:
   ```bash
   git add -A
   git commit -m "chore: sync specs and archive <change-name> change"
   ```

   **When pausing mid-implementation** (not all tasks done), commit directly without archive:
   ```bash
   git add -A
   git commit -m "feat: implement <change-name> tasks N-M (<brief description>)"
   ```

   Commit messages should reflect what was implemented, not just "completed tasks".

   Do NOT commit after every individual task -- wait until a session's work is done or you are pausing. One clean commit per implementation session.

   If the commit fails (e.g., pre-commit hooks), fix the issue and retry. Do NOT skip this step.

   Display:
   - Tasks completed this session
   - Overall progress: "N/M tasks complete"
   - Git commit confirmation
   - If all done: confirm archive location
   - If paused: explain why and wait for guidance

**Output During Implementation**

Keep output minimal. Do NOT display full artifact content. Progress should be one-liners.

```
## Implementing: <change-name> (schema: <schema-name>)

Working on task 3/7: <task description>
[...implementation happening...]
✓ Task complete

Working on task 4/7: <task description>
[...implementation happening...]
✓ Task complete
```

**Output On Completion**

```
## Implementation Complete

**Change:** <change-name>
**Schema:** <schema-name>
**Progress:** 7/7 tasks complete ✓

### Completed This Session
- [x] Task 1
- [x] Task 2
...

All tasks complete! Ready to archive this change.
```

**Output On Pause (Issue Encountered)**

```
## Implementation Paused

**Change:** <change-name>
**Schema:** <schema-name>
**Progress:** 4/7 tasks complete

### Issue Encountered
<description of the issue>

**Options:**
1. <option 1>
2. <option 2>
3. Other approach

What would you like to do?
```

**Guardrails**
- Keep going through tasks until done or blocked
- Always read context files before starting (from the apply instructions output)
- If task is ambiguous, pause and ask before implementing
- If implementation reveals issues, pause and suggest artifact updates
- Keep code changes minimal and scoped to each task
- Update task checkbox immediately after completing each task
- Pause on errors, blockers, or unclear requirements - don't guess
- Use contextFiles from CLI output, don't assume specific file names
- **ALWAYS commit work before stopping a session** - never leave implemented code uncommitted

**Fluid Workflow Integration**

This skill supports the "actions on a change" model:

- **Can be invoked anytime**: Before all artifacts are done (if tasks exist), after partial implementation, interleaved with other actions
- **Allows artifact updates**: If implementation reveals design issues, suggest updating artifacts - not phase-locked, work fluidly
