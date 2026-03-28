/*
 * Copyright (c) 2024 Pragati Robotics
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

#ifndef ODRIVE_CONTROL_ROS2__MG6010_CAN_INTERFACE_HPP_
#define ODRIVE_CONTROL_ROS2__MG6010_CAN_INTERFACE_HPP_

#include "motor_control_ros2/motor_abstraction.hpp"

#include <linux/can.h>

#include <chrono>
#include <deque>
#include <functional>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

// Forward-declare epoll_event to avoid pulling <sys/epoll.h> into the header
struct epoll_event;

namespace motor_control_ros2
{

/**
 * @brief CAN interface implementation for MG6010 motors
 *
 * This class provides a lightweight wrapper around Linux SocketCAN
 * specifically designed for MG6010 motor communication.
 */
class MG6010CANInterface : public CANInterface
{
public:
  MG6010CANInterface();
  virtual ~MG6010CANInterface();

  // CANInterface implementation
  bool initialize(const std::string & interface_name, uint32_t baud_rate = 1000000) override;
  bool send_message(uint32_t id, const std::vector<uint8_t> & data) override;
  bool receive_message(uint32_t & id, std::vector<uint8_t> & data, int timeout_ms = 10) override;
  bool configure_node(uint8_t node_id, uint32_t baud_rate = 0) override;
  bool is_connected() const override;
  std::string get_last_error() const override;

  // CAN bus resilience (tasks 1.4, 1.5)
  bool attemptReconnection();
  void setConnectionStatusCallback(std::function<void(bool)> callback);

  // CAN error diagnostics
  uint64_t get_can_error_count() const;
  std::string get_interface_name() const { return interface_name_; }

  // CAN frame response buffer (tasks 6.2, 6.3)
  static constexpr size_t MAX_BUFFERED_FRAMES_PER_MOTOR = 16;
  bool getBufferedResponse(uint32_t expected_id, std::vector<uint8_t> & data);
  void bufferCurrentFrame(uint32_t id, const std::vector<uint8_t> & data);

  /**
   * @brief Expose epoll fd for protocol-layer epoll_wait.
   *
   * The CAN interface owns the epoll instance; the protocol layer uses it in
   * wait_response() instead of busy-polling.  Returns -1 when epoll is not
   * available (e.g. unit-test builds with mock interfaces).
   */
  int get_epoll_fd() const { return epoll_fd_; }

  /**
   * @brief Bus-level transaction mutex for atomic send+receive.
   *
   * With MultiThreadedExecutor, multiple threads (control_loop, action feedback,
   * motion_feedback) can call send_message() + receive_message() concurrently.
   * The per-call mutex_ prevents data corruption but not response interleaving:
   * thread A sends to motor 1, thread B sends to motor 2 before motor 1 replies,
   * causing cross-motor response buffering that overflows at high rates.
   *
   * Protocol-layer callers (send_and_wait) must hold this lock for the entire
   * send+wait_response duration to serialize CAN bus transactions.
   */
  std::mutex& transaction_mutex() { return transaction_mutex_; }

private:
  int can_socket_;
  int epoll_fd_;  // epoll instance for efficient CAN receive (task 2.1)
  std::string interface_name_;
  uint32_t baud_rate_;
  bool connected_;
  std::string last_error_;
  mutable std::mutex mutex_;
  std::mutex transaction_mutex_;  // Bus-level lock for atomic send+receive

  // CAN error tracking (task 1.2)
  uint64_t can_error_count_;

  // CAN reconnection state (task 1.4)
  uint32_t reconnect_backoff_ms_;
  std::chrono::steady_clock::time_point last_reconnect_attempt_;

  // Connection status callback (task 1.5)
  std::function<void(bool)> connection_status_callback_;

  // CAN frame response buffer (task 6.2)
  std::unordered_map<uint32_t, std::deque<struct can_frame>> response_buffer_;

  // Cached SO_RCVTIMEO value to avoid redundant setsockopt calls (D4: can-io-efficiency)
  int last_rcvtimeo_ms_ = 10;  // Default matches setup_can_socket()'s 10ms

  // Helper methods
  bool setup_can_socket();
  void close_can_socket();
  void set_error(const std::string & error);
  void bufferFrame(const struct can_frame & frame);
};

}  // namespace motor_control_ros2

#endif  // ODRIVE_CONTROL_ROS2__MG6010_CAN_INTERFACE_HPP_
