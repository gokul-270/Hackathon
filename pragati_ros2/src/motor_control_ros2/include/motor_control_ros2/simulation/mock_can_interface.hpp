/*
 * Mock CAN Interface for Unit Testing
 *
 * This file provides comprehensive mock implementations of CAN interfaces
 * for testing motor control systems without requiring actual hardware.
 *
 * Features:
 * 1. Configurable response simulation
 * 2. Message history tracking
 * 3. Error injection capabilities
 * 4. Latency simulation
 * 5. Easy-to-use test helpers
 */

#pragma once

#include "motor_control_ros2/motor_abstraction.hpp"
// Note: enhanced_can_interface.hpp moved to archive - MockEnhancedCANController removed
#include "motor_control_ros2/simulation/motor_physics_simulator.hpp"
#include <queue>
#include <map>
#include <mutex>
#include <chrono>
#include <functional>
#include <set>
#include <cstring>
#include <deque>

// GMock is optional - only needed for SimpleMockCANInterface and MockEnhancedCANController
#ifdef HAS_GMOCK
#include <gmock/gmock.h>
#endif

namespace motor_control_ros2
{
namespace test
{

// =============================================================================
// SIMPLE MOCK CAN INTERFACE (for basic CANInterface - requires GMock)
// =============================================================================

#ifdef HAS_GMOCK
/**
 * @brief Simple mock CAN interface for basic testing
 *
 * Use this when you need a lightweight mock with GMock MOCK_METHOD support.
 */
class SimpleMockCANInterface : public CANInterface
{
public:
  MOCK_METHOD(bool, initialize, (const std::string & interface_name, uint32_t baud_rate), (override));
  MOCK_METHOD(bool, send_message, (uint32_t id, const std::vector<uint8_t> & data), (override));
  MOCK_METHOD(bool, receive_message, (uint32_t & id, std::vector<uint8_t> & data, int timeout_ms), (override));
  MOCK_METHOD(bool, configure_node, (uint8_t node_id, uint32_t baud_rate), (override));
  MOCK_METHOD(bool, is_connected, (), (const, override));
  MOCK_METHOD(std::string, get_last_error, (), (const, override));
};
#endif

// =============================================================================
// CONFIGURABLE MOCK CAN INTERFACE (with behavior simulation)
// =============================================================================

/**
 * @brief Message response configuration
 */
struct MessageResponse
{
  uint32_t response_id;
  std::vector<uint8_t> response_data;
  int delay_ms{0};
  bool should_fail{false};

  MessageResponse() = default;
  MessageResponse(uint32_t id, const std::vector<uint8_t> & data)
    : response_id(id), response_data(data) {}
};

/**
 * @brief Configurable mock CAN interface with realistic behavior
 *
 * Use this when you need more control over CAN behavior in tests.
 * This mock actually implements the interface methods with configurable responses.
 */
class ConfigurableMockCANInterface : public CANInterface
{
public:
  ConfigurableMockCANInterface()
    : connected_(false), initialized_(false), error_injection_enabled_(false) {}

  virtual ~ConfigurableMockCANInterface() = default;

  // =============================================================================
  // CANInterface Implementation
  // =============================================================================

  bool initialize(const std::string & interface_name, uint32_t baud_rate = 1000000) override
  {
    std::lock_guard<std::mutex> lock(mutex_);

    if (error_injection_enabled_ && next_operation_fails_) {
      last_error_ = "Simulated initialization failure";
      next_operation_fails_ = false;
      return false;
    }

    interface_name_ = interface_name;
    baud_rate_ = baud_rate;
    connected_ = true;
    initialized_ = true;
    last_error_.clear();

    init_call_count_++;
    return true;
  }

  bool send_message(uint32_t id, const std::vector<uint8_t> & data) override
  {
    std::lock_guard<std::mutex> lock(mutex_);

    if (!connected_) {
      last_error_ = "CAN interface not connected";
      return false;
    }

    if (error_injection_enabled_ && next_operation_fails_) {
      last_error_ = "Simulated send failure";
      next_operation_fails_ = false;
      send_errors_++;
      return false;
    }

    // Record sent message
    SentMessage msg;
    msg.id = id;
    msg.data = data;
    msg.timestamp = std::chrono::steady_clock::now();
    sent_messages_.push_back(msg);

    // Task 3.2 -- Check if the target motor has simulation enabled.
    // Motor ID is derived from arbitration ID: motor_id = arb_id - 0x140
    if (id >= MG6010Protocol::BASE_ARBITRATION_ID && data.size() >= 1) {
      uint8_t motor_id = static_cast<uint8_t>(id - MG6010Protocol::BASE_ARBITRATION_ID);
      if (simulator_.hasMotor(motor_id)) {
        // Delegate to simulator instead of static response map
        uint8_t cmd_byte = data[0];
        std::vector<uint8_t> payload(data.begin() + 1, data.end());
        auto result = simulator_.processCommand(motor_id, cmd_byte, payload);
        if (result.has_value()) {
          auto & [resp_id, resp_data] = result.value();
          // Task 3.5 -- Latency simulation: check motor config
          const auto * state = simulator_.getMotorState(motor_id);
          double latency_ms = (state != nullptr) ? state->config.response_latency_ms : 0.0;
          if (latency_ms > 0.0) {
            // Queue with timestamp; released by advance_time()
            int64_t available_at = simulated_time_ms_ +
                                   static_cast<int64_t>(latency_ms);
            latency_queue_.push_back({resp_id, resp_data, available_at});
          } else {
            received_messages_.push(MessageResponse{resp_id, resp_data});
          }
        }
        // If result is empty (CAN timeout fault), no response is queued
        messages_sent_++;
        return true;
      }
    }

    // Check for configured response (existing static response path)
    auto it = response_map_.find(id);
    if (it != response_map_.end()) {
      // Queue response for later retrieval
      if (it->second.delay_ms > 0) {
        // Simulate latency - in real test, you'd wait or track time
        // For simplicity, we just queue it immediately
      }

      if (!it->second.should_fail) {
        received_messages_.push(it->second);
      }
    }

    messages_sent_++;
    return true;
  }

  bool receive_message(uint32_t & id, std::vector<uint8_t> & data, int timeout_ms = 10) override
  {
    (void)timeout_ms;  // Timeout not simulated in mock - message available immediately
    std::lock_guard<std::mutex> lock(mutex_);

    if (!connected_) {
      last_error_ = "CAN interface not connected";
      return false;
    }

    if (error_injection_enabled_ && next_operation_fails_) {
      last_error_ = "Simulated receive failure";
      next_operation_fails_ = false;
      receive_errors_++;
      return false;
    }

    // Check if there's a queued message
    if (!received_messages_.empty()) {
      MessageResponse response = received_messages_.front();
      received_messages_.pop();

      id = response.response_id;
      data = response.response_data;

      messages_received_++;
      return true;
    }

    // No message available
    last_error_ = "No message received within timeout";
    return false;
  }

  bool configure_node(uint8_t node_id, uint32_t baud_rate = 0) override
  {
    (void)baud_rate;  // Baud rate per-node configuration not used in mock
    std::lock_guard<std::mutex> lock(mutex_);

    if (!connected_) {
      last_error_ = "CAN interface not connected";
      return false;
    }

    if (error_injection_enabled_ && next_operation_fails_) {
      last_error_ = "Simulated node configuration failure";
      next_operation_fails_ = false;
      return false;
    }

    configured_nodes_.insert(node_id);
    return true;
  }

  bool is_connected() const override
  {
    std::lock_guard<std::mutex> lock(mutex_);
    return connected_;
  }

  std::string get_last_error() const override
  {
    std::lock_guard<std::mutex> lock(mutex_);
    return last_error_;
  }

  // =============================================================================
  // Test Configuration Methods
  // =============================================================================

  /**
   * @brief Configure automatic response for a specific message ID
   */
  void configure_response(uint32_t message_id, uint32_t response_id,
                         const std::vector<uint8_t> & response_data,
                         int delay_ms = 0, bool should_fail = false)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    MessageResponse response{response_id, response_data};
    response.delay_ms = delay_ms;
    response.should_fail = should_fail;
    response_map_[message_id] = response;
  }

  /**
   * @brief Queue a message to be received
   */
  void queue_receive_message(uint32_t id, const std::vector<uint8_t> & data)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    received_messages_.push(MessageResponse{id, data});
  }

  /**
   * @brief Clear all configured responses
   */
  void clear_responses()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    response_map_.clear();
    while (!received_messages_.empty()) {
      received_messages_.pop();
    }
  }

  /**
   * @brief Inject error on next operation
   */
  void inject_error_on_next_operation()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    error_injection_enabled_ = true;
    next_operation_fails_ = true;
  }

  /**
   * @brief Simulate disconnection
   */
  void simulate_disconnect()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    connected_ = false;
    last_error_ = "CAN bus disconnected";
  }

  /**
   * @brief Simulate reconnection
   */
  void simulate_reconnect()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    connected_ = true;
    last_error_.clear();
  }

  // =============================================================================
  // Motor Simulation Methods (Tasks 3.1, 3.3, 3.4)
  // =============================================================================

  /**
   * @brief Enable physics simulation for a specific motor.
   *
   * When enabled, commands sent to the motor's arbitration ID (0x140 + motor_id)
   * are delegated to the MotorPhysicsSimulator instead of the static response map.
   */
  void enable_motor_simulation(uint8_t motor_id, const MotorSimConfig & config)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    simulator_.addMotor(motor_id, config);
  }

  /**
   * @brief Disable physics simulation for a specific motor.
   *
   * Subsequent commands to this motor will fall through to the static response
   * map (configure_response) as before.
   */
  void disable_motor_simulation(uint8_t motor_id)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    simulator_.removeMotor(motor_id);
  }

  /**
   * @brief Advance simulated time for all simulated motors.
   *
   * Updates position, velocity, temperature, and encoder state according to
   * the configured physics model. Also releases latency-delayed responses
   * whose scheduled time has been reached.
   */
  void advance_time(std::chrono::milliseconds dt)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    simulator_.advanceTime(dt);
    simulated_time_ms_ += dt.count();

    // Release latency-delayed responses whose time has arrived
    while (!latency_queue_.empty() &&
           latency_queue_.front().available_at_ms <= simulated_time_ms_) {
      const auto & entry = latency_queue_.front();
      received_messages_.push(
        MessageResponse{entry.response_id, entry.response_data});
      latency_queue_.pop_front();
    }
  }

  /**
   * @brief Inject a fault on a simulated motor.
   */
  void inject_fault(uint8_t motor_id, FaultType fault)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    simulator_.injectFault(motor_id, fault);
  }

  /**
   * @brief Inject a fault with configuration on a simulated motor.
   */
  void inject_fault(uint8_t motor_id, FaultType fault, const FaultConfig & config)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    simulator_.injectFault(motor_id, fault, config);
  }

  /**
   * @brief Clear a specific fault on a simulated motor.
   */
  void clear_fault(uint8_t motor_id, FaultType fault)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    simulator_.clearFault(motor_id, fault);
  }

  /**
   * @brief Clear all faults on a simulated motor.
   */
  void clear_all_faults(uint8_t motor_id)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    simulator_.clearAllFaults(motor_id);
  }

  /**
   * @brief Get read-only access to a simulated motor's state.
   */
  const MotorState * get_motor_state(uint8_t motor_id) const
  {
    std::lock_guard<std::mutex> lock(mutex_);
    return simulator_.getMotorState(motor_id);
  }

  // =============================================================================
  // Test Inspection Methods
  // =============================================================================

  struct SentMessage
  {
    uint32_t id;
    std::vector<uint8_t> data;
    std::chrono::steady_clock::time_point timestamp;
  };

  /**
   * @brief Get all sent messages (for verification)
   */
  std::vector<SentMessage> get_sent_messages() const
  {
    std::lock_guard<std::mutex> lock(mutex_);
    return sent_messages_;
  }

  /**
   * @brief Get last sent message
   */
  bool get_last_sent_message(uint32_t & id, std::vector<uint8_t> & data) const
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (sent_messages_.empty()) {
      return false;
    }
    const auto & last = sent_messages_.back();
    id = last.id;
    data = last.data;
    return true;
  }

  /**
   * @brief Get count of messages sent with specific ID
   */
  size_t get_message_count(uint32_t id) const
  {
    std::lock_guard<std::mutex> lock(mutex_);
    return std::count_if(sent_messages_.begin(), sent_messages_.end(),
                        [id](const SentMessage & msg) { return msg.id == id; });
  }

  /**
   * @brief Clear message history
   */
  void clear_message_history()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    sent_messages_.clear();
    messages_sent_ = 0;
    messages_received_ = 0;
    send_errors_ = 0;
    receive_errors_ = 0;
  }

  /**
   * @brief Get statistics
   */
  struct Statistics
  {
    size_t messages_sent{0};
    size_t messages_received{0};
    size_t send_errors{0};
    size_t receive_errors{0};
    size_t init_call_count{0};
  };

  Statistics get_statistics() const
  {
    std::lock_guard<std::mutex> lock(mutex_);
    Statistics stats;
    stats.messages_sent = messages_sent_;
    stats.messages_received = messages_received_;
    stats.send_errors = send_errors_;
    stats.receive_errors = receive_errors_;
    stats.init_call_count = init_call_count_;
    return stats;
  }

  /**
   * @brief Reset mock to initial state
   */
  void reset()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    connected_ = false;
    initialized_ = false;
    error_injection_enabled_ = false;
    next_operation_fails_ = false;
    sent_messages_.clear();
    response_map_.clear();
    configured_nodes_.clear();
    while (!received_messages_.empty()) {
      received_messages_.pop();
    }
    messages_sent_ = 0;
    messages_received_ = 0;
    send_errors_ = 0;
    receive_errors_ = 0;
    init_call_count_ = 0;
    last_error_.clear();
    latency_queue_.clear();
    simulated_time_ms_ = 0;
  }

private:
  mutable std::mutex mutex_;

  // State
  bool connected_;
  bool initialized_;
  std::string interface_name_;
  uint32_t baud_rate_;
  std::string last_error_;

  // Message tracking
  std::vector<SentMessage> sent_messages_;
  std::queue<MessageResponse> received_messages_;
  std::map<uint32_t, MessageResponse> response_map_;
  std::set<uint8_t> configured_nodes_;

  // Statistics
  size_t messages_sent_{0};
  size_t messages_received_{0};
  size_t send_errors_{0};
  size_t receive_errors_{0};
  size_t init_call_count_{0};

  // Error injection
  bool error_injection_enabled_;
  bool next_operation_fails_{false};

  // Motor physics simulation (tasks 3.1-3.5)
  MotorPhysicsSimulator simulator_;
  int64_t simulated_time_ms_{0};

  // Latency queue entry for delayed responses (task 3.5)
  struct LatencyEntry
  {
    uint32_t response_id;
    std::vector<uint8_t> response_data;
    int64_t available_at_ms;  // simulated time at which response becomes available
  };
  std::deque<LatencyEntry> latency_queue_;
};

// =============================================================================
// NOTE: MockEnhancedCANController was removed - enhanced_can_interface.hpp
// has been moved to archive/unused_headers_2025-11/
// If needed in future, restore that header and uncomment below.
// =============================================================================

// =============================================================================
// TEST HELPERS
// =============================================================================

/**
 * @brief Helper functions for CAN testing
 *
 * Note: create_test_message removed (depended on UniversalCANMessage from
 * archived enhanced_can_interface.hpp). Use ConfigurableMockCANInterface
 * directly for testing.
 */
class CANTestHelpers
{
public:

  /**
   * @brief Create MG6010 position command message
   */
  static std::vector<uint8_t> create_mg6010_position_command(float position, float velocity = 0.0f)
  {
    std::vector<uint8_t> data(8, 0);
    // MG6010 protocol: bytes 0-3 = position (float), bytes 4-7 = velocity (float)
    std::memcpy(&data[0], &position, sizeof(float));
    std::memcpy(&data[4], &velocity, sizeof(float));
    return data;
  }

  /**
   * @brief Create MG6010 feedback message
   */
  static std::vector<uint8_t> create_mg6010_feedback(float position, float velocity, float torque)
  {
    std::vector<uint8_t> data(8, 0);
    // Simplified feedback: position (2 bytes), velocity (2 bytes), torque (2 bytes)
    int16_t pos_int = static_cast<int16_t>(position * 1000.0f);
    int16_t vel_int = static_cast<int16_t>(velocity * 1000.0f);
    int16_t torque_int = static_cast<int16_t>(torque * 1000.0f);

    std::memcpy(&data[0], &pos_int, sizeof(int16_t));
    std::memcpy(&data[2], &vel_int, sizeof(int16_t));
    std::memcpy(&data[4], &torque_int, sizeof(int16_t));

    return data;
  }

  /**
   * @brief Verify message was sent with expected data
   */
  static bool verify_message_sent(const ConfigurableMockCANInterface & mock,
                                  uint32_t expected_id,
                                  const std::vector<uint8_t> & expected_data)
  {
    auto messages = mock.get_sent_messages();
    for (const auto & msg : messages) {
      if (msg.id == expected_id && msg.data == expected_data) {
        return true;
      }
    }
    return false;
  }
};

}  // namespace test
}  // namespace motor_control_ros2
