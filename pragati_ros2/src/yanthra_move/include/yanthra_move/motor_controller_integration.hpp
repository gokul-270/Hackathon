#ifndef YANTHRA_MOVE_MOTOR_CONTROLLER_INTEGRATION_HPP_
#define YANTHRA_MOVE_MOTOR_CONTROLLER_INTEGRATION_HPP_

/**
 * @file motor_controller_integration.hpp
 * @brief Integration layer between YanthraMove and the new motor abstraction layer
 * @details This file bridges the existing joint_move class with the new MotorControllerInterface
 *          enabling seamless migration from ODrive-specific control to generic motor control
 */

#include <memory>
#include <map>
#include <string>
#include <rclcpp/rclcpp.hpp>

// YanthraMove includes
#include "yanthra_move/joint_move.h"

// Motor abstraction includes
#include "motor_control_ros2/motor_abstraction.hpp"
#include "motor_control_ros2/odrive_controller.hpp"
#include "motor_control_ros2/mg6010_controller.hpp"

namespace yanthra_move {

/**
 * @class MotorControllerIntegration
 * @brief Manages the integration between YanthraMove joint controllers and motor abstraction
 */
class MotorControllerIntegration {
public:
    /**
     * @brief Constructor
     * @param node ROS2 node for logging and services
     */
    explicit MotorControllerIntegration(rclcpp::Node::SharedPtr node);
    
    /**
     * @brief Initialize motor controllers for all joints
     * @param config_path Path to motor configuration file
     * @return true if initialization successful
     */
    bool initialize(const std::string& config_path = "");
    
    /**
     * @brief Get motor controller for a specific joint
     * @param joint_name Joint name (e.g., "joint2", "joint3")
     * @return Shared pointer to motor controller interface
     */
    std::shared_ptr<motor_control_ros2::MotorControllerInterface> getMotorController(
        const std::string& joint_name);
    
    /**
     * @brief Update joint_move instances to use new motor controllers
     * @param joint2 Joint2 controller instance
     * @param joint3 Joint3 controller instance  
     * @param joint4 Joint4 controller instance
     * @param joint5 Joint5 controller instance
     */
    void integrateWithJointMove(
        std::unique_ptr<joint_move>& joint2,
        std::unique_ptr<joint_move>& joint3,
        std::unique_ptr<joint_move>& joint4,
        std::unique_ptr<joint_move>& joint5);
    
    /**
     * @brief Enable all motors
     * @return true if all motors enabled successfully
     */
    bool enableAllMotors();
    
    /**
     * @brief Disable all motors
     * @return true if all motors disabled successfully
     */
    bool disableAllMotors();
    
    /**
     * @brief Home all motors
     * @return true if homing successful for all motors
     */
    bool homeAllMotors();
    
    /**
     * @brief Emergency stop all motors
     */
    void emergencyStopAll();
    
    /**
     * @brief Get status of all motors
     * @return Map of joint names to motor status
     */
    std::map<std::string, motor_control_ros2::MotorStatus> getAllMotorStatus();
    
    /**
     * @brief Check if all motors are healthy
     * @return true if all motors are operational
     */
    bool areAllMotorsHealthy();

private:
    rclcpp::Node::SharedPtr node_;
    
    // Motor controllers mapped by joint name
    std::map<std::string, std::shared_ptr<motor_control_ros2::MotorControllerInterface>> motor_controllers_;
    
    // CAN interfaces for different motor types
    std::shared_ptr<motor_control_ros2::CANInterface> odrive_can_interface_;
    std::shared_ptr<motor_control_ros2::CANInterface> mg6010_can_interface_;
    
    // Joint to ODrive ID mapping (preserved from original system)
    std::map<std::string, int> joint_to_odrive_id_ = {
        {"joint2", 3},  // Joint2 -> ODrive service joint_id 3
        {"joint3", 0},  // Joint3 -> ODrive service joint_id 0  
        {"joint4", 1},  // Joint4 -> ODrive service joint_id 1
        {"joint5", 2}   // Joint5 -> ODrive service joint_id 2
    };
    
    /**
     * @brief Load motor configuration for all joints
     * @param config_path Path to configuration file
     * @return true if configuration loaded successfully
     */
    bool loadConfiguration(const std::string& config_path);
    
    /**
     * @brief Create motor controller based on configuration
     * @param config Motor configuration
     * @return Shared pointer to created motor controller
     */
    std::shared_ptr<motor_control_ros2::MotorControllerInterface> createMotorController(
        const motor_control_ros2::MotorConfiguration& config);
    
    /**
     * @brief Initialize CAN interfaces
     * @return true if CAN interfaces initialized successfully
     */
    bool initializeCANInterfaces();
    
    /**
     * @brief Get default configuration for a joint
     * @param joint_name Name of the joint
     * @param odrive_id ODrive ID for the joint
     * @return Default motor configuration
     */
    motor_control_ros2::MotorConfiguration getDefaultConfiguration(
        const std::string& joint_name, int odrive_id);
};

/**
 * @class EnhancedJointMove
 * @brief Enhanced joint_move class that uses the new motor abstraction
 * @details This class extends the original joint_move functionality with the new motor controllers
 */
class EnhancedJointMove : public joint_move {
public:
    /**
     * @brief Constructor with motor controller integration
     * @param node ROS2 node
     * @param name Joint name
     * @param motor_controller Motor controller instance
     * @param odrive_id ODrive ID (for compatibility)
     */
    EnhancedJointMove(
        rclcpp::Node::SharedPtr node, 
        const std::string& name,
        std::shared_ptr<motor_control_ros2::MotorControllerInterface> motor_controller,
        int odrive_id);
    
    /**
     * @brief Move joint using new motor controller
     * @param position Target position in radians
     * @param wait Whether to wait for completion
     */
    void move_joint_enhanced(double position, bool wait = false);
    
    /**
     * @brief Get motor status
     * @return Current motor status
     */
    motor_control_ros2::MotorStatus getMotorStatus() const;
    
    /**
     * @brief Enable motor
     * @return true if successful
     */
    bool enableMotor();
    
    /**
     * @brief Disable motor
     * @return true if successful
     */
    bool disableMotor();
    
    /**
     * @brief Home motor
     * @return true if successful
     */
    bool homeMotor();
    
private:
    std::shared_ptr<motor_control_ros2::MotorControllerInterface> motor_controller_;
};

} // namespace yanthra_move

#endif // YANTHRA_MOVE_MOTOR_CONTROLLER_INTEGRATION_HPP_