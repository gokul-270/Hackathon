"""
Static Files — Static file serving and frontend mount.

Extracted from dashboard_server.py as part of the backend restructure.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter(tags=["static"])

_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"


@router.get("/")
async def serve_dashboard():
    """Serve the main dashboard page."""
    dashboard_path = _frontend_dir / "index.html"
    if dashboard_path.exists():
        return FileResponse(dashboard_path)
    return HTMLResponse(
        """
    <html><body>
    <h1>Pragati ROS2 Dashboard</h1>
    <p>Frontend not found. Please check frontend directory.</p>
    <p>API endpoints available at:</p>
    <ul>
        <li><a href="/api/status">/api/status</a></li>
        <li><a href="/api/nodes">/api/nodes</a></li>
        <li><a href="/api/topics">/api/topics</a></li>
        <li><a href="/api/services">/api/services</a></li>
    </ul>
    </body></html>
    """
    )


@router.get("/styles.css")
async def serve_styles():
    """Serve CSS file."""
    css_path = _frontend_dir / "styles.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css")
    raise HTTPException(status_code=404, detail="CSS not found")


@router.get("/dashboard.js")
async def serve_js():
    """Serve JavaScript file."""
    js_path = _frontend_dir / "dashboard.js"
    if js_path.exists():
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="JS not found")


def mount_static_files(app: FastAPI):
    """Mount frontend directory for static assets.

    Must be called LAST, after all API routes are registered.
    """
    try:
        if _frontend_dir.exists():
            app.mount("/", StaticFiles(directory=_frontend_dir), name="static")
    except Exception as e:
        print(f"Could not mount static files: {e}")
