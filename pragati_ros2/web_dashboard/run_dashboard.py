#!/usr/bin/env python3
"""
Pragati ROS2 Web Dashboard Launcher
Starts the FastAPI backend server with static file serving for the frontend
"""

import os
import sys
import subprocess
import signal
import threading
import time
import argparse
from pathlib import Path

def check_dependencies():
    """Check if required packages are installed"""
    required_packages = ['fastapi', 'uvicorn', 'websockets', 'psutil']
    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("Install them with: pip install " + " ".join(missing_packages))
        return False

    return True

def check_ros2_environment():
    """Check if ROS2 is properly sourced"""
    if 'ROS_DISTRO' not in os.environ:
        print("❌ ROS2 environment not sourced!")
        print("Please run: source /opt/ros/<distro>/setup.bash")
        return False

    print(f"✅ ROS2 {os.environ['ROS_DISTRO']} environment detected")
    return True

def start_dashboard(host: str, port: int, reload: bool, log_level: str):
    """Start the dashboard server"""
    dashboard_dir = Path(__file__).parent
    backend_script = dashboard_dir / "backend" / "dashboard_server.py"

    if not backend_script.exists():
        print(f"❌ Backend script not found at {backend_script}")
        return None

    print("🚀 Starting Pragati ROS2 Dashboard...")
    print(f"📁 Dashboard directory: {dashboard_dir}")
    print(f"🔧 Backend script: {backend_script}")
    print(f"🌐 Web interface will be available at: http://{host}:{port}")
    print("📊 Dashboard will auto-refresh every 2 seconds")
    print("-" * 60)

    # Start the server with uvicorn
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.dashboard_server:app",
        "--host",
        host,
        "--port",
        str(port),
        "--log-level",
        log_level,
    ]

    if reload:
        cmd.append("--reload")

    try:
        # Change to dashboard directory
        os.chdir(dashboard_dir)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        # Print server output
        def print_output():
            for line in process.stdout:
                print(line.strip())

        output_thread = threading.Thread(target=print_output, daemon=True)
        output_thread.start()

        return process

    except Exception as e:
        print(f"❌ Error starting dashboard: {e}")
        return None

def main():
    print("🤖 Pragati ROS2 Dashboard Launcher")
    print("=" * 50)

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Check ROS2 environment
    if not check_ros2_environment():
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Launch the Pragati web dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8090, help="Port to serve on (default: 8090)")
    parser.add_argument("--reload", choices=["true", "false"], default="true",
                        help="Enable uvicorn reload (default: true)")
    parser.add_argument("--log-level", default="info",
                        choices=["critical", "error", "warning", "info", "debug", "trace"],
                        help="Uvicorn log level (default: info)")

    args = parser.parse_args()

    reload_enabled = args.reload.lower() == "true"

    # Start dashboard
    process = start_dashboard(args.host, args.port, reload_enabled, args.log_level)
    if not process:
        sys.exit(1)

    print("\n✅ Dashboard started successfully!")
    print(f"🔗 Open http://{args.host}:{args.port} in your web browser")
    print("🔄 Dashboard will automatically detect and display ROS2 nodes, topics, and services")
    print("\nPress Ctrl+C to stop the dashboard")
    print("-" * 60)

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\n🛑 Shutting down dashboard...")
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        print("✅ Dashboard stopped")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Wait for process to complete
    try:
        process.wait()
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)

if __name__ == "__main__":
    main()
