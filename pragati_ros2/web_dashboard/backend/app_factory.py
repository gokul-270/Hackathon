"""
App Factory — FastAPI app creation, router wiring, and lifecycle management.

Extracted from dashboard_server.py as part of the backend restructure.
Creates a fully configured FastAPI app with all routers, WebSocket endpoints,
startup/shutdown events, and static file serving.
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

import yaml

from .fleet_api import fleet_router, parse_role_config, set_dashboard_role
from .version import get_version
from .middleware import ApiKeyAuthMiddleware, RateLimitMiddleware

# Routers excluded per role (empty set = all routers allowed).
# This is a product decision — hardcoded, not config-driven (design D3).
# NOTE (Phase 3, D1): Dashboard role is always "dev" now. The exclusion
# dict is retained for reference but the role is hardcoded below so
# the excluded set is always empty.
ROLE_EXCLUDED_ROUTERS: dict[str, set[str]] = {
    "dev": set(),  # dev gets everything
    "vehicle": {"motor", "fleet", "analysis"},
    "arm": {"mqtt", "fleet", "analysis"},
}


def _load_config() -> dict:
    """Load dashboard.yaml configuration."""
    config_path = Path(__file__).resolve().parent.parent / "config" / "dashboard.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns a fully configured FastAPI app with CORS, auth, rate-limit
    middleware, all routers registered, WebSocket endpoints wired,
    startup/shutdown events attached, and static files mounted.
    """
    config = _load_config()

    # --- Role configuration ------------------------------------------------
    # Phase 3 (D1): Dashboard role is always "dev". We still call
    # parse_role_config / set_dashboard_role so existing code paths
    # (fleet_api, service_registry) work unchanged, but the value is
    # hardcoded. ROLE_EXCLUDED_ROUTERS["dev"] == set() so no routers
    # are excluded.
    _parsed_role = parse_role_config(config)  # noqa: F841 — kept for log
    role = "dev"  # hardcoded — design decision D1
    set_dashboard_role(role)

    # --- Shared state & service accessors ---------------------------------
    from .ros2_monitor import system_state, setup_ros2_monitoring
    from .service_registry import (
        get_capabilities_manager,
        get_message_envelope,
        get_mqtt_status_service,
        get_process_manager,
        get_sync_manager,
        get_performance_monitor,
        get_health_monitor,
        get_alert_engine,
        get_topic_echo_service,
        init_services,
        register_routers,
        reload_capabilities,
        shutdown_services,
        ENHANCED_SERVICES_AVAILABLE,
        SAFETY_AVAILABLE,
        _safety_manager,
    )
    from .websocket_handlers import (
        handle_arms_status,
        handle_launch_output,
        handle_main_websocket,
        handle_sync_output,
        mqtt_ws_bridge_loop,
        websocket_connections,
    )
    from .health import init_status_deps
    from .api_routes_core import init_core_deps, router as core_router
    from .api_routes_performance import (
        init_performance_deps,
        router as perf_router,
    )
    from .api_routes_operations import (
        init_operations_deps,
        router as ops_router,
    )
    from .static_files import router as static_router, mount_static_files

    server_start_time = time.time()

    capabilities_manager = get_capabilities_manager()
    message_envelope = get_message_envelope()

    # --- Lifespan context manager -----------------------------------------

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        """Initialize ROS2 monitoring and backend services on startup,
        gracefully shut down on exit."""
        # -- Startup -------------------------------------------------------
        print("Starting Pragati ROS2 Dashboard...")

        if capabilities_manager:
            enabled_caps = capabilities_manager.get_enabled_capabilities()
            if enabled_caps:
                print(f"Enhanced capabilities enabled: " f"{', '.join(enabled_caps)}")
            else:
                print("Running in basic compatibility mode")

        setup_ros2_monitoring(system_state)
        await init_services(system_state)

        # Phase 3 (Task 3.1): Start EntityManager polling loop
        from .entity_manager import init_entity_manager
        from .entity_manager import get_entity_manager

        await init_entity_manager()

        mqtt_svc = get_mqtt_status_service()
        entity_manager = get_entity_manager()
        if mqtt_svc is not None and entity_manager is not None:
            mqtt_svc.subscribe_changes(entity_manager._handle_mqtt_change)

        # Inject entity manager into operations module
        from .entity_manager import get_entity_manager
        from .service_registry import (
            OPERATIONS_AVAILABLE,
            operations_set_entity_manager,
        )

        if OPERATIONS_AVAILABLE and operations_set_entity_manager is not None:
            em = get_entity_manager()
            if em is not None:
                operations_set_entity_manager(em)
                print("Operations: entity manager injected")

        # Start MQTT → WebSocket bridge loop (task 2.3)
        application.state.mqtt_ws_bridge_task = asyncio.create_task(
            mqtt_ws_bridge_loop(get_mqtt_status_service)
        )

        # Start heartbeat checker in event loop context (task 5.2)
        mqtt_svc = get_mqtt_status_service()
        if mqtt_svc is not None:
            mqtt_svc.start_heartbeat_checker()

        print("Dashboard server ready!")
        print("WebSocket endpoint: ws://localhost:8090/ws")
        print("API endpoints: http://localhost:8090/api/capabilities")

        yield

        # -- Shutdown ------------------------------------------------------
        from .ros2_monitor import get_ros2_executor

        print("Shutting down dashboard...")

        # Phase 3 (Task 3.1): Stop EntityManager
        from .entity_manager import shutdown_entity_manager
        from .entity_manager import get_entity_manager

        mqtt_svc = get_mqtt_status_service()
        entity_manager = get_entity_manager()
        if mqtt_svc is not None and entity_manager is not None:
            mqtt_svc.unsubscribe_changes(entity_manager._handle_mqtt_change)

        await shutdown_entity_manager()

        # Cancel MQTT WS bridge task
        bridge_task = getattr(application.state, "mqtt_ws_bridge_task", None)
        if bridge_task is not None:
            bridge_task.cancel()
            try:
                await bridge_task
            except asyncio.CancelledError:
                pass

        await shutdown_services()

        executor = get_ros2_executor()
        if executor:
            executor.shutdown()

        for ws in list(websocket_connections.values()):
            try:
                await ws.close()
            except Exception as e:
                print(f"Error closing WebSocket during shutdown: {e}")

    app = FastAPI(
        title="Pragati ROS2 Dashboard",
        version=get_version(),
        lifespan=lifespan,
    )

    # --- Middleware --------------------------------------------------------
    cors_config = config.get("cors", {})
    allowed_origins = cors_config.get(
        "allowed_origins",
        ["http://localhost:8090", "http://127.0.0.1:8090"],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    auth_config = config.get("auth", {})
    api_key = os.environ.get("PRAGATI_DASHBOARD_AUTH_API_KEY") or auth_config.get("api_key", "")
    auth_enabled = auth_config.get("enabled", False)
    app.add_middleware(
        ApiKeyAuthMiddleware,
        api_key=api_key,
        enabled=auth_enabled,
    )

    security_config = config.get("security", {})
    rpm = security_config.get("api_rate_limit_per_minute", 1000)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=rpm)

    # Prevent browser caching of JS/MJS files so deployments take effect
    # immediately without requiring manual hard-refresh.
    from starlette.middleware.base import BaseHTTPMiddleware

    class NoCacheJSMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            path = request.url.path
            if path.endswith((".mjs", ".js", ".css")):
                response.headers["Cache-Control"] = "no-cache, must-revalidate"
            return response

    app.add_middleware(NoCacheJSMiddleware)

    # --- Router registration ----------------------------------------------
    register_routers(app, role=role)
    app.include_router(core_router)
    app.include_router(perf_router)
    app.include_router(ops_router)
    app.include_router(static_router)

    # Phase 3 (Task 3.1): Register entity-centric routers
    from .entity_manager import entity_router
    from .entity_proxy import entity_proxy_router
    from .entity_ros2_router import entity_ros2_router

    app.include_router(entity_router)
    app.include_router(entity_proxy_router)
    app.include_router(entity_ros2_router)

    # Phase 3b: Entity-scoped motor & rosbag routers
    from .entity_motor_router import entity_motor_router
    from .entity_rosbag_router import entity_rosbag_router

    app.include_router(entity_motor_router)
    app.include_router(entity_rosbag_router)

    # Phase 4: Entity-scoped system management router
    from .entity_system_router import entity_system_router

    app.include_router(entity_system_router)

    # Entity-scoped system stats router (CPU, RAM, disk, temp, processes)
    from .entity_system_stats_router import entity_system_stats_router

    app.include_router(entity_system_stats_router)

    # Active fleet diagnostics router (dashboard-reliability-hardening)
    from .diagnostics_api import diagnostics_router

    app.include_router(diagnostics_router)

    # Wire dependencies into extracted modules
    init_status_deps(system_state, capabilities_manager, message_envelope, server_start_time)
    init_core_deps(system_state, capabilities_manager, message_envelope)
    init_performance_deps(system_state, capabilities_manager)
    init_operations_deps(system_state, capabilities_manager)

    # --- WebSocket endpoints ----------------------------------------------

    @app.websocket("/ws")
    async def ws_main(websocket: WebSocket):
        await handle_main_websocket(
            websocket,
            system_state=system_state,
            capabilities_manager=capabilities_manager,
            message_envelope=message_envelope,
            reload_capabilities=reload_capabilities,
            get_topic_echo_service=get_topic_echo_service,
            get_performance_monitor=get_performance_monitor,
            get_health_monitor=get_health_monitor,
            get_alert_engine=get_alert_engine,
            enhanced_services_available=ENHANCED_SERVICES_AVAILABLE,
            safety_manager=_safety_manager if SAFETY_AVAILABLE else None,
        )

    @app.websocket("/ws/launch/{role}/output")
    async def ws_launch(websocket: WebSocket, role: str):
        await handle_launch_output(websocket, role, get_process_manager)

    @app.websocket("/ws/arms/status")
    async def ws_arms(websocket: WebSocket):
        await handle_arms_status(websocket, get_mqtt_status_service)

    @app.websocket("/ws/sync/output")
    async def ws_sync(websocket: WebSocket):
        await handle_sync_output(websocket, get_sync_manager)

    # --- Static files (must be last) --------------------------------------
    mount_static_files(app)

    return app
