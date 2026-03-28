#!/usr/bin/env python3
"""
Vehicle + Arm Sim — Testing Web UI Backend
===========================================
FastAPI server on port 8081 providing:
  - Static file serving (HTML, CSS, JS)
  - URDF model spawn/respawn in Gazebo (gz service CLI)
  - E-STOP via rclpy (publishes zero cmd_vel + zero arm joints)
  - System status (Gazebo, rosbridge, kinematics node)

Vehicle & arm CONTROL is handled externally via:
  - rosbridge (browser ↔ ROS2) at port 9090
  - kinematics_node (cmd_vel → steering/wheel)
  - parameter_bridge (ROS2 ↔ Gazebo topics)
"""

import argparse
import logging
import math
import os
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from starlette.responses import Response
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# ROS2 import (optional — degrades gracefully)
# ---------------------------------------------------------------------------
HAS_RCLPY = False
try:
    import rclpy
    from geometry_msgs.msg import Twist
    from std_msgs.msg import Float64

    HAS_RCLPY = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("testing_backend")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PKG_DIR = _SCRIPT_DIR.parent
_WORKSPACE_ROOT = _PKG_DIR.parent.parent
_URDF_SAVED_DIR = _PKG_DIR / "urdf" / "saved"
_MESHES_DIR = _PKG_DIR / "meshes"
_TMP_URDF_PATH = Path("/tmp/vehicle_arm_testing.urdf")


# ---------------------------------------------------------------------------
# Gazebo helpers
# ---------------------------------------------------------------------------
def _is_gazebo_running() -> bool:
    """Check if a Gazebo sim server process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "gz sim"],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def _detect_gz_world_name() -> str:
    """Auto-detect the Gazebo world name from running services."""
    try:
        result = subprocess.run(
            ["gz", "service", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            m = re.search(r"/world/([^/]+)/create", line)
            if m:
                return m.group(1)
    except Exception:
        pass
    return "empty"


def _is_process_running(name: str) -> bool:
    """Check if a named process is running via pgrep."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", name],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# ROS2 E-STOP Node
# ---------------------------------------------------------------------------
class EstopNode:
    """
    Lightweight ROS2 node that publishes zero commands for E-STOP.

    Publishes to:
      - /cmd_vel (zero Twist) — stops vehicle via kinematics_node
      - /joint{3,4,5}_cmd, /joint{3,4,5}_copy_cmd (zero Float64) — stops arms
    """

    def __init__(self):
        self.node = None
        self.cmd_vel_pub = None
        self.arm_pubs = {}
        self._initialized = False
        self._spin_thread = None

    def start(self):
        """Initialize ROS2 node and publishers."""
        if not HAS_RCLPY:
            logger.warning("rclpy not available — E-STOP via ROS2 disabled")
            return
        try:
            if not rclpy.ok():
                rclpy.init()
            self.node = rclpy.create_node("testing_estop")
            self.cmd_vel_pub = self.node.create_publisher(Twist, "/cmd_vel", 10)

            # Arm joint publishers (matching Gazebo URDF plugin topics)
            arm_topics = [
                "/joint3_cmd",
                "/joint4_cmd",
                "/joint5_cmd",
                "/joint3_copy_cmd",
                "/joint4_copy_cmd",
                "/joint5_copy_cmd",
                "/arm_joint3_copy1_cmd",
                "/arm_joint4_copy1_cmd",
                "/arm_joint5_copy1_cmd",
            ]
            for topic in arm_topics:
                self.arm_pubs[topic] = self.node.create_publisher(
                    Float64, topic, 10
                )

            self._initialized = True

            # Background spin
            self._spin_thread = threading.Thread(target=self._spin, daemon=True)
            self._spin_thread.start()
            logger.info("E-STOP ROS2 node initialized (%d publishers)", 1 + len(arm_topics))
        except Exception as e:
            logger.error("Failed to initialize E-STOP node: %s", e)

    def _spin(self):
        """Spin ROS2 node in background thread."""
        try:
            while rclpy.ok():
                rclpy.spin_once(self.node, timeout_sec=0.05)
        except Exception:
            pass

    def execute_estop(self) -> bool:
        """Publish zero on all control topics."""
        if not self._initialized:
            logger.warning("E-STOP not initialized — using gz topic fallback")
            return self._estop_gz_fallback()

        try:
            # Zero vehicle velocity (burst — 5 messages for reliability)
            twist = Twist()
            for _ in range(5):
                self.cmd_vel_pub.publish(twist)

            # Zero arm joints (burst — 3 messages each)
            zero_msg = Float64()
            zero_msg.data = 0.0
            for pub in self.arm_pubs.values():
                for _ in range(3):
                    pub.publish(zero_msg)

            logger.info("E-STOP executed: all commands zeroed via rclpy")
            return True
        except Exception as e:
            logger.error("E-STOP publish failed: %s — trying gz fallback", e)
            return self._estop_gz_fallback()

    def _estop_gz_fallback(self) -> bool:
        """Fallback E-STOP using gz topic CLI (works without rclpy)."""
        try:
            topics = [
                "/steering/front",
                "/steering/left",
                "/steering/right",
                "/wheel/front/velocity",
                "/wheel/left/velocity",
                "/wheel/right/velocity",
                "/joint3_cmd",
                "/joint4_cmd",
                "/joint5_cmd",
                "/joint3_copy_cmd",
                "/joint4_copy_cmd",
                "/joint5_copy_cmd",
                "/arm_joint3_copy1_cmd",
                "/arm_joint4_copy1_cmd",
                "/arm_joint5_copy1_cmd",
            ]
            for topic in topics:
                subprocess.Popen(
                    [
                        "gz",
                        "topic",
                        "-t",
                        topic,
                        "-m",
                        "gz.msgs.Double",
                        "-p",
                        "data: 0.0",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            logger.info("E-STOP executed via gz topic fallback")
            return True
        except Exception as e:
            logger.error("gz topic E-STOP fallback failed: %s", e)
            return False

    def shutdown(self):
        """Clean shutdown of ROS2 node."""
        try:
            if self.node:
                self.node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Vehicle Arm Sim — Testing UI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

estop_node = EstopNode()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class SpawnRequest(BaseModel):
    urdf_file: str = ""


# ---------------------------------------------------------------------------
# Static file serving (no-cache to prevent stale JS/CSS)
# ---------------------------------------------------------------------------
def _no_cache_file(path: Path, media_type: str) -> Response:
    """Serve a file with no-cache headers."""
    if not path.exists():
        return HTMLResponse("", 404)
    resp = FileResponse(path, media_type=media_type)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.get("/")
async def index():
    return _no_cache_file(_SCRIPT_DIR / "testing_ui.html", "text/html")


@app.get("/testing_ui.css")
async def serve_css():
    return _no_cache_file(_SCRIPT_DIR / "testing_ui.css", "text/css")


@app.get("/testing_ui.js")
async def serve_js():
    return _no_cache_file(_SCRIPT_DIR / "testing_ui.js", "application/javascript")


# ---------------------------------------------------------------------------
# Status & URDF list
# ---------------------------------------------------------------------------
@app.get("/api/status")
async def get_status():
    """System status: Gazebo, rosbridge, kinematics node."""
    gz_running = _is_gazebo_running()
    return {
        "gazebo_running": gz_running,
        "world_name": _detect_gz_world_name() if gz_running else None,
        "rosbridge_running": _is_process_running("rosbridge"),
        "kinematics_running": _is_process_running("kinematics_node"),
        "estop_rclpy": estop_node._initialized,
    }


@app.get("/api/urdf/list")
async def list_urdf_files():
    """List available URDF files (session + saved)."""
    files = []

    # Session URDF
    session_urdf = Path.home() / ".vehicle_arm_sim" / "latest_editor.urdf"
    if session_urdf.exists():
        files.append(
            {
                "name": "[Session] latest_editor.urdf",
                "path": str(session_urdf),
                "size": session_urdf.stat().st_size,
                "modified": session_urdf.stat().st_mtime,
            }
        )

    # Saved URDFs
    if _URDF_SAVED_DIR.exists():
        for f in sorted(
            _URDF_SAVED_DIR.glob("*.urdf"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            files.append(
                {
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "modified": f.stat().st_mtime,
                }
            )
    return {"files": files}


# ---------------------------------------------------------------------------
# Spawn / Respawn
# ---------------------------------------------------------------------------
@app.post("/api/spawn")
async def spawn_model(req: SpawnRequest):
    """Spawn URDF model into Gazebo via gz service CLI."""
    # Find URDF
    urdf_path = None
    if req.urdf_file:
        urdf_path = Path(req.urdf_file)
    else:
        session = Path.home() / ".vehicle_arm_sim" / "latest_editor.urdf"
        if session.exists():
            urdf_path = session
        else:
            saved = sorted(
                _URDF_SAVED_DIR.glob("*.urdf"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if saved:
                urdf_path = saved[0]

    if not urdf_path or not urdf_path.exists():
        raise HTTPException(status_code=404, detail="No URDF file found")

    logger.info("Spawning URDF: %s", urdf_path)

    # Write to temp
    urdf_content = urdf_path.read_text(encoding="utf-8")
    _TMP_URDF_PATH.write_text(urdf_content, encoding="utf-8")

    if not _is_gazebo_running():
        return {"status": "error", "message": "Gazebo is not running"}

    # Convert URDF → SDF
    sdf_path = Path("/tmp/vehicle_arm_testing.sdf")
    use_sdf = False
    try:
        result = subprocess.run(
            ["gz", "sdf", "-p", str(_TMP_URDF_PATH)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            sdf_content = result.stdout
            sdf_path.write_text(sdf_content, encoding="utf-8")
            use_sdf = True
            logger.info("URDF → SDF conversion OK (%d bytes)", len(sdf_content))
        else:
            logger.warning("SDF conversion failed: %s", result.stderr[:200])
    except Exception as exc:
        logger.warning("SDF conversion error: %s", exc)

    world_name = _detect_gz_world_name()
    logger.info("Gazebo world: %s", world_name)

    # Remove existing model
    try:
        subprocess.run(
            [
                "gz",
                "service",
                "-s",
                f"/world/{world_name}/remove",
                "--reqtype",
                "gz.msgs.Entity",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                "3000",
                "--req",
                'name: "vehicle_arm" type: MODEL',
            ],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass

    # Build spawn content with resolved mesh paths
    if use_sdf:
        spawn_content = sdf_path.read_text(encoding="utf-8")
        spawn_content = spawn_content.replace(
            "model://vehicle_arm_sim/meshes/", str(_MESHES_DIR) + "/"
        )
    else:
        spawn_content = _TMP_URDF_PATH.read_text(encoding="utf-8")
        spawn_content = spawn_content.replace(
            "package://vehicle_arm_sim/meshes/", str(_MESHES_DIR) + "/"
        )

    # Escape for protobuf inline string
    escaped = (
        spawn_content.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )

    spawn_req = (
        f'sdf: "{escaped}" '
        f'name: "vehicle_arm" '
        f"pose: {{ position: {{ x: 0, y: 0, z: 1.0 }} "
        f"orientation: {{ x: 0.7071068, y: 0, z: 0, w: 0.7071068 }} }}"
    )
    try:
        result = subprocess.run(
            [
                "gz",
                "service",
                "-s",
                f"/world/{world_name}/create",
                "--reqtype",
                "gz.msgs.EntityFactory",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                "5000",
                "--req",
                spawn_req,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        combined = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or "Unknown"
            return {"status": "error", "message": f"Spawn failed: {err}"}
        if "timed out" in combined.lower():
            return {"status": "error", "message": "Gazebo spawn service timed out"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Spawn command timed out"}
    except FileNotFoundError:
        return {"status": "error", "message": "'gz' command not found"}

    logger.info("Model spawned (SDF=%s)", use_sdf)
    return {
        "status": "ok",
        "message": "Model spawned in Gazebo",
        "urdf_file": str(urdf_path),
        "used_sdf": use_sdf,
    }


# ---------------------------------------------------------------------------
# E-STOP
# ---------------------------------------------------------------------------
@app.post("/api/estop")
async def emergency_stop():
    """
    Emergency stop — zero ALL actuators.

    Publishes zero cmd_vel (vehicle) + zero arm joints via rclpy.
    Falls back to gz topic CLI if rclpy is unavailable.
    """
    ok = estop_node.execute_estop()
    return {
        "status": "ok" if ok else "partial",
        "message": "E-STOP: all commands zeroed" if ok else "E-STOP: fallback used",
    }


# ---------------------------------------------------------------------------
# Joint limits info
# ---------------------------------------------------------------------------
JOINT_LIMITS = {
    "joint3": {"min": -0.9, "max": 0.0, "unit": "rad", "topic": "/joint3_cmd"},
    "joint4": {"min": -0.250, "max": 0.350, "unit": "m", "topic": "/joint4_cmd"},
    "joint5": {"min": 0.0, "max": 0.450, "unit": "m", "topic": "/joint5_cmd"},
    "joint3_copy": {"min": -0.9, "max": 0.0, "unit": "rad", "topic": "/joint3_copy_cmd"},
    "joint4_copy": {"min": -0.250, "max": 0.350, "unit": "m", "topic": "/joint4_copy_cmd"},
    "joint5_copy": {"min": 0.0, "max": 0.450, "unit": "m", "topic": "/joint5_copy_cmd"},
    "joint3_copy1": {"min": -0.9, "max": 0.0, "unit": "rad", "topic": "/arm_joint3_copy1_cmd"},
    "joint4_copy1": {"min": -0.250, "max": 0.350, "unit": "m", "topic": "/arm_joint4_copy1_cmd"},
    "joint5_copy1": {"min": 0.0, "max": 0.450, "unit": "m", "topic": "/arm_joint5_copy1_cmd"},
}


@app.get("/api/joint_limits")
async def get_joint_limits():
    return {"limits": JOINT_LIMITS}


# ---------------------------------------------------------------------------
# Camera → World FK
# ---------------------------------------------------------------------------
# T_world_camera derived from vehicle_arm_merged.urdf + spawn pose (Rx 90°, z=1.0).
# Camera joint: xyz=(1.55, -0.25, 0.9) rpy=(-1.5708, 0, -0.2618) rel. base-v1.
# Vehicle spawn: z=1.0, orientation=(x=0.7071068, y=0, z=0, w=0.7071068) = Rx(90°).
#
# Row 0: [ 0.9659,  0.0,    0.2588,  1.55 ]
# Row 1: [ 0.0,     1.0,    0.0,    -0.90 ]
# Row 2: [-0.2588,  0.0,    0.9659,  0.75 ]
# Row 3: [ 0.0,     0.0,    0.0,     1.0  ]
_T_WC_R00 = 0.9659
_T_WC_R02 = 0.2588
_T_WC_TX  = 1.55
_T_WC_TY  = -0.90
_T_WC_R20 = -0.2588
_T_WC_R22 = 0.9659
_T_WC_TZ  = 0.75


def cam_to_world(cam_x: float, cam_y: float, cam_z: float) -> tuple[float, float, float]:
    """Convert camera-frame point to Gazebo world frame via pre-computed FK matrix."""
    wx = _T_WC_R00 * cam_x + _T_WC_R02 * cam_z + _T_WC_TX
    wy = cam_y + _T_WC_TY
    wz = _T_WC_R20 * cam_x + _T_WC_R22 * cam_z + _T_WC_TZ
    return wx, wy, wz


# ---------------------------------------------------------------------------
# Cam marker state
# ---------------------------------------------------------------------------
_spawned_marker_names: list[str] = []

# SDF template for a 0.05 m radius sphere (visual only, no collision)
_MARKER_SDF_TEMPLATE = (
    "<sdf version='1.7'>"
    "<model name='{name}'>"
    "<static>true</static>"
    "<link name='link'>"
    "<visual name='visual'>"
    "<geometry><sphere><radius>0.05</radius></sphere></geometry>"
    "<material><ambient>1 0 0 1</ambient><diffuse>1 0 0 1</diffuse></material>"
    "</visual>"
    "</link>"
    "</model>"
    "</sdf>"
)


class CamMarkerPlaceRequest(BaseModel):
    cam_x: float
    cam_y: float
    cam_z: float


@app.post("/api/cam_markers/place")
async def cam_markers_place(req: CamMarkerPlaceRequest):
    """Convert camera-frame coords to world frame and spawn a sphere marker in Gazebo."""
    wx, wy, wz = cam_to_world(req.cam_x, req.cam_y, req.cam_z)
    marker_name = f"cam_marker_{uuid.uuid4().hex[:8]}"

    sdf_str = _MARKER_SDF_TEMPLATE.format(name=marker_name)
    escaped = (
        sdf_str.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )
    world_name = _detect_gz_world_name()
    spawn_req = (
        f'sdf: "{escaped}" '
        f'name: "{marker_name}" '
        f"pose: {{ position: {{ x: {wx}, y: {wy}, z: {wz} }} }}"
    )
    subprocess.run(
        [
            "gz", "service",
            "-s", f"/world/{world_name}/create",
            "--reqtype", "gz.msgs.EntityFactory",
            "--reptype", "gz.msgs.Boolean",
            "--timeout", "5000",
            "--req", spawn_req,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    _spawned_marker_names.append(marker_name)
    return {"status": "ok", "marker_name": marker_name, "world_pos": {"x": wx, "y": wy, "z": wz}}


@app.post("/api/cam_markers/clear")
async def cam_markers_clear():
    """Remove all previously spawned cam marker spheres from Gazebo."""
    world_name = _detect_gz_world_name()
    for name in list(_spawned_marker_names):
        subprocess.run(
            [
                "gz", "service",
                "-s", f"/world/{world_name}/remove",
                "--reqtype", "gz.msgs.Entity",
                "--reptype", "gz.msgs.Boolean",
                "--timeout", "3000",
                "--req", f'name: "{name}" type: MODEL',
            ],
            capture_output=True,
            timeout=10,
        )
    _spawned_marker_names.clear()
    return {"status": "ok", "cleared": 0}


# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    estop_node.start()
    logger.info("Testing backend ready (rclpy=%s)", HAS_RCLPY)


@app.on_event("shutdown")
async def on_shutdown():
    estop_node.execute_estop()
    estop_node.shutdown()
    logger.info("Testing backend shutdown")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Testing Web UI Backend")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    logger.info("Starting on %s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
