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
    assert 'value="3"' in _HTML  # sequential_pick


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


# ---------------------------------------------------------------------------
# Group 7 – Mode dropdown: five options, correct labels
# ---------------------------------------------------------------------------

def test_html_mode_select_has_five_options():
    """Mode selector contains exactly 5 <option> elements (modes 0-4)."""
    from html.parser import HTMLParser

    class _OptionCounter(HTMLParser):
        def __init__(self):
            super().__init__()
            self._in_select = False
            self.count = 0

        def handle_starttag(self, tag, attrs):
            attrs_d = dict(attrs)
            if tag == "select" and attrs_d.get("id") == "run-mode-select":
                self._in_select = True
            if tag == "option" and self._in_select:
                self.count += 1

        def handle_endtag(self, tag):
            if tag == "select" and self._in_select:
                self._in_select = False

    counter = _OptionCounter()
    counter.feed(_HTML)
    assert counter.count == 5, f"Expected 5 mode options, found {counter.count}"


def test_html_mode_3_labeled_sequential_pick():
    """Mode 3 option text contains 'Sequential Pick'."""
    from html.parser import HTMLParser

    class _LabelFinder(HTMLParser):
        def __init__(self):
            super().__init__()
            self._capture = False
            self.label = ""

        def handle_starttag(self, tag, attrs):
            attrs_d = dict(attrs)
            if tag == "option" and attrs_d.get("value") == "3":
                self._capture = True

        def handle_data(self, data):
            if self._capture:
                self.label += data

        def handle_endtag(self, tag):
            if tag == "option" and self._capture:
                self._capture = False

    finder = _LabelFinder()
    finder.feed(_HTML)
    assert "Sequential Pick" in finder.label, (
        f"Mode 3 label should contain 'Sequential Pick', got: '{finder.label}'"
    )


def test_html_mode_4_labeled_smart_reorder():
    """Mode 4 option text contains 'Smart Reorder'."""
    from html.parser import HTMLParser

    class _LabelFinder(HTMLParser):
        def __init__(self):
            super().__init__()
            self._capture = False
            self.label = ""

        def handle_starttag(self, tag, attrs):
            attrs_d = dict(attrs)
            if tag == "option" and attrs_d.get("value") == "4":
                self._capture = True

        def handle_data(self, data):
            if self._capture:
                self.label += data

        def handle_endtag(self, tag):
            if tag == "option" and self._capture:
                self._capture = False

    finder = _LabelFinder()
    finder.feed(_HTML)
    assert "Smart Reorder" in finder.label, (
        f"Mode 4 label should contain 'Smart Reorder', got: '{finder.label}'"
    )
