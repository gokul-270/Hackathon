#!/usr/bin/env python3
"""
Tests for standalone_motor_server.py

Unit tests for RS485 frame building/parsing and JSON conversion.
Integration tests for FastAPI endpoints with mocked serial port.
"""

import asyncio
import json
import struct
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from standalone_motor_server import (
    RS485MotorDriver,
    RS485_HEADER,
    CMD_READ_STATUS_1,
    CMD_READ_STATUS_2,
    CMD_READ_STATUS_3,
    CMD_READ_ENCODER,
    CMD_READ_MULTI_TURN_ANGLE,
    CMD_READ_SINGLE_TURN_ANGLE,
    CMD_READ_PID,
    CURRENT_SCALE,
    PHASE_CURRENT_SCALE,
    decode_error_flags_short,
    decode_error_flags_long,
    infer_motor_state,
)

# ---------------------------------------------------------------------------
# Task 3.1: Unit tests for RS485 frame building and parsing
# ---------------------------------------------------------------------------


class TestRS485FrameBuilding:
    """Test RS485 frame construction."""

    def test_build_frame_no_data(self):
        """Frame with no data: [0x3E][CMD][ID][0x00][CHECKSUM]"""
        frame = RS485MotorDriver._build_frame(0x9A, 3)
        assert frame[0] == 0x3E
        assert frame[1] == 0x9A
        assert frame[2] == 3
        assert frame[3] == 0x00  # length
        expected_checksum = (0x3E + 0x9A + 3 + 0x00) & 0xFF
        assert frame[4] == expected_checksum
        assert len(frame) == 5

    def test_build_frame_with_data(self):
        """Frame with data: [0x3E][CMD][ID][LEN][CHECKSUM][DATA...][DATA_CHECKSUM]"""
        data = [0x01, 0x02, 0x03]
        frame = RS485MotorDriver._build_frame(0x31, 1, data)
        assert frame[0] == 0x3E
        assert frame[1] == 0x31
        assert frame[2] == 1
        assert frame[3] == 3  # data length
        frame_checksum = (0x3E + 0x31 + 1 + 3) & 0xFF
        assert frame[4] == frame_checksum
        assert frame[5] == 0x01
        assert frame[6] == 0x02
        assert frame[7] == 0x03
        data_checksum = (0x01 + 0x02 + 0x03) & 0xFF
        assert frame[8] == data_checksum

    def test_build_frame_motor_on(self):
        """Motor ON command for motor ID 3 matches known good frame."""
        frame = RS485MotorDriver._build_frame(0x88, 3)
        # Known good: 3E 88 03 00 C9
        assert frame == bytes([0x3E, 0x88, 0x03, 0x00, 0xC9])

    def test_build_frame_read_status1(self):
        """Read status 1 for motor ID 3 matches known good frame."""
        frame = RS485MotorDriver._build_frame(0x9A, 3)
        # Known good: 3E 9A 03 00 DB
        assert frame == bytes([0x3E, 0x9A, 0x03, 0x00, 0xDB])

    def test_checksum_wraps(self):
        """Checksum wraps at 256."""
        assert RS485MotorDriver._checksum([0xFF, 0x01]) == 0x00
        assert RS485MotorDriver._checksum([0xFF, 0xFF]) == 0xFE


class TestRS485FrameParsing:
    """Test RS485 response frame parsing."""

    def test_parse_no_data_response(self):
        """Parse response with no data payload."""
        # Motor ON response: 3E 88 03 00 C9
        raw = bytes([0x3E, 0x88, 0x03, 0x00, 0xC9])
        result = RS485MotorDriver._parse_response(raw)
        assert result is not None
        assert result["cmd"] == 0x88
        assert result["motor_id"] == 3
        assert result["data_len"] == 0

    def test_parse_status1_response(self):
        """Parse known good Status 1 response."""
        # From actual motor: 3E 9A 03 07 E2 28 07 12 00 00 00 00 41
        raw = bytes(
            [
                0x3E,
                0x9A,
                0x03,
                0x07,
                0xE2,
                0x28,
                0x07,
                0x12,
                0x00,
                0x00,
                0x00,
                0x00,
                0x41,
            ]
        )
        result = RS485MotorDriver._parse_response(raw)
        assert result is not None
        assert result["cmd"] == 0x9A
        assert result["motor_id"] == 3
        assert result["data_len"] == 7
        assert result["data"] == bytes([0x28, 0x07, 0x12, 0x00, 0x00, 0x00, 0x00])

    def test_parse_invalid_header(self):
        """Reject frame with wrong header."""
        raw = bytes([0x00, 0x9A, 0x03, 0x00, 0x9D])
        assert RS485MotorDriver._parse_response(raw) is None

    def test_parse_too_short(self):
        """Reject frame that is too short."""
        assert RS485MotorDriver._parse_response(b"\x3e\x9a") is None

    def test_parse_bad_frame_checksum(self):
        """Reject frame with bad checksum."""
        raw = bytes([0x3E, 0x9A, 0x03, 0x00, 0xFF])  # wrong checksum
        assert RS485MotorDriver._parse_response(raw) is None

    def test_parse_bad_data_checksum(self):
        """Reject frame with bad data checksum."""
        raw = bytes(
            [
                0x3E,
                0x9A,
                0x03,
                0x07,
                0xE2,
                0x28,
                0x07,
                0x12,
                0x00,
                0x00,
                0x00,
                0x00,
                0xFF,
            ]
        )  # wrong data checksum
        assert RS485MotorDriver._parse_response(raw) is None

    def test_parse_incomplete_data(self):
        """Reject frame with data_len > actual data bytes."""
        raw = bytes([0x3E, 0x9A, 0x03, 0x07, 0xE2, 0x28])  # only 1 data byte
        assert RS485MotorDriver._parse_response(raw) is None


# ---------------------------------------------------------------------------
# Task 3.2: Unit tests for response-to-JSON conversion
# ---------------------------------------------------------------------------


class TestStatusDecoding:
    """Test motor status response decoding."""

    def test_decode_status1(self):
        """Decode Status 1 response: temp=40C, voltage=18.1V, no errors."""
        driver = RS485MotorDriver.__new__(RS485MotorDriver)
        driver._lock = threading.Lock()
        driver._serial = MagicMock()
        driver.motor_id = 3
        driver.timeout = 1.0

        # Mock _send_receive to return parsed response
        # Voltage 18.1V = 1810 raw at 0.01V/LSB (little-endian: 0x12, 0x07)
        data = bytes([0x28, 0x12, 0x07, 0x00, 0x00, 0x00, 0x00])
        with patch.object(
            driver,
            "_send_receive",
            return_value={"cmd": 0x9A, "motor_id": 3, "data_len": 7, "data": data},
        ):
            result = driver.read_status_1()

        assert result is not None
        assert result["temperature_c"] == 40.0
        assert result["voltage_v"] == 18.1  # 1810 * 0.01 = 18.1V
        assert result["error_byte"] == 0

    def test_decode_status2(self):
        """Decode Status 2 response."""
        driver = RS485MotorDriver.__new__(RS485MotorDriver)
        driver._lock = threading.Lock()
        driver._serial = MagicMock()
        driver.motor_id = 3
        driver.timeout = 1.0

        # temp=30, iq=100 raw, speed=360 dps, encoder=32768
        temp = struct.pack("<b", 30)
        iq = struct.pack("<h", 100)
        speed = struct.pack("<h", 360)
        enc = struct.pack("<H", 32768)
        data = temp + iq + speed + enc

        with patch.object(
            driver,
            "_send_receive",
            return_value={"cmd": 0x9C, "motor_id": 3, "data_len": 7, "data": data},
        ):
            result = driver.read_status_2()

        assert result is not None
        assert result["temperature_c"] == 30.0
        assert abs(result["torque_current_a"] - (100 * CURRENT_SCALE)) < 0.001
        assert result["speed_dps"] == 360.0
        assert result["encoder_position"] == 32768

    def test_decode_multi_turn_angle_positive(self):
        """Decode positive multi-turn angle."""
        driver = RS485MotorDriver.__new__(RS485MotorDriver)
        driver._lock = threading.Lock()
        driver._serial = MagicMock()
        driver.motor_id = 3
        driver.timeout = 1.0

        # 9000 centideg = 90.00 degrees
        angle_bytes = struct.pack("<q", 9000)[:8]  # use first 8 bytes
        with patch.object(
            driver,
            "_send_receive",
            return_value={
                "cmd": 0x92,
                "motor_id": 3,
                "data_len": 8,
                "data": angle_bytes,
            },
        ):
            result = driver.read_multi_turn_angle()

        assert result is not None
        assert abs(result - 90.0) < 0.01

    def test_decode_multi_turn_angle_negative(self):
        """Decode negative multi-turn angle."""
        driver = RS485MotorDriver.__new__(RS485MotorDriver)
        driver._lock = threading.Lock()
        driver._serial = MagicMock()
        driver.motor_id = 3
        driver.timeout = 1.0

        # From actual motor: CA FF FF FF FF FF FF FF = -54 centideg = -0.54 deg
        data = bytes([0xCA, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        with patch.object(
            driver,
            "_send_receive",
            return_value={"cmd": 0x92, "motor_id": 3, "data_len": 8, "data": data},
        ):
            result = driver.read_multi_turn_angle()

        assert result is not None
        assert abs(result - (-0.54)) < 0.01

    def test_decode_single_turn_angle(self):
        """Decode single-turn angle."""
        driver = RS485MotorDriver.__new__(RS485MotorDriver)
        driver._lock = threading.Lock()
        driver._serial = MagicMock()
        driver.motor_id = 3
        driver.timeout = 1.0

        # Little-endian uint32: [0x89, 0x4B, 0x03, 0x00] = 215945
        # 215945 * 0.01 = 2159.45 degrees (multi-turn raw value)
        data = bytes([0x89, 0x4B, 0x03, 0x00])
        with patch.object(
            driver,
            "_send_receive",
            return_value={"cmd": 0x94, "motor_id": 3, "data_len": 4, "data": data},
        ):
            result = driver.read_single_turn_angle()

        assert result is not None
        assert abs(result - 2159.45) < 0.01

    def test_decode_encoder(self):
        """Decode encoder response."""
        driver = RS485MotorDriver.__new__(RS485MotorDriver)
        driver._lock = threading.Lock()
        driver._serial = MagicMock()
        driver.motor_id = 3
        driver.timeout = 1.0

        # From actual: [9C FF 9C FF 00 00]
        data = bytes([0x9C, 0xFF, 0x9C, 0xFF, 0x00, 0x00])
        with patch.object(
            driver,
            "_send_receive",
            return_value={"cmd": 0x90, "motor_id": 3, "data_len": 6, "data": data},
        ):
            result = driver.read_encoder()

        assert result is not None
        assert result["original_value"] == 0xFF9C  # 65436
        assert result["raw_value"] == 0xFF9C
        assert result["offset"] == 0


class TestErrorFlagDecoding:
    """Test error flag decoding functions."""

    def test_short_flags_no_errors(self):
        flags = decode_error_flags_short(0x00)
        assert all(v is False for v in flags.values())
        assert len(flags) == 8

    def test_short_flags_undervoltage(self):
        flags = decode_error_flags_short(0x01)
        assert flags["uvp"] is True
        assert flags["ovp"] is False

    def test_short_flags_all_errors(self):
        flags = decode_error_flags_short(0xFF)
        assert all(v is True for v in flags.values())

    def test_long_flags_no_errors(self):
        flags = decode_error_flags_long(0x00)
        assert all(v is False for v in flags.values())
        assert "undervoltage_protection" in flags

    def test_long_flags_overcurrent(self):
        flags = decode_error_flags_long(0x10)
        assert flags["overcurrent_protection"] is True
        assert flags["undervoltage_protection"] is False

    def test_motor_state_inference_running(self):
        assert infer_motor_state(0, 10.5) == "running"

    def test_motor_state_inference_error(self):
        assert infer_motor_state(0x01, 0.0) == "error"

    def test_motor_state_inference_off(self):
        assert infer_motor_state(0, 0.0) == "off"


# ---------------------------------------------------------------------------
# Task 3.3: Integration tests for FastAPI endpoints with mocked serial
# ---------------------------------------------------------------------------


class TestFastAPIEndpoints:
    """Integration tests for REST API endpoints."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock RS485MotorDriver."""
        d = MagicMock(spec=RS485MotorDriver)
        d.motor_id = 3
        return d

    @pytest.fixture
    def client(self, mock_driver):
        """Create a FastAPI TestClient with mocked driver."""
        from fastapi.testclient import TestClient
        import standalone_motor_server as sms

        # Override the global driver
        original_driver = sms.driver
        sms.driver = mock_driver

        # Set cli_args
        original_args = sms.cli_args
        args = MagicMock()
        args.motor_id = 3
        sms.cli_args = args

        client = TestClient(sms.app)
        yield client

        sms.driver = original_driver
        sms.cli_args = original_args

    def test_validation_ranges(self, client):
        resp = client.get("/api/motor/validation_ranges")
        assert resp.status_code == 200
        data = resp.json()
        assert "mg6010" in data
        assert data["mg6010"]["pid_gains"]["max"] == 255

    def test_get_state_success(self, client, mock_driver):
        mock_driver.get_full_state.return_value = {
            "temperature_c": 40.0,
            "voltage_v": 24.0,
            "torque_current_a": 0.5,
            "speed_dps": 0.0,
            "encoder_position": 32768,
            "multi_turn_deg": 90.0,
            "single_turn_deg": 90.0,
            "phase_current_a": [0.1, 0.2, 0.3],
            "error_byte": 0,
        }

        resp = client.get("/api/motor/3/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["temperature_c"] == 40.0
        assert data["voltage_v"] == 24.0
        assert "error_flags" in data
        assert data["error_flags"]["undervoltage_protection"] is False

    def test_get_state_timeout(self, client, mock_driver):
        mock_driver.get_full_state.return_value = None

        resp = client.get("/api/motor/3/state")
        assert resp.status_code == 504

    def test_get_angles_success(self, client, mock_driver):
        mock_driver.read_multi_turn_angle.return_value = 180.5
        mock_driver.read_single_turn_angle.return_value = 180.5

        resp = client.get("/api/motor/3/angles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["multi_turn_deg"] == 180.5

    def test_get_encoder_success(self, client, mock_driver):
        mock_driver.read_encoder.return_value = {
            "raw_value": 65436,
            "offset": 0,
            "original_value": 65436,
        }

        resp = client.get("/api/motor/3/encoder")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["raw_value"] == 65436

    def test_get_limits(self, client, mock_driver):
        mock_driver.read_max_torque.return_value = 2000
        mock_driver.read_acceleration.return_value = 1000.0

        resp = client.get("/api/motor/3/limits")
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_torque_ratio"] == 2000
        assert data["acceleration_dps"] == 1000.0
        # Also check for the frontend-compat field
        assert data["acceleration"] == 1000.0

    def test_list_motors(self, client):
        resp = client.get("/api/pid/motors")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["motors"]) == 1
        assert data["motors"][0]["motor_id"] == 3

    def test_read_pid(self, client, mock_driver):
        mock_driver.read_pid.return_value = {
            "angle_kp": 30,
            "angle_ki": 10,
            "speed_kp": 50,
            "speed_ki": 20,
            "current_kp": 40,
            "current_ki": 15,
        }

        resp = client.get("/api/pid/read/3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["gains"]["angle_kp"] == 30

    def test_lifecycle_motor_on(self, client, mock_driver):
        mock_driver.motor_on.return_value = {"cmd": 0x88, "motor_id": 3}

        resp = client.post("/api/motor/3/lifecycle", json={"action": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["motor_state_name"] == "RUNNING"

    def test_clear_errors(self, client, mock_driver):
        mock_driver.clear_errors.return_value = {"error_byte": 0}

        resp = client.post("/api/motor/3/errors/clear")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["error_flags_after"]["undervoltage_protection"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
