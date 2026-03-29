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
import asyncio
import logging
import math
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from starlette.responses import Response
from pydantic import BaseModel

from fk_chain import (
    camera_to_world_fk,
    camera_to_arm,
    polar_decompose,
    phi_compensation,
    ARM_CONFIGS,
    J3_MIN,
    J3_MAX,
    J4_MIN,
    J4_MAX,
    J5_MIN,
    J5_MAX,
)
from run_controller import RunController
from run_step_executor import RunStepExecutor
from markdown_reporter import MarkdownReporter

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
# UI Run Flow — module-level state
# ---------------------------------------------------------------------------
_current_run_result: dict | None = None
_run_state: str = "idle"  # "idle" | "running" | "complete"
_estop_event: threading.Event = threading.Event()  # set by /api/estop; cleared at run start

from run_event_bus import RunEventBus
_event_bus: RunEventBus = RunEventBus()


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


@app.get("/scenarios/{name}.json")
async def serve_scenario(name: str):
    """Serve a preset scenario JSON file from the scenarios/ directory."""
    scenario_path = _SCRIPT_DIR / "scenarios" / f"{name}.json"
    if not scenario_path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Scenario '{name}' not found")
    return _no_cache_file(scenario_path, "application/json")


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
    _estop_event.set()
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


def cam_to_world(cam_x: float, cam_y: float, cam_z: float) -> tuple[float, float, float]:
    """Convert camera-frame point to Gazebo world frame via FK.

    Uses Arm 1 with J3=0, J4=0 as default (camera is on Arm 1).
    """
    return camera_to_world_fk(
        cam_x, cam_y, cam_z,
        j3=0.0, j4=0.0,
        arm_config=ARM_CONFIGS['arm1'],
    )


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
# Cotton picking state
# ---------------------------------------------------------------------------
@dataclass
class CottonState:
    """State for a single cotton ball in the collection."""
    name: str
    cam_x: float
    cam_y: float
    cam_z: float
    arm: str
    j4_pos: float = 0.0
    arm_coords: tuple | None = None  # (ax, ay, az) from camera_to_arm
    joint_values: dict | None = None  # {"j3": ..., "j4": ..., "j5": ...}
    status: str = "spawned"  # spawned | picked

_cottons: dict[str, CottonState] = {}  # name → CottonState
_cotton_counter: int = 0
_cotton_spawned: bool = False
_cotton_name: str = ""
_last_cotton_cam: tuple | None = None
_last_cotton_arm: str | None = None
_last_cotton_j4: float = 0.0

# Per-arm cotton colours in RGBA format (r g b a).  Unknown arms fall back to white.
_ARM_COTTON_COLOURS: dict[str, str] = {
    "arm1": "1 0 0 1",  # red
    "arm2": "0 0 1 1",  # blue
}

# SDF template for cotton ball (coloured sphere, 0.04m radius).
# {ambient} and {diffuse} are filled with an RGBA string at spawn time.
_COTTON_SDF_TEMPLATE = (
    "<sdf version='1.7'>"
    "<model name='{name}'>"
    "<static>true</static>"
    "<link name='link'>"
    "<visual name='visual'>"
    "<geometry><sphere><radius>0.04</radius></sphere></geometry>"
    "<material><ambient>{ambient}</ambient><diffuse>{diffuse}</diffuse></material>"
    "</visual>"
    "</link>"
    "</model>"
    "</sdf>"
)


def _gz_spawn_model(name: str, sdf: str, x: float, y: float, z: float, world: str):
    """Spawn an SDF model in Gazebo via gz service create."""
    escaped = (
        sdf.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )
    spawn_req = (
        f'sdf: "{escaped}" '
        f'name: "{name}" '
        f"pose: {{ position: {{ x: {x}, y: {y}, z: {z} }} }}"
    )
    subprocess.run(
        [
            "gz", "service",
            "-s", f"/world/{world}/create",
            "--reqtype", "gz.msgs.EntityFactory",
            "--reptype", "gz.msgs.Boolean",
            "--timeout", "5000",
            "--req", spawn_req,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )


def _gz_remove_model(name: str, world: str):
    """Remove a model from Gazebo via gz service remove."""
    subprocess.run(
        [
            "gz", "service",
            "-s", f"/world/{world}/remove",
            "--reqtype", "gz.msgs.Entity",
            "--reptype", "gz.msgs.Boolean",
            "--timeout", "3000",
            "--req", f'name: "{name}" type: MODEL',
        ],
        capture_output=True,
        timeout=10,
    )


class CottonSpawnRequest(BaseModel):
    cam_x: float
    cam_y: float
    cam_z: float
    arm: str = "arm1"
    j4_pos: float = 0.0


@app.post("/api/cotton/spawn")
def cotton_spawn(req: CottonSpawnRequest):
    """Spawn a cotton ball in Gazebo at the camera-frame position."""
    global _cotton_spawned, _cotton_name, _last_cotton_cam
    global _last_cotton_arm, _last_cotton_j4, _cotton_counter

    arm_config = ARM_CONFIGS.get(req.arm)
    if arm_config is None:
        raise HTTPException(status_code=400, detail=f"Unknown arm: {req.arm}")

    # --- Reachability check ---
    ax, ay, az = camera_to_arm(req.cam_x, req.cam_y, req.cam_z, j4_pos=req.j4_pos)
    result = polar_decompose(ax, ay, az)
    if not result["reachable"]:
        # Build specific reason
        reasons = []
        j3_val = result["j3"]
        j5_val = result["j5"]
        j4_val = result["j4"]
        if j3_val < J3_MIN or j3_val > J3_MAX:
            reasons.append(
                f"J3={j3_val:.3f} rad out of range [{J3_MIN}, {J3_MAX}]"
            )
        if j4_val < J4_MIN or j4_val > J4_MAX:
            reasons.append(
                f"J4={j4_val:.3f} m out of range [{J4_MIN}, {J4_MAX}]"
            )
        if j5_val < J5_MIN or j5_val > J5_MAX:
            reasons.append(
                f"J5={j5_val:.3f} m out of range [{J5_MIN}, {J5_MAX}]"
            )
        if result["r"] <= 0.1:
            reasons.append(f"r={result['r']:.3f} m too small (min 0.1)")
        reason_str = "; ".join(reasons) if reasons else "target unreachable"
        raise HTTPException(
            status_code=400,
            detail=f"Unreachable: {reason_str}",
        )

    # Convert camera coords to world frame via FK
    wx, wy, wz = camera_to_world_fk(
        req.cam_x, req.cam_y, req.cam_z,
        j3=0.0, j4=req.j4_pos,
        arm_config=arm_config,
    )

    # Spawn new cotton with sequential name
    _cotton_name = f"cotton_{_cotton_counter}"
    _cotton_counter += 1
    sdf = _COTTON_SDF_TEMPLATE.format(name=_cotton_name, ambient="1 1 1 1", diffuse="1 1 1 1")
    world_name = _detect_gz_world_name()
    _gz_spawn_model(_cotton_name, sdf, wx, wy, wz, world_name)

    # Add to collection
    _cottons[_cotton_name] = CottonState(
        name=_cotton_name,
        cam_x=req.cam_x,
        cam_y=req.cam_y,
        cam_z=req.cam_z,
        arm=req.arm,
        j4_pos=req.j4_pos,
        arm_coords=(ax, ay, az),
        joint_values={
            "j3": result["j3"],
            "j4": result["j4"],
            "j5": result["j5"],
        },
    )

    _cotton_spawned = True
    _last_cotton_cam = (req.cam_x, req.cam_y, req.cam_z)
    _last_cotton_arm = req.arm
    _last_cotton_j4 = req.j4_pos

    return {
        "status": "ok",
        "cotton_name": _cotton_name,
        "world_x": wx,
        "world_y": wy,
        "world_z": wz,
    }


@app.post("/api/cotton/remove")
def cotton_remove():
    """Remove the last spawned cotton ball from Gazebo."""
    global _cotton_spawned, _last_cotton_cam
    if _cotton_spawned:
        world_name = _detect_gz_world_name()
        _gz_remove_model(_cotton_name, world_name)
        # Remove from collection
        _cottons.pop(_cotton_name, None)
    _cotton_spawned = False
    _last_cotton_cam = None
    return {"status": "ok"}


@app.get("/api/cotton/list")
def cotton_list():
    """Return all cottons in the collection with coords and status."""
    return {
        "cottons": [
            {
                "name": c.name,
                "cam_x": c.cam_x,
                "cam_y": c.cam_y,
                "cam_z": c.cam_z,
                "arm": c.arm,
                "j4_pos": c.j4_pos,
                "arm_coords": list(c.arm_coords) if c.arm_coords else None,
                "joint_values": c.joint_values,
                "status": c.status,
            }
            for c in _cottons.values()
        ]
    }


@app.post("/api/cotton/remove-all")
def cotton_remove_all():
    """Remove all cottons from Gazebo and clear the collection."""
    global _cotton_spawned, _last_cotton_cam

    count = len(_cottons)
    if count > 0:
        world_name = _detect_gz_world_name()
        for name in list(_cottons.keys()):
            _gz_remove_model(name, world_name)
        _cottons.clear()

    _cotton_spawned = False
    _last_cotton_cam = None
    return {"status": "ok", "removed": count}


class CottonComputeRequest(BaseModel):
    cam_x: float = 0.328
    cam_y: float = -0.011
    cam_z: float = -0.003
    arm: str = "arm1"
    j4_pos: float = 0.0
    enable_phi_compensation: bool = False


@app.post("/api/cotton/compute")
def cotton_compute(req: CottonComputeRequest):
    """Compute polar decomposition and joint commands for cotton pick."""
    arm_config = ARM_CONFIGS.get(req.arm)
    if arm_config is None:
        raise HTTPException(status_code=400, detail=f"Unknown arm: {req.arm}")

    ax, ay, az = camera_to_arm(req.cam_x, req.cam_y, req.cam_z, j4_pos=req.j4_pos)
    result = polar_decompose(ax, ay, az)

    j3 = result["j3"]
    j5 = result["j5"]

    if req.enable_phi_compensation:
        j3 = phi_compensation(j3, j5)
        result["reachable"] = (
            J3_MIN <= j3 <= J3_MAX
            and J4_MIN <= result["j4"] <= J4_MAX
            and J5_MIN <= j5 <= J5_MAX
            and result["r"] > 0.1
        )

    j3_clamped = max(J3_MIN, min(J3_MAX, j3))
    j4_clamped = max(J4_MIN, min(J4_MAX, result["j4"]))
    j5_clamped = max(J5_MIN, min(J5_MAX, j5))

    return {
        "arm_x": ax,
        "arm_y": ay,
        "arm_z": az,
        "r": result["r"],
        "theta": result["theta"],
        "phi": result["phi"],
        "j3": j3_clamped,
        "j4": j4_clamped,
        "j5": j5_clamped,
        "j3_raw": j3,
        "j4_raw": result["j4"],
        "j5_raw": j5,
        "reachable": result["reachable"],
        "phi_compensated": req.enable_phi_compensation,
    }


# ---------------------------------------------------------------------------
# Cotton pick endpoints (compute-only — frontend drives animation)
# ---------------------------------------------------------------------------
class CottonPickRequest(BaseModel):
    arm: str = "arm1"
    enable_phi_compensation: bool = False


def _run_spawn_cotton(
    arm_id: str,
    cam_x: float,
    cam_y: float,
    cam_z: float,
    j4_pos: float,
    step_id: int = -1,
) -> str:
    """Spawn a cotton model at cam position for a replay run step.

    Returns the model name so the caller can remove it later.
    Uses the arm-specific FK config so cotton appears at the correct
    world position for each arm.
    """
    global _cotton_counter
    world_name = _detect_gz_world_name()
    arm_config = ARM_CONFIGS[arm_id]
    wx, wy, wz = camera_to_world_fk(cam_x, cam_y, cam_z, j3=0.0, j4=0.0,
                                      arm_config=arm_config)
    name = f"run_cotton_{arm_id}_{_cotton_counter}"
    _cotton_counter += 1
    colour = _ARM_COTTON_COLOURS.get(arm_id, "1 1 1 1")
    sdf = _COTTON_SDF_TEMPLATE.format(name=name, ambient=colour, diffuse=colour)
    _gz_spawn_model(name, sdf, wx, wy, wz, world_name)
    _event_bus.emit({
        "type": "cotton_spawn",
        "arm_id": arm_id,
        "step_id": step_id,
        "cam_x": cam_x,
        "cam_y": cam_y,
        "cam_z": cam_z,
        "world_x": round(wx, 4),
        "world_y": round(wy, 4),
        "world_z": round(wz, 4),
        "model_name": name,
    })
    return name


def _run_remove_cotton(model_name: str) -> None:
    """Remove a cotton model that was spawned during a replay run step."""
    world_name = _detect_gz_world_name()
    _gz_remove_model(model_name, world_name)


def _run_sleep(seconds: float) -> None:
    """time.sleep wrapper used during run replay animation; injectable in tests."""
    time.sleep(seconds)


@app.post("/api/cotton/pick")
def cotton_pick(req: CottonPickRequest):
    """Compute joint values for picking the last spawned cotton. No animation."""

    if _last_cotton_cam is None:
        raise HTTPException(status_code=400, detail="No cotton spawned yet")

    arm_name = _last_cotton_arm or req.arm
    arm_config = ARM_CONFIGS.get(arm_name)
    if arm_config is None:
        raise HTTPException(status_code=400, detail=f"Unknown arm: {arm_name}")

    cam_x, cam_y, cam_z = _last_cotton_cam
    j4_pos = _last_cotton_j4
    ax, ay, az = camera_to_arm(cam_x, cam_y, cam_z, j4_pos=j4_pos)
    result = polar_decompose(ax, ay, az)

    j3 = result["j3"]
    j5 = result["j5"]

    if req.enable_phi_compensation:
        j3 = phi_compensation(j3, j5)

    j3_val = max(J3_MIN, min(J3_MAX, j3))
    j4_val = max(J4_MIN, min(J4_MAX, result["j4"]))
    j5_val = max(J5_MIN, min(J5_MAX, j5))

    reachable = result["reachable"]
    response = {
        "status": "ready",
        "j3": j3_val,
        "j4": j4_val,
        "j5": j5_val,
        "arm": arm_name,
        "cotton_name": _cotton_name,
        "reachable": reachable,
    }
    if not reachable:
        response["reason"] = result.get("reason", "Target outside joint limits")
    return response


class CottonPickAllRequest(BaseModel):
    arm: str = "arm1"
    enable_phi_compensation: bool = False


@app.post("/api/cotton/pick-all")
def cotton_pick_all(req: CottonPickAllRequest):
    """Compute joint values for all spawned cottons, grouped by arm. No animation."""

    to_pick = [c for c in _cottons.values() if c.status == "spawned"]

    if not to_pick:
        return {"status": "nothing_to_pick", "total": 0}

    arms: dict[str, list] = {}
    warnings: list[str] = []

    for cotton in to_pick:
        arm_name = cotton.arm
        arm_config = ARM_CONFIGS.get(arm_name)
        if arm_config is None:
            warnings.append(f"{cotton.name}: unknown arm '{arm_name}'")
            continue

        ax, ay, az = camera_to_arm(cotton.cam_x, cotton.cam_y, cotton.cam_z,
                                   j4_pos=cotton.j4_pos)
        result = polar_decompose(ax, ay, az)

        j3 = result["j3"]
        j5 = result["j5"]
        if req.enable_phi_compensation:
            j3 = phi_compensation(j3, j5)

        j3_val = max(J3_MIN, min(J3_MAX, j3))
        j4_val = max(J4_MIN, min(J4_MAX, result["j4"]))
        j5_val = max(J5_MIN, min(J5_MAX, j5))

        if not result["reachable"]:
            reason = result.get("reason", "outside joint limits")
            warnings.append(f"{cotton.name}: unreachable ({reason})")
            continue

        arms.setdefault(arm_name, []).append({
            "name": cotton.name,
            "j3": j3_val,
            "j4": j4_val,
            "j5": j5_val,
        })

    if not arms:
        response = {"status": "nothing_to_pick", "total": 0}
    else:
        response = {"status": "ready", "arms": arms}

    if warnings:
        response["warnings"] = warnings

    return response


@app.post("/api/cotton/{name}/mark-picked")
def cotton_mark_picked(name: str):
    """Mark a cotton as picked. Called by frontend after J5-extend animation step."""
    if name not in _cottons:
        return JSONResponse(status_code=404, content={"error": f"Cotton '{name}' not found"})
    cotton = _cottons[name]
    if cotton.status == "picked":
        return JSONResponse(status_code=409, content={"error": f"Cotton '{name}' already picked"})
    cotton.status = "picked"
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# UI Run Flow — request models
# ---------------------------------------------------------------------------
class RunStartRequest(BaseModel):
    mode: int
    scenario: dict
    arm_pair: list = ["arm1", "arm2"]


def _gz_publish(topic: str, value: float) -> None:
    """Publish a joint command via gz topic (blocking, triple-publish for reliability)."""
    cmd = [
        "gz", "topic",
        "-t", topic,
        "-m", "gz.msgs.Double",
        "-p", f"data: {value}",
    ]
    for i in range(3):
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace").strip()
            logger.warning(
                "gz publish failed on topic %s (attempt %d/3): %s",
                topic, i + 1, stderr_text or "(no stderr)",
            )
        if i < 2:
            time.sleep(0.050)


# ---------------------------------------------------------------------------
# UI Run Flow — endpoints
# ---------------------------------------------------------------------------

@app.get("/api/run/events")
async def run_events():
    """SSE stream of per-step run events. Opens before POST /api/run/start."""
    async def _generator():
        import json as _json
        import asyncio
        loop = asyncio.get_event_loop()
        gen = _event_bus.subscribe()
        try:
            while True:
                try:
                    event = await loop.run_in_executor(None, next, gen)
                    yield f"data: {_json.dumps(event)}\n\n"
                    if event.get("type") == "run_complete":
                        return
                except StopIteration:
                    return
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.post("/api/run/start")
async def run_start(req: RunStartRequest):
    """Start a replay run with the given mode and scenario data."""
    global _current_run_result, _run_state

    valid_modes = {0, 1, 2, 3}
    if req.mode not in valid_modes:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Invalid mode {req.mode}; must be 0-3")

    # Validate arm_pair
    from fk_chain import ARM_CONFIGS
    valid_arm_ids = set(ARM_CONFIGS.keys())
    if (
        len(req.arm_pair) != 2
        or len(set(req.arm_pair)) != 2
        or not all(a in valid_arm_ids for a in req.arm_pair)
    ):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Invalid arm_pair {req.arm_pair}")

    _run_state = "running"
    _estop_event.clear()
    _event_bus.reset()
    run_id = str(uuid.uuid4())

    executor = RunStepExecutor(
        publish_fn=_gz_publish,
        remove_fn=_run_remove_cotton,
        sleep_fn=_run_sleep,
        estop_check=_estop_event.is_set,
    )
    controller = RunController(
        req.mode,
        executor=executor,
        arm_pair=tuple(req.arm_pair),
        spawn_fn=_run_spawn_cotton,
        remove_fn=_run_remove_cotton,
        event_bus=_event_bus,
    )
    controller.load_scenario(req.scenario)
    summary = await asyncio.to_thread(controller.run)
    json_report_str = controller.get_json_report()

    import json as _json
    report_data = _json.loads(json_report_str)

    # Rename step_reports -> steps for UI consistency
    steps = report_data.pop("step_reports", [])

    md_lines = [
        f"## Run Report",
        f"",
        f"**Mode:** {summary.get('mode', 'unknown')}",
        f"",
        f"| Metric | Value |",
        f"| --- | --- |",
        f"| Total steps | {summary.get('total_steps', 0)} |",
        f"| Near-collision steps | {summary.get('steps_with_near_collision', 0)} |",
        f"| Collision steps | {summary.get('steps_with_collision', 0)} |",
        f"| Blocked or skipped | {summary.get('steps_with_blocked_or_skipped', 0)} |",
        f"| Completed picks | {summary.get('completed_picks', 0)} |",
        f"",
    ]
    md_report = "\n".join(md_lines)

    _current_run_result = {
        "run_id": run_id,
        "summary": summary,
        "steps": steps,
        "md_report": md_report,
    }
    _run_state = "complete"

    _event_bus.emit({
        "type": "run_complete",
        "run_id": run_id,
        "total_steps": summary.get("total_steps", 0),
        "collisions": summary.get("steps_with_collision", 0),
        "completed_picks": summary.get("completed_picks", 0),
    })
    _event_bus.close()

    return {"run_id": run_id, "status": "complete"}


@app.get("/api/run/status")
async def run_status():
    """Return the current run state."""
    return {"state": _run_state}


@app.get("/api/run/report/json")
async def run_report_json():
    """Return the JSON run report for the last completed run."""
    if _current_run_result is None:
        raise HTTPException(status_code=404, detail="No run result available")
    return {
        "summary": _current_run_result["summary"],
        "steps": _current_run_result["steps"],
    }


@app.get("/api/run/report/markdown")
async def run_report_markdown():
    """Return the Markdown run report for the last completed run."""
    if _current_run_result is None:
        raise HTTPException(status_code=404, detail="No run result available")
    from starlette.responses import Response as _Response
    return _Response(content=_current_run_result["md_report"], media_type="text/plain")


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
