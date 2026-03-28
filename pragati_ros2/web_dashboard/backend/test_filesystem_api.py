"""Tests for the filesystem browser API."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.filesystem_api import (
    _build_allowed_roots,
    _is_path_allowed,
    _ALLOWED_ROOTS,
    filesystem_router,
    initialize_filesystem_api,
)


@pytest.fixture(autouse=True)
def _setup_allowed_roots(tmp_path):
    """Set up allowed roots to include tmp_path for testing."""
    import backend.filesystem_api as mod

    original = mod._ALLOWED_ROOTS[:]
    mod._ALLOWED_ROOTS = [tmp_path.resolve()]
    yield
    mod._ALLOWED_ROOTS = original


@pytest.fixture()
def client():
    """Create a FastAPI test client with the filesystem router."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(filesystem_router)
    return TestClient(app)


class TestPathTraversalProtection:
    """Test that path traversal attacks are rejected."""

    def test_traversal_with_dotdot_rejected(
        self, client, tmp_path
    ):
        evil_path = str(tmp_path / ".." / ".." / "etc" / "passwd")
        resp = client.get(
            "/api/filesystem/browse", params={"path": evil_path}
        )
        assert resp.status_code == 403

    def test_path_outside_allowlist_rejected(self, client):
        resp = client.get(
            "/api/filesystem/browse",
            params={"path": "/usr/bin"},
        )
        assert resp.status_code == 403

    def test_allowed_path_succeeds(self, client, tmp_path):
        resp = client.get(
            "/api/filesystem/browse",
            params={"path": str(tmp_path)},
        )
        assert resp.status_code == 200


class TestNormalBrowsing:
    """Test normal directory listing."""

    def test_lists_files_and_dirs(self, client, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("hello")

        resp = client.get(
            "/api/filesystem/browse",
            params={"path": str(tmp_path)},
        )
        assert resp.status_code == 200
        data = resp.json()
        names = [e["name"] for e in data["entries"]]
        assert "subdir" in names
        assert "file.txt" in names

    def test_dirs_first_sorting(self, client, tmp_path):
        (tmp_path / "zz_dir").mkdir()
        (tmp_path / "aa_file.txt").write_text("hello")

        resp = client.get(
            "/api/filesystem/browse",
            params={"path": str(tmp_path)},
        )
        data = resp.json()
        # Directory should come before file
        types = [e["type"] for e in data["entries"]]
        assert types == ["directory", "file"]

    def test_dirs_only_filter(self, client, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("hello")

        resp = client.get(
            "/api/filesystem/browse",
            params={
                "path": str(tmp_path),
                "dirs_only": "true",
            },
        )
        data = resp.json()
        types = [e["type"] for e in data["entries"]]
        assert all(t == "directory" for t in types)

    def test_entry_fields(self, client, tmp_path):
        (tmp_path / "file.txt").write_text("content")

        resp = client.get(
            "/api/filesystem/browse",
            params={"path": str(tmp_path)},
        )
        data = resp.json()
        entry = data["entries"][0]
        assert "name" in entry
        assert "path" in entry
        assert "type" in entry
        assert "size" in entry
        assert "modified" in entry


class TestErrorHandling:
    """Test 404 on non-existent paths."""

    def test_nonexistent_path_returns_404(
        self, client, tmp_path
    ):
        resp = client.get(
            "/api/filesystem/browse",
            params={
                "path": str(tmp_path / "nonexistent")
            },
        )
        assert resp.status_code == 404
        assert "does not exist" in resp.json()["detail"]
