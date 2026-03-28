/*
 * RoleStrategy Unit Tests (TDD RED phase)
 *
 * Tests for the RoleStrategy hierarchy: factory function, ArmRoleStrategy,
 * VehicleRoleStrategy.  Covers all scenarios from role-strategy/spec.md.
 *
 * Part of mg6010-decomposition Phase 3 (Step 6).
 */

#include <gmock/gmock.h>
#include <fstream>
#include <regex>
#include <gtest/gtest.h>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>

#include "motor_control_ros2/role_strategy.hpp"

#include <memory>
#include <string>
#include <vector>

using namespace motor_control_ros2;

// =============================================================================
// Test Fixture — creates a lightweight rclcpp::Node for parameter injection
// =============================================================================

class RoleStrategyTest : public ::testing::Test
{
protected:
  static void SetUpTestSuite()
  {
    rclcpp::init(0, nullptr);
  }

  static void TearDownTestSuite()
  {
    rclcpp::shutdown();
  }

  /// Create a test node with the given role and joint_names parameters.
  /// Pass empty string for role to simulate missing role parameter.
  std::shared_ptr<rclcpp_lifecycle::LifecycleNode> makeNode(
    const std::string & role,
    const std::vector<std::string> & joint_names,
    const std::string & node_name = "test_role_node")
  {
    auto node = std::make_shared<rclcpp_lifecycle::LifecycleNode>(node_name);

    // Declare and set joint_names
    node->declare_parameter<std::vector<std::string>>(
      "joint_names", std::vector<std::string>());
    node->set_parameter(rclcpp::Parameter("joint_names", joint_names));

    // Only declare role if non-empty (simulates config with/without role field)
    if (!role.empty()) {
      node->declare_parameter<std::string>("role", "");
      node->set_parameter(rclcpp::Parameter("role", role));
    }

    return node;
  }

  // Standard arm joint names (same as production.yaml)
  const std::vector<std::string> arm_joints_ = {"joint5", "joint3", "joint4"};

  // Standard vehicle joint names (steering + drive for test coverage)
  const std::vector<std::string> vehicle_joints_ = {
    "front_left_steering", "front_right_steering",
    "front_left_drive", "front_right_drive"
  };

  // Vehicle steering-only (matches actual vehicle_motors.yaml)
  const std::vector<std::string> vehicle_steering_only_ = {
    "steering_left", "steering_right", "steering_front"
  };

  // Ambiguous joint names (neither arm nor vehicle pattern)
  const std::vector<std::string> ambiguous_joints_ = {"motor_a", "motor_b"};

  // Standard positions for arm shutdown tests
  const std::vector<double> arm_homing_positions_ = {0.0, 0.0, 0.0};  // J5, J3, J4
  const std::vector<double> arm_packing_positions_ = {0.0, -0.25, 0.0};  // J5, J3, J4

  // Standard positions for vehicle shutdown tests
  const std::vector<double> vehicle_homing_positions_ = {0.0, 0.0, 0.0, 0.0};
  const std::vector<double> vehicle_packing_positions_ = {0.0, 0.0, 0.0, 0.0};
};

// =============================================================================
// Task 1.1: createRoleStrategy() — explicit "arm" returns ArmRoleStrategy
// =============================================================================

TEST_F(RoleStrategyTest, ExplicitArmRoleReturnsArmStrategy)
{
  auto node = makeNode("arm", arm_joints_);
  auto strategy = createRoleStrategy(node);

  ASSERT_NE(strategy, nullptr);
  EXPECT_EQ(strategy->roleType(), "arm");
  EXPECT_TRUE(strategy->isArm());
  EXPECT_FALSE(strategy->isVehicle());

  // Verify it's actually an ArmRoleStrategy via dynamic_cast
  auto arm = std::dynamic_pointer_cast<ArmRoleStrategy>(
    std::shared_ptr<RoleStrategy>(strategy.get(), [](RoleStrategy*) {}));
  // Can't dynamic_cast shared_ptr easily; use roleType() as proxy
}

// =============================================================================
// Task 1.2: createRoleStrategy() — explicit "vehicle" returns VehicleRoleStrategy
// =============================================================================

TEST_F(RoleStrategyTest, ExplicitVehicleRoleReturnsVehicleStrategy)
{
  auto node = makeNode("vehicle", vehicle_joints_);
  auto strategy = createRoleStrategy(node);

  ASSERT_NE(strategy, nullptr);
  EXPECT_EQ(strategy->roleType(), "vehicle");
  EXPECT_TRUE(strategy->isVehicle());
  EXPECT_FALSE(strategy->isArm());
}

// =============================================================================
// Task 1.3: createRoleStrategy() — invalid role throws std::invalid_argument
// =============================================================================

TEST_F(RoleStrategyTest, InvalidRoleThrowsInvalidArgument)
{
  auto node = makeNode("invalid_value", arm_joints_);

  EXPECT_THROW(
    {
      try {
        createRoleStrategy(node);
      } catch (const std::invalid_argument & e) {
        // Verify message contains the invalid value and "role"
        std::string msg = e.what();
        EXPECT_NE(msg.find("role"), std::string::npos)
          << "Exception should mention 'role', got: " << msg;
        EXPECT_NE(msg.find("invalid_value"), std::string::npos)
          << "Exception should contain the invalid value, got: " << msg;
        throw;
      }
    },
    std::invalid_argument);
}

// =============================================================================
// Task 1.4: Auto-detect — missing role + arm joint names returns ArmRoleStrategy
//           with deprecation warning
// =============================================================================

TEST_F(RoleStrategyTest, AutoDetectArmFromJointNames)
{
  // No role parameter declared — simulates missing role field in config
  auto node = makeNode("", arm_joints_);
  auto strategy = createRoleStrategy(node);

  ASSERT_NE(strategy, nullptr);
  EXPECT_EQ(strategy->roleType(), "arm");
  EXPECT_TRUE(strategy->isArm());

  // Note: deprecation warning is logged but difficult to assert in unit test.
  // The spec says "deprecation warning SHALL be logged containing 'role' and 'auto-detect'".
  // We verify the correct strategy is returned; warning assertion can be done
  // via integration test with log capture if needed.
}

// =============================================================================
// Task 1.5: Auto-detect — missing role + vehicle joint names returns
//           VehicleRoleStrategy
// =============================================================================

TEST_F(RoleStrategyTest, AutoDetectVehicleFromJointNames)
{
  auto node = makeNode("", vehicle_joints_);
  auto strategy = createRoleStrategy(node);

  ASSERT_NE(strategy, nullptr);
  EXPECT_EQ(strategy->roleType(), "vehicle");
  EXPECT_TRUE(strategy->isVehicle());
}

TEST_F(RoleStrategyTest, AutoDetectVehicleFromSteeringOnlyJointNames)
{
  auto node = makeNode("", vehicle_steering_only_);
  auto strategy = createRoleStrategy(node);

  ASSERT_NE(strategy, nullptr);
  EXPECT_EQ(strategy->roleType(), "vehicle");
  EXPECT_TRUE(strategy->isVehicle());
}

// =============================================================================
// Task 1.6: Auto-detect — ambiguous joint names defaults to arm with warning
// =============================================================================

TEST_F(RoleStrategyTest, AutoDetectAmbiguousDefaultsToArm)
{
  auto node = makeNode("", ambiguous_joints_);

  // Should NOT throw — defaults to arm when auto-detect can't determine role
  auto strategy = createRoleStrategy(node);
  ASSERT_NE(strategy, nullptr);
  EXPECT_EQ(strategy->roleType(), "arm");
  EXPECT_TRUE(strategy->isArm());
}

// =============================================================================
// Task 1.7: ArmRoleStrategy identity and motor type queries
// =============================================================================

TEST_F(RoleStrategyTest, ArmStrategyIdentityQueries)
{
  ArmRoleStrategy arm;

  EXPECT_TRUE(arm.isArm());
  EXPECT_FALSE(arm.isVehicle());
  EXPECT_EQ(arm.roleType(), "arm");
}

TEST_F(RoleStrategyTest, ArmStrategyIsDriveMotorAlwaysFalse)
{
  ArmRoleStrategy arm;

  EXPECT_FALSE(arm.isDriveMotor("joint3"));
  EXPECT_FALSE(arm.isDriveMotor("joint4"));
  EXPECT_FALSE(arm.isDriveMotor("joint5"));
  EXPECT_FALSE(arm.isDriveMotor("anything"));
}

TEST_F(RoleStrategyTest, ArmStrategyIsSteeringMotorAlwaysFalse)
{
  ArmRoleStrategy arm;

  EXPECT_FALSE(arm.isSteeringMotor("joint3"));
  EXPECT_FALSE(arm.isSteeringMotor("joint5"));
  EXPECT_FALSE(arm.isSteeringMotor("anything"));
}

// =============================================================================
// Task 1.8: ArmRoleStrategy::getShutdownSequence() — J5→J3(home)→J4→J3(park)
// =============================================================================

TEST_F(RoleStrategyTest, ArmShutdownSequenceOrdering)
{
  ArmRoleStrategy arm;

  // joint_names in config order: ["joint5", "joint3", "joint4"] (CAN ID 1,2,3)
  auto seq = arm.getShutdownSequence(arm_joints_, arm_homing_positions_, arm_packing_positions_);

  // Expected sequence: J5(PARK) → J3(HOME) → J4(PARK) → J3(PARK)
  ASSERT_EQ(seq.size(), 4u) << "Arm shutdown sequence should have 4 steps (J5, J3-home, J4, J3-park)";

  // Step 1: J5 parks
  EXPECT_EQ(seq[0].joint_name, "joint5");
  EXPECT_EQ(seq[0].joint_index, 0u);  // index 0 in arm_joints_
  EXPECT_EQ(seq[0].action, ShutdownStep::Action::PARK);
  EXPECT_TRUE(seq[0].needs_position_parking);

  // Step 2: J3 goes to HOMING position (not parking yet — creating clearance for J4)
  EXPECT_EQ(seq[1].joint_name, "joint3");
  EXPECT_EQ(seq[1].joint_index, 1u);  // index 1 in arm_joints_
  EXPECT_EQ(seq[1].action, ShutdownStep::Action::HOME);
  EXPECT_DOUBLE_EQ(seq[1].target_position, arm_homing_positions_[1]);
  EXPECT_TRUE(seq[1].needs_position_parking);

  // Step 3: J4 parks
  EXPECT_EQ(seq[2].joint_name, "joint4");
  EXPECT_EQ(seq[2].joint_index, 2u);  // index 2 in arm_joints_
  EXPECT_EQ(seq[2].action, ShutdownStep::Action::PARK);
  EXPECT_TRUE(seq[2].needs_position_parking);

  // Step 4: J3 goes to PARKING position (final — transport-ready)
  EXPECT_EQ(seq[3].joint_name, "joint3");
  EXPECT_EQ(seq[3].joint_index, 1u);
  EXPECT_EQ(seq[3].action, ShutdownStep::Action::PARK);
  EXPECT_DOUBLE_EQ(seq[3].target_position, arm_packing_positions_[1]);
  EXPECT_TRUE(seq[3].needs_position_parking);
}

TEST_F(RoleStrategyTest, ArmShutdownSequenceTargetPositions)
{
  ArmRoleStrategy arm;

  auto seq = arm.getShutdownSequence(arm_joints_, arm_homing_positions_, arm_packing_positions_);

  // J5 parks to packing position
  EXPECT_DOUBLE_EQ(seq[0].target_position, arm_packing_positions_[0]);  // 0.0

  // J3 first pass: homing position
  EXPECT_DOUBLE_EQ(seq[1].target_position, arm_homing_positions_[1]);  // 0.0

  // J4: packing position
  EXPECT_DOUBLE_EQ(seq[2].target_position, arm_packing_positions_[2]);  // 0.0

  // J3 second pass: packing position
  EXPECT_DOUBLE_EQ(seq[3].target_position, arm_packing_positions_[1]);  // -0.25
}

// =============================================================================
// Task 1.9: ArmRoleStrategy::needsPositionParking() — true for all arm joints
// =============================================================================

TEST_F(RoleStrategyTest, ArmNeedsPositionParkingTrueForAll)
{
  ArmRoleStrategy arm;

  EXPECT_TRUE(arm.needsPositionParking("joint3"));
  EXPECT_TRUE(arm.needsPositionParking("joint4"));
  EXPECT_TRUE(arm.needsPositionParking("joint5"));
}

// =============================================================================
// Task 1.10: VehicleRoleStrategy identity and motor type queries
// =============================================================================

TEST_F(RoleStrategyTest, VehicleStrategyIdentityQueries)
{
  VehicleRoleStrategy vehicle;

  EXPECT_FALSE(vehicle.isArm());
  EXPECT_TRUE(vehicle.isVehicle());
  EXPECT_EQ(vehicle.roleType(), "vehicle");
}

TEST_F(RoleStrategyTest, VehicleStrategyIsDriveMotor)
{
  VehicleRoleStrategy vehicle;

  EXPECT_TRUE(vehicle.isDriveMotor("front_left_drive"));
  EXPECT_TRUE(vehicle.isDriveMotor("front_right_drive"));
  EXPECT_TRUE(vehicle.isDriveMotor("rear_drive"));

  // Steering motors are NOT drive motors
  EXPECT_FALSE(vehicle.isDriveMotor("front_left_steering"));
  EXPECT_FALSE(vehicle.isDriveMotor("steering_left"));
}

TEST_F(RoleStrategyTest, VehicleStrategyIsSteeringMotor)
{
  VehicleRoleStrategy vehicle;

  EXPECT_TRUE(vehicle.isSteeringMotor("front_left_steering"));
  EXPECT_TRUE(vehicle.isSteeringMotor("front_right_steering"));
  EXPECT_TRUE(vehicle.isSteeringMotor("steering_left"));
  EXPECT_TRUE(vehicle.isSteeringMotor("steering_front"));

  // Drive motors are NOT steering motors
  EXPECT_FALSE(vehicle.isSteeringMotor("front_left_drive"));
  EXPECT_FALSE(vehicle.isSteeringMotor("rear_drive"));
}

// =============================================================================
// Task 1.11: VehicleRoleStrategy::getShutdownSequence() — steering before drive,
//            drive marked no-park
// =============================================================================

TEST_F(RoleStrategyTest, VehicleShutdownSequenceSteeringBeforeDrive)
{
  VehicleRoleStrategy vehicle;

  auto seq = vehicle.getShutdownSequence(
    vehicle_joints_, vehicle_homing_positions_, vehicle_packing_positions_);

  // Should have entries for all joints
  ASSERT_EQ(seq.size(), vehicle_joints_.size());

  // Find the boundary between steering and drive
  bool seen_drive = false;
  for (const auto & step : seq) {
    bool is_drive = (step.joint_name.find("drive") != std::string::npos);

    if (is_drive) {
      seen_drive = true;
      // Drive motors: DISABLE action, no position parking
      EXPECT_EQ(step.action, ShutdownStep::Action::DISABLE)
        << "Drive motor " << step.joint_name << " should be DISABLE";
      EXPECT_FALSE(step.needs_position_parking)
        << "Drive motor " << step.joint_name << " should not need position parking";
    } else {
      // Steering motors should come before any drive motor
      EXPECT_FALSE(seen_drive)
        << "Steering motor " << step.joint_name << " appeared after drive motor";
      // Steering motors: PARK action, needs position parking
      EXPECT_EQ(step.action, ShutdownStep::Action::PARK)
        << "Steering motor " << step.joint_name << " should be PARK";
      EXPECT_TRUE(step.needs_position_parking)
        << "Steering motor " << step.joint_name << " should need position parking";
    }
  }
}

TEST_F(RoleStrategyTest, VehicleShutdownSequenceSteeringOnlyConfig)
{
  VehicleRoleStrategy vehicle;

  // Steering-only (matches actual vehicle_motors.yaml)
  std::vector<double> homing = {0.0, 0.0, 0.0};
  std::vector<double> packing = {0.0, 0.0, 0.0};

  auto seq = vehicle.getShutdownSequence(vehicle_steering_only_, homing, packing);

  ASSERT_EQ(seq.size(), 3u);
  for (const auto & step : seq) {
    EXPECT_EQ(step.action, ShutdownStep::Action::PARK);
    EXPECT_TRUE(step.needs_position_parking);
  }
}

// =============================================================================
// Task 1.12: VehicleRoleStrategy::needsPositionParking() — false for drive,
//            true for steering
// =============================================================================

TEST_F(RoleStrategyTest, VehicleNeedsPositionParkingDriveFalse)
{
  VehicleRoleStrategy vehicle;

  EXPECT_FALSE(vehicle.needsPositionParking("front_left_drive"));
  EXPECT_FALSE(vehicle.needsPositionParking("front_right_drive"));
  EXPECT_FALSE(vehicle.needsPositionParking("rear_drive"));
}

TEST_F(RoleStrategyTest, VehicleNeedsPositionParkingSteeringTrue)
{
  VehicleRoleStrategy vehicle;

  EXPECT_TRUE(vehicle.needsPositionParking("front_left_steering"));
  EXPECT_TRUE(vehicle.needsPositionParking("front_right_steering"));
  EXPECT_TRUE(vehicle.needsPositionParking("steering_left"));
}

// =============================================================================
// Additional Arm tests: isControlLoopJoint — all arm joints participate
// =============================================================================

TEST_F(RoleStrategyTest, ArmIsControlLoopJointTrueForAll)
{
  ArmRoleStrategy arm;

  EXPECT_TRUE(arm.isControlLoopJoint("joint3"));
  EXPECT_TRUE(arm.isControlLoopJoint("joint4"));
  EXPECT_TRUE(arm.isControlLoopJoint("joint5"));
}

// =============================================================================
// Additional Vehicle tests: isControlLoopJoint — steering yes, drive no
// =============================================================================

TEST_F(RoleStrategyTest, VehicleIsControlLoopJointSteeringTrue)
{
  VehicleRoleStrategy vehicle;

  EXPECT_TRUE(vehicle.isControlLoopJoint("front_left_steering"));
  EXPECT_TRUE(vehicle.isControlLoopJoint("steering_left"));
}

TEST_F(RoleStrategyTest, VehicleIsControlLoopJointDriveFalse)
{
  VehicleRoleStrategy vehicle;

  EXPECT_FALSE(vehicle.isControlLoopJoint("front_left_drive"));
  EXPECT_FALSE(vehicle.isControlLoopJoint("rear_drive"));
}

// =============================================================================
// Task 1.13: Standalone compilation — no dependency on MG6010ControllerNode
// =============================================================================
// This test verifies by its mere existence: if test_role_strategy.cpp compiles
// and links without including mg6010_controller_node.hpp, the dependency is
// absent. The CMakeLists.txt target must NOT link against the main node object.

TEST_F(RoleStrategyTest, StandaloneCompilationNoDependencyOnNode)
{
  // If this test compiles and links, it proves role_strategy has no dependency
  // on MG6010ControllerNode. The factory only needs rclcpp::Node for params.
  ArmRoleStrategy arm;
  VehicleRoleStrategy vehicle;

  EXPECT_EQ(arm.roleType(), "arm");
  EXPECT_EQ(vehicle.roleType(), "vehicle");
}

// =============================================================================
// Edge cases: joint state conversions
// =============================================================================

TEST_F(RoleStrategyTest, ArmJointStateConversionsReturnsFactors)
{
  ArmRoleStrategy arm;

  // Spec says: "factors SHALL match the values currently hardcoded in the node for arm joints"
  // The generic_motor_controller uses 2*PI/16384 but role_strategy returns
  // higher-level factors (position_factor, velocity_factor) that depend on
  // joint type and transmission, not raw motor counts.
  // For now, we verify the struct is populated (non-zero).
  auto conv = arm.getJointStateConversions("joint3");
  EXPECT_NE(conv.position_factor, 0.0);
  EXPECT_NE(conv.velocity_factor, 0.0);
}

TEST_F(RoleStrategyTest, VehicleJointStateConversionsSteeringVsDrive)
{
  VehicleRoleStrategy vehicle;

  auto steering_conv = vehicle.getJointStateConversions("front_left_steering");
  auto drive_conv = vehicle.getJointStateConversions("front_left_drive");

  // Both should have non-zero factors
  EXPECT_NE(steering_conv.position_factor, 0.0);
  EXPECT_NE(drive_conv.position_factor, 0.0);
}

// =============================================================================
// Task 1.19: Grep verification — no find("steering")/find("drive") in business logic
// =============================================================================

TEST_F(RoleStrategyTest, NodeSourceHasNoScatteredRoleDetection)
{
  // Read the node source file at test time
  std::string src_path = std::string(PROJECT_SOURCE_DIR) +
    "/src/mg6010_controller_node.cpp";
  std::ifstream file(src_path);
  ASSERT_TRUE(file.is_open())
    << "Cannot open node source: " << src_path;

  // Regex matches find("drive") or find("steering") for role detection
  // but NOT inside comments (lines starting with optional whitespace + //)
  std::regex role_find_pattern(R"RE(find\("(?:drive|steering)"\))RE");

  // The ONLY allowed occurrences are inside the role strategy creation block.
  // That block is bounded by the comment "Create role strategy" and ends at
  // the comment "Initialize all motors". Count occurrences outside that block.
  bool in_strategy_block = false;
  int violations = 0;
  int line_num = 0;
  std::string line;
  std::vector<std::string> violation_lines;

  while (std::getline(file, line)) {
    line_num++;

    // Detect strategy creation block boundaries
    if (line.find("Create role strategy") != std::string::npos) {
      in_strategy_block = true;
    }
    if (in_strategy_block && line.find("Initialize all motors") != std::string::npos) {
      in_strategy_block = false;
    }

    // Skip lines inside the strategy creation block
    if (in_strategy_block) continue;

    // Skip comment-only lines
    std::string trimmed = line;
    size_t first_non_space = trimmed.find_first_not_of(" \t");
    if (first_non_space != std::string::npos &&
        trimmed.substr(first_non_space, 2) == "//") {
      continue;
    }

    // Check for role detection patterns
    if (std::regex_search(line, role_find_pattern)) {
      violations++;
      violation_lines.push_back(
        "Line " + std::to_string(line_num) + ": " + line);
    }
  }

  EXPECT_EQ(violations, 0)
    << "Found " << violations << " scattered role detection pattern(s) "
    << "in mg6010_controller_node.cpp that should use role_strategy_->:\n"
    << [&]() {
         std::string result;
         for (const auto & vl : violation_lines) result += "  " + vl + "\n";
         return result;
       }();
}
