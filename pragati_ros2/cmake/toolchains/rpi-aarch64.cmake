# RPi aarch64 cross-compilation toolchain file
#
# IMPORTANT:
# - This file is **opt-in only**. It is used **only** when explicitly passed via
#   -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/rpi-aarch64.cmake
# - It MUST NOT be referenced from default CMakeLists or presets.
# - If anything fails, fall back to native builds on x86 / RPi.

# Target system
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

# Sysroot configuration
# Default sysroot path can be overridden via RPI_SYSROOT env var.
if(DEFINED ENV{RPI_SYSROOT})
  set(RPI_SYSROOT "$ENV{RPI_SYSROOT}" CACHE PATH "Raspberry Pi sysroot")
else()
  set(RPI_SYSROOT "$ENV{HOME}/rpi-sysroot" CACHE PATH "Raspberry Pi sysroot")
endif()

set(CMAKE_SYSROOT "${RPI_SYSROOT}")

# Compilers (aarch64 cross toolchain)
# Use the host cross-compiler (from gcc-aarch64-linux-gnu), not the copies in the sysroot.
set(CMAKE_C_COMPILER "/usr/bin/aarch64-linux-gnu-gcc")
set(CMAKE_CXX_COMPILER "/usr/bin/aarch64-linux-gnu-g++")

# Use host binutils (ar, ranlib, etc.) - NOT from sysroot
set(CMAKE_AR "/usr/bin/aarch64-linux-gnu-ar" CACHE FILEPATH "Archiver")
set(CMAKE_RANLIB "/usr/bin/aarch64-linux-gnu-ranlib" CACHE FILEPATH "Ranlib")
set(CMAKE_STRIP "/usr/bin/aarch64-linux-gnu-strip" CACHE FILEPATH "Strip")
set(CMAKE_NM "/usr/bin/aarch64-linux-gnu-nm" CACHE FILEPATH "NM")
set(CMAKE_OBJCOPY "/usr/bin/aarch64-linux-gnu-objcopy" CACHE FILEPATH "Objcopy")
set(CMAKE_OBJDUMP "/usr/bin/aarch64-linux-gnu-objdump" CACHE FILEPATH "Objdump")

# Basic flags: point to sysroot, avoid -march=native (binaries must be portable)
set(CMAKE_C_FLAGS_INIT   "--sysroot=${RPI_SYSROOT} -I${RPI_SYSROOT}/usr/local/include")
set(CMAKE_CXX_FLAGS_INIT "--sysroot=${RPI_SYSROOT} -I${RPI_SYSROOT}/usr/local/include")

# Linker flags: add library search paths and rpath-link
set(CMAKE_EXE_LINKER_FLAGS_INIT "-L${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu -L${RPI_SYSROOT}/lib/aarch64-linux-gnu -L${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/blas -L${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/lapack -Wl,-rpath-link,${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu:${RPI_SYSROOT}/lib/aarch64-linux-gnu:${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/blas:${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/lapack" CACHE STRING "" FORCE)
set(CMAKE_SHARED_LINKER_FLAGS_INIT "-L${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu -L${RPI_SYSROOT}/lib/aarch64-linux-gnu -L${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/blas -L${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/lapack -Wl,-rpath-link,${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu:${RPI_SYSROOT}/lib/aarch64-linux-gnu:${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/blas:${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/lapack" CACHE STRING "" FORCE)

# Release configuration for cross-builds (no -march=native)
set(CMAKE_C_FLAGS_RELEASE   "-O3 -DNDEBUG" CACHE STRING "" FORCE)
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG" CACHE STRING "" FORCE)

# Use host make for try_compile/build steps (do not run gmake from sysroot)

# For cross-compiling, avoid try-compile running executables; build static libs instead
set(CMAKE_TRY_COMPILE_TARGET_TYPE "STATIC_LIBRARY")

# Skip cmake package registries — they add unnecessary filesystem searches.
# The user registry (~/.cmake/packages/) and system registry (/usr/local/share)
# never contain cross-compile targets.
set(CMAKE_FIND_PACKAGE_NO_PACKAGE_REGISTRY ON)
set(CMAKE_FIND_PACKAGE_NO_SYSTEM_PACKAGE_REGISTRY ON)

# Python: Use host Python for build tools, but reference target Python for runtime
# This prevents CMake from trying to run ARM Python binaries during configuration
set(Python3_EXECUTABLE "/usr/bin/python3" CACHE FILEPATH "Host Python3 interpreter")
find_program(Python3_EXECUTABLE python3 REQUIRED)
set(PYTHON_EXECUTABLE "${Python3_EXECUTABLE}" CACHE FILEPATH "Python executable")

# ccache for cross-compilation: use the HOST ccache binary (not anything from
# the ARM sysroot).  The host ccache wraps the cross-compiler and caches its
# output, which is perfectly safe -- ccache hashes the compiler binary, flags,
# sysroot paths, and source contents, so native and cross caches never collide.
find_program(_HOST_CCACHE ccache PATHS /usr/bin /usr/local/bin NO_CMAKE_FIND_ROOT_PATH)
if(_HOST_CCACHE)
  set(CMAKE_C_COMPILER_LAUNCHER "${_HOST_CCACHE}" CACHE STRING "C compiler launcher" FORCE)
  set(CMAKE_CXX_COMPILER_LAUNCHER "${_HOST_CCACHE}" CACHE STRING "CXX compiler launcher" FORCE)
  message(STATUS "[rpi-aarch64] ccache ENABLED: ${_HOST_CCACHE}")
else()
  set(CMAKE_C_COMPILER_LAUNCHER "" CACHE STRING "C compiler launcher" FORCE)
  set(CMAKE_CXX_COMPILER_LAUNCHER "" CACHE STRING "CXX compiler launcher" FORCE)
  message(STATUS "[rpi-aarch64] ccache not found on host -- cross-compile caching disabled")
endif()

# Make sure CMake looks in the sysroot first
set(CMAKE_FIND_ROOT_PATH "${RPI_SYSROOT}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)

# Add target paths to CMAKE_PREFIX_PATH (CMake will re-root them to RPI_SYSROOT)
list(APPEND CMAKE_PREFIX_PATH
    "/opt/ros/jazzy"
    "/usr/lib/aarch64-linux-gnu/console_bridge"
    "/usr/lib/aarch64-linux-gnu/cmake/opencv4"
    "/usr/lib/aarch64-linux-gnu/cmake/orocos_kdl"
    "/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/depthai/dependencies"
)

# Ensure the sysroot ROS2 prefix is in AMENT_PREFIX_PATH.
# ament_index_get_prefix_path() reads $ENV{AMENT_PREFIX_PATH} to discover available
# RMW implementations (rmw_typesupport resource index).  When we source the HOST
# /opt/ros/jazzy/setup.bash before cross-compiling, AMENT_PREFIX_PATH only contains
# the HOST prefix (/opt/ros/jazzy), whose ament index lacks CycloneDDS.  Prepending
# the sysroot prefix lets ament find the TARGET's rmw_cyclonedds_cpp registration.
set(ENV{AMENT_PREFIX_PATH} "${RPI_SYSROOT}/opt/ros/jazzy:$ENV{AMENT_PREFIX_PATH}")

# Add library search paths
list(APPEND CMAKE_LIBRARY_PATH "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu")

# Set OpenSSL hints for cross-compilation
set(OPENSSL_ROOT_DIR "${RPI_SYSROOT}/usr" CACHE PATH "OpenSSL root directory")
set(OPENSSL_INCLUDE_DIR "${RPI_SYSROOT}/usr/include" CACHE PATH "OpenSSL include directory")
set(OPENSSL_CRYPTO_LIBRARY "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/libcrypto.so" CACHE FILEPATH "OpenSSL crypto library")
set(OPENSSL_SSL_LIBRARY "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/libssl.so" CACHE FILEPATH "OpenSSL SSL library")

# Set TinyXML2 hints for cross-compilation
# Both cases needed: packages call find_package(TinyXML2) but cmake dir is lowercase
set(tinyxml2_DIR "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/cmake/tinyxml2" CACHE PATH "TinyXML2 cmake directory")
set(TinyXML2_DIR "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/cmake/tinyxml2" CACHE PATH "TinyXML2 cmake directory (capital case)")
set(TINYXML2_LIBRARY "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/libtinyxml2.so" CACHE FILEPATH "TinyXML2 library")
set(TINYXML2_INCLUDE_DIR "${RPI_SYSROOT}/usr/include" CACHE PATH "TinyXML2 include directory")

# Set FastRTPS hints for cross-compilation
set(fastrtps_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/fastrtps/cmake" CACHE PATH "FastRTPS cmake directory")
set(FastRTPS_INCLUDE_DIR "${RPI_SYSROOT}/opt/ros/jazzy/include/fastrtps" CACHE PATH "FastRTPS include directory")

# Set CycloneDDS hints for cross-compilation (preferred RMW)
set(CycloneDDS_DIR "${RPI_SYSROOT}/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/CycloneDDS" CACHE PATH "CycloneDDS cmake directory")
set(rmw_cyclonedds_cpp_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rmw_cyclonedds_cpp/cmake" CACHE PATH "rmw_cyclonedds_cpp cmake directory")

# iceoryx (transitive dependency of CycloneDDS/rmw_cyclonedds_cpp)
set(iceoryx_binding_c_DIR "${RPI_SYSROOT}/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/iceoryx_binding_c" CACHE PATH "iceoryx_binding_c cmake directory")
set(iceoryx_hoofs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/iceoryx_hoofs" CACHE PATH "iceoryx_hoofs cmake directory")
set(iceoryx_posh_DIR "${RPI_SYSROOT}/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/iceoryx_posh" CACHE PATH "iceoryx_posh cmake directory")

# Force CycloneDDS as default RMW implementation for cross-compilation.
# This must match the runtime setting in /etc/default/pragati-arm and arm_launcher.sh.
set(RMW_IMPLEMENTATION "rmw_cyclonedds_cpp" CACHE STRING "RMW implementation")

# Set console_bridge hints
set(console_bridge_DIR "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/console_bridge/cmake" CACHE PATH "console_bridge cmake directory")

# Set OpenCV hints
set(OpenCV_DIR "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/cmake/opencv4" CACHE PATH "OpenCV cmake directory")

# Set ament_cmake hints
set(ament_cmake_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake/cmake" CACHE PATH "ament_cmake cmake directory")

# Set urdfdom hints
set(urdfdom_DIR "${RPI_SYSROOT}/opt/ros/jazzy/lib/aarch64-linux-gnu/urdfdom/cmake" CACHE PATH "urdfdom cmake directory")

# Set Python3 hints for cross-compilation
set(Python3_INCLUDE_DIR "${RPI_SYSROOT}/usr/include/python3.12" CACHE PATH "Python3 include directory")
set(Python3_LIBRARY "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/libpython3.12.so" CACHE FILEPATH "Python3 library")
set(Python3_LIBRARIES "${Python3_LIBRARY}" CACHE FILEPATH "Python3 libraries")

# Set orocos_kdl hints
set(orocos_kdl_DIR "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/cmake/orocos_kdl" CACHE PATH "orocos_kdl cmake directory")
set(orocos_kdl_LIBRARY "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/liborocos-kdl.so" CACHE FILEPATH "orocos_kdl library")

# Set urdfdom hints
set(urdfdom_DIR "${RPI_SYSROOT}/opt/ros/jazzy/lib/aarch64-linux-gnu/urdfdom/cmake" CACHE PATH "urdfdom cmake directory")

# Set fmt hints
set(fmt_DIR "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/cmake/fmt" CACHE PATH "fmt cmake directory")

# Set depthai hints
set(depthai_DIR "${RPI_SYSROOT}/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/depthai" CACHE PATH "depthai cmake directory")
set(libnop_DIR "${RPI_SYSROOT}/opt/ros/jazzy/lib/aarch64-linux-gnu/cmake/depthai/dependencies/lib/cmake/libnop" CACHE PATH "libnop cmake directory")

# Set Python3 hints for cross-compilation
set(Python3_INCLUDE_DIR "${RPI_SYSROOT}/usr/include/python3.12" CACHE PATH "Python3 include directory")
set(Python3_LIBRARY "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/libpython3.12.so" CACHE FILEPATH "Python3 library")
set(Python3_NumPy_INCLUDE_DIR "${RPI_SYSROOT}/usr/lib/python3/dist-packages/numpy/core/include" CACHE PATH "NumPy include directory")
set(FastRTPS_LIBRARY_RELEASE "${RPI_SYSROOT}/opt/ros/jazzy/lib/libfastrtps.so" CACHE FILEPATH "FastRTPS library")
set(FastCDR_INCLUDE_DIR "${RPI_SYSROOT}/opt/ros/jazzy/include/fastcdr" CACHE PATH "FastCDR include directory")
set(FastCDR_LIBRARY_RELEASE "${RPI_SYSROOT}/opt/ros/jazzy/lib/libfastcdr.so" CACHE FILEPATH "FastCDR library")


# ============================================================================
# Package _DIR hints for transitive dependencies
# ============================================================================
# Pre-setting _DIR for all transitive ROS2 dependencies eliminates filesystem
# walks during cmake configure. Without these, each find_package() searches
# through 270+ package directories in the sysroot. With hints, cmake jumps
# directly to the right directory.
#
# Generated from the transitive dependency closure of all workspace packages.
set(action_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/action_msgs/cmake" CACHE PATH "")
set(ament_cmake_core_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_core/cmake" CACHE PATH "")
set(ament_cmake_export_definitions_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_export_definitions/cmake" CACHE PATH "")
set(ament_cmake_export_dependencies_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_export_dependencies/cmake" CACHE PATH "")
set(ament_cmake_export_include_directories_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_export_include_directories/cmake" CACHE PATH "")
set(ament_cmake_export_interfaces_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_export_interfaces/cmake" CACHE PATH "")
set(ament_cmake_export_libraries_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_export_libraries/cmake" CACHE PATH "")
set(ament_cmake_export_link_flags_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_export_link_flags/cmake" CACHE PATH "")
set(ament_cmake_export_targets_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_export_targets/cmake" CACHE PATH "")
set(ament_cmake_gen_version_h_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_gen_version_h/cmake" CACHE PATH "")
set(ament_cmake_libraries_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_libraries/cmake" CACHE PATH "")
set(ament_cmake_python_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_python/cmake" CACHE PATH "")
set(ament_cmake_ros_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_ros/cmake" CACHE PATH "")
set(ament_cmake_test_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_test/cmake" CACHE PATH "")
set(ament_cmake_version_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_cmake_version/cmake" CACHE PATH "")
set(ament_index_cpp_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/ament_index_cpp/cmake" CACHE PATH "")
set(builtin_interfaces_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/builtin_interfaces/cmake" CACHE PATH "")
set(class_loader_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/class_loader/cmake" CACHE PATH "")
set(control_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/control_msgs/cmake" CACHE PATH "")
set(controller_interface_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/controller_interface/cmake" CACHE PATH "")
set(controller_manager_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/controller_manager/cmake" CACHE PATH "")
set(controller_manager_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/controller_manager_msgs/cmake" CACHE PATH "")
set(cv_bridge_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/cv_bridge/cmake" CACHE PATH "")
set(diagnostic_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/diagnostic_msgs/cmake" CACHE PATH "")
set(diagnostic_updater_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/diagnostic_updater/cmake" CACHE PATH "")
set(fastrtps_cmake_module_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/fastrtps_cmake_module/cmake" CACHE PATH "")
set(generate_parameter_library_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/generate_parameter_library/cmake" CACHE PATH "")
set(geometry_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/geometry_msgs/cmake" CACHE PATH "")
set(hardware_interface_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/hardware_interface/cmake" CACHE PATH "")
set(image_transport_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/image_transport/cmake" CACHE PATH "")
set(joint_limits_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/joint_limits/cmake" CACHE PATH "")
set(libstatistics_collector_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/libstatistics_collector/cmake" CACHE PATH "")
set(lifecycle_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/lifecycle_msgs/cmake" CACHE PATH "")
set(message_filters_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/message_filters/cmake" CACHE PATH "")
set(nav_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/nav_msgs/cmake" CACHE PATH "")
set(parameter_traits_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/parameter_traits/cmake" CACHE PATH "")
set(pluginlib_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/pluginlib/cmake" CACHE PATH "")
set(rcl_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rcl/cmake" CACHE PATH "")
set(rcl_interfaces_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rcl_interfaces/cmake" CACHE PATH "")
set(rcl_lifecycle_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rcl_lifecycle/cmake" CACHE PATH "")
set(rcl_logging_interface_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rcl_logging_interface/cmake" CACHE PATH "")
set(rcl_yaml_param_parser_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rcl_yaml_param_parser/cmake" CACHE PATH "")
set(rclcpp_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rclcpp/cmake" CACHE PATH "")
set(rclcpp_action_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rclcpp_action/cmake" CACHE PATH "")
set(rclcpp_components_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rclcpp_components/cmake" CACHE PATH "")
set(rclcpp_lifecycle_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rclcpp_lifecycle/cmake" CACHE PATH "")
set(rcpputils_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rcpputils/cmake" CACHE PATH "")
set(rcutils_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rcutils/cmake" CACHE PATH "")
set(realtime_tools_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/realtime_tools/cmake" CACHE PATH "")
set(rmw_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rmw/cmake" CACHE PATH "")
set(rosgraph_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosgraph_msgs/cmake" CACHE PATH "")
set(rosidl_adapter_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_adapter/cmake" CACHE PATH "")
set(rosidl_cmake_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_cmake/cmake" CACHE PATH "")
set(rosidl_default_generators_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_default_generators/cmake" CACHE PATH "")
set(rosidl_default_runtime_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_default_runtime/cmake" CACHE PATH "")
set(rosidl_dynamic_typesupport_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_dynamic_typesupport/cmake" CACHE PATH "")
set(rosidl_generator_c_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_generator_c/cmake" CACHE PATH "")
set(rosidl_generator_cpp_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_generator_cpp/cmake" CACHE PATH "")
set(rosidl_runtime_c_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_runtime_c/cmake" CACHE PATH "")
set(rosidl_runtime_cpp_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_runtime_cpp/cmake" CACHE PATH "")
set(rosidl_typesupport_c_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_typesupport_c/cmake" CACHE PATH "")
set(rosidl_typesupport_cpp_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_typesupport_cpp/cmake" CACHE PATH "")
set(rosidl_typesupport_fastrtps_c_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_typesupport_fastrtps_c/cmake" CACHE PATH "")
set(rosidl_typesupport_fastrtps_cpp_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_typesupport_fastrtps_cpp/cmake" CACHE PATH "")
set(rosidl_typesupport_interface_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_typesupport_interface/cmake" CACHE PATH "")
set(rosidl_typesupport_introspection_c_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_typesupport_introspection_c/cmake" CACHE PATH "")
set(rosidl_typesupport_introspection_cpp_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rosidl_typesupport_introspection_cpp/cmake" CACHE PATH "")
set(sensor_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/sensor_msgs/cmake" CACHE PATH "")
set(statistics_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/statistics_msgs/cmake" CACHE PATH "")
set(std_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/std_msgs/cmake" CACHE PATH "")
set(std_srvs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/std_srvs/cmake" CACHE PATH "")
set(tf2_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/tf2/cmake" CACHE PATH "")
set(tf2_geometry_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/tf2_geometry_msgs/cmake" CACHE PATH "")
set(tf2_ros_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/tf2_ros/cmake" CACHE PATH "")
set(tinyxml2_vendor_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/tinyxml2_vendor/cmake" CACHE PATH "")
set(tracetools_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/tracetools/cmake" CACHE PATH "")
set(trajectory_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/trajectory_msgs/cmake" CACHE PATH "")

# Missing transitive deps (discovered via configure timing analysis)
set(pal_statistics_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/pal_statistics/cmake" CACHE PATH "")
set(pal_statistics_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/pal_statistics_msgs/cmake" CACHE PATH "")
set(rclpy_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rclpy/cmake" CACHE PATH "")
set(service_msgs_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/service_msgs/cmake" CACHE PATH "")
set(urdf_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/urdf/cmake" CACHE PATH "")
set(urdf_parser_plugin_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/urdf_parser_plugin/cmake" CACHE PATH "")
set(urdfdom_headers_DIR "${RPI_SYSROOT}/opt/ros/jazzy/lib/aarch64-linux-gnu/urdfdom_headers/cmake" CACHE PATH "")
set(rcl_action_DIR "${RPI_SYSROOT}/opt/ros/jazzy/share/rcl_action/cmake" CACHE PATH "")

# Non-standard locations
set(fastcdr_DIR "${RPI_SYSROOT}/opt/ros/jazzy/lib/cmake/fastcdr" CACHE PATH "")
set(nlohmann_json_DIR "${RPI_SYSROOT}/usr/share/cmake/nlohmann_json" CACHE PATH "")

# Boost: CRITICAL performance fix. Without this hint, cmake scans 440+ Boost
# cmake config files in the sysroot, taking 5-7 minutes of I/O-bound searching.
# With the hint, it resolves instantly. Auto-detect version to avoid hardcoding.
file(GLOB _BOOST_CMAKE_DIRS "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/cmake/Boost-*")
list(LENGTH _BOOST_CMAKE_DIRS _BOOST_COUNT)
if(_BOOST_COUNT GREATER 0)
  list(SORT _BOOST_CMAKE_DIRS)
  list(GET _BOOST_CMAKE_DIRS -1 _BOOST_CMAKE_DIR)
  set(Boost_DIR "${_BOOST_CMAKE_DIR}" CACHE PATH "Boost cmake directory")
  set(Boost_INCLUDE_DIR "${RPI_SYSROOT}/usr/include" CACHE PATH "Boost include directory")
  message(STATUS "[rpi-aarch64] Auto-detected Boost: ${_BOOST_CMAKE_DIR}")
else()
  message(WARNING "[rpi-aarch64] No Boost cmake config found in sysroot — configure may be slow")
endif()

# Use pkg-config inside the sysroot when available
find_program(PKG_CONFIG_EXECUTABLE pkg-config)
if(PKG_CONFIG_EXECUTABLE)
  set(ENV{PKG_CONFIG_SYSROOT_DIR} "${RPI_SYSROOT}")
  set(ENV{PKG_CONFIG_PATH} "${RPI_SYSROOT}/usr/lib/aarch64-linux-gnu/pkgconfig:${RPI_SYSROOT}/usr/share/pkgconfig")
endif()

message(STATUS "[rpi-aarch64] Using sysroot: ${RPI_SYSROOT}")
message(STATUS "[rpi-aarch64] C compiler: ${CMAKE_C_COMPILER}")
message(STATUS "[rpi-aarch64] CXX compiler: ${CMAKE_CXX_COMPILER}")
