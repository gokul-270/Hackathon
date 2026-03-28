/*
 * CAN Communication Tests
 *
 * Comprehensive test suite for CAN communication layer including:
 * 1. Basic send/receive operations
 * 2. Error handling and recovery
 * 3. Timeout scenarios
 * 4. Message parsing and validation
 * 5. Protocol-specific behaviors
 */

#include <gtest/gtest.h>
#include <memory>
#include <thread>
#include <chrono>

#include "motor_control_ros2/simulation/mock_can_interface.hpp"
#include "motor_control_ros2/mg6010_protocol.hpp"

using namespace motor_control_ros2;
using namespace motor_control_ros2::test;
using namespace std::chrono_literals;

// =============================================================================
// TEST FIXTURES
// =============================================================================

class CANCommunicationTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    mock_can_ = std::make_shared<ConfigurableMockCANInterface>();
  }

  void TearDown() override
  {
    mock_can_.reset();
  }

  std::shared_ptr<ConfigurableMockCANInterface> mock_can_;
};

// =============================================================================
// INITIALIZATION TESTS
// =============================================================================

TEST_F(CANCommunicationTest, InitializeSuccess)
{
  EXPECT_TRUE(mock_can_->initialize("can0", 1000000));
  EXPECT_TRUE(mock_can_->is_connected());

  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.init_call_count, 1);
}

TEST_F(CANCommunicationTest, InitializeFailure)
{
  mock_can_->inject_error_on_next_operation();

  EXPECT_FALSE(mock_can_->initialize("can0", 1000000));
  EXPECT_FALSE(mock_can_->is_connected());
  EXPECT_EQ(mock_can_->get_last_error(), "Simulated initialization failure");
}

TEST_F(CANCommunicationTest, MultipleInitialize)
{
  EXPECT_TRUE(mock_can_->initialize("can0", 1000000));
  EXPECT_TRUE(mock_can_->initialize("can1", 500000));

  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.init_call_count, 2);
}

// =============================================================================
// SEND MESSAGE TESTS
// =============================================================================

TEST_F(CANCommunicationTest, SendMessageSuccess)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  std::vector<uint8_t> test_data = {0x01, 0x02, 0x03, 0x04};
  EXPECT_TRUE(mock_can_->send_message(0x100, test_data));

  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.messages_sent, 1);

  // Verify message was recorded
  uint32_t sent_id;
  std::vector<uint8_t> sent_data;
  ASSERT_TRUE(mock_can_->get_last_sent_message(sent_id, sent_data));
  EXPECT_EQ(sent_id, 0x100);
  EXPECT_EQ(sent_data, test_data);
}

TEST_F(CANCommunicationTest, SendMessageWithoutInit)
{
  std::vector<uint8_t> test_data = {0x01, 0x02};
  EXPECT_FALSE(mock_can_->send_message(0x100, test_data));
  EXPECT_EQ(mock_can_->get_last_error(), "CAN interface not connected");
}

TEST_F(CANCommunicationTest, SendMessageFailure)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  mock_can_->inject_error_on_next_operation();

  std::vector<uint8_t> test_data = {0x01, 0x02};
  EXPECT_FALSE(mock_can_->send_message(0x100, test_data));

  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.send_errors, 1);
}

TEST_F(CANCommunicationTest, SendMultipleMessages)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  for (uint32_t i = 0; i < 10; i++) {
    std::vector<uint8_t> data = {static_cast<uint8_t>(i)};
    EXPECT_TRUE(mock_can_->send_message(0x100 + i, data));
  }

  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.messages_sent, 10);

  auto all_messages = mock_can_->get_sent_messages();
  EXPECT_EQ(all_messages.size(), 10);
}

TEST_F(CANCommunicationTest, SendEmptyMessage)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  std::vector<uint8_t> empty_data;
  EXPECT_TRUE(mock_can_->send_message(0x100, empty_data));

  uint32_t sent_id;
  std::vector<uint8_t> sent_data;
  ASSERT_TRUE(mock_can_->get_last_sent_message(sent_id, sent_data));
  EXPECT_EQ(sent_id, 0x100);
  EXPECT_TRUE(sent_data.empty());
}

TEST_F(CANCommunicationTest, SendLargeMessage)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  // CAN messages are typically limited to 8 bytes, but we test with larger
  std::vector<uint8_t> large_data(16, 0xFF);
  EXPECT_TRUE(mock_can_->send_message(0x100, large_data));

  uint32_t sent_id;
  std::vector<uint8_t> sent_data;
  ASSERT_TRUE(mock_can_->get_last_sent_message(sent_id, sent_data));
  EXPECT_EQ(sent_data.size(), 16);  // Mock allows it for testing
}

// =============================================================================
// RECEIVE MESSAGE TESTS
// =============================================================================

TEST_F(CANCommunicationTest, ReceiveMessageSuccess)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  // Queue a message for reception
  std::vector<uint8_t> test_data = {0xAA, 0xBB, 0xCC};
  mock_can_->queue_receive_message(0x200, test_data);

  uint32_t received_id;
  std::vector<uint8_t> received_data;
  EXPECT_TRUE(mock_can_->receive_message(received_id, received_data, 100));

  EXPECT_EQ(received_id, 0x200);
  EXPECT_EQ(received_data, test_data);

  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.messages_received, 1);
}

TEST_F(CANCommunicationTest, ReceiveMessageTimeout)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  uint32_t received_id;
  std::vector<uint8_t> received_data;

  // No message queued - should timeout
  EXPECT_FALSE(mock_can_->receive_message(received_id, received_data, 10));
  EXPECT_EQ(mock_can_->get_last_error(), "No message received within timeout");
}

TEST_F(CANCommunicationTest, ReceiveMessageWithoutInit)
{
  uint32_t received_id;
  std::vector<uint8_t> received_data;

  EXPECT_FALSE(mock_can_->receive_message(received_id, received_data, 100));
  EXPECT_EQ(mock_can_->get_last_error(), "CAN interface not connected");
}

TEST_F(CANCommunicationTest, ReceiveMultipleMessages)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  // Queue multiple messages
  for (uint32_t i = 0; i < 5; i++) {
    std::vector<uint8_t> data = {static_cast<uint8_t>(i)};
    mock_can_->queue_receive_message(0x200 + i, data);
  }

  // Receive all messages
  for (uint32_t i = 0; i < 5; i++) {
    uint32_t id;
    std::vector<uint8_t> data;
    EXPECT_TRUE(mock_can_->receive_message(id, data, 100));
    EXPECT_EQ(id, 0x200 + i);
    EXPECT_EQ(data[0], i);
  }

  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.messages_received, 5);
}

// =============================================================================
// REQUEST-RESPONSE TESTS
// =============================================================================

TEST_F(CANCommunicationTest, RequestResponsePattern)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  // Configure automatic response
  std::vector<uint8_t> request_data = {0x01, 0x02};
  std::vector<uint8_t> response_data = {0x03, 0x04, 0x05};
  mock_can_->configure_response(0x100, 0x200, response_data);

  // Send request
  EXPECT_TRUE(mock_can_->send_message(0x100, request_data));

  // Receive response
  uint32_t id;
  std::vector<uint8_t> data;
  EXPECT_TRUE(mock_can_->receive_message(id, data, 100));
  EXPECT_EQ(id, 0x200);
  EXPECT_EQ(data, response_data);
}

TEST_F(CANCommunicationTest, MultipleRequestResponse)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  // Configure multiple responses
  for (uint32_t i = 0; i < 3; i++) {
    std::vector<uint8_t> resp_data = {static_cast<uint8_t>(i * 10)};
    mock_can_->configure_response(0x100 + i, 0x200 + i, resp_data);
  }

  // Send requests and verify responses
  for (uint32_t i = 0; i < 3; i++) {
    std::vector<uint8_t> req_data = {static_cast<uint8_t>(i)};
    EXPECT_TRUE(mock_can_->send_message(0x100 + i, req_data));

    uint32_t id;
    std::vector<uint8_t> data;
    EXPECT_TRUE(mock_can_->receive_message(id, data, 100));
    EXPECT_EQ(id, 0x200 + i);
    EXPECT_EQ(data[0], i * 10);
  }
}

// =============================================================================
// ERROR INJECTION TESTS
// =============================================================================

TEST_F(CANCommunicationTest, DisconnectionHandling)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));
  EXPECT_TRUE(mock_can_->is_connected());

  // Simulate disconnection
  mock_can_->simulate_disconnect();
  EXPECT_FALSE(mock_can_->is_connected());

  // Sending should fail
  std::vector<uint8_t> data = {0x01};
  EXPECT_FALSE(mock_can_->send_message(0x100, data));

  // Reconnect and verify
  mock_can_->simulate_reconnect();
  EXPECT_TRUE(mock_can_->is_connected());
  EXPECT_TRUE(mock_can_->send_message(0x100, data));
}

TEST_F(CANCommunicationTest, SendErrorRecovery)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  std::vector<uint8_t> data = {0x01, 0x02};

  // First send should fail
  mock_can_->inject_error_on_next_operation();
  EXPECT_FALSE(mock_can_->send_message(0x100, data));

  // Second send should succeed (error only on next operation)
  EXPECT_TRUE(mock_can_->send_message(0x100, data));

  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.messages_sent, 1);
  EXPECT_EQ(stats.send_errors, 1);
}

TEST_F(CANCommunicationTest, ReceiveErrorRecovery)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  mock_can_->queue_receive_message(0x200, {0x01, 0x02});

  // First receive should fail
  mock_can_->inject_error_on_next_operation();
  uint32_t id;
  std::vector<uint8_t> data;
  EXPECT_FALSE(mock_can_->receive_message(id, data, 100));

  // Message should still be in queue - second receive succeeds
  EXPECT_TRUE(mock_can_->receive_message(id, data, 100));
  EXPECT_EQ(id, 0x200);
}

// =============================================================================
// NODE CONFIGURATION TESTS
// =============================================================================

TEST_F(CANCommunicationTest, ConfigureNode)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  EXPECT_TRUE(mock_can_->configure_node(1, 1000000));
  EXPECT_TRUE(mock_can_->configure_node(2, 1000000));
  EXPECT_TRUE(mock_can_->configure_node(3, 1000000));
}

TEST_F(CANCommunicationTest, ConfigureNodeWithoutInit)
{
  EXPECT_FALSE(mock_can_->configure_node(1, 1000000));
  EXPECT_EQ(mock_can_->get_last_error(), "CAN interface not connected");
}

// =============================================================================
// MESSAGE HISTORY AND INSPECTION TESTS
// =============================================================================

TEST_F(CANCommunicationTest, MessageCountTracking)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  // Send messages with different IDs
  for (int i = 0; i < 5; i++) {
    mock_can_->send_message(0x100, {0x01});
  }
  for (int i = 0; i < 3; i++) {
    mock_can_->send_message(0x200, {0x02});
  }

  EXPECT_EQ(mock_can_->get_message_count(0x100), 5);
  EXPECT_EQ(mock_can_->get_message_count(0x200), 3);
  EXPECT_EQ(mock_can_->get_message_count(0x300), 0);
}

TEST_F(CANCommunicationTest, MessageHistoryClear)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  mock_can_->send_message(0x100, {0x01});
  mock_can_->send_message(0x200, {0x02});

  EXPECT_EQ(mock_can_->get_sent_messages().size(), 2);

  mock_can_->clear_message_history();

  EXPECT_EQ(mock_can_->get_sent_messages().size(), 0);
  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.messages_sent, 0);
}

TEST_F(CANCommunicationTest, StatisticsAccuracy)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  // Generate traffic
  for (int i = 0; i < 10; i++) {
    mock_can_->send_message(0x100 + i, {static_cast<uint8_t>(i)});
  }

  for (int i = 0; i < 5; i++) {
    mock_can_->queue_receive_message(0x200 + i, {static_cast<uint8_t>(i)});
  }

  uint32_t id;
  std::vector<uint8_t> data;
  for (int i = 0; i < 5; i++) {
    mock_can_->receive_message(id, data, 100);
  }

  // Inject some errors
  mock_can_->inject_error_on_next_operation();
  mock_can_->send_message(0x999, {0xFF});

  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.messages_sent, 10);
  EXPECT_EQ(stats.messages_received, 5);
  EXPECT_EQ(stats.send_errors, 1);
  EXPECT_EQ(stats.init_call_count, 1);
}

// =============================================================================
// MOCK RESET TESTS
// =============================================================================

TEST_F(CANCommunicationTest, MockReset)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));
  mock_can_->send_message(0x100, {0x01, 0x02});

  EXPECT_TRUE(mock_can_->is_connected());
  EXPECT_EQ(mock_can_->get_sent_messages().size(), 1);

  mock_can_->reset();

  EXPECT_FALSE(mock_can_->is_connected());
  EXPECT_EQ(mock_can_->get_sent_messages().size(), 0);
  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.messages_sent, 0);
  EXPECT_EQ(stats.init_call_count, 0);
}

// =============================================================================
// MG6010 PROTOCOL-SPECIFIC TESTS
// =============================================================================

TEST_F(CANCommunicationTest, MG6010PositionCommandFormat)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  // Create position command using helper
  auto cmd_data = CANTestHelpers::create_mg6010_position_command(1.5f, 0.5f);

  EXPECT_EQ(cmd_data.size(), 8);
  EXPECT_TRUE(mock_can_->send_message(0x101, cmd_data));

  // Verify message was sent correctly
  uint32_t id;
  std::vector<uint8_t> data;
  ASSERT_TRUE(mock_can_->get_last_sent_message(id, data));
  EXPECT_EQ(id, 0x101);
  EXPECT_EQ(data.size(), 8);
}

TEST_F(CANCommunicationTest, MG6010FeedbackParsing)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  // Create feedback message
  auto feedback_data = CANTestHelpers::create_mg6010_feedback(2.0f, 1.5f, 0.5f);

  mock_can_->queue_receive_message(0x201, feedback_data);

  uint32_t id;
  std::vector<uint8_t> data;
  EXPECT_TRUE(mock_can_->receive_message(id, data, 100));
  EXPECT_EQ(id, 0x201);
  EXPECT_EQ(data.size(), 8);
}

TEST_F(CANCommunicationTest, MG6010RequestResponseCycle)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  // Configure MG6010 feedback response
  auto feedback = CANTestHelpers::create_mg6010_feedback(1.0f, 0.5f, 0.2f);
  mock_can_->configure_response(0x101, 0x201, feedback);

  // Send position command
  auto command = CANTestHelpers::create_mg6010_position_command(1.0f, 0.5f);
  EXPECT_TRUE(mock_can_->send_message(0x101, command));

  // Receive feedback
  uint32_t id;
  std::vector<uint8_t> data;
  EXPECT_TRUE(mock_can_->receive_message(id, data, 100));
  EXPECT_EQ(id, 0x201);
  EXPECT_EQ(data, feedback);
}

// =============================================================================
// CONCURRENCY TESTS (basic thread-safety validation)
// =============================================================================

TEST_F(CANCommunicationTest, ConcurrentSends)
{
  ASSERT_TRUE(mock_can_->initialize("can0", 1000000));

  const int num_threads = 4;
  const int messages_per_thread = 25;

  std::vector<std::thread> threads;
  for (int t = 0; t < num_threads; t++) {
    threads.emplace_back([this, t, messages_per_thread]() {
      for (int i = 0; i < messages_per_thread; i++) {
        std::vector<uint8_t> data = {static_cast<uint8_t>(t), static_cast<uint8_t>(i)};
        mock_can_->send_message(0x100 + t, data);
      }
    });
  }

  for (auto & thread : threads) {
    thread.join();
  }

  auto stats = mock_can_->get_statistics();
  EXPECT_EQ(stats.messages_sent, num_threads * messages_per_thread);
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
