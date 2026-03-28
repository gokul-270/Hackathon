// Copyright 2025 Pragati Robotics
// ODrive CAN Driver - Standalone driver layer for ODrive Pro CANSimple 0.6.x
// This is a reusable driver layer that works independently of ROS2

#ifndef ODRIVE_CONTROL_ROS2__ODRIVE_CAN_DRIVER_HPP_
#define ODRIVE_CONTROL_ROS2__ODRIVE_CAN_DRIVER_HPP_

#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <chrono>
#include <optional>

#include "odrive_control_ros2/odrive_cansimple_protocol.hpp"
#include "odrive_control_ros2/socketcan_interface.hpp"

namespace odrive_can {

/**
 * @brief ODrive CAN Driver - High-level API for ODrive Pro via CANSimple protocol
 * 
 * This class provides:
 * - High-level command methods (setInputPos, setAxisState, etc.)
 * - Automatic message encoding/decoding
 * - Per-motor state caching with timestamps
 * - Thread-safe state access
 * - RTR (Remote Transmission Request) support
 * 
 * This driver is standalone and does NOT depend on ROS2.
 * It can be used in any C++ application.
 */
class ODriveCanDriver {
public:
  /**
   * @brief Motor state structure - caches latest received data for each motor
   */
  struct MotorState {
    // Identity
    uint8_t node_id;
    
    // Latest received messages (from DBC 0.6.10)
    std::optional<odrive_cansimple::Version> version;
    std::optional<odrive_cansimple::Heartbeat> heartbeat;
    std::optional<odrive_cansimple::ErrorStatus> error_status;
    std::optional<odrive_cansimple::EncoderEstimates> encoder_estimates;
    std::optional<odrive_cansimple::IqValues> iq_values;
    std::optional<odrive_cansimple::Temperature> temperature;
    std::optional<odrive_cansimple::BusVoltageCurrent> bus_voltage_current;
    std::optional<odrive_cansimple::Torques> torques;
    std::optional<odrive_cansimple::Powers> powers;
    
    // Timestamps for freshness checking
    std::chrono::steady_clock::time_point last_version_time;
    std::chrono::steady_clock::time_point last_heartbeat_time;
    std::chrono::steady_clock::time_point last_error_status_time;
    std::chrono::steady_clock::time_point last_encoder_estimates_time;
    std::chrono::steady_clock::time_point last_iq_time;
    std::chrono::steady_clock::time_point last_temperature_time;
    std::chrono::steady_clock::time_point last_bus_voltage_current_time;
    std::chrono::steady_clock::time_point last_torques_time;
    std::chrono::steady_clock::time_point last_powers_time;
  };

  /**
   * @brief Constructor
   * @param can_interface Shared pointer to SocketCAN interface
   */
  explicit ODriveCanDriver(std::shared_ptr<odrive_cansimple::SocketCANInterface> can_interface);

  /**
   * @brief Destructor
   */
  ~ODriveCanDriver() = default;

  // ========================================================================
  // Motor Management
  // ========================================================================

  /**
   * @brief Register a motor node ID to track its state
   * @param node_id ODrive node ID (0-63)
   */
  void addMotor(uint8_t node_id);

  /**
   * @brief Get the current state of a motor (unsafe - pointer may be invalidated)
   * @param node_id ODrive node ID
   * @return Pointer to MotorState (nullptr if not registered)
   * @warning This method is NOT thread-safe for reading. Use getMotorStateSnapshot() instead.
   */
  const MotorState* getMotorState(uint8_t node_id) const;

  /**
   * @brief Get a thread-safe snapshot of motor state
   * @param node_id ODrive node ID
   * @return Optional containing MotorState copy, or std::nullopt if not registered
   */
  std::optional<MotorState> getMotorStateSnapshot(uint8_t node_id) const;

  /**
   * @brief Check if a motor is registered
   * @param node_id ODrive node ID
   * @return true if motor is registered
   */
  bool hasMotor(uint8_t node_id) const;

  // ========================================================================
  // High-Level TX Commands (Host → ODrive)
  // ========================================================================

  /**
   * @brief Emergency stop - immediately disarms the motor
   * @param node_id ODrive node ID
   * @return true if sent successfully
   */
  bool estop(uint8_t node_id);

  /**
   * @brief Set the axis state (IDLE, CLOSED_LOOP_CONTROL, etc.)
   * @param node_id ODrive node ID
   * @param state Requested state (use odrive_cansimple::AXIS_STATE constants)
   * @return true if sent successfully
   */
  bool setAxisState(uint8_t node_id, uint32_t state);

  /**
   * @brief Set controller mode and input mode
   * @param node_id ODrive node ID
   * @param control_mode Control mode (POSITION_CONTROL, VELOCITY_CONTROL, etc.)
   * @param input_mode Input mode (PASSTHROUGH, TRAP_TRAJ, POS_FILTER, etc.)
   * @return true if sent successfully
   */
  bool setControllerMode(uint8_t node_id, uint32_t control_mode, uint32_t input_mode);

  /**
   * @brief Set position setpoint with optional feedforward
   * @param node_id ODrive node ID
   * @param position Position in turns
   * @param vel_ff Velocity feedforward (turns/s), default 0
   * @param torque_ff Torque feedforward (Nm), default 0
   * @return true if sent successfully
   */
  bool setInputPos(uint8_t node_id, float position, float vel_ff = 0.0f, float torque_ff = 0.0f);

  /**
   * @brief Set velocity setpoint with optional torque feedforward
   * @param node_id ODrive node ID
   * @param velocity Velocity in turns/s
   * @param torque_ff Torque feedforward (Nm), default 0
   * @return true if sent successfully
   */
  bool setInputVel(uint8_t node_id, float velocity, float torque_ff = 0.0f);

  /**
   * @brief Set torque setpoint
   * @param node_id ODrive node ID
   * @param torque Torque in Nm
   * @return true if sent successfully
   */
  bool setInputTorque(uint8_t node_id, float torque);

  /**
   * @brief Set velocity and current limits
   * @param node_id ODrive node ID
   * @param vel_limit Velocity limit (turns/s)
   * @param current_limit Current limit (A)
   * @return true if sent successfully
   */
  bool setLimits(uint8_t node_id, float vel_limit, float current_limit);

  /**
   * @brief Set trajectory velocity limit
   * @param node_id ODrive node ID
   * @param limit Trajectory velocity limit (turns/s)
   * @return true if sent successfully
   */
  bool setTrajVelLimit(uint8_t node_id, float limit);

  /**
   * @brief Set trajectory acceleration/deceleration limits
   * @param node_id ODrive node ID
   * @param accel Acceleration limit (turns/s²)
   * @param decel Deceleration limit (turns/s²)
   * @return true if sent successfully
   */
  bool setTrajAccelLimits(uint8_t node_id, float accel, float decel);

  /**
   * @brief Set trajectory inertia
   * @param node_id ODrive node ID
   * @param inertia Inertia (kg⋅m²)
   * @return true if sent successfully
   */
  bool setTrajInertia(uint8_t node_id, float inertia);

  /**
   * @brief Start anticogging calibration
   * @param node_id ODrive node ID
   * @return true if sent successfully
   */
  bool startAnticogging(uint8_t node_id);

  /**
   * @brief Clear all errors
   * @param node_id ODrive node ID
   * @param identify Optional identify flag (default 0)
   * @return true if sent successfully
   */
  bool clearErrors(uint8_t node_id, uint8_t identify = 0);

  /**
   * @brief Reboot the ODrive
   * @param node_id ODrive node ID
   * @param action Action (0=reboot, 1=save_config, 2=erase_config, 3=enter_dfu)
   * @return true if sent successfully
   */
  bool reboot(uint8_t node_id, uint8_t action = 0);

  /**
   * @brief Set the ODrive's CAN node ID (changes node_id permanently)
   * @param node_id Current ODrive node ID
   * @param new_node_id New node ID to assign
   * @return true if sent successfully
   */
  bool setAxisNodeId(uint8_t node_id, uint32_t new_node_id);

  /**
   * @brief Set absolute position reference frame
   * @param node_id ODrive node ID
   * @param position Absolute position in turns
   * @return true if sent successfully
   */
  bool setAbsolutePosition(uint8_t node_id, float position);

  /**
   * @brief Set position gain
   * @param node_id ODrive node ID
   * @param pos_gain Position gain ((rev/s) / rev)
   * @return true if sent successfully
   */
  bool setPosGain(uint8_t node_id, float pos_gain);

  /**
   * @brief Set velocity gains
   * @param node_id ODrive node ID
   * @param vel_gain Velocity gain (Nm / (rev/s))
   * @param vel_integrator_gain Velocity integrator gain (Nm / rev)
   * @return true if sent successfully
   */
  bool setVelGains(uint8_t node_id, float vel_gain, float vel_integrator_gain);

  /**
   * @brief Enter DFU (Device Firmware Update) mode
   * @param node_id ODrive node ID
   * @return true if sent successfully
   */
  bool enterDfuMode(uint8_t node_id);

  // ========================================================================
  // RTR Requests (Request data from ODrive)
  // ========================================================================

  /**
   * @brief Request version information
   * @param node_id ODrive node ID
   * @return true if RTR sent successfully
   */
  bool requestVersion(uint8_t node_id);

  /**
   * @brief Request encoder estimates (position, velocity)
   * @param node_id ODrive node ID
   * @return true if RTR sent successfully
   */
  bool requestEncoderEstimates(uint8_t node_id);

  /**
   * @brief Request IQ values (setpoint, measured)
   * @param node_id ODrive node ID
   * @return true if RTR sent successfully
   */
  bool requestIq(uint8_t node_id);

  /**
   * @brief Request temperature (FET, motor)
   * @param node_id ODrive node ID
   * @return true if RTR sent successfully
   */
  bool requestTemperature(uint8_t node_id);

  /**
   * @brief Request bus voltage and current
   * @param node_id ODrive node ID
   * @return true if RTR sent successfully
   */
  bool requestBusVoltageCurrent(uint8_t node_id);

  /**
   * @brief Request torques (target, estimate)
   * @param node_id ODrive node ID
   * @return true if RTR sent successfully
   */
  bool requestTorques(uint8_t node_id);

  /**
   * @brief Request powers (electrical, mechanical)
   * @param node_id ODrive node ID
   * @return true if RTR sent successfully
   */
  bool requestPowers(uint8_t node_id);

  /**
   * @brief Request error status (active_errors, disarm_reason)
   * @param node_id ODrive node ID
   * @return true if RTR sent successfully
   */
  bool requestErrorStatus(uint8_t node_id);

  // ========================================================================
  // Frame Processing (RX message handling)
  // ========================================================================

  /**
   * @brief Process a received CAN frame and update motor state
   * @param arb_id CAN arbitration ID
   * @param data CAN frame data (0-8 bytes)
   * @return true if frame was successfully decoded and state updated
   */
  bool handleFrame(uint16_t arb_id, const std::vector<uint8_t>& data);

private:
  // CAN interface
  std::shared_ptr<odrive_cansimple::SocketCANInterface> can_interface_;

  // Motor state storage (thread-safe)
  mutable std::mutex state_mutex_;
  std::map<uint8_t, MotorState> motor_states_;

  // Helper methods
  bool sendCommand(uint8_t node_id, uint8_t cmd_id, const std::vector<uint8_t>& data);
  bool sendRTR(uint8_t node_id, uint8_t cmd_id);
};

}  // namespace odrive_can

#endif  // ODRIVE_CONTROL_ROS2__ODRIVE_CAN_DRIVER_HPP_
