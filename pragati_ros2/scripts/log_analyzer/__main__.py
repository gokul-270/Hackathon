"""Allow running as ``python3 scripts/log_analyzer/`` or ``python3 -m scripts.log_analyzer``."""

import os
import sys

# When invoked as ``python3 scripts/log_analyzer/``, Python doesn't set up
# the parent package.  Add the repo root to sys.path so absolute imports work,
# then import the CLI entry-point via the fully-qualified package path.
_this_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(os.path.dirname(_this_dir))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from scripts.log_analyzer.cli import main  # noqa: E402

main()
