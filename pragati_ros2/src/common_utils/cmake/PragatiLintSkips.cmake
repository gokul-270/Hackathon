# PragatiLintSkips.cmake — Standard lint suppression for Pragati ROS2 packages.
#
# Usage: After find_package(common_utils REQUIRED), call include(PragatiLintSkips)
#        inside the if(BUILD_TESTING) block.
#
# Suppresses: copyright, cpplint, uncrustify, flake8, pep257, lint_cmake, xmllint.
# These linters are project-wide policy decisions, not per-package.
# Code quality is enforced by .clang-tidy (C++) and pre-commit hooks (Python).

# Idempotent guard
if(_PRAGATI_LINT_SKIPS_INCLUDED)
  return()
endif()
set(_PRAGATI_LINT_SKIPS_INCLUDED TRUE)

set(ament_cmake_copyright_FOUND TRUE CACHE BOOL "Skip ament copyright check" FORCE)
set(ament_cmake_cpplint_FOUND TRUE CACHE BOOL "Skip ament cpplint check" FORCE)
set(ament_cmake_uncrustify_FOUND TRUE CACHE BOOL "Skip ament uncrustify check" FORCE)
set(ament_cmake_flake8_FOUND TRUE CACHE BOOL "Skip ament flake8 check" FORCE)
set(ament_cmake_pep257_FOUND TRUE CACHE BOOL "Skip ament pep257 check" FORCE)
set(ament_cmake_lint_cmake_FOUND TRUE CACHE BOOL "Skip ament lint_cmake check" FORCE)
set(ament_cmake_xmllint_FOUND TRUE CACHE BOOL "Skip ament xmllint check" FORCE)
