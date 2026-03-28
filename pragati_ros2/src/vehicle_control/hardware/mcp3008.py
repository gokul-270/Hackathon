"""vehicle_control.hardware.mcp3008
MCP3008 (10-bit ADC) SPI reader utilities.

Board context:
- The vehicle board exposes an analog joystick wired to an MCP3008.
- MCP3008 is on the Raspberry Pi SPI bus, typically SPI0 CE1 (GPIO7 / ADC_CS).

Implementation notes:
- Supports two SPI backends:
  - `spidev` (recommended when the system also uses an SPI-based CAN controller like mcp251x)
  - `pigpio` (requires pigpiod; convenient when you don't want to rely on /dev/spidev permissions)

Why `spidev` matters:
- If your CAN interface is provided by an SPI controller (e.g., MCP2515 via the kernel `mcp251x`
  driver), using pigpio to access the *same* SPI master can disrupt the kernel driver's
  transfers and cause CAN issues.

Provides a small adapter class that matches the VehicleControl JoystickProcessor expectation:
- a `read_raw() -> (x, y)` method returning 0..1023.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple


try:
    import pigpio

    _PIGPIO_AVAILABLE = True
except Exception:  # pragma: no cover
    pigpio = None
    _PIGPIO_AVAILABLE = False

try:
    import spidev  # type: ignore

    _SPIDEV_AVAILABLE = True
except Exception:  # pragma: no cover
    spidev = None
    _SPIDEV_AVAILABLE = False


_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class MCP3008Config:
    # SPI backend selection:
    # - spidev: uses /dev/spidev<bus>.<device>
    # - pigpio: uses pigpiod daemon SPI
    spi_backend: str = "pigpio"  # spidev|pigpio

    # For spidev backend
    spi_bus: int = 0

    # For both backends:
    # - pigpio: 0=CE0 (GPIO8), 1=CE1 (GPIO7)
    # - spidev: device number (e.g., /dev/spidev0.1 -> spi_bus=0, spi_channel=1)
    spi_channel: int = 1

    spi_baud_hz: int = 1_000_000  # 1 MHz

    # pigpio SPI flags (mode, etc). spidev backend currently uses mode 0.
    spi_flags: int = 0


class _MCP3008Pigpio:
    """MCP3008 reader via pigpio SPI."""

    def __init__(self, config: MCP3008Config, *, pi: Optional["pigpio.pi"] = None):
        if not _PIGPIO_AVAILABLE:
            raise RuntimeError("pigpio is not available (python3-pigpio not installed)")

        self._own_pi = pi is None
        self._pi = pi or pigpio.pi()
        if not self._pi.connected:
            raise RuntimeError("Failed to connect to pigpiod (is pigpiod running?)")

        self._handle = self._pi.spi_open(config.spi_channel, config.spi_baud_hz, config.spi_flags)
        self._config = config

    def close(self) -> None:
        try:
            if self._handle is not None and self._pi is not None:
                self._pi.spi_close(self._handle)
        finally:
            self._handle = None
            if self._own_pi and self._pi is not None:
                try:
                    self._pi.stop()
                finally:
                    self._pi = None

    def read(self, channel: int) -> int:
        """Read raw ADC value (0..1023) from MCP3008 channel 0..7."""
        if channel < 0 or channel > 7:
            raise ValueError(f"MCP3008 channel must be 0..7 (got {channel})")

        tx = bytes([1, (8 + channel) << 4, 0])
        count, rx = self._pi.spi_xfer(self._handle, tx)
        if count != 3 or rx is None or len(rx) < 3:
            raise RuntimeError(f"SPI transfer failed (count={count}, rx_len={0 if rx is None else len(rx)})")

        value = ((rx[1] & 0x03) << 8) | rx[2]
        return int(value)


class _MCP3008Spidev:
    """MCP3008 reader via Linux spidev (/dev/spidevX.Y)."""

    def __init__(self, config: MCP3008Config):
        if not _SPIDEV_AVAILABLE:
            raise RuntimeError("spidev is not available (python3-spidev not installed)")

        self._spi = spidev.SpiDev()
        self._spi.open(int(config.spi_bus), int(config.spi_channel))
        self._spi.max_speed_hz = int(config.spi_baud_hz)
        self._spi.mode = 0
        self._spi.bits_per_word = 8

        if int(config.spi_flags) != 0:
            # spidev mode is currently fixed at 0; warn once if someone set pigpio flags.
            _LOG.debug("MCP3008 spidev backend: ignoring spi_flags=%s (mode fixed at 0)", config.spi_flags)

    def close(self) -> None:
        try:
            self._spi.close()
        except Exception:
            pass

    def read(self, channel: int) -> int:
        if channel < 0 or channel > 7:
            raise ValueError(f"MCP3008 channel must be 0..7 (got {channel})")

        rx = self._spi.xfer2([1, (8 + int(channel)) << 4, 0])
        if rx is None or len(rx) < 3:
            raise RuntimeError(f"SPI transfer failed (rx_len={0 if rx is None else len(rx)})")

        value = ((rx[1] & 0x03) << 8) | rx[2]
        return int(value)


class MCP3008:
    """MCP3008 reader with selectable backend (spidev or pigpio)."""

    def __init__(self, config: MCP3008Config, *, pi: Optional["pigpio.pi"] = None):
        backend = str(config.spi_backend or "pigpio").strip().lower()

        if backend == "spidev":
            self._impl = _MCP3008Spidev(config)
        elif backend == "pigpio":
            self._impl = _MCP3008Pigpio(config, pi=pi)
        else:
            raise ValueError(f"Unknown MCP3008 spi_backend={config.spi_backend!r} (expected 'spidev' or 'pigpio')")

    def close(self) -> None:
        self._impl.close()

    def read(self, channel: int) -> int:
        return self._impl.read(channel)


class MCP3008Joystick:
    """Joystick adapter backed by MCP3008.

    Exposes a `read_raw()` method compatible with utils.input_processing.JoystickProcessor.
    """

    def __init__(
        self,
        *,
        adc: MCP3008,
        x_channel: int = 0,
        y_channel: int = 1,
        invert_x: bool = False,
        invert_y: bool = False,
        max_value: int = 1023,
    ):
        self._adc = adc
        self._x_channel = int(x_channel)
        self._y_channel = int(y_channel)
        self._invert_x = bool(invert_x)
        self._invert_y = bool(invert_y)
        self._max_value = int(max_value)

        self._last_error_time = 0.0
        self._error_min_interval_s = 5.0

    def close(self) -> None:
        # The ADC owns the pigpio handle; close it here for convenience.
        try:
            self._adc.close()
        except Exception:
            # Never crash shutdown paths.
            pass

    def read_raw(self) -> Tuple[int, int]:
        x = self._adc.read(self._x_channel)
        y = self._adc.read(self._y_channel)

        if self._invert_x:
            x = self._max_value - x
        if self._invert_y:
            y = self._max_value - y

        return int(x), int(y)
