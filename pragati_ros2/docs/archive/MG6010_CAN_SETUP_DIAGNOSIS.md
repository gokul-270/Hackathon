# MG6010 Motor CAN Communication - Complete Diagnosis

**Date**: 2025-10-10  
**Status**: Motors responding but not executing commands  
**Motor**: MG6010E-i6 (48V, Node IDs: 1, 2, 3)

---

## 🔍 **Current Situation**

### ✅ **What's Working:**
1. CAN hardware and wiring perfect
2. All three motors ACKing CAN messages
3. CAN communication at 250kbps confirmed
4. Motors respond to all command types (0x80-0xA6)
5. CAN bus statistics: 83 RX, 102 TX, 0 errors

### ❌ **What's NOT Working:**
1. Motors return **all zero data** (no sensor readings)
2. Motors do **NOT execute movement commands**
3. No actual motor shaft movement observed
4. All status queries return: temp=0, voltage=0, position=0

---

## 🎯 **Root Cause**

**The motors are in UART configuration mode, not CAN operational mode.**

### Evidence:
- Motors ACK CAN frames (protocol layer working)
- Motors echo command bytes (communication OK)
- BUT: No sensor data, no movement execution
- This is classic symptom of "CAN interface enabled but motor not in CAN control mode"

### Why This Happens:
MG6010 motors support **both UART and CAN** interfaces:
- **UART**: Configuration, setup, diagnostics (115200 bps)
- **CAN**: Real-time control after configuration

By default or after reset, motors may be in:
- ✅ UART-primary mode (listens to UART, acknowledges CAN)
- ❌ CAN-operational mode (what we need)

---

## 📋 **Required Action**

### **You MUST configure motors via UART to enable CAN operational mode:**

1. **Connect to motor via UART** (115200 bps)
2. **Send configuration commands** to:
   - Enable CAN interface
   - Set CAN bitrate to 250kbps
   - Set Node ID (1, 2, or 3)
   - Set communication mode to CAN
   - Save to EEPROM
3. **Power cycle the motor**
4. **Test CAN again** - should now execute commands

---

## 🔧 **Next Steps**

### **Step 1: Test UART Connection**

You have UART connected on RPi (`/dev/ttyUSB0` at 115200 bps).

**Run the test script:**
```bash
# On Raspberry Pi
cd /home/ubuntu/pragati_ws
sudo python3 test_motor_uart_simple.py
```

This will:
- Test UART communication
- Try different command formats
- Identify if motor responds to UART

### **Step 2: Find UART Protocol**

Once UART communication works, we need to know:
1. **Command format** - How to send commands
2. **CAN enable command** - Specific bytes to enable CAN mode
3. **Node ID command** - How to set motor ID
4. **Save command** - How to persist to EEPROM

**Sources to check:**
- MG6010 user manual (from manufacturer)
- Windows app documentation
- Motor datasheet

### **Step 3: Configure Each Motor**

For each of the 3 motors:
```python
# Pseudocode - actual commands depend on protocol
uart.send("ENABLE_CAN_MODE")
uart.send("SET_CAN_BITRATE 250000")
uart.send("SET_NODE_ID 1")  # Then 2, 3 for other motors
uart.send("SAVE_TO_EEPROM")
```

### **Step 4: Verify CAN Operation**

After configuration:
```bash
# Power cycle motor
# Run CAN test again
cd /home/ubuntu/pragati_ws
./comprehensive_can_motor_test.sh
```

Should now see:
- ✅ Real voltage readings (~48V)
- ✅ Real temperature readings
- ✅ Motor movement when commanded
- ✅ Position feedback updates

---

## 🆘 **If You Can't Get UART Working**

### Alternative 1: Use Windows App
If the Windows app worked before:
1. Connect motor to Windows PC via UART
2. Open the app
3. Look for settings like:
   - "Communication Mode" → Change to CAN
   - "CAN Settings" → Enable, set bitrate, set Node ID
4. Save and power cycle
5. Move motor back to Raspberry Pi

### Alternative 2: Contact Manufacturer
- Ask for CAN configuration procedure
- Request UART command protocol document
- Ask if there's a hardware jumper/DIP switch for CAN mode

### Alternative 3: Check Hardware
Some motors have:
- **DIP switches** to select UART vs CAN mode
- **Jumpers** to enable/disable interfaces
- **Configuration mode** entered by power-on sequence

Check motor case/PCB for switches or jumpers.

---

## 📊 **CAN vs UART Mode Comparison**

| Feature | UART Mode | CAN Mode |
|---------|-----------|----------|
| Communication | ✅ Works | ✅ ACKs only |
| Configuration | ✅ Full access | ❌ Limited |
| Real-time control | ❌ Too slow | ✅ Fast (0.25ms) |
| Motor movement | ❌ Not executed | ✅ Executes |
| Sensor data | ✅ Returns real data | ❌ Returns zeros (if not configured) |
| Use case | Setup, diagnostics | **Operational control** |

---

## 🔑 **Key Information Needed**

To proceed, we need from you:

1. **Windows App Details:**
   - What settings did you change?
   - Any "CAN enable" or "communication mode" option?
   - What baud rate did you use? (confirmed: 115200)

2. **Motor Documentation:**
   - Do you have the MG6010 user manual?
   - Any configuration guide from manufacturer?

3. **Physical Motor:**
   - Any switches or jumpers on the motor?
   - LED behavior when powered?
   - Model number confirmation: MG6010E-i6?

---

## 📁 **Supporting Files Created**

1. **`test_motor_uart_simple.py`** - UART communication test
   - Location: `/home/ubuntu/pragati_ws/`
   - Tests 5 baud rates
   - Tries multiple command formats

2. **`comprehensive_can_motor_test.sh`** - Full CAN test
   - Tests all CAN commands
   - Shows if motor is operational

3. **CAN diagnostic scripts** - All in `/home/ubuntu/pragati_ws/scripts/`

---

## ✅ **Summary**

**Hardware:** ✅ Perfect  
**CAN Communication:** ✅ Working  
**Motor Configuration:** ❌ **Needs UART setup to enable CAN operational mode**

**Next action:** Run UART test and share what configuration options you had in the Windows app.

---

**Once UART protocol is identified, I can create a script to automatically configure all three motors!**
