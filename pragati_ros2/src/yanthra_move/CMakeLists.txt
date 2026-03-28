cmake_minimum_required(VERSION 3.16)
project(yanthra_move)

# Shared Pragati build defaults (C++17, warnings, build type, RPi detection, optimizations)
find_package(ament_cmake REQUIRED)
find_package(common_utils REQUIRED)

# Enable ccache if available (significantly speeds up rebuilds)
find_program(CCACHE_PROGRAM ccache)
if(CCACHE_PROGRAM)
  set(CMAKE_CXX_COMPILER_LAUNCHER ${CCACHE_PROGRAM})
  set(CMAKE_C_COMPILER_LAUNCHER ${CCACHE_PROGRAM})
  message(STATUS "⚡ ccache enabled for faster rebuilds")
endif()

# Git build provenance — shared module generates git_version.h on every build
set(GIT_VERSION_TEMPLATE_DIR "${PROJECT_SOURCE_DIR}/../../cmake")
include(${GIT_VERSION_TEMPLATE_DIR}/GenerateGitVersion.cmake)

# Limit parallel compilation to prevent memory exhaustion on low-RAM systems
# Each C++ compilation unit can use 1-2GB RAM with heavy template usage
include(ProcessorCount)
ProcessorCount(N)
if(N GREATER 2)
  # Limit to 2 parallel jobs to stay under ~4GB RAM usage
  set(CMAKE_JOB_POOLS "compile=2")
  set(CMAKE_JOB_POOL_COMPILE compile)
  message(STATUS "⚙️ Limiting parallel compilation to 2 jobs (memory optimization)")
endif()

# Find dependencies
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(control_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(motor_control_ros2 REQUIRED)
find_package(motor_control_msgs REQUIRED)
find_package(cotton_detection_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)
# REMOVED 2025-11-28: Unused dependencies cleaned up
# - rclpy (Python in C++ package)
# - cv_bridge, image_transport (no vision processing in this package)
# - geometric_shapes, resource_retriever (MoveIt leftovers)
# - yaml-cpp (not used)

# Generate services
rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/ArmStatus.srv"
  DEPENDENCIES std_msgs
)

rosidl_get_typesupport_target(cpp_typesupport_target ${PROJECT_NAME} "rosidl_typesupport_cpp")

# Collect all dependencies for easier management
# CLEANED UP 2025-11-28: Removed unused dependencies
set(YANTHRA_DEPENDENCIES
  rclcpp
  rclcpp_action
  std_msgs
  geometry_msgs
  sensor_msgs
  trajectory_msgs
  control_msgs
  tf2
  tf2_ros
  tf2_geometry_msgs
  motor_control_ros2
  motor_control_msgs
  cotton_detection_msgs
  common_utils
)

# Set up all source files needed for the modular system
set(MODULAR_SOURCES
  src/core/motion_controller.cpp
  src/core/cotton_picking_optimizer.cpp
  src/core/recovery_manager.cpp
  src/core/trajectory_planner.cpp
  src/core/capture_sequence.cpp
  src/core/trajectory_executor.cpp
  src/core/aruco_coordinator.cpp
  src/coordinate_transforms.cpp
  src/yanthra_utilities.cpp
  src/joint_move.cpp
  src/transform_cache.cpp  # Tier 1.3 - Static TF optimization
)

# =========================================================================
# MAIN EXECUTABLE (MODULAR SPLIT)
# =========================================================================

# YanthraMoveSystem split into modular compilation units for better build performance
set(YANTHRA_MOVE_SYSTEM_SOURCES
  src/yanthra_move_system_core.cpp
  src/yanthra_move_system_parameters.cpp
  src/yanthra_move_system_services.cpp
  src/yanthra_move_system_error_recovery.cpp
  src/yanthra_move_system_hardware.cpp
  src/yanthra_move_system_operation.cpp
)

# Single main executable - clean and simple
add_executable(yanthra_move_node
  ${YANTHRA_MOVE_SYSTEM_SOURCES}
  ${MODULAR_SOURCES}
)
target_compile_features(yanthra_move_node PUBLIC cxx_std_17)
ament_target_dependencies(yanthra_move_node ${YANTHRA_DEPENDENCIES})

# Modern CMake: use target_include_directories instead of include_directories
# This properly scopes includes to this target only
target_include_directories(yanthra_move_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>
  $<INSTALL_INTERFACE:include>
)
setup_git_version(yanthra_move_node)

# =========================================================================
# LEGACY BUILD REMOVED (October 6, 2025)
# =========================================================================
# Legacy monolithic code has been removed as part of archive cleanup.
# The system now uses only the modern modular architecture.
# BUILD_LEGACY option removed - legacy code no longer available.

message(STATUS "Building MODULAR architecture (legacy code removed)")

# =========================================================================
# GPIO SUPPORT
# =========================================================================

option(ENABLE_PIGPIO "Enable pigpio GPIO support" ON)

if(ENABLE_PIGPIO)
  # Find pigpio libraries with proper error handling
  find_library(PIGPIO_LIBRARY NAMES pigpio)
  find_library(PIGPIOD_IF2_LIBRARY NAMES pigpiod_if2)

  # Check for pigpio headers
  find_path(PIGPIO_INCLUDE_DIR NAMES pigpio.h)
  find_path(PIGPIOD_IF2_INCLUDE_DIR NAMES pigpiod_if2.h)

  if(PIGPIO_LIBRARY AND PIGPIOD_IF2_LIBRARY)
    # Add pigpio compile definitions to main executable
    target_compile_definitions(yanthra_move_node PUBLIC ENABLE_PIGPIO=1)

    # Link pigpio libraries
    target_link_libraries(yanthra_move_node ${PIGPIO_LIBRARY} ${PIGPIOD_IF2_LIBRARY})

    message(STATUS "✅ Building with pigpio GPIO support")
    message(STATUS "   pigpio: ${PIGPIO_LIBRARY}")
    message(STATUS "   pigpiod_if2: ${PIGPIOD_IF2_LIBRARY}")
  else()
    # Graceful fallback with clear instructions
    message(WARNING "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    message(WARNING "⚠️  pigpio libraries not found!")
    message(WARNING "")
    message(WARNING "To enable GPIO support, install pigpio:")
    message(WARNING "  sudo apt-get update")
    message(WARNING "  sudo apt-get install libpigpio-dev pigpio")
    message(WARNING "  sudo systemctl enable pigpiod")
    message(WARNING "  sudo systemctl start pigpiod")
    message(WARNING "")
    message(WARNING "Then rebuild: colcon build --packages-select yanthra_move")
    message(WARNING "")
    message(WARNING "Continuing without GPIO support (ROS services only)")
    message(WARNING "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Disable ENABLE_PIGPIO so conditional compilation works correctly
    set(ENABLE_PIGPIO OFF)
  endif()
else()
  message(STATUS "Building without pigpio GPIO support (placeholder mode)")
endif()

# =========================================================================
# INTERFACE LINKING
# =========================================================================

# Link generated interfaces and motor_control library to main executable
# Use motor_control_ros2_LIBRARIES which is populated by find_package()
# This includes motor_control_ros2_hardware and all other exported libraries
if(motor_control_ros2_LIBRARIES)
  message(STATUS "✅ Found motor_control_ros2 libraries: ${motor_control_ros2_LIBRARIES}")
  target_link_libraries(yanthra_move_node
    "${cpp_typesupport_target}"
    ${motor_control_ros2_LIBRARIES}
    nlohmann_json::nlohmann_json
  )
else()
  message(WARNING "⚠️ motor_control_ros2_LIBRARIES not found - GPIO functions may not link")
  target_link_libraries(yanthra_move_node
    "${cpp_typesupport_target}"
    nlohmann_json::nlohmann_json
  )
endif()

# =========================================================================
# INSTALL TARGETS
# =========================================================================

# =========================================================================
# SIMULATION BRIDGE EXECUTABLE
# =========================================================================

# Simulation bridge for Gazebo integration
add_executable(simulation_bridge
  src/simulation_bridge.cpp
)
target_compile_features(simulation_bridge PUBLIC cxx_std_17)
ament_target_dependencies(simulation_bridge
  rclcpp
  rclcpp_action
  std_msgs
  sensor_msgs
  trajectory_msgs
  control_msgs
)

# Install executables
install(TARGETS
  yanthra_move_node
  simulation_bridge
  DESTINATION lib/${PROJECT_NAME}
)

# Install directories
install(DIRECTORY
  config
  launch
  DESTINATION share/${PROJECT_NAME}
)

install(DIRECTORY
  include/
  DESTINATION include
)

# =========================================================================
# EXPORTS AND TESTING
# =========================================================================

# Export dependencies
ament_export_include_directories(include)
ament_export_dependencies(${YANTHRA_DEPENDENCIES})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  # Add unit tests using GTest
  find_package(GTest QUIET)
  if(GTest_FOUND OR GTEST_FOUND)
    message(STATUS "GTest found - building yanthra_move unit tests")

    # Coordinate transforms tests
    ament_add_gtest(yanthra_move_coordinate_tests
      test/test_coordinate_transforms.cpp
      src/coordinate_transforms.cpp
    )

    ament_target_dependencies(yanthra_move_coordinate_tests
      rclcpp
      geometry_msgs
      tf2
      tf2_ros
      tf2_geometry_msgs
      common_utils
    )

    target_include_directories(yanthra_move_coordinate_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(yanthra_move_coordinate_tests
      PROPERTIES
      LABELS "unit;regression;coordinates"
    )

    # Joint move simulation tests
    ament_add_gtest(yanthra_move_joint_simulation_tests
      test/test_joint_move_simulation.cpp
      src/joint_move.cpp
    )

    ament_target_dependencies(yanthra_move_joint_simulation_tests
      rclcpp
      rclcpp_action
      std_msgs
      trajectory_msgs
      motor_control_msgs
    )

    target_include_directories(yanthra_move_joint_simulation_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>
      $<INSTALL_INTERFACE:include>
    )

    # Link generated service interfaces (for yanthra_move/srv/arm_status.hpp)
    target_link_libraries(yanthra_move_joint_simulation_tests
      "${cpp_typesupport_target}"
    )

    set_tests_properties(yanthra_move_joint_simulation_tests
      PROPERTIES
      LABELS "unit;simulation;joint_move"
    )

    # Cotton picking optimizer tests
    ament_add_gtest(yanthra_move_optimizer_tests
      test/test_cotton_picking_optimizer.cpp
      src/core/cotton_picking_optimizer.cpp
    )

    ament_target_dependencies(yanthra_move_optimizer_tests
      rclcpp
      geometry_msgs
    )

    target_include_directories(yanthra_move_optimizer_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(yanthra_move_optimizer_tests
      PROPERTIES
      LABELS "unit;regression;optimizer"
    )

    # Error recovery and safety feature tests (MotionController)
    ament_add_gtest(yanthra_move_error_recovery_tests
      test/test_error_recovery.cpp
      ${MODULAR_SOURCES}
    )

    # MODULAR_SOURCES includes yanthra_utilities.cpp which #includes git_version.h.
    # Cannot call setup_git_version() again (duplicate target), so reuse the
    # generation target created for yanthra_move_node.
    add_dependencies(yanthra_move_error_recovery_tests generate_git_version_yanthra_move)
    target_include_directories(yanthra_move_error_recovery_tests PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
    set_source_files_properties(${CMAKE_CURRENT_BINARY_DIR}/build_timestamp.cpp PROPERTIES GENERATED TRUE)
    target_sources(yanthra_move_error_recovery_tests PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/build_timestamp.cpp)

    ament_target_dependencies(yanthra_move_error_recovery_tests
      ${YANTHRA_DEPENDENCIES}
    )

    target_include_directories(yanthra_move_error_recovery_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>
      $<INSTALL_INTERFACE:include>
    )

    target_link_libraries(yanthra_move_error_recovery_tests
      "${cpp_typesupport_target}"
      nlohmann_json::nlohmann_json
    )

    if(motor_control_ros2_LIBRARIES)
      target_link_libraries(yanthra_move_error_recovery_tests
        ${motor_control_ros2_LIBRARIES}
      )
    endif()

    if(ENABLE_PIGPIO AND PIGPIO_LIBRARY AND PIGPIOD_IF2_LIBRARY)
      target_compile_definitions(yanthra_move_error_recovery_tests PUBLIC ENABLE_PIGPIO=1)
      target_link_libraries(yanthra_move_error_recovery_tests
        ${PIGPIO_LIBRARY} ${PIGPIOD_IF2_LIBRARY}
      )
    endif()

    set_tests_properties(yanthra_move_error_recovery_tests
      PROPERTIES
      LABELS "unit;error_recovery;safety"
    )

    # Motion controller tests (construction, picking, cycles, timing)
    ament_add_gtest(yanthra_move_motion_controller_tests
      test/test_motion_controller.cpp
      ${MODULAR_SOURCES}
    )

    # Reuse git_version generation from yanthra_move_node (no duplicate target)
    add_dependencies(yanthra_move_motion_controller_tests generate_git_version_yanthra_move)
    target_include_directories(yanthra_move_motion_controller_tests PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
    set_source_files_properties(${CMAKE_CURRENT_BINARY_DIR}/build_timestamp.cpp PROPERTIES GENERATED TRUE)
    target_sources(yanthra_move_motion_controller_tests PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/build_timestamp.cpp)

    ament_target_dependencies(yanthra_move_motion_controller_tests
      ${YANTHRA_DEPENDENCIES}
    )

    target_include_directories(yanthra_move_motion_controller_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>
      $<INSTALL_INTERFACE:include>
    )

    target_link_libraries(yanthra_move_motion_controller_tests
      "${cpp_typesupport_target}"
      nlohmann_json::nlohmann_json
    )

    if(motor_control_ros2_LIBRARIES)
      target_link_libraries(yanthra_move_motion_controller_tests
        ${motor_control_ros2_LIBRARIES}
      )
    endif()

    if(ENABLE_PIGPIO AND PIGPIO_LIBRARY AND PIGPIOD_IF2_LIBRARY)
      target_compile_definitions(yanthra_move_motion_controller_tests PUBLIC ENABLE_PIGPIO=1)
      target_link_libraries(yanthra_move_motion_controller_tests
        ${PIGPIO_LIBRARY} ${PIGPIOD_IF2_LIBRARY}
      )
    endif()

    set_tests_properties(yanthra_move_motion_controller_tests
      PROPERTIES
      LABELS "unit;motion_controller;picking;timing"
    )

    # RecoveryManager unit tests (standalone — no full MODULAR_SOURCES needed)
    ament_add_gtest(yanthra_move_recovery_manager_tests
      test/core/recovery_manager_test.cpp
      src/core/recovery_manager.cpp
    )

    ament_target_dependencies(yanthra_move_recovery_manager_tests
      rclcpp
      rclcpp_action
      std_msgs
      trajectory_msgs
      motor_control_msgs
    )

    target_include_directories(yanthra_move_recovery_manager_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>
      $<INSTALL_INTERFACE:include>
    )

    target_link_libraries(yanthra_move_recovery_manager_tests
      "${cpp_typesupport_target}"
    )

    set_tests_properties(yanthra_move_recovery_manager_tests
      PROPERTIES
      LABELS "unit;recovery_manager;decomposition"
    )

    # TrajectoryPlanner unit tests (standalone — needs coordinate_transforms + TF)
    ament_add_gtest(yanthra_move_trajectory_planner_tests
      test/core/trajectory_planner_test.cpp
      src/core/trajectory_planner.cpp
      src/coordinate_transforms.cpp
    )

    ament_target_dependencies(yanthra_move_trajectory_planner_tests
      rclcpp
      rclcpp_action
      std_msgs
      trajectory_msgs
      motor_control_msgs
      geometry_msgs
      tf2
      tf2_ros
      tf2_geometry_msgs
    )

    target_include_directories(yanthra_move_trajectory_planner_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>
      $<INSTALL_INTERFACE:include>
    )

    target_link_libraries(yanthra_move_trajectory_planner_tests
      "${cpp_typesupport_target}"
    )

    set_tests_properties(yanthra_move_trajectory_planner_tests
      PROPERTIES
      LABELS "unit;trajectory_planner;decomposition"
    )

    # CaptureSequence unit tests (standalone — needs GPIO control)
    ament_add_gtest(yanthra_move_capture_sequence_tests
      test/core/capture_sequence_test.cpp
      src/core/capture_sequence.cpp
    )

    ament_target_dependencies(yanthra_move_capture_sequence_tests
      rclcpp
      rclcpp_action
      std_msgs
      trajectory_msgs
      motor_control_msgs
    )

    target_include_directories(yanthra_move_capture_sequence_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>
      $<INSTALL_INTERFACE:include>
    )

    target_link_libraries(yanthra_move_capture_sequence_tests
      "${cpp_typesupport_target}"
    )

    if(motor_control_ros2_LIBRARIES)
      target_link_libraries(yanthra_move_capture_sequence_tests
        ${motor_control_ros2_LIBRARIES}
      )
    endif()

    set_tests_properties(yanthra_move_capture_sequence_tests
      PROPERTIES
      LABELS "unit;capture_sequence;decomposition"
    )

    # TrajectoryExecutor unit tests (needs joint_move for motor commanding)
    ament_add_gtest(yanthra_move_trajectory_executor_tests
      test/core/trajectory_executor_test.cpp
      src/core/trajectory_executor.cpp
      src/core/recovery_manager.cpp
      src/joint_move.cpp
      src/yanthra_utilities.cpp
    )

    # yanthra_utilities.cpp includes git_version.h — reuse generation target
    add_dependencies(yanthra_move_trajectory_executor_tests generate_git_version_yanthra_move)
    target_include_directories(yanthra_move_trajectory_executor_tests PRIVATE ${CMAKE_CURRENT_BINARY_DIR})
    set_source_files_properties(${CMAKE_CURRENT_BINARY_DIR}/build_timestamp.cpp PROPERTIES GENERATED TRUE)
    target_sources(yanthra_move_trajectory_executor_tests PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/build_timestamp.cpp)

    ament_target_dependencies(yanthra_move_trajectory_executor_tests
      rclcpp
      rclcpp_action
      std_msgs
      trajectory_msgs
      motor_control_msgs
    )

    target_include_directories(yanthra_move_trajectory_executor_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>
      $<INSTALL_INTERFACE:include>
    )

    target_link_libraries(yanthra_move_trajectory_executor_tests
      "${cpp_typesupport_target}"
    )

    set_tests_properties(yanthra_move_trajectory_executor_tests
      PROPERTIES
      LABELS "unit;trajectory_executor;decomposition"
    )

    # ArucoCoordinator unit tests (standalone — detection via callbacks)
    ament_add_gtest(yanthra_move_aruco_coordinator_tests
      test/core/aruco_coordinator_test.cpp
      src/core/aruco_coordinator.cpp
    )

    ament_target_dependencies(yanthra_move_aruco_coordinator_tests
      rclcpp
      rclcpp_action
      std_msgs
      trajectory_msgs
      motor_control_msgs
    )

    target_include_directories(yanthra_move_aruco_coordinator_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>
      $<INSTALL_INTERFACE:include>
    )

    target_link_libraries(yanthra_move_aruco_coordinator_tests
      "${cpp_typesupport_target}"
    )

    set_tests_properties(yanthra_move_aruco_coordinator_tests
      PROPERTIES
      LABELS "unit;aruco_coordinator;decomposition"
    )

    # Pick logging field tests (JSON contract verification — no ROS2 needed)
    ament_add_gtest(yanthra_move_pick_logging_field_tests
      test/core/test_pick_logging_fields.cpp
    )

    target_link_libraries(yanthra_move_pick_logging_field_tests
      nlohmann_json::nlohmann_json
    )

    set_tests_properties(yanthra_move_pick_logging_field_tests
      PROPERTIES
      LABELS "unit;logging;json;field-trial"
    )

    ament_add_gtest(yanthra_move_joint_logging_contract_tests
      test/test_joint_move_logging_contract.cpp
    )

    target_compile_definitions(yanthra_move_joint_logging_contract_tests PRIVATE
      SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
    )

    target_include_directories(yanthra_move_joint_logging_contract_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(yanthra_move_joint_logging_contract_tests
      PROPERTIES
      LABELS "unit;logging;regression;remote-debug"
    )

    # Timing overhead tests (decomposition delegation overhead characterization)
    ament_add_gtest(yanthra_move_timing_overhead_tests
      test/core/timing_overhead_test.cpp
      src/core/recovery_manager.cpp
      src/core/capture_sequence.cpp
      src/core/aruco_coordinator.cpp
    )

    ament_target_dependencies(yanthra_move_timing_overhead_tests
      rclcpp
      rclcpp_action
      std_msgs
      trajectory_msgs
      motor_control_msgs
    )

    target_include_directories(yanthra_move_timing_overhead_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../common/include>
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../motor_control_ros2/include>
      $<INSTALL_INTERFACE:include>
    )

    target_link_libraries(yanthra_move_timing_overhead_tests
      "${cpp_typesupport_target}"
    )

    if(motor_control_ros2_LIBRARIES)
      target_link_libraries(yanthra_move_timing_overhead_tests
        ${motor_control_ros2_LIBRARIES}
      )
    endif()

    set_tests_properties(yanthra_move_timing_overhead_tests
      PROPERTIES
      LABELS "unit;timing;decomposition;overhead"
    )

    # Dead global removal source-verification tests (tech debt 4.2)
    # Verifies PRAGATI_INPUT_DIR/PRAGATI_OUTPUT_DIR char[512] globals removed.
    # No ROS2 dependencies — pure filesystem + gtest.
    ament_add_gtest(yanthra_move_dead_global_removal_tests
      test/test_dead_global_removal.cpp
    )

    target_link_libraries(yanthra_move_dead_global_removal_tests
      stdc++fs
    )

    target_include_directories(yanthra_move_dead_global_removal_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    )

    set_tests_properties(yanthra_move_dead_global_removal_tests
      PROPERTIES
      LABELS "unit;tech-debt;dead-code-removal"
    )

    # Sleep annotation source-verification tests (Tasks 2.18, 2.19, 2.20)
    # Verifies all blocking sleep calls have BLOCKING_SLEEP_OK annotations
    # and parameter fallback values are documented in catch blocks.
    # No ROS2 dependencies — pure filesystem + gtest.
    ament_add_gtest(yanthra_move_sleep_annotation_tests
      test/test_sleep_annotations.cpp
    )

    target_link_libraries(yanthra_move_sleep_annotation_tests
      stdc++fs
    )

    target_include_directories(yanthra_move_sleep_annotation_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    )

    set_tests_properties(yanthra_move_sleep_annotation_tests
      PROPERTIES
      LABELS "unit;annotations;blocking-sleeps"
    )

    # System call safety source-verification tests (tech debt 3.6)
    # Verifies motion_controller.cpp uses ARUCO_FINDER_PROGRAM macro
    # instead of hardcoded paths, and popen() instead of system().
    # No ROS2 dependencies — pure filesystem + gtest.
    ament_add_gtest(yanthra_move_system_call_safety_tests
      test/test_system_call_safety.cpp
    )

    target_link_libraries(yanthra_move_system_call_safety_tests
      stdc++fs
    )

    target_include_directories(yanthra_move_system_call_safety_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    )

    set_tests_properties(yanthra_move_system_call_safety_tests
      PROPERTIES
      LABELS "unit;system-calls;tech-debt"
    )

    # Executor dispatch latency placeholder test (task 6.5b)
    # Verifies annotation audit completeness; placeholder for future
    # real latency measurement after Pattern A conversions.
    ament_add_gtest(yanthra_move_executor_dispatch_latency_tests
      test/test_executor_dispatch_latency.cpp
    )

    target_link_libraries(yanthra_move_executor_dispatch_latency_tests
      stdc++fs
    )

    target_include_directories(yanthra_move_executor_dispatch_latency_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    )

    set_tests_properties(yanthra_move_executor_dispatch_latency_tests
      PROPERTIES
      LABELS "unit;executor;latency;blocking-sleeps"
      ENVIRONMENT "REPO_ROOT=${CMAKE_CURRENT_SOURCE_DIR}/../.."
    )

    # Arm integration tests (subprocess-based, requires motor_control_ros2 and cotton_detection_msgs)
    ament_add_gtest(yanthra_move_arm_integration_tests
      test/test_arm_integration.cpp
      TIMEOUT 120
    )

    ament_target_dependencies(yanthra_move_arm_integration_tests
      rclcpp
      std_srvs
      std_msgs
      sensor_msgs
      cotton_detection_msgs
    )

    target_include_directories(yanthra_move_arm_integration_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(yanthra_move_arm_integration_tests
      PROPERTIES
      LABELS "integration;arm_pipeline;simulation"
    )

    # Launch config flow regression tests (field-test-fix-mar2026)
    # Verifies pragati_complete.launch.py does not override YAML config
    # with launch arguments.  The Mar 17 2026 field failure was caused by
    # j4_multiposition launch arg always overriding production.yaml.
    ament_add_gtest(yanthra_move_launch_config_flow_tests
      test/test_launch_config_flow.cpp
    )

    target_compile_definitions(yanthra_move_launch_config_flow_tests PRIVATE
      SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
    )

    target_include_directories(yanthra_move_launch_config_flow_tests PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      $<INSTALL_INTERFACE:include>
    )

    set_tests_properties(yanthra_move_launch_config_flow_tests
      PROPERTIES
      LABELS "unit;regression;config;launch"
    )

  else()
    message(WARNING "GTest not found - skipping yanthra_move unit tests")
  endif()

  # Full pipeline integration test (launch_testing - Python)
  find_package(launch_testing_ament_cmake QUIET)
  if(launch_testing_ament_cmake_FOUND)
    add_launch_test(test/test_full_pipeline.py
      TIMEOUT 180
    )
  else()
    message(WARNING "launch_testing_ament_cmake not found - skipping full pipeline test")
  endif()
endif()

ament_package()
