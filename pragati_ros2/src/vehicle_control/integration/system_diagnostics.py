#!/usr/bin/env python3
"""
Vehicle System Diagnostics
Comprehensive health monitoring for the entire vehicle control system
"""

import asyncio
import logging
import time
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque

try:
    from ..hardware.motor_controller import VehicleMotorController, MotorStatus
    from ..hardware.gpio_manager import GPIOManager
    from ..config.constants import GPIO_PINS, MotorIDs
except ImportError:
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from hardware.motor_controller import VehicleMotorController, MotorStatus
    from hardware.gpio_manager import GPIOManager
    from config.constants import GPIO_PINS, MotorIDs


class HealthStatus(Enum):
    """System health status levels"""

    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class DiagnosticLevel(Enum):
    """Diagnostic detail levels"""

    BASIC = "BASIC"
    DETAILED = "DETAILED"
    COMPREHENSIVE = "COMPREHENSIVE"


@dataclass
class DiagnosticResult:
    """Individual diagnostic test result"""

    test_name: str
    status: HealthStatus
    message: str
    timestamp: float
    details: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class SubsystemHealth:
    """Health information for a subsystem"""

    name: str
    status: HealthStatus
    last_updated: float
    diagnostics: List[DiagnosticResult] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class SystemHealthReport:
    """Complete system health report"""

    timestamp: float
    overall_status: HealthStatus
    system_score: float  # 0.0 to 1.0
    subsystems: Dict[str, SubsystemHealth]
    recommendations: List[str] = field(default_factory=list)
    critical_issues: List[str] = field(default_factory=list)


class PerformanceTracker:
    """Track system performance metrics over time"""

    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_samples))
        self._lock = threading.RLock()  # Use RLock to allow reentrant locking

    def record_metric(self, name: str, value: float, timestamp: Optional[float] = None):
        """Record a performance metric"""
        if timestamp is None:
            timestamp = time.time()

        with self._lock:
            self._metrics[name].append((timestamp, value))

    def get_metric_stats(
        self, name: str, time_window: Optional[float] = None
    ) -> Dict[str, float]:
        """Get statistics for a metric"""
        with self._lock:
            if name not in self._metrics:
                return {}

            data = list(self._metrics[name])

            # Filter by time window if specified
            if time_window:
                cutoff_time = time.time() - time_window
                data = [(t, v) for t, v in data if t >= cutoff_time]

            if not data:
                return {}

            values = [v for _, v in data]
            return {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "latest": values[-1] if values else 0.0,
            }

    def get_all_metrics(self) -> Dict[str, Dict[str, float]]:
        """Get statistics for all metrics"""
        with self._lock:
            # Get all metrics without calling get_metric_stats to avoid nested locking
            result = {}
            for name in self._metrics.keys():
                data = list(self._metrics[name])
                if not data:
                    result[name] = {}
                    continue

                values = [v for _, v in data]
                result[name] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values),
                    "latest": values[-1] if values else 0.0,
                }
            return result


class VehicleSystemDiagnostics:
    """
    Comprehensive vehicle system diagnostics and health monitoring
    """

    def __init__(
        self,
        motor_controller: VehicleMotorController,
        gpio_manager: Optional[GPIOManager] = None,
        diagnostic_level: DiagnosticLevel = DiagnosticLevel.DETAILED,
    ):
        """
        Initialize system diagnostics

        Args:
            motor_controller: Vehicle motor controller instance
            gpio_manager: GPIO manager instance (optional)
            diagnostic_level: Level of diagnostic detail
        """
        self.logger = logging.getLogger(__name__)

        # Component references
        self.motor_controller = motor_controller
        self.gpio_manager = gpio_manager
        self.diagnostic_level = diagnostic_level

        # Diagnostics state
        self._running = False
        self._diagnostic_thread: Optional[threading.Thread] = None
        self._diagnostic_interval = 5.0  # seconds

        # Performance tracking
        self.performance_tracker = PerformanceTracker()

        # Health history
        self._health_history: deque = deque(maxlen=100)  # Keep last 100 reports

        # Diagnostic callbacks
        self._diagnostic_callbacks: List[Callable[[SystemHealthReport], None]] = []

        # System thresholds
        self.thresholds = {
            "motor_temperature_warning": 60.0,  # °C
            "motor_temperature_critical": 75.0,  # °C
            "voltage_low_warning": 21.0,  # V
            "voltage_low_critical": 20.0,  # V
            "voltage_high_warning": 28.0,  # V
            "voltage_high_critical": 30.0,  # V
            "response_time_warning": 1.0,  # seconds
            "response_time_critical": 2.0,  # seconds
            "error_rate_warning": 0.05,  # 5% error rate
            "error_rate_critical": 0.15,  # 15% error rate
        }

        self.logger.info("Vehicle system diagnostics initialized")

    def start_continuous_diagnostics(self, interval: float = 5.0):
        """Start continuous diagnostic monitoring"""
        if self._running:
            self.logger.warning("Diagnostics already running")
            return

        self._diagnostic_interval = interval
        self._running = True

        self._diagnostic_thread = threading.Thread(
            target=self._diagnostic_loop, daemon=True, name="VehicleDiagnostics"
        )
        self._diagnostic_thread.start()

        self.logger.info(f"Started continuous diagnostics with {interval}s interval")

    def stop_continuous_diagnostics(self):
        """Stop continuous diagnostic monitoring"""
        if not self._running:
            return

        self._running = False

        if self._diagnostic_thread:
            self._diagnostic_thread.join(timeout=2.0)

        self.logger.info("Stopped continuous diagnostics")

    def _diagnostic_loop(self):
        """Main diagnostic monitoring loop"""
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            while self._running:
                try:
                    # Perform system health check using the thread's event loop
                    health_report = loop.run_until_complete(
                        self.perform_system_health_check()
                    )

                    # Store in history
                    self._health_history.append(health_report)
                    self.logger.debug(
                        f"Health report added to history, total reports: {len(self._health_history)}"
                    )

                    # Notify callbacks
                    for callback in self._diagnostic_callbacks:
                        try:
                            callback(health_report)
                        except Exception as e:
                            self.logger.error(f"Diagnostic callback failed: {e}")

                    # Log critical issues
                    if health_report.critical_issues:
                        for issue in health_report.critical_issues:
                            self.logger.critical(f"CRITICAL: {issue}")

                    # Log overall status
                    if health_report.overall_status in [
                        HealthStatus.ERROR,
                        HealthStatus.CRITICAL,
                    ]:
                        self.logger.error(
                            f"System health: {health_report.overall_status.value} (Score: {health_report.system_score:.2f})"
                        )
                    elif health_report.overall_status == HealthStatus.WARNING:
                        self.logger.warning(
                            f"System health: {health_report.overall_status.value} (Score: {health_report.system_score:.2f})"
                        )

                    # Sleep until next diagnostic cycle
                    time.sleep(self._diagnostic_interval)

                except Exception as e:
                    self.logger.error(f"Diagnostic loop error: {e}")
                    import traceback

                    self.logger.debug(traceback.format_exc())
                    time.sleep(self._diagnostic_interval)
        finally:
            loop.close()

    async def perform_system_health_check(self) -> SystemHealthReport:
        """Perform comprehensive system health assessment"""
        start_time = time.time()

        try:
            self.logger.debug("Starting system health check...")

            # Initialize report
            report = SystemHealthReport(
                timestamp=start_time,
                overall_status=HealthStatus.UNKNOWN,
                system_score=0.0,
                subsystems={},
            )

            # Check all subsystems concurrently
            subsystem_tasks = [
                self._check_motor_subsystem(),
                self._check_gpio_subsystem(),
                self._check_communication_subsystem(),
                self._check_performance_subsystem(),
            ]

            if self.diagnostic_level == DiagnosticLevel.COMPREHENSIVE:
                subsystem_tasks.extend(
                    [self._check_safety_subsystem(), self._check_system_resources()]
                )

            # Execute all diagnostic tasks
            subsystem_results = await asyncio.gather(
                *subsystem_tasks, return_exceptions=True
            )

            # Process results
            for result in subsystem_results:
                if isinstance(result, Exception):
                    self.logger.error(f"Subsystem diagnostic failed: {result}")
                    continue

                if isinstance(result, SubsystemHealth):
                    report.subsystems[result.name] = result

            # Calculate overall system health
            report.overall_status, report.system_score = self._calculate_overall_health(
                report.subsystems
            )

            # Generate recommendations
            report.recommendations = self._generate_recommendations(report)

            # Identify critical issues
            report.critical_issues = self._identify_critical_issues(report)

            # Record performance metrics
            diagnostic_time = time.time() - start_time
            self.performance_tracker.record_metric("diagnostic_time", diagnostic_time)

            self.logger.debug(
                f"System health check completed in {diagnostic_time:.3f}s"
            )
            return report

        except Exception as e:
            self.logger.error(f"System health check failed: {e}")
            return SystemHealthReport(
                timestamp=start_time,
                overall_status=HealthStatus.ERROR,
                system_score=0.0,
                subsystems={},
                critical_issues=[f"Health check failed: {e}"],
            )

    async def _check_motor_subsystem(self) -> SubsystemHealth:
        """Check motor subsystem health"""
        subsystem = SubsystemHealth(
            name="motors", status=HealthStatus.UNKNOWN, last_updated=time.time()
        )

        try:
            # Get motor IDs from motor controller or use default
            if hasattr(self.motor_controller, "_motor_ids"):
                motor_ids = self.motor_controller._motor_ids.all_motors
            elif hasattr(self.motor_controller, "get_motor_ids"):
                motor_ids = self.motor_controller.get_motor_ids()
            else:
                # Fallback to default motor IDs
                try:
                    from config.constants import MotorIDs

                    motor_ids_obj = MotorIDs()
                    motor_ids = motor_ids_obj.all_motors
                except ImportError:
                    motor_ids = [0, 1, 2, 3, 4, 5]  # Default fallback

            healthy_motors = 0
            total_motors = len(motor_ids)

            for motor_id in motor_ids:
                try:
                    # Get motor status with timeout (compatible with older Python versions)
                    try:
                        status = await asyncio.wait_for(
                            asyncio.create_task(
                                asyncio.to_thread(
                                    self.motor_controller._motor_interface.get_status,
                                    motor_id,
                                )
                            ),
                            timeout=1.0,
                        )
                    except AttributeError:
                        # Fallback for sync interfaces
                        status = self.motor_controller._motor_interface.get_status(
                            motor_id
                        )

                    # Create diagnostic for this motor
                    motor_diagnostic = self._diagnose_motor(motor_id, status)
                    subsystem.diagnostics.append(motor_diagnostic)

                    # Track motor metrics
                    if status.temperature:
                        self.performance_tracker.record_metric(
                            f"motor_{motor_id}_temperature", status.temperature
                        )
                    if status.voltage:
                        self.performance_tracker.record_metric(
                            f"motor_{motor_id}_voltage", status.voltage
                        )

                    # Count healthy motors
                    if motor_diagnostic.status in [
                        HealthStatus.HEALTHY,
                        HealthStatus.WARNING,
                    ]:
                        healthy_motors += 1

                    # Store motor metrics
                    subsystem.metrics[f"motor_{motor_id}"] = {
                        "temperature": status.temperature,
                        "voltage": status.voltage,
                        "position": status.position,
                        "velocity": status.velocity,
                        "enabled": status.is_enabled,
                        "error_code": status.error_code,
                    }

                except asyncio.TimeoutError:
                    error_msg = f"Motor {motor_id} communication timeout"
                    subsystem.errors.append(error_msg)
                    subsystem.diagnostics.append(
                        DiagnosticResult(
                            test_name=f"motor_{motor_id}_communication",
                            status=HealthStatus.ERROR,
                            message=error_msg,
                            timestamp=time.time(),
                        )
                    )

                except Exception as e:
                    error_msg = f"Motor {motor_id} diagnostic failed: {e}"
                    subsystem.errors.append(error_msg)
                    subsystem.diagnostics.append(
                        DiagnosticResult(
                            test_name=f"motor_{motor_id}_diagnostic",
                            status=HealthStatus.ERROR,
                            message=error_msg,
                            timestamp=time.time(),
                        )
                    )

            # Determine overall motor subsystem health
            health_ratio = healthy_motors / total_motors if total_motors > 0 else 0.0

            if health_ratio >= 0.9:
                subsystem.status = HealthStatus.HEALTHY
            elif health_ratio >= 0.7:
                subsystem.status = HealthStatus.WARNING
                subsystem.warnings.append(
                    f"Only {healthy_motors}/{total_motors} motors healthy"
                )
            elif health_ratio >= 0.5:
                subsystem.status = HealthStatus.ERROR
                subsystem.errors.append(
                    f"Only {healthy_motors}/{total_motors} motors operational"
                )
            else:
                subsystem.status = HealthStatus.CRITICAL
                subsystem.errors.append(
                    f"Critical motor failure: {healthy_motors}/{total_motors} operational"
                )

            subsystem.metrics["health_ratio"] = health_ratio
            subsystem.metrics["healthy_count"] = healthy_motors
            subsystem.metrics["total_count"] = total_motors

        except Exception as e:
            subsystem.status = HealthStatus.ERROR
            subsystem.errors.append(f"Motor subsystem diagnostic failed: {e}")

        return subsystem

    def _diagnose_motor(self, motor_id: int, status: MotorStatus) -> DiagnosticResult:
        """Diagnose individual motor health"""
        issues = []
        overall_status = HealthStatus.HEALTHY

        # Check temperature
        if status.temperature:
            if status.temperature > self.thresholds["motor_temperature_critical"]:
                issues.append(f"Critical temperature: {status.temperature:.1f}°C")
                overall_status = HealthStatus.CRITICAL
            elif status.temperature > self.thresholds["motor_temperature_warning"]:
                issues.append(f"High temperature: {status.temperature:.1f}°C")
                overall_status = max(
                    overall_status, HealthStatus.WARNING, key=lambda x: x.value
                )

        # Check voltage
        if status.voltage:
            if (
                status.voltage < self.thresholds["voltage_low_critical"]
                or status.voltage > self.thresholds["voltage_high_critical"]
            ):
                issues.append(f"Critical voltage: {status.voltage:.1f}V")
                overall_status = HealthStatus.CRITICAL
            elif (
                status.voltage < self.thresholds["voltage_low_warning"]
                or status.voltage > self.thresholds["voltage_high_warning"]
            ):
                issues.append(f"Voltage warning: {status.voltage:.1f}V")
                overall_status = max(
                    overall_status, HealthStatus.WARNING, key=lambda x: x.value
                )

        # Check error codes
        if status.error_code != 0:
            issues.append(f"Error code: {status.error_code}")
            overall_status = HealthStatus.ERROR

        # Check if motor is enabled when expected
        if hasattr(self.motor_controller, "_motor_enabled"):
            expected_enabled = self.motor_controller._motor_enabled.get(motor_id, False)
            if expected_enabled and not status.is_enabled:
                issues.append("Motor disabled unexpectedly")
                overall_status = HealthStatus.ERROR

        message = f"Motor {motor_id}: " + (
            "; ".join(issues) if issues else "Operating normally"
        )

        return DiagnosticResult(
            test_name=f"motor_{motor_id}_health",
            status=overall_status,
            message=message,
            timestamp=time.time(),
            details={
                "temperature": status.temperature,
                "voltage": status.voltage,
                "position": status.position,
                "velocity": status.velocity,
                "error_code": status.error_code,
                "enabled": status.is_enabled,
            },
        )

    async def _check_gpio_subsystem(self) -> SubsystemHealth:
        """Check GPIO subsystem health"""
        subsystem = SubsystemHealth(
            name="gpio", status=HealthStatus.UNKNOWN, last_updated=time.time()
        )

        try:
            if not self.gpio_manager:
                subsystem.status = HealthStatus.WARNING
                subsystem.warnings.append("GPIO manager not available")
                return subsystem

            # Test GPIO functionality
            try:
                # Test input reading
                inputs = self.gpio_manager.read_all_inputs()
                subsystem.metrics["input_count"] = len(inputs)

                # Test emergency stop reading
                emergency_stop = self.gpio_manager.is_emergency_stop_active()
                subsystem.metrics["emergency_stop"] = emergency_stop

                if emergency_stop:
                    subsystem.status = HealthStatus.CRITICAL
                    subsystem.errors.append("Emergency stop is active")
                else:
                    subsystem.status = HealthStatus.HEALTHY

                subsystem.diagnostics.append(
                    DiagnosticResult(
                        test_name="gpio_functionality",
                        status=subsystem.status,
                        message=f"GPIO operational, emergency stop: {emergency_stop}",
                        timestamp=time.time(),
                        details={"inputs": inputs, "emergency_stop": emergency_stop},
                    )
                )

            except Exception as e:
                subsystem.status = HealthStatus.ERROR
                subsystem.errors.append(f"GPIO test failed: {e}")

        except Exception as e:
            subsystem.status = HealthStatus.ERROR
            subsystem.errors.append(f"GPIO subsystem diagnostic failed: {e}")

        return subsystem

    async def _check_communication_subsystem(self) -> SubsystemHealth:
        """Check communication subsystem health"""
        subsystem = SubsystemHealth(
            name="communication", status=HealthStatus.UNKNOWN, last_updated=time.time()
        )

        try:
            # Test motor communication response times
            response_times = []
            failed_communications = 0

            # Get motor IDs for testing
            if hasattr(self.motor_controller, "_motor_ids"):
                test_motor_ids = self.motor_controller._motor_ids.all_motors[:3]
            else:
                try:
                    from config.constants import MotorIDs

                    motor_ids_obj = MotorIDs()
                    test_motor_ids = motor_ids_obj.all_motors[:3]
                except ImportError:
                    test_motor_ids = [0, 1, 2]  # Default test motors

            for motor_id in test_motor_ids:  # Test first 3 motors
                start_time = time.time()
                try:
                    # Use asyncio.wait_for instead of asyncio.timeout for compatibility
                    try:
                        await asyncio.wait_for(
                            asyncio.create_task(
                                asyncio.to_thread(
                                    self.motor_controller._motor_interface.get_status,
                                    motor_id,
                                )
                            ),
                            timeout=2.0,
                        )
                    except AttributeError:
                        # Fallback for sync interfaces
                        self.motor_controller._motor_interface.get_status(motor_id)

                    response_time = time.time() - start_time
                    response_times.append(response_time)

                    self.performance_tracker.record_metric(
                        "communication_response_time", response_time
                    )

                except Exception:
                    failed_communications += 1

            # Analyze communication health
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                max_response_time = max(response_times)

                subsystem.metrics["avg_response_time"] = avg_response_time
                subsystem.metrics["max_response_time"] = max_response_time
                subsystem.metrics["failed_communications"] = failed_communications

                if max_response_time > self.thresholds["response_time_critical"]:
                    subsystem.status = HealthStatus.CRITICAL
                    subsystem.errors.append(
                        f"Critical communication delay: {max_response_time:.3f}s"
                    )
                elif max_response_time > self.thresholds["response_time_warning"]:
                    subsystem.status = HealthStatus.WARNING
                    subsystem.warnings.append(
                        f"Slow communication: {max_response_time:.3f}s"
                    )
                else:
                    subsystem.status = HealthStatus.HEALTHY

                if failed_communications > 0:
                    failure_rate = failed_communications / (
                        len(response_times) + failed_communications
                    )
                    if failure_rate > self.thresholds["error_rate_critical"]:
                        subsystem.status = HealthStatus.CRITICAL
                        subsystem.errors.append(
                            f"High communication failure rate: {failure_rate:.1%}"
                        )
                    elif failure_rate > self.thresholds["error_rate_warning"]:
                        subsystem.status = max(
                            subsystem.status,
                            HealthStatus.WARNING,
                            key=lambda x: x.value,
                        )
                        subsystem.warnings.append(
                            f"Communication failures detected: {failure_rate:.1%}"
                        )

            else:
                subsystem.status = HealthStatus.CRITICAL
                subsystem.errors.append("No successful communications")

            subsystem.diagnostics.append(
                DiagnosticResult(
                    test_name="communication_performance",
                    status=subsystem.status,
                    message=f"Communication test completed: {len(response_times)} success, {failed_communications} failed",
                    timestamp=time.time(),
                    details=subsystem.metrics.copy(),
                )
            )

        except Exception as e:
            subsystem.status = HealthStatus.ERROR
            subsystem.errors.append(f"Communication diagnostic failed: {e}")

        return subsystem

    async def _check_performance_subsystem(self) -> SubsystemHealth:
        """Check system performance metrics"""
        subsystem = SubsystemHealth(
            name="performance", status=HealthStatus.HEALTHY, last_updated=time.time()
        )

        try:
            # Get performance metrics with timeout protection
            try:
                all_metrics = await asyncio.wait_for(
                    asyncio.create_task(
                        asyncio.to_thread(self.performance_tracker.get_all_metrics)
                    ),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                self.logger.warning("Performance metrics collection timed out")
                all_metrics = {}
            except Exception as e:
                self.logger.error(f"Error getting performance metrics: {e}")
                all_metrics = {}

            # Analyze diagnostic performance
            if "diagnostic_time" in all_metrics:
                diag_stats = all_metrics["diagnostic_time"]
                if diag_stats.get("avg", 0) > 5.0:  # Diagnostics taking too long
                    subsystem.status = HealthStatus.WARNING
                    subsystem.warnings.append(
                        f"Slow diagnostics: {diag_stats['avg']:.2f}s average"
                    )

            # Analyze communication performance
            if "communication_response_time" in all_metrics:
                comm_stats = all_metrics["communication_response_time"]
                if comm_stats.get("avg", 0) > self.thresholds["response_time_warning"]:
                    subsystem.status = max(
                        subsystem.status, HealthStatus.WARNING, key=lambda x: x.value
                    )
                    subsystem.warnings.append(
                        f"Slow communication: {comm_stats['avg']:.3f}s average"
                    )

            subsystem.metrics = all_metrics

            subsystem.diagnostics.append(
                DiagnosticResult(
                    test_name="performance_analysis",
                    status=subsystem.status,
                    message=f"Performance metrics analyzed: {len(all_metrics)} metrics tracked",
                    timestamp=time.time(),
                    details=all_metrics,
                )
            )

        except Exception as e:
            subsystem.status = HealthStatus.ERROR
            subsystem.errors.append(f"Performance diagnostic failed: {e}")

        return subsystem

    async def _check_safety_subsystem(self) -> SubsystemHealth:
        """Check safety system status"""
        subsystem = SubsystemHealth(
            name="safety", status=HealthStatus.HEALTHY, last_updated=time.time()
        )

        try:
            safety_issues = []

            # Check emergency stop status
            if hasattr(self.motor_controller, "_emergency_stop"):
                if self.motor_controller._emergency_stop.is_set():
                    safety_issues.append("Emergency stop active")
                    subsystem.status = HealthStatus.CRITICAL

            # Generate diagnostic result
            if safety_issues:
                subsystem.errors.extend(safety_issues)
                message = f"Safety issues detected: {'; '.join(safety_issues)}"
            else:
                message = "Safety systems operational"

            subsystem.diagnostics.append(
                DiagnosticResult(
                    test_name="safety_systems",
                    status=subsystem.status,
                    message=message,
                    timestamp=time.time(),
                    details=subsystem.metrics.copy(),
                )
            )

        except Exception as e:
            subsystem.status = HealthStatus.ERROR
            subsystem.errors.append(f"Safety diagnostic failed: {e}")

        return subsystem

    async def _check_system_resources(self) -> SubsystemHealth:
        """Check system resource usage"""
        subsystem = SubsystemHealth(
            name="resources", status=HealthStatus.HEALTHY, last_updated=time.time()
        )

        try:
            import psutil
            import os

            # Get process info
            process = psutil.Process(os.getpid())

            # Memory usage
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            # CPU usage
            cpu_percent = process.cpu_percent(interval=0.1)

            # Thread count
            thread_count = process.num_threads()

            subsystem.metrics.update(
                {
                    "memory_mb": memory_mb,
                    "cpu_percent": cpu_percent,
                    "thread_count": thread_count,
                }
            )

            # Check thresholds
            if memory_mb > 500:  # 500MB threshold
                subsystem.status = HealthStatus.WARNING
                subsystem.warnings.append(f"High memory usage: {memory_mb:.1f} MB")

            if cpu_percent > 80:  # 80% CPU threshold
                subsystem.status = max(
                    subsystem.status, HealthStatus.WARNING, key=lambda x: x.value
                )
                subsystem.warnings.append(f"High CPU usage: {cpu_percent:.1f}%")

            subsystem.diagnostics.append(
                DiagnosticResult(
                    test_name="resource_usage",
                    status=subsystem.status,
                    message=f"Resources: {memory_mb:.1f}MB, {cpu_percent:.1f}% CPU, {thread_count} threads",
                    timestamp=time.time(),
                    details=subsystem.metrics.copy(),
                )
            )

        except ImportError:
            subsystem.status = HealthStatus.WARNING
            subsystem.warnings.append("psutil not available for resource monitoring")
        except Exception as e:
            subsystem.status = HealthStatus.ERROR
            subsystem.errors.append(f"Resource diagnostic failed: {e}")

        return subsystem

    def _calculate_overall_health(
        self, subsystems: Dict[str, SubsystemHealth]
    ) -> tuple[HealthStatus, float]:
        """Calculate overall system health from subsystem health"""
        if not subsystems:
            return HealthStatus.UNKNOWN, 0.0

        # Weight different subsystems
        weights = {
            "motors": 0.4,
            "communication": 0.2,
            "safety": 0.2,
            "gpio": 0.1,
            "performance": 0.05,
            "resources": 0.05,
        }

        # Calculate weighted score
        total_score = 0.0
        total_weight = 0.0
        critical_count = 0
        error_count = 0
        warning_count = 0

        for name, subsystem in subsystems.items():
            weight = weights.get(name, 0.1)  # Default weight for unknown subsystems
            total_weight += weight

            # Convert status to score
            if subsystem.status == HealthStatus.HEALTHY:
                score = 1.0
            elif subsystem.status == HealthStatus.WARNING:
                score = 0.7
                warning_count += 1
            elif subsystem.status == HealthStatus.ERROR:
                score = 0.3
                error_count += 1
            elif subsystem.status == HealthStatus.CRITICAL:
                score = 0.0
                critical_count += 1
            else:  # UNKNOWN
                score = 0.5

            total_score += score * weight

        # Calculate final score
        system_score = total_score / total_weight if total_weight > 0 else 0.0

        # Determine overall status
        if critical_count > 0:
            overall_status = HealthStatus.CRITICAL
        elif error_count > 0:
            overall_status = HealthStatus.ERROR
        elif warning_count > 0:
            overall_status = HealthStatus.WARNING
        elif system_score > 0.8:
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.WARNING

        return overall_status, system_score

    def _generate_recommendations(self, report: SystemHealthReport) -> List[str]:
        """Generate actionable recommendations based on health report"""
        recommendations = []

        for name, subsystem in report.subsystems.items():
            if subsystem.status in [HealthStatus.ERROR, HealthStatus.CRITICAL]:
                if name == "motors":
                    recommendations.append(
                        "Check motor connections and clear any error codes"
                    )
                    if subsystem.metrics.get("health_ratio", 1.0) < 0.7:
                        recommendations.append(
                            "Multiple motor failures detected - inspect hardware"
                        )

                elif name == "communication":
                    recommendations.append("Check CAN bus connections and cables")
                    if "avg_response_time" in subsystem.metrics:
                        recommendations.append(
                            "Consider reducing communication load or checking network performance"
                        )

                elif name == "gpio":
                    if subsystem.metrics.get("emergency_stop", False):
                        recommendations.append(
                            "Release emergency stop to resume operations"
                        )
                    else:
                        recommendations.append("Check GPIO hardware connections")

                elif name == "safety":
                    recommendations.append(
                        "Address safety system issues before continuing operations"
                    )

        # Add general recommendations based on overall health
        if report.system_score < 0.5:
            recommendations.append(
                "System health is critical - consider immediate maintenance"
            )
        elif report.system_score < 0.7:
            recommendations.append("Schedule preventive maintenance to address issues")

        return recommendations

    def _identify_critical_issues(self, report: SystemHealthReport) -> List[str]:
        """Identify critical issues that require immediate attention"""
        critical_issues = []

        for name, subsystem in report.subsystems.items():
            if subsystem.status == HealthStatus.CRITICAL:
                for error in subsystem.errors:
                    critical_issues.append(f"{name.upper()}: {error}")

        return critical_issues

    def add_diagnostic_callback(self, callback: Callable[[SystemHealthReport], None]):
        """Add a callback to be notified of diagnostic results"""
        self._diagnostic_callbacks.append(callback)

    def remove_diagnostic_callback(
        self, callback: Callable[[SystemHealthReport], None]
    ):
        """Remove a diagnostic callback"""
        if callback in self._diagnostic_callbacks:
            self._diagnostic_callbacks.remove(callback)

    def get_health_history(self, count: int = 10) -> List[SystemHealthReport]:
        """Get recent health reports"""
        return list(self._health_history)[-count:]

    def export_health_report(self, filepath: str, format: str = "json"):
        """Export latest health report to file"""
        if not self._health_history:
            self.logger.warning("No health reports available to export")
            return

        latest_report = self._health_history[-1]

        try:
            if format.lower() == "json":
                import json

                # Convert to serializable format
                report_dict = {
                    "timestamp": latest_report.timestamp,
                    "overall_status": latest_report.overall_status.value,
                    "system_score": latest_report.system_score,
                    "recommendations": latest_report.recommendations,
                    "critical_issues": latest_report.critical_issues,
                    "subsystems": {},
                }

                for name, subsystem in latest_report.subsystems.items():
                    report_dict["subsystems"][name] = {
                        "status": subsystem.status.value,
                        "last_updated": subsystem.last_updated,
                        "warnings": subsystem.warnings,
                        "errors": subsystem.errors,
                        "metrics": subsystem.metrics,
                        "diagnostics": [
                            {
                                "test_name": diag.test_name,
                                "status": diag.status.value,
                                "message": diag.message,
                                "timestamp": diag.timestamp,
                                "details": diag.details,
                            }
                            for diag in subsystem.diagnostics
                        ],
                    }

                with open(filepath, "w") as f:
                    json.dump(report_dict, f, indent=2)

                self.logger.info(f"Health report exported to {filepath}")

            else:
                self.logger.error(f"Unsupported export format: {format}")

        except Exception as e:
            self.logger.error(f"Failed to export health report: {e}")
