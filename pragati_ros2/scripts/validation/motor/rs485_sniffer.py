#!/usr/bin/env python3
"""
RS485 Serial Protocol Sniffer/Logger for MG6010E-i6 Motors

Sniffs wire-level RS485 traffic between the LK Motor Tool (Windows app)
and MG6010E-i6 motors. Captures raw bytes with microsecond timestamps,
decodes known LK Motor protocol frames (0x3E envelope), and identifies
command types including PID read/write, status queries, and motion commands.

Typical setup: CH340 UART-USB adapter tapped onto the RS485 bus in
listen-only mode, or a dual-port setup where one adapter carries traffic
and another monitors.

Protocol frame format:
    [0x3E] [cmd] [motor_id] [data_len] [header_checksum] [data...] [data_checksum]
    - header_checksum = (0x3E + cmd + id + len) & 0xFF
    - data_checksum   = sum(data_bytes) & 0xFF
    - data_checksum is only present when data_len > 0

Usage:
    # Basic sniffing on /dev/ttyUSB0
    python3 rs485_sniffer.py

    # Specific port, filter motor ID 3, log to file
    python3 rs485_sniffer.py -p /dev/ttyUSB1 -m 3 -o capture.log

    # Raw hex dump only, no protocol decoding
    python3 rs485_sniffer.py --no-decode

    # Dual-port mode (two USB adapters on same bus)
    python3 rs485_sniffer.py -p /dev/ttyUSB0 --dual-port /dev/ttyUSB1
"""

import argparse
import datetime
import signal
import sys
import time
from typing import Optional

try:
    import serial
except ImportError:
    print(
        "ERROR: pyserial not installed. Install with: pip3 install pyserial",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# LK Motor RS485 command table
# ---------------------------------------------------------------------------

COMMAND_TABLE: dict[int, str] = {
    0x30: "PID Read",
    0x31: "PID Write RAM",
    0x32: "PID Write ROM",
    0x80: "Motor OFF",
    0x81: "Motor STOP",
    0x88: "Motor ON",
    0x90: "Encoder Read",
    0x92: "Multi-turn Angle",
    0x94: "Single-turn Angle",
    0x9A: "Status 1",
    0x9B: "Clear Errors",
    0x9C: "Status 2",
    0x9D: "Status 3",
    0xA1: "Torque Cmd",
    0xA2: "Speed Cmd",
}

# PID data field names in byte order (6 bytes)
PID_FIELDS = [
    "angle_kp",
    "angle_ki",
    "speed_kp",
    "speed_ki",
    "current_kp",
    "current_ki",
]


# ---------------------------------------------------------------------------
# Frame parsing
# ---------------------------------------------------------------------------


def _header_checksum(header_bytes: "bytes | bytearray") -> int:
    """Header checksum: (0x3E + cmd + id + len) & 0xFF."""
    return sum(header_bytes) & 0xFF


def _data_checksum(data_bytes: bytes) -> int:
    """Data checksum: sum(data_bytes) & 0xFF."""
    return sum(data_bytes) & 0xFF


def _hex(data: bytes) -> str:
    """Format bytes as space-separated hex string."""
    return " ".join(f"{b:02x}" for b in data)


def _decode_pid_data(data: bytes) -> str:
    """Decode 6-byte PID parameter payload into named fields."""
    if len(data) < 6:
        return f"(incomplete PID data, got {len(data)} bytes)"
    parts = []
    for i, name in enumerate(PID_FIELDS):
        parts.append(f"{name}={data[i]}")
    return "  ".join(parts)


def _decode_data_payload(cmd: int, data: bytes) -> Optional[str]:
    """Attempt to decode the data payload for known command types.

    Returns a human-readable string, or None if no specific decoder exists.
    """
    if cmd in (0x30, 0x31, 0x32) and len(data) >= 6:
        return _decode_pid_data(data)
    return None


class Frame:
    """A parsed LK Motor RS485 protocol frame."""

    def __init__(
        self,
        raw: bytes,
        cmd: int,
        motor_id: int,
        data_len: int,
        header_ok: bool,
        data: bytes,
        data_ok: bool,
    ):
        self.raw = raw
        self.cmd = cmd
        self.motor_id = motor_id
        self.data_len = data_len
        self.header_ok = header_ok
        self.data = data
        self.data_ok = data_ok

    @property
    def cmd_name(self) -> str:
        base = COMMAND_TABLE.get(self.cmd, "Unknown")
        if self.data_len > 0 and self.cmd in COMMAND_TABLE:
            return f"{base} Response"
        return base

    def format_line(self, direction: str, timestamp: datetime.datetime) -> str:
        """Format the frame as a single log line."""
        ts = (
            timestamp.strftime("%Y-%m-%d %H:%M:%S.")
            + f"{timestamp.microsecond // 1000:03d}"
        )
        raw_hex = _hex(self.raw)

        parts = [
            f"[{ts}]",
            f"{direction}",
            f"CMD=0x{self.cmd:02X} ({self.cmd_name})",
            f"ID={self.motor_id}",
            f"LEN={self.data_len}",
        ]

        # Checksum warnings
        warnings = []
        if not self.header_ok:
            warnings.append("HDR_CSUM_ERR")
        if self.data_len > 0 and not self.data_ok:
            warnings.append("DATA_CSUM_ERR")
        if warnings:
            parts.append("[" + ",".join(warnings) + "]")

        # Decoded data payload
        if self.data_len > 0 and self.data:
            decoded = _decode_data_payload(self.cmd, self.data)
            if decoded:
                parts.append(f"DATA: {decoded}")

        parts.append(f"RAW: {raw_hex}")
        return "  ".join(parts)


def try_parse_frame(
    buf: "bytes | bytearray", offset: int
) -> Optional[tuple[Frame, int]]:
    """Try to parse a frame starting at buf[offset].

    Returns (Frame, bytes_consumed) on success, or None if not enough data
    or the header checksum fails (indicating this 0x3E is not a real frame
    start).
    """
    remaining = len(buf) - offset
    if remaining < 5:
        return None  # need at least header (5 bytes)

    head = buf[offset]
    if head != 0x3E:
        return None

    cmd = buf[offset + 1]
    motor_id = buf[offset + 2]
    data_len = buf[offset + 3]
    hdr_csum = buf[offset + 4]

    expected_hdr_csum = _header_checksum(buf[offset : offset + 4])
    header_ok = hdr_csum == expected_hdr_csum

    if not header_ok:
        # Not a valid frame start -- caller should skip this byte
        return None

    if data_len == 0:
        total = 5
        frame = Frame(
            raw=bytes(buf[offset : offset + total]),
            cmd=cmd,
            motor_id=motor_id,
            data_len=0,
            header_ok=header_ok,
            data=b"",
            data_ok=True,
        )
        return frame, total

    # Need header (5) + data (data_len) + data checksum (1)
    total = 5 + data_len + 1
    if remaining < total:
        return None  # incomplete -- wait for more bytes

    data = bytes(buf[offset + 5 : offset + 5 + data_len])
    d_csum = buf[offset + 5 + data_len]
    data_ok = d_csum == _data_checksum(data)

    frame = Frame(
        raw=bytes(buf[offset : offset + total]),
        cmd=cmd,
        motor_id=motor_id,
        data_len=data_len,
        header_ok=header_ok,
        data=data,
        data_ok=data_ok,
    )
    return frame, total


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


class Logger:
    """Writes log lines to stdout and optionally to a file."""

    def __init__(self, path: Optional[str] = None):
        self._file = None
        if path:
            self._file = open(path, "a", encoding="utf-8")

    def log(self, line: str) -> None:
        print(line, flush=True)
        if self._file:
            self._file.write(line + "\n")
            self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None


# ---------------------------------------------------------------------------
# Port reader (single or dual)
# ---------------------------------------------------------------------------


def _open_port(port: str, baud: int) -> serial.Serial:
    """Open a serial port with 8N1 settings."""
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
        )
        return ser
    except serial.SerialException as exc:
        print(f"ERROR: Cannot open {port}: {exc}", file=sys.stderr)
        print("Troubleshooting:", file=sys.stderr)
        print("  1. Check device exists: ls -l /dev/ttyUSB*", file=sys.stderr)
        print(
            "  2. Check permissions: sudo usermod -aG dialout $USER",
            file=sys.stderr,
        )
        print("  3. Reconnect USB cable and try again", file=sys.stderr)
        sys.exit(2)


def _raw_hex_line(data: bytes, direction: str, timestamp: datetime.datetime) -> str:
    """Format raw bytes as a timestamped hex dump line."""
    ts = (
        timestamp.strftime("%Y-%m-%d %H:%M:%S.")
        + f"{timestamp.microsecond // 1000:03d}"
    )
    return f"[{ts}] {direction}  RAW: {_hex(data)}"


# ---------------------------------------------------------------------------
# Main sniffing loop
# ---------------------------------------------------------------------------


def sniff_single_port(
    port: str,
    baud: int,
    motor_id_filter: Optional[int],
    logger: Logger,
    raw_mode: bool,
    no_decode: bool,
    show_raw: bool,
) -> None:
    """Sniff a single serial port (half-duplex RS485)."""
    ser = _open_port(port, baud)
    logger.log(f"# Listening on {port} @ {baud} baud (8N1)")
    logger.log(f"# Mode: {'raw hex' if no_decode else 'protocol decode'}")
    if motor_id_filter is not None:
        logger.log(f"# Motor ID filter: {motor_id_filter}")
    logger.log(f"# Started at {datetime.datetime.now().isoformat()}")
    logger.log("# Press Ctrl+C to stop")
    logger.log("")

    buf = bytearray()
    direction = "---"

    try:
        while True:
            chunk = ser.read(256)
            if not chunk:
                continue

            now = datetime.datetime.now()

            if no_decode:
                logger.log(_raw_hex_line(chunk, direction, now))
                continue

            buf.extend(chunk)

            # Process buffer -- scan for frames
            while len(buf) > 0:
                # Find next 0x3E marker
                idx = buf.find(0x3E)
                if idx < 0:
                    # No marker found -- dump noise if --raw
                    if show_raw and len(buf) > 0:
                        logger.log(_raw_hex_line(bytes(buf), direction, now))
                    buf.clear()
                    break

                # Dump bytes before the marker as noise
                if idx > 0:
                    if show_raw:
                        noise = bytes(buf[:idx])
                        logger.log(
                            _raw_hex_line(noise, direction, now) + "  (noise/partial)"
                        )
                    del buf[:idx]

                # Try to parse frame at start of buffer
                result = try_parse_frame(buf, 0)
                if result is None:
                    # Could be incomplete -- if buffer is very large
                    # (> max plausible frame), discard the 0x3E byte
                    if len(buf) > 260:
                        if show_raw:
                            logger.log(
                                _raw_hex_line(bytes(buf[:1]), direction, now)
                                + "  (stale 0x3E discarded)"
                            )
                        del buf[:1]
                        continue
                    # Otherwise wait for more data
                    break

                frame, consumed = result
                del buf[:consumed]

                # Apply motor ID filter
                if motor_id_filter is not None and frame.motor_id != motor_id_filter:
                    continue

                logger.log(frame.format_line(direction, now))

    except KeyboardInterrupt:
        pass
    finally:
        ser.close()


def sniff_dual_port(
    port_a: str,
    port_b: str,
    baud: int,
    motor_id_filter: Optional[int],
    logger: Logger,
    raw_mode: bool,
    no_decode: bool,
    show_raw: bool,
) -> None:
    """Sniff two serial ports, labeling traffic as TX (port A) / RX (port B)."""
    ser_a = _open_port(port_a, baud)
    ser_b = _open_port(port_b, baud)
    logger.log(f"# Dual-port mode: TX={port_a}  RX={port_b}  @ {baud} baud (8N1)")
    logger.log(f"# Mode: {'raw hex' if no_decode else 'protocol decode'}")
    if motor_id_filter is not None:
        logger.log(f"# Motor ID filter: {motor_id_filter}")
    logger.log(f"# Started at {datetime.datetime.now().isoformat()}")
    logger.log("# Press Ctrl+C to stop")
    logger.log("")

    buf_a = bytearray()
    buf_b = bytearray()

    def _process_buffer(buf: bytearray, direction: str, now: datetime.datetime) -> None:
        """Shared frame-extraction logic for a single direction buffer."""
        while len(buf) > 0:
            idx = buf.find(0x3E)
            if idx < 0:
                if show_raw and len(buf) > 0:
                    logger.log(_raw_hex_line(bytes(buf), direction, now))
                buf.clear()
                break

            if idx > 0:
                if show_raw:
                    noise = bytes(buf[:idx])
                    logger.log(
                        _raw_hex_line(noise, direction, now) + "  (noise/partial)"
                    )
                del buf[:idx]

            result = try_parse_frame(buf, 0)
            if result is None:
                if len(buf) > 260:
                    if show_raw:
                        logger.log(
                            _raw_hex_line(bytes(buf[:1]), direction, now)
                            + "  (stale 0x3E discarded)"
                        )
                    del buf[:1]
                    continue
                break

            frame, consumed = result
            del buf[:consumed]

            if motor_id_filter is not None and frame.motor_id != motor_id_filter:
                continue

            if no_decode:
                logger.log(_raw_hex_line(frame.raw, direction, now))
            else:
                logger.log(frame.format_line(direction, now))

    try:
        while True:
            chunk_a = ser_a.read(256)
            chunk_b = ser_b.read(256)
            now = datetime.datetime.now()

            if chunk_a:
                if no_decode:
                    logger.log(_raw_hex_line(chunk_a, " TX", now))
                else:
                    buf_a.extend(chunk_a)
                    _process_buffer(buf_a, " TX", now)

            if chunk_b:
                if no_decode:
                    logger.log(_raw_hex_line(chunk_b, " RX", now))
                else:
                    buf_b.extend(chunk_b)
                    _process_buffer(buf_b, " RX", now)

            if not chunk_a and not chunk_b:
                time.sleep(0.001)

    except KeyboardInterrupt:
        pass
    finally:
        ser_a.close()
        ser_b.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rs485_sniffer",
        description=(
            "RS485 serial protocol sniffer for MG6010E-i6 (LK Motor) traffic.\n"
            "Captures raw bytes with timestamps and decodes the 0x3E envelope\n"
            "protocol used by LK Motor Tool and MG60-series motors."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # Basic sniffing on default port
  python3 rs485_sniffer.py

  # Sniff a specific port, filter motor ID 3, log to file
  python3 rs485_sniffer.py -p /dev/ttyUSB1 -m 3 -o capture.log

  # Raw hex dump only (no protocol decoding)
  python3 rs485_sniffer.py --no-decode

  # Show unrecognized bytes alongside decoded frames
  python3 rs485_sniffer.py --raw

  # Dual-port mode (TX on USB0, RX on USB1)
  python3 rs485_sniffer.py -p /dev/ttyUSB0 --dual-port /dev/ttyUSB1

known commands decoded:
  0x30  PID Read           0x31  PID Write RAM      0x32  PID Write ROM
  0x80  Motor OFF          0x81  Motor STOP         0x88  Motor ON
  0x90  Encoder Read       0x92  Multi-turn Angle   0x94  Single-turn Angle
  0x9A  Status 1           0x9B  Clear Errors       0x9C  Status 2
  0x9D  Status 3           0xA1  Torque Cmd         0xA2  Speed Cmd
""",
    )

    parser.add_argument(
        "-p",
        "--port",
        default="/dev/ttyUSB0",
        help="serial port to listen on (default: /dev/ttyUSB0)",
    )
    parser.add_argument(
        "-b",
        "--baud",
        type=int,
        default=115200,
        help="baud rate (default: 115200)",
    )
    parser.add_argument(
        "-m",
        "--motor-id",
        type=int,
        default=None,
        metavar="ID",
        help="filter to a specific motor ID (1-32); default: show all",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="log output to FILE in addition to stdout",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        default=False,
        help="show raw hex dump for unrecognized / noise bytes",
    )
    parser.add_argument(
        "--no-decode",
        action="store_true",
        default=False,
        help="disable protocol decoding; just show raw hex with timestamps",
    )
    parser.add_argument(
        "--dual-port",
        type=str,
        default=None,
        metavar="PORT",
        help=("enable dual-port mode: --port is TX side, " "--dual-port is RX side"),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Validate motor-id range
    if args.motor_id is not None and not (1 <= args.motor_id <= 32):
        print(
            "ERROR: --motor-id must be between 1 and 32",
            file=sys.stderr,
        )
        sys.exit(1)

    logger = Logger(args.output)

    # Ensure clean exit message on Ctrl+C
    def _sigint_handler(sig, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        if args.dual_port:
            sniff_dual_port(
                port_a=args.port,
                port_b=args.dual_port,
                baud=args.baud,
                motor_id_filter=args.motor_id,
                logger=logger,
                raw_mode=args.raw,
                no_decode=args.no_decode,
                show_raw=args.raw,
            )
        else:
            sniff_single_port(
                port=args.port,
                baud=args.baud,
                motor_id_filter=args.motor_id,
                logger=logger,
                raw_mode=args.raw,
                no_decode=args.no_decode,
                show_raw=args.raw,
            )
    except KeyboardInterrupt:
        pass
    finally:
        logger.log("")
        logger.log(f"# Stopped at {datetime.datetime.now().isoformat()}")
        logger.close()
        print("\nSniffer stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
