#!/usr/bin/env python3
"""
Health Monitoring Service
=========================

Monitors system health for:
- Motor controllers (temperature, current, errors, position)
- CAN bus (message counts, errors, timeouts)
- Safety monitor (violations, e-stop, limits)
- Cotton detection (rate, latency, camera health)

Optimized for RPi with efficient aggregation.

NOTE (Phase 3, Task 3.4 — entity scoping): This service monitors the
LOCAL entity's health only. It subscribes to ROS2 topics on the local
machine and aggregates metrics for the dashboard running on this host.
Remote entity health data is obtained via the entity_proxy routes, which
proxy to each RPi's lightweight agent (port 8091). Do not treat data
from this service as fleet-wide health state.
"""

import time
import threading
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

try:
    import rclpy
    from rclpy.node import Node

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    Node = object

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels"""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MotorHealth:
    """Motor health status"""

    motor_id: int
    name: str
    temperature: float = 0.0
    current_ma: float = 0.0
    voltage: float = 0.0
    position: float = 0.0
    velocity: float = 0.0
    error_code: int = 0
    last_update: float = 0.0
    status: HealthStatus = HealthStatus.UNKNOWN

    def update_status(self):
        """Determine health status from metrics.

        NOTE: These thresholds (temp >70 = CRITICAL, >60 = WARNING, etc.)
        are for LOCAL RPi alerting only. The dashboard frontend applies its
        own thresholds in deriveSubsystemHealth() (StatusHealthTab.mjs) for
        presentation purposes. The two sets are intentionally different —
        do NOT synchronise them. Frontend thresholds are the single source
        of truth for dashboard health display.
        """
        if self.error_code != 0:
            self.status = HealthStatus.ERROR
        elif self.temperature > 70:
            self.status = HealthStatus.CRITICAL
        elif self.temperature > 60:
            self.status = HealthStatus.WARNING
        elif self.current_ma > 15000:
            self.status = HealthStatus.WARNING
        else:
            self.status = HealthStatus.HEALTHY

    def to_dict(self) -> Dict:
        return {
            "motor_id": self.motor_id,
            "name": self.name,
            "temperature": self.temperature,
            "current_ma": self.current_ma,
            "voltage": self.voltage,
            "position": self.position,
            "velocity": self.velocity,
            "error_code": self.error_code,
            "status": self.status.value,
            "last_update": self.last_update,
            "stale": (time.time() - self.last_update) > 2.0,
        }


@dataclass
class CANBusHealth:
    """CAN bus health metrics"""

    bus_id: str = "can0"
    message_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    bus_load_percent: float = 0.0
    last_message_time: float = 0.0
    status: HealthStatus = HealthStatus.UNKNOWN

    # Recent history
    error_history: deque = field(default_factory=lambda: deque(maxlen=100))

    def record_error(self, error_type: str):
        """Record CAN error"""
        self.error_count += 1
        self.error_history.append({"timestamp": time.time(), "type": error_type})
        self.update_status()

    def update_status(self):
        """Determine health status"""
        age = time.time() - self.last_message_time

        if age > 5.0:
            self.status = HealthStatus.CRITICAL
        elif self.error_count > 10:
            self.status = HealthStatus.ERROR
        elif self.bus_load_percent > 90:
            self.status = HealthStatus.WARNING
        elif age > 1.0:
            self.status = HealthStatus.WARNING
        else:
            self.status = HealthStatus.HEALTHY

    def to_dict(self) -> Dict:
        return {
            "bus_id": self.bus_id,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "timeout_count": self.timeout_count,
            "bus_load_percent": self.bus_load_percent,
            "status": self.status.value,
            "last_message_time": self.last_message_time,
            "age_sec": time.time() - self.last_message_time,
            "recent_errors": list(self.error_history)[-10:],
        }


@dataclass
class SafetyHealth:
    """Safety system health"""

    state: str = "unknown"
    e_stop_active: bool = False
    violations: List[Dict] = field(default_factory=list)
    last_violation_time: float = 0.0
    watchdog_ok: bool = True
    last_update: float = 0.0
    status: HealthStatus = HealthStatus.UNKNOWN

    def record_violation(self, violation_type: str, details: str):
        """Record safety violation"""
        self.violations.append(
            {"timestamp": time.time(), "type": violation_type, "details": details}
        )
        # Keep only last 100 violations
        if len(self.violations) > 100:
            self.violations = self.violations[-100:]
        self.last_violation_time = time.time()
        self.update_status()

    def update_status(self):
        """Determine safety health status"""
        if self.e_stop_active:
            self.status = HealthStatus.CRITICAL
        elif self.violations and (time.time() - self.last_violation_time) < 10:
            self.status = HealthStatus.ERROR
        elif not self.watchdog_ok:
            self.status = HealthStatus.WARNING
        elif (time.time() - self.last_update) > 2.0:
            self.status = HealthStatus.WARNING
        else:
            self.status = HealthStatus.HEALTHY

    def to_dict(self) -> Dict:
        return {
            "state": self.state,
            "e_stop_active": self.e_stop_active,
            "violation_count": len(self.violations),
            "recent_violations": self.violations[-5:],
            "watchdog_ok": self.watchdog_ok,
            "status": self.status.value,
            "last_update": self.last_update,
        }


@dataclass
class DetectionHealth:
    """Cotton detection pipeline health"""

    detection_rate_hz: float = 0.0
    processing_latency_ms: float = 0.0
    camera_connected: bool = False
    camera_fps: float = 0.0
    model_loaded: bool = False
    detections_total: int = 0
    last_detection_time: float = 0.0
    last_update: float = 0.0
    status: HealthStatus = HealthStatus.UNKNOWN

    def update_status(self):
        """Determine detection health status"""
        age = time.time() - self.last_update

        if not self.camera_connected:
            self.status = HealthStatus.CRITICAL
        elif not self.model_loaded:
            self.status = HealthStatus.ERROR
        elif self.detection_rate_hz < 1.0:
            self.status = HealthStatus.WARNING
        elif self.processing_latency_ms > 200:
            self.status = HealthStatus.WARNING
        elif age > 2.0:
            self.status = HealthStatus.WARNING
        else:
            self.status = HealthStatus.HEALTHY

    def to_dict(self) -> Dict:
        return {
            "detection_rate_hz": self.detection_rate_hz,
            "processing_latency_ms": self.processing_latency_ms,
            "camera_connected": self.camera_connected,
            "camera_fps": self.camera_fps,
            "model_loaded": self.model_loaded,
            "detections_total": self.detections_total,
            "status": self.status.value,
            "last_update": self.last_update,
            "age_sec": time.time() - self.last_update,
        }


class HealthMonitoringService:
    """
    System health monitoring service

    Aggregates health data from all subsystems:
    - Motor controllers
    - CAN bus
    - Safety monitor
    - Cotton detection
    """

    def __init__(self, node: Optional[Node] = None):
        self.node = node
        self.lock = threading.RLock()

        # Health tracking
        self.motors: Dict[int, MotorHealth] = {}
        self.can_bus = CANBusHealth()
        self.safety = SafetyHealth()
        self.detection = DetectionHealth()

        # Subscriptions (created lazily when node is available)
        self.subscriptions = []

        logger.info("Health Monitoring Service initialized")

    def set_node(self, node: Node):
        """Set ROS2 node and create subscriptions"""
        self.node = node
        self._create_subscriptions()

    def _create_subscriptions(self):
        """Create ROS2 subscriptions for health monitoring"""
        if not self.node or not ROS2_AVAILABLE:
            return

        # These would be real subscriptions in production
        # For now, we'll provide methods to update health manually
        logger.info("Health monitoring subscriptions ready")

    # ========== Motor Health ==========

    def update_motor_health(self, motor_id: int, **kwargs):
        """Update motor health data"""
        with self.lock:
            if motor_id not in self.motors:
                self.motors[motor_id] = MotorHealth(
                    motor_id=motor_id, name=kwargs.get("name", f"Motor {motor_id}")
                )

            motor = self.motors[motor_id]
            for key, value in kwargs.items():
                if hasattr(motor, key):
                    setattr(motor, key, value)

            motor.last_update = time.time()
            motor.update_status()

    def get_motor_health(self, motor_id: Optional[int] = None) -> Dict:
        """Get motor health data"""
        with self.lock:
            if motor_id is not None:
                if motor_id not in self.motors:
                    return {"error": f"Motor {motor_id} not found"}
                return self.motors[motor_id].to_dict()
            else:
                return {
                    "motors": [m.to_dict() for m in self.motors.values()],
                    "count": len(self.motors),
                    "healthy": sum(
                        1
                        for m in self.motors.values()
                        if m.status == HealthStatus.HEALTHY
                    ),
                    "warnings": sum(
                        1
                        for m in self.motors.values()
                        if m.status == HealthStatus.WARNING
                    ),
                    "errors": sum(
                        1
                        for m in self.motors.values()
                        if m.status in [HealthStatus.ERROR, HealthStatus.CRITICAL]
                    ),
                }

    # ========== CAN Bus Health ==========

    def update_can_health(self, **kwargs):
        """Update CAN bus health"""
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self.can_bus, key):
                    setattr(self.can_bus, key, value)

            if "message_count" in kwargs:
                self.can_bus.last_message_time = time.time()

            self.can_bus.update_status()

    def record_can_error(self, error_type: str):
        """Record CAN bus error"""
        with self.lock:
            self.can_bus.record_error(error_type)

    def get_can_health(self) -> Dict:
        """Get CAN bus health"""
        with self.lock:
            return self.can_bus.to_dict()

    # ========== Safety Health ==========

    def update_safety_health(self, **kwargs):
        """Update safety system health"""
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self.safety, key):
                    setattr(self.safety, key, value)

            self.safety.last_update = time.time()
            self.safety.update_status()

    def record_safety_violation(self, violation_type: str, details: str = ""):
        """Record safety violation"""
        with self.lock:
            self.safety.record_violation(violation_type, details)

    def get_safety_health(self) -> Dict:
        """Get safety system health"""
        with self.lock:
            return self.safety.to_dict()

    # ========== Detection Health ==========

    def update_detection_health(self, **kwargs):
        """Update cotton detection health"""
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self.detection, key):
                    setattr(self.detection, key, value)

            self.detection.last_update = time.time()
            self.detection.update_status()

    def get_detection_health(self) -> Dict:
        """Get cotton detection health"""
        with self.lock:
            return self.detection.to_dict()

    # ========== Overall Health ==========

    def get_system_health(self) -> Dict:
        """Get overall system health summary"""
        with self.lock:
            motor_health = self.get_motor_health()
            can_health = self.get_can_health()
            safety_health = self.get_safety_health()
            detection_health = self.get_detection_health()

            # Check if ROS2 is available
            try:
                from backend.ros2_monitor import ROS2_AVAILABLE

                ros2_up = ROS2_AVAILABLE
            except ImportError:
                ros2_up = False

            # Add top-level 'status' to motors subsystem
            if not ros2_up or not self.motors:
                motor_status = "unavailable"
            elif any(
                m.status in [HealthStatus.ERROR, HealthStatus.CRITICAL]
                for m in self.motors.values()
            ):
                motor_status = "error"
            elif any(m.status == HealthStatus.WARNING for m in self.motors.values()):
                motor_status = "degraded"
            elif all(m.status == HealthStatus.HEALTHY for m in self.motors.values()):
                motor_status = "healthy"
            else:
                motor_status = "unavailable"
            motor_health["status"] = motor_status

            # Ensure can_bus, safety, detection have top-level 'status'
            # (their to_dict() already includes 'status' from .status.value,
            #  but override to "unavailable" when ROS2 is down)
            if not ros2_up:
                can_health["status"] = "unavailable"
                safety_health["status"] = "unavailable"
                detection_health["status"] = "unavailable"

            # Determine overall status (worst of all subsystems)
            statuses = [
                self.can_bus.status,
                self.safety.status,
                self.detection.status,
            ] + [m.status for m in self.motors.values()]

            if not ros2_up:
                overall_status = HealthStatus.UNKNOWN
            elif HealthStatus.CRITICAL in statuses:
                overall_status = HealthStatus.CRITICAL
            elif HealthStatus.ERROR in statuses:
                overall_status = HealthStatus.ERROR
            elif HealthStatus.WARNING in statuses:
                overall_status = HealthStatus.WARNING
            elif HealthStatus.HEALTHY in statuses:
                overall_status = HealthStatus.HEALTHY
            else:
                overall_status = HealthStatus.UNKNOWN

            return {
                "timestamp": time.time(),
                "overall_status": overall_status.value,
                "motors": motor_health,
                "can_bus": can_health,
                "safety": safety_health,
                "detection": detection_health,
                "summary": {
                    "critical_issues": sum(
                        1 for s in statuses if s == HealthStatus.CRITICAL
                    ),
                    "errors": sum(1 for s in statuses if s == HealthStatus.ERROR),
                    "warnings": sum(1 for s in statuses if s == HealthStatus.WARNING),
                    "healthy": sum(1 for s in statuses if s == HealthStatus.HEALTHY),
                },
            }


# Singleton instance
_health_monitor: Optional[HealthMonitoringService] = None


def get_health_monitor(node: Optional[Node] = None) -> HealthMonitoringService:
    """Get or create health monitor singleton"""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitoringService(node)
    elif node and not _health_monitor.node:
        _health_monitor.set_node(node)
    return _health_monitor


def initialize_health_monitoring(node: Optional[Node] = None):
    """Initialize health monitoring service"""
    return get_health_monitor(node)
