"""
markdown_reporter.py — three-mode Markdown comparison report generator.

Produces a Markdown document comparing the results of three replay modes:
  - unrestricted
  - baseline_j5_block_skip
  - geometry_block

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
    """Generates a three-mode Markdown comparison report."""

    def generate(self, runs: list[dict]) -> str:
        """Produce a Markdown comparison report from three run summaries.

        Args:
            runs: List of at least 3 run-summary dicts.  Each dict must contain:
                  "mode", "total_steps", "steps_with_near_collision",
                  "steps_with_collision", "steps_with_motion_blocked"

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

        lines: list[str] = []

        lines.append("## Three-Mode Collision Comparison Report")
        lines.append("")
        lines.append(
            "| Mode | Total Steps | Near-Collision Steps | Collision Steps | Blocked Steps |"
        )
        lines.append(
            "| --- | --- | --- | --- | --- |"
        )
        for run in runs:
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
        """Select the best mode based on collision metrics and explain why."""
        # Primary: fewest collisions. Secondary: fewest near-collisions.
        # Tertiary: fewest blocked steps (least conservative).
        def score(run: dict) -> tuple:
            return (
                run["steps_with_collision"],
                run["steps_with_near_collision"],
                run["steps_with_motion_blocked"],
            )

        best = min(runs, key=score)
        worst = max(runs, key=lambda r: r["steps_with_collision"])

        lines = [
            f"**Best mode: `{best['mode']}`** "
            f"({best['steps_with_collision']} collision steps, "
            f"{best['steps_with_near_collision']} near-collision steps, "
            f"{best['steps_with_motion_blocked']} blocked steps).",
        ]

        if best["steps_with_collision"] < worst["steps_with_collision"]:
            lines.append(
                f"The geometry-aware strategy avoids "
                f"{worst['steps_with_collision'] - best['steps_with_collision']} "
                f"collision(s) compared to the least safe mode (`{worst['mode']}`)."
            )
        else:
            lines.append(
                "All modes produced equivalent collision outcomes for this scenario."
            )

        return " ".join(lines)
