# Dashboard Overhaul Plan — 2026-03-08

## Context

After completing `dashboard-multi-arm-fix` and doing a comprehensive audit,
40 issues were found across all tabs. The dashboard has substantial code
(58 backend files, 16 tabs, 13 fully-wired features) but the plumbing is
broken: WebSocket ping/pong missing, message envelope mismatch, field name
mismatches, and no graceful no-ROS2 degradation.

## Decision Record

### Architecture: Dashboard per RPi + Dev PC Fleet Hub

- **Each RPi** (vehicle + up to 6 arms) runs its own dashboard instance (:8090)
- **Dev PC** runs a fleet hub dashboard that proxies to all RPi dashboards
- **Role detection**: Config file in `dashboard.yaml` (`role: dev|vehicle|arm`)
- **RPi discovery**: Config file with IP list and roles (not mDNS)
- **Scale**: 1 vehicle + 2 arms (today) → 1 vehicle + 6 arms (future)

### Strategy: Fix Existing, Then Extend (Option A)

- Backend services are solid — don't rewrite
- Frontend bugs are wiring issues (field mismatches, missing ping/pong)
- Fleet hub is additive capability, not a rewrite
- 3 sequential changes, each independently valuable

### MQTT Scope (Current)

Only 3 message types between vehicle and arms:
1. Arm ready/busy status (arm → vehicle)
2. Pick start command (vehicle → arm)
3. Shutdown signal (vehicle → arms)

No expansion planned for now. Fleet hub uses MQTT for these 3 messages
plus HTTP health checks to each RPi's dashboard for monitoring data.

### Dashboard Users

- **Developers**: During development and testing (primary today)
- **Field operators**: During picking operations (future)
- **Device**: Desktop browser only (for now)

## Three-Change Plan

### Change 1: `dashboard-foundation-fix` (~35 tasks)

Fix the 2 root causes + infrastructure. After this change, the dashboard
connects reliably, shows real data when ROS2 is running, and shows
friendly messages when it's not.

**WebSocket fixes:**
- Server handles `ping` → sends `pong` (C1 — root cause of 5s disconnect cycle)
- Server handles `refresh` → sends full state dump (M3)
- Server-side change detection: skip push if state unchanged (M4)
- Replace swallowed exceptions with proper logging (L5)
- Fix message envelope parsing in frontend (C2 — root cause of all-zeros display)
- Fix data merge: reset on disconnect, clear chart history on reconnect (H8, M7)
- Fix pong timer leak: clear old timeouts before creating new (M1)
- Fix stale closure in `connect()` (M2)

**Header / chrome:**
- Wire connection indicator to actual WebSocket state (C3)
- Wire or remove header buttons: E-STOP, Refresh, Settings (M5)
- Fix disconnect banner z-index overlap with header (L3)

**No-ROS2 graceful degradation:**
- Add `ros2_available` flag to `system_state` (H3)
- Friendly "ROS2 not running" messages across all tabs (M13)
- Performance endpoint returns psutil data even without ROS2 (H2)
- Fix health data structure mismatch (H1)
- Fix `ENHANCED_SERVICES_AVAILABLE` import-time evaluation (L6)

**Tests for all of the above.**

### Change 2: `dashboard-tab-wiring-fix` (~35 tasks)

Fix every broken tab and add 3 missing frontends. After this change,
every tab works correctly.

**Field name mismatches (backend ↔ frontend):**
- Launch Control: frontend reads `state`, backend returns `status` (H5)
- Sync PUT: frontend sends `recent_ips`, backend expects `target_ips` (H6)
- Sync status: frontend reads `data.state`, backend returns `data.running` (H7)
- Capability name: `performance_monitoring` vs `performance_metrics` (M8)

**Missing frontend tabs (backend exists, wire frontend):**
- Safety tab — `safety_api.py` exists, needs `SafetyTab.mjs` (C4)
- File Browser tab — `filesystem_api.py` exists, needs tab (C5)
- Log Viewer tab — `log_aggregator.py` exists, needs tab

**CSS fixes:**
- Add `.section-grid` for Launch Control layout (M12)
- Add missing Multi-Arm CSS classes (~20 classes) (H4)
- Fix Field Analysis `ResultTabBar` class mismatch (M10)
- Add CSS variable fallbacks for chart colors (L2)

**Sidebar / navigation:**
- Add Alerts to sidebar TAB_GROUPS (M11)
- Add Safety `<section>` to `index.html` (C4)
- Fix "Bag Analyser" label to "Bag Manager" (L4)

**Bug fixes:**
- Field Analysis stale closure in `onAnalysisComplete` (C6)
- Multi-Arm WS: return empty state instead of force-close (C7)
- Multi-Arm: graceful no-broker state UX (M9)
- HTTP polling: only poll when WebSocket is disconnected (M6)
- Chart theme memo: add theme to dependency array (L1)

**Tests for all of the above.**

### Change 3: `dashboard-fleet-hub` (~25 tasks)

Dev PC fleet management + role-based tabs + tabletop test with 3 RPis.
After this change, one URL on dev PC manages all RPis.

**Role system:**
- Role config in `dashboard.yaml`: `role: dev|vehicle|arm`
- Tab filtering based on role:
  - **Vehicle**: Overview, Multi-Arm, Launch, Safety, ROS2, Parameters, Bags, Alerts, Settings, Systemd Services
  - **Arm**: Overview, Motor Config, Health, Launch, Safety, ROS2, Parameters, Bags, Alerts, Settings, Systemd Services
  - **Dev**: All tabs including Fleet Hub, Sync/Deploy, + drill-down to RPi dashboards

**Fleet config:**
```yaml
fleet:
  vehicle:
    ip: 192.168.1.10
    name: "vehicle"
  arms:
    - ip: 192.168.1.11
      name: "arm1"
    - ip: 192.168.1.12
      name: "arm2"
    # ... up to 6 arms
```

**Fleet hub services (dev PC):**
- Fleet overview service: HTTP health checks to each RPi dashboard
- MQTT client: connects to vehicle broker for 3-message fleet status
- Fleet overview tab: all RPis at a glance (status, CPU, health)
- Drill-down: click RPi → proxy/link to its dashboard
- Sync all: deploy code to all RPis at once
- Collect logs: pull from all RPis

**Tabletop validation:**
- 3 RPis provisioned with role config
- Vehicle dashboard shows fleet view via MQTT
- Dev PC fleet hub shows all 3 RPis
- MQTT 3-message flow working end-to-end

## Issue Reference

Full audit: `docs/audits/2026-03-08-dashboard-audit.md`

## Open Questions

1. Detection/Camera: should this be a dedicated arm tab or stay scattered?
2. Topic Echo: backend exists (673 lines), worth adding a tab?
3. Web Terminal: not planned, using SSH directly. Revisit later?
4. Auto-discovery (mDNS): not planned, using config file. Revisit at 6 arms?
