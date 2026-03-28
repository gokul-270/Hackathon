# Dashboard Comprehensive Audit — 2026-03-08

## Context

After completing the `dashboard-multi-arm-fix` change (33 tasks, MQTT lifecycle + star
topology + heartbeat monitoring + frontend), the dashboard was launched for user review.
Multiple systemic issues were found across all tabs — most pre-existing, not from the
multi-arm change. This audit catalogs every issue found via code-level analysis.

## Hardware Test Environment

- 3x Raspberry Pi 4B available (1 vehicle, 2 arms) for tabletop testing
- Dev workstation running dashboard (Ubuntu 24.04, no ROS2 nodes active during audit)

---

## Summary

**40 issues total**: 7 CRITICAL, 8 HIGH, 14 MEDIUM, 5+ LOW

### Root Causes (fix these first, ~60% of symptoms disappear)

1. **Server never sends `pong` reply** — client heartbeat kills connection every 5s,
   causing perpetual reconnect cycle (`websocket_handlers.py:115-133`)
2. **WebSocket message envelope mismatch** — backend wraps in `{meta, data}`, frontend
   merges raw and reads wrong keys — all real-time data silently discarded

---

## CRITICAL Issues (7)

### C1: Server never sends `pong` reply to client `ping`

- **Files**: `backend/websocket_handlers.py:115-133`, `frontend/js/app.js:120-143`
- **Detail**: Server `handle_main_websocket` only handles `visibility` and `estop` message
  types. Client sends `{"type":"ping"}` every 3s, expects `{"type":"pong"}` within 5s.
  No pong → client closes connection → reconnects → cycle repeats every 5s.
- **User symptom**: "keeps getting disconnected/reconnected"

### C2: WebSocket message envelope mismatch

- **Files**: `backend/websocket_handlers.py:166-215`, `frontend/js/app.js:216`,
  `frontend/js/tabs/OverviewTab.mjs:290-305`, `config/dashboard.yaml:28`
- **Detail**: `message_envelope: true` in config. Backend wraps as
  `{"meta":{"msg_type":"performance_update",...},"data":{...}}`. Frontend does
  `setData(prev => ({...prev, ...msg}))` merging `{meta, data}` into state.
  Tabs check for `wsData.performance_update` — key never exists.
- **User symptom**: "CPU usage broken", "nodes/topics are 0", "subsystem health unknown"

### C3: Header connection indicator permanently stuck on "Connecting..."

- **Files**: `frontend/index.html:31-34`
- **Detail**: `#connection-indicator` and `#connection-text` are static HTML. No JS
  anywhere updates them. Preact `DisconnectBanner` is separate. These are dead elements.
- **User symptom**: "next to pragati it says connecting only"

### C4: Safety tab — no frontend component exists

- **Files**: Missing `SafetyTab.mjs`; `backend/safety_api.py` exists (284 lines)
- **Detail**: Sidebar has `{id:"safety", label:"Safety"}`. No `<section id="safety-section">`
  in index.html. No `SafetyTab.mjs` or `registerTab("safety",...)` anywhere. Backend has
  POST `/api/estop`, POST `/api/estop/reset`, GET `/api/safety/status`.
- **User symptom**: "Safety tab nothing"

### C5: Browse tab — no frontend component exists

- **Files**: Missing `BrowseTab.mjs`; `backend/filesystem_api.py` exists
- **Detail**: Backend has fully implemented `/api/filesystem/browse` endpoint registered
  in `service_registry.py`. No frontend tab, no sidebar entry.
- **User symptom**: "Browse option gone"

### C6: Field Analysis stale closure bug

- **Files**: `frontend/js/tabs/FieldAnalysisTab.mjs:1281-1296`
- **Detail**: `onAnalysisComplete` calls `viewAnalysis(jobId)` but `viewAnalysis` is a
  `useCallback` defined later (line 1430). Not in `onAnalysisComplete`'s dependency array.
  Captures stale reference — viewing completed results silently fails.

### C7: Multi-Arm WebSocket force-closes on missing MQTT service

- **Files**: `backend/websocket_handlers.py:302-307`
- **Detail**: When `_mqtt_status` is None (no paho-mqtt), handler sends error then closes
  WebSocket with code 4003. Forces frontend reconnect loop. REST endpoint correctly returns
  empty state; WebSocket should do the same.

---

## HIGH Issues (8)

### H1: Health subsystems always "unknown"

- **Files**: `backend/health_monitoring_service.py`, `frontend/js/tabs/OverviewTab.mjs:536`
- **Detail**: All health subsystems init with `UNKNOWN`, only update from ROS2 topic data.
  Frontend reads `healthData.motors.status` but structure is
  `{motors:{motors:[...], count:N, healthy:N}}` — `.status` doesn't exist.

### H2: Performance summary returns error without ROS2

- **Files**: `backend/api_routes_performance.py:243`, `frontend/js/tabs/OverviewTab.mjs:254`
- **Detail**: `/api/performance/summary` returns `{"error":"Enhanced services not available"}`
  without ROS2. Frontend shows misleading 0% CPU, 0 nodes, 0 topics instead of "unavailable".

### H3: No `ros2_available` flag in data sent to frontend

- **Files**: `backend/ros2_monitor.py:37-54`, `backend/websocket_handlers.py:139-164`
- **Detail**: `system_state` has no `ros2_available` field. Frontend can't distinguish
  "ROS2 not running" from "ROS2 running, nothing discovered yet".

### H4: Many Multi-Arm CSS classes missing from styles.css

- **Files**: `frontend/js/tabs/MultiArmTab.mjs`, `frontend/styles.css`
- **Detail**: ~20 CSS classes referenced but never defined: `fleet-overview-header`,
  `arm-card-header`, `arm-card-body`, `arm-info-row`, `arm-state-active`, etc.

### H5: Launch Control status field mismatch

- **Files**: `frontend/js/tabs/LaunchControlTab.mjs:550-552`, `backend/launch_api.py:588-599`
- **Detail**: Frontend reads `status.state`, backend returns `status.status`. All profiles
  always show "Stopped" regardless of actual state.

### H6: Sync PUT config field mismatch (422 error)

- **Files**: `frontend/js/tabs/SyncTab.mjs:142-146`, `backend/sync_api.py:53-54`
- **Detail**: Frontend sends `{recent_ips:[...]}`, Pydantic model expects `{target_ips:[...]}`.
  Every save gets 422 Unprocessable Entity.

### H7: Sync status polling field mismatch

- **Files**: `frontend/js/tabs/SyncTab.mjs:218-219`, `backend/sync_api.py:195-203`
- **Detail**: Frontend reads `data.state`, backend returns `data.running`. Sync status
  indicator never reflects actual operation progress.

### H8: WebSocket data merge accumulates stale keys forever

- **Files**: `frontend/js/app.js:216`
- **Detail**: `setData(prev => ({...prev, ...msg}))` never resets on disconnect. Stale
  pre-disconnect data persists. Different envelope formats collide in same flat object.

---

## MEDIUM Issues (14)

### M1: Pong timeout timers overlap and leak

- `frontend/js/app.js:125-142` — new setTimeout every 3s, old ones orphaned

### M2: `connect()` stale closure over `disconnected` state

- `frontend/js/app.js:179,190,235` — can cause "false first connect" scenario

### M3: Server ignores `refresh` messages

- `backend/websocket_handlers.py:115-133` — stale data on reconnect

### M4: Full state sent every cycle with no change detection

- `backend/websocket_handlers.py:139-164` — bandwidth waste, unnecessary re-renders

### M5: Header buttons (Refresh, Settings, E-STOP) non-functional

- `frontend/index.html:38-43` — no event handlers attached, purely decorative

### M6: HTTP polling runs alongside WebSocket (double-fetching)

- `frontend/js/tabs/OverviewTab.mjs:324-330` — both data sources active simultaneously

### M7: Chart data not cleared on reconnect

- `frontend/js/tabs/OverviewTab.mjs:228-247` — corruption after reconnections

### M8: Capability name mismatch: `performance_monitoring` vs `performance_metrics`

- `backend/service_registry.py:510`, `config/dashboard.yaml:40`

### M9: Multi-Arm no graceful no-broker state

- `frontend/js/tabs/MultiArmTab.mjs:73-109` — raw "Broker: Disconnected"

### M10: Field Analysis `ResultTabBar` wrong CSS class

- `frontend/js/tabs/FieldAnalysisTab.mjs:361` — uses `analysis-tabs`, CSS defines `fa-result-tabs`

### M11: Alerts tab unreachable from sidebar

- `frontend/js/components/GroupedSidebar.mjs` — no entry for "alerts" in TAB_GROUPS

### M12: `.section-grid` CSS class missing

- `frontend/js/tabs/LaunchControlTab.mjs:824` — no grid layout, icons crammed together

### M13: Empty state messages don't distinguish "no ROS2" from "no data"

- All tabs: Nodes, Topics, Services, Health — generic "No X found" messages

### M14: `analysisApi` throws on all failures instead of returning null

- `frontend/js/tabs/FieldAnalysisTab.mjs:46-57` — fragile error pattern

---

## LOW Issues (5+)

- L1: Chart theme memoized with empty deps — won't update on theme switch
- L2: Chart colors invisible when CSS variables undefined (no fallbacks)
- L3: Disconnect banner overlaps fixed header (z-index: 10000)
- L4: "Bag Analyser" feature doesn't exist (only Bag Manager for record/list/download)
- L5: Silently swallowed exceptions in WS handler (`except Exception: pass`)
- L6: `ENHANCED_SERVICES_AVAILABLE` evaluated at import time, not runtime
- L7: Duplicate HTTP polling alongside WebSocket push across multiple tabs

---

## Cross-Reference: User-Reported Issues → Root Causes

| User Report | Root Cause(s) |
|---|---|
| "keeps getting disconnected/reconnected" | C1 (no pong reply) |
| "next to pragati it says connecting only" | C3 (dead HTML indicator) |
| "CPU usage broken" | C2 (envelope mismatch), H2 (no-ROS2 fallback) |
| "top resource consumers not shown" | C2, H2 (cascading from no data) |
| "subsystem health unknown" | C2 (envelope), H1 (data structure mismatch) |
| "active nodes/topics are 0" | C2, H2, H3 (no ros2_available flag) |
| "WebSocket disconnected" | C1 (5s heartbeat kill cycle) |
| "Multi-Arm: Broker Disconnected, 0/0 Arms" | M9 (no graceful state), C7 (WS force-close) |
| "Field analysis gone" | C6 (stale closure), M10 (wrong CSS), M14 (throws) |
| "Browse option gone" | C5 (no frontend component) |
| "Bag analyser gone" | L4 (feature never existed, only Bag Manager) |
| "Launch control icons close/not clean" | M12 (missing .section-grid CSS), H5 (field mismatch) |
| "Safety tab nothing" | C4 (no frontend component) |
| "Sync options not coming properly" | H6 (PUT 422), H7 (status field mismatch) |
