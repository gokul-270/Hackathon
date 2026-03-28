# Dashboard Redesign: Entity-Centric Dev & Field Engineering Tool

**Date:** 2026-03-09
**Status:** ✅ Fully implemented and archived — entity-core (67/67), operations (25/25), ros2-subtabs (56/56), motor-rosbag (38/38). 186/186 tasks complete.

## Problem Statement

The dashboard grew into 20 tabs, 67+ backend files, and 48+ REST endpoints for
a feature the PRD calls "POC only." It was never grounded in actual use cases.
The role-based architecture (dev/vehicle/arm) and per-RPi dashboard deployment
added complexity without solving real problems. Meanwhile the tool that developers
and field engineers actually need — a single control surface for understanding
and operating the entire robot fleet — does not exist in a usable form.

## Vision

**One dashboard, running on the dev machine, that lets any developer or field
engineer see the status of every entity (local, vehicle, arms), control them,
debug them, and analyze their sessions.**

The dashboard is NOT a production operator interface (that's physical buttons
and LEDs per the PRD). It IS the primary tool for:
- Development and bench testing
- Field trial debugging
- Post-session analysis
- Fleet operations (deploy, provision, collect logs)
- Motor setup and calibration

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Dashboard (dev machine only, localhost:8090)               │
│  FastAPI + Preact/HTM (reshape existing code)              │
│                                                             │
│  ┌───────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  Local     │  │  Vehicle    │  │   Arm 1     │  ...x6  │
│  │  (rclpy)   │  │  (HTTP)     │  │  (HTTP)     │          │
│  └───────────┘  └─────────────┘  └─────────────┘          │
│   direct ROS2     agent:8091       agent:8091               │
│   access          on vehicle RPi   on arm RPi               │
└────────────────────────────────────────────────────────────┘
```

### Local Entity
- Uses native `rclpy` for ROS2 introspection (nodes, topics, services, parameters)
- Uses `psutil` for system health (CPU, memory, temp, disk)
- Behaves identically to remote entities — same UI, same data model
- Use case: run ROS2 nodes locally, debug them in dashboard just like LazyROS

### Remote Entities (RPis)
- Each RPi runs a **lightweight REST agent** (~100-150 lines of Python)
- Agent exposes standardized JSON endpoints (see Agent API below)
- Dashboard polls agents via HTTP for status, streams logs via SSE
- No full dashboard backend on RPis — just the agent
- `sync.sh` operations run as subprocesses on dev machine (SSH to RPis internally)

### RPi Agent API (port 8091)

Tiny FastAPI app installed via `sync.sh --provision`. Endpoints:

```
GET  /health                  - CPU, memory, temp, disk, uptime
GET  /ros2/nodes              - node list + lifecycle states
GET  /ros2/topics             - topic list + types + pub/sub counts
GET  /ros2/services           - service list + types
GET  /ros2/parameters         - parameters from all nodes
GET  /ros2/topic/echo/{name}  - SSE stream of messages on a topic
POST /ros2/service/call       - call a ROS2 service with JSON input
POST /ros2/parameter/set      - set a parameter value
GET  /systemd/status          - pragati service statuses
POST /systemd/restart/{name}  - restart a systemd service
GET  /logs/list               - available log files
GET  /logs/tail/{path}        - last N lines of a log file (SSE for live tail)
GET  /mqtt/status             - MQTT broker connectivity (vehicle only)
```

Agent is started by systemd (`pragati-agent.service`), replaces `pragati-dashboard.service`.

### Entity Data Model

Every entity (local or remote) is represented uniformly:

```python
@dataclass
class Entity:
    name: str           # "local", "vehicle", "arm1", "arm2", ...
    role: str           # "local", "vehicle", "arm"
    ip: str             # "127.0.0.1" for local, RPi IP for remote
    agent_port: int     # 8091 for remote, N/A for local
    online: bool        # reachable?
    health: SystemHealth  # cpu, mem, temp, disk
    ros2: ROS2State     # nodes, topics, services, parameters
    services: list      # systemd service statuses
    last_seen: datetime
    last_error: str | None
```

### Configuration

Entities are configured in `config.env` (already exists, used by `sync.sh`):

```bash
VEHICLE_IP=192.168.1.10
ARM_1_IP=192.168.1.11
ARM_2_IP=192.168.1.12
# ARM_3_IP through ARM_6_IP when scaling
```

Dashboard reads this file at startup. No separate `dashboard.yaml` fleet config
needed — single source of truth.

## Features

### 1. Fleet Overview (Home Page)

Entity cards showing all configured entities at a glance.

**Per-entity card shows:**
- Name and role (vehicle, arm1, arm2, ...)
- Online/offline status (green/red dot)
- CPU, memory, temperature gauges
- ROS2 node count and health summary
- Last error (if any)
- Click to drill down

**Actions from overview:**
- Refresh all entities
- Quick-action buttons: Sync All, Collect All Logs, Shutdown All, E-Stop All

### 2. Entity Detail (Drill-Down View)

When you click an entity card, you see a tabbed detail view:

#### 2a. Status / Health
- System metrics: CPU, memory, temp, disk (gauges + history chart)
- ROS2 node list with lifecycle states (active, inactive, finalized)
- Systemd service statuses (launch service, field-monitor, CAN watchdog, etc.)
- Start/stop/restart individual services
- Overall health indicator (healthy/degraded/critical)

#### 2b. Topics
- Full topic list with message types, publisher count, subscriber count
- Estimated publish rate
- Click any topic to echo its messages live
- For local entity: uses rclpy subscriber
- For remote entity: uses agent SSE `/ros2/topic/echo/{name}`

#### 2c. Services
- Service list with types
- Call any service: enter JSON input, see JSON response
- History of recent service calls and results

#### 2d. Parameters
- Parameters from all running nodes, grouped by node
- Search/filter across all parameters
- Edit any parameter inline (with confirmation)
- For local: rclpy parameter API
- For remote: agent `/ros2/parameter/set`

#### 2e. Nodes
- Node detail panel: publishers, subscribers, services per node
- Lifecycle state and transitions (configure, activate, deactivate, shutdown)
- Restart node capability

#### 2f. Logs
- Live log tail from entity (auto-scroll, severity filtering, search)
- For local: read local log files + `/rosout` subscription
- For remote: agent `/logs/tail/{path}` SSE stream
- Log file browser: pick which log file to view

#### 2g. Motor Config (arm entities only, bench/setup use)
- PID gain tuning with safety-limited sliders
- Motor commands (torque, speed, angle modes)
- Encoder calibration and zero-setting
- Motor limits configuration
- Step response testing
- Live motor state display
- Reuses existing `motor_api.py` and `pid_tuning_api.py` logic

#### 2h. Rosbag
- Start/stop bag recording on entity
- List existing bag files with size, duration, topic count
- Download bags from remote entity
- Playback controls (if rosbag2 supports it on entity)
- For remote: agent endpoint for bag operations

### 3. Live Pipeline View

Real-time visualization of the picking pipeline for all active arms:

```
┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────┐    ┌───────┐
│ Detection │ -> │ Transform │ -> │  Motion  │ -> │ Pick │ -> │ Eject │
│  OAK-D   │    │  IK solve │    │ Traj.    │    │      │    │       │
│  ░░░░░░  │    │  ░░░░░░░  │    │  ░░░░░░  │    │ ░░░░ │    │       │
└──────────┘    └───────────┘    └──────────┘    └──────┘    └───────┘
  arm1: detecting cotton at (0.3, 0.1, 0.2)     arm2: picking
```

**Data sources:**
- ROS2 topics: `/cotton_detection/status`, `/yanthra_move/state`, joint_states
- MQTT: arm ready/busy, pick start, shutdown signals
- Pipeline state derived from node states and topic messages

**Shows per-arm:**
- Current pipeline stage (highlighted)
- Detection coordinates, confidence
- Motion target, current joint positions
- Pick attempt result (success/fail)
- Cycle time
- Error states with details

**MQTT overlay:**
- Vehicle → arm commands shown as arrows
- Arm → vehicle status shown as arrows
- Timestamps and latency on each message

### 4. Controls (Operator Actions)

Actions that can be triggered from the dashboard for any entity:

**Vehicle controls:**
- Move vehicle (start/stop drive motors)
- Start pick cycle (sends MQTT start to arms)
- Stop all arms (MQTT shutdown signal)
- E-stop vehicle

**Per-arm controls:**
- Start/stop arm
- E-stop arm
- Homing (return to home position)
- Reset errors

**System-wide:**
- E-stop ALL (vehicle + all arms)
- Shutdown ALL
- Start ALL (sequential power-up)

**Safety:**
- Confirmation dialog for all destructive actions
- E-stop button always visible in header (existing feature)
- Controls disabled when entity is offline

**Implementation:**
- Vehicle controls: MQTT publish via vehicle's MQTT broker
- Arm controls: ROS2 service calls via agent
- E-stop: direct GPIO command via agent + MQTT broadcast

### 5. Operations (sync.sh GUI)

Full GUI wrapper around `sync.sh`. Runs as subprocess on dev machine.

**Target selection:**
- Dropdown: select one entity, multiple, or "all"
- Entity IPs auto-populated from `config.env`

**Operations (each maps to a sync.sh flag):**

| Operation | sync.sh flag | Description |
|-----------|-------------|-------------|
| Deploy (cross-compiled) | `--deploy-cross` | Push ARM64 binaries from `install_rpi/` |
| Deploy (local) | `--deploy-local` | Push x86 binaries from `install/` |
| Build on RPi | `--build` | Sync source + trigger native build |
| Quick sync | `--quick` | Scripts only, additive |
| Provision | `--provision` | OS fixes, systemd services, CAN config |
| Set role | `--provision --role <r>` | Configure vehicle/arm role |
| Set arm identity | `--provision --arm-id <id>` | Set ARM_ID, MQTT addr, ROS_DOMAIN_ID |
| Set MQTT address | `--mqtt-address <addr>` | Override MQTT broker IP |
| Collect logs | `--collect-logs` | Pull logs from all entities |
| Verify | `--verify` | Health check on entity |
| Restart services | `--restart` | Restart pragati services |
| Test MQTT | `--test-mqtt` | Pub/sub connectivity test |

**Output:**
- Live terminal-like panel showing sync.sh stdout/stderr
- Color-coded output (green success, red errors, yellow warnings)
- Progress indication for multi-target operations

### 6. Log Analysis (Post-Session)

Two entry points:
1. **Collect from RPi** — triggers `sync.sh --collect-logs`, then analyzes
2. **Open local folder** — point at `collected_logs/` or any log directory

#### 6a. Session Timeline
Ordered event stream across all entities:

```
T+0.0s   [vehicle]  System startup
T+1.2s   [arm1]     Node cotton_detection_node: ACTIVE
T+1.3s   [arm2]     Node cotton_detection_node: ACTIVE
T+2.5s   [vehicle]  MQTT: pick_start → arm1
T+3.1s   [arm1]     Detection: cotton at (0.31, 0.12, 0.22) conf=0.87
T+3.8s   [arm1]     Motion: IK solved, moving to target
T+5.2s   [arm1]     Pick: SUCCESS (cycle time: 2.7s)
T+5.3s   [arm1]     MQTT: arm_ready → vehicle
T+6.0s   [arm1]     Detection: cotton at (0.28, 0.15, 0.20) conf=0.72
T+6.1s   [arm2]     ERROR: motor_control_node — CAN timeout on joint 3
```

- Filter by entity, severity, event type
- Click any event to see full log context
- Zoom in/out on timeline

#### 6b. Session Statistics
- Total picks: N, success rate: X%
- Average cycle time, min, max, P95
- Detections: total, filtered (low confidence, bad coordinates), valid
- Errors: count by type, by entity
- Motor health: max temperatures, current draw peaks
- Vehicle: distance traveled, stops, steering events

#### 6c. Flow Visualization
Sequence diagram showing the interaction flow:

```
Vehicle          Arm1             Arm2
  │                │                │
  │──pick_start──>│                │
  │                │──detect──>    │
  │                │<──cotton──    │
  │                │──move──>      │
  │                │──pick──>      │
  │                │<──success──   │
  │<──arm_ready───│                │
  │──pick_start──────────────────>│
  │                                │──detect──>
```

### 7. MQTT Monitor

Real-time view of MQTT message flow:

- Subscribe to all 3 pragati MQTT topics
- Show each message: timestamp, topic, sender, payload
- Visual arrows: vehicle ↔ arms
- Latency measurement (if timestamps in payload)
- Message rate indicator
- Filter by topic or entity
- Connection: dev machine connects directly to vehicle's MQTT broker (port 1883)

### 8. Settings

- **Entity config**: IPs, names (edit `config.env` via UI)
- **Agent port**: default 8091
- **Theme**: dark/light
- **Refresh intervals**: polling rates for health, topics, etc.
- **MQTT broker**: vehicle IP and port for MQTT monitor
- **Log paths**: where to find/store collected logs

## What Changes from Current Dashboard

### Backend (reshape, don't rewrite)

| Current | New |
|---------|-----|
| 67+ backend files | ~30 files (remove role system, simplify) |
| Per-RPi dashboard server | Single server on dev machine + lightweight agents |
| Complex WebSocket push for everything | WebSocket for local entity, HTTP polling for remote agents |
| Role-based route filtering | Not needed — one dashboard, one role |
| Fleet health via HTTP to RPi dashboards | HTTP to lightweight RPi agents |
| `dashboard.yaml` fleet config | `config.env` (single source of truth with sync.sh) |

### Frontend (reshape, don't rewrite)

| Current | New |
|---------|-----|
| 20 flat/grouped tabs | 8 views: fleet, entity detail (8 sub-tabs), pipeline, controls, operations, analysis, MQTT, settings |
| Role-based tab filtering | Not needed |
| GroupedSidebar with 6 groups | Simpler nav: fleet overview is home, sidebar lists views |
| Topics/Nodes/Services as top-level tabs | Moved inside entity detail |

### RPi Changes

| Current | New |
|---------|-----|
| Full dashboard backend on each RPi | Lightweight agent (~100-150 lines) |
| `pragati-dashboard.service` | `pragati-agent.service` |
| 48+ REST endpoints per RPi | ~15 agent endpoints |
| WebSocket server on each RPi | No WebSocket — HTTP + SSE only |

### Code Reuse Estimate

| Component | Reuse |
|-----------|-------|
| `ros2_monitor.py` (rclpy introspection) | 90% — used for local entity |
| `health_monitoring_service.py` (psutil) | 95% — used for local entity |
| `motor_api.py` + `pid_tuning_api.py` | 80% — reshuffled into entity detail |
| `analysis_api.py` | 70% — add timeline/flow features |
| Topic/Node/Service/Parameter tabs | 85% — move inside entity detail |
| `OverviewTab.mjs` | 60% — becomes fleet overview |
| `MultiArmTab.mjs` | 40% — concepts feed into pipeline view |
| `sync_api.py` | 70% — reshape into operations view |
| `launch_api.py` | 50% — merge into operations |
| `websocket_handlers.py` | 60% — simplify, local entity only |
| `alert_engine.py` | 30% — simplify to entity-level health indicators |
| `fleet_health_service.py` | 50% — reshape to poll agents instead of dashboards |
| Agent code | 0% — new, but tiny (~150 lines) |
| Pipeline view | 0% — new feature |
| MQTT monitor | 0% — new feature |
| Controls | 20% — some safety_api.py reuse |
| Log analysis timeline/flow | 10% — mostly new |
| Tests | 30% — new structure needs new tests |

### New Code Required

1. **RPi agent** (~150 lines) — new FastAPI app
2. **Entity manager** (~200 lines) — polls agents, manages entity state
3. **Pipeline view** (~400 lines frontend) — new visualization
4. **MQTT monitor** (~200 lines) — new paho-mqtt subscriber + UI
5. **Controls panel** (~300 lines) — MQTT publish + service calls
6. **Log analysis timeline** (~500 lines) — log parsing + timeline UI
7. **Log analysis flow viz** (~300 lines) — sequence diagram rendering
8. **Operations view** (~300 lines) — sync.sh subprocess wrapper + UI
9. **Entity detail shell** (~200 lines) — tabbed container for sub-views

**Estimated new code: ~2,500 lines**
**Estimated reshuffled/adapted code: ~4,000 lines**
**Estimated removed code: ~3,000 lines** (role system, duplicate polling, unused features)

## Implementation Priority

When implementation begins (post field trial or when decided):

### Phase 1: Core Infrastructure
1. RPi agent (write + deploy via provision)
2. Entity manager (poll agents + local rclpy)
3. Fleet overview (home page with entity cards)
4. Entity detail shell with Status/Health tab

### Phase 2: ROS2 Introspection
5. Topics sub-tab (move existing code)
6. Nodes sub-tab (move existing code)
7. Services sub-tab (move existing code)
8. Parameters sub-tab (move existing code)

### Phase 3: Operations
9. Operations view (sync.sh GUI)
10. Logs sub-tab (local + remote)
11. Motor Config sub-tab (move existing code)
12. Rosbag sub-tab (move existing code)

### Phase 4: Live Monitoring
13. MQTT monitor
14. Live pipeline view
15. Controls panel

### Phase 5: Analysis
16. Log analysis: collection integration
17. Log analysis: session timeline
18. Log analysis: session statistics
19. Log analysis: flow visualization

### Phase 6: Polish
20. Settings
21. Tests (pytest + Playwright)
22. Documentation

## Open Questions

1. **Agent authentication**: Should the RPi agent require API key auth on local WiFi?
   Recommendation: Yes, reuse existing auth middleware pattern.

2. **Agent auto-discovery**: Should agents announce themselves via mDNS or stick
   with `config.env` IP list? Recommendation: config.env for now, mDNS at 6 arms.

3. **Topic echo bandwidth**: Streaming high-rate topics (e.g. joint_states at 100Hz)
   from remote RPi via HTTP SSE. May need decimation.
   Recommendation: Agent-side decimation (max 10Hz for SSE streams).

4. **Pipeline view data source**: Need to define exactly which ROS2 topics/services
   carry the pipeline state. This depends on current node implementations.
   Action: audit yanthra_move, cotton_detection, arm_client state topics.

5. **Log analysis parsing**: Log format varies between C++ ROS2 nodes (structured JSON)
   and Python scripts. Need a unified parser.
   Action: audit all log formats before implementing timeline.
