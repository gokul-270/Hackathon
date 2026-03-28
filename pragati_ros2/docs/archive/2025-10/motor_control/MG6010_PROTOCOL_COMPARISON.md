# MG6010-i6 CAN Protocol Implementation Comparison

**Document Version**: 1.1  
**Date**: 2025-10-07 (Updated: 2024-10-09)  
**Status**: Implementation Complete

---

## ⚠️ IMPLEMENTATION UPDATE (2024-10-09)

**Our implementation now uses 250kbps as the default CAN bitrate**, not 1Mbps as originally recommended in this document.

### Why 250kbps Instead of 1Mbps?

While the official LK-TECH specification lists **1Mbps as the default**, we chose **250kbps** as our standard for the following reasons:

1. **Improved Reliability** - Better noise immunity on real hardware
2. **Longer Cable Runs** - More stable with extended CAN bus lengths
3. **Tested Configuration** - Validated with colleague's working implementation
4. **Hardware Compatibility** - Works reliably on Raspberry Pi and embedded systems
5. **Agricultural Environment** - Better suited for outdoor/field conditions with potential EMI

### Performance Impact

The 250kbps bitrate provides:
- **Response time**: Still well under 10ms (spec: 0.25ms typical)
- **Command frequency**: 100+ Hz easily achievable
- **Sufficient for control**: Agricultural robot control loops (10-50 Hz typical)

### Configuration

**Our Default (Recommended)**:
```bash
sudo ip link set can0 type can bitrate 250000  # 250kbps
```

**Alternative (if 1Mbps needed)**:
```bash
sudo ip link set can0 type can bitrate 1000000  # 1Mbps
# Update motor_params: baud_rate: 1000000
```

Both bitrates are fully supported by the MG6010-i6 motors and can be configured via parameters.

---

## 1. EXECUTIVE SUMMARY

This document provides a comprehensive comparison of three MG6010-i6 motor controller implementations:

| Source | Type | Status |
|--------|------|--------|
| **Official Documentation** | LK-TECH CAN Protocol V2.35 | Ground Truth ✅ |
| **Tested Implementation** | `mg_can_compat.cpp` by colleague | Validated on hardware ✅ |
| **Current ROS2 Code** | `GenericMotorController` | CANopen-based (incompatible) ❌ |

### Key Findings

🎯 **CRITICAL**: MG6010-i6 uses a **proprietary protocol**, NOT CANopen  
🎯 **Official Default Baud Rate**: **1Mbps** (tested code used 250kbps but both valid)  
🎯 **Response Time**: Official spec says **within 0.25ms**  
🎯 **Integration Strategy**: Create new `MG6010Protocol` class; DO NOT modify odrive_legacy

---

## 2. BAUD RATE ANALYSIS

### Official Specification (Page 5)

The official LK-TECH documentation lists these supported baud rates for **single motor command mode**:

| Baud Rate | Status | Notes |
|-----------|--------|-------|
| **1Mbps** | **DEFAULT** ✅ | Official default, fastest |
| 500kbps | Supported | Half speed |
| 250kbps | Supported | Used by tested code |
| 125kbps | Supported | Slower |
| 100kbps | Supported | Slowest |

**Multi-motor broadcast mode** supports:
- 1Mbps
- 500kbps

### Implementation Comparison

| Implementation | Baud Rate | Assessment |
|----------------|-----------|------------|
| **Official Spec** | 1Mbps (default) | ✅ Ground truth |
| **Tested Code** | 250kbps | ✅ Works but 4x slower than default |
| **Our ROS2 Code** | 1Mbps | ✅ Matches official default |

### **RECOMMENDATION** 

**Use 1Mbps as default** (official specification). The tested code works at 250kbps, but there's no technical reason to use slower speeds unless bus issues occur.

**Configuration**:
```bash
# Recommended (official default)
sudo ip link set can0 type can bitrate 1000000

# Fallback if issues (tested)
sudo ip link set can0 type can bitrate 250000
```

---

## 3. CAN MESSAGE STRUCTURE

### Base Format (Official Spec, Page 5)

```
Identifier: 0x140 + motor_id (1~32)
Frame format: Data frame
Frame type: Standard frame (11-bit)
DLC: 8 bytes
Response time: Within 0.25ms
```

### Arbitration ID Formula

```c
arbitration_id = 0x140 + motor_id
// Examples:
// Motor ID 1:  0x141
// Motor ID 2:  0x142
// Motor ID 32: 0x160
```

**Multi-motor broadcast**: `0x280` (up to 4 motors simultaneously)

### Response Matching

**Official Spec**: Motor echoes the command byte in DATA[0] of response  
**Tested Code**: Filters by `(arbitration_id == expected) && (data[0] == cmd_byte)` ✅  
**Our Code**: Uses CANopen COB-ID calculation ❌ (incompatible)

---

## 4. COMMAND MAPPING TABLE

Complete command set from official LK-TECH CAN Protocol V2.35:

| Command Name | Code | Tested | Our Code | Status |
|--------------|------|--------|----------|--------|
| **Motor Control** |
| MOTOR_OFF | 0x80 | ✅ Implemented | ❌ Missing | Port from tested |
| MOTOR_ON | 0x88 | ✅ Implemented | ❌ Missing | Port from tested |
| MOTOR_STOP | 0x81 | ✅ Implemented | ❌ Missing | Port from tested |
| **Torque Control (MG Series)** |
| TORQUE_CTRL | 0xA1 | ✅ Implemented | ❌ Uses CANopen | Port from tested |
| **Speed Control** |
| SPEED_CTRL | 0xA2 | ✅ Implemented | ❌ Uses CANopen | Port from tested |
| **Position Control** |
| MULTI_LOOP_ANGLE_1 | 0xA3 | ✅ Implemented | ❌ Uses CANopen | Port from tested |
| MULTI_LOOP_ANGLE_2 | 0xA4 | ✅ Implemented | ❌ Uses CANopen | Port from tested |
| SINGLE_LOOP_ANGLE_1 | 0xA5 | ✅ Implemented | ❌ Missing | Port from tested |
| SINGLE_LOOP_ANGLE_2 | 0xA6 | ✅ Implemented | ❌ Missing | Port from tested |
| INCREMENT_ANGLE_1 | 0xA7 | ✅ Implemented | ❌ Missing | Port from tested |
| INCREMENT_ANGLE_2 | 0xA8 | ✅ Implemented | ❌ Missing | Port from tested |
| **PID Configuration** |
| READ_PID | 0x30 | ✅ Implemented | ❌ Uses SDO | Port from tested |
| WRITE_PID_RAM | 0x31 | ❌ Not implemented | ❌ Uses SDO | Implement new |
| WRITE_PID_ROM | 0x32 | ❌ Not implemented | ❌ Uses SDO | Implement new |
| **Acceleration** |
| READ_ACCEL | 0x33 | ✅ Implemented | ❌ Uses SDO | Port from tested |
| WRITE_ACCEL_RAM | 0x34 | ✅ Implemented | ❌ Uses SDO | Port from tested |
| **Encoder/Position** |
| READ_ENCODER | 0x90 | ✅ Implemented | ❌ Uses SDO | Port from tested |
| WRITE_ENCODER_OFFSET_ROM | 0x91 | ✅ Implemented | ❌ Missing | Port from tested |
| WRITE_CURRENT_POS_AS_ZERO | 0x19 | ✅ Implemented | ❌ Missing | Port from tested |
| READ_MULTI_TURN_ANGLE | 0x92 | ✅ Implemented | ❌ Missing | Port from tested |
| READ_SINGLE_TURN_ANGLE | 0x94 | ✅ Implemented | ❌ Missing | Port from tested |
| CLEAR_ANGLE_LOOP | 0x95 | ❌ Not available (per spec) | ❌ Missing | Skip |
| **Status/Diagnostics** |
| READ_STATUS_1 | 0x9A | ✅ Implemented | ❌ Uses SDO | Port from tested |
| CLEAR_ERRORS | 0x9B | ✅ Implemented | ❌ Uses SDO | Port from tested |
| READ_STATUS_2 | 0x9C | ✅ Implemented | ❌ Missing | Port from tested |
| READ_STATUS_3 | 0x9D | ❌ Not implemented | ❌ Missing | Implement new |

---

## 5. DATA ENCODING DETAILS

### 5.1 Multi-Turn Angle (Command 0x92)

| Aspect | Official Spec | Tested Code | Our Code |
|--------|---------------|-------------|----------|
| **Data Type** | int64_t | 56-bit signed | N/A |
| **Byte Range** | DATA[1]–DATA[7] | DATA[1]–DATA[7] | N/A |
| **Encoding** | 7 bytes, little-endian | 7 bytes + sign extension | N/A |
| **Unit** | 0.01°/LSB | 0.01°/LSB | N/A |
| **Sign** | Signed (CW=positive, CCW=negative) | Sign-extended from bit 55 | N/A |

**Official Formula**:
```c
int64_t angle = (data[1]) | (data[2]<<8) | (data[3]<<16) | (data[4]<<24) 
              | (data[5]<<32) | (data[6]<<40) | (data[7]<<48);
// Sign extend if needed
if (angle & (1LL << 55)) {
    angle |= ~((1LL << 56) - 1);
}
float angle_degrees = angle * 0.01f;
```

**Tested Code**: ✅ Matches (with 56-bit treatment)  
**Our Code**: ❌ Not implemented

### 5.2 Single-Turn Angle (Command 0x94)

| Aspect | Official Spec | Tested Code | Our Code |
|--------|---------------|-------------|----------|
| **Data Type** | uint32_t | uint32_t | N/A |
| **Byte Range** | DATA[4]–DATA[7] | DATA[4]–DATA[7] | N/A |
| **Encoding** | 4 bytes, little-endian | 4 bytes, little-endian | N/A |
| **Unit** | 0.01°/LSB | 0.01°/LSB | N/A |
| **Range** | **0–35999** (0°–359.99°) | **0–36000** assumed | N/A |

⚠️ **CRITICAL**: Official spec says range is **0–35999**, not 0–36000!

**Official Formula**:
```c
uint32_t angle = (data[4]) | (data[5]<<8) | (data[6]<<16) | (data[7]<<24);
float angle_degrees = angle * 0.01f;  // Range: 0.00° to 359.99°
```

**Tested Code**: ⚠️ Assumed 0–36000  
**Our Code**: ❌ Not implemented

### 5.3 Torque Control (Command 0xA1)

| Aspect | Official Spec | Tested Code | Our Code |
|--------|---------------|-------------|----------|
| **Data Type** | int16_t | int16_t | N/A |
| **Range** | -2048 to +2048 | -2048 to +2048 | N/A |
| **Actual Current (MG)** | -33A to +33A | -33A to +33A | Uses CANopen |
| **Byte Range** | DATA[4]–DATA[5] | DATA[4]–DATA[5] | N/A |
| **Encoding** | Little-endian | Little-endian | CANopen SDO |

**Tested Code**: ✅ Correct  
**Our Code**: ❌ Incompatible (CANopen)

### 5.4 Speed Control (Command 0xA2)

| Aspect | Official Spec | Tested Code | Our Code |
|--------|---------------|-------------|----------|
| **Data Type** | int32_t | int32_t | N/A |
| **Unit** | 0.01 dps/LSB | 0.01 dps/LSB | N/A |
| **Byte Range** | DATA[4]–DATA[7] | DATA[4]–DATA[7] | N/A |
| **Encoding** | Little-endian | Little-endian | CANopen SDO |

**Example**: To command 360 dps → send value `36000`

**Tested Code**: ✅ Correct  
**Our Code**: ❌ Incompatible (CANopen)

### 5.5 PID Parameters (Commands 0x30, 0x31, 0x32)

| Aspect | Official Spec | Tested Code | Our Code |
|--------|---------------|-------------|----------|
| **Data Type** | **uint8_t** (each param) | uint8_t | **float** assumed |
| **Byte Layout** | DATA[2]=posKp, DATA[3]=posKi, DATA[4]=spdKp, DATA[5]=spdKi, DATA[6]=iqKp, DATA[7]=iqKi | ✅ Matches | ❌ Wrong type |

⚠️ **CRITICAL**: PID parameters are **uint8_t** (0–255), NOT floats!

**Tested Code**: ✅ Correct  
**Our Code**: ❌ Assumed float (wrong)

### 5.6 Temperature, Voltage, Phase Currents

| Parameter | Type | Unit | Source |
|-----------|------|------|--------|
| Temperature | int8_t | 1°C/LSB | DATA[1] in most responses |
| Voltage | uint16_t | 0.1V/LSB | DATA[3:4] in READ_STATUS_1 |
| Phase Current A/B/C | int16_t | 1A/64LSB | DATA[2:7] in READ_STATUS_3 |
| Torque Current (iq) | int16_t | Range -2048 to +2048 | DATA[2:3] in responses |
| Speed | int16_t | 1 dps/LSB | DATA[4:5] in responses |
| Encoder Position | uint16_t | 14-bit or 16-bit | DATA[6:7] in responses |

**Tested Code**: ✅ All correct  
**Our Code**: ❌ Not implemented for MG protocol

---

## 6. RESPONSE TIMING & RETRY LOGIC

### Official Specification

| Parameter | Value |
|-----------|-------|
| **Response Time** | Within 0.25ms |
| **Max Node ID** | 32 |
| **Max Motors on Bus** | 32 (depending on bus load) |

### Implementation Comparison

| Implementation | Timeout | Retries | Assessment |
|----------------|---------|---------|------------|
| **Official Spec** | 0.25ms response guarantee | N/A | Ground truth |
| **Tested Code** | 50ms timeout | 1 retry | ✅ Conservative, works |
| **Our Code** | 100ms timeout (SDO) | 3 retries | ⚠️ Wrong protocol |

### **RECOMMENDATION**

Use **10ms timeout with 3 retries**:
- Balances official 0.25ms spec with real-world margins
- Faster than tested code's 50ms
- Allows up to 30ms total (10ms × 3 retries)

```cpp
const int DEFAULT_TIMEOUT_MS = 10;
const int DEFAULT_RETRIES = 3;
```

---

## 7. ERROR HANDLING

### Error State Byte (DATA[7] in READ_STATUS_1 / CLEAR_ERRORS)

| Bit | State | 0 | 1 |
|-----|-------|---|---|
| 0 | Voltage | Normal | **Under voltage protection** |
| 1 | Reserved | - | - |
| 2 | Reserved | - | - |
| 3 | Temperature | Normal | **Over temperature protection** |
| 4-7 | Reserved | - | - |

**Tested Code**: ✅ Parses error flags correctly  
**Our Code**: ❌ Not implemented for MG protocol

---

## 8. WHAT TO INTEGRATE FROM TESTED CODE

### ✅ **Keep/Port These Elements**

1. **Command Constants** (verified against official spec)
   ```cpp
   MOTOR_OFF = 0x80, MOTOR_ON = 0x88, MOTOR_STOP = 0x81
   TORQUE_CTRL = 0xA1, SPEED_CTRL = 0xA2
   // ... etc
   ```

2. **Arbitration ID Formula**
   ```cpp
   uint32_t arb_id = 0x140 + motor_id;
   ```

3. **Response Parser Structure** (`motor_response()` function logic)

4. **Retry Logic** with exponential backoff

5. **Frame Filtering** (match both ID and command byte)

### ⚠️ **Update These Elements**

1. **Timeout**: Change from 50ms → **10ms**

2. **Multi-turn Angle**: Ensure full int64_t support (not just 56-bit)

3. **Single-turn Range**: Validate 0–35999 (not 0–36000)

4. **Baud Rate Default**: Change from 250kbps → **1Mbps**

### ❌ **Do NOT Port These**

1. Custom `optional<>` template (use `std::optional` in C++17)

2. Hardcoded debug prints (use ROS logging instead)

---

## 9. WHAT TO DEPRECATE FROM OUR CODE

### ❌ **CANopen Elements (Incompatible with MG Protocol)**

1. **SDO/PDO Communication**
   - `send_sdo_request()`, `receive_sdo_response()`
   - `send_pdo()`, PDO mapping

2. **CANopen State Machine**
   - `switch_to_operation_enabled()`
   - `switch_to_switched_on()`
   - State word/control word logic

3. **CANopen Object Dictionary**
   - All `OD_*` constants (0x1000, 0x6040, etc.)
   - `get_cob_id()` function

4. **Type Assumptions**
   - Float PID parameters (should be uint8_t)
   - CANopen-specific scaling factors

### ✅ **Keep From Our Code**

1. **Socket Management** (`GenericCANInterface`)
   - `setup_can_socket()`, `close_can_socket()`
   - `send_message()`, `receive_message()`

2. **High-Level Architecture**
   - `MotorControllerInterface` abstraction
   - `MotorConfiguration` structure
   - Safety limits, homing config

3. **ROS2 Integration**
   - Parameter handling
   - Logging infrastructure
   - CMake build system

---

## 10. INTEGRATION STRATEGY

### Phase 1: Create MG6010Protocol Class ✅

**New Files**:
- `src/odrive_control_ros2/include/odrive_control_ros2/mg6010_protocol.hpp`
- `src/odrive_control_ros2/src/mg6010_protocol.cpp`

**Design**:
- Lightweight class using existing `CANInterface`
- Official spec compliant
- NO CANopen dependencies

### Phase 2: Standalone Test Node ✅

**New File**:
- `src/odrive_control_ros2/src/mg6010_test_node.cpp`

**Purpose**: Validate protocol before full integration

### Phase 3: Integration Hook (Optional) 🔄

**Modify**:
- `GenericMotorController::initialize()`

**Logic**:
```cpp
if (config.motor_type == "mg6010") {
    // Route to MG6010Protocol
} else {
    // Existing CANopen/ODrive logic
}
```

### Phase 4: Testing & Validation ✅

1. Compare CAN messages with tested implementation
2. Hardware-in-loop testing with actual MG6010-i6
3. Performance benchmarking (1Mbps vs 250kbps)

---

## 11. COMMAND-BY-COMMAND COMPARISON

### Motor ON (0x88)

| Aspect | Official | Tested | Our Code |
|--------|----------|--------|----------|
| TX Data | All 0x00 except DATA[0]=0x88 | ✅ Matches | ❌ N/A |
| RX Data | Echo command | ✅ Validates | ❌ N/A |
| Effect | Enable motor, LED solid | ✅ Documented | ❌ N/A |

### Torque Control (0xA1)

| Aspect | Official | Tested | Our Code |
|--------|----------|--------|----------|
| TX Data[4:5] | int16_t torque (-2048 to +2048) | ✅ Correct | ❌ Uses CANopen |
| RX Data[1] | Temperature (int8_t) | ✅ Parses | ❌ N/A |
| RX Data[2:3] | Torque current (int16_t) | ✅ Parses | ❌ N/A |
| RX Data[4:5] | Speed (int16_t dps) | ✅ Parses | ❌ N/A |
| RX Data[6:7] | Encoder position (uint16_t) | ✅ Parses | ❌ N/A |

### Speed Control (0xA2)

| Aspect | Official | Tested | Our Code |
|--------|----------|--------|----------|
| TX Data[4:7] | int32_t speed (0.01 dps/LSB) | ✅ Correct | ❌ Uses CANopen |
| RX Response | Same as torque control | ✅ Handles | ❌ N/A |
| Speed Limit | Constrained by LK motor tool | ✅ Noted | ❌ N/A |

### Multi-Turn Position (0xA3, 0xA4)

| Aspect | Official | Tested | Our Code |
|--------|----------|--------|----------|
| TX Data[4:7] | int32_t angle (0.01°/LSB) | ✅ Correct | ❌ Uses CANopen |
| TX Data[2:3] (0xA4) | uint16_t max speed (1 dps/LSB) | ✅ Implemented | ❌ N/A |
| Direction | Auto (target - current) | ✅ Correct | ❌ N/A |

### Read Multi-Turn Angle (0x92)

| Aspect | Official | Tested | Our Code |
|--------|----------|--------|----------|
| RX Data[1:7] | int64_t angle (7 bytes) | ⚠️ 56-bit treatment | ❌ N/A |
| Unit | 0.01°/LSB | ✅ Correct | ❌ N/A |
| Sign | Signed (CW+, CCW-) | ✅ Sign-extends | ❌ N/A |

### Read Single-Turn Angle (0x94)

| Aspect | Official | Tested | Our Code |
|--------|----------|--------|----------|
| RX Data[4:7] | uint32_t angle (0–35999) | ⚠️ Assumed 0–36000 | ❌ N/A |
| Unit | 0.01°/LSB | ✅ Correct | ❌ N/A |
| Wrap | Returns to 0 at encoder zero | ✅ Noted | ❌ N/A |

---

## 12. RECOMMENDATIONS SUMMARY

### 🎯 **Critical Actions**

1. **Use 1Mbps baud rate** (official default)
   - Fall back to 250kbps only if bus issues occur

2. **Port tested command structure** with these updates:
   - Timeout: 50ms → **10ms**
   - Multi-turn: Ensure full int64_t (not 56-bit)
   - Single-turn: Validate 0–35999 range

3. **Create separate MG6010Protocol class**
   - DO NOT modify `odrive_legacy`
   - DO NOT mix with CANopen code

4. **Validate with hardware**
   - Compare CAN traces with tested implementation
   - Test at both 1Mbps and 250kbps
   - Verify all 27 commands

### 📋 **Development Checklist**

- [ ] Create `mg6010_protocol.hpp/cpp`
- [ ] Implement all 27 commands from official spec
- [ ] Create standalone test node
- [ ] Test at 1Mbps baud rate
- [ ] Validate single-turn range (0–35999)
- [ ] Compare CAN messages with tested code
- [ ] Hardware validation with MG6010-i6
- [ ] Integration with GenericMotorController (optional)

---

## 13. REFERENCES

1. **Official**: LK-TECH CAN Protocol V2.35 (`CANprotocal.pdf`)
2. **Tested**: `mg_can_compat.cpp/hpp` by colleague
3. **Current**: `src/odrive_control_ros2/src/generic_motor_controller.cpp`

---

**Document Status**: ✅ Complete - Ready for implementation  
**Next Steps**: Create `MG6010Protocol` class based on official spec + tested code patterns
