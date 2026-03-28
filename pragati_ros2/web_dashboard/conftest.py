"""Root conftest — ensures web_dashboard/ is on sys.path for imports."""

import sys
from pathlib import Path

# Add web_dashboard/ to sys.path so `from backend.X import Y` works
_dir = str(Path(__file__).parent)
if _dir not in sys.path:
    sys.path.insert(0, _dir)
