"""Audit logger for control action tracking.

Provides an append-only JSON-lines logger for recording all control
actions (launch, stop, E-stop, etc.) with timestamps and results.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class AuditLogger:
    """Append-only JSON-lines audit log.

    Each entry contains:
    - timestamp: ISO 8601 UTC
    - action: descriptive action name
    - params: action parameters dict
    - result: outcome string
    """

    def __init__(self, log_path: Optional[str] = None):
        if log_path is None:
            log_path = str(
                Path(__file__).parent.parent / "data" / "audit.jsonl"
            )
        self._log_path = Path(log_path)
        self._lock = threading.Lock()

    def log(self, action: str, params: Dict[str, Any], result: str) -> None:
        """Append one JSON-line entry to the log file.

        Creates parent directories if needed.  Thread-safe.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "params": params,
            "result": result,
        }
        line = json.dumps(entry, separators=(",", ":")) + "\n"

        with self._lock:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line)

    def get_recent(self, n: int = 50) -> List[Dict[str, Any]]:
        """Return the last *n* log entries, oldest first.

        Returns an empty list if the file doesn't exist or is empty.
        """
        if not self._log_path.exists():
            return []

        with self._lock:
            with open(self._log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        entries: List[Dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        return entries[-n:]
