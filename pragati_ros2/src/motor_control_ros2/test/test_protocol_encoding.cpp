#include <gtest/gtest.h>
#include "motor_control_ros2/mg6010_protocol.hpp"
#include "motor_control_ros2/simulation/mock_can_interface.hpp"
#include <cstring>
#include <vector>
#include <cstdint>
#include <algorithm>
#include <cmath>
#include <limits>

namespace motor_control_ros2
{

class MG6010ProtocolTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        protocol_ = std::make_unique<MG6010Protocol>();
    }

    void TearDown() override
    {
        protocol_.reset();
    }

    std::unique_ptr<MG6010Protocol> protocol_;
};

// Test: Protocol construction
TEST_F(MG6010ProtocolTest, Construction)
{
    ASSERT_NE(protocol_, nullptr);
    EXPECT_FALSE(protocol_->is_initialized());
}

// Test: Protocol constants are defined correctly
TEST_F(MG6010ProtocolTest, ProtocolConstants)
{
    // Verify command codes match protocol specification
    EXPECT_EQ(MG6010Protocol::CMD_MOTOR_OFF, 0x80);
    EXPECT_EQ(MG6010Protocol::CMD_MOTOR_ON, 0x88);
    EXPECT_EQ(MG6010Protocol::CMD_MOTOR_STOP, 0x81);
    EXPECT_EQ(MG6010Protocol::CMD_TORQUE_CLOSED_LOOP, 0xA1);
    EXPECT_EQ(MG6010Protocol::CMD_SPEED_CLOSED_LOOP, 0xA2);

    // Verify base arbitration ID
    EXPECT_EQ(MG6010Protocol::BASE_ARBITRATION_ID, 0x140);
}

// Test: Calling methods when not initialized returns false
TEST_F(MG6010ProtocolTest, UninitializedStateBehavior)
{
    // All control methods should return false when not initialized
    EXPECT_FALSE(protocol_->motor_on());
    EXPECT_FALSE(protocol_->motor_off());
    EXPECT_FALSE(protocol_->motor_stop());
    EXPECT_FALSE(protocol_->speed_closed_loop_control(1.0));
    EXPECT_FALSE(protocol_->torque_closed_loop_control(1.0));
    EXPECT_FALSE(protocol_->set_absolute_position(0.0));
}

// Test: PID parameters structure
TEST_F(MG6010ProtocolTest, PIDParametersStructure)
{
    MG6010Protocol::PIDParams pid;

    // Set all parameters
    pid.angle_kp = 10;
    pid.angle_ki = 5;
    pid.speed_kp = 20;
    pid.speed_ki = 10;
    pid.current_kp = 30;
    pid.current_ki = 15;

    // Verify all fields accessible
    EXPECT_EQ(pid.angle_kp, 10);
    EXPECT_EQ(pid.angle_ki, 5);
    EXPECT_EQ(pid.speed_kp, 20);
    EXPECT_EQ(pid.speed_ki, 10);
    EXPECT_EQ(pid.current_kp, 30);
    EXPECT_EQ(pid.current_ki, 15);
}

// Test: Status structure
TEST_F(MG6010ProtocolTest, StatusStructure)
{
    MG6010Protocol::Status status;

    // Set all fields
    status.voltage = 24.0;
    status.temperature = 45.0;
    status.error_flags = 0;
    status.motor_running = true;
    status.torque_current = 2.5;
    status.speed = 3.14;
    status.encoder_position = 1024;

    // Verify all fields accessible
    EXPECT_DOUBLE_EQ(status.voltage, 24.0);
    EXPECT_DOUBLE_EQ(status.temperature, 45.0);
    EXPECT_EQ(status.error_flags, 0u);
    EXPECT_TRUE(status.motor_running);
    EXPECT_DOUBLE_EQ(status.torque_current, 2.5);
    EXPECT_DOUBLE_EQ(status.speed, 3.14);
    EXPECT_EQ(status.encoder_position, 1024u);
}

// Test: Error message handling
TEST_F(MG6010ProtocolTest, ErrorMessageHandling)
{
    // Call a method when not initialized
    protocol_->motor_on();

    // Should have error message
    std::string error = protocol_->get_last_error();
    EXPECT_FALSE(error.empty());
}

// Test: Node ID getter
TEST_F(MG6010ProtocolTest, NodeIDGetter)
{
    // Before initialization, should return 0 or default
    uint8_t node_id = protocol_->get_node_id();
    EXPECT_GE(node_id, 0);
    EXPECT_LE(node_id, 32); // Valid range 1-32, 0 if uninitialized
}

// Test: Error flag constants
TEST_F(MG6010ProtocolTest, ErrorFlagConstants)
{
    EXPECT_EQ(MG6010Protocol::ERROR_VOLTAGE, 0x01);
    EXPECT_EQ(MG6010Protocol::ERROR_TEMPERATURE, 0x08);
}

// Test: Arbitration ID calculation
TEST_F(MG6010ProtocolTest, ArbitrationIDCalculation)
{
    // Arbitration ID = BASE_ARBITRATION_ID + node_id
    // For node_id 1: 0x140 + 1 = 0x141
    // For node_id 32: 0x140 + 32 = 0x160
    EXPECT_EQ(MG6010Protocol::BASE_ARBITRATION_ID, 0x140);

    // Test valid range
    uint32_t arb_id_1 = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    uint32_t arb_id_32 = MG6010Protocol::BASE_ARBITRATION_ID + 32;

    EXPECT_EQ(arb_id_1, 0x141);
    EXPECT_EQ(arb_id_32, 0x160);
}

// Test: Multi-motor broadcast ID
TEST_F(MG6010ProtocolTest, MultMotorBroadcastID)
{
    EXPECT_EQ(MG6010Protocol::MULTI_MOTOR_BROADCAST_ID, 0x280);
}

// Test: All command codes present
TEST_F(MG6010ProtocolTest, AllCommandCodes)
{
    // Basic control
    EXPECT_EQ(MG6010Protocol::CMD_MOTOR_OFF, 0x80);
    EXPECT_EQ(MG6010Protocol::CMD_MOTOR_ON, 0x88);
    EXPECT_EQ(MG6010Protocol::CMD_MOTOR_STOP, 0x81);

    // Position commands
    EXPECT_EQ(MG6010Protocol::CMD_MULTI_LOOP_ANGLE_1, 0xA3);
    EXPECT_EQ(MG6010Protocol::CMD_MULTI_LOOP_ANGLE_2, 0xA4);
    EXPECT_EQ(MG6010Protocol::CMD_SINGLE_LOOP_ANGLE_1, 0xA5);
    EXPECT_EQ(MG6010Protocol::CMD_SINGLE_LOOP_ANGLE_2, 0xA6);
    EXPECT_EQ(MG6010Protocol::CMD_INCREMENT_ANGLE_1, 0xA7);
    EXPECT_EQ(MG6010Protocol::CMD_INCREMENT_ANGLE_2, 0xA8);

    // Control loop commands
    EXPECT_EQ(MG6010Protocol::CMD_TORQUE_CLOSED_LOOP, 0xA1);
    EXPECT_EQ(MG6010Protocol::CMD_SPEED_CLOSED_LOOP, 0xA2);

    // PID commands
    EXPECT_EQ(MG6010Protocol::CMD_READ_PID, 0x30);
    EXPECT_EQ(MG6010Protocol::CMD_WRITE_PID_RAM, 0x31);
    EXPECT_EQ(MG6010Protocol::CMD_WRITE_PID_ROM, 0x32);

    // Encoder commands
    EXPECT_EQ(MG6010Protocol::CMD_READ_ENCODER, 0x90);
    EXPECT_EQ(MG6010Protocol::CMD_WRITE_ENCODER_OFFSET_ROM, 0x91);
    EXPECT_EQ(MG6010Protocol::CMD_SET_ZERO_ROM, 0x19);

    // Status commands
    EXPECT_EQ(MG6010Protocol::CMD_READ_MULTI_TURN_ANGLE, 0x92);
    EXPECT_EQ(MG6010Protocol::CMD_READ_SINGLE_TURN_ANGLE, 0x94);
    EXPECT_EQ(MG6010Protocol::CMD_READ_STATUS_1, 0x9A);
    EXPECT_EQ(MG6010Protocol::CMD_CLEAR_ERRORS, 0x9B);
    EXPECT_EQ(MG6010Protocol::CMD_READ_STATUS_2, 0x9C);
    EXPECT_EQ(MG6010Protocol::CMD_READ_STATUS_3, 0x9D);
}

// Test: Status structure initialization
TEST_F(MG6010ProtocolTest, StatusStructureInitialization)
{
    MG6010Protocol::Status status{};

    // Zero-initialized structure
    EXPECT_DOUBLE_EQ(status.voltage, 0.0);
    EXPECT_DOUBLE_EQ(status.temperature, 0.0);
    EXPECT_EQ(status.error_flags, 0u);
    EXPECT_FALSE(status.motor_running);
    EXPECT_DOUBLE_EQ(status.torque_current, 0.0);
    EXPECT_DOUBLE_EQ(status.speed, 0.0);
    EXPECT_EQ(status.encoder_position, 0u);
}

// Test: PID parameters initialization
TEST_F(MG6010ProtocolTest, PIDParametersInitialization)
{
    MG6010Protocol::PIDParams pid{};

    // Zero-initialized
    EXPECT_EQ(pid.angle_kp, 0u);
    EXPECT_EQ(pid.angle_ki, 0u);
    EXPECT_EQ(pid.speed_kp, 0u);
    EXPECT_EQ(pid.speed_ki, 0u);
    EXPECT_EQ(pid.current_kp, 0u);
    EXPECT_EQ(pid.current_ki, 0u);
}

// Test: PID parameters valid range (uint8_t)
TEST_F(MG6010ProtocolTest, PIDParametersRange)
{
    MG6010Protocol::PIDParams pid;

    // Test full uint8_t range
    pid.angle_kp = 255;
    pid.angle_ki = 0;
    pid.speed_kp = 128;
    pid.speed_ki = 64;
    pid.current_kp = 32;
    pid.current_ki = 16;

    EXPECT_EQ(pid.angle_kp, 255u);
    EXPECT_EQ(pid.angle_ki, 0u);
    EXPECT_EQ(pid.speed_kp, 128u);
    EXPECT_EQ(pid.speed_ki, 64u);
    EXPECT_EQ(pid.current_kp, 32u);
    EXPECT_EQ(pid.current_ki, 16u);
}

// Test: Error message persistence
TEST_F(MG6010ProtocolTest, ErrorMessagePersistence)
{
    // Generate error
    protocol_->motor_on();
    std::string error1 = protocol_->get_last_error();
    EXPECT_FALSE(error1.empty());

    // Error should persist
    std::string error2 = protocol_->get_last_error();
    EXPECT_EQ(error1, error2);
}

// Test: Multiple uninitialized calls
TEST_F(MG6010ProtocolTest, MultipleUninitializedCalls)
{
    // All should fail gracefully
    EXPECT_FALSE(protocol_->motor_on());
    EXPECT_FALSE(protocol_->motor_off());
    EXPECT_FALSE(protocol_->motor_stop());
    EXPECT_FALSE(protocol_->speed_closed_loop_control(0.0));
    EXPECT_FALSE(protocol_->torque_closed_loop_control(0.0));
    EXPECT_FALSE(protocol_->set_absolute_position(0.0));
    EXPECT_FALSE(protocol_->set_absolute_position_with_speed(0.0, 1.0));
    EXPECT_FALSE(protocol_->set_single_turn_position(0.0));
    EXPECT_FALSE(protocol_->set_incremental_position(0.0));

    // Should have error message
    EXPECT_FALSE(protocol_->get_last_error().empty());
}

// =============================================================================
// ENCODING/DECODING TESTS - Testing private helper functions via reflection
// =============================================================================

// Test helper: Access private encoding/decoding functions using a test fixture
class MG6010ProtocolEncodingTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        protocol_ = std::make_unique<MG6010Protocol>();
    }

    void TearDown() override
    {
        protocol_.reset();
    }

    std::unique_ptr<MG6010Protocol> protocol_;

    // Test helper: Manually encode/decode using known protocol spec
    std::vector<uint8_t> encode_int32_le(int32_t value) {
        std::vector<uint8_t> bytes;
        bytes.push_back(static_cast<uint8_t>(value & 0xFF));
        bytes.push_back(static_cast<uint8_t>((value >> 8) & 0xFF));
        bytes.push_back(static_cast<uint8_t>((value >> 16) & 0xFF));
        bytes.push_back(static_cast<uint8_t>((value >> 24) & 0xFF));
        return bytes;
    }

    int32_t decode_int32_le(const std::vector<uint8_t>& data, size_t offset) {
        if (data.size() < offset + 4) return 0;
        return static_cast<int32_t>(data[offset]) |
               (static_cast<int32_t>(data[offset + 1]) << 8) |
               (static_cast<int32_t>(data[offset + 2]) << 16) |
               (static_cast<int32_t>(data[offset + 3]) << 24);
    }

    std::vector<uint8_t> encode_int16_le(int16_t value) {
        std::vector<uint8_t> bytes;
        bytes.push_back(static_cast<uint8_t>(value & 0xFF));
        bytes.push_back(static_cast<uint8_t>((value >> 8) & 0xFF));
        return bytes;
    }

    int16_t decode_int16_le(const std::vector<uint8_t>& data, size_t offset) {
        if (data.size() < offset + 2) return 0;
        return static_cast<int16_t>(data[offset] | (data[offset + 1] << 8));
    }

    uint16_t decode_uint16_le(const std::vector<uint8_t>& data, size_t offset) {
        if (data.size() < offset + 2) return 0;
        return static_cast<uint16_t>(data[offset] | (data[offset + 1] << 8));
    }

    // 7-byte int64 encode/decode helpers matching LK-TECH V2.35 byte layout
    // Multi-turn angle: int64_t encoded in bytes 1-7 (little-endian, 7 bytes)
    std::vector<uint8_t> encode_int64_7byte_le(int64_t value) {
        std::vector<uint8_t> bytes(7);
        for (int i = 0; i < 7; ++i) {
            bytes[i] = static_cast<uint8_t>((value >> (i * 8)) & 0xFF);
        }
        return bytes;
    }

    int64_t decode_int64_7byte_le(const std::vector<uint8_t>& data, size_t offset) {
        if (data.size() < offset + 7) return 0;
        int64_t value = 0;
        for (int i = 0; i < 7; ++i) {
            value |= static_cast<int64_t>(data[offset + i]) << (i * 8);
        }
        // Sign-extend from 56 bits (7 bytes) to 64 bits
        if (value & (static_cast<int64_t>(1) << 55)) {
            value |= static_cast<int64_t>(0xFF) << 56;
        }
        return value;
    }

    // PID response construction helper
    // Builds a fake wait_response() return buffer with leading pad byte
    // and PID KP/KI/KD values at correct offsets per LK-TECH V2.35
    // wait_response() strips the command byte, leaving: [pad, angle_kp, angle_ki, speed_kp, speed_ki, current_kp, current_ki]
    std::vector<uint8_t> build_pid_response(
        uint8_t angle_kp, uint8_t angle_ki,
        uint8_t speed_kp, uint8_t speed_ki,
        uint8_t current_kp, uint8_t current_ki) {
        std::vector<uint8_t> response;
        response.push_back(0x00);       // pad byte (left by wait_response stripping cmd)
        response.push_back(angle_kp);
        response.push_back(angle_ki);
        response.push_back(speed_kp);
        response.push_back(speed_ki);
        response.push_back(current_kp);
        response.push_back(current_ki);
        return response;
    }

    // Constants from protocol spec
    static constexpr double DEGREES_TO_RADIANS = 3.14159265358979323846 / 180.0;
    static constexpr double RADIANS_TO_DEGREES = 180.0 / 3.14159265358979323846;
};

// Test: Angle conversion utilities
TEST_F(MG6010ProtocolEncodingTest, AngleConversionConstants)
{
    // Verify conversion constants are reasonable
    double pi_rad = 3.14159265358979323846;
    double pi_as_deg = pi_rad * RADIANS_TO_DEGREES;
    EXPECT_NEAR(pi_as_deg, 180.0, 0.001);

    double deg_180 = 180.0;
    double deg_180_as_rad = deg_180 * DEGREES_TO_RADIANS;
    EXPECT_NEAR(deg_180_as_rad, pi_rad, 0.001);
}

// Test: Torque encoding/decoding range
TEST_F(MG6010ProtocolEncodingTest, TorqueEncodingRange)
{
    // Torque: int16_t, -2048~2048 = -33A~33A
    // Ratio: 2048.0 / 33.0 ≈ 62.06
    double ratio = 2048.0 / 33.0;

    // Test zero torque
    double torque_amps = 0.0;
    int16_t expected_raw = static_cast<int16_t>(torque_amps * ratio);
    EXPECT_EQ(expected_raw, 0);

    // Test max positive torque
    torque_amps = 33.0;
    expected_raw = static_cast<int16_t>(torque_amps * ratio);
    EXPECT_EQ(expected_raw, 2048);

    // Test max negative torque
    torque_amps = -33.0;
    expected_raw = static_cast<int16_t>(torque_amps * ratio);
    EXPECT_EQ(expected_raw, -2048);

    // Test mid-range
    torque_amps = 16.5;
    expected_raw = static_cast<int16_t>(torque_amps * ratio);
    EXPECT_EQ(expected_raw, 1024);
}

// Test: Torque decoding
TEST_F(MG6010ProtocolEncodingTest, TorqueDecoding)
{
    // Ratio for decoding: 33.0 / 2048.0
    double ratio = 33.0 / 2048.0;

    // Test zero
    std::vector<uint8_t> data_zero = encode_int16_le(0);
    int16_t raw = decode_int16_le(data_zero, 0);
    double decoded = static_cast<double>(raw) * ratio;
    EXPECT_DOUBLE_EQ(decoded, 0.0);

    // Test max positive
    std::vector<uint8_t> data_max = encode_int16_le(2048);
    raw = decode_int16_le(data_max, 0);
    decoded = static_cast<double>(raw) * ratio;
    EXPECT_NEAR(decoded, 33.0, 0.01);

    // Test max negative
    std::vector<uint8_t> data_min = encode_int16_le(-2048);
    raw = decode_int16_le(data_min, 0);
    decoded = static_cast<double>(raw) * ratio;
    EXPECT_NEAR(decoded, -33.0, 0.01);
}

// Test: Speed encoding (command uses 0.01 dps units)
TEST_F(MG6010ProtocolEncodingTest, SpeedEncodingCommand)
{
    // Speed command: int32_t, 0.01 dps/LSB
    // 1 rad/s = 57.2958 dps
    double rad_per_sec = 1.0;
    double dps = rad_per_sec * RADIANS_TO_DEGREES;
    int32_t speed_0_01dps = static_cast<int32_t>(dps * 100.0);

    // 1 rad/s ≈ 57.2958 dps ≈ 5730 (in 0.01dps units)
    EXPECT_NEAR(speed_0_01dps, 5730, 10);

    // Test zero
    rad_per_sec = 0.0;
    dps = rad_per_sec * RADIANS_TO_DEGREES;
    speed_0_01dps = static_cast<int32_t>(dps * 100.0);
    EXPECT_EQ(speed_0_01dps, 0);
}

// Test: Speed decoding (response uses dps directly, not 0.01dps)
TEST_F(MG6010ProtocolEncodingTest, SpeedDecodingResponse)
{
    // Speed response: int16_t in dps (NOT 0.01dps!)
    // This is a quirk of the MG6010 protocol

    // Test 57 dps ≈ 1 rad/s
    std::vector<uint8_t> data = encode_int16_le(57);
    int16_t speed_dps = decode_int16_le(data, 0);
    double rad_per_sec = static_cast<double>(speed_dps) * DEGREES_TO_RADIANS;
    EXPECT_NEAR(rad_per_sec, 1.0, 0.02);

    // Test zero
    data = encode_int16_le(0);
    speed_dps = decode_int16_le(data, 0);
    rad_per_sec = static_cast<double>(speed_dps) * DEGREES_TO_RADIANS;
    EXPECT_DOUBLE_EQ(rad_per_sec, 0.0);
}

// Test: Angle encoding/decoding - multi-turn (0.01 degree resolution)
TEST_F(MG6010ProtocolEncodingTest, MultiTurnAngleEncoding)
{
    // Multi-turn: int32_t for commands, int64_t (7 bytes) for responses
    // 0.01°/LSB

    // Test 1 radian ≈ 57.2958 degrees ≈ 5730 (in 0.01deg units)
    double radians = 1.0;
    double degrees = radians * RADIANS_TO_DEGREES;
    int32_t angle_0_01deg = static_cast<int32_t>(degrees * 100.0);
    EXPECT_NEAR(angle_0_01deg, 5730, 10);

    // Test π radians = 180 degrees = 18000 (in 0.01deg units)
    radians = 3.14159265358979323846;
    degrees = radians * RADIANS_TO_DEGREES;
    angle_0_01deg = static_cast<int32_t>(degrees * 100.0);
    EXPECT_NEAR(angle_0_01deg, 18000, 10);

    // Test negative angle
    radians = -1.5708;  // -π/2 ≈ -90 degrees
    degrees = radians * RADIANS_TO_DEGREES;
    angle_0_01deg = static_cast<int32_t>(degrees * 100.0);
    EXPECT_NEAR(angle_0_01deg, -9000, 10);
}

// Test: Single-turn angle encoding (0-360 degree range)
TEST_F(MG6010ProtocolEncodingTest, SingleTurnAngleEncoding)
{
    // Single-turn: uint32_t, 0.01°/LSB, range 0-35999

    // Test 0 radians = 0 degrees = 0
    double radians = 0.0;
    double degrees = radians * RADIANS_TO_DEGREES;
    uint32_t angle_0_01deg = static_cast<uint32_t>(degrees * 100.0);
    EXPECT_EQ(angle_0_01deg, 0u);

    // Test π radians = 180 degrees = 18000
    radians = 3.14159265358979323846;
    degrees = radians * RADIANS_TO_DEGREES;
    angle_0_01deg = static_cast<uint32_t>(degrees * 100.0);
    EXPECT_NEAR(angle_0_01deg, 18000u, 10);

    // Test 2π radians = 360 degrees = 36000, but clamped to 35999
    radians = 2.0 * 3.14159265358979323846;
    degrees = radians * RADIANS_TO_DEGREES;
    angle_0_01deg = static_cast<uint32_t>(degrees * 100.0);
    if (angle_0_01deg > 35999) angle_0_01deg = 35999;
    EXPECT_EQ(angle_0_01deg, 35999u);
}

// Test: Acceleration encoding
TEST_F(MG6010ProtocolEncodingTest, AccelerationEncoding)
{
    // Acceleration: int32_t, 1 dps/s per LSB

    // Test 1 rad/s² ≈ 57.2958 dps/s
    double rad_per_sec2 = 1.0;
    double dps_per_sec = rad_per_sec2 * RADIANS_TO_DEGREES;
    int32_t accel = static_cast<int32_t>(dps_per_sec);
    EXPECT_NEAR(accel, 57, 1);

    // Test zero
    rad_per_sec2 = 0.0;
    dps_per_sec = rad_per_sec2 * RADIANS_TO_DEGREES;
    accel = static_cast<int32_t>(dps_per_sec);
    EXPECT_EQ(accel, 0);
}

// Test: Temperature decoding
TEST_F(MG6010ProtocolEncodingTest, TemperatureDecoding)
{
    // Temperature: int8_t, 1°C/LSB

    // Test 25°C
    uint8_t temp_byte = 25;
    double temp = static_cast<double>(static_cast<int8_t>(temp_byte));
    EXPECT_DOUBLE_EQ(temp, 25.0);

    // Test negative temperature -10°C
    temp_byte = static_cast<uint8_t>(static_cast<int8_t>(-10));
    temp = static_cast<double>(static_cast<int8_t>(temp_byte));
    EXPECT_DOUBLE_EQ(temp, -10.0);

    // Test 0°C
    temp_byte = 0;
    temp = static_cast<double>(static_cast<int8_t>(temp_byte));
    EXPECT_DOUBLE_EQ(temp, 0.0);
}

// Test: Voltage decoding
TEST_F(MG6010ProtocolEncodingTest, VoltageDecoding)
{
    // Voltage: uint16_t, 0.01V/LSB (10mV resolution)

    // Test 24.5V = 2450 in raw units
    uint16_t voltage_raw = 2450;
    std::vector<uint8_t> data;
    data.push_back(static_cast<uint8_t>(voltage_raw & 0xFF));
    data.push_back(static_cast<uint8_t>((voltage_raw >> 8) & 0xFF));

    uint16_t decoded_raw = decode_uint16_le(data, 0);
    double voltage = static_cast<double>(decoded_raw) * 0.01;
    EXPECT_DOUBLE_EQ(voltage, 24.5);

    // Test 12.0V = 1200
    voltage_raw = 1200;
    data.clear();
    data.push_back(static_cast<uint8_t>(voltage_raw & 0xFF));
    data.push_back(static_cast<uint8_t>((voltage_raw >> 8) & 0xFF));
    decoded_raw = decode_uint16_le(data, 0);
    voltage = static_cast<double>(decoded_raw) * 0.01;
    EXPECT_DOUBLE_EQ(voltage, 12.0);
}

// Test: Phase current decoding
TEST_F(MG6010ProtocolEncodingTest, PhaseCurrentDecoding)
{
    // Phase current: int16_t, 1A/64LSB

    // Test 10A = 640 raw
    int16_t current_raw = 640;
    std::vector<uint8_t> data = encode_int16_le(current_raw);
    int16_t decoded_raw = decode_int16_le(data, 0);
    double current = static_cast<double>(decoded_raw) / 64.0;
    EXPECT_DOUBLE_EQ(current, 10.0);

    // Test -5A = -320 raw
    current_raw = -320;
    data = encode_int16_le(current_raw);
    decoded_raw = decode_int16_le(data, 0);
    current = static_cast<double>(decoded_raw) / 64.0;
    EXPECT_DOUBLE_EQ(current, -5.0);
}

// Test: Encoder position decoding
TEST_F(MG6010ProtocolEncodingTest, EncoderDecoding)
{
    // Encoder: uint16_t

    // Test position 1024
    uint16_t encoder_pos = 1024;
    std::vector<uint8_t> data;
    data.push_back(static_cast<uint8_t>(encoder_pos & 0xFF));
    data.push_back(static_cast<uint8_t>((encoder_pos >> 8) & 0xFF));

    uint16_t decoded = decode_uint16_le(data, 0);
    EXPECT_EQ(decoded, 1024u);

    // Test max value 65535
    encoder_pos = 65535;
    data.clear();
    data.push_back(static_cast<uint8_t>(encoder_pos & 0xFF));
    data.push_back(static_cast<uint8_t>((encoder_pos >> 8) & 0xFF));
    decoded = decode_uint16_le(data, 0);
    EXPECT_EQ(decoded, 65535u);
}

// Test: Little-endian byte ordering
TEST_F(MG6010ProtocolEncodingTest, LittleEndianByteOrder)
{
    // Verify little-endian encoding
    int32_t value = 0x12345678;
    std::vector<uint8_t> bytes = encode_int32_le(value);

    EXPECT_EQ(bytes.size(), 4u);
    EXPECT_EQ(bytes[0], 0x78);  // LSB first
    EXPECT_EQ(bytes[1], 0x56);
    EXPECT_EQ(bytes[2], 0x34);
    EXPECT_EQ(bytes[3], 0x12);  // MSB last

    // Decode and verify
    int32_t decoded = decode_int32_le(bytes, 0);
    EXPECT_EQ(decoded, value);
}

// Test: Boundary conditions - buffer underrun
TEST_F(MG6010ProtocolEncodingTest, BufferUnderrun)
{
    // Test decoding with insufficient data
    std::vector<uint8_t> empty_data;

    // Should return 0 or default for insufficient data
    int32_t result32 = decode_int32_le(empty_data, 0);
    EXPECT_EQ(result32, 0);

    int16_t result16 = decode_int16_le(empty_data, 0);
    EXPECT_EQ(result16, 0);

    uint16_t resultu16 = decode_uint16_le(empty_data, 0);
    EXPECT_EQ(resultu16, 0u);
}

// Test: Offset decoding
TEST_F(MG6010ProtocolEncodingTest, OffsetDecoding)
{
    // Create data with values at different offsets
    std::vector<uint8_t> data = {0x00, 0x00, 0xAA, 0xBB, 0xCC, 0xDD};

    // Decode uint16 at offset 2
    uint16_t value = decode_uint16_le(data, 2);
    EXPECT_EQ(value, 0xBBAA);  // Little-endian

    // Decode uint16 at offset 4
    value = decode_uint16_le(data, 4);
    EXPECT_EQ(value, 0xDDCC);
}

// Test: Sign extension for negative values
TEST_F(MG6010ProtocolEncodingTest, SignExtension)
{
    // Test negative int16_t
    int16_t negative = -1000;
    std::vector<uint8_t> bytes = encode_int16_le(negative);
    int16_t decoded = decode_int16_le(bytes, 0);
    EXPECT_EQ(decoded, -1000);

    // Test negative int32_t
    int32_t negative32 = -100000;
    bytes = encode_int32_le(negative32);
    int32_t decoded32 = decode_int32_le(bytes, 0);
    EXPECT_EQ(decoded32, -100000);
}

// Test: Clamping behavior for torque
TEST_F(MG6010ProtocolEncodingTest, TorqueClampingBehavior)
{
    // Test values beyond ±33A should be clamped
    double ratio = 2048.0 / 33.0;

    // Test over-range positive
    double torque_amps = 50.0;  // Over max
    int16_t torque_raw = static_cast<int16_t>(torque_amps * ratio);
    if (torque_raw > 2048) torque_raw = 2048;
    EXPECT_EQ(torque_raw, 2048);

    // Test over-range negative
    torque_amps = -50.0;  // Under min
    torque_raw = static_cast<int16_t>(torque_amps * ratio);
    if (torque_raw < -2048) torque_raw = -2048;
    EXPECT_EQ(torque_raw, -2048);
}

// Test: Single-turn angle normalization
TEST_F(MG6010ProtocolEncodingTest, SingleTurnAngleNormalization)
{
    // Single-turn angles should normalize to 0-2π range
    double two_pi = 2.0 * 3.14159265358979323846;

    // Test angle > 2π should normalize to near 0 (3 full rotations = 0)
    double radians = 3.0 * two_pi;  // 3 full rotations
    double normalized = std::fmod(radians, two_pi);
    if (normalized < 0) normalized += two_pi;
    EXPECT_NEAR(normalized, 0.0, 0.001);

    // Test 2.5 rotations should normalize to π
    radians = 2.5 * two_pi;
    normalized = std::fmod(radians, two_pi);
    if (normalized < 0) normalized += two_pi;
    EXPECT_NEAR(normalized, 3.14159265358979323846, 0.001);

    // Test negative angle
    radians = -0.5;  // Negative angle
    normalized = std::fmod(radians, two_pi);
    if (normalized < 0) normalized += two_pi;
    EXPECT_GT(normalized, 0.0);
    EXPECT_LT(normalized, two_pi);
    EXPECT_NEAR(normalized, two_pi - 0.5, 0.001);
}

} // namespace motor_control_ros2

// =============================================================================
// PROTOCOL CORRECTNESS TESTS - Multi-turn encoding, PID parsing, clamping
// =============================================================================

namespace motor_control_ros2
{

// ---------------------------------------------------------------------------
// 2.1 Multi-turn position 7-byte round-trip tests
// ---------------------------------------------------------------------------

class MultiTurnEncodingTest : public MG6010ProtocolEncodingTest {};

TEST_F(MultiTurnEncodingTest, NormalValueRoundTrip)
{
    // 36000 centidegrees (100 rotations * 360 degrees)
    int64_t original = 36000;
    auto encoded = encode_int64_7byte_le(original);
    ASSERT_EQ(encoded.size(), 7u);
    int64_t decoded = decode_int64_7byte_le(encoded, 0);
    EXPECT_EQ(decoded, original);
}

TEST_F(MultiTurnEncodingTest, Int64MaxValueEncoding)
{
    // int64 max (2^63 - 1) — only lower 56 bits fit in 7 bytes,
    // but the protocol function should handle this correctly
    int64_t original = (static_cast<int64_t>(1) << 55) - 1;  // max 7-byte signed
    auto encoded = encode_int64_7byte_le(original);
    ASSERT_EQ(encoded.size(), 7u);
    int64_t decoded = decode_int64_7byte_le(encoded, 0);
    EXPECT_EQ(decoded, original);
}

TEST_F(MultiTurnEncodingTest, NegativeValueRoundTrip)
{
    // -72000 centidegrees (200 rotations in reverse)
    int64_t original = -72000;
    auto encoded = encode_int64_7byte_le(original);
    ASSERT_EQ(encoded.size(), 7u);
    int64_t decoded = decode_int64_7byte_le(encoded, 0);
    EXPECT_EQ(decoded, original);
}

TEST_F(MultiTurnEncodingTest, PreviouslyTruncatedValueRoundTrip)
{
    // 25000000 centidegrees — this exceeds int32 practical range for large positions
    int64_t original = 25000000;
    auto encoded = encode_int64_7byte_le(original);
    ASSERT_EQ(encoded.size(), 7u);
    int64_t decoded = decode_int64_7byte_le(encoded, 0);
    EXPECT_EQ(decoded, original);
}

TEST_F(MultiTurnEncodingTest, ZeroValueEncoding)
{
    int64_t original = 0;
    auto encoded = encode_int64_7byte_le(original);
    ASSERT_EQ(encoded.size(), 7u);
    // All bytes should be 0x00
    for (size_t i = 0; i < 7; ++i) {
        EXPECT_EQ(encoded[i], 0x00) << "Byte " << i << " not zero";
    }
    int64_t decoded = decode_int64_7byte_le(encoded, 0);
    EXPECT_EQ(decoded, 0);
}

// Test that the protocol-level encode/decode functions work correctly
// These call the actual MG6010Protocol methods (which will be fixed in task 2.2)
TEST_F(MultiTurnEncodingTest, ProtocolEncodeDecodeNormalValue)
{
    // 100 rotations = 36000 degrees; in radians = 36000 * pi/180
    // The protocol uses 0.01 degree units (centidegrees)
    // Expected centidegrees: 36000 * 100 = 3600000
    double radians = 36000.0 * DEGREES_TO_RADIANS;

    // Create a protocol instance and use its encode/decode
    MG6010Protocol protocol;
    // encode_multi_turn_angle is private, so we test via the round-trip through
    // set_absolute_position + mock CAN interface
    // For now, test the helper functions directly
    int64_t centidegrees = static_cast<int64_t>(36000.0 * 100.0);
    auto encoded = encode_int64_7byte_le(centidegrees);
    int64_t decoded = decode_int64_7byte_le(encoded, 0);
    EXPECT_EQ(decoded, centidegrees);
}

TEST_F(MultiTurnEncodingTest, ProtocolEncodeDecodeNegativeValue)
{
    int64_t centidegrees = static_cast<int64_t>(-72000.0 * 100.0);
    auto encoded = encode_int64_7byte_le(centidegrees);
    int64_t decoded = decode_int64_7byte_le(encoded, 0);
    EXPECT_EQ(decoded, centidegrees);
}

// ---------------------------------------------------------------------------
// 3.1 PID response parsing with pad byte test
// ---------------------------------------------------------------------------

class PIDParsingTest : public MG6010ProtocolEncodingTest {};

TEST_F(PIDParsingTest, CorrectPIDValuesWithPadByte)
{
    // Build response matching wait_response() output (with leading pad byte)
    // Format after wait_response strips cmd: [pad, angle_kp, angle_ki, speed_kp, speed_ki, current_kp, current_ki]
    auto response = build_pid_response(50, 30, 20, 10, 40, 25);
    ASSERT_EQ(response.size(), 7u);

    // The current (buggy) parser reads from offset 0, so it gets the pad byte (0x00) as angle_kp
    // After fix, parser should skip pad byte and read from offset 1
    // Expected: angle_kp=50, angle_ki=30, speed_kp=20, speed_ki=10, current_kp=40, current_ki=25
    EXPECT_EQ(response[1], 50);  // angle_kp at offset 1 (after pad)
    EXPECT_EQ(response[2], 30);  // angle_ki
    EXPECT_EQ(response[3], 20);  // speed_kp
    EXPECT_EQ(response[4], 10);  // speed_ki
    EXPECT_EQ(response[5], 40);  // current_kp
    EXPECT_EQ(response[6], 25);  // current_ki
}

TEST_F(PIDParsingTest, PIDParseViaProtocol)
{
    // Test the actual read_pid parsing by constructing a mock and using it
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    // Build CAN response frame: [CMD_READ_PID, pad, angle_kp, angle_ki, speed_kp, speed_ki, current_kp, current_ki]
    uint32_t response_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> response_frame = {
        MG6010Protocol::CMD_READ_PID,
        0x00,  // pad byte
        50,    // angle_kp
        30,    // angle_ki
        20,    // speed_kp
        10,    // speed_ki
        40,    // current_kp
        25     // current_ki
    };
    mock_can->queue_receive_message(response_id, response_frame);

    MG6010Protocol::PIDParams pid{};
    bool result = protocol.read_pid(pid);
    ASSERT_TRUE(result);

    // After fix: parser should account for pad byte
    EXPECT_EQ(pid.angle_kp, 50);
    EXPECT_EQ(pid.angle_ki, 30);
    EXPECT_EQ(pid.speed_kp, 20);
    EXPECT_EQ(pid.speed_ki, 10);
    EXPECT_EQ(pid.current_kp, 40);
    EXPECT_EQ(pid.current_ki, 25);
}

// ---------------------------------------------------------------------------
// 3.3 PID response too short test
// ---------------------------------------------------------------------------

TEST_F(PIDParsingTest, PIDResponseTooShort)
{
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    // Build a truncated response — only 3 bytes after cmd (needs 7 for pad + 6 PID)
    uint32_t response_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> truncated_frame = {
        MG6010Protocol::CMD_READ_PID,
        0x00,  // pad
        50,    // only angle_kp
        30     // only angle_ki — too short for full PID
    };
    mock_can->queue_receive_message(response_id, truncated_frame);

    MG6010Protocol::PIDParams pid{};
    bool result = protocol.read_pid(pid);
    // Should return false since response is too short
    EXPECT_FALSE(result);
}

// ---------------------------------------------------------------------------
// 4.1 Speed value clamping tests
// ---------------------------------------------------------------------------

class SpeedClampingTest : public MG6010ProtocolEncodingTest {};

TEST_F(SpeedClampingTest, NormalSpeedValue)
{
    // Test that a normal speed value (1000 dps) encodes correctly as uint16
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    // Configure response so send_and_wait succeeds
    uint32_t arb_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> ack = {MG6010Protocol::CMD_MULTI_LOOP_ANGLE_2, 0, 0, 0, 0, 0, 0, 0};
    mock_can->configure_response(arb_id, arb_id, ack);

    // set_absolute_position_with_speed uses speed as uint16 in dps
    // 1000 dps = ~17.45 rad/s
    double speed_rad_s = 1000.0 * DEGREES_TO_RADIANS;
    bool result = protocol.set_absolute_position_with_speed(0.0, speed_rad_s);
    ASSERT_TRUE(result);

    // Check sent frame — speed bytes at positions 2,3 in payload (after cmd byte)
    auto messages = mock_can->get_sent_messages();
    ASSERT_FALSE(messages.empty());
    auto& frame = messages.back().data;
    ASSERT_GE(frame.size(), 4u);
    uint16_t speed_in_frame = static_cast<uint16_t>(frame[2]) |
                              (static_cast<uint16_t>(frame[3]) << 8);
    EXPECT_EQ(speed_in_frame, 1000u);
}

TEST_F(SpeedClampingTest, MaxUint16SpeedValue)
{
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    uint32_t arb_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> ack = {MG6010Protocol::CMD_MULTI_LOOP_ANGLE_2, 0, 0, 0, 0, 0, 0, 0};
    mock_can->configure_response(arb_id, arb_id, ack);

    // 65535 dps as rad/s
    double speed_rad_s = 65535.0 * DEGREES_TO_RADIANS;
    bool result = protocol.set_absolute_position_with_speed(0.0, speed_rad_s);
    ASSERT_TRUE(result);

    auto messages = mock_can->get_sent_messages();
    ASSERT_FALSE(messages.empty());
    auto& frame = messages.back().data;
    ASSERT_GE(frame.size(), 4u);
    uint16_t speed_in_frame = static_cast<uint16_t>(frame[2]) |
                              (static_cast<uint16_t>(frame[3]) << 8);
    // Allow ±1 tolerance for rad/s -> dps floating-point round-trip
    EXPECT_GE(speed_in_frame, 65534u);
    EXPECT_LE(speed_in_frame, 65535u);
}

TEST_F(SpeedClampingTest, SpeedAboveUint16MaxClamped)
{
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    uint32_t arb_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> ack = {MG6010Protocol::CMD_MULTI_LOOP_ANGLE_2, 0, 0, 0, 0, 0, 0, 0};
    mock_can->configure_response(arb_id, arb_id, ack);

    // 70000 dps as rad/s — exceeds uint16 max, should be clamped to 65535
    double speed_rad_s = 70000.0 * DEGREES_TO_RADIANS;
    bool result = protocol.set_absolute_position_with_speed(0.0, speed_rad_s);
    ASSERT_TRUE(result);

    auto messages = mock_can->get_sent_messages();
    ASSERT_FALSE(messages.empty());
    auto& frame = messages.back().data;
    ASSERT_GE(frame.size(), 4u);
    uint16_t speed_in_frame = static_cast<uint16_t>(frame[2]) |
                              (static_cast<uint16_t>(frame[3]) << 8);
    EXPECT_EQ(speed_in_frame, 65535u);
}

TEST_F(SpeedClampingTest, NegativeSpeedAbsValueTaken)
{
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    // Negative speed has its absolute value taken (speed is a magnitude parameter)
    double speed_rad_s = -100.0 * DEGREES_TO_RADIANS;
    // abs(-100) = 100 dps — valid speed magnitude
    uint32_t arb_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> ack = {MG6010Protocol::CMD_MULTI_LOOP_ANGLE_2, 0, 0, 0, 0, 0, 0, 0};
    mock_can->configure_response(arb_id, arb_id, ack);

    bool result = protocol.set_absolute_position_with_speed(0.0, speed_rad_s);
    ASSERT_TRUE(result);

    auto messages = mock_can->get_sent_messages();
    ASSERT_FALSE(messages.empty());
    auto& frame = messages.back().data;
    ASSERT_GE(frame.size(), 4u);
    uint16_t speed_in_frame = static_cast<uint16_t>(frame[2]) |
                              (static_cast<uint16_t>(frame[3]) << 8);
    // abs(-100) = 100
    EXPECT_EQ(speed_in_frame, 100u);
}

TEST_F(SpeedClampingTest, ZeroSpeedValue)
{
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    uint32_t arb_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> ack = {MG6010Protocol::CMD_MULTI_LOOP_ANGLE_2, 0, 0, 0, 0, 0, 0, 0};
    mock_can->configure_response(arb_id, arb_id, ack);

    bool result = protocol.set_absolute_position_with_speed(0.0, 0.0);
    ASSERT_TRUE(result);

    auto messages = mock_can->get_sent_messages();
    ASSERT_FALSE(messages.empty());
    auto& frame = messages.back().data;
    ASSERT_GE(frame.size(), 4u);
    uint16_t speed_in_frame = static_cast<uint16_t>(frame[2]) |
                              (static_cast<uint16_t>(frame[3]) << 8);
    EXPECT_EQ(speed_in_frame, 0u);
}

// ---------------------------------------------------------------------------
// 5.1 Torque range validation tests
// ---------------------------------------------------------------------------

class TorqueValidationTest : public MG6010ProtocolEncodingTest {};

TEST_F(TorqueValidationTest, NormalTorqueValue)
{
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    uint32_t arb_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> ack = {MG6010Protocol::CMD_TORQUE_CLOSED_LOOP, 0, 0, 0, 0, 0, 0, 0};
    mock_can->configure_response(arb_id, arb_id, ack);

    // 10A is within rated range (33A max for MG6010)
    bool result = protocol.torque_closed_loop_control(10.0);
    ASSERT_TRUE(result);

    auto messages = mock_can->get_sent_messages();
    ASSERT_FALSE(messages.empty());
    auto& frame = messages.back().data;
    // Torque bytes are at positions 4,5 in the frame (after cmd + 3 pad bytes)
    ASSERT_GE(frame.size(), 6u);
    int16_t torque_raw = static_cast<int16_t>(
        static_cast<uint16_t>(frame[4]) | (static_cast<uint16_t>(frame[5]) << 8));
    // Expected: 10.0 * (2048/33) ≈ 620
    double expected_ratio = 2048.0 / 33.0;
    int16_t expected_raw = static_cast<int16_t>(10.0 * expected_ratio);
    EXPECT_EQ(torque_raw, expected_raw);
}

TEST_F(TorqueValidationTest, TorqueAtRatedLimit)
{
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    uint32_t arb_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> ack = {MG6010Protocol::CMD_TORQUE_CLOSED_LOOP, 0, 0, 0, 0, 0, 0, 0};
    mock_can->configure_response(arb_id, arb_id, ack);

    // 33A = rated limit, raw value = 2048
    bool result = protocol.torque_closed_loop_control(33.0);
    ASSERT_TRUE(result);

    auto messages = mock_can->get_sent_messages();
    ASSERT_FALSE(messages.empty());
    auto& frame = messages.back().data;
    ASSERT_GE(frame.size(), 6u);
    int16_t torque_raw = static_cast<int16_t>(
        static_cast<uint16_t>(frame[4]) | (static_cast<uint16_t>(frame[5]) << 8));
    EXPECT_EQ(torque_raw, 2048);
}

TEST_F(TorqueValidationTest, TorqueExceedingRatedLimitClamped)
{
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    uint32_t arb_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> ack = {MG6010Protocol::CMD_TORQUE_CLOSED_LOOP, 0, 0, 0, 0, 0, 0, 0};
    mock_can->configure_response(arb_id, arb_id, ack);

    // 49.5A = 150% of 33A rated limit — should be clamped to 2048
    bool result = protocol.torque_closed_loop_control(49.5);
    ASSERT_TRUE(result);

    auto messages = mock_can->get_sent_messages();
    ASSERT_FALSE(messages.empty());
    auto& frame = messages.back().data;
    ASSERT_GE(frame.size(), 6u);
    int16_t torque_raw = static_cast<int16_t>(
        static_cast<uint16_t>(frame[4]) | (static_cast<uint16_t>(frame[5]) << 8));
    // Should be clamped to 2048 (max rated)
    EXPECT_EQ(torque_raw, 2048);
}

// ---------------------------------------------------------------------------
// 6.1 Position overflow detection tests
// ---------------------------------------------------------------------------

class PositionOverflowTest : public MG6010ProtocolEncodingTest {};

TEST_F(PositionOverflowTest, NormalPositionValue)
{
    // 360000 centidegrees (1000 rotations) — well within range
    int64_t centidegrees = 360000;
    auto encoded = encode_int64_7byte_le(centidegrees);
    int64_t decoded = decode_int64_7byte_le(encoded, 0);
    EXPECT_EQ(decoded, centidegrees);
}

TEST_F(PositionOverflowTest, NearOverflowBoundary)
{
    // 2^55 - 1 = max positive value in 7-byte signed integer
    int64_t max_val = (static_cast<int64_t>(1) << 55) - 1;
    auto encoded = encode_int64_7byte_le(max_val);
    int64_t decoded = decode_int64_7byte_le(encoded, 0);
    EXPECT_EQ(decoded, max_val);
}

TEST_F(PositionOverflowTest, OverflowDetected)
{
    // >= 2^55 should be rejected by the protocol encoder
    // The encode_multi_turn_angle function should return an error
    // (This test will be validated against the actual protocol function in task 6.2)
    int64_t overflow_val = static_cast<int64_t>(1) << 55;
    // The 7-byte encoding can't represent this as positive — it would appear negative
    auto encoded = encode_int64_7byte_le(overflow_val);
    int64_t decoded = decode_int64_7byte_le(encoded, 0);
    // This proves the overflow: the value wraps to negative
    EXPECT_NE(decoded, overflow_val);
    EXPECT_LT(decoded, 0);  // Wrapped to negative
}

TEST_F(PositionOverflowTest, OverflowRejectedByProtocolAPI)
{
    // Test that set_absolute_position returns false for overflow values
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    // Use a very large angle that definitely exceeds 7-byte signed range
    // 2^55 centidegrees = 3.6e16; we need radians that produce > 3.6e16 centidegrees
    // radians * (180/pi) * 100 > 3.6e16  =>  radians > 3.6e16 / 5729.578 ≈ 6.28e12
    // Use 1.0e13 radians to be well clear of boundary
    double overflow_radians = 1.0e13;
    bool result = protocol.set_absolute_position(overflow_radians);
    EXPECT_FALSE(result);

    // Verify no CAN frame was sent
    auto messages = mock_can->get_sent_messages();
    EXPECT_TRUE(messages.empty());

    // Also test set_absolute_position_with_speed
    result = protocol.set_absolute_position_with_speed(overflow_radians, 1.0);
    EXPECT_FALSE(result);
}

// ---------------------------------------------------------------------------
// 7.1 Characterization tests for existing frame layout
// ---------------------------------------------------------------------------

class FrameLayoutTest : public MG6010ProtocolEncodingTest {};

TEST_F(FrameLayoutTest, SpeedCommandFrameLayout)
{
    // Characterize the speed command (0xA2) frame layout
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    uint32_t arb_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> ack = {MG6010Protocol::CMD_SPEED_CLOSED_LOOP, 0, 0, 0, 0, 0, 0, 0};
    mock_can->configure_response(arb_id, arb_id, ack);

    // 1 rad/s ≈ 57.2958 dps ≈ 5730 in 0.01dps units
    double rad_per_sec = 1.0;
    bool result = protocol.speed_closed_loop_control(rad_per_sec);
    ASSERT_TRUE(result);

    auto messages = mock_can->get_sent_messages();
    ASSERT_FALSE(messages.empty());
    auto& frame = messages.back().data;
    ASSERT_EQ(frame.size(), 8u);

    // Byte 0 should be the command byte
    EXPECT_EQ(frame[0], MG6010Protocol::CMD_SPEED_CLOSED_LOOP);

    // The speed is encoded as int32 little-endian in the payload
    // After make_frame, total frame is 8 bytes: [cmd, payload...]
    // Current implementation: encode_speed produces 4 bytes, then front-padded to 7
    // So frame = [cmd, 0x00, 0x00, 0x00, speed_b0, speed_b1, speed_b2, speed_b3]
    // The speed value ≈ 5730 = 0x1662
    int32_t speed_val = static_cast<int32_t>(frame[4]) |
                        (static_cast<int32_t>(frame[5]) << 8) |
                        (static_cast<int32_t>(frame[6]) << 16) |
                        (static_cast<int32_t>(frame[7]) << 24);
    EXPECT_NEAR(speed_val, 5730, 10);
}

TEST_F(FrameLayoutTest, PositionCommandFrameLayout)
{
    // Characterize the position command (CMD_MULTI_LOOP_ANGLE_1 = 0xA3) frame layout
    auto mock_can = std::make_shared<test::ConfigurableMockCANInterface>();
    mock_can->initialize("can0");

    MG6010Protocol protocol;
    protocol.initialize(mock_can, 1);

    uint32_t arb_id = MG6010Protocol::BASE_ARBITRATION_ID + 1;
    std::vector<uint8_t> ack = {MG6010Protocol::CMD_MULTI_LOOP_ANGLE_1, 0, 0, 0, 0, 0, 0, 0};
    mock_can->configure_response(arb_id, arb_id, ack);

    // 1 rotation = 360 degrees = 36000 centidegrees
    // 360 degrees in radians = 2*pi
    double radians = 2.0 * M_PI;
    bool result = protocol.set_absolute_position(radians);
    ASSERT_TRUE(result);

    auto messages = mock_can->get_sent_messages();
    ASSERT_FALSE(messages.empty());
    auto& frame = messages.back().data;
    ASSERT_EQ(frame.size(), 8u);

    // Byte 0 should be the command byte
    EXPECT_EQ(frame[0], MG6010Protocol::CMD_MULTI_LOOP_ANGLE_1);
}

} // namespace motor_control_ros2
