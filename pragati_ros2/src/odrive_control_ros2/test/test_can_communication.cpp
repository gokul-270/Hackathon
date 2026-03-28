// Copyright 2025 Pragati Robotics
// CAN Driver Communication Behavioral Tests (Phase-1 Tasks 3.1-3.7)
//
// Tests ODriveCanDriver behavior through a mock SocketCAN interface.
// Covers: motor registration, TX commands, RTR requests, RX frame handling,
//         state accumulation, and snapshot thread-safety.
// No ROS2 dependencies, no hardware dependencies.

#include <gtest/gtest.h>
#include <gmock/gmock.h>

#include <chrono>
#include <cstdint>
#include <cstring>
#include <memory>
#include <optional>
#include <vector>

#include "odrive_control_ros2/odrive_can_driver.hpp"
#include "odrive_control_ros2/odrive_cansimple_protocol.hpp"

using namespace odrive_cansimple;
using ::testing::_;
using ::testing::Return;

// ============================================================================
// 3.1 - MockSocketCANInterface
// ============================================================================

class MockSocketCANInterface : public odrive_cansimple::SocketCANInterface {
public:
  MOCK_METHOD(bool, send_frame,
              (uint16_t arb_id, const std::vector<uint8_t>& data, bool is_rtr),
              (override));
  MOCK_METHOD(bool, receive_frame,
              (uint16_t& arb_id, std::vector<uint8_t>& data, int timeout_ms),
              (override));
};

// ============================================================================
// Test Fixture
// ============================================================================

class CANCommunicationTest : public ::testing::Test {
protected:
  void SetUp() override {
    mock_can_ = std::make_shared<MockSocketCANInterface>();
    driver_ = std::make_unique<odrive_can::ODriveCanDriver>(mock_can_);

    // Default: send_frame succeeds unless overridden
    ON_CALL(*mock_can_, send_frame(_, _, _)).WillByDefault(Return(true));
  }

  std::shared_ptr<MockSocketCANInterface> mock_can_;
  std::unique_ptr<odrive_can::ODriveCanDriver> driver_;

  // ---- Helpers for building RX test frames ----

  /// Build 8-byte frame from two float values (little-endian)
  static std::vector<uint8_t> make_two_float_frame(float a, float b) {
    std::vector<uint8_t> data(8);
    std::memcpy(data.data(), &a, 4);
    std::memcpy(data.data() + 4, &b, 4);
    return data;
  }

  /// Build heartbeat frame: axis_error(u32) | axis_state(u8) | procedure_result(u8) | traj_done(u8) | reserved(u8)
  static std::vector<uint8_t> make_heartbeat_frame(
      uint32_t axis_error, uint8_t axis_state,
      uint8_t procedure_result = 0, uint8_t traj_done = 0) {
    std::vector<uint8_t> data(8, 0);
    std::memcpy(data.data(), &axis_error, 4);
    data[4] = axis_state;
    data[5] = procedure_result;
    data[6] = traj_done;
    data[7] = 0;  // reserved
    return data;
  }

  /// Build error status frame: active_errors(u32) | disarm_reason(u32)
  static std::vector<uint8_t> make_error_status_frame(
      uint32_t active_errors, uint32_t disarm_reason) {
    std::vector<uint8_t> data(8);
    std::memcpy(data.data(), &active_errors, 4);
    std::memcpy(data.data() + 4, &disarm_reason, 4);
    return data;
  }

  /// Build version frame: 8 individual bytes
  static std::vector<uint8_t> make_version_frame(
      uint8_t proto, uint8_t hw_major, uint8_t hw_minor, uint8_t hw_variant,
      uint8_t fw_major, uint8_t fw_minor, uint8_t fw_rev, uint8_t fw_unreleased) {
    return {proto, hw_major, hw_minor, hw_variant,
            fw_major, fw_minor, fw_rev, fw_unreleased};
  }

  /// Build temperature frame: fet_temp(f32) | motor_temp(f32)
  static std::vector<uint8_t> make_temperature_frame(float fet, float motor) {
    return make_two_float_frame(fet, motor);
  }

  /// Extract float from byte vector at offset
  static float extract_float(const std::vector<uint8_t>& data, size_t offset) {
    float val;
    std::memcpy(&val, data.data() + offset, 4);
    return val;
  }

  /// Extract uint32_t from byte vector at offset
  static uint32_t extract_u32(const std::vector<uint8_t>& data, size_t offset) {
    uint32_t val;
    std::memcpy(&val, data.data() + offset, 4);
    return val;
  }
};

// ============================================================================
// 3.2 - Motor Registration Tests
// ============================================================================

TEST_F(CANCommunicationTest, AddMotor_SingleMotor_IsRegistered) {
  driver_->addMotor(3);
  EXPECT_TRUE(driver_->hasMotor(3));
  EXPECT_FALSE(driver_->hasMotor(4));
}

TEST_F(CANCommunicationTest, AddMotor_MultipleMotors_AllRegistered) {
  driver_->addMotor(1);
  driver_->addMotor(2);
  driver_->addMotor(3);
  EXPECT_TRUE(driver_->hasMotor(1));
  EXPECT_TRUE(driver_->hasMotor(2));
  EXPECT_TRUE(driver_->hasMotor(3));
}

TEST_F(CANCommunicationTest, AddMotor_DuplicateRegistration_NoError) {
  driver_->addMotor(5);
  driver_->addMotor(5);  // duplicate — should not throw or corrupt state
  EXPECT_TRUE(driver_->hasMotor(5));

  // Verify state is still accessible and sane
  auto snapshot = driver_->getMotorStateSnapshot(5);
  ASSERT_TRUE(snapshot.has_value());
  EXPECT_EQ(snapshot->node_id, 5);
}

// ============================================================================
// 3.3 - TX Command Tests
// ============================================================================

TEST_F(CANCommunicationTest, TxEstop_CorrectArbIdAndEmptyPayload) {
  // arb_id = (3 << 5) | 0x02 = 0x62
  EXPECT_CALL(*mock_can_, send_frame(0x62, std::vector<uint8_t>{}, false))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->estop(3));
}

TEST_F(CANCommunicationTest, TxSetAxisState_CorrectArbIdAndPayload) {
  // arb_id = (3 << 5) | 0x07 = 0x67
  auto expected_data = encode_set_axis_state(AXIS_STATE::CLOSED_LOOP_CONTROL);
  EXPECT_CALL(*mock_can_, send_frame(0x67, expected_data, false))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->setAxisState(3, AXIS_STATE::CLOSED_LOOP_CONTROL));
}

TEST_F(CANCommunicationTest, TxSetInputPos_CorrectArbIdAndPayload) {
  // arb_id = (3 << 5) | 0x0C = 0x6C
  auto expected_data = encode_set_input_pos(2.5f, 0.5f, 0.1f);
  EXPECT_CALL(*mock_can_, send_frame(0x6C, expected_data, false))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->setInputPos(3, 2.5f, 0.5f, 0.1f));
}

TEST_F(CANCommunicationTest, TxSetInputVel_CorrectArbIdAndPayload) {
  // arb_id = (3 << 5) | 0x0D = 0x6D
  auto expected_data = encode_set_input_vel(10.0f, 0.5f);
  EXPECT_CALL(*mock_can_, send_frame(0x6D, expected_data, false))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->setInputVel(3, 10.0f, 0.5f));
}

TEST_F(CANCommunicationTest, TxSetInputTorque_CorrectArbIdAndPayload) {
  // arb_id = (3 << 5) | 0x0E = 0x6E
  auto expected_data = encode_set_input_torque(1.5f);
  EXPECT_CALL(*mock_can_, send_frame(0x6E, expected_data, false))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->setInputTorque(3, 1.5f));
}

TEST_F(CANCommunicationTest, TxSetControllerMode_CorrectArbIdAndPayload) {
  // arb_id = (3 << 5) | 0x0B = 0x6B
  auto expected_data = encode_set_controller_mode(
      CONTROL_MODE::POSITION_CONTROL, INPUT_MODE::TRAP_TRAJ);
  EXPECT_CALL(*mock_can_, send_frame(0x6B, expected_data, false))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->setControllerMode(
      3, CONTROL_MODE::POSITION_CONTROL, INPUT_MODE::TRAP_TRAJ));
}

TEST_F(CANCommunicationTest, TxClearErrors_CorrectArbIdAndPayload) {
  // arb_id = (3 << 5) | 0x18 = 0x78
  auto expected_data = encode_clear_errors(1);
  EXPECT_CALL(*mock_can_, send_frame(0x78, expected_data, false))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->clearErrors(3, 1));
}

TEST_F(CANCommunicationTest, TxReboot_CorrectArbIdAndPayload) {
  // arb_id = (3 << 5) | 0x16 = 0x76
  auto expected_data = encode_reboot(0);
  EXPECT_CALL(*mock_can_, send_frame(0x76, expected_data, false))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->reboot(3, 0));
}

// ============================================================================
// 3.4 - RTR Request Tests
// ============================================================================

TEST_F(CANCommunicationTest, RtrEncoderEstimates_CorrectArbIdAndRtrFlag) {
  // arb_id = (3 << 5) | 0x09 = 0x69
  EXPECT_CALL(*mock_can_, send_frame(0x69, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->requestEncoderEstimates(3));
}

TEST_F(CANCommunicationTest, RtrBusVoltageCurrent_CorrectArbIdAndRtrFlag) {
  // arb_id = (3 << 5) | 0x17 = 0x77
  EXPECT_CALL(*mock_can_, send_frame(0x77, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->requestBusVoltageCurrent(3));
}

TEST_F(CANCommunicationTest, RtrTemperature_CorrectArbIdAndRtrFlag) {
  // arb_id = (3 << 5) | 0x15 = 0x75
  EXPECT_CALL(*mock_can_, send_frame(0x75, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));

  EXPECT_TRUE(driver_->requestTemperature(3));
}

TEST_F(CANCommunicationTest, RtrAllMethods_CorrectArbIdsAndRtrFlag) {
  const uint8_t node_id = 3;

  // Expected cmd_ids and their corresponding arb_ids for node 3
  struct RtrExpectation {
    uint8_t cmd_id;
    uint16_t arb_id;
    std::function<bool()> method;
  };

  // Build expectations - cannot use initializer list with std::function easily,
  // so we set up and verify each one explicitly.

  // GET_VERSION: (3 << 5) | 0x00 = 0x60
  EXPECT_CALL(*mock_can_, send_frame(0x60, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));
  EXPECT_TRUE(driver_->requestVersion(node_id));
  ::testing::Mock::VerifyAndClearExpectations(mock_can_.get());

  // GET_ENCODER_ESTIMATES: (3 << 5) | 0x09 = 0x69
  EXPECT_CALL(*mock_can_, send_frame(0x69, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));
  EXPECT_TRUE(driver_->requestEncoderEstimates(node_id));
  ::testing::Mock::VerifyAndClearExpectations(mock_can_.get());

  // GET_IQ: (3 << 5) | 0x14 = 0x74
  EXPECT_CALL(*mock_can_, send_frame(0x74, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));
  EXPECT_TRUE(driver_->requestIq(node_id));
  ::testing::Mock::VerifyAndClearExpectations(mock_can_.get());

  // GET_TEMPERATURE: (3 << 5) | 0x15 = 0x75
  EXPECT_CALL(*mock_can_, send_frame(0x75, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));
  EXPECT_TRUE(driver_->requestTemperature(node_id));
  ::testing::Mock::VerifyAndClearExpectations(mock_can_.get());

  // GET_BUS_VOLTAGE_CURRENT: (3 << 5) | 0x17 = 0x77
  EXPECT_CALL(*mock_can_, send_frame(0x77, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));
  EXPECT_TRUE(driver_->requestBusVoltageCurrent(node_id));
  ::testing::Mock::VerifyAndClearExpectations(mock_can_.get());

  // GET_TORQUES: (3 << 5) | 0x1C = 0x7C
  EXPECT_CALL(*mock_can_, send_frame(0x7C, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));
  EXPECT_TRUE(driver_->requestTorques(node_id));
  ::testing::Mock::VerifyAndClearExpectations(mock_can_.get());

  // GET_POWERS: (3 << 5) | 0x1D = 0x7D
  EXPECT_CALL(*mock_can_, send_frame(0x7D, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));
  EXPECT_TRUE(driver_->requestPowers(node_id));
  ::testing::Mock::VerifyAndClearExpectations(mock_can_.get());

  // GET_ERROR: (3 << 5) | 0x03 = 0x63
  EXPECT_CALL(*mock_can_, send_frame(0x63, std::vector<uint8_t>{}, true))
      .WillOnce(Return(true));
  EXPECT_TRUE(driver_->requestErrorStatus(node_id));
  ::testing::Mock::VerifyAndClearExpectations(mock_can_.get());
}

// ============================================================================
// 3.5 - handleFrame Tests (RX message types)
// ============================================================================

TEST_F(CANCommunicationTest, HandleFrame_Heartbeat_DecodesAndUpdatesTimestamp) {
  driver_->addMotor(3);

  // HEARTBEAT cmd = 0x01, arb_id = (3 << 5) | 0x01 = 0x61
  auto data = make_heartbeat_frame(0x00000000, AXIS_STATE::CLOSED_LOOP_CONTROL, 0, 1);

  auto before = std::chrono::steady_clock::now();
  EXPECT_TRUE(driver_->handleFrame(0x61, data));
  auto after = std::chrono::steady_clock::now();

  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  ASSERT_TRUE(snapshot->heartbeat.has_value());
  EXPECT_EQ(snapshot->heartbeat->axis_error, 0x00000000u);
  EXPECT_EQ(snapshot->heartbeat->axis_state, AXIS_STATE::CLOSED_LOOP_CONTROL);
  EXPECT_EQ(snapshot->heartbeat->procedure_result, 0);
  EXPECT_EQ(snapshot->heartbeat->traj_done, 1);

  // Timestamp within 100ms of now
  EXPECT_GE(snapshot->last_heartbeat_time, before);
  EXPECT_LE(snapshot->last_heartbeat_time, after);
}

TEST_F(CANCommunicationTest, HandleFrame_EncoderEstimates_DecodesCorrectly) {
  driver_->addMotor(3);

  // GET_ENCODER_ESTIMATES cmd = 0x09, arb_id = (3 << 5) | 0x09 = 0x69
  float pos = 1.5f;
  float vel = -0.25f;
  auto data = make_two_float_frame(pos, vel);

  EXPECT_TRUE(driver_->handleFrame(0x69, data));

  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  ASSERT_TRUE(snapshot->encoder_estimates.has_value());
  EXPECT_FLOAT_EQ(snapshot->encoder_estimates->pos_estimate, 1.5f);
  EXPECT_FLOAT_EQ(snapshot->encoder_estimates->vel_estimate, -0.25f);
}

TEST_F(CANCommunicationTest, HandleFrame_Version_DecodesCorrectly) {
  driver_->addMotor(3);

  // GET_VERSION cmd = 0x00, arb_id = (3 << 5) | 0x00 = 0x60
  auto data = make_version_frame(2, 3, 6, 0, 0, 6, 11, 0);

  EXPECT_TRUE(driver_->handleFrame(0x60, data));

  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  ASSERT_TRUE(snapshot->version.has_value());
  EXPECT_EQ(snapshot->version->protocol_version, 2);
  EXPECT_EQ(snapshot->version->hw_version_major, 3);
  EXPECT_EQ(snapshot->version->hw_version_minor, 6);
  EXPECT_EQ(snapshot->version->hw_version_variant, 0);
  EXPECT_EQ(snapshot->version->fw_version_major, 0);
  EXPECT_EQ(snapshot->version->fw_version_minor, 6);
  EXPECT_EQ(snapshot->version->fw_version_revision, 11);
  EXPECT_EQ(snapshot->version->fw_version_unreleased, 0);
}

TEST_F(CANCommunicationTest, HandleFrame_ErrorStatus_DecodesCorrectly) {
  driver_->addMotor(3);

  // GET_ERROR cmd = 0x03, arb_id = (3 << 5) | 0x03 = 0x63
  auto data = make_error_status_frame(0x00000010, 0x00000004);

  EXPECT_TRUE(driver_->handleFrame(0x63, data));

  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  ASSERT_TRUE(snapshot->error_status.has_value());
  EXPECT_EQ(snapshot->error_status->active_errors, 0x00000010u);
  EXPECT_EQ(snapshot->error_status->disarm_reason, 0x00000004u);
}

TEST_F(CANCommunicationTest, HandleFrame_IqValues_DecodesCorrectly) {
  driver_->addMotor(3);

  // GET_IQ cmd = 0x14, arb_id = (3 << 5) | 0x14 = 0x74
  auto data = make_two_float_frame(2.0f, 1.8f);

  EXPECT_TRUE(driver_->handleFrame(0x74, data));

  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  ASSERT_TRUE(snapshot->iq_values.has_value());
  EXPECT_FLOAT_EQ(snapshot->iq_values->iq_setpoint, 2.0f);
  EXPECT_FLOAT_EQ(snapshot->iq_values->iq_measured, 1.8f);
}

TEST_F(CANCommunicationTest, HandleFrame_Temperature_DecodesCorrectly) {
  driver_->addMotor(3);

  // GET_TEMPERATURE cmd = 0x15, arb_id = (3 << 5) | 0x15 = 0x75
  auto data = make_temperature_frame(45.5f, 52.3f);

  EXPECT_TRUE(driver_->handleFrame(0x75, data));

  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  ASSERT_TRUE(snapshot->temperature.has_value());
  EXPECT_FLOAT_EQ(snapshot->temperature->fet_temperature, 45.5f);
  EXPECT_FLOAT_EQ(snapshot->temperature->motor_temperature, 52.3f);
}

TEST_F(CANCommunicationTest, HandleFrame_BusVoltageCurrent_DecodesCorrectly) {
  driver_->addMotor(3);

  // GET_BUS_VOLTAGE_CURRENT cmd = 0x17, arb_id = (3 << 5) | 0x17 = 0x77
  auto data = make_two_float_frame(24.1f, 0.75f);

  EXPECT_TRUE(driver_->handleFrame(0x77, data));

  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  ASSERT_TRUE(snapshot->bus_voltage_current.has_value());
  EXPECT_FLOAT_EQ(snapshot->bus_voltage_current->bus_voltage, 24.1f);
  EXPECT_FLOAT_EQ(snapshot->bus_voltage_current->bus_current, 0.75f);
}

TEST_F(CANCommunicationTest, HandleFrame_Torques_DecodesCorrectly) {
  driver_->addMotor(3);

  // GET_TORQUES cmd = 0x1C, arb_id = (3 << 5) | 0x1C = 0x7C
  auto data = make_two_float_frame(0.5f, 0.48f);

  EXPECT_TRUE(driver_->handleFrame(0x7C, data));

  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  ASSERT_TRUE(snapshot->torques.has_value());
  EXPECT_FLOAT_EQ(snapshot->torques->torque_target, 0.5f);
  EXPECT_FLOAT_EQ(snapshot->torques->torque_estimate, 0.48f);
}

TEST_F(CANCommunicationTest, HandleFrame_Powers_DecodesCorrectly) {
  driver_->addMotor(3);

  // GET_POWERS cmd = 0x1D, arb_id = (3 << 5) | 0x1D = 0x7D
  auto data = make_two_float_frame(12.0f, 10.5f);

  EXPECT_TRUE(driver_->handleFrame(0x7D, data));

  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  ASSERT_TRUE(snapshot->powers.has_value());
  EXPECT_FLOAT_EQ(snapshot->powers->electrical_power, 12.0f);
  EXPECT_FLOAT_EQ(snapshot->powers->mechanical_power, 10.5f);
}

TEST_F(CANCommunicationTest, HandleFrame_UnregisteredMotor_ReturnsFalse) {
  // Node 99 is NOT registered
  auto data = make_heartbeat_frame(0, AXIS_STATE::IDLE);
  uint16_t arb_id = make_arbitration_id(99, CMD::HEARTBEAT);

  EXPECT_FALSE(driver_->handleFrame(arb_id, data));
}

TEST_F(CANCommunicationTest, HandleFrame_InsufficientData_ReturnsFalseStateUnchanged) {
  driver_->addMotor(3);

  // Only 4 bytes instead of required 8
  std::vector<uint8_t> short_data = {0x00, 0x01, 0x02, 0x03};
  uint16_t arb_id = make_arbitration_id(3, CMD::HEARTBEAT);

  EXPECT_FALSE(driver_->handleFrame(arb_id, short_data));

  // State should remain empty (no heartbeat set)
  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  EXPECT_FALSE(snapshot->heartbeat.has_value());
}

TEST_F(CANCommunicationTest, HandleFrame_UnknownCmdId_ReturnsFalse) {
  driver_->addMotor(3);

  std::vector<uint8_t> data(8, 0);
  // cmd_id 0x1E is not handled by any case in the switch
  uint16_t arb_id = make_arbitration_id(3, 0x1E);

  EXPECT_FALSE(driver_->handleFrame(arb_id, data));
}

// ============================================================================
// 3.6 - State Accumulation Test
// ============================================================================

TEST_F(CANCommunicationTest, HandleFrame_MultipleTypes_AllFieldsAccumulate) {
  driver_->addMotor(3);

  // Send heartbeat
  auto hb_data = make_heartbeat_frame(0, AXIS_STATE::CLOSED_LOOP_CONTROL, 0, 1);
  EXPECT_TRUE(driver_->handleFrame(make_arbitration_id(3, CMD::HEARTBEAT), hb_data));

  // Send encoder estimates
  auto enc_data = make_two_float_frame(3.14f, -1.0f);
  EXPECT_TRUE(driver_->handleFrame(make_arbitration_id(3, CMD::GET_ENCODER_ESTIMATES), enc_data));

  // Send temperature
  auto temp_data = make_temperature_frame(40.0f, 55.0f);
  EXPECT_TRUE(driver_->handleFrame(make_arbitration_id(3, CMD::GET_TEMPERATURE), temp_data));

  // All three fields should be populated simultaneously
  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());

  ASSERT_TRUE(snapshot->heartbeat.has_value());
  EXPECT_EQ(snapshot->heartbeat->axis_state, AXIS_STATE::CLOSED_LOOP_CONTROL);
  EXPECT_EQ(snapshot->heartbeat->traj_done, 1);

  ASSERT_TRUE(snapshot->encoder_estimates.has_value());
  EXPECT_FLOAT_EQ(snapshot->encoder_estimates->pos_estimate, 3.14f);
  EXPECT_FLOAT_EQ(snapshot->encoder_estimates->vel_estimate, -1.0f);

  ASSERT_TRUE(snapshot->temperature.has_value());
  EXPECT_FLOAT_EQ(snapshot->temperature->fet_temperature, 40.0f);
  EXPECT_FLOAT_EQ(snapshot->temperature->motor_temperature, 55.0f);

  // Fields NOT sent should remain empty
  EXPECT_FALSE(snapshot->version.has_value());
  EXPECT_FALSE(snapshot->error_status.has_value());
  EXPECT_FALSE(snapshot->iq_values.has_value());
  EXPECT_FALSE(snapshot->bus_voltage_current.has_value());
  EXPECT_FALSE(snapshot->torques.has_value());
  EXPECT_FALSE(snapshot->powers.has_value());
}

// ============================================================================
// 3.7 - Snapshot Thread-Safety Tests
// ============================================================================

TEST_F(CANCommunicationTest, Snapshot_ReturnsCopy_ModifyingDoesNotAffectInternal) {
  driver_->addMotor(3);

  // Populate state with a heartbeat
  auto hb_data = make_heartbeat_frame(0, AXIS_STATE::CLOSED_LOOP_CONTROL);
  driver_->handleFrame(make_arbitration_id(3, CMD::HEARTBEAT), hb_data);

  // Take a snapshot
  auto snapshot = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot.has_value());
  ASSERT_TRUE(snapshot->heartbeat.has_value());
  EXPECT_EQ(snapshot->heartbeat->axis_state, AXIS_STATE::CLOSED_LOOP_CONTROL);

  // Mutate the snapshot's heartbeat
  snapshot->heartbeat->axis_state = AXIS_STATE::IDLE;

  // Verify internal state is unchanged
  auto snapshot2 = driver_->getMotorStateSnapshot(3);
  ASSERT_TRUE(snapshot2.has_value());
  ASSERT_TRUE(snapshot2->heartbeat.has_value());
  EXPECT_EQ(snapshot2->heartbeat->axis_state, AXIS_STATE::CLOSED_LOOP_CONTROL);
}

TEST_F(CANCommunicationTest, Snapshot_UnregisteredMotor_ReturnsNullopt) {
  // Motor 99 was never registered
  auto snapshot = driver_->getMotorStateSnapshot(99);
  EXPECT_FALSE(snapshot.has_value());
  EXPECT_EQ(snapshot, std::nullopt);
}
