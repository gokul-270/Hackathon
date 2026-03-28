/*
 * Copyright (c) 2024 Open Source Robotics Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http:  // www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef MOTOR_CONTROL_ROS2_SAFETY_MONITOR_HPP_
#define MOTOR_CONTROL_ROS2_SAFETY_MONITOR_HPP_

/*
 * Author: ROS2 Migration Team
 * Description: Safety Monitor for Motor Control System
 *
 * Provides safety monitoring with a proper state machine,
 * fail-safe defaults, and emergency stop execution.
 */

#pragma once

#include <memory>
#include <atomic>
#include <list>
#include <mutex>
#include <unordered_map>
#include <vector>
#include <map>
#include <string>
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/joint_state.hpp"
#include "std_msgs/msg/string.hpp"
#include "std_srvs/srv/trigger.hpp"
#include "motor_control_ros2/motor_controller_interface.hpp"

namespace motor_control_ros2
{

/**
 * @brief Bounded LRU map — evicts oldest entries when capacity is exceeded.
 *
 * Used to replace unbounded std::map containers that would grow without limit
 * during 24-hour field operations.
 */
template<typename Key, typename Value>
class BoundedLruMap
{
public:
    explicit BoundedLruMap(size_t max_size = 1000) : max_size_(max_size) {}

    void put(const Key& key, const Value& value)
    {
        auto it = map_.find(key);
        if (it != map_.end()) {
            // Update existing: move to front of LRU list
            lru_list_.erase(it->second.second);
            lru_list_.push_front(key);
            it->second = {value, lru_list_.begin()};
        } else {
            // Insert new entry
            if (map_.size() >= max_size_) {
                // Evict oldest (back of LRU list)
                auto oldest_key = lru_list_.back();
                lru_list_.pop_back();
                map_.erase(oldest_key);
            }
            lru_list_.push_front(key);
            map_[key] = {value, lru_list_.begin()};
        }
    }

    bool contains(const Key& key) const { return map_.find(key) != map_.end(); }

    const Value& get(const Key& key) const { return map_.at(key).first; }

    Value& get(const Key& key) { return map_.at(key).first; }

    size_t size() const { return map_.size(); }

    size_t max_size() const { return max_size_; }

    void clear()
    {
        map_.clear();
        lru_list_.clear();
    }

private:
    size_t max_size_;
    std::list<Key> lru_list_;
    std::unordered_map<Key, std::pair<Value, typename std::list<Key>::iterator>> map_;
};

/**
 * @brief Safety state enum — replaces bare booleans with explicit states.
 *
 * States: UNKNOWN (initial), INITIALIZING, SAFE, WARNING, CRITICAL, EMERGENCY.
 * is_safe() returns true only for SAFE and WARNING (fail-safe default).
 */
enum class SafetyState : uint8_t
{
    UNKNOWN = 0,
    INITIALIZING = 1,
    SAFE = 2,
    WARNING = 3,
    CRITICAL = 4,
    EMERGENCY = 5
};

/**
 * @brief Convert SafetyState to human-readable string
 */
inline const char* safety_state_to_string(SafetyState state)
{
    switch (state) {
        case SafetyState::UNKNOWN: return "UNKNOWN";
        case SafetyState::INITIALIZING: return "INITIALIZING";
        case SafetyState::SAFE: return "SAFE";
        case SafetyState::WARNING: return "WARNING";
        case SafetyState::CRITICAL: return "CRITICAL";
        case SafetyState::EMERGENCY: return "EMERGENCY";
        default: return "INVALID";
    }
}


/**
 * @brief Safety monitor with proper state machine for motor control system
 *
 * Uses SafetyState enum stored in std::atomic for lock-free, thread-safe
 * state access. Fail-safe default: is_safe() returns false unless state is
 * SAFE or WARNING.
 */
class SafetyMonitor
{
public:
    /**
     * @brief Constructor
     */
    SafetyMonitor(
        std::shared_ptr<rclcpp::node_interfaces::NodeBaseInterface> node_base,
        std::shared_ptr<rclcpp::node_interfaces::NodeLoggingInterface> node_logging,
        std::shared_ptr<rclcpp::node_interfaces::NodeParametersInterface> node_parameters,
        std::shared_ptr<rclcpp::node_interfaces::NodeTopicsInterface> node_topics,
        std::shared_ptr<rclcpp::node_interfaces::NodeServicesInterface> node_services
    );

    /**
     * @brief Destructor
     */
    ~SafetyMonitor() = default;

    /**
     * @brief Activate the safety monitor
     * @return true if activation successful
     */
    bool activate();

    /**
     * @brief Deactivate the safety monitor
     */
    void deactivate();

    /**
     * @brief Update the safety monitor (called from control loop)
     */
    void update();

    /**
     * @brief Check if the system is in a safe state (fail-safe)
     * @return true only if state is SAFE or WARNING; false otherwise
     */
    bool is_safe() const;

    /**
     * @brief Get the current safety state
     * @return Current SafetyState enum value
     */
    SafetyState get_state() const;

    /**
     * @brief Attempt a state transition with validation
     * @param new_state The target state
     * @return true if transition was valid and applied
     */
    bool transition_to(SafetyState new_state);

    /**
     * @brief Request emergency stop
     */
    void request_emergency_stop();

    /**
     * @brief Trigger emergency shutdown with reason
     * @param reason The reason for emergency shutdown
     */
    void trigger_emergency_shutdown(const std::string& reason);

    /**
     * @brief Update joint state data from /joint_states topic
     * @param msg Joint state message
     */
    void update_joint_states(const sensor_msgs::msg::JointState::SharedPtr msg);

    /**
     * @brief Update motor temperature data
     * @param joint_name Name of the joint
     * @param temperature Temperature in degrees Celsius
     */
    void update_motor_temperature(const std::string& joint_name, double temperature);

    /**
     * @brief Update motor error status
     * @param joint_name Name of the joint
     * @param error_flags ODrive error flags
     */
    void update_motor_errors(const std::string& joint_name, uint32_t error_flags);

    /**
     * @brief Update bus voltage
     * @param voltage VBus voltage in volts
     */
    void update_vbus_voltage(double voltage);

    /**
     * @brief Set motor controllers for e-stop execution
     * @param controllers Vector of motor controller shared pointers
     *
     * SafetyMonitor calls emergency_stop() on each controller during
     * emergency shutdown. Fire-all-then-verify pattern: all controllers
     * receive stop commands before checking results.
     */
    void set_controllers(
        const std::vector<std::shared_ptr<MotorControllerInterface>>& controllers);

private:
    // Node interfaces
    std::shared_ptr<rclcpp::node_interfaces::NodeBaseInterface> node_base_;
    std::shared_ptr<rclcpp::node_interfaces::NodeLoggingInterface> node_logging_;
    std::shared_ptr<rclcpp::node_interfaces::NodeParametersInterface> node_parameters_;
    std::shared_ptr<rclcpp::node_interfaces::NodeTopicsInterface> node_topics_;
    std::shared_ptr<rclcpp::node_interfaces::NodeServicesInterface> node_services_;

    // ROS2 Subscribers
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_states_sub_;

    // ROS2 Publishers
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr emergency_stop_pub_;
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr safety_state_pub_;

    // ROS2 Service servers
    rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr reset_service_;
    rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr emergency_stop_service_;

    // Parameter callback handle
    rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr param_callback_handle_;

    /**
     * @brief Handle /safety/reset service request
     */
    void handle_safety_reset(
        const std::shared_ptr<std_srvs::srv::Trigger::Request> request,
        std::shared_ptr<std_srvs::srv::Trigger::Response> response);

    // Safety state — single atomic enum replaces is_active_, is_safe_, emergency_stop_requested_
    std::atomic<SafetyState> safety_state_{SafetyState::UNKNOWN};

    // Motor controllers for e-stop execution
    std::vector<std::shared_ptr<MotorControllerInterface>> controllers_;

    /**
     * @brief Check if a state transition is valid
     * @param from Current state
     * @param to Target state
     * @return true if transition is allowed
     */
    bool is_valid_transition(SafetyState from, SafetyState to) const;

    // --- Data mutex: protects ALL shared mutable state below ---
    // Must be held when reading or writing joint state vectors, telemetry data,
    // configuration values, and throttle state. The only exception is safety_state_
    // which is std::atomic.
    mutable std::mutex data_mutex_;

    // Configuration (written by parameter callback, read by check methods)
    double max_velocity_limit_;
    double timeout_threshold_;

    // Timing
    std::chrono::steady_clock::time_point last_update_time_;

    // Joint state data (from /joint_states topic)
    std::vector<double> joint_positions_;
    std::vector<double> joint_velocities_;
    std::vector<double> joint_efforts_;
    std::vector<std::string> joint_names_;
    std::chrono::steady_clock::time_point last_joint_state_time_;
    bool joint_state_received_;

    // Motor telemetry data (from ODrive)
    std::map<std::string, double> motor_temperatures_;  // Joint name -> temperature (°C)
    std::map<std::string, uint32_t> motor_errors_;      // Joint name -> error flags
    double vbus_voltage_;                                // Battery voltage (V)
    std::chrono::steady_clock::time_point last_telemetry_time_;
    bool telemetry_received_;

    // Safety thresholds
    double position_safety_margin_;      // degrees from limit
    double max_temperature_warning_;     // °C
    double max_temperature_critical_;    // °C
    double min_voltage_warning_;         // V
    double min_voltage_critical_;        // V

    // --- Former static locals, now instance members (task 1.1) ---
    // Throttle time points for warning rate-limiting
    std::chrono::steady_clock::time_point update_warn_throttle_time_;
    std::chrono::steady_clock::time_point power_warn_throttle_time_;
    // Check cycle counter for staggering comprehensive checks
    int check_cycle_{0};
    // Bounded LRU maps replacing unbounded static std::map (task 1.2)
    BoundedLruMap<std::string, std::chrono::steady_clock::time_point> temp_warning_times_{1000};
    BoundedLruMap<std::string, uint32_t> last_reported_errors_{1000};

    // CRITICAL FIX: Comprehensive safety check methods from ROS1 system
    void perform_comprehensive_safety_checks();
    void check_joint_position_limits();
    void check_velocity_limits();
    void check_temperature_limits();
    void check_communication_timeouts();
    void check_motor_error_status();
    void check_power_supply_status();

    /**
     * @brief Execute complete emergency shutdown sequence
     * @param reason The reason for emergency shutdown
     *
     * Performs 5-step emergency shutdown:
     * 1. Send ESTOP to all motors via CAN
     * 2. Disable all GPIO outputs (vacuum, LEDs)
     * 3. Activate error LED indicator
     * 4. Log critical event with timestamp
     * 5. Prepare system for safe shutdown
     */
    void execute_emergency_shutdown_sequence(const std::string& reason);
};

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2_SAFETY_MONITOR_HPP_
