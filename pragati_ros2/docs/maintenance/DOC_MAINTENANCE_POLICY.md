# Documentation Maintenance Policy

**Effective Date:** 2025-10-13  
**Owners:** Systems & Documentation Team (primary), Package Leads (reviewers)

---

## 1. Purpose

Keep source-of-truth documentation aligned with the live codebase by defining a repeatable review
process, explicit ownership, and automation aids. This policy covers all assets in `docs/`
(including archived materials) plus package-level READMEs inside `src/**`.

---

## 2. Scope & Ownership

| Area | Primary Owner | Review Cadence |
|------|---------------|----------------|
| `docs/` (status, guides, plans) | Systems & Documentation | Bi-weekly or before every release | 
| `docs/archive/` (historical evidence) | Systems & Documentation | Quarterly archive review |
| Package READMEs (`src/*/README.md`) | Respective package lead | With every feature PR |
| Status Reality Matrix | Systems lead + package lead sign-off | Weekly sync + before deployments |

### 2.1 Detailed Ownership Matrix (2025-10-14)

| Domain / Asset | Primary Owner | Backup | Review Cadence | Evidence / Tooling |
|----------------|---------------|--------|----------------|--------------------|
| Status Reality Matrix (`docs/STATUS_REALITY_MATRIX.md`) | Systems lead | Package leads (rotating) | Weekly sync + before deployments | Linked issues + `test_output/integration/` artefacts |
| Cross-reference Matrix (`docs/cross_reference_matrix.csv`) | Documentation lead | Cotton detection lead | Refresh alongside major feature merges | CSV regenerated per feature PR |
| Validation reports (`docs/validation/*.md`) | QA lead | Systems lead | After each validation run (simulation or hardware) | `test_output/integration/` folder; `~/pragati_test_output/integration/` logs |
| Hardware checklists (`docs/HARDWARE_TEST_CHECKLIST.md` et al.) | Hardware owner | QA lead | Before/after lab sessions | Bench logs; matrix hardware column |
| Build / performance guides (`docs/guides/software/*.md`) | Build & tooling lead | Systems & Documentation | Monthly or when build scripts change | `build.sh` outputs; CI metrics |
| Package READMEs (`src/*/README.md`) | Package leads | Systems & Documentation | With every feature PR | Linked code diffs + validation evidence |
| Archive hygiene (`docs/archive/**`) | Systems & Documentation | Release manager | Quarterly | `scripts/doc_inventory.py`; archive index |
| Automation scripts (`scripts/validation/*.sh`) | Tooling maintainer | QA lead | Quarterly + when automation changes | Script changelog; CI runbooks |

---

## 3. Review Cadence Checklist

### Weekly (or pre-release) sweep

1. Run the documentation inventory check:
   ```bash
   scripts/validation/doc_inventory_check.sh
   ```
   - Resolves to `python3 scripts/doc_inventory.py docs --verify docs/doc_inventory_snapshot.json`
   - If the check fails, update content and regenerate the snapshot:
     ```bash
     python3 scripts/doc_inventory.py docs --snapshot docs/doc_inventory_snapshot.json --table
     ```
2. Review `docs/STATUS_REALITY_MATRIX.md` and update any rows flagged ⚠️/🔴 with relevant evidence or
   backlog references.
3. Confirm that top-level README badges still map to the matrix.
4. Validate that new features/bug fixes reference the appropriate docs (package README + interface
   spec, as applicable).

### Monthly (or after major milestones)

1. Re-run the inventory snapshot and archive the JSON in the release notes if significant changes
   occurred (optional but recommended).
2. Review `docs/archive/` for any audit materials that should be promoted to living docs or retired.
3. Ensure hardware validation evidence in `test_output/integration/` matches the claims in the matrix and top
   level docs.

---

## 4. Change Control Expectations

- **Every documentation PR** must reference the corresponding work item (issue/JIRA) and list the
  specific files touched in the PR description.
- When altering high-level status claims (README badges, master strategy, migration guides), update
  the Status Reality Matrix in the same PR.
- For package README updates, include a link to the relevant code diff or test evidence.
- Deprecated documents should be either deleted (preferable) or renamed with an `_ARCHIVE.md`
  suffix and linked from `docs/archive/README.md`.

---

## 5. Automation Hooks

- `scripts/doc_inventory.py` — Generates JSON inventory and optional table output.
  - Primary snapshot stored at `docs/doc_inventory_snapshot.json`.
  - CI/pre-upload target: `scripts/validation/doc_inventory_check.sh`.
  - Included in the automation sweep via `scripts/validation/quick_validation.sh` to guard against drift.
- Future work: integrate the check into the existing `scripts/validation/pre_upload_verification.sh`
  pipeline (tracked in STATUS_REALITY_MATRIX.md).

---

## 6. Sign-off Checklist (per review cycle)

- [ ] Inventory check passes (`scripts/validation/doc_inventory_check.sh`).
- [ ] Status Reality Matrix reconciled with latest code/test evidence.
- [ ] README badges validated against the matrix.
- [ ] Outstanding ⚠️/🔴 rows either updated or assigned to backlog owners.
- [ ] Documentation backlog (Section 6 of `docs/cleanup/DOCUMENTATION_RECONCILIATION_PLAN.md`)
      reviewed and reprioritised if needed.

---

## 7. Contacts

- Primary: Documentation Lead (current: @systems-team)  
- Backup: Package leads listed in `docs/MASTER_MIGRATION_STRATEGY.md`
