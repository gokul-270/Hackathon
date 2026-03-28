/**
 * @file motor_controller_integration.cpp
 * @brief Implementation of motor controller integration for YanthraMove
 */

#include "yanthra_move/motor_controller_integration.hpp"
#include <fstream>
#include <yaml-cpp/yaml.h>

namespace yanthra_move {

// ===========================================
// MotorControllerIntegration Implementation
// ===========================================

MotorControllerIntegration::MotorControllerIntegration(rclcpp::Node::SharedPtr node) 
    : node_(node) {
    RCLCPP_INFO(node_->get_logger(), "Motor controller integration initialized");
}

bool MotorControllerIntegration::initialize(const std::string& config_path) {
    RCLCPP_INFO(node_->get_logger(), "Initializing motor controller integration...");
    
    // Initialize CAN interfaces first
    if (!initializeCANInterfaces()) {
        RCLCPP_ERROR(node_->get_logger(), "Failed to initialize CAN interfaces");
        return false;
    }
    
    // Load configuration or use defaults
    if (!loadConfiguration(config_path)) {
        RCLCPP_WARN(node_->get_logger(), "Using default motor configurations");
        
        // Create default configurations for all joints
        for (const auto& joint_pair : joint_to_odrive_id_) {
            const std::string& joint_name = joint_pair.first;
            int odrive_id = joint_pair.second;
            
            auto config = getDefaultConfiguration(joint_name, odrive_id);
            auto controller = createMotorController(config);
            
            if (controller) {
                motor_controllers_[joint_name] = controller;
                RCLCPP_INFO(node_->get_logger(), "Created default controller for %s", joint_name.c_str());
            } else {
                RCLCPP_ERROR(node_->get_logger(), "Failed to create controller for %s", joint_name.c_str());
                return false;
            }
        }
    }
    
    // Initialize all motor controllers
    bool all_initialized = true;
    for (auto& pair : motor_controllers_) {
        const std::string& joint_name = pair.first;
        auto& controller = pair.second;
        
        // For ODrive controllers, use ODrive CAN interface
        // For MG6010 controllers, use MG6010 CAN interface
        std::shared_ptr<motor_control_ros2::CANInterface> can_interface;
        auto config = controller->get_configuration();
        
        if (config.motor_type == "odrive") {
            can_interface = odrive_can_interface_;
        } else if (config.motor_type == "mg6010") {
            can_interface = mg6010_can_interface_;
        } else {
            can_interface = odrive_can_interface_; // Default to ODrive
        }
        
        // Update configuration with the correct CAN interface
        if (!controller->initialize(config, can_interface)) {
            RCLCPP_ERROR(node_->get_logger(), "Failed to initialize controller for %s", joint_name.c_str());
            all_initialized = false;
        } else {
            RCLCPP_INFO(node_->get_logger(), "✅ Motor controller initialized for %s", joint_name.c_str());
        }
    }
    
    if (all_initialized) {
        RCLCPP_INFO(node_->get_logger(), "✅ All motor controllers initialized successfully");
    }
    
    return all_initialized;
}

std::shared_ptr<motor_control_ros2::MotorControllerInterface> 
MotorControllerIntegration::getMotorController(const std::string& joint_name) {
    auto it = motor_controllers_.find(joint_name);
    if (it != motor_controllers_.end()) {
        return it->second;
    }
    return nullptr;
}

void MotorControllerIntegration::integrateWithJointMove(
    std::unique_ptr<joint_move>& joint2,
    std::unique_ptr<joint_move>& joint3,
    std::unique_ptr<joint_move>& joint4,
    std::unique_ptr<joint_move>& joint5) {
    
    RCLCPP_INFO(node_->get_logger(), "Integrating motor controllers with joint_move instances...");
    
    // For now, this preserves the existing joint_move functionality
    // Future enhancement: Replace joint_move instances with EnhancedJointMove
    
    // Log integration status
    std::vector<std::pair<std::string, std::unique_ptr<joint_move>&>> joints = {
        {"joint2", joint2},
        {"joint3", joint3}, 
        {"joint4", joint4},
        {"joint5", joint5}
    };
    
    for (const auto& joint_pair : joints) {
        const std::string& joint_name = joint_pair.first;
        auto controller = getMotorController(joint_name);
        
        if (controller) {
            RCLCPP_INFO(node_->get_logger(), "✅ %s integrated with %s motor controller", 
                       joint_name.c_str(), controller->get_configuration().motor_type.c_str());
        } else {
            RCLCPP_WARN(node_->get_logger(), "⚠️ No controller found for %s", joint_name.c_str());
        }
    }
}

bool MotorControllerIntegration::enableAllMotors() {
    RCLCPP_INFO(node_->get_logger(), "Enabling all motors...");
    
    bool all_enabled = true;
    for (auto& pair : motor_controllers_) {
        const std::string& joint_name = pair.first;
        auto& controller = pair.second;
        
        if (!controller->set_enabled(true)) {
            RCLCPP_ERROR(node_->get_logger(), "Failed to enable motor for %s", joint_name.c_str());
            all_enabled = false;
        } else {
            RCLCPP_INFO(node_->get_logger(), "✅ Motor enabled for %s", joint_name.c_str());
        }
    }
    
    return all_enabled;
}

bool MotorControllerIntegration::disableAllMotors() {
    RCLCPP_INFO(node_->get_logger(), "Disabling all motors...");
    
    bool all_disabled = true;
    for (auto& pair : motor_controllers_) {
        const std::string& joint_name = pair.first;
        auto& controller = pair.second;
        
        if (!controller->set_enabled(false)) {
            RCLCPP_ERROR(node_->get_logger(), "Failed to disable motor for %s", joint_name.c_str());
            all_disabled = false;
        } else {
            RCLCPP_INFO(node_->get_logger(), "✅ Motor disabled for %s", joint_name.c_str());
        }
    }
    
    return all_disabled;
}

bool MotorControllerIntegration::homeAllMotors() {
    RCLCPP_INFO(node_->get_logger(), "Homing all motors...");
    
    bool all_homed = true;
    for (auto& pair : motor_controllers_) {
        const std::string& joint_name = pair.first;
        auto& controller = pair.second;
        
        if (!controller->home_motor()) {
            RCLCPP_ERROR(node_->get_logger(), "Failed to home motor for %s", joint_name.c_str());
            all_homed = false;
        } else {
            RCLCPP_INFO(node_->get_logger(), "✅ Motor homed for %s", joint_name.c_str());
        }
    }
    
    return all_homed;
}

void MotorControllerIntegration::emergencyStopAll() {
    RCLCPP_ERROR(node_->get_logger(), "🚨 EMERGENCY STOP - All motors stopping immediately!");
    
    for (auto& pair : motor_controllers_) {
        const std::string& joint_name = pair.first;
        auto& controller = pair.second;
        
        controller->emergency_stop();
        RCLCPP_ERROR(node_->get_logger(), "⛔ Emergency stop executed for %s", joint_name.c_str());
    }
}

std::map<std::string, motor_control_ros2::MotorStatus> 
MotorControllerIntegration::getAllMotorStatus() {
    std::map<std::string, motor_control_ros2::MotorStatus> status_map;
    
    for (auto& pair : motor_controllers_) {
        const std::string& joint_name = pair.first;
        auto& controller = pair.second;
        
        status_map[joint_name] = controller->get_status();
    }
    
    return status_map;
}

bool MotorControllerIntegration::areAllMotorsHealthy() {
    auto status_map = getAllMotorStatus();
    
    for (const auto& pair : status_map) {
        const std::string& joint_name = pair.first;
        const auto& status = pair.second;
        
        if (status.error_code != 0) {
            RCLCPP_WARN(node_->get_logger(), "Motor %s has error code: %u", 
                       joint_name.c_str(), status.error_code);
            return false;
        }
        
        if (!status.hardware_connected) {
            RCLCPP_WARN(node_->get_logger(), "Motor %s hardware not connected", joint_name.c_str());
            return false;
        }
    }
    
    return true;
}

// Private methods

bool MotorControllerIntegration::loadConfiguration(const std::string& config_path) {
    if (config_path.empty()) {
        return false; // Use defaults
    }
    
    try {
        YAML::Node yaml_config = YAML::LoadFile(config_path);
        
        if (!yaml_config["motor_controllers"]) {
            RCLCPP_WARN(node_->get_logger(), "No motor_controllers section in config file");
            return false;
        }
        
        for (const auto& joint_config : yaml_config["motor_controllers"]) {
            std::string joint_name = joint_config["joint_name"].as<std::string>();
            
            motor_control_ros2::MotorConfiguration config;
            config.joint_name = joint_name;
            config.motor_type = joint_config["motor_type"].as<std::string>("odrive");
            config.can_id = joint_config["can_id"].as<uint8_t>(0x001);
            config.axis_id = joint_config["axis_id"].as<uint8_t>(0);
            
            // Load other parameters...
            if (joint_config["transmission_factor"]) {
                config.transmission_factor = joint_config["transmission_factor"].as<double>();
            }
            
            auto controller = createMotorController(config);
            if (controller) {
                motor_controllers_[joint_name] = controller;
                RCLCPP_INFO(node_->get_logger(), "Loaded configuration for %s (%s motor)", 
                           joint_name.c_str(), config.motor_type.c_str());
            }
        }
        
        return true;
        
    } catch (const std::exception& e) {
        RCLCPP_ERROR(node_->get_logger(), "Failed to load configuration: %s", e.what());
        return false;
    }
}

std::shared_ptr<motor_control_ros2::MotorControllerInterface> 
MotorControllerIntegration::createMotorController(
    const motor_control_ros2::MotorConfiguration& config) {
    
    if (config.motor_type == "odrive") {
        return std::make_shared<motor_control_ros2::ODriveController>();
    } else if (config.motor_type == "mg6010") {
        return std::make_shared<motor_control_ros2::MG6010Controller>();
    } else {
        RCLCPP_ERROR(node_->get_logger(), "Unsupported motor type: %s", config.motor_type.c_str());
        return nullptr;
    }
}

bool MotorControllerIntegration::initializeCANInterfaces() {
    RCLCPP_INFO(node_->get_logger(), "Initializing CAN interfaces...");
    
    // Initialize ODrive CAN interface
    odrive_can_interface_ = std::make_shared<motor_control_ros2::ODriveCANInterface>();
    if (!odrive_can_interface_->initialize("can0", 1000000)) {
        RCLCPP_ERROR(node_->get_logger(), "Failed to initialize ODrive CAN interface");
        return false;
    }
    
    // Initialize MG6010 CAN interface (optional)
    mg6010_can_interface_ = std::make_shared<motor_control_ros2::MG6010CANInterface>();
    if (!mg6010_can_interface_->initialize("can1", 1000000)) {
        RCLCPP_WARN(node_->get_logger(), "MG6010 CAN interface not available (optional)");
        // Don't fail if MG6010 interface is not available
    }
    
    RCLCPP_INFO(node_->get_logger(), "✅ CAN interfaces initialized");
    return true;
}

motor_control_ros2::MotorConfiguration 
MotorControllerIntegration::getDefaultConfiguration(const std::string& joint_name, int odrive_id) {
    motor_control_ros2::MotorConfiguration config;
    
    config.joint_name = joint_name;
    config.motor_type = "mg6010"; // Default to MG6010 (current motor)
    config.can_id = static_cast<uint8_t>(odrive_id);
    config.axis_id = 0; // Default axis
    
    // Default mechanical configuration
    config.transmission_factor = 1.0;
    config.joint_offset = 0.0;
    config.encoder_offset = 0.0;
    config.encoder_resolution = 8192;
    config.direction = 1;
    
    // Default control parameters
    config.p_gain = 20.0;
    config.v_gain = 0.16;
    config.v_int_gain = 0.32;
    config.current_limit = 10.0;
    config.velocity_limit = 10.0;
    
    // Safety limits
    config.limits.position_min = -6.28; // -2π
    config.limits.position_max = 6.28;  // 2π
    config.limits.velocity_max = 10.0;
    config.limits.velocity_min = -10.0;
    config.limits.current_max = 15.0;
    config.limits.temperature_max = 80.0;
    config.limits.error_threshold = 0.1;
    
    // Homing configuration
    config.homing.method = motor_control_ros2::HomingConfig::LIMIT_SWITCH_ONLY;
    config.homing.homing_velocity = 1.0;
    config.homing.timeout_seconds = 30.0;
    
    return config;
}

// ===========================================
// EnhancedJointMove Implementation
// ===========================================

EnhancedJointMove::EnhancedJointMove(
    rclcpp::Node::SharedPtr node, 
    const std::string& name,
    std::shared_ptr<motor_control_ros2::MotorControllerInterface> motor_controller,
    int odrive_id)
    : joint_move(node, name, odrive_id), motor_controller_(motor_controller) {
    
    RCLCPP_INFO(node->get_logger(), "Enhanced joint move created for %s with %s controller", 
               name.c_str(), motor_controller_->get_configuration().motor_type.c_str());
}

void EnhancedJointMove::move_joint_enhanced(double position, bool wait) {
    if (!motor_controller_) {
        RCLCPP_ERROR(node_->get_logger(), "Motor controller not available for %s", joint_name_.c_str());
        return;
    }
    
    // Use the new motor controller instead of ODrive-specific functions
    if (!motor_controller_->set_position(position)) {
        RCLCPP_ERROR(node_->get_logger(), "Failed to move %s to position %.3f", 
                    joint_name_.c_str(), position);
        return;
    }
    
    RCLCPP_INFO(node_->get_logger(), "🚀 Enhanced: %s moved to position %.3f rad", 
               joint_name_.c_str(), position);
    
    if (wait) {
        // Wait for movement completion - could be enhanced with position feedback
        rclcpp::sleep_for(std::chrono::milliseconds(100));
    }
}

motor_control_ros2::MotorStatus EnhancedJointMove::getMotorStatus() const {
    if (motor_controller_) {
        return motor_controller_->get_status();
    }
    
    // Return empty status if no controller
    motor_control_ros2::MotorStatus empty_status;
    empty_status.state = motor_control_ros2::MotorStatus::UNKNOWN;
    return empty_status;
}

bool EnhancedJointMove::enableMotor() {
    if (motor_controller_) {
        return motor_controller_->set_enabled(true);
    }
    return false;
}

bool EnhancedJointMove::disableMotor() {
    if (motor_controller_) {
        return motor_controller_->set_enabled(false);
    }
    return false;
}

bool EnhancedJointMove::homeMotor() {
    if (motor_controller_) {
        return motor_controller_->home_motor();
    }
    return false;
}

} // namespace yanthra_move