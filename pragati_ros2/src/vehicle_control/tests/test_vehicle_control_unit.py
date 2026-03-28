#!/usr/bin/env python3
"""
Unit Tests for Vehicle Control System
Tests core components: state machine, circuit breaker, steering calculations
"""
import pytest
import time
import math
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config.constants import VehicleState, PivotDirection, GEAR_RATIOS, PHYSICAL
from core.state_machine import VehicleStateMachine, StateTransition
from utils.circuit_breaker import CircuitBreaker, CircuitBreakerState, CircuitBreakerError, RetryPolicy
from hardware.advanced_steering import AdvancedSteeringController, SteeringAngles


# =============================================================================
# STATE MACHINE TESTS
# =============================================================================

class TestVehicleStateMachine:
    """Test state machine functionality"""
    
    def test_initial_state(self):
        """State machine starts in UNKNOWN state"""
        sm = VehicleStateMachine()
        assert sm.current_state == VehicleState.UNKNOWN
    
    def test_valid_transition_unknown_to_manual(self):
        """Can transition from UNKNOWN to MANUAL_MODE"""
        sm = VehicleStateMachine()
        result = sm.transition_to(VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL)
        assert result == True
        assert sm.current_state == VehicleState.MANUAL_MODE
    
    def test_valid_transition_unknown_to_automatic(self):
        """Can transition from UNKNOWN to AUTOMATIC_MODE"""
        sm = VehicleStateMachine()
        result = sm.transition_to(VehicleState.AUTOMATIC_MODE, StateTransition.MODE_SWITCH_AUTO)
        assert result == True
        assert sm.current_state == VehicleState.AUTOMATIC_MODE
    
    def test_valid_transition_manual_to_automatic(self):
        """Can transition from MANUAL to AUTOMATIC"""
        sm = VehicleStateMachine()
        sm.transition_to(VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL)
        result = sm.transition_to(VehicleState.AUTOMATIC_MODE, StateTransition.MODE_SWITCH_AUTO)
        assert result == True
        assert sm.current_state == VehicleState.AUTOMATIC_MODE
    
    def test_valid_transition_manual_to_left(self):
        """Can transition from MANUAL to MANUAL_LEFT"""
        sm = VehicleStateMachine()
        sm.transition_to(VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL)
        result = sm.transition_to(VehicleState.MANUAL_LEFT, StateTransition.DIRECTION_LEFT)
        assert result == True
        assert sm.current_state == VehicleState.MANUAL_LEFT
    
    def test_valid_transition_manual_to_right(self):
        """Can transition from MANUAL to MANUAL_RIGHT"""
        sm = VehicleStateMachine()
        sm.transition_to(VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL)
        result = sm.transition_to(VehicleState.MANUAL_RIGHT, StateTransition.DIRECTION_RIGHT)
        assert result == True
        assert sm.current_state == VehicleState.MANUAL_RIGHT
    
    def test_invalid_transition_automatic_to_left(self):
        """Cannot transition from AUTOMATIC to MANUAL_LEFT directly"""
        sm = VehicleStateMachine()
        sm.transition_to(VehicleState.AUTOMATIC_MODE, StateTransition.MODE_SWITCH_AUTO)
        result = sm.transition_to(VehicleState.MANUAL_LEFT, StateTransition.DIRECTION_LEFT)
        assert result == False
        assert sm.current_state == VehicleState.AUTOMATIC_MODE
    
    def test_error_transition_always_valid(self):
        """Can transition to ERROR from most states"""
        sm = VehicleStateMachine()
        sm.transition_to(VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL)
        result = sm.transition_to(VehicleState.ERROR, StateTransition.ERROR_OCCURRED)
        assert result == True
        assert sm.current_state == VehicleState.ERROR
    
    def test_previous_state_tracking(self):
        """Previous state is tracked correctly"""
        sm = VehicleStateMachine()
        sm.transition_to(VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL)
        sm.transition_to(VehicleState.AUTOMATIC_MODE, StateTransition.MODE_SWITCH_AUTO)
        assert sm.previous_state == VehicleState.MANUAL_MODE
    
    def test_state_listener_callback(self):
        """State change listeners are called"""
        sm = VehicleStateMachine()
        callback_called = False
        received_context = None
        
        def listener(context):
            nonlocal callback_called, received_context
            callback_called = True
            received_context = context
        
        sm.add_listener(listener)
        sm.transition_to(VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL)
        
        assert callback_called == True
        assert received_context is not None
        assert received_context.previous_state == VehicleState.UNKNOWN
    
    def test_system_reset_transition(self):
        """SYSTEM_RESET is accessible from most states"""
        sm = VehicleStateMachine()
        sm.transition_to(VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL)
        result = sm.transition_to(VehicleState.SYSTEM_RESET, StateTransition.SYSTEM_RESET)
        assert result == True
        assert sm.current_state == VehicleState.SYSTEM_RESET


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

class TestCircuitBreaker:
    """Test circuit breaker functionality"""
    
    def test_initial_state_closed(self):
        """Circuit breaker starts in CLOSED state"""
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitBreakerState.CLOSED
    
    def test_successful_call_stays_closed(self):
        """Successful calls keep circuit breaker closed"""
        cb = CircuitBreaker(failure_threshold=3)
        
        @cb
        def successful_func():
            return "success"
        
        result = successful_func()
        assert result == "success"
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
    
    def test_failure_increments_count(self):
        """Failed calls increment failure count"""
        cb = CircuitBreaker(failure_threshold=3)
        
        @cb
        def failing_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            failing_func()
        
        assert cb.failure_count == 1
        assert cb.state == CircuitBreakerState.CLOSED
    
    def test_circuit_opens_after_threshold(self):
        """Circuit opens after reaching failure threshold"""
        cb = CircuitBreaker(failure_threshold=2)
        
        @cb
        def failing_func():
            raise ValueError("Test error")
        
        # First failure
        with pytest.raises(ValueError):
            failing_func()
        assert cb.state == CircuitBreakerState.CLOSED
        
        # Second failure - should open
        with pytest.raises(ValueError):
            failing_func()
        assert cb.state == CircuitBreakerState.OPEN
    
    def test_open_circuit_raises_error(self):
        """Open circuit raises CircuitBreakerError"""
        cb = CircuitBreaker(failure_threshold=1)
        
        @cb
        def failing_func():
            raise ValueError("Test error")
        
        # Trigger opening
        with pytest.raises(ValueError):
            failing_func()
        
        # Next call should raise CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            failing_func()
    
    def test_circuit_half_open_after_timeout(self):
        """Circuit becomes HALF_OPEN after recovery timeout"""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        
        @cb
        def failing_func():
            raise ValueError("Test error")
        
        # Open circuit
        with pytest.raises(ValueError):
            failing_func()
        assert cb.state == CircuitBreakerState.OPEN
        
        # Wait for recovery timeout
        time.sleep(0.02)
        
        # Next call should be allowed (HALF_OPEN)
        cb._allow_request()
        assert cb.state == CircuitBreakerState.HALF_OPEN
    
    def test_circuit_closes_after_success_threshold(self):
        """Circuit closes after success_threshold successes in HALF_OPEN"""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01, success_threshold=1)
        
        call_count = 0
        
        @cb
        def sometimes_failing_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First call fails")
            return "success"
        
        # Open circuit
        with pytest.raises(ValueError):
            sometimes_failing_func()
        assert cb.state == CircuitBreakerState.OPEN
        
        # Wait for recovery
        time.sleep(0.02)
        
        # Successful call should close circuit
        result = sometimes_failing_func()
        assert result == "success"
        assert cb.state == CircuitBreakerState.CLOSED
    
    def test_success_resets_failure_count(self):
        """Successful call resets failure count in CLOSED state"""
        cb = CircuitBreaker(failure_threshold=3)
        
        fail_count = 0
        
        @cb
        def controlled_func(should_fail=False):
            if should_fail:
                raise ValueError("Controlled failure")
            return "success"
        
        # One failure
        with pytest.raises(ValueError):
            controlled_func(should_fail=True)
        assert cb.failure_count == 1
        
        # One success should reset
        controlled_func(should_fail=False)
        assert cb.failure_count == 0
    
    def test_force_open(self):
        """force_open() manually opens circuit"""
        cb = CircuitBreaker(failure_threshold=10)
        assert cb.state == CircuitBreakerState.CLOSED
        
        cb.force_open()
        assert cb.state == CircuitBreakerState.OPEN
    
    def test_force_close(self):
        """force_close() manually closes circuit"""
        cb = CircuitBreaker(failure_threshold=1)
        
        @cb
        def failing_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            failing_func()
        assert cb.state == CircuitBreakerState.OPEN
        
        cb.force_close()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
    
    def test_get_stats(self):
        """get_stats() returns correct statistics"""
        cb = CircuitBreaker(failure_threshold=3)
        
        stats = cb.get_stats()
        assert stats['state'] == 'CLOSED'
        assert stats['failure_count'] == 0
        assert stats['success_count'] == 0


# =============================================================================
# ADVANCED STEERING TESTS
# =============================================================================

class MockMotorInterface:
    """Mock motor interface for testing steering calculations"""
    
    def __init__(self):
        self.positions = {}
        self.move_calls = []
    
    def move_to_position(self, motor_id, position):
        self.positions[motor_id] = position
        self.move_calls.append((motor_id, position))
        return True


class TestAdvancedSteering:
    """Test Ackermann steering calculations"""
    
    @pytest.fixture
    def steering_controller(self):
        mock_interface = MockMotorInterface()
        return AdvancedSteeringController(mock_interface)
    
    def test_straight_steering_returns_zero(self, steering_controller):
        """Zero input returns zero angles"""
        angles = steering_controller.calculate_ackermann_angles(0.0)
        assert angles.left == 0.0
        assert angles.right == 0.0
    
    def test_small_input_returns_zero(self, steering_controller):
        """Very small input (< 0.001) returns zero angles"""
        angles = steering_controller.calculate_ackermann_angles(0.0001)
        assert angles.left == 0.0
        assert angles.right == 0.0
    
    def test_right_turn_different_angles(self, steering_controller):
        """Right turn produces different left/right angles (Ackermann geometry)"""
        angles = steering_controller.calculate_ackermann_angles(0.5)
        # In Ackermann steering, inside wheel turns more than outside
        # For right turn, right wheel is inside (larger angle)
        assert angles.left != angles.right
        assert angles.left > 0  # Positive rotation for right turn
        assert angles.right > 0
    
    def test_left_turn_different_angles(self, steering_controller):
        """Left turn produces different left/right angles"""
        angles = steering_controller.calculate_ackermann_angles(-0.5)
        assert angles.left != angles.right
        assert angles.left < 0  # Negative rotation for left turn
        assert angles.right < 0
    
    def test_symmetry_of_left_right_turns(self, steering_controller):
        """Left and right turns are symmetric"""
        right_angles = steering_controller.calculate_ackermann_angles(0.5)
        left_angles = steering_controller.calculate_ackermann_angles(-0.5)
        
        # The magnitudes should be approximately symmetric
        assert abs(right_angles.left) == pytest.approx(abs(left_angles.right), rel=0.01)
        assert abs(right_angles.right) == pytest.approx(abs(left_angles.left), rel=0.01)
    
    def test_three_wheel_steering_calculates_front(self, steering_controller):
        """Three-wheel steering includes front wheel calculation"""
        angles = steering_controller.calculate_three_wheel_ackermann_angles(0.5)
        assert angles.left != 0
        assert angles.right != 0
        assert angles.front != 0  # Front wheel should also have angle
    
    def test_three_wheel_straight_returns_zero(self, steering_controller):
        """Three-wheel steering with zero input returns all zeros"""
        angles = steering_controller.calculate_three_wheel_ackermann_angles(0.0)
        assert angles.left == 0.0
        assert angles.right == 0.0
        assert angles.front == 0.0
    
    def test_apply_ackermann_steering_calls_motors(self, steering_controller):
        """apply_ackermann_steering sends commands to motors"""
        mock = steering_controller.motor_interface
        
        result = steering_controller.apply_ackermann_steering(0.3)
        
        assert result == True
        assert len(mock.move_calls) == 2  # Left and right steering motors
    
    def test_steering_angles_dataclass(self):
        """SteeringAngles dataclass works correctly"""
        angles = SteeringAngles(left=1.0, right=2.0, front=0.5)
        assert angles.left == 1.0
        assert angles.right == 2.0
        assert angles.front == 0.5
    
    def test_steering_angles_default_front(self):
        """SteeringAngles front defaults to 0.0"""
        angles = SteeringAngles(left=1.0, right=2.0)
        assert angles.front == 0.0


# =============================================================================
# PIVOT MODE TESTS
# =============================================================================

class TestPivotMode:
    """Test pivot mode functionality"""
    
    @pytest.fixture
    def steering_controller(self):
        mock_interface = MockMotorInterface()
        return AdvancedSteeringController(mock_interface)
    
    def test_pivot_direction_enum(self):
        """PivotDirection enum has correct values"""
        assert PivotDirection.LEFT is not None
        assert PivotDirection.RIGHT is not None
        assert PivotDirection.NONE is not None
    
    def test_set_pivot_mode_left(self, steering_controller):
        """Setting pivot mode LEFT positions wheels correctly"""
        result = steering_controller.set_pivot_mode(PivotDirection.LEFT)
        assert result == True
        
        mock = steering_controller.motor_interface
        # Should have set steering motors to 90 degree positions
        assert len(mock.move_calls) >= 2
    
    def test_set_pivot_mode_right(self, steering_controller):
        """Setting pivot mode RIGHT positions wheels correctly"""
        result = steering_controller.set_pivot_mode(PivotDirection.RIGHT)
        assert result == True
    
    def test_set_pivot_mode_none(self, steering_controller):
        """Setting pivot mode NONE straightens wheels"""
        result = steering_controller.set_pivot_mode(PivotDirection.NONE)
        assert result == True


# =============================================================================
# CONSTANTS TESTS
# =============================================================================

class TestConstants:
    """Test configuration constants are valid"""
    
    def test_gear_ratios_positive(self):
        """Gear ratios are positive values"""
        assert GEAR_RATIOS.STEERING_MOTOR > 0
        assert GEAR_RATIOS.DRIVE_MOTOR > 0
    
    def test_physical_dimensions_positive(self):
        """Physical dimensions are positive values"""
        assert PHYSICAL.WHEEL_BASE > 0
        assert PHYSICAL.WHEEL_TREAD > 0
        assert PHYSICAL.WHEEL_DIAMETER > 0
    
    def test_vehicle_states_exist(self):
        """All expected vehicle states exist"""
        expected_states = [
            VehicleState.UNKNOWN,
            VehicleState.MANUAL_MODE,
            VehicleState.AUTOMATIC_MODE,
            VehicleState.ERROR,
            VehicleState.IDLING,
        ]
        for state in expected_states:
            assert state is not None


# =============================================================================
# INTEGRATION TESTS (without ROS)
# =============================================================================

class TestIntegration:
    """Integration tests for vehicle control components"""
    
    def test_state_machine_with_circuit_breaker(self):
        """State machine and circuit breaker work together"""
        sm = VehicleStateMachine()
        cb = CircuitBreaker(failure_threshold=3)
        
        # Wrap state transition in circuit breaker
        @cb
        def safe_transition(new_state, trigger):
            return sm.transition_to(new_state, trigger)
        
        # Successful transitions
        result = safe_transition(VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL)
        assert result == True
        assert cb.state == CircuitBreakerState.CLOSED
    
    def test_steering_with_state_check(self):
        """Steering only works in appropriate states"""
        sm = VehicleStateMachine()
        mock_interface = MockMotorInterface()
        steering = AdvancedSteeringController(mock_interface)
        
        # In MANUAL_MODE, steering should work
        sm.transition_to(VehicleState.MANUAL_MODE, StateTransition.MODE_SWITCH_MANUAL)
        
        if sm.current_state in [VehicleState.MANUAL_MODE, VehicleState.MANUAL_LEFT, VehicleState.MANUAL_RIGHT]:
            result = steering.apply_ackermann_steering(0.3)
            assert result == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
