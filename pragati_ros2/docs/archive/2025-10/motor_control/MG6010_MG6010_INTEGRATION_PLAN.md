# MG6010 Integration Plan - Complete Implementation

**Goal**: Enable MG6010-i6 motors to work in both standalone and fully integrated modes within the robot application.

---

## Current Status

### ✅ What Works
- MG6010Protocol class (low-level CAN protocol)
- mg6010_test_node (standalone testing)
- Test scripts and documentation
- Motor abstraction framework ready

### ❌ What's Missing
- MG6010CANInterface wrapper
- MG6010Controller bridge class
- Integration with yanthra_move
- Configuration examples

---

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Robot Application                         │
│                     (yanthra_move)                           │
└───────────────────────────┬─────────────────────────────────┘
                            │ Uses
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              MotorControllerInterface (Abstract)             │
│  - set_position(), set_velocity(), get_status()             │
└───────────┬────────────────────────────────┬────────────────┘
            │                                │
            ▼                                ▼
┌───────────────────────┐      ┌───────────────────────────┐
│   ODriveController    │      │  MG6010Controller ⭐ NEW  │
│   (Existing)          │      │  (To Be Created)          │
└───────────┬───────────┘      └───────────┬───────────────┘
            │                              │ Uses
            ▼                              ▼
┌───────────────────────┐      ┌───────────────────────────┐
│  ODriveCANInterface   │      │ MG6010CANInterface ⭐ NEW │
│  (Existing)           │      │ (Wrapper for sockets)     │
└───────────────────────┘      └───────────┬───────────────┘
                                           │ Uses
                                           ▼
                               ┌───────────────────────────┐
                               │   MG6010Protocol ✅ Done  │
                               │   (CAN Protocol Layer)    │
                               └───────────────────────────┘
```

---

## Implementation Plan (10 Steps)

### Step 1: Create MG6010CANInterface
**File**: `src/odrive_control_ros2/src/mg6010_can_interface.cpp`  
**Header**: `include/odrive_control_ros2/mg6010_can_interface.hpp`

**Purpose**: Lightweight wrapper implementing `CANInterface` abstract class.

**Key Methods**:
```cpp
class MG6010CANInterface : public CANInterface {
public:
  bool initialize(const std::string& interface_name, uint32_t baud_rate) override;
  bool send_message(uint32_t id, const std::vector<uint8_t>& data) override;
  bool receive_message(uint32_t& id, std::vector<uint8_t>& data, int timeout_ms) override;
  bool configure_node(uint8_t node_id, uint32_t baud_rate) override;
  bool is_connected() const override;
  std::string get_last_error() const override;
  
private:
  int can_socket_;
  std::string interface_name_;
  bool connected_;
  std::string last_error_;
};
```

**Implementation Notes**:
- Reuse socket code patterns from MG6010Protocol
- Simple pass-through to Linux SocketCAN
- No complex logic needed

---

### Step 2: Create MG6010Controller Header
**File**: `include/odrive_control_ros2/mg6010_controller.hpp`

**Purpose**: Implement MotorControllerInterface using MG6010Protocol.

**Key Components**:
```cpp
class MG6010Controller : public MotorControllerInterface {
public:
  MG6010Controller();
  virtual ~MG6010Controller();
  
  // MotorControllerInterface implementation
  bool initialize(const MotorConfiguration& config, 
                  std::shared_ptr<CANInterface> can_interface) override;
  bool configure(const MotorConfiguration& config) override;
  bool set_enabled(bool enable) override;
  
  bool set_position(double position, double velocity, double torque) override;
  bool set_velocity(double velocity, double torque) override;
  bool set_torque(double torque) override;
  
  double get_position() override;
  double get_velocity() override;
  double get_torque() override;
  
  bool home_motor(const HomingConfig* config) override;
  bool is_homed() const override;
  
  MotorStatus get_status() override;
  bool emergency_stop() override;
  bool clear_errors() override;
  bool calibrate_motor() override;
  
  const MotorConfiguration& get_configuration() const override;
  
  // Error handling (from ErrorFramework)
  const ErrorFramework::ErrorInfo& get_error_info() const override;
  std::vector<ErrorFramework::ErrorInfo> get_error_history() const override;
  ErrorFramework::RecoveryResult attempt_error_recovery() override;
  void set_error_handler(std::function<void(const ErrorFramework::ErrorInfo&)> handler) override;
  
private:
  MotorConfiguration config_;
  std::shared_ptr<MG6010Protocol> protocol_;
  std::shared_ptr<CANInterface> can_interface_;
  
  bool initialized_;
  bool homed_;
  bool enabled_;
  
  // Position tracking
  double current_position_;    // Radians (joint space)
  double current_velocity_;    // Rad/s (joint space)
  double current_torque_;      // Nm
  
  // Conversion helpers
  double motor_to_joint_position(double motor_pos);
  double joint_to_motor_position(double joint_pos);
  double motor_to_joint_velocity(double motor_vel);
  double joint_to_motor_velocity(double joint_vel);
  
  // State management
  void update_cached_state();
  bool check_safety_limits(double position, double velocity);
  
  // Error handling
  ErrorFramework::ErrorInfo current_error_;
  std::vector<ErrorFramework::ErrorInfo> error_history_;
  std::function<void(const ErrorFramework::ErrorInfo&)> error_handler_;
  
  std::mutex state_mutex_;
};
```

---

### Step 3: Implement MG6010Controller
**File**: `src/odrive_control_ros2/src/mg6010_controller.cpp`

**Key Implementation Details**:

#### A. Initialization
```cpp
bool MG6010Controller::initialize(
    const MotorConfiguration& config,
    std::shared_ptr<CANInterface> can_interface) {
  
  config_ = config;
  can_interface_ = can_interface;
  
  // Create MG6010Protocol instance
  protocol_ = std::make_shared<MG6010Protocol>(
    can_interface_, 
    config_.can_id,
    3  // retries
  );
  
  initialized_ = true;
  return true;
}
```

#### B. Position Control
```cpp
bool MG6010Controller::set_position(double position, double velocity, double torque) {
  std::lock_guard<std::mutex> lock(state_mutex_);
  
  if (!initialized_ || !enabled_) {
    return false;
  }
  
  // Convert joint space to motor space
  double motor_position = joint_to_motor_position(position);
  double motor_velocity = joint_to_motor_velocity(velocity);
  
  // Check safety limits
  if (!check_safety_limits(position, velocity)) {
    return false;
  }
  
  // Send command via protocol
  return protocol_->sendPositionCommand4(motor_position, motor_velocity);
}
```

#### C. State Reading
```cpp
double MG6010Controller::get_position() {
  std::lock_guard<std::mutex> lock(state_mutex_);
  
  double motor_angle = 0.0;
  uint16_t raw_current = 0;
  uint16_t raw_speed = 0;
  uint16_t encoder = 0;
  
  if (protocol_->readAngleCommand(motor_angle, raw_current, raw_speed, encoder)) {
    current_position_ = motor_to_joint_position(motor_angle);
  }
  
  return current_position_;
}
```

#### D. Coordinate Conversions
```cpp
double MG6010Controller::joint_to_motor_position(double joint_pos) {
  // Apply transmission factor, direction, offset
  return (joint_pos - config_.joint_offset) * 
         config_.transmission_factor * 
         config_.direction;
}

double MG6010Controller::motor_to_joint_position(double motor_pos) {
  // Inverse transformation
  return (motor_pos / config_.direction / config_.transmission_factor) + 
         config_.joint_offset;
}
```

---

### Step 4: Update CMakeLists.txt

Add to `src/odrive_control_ros2/CMakeLists.txt`:

```cmake
# Add MG6010 CAN interface to MG6010 library
target_sources(${PROJECT_NAME}_mg6010 PRIVATE
  src/mg6010_can_interface.cpp
)

# Create motor abstraction library (needed for MG6010Controller)
add_library(${PROJECT_NAME}_motor_abstraction SHARED
  src/motor_abstraction.cpp
  src/motor_parameter_mapping.cpp
  src/mg6010_controller.cpp
)

target_link_libraries(${PROJECT_NAME}_motor_abstraction
  ${PROJECT_NAME}_mg6010
)

ament_target_dependencies(${PROJECT_NAME}_motor_abstraction
  rclcpp
  std_msgs
)

# Install the motor abstraction library
install(TARGETS ${PROJECT_NAME}_motor_abstraction
  DESTINATION lib
)
```

---

### Step 5: Create Integrated Test Node
**File**: `src/odrive_control_ros2/src/mg6010_integrated_test_node.cpp`

**Purpose**: Test MG6010Controller through MotorControllerInterface.

```cpp
int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("mg6010_integrated_test");
  
  // Create CAN interface
  auto can_interface = std::make_shared<MG6010CANInterface>();
  can_interface->initialize("can0", 1000000);
  
  // Create motor configuration
  MotorConfiguration config;
  config.motor_type = "mg6010";
  config.joint_name = "test_joint";
  config.can_id = 1;
  config.transmission_factor = 1.0;
  config.direction = 1;
  
  // Create controller via interface
  auto controller = std::make_shared<MG6010Controller>();
  
  if (!controller->initialize(config, can_interface)) {
    RCLCPP_ERROR(node->get_logger(), "Failed to initialize controller");
    return 1;
  }
  
  // Enable motor
  RCLCPP_INFO(node->get_logger(), "Enabling motor...");
  controller->set_enabled(true);
  
  // Test position command
  RCLCPP_INFO(node->get_logger(), "Sending position command...");
  controller->set_position(1.57, 0.0, 0.0);  // 90 degrees
  
  // Read status
  auto status = controller->get_status();
  RCLCPP_INFO(node->get_logger(), "Position: %.3f rad, Velocity: %.3f rad/s", 
              controller->get_position(), controller->get_velocity());
  
  rclcpp::shutdown();
  return 0;
}
```

---

### Step 6: Update motor_controller_integration.cpp

Verify factory pattern works:

```cpp
std::shared_ptr<MotorControllerInterface> 
MotorControllerIntegration::createMotorController(
    const MotorConfiguration& config) {
  
  if (config.motor_type == "odrive") {
    return std::make_shared<ODriveController>();
  } else if (config.motor_type == "mg6010") {
    return std::make_shared<MG6010Controller>();  // ⭐ Now exists!
  } else {
    RCLCPP_ERROR(node_->get_logger(), "Unsupported motor type: %s", 
                 config.motor_type.c_str());
    return nullptr;
  }
}
```

---

### Step 7: Create Configuration Example
**File**: `config/mg6010_robot_config.yaml`

```yaml
motor_controllers:
  - joint_name: "joint2"
    motor_type: "mg6010"
    can_id: 1
    axis_id: 0
    
    # Mechanical configuration
    transmission_factor: 50.0  # 50:1 gear ratio
    joint_offset: 0.0
    encoder_offset: 0.0
    encoder_resolution: 16384
    direction: 1
    
    # Control parameters
    p_gain: 100.0
    v_gain: 0.5
    v_int_gain: 1.0
    current_limit: 8.0
    velocity_limit: 15.0
    
    # Safety limits
    limits:
      position_min: -3.14
      position_max: 3.14
      velocity_max: 15.0
      current_max: 8.0
      temperature_max: 85.0
    
    # MG6010-specific parameters
    motor_params:
      baud_rate: 1000000
      can_interface: "can0"
      timeout_ms: 10
      
  - joint_name: "joint3"
    motor_type: "odrive"  # Mix ODrive and MG6010!
    can_id: 2
    # ... ODrive config ...
```

---

### Step 8: Build and Test

```bash
cd /home/uday/Downloads/pragati_ros2
colcon build --packages-select odrive_control_ros2
source install/setup.bash
```

---

### Step 9: Create Integration Test Script
**File**: `scripts/test_mg6010_integration.sh`

```bash
#!/bin/bash
# Test both standalone and integrated modes

echo "MG6010 Integration Test Suite"
echo "=============================="

# Setup CAN
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up

# Test 1: Standalone mode
echo "Test 1: Standalone mode (mg6010_test_node)"
ros2 run odrive_control_ros2 mg6010_test_node --ros-args \
  -p mode:=status -p node_id:=1 &
PID1=$!
sleep 2
kill $PID1

# Test 2: Integrated mode
echo "Test 2: Integrated mode (mg6010_integrated_test_node)"
ros2 run odrive_control_ros2 mg6010_integrated_test_node &
PID2=$!
sleep 2
kill $PID2

# Test 3: Via yanthra_move (if configured)
echo "Test 3: Full robot integration"
# ros2 launch yanthra_move robot.launch.py config:=mg6010_robot_config.yaml

echo "Integration tests complete!"
```

---

### Step 10: Update Documentation

Update `docs/MG6010_INTEGRATION_README.md` with:
- Using MG6010Controller in robot applications
- Configuration examples for mixed motor setups
- Integration testing procedures
- Troubleshooting guide

---

## Testing Strategy

### Level 1: Standalone (Already Works)
```bash
ros2 run odrive_control_ros2 mg6010_test_node --ros-args -p mode:=status
```

### Level 2: Controller Interface
```bash
ros2 run odrive_control_ros2 mg6010_integrated_test_node
```

### Level 3: Robot Application
```bash
ros2 launch yanthra_move robot.launch.py config:=mg6010_robot_config.yaml
```

---

## Expected Timeline

1. **Steps 1-3** (Classes): ~30 minutes implementation
2. **Step 4** (Build): ~5 minutes
3. **Steps 5-6** (Testing): ~15 minutes
4. **Steps 7-10** (Documentation): ~10 minutes

**Total**: ~60 minutes for complete integration

---

## Success Criteria

✅ Code compiles without errors  
✅ mg6010_integrated_test_node runs successfully  
✅ Can create MG6010Controller via factory pattern  
✅ Position commands work through MotorControllerInterface  
✅ Status reading works correctly  
✅ Configuration file loads and initializes MG6010 motors  
✅ Can mix ODrive and MG6010 motors in same robot  

---

## Risk Mitigation

**Risk**: Breaking existing ODrive code  
**Mitigation**: All MG6010 code isolated, ODrive paths untouched

**Risk**: CAN interface conflicts  
**Mitigation**: Use separate CAN interfaces (can0/can1) or proper filtering

**Risk**: Coordinate transformation errors  
**Mitigation**: Unit tests for conversion functions, validate with known positions

**Risk**: Thread safety issues  
**Mitigation**: Use mutex for all state access, follow existing patterns

---

## Next Actions

Ready to proceed? I will:
1. Create MG6010CANInterface class
2. Create MG6010Controller header and implementation
3. Update build system
4. Create integrated test node
5. Update documentation

Shall I begin?
