"""
Service Registry — Service initialization, router registration, and dependency wiring.

Extracted from dashboard_server.py as part of the backend restructure.
All try/except ImportError blocks for optional routers live here.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import psutil
from fastapi import FastAPI
import yaml

from .health import init_health_registry, register_module_failed, register_module_ok

logger = logging.getLogger(__name__)


def _resolve_mqtt_broker_host(dashboard_yaml_path: Path, entities_yaml_path: Path) -> str:
    """Resolve MQTT broker host from explicit config or approved vehicle slot."""
    dashboard_cfg: dict = {}
    if dashboard_yaml_path.exists():
        dashboard_cfg = yaml.safe_load(dashboard_yaml_path.read_text()) or {}

    mqtt_cfg = dashboard_cfg.get("mqtt", {}) or {}
    broker_host = str(mqtt_cfg.get("broker_host", "") or "").strip()
    if broker_host:
        return broker_host

    if not entities_yaml_path.exists():
        return ""

    entities_cfg = yaml.safe_load(entities_yaml_path.read_text()) or {}
    for entry in entities_cfg.get("entities", []) or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("entity_type") != "vehicle":
            continue
        if entry.get("slot") != "vehicle":
            continue
        if entry.get("membership_state") != "approved":
            continue
        return str(entry.get("ip", "") or "").strip()

    return ""


# Ensure parent directory is on the path for backend.* imports
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))


# ---------------------------------------------------------------------------
# Optional module imports — each wrapped in try/except
# ---------------------------------------------------------------------------

# Core capabilities (separated from enhanced services so that a missing
# ROS2 / third-party dependency in topic_echo_service, performance_service,
# etc. does NOT drag the capabilities manager down to None).
try:
    from backend.capabilities import (
        get_capabilities_manager,
        get_message_envelope,
        reload_capabilities,
    )

    register_module_ok("capabilities")
except ImportError as e:
    register_module_failed("capabilities", str(e))
    print(f"Warning: Capabilities manager not available. Error: {e}")
    get_capabilities_manager = lambda: None
    get_message_envelope = lambda: None
    reload_capabilities = lambda: None

# Enhanced services (ROS2-dependent, optional on RPi)
try:
    from backend.topic_echo_service import (
        get_topic_echo_service,
        topic_echo_router,
    )
    from backend.log_aggregator import get_log_aggregation_service
    from backend.node_lifecycle_service import get_node_lifecycle_service
    from backend.performance_service import get_performance_service

    # Enhanced monitoring (merged into performance_service)
    from backend.performance_service import (
        get_performance_monitor,
        initialize_performance_monitoring,
    )
    from backend.health_monitoring_service import (
        get_health_monitor,
        initialize_health_monitoring,
    )
    from backend.historical_data_service import (
        get_historical_data,
        initialize_historical_data,
    )
    from backend.alert_engine import (
        AlertRule,
        get_alert_engine,
        initialize_alert_engine,
    )
    from backend.debug_tools_service import (
        get_debug_tools_service,
        initialize_debug_tools,
    )
    from backend.session_stats_service import (
        get_session_stats_service,
        initialize_session_stats,
    )

    ENHANCED_SERVICES_AVAILABLE = True
    register_module_ok("enhanced_services")
except ImportError as e:
    register_module_failed("enhanced_services", str(e))
    print(f"Warning: Enhanced services not available, using basic mode. Error: {e}")
    get_topic_echo_service = None
    topic_echo_router = None
    get_log_aggregation_service = None
    get_node_lifecycle_service = None
    get_performance_service = None
    get_performance_monitor = None
    initialize_performance_monitoring = None
    get_health_monitor = None
    initialize_health_monitoring = None
    get_historical_data = None
    initialize_historical_data = None
    AlertRule = None
    get_alert_engine = None
    initialize_alert_engine = None
    get_debug_tools_service = None
    initialize_debug_tools = None
    get_session_stats_service = None
    initialize_session_stats = None
    ENHANCED_SERVICES_AVAILABLE = False

# PID tuning API
try:
    from backend.pid_tuning_api import pid_router, initialize_pid_bridge

    PID_TUNING_AVAILABLE = True
    register_module_ok("pid_tuning")
except ImportError as e:
    register_module_failed("pid_tuning", str(e))
    print(f"Warning: PID tuning API not available. Error: {e}")
    pid_router = None
    initialize_pid_bridge = None
    PID_TUNING_AVAILABLE = False

# Motor config API
try:
    from backend.motor_api import motor_router, initialize_motor_bridge

    MOTOR_CONFIG_AVAILABLE = True
    register_module_ok("motor_config")
except ImportError as e:
    register_module_failed("motor_config", str(e))
    print(f"Warning: Motor config API not available. Error: {e}")
    motor_router = None
    initialize_motor_bridge = None
    MOTOR_CONFIG_AVAILABLE = False

# Field Analysis API
try:
    from backend.analysis_api import analysis_router, initialize_analysis_service

    ANALYSIS_AVAILABLE = True
    register_module_ok("analysis")
except ImportError as e:
    register_module_failed("analysis", str(e))
    print(f"Warning: Analysis API not available. Error: {e}")
    analysis_router = None
    initialize_analysis_service = None
    ANALYSIS_AVAILABLE = False

# Bag Manager API
try:
    from backend.bag_api import bag_router, initialize_bag_service

    BAG_MANAGER_AVAILABLE = True
    register_module_ok("bag_manager")
except ImportError as e:
    register_module_failed("bag_manager", str(e))
    print(f"Warning: Bag Manager API not available. Error: {e}")
    bag_router = None
    initialize_bag_service = None
    BAG_MANAGER_AVAILABLE = False

# Filesystem Browser API
try:
    from backend.filesystem_api import filesystem_router, initialize_filesystem_api

    FILESYSTEM_AVAILABLE = True
    register_module_ok("filesystem")
except ImportError as e:
    register_module_failed("filesystem", str(e))
    print(f"Warning: Filesystem API not available. Error: {e}")
    filesystem_router = None
    initialize_filesystem_api = None
    FILESYSTEM_AVAILABLE = False

# Systemd API
try:
    from backend.systemd_api import systemd_router
    from backend.systemd_api import set_audit_logger as systemd_set_audit

    SYSTEMD_AVAILABLE = True
    register_module_ok("systemd")
except ImportError as e:
    register_module_failed("systemd", str(e))
    print(f"Warning: Systemd API not available. Error: {e}")
    systemd_router = None
    systemd_set_audit = None
    SYSTEMD_AVAILABLE = False

# Sync API
try:
    from backend.sync_api import sync_router
    from backend.sync_api import set_audit_logger as sync_set_audit
    from backend.sync_api import get_sync_manager

    SYNC_AVAILABLE = True
    register_module_ok("sync")
except ImportError as e:
    register_module_failed("sync", str(e))
    print(f"Warning: Sync API not available. Error: {e}")
    sync_router = None
    sync_set_audit = None
    get_sync_manager = None
    SYNC_AVAILABLE = False

# Safety API
try:
    from backend.safety_api import (
        safety_router,
        SafetyManager,
        set_process_manager as safety_set_pm,
        set_audit_logger as safety_set_audit,
        _safety_manager,
    )

    SAFETY_AVAILABLE = True
    register_module_ok("safety")
except ImportError as e:
    register_module_failed("safety", str(e))
    print(f"Warning: Safety API not available. Error: {e}")
    safety_router = None
    SafetyManager = None
    safety_set_pm = None
    safety_set_audit = None
    _safety_manager = None
    SAFETY_AVAILABLE = False

# Launch API
try:
    from backend.launch_api import (
        launch_router,
        ProcessManager,
        set_process_manager as launch_set_pm,
        set_audit_logger as launch_set_audit,
    )

    LAUNCH_AVAILABLE = True
    register_module_ok("launch")
except ImportError as e:
    register_module_failed("launch", str(e))
    print(f"Warning: Launch API not available. Error: {e}")
    launch_router = None
    ProcessManager = None
    launch_set_pm = None
    launch_set_audit = None
    LAUNCH_AVAILABLE = False

# MQTT API
try:
    from backend.mqtt_api import (
        mqtt_router,
        set_mqtt_service as mqtt_set_service,
        set_audit_logger as mqtt_set_audit,
    )

    MQTT_AVAILABLE = True
    register_module_ok("mqtt")
except ImportError as e:
    register_module_failed("mqtt", str(e))
    print(f"Warning: MQTT API not available. Error: {e}")
    mqtt_router = None
    mqtt_set_service = None
    mqtt_set_audit = None
    MQTT_AVAILABLE = False

# Audit Logger
try:
    from backend.audit_logger import AuditLogger

    AUDIT_LOGGER_AVAILABLE = True
    register_module_ok("audit_logger")
except ImportError as e:
    register_module_failed("audit_logger", str(e))
    AuditLogger = None
    AUDIT_LOGGER_AVAILABLE = False

# MQTT Status Service
try:
    from backend.mqtt_status_service import MqttStatusService

    MQTT_STATUS_AVAILABLE = True
    register_module_ok("mqtt_status")
except ImportError as e:
    register_module_failed("mqtt_status", str(e))
    MqttStatusService = None
    MQTT_STATUS_AVAILABLE = False

# Fleet Health Service
try:
    from backend.fleet_health_service import FleetHealthService

    FLEET_HEALTH_AVAILABLE = True
    register_module_ok("fleet_health")
except ImportError as e:
    register_module_failed("fleet_health", str(e))
    FleetHealthService = None
    FLEET_HEALTH_AVAILABLE = False

# Decimation API
try:
    from backend.decimation import decimation_router

    DECIMATION_AVAILABLE = True
    register_module_ok("decimation")
except ImportError as e:
    register_module_failed("decimation", str(e))
    decimation_router = None
    DECIMATION_AVAILABLE = False

# Service Type API
try:
    from backend.service_api import service_type_router

    SERVICE_TYPE_AVAILABLE = True
    register_module_ok("service_type")
except ImportError as e:
    register_module_failed("service_type", str(e))
    service_type_router = None
    SERVICE_TYPE_AVAILABLE = False

# Parameter aggregation API
try:
    from backend.parameter_api import parameter_router

    PARAMETER_AVAILABLE = True
    register_module_ok("parameter")
except ImportError as e:
    register_module_failed("parameter", str(e))
    parameter_router = None
    PARAMETER_AVAILABLE = False

# Operations API (sync.sh subprocess runner)
try:
    from backend.operations_api import (
        operations_router,
        set_entity_manager as operations_set_entity_manager,
        set_audit_logger as operations_set_audit,
    )

    OPERATIONS_AVAILABLE = True
    register_module_ok("operations")
except ImportError as e:
    register_module_failed("operations", str(e))
    operations_router = None
    operations_set_entity_manager = None
    operations_set_audit = None
    OPERATIONS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Module-level service instances (initialized in init_services)
# ---------------------------------------------------------------------------
_process_manager = None
_audit_logger = None
_mqtt_status_service = None
_fleet_health_service = None
_alert_eval_task: Optional[asyncio.Task] = None
_system_state_ref: Optional[dict] = None


def get_process_manager():
    return _process_manager


def get_audit_logger():
    return _audit_logger


def get_mqtt_status_service():
    return _mqtt_status_service


def get_fleet_health_service():
    return _fleet_health_service


# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------


def register_routers(app: FastAPI, role: str = "dev"):
    """Register all available API routers on the FastAPI app.

    Args:
        app: FastAPI application instance.
        role: Dashboard role (dev, vehicle, arm). Controls which
            routers are excluded via ROLE_EXCLUDED_ROUTERS.
    """
    from .app_factory import ROLE_EXCLUDED_ROUTERS
    from .fleet_api import fleet_router, role_config_router

    excluded = ROLE_EXCLUDED_ROUTERS.get(role, set())

    from .health import router as health_router

    app.include_router(health_router)

    # Role config endpoint — always registered (all roles need it)
    app.include_router(role_config_router)
    print("Role config API router registered")

    if PID_TUNING_AVAILABLE and pid_router is not None:
        app.include_router(pid_router)
        print("PID tuning API router registered")

    if MOTOR_CONFIG_AVAILABLE and motor_router is not None and "motor" not in excluded:
        app.include_router(motor_router)
        print("Motor config API router registered")

    if ANALYSIS_AVAILABLE and analysis_router is not None and "analysis" not in excluded:
        app.include_router(analysis_router)
        print("Analysis API router registered")

    if BAG_MANAGER_AVAILABLE and bag_router is not None:
        app.include_router(bag_router)
        print("Bag Manager API router registered")

    if FILESYSTEM_AVAILABLE and filesystem_router is not None:
        initialize_filesystem_api()
        app.include_router(filesystem_router)
        print("Filesystem Browser API router registered")

    if SYSTEMD_AVAILABLE and systemd_router is not None:
        app.include_router(systemd_router)
        print("Systemd API router registered")

    if SYNC_AVAILABLE and sync_router is not None:
        app.include_router(sync_router)
        print("Sync API router registered")

    if SAFETY_AVAILABLE and safety_router is not None:
        app.include_router(safety_router)
        print("Safety API router registered")

    if LAUNCH_AVAILABLE and launch_router is not None:
        app.include_router(launch_router)
        print("Launch API router registered")

    if MQTT_AVAILABLE and mqtt_router is not None and "mqtt" not in excluded:
        app.include_router(mqtt_router)
        print("MQTT API router registered")

    if DECIMATION_AVAILABLE and decimation_router is not None:
        app.include_router(decimation_router)
        print("Decimation API router registered")

    if SERVICE_TYPE_AVAILABLE and service_type_router is not None:
        app.include_router(service_type_router)
        print("Service Type API router registered")

    if PARAMETER_AVAILABLE and parameter_router is not None:
        app.include_router(parameter_router)
        print("Parameter API router registered")

    if OPERATIONS_AVAILABLE and operations_router is not None:
        app.include_router(operations_router)
        print("Operations API router registered")

    if topic_echo_router is not None:
        app.include_router(topic_echo_router)
        print("Topic Echo API router registered")

    # Fleet router — dev role only
    if "fleet" not in excluded:
        app.include_router(fleet_router)
        print("Fleet API router registered")


# ---------------------------------------------------------------------------
# Periodic alert evaluation
# ---------------------------------------------------------------------------

_ALERT_EVAL_INTERVAL_SEC = 30


def _run_alert_evaluation() -> None:
    """Evaluate system metrics against alert rules.

    Reads CPU/memory from psutil and node count from the shared
    system_state dict, then feeds them into the AlertEngine.
    """
    try:
        if not ENHANCED_SERVICES_AVAILABLE or get_alert_engine is None:
            return
        alert_engine = get_alert_engine()
        if alert_engine is None:
            return

        # CPU and memory from psutil (non-blocking, interval=None)
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        alert_engine.check_metric("cpu_percent", cpu)
        alert_engine.check_metric("memory_percent", mem.percent)

        # Node count from shared system state
        if _system_state_ref is not None:
            nodes = _system_state_ref.get("nodes", {})
            alert_engine.check_metric("node_count", len(nodes))
    except Exception:
        logger.debug("Alert evaluation cycle failed", exc_info=True)


async def _alert_evaluation_loop() -> None:
    """Run ``_run_alert_evaluation`` every 30 s in the background."""
    while True:
        await asyncio.sleep(_ALERT_EVAL_INTERVAL_SEC)
        try:
            await asyncio.to_thread(_run_alert_evaluation)
        except Exception:
            logger.debug("Alert evaluation task error", exc_info=True)


# ---------------------------------------------------------------------------
# Service initialization (called from startup event)
# ---------------------------------------------------------------------------


async def init_services(system_state: dict):
    """Initialize all backend services and wire dependencies.

    Args:
        system_state: Shared mutable dict for ROS2 system state.
    """
    global _process_manager, _audit_logger, _mqtt_status_service
    global _alert_eval_task, _system_state_ref, _fleet_health_service

    init_health_registry()

    _system_state_ref = system_state

    capabilities_mgr = get_capabilities_manager()

    # Setup enhanced topic echo service if available
    if get_topic_echo_service:
        try:
            await get_topic_echo_service()
            print("Topic echo service initialized")
        except Exception as e:
            print(f"Topic echo service initialization failed: {e}")

    # Setup advanced log aggregation service
    if (
        get_log_aggregation_service
        and capabilities_mgr
        and capabilities_mgr.is_enabled("logs_history")
    ):
        try:
            await get_log_aggregation_service()
            print("Advanced log aggregation service initialized")
        except Exception as e:
            print(f"Log aggregation service initialization failed: {e}")

    # Node lifecycle service
    if (
        get_node_lifecycle_service
        and capabilities_mgr
        and capabilities_mgr.is_enabled("node_lifecycle")
    ):
        try:
            await get_node_lifecycle_service()
            print("Node lifecycle service initialized")
        except Exception as e:
            print(f"Node lifecycle service initialization failed: {e}")

    # Performance monitoring service
    if (
        get_performance_service
        and capabilities_mgr
        and capabilities_mgr.is_enabled("performance_metrics")
    ):
        try:
            await get_performance_service()
            print("Performance monitoring service initialized")
        except Exception as e:
            print(f"Performance monitoring service initialization failed: {e}")

    # Initialize enhanced services
    if ENHANCED_SERVICES_AVAILABLE:
        try:
            import yaml

            config_path = Path(__file__).parent.parent / "config" / "dashboard.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    enhanced_config = yaml.safe_load(f)
            else:
                enhanced_config = {}

            initialize_performance_monitoring(enhanced_config.get("monitoring", {}))
            print("Enhanced performance monitoring started")

            initialize_health_monitoring()
            print("Health monitoring initialized")

            initialize_historical_data()
            print("Historical data storage ready")

            alert_config_path = Path(__file__).parent.parent / "config" / "alerts.yaml"
            alerts = initialize_alert_engine(
                str(alert_config_path) if alert_config_path.exists() else None
            )
            print(f"Alert engine loaded ({len(alerts.rules)} rules)")

            initialize_session_stats()
            print("Session statistics tracking ready")

            print("Enhanced monitoring services active!")
        except Exception as e:
            print(f"Enhanced services initialization failed: {e}")

    # Shared services: AuditLogger, ProcessManager, MqttStatusService
    try:
        if AUDIT_LOGGER_AVAILABLE and AuditLogger is not None:
            _audit_logger = AuditLogger()
            print("AuditLogger initialized")
    except Exception as e:
        print(f"AuditLogger initialization failed: {e}")

    try:
        if LAUNCH_AVAILABLE and ProcessManager is not None:
            _process_manager = ProcessManager()
            print("ProcessManager initialized")
    except Exception as e:
        print(f"ProcessManager initialization failed: {e}")

    # MqttStatusService — conditional on dashboard.yaml mqtt config (task 1.3)
    try:
        if MQTT_STATUS_AVAILABLE and MqttStatusService is not None:
            _cfg_path = Path(__file__).parent.parent / "config" / "dashboard.yaml"
            _entities_path = Path(__file__).parent.parent / "config" / "entities.yaml"
            _mqtt_cfg: dict = {}
            if _cfg_path.exists():
                with open(_cfg_path) as _f:
                    _full_cfg = yaml.safe_load(_f) or {}
                    _mqtt_cfg = _full_cfg.get("mqtt", {}) or {}

            _broker_host = _resolve_mqtt_broker_host(_cfg_path, _entities_path)
            if _broker_host:
                _mqtt_status_service = MqttStatusService(
                    broker_host=_broker_host,
                    broker_port=int(_mqtt_cfg.get("broker_port", 1883)),
                    heartbeat_timeout=float(_mqtt_cfg.get("heartbeat_timeout_s", 7.5)),
                )
                print(
                    f"MqttStatusService initialized "
                    f"(broker={_broker_host}:"
                    f"{_mqtt_cfg.get('broker_port', 1883)})"
                )
                try:
                    _mqtt_status_service.start()
                    print("MqttStatusService started")
                except Exception as exc:
                    logger.warning("MqttStatusService failed to start: %s", exc)
            else:
                print("MqttStatusService skipped — " "no broker_host in dashboard.yaml mqtt config")
    except Exception as e:
        print(f"MqttStatusService initialization failed: {e}")

    # FleetHealthService — conditional on role == "dev" AND fleet config present
    try:
        if FLEET_HEALTH_AVAILABLE and FleetHealthService is not None:
            import yaml as _fleet_yaml

            _fleet_cfg_path = Path(__file__).parent.parent / "config" / "dashboard.yaml"
            _fleet_full_cfg: dict = {}
            if _fleet_cfg_path.exists():
                with open(_fleet_cfg_path) as _ff:
                    _fleet_full_cfg = _fleet_yaml.safe_load(_ff) or {}

            _fleet_role = _fleet_full_cfg.get("role", "dev")
            _fleet_section = _fleet_full_cfg.get("fleet") or {}

            if _fleet_role == "dev" and _fleet_section:
                _fleet_health_service = FleetHealthService(_fleet_section)
                await _fleet_health_service.start()
                print(
                    f"FleetHealthService initialized "
                    f"({len(_fleet_health_service.get_fleet_status())} members)"
                )
            else:
                print(
                    "FleetHealthService skipped — "
                    f"role={_fleet_role}, fleet config "
                    f"{'present' if _fleet_section else 'absent'}"
                )
    except Exception as e:
        print(f"FleetHealthService initialization failed: {e}")

    # Inject dependencies into API modules
    if _process_manager is not None:
        if launch_set_pm is not None:
            launch_set_pm(_process_manager)
        if safety_set_pm is not None:
            safety_set_pm(_process_manager)

    if _audit_logger is not None:
        if launch_set_audit is not None:
            launch_set_audit(_audit_logger)
        if safety_set_audit is not None:
            safety_set_audit(_audit_logger)
        if systemd_set_audit is not None:
            systemd_set_audit(_audit_logger)
        if sync_set_audit is not None:
            sync_set_audit(_audit_logger)
        if mqtt_set_audit is not None:
            mqtt_set_audit(_audit_logger)
        if operations_set_audit is not None:
            operations_set_audit(_audit_logger)

    if _mqtt_status_service is not None:
        if mqtt_set_service is not None:
            mqtt_set_service(_mqtt_status_service)

    # Initialize Motor config bridge (first — creates RS485 driver)
    rs485_driver = None
    transport_pref = os.environ.get("PRAGATI_MOTOR_TRANSPORT", "auto")
    if MOTOR_CONFIG_AVAILABLE and initialize_motor_bridge is not None:
        try:
            serial_port = os.environ.get("PRAGATI_MOTOR_SERIAL_PORT")
            motor_id_str = os.environ.get("PRAGATI_MOTOR_ID")
            motor_id = int(motor_id_str) if motor_id_str else None
            initialize_motor_bridge(serial_port=serial_port, motor_id=motor_id)
            print("Motor config bridge initialized")
            if serial_port:
                print(f"  RS485 fallback: {serial_port} " f"(motor_id={motor_id or 1})")
                # Grab the RS485 driver to share with PID bridge
                try:
                    from backend.motor_api import _bridge as _motor_bridge

                    if _motor_bridge.has_rs485:
                        rs485_driver = _motor_bridge._rs485_driver
                    # Apply transport preference
                    _motor_bridge.set_transport_preference(transport_pref)
                    print(f"  Transport preference: {transport_pref}")
                except Exception:
                    pass
        except Exception as e:
            print(f"Motor config bridge initialization failed: {e}")

    # Initialize PID tuning bridge (shares RS485 driver from motor bridge)
    if PID_TUNING_AVAILABLE and initialize_pid_bridge is not None:
        try:
            initialize_pid_bridge(rs485_driver=rs485_driver)
            print("PID tuning bridge initialized")
            if rs485_driver is not None:
                print("  PID bridge RS485 fallback: shared driver")
            # Apply transport preference to PID bridge too
            try:
                from backend.pid_tuning_api import _bridge as _pid_bridge

                _pid_bridge.set_transport_preference(transport_pref)
            except Exception:
                pass
        except Exception as e:
            print(f"PID tuning bridge initialization failed: {e}")

    # Initialize Analysis service
    if ANALYSIS_AVAILABLE and initialize_analysis_service is not None:
        try:
            initialize_analysis_service()
            print("Analysis service initialized")
        except Exception as e:
            print(f"Analysis service initialization failed: {e}")

    # Initialize Bag Manager service
    if BAG_MANAGER_AVAILABLE and initialize_bag_service is not None:
        try:
            initialize_bag_service()
            print("Bag Manager service initialized")
        except Exception as e:
            print(f"Bag Manager service initialization failed: {e}")

    # Start periodic alert evaluation background task
    if ENHANCED_SERVICES_AVAILABLE and get_alert_engine is not None:
        try:
            _alert_eval_task = asyncio.create_task(_alert_evaluation_loop())
            print("Alert evaluation task started " f"(every {_ALERT_EVAL_INTERVAL_SEC}s)")
        except Exception as e:
            logger.warning("Failed to start alert evaluation task: %s", e)


async def shutdown_services():
    """Gracefully shut down all services."""
    global _alert_eval_task, _fleet_health_service

    # Cancel periodic alert evaluation task
    if _alert_eval_task is not None:
        _alert_eval_task.cancel()
        try:
            await _alert_eval_task
        except asyncio.CancelledError:
            pass
        _alert_eval_task = None
        print("Alert evaluation task cancelled")

    # Stop MQTT status service (3s timeout — task 1.2)
    if _mqtt_status_service is not None:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_mqtt_status_service.stop),
                timeout=3.0,
            )
            print("MqttStatusService stopped")
        except asyncio.TimeoutError:
            logger.warning("MqttStatusService stop timed out (3s) — force-closing")
            _mqtt_status_service._running = False
            _mqtt_status_service._connected = False
        except Exception as e:
            print(f"Error stopping MqttStatusService: {e}")

    # Stop FleetHealthService
    if _fleet_health_service is not None:
        try:
            await asyncio.wait_for(
                _fleet_health_service.stop(),
                timeout=3.0,
            )
            _fleet_health_service = None
            print("FleetHealthService stopped")
        except asyncio.TimeoutError:
            logger.warning("FleetHealthService stop timed out (3s)")
            _fleet_health_service = None
        except Exception as e:
            print(f"Error stopping FleetHealthService: {e}")
            _fleet_health_service = None

    if get_topic_echo_service:
        try:
            topic_echo_service = await get_topic_echo_service()
            await topic_echo_service.shutdown()
            print("Topic echo service shut down")
        except Exception as e:
            print(f"Error shutting down topic echo service: {e}")

    if get_log_aggregation_service:
        try:
            log_service = await get_log_aggregation_service()
            await log_service.shutdown()
            print("Log aggregation service shut down")
        except Exception as e:
            print(f"Error shutting down log service: {e}")

    if get_node_lifecycle_service:
        try:
            lifecycle_service = await get_node_lifecycle_service()
            await lifecycle_service.shutdown()
            print("Node lifecycle service shut down")
        except Exception as e:
            print(f"Error shutting down node lifecycle service: {e}")

    if get_performance_service:
        try:
            performance_service = await get_performance_service()
            await performance_service.shutdown()
            print("Performance monitoring service shut down")
        except Exception as e:
            print("Error shutting down performance monitoring" f" service: {e}")
