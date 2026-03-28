#!/usr/bin/env python3
"""
Standalone Motor Dashboard Server

Talks directly to MG6010E-i6 motor via RS485 UART protocol (no ROS2 required).
Serves the existing dashboard frontend with compatible REST + WebSocket APIs.

Usage:
    python3 standalone_motor_server.py --serial-port /dev/ttyUSB0 --motor-id 3
    python3 standalone_motor_server.py --help
"""

import argparse
import asyncio
import json
import logging
import struct
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Install with: pip3 install pyserial")
    sys.exit(1)

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError:
    print(
        "ERROR: fastapi/uvicorn not installed. "
        "Install with: pip3 install fastapi uvicorn[standard]"
    )
    sys.exit(1)


logger = logging.getLogger("standalone_motor")

# ---------------------------------------------------------------------------
# RS485 Protocol Constants
# ---------------------------------------------------------------------------
RS485_HEADER = 0x3E

# Read commands
CMD_READ_PID = 0x30
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
CMD_WRITE_PID_RAM = 0x31
CMD_WRITE_PID_ROM = 0x32
CMD_READ_ACCELERATION = 0x33
CMD_WRITE_ACCELERATION_RAM = 0x34
CMD_READ_MAX_TORQUE = 0x37
CMD_WRITE_MAX_TORQUE_RAM = 0x38
CMD_SET_ENCODER_ZERO = 0x19
CMD_WRITE_ENCODER_OFFSET_ROM = 0x91

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
# Current conversion: raw -2048..2048 maps to -33A..33A
CURRENT_SCALE = 33.0 / 2048.0
# Phase current scale: raw / 64.0 = Amps
PHASE_CURRENT_SCALE = 1.0 / 64.0


# ---------------------------------------------------------------------------
# RS485 Motor Driver
# ---------------------------------------------------------------------------
class RS485MotorDriver:
    """Communicates with MG6010E-i6 motor via RS485 UART protocol."""

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baud: int = 115200,
        motor_id: int = 1,
        timeout: float = 1.0,
    ):
        self.port = port
        self.baud = baud
        self.motor_id = motor_id
        self.timeout = timeout
        self._lock = threading.Lock()
        self._serial: Optional[serial.Serial] = None

    def connect(self) -> bool:
        """Open serial port. Returns True on success."""
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
        """Close serial port."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serial port closed")

    @staticmethod
    def _checksum(data: list[int]) -> int:
        return sum(data) & 0xFF

    @staticmethod
    def _build_frame(
        cmd: int, motor_id: int, data: Optional[list[int]] = None
    ) -> bytes:
        """Build RS485 frame: [0x3E][CMD][ID][LEN][CHECKSUM][DATA...][DATA_CHECKSUM]"""
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
        """Parse RS485 response frame. Returns dict with cmd, motor_id, data."""
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

        result = {"cmd": cmd, "motor_id": motor_id, "data_len": data_len}

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
            expected_data_checksum = RS485MotorDriver._checksum(list(result["data"]))
            if expected_data_checksum != data_checksum:
                logger.warning("Data checksum mismatch")
                return None
        else:
            result["data"] = b""

        return result

    def _send_receive(
        self, cmd: int, data: Optional[list[int]] = None
    ) -> Optional[dict]:
        """Send command and wait for response. Thread-safe."""
        if not self._serial or not self._serial.is_open:
            return None

        frame = self._build_frame(cmd, self.motor_id, data)

        with self._lock:
            # Flush input buffer
            self._serial.reset_input_buffer()
            self._serial.write(frame)
            self._serial.flush()

            # Read response
            start = time.time()
            rx_buffer = b""
            while (time.time() - start) < self.timeout:
                if self._serial.in_waiting > 0:
                    rx_buffer += self._serial.read(self._serial.in_waiting)
                    # Check for complete frame
                    if len(rx_buffer) >= 5 and rx_buffer[0] == RS485_HEADER:
                        resp_data_len = rx_buffer[3]
                        expected_len = (
                            5 + resp_data_len + (1 if resp_data_len > 0 else 0)
                        )
                        if len(rx_buffer) >= expected_len:
                            return self._parse_response(rx_buffer[:expected_len])
                time.sleep(0.005)

            logger.warning("Timeout waiting for response to cmd 0x%02X", cmd)
            return None

    # --- Read Commands ---

    def read_status_1(self) -> Optional[dict]:
        """Read Status 1 (0x9A): temperature, voltage, error flags."""
        resp = self._send_receive(CMD_READ_STATUS_1)
        if not resp or len(resp.get("data", b"")) < 7:
            return None
        d = resp["data"]
        temp = struct.unpack_from("<b", d, 0)[0]
        voltage = struct.unpack_from("<H", d, 1)[0] * 0.01
        error_byte = d[6] if len(d) > 6 else 0
        return {
            "temperature_c": float(temp),
            "voltage_v": round(voltage, 1),
            "error_byte": error_byte,
        }

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
        """Read multi-turn angle (0x92). Returns degrees."""
        resp = self._send_receive(CMD_READ_MULTI_TURN_ANGLE)
        if not resp or len(resp.get("data", b"")) < 8:
            return None
        d = resp["data"]
        # 64-bit signed, but only 7 bytes from motor (pad the 8th)
        raw_bytes = bytes(d[:7]) + (b"\xff" if d[6] & 0x80 else b"\x00")
        angle_raw = struct.unpack("<q", raw_bytes)[0]
        return round(angle_raw * 0.01, 2)

    def read_single_turn_angle(self) -> Optional[float]:
        """Read single-turn angle (0x94). Returns degrees 0-359.99."""
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

    def read_pid(self) -> Optional[dict]:
        """Read PID gains (0x30)."""
        resp = self._send_receive(CMD_READ_PID)
        if not resp or len(resp.get("data", b"")) < 6:
            return None
        d = resp["data"]
        return {
            "angle_kp": d[0],
            "angle_ki": d[1],
            "speed_kp": d[2],
            "speed_ki": d[3],
            "current_kp": d[4],
            "current_ki": d[5],
        }

    def read_acceleration(self) -> Optional[float]:
        """Read acceleration (0x33). Returns dps/s."""
        resp = self._send_receive(CMD_READ_ACCELERATION)
        if not resp or len(resp.get("data", b"")) < 4:
            return None
        d = resp["data"]
        accel = struct.unpack_from("<i", d, 0)[0]
        return float(accel)

    def read_max_torque(self) -> Optional[int]:
        """Read max torque current ratio (0x37). Returns raw ratio 0-2000."""
        resp = self._send_receive(CMD_READ_MAX_TORQUE)
        if not resp or len(resp.get("data", b"")) < 7:
            return None
        d = resp["data"]
        ratio = struct.unpack_from("<H", d, 4)[0]
        return ratio

    # --- Write Commands ---

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
        """Clear motor errors (0x9B). Returns status_1 data."""
        resp = self._send_receive(CMD_CLEAR_ERRORS)
        if not resp or len(resp.get("data", b"")) < 7:
            return None
        d = resp["data"]
        error_byte = d[6] if len(d) > 6 else 0
        return {"error_byte": error_byte}

    def write_pid_ram(self, gains: dict) -> Optional[dict]:
        """Write PID gains to RAM (0x31)."""
        data = [
            gains.get("angle_kp", 0),
            gains.get("angle_ki", 0),
            gains.get("speed_kp", 0),
            gains.get("speed_ki", 0),
            gains.get("current_kp", 0),
            gains.get("current_ki", 0),
        ]
        return self._send_receive(CMD_WRITE_PID_RAM, data)

    def write_pid_rom(self, gains: dict) -> Optional[dict]:
        """Write PID gains to ROM (0x32)."""
        data = [
            gains.get("angle_kp", 0),
            gains.get("angle_ki", 0),
            gains.get("speed_kp", 0),
            gains.get("speed_ki", 0),
            gains.get("current_kp", 0),
            gains.get("current_ki", 0),
        ]
        return self._send_receive(CMD_WRITE_PID_ROM, data)

    def set_encoder_zero(self) -> Optional[dict]:
        """Set current position as encoder zero (0x19)."""
        resp = self._send_receive(CMD_SET_ENCODER_ZERO)
        if not resp:
            return None
        return {"success": True}

    def write_acceleration(self, accel_dps_s: int) -> Optional[dict]:
        """Write acceleration to RAM (0x34)."""
        data = list(struct.pack("<i", accel_dps_s))
        return self._send_receive(CMD_WRITE_ACCELERATION_RAM, data)

    def write_max_torque(self, ratio: int) -> Optional[dict]:
        """Write max torque current ratio to RAM (0x38)."""
        # Frame: [00 00 00 00 ratio_lo ratio_hi 00]
        data = [0x00, 0x00, 0x00, 0x00] + list(struct.pack("<H", ratio)) + [0x00]
        return self._send_receive(CMD_WRITE_MAX_TORQUE_RAM, data)

    def send_torque_command(self, iq_raw: int) -> Optional[dict]:
        """Torque closed-loop (0xA1). iq_raw in -2048..2048."""
        data = [0x00, 0x00, 0x00] + list(struct.pack("<h", iq_raw)) + [0x00, 0x00]
        resp = self._send_receive(CMD_TORQUE_CLOSED_LOOP, data)
        return self._parse_status2_from_response(resp)

    def send_speed_command(self, speed_centideg_s: int) -> Optional[dict]:
        """Speed closed-loop (0xA2). Speed in 0.01 dps units."""
        data = [0x00, 0x00, 0x00] + list(struct.pack("<i", speed_centideg_s))
        resp = self._send_receive(CMD_SPEED_CLOSED_LOOP, data)
        return self._parse_status2_from_response(resp)

    def send_position_command(
        self, angle_centideg: int, max_speed_dps: int = 0
    ) -> Optional[dict]:
        """Position absolute with speed limit (0xA4)."""
        speed_bytes = list(struct.pack("<H", max_speed_dps))
        angle_bytes = list(struct.pack("<i", angle_centideg))
        data = [0x00] + speed_bytes + angle_bytes[:4]
        resp = self._send_receive(CMD_POSITION_ABSOLUTE_2, data)
        return self._parse_status2_from_response(resp)

    def _parse_status2_from_response(self, resp: Optional[dict]) -> Optional[dict]:
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

    def get_full_state(self) -> Optional[dict]:
        """Read all motor state data (status1 + status2 + status3 + angles)."""
        state = {}

        s2 = self.read_status_2()
        if s2:
            state.update(s2)

        s1 = self.read_status_1()
        if s1:
            state["temperature_c"] = s1["temperature_c"]
            state["voltage_v"] = s1["voltage_v"]
            state["error_byte"] = s1["error_byte"]

        s3 = self.read_status_3()
        if s3:
            state["phase_current_a"] = s3["phase_current_a"]

        mt = self.read_multi_turn_angle()
        if mt is not None:
            state["multi_turn_deg"] = mt

        st = self.read_single_turn_angle()
        if st is not None:
            state["single_turn_deg"] = st

        if not state:
            return None

        # Defaults for missing fields
        state.setdefault("temperature_c", 0.0)
        state.setdefault("voltage_v", 0.0)
        state.setdefault("torque_current_a", 0.0)
        state.setdefault("speed_dps", 0.0)
        state.setdefault("encoder_position", 0)
        state.setdefault("multi_turn_deg", 0.0)
        state.setdefault("single_turn_deg", 0.0)
        state.setdefault("phase_current_a", [0.0, 0.0, 0.0])
        state.setdefault("error_byte", 0)

        return state


# ---------------------------------------------------------------------------
# Error flag decoding
# ---------------------------------------------------------------------------
def decode_error_flags_short(error_byte: int) -> dict:
    """Decode error byte into short-key flags (matches WS format from ROS2 node)."""
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
    """Decode error byte into long-key flags (matches REST format from motor_api.py)."""
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


def infer_motor_state(error_byte: int, speed_dps: float) -> str:
    """Infer motor state string."""
    if error_byte != 0:
        return "error"
    if abs(speed_dps) > 0.1:
        return "running"
    return "off"


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

# Global driver instance (set in lifespan)
driver: Optional[RS485MotorDriver] = None
ws_clients: list[WebSocket] = []
polling_task: Optional[asyncio.Task] = None
cli_args: Optional[argparse.Namespace] = None


async def poll_motor_state():
    """Background task: poll motor at ~10Hz and broadcast to WebSocket clients."""
    while True:
        try:
            if driver and ws_clients:
                loop = asyncio.get_event_loop()
                state = await loop.run_in_executor(None, driver.read_status_2)

                if state:
                    # Periodically get full state (every 1s = every 10th poll)
                    # For efficiency, only do status2 most of the time
                    msg = {
                        "motor_id": driver.motor_id,
                        "timestamp": time.time(),
                        "temperature_c": state.get("temperature_c", 0.0),
                        "voltage_v": 0.0,
                        "torque_current_a": state.get("torque_current_a", 0.0),
                        "speed_dps": state.get("speed_dps", 0.0),
                        "encoder_position": state.get("encoder_position", 0),
                        "multi_turn_deg": 0.0,
                        "single_turn_deg": 0.0,
                        "phase_current_a": [0.0, 0.0, 0.0],
                        "error_flags": decode_error_flags_short(0),
                        "motor_state": infer_motor_state(
                            0, state.get("speed_dps", 0.0)
                        ),
                        # Extra fields the frontend may use for charts
                        "position_deg": 0.0,
                        "velocity_dps": state.get("speed_dps", 0.0),
                    }

                    text = json.dumps(msg)
                    disconnected = []
                    for ws in ws_clients:
                        try:
                            await ws.send_text(text)
                        except Exception:
                            disconnected.append(ws)
                    for ws in disconnected:
                        ws_clients.remove(ws)

            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Polling error: %s", e)
            await asyncio.sleep(1.0)


# Full state polling (1Hz) - enriches the fast polling with voltage, angles, etc.
_full_state_cache: dict = {}
_full_state_counter = 0


async def poll_full_state():
    """Background task: poll full motor state at ~1Hz for enrichment."""
    global _full_state_cache
    while True:
        try:
            if driver:
                loop = asyncio.get_event_loop()
                s1 = await loop.run_in_executor(None, driver.read_status_1)
                if s1:
                    _full_state_cache["voltage_v"] = s1["voltage_v"]
                    _full_state_cache["error_byte"] = s1["error_byte"]

                s3 = await loop.run_in_executor(None, driver.read_status_3)
                if s3:
                    _full_state_cache["phase_current_a"] = s3["phase_current_a"]

                mt = await loop.run_in_executor(None, driver.read_multi_turn_angle)
                if mt is not None:
                    _full_state_cache["multi_turn_deg"] = mt

                st = await loop.run_in_executor(None, driver.read_single_turn_angle)
                if st is not None:
                    _full_state_cache["single_turn_deg"] = st

            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Full state polling error: %s", e)
            await asyncio.sleep(2.0)


async def poll_motor_state_enriched():
    """Background task: poll motor at ~10Hz with enriched data, broadcast to WS."""
    while True:
        try:
            if driver and ws_clients:
                loop = asyncio.get_event_loop()
                state = await loop.run_in_executor(None, driver.read_status_2)

                if state:
                    error_byte = _full_state_cache.get("error_byte", 0)
                    multi_turn = _full_state_cache.get("multi_turn_deg", 0.0)
                    speed = state.get("speed_dps", 0.0)

                    msg = {
                        "motor_id": driver.motor_id,
                        "timestamp": time.time(),
                        "temperature_c": state.get("temperature_c", 0.0),
                        "voltage_v": _full_state_cache.get("voltage_v", 0.0),
                        "torque_current_a": state.get("torque_current_a", 0.0),
                        "speed_dps": speed,
                        "encoder_position": state.get("encoder_position", 0),
                        "multi_turn_deg": multi_turn,
                        "single_turn_deg": _full_state_cache.get(
                            "single_turn_deg", 0.0
                        ),
                        "phase_current_a": _full_state_cache.get(
                            "phase_current_a", [0.0, 0.0, 0.0]
                        ),
                        "error_flags": decode_error_flags_short(error_byte),
                        "motor_state": infer_motor_state(error_byte, speed),
                        # Extra fields for frontend charts
                        "position_deg": multi_turn,
                        "velocity_dps": speed,
                    }

                    text = json.dumps(msg)
                    disconnected = []
                    for ws in ws_clients:
                        try:
                            await ws.send_text(text)
                        except Exception:
                            disconnected.append(ws)
                    for ws in disconnected:
                        ws_clients.remove(ws)

            await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Polling error: %s", e)
            await asyncio.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    global driver, polling_task

    # Connect to motor
    driver = RS485MotorDriver(
        port=cli_args.serial_port,
        baud=cli_args.baud,
        motor_id=cli_args.motor_id,
        timeout=1.0,
    )
    if not driver.connect():
        logger.error("Cannot connect to motor. Exiting.")
        sys.exit(1)

    # Startup connectivity check
    logger.info("Checking motor connectivity (motor_id=%d)...", cli_args.motor_id)
    status = driver.read_status_1()
    if status is None:
        logger.error(
            "Motor not responding on %s (id=%d). Check wiring and motor ID.",
            cli_args.serial_port,
            cli_args.motor_id,
        )
        driver.disconnect()
        sys.exit(1)

    logger.info(
        "Motor connected! Temp=%s C, Voltage=%s V",
        status["temperature_c"],
        status["voltage_v"],
    )

    # Start background polling
    full_task = asyncio.create_task(poll_full_state())
    polling_task = asyncio.create_task(poll_motor_state_enriched())

    yield

    # Shutdown
    if polling_task:
        polling_task.cancel()
    full_task.cancel()
    if driver:
        driver.disconnect()


app = FastAPI(title="Standalone Motor Dashboard", lifespan=lifespan)


# ---------------------------------------------------------------------------
# REST API Endpoints (compatible with motor_api.py)
# ---------------------------------------------------------------------------


@app.get("/api/motor/validation_ranges")
async def get_validation_ranges():
    return {
        "mg6010": {
            "torque_current": {"min": -2000, "max": 2000, "unit": "mA"},
            "speed": {"min": -3600, "max": 3600, "unit": "dps"},
            "angle": {"min": -36000, "max": 36000, "unit": "degrees"},
            "max_speed": {"min": 0, "max": 3600, "unit": "dps"},
            "max_torque_current": {"min": 0, "max": 2000, "unit": "ratio"},
            "acceleration": {"min": 1, "max": 65535, "unit": "dps/s"},
            "encoder": {"min": 0, "max": 65535, "unit": "raw"},
            "pid_gains": {"min": 0, "max": 255, "unit": "byte"},
        }
    }


@app.get("/api/motor/{motor_id}/state")
async def get_motor_state(motor_id: int):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    loop = asyncio.get_event_loop()
    state = await loop.run_in_executor(None, driver.get_full_state)
    if state is None:
        return JSONResponse(
            status_code=504,
            content={"success": False, "error_message": "Motor communication timeout"},
        )

    error_byte = state.get("error_byte", 0)
    return {
        "success": True,
        "temperature_c": state["temperature_c"],
        "voltage_v": state["voltage_v"],
        "torque_current_a": state["torque_current_a"],
        "speed_dps": state["speed_dps"],
        "encoder_position": state["encoder_position"],
        "multi_turn_deg": state["multi_turn_deg"],
        "single_turn_deg": state["single_turn_deg"],
        "phase_current_a": state["phase_current_a"],
        "error_flags": decode_error_flags_long(error_byte),
        "error_message": "",
    }


@app.get("/api/motor/{motor_id}/angles")
async def get_motor_angles(motor_id: int):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    loop = asyncio.get_event_loop()
    mt = await loop.run_in_executor(None, driver.read_multi_turn_angle)
    st = await loop.run_in_executor(None, driver.read_single_turn_angle)

    if mt is None and st is None:
        return JSONResponse(
            status_code=504,
            content={"success": False, "error_message": "Motor communication timeout"},
        )

    return {
        "success": True,
        "multi_turn_deg": mt if mt is not None else 0.0,
        "single_turn_deg": st if st is not None else 0.0,
        "error_message": "",
    }


@app.get("/api/motor/{motor_id}/encoder")
async def get_motor_encoder(motor_id: int):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    loop = asyncio.get_event_loop()
    enc = await loop.run_in_executor(None, driver.read_encoder)

    if enc is None:
        return JSONResponse(
            status_code=504,
            content={"success": False, "error_message": "Motor communication timeout"},
        )

    return {
        "success": True,
        "raw_value": enc["raw_value"],
        "offset": enc["offset"],
        "original_value": enc["original_value"],
        "error_message": "",
    }


@app.get("/api/motor/{motor_id}/limits")
async def get_motor_limits(motor_id: int):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    loop = asyncio.get_event_loop()
    torque = await loop.run_in_executor(None, driver.read_max_torque)
    accel = await loop.run_in_executor(None, driver.read_acceleration)

    return {
        "success": True,
        "max_torque_ratio": torque if torque is not None else 0,
        "acceleration_dps": accel if accel is not None else 0.0,
        "acceleration": accel if accel is not None else 0.0,
        "error_message": "",
    }


@app.post("/api/motor/{motor_id}/lifecycle")
async def motor_lifecycle(motor_id: int, body: dict):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    action = body.get("action", 0)
    loop = asyncio.get_event_loop()

    # 0=OFF, 1=ON, 2=STOP, 3=REBOOT
    action_map = {
        0: driver.motor_off,
        1: driver.motor_on,
        2: driver.motor_stop,
    }

    func = action_map.get(action)
    if func is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error_message": f"Unsupported action: {action}",
            },
        )

    resp = await loop.run_in_executor(None, func)
    if resp is None:
        return JSONResponse(
            status_code=504,
            content={"success": False, "error_message": "Motor communication timeout"},
        )

    state_names = {0: "OFF", 1: "RUNNING", 2: "STOPPED"}
    return {
        "success": True,
        "motor_state": action,
        "motor_state_name": state_names.get(action, "UNKNOWN"),
    }


@app.post("/api/motor/{motor_id}/command")
async def motor_command(motor_id: int, body: dict):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    mode = body.get("mode", body.get("command_type", 0))
    value = body.get("value", 0.0)
    max_speed = body.get("max_speed", 360.0)

    loop = asyncio.get_event_loop()
    result = None

    # Mode: 0=torque, 1=speed, 2=position_abs
    if mode == 0:
        iq_raw = int(value)
        result = await loop.run_in_executor(None, driver.send_torque_command, iq_raw)
    elif mode == 1:
        speed_centideg = int(value * 100)
        result = await loop.run_in_executor(
            None, driver.send_speed_command, speed_centideg
        )
    elif mode == 2:
        angle_centideg = int(value * 100)
        max_speed_dps = int(max_speed)
        result = await loop.run_in_executor(
            None, driver.send_position_command, angle_centideg, max_speed_dps
        )
    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error_message": f"Unsupported mode: {mode}"},
        )

    if result is None:
        return JSONResponse(
            status_code=504,
            content={"success": False, "error_message": "Motor communication timeout"},
        )

    return {
        "success": True,
        "temperature": int(result.get("temperature_c", 0)),
        "torque_current": int(result.get("torque_current_a", 0) / CURRENT_SCALE),
        "speed": int(result.get("speed_dps", 0)),
        "encoder": result.get("encoder_position", 0),
        "temperature_c": result.get("temperature_c", 0.0),
        "torque_current_a": result.get("torque_current_a", 0.0),
        "speed_dps": result.get("speed_dps", 0.0),
        "error_message": "",
    }


@app.post("/api/motor/{motor_id}/errors/clear")
async def clear_motor_errors(motor_id: int):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, driver.clear_errors)

    if result is None:
        return JSONResponse(
            status_code=504,
            content={"success": False, "error_message": "Motor communication timeout"},
        )

    return {
        "success": True,
        "error_flags_after": decode_error_flags_long(result.get("error_byte", 0)),
    }


@app.put("/api/motor/{motor_id}/limits/max_torque_current")
async def set_max_torque(motor_id: int, body: dict):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    value = int(body.get("value", 0))
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, driver.write_max_torque, value)
    return {"success": True, "max_torque_ratio": value}


@app.put("/api/motor/{motor_id}/limits/acceleration")
async def set_acceleration(motor_id: int, body: dict):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    value = int(body.get("value", 0))
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, driver.write_acceleration, value)
    return {"success": True, "acceleration_dps": float(value)}


@app.post("/api/motor/{motor_id}/encoder/zero")
async def set_encoder_zero(motor_id: int, body: dict):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, driver.set_encoder_zero)
    return {"success": True, "mode": body.get("mode", 0)}


# --- PID Endpoints (for PID tuning tab) ---


@app.get("/api/pid/read/{motor_id}")
async def read_pid(motor_id: int):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    loop = asyncio.get_event_loop()
    gains = await loop.run_in_executor(None, driver.read_pid)

    if gains is None:
        return JSONResponse(
            status_code=504,
            content={"success": False, "error_message": "Motor communication timeout"},
        )

    return {
        "success": True,
        "gains": {
            "angle_kp": gains["angle_kp"],
            "angle_ki": gains["angle_ki"],
            "speed_kp": gains["speed_kp"],
            "speed_ki": gains["speed_ki"],
            "current_kp": gains["current_kp"],
            "current_ki": gains["current_ki"],
        },
    }


@app.post("/api/pid/write/{motor_id}")
async def write_pid(motor_id: int, body: dict):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    gains = body.get("gains", body)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, driver.write_pid_ram, gains)

    if result is None:
        return JSONResponse(
            status_code=504,
            content={"success": False, "error_message": "Motor communication timeout"},
        )

    return {"success": True, "message": "PID gains written to RAM"}


@app.post("/api/pid/save/{motor_id}")
async def save_pid(motor_id: int, body: dict):
    if not driver:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error_message": "Not connected"},
        )

    gains = body.get("gains", body)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, driver.write_pid_rom, gains)

    if result is None:
        return JSONResponse(
            status_code=504,
            content={"success": False, "error_message": "Motor communication timeout"},
        )

    return {"success": True, "message": "PID gains written to ROM"}


@app.get("/api/pid/motors")
async def list_motors():
    motor_id = cli_args.motor_id if cli_args else 1
    return {
        "motors": [
            {
                "motor_id": motor_id,
                "name": f"MG6010E-i6 (ID {motor_id})",
                "type": "mg6010",
            }
        ]
    }


@app.get("/api/pid/limits/{motor_type}")
async def get_pid_limits(motor_type: str):
    return {
        "angle_kp": {"min": 0, "max": 255},
        "angle_ki": {"min": 0, "max": 255},
        "speed_kp": {"min": 0, "max": 255},
        "speed_ki": {"min": 0, "max": 255},
        "current_kp": {"min": 0, "max": 255},
        "current_ki": {"min": 0, "max": 255},
    }


# --- WebSocket ---


@app.websocket("/api/motor/ws/state")
async def ws_motor_state(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    logger.info("WebSocket client connected (%d total)", len(ws_clients))
    try:
        while True:
            # Keep connection alive; client may send filter messages
            data = await websocket.receive_text()
            # We ignore filter messages - we broadcast all motor data
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in ws_clients:
            ws_clients.remove(websocket)
        logger.info("WebSocket client disconnected (%d remaining)", len(ws_clients))


@app.websocket("/api/pid/ws/motor_state")
async def ws_pid_motor_state(websocket: WebSocket):
    """PID tuning tab also uses WebSocket for live data."""
    await websocket.accept()
    ws_clients.append(websocket)
    logger.info("PID WebSocket client connected (%d total)", len(ws_clients))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in ws_clients:
            ws_clients.remove(websocket)


# ---------------------------------------------------------------------------
# Static File Serving
# ---------------------------------------------------------------------------


def setup_static_files(app: FastAPI, frontend_dir: Path):
    """Mount frontend static files."""
    if frontend_dir.exists():
        app.mount(
            "/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend"
        )
        logger.info("Serving frontend from %s", frontend_dir)
    else:
        logger.warning("Frontend directory not found: %s", frontend_dir)

        @app.get("/")
        async def fallback_index():
            return {
                "message": "Standalone Motor Dashboard API",
                "docs": "/docs",
                "motor_id": cli_args.motor_id if cli_args else 1,
            }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    global cli_args

    parser = argparse.ArgumentParser(
        description="Standalone Motor Dashboard - RS485 serial to web",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 standalone_motor_server.py --serial-port /dev/ttyUSB0 --motor-id 3
  python3 standalone_motor_server.py --port 8090 --motor-id 1 --baud 115200
        """,
    )

    parser.add_argument(
        "--port", type=int, default=8090, help="HTTP server port (default: 8090)"
    )
    parser.add_argument(
        "--serial-port",
        default="/dev/ttyUSB0",
        help="Serial port path (default: /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--motor-id", type=int, default=1, help="Motor ID 1-32 (default: 1)"
    )
    parser.add_argument(
        "--baud", type=int, default=115200, help="Serial baud rate (default: 115200)"
    )
    parser.add_argument(
        "--frontend-dir",
        default=None,
        help="Frontend directory (default: auto-detect web_dashboard/frontend/)",
    )

    cli_args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Find frontend directory
    if cli_args.frontend_dir:
        frontend_dir = Path(cli_args.frontend_dir)
    else:
        # Auto-detect relative to this script or repo root
        script_dir = Path(__file__).parent
        candidates = [
            script_dir / "frontend",
            script_dir.parent / "web_dashboard" / "frontend",
            script_dir / "web_dashboard" / "frontend",
            Path.cwd() / "web_dashboard" / "frontend",
        ]
        frontend_dir = None
        for c in candidates:
            if c.exists():
                frontend_dir = c
                break
        if frontend_dir is None:
            logger.warning(
                "Could not find frontend directory. API-only mode. "
                "Use --frontend-dir to specify."
            )

    if frontend_dir:
        setup_static_files(app, frontend_dir)

    print("=" * 60)
    print("Standalone Motor Dashboard")
    print("=" * 60)
    print(f"  Serial Port:  {cli_args.serial_port}")
    print(f"  Motor ID:     {cli_args.motor_id}")
    print(f"  Baud Rate:    {cli_args.baud}")
    print(f"  HTTP Port:    {cli_args.port}")
    print(f"  Frontend:     {frontend_dir or 'API-only'}")
    print(f"  Dashboard:    http://localhost:{cli_args.port}/")
    print(f"  API Docs:     http://localhost:{cli_args.port}/docs")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=cli_args.port, log_level="info")


if __name__ == "__main__":
    main()
