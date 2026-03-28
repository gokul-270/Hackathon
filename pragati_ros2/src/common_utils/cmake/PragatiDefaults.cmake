# PragatiDefaults.cmake — Shared build flags for all Pragati ROS2 packages.
#
# Usage: After find_package(common_utils REQUIRED), call include(PragatiDefaults).
#
# Sets:
#   - C++17 standard
#   - Warning flags: -Wall -Wextra -Wpedantic
#   - Build type default: RelWithDebInfo
#   - RPi vs x86 optimization split
#   - Debug build flags
#
# Does NOT set optimization level flags (-O2/-O3). Those follow CMake build type.
# See design.md OQ2: warning flags only, optimization follows build type conventions.

# Idempotent guard
if(_PRAGATI_DEFAULTS_INCLUDED)
  return()
endif()
set(_PRAGATI_DEFAULTS_INCLUDED TRUE)

# C++17 standard
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Warning flags
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Default build type
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE "RelWithDebInfo" CACHE STRING "Build type" FORCE)
endif()

# Include RPi detection (sets PRAGATI_IS_RPI)
# Use full path since this module may not be on CMAKE_MODULE_PATH
include("${CMAKE_CURRENT_LIST_DIR}/PragatiRPiDetect.cmake")

# Optimization flags based on build type and architecture
if(CMAKE_BUILD_TYPE STREQUAL "Release" OR CMAKE_BUILD_TYPE STREQUAL "RelWithDebInfo")
  if(PRAGATI_IS_RPI)
    # Gentler optimizations for RPi to reduce memory usage during compilation
    add_compile_options(-O2 -DNDEBUG)
    message(STATUS "[PragatiDefaults] RPi optimizations enabled (-O2)")
  else()
    # Full optimizations on x86_64
    add_compile_options(-O3 -march=native -DNDEBUG)
    message(STATUS "[PragatiDefaults] Desktop optimizations enabled (-O3 -march=native)")
  endif()
endif()

if(CMAKE_BUILD_TYPE STREQUAL "Debug")
  add_compile_options(-Og -g3)
endif()
