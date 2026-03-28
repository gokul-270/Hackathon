// Copyright 2025 Pragati Robotics
// SocketCAN Interface for ODrive CANSimple communication

#ifndef ODRIVE_CONTROL_ROS2__SOCKETCAN_INTERFACE_HPP_
#define ODRIVE_CONTROL_ROS2__SOCKETCAN_INTERFACE_HPP_

#include <string>
#include <vector>
#include <cstdint>
#include <functional>
#include <linux/can.h>
#include <linux/can/raw.h>

namespace odrive_cansimple {

/**
 * @brief SocketCAN interface for ODrive communication
 *
 * Provides:
 * - CAN frame TX/RX
 * - RX filtering for specific node_ids
 * - Non-blocking receive with timeout
 * - RTR (Remote Transmission Request) support
 */
class SocketCANInterface {
public:
  SocketCANInterface();
  virtual ~SocketCANInterface();

  /**
   * @brief Initialize CAN interface
   * @param interface_name CAN interface name (e.g., "can0")
   * @param node_ids List of ODrive node IDs to filter (0-63)
   * @return true if successful
   */
  bool initialize(const std::string& interface_name, const std::vector<uint8_t>& node_ids);

  /**
   * @brief Close CAN interface
   */
  void close();

  /**
   * @brief Send CAN frame
   * @param arb_id CAN arbitration ID (11-bit standard)
   * @param data Frame data (0-8 bytes)
   * @param is_rtr Remote transmission request flag
   * @return true if sent successfully
   */
  virtual bool send_frame(uint16_t arb_id, const std::vector<uint8_t>& data, bool is_rtr = false);

  /**
   * @brief Receive CAN frame (non-blocking with timeout)
   * @param arb_id Output: received arbitration ID
   * @param data Output: received data
   * @param timeout_ms Timeout in milliseconds (0 = no wait, -1 = block forever)
   * @return true if frame received
   */
  virtual bool receive_frame(uint16_t& arb_id, std::vector<uint8_t>& data, int timeout_ms = 100);

  /**
   * @brief Check if interface is open
   */
  bool is_open() const { return socket_fd_ >= 0; }

  /**
   * @brief Get interface name
   */
  std::string get_interface_name() const { return interface_name_; }

private:
  /**
   * @brief Apply CAN filters for specified node IDs
   * @param node_ids List of node IDs to accept
   * @return true if filters applied successfully
   */
  bool apply_filters(const std::vector<uint8_t>& node_ids);

  int socket_fd_;
  std::string interface_name_;
  std::vector<uint8_t> configured_node_ids_;
};

}  // namespace odrive_cansimple

#endif  // ODRIVE_CONTROL_ROS2__SOCKETCAN_INTERFACE_HPP_
