# Enhanced Web Dashboard: Monitoring & Debugging Plan

**Date:** 2025-10-30  
**Target:** Raspberry Pi 4+ deployment  
**Optimization Focus:** Low memory footprint, minimal CPU overhead, efficient data structures

---

## Executive Summary

Transform the Pragati web dashboard from basic status monitoring into a comprehensive debugging and operational tool while maintaining performance on resource-constrained Raspberry Pi hardware.

**Key Principles:**
- ⚡ Lightweight: Minimize memory and CPU usage
- 🎯 Focused: Show what operators need when they need it
- 📊 Actionable: Every metric should enable decision-making
- 🔄 Real-time: Critical data updates within 1 second
- 💾 Smart caching: Reduce network and computation overhead

---

## Current State Analysis

### Existing Capabilities
✅ Basic node/topic/service listing  
✅ WebSocket real-time updates  
✅ Simple arm status monitoring  
✅ Log aggregation (basic)  
✅ Service call interface

### Critical Gaps
❌ No performance metrics (CPU, memory, latency)  
❌ Limited debugging tools (can't inspect message contents)  
❌ No historical data or trends  
❌ Missing system health diagnostics  
❌ No alert/notification system  
❌ Can't visualize motor controller state  
❌ No CAN bus health monitoring  
❌ Limited error tracking and correlation

---

## Enhanced Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Web Dashboard (Port 8080)                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Frontend (Optimized HTML/CSS/JS)                            │
│  ├── Real-time Status Dashboard                              │
│  ├── Performance Monitoring View                             │
│  ├── Debug Tools Panel                                       │
│  ├── System Health Overview                                  │
│  ├── Historical Data Viewer                                  │
│  └── Alert Configuration                                     │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Backend (FastAPI + ROS2)                                    │
│  ├── WebSocket Handler (1Hz updates)                         │
│  ├── REST API Endpoints                                      │
│  ├── Performance Monitor Service                             │
│  ├── Debug Tools Service                                     │
│  ├── Health Monitor Service                                  │
│  ├── Data Aggregator (circular buffers)                      │
│  └── Alert Engine (threshold-based)                          │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ROS2 Integration Layer                                      │
│  ├── Node Discovery & Monitoring                             │
│  ├── Topic Inspector (on-demand)                             │
│  ├── Service Client Pool                                     │
│  ├── Parameter Client                                        │
│  └── Diagnostic Subscriber                                   │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Storage (Lightweight)                                       │
│  ├── In-Memory Circular Buffers (metrics)                    │
│  ├── SQLite (error logs, sessions)                           │
│  └── JSON Config Files                                       │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Feature Set Overview

### Phase 1: Performance Monitoring (CRITICAL - Week 1-2)

#### 1.1 System Resource Tracking
**Backend:**
- Per-node CPU usage (via `/proc/<pid>/stat`)
- Per-node memory usage (RSS, shared)
- System-wide CPU/memory overview
- Sampling rate: 1Hz for critical nodes, 0.2Hz for others

**Frontend:**
- Live sparkline charts (last 60 seconds)
- Color-coded alerts (>80% red, >60% yellow)
- Sortable table by resource usage
- Drill-down for per-node history

**RPi Optimization:**
- Cache process info, update only changed values
- Use fixed-size circular buffers (max 60 samples)
- Batch psutil calls to minimize overhead

#### 1.2 Message Performance Metrics
**Backend:**
- Topic publication rates (Hz)
- Message latency (publish → receive)
- Message size tracking
- Subscriber callback duration

**Frontend:**
- Real-time rate graphs
- Latency heatmap
- Bandwidth usage per topic
- Performance alerts (rate drops, latency spikes)

**RPi Optimization:**
- Sample subset of messages (1 in N for high-frequency topics)
- Use header timestamps, avoid deep message inspection
- Aggregate statistics in 1-second windows

#### 1.3 Control Loop Timing
**Backend:**
- Motor control loop frequency
- Loop jitter measurement
- Callback execution time
- Queue depth monitoring

**Frontend:**
- Real-time frequency meter
- Jitter visualization
- Performance degradation alerts

---

### Phase 2: Advanced Debugging Tools (Week 3-4)

#### 2.1 Live Topic Inspector
**Backend:**
- On-demand topic echo (lazy subscription)
- Message field filtering
- Recording buffer (last 100 messages)
- Export to JSON/CSV

**Frontend:**
- Searchable topic list
- JSON tree viewer for messages
- Field-level filtering
- Temporal message browser

**RPi Optimization:**
- Create subscriptions only when viewing
- Limit simultaneous active echoes (max 3)
- Use pagination for message history

#### 2.2 Service Testing Interface
**Backend:**
- Service call builder
- Request/response logging
- Timeout configuration
- Call history tracking

**Frontend:**
- Auto-complete for service names
- Form generator from service types
- Response inspector
- Call history with replay

**RPi Optimization:**
- Lazy-load service type definitions
- Cache service metadata

#### 2.3 Parameter Management
**Backend:**
- Parameter discovery per node
- Get/set parameter values
- Parameter change monitoring
- Bulk parameter updates

**Frontend:**
- Hierarchical parameter tree
- Type-aware editors (int, float, bool, string, array)
- Change history tracking
- Export/import parameter sets

---

### Phase 3: System Health Visualization (Week 5-6)

#### 3.1 Motor Controller Dashboard
**Backend:**
- Per-motor status aggregation
- Temperature monitoring
- Current/voltage tracking
- Error state detection
- Position/velocity tracking

**Frontend:**
- Motor status cards (one per motor)
- Real-time temperature gauges
- Current draw graphs
- Error indicator with history
- Position visualization

**Topics to Monitor:**
```
/motor_control/status
/motor_control/diagnostics
/motor_control/temperatures
/motor_control/errors
```

#### 3.2 CAN Bus Health Monitor
**Backend:**
- CAN message counters
- Error frame detection
- Bus load percentage
- Timeout tracking
- Retransmission monitoring

**Frontend:**
- Bus activity meter
- Error log viewer
- Communication quality metrics
- Device availability matrix

**Topics to Monitor:**
```
/can_bus/statistics
/can_bus/errors
/motor_control/can_diagnostics
```

#### 3.3 Safety Monitor Integration
**Backend:**
- Safety state tracking
- E-stop status
- Limit violations
- Watchdog status
- Recovery state machine

**Frontend:**
- Safety status banner (always visible)
- Violation history
- State transition log
- Recovery action tracker

**Topics to Monitor:**
```
/safety_monitor/status
/safety_monitor/violations
/safety_monitor/state
```

#### 3.4 Cotton Detection Pipeline
**Backend:**
- Detection rate tracking
- Processing latency
- Camera health
- Model performance metrics
- Bounding box statistics

**Frontend:**
- Detection rate graph
- Sample images (optional, memory-aware)
- Processing pipeline visualization
- Performance metrics

**Topics to Monitor:**
```
/cotton_detection/results
/cotton_detection/diagnostics
/oak_d_lite/status
```

---

### Phase 4: Historical Data & Analytics (Week 7-8)

#### 4.1 Lightweight Data Storage
**Backend:**
- SQLite database for persistence
- Rotating log files (max 100MB)
- Automatic cleanup (>7 days)
- Session recording

**Schema:**
```sql
CREATE TABLE error_logs (
    id INTEGER PRIMARY KEY,
    timestamp REAL,
    node TEXT,
    severity TEXT,
    message TEXT,
    context TEXT
);

CREATE TABLE performance_snapshots (
    id INTEGER PRIMARY KEY,
    timestamp REAL,
    metric_type TEXT,
    node TEXT,
    value REAL
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    start_time REAL,
    end_time REAL,
    notes TEXT
);
```

#### 4.2 Trend Visualization
**Frontend:**
- Time-series graphs (last hour/day/week)
- Metric comparison tool
- Anomaly highlighting
- Export to CSV

**RPi Optimization:**
- Query with time-based pagination
- Downsample historical data (avg per minute)
- Limit chart points (max 500)

#### 4.3 Error Correlation
**Backend:**
- Error pattern detection
- Temporal correlation analysis
- Root cause suggestions

**Frontend:**
- Error timeline view
- Related error grouping
- Correlation matrix

---

### Phase 5: Alert & Notification System (Week 9)

#### 5.1 Alert Configuration
**Backend:**
- Threshold-based monitoring
- Rate-of-change detection
- State transition alerts
- Alert history tracking

**Configuration:**
```yaml
alerts:
  - name: "High CPU Usage"
    metric: "node_cpu_percent"
    threshold: 80
    duration: 5  # seconds
    action: log_and_notify
    
  - name: "Motor Temperature Critical"
    metric: "motor_temperature"
    threshold: 70
    duration: 2
    action: emergency_stop
    
  - name: "Detection Rate Drop"
    metric: "cotton_detection_rate"
    threshold: 5  # Hz
    comparison: less_than
    duration: 10
    action: notify
```

#### 5.2 Notification Channels
**Backend:**
- WebSocket notifications (dashboard)
- Webhook support (Discord, Slack)
- Log file alerts
- Optional: Email (SMTP)

**Frontend:**
- Alert badge counter
- Alert history panel
- Snackbar notifications
- Sound alerts (optional)

---

## RPi Optimization Strategies

### Memory Management
1. **Fixed-size circular buffers** for all time-series data
2. **Lazy loading** of historical data
3. **Aggressive garbage collection** in Python backend
4. **Frontend pagination** to limit DOM size
5. **Image compression** for any visual data

### CPU Efficiency
1. **Adaptive sampling rates** (slow down when idle)
2. **Batch operations** to reduce context switching
3. **Debounced updates** (group rapid changes)
4. **Worker thread** for heavy computation
5. **Cache frequently accessed data**

### Network Optimization
1. **WebSocket compression** (permessage-deflate)
2. **Delta updates** (send only changes)
3. **Batch small updates** into single message
4. **Connection pooling** for ROS2 clients
5. **Message pruning** (drop old undelivered messages)

### Storage Efficiency
1. **SQLite with WAL mode** for concurrent access
2. **VACUUM on startup** to reclaim space
3. **Index critical columns** (timestamp, node)
4. **Automatic log rotation** (logrotate integration)
5. **Memory-mapped files** for high-frequency metrics

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2) ✓ START HERE
- [ ] Backend performance monitoring service
- [ ] System resource tracking (psutil integration)
- [ ] Basic performance metrics API
- [ ] Frontend sparkline charts
- [ ] Resource usage dashboard

### Phase 2: Debugging Tools (Week 3-4)
- [ ] Topic inspector backend
- [ ] Service tester backend
- [ ] Parameter management backend
- [ ] Debug tools frontend UI
- [ ] Message viewer component

### Phase 3: Health Monitoring (Week 5-6)
- [ ] Motor status aggregator
- [ ] CAN bus monitor
- [ ] Safety monitor integration
- [ ] Cotton detection tracker
- [ ] Health dashboard frontend

### Phase 4: Data Persistence (Week 7-8)
- [ ] SQLite schema setup
- [ ] Data aggregation service
- [ ] Historical query API
- [ ] Trend visualization frontend
- [ ] Export functionality

### Phase 5: Alerts (Week 9)
- [ ] Alert engine backend
- [ ] Threshold configuration
- [ ] Notification service
- [ ] Alert UI components
- [ ] Webhook integration

### Phase 6: Polish & Optimization (Week 10)
- [ ] Performance profiling
- [ ] Memory leak detection
- [ ] UI responsiveness tuning
- [ ] Documentation update
- [ ] User testing

---

## Testing Strategy

### Unit Tests
- Backend service logic
- Data aggregation functions
- Alert threshold detection
- SQL queries

### Integration Tests
- ROS2 topic subscription
- WebSocket message flow
- API endpoint responses
- Database operations

### Performance Tests
- Memory usage under load
- CPU usage monitoring
- WebSocket throughput
- Database query performance

### Hardware Tests (on RPi)
- Dashboard startup time
- Concurrent user handling
- Long-running stability
- Resource exhaustion scenarios

---

## Configuration Files

### `dashboard_config.yaml`
```yaml
server:
  host: "0.0.0.0"
  port: 8080
  workers: 1  # Single worker for RPi
  
monitoring:
  update_rate_hz: 1.0
  critical_nodes:
    - "/motor_control"
    - "/cotton_detection"
    - "/safety_monitor"
  
  sampling:
    high_frequency_topics: 0.1  # Sample 10% of messages
    standard_topics: 1.0  # Sample all messages
  
  buffer_sizes:
    performance_history: 60  # 1 minute at 1Hz
    error_logs: 1000
    message_cache: 100

performance:
  cpu_threshold: 80  # percent
  memory_threshold: 500  # MB
  latency_threshold: 100  # ms
  
storage:
  database_path: "./data/dashboard.db"
  max_db_size_mb: 100
  retention_days: 7
  
alerts:
  enabled: true
  config_file: "./config/alerts.yaml"
  webhook_url: null  # Optional
  
optimization:
  websocket_compression: true
  delta_updates: true
  lazy_loading: true
```

### `alerts.yaml`
```yaml
alerts:
  - name: "High CPU"
    metric: "node_cpu_percent"
    threshold: 80
    duration_sec: 5
    severity: "warning"
    
  - name: "Critical CPU"
    metric: "node_cpu_percent"
    threshold: 95
    duration_sec: 2
    severity: "critical"
    
  - name: "Motor Overheat"
    metric: "motor_temperature"
    threshold: 65
    duration_sec: 1
    severity: "critical"
    actions:
      - log
      - notify
      - trigger_safety_stop
```

---

## API Documentation

### New Endpoints

#### Performance Monitoring
```
GET /api/performance/nodes
GET /api/performance/topics
GET /api/performance/system
GET /api/performance/history?metric=cpu&node=motor_control&duration=60
```

#### Debug Tools
```
POST /api/debug/topic/echo
    Body: { "topic": "/joint_states", "duration": 10 }
    
POST /api/debug/service/call
    Body: { "service": "/home_arm", "request": {} }
    
GET /api/debug/parameters?node=/motor_control
POST /api/debug/parameters/set
```

#### Health Monitoring
```
GET /api/health/motors
GET /api/health/can_bus
GET /api/health/safety
GET /api/health/detection
```

#### Historical Data
```
GET /api/history/errors?start=<timestamp>&end=<timestamp>
GET /api/history/performance?metric=cpu&interval=1m
GET /api/history/sessions
```

#### Alerts
```
GET /api/alerts/active
GET /api/alerts/history
POST /api/alerts/acknowledge
PUT /api/alerts/config
```

---

## Documentation Updates Needed

1. **README.md** - Add new features section
2. **QUICKSTART.md** - Update with new UI walkthrough
3. **API_REFERENCE.md** - Complete API documentation
4. **TROUBLESHOOTING.md** - Common issues and solutions
5. **OPTIMIZATION_GUIDE.md** - RPi-specific tuning tips
6. **DEPLOYMENT.md** - Production deployment guide

---

## Success Metrics

### Performance (on RPi 4)
- Dashboard startup: < 5 seconds
- WebSocket latency: < 50ms
- Memory usage: < 200MB
- CPU usage (idle): < 5%
- CPU usage (active): < 25%

### Reliability
- Uptime: > 99.9%
- Data loss: < 0.1%
- Alert latency: < 2 seconds
- Recovery time: < 10 seconds

### Usability
- Time to diagnose issue: < 2 minutes
- False positive alerts: < 5%
- User satisfaction: > 4/5

---

## Next Steps

1. ✅ Review and approve this plan
2. 🔨 Implement Phase 1 (performance monitoring)
3. 🧪 Test on RPi hardware
4. 📝 Document new features
5. 🔄 Iterate based on feedback

---

**Questions or concerns? Let's discuss before implementation begins!**
