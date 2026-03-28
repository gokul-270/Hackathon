# Copyright 2025 Pragati Robotics
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for cotton_detection_msgs extraction (Section 6)."""

import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class TestCottonDetectionMsgsPackage(unittest.TestCase):
    """Verify cotton_detection_msgs is a proper interface-only package."""

    def test_python_msg_imports(self):
        """All msg types importable from cotton_detection_msgs."""
        from cotton_detection_msgs.msg import CottonPosition
        from cotton_detection_msgs.msg import DetectionResult
        from cotton_detection_msgs.msg import PerformanceMetrics

        # Verify field existence
        cp = CottonPosition()
        self.assertTrue(hasattr(cp, 'position'))
        self.assertTrue(hasattr(cp, 'confidence'))
        self.assertTrue(hasattr(cp, 'detection_id'))
        self.assertTrue(hasattr(cp, 'header'))

        dr = DetectionResult()
        self.assertTrue(hasattr(dr, 'positions'))
        self.assertTrue(hasattr(dr, 'total_count'))
        self.assertTrue(hasattr(dr, 'detection_successful'))
        self.assertTrue(hasattr(dr, 'processing_time_ms'))

        pm = PerformanceMetrics()
        self.assertTrue(hasattr(pm, 'fps_actual'))
        self.assertTrue(hasattr(pm, 'latency_avg_ms'))
        self.assertTrue(hasattr(pm, 'uptime_seconds'))

    def test_python_srv_import(self):
        """Verify CottonDetection srv importable from msgs pkg."""
        from cotton_detection_msgs.srv import CottonDetection

        req = CottonDetection.Request()
        self.assertTrue(hasattr(req, 'detect_command'))

        resp = CottonDetection.Response()
        self.assertTrue(hasattr(resp, 'data'))
        self.assertTrue(hasattr(resp, 'success'))
        self.assertTrue(hasattr(resp, 'message'))

    def test_detection_result_references_cotton_position(self):
        """Verify DetectionResult.positions uses CottonPosition."""
        from cotton_detection_msgs.msg import DetectionResult

        fields = DetectionResult.get_fields_and_field_types()
        self.assertIn('positions', fields)
        self.assertIn(
            'cotton_detection_msgs/CottonPosition',
            fields['positions'],
        )


class TestCottonDetectionRos2NoInterfaces(unittest.TestCase):
    """Verify cotton_detection_ros2 no longer generates interfaces."""

    def _read_cmake(self):
        path = os.path.join(
            REPO_ROOT,
            'src',
            'cotton_detection_ros2',
            'CMakeLists.txt',
        )
        with open(path) as f:
            return f.read()

    def test_no_rosidl_generate_interfaces(self):
        """No rosidl_generate_interfaces in cotton_detection_ros2."""
        content = self._read_cmake()
        lines = content.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            self.assertNotIn(
                'rosidl_generate_interfaces',
                stripped,
                'cotton_detection_ros2 should not generate interfaces',
            )

    def test_depends_on_cotton_detection_msgs(self):
        """CMakeLists.txt finds cotton_detection_msgs."""
        content = self._read_cmake()
        self.assertIn(
            'find_package(cotton_detection_msgs REQUIRED)',
            content,
        )

    def test_package_xml_deps(self):
        """Package.xml depends on cotton_detection_msgs."""
        path = os.path.join(
            REPO_ROOT,
            'src',
            'cotton_detection_ros2',
            'package.xml',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('cotton_detection_msgs', content)
        self.assertNotIn('member_of_group', content)


class TestYanthraMoveConsumer(unittest.TestCase):
    """Verify yanthra_move uses cotton_detection_msgs."""

    def test_package_xml_depends_on_msgs(self):
        """Package.xml depends on cotton_detection_msgs."""
        path = os.path.join(
            REPO_ROOT,
            'src',
            'yanthra_move',
            'package.xml',
        )
        with open(path) as f:
            content = f.read()
        self.assertRegex(
            content,
            r'<depend>cotton_detection_msgs</depend>',
        )

    def test_package_xml_no_detection_ros2_dep(self):
        """Package.xml does not depend on cotton_detection_ros2."""
        path = os.path.join(
            REPO_ROOT,
            'src',
            'yanthra_move',
            'package.xml',
        )
        with open(path) as f:
            content = f.read()
        self.assertNotRegex(
            content,
            r'<depend>cotton_detection_ros2</depend>',
        )

    def test_cmake_uses_msgs_not_ros2(self):
        """CMakeLists.txt references cotton_detection_msgs."""
        path = os.path.join(
            REPO_ROOT,
            'src',
            'yanthra_move',
            'CMakeLists.txt',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn(
            'find_package(cotton_detection_msgs REQUIRED)',
            content,
        )

    def test_cpp_includes_use_msgs(self):
        """C++ sources include cotton_detection_msgs, not ros2."""
        src_dir = os.path.join(REPO_ROOT, 'src', 'yanthra_move')
        files_to_check = [
            'include/yanthra_move/yanthra_move_system.hpp',
            'src/yanthra_move_system_core.cpp',
            'src/yanthra_move_system_services.cpp',
            'src/yanthra_move_system_operation.cpp',
        ]
        include_pattern = re.compile(
            r'#include\s+[<"]cotton_detection_ros2/(msg|srv)/',
        )
        for rel_path in files_to_check:
            full_path = os.path.join(src_dir, rel_path)
            if not os.path.exists(full_path):
                continue
            with open(full_path) as f:
                content = f.read()
            matches = include_pattern.findall(content)
            self.assertEqual(
                len(matches),
                0,
                f'{rel_path} still includes ' 'cotton_detection_ros2 msg/srv',
            )
            self.assertIn(
                'cotton_detection_msgs',
                content,
                f'{rel_path}',
            )


if __name__ == '__main__':
    unittest.main()
