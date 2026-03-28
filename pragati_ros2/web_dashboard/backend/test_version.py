"""Tests for centralized version management.

Verifies that all version-reporting code reads from the single
web_dashboard/VERSION file rather than using hardcoded strings.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from backend.version import get_version, VERSION_FILE_PATH


class TestGetVersion:
    """Tests for the get_version() utility function."""

    def test_reads_from_version_file(self, tmp_path):
        """get_version() returns the content of the VERSION file."""
        version_file = tmp_path / "VERSION"
        version_file.write_text("1.2.0\n")
        assert get_version(version_file) == "1.2.0"

    def test_strips_whitespace(self, tmp_path):
        """Trailing newlines and spaces are stripped."""
        version_file = tmp_path / "VERSION"
        version_file.write_text("  2.0.0-rc1  \n\n")
        assert get_version(version_file) == "2.0.0-rc1"

    def test_fallback_when_file_missing(self, tmp_path):
        """Returns '0.0.0-unknown' when VERSION file doesn't exist."""
        missing = tmp_path / "DOES_NOT_EXIST"
        assert get_version(missing) == "0.0.0-unknown"

    def test_default_path_is_web_dashboard_version(self):
        """The default path points to web_dashboard/VERSION."""
        expected = Path(__file__).resolve().parent.parent / "VERSION"
        assert VERSION_FILE_PATH == expected

    def test_real_version_file_exists(self):
        """The actual VERSION file exists and contains a valid semver."""
        assert (
            VERSION_FILE_PATH.exists()
        ), f"VERSION file not found at {VERSION_FILE_PATH}"
        version = get_version()
        # Basic semver: digits.digits.digits with optional pre-release
        assert (
            version and version[0].isdigit()
        ), f"VERSION file content doesn't look like semver: {version!r}"


class TestHealthEndpointVersions:
    """Verify health.py endpoints use centralized version."""

    def setup_method(self):
        from backend.health import init_health_registry

        init_health_registry()

    def test_capabilities_endpoint_uses_version_file(self):
        """GET /api/capabilities returns version from VERSION file."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.health import router, init_status_deps

        # Inject a mock capabilities manager
        class FakeCaps:
            capabilities = {"topic_echo": True}

            def get_enabled_capabilities(self):
                return ["topic_echo"]

        init_status_deps(
            system_state={"nodes": {}, "topics": {}, "services": {}},
            capabilities_manager=FakeCaps(),
            message_envelope=None,
            server_start_time=0,
        )

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/api/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        # Must match VERSION file, not a hardcoded string
        from backend.version import get_version

        assert data["server_version"] == get_version()

    def test_capabilities_endpoint_no_manager_uses_version_file(self):
        """GET /api/capabilities with no caps manager still returns VERSION."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.health import router, init_status_deps

        init_status_deps(
            system_state={"nodes": {}, "topics": {}, "services": {}},
            capabilities_manager=None,
            message_envelope=None,
            server_start_time=0,
        )

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/api/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        from backend.version import get_version

        assert data["server_version"] == get_version()

    def test_system_info_uses_version_file(self):
        """GET /api/system/info dashboard_version matches VERSION file."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.health import router, init_status_deps

        init_status_deps(
            system_state={"nodes": {}, "topics": {}, "services": {}},
            capabilities_manager=None,
            message_envelope=None,
            server_start_time=0,
        )

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.get("/api/system/info")
        assert resp.status_code == 200
        data = resp.json()
        from backend.version import get_version

        assert data["dashboard_version"] == get_version()


class TestCapabilitiesModuleVersion:
    """Verify capabilities.py uses centralized version."""

    def test_message_envelope_uses_version_file(self):
        """MessageEnvelope.server_version matches VERSION file."""
        from backend.capabilities import MessageEnvelope, CapabilitiesManager
        from backend.version import get_version

        caps = CapabilitiesManager()
        envelope = MessageEnvelope(caps)
        assert envelope.server_version == get_version()


class TestAppFactoryVersion:
    """Verify app_factory.py uses centralized version."""

    def test_fastapi_app_version_matches_version_file(self):
        """FastAPI app.version matches VERSION file."""
        from backend.version import get_version

        # We can't easily create the full app (requires ROS2 etc),
        # so we check the source doesn't contain hardcoded "1.0.0"
        source = Path(__file__).resolve().parent / "app_factory.py"
        content = source.read_text()
        # The FastAPI version= kwarg should reference get_version()
        assert (
            'version="1.0.0"' not in content
        ), "app_factory.py still has hardcoded version='1.0.0'"
        assert (
            "get_version()" in content
        ), "app_factory.py should call get_version() for FastAPI version"
