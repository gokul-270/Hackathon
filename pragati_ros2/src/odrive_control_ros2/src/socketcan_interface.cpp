// Copyright 2025 Pragati Robotics
// SocketCAN Interface Implementation

#include "odrive_control_ros2/socketcan_interface.hpp"
#include "odrive_control_ros2/odrive_cansimple_protocol.hpp"

#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <unistd.h>
#include <poll.h>
#include <cstring>
#include <iostream>

namespace odrive_cansimple {

SocketCANInterface::SocketCANInterface()
: socket_fd_(-1)
, interface_name_()
, configured_node_ids_()
{
}

SocketCANInterface::~SocketCANInterface() {
  close();
}

bool SocketCANInterface::initialize(const std::string& interface_name, const std::vector<uint8_t>& node_ids) {
  // Close existing socket if open
  if (socket_fd_ >= 0) {
    close();
  }

  interface_name_ = interface_name;
  configured_node_ids_ = node_ids;

  // Create socket
  socket_fd_ = socket(PF_CAN, SOCK_RAW, CAN_RAW);
  if (socket_fd_ < 0) {
    std::cerr << "Failed to create CAN socket: " << strerror(errno) << std::endl;
    return false;
  }

  // Get interface index
  struct ifreq ifr;
  std::strncpy(ifr.ifr_name, interface_name.c_str(), IFNAMSIZ - 1);
  ifr.ifr_name[IFNAMSIZ - 1] = '\0';

  if (ioctl(socket_fd_, SIOCGIFINDEX, &ifr) < 0) {
    std::cerr << "Failed to get interface index for " << interface_name
              << ": " << strerror(errno) << std::endl;
    ::close(socket_fd_);
    socket_fd_ = -1;
    return false;
  }

  // Bind socket to interface
  struct sockaddr_can addr;
  std::memset(&addr, 0, sizeof(addr));
  addr.can_family = AF_CAN;
  addr.can_ifindex = ifr.ifr_ifindex;

  if (bind(socket_fd_, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
    std::cerr << "Failed to bind CAN socket: " << strerror(errno) << std::endl;
    ::close(socket_fd_);
    socket_fd_ = -1;
    return false;
  }

  // Disable CAN loopback to prevent TX echo wakeups (fix-vehicle-cpu-thermal).
  // Linux SocketCAN echoes every transmitted frame back to the sending socket
  // by default.  This causes spurious poll() wakeups, burning CPU.  Disabling
  // loopback is per-socket and does not affect other CAN users.
  // Must be set unconditionally after bind, NOT inside apply_filters() which
  // returns early when node_ids is empty.
  int loopback = 0;
  if (setsockopt(socket_fd_, SOL_CAN_RAW, CAN_RAW_LOOPBACK,
                 &loopback, sizeof(loopback)) < 0) {
    std::cerr << "ODrive SocketCAN: Failed to disable CAN_RAW_LOOPBACK: "
              << strerror(errno) << std::endl;
    // Non-fatal: loopback frames waste CPU but don't break functionality
  }
  int recv_own_msgs = 0;
  if (setsockopt(socket_fd_, SOL_CAN_RAW, CAN_RAW_RECV_OWN_MSGS,
                 &recv_own_msgs, sizeof(recv_own_msgs)) < 0) {
    std::cerr << "ODrive SocketCAN: Failed to disable CAN_RAW_RECV_OWN_MSGS: "
              << strerror(errno) << std::endl;
  }

  // Apply filters for configured node IDs
  if (!apply_filters(node_ids)) {
    std::cerr << "Warning: Failed to apply CAN filters" << std::endl;
    // Continue anyway - filters are optional optimization
  }

  std::cout << "SocketCAN initialized: " << interface_name << std::endl;
  return true;
}

void SocketCANInterface::close() {
  if (socket_fd_ >= 0) {
    ::close(socket_fd_);
    socket_fd_ = -1;
  }
  interface_name_.clear();
  configured_node_ids_.clear();
}

bool SocketCANInterface::apply_filters(const std::vector<uint8_t>& node_ids) {
  if (socket_fd_ < 0) {
    return false;
  }

  if (node_ids.empty()) {
    // No filters = accept all frames (default)
    return true;
  }

  // Create filter for each node_id
  // Filter matches: (received_can_id & mask) == (filter_can_id & mask)
  // We want to match node_id bits (5-10) and ignore cmd_id bits (0-4)
  // Mask: 0x7E0 (bits 5-10 set, bits 0-4 clear)

  std::vector<struct can_filter> filters;
  filters.reserve(node_ids.size());

  for (uint8_t node_id : node_ids) {
    struct can_filter filter;
    // Filter can_id: node_id shifted to bits 5-10
    filter.can_id = static_cast<canid_t>(node_id) << NODE_ID_SHIFT;
    // Mask: match node_id bits, ignore cmd_id bits
    filter.can_mask = NODE_ID_MASK;  // 0x7E0

    filters.push_back(filter);
  }

  // Apply filters
  if (setsockopt(socket_fd_, SOL_CAN_RAW, CAN_RAW_FILTER,
                 filters.data(), filters.size() * sizeof(struct can_filter)) < 0) {
    std::cerr << "Failed to set CAN filters: " << strerror(errno) << std::endl;
    return false;
  }

  std::cout << "Applied CAN filters for " << node_ids.size() << " node(s): ";
  for (size_t i = 0; i < node_ids.size(); ++i) {
    if (i > 0) std::cout << ", ";
    std::cout << static_cast<int>(node_ids[i]);
  }
  std::cout << std::endl;

  return true;
}

bool SocketCANInterface::send_frame(uint16_t arb_id, const std::vector<uint8_t>& data, bool is_rtr) {
  if (socket_fd_ < 0) {
    return false;
  }

  if (data.size() > 8) {
    std::cerr << "CAN frame data too large: " << data.size() << " bytes" << std::endl;
    return false;
  }

  struct can_frame frame;
  std::memset(&frame, 0, sizeof(frame));

  frame.can_id = arb_id & CAN_SFF_MASK;  // Standard 11-bit ID
  if (is_rtr) {
    frame.can_id |= CAN_RTR_FLAG;
  }

  frame.can_dlc = static_cast<__u8>(data.size());
  std::memcpy(frame.data, data.data(), data.size());

  ssize_t bytes_sent = write(socket_fd_, &frame, sizeof(frame));
  if (bytes_sent != sizeof(frame)) {
    std::cerr << "Failed to send CAN frame: " << strerror(errno) << std::endl;
    return false;
  }

  return true;
}

bool SocketCANInterface::receive_frame(uint16_t& arb_id, std::vector<uint8_t>& data, int timeout_ms) {
  if (socket_fd_ < 0) {
    return false;
  }

  // Use poll for timeout
  struct pollfd pfd;
  pfd.fd = socket_fd_;
  pfd.events = POLLIN;
  pfd.revents = 0;

  int poll_result = poll(&pfd, 1, timeout_ms);

  if (poll_result < 0) {
    if (errno != EINTR) {
      std::cerr << "Poll error: " << strerror(errno) << std::endl;
    }
    return false;
  }

  if (poll_result == 0) {
    // Timeout
    return false;
  }

  // Data available - read frame
  struct can_frame frame;
  ssize_t bytes_read = read(socket_fd_, &frame, sizeof(frame));

  if (bytes_read != sizeof(frame)) {
    if (bytes_read < 0 && errno != EINTR) {
      std::cerr << "Failed to read CAN frame: " << strerror(errno) << std::endl;
    }
    return false;
  }

  // Extract arbitration ID and data
  arb_id = frame.can_id & CAN_SFF_MASK;  // Remove flags, keep 11-bit ID

  data.clear();
  data.reserve(frame.can_dlc);
  for (int i = 0; i < frame.can_dlc && i < 8; ++i) {
    data.push_back(frame.data[i]);
  }

  return true;
}

}  // namespace odrive_cansimple
