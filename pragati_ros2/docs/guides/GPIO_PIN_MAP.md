# GPIO Pin Map — Pragati Cotton Picking Robot

The Pragati system uses **separate Raspberry Pi 4B boards** for each role:

- **Arm RPi** — controls motors, end-effector, LEDs, and sensors for one picking arm
- **Vehicle RPi** — controls vehicle-level switches, LEDs, and peripherals

Because each role runs on its own physical board, the same BCM pin number can appear
in both roles without conflict. See [Cross-Role Pin Sharing](#cross-role-pin-sharing)
for the overlap table.

**Authoritative source files:**

- Arm role: `src/motor_control_ros2/include/motor_control_ros2/gpio_control_functions.hpp`
- Vehicle role: `src/vehicle_control/config/constants.py`

---

## Arm-Role Pins

Source: `src/motor_control_ros2/include/motor_control_ros2/gpio_control_functions.hpp`

13 logical pin assignments (12 unique BCM pins — BCM 12 is aliased).

| BCM Pin | Constant Name | Purpose | Direction |
|--------:|---------------|---------|-----------|
| 2 | `SHUTDOWN_SWITCH` | Shutdown switch input | Input |
| 3 | `START_SWITCH` | Start switch input | Input |
| 4 | `GREEN_LED_PIN` | Green status LED (robot ready) | Output |
| 12 | `END_EFFECTOR_DROP_ON` | M2 enable (drop motor) | Output |
| 12 | `COTTON_DROP_SERVO_PIN` | Cotton drop servo (aliases BCM 12) | Output |
| 13 | `END_EFFECTOR_DIRECTION_PIN` | M1 direction (Cytron board) | Output |
| 14 | `TRANSPORT_SERVO_PIN` | Transport shutter servo | Output |
| 15 | `RED_LED_PIN` | Red status LED (error/busy) | Output |
| 17 | `CAMERA_LED_PIN` | Camera illumination LED | Output |
| 18 | `COMPRESSOR_PIN` | Compressor flow control | Output |
| 20 | `END_EFFECTOR_DROP_DIRECTION` | M2 direction | Output |
| 21 | `END_EFFECTOR_ON_PIN` | M1 enable (Cytron board) | Output |
| 24 | `VACUUM_MOTOR_ON_PIN` | Vacuum pump motor | Output |

> **Note:** BCM 12 is shared between `END_EFFECTOR_DROP_ON` and `COTTON_DROP_SERVO_PIN`.
> These are two logical names for the same physical pin. See [Known Issues](#known-issues)
> for whether the servo alias is still active.

---

## Vehicle-Role Pins

Source: `src/vehicle_control/config/constants.py`

17 pin assignments (15 unique BCM pins). Includes reserved pins not yet wired.

| BCM Pin | Constant Name | Purpose | Direction | Status |
|--------:|---------------|---------|-----------|--------|
| 4 | `SYSTEM_RESET` | Reboot button | Input | Active |
| 5 | `ARM_SHUTDOWN` | Shutdown button | Input | Active |
| 6 | `ARM_START` | Start button | Input | Active |
| 7 | `ADC_ENABLE` | ADC enable (SPI CE1) | SPI | Active |
| 8 | `CAN_ENABLE` | CAN bus enable (SPI CE0) | SPI | Active |
| 12 | `BRAKE_SWITCH` | Brake switch | Input | Reserved, unused |
| 13 | `VEHICLE_STOP` | Vehicle stop | Input | Reserved, unused |
| 16 | `DIRECTION_LEFT` | Direction left switch | Input | Active |
| 17 | `RASPBERRY_PI_LED` | RPi power LED (Red) | Output | Active |
| 20 | `AUTOMATIC_MODE` | Auto/Manual mode switch | Input | Active |
| 21 | `DIRECTION_RIGHT` | Direction right switch | Input | Active |
| 22 | `SOFTWARE_STATUS_LED` | Software status LED (Green) | Output | Active |
| 23 | `ERROR_LED` | Error LED | Output | Reserved, unused |
| 24 | `FAN` | Fan control | Output | Reserved, unused |
| 27 | `YELLOW_LED` | Yellow/Orange LED | Output | Active |

> **Aliases:** `GREEN_LED` = BCM 22 (same as `SOFTWARE_STATUS_LED`),
> `RED_LED` = BCM 17 (same as `RASPBERRY_PI_LED`).

---

## Cross-Role Pin Sharing

These BCM pins appear in **both** roles. Since arm and vehicle run on separate physical
RPi boards, these are **not** electrical conflicts — just shared pin numbers.

| BCM | Arm Purpose | Vehicle Purpose |
|----:|-------------|-----------------|
| 4 | Green LED | System Reset |
| 12 | EE Drop ON | Brake Switch (unused) |
| 13 | EE Direction | Vehicle Stop (unused) |
| 17 | Camera LED | RPi Power LED |
| 20 | EE Drop Direction | Auto/Manual Switch |
| 21 | EE ON (M1 enable) | Direction Right Switch |
| 24 | Vacuum Motor | Fan (unused) |

---

## Known Issues

- **E-stop pin unassigned (GAP-ELEC-002)** — The hardware E-stop has no GPIO pin defined
  in either role. A dedicated pin assignment is needed before field deployment.

- **production.yaml discrepancies** — `auto_manual_switch_pin` is listed as BCM 26 in
  production config but BCM 20 in `constants.py`. Similarly, `arm_start_pin` is BCM 16
  in production config but BCM 6 in `constants.py`. Physical wiring must be verified to
  determine which values are correct (see `docs/project-notes/GPIO_PIN_REVIEW.md`).

- **BCM 12 aliased** — `COTTON_DROP_SERVO_PIN` aliases `END_EFFECTOR_DROP_ON` on the same
  physical pin. Confirm whether the servo function is still used or if this alias should
  be removed.

---

## GPIO Library Stack

| Layer | Library | Used By |
|-------|---------|---------|
| Production daemon | `pigpiod` (started via systemd) | Both roles |
| C interface | `pigpiod_if2` | `motor_control_ros2` (arm role) |
| Python interface | `pigpio` module | `vehicle_control` (vehicle role) |
| Legacy test scripts | `RPi.GPIO` | Some older scripts (not production) |
| Not used in production | `libgpiod`, `lgpio` | — |

---

## Related Documents

- GPIO Setup Guide: `docs/guides/GPIO_SETUP_GUIDE.md`
- GPIO Pin Review (pending): `docs/project-notes/GPIO_PIN_REVIEW.md`
- Technical Specification: `docs/specifications/TECHNICAL_SPECIFICATION_DOCUMENT.md`
  (Section 4.4.1, Appendix D)
