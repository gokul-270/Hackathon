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

/*
 * Author: ROS2 Migration Team
 * Description: Safety Monitor Implementation for Motor Control System
 */

#include "motor_control_ros2/safety_monitor.hpp"
#include <chrono>
#include <common_utils/json_logging.hpp>
#include <nlohmann/json.hpp>
#include <std_srvs/srv/trigger.hpp>

namespace motor_control_ros2
{


SafetyMonitor::SafetyMonitor(
    std::shared_ptr<rclcpp::node_interfaces::NodeBaseInterface> node_base,
    std::shared_ptr<rclcpp::node_interfaces::NodeLoggingInterface> node_logging,
    std::shared_ptr<rclcpp::node_interfaces::NodeParametersInterface> node_parameters,
    std::shared_ptr<rclcpp::node_interfaces::NodeTopicsInterface> node_topics,
    std::shared_ptr<rclcpp::node_interfaces::NodeServicesInterface> node_services
)
: node_base_(node_base)
, node_logging_(node_logging)
, node_parameters_(node_parameters)
, node_topics_(node_topics)
, node_services_(node_services)
, safety_state_(SafetyState::UNKNOWN)
, max_velocity_limit_(10.0)  // rad/s — default, overridden by parameter
, timeout_threshold_(1.0)    // seconds
, joint_state_received_(false)
, vbus_voltage_(48.0)        // Default nominal voltage
, telemetry_received_(false)
, position_safety_margin_(5.0)      // degrees
, max_temperature_warning_(65.0)    // °C — default, overridden by parameter
, max_temperature_critical_(70.0)   // °C — default, overridden by parameter
, min_voltage_warning_(42.0)        // V — default, overridden by parameter
, min_voltage_critical_(40.0)       // V — default, overridden by parameter
{
    // Initialize timing
    last_update_time_ = std::chrono::steady_clock::now();
    last_joint_state_time_ = std::chrono::steady_clock::now();
    last_telemetry_time_ = std::chrono::steady_clock::now();

    // Declare safety thresholds as ROS2 parameters with defaults.
    // Use has_parameter() guard so SafetyMonitor can be re-created across
    // lifecycle configure/cleanup cycles without "already declared" errors.
    if (!node_parameters_->has_parameter("safety.temperature_warning")) {
      rcl_interfaces::msg::ParameterDescriptor temp_warn_desc;
      temp_warn_desc.description = "Temperature warning threshold (C)";
      temp_warn_desc.floating_point_range.resize(1);
      temp_warn_desc.floating_point_range[0].from_value = 0.0;
      temp_warn_desc.floating_point_range[0].to_value = 200.0;
      max_temperature_warning_ = node_parameters_->declare_parameter(
          "safety.temperature_warning",
          rclcpp::ParameterValue(65.0), temp_warn_desc).get<double>();
    } else {
      rclcpp::Parameter param;
      node_parameters_->get_parameter("safety.temperature_warning", param);
      max_temperature_warning_ = param.as_double();
    }

    if (!node_parameters_->has_parameter("safety.temperature_critical")) {
      rcl_interfaces::msg::ParameterDescriptor temp_crit_desc;
      temp_crit_desc.description = "Temperature critical threshold (C)";
      temp_crit_desc.floating_point_range.resize(1);
      temp_crit_desc.floating_point_range[0].from_value = 0.0;
      temp_crit_desc.floating_point_range[0].to_value = 200.0;
      max_temperature_critical_ = node_parameters_->declare_parameter(
          "safety.temperature_critical",
          rclcpp::ParameterValue(70.0), temp_crit_desc).get<double>();
    } else {
      rclcpp::Parameter param;
      node_parameters_->get_parameter("safety.temperature_critical", param);
      max_temperature_critical_ = param.as_double();
    }

    if (!node_parameters_->has_parameter("safety.voltage_min_warning")) {
      rcl_interfaces::msg::ParameterDescriptor volt_warn_desc;
      volt_warn_desc.description = "Minimum voltage warning threshold (V)";
      volt_warn_desc.floating_point_range.resize(1);
      volt_warn_desc.floating_point_range[0].from_value = 0.0;
      volt_warn_desc.floating_point_range[0].to_value = 100.0;
      min_voltage_warning_ = node_parameters_->declare_parameter(
          "safety.voltage_min_warning",
          rclcpp::ParameterValue(42.0), volt_warn_desc).get<double>();
    } else {
      rclcpp::Parameter param;
      node_parameters_->get_parameter("safety.voltage_min_warning", param);
      min_voltage_warning_ = param.as_double();
    }

    if (!node_parameters_->has_parameter("safety.voltage_min_critical")) {
      rcl_interfaces::msg::ParameterDescriptor volt_crit_desc;
      volt_crit_desc.description = "Minimum voltage critical threshold (V)";
      volt_crit_desc.floating_point_range.resize(1);
      volt_crit_desc.floating_point_range[0].from_value = 0.0;
      volt_crit_desc.floating_point_range[0].to_value = 100.0;
      min_voltage_critical_ = node_parameters_->declare_parameter(
          "safety.voltage_min_critical",
          rclcpp::ParameterValue(40.0), volt_crit_desc).get<double>();
    } else {
      rclcpp::Parameter param;
      node_parameters_->get_parameter("safety.voltage_min_critical", param);
      min_voltage_critical_ = param.as_double();
    }

    if (!node_parameters_->has_parameter("safety.velocity_max")) {
      rcl_interfaces::msg::ParameterDescriptor vel_max_desc;
      vel_max_desc.description = "Maximum velocity limit (rad/s)";
      vel_max_desc.floating_point_range.resize(1);
      vel_max_desc.floating_point_range[0].from_value = 0.1;
      vel_max_desc.floating_point_range[0].to_value = 100.0;
      max_velocity_limit_ = node_parameters_->declare_parameter(
          "safety.velocity_max",
          rclcpp::ParameterValue(10.0), vel_max_desc).get<double>();
    } else {
      rclcpp::Parameter param;
      node_parameters_->get_parameter("safety.velocity_max", param);
      max_velocity_limit_ = param.as_double();
    }

    // Create subscriber for joint_states topic
    rclcpp::SubscriptionOptions sub_options;
    joint_states_sub_ = rclcpp::create_subscription<sensor_msgs::msg::JointState>(
        node_parameters_,
        node_topics_,
        "/joint_states",
        rclcpp::QoS(10),
        [this](const sensor_msgs::msg::JointState::SharedPtr msg) {
            this->update_joint_states(msg);
        },
        sub_options
    );

    // Create publisher for emergency stop events
    rclcpp::PublisherOptions pub_options;
    emergency_stop_pub_ = rclcpp::create_publisher<std_msgs::msg::String>(
        node_parameters_,
        node_topics_,
        "/safety/emergency_stop",
        rclcpp::QoS(10).transient_local(),  // Latched for critical events
        pub_options
    );

    // Create publisher for safety state (queryable via topic)
    rclcpp::PublisherOptions state_pub_options;
    safety_state_pub_ = rclcpp::create_publisher<std_msgs::msg::String>(
        node_parameters_,
        node_topics_,
        "/safety/state",
        rclcpp::QoS(10).transient_local(),
        state_pub_options
    );

    // Create /safety/reset service
    reset_service_ = rclcpp::create_service<std_srvs::srv::Trigger>(
        node_base_,
        node_services_,
        "/safety/reset",
        std::bind(&SafetyMonitor::handle_safety_reset, this,
                  std::placeholders::_1, std::placeholders::_2),
        rclcpp::ServicesQoS(),
        nullptr
    );

    // Create /safety/emergency_stop service
    emergency_stop_service_ = rclcpp::create_service<std_srvs::srv::Trigger>(
        node_base_,
        node_services_,
        "/safety/trigger_emergency_stop",
        [this](
            const std::shared_ptr<std_srvs::srv::Trigger::Request> /*request*/,
            std::shared_ptr<std_srvs::srv::Trigger::Response> response) {
            trigger_emergency_shutdown("ROS2 service call");
            response->success = true;
            response->message = "Emergency stop triggered via service";
        },
        rclcpp::ServicesQoS(),
        nullptr
    );

    // Register parameter change callback to update member variables at runtime
    param_callback_handle_ = node_parameters_->add_on_set_parameters_callback(
        [this](const std::vector<rclcpp::Parameter>& parameters)
            -> rcl_interfaces::msg::SetParametersResult {
            rcl_interfaces::msg::SetParametersResult result;
            result.successful = true;

            std::lock_guard<std::mutex> lock(data_mutex_);
            for (const auto& param : parameters) {
                if (param.get_name() == "safety.temperature_warning") {
                    max_temperature_warning_ = param.as_double();
                } else if (param.get_name() == "safety.temperature_critical") {
                    max_temperature_critical_ = param.as_double();
                } else if (param.get_name() == "safety.voltage_min_warning") {
                    min_voltage_warning_ = param.as_double();
                } else if (param.get_name() == "safety.voltage_min_critical") {
                    min_voltage_critical_ = param.as_double();
                } else if (param.get_name() == "safety.velocity_max") {
                    max_velocity_limit_ = param.as_double();
                }
            }

            RCLCPP_INFO(
                rclcpp::get_logger("safety_monitor"),
                "Safety parameters updated at runtime");
            return result;
        }
    );

    RCLCPP_INFO(
        rclcpp::get_logger("safety_monitor"),
        "Safety Monitor initialized (state: UNKNOWN) - velocity limit: %.2f rad/s",
        max_velocity_limit_
    );
}

bool SafetyMonitor::activate()
{
    RCLCPP_INFO(rclcpp::get_logger("safety_monitor"), "Activating Safety Monitor");

    // Transition to INITIALIZING
    transition_to(SafetyState::INITIALIZING);
    {
        std::lock_guard<std::mutex> lock(data_mutex_);
        last_update_time_ = std::chrono::steady_clock::now();
    }

    RCLCPP_INFO(rclcpp::get_logger("safety_monitor"),
        "Safety Monitor activated (state: INITIALIZING)");
    return true;
}

void SafetyMonitor::deactivate()
{
    RCLCPP_INFO(rclcpp::get_logger("safety_monitor"), "Deactivating Safety Monitor");
    safety_state_.store(SafetyState::UNKNOWN);
    RCLCPP_INFO(rclcpp::get_logger("safety_monitor"),
        "Safety Monitor deactivated (state: UNKNOWN)");
}


void SafetyMonitor::update()
{
    SafetyState current = safety_state_.load();

    // Only process updates in active states
    if (current == SafetyState::UNKNOWN) {
        return;
    }

    std::lock_guard<std::mutex> lock(data_mutex_);

    auto current_time = std::chrono::steady_clock::now();
    auto time_since_last_update = std::chrono::duration<double>(
        current_time - last_update_time_).count();

    // Check for timeout
    if (time_since_last_update > timeout_threshold_) {
        if (std::chrono::duration<double>(current_time - update_warn_throttle_time_).count() > 1.0) {
            RCLCPP_WARN(
                rclcpp::get_logger("safety_monitor"),
                "Safety monitor update timeout: %.3f seconds (threshold: %.3f)",
                time_since_last_update, timeout_threshold_
            );
            update_warn_throttle_time_ = current_time;
        }
    }

    // Check for emergency state — don't run safety checks, stay in EMERGENCY
    if (current == SafetyState::EMERGENCY) {
        last_update_time_ = current_time;
        return;
    }

    // Run comprehensive safety checks
    perform_comprehensive_safety_checks();

    // If still in INITIALIZING after successful checks, transition to SAFE
    current = safety_state_.load();
    if (current == SafetyState::INITIALIZING) {
        transition_to(SafetyState::SAFE);
    }

    last_update_time_ = current_time;
}

void SafetyMonitor::perform_comprehensive_safety_checks()
{
    // CRITICAL FIX: Implement safety checks from ROS1 system
    check_cycle_++;


    // Check 1: Joint position limits (every cycle)
    check_joint_position_limits();

    // Check 2: Velocity limits (every cycle)
    check_velocity_limits();

    // Check 3: Temperature monitoring (every 10 cycles)
    if (check_cycle_ % 10 == 0) {
        check_temperature_limits();
    }

    // Check 4: Communication timeouts (every 5 cycles)
    if (check_cycle_ % 5 == 0) {
        check_communication_timeouts();
    }

    // Check 5: Motor error status (every cycle)
    check_motor_error_status();

    // Check 6: Power supply voltage (every 20 cycles)
    if (check_cycle_ % 20 == 0) {
        check_power_supply_status();
    }
}

void SafetyMonitor::check_joint_position_limits()
{
    if (!joint_state_received_ || joint_positions_.empty()) {
        return;  // No data yet
    }

    // Define joint limits (from URDF - pragati robot)
    const std::vector<std::pair<double, double>> joint_limits = {
        {-1.57, 1.57},    // joint2: +/-90 degrees
        {-1.57, 1.57},    // joint3: +/-90 degrees
        {-1.57, 1.57},    // joint4: +/-90 degrees
        {-3.14, 3.14}     // joint5: +/-180 degrees (continuous)
    };

    double safety_margin_rad = position_safety_margin_ * (M_PI / 180.0);

    for (size_t i = 0; i < joint_positions_.size() && i < joint_limits.size(); ++i) {
        double position = joint_positions_[i];
        double min_limit = joint_limits[i].first;
        double max_limit = joint_limits[i].second;

        if (position < (min_limit + safety_margin_rad)) {
            RCLCPP_ERROR(
                rclcpp::get_logger("safety_monitor"),
                "Joint %zu position %.2f rad approaching min limit %.2f rad!",
                i, position, min_limit
            );
            pragati::emit_motor_alert(
                rclcpp::get_logger("safety_monitor"),
                "critical", "joint_position_limits", "joint" + std::to_string(i),
                "position approaching min limit", position, min_limit + safety_margin_rad,
                "emergency_shutdown");

            trigger_emergency_shutdown(
                "Joint " + std::to_string(i) + " approaching minimum position limit"
            );
            return;
        }

        if (position > (max_limit - safety_margin_rad)) {
            RCLCPP_ERROR(
                rclcpp::get_logger("safety_monitor"),
                "Joint %zu position %.2f rad approaching max limit %.2f rad!",
                i, position, max_limit
            );
            pragati::emit_motor_alert(
                rclcpp::get_logger("safety_monitor"),
                "critical", "joint_position_limits", "joint" + std::to_string(i),
                "position approaching max limit", position, max_limit - safety_margin_rad,
                "emergency_shutdown");

            trigger_emergency_shutdown(
                "Joint " + std::to_string(i) + " approaching maximum position limit"
            );
            return;
        }
    }
}


void SafetyMonitor::check_velocity_limits()
{
    if (!joint_state_received_ || joint_velocities_.empty()) {
        return;  // No data yet
    }

    for (size_t i = 0; i < joint_velocities_.size(); ++i) {
        double velocity = std::abs(joint_velocities_[i]);

        if (velocity > max_velocity_limit_) {
            RCLCPP_ERROR(
                rclcpp::get_logger("safety_monitor"),
                "Joint %zu velocity %.2f rad/s EXCEEDS limit %.2f rad/s!",
                i, velocity, max_velocity_limit_
            );
            pragati::emit_motor_alert(
                rclcpp::get_logger("safety_monitor"),
                "critical", "velocity_limits", "joint" + std::to_string(i),
                "velocity exceeds limit", velocity, max_velocity_limit_,
                "emergency_shutdown");

            trigger_emergency_shutdown(
                "Joint " + std::to_string(i) + " velocity " +
                std::to_string(velocity) + " rad/s exceeds limit " +
                std::to_string(max_velocity_limit_) + " rad/s"
            );
            return;
        }
    }
}


void SafetyMonitor::check_temperature_limits()
{
    if (!telemetry_received_ || motor_temperatures_.empty()) {
        return;  // No telemetry data yet
    }

    bool has_warning = false;

    for (const auto& [joint_name, temperature] : motor_temperatures_) {
        // Critical temperature - immediate stop
        if (temperature > max_temperature_critical_) {
            RCLCPP_ERROR(
                rclcpp::get_logger("safety_monitor"),
                "CRITICAL: %s temperature %.1fC exceeds %.1fC!",
                joint_name.c_str(), temperature, max_temperature_critical_
            );
            pragati::emit_motor_alert(
                rclcpp::get_logger("safety_monitor"),
                "critical", "temperature_limits", joint_name,
                "temperature exceeds critical threshold", temperature,
                max_temperature_critical_, "emergency_shutdown");

            trigger_emergency_shutdown(
                joint_name + " temperature critical: " +
                std::to_string(temperature) + "C > " +
                std::to_string(max_temperature_critical_) + "C"
            );
            return;
        }

        // Warning temperature - transition to WARNING state
        if (temperature > max_temperature_warning_) {
            has_warning = true;
            auto now = std::chrono::steady_clock::now();

            if (!temp_warning_times_.contains(joint_name) ||
                std::chrono::duration<double>(now - temp_warning_times_.get(joint_name)).count() > 5.0) {
                RCLCPP_WARN(
                    rclcpp::get_logger("safety_monitor"),
                    "%s temperature %.1fC approaching limit (critical: %.1fC)",
                    joint_name.c_str(), temperature, max_temperature_critical_
                );
                pragati::emit_motor_alert(
                    rclcpp::get_logger("safety_monitor"),
                    "warning", "temperature_limits", joint_name,
                    "temperature approaching critical threshold", temperature,
                    max_temperature_warning_, "log_warning");

                temp_warning_times_.put(joint_name, now);
            }
        }
    }

    // Transition to WARNING if any motor is in warning range
    SafetyState current = safety_state_.load();
    if (has_warning && current == SafetyState::SAFE) {
        transition_to(SafetyState::WARNING);
    } else if (!has_warning && current == SafetyState::WARNING) {
        // Recovery from warning — all temps back to normal
        transition_to(SafetyState::SAFE);
    }
}


void SafetyMonitor::check_communication_timeouts()
{
    auto current_time = std::chrono::steady_clock::now();

    // Check joint state timeout
    if (joint_state_received_) {
        double time_since_joint_state =
            std::chrono::duration<double>(current_time - last_joint_state_time_).count();

        if (time_since_joint_state > timeout_threshold_) {
            RCLCPP_ERROR(
                rclcpp::get_logger("safety_monitor"),
                "Joint state communication TIMEOUT: %.2f s (threshold: %.2f s)",
                time_since_joint_state, timeout_threshold_
            );
            pragati::emit_motor_alert(
                rclcpp::get_logger("safety_monitor"),
                "critical", "communication_timeouts", "all",
                "joint state communication timeout", time_since_joint_state,
                timeout_threshold_, "emergency_shutdown");

            trigger_emergency_shutdown(
                "Joint state communication timeout: " +
                std::to_string(time_since_joint_state) + "s"
            );
            return;
        }
    }

    // Check telemetry timeout (if we've received it at least once)
    if (telemetry_received_) {
        double time_since_telemetry =
            std::chrono::duration<double>(current_time - last_telemetry_time_).count();

        if (time_since_telemetry > timeout_threshold_ * 2.0) {
            RCLCPP_WARN(
                rclcpp::get_logger("safety_monitor"),
                "ODrive telemetry timeout: %.2f s",
                time_since_telemetry
            );
            pragati::emit_motor_alert(
                rclcpp::get_logger("safety_monitor"),
                "warning", "communication_timeouts", "all",
                "telemetry timeout", time_since_telemetry,
                timeout_threshold_ * 2.0, "log_warning");

            // Don't trigger E-stop for telemetry timeout, just warn
        }
    }
}


void SafetyMonitor::check_motor_error_status()
{
    if (!telemetry_received_ || motor_errors_.empty()) {
        return;  // No error data yet
    }

    const uint32_t CRITICAL_ERRORS = 0x00F2;  // Bits 1,4,5,6,7 are critical

    for (const auto& [joint_name, error_flags] : motor_errors_) {
        if (error_flags == 0) {
            continue;  // No errors
        }

        // Check for critical errors
        if (error_flags & CRITICAL_ERRORS) {
            RCLCPP_ERROR(
                rclcpp::get_logger("safety_monitor"),
                "CRITICAL MOTOR ERROR: %s has error flags 0x%04X",
                joint_name.c_str(), error_flags
            );

            std::string error_desc;
            if (error_flags & 0x0002) error_desc += "SYSTEM_ERROR ";
            if (error_flags & 0x0010) error_desc += "BAD_CONFIG ";
            if (error_flags & 0x0020) error_desc += "DRV_FAULT ";
            if (error_flags & 0x0040) error_desc += "MISSING_INPUT ";
            if (error_flags & 0x0080) error_desc += "VOLTAGE_ERROR ";

            pragati::emit_motor_alert(
                rclcpp::get_logger("safety_monitor"),
                "critical", "motor_error_status", joint_name,
                "critical motor error: " + error_desc,
                static_cast<double>(error_flags),
                static_cast<double>(CRITICAL_ERRORS), "emergency_shutdown");

            trigger_emergency_shutdown(
                joint_name + " motor error: " + error_desc +
                "(flags: 0x" + std::to_string(error_flags) + ")"
            );
            return;
        }

        // Non-critical errors - log warning
        if (error_flags != 0) {
            if (!last_reported_errors_.contains(joint_name) ||
                last_reported_errors_.get(joint_name) != error_flags) {
                RCLCPP_WARN(
                    rclcpp::get_logger("safety_monitor"),
                    "%s has non-critical error flags: 0x%04X",
                    joint_name.c_str(), error_flags
                );
                pragati::emit_motor_alert(
                    rclcpp::get_logger("safety_monitor"),
                    "warning", "motor_error_status", joint_name,
                    "non-critical motor error flags",
                    static_cast<double>(error_flags), 0.0, "log_warning");

                last_reported_errors_.put(joint_name, error_flags);
            }
        }
    }
}


void SafetyMonitor::check_power_supply_status()
{
    if (!telemetry_received_) {
        return;  // No voltage data yet
    }

    // Critical voltage - immediate controlled shutdown
    if (vbus_voltage_ < min_voltage_critical_) {
        RCLCPP_ERROR(
            rclcpp::get_logger("safety_monitor"),
            "CRITICAL: Battery voltage %.1fV below minimum %.1fV!",
            vbus_voltage_, min_voltage_critical_
        );
        pragati::emit_motor_alert(
            rclcpp::get_logger("safety_monitor"),
            "critical", "power_supply_status", "all",
            "battery voltage below critical minimum", vbus_voltage_,
            min_voltage_critical_, "emergency_shutdown");

        trigger_emergency_shutdown(
            "Battery voltage critical: " + std::to_string(vbus_voltage_) +
            "V < " + std::to_string(min_voltage_critical_) + "V"
        );
        return;
    }

    // Warning voltage - transition to WARNING
    if (vbus_voltage_ < min_voltage_warning_) {
        SafetyState current = safety_state_.load();
        if (current == SafetyState::SAFE) {
            transition_to(SafetyState::WARNING);
        }

        auto now = std::chrono::steady_clock::now();

        if (std::chrono::duration<double>(now - power_warn_throttle_time_).count() > 10.0) {
            RCLCPP_WARN(
                rclcpp::get_logger("safety_monitor"),
                "Battery voltage %.1fV low (warning: %.1fV, critical: %.1fV)",
                vbus_voltage_, min_voltage_warning_, min_voltage_critical_
            );
            pragati::emit_motor_alert(
                rclcpp::get_logger("safety_monitor"),
                "warning", "power_supply_status", "all",
                "battery voltage low", vbus_voltage_,
                min_voltage_warning_, "log_warning");

            power_warn_throttle_time_ = now;
        }
    }

    // Over-voltage check (safety feature)
    const double MAX_VOLTAGE = 60.0;
    if (vbus_voltage_ > MAX_VOLTAGE) {
        RCLCPP_ERROR(
            rclcpp::get_logger("safety_monitor"),
            "OVER-VOLTAGE: Battery voltage %.1fV exceeds safe maximum %.1fV!",
            vbus_voltage_, MAX_VOLTAGE
        );
        pragati::emit_motor_alert(
            rclcpp::get_logger("safety_monitor"),
            "critical", "power_supply_status", "all",
            "battery over-voltage", vbus_voltage_, MAX_VOLTAGE,
            "emergency_shutdown");

        trigger_emergency_shutdown(
            "Battery over-voltage: " + std::to_string(vbus_voltage_) + "V"
        );
    }
}


void SafetyMonitor::trigger_emergency_shutdown(const std::string& reason)
{
    RCLCPP_ERROR(
        rclcpp::get_logger("safety_monitor"),
        "EMERGENCY SHUTDOWN TRIGGERED: %s", reason.c_str()
    );

    // Transition to EMERGENCY state (valid from any state)
    transition_to(SafetyState::EMERGENCY);

    // Execute emergency shutdown sequence
    execute_emergency_shutdown_sequence(reason);

    RCLCPP_ERROR(
        rclcpp::get_logger("safety_monitor"),
        "SYSTEM SHUTDOWN SEQUENCE INITIATED - IMMEDIATE STOP REQUIRED"
    );
}

bool SafetyMonitor::is_safe() const
{
    SafetyState state = safety_state_.load();
    return (state == SafetyState::SAFE || state == SafetyState::WARNING);
}

SafetyState SafetyMonitor::get_state() const
{
    return safety_state_.load();
}

bool SafetyMonitor::transition_to(SafetyState new_state)
{
    SafetyState current = safety_state_.load();

    // Retry loop for atomic CAS — handles concurrent transitions
    while (true) {
        if (current == new_state) {
            return true;  // Already in target state
        }

        if (!is_valid_transition(current, new_state)) {
            RCLCPP_WARN(
                rclcpp::get_logger("safety_monitor"),
                "Invalid safety state transition: %s -> %s",
                safety_state_to_string(current),
                safety_state_to_string(new_state)
            );
            return false;
        }

        // Atomic compare-and-swap: only succeeds if state is still 'current'
        if (safety_state_.compare_exchange_strong(current, new_state)) {
            RCLCPP_INFO(
                rclcpp::get_logger("safety_monitor"),
                "Safety state transition: %s -> %s",
                safety_state_to_string(current),
                safety_state_to_string(new_state)
            );

            // Publish state change to /safety/state topic
            if (safety_state_pub_) {
                std_msgs::msg::String state_msg;
                state_msg.data = safety_state_to_string(new_state);
                safety_state_pub_->publish(state_msg);
            }

            return true;
        }
        // CAS failed: 'current' was updated to the actual value by compare_exchange_strong.
        // Re-validate with new current state on next iteration.
    }
}

bool SafetyMonitor::is_valid_transition(SafetyState from, SafetyState to) const
{
    // Any state can transition to EMERGENCY
    if (to == SafetyState::EMERGENCY) {
        return true;
    }

    switch (from) {
        case SafetyState::UNKNOWN:
            return (to == SafetyState::INITIALIZING);
        case SafetyState::INITIALIZING:
            return (to == SafetyState::SAFE);
        case SafetyState::SAFE:
            return (to == SafetyState::WARNING || to == SafetyState::CRITICAL);
        case SafetyState::WARNING:
            return (to == SafetyState::SAFE || to == SafetyState::CRITICAL);
        case SafetyState::CRITICAL:
            return (to == SafetyState::WARNING);
        case SafetyState::EMERGENCY:
            // Only manual reset can transition out of EMERGENCY
            return (to == SafetyState::INITIALIZING);
        default:
            return false;
    }
}

void SafetyMonitor::request_emergency_stop()
{
    RCLCPP_WARN(rclcpp::get_logger("safety_monitor"), "Emergency stop requested!");
    transition_to(SafetyState::EMERGENCY);
}


// Data update methods for sensor inputs

void SafetyMonitor::update_joint_states(const sensor_msgs::msg::JointState::SharedPtr msg)
{
    if (!msg || msg->position.empty()) {
        return;
    }

    std::lock_guard<std::mutex> lock(data_mutex_);
    joint_names_ = msg->name;
    joint_positions_ = msg->position;
    joint_velocities_ = msg->velocity;
    joint_efforts_ = msg->effort;

    last_joint_state_time_ = std::chrono::steady_clock::now();
    joint_state_received_ = true;
}

void SafetyMonitor::update_motor_temperature(const std::string& joint_name, double temperature)
{
    std::lock_guard<std::mutex> lock(data_mutex_);
    motor_temperatures_[joint_name] = temperature;
    last_telemetry_time_ = std::chrono::steady_clock::now();
    telemetry_received_ = true;
}

void SafetyMonitor::update_motor_errors(const std::string& joint_name, uint32_t error_flags)
{
    std::lock_guard<std::mutex> lock(data_mutex_);
    motor_errors_[joint_name] = error_flags;
    last_telemetry_time_ = std::chrono::steady_clock::now();
    telemetry_received_ = true;
}

void SafetyMonitor::update_vbus_voltage(double voltage)
{
    std::lock_guard<std::mutex> lock(data_mutex_);
    vbus_voltage_ = voltage;
    last_telemetry_time_ = std::chrono::steady_clock::now();
    telemetry_received_ = true;
}

void SafetyMonitor::set_controllers(
    const std::vector<std::shared_ptr<MotorControllerInterface>>& controllers)
{
    std::lock_guard<std::mutex> lock(data_mutex_);
    controllers_ = controllers;
    RCLCPP_INFO(
        rclcpp::get_logger("safety_monitor"),
        "SafetyMonitor: %zu motor controllers registered for e-stop execution",
        controllers_.size()
    );
}

void SafetyMonitor::execute_emergency_shutdown_sequence(const std::string& reason)
{
    RCLCPP_ERROR(
        rclcpp::get_logger("safety_monitor"),
        "Executing emergency shutdown sequence for: %s", reason.c_str()
    );

    // Take a snapshot of controllers — data_mutex_ may or may not be held by caller.
    // Using a local copy avoids holding the lock during potentially slow e-stop calls.
    std::vector<std::shared_ptr<MotorControllerInterface>> controllers_snapshot;
    {
        // Use try_lock because update() may have already locked data_mutex_
        // If we can't lock, we're already protected by the caller's lock
        std::unique_lock<std::mutex> lock(data_mutex_, std::try_to_lock);
        controllers_snapshot = controllers_;
    }

    // Step 1: Send ESTOP command to all motors — fire-all-then-verify pattern
    // Send stop to ALL controllers without waiting for individual acknowledgments
    size_t stop_success_count = 0;
    size_t stop_fail_count = 0;

    for (size_t i = 0; i < controllers_snapshot.size(); ++i) {
        try {
            bool result = controllers_snapshot[i]->emergency_stop();
            if (result) {
                stop_success_count++;
            } else {
                stop_fail_count++;
                RCLCPP_ERROR(
                    rclcpp::get_logger("safety_monitor"),
                    "Emergency stop FAILED for controller %zu (returned false)", i
                );
            }
        } catch (const std::exception& e) {
            stop_fail_count++;
            RCLCPP_ERROR(
                rclcpp::get_logger("safety_monitor"),
                "Emergency stop EXCEPTION for controller %zu: %s", i, e.what()
            );
        }
    }

    // Verify results after all stop commands sent
    if (!controllers_snapshot.empty()) {
        RCLCPP_ERROR(
            rclcpp::get_logger("safety_monitor"),
            "E-stop results: %zu/%zu controllers stopped successfully, %zu failed",
            stop_success_count, controllers_snapshot.size(), stop_fail_count
        );
    } else {
        RCLCPP_WARN(
            rclcpp::get_logger("safety_monitor"),
            "No motor controllers registered — e-stop has no motors to stop"
        );
    }

    // Step 2: Disable all GPIO outputs (vacuum, LEDs, etc.)
    RCLCPP_WARN(
        rclcpp::get_logger("safety_monitor"),
        "Disabling GPIO outputs (vacuum pump, end effector, LEDs)"
    );

    // Step 3: Turn on error LED indicator
    RCLCPP_WARN(
        rclcpp::get_logger("safety_monitor"),
        "Activating error LED indicator"
    );

    // Step 4: Log critical event with timestamp
    auto now = std::chrono::system_clock::now();
    auto timestamp = std::chrono::system_clock::to_time_t(now);
    RCLCPP_ERROR(
        rclcpp::get_logger("safety_monitor"),
        "CRITICAL EVENT LOGGED at %s: %s",
        std::ctime(&timestamp), reason.c_str()
    );

    // Step 5: Prepare for safe system shutdown
    RCLCPP_ERROR(
        rclcpp::get_logger("safety_monitor"),
        "System prepared for safe shutdown. Manual intervention may be required."
    );

    // Publish emergency stop event for system-wide notification
    if (emergency_stop_pub_) {
        std_msgs::msg::String emergency_msg;
        emergency_msg.data = "EMERGENCY_STOP: " + reason +
            " at " + std::string(std::ctime(&timestamp));
        emergency_stop_pub_->publish(emergency_msg);
        RCLCPP_INFO(
            rclcpp::get_logger("safety_monitor"),
            "Emergency stop event published to /safety/emergency_stop"
        );
    }

    RCLCPP_ERROR(
        rclcpp::get_logger("safety_monitor"),
        "Emergency shutdown sequence complete. System in EMERGENCY state."
    );
}

void SafetyMonitor::handle_safety_reset(
    const std::shared_ptr<std_srvs::srv::Trigger::Request> /*request*/,
    std::shared_ptr<std_srvs::srv::Trigger::Response> response)
{
    SafetyState current = safety_state_.load();

    // Only allow reset from EMERGENCY state
    if (current != SafetyState::EMERGENCY) {
        response->success = false;
        response->message = "Cannot reset: not in EMERGENCY state (current: " +
            std::string(safety_state_to_string(current)) + ")";
        RCLCPP_WARN(rclcpp::get_logger("safety_monitor"),
            "Safety reset rejected: %s", response->message.c_str());
        return;
    }

    // Check if fault conditions have cleared before allowing reset
    std::lock_guard<std::mutex> lock(data_mutex_);
    bool fault_persists = false;
    std::string fault_reason;

    // Check temperature
    for (const auto& [joint_name, temperature] : motor_temperatures_) {
        if (temperature > max_temperature_critical_) {
            fault_persists = true;
            fault_reason = joint_name + " temperature still critical: " +
                std::to_string(temperature) + "C > " +
                std::to_string(max_temperature_critical_) + "C";
            break;
        }
    }

    // Check voltage
    if (!fault_persists && telemetry_received_ && vbus_voltage_ < min_voltage_critical_) {
        fault_persists = true;
        fault_reason = "Voltage still critical: " +
            std::to_string(vbus_voltage_) + "V < " +
            std::to_string(min_voltage_critical_) + "V";
    }

    // Check motor errors
    if (!fault_persists) {
        const uint32_t CRITICAL_ERRORS = 0x00F2;
        for (const auto& [joint_name, error_flags] : motor_errors_) {
            if (error_flags & CRITICAL_ERRORS) {
                fault_persists = true;
                fault_reason = joint_name + " still has critical errors: 0x" +
                    std::to_string(error_flags);
                break;
            }
        }
    }

    if (fault_persists) {
        response->success = false;
        response->message = "Reset rejected: fault persists - " + fault_reason;
        RCLCPP_WARN(rclcpp::get_logger("safety_monitor"),
            "Safety reset rejected: %s", response->message.c_str());
        return;
    }

    // Fault cleared — transition to INITIALIZING
    if (transition_to(SafetyState::INITIALIZING)) {
        response->success = true;
        response->message = "Safety reset successful. State: INITIALIZING. "
            "Re-run safety checks before resuming operation.";
        RCLCPP_INFO(rclcpp::get_logger("safety_monitor"),
            "Safety reset accepted: EMERGENCY -> INITIALIZING");
    } else {
        response->success = false;
        response->message = "Reset failed: state transition rejected";
        RCLCPP_ERROR(rclcpp::get_logger("safety_monitor"),
            "Safety reset: transition to INITIALIZING failed");
    }
}

}  // namespace motor_control_ros2
