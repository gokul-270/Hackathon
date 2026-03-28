/*
 * Copyright (c) 2024 Open Source Robotics Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef MOTOR_CONTROL_ROS2__CAN_INTERFACE_HPP_
#define MOTOR_CONTROL_ROS2__CAN_INTERFACE_HPP_

#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace motor_control_ros2
{

class CANInterface
{
public:
  virtual ~CANInterface() = default;

  /**
   * @brief Initialize CAN interface
   * @param interface_name CAN interface name (e.g., "can0")
   * @param baud_rate CAN bus baud rate
   * @return true if successful
   */
  virtual bool initialize(const std::string & interface_name, uint32_t baud_rate = 1000000) = 0;

  /**
   * @brief Send CAN message
   * @param id CAN message ID
   * @param data Message data bytes
   * @return true if successful
   */
  virtual bool send_message(uint32_t id, const std::vector<uint8_t> & data) = 0;

  /**
   * @brief Receive CAN message (blocking with timeout)
   * @param id [out] Received message ID
   * @param data [out] Received message data
   * @param timeout_ms Timeout in milliseconds
   * @return true if message received
   */
  virtual bool receive_message(uint32_t & id, std::vector<uint8_t> & data, int timeout_ms = 10) = 0;

  /**
   * @brief Configure CAN node parameters
   * @param node_id CAN node ID to configure
   * @param baud_rate Node-specific baud rate (if supported)
   * @return true if successful
   */
  virtual bool configure_node(uint8_t node_id, uint32_t baud_rate = 0) = 0;

  /**
   * @brief Check if CAN interface is connected
   * @return true if connected and operational
   */
  virtual bool is_connected() const = 0;

  /**
   * @brief Get last error message
   * @return Error description string
   */
  virtual std::string get_last_error() const = 0;
};

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2__CAN_INTERFACE_HPP_
