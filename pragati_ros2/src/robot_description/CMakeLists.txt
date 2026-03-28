cmake_minimum_required(VERSION 3.16)
project(robot_description)

find_package(ament_cmake REQUIRED)
find_package(common_utils REQUIRED)

# Install directories
install(DIRECTORY
  urdf
  meshes
  launch
  config
  DESTINATION share/${PROJECT_NAME}
  PATTERN ".svn" EXCLUDE
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  ament_lint_auto_find_test_dependencies()

  ament_add_pytest_test(test_joint_naming_consistency
    test/test_joint_naming_consistency.py
    TIMEOUT 30
  )
endif()

ament_package()
