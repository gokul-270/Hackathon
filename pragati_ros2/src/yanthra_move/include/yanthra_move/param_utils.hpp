// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#pragma once

#include <rclcpp/rclcpp.hpp>
#include <limits>
#include <string>

namespace yanthra_move {
namespace param_utils {

/**
 * @brief Helper to get parameter value with correct type casting
 * 
 * ROS2 parameters use specific as_*() methods instead of template as<T>()
 */
template<typename T>
T get_param_value(const rclcpp::Parameter& param);

template<>
inline double get_param_value<double>(const rclcpp::Parameter& param) {
    return param.as_double();
}

template<>
inline float get_param_value<float>(const rclcpp::Parameter& param) {
    return static_cast<float>(param.as_double());
}

template<>
inline int get_param_value<int>(const rclcpp::Parameter& param) {
    return static_cast<int>(param.as_int());
}

template<>
inline bool get_param_value<bool>(const rclcpp::Parameter& param) {
    return param.as_bool();
}

template<>
inline std::string get_param_value<std::string>(const rclcpp::Parameter& param) {
    return param.as_string();
}

/**
 * @brief Safe parameter getter with validation and defaults
 * 
 * Reduces 220+ lines of try/catch boilerplate to simple one-liners.
 * Automatically handles missing parameters, range validation, and logging.
 * 
 * Usage:
 *   using yanthra_move::param_utils::get_param_safe;
 *   double delay = get_param_safe(*node, "delays/picking", 0.2, 0.0, 10.0);
 * 
 * @tparam T Parameter type (double, int, bool, string)
 * @param node ROS2 node to get parameter from
 * @param name Parameter name
 * @param default_val Default value if parameter not found or invalid
 * @param min_val Minimum valid value (for numeric types)
 * @param max_val Maximum valid value (for numeric types)
 * @return T Parameter value or default
 */
template<typename T>
T get_param_safe(rclcpp::Node& node, 
                 const std::string& name, 
                 T default_val,
                 T min_val = std::numeric_limits<T>::lowest(),
                 T max_val = std::numeric_limits<T>::max()) {
    try {
        if (!node.has_parameter(name)) {
            RCLCPP_DEBUG(node.get_logger(), 
                        "Parameter '%s' not found, using default", 
                        name.c_str());
            return default_val;
        }
        
        T value = get_param_value<T>(node.get_parameter(name));
        
        // Range validation for numeric types
        if constexpr (std::is_arithmetic_v<T>) {
            if (value < min_val || value > max_val) {
                RCLCPP_WARN(node.get_logger(), 
                           "Parameter '%s' out of range, using default",
                           name.c_str());
                return default_val;
            }
        }
        
        return value;
    } catch (const rclcpp::exceptions::ParameterNotDeclaredException& e) {
        RCLCPP_DEBUG(node.get_logger(), 
                    "Parameter '%s' not declared, using default", 
                    name.c_str());
        return default_val;
    } catch (const std::exception& e) {
        RCLCPP_WARN(node.get_logger(), 
                   "Error reading parameter '%s': %s, using default", 
                   name.c_str(), e.what());
        return default_val;
    }
}

}} // namespace yanthra_move::param_utils
