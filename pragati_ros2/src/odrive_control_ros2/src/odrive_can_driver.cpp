// Copyright 2025 Pragati Robotics
// ODrive CAN Driver Implementation

#include "odrive_control_ros2/odrive_can_driver.hpp"
#include <iostream>

namespace odrive_can {

using namespace odrive_cansimple;

// ============================================================================
// Constructor / Destructor
// ============================================================================

ODriveCanDriver::ODriveCanDriver(std::shared_ptr<odrive_cansimple::SocketCANInterface> can_interface)
  : can_interface_(can_interface)
{
}

// ============================================================================
// Motor Management
// ============================================================================

void ODriveCanDriver::addMotor(uint8_t node_id) {
  std::lock_guard<std::mutex> lock(state_mutex_);
  if (motor_states_.find(node_id) == motor_states_.end()) {
    MotorState state;
    state.node_id = node_id;
    motor_states_[node_id] = state;
  }
}

const ODriveCanDriver::MotorState* ODriveCanDriver::getMotorState(uint8_t node_id) const {
  std::lock_guard<std::mutex> lock(state_mutex_);
  auto it = motor_states_.find(node_id);
  if (it != motor_states_.end()) {
    return &it->second;
  }
  return nullptr;
}

std::optional<ODriveCanDriver::MotorState> ODriveCanDriver::getMotorStateSnapshot(uint8_t node_id) const {
  std::lock_guard<std::mutex> lock(state_mutex_);
  auto it = motor_states_.find(node_id);
  if (it != motor_states_.end()) {
    return it->second;  // Return a copy
  }
  return std::nullopt;
}

bool ODriveCanDriver::hasMotor(uint8_t node_id) const {
  std::lock_guard<std::mutex> lock(state_mutex_);
  return motor_states_.find(node_id) != motor_states_.end();
}

// ============================================================================
// High-Level TX Commands
// ============================================================================

bool ODriveCanDriver::estop(uint8_t node_id) {
  return sendCommand(node_id, CMD::ESTOP, encode_estop());
}

bool ODriveCanDriver::setAxisState(uint8_t node_id, uint32_t state) {
  return sendCommand(node_id, CMD::SET_AXIS_STATE, encode_set_axis_state(state));
}

bool ODriveCanDriver::setControllerMode(uint8_t node_id, uint32_t control_mode, uint32_t input_mode) {
  return sendCommand(node_id, CMD::SET_CONTROLLER_MODE, encode_set_controller_mode(control_mode, input_mode));
}

bool ODriveCanDriver::setInputPos(uint8_t node_id, float position, float vel_ff, float torque_ff) {
  return sendCommand(node_id, CMD::SET_INPUT_POS, encode_set_input_pos(position, vel_ff, torque_ff));
}

bool ODriveCanDriver::setInputVel(uint8_t node_id, float velocity, float torque_ff) {
  return sendCommand(node_id, CMD::SET_INPUT_VEL, encode_set_input_vel(velocity, torque_ff));
}

bool ODriveCanDriver::setInputTorque(uint8_t node_id, float torque) {
  return sendCommand(node_id, CMD::SET_INPUT_TORQUE, encode_set_input_torque(torque));
}

bool ODriveCanDriver::setLimits(uint8_t node_id, float vel_limit, float current_limit) {
  return sendCommand(node_id, CMD::SET_LIMITS, encode_set_limits(vel_limit, current_limit));
}

bool ODriveCanDriver::setTrajVelLimit(uint8_t node_id, float limit) {
  return sendCommand(node_id, CMD::SET_TRAJ_VEL_LIMIT, encode_set_traj_vel_limit(limit));
}

bool ODriveCanDriver::setTrajAccelLimits(uint8_t node_id, float accel, float decel) {
  return sendCommand(node_id, CMD::SET_TRAJ_ACCEL_LIMITS, encode_set_traj_accel_limits(accel, decel));
}

bool ODriveCanDriver::setTrajInertia(uint8_t node_id, float inertia) {
  return sendCommand(node_id, CMD::SET_TRAJ_INERTIA, encode_set_traj_inertia(inertia));
}

bool ODriveCanDriver::startAnticogging(uint8_t /* node_id */) {
  // Note: START_ANTICOGGING not in DBC 0.6.10 - keeping for backwards compatibility
  return false;  // Not supported in this firmware version
}

bool ODriveCanDriver::clearErrors(uint8_t node_id, uint8_t identify) {
  return sendCommand(node_id, CMD::CLEAR_ERRORS, encode_clear_errors(identify));
}

bool ODriveCanDriver::reboot(uint8_t node_id, uint8_t action) {
  return sendCommand(node_id, CMD::REBOOT, encode_reboot(action));
}

bool ODriveCanDriver::setAxisNodeId(uint8_t node_id, uint32_t new_node_id) {
  return sendCommand(node_id, CMD::SET_AXIS_NODE_ID, encode_set_axis_node_id(new_node_id));
}

bool ODriveCanDriver::setAbsolutePosition(uint8_t node_id, float position) {
  return sendCommand(node_id, CMD::SET_ABSOLUTE_POSITION, encode_set_absolute_position(position));
}

bool ODriveCanDriver::setPosGain(uint8_t node_id, float pos_gain) {
  return sendCommand(node_id, CMD::SET_POS_GAIN, encode_set_pos_gain(pos_gain));
}

bool ODriveCanDriver::setVelGains(uint8_t node_id, float vel_gain, float vel_integrator_gain) {
  return sendCommand(node_id, CMD::SET_VEL_GAINS, encode_set_vel_gains(vel_gain, vel_integrator_gain));
}

bool ODriveCanDriver::enterDfuMode(uint8_t node_id) {
  return sendCommand(node_id, CMD::ENTER_DFU_MODE, encode_enter_dfu_mode());
}

// ============================================================================
// RTR Requests
// ============================================================================

bool ODriveCanDriver::requestVersion(uint8_t node_id) {
  return sendRTR(node_id, CMD::GET_VERSION);
}

bool ODriveCanDriver::requestEncoderEstimates(uint8_t node_id) {
  return sendRTR(node_id, CMD::GET_ENCODER_ESTIMATES);
}

bool ODriveCanDriver::requestIq(uint8_t node_id) {
  return sendRTR(node_id, CMD::GET_IQ);
}

bool ODriveCanDriver::requestTemperature(uint8_t node_id) {
  return sendRTR(node_id, CMD::GET_TEMPERATURE);
}

bool ODriveCanDriver::requestBusVoltageCurrent(uint8_t node_id) {
  return sendRTR(node_id, CMD::GET_BUS_VOLTAGE_CURRENT);
}

bool ODriveCanDriver::requestTorques(uint8_t node_id) {
  return sendRTR(node_id, CMD::GET_TORQUES);
}

bool ODriveCanDriver::requestPowers(uint8_t node_id) {
  return sendRTR(node_id, CMD::GET_POWERS);
}

bool ODriveCanDriver::requestErrorStatus(uint8_t node_id) {
  return sendRTR(node_id, CMD::GET_ERROR);
}

// ============================================================================
// Frame Processing (RX message handling)
// ============================================================================

bool ODriveCanDriver::handleFrame(uint16_t arb_id, const std::vector<uint8_t>& data) {
  uint8_t node_id = extract_node_id(arb_id);
  uint8_t cmd_id = extract_cmd_id(arb_id);

  // Check if this motor is registered
  if (!hasMotor(node_id)) {
    return false;
  }

  std::lock_guard<std::mutex> lock(state_mutex_);
  MotorState& state = motor_states_[node_id];
  auto now = std::chrono::steady_clock::now();

  // Decode based on command ID (from DBC 0.6.10)
  switch (cmd_id) {
    case CMD::GET_VERSION:
      if (data.size() >= 8) {
        state.version = Version::decode(data.data());
        state.last_version_time = now;
        return true;
      }
      break;

    case CMD::HEARTBEAT:
      if (data.size() >= 8) {
        state.heartbeat = Heartbeat::decode(data.data());
        state.last_heartbeat_time = now;
        return true;
      }
      break;

    case CMD::GET_ERROR:
      if (data.size() >= 8) {
        state.error_status = ErrorStatus::decode(data.data());
        state.last_error_status_time = now;
        return true;
      }
      break;

    case CMD::GET_ENCODER_ESTIMATES:
      if (data.size() >= 8) {
        state.encoder_estimates = EncoderEstimates::decode(data.data());
        state.last_encoder_estimates_time = now;
        return true;
      }
      break;

    case CMD::GET_IQ:
      if (data.size() >= 8) {
        state.iq_values = IqValues::decode(data.data());
        state.last_iq_time = now;
        return true;
      }
      break;

    case CMD::GET_TEMPERATURE:
      if (data.size() >= 8) {
        state.temperature = Temperature::decode(data.data());
        state.last_temperature_time = now;
        return true;
      }
      break;

    case CMD::GET_BUS_VOLTAGE_CURRENT:
      if (data.size() >= 8) {
        state.bus_voltage_current = BusVoltageCurrent::decode(data.data());
        state.last_bus_voltage_current_time = now;
        return true;
      }
      break;

    case CMD::GET_TORQUES:
      if (data.size() >= 8) {
        state.torques = Torques::decode(data.data());
        state.last_torques_time = now;
        return true;
      }
      break;

    case CMD::GET_POWERS:
      if (data.size() >= 8) {
        state.powers = Powers::decode(data.data());
        state.last_powers_time = now;
        return true;
      }
      break;

    default:
      // Unknown command ID or not implemented
      return false;
  }

  return false;  // Insufficient data length
}

// ============================================================================
// Helper Methods (Private)
// ============================================================================

bool ODriveCanDriver::sendCommand(uint8_t node_id, uint8_t cmd_id, const std::vector<uint8_t>& data) {
  if (!can_interface_) {
    return false;
  }

  uint16_t arb_id = make_arbitration_id(node_id, cmd_id);
  return can_interface_->send_frame(arb_id, data);
}

bool ODriveCanDriver::sendRTR(uint8_t node_id, uint8_t cmd_id) {
  if (!can_interface_) {
    return false;
  }

  uint16_t arb_id = make_arbitration_id(node_id, cmd_id);
  std::vector<uint8_t> empty_data;  // RTR frames have no data
  return can_interface_->send_frame(arb_id, empty_data, true);  // is_rtr = true
}

}  // namespace odrive_can
