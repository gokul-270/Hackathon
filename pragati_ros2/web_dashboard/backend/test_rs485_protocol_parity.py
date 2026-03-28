"""Tests for RS485 protocol parity commands.

Covers CMD 0x1F (firmware version), CMD 0x14 (full config),
CMD 0x10 (heartbeat), CMD 0x16 extensions (encoder fields),
bus_type mapping fix, API endpoint tests, and WebSocket
late-driver registration.

Tasks: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import asyncio
import struct
import sys
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock ROS2 modules so we can import motor_api without ROS2 installed.
# ---------------------------------------------------------------------------
sys.modules.setdefault("rclpy", MagicMock())
sys.modules.setdefault("rclpy.node", MagicMock())
sys.modules.setdefault("rclpy.callback_groups", MagicMock())
sys.modules.setdefault("rclpy.qos", MagicMock())
sys.modules.setdefault("motor_control_msgs", MagicMock())
sys.modules.setdefault("motor_control_msgs.srv", MagicMock())
sys.modules.setdefault("std_msgs", MagicMock())
sys.modules.setdefault("std_msgs.msg", MagicMock())

# Ensure backend is importable
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.rs485_driver import (  # noqa: E402
    CMD_READ_FIRMWARE_VERSION,
    CMD_READ_FULL_CONFIG,
    CMD_READ_SYSTEM_STATE,
    RS485MotorDriver,
    _lookup_motor_poles,
    _lookup_reduction_ratio,
)

import backend.motor_api as motor_api_module  # noqa: E402
from backend.motor_api import (  # noqa: E402
    MotorConfigBridge,
    motor_router,
)

# Force ROS2 unavailable for all tests in this file
motor_api_module.ROS2_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_response(cmd: int, motor_id: int, data_bytes: list[int]) -> bytes:
    """Build a valid RS485 response frame for mocking."""
    header = [0x3E, cmd, motor_id, len(data_bytes)]
    header_checksum = sum(header) & 0xFF
    frame = bytes(header + [header_checksum])
    if data_bytes:
        data_checksum = sum(data_bytes) & 0xFF
        frame += bytes(data_bytes) + bytes([data_checksum])
    return frame


def _make_driver(motor_id: int = 1) -> RS485MotorDriver:
    """Create a driver with mocked serial port."""
    with patch("backend.rs485_driver.serial") as mock_serial:
        mock_serial.Serial = MagicMock
        mock_serial.EIGHTBITS = 8
        mock_serial.PARITY_NONE = "N"
        mock_serial.STOPBITS_ONE = 1
        drv = RS485MotorDriver(port="/dev/ttyUSB0", baud=115200, motor_id=motor_id)
    drv._serial = MagicMock()
    drv._serial.is_open = True
    return drv


def _setup_response(drv: RS485MotorDriver, response_bytes: bytes):
    """Configure mock serial to return response_bytes on read.

    The _send_receive loop checks in_waiting in two phases:
    1. Drain phase: reads until in_waiting == 0
    2. Response phase: waits for in_waiting > 0, then reads

    We use a PropertyMock with side_effect to simulate:
    drain(0) -> send -> wait(0, ..., response_len) -> read -> done
    """
    # Phase tracking: drain returns 0, then after write we return
    # response length once, then 0 forever
    call_count = {"n": 0, "written": False}

    original_write = drv._serial.write

    def _track_write(*args, **kwargs):
        call_count["written"] = True
        return original_write(*args, **kwargs)

    drv._serial.write = MagicMock(side_effect=_track_write)

    def _in_waiting_side_effect():
        call_count["n"] += 1
        if not call_count["written"]:
            return 0  # drain phase
        if call_count["n"] <= 20:
            # First few calls after write: no data yet
            if call_count.get("delivered"):
                return 0
            call_count["delivered"] = True
            return len(response_bytes)
        return 0

    type(drv._serial).in_waiting = PropertyMock(side_effect=_in_waiting_side_effect)
    drv._serial.read.return_value = response_bytes


# ---------------------------------------------------------------------------
# 7.1 — read_firmware_version() tests
# ---------------------------------------------------------------------------


class TestReadFirmwareVersion:
    """Task 7.1: CMD 0x1F firmware version read."""

    def test_successful_2byte_response(self):
        """Successful firmware version decode from 2-byte payload."""
        drv = _make_driver()
        # firmware build = 0x0123 (LE: 0x23, 0x01)
        resp_frame = _build_response(0x1F, 1, [0x23, 0x01])
        _setup_response(drv, resp_frame)

        result = drv.read_firmware_version()

        assert result is not None
        assert "error" not in result
        assert result["firmware_build"] == 0x0123
        assert result["firmware_build_hex"] == "0x0123"
        assert result["byte_0"] == 0x23
        assert result["byte_1"] == 0x01

    def test_invalid_response_length_rejected(self):
        """Response with != 2 data bytes returns error."""
        drv = _make_driver()
        # 3 data bytes instead of 2
        resp_frame = _build_response(0x1F, 1, [0x23, 0x01, 0xFF])
        _setup_response(drv, resp_frame)

        result = drv.read_firmware_version()

        assert result is not None
        assert "error" in result
        assert "3 bytes" in result["error"]

    def test_timeout_returns_none(self):
        """No response within timeout returns None."""
        drv = _make_driver()
        drv.timeout = 0.05
        type(drv._serial).in_waiting = PropertyMock(return_value=0)
        drv._serial.read.return_value = b""

        result = drv.read_firmware_version()

        assert result is None

    def test_tx_frame_correct(self):
        """Verify the TX frame sent matches protocol spec."""
        drv = _make_driver(motor_id=1)
        drv.timeout = 0.05
        type(drv._serial).in_waiting = PropertyMock(return_value=0)
        drv._serial.read.return_value = b""

        drv.read_firmware_version()

        # TX frame: 3E 1F 01 00 <checksum>
        # checksum = (0x3E + 0x1F + 0x01 + 0x00) & 0xFF = 0x5E
        expected_frame = bytes([0x3E, 0x1F, 0x01, 0x00, 0x5E])
        drv._serial.write.assert_called_with(expected_frame)


# ---------------------------------------------------------------------------
# 7.2 — read_full_config() tests
# ---------------------------------------------------------------------------


def _build_104byte_config() -> list[int]:
    """Build a 104-byte config payload with known test values."""
    data = [0] * 104

    # Current Ramp [4-5] LE uint16 = 500
    struct.pack_into("<H", bytearray(data), 4, 500)
    data[4:6] = list(struct.pack("<H", 500))

    # Angle Kp [6] = 30
    data[6] = 30
    # Angle Ki [8] = 5
    data[8] = 5

    # Motor Temp Limit [14] = 80
    data[14] = 80
    # Driver Temp Limit [15] = 70
    data[15] = 70

    # Under Voltage [16-17] LE = 2400 -> /100 = 24.0
    data[16:18] = list(struct.pack("<H", 2400))
    # Over Voltage [18-19] LE = 6000 -> /100 = 60.0
    data[18:20] = list(struct.pack("<H", 6000))
    # Over Current [20-21] LE = 1500 -> /100 = 15.0
    data[20:22] = list(struct.pack("<H", 1500))
    # Over Current Time [22-23] LE = 3000 ms
    data[22:24] = list(struct.pack("<H", 3000))

    # Stall Threshold [24-25] LE = 200
    data[24:26] = list(struct.pack("<H", 200))
    # Lost Input Time [26-27] LE = 1000 ms
    data[26:28] = list(struct.pack("<H", 1000))

    # Motor Temp Enable [28] = 1
    data[28] = 1
    # Driver Temp Enable [29] = 0
    data[29] = 0

    # Brake Resistor Voltage [30-31] LE = 4800 -> /100 = 48.0
    data[30:32] = list(struct.pack("<H", 4800))

    # Under Voltage Enable [32] = 1
    data[32] = 1
    # Over Voltage Enable [33] = 1
    data[33] = 1
    # Over Current Enable [34] = 1 (estimated offset)
    data[34] = 1
    # Stall Enable [35] = 0 (estimated offset)
    data[35] = 0
    # Lost Input Enable [36] = 1 (estimated offset)
    data[36] = 1

    # Speed Kp [56-57] LE = 120
    data[56:58] = list(struct.pack("<H", 120))
    # Speed Ki [58-59] LE = 10
    data[58:60] = list(struct.pack("<H", 10))
    # Current Kp [62-63] LE = 200
    data[62:64] = list(struct.pack("<H", 200))
    # Current Ki [64-65] LE = 50
    data[64:66] = list(struct.pack("<H", 50))

    # Max Torque Current [68-69] LE = 2000
    data[68:70] = list(struct.pack("<H", 2000))

    # Max Speed [72-75] LE uint32 = 100000 -> /100 = 1000.0
    data[72:76] = list(struct.pack("<I", 100000))
    # Max Angle [76-79] LE int32 signed = -36000 -> /100 = -360.0
    data[76:80] = list(struct.pack("<i", -36000))

    # Speed Ramp [92-93] LE = 300
    data[92:94] = list(struct.pack("<H", 300))

    # Trailer [100-103]: version bytes + 0x55AA magic
    data[100] = 0x01  # version byte 0
    data[101] = 0x02  # version byte 1
    data[102:104] = list(struct.pack("<H", 0x55AA))

    return data


class TestReadFullConfig:
    """Task 7.2: CMD 0x14 full config 104-byte decode."""

    def test_pid_gains_decoded(self):
        """PID gains decoded from correct offsets."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()

        assert result is not None
        assert "error" not in result
        pid = result["pid_setting"]
        assert pid["angle_kp"] == 30
        assert pid["angle_ki"] == 5
        assert pid["speed_kp"] == 120
        assert pid["speed_ki"] == 10
        assert pid["current_kp"] == 200
        assert pid["current_ki"] == 50

    def test_temperature_limits_and_enables(self):
        """Temperature fields and enable booleans decoded."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()
        prot = result["protection_setting"]

        assert prot["motor_temp_limit"] == 80
        assert prot["driver_temp_limit"] == 70
        assert prot["motor_temp_enable"] == "Enable (recoverable)"
        assert prot["driver_temp_enable"] == "Disable"

    def test_voltage_thresholds_with_scaling(self):
        """Voltage thresholds decoded with /100 scaling."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()
        prot = result["protection_setting"]

        assert prot["under_voltage"] == pytest.approx(24.0)
        assert prot["over_voltage"] == pytest.approx(60.0)
        assert prot["over_current"] == pytest.approx(15.0)
        assert prot["over_current_time"] == 3000
        assert prot["brake_resistor_voltage"] == pytest.approx(48.0)

    def test_protection_enables(self):
        """Protection enable booleans decoded."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()
        prot = result["protection_setting"]

        assert prot["under_voltage_enable"] == "Enable (recoverable)"
        assert prot["over_voltage_enable"] == "Enable (recoverable)"
        assert prot["over_current_enable"] is None
        assert prot["stall_enable"] is None
        assert prot["lost_input_enable"] is None
        assert prot["short_circuit_enable"] == "N/A"

    def test_mechanical_limits(self):
        """Mechanical limits with scaling decoded."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()
        lim = result["limits_setting"]

        assert lim["max_torque_current"] == 2000
        assert lim["max_speed"] == pytest.approx(1000.0)
        assert lim["max_angle"] == pytest.approx(-360.0)
        assert lim["speed_ramp"] == 300
        assert lim["current_ramp"] == 500

    def test_stall_and_lost_input(self):
        """Stall threshold and lost input time decoded."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()
        prot = result["protection_setting"]

        assert prot["stall_threshold"] == 200
        assert prot["lost_input_time"] == 1000

    def test_trailer_valid_magic(self):
        """Trailer with 0x55AA magic accepted."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()
        trailer = result["trailer"]

        assert trailer["magic_valid"] is True
        assert trailer["magic"] == "0x55AA"
        assert trailer["version_byte_0"] == 0x01
        assert trailer["version_byte_1"] == 0x02

    def test_trailer_invalid_magic_warns_but_returns(self):
        """Invalid trailer magic logs warning but returns data."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        # Corrupt magic bytes
        config_data[102] = 0x00
        config_data[103] = 0x00
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        with patch("backend.rs485_driver.logger") as mock_logger:
            result = drv.read_full_config()

        assert result is not None
        assert result["trailer"]["magic_valid"] is False
        mock_logger.warning.assert_called()

    def test_short_response_rejected(self):
        """Response shorter than 104 bytes returns error."""
        drv = _make_driver()
        short_data = [0] * 50
        resp_frame = _build_response(0x14, 1, short_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()

        assert result is not None
        assert "error" in result
        assert "50 bytes" in result["error"]

    def test_timeout_returns_none(self):
        """No response returns None."""
        drv = _make_driver()
        drv.timeout = 0.05
        type(drv._serial).in_waiting = PropertyMock(return_value=0)
        drv._serial.read.return_value = b""

        result = drv.read_full_config()

        assert result is None

    def test_basic_setting_section(self):
        """Basic setting section includes brake voltage and ramp."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()
        basic = result["basic_setting"]

        assert basic["brake_resistor_voltage"] == pytest.approx(48.0)
        assert basic["current_ramp"] == 500

    def test_raw_hex_present(self):
        """Raw hex string included in response."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()

        assert "raw_hex" in result
        assert isinstance(result["raw_hex"], str)

    def test_max_angle_sentinel_returns_zero(self):
        """max_angle with 0xFFFFFFFF raw (int32 -1) returns 0.0."""
        drv = _make_driver()
        config_data = _build_104byte_config()
        # Set max_angle bytes [76-79] to 0xFFFFFFFF (int32 = -1)
        config_data[76:80] = [0xFF, 0xFF, 0xFF, 0xFF]
        resp_frame = _build_response(0x14, 1, config_data)
        _setup_response(drv, resp_frame)

        result = drv.read_full_config()
        lim = result["limits_setting"]

        assert lim["max_angle"] == pytest.approx(0.0)


class TestDecodeEnableByte:
    """Test RS485MotorDriver._decode_enable_byte() static method."""

    def test_disable_0x00(self):
        """0x00 decodes to 'Disable'."""
        assert RS485MotorDriver._decode_enable_byte(0x00) == "Disable"

    def test_enable_recoverable(self):
        """0x01 decodes to 'Enable (recoverable)'."""
        assert RS485MotorDriver._decode_enable_byte(0x01) == "Enable (recoverable)"

    def test_enable_not_recoverable(self):
        """0x02 decodes to 'Enable (not recoverable)'."""
        assert RS485MotorDriver._decode_enable_byte(0x02) == "Enable (not recoverable)"

    def test_disable_0xff(self):
        """0xFF decodes to 'Disable'."""
        assert RS485MotorDriver._decode_enable_byte(0xFF) == "Disable"

    def test_unknown_value(self):
        """Unknown byte value includes hex representation."""
        result = RS485MotorDriver._decode_enable_byte(0x42)
        assert result == "Unknown (0x42)"


# ---------------------------------------------------------------------------
# 7.3 — read_system_state() tests
# ---------------------------------------------------------------------------


class TestReadSystemState:
    """Task 7.3: CMD 0x10 heartbeat echo validation."""

    def test_echo_with_zero_data_bytes(self):
        """Echo with 0 data bytes = success."""
        drv = _make_driver()
        resp_frame = _build_response(0x10, 1, [])
        _setup_response(drv, resp_frame)

        result = drv.read_system_state()

        assert result is not None
        assert result["alive"] is True
        assert result["data_len"] == 0

    def test_echo_with_unexpected_data_warns(self):
        """Echo with unexpected data bytes still succeeds."""
        drv = _make_driver()
        resp_frame = _build_response(0x10, 1, [0xFF, 0xAA])
        _setup_response(drv, resp_frame)

        with patch("backend.rs485_driver.logger") as mock_logger:
            result = drv.read_system_state()

        assert result is not None
        assert result["alive"] is True
        assert result["data_len"] == 2
        mock_logger.warning.assert_called()

    def test_timeout_returns_none(self):
        """No response returns None."""
        drv = _make_driver()
        drv.timeout = 0.05
        type(drv._serial).in_waiting = PropertyMock(return_value=0)
        drv._serial.read.return_value = b""

        result = drv.read_system_state()

        assert result is None

    def test_tx_frame_correct(self):
        """Verify TX frame for heartbeat."""
        drv = _make_driver(motor_id=1)
        drv.timeout = 0.05
        type(drv._serial).in_waiting = PropertyMock(return_value=0)
        drv._serial.read.return_value = b""

        drv.read_system_state()

        # TX: 3E 10 01 00 <checksum>
        # checksum = (0x3E + 0x10 + 0x01 + 0x00) & 0xFF = 0x4F
        expected = bytes([0x3E, 0x10, 0x01, 0x00, 0x4F])
        drv._serial.write.assert_called_with(expected)


# ---------------------------------------------------------------------------
# 7.4 — read_product_info_ext() new encoder fields
# ---------------------------------------------------------------------------


def _build_108byte_eeprom() -> list[int]:
    """Build a 108-byte EEPROM payload with known encoder values."""
    data = [0] * 108

    # Communication config (existing)
    data[0] = 0x1C  # RS485 divider (115200 baud)
    data[1] = 0x07  # CAN baud index
    data[2] = 0x01  # driver ID
    data[3] = 0x01  # bus_type_raw (should be CAN after fix)

    # Broadcast mode / spin direction (NEW)
    data[6] = 0x00  # broadcast_mode_raw (0=OFF)
    data[7] = 0x00  # spin_direction_raw (0=Normal)

    # Encoder fields (NEW)
    # Encoder Offset [4-5] LE uint16 = 1234
    data[4:6] = list(struct.pack("<H", 1234))
    # Align Ratio [8-9] LE uint16 = 567
    data[8:10] = list(struct.pack("<H", 567))
    # Align Voltage [10-11] LE uint16 = 500 -> /100 = 5.0
    data[10:12] = list(struct.pack("<H", 500))
    # Encoder Position [12] = 42
    data[12] = 42
    # Motor Phase Sequence [13]: 0xFF = Reverse
    data[13] = 0xFF

    # Encoder Type [92]: 0x01 = "16Bit Encoder"
    data[92] = 0x01

    # Over current threshold (existing)
    data[85] = 0x06

    # Reducer fields (NEW)
    # Reducer Align Value [88-89] LE uint16 = 789
    data[88:90] = list(struct.pack("<H", 789))
    # Reducer Zero Position [90-91] LE uint16 = 321
    data[90:92] = list(struct.pack("<H", 321))

    # EEPROM trailer
    data[104:106] = list(struct.pack("<H", 0x1234))  # version
    data[106:108] = list(struct.pack("<H", 0x55AA))  # magic

    return data


class TestProductInfoExtEncoderFields:
    """Task 7.4: CMD 0x16 extended encoder field decode."""

    def test_encoder_fields_present(self):
        """New encoder fields present in response dict."""
        drv = _make_driver()
        eeprom_data = _build_108byte_eeprom()
        resp_frame = _build_response(0x16, 1, eeprom_data)
        _setup_response(drv, resp_frame)

        result = drv.read_product_info_ext()

        assert result is not None
        assert "encoder_setting" in result
        enc = result["encoder_setting"]
        assert enc["encoder_offset"] == 1234
        assert enc["align_ratio"] == 567
        assert enc["encoder_position"] == 42
        assert enc["reducer_align_value"] == 789
        assert enc["reducer_zero_position"] == 321

    def test_align_voltage_scaled(self):
        """Align voltage scaled by /100."""
        drv = _make_driver()
        eeprom_data = _build_108byte_eeprom()
        resp_frame = _build_response(0x16, 1, eeprom_data)
        _setup_response(drv, resp_frame)

        result = drv.read_product_info_ext()
        enc = result["encoder_setting"]

        assert enc["align_voltage"] == pytest.approx(5.0)

    def test_existing_fields_preserved(self):
        """Existing basic_setting and protection_setting still present."""
        drv = _make_driver()
        eeprom_data = _build_108byte_eeprom()
        resp_frame = _build_response(0x16, 1, eeprom_data)
        _setup_response(drv, resp_frame)

        result = drv.read_product_info_ext()

        assert "basic_setting" in result
        assert "protection_setting" in result
        assert "eeprom_version" in result
        assert "eeprom_magic_valid" in result
        assert result["basic_setting"]["driver_id"] == 1

    def test_encoder_type_decoded(self):
        """Encoder type decoded from d[92] via _ENCODER_TYPE_MAP."""
        drv = _make_driver()
        eeprom_data = _build_108byte_eeprom()
        resp_frame = _build_response(0x16, 1, eeprom_data)
        _setup_response(drv, resp_frame)

        result = drv.read_product_info_ext()
        enc = result["encoder_setting"]

        assert enc["encoder_type"] == "16Bit Encoder"
        assert enc["encoder_type_raw"] == 1

    def test_motor_phase_sequence_reverse(self):
        """Motor phase sequence decoded from d[13]: 0xFF = Reverse."""
        drv = _make_driver()
        eeprom_data = _build_108byte_eeprom()
        resp_frame = _build_response(0x16, 1, eeprom_data)
        _setup_response(drv, resp_frame)

        result = drv.read_product_info_ext()
        enc = result["encoder_setting"]

        assert enc["motor_phase_sequence"] == "Reverse"
        assert enc["motor_phase_seq_raw"] == 0xFF

    def test_motor_phase_sequence_normal(self):
        """Motor phase sequence d[13]=0x00 = Normal."""
        drv = _make_driver()
        eeprom_data = _build_108byte_eeprom()
        eeprom_data[13] = 0x00
        resp_frame = _build_response(0x16, 1, eeprom_data)
        _setup_response(drv, resp_frame)

        result = drv.read_product_info_ext()
        enc = result["encoder_setting"]

        assert enc["motor_phase_sequence"] == "Normal"

    def test_broadcast_mode_and_spin_direction(self):
        """Broadcast mode and spin direction from d[6], d[7]."""
        drv = _make_driver()
        eeprom_data = _build_108byte_eeprom()
        resp_frame = _build_response(0x16, 1, eeprom_data)
        _setup_response(drv, resp_frame)

        result = drv.read_product_info_ext()
        bs = result["basic_setting"]

        assert bs["broadcast_mode"] == 0  # integer, not string
        assert bs["spin_direction"] == 0  # integer, not string


# ---------------------------------------------------------------------------
# 7.5 — bus_type mapping fix
# ---------------------------------------------------------------------------


class TestBusTypeMapping:
    """Task 7.5: CMD 0x16 bus_type inversion fix."""

    def test_bus_type_0x01_is_can(self):
        """data[3]=0x01 decoded as CAN."""
        drv = _make_driver()
        eeprom_data = _build_108byte_eeprom()
        eeprom_data[3] = 0x01
        resp_frame = _build_response(0x16, 1, eeprom_data)
        _setup_response(drv, resp_frame)

        result = drv.read_product_info_ext()

        assert result["basic_setting"]["bus_type"] == "CAN"
        assert result["basic_setting"]["bus_type_raw"] == 1

    def test_bus_type_0x00_is_rs485(self):
        """data[3]=0x00 decoded as RS485."""
        drv = _make_driver()
        eeprom_data = _build_108byte_eeprom()
        eeprom_data[3] = 0x00
        resp_frame = _build_response(0x16, 1, eeprom_data)
        _setup_response(drv, resp_frame)

        result = drv.read_product_info_ext()

        assert result["basic_setting"]["bus_type"] == "RS485"
        assert result["basic_setting"]["bus_type_raw"] == 0

    def test_bus_type_unknown_value(self):
        """Unknown bus_type value shows raw."""
        drv = _make_driver()
        eeprom_data = _build_108byte_eeprom()
        eeprom_data[3] = 0x05
        resp_frame = _build_response(0x16, 1, eeprom_data)
        _setup_response(drv, resp_frame)

        result = drv.read_product_info_ext()

        assert "unknown" in result["basic_setting"]["bus_type"]


# ---------------------------------------------------------------------------
# 7.5b — Motor model name lookup functions
# ---------------------------------------------------------------------------


class TestMotorModelLookups:
    """Tests for _lookup_motor_poles and _lookup_reduction_ratio."""

    def test_mg6010_poles(self):
        """MG6010E-i6 -> 28 poles."""
        assert _lookup_motor_poles("MG6010E-i6") == 28

    def test_mg6012_poles(self):
        """MG6012E-i10 -> 28 poles."""
        assert _lookup_motor_poles("MG6012E-i10") == 28

    def test_unknown_motor_poles(self):
        """Unknown motor model -> None."""
        assert _lookup_motor_poles("XYZMOTOR-i3") is None

    def test_empty_motor_poles(self):
        """Empty string -> None."""
        assert _lookup_motor_poles("") is None

    def test_reduction_ratio_i6(self):
        """MG6010E-i6 -> ratio 6."""
        assert _lookup_reduction_ratio("MG6010E-i6") == 6

    def test_reduction_ratio_i10(self):
        """MG6012E-i10 -> ratio 10."""
        assert _lookup_reduction_ratio("MG6012E-i10") == 10

    def test_reduction_ratio_no_suffix(self):
        """Motor name without -iN suffix -> None."""
        assert _lookup_reduction_ratio("MG6010E") is None

    def test_reduction_ratio_empty(self):
        """Empty string -> None."""
        assert _lookup_reduction_ratio("") is None


# ---------------------------------------------------------------------------
# 7.6 — API endpoint tests
# ---------------------------------------------------------------------------


def _make_test_app():
    """Create a FastAPI app with motor_router for testing."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(motor_router)
    return app


def _make_mock_driver(motor_id: int = 1):
    """Create a mock RS485MotorDriver for API tests."""
    drv = MagicMock(spec=RS485MotorDriver)
    drv.port = "/dev/ttyUSB0"
    drv.motor_id = motor_id
    drv._serial = MagicMock()
    drv._serial.is_open = True
    return drv


def _make_bridge_with_driver(motor_id: int = 1):
    """Create a MotorConfigBridge with a mock RS485 driver."""
    bridge = MotorConfigBridge()
    drv = _make_mock_driver(motor_id)
    bridge.set_rs485_driver(drv)
    return bridge, drv


class TestAPIEndpoints:
    """Task 7.6: API endpoint tests for protocol parity routes."""

    def test_firmware_version_endpoint(self):
        """GET /api/motor/{id}/firmware_version returns driver data."""
        from fastapi.testclient import TestClient

        bridge, drv = _make_bridge_with_driver(motor_id=1)
        drv.read_firmware_version.return_value = {
            "firmware_build": 0x0123,
            "firmware_build_hex": "0x0123",
            "byte_0": 0x23,
            "byte_1": 0x01,
        }

        app = _make_test_app()
        with patch.object(motor_api_module, "_bridge", bridge):
            with TestClient(app) as client:
                resp = client.get("/api/motor/1/firmware_version")

        assert resp.status_code == 200
        data = resp.json()
        assert data["firmware_build"] == 0x0123
        assert data["firmware_build_hex"] == "0x0123"
        drv.read_firmware_version.assert_called_once()

    def test_full_config_endpoint(self):
        """GET /api/motor/{id}/full_config returns structured config."""
        from fastapi.testclient import TestClient

        bridge, drv = _make_bridge_with_driver(motor_id=1)
        drv.read_full_config.return_value = {
            "pid_setting": {"angle_kp": 30},
            "protection_setting": {"motor_temp_limit": 80},
            "limits_setting": {"max_torque_current": 2000},
            "basic_setting": {"current_ramp": 500},
            "trailer": {"magic_valid": True},
            "raw_hex": "00" * 104,
        }

        app = _make_test_app()
        with patch.object(motor_api_module, "_bridge", bridge):
            with TestClient(app) as client:
                resp = client.get("/api/motor/1/full_config")

        assert resp.status_code == 200
        data = resp.json()
        assert "pid_setting" in data
        assert "protection_setting" in data
        assert "limits_setting" in data
        assert "basic_setting" in data
        assert "trailer" in data
        assert data["pid_setting"]["angle_kp"] == 30
        drv.read_full_config.assert_called_once()

    def test_heartbeat_endpoint(self):
        """GET /api/motor/{id}/heartbeat returns alive status."""
        from fastapi.testclient import TestClient

        bridge, drv = _make_bridge_with_driver(motor_id=1)
        drv.read_system_state.return_value = {
            "alive": True,
            "data_len": 0,
        }

        app = _make_test_app()
        with patch.object(motor_api_module, "_bridge", bridge):
            with TestClient(app) as client:
                resp = client.get("/api/motor/1/heartbeat")

        assert resp.status_code == 200
        data = resp.json()
        assert data["alive"] is True
        assert data["data_len"] == 0
        drv.read_system_state.assert_called_once()

    def test_read_all_settings_endpoint(self):
        """POST /api/motor/{id}/read_all_settings returns combined."""
        from fastapi.testclient import TestClient

        bridge, drv = _make_bridge_with_driver(motor_id=1)
        drv.read_firmware_version.return_value = {
            "firmware_build": 0x0123,
        }
        drv.read_product_info.return_value = {
            "model": "MG6012",
            "motor_name": "MG6010E-i6",
        }
        drv.read_product_info_ext.return_value = {
            "basic_setting": {"driver_id": 1},
            "encoder_setting": {
                "encoder_offset": 3749,
            },
        }
        drv.read_full_config.return_value = {
            "pid_setting": {"angle_kp": 30},
        }
        drv.read_system_state.return_value = {
            "alive": True,
        }

        app = _make_test_app()
        with patch.object(motor_api_module, "_bridge", bridge):
            with TestClient(app) as client:
                resp = client.post("/api/motor/1/read_all_settings")

        assert resp.status_code == 200
        data = resp.json()
        assert "firmware_version" in data
        assert "product_info" in data
        assert "ext_config" in data
        assert "full_config" in data
        assert "heartbeat" in data
        assert data["_success"] is True
        assert "_failed" not in data
        # Verify motor_poles and reduction_ratio derived from motor_name
        enc = data["ext_config"]["encoder_setting"]
        assert enc["motor_poles"] == 28
        assert enc["reduction_ratio"] == 6

    def test_read_all_settings_partial_failure(self):
        """POST read_all_settings with some failures includes _failed."""
        from fastapi.testclient import TestClient

        bridge, drv = _make_bridge_with_driver(motor_id=1)
        # firmware_version and heartbeat succeed
        drv.read_firmware_version.return_value = {
            "firmware_build": 0x0123,
        }
        drv.read_system_state.return_value = {
            "alive": True,
        }
        # product_info, ext_config, full_config fail (return None)
        drv.read_product_info.return_value = None
        drv.read_product_info_ext.return_value = None
        drv.read_full_config.return_value = None

        app = _make_test_app()
        with patch.object(motor_api_module, "_bridge", bridge):
            with TestClient(app) as client:
                resp = client.post("/api/motor/1/read_all_settings")

        assert resp.status_code == 200
        data = resp.json()
        assert data["_success"] is False
        assert "_failed" in data
        failed = data["_failed"]
        assert "product_info" in failed
        assert "ext_config" in failed
        assert "full_config" in failed
        # These should have succeeded
        assert "firmware_version" in data
        assert "heartbeat" in data

    def test_ext_config_endpoint_enriches_motor_poles(self):
        """GET /ext_config derives motor_poles/reduction_ratio from product info.

        Bug 1 fix: the individual ext_config endpoint must also inject
        motor_poles and reduction_ratio (not just read_all_settings).
        """
        from fastapi.testclient import TestClient

        bridge, drv = _make_bridge_with_driver(motor_id=1)
        drv.read_product_info_ext.return_value = {
            "basic_setting": {"driver_id": 1},
            "encoder_setting": {
                "encoder_offset": 3749,
            },
        }
        drv.read_product_info.return_value = {
            "model": "MG6012",
            "motor_name": "MG6010E-i6",
        }

        app = _make_test_app()
        with patch.object(motor_api_module, "_bridge", bridge):
            with TestClient(app) as client:
                resp = client.get("/api/motor/1/ext_config")

        assert resp.status_code == 200
        data = resp.json()
        enc = data["encoder_setting"]
        assert enc["motor_poles"] == 28
        assert enc["reduction_ratio"] == 6
        drv.read_product_info_ext.assert_called_once()
        drv.read_product_info.assert_called_once()

    def test_ext_config_endpoint_without_product_info(self):
        """GET /ext_config still works when product_info returns None.

        Motor poles and reduction ratio should not be present, but the
        endpoint must not fail.
        """
        from fastapi.testclient import TestClient

        bridge, drv = _make_bridge_with_driver(motor_id=1)
        drv.read_product_info_ext.return_value = {
            "basic_setting": {"driver_id": 1},
            "encoder_setting": {
                "encoder_offset": 3749,
            },
        }
        drv.read_product_info.return_value = None

        app = _make_test_app()
        with patch.object(motor_api_module, "_bridge", bridge):
            with TestClient(app) as client:
                resp = client.get("/api/motor/1/ext_config")

        assert resp.status_code == 200
        data = resp.json()
        enc = data["encoder_setting"]
        # motor_poles and reduction_ratio should NOT be injected
        assert "motor_poles" not in enc
        assert "reduction_ratio" not in enc

    def test_firmware_version_no_driver(self):
        """GET firmware_version returns 503 when driver is None."""
        from fastapi.testclient import TestClient

        bridge = MotorConfigBridge()
        # No RS485 driver set — _rs485_driver is None

        app = _make_test_app()
        with patch.object(motor_api_module, "_bridge", bridge):
            with TestClient(app) as client:
                resp = client.get("/api/motor/1/firmware_version")

        assert resp.status_code == 503
        assert "not available" in resp.json()["detail"].lower()

    def test_firmware_version_invalid_motor_id(self):
        """GET firmware_version returns 400 for motor_id=0."""
        from fastapi.testclient import TestClient

        bridge, drv = _make_bridge_with_driver(motor_id=1)

        app = _make_test_app()
        with patch.object(motor_api_module, "_bridge", bridge):
            with TestClient(app) as client:
                resp = client.get("/api/motor/0/firmware_version")

        assert resp.status_code == 400
        assert "invalid" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 7.7 — serial_log_ws late-driver registration test
# ---------------------------------------------------------------------------


class TestSerialLogWsLateDriver:
    """Task 7.7: WebSocket late-driver registration via keepalive."""

    def test_late_driver_registration(self):
        """WS connects with no driver, then picks it up on keepalive.

        1. Connect with _bridge._rs485_driver = None
        2. After keepalive timeout, driver appears on bridge
        3. WS re-checks and registers listener on the new driver
        """
        from fastapi.testclient import TestClient

        bridge = MotorConfigBridge()
        # Start with no driver
        assert bridge._rs485_driver is None

        late_drv = _make_mock_driver(motor_id=1)
        late_drv.get_frame_log.return_value = []

        app = _make_test_app()
        with patch.object(motor_api_module, "_bridge", bridge):
            with TestClient(app) as client:
                with client.websocket_connect("/api/motor/ws/serial_log") as ws:
                    # At this point, no driver => keepalive sends ping
                    # after 30s timeout. We simulate by injecting driver
                    # before the ping arrives.
                    bridge.set_rs485_driver(late_drv)

                    # The next keepalive cycle re-checks the driver.
                    # In a real scenario the 30s timeout fires; here
                    # we just send a frame through the queue to prove
                    # the listener was registered. But TestClient WS
                    # is synchronous, so we read the ping that fires.

                    # Receive the keepalive ping (30s timeout in handler)
                    # With TestClient the timeout still applies; just
                    # verify the connection stays alive and can receive.
                    msg = ws.receive_json(mode="text")
                    assert msg["type"] == "ping"

                    # After ping, _sync_listener should have registered
                    # on late_drv
                    late_drv.add_frame_listener.assert_called()
