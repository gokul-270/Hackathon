#!/usr/bin/env python3
"""
Group 1 – UI controls tests.

These tests verify that the HTML and JS source contain the required
DOM elements and wiring for:
  - mode selector
  - scenario JSON file input / built-in scenario selector
  - Start Run button
"""

import re
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent
_HTML = (_WEB_DIR / "testing_ui.html").read_text()
_JS = (_WEB_DIR / "testing_ui.js").read_text()


# ---------------------------------------------------------------------------
# Mode selector
# ---------------------------------------------------------------------------

def test_html_has_mode_select_element():
    """HTML contains a <select> element for collision-avoidance mode."""
    assert 'id="run-mode-select"' in _HTML


def test_html_mode_select_has_all_four_modes():
    """Mode selector includes all four modes as <option> values."""
    assert 'value="0"' in _HTML  # unrestricted
    assert 'value="1"' in _HTML  # baseline_j5_block_skip
    assert 'value="2"' in _HTML  # geometry_block
    assert 'value="3"' in _HTML  # overlap_zone_wait


# ---------------------------------------------------------------------------
# Scenario selector
# ---------------------------------------------------------------------------

def test_html_has_scenario_select_element():
    """HTML contains a scenario selector (built-in packs or file upload)."""
    assert 'id="run-scenario-select"' in _HTML


def test_html_has_scenario_file_input():
    """HTML provides a file input for uploading a custom scenario JSON."""
    assert 'id="run-scenario-file"' in _HTML
    assert 'type="file"' in _HTML


# ---------------------------------------------------------------------------
# Start Run button
# ---------------------------------------------------------------------------

def test_html_has_start_run_button():
    """HTML contains a Start Run button."""
    assert 'id="run-start-btn"' in _HTML


def test_js_start_run_button_wired():
    """JS wires the Start Run button to a handler."""
    assert "run-start-btn" in _JS


# ---------------------------------------------------------------------------
# Reports area
# ---------------------------------------------------------------------------

def test_html_has_report_download_area():
    """HTML contains links or buttons to download JSON and Markdown reports."""
    assert 'id="run-report-json-link"' in _HTML
    assert 'id="run-report-md-link"' in _HTML


def test_html_has_run_status_element():
    """HTML has a status/progress display for the run."""
    assert 'id="run-status-text"' in _HTML
