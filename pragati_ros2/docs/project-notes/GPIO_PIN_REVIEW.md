# GPIO Pin Review — For Shwetha & Gokul

**Created:** March 08, 2026
**Author:** Udayakumar
**Context:** gpio-pin-consolidation OpenSpec change — code/doc changes applied, need physical verification before field trial
**Action Required:** Review each section, verify against physical wiring, sign off or flag corrections

---

## Why This Review Exists

We found 14 GPIO pin conflicts across 5+ files (GAP-GPIO-001). Code and documentation
changes have been applied to align everything to the two authoritative sources:

- **Arm role:** `gpio_control_functions.hpp` (compile-time constants, pigpiod API)
- **Vehicle role:** `constants.py` (Python dataclass, pigpio module)

**Some changes involve pin numbers that may differ from actual physical wiring.**
Before we commit and deploy, you need to verify each flagged item against the real hardware.

---

## Section 1: Arm GPIO Pins (Reviewer: Shwetha)

Source of truth: `src/motor_control_ros2/include/motor_control_ros2/gpio_control_functions.hpp`

| BCM Pin | Constant Name | Purpose | Direction | Verify? |
|---------|---------------|---------|-----------|---------|
| 2 | SHUTDOWN_SWITCH | Shutdown switch input | Input | |
| 3 | START_SWITCH | Start switch input | Input | |
| 4 | GREEN_LED_PIN | Green status LED (robot ready) | Output | |
| 12 | END_EFFECTOR_DROP_ON | M2 enable (drop motor) | Output | |
| 12 | COTTON_DROP_SERVO_PIN | **Alias — same BCM 12 as above** | Output | **NOTE: shared pin** |
| 13 | END_EFFECTOR_DIRECTION_PIN | M1 direction (Cytron board) | Output | |
| 14 | TRANSPORT_SERVO_PIN | Transport shutter servo | Output | |
| 15 | RED_LED_PIN | Red status LED (error/busy) | Output | |
| 17 | CAMERA_LED_PIN | Camera illumination LED | Output | |
| 18 | COMPRESSOR_PIN | Compressor flow control | Output | |
| 20 | END_EFFECTOR_DROP_DIRECTION | M2 direction | Output | |
| 21 | END_EFFECTOR_ON_PIN | M1 enable (Cytron board) | Output | |
| 24 | VACUUM_MOTOR_ON_PIN | Vacuum pump motor | Output | |

### What Changed (arm side)

1. **Removed 11 stale pin members from `yanthra_move_system.hpp`** (lines 382-393). These
   were class defaults never used at runtime — all GPIO goes through the functions API.
   6 of 11 had wrong values (e.g., Green LED was 25 instead of 4, Camera LED was 18
   instead of 17, Shutdown switch was 27 instead of 2).

2. **Fixed `endeffector_control.py`** — had BOARD pins (35, 32) with BCM mode. Changed to
   BCM 21 (M1 enable) and BCM 13 (M1 direction).

3. **Fixed `ee_test_bcm.py`** — corrected swapped comments (said GPIO 19 for pin 12 and
   vice versa).

### Shwetha: Please Verify

- [ ] **BCM 12 shared between END_EFFECTOR_DROP_ON and COTTON_DROP_SERVO_PIN** — is
  COTTON_DROP_SERVO_PIN still used? Or is it dead code?
- [ ] **BCM 21 and 13** — confirm these match physical Cytron board wiring for M1
  enable/direction
- [ ] **BCM 14 (Transport servo)** — is this actively wired and used?
- [ ] **BCM 18 (Compressor)** — confirm physical connection

---

## Section 2: Vehicle GPIO Pins (Reviewer: Gokul)

Source of truth: `src/vehicle_control/config/constants.py`

| BCM Pin | Constant Name | Purpose | Direction | Verify? |
|---------|---------------|---------|-----------|---------|
| 4 | SYSTEM_RESET | Reboot button | Input | |
| 5 | ARM_SHUTDOWN | Shutdown button | Input | |
| 6 | ARM_START | Start button | Input | **FLAG** |
| 7 | ADC_ENABLE | ADC enable (SPI CE1) | SPI | |
| 8 | CAN_ENABLE | CAN bus enable (SPI CE0) | SPI | |
| 12 | BRAKE_SWITCH | Reserved, unused | Input | |
| 13 | VEHICLE_STOP | Reserved, unused | Input | |
| 16 | DIRECTION_LEFT | Direction left switch | Input | |
| 17 | RASPBERRY_PI_LED | RPi power LED (Red) | Output | |
| 20 | AUTOMATIC_MODE | Auto/Manual mode switch | Input | **FLAG** |
| 21 | DIRECTION_RIGHT | Direction right switch | Input | |
| 22 | SOFTWARE_STATUS_LED | Software status LED (Green) | Output | |
| 23 | ERROR_LED | Reserved, unused | Output | |
| 24 | FAN | Reserved, unused | Output | |
| 27 | YELLOW_LED | Yellow/Orange LED | Output | |

### What Changed (vehicle side)

1. **Renamed `production.yaml` pins** to match `constants.py` naming:
   - `stop_button_pin` → `system_reset_pin`
   - `direction_switch_pin` → `direction_right_pin`

2. **Fixed "GPIO 27" comments** in `vehicle_control_node.py` (4 places) — should have
   been "GPIO 22" for SOFTWARE_STATUS_LED.

3. **Fixed `vehicle_gpio_testing.py`** — GPIO 22 and 27 labels were swapped.

### CRITICAL: Two Pin Discrepancies Needing Physical Verification

These are the most important items in this review. The YAML config has different pin
numbers from `constants.py`, and we don't know which is correct without checking the
physical wiring.

#### Discrepancy 1: Auto/Manual Mode Switch

| Source | Pin |
|--------|-----|
| `production.yaml` (`auto_manual_switch_pin`) | **BCM 26** |
| `constants.py` (`AUTOMATIC_MODE`) | **BCM 20** |
| `vehicle_control_node.py` (runtime) | Uses **constants.py → BCM 20** |

**The YAML value (26) is never loaded by the node** — it reads from `constants.py` directly.
If the physical wire goes to BCM 26, the software is reading the wrong pin.

#### Discrepancy 2: Arm Start Button

| Source | Pin |
|--------|-----|
| `production.yaml` (`arm_start_pin`) | **BCM 16** |
| `constants.py` (`ARM_START`) | **BCM 6** |
| `vehicle_control_node.py` (runtime) | Reads YAML → defaults to **6** if not in YAML |

**The YAML says 16 but `start_switch_pin` in YAML is 6** (different key). The node
reads `start_switch_pin` (6), not `arm_start_pin` (16). If the physical wire goes to
BCM 16, the node is reading the wrong pin.

### Gokul: Please Verify

- [ ] **Auto/Manual switch** — physically wired to BCM **20** or BCM **26**?
  - If 20: `constants.py` is correct, YAML comment is sufficient
  - If 26: `constants.py` must be updated to 26, and node must read from YAML
- [ ] **Arm start button** — physically wired to BCM **6** or BCM **16**?
  - If 6: current code is correct
  - If 16: `constants.py` ARM_START must change to 16
- [ ] **BCM 22 (Green LED)** — confirm this is the physically wired software status LED
- [ ] **BCM 27 (Yellow/Orange LED)** — confirm physical wiring
- [ ] **BCM 12, 13 (BRAKE_SWITCH, VEHICLE_STOP)** — are these actually wired or truly unused?

---

## Section 3: Cross-Role Pin Sharing

Both arm and vehicle use separate RPi 4B boards, so the same BCM pin number can be used
for different purposes on different boards. This is expected, not a conflict.

Shared BCM numbers (different purpose per role):

| BCM Pin | Arm Purpose | Vehicle Purpose |
|---------|-------------|-----------------|
| 4 | Green LED (Output) | System Reset (Input) |
| 12 | EE Drop ON (Output) | Brake Switch (Input, unused) |
| 13 | EE Direction (Output) | Vehicle Stop (Input, unused) |
| 17 | Camera LED (Output) | RPi Power LED (Output) |
| 20 | EE Drop Direction (Output) | Auto/Manual Switch (Input) |
| 21 | EE ON / M1 Enable (Output) | Direction Right Switch (Input) |
| 24 | Vacuum Motor (Output) | Fan (Output, unused) |

**No action needed** — these are on separate physical boards.

---

## Section 4: E-Stop Pin (UNRESOLVED — GAP-ELEC-002)

The hardware E-stop GPIO pin assignment is still undefined. This is tracked separately
as GAP-ELEC-002 and is **not resolved by this change**.

- **Arm side:** No E-stop pin in `gpio_control_functions.hpp`
- **Vehicle side:** No E-stop pin in `constants.py`
- **TSD:** Previously listed "E-Stop: TBD"

**Decision needed from Gokul/Rajesh:** Which BCM pin will the hardware E-stop use?
This affects task V12 (E-stop integration, deadline Mar 12).

---

## How to Sign Off

For each section, either:

1. **Confirm correct** — mark the checkbox, no changes needed
2. **Flag correction** — write the correct pin number and which file(s) need updating

Return this document (or a message) with your findings. Udayakumar will apply any
corrections before final commit.

**Deadline:** Before March 12 (Go/No-Go decision 3)

---

## Files Changed in This Consolidation

| File | Change |
|------|--------|
| `src/yanthra_move/include/yanthra_move/yanthra_move_system.hpp` | Removed 11 stale GPIO pin members |
| `src/vehicle_control/config/production.yaml` | Renamed 2 pins, added discrepancy comments |
| `src/vehicle_control/integration/vehicle_control_node.py` | Fixed 4 "GPIO 27" → "GPIO 22" comments |
| `scripts/testing/gpio/vehicle_gpio_testing.py` | Swapped GPIO 22/27 labels |
| `scripts/testing/motor/endeffector_control.py` | Fixed BOARD→BCM pin numbers (35→21, 32→13) |
| `scripts/testing/motor/ee_test_bcm.py` | Fixed swapped comments |
| `docs/specifications/TECHNICAL_SPECIFICATION_DOCUMENT.md` | Updated Section 4.4.1 and Appendix D pin tables |
| `docs/guides/GPIO_SETUP_GUIDE.md` | Replaced RPi.GPIO with pigpiod, updated pin tables |
