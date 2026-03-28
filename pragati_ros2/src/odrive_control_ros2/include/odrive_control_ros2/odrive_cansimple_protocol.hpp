// Copyright 2025 Pragati Robotics
// ODrive CANSimple Protocol v0.6.x Implementation
// This header defines the ODrive CANSimple 0.6.x protocol constants and message structures
// Reference: ODrive Pro firmware 0.6.11

#ifndef ODRIVE_CONTROL_ROS2__ODRIVE_CANSIMPLE_PROTOCOL_HPP_
#define ODRIVE_CONTROL_ROS2__ODRIVE_CANSIMPLE_PROTOCOL_HPP_

#include <cstdint>
#include <cstring>
#include <vector>

namespace odrive_cansimple {

// ============================================================================
// CAN Message Format
// ============================================================================
// Arbitration ID = (node_id << 5) | cmd_id
// - node_id: 0-63 (bits 5-10)
// - cmd_id: 0-31 (bits 0-4)
// - All messages use standard 11-bit CAN ID (not extended)
// - Data: 0-8 bytes, little-endian encoding

constexpr uint8_t NODE_ID_SHIFT = 5;
constexpr uint16_t NODE_ID_MASK = 0x7E0;  // Bits 5-10
constexpr uint16_t CMD_ID_MASK = 0x01F;   // Bits 0-4

inline uint16_t make_arbitration_id(uint8_t node_id, uint8_t cmd_id) {
  return (static_cast<uint16_t>(node_id) << NODE_ID_SHIFT) | (cmd_id & CMD_ID_MASK);
}

inline uint8_t extract_node_id(uint16_t arb_id) {
  return static_cast<uint8_t>((arb_id & NODE_ID_MASK) >> NODE_ID_SHIFT);
}

inline uint8_t extract_cmd_id(uint16_t arb_id) {
  return static_cast<uint8_t>(arb_id & CMD_ID_MASK);
}

// ============================================================================
// Command IDs (ODrive CANSimple 0.6.10 - from official DBC)
// ============================================================================
namespace CMD {
  constexpr uint8_t GET_VERSION = 0x00;
  constexpr uint8_t HEARTBEAT = 0x01;
  constexpr uint8_t ESTOP = 0x02;
  constexpr uint8_t GET_ERROR = 0x03;
  constexpr uint8_t RX_SDO = 0x04;  // Read/write arbitrary parameters
  constexpr uint8_t TX_SDO = 0x05;  // Response to RX_SDO
  constexpr uint8_t SET_AXIS_NODE_ID = 0x06;  // Also called "Address"
  constexpr uint8_t SET_AXIS_STATE = 0x07;
  constexpr uint8_t GET_ENCODER_ESTIMATES = 0x09;
  constexpr uint8_t SET_CONTROLLER_MODE = 0x0B;
  constexpr uint8_t SET_INPUT_POS = 0x0C;
  constexpr uint8_t SET_INPUT_VEL = 0x0D;
  constexpr uint8_t SET_INPUT_TORQUE = 0x0E;
  constexpr uint8_t SET_LIMITS = 0x0F;
  constexpr uint8_t SET_TRAJ_VEL_LIMIT = 0x11;
  constexpr uint8_t SET_TRAJ_ACCEL_LIMITS = 0x12;
  constexpr uint8_t SET_TRAJ_INERTIA = 0x13;
  constexpr uint8_t GET_IQ = 0x14;
  constexpr uint8_t GET_TEMPERATURE = 0x15;
  constexpr uint8_t REBOOT = 0x16;
  constexpr uint8_t GET_BUS_VOLTAGE_CURRENT = 0x17;
  constexpr uint8_t CLEAR_ERRORS = 0x18;
  constexpr uint8_t SET_ABSOLUTE_POSITION = 0x19;
  constexpr uint8_t SET_POS_GAIN = 0x1A;
  constexpr uint8_t SET_VEL_GAINS = 0x1B;
  constexpr uint8_t GET_TORQUES = 0x1C;
  constexpr uint8_t GET_POWERS = 0x1D;
  constexpr uint8_t ENTER_DFU_MODE = 0x1F;
}

// ============================================================================
// Axis States
// ============================================================================
namespace AXIS_STATE {
  constexpr uint32_t UNDEFINED = 0x00;
  constexpr uint32_t IDLE = 0x01;
  constexpr uint32_t STARTUP_SEQUENCE = 0x02;
  constexpr uint32_t FULL_CALIBRATION = 0x03;
  constexpr uint32_t MOTOR_CALIBRATION = 0x04;
  constexpr uint32_t ENCODER_INDEX_SEARCH = 0x06;
  constexpr uint32_t ENCODER_OFFSET_CALIBRATION = 0x07;
  constexpr uint32_t CLOSED_LOOP_CONTROL = 0x08;
  constexpr uint32_t LOCKIN_SPIN = 0x09;
  constexpr uint32_t ENCODER_DIR_FIND = 0x0A;
  constexpr uint32_t HOMING = 0x0B;
}

// ============================================================================
// Control Modes
// ============================================================================
namespace CONTROL_MODE {
  constexpr uint32_t VOLTAGE_CONTROL = 0x00;
  constexpr uint32_t TORQUE_CONTROL = 0x01;
  constexpr uint32_t VELOCITY_CONTROL = 0x02;
  constexpr uint32_t POSITION_CONTROL = 0x03;
}

namespace INPUT_MODE {
  constexpr uint32_t INACTIVE = 0x00;
  constexpr uint32_t PASSTHROUGH = 0x01;
  constexpr uint32_t VEL_RAMP = 0x02;
  constexpr uint32_t POS_FILTER = 0x03;
  constexpr uint32_t MIX_CHANNELS = 0x04;
  constexpr uint32_t TRAP_TRAJ = 0x05;
  constexpr uint32_t TORQUE_RAMP = 0x06;
  constexpr uint32_t MIRROR = 0x07;
  constexpr uint32_t TUNING = 0x08;
}

// ============================================================================
// Message Structures (0.6.x format)
// ============================================================================

// Heartbeat (0x01) - Received cyclically
struct Heartbeat {
  uint32_t axis_error;         // Bytes 0-3
  uint8_t axis_state;          // Byte 4
  uint8_t procedure_result;    // Byte 5
  uint8_t traj_done;           // Byte 6 (0 = trajectory in progress, 1 = done)
  // Byte 7 reserved
  
  static Heartbeat decode(const uint8_t* data) {
    Heartbeat hb;
    std::memcpy(&hb.axis_error, data, 4);
    hb.axis_state = data[4];
    hb.procedure_result = data[5];
    hb.traj_done = data[6];
    return hb;
  }
};

// Get_Error (0x03) - Response to RTR or cyclic
struct ErrorStatus {
  uint32_t active_errors;      // Bytes 0-3
  uint32_t disarm_reason;      // Bytes 4-7
  
  static ErrorStatus decode(const uint8_t* data) {
    ErrorStatus es;
    std::memcpy(&es.active_errors, data, 4);
    std::memcpy(&es.disarm_reason, data + 4, 4);
    return es;
  }
};

// Get_Encoder_Estimates (0x09) - Response to RTR or cyclic
struct EncoderEstimates {
  float pos_estimate;          // Bytes 0-3 (float32, little-endian)
  float vel_estimate;          // Bytes 4-7 (float32, little-endian)
  
  static EncoderEstimates decode(const uint8_t* data) {
    EncoderEstimates ee;
    std::memcpy(&ee.pos_estimate, data, 4);
    std::memcpy(&ee.vel_estimate, data + 4, 4);
    return ee;
  }
};

// Get_Version (0x00) - Response to RTR
struct Version {
  uint8_t protocol_version;    // Byte 0 (always 2)
  uint8_t hw_version_major;    // Byte 1
  uint8_t hw_version_minor;    // Byte 2
  uint8_t hw_version_variant;  // Byte 3
  uint8_t fw_version_major;    // Byte 4
  uint8_t fw_version_minor;    // Byte 5
  uint8_t fw_version_revision; // Byte 6
  uint8_t fw_version_unreleased; // Byte 7
  
  static Version decode(const uint8_t* data) {
    Version v;
    v.protocol_version = data[0];
    v.hw_version_major = data[1];
    v.hw_version_minor = data[2];
    v.hw_version_variant = data[3];
    v.fw_version_major = data[4];
    v.fw_version_minor = data[5];
    v.fw_version_revision = data[6];
    v.fw_version_unreleased = data[7];
    return v;
  }
};

// Get_Iq (0x14) - Response to RTR or cyclic
struct IqValues {
  float iq_setpoint;           // Bytes 0-3 (float32, little-endian)
  float iq_measured;           // Bytes 4-7 (float32, little-endian)
  
  static IqValues decode(const uint8_t* data) {
    IqValues iq;
    std::memcpy(&iq.iq_setpoint, data, 4);
    std::memcpy(&iq.iq_measured, data + 4, 4);
    return iq;
  }
};

// Get_Temperature (0x15) - Response to RTR or cyclic
struct Temperature {
  float fet_temperature;       // Bytes 0-3 (float32, little-endian, deg C)
  float motor_temperature;     // Bytes 4-7 (float32, little-endian, deg C)
  
  static Temperature decode(const uint8_t* data) {
    Temperature temp;
    std::memcpy(&temp.fet_temperature, data, 4);
    std::memcpy(&temp.motor_temperature, data + 4, 4);
    return temp;
  }
};

// Get_Bus_Voltage_Current (0x17) - Response to RTR or cyclic
struct BusVoltageCurrent {
  float bus_voltage;           // Bytes 0-3 (float32, little-endian, V)
  float bus_current;           // Bytes 4-7 (float32, little-endian, A)
  
  static BusVoltageCurrent decode(const uint8_t* data) {
    BusVoltageCurrent bvc;
    std::memcpy(&bvc.bus_voltage, data, 4);
    std::memcpy(&bvc.bus_current, data + 4, 4);
    return bvc;
  }
};

// Get_Torques (0x1C) - Response to RTR or cyclic
struct Torques {
  float torque_target;         // Bytes 0-3 (float32, little-endian, Nm)
  float torque_estimate;       // Bytes 4-7 (float32, little-endian, Nm)
  
  static Torques decode(const uint8_t* data) {
    Torques torq;
    std::memcpy(&torq.torque_target, data, 4);
    std::memcpy(&torq.torque_estimate, data + 4, 4);
    return torq;
  }
};

// Get_Powers (0x1D) - Response to RTR or cyclic
struct Powers {
  float electrical_power;      // Bytes 0-3 (float32, little-endian, W)
  float mechanical_power;      // Bytes 4-7 (float32, little-endian, W)
  
  static Powers decode(const uint8_t* data) {
    Powers pow;
    std::memcpy(&pow.electrical_power, data, 4);
    std::memcpy(&pow.mechanical_power, data + 4, 4);
    return pow;
  }
};

// ============================================================================
// Message Encoding (TX commands)
// ============================================================================

// Estop (0x02) - Emergency stop, no data payload
inline std::vector<uint8_t> encode_estop() {
  return std::vector<uint8_t>();  // Empty payload
}

// Set_Axis_Node_ID (0x06)
inline std::vector<uint8_t> encode_set_axis_node_id(uint32_t node_id) {
  std::vector<uint8_t> data(4);
  std::memcpy(data.data(), &node_id, 4);
  return data;
}

// Set_Axis_State (0x07)
inline std::vector<uint8_t> encode_set_axis_state(uint32_t requested_state) {
  std::vector<uint8_t> data(4);
  std::memcpy(data.data(), &requested_state, 4);
  return data;
}

// Set_Controller_Mode (0x0B)
inline std::vector<uint8_t> encode_set_controller_mode(uint32_t control_mode, uint32_t input_mode) {
  std::vector<uint8_t> data(8);
  std::memcpy(data.data(), &control_mode, 4);
  std::memcpy(data.data() + 4, &input_mode, 4);
  return data;
}

// Set_Input_Pos (0x0C) - CRITICAL: Correct 0.6.x format
// Bytes 0-3: float32 position (little-endian)
// Bytes 4-5: int16 velocity feedforward (scaled by 0.001, little-endian)
// Bytes 6-7: int16 torque feedforward (scaled by 0.001, little-endian)
inline std::vector<uint8_t> encode_set_input_pos(float position, float vel_ff = 0.0f, float torque_ff = 0.0f) {
  std::vector<uint8_t> data(8);
  
  // Position: float32 (bytes 0-3)
  std::memcpy(data.data(), &position, 4);
  
  // Velocity feedforward: scaled to int16 (bytes 4-5)
  int16_t vel_ff_scaled = static_cast<int16_t>(vel_ff / 0.001f);
  std::memcpy(data.data() + 4, &vel_ff_scaled, 2);
  
  // Torque feedforward: scaled to int16 (bytes 6-7)
  int16_t torque_ff_scaled = static_cast<int16_t>(torque_ff / 0.001f);
  std::memcpy(data.data() + 6, &torque_ff_scaled, 2);
  
  return data;
}

// Set_Input_Vel (0x0D)
inline std::vector<uint8_t> encode_set_input_vel(float velocity, float torque_ff = 0.0f) {
  std::vector<uint8_t> data(8);
  std::memcpy(data.data(), &velocity, 4);
  std::memcpy(data.data() + 4, &torque_ff, 4);
  return data;
}

// Set_Input_Torque (0x0E)
inline std::vector<uint8_t> encode_set_input_torque(float torque) {
  std::vector<uint8_t> data(4);
  std::memcpy(data.data(), &torque, 4);
  return data;
}

// Set_Limits (0x0F)
inline std::vector<uint8_t> encode_set_limits(float velocity_limit, float current_limit) {
  std::vector<uint8_t> data(8);
  std::memcpy(data.data(), &velocity_limit, 4);
  std::memcpy(data.data() + 4, &current_limit, 4);
  return data;
}

// Set_Traj_Vel_Limit (0x11)
inline std::vector<uint8_t> encode_set_traj_vel_limit(float traj_vel_limit) {
  std::vector<uint8_t> data(4);
  std::memcpy(data.data(), &traj_vel_limit, 4);
  return data;
}

// Set_Traj_Accel_Limits (0x12)
inline std::vector<uint8_t> encode_set_traj_accel_limits(float accel_limit, float decel_limit) {
  std::vector<uint8_t> data(8);
  std::memcpy(data.data(), &accel_limit, 4);
  std::memcpy(data.data() + 4, &decel_limit, 4);
  return data;
}

// Set_Traj_Inertia (0x13)
inline std::vector<uint8_t> encode_set_traj_inertia(float inertia) {
  std::vector<uint8_t> data(4);
  std::memcpy(data.data(), &inertia, 4);
  return data;
}

// Reboot (0x16) - 1 byte payload with Action
// Action: 0=reboot, 1=save_configuration, 2=erase_configuration, 3=enter_dfu_mode2
inline std::vector<uint8_t> encode_reboot(uint8_t action = 0) {
  std::vector<uint8_t> data(1);
  data[0] = action;
  return data;
}

// Clear_Errors (0x18) - 1 byte payload with Identify flag
inline std::vector<uint8_t> encode_clear_errors(uint8_t identify = 0) {
  std::vector<uint8_t> data(1);
  data[0] = identify;
  return data;
}

// Set_Absolute_Position (0x19)
inline std::vector<uint8_t> encode_set_absolute_position(float position) {
  std::vector<uint8_t> data(4);
  std::memcpy(data.data(), &position, 4);
  return data;
}

// Set_Pos_Gain (0x1A)
inline std::vector<uint8_t> encode_set_pos_gain(float pos_gain) {
  std::vector<uint8_t> data(4);
  std::memcpy(data.data(), &pos_gain, 4);
  return data;
}

// Set_Vel_Gains (0x1B)
inline std::vector<uint8_t> encode_set_vel_gains(float vel_gain, float vel_integrator_gain) {
  std::vector<uint8_t> data(8);
  std::memcpy(data.data(), &vel_gain, 4);
  std::memcpy(data.data() + 4, &vel_integrator_gain, 4);
  return data;
}

// Enter_DFU_Mode (0x1F) - No data payload
inline std::vector<uint8_t> encode_enter_dfu_mode() {
  return std::vector<uint8_t>();  // Empty payload
}

}  // namespace odrive_cansimple

#endif  // ODRIVE_CONTROL_ROS2__ODRIVE_CANSIMPLE_PROTOCOL_HPP_
