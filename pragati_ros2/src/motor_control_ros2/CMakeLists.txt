cmake_minimum_required(VERSION 3.8)
project(motor_control_ros2)

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(common_utils REQUIRED)

# Git build provenance — shared module generates git_version.h on every build
set(GIT_VERSION_TEMPLATE_DIR "${PROJECT_SOURCE_DIR}/../../cmake")
include(${GIT_VERSION_TEMPLATE_DIR}/GenerateGitVersion.cmake)

find_package(hardware_interface REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_lifecycle REQUIRED)
find_package(pluginlib REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(sensor_msgs REQUIRED)

find_package(motor_control_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(diagnostic_msgs REQUIRED)

# GPIO Support Configuration
# Simplified: Uses pigpiod_if2 only. Simulation mode available via runtime parameter.
option(ENABLE_GPIO "Enable GPIO support using pigpiod_if2 library" ON)

# Test and Example Build Configuration
option(BUILD_TESTING "Build tests" ON)
option(BUILD_TEST_NODES "Build test node executables" OFF)

if(ENABLE_GPIO)
  # Look for pigpiod_if2 library (requires pigpiod daemon on RPi)
  find_library(PIGPIOD_IF2_LIBRARY pigpiod_if2)
  find_path(PIGPIOD_IF2_INCLUDE_DIR pigpiod_if2.h)
  find_path(PIGPIO_MAIN_INCLUDE_DIR pigpio.h)

  if(PIGPIOD_IF2_LIBRARY AND PIGPIOD_IF2_INCLUDE_DIR AND PIGPIO_MAIN_INCLUDE_DIR)
    message(STATUS "✅ GPIO: Found pigpiod_if2 library: ${PIGPIOD_IF2_LIBRARY}")
    add_compile_definitions(USE_PIGPIOD_IF)
    set(GPIO_LIBRARIES ${PIGPIOD_IF2_LIBRARY})
    set(GPIO_INCLUDE_DIRS ${PIGPIOD_IF2_INCLUDE_DIR} ${PIGPIO_MAIN_INCLUDE_DIR})
  else()
    message(STATUS "⚠️  GPIO: pigpiod_if2 not found - GPIO will run in simulation mode")
    message(STATUS "   To enable hardware GPIO on RPi: sudo apt install pigpio pigpiod")
    set(GPIO_LIBRARIES "")
    set(GPIO_INCLUDE_DIRS "")
  endif()
else()
  message(STATUS "GPIO: Disabled by configuration (simulation mode only)")
  set(GPIO_LIBRARIES "")
  set(GPIO_INCLUDE_DIRS "")
endif()


# Create hardware interface library
message(STATUS "Building with MG6010 CAN motor controller")
add_library(${PROJECT_NAME}_hardware SHARED
  src/generic_hw_interface.cpp
  src/gpio_interface.cpp
  src/gpio_control_functions.cpp
  src/safety_monitor.cpp
)

target_include_directories(${PROJECT_NAME}_hardware PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

ament_target_dependencies(${PROJECT_NAME}_hardware
  hardware_interface
  rclcpp
  rclcpp_lifecycle
  pluginlib
  std_msgs
  std_srvs
  sensor_msgs
  common_utils
)

# Link against motor_control_msgs interfaces
ament_target_dependencies(${PROJECT_NAME}_hardware motor_control_msgs)

# Link GPIO libraries if available
if(GPIO_LIBRARIES)
  target_link_libraries(${PROJECT_NAME}_hardware ${GPIO_LIBRARIES})
  target_include_directories(${PROJECT_NAME}_hardware PRIVATE ${GPIO_INCLUDE_DIRS})
  message(STATUS "Linking GPIO support: ${GPIO_LIBRARIES}")
endif()


# ========================================================================
# TEST EXECUTABLES - Only build when explicitly requested
# ========================================================================

if(BUILD_TEST_NODES)
  message(STATUS "Building test node executables")

  # Create basic service test for fundamental ROS2 service testing
  add_executable(basic_service_test
    test/basic_service_test.cpp
  )

  ament_target_dependencies(basic_service_test
    rclcpp
    std_srvs
  )
else()
  message(STATUS "Skipping test nodes (enable with -DBUILD_TEST_NODES=ON)")
endif()

if(BUILD_TEST_NODES)

  # Create GPIO interface test executable
  add_executable(gpio_test
    test/gpio_test.cpp
  )

  target_link_libraries(gpio_test ${PROJECT_NAME}_hardware)

  target_include_directories(gpio_test PRIVATE include)


  # Create SafetyMonitor test executable
  add_executable(test_safety_monitor
    test/test_safety_monitor.cpp
  )

  ament_target_dependencies(test_safety_monitor
    rclcpp
    sensor_msgs
  )

  target_link_libraries(test_safety_monitor ${PROJECT_NAME}_hardware)

  target_include_directories(test_safety_monitor PRIVATE include)
endif()

# ========================================================================
# MG6010 Motor Protocol Support
# ========================================================================

# Create MG6010 protocol library
add_library(${PROJECT_NAME}_mg6010 SHARED
  src/mg6010_protocol.cpp
  src/mg6010_can_interface.cpp
  src/generic_motor_controller.cpp
)

ament_target_dependencies(${PROJECT_NAME}_mg6010
  rclcpp
  std_msgs
)

# Define to avoid pulling in full motor_abstraction dependencies
target_compile_definitions(${PROJECT_NAME}_mg6010 PRIVATE
  BUILD_MG6010_ONLY=1
)

target_include_directories(${PROJECT_NAME}_mg6010 PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

# Create motor abstraction library (for full integration)
add_library(${PROJECT_NAME}_motor_abstraction SHARED
  src/motor_abstraction.cpp
  src/motor_parameter_mapping.cpp
  src/mg6010_controller.cpp
)

ament_target_dependencies(${PROJECT_NAME}_motor_abstraction
  rclcpp
  std_msgs
)

target_link_libraries(${PROJECT_NAME}_motor_abstraction
  ${PROJECT_NAME}_mg6010
)

target_include_directories(${PROJECT_NAME}_motor_abstraction PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

# ========================================================================
# MG6010 PRODUCTION NODE - Always built (critical for operation)
# ========================================================================

# Create MG6010 controller node (PRODUCTION - always built)
add_executable(mg6010_controller_node
  src/mg6010_controller_node.cpp
  src/motor_test_suite.cpp
  src/control_loop_manager.cpp
  src/ros_interface_manager.cpp
  src/role_strategy.cpp
  src/motor_manager.cpp
  src/shutdown_handler.cpp
)

ament_target_dependencies(mg6010_controller_node
  rclcpp
  rclcpp_action
  rclcpp_lifecycle
  std_msgs
  sensor_msgs
  std_srvs
  motor_control_msgs
  diagnostic_msgs
  common_utils
)

target_link_libraries(mg6010_controller_node
  ${PROJECT_NAME}_motor_abstraction
  ${PROJECT_NAME}_mg6010
  ${PROJECT_NAME}_hardware
  nlohmann_json::nlohmann_json
)

target_include_directories(mg6010_controller_node PRIVATE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

setup_git_version(mg6010_controller_node)

# MG6010 test nodes - only build when test nodes enabled
if(BUILD_TEST_NODES)
  # Create MG6010 standalone test node
  add_executable(mg6010_test_node
    src/mg6010_test_node.cpp
  )

  ament_target_dependencies(mg6010_test_node
    rclcpp
    std_msgs
  )

  target_link_libraries(mg6010_test_node
    ${PROJECT_NAME}_mg6010
  )

  target_include_directories(mg6010_test_node PRIVATE include)
endif()


# Install targets
install(TARGETS
  ${PROJECT_NAME}_hardware
  ${PROJECT_NAME}_mg6010
  ${PROJECT_NAME}_motor_abstraction
  DESTINATION lib
)

# Install production executables (always installed)
install(TARGETS mg6010_controller_node
  DESTINATION lib/${PROJECT_NAME}
)

# Install test executables
set(INSTALL_TARGETS)

if(BUILD_TEST_NODES)
  list(APPEND INSTALL_TARGETS
    basic_service_test
    gpio_test
    test_safety_monitor
    mg6010_test_node
  )
endif()

if(INSTALL_TARGETS)
  install(TARGETS ${INSTALL_TARGETS}
    DESTINATION lib/${PROJECT_NAME}
  )
endif()

install(DIRECTORY include/
  DESTINATION include
)

install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME}
)

# Install MG6010 test scripts
install(PROGRAMS
  ../../scripts/test_mg6010_communication.sh
  ../../scripts/compare_can_messages.py
  scripts/joint_cycle_test.py
  DESTINATION lib/${PROJECT_NAME}
)


if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # Keep important tests
  ament_lint_auto_find_test_dependencies()

  # Add unit tests using GTest
  find_package(ament_cmake_gtest REQUIRED)
  find_package(GTest QUIET)
  if(GTest_FOUND OR GTEST_FOUND)
    message(STATUS "GTest found - building motor_control unit tests")

    # Protocol encoding/decoding tests
    ament_add_gtest(motor_control_protocol_tests
      test/test_protocol_encoding.cpp
    )

    ament_target_dependencies(motor_control_protocol_tests
      rclcpp
      std_msgs
    )

    target_link_libraries(motor_control_protocol_tests
      ${PROJECT_NAME}_mg6010
    )

    target_include_directories(motor_control_protocol_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    # Mark tests with labels for regression
    set_tests_properties(motor_control_protocol_tests
      PROPERTIES
      LABELS "unit;regression"
    )

    # Safety monitor tests
    ament_add_gtest(motor_control_safety_tests
      test/test_safety_monitor_unit.cpp
    )

    ament_target_dependencies(motor_control_safety_tests
      rclcpp
      std_msgs
      std_srvs
      sensor_msgs
    )

    target_link_libraries(motor_control_safety_tests
      ${PROJECT_NAME}_hardware
    )

    if(GPIO_LIBRARIES)
      target_link_libraries(motor_control_safety_tests ${GPIO_LIBRARIES})
      target_include_directories(motor_control_safety_tests PRIVATE ${GPIO_INCLUDE_DIRS})
    endif()

    target_include_directories(motor_control_safety_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_safety_tests
      PROPERTIES
      LABELS "unit;regression;safety"
    )

    # Parameter validation tests
    ament_add_gtest(motor_control_parameter_tests
      test/test_parameter_validation.cpp
    )

    ament_target_dependencies(motor_control_parameter_tests
      rclcpp
      rcl_interfaces
    )

    target_include_directories(motor_control_parameter_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_parameter_tests
      PROPERTIES
      LABELS "unit;regression;parameters"
    )

    # CAN communication tests (with mocks)
    ament_add_gtest(motor_control_can_tests
      test/test_can_communication.cpp
    )

    ament_target_dependencies(motor_control_can_tests
      rclcpp
      std_msgs
    )

    target_link_libraries(motor_control_can_tests
      ${PROJECT_NAME}_mg6010
    )

    target_include_directories(motor_control_can_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_can_tests
      PROPERTIES
      LABELS "unit;regression;can;communication"
    )

    # Motor control safety change tests (covers tasks 1.7, 2.5, 3.5, 4.7, 5.6, 6.4, 8.6)
    ament_add_gtest(motor_control_safety_change_tests
      test/test_motor_control_safety.cpp
    )

    ament_target_dependencies(motor_control_safety_change_tests
      rclcpp
      std_msgs
      std_srvs
      sensor_msgs
      hardware_interface
      rclcpp_lifecycle
      pluginlib
    )

    target_link_libraries(motor_control_safety_change_tests
      ${PROJECT_NAME}_mg6010
      ${PROJECT_NAME}_motor_abstraction
      ${PROJECT_NAME}_hardware
    )

    target_include_directories(motor_control_safety_change_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_safety_change_tests
      PROPERTIES
      LABELS "unit;regression;safety;can"
    )

    # Motor physics simulator tests (mock-can-motor-simulator change)
    ament_add_gtest(motor_control_simulator_tests
      test/test_motor_simulator.cpp
    )

    ament_target_dependencies(motor_control_simulator_tests
      rclcpp
      std_msgs
    )

    target_link_libraries(motor_control_simulator_tests
      ${PROJECT_NAME}_mg6010
    )

    target_include_directories(motor_control_simulator_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_simulator_tests
      PROPERTIES
      LABELS "unit;regression;can;simulation"
    )

    # CAN I/O efficiency tests (motor-control-runtime-hardening task 2.5)
    ament_add_gtest(motor_control_can_io_tests
      test/test_can_io_epoll.cpp
    )

    ament_target_dependencies(motor_control_can_io_tests
      rclcpp
      std_msgs
    )

    target_link_libraries(motor_control_can_io_tests
      ${PROJECT_NAME}_mg6010
    )

    target_include_directories(motor_control_can_io_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_can_io_tests
      PROPERTIES
      LABELS "unit;regression;can;io"
    )

    # Motor absence detection / backoff tests (motor-cpu-burn-fix tasks 4.1-4.6)
    ament_add_gtest(motor_control_absence_tests
      test/test_motor_absence.cpp
    )

    target_include_directories(motor_control_absence_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_absence_tests
      PROPERTIES
      LABELS "unit;regression;absence;backoff"
    )

    # Action server interface tests (motor-control-runtime-hardening task 3.8)
    ament_add_gtest(motor_control_action_tests
      test/test_action_servers.cpp
    )

    ament_target_dependencies(motor_control_action_tests
      rclcpp
      rclcpp_action
      motor_control_msgs
    )

    target_include_directories(motor_control_action_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_action_tests
      PROPERTIES
      LABELS "unit;regression;action;async"
    )

    # Watchdog exempt flag tests (phase-1-critical-fixes task 5.1-5.4)
    ament_add_gtest(motor_control_watchdog_exempt_tests
      test/test_watchdog_exempt_flag.cpp
    )

    target_compile_definitions(motor_control_watchdog_exempt_tests PRIVATE
      SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
    )

    target_include_directories(motor_control_watchdog_exempt_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_watchdog_exempt_tests
      PROPERTIES
      LABELS "unit;regression;safety;watchdog"
    )

    ament_add_gtest(motor_control_remote_motion_logging_tests
      test/test_remote_motion_logging.cpp
    )

    target_compile_definitions(motor_control_remote_motion_logging_tests PRIVATE
      SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
    )

    target_include_directories(motor_control_remote_motion_logging_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_remote_motion_logging_tests
      PROPERTIES
      LABELS "unit;logging;regression;remote-debug"
    )

    # Service blocking removal tests (phase-2-critical-fixes tasks 1.1-1.6)
    ament_add_gtest(motor_control_service_blocking_tests
      test/test_service_blocking_removal.cpp
    )

    target_compile_definitions(motor_control_service_blocking_tests PRIVATE
      SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
    )

    target_include_directories(motor_control_service_blocking_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_service_blocking_tests
      PROPERTIES
      LABELS "unit;regression;safety;service;async"
    )

    # Simulation mode integration tests (motor-node-simulation-mode task 5.1-5.4)
    ament_add_gtest(motor_control_simulation_tests
      test/test_simulation_mode.cpp
    )

    ament_target_dependencies(motor_control_simulation_tests
      rclcpp
      std_srvs
      sensor_msgs
    )

    target_include_directories(motor_control_simulation_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_simulation_tests
      PROPERTIES
      LABELS "integration;simulation"
      TIMEOUT 120
    )

    # Action topic discovery integration tests (field-test-fix-mar2026)
    # Regression test: server + client at absolute /joint_position_command
    # and /joint_homing must discover each other.  The Mar 17 2026 field
    # failure was caused by servers using ~/... (node-namespaced) paths.
    ament_add_gtest(motor_control_action_topic_discovery_tests
      test/test_action_topic_discovery.cpp
    )

    ament_target_dependencies(motor_control_action_topic_discovery_tests
      rclcpp
      rclcpp_action
      motor_control_msgs
    )

    target_compile_definitions(motor_control_action_topic_discovery_tests PRIVATE
      SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
    )

    target_include_directories(motor_control_action_topic_discovery_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_action_topic_discovery_tests
      PROPERTIES
      LABELS "integration;regression;action;topic-discovery"
      TIMEOUT 30
    )

    # Lifecycle node integration tests (Phase 3 Step 9 — TDD RED phase)
    ament_add_gtest(motor_control_lifecycle_tests
      test/test_lifecycle_node.cpp
    )

    ament_target_dependencies(motor_control_lifecycle_tests
      rclcpp
      rclcpp_action
      lifecycle_msgs
      std_srvs
      sensor_msgs
      motor_control_msgs
    )

    target_include_directories(motor_control_lifecycle_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(motor_control_lifecycle_tests
      PROPERTIES
      LABELS "integration;lifecycle;decomposition"
      TIMEOUT 180
    )

    # MotorTestSuite tests (decomposition — TDD RED phase)
    find_package(ament_cmake_gmock QUIET)
    if(ament_cmake_gmock_FOUND)
      ament_add_gmock(motor_control_test_suite_tests
        test/test_motor_test_suite.cpp
        src/motor_test_suite.cpp
      )

      ament_target_dependencies(motor_control_test_suite_tests
        rclcpp
        rclcpp_lifecycle
        std_msgs
        std_srvs
        motor_control_msgs
      )

      target_link_libraries(motor_control_test_suite_tests
        ${PROJECT_NAME}_mg6010
        ${PROJECT_NAME}_motor_abstraction
      )

      target_include_directories(motor_control_test_suite_tests PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
      )

      set_tests_properties(motor_control_test_suite_tests
        PROPERTIES
        LABELS "unit;regression;decomposition"
      )

      # ControlLoopManager tests (decomposition — TDD RED phase)
      ament_add_gmock(motor_control_loop_manager_tests
        test/test_control_loop_manager.cpp
        src/control_loop_manager.cpp
      )

      ament_target_dependencies(motor_control_loop_manager_tests
        rclcpp
        rclcpp_lifecycle
        std_msgs
        std_srvs
        sensor_msgs
        diagnostic_msgs
        motor_control_msgs
      )

      target_link_libraries(motor_control_loop_manager_tests
        ${PROJECT_NAME}_mg6010
        ${PROJECT_NAME}_motor_abstraction
      )

      target_include_directories(motor_control_loop_manager_tests PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
      )

      set_tests_properties(motor_control_loop_manager_tests
        PROPERTIES
        LABELS "unit;regression;decomposition"
      )

      # RosInterfaceManager tests (decomposition — TDD RED phase)
      ament_add_gmock(motor_control_ros_interface_manager_tests
        test/test_ros_interface_manager.cpp
        src/motor_test_suite.cpp
        src/control_loop_manager.cpp
        src/ros_interface_manager.cpp
      )

      ament_target_dependencies(motor_control_ros_interface_manager_tests
        rclcpp
        rclcpp_action
        rclcpp_lifecycle
        std_msgs
        std_srvs
        sensor_msgs
        diagnostic_msgs
        motor_control_msgs
      )

      target_link_libraries(motor_control_ros_interface_manager_tests
        ${PROJECT_NAME}_mg6010
        ${PROJECT_NAME}_motor_abstraction
      )

      target_include_directories(motor_control_ros_interface_manager_tests PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
      )

      set_tests_properties(motor_control_ros_interface_manager_tests
        PROPERTIES
        LABELS "unit;regression;decomposition"
      )

      # MotorManager tests (decomposition — TDD RED phase)
      ament_add_gmock(motor_control_motor_manager_tests
        test/test_motor_manager.cpp
        src/motor_manager.cpp
      )

      ament_target_dependencies(motor_control_motor_manager_tests
        rclcpp
        rclcpp_lifecycle
        std_msgs
        std_srvs
        motor_control_msgs
        common_utils
      )

      target_link_libraries(motor_control_motor_manager_tests
        ${PROJECT_NAME}_mg6010
        ${PROJECT_NAME}_motor_abstraction
      )

      target_include_directories(motor_control_motor_manager_tests PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
      )

      set_tests_properties(motor_control_motor_manager_tests
        PROPERTIES
        LABELS "unit;regression;decomposition"
      )

      # RoleStrategy tests (decomposition Phase 3 — TDD RED phase)
      ament_add_gmock(motor_control_role_strategy_tests
        test/test_role_strategy.cpp
        src/role_strategy.cpp
      )

      ament_target_dependencies(motor_control_role_strategy_tests
        rclcpp
        rclcpp_lifecycle
      )

      target_include_directories(motor_control_role_strategy_tests PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
      )

      target_compile_definitions(motor_control_role_strategy_tests PRIVATE
        PROJECT_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
      )

      set_tests_properties(motor_control_role_strategy_tests
        PROPERTIES
        LABELS "unit;regression;decomposition"
      )

      # ActionServerManager tests (decomposition — TDD RED phase)
      ament_add_gmock(motor_control_action_server_manager_tests
        test/test_action_server_manager.cpp
        src/motor_manager.cpp
        src/action_server_manager.cpp
      )

      ament_target_dependencies(motor_control_action_server_manager_tests
        rclcpp
        rclcpp_action
        rclcpp_lifecycle
        std_msgs
        std_srvs
        sensor_msgs
        diagnostic_msgs
        motor_control_msgs
        common_utils
      )

      target_link_libraries(motor_control_action_server_manager_tests
        ${PROJECT_NAME}_mg6010
        ${PROJECT_NAME}_motor_abstraction
      )

      target_include_directories(motor_control_action_server_manager_tests PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
      )

      set_tests_properties(motor_control_action_server_manager_tests
        PROPERTIES
        LABELS "unit;regression;decomposition;action"
        TIMEOUT 120
      )

      # ShutdownHandler tests (decomposition Phase 3 — TDD RED phase)
      ament_add_gmock(motor_control_shutdown_handler_tests
        test/test_shutdown_handler.cpp
        src/shutdown_handler.cpp
        src/role_strategy.cpp
        src/motor_manager.cpp
      )

      ament_target_dependencies(motor_control_shutdown_handler_tests
        rclcpp
        rclcpp_lifecycle
        std_msgs
        std_srvs
        sensor_msgs
        diagnostic_msgs
        motor_control_msgs
        common_utils
      )

      target_link_libraries(motor_control_shutdown_handler_tests
        ${PROJECT_NAME}_mg6010
        ${PROJECT_NAME}_motor_abstraction
      )

      target_include_directories(motor_control_shutdown_handler_tests PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
      )

      set_tests_properties(motor_control_shutdown_handler_tests
        PROPERTIES
        LABELS "unit;regression;decomposition;shutdown"
        TIMEOUT 120
      )

      # MG6010 init/shutdown sequence tests (motor-control-hardening — TDD RED phase)
      # Tests hardened init (stop→clear→status→on) and shutdown (stop→off→clear) sequences.
      ament_add_gmock(motor_control_init_shutdown_tests
        test/test_mg6010_init_shutdown.cpp
      )

      ament_target_dependencies(motor_control_init_shutdown_tests
        rclcpp
      )

      target_link_libraries(motor_control_init_shutdown_tests
        ${PROJECT_NAME}_mg6010
        ${PROJECT_NAME}_motor_abstraction
      )

      target_include_directories(motor_control_init_shutdown_tests PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
      )

      set_tests_properties(motor_control_init_shutdown_tests
        PROPERTIES
        LABELS "unit;regression;hardening;init;shutdown"
        TIMEOUT 30
      )

      # Motor timeout stop tests (motor-control-hardening — TDD RED phase)
      # Tests the behavioral contract: on position command timeout,
      # controller->stop() (0x81) must be sent before clearing busy flag.
      ament_add_gmock(motor_control_timeout_stop_tests
        test/test_motor_timeout_stop.cpp
      )

      ament_target_dependencies(motor_control_timeout_stop_tests
        rclcpp
      )

      target_link_libraries(motor_control_timeout_stop_tests
        ${PROJECT_NAME}_motor_abstraction
      )

      target_include_directories(motor_control_timeout_stop_tests PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
      )

      set_tests_properties(motor_control_timeout_stop_tests
        PROPERTIES
        LABELS "unit;regression;hardening;timeout"
        TIMEOUT 30
      )

      # Callback group / MultiThreadedExecutor tests (decomposition Phase 3 Step 8)
      ament_add_gmock(motor_control_callback_group_tests
        test/test_callback_groups.cpp
        src/ros_interface_manager.cpp
        src/control_loop_manager.cpp
        src/motor_test_suite.cpp
        src/role_strategy.cpp
      )

      ament_target_dependencies(motor_control_callback_group_tests
        rclcpp
        rclcpp_action
        rclcpp_lifecycle
        std_msgs
        std_srvs
        sensor_msgs
        diagnostic_msgs
        motor_control_msgs
        common_utils
      )

      target_link_libraries(motor_control_callback_group_tests
        ${PROJECT_NAME}_mg6010
        ${PROJECT_NAME}_motor_abstraction
      )

      target_include_directories(motor_control_callback_group_tests PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
      )

      set_tests_properties(motor_control_callback_group_tests
        PROPERTIES
        LABELS "unit;regression;decomposition;threading"
        TIMEOUT 120
      )
    else()
      message(WARNING "ament_cmake_gmock not found - skipping MotorTestSuite tests")
    endif()

  else()
    message(WARNING "GTest not found - skipping unit tests")
  endif()
endif()

ament_export_libraries(${PROJECT_NAME}_hardware)
ament_export_dependencies(
  hardware_interface
  rclcpp
  rclcpp_lifecycle
  pluginlib
  std_msgs
  std_srvs
  sensor_msgs
  common_utils
  motor_control_msgs
)

ament_package()
