# Pragati ROS2 Web Dashboard

A comprehensive web-based monitoring and debugging dashboard for the Pragati cotton picking robot ROS2 system, similar to lazyros.

![Dashboard Preview](preview.png)

## Features

### Core Features

🤖 **Real-time Monitoring**
- Live node status and health monitoring
- Topic publication rates and subscriber counts
- Service availability checking
- System health assessment
- WebSocket-based real-time updates

🦾 **Pragati-Specific Status**
- Robotic arm joint positions (Joint 2-5)
- Homing status and initialization progress
- Cotton detection system status
- Operation mode (waiting/active/error)
- Start switch state monitoring

📊 **System Overview**
- Active node count dashboard
- Topic and service statistics
- Last update timestamps
- Connection status indicators

🔧 **Interactive Controls**
- Arm homing service calls
- Emergency stop functionality
- Parameter refresh controls
- Service debugging tools

📝 **Live Logging**
- Real-time log stream display
- Filterable log levels (INFO/WARN/ERROR)
- Log history management
- ROS2 node log aggregation

### Enhanced Features (NEW! 🎉)

⚡ **Performance Monitoring**
- Per-node CPU and memory tracking
- Topic rate and latency metrics
- Message bandwidth usage
- Control loop timing analysis
- System resource monitoring
- Circular buffers for historical data (fixed memory)

🔍 **Advanced Debugging Tools**
- Live topic echo with message inspection
- Service call testing with history
- Parameter management (get/set/monitor)
- Message filtering and search
- Lazy subscriptions (max 3 concurrent for RPi efficiency)

🏥 **System Health Monitoring** (Coming Soon)
- Motor controller status (temperature, current, errors)
- CAN bus health and statistics
- Safety monitor integration
- Cotton detection pipeline metrics

📈 **Historical Data & Analytics** (Coming Soon)
- SQLite-based data storage
- Performance trend visualization
- Error correlation analysis
- Session recording and playback

🔔 **Alert System** (Coming Soon)
- Configurable threshold monitoring
- WebSocket and webhook notifications
- Alert grouping and deduplication
- Critical event tracking

**Optimized for Raspberry Pi:**
- Memory usage: 150-200 MB (active)
- CPU usage: 10-25% (monitoring 10+ nodes)
- Adaptive sampling rates
- Efficient circular buffers
- Delta updates for minimal bandwidth

## Quick Start

### Prerequisites

Ensure ROS2 is installed and sourced:
```bash
source /opt/ros/humble/setup.bash  # or your ROS2 distro
```

Install Python dependencies:
```bash
pip install fastapi uvicorn websockets psutil
```

### Running the Dashboard

1. **Start the dashboard server:**
   ```bash
   cd /home/uday/Downloads/pragati_ros2
   scripts/launch/web_dashboard.sh
   ```

   _or via ROS 2 launch:_

   ```bash
   ros2 launch web_dashboard.launch.py
   ```

2. **Access the dashboard:**
   Open your web browser and navigate to:
   ```
   http://localhost:8080
   ```

3. **For remote access:**
   The dashboard binds to `0.0.0.0:8080`, so you can access it from other machines on your network using:
   ```
   http://YOUR_ROBOT_IP:8080
   ```

## Architecture

```
web_dashboard/
├── README.md                    # This documentation
├── run_dashboard.py            # Launcher script
├── backend/
│   └── dashboard_server.py     # FastAPI backend server
└── frontend/
    └── index.html              # Web interface (HTML/CSS/JS)
```

### Backend (FastAPI + WebSocket)
- **FastAPI server** serving REST API endpoints
- **WebSocket connection** for real-time data streaming
- **ROS2 integration** using rclpy for live monitoring
- **Background monitoring** of nodes, topics, services
- **Pragati-specific subscribers** for arm status and cotton detection

### Frontend (Responsive Web UI)
- **Modern responsive design** with gradient glassmorphism styling
- **Real-time WebSocket updates** every 1 second
- **Interactive controls** for system management
- **Mobile-friendly** responsive grid layout
- **Status indicators** with color-coded health states

## API Endpoints

### Core REST API
- `GET /api/status` - Complete system status
- `GET /api/nodes` - Node information
- `GET /api/topics` - Topic statistics
- `GET /api/services` - Service availability
- `GET /api/pragati` - Pragati-specific status
- `GET /api/logs` - Recent system logs
- `POST /api/service/{service_name}/call` - Call ROS2 service

### Enhanced Performance API (NEW)
- `GET /api/performance/summary` - System, nodes, and topics summary
- `GET /api/performance/nodes?node_name={name}&duration_sec={duration}` - Per-node CPU/memory history
- `GET /api/performance/topics?topic_name={name}` - Topic rate, latency, size metrics
- `GET /api/performance/system?duration_sec={duration}` - System-wide metrics

### Debug Tools API (NEW)
- `POST /api/debug/topic/echo` - Start topic echo session
- `POST /api/debug/topic/echo/stop` - Stop echo session
- `GET /api/debug/topic/echo/{session_id}` - Get buffered messages
- `GET /api/debug/topic/echo/sessions` - List all sessions
- `POST /api/debug/service/call` - Test service call
- `GET /api/debug/service/history` - Service call history
- `GET /api/debug/parameters?node_name={name}` - Get node parameters
- `POST /api/debug/parameters/set` - Set parameter value

### WebSocket
- `WS /ws` - Real-time status updates (now includes performance data)

## Configuration

### Backend Configuration

The dashboard automatically detects and monitors:
- All active ROS2 nodes
- Published topics with `/joint_states` for arm monitoring
- `/start_switch/state` topic for operation status
- Available services for interactive control

### Enhanced Configuration (NEW)

Configure enhanced features via `config/dashboard.yaml`:

```yaml
monitoring:
  update_rate_hz: 1.0  # WebSocket update frequency
  critical_nodes:      # Always monitored at full rate
    - "/motor_control"
    - "/cotton_detection"
  sampling:
    standard_topics: 0.2  # Sample 20% of standard topics
  buffer_sizes:
    performance_history: 60  # Keep 60 seconds
    message_cache: 100  # Per-topic cache

features:
  performance_monitoring: true
  debug_tools: true
  max_concurrent_echoes: 3  # Limit for RPi

optimization:
  websocket_compression: true
  delta_updates: true  # Send only changes
  aggressive_gc: true  # For memory efficiency
```

Alert thresholds in `config/alerts.yaml`:

```yaml
alerts:
  - name: "High CPU Usage"
    metric: "system_cpu_percent"
    threshold: 80
    duration_sec: 5
    actions: [log, notify]

  - name: "Motor Temperature Critical"
    metric: "motor_temperature"
    threshold: 70
    actions: [log, notify, trigger_safety_stop]
```

### Customization

To add new monitoring capabilities:

1. **Add new subscribers** in `dashboard_server.py`:
   ```python
   self.new_topic_sub = self.create_subscription(
       MessageType, '/your_topic', self.callback, 10)
   ```

2. **Update the frontend** in `index.html` to display new data
3. **Extend the API** with new endpoints as needed
4. **Configure monitoring** in `config/dashboard.yaml`

See `docs/IMPLEMENTATION_STATUS.md` for detailed examples.

## System Requirements

- **Python 3.8+**
- **ROS2 Jazzy** or later
- **Modern web browser** with WebSocket support
- **Network access** to port 8080

## Troubleshooting

### Dashboard won't start
```bash
# Check ROS2 environment
echo $ROS_DISTRO

# Source ROS2 if needed
source /opt/ros/humble/setup.bash

# Check dependencies
pip install fastapi uvicorn websockets psutil
```

### No data displayed
- Ensure ROS2 nodes are running: `ros2 node list`
- Check topic availability: `ros2 topic list`
- Verify network connectivity to dashboard server

### WebSocket connection failed
- Check firewall settings for port 8080
- Ensure no other process is using port 8080
- Try accessing via `localhost:8080` directly

## Development

### Adding New Features

1. **Backend changes** - Edit `backend/dashboard_server.py`
2. **Frontend changes** - Edit `frontend/index.html`
3. **Configuration** - Update `run_dashboard.py`
4. **Enhancement roadmap** - Track tasks in `docs/enhancements/WEB_DASHBOARD_ENHANCEMENT_PLAN.md`

### Testing

Start a test ROS2 environment:
```bash
# Terminal 1: Start demo nodes
ros2 run demo_nodes_py talker

# Terminal 2: Start dashboard
python3 run_dashboard.py

# Terminal 3: Check topics
ros2 topic list
```

## Documentation

### Enhanced Features Documentation

📚 **Quick Links:**
- **[Enhanced Monitoring Plan](docs/ENHANCED_MONITORING_PLAN.md)** - Complete implementation roadmap and architecture
- **[Implementation Status](docs/IMPLEMENTATION_STATUS.md)** - Current features, API reference, and usage examples
- **[Configuration Guide](config/dashboard.yaml)** - Full configuration options
- **[Alert Configuration](config/alerts.yaml)** - Alert thresholds and actions

### Architecture Overview

```
┌───────────────────────────────────┐
web_dashboard/
├── README.md                    # This file
├── config/
│   ├── dashboard.yaml           # Main config (all settings consolidated)
│   └── alerts.yaml              # Alert thresholds
├── backend/
│   ├── dashboard_server.py      # Main FastAPI server
│   ├── enhanced_performance_service.py  # ⚡ Performance monitoring
│   ├── debug_tools_service.py   # 🔍 Debug tools
│   ├── performance_service.py   # Original performance service
│   └── ...                      # Other services
├── frontend/
│   ├── index.html               # Main UI
│   └── ...                      # JS/CSS files
└── docs/
    ├── ENHANCED_MONITORING_PLAN.md
    └── IMPLEMENTATION_STATUS.md
└───────────────────────────────────┘
```

## Contributing

The dashboard is designed to be easily extensible. To add new monitoring capabilities:

1. Add ROS2 subscribers in the `ROS2Monitor` class
2. Update the `system_state` dictionary structure
3. Extend the frontend UI with new display components
4. Add corresponding API endpoints if needed
5. Update `launch/web_dashboard.launch.py` (or the shell wrapper) if new runtime parameters are required
6. **For enhanced features:** Follow patterns in `enhanced_performance_service.py` (circular buffers, lazy loading)
7. **Update configuration:** Add settings to `config/dashboard.yaml`
8. **Document:** Update `docs/IMPLEMENTATION_STATUS.md` with new APIs

### Development Workflow

1. **Make changes** to backend services or frontend
2. **Test locally** with demo ROS2 nodes
3. **Check resource usage** on RPi if possible
4. **Update documentation** as needed
5. **Commit with clear messages**

## Performance Targets (Raspberry Pi 4)

| Metric | Target | Notes |
|--------|--------|-------|
| Startup Time | < 5s | Dashboard ready to serve |
| Memory (Idle) | < 100 MB | No active monitoring |
| Memory (Active) | < 200 MB | 10 nodes, 20 topics |
| CPU (Idle) | < 5% | Background monitoring only |
| CPU (Active) | < 25% | Full monitoring + 3 echoes |
| WebSocket Latency | < 50ms | Update delivery time |

## License

This dashboard is part of the Pragati ROS2 project for educational and research purposes.

---

**Happy monitoring! 🤖📊**

For issues or feature requests, please check:
- Enhanced features: `docs/IMPLEMENTATION_STATUS.md`
- Main Pragati project documentation
