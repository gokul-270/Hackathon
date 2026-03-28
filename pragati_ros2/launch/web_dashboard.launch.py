#!/usr/bin/env python3
"""ROS 2 launch file to start the Pragati web dashboard."""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, LogInfo
from launch.substitutions import LaunchConfiguration


def generate_launch_description() -> LaunchDescription:
    repo_root = Path(__file__).resolve().parent.parent
    dashboard_script = repo_root / "web_dashboard" / "run_dashboard.py"

    host_arg = DeclareLaunchArgument(
        "host",
        default_value="0.0.0.0",
        description="Host address for the dashboard server",
    )
    port_arg = DeclareLaunchArgument(
        "port",
        default_value="8090",
        description="Port for the dashboard server",
    )
    reload_arg = DeclareLaunchArgument(
        "reload",
        default_value="false",
        description="Enable uvicorn reload (true/false)",
    )
    log_level_arg = DeclareLaunchArgument(
        "log_level",
        default_value="info",
        description="Log level for the dashboard backend",
    )

    launch_dashboard = ExecuteProcess(
        cmd=[
            "python3",
            str(dashboard_script),
            "--host",
            LaunchConfiguration("host"),
            "--port",
            LaunchConfiguration("port"),
            "--reload",
            LaunchConfiguration("reload"),
            "--log-level",
            LaunchConfiguration("log_level"),
        ],
        output="screen",
        cwd=str(dashboard_script.parent),
    )

    announce = LogInfo(
        msg=[
            "Web dashboard starting on http://",
            LaunchConfiguration("host"),
            ":",
            LaunchConfiguration("port"),
        ]
    )

    return LaunchDescription([
        host_arg,
        port_arg,
        reload_arg,
        log_level_arg,
        announce,
        launch_dashboard,
    ])
