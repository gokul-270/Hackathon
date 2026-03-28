"""Source verification tests for blocking sleep annotations in web_dashboard backend.

Scans all Python files in the backend directory for time.sleep() calls that lack
a BLOCKING_SLEEP_OK annotation. This enforces the blocking-sleeps-error-handlers
change requirement that every blocking sleep must be explicitly justified.

The annotation can appear on the same line as the sleep or on the immediately
preceding line, e.g.:

    time.sleep(1.0)  # BLOCKING_SLEEP_OK: thread-loop pacing
    # BLOCKING_SLEEP_OK: serial port settle time
    time.sleep(0.01)
"""

import os
import re

import pytest

# backend/ directory (this file lives alongside the source files)
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

# Pattern that matches time.sleep(...) but not asyncio.sleep(...)
_TIME_SLEEP_RE = re.compile(r"(?<!asyncio\.)time\.sleep\s*\(")

# Annotation marker
_ANNOTATION_MARKER = "BLOCKING_SLEEP_OK"


def _get_python_files(directory, *, include_tests=False):
    """Collect .py files under *directory*, excluding caches and node_modules.

    Parameters
    ----------
    include_tests : bool
        If False (default), skip files matching ``test_*.py``.
    """
    files = []
    for root, dirs, filenames in os.walk(directory):
        # Prune directories we never want to descend into
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".pytest_cache")]
        for fname in sorted(filenames):
            if not fname.endswith(".py"):
                continue
            if not include_tests and fname.startswith("test_"):
                continue
            files.append(os.path.join(root, fname))
    return files


def _find_unannotated_sleeps(filepath):
    """Return list of ``(filepath, lineno, line_text)`` for unannotated sleeps.

    Handles multi-line sleep calls where black reformats:
        time.sleep(
            0.5
        )  # BLOCKING_SLEEP_OK: ...
    by scanning forward up to 5 lines for the annotation.
    """
    issues = []
    with open(filepath) as fh:
        lines = fh.readlines()

    for idx, line in enumerate(lines):
        stripped = line.strip()

        # Skip pure comments and import statements
        if stripped.startswith("#"):
            continue
        if stripped.startswith(("import ", "from ")):
            continue

        # Skip asyncio.sleep / await asyncio.sleep
        if "asyncio.sleep" in line or "await " in stripped:
            continue

        if not _TIME_SLEEP_RE.search(line):
            continue

        # Check for annotation on this line or the previous line
        has_annotation = _ANNOTATION_MARKER in line
        if idx > 0:
            has_annotation = has_annotation or _ANNOTATION_MARKER in lines[idx - 1]

        # For multi-line sleep calls, scan forward up to 5 lines.
        # black reformats time.sleep(val)  # comment into:
        #   time.sleep(
        #       val
        #   )  # comment
        if not has_annotation:
            sleep_indent = len(line) - len(line.lstrip())
            for j in range(1, 6):
                if idx + j >= len(lines):
                    break
                fwd_line = lines[idx + j]
                if _ANNOTATION_MARKER in fwd_line:
                    has_annotation = True
                    break
                fwd_stripped = fwd_line.strip()
                # Stop at blank lines
                if not fwd_stripped:
                    break
                # Stop if we hit a new statement at same/lesser indent
                # (but not closing parens or continuation lines)
                fwd_indent = len(fwd_line) - len(fwd_line.lstrip())
                if fwd_indent <= sleep_indent and not fwd_stripped.startswith((")", "]", "}", "#")):
                    break

        if not has_annotation:
            issues.append((filepath, idx + 1, stripped))

    return issues


# -- Tests -----------------------------------------------------------------


class TestBlockingSleepAnnotations:
    """Every time.sleep() in backend source code must carry BLOCKING_SLEEP_OK."""

    def test_all_source_sleeps_annotated(self):
        """Production source files must not have unannotated time.sleep()."""
        all_issues = []
        for filepath in _get_python_files(BACKEND_DIR, include_tests=False):
            all_issues.extend(_find_unannotated_sleeps(filepath))

        if all_issues:
            details = "\n".join(
                f"  {os.path.relpath(f, BACKEND_DIR)}:{ln}: {txt}" for f, ln, txt in all_issues
            )
            pytest.fail(
                f"Found {len(all_issues)} unannotated time.sleep() call(s) "
                f"in backend source files:\n{details}"
            )

    def test_all_test_sleeps_annotated(self):
        """Test files with time.sleep() should also be annotated."""
        all_issues = []
        test_files = [
            f
            for f in _get_python_files(BACKEND_DIR, include_tests=True)
            if os.path.basename(f).startswith("test_")
            and f != os.path.abspath(__file__)  # exclude this audit test
        ]
        for filepath in test_files:
            all_issues.extend(_find_unannotated_sleeps(filepath))

        if all_issues:
            details = "\n".join(
                f"  {os.path.relpath(f, BACKEND_DIR)}:{ln}: {txt}" for f, ln, txt in all_issues
            )
            pytest.fail(
                f"Found {len(all_issues)} unannotated time.sleep() call(s) "
                f"in test files:\n{details}"
            )


class TestAuditToolIntegrity:
    """Verify the audit helpers themselves work correctly."""

    def test_detects_unannotated_sleep(self, tmp_path):
        """A bare time.sleep() without annotation is caught."""
        py = tmp_path / "example.py"
        py.write_text("import time\ntime.sleep(1)\n")
        issues = _find_unannotated_sleeps(str(py))
        assert len(issues) == 1
        assert issues[0][1] == 2  # line 2

    def test_same_line_annotation_passes(self, tmp_path):
        """time.sleep() with inline annotation is not flagged."""
        py = tmp_path / "example.py"
        py.write_text("import time\n" "time.sleep(1)  # BLOCKING_SLEEP_OK: test\n")
        issues = _find_unannotated_sleeps(str(py))
        assert len(issues) == 0

    def test_preceding_line_annotation_passes(self, tmp_path):
        """time.sleep() with annotation on the line above is not flagged."""
        py = tmp_path / "example.py"
        py.write_text("import time\n" "# BLOCKING_SLEEP_OK: test reason\n" "time.sleep(1)\n")
        issues = _find_unannotated_sleeps(str(py))
        assert len(issues) == 0

    def test_asyncio_sleep_ignored(self, tmp_path):
        """asyncio.sleep() must not be flagged."""
        py = tmp_path / "example.py"
        py.write_text("import asyncio\n" "await asyncio.sleep(1)\n")
        issues = _find_unannotated_sleeps(str(py))
        assert len(issues) == 0

    def test_comment_line_ignored(self, tmp_path):
        """A comment mentioning time.sleep() is not flagged."""
        py = tmp_path / "example.py"
        py.write_text("# time.sleep(1) is bad\n")
        issues = _find_unannotated_sleeps(str(py))
        assert len(issues) == 0

    def test_import_line_ignored(self, tmp_path):
        """An import statement is not flagged even if it mentions sleep."""
        py = tmp_path / "example.py"
        py.write_text("import time\nfrom time import sleep\n")
        issues = _find_unannotated_sleeps(str(py))
        assert len(issues) == 0

    def test_multiline_sleep_annotation_passes(self, tmp_path):
        """Multi-line time.sleep() with annotation on closing paren passes."""
        py = tmp_path / "example.py"
        py.write_text(
            "import time\n" "time.sleep(\n" "    0.5\n" ")  # BLOCKING_SLEEP_OK: test reason\n"
        )
        issues = _find_unannotated_sleeps(str(py))
        assert len(issues) == 0
