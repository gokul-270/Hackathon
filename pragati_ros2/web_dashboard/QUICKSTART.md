# Pragati ROS2 Dashboard - Quick Start Guide

## 🚀 Getting Started in 3 Steps

### Step 1: Install Dependencies
```bash
# Install Python packages
pip install fastapi uvicorn websockets psutil

# Ensure ROS2 is sourced  
source /opt/ros/humble/setup.bash  # Replace 'humble' with your ROS2 distro
```

### Step 2: Start the Dashboard
```bash
cd /home/uday/Downloads/pragati_ros2/web_dashboard
python3 run_dashboard.py
```

You should see:
```
🤖 Pragati ROS2 Dashboard Launcher
==================================================
✅ ROS2 humble environment detected
🚀 Starting Pragati ROS2 Dashboard...
📁 Dashboard directory: /home/uday/Downloads/pragati_ros2/web_dashboard
🔧 Backend script: /home/uday/Downloads/pragati_ros2/web_dashboard/backend/dashboard_server.py
🌐 Web interface will be available at: http://localhost:8080
📊 Dashboard will auto-refresh every 2 seconds
------------------------------------------------------------

✅ Dashboard started successfully!
🔗 Open http://localhost:8080 in your web browser
🔄 Dashboard will automatically detect and display ROS2 nodes, topics, and services

Press Ctrl+C to stop the dashboard
```

### Step 3: Open in Browser
Navigate to **http://localhost:8080** in your web browser

## 🎯 What You'll See

### 🤖 Real-time System Monitoring
- **System Overview**: Live counts of active nodes, topics, services
- **Connection Status**: Green/red indicator in top-right corner  
- **Health Status**: Overall system health assessment

### 🦾 Pragati Robot Status
- **Arm Position**: Current joint angles (Joint 2-5)
- **System Status**: Homing, operation mode, cotton detection
- **Interactive Controls**: Home arm, refresh data, emergency stop

### 📡 Live Data Streams
- **Nodes List**: All active ROS2 nodes with status indicators
- **Topics List**: Published topics with subscriber/publisher counts
- **Services List**: Available services with availability status

### 📝 System Logs
- **Live Log Stream**: Real-time system messages
- **Filterable Logs**: INFO, WARN, ERROR levels
- **Log Management**: Clear and refresh controls

## 🔧 Testing the Dashboard

Run the test suite to verify everything works:
```bash
python3 test_dashboard.py
```

Expected output:
```
🤖 Pragati ROS2 Dashboard Test Suite
==================================================

🖥️  Testing Frontend Files
========================================
✅ Frontend index.html exists
✅ Dashboard title - OK
✅ WebSocket code - OK
✅ API calls - OK
✅ Responsive design - OK
✅ Status indicators - OK
```

## 🚨 Troubleshooting

### "ROS2 environment not sourced"
```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0  # If using multi-robot setup
```

### "Missing required packages" 
```bash
pip install fastapi uvicorn websockets psutil
```

### "Port 8080 already in use"
The dashboard uses port 8080 by default. If blocked:
```bash
# Find process using port 8080
sudo netstat -tlnp | grep :8080

# Kill the process
sudo kill -9 <PID>

# Or change port in dashboard_server.py (line 527)
```

### No data showing in dashboard
1. **Start some ROS2 nodes first:**
   ```bash
   # Terminal 1: Demo publisher
   ros2 run demo_nodes_py talker

   # Terminal 2: Demo subscriber  
   ros2 run demo_nodes_py listener
   
   # Terminal 3: Start dashboard
   python3 run_dashboard.py
   ```

2. **Check ROS2 is working:**
   ```bash
   ros2 node list
   ros2 topic list
   ```

## 📱 Mobile/Remote Access

The dashboard is responsive and works on mobile devices. For remote access:

1. **Find your robot's IP:**
   ```bash
   ip addr show | grep inet
   ```

2. **Access from any device on the same network:**
   ```
   http://YOUR_ROBOT_IP:8080
   ```

## ⚙️ Advanced Usage

### Start Dashboard as Service
```bash
# Create systemd service (optional)
sudo nano /etc/systemd/system/pragati-dashboard.service
```

### Enable HTTPS (for production)
- Add SSL certificates to the FastAPI server
- Use nginx reverse proxy for HTTPS termination

### Custom Monitoring
- Edit `backend/dashboard_server.py` to add new ROS2 subscribers
- Update `frontend/index.html` to display new data
- Add custom API endpoints for specific functionality

## 🎉 You're Ready!

The dashboard will automatically:
- ✅ Detect when ROS2 nodes start/stop
- ✅ Monitor topic publication rates  
- ✅ Track service availability
- ✅ Display Pragati-specific status
- ✅ Update in real-time via WebSocket

**Happy monitoring! 🤖📊**