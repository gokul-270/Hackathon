#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <rcl_interfaces/msg/parameter_descriptor.hpp>
#include <rcl_interfaces/msg/floating_point_range.hpp>
#include <rcl_interfaces/msg/integer_range.hpp>
#include <memory>

namespace motor_control_ros2
{

class ParameterValidationTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        rclcpp::init(0, nullptr);
        node_ = std::make_shared<rclcpp::Node>("test_param_validation");
    }

    void TearDown() override
    {
        node_.reset();
        rclcpp::shutdown();
    }

    std::shared_ptr<rclcpp::Node> node_;
};

// Test: Declare parameter with range descriptor
TEST_F(ParameterValidationTest, DeclareParameterWithRange)
{
    rcl_interfaces::msg::ParameterDescriptor descriptor;
    descriptor.description = "Test velocity limit parameter";

    rcl_interfaces::msg::FloatingPointRange range;
    range.from_value = 0.0;
    range.to_value = 10.0;
    range.step = 0.1;
    descriptor.floating_point_range.push_back(range);

    EXPECT_NO_THROW({
        node_->declare_parameter("velocity_limit", 5.0, descriptor);
    });

    // Verify parameter is declared
    EXPECT_TRUE(node_->has_parameter("velocity_limit"));

    // Get parameter value
    double velocity = node_->get_parameter("velocity_limit").as_double();
    EXPECT_DOUBLE_EQ(velocity, 5.0);
}

// Test: Integer parameter with range
TEST_F(ParameterValidationTest, IntegerParameterWithRange)
{
    rcl_interfaces::msg::ParameterDescriptor descriptor;
    descriptor.description = "Motor ID parameter";

    rcl_interfaces::msg::IntegerRange range;
    range.from_value = 1;
    range.to_value = 32;
    range.step = 1;
    descriptor.integer_range.push_back(range);

    EXPECT_NO_THROW({
        node_->declare_parameter("motor_id", 1, descriptor);
    });

    EXPECT_TRUE(node_->has_parameter("motor_id"));
    int motor_id = node_->get_parameter("motor_id").as_int();
    EXPECT_EQ(motor_id, 1);
}

// Test: Set parameter within range
TEST_F(ParameterValidationTest, SetParameterWithinRange)
{
    // Declare with range
    rcl_interfaces::msg::ParameterDescriptor descriptor;
    rcl_interfaces::msg::FloatingPointRange range;
    range.from_value = 0.0;
    range.to_value = 100.0;
    descriptor.floating_point_range.push_back(range);

    node_->declare_parameter("max_current", 10.0, descriptor);

    // Set to valid value
    EXPECT_NO_THROW({
        node_->set_parameter(rclcpp::Parameter("max_current", 50.0));
    });

    double current = node_->get_parameter("max_current").as_double();
    EXPECT_DOUBLE_EQ(current, 50.0);
}

// Test: Read-only parameter
TEST_F(ParameterValidationTest, ReadOnlyParameter)
{
    rcl_interfaces::msg::ParameterDescriptor descriptor;
    descriptor.description = "Read-only CAN bitrate";
    descriptor.read_only = true;

    EXPECT_NO_THROW({
        node_->declare_parameter("can_bitrate", 500000, descriptor);
    });

    int bitrate = node_->get_parameter("can_bitrate").as_int();
    EXPECT_EQ(bitrate, 500000);
}

// Test: String parameter validation
TEST_F(ParameterValidationTest, StringParameter)
{
    rcl_interfaces::msg::ParameterDescriptor descriptor;
    descriptor.description = "CAN interface name";

    EXPECT_NO_THROW({
        node_->declare_parameter("can_interface", "can0", descriptor);
    });

    std::string interface = node_->get_parameter("can_interface").as_string();
    EXPECT_EQ(interface, "can0");
}

// Test: Boolean parameter
TEST_F(ParameterValidationTest, BooleanParameter)
{
    rcl_interfaces::msg::ParameterDescriptor descriptor;
    descriptor.description = "Enable GPIO control";

    EXPECT_NO_THROW({
        node_->declare_parameter("enable_gpio", true, descriptor);
    });

    bool enabled = node_->get_parameter("enable_gpio").as_bool();
    EXPECT_TRUE(enabled);
}

// Test: Array parameter
TEST_F(ParameterValidationTest, ArrayParameter)
{
    std::vector<double> joint_limits = {-3.14, -2.0, -1.5, -1.0};

    rcl_interfaces::msg::ParameterDescriptor descriptor;
    descriptor.description = "Joint position limits";

    EXPECT_NO_THROW({
        node_->declare_parameter("joint_limits", joint_limits, descriptor);
    });

    auto limits = node_->get_parameter("joint_limits").as_double_array();
    EXPECT_EQ(limits.size(), 4u);
    EXPECT_DOUBLE_EQ(limits[0], -3.14);
}

// Test: Parameter callback handling
TEST_F(ParameterValidationTest, ParameterCallbackHandling)
{
    node_->declare_parameter("test_value", 1.0);

    bool callback_called = false;

    // Set parameter change callback
    auto callback = [&callback_called](const std::vector<rclcpp::Parameter> & parameters) {
        (void)parameters;  // Suppress unused parameter warning in test
        callback_called = true;
        return rcl_interfaces::msg::SetParametersResult();
    };

    auto callback_handle = node_->add_on_set_parameters_callback(callback);

    // Change parameter
    node_->set_parameter(rclcpp::Parameter("test_value", 2.0));

    EXPECT_TRUE(callback_called);
}

// Test: Multiple parameters declared
TEST_F(ParameterValidationTest, MultipleParameterDeclaration)
{
    rcl_interfaces::msg::ParameterDescriptor desc1;
     desc1.description = "Angle KP gain";

    rcl_interfaces::msg::ParameterDescriptor desc2;
    desc2.description = "Angle KI gain";

    rcl_interfaces::msg::ParameterDescriptor desc3;
    desc3.description = "Position KD gain";

    EXPECT_NO_THROW({
        node_->declare_parameter("angle_kp", 10.0, desc1);
        node_->declare_parameter("angle_ki", 0.5, desc2);
        node_->declare_parameter("position_kd", 1.0, desc3);
    });

    EXPECT_TRUE(node_->has_parameter("angle_kp"));
    EXPECT_TRUE(node_->has_parameter("angle_ki"));
    EXPECT_TRUE(node_->has_parameter("position_kd"));
}

// Test: Get all parameters
TEST_F(ParameterValidationTest, GetAllParameters)
{
    node_->declare_parameter("param1", 1);
    node_->declare_parameter("param2", 2);
    node_->declare_parameter("param3", 3);

    auto all_params = node_->list_parameters({}, 0);

    // Should have at least our 3 parameters (plus any built-in ones)
    EXPECT_GE(all_params.names.size(), 3u);
}

// Test: Parameter type consistency
TEST_F(ParameterValidationTest, ParameterTypeConsistency)
{
    node_->declare_parameter("int_param", 42);

    // Get as int
    int value_int = node_->get_parameter("int_param").as_int();
    EXPECT_EQ(value_int, 42);

    // Parameter type should be integer
    auto param_type = node_->get_parameter("int_param").get_type();
    EXPECT_EQ(param_type, rclcpp::ParameterType::PARAMETER_INTEGER);
}

// Test: Undeclared parameter handling
TEST_F(ParameterValidationTest, UndeclaredParameterHandling)
{
    // Attempting to get undeclared parameter should throw
    EXPECT_THROW({
        node_->get_parameter("nonexistent_param");
    }, rclcpp::exceptions::ParameterNotDeclaredException);
}

} // namespace motor_control_ros2
