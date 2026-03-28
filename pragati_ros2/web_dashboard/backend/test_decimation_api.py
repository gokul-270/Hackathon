"""Tests for the data decimation endpoint (Task 8.3).

Verifies:
- Correct bucket count
- Averaging math
- Min/max preservation
- Empty bucket handling
- Edge case: fewer points than requested
"""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.decimation import decimate_metrics, decimation_router


@pytest.fixture()
def app():
    """Create a test FastAPI app with the decimation router."""
    _app = FastAPI()
    _app.include_router(decimation_router)
    return _app


@pytest.fixture()
def client(app):
    return TestClient(app)


# ── Unit tests for decimate_metrics ──────────────────────────────────────


class TestDecimateMetrics:
    """Test the pure decimation function."""

    def test_reduces_to_target_buckets(self):
        """Data with 100 points reduced to 10 buckets."""
        now = time.time()
        metrics = [
            {"timestamp": now - 100 + i, "value": float(i), "metric_name": "cpu"}
            for i in range(100)
        ]
        result = decimate_metrics(metrics, target_points=10)
        assert len(result) <= 10

    def test_averaging_math(self):
        """Bucket with [10,20,30,40,50] → avg 30, min 10, max 50."""
        now = time.time()
        metrics = [
            {"timestamp": now, "value": v, "metric_name": "cpu"}
            for v in [10.0, 20.0, 30.0, 40.0, 50.0]
        ]
        result = decimate_metrics(metrics, target_points=1)
        assert len(result) == 1
        bucket = result[0]
        assert bucket["value_avg"] == pytest.approx(30.0)
        assert bucket["value_min"] == pytest.approx(10.0)
        assert bucket["value_max"] == pytest.approx(50.0)

    def test_min_max_preservation(self):
        """Min and max are preserved across multiple buckets."""
        now = time.time()
        metrics = [
            {"timestamp": now - 20, "value": 5.0, "metric_name": "cpu"},
            {"timestamp": now - 15, "value": 95.0, "metric_name": "cpu"},
            {"timestamp": now - 10, "value": 50.0, "metric_name": "cpu"},
            {"timestamp": now - 5, "value": 10.0, "metric_name": "cpu"},
            {"timestamp": now, "value": 80.0, "metric_name": "cpu"},
        ]
        result = decimate_metrics(metrics, target_points=2)
        all_mins = [b["value_min"] for b in result]
        all_maxs = [b["value_max"] for b in result]
        assert min(all_mins) == pytest.approx(5.0)
        assert max(all_maxs) == pytest.approx(95.0)

    def test_empty_buckets_omitted(self):
        """Time gap → no interpolation, empty buckets omitted."""
        now = time.time()
        # Two clusters of data with a gap
        metrics = [
            {"timestamp": now - 100, "value": 1.0, "metric_name": "cpu"},
            {"timestamp": now - 99, "value": 2.0, "metric_name": "cpu"},
            # Gap from -99 to -10
            {"timestamp": now - 10, "value": 3.0, "metric_name": "cpu"},
            {"timestamp": now - 9, "value": 4.0, "metric_name": "cpu"},
        ]
        result = decimate_metrics(metrics, target_points=10)
        # Should have <= 10 buckets, and none with 0 or null values
        for bucket in result:
            assert bucket["count"] > 0
            assert bucket["value_avg"] is not None

    def test_fewer_points_than_requested(self):
        """100 raw points with target 500 → returns all 100 without upsampling."""
        now = time.time()
        metrics = [
            {"timestamp": now - 100 + i, "value": float(i), "metric_name": "cpu"}
            for i in range(100)
        ]
        result = decimate_metrics(metrics, target_points=500)
        # Should return <= 100 (one bucket per unique point or per second)
        assert len(result) <= 100

    def test_empty_input(self):
        """Empty metrics list → empty result."""
        result = decimate_metrics([], target_points=500)
        assert result == []

    def test_single_point(self):
        """Single data point → single bucket."""
        now = time.time()
        metrics = [{"timestamp": now, "value": 42.0, "metric_name": "cpu"}]
        result = decimate_metrics(metrics, target_points=500)
        assert len(result) == 1
        assert result[0]["value_avg"] == pytest.approx(42.0)
        assert result[0]["value_min"] == pytest.approx(42.0)
        assert result[0]["value_max"] == pytest.approx(42.0)

    def test_result_has_required_fields(self):
        """Each bucket has timestamp, value_avg, value_min, value_max, count."""
        now = time.time()
        metrics = [
            {"timestamp": now - i, "value": float(i), "metric_name": "cpu"}
            for i in range(10)
        ]
        result = decimate_metrics(metrics, target_points=3)
        for bucket in result:
            assert "timestamp" in bucket
            assert "value_avg" in bucket
            assert "value_min" in bucket
            assert "value_max" in bucket
            assert "count" in bucket


# ── API endpoint tests ───────────────────────────────────────────────────


class TestDecimationEndpoint:
    """Test the /api/history/decimated endpoint."""

    def test_endpoint_returns_200(self, client):
        result = client.get("/api/history/decimated")
        assert result.status_code == 200

    def test_default_params(self, client):
        result = client.get("/api/history/decimated")
        data = result.json()
        assert "points" in data
        assert "hours" in data
        assert data["points"] == 500
        assert data["hours"] == 168

    def test_custom_params(self, client):
        result = client.get("/api/history/decimated?points=100&hours=24")
        data = result.json()
        assert data["points"] == 100
        assert data["hours"] == 24

    def test_response_has_metrics_array(self, client):
        result = client.get("/api/history/decimated")
        data = result.json()
        assert "metrics" in data
        assert isinstance(data["metrics"], list)
