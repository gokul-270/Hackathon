cmake_minimum_required(VERSION 3.16)
project(pattern_finder)

# Set CMake policies to suppress warnings
if(POLICY CMP0144)
  cmake_policy(SET CMP0144 NEW)
endif()

# Shared build defaults (C++17, warnings, build type, RPi detection, optimizations)
find_package(ament_cmake REQUIRED)
find_package(common_utils REQUIRED)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Find dependencies
find_package(rclcpp REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(image_transport REQUIRED)
find_package(rosidl_default_generators REQUIRED)

# Find OpenCV
find_package(OpenCV 4.0 REQUIRED)

# Include directories
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/src)
include_directories(${OpenCV_INCLUDE_DIRS})

# Configure data directories (can be overridden with -DYANTHRA_DATA_ROOT=/custom/path)
if(NOT DEFINED YANTHRA_DATA_ROOT)
  set(YANTHRA_DATA_ROOT "$ENV{HOME}/.ros/yanthra_data" CACHE STRING "Root directory for Yanthra data files")
endif()

set(YANTHRA_DATA_OUTPUT_DIR "${YANTHRA_DATA_ROOT}/outputs" CACHE STRING "Output data directory")
set(YANTHRA_DATA_INPUT_DIR "${YANTHRA_DATA_ROOT}/inputs" CACHE STRING "Input data directory")
set(YANTHRA_DATA_DEBUG_DIR "${YANTHRA_DATA_ROOT}/debug" CACHE STRING "Debug data directory")
set(RS_CAPTURE_PROGRAM "${YANTHRA_DATA_ROOT}/scripts/rs_capture_s640" CACHE STRING "RealSense capture program path")

message(STATUS "Yanthra data directories:")
message(STATUS "  Root: ${YANTHRA_DATA_ROOT}")
message(STATUS "  Output: ${YANTHRA_DATA_OUTPUT_DIR}")
message(STATUS "  Input: ${YANTHRA_DATA_INPUT_DIR}")
message(STATUS "  Debug: ${YANTHRA_DATA_DEBUG_DIR}")
message(STATUS "  Capture program: ${RS_CAPTURE_PROGRAM}")

# C++ aruco_finder removed - using Python version (aruco_detect_oakd.py)
# See archive/aruco_finder.cpp for legacy RealSense-based implementation

# Install Python-based OAK-D ArUco detector (production)
# All code is self-contained in aruco_detect_oakd.py (no separate helper modules needed)
install(PROGRAMS
  scripts/aruco_detect_oakd.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME aruco_finder_oakd
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
