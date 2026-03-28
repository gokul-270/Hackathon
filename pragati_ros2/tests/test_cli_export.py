"""
tests/test_cli_export.py

Tests for CLI flags and CSV export functionality.

Tasks: 21.13–21.14
"""

import json
from pathlib import Path
from unittest.mock import patch

from log_analyzer import exporters as _exp
from log_analyzer.analyzer import ROS2LogAnalyzer
from log_analyzer.cli import main


# ---------------------------------------------------------------------------
# task 21.13 — CSV export
# ---------------------------------------------------------------------------


class TestCSVExport:
    def test_events_csv_created(self, log_dir_with_files):
        """export_csv_events creates a CSV file in the output directory."""
        a = ROS2LogAnalyzer(str(log_dir_with_files))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass
        # Manually add a pick so CSV has content
        a.events.picks.append(
            {
                "_ts": 1700000002.0,
                "success": True,
                "cotton_id": "c1",
                "pick_id": 1,
            }
        )
        out = _exp.export_csv_events(a, log_dir_with_files)
        assert out.exists()
        text = out.read_text()
        assert "pick" in text.lower()

    def test_metrics_csv_created(self, log_dir_with_files):
        """export_csv_metrics creates a CSV file."""
        a = ROS2LogAnalyzer(str(log_dir_with_files))
        with patch("builtins.print"):
            try:
                a.analyze()
            except SystemExit:
                pass
        out = _exp.export_csv_metrics(a, log_dir_with_files)
        assert out.exists()


# ---------------------------------------------------------------------------
# task 21.14 — CLI flag compatibility
# ---------------------------------------------------------------------------


class TestCLIFlagCompatibility:
    def test_json_flag_produces_json(self, log_dir_with_files, capsys):
        """--json flag still produces valid JSON output."""
        with patch(
            "sys.argv",
            ["log_analyzer.py", str(log_dir_with_files), "--json"],
        ):
            main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "log_directory" in data

    def test_summary_flag_no_crash(self, log_dir_with_files, capsys):
        """--summary flag runs without error."""
        with patch(
            "sys.argv",
            ["log_analyzer.py", str(log_dir_with_files), "--summary"],
        ):
            main()

    def test_timeline_flag_no_crash(self, log_dir_with_files, capsys):
        """--timeline flag runs without error."""
        with patch(
            "sys.argv",
            ["log_analyzer.py", str(log_dir_with_files), "--timeline"],
        ):
            main()

    def test_output_flag_saves_file(self, log_dir_with_files, tmp_path):
        """--output flag saves report to file."""
        out_file = str(tmp_path / "report.txt")
        with patch(
            "sys.argv",
            [
                "log_analyzer.py",
                str(log_dir_with_files),
                "--output",
                out_file,
            ],
        ):
            main()
        assert Path(out_file).exists()

    def test_new_flags_dont_break_existing(self, log_dir_with_files, capsys):
        """New flags (--field-summary) don't crash when used alone."""
        with patch(
            "sys.argv",
            [
                "log_analyzer.py",
                str(log_dir_with_files),
                "--field-summary",
            ],
        ):
            main()
