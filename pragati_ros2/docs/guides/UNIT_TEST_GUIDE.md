# Unit Testing Guide - Pragati ROS2

**Last Updated:** 2025-10-15  
**Status:** Framework Documentation Complete  
**Target Coverage:** 70%+

---

## Overview

This guide documents the unit test framework and strategy for Pragati ROS2. While test implementation is ongoing, the framework and structure are defined here for consistent test development.

---

## Test Framework

### Technology Stack

| Component | Framework | Purpose |
|-----------|-----------|---------|
| **C++ Unit Tests** | Google Test (gtest) | Core component testing |
| **ROS2 Integration** | `ament_cmake_gtest` | ROS2-aware tests |
| **Python Tests** | pytest | Python node/script testing |
| **Coverage** | gcov/lcov | Code coverage analysis |
| **CI/CD** | GitHub Actions (planned) | Automated testing |

---

## Test Structure

### Directory Layout

```
src/<package>/
├── src/                    # Source code
├── include/<package>/      # Headers
├── test/                   # Test directory
│   ├── unit/              # Unit tests
│   │   ├── test_<component>.cpp
│   │   └── CMakeLists.txt
│   ├── integration/       # Integration tests
│   │   └── test_<workflow>.cpp
│   └── fixtures/          # Test data
│       ├── sample_images/
│       └── mock_configs/
└── CMakeLists.txt         # Main build file
```

---

## Unit Test Templates

### C++ Component Test Template

```cpp
// test/unit/test_motor_controller.cpp
#include <gtest/gtest.h>
#include "motor_control_ros2/mg6010_motor_controller.hpp"

class MG6010ControllerTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Initialize test fixtures
        controller = std::make_shared<MG6010MotorController>();
    }

    void TearDown() override {
        // Cleanup
        controller.reset();
    }

    std::shared_ptr<MG6010MotorController> controller;
};

TEST_F(MG6010ControllerTest, InitializationTest) {
    ASSERT_NE(controller, nullptr);
    EXPECT_FALSE(controller->isInitialized());
}

TEST_F(MG6010ControllerTest, PositionCommandTest) {
    double target_position = 1.5;  // radians
    controller->setTargetPosition(target_position);
    
    EXPECT_NEAR(controller->getTargetPosition(), target_position, 0.001);
}

TEST_F(MG6010ControllerTest, SafetyLimitTest) {
    double excessive_position = 10.0;  // Beyond limits
    
    EXPECT_THROW(
        controller->setTargetPosition(excessive_position),
        std::out_of_range
    );
}
```

### ROS2 Node Test Template

```cpp
// test/integration/test_motor_control_node.cpp
#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include "motor_control_ros2/motor_controller_node.hpp"

class MotorControlNodeTest : public ::testing::Test {
protected:
    void SetUp() override {
        rclcpp::init(0, nullptr);
        node = std::make_shared<MotorControllerNode>();
    }

    void TearDown() override {
        node.reset();
        rclcpp::shutdown();
    }

    std::shared_ptr<MotorControllerNode> node;
};

TEST_F(MotorControlNodeTest, NodeInitialization) {
    ASSERT_NE(node, nullptr);
    EXPECT_EQ(node->get_name(), "motor_controller");
}

TEST_F(MotorControlNodeTest, ParameterValidation) {
    // Test parameter loading
    auto can_bitrate = node->get_parameter("can_bitrate").as_int();
    EXPECT_EQ(can_bitrate, 500000);
}
```

---

## Test Targets by Package

### 1. motor_control_ros2

**Priority: HIGH**

**Unit Tests:**
- [ ] `test_mg6010_protocol.cpp` - Protocol encoding/decoding
  - CAN frame construction
  - Message parsing
  - Error detection
  
- [ ] `test_motor_controller.cpp` - Controller logic
  - Position control
  - Velocity control
  - Torque control
  - PID calculations
  
- [ ] `test_safety_monitor.cpp` - Safety checks
  - Position limits
  - Velocity limits
  - Temperature monitoring
  - Timeout detection
  
- [ ] `test_can_interface.cpp` - CAN communication (mocked)
  - Send/receive
  - Error handling
  - Timeout handling

**Integration Tests:**
- [ ] `test_motor_control_node.cpp` - Full node
- [ ] `test_multi_motor.cpp` - Multi-motor coordination

**Estimated Effort:** 4-6 hours

---

### 2. cotton_detection_ros2

**Priority: HIGH**

**Unit Tests:**
- [ ] `test_image_processor.cpp` - Image processing
  - HSV conversion
  - Color filtering
  - Contour detection
  
- [ ] `test_yolo_detector.cpp` - YOLO detection
  - Model loading
  - Inference
  - Bounding box extraction
  
- [ ] `test_cotton_classifier.cpp` - Pickability logic
  - Classification criteria
  - Size/shape filtering
  
- [ ] `test_depthai_manager.cpp` - Camera manager (mocked)
  - Initialization
  - Configuration
  - Frame capture (with mock)

**Integration Tests:**
- [ ] `test_detection_pipeline.cpp` - Full pipeline
- [ ] `test_offline_mode.cpp` - Offline testing mode

**Estimated Effort:** 3-4 hours

---

### 3. yanthra_move

**Priority: MEDIUM**

**Unit Tests:**
- [ ] `test_kinematics.cpp` - IK/FK calculations
- [ ] `test_trajectory_generator.cpp` - Motion planning
- [ ] `test_coordinate_transforms.cpp` - Coordinate systems

**Integration Tests:**
- [ ] `test_yanthra_move_node.cpp` - Full node
- [ ] `test_pick_place_workflow.cpp` - Complete workflow

**Estimated Effort:** 2-3 hours

---

## Test Execution

### Build with Tests

```bash
# Build all packages with tests
colcon build --symlink-install --cmake-args -DBUILD_TESTING=ON

# Build specific package tests
colcon build --packages-select motor_control_ros2 --cmake-args -DBUILD_TESTING=ON
```

### Run Tests

```bash
# Run all tests
colcon test

# Run specific package tests
colcon test --packages-select motor_control_ros2

# View test results
colcon test-result --all
colcon test-result --verbose
```

### Run Individual Test

```bash
# Run single test file
./build/motor_control_ros2/test_mg6010_protocol

# Run with gtest filters
./build/motor_control_ros2/test_mg6010_protocol --gtest_filter="*Position*"

# Run with verbose output
./build/motor_control_ros2/test_mg6010_protocol --gtest_verbose
```

---

## Coverage Analysis

### Generate Coverage Report

```bash
# Build with coverage flags
colcon build --cmake-args -DCMAKE_CXX_FLAGS="--coverage" -DCMAKE_BUILD_TYPE=Debug

# Run tests
colcon test

# Generate coverage report
lcov --capture --directory build/ --output-file coverage.info
lcov --remove coverage.info '/usr/*' '*/install/*' '*/test/*' --output-file coverage_filtered.info
genhtml coverage_filtered.info --output-directory coverage_html

# View report
xdg-open coverage_html/index.html
```

### Coverage Targets

| Package | Target | Current | Status |
|---------|--------|---------|--------|
| motor_control_ros2 | 70% | TBD | ⏳ |
| cotton_detection_ros2 | 70% | TBD | ⏳ |
| yanthra_move | 60% | TBD | ⏳ |
| robot_description | N/A | N/A | ✅ |
| vehicle_control | 50% | TBD | ⏳ |

---

## Mocking Strategy

### Hardware Mocking

**For CAN Interface:**
```cpp
class MockCANInterface : public CANInterface {
public:
    MOCK_METHOD(bool, send, (const CANFrame& frame), (override));
    MOCK_METHOD(bool, receive, (CANFrame& frame), (override));
    MOCK_METHOD(bool, isConnected, (), (const, override));
};
```

**For DepthAI Camera:**
```cpp
class MockDepthAIDevice {
public:
    std::vector<cv::Mat> mock_frames;
    int frame_index = 0;
    
    cv::Mat getFrame() {
        if (frame_index < mock_frames.size()) {
            return mock_frames[frame_index++];
        }
        return cv::Mat();
    }
};
```

---

## Test Data

### Sample Data Location

```
test/fixtures/
├── images/
│   ├── cotton_sample_1.jpg
│   ├── cotton_sample_2.jpg
│   └── no_cotton.jpg
├── configs/
│   ├── test_motors.yaml
│   └── test_camera.yaml
└── can_traces/
    ├── motor_response_ok.bin
    └── motor_response_error.bin
```

### Generating Test Data

```bash
# Capture cotton images for testing
ros2 run cotton_detection_ros2 capture_test_images

# Record CAN traces (when hardware available)
candump can0 > test/fixtures/can_traces/real_motor.log
```

---

## CI/CD Integration (Planned)

### GitHub Actions Workflow

```yaml
name: ROS2 Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v3
      
      - name: Install ROS2 Jazzy
        run: |
          sudo apt update
          sudo apt install ros-jazzy-desktop
          
      - name: Install Dependencies
        run: |
          source /opt/ros/jazzy/setup.bash
          rosdep install --from-paths src --ignore-src -y
          
      - name: Build
        run: |
          source /opt/ros/jazzy/setup.bash
          colcon build --cmake-args -DBUILD_TESTING=ON
          
      - name: Test
        run: |
          source /opt/ros/jazzy/setup.bash
          source install/setup.bash
          colcon test
          colcon test-result --verbose
          
      - name: Coverage
        run: |
          lcov --capture --directory build/ --output-file coverage.info
          bash <(curl -s https://codecov.io/bash)
```

---

## Best Practices

### Test Writing Guidelines

1. **AAA Pattern:** Arrange, Act, Assert
   ```cpp
   // Arrange: Set up test conditions
   double target = 1.5;
   
   // Act: Execute the code under test
   controller->setPosition(target);
   
   // Assert: Verify the results
   EXPECT_NEAR(controller->getPosition(), target, 0.01);
   ```

2. **One Assertion Per Test (Generally)**
   - Each test should verify one behavior
   - Use descriptive test names

3. **Test Edge Cases**
   - Zero values
   - Negative values
   - Maximum values
   - Invalid inputs

4. **Avoid Test Interdependence**
   - Each test should be independent
   - Use Setup/TearDown for shared state

5. **Mock External Dependencies**
   - Hardware interfaces
   - Network calls
   - File I/O

---

## Common Patterns

### Testing Exceptions

```cpp
TEST(SafetyTest, ThrowsOnInvalidPosition) {
    EXPECT_THROW(
        controller->setPosition(999.0),
        std::out_of_range
    );
}
```

### Testing Floating Point

```cpp
TEST(ControlTest, PIDCalculation) {
    double result = controller->calculatePID(1.0, 0.5);
    EXPECT_NEAR(result, 0.75, 0.001);  // Use NEAR for floats
}
```

### Testing Callbacks

```cpp
TEST(NodeTest, CallbackExecution) {
    bool callback_called = false;
    
    auto callback = [&](const auto& msg) {
        callback_called = true;
    };
    
    node->setCallback(callback);
    node->processMessage(test_msg);
    
    EXPECT_TRUE(callback_called);
}
```

---

## Running Tests During Development

### Quick Workflow

```bash
# 1. Make code changes
vim src/motor_control_ros2/src/motor_controller.cpp

# 2. Build only changed package
colcon build --packages-select motor_control_ros2 --cmake-args -DBUILD_TESTING=ON

# 3. Run tests
colcon test --packages-select motor_control_ros2

# 4. Check results
colcon test-result --verbose | grep motor_control_ros2
```

---

## Test Maintenance

### When to Update Tests

- [ ] After adding new features
- [ ] After fixing bugs (add regression test)
- [ ] When refactoring (tests should still pass)
- [ ] When changing APIs (update interface tests)

### Test Review Checklist

- [ ] All tests pass
- [ ] No skipped tests (unless documented)
- [ ] Coverage meets target (70%+)
- [ ] No hardcoded values (use constants/fixtures)
- [ ] Tests are deterministic (no randomness)
- [ ] Test names are descriptive

---

## Next Steps

### Immediate (2-3 hours)

1. Create CMakeLists.txt test configuration for each package
2. Implement protocol encoding/decoding tests (motor_control)
3. Implement image processing tests (cotton_detection)
4. Set up test fixtures directory

### Short Term (1 week)

1. Achieve 50% coverage on motor_control_ros2
2. Achieve 50% coverage on cotton_detection_ros2
3. Add integration tests
4. Set up coverage reporting

### Long Term (1 month)

1. Achieve 70%+ coverage on all packages
2. Integrate with CI/CD
3. Add performance benchmarking tests
4. Create automated regression suite

---

## Related Documentation

- **Motor Control README:** [src/motor_control_ros2/README.md](../../src/motor_control_ros2/README.md)
- **Cotton Detection README:** [src/cotton_detection_ros2/README.md](../../src/cotton_detection_ros2/README.md)
- **Troubleshooting:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

**Document Version:** 1.0  
**Status:** Framework Complete, Implementation Pending  
**Next Review:** After first test suite implementation
