# Contributing to Pragati ROS2

Thanks for helping keep the Pragati cotton-picking stack healthy! This guide captures the minimum
set of checks and expectations before opening a pull request. Pair it with the
[Documentation Maintenance Policy](docs/maintenance/DOC_MAINTENANCE_POLICY.md) and the
[Status Reality Matrix](docs/STATUS_REALITY_MATRIX.md) for day-to-day decisions.

## 🤝 Contributor Workflow

1. **Fork and branch**
   - Create feature branches from `main` (`git checkout -b feat/<topic>`).
2. **Keep builds green**
   - Run `colcon build` (or `./build.sh fast`) for the packages you touch.
   - Execute the targeted tests (`colcon test --packages-select <pkg>` or the
     relevant script in `scripts/validation/`).
3. **Link evidence**
   - Reference issues or tickets in the PR description.
   - Attach log snippets or paths inside `test_results/` when claiming behaviour changes.

## 📚 Documentation Truth Contract

Any change that touches high-level documentation (README badges, migration plans, validation
reports, package READMEs) must satisfy the following contract:

- **Single source of truth:** Align all claims with `docs/STATUS_REALITY_MATRIX.md`. Update the
  matrix in the same PR when you adjust readiness language, percentages, or badges.
- **Evidence-driven edits:** Link to tests, logs, or code paths that back the change. For hardware
  claims, capture the artefact under `test_results/` or reference a dated log in `~/pragati_test_results/`.
- **Inventory discipline:** Run `scripts/validation/doc_inventory_check.sh` to ensure the
  documentation snapshot stays in sync. Regenerate with `python3 scripts/doc_inventory.py docs --snapshot docs/doc_inventory_snapshot.json`
  if the check fails.
- **README ⇄ Matrix parity:** Run `python3 scripts/validation/readme_status_parity.py` and resolve any
  mismatched modules before merging. (The quick validation script already enforces this.)
- **Archive or delete stale artefacts:** When consolidating reports (e.g. audit summaries), move the
  originals into `docs/archive/<date>/` once their findings have been integrated into living docs.

Pull requests that update docs but skip these steps will be marked as changes requested.

## ✅ Required Pre-PR Checklist

- [ ] `colcon build --packages-select <touched packages>` (or `./build.sh fast`) succeeds.
- [ ] `colcon test --packages-select <touched packages>` (or relevant validation script) passes.
- [ ] `scripts/validation/quick_validation.sh` succeeds (this runs the doc inventory and README parity checks).
- [ ] `clang-format`, `ament_uncrustify`, or other linters applied as required by the packages you modified.

## 🧪 Recommended Validation Scripts

| Area | Command |
|------|---------|
| Full simulation sweep | `./scripts/validation/comprehensive_test_suite.sh` |
| Documentation inventory | `scripts/validation/doc_inventory_check.sh` |
| README ↔ Status Matrix parity | `python3 scripts/validation/readme_status_parity.py` |
| Motor control sanity | `./scripts/validation/motor/mg6010_smoke_test.sh` *(when hardware available)* |

> Tip: Use `SIMULATION_EXPECTS_MG6010=0` when running the comprehensive suite without hardware.

## 🛡️ Code Style & Commit Hygiene

- Follow existing formatting (`ament` linters for C++, `black`/`ruff` defaults for Python when present).
- Keep commits focused; split large changes into logical units.
- Reference issues in commit messages where appropriate (e.g. `[#123] Update cotton detection service`).

## 📦 Release & CI Notes

- The CI pipeline mirrors the checklist above. Failing the doc inventory or README parity checks is a
  hard stop.
- Upcoming enhancement: wiring the parity script into `pre_upload_verification.sh` so contributors
  catch drift before opening a PR (tracked in the Status Reality Matrix).

## 🙋 Need Help?

- Ping the Systems & Documentation team on Slack (`#pragati-docs`).
- File an issue with reproduction steps, desired outcome, and evidence (logs/tests).

Thanks again—accurate documentation and reproducible builds keep the robot honest! 🚀
