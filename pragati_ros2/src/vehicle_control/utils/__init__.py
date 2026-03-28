"""
Utilities module for Vehicle Control System
Contains logging utilities, input processing, and helper functions
"""

from .logging_utils import (
    setup_logging,
    get_logger,
    PerformanceLogger,
    ErrorLogger,
    log_function_call,
    log_motor_command,
    log_state_transition,
    log_safety_event
)

try:
    from .input_processing import JoystickProcessor, GPIOProcessor
    __all__ = [
        'setup_logging',
        'get_logger', 
        'PerformanceLogger',
        'ErrorLogger',
        'log_function_call',
        'log_motor_command',
        'log_state_transition',
        'log_safety_event',
        'JoystickProcessor',
        'GPIOProcessor'
    ]
except ImportError:
    # input_processing module might not be available
    __all__ = [
        'setup_logging',
        'get_logger',
        'PerformanceLogger', 
        'ErrorLogger',
        'log_function_call',
        'log_motor_command',
        'log_state_transition',
        'log_safety_event'
    ]
