cmake_minimum_required(VERSION 3.8)
project(odrive_control_ros2)

find_package(ament_cmake REQUIRED)
find_package(common_utils REQUIRED)

# find dependencies
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(motor_control_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)

# Include directories
include_directories(include)

# SocketCAN interface library (standalone, no ROS2 dependency)
add_library(socketcan_interface src/socketcan_interface.cpp)
target_include_directories(socketcan_interface PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)

# ODrive CAN Driver library (standalone, no ROS2 dependency)
add_library(odrive_can_driver src/odrive_can_driver.cpp)
target_include_directories(odrive_can_driver PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(odrive_can_driver socketcan_interface)

# ODrive service node executable
add_executable(odrive_service_node src/odrive_service_node.cpp)
ament_target_dependencies(odrive_service_node
  rclcpp
  std_msgs
  sensor_msgs
  motor_control_msgs
  diagnostic_msgs)
target_link_libraries(odrive_service_node odrive_can_driver socketcan_interface)
target_include_directories(odrive_service_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)

# Standalone CAN test tool (no ROS2 dependency)
add_executable(odrive_can_tool src/odrive_can_tool.cpp)
target_link_libraries(odrive_can_tool odrive_can_driver socketcan_interface pthread)
ament_target_dependencies(odrive_can_tool common_utils)
target_include_directories(odrive_can_tool PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)

# Install targets
install(TARGETS
  odrive_service_node
  odrive_can_tool
  odrive_can_driver
  socketcan_interface
  DESTINATION lib/${PROJECT_NAME})

# Install directories
install(DIRECTORY
  config
  launch
  DESTINATION share/${PROJECT_NAME})

# Install header files
install(DIRECTORY include/
  DESTINATION include)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  # CAN write safety source verification tests (task 6.2, 6.3, 6.5)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(odrive_can_write_safety_tests test/test_can_write_safety.cpp)
  target_compile_definitions(odrive_can_write_safety_tests PRIVATE
    SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")

  # SocketCAN loopback bugfix verification (Section 7)
  ament_add_gtest(socketcan_loopback_tests test/test_socketcan_loopback.cpp)
  target_compile_definitions(socketcan_loopback_tests PRIVATE
    SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")

  # Mutex coverage source verification (data race fix)
  ament_add_gtest(mutex_coverage_tests test/test_mutex_coverage.cpp)
  target_compile_definitions(mutex_coverage_tests PRIVATE
    SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")

  # Heartbeat timeout detection source verification
  ament_add_gtest(heartbeat_timeout_tests test/test_heartbeat_timeout.cpp)
  target_compile_definitions(heartbeat_timeout_tests PRIVATE
    SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}")

  # Protocol encoding behavioral tests (tasks 2.1-2.9)
  ament_add_gtest(protocol_encoding_tests test/test_protocol_encoding.cpp)
  target_include_directories(protocol_encoding_tests PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include)

  # CAN driver communication behavioral tests (tasks 3.1-3.7)
  find_package(ament_cmake_gmock REQUIRED)
  ament_add_gmock(can_communication_tests test/test_can_communication.cpp)
  target_link_libraries(can_communication_tests odrive_can_driver socketcan_interface)

  # Error handling behavioral tests (tasks 4.1-4.8)
  ament_add_gmock(error_handling_tests test/test_error_handling.cpp)
  target_link_libraries(error_handling_tests odrive_can_driver socketcan_interface)
endif()

ament_package()
