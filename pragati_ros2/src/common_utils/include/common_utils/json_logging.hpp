// Copyright 2025 Pragati Robotics Team
// SPDX-License-Identifier: Apache-2.0
//
// Shared JSON logging helpers for structured field-trial logs.
// Header-only — include and use, no linking needed.
//
// Standard envelope fields: event, ts, node, arm_id
// Domain fields use snake_case with unit suffixes: current_a, temp_c, duration_ms
//
// See docs/JSON_LOG_CONVENTIONS.md for field naming conventions

#pragma once

#include <chrono>
#include <cstdint>
#include <string>

#include <nlohmann/json.hpp>
#include <rclcpp/logging.hpp>

namespace pragati {

/// Return current UTC epoch time in milliseconds.
inline int64_t epoch_ms_now()
{
  auto now = std::chrono::system_clock::now();
  return std::chrono::duration_cast<std::chrono::milliseconds>(
             now.time_since_epoch())
      .count();
}

/// Build a JSON envelope with standard fields.
/// @param event   Event name (e.g. "motor_alert", "detection_summary")
/// @param node_name  ROS2 node name
/// @param arm_id  Optional arm identifier (empty string if not applicable)
inline nlohmann::json json_envelope(
    const std::string& event,
    const std::string& node_name,
    const std::string& arm_id = "")
{
  nlohmann::json j;
  j["event"] = event;
  j["ts"] = epoch_ms_now();
  j["node"] = node_name;
  if (!arm_id.empty()) {
    j["arm_id"] = arm_id;
  }
  return j;
}

/// Emit a structured motor_alert via RCLCPP_WARN.
/// Replaces the 12+ copy-pasted alert blocks in safety_monitor.cpp.
inline void emit_motor_alert(
    const rclcpp::Logger& logger,
    const std::string& severity,
    const std::string& check,
    const std::string& joint,
    const std::string& detail,
    double value,
    double threshold,
    const std::string& action)
{
  auto alert = json_envelope("motor_alert", logger.get_name());
  alert["severity"] = severity;
  alert["check"] = check;
  alert["joint"] = joint;
  alert["detail"] = detail;
  alert["value"] = value;
  alert["threshold"] = threshold;
  alert["action"] = action;
  RCLCPP_WARN(logger, "%s", alert.dump().c_str());
}

/// Emit a structured timing event via RCLCPP_INFO.
inline void emit_timing_event(
    const rclcpp::Logger& logger,
    const std::string& node_name,
    const std::string& operation,
    double duration_ms,
    const nlohmann::json& extra = nlohmann::json::object())
{
  auto j = json_envelope("timing", node_name);
  j["operation"] = operation;
  j["duration_ms"] = duration_ms;
  j.update(extra);
  RCLCPP_INFO(logger, "%s", j.dump().c_str());
}

/// Emit a structured health_summary event via RCLCPP_INFO.
inline void emit_health_summary(
    const rclcpp::Logger& logger,
    const std::string& node_name,
    const std::string& component,
    const std::string& status,
    const nlohmann::json& extra = nlohmann::json::object())
{
  auto j = json_envelope("health_summary", node_name);
  j["component"] = component;
  j["status"] = status;
  j.update(extra);
  RCLCPP_INFO(logger, "%s", j.dump().c_str());
}

}  // namespace pragati
