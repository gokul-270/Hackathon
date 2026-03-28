cmake_minimum_required(VERSION 3.8)
project(vehicle_control)

# Shared build configuration
find_package(ament_cmake REQUIRED)
find_package(common_utils REQUIRED)

# find dependencies
find_package(ament_cmake_python REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(std_srvs REQUIRED)

# Set Python install directory
set(PYTHON_INSTALL_DIR "lib/python${Python3_VERSION_MAJOR}.${Python3_VERSION_MINOR}/site-packages")

# Install Python packages to site-packages
# This replaces ament_python_install_package since we have a flat structure
install(DIRECTORY
  core
  hardware
  integration
  utils
  simulation
  config
  DESTINATION ${PYTHON_INSTALL_DIR}/${PROJECT_NAME}
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.pyc" EXCLUDE
)

# Install root __init__.py
install(FILES
  __init__.py
  DESTINATION ${PYTHON_INSTALL_DIR}/${PROJECT_NAME}
)

# Install Python executables to lib/<package_name> for ros2 launch
# Note: executables are renamed to remove .py extension for ros2 launch compatibility
install(PROGRAMS integration/vehicle_control_node.py DESTINATION lib/${PROJECT_NAME} RENAME vehicle_control_node)
install(PROGRAMS quick_start.py DESTINATION lib/${PROJECT_NAME} RENAME quick_start)
install(PROGRAMS demo.py DESTINATION lib/${PROJECT_NAME} RENAME demo)
install(PROGRAMS simple_demo.py DESTINATION lib/${PROJECT_NAME} RENAME simple_demo)

# Install Gazebo simulation nodes
install(PROGRAMS simulation/gazebo/nodes/kinematics_node.py DESTINATION lib/${PROJECT_NAME} RENAME gazebo_kinematics_node)
install(PROGRAMS simulation/gazebo/nodes/joy_teleop.py DESTINATION lib/${PROJECT_NAME} RENAME gazebo_joy_teleop)
install(PROGRAMS simulation/gazebo/nodes/keyboard_teleop.py DESTINATION lib/${PROJECT_NAME} RENAME gazebo_keyboard_teleop)
install(PROGRAMS simulation/gazebo/nodes/ackermann_steering.py DESTINATION lib/${PROJECT_NAME} RENAME gazebo_ackermann_steering)
install(PROGRAMS simulation/gazebo/nodes/rtk_gps_simulator.py DESTINATION lib/${PROJECT_NAME} RENAME gazebo_rtk_gps_simulator)
install(PROGRAMS simulation/gazebo/nodes/front_camera_cotton_detector.py DESTINATION lib/${PROJECT_NAME} RENAME gazebo_front_camera_cotton_detector)

# Install launch files
# Exclude archived launch files (legacy consolidation)
install(DIRECTORY
  launch/
  DESTINATION share/${PROJECT_NAME}/launch
  PATTERN "archive" EXCLUDE
)

# Install Gazebo simulation launch files
install(DIRECTORY
  simulation/gazebo/launch/
  DESTINATION share/${PROJECT_NAME}/launch
  FILES_MATCHING PATTERN "*.launch.py"
)

# Install config files
install(DIRECTORY
  config/
  DESTINATION share/${PROJECT_NAME}/config
)

# Install Gazebo simulation resources
install(DIRECTORY
  simulation/gazebo/urdf/
  DESTINATION share/${PROJECT_NAME}/urdf
  FILES_MATCHING PATTERN "*.urdf" PATTERN "*.xacro"
)

install(DIRECTORY
  simulation/gazebo/worlds/
  DESTINATION share/${PROJECT_NAME}/worlds
  FILES_MATCHING PATTERN "*.sdf" PATTERN "*.world" PATTERN "*.png"
)

install(DIRECTORY
  simulation/gazebo/meshes/
  DESTINATION share/${PROJECT_NAME}/meshes
)

# Install cotton plant models for Gazebo
install(DIRECTORY
  simulation/gazebo/models/
  DESTINATION share/${PROJECT_NAME}/models
)

# Install generator scripts
install(PROGRAMS
  simulation/gazebo/scripts/generate_cotton_field.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME generate_cotton_field
)

install(DIRECTORY
  simulation/gazebo/config/
  DESTINATION share/${PROJECT_NAME}/simulation/config
  FILES_MATCHING PATTERN "*.yaml" PATTERN "*.config"
)

# Install vehicle MQTT bridge script to share directory (launch file uses
# get_package_share_directory + 'scripts/vehicle_mqtt_bridge.py')
install(PROGRAMS
  ${CMAKE_CURRENT_SOURCE_DIR}/../../scripts/vehicle_mqtt_bridge.py
  DESTINATION share/${PROJECT_NAME}/scripts
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  ament_lint_auto_find_test_dependencies()

  ament_add_pytest_test(test_safety_manager_fixes tests/test_safety_manager_fixes.py)
  ament_add_pytest_test(test_motor_enable_deadlock_fix tests/test_motor_enable_deadlock_fix.py)
  ament_add_pytest_test(test_thread_safety tests/test_thread_safety.py)
endif()

ament_package()
