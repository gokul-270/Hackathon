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

#pragma once

#include <cstdint>

namespace motor_control_ros2
{
namespace test
{

// =============================================================================
// Motor Simulation Configuration (Task 1.1)
// =============================================================================

/**
 * @brief Configuration parameters for motor physics simulation.
 *
 * Controls the simulated motor's kinematic limits, first-order position
 * response, and thermal model. All defaults match the MG6010/MG6012
 * servo characteristics used on the Pragati cotton-picking arm.
 */
struct MotorSimConfig
{
  double position_min_deg = -3600.0;         // multi-turn position limit, lower (degrees)
  double position_max_deg = 3600.0;          // multi-turn position limit, upper (degrees)
  double velocity_max_dps = 360.0;           // max velocity (degrees per second)
  double settling_time_constant_ms = 200.0;  // first-order time constant (milliseconds)
  double thermal_time_constant_s = 60.0;     // thermal cooling time constant (seconds)
  double thermal_gain = 0.001;               // temperature rise per (current^2 * dt)
  double ambient_temperature_c = 25.0;       // ambient temperature (Celsius)
  double over_temp_threshold_c = 85.0;       // over-temperature threshold (Celsius)
  double initial_position_deg = 0.0;         // starting position (degrees)
  double response_latency_ms = 0.0;          // simulated response delay (milliseconds)
};

// =============================================================================
// Fault Injection Types (Task 2.1)
// =============================================================================

/**
 * @brief Bit-flag enumeration of injectable fault types.
 *
 * Values are powers of two so they can be composed via bitwise OR
 * to represent multiple simultaneous faults.
 */
enum class FaultType : uint32_t
{
  NONE             = 0x00,
  STALL            = 0x01,
  OVERCURRENT      = 0x02,
  OVER_TEMPERATURE = 0x04,
  CAN_TIMEOUT      = 0x08,
  ENCODER_DRIFT    = 0x10,
};

// -- Bitwise operators for FaultType composition ------------------------------

inline FaultType operator|(FaultType lhs, FaultType rhs)
{
  return static_cast<FaultType>(
    static_cast<uint32_t>(lhs) | static_cast<uint32_t>(rhs));
}

inline FaultType operator&(FaultType lhs, FaultType rhs)
{
  return static_cast<FaultType>(
    static_cast<uint32_t>(lhs) & static_cast<uint32_t>(rhs));
}

inline FaultType operator~(FaultType val)
{
  return static_cast<FaultType>(~static_cast<uint32_t>(val));
}

inline FaultType & operator|=(FaultType & lhs, FaultType rhs)
{
  lhs = lhs | rhs;
  return lhs;
}

inline FaultType & operator&=(FaultType & lhs, FaultType rhs)
{
  lhs = lhs & rhs;
  return lhs;
}

/**
 * @brief Test whether a specific fault bit is set in a flags value.
 * @param flags  Combined fault flags to inspect.
 * @param test   The individual fault bit to check for.
 * @return true if every bit in @p test is set in @p flags.
 */
inline bool hasFault(FaultType flags, FaultType test)
{
  return (flags & test) != FaultType::NONE;
}

// =============================================================================
// Fault Configuration Parameters
// =============================================================================

/**
 * @brief Numeric parameters that accompany injected faults.
 *
 * When a fault is active, the simulator uses these values to determine
 * the magnitude of the simulated failure condition.
 */
struct FaultConfig
{
  double overcurrent_amps = 40.0;    // overcurrent phase-A value (amps)
  double encoder_drift_deg = 5.0;    // encoder offset from true position (degrees)
  double timeout_drop_rate = 1.0;    // CAN drop probability: 1.0 = always, 0.5 = 50%
};

}  // namespace test
}  // namespace motor_control_ros2
