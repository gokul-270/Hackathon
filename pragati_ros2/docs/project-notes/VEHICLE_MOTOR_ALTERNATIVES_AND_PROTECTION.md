# Vehicle Motor Alternatives and Back-EMF Protection Guide

**Date:** January 28, 2026
**Status:** 🔴 CRITICAL - Motors burnt, no replacements available
**Owner:** Gokul, Uday

---

## 1. Problem Statement

### What Happened
When the vehicle was moved manually **without power**, the drive motors were burnt due to **back-EMF (Electromotive Force)** damage.

### Technical Explanation
```
When motor is powered:     Motor consumes electricity → Rotation
When motor is back-driven: External force rotates motor → Motor generates electricity

The generated voltage (back-EMF) flows BACK into the motor controller.
Without protection, this voltage spike damages:
  1. Motor windings (burnt/shorted)
  2. Motor controller electronics
  3. Power supply capacitors
```

### Why This Happens with BLDC Motors
MG6010/MG6012 are **Brushless DC (BLDC) motors** with permanent magnets. When rotated:
- Permanent magnets induce voltage in stator windings
- Voltage is proportional to rotation speed: `V_emf = k × ω`
- At normal walking speed (~1 m/s), back-EMF can exceed rated voltage

---

## 2. Current Motor Specifications

### Damaged Motors

| Motor | Type | Application | Qty | Status |
|-------|------|-------------|-----|--------|
| MG6012-i6 | BLDC + 1:6 internal | Steering | 3 | ✅ Working (survived January) |
| MG6012-i36 | BLDC + 1:36 internal | Drive | 3 | ❌ BURNT |

### Key Specifications (MG6012-i6)
- **Voltage:** 24V (range 7.4V-32V)
- **Max Torque:** 10 N·m
- **Internal Gear:** 1:6
- **External Gear:** 1:50 (steering), 1:5 (drive)
- **CAN Protocol:** LK-TECH CAN V2.35

---

## 3. Motor Alternatives

### 3.1 Option A: Repair Existing Motors (RECOMMENDED FIRST)

**Damage Assessment Needed:**
```bash
# Check motor winding resistance (should be ~1-5 ohms between phases)
# Use multimeter between motor phase wires (U-V, V-W, W-U)
# If infinite resistance → winding open (burnt)
# If near-zero resistance → winding shorted (burnt)
```

**If Controller Damaged (Motor OK):**
- MG6010/MG6012 have integrated controllers
- Contact LK-TECH/MyActuator for controller replacement
- Estimated cost: ~$50-100 per motor

**If Windings Damaged:**
- Rewinding possible but expensive (~$100-200 per motor)
- Usually not cost-effective for integrated motors

### 3.2 Option B: Same Model Replacement

| Source | Model | Lead Time | Cost (est.) |
|--------|-------|-----------|-------------|
| MyActuator (official) | MG6010-i6 | 2-4 weeks | ~$150-200 |
| MyActuator (official) | MG6012-i36 | 2-4 weeks | ~$200-250 |
| AliExpress (LK-TECH) | MG6010-i6 | 1-3 weeks | ~$100-150 |

**Pros:** No software changes, same mounting, proven compatibility
**Cons:** Lead time, same vulnerability to back-EMF

### 3.3 Option C: Alternative BLDC Motors

| Motor | Specs | Compatibility | Cost |
|-------|-------|---------------|------|
| **ODrive D6374** | 150KV, 24V | Needs new driver | ~$80 + ODrive $200 |
| **T-Motor AK80-6** | 6:1 gear, CAN | Similar protocol | ~$400 |
| **Xiaomi CyberGear** | 1:9 gear, CAN | Different protocol | ~$300 |
| **iPower GM6208** | Gimbal motor | Lower torque | ~$60 |

**Considerations:**
- Different CAN protocols require driver changes
- Mounting dimensions may differ
- Gear ratios affect software calculations

### 3.4 Option D: Stepper Motors (Not Recommended)

| Pros | Cons |
|------|------|
| No back-EMF issue when unpowered | Lower speed |
| Cheaper | Lower efficiency |
| Position holding without power | Vibration/noise |
| | Requires different driver |

**Verdict:** Not suitable for vehicle drive; may work for steering

---

## 4. Back-EMF Protection Solutions

### 4.1 Hardware Protection (CRITICAL - Implement Before Next Visit)

#### Solution 1: Flyback/Freewheeling Diodes (REQUIRED)
```
Motor phases    Diode bank
   U ─────────┬──→|──┬───── +V
   V ─────────┼──→|──┤
   W ─────────┼──→|──┤
              │      │
              └──────┴───── GND

Diode type: Fast recovery (e.g., MUR1560, 15A 600V)
Install: Across each motor phase to power rails
Cost: ~$5-10 per motor
```

**How it works:** When back-EMF is generated, diodes conduct and safely dissipate energy to power supply capacitors.

#### Solution 2: TVS (Transient Voltage Suppressor) Diodes
```
Install: Between power rails (+V and GND)
Rating: Breakdown voltage slightly above nominal (e.g., 30V TVS for 24V system)
Examples: SMBJ30A, P6KE30A
Cost: ~$2-5 per motor
```

**How it works:** Clamps voltage spikes that exceed threshold, preventing controller damage.

#### Solution 3: Regenerative Braking Resistor
```
         ┌─────────────┐
+V ──────┤             │
         │  Power      ├──── Regen
GND ─────┤  Stage      │     Resistor
         └──────┬──────┘     (10-50Ω, 50-100W)
                │
              Motor
```

**How it works:** Absorbs regenerated energy as heat instead of feeding back to controller.

**Components needed:**
- Power resistor: 10-50Ω, 50-100W (wirewound)
- Switching MOSFET/relay to engage during regen
- Cost: ~$20-30 per motor

#### Solution 4: Mechanical Wheel Lock
```
Simple solution: Engage parking brake or wheel chocks before moving vehicle
More complex: Add solenoid-actuated wheel locks
```

### 4.2 Recommended Protection Implementation

**Minimum (Before Feb 25 visit):**
1. ✅ TVS diodes on power rails (~$10 total)
2. ✅ Flyback diodes on motor phases (~$30 total)
3. ✅ Warning labels: "DO NOT PUSH VEHICLE WITHOUT POWER"

**Ideal (If time permits):**
4. ⬜ Regenerative braking resistor circuit
5. ⬜ Software detection of back-EMF condition
6. ⬜ Mechanical wheel locks

### 4.3 Circuit Diagram

```
                   ┌─────────────────────────────────────┐
                   │         PROTECTION BOARD            │
                   │                                     │
 Battery ──────────┤ +24V ──┬── TVS ──┬── Flyback ──────├──── Motor Controller
      │            │        │  (30V)  │   Diodes        │
      │            │ GND ───┴─────────┴─────────────────├──── Motor Phases
      │            │                                     │
      │            │        Regen Resistor (optional)    │
      │            │        ════════════════             │
      │            └─────────────────────────────────────┘
      │
 Main Switch (MUST be ON when moving vehicle)
```

---

## 5. Software Enhancements

### 5.1 Back-EMF Detection
```cpp
// Add to mg6010_controller_node.cpp

void checkBackEMF() {
    // Monitor bus voltage
    float bus_voltage = readBusVoltage();

    // If voltage exceeds nominal by >10%, possible regen
    if (bus_voltage > NOMINAL_VOLTAGE * 1.1) {
        RCLCPP_WARN(logger_, "⚠️ Back-EMF detected! V=%.1fV", bus_voltage);
        // Engage regen resistor or alert operator
        engageRegenResistor();
    }
}
```

### 5.2 Startup Warning
```cpp
// Add to initialization sequence
RCLCPP_WARN(logger_, "🚨 WARNING: Do NOT move vehicle manually when power is OFF!");
RCLCPP_WARN(logger_, "🚨 Motor damage will occur from back-EMF!");
```

---

## 6. Immediate Action Plan

### This Week (Before Feb 25)
| Task | Owner | Deadline | Status |
|------|-------|----------|--------|
| Diagnose motor damage (multimeter test) | Gokul | Jan 30 | ⬜ |
| Order TVS + flyback diodes | Uday | Jan 30 | ⬜ |
| Contact MyActuator for replacements | Gokul | Jan 31 | ⬜ |
| Install protection circuit | Gokul | Feb 15 | ⬜ |
| Create warning labels | Uday | Feb 1 | ⬜ |
| Update SOP documentation | Uday | Feb 5 | ⬜ |

### Parts List
| Part | Qty | Supplier | Est. Cost |
|------|-----|----------|-----------|
| SMBJ30A TVS diodes | 10 | DigiKey/Mouser | $5 |
| MUR1560 fast diodes | 20 | DigiKey/Mouser | $10 |
| 25Ω 100W resistor | 6 | DigiKey/Mouser | $30 |
| Heat sinks | 6 | Amazon | $10 |
| **Total** | | | **~$55** |

---

## 7. Questions for Motor Supplier

1. Is controller damage separate from winding damage for MG6010/MG6012?
2. Can controllers be replaced separately?
3. Do you offer motors with built-in regen protection?
4. What is lead time for emergency replacement?
5. Can damaged motors be sent for repair assessment?

---

## 8. References

- MG6010/MG6012 Datasheet: `/home/uday/Downloads/MG_motors.pdf`
- LK-TECH CAN Protocol V2.35: `/home/uday/Downloads/CANprotocal.pdf`
- Motor control code: `src/motor_control_ros2/`

---

**Document Status:** Draft - Awaiting team review
**Last Updated:** January 28, 2026
