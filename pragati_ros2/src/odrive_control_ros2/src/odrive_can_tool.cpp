// Copyright 2025 Pragati Robotics
// Standalone ODrive CAN Communication Test Tool
//
// This tool verifies CAN communication with ODrive Pro boards using CANSimple 0.6.x protocol.
// It does NOT require ROS2 and can be used for hardware bring-up and debugging.

#include "odrive_control_ros2/odrive_can_driver.hpp"
#include "odrive_control_ros2/odrive_cansimple_protocol.hpp"
#include "odrive_control_ros2/socketcan_interface.hpp"
#include "common_utils/signal_handler.hpp"

#include <iostream>
#include <iomanip>
#include <thread>
#include <atomic>
#include <chrono>
#include <vector>
#include <string>
#include <sstream>
#include <cstring>

using namespace std::chrono_literals;

// Local flag for programmatic (non-signal) shutdown of the RX thread.
// The shared pragati::shutdown_requested() handles Ctrl-C / SIGTERM;
// this flag lets main() stop the RX thread when work completes normally.
static std::atomic<bool> g_tool_done{false};

// CLI configuration
struct Config {
  std::string can_interface = "can0";
  std::vector<uint8_t> node_ids;
  int wait_heartbeat_ms = 2000;
  int timeout_ms = 500;
  int max_heartbeat_age_ms = 100;
  std::vector<std::string> checks;
  bool watch_mode = false;
  bool allow_dangerous = false;
  bool motion_test = false;
};

// Parse comma-separated node IDs
std::vector<uint8_t> parseNodeIds(const std::string& str) {
  std::vector<uint8_t> ids;
  std::stringstream ss(str);
  std::string token;
  while (std::getline(ss, token, ',')) {
    ids.push_back(static_cast<uint8_t>(std::stoi(token)));
  }
  return ids;
}

// Parse comma-separated checks
std::vector<std::string> parseChecks(const std::string& str) {
  std::vector<std::string> checks;
  std::stringstream ss(str);
  std::string token;
  while (std::getline(ss, token, ',')) {
    checks.push_back(token);
  }
  return checks;
}

// Print usage
void printUsage(const char* program_name) {
  std::cout << "Usage: " << program_name << " [OPTIONS]\n\n";
  std::cout << "Standalone CAN communication test tool for ODrive Pro (CANSimple 0.6.x)\n\n";
  std::cout << "Options:\n";
  std::cout << "  --if <interface>          CAN interface (default: can0)\n";
  std::cout << "  --nodes <id1,id2,...>     Comma-separated node IDs (required)\n";
  std::cout << "  --wait-heartbeat-ms <ms>  Heartbeat wait timeout (default: 2000)\n";
  std::cout << "  --timeout-ms <ms>         RTR reply timeout (default: 500)\n";
  std::cout << "  --max-hb-age-ms <ms>      Max heartbeat age (default: 100)\n";
  std::cout << "  --checks <list>           Checks to run (default: all safe checks)\n";
  std::cout << "                            Available: heartbeat,version,error,encoder,\n";
  std::cout << "                                       iq,temp,bus,torques,powers\n";
  std::cout << "  --watch                   Continuous monitoring mode (default: test-and-exit)\n";
  std::cout << "  --allow-dangerous         Enable dangerous actions (clear_errors, reboot, estop)\n";
  std::cout << "  --motion-test             Run motion test sequence (MOTOR WILL MOVE!)\n";
  std::cout << "  --help                    Show this help message\n\n";
  std::cout << "Motion Test Sequence (--motion-test):\n";
  std::cout << "  1. Set axis to CLOSED_LOOP_CONTROL\n";
  std::cout << "  2. Set controller to POSITION_CONTROL + TRAP_TRAJ\n";
  std::cout << "  3. Move to 0.5 turns, wait 1 sec\n";
  std::cout << "  4. Move to 2.0 turns, wait 1 sec\n";
  std::cout << "  5. Clear errors\n";
  std::cout << "  6. Reboot ODrive\n\n";
  std::cout << "Examples:\n";
  std::cout << "  " << program_name << " --if can0 --nodes 3,4,5\n";
  std::cout << "  " << program_name << " --if can0 --nodes 3 --watch\n";
  std::cout << "  " << program_name << " --if can0 --nodes 3 --checks heartbeat,version,encoder\n";
  std::cout << "  " << program_name << " --if can0 --nodes 0 --motion-test\n\n";
  std::cout << "Note: DFU mode and SET_AXIS_NODE_ID are intentionally excluded for safety.\n";
}

// Parse CLI arguments
bool parseArgs(int argc, char** argv, Config& config) {
  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];

    if (arg == "--help" || arg == "-h") {
      printUsage(argv[0]);
      return false;
    } else if (arg == "--if" && i + 1 < argc) {
      config.can_interface = argv[++i];
    } else if (arg == "--nodes" && i + 1 < argc) {
      config.node_ids = parseNodeIds(argv[++i]);
    } else if (arg == "--wait-heartbeat-ms" && i + 1 < argc) {
      config.wait_heartbeat_ms = std::stoi(argv[++i]);
    } else if (arg == "--timeout-ms" && i + 1 < argc) {
      config.timeout_ms = std::stoi(argv[++i]);
    } else if (arg == "--max-hb-age-ms" && i + 1 < argc) {
      config.max_heartbeat_age_ms = std::stoi(argv[++i]);
    } else if (arg == "--checks" && i + 1 < argc) {
      config.checks = parseChecks(argv[++i]);
    } else if (arg == "--watch") {
      config.watch_mode = true;
    } else if (arg == "--allow-dangerous") {
      config.allow_dangerous = true;
    } else if (arg == "--motion-test") {
      config.motion_test = true;
    } else {
      std::cerr << "[ERROR] Unknown argument: " << arg << "\n";
      printUsage(argv[0]);
      return false;
    }
  }

  if (config.node_ids.empty()) {
    std::cerr << "[ERROR] --nodes is required\n";
    printUsage(argv[0]);
    return false;
  }

  // Default checks if not specified
  if (config.checks.empty()) {
    config.checks = {"heartbeat", "version", "error", "encoder", "iq", "temp", "bus", "torques", "powers"};
  }

  return true;
}

// CAN RX thread
void canRxThread(
  std::shared_ptr<odrive_cansimple::SocketCANInterface> can,
  std::shared_ptr<odrive_can::ODriveCanDriver> driver)
{
  while (!pragati::shutdown_requested() && !g_tool_done) {
    uint16_t arb_id;
    std::vector<uint8_t> data;

    if (can->receive_frame(arb_id, data, 100)) {
      driver->handleFrame(arb_id, data);
    }
  }
}

// Wait for heartbeat from all nodes
bool waitForHeartbeats(
  std::shared_ptr<odrive_can::ODriveCanDriver> driver,
  const std::vector<uint8_t>& node_ids,
  int timeout_ms)
{
  std::cout << "[INFO] Waiting for heartbeat from nodes: ";
  for (size_t i = 0; i < node_ids.size(); ++i) {
    if (i > 0) std::cout << ", ";
    std::cout << static_cast<int>(node_ids[i]);
  }
  std::cout << " (timeout: " << timeout_ms << " ms)\n";

  auto start = std::chrono::steady_clock::now();
  std::vector<bool> received(node_ids.size(), false);

  while (!pragati::shutdown_requested()) {
    auto now = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - start).count();

    if (elapsed_ms > timeout_ms) {
      std::cerr << "[ERROR] Heartbeat timeout\n";
      for (size_t i = 0; i < node_ids.size(); ++i) {
        if (!received[i]) {
          std::cerr << "  Node " << static_cast<int>(node_ids[i]) << ": NO HEARTBEAT\n";
        }
      }
      return false;
    }

    bool all_received = true;
    for (size_t i = 0; i < node_ids.size(); ++i) {
      if (!received[i]) {
        auto state = driver->getMotorStateSnapshot(node_ids[i]);
        if (state && state->heartbeat.has_value()) {
          received[i] = true;
          std::cout << "[PASS] Node " << static_cast<int>(node_ids[i]) << ": Heartbeat received\n";
        } else {
          all_received = false;
        }
      }
    }

    if (all_received) {
      return true;
    }

    std::this_thread::sleep_for(10ms);
  }

  return false;
}

// Check heartbeat freshness and print status
bool checkHeartbeat(uint8_t node_id, std::shared_ptr<odrive_can::ODriveCanDriver> driver, int max_age_ms) {
  auto state = driver->getMotorStateSnapshot(node_id);
  if (!state || !state->heartbeat.has_value()) {
    std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": No heartbeat\n";
    return false;
  }

  auto now = std::chrono::steady_clock::now();
  auto age_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - state->last_heartbeat_time).count();

  if (age_ms > max_age_ms) {
    std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": Heartbeat stale (age=" << age_ms << " ms)\n";
    return false;
  }

  const auto& hb = state->heartbeat.value();
  std::cout << "[PASS] Node " << static_cast<int>(node_id) << ": Heartbeat fresh (age=" << age_ms << " ms)\n";
  std::cout << "       axis_state=" << static_cast<int>(hb.axis_state)
            << " axis_error=0x" << std::hex << hb.axis_error << std::dec
            << " procedure_result=" << static_cast<int>(hb.procedure_result)
            << " traj_done=" << static_cast<int>(hb.traj_done) << "\n";

  return true;
}

// Request and wait for version
bool checkVersion(uint8_t node_id, std::shared_ptr<odrive_can::ODriveCanDriver> driver, int timeout_ms) {
  // Get baseline timestamp
  auto state_before = driver->getMotorStateSnapshot(node_id);
  auto baseline_time = state_before && state_before->version.has_value()
    ? state_before->last_version_time
    : std::chrono::steady_clock::time_point{};

  // Send RTR
  if (!driver->requestVersion(node_id)) {
    std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": Failed to send GET_VERSION RTR\n";
    return false;
  }

  // Wait for reply
  auto start = std::chrono::steady_clock::now();
  while (!pragati::shutdown_requested()) {
    auto now = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - start).count();

    if (elapsed_ms > timeout_ms) {
      std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": GET_VERSION timeout\n";
      return false;
    }

    auto state = driver->getMotorStateSnapshot(node_id);
    if (state && state->version.has_value() && state->last_version_time > baseline_time) {
      const auto& ver = state->version.value();
      std::cout << "[PASS] Node " << static_cast<int>(node_id) << ": Version received\n";
      std::cout << "       FW v" << static_cast<int>(ver.fw_version_major) << "."
                << static_cast<int>(ver.fw_version_minor) << "."
                << static_cast<int>(ver.fw_version_revision);
      if (ver.fw_version_unreleased) {
        std::cout << "." << static_cast<int>(ver.fw_version_unreleased) << "-unreleased";
      }
      std::cout << "\n";
      std::cout << "       HW v" << static_cast<int>(ver.hw_version_major) << "."
                << static_cast<int>(ver.hw_version_minor) << "."
                << static_cast<int>(ver.hw_version_variant) << "\n";
      return true;
    }

    std::this_thread::sleep_for(5ms);
  }

  return false;
}

// Request and wait for error status
bool checkErrorStatus(uint8_t node_id, std::shared_ptr<odrive_can::ODriveCanDriver> driver, int timeout_ms) {
  auto state_before = driver->getMotorStateSnapshot(node_id);
  auto baseline_time = state_before && state_before->error_status.has_value()
    ? state_before->last_error_status_time
    : std::chrono::steady_clock::time_point{};

  if (!driver->requestErrorStatus(node_id)) {
    std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": Failed to send GET_ERROR RTR\n";
    return false;
  }

  auto start = std::chrono::steady_clock::now();
  while (!pragati::shutdown_requested()) {
    auto now = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - start).count();

    if (elapsed_ms > timeout_ms) {
      std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": GET_ERROR timeout\n";
      return false;
    }

    auto state = driver->getMotorStateSnapshot(node_id);
    if (state && state->error_status.has_value() && state->last_error_status_time > baseline_time) {
      const auto& err = state->error_status.value();
      std::cout << "[PASS] Node " << static_cast<int>(node_id) << ": Error status received\n";
      std::cout << "       active_errors=0x" << std::hex << err.active_errors << std::dec
                << " disarm_reason=0x" << std::hex << err.disarm_reason << std::dec << "\n";
      return true;
    }

    std::this_thread::sleep_for(5ms);
  }

  return false;
}

// Request and wait for encoder estimates
bool checkEncoder(uint8_t node_id, std::shared_ptr<odrive_can::ODriveCanDriver> driver, int timeout_ms) {
  auto state_before = driver->getMotorStateSnapshot(node_id);
  auto baseline_time = state_before && state_before->encoder_estimates.has_value()
    ? state_before->last_encoder_estimates_time
    : std::chrono::steady_clock::time_point{};

  if (!driver->requestEncoderEstimates(node_id)) {
    std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": Failed to send GET_ENCODER_ESTIMATES RTR\n";
    return false;
  }

  auto start = std::chrono::steady_clock::now();
  while (!pragati::shutdown_requested()) {
    auto now = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - start).count();

    if (elapsed_ms > timeout_ms) {
      std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": GET_ENCODER_ESTIMATES timeout\n";
      return false;
    }

    auto state = driver->getMotorStateSnapshot(node_id);
    if (state && state->encoder_estimates.has_value() && state->last_encoder_estimates_time > baseline_time) {
      const auto& enc = state->encoder_estimates.value();
      std::cout << "[PASS] Node " << static_cast<int>(node_id) << ": Encoder estimates received\n";
      std::cout << "       pos=" << std::fixed << std::setprecision(4) << enc.pos_estimate
                << " turns, vel=" << enc.vel_estimate << " turns/s\n";
      return true;
    }

    std::this_thread::sleep_for(5ms);
  }

  return false;
}

// Request and wait for IQ values
bool checkIq(uint8_t node_id, std::shared_ptr<odrive_can::ODriveCanDriver> driver, int timeout_ms) {
  auto state_before = driver->getMotorStateSnapshot(node_id);
  auto baseline_time = state_before && state_before->iq_values.has_value()
    ? state_before->last_iq_time
    : std::chrono::steady_clock::time_point{};

  if (!driver->requestIq(node_id)) {
    std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": Failed to send GET_IQ RTR\n";
    return false;
  }

  auto start = std::chrono::steady_clock::now();
  while (!pragati::shutdown_requested()) {
    auto now = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - start).count();

    if (elapsed_ms > timeout_ms) {
      std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": GET_IQ timeout\n";
      return false;
    }

    auto state = driver->getMotorStateSnapshot(node_id);
    if (state && state->iq_values.has_value() && state->last_iq_time > baseline_time) {
      const auto& iq = state->iq_values.value();
      std::cout << "[PASS] Node " << static_cast<int>(node_id) << ": IQ values received\n";
      std::cout << "       iq_setpoint=" << std::fixed << std::setprecision(3) << iq.iq_setpoint
                << " A, iq_measured=" << iq.iq_measured << " A\n";
      return true;
    }

    std::this_thread::sleep_for(5ms);
  }

  return false;
}

// Request and wait for temperature
bool checkTemperature(uint8_t node_id, std::shared_ptr<odrive_can::ODriveCanDriver> driver, int timeout_ms) {
  auto state_before = driver->getMotorStateSnapshot(node_id);
  auto baseline_time = state_before && state_before->temperature.has_value()
    ? state_before->last_temperature_time
    : std::chrono::steady_clock::time_point{};

  if (!driver->requestTemperature(node_id)) {
    std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": Failed to send GET_TEMPERATURE RTR\n";
    return false;
  }

  auto start = std::chrono::steady_clock::now();
  while (!pragati::shutdown_requested()) {
    auto now = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - start).count();

    if (elapsed_ms > timeout_ms) {
      std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": GET_TEMPERATURE timeout\n";
      return false;
    }

    auto state = driver->getMotorStateSnapshot(node_id);
    if (state && state->temperature.has_value() && state->last_temperature_time > baseline_time) {
      const auto& temp = state->temperature.value();
      std::cout << "[PASS] Node " << static_cast<int>(node_id) << ": Temperature received\n";
      std::cout << "       FET=" << std::fixed << std::setprecision(1) << temp.fet_temperature
                << " °C, Motor=" << temp.motor_temperature << " °C\n";
      return true;
    }

    std::this_thread::sleep_for(5ms);
  }

  return false;
}

// Request and wait for bus voltage/current
bool checkBusVoltageCurrent(uint8_t node_id, std::shared_ptr<odrive_can::ODriveCanDriver> driver, int timeout_ms) {
  auto state_before = driver->getMotorStateSnapshot(node_id);
  auto baseline_time = state_before && state_before->bus_voltage_current.has_value()
    ? state_before->last_bus_voltage_current_time
    : std::chrono::steady_clock::time_point{};

  if (!driver->requestBusVoltageCurrent(node_id)) {
    std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": Failed to send GET_BUS_VOLTAGE_CURRENT RTR\n";
    return false;
  }

  auto start = std::chrono::steady_clock::now();
  while (!pragati::shutdown_requested()) {
    auto now = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - start).count();

    if (elapsed_ms > timeout_ms) {
      std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": GET_BUS_VOLTAGE_CURRENT timeout\n";
      return false;
    }

    auto state = driver->getMotorStateSnapshot(node_id);
    if (state && state->bus_voltage_current.has_value() && state->last_bus_voltage_current_time > baseline_time) {
      const auto& bus = state->bus_voltage_current.value();
      std::cout << "[PASS] Node " << static_cast<int>(node_id) << ": Bus voltage/current received\n";
      std::cout << "       voltage=" << std::fixed << std::setprecision(2) << bus.bus_voltage
                << " V, current=" << bus.bus_current << " A\n";
      return true;
    }

    std::this_thread::sleep_for(5ms);
  }

  return false;
}

// Request and wait for torques
bool checkTorques(uint8_t node_id, std::shared_ptr<odrive_can::ODriveCanDriver> driver, int timeout_ms) {
  auto state_before = driver->getMotorStateSnapshot(node_id);
  auto baseline_time = state_before && state_before->torques.has_value()
    ? state_before->last_torques_time
    : std::chrono::steady_clock::time_point{};

  if (!driver->requestTorques(node_id)) {
    std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": Failed to send GET_TORQUES RTR\n";
    return false;
  }

  auto start = std::chrono::steady_clock::now();
  while (!pragati::shutdown_requested()) {
    auto now = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - start).count();

    if (elapsed_ms > timeout_ms) {
      std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": GET_TORQUES timeout\n";
      return false;
    }

    auto state = driver->getMotorStateSnapshot(node_id);
    if (state && state->torques.has_value() && state->last_torques_time > baseline_time) {
      const auto& torq = state->torques.value();
      std::cout << "[PASS] Node " << static_cast<int>(node_id) << ": Torques received\n";
      std::cout << "       target=" << std::fixed << std::setprecision(3) << torq.torque_target
                << " Nm, estimate=" << torq.torque_estimate << " Nm\n";
      return true;
    }

    std::this_thread::sleep_for(5ms);
  }

  return false;
}

// Request and wait for powers
bool checkPowers(uint8_t node_id, std::shared_ptr<odrive_can::ODriveCanDriver> driver, int timeout_ms) {
  auto state_before = driver->getMotorStateSnapshot(node_id);
  auto baseline_time = state_before && state_before->powers.has_value()
    ? state_before->last_powers_time
    : std::chrono::steady_clock::time_point{};

  if (!driver->requestPowers(node_id)) {
    std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": Failed to send GET_POWERS RTR\n";
    return false;
  }

  auto start = std::chrono::steady_clock::now();
  while (!pragati::shutdown_requested()) {
    auto now = std::chrono::steady_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - start).count();

    if (elapsed_ms > timeout_ms) {
      std::cout << "[FAIL] Node " << static_cast<int>(node_id) << ": GET_POWERS timeout\n";
      return false;
    }

    auto state = driver->getMotorStateSnapshot(node_id);
    if (state && state->powers.has_value() && state->last_powers_time > baseline_time) {
      const auto& pow = state->powers.value();
      std::cout << "[PASS] Node " << static_cast<int>(node_id) << ": Powers received\n";
      std::cout << "       electrical=" << std::fixed << std::setprecision(2) << pow.electrical_power
                << " W, mechanical=" << pow.mechanical_power << " W\n";
      return true;
    }

    std::this_thread::sleep_for(5ms);
  }

  return false;
}

// Motion test sequence
bool runMotionTest(uint8_t node_id, std::shared_ptr<odrive_can::ODriveCanDriver> driver) {
  std::cout << "\n========================================\n";
  std::cout << "MOTION TEST SEQUENCE - Node " << static_cast<int>(node_id) << "\n";
  std::cout << "⚠️  WARNING: MOTOR WILL MOVE!\n";
  std::cout << "========================================\n\n";

  // Step 1: Set controller mode (POSITION_CONTROL + TRAP_TRAJ)
  std::cout << "[STEP 1] Setting controller mode to POSITION_CONTROL + TRAP_TRAJ...\n";
  if (!driver->setControllerMode(node_id,
      odrive_cansimple::CONTROL_MODE::POSITION_CONTROL,
      odrive_cansimple::INPUT_MODE::TRAP_TRAJ)) {
    std::cout << "[FAIL] Failed to set controller mode\n";
    return false;
  }
  std::this_thread::sleep_for(100ms);
  std::cout << "[PASS] Controller mode set\n\n";

  // Step 2: Enter CLOSED_LOOP_CONTROL
  std::cout << "[STEP 2] Entering CLOSED_LOOP_CONTROL state...\n";
  if (!driver->setAxisState(node_id, odrive_cansimple::AXIS_STATE::CLOSED_LOOP_CONTROL)) {
    std::cout << "[FAIL] Failed to set axis state\n";
    return false;
  }
  std::this_thread::sleep_for(500ms);

  // Verify axis state via heartbeat
  auto state = driver->getMotorStateSnapshot(node_id);
  if (state && state->heartbeat.has_value()) {
    const auto& hb = state->heartbeat.value();
    std::cout << "[INFO] axis_state=" << static_cast<int>(hb.axis_state)
              << " axis_error=0x" << std::hex << hb.axis_error << std::dec << "\n";

    if (hb.axis_state != odrive_cansimple::AXIS_STATE::CLOSED_LOOP_CONTROL) {
      std::cout << "[FAIL] Axis did not enter CLOSED_LOOP_CONTROL (state="
                << static_cast<int>(hb.axis_state) << ")\n";
      if (hb.axis_error != 0) {
        std::cout << "[ERROR] axis_error=0x" << std::hex << hb.axis_error << std::dec << "\n";
      }
      return false;
    }
  }
  std::cout << "[PASS] Entered CLOSED_LOOP_CONTROL\n\n";

  // Step 3: Move to 0.5 turns
  std::cout << "[STEP 3] Moving to 0.5 turns...\n";
  if (!driver->setInputPos(node_id, 0.5f, 0.0f, 0.0f)) {
    std::cout << "[FAIL] Failed to send position command\n";
    return false;
  }

  // Wait and monitor position
  std::this_thread::sleep_for(4000ms);

  state = driver->getMotorStateSnapshot(node_id);
  if (state && state->encoder_estimates.has_value()) {
    const auto& enc = state->encoder_estimates.value();
    std::cout << "[INFO] Current position: " << std::fixed << std::setprecision(4)
              << enc.pos_estimate << " turns\n";
  }

  if (state && state->heartbeat.has_value() && state->heartbeat->traj_done) {
    std::cout << "[PASS] Trajectory complete\n\n";
  } else {
    std::cout << "[INFO] Trajectory may still be in progress\n\n";
  }

  // Step 4: Move to 2.0 turns
  std::cout << "[STEP 4] Moving to 2.0 turns...\n";
  if (!driver->setInputPos(node_id, 2.0f, 0.0f, 0.0f)) {
    std::cout << "[FAIL] Failed to send position command\n";
    return false;
  }

  // Wait and monitor position
  std::this_thread::sleep_for(4000ms);

  state = driver->getMotorStateSnapshot(node_id);
  if (state && state->encoder_estimates.has_value()) {
    const auto& enc = state->encoder_estimates.value();
    std::cout << "[INFO] Current position: " << std::fixed << std::setprecision(4)
              << enc.pos_estimate << " turns\n";
  }

  if (state && state->heartbeat.has_value() && state->heartbeat->traj_done) {
    std::cout << "[PASS] Trajectory complete\n\n";
  } else {
    std::cout << "[INFO] Trajectory may still be in progress\n\n";
  }

  // Step 5: Clear errors
  std::cout << "[STEP 5] Clearing errors...\n";
  if (!driver->clearErrors(node_id, 0)) {
    std::cout << "[FAIL] Failed to send clear errors command\n";
    return false;
  }
  std::this_thread::sleep_for(100ms);
  std::cout << "[PASS] Clear errors sent\n\n";

  // Step 6: Reboot
  std::cout << "[STEP 6] Rebooting ODrive...\n";
  if (!driver->reboot(node_id, 0)) {
    std::cout << "[FAIL] Failed to send reboot command\n";
    return false;
  }
  std::cout << "[PASS] Reboot command sent\n";
  std::cout << "[INFO] ODrive will reboot now. Heartbeat will stop.\n\n";

  std::cout << "========================================\n";
  std::cout << "MOTION TEST COMPLETE\n";
  std::cout << "========================================\n";

  return true;
}

// Run all requested checks
bool runChecks(const Config& config, std::shared_ptr<odrive_can::ODriveCanDriver> driver) {
  bool all_passed = true;

  for (uint8_t node_id : config.node_ids) {
    std::cout << "\n========================================\n";
    std::cout << "Testing Node " << static_cast<int>(node_id) << "\n";
    std::cout << "========================================\n";

    for (const auto& check : config.checks) {
      if (check == "heartbeat") {
        if (!checkHeartbeat(node_id, driver, config.max_heartbeat_age_ms)) {
          all_passed = false;
        }
      } else if (check == "version") {
        if (!checkVersion(node_id, driver, config.timeout_ms)) {
          all_passed = false;
        }
      } else if (check == "error") {
        if (!checkErrorStatus(node_id, driver, config.timeout_ms)) {
          all_passed = false;
        }
      } else if (check == "encoder") {
        if (!checkEncoder(node_id, driver, config.timeout_ms)) {
          all_passed = false;
        }
      } else if (check == "iq") {
        if (!checkIq(node_id, driver, config.timeout_ms)) {
          all_passed = false;
        }
      } else if (check == "temp") {
        if (!checkTemperature(node_id, driver, config.timeout_ms)) {
          all_passed = false;
        }
      } else if (check == "bus") {
        if (!checkBusVoltageCurrent(node_id, driver, config.timeout_ms)) {
          all_passed = false;
        }
      } else if (check == "torques") {
        if (!checkTorques(node_id, driver, config.timeout_ms)) {
          all_passed = false;
        }
      } else if (check == "powers") {
        if (!checkPowers(node_id, driver, config.timeout_ms)) {
          all_passed = false;
        }
      } else {
        std::cerr << "[WARN] Unknown check: " << check << "\n";
      }

      if (pragati::shutdown_requested()) {
        return false;
      }
    }
  }

  return all_passed;
}

// Watch mode - continuous monitoring
void watchMode(const Config& config, std::shared_ptr<odrive_can::ODriveCanDriver> driver) {
  std::cout << "\n[INFO] Entering watch mode (Ctrl+C to exit)...\n";

  while (!pragati::shutdown_requested()) {
    std::cout << "\n========================================\n";
    std::cout << "Status @ " << std::chrono::system_clock::now().time_since_epoch().count() << "\n";
    std::cout << "========================================\n";

    for (uint8_t node_id : config.node_ids) {
      auto state = driver->getMotorStateSnapshot(node_id);

      std::cout << "Node " << static_cast<int>(node_id) << ":\n";

      if (state && state->heartbeat.has_value()) {
        const auto& hb = state->heartbeat.value();
        auto now = std::chrono::steady_clock::now();
        auto age_ms = std::chrono::duration_cast<std::chrono::milliseconds>(now - state->last_heartbeat_time).count();

        std::cout << "  Heartbeat: age=" << age_ms << "ms"
                  << " state=" << static_cast<int>(hb.axis_state)
                  << " error=0x" << std::hex << hb.axis_error << std::dec
                  << " traj_done=" << static_cast<int>(hb.traj_done) << "\n";
      } else {
        std::cout << "  Heartbeat: NONE\n";
      }

      if (state && state->encoder_estimates.has_value()) {
        const auto& enc = state->encoder_estimates.value();
        std::cout << "  Encoder: pos=" << std::fixed << std::setprecision(4) << enc.pos_estimate
                  << " turns, vel=" << enc.vel_estimate << " turns/s\n";
      }

      if (state && state->error_status.has_value()) {
        const auto& err = state->error_status.value();
        std::cout << "  Errors: active=0x" << std::hex << err.active_errors
                  << " disarm=0x" << err.disarm_reason << std::dec << "\n";
      }

      if (state && state->temperature.has_value()) {
        const auto& temp = state->temperature.value();
        std::cout << "  Temp: FET=" << std::fixed << std::setprecision(1) << temp.fet_temperature
                  << "°C Motor=" << temp.motor_temperature << "°C\n";
      }

      if (state && state->bus_voltage_current.has_value()) {
        const auto& bus = state->bus_voltage_current.value();
        std::cout << "  Bus: " << std::fixed << std::setprecision(2) << bus.bus_voltage
                  << "V " << bus.bus_current << "A\n";
      }
    }

    std::this_thread::sleep_for(1000ms);
  }
}

int main(int argc, char** argv) {
  // Install signal handler (shared across Pragati tools/nodes)
  pragati::install_signal_handlers();

  // Parse CLI
  Config config;
  if (!parseArgs(argc, argv, config)) {
    return 1;
  }

  std::cout << "========================================\n";
  std::cout << "ODrive CAN Communication Test Tool\n";
  std::cout << "========================================\n";
  std::cout << "Interface: " << config.can_interface << "\n";
  std::cout << "Node IDs: ";
  for (size_t i = 0; i < config.node_ids.size(); ++i) {
    if (i > 0) std::cout << ", ";
    std::cout << static_cast<int>(config.node_ids[i]);
  }
  std::cout << "\n";
  std::cout << "Checks: ";
  for (size_t i = 0; i < config.checks.size(); ++i) {
    if (i > 0) std::cout << ", ";
    std::cout << config.checks[i];
  }
  std::cout << "\n";
  std::cout << "Watch mode: " << (config.watch_mode ? "enabled" : "disabled") << "\n";
  std::cout << "Dangerous actions: " << (config.allow_dangerous ? "enabled" : "disabled") << "\n";
  std::cout << "Motion test: " << (config.motion_test ? "enabled" : "disabled") << "\n";
  std::cout << "========================================\n\n";

  // Initialize CAN
  auto can_interface = std::make_shared<odrive_cansimple::SocketCANInterface>();
  if (!can_interface->initialize(config.can_interface, config.node_ids)) {
    std::cerr << "[ERROR] Failed to initialize CAN interface: " << config.can_interface << "\n";
    return 1;
  }

  // Initialize driver
  auto driver = std::make_shared<odrive_can::ODriveCanDriver>(can_interface);
  for (uint8_t node_id : config.node_ids) {
    driver->addMotor(node_id);
  }

  // Start RX thread
  std::thread rx_thread(canRxThread, can_interface, driver);

  // Wait for initial heartbeats
  if (!waitForHeartbeats(driver, config.node_ids, config.wait_heartbeat_ms)) {
    g_tool_done = true;
    rx_thread.join();
    can_interface->close();
    return 1;
  }

  std::cout << "\n[INFO] All nodes are alive!\n";

  // Run checks, watch mode, or motion test
  bool success = true;
  if (config.motion_test) {
    // Motion test mode - run for each node
    for (uint8_t node_id : config.node_ids) {
      if (!runMotionTest(node_id, driver)) {
        success = false;
      }
      if (pragati::shutdown_requested()) break;
    }
  } else if (config.watch_mode) {
    watchMode(config, driver);
  } else {
    success = runChecks(config, driver);
  }

  // Cleanup
  std::cout << "\n[INFO] Shutting down...\n";
  g_tool_done = true;
  rx_thread.join();
  can_interface->close();

  std::cout << "\n========================================\n";
  if (success) {
    std::cout << "Result: ALL CHECKS PASSED\n";
    std::cout << "========================================\n";
    return 0;
  } else {
    std::cout << "Result: SOME CHECKS FAILED\n";
    std::cout << "========================================\n";
    return 1;
  }
}
