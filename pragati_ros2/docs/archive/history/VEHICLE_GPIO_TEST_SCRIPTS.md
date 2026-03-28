# Vehicle GPIO Pin Validation Test Scripts

## Overview
Three comprehensive test scripts for validating GPIO functionality in the vehicle control system, similar to the existing compressor and end effector tests.

## Test Scripts

### 1. **test_vehicle_gpio_inputs.sh**
**Purpose:** Validate all GPIO input pins (switches, buttons, sensors)

**Pins Tested:**
- Direction Switch (GPIO 21) - Forward/Reverse
- Stop Button (GPIO 4) - Vehicle stop/brake
- Auto/Manual Switch (GPIO 26) - Mode selection
- Arm Start Button (GPIO 16) - Manual arm operation

**Test Phases:**
1. **Basic Input Tests**
   - Verify pin accessibility
   - Check input direction configuration
   - Read current pin states
   
2. **Interactive Tests**
   - Real-time state change monitoring
   - User activates physical switches/buttons
   - Validates wiring and switch functionality

**Usage:**
```bash
# On Raspberry Pi
cd ~/pragati_ros2
./scripts/testing/hardware/test_vehicle_gpio_inputs.sh
```

**Expected Output:**
- Pin accessibility confirmation
- Current state readings (HIGH/LOW)
- Interactive state change detection
- Pass/fail status for each input

---

### 2. **test_vehicle_gpio_outputs.sh**
**Purpose:** Validate all GPIO output pins (LEDs, fan control)

**Pins Tested:**
- Green LED (GPIO 17) - Status OK indicator
- Yellow LED (GPIO 27) - Warning indicator
- Red LED (GPIO 22) - Error indicator
- Fan (GPIO 23) - Cooling fan control
- Error LED (GPIO 24) - Critical error indicator

**Test Phases:**
1. **Basic Output Control**
   - Set pins HIGH and LOW
   - Verify state changes
   - Test write operations

2. **Visual Confirmation**
   - Blink each LED/device 3 times
   - User visual verification
   - LED polarity/wiring validation

3. **LED Sequence**
   - All LEDs light in order
   - Multiple rounds for clarity
   - Complete system visual check

4. **Fan Control**
   - Start fan for 3 seconds
   - Stop fan gracefully
   - Audio/tactile verification

**Usage:**
```bash
# On Raspberry Pi
cd ~/pragati_ros2
./scripts/testing/hardware/test_vehicle_gpio_outputs.sh
```

**Expected Output:**
- HIGH/LOW control verification
- Visual blink confirmation
- LED sequence visualization
- Fan operation confirmation

---

### 3. **test_vehicle_gpio_full.sh**
**Purpose:** Full GPIO integration test via ROS2 vehicle_control_node

**Integration Stack Tested:**
```
Hardware GPIO → pigpiod daemon → GPIO Manager → ROS2 Services → User Commands
```

**ROS2 Services Tested:**
- `/vehicle_control/led_control` - LED control service
- `/vehicle_control/lid_open` - Lid actuator service
- `/vehicle_control/emergency_stop` - Emergency stop service

**ROS2 Topics Monitored:**
- `/vehicle_control/gpio_status` - Real-time GPIO state

**Test Phases:**
1. **Prerequisites Check**
   - ROS2 environment sourced
   - vehicle_control_node running
   - GPIO enabled in config

2. **Service Availability**
   - List all GPIO services
   - Verify service registration
   - Check topic publishers

3. **Service Functionality**
   - LED ON/OFF via ROS2
   - Lid control via ROS2
   - Emergency stop trigger
   - Status topic data validation

4. **Visual Tests (Optional)**
   - LED blinking via ROS2 services
   - User confirmation

5. **Input Monitoring (Optional)**
   - 10-second GPIO status monitoring
   - Switch/button activation detection
   - Real-time state updates

**Prerequisites:**
```bash
# Enable GPIO in config
vim src/vehicle_control/config/production.yaml
# Set: enable_gpio: true

# Build and run node
colcon build --packages-select vehicle_control
source install/setup.bash
ros2 run vehicle_control vehicle_control_node
```

**Usage:**
```bash
# In separate terminal (after node is running)
cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source install/setup.bash
./scripts/testing/hardware/test_vehicle_gpio_full.sh
```

**Expected Output:**
- Service call success confirmations
- GPIO status topic data
- LED visual verification
- Complete integration validation

---

## Testing Workflow

### Step 1: Hardware-Only Tests
Run hardware tests WITHOUT ROS2 node running:

```bash
# Test inputs first
./scripts/testing/hardware/test_vehicle_gpio_inputs.sh

# Then test outputs
./scripts/testing/hardware/test_vehicle_gpio_outputs.sh
```

### Step 2: Enable GPIO
After hardware validation passes:

```bash
# Edit config
vim src/vehicle_control/config/production.yaml
# Change: enable_gpio: false → enable_gpio: true

# Rebuild
colcon build --packages-select vehicle_control
```

### Step 3: Full Integration Test
Run with ROS2 node:

```bash
# Terminal 1: Start node
ros2 run vehicle_control vehicle_control_node

# Terminal 2: Run integration test
./scripts/testing/hardware/test_vehicle_gpio_full.sh
```

---

## Pin Assignment Reference

### Input Pins (with pull resistors)
| Pin Name | GPIO | Pull | Function |
|----------|------|------|----------|
| direction_switch | 21 | DOWN | Forward/Reverse |
| stop_button | 4 | DOWN | Vehicle stop |
| auto_manual_switch | 26 | DOWN | Mode selection |
| arm_start | 16 | DOWN | Arm trigger |

### Output Pins
| Pin Name | GPIO | Function |
|----------|------|----------|
| green_led | 17 | Status OK |
| yellow_led | 27 | Warning |
| red_led | 22 | Error |
| fan | 23 | Cooling |
| error_led | 24 | Critical error |

---

## Troubleshooting

### Test Failures - Input Pins
**Problem:** "No state change detected"
- Check physical wiring
- Verify switch operation with multimeter
- Ensure proper pull resistor configuration
- Check for loose connections

### Test Failures - Output Pins
**Problem:** "LED not blinking" or "Fan not running"
- Check LED polarity (anode/cathode)
- Verify resistor values (220-330Ω for LEDs)
- Test with multimeter for voltage
- Check for short circuits
- Verify 3.3V power supply

### Test Failures - ROS2 Integration
**Problem:** "Service not available"
- Check GPIO enabled: `grep enable_gpio config/production.yaml`
- Verify node running: `ros2 node list | grep vehicle_control`
- Check pigpiod: `sudo systemctl status pigpiod`
- Review node logs for GPIO initialization message

---

## Comparison with Existing Tests

Similar to compressor and end effector tests, these GPIO tests provide:
- ✅ Hardware-level validation
- ✅ Interactive user confirmation
- ✅ Visual/audio feedback
- ✅ Clear pass/fail criteria
- ✅ Detailed troubleshooting guidance
- ✅ Step-by-step workflow

**Additional features:**
- Separate input/output testing
- Full ROS2 integration validation
- Real-time GPIO monitoring
- Service-level testing

---

## Field Trial Integration

### Pre-Deployment Checklist
1. ☐ Run `test_vehicle_gpio_inputs.sh` - all switches work
2. ☐ Run `test_vehicle_gpio_outputs.sh` - all LEDs/fan work
3. ☐ Enable GPIO in production.yaml
4. ☐ Run `test_vehicle_gpio_full.sh` - ROS2 integration works
5. ☐ Document any pin assignment issues
6. ☐ Verify emergency stop functionality

### During Testing
- Keep GPIO disabled initially (`enable_gpio: false`)
- Validate motor control without GPIO interference
- Enable GPIO only after pin verification complete
- Use LED indicators for system status monitoring

---

## File Locations

```
pragati_ros2/
└── scripts/
    └── testing/
        └── hardware/
            ├── test_vehicle_gpio_inputs.sh    # Input pin tests
            ├── test_vehicle_gpio_outputs.sh   # Output pin tests
            └── test_vehicle_gpio_full.sh      # ROS2 integration tests
```

---

## Related Documentation

- **GPIO Disable Feature:** `docs/VEHICLE_GPIO_DISABLE_FEATURE.md`
- **Vehicle Control Config:** `src/vehicle_control/config/production.yaml`
- **GPIO Manager:** `src/vehicle_control/hardware/gpio_manager.py`
- **Hardware Checklist:** `docs/HARDWARE_TEST_CHECKLIST.md`
- **Field Trial Plan:** `docs/project-notes/JANUARY_FIELD_TRIAL_PLAN_2025.md`

---

## Safety Notes

⚠️ **Important Safety Guidelines:**

1. **Always test with GPIO disabled first** (`enable_gpio: false`)
2. **Verify pin assignments** before enabling GPIO
3. **Use current-limiting resistors** for all LEDs (220-330Ω)
4. **Never exceed 3.3V** on GPIO pins
5. **Check for short circuits** before powering on
6. **Emergency stop button** must be accessible during tests
7. **Disconnect motors** during initial GPIO testing
8. **Use proper ESD protection** when handling Raspberry Pi

---

## Success Criteria

All tests pass when:
- ✅ All input pins detect state changes
- ✅ All output pins control devices successfully
- ✅ Visual confirmation for all LEDs
- ✅ Fan operates on command
- ✅ ROS2 services respond correctly
- ✅ GPIO status topic publishes data
- ✅ No wiring or polarity issues
- ✅ Emergency stop functional

---

**Last Updated:** December 10, 2025  
**Author:** Pragati ROS2 Development Team  
**Status:** Ready for field testing
