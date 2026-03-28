// Copyright 2025 Pragati Robotics
// Error handling behavioral tests for ODriveCanDriver
//
// Tests error paths, failure propagation, thread safety, and edge cases
// of the standalone ODriveCanDriver class using gtest + gmock.
//
// Spec scenarios:
//   4.1 CAN send failure propagation
//   4.2 Null interface safety
//   4.3 Heartbeat error field detection
//   4.4 ErrorStatus decode
//   4.5 Frame rejection
//   4.6 startAnticogging unsupported
//   4.7 Concurrent access
//   4.8 Timestamp freshness
//
// No ROS2 dependencies. No hardware dependencies.

#include <gtest/gtest.h>
#include <gmock/gmock.h>

#include <chrono>
#include <cstring>
#include <memory>
#include <thread>
#include <vector>

#include "odrive_control_ros2/odrive_can_driver.hpp"
#include "odrive_control_ros2/odrive_cansimple_protocol.hpp"

using ::testing::_;
using ::testing::Return;

// ============================================================================
// Mock
// ============================================================================

class MockSocketCANInterface : public odrive_cansimple::SocketCANInterface {
public:
  MOCK_METHOD(bool, send_frame,
              (uint16_t arb_id, const std::vector<uint8_t>& data, bool is_rtr),
              (override));
  MOCK_METHOD(bool, receive_frame,
              (uint16_t & arb_id, std::vector<uint8_t>& data, int timeout_ms),
              (override));
};

// ============================================================================
// Helpers
// ============================================================================

// Build an 8-byte heartbeat frame:
//   bytes 0-3: axis_error (uint32_t LE)
//   byte  4:   axis_state
//   byte  5:   procedure_result
//   byte  6:   traj_done
//   byte  7:   reserved
static std::vector<uint8_t> make_heartbeat_data(uint32_t axis_error,
                                                 uint8_t axis_state,
                                                 uint8_t procedure_result,
                                                 uint8_t traj_done) {
  std::vector<uint8_t> data(8, 0);
  std::memcpy(data.data(), &axis_error, 4);
  data[4] = axis_state;
  data[5] = procedure_result;
  data[6] = traj_done;
  return data;
}

// Build an 8-byte GET_ERROR (ErrorStatus) frame:
//   bytes 0-3: active_errors (uint32_t LE)
//   bytes 4-7: disarm_reason (uint32_t LE)
static std::vector<uint8_t> make_error_status_data(uint32_t active_errors,
                                                    uint32_t disarm_reason) {
  std::vector<uint8_t> data(8, 0);
  std::memcpy(data.data(), &active_errors, 4);
  std::memcpy(data.data() + 4, &disarm_reason, 4);
  return data;
}

// Build an 8-byte frame from two floats (used for encoder estimates, etc.)
static std::vector<uint8_t> make_dual_float_data(float a, float b) {
  std::vector<uint8_t> data(8, 0);
  std::memcpy(data.data(), &a, 4);
  std::memcpy(data.data() + 4, &b, 4);
  return data;
}

// ============================================================================
// Fixture
// ============================================================================

class ErrorHandlingTest : public ::testing::Test {
protected:
  void SetUp() override {
    mock_can_ = std::make_shared<MockSocketCANInterface>();
    driver_ = std::make_unique<odrive_can::ODriveCanDriver>(mock_can_);
    driver_->addMotor(3);  // Register default test motor (node_id=3)
  }

  std::shared_ptr<MockSocketCANInterface> mock_can_;
  std::unique_ptr<odrive_can::ODriveCanDriver> driver_;

  // Default node_id for most tests
  static constexpr uint8_t kNodeId = 3;
};

// ============================================================================
// 4.1 CAN send failure propagation
// ============================================================================

// 4.1.1 setInputPos returns false when send_frame fails
TEST_F(ErrorHandlingTest, SendFailure_SetInputPos_ReturnsFalse) {
  EXPECT_CALL(*mock_can_, send_frame(_, _, _)).WillOnce(Return(false));
  EXPECT_FALSE(driver_->setInputPos(kNodeId, 1.0f));
}

// 4.1.2 estop returns false when send_frame fails
TEST_F(ErrorHandlingTest, SendFailure_Estop_ReturnsFalse) {
  EXPECT_CALL(*mock_can_, send_frame(_, _, _)).WillOnce(Return(false));
  EXPECT_FALSE(driver_->estop(kNodeId));
}

// 4.1.3 setAxisState returns false when send_frame fails
TEST_F(ErrorHandlingTest, SendFailure_SetAxisState_ReturnsFalse) {
  EXPECT_CALL(*mock_can_, send_frame(_, _, _)).WillOnce(Return(false));
  EXPECT_FALSE(
      driver_->setAxisState(kNodeId, odrive_cansimple::AXIS_STATE::CLOSED_LOOP_CONTROL));
}

// 4.1.4 requestEncoderEstimates (RTR) returns false when send_frame fails
TEST_F(ErrorHandlingTest, SendFailure_RequestEncoderEstimates_ReturnsFalse) {
  EXPECT_CALL(*mock_can_, send_frame(_, _, _)).WillOnce(Return(false));
  EXPECT_FALSE(driver_->requestEncoderEstimates(kNodeId));
}

// ============================================================================
// 4.2 Null interface safety
// ============================================================================

// 4.2.1 estop with nullptr interface returns false, no crash
TEST_F(ErrorHandlingTest, NullInterface_Estop_ReturnsFalse) {
  auto null_driver =
      std::make_unique<odrive_can::ODriveCanDriver>(nullptr);
  null_driver->addMotor(kNodeId);
  EXPECT_FALSE(null_driver->estop(kNodeId));
}

// 4.2.2 requestEncoderEstimates with nullptr interface returns false, no crash
TEST_F(ErrorHandlingTest, NullInterface_RequestEncoderEstimates_ReturnsFalse) {
  auto null_driver =
      std::make_unique<odrive_can::ODriveCanDriver>(nullptr);
  null_driver->addMotor(kNodeId);
  EXPECT_FALSE(null_driver->requestEncoderEstimates(kNodeId));
}

// ============================================================================
// 4.3 Heartbeat error field detection
// ============================================================================

// 4.3.1 Heartbeat with non-zero axis_error is stored correctly
TEST_F(ErrorHandlingTest, Heartbeat_NonZeroAxisError_StoredCorrectly) {
  uint16_t arb_id = odrive_cansimple::make_arbitration_id(
      kNodeId, odrive_cansimple::CMD::HEARTBEAT);
  auto data = make_heartbeat_data(0x00000040, 0x08, 0, 0);

  EXPECT_TRUE(driver_->handleFrame(arb_id, data));

  auto state = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state.has_value());
  ASSERT_TRUE(state->heartbeat.has_value());
  EXPECT_EQ(state->heartbeat->axis_error, 0x00000040u);
}

// 4.3.2 Error clearing: non-zero then zero → final state shows zero
TEST_F(ErrorHandlingTest, Heartbeat_ErrorClearing_FinalStateZero) {
  uint16_t arb_id = odrive_cansimple::make_arbitration_id(
      kNodeId, odrive_cansimple::CMD::HEARTBEAT);

  // First heartbeat: axis_error = 0x10
  auto data1 = make_heartbeat_data(0x10, 0x08, 0, 0);
  EXPECT_TRUE(driver_->handleFrame(arb_id, data1));

  auto state1 = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state1.has_value());
  ASSERT_TRUE(state1->heartbeat.has_value());
  EXPECT_EQ(state1->heartbeat->axis_error, 0x10u);

  // Second heartbeat: axis_error = 0x00 (cleared)
  auto data2 = make_heartbeat_data(0x00, 0x08, 0, 0);
  EXPECT_TRUE(driver_->handleFrame(arb_id, data2));

  auto state2 = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state2.has_value());
  ASSERT_TRUE(state2->heartbeat.has_value());
  EXPECT_EQ(state2->heartbeat->axis_error, 0x00u);
}

// 4.3.3 All bits set: axis_error = 0xFFFFFFFF
TEST_F(ErrorHandlingTest, Heartbeat_AllBitsSet_StoredCorrectly) {
  uint16_t arb_id = odrive_cansimple::make_arbitration_id(
      kNodeId, odrive_cansimple::CMD::HEARTBEAT);
  auto data = make_heartbeat_data(0xFFFFFFFF, 0xFF, 0xFF, 0xFF);

  EXPECT_TRUE(driver_->handleFrame(arb_id, data));

  auto state = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state.has_value());
  ASSERT_TRUE(state->heartbeat.has_value());
  EXPECT_EQ(state->heartbeat->axis_error, 0xFFFFFFFFu);
}

// ============================================================================
// 4.4 ErrorStatus decode
// ============================================================================

// 4.4.1 Non-zero active_errors and disarm_reason
TEST_F(ErrorHandlingTest, ErrorStatus_NonZeroFields_StoredCorrectly) {
  uint16_t arb_id = odrive_cansimple::make_arbitration_id(
      kNodeId, odrive_cansimple::CMD::GET_ERROR);
  auto data = make_error_status_data(0x04, 0x08);

  EXPECT_TRUE(driver_->handleFrame(arb_id, data));

  auto state = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state.has_value());
  ASSERT_TRUE(state->error_status.has_value());
  EXPECT_EQ(state->error_status->active_errors, 0x04u);
  EXPECT_EQ(state->error_status->disarm_reason, 0x08u);
}

// 4.4.2 Both fields zero
TEST_F(ErrorHandlingTest, ErrorStatus_BothZero_StoredCorrectly) {
  uint16_t arb_id = odrive_cansimple::make_arbitration_id(
      kNodeId, odrive_cansimple::CMD::GET_ERROR);
  auto data = make_error_status_data(0x00, 0x00);

  EXPECT_TRUE(driver_->handleFrame(arb_id, data));

  auto state = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state.has_value());
  ASSERT_TRUE(state->error_status.has_value());
  EXPECT_EQ(state->error_status->active_errors, 0x00u);
  EXPECT_EQ(state->error_status->disarm_reason, 0x00u);
}

// ============================================================================
// 4.5 Frame rejection
// ============================================================================

// 4.5.1 Unregistered node_id → returns false
TEST_F(ErrorHandlingTest, FrameRejection_UnregisteredNode_ReturnsFalse) {
  uint16_t arb_id = odrive_cansimple::make_arbitration_id(
      99, odrive_cansimple::CMD::HEARTBEAT);
  auto data = make_heartbeat_data(0, 1, 0, 1);

  EXPECT_FALSE(driver_->handleFrame(arb_id, data));
}

// 4.5.2 Insufficient data (4 bytes instead of 8) → returns false, state unchanged
TEST_F(ErrorHandlingTest, FrameRejection_InsufficientData_ReturnsFalse) {
  uint16_t arb_id = odrive_cansimple::make_arbitration_id(
      kNodeId, odrive_cansimple::CMD::HEARTBEAT);
  std::vector<uint8_t> short_data = {0x00, 0x00, 0x00, 0x00};  // Only 4 bytes

  EXPECT_FALSE(driver_->handleFrame(arb_id, short_data));

  // State should have no heartbeat set
  auto state = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state.has_value());
  EXPECT_FALSE(state->heartbeat.has_value());
}

// 4.5.3 Unknown cmd_id (0x1E is not in the switch) → returns false
TEST_F(ErrorHandlingTest, FrameRejection_UnknownCmdId_ReturnsFalse) {
  uint16_t arb_id = odrive_cansimple::make_arbitration_id(kNodeId, 0x1E);
  std::vector<uint8_t> data(8, 0);

  EXPECT_FALSE(driver_->handleFrame(arb_id, data));
}

// ============================================================================
// 4.6 startAnticogging unsupported
// ============================================================================

// 4.6.1 startAnticogging returns false and sends no CAN frame
TEST_F(ErrorHandlingTest, StartAnticogging_ReturnsFalse_NoCANFrame) {
  // Expect NO calls to send_frame at all
  EXPECT_CALL(*mock_can_, send_frame(_, _, _)).Times(0);

  EXPECT_FALSE(driver_->startAnticogging(kNodeId));
}

// ============================================================================
// 4.7 Concurrent access
// ============================================================================

// 4.7.1 Two threads calling handleFrame concurrently — no crash or deadlock
TEST_F(ErrorHandlingTest, ConcurrentHandleFrame_NoCrashOrDeadlock) {
  uint16_t heartbeat_arb =
      odrive_cansimple::make_arbitration_id(kNodeId, odrive_cansimple::CMD::HEARTBEAT);
  uint16_t encoder_arb = odrive_cansimple::make_arbitration_id(
      kNodeId, odrive_cansimple::CMD::GET_ENCODER_ESTIMATES);

  auto heartbeat_data = make_heartbeat_data(0, 0x08, 0, 1);
  auto encoder_data = make_dual_float_data(1.5f, -0.25f);

  constexpr int kIterations = 1000;

  std::thread t1([&]() {
    for (int i = 0; i < kIterations; ++i) {
      driver_->handleFrame(heartbeat_arb, heartbeat_data);
    }
  });

  std::thread t2([&]() {
    for (int i = 0; i < kIterations; ++i) {
      driver_->handleFrame(encoder_arb, encoder_data);
    }
  });

  t1.join();
  t2.join();

  // Verify state is consistent (both message types were processed)
  auto state = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state.has_value());
  EXPECT_TRUE(state->heartbeat.has_value());
  EXPECT_TRUE(state->encoder_estimates.has_value());
}

// 4.7.2 addMotor + hasMotor concurrency — no crash or deadlock
TEST_F(ErrorHandlingTest, ConcurrentAddMotorHasMotor_NoCrashOrDeadlock) {
  // Create a fresh driver without the default motor
  auto fresh_driver =
      std::make_unique<odrive_can::ODriveCanDriver>(mock_can_);

  constexpr int kIterations = 1000;

  std::thread t1([&]() {
    for (int i = 0; i < kIterations; ++i) {
      uint8_t node_id = static_cast<uint8_t>(i % 64);
      fresh_driver->addMotor(node_id);
    }
  });

  std::thread t2([&]() {
    for (int i = 0; i < kIterations; ++i) {
      uint8_t node_id = static_cast<uint8_t>(i % 64);
      // Just call hasMotor — result doesn't matter, we're testing for crashes
      (void)fresh_driver->hasMotor(node_id);
    }
  });

  t1.join();
  t2.join();

  // After all iterations, all 64 node_ids should be registered
  for (uint8_t id = 0; id < 64; ++id) {
    EXPECT_TRUE(fresh_driver->hasMotor(id));
  }
}

// ============================================================================
// 4.8 Timestamp freshness
// ============================================================================

// 4.8.1 Two heartbeats with time gap → second timestamp is strictly later
TEST_F(ErrorHandlingTest, Timestamp_HeartbeatMonotonicAdvancement) {
  uint16_t arb_id = odrive_cansimple::make_arbitration_id(
      kNodeId, odrive_cansimple::CMD::HEARTBEAT);
  auto data = make_heartbeat_data(0, 0x08, 0, 1);

  // First heartbeat
  EXPECT_TRUE(driver_->handleFrame(arb_id, data));
  auto state1 = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state1.has_value());
  auto time1 = state1->last_heartbeat_time;

  // Wait to ensure measurable time difference
  std::this_thread::sleep_for(std::chrono::milliseconds(10));

  // Second heartbeat
  EXPECT_TRUE(driver_->handleFrame(arb_id, data));
  auto state2 = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state2.has_value());
  auto time2 = state2->last_heartbeat_time;

  EXPECT_GT(time2, time1)
      << "Second heartbeat timestamp should be strictly greater than first";
}

// 4.8.2 Heartbeat and EncoderEstimates have independent timestamps
TEST_F(ErrorHandlingTest, Timestamp_IndependentPerMessageType) {
  uint16_t heartbeat_arb =
      odrive_cansimple::make_arbitration_id(kNodeId, odrive_cansimple::CMD::HEARTBEAT);
  uint16_t encoder_arb = odrive_cansimple::make_arbitration_id(
      kNodeId, odrive_cansimple::CMD::GET_ENCODER_ESTIMATES);

  // Send heartbeat first
  auto hb_data = make_heartbeat_data(0, 0x08, 0, 1);
  EXPECT_TRUE(driver_->handleFrame(heartbeat_arb, hb_data));
  auto state1 = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state1.has_value());
  auto hb_time = state1->last_heartbeat_time;

  // Wait to ensure measurable time difference
  std::this_thread::sleep_for(std::chrono::milliseconds(10));

  // Send encoder estimates
  auto enc_data = make_dual_float_data(1.5f, -0.25f);
  EXPECT_TRUE(driver_->handleFrame(encoder_arb, enc_data));
  auto state2 = driver_->getMotorStateSnapshot(kNodeId);
  ASSERT_TRUE(state2.has_value());
  auto enc_time = state2->last_encoder_estimates_time;

  // Encoder timestamp should be later than heartbeat timestamp
  EXPECT_GT(enc_time, hb_time)
      << "Encoder estimates timestamp should be later than heartbeat";

  // Heartbeat timestamp should NOT have changed (independent)
  EXPECT_EQ(state2->last_heartbeat_time, hb_time)
      << "Heartbeat timestamp should remain unchanged after encoder update";
}
