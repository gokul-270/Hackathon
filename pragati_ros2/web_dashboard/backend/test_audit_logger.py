"""Tests for AuditLogger in audit_logger.py.

Validates:
- log writes valid JSON line
- get_recent returns entries in order
- log creates directory if missing
- concurrent logging doesn't corrupt file
- entries have correct fields
"""

import json
import threading

from backend.audit_logger import AuditLogger


# -----------------------------------------------------------------
# Tests
# -----------------------------------------------------------------


class TestAuditLogWrite:
    """Tests for AuditLogger.log writing."""

    def test_log_writes_valid_json_line(self, tmp_path):
        """Each log() call appends exactly one valid JSON line."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_file))

        logger.log("launch_arm", {"use_simulation": True}, "success")

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["action"] == "launch_arm"

    def test_log_creates_directory_if_missing(self, tmp_path):
        """log() creates parent directories if they don't exist."""
        log_file = tmp_path / "nested" / "deep" / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_file))

        logger.log("test_action", {}, "ok")

        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_multiple_logs_append(self, tmp_path):
        """Multiple log() calls append multiple lines."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_file))

        logger.log("action_1", {"a": 1}, "ok")
        logger.log("action_2", {"b": 2}, "fail")
        logger.log("action_3", {"c": 3}, "ok")

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3


class TestAuditLogEntryFields:
    """Tests for entry structure."""

    def test_entries_have_correct_fields(self, tmp_path):
        """Each entry has timestamp, action, params, result."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_file))

        logger.log("stop_vehicle", {"force": False}, "success")

        entry = json.loads(log_file.read_text().strip())
        assert "timestamp" in entry
        assert "action" in entry
        assert "params" in entry
        assert "result" in entry
        assert entry["action"] == "stop_vehicle"
        assert entry["params"] == {"force": False}
        assert entry["result"] == "success"

    def test_timestamp_is_iso8601(self, tmp_path):
        """Timestamp should be ISO 8601 format."""
        from datetime import datetime

        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_file))

        logger.log("check", {}, "ok")

        entry = json.loads(log_file.read_text().strip())
        # Should not raise
        datetime.fromisoformat(entry["timestamp"])


class TestAuditLogGetRecent:
    """Tests for AuditLogger.get_recent."""

    def test_get_recent_returns_entries_in_order(self, tmp_path):
        """get_recent returns entries oldest-first."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_file))

        for i in range(5):
            logger.log(f"action_{i}", {"i": i}, "ok")

        recent = logger.get_recent(n=5)
        assert len(recent) == 5
        assert recent[0]["action"] == "action_0"
        assert recent[4]["action"] == "action_4"

    def test_get_recent_limits_count(self, tmp_path):
        """get_recent(n=3) returns only last 3 entries."""
        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_file))

        for i in range(10):
            logger.log(f"action_{i}", {}, "ok")

        recent = logger.get_recent(n=3)
        assert len(recent) == 3
        assert recent[0]["action"] == "action_7"
        assert recent[2]["action"] == "action_9"

    def test_get_recent_empty_file(self, tmp_path):
        """get_recent on empty/nonexistent file returns empty list."""
        log_file = tmp_path / "empty.jsonl"
        logger = AuditLogger(log_path=str(log_file))

        recent = logger.get_recent(n=50)
        assert recent == []


class TestAuditLogConcurrency:
    """Tests for thread-safety."""

    def test_concurrent_logging_no_corruption(self, tmp_path):
        """Multiple threads logging concurrently don't corrupt file."""
        log_file = tmp_path / "concurrent.jsonl"
        logger = AuditLogger(log_path=str(log_file))
        num_threads = 10
        writes_per_thread = 20

        def writer(thread_id):
            for i in range(writes_per_thread):
                logger.log(
                    f"thread_{thread_id}",
                    {"i": i},
                    "ok",
                )

        threads = [
            threading.Thread(target=writer, args=(t,))
            for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == num_threads * writes_per_thread

        # Every line should be valid JSON
        for line in lines:
            entry = json.loads(line)
            assert "action" in entry
            assert "timestamp" in entry
