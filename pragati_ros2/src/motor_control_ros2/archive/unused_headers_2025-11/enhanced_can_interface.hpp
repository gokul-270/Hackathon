/*
 * Enhanced CAN Interface for Universal Motor Control
 *
 * This file provides complete CAN bus abstraction supporting multiple protocols:
 * - ODrive custom protocol
 * - CANopen (for MG6010, MG4040, and other standard motors)
 * - J1939 and other industrial protocols
 *
 * Key Features:
 * 1. Protocol-independent message handling
 * 2. Automatic protocol detection and adaptation
 * 3. Comprehensive error handling and recovery
 * 4. High-performance buffering and filtering
 * 5. Real-time monitoring and diagnostics
 */

#pragma once

#include "motor_abstraction.hpp"
#include <memory>
#include <functional>
#include <queue>
#include <thread>
#include <condition_variable>
#include <atomic>
#include <unordered_map>

namespace motor_control_ros2
{

// =============================================================================
// ENHANCED CAN MESSAGE STRUCTURES
// =============================================================================

/**
 * @brief Universal CAN message structure
 */
struct UniversalCANMessage
{
  uint32_t can_id;
  std::vector<uint8_t> data;
  uint8_t dlc;
  bool extended_frame;
  bool remote_frame;
  std::chrono::steady_clock::time_point timestamp;

  // Protocol-specific fields
  uint8_t node_id;        // For CANopen and similar protocols
  uint16_t function_code; // Protocol-specific function/command code
  uint8_t priority;       // Message priority (0 = highest)

  UniversalCANMessage()
  : can_id(0), dlc(0), extended_frame(false), remote_frame(false),
    node_id(0), function_code(0), priority(4)
  {
    timestamp = std::chrono::steady_clock::now();
  }
};

/**
 * @brief CAN protocol specifications
 */
enum class CANProtocol : uint8_t
{
  UNKNOWN = 0,
  ODRIVE_CUSTOM = 1,     // ODrive's custom protocol
  CANOPEN = 2,           // Standard CANopen protocol
  J1939 = 3,             // SAE J1939 automotive/industrial protocol
  CANFD = 4,             // CAN FD protocol
  PROPRIETARY = 5        // Vendor-specific protocols
};

/**
 * @brief Protocol-specific configuration
 */
struct ProtocolConfig
{
  CANProtocol protocol;
  uint32_t baud_rate;
  uint8_t node_id_base;
  uint16_t heartbeat_interval_ms;
  uint16_t sync_interval_ms;
  bool auto_recovery_enabled;
  uint8_t max_retries;
  uint32_t timeout_ms;

  // Protocol-specific settings
  std::unordered_map<std::string, std::string> custom_settings;

  ProtocolConfig()
  : protocol(CANProtocol::ODRIVE_CUSTOM), baud_rate(1000000), node_id_base(0),
    heartbeat_interval_ms(1000), sync_interval_ms(10), auto_recovery_enabled(true),
    max_retries(3), timeout_ms(100) {}
};

// =============================================================================
// COMPREHENSIVE CAN INTERFACE
// =============================================================================

/**
 * @brief Enhanced CAN interface with universal protocol support
 */
class EnhancedCANController : public CANInterface
{
public:
  /**
   * @brief CAN bus statistics for monitoring
   */
  struct CANStatistics
  {
    uint64_t messages_sent = 0;
    uint64_t messages_received = 0;
    uint64_t send_errors = 0;
    uint64_t receive_errors = 0;
    uint64_t bus_off_events = 0;
    uint64_t error_passive_events = 0;
    double bus_load_percent = 0.0;
    std::chrono::steady_clock::time_point last_reset;

    CANStatistics()
    {
      last_reset = std::chrono::steady_clock::now();
    }
  };

  /**
   * @brief Message filter for selective reception
   */
  struct MessageFilter
  {
    std::vector<uint32_t> accept_ids;      // IDs to accept (empty = accept all)
    std::vector<uint32_t> reject_ids;      // IDs to explicitly reject
    std::vector<uint8_t> accept_nodes;     // Node IDs to accept
    std::vector<uint8_t> reject_nodes;     // Node IDs to reject
    bool use_mask_filtering = false;       // Enable hardware mask filtering
    uint32_t acceptance_mask = 0xFFFFFFFF; // Acceptance mask for hardware filter
  };

public:
  virtual ~EnhancedCANController() = default;

  // =============================================================================
  // CORE INTERFACE METHODS
  // =============================================================================

  /**
   * @brief Initialize CAN interface with protocol configuration
   */
  virtual bool initialize(
    const std::string & interface_name,
    const ProtocolConfig & config = ProtocolConfig()) = 0;

  /**
   * @brief Send universal CAN message
   */
  virtual bool send_message(const UniversalCANMessage & message) = 0;

  /**
   * @brief Receive universal CAN message with timeout
   */
  virtual bool receive_message(UniversalCANMessage & message, int timeout_ms = 10) = 0;

  /**
   * @brief Send high-level motor command (protocol-aware)
   */
  virtual bool send_motor_command(
    uint8_t node_id, uint16_t command_code,
    const std::vector<uint8_t> & data) = 0;

  /**
   * @brief Request motor data (protocol-aware)
   */
  virtual bool request_motor_data(
    uint8_t node_id, uint16_t data_type,
    std::vector<uint8_t> & response, int timeout_ms = 100) = 0;

  // =============================================================================
  // PROTOCOL MANAGEMENT
  // =============================================================================

  /**
   * @brief Set active protocol
   */
  virtual bool set_protocol(CANProtocol protocol) = 0;

  /**
   * @brief Get current protocol
   */
  virtual CANProtocol get_protocol() const = 0;

  /**
   * @brief Auto-detect protocol from bus traffic
   */
  virtual bool auto_detect_protocol(int detection_time_ms = 5000) = 0;

  /**
   * @brief Configure protocol-specific settings
   */
  virtual bool configure_protocol(const ProtocolConfig & config) = 0;

  // =============================================================================
  // ADVANCED FEATURES
  // =============================================================================

  /**
   * @brief Set message filters
   */
  virtual bool set_message_filters(const MessageFilter & filter) = 0;

  /**
   * @brief Enable/disable timestamping
   */
  virtual bool enable_timestamping(bool enable) = 0;

  /**
   * @brief Enable/disable loopback for testing
   */
  virtual bool set_loopback(bool enable) = 0;

  /**
   * @brief Perform bus recovery after error conditions
   */
  virtual bool perform_bus_recovery() = 0;

  /**
   * @brief Get comprehensive bus statistics
   */
  virtual CANStatistics get_statistics() const = 0;

  /**
   * @brief Reset statistics counters
   */
  virtual void reset_statistics() = 0;

  // =============================================================================
  // MONITORING AND DIAGNOSTICS
  // =============================================================================

  /**
   * @brief Check if CAN bus is healthy
   */
  virtual bool is_bus_healthy() const = 0;

  /**
   * @brief Get current bus load percentage
   */
  virtual double get_bus_load_percent() const = 0;

  /**
   * @brief Get error counts
   */
  virtual std::pair<uint32_t, uint32_t> get_error_counts() const = 0; // TX, RX errors

  /**
   * @brief Get last error message
   */
  virtual std::string get_last_error() const = 0;

  /**
   * @brief Register callback for bus events
   */
  virtual void register_event_callback(std::function<void(const std::string &)> callback) = 0;

  // =============================================================================
  // LEGACY COMPATIBILITY (from base CANInterface)
  // =============================================================================

  bool initialize(const std::string & interface_name, uint32_t baud_rate = 1000000) override
  {
    ProtocolConfig config;
    config.baud_rate = baud_rate;
    return initialize(interface_name, config);
  }

  bool send_message(uint32_t id, const std::vector<uint8_t> & data) override
  {
    UniversalCANMessage msg;
    msg.can_id = id;
    msg.data = data;
    msg.dlc = static_cast<uint8_t>(std::min(data.size(), size_t(8)));
    return send_message(msg);
  }

  bool receive_message(uint32_t & id, std::vector<uint8_t> & data, int timeout_ms = 10) override
  {
    UniversalCANMessage msg;
    if (receive_message(msg, timeout_ms)) {
      id = msg.can_id;
      data = msg.data;
      return true;
    }
    return false;
  }

  bool configure_node(uint8_t node_id, uint32_t baud_rate = 0) override
  {
    (void)node_id;  // Suppress unused parameter warnings in legacy compatibility stub
    (void)baud_rate;
    // Legacy method - use current protocol config
    return true; // Implementation would update node configuration
  }

  bool is_connected() const override
  {
    return is_bus_healthy();
  }
};

// =============================================================================
// PROTOCOL-SPECIFIC IMPLEMENTATIONS
// =============================================================================

/**
 * @brief ODrive-specific CAN controller
 */
class ODriveCANController : public EnhancedCANController
{
public:
  // ODrive-specific message formats
  enum ODriveCommand : uint16_t
  {
    CMD_HEARTBEAT = 0x001,
    CMD_ESTOP = 0x002,
    CMD_GET_MOTOR_ERROR = 0x003,
    CMD_GET_ENCODER_ERROR = 0x004,
    CMD_GET_SENSORLESS_ERROR = 0x005,
    CMD_SET_AXIS_NODE_ID = 0x006,
    CMD_SET_AXIS_REQUESTED_STATE = 0x007,
    CMD_SET_AXIS_STARTUP_CONFIG = 0x008,
    CMD_GET_ENCODER_ESTIMATES = 0x009,
    CMD_GET_ENCODER_COUNT = 0x00A,
    CMD_SET_CONTROLLER_MODES = 0x00B,
    CMD_SET_INPUT_POS = 0x00C,
    CMD_SET_INPUT_VEL = 0x00D,
    CMD_SET_INPUT_TORQUE = 0x00E,
    CMD_SET_LIMITS = 0x00F,
    CMD_START_ANTICOGGING = 0x010,
    CMD_SET_TRAJ_VEL_LIMIT = 0x011,
    CMD_SET_TRAJ_ACCEL_LIMITS = 0x012,
    CMD_SET_TRAJ_INERTIA = 0x013,
    CMD_GET_IQ = 0x014,
    CMD_GET_SENSORLESS_ESTIMATES = 0x015,
    CMD_REBOOT = 0x016,
    CMD_GET_VBUS_VOLTAGE = 0x017,
    CMD_CLEAR_ERRORS = 0x018,
    CMD_SET_LINEAR_COUNT = 0x019,
    CMD_SET_POS_GAIN = 0x01A,
    CMD_SET_VEL_GAINS = 0x01B
  };

  bool send_motor_command(
    uint8_t node_id, uint16_t command_code,
    const std::vector<uint8_t> & data) override;
  bool request_motor_data(
    uint8_t node_id, uint16_t data_type,
    std::vector<uint8_t> & response, int timeout_ms = 100) override;
};

/**
 * @brief CANopen-specific controller for MG6010 and other standard motors
 */
class CANopenController : public EnhancedCANController
{
public:
  // Standard CANopen communication objects
  enum CANopenCOB : uint16_t
  {
    NMT = 0x000,
    SYNC = 0x080,
    EMCY_BASE = 0x080,    // Emergency + Node ID
    TPDO1_BASE = 0x180,   // Transmit PDO 1 + Node ID
    RPDO1_BASE = 0x200,   // Receive PDO 1 + Node ID
    TPDO2_BASE = 0x280,   // Transmit PDO 2 + Node ID
    RPDO2_BASE = 0x300,   // Receive PDO 2 + Node ID
    TPDO3_BASE = 0x380,   // Transmit PDO 3 + Node ID
    RPDO3_BASE = 0x400,   // Receive PDO 3 + Node ID
    TPDO4_BASE = 0x480,   // Transmit PDO 4 + Node ID
    RPDO4_BASE = 0x500,   // Receive PDO 4 + Node ID
    TSDO_BASE = 0x580,    // Transmit SDO + Node ID
    RSDO_BASE = 0x600,    // Receive SDO + Node ID
    HEARTBEAT_BASE = 0x700 // Heartbeat + Node ID
  };

  bool send_motor_command(
    uint8_t node_id, uint16_t command_code,
    const std::vector<uint8_t> & data) override;
  bool request_motor_data(
    uint8_t node_id, uint16_t data_type,
    std::vector<uint8_t> & response, int timeout_ms = 100) override;

  // CANopen-specific methods
  bool send_nmt_command(uint8_t node_id, uint8_t command);
  bool send_sync();
  bool read_object_dictionary(
    uint8_t node_id, uint16_t index, uint8_t subindex,
    std::vector<uint8_t> & data);
  bool write_object_dictionary(
    uint8_t node_id, uint16_t index, uint8_t subindex,
    const std::vector<uint8_t> & data);
};

// =============================================================================
// CAN INTERFACE FACTORY
// =============================================================================

/**
 * @brief Factory for creating protocol-specific CAN controllers
 */
class CANControllerFactory
{
public:
  static std::unique_ptr<EnhancedCANController> create_controller(CANProtocol protocol);
  static std::unique_ptr<EnhancedCANController> create_auto_detect_controller(
    const std::string & interface_name, int detection_time_ms = 5000);

  // Register custom protocol implementations
  static void register_protocol(
    CANProtocol protocol,
    std::function<std::unique_ptr<EnhancedCANController>()> factory_func);
};

} // namespace motor_control_ros2
