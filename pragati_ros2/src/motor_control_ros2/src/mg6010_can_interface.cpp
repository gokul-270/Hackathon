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

#include "motor_control_ros2/mg6010_can_interface.hpp"

#include <linux/can.h>
#include <linux/can/raw.h>
#include <linux/can/error.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <sys/epoll.h>
#include <net/if.h>
#include <unistd.h>
#include <cstring>
#include <iostream>
#include <rclcpp/rclcpp.hpp>

namespace motor_control_ros2
{

MG6010CANInterface::MG6010CANInterface()
: can_socket_(-1),
  epoll_fd_(-1),
  interface_name_(""),
  baud_rate_(500000),
  connected_(false),
  last_error_(""),
  can_error_count_(0),
  reconnect_backoff_ms_(100)
{
}

MG6010CANInterface::~MG6010CANInterface()
{
  close_can_socket();
}

bool MG6010CANInterface::initialize(const std::string & interface_name, uint32_t baud_rate)
{
  std::lock_guard<std::mutex> lock(mutex_);

  interface_name_ = interface_name;
  baud_rate_ = baud_rate;

  if (!setup_can_socket()) {
    return false;
  }

  connected_ = true;
  return true;
}

bool MG6010CANInterface::setup_can_socket()
{
  // Create socket
  can_socket_ = socket(PF_CAN, SOCK_RAW, CAN_RAW);
  if (can_socket_ < 0) {
    set_error("Failed to create CAN socket: " + std::string(strerror(errno)));
    return false;
  }

  // Get interface index
  struct ifreq ifr;
  std::strncpy(ifr.ifr_name, interface_name_.c_str(), IFNAMSIZ - 1);
  ifr.ifr_name[IFNAMSIZ - 1] = '\0';

  if (ioctl(can_socket_, SIOCGIFINDEX, &ifr) < 0) {
    set_error("Failed to get interface index for " + interface_name_ + ": " +
              std::string(strerror(errno)));
    close(can_socket_);
    can_socket_ = -1;
    return false;
  }

  // Bind socket to CAN interface
  struct sockaddr_can addr;
  std::memset(&addr, 0, sizeof(addr));
  addr.can_family = AF_CAN;
  addr.can_ifindex = ifr.ifr_ifindex;

  if (bind(can_socket_, reinterpret_cast<struct sockaddr *>(&addr), sizeof(addr)) < 0) {
    set_error("Failed to bind socket to " + interface_name_ + ": " +
              std::string(strerror(errno)));
    close(can_socket_);
    can_socket_ = -1;
    return false;
  }

  // Enable CAN error frame reception for bus-off and controller error detection (D1).
  // The Linux kernel generates error frames when hardware detects bus-off, controller
  // errors, or TX timeouts. Without this filter, those frames are silently dropped.
  can_err_mask_t err_mask = CAN_ERR_BUSOFF | CAN_ERR_CRTL | CAN_ERR_TX_TIMEOUT;
  if (setsockopt(can_socket_, SOL_CAN_RAW, CAN_RAW_ERR_FILTER,
                 &err_mask, sizeof(err_mask)) < 0) {
    set_error("Failed to set CAN error filter: " + std::string(strerror(errno)));
    // Non-fatal: we lose error detection but can still communicate
  }

  // Set socket to non-blocking mode for receive with timeout
  struct timeval tv;
  tv.tv_sec = 0;
  tv.tv_usec = 10000;  // 10ms default timeout
  setsockopt(can_socket_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

  // Disable CAN loopback to prevent TX echo wakeups (D1: can-tx-echo-filter).
  // Linux SocketCAN echoes every transmitted frame back to the sending socket by
  // default.  This causes spurious epoll_wait() wakeups in wait_response() when
  // motors are absent (no real RX data), burning ~65% CPU on RPi 4B.  Disabling
  // loopback is per-socket and does not affect other CAN users (candump, ODrive).
  int loopback = 0;
  if (setsockopt(can_socket_, SOL_CAN_RAW, CAN_RAW_LOOPBACK,
                 &loopback, sizeof(loopback)) < 0) {
    RCLCPP_WARN(rclcpp::get_logger("motor_control"),
      "MG6010CANInterface: Failed to disable CAN_RAW_LOOPBACK: %s", strerror(errno));
    // Non-fatal: loopback frames waste CPU but don't break functionality
  }
  int recv_own_msgs = 0;
  if (setsockopt(can_socket_, SOL_CAN_RAW, CAN_RAW_RECV_OWN_MSGS,
                 &recv_own_msgs, sizeof(recv_own_msgs)) < 0) {
    RCLCPP_WARN(rclcpp::get_logger("motor_control"),
      "MG6010CANInterface: Failed to disable CAN_RAW_RECV_OWN_MSGS: %s", strerror(errno));
  }

  // Create epoll instance and register the CAN socket for read readiness (task 2.1).
  // The protocol layer uses epoll_wait() in wait_response() instead of busy-polling.
  // Close any stale epoll fd from a previous failed setup or reconnection.
  if (epoll_fd_ >= 0) {
    close(epoll_fd_);
    epoll_fd_ = -1;
  }
  epoll_fd_ = epoll_create1(EPOLL_CLOEXEC);
  if (epoll_fd_ < 0) {
    set_error("Failed to create epoll instance: " + std::string(strerror(errno)));
    close(can_socket_);
    can_socket_ = -1;
    return false;
  }
  struct epoll_event ev;
  ev.events = EPOLLIN;
  ev.data.fd = can_socket_;
  if (epoll_ctl(epoll_fd_, EPOLL_CTL_ADD, can_socket_, &ev) < 0) {
    set_error("Failed to add CAN socket to epoll: " + std::string(strerror(errno)));
    close(epoll_fd_);
    epoll_fd_ = -1;
    close(can_socket_);
    can_socket_ = -1;
    return false;
  }

  return true;
}

void MG6010CANInterface::close_can_socket()
{
  // Use try_lock to prevent deadlock if another thread holds mutex_ (e.g.,
  // during send/receive). In destructor context, best-effort close is acceptable.
  std::unique_lock<std::mutex> lock(mutex_, std::try_to_lock);
  if (!lock.owns_lock()) {
    // Could not acquire lock — another thread is using the socket.
    // Set connected_ to false (atomic-safe flag) so the other thread stops,
    // then close the socket directly (close() is thread-safe on the fd).
    connected_ = false;
    if (epoll_fd_ >= 0) {
      close(epoll_fd_);
      epoll_fd_ = -1;
    }
    if (can_socket_ >= 0) {
      close(can_socket_);
      can_socket_ = -1;
    }
    return;
  }

  // Close epoll fd before socket (task 2.4)
  if (epoll_fd_ >= 0) {
    close(epoll_fd_);
    epoll_fd_ = -1;
  }
  if (can_socket_ >= 0) {
    close(can_socket_);
    can_socket_ = -1;
  }
  connected_ = false;
}

bool MG6010CANInterface::send_message(uint32_t id, const std::vector<uint8_t> & data)
{
  std::unique_lock<std::mutex> lock(mutex_);

  if (!connected_ || can_socket_ < 0) {
    set_error("CAN bus disconnected - reconnection in progress");
    return false;
  }

  if (data.size() > 8) {
    set_error("CAN data size exceeds 8 bytes");
    return false;
  }

  struct can_frame frame;
  std::memset(&frame, 0, sizeof(frame));

  frame.can_id = id;
  frame.can_dlc = data.size();
  std::memcpy(frame.data, data.data(), data.size());

  ssize_t bytes_written = write(can_socket_, &frame, sizeof(frame));
  if (bytes_written != sizeof(frame)) {
    connected_ = false;
    set_error("CAN write failure (disconnected): " + std::string(strerror(errno)));
    // Notify controller of disconnection outside the lock
    auto callback = connection_status_callback_;
    lock.unlock();
    if (callback) {
      callback(false);
    }
    return false;
  }

  return true;
}

bool MG6010CANInterface::receive_message(
  uint32_t & id,
  std::vector<uint8_t> & data,
  int timeout_ms)
{
  std::unique_lock<std::mutex> lock(mutex_);

  if (!connected_ || can_socket_ < 0) {
    set_error("CAN bus disconnected - reconnection in progress");
    return false;
  }

  // Note: SO_RCVTIMEO is set once in setup_can_socket() with a default 10ms timeout.
  // Per-call timeout override: apply caller's timeout_ms to SO_RCVTIMEO when it differs
  // from the cached value.  A value of -1 or 0 reverts to the default 10ms (D4).
  int effective_timeout_ms = (timeout_ms <= 0) ? 10 : timeout_ms;
  if (effective_timeout_ms != last_rcvtimeo_ms_) {
    struct timeval tv;
    tv.tv_sec = effective_timeout_ms / 1000;
    tv.tv_usec = (effective_timeout_ms % 1000) * 1000;
    if (setsockopt(can_socket_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) == 0) {
      last_rcvtimeo_ms_ = effective_timeout_ms;
    }
  }

  struct can_frame frame;
  std::memset(&frame, 0, sizeof(frame));

  ssize_t bytes_read = read(can_socket_, &frame, sizeof(frame));

  if (bytes_read < 0) {
    if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
      // Timeout or interrupted syscall (e.g., SIGINT/SIGTERM during shutdown).
      // Treat as a non-fatal "no message" condition.
      return false;
    }
    set_error("Failed to receive CAN message: " + std::string(strerror(errno)));
    return false;
  }

  if (bytes_read < static_cast<ssize_t>(sizeof(frame))) {
    set_error("Incomplete CAN frame received");
    return false;
  }

  // Check for CAN error frames (task 1.2 — D1: bus-off and controller error detection).
  // Error frames have CAN_ERR_FLAG set in can_id and are generated by the kernel when
  // SO_CAN_ERR_FILTER is configured (task 1.1).
  if (frame.can_id & CAN_ERR_FLAG) {
    can_error_count_++;

    if (frame.can_id & CAN_ERR_BUSOFF) {
      connected_ = false;
      set_error("CAN bus-off detected — marking disconnected");
      auto callback = connection_status_callback_;
      lock.unlock();
      if (callback) {
        callback(false);
      }
      return false;
    }

    if (frame.can_id & CAN_ERR_CRTL) {
      // Controller error (error-passive or error-warning) — log but stay connected.
      // data[1] contains the controller-specific error flags.
      uint8_t ctrl_err = (frame.can_dlc > 1) ? frame.data[1] : 0;
      RCLCPP_WARN(rclcpp::get_logger("motor_control"),
        "MG6010CANInterface: CAN controller error (ctrl_err=0x%X, error_count=%lu)",
        static_cast<int>(ctrl_err), static_cast<unsigned long>(can_error_count_));
    }

    if (frame.can_id & CAN_ERR_TX_TIMEOUT) {
      RCLCPP_WARN(rclcpp::get_logger("motor_control"),
        "MG6010CANInterface: CAN TX timeout detected (error_count=%lu)",
        static_cast<unsigned long>(can_error_count_));
    }

    // Error frames are not data frames — do not pass to caller
    return false;
  }

  // Filter: discard CAN frames outside MG6010 arbitration ID range (0x140-0x240).
  // ODrive controllers share can0 and send heartbeats/responses in the 0x000-0x05F range;
  // without this filter those frames would reach the MG6010 protocol parser and cause errors.
  uint32_t arb_id = frame.can_id & CAN_EFF_MASK;
  if (arb_id < 0x140 || arb_id > 0x240) {
    return false;  // silently discard non-MG6010 frame
  }

  // Extract message
  id = arb_id;
  data.clear();
  data.reserve(frame.can_dlc);
  for (uint8_t i = 0; i < frame.can_dlc; ++i) {
    data.push_back(frame.data[i]);
  }

  return true;
}

bool MG6010CANInterface::configure_node(uint8_t node_id, uint32_t baud_rate)
{
  // MG6010 motors don't require node-level configuration via CAN
  // Node ID is set via hardware DIP switches or configuration tool
  // Baud rate is set via CAN interface configuration (ip link set)

  // This is a no-op for MG6010 but required by interface
  (void)node_id;
  (void)baud_rate;
  return true;
}

bool MG6010CANInterface::is_connected() const
{
  std::lock_guard<std::mutex> lock(mutex_);
  return connected_ && can_socket_ >= 0;
}

std::string MG6010CANInterface::get_last_error() const
{
  std::lock_guard<std::mutex> lock(mutex_);
  return last_error_;
}

void MG6010CANInterface::set_error(const std::string & error)
{
  last_error_ = error;
  RCLCPP_ERROR(rclcpp::get_logger("motor_control"),
    "MG6010CANInterface Error: %s", error.c_str());
}

// --- CAN bus resilience (tasks 1.4, 1.5) ---

void MG6010CANInterface::setConnectionStatusCallback(std::function<void(bool)> callback)
{
  std::lock_guard<std::mutex> lock(mutex_);
  connection_status_callback_ = std::move(callback);
}

uint64_t MG6010CANInterface::get_can_error_count() const
{
  std::lock_guard<std::mutex> lock(mutex_);
  return can_error_count_;
}

bool MG6010CANInterface::attemptReconnection()
{
  // Check if enough time has elapsed since the last attempt (exponential backoff).
  // Called from a ROS2 timer in the controller node — never blocks the control loop.
  auto now = std::chrono::steady_clock::now();

  std::unique_lock<std::mutex> lock(mutex_);

  // Already connected — nothing to do
  if (connected_ && can_socket_ >= 0) {
    return true;
  }

  auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
    now - last_reconnect_attempt_);
  if (elapsed.count() < static_cast<int64_t>(reconnect_backoff_ms_)) {
    return false;  // too soon
  }

  last_reconnect_attempt_ = now;

  // Close existing socket if any
  if (can_socket_ >= 0) {
    close(can_socket_);
    can_socket_ = -1;
  }
  // Close stale epoll fd — setup_can_socket() creates a fresh one
  if (epoll_fd_ >= 0) {
    close(epoll_fd_);
    epoll_fd_ = -1;
  }

  // Clear the response buffer on reconnection — stale frames are invalid
  response_buffer_.clear();

  // Attempt to reopen
  if (!setup_can_socket()) {
    // Double backoff, cap at 5000ms
    reconnect_backoff_ms_ = std::min(reconnect_backoff_ms_ * 2, static_cast<uint32_t>(5000));
    RCLCPP_WARN(rclcpp::get_logger("motor_control"),
      "MG6010CANInterface: CAN reconnection failed on %s — next attempt in %ums",
      interface_name_.c_str(), reconnect_backoff_ms_);
    return false;
  }

  // Success — reset state
  connected_ = true;
  reconnect_backoff_ms_ = 100;
  RCLCPP_INFO(rclcpp::get_logger("motor_control"),
    "MG6010CANInterface: CAN reconnected on %s", interface_name_.c_str());

  auto callback = connection_status_callback_;
  lock.unlock();
  if (callback) {
    callback(true);
  }
  return true;
}

// --- CAN frame response buffer (tasks 6.2, 6.3) ---

void MG6010CANInterface::bufferFrame(const struct can_frame & frame)
{
  // Called under existing mutex lock — no additional locking needed.
  uint32_t arb_id = frame.can_id & CAN_EFF_MASK;
  auto & buf = response_buffer_[arb_id];
  if (buf.size() >= MAX_BUFFERED_FRAMES_PER_MOTOR) {
    buf.pop_front();
    RCLCPP_WARN(rclcpp::get_logger("motor_control"),
      "MG6010CANInterface: response buffer overflow for CAN ID 0x%X — oldest frame discarded",
      arb_id);
  }
  buf.push_back(frame);
}

bool MG6010CANInterface::getBufferedResponse(uint32_t expected_id, std::vector<uint8_t> & data)
{
  std::lock_guard<std::mutex> lock(mutex_);

  auto it = response_buffer_.find(expected_id);
  if (it == response_buffer_.end() || it->second.empty()) {
    return false;
  }

  const struct can_frame & frame = it->second.front();
  data.clear();
  data.reserve(frame.can_dlc);
  for (uint8_t i = 0; i < frame.can_dlc; ++i) {
    data.push_back(frame.data[i]);
  }
  it->second.pop_front();

  // Clean up empty deques to avoid map bloat
  if (it->second.empty()) {
    response_buffer_.erase(it);
  }

  return true;
}

void MG6010CANInterface::bufferCurrentFrame(uint32_t id, const std::vector<uint8_t> & data)
{
  std::lock_guard<std::mutex> lock(mutex_);

  struct can_frame frame;
  std::memset(&frame, 0, sizeof(frame));
  frame.can_id = id;
  frame.can_dlc = static_cast<uint8_t>(std::min(data.size(), static_cast<size_t>(8)));
  std::memcpy(frame.data, data.data(), frame.can_dlc);

  bufferFrame(frame);
}

}  // namespace motor_control_ros2
