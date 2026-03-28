cmake_minimum_required(VERSION 3.8)
project(cotton_detection_ros2)

find_package(ament_cmake REQUIRED)
find_package(common_utils REQUIRED)

# Git build provenance — shared module generates git_version.h on every build
set(GIT_VERSION_TEMPLATE_DIR "${PROJECT_SOURCE_DIR}/../../cmake")
include(${GIT_VERSION_TEMPLATE_DIR}/GenerateGitVersion.cmake)

# find dependencies
find_package(rclcpp REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)
find_package(diagnostic_updater REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(image_transport REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(cotton_detection_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(nlohmann_json REQUIRED)

# OpenCV
find_package(OpenCV REQUIRED)

# DepthAI camera support (OAK-D Lite)
option(HAS_DEPTHAI "Enable DepthAI camera support" ON)
set(DEPTHAI_FOUND FALSE)
if(HAS_DEPTHAI)
  message(STATUS "Searching for depthai package...")
  message(STATUS "CMAKE_PREFIX_PATH: ${CMAKE_PREFIX_PATH}")
  find_package(depthai)
  message(STATUS "depthai_FOUND: ${depthai_FOUND}")
  if(depthai_FOUND)
    set(DEPTHAI_FOUND TRUE)
    message(STATUS "✅ DepthAI library found - OAK-D Lite camera support ENABLED")
  else()
    message(FATAL_ERROR "DepthAI library not found but HAS_DEPTHAI=ON. DepthAI is required for cotton_detection_ros2. Install depthai (and ensure it is discoverable via CMAKE_PREFIX_PATH). For offline testing, keep HAS_DEPTHAI=ON and disable DepthAI at runtime (e.g., use_depthai:=false), rather than building without it.")
  endif()
endif()

# Interfaces now provided by cotton_detection_msgs package

# =========================================================================
# ThermalGuard Library (hardware-decoupled thermal monitoring)
# =========================================================================
add_library(thermal_guard
  src/thermal_guard.cpp
)

target_include_directories(thermal_guard PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

target_compile_features(thermal_guard PUBLIC cxx_std_17)

install(TARGETS thermal_guard
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

# =========================================================================
# DiagnosticsCollector Library (hardware-decoupled diagnostics extraction)
# =========================================================================
add_library(diagnostics_collector
  src/diagnostics_collector.cpp
)

target_include_directories(diagnostics_collector PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

target_compile_features(diagnostics_collector PUBLIC cxx_std_17)

install(TARGETS diagnostics_collector
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

# =========================================================================
# DepthAI Libraries (Decomposed Camera Components)
# =========================================================================

if(DEPTHAI_FOUND)
  # =========================================================================
  # PipelineBuilder Library (stateless pipeline factory, requires depthai::core)
  # =========================================================================
  add_library(pipeline_builder
    src/pipeline_builder.cpp
  )

  target_include_directories(pipeline_builder PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )

  target_link_libraries(pipeline_builder
    depthai::core
  )

  target_compile_features(pipeline_builder PUBLIC cxx_std_17)

  install(TARGETS pipeline_builder
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
  )

  # =========================================================================
  # DeviceConnection Library (device lifecycle management, requires depthai::core)
  # =========================================================================
  add_library(device_connection
    src/device_connection.cpp
  )

  target_include_directories(device_connection PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )

  target_link_libraries(device_connection
    depthai::core
  )

  target_compile_features(device_connection PUBLIC cxx_std_17)

  install(TARGETS device_connection
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
  )

  # =========================================================================
  # CameraManager Library (composes PipelineBuilder + DeviceConnection)
  # =========================================================================
  add_library(camera_manager
    src/camera_manager.cpp
  )

  target_include_directories(camera_manager PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )

  target_link_libraries(camera_manager
    pipeline_builder
    device_connection
    depthai::core
    ${OpenCV_LIBRARIES}
  )

  target_compile_features(camera_manager PUBLIC cxx_std_17)

  install(TARGETS camera_manager
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
  )

  # =========================================================================
  # DepthAIManager Library (production camera integration, restored from pre-decomposition)
  # =========================================================================
  add_library(depthai_manager
    src/depthai_manager.cpp
  )

  target_include_directories(depthai_manager PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )

  ament_target_dependencies(depthai_manager
    rclcpp
  )

  target_link_libraries(depthai_manager
    depthai::core
    ${OpenCV_LIBRARIES}
  )

  target_compile_features(depthai_manager PUBLIC cxx_std_17)

  install(TARGETS depthai_manager
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
  )

endif()

# =========================================================================
# AsyncImageSaver Library (Non-blocking image I/O)
# =========================================================================
add_library(async_image_saver
  src/async_image_saver.cpp
)

target_include_directories(async_image_saver PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

target_link_libraries(async_image_saver
  ${OpenCV_LIBRARIES}
  rclcpp::rclcpp
)

target_compile_features(async_image_saver PUBLIC cxx_std_17)

install(TARGETS async_image_saver
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

# =========================================================================
# AsyncJsonLogger Library (Non-blocking JSON logging)
# =========================================================================
add_library(async_json_logger
  src/async_json_logger.cpp
)

target_include_directories(async_json_logger PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

target_link_libraries(async_json_logger
  rclcpp::rclcpp
)

# DepthAI bundles nlohmann_json 3.9.1 which has NO inline ABI namespace.
# System nlohmann_json 3.11.3 uses inline namespace json_abi[_v3_11_3], causing
# linker symbol mismatches when async_json_logger (compiled against system json)
# is linked into targets that include DepthAI's 3.9.1 headers.
# Fix: when DepthAI is found, use its bundled json; otherwise fall back to system.
if(DEPTHAI_FOUND)
  target_include_directories(async_json_logger SYSTEM PUBLIC
    ${depthai_DIR}/dependencies/include
  )
else()
  target_link_libraries(async_json_logger
    nlohmann_json::nlohmann_json
  )
endif()

target_compile_features(async_json_logger PUBLIC cxx_std_17)

install(TARGETS async_json_logger
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

# Create executable for cotton detection node
# Refactored into multiple files for improved build performance (2025-11-04)
set(COTTON_DETECTION_SOURCES
  src/cotton_detection_node.cpp
  src/cotton_detection_node_parameters.cpp
  src/cotton_detection_node_init.cpp
  src/service_handler.cpp
  src/cotton_detection_node_main.cpp
  src/detection_engine.cpp
  src/performance_monitor.cpp
)

add_executable(cotton_detection_node ${COTTON_DETECTION_SOURCES})

ament_target_dependencies(cotton_detection_node
  rclcpp
  ament_index_cpp
  std_msgs
  std_srvs
  sensor_msgs
  geometry_msgs
  diagnostic_msgs
  diagnostic_updater
  cv_bridge
  image_transport
  tf2_ros
  cotton_detection_msgs
  common_utils
)

# Link OpenCV, async_image_saver, and nlohmann_json
target_link_libraries(cotton_detection_node
  ${OpenCV_LIBRARIES}
  async_image_saver
  async_json_logger
  nlohmann_json::nlohmann_json
)

# Apply DepthAI configuration if found
if(DEPTHAI_FOUND)
  target_compile_definitions(cotton_detection_node PUBLIC HAS_DEPTHAI=1)
  target_link_libraries(cotton_detection_node
    depthai_manager
    thermal_guard
    diagnostics_collector
    depthai::core
  )
endif()

# C++17 standard (required for std::filesystem)
target_compile_features(cotton_detection_node PUBLIC cxx_std_17)

# Precompiled headers disabled due to build hanging issues
# TODO: Re-enable after fixing build problems
# target_precompile_headers(cotton_detection_node PRIVATE
#   <rclcpp/rclcpp.hpp>
#   <memory>
#   <vector>
#   <string>
#   <mutex>
#   <chrono>
# )

# Include directories
target_include_directories(cotton_detection_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>
  $<INSTALL_INTERFACE:include>
)
setup_git_version(cotton_detection_node)


# Install executables
install(TARGETS
  cotton_detection_node
  DESTINATION lib/${PROJECT_NAME}
)

# Install public headers
install(DIRECTORY include/
  DESTINATION include
)

# Install launch and config files
# Exclude archived launch files (Phase 1 legacy consolidated)
install(DIRECTORY
  launch
  config
  models
  DESTINATION share/${PROJECT_NAME}/
  PATTERN "archive" EXCLUDE
)

# Export dependencies
ament_export_dependencies(cotton_detection_msgs)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_gtest REQUIRED)
  ament_lint_auto_find_test_dependencies()

  # Build node sources as a library for test linking
  # (excludes cotton_detection_node_main.cpp which contains main())
  set(COTTON_DETECTION_TEST_SOURCES
    src/cotton_detection_node.cpp
    src/cotton_detection_node_parameters.cpp
    src/cotton_detection_node_init.cpp
    src/service_handler.cpp
    src/detection_engine.cpp
    src/performance_monitor.cpp
  )

  add_library(cotton_detection_node_testlib STATIC ${COTTON_DETECTION_TEST_SOURCES})
  ament_target_dependencies(cotton_detection_node_testlib
    rclcpp
    ament_index_cpp
    std_msgs
    std_srvs
    sensor_msgs
    geometry_msgs
    diagnostic_msgs
    diagnostic_updater
    cv_bridge
    image_transport
    tf2_ros
    cotton_detection_msgs
    common_utils
  )
  target_link_libraries(cotton_detection_node_testlib
    ${OpenCV_LIBRARIES}
    async_image_saver
    async_json_logger
    nlohmann_json::nlohmann_json
  )
  if(DEPTHAI_FOUND)
    target_compile_definitions(cotton_detection_node_testlib PUBLIC HAS_DEPTHAI=1)
    target_link_libraries(cotton_detection_node_testlib
      depthai_manager
      thermal_guard
      diagnostics_collector
      depthai::core
    )
  endif()
  target_compile_features(cotton_detection_node_testlib PUBLIC cxx_std_17)
  target_include_directories(cotton_detection_node_testlib PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}>
    $<INSTALL_INTERFACE:include>
  )
  # Depend on the git_version.h generation target (already created for the main executable)
  add_dependencies(cotton_detection_node_testlib generate_git_version_${PROJECT_NAME})
  # Add the generated build_timestamp.cpp (provides getBuildTimestamp())
  set_source_files_properties(${CMAKE_CURRENT_BINARY_DIR}/build_timestamp.cpp PROPERTIES GENERATED TRUE)
  target_sources(cotton_detection_node_testlib PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/build_timestamp.cpp)

  # DetectionEngine unit tests (restore-depthai-manager wiring verification)
  ament_add_gtest(cotton_detection_engine_tests
    test/test_detection_engine.cpp
    TIMEOUT 30
  )
  target_link_libraries(cotton_detection_engine_tests
    cotton_detection_node_testlib
  )
  target_include_directories(cotton_detection_engine_tests PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )

  # Simulation mode tests
  ament_add_gtest(cotton_detection_simulation_tests
    test/test_simulation_mode.cpp
    TIMEOUT 60
  )
  target_link_libraries(cotton_detection_simulation_tests
    cotton_detection_node_testlib
  )
  target_include_directories(cotton_detection_simulation_tests PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )

  # Executor safety tests (MultiThreadedExecutor + callback groups)
  ament_add_gtest(cotton_detection_executor_safety_tests
    test/test_executor_safety.cpp
    TIMEOUT 60
  )
  target_link_libraries(cotton_detection_executor_safety_tests
    cotton_detection_node_testlib
  )
  target_include_directories(cotton_detection_executor_safety_tests PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_compile_definitions(cotton_detection_executor_safety_tests PRIVATE
    SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
  )

  # ThermalGuard unit tests (NO depthai::core, NO rclcpp dependency)
  ament_add_gtest(cotton_detection_thermal_guard_tests
    test/test_thermal_guard.cpp
    TIMEOUT 30
  )
  target_link_libraries(cotton_detection_thermal_guard_tests
    thermal_guard
  )
  target_include_directories(cotton_detection_thermal_guard_tests PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )

  # Thermal logging JSON tests (NO depthai::core, NO rclcpp dependency)
  ament_add_gtest(cotton_detection_thermal_logging_tests
    test/test_thermal_logging.cpp
    TIMEOUT 30
  )
  target_link_libraries(cotton_detection_thermal_logging_tests
    nlohmann_json::nlohmann_json
  )
  target_include_directories(cotton_detection_thermal_logging_tests PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )

  # AsyncJsonLogger unit tests (NO depthai::core, needs rclcpp for logger)
  ament_add_gtest(cotton_detection_async_json_logger_tests
    test/test_async_json_logger.cpp
    TIMEOUT 30
  )
  target_link_libraries(cotton_detection_async_json_logger_tests
    async_json_logger
  )
  target_include_directories(cotton_detection_async_json_logger_tests PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )

  # DiagnosticsCollector unit tests (NO depthai::core, NO rclcpp dependency)
  ament_add_gtest(cotton_detection_diagnostics_collector_tests
    test/test_diagnostics_collector.cpp
    TIMEOUT 30
  )
  target_link_libraries(cotton_detection_diagnostics_collector_tests
    diagnostics_collector
  )
  target_include_directories(cotton_detection_diagnostics_collector_tests PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )

  # Blocking sleep audit tests (source-verification, no hardware dependency)
  ament_add_gtest(cotton_detection_blocking_sleep_audit_tests
    test/test_blocking_sleep_audit.cpp
    TIMEOUT 30
  )
  target_link_libraries(cotton_detection_blocking_sleep_audit_tests
    cotton_detection_node_testlib
  )
  target_include_directories(cotton_detection_blocking_sleep_audit_tests PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_compile_definitions(cotton_detection_blocking_sleep_audit_tests PRIVATE
    SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
  )

  # Zero-spatial diagnostics tests (source-audit + draw function pixel tests)
  ament_add_gtest(cotton_detection_zero_spatial_diagnostics_tests
    test/test_zero_spatial_diagnostics.cpp
    TIMEOUT 30
  )
  target_link_libraries(cotton_detection_zero_spatial_diagnostics_tests
    cotton_detection_node_testlib
  )
  target_include_directories(cotton_detection_zero_spatial_diagnostics_tests PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_compile_definitions(cotton_detection_zero_spatial_diagnostics_tests PRIVATE
    SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
  )

  # Stereo parameter configurability tests (source-audit, no hardware dependency)
  ament_add_gtest(cotton_detection_stereo_param_configurability_tests
    test/test_stereo_param_configurability.cpp
    TIMEOUT 30
  )
  target_link_libraries(cotton_detection_stereo_param_configurability_tests
    cotton_detection_node_testlib
  )
  target_include_directories(cotton_detection_stereo_param_configurability_tests PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_compile_definitions(cotton_detection_stereo_param_configurability_tests PRIVATE
    SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
  )

  # PipelineBuilder unit tests (requires depthai::core for pipeline construction)
  if(DEPTHAI_FOUND)
    ament_add_gtest(cotton_detection_pipeline_builder_tests
      test/test_pipeline_builder.cpp
      TIMEOUT 60
    )
    target_link_libraries(cotton_detection_pipeline_builder_tests
      pipeline_builder
      depthai::core
    )
    target_include_directories(cotton_detection_pipeline_builder_tests PRIVATE
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    )

    # DeviceConnection unit tests (requires depthai::core for dai::Pipeline type)
    ament_add_gtest(cotton_detection_device_connection_tests
      test/test_device_connection.cpp
      TIMEOUT 60
    )
    target_link_libraries(cotton_detection_device_connection_tests
      device_connection
      depthai::core
    )
    target_include_directories(cotton_detection_device_connection_tests PRIVATE
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    )

    # CameraManager unit tests (requires depthai::core, composes PipelineBuilder + DeviceConnection)
    ament_add_gtest(cotton_detection_camera_manager_tests
      test/test_camera_manager.cpp
      TIMEOUT 60
    )
    target_link_libraries(cotton_detection_camera_manager_tests
      camera_manager
      pipeline_builder
      device_connection
      depthai::core
      ${OpenCV_LIBRARIES}
    )
    target_include_directories(cotton_detection_camera_manager_tests PRIVATE
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    )
  endif()

endif()

ament_package()
