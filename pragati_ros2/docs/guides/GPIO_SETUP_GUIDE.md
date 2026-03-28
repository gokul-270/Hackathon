# GPIO Setup Guide

**Version**: 2.0
**Last Updated**: March 2026
**Target Platform**: Raspberry Pi 4B running Ubuntu 24.04 (arm64)

---

## Overview

This guide covers GPIO (General Purpose Input/Output) configuration for the Pragati ROS2 cotton picking robot, including status LEDs, motor control, and switch inputs.

### GPIO Architecture

Production firmware uses the **pigpiod** daemon for all GPIO access:

- **Daemon**: `pigpiod` — runs as a system service, provides shared access to GPIO pins
- **C/C++ interface**: `pigpiod_if2` — used by ROS2 C++ nodes (arm role)
- **Python interface**: `pigpio` module — used by vehicle-role Python nodes

> **Legacy note:** Earlier prototypes used `RPi.GPIO` (Python) and `libgpiod` (C++).
> These are no longer used in production. The example code in the "Code Implementation"
> section below retains `libgpiod` patterns for reference only — production code uses
> `pigpiod_if2` via `gpio_control_functions.hpp`.

### Current Status

- **Arm role (C++)**: GPIO active via `pigpiod_if2` — see `gpio_control_functions.hpp`
- **Vehicle role (Python)**: GPIO active via `pigpio` module — see `constants.py`
- **Build flag**: `USE_GPIO=ON` enables GPIO in C++ packages

For the consolidated pin map covering both arm and vehicle roles, see [GPIO_PIN_MAP.md](GPIO_PIN_MAP.md).

---

## Hardware Requirements

### Supported Platform

| Platform | GPIO Library | Pin Count | Voltage | Notes |
|----------|--------------|-----------|---------|-------|
| **Raspberry Pi 4B** | pigpiod (pigpiod_if2 / pigpio) | 40-pin header | 3.3V | Production target |

> Other SBCs (Jetson, generic Linux with libgpiod) are not currently supported or tested.

### Required Components

1. **Emergency Stop Button**
   - Type: Normally-open push button (red, mushroom head recommended)
   - Rating: Low voltage (3.3V-5V logic)
   - Wiring: NO (Normally Open) configuration
   - Quantity: 1-2 (primary + backup recommended)

2. **Status LEDs** (Optional)
   - Red LED: Emergency stop / error state
   - Green LED: System ready
   - Yellow LED: System busy
   - Current-limiting resistors: 220Ω-330Ω for 3.3V

3. **Level Shifters** (If needed)
   - Bidirectional 3.3V ↔ 5V level shifter
   - Required if interfacing with 5V devices
   - Recommended: Sparkfun BOB-12009 or similar

4. **Wiring and Connectors**
   - Dupont wires or crimped connectors
   - Heat shrink tubing
   - Terminal blocks (optional, for permanent installation)

---

## Pin Mapping

### Arm-Role Pin Assignment (Raspberry Pi 4B)

Source of truth: `src/yanthra_move/include/yanthra_move/gpio_control_functions.hpp`

| BCM Pin | Physical Pin | Function | Direction | Notes |
|---------|--------------|----------|-----------|-------|
| 2 | 3 | Shutdown Switch | Input | Active-low, internal pull-up |
| 3 | 5 | Start Switch | Input | Active-low, internal pull-up |
| 4 | 7 | Green LED | Output | System ready indicator |
| 12 | 32 | EE Drop ON (M2 Enable) / Cotton Drop Servo | Output | Motor 2 enable |
| 13 | 33 | End Effector Direction | Output | Motor direction |
| 14 | 8 | Transport Servo | Output | Servo PWM |
| 15 | 10 | Red LED | Output | Error/status indicator |
| 17 | 11 | Camera LED | Output | Illumination |
| 18 | 12 | Compressor | Output | Pneumatic relay |
| 20 | 38 | EE Drop Direction (M2 Direction) | Output | Motor 2 direction |
| 21 | 40 | End Effector ON (M1 Enable) | Output | Motor 1 enable |
| 24 | 18 | Vacuum Motor ON | Output | Vacuum relay |

**Pin Numbering**: Uses BCM (Broadcom) numbering, not physical pin numbers.

### Wiring Diagram

```
Switch Input (Example: Shutdown Switch on BCM 2)
+----------------------------------------------+
|                                               |
|  +3.3V -----+--- 10k Resistor ---+           |
|              |                    |           |
|              +--- Switch --------+--- BCM 2  |
|                       |                       |
|                      GND                      |
+----------------------------------------------+

LED Output (Example: Green LED on BCM 4)
+----------------------------------------------+
|                                               |
|  BCM 4 --- 330 Resistor --- LED --- GND      |
|                             (v)               |
|                           Anode  Cathode      |
+----------------------------------------------+
```

**Safety Note**: Always use current-limiting resistors with LEDs to prevent damage.

---

## Software Configuration

### Step 1: Enable GPIO at Build Time

#### Modify CMake Configuration

**File**: `src/yanthra_move/CMakeLists.txt` or top-level CMakeLists.txt

```cmake
# Enable GPIO support
option(USE_GPIO "Enable GPIO support for hardware I/O" ON)

if(USE_GPIO)
    add_definitions(-DUSE_GPIO)

    # Find GPIO library
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(GPIOD REQUIRED libgpiod)

    include_directories(${GPIOD_INCLUDE_DIRS})
    link_directories(${GPIOD_LIBRARY_DIRS})

    # Link GPIO library
    target_link_libraries(${PROJECT_NAME}
        ${GPIOD_LIBRARIES}
    )
endif()
```

#### Rebuild with GPIO Enabled

```bash
cd /home/uday/Downloads/pragati_ros2

# Clean previous build
rm -rf build/ install/ log/

# Build with GPIO support
colcon build --cmake-args -DUSE_GPIO=ON

# Source the workspace
source install/setup.bash
```

### Step 2: Install GPIO Libraries

#### pigpiod (Production — Raspberry Pi 4B)

```bash
# Install pigpio daemon and libraries
sudo apt-get update
sudo apt-get install -y pigpio python3-pigpio

# Enable and start pigpiod as a system service
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

# Verify pigpiod is running
pigs t  # Should return current tick count

# Verify GPIO chip is accessible
gpiodetect
gpioinfo
```

> **Note:** The `pigpiod_if2` C library is included with the `pigpio` package.
> Python code imports `pigpio`; C++ code links against `pigpiod_if2`.

### Step 3: Configure GPIO Permissions

#### Add User to GPIO Group

```bash
# Find GPIO group
ls -l /dev/gpio* /sys/class/gpio

# Add user to group
sudo usermod -a -G gpio $USER
sudo usermod -a -G dialout $USER  # For serial devices if needed

# Create udev rules for GPIO access
sudo tee /etc/udev/rules.d/99-gpio.rules << EOF
SUBSYSTEM=="gpio", KERNEL=="gpiochip*", GROUP="gpio", MODE="0660"
SUBSYSTEM=="gpio*", PROGRAM="/bin/sh -c 'chown -R root:gpio /sys/class/gpio && chmod -R 770 /sys/class/gpio; chown -R root:gpio /sys/devices/virtual/gpio && chmod -R 770 /sys/devices/virtual/gpio'"
EOF

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Logout and login for group changes to take effect
```

### Step 4: Update ROS2 Parameters

> **Note:** Arm-role GPIO pins are defined as compile-time constants in
> `gpio_control_functions.hpp`, not as ROS2 parameters. Vehicle-role pins are
> defined in `constants.py`. The YAML config below is a legacy example and
> does not reflect the current pin architecture.

**File**: `src/yanthra_move/config/production.yaml` (vehicle role only)

```yaml
vehicle_control:
  ros__parameters:
    # GPIO pins defined in constants.py — these are for reference
    # Actual pin assignments are in src/vehicle_control/vehicle_control/constants.py
    gpio_polling_rate_hz: 100
    led_blink_rate_hz: 2
```

---

## Code Implementation

### GPIO Manager Class (C++)

**File**: `src/yanthra_move/include/yanthra_move/gpio_manager.hpp`

```cpp
#pragma once

#ifdef USE_GPIO
#include <gpiod.hpp>
#endif

#include <rclcpp/rclcpp.hpp>
#include <memory>
#include <functional>

namespace yanthra_move {

class GPIOManager {
public:
    using EmergencyStopCallback = std::function<void()>;

    explicit GPIOManager(rclcpp::Node* node);
    ~GPIOManager();

    // Initialization
    bool initialize();
    void shutdown();

    // Emergency stop
    void setEmergencyStopCallback(EmergencyStopCallback callback);
    bool isEmergencyStopPressed() const;

    // LED control
    void setRedLED(bool state);
    void setGreenLED(bool state);
    void setYellowLED(bool state);
    void blinkLED(int pin, double rate_hz);

private:
    rclcpp::Node* node_;

#ifdef USE_GPIO
    std::unique_ptr<gpiod::chip> chip_;
    std::unique_ptr<gpiod::line> emergency_stop_line_;
    std::unique_ptr<gpiod::line> red_led_line_;
    std::unique_ptr<gpiod::line> green_led_line_;
    std::unique_ptr<gpiod::line> yellow_led_line_;
#endif

    EmergencyStopCallback emergency_stop_callback_;
    rclcpp::TimerBase::SharedPtr gpio_poll_timer_;

    void pollGPIO();
    bool setupInputPin(int pin, const std::string& consumer);
    bool setupOutputPin(int pin, const std::string& consumer);
};

} // namespace yanthra_move
```

**File**: `src/yanthra_move/src/gpio_manager.cpp`

```cpp
#include "yanthra_move/gpio_manager.hpp"
#include <chrono>

namespace yanthra_move {

GPIOManager::GPIOManager(rclcpp::Node* node) : node_(node) {}

GPIOManager::~GPIOManager() {
    shutdown();
}

bool GPIOManager::initialize() {
#ifdef USE_GPIO
    try {
        // Open GPIO chip
        chip_ = std::make_unique<gpiod::chip>("gpiochip0");

        // Get pin numbers from parameters
        int e_stop_pin = node_->declare_parameter("gpio_emergency_stop_pin", 17);
        int red_led_pin = node_->declare_parameter("gpio_red_led_pin", 22);
        int green_led_pin = node_->declare_parameter("gpio_green_led_pin", 23);
        int yellow_led_pin = node_->declare_parameter("gpio_yellow_led_pin", 24);

        // Setup input pins (emergency stop)
        emergency_stop_line_ = chip_->get_line(e_stop_pin);
        emergency_stop_line_->request({
            "yanthra_move",
            gpiod::line_request::DIRECTION_INPUT,
            gpiod::line_request::FLAG_BIAS_PULL_UP
        });

        // Setup output pins (LEDs)
        red_led_line_ = chip_->get_line(red_led_pin);
        red_led_line_->request({
            "yanthra_move",
            gpiod::line_request::DIRECTION_OUTPUT,
            0
        }, 0);  // Initial value LOW

        green_led_line_ = chip_->get_line(green_led_pin);
        green_led_line_->request({"yanthra_move", gpiod::line_request::DIRECTION_OUTPUT, 0}, 0);

        yellow_led_line_ = chip_->get_line(yellow_led_pin);
        yellow_led_line_->request({"yanthra_move", gpiod::line_request::DIRECTION_OUTPUT, 0}, 0);

        // Start GPIO polling timer
        int poll_rate = node_->declare_parameter("gpio_polling_rate_hz", 100);
        auto poll_period = std::chrono::milliseconds(1000 / poll_rate);
        gpio_poll_timer_ = node_->create_wall_timer(
            poll_period,
            std::bind(&GPIOManager::pollGPIO, this)
        );

        RCLCPP_INFO(node_->get_logger(), "GPIO initialized successfully");
        return true;

    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(),
            "Failed to initialize GPIO: %s", e.what());
        return false;
    }
#else
    RCLCPP_WARN(node_->get_logger(),
        "GPIO support not compiled (USE_GPIO=OFF)");
    return false;
#endif
}

void GPIOManager::shutdown() {
#ifdef USE_GPIO
    if (gpio_poll_timer_) {
        gpio_poll_timer_->cancel();
    }

    // Turn off all LEDs
    if (red_led_line_) red_led_line_->set_value(0);
    if (green_led_line_) green_led_line_->set_value(0);
    if (yellow_led_line_) yellow_led_line_->set_value(0);

    // Release GPIO lines
    if (emergency_stop_line_) emergency_stop_line_->release();
    if (red_led_line_) red_led_line_->release();
    if (green_led_line_) green_led_line_->release();
    if (yellow_led_line_) yellow_led_line_->release();

    RCLCPP_INFO(node_->get_logger(), "GPIO shutdown complete");
#endif
}

void GPIOManager::setEmergencyStopCallback(EmergencyStopCallback callback) {
    emergency_stop_callback_ = callback;
}

bool GPIOManager::isEmergencyStopPressed() const {
#ifdef USE_GPIO
    if (emergency_stop_line_) {
        // Button is normally open with pull-up
        // Pressed = LOW (0), Released = HIGH (1)
        return emergency_stop_line_->get_value() == 0;
    }
#endif
    return false;
}

void GPIOManager::pollGPIO() {
#ifdef USE_GPIO
    // Check emergency stop button
    if (isEmergencyStopPressed() && emergency_stop_callback_) {
        RCLCPP_WARN(node_->get_logger(), "Hardware emergency stop pressed!");
        emergency_stop_callback_();
    }
#endif
}

void GPIOManager::setRedLED(bool state) {
#ifdef USE_GPIO
    if (red_led_line_) {
        red_led_line_->set_value(state ? 1 : 0);
    }
#endif
}

void GPIOManager::setGreenLED(bool state) {
#ifdef USE_GPIO
    if (green_led_line_) {
        green_led_line_->set_value(state ? 1 : 0);
    }
#endif
}

void GPIOManager::setYellowLED(bool state) {
#ifdef USE_GPIO
    if (yellow_led_line_) {
        yellow_led_line_->set_value(state ? 1 : 0);
    }
#endif
}

} // namespace yanthra_move
```

---

## Testing Procedures

### Pre-Test Checklist

- [ ] GPIO libraries installed
- [ ] User added to gpio group (and logged out/in)
- [ ] udev rules configured
- [ ] Wiring double-checked (no shorts!)
- [ ] Current-limiting resistors in place for LEDs
- [ ] Emergency stop button wired correctly (NO configuration)

### Test 1: GPIO Detection

```bash
# List available GPIO chips
gpiodetect

# Expected output:
# gpiochip0 [pinctrl-bcm2835] (54 lines)

# Verify pigpiod is running
pigs t

# Show GPIO line information for arm-role pins
gpioinfo gpiochip0 | grep -E "line (2|3|4|12|13|14|15|17|18|20|21|24) "
```

### Test 2: LED Control (Manual)

```bash
# Test Green LED (BCM 4)
pigs w 4 1   # Turn on
sleep 1
pigs w 4 0   # Turn off

# Test Red LED (BCM 15)
pigs w 15 1  # Turn on
sleep 1
pigs w 15 0  # Turn off

# Test Camera LED (BCM 17)
pigs w 17 1  # Turn on
sleep 1
pigs w 17 0  # Turn off
```

### Test 3: Switch Input (Manual)

```bash
# Monitor shutdown switch (BCM 2)
# Press and hold button while running this:
pigs r 2

# Expected:
# - Released (not pressed): 1 (HIGH due to pull-up)
# - Pressed: 0 (LOW, button connects to ground)
```

### Test 4: ROS2 Integration Test

```bash
# Terminal 1: Launch with GPIO enabled
ros2 launch yanthra_move yanthra_move.launch.py

# Terminal 2: Monitor emergency stop topic
ros2 topic echo /emergency_stop

# Physical action: Press emergency stop button
# Expected: /emergency_stop topic shows "data: true"

# Terminal 3: Control LEDs via service (if implemented)
ros2 service call /gpio/set_led yanthra_move_interfaces/srv/SetLED "{led: 'red', state: true}"
```

### Test 5: Emergency Stop Response Time

```bash
# Measure response time from button press to motion halt
./scripts/test_emergency_stop_timing.sh

# Expected: < 500ms total response time
# - GPIO detection: < 10ms (100Hz polling)
# - ROS2 callback: < 50ms
# - Motion halt: < 100ms
```

---

## Troubleshooting

### Permission Denied Errors

**Symptom**: `Permission denied` when accessing `/dev/gpiochip*`

**Solution**:
```bash
# Check current groups
groups

# Ensure gpio group exists and user is member
sudo groupadd -f gpio
sudo usermod -a -G gpio $USER

# Check file permissions
ls -l /dev/gpiochip*

# Should show: crw-rw---- 1 root gpio

# If not, apply udev rules and reboot
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo reboot
```

### GPIO Chip Not Found

**Symptom**: `gpiodetect` shows no chips

**Solution**:
```bash
# Check if GPIO kernel module is loaded
lsmod | grep gpio

# For Raspberry Pi, ensure dtparam is set
# Edit /boot/config.txt:
dtparam=gpio=on

# Reboot
sudo reboot
```

### LEDs Not Lighting

**Checks**:
1. Correct resistor value (220Ω-330Ω for 3.3V)
2. LED polarity (anode to resistor, cathode to ground)
3. GPIO pin configured as OUTPUT
4. GPIO pin value set to HIGH (1)
5. Sufficient power supply

**Debug**:
```bash
# Measure voltage at GPIO pin
# Should read ~3.3V when HIGH

# Test LED directly with 3.3V and resistor
# If LED works, problem is software configuration
```

### Emergency Stop Not Triggering

> **Note:** Hardware E-stop is not yet assigned a GPIO pin (see GAP-ELEC-002).
> The shutdown switch on BCM 2 provides a software-level stop.

**Checks (for shutdown switch)**:
1. Button wired correctly (NO configuration)
2. Pull-up resistor or internal pull-up enabled
3. pigpiod daemon running (`pigs t`)
4. Callback function registered
5. ROS topic connected

**Debug**:
```bash
# Verify pigpiod is running
systemctl status pigpiod

# Monitor GPIO value in real-time
watch -n 0.1 'pigs r 2'

# Press button and observe value change
# Should toggle between 1 (released) and 0 (pressed)
```

---

## Safety Considerations

### Electrical Safety

⚠️ **WARNING**: Improper GPIO wiring can damage your board!

1. **Never exceed voltage limits**: 3.3V max for most boards
2. **Always use current-limiting resistors**: Especially for LEDs
3. **Check for shorts**: Use multimeter before powering on
4. **Proper grounding**: All grounds must be common
5. **ESD protection**: Use anti-static wrist strap when handling

### Emergency Stop Safety

1. **Normally-Open Configuration**: Ensures button press always triggers stop
2. **Hardware Redundancy**: Consider dual e-stop buttons
3. **Failsafe Design**: System should halt on GPIO read failure
4. **Regular Testing**: Test e-stop weekly in production

### Best Practices

- ✅ Document all pin assignments
- ✅ Label all wires clearly
- ✅ Use crimped connectors for permanent installations
- ✅ Protect exposed pins with enclosure
- ✅ Add fuses for high-current devices
- ✅ Keep GPIO wires short to reduce noise

---

## Related Documentation

- **GPIO Pin Map**: `docs/guides/GPIO_PIN_MAP.md` — consolidated pin map for arm and vehicle roles
- **Safety Monitor Guide**: `docs/guides/SAFETY_MONITOR_INTEGRATION_GUIDE.md`
- **Source Code (arm)**: `src/yanthra_move/include/yanthra_move/gpio_control_functions.hpp`
- **Source Code (vehicle)**: `src/vehicle_control/vehicle_control/constants.py`

---

## Revision History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-09-30 | 1.0 | Initial GPIO setup guide | AI Assistant |
| 2026-03-08 | 2.0 | Updated to pigpiod architecture, aligned pins with gpio_control_functions.hpp, added GPIO_PIN_MAP.md link | AI Assistant |

---

## Quick Reference

### Start pigpiod
```bash
sudo systemctl start pigpiod
pigs t  # Verify running
```

### Enable GPIO at Build
```bash
colcon build --cmake-args -DUSE_GPIO=ON
```

### Test LED Control
```bash
pigs w 4 1   # Green LED on  (BCM 4)
pigs w 4 0   # Green LED off
pigs w 15 1  # Red LED on    (BCM 15)
pigs w 15 0  # Red LED off
```

### Monitor Shutdown Switch
```bash
watch -n 0.1 'pigs r 2'
```

### Check Permissions
```bash
ls -l /dev/gpiochip* && groups
systemctl status pigpiod
```
