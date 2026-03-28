cmake_minimum_required(VERSION 3.8)
project(common_utils)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclcpp REQUIRED)
find_package(nlohmann_json REQUIRED)

# =========================================================================
# CMAKE MODULES
# =========================================================================
# Export shared CMake modules (PragatiDefaults, PragatiLintSkips, PragatiRPiDetect)
# Auto-loaded by downstream packages via find_package(common_utils REQUIRED)
# through CONFIG_EXTRAS — no explicit include() needed in consumers.

install(DIRECTORY cmake/
  DESTINATION share/${PROJECT_NAME}/cmake
)

# =========================================================================
# C++ LIBRARY
# =========================================================================
# Compiled library (signal_handler) + header-only components (json_logging).
# Downstream packages link via ament_target_dependencies(... common_utils).

add_library(${PROJECT_NAME}
  src/signal_handler.cpp
)
target_include_directories(${PROJECT_NAME} PUBLIC
  "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
  "$<INSTALL_INTERFACE:include>"
)
# signal_handler.cpp only needs standard C++ — no ROS2 deps for the library
# itself.  json_logging.hpp still needs rclcpp + nlohmann_json at consumer
# include time, so we keep exporting those.

install(TARGETS ${PROJECT_NAME}
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(DIRECTORY include/
  DESTINATION include
)

ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_include_directories(include)
ament_export_dependencies(rclcpp nlohmann_json)

# =========================================================================
# PYTHON MODULE
# =========================================================================
# Install the Python common_utils package (json_logging, etc.)

ament_python_install_package(${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/PragatiLintSkips.cmake")
  ament_lint_auto_find_test_dependencies()

  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(signal_handler_tests test/test_signal_handler.cpp)
  target_link_libraries(signal_handler_tests ${PROJECT_NAME})

  ament_add_gtest(common_utils_consecutive_failure_tracker_tests
    test/test_consecutive_failure_tracker.cpp
  )
  target_include_directories(common_utils_consecutive_failure_tracker_tests PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  set_tests_properties(common_utils_consecutive_failure_tracker_tests
    PROPERTIES
    LABELS "unit;regression"
  )
endif()

ament_package(
  CONFIG_EXTRAS
    "cmake/PragatiDefaults.cmake"
    "cmake/PragatiLintSkips.cmake"
)
