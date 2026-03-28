#!/usr/bin/env python3
"""
ROS2 Log Analyzer Tool for Pragati Robot — entry-point shim.

All logic has been moved to the ``log_analyzer`` package in the same
directory.  This file exists solely so that the RPi field-trial invocation

    python3 log_analyzer.py <log_directory> [flags]

continues to work unchanged.

Usage:
    python3 log_analyzer.py <log_directory>
    python3 log_analyzer.py <log_directory> --json          # JSON output
    python3 log_analyzer.py <log_directory> --verbose       # Include all details
    python3 log_analyzer.py <log_directory> --summary       # Quick summary only
    python3 log_analyzer.py <log_directory> --watch         # Watch mode (live)
    python3 log_analyzer.py <log_directory> --field-summary # Field-trial report
    python3 log_analyzer.py <log_directory> --csv events    # CSV export
    python3 log_analyzer.py <log_directory> --html          # HTML export
    python3 log_analyzer.py <log_directory> --compare /dir  # Session comparison

Author: Pragati Team
"""

import os
import sys

# Ensure the directory containing this file is on the path so that
# ``import log_analyzer`` resolves to the package sub-directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log_analyzer.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
