# Spec: Multi Cotton Management

## Purpose

Defines how multiple cotton targets are managed during pick operations, including spawning, picking, status tracking, and Gazebo model lifecycle.

## Requirements

### Requirement: Sequential pick all cottons

The `POST /api/cotton/pick-all` endpoint SHALL compute joint values for all cottons with status `"spawned"` grouped by arm and return the grouped data immediately (see pick-compute-api spec). The frontend SHALL then animate all arms in parallel via `Promise.all()`, picking cottons sequentially within each arm using the frontend-driven animation (see frontend-pick-animation spec). After each cotton's J5-extend step, the frontend SHALL call `POST /api/cotton/{name}/mark-picked` to update the cotton's status from `"spawned"` to `"picked"`. Cotton models SHALL NOT be deleted from Gazebo after pick; only status is updated.

#### Scenario: Pick 3 cottons with frontend-driven animation

- **WHEN** 3 cottons are spawned and `POST /api/cotton/pick-all` is called
- **THEN** the backend returns per-arm grouped joint values with `status: "ready"`
- **AND** the frontend runs `executePickAnimation()` for each cotton
- **AND** each cotton's status changes from `"spawned"` to `"picked"` via `POST /api/cotton/{name}/mark-picked` after J5-extend
- **AND** all 3 cotton Gazebo models still exist in the scene

#### Scenario: Skip already-picked cottons

- **WHEN** cotton_0 has status `"picked"` and cotton_1 has status `"spawned"`
- **AND** `POST /api/cotton/pick-all` is called
- **THEN** only cotton_1 appears in the backend response (cotton_0 is excluded)

#### Scenario: No cottons to pick

- **WHEN** all cottons have status `"picked"` or no cottons exist
- **AND** `POST /api/cotton/pick-all` is called
- **THEN** the endpoint returns `{"status": "nothing_to_pick"}`
- **AND** no arm motion occurs

### Requirement: Cotton persists after pick

The cotton's status transition to `"picked"` SHALL only occur when the frontend explicitly calls `POST /api/cotton/{name}/mark-picked`. The backend SHALL NOT change cotton status during the compute-only `/api/cotton/pick` or `/api/cotton/pick-all` calls. The Gazebo model SHALL persist regardless of pick status.

#### Scenario: Cotton status unchanged by compute endpoint

- **WHEN** `POST /api/cotton/pick` is called for cotton_0
- **THEN** cotton_0's status remains `"spawned"` in the backend
- **AND** the status only changes to `"picked"` when `POST /api/cotton/cotton_0/mark-picked` is subsequently called

#### Scenario: Aborted animation leaves cotton spawned

- **WHEN** `executePickAnimation()` is aborted before step 3 (J5 extend)
- **THEN** `mark-picked` is never called
- **AND** cotton_0 remains with status `"spawned"`
- **AND** the cotton can be picked again by retrying

### Requirement: Pick-all status endpoint (REMOVED)
**Reason**: The `GET /api/cotton/pick-status` endpoint is removed because the frontend drives the animation directly and knows its own state. No backend polling is needed. The frontend updates its status display inline during the animation.
**Migration**: Frontend `cottonPickAll()` updates the status div text at each animation step for each arm. Progress is tracked by counting completed cottons vs total in the frontend.
