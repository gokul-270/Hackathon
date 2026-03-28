#!/usr/bin/env python3
"""
Shared pytest configuration for vehicle_control tests.

Adds required package paths to sys.path so that imports like
`from core.safety_manager import SafetyManager` and
`from common_utils.consecutive_failure_tracker import ConsecutiveFailureTracker`
resolve correctly without needing colcon/pip install.
"""

import os
import sys

# Root of src/vehicle_control/ — needed for `from core.*`, `from hardware.*`, etc.
_vehicle_control_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _vehicle_control_dir not in sys.path:
    sys.path.insert(0, _vehicle_control_dir)

# Root of src/common_utils/ — needed for `from common_utils.*` imports
_common_utils_dir = os.path.join(os.path.dirname(_vehicle_control_dir), "common_utils")
if _common_utils_dir not in sys.path:
    sys.path.insert(0, _common_utils_dir)
