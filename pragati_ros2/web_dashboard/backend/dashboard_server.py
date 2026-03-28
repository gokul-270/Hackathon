#!/usr/bin/env python3

"""
Pragati ROS2 Web Dashboard Backend — Entry Point
=================================================

Thin entry point that creates the FastAPI app and runs uvicorn.
All logic lives in dedicated modules:
  - app_factory.py           — App creation, middleware, router wiring, lifecycle
  - service_registry.py      — Service imports, router registration, DI wiring
  - ros2_monitor.py          — ROS2Monitor node, shared system_state, utilities
  - websocket_handlers.py    — WebSocket connection management and broadcast
  - api_routes_core.py       — Core REST endpoints (logs, nodes, lifecycle)
  - api_routes_performance.py — Performance, health, and history endpoints
  - api_routes_operations.py — Alerts, sessions, graph, search, visibility
  - health.py                — Health registry and status endpoints
  - static_files.py          — Static file serving and frontend mount
  - middleware.py            — Auth and rate-limiting middleware

RS485 serial motor support
--------------------------
When ROS2 motor nodes are not running, the dashboard can communicate
directly with MG6010 motors over RS485 serial.  Pass ``--serial-port``
(and optionally ``--motor-id``) on the command line, or set the
environment variables ``PRAGATI_MOTOR_SERIAL_PORT`` and
``PRAGATI_MOTOR_ID`` before launching via an ASGI server.
"""

import os

from backend.app_factory import create_app

app = create_app()

if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Pragati ROS2 Web Dashboard")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PRAGATI_DASHBOARD_SERVER_PORT", 8090)),
        help="HTTP listen port (default: 8090)",
    )
    parser.add_argument(
        "--serial-port",
        type=str,
        default=os.environ.get("PRAGATI_MOTOR_SERIAL_PORT"),
        help=(
            "RS485 serial device for direct motor communication "
            "(e.g. /dev/ttyUSB0). Enables RS485 fallback when "
            "ROS2 motor nodes are not running."
        ),
    )
    parser.add_argument(
        "--motor-id",
        type=int,
        default=int(os.environ.get("PRAGATI_MOTOR_ID", 1)),
        help="Motor ID on the RS485 bus (default: 1)",
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["auto", "rs485", "ros2"],
        default=os.environ.get("PRAGATI_MOTOR_TRANSPORT", "auto"),
        help=(
            "Transport preference: 'auto' (RS485 preferred when available), "
            "'rs485' (force RS485), 'ros2' (force ROS2). Default: auto"
        ),
    )
    args = parser.parse_args()

    # Expose serial config as env vars so create_app() → init_services()
    # can pick them up regardless of entry-point style (CLI vs ASGI).
    if args.serial_port:
        os.environ["PRAGATI_MOTOR_SERIAL_PORT"] = args.serial_port
        os.environ["PRAGATI_MOTOR_ID"] = str(args.motor_id)
    os.environ["PRAGATI_MOTOR_TRANSPORT"] = args.transport

    # Re-create app after env vars are set (module-level `app` was created
    # before argparse ran, so it won't have the serial config yet).
    app = create_app()

    print("Starting Pragati ROS2 Web Dashboard")
    print("=" * 50)
    print(f"Dashboard: http://localhost:{args.port}")
    print(f"API docs:  http://localhost:{args.port}/docs")
    if args.serial_port:
        print(f"RS485:     {args.serial_port} (motor_id={args.motor_id})")
    print(f"Transport: {args.transport}")
    print("")

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
