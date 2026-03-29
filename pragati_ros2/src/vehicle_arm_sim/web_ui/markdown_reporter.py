"""
markdown_reporter.py — three- and four-mode Markdown comparison report generator.

Produces a Markdown document comparing the results of replay modes:
  - unrestricted
  - baseline_j5_block_skip
  - geometry_block
  - sequential_pick     (Release 3, replaces overlap_zone_wait)

Usage
-----
    from markdown_reporter import MarkdownReporter

    reporter = MarkdownReporter()
    md = reporter.generate([unrestricted_run, baseline_run, geometry_run])
    print(md)
"""
from __future__ import annotations

_REQUIRED_KEYS = {"mode", "total_steps", "steps_with_near_collision",
                  "steps_with_collision", "steps_with_motion_blocked"}


class MarkdownReporter:
    """Generates a three- or four-mode Markdown comparison report."""

    def generate(self, runs: list[dict]) -> str:
        """Produce a Markdown comparison report from three or four run summaries.

        Args:
            runs: List of 3 or 4 run-summary dicts.  Each dict must contain:
                  "mode", "total_steps", "steps_with_near_collision",
                  "steps_with_collision", "steps_with_motion_blocked".
                  Optional: "steps_with_blocked_or_skipped" (for four-mode reports).

        Returns:
            Markdown string with a heading, comparison table, and recommendation.

        Raises:
            ValueError: If fewer than 3 runs are supplied or a required key is missing.
        """
        if len(runs) < 3:
            raise ValueError(
                f"Expected at least 3 run dicts for a three-mode report, got {len(runs)}"
            )
        for i, run in enumerate(runs):
            missing = _REQUIRED_KEYS - set(run.keys())
            if missing:
                raise ValueError(
                    f"Run {i} is missing required keys: {sorted(missing)}"
                )

        four_mode = len(runs) >= 4

        lines: list[str] = []

        if four_mode:
            lines.append("## Four-Mode Collision Comparison Report")
        else:
            lines.append("## Three-Mode Collision Comparison Report")
        lines.append("")

        if four_mode:
            lines.append(
                "| Mode | Total Steps | Near-Collision Steps | Collision Steps"
                " | Blocked Steps | Blocked+Skipped |"
            )
            lines.append(
                "| --- | --- | --- | --- | --- | --- |"
            )
        else:
            lines.append(
                "| Mode | Total Steps | Near-Collision Steps | Collision Steps | Blocked Steps |"
            )
            lines.append(
                "| --- | --- | --- | --- | --- |"
            )

        for run in runs:
            blocked_or_skipped = run.get(
                "steps_with_blocked_or_skipped",
                run["steps_with_motion_blocked"],
            )
            if four_mode:
                lines.append(
                    f"| {run['mode']} "
                    f"| {run['total_steps']} "
                    f"| {run['steps_with_near_collision']} "
                    f"| {run['steps_with_collision']} "
                    f"| {run['steps_with_motion_blocked']} "
                    f"| {blocked_or_skipped} |"
                )
            else:
                lines.append(
                    f"| {run['mode']} "
                    f"| {run['total_steps']} "
                    f"| {run['steps_with_near_collision']} "
                    f"| {run['steps_with_collision']} "
                    f"| {run['steps_with_motion_blocked']} |"
                )

        lines.append("")
        lines.append("### Recommendation")
        lines.append("")
        recommendation = self._recommend(runs)
        lines.append(recommendation)
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _recommend(self, runs: list[dict]) -> str:
        """Select the best mode based on the spec-driven decision tree.

        Decision tree:
          PRIMARY:   prefer zero actual collisions (steps_with_collision == 0)
          SECONDARY: among zero-collision modes, prefer highest successful picks
                     (total_steps - steps_with_blocked_or_skipped)
          FALLBACK:  if no zero-collision mode exists, fewest collision steps
                     (then fewest near-collisions, then fewest blocked).
        """
        zero_collision_runs = [r for r in runs if r["steps_with_collision"] == 0]

        if zero_collision_runs:
            # Among zero-collision modes, pick highest successful picks
            def success_count(run: dict) -> int:
                blocked_or_skipped = run.get(
                    "steps_with_blocked_or_skipped",
                    run["steps_with_motion_blocked"],
                )
                return run["total_steps"] - blocked_or_skipped

            best = max(zero_collision_runs, key=success_count)
        else:
            # Fallback: fewest collisions → fewest near-collisions → fewest blocked
            def fallback_score(run: dict) -> tuple:
                return (
                    run["steps_with_collision"],
                    run["steps_with_near_collision"],
                    run["steps_with_motion_blocked"],
                )

            best = min(runs, key=fallback_score)

        worst = max(runs, key=lambda r: r["steps_with_collision"])
        blocked_or_skipped = best.get(
            "steps_with_blocked_or_skipped",
            best["steps_with_motion_blocked"],
        )

        lines = [
            f"**Best mode: `{best['mode']}`** "
            f"({best['steps_with_collision']} collision steps, "
            f"{best['steps_with_near_collision']} near-collision steps, "
            f"{blocked_or_skipped} blocked+skipped steps).",
        ]

        if best["steps_with_collision"] < worst["steps_with_collision"]:
            lines.append(
                f"`{best['mode']}` avoids "
                f"{worst['steps_with_collision'] - best['steps_with_collision']} "
                f"collision(s) compared to the least safe mode (`{worst['mode']}`)."
            )
        else:
            lines.append(
                "All modes produced equivalent collision outcomes for this scenario."
            )

        return " ".join(lines)
