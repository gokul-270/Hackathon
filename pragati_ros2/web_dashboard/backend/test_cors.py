"""Tests for CORS restriction configuration."""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


class TestCorsRestriction:
    def test_allowed_origin_gets_cors_headers(self):
        """An origin in the allowlist gets access-control headers."""
        with patch("backend.app_factory._load_config") as mock_cfg:
            mock_cfg.return_value = {
                "cors": {
                    "allowed_origins": ["http://localhost:8090"]
                },
            }
            from backend.app_factory import create_app

            app = create_app()

            @app.get("/cors-test-allowed")
            def _route():
                return {"ok": True}

            client = TestClient(app)
            resp = client.get(
                "/cors-test-allowed",
                headers={"Origin": "http://localhost:8090"},
            )
            assert (
                resp.headers.get("access-control-allow-origin")
                == "http://localhost:8090"
            )
            assert (
                resp.headers.get("access-control-allow-credentials")
                == "true"
            )

    def test_disallowed_origin_no_cors_headers(self):
        """An origin NOT in the allowlist gets no CORS headers."""
        with patch("backend.app_factory._load_config") as mock_cfg:
            mock_cfg.return_value = {
                "cors": {
                    "allowed_origins": ["http://localhost:8090"]
                },
            }
            from backend.app_factory import create_app

            app = create_app()

            @app.get("/cors-test-disallowed")
            def _route():
                return {"ok": True}

            client = TestClient(app)
            resp = client.get(
                "/cors-test-disallowed",
                headers={"Origin": "http://evil.com"},
            )
            assert (
                "access-control-allow-origin" not in resp.headers
            )

    def test_no_wildcard_in_default_origins(self):
        """Default config should not use wildcard '*'."""
        with patch("backend.app_factory._load_config") as mock_cfg:
            mock_cfg.return_value = {}
            from backend.app_factory import create_app

            app = create_app()

            @app.get("/cors-test-wildcard")
            def _route():
                return {"ok": True}

            client = TestClient(app)
            # A random origin should NOT get CORS headers with
            # the default localhost-only allowlist
            resp = client.get(
                "/cors-test-wildcard",
                headers={"Origin": "http://random-site.com"},
            )
            assert (
                resp.headers.get("access-control-allow-origin")
                != "*"
            )

    def test_preflight_options_for_allowed_origin(self):
        """CORS preflight (OPTIONS) returns proper headers."""
        with patch("backend.app_factory._load_config") as mock_cfg:
            mock_cfg.return_value = {
                "cors": {
                    "allowed_origins": ["http://localhost:8090"]
                },
            }
            from backend.app_factory import create_app

            app = create_app()

            @app.get("/cors-test-preflight")
            def _route():
                return {"ok": True}

            client = TestClient(app)
            resp = client.options(
                "/cors-test-preflight",
                headers={
                    "Origin": "http://localhost:8090",
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert (
                resp.headers.get("access-control-allow-origin")
                == "http://localhost:8090"
            )
