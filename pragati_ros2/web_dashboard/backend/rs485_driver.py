"""RS485 Motor Driver for MG6010E-i6 motors via UART adapter."""

import logging
import re
import struct
import threading
import time
from collections import deque
from typing import Optional

try:
    import serial
except ImportError:
    serial = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RS485 Protocol Constants
# ---------------------------------------------------------------------------
RS485_HEADER = 0x3E

# Read commands
CMD_READ_PID = 0x40
CMD_MOTOR_OFF = 0x80
CMD_MOTOR_STOP = 0x81
CMD_MOTOR_ON = 0x88
CMD_READ_ENCODER = 0x90
CMD_READ_MULTI_TURN_ANGLE = 0x92
CMD_READ_SINGLE_TURN_ANGLE = 0x94
CMD_READ_STATUS_1 = 0x9A
CMD_CLEAR_ERRORS = 0x9B
CMD_READ_STATUS_2 = 0x9C
CMD_READ_STATUS_3 = 0x9D

# Write commands
CMD_WRITE_PID_RAM = 0x42
CMD_WRITE_PID_ROM = 0x44
CMD_READ_ACCELERATION = 0x33
CMD_WRITE_ACCELERATION_RAM = 0x34
CMD_READ_MAX_TORQUE = 0x37
CMD_WRITE_MAX_TORQUE_RAM = 0x38
CMD_SET_ENCODER_ZERO = 0x19
CMD_WRITE_ENCODER_OFFSET_ROM = 0x91

# Brake / restore / zero commands
CMD_BRAKE_CONTROL = 0x8C
CMD_MOTOR_RESTORE = 0x89
CMD_CLEAR_MULTI_TURN = 0x93
CMD_SET_ZERO_RAM = 0x95

# System / config commands
CMD_READ_SYSTEM_STATE = 0x10  # Heartbeat / echo (0 data bytes)
CMD_READ_PRODUCT_INFO = 0x12
CMD_READ_FULL_CONFIG = 0x14  # 104-byte full config read
CMD_READ_PRODUCT_INFO_EXT = 0x16  # Undocumented, 108-byte response
CMD_READ_FIRMWARE_VERSION = 0x1F  # 2-byte firmware build info

# Control commands
CMD_TORQUE_CLOSED_LOOP = 0xA1
CMD_SPEED_CLOSED_LOOP = 0xA2
CMD_POSITION_ABSOLUTE_1 = 0xA3
CMD_POSITION_ABSOLUTE_2 = 0xA4
CMD_POSITION_SINGLE_1 = 0xA5
CMD_POSITION_SINGLE_2 = 0xA6
CMD_POSITION_INCREMENT_1 = 0xA7
CMD_POSITION_INCREMENT_2 = 0xA8

# Gear ratio for MG6010E-i6
GEAR_RATIO = 6.0

# Motor pole count by model family (from hardware datasheets).
# Key = prefix of motor_name from CMD 0x12 product info.
_MOTOR_POLES_MAP = {
    "MG6010": 28,
    "MG6012": 28,
    "MG4005": 14,
    "MG5010": 20,
}

# Encoder type index → display string (from LK Motor Tool dropdown)
_ENCODER_TYPE_MAP = {
    0: "14Bit Encoder",
    1: "16Bit Encoder",
}


def _lookup_motor_poles(motor_name: str) -> Optional[int]:
    """Derive motor pole count from product info motor name string."""
    if not motor_name:
        return None
    upper = motor_name.upper()
    for prefix, poles in _MOTOR_POLES_MAP.items():
        if upper.startswith(prefix.upper()):
            return poles
    return None


def _lookup_reduction_ratio(motor_name: str) -> Optional[int]:
    """Derive reduction ratio from motor model suffix.

    Convention: MG6010E-i6 → 'i6' means internal gear ratio 6:1.
    """
    if not motor_name:
        return None
    m = re.search(r"-i(\d+)", motor_name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


# Command name lookup for serial monitor display
_CMD_NAMES = {
    0x10: "ReadSystemState",
    0x12: "ReadProductInfo",
    0x14: "ReadFullConfig",
    0x16: "ReadProductInfoExt",
    0x1F: "ReadFirmwareVersion",
    0x19: "SetEncoderZeroROM",
    0x33: "ReadAcceleration",
    0x34: "WriteAccelerationRAM",
    0x37: "ReadMaxTorque",
    0x38: "WriteMaxTorqueRAM",
    0x40: "ReadParam",
    0x42: "WriteParamRAM",
    0x44: "WriteParamROM",
    0x80: "MotorOFF",
    0x81: "MotorSTOP",
    0x88: "MotorON",
    0x89: "MotorRestore",
    0x8C: "BrakeControl",
    0x90: "ReadEncoder",
    0x91: "WriteEncoderOffsetROM",
    0x92: "ReadMultiTurnAngle",
    0x93: "ClearMultiTurn",
    0x94: "ReadSingleTurnAngle",
    0x95: "SetZeroRAM",
    0x9A: "ReadState1",
    0x9B: "ClearError",
    0x9C: "ReadState2",
    0x9D: "ReadState3",
    0xA1: "TorqueControl",
    0xA2: "SpeedControl",
    0xA3: "PositionAbs1",
    0xA4: "PositionAbs2",
    0xA5: "PositionSingle1",
    0xA6: "PositionSingle2",
    0xA7: "PositionIncr1",
    0xA8: "PositionIncr2",
}
# Current conversion: raw -2048..2048 maps to -33A..33A
CURRENT_SCALE = 33.0 / 2048.0
# Phase current scale: raw / 64.0 = Amps
PHASE_CURRENT_SCALE = 1.0 / 64.0

# PID ParamID values (used with CMD_READ_PID / CMD_WRITE_PID_RAM / CMD_WRITE_PID_ROM)
PID_PARAM_ANGLE = 0x96
PID_PARAM_SPEED = 0x97
PID_PARAM_CURRENT = 0x98

# Extended ParamID values (used with CMD_READ_PID / CMD_WRITE_PID_RAM / CMD_WRITE_PID_ROM)
PARAM_MAX_TORQUE_CURRENT = 0x99
PARAM_MAX_SPEED = 0x9A
PARAM_MAX_ANGLE_LOW = 0x9B
PARAM_MAX_ANGLE_HIGH = 0x9C
PARAM_CURRENT_RAMP = 0x9D
PARAM_SPEED_RAMP = 0x9E


# ---------------------------------------------------------------------------
# Error Flag Decoding
# ---------------------------------------------------------------------------
def decode_error_flags_short(error_byte: int) -> dict:
    """Decode error byte into short-key flags.

    Matches the WebSocket format used by the ROS2 motor node.
    """
    return {
        "uvp": bool(error_byte & 0x01),
        "ovp": bool(error_byte & 0x02),
        "dtp": bool(error_byte & 0x04),
        "mtp": bool(error_byte & 0x08),
        "ocp": bool(error_byte & 0x10),
        "scp": bool(error_byte & 0x20),
        "sp": bool(error_byte & 0x40),
        "lip": bool(error_byte & 0x80),
    }


def decode_error_flags_long(error_byte: int) -> dict:
    """Decode error byte into long-key flags.

    Matches the REST format used by motor_api.py.
    """
    return {
        "undervoltage_protection": bool(error_byte & 0x01),
        "overvoltage_protection": bool(error_byte & 0x02),
        "drive_temperature_protection": bool(error_byte & 0x04),
        "motor_temperature_protection": bool(error_byte & 0x08),
        "overcurrent_protection": bool(error_byte & 0x10),
        "short_circuit_protection": bool(error_byte & 0x20),
        "stall_protection": bool(error_byte & 0x40),
        "locked_rotor_protection": bool(error_byte & 0x80),
    }


# ---------------------------------------------------------------------------
# RS485 Motor Driver
# ---------------------------------------------------------------------------
class RS485MotorDriver:
    """Communicates with MG6010E-i6 motor via RS485 UART protocol.

    Thread-safe: all serial I/O is guarded by an internal lock.
    Requires pyserial (``pip install pyserial``).
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baud: int = 115200,
        motor_id: int = 1,
        timeout: float = 0.3,
    ):
        if serial is None:
            raise ImportError(
                "pyserial is required but not installed. " "Install with: pip install pyserial"
            )
        self.port = port
        self.baud = baud
        self.motor_id = motor_id
        self.timeout = timeout
        self._lock = threading.Lock()
        self._serial: Optional[serial.Serial] = None

        # Serial monitor - circular buffer of TX/RX frames
        self._frame_log: deque = deque(maxlen=500)
        self._frame_log_lock = threading.Lock()
        self._frame_listeners: list = []  # callbacks for real-time streaming
        self._comm_error_count = 0

    # -- Connection ---------------------------------------------------------

    def connect(self) -> bool:
        """Open the serial port. Returns True on success."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05,
            )
            logger.info("Serial port %s opened at %d baud", self.port, self.baud)
            return True
        except Exception as e:
            logger.error("Failed to open serial port %s: %s", self.port, e)
            return False

    def disconnect(self):
        """Close the serial port."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serial port closed")

    # -- Serial Monitor -----------------------------------------------------

    def _log_frame(self, direction, raw_bytes, cmd_name=None):
        """Log a TX or RX frame to the circular buffer and notify listeners."""
        entry = {
            "ts": time.time(),
            "dir": direction,  # "TX" or "RX"
            "hex": " ".join(f"{b:02X}" for b in raw_bytes),
            "cmd": cmd_name,
            "len": len(raw_bytes),
        }
        with self._frame_log_lock:
            self._frame_log.append(entry)
        # Notify real-time listeners (for WebSocket streaming)
        for cb in self._frame_listeners:
            try:
                cb(entry)
            except Exception:
                pass

    def add_frame_listener(self, callback):
        """Register a callback for real-time frame notifications."""
        self._frame_listeners.append(callback)

    def remove_frame_listener(self, callback):
        """Remove a frame listener."""
        try:
            self._frame_listeners.remove(callback)
        except ValueError:
            pass

    def get_frame_log(self, limit=100):
        """Get recent frames from the log buffer."""
        with self._frame_log_lock:
            entries = list(self._frame_log)
        return entries[-limit:] if limit else entries

    def get_comm_error_count(self):
        """Get the communication error counter."""
        return self._comm_error_count

    def clear_frame_log(self):
        """Clear the frame log buffer and reset error counter."""
        with self._frame_log_lock:
            self._frame_log.clear()
        self._comm_error_count = 0

    # -- Frame Helpers ------------------------------------------------------

    @staticmethod
    def _checksum(data: list[int]) -> int:
        """Compute single-byte checksum (sum mod 256)."""
        return sum(data) & 0xFF

    @staticmethod
    def _build_frame(
        cmd: int,
        motor_id: int,
        data: Optional[list[int]] = None,
    ) -> bytes:
        """Build RS485 frame.

        Format: [0x3E][CMD][ID][LEN][CHECKSUM][DATA...][DATA_CHECKSUM]
        """
        frame = [RS485_HEADER, cmd, motor_id]
        if data is None or len(data) == 0:
            frame.append(0x00)
            frame.append(RS485MotorDriver._checksum(frame))
            return bytes(frame)
        else:
            frame.append(len(data))
            frame.append(RS485MotorDriver._checksum(frame))
            frame.extend(data)
            frame.append(RS485MotorDriver._checksum(data))
            return bytes(frame)

    @staticmethod
    def _parse_response(raw: bytes) -> Optional[dict]:
        """Parse RS485 response frame.

        Returns dict with keys: cmd, motor_id, data_len, data.
        """
        if len(raw) < 5 or raw[0] != RS485_HEADER:
            return None

        cmd = raw[1]
        motor_id = raw[2]
        data_len = raw[3]
        frame_checksum = raw[4]

        expected_checksum = RS485MotorDriver._checksum(list(raw[0:4]))
        if expected_checksum != frame_checksum:
            logger.warning(
                "Frame checksum mismatch: expected 0x%02X got 0x%02X",
                expected_checksum,
                frame_checksum,
            )
            return None

        result = {
            "cmd": cmd,
            "motor_id": motor_id,
            "data_len": data_len,
        }

        if data_len > 0:
            expected_total = 5 + data_len + 1
            if len(raw) < expected_total:
                logger.warning(
                    "Incomplete data: expected %d bytes, got %d",
                    expected_total,
                    len(raw),
                )
                return None
            result["data"] = raw[5 : 5 + data_len]
            data_checksum = raw[5 + data_len]
            expected_data_cs = RS485MotorDriver._checksum(list(result["data"]))
            if expected_data_cs != data_checksum:
                logger.warning("Data checksum mismatch")
                return None
        else:
            result["data"] = b""

        return result

    _SEND_RECV_MAX_RETRIES = 2

    def _send_receive(
        self,
        cmd: int,
        data: Optional[list[int]] = None,
    ) -> Optional[dict]:
        """Send command and wait for matching response. Thread-safe.

        The motor (or RS485 bus) can have stale/buffered responses from
        previous commands.  We validate that the response command byte
        matches the sent command.  On mismatch we drain, resend, and
        retry up to ``_SEND_RECV_MAX_RETRIES`` times.
        """
        if not self._serial or not self._serial.is_open:
            return None

        frame = self._build_frame(cmd, self.motor_id, data)
        cmd_name = _CMD_NAMES.get(cmd, f"0x{cmd:02X}")

        with self._lock:
            for _attempt in range(self._SEND_RECV_MAX_RETRIES):
                # Drain any stale data before sending
                self._serial.reset_input_buffer()
                time.sleep(
                    0.01
                )  # BLOCKING_SLEEP_OK: serial port drain — dedicated serial thread — reviewed 2026-03-14
                while self._serial.in_waiting > 0:
                    self._serial.read(self._serial.in_waiting)
                    time.sleep(
                        0.005
                    )  # BLOCKING_SLEEP_OK: serial port drain — dedicated serial thread — reviewed 2026-03-14

                self._serial.write(frame)
                self._serial.flush()
                self._log_frame("TX", frame, cmd_name=cmd_name)

                start = time.time()
                rx_buffer = b""
                matched = False
                while (time.time() - start) < self.timeout:
                    if self._serial.in_waiting > 0:
                        rx_buffer += self._serial.read(self._serial.in_waiting)
                        if len(rx_buffer) >= 5 and rx_buffer[0] == RS485_HEADER:
                            resp_data_len = rx_buffer[3]
                            expected_len = 5 + resp_data_len + (1 if resp_data_len > 0 else 0)
                            if len(rx_buffer) >= expected_len:
                                resp_cmd = rx_buffer[1]
                                if resp_cmd == cmd:
                                    matched = True
                                    rx_raw = rx_buffer[:expected_len]
                                    self._log_frame("RX", rx_raw, cmd_name=cmd_name)
                                    return self._parse_response(rx_raw)
                                # Wrong command — discard and retry
                                self._comm_error_count += 1
                                logger.debug(
                                    "CMD mismatch: sent 0x%02X got 0x%02X, " "retry %d/%d",
                                    cmd,
                                    resp_cmd,
                                    _attempt + 1,
                                    self._SEND_RECV_MAX_RETRIES,
                                )
                                break  # break inner while, go to next attempt
                    time.sleep(
                        0.005
                    )  # BLOCKING_SLEEP_OK: serial port drain — dedicated serial thread — reviewed 2026-03-14

                if matched:
                    break  # pragma: no cover — already returned above

            logger.warning("Timeout waiting for response to cmd 0x%02X", cmd)
            self._comm_error_count += 1
            return None

    # -- Read Commands ------------------------------------------------------

    def read_status_1(self) -> Optional[dict]:
        """Read Status 1 (0x9A): temperature, voltage, error flags."""
        resp = self._send_receive(CMD_READ_STATUS_1)
        if not resp or len(resp.get("data", b"")) < 7:
            return None
        d = resp["data"]
        temp = struct.unpack_from("<b", d, 0)[0]
        voltage = struct.unpack_from("<H", d, 1)[0] * 0.01
        error_byte = d[6] if len(d) > 6 else 0
        result = {
            "temperature_c": float(temp),
            "voltage_v": round(voltage, 1),
            "error_byte": error_byte,
        }
        result["error_flags"] = {
            "under_voltage": bool(error_byte & 0x01),
            "over_voltage": bool(error_byte & 0x02),
            "driver_over_temp": bool(error_byte & 0x04),
            "motor_over_temp": bool(error_byte & 0x08),
            "over_current": bool(error_byte & 0x10),
            "short_circuit": bool(error_byte & 0x20),
            "stall": bool(error_byte & 0x40),
            "lost_input_timeout": bool(error_byte & 0x80),
        }
        result["has_error"] = error_byte != 0
        return result

    def read_status_2(self) -> Optional[dict]:
        """Read Status 2 (0x9C): temperature, torque current, speed, encoder."""
        resp = self._send_receive(CMD_READ_STATUS_2)
        if not resp or len(resp.get("data", b"")) < 7:
            return None
        d = resp["data"]
        temp = struct.unpack_from("<b", d, 0)[0]
        iq_raw = struct.unpack_from("<h", d, 1)[0]
        speed_raw = struct.unpack_from("<h", d, 3)[0]
        encoder = struct.unpack_from("<H", d, 5)[0]
        return {
            "temperature_c": float(temp),
            "torque_current_a": round(iq_raw * CURRENT_SCALE, 3),
            "speed_dps": float(speed_raw),
            "encoder_position": encoder,
        }

    def read_status_3(self) -> Optional[dict]:
        """Read Status 3 (0x9D): phase currents A, B, C."""
        resp = self._send_receive(CMD_READ_STATUS_3)
        if not resp or len(resp.get("data", b"")) < 7:
            return None
        d = resp["data"]
        phase_a = struct.unpack_from("<h", d, 1)[0] * PHASE_CURRENT_SCALE
        phase_b = struct.unpack_from("<h", d, 3)[0] * PHASE_CURRENT_SCALE
        phase_c = struct.unpack_from("<h", d, 5)[0] * PHASE_CURRENT_SCALE
        return {
            "phase_current_a": [
                round(phase_a, 3),
                round(phase_b, 3),
                round(phase_c, 3),
            ]
        }

    def read_multi_turn_angle(self) -> Optional[float]:
        """Read multi-turn angle (0x92). Returns degrees.

        Response is int64_t (8 bytes), unit 0.01 deg/LSB.
        """
        resp = self._send_receive(CMD_READ_MULTI_TURN_ANGLE)
        if not resp or len(resp.get("data", b"")) < 8:
            return None
        d = resp["data"]
        angle_raw = struct.unpack_from("<q", d, 0)[0]
        return round(angle_raw * 0.01, 2)

    def read_single_turn_angle(self) -> Optional[float]:
        """Read single-turn angle (0x94). Returns degrees.

        The raw uint32 value is in units of 0.01 deg.  With a gear
        ratio of 6 the motor shaft rotates 6x per output revolution,
        so motor-side values up to ~2160 deg are normal (matching LK
        Motor Tool behaviour).  We return the raw value as-is —
        conversion to output-shaft degrees is the caller's concern.
        """
        resp = self._send_receive(CMD_READ_SINGLE_TURN_ANGLE)
        if not resp or len(resp.get("data", b"")) < 4:
            return None
        d = resp["data"]
        angle_raw = struct.unpack_from("<I", d, 0)[0]
        return round(angle_raw * 0.01, 2)

    def read_encoder(self) -> Optional[dict]:
        """Read encoder data (0x90)."""
        resp = self._send_receive(CMD_READ_ENCODER)
        if not resp or len(resp.get("data", b"")) < 6:
            return None
        d = resp["data"]
        encoder_pos = struct.unpack_from("<H", d, 0)[0]
        raw_pos = struct.unpack_from("<H", d, 2)[0]
        offset = struct.unpack_from("<H", d, 4)[0]
        return {
            "raw_value": raw_pos,
            "offset": offset,
            "original_value": encoder_pos,
        }

    def _read_pid_param(self, param_id: int) -> Optional[dict]:
        """Read one PID parameter group via 0x40 + ParamID.

        The host sends DATA = [ParamID, 0x00].  The motor responds with
        DATA = [ParamID, kp_lo, kp_hi, ki_lo, ki_hi, kd_lo, kd_hi]
        where each gain is a little-endian uint16.

        Returns dict with keys ``kp``, ``ki``, ``kd`` (int 0-65535),
        or *None* on failure.
        """
        resp = self._send_receive(CMD_READ_PID, [param_id, 0x00])
        if not resp:
            return None
        d = resp.get("data", b"")
        if len(d) < 7:
            logger.warning(
                "PID read 0x%02X: expected >=7 data bytes, got %d",
                param_id,
                len(d),
            )
            return None
        if d[0] != param_id:
            logger.warning(
                "PID read ParamID mismatch: sent 0x%02X got 0x%02X",
                param_id,
                d[0],
            )
            return None
        kp = struct.unpack_from("<H", d, 1)[0]
        ki = struct.unpack_from("<H", d, 3)[0]
        kd = struct.unpack_from("<H", d, 5)[0]
        return {"kp": kp, "ki": ki, "kd": kd}

    def read_pid(self) -> Optional[dict]:
        """Read all PID gains (angle, speed, current) via 0x40.

        Performs three sequential reads (ParamID 0x96, 0x97, 0x98).
        Returns a flat dict with keys like ``angle_kp``, ``speed_ki``,
        ``current_kd``, etc. (9 fields, all uint16 0-65535).
        Returns *None* only if all three reads fail.
        """
        result: dict = {}
        any_ok = False
        for param_id, prefix in [
            (PID_PARAM_ANGLE, "angle"),
            (PID_PARAM_SPEED, "speed"),
            (PID_PARAM_CURRENT, "current"),
        ]:
            time.sleep(
                0.01
            )  # BLOCKING_SLEEP_OK: RS485 protocol timing — dedicated serial thread — reviewed 2026-03-14
            group = self._read_pid_param(param_id)
            if group is not None:
                any_ok = True
                result[f"{prefix}_kp"] = group["kp"]
                result[f"{prefix}_ki"] = group["ki"]
                result[f"{prefix}_kd"] = group["kd"]
            else:
                logger.warning("Failed to read %s PID (ParamID 0x%02X)", prefix, param_id)
                result[f"{prefix}_kp"] = 0
                result[f"{prefix}_ki"] = 0
                result[f"{prefix}_kd"] = 0

        return result if any_ok else None

    def read_acceleration(self) -> Optional[float]:
        """Read acceleration (0x33). Returns dps/s."""
        resp = self._send_receive(CMD_READ_ACCELERATION)
        if not resp or len(resp.get("data", b"")) < 4:
            return None
        d = resp["data"]
        accel = struct.unpack_from("<i", d, 0)[0]
        return float(accel)

    def read_max_torque(self) -> Optional[int]:
        """Read max torque current ratio (0x37). Returns raw 0-2000."""
        resp = self._send_receive(CMD_READ_MAX_TORQUE)
        if not resp or len(resp.get("data", b"")) < 7:
            return None
        d = resp["data"]
        ratio = struct.unpack_from("<H", d, 4)[0]
        return ratio

    # -- Write / Control Commands -------------------------------------------

    def motor_on(self) -> Optional[dict]:
        """Motor ON (0x88)."""
        return self._send_receive(CMD_MOTOR_ON)

    def motor_off(self) -> Optional[dict]:
        """Motor OFF (0x80)."""
        return self._send_receive(CMD_MOTOR_OFF)

    def motor_stop(self) -> Optional[dict]:
        """Motor STOP (0x81)."""
        return self._send_receive(CMD_MOTOR_STOP)

    def clear_errors(self) -> Optional[dict]:
        """Clear motor errors (0x9B). Returns dict with error_byte."""
        resp = self._send_receive(CMD_CLEAR_ERRORS)
        if not resp or len(resp.get("data", b"")) < 7:
            return None
        d = resp["data"]
        error_byte = d[6] if len(d) > 6 else 0
        return {"error_byte": error_byte}

    def _write_pid_param(
        self, cmd: int, param_id: int, kp: int, ki: int, kd: int
    ) -> Optional[dict]:
        """Write one PID parameter group via cmd (0x42 or 0x44) + ParamID.

        DATA = [ParamID, kp_lo, kp_hi, ki_lo, ki_hi, kd_lo, kd_hi].
        Returns the parsed response or *None* on failure.
        """
        data = [param_id]
        data.extend(struct.pack("<H", kp & 0xFFFF))
        data.extend(struct.pack("<H", ki & 0xFFFF))
        data.extend(struct.pack("<H", kd & 0xFFFF))
        return self._send_receive(cmd, list(data))

    def write_pid_ram(self, gains: dict) -> Optional[dict]:
        """Write PID gains to RAM (0x42) for all three loops.

        ``gains`` keys: ``angle_kp``, ``angle_ki``, ``angle_kd``,
        ``speed_kp``, ``speed_ki``, ``speed_kd``,
        ``current_kp``, ``current_ki``, ``current_kd`` (uint16).
        """
        results = {}
        for param_id, prefix in [
            (PID_PARAM_ANGLE, "angle"),
            (PID_PARAM_SPEED, "speed"),
            (PID_PARAM_CURRENT, "current"),
        ]:
            time.sleep(
                0.01
            )  # BLOCKING_SLEEP_OK: RS485 protocol timing — dedicated serial thread — reviewed 2026-03-14
            resp = self._write_pid_param(
                CMD_WRITE_PID_RAM,
                param_id,
                gains.get(f"{prefix}_kp", 0),
                gains.get(f"{prefix}_ki", 0),
                gains.get(f"{prefix}_kd", 0),
            )
            results[prefix] = resp is not None
        return results

    def write_pid_rom(self, gains: dict) -> Optional[dict]:
        """Write PID gains to ROM (0x44) for all three loops.

        Same ``gains`` format as :meth:`write_pid_ram`.
        """
        results = {}
        for param_id, prefix in [
            (PID_PARAM_ANGLE, "angle"),
            (PID_PARAM_SPEED, "speed"),
            (PID_PARAM_CURRENT, "current"),
        ]:
            time.sleep(
                0.01
            )  # BLOCKING_SLEEP_OK: RS485 protocol timing — dedicated serial thread — reviewed 2026-03-14
            resp = self._write_pid_param(
                CMD_WRITE_PID_ROM,
                param_id,
                gains.get(f"{prefix}_kp", 0),
                gains.get(f"{prefix}_ki", 0),
                gains.get(f"{prefix}_kd", 0),
            )
            results[prefix] = resp is not None
        return results

    def set_encoder_zero(self) -> Optional[dict]:
        """Set current position as encoder zero (0x19)."""
        resp = self._send_receive(CMD_SET_ENCODER_ZERO)
        if not resp:
            return None
        return {"success": True}

    def write_acceleration(self, accel_dps_s: int) -> Optional[dict]:
        """Write acceleration to RAM (0x34). Units: dps/s."""
        data = list(struct.pack("<i", accel_dps_s))
        return self._send_receive(CMD_WRITE_ACCELERATION_RAM, data)

    def write_max_torque(self, ratio: int) -> Optional[dict]:
        """Write max torque current ratio to RAM (0x38).

        Args:
            ratio: Torque ratio 0-2000.
        """
        data = [0x00, 0x00, 0x00, 0x00] + list(struct.pack("<H", ratio)) + [0x00]
        return self._send_receive(CMD_WRITE_MAX_TORQUE_RAM, data)

    def send_torque_command(self, iq_raw: int) -> Optional[dict]:
        """Torque closed-loop (0xA1).

        RS485 frame: 2 data bytes — iqControl(int16).

        Args:
            iq_raw: Torque current in range -2048..2048.
        """
        data = list(struct.pack("<h", iq_raw))
        resp = self._send_receive(CMD_TORQUE_CLOSED_LOOP, data)
        return self._parse_status2_from_response(resp)

    def send_speed_command(self, speed_centideg_s: int) -> Optional[dict]:
        """Speed closed-loop (0xA2).

        RS485 frame: 4 data bytes — speedControl(int32, 0.01 dps/LSB).

        Args:
            speed_centideg_s: Speed in 0.01 dps units.
        """
        data = list(struct.pack("<i", speed_centideg_s))
        resp = self._send_receive(CMD_SPEED_CLOSED_LOOP, data)
        return self._parse_status2_from_response(resp)

    def send_position_command(
        self,
        angle_centideg: int,
        max_speed_dps: int = 0,
    ) -> Optional[dict]:
        """Position absolute with speed limit (0xA4).

        RS485 frame: 12 data bytes — angle(int64, 8B) + maxSpeed(uint32, 4B).
        maxSpeed is in 0.01 dps units on the wire.

        Args:
            angle_centideg: Target angle in 0.01 degree units.
            max_speed_dps: Maximum speed in dps. If 0, defaults to 360 dps.
        """
        if max_speed_dps == 0:
            max_speed_dps = 360  # safe default: 1 revolution per second
        speed_centidps = max_speed_dps * 100  # convert dps -> 0.01 dps
        angle_bytes = list(struct.pack("<q", angle_centideg))
        speed_bytes = list(struct.pack("<I", speed_centidps))
        data = angle_bytes[:8] + speed_bytes[:4]
        resp = self._send_receive(CMD_POSITION_ABSOLUTE_2, data)
        return self._parse_status2_from_response(resp)

    def send_position_command_no_speed(
        self,
        angle_centideg: int,
    ) -> Optional[dict]:
        """Position absolute without speed limit (0xA3).

        Args:
            angle_centideg: Target angle in 0.01 degree units.
        """
        # Spec: angleControl is int64_t, 8 data bytes, 0.01 deg/LSB
        angle_bytes = list(struct.pack("<q", angle_centideg))
        data = angle_bytes[:8]
        resp = self._send_receive(CMD_POSITION_ABSOLUTE_1, data)
        return self._parse_status2_from_response(resp)

    def send_single_loop_command(
        self,
        angle_centideg: int,
        max_speed_dps: int = 0,
        direction: int = 0,
    ) -> Optional[dict]:
        """Single-loop angle control with speed limit (0xA6).

        RS485 frame: 8 data bytes — dir(u8) + angle(uint16, 2B) + 0x00
                                     + maxSpeed(uint32, 4B).
        maxSpeed is in 0.01 dps units on the wire.

        Args:
            angle_centideg: Target angle in 0.01 degree units (0-35999).
            max_speed_dps: Maximum speed in dps. If 0, defaults to 360 dps.
            direction: 0 = CW, 1 = CCW.
        """
        if max_speed_dps == 0:
            max_speed_dps = 360  # safe default: 1 revolution per second
        dir_byte = 0x01 if direction else 0x00
        speed_centidps = max_speed_dps * 100  # convert dps -> 0.01 dps
        angle_bytes = list(struct.pack("<H", angle_centideg & 0xFFFF))
        speed_bytes = list(struct.pack("<I", speed_centidps))
        data = [dir_byte] + angle_bytes[:2] + [0x00] + speed_bytes[:4]
        resp = self._send_receive(CMD_POSITION_SINGLE_2, data)
        return self._parse_status2_from_response(resp)

    def send_single_loop_command_no_speed(
        self,
        angle_centideg: int,
        direction: int = 0,
    ) -> Optional[dict]:
        """Single-loop angle control without speed limit (0xA5).

        RS485 frame: 4 data bytes — dir(uint8) + angle(uint16 LE) + 0x00.
        angle is in 0.01 degree units (0-35999).

        Args:
            angle_centideg: Target angle in 0.01 degree units (0-35999).
            direction: 0 = CW, 1 = CCW.
        """
        dir_byte = 0x01 if direction else 0x00
        angle_bytes = list(struct.pack("<H", angle_centideg & 0xFFFF))
        data = [dir_byte] + angle_bytes[:2] + [0x00]
        resp = self._send_receive(CMD_POSITION_SINGLE_1, data)
        return self._parse_status2_from_response(resp)

    def send_increment_command(
        self,
        angle_centideg: int,
        max_speed_dps: int = 0,
    ) -> Optional[dict]:
        """Increment angle control with speed limit (0xA8).

        RS485 frame: 8 data bytes — angleInc(int32, 4B) + maxSpeed(uint32, 4B).
        maxSpeed is in 0.01 dps units on the wire.

        Args:
            angle_centideg: Increment angle in 0.01 degree units.
            max_speed_dps: Maximum speed in dps. If 0, defaults to 360 dps.
        """
        if max_speed_dps == 0:
            max_speed_dps = 360
        speed_centidps = max_speed_dps * 100  # convert dps -> 0.01 dps
        angle_bytes = list(struct.pack("<i", angle_centideg))
        speed_bytes = list(struct.pack("<I", speed_centidps))
        data = angle_bytes[:4] + speed_bytes[:4]
        resp = self._send_receive(CMD_POSITION_INCREMENT_2, data)
        return self._parse_status2_from_response(resp)

    def send_increment_command_no_speed(
        self,
        angle_centideg: int,
    ) -> Optional[dict]:
        """Increment angle control without speed limit (0xA7).

        RS485 frame: 4 data bytes — angleInc(int32, 4B).

        Args:
            angle_centideg: Increment angle in 0.01 degree units.
        """
        angle_bytes = list(struct.pack("<i", angle_centideg))
        data = angle_bytes[:4]
        resp = self._send_receive(CMD_POSITION_INCREMENT_1, data)
        return self._parse_status2_from_response(resp)

    def _parse_status2_from_response(
        self,
        resp: Optional[dict],
    ) -> Optional[dict]:
        """Parse status2-format response from control commands."""
        if not resp or len(resp.get("data", b"")) < 7:
            return None
        d = resp["data"]
        temp = struct.unpack_from("<b", d, 0)[0]
        iq_raw = struct.unpack_from("<h", d, 1)[0]
        speed_raw = struct.unpack_from("<h", d, 3)[0]
        encoder = struct.unpack_from("<H", d, 5)[0]
        return {
            "temperature_c": float(temp),
            "torque_current_a": round(iq_raw * CURRENT_SCALE, 3),
            "speed_dps": float(speed_raw),
            "encoder_position": encoder,
        }

    # -- Product Info / Brake / Restore / Zero Commands ---------------------

    def read_product_info(self) -> Optional[dict]:
        """Read product info (cmd 0x12). Returns driver/motor names, versions."""
        resp = self._send_receive(CMD_READ_PRODUCT_INFO)
        if not resp or not resp.get("data"):
            return None
        data = resp["data"]
        if len(data) < 58:
            return {"error": f"Short response: {len(data)} bytes, expected 58"}

        def _decode_str(raw_bytes):
            """Decode null-padded ASCII string."""
            return bytes(raw_bytes).split(b"\x00")[0].decode("ascii", errors="replace").strip()

        driver_name = _decode_str(data[0:20])
        motor_name = _decode_str(data[20:40])
        motor_id_bytes = bytes(data[40:52]).hex().upper()
        hw_version = struct.unpack_from("<H", bytes(data[52:54]))[0]
        motor_version = struct.unpack_from("<H", bytes(data[54:56]))[0]
        fw_version = struct.unpack_from("<H", bytes(data[56:58]))[0]

        def _fmt_ver(raw: int) -> str:
            """Format raw version int (e.g. 240 -> 'V2.4', 236 -> 'V2.36')."""
            s = f"{raw / 100:.2f}".rstrip("0")
            if s.endswith("."):
                s += "0"
            return f"V{s}"

        return {
            "driver_name": driver_name,
            "motor_name": motor_name,
            "motor_serial_id": motor_id_bytes,
            "hardware_version": _fmt_ver(hw_version),
            "motor_version": _fmt_ver(motor_version),
            "firmware_version": _fmt_ver(fw_version),
            "hardware_version_raw": hw_version,
            "motor_version_raw": motor_version,
            "firmware_version_raw": fw_version,
        }

    def brake_control(self, action: int) -> Optional[dict]:
        """Control holding brake (cmd 0x8C).

        Args:
            action: 0=brake_on (hold), 1=brake_release, 0x10=read_state.
        """
        resp = self._send_receive(CMD_BRAKE_CONTROL, [action])
        if not resp:
            return None
        # Response echoes back the brake state
        data = resp.get("data", b"")
        if data:
            return {"brake_state": data[0], "brake_on": data[0] == 0x00}
        return {"success": True}

    def motor_restore(self) -> Optional[dict]:
        """Motor restore (cmd 0x89). Restores motor to default running state."""
        return self._send_receive(CMD_MOTOR_RESTORE)

    def clear_multi_turn_angle(self) -> Optional[dict]:
        """Clear multi-turn angle counter (cmd 0x93)."""
        return self._send_receive(CMD_CLEAR_MULTI_TURN)

    def set_zero_position_ram(self) -> Optional[dict]:
        """Write current position as motor zero to RAM (cmd 0x95).

        Lost on power-off.
        """
        return self._send_receive(CMD_SET_ZERO_RAM)

    # -- ParamID-based Extended Reads/Writes --------------------------------

    def _read_ext_param(self, param_id: int) -> Optional[dict]:
        """Read an extended parameter via 0x40 + ParamID.

        Returns the raw response dict (with ``data`` key) for caller
        to decode, since extended params have variable-width values
        (int16, int32, etc.) unlike PID params which are always 3xU16.
        """
        return self._send_receive(CMD_READ_PID, [param_id, 0x00])

    def read_max_speed(self) -> Optional[dict]:
        """Read max speed via ParamID 0x9A. Returns int32."""
        resp = self._read_ext_param(PARAM_MAX_SPEED)
        if not resp or not resp.get("data") or len(resp["data"]) < 5:
            return None
        data = resp["data"]
        value = struct.unpack_from("<i", bytes(data[1:5]))[0]
        return {"max_speed": value, "max_speed_dps": value * 0.01}

    def write_max_speed(self, value: int, to_rom: bool = False) -> Optional[dict]:
        """Write max speed via ParamID 0x9A. value is int32."""
        data = [PARAM_MAX_SPEED] + list(struct.pack("<i", int(value)))
        cmd = CMD_WRITE_PID_ROM if to_rom else CMD_WRITE_PID_RAM
        return self._send_receive(cmd, data)

    def read_max_angle(self) -> Optional[dict]:
        """Read max angle (int64 split across ParamIDs 0x9B and 0x9C)."""
        resp_low = self._read_ext_param(PARAM_MAX_ANGLE_LOW)
        resp_high = self._read_ext_param(PARAM_MAX_ANGLE_HIGH)
        if not resp_low or not resp_high:
            return None
        data_low = resp_low.get("data", b"")
        data_high = resp_high.get("data", b"")
        if len(data_low) < 5 or len(data_high) < 5:
            return None
        low = struct.unpack_from("<i", bytes(data_low[1:5]))[0]
        high = struct.unpack_from("<i", bytes(data_high[1:5]))[0]
        value = (high << 32) | (low & 0xFFFFFFFF)
        return {"max_angle_raw": value, "max_angle_deg": value * 0.01}

    def write_max_angle(self, value: int, to_rom: bool = False) -> Optional[bool]:
        """Write max angle (int64 split across ParamIDs 0x9B and 0x9C)."""
        value = int(value)
        low = value & 0xFFFFFFFF
        high = (value >> 32) & 0xFFFFFFFF
        cmd = CMD_WRITE_PID_ROM if to_rom else CMD_WRITE_PID_RAM
        data_low = [PARAM_MAX_ANGLE_LOW] + list(struct.pack("<I", low))
        data_high = [PARAM_MAX_ANGLE_HIGH] + list(struct.pack("<I", high))
        resp1 = self._send_receive(cmd, data_low)
        resp2 = self._send_receive(cmd, data_high)
        return resp1 is not None and resp2 is not None

    def read_current_ramp(self) -> Optional[dict]:
        """Read current ramp via ParamID 0x9D. Returns int16."""
        resp = self._read_ext_param(PARAM_CURRENT_RAMP)
        if not resp or not resp.get("data") or len(resp["data"]) < 3:
            return None
        data = resp["data"]
        value = struct.unpack_from("<h", bytes(data[1:3]))[0]
        return {"current_ramp": value}

    def write_current_ramp(self, value: int, to_rom: bool = False) -> Optional[dict]:
        """Write current ramp via ParamID 0x9D. value is int16."""
        data = [PARAM_CURRENT_RAMP] + list(struct.pack("<h", int(value)))
        cmd = CMD_WRITE_PID_ROM if to_rom else CMD_WRITE_PID_RAM
        return self._send_receive(cmd, data)

    def read_speed_ramp(self) -> Optional[dict]:
        """Read speed ramp via ParamID 0x9E. Returns int16."""
        resp = self._read_ext_param(PARAM_SPEED_RAMP)
        if not resp or not resp.get("data") or len(resp["data"]) < 3:
            return None
        data = resp["data"]
        value = struct.unpack_from("<h", bytes(data[1:3]))[0]
        return {"speed_ramp": value}

    def write_speed_ramp(self, value: int, to_rom: bool = False) -> Optional[dict]:
        """Write speed ramp via ParamID 0x9E. value is int16."""
        data = [PARAM_SPEED_RAMP] + list(struct.pack("<h", int(value)))
        cmd = CMD_WRITE_PID_ROM if to_rom else CMD_WRITE_PID_RAM
        return self._send_receive(cmd, data)

    def read_product_info_ext(self) -> Optional[dict]:
        """Read extended product/config info via undocumented cmd 0x16.

        Returns a dict with known fields parsed and raw hex for unknown regions.
        The 108-byte response is an EEPROM config dump.
        """
        resp = self._send_receive(CMD_READ_PRODUCT_INFO_EXT, [])
        if not resp or not resp.get("data"):
            return None
        data = resp["data"]
        if len(data) < 107:
            return {"raw_hex": bytes(data).hex(" "), "error": "short response"}

        # --- Communication config (HIGH confidence) ---
        # Offsets verified against live capture (114-byte frame, 108-byte data payload):
        # data[0]=0x1C, data[1]=0x07, data[2]=0x01, data[3]=0x01
        rs485_divider = data[0]
        rs485_baudrate = 3225600 // rs485_divider if rs485_divider else 0

        # CAN baud index to rate mapping (from LK Motor Tool dropdown order)
        can_baud_map = {
            0: 1000000,
            1: 800000,
            2: 500000,
            3: 400000,
            4: 250000,
            5: 200000,
            6: 125000,
            7: 1000000,
        }
        can_baud_index = data[1]
        can_baudrate = can_baud_map.get(can_baud_index, 0)

        driver_id = data[2]
        bus_type_raw = data[3]
        bus_type = (
            "CAN"
            if bus_type_raw == 1
            else "RS485" if bus_type_raw == 0 else f"unknown({bus_type_raw})"
        )

        # --- Protection region (PARTIAL confidence) ---
        # data[85]=0x06 = Over Current threshold in integer amps (verified live)
        over_current_threshold = data[85]

        # --- Encoder / alignment region ---
        encoder_offset = struct.unpack_from("<H", bytes(data[4:6]))[0]
        align_ratio = struct.unpack_from("<H", bytes(data[8:10]))[0]
        align_voltage_raw = struct.unpack_from("<H", bytes(data[10:12]))[0]
        align_voltage = align_voltage_raw / 100.0
        encoder_position = data[12]
        # d[13]: Motor phase sequence (MEDIUM confidence)
        # Adjacent to encoder_position (d[12]). Observed 0xFF on
        # MG6010E-i6 where LK Motor Tool shows "Reverse".
        # Encoding: 0x00=Normal, non-zero=Reverse (confirmed: 0xFF).
        motor_phase_seq_raw = data[13]
        motor_phase_sequence = "Normal" if motor_phase_seq_raw == 0x00 else "Reverse"

        # --- Basic setting flags (MEDIUM confidence) ---
        # d[6], d[7]: observed 0x00 on MG6010E-i6 where LK shows
        # Broadcast=OFF, Spin Direction=Normal. Single data point.
        broadcast_mode_raw = data[6]
        spin_direction_raw = data[7]

        # Reducer fields (near end of 108-byte payload)
        reducer_align_value = struct.unpack_from("<H", bytes(data[88:90]))[0]
        reducer_zero_position = struct.unpack_from("<H", bytes(data[90:92]))[0]

        # d[92]: Encoder type index (MEDIUM confidence)
        # Observed 0x01 on MG6010E-i6 where LK shows "16Bit Encoder".
        encoder_type_raw = data[92]
        encoder_type = _ENCODER_TYPE_MAP.get(encoder_type_raw, f"Unknown({encoder_type_raw})")

        # EEPROM trailer (last 4 bytes of 108-byte payload)
        # data[104:106] LE = 0x1234 = EEPROM version
        # data[106:108] LE = 0x55AA = EEPROM magic
        eeprom_version = (data[105] << 8) | data[104]  # LE: 0x1234
        eeprom_magic = (data[107] << 8) | data[106]  # LE: 0x55AA

        # Sentinel for fields not readable over RS485 (0x30/0x33/0x37/0x40
        # commands are CAN-only on this firmware). Frontend displays this as-is.
        NA = "N/A (RS485)"

        return {
            "basic_setting": {
                "driver_id": driver_id,
                "bus_type": bus_type,
                "bus_type_raw": bus_type_raw,
                "rs485_baudrate": rs485_baudrate,
                "rs485_divider": rs485_divider,
                "can_baudrate": can_baudrate,
                "can_baud_index": can_baud_index,
                "broadcast_mode": broadcast_mode_raw,
                "spin_direction": spin_direction_raw,
                "brake_resistor_control": NA,
                "brake_resistor_voltage": NA,
            },
            "protection_setting": {
                "motor_temp_threshold": NA,
                "motor_temp_enable": NA,
                "driver_temp_threshold": NA,
                "driver_temp_enable": NA,
                "under_voltage_threshold": NA,
                "under_voltage_enable": NA,
                "over_voltage_threshold": NA,
                "over_voltage_enable": NA,
                "over_current_threshold": over_current_threshold,
                "over_current_enable": NA,
                "over_current_time": NA,
                "short_circuit_enable": NA,
                "stall_threshold": NA,
                "stall_enable": NA,
                "lost_input_time": NA,
                "lost_input_enable": NA,
            },
            "encoder_setting": {
                "encoder_offset": encoder_offset,
                "align_ratio": align_ratio,
                "align_voltage": align_voltage,
                "encoder_position": encoder_position,
                "encoder_type": encoder_type,
                "encoder_type_raw": encoder_type_raw,
                "motor_phase_sequence": motor_phase_sequence,
                "motor_phase_seq_raw": motor_phase_seq_raw,
                "reducer_align_value": reducer_align_value,
                "reducer_zero_position": reducer_zero_position,
            },
            "eeprom_version": f"0x{eeprom_version:04X}",
            "eeprom_magic_valid": eeprom_magic == 0x55AA,
            "raw_hex": bytes(data).hex(" "),
        }

    # -- Firmware Version (CMD 0x1F) ----------------------------------------

    def read_firmware_version(self) -> Optional[dict]:
        """Read firmware version (cmd 0x1F). Returns 2-byte build info."""
        resp = self._send_receive(CMD_READ_FIRMWARE_VERSION)
        if not resp or not resp.get("data"):
            return None
        data = resp["data"]
        if len(data) != 2:
            return {"error": (f"Invalid response length: {len(data)} bytes," " expected 2")}
        # 2-byte firmware build info (little-endian)
        fw_build = struct.unpack_from("<H", bytes(data))[0]
        return {
            "firmware_build": fw_build,
            "firmware_build_hex": f"0x{fw_build:04X}",
            "byte_0": data[0],
            "byte_1": data[1],
        }

    # -- Full Config Read (CMD 0x14) ----------------------------------------

    @staticmethod
    def _decode_enable_byte(val: int) -> str:
        """Decode a protection-enable byte from CMD 0x14.

        Encoding:
          0x00 = Disable
          0x01 = Enable (recoverable)
          0x02 = Enable (not recoverable)
          0xFF = Disable
        """
        if val == 0x00 or val == 0xFF:
            return "Disable"
        if val == 0x01:
            return "Enable (recoverable)"
        if val == 0x02:
            return "Enable (not recoverable)"
        return f"Unknown (0x{val:02X})"

    def read_full_config(self) -> Optional[dict]:
        """Read full config (cmd 0x14). Returns 104-byte config decode.

        This single command replaces multiple individual reads (PID,
        acceleration, torque limit) with one bus transaction.
        """
        resp = self._send_receive(CMD_READ_FULL_CONFIG)
        if not resp or not resp.get("data"):
            return None
        data = resp["data"]
        if len(data) < 104:
            return {"error": (f"Short response: {len(data)} bytes," " expected 104")}

        d = bytes(data)

        # --- PID gains ---
        angle_kp = d[6]
        angle_ki = d[8]
        speed_kp = struct.unpack_from("<H", d, 56)[0]
        speed_ki = struct.unpack_from("<H", d, 58)[0]
        current_kp = struct.unpack_from("<H", d, 62)[0]
        current_ki = struct.unpack_from("<H", d, 64)[0]

        # --- Temperature protection ---
        motor_temp_limit = d[14]
        driver_temp_limit = d[15]
        motor_temp_enable = self._decode_enable_byte(d[28])
        driver_temp_enable = self._decode_enable_byte(d[29])

        # --- Voltage / current protection ---
        under_voltage = struct.unpack_from("<H", d, 16)[0] / 100.0
        over_voltage = struct.unpack_from("<H", d, 18)[0] / 100.0
        over_current = struct.unpack_from("<H", d, 20)[0] / 100.0
        over_current_time = struct.unpack_from("<H", d, 22)[0]
        brake_resistor_voltage = struct.unpack_from("<H", d, 30)[0] / 100.0
        under_voltage_enable = self._decode_enable_byte(d[32])
        over_voltage_enable = self._decode_enable_byte(d[33])
        # d[34-36] are data values, not enable bytes;
        # actual offsets for these protections are unknown
        over_current_enable = None
        stall_enable = None
        lost_input_enable = None

        # --- Mechanical limits ---
        stall_threshold = struct.unpack_from("<H", d, 24)[0]
        lost_input_time = struct.unpack_from("<H", d, 26)[0]
        max_torque_current = struct.unpack_from("<H", d, 68)[0]
        max_speed = struct.unpack_from("<I", d, 72)[0] / 100.0
        raw_max_angle = struct.unpack_from("<i", d, 76)[0]
        max_angle = 0.0 if raw_max_angle == -1 else (raw_max_angle / 100.0)
        speed_ramp = struct.unpack_from("<H", d, 92)[0]
        current_ramp = struct.unpack_from("<H", d, 4)[0]

        # --- Trailer (last 4 bytes: [100-103]) ---
        trailer_v0 = d[100]
        trailer_v1 = d[101]
        magic = struct.unpack_from("<H", d, 102)[0]
        magic_valid = magic == 0x55AA
        if not magic_valid:
            logger.warning("CMD 0x14 trailer magic mismatch: 0x%04X" " (expected 0x55AA)", magic)

        return {
            "pid_setting": {
                "angle_kp": angle_kp,
                "angle_ki": angle_ki,
                "speed_kp": speed_kp,
                "speed_ki": speed_ki,
                "current_kp": current_kp,
                "current_ki": current_ki,
            },
            "protection_setting": {
                "motor_temp_limit": motor_temp_limit,
                "driver_temp_limit": driver_temp_limit,
                "motor_temp_enable": motor_temp_enable,
                "driver_temp_enable": driver_temp_enable,
                "under_voltage": under_voltage,
                "over_voltage": over_voltage,
                "over_current": over_current,
                "over_current_time": over_current_time,
                "brake_resistor_voltage": brake_resistor_voltage,
                "under_voltage_enable": under_voltage_enable,
                "over_voltage_enable": over_voltage_enable,
                "over_current_enable": over_current_enable,
                "stall_enable": stall_enable,
                "lost_input_enable": lost_input_enable,
                "stall_threshold": stall_threshold,
                "lost_input_time": lost_input_time,
                "short_circuit_enable": "N/A",
            },
            "limits_setting": {
                "max_torque_current": max_torque_current,
                "max_speed": max_speed,
                "max_angle": max_angle,
                "speed_ramp": speed_ramp,
                "current_ramp": current_ramp,
            },
            "basic_setting": {
                "brake_resistor_voltage": brake_resistor_voltage,
                "current_ramp": current_ramp,
            },
            "trailer": {
                "version_byte_0": trailer_v0,
                "version_byte_1": trailer_v1,
                "magic": f"0x{magic:04X}",
                "magic_valid": magic_valid,
            },
            "raw_hex": d.hex(" "),
        }

    # -- System State / Heartbeat (CMD 0x10) --------------------------------

    def read_system_state(self) -> Optional[dict]:
        """Read system state / heartbeat (cmd 0x10).

        Sends CMD 0x10 and expects an echo with 0 data bytes.
        A successful response confirms the motor is alive.
        """
        resp = self._send_receive(CMD_READ_SYSTEM_STATE)
        if resp is None:
            return None
        data = resp.get("data", b"")
        if len(data) > 0:
            logger.warning(
                "CMD 0x10 heartbeat: unexpected %d data bytes" " (expected 0)", len(data)
            )
        return {"alive": True, "data_len": len(data)}
