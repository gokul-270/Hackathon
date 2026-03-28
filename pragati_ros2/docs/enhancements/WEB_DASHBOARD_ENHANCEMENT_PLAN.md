# Web Dashboard Enhancement Plan

**Date:** 2025-10-13  
**Owner:** Systems & Tooling Team  
**Scope:** `web_dashboard/` package (FastAPI backend, front-end UI, launch helpers)

---

## 1. Objectives

1. Align dashboard features with the current ROS 2 stack (cotton detection C++, MG6010 controllers, DepthAI hooks).
2. Improve operability for remote operators without requiring hardware access.
3. Harden code quality (linting, tests) and documentation so the dashboard can become part of the standard deployment story.

---

## 2. Current State Snapshot

- **Backend:** FastAPI + rclpy monitor (`backend/dashboard_server.py`), last touched mid-2024.
- **Frontend:** Single-page HTML in `frontend/index.html` with legacy widgets (Dynamixel & wrapper references still present).
- **Runtimes:** Manual `python3 run_dashboard.py`; no launch file or systemd recipe.
- **Logs:** Several ad-hoc logs in repo (`dashboard_live_test.log`, etc.) from earlier experiments.
- **Docs:** `web_dashboard/README.md` covers basics but lacks feature list vs. roadmap.

---

## 3. Enhancement Backlog

| Priority | Area | Task | Notes |
|----------|------|------|-------|
| High | Data Model | Update monitored topics/services to new MG6010 + cotton detection APIs | Replace legacy Dynamixel fields, include DepthAI diagnostics, integrate `/cotton_detection/results` summary |
| High | Frontend UX | Refresh UI panels to match new data sources and highlight calibration/export status | Add cards for calibration service responses, runtime parameter overrides |
| High | Launching | Provide `ros2 launch` wrapper or `dashboard.launch.py` for easy start | Avoid manual python invocation; include parameter file |
| Medium | Observability | Add structured logging + metrics (uptime, reconnect attempts) | Surface in UI + backend logs |
| Medium | Testing | Create minimal FastAPI unit tests + websocket smoke test (`pytest`) | Hook into CI pipeline once available |
| Medium | Configuration | Externalize ports + polling intervals to YAML | Feed through CLI args/env |
| Low | Packaging | Optional Dockerfile or Debian packaging for kiosk deployment | Defer until after core feature parity |
| Low | Documentation | Expand Quick Start with troubleshooting, screenshot updates, and new feature list | Link from main README + docs inventory |

---

## 4. Immediate Next Steps (No Hardware Required)

1. Audit backend subscriptions and remove any residual Dynamixel / wrapper endpoints.
2. Draft new JSON schema for cotton detection + MG6010 status payloads.
3. Prototype updated UI widgets (static data acceptable) to validate layout.
4. ✅ Launcher entry points ready: shell wrapper at `scripts/launch/web_dashboard.sh` and ROS 2 launch file `launch/web_dashboard.launch.py` (update as parameters evolve).

---

## 5. Dependencies & Risks

- **Dependencies:** `rclpy`, FastAPI packages (ensure requirements tracked); reuse existing cotton detection topics.
- **Risks:** Dashboard currently untested—introducing launch automation requires validation to avoid regressions.
- **Mitigations:** Keep feature toggles to allow safe incremental roll-out; document fallback to manual script if launch file misbehaves.

---

## 6. Acceptance Criteria

- Dashboard visualizes MG6010 motor status, cotton detection heartbeat, and DepthAI diagnostics without referencing legacy packages.
- Launch file or script starts the full stack with a single ROS 2 command.
- Basic automated tests run in CI (import + simple API response) and pass.
- README updated with screenshots and step-by-step instructions aligned with new features.

---

## 7. Tracking

- Tie each enhancement to issues in the Pragati tracker (placeholder IDs pending).
- Review progress during weekly documentation/automation sync.
- Update `docs/DOC_INVENTORY_FOR_AUDIT.md` once new docs/screenshots land, ensuring web dashboard section reflects current status.
