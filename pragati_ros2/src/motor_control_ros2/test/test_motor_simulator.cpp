/*
 * Copyright (c) 2025 Pragati Robotics
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

/*
 * Motor Physics Simulator Integration Tests (Tasks 4.1 - 4.7)
 *
 * Validates the MotorPhysicsSimulator through the ConfigurableMockCANInterface
 * public API. Covers position dynamics, thermal model, frame byte layouts,
 * backward compatibility, fault injection, composite faults, and latency
 * simulation.
 */

#include <gtest/gtest.h>
#include "motor_control_ros2/simulation/mock_can_interface.hpp"
#include "motor_control_ros2/mg6010_protocol.hpp"
#include <chrono>
#include <cmath>

using namespace motor_control_ros2::test;
using P = motor_control_ros2::MG6010Protocol;

// =============================================================================
// TEST FIXTURE
// =============================================================================

class MotorSimulatorTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    mock_ = std::make_shared<ConfigurableMockCANInterface>();
    mock_->initialize("vcan0");
    MotorSimConfig config;
    config.settling_time_constant_ms = 200.0;
    config.velocity_max_dps = 360.0;
    config.position_min_deg = -3600.0;
    config.position_max_deg = 3600.0;
    config.thermal_time_constant_s = 60.0;
    config.thermal_gain = 0.001;
    config.ambient_temperature_c = 25.0;
    config.over_temp_threshold_c = 85.0;
    mock_->enable_motor_simulation(1, config);
  }

  std::shared_ptr<ConfigurableMockCANInterface> mock_;
  static constexpr uint32_t MOTOR1_ID = P::BASE_ARBITRATION_ID + 1;  // 0x141

  // Helper: send a command and receive the response
  bool sendAndReceive(uint32_t arb_id, const std::vector<uint8_t> & cmd,
                      uint32_t & resp_id, std::vector<uint8_t> & resp_data)
  {
    if (!mock_->send_message(arb_id, cmd)) {
      return false;
    }
    return mock_->receive_message(resp_id, resp_data);
  }

  // Helper: build a multi-loop angle 2 command (0xA4) targeting degrees
  std::vector<uint8_t> makePositionCmd(double target_deg)
  {
    std::vector<uint8_t> frame(8, 0);
    frame[0] = P::CMD_MULTI_LOOP_ANGLE_2;
    // Bytes 2-3: max speed (uint16 LE, 1 dps/LSB) - use 360 dps
    uint16_t speed = 360;
    frame[2] = static_cast<uint8_t>(speed & 0xFF);
    frame[3] = static_cast<uint8_t>((speed >> 8) & 0xFF);
    // Bytes 4-7: angle in centidegrees (int32 LE)
    int32_t centideg = static_cast<int32_t>(target_deg * 100.0);
    frame[4] = static_cast<uint8_t>(centideg & 0xFF);
    frame[5] = static_cast<uint8_t>((centideg >> 8) & 0xFF);
    frame[6] = static_cast<uint8_t>((centideg >> 16) & 0xFF);
    frame[7] = static_cast<uint8_t>((centideg >> 24) & 0xFF);
    return frame;
  }

  // Helper: build a read status command
  std::vector<uint8_t> makeReadCmd(uint8_t cmd_byte)
  {
    std::vector<uint8_t> frame(8, 0);
    frame[0] = cmd_byte;
    return frame;
  }

  // Helper: build a torque command (0xA1)
  std::vector<uint8_t> makeTorqueCmd(double amps)
  {
    std::vector<uint8_t> frame(8, 0);
    frame[0] = P::CMD_TORQUE_CLOSED_LOOP;
    int16_t raw = static_cast<int16_t>(amps * (2048.0 / 33.0));
    frame[4] = static_cast<uint8_t>(raw & 0xFF);
    frame[5] = static_cast<uint8_t>((raw >> 8) & 0xFF);
    return frame;
  }

  // Helper: decode int16 LE from response data
  int16_t decodeInt16LE(const std::vector<uint8_t> & data, size_t offset)
  {
    uint16_t raw = static_cast<uint16_t>(data[offset]) |
                   (static_cast<uint16_t>(data[offset + 1]) << 8);
    return static_cast<int16_t>(raw);
  }

  // Helper: decode uint16 LE
  uint16_t decodeUint16LE(const std::vector<uint8_t> & data, size_t offset)
  {
    return static_cast<uint16_t>(data[offset]) |
           (static_cast<uint16_t>(data[offset + 1]) << 8);
  }

  // Helper: decode int64 LE 7-byte (sign-extended from bit 55)
  int64_t decodeInt64LE7(const std::vector<uint8_t> & data, size_t offset)
  {
    int64_t val = 0;
    for (int i = 0; i < 7; ++i) {
      val |= static_cast<int64_t>(data[offset + i]) << (8 * i);
    }
    if (val & (static_cast<int64_t>(1) << 55)) {
      val |= static_cast<int64_t>(0xFF) << 56;
    }
    return val;
  }
};

// =============================================================================
// Task 4.1: Position Dynamics
// =============================================================================

TEST_F(MotorSimulatorTest, PositionConvergesToTarget)
{
  // Send position command to 90 degrees
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(90.0), resp_id, resp));

  // Advance time by 1000ms (5x time constant of 200ms)
  mock_->advance_time(std::chrono::milliseconds(1000));

  // Read multi-turn angle to get position
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_MULTI_TURN_ANGLE),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  int64_t centideg = decodeInt64LE7(resp, 1);
  double position_deg = centideg / 100.0;

  // After 5 time constants, expect ~99.3% convergence.
  // Position should be within 5% of 90 degrees (tolerance = 4.5 deg).
  EXPECT_NEAR(position_deg, 90.0, 90.0 * 0.05)
      << "Position should be within 5% of 90 degrees after 5 time constants";

  // Also verify velocity is non-zero during motion: read STATUS_2 mid-motion
  // Reset and re-test with a fresh read during motion
  mock_ = std::make_shared<ConfigurableMockCANInterface>();
  mock_->initialize("vcan0");
  MotorSimConfig config;
  config.settling_time_constant_ms = 200.0;
  config.velocity_max_dps = 360.0;
  mock_->enable_motor_simulation(1, config);

  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(90.0), resp_id, resp));
  // Advance only a small amount so motor is still in motion
  mock_->advance_time(std::chrono::milliseconds(100));

  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  int16_t speed = decodeInt16LE(resp, 4);
  EXPECT_NE(speed, 0) << "Velocity should be non-zero during motion";
}

TEST_F(MotorSimulatorTest, PositionSettlesAfterSufficientTime)
{
  // Send position command to 90 degrees
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(90.0), resp_id, resp));

  // Advance time by 2000ms (10x time constant) -- should be fully settled
  mock_->advance_time(std::chrono::milliseconds(2000));

  // Read multi-turn angle
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_MULTI_TURN_ANGLE),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  int64_t centideg = decodeInt64LE7(resp, 1);
  double position_deg = centideg / 100.0;

  // After 10 time constants, position should be within 0.1 degrees of target
  EXPECT_NEAR(position_deg, 90.0, 0.1)
      << "Position should settle to within 0.1 degrees after 10 time constants";
}

TEST_F(MotorSimulatorTest, VelocityLimitEnforced)
{
  // Create a fresh mock with a low velocity limit
  mock_ = std::make_shared<ConfigurableMockCANInterface>();
  mock_->initialize("vcan0");
  MotorSimConfig config;
  config.settling_time_constant_ms = 200.0;
  config.velocity_max_dps = 100.0;
  config.position_min_deg = -3600.0;
  config.position_max_deg = 3600.0;
  mock_->enable_motor_simulation(1, config);

  // Send position command 180 degrees away
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(180.0), resp_id, resp));

  // Advance a small step
  mock_->advance_time(std::chrono::milliseconds(50));

  // Read STATUS_2 to get speed
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  int16_t speed = decodeInt16LE(resp, 4);
  double speed_dps = static_cast<double>(speed);

  EXPECT_LE(std::abs(speed_dps), 100.0)
      << "Speed should not exceed velocity_max_dps of 100 dps";
}

TEST_F(MotorSimulatorTest, PositionLimitsEnforced)
{
  // Default config has position_max_deg = 3600
  // Send position command beyond the limit
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(5000.0), resp_id, resp));

  // Advance time well past settling. At 360 dps velocity limit,
  // reaching 3600 deg takes 10s. Allow 15s for the exponential to fully settle.
  mock_->advance_time(std::chrono::milliseconds(15000));

  // Read multi-turn angle
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_MULTI_TURN_ANGLE),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  int64_t centideg = decodeInt64LE7(resp, 1);
  double position_deg = centideg / 100.0;

  EXPECT_LE(position_deg, 3600.0)
      << "Position should be clamped at position_max_deg (3600)";
  EXPECT_NEAR(position_deg, 3600.0, 1.0)
      << "Position should have converged to the clamped limit";
}

// =============================================================================
// Task 4.2: Thermal Model
// =============================================================================

TEST_F(MotorSimulatorTest, TemperatureRisesUnderLoad)
{
  // Send torque command with significant current (15A)
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeTorqueCmd(15.0), resp_id, resp));

  // Advance time by 30 seconds in 1-second steps
  for (int i = 0; i < 30; ++i) {
    mock_->advance_time(std::chrono::milliseconds(1000));
  }

  // Read STATUS_2 to get temperature byte
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  int8_t temp = static_cast<int8_t>(resp[1]);

  EXPECT_GT(temp, 25) << "Temperature should rise above ambient (25C) under load";
}

TEST_F(MotorSimulatorTest, TemperatureDecreasesWhenIdle)
{
  // Apply torque for 30 seconds to heat up
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeTorqueCmd(15.0), resp_id, resp));

  for (int i = 0; i < 30; ++i) {
    mock_->advance_time(std::chrono::milliseconds(1000));
  }

  // Read peak temperature
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  int8_t peak_temp = static_cast<int8_t>(resp[1]);
  ASSERT_GT(peak_temp, 25) << "Precondition: motor should be heated above ambient";

  // Send motor off (0x80) to remove load
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_MOTOR_OFF), resp_id, resp));

  // Advance time by 60 more seconds for cooling
  for (int i = 0; i < 60; ++i) {
    mock_->advance_time(std::chrono::milliseconds(1000));
  }

  // Read temperature after cooling
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  int8_t cooled_temp = static_cast<int8_t>(resp[1]);

  EXPECT_LT(cooled_temp, peak_temp)
      << "Temperature should decrease after removing load";
}

// =============================================================================
// Task 4.3: Frame Byte Layouts
// =============================================================================

TEST_F(MotorSimulatorTest, Status1FrameLayout)
{
  // Read STATUS_1
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_1),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);

  // Byte 0: command echo
  EXPECT_EQ(resp[0], P::CMD_READ_STATUS_1)
      << "Byte 0 should echo the STATUS_1 command (0x9A)";

  // Byte 1: temperature (int8, should be ~25C at ambient)
  int8_t temp = static_cast<int8_t>(resp[1]);
  EXPECT_EQ(temp, 25) << "Initial temperature should be 25C (ambient)";

  // Bytes 2-3: voltage (uint16 LE, 240 = 24.0V at 0.1V/LSB)
  uint16_t voltage = decodeUint16LE(resp, 2);
  EXPECT_EQ(voltage, 240u) << "Voltage should be 240 (24.0V)";

  // Byte 7: error flags (0 initially)
  EXPECT_EQ(resp[7], 0u) << "Error flags should be 0 initially";
}

TEST_F(MotorSimulatorTest, Status2FrameLayout)
{
  // Send a position command so motor has state, then advance time
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(45.0), resp_id, resp));
  mock_->advance_time(std::chrono::milliseconds(100));

  // Read STATUS_2
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);

  // Byte 0: command echo (0x9C)
  EXPECT_EQ(resp[0], P::CMD_READ_STATUS_2)
      << "Byte 0 should echo the STATUS_2 command (0x9C)";

  // Byte 1: temperature (int8)
  int8_t temp = static_cast<int8_t>(resp[1]);
  EXPECT_GE(temp, 24) << "Temperature should be near ambient";
  EXPECT_LE(temp, 30) << "Temperature should be near ambient";

  // Bytes 2-3: iq (int16 LE, torque current)
  int16_t iq = decodeInt16LE(resp, 2);
  (void)iq;  // Value depends on state; just verify decode doesn't crash

  // Bytes 4-5: speed (int16 LE, 1 dps/LSB)
  int16_t speed = decodeInt16LE(resp, 4);
  (void)speed;  // Non-zero during motion; verified in dynamics tests

  // Bytes 6-7: encoder (uint16 LE)
  uint16_t encoder = decodeUint16LE(resp, 6);
  (void)encoder;  // Position-dependent; verified by consistency with angle
}

TEST_F(MotorSimulatorTest, Status3FrameLayout)
{
  // Send torque command to generate phase currents
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeTorqueCmd(10.0), resp_id, resp));

  // Read STATUS_3
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_3),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);

  // Byte 0: command echo (0x9D)
  EXPECT_EQ(resp[0], P::CMD_READ_STATUS_3)
      << "Byte 0 should echo the STATUS_3 command (0x9D)";

  // Bytes 2-3: phase A current (int16 LE, 1A/64 LSB)
  int16_t phase_a_raw = decodeInt16LE(resp, 2);
  double phase_a_amps = phase_a_raw / 64.0;
  // With 10A torque current, phase A should reflect that
  EXPECT_NEAR(phase_a_amps, 10.0, 1.0)
      << "Phase A current should approximately match the torque current";
}

TEST_F(MotorSimulatorTest, MultiTurnAngleFrameLayout)
{
  // Send position to 450 degrees and let it settle
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(450.0), resp_id, resp));
  mock_->advance_time(std::chrono::milliseconds(3000));

  // Read multi-turn angle (0x92)
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_MULTI_TURN_ANGLE),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);

  // Byte 0: command echo
  EXPECT_EQ(resp[0], P::CMD_READ_MULTI_TURN_ANGLE);

  // Decode 7-byte int64 LE from bytes 1-7
  int64_t centideg = decodeInt64LE7(resp, 1);
  // 450 degrees = 45000 centidegrees
  EXPECT_NEAR(static_cast<double>(centideg), 45000.0, 50.0)
      << "Multi-turn angle should be approximately 45000 centidegrees (450 deg)";
}

// =============================================================================
// Task 4.4: Backward Compatibility
// =============================================================================

TEST_F(MotorSimulatorTest, StaticResponsesWorkWithoutSimulation)
{
  // Create a new mock with NO simulation enabled
  auto plain_mock = std::make_shared<ConfigurableMockCANInterface>();
  plain_mock->initialize("vcan0");

  // Configure a static response for motor_id 2 (arb_id 0x142)
  uint32_t motor2_id = P::BASE_ARBITRATION_ID + 2;
  std::vector<uint8_t> static_resp = {0x9C, 25, 0, 0, 0, 0, 0, 0};
  plain_mock->configure_response(motor2_id, motor2_id, static_resp);

  // Send message to motor 2
  ASSERT_TRUE(plain_mock->send_message(motor2_id, makeReadCmd(P::CMD_READ_STATUS_2)));

  // Receive and verify the static response is returned unchanged
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(plain_mock->receive_message(resp_id, resp));
  EXPECT_EQ(resp_id, motor2_id);
  EXPECT_EQ(resp, static_resp)
      << "Static response should be returned unchanged when simulation is not enabled";
}

TEST_F(MotorSimulatorTest, SimulatorOverridesStaticResponse)
{
  // Configure a static response for motor_id 1 (0x141)
  std::vector<uint8_t> static_resp = {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x11, 0x22};
  mock_->configure_response(MOTOR1_ID, MOTOR1_ID, static_resp);

  // Motor 1 already has simulation enabled (from SetUp).
  // Send a STATUS_2 read command.
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);

  // Verify the response came from the simulator, not the static map
  EXPECT_EQ(resp[0], P::CMD_READ_STATUS_2)
      << "Response byte 0 should be 0x9C from simulator, not 0xAA from static";
  EXPECT_NE(resp, static_resp)
      << "Simulator response should override the static response";
}

// =============================================================================
// Task 4.5: Fault Injection
// =============================================================================

TEST_F(MotorSimulatorTest, StallFaultStopsMotion)
{
  // Send position command to 90 degrees
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(90.0), resp_id, resp));

  // Inject stall fault BEFORE advancing time
  mock_->inject_fault(1, FaultType::STALL);

  // Advance time by 500ms
  mock_->advance_time(std::chrono::milliseconds(500));

  // Read STATUS_2
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);

  // Verify speed = 0
  int16_t speed = decodeInt16LE(resp, 4);
  EXPECT_EQ(speed, 0) << "Speed should be 0 when motor is stalled";

  // Read multi-turn angle -- position should still be near 0
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_MULTI_TURN_ANGLE),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  int64_t centideg = decodeInt64LE7(resp, 1);
  double position_deg = centideg / 100.0;
  EXPECT_NEAR(position_deg, 0.0, 1.0)
      << "Position should not move when stalled";
}

TEST_F(MotorSimulatorTest, StallFaultClearsAndResumes)
{
  // Inject stall, command position, advance time -- verify stuck
  mock_->inject_fault(1, FaultType::STALL);

  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(90.0), resp_id, resp));
  mock_->advance_time(std::chrono::milliseconds(500));

  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_MULTI_TURN_ANGLE),
                             resp_id, resp));
  int64_t centideg_stalled = decodeInt64LE7(resp, 1);
  double pos_stalled = centideg_stalled / 100.0;
  ASSERT_NEAR(pos_stalled, 0.0, 1.0) << "Precondition: motor should be stuck";

  // Clear stall fault
  mock_->clear_fault(1, FaultType::STALL);

  // Advance time by 500ms more
  mock_->advance_time(std::chrono::milliseconds(500));

  // Verify position has started moving
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_MULTI_TURN_ANGLE),
                             resp_id, resp));
  int64_t centideg_after = decodeInt64LE7(resp, 1);
  double pos_after = centideg_after / 100.0;
  EXPECT_GT(pos_after, 1.0)
      << "Position should have moved after clearing stall fault";
}

TEST_F(MotorSimulatorTest, CanTimeoutNoResponse)
{
  // Inject CAN_TIMEOUT fault with drop rate 1.0 (always drop)
  FaultConfig fc;
  fc.timeout_drop_rate = 1.0;
  mock_->inject_fault(1, FaultType::CAN_TIMEOUT, fc);

  // Send STATUS_2 read command
  ASSERT_TRUE(mock_->send_message(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2)));

  // Attempt receive_message -- should fail (no response queued)
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  EXPECT_FALSE(mock_->receive_message(resp_id, resp))
      << "receive_message should return false when CAN_TIMEOUT drops all frames";
}

TEST_F(MotorSimulatorTest, CanTimeoutIntermittent)
{
  // Inject CAN_TIMEOUT with 50% drop rate
  FaultConfig fc;
  fc.timeout_drop_rate = 0.5;
  mock_->inject_fault(1, FaultType::CAN_TIMEOUT, fc);

  int response_count = 0;
  const int total_requests = 100;

  for (int i = 0; i < total_requests; ++i) {
    ASSERT_TRUE(mock_->send_message(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2)));
    uint32_t resp_id = 0;
    std::vector<uint8_t> resp;
    if (mock_->receive_message(resp_id, resp)) {
      response_count++;
    }
  }

  // With 50% drop rate and deterministic seed, expect roughly 40-60 responses
  EXPECT_GE(response_count, 30)
      << "Should receive at least ~30% of messages with 50% drop rate";
  EXPECT_LE(response_count, 70)
      << "Should not receive more than ~70% of messages with 50% drop rate";
}

TEST_F(MotorSimulatorTest, EncoderDriftFault)
{
  // Send position command to 90 degrees and let it settle
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(90.0), resp_id, resp));
  mock_->advance_time(std::chrono::milliseconds(3000));

  // Inject ENCODER_DRIFT with 5.0 degree offset
  FaultConfig fc;
  fc.encoder_drift_deg = 5.0;
  mock_->inject_fault(1, FaultType::ENCODER_DRIFT, fc);

  // Read encoder (0x90) -- should include drift offset
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_ENCODER),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  uint16_t enc_value = decodeUint16LE(resp, 2);
  // 90 + 5 = 95 degrees. Encoder maps 0-360 to 0-65535.
  double enc_deg = (static_cast<double>(enc_value) / 65535.0) * 360.0;
  EXPECT_NEAR(enc_deg, 95.0, 2.0)
      << "Encoder should report ~95 degrees (90 true + 5 drift)";

  // Read multi-turn angle (0x92) -- should report true position without drift
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_MULTI_TURN_ANGLE),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);
  int64_t centideg = decodeInt64LE7(resp, 1);
  double true_deg = centideg / 100.0;
  EXPECT_NEAR(true_deg, 90.0, 0.5)
      << "Multi-turn angle should report true position (~90 deg) without drift";
}

// =============================================================================
// Task 4.6: Composite Faults
// =============================================================================

TEST_F(MotorSimulatorTest, StallPlusOverTemp)
{
  // Inject both STALL and OVER_TEMPERATURE faults
  mock_->inject_fault(1, FaultType::STALL);
  mock_->inject_fault(1, FaultType::OVER_TEMPERATURE);

  // Send position command
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makePositionCmd(90.0), resp_id, resp));

  // Advance time for effects to manifest
  mock_->advance_time(std::chrono::milliseconds(500));

  // Read STATUS_1: verify error_flags and temperature
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_1),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);

  uint8_t error_flags = resp[7];
  EXPECT_NE(error_flags & P::ERROR_TEMPERATURE, 0u)
      << "Error flags should have temperature bit (0x08) set";

  int8_t temp_s1 = static_cast<int8_t>(resp[1]);
  EXPECT_GE(temp_s1, 85)
      << "Temperature should be at or above over_temp_threshold (85C)";

  // Read STATUS_2: verify speed = 0 (stall) and temperature >= 85
  ASSERT_TRUE(sendAndReceive(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2),
                             resp_id, resp));
  ASSERT_EQ(resp.size(), 8u);

  int16_t speed = decodeInt16LE(resp, 4);
  EXPECT_EQ(speed, 0) << "Speed should be 0 due to stall fault";

  int8_t temp_s2 = static_cast<int8_t>(resp[1]);
  EXPECT_GE(temp_s2, 85)
      << "Temperature in STATUS_2 should be >= 85C due to over-temperature fault";
}

// =============================================================================
// Task 4.7: Latency Simulation
// =============================================================================

TEST_F(MotorSimulatorTest, ResponseDelayedByLatency)
{
  // Create a fresh mock with response latency configured
  mock_ = std::make_shared<ConfigurableMockCANInterface>();
  mock_->initialize("vcan0");
  MotorSimConfig config;
  config.settling_time_constant_ms = 200.0;
  config.velocity_max_dps = 360.0;
  config.response_latency_ms = 5.0;
  mock_->enable_motor_simulation(1, config);

  // Send a STATUS_2 read command
  ASSERT_TRUE(mock_->send_message(MOTOR1_ID, makeReadCmd(P::CMD_READ_STATUS_2)));

  // Attempt receive immediately -- should fail (latency not yet elapsed)
  uint32_t resp_id = 0;
  std::vector<uint8_t> resp;
  EXPECT_FALSE(mock_->receive_message(resp_id, resp))
      << "Response should not be available immediately with 5ms latency";

  // Advance time by 3ms -- still not enough
  mock_->advance_time(std::chrono::milliseconds(3));
  EXPECT_FALSE(mock_->receive_message(resp_id, resp))
      << "Response should not be available after only 3ms with 5ms latency";

  // Advance time by 3ms more (total 6ms > 5ms) -- now response should be available
  mock_->advance_time(std::chrono::milliseconds(3));
  ASSERT_TRUE(mock_->receive_message(resp_id, resp))
      << "Response should be available after 6ms (> 5ms latency)";

  // Verify the response is correct
  ASSERT_EQ(resp.size(), 8u);
  EXPECT_EQ(resp[0], P::CMD_READ_STATUS_2)
      << "Delayed response should still have correct command echo";
  EXPECT_EQ(resp_id, MOTOR1_ID)
      << "Delayed response should have correct arbitration ID";
}
