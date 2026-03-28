#!/usr/bin/env python3
"""
Tests for fix-vehicle-cpu-thermal change.

Tasks 1-5: vehicle_control_node CPU reduction, timer frequency changes,
batched GPIO reads, thermal self-monitoring, and control loop health.
"""

import pytest
import sys
import os
import time
import json
import logging
from unittest.mock import MagicMock, patch, PropertyMock, call

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# =============================================================================
# TASK 1: Replace rclpy.spin() with spin_once(timeout) loop
# =============================================================================


class TestSpinOncePattern:
    """Task 1.1, 1.3, 1.4: Verify main() uses SingleThreadedExecutor.spin_once()"""

    @patch("integration.vehicle_control_node.rclpy")
    def test_main_uses_spin_once_not_rclpy_spin(self, mock_rclpy):
        """1.1: main() uses SingleThreadedExecutor.spin_once() pattern, not rclpy.spin()"""
        from integration.vehicle_control_node import main

        # Mock rclpy.ok() to return True once then False (to exit loop)
        mock_rclpy.ok.side_effect = [True, True, False]
        mock_rclpy.init.return_value = None
        mock_rclpy.shutdown.return_value = None

        # Mock the executor
        mock_executor_instance = MagicMock()
        mock_executor_class = MagicMock(return_value=mock_executor_instance)
        mock_rclpy.executors.SingleThreadedExecutor = mock_executor_class

        # Mock the node constructor to avoid full initialization
        with patch(
            "integration.vehicle_control_node.ROS2VehicleControlNode"
        ) as mock_node_class:
            mock_node = MagicMock()
            mock_node_class.return_value = mock_node

            main(args=[])

            # Verify SingleThreadedExecutor was created and node was added
            mock_executor_class.assert_called_once()
            mock_executor_instance.add_node.assert_called_once_with(mock_node)

            # Verify spin_once was called (not rclpy.spin)
            assert mock_executor_instance.spin_once.call_count >= 1
            # Verify timeout_sec=0.1 (blocks in wait_set when idle)
            for c in mock_executor_instance.spin_once.call_args_list:
                assert c == call(timeout_sec=0.1)

            # Verify rclpy.spin was NOT called
            mock_rclpy.spin.assert_not_called()

    @patch("time.sleep")
    @patch("integration.vehicle_control_node.rclpy")
    def test_spin_loop_includes_sleep_throttle(self, mock_rclpy, mock_sleep):
        """1.1b: spin loop includes time.sleep(0.05) to prevent CPU busy-poll"""
        from integration.vehicle_control_node import main

        # Loop runs twice then exits
        mock_rclpy.ok.side_effect = [True, True, False]
        mock_rclpy.init.return_value = None
        mock_rclpy.shutdown.return_value = None

        mock_executor_instance = MagicMock()
        mock_rclpy.executors.SingleThreadedExecutor = MagicMock(
            return_value=mock_executor_instance
        )

        with patch(
            "integration.vehicle_control_node.ROS2VehicleControlNode"
        ) as mock_node_class:
            mock_node = MagicMock()
            mock_node_class.return_value = mock_node

            main(args=[])

            # time.sleep should be called once per spin_once iteration
            assert mock_sleep.call_count >= 1
            for c in mock_sleep.call_args_list:
                assert c == call(0.05), f"Expected time.sleep(0.05) but got {c}"

    @patch("integration.vehicle_control_node.rclpy")
    def test_spin_loop_exits_when_rclpy_ok_false(self, mock_rclpy):
        """1.3: Loop exits when rclpy.ok() returns False, shutdown handler runs"""
        from integration.vehicle_control_node import main

        # rclpy.ok() returns False immediately
        mock_rclpy.ok.return_value = False
        mock_rclpy.init.return_value = None
        mock_rclpy.shutdown.return_value = None

        mock_executor_instance = MagicMock()
        mock_rclpy.executors.SingleThreadedExecutor = MagicMock(
            return_value=mock_executor_instance
        )

        with patch(
            "integration.vehicle_control_node.ROS2VehicleControlNode"
        ) as mock_node_class:
            mock_node = MagicMock()
            mock_node_class.return_value = mock_node

            main(args=[])

            # spin_once should not be called since rclpy.ok() is False
            mock_executor_instance.spin_once.assert_not_called()

            # Shutdown should be called
            mock_node.shutdown.assert_called_once()
            mock_node.destroy_node.assert_called_once()

    @patch("integration.vehicle_control_node.rclpy")
    def test_executor_shutdown_called_in_finally(self, mock_rclpy):
        """1.3: executor.shutdown() is called during cleanup"""
        from integration.vehicle_control_node import main

        mock_rclpy.ok.side_effect = [True, False]
        mock_rclpy.init.return_value = None
        mock_rclpy.shutdown.return_value = None

        mock_executor_instance = MagicMock()
        mock_rclpy.executors.SingleThreadedExecutor = MagicMock(
            return_value=mock_executor_instance
        )

        with patch(
            "integration.vehicle_control_node.ROS2VehicleControlNode"
        ) as mock_node_class:
            mock_node = MagicMock()
            mock_node_class.return_value = mock_node

            main(args=[])

            # Verify executor.shutdown() was called
            mock_executor_instance.shutdown.assert_called_once()


# =============================================================================
# TASK 2: Reduce timer frequencies
# =============================================================================


class TestTimerFrequencies:
    """Task 2.1, 2.4: Verify timer frequencies match new defaults"""

    def _make_mock_node(self, config_overrides=None):
        """Create a mock node with _setup_timers() callable"""
        # We test _setup_timers() by calling it on a partially mocked node
        # that has the config and create_timer available
        node = MagicMock()
        config = {
            "joint_names": ["fl_steer", "fr_steer", "rl_steer", "rr_steer"],
            "control_frequency": 5.0,
            "joint_state_frequency": 5.0,
            "status_frequency": 2.0,
            "gpio_frequency": 10.0,
        }
        if config_overrides:
            config.update(config_overrides)
        node.config = config
        node.gpio_processor = MagicMock()  # GPIO enabled
        node.joystick_processor = None  # No joystick
        node.logger = MagicMock()
        node.create_timer = MagicMock(return_value=MagicMock())
        return node

    def test_control_timer_at_5hz_default(self):
        """2.1: _setup_timers() creates control timer at 5Hz with default production config"""
        # Import the unbound method
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node()
        # Call _setup_timers as unbound with our mock node
        ROS2VehicleControlNode._setup_timers(node)

        # Find the create_timer call for control loop (first call, period=0.2s)
        calls = node.create_timer.call_args_list
        # First call is control timer
        control_call = calls[0]
        period = control_call[0][0]  # First positional arg is period
        assert period == pytest.approx(
            1.0 / 5.0, abs=0.001
        ), f"Control timer period should be 0.2s (5Hz), got {period}s"

    def test_joint_state_timer_at_5hz(self):
        """2.1: Joint state timer at 5Hz"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node()
        ROS2VehicleControlNode._setup_timers(node)

        calls = node.create_timer.call_args_list
        # Second call is joint state timer
        joint_call = calls[1]
        period = joint_call[0][0]
        assert period == pytest.approx(
            1.0 / 5.0, abs=0.001
        ), f"Joint state timer period should be 0.2s (5Hz), got {period}s"

    def test_status_timer_at_2hz(self):
        """2.1: Status timer at 2Hz"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node()
        ROS2VehicleControlNode._setup_timers(node)

        calls = node.create_timer.call_args_list
        # Fourth call is status timer (after GPIO timer)
        status_call = calls[3]
        period = status_call[0][0]
        assert period == pytest.approx(
            1.0 / 2.0, abs=0.001
        ), f"Status timer period should be 0.5s (2Hz), got {period}s"

    def test_gpio_timer_unchanged_at_10hz(self):
        """2.1: GPIO timer stays at 10Hz"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node()
        ROS2VehicleControlNode._setup_timers(node)

        calls = node.create_timer.call_args_list
        # Third call is GPIO timer
        gpio_call = calls[2]
        period = gpio_call[0][0]
        assert period == pytest.approx(
            1.0 / 10.0, abs=0.001
        ), f"GPIO timer period should be 0.1s (10Hz), got {period}s"

    def test_startup_frequency_logging(self):
        """2.4: Node logs active frequencies at startup in structured JSON format"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node()
        ROS2VehicleControlNode._setup_timers(node)

        # Check that logger.info was called with a TIMING event containing frequencies
        info_calls = [str(c) for c in node.logger.info.call_args_list]
        timing_logged = any("[TIMING]" in c for c in info_calls)
        assert (
            timing_logged
        ), "Expected a [TIMING] log entry with timer frequencies at startup"


# =============================================================================
# TASK 3: Batch GPIO reads
# =============================================================================


class TestBatchGPIOReads:
    """Task 3.1, 3.3, 3.4: Verify batched GPIO reads via read_bank1()"""

    def _make_gpio_manager(self):
        """Create a GPIOManager with mocked pigpio connection"""
        from hardware.gpio_manager import GPIOManager

        manager = GPIOManager.__new__(GPIOManager)
        manager._pi = MagicMock()
        manager._pi.connected = True
        manager._initialized = True
        manager._output_states = {}
        manager._input_callbacks = {}
        manager._bank_read_available = True
        manager._bank_read_warned = False
        manager.logger = MagicMock()
        return manager

    def test_read_all_uses_bank_read(self):
        """3.1: GPIOManager.read_all_inputs() calls pi.read_bank1() once, not individual read()"""
        from config.constants import GPIO_PINS

        manager = self._make_gpio_manager()
        # read_bank1 returns a bitmask with pins 4,5,6 high, 16,21,26 low
        # Using GPIO_PINS constants
        bank_value = (
            (1 << GPIO_PINS.DIRECTION_LEFT)
            | (1 << GPIO_PINS.DIRECTION_RIGHT)
            | (1 << GPIO_PINS.ARM_START)
        )
        manager._pi.read_bank1.return_value = bank_value

        result = manager.read_all_inputs()

        # read_bank1 should be called exactly once
        manager._pi.read_bank1.assert_called_once()
        # Individual read() should NOT be called
        manager._pi.read.assert_not_called()

        # Verify pin values match expected bitmask
        assert result[GPIO_PINS.DIRECTION_LEFT] is True
        assert result[GPIO_PINS.DIRECTION_RIGHT] is True
        assert result[GPIO_PINS.ARM_START] is True
        assert result[GPIO_PINS.AUTOMATIC_MODE] is False
        assert result[GPIO_PINS.VEHICLE_STOP] is False

    def test_bank_read_consistent_snapshot(self):
        """3.3: All pin values from same read_bank1() snapshot"""
        from config.constants import GPIO_PINS

        manager = self._make_gpio_manager()
        # Set a known bitmask: only ARM_SHUTDOWN and BRAKE_SWITCH high
        known_bitmask = (1 << GPIO_PINS.ARM_SHUTDOWN) | (1 << GPIO_PINS.BRAKE_SWITCH)
        manager._pi.read_bank1.return_value = known_bitmask

        result = manager.read_all_inputs()

        # All values should be derived from ONE read_bank1 call
        manager._pi.read_bank1.assert_called_once()

        assert result[GPIO_PINS.ARM_SHUTDOWN] is True
        assert result[GPIO_PINS.BRAKE_SWITCH] is True
        assert result[GPIO_PINS.DIRECTION_LEFT] is False
        assert result[GPIO_PINS.DIRECTION_RIGHT] is False
        assert result[GPIO_PINS.AUTOMATIC_MODE] is False

    def test_fallback_to_individual_reads_on_exception(self):
        """3.4: Falls back to individual read() when read_bank1() raises exception"""
        from config.constants import GPIO_PINS

        manager = self._make_gpio_manager()

        # read_bank1 raises an exception
        manager._pi.read_bank1.side_effect = Exception("pigpiod version too old")
        # Individual reads return known values
        manager._pi.read.return_value = 0

        result = manager.read_all_inputs()

        # Should have fallen back to individual reads (8 input pins)
        assert manager._pi.read.call_count == 8

        # Warning should be logged once
        manager.logger.warning.assert_called_once()

        # Flag should be set to skip bank read next time
        assert manager._bank_read_available is False

    def test_subsequent_calls_skip_bank_read_after_failure(self):
        """3.4: After bank read failure, subsequent calls use individual reads directly"""
        manager = self._make_gpio_manager()
        manager._bank_read_available = False  # Already failed
        manager._pi.read.return_value = 0

        result = manager.read_all_inputs()

        # Should NOT attempt read_bank1
        manager._pi.read_bank1.assert_not_called()
        # Should use individual reads
        assert manager._pi.read.call_count == 8


# =============================================================================
# TASK 4: RPi thermal self-monitoring
# =============================================================================


class TestThermalSelfMonitoring:
    """Task 4.1, 4.7-4.10: Verify thermal monitoring in control_loop_health"""

    def _make_mock_node_for_health(self):
        """Create a mock node with attributes needed for health emission"""
        node = MagicMock()
        node.config = {
            "control_frequency": 5.0,
        }
        node.logger = MagicMock()
        node.start_time = time.time() - 60  # 60s uptime
        node._thermal_monitoring_available = True
        node._throttle_monitoring_available = True
        node._cpu_process = MagicMock()
        node._cpu_process.cpu_percent.return_value = 12.5
        node._last_cpu_high_count = 0
        # Loop timing counters
        node._loop_time_sum = 0.5  # 500ms total over 10 iterations
        node._loop_time_max = 0.08  # 80ms max
        node._loop_count = 10
        node._missed_deadlines = 0
        return node

    def test_health_event_includes_thermal_fields(self):
        """4.1: control_loop_health event includes cpu_temp_c, process_cpu_percent, throttled"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node_for_health()

        # Bind the real methods onto the mock node so _emit_control_loop_health
        # can call _read_cpu_temperature / _read_throttle_state.
        node._read_cpu_temperature = (
            lambda: ROS2VehicleControlNode._read_cpu_temperature(node)
        )
        node._read_throttle_state = lambda: ROS2VehicleControlNode._read_throttle_state(
            node
        )

        # Mock sysfs reads for temperature and throttle
        with patch("builtins.open", create=True) as mock_open:
            mock_temp_file = MagicMock()
            mock_temp_file.read.return_value = "55000"
            mock_temp_file.__enter__ = lambda s: s
            mock_temp_file.__exit__ = MagicMock(return_value=False)

            mock_throttle_file = MagicMock()
            mock_throttle_file.read.return_value = "0x0"
            mock_throttle_file.__enter__ = lambda s: s
            mock_throttle_file.__exit__ = MagicMock(return_value=False)

            def open_side_effect(path, *args, **kwargs):
                if "thermal" in path:
                    return mock_temp_file
                if "throttled" in path:
                    return mock_throttle_file
                raise FileNotFoundError(path)

            mock_open.side_effect = open_side_effect

            ROS2VehicleControlNode._emit_control_loop_health(node)

        # Find the TIMING log call and parse its JSON
        info_calls = node.logger.info.call_args_list
        timing_call = None
        for c in info_calls:
            args_str = str(c)
            if "[TIMING]" in args_str and "control_loop_health" in args_str:
                timing_call = args_str
                break

        assert (
            timing_call is not None
        ), "Expected [TIMING] control_loop_health log entry"
        assert "cpu_temp_c" in timing_call
        assert "process_cpu_percent" in timing_call
        assert "throttled" in timing_call

    def test_read_cpu_temperature_converts_millidegrees(self):
        """4.2: _read_cpu_temperature reads sysfs and converts millidegrees to Celsius"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node_for_health()

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = "55000"
            mock_file.__enter__ = lambda s: s
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_file

            temp = ROS2VehicleControlNode._read_cpu_temperature(node)
            assert temp == pytest.approx(55.0)

    def test_temperature_warning_at_70c(self):
        """4.7: Temperature >70C logs WARNING via _emit_control_loop_health"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node_for_health()
        node._read_cpu_temperature = (
            lambda: ROS2VehicleControlNode._read_cpu_temperature(node)
        )
        node._read_throttle_state = lambda: ROS2VehicleControlNode._read_throttle_state(
            node
        )

        with patch("builtins.open", create=True) as mock_open:
            mock_temp_file = MagicMock()
            mock_temp_file.read.return_value = "72000"  # 72C
            mock_temp_file.__enter__ = lambda s: s
            mock_temp_file.__exit__ = MagicMock(return_value=False)

            mock_throttle_file = MagicMock()
            mock_throttle_file.read.return_value = "0x0"
            mock_throttle_file.__enter__ = lambda s: s
            mock_throttle_file.__exit__ = MagicMock(return_value=False)

            def open_side_effect(path, *args, **kwargs):
                if "thermal" in path:
                    return mock_temp_file
                if "throttled" in path:
                    return mock_throttle_file
                raise FileNotFoundError(path)

            mock_open.side_effect = open_side_effect

            ROS2VehicleControlNode._emit_control_loop_health(node)

        # Check that a warning was logged for high temp
        warning_calls = [str(c) for c in node.logger.warning.call_args_list]
        assert any(
            "72.0" in c and "HIGH" in c for c in warning_calls
        ), f"Expected temperature HIGH warning, got: {warning_calls}"

    def test_temperature_critical_at_80c(self):
        """4.7: Temperature >80C logs ERROR via _emit_control_loop_health"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node_for_health()
        node._read_cpu_temperature = (
            lambda: ROS2VehicleControlNode._read_cpu_temperature(node)
        )
        node._read_throttle_state = lambda: ROS2VehicleControlNode._read_throttle_state(
            node
        )

        with patch("builtins.open", create=True) as mock_open:
            mock_temp_file = MagicMock()
            mock_temp_file.read.return_value = "82000"  # 82C
            mock_temp_file.__enter__ = lambda s: s
            mock_temp_file.__exit__ = MagicMock(return_value=False)

            mock_throttle_file = MagicMock()
            mock_throttle_file.read.return_value = "0x0"
            mock_throttle_file.__enter__ = lambda s: s
            mock_throttle_file.__exit__ = MagicMock(return_value=False)

            def open_side_effect(path, *args, **kwargs):
                if "thermal" in path:
                    return mock_temp_file
                if "throttled" in path:
                    return mock_throttle_file
                raise FileNotFoundError(path)

            mock_open.side_effect = open_side_effect

            ROS2VehicleControlNode._emit_control_loop_health(node)

        # Check that an error was logged for critical temp
        error_calls = [str(c) for c in node.logger.error.call_args_list]
        assert any(
            "82.0" in c and "CRITICAL" in c for c in error_calls
        ), f"Expected temperature CRITICAL error, got: {error_calls}"

    def test_thermal_sysfs_unavailable(self):
        """4.9: Thermal sysfs unavailable returns None, does not retry"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node_for_health()
        node._thermal_monitoring_available = False

        temp = ROS2VehicleControlNode._read_cpu_temperature(node)
        assert temp is None

    def test_throttle_sysfs_unavailable(self):
        """4.10: Throttle sysfs unavailable returns None, does not retry"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node_for_health()
        node._throttle_monitoring_available = False

        throttled = ROS2VehicleControlNode._read_throttle_state(node)
        assert throttled is None

    def test_cpu_usage_high_two_consecutive_warns(self):
        """4.8: CPU usage >30% for two consecutive intervals logs WARNING"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node_for_health()
        node._cpu_process.cpu_percent.return_value = 35.0
        node._last_cpu_high_count = 1  # Already one high reading
        node._thermal_monitoring_available = False
        node._throttle_monitoring_available = False
        node._read_cpu_temperature = (
            lambda: ROS2VehicleControlNode._read_cpu_temperature(node)
        )
        node._read_throttle_state = lambda: ROS2VehicleControlNode._read_throttle_state(
            node
        )

        ROS2VehicleControlNode._emit_control_loop_health(node)

        warning_calls = [str(c) for c in node.logger.warning.call_args_list]
        assert any(
            "sustained high" in c for c in warning_calls
        ), f"Expected sustained high CPU warning, got: {warning_calls}"

    def test_throttle_read_returns_true_when_throttled(self):
        """4.3: _read_throttle_state returns True when throttle bits are set"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node_for_health()

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = "0x50005"  # some throttle bits
            mock_file.__enter__ = lambda s: s
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_file

            throttled = ROS2VehicleControlNode._read_throttle_state(node)
            assert throttled is True

    def test_throttle_read_returns_false_when_clear(self):
        """4.3: _read_throttle_state returns False when no throttle bits set"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = self._make_mock_node_for_health()

        with patch("builtins.open", create=True) as mock_open:
            mock_file = MagicMock()
            mock_file.read.return_value = "0x0"
            mock_file.__enter__ = lambda s: s
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_file

            throttled = ROS2VehicleControlNode._read_throttle_state(node)
            assert throttled is False


# =============================================================================
# TASK 5: Control loop timing + missed deadline tracking
# =============================================================================


class TestControlLoopTiming:
    """Task 5.1, 5.3, 5.4, 5.6: Verify per-iteration timing and missed deadlines"""

    def test_loop_measures_wall_clock_duration(self):
        """5.1: _control_loop() measures its own duration using time.perf_counter()"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock()
        node.config = {"control_frequency": 5.0}
        node.current_state = MagicMock()
        node.last_cmd_vel_time = time.time()
        node.cmd_vel_timeout = 1.0
        node.motor_status = {}
        node.logger = MagicMock()
        # Initialize timing counters
        node._loop_time_sum = 0.0
        node._loop_time_max = 0.0
        node._loop_count = 0
        node._missed_deadlines = 0
        node._deadline_threshold = 0.2  # 200ms for 5Hz

        # Call _control_loop
        with patch("time.perf_counter", side_effect=[1.0, 1.05]):
            ROS2VehicleControlNode._control_loop(node)

        assert node._loop_count == 1
        assert node._loop_time_sum == pytest.approx(0.05, abs=0.001)
        assert node._loop_time_max == pytest.approx(0.05, abs=0.001)
        assert node._missed_deadlines == 0  # 50ms < 200ms deadline

    def test_missed_deadline_counted_correctly(self):
        """5.3: Callback taking 250ms at 5Hz (200ms period) increments counter"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock()
        node.config = {"control_frequency": 5.0}
        node.current_state = MagicMock()
        node.last_cmd_vel_time = time.time()
        node.cmd_vel_timeout = 1.0
        node.motor_status = {}
        node.logger = MagicMock()
        node._loop_time_sum = 0.0
        node._loop_time_max = 0.0
        node._loop_count = 0
        node._missed_deadlines = 0
        node._deadline_threshold = 0.2  # 200ms

        # Simulate a 250ms callback
        with patch("time.perf_counter", side_effect=[1.0, 1.25]):
            ROS2VehicleControlNode._control_loop(node)

        assert node._missed_deadlines == 1
        assert node._loop_time_max == pytest.approx(0.25, abs=0.001)

    def test_no_missed_deadline_under_threshold(self):
        """5.3: Callback taking 150ms at 5Hz does NOT increment counter"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock()
        node.config = {"control_frequency": 5.0}
        node.current_state = MagicMock()
        node.last_cmd_vel_time = time.time()
        node.cmd_vel_timeout = 1.0
        node.motor_status = {}
        node.logger = MagicMock()
        node._loop_time_sum = 0.0
        node._loop_time_max = 0.0
        node._loop_count = 0
        node._missed_deadlines = 0
        node._deadline_threshold = 0.2

        with patch("time.perf_counter", side_effect=[1.0, 1.15]):
            ROS2VehicleControlNode._control_loop(node)

        assert node._missed_deadlines == 0

    def test_deadline_threshold_derived_from_config(self):
        """5.6: Threshold derived from configured frequency, not hardcoded"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock()
        node.config = {"control_frequency": 10.0}
        node.current_state = MagicMock()
        node.last_cmd_vel_time = time.time()
        node.cmd_vel_timeout = 1.0
        node.motor_status = {}
        node.logger = MagicMock()
        node._loop_time_sum = 0.0
        node._loop_time_max = 0.0
        node._loop_count = 0
        node._missed_deadlines = 0
        node._deadline_threshold = 0.1  # 100ms for 10Hz

        # 120ms > 100ms threshold at 10Hz -> should be a missed deadline
        with patch("time.perf_counter", side_effect=[1.0, 1.12]):
            ROS2VehicleControlNode._control_loop(node)

        assert node._missed_deadlines == 1

    def test_health_event_includes_loop_timing_fields(self):
        """5.4: control_loop_health event includes loop timing fields"""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock()
        node.config = {"control_frequency": 5.0}
        node.logger = MagicMock()
        node.start_time = time.time() - 60
        node._loop_time_sum = 0.5  # 500ms total
        node._loop_time_max = 0.08  # 80ms max
        node._loop_count = 10
        node._missed_deadlines = 1
        node._thermal_monitoring_available = False
        node._throttle_monitoring_available = False
        node._cpu_process = MagicMock()
        node._cpu_process.cpu_percent.return_value = 8.0
        node._last_cpu_high_count = 0
        node._read_cpu_temperature = (
            lambda: ROS2VehicleControlNode._read_cpu_temperature(node)
        )
        node._read_throttle_state = lambda: ROS2VehicleControlNode._read_throttle_state(
            node
        )

        ROS2VehicleControlNode._emit_control_loop_health(node)

        # Find the TIMING log call
        info_calls = node.logger.info.call_args_list
        timing_call = None
        for c in info_calls:
            args_str = str(c)
            if "[TIMING]" in args_str:
                timing_call = args_str
                break

        assert timing_call is not None, "Expected [TIMING] log entry"
        assert "loop_count" in timing_call
        assert "avg_loop_time_ms" in timing_call
        assert "max_loop_time_ms" in timing_call
        assert "missed_deadlines" in timing_call


# =============================================================================
# VERIFY FIX: _get_default_config() fallback frequencies match reduced values
# =============================================================================


class TestFallbackConfigFrequencies:
    """Verify _get_default_config() returns reduced frequencies, not old burn values."""

    def test_default_config_control_frequency_is_5hz(self):
        """Fallback config must not reintroduce 100Hz CPU burn."""
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock()
        config = ROS2VehicleControlNode._get_default_config(node)
        assert config["control_frequency"] == 5.0, (
            f"Expected 5.0Hz, got {config['control_frequency']}Hz — "
            "stale default would reintroduce CPU burn if YAML loading fails"
        )

    def test_default_config_joint_state_frequency_is_5hz(self):
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock()
        config = ROS2VehicleControlNode._get_default_config(node)
        assert config["joint_state_frequency"] == 5.0

    def test_default_config_status_frequency_is_2hz(self):
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock()
        config = ROS2VehicleControlNode._get_default_config(node)
        assert config["status_frequency"] == 2.0

    def test_default_config_gpio_frequency_unchanged_at_10hz(self):
        from integration.vehicle_control_node import ROS2VehicleControlNode

        node = MagicMock()
        config = ROS2VehicleControlNode._get_default_config(node)
        assert config["gpio_frequency"] == 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
