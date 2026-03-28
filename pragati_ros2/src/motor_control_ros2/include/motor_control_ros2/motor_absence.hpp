/*
 * Motor Absence Detection and Exponential Backoff
 *
 * Tracks per-motor CAN failure counts and manages exponential backoff for
 * absent motors. Extracted as a standalone header so the logic is unit-
 * testable without requiring a ROS2 node.
 *
 * Design reference: motor-cpu-burn-fix D2, D3
 */

#ifndef MOTOR_CONTROL_ROS2__MOTOR_ABSENCE_HPP_
#define MOTOR_CONTROL_ROS2__MOTOR_ABSENCE_HPP_

#include <chrono>
#include <algorithm>

namespace motor_control_ros2
{

/// Configuration for motor absence detection and backoff.
struct MotorAbsenceConfig
{
  int failure_threshold = 5;             // Consecutive failures before marking absent
  int initial_backoff_ms = 1000;         // First re-probe interval (ms)
  int max_backoff_ms = 30000;            // Cap for backoff interval (ms)
  double backoff_multiplier = 2.0;       // Multiplicative factor per failed probe
};

/// Per-motor absence tracking state.
struct MotorAbsenceState
{
  int consecutive_failures = 0;
  bool is_absent = false;
  std::chrono::steady_clock::time_point next_probe_time{};
  std::chrono::milliseconds current_backoff{0};
};

/// Record a get_status() failure for one motor.
/// Returns true if the motor just transitioned to absent this call.
inline bool absence_record_failure(
  MotorAbsenceState & state,
  const MotorAbsenceConfig & cfg,
  std::chrono::steady_clock::time_point now)
{
  ++state.consecutive_failures;

  if (!state.is_absent && state.consecutive_failures >= cfg.failure_threshold) {
    state.is_absent = true;
    state.current_backoff = std::chrono::milliseconds(cfg.initial_backoff_ms);
    state.next_probe_time = now + state.current_backoff;
    return true;  // Just became absent
  }

  if (state.is_absent) {
    // Failed re-probe — grow backoff
    int next_ms = static_cast<int>(
      std::min(
        static_cast<double>(state.current_backoff.count()) * cfg.backoff_multiplier,
        static_cast<double>(cfg.max_backoff_ms)));
    state.current_backoff = std::chrono::milliseconds(next_ms);
    state.next_probe_time = now + state.current_backoff;
  }

  return false;
}

/// Record a get_status() success for one motor.
/// Returns true if the motor just recovered from absent.
inline bool absence_record_success(
  MotorAbsenceState & state,
  const MotorAbsenceConfig & cfg)
{
  bool was_absent = state.is_absent;
  state.consecutive_failures = 0;
  state.is_absent = false;
  state.current_backoff = std::chrono::milliseconds(cfg.initial_backoff_ms);
  state.next_probe_time = std::chrono::steady_clock::time_point{};
  return was_absent;  // True = recovered
}

/// Check whether an absent motor should be re-probed now.
inline bool absence_should_probe(
  const MotorAbsenceState & state,
  std::chrono::steady_clock::time_point now)
{
  return state.is_absent && now >= state.next_probe_time;
}

/// Count how many motors in the array are currently marked absent.
/// Useful for diagnostics reporting (absent_motor_count field).
inline size_t absence_count_absent(
  const MotorAbsenceState * states,
  size_t count)
{
  size_t n = 0;
  for (size_t i = 0; i < count; ++i) {
    if (states[i].is_absent) {
      ++n;
    }
  }
  return n;
}

/// Reset absence state (e.g., from ~/reset_motors service).
inline void absence_reset(
  MotorAbsenceState & state,
  const MotorAbsenceConfig & cfg)
{
  state.consecutive_failures = 0;
  state.is_absent = false;
  state.current_backoff = std::chrono::milliseconds(cfg.initial_backoff_ms);
  state.next_probe_time = std::chrono::steady_clock::time_point{};
  (void)cfg;  // Suppress unused warning (backoff already reset above)
}

}  // namespace motor_control_ros2

#endif  // MOTOR_CONTROL_ROS2__MOTOR_ABSENCE_HPP_
