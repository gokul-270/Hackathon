# Enhanced Dashboard - Quick Start Guide

## 🎯 What You Have Now

Your Pragati ROS2 dashboard now has enhanced monitoring capabilities:

✅ **Performance Monitoring** - Tracks system CPU/memory and per-node resources
✅ **Health Monitoring** - Motors, CAN bus, safety, detection pipeline
✅ **Historical Data** - SQLite storage with 7-day retention
✅ **Alert System** - 21 configurable alert rules

## 🚀 Starting the Dashboard

```bash
cd /home/uday/Downloads/pragati_ros2/web_dashboard/backend
python3 dashboard_server.py
```

You should see:
```
🚀 Starting Enhanced Pragati ROS2 Dashboard...
✅ Enhanced performance monitoring started
✅ Health monitoring initialized
✅ Historical data storage ready
✅ Alert engine loaded (21 rules)
🎉 Enhanced monitoring services active!
✅ Dashboard server ready!
📊 WebSocket endpoint: ws://localhost:8080/ws
🔧 API endpoints: http://localhost:8080/api/capabilities
⚡ Enhanced APIs: /api/performance/summary, /api/health/system
```

## 📊 Viewing Performance Data

### Option 1: Browser (JSON)

Open these URLs in your browser:

```
# Performance Summary
http://localhost:8080/api/performance/summary

# System Health
http://localhost:8080/api/health/system

# Alert Status
http://localhost:8080/api/alerts/active

# Historical Data Stats
http://localhost:8080/api/history/stats
```

### Option 2: Command Line

```bash
# Performance Summary (pretty JSON)
curl -s http://localhost:8080/api/performance/summary | jq

# Quick system stats
curl -s http://localhost:8080/api/performance/summary | jq '.system'

# Node CPU usage
curl -s http://localhost:8080/api/performance/summary | jq '.nodes.top_cpu'

# Active alerts
curl -s http://localhost:8080/api/alerts/active | jq '.alerts'
```

### Option 3: Test Script

```bash
cd /home/uday/Downloads/pragati_ros2/web_dashboard
python3 test_api_endpoints.py
```

## 📈 What Data Is Collected

### System Metrics (Updated every 1 second)
- CPU usage percentage
- Memory usage (used/available MB)
- Disk usage
- Network statistics

### Per-Node Metrics (Discovered automatically)
- CPU usage per node
- Memory usage per node
- Process tracking

**Your nodes already detected:**
- `yanthra_move_node` - 9.4% CPU, 34.4 MB RAM
- `cotton_detection_node` - 0.9% CPU, 77.5 MB RAM

### Topic Performance (When topics are active)
- Publication rate (Hz)
- Message latency (ms)
- Message size (bytes)

### Health Monitoring
- Motor status (temperature, current, errors)
- CAN bus health
- Safety system status
- Detection pipeline metrics

## 🔧 Configuration

### Main Settings
Edit `config/dashboard.yaml`:

```yaml
monitoring:
  update_rate_hz: 1.0  # How often to update (1 Hz = once per second)

  critical_nodes:
    - "/yanthra_move_node"
    - "/cotton_detection_node"
```

### Alert Rules
Edit `config/alerts.yaml`:

```yaml
alerts:
  - name: "High CPU Usage"
    metric: "system_cpu_percent"
    threshold: 80
    duration_sec: 5
    severity: warning
    actions:
      - log
      - notify
```

## 🔍 Monitoring Your System

### Check What's Being Tracked

```bash
# See discovered nodes
curl -s http://localhost:8080/api/performance/summary | jq '.nodes'

# See system resources
curl -s http://localhost:8080/api/performance/summary | jq '.system'

# Check database size
curl -s http://localhost:8080/api/history/stats | jq
```

### View Historical Data

```bash
# Last hour of metrics
curl -s "http://localhost:8080/api/history/metrics?limit=100" | jq

# System errors
curl -s "http://localhost:8080/api/history/errors?severity=error" | jq
```

### Monitor Specific Node

```bash
# Get specific node performance
curl -s http://localhost:8080/api/performance/nodes/yanthra_move_node | jq

# Results:
# {
#   "node_name": "/yanthra_move_node",
#   "pid": 12345,
#   "current_cpu": [timestamp, 9.4],
#   "current_memory": [timestamp, 34.4],
#   "cpu_history": [...],
#   "memory_history": [...]
# }
```

## 🎛️ API Endpoints Reference

### Performance
```
GET /api/performance/summary           - Complete performance overview
GET /api/performance/nodes/{name}      - Specific node performance
GET /api/performance/topics/{name}     - Specific topic performance
```

### Health
```
GET /api/health/system                 - Overall system health
GET /api/health/motors                 - Motor status
GET /api/health/can                    - CAN bus health
GET /api/health/safety                 - Safety system
GET /api/health/detection              - Detection pipeline
```

### Historical Data
```
GET /api/history/metrics               - Query metrics
GET /api/history/errors                - Query errors
GET /api/history/stats                 - Database info
```

### Alerts
```
GET /api/alerts/active                 - Active alerts
GET /api/alerts/history                - Alert history
GET /api/alerts/stats                  - Alert statistics
POST /api/alerts/{id}/acknowledge      - Acknowledge alert
POST /api/alerts/{id}/clear            - Clear alert
```

## 🧪 Testing

### Verify Everything Works

```bash
cd /home/uday/Downloads/pragati_ros2/web_dashboard

# Test service integration
python3 test_enhanced_integration.py

# Test performance data collection
python3 test_performance_data.py

# Test API endpoints (requires dashboard running)
python3 test_api_endpoints.py
```

## 🐛 Troubleshooting

### No Performance Data

**Problem:** `/api/performance/summary` shows empty nodes
**Solution:** This is expected if no ROS2 nodes are running. The monitor will automatically detect nodes when they start.

**Test:** Run `python3 test_performance_data.py` - it should show system metrics even without ROS2 nodes.

### High Memory Usage

**Problem:** Dashboard using > 200 MB RAM
**Solutions:**
1. Reduce buffer sizes in `config/dashboard.yaml`
2. Lower `update_rate_hz` to 0.5 (update every 2 seconds)
3. Decrease historical retention: `retention_days: 3`

### Services Not Starting

**Problem:** Dashboard starts but enhanced services fail
**Check:**
```bash
# Verify dependencies
pip3 install psutil pyyaml

# Check YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config/dashboard.yaml'))"

# Check database directory
mkdir -p data && chmod 777 data
```

## 📊 Next Steps

### Deploy to Raspberry Pi

```bash
# From your dev machine
scp -r /home/uday/Downloads/pragati_ros2/web_dashboard pi@raspberrypi.local:~/

# On Raspberry Pi
cd ~/web_dashboard/backend
python3 dashboard_server.py
```

### Build Frontend UI

The backend is ready! Now you can build a frontend to visualize:
- Real-time performance charts
- Node status grid
- Alert notifications
- Historical trends

## 💡 Tips

1. **Monitor during operation**: Start the dashboard before starting your robot nodes to track everything from boot
2. **Check alerts regularly**: Use `/api/alerts/active` to catch issues early
3. **Review history**: Use `/api/history/metrics` to analyze performance trends
4. **Configure thresholds**: Adjust `config/alerts.yaml` based on your system's normal behavior

## 📚 More Documentation

- **Complete Implementation**: `docs/INTEGRATION_COMPLETE.md`
- **API Reference**: `docs/IMPLEMENTATION_STATUS.md`
- **Architecture**: `docs/ENHANCED_MONITORING_PLAN.md`
- **Configuration**: See files in `config/`

---

**🎉 Your enhanced dashboard is ready to use!**

Start the dashboard, open the API endpoints in your browser, and see your system metrics in real-time.
