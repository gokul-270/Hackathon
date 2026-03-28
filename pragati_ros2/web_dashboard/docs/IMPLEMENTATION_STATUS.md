# Enhanced Web Dashboard - Implementation Status

**Last Updated:** 2025-01-01
**Status:** Phase 1-5 Backend Complete, Phase 6 Frontend Planned

---

## Quick Reference

### What's Implemented ✅

1. **Performance Monitoring Backend** (`backend/enhanced_performance_service.py`)
   - Per-node CPU/memory tracking with circular buffers
   - Topic rate and latency monitoring
   - System-wide resource monitoring
   - Adaptive sampling rates (1Hz critical, 0.2Hz standard)
   - Fixed memory footprint (no growth)

2. **Debug Tools Service** (`backend/debug_tools_service.py`)
   - Live topic echo with lazy subscriptions (max 3 concurrent)
   - Service testing with call history
   - Parameter get/set/monitor with caching
   - Message inspection and filtering

3. **Configuration System**
   - `config/dashboard.yaml` - Main configuration
   - `config/alerts.yaml` - Alert thresholds and actions
   - All features configurable via YAML

4. **Documentation**
   - `docs/ENHANCED_MONITORING_PLAN.md` - Complete implementation plan
   - `docs/IMPLEMENTATION_STATUS.md` - This file
   - API specifications and examples

5. **Health Monitoring Service** (`backend/health_monitoring_service.py`) ✅
   - Motor status aggregation (temperature, current, errors, position)
   - CAN bus health monitoring (message counts, errors, timeouts)
   - Safety monitor integration (e-stop, violations, watchdog)
   - Cotton detection pipeline tracking (detection rate, latency, camera health)

6. **Historical Data Storage** (`backend/historical_data_service.py`) ✅
   - SQLite database with automatic cleanup (7 day retention)
   - Performance metrics storage with indexing
   - Error log persistence
   - Query API for trends and export

7. **Alert Engine** (`backend/alert_engine.py`) ✅
   - 21 predefined alert rules from YAML config
   - Threshold monitoring with duration requirements
   - Multiple notification channels (WebSocket, webhook, log, safety stop)
   - Alert grouping to prevent spam
   - Cooldown management

### What's Next 🔨

8. **Integration Testing**
   - Full system integration tests
   - Performance benchmarks on RPi
   - Load testing with multiple clients

9. **Frontend UI** (Phase 6)
   - React/Vue components or vanilla JS
   - Sparkline charts with minimal DOM updates
   - Virtual scrolling for lists
   - Responsive design
   - Real-time alert displays

---

## Using the Enhanced Features

### Starting Performance Monitoring

```python
from backend.enhanced_performance_service import initialize_performance_monitoring
import yaml

# Load configuration
with open('config/dashboard.yaml') as f:
    config = yaml.safe_load(f)

# Initialize and start
monitor = initialize_performance_monitoring(config['monitoring'])

# Get performance summary
summary = monitor.get_summary()
print(f"System CPU: {summary['system']['cpu_percent']}%")
print(f"Active nodes: {summary['nodes']['total']}")

# Get specific node performance
node_perf = monitor.get_node_performance('/motor_control', duration_sec=60)
print(f"CPU history: {node_perf['cpu_history']}")
```

### Using Debug Tools

```python
from backend.debug_tools_service import initialize_debug_tools
import rclpy

# Initialize ROS2
rclpy.init()
node = rclpy.create_node('debug_client')

# Initialize debug tools
debug_tools = initialize_debug_tools(node, max_echo_sessions=3)

# Start topic echo
result = debug_tools.start_topic_echo('/joint_states', duration=10)
session_id = result['session']['session_id']

# Get messages
messages = debug_tools.get_echo_messages(session_id, limit=10)
for msg in messages['messages']:
    print(f"[{msg['timestamp']}] {msg['data']}")

# Call a service
call_result = debug_tools.call_service(
    '/home_arm',
    {'timeout_sec': 30.0},
    timeout_sec=5.0
)
print(f"Service call {'succeeded' if call_result['success'] else 'failed'}")

# Get node parameters
params = debug_tools.get_node_parameters('/motor_control')
for name, value in params['parameters'].items():
    print(f"{name}: {value}")
```

### Configuration Examples

**Enable/Disable Features:**
```yaml
# config/dashboard.yaml
features:
  performance_monitoring: true
  debug_tools: true
  health_monitoring: false  # Not yet implemented
  historical_data: false  # Not yet implemented
  alert_system: false  # Not yet implemented
```

**Adjust Performance Settings:**
```yaml
monitoring:
  update_rate_hz: 1.0  # WebSocket update frequency
  critical_nodes:
    - "/motor_control"
    - "/cotton_detection"
  sampling:
    standard_topics: 0.2  # Sample 20% of standard topics
  buffer_sizes:
    performance_history: 60  # Keep 60 seconds of data
```

**Configure Alerts:**
```yaml
# config/alerts.yaml
alerts:
  - name: "High CPU Usage"
    metric: "system_cpu_percent"
    threshold: 80
    duration_sec: 5
    actions:
      - log
      - notify
```

---

## API Endpoints (Current)

### Enhanced Performance Monitoring

```
GET /api/performance/summary
    → Returns: System, nodes, and topics summary with real-time metrics

GET /api/performance/nodes/{node_name}
    → Returns: Per-node CPU/memory history with circular buffer data

GET /api/performance/topics/{topic_name}
    → Returns: Topic rate, latency, size metrics with history

GET /api/performance/system?duration_sec={duration}
    → Returns: System-wide CPU/memory/disk history
```

### Health Monitoring

```
GET /api/health/system
    → Returns: Overall system health with all subsystems status

GET /api/health/motors
    → Returns: All motor health (temperature, current, errors)

GET /api/health/can
    → Returns: CAN bus health (message counts, errors, timeouts)

GET /api/health/safety
    → Returns: Safety system status (e-stop, violations, watchdog)

GET /api/health/detection
    → Returns: Cotton detection health (rate, latency, camera)
```

### Historical Data

```
GET /api/history/metrics?metric_type={type}&node_name={name}&start_time={ts}&end_time={ts}&limit={n}
    → Returns: Historical performance metrics from SQLite database

GET /api/history/errors?severity={level}&node_name={name}&start_time={ts}&end_time={ts}&limit={n}
    → Returns: Historical error logs

GET /api/history/stats
    → Returns: Database statistics (size, record counts, retention)
```

### Alert System

```
GET /api/alerts/active
    → Returns: All currently active alerts

GET /api/alerts/history?limit={n}
    → Returns: Alert history (last N alerts)

GET /api/alerts/stats
    → Returns: Alert statistics (rules, counts, by severity)

POST /api/alerts/{alert_id}/acknowledge
    → Acknowledge an alert (marks as acknowledged)

POST /api/alerts/{alert_id}/clear
    → Clear an alert (removes from active list)
```

### Debug Tools

```
POST /api/debug/topic/echo
    Body: {
        "topic_name": "/joint_states",
        "duration": 10  // optional, seconds
    }
    → Returns: Session info with session_id

POST /api/debug/topic/echo/stop
    Body: { "session_id": "echo_1234567890" }
    → Returns: Final session info

GET /api/debug/topic/echo/{session_id}?limit=50
    → Returns: Buffered messages from session

GET /api/debug/topic/echo/sessions
    → Returns: List of all active/inactive sessions

POST /api/debug/service/call
    Body: {
        "service_name": "/home_arm",
        "request": { "timeout_sec": 30.0 },
        "timeout_sec": 5.0
    }
    → Returns: Call result with response/error

GET /api/debug/service/history?limit=50
    → Returns: Service call history

GET /api/debug/parameters?node_name={name}&use_cache=true
    → Returns: All parameters for node

POST /api/debug/parameters/set
    Body: {
        "node_name": "/motor_control",
        "param_name": "control_frequency",
        "param_value": 100.0,
        "param_type": "float"
    }
    → Returns: Success/error
```

---

## Memory & CPU Footprint

### Expected Resource Usage (RPi 4, 4GB RAM)

**Idle State:**
- Memory: ~50-100 MB
- CPU: <5%

**Active Monitoring (10 nodes, 20 topics):**
- Memory: ~150-200 MB
- CPU: 10-25%

**With 3 Active Debug Sessions:**
- Memory: ~200-250 MB
- CPU: 15-30%

### Memory Breakdown

| Component | Memory | Notes |
|-----------|--------|-------|
| FastAPI Backend | 30-50 MB | Base overhead |
| ROS2 Node | 20-40 MB | rclpy overhead |
| Performance Monitor | 20-30 MB | Circular buffers, process tracking |
| Debug Tools (idle) | 5-10 MB | Minimal when not active |
| Debug Tools (3 echoes) | 30-50 MB | 100 msgs × 3 topics |
| **Total (Active)** | **150-200 MB** | Well within limits |

### Optimization Tips

1. **Reduce buffer sizes** if memory constrained:
   ```yaml
   buffer_sizes:
     performance_history: 30  # 30 seconds instead of 60
     message_cache: 50  # 50 messages instead of 100
   ```

2. **Lower sampling rates** for non-critical nodes:
   ```yaml
   sampling:
     standard_topics: 0.1  # Sample 10% instead of 20%
   ```

3. **Limit concurrent echo sessions**:
   ```yaml
   features:
     max_concurrent_echoes: 2  # Instead of 3
   ```

4. **Enable aggressive garbage collection**:
   ```yaml
   optimization:
     aggressive_gc: true
   ```

---

## Integration with Existing Dashboard

### Adding to `dashboard_server.py`

```python
# Add at top of dashboard_server.py
from backend.enhanced_performance_service import initialize_performance_monitoring
from backend.debug_tools_service import initialize_debug_tools
import yaml

# Load config
with open('web_dashboard/config/dashboard.yaml') as f:
    enhanced_config = yaml.safe_load(f)

# Initialize services (in __init__ or startup)
perf_monitor = initialize_performance_monitoring(enhanced_config['monitoring'])
debug_tools = initialize_debug_tools(ros2_node, max_echo_sessions=3)

# Add new endpoints
@app.get("/api/performance/summary")
async def get_performance_summary():
    return perf_monitor.get_summary()

@app.post("/api/debug/topic/echo")
async def start_topic_echo(request: dict):
    return debug_tools.start_topic_echo(
        request['topic_name'],
        request.get('duration')
    )

# Update WebSocket broadcast to include performance data
async def broadcast_state():
    state = {
        **system_state,  # Existing state
        'performance': perf_monitor.get_summary()
    }
    # ... broadcast to clients
```

---

## Testing

### Unit Tests

```bash
# Test performance monitoring
python3 -m pytest web_dashboard/tests/test_performance_service.py

# Test debug tools
python3 -m pytest web_dashboard/tests/test_debug_tools.py
```

### Manual Testing

```bash
# Start ROS2 environment
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# Start some test nodes
ros2 run demo_nodes_cpp talker &
ros2 run demo_nodes_cpp listener &

# Start dashboard with enhanced features
cd web_dashboard
python3 run_dashboard_enhanced.py

# In another terminal, test API
curl http://localhost:8080/api/performance/summary
curl -X POST http://localhost:8080/api/debug/topic/echo \
  -H "Content-Type: application/json" \
  -d '{"topic_name": "/chatter", "duration": 10}'
```

### Load Testing

```bash
# Monitor resource usage during operation
htop  # In one terminal

# Generate load
ros2 topic pub /test_topic std_msgs/String "data: test" -r 100

# Check dashboard performance
curl http://localhost:8080/api/performance/system
```

---

## Troubleshooting

### High Memory Usage

1. Check buffer sizes: `grep buffer_sizes config/dashboard.yaml`
2. Reduce sample rates for non-critical nodes
3. Stop unused echo sessions: `GET /api/debug/topic/echo/sessions`
4. Clear old sessions: `POST /api/debug/topic/echo/cleanup`

### High CPU Usage

1. Check monitoring update rate: `update_rate_hz` in config
2. Reduce number of monitored nodes
3. Use adaptive sampling more aggressively
4. Check for stuck subscriptions

### Service Call Failures

1. Verify service exists: `ros2 service list`
2. Check service type matches
3. Increase timeout: `timeout_sec` parameter
4. Check node responsiveness

### Topic Echo Not Working

1. Verify topic exists: `ros2 topic list`
2. Check message type can be loaded
3. Verify session limit not reached
4. Check ROS2 node is running

---

## Next Implementation Steps

### Phase 3: Health Monitoring (Week 5-6)

1. Create `backend/health_monitoring_service.py`
2. Implement motor status aggregator
3. Add CAN bus health monitor
4. Integrate safety monitor
5. Add cotton detection tracker

### Phase 4: Historical Data (Week 7-8)

1. Create SQLite schema
2. Implement data aggregation service
3. Add query API for historical data
4. Create trend visualization endpoints
5. Add export functionality

### Phase 5: Alert Engine (Week 9)

1. Create `backend/alert_engine.py`
2. Implement threshold monitoring
3. Add notification channels
4. Create alert management API
5. Add webhook integration

### Phase 6: Frontend UI (Week 10+)

1. Design component architecture
2. Implement sparkline charts
3. Add virtual scrolling for lists
4. Create responsive layouts
5. Add keyboard shortcuts

---

## Contributing

To add new features:

1. Follow existing patterns (circular buffers, lazy loading)
2. Add configuration to `dashboard.yaml`
3. Update API documentation in this file
4. Add unit tests
5. Test on RPi hardware
6. Update `ENHANCED_MONITORING_PLAN.md`

---

## References

- **Main Plan:** `docs/ENHANCED_MONITORING_PLAN.md`
- **Config:** `config/dashboard.yaml`
- **Alerts:** `config/alerts.yaml`
- **Performance Service:** `backend/enhanced_performance_service.py`
- **Debug Tools:** `backend/debug_tools_service.py`

---

**Questions? Check the main plan document or open an issue.**
