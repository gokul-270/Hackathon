"""
Logging Utilities
Centralized logging configuration and utilities
"""
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional
import json
from datetime import datetime

try:
    from vehicle_control.config.constants import LOGGING_CONFIG
except ImportError:
    # Fallback for standalone testing
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from config.constants import LOGGING_CONFIG


class VehicleLogFilter(logging.Filter):
    """Custom filter for vehicle-specific logging"""
    
    def filter(self, record):
        # Add vehicle-specific context to log records
        if not hasattr(record, 'vehicle_id'):
            record.vehicle_id = 'VEHICLE_01'
        
        if not hasattr(record, 'system'):
            record.system = getattr(record, 'name', 'unknown').split('.')[0]
        
        return True


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add vehicle-specific fields
        if hasattr(record, 'vehicle_id'):
            log_entry['vehicle_id'] = record.vehicle_id
        if hasattr(record, 'system'):
            log_entry['system'] = record.system
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)


# Track if logging has been initialized to prevent duplicate setup
_logging_initialized = False


def setup_logging(log_level: str = "INFO", 
                 log_file: Optional[str] = None,
                 enable_console: bool = True,
                 enable_json: bool = False,
                 max_file_size_mb: int = 10,
                 backup_count: int = 5) -> logging.Logger:
    """
    Setup centralized logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        enable_console: Enable console logging
        enable_json: Use JSON formatter
        max_file_size_mb: Maximum log file size before rotation
        backup_count: Number of backup files to keep
        
    Returns:
        Configured root logger
    """
    global _logging_initialized
    
    # Skip if already initialized (prevent duplicate messages)
    if _logging_initialized:
        return logging.getLogger()
    
    # Clear any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)
    
    # Create formatters
    if enable_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt=LOGGING_CONFIG.LOG_FORMAT,
            datefmt=LOGGING_CONFIG.DATE_FORMAT
        )
    
    # Add custom filter
    vehicle_filter = VehicleLogFilter()
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(vehicle_filter)
        root_logger.addHandler(console_handler)
    
    # File handler with rotation
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_file_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(vehicle_filter)
        root_logger.addHandler(file_handler)
    
    # Mark as initialized
    _logging_initialized = True
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging initialized - Level: {log_level}, "
        f"Console: {enable_console}, File: {log_file is not None}, "
        f"JSON: {enable_json}"
    )
    
    return root_logger


def get_logger(name: str, system: Optional[str] = None) -> logging.Logger:
    """
    Get a logger with vehicle-specific context
    
    Args:
        name: Logger name
        system: System/module name for filtering
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    
    # Add system context if provided
    if system:
        def add_system_context(record):
            record.system = system
            return True
        
        filter_func = add_system_context
        logger.addFilter(filter_func)
    
    return logger


class PerformanceLogger:
    """Performance logging utility"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.timings = {}
    
    def start_timer(self, operation: str):
        """Start timing an operation"""
        import time
        self.timings[operation] = time.perf_counter()
    
    def end_timer(self, operation: str, log_level: int = logging.INFO):
        """End timing and log the duration"""
        import time
        if operation in self.timings:
            duration = time.perf_counter() - self.timings[operation]
            self.logger.log(
                log_level,
                f"Performance: {operation} took {duration*1000:.2f}ms"
            )
            del self.timings[operation]
        else:
            self.logger.warning(f"Timer '{operation}' was not started")
    
    def log_timing(self, operation: str, duration_sec: float, 
                   log_level: int = logging.INFO):
        """Log timing information directly"""
        self.logger.log(
            log_level,
            f"Performance: {operation} took {duration_sec*1000:.2f}ms"
        )


class ErrorLogger:
    """Error logging utility with context"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.error_counts = {}
    
    def log_error(self, error: Exception, context: Optional[dict] = None):
        """Log error with context information"""
        error_type = type(error).__name__
        
        # Count errors by type
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # Create error message
        message = f"Error ({self.error_counts[error_type]}): {error}"
        
        if context:
            message += f" | Context: {context}"
        
        self.logger.error(message, exc_info=True)
    
    def get_error_summary(self) -> dict:
        """Get summary of error counts"""
        return dict(self.error_counts)


# Utility functions for common logging patterns
def log_function_call(func):
    """Decorator to log function calls"""
    import functools
    import time
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
        
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            duration = time.perf_counter() - start_time
            logger.debug(f"{func.__name__} completed in {duration*1000:.2f}ms")
            return result
        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.error(
                f"{func.__name__} failed after {duration*1000:.2f}ms: {e}",
                exc_info=True
            )
            raise
    
    return wrapper


def log_motor_command(motor_id, command: str, value: float, ros_logger=None):
    """Log motor command with [TIMING] JSON format via ROS2 logger
    
    Args:
        motor_id: Motor/joint identifier (str joint name or int CAN ID)
        command: Command type (e.g., 'position', 'velocity')
        value: Command value
        ros_logger: ROS2 node logger. If None, falls back to Python logging.
    """
    import time
    event = {
        "event": "motor_command",
        "ts": datetime.now().isoformat(),
        "motor_id": motor_id,
        "command": command,
        "value": round(value, 6),
        "t": round(time.perf_counter() * 1000, 3)
    }
    if ros_logger is not None:
        ros_logger.info(f"[TIMING] {json.dumps(event)}")
    else:
        logger = logging.getLogger('vehicle.motor')
        logger.info(f"[TIMING] {json.dumps(event)}")


def log_state_transition(from_state: str, to_state: str, trigger: str,
                         time_in_previous_state_ms: float = None,
                         transition_ms: float = None,
                         error_cause=None,
                         estop_latency_ms: float = None,
                         ros_logger=None):
    """Log state transition with [TIMING] JSON format via ROS2 logger
    
    Args:
        from_state: Previous state name
        to_state: New state name
        trigger: What triggered the transition
        time_in_previous_state_ms: Time spent in previous state (ms)
        transition_ms: Time taken for the transition itself (ms)
        error_cause: Error metadata dict when transitioning to ERROR (or None)
        estop_latency_ms: E-stop detection to publish latency (ms), null for non-emergency
        ros_logger: ROS2 node logger. If None, falls back to Python logging.
    """
    event = {
        "event": "state_transition",
        "ts": datetime.now().isoformat(),
        "from_state": str(from_state),
        "to_state": str(to_state),
        "trigger": str(trigger),
        "time_in_previous_state_ms": round(time_in_previous_state_ms, 3) if time_in_previous_state_ms is not None else None,
        "transition_ms": round(transition_ms, 3) if transition_ms is not None else None,
        "error_cause": error_cause,
        "estop_latency_ms": round(estop_latency_ms, 3) if estop_latency_ms is not None else None
    }
    if ros_logger is not None:
        ros_logger.info(f"[TIMING] {json.dumps(event)}")
    else:
        logger = logging.getLogger('vehicle.state')
        logger.info(f"[TIMING] {json.dumps(event)}")


def log_safety_event(level: str, message: str, source: str):
    """Log safety event with consistent format"""
    logger = logging.getLogger('vehicle.safety')
    getattr(logger, level.lower())(f"SAFETY [{source.upper()}]: {message}")


# Note: Logging is initialized on-demand when setup_logging() is called
# Auto-initialization removed to prevent duplicate "Logging initialized" messages
