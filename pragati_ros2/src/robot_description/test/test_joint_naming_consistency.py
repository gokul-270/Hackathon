"""Test that joint names are consistent (no spaces) across robot_description files.

Verifies spec scenario: 'No joint names with spaces after fix'
- Grep all .urdf, .xacro, .yaml files for 'joint N' (with space)
- Zero matches expected
"""

import pathlib
import re

import pytest

# Root of robot_description package
PKG_DIR = pathlib.Path(__file__).resolve().parent.parent

# Pattern matching joint names with spaces: "joint 2", "joint 3", etc.
# Excludes comment-only lines (lines starting with optional whitespace + #)
SPACED_JOINT_RE = re.compile(r"joint\s+[2-7]")
COMMENT_LINE_RE = re.compile(r"^\s*#")

# File extensions to check
EXTENSIONS = {".urdf", ".xacro", ".yaml", ".yml"}


def _collect_files():
    """Collect all URDF, xacro, and YAML files in the package."""
    files = []
    for ext in EXTENSIONS:
        files.extend(PKG_DIR.rglob(f"*{ext}"))
    # Exclude backup files
    return [f for f in files if ".backup" not in f.name]


def _find_spaced_joints(filepath):
    """Return list of (line_number, line_text) with spaced joint names."""
    violations = []
    with open(filepath, "r") as f:
        for i, line in enumerate(f, start=1):
            # Skip comment-only lines
            if COMMENT_LINE_RE.match(line):
                continue
            if SPACED_JOINT_RE.search(line):
                violations.append((i, line.rstrip()))
    return violations


class TestJointNamingConsistency:
    """Verify no functional files use 'joint N' (with space) naming."""

    def test_no_spaced_joint_names_in_urdf_xacro_yaml(self):
        """All .urdf, .xacro, .yaml files must use 'jointN' (no space)."""
        files = _collect_files()
        assert len(files) > 0, "No URDF/xacro/YAML files found — test setup error"

        all_violations = {}
        for filepath in files:
            violations = _find_spaced_joints(filepath)
            if violations:
                rel = filepath.relative_to(PKG_DIR)
                all_violations[str(rel)] = violations

        if all_violations:
            msg_parts = ["Found joint names with spaces (should be 'jointN'):"]
            for fname, viols in sorted(all_violations.items()):
                for line_no, line_text in viols:
                    msg_parts.append(f"  {fname}:{line_no}: {line_text}")
            pytest.fail("\n".join(msg_parts))

    def test_canonical_joint_names_present(self):
        """At least one file must contain canonical 'joint2' naming."""
        files = _collect_files()
        canonical_re = re.compile(r"joint[2-7]")
        found = False
        for filepath in files:
            with open(filepath, "r") as f:
                if canonical_re.search(f.read()):
                    found = True
                    break
        assert found, "No canonical 'jointN' names found — expected at least one"
