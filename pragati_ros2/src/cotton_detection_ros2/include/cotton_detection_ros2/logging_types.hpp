#pragma once

#include <functional>
#include <string>

namespace cotton_detection {

/**
 * @brief Log level for camera component logging
 */
enum class LogLevel { DEBUG, INFO, WARN, ERROR };

/**
 * @brief Logger callback type for ROS2 integration
 */
using LoggerCallback = std::function<void(LogLevel, const std::string&)>;

}  // namespace cotton_detection
