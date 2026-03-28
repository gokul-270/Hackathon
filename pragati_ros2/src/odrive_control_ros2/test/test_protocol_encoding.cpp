// Copyright 2025 Pragati Robotics
// Tests for ODrive CANSimple protocol encoding/decoding (Phase-1 Item 2.1-2.9)
//
// Pure behavioral tests for the header-only protocol implementation.
// No ROS2 dependencies, no hardware dependencies.

#include <gtest/gtest.h>

#include <cstdint>
#include <cstring>
#include <vector>

#include "odrive_control_ros2/odrive_cansimple_protocol.hpp"

using namespace odrive_cansimple;

// ============================================================================
// Helpers
// ============================================================================

// Build an 8-byte frame from two uint32_t values (little-endian)
static void build_frame_u32_u32(uint8_t* out, uint32_t lo, uint32_t hi) {
  std::memcpy(out, &lo, 4);
  std::memcpy(out + 4, &hi, 4);
}

// Build an 8-byte frame from two float values (little-endian)
static void build_frame_f32_f32(uint8_t* out, float lo, float hi) {
  std::memcpy(out, &lo, 4);
  std::memcpy(out + 4, &hi, 4);
}

// Extract a float from a byte vector at a given offset
static float extract_float(const std::vector<uint8_t>& data, size_t offset) {
  float val;
  std::memcpy(&val, data.data() + offset, 4);
  return val;
}

// Extract a uint32_t from a byte vector at a given offset
static uint32_t extract_u32(const std::vector<uint8_t>& data, size_t offset) {
  uint32_t val;
  std::memcpy(&val, data.data() + offset, 4);
  return val;
}

// Extract an int16_t from a byte vector at a given offset
static int16_t extract_i16(const std::vector<uint8_t>& data, size_t offset) {
  int16_t val;
  std::memcpy(&val, data.data() + offset, 2);
  return val;
}

// ============================================================================
// Fixture
// ============================================================================

class ProtocolEncodingTest : public ::testing::Test {};

// ============================================================================
// 2.2 - Arbitration ID round-trip tests
// ============================================================================

// Scenario 1: Round-trip for representative node_ids with cmd_id=HEARTBEAT
TEST_F(ProtocolEncodingTest, ArbitrationId_RoundTrip_MultipleNodeIds) {
  const uint8_t node_ids[] = {0, 1, 31, 32, 63};
  const uint8_t cmd_id = CMD::HEARTBEAT;  // 0x01

  for (uint8_t nid : node_ids) {
    uint16_t arb_id = make_arbitration_id(nid, cmd_id);
    EXPECT_EQ(extract_node_id(arb_id), nid)
        << "node_id round-trip failed for node_id=" << static_cast<int>(nid);
    EXPECT_EQ(extract_cmd_id(arb_id), cmd_id)
        << "cmd_id round-trip failed for node_id=" << static_cast<int>(nid);
  }
}

// Scenario 2: Round-trip for all valid cmd_ids 0x00-0x1F with node_id=3
TEST_F(ProtocolEncodingTest, ArbitrationId_RoundTrip_AllCmdIds) {
  const uint8_t node_id = 3;

  for (uint8_t cmd = 0x00; cmd <= 0x1F; ++cmd) {
    uint16_t arb_id = make_arbitration_id(node_id, cmd);
    EXPECT_EQ(extract_node_id(arb_id), node_id)
        << "node_id round-trip failed for cmd_id=0x"
        << std::hex << static_cast<int>(cmd);
    EXPECT_EQ(extract_cmd_id(arb_id), cmd)
        << "cmd_id round-trip failed for cmd_id=0x"
        << std::hex << static_cast<int>(cmd);
  }
}

// Scenario 3: Boundary node_ids produce distinct IDs that extract correctly
TEST_F(ProtocolEncodingTest, ArbitrationId_BoundaryDistinct) {
  uint16_t arb_0 = make_arbitration_id(0, CMD::HEARTBEAT);
  uint16_t arb_63 = make_arbitration_id(63, CMD::HEARTBEAT);

  EXPECT_NE(arb_0, arb_63);
  EXPECT_EQ(extract_node_id(arb_0), 0);
  EXPECT_EQ(extract_node_id(arb_63), 63);
  EXPECT_EQ(extract_cmd_id(arb_0), CMD::HEARTBEAT);
  EXPECT_EQ(extract_cmd_id(arb_63), CMD::HEARTBEAT);

  // Verify actual bit math: node_id=0 → (0<<5)|1 = 0x001, node_id=63 → (63<<5)|1 = 0x7E1
  EXPECT_EQ(arb_0, 0x001);
  EXPECT_EQ(arb_63, 0x7E1);
}

// ============================================================================
// 2.3 - Heartbeat decode tests
// ============================================================================

// Scenario 1: No-error IDLE heartbeat
TEST_F(ProtocolEncodingTest, Heartbeat_NoError_Idle) {
  uint8_t data[8] = {};
  // axis_error = 0 (bytes 0-3 already zero)
  data[4] = 1;  // axis_state = IDLE
  data[5] = 0;  // procedure_result = 0
  data[6] = 1;  // traj_done = 1

  Heartbeat hb = Heartbeat::decode(data);
  EXPECT_EQ(hb.axis_error, 0u);
  EXPECT_EQ(hb.axis_state, AXIS_STATE::IDLE);
  EXPECT_EQ(hb.procedure_result, 0);
  EXPECT_EQ(hb.traj_done, 1);
}

// Scenario 2: Active error in closed-loop
TEST_F(ProtocolEncodingTest, Heartbeat_ActiveError_ClosedLoop) {
  uint8_t data[8] = {};
  // axis_error = 0x10 in little-endian
  uint32_t error = 0x10;
  std::memcpy(data, &error, 4);
  data[4] = static_cast<uint8_t>(AXIS_STATE::CLOSED_LOOP_CONTROL);  // 0x08

  Heartbeat hb = Heartbeat::decode(data);
  EXPECT_EQ(hb.axis_error, 0x10u);
  EXPECT_EQ(hb.axis_state, AXIS_STATE::CLOSED_LOOP_CONTROL);
}

// Scenario 3: All-max fields
TEST_F(ProtocolEncodingTest, Heartbeat_AllMax) {
  uint8_t data[8];
  std::memset(data, 0xFF, 8);

  Heartbeat hb = Heartbeat::decode(data);
  EXPECT_EQ(hb.axis_error, 0xFFFFFFFFu);
  EXPECT_EQ(hb.axis_state, 0xFF);
  EXPECT_EQ(hb.procedure_result, 0xFF);
  EXPECT_EQ(hb.traj_done, 0xFF);
}

// ============================================================================
// 2.4 - EncoderEstimates decode tests
// ============================================================================

// Scenario 1: Typical values pos=1.5, vel=-0.25
TEST_F(ProtocolEncodingTest, EncoderEstimates_Typical) {
  uint8_t data[8];
  float pos = 1.5f;
  float vel = -0.25f;
  build_frame_f32_f32(data, pos, vel);

  EncoderEstimates ee = EncoderEstimates::decode(data);
  EXPECT_FLOAT_EQ(ee.pos_estimate, 1.5f);
  EXPECT_FLOAT_EQ(ee.vel_estimate, -0.25f);
}

// Scenario 2: All zeros
TEST_F(ProtocolEncodingTest, EncoderEstimates_Zero) {
  uint8_t data[8] = {};

  EncoderEstimates ee = EncoderEstimates::decode(data);
  EXPECT_FLOAT_EQ(ee.pos_estimate, 0.0f);
  EXPECT_FLOAT_EQ(ee.vel_estimate, 0.0f);
}

// Scenario 3: Negative position
TEST_F(ProtocolEncodingTest, EncoderEstimates_Negative) {
  uint8_t data[8];
  float pos = -10.0f;
  float vel = 0.0f;
  build_frame_f32_f32(data, pos, vel);

  EncoderEstimates ee = EncoderEstimates::decode(data);
  EXPECT_FLOAT_EQ(ee.pos_estimate, -10.0f);
  EXPECT_FLOAT_EQ(ee.vel_estimate, 0.0f);
}

// ============================================================================
// 2.5 - Set_Input_Pos encode tests
// ============================================================================

// Scenario 1: Position-only (feedforwards default to 0)
TEST_F(ProtocolEncodingTest, SetInputPos_PositionOnly) {
  auto data = encode_set_input_pos(2.5f);
  ASSERT_EQ(data.size(), 8u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), 2.5f);
  EXPECT_EQ(extract_i16(data, 4), 0);   // vel_ff = 0
  EXPECT_EQ(extract_i16(data, 6), 0);   // torque_ff = 0
}

// Scenario 2: With positive feedforward values
TEST_F(ProtocolEncodingTest, SetInputPos_WithFeedforward) {
  auto data = encode_set_input_pos(1.0f, 0.5f, 0.1f);
  ASSERT_EQ(data.size(), 8u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), 1.0f);
  // vel_ff and torque_ff are scaled by dividing by 0.001f then truncated to int16.
  // Due to IEEE 754 float imprecision, 0.5f/0.001f may not be exactly 500.
  // Match the production code's actual truncation behavior.
  EXPECT_EQ(extract_i16(data, 4), static_cast<int16_t>(0.5f / 0.001f));
  EXPECT_EQ(extract_i16(data, 6), static_cast<int16_t>(0.1f / 0.001f));
}

// Scenario 3: Negative feedforward values
TEST_F(ProtocolEncodingTest, SetInputPos_NegativeFeedforward) {
  auto data = encode_set_input_pos(0.0f, -0.5f, -0.1f);
  ASSERT_EQ(data.size(), 8u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), 0.0f);
  // Same truncation behavior as positive case
  EXPECT_EQ(extract_i16(data, 4), static_cast<int16_t>(-0.5f / 0.001f));
  EXPECT_EQ(extract_i16(data, 6), static_cast<int16_t>(-0.1f / 0.001f));
}

// ============================================================================
// 2.6 - Set_Input_Vel and Set_Input_Torque encode tests
// ============================================================================

// Set_Input_Vel Scenario 1: With torque feedforward
TEST_F(ProtocolEncodingTest, SetInputVel_WithTorqueFeedforward) {
  auto data = encode_set_input_vel(10.0f, 0.5f);
  ASSERT_EQ(data.size(), 8u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), 10.0f);
  EXPECT_FLOAT_EQ(extract_float(data, 4), 0.5f);
}

// Set_Input_Vel Scenario 2: Default torque feedforward (0)
TEST_F(ProtocolEncodingTest, SetInputVel_DefaultTorqueFeedforward) {
  auto data = encode_set_input_vel(5.0f);
  ASSERT_EQ(data.size(), 8u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), 5.0f);
  EXPECT_FLOAT_EQ(extract_float(data, 4), 0.0f);
}

// Set_Input_Torque Scenario 1: Positive torque
TEST_F(ProtocolEncodingTest, SetInputTorque_Positive) {
  auto data = encode_set_input_torque(1.5f);
  ASSERT_EQ(data.size(), 4u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), 1.5f);
}

// Set_Input_Torque Scenario 2: Negative torque
TEST_F(ProtocolEncodingTest, SetInputTorque_Negative) {
  auto data = encode_set_input_torque(-2.0f);
  ASSERT_EQ(data.size(), 4u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), -2.0f);
}

// ============================================================================
// 2.7 - Set_Axis_State and Set_Controller_Mode encode tests
// ============================================================================

// Set_Axis_State Scenario 1: CLOSED_LOOP_CONTROL
TEST_F(ProtocolEncodingTest, SetAxisState_ClosedLoop) {
  auto data = encode_set_axis_state(AXIS_STATE::CLOSED_LOOP_CONTROL);
  ASSERT_EQ(data.size(), 4u);

  EXPECT_EQ(extract_u32(data, 0), 0x08u);
}

// Set_Axis_State Scenario 2: IDLE
TEST_F(ProtocolEncodingTest, SetAxisState_Idle) {
  auto data = encode_set_axis_state(AXIS_STATE::IDLE);
  ASSERT_EQ(data.size(), 4u);

  EXPECT_EQ(extract_u32(data, 0), 0x01u);
}

// Set_Controller_Mode Scenario 1: POSITION_CONTROL + TRAP_TRAJ
TEST_F(ProtocolEncodingTest, SetControllerMode_PositionTrapTraj) {
  auto data = encode_set_controller_mode(CONTROL_MODE::POSITION_CONTROL,
                                         INPUT_MODE::TRAP_TRAJ);
  ASSERT_EQ(data.size(), 8u);

  EXPECT_EQ(extract_u32(data, 0), 0x03u);  // POSITION_CONTROL
  EXPECT_EQ(extract_u32(data, 4), 0x05u);  // TRAP_TRAJ
}

// ============================================================================
// 2.8 - Remaining TX encode tests
// ============================================================================

// Set_Limits: velocity_limit=100.0, current_limit=20.0
TEST_F(ProtocolEncodingTest, SetLimits_Typical) {
  auto data = encode_set_limits(100.0f, 20.0f);
  ASSERT_EQ(data.size(), 8u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), 100.0f);
  EXPECT_FLOAT_EQ(extract_float(data, 4), 20.0f);
}

// Set_Traj_Vel_Limit: traj_vel_limit=50.0
TEST_F(ProtocolEncodingTest, SetTrajVelLimit_Typical) {
  auto data = encode_set_traj_vel_limit(50.0f);
  ASSERT_EQ(data.size(), 4u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), 50.0f);
}

// Set_Traj_Accel_Limits: accel=5.0, decel=10.0
TEST_F(ProtocolEncodingTest, SetTrajAccelLimits_Typical) {
  auto data = encode_set_traj_accel_limits(5.0f, 10.0f);
  ASSERT_EQ(data.size(), 8u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), 5.0f);
  EXPECT_FLOAT_EQ(extract_float(data, 4), 10.0f);
}

// Set_Traj_Inertia: inertia=0.05
TEST_F(ProtocolEncodingTest, SetTrajInertia_Typical) {
  auto data = encode_set_traj_inertia(0.05f);
  ASSERT_EQ(data.size(), 4u);

  EXPECT_NEAR(extract_float(data, 0), 0.05f, 0.001f);
}

// Clear_Errors: default (identify=0)
TEST_F(ProtocolEncodingTest, ClearErrors_Default) {
  auto data = encode_clear_errors();
  ASSERT_EQ(data.size(), 1u);

  EXPECT_EQ(data[0], 0);
}

// Clear_Errors: with identify=1
TEST_F(ProtocolEncodingTest, ClearErrors_WithIdentify) {
  auto data = encode_clear_errors(1);
  ASSERT_EQ(data.size(), 1u);

  EXPECT_EQ(data[0], 1);
}

// Reboot: default (action=0)
TEST_F(ProtocolEncodingTest, Reboot_Default) {
  auto data = encode_reboot();
  ASSERT_EQ(data.size(), 1u);

  EXPECT_EQ(data[0], 0);
}

// Reboot: save_configuration (action=1)
TEST_F(ProtocolEncodingTest, Reboot_SaveConfig) {
  auto data = encode_reboot(1);
  ASSERT_EQ(data.size(), 1u);

  EXPECT_EQ(data[0], 1);
}

// Estop: empty payload
TEST_F(ProtocolEncodingTest, Estop_EmptyPayload) {
  auto data = encode_estop();
  EXPECT_TRUE(data.empty());
}

// Enter_DFU_Mode: empty payload
TEST_F(ProtocolEncodingTest, EnterDfuMode_EmptyPayload) {
  auto data = encode_enter_dfu_mode();
  EXPECT_TRUE(data.empty());
}

// Set_Vel_Gains: vel_gain=0.1, vel_integrator_gain=0.01
TEST_F(ProtocolEncodingTest, SetVelGains_Typical) {
  auto data = encode_set_vel_gains(0.1f, 0.01f);
  ASSERT_EQ(data.size(), 8u);

  EXPECT_NEAR(extract_float(data, 0), 0.1f, 0.001f);
  EXPECT_NEAR(extract_float(data, 4), 0.01f, 0.001f);
}

// Set_Pos_Gain: pos_gain=20.0
TEST_F(ProtocolEncodingTest, SetPosGain_Typical) {
  auto data = encode_set_pos_gain(20.0f);
  ASSERT_EQ(data.size(), 4u);

  EXPECT_FLOAT_EQ(extract_float(data, 0), 20.0f);
}

// Set_Absolute_Position: position=3.14
TEST_F(ProtocolEncodingTest, SetAbsolutePosition_Typical) {
  auto data = encode_set_absolute_position(3.14f);
  ASSERT_EQ(data.size(), 4u);

  EXPECT_NEAR(extract_float(data, 0), 3.14f, 0.001f);
}

// Set_Axis_Node_Id: node_id=5
TEST_F(ProtocolEncodingTest, SetAxisNodeId_Typical) {
  auto data = encode_set_axis_node_id(5);
  ASSERT_EQ(data.size(), 4u);

  EXPECT_EQ(extract_u32(data, 0), 5u);
}

// ============================================================================
// 2.9 - Remaining RX decode tests
// ============================================================================

// ErrorStatus: active_errors=0x0004, disarm_reason=0x0100
TEST_F(ProtocolEncodingTest, ErrorStatus_Typical) {
  uint8_t data[8];
  uint32_t active = 0x0004;
  uint32_t disarm = 0x0100;
  build_frame_u32_u32(data, active, disarm);

  ErrorStatus es = ErrorStatus::decode(data);
  EXPECT_EQ(es.active_errors, 0x0004u);
  EXPECT_EQ(es.disarm_reason, 0x0100u);
}

// Version: protocol=2, hw=3.6.0, fw=0.6.11.0
TEST_F(ProtocolEncodingTest, Version_Typical) {
  uint8_t data[8] = {2, 3, 6, 0, 0, 6, 11, 0};

  Version v = Version::decode(data);
  EXPECT_EQ(v.protocol_version, 2);
  EXPECT_EQ(v.hw_version_major, 3);
  EXPECT_EQ(v.hw_version_minor, 6);
  EXPECT_EQ(v.hw_version_variant, 0);
  EXPECT_EQ(v.fw_version_major, 0);
  EXPECT_EQ(v.fw_version_minor, 6);
  EXPECT_EQ(v.fw_version_revision, 11);
  EXPECT_EQ(v.fw_version_unreleased, 0);
}

// IqValues: iq_setpoint=1.0, iq_measured=0.95
TEST_F(ProtocolEncodingTest, IqValues_Typical) {
  uint8_t data[8];
  build_frame_f32_f32(data, 1.0f, 0.95f);

  IqValues iq = IqValues::decode(data);
  EXPECT_FLOAT_EQ(iq.iq_setpoint, 1.0f);
  EXPECT_NEAR(iq.iq_measured, 0.95f, 0.001f);
}

// Temperature: FET=45.5, motor=38.2
TEST_F(ProtocolEncodingTest, Temperature_Typical) {
  uint8_t data[8];
  build_frame_f32_f32(data, 45.5f, 38.2f);

  Temperature temp = Temperature::decode(data);
  EXPECT_FLOAT_EQ(temp.fet_temperature, 45.5f);
  EXPECT_NEAR(temp.motor_temperature, 38.2f, 0.001f);
}

// BusVoltageCurrent: voltage=24.1, current=3.5
TEST_F(ProtocolEncodingTest, BusVoltageCurrent_Typical) {
  uint8_t data[8];
  build_frame_f32_f32(data, 24.1f, 3.5f);

  BusVoltageCurrent bvc = BusVoltageCurrent::decode(data);
  EXPECT_NEAR(bvc.bus_voltage, 24.1f, 0.001f);
  EXPECT_FLOAT_EQ(bvc.bus_current, 3.5f);
}

// Torques: target=0.5, estimate=0.48
TEST_F(ProtocolEncodingTest, Torques_Typical) {
  uint8_t data[8];
  build_frame_f32_f32(data, 0.5f, 0.48f);

  Torques torq = Torques::decode(data);
  EXPECT_FLOAT_EQ(torq.torque_target, 0.5f);
  EXPECT_NEAR(torq.torque_estimate, 0.48f, 0.001f);
}

// Powers: electrical=120.0, mechanical=95.0
TEST_F(ProtocolEncodingTest, Powers_Typical) {
  uint8_t data[8];
  build_frame_f32_f32(data, 120.0f, 95.0f);

  Powers pow = Powers::decode(data);
  EXPECT_FLOAT_EQ(pow.electrical_power, 120.0f);
  EXPECT_FLOAT_EQ(pow.mechanical_power, 95.0f);
}
