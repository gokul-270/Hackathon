"""Tests for path traversal protection in analysis_api and bag_api."""

import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.analysis_api import analysis_router
import backend.analysis_api as _analysis_mod
from backend.bag_api import bag_router
import backend.bag_api as _bag_mod

# -----------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_analysis_state(tmp_path):
    """Point analysis dirs to tmp and reset jobs dict."""
    orig_results = _analysis_mod._results_dir
    orig_field_logs = _analysis_mod.FIELD_LOGS_DIR
    orig_jobs = _analysis_mod._jobs.copy()

    _analysis_mod._results_dir = tmp_path / "results"
    _analysis_mod._results_dir.mkdir()
    _analysis_mod.FIELD_LOGS_DIR = tmp_path / "field_logs"
    _analysis_mod.FIELD_LOGS_DIR.mkdir()

    yield

    _analysis_mod._results_dir = orig_results
    _analysis_mod.FIELD_LOGS_DIR = orig_field_logs
    _analysis_mod._jobs.clear()
    _analysis_mod._jobs.update(orig_jobs)


@pytest.fixture(autouse=True)
def _isolate_bag_state(tmp_path):
    """Point bag BAGS_DIR to tmp."""
    orig_bags = _bag_mod.BAGS_DIR
    _bag_mod.BAGS_DIR = tmp_path / "bags"
    _bag_mod.BAGS_DIR.mkdir()
    yield
    _bag_mod.BAGS_DIR = orig_bags


@pytest.fixture()
def client():
    """Test client with analysis and bag routers."""
    app = FastAPI()
    app.include_router(analysis_router)
    app.include_router(bag_router)
    return TestClient(app)


# -----------------------------------------------------------------
# analysis_api path traversal
# -----------------------------------------------------------------


class TestAnalysisPathTraversal:
    """Path traversal protection on POST /api/analysis/run."""

    def test_traversal_rejected(self, client, tmp_path):
        """Path containing ../../ outside FIELD_LOGS_DIR gets 403."""
        resp = client.post(
            "/api/analysis/run",
            json={"log_directory": "/tmp/../../etc/passwd"},
        )
        assert resp.status_code == 403
        assert "Path outside allowed director" in resp.json()["detail"]

    def test_valid_path_not_rejected_as_traversal(self, client, tmp_path):
        """A valid subdirectory within FIELD_LOGS_DIR passes traversal
        check (may still fail for other reasons like dir not existing
        as an absolute path)."""
        sub = _analysis_mod.FIELD_LOGS_DIR / "session_001"
        sub.mkdir()
        # The endpoint resolves path relative to FIELD_LOGS_DIR, then
        # checks the directory exists as an absolute path.
        # A relative name that stays inside FIELD_LOGS_DIR should not
        # get 403; it may get 400 if the path doesn't exist as an
        # absolute path on disk.
        resp = client.post(
            "/api/analysis/run",
            json={"log_directory": "session_001"},
        )
        # Should NOT be 403 (traversal). 400 is acceptable because
        # the endpoint also checks Path(log_directory).exists().
        assert resp.status_code != 403

    def test_symlink_traversal_blocked(self, client, tmp_path):
        """A symlink inside FIELD_LOGS_DIR pointing outside is 403."""
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        link_path = _analysis_mod.FIELD_LOGS_DIR / "sneaky_link"
        try:
            os.symlink(str(outside_dir), str(link_path))
        except OSError:
            pytest.skip("Cannot create symlinks in this environment")
        resp = client.post(
            "/api/analysis/run",
            json={"log_directory": str(link_path)},
        )
        assert resp.status_code == 403


# -----------------------------------------------------------------
# bag_api path traversal
# -----------------------------------------------------------------


class TestBagPathTraversal:
    """Path traversal protection on GET /api/bags/list."""

    def test_traversal_rejected(self, client):
        """Path query parameter escaping BAGS_DIR gets 403."""
        resp = client.get("/api/bags/list", params={"path": "/tmp/../../etc"})
        assert resp.status_code == 403
        assert "Path outside allowed directory" in resp.json()["detail"]

    def test_valid_subpath_accepted(self, client, tmp_path):
        """A subdirectory inside BAGS_DIR is accepted."""
        sub = _bag_mod.BAGS_DIR / "trial_001"
        sub.mkdir()
        resp = client.get("/api/bags/list", params={"path": str(sub)})
        assert resp.status_code == 200

    def test_no_path_defaults_to_bags_dir(self, client):
        """Omitting the path parameter lists bags from BAGS_DIR."""
        resp = client.get("/api/bags/list")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
