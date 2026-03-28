# GM25-BK370 Hall Encoder DC Gear Motor - Analysis & Design

> **Document Created:** December 30, 2025  
> **Motor Model:** CHR-GM25-BK370-ABHL  
> **Manufacturer:** Shenzhen Chihai Motor Co., Ltd  
> **Product Page:** https://www.airsoftmotor.com/micro-dc-reduction-motor/circular-reduction-motor/gm25-bk370-hall-encoder-dc-gear-motor.html

## 1. Executive Summary

The End Effector (EE) motor used in the Pragati cotton picking robot is a **GM25-BK370 Hall Encoder DC Gear Motor**. This motor has a built-in AB dual-phase Hall encoder that is **currently not being utilized**. Implementing encoder feedback would provide:

- **Motor running confirmation** - Know if motor is actually spinning
- **Stall detection** - Prevent motor burnout from jams
- **Cotton capture verification** - Actual feedback vs assumed success
- **Adaptive timing** - Faster, more efficient pick cycles
- **Better diagnostics** - Real data for troubleshooting

---

## 2. Motor Specifications

### 2.1 Physical Specifications

| Parameter | Value |
|-----------|-------|
| Motor Diameter | Φ25mm |
| Shaft Length | 12mm (D-shaft 8mm) |
| Weight | ~97g |
| Connector | PH2.0 (6-pin) |

### 2.2 Electrical Specifications

| Parameter | 6V Operation | 12V Operation |
|-----------|--------------|---------------|
| Max Power | 8.0W | 26W |
| Input Motor Speed | 10,000 RPM | 20,000 RPM |
| No-load Current | ≤400mA | ≤600mA |
| Rated Current | ≤1.4A | ≤2.7A |
| Stall Current | ≤8.0A | ≤16.0A |

> ⚠️ **Note:** Due to high power and current requirements, a power supply of 10A or more is recommended.

### 2.3 Gear Ratio Options & Performance

**At 6V:**

| Ratio | No-load RPM | Rated RPM | Rated Torque | Hall Pulses/Rev |
|-------|-------------|-----------|--------------|-----------------|
| 1:4.4 | 2000 | 1500 | 0.03 N.m | 48.4 |
| 1:9.3 | 880 | 660 | 0.06 N.m | 102.3 |
| 1:20 | 440 | 330 | 0.12 N.m | 220 |
| 1:34 | 259 | 194 | 0.20 N.m | 374 |
| 1:45 | 195 | 147 | 0.27 N.m | 495 |
| 1:57 | 154 | 116 | 0.34 N.m | 627 |
| 1:75 | 117 | 88 | 0.44 N.m | 825 |
| 1:100 | 88 | 66 | 0.59 N.m | 1100 |
| 1:125 | 70 | 53 | ≤0.8 N.m | 1361.8 |
| 1:217 | 40 | 30 | ≤0.8 N.m | 2387 |
| 1:478 | 18 | 14 | ≤0.8 N.m | 5258 |

**At 12V:**

| Ratio | No-load RPM | Rated RPM | Rated Torque | Hall Pulses/Rev |
|-------|-------------|-----------|--------------|-----------------|
| 1:4.4 | 4300 | 3300 | 0.05 N.m | 48.4 |
| 1:9.3 | 1892 | 1452 | 0.10 N.m | 102.3 |
| 1:20 | 946 | 726 | 0.21 N.m | 220 |
| 1:34 | 556 | 427 | 0.34 N.m | 374 |
| 1:45 | 420 | 323 | 0.44 N.m | 495 |
| 1:57 | 332 | 255 | 0.59 N.m | 627 |
| 1:75 | 252 | 194 | 0.69 N.m | 825 |
| 1:100 | 189 | 145 | ≤0.8 N.m | 1100 |
| 1:125 | 151 | 116 | ≤0.8 N.m | 1361.8 |
| 1:217 | 87 | 67 | ≤0.8 N.m | 2387 |
| 1:478 | 40 | 30 | ≤0.8 N.m | 5258 |

> **Max Torque:** Cannot exceed 8.0 kg.cm (0.8 N.m) / 9.0 kg.cm for stall torque

### 2.4 Encoder Specifications

| Parameter | Value |
|-----------|-------|
| Encoder Type | AB Dual-Phase Hall Encoder |
| Base Resolution | 11 lines (pulses per motor revolution) |
| Signal Voltage | 3.3V or 5.0V (configurable) |
| Output Signals | Channel A, Channel B (90° phase offset) |

---

## 3. Current Implementation

### 3.1 Motor Wiring Overview

The GM25-BK370 motor has a **6-pin PH2.0 connector** with the following wires:

| Pin | Wire Color (typical) | Function | Current Status |
|-----|---------------------|----------|----------------|
| 1 | Red | Motor + (Power) | ✅ Connected to Motor Driver |
| 2 | Black | Motor - (Ground) | ✅ Connected to Motor Driver |
| 3 | Yellow | Encoder VCC | ❌ **NOT Connected** |
| 4 | Green | Encoder GND | ❌ **NOT Connected** |
| 5 | Blue | Encoder Channel A | ❌ **NOT Connected** |
| 6 | White | Encoder Channel B | ❌ **NOT Connected** |

> ⚠️ **Wire colors may vary by batch.** Always verify with multimeter before connecting.

### 3.2 Hardware Architecture - Robotics Board V1.2

The Pragati robot uses a custom **Robotics Board V1.2** that interfaces between the Raspberry Pi 4B and all peripherals. This board:

- Powers the RPi via isolated 5V supply
- Contains the **DRV8235RTER** motor driver for the DC motor
- Provides isolated GPIO inputs for limit switches and buttons
- Routes all GPIO signals through the 40-pin header

**Reference Schematics:**
- `Robotics_Board_V1.2-1.pdf` - Full board schematic
- `Connector mapping-1.pdf` - Connector layout diagram

### 3.3 Motor Driver Circuit (DRV8235RTER)

The Robotics Board V1.2 uses Texas Instruments **DRV8235RTER** H-bridge motor driver:

| DRV8235 Pin | Connected To | Function |
|-------------|--------------|----------|
| VM | M_POWER_IN | Motor power supply |
| OUT1 | Motor + (via J11 connector) | Motor output 1 |
| OUT2 | Motor - (via J11 connector) | Motor output 2 |
| EN/IN1 | DVR_IN1 (GPIO 12) | Enable/Input 1 |
| PH/IN2 | DVR_IN2 (GPIO 19) | Phase/Input 2 |
| VREF | Reference voltage | Speed control reference |
| NFAULT | Fault detection | Motor fault indicator |

**J11 Connector (DC Motor Output):**
```
J11 - XT30 Connector
├── Pin P: DCMOTOR_OUT1 (Motor +)
└── Pin N: DCMOTOR_OUT2 (Motor -)
```

### 3.4 Current Wiring Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    CURRENT WIRING - via Robotics Board V1.2                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   GM25-BK370 Motor           Robotics Board V1.2              RPi 4B            │
│   ================          ===================              ======            │
│                                                                                 │
│   Motor + (Red) ─────────► J11-P (DCMOTOR_OUT1)                                │
│   Motor - (Black) ───────► J11-N (DCMOTOR_OUT2)                                │
│                                      │                                          │
│                                      ▼                                          │
│                              DRV8235 Motor Driver                               │
│                              (on Robotics Board)                                │
│                                      │                                          │
│                          ┌───────────┴───────────┐                              │
│                          │                       │                              │
│                     DVR_IN1 (EN/IN1)       DVR_IN2 (PH/IN2)                     │
│                          │                       │                              │
│                          ▼                       ▼                              │
│                    Pin 32 (GPIO 12)        Pin 35 (GPIO 19)                     │
│                                                                                 │
│   Power Supply:                                                                 │
│   ─────────────                                                                 │
│   V_IN (24V) ───────────► F1 (Fuse) ─────► Robotics Board Power Rails          │
│   M_POWER ──────────────────────────────► DRV8235 VM (Motor Power)             │
│                                                                                 │
│   Encoder (4 wires - NOT CONNECTED):                                           │
│   ──────────────────────────────────                                           │
│   Encoder VCC (Yellow) ────── NOT CONNECTED                                    │
│   Encoder GND (Green) ─────── NOT CONNECTED                                    │
│   Encoder A (Blue) ────────── NOT CONNECTED                                    │
│   Encoder B (White) ───────── NOT CONNECTED                                    │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 3.5 RPi GPIO Pin Allocation (Robotics Board V1.2)

**CRITICAL: The Robotics Board V1.2 allocates MOST GPIO pins!**

| Physical Pin | GPIO BCM | Robotics Board Function | Available? |
|--------------|----------|------------------------|------------|
| 1 | 3.3V | Power | For encoder VCC ✅ |
| 2, 4 | 5V | +5V_ISO_RPI | ❌ Used |
| 3 | GPIO 2 | RPI_SDA (I2C) | ❌ Used |
| 5 | GPIO 3 | RPI_SCL (I2C) | ❌ Used |
| 6, 9, 14, 20, 25, 30, 34 | GND | Ground | For encoder GND ✅ |
| 7 | GPIO 4 | GREEN_LED | ❌ Used |
| 8 | GPIO 14 | TRANSPORT_SERVO | ❌ Used |
| 10 | GPIO 15 | RED_LED | ❌ Used |
| 11 | GPIO 17 | CAMERA_LED | ❌ Used |
| 12 | GPIO 18 | COMPRESSOR | ❌ Used |
| 13 | GPIO 27 | (Check schematic) | ⚠️ Verify |
| 15 | GPIO 22 | (Check schematic) | ⚠️ Verify |
| 16 | GPIO 23 | (Check schematic) | ⚠️ Verify |
| 18 | GPIO 24 | VACUUM_MOTOR | ❌ Used |
| 19 | GPIO 10 | RPI_MOSI (SPI) | ❌ Used |
| 21 | GPIO 9 | RPI_MISO (SPI) | ❌ Used |
| 22 | GPIO 25 | CAN_INT | ❌ Used |
| 23 | GPIO 11 | RPI_SCK (SPI) | ❌ Used |
| 24 | GPIO 8 | CAN_CS | ❌ Used |
| 26 | GPIO 7 | ADC_CS | ❌ Used |
| 27 | ID_SD | Internal EEPROM | ❌ Reserved |
| 28 | ID_SC | Internal EEPROM | ❌ Reserved |
| 29 | GPIO 5 | ISO_START_BUTTN | ⚠️ Input |
| 31 | GPIO 6 | ISO_RESET_BUTTN | ⚠️ Input |
| 32 | GPIO 12 | DVR_IN1 / EE_DIRECTION | ❌ Used (EE Motor) |
| 33 | GPIO 13 | (Check schematic) | ⚠️ Verify |
| 35 | GPIO 19 | DVR_IN2 / EE_ENABLE | ❌ Used (EE Motor) |
| 36 | GPIO 16 | LIMIT2_INP_ISO | ❌ Used |
| 37 | GPIO 26 | (Check schematic) | ⚠️ Verify |
| 38 | GPIO 20 | LIMIT3_INP_ISO | ❌ Used |
| 39 | GPIO 21 | LIMIT1_INP_ISO | ❌ Used |
| 40 | GPIO 20 | LIMIT4_INP_ISO | ❌ Used |

**⚠️ IMPORTANT:** Encoder requires 2 free GPIO input pins. Need to verify actual availability on board.

### 3.6 RPi GPIO Control Signals

| Signal | RPi GPIO (BCM) | Physical Pin | Function |
|--------|----------------|--------------|----------|
| Enable | GPIO 19 | Pin 35 | END_EFFECTOR_ON_PIN (DVR_IN2) |
| Direction | GPIO 12 | Pin 32 | END_EFFECTOR_DIRECTION_PIN (DVR_IN1) |

### 3.7 Software Control (Current)

**File:** `src/motor_control_ros2/src/gpio_control_functions.cpp`

```cpp
void GPIOControlFunctions::end_effector_control(bool end_effector_condition)
{
  if (end_effector_condition)
  {
    // Turn ON with current direction
    if (end_effector_direction_ == CLOCKWISE)
    {
      gpio_interface_->write_gpio(END_EFFECTOR_ON_PIN, 1);
      gpio_interface_->write_gpio(END_EFFECTOR_DIRECTION_PIN, 0);
    }
    else
    {
      gpio_interface_->write_gpio(END_EFFECTOR_ON_PIN, 0);
      gpio_interface_->write_gpio(END_EFFECTOR_DIRECTION_PIN, 1);
    }
  }
  else
  {
    // Turn OFF
    gpio_interface_->write_gpio(END_EFFECTOR_ON_PIN, 0);
    gpio_interface_->write_gpio(END_EFFECTOR_DIRECTION_PIN, 0);
  }
}
```

### 3.8 Current Limitations

1. **Open-Loop Control** - No feedback on actual motor state
2. **Time-Based Operation** - Motor runs for fixed duration (0.8s typical)
3. **No Stall Detection** - Motor could burn out if jammed
4. **Assumed Success** - Pick success is inferred, not verified
5. **No Diagnostics** - Cannot detect motor degradation or issues

---

## 4. Encoder Capabilities

### 4.1 What the Encoder Provides

The AB dual-phase Hall encoder outputs two square wave signals that are 90° out of phase:

```
Channel A: ─┐   ┌───┐   ┌───┐   ┌───┐   ┌───
            └───┘   └───┘   └───┘   └───┘   

Channel B: ───┐   ┌───┐   ┌───┐   ┌───┐   ┌─
              └───┘   └───┘   └───┘   └───┘
              
          (90° phase difference enables direction detection)
```

### 4.2 Derivable Information

| Measurement | Method | Use Case |
|-------------|--------|----------|
| **Motor Running** | Pulses present when commanded ON | Verify motor is actually spinning |
| **Speed (RPM)** | Count pulses per second, convert | Monitor performance |
| **Direction** | A leads B = CW, B leads A = CCW | Verify direction command worked |
| **Position** | Cumulative pulse count | Track total rotation |
| **Stall Detection** | Motor ON but no pulses | Detect jams, protect motor |
| **Load Estimation** | Speed reduction under load | Detect cotton engagement |

### 4.3 Resolution Examples

| Gear Ratio | Pulses/Rev | Angular Resolution |
|------------|------------|-------------------|
| 1:20 | 220 | 1.64° per pulse |
| 1:34 | 374 | 0.96° per pulse |
| 1:45 | 495 | 0.73° per pulse |
| 1:75 | 825 | 0.44° per pulse |
| 1:100 | 1100 | 0.33° per pulse |

---

## 5. Proposed Implementation

### 5.1 Can RPi Handle Encoder Input Directly? - DEEP DIVE ANALYSIS

**Short Answer: YES, with some caveats.**

This is a critical question that requires thorough analysis across multiple dimensions.

---

#### 5.1.1 Voltage Compatibility ⚠️ CRITICAL

| Parameter | GM25-BK370 Encoder | RPi 4B GPIO | Analysis |
|-----------|-------------------|-------------|----------|
| **Signal Voltage** | 3.3V OR 5V (selectable) | 3.3V tolerant ONLY | ⚠️ **MUST verify encoder voltage** |
| **Max Input Voltage** | Outputs at VCC level | Absolute max 3.6V | ⚡ **5V WILL DAMAGE RPi** |
| **Logic High Threshold** | ~2.0V (for 3.3V) | >2.0V detected as HIGH | ✅ Compatible |
| **Logic Low Threshold** | ~0.8V | <0.8V detected as LOW | ✅ Compatible |

**⚠️ CRITICAL WARNING:**
```
The GM25-BK370 encoder operates at the voltage supplied to its VCC pin.
- If you supply 5V to Encoder VCC → Output signals will be 5V → WILL DAMAGE RPi GPIO!
- If you supply 3.3V to Encoder VCC → Output signals will be 3.3V → SAFE for RPi!

ALWAYS connect Encoder VCC to RPi 3.3V pin (Pin 1 or 17), NOT to 5V!
```

**Verification Steps Before Connecting:**
1. Disconnect motor from everything
2. Connect Encoder VCC to 3.3V, Encoder GND to GND
3. Use multimeter to measure voltage on Encoder A/B pins while rotating shaft by hand
4. Should see pulses between 0V and ~3.3V
5. If you see ~5V, DO NOT CONNECT to GPIO - check wiring

---

#### 5.1.2 Pulse Frequency Analysis ✅ SAFE

**Maximum Encoder Pulse Frequency Calculation:**

```
Motor Input Speed (no load @ 6V) = 10,000 RPM (internal motor, before gearbox)
Encoder PPR (base) = 11 pulses per motor revolution
Max pulse frequency = 10,000 RPM × 11 PPR / 60 seconds = 1,833 Hz ≈ 1.8 kHz
```

**Output Shaft (after gearbox) - What we actually measure:**

| Gear Ratio | Max Output RPM (6V) | Pulses/Rev | Max Frequency | Period |
|------------|---------------------|------------|---------------|--------|
| 1:20 | 440 RPM | 220 | ~1.6 kHz | 625 µs |
| 1:34 | 259 RPM | 374 | ~1.6 kHz | 625 µs |
| 1:45 | 195 RPM | 495 | ~1.6 kHz | 625 µs |
| 1:75 | 117 RPM | 825 | ~1.6 kHz | 625 µs |
| 1:100 | 88 RPM | 1100 | ~1.6 kHz | 625 µs |

> **Key Insight:** Regardless of gear ratio, the encoder frequency is similar because higher gear ratios have more pulses but slower shaft speed. The motor input speed determines the max frequency.

**pigpio Capability:**
- Sampling rate: 1 µs (1 MHz)
- Practical callback rate: Up to ~25 kHz per GPIO
- Our requirement: ~1.8 kHz
- **Margin: ~14x headroom** ✅

---

#### 5.1.3 Real-Time Constraints - Linux is NOT Real-Time

**The Concern:**
Linux is not a real-time operating system. The kernel can preempt user processes at any time for:
- Disk I/O
- Network interrupts
- Other processes
- Garbage collection
- Memory management

**Could we miss pulses?**

| Factor | Risk | Mitigation |
|--------|------|------------|
| **Process scheduling** | Medium | pigpio daemon runs at high priority |
| **Kernel preemption** | Low | DMA-based sampling, not CPU interrupts |
| **Garbage collection** | N/A | C/C++ code, no GC |
| **Heavy CPU load** | Low | Sampling is DMA, independent of CPU |

**How pigpio Actually Works:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          pigpio Architecture                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   GPIO Pins ──────►  DMA Engine  ──────►  Memory Buffer                │
│                     (hardware)           (ring buffer)                  │
│                                               │                         │
│                                               ▼                         │
│                                        pigpio Daemon                    │
│                                     (samples buffer at                  │
│                                      configurable rate)                 │
│                                               │                         │
│                                               ▼                         │
│                                       User Callbacks                    │
│                                                                         │
│   Key: The DMA engine samples GPIO state into memory INDEPENDENTLY      │
│   of the CPU. Even if the CPU is busy, samples are not lost.           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Practical Test Results (from pigpio documentation):**
- Tested up to 100 kHz input frequency without missed pulses
- Our 1.8 kHz is well within safe range

**Recommendation:** For our use case (motor running detection, stall detection, RPM), missing an occasional pulse is acceptable. We're not doing precision positioning.

---

#### 5.1.4 Current Draw - Will the 3.3V Rail Handle It?

| Component | Current Draw | Source |
|-----------|-------------|--------|
| Hall sensor (typical) | 5-15 mA per sensor | Datasheet estimate |
| AB encoder (2 sensors) | 10-30 mA total | Conservative estimate |
| RPi 3.3V rail capacity | 50 mA (GPIO total) | RPi specs |
| RPi 3.3V pin capacity | Up to 800 mA | Via regulator |

**Analysis:**
- The encoder draws from the 3.3V power pin, NOT from GPIO pins
- GPIO pins are inputs only (no current sourcing needed)
- 3.3V power pins can supply several hundred mA
- Encoder needs ~10-30 mA
- **Conclusion: ✅ No problem**

---

#### 5.1.5 Signal Integrity - Noise and Long Wires

**Potential Issues:**

| Issue | Cause | Symptom | Solution |
|-------|-------|---------|----------|
| **Noise pickup** | Long wires acting as antenna | False pulses, erratic counts | Shielded cable, twisted pairs |
| **Ringing** | Fast edges on long traces | Multiple triggers per pulse | Software debounce, 0.1µF cap |
| **Ground loops** | Different ground potentials | Noise, interference | Single-point grounding |
| **EMI from motor** | Motor brushes, PWM | Sporadic false pulses | Keep encoder wires away from motor wires |

**Recommended Wiring Practices:**
1. Keep encoder wires short (< 30 cm ideal)
2. Twist encoder A and GND wires together
3. Twist encoder B and GND wires together  
4. Route encoder wires away from motor power wires
5. Consider 0.1µF ceramic capacitor on each encoder input to GND

**Software Debouncing (if needed):**
```cpp
// Ignore pulses closer than 100µs (10kHz max)
static uint32_t last_tick = 0;
void encoder_callback(int gpio, int level, uint32_t tick) {
    if (tick - last_tick < 100) return;  // Debounce
    last_tick = tick;
    pulse_count++;
}
```

---

#### 5.1.6 When You WOULD Need Additional Hardware

| Scenario | Our Situation | Hardware Needed |
|----------|---------------|-----------------|
| Encoder outputs 5V | ❌ Use 3.3V supply | Logic level shifter |
| Frequency >25 kHz | ❌ We have ~1.8 kHz | Dedicated counter IC |
| Precision positioning | ❌ We just need detection | Hardware quadrature decoder |
| Long cable runs (>1m) | ❌ Short run inside robot | Line driver/receiver (RS-485) |
| Multiple encoders (>4) | ❌ Just one encoder | Multiplexer or MCU |
| Hard real-time guarantees | ❌ Soft real-time OK | RTOS or dedicated MCU |
| **No free GPIO pins** | ⚠️ **VERIFY BOARD** | External GPIO expander (MCP23017) |

---

#### 5.1.7 Final Verdict - REQUIRES HARDWARE VERIFICATION

| Requirement | Met? | Notes |
|-------------|------|-------|
| Voltage compatibility | ✅ | **MUST use 3.3V supply** |
| Frequency capability | ✅ | 14x headroom |
| Real-time performance | ✅ | DMA-based, not CPU dependent |
| Current capacity | ✅ | Well within limits |
| Signal integrity | ✅* | *May need capacitors if noisy |
| **Free GPIO pins** | ⚠️ | **MUST verify on actual board** |

**⚠️ CRITICAL CONSTRAINT: GPIO Pin Availability**

The Robotics Board V1.2 allocates most GPIO pins. According to the schematic analysis:
- GPIO 5 (Pin 29): ISO_START_BUTTN - May be usable if button not needed
- GPIO 6 (Pin 31): ISO_RESET_BUTTN - May be usable if button not needed
- GPIO 13 (Pin 33): Need to verify
- GPIO 22 (Pin 15): Need to verify  
- GPIO 23 (Pin 16): Need to verify
- GPIO 26 (Pin 37): Need to verify
- GPIO 27 (Pin 13): Need to verify

**ACTION REQUIRED:** Before implementing encoder feedback:
1. **Physically inspect** the Robotics Board V1.2
2. **Verify** which GPIO pins are actually routed to connectors
3. **Test** if unused pins can be accessed
4. If no free GPIO pins, consider:
   - Using one of the ADC channels on the MCP3008 (already on board)
   - Adding external I2C GPIO expander
   - Board modification (add test points)

---

### 5.2 Hardware Wiring

**⚠️ IMPORTANT:** GPIO pin selection depends on Robotics Board V1.2 availability!

The GPIO pins previously suggested (GPIO 5, GPIO 6) may conflict with ISO_START_BUTTN and ISO_RESET_BUTTN signals on the Robotics Board.

**Potential Alternative GPIO Pins (require verification):**

| Encoder Wire | Option 1 | Option 2 | Option 3 |
|--------------|----------|----------|----------|
| Encoder A | GPIO 13 (Pin 33) | GPIO 22 (Pin 15) | GPIO 27 (Pin 13) |
| Encoder B | GPIO 26 (Pin 37) | GPIO 23 (Pin 16) | (pair with above) |

**Recommended Approach:**

1. **Best case** - Use GPIO 5 & 6 if ISO_START/RESET buttons are NOT used in current application
2. **Alternative** - Find other unused GPIO pairs on the Robotics Board
3. **Fallback** - Use I2C GPIO expander (MCP23017) if no GPIO available

**New Connections Required (Encoder Only - AFTER GPIO VERIFICATION):**

| Encoder Wire | Connect To | RPi Pin | Notes |
|--------------|------------|---------|-------|
| Encoder VCC (Yellow) | 3.3V | Pin 1 or 17 | Powers the Hall sensors |
| Encoder GND (Green) | GND | Pin 6, 9, 14, etc. | Common ground via Robotics Board |
| Encoder A (Blue) | TBD GPIO | TBD Pin | **Verify availability** |
| Encoder B (White) | TBD GPIO | TBD Pin | **Verify availability** |

**Power/Ground Availability via Robotics Board:**
- 3.3V available via Pin 1 or Pin 17 (verify accessible on board)
- GND available via multiple pins (6, 9, 14, 20, 25, 30, 34)

**Complete Wiring Diagram (CONCEPTUAL - Requires Pin Verification):**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│             PROPOSED WIRING (WITH ENCODER) - via Robotics Board V1.2            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   GM25-BK370 Motor           Robotics Board V1.2              RPi 4B            │
│   ================          ===================              ======            │
│                                                                                 │
│   Motor + (Red) ─────────► J11-P (DCMOTOR_OUT1)                                │
│   Motor - (Black) ───────► J11-N (DCMOTOR_OUT2)                                │
│                                      │                                          │
│                                      ▼                                          │
│                              DRV8235 Motor Driver                               │
│                              (on Robotics Board)                                │
│                                      │                                          │
│                          ┌───────────┴───────────┐                              │
│                     DVR_IN1 (EN/IN1)       DVR_IN2 (PH/IN2)                     │
│                          │                       │                              │
│                    Pin 32 (GPIO 12)        Pin 35 (GPIO 19)                     │
│                                                                                 │
│   NEW ENCODER CONNECTIONS (via test points or available connector):            │
│   ─────────────────────────────────────────────────────────────────            │
│   Encoder VCC (Yellow) ──────────────────────────► 3.3V (Pin 1)                │
│   Encoder GND (Green) ───────────────────────────► GND (Pin 6)                 │
│   Encoder A (Blue) ──────────────────────────────► TBD GPIO (verify)           │
│   Encoder B (White) ─────────────────────────────► TBD GPIO (verify)           │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

> ⚠️ **Important:** Encoder GND MUST connect to the same ground reference as the motor driver (common ground on Robotics Board).

### 5.3 Software Architecture

**Current Architecture (Open Loop):**

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   MotionController                                              │
│        │                                                        │
│        ▼                                                        │
│   GPIOControlFunctions                                          │
│        │                                                        │
│        ▼                                                        │
│   end_effector_control(ON/OFF)  ─────►  GPIO 19/12              │
│                                                                 │
│   [OPEN LOOP - NO FEEDBACK]                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Proposed Architecture (Closed Loop):**

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   MotionController                                              │
│        │                                                        │
│        ▼                                                        │
│   EEMotorController (new class)                                 │
│        │                                                        │
│        ├──────► GPIO 19/12 (Motor Control - Output)             │
│        │                                                        │
│        └──────► GPIO 5/6 (Encoder Input)                        │
│                      │                                          │
│                      ▼                                          │
│              EncoderReader (interrupt-driven)                   │
│                      │                                          │
│                      ▼                                          │
│              Feedback: RPM, Position, Stall, Load               │
│                                                                 │
│   [CLOSED LOOP - WITH FEEDBACK]                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.4 New Class Design

```cpp
// Proposed: src/motor_control_ros2/include/motor_control_ros2/ee_motor_controller.hpp

class EEMotorController
{
public:
    // Initialization
    bool initialize(int enable_pin, int direction_pin, int encoder_a_pin, int encoder_b_pin);
    
    // Motor Control
    void setDirection(bool clockwise);
    void start();
    void stop();
    
    // Encoder Feedback
    int getPulseCount() const;
    float getRPM() const;
    bool isRunning() const;
    bool isStalled() const;
    
    // Advanced Control
    bool runUntilPulses(int target_pulses, int timeout_ms);
    bool runUntilLoadDetected(int timeout_ms);
    
    // Diagnostics
    struct MotorStats {
        int total_pulses;
        float avg_rpm;
        int stall_count;
        int run_cycles;
    };
    MotorStats getStats() const;
    
private:
    // Interrupt handlers
    static void encoderAInterrupt(int gpio, int level, uint32_t tick);
    static void encoderBInterrupt(int gpio, int level, uint32_t tick);
    
    // State
    std::atomic<int> pulse_count_;
    std::atomic<bool> running_;
    std::atomic<bool> stalled_;
    int direction_;
    
    // Timing
    std::chrono::steady_clock::time_point last_pulse_time_;
    static constexpr int STALL_TIMEOUT_MS = 200;
};
```

---

## 6. Use Cases for Cotton Picking

### 6.1 Cotton Capture Confirmation

**Before (Current - Open Loop):**
```
1. Command: Run EE motor for 0.8 seconds
2. Wait 0.8 seconds
3. ASSUME cotton is captured
4. No verification
```

**After (With Encoder):**
```
1. Command: Run EE motor
2. Monitor encoder pulses
3. IF speed drops >30%: Cotton engaged (load detected)
4. IF speed stays constant: No cotton captured (miss)
5. IF pulses stop: Stall/jam condition
6. VERIFY actual capture success
```

### 6.2 Stall Protection

**Current Problem:**
- Motor runs blindly for fixed duration
- If jammed, motor continues drawing current
- Could cause motor burnout or driver damage

**With Encoder:**
```cpp
void runWithStallProtection(int duration_ms)
{
    start();
    auto start_time = now();
    
    while (elapsed(start_time) < duration_ms)
    {
        if (isStalled())  // No pulses for 200ms while motor ON
        {
            stop();
            log_error("EE motor stalled - jam detected");
            return;
        }
        sleep(10ms);
    }
    stop();
}
```

### 6.3 Adaptive Timing

**Current:** Fixed 0.8s runtime regardless of conditions

**With Encoder:**
```cpp
bool captureWithAdaptiveTiming()
{
    start();
    auto start_time = now();
    float initial_rpm = getRPM();
    
    while (elapsed(start_time) < MAX_CAPTURE_TIME)
    {
        float current_rpm = getRPM();
        
        // Load detection: RPM dropped significantly
        if (current_rpm < initial_rpm * 0.7)
        {
            // Cotton captured! Stop early.
            stop();
            return true;  // Success - verified!
        }
        
        if (isStalled())
        {
            stop();
            return false;  // Jam - fail
        }
        
        sleep(10ms);
    }
    
    stop();
    return false;  // Timeout - no load detected
}
```

### 6.4 Pick Success Verification

```cpp
struct PickResult {
    bool commanded;           // Motor was commanded ON
    bool motor_ran;           // Encoder confirmed rotation
    bool load_detected;       // Speed reduction = cotton engaged
    bool stall_occurred;      // Jam detected
    int actual_runtime_ms;    // How long motor actually ran
    int pulse_count;          // Total encoder pulses
    float avg_rpm;            // Average speed during capture
};

PickResult verifyPick()
{
    PickResult result;
    result.commanded = true;
    
    start();
    auto start_time = now();
    
    // Wait for motor to spin up
    sleep(50ms);
    result.motor_ran = (getPulseCount() > 0);
    
    if (!result.motor_ran) {
        stop();
        result.stall_occurred = true;
        return result;  // Motor failed to start
    }
    
    float initial_rpm = getRPM();
    
    while (elapsed(start_time) < MAX_CAPTURE_TIME)
    {
        if (getRPM() < initial_rpm * 0.7)
        {
            result.load_detected = true;
            break;
        }
        
        if (isStalled())
        {
            result.stall_occurred = true;
            break;
        }
        
        sleep(10ms);
    }
    
    stop();
    result.actual_runtime_ms = elapsed(start_time);
    result.pulse_count = getPulseCount();
    result.avg_rpm = result.pulse_count / (result.actual_runtime_ms / 60000.0) / PULSES_PER_REV;
    
    return result;
}
```

---

## 7. Enhanced Telemetry

### 7.1 Per-Pick Data

```yaml
pick_attempt:
  id: 47
  timestamp: "2025-12-30T17:15:23.456Z"
  
  # Current data (existing)
  cotton_position:
    x: 0.234
    y: -0.067
    z: 0.148
  joint_positions:
    joint3: -0.147
    joint4: -0.067
    joint5: 0.236
  
  # NEW: Encoder feedback data
  ee_motor:
    commanded: true
    motor_ran: true
    commanded_runtime_ms: 800
    actual_runtime_ms: 623        # Stopped early - load detected
    pulse_count: 412
    avg_rpm: 45.2
    initial_rpm: 62.1
    final_rpm: 38.4               # Slowed down = cotton engaged
    rpm_drop_percent: 38.2
    load_detected: true
    stall_detected: false
    
  # Enhanced verification
  cotton_capture_verified: true   # Based on actual encoder feedback
  verification_method: "load_detection"
```

### 7.2 Enhanced Session Statistics

```yaml
session_statistics:
  # Current stats
  session_start: "2025-12-30T15:00:00Z"
  total_cycles: 47
  
  # Existing pick stats
  picks:
    attempted: 47
    successful: 42
    success_rate: 89.4%
  
  # NEW: EE motor statistics
  ee_motor_stats:
    total_activations: 47
    total_runtime_ms: 31240
    total_pulses: 19842
    total_rotations: 18.04        # pulses / pulses_per_rev
    avg_rpm: 48.3
    avg_capture_time_ms: 623
    
    # Failure analysis
    stall_events: 2
    stall_rate: 4.3%
    no_rotation_events: 1         # Motor commanded but didn't spin
    
    # Load detection stats
    load_detected_count: 41
    no_load_count: 4              # Motor ran but no cotton captured
    
    # Verification breakdown
    verified_captures: 41         # Load detected = confirmed capture
    assumed_captures: 1           # Ran full duration, no clear load
    verified_misses: 3            # No load = confirmed miss
    
  # Motor health indicators
  motor_health:
    avg_startup_time_ms: 45
    rpm_consistency: 94.2%        # How consistent is the speed
    degradation_trend: "stable"   # Or "declining"
```

---

## 8. Implementation Phases

### Phase 1: Basic Feedback (1-2 days)

**Objective:** Confirm motor is actually running

**Tasks:**
1. Wire encoder to RPi (4 new connections)
2. Add basic pulse counting with pigpio interrupts
3. Add `isRunning()` check to EE activation
4. Log encoder status in pick telemetry

**Deliverables:**
- Know if motor actually spins when commanded
- Detect complete motor failure

### Phase 2: Stall Detection (1 day)

**Objective:** Protect motor from jam damage

**Tasks:**
1. Implement stall timeout (no pulses for 200ms)
2. Add auto-stop on stall detection
3. Log stall events with context
4. Add recovery/retry logic

**Deliverables:**
- Motor protection from jams
- Stall event logging

### Phase 3: Speed Monitoring (2 days)

**Objective:** Track motor performance

**Tasks:**
1. Calculate RPM from pulse timing
2. Add speed to telemetry output
3. Track speed trends over session
4. Alert on abnormal speeds

**Deliverables:**
- RPM data in logs
- Performance trending

### Phase 4: Load Detection (3 days)

**Objective:** Verify cotton capture

**Tasks:**
1. Establish baseline RPM at startup
2. Detect significant speed drop (load)
3. Implement adaptive stopping (stop when captured)
4. Update pick success based on actual verification

**Deliverables:**
- Verified pick success (not assumed)
- Faster pick cycles (stop when done)

### Phase 5: Full Closed-Loop Control (1 week)

**Objective:** Optimal EE operation

**Tasks:**
1. Position-based control (rotate N degrees)
2. Torque estimation from speed/current
3. Multiple capture strategies (time, position, load)
4. Self-calibration routines

**Deliverables:**
- Fully instrumented EE motor
- Adaptive picking algorithms

---

## 9. Bill of Materials

### Required for Encoder Integration

| Item | Quantity | Notes |
|------|----------|-------|
| Jumper wires (F-F) | 4 | For encoder connections |
| Heat shrink | As needed | Wire protection |
| Multimeter | 1 | For testing/verification |

### Optional Enhancements

| Item | Quantity | Notes |
|------|----------|-------|
| Current sensor (ACS712) | 1 | For current monitoring |
| Voltage divider | 1 | If encoder outputs 5V |
| Logic level shifter | 1 | If voltage conversion needed |

---

## 10. Testing Procedures

### 10.1 Hardware Verification

```bash
# Test encoder connections
# Expected: See pulse counts when motor spins

# 1. Manual test - rotate motor shaft by hand
python3 -c "
import pigpio
pi = pigpio.pi()

pulse_count = 0
def callback(gpio, level, tick):
    global pulse_count
    pulse_count += 1
    print(f'Pulse {pulse_count} on GPIO {gpio}')

pi.set_mode(5, pigpio.INPUT)
pi.set_mode(6, pigpio.INPUT)
cb1 = pi.callback(5, pigpio.RISING_EDGE, callback)
cb2 = pi.callback(6, pigpio.RISING_EDGE, callback)

input('Rotate motor shaft manually, then press Enter...')
print(f'Total pulses: {pulse_count}')

cb1.cancel()
cb2.cancel()
pi.stop()
"
```

### 10.2 RPM Verification

```bash
# Test RPM calculation
# Expected: Consistent RPM reading when motor running

python3 -c "
import pigpio
import time

pi = pigpio.pi()
pulse_count = 0
PULSES_PER_REV = 1100  # Adjust for your gear ratio

def callback(gpio, level, tick):
    global pulse_count
    pulse_count += 1

pi.set_mode(5, pigpio.INPUT)
cb = pi.callback(5, pigpio.RISING_EDGE, callback)

# Start motor (GPIO 19 HIGH)
pi.set_mode(19, pigpio.OUTPUT)
pi.write(19, 1)

time.sleep(1)  # Run for 1 second

pi.write(19, 0)  # Stop motor

rpm = (pulse_count / PULSES_PER_REV) * 60
print(f'Pulses in 1 second: {pulse_count}')
print(f'Calculated RPM: {rpm:.1f}')

cb.cancel()
pi.stop()
"
```

---

## 11. Troubleshooting

### No Pulses Detected

1. **Check wiring:** Encoder VCC and GND connected?
2. **Check voltage:** Measure encoder output with multimeter (should see ~3.3V pulses)
3. **Check GPIO mode:** Pins set as INPUT?
4. **Check pull-up/down:** May need internal pull-up enabled

### Erratic Pulse Count

1. **Noise:** Add 0.1µF capacitor between encoder output and GND
2. **Debouncing:** Add software debounce (ignore pulses < 1ms apart)
3. **Grounding:** Ensure common ground between motor and RPi

### RPM Reading Too High/Low

1. **Verify gear ratio:** Check motor label
2. **Verify pulses_per_rev:** Should be 11 × gear_ratio
3. **Check both channels:** Count on A only, not A+B

---

## 12. References

- [Motor Product Page](https://www.airsoftmotor.com/micro-dc-reduction-motor/circular-reduction-motor/gm25-bk370-hall-encoder-dc-gear-motor.html)
- [pigpio Library Documentation](http://abyz.me.uk/rpi/pigpio/)
- [Quadrature Encoder Theory](https://en.wikipedia.org/wiki/Rotary_encoder#Incremental_encoder)
- [Current GPIO Control Implementation](../src/motor_control_ros2/src/gpio_control_functions.cpp)

---

## 13. Appendix: Pin Reference

### Current GPIO Usage (EE Motor)

| GPIO (BCM) | Physical Pin | Function | Direction |
|------------|--------------|----------|-----------|
| 19 | 35 | END_EFFECTOR_ON_PIN | Output |
| 12 | 32 | END_EFFECTOR_DIRECTION_PIN | Output |

### Proposed Additional GPIO (Encoder)

| GPIO (BCM) | Physical Pin | Function | Direction | Note |
|------------|--------------|----------|-----------|------|
| 5 | 29 | ENCODER_A_PIN | Input | ⚠️ Currently ISO_START_BUTTN - verify available |
| 6 | 31 | ENCODER_B_PIN | Input | ⚠️ Currently ISO_RESET_BUTTN - verify available |

> ⚠️ **Important:** GPIO 5 and 6 are mapped to ISO_START_BUTTN and ISO_RESET_BUTTN on the Robotics Board V1.2. Verify these buttons are not used by any software before repurposing for encoder.

### Full Motor Connector Pinout (PH2.0 6-pin)

| Pin | Wire Color (typical) | Function |
|-----|---------------------|----------|
| 1 | Red | Motor + (VCC) |
| 2 | Black | Motor - (GND) |
| 3 | Yellow | Encoder VCC (3.3V/5V) |
| 4 | Green | Encoder GND |
| 5 | Blue | Encoder A |
| 6 | White | Encoder B |

> ⚠️ **Note:** Wire colors may vary. Verify with multimeter before connecting.

---

## 14. Implementation Checklist

### Pre-Implementation Verification

- [ ] **Identify motor gear ratio** - Check label on motor (needed for pulses_per_rev calculation)
- [ ] **Locate encoder connector** - Find the 6-pin PH2.0 connector on motor
- [ ] **Verify encoder wire colors** - May differ from typical, use multimeter
- [ ] **Check GPIO availability** - ⚠️ **Critical:** Verify GPIO 5/6 are not in use (ISO_START/RESET buttons)

### Hardware Implementation

- [ ] **Connect Encoder VCC to RPi 3.3V (Pin 1)** - ⚠️ NOT 5V!
- [ ] **Connect Encoder GND to RPi GND (Pin 6)**
- [ ] **Connect Encoder A to GPIO 5 (Pin 29)**
- [ ] **Connect Encoder B to GPIO 6 (Pin 31)**
- [ ] **Verify voltages with multimeter** before powering RPi
- [ ] **Test manual rotation** - Rotate shaft, check for pulses

### Software Implementation

- [ ] **Add encoder pin definitions** to gpio_control_functions.hpp
- [ ] **Initialize encoder pins as INPUT** in initialization code
- [ ] **Register pigpio callbacks** for pulse counting
- [ ] **Add stall detection logic** - No pulses for 200ms = stall
- [ ] **Add RPM calculation** - Pulses per second × 60 / pulses_per_rev
- [ ] **Integrate with pick cycle** - Verify motor runs during EE activation
- [ ] **Add telemetry logging** - Include encoder data in pick stats

### Testing & Validation

- [ ] **Run hardware verification script** (Section 10.1)
- [ ] **Run RPM verification script** (Section 10.2)
- [ ] **Test stall detection** - Block motor shaft, verify detection
- [ ] **Test load detection** - Run with/without cotton, compare RPM
- [ ] **Long-duration test** - 100+ pick cycles, check for missed pulses
- [ ] **Field test** - Full integration in cotton picking scenario

---

## 15. Summary: Can RPi Handle This Without Additional Hardware?

### ⚠️ CONDITIONAL YES - Requires GPIO Pin Verification

| Requirement | Status | Details |
|-------------|--------|---------|
| **Voltage** | ✅ | Encoder supports 3.3V operation |
| **Frequency** | ✅ | ~1.8 kHz max, pigpio handles 25+ kHz |
| **Real-time** | ✅ | DMA-based sampling, independent of CPU |
| **Current** | ✅ | Encoder draws ~10-30mA, 3.3V rail supports 800mA |
| **GPIO** | ⚠️ | **Verify GPIO 5/6 available (ISO_START/RESET)** |
| **Software** | ✅ | pigpio already in use, just add callbacks |

### Critical Requirements

1. **MUST use 3.3V for Encoder VCC** - 5V will damage RPi GPIO
2. **MUST verify GPIO 5/6 availability** - may conflict with ISO_START/RESET buttons
3. **MAY need 0.1µF capacitors** if noise causes false pulses

### Cost-Benefit Analysis

| Aspect | Cost | Benefit |
|--------|------|---------|
| **Hardware** | 4 wires, ~2 capacitors (~$0.50) | Motor feedback capability |
| **Software** | ~200-500 lines of code | Stall detection, RPM, load sensing |
| **Development** | 2-5 days | Verified pick success, motor protection |
| **Risk** | Low (reversible wiring change) | High value (actual feedback vs assumed) |

### Conclusion

The encoder feedback integration requires **only wiring changes and software updates** IF:

1. **Encoder is powered from 3.3V** (NOT 5V - will damage RPi)
2. **Two GPIO input pins are available** (GPIO 5/6, or alternatives like GPIO 16/21)

No additional controller, logic level shifter, or specialized hardware is needed.

**Quick Wiring Summary (once GPIO pins confirmed):**
```
Encoder VCC (Yellow) → RPi 3.3V (Pin 1)   ← Always available
Encoder GND (Green)  → RPi GND (Pin 6)    ← Always available  
Encoder A (Blue)     → GPIO X (verified)  ← Any free input GPIO
Encoder B (White)    → GPIO Y (verified)  ← Any free input GPIO
```

### 🎯 Implementation Effort Summary

**IF GPIO pins are available, this is a LOW complexity task:**

| Aspect | Effort | Details |
|--------|--------|---------|
| **Hardware** | ~30 min | Solder 4 wires to encoder connector |
| **Wiring** | ~15 min | Connect to RPi GPIO header |
| **Software** | ~1-2 days | Add pigpio callbacks + ROS2 publisher |
| **Testing** | ~1 day | Calibrate pulses/rev, verify direction |
| **Total** | **2-3 days** | Mostly software development |

**Why it's simple:**
- ✅ pigpio library already in use (no new dependencies)
- ✅ Encoder is 3.3V compatible (no level shifters)
- ✅ ~1.8kHz max frequency (well within pigpio limits)
- ✅ No additional hardware/boards needed
- ✅ Existing motor control code can be extended

**No complexity from:**
- ❌ No external microcontroller needed
- ❌ No I²C/SPI protocol implementation
- ❌ No voltage level conversion
- ❌ No custom PCB or shield

---

## 16. Robotics Board V1.2 - Additional Notes

### Hardware Architecture Update

The analysis has been updated to reflect that the Pragati robot uses a custom **Robotics Board V1.2** which:

1. **Powers the RPi** via isolated 5V supply (URB4805YMD-20WR3)
2. **Contains the DRV8235RTER motor driver** for EE DC motor control
3. **Routes GPIO signals** from RPi to various subsystems via 40-pin header
4. **Provides power rails**: 24V input, 5V isolated, 3.3V regulated

### DRV8235 Motor Driver (on Robotics Board)

The EE motor is controlled via the onboard DRV8235RTER H-bridge:
- **DVR_IN1** (GPIO 12, Pin 32): EN/IN1 - Enable/Input 1
- **DVR_IN2** (GPIO 19, Pin 35): PH/IN2 - Phase/Input 2
- **Motor output**: J11 XT30 connector (DCMOTOR_OUT1, DCMOTOR_OUT2)

### GPIO Availability Constraint

**⚠️ CRITICAL**: Most GPIO pins are allocated by the Robotics Board. Before implementing encoder feedback:

1. Review `Robotics_Board_V1.2-1.pdf` schematic
2. Check `Connector mapping-1.pdf` for physical access
3. Identify which GPIO pins are actually accessible
4. Verify if ISO_START_BUTTN (GPIO 5) and ISO_RESET_BUTTN (GPIO 6) can be repurposed

### Reference Documents

- `Robotics_Board_V1.2-1.pdf` - Full schematic
- `Connector mapping-1.pdf` - Connector layout
- Located in: `/home/uday/Downloads/`

