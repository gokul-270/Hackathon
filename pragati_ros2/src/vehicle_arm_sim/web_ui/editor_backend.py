#!/usr/bin/env python3
"""
URDF Editor Backend -- FastAPI server for the vehicle_arm_sim URDF visual editor.

Serves the web UI and provides API endpoints for loading, saving, validating,
and spawning URDF robot descriptions in the Gazebo simulation environment.

Usage:
    python3 editor_backend.py
    python3 editor_backend.py --port 9090
    python3 editor_backend.py --host 127.0.0.1 --port 8080
"""

import argparse
import datetime
import hashlib
import logging
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
# web_ui/editor_backend.py -> two levels up gives the package root
_THIS_DIR = Path(__file__).resolve().parent
_PKG_ROOT = _THIS_DIR.parent

_URDF_DIR = _PKG_ROOT / "urdf"
_SAVED_DIR = _URDF_DIR / "saved"
_MESHES_DIR = _PKG_ROOT / "meshes"
_DEFAULT_URDF = _URDF_DIR / "vehicle_arm_merged.urdf"
_WEB_UI_DIR = _THIS_DIR

_TMP_URDF_PATH = Path("/tmp/vehicle_arm_editor.urdf")
_WORLDS_DIR = _PKG_ROOT / "worlds"

# Persistent session file: survives backend restarts and is picked up by the
# launch file so Gazebo always starts with the latest editor version.
_SESSION_DIR = Path.home() / ".vehicle_arm_sim"
_SESSION_URDF = _SESSION_DIR / "latest_editor.urdf"

# Install tree path: the launch file in install/ looks for urdf/saved/*.urdf
# We detect the workspace root from the source package location:
#   src/vehicle_arm_sim/web_ui/ => 4 levels up => workspace root
_WORKSPACE_ROOT = _PKG_ROOT.parent.parent
_INSTALL_SAVED_DIR = (
    _WORKSPACE_ROOT / "install" / "vehicle_arm_sim" / "share"
    / "vehicle_arm_sim" / "urdf" / "saved"
)


def _persist_session_urdf(content: str) -> None:
    """Write a copy of the URDF to the session file AND install tree for cross-restart persistence."""
    # 1. Session file (picked up by updated launch file / launch script)
    try:
        _SESSION_DIR.mkdir(parents=True, exist_ok=True)
        _SESSION_URDF.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write session URDF: %s", exc)

    # 2. Copy into install tree so even the old launch file finds it
    try:
        _INSTALL_SAVED_DIR.mkdir(parents=True, exist_ok=True)
        install_target = _INSTALL_SAVED_DIR / "editor_latest.urdf"
        install_target.write_text(content, encoding="utf-8")
        logger.info("Persisted URDF to install tree: %s", install_target)
    except OSError as exc:
        logger.warning("Failed to write to install saved dir: %s", exc)


def _detect_gz_world_name() -> str:
    """Auto-detect the Gazebo world name.

    Strategy:
      1. Parse the world SDF file (worlds/*.sdf) for <world name="...">.
      2. Query ``gz service -l`` for /world/<name>/create endpoints.
      3. Fall back to 'vehicle_arm_world'.
    """
    # 1. Read from world SDF file
    if _WORLDS_DIR.is_dir():
        for sdf_file in _WORLDS_DIR.glob("*.sdf"):
            try:
                tree = ET.parse(sdf_file)
                world_el = tree.find(".//world")
                if world_el is not None:
                    name = world_el.get("name")
                    if name:
                        logger.info("Detected Gazebo world name from SDF: %s", name)
                        return name
            except Exception:
                pass

    # 2. Query running Gazebo
    try:
        result = subprocess.run(
            ["gz", "service", "-l"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                # Look for /world/<name>/create
                if "/world/" in line and "/create" in line:
                    parts = line.strip().split("/")
                    # /world/<name>/create → parts = ['', 'world', '<name>', 'create']
                    if len(parts) >= 4:
                        name = parts[2]
                        logger.info("Detected Gazebo world name from service list: %s", name)
                        return name
    except Exception:
        pass

    logger.warning("Could not detect Gazebo world name, using default 'vehicle_arm_world'")
    return "vehicle_arm_world"


def _fix_material_names(urdf_content: str) -> str:
    """Ensure every <material> in <visual> has a name attribute.

    The URDF parser used by ``gz sdf -p`` silently drops the entire
    ``<visual>`` element when ``<material>`` lacks a ``name`` attribute,
    making links invisible in Gazebo.  The web editor may produce
    materials without names, so we patch them here.
    """
    try:
        root = ET.fromstring(urdf_content)
        counter = 0
        for link in root.findall(".//link"):
            for vis in link.findall("visual"):
                mat = vis.find("material")
                if mat is not None and not mat.get("name"):
                    link_name = link.get("name", "unknown")
                    mat.set("name", f"{link_name}_material_{counter}")
                    counter += 1
        if counter > 0:
            logger.info("Fixed %d material(s) missing 'name' attribute", counter)
            return '<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode")
    except ET.ParseError:
        pass
    return urdf_content

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("urdf_editor_backend")

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class URDFSaveRequest(BaseModel):
    filename: str
    content: str


class URDFSpawnRequest(BaseModel):
    urdf_content: str


class URDFValidateRequest(BaseModel):
    content: str


class URDFAnalyzeRequest(BaseModel):
    urdf_path: str  # Absolute path to the external URDF file


class URDFMergeRequest(BaseModel):
    urdf_path: str        # Absolute path to the external URDF file
    main_urdf_xml: str    # Current main URDF XML (from editor)
    prefix: str = ""      # Prefix for imported link/joint names
    attach_to: str = ""   # Parent link in main URDF to attach to
    offset_xyz: str = "0 0 0"
    offset_rpy: str = "0 0 0"
    rename_map: dict = {}  # Optional explicit rename map { old_name: new_name }


class EnvObjectSpawnRequest(BaseModel):
    mesh_folder: str     # Absolute path to the mesh folder
    mesh_file: str       # The main mesh filename (e.g. "plant.obj")
    name: str            # Model name in Gazebo
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    scale: float = 1.0


# Track spawned environment objects in-memory
_spawned_env_objects: list[dict] = []


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(title="URDF Editor Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Prevent browser caching of static assets during development."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        path = request.url.path
        if path.endswith(('.js', '.css', '.html')):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response


app.add_middleware(NoCacheMiddleware)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_saved_urdf() -> Path | None:
    """Return the most recently modified file in urdf/saved/, or None."""
    if not _SAVED_DIR.is_dir():
        return None
    files = sorted(_SAVED_DIR.glob("*.urdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _is_gazebo_running() -> bool:
    """Check whether a Gazebo (gz sim) process is alive."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "gz sim"],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Routes — root redirect
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/urdf_editor.html")


# ---------------------------------------------------------------------------
# API — URDF load / save
# ---------------------------------------------------------------------------

@app.get("/api/urdf")
async def get_urdf():
    """Return the current URDF content (most recent saved, session, or default)."""
    saved = _latest_saved_urdf()
    if saved is not None:
        target = saved
    elif _SESSION_URDF.is_file():
        target = _SESSION_URDF
    elif _DEFAULT_URDF.is_file():
        target = _DEFAULT_URDF
    else:
        raise HTTPException(status_code=404, detail="No URDF file found")

    content = target.read_text(encoding="utf-8")
    return {
        "filename": target.name,
        "content": content,
        "path": str(target),
    }


@app.post("/api/urdf")
async def save_urdf(req: URDFSaveRequest):
    """Save URDF content to urdf/saved/{filename}."""
    if not req.filename.strip():
        raise HTTPException(status_code=400, detail="Filename must not be empty")

    # Sanitise: prevent directory traversal
    safe_name = Path(req.filename).name
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    _SAVED_DIR.mkdir(parents=True, exist_ok=True)
    dest = _SAVED_DIR / safe_name

    # Fix material names before saving so the URDF stays Gazebo-compatible
    fixed_content = _fix_material_names(req.content)
    dest.write_text(fixed_content, encoding="utf-8")

    # Persist session copy for Gazebo restart
    _persist_session_urdf(fixed_content)

    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    logger.info("Saved URDF: %s (%d bytes)", dest, len(req.content))
    return {"status": "ok", "path": str(dest), "timestamp": ts}


# ---------------------------------------------------------------------------
# API — mesh listing
# ---------------------------------------------------------------------------

@app.get("/api/meshes")
async def list_meshes():
    """List all mesh files in the meshes/ directory."""
    if not _MESHES_DIR.is_dir():
        return {"meshes": []}

    meshes = []
    for f in sorted(_MESHES_DIR.iterdir()):
        if f.is_file():
            meshes.append({
                "name": f.name,
                "path": str(f),
                "size_bytes": f.stat().st_size,
                "extension": f.suffix.lower(),
            })
    return {"meshes": meshes}


@app.post("/api/meshes/upload")
async def upload_mesh(file: UploadFile = File(...)):
    """Upload an STL/DAE/OBJ mesh file to the meshes/ directory."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate extension
    allowed = {".stl", ".dae", ".obj", ".STL", ".DAE", ".OBJ"}
    ext = Path(file.filename).suffix
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: .stl, .dae, .obj",
        )

    # Ensure meshes directory exists
    _MESHES_DIR.mkdir(parents=True, exist_ok=True)

    # Save the file
    dest = _MESHES_DIR / file.filename
    content = await file.read()
    dest.write_bytes(content)

    # Also copy to install tree so Gazebo can find it
    install_meshes = (
        Path(os.environ.get("AMENT_PREFIX_PATH", "").split(":")[0])
        / "share"
        / "vehicle_arm_sim"
        / "meshes"
    ) if os.environ.get("AMENT_PREFIX_PATH") else None

    if install_meshes and install_meshes.is_dir():
        try:
            (install_meshes / file.filename).write_bytes(content)
        except OSError:
            pass  # Best effort

    logger.info("Uploaded mesh: %s (%d bytes)", file.filename, len(content))
    return {
        "status": "ok",
        "filename": file.filename,
        "size_bytes": len(content),
        "package_path": f"package://vehicle_arm_sim/meshes/{file.filename}",
    }


class CopyMeshFolderRequest(BaseModel):
    source_folder: str   # Absolute path to the source mesh folder
    mesh_file: str       # Main mesh filename (e.g. "plant.obj")


@app.post("/api/meshes/copy-folder")
async def copy_mesh_folder(req: CopyMeshFolderRequest):
    """Copy a mesh folder's files (OBJ/STL + MTL + textures) to meshes/."""
    src = Path(req.source_folder)
    if not src.is_dir():
        raise HTTPException(status_code=404, detail=f"Source folder not found: {src}")

    mesh_path = src / req.mesh_file
    if not mesh_path.is_file():
        raise HTTPException(
            status_code=404, detail=f"Mesh file not found: {mesh_path}"
        )

    _MESHES_DIR.mkdir(parents=True, exist_ok=True)

    # Determine which files to copy: mesh, material, and textures
    mesh_exts = {".obj", ".stl", ".dae"}
    mat_exts = {".mtl"}
    tex_exts = {".png", ".jpg", ".jpeg", ".tga", ".bmp"}
    all_exts = mesh_exts | mat_exts | tex_exts

    copied = []
    skipped = []
    for f in sorted(src.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in all_exts:
            continue
        dest = _MESHES_DIR / f.name
        if dest.exists():
            # Check if same content (MD5)
            src_hash = hashlib.md5(f.read_bytes()).hexdigest()
            dst_hash = hashlib.md5(dest.read_bytes()).hexdigest()
            if src_hash == dst_hash:
                skipped.append(f.name)
                continue
            # Different content — rename
            stem = dest.stem
            suffix = dest.suffix
            counter = 2
            while (_MESHES_DIR / f"{stem}_{counter}{suffix}").exists():
                counter += 1
            dest = _MESHES_DIR / f"{stem}_{counter}{suffix}"

        shutil.copy2(str(f), str(dest))
        copied.append({"src": f.name, "dest": dest.name})
        logger.info("Copied mesh file: %s → %s", f.name, dest.name)

    # Also try to copy to install tree
    install_meshes = (
        Path(os.environ.get("AMENT_PREFIX_PATH", "").split(":")[0])
        / "share" / "vehicle_arm_sim" / "meshes"
    ) if os.environ.get("AMENT_PREFIX_PATH") else None

    if install_meshes and install_meshes.is_dir():
        for item in copied:
            try:
                shutil.copy2(
                    str(_MESHES_DIR / item["dest"]),
                    str(install_meshes / item["dest"]),
                )
            except OSError:
                pass

    # Return the package path for the main mesh file
    # Check if it was renamed
    main_dest = req.mesh_file
    for item in copied:
        if item["src"] == req.mesh_file:
            main_dest = item["dest"]
            break

    return {
        "status": "ok",
        "copied": copied,
        "skipped": skipped,
        "mesh_package_path": f"package://vehicle_arm_sim/meshes/{main_dest}",
        "mesh_filename": main_dest,
    }


# ---------------------------------------------------------------------------
# URDF Analyzer / Merger helpers
# ---------------------------------------------------------------------------

def _analyze_urdf_file(urdf_path: Path) -> dict:
    """
    Comprehensive analysis of an external URDF file.
    Returns a dict with links, joints, meshes, tree structure, warnings, etc.
    """
    urdf_dir = urdf_path.parent
    errors = []
    warnings = []

    # Parse XML
    try:
        tree = ET.parse(str(urdf_path))
        root = tree.getroot()
    except ET.ParseError as exc:
        return {"status": "error", "errors": [f"XML parse error: {exc}"]}
    except FileNotFoundError:
        return {"status": "error", "errors": [f"File not found: {urdf_path}"]}

    if root.tag != "robot":
        return {"status": "error", "errors": [f"Root element is <{root.tag}>, expected <robot>"]}

    robot_name = root.get("name", "unnamed")

    # Extract all links
    links_info = []
    link_names = []
    for link_el in root.findall("link"):
        name = link_el.get("name", "")
        link_names.append(name)
        info = {
            "name": name,
            "has_visual": link_el.find("visual") is not None,
            "has_collision": link_el.find("collision") is not None,
            "has_inertial": link_el.find("inertial") is not None,
            "meshes": [],
        }
        # Gather all mesh references (visual + collision)
        for mesh_el in link_el.findall(".//mesh"):
            fname = mesh_el.get("filename", "")
            scale = mesh_el.get("scale", "1 1 1")
            # Resolve the mesh file path relative to URDF dir
            if fname.startswith("package://"):
                # Extract just the filename
                base_name = Path(fname.split("/")[-1]).name
                resolved = urdf_dir / "meshes" / base_name
                if not resolved.exists():
                    # Try relative to URDF dir directly
                    resolved = urdf_dir / fname.replace("package://", "").split("/", 1)[-1]
            elif fname.startswith("/"):
                resolved = Path(fname)
            else:
                resolved = urdf_dir / fname

            info["meshes"].append({
                "original_path": fname,
                "resolved_path": str(resolved),
                "filename": Path(fname).name,
                "exists": resolved.exists(),
                "size_bytes": resolved.stat().st_size if resolved.exists() else 0,
                "scale": scale,
            })
        links_info.append(info)

    # Detect duplicate link names
    name_counts = Counter(link_names)
    duplicates = {n: c for n, c in name_counts.items() if c > 1}
    if duplicates:
        for n, c in duplicates.items():
            warnings.append(f"Duplicate link name '{n}' appears {c} times — will be auto-renamed")

    # Extract all joints
    joints_info = []
    joint_names = []
    for joint_el in root.findall("joint"):
        jname = joint_el.get("name", "")
        jtype = joint_el.get("type", "fixed")
        parent_el = joint_el.find("parent")
        child_el = joint_el.find("child")
        origin_el = joint_el.find("origin")
        joint_names.append(jname)

        joints_info.append({
            "name": jname,
            "type": jtype,
            "parent": parent_el.get("link", "") if parent_el is not None else "",
            "child": child_el.get("link", "") if child_el is not None else "",
            "xyz": origin_el.get("xyz", "0 0 0") if origin_el is not None else "0 0 0",
            "rpy": origin_el.get("rpy", "0 0 0") if origin_el is not None else "0 0 0",
        })

    # Build tree structure — find root
    child_links = {j["child"] for j in joints_info}
    # Root is a link that is never a child (or the first link if all are children - cycle)
    root_candidates = [n for n in link_names if n not in child_links]
    root_link = root_candidates[0] if root_candidates else (link_names[0] if link_names else "")

    # Build parent→children map
    parent_map = {}
    for j in joints_info:
        parent_map.setdefault(j["parent"], []).append({
            "joint": j["name"],
            "child": j["child"],
            "type": j["type"],
        })

    # Recursive tree builder with cycle detection
    def build_tree(link_name, depth=0, visited=None):
        if visited is None:
            visited = set()
        node = {"name": link_name, "children": [], "depth": depth}
        if link_name in visited or depth > 50:
            node["cycle"] = True
            warnings.append(f"Cycle detected at link '{link_name}' (duplicate name or circular reference)")
            return node
        visited = visited | {link_name}
        for child_info in parent_map.get(link_name, []):
            child_node = build_tree(child_info["child"], depth + 1, visited)
            child_node["joint"] = child_info["joint"]
            child_node["joint_type"] = child_info["type"]
            node["children"].append(child_node)
        return node

    tree = build_tree(root_link) if root_link else {}

    # All unique mesh files
    all_meshes = []
    seen_files = set()
    for li in links_info:
        for m in li["meshes"]:
            if m["filename"] not in seen_files:
                seen_files.add(m["filename"])
                # Check conflict with main URDF meshes
                conflict = (_MESHES_DIR / m["filename"]).exists()
                all_meshes.append({**m, "conflicts_with_main": conflict})

    # Missing meshes
    missing = [m for m in all_meshes if not m["exists"]]
    if missing:
        for m in missing:
            warnings.append(f"Mesh file not found: {m['original_path']} (expected at {m['resolved_path']})")

    # Suggest prefix from robot name or URDF filename
    stem = urdf_path.stem.replace("-", "_").replace(" ", "_")
    suggested_prefix = stem + "_" if stem else "imported_"

    return {
        "status": "ok",
        "robot_name": robot_name,
        "urdf_path": str(urdf_path),
        "urdf_dir": str(urdf_dir),
        "links": links_info,
        "joints": joints_info,
        "root_link": root_link,
        "tree": tree,
        "meshes": all_meshes,
        "warnings": warnings,
        "errors": errors,
        "duplicate_links": duplicates,
        "suggested_prefix": suggested_prefix,
        "total_links": len(links_info),
        "total_joints": len(joints_info),
        "total_meshes": len(all_meshes),
    }


def _merge_urdf(
    ext_path: Path,
    main_xml: str,
    prefix: str,
    attach_to: str,
    offset_xyz: str,
    offset_rpy: str,
    rename_map: dict | None = None,
) -> dict:
    """
    Merge an external URDF into the main URDF.
    - Copies mesh files to package meshes/ dir
    - Rewrites mesh paths to package://vehicle_arm_sim/meshes/
    - Handles duplicate link/joint names with prefix or rename_map
    - Creates attachment joint if attach_to is specified
    Returns {"status": "ok", "xml": "...", "imported_links": N, ...}
    """
    ext_dir = ext_path.parent

    # Parse external URDF
    try:
        ext_tree = ET.parse(str(ext_path))
        ext_root = ext_tree.getroot()
    except (ET.ParseError, FileNotFoundError) as exc:
        return {"status": "error", "errors": [str(exc)]}

    # Parse main URDF
    try:
        main_root = ET.fromstring(main_xml)
    except ET.ParseError as exc:
        return {"status": "error", "errors": [f"Main URDF parse error: {exc}"]}

    # Gather existing names from main URDF
    main_link_names = {l.get("name") for l in main_root.findall("link")}
    main_joint_names = {j.get("name") for j in main_root.findall("joint")}

    # Gather external names
    ext_links = ext_root.findall("link")
    ext_joints = ext_root.findall("joint")

    # Build name mapping: handle duplicates within the external URDF
    # AND conflicts with main URDF
    link_rename = {}
    seen_link_names = set()
    for link_el in ext_links:
        old_name = link_el.get("name", "")
        new_name = old_name

        # Apply explicit rename map first
        if rename_map and old_name in rename_map:
            new_name = rename_map[old_name]
        elif prefix:
            new_name = prefix + old_name

        # Handle internal duplicates (same name appears multiple times in ext URDF)
        if new_name in seen_link_names or new_name in main_link_names:
            counter = 2
            base = new_name
            while (base + f"_{counter}") in seen_link_names or (base + f"_{counter}") in main_link_names:
                counter += 1
            new_name = base + f"_{counter}"

        link_rename[old_name] = link_rename.get(old_name, [])
        link_rename[old_name].append(new_name)
        seen_link_names.add(new_name)

    # For links with duplicate original names, we need a positional approach
    # (first occurrence → rename[0], second → rename[1], etc.)
    link_rename_counters = {k: 0 for k in link_rename}

    joint_rename = {}
    for joint_el in ext_joints:
        old_name = joint_el.get("name", "")
        new_name = (prefix + old_name) if prefix else old_name
        if rename_map and old_name in rename_map:
            new_name = rename_map[old_name]
        if new_name in main_joint_names:
            counter = 2
            base = new_name
            while (base + f"_{counter}") in main_joint_names:
                counter += 1
            new_name = base + f"_{counter}"
        joint_rename[old_name] = new_name
        main_joint_names.add(new_name)

    # Copy mesh files and build path mapping.
    # Deduplicate: each unique source file is copied only once.
    mesh_path_map = {}  # old_filename -> new package:// path
    _MESHES_DIR.mkdir(parents=True, exist_ok=True)
    copied_meshes = []
    _resolved_src_map = {}  # resolved_src_path -> dest package path (for dedup)

    for link_el in ext_links:
        for mesh_el in link_el.findall(".//mesh"):
            fname = mesh_el.get("filename", "")
            if not fname or fname in mesh_path_map:
                continue  # Already mapped

            # Resolve source path
            if fname.startswith("package://"):
                base_name = Path(fname).name
                src = ext_dir / "meshes" / base_name
                if not src.exists():
                    rel = fname.replace("package://", "").split("/", 1)[-1]
                    src = ext_dir / rel
            elif fname.startswith("/"):
                src = Path(fname)
            else:
                src = ext_dir / fname

            if not src.exists():
                logger.warning("Mesh file not found, skipping copy: %s", src)
                continue

            resolved_key = str(src.resolve())

            # Check if this exact source was already processed
            if resolved_key in _resolved_src_map:
                mesh_path_map[fname] = _resolved_src_map[resolved_key]
                continue

            # Check if destination already has identical content (same checksum)
            dest_name = src.name
            dest = _MESHES_DIR / dest_name
            need_copy = True

            if dest.exists():
                # Compare content
                src_hash = hashlib.md5(src.read_bytes()).hexdigest()
                dest_hash = hashlib.md5(dest.read_bytes()).hexdigest()
                if src_hash == dest_hash:
                    # Same file already exists, no need to copy or rename
                    need_copy = False
                else:
                    # Different file with same name — rename
                    stem = src.stem
                    suffix = src.suffix
                    counter = 2
                    while (_MESHES_DIR / f"{stem}_{counter}{suffix}").exists():
                        counter += 1
                    dest_name = f"{stem}_{counter}{suffix}"
                    dest = _MESHES_DIR / dest_name

            if need_copy:
                shutil.copy2(str(src), str(dest))
                copied_meshes.append(dest_name)
                logger.info("Copied mesh: %s -> %s", src.name, dest)

                # Also copy to install tree
                install_meshes = (
                    Path(os.environ.get("AMENT_PREFIX_PATH", "").split(":")[0])
                    / "share" / "vehicle_arm_sim" / "meshes"
                ) if os.environ.get("AMENT_PREFIX_PATH") else None
                if install_meshes and install_meshes.is_dir():
                    try:
                        shutil.copy2(str(src), str(install_meshes / dest_name))
                    except OSError:
                        pass

            pkg_path = f"package://vehicle_arm_sim/meshes/{dest_name}"
            mesh_path_map[fname] = pkg_path
            _resolved_src_map[resolved_key] = pkg_path

    # Now apply changes to external elements and append to main URDF
    imported_links = 0
    imported_joints = 0

    # Track which positional rename to use for duplicate link names
    dup_link_pos = {}

    # We need to process links and joints in order to maintain positional
    # mapping for duplicate link names in joints
    # Build a list of (link_element, new_name) pairs
    link_pairs = []
    for link_el in ext_links:
        old_name = link_el.get("name", "")
        pos = dup_link_pos.get(old_name, 0)
        dup_link_pos[old_name] = pos + 1
        new_name = link_rename[old_name][pos] if pos < len(link_rename.get(old_name, [])) else old_name
        link_pairs.append((link_el, old_name, new_name))

    # Build joint reference resolution for duplicate link names.
    # SolidWorks exports URDFs where the same link name appears in both
    # parent and child roles across different joints, creating apparent
    # cycles (e.g. A→B→A→C).  After renaming duplicates (A, A_2), we
    # must assign each joint reference to the correct instance.
    #
    # Algorithm: track which resolved names have been used as parents.
    # When a name appears as child, skip any instance already used as
    # parent (would create a cycle).  When a name appears as parent and
    # was previously resolved as child, reuse that same instance
    # (child in one joint continues as parent downstream).
    used_as_parent = set()        # resolved new_names used as parent
    resolved_child = {}           # old_name -> latest resolved new_name as child

    joint_pairs = []
    for joint_el in ext_joints:
        parent_el = joint_el.find("parent")
        child_el = joint_el.find("child")
        old_parent = parent_el.get("link", "") if parent_el is not None else ""
        old_child = child_el.get("link", "") if child_el is not None else ""

        # --- Resolve parent ---
        p_cands = link_rename.get(old_parent, [old_parent])
        if old_parent in resolved_child:
            # Previously appeared as child → same instance continues as parent
            new_parent = resolved_child[old_parent]
        else:
            new_parent = p_cands[0]
        used_as_parent.add(new_parent)

        # --- Resolve child ---
        c_cands = link_rename.get(old_child, [old_child])
        if len(c_cands) <= 1:
            new_child = c_cands[0] if c_cands else old_child
        else:
            # Multiple instances: pick the first NOT already used as parent
            new_child = None
            for cand in c_cands:
                if cand not in used_as_parent:
                    new_child = cand
                    break
            if new_child is None:
                new_child = c_cands[-1]  # fallback
        resolved_child[old_child] = new_child

        new_jname = joint_rename.get(joint_el.get("name", ""), joint_el.get("name", ""))
        joint_pairs.append((joint_el, new_jname, new_parent, new_child))

    # Append links to main URDF
    for link_el, old_name, new_name in link_pairs:
        link_el.set("name", new_name)
        # Rewrite mesh paths
        for mesh_el in link_el.findall(".//mesh"):
            old_path = mesh_el.get("filename", "")
            if old_path in mesh_path_map:
                mesh_el.set("filename", mesh_path_map[old_path])
        main_root.append(link_el)
        imported_links += 1

    # Append joints to main URDF
    for joint_el, new_jname, new_parent, new_child in joint_pairs:
        joint_el.set("name", new_jname)
        parent_el = joint_el.find("parent")
        child_el = joint_el.find("child")
        if parent_el is not None:
            parent_el.set("link", new_parent)
        if child_el is not None:
            child_el.set("link", new_child)
        main_root.append(joint_el)
        imported_joints += 1

    # Create attachment joint if attach_to is specified
    root_link = None
    if attach_to:
        # Find the root of the imported tree (first link that isn't a child)
        ext_children = set()
        for _, _, _, child_name in joint_pairs:
            ext_children.add(child_name)
        for _, _, new_name in link_pairs:
            if new_name not in ext_children:
                root_link = new_name
                break
        if not root_link and link_pairs:
            root_link = link_pairs[0][2]

        if root_link:
            attach_joint = ET.SubElement(main_root, "joint")
            attach_joint.set("name", f"{attach_to}_to_{root_link}_joint")
            attach_joint.set("type", "fixed")
            origin = ET.SubElement(attach_joint, "origin")
            origin.set("xyz", offset_xyz)
            origin.set("rpy", offset_rpy)
            parent = ET.SubElement(attach_joint, "parent")
            parent.set("link", attach_to)
            child = ET.SubElement(attach_joint, "child")
            child.set("link", root_link)
            imported_joints += 1

    # Serialize back to XML string
    ET.indent(main_root, space="    ")
    result_xml = '<?xml version="1.0"?>\n' + ET.tostring(main_root, encoding="unicode")

    return {
        "status": "ok",
        "xml": result_xml,
        "imported_links": imported_links,
        "imported_joints": imported_joints,
        "copied_meshes": copied_meshes,
        "root_link": root_link,
        "link_rename_map": {old: news for old, news in link_rename.items()},
        "joint_rename_map": joint_rename,
    }


# ---------------------------------------------------------------------------
# API — URDF Analyze & Merge (comprehensive import)
# ---------------------------------------------------------------------------

@app.post("/api/analyze-urdf")
async def analyze_urdf(req: URDFAnalyzeRequest):
    """
    Analyze an external URDF file comprehensively.
    Returns tree structure, mesh inventory, warnings about duplicates,
    and suggestions for merging into the main URDF.
    """
    urdf_path = Path(req.urdf_path)
    if not urdf_path.is_absolute():
        # Try relative to workspace root
        urdf_path = _WORKSPACE_ROOT / req.urdf_path
    if not urdf_path.exists():
        raise HTTPException(status_code=404, detail=f"URDF file not found: {req.urdf_path}")

    result = _analyze_urdf_file(urdf_path)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("errors", ["Unknown error"]))

    # Also include available main URDF links for attach-to dropdown
    main_links = []
    try:
        session_urdf = _SESSION_URDF if _SESSION_URDF.exists() else _DEFAULT_URDF
        main_tree = ET.parse(str(session_urdf))
        main_links = [l.get("name") for l in main_tree.getroot().findall("link")]
    except Exception:
        pass

    result["main_urdf_links"] = main_links
    return result


@app.post("/api/merge-urdf")
async def merge_urdf(req: URDFMergeRequest):
    """
    Merge an external URDF into the main URDF.
    - Copies all mesh files to package meshes/
    - Rewrites mesh paths to package:// format
    - Handles duplicate names with prefix or auto-rename
    - Creates attachment joint to connect imported tree
    Returns the merged URDF XML.
    """
    urdf_path = Path(req.urdf_path)
    if not urdf_path.is_absolute():
        urdf_path = _WORKSPACE_ROOT / req.urdf_path
    if not urdf_path.exists():
        raise HTTPException(status_code=404, detail=f"URDF file not found: {req.urdf_path}")

    result = _merge_urdf(
        ext_path=urdf_path,
        main_xml=req.main_urdf_xml,
        prefix=req.prefix,
        attach_to=req.attach_to,
        offset_xyz=req.offset_xyz,
        offset_rpy=req.offset_rpy,
        rename_map=req.rename_map or None,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("errors", ["Merge failed"]))

    # Persist the merged result as session URDF
    _persist_session_urdf(result["xml"])

    logger.info(
        "Merged URDF from %s: +%d links, +%d joints, %d meshes copied",
        urdf_path.name,
        result["imported_links"],
        result["imported_joints"],
        len(result["copied_meshes"]),
    )
    return result


@app.get("/api/browse-urdf")
async def browse_urdf(directory: str = ""):
    """
    Browse directories for URDF files. Returns folders and .urdf files
    in the given directory (defaults to the package source root).
    """
    if not directory:
        base = _PKG_ROOT
    else:
        base = Path(directory)

    if not base.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

    items = []
    try:
        for entry in sorted(base.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                # Check if dir contains URDF files or mesh files
                has_urdf = any(entry.glob("*.urdf")) or any(entry.glob("**/*.urdf"))
                has_mesh = (
                    any(entry.glob("*.stl")) or any(entry.glob("*.STL"))
                    or any(entry.glob("*.obj")) or any(entry.glob("*.OBJ"))
                    or any(entry.glob("*.dae")) or any(entry.glob("*.DAE"))
                )
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "directory",
                    "has_urdf": has_urdf,
                    "has_mesh": has_mesh,
                })
            elif entry.suffix.lower() in (".urdf", ".xacro"):
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "urdf",
                    "size": entry.stat().st_size,
                })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    return {
        "directory": str(base),
        "parent": str(base.parent) if base != base.parent else None,
        "items": items,
    }


# ---------------------------------------------------------------------------
# API — saved file management
# ---------------------------------------------------------------------------

@app.get("/api/saved")
async def list_saved():
    """List saved URDF files, sorted by modification time descending."""
    if not _SAVED_DIR.is_dir():
        return {"files": []}

    files = []
    for f in _SAVED_DIR.iterdir():
        if f.is_file():
            stat = f.stat()
            mtime = datetime.datetime.fromtimestamp(
                stat.st_mtime, tz=datetime.timezone.utc
            )
            files.append({
                "name": f.name,
                "modified": mtime.isoformat(),
                "size_bytes": stat.st_size,
            })

    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"files": files}


@app.delete("/api/saved/{filename}")
async def delete_saved(filename: str):
    """Delete a saved URDF file."""
    safe_name = Path(filename).name
    target = _SAVED_DIR / safe_name

    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {safe_name}")

    target.unlink()
    logger.info("Deleted saved URDF: %s", target)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# API — Gazebo spawn
# ---------------------------------------------------------------------------

@app.post("/api/spawn")
async def spawn_in_gazebo(req: URDFSpawnRequest):
    """Write URDF to temp file, convert to SDF, and spawn the model in Gazebo."""
    # Fix missing material name attributes before SDF conversion
    urdf_content = _fix_material_names(req.urdf_content)

    # Write the URDF content to the temp location
    try:
        _TMP_URDF_PATH.write_text(urdf_content, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write temp URDF: {exc}")

    # Persist session copy for Gazebo restart
    _persist_session_urdf(urdf_content)

    # Pre-convert URDF → SDF to avoid Gazebo's internal URDF parser issues
    # (duplicate link/joint names when collapsing fixed joints)
    sdf_path = Path("/tmp/vehicle_arm_editor.sdf")
    use_sdf = False
    try:
        result = subprocess.run(
            ["gz", "sdf", "-p", str(_TMP_URDF_PATH)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            sdf_content = result.stdout
            sdf_path.write_text(sdf_content, encoding="utf-8")
            use_sdf = True
            logger.info("Pre-converted URDF → SDF (%d bytes)", len(sdf_content))
        else:
            logger.warning("SDF conversion failed, falling back to raw URDF: %s",
                           result.stderr.strip()[:200])
    except Exception as exc:
        logger.warning("SDF conversion error, falling back to raw URDF: %s", exc)

    # Pre-check: ensure Gazebo is actually running before we attempt spawn
    if not _is_gazebo_running():
        logger.error("Gazebo is not running – cannot spawn model")
        return {
            "status": "error",
            "message": "Gazebo is not running. Start the simulation first.",
        }

    # Auto-detect the Gazebo world name
    world_name = _detect_gz_world_name()
    logger.info("Using Gazebo world: %s", world_name)

    # Remove any existing vehicle_arm model first
    remove_cmd = [
        "gz", "service",
        "-s", f"/world/{world_name}/remove",
        "--reqtype", "gz.msgs.Entity",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "3000",
        "--req", 'name: "vehicle_arm" type: MODEL',
    ]
    try:
        logger.info("Removing existing vehicle_arm model...")
        subprocess.run(remove_cmd, capture_output=True, timeout=10)
    except Exception:
        # It is fine if removal fails (model may not exist yet)
        pass

    # Build the SDF/URDF content to send inline.
    # We use the `sdf` field (inline string) of gz.msgs.EntityFactory instead of
    # `sdf_filename` (file path) because:
    #   - It matches how ros_gz_sim create -string works
    #   - It avoids GZ_SIM_RESOURCE_PATH dependency for model:// URIs
    #
    # For SDF content, replace model:// URIs with absolute file paths so Gazebo
    # can find the meshes regardless of its resource path configuration.
    if use_sdf:
        spawn_content = sdf_path.read_text(encoding="utf-8")
        # Resolve model://vehicle_arm_sim/meshes/X → absolute path
        meshes_abs = str(_MESHES_DIR)
        spawn_content = spawn_content.replace(
            "model://vehicle_arm_sim/meshes/",
            meshes_abs + "/",
        )
        logger.info("Spawning with inline SDF (%d bytes, mesh paths resolved)", len(spawn_content))
    else:
        spawn_content = _TMP_URDF_PATH.read_text(encoding="utf-8")
        # Resolve package://vehicle_arm_sim/meshes/X → absolute path
        meshes_abs = str(_MESHES_DIR)
        spawn_content = spawn_content.replace(
            "package://vehicle_arm_sim/meshes/",
            meshes_abs + "/",
        )
        logger.info("Spawning with inline URDF (%d bytes, mesh paths resolved)", len(spawn_content))

    # Escape the content for protobuf text format: backslashes, quotes, newlines
    escaped = (spawn_content
               .replace("\\", "\\\\")
               .replace('"', '\\"')
               .replace("\n", "\\n"))

    # Spawn the new model with a 90° roll to convert Y-up (CAD) → Z-up (Gazebo)
    spawn_req = (
        f'sdf: "{escaped}" '
        f'name: "vehicle_arm" '
        f'pose: {{ position: {{ x: 0, y: 0, z: 1.0 }} '
        f'orientation: {{ x: 0.7071068, y: 0, z: 0, w: 0.7071068 }} }}'
    )
    spawn_cmd = [
        "gz", "service",
        "-s", f"/world/{world_name}/create",
        "--reqtype", "gz.msgs.EntityFactory",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "5000",
        "--req", spawn_req,
    ]
    try:
        logger.info("Spawning vehicle_arm model in Gazebo...")
        result = subprocess.run(spawn_cmd, capture_output=True, text=True, timeout=15)
        combined = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            logger.error("Spawn failed (rc=%d): %s", result.returncode, err)
            return {"status": "error", "message": f"Spawn command failed: {err}"}
        if "timed out" in combined.lower():
            logger.error("Spawn service call timed out (Gazebo not reachable): %s", combined)
            return {
                "status": "error",
                "message": "Gazebo service call timed out. Is the simulation running?",
            }
    except subprocess.TimeoutExpired:
        logger.error("Spawn command timed out")
        return {"status": "error", "message": "Spawn command timed out (Gazebo may not be running)"}
    except FileNotFoundError:
        logger.error("gz command not found")
        return {"status": "error", "message": "'gz' command not found. Is Gazebo installed?"}

    logger.info("Model spawned successfully (SDF=%s)", use_sdf)
    return {"status": "ok", "message": "Model spawned in Gazebo", "used_sdf": use_sdf}


# ---------------------------------------------------------------------------
# API — health check
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def status():
    """Health check. Reports whether Gazebo is running."""
    return {
        "status": "ok",
        "gazebo_running": _is_gazebo_running(),
    }


# ---------------------------------------------------------------------------
# API — URDF validation
# ---------------------------------------------------------------------------

@app.post("/api/validate")
async def validate_urdf(req: URDFValidateRequest):
    """Validate URDF XML structure and return stats."""
    errors: list[str] = []
    warnings: list[str] = []
    stats = {"links": 0, "joints": 0, "meshes": 0}

    # Parse XML
    try:
        root = ET.fromstring(req.content)
    except ET.ParseError as exc:
        return {
            "valid": False,
            "errors": [f"XML parse error: {exc}"],
            "warnings": [],
            "stats": stats,
        }

    # Must have <robot> root element
    if root.tag != "robot":
        errors.append(f"Root element must be <robot>, found <{root.tag}>")

    # Count elements
    links = root.findall(".//link")
    joints = root.findall(".//joint")
    meshes = root.findall(".//mesh")

    stats["links"] = len(links)
    stats["joints"] = len(joints)
    stats["meshes"] = len(meshes)

    # Must have at least one link
    if len(links) == 0:
        errors.append("URDF must contain at least one <link> element")

    # Warnings for common issues
    if root.tag == "robot" and not root.get("name"):
        warnings.append("Robot element has no 'name' attribute")

    for joint in joints:
        if not joint.get("type"):
            jname = joint.get("name", "(unnamed)")
            warnings.append(f"Joint '{jname}' has no 'type' attribute")

    for mesh in meshes:
        fname = mesh.get("filename", "")
        if fname and not os.path.isabs(fname) and not fname.startswith("package://"):
            warnings.append(f"Mesh filename may not resolve: {fname}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# API — Environment Objects (mesh folder → Gazebo)
# ---------------------------------------------------------------------------

@app.get("/api/browse-mesh-folders")
async def browse_mesh_folders(directory: str = ""):
    """Browse directories for mesh folders containing OBJ/STL/DAE files."""
    if not directory:
        # Default to the Gazebo meshes folder in vehicle_control
        default_meshes = (
            _PKG_ROOT.parent / "vehicle_control" / "simulation" / "gazebo" / "meshes"
        )
        base = default_meshes if default_meshes.is_dir() else _PKG_ROOT
    else:
        base = Path(directory)

    if not base.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

    items = []
    mesh_exts = {".obj", ".stl", ".dae"}
    texture_exts = {".png", ".jpg", ".jpeg", ".tga", ".bmp"}
    try:
        for entry in sorted(base.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                # Check if dir contains mesh files
                meshes_found = [
                    f.name for f in entry.iterdir()
                    if f.is_file() and f.suffix.lower() in mesh_exts
                ]
                textures_found = [
                    f.name for f in entry.iterdir()
                    if f.is_file() and f.suffix.lower() in texture_exts
                ]
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "directory",
                    "meshes": meshes_found,
                    "textures": textures_found,
                    "is_mesh_folder": len(meshes_found) > 0,
                })
            elif entry.is_file() and entry.suffix.lower() in mesh_exts:
                # Loose mesh file in this directory
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "mesh",
                    "size_kb": round(entry.stat().st_size / 1024, 1),
                })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    return {
        "directory": str(base),
        "parent": str(base.parent) if base != base.parent else None,
        "items": items,
    }


@app.post("/api/spawn-env-object")
async def spawn_env_object(req: EnvObjectSpawnRequest):
    """Spawn a mesh as a standalone static model in the Gazebo world."""
    mesh_folder = Path(req.mesh_folder)
    mesh_path = mesh_folder / req.mesh_file

    if not mesh_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Mesh file not found: {mesh_path}",
        )

    if not _is_gazebo_running():
        raise HTTPException(
            status_code=503,
            detail="Gazebo is not running. Start the simulation first.",
        )

    # Sanitize model name (alphanumeric + underscore only)
    safe_name = "".join(
        c if c.isalnum() or c == "_" else "_" for c in req.name
    ).strip("_")
    if not safe_name:
        safe_name = "env_object"

    # Check for duplicate name and auto-increment
    existing = {obj["name"] for obj in _spawned_env_objects}
    final_name = safe_name
    counter = 2
    while final_name in existing:
        final_name = f"{safe_name}_{counter}"
        counter += 1

    # Build SDF with absolute mesh path (Gazebo needs this)
    abs_mesh = str(mesh_path.resolve())
    sdf_content = f"""<?xml version="1.0" ?>
<sdf version="1.9">
  <model name="{final_name}">
    <static>true</static>
    <link name="link">
      <visual name="visual">
        <geometry>
          <mesh>
            <uri>{abs_mesh}</uri>
            <scale>{req.scale} {req.scale} {req.scale}</scale>
          </mesh>
        </geometry>
      </visual>
      <collision name="collision">
        <geometry>
          <mesh>
            <uri>{abs_mesh}</uri>
            <scale>{req.scale} {req.scale} {req.scale}</scale>
          </mesh>
        </geometry>
      </collision>
    </link>
  </model>
</sdf>"""

    # Compute quaternion from RPY for Gazebo spawn
    import math
    cr = math.cos(req.roll / 2)
    sr = math.sin(req.roll / 2)
    cp = math.cos(req.pitch / 2)
    sp = math.sin(req.pitch / 2)
    cy = math.cos(req.yaw / 2)
    sy = math.sin(req.yaw / 2)
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy

    # Escape SDF for protobuf text format
    escaped = (
        sdf_content
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )

    world_name = _detect_gz_world_name()

    spawn_req = (
        f'sdf: "{escaped}" '
        f'name: "{final_name}" '
        f'pose: {{ position: {{ x: {req.x}, y: {req.y}, z: {req.z} }} '
        f'orientation: {{ x: {qx}, y: {qy}, z: {qz}, w: {qw} }} }}'
    )
    spawn_cmd = [
        "gz", "service",
        "-s", f"/world/{world_name}/create",
        "--reqtype", "gz.msgs.EntityFactory",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "5000",
        "--req", spawn_req,
    ]

    try:
        result = subprocess.run(
            spawn_cmd, capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or "Unknown"
            raise HTTPException(status_code=500, detail=f"Spawn failed: {err}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Gazebo spawn timed out")

    # Track it
    obj_info = {
        "name": final_name,
        "mesh_folder": str(mesh_folder),
        "mesh_file": req.mesh_file,
        "x": req.x, "y": req.y, "z": req.z,
        "roll": req.roll, "pitch": req.pitch, "yaw": req.yaw,
        "scale": req.scale,
    }
    _spawned_env_objects.append(obj_info)

    logger.info("Spawned env object '%s' at (%.2f, %.2f, %.2f) scale=%.2f",
                final_name, req.x, req.y, req.z, req.scale)
    return {"status": "ok", "name": final_name, "object": obj_info}


@app.get("/api/env-objects")
async def list_env_objects():
    """List all spawned environment objects."""
    return {"objects": _spawned_env_objects}


@app.delete("/api/env-objects/{name}")
async def remove_env_object(name: str):
    """Remove a spawned environment object from Gazebo."""
    if not _is_gazebo_running():
        raise HTTPException(status_code=503, detail="Gazebo is not running")

    world_name = _detect_gz_world_name()
    remove_cmd = [
        "gz", "service",
        "-s", f"/world/{world_name}/remove",
        "--reqtype", "gz.msgs.Entity",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "3000",
        "--req", f'name: "{name}" type: MODEL',
    ]
    try:
        subprocess.run(remove_cmd, capture_output=True, timeout=10)
    except Exception:
        pass

    # Remove from tracking
    global _spawned_env_objects
    _spawned_env_objects = [o for o in _spawned_env_objects if o["name"] != name]
    logger.info("Removed env object '%s'", name)
    return {"status": "ok", "name": name}


@app.get("/api/serve-external-mesh")
async def serve_external_mesh(folder: str = "", filename: str = ""):
    """Serve a mesh file from an external folder (for preview)."""
    if not folder or not filename:
        raise HTTPException(status_code=400, detail="folder and filename required")
    file_path = Path(folder) / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    # Security: only serve mesh/texture files
    allowed_exts = {".obj", ".mtl", ".stl", ".dae", ".png", ".jpg", ".jpeg", ".tga", ".bmp"}
    if file_path.suffix.lower() not in allowed_exts:
        raise HTTPException(status_code=403, detail="File type not allowed")
    return FileResponse(str(file_path))


# ---------------------------------------------------------------------------
# Static file serving (must be mounted AFTER API routes)
# ---------------------------------------------------------------------------
# Serve mesh files at /meshes/<filename> so Three.js can load STL files
app.mount("/meshes", StaticFiles(directory=str(_MESHES_DIR)), name="meshes")

app.mount("/", StaticFiles(directory=str(_WEB_UI_DIR)), name="web_ui")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="URDF Editor Backend")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("URDF Editor Backend starting")
    logger.info("  Package root : %s", _PKG_ROOT)
    logger.info("  Default URDF : %s", _DEFAULT_URDF)
    logger.info("  Saved dir    : %s", _SAVED_DIR)
    logger.info("  Meshes dir   : %s", _MESHES_DIR)
    logger.info("  Web UI dir   : %s", _WEB_UI_DIR)
    logger.info("  Listening on : http://%s:%d", args.host, args.port)
    logger.info("=" * 60)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
