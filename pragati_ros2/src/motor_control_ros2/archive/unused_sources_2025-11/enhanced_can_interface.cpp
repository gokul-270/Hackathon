/*
 * Enhanced CAN Interface Implementation
 *
 * This implementation provides a comprehensive CAN bus abstraction with:
 * - Multi-protocol support (ODrive Custom, CANopen, J1939)
 * - Automatic protocol detection
 * - Advanced error handling and recovery
 * - Real-time statistics and monitoring
 * - Thread-safe operations
 */

#include "motor_control_ros2/enhanced_can_interface.hpp"
#include <linux/can.h>
#include <linux/can/raw.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstring>
#include <chrono>
#include <algorithm>
#include <iostream>

namespace motor_control_ros2
{

// =============================================================================
// ENHANCED CAN CONTROLLER IMPLEMENTATION
// =============================================================================

EnhancedCANController::EnhancedCANController()
: socket_fd_(-1)
  , current_protocol_(CANProtocol::AUTO_DETECT)
  , is_initialized_(false)
  , is_running_(false)
  , enable_timestamping_(false)
  , enable_loopback_(false)
  , rng_(std::chrono::steady_clock::now().time_since_epoch().count())
{
    // Initialize statistics
  std::lock_guard<std::mutex> lock(stats_mutex_);
  statistics_ = CANStatistics{};

    // Initialize protocol configurations
  initialize_protocol_configs();
}

EnhancedCANController::~EnhancedCANController()
{
  shutdown();
}

bool EnhancedCANController::initialize(
  const std::string & interface_name,
  const ProtocolConfig & config)
{
  std::lock_guard<std::mutex> lock(interface_mutex_);

  if (is_initialized_) {
    last_error_ = "CAN interface already initialized";
    return false;
  }

  interface_name_ = interface_name;
  protocol_config_ = config;

    // Create socket
  socket_fd_ = socket(PF_CAN, SOCK_RAW, CAN_RAW);
  if (socket_fd_ < 0) {
    last_error_ = "Failed to create CAN socket: " + std::string(strerror(errno));
    return false;
  }

    // Set socket options
  if (!configure_socket_options()) {
    close(socket_fd_);
    socket_fd_ = -1;
    return false;
  }

    // Bind to interface
  if (!bind_to_interface(interface_name)) {
    close(socket_fd_);
    socket_fd_ = -1;
    return false;
  }

    // Configure protocol
  if (!configure_protocol(config)) {
    close(socket_fd_);
    socket_fd_ = -1;
    return false;
  }

    // Start background threads
  is_running_ = true;
  message_thread_ = std::thread(&EnhancedCANController::message_processing_thread, this);
  statistics_thread_ = std::thread(&EnhancedCANController::statistics_thread, this);

  is_initialized_ = true;
  current_protocol_ = config.protocol;

  return true;
}

void EnhancedCANController::shutdown()
{
  std::lock_guard<std::mutex> lock(interface_mutex_);

  if (!is_initialized_) {
    return;
  }

    // Stop background threads
  is_running_ = false;

  if (message_thread_.joinable()) {
    message_thread_.join();
  }

  if (statistics_thread_.joinable()) {
    statistics_thread_.join();
  }

    // Close socket
  if (socket_fd_ >= 0) {
    close(socket_fd_);
    socket_fd_ = -1;
  }

    // Clear queues
  {
    std::lock_guard<std::mutex> queue_lock(queue_mutex_);
    while (!tx_queue_.empty()) {tx_queue_.pop();}
    while (!rx_queue_.empty()) {rx_queue_.pop();}
  }

  is_initialized_ = false;
}

bool EnhancedCANController::send_message(const UniversalCANMessage & message)
{
  if (!is_initialized_) {
    last_error_ = "CAN interface not initialized";
    return false;
  }

    // Add to transmission queue
  {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    if (tx_queue_.size() >= MAX_QUEUE_SIZE) {
      last_error_ = "Transmission queue full";
      update_statistics_error();
      return false;
    }
    tx_queue_.push(message);
  }

  queue_cv_.notify_one();
  return true;
}

bool EnhancedCANController::receive_message(UniversalCANMessage & message, int timeout_ms)
{
  if (!is_initialized_) {
    last_error_ = "CAN interface not initialized";
    return false;
  }

  std::unique_lock<std::mutex> lock(queue_mutex_);

  if (timeout_ms > 0) {
        // Wait with timeout
    auto timeout = std::chrono::milliseconds(timeout_ms);
    if (!queue_cv_.wait_for(lock, timeout, [this] {return !rx_queue_.empty() || !is_running_;})) {
      last_error_ = "Receive timeout";
      return false;
    }
  } else if (timeout_ms == 0) {
        // Non-blocking check
    if (rx_queue_.empty()) {
      last_error_ = "No message available";
      return false;
    }
  } else {
        // Blocking wait
    queue_cv_.wait(lock, [this] {return !rx_queue_.empty() || !is_running_;});
  }

  if (!is_running_ || rx_queue_.empty()) {
    last_error_ = "Interface shutdown or no message available";
    return false;
  }

  message = rx_queue_.front();
  rx_queue_.pop();

  update_statistics_rx();
  return true;
}

bool EnhancedCANController::send_motor_command(
  uint8_t node_id, uint16_t command_code,
  const std::vector<uint8_t> & data)
{
  UniversalCANMessage message;

  switch (current_protocol_) {
    case CANProtocol::ODRIVE_CUSTOM:
      return send_odrive_command(node_id, command_code, data, message);

    case CANProtocol::CANOPEN:
      return send_canopen_command(node_id, command_code, data, message);

    case CANProtocol::J1939:
      return send_j1939_command(node_id, command_code, data, message);

    default:
      last_error_ = "Invalid protocol for motor command";
      return false;
  }
}

bool EnhancedCANController::request_motor_data(
  uint8_t node_id, uint16_t data_type,
  std::vector<uint8_t> & response, int timeout_ms)
{
    // Send request
  std::vector<uint8_t> request_data = {static_cast<uint8_t>(data_type & 0xFF),
    static_cast<uint8_t>((data_type >> 8) & 0xFF)};
  if (!send_motor_command(node_id, 0x01, request_data)) {   // 0x01 = data request command
    return false;
  }

    // Wait for response
  auto start_time = std::chrono::steady_clock::now();
  while (true) {
    UniversalCANMessage message;
    if (receive_message(message, 10)) {     // 10ms polling
      if (is_response_for_request(message, node_id, data_type)) {
        response = message.data;
        return true;
      }
    }

    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - start_time).count();
    if (elapsed > timeout_ms) {
      last_error_ = "Request timeout";
      return false;
    }
  }
}

bool EnhancedCANController::set_protocol(CANProtocol protocol)
{
  if (!is_initialized_) {
    last_error_ = "CAN interface not initialized";
    return false;
  }

  ProtocolConfig config = protocol_config_;
  config.protocol = protocol;

  return configure_protocol(config);
}

CANProtocol EnhancedCANController::get_protocol() const
{
  return current_protocol_;
}

bool EnhancedCANController::auto_detect_protocol(int detection_time_ms)
{
  if (!is_initialized_) {
    last_error_ = "CAN interface not initialized";
    return false;
  }

  std::map<CANProtocol, int> protocol_scores;
  protocol_scores[CANProtocol::ODRIVE_CUSTOM] = 0;
  protocol_scores[CANProtocol::CANOPEN] = 0;
  protocol_scores[CANProtocol::J1939] = 0;

  auto start_time = std::chrono::steady_clock::now();

  while (true) {
    UniversalCANMessage message;
    if (receive_message(message, 10)) {     // 10ms polling
            // Analyze message to determine protocol
      if (is_odrive_message(message)) {
        protocol_scores[CANProtocol::ODRIVE_CUSTOM]++;
      } else if (is_canopen_message(message)) {
        protocol_scores[CANProtocol::CANOPEN]++;
      } else if (is_j1939_message(message)) {
        protocol_scores[CANProtocol::J1939]++;
      }
    }

    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - start_time).count();
    if (elapsed > detection_time_ms) {
      break;
    }
  }

    // Find protocol with highest score
  auto max_element = std::max_element(protocol_scores.begin(), protocol_scores.end(),
      [](const auto & a, const auto & b) {return a.second < b.second;});

  if (max_element->second > 0) {
    return set_protocol(max_element->first);
  }

  last_error_ = "No valid protocol detected";
  return false;
}

bool EnhancedCANController::configure_protocol(const ProtocolConfig & config)
{
  protocol_config_ = config;
  current_protocol_ = config.protocol;

    // Protocol-specific configuration
  switch (config.protocol) {
    case CANProtocol::ODRIVE_CUSTOM:
      return configure_odrive_protocol();

    case CANProtocol::CANOPEN:
      return configure_canopen_protocol();

    case CANProtocol::J1939:
      return configure_j1939_protocol();

    default:
      last_error_ = "Unsupported protocol";
      return false;
  }
}

bool EnhancedCANController::set_message_filters(const MessageFilter & filter)
{
  if (!is_initialized_) {
    last_error_ = "CAN interface not initialized";
    return false;
  }

  current_filter_ = filter;

    // Apply filters to socket
  if (filter.enable_filtering) {
    struct can_filter can_filters[filter.filter_list.size()];

    for (size_t i = 0; i < filter.filter_list.size(); ++i) {
      can_filters[i].can_id = filter.filter_list[i].can_id;
      can_filters[i].can_mask = filter.filter_list[i].can_mask;
    }

    if (setsockopt(socket_fd_, SOL_CAN_RAW, CAN_RAW_FILTER,
                      &can_filters, sizeof(can_filters)) < 0)
    {
      last_error_ = "Failed to set CAN filters: " + std::string(strerror(errno));
      return false;
    }
  } else {
        // Remove all filters
    if (setsockopt(socket_fd_, SOL_CAN_RAW, CAN_RAW_FILTER,
                      nullptr, 0) < 0)
    {
      last_error_ = "Failed to remove CAN filters: " + std::string(strerror(errno));
      return false;
    }
  }

  return true;
}

bool EnhancedCANController::enable_timestamping(bool enable)
{
  enable_timestamping_ = enable;

  if (!is_initialized_) {
    return true;     // Will be applied when initialized
  }

  int timestamp_on = enable ? 1 : 0;
  if (setsockopt(socket_fd_, SOL_SOCKET, SO_TIMESTAMP, &timestamp_on, sizeof(timestamp_on)) < 0) {
    last_error_ = "Failed to configure timestamping: " + std::string(strerror(errno));
    return false;
  }

  return true;
}

bool EnhancedCANController::set_loopback(bool enable)
{
  enable_loopback_ = enable;

  if (!is_initialized_) {
    return true;     // Will be applied when initialized
  }

  int loopback = enable ? 1 : 0;
  if (setsockopt(socket_fd_, SOL_CAN_RAW, CAN_RAW_LOOPBACK, &loopback, sizeof(loopback)) < 0) {
    last_error_ = "Failed to configure loopback: " + std::string(strerror(errno));
    return false;
  }

  return true;
}

bool EnhancedCANController::perform_bus_recovery()
{
  if (!is_initialized_) {
    last_error_ = "CAN interface not initialized";
    return false;
  }

    // Reset error counters
  reset_statistics();

    // Clear queues
  {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    while (!tx_queue_.empty()) {tx_queue_.pop();}
    while (!rx_queue_.empty()) {rx_queue_.pop();}
  }

    // Send bus recovery command if supported by protocol
  switch (current_protocol_) {
    case CANProtocol::CANOPEN:
            // Send CANopen reset communication command
      return send_canopen_reset_command();

    default:
            // Generic recovery - just clear errors
      break;
  }

  last_error_ = "";
  return true;
}

CANStatistics EnhancedCANController::get_statistics() const
{
  std::lock_guard<std::mutex> lock(stats_mutex_);

  CANStatistics stats = statistics_;

    // Calculate derived statistics
  auto now = std::chrono::steady_clock::now();
  auto elapsed_seconds = std::chrono::duration<double>(now - stats.start_time).count();

  if (elapsed_seconds > 0) {
    stats.messages_per_second = static_cast<double>(stats.total_messages_sent +
      stats.total_messages_received) / elapsed_seconds;
    stats.bus_utilization = calculate_bus_utilization();
  }

  return stats;
}

void EnhancedCANController::reset_statistics()
{
  std::lock_guard<std::mutex> lock(stats_mutex_);

  statistics_ = CANStatistics{};
  statistics_.start_time = std::chrono::steady_clock::now();
}

bool EnhancedCANController::is_bus_healthy() const
{
  auto stats = get_statistics();

    // Check error rates
  double error_rate = static_cast<double>(stats.total_errors) /
    std::max(1UL, stats.total_messages_sent + stats.total_messages_received);

  if (error_rate > 0.05) {   // More than 5% error rate
    return false;
  }

    // Check bus utilization
  if (stats.bus_utilization > 0.8) {   // More than 80% utilization
    return false;
  }

    // Check for recent activity
  auto now = std::chrono::steady_clock::now();
  auto last_activity_age = std::chrono::duration_cast<std::chrono::seconds>(
        now - stats.last_message_time).count();

  if (stats.total_messages_sent > 0 && last_activity_age > 60) {   // No activity for 60 seconds
    return false;
  }

  return true;
}

double EnhancedCANController::get_bus_load_percent() const
{
  return calculate_bus_utilization() * 100.0;
}

std::pair<uint32_t, uint32_t> EnhancedCANController::get_error_counts() const
{
  auto stats = get_statistics();
  return std::make_pair(stats.tx_errors, stats.rx_errors);
}

std::string EnhancedCANController::get_last_error() const
{
  std::lock_guard<std::mutex> lock(interface_mutex_);
  return last_error_;
}

void EnhancedCANController::register_event_callback(
  std::function<void(const std::string &)> callback)
{
  std::lock_guard<std::mutex> lock(callback_mutex_);
  event_callbacks_.push_back(callback);
}

// =============================================================================
// PRIVATE HELPER METHODS
// =============================================================================

bool EnhancedCANController::configure_socket_options()
{
    // Enable timestamping if requested
  if (enable_timestamping_) {
    int timestamp_on = 1;
    if (setsockopt(socket_fd_, SOL_SOCKET, SO_TIMESTAMP, &timestamp_on, sizeof(timestamp_on)) < 0) {
      last_error_ = "Failed to enable timestamping: " + std::string(strerror(errno));
      return false;
    }
  }

    // Configure loopback
  int loopback = enable_loopback_ ? 1 : 0;
  if (setsockopt(socket_fd_, SOL_CAN_RAW, CAN_RAW_LOOPBACK, &loopback, sizeof(loopback)) < 0) {
    last_error_ = "Failed to configure loopback: " + std::string(strerror(errno));
    return false;
  }

    // Enable receipt of own messages if loopback is disabled
  int recv_own_msgs = enable_loopback_ ? 0 : 1;
  if (setsockopt(socket_fd_, SOL_CAN_RAW, CAN_RAW_RECV_OWN_MSGS, &recv_own_msgs,
      sizeof(recv_own_msgs)) < 0)
  {
    last_error_ = "Failed to configure own message receipt: " + std::string(strerror(errno));
    return false;
  }

    // Set socket to non-blocking mode
  int flags = fcntl(socket_fd_, F_GETFL, 0);
  if (flags == -1) {
    last_error_ = "Failed to get socket flags: " + std::string(strerror(errno));
    return false;
  }

  if (fcntl(socket_fd_, F_SETFL, flags | O_NONBLOCK) == -1) {
    last_error_ = "Failed to set non-blocking mode: " + std::string(strerror(errno));
    return false;
  }

  return true;
}

bool EnhancedCANController::bind_to_interface(const std::string & interface_name)
{
  struct ifreq ifr;
  struct sockaddr_can addr;

    // Get interface index
  strcpy(ifr.ifr_name, interface_name.c_str());
  if (ioctl(socket_fd_, SIOCGIFINDEX, &ifr) < 0) {
    last_error_ = "Failed to get interface index for " + interface_name + ": " +
      std::string(strerror(errno));
    return false;
  }

    // Bind socket to interface
  addr.can_family = AF_CAN;
  addr.can_ifindex = ifr.ifr_ifindex;

  if (bind(socket_fd_, reinterpret_cast<struct sockaddr *>(&addr), sizeof(addr)) < 0) {
    last_error_ = "Failed to bind to interface " + interface_name + ": " +
      std::string(strerror(errno));
    return false;
  }

  return true;
}

void EnhancedCANController::message_processing_thread()
{
  struct can_frame frame;
  struct timeval tv;
  fd_set readfds, writefds;

  while (is_running_) {
    FD_ZERO(&readfds);
    FD_ZERO(&writefds);
    FD_SET(socket_fd_, &readfds);

        // Check if we have messages to send
    bool has_tx_messages = false;
    {
      std::lock_guard<std::mutex> lock(queue_mutex_);
      has_tx_messages = !tx_queue_.empty();
    }

    if (has_tx_messages) {
      FD_SET(socket_fd_, &writefds);
    }

        // Set timeout
    tv.tv_sec = 0;
    tv.tv_usec = 10000;     // 10ms

    int result = select(socket_fd_ + 1, &readfds, &writefds, nullptr, &tv);

    if (result < 0) {
      if (errno == EINTR) {continue;}     // Interrupted by signal
      break;       // Other error
    }

        // Handle reception
    if (FD_ISSET(socket_fd_, &readfds)) {
      process_received_messages();
    }

        // Handle transmission
    if (FD_ISSET(socket_fd_, &writefds)) {
      process_transmission_queue();
    }
  }
}

void EnhancedCANController::process_received_messages()
{
  struct can_frame frame;

  while (true) {
    ssize_t nbytes = read(socket_fd_, &frame, sizeof(frame));

    if (nbytes < 0) {
      if (errno == EAGAIN || errno == EWOULDBLOCK) {
        break;         // No more messages
      }
      update_statistics_error();
      break;
    }

    if (nbytes != sizeof(frame)) {
      update_statistics_error();
      continue;
    }

        // Convert to universal message
    UniversalCANMessage message;
    message.can_id = frame.can_id & CAN_EFF_MASK;
    message.is_extended = (frame.can_id & CAN_EFF_FLAG) != 0;
    message.is_rtr = (frame.can_id & CAN_RTR_FLAG) != 0;
    message.dlc = frame.can_dlc;
    message.data.assign(frame.data, frame.data + frame.can_dlc);
    message.timestamp = std::chrono::steady_clock::now();

        // Apply filters
    if (should_filter_message(message)) {
      continue;
    }

        // Add to receive queue
    {
      std::lock_guard<std::mutex> lock(queue_mutex_);
      if (rx_queue_.size() >= MAX_QUEUE_SIZE) {
        rx_queue_.pop();         // Remove oldest message
      }
      rx_queue_.push(message);
    }

    queue_cv_.notify_one();
    update_statistics_rx();
  }
}

void EnhancedCANController::process_transmission_queue()
{
  std::unique_lock<std::mutex> lock(queue_mutex_);

  while (!tx_queue_.empty()) {
    UniversalCANMessage message = tx_queue_.front();
    lock.unlock();

        // Convert to CAN frame
    struct can_frame frame;
    frame.can_id = message.can_id;
    if (message.is_extended) {
      frame.can_id |= CAN_EFF_FLAG;
    }
    if (message.is_rtr) {
      frame.can_id |= CAN_RTR_FLAG;
    }
    frame.can_dlc = std::min(static_cast<size_t>(8), message.data.size());
    std::copy(message.data.begin(), message.data.begin() + frame.can_dlc, frame.data);

        // Send message
    ssize_t nbytes = write(socket_fd_, &frame, sizeof(frame));

    lock.lock();

    if (nbytes == sizeof(frame)) {
      tx_queue_.pop();
      lock.unlock();
      update_statistics_tx();
      lock.lock();
    } else {
            // Transmission failed
      if (errno == EAGAIN || errno == EWOULDBLOCK) {
        break;         // Socket buffer full, try again later
      }

      tx_queue_.pop();       // Remove failed message
      lock.unlock();
      update_statistics_error();
      lock.lock();
    }
  }
}

void EnhancedCANController::statistics_thread()
{
  while (is_running_) {
    std::this_thread::sleep_for(std::chrono::seconds(1));

        // Update periodic statistics
    update_bus_utilization();

        // Check for error conditions
    if (!is_bus_healthy()) {
      notify_event("Bus health warning detected");
    }
  }
}

bool EnhancedCANController::should_filter_message(const UniversalCANMessage & message)
{
  if (!current_filter_.enable_filtering) {
    return false;
  }

  for (const auto & filter : current_filter_.filter_list) {
    if ((message.can_id & filter.can_mask) == (filter.can_id & filter.can_mask)) {
      return false;       // Message matches filter, don't filter out
    }
  }

  return true;   // Filter out message
}

void EnhancedCANController::update_statistics_tx()
{
  std::lock_guard<std::mutex> lock(stats_mutex_);
  statistics_.total_messages_sent++;
  statistics_.last_message_time = std::chrono::steady_clock::now();
}

void EnhancedCANController::update_statistics_rx()
{
  std::lock_guard<std::mutex> lock(stats_mutex_);
  statistics_.total_messages_received++;
  statistics_.last_message_time = std::chrono::steady_clock::now();
}

void EnhancedCANController::update_statistics_error()
{
  std::lock_guard<std::mutex> lock(stats_mutex_);
  statistics_.total_errors++;
  statistics_.last_error_time = std::chrono::steady_clock::now();
}

void EnhancedCANController::notify_event(const std::string & event)
{
  std::lock_guard<std::mutex> lock(callback_mutex_);
  for (const auto & callback : event_callbacks_) {
    try {
      callback(event);
    } catch (...) {
            // Ignore callback exceptions
    }
  }
}

double EnhancedCANController::calculate_bus_utilization() const
{
    // Simplified bus utilization calculation
    // In reality, this would need more sophisticated analysis
  auto stats = get_statistics();
  double message_rate = stats.messages_per_second;
  double max_theoretical_rate = protocol_config_.baud_rate / (64 * 8);   // Rough estimate

  return std::min(1.0, message_rate / max_theoretical_rate);
}

void EnhancedCANController::update_bus_utilization()
{
  std::lock_guard<std::mutex> lock(stats_mutex_);
  statistics_.bus_utilization = calculate_bus_utilization();
}

// Protocol-specific implementations (simplified for brevity)
bool EnhancedCANController::send_odrive_command(
  uint8_t node_id, uint16_t command_code,
  const std::vector<uint8_t> & data, UniversalCANMessage & message)
{
  message.can_id = (node_id << 5) | (command_code & 0x1F);
  message.data = data;
  message.dlc = data.size();
  message.is_extended = false;
  message.is_rtr = false;
  return send_message(message);
}

bool EnhancedCANController::send_canopen_command(
  uint8_t node_id, uint16_t command_code,
  const std::vector<uint8_t> & data, UniversalCANMessage & message)
{
  message.can_id = 0x600 + node_id;
  message.data = data;
  message.dlc = data.size();
  message.is_extended = false;
  message.is_rtr = false;
  return send_message(message);
}

bool EnhancedCANController::send_j1939_command(
  uint8_t node_id, uint16_t command_code,
  const std::vector<uint8_t> & data, UniversalCANMessage & message)
{
  message.can_id = 0x18000000 | (command_code << 8) | node_id;
  message.data = data;
  message.dlc = data.size();
  message.is_extended = true;
  message.is_rtr = false;
  return send_message(message);
}

// Protocol detection helpers
bool EnhancedCANController::is_odrive_message(const UniversalCANMessage & message)
{
  return !message.is_extended && (message.can_id <= 0x3FF);
}

bool EnhancedCANController::is_canopen_message(const UniversalCANMessage & message)
{
  return !message.is_extended &&
         ((message.can_id >= 0x580 && message.can_id <= 0x5FF) ||
         (message.can_id >= 0x600 && message.can_id <= 0x67F));
}

bool EnhancedCANController::is_j1939_message(const UniversalCANMessage & message)
{
  return message.is_extended && (message.can_id & 0xFF000000) == 0x18000000;
}

// Additional helper methods
void EnhancedCANController::initialize_protocol_configs()
{
    // Initialize default configurations for each protocol
    // This would be expanded based on specific protocol requirements
}

bool EnhancedCANController::configure_odrive_protocol()
{
    // ODrive-specific configuration
  return true;
}

bool EnhancedCANController::configure_canopen_protocol()
{
    // CANopen-specific configuration
  return true;
}

bool EnhancedCANController::configure_j1939_protocol()
{
    // J1939-specific configuration
  return true;
}

bool EnhancedCANController::send_canopen_reset_command()
{
    // Send CANopen network reset command
  std::vector<uint8_t> reset_data = {0x01, 0x00};
  return send_canopen_command(0, 0x000, reset_data);
}

bool EnhancedCANController::is_response_for_request(
  const UniversalCANMessage & message,
  uint8_t node_id, uint16_t data_type)
{
    // Protocol-specific response matching logic
  switch (current_protocol_) {
    case CANProtocol::ODRIVE_CUSTOM:
      return (message.can_id >> 5) == node_id;

    case CANProtocol::CANOPEN:
      return message.can_id == (0x580 + node_id);

    default:
      return false;
  }
}

} // namespace motor_control_ros2
