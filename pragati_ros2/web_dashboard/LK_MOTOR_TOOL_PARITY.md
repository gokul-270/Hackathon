# LK Motor Tool Feature Parity — Session Handoff

## Goal

Make the Pragati web dashboard Motor Config tab achieve **full feature parity** with the
LingKong Motor Tool V2.36 (Windows desktop app). The dashboard uses Preact + HTM frontend,
FastAPI backend, and RS485 serial communication.

## Reference Screenshots

4 LK Motor Tool screenshots in `collected_logs/log3/LK Motor tool/`:
- `Screenshot 2026-03-10 121511.png` — **Setting tab**
- `Screenshot 2026-03-10 121520.png` — **Encoder tab**
- `Screenshot 2026-03-10 121529.png` — **Test tab**
- `Screenshot 2026-03-10 123203.png` — **Product tab**

## Architecture

- **Frontend files** (95% duplicated — ALL changes must go in BOTH):
  - `web_dashboard/frontend/js/tabs/MotorConfigTab.mjs` (~3932 lines, standalone)
  - `web_dashboard/frontend/js/tabs/entity/MotorConfigSubTab.mjs` (~4086 lines, entity-scoped)
- **Backend files:**
  - `web_dashboard/backend/rs485_driver.py` — RS485 protocol, 0x16 parser
  - `web_dashboard/backend/motor_api.py` — REST/WS endpoints
  - `web_dashboard/backend/pid_tuning_api.py` — PID read/write endpoints
- **RS485 Protocol spec:** `collected_logs/log3/RS485_spec.txt` (V2.35, 27 commands)

## Critical Rules

1. **NEVER send unknown/experimental commands** — only documented V2.35 commands + 0x16
2. **Frontend uses Preact + HTM** — `html\`...\`` tagged templates, NOT JSX
3. **`api()` uses positional args:** `api(path, method, body)` — NOT options object
4. **ALL reads must be manual** (button click only) — NO auto-read, NO auto-polling
5. **Do NOT modify backend unless specifically needed** for new endpoints
6. **Motor ID is 1**, port `/dev/ttyUSB0`, 115200 baud

## Current State: Connection Bar (Top — Always Visible)

**Matches LK Tool.** Single row with:
Port | Baudrate | ID | [Apply] | CONNECT/DISCONNECT | Connected/Disconnected badge |
**|** | Motor Off (red) | Motor On (green) | Comm Error : N | Transport dropdown + badge

**Status:** COMPLETE

---

## Tab 1: Setting — MOSTLY COMPLETE

**LK Tool layout:** 4 sections in 2x2 grid + 4 action buttons on right

### BasicSettingPanel (Top-Left) — PARTIAL

**Our component:** Lines ~1313-1380 in MotorConfigTab.mjs
**Data source:** `GET /api/motor/{id}/ext_config` → `config.basic_setting`

| # | LK Tool Field | Our Field | Data Source | Status |
|---|--------------|-----------|-------------|--------|
| 1 | Driver ID | Driver ID | `basic_setting.driver_id` (0x16 data[2]) | WORKING |
| 2 | Bus Type | Bus Type | `basic_setting.bus_type` (0x16 data[3]) | WORKING |
| 3 | RS485 Baudrate | RS485 Baudrate | `basic_setting.rs485_baudrate` (0x16 data[0]) | WORKING |
| 4 | CAN Baudrate | CAN Baudrate | `basic_setting.can_baudrate` (0x16 data[1]) | WORKING |
| 5 | Broadcast Mode | Broadcast Mode | `basic_setting.broadcast_mode` | NULL — offset unmapped |
| 6 | Spin Direction | Spin Direction | `basic_setting.spin_direction` | NULL — offset unmapped |
| 7 | Brake Resistor Control | Brake Resistor Control | `basic_setting.brake_resistor_control` | NULL — offset unmapped |
| 8 | Brake Resistor Voltage | Brake Resistor Voltage | `basic_setting.brake_resistor_voltage` | NULL — offset unmapped |

**Gap:** 4 fields show "N/A" because 0x16 offsets not reverse-engineered.
**Action:** Show "--" placeholder for unmapped fields. All fields are read-only (no write support).

### ProtectionSettingPanel (Top-Right) — PARTIAL

**Our component:** Lines ~1386-1445
**Data source:** `GET /api/motor/{id}/ext_config` → `config.protection_setting`

| # | LK Tool Field | Threshold | Enable | Status |
|---|--------------|-----------|--------|--------|
| 1 | Protect Motor Temperature | `motor_temp_threshold` | `motor_temp_enable` | NULL / NULL |
| 2 | Protect Driver Temperature | `driver_temp_threshold` | `driver_temp_enable` | NULL / NULL |
| 3 | Protect Under Voltage | `under_voltage_threshold` | `under_voltage_enable` | NULL / NULL |
| 4 | Protect Over Voltage | `over_voltage_threshold` | `over_voltage_enable` | NULL / NULL |
| 5 | Protect Over Current | `over_current_threshold` | `over_current_enable` | **6 (WORKING)** / NULL |
| 6 | Protect Over Current Time | `over_current_time` | (none) | NULL |
| 7 | Protect Short Circuit | (none) | `short_circuit_enable` | NULL |
| 8 | Protect Stall | `stall_threshold` | `stall_enable` | NULL / NULL |
| 9 | Protect Lost Input Time | `lost_input_time` | `lost_input_enable` | NULL / NULL |

**Gap:** 15 of 16 fields return NULL. Only `over_current_threshold` is mapped (0x16 data[85]).
**Action:** Show "--" for unmapped values. All fields are read-only.

### LimitsSettingPanel (Bottom-Left) — COMPLETE (but commands may fail)

**Our component:** Lines ~1959-2054
**Data source:** `GET /api/motor/{id}/extended_limits` (ParamID 0x40 commands)

| # | LK Tool Field | Endpoint | Status |
|---|--------------|----------|--------|
| 1 | Max Torque Current | `PUT .../max_torque_current` | ParamID 0x40 may not respond on V2.36 firmware |
| 2 | Max Speed | `PUT .../max_speed` | Same firmware issue |
| 3 | Max Angle | `PUT .../max_angle` | Same firmware issue |
| 4 | Speed Ramp | `PUT .../speed_ramp` | Same firmware issue |
| 5 | Current Ramp | `PUT .../current_ramp` | Same firmware issue |

Each has a "SET RAM" button. Layout matches LK Tool.
**Gap:** ParamID commands (0x40/0x42/0x44) DO NOT WORK on V2.36 firmware. Backend returns
`{_success: false, _warning: "..."}` gracefully. Frontend should show a toast/warning when
`_success === false` instead of silently failing.

### SettingPIDPanel (Bottom-Right) — COMPLETE (but read may fail)

**Our component:** Lines ~1886-1953
**Data source:** `GET /api/pid/read/{id}`, `POST /api/pid/write/{id}`

| Loop | Kp | Ki | SET RAM | Status |
|------|----|----|---------|--------|
| Angle | ✓ | ✓ | ✓ | PID read may return `{success:false}` on V2.36 |
| Speed | ✓ | ✓ | ✓ | Same |
| Current | ✓ | ✓ | ✓ | Same |

**Gap:** Frontend should show toast when `success === false`.

### Action Buttons (Right Side) — COMPLETE

| Button | API Call | Status |
|--------|---------|--------|
| Read Setting | calls `readGains()` | WORKING |
| Save Setting | `POST .../lifecycle {action:"save_rom"}` | WORKING |
| Reset Setting | `POST .../restore` | WORKING |
| Reboot Device | `POST .../lifecycle {action:"reboot"}` | WORKING |

---

## Tab 2: Encoder — UI PARITY DONE (data pending)

**LK Tool layout:** 2 panels side-by-side + Save/Read buttons
**Our layout:** Matches LK Tool — 2-panel grid + Save/Read at bottom-right + collapsible Advanced section

### LK Tool: Motor / Encoder Setting (Left Panel)

| # | Field | Type | Our Status |
|---|-------|------|------------|
| 1 | Motor Poles | number spinner | **UI DONE** — spinner present, disabled (needs 0x16 EEPROM mapping for data) |
| 2 | Encoder Type | read-only text | **UI DONE** — placeholder "--" (needs 0x16 EEPROM mapping) |
| 3 | Encoder Position | read-only text | **UI DONE** — placeholder "--" (needs 0x16 EEPROM mapping) |
| 4 | Motor Phase Sequence | read-only text | **UI DONE** — placeholder "--" (needs 0x16 EEPROM mapping) |
| 5 | Motor/Encoder Offset | read-only text | **WORKING** — shows offset from 0x90 read |
| 6 | Motor/Encoder Align Ratio | read-only text | **UI DONE** — placeholder "--" (needs 0x16 EEPROM mapping) |
| 7 | Motor/Encoder Align Voltage | number spinner + "Align" button | **UI DONE** — spinner + Align button present, disabled (needs 0x16 EEPROM mapping) |
| 8 | Motor Zero Position (Rom) | read-only + "Set" button | **WORKING** — shows raw_value from 0x90, Set button saves to ROM |

### LK Tool: Reducer / Encoder Setting (Right Panel)

| # | Field | Type | Our Status |
|---|-------|------|------------|
| 1 | Reduction Ratio | number spinner | **UI DONE** — spinner present, disabled (needs 0x16 EEPROM mapping) |
| 2 | Reducer/Encoder Align Value | read-only + "Clear" button | **UI DONE** — field + Clear button present, disabled (needs 0x16 EEPROM mapping) |
| 3 | Reducer Zero Position | read-only + "Set" button | **UI DONE** — field + Set button present, disabled (needs 0x16 EEPROM mapping) |

### LK Tool: Action Buttons

| Button | Our Status |
|--------|------------|
| Save | **HAVE** — Save button at bottom-right, calls saveZeroRom |
| Read | **HAVE** — Read button at bottom-right, reads encoder data (0x90) |

### Our EncoderPanel Layout

Matches LK Motor Tool V2.36 Encoder tab:
1. **Left panel:** Motor / Encoder Setting — all 8 fields with correct control types
2. **Right panel:** Reducer / Encoder Setting — all 3 fields with inline buttons (Clear, Set)
3. **Bottom-right:** Save and Read buttons
4. **Collapsible Advanced section:** Write Zero (RAM) + before/after comparison (our extension)

**Remaining work (P3 — requires hardware reverse engineering):**
- Map Motor Poles, Encoder Type, Encoder Position, Motor Phase Sequence, Align Ratio,
  Align Voltage, Reduction Ratio, Reducer Align Value, Reducer Zero Position to 0x16
  EEPROM byte offsets
- Enable the disabled spinner/button controls once data sources are mapped

---

## Tab 3: Product — COMPLETE

**LK Tool fields vs ours:**

| # | LK Tool Field | Our Field | Source | Status |
|---|--------------|-----------|--------|--------|
| 1 | Motor : MG6010E-i6 | Motor | `product_info.motor_name` (0x12) | WORKING |
| 2 | Motor version : V3.0 | Motor version | `product_info.motor_version` (0x12) | WORKING |
| 3 | Driver : DG60C7 | Driver | `product_info.driver_name` (0x12) | WORKING |
| 4 | Hardware version : V2.4 | Hardware version | `product_info.hardware_version` (0x12) | WORKING |
| 5 | Firmware version : V2.36 | Firmware version | `product_info.firmware_version` (0x12) | WORKING |
| 6 | Chip ID | Chip ID | `product_info.motor_serial_id` (0x12) | WORKING |
| 7 | Open File + path | — | SKIPPED (firmware download) | OUT OF SCOPE |
| 8 | Download | — | SKIPPED (firmware download) | OUT OF SCOPE |
| 9 | Read Info button | Read Info | `GET /api/motor/{id}/product_info` | WORKING |

**Status:** COMPLETE (firmware download intentionally skipped — too risky)

---

## Tab 4: Test — COMPLETE (with caveats)

**LK Tool layout:** 3 columns — Commands (left), State+SerialMonitor (center+right)

### Column 1: Commands Panel — COMPLETE

| Feature | LK Tool | Ours | Status |
|---------|---------|------|--------|
| Control Mode dropdown | Torque Control | 8 modes (0xA1-0xA8) | WORKING (more modes than LK) |
| Torque Current input | ✓ | ✓ | WORKING |
| Speed input | ✓ | ✓ | WORKING |
| Angle input + Rev checkbox | ✓ | ✓ (direction selector) | WORKING |
| Motor Stop button | ✓ | ✓ | WORKING |
| Send button | ✓ | ✓ | WORKING |
| Motor Restore button | ✓ | ✓ (in TestStatePanel) | WORKING |

### Column 2: State Values — COMPLETE

| Value | LK Tool | Ours | Status |
|-------|---------|------|--------|
| Bus Voltage | ✓ | ✓ (`state1.voltage_v`) | WORKING |
| Bus Current | ✓ | — | NOT AVAILABLE (only phase currents via State 3) |
| Motor Temp | ✓ | ✓ (`state1.temperature_c`) | WORKING |
| Torque Current | ✓ | ✓ (`state2.torque_current_a`) | WORKING |
| Speed | ✓ | ✓ (`state2.speed_dps`) | WORKING |
| Encoder | ✓ | ✓ (`state2.encoder_position`) | WORKING |
| IA, IB, IC | ✓ | ✓ (`state3.phase_current_a[0,1,2]`) | WORKING |
| Error flags (8) | ✓ checkboxes | ✓ checkboxes | WORKING |

| Button | LK Tool | Ours | Status |
|--------|---------|------|--------|
| Read State 1 | ✓ | ✓ | WORKING (but blocked by selectedMotor=null) |
| Read State 2 | ✓ | ✓ | Same blocker |
| Read State 3 | ✓ | ✓ | Same blocker |
| Clear Error | ✓ | ✓ | Same blocker |
| Brake / Brake Release | ✓ | ✓ | Same blocker |
| Read Multi Loop Angle | ✓ | ✓ | Same blocker |
| Read Single Loop Angle | ✓ | ✓ | Same blocker |
| Clear Motor Loops | ✓ | ✓ | Same blocker |
| Set Motor Zero (RAM) | ✓ | ✓ | Same blocker |
| Motor Restore | ✓ | ✓ | Same blocker |

### Column 3: Serial Monitor — COMPLETE

| Feature | LK Tool | Ours | Status |
|---------|---------|------|--------|
| TX/RX hex frames | ✓ (green TX, orange RX) | ✓ (same colors) | WORKING |
| Clear Text button | ✓ | ✓ | WORKING |
| Auto-scroll | — | ✓ (checkbox) | EXTRA |

### **CRITICAL BLOCKER: `selectedMotor` is null**

ALL Test tab buttons silently return because of `if (!selectedMotor) return` guards.

**Root cause:** After connecting, `handleConnect` calls `checkNodes()` which populates the
`motors` array, but nothing calls `onMotorSelect(motorId)` to set `selectedMotor`.

**Fix needed:** After successful connect + `checkNodes()`, auto-call `onMotorSelect` with
the connected motor ID. Two approaches:

**(A) useEffect approach (more robust):**
```js
// Add after other useEffects in main component:
useEffect(() => {
    if (motors.length > 0 && connInfo.connected && !selectedMotor) {
        const m = motors.find(m => String(m.motor_id) === String(connInfo.motor_id));
        if (m) onMotorSelect(m.motor_id);
    }
}, [motors, connInfo.connected, connInfo.motor_id, selectedMotor, onMotorSelect]);
```

**(B) Inline in handleConnect (simpler):**
After `checkNodes()` resolves, fetch motors directly and call `onMotorSelect`.

**Must be applied in BOTH .mjs files.**

---

## Tab 5: PID Tuning — OUR ADDITION (Not in LK Tool)

LK Tool has "About" as the 5th tab. We replaced it with a full PID Tuning workspace:
- PIDPanel (9-gain sliders), StepTestPanel, AutoTunePanel, ProfilePanel, WizardPanel
- MetricsPanel, RuleComparisonTable, SessionLog
- MotorChartsPanel (live data + step response charts)
- SafetyBar (e-stop, session status, override limits)

**Status:** COMPLETE (this is our value-add over LK Tool)

---

## Priority Fix List

### P0 — Blocking
1. **Fix `selectedMotor` null** — Test tab buttons don't work at all

### P1 — UI Completeness
2. ~~**Rebuild Encoder tab** to match LK Tool 2-panel layout with all fields (placeholders for unmapped)~~ **DONE**
3. **Show toast/warning** in LimitsSettingPanel when `_success === false`
4. **Show toast/warning** in SettingPIDPanel when `success === false`

### P2 — Polish
5. **BasicSettingPanel** — ensure unmapped fields show "--" cleanly (not "null" or "N/A")
6. **ProtectionSettingPanel** — same "--" treatment for null values
7. **Bus Current** in Test tab — LK Tool shows it but RS485 protocol doesn't provide it
   (only phase currents). Show "--" with tooltip "Not available via RS485"

### P3 — Future (requires hardware + reverse engineering)
8. Map remaining 0x16 EEPROM offsets (broadcast_mode, spin_direction, brake_resistor, etc.)
9. Map 0x16 protection thresholds (all except over_current)
10. Encoder tab fields from 0x16 (motor poles, encoder type, reduction ratio, etc.)
11. EEPROM write support (currently all 0x16-sourced fields are read-only)

---

## Backend Endpoints Reference

### Working Endpoints (confirmed on hardware)
| Endpoint | RS485 Cmd | Description |
|----------|-----------|-------------|
| `GET /api/motor/{id}/state` | 0x9A | Quick state (temp, voltage, speed, on/off) |
| `GET /api/motor/{id}/state_detailed` | 0x9A+0x9C+0x9D | Full state 1+2+3 |
| `GET /api/motor/{id}/ext_config` | 0x16 | EEPROM config dump (108 bytes) |
| `GET /api/motor/{id}/product_info` | 0x12 | Motor/driver model, versions |
| `GET /api/motor/{id}/encoder` | 0x90 | Encoder raw/offset/original |
| `GET /api/motor/{id}/angles` | 0x92+0x94 | Multi-turn + single-turn angles |
| `POST /api/motor/{id}/encoder/zero` | 0x91 | Write encoder zero (RAM/ROM) |
| `POST /api/motor/{id}/brake` | 0x8C | Brake engage/release |
| `POST /api/motor/{id}/command` | 0xA1-0xA8 | Motor control commands |
| `POST /api/motor/{id}/lifecycle` | 0x80/0x81/0x88/0xFE | On/Off/Stop/Reboot/SaveROM |
| `POST /api/motor/{id}/restore` | 0x89(?) | Motor restore |
| `POST /api/motor/{id}/clear_multi_turn` | 0x94(?) | Clear multi-turn counter |
| `POST /api/motor/{id}/errors/clear` | 0x9B | Clear error flags |
| `GET /api/motor/serial_log` | — | Serial frame log + comm errors |
| `WS /api/motor/ws/serial_log` | — | Live serial frame WebSocket |

### Gracefully-Failing Endpoints (ParamID not supported on V2.36)
| Endpoint | RS485 Cmd | Description |
|----------|-----------|-------------|
| `GET /api/motor/{id}/extended_limits` | 0x40 (ParamID) | Returns `{_success:false}` |
| `PUT /api/motor/{id}/extended_limits/{param}` | 0x42/0x44 | Returns `{_success:false}` |
| `GET /api/pid/read/{id}` | 0x30 | Returns `{success:false}` |
| `POST /api/pid/write/{id}` | 0x31/0x32 | May not work |

---

## 0x16 EEPROM Map (Current Knowledge)

108-byte data payload from cmd 0x16. Offsets into data (after 5-byte header).

### Mapped (HIGH confidence)
| Offset | Bytes | Field | Value (our motor) |
|--------|-------|-------|-------------------|
| 0 | 1 | RS485 baud divider | 0x1C (28 → 115200) |
| 1 | 1 | CAN baud index | 0x07 (→ 1000000) |
| 2 | 1 | Driver ID | 0x01 (1) |
| 3 | 1 | Bus Type | 0x01 (RS485) |
| 85 | 1 | Over Current threshold | 0x06 (6A) |
| 104-105 | 2 LE | EEPROM version | 0x1234 |
| 106-107 | 2 LE | EEPROM magic | 0x55AA |

### Unmapped Regions
| Offset Range | Notes |
|-------------|-------|
| 4-41 | Encoder calibration data (changes between reads, NOT config) |
| 42-77 | Zero padding |
| 78-84 | Protection/config region (partially explored) |
| 86-103 | Unknown config fields |

### Known Hardware Values (from LK Tool, not mapped to offsets)
- Motor Poles: 28
- Encoder Type: 16Bit Encoder
- Encoder Position: Reverse
- Motor Phase Sequence: Normal
- Reduction Ratio: 6
- Brake Resistor Voltage: 56.00

These values ARE somewhere in the 0x16 response but their exact byte offsets are not yet
reverse-engineered. For now, show them as read-only placeholders with "--".

---

## File Locations Quick Reference

| File | Lines | Purpose |
|------|-------|---------|
| `web_dashboard/frontend/js/tabs/MotorConfigTab.mjs` | ~3932 | Standalone motor config |
| `web_dashboard/frontend/js/tabs/entity/MotorConfigSubTab.mjs` | ~4086 | Entity-scoped duplicate |
| `web_dashboard/frontend/styles.css` | — | `.motor-number-input` etc |
| `web_dashboard/backend/rs485_driver.py` | ~1007 | RS485 protocol + 0x16 parser |
| `web_dashboard/backend/motor_api.py` | — | REST/WS endpoints |
| `web_dashboard/backend/pid_tuning_api.py` | — | PID endpoints |
| `web_dashboard/backend/dashboard_server.py` | — | Server entry point |
| `collected_logs/log3/RS485_spec.txt` | — | Protocol V2.35 spec |
| `collected_logs/log3/LK Motor tool/` | — | 4 screenshots |

---

## Launch Command

```bash
cd /home/udayakumar/pragati_ros2/web_dashboard
python3 -m backend.dashboard_server --serial-port /dev/ttyUSB0 --motor-id 1 --transport rs485 --port 8092
```

Without hardware (no `/dev/ttyUSB0`):
```bash
cd /home/udayakumar/pragati_ros2/web_dashboard
python3 -m backend.dashboard_server --port 8092 --transport rs485 --motor-id 1
```
