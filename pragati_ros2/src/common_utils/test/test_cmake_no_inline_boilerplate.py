"""Test: No duplicate build-flag boilerplate after CMake module migration.

Scenario (from spec cmake-module-extraction):
  GIVEN all consumer packages have been migrated
  WHEN  a grep is run across all CMakeLists.txt files for previously inlined patterns
  THEN  the only occurrences are inside common_utils/cmake/
  AND   zero occurrences remain in consumer CMakeLists.txt files
"""

import os
import re

import pytest

# Repo root is four levels up from this test file
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src")

# Packages that SHOULD contain these patterns (the shared modules themselves)
ALLOWED_PACKAGES = {"common_utils"}

# Consumer packages that must NOT contain inline boilerplate
CONSUMER_PACKAGES = [
    "motor_control_ros2",
    "odrive_control_ros2",
    "cotton_detection_ros2",
    "yanthra_move",
    "vehicle_control",
    "robot_description",
    "pattern_finder",
]

# Patterns that indicate inline boilerplate — these should only exist in
# common_utils/cmake/ modules, never in consumer CMakeLists.txt
BOILERPLATE_PATTERNS = [
    # Manual warning flags (should be in PragatiDefaults.cmake)
    (r"-Wall\s+-Wextra\s+-Wpedantic", "Inline warning flags"),
    # Manual lint skips (should be in PragatiLintSkips.cmake)
    (r"set\(ament_cmake_cpplint_FOUND\s+TRUE\)", "Inline cpplint skip"),
    (r"set\(ament_cmake_uncrustify_FOUND\s+TRUE\)", "Inline uncrustify skip"),
    (r"set\(ament_cmake_cppcheck_FOUND\s+TRUE\)", "Inline cppcheck skip"),
    (r"set\(ament_cmake_flake8_FOUND\s+TRUE\)", "Inline flake8 skip"),
    # Manual RPi detection (should be in PragatiRPiDetect.cmake)
    (r"CMAKE_SYSTEM_PROCESSOR.*aarch64", "Inline RPi/aarch64 detection"),
    # Manual optimization splits (should be in PragatiDefaults.cmake)
    (r"-O2\s.*-march=armv8-a", "Inline RPi optimization flags"),
    (r"-O3\s.*-march=native", "Inline desktop optimization flags"),
]


def _find_cmake_files():
    """Find all CMakeLists.txt in consumer packages."""
    results = []
    for pkg in CONSUMER_PACKAGES:
        cmake_path = os.path.join(SRC_DIR, pkg, "CMakeLists.txt")
        if os.path.isfile(cmake_path):
            results.append((pkg, cmake_path))
    return results


class TestNoInlineBoilerplate:
    """Verify no consumer package has inline CMake boilerplate."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.cmake_files = _find_cmake_files()
        assert len(self.cmake_files) == len(CONSUMER_PACKAGES), (
            f"Expected {len(CONSUMER_PACKAGES)} consumer CMakeLists.txt, "
            f"found {len(self.cmake_files)}"
        )

    @pytest.mark.parametrize(
        "pattern,description",
        BOILERPLATE_PATTERNS,
        ids=[desc for _, desc in BOILERPLATE_PATTERNS],
    )
    def test_pattern_not_in_consumers(self, pattern, description):
        """Each boilerplate pattern must have zero matches in consumer CMakeLists."""
        violations = []
        regex = re.compile(pattern)
        for pkg, cmake_path in self.cmake_files:
            with open(cmake_path, "r") as f:
                for line_no, line in enumerate(f, 1):
                    if regex.search(line):
                        violations.append(
                            f"  {pkg}/CMakeLists.txt:{line_no}: {line.strip()}"
                        )
        assert (
            not violations
        ), f"{description} found in consumer packages:\n" + "\n".join(violations)

    def test_consumers_use_find_package_common_utils(self):
        """Every consumer must have find_package(common_utils REQUIRED).

        This triggers CONFIG_EXTRAS auto-loading of PragatiDefaults and
        PragatiLintSkips — no explicit include() needed in consumers.
        """
        missing = []
        for pkg, cmake_path in self.cmake_files:
            with open(cmake_path, "r") as f:
                content = f.read()
            if "find_package(common_utils REQUIRED)" not in content:
                missing.append(pkg)
        assert (
            not missing
        ), f"Packages missing find_package(common_utils REQUIRED): {missing}"

    def test_consumers_no_explicit_include_pragmati(self):
        """Consumers must NOT have explicit include(PragatiDefaults/LintSkips).

        These are auto-loaded by find_package(common_utils) via CONFIG_EXTRAS.
        Explicit includes would fail because modules aren't on CMAKE_MODULE_PATH.
        """
        violations = []
        for pkg, cmake_path in self.cmake_files:
            with open(cmake_path, "r") as f:
                for line_no, line in enumerate(f, 1):
                    stripped = line.strip()
                    if stripped in (
                        "include(PragatiDefaults)",
                        "include(PragatiLintSkips)",
                    ):
                        violations.append(
                            f"  {pkg}/CMakeLists.txt:{line_no}: {stripped}"
                        )
        assert not violations, (
            "Consumers must not explicitly include Pragati modules "
            "(auto-loaded via CONFIG_EXTRAS):\n" + "\n".join(violations)
        )

    def test_consumers_have_common_utils_dependency(self):
        """Every consumer package.xml must declare common_utils as a dependency."""
        missing = []
        for pkg, _ in self.cmake_files:
            pkg_xml = os.path.join(SRC_DIR, pkg, "package.xml")
            if not os.path.isfile(pkg_xml):
                missing.append(f"{pkg} (no package.xml)")
                continue
            with open(pkg_xml, "r") as f:
                content = f.read()
            if "common_utils" not in content:
                missing.append(pkg)
        assert (
            not missing
        ), f"Packages missing common_utils dependency in package.xml: {missing}"
