# CI Jazzy Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update GitHub Actions CI to target the project's actual ROS2 Jazzy and Ubuntu 24.04 environment so CI results stop reporting misleading Humble-era status.

**Architecture:** Keep the existing workflow structure and job behavior intact, and only align the runtime labels and environment selectors with the repo's supported platform. This is a narrow metadata/runtime update, not a CI redesign.

**Tech Stack:** GitHub Actions, YAML, ROS2 Jazzy, Ubuntu 24.04, Python 3.12

---

### Task 1: Inspect current workflow

**Files:**
- Modify: `.github/workflows/ci.yml`
- Test: `.github/workflows/ci.yml`

**Step 1: Read the existing workflow**

Confirm the current workflow uses Humble, Ubuntu 22.04, and Python 3.10.

**Step 2: Identify exact alignment fields**

Update only these fields:
- job display name
- `runs-on`
- ROS setup step label
- `required-ros-distributions`
- `source /opt/ros/.../setup.bash`
- Python version in Python-only jobs

**Step 3: Avoid broader CI changes**

Do not change:
- lint strictness
- artifact actions versions
- test scope
- pre-commit behavior

**Step 4: Commit scope guard**

Keep the patch limited to environment alignment only.

### Task 2: Update workflow to Jazzy and Noble

**Files:**
- Modify: `.github/workflows/ci.yml`
- Test: `.github/workflows/ci.yml`

**Step 1: Write the failing test**

Not applicable for CI metadata alignment. Verification is done by static inspection of the workflow file.

**Step 2: Run test to verify it fails**

Not applicable.

**Step 3: Write minimal implementation**

Apply these edits in `.github/workflows/ci.yml`:
- `Build & Test (ROS2 Humble)` -> `Build & Test (ROS2 Jazzy)`
- `ubuntu-22.04` -> `ubuntu-24.04` for all jobs
- `Setup ROS2 Humble` -> `Setup ROS2 Jazzy`
- `required-ros-distributions: humble` -> `required-ros-distributions: jazzy`
- `source /opt/ros/humble/setup.bash` -> `source /opt/ros/jazzy/setup.bash`
- `python-version: '3.10'` -> `python-version: '3.12'`

**Step 4: Run test to verify it passes**

Use targeted checks to confirm there are no remaining references to:
- `humble`
- `ubuntu-22.04`
- `3.10`

And confirm the expected replacements exist:
- `jazzy`
- `ubuntu-24.04`
- `3.12`

**Step 5: Commit**

Commit later with related CI/workflow changes if requested.
