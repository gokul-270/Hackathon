# Tier 3.1 Complete: Log Rotation & Disk Space Protection

**Date:** October 8, 2025  
**Status:** ✅ COMPLETE  
**Priority:** HIGH (Critical for Raspberry Pi deployment)

---

## Summary

Implemented comprehensive log rotation and disk space monitoring to protect Raspberry Pi from disk-full failures. This is essential for long-running production deployments with limited SD card storage (64GB).

---

## Changes Made

### 1. **Created Common Utilities Package**

**New Package:** `common_utils`
- Location: `src/common_utils/`
- Type: Python (ament_python)
- Purpose: Shared utilities across all Pragati ROS2 nodes

**Package Structure:**
```
src/common_utils/
├── package.xml
├── setup.py
├── resource/
│   └── common_utils
└── common_utils/
    ├── __init__.py
    └── pragati_logging.py  # Main logging utilities
```

### 2. **Implemented PragatiRotatingLogger Class**

**Features:**
- Automatic log rotation at 10MB per file
- Keep only 5 backup files (50MB total per node)
- ROS2 parameter integration for log directory
- Dual logging: ROS2 logger + Python file logger
- Compatible with existing `node.get_logger()` API

**Usage Example:**
```python
from common_utils.pragati_logging import PragatiRotatingLogger

class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        
        # Setup rotating logger
        self.logger = PragatiRotatingLogger(self)
        
        # Use like normal logger
        self.logger.info('Node started')
        self.logger.warn('Warning message')
        self.logger.error('Error message')
```

**Log File Management:**
- Default location: `~/.ros/logs/`
- Configurable via `log_directory` ROS2 parameter
- Files named: `{node_name}.log`, `{node_name}.log.1`, etc.
- Total cap per node: 50 MB (10MB × 5 files)

### 3. **Implemented Disk Space Monitor Node**

**Node:** `disk_space_monitor`
- Package: `common_utils`
- Executable: `disk_space_monitor`

**Features:**
- Monitors root filesystem (`/`) disk usage every 60 seconds
- Publishes free space to `/system/disk_usage` (Float32, in GB)
- Warning threshold: < 2GB free
- Critical threshold: < 1GB free
- Automatic emergency cleanup at critical threshold

**Configurable Parameters:**
```yaml
disk_space_monitor:
  ros__parameters:
    monitor_interval_sec: 60
    warning_threshold_gb: 2.0
    critical_threshold_gb: 1.0
    log_directory: ~/.ros/logs
    image_directory: /home/ubuntu/pragati/outputs
    max_log_age_days: 7
    max_image_age_days: 3
```

### 4. **Emergency Cleanup Mechanism**

When disk space drops below 1GB, automatic cleanup:
1. Delete log files older than 7 days
2. Delete image files older than 3 days
3. Log cleanup results
4. Re-check and report free space

**Cleanup Logic:**
- Searches recursively in configured directories
- Matches patterns: `*.log`, `*.log.*`, `*.jpg`, `*.png`, `*.jpeg`
- Uses file modification time for age determination
- Safe: Only deletes files, not directories
- Logged: All deletions and errors are logged

### 5. **Updated Launch File**

**File:** `src/yanthra_move/launch/pragati_complete.launch.py`

**Added:**
1. **New Parameter:** `log_directory`
   - Default: `~/.ros/logs`
   - Description: "Directory for rotating log files (Tier 3.1)"

2. **New Node:** `disk_space_monitor`
   - Launches with other core nodes
   - Uses `log_directory` parameter
   - Monitors every 60 seconds

**Launch Command:**
```bash
# Use default log directory
ros2 launch yanthra_move pragati_complete.launch.py

# Custom log directory
ros2 launch yanthra_move pragati_complete.launch.py \
  log_directory:=/mnt/external/pragati_logs
```

---

## Build & Verification

### Build Status
```bash
$ colcon build --packages-select common_utils
Summary: 1 package finished [3.23s]
```
✅ **PASS:** Package builds successfully

### Package Verification
```bash
$ ros2 pkg list | grep common_utils
common_utils
```
✅ **PASS:** Package appears in ROS2

### Executable Verification
```bash
$ ros2 pkg executables common_utils
common_utils disk_space_monitor
```
✅ **PASS:** Disk space monitor executable available

---

## Usage Examples

### 1. Standalone Disk Space Monitor
```bash
# Run disk monitor standalone
ros2 run common_utils disk_space_monitor

# Monitor disk usage topic
ros2 topic echo /system/disk_usage
```

### 2. In Launch File (Already Integrated)
The disk space monitor is automatically launched with `pragati_complete.launch.py`

### 3. Using Rotating Logger in Python Nodes

**Before (Basic ROS2 logging - no rotation):**
```python
class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        self.get_logger().info('Message')  # Only to console/ROS log
```

**After (With rotation):**
```python
from common_utils.pragati_logging import PragatiRotatingLogger

class MyNode(Node):
    def __init__(self):
        super().__init__('my_node')
        self.logger = PragatiRotatingLogger(self)
        self.logger.info('Message')  # To console, ROS log, AND rotating file
```

---

## Resource Limits

### Per-Node Log Limits
| Component | Max Size | Rotation | Total Cap |
|-----------|----------|----------|-----------|
| Single log file | 10 MB | At 10MB | N/A |
| Backup files | 10 MB each | - | 5 files |
| **Total per node** | - | - | **50 MB** |

### System-Wide Estimates
Assuming 5 Python nodes with rotating logs:
- **Total log space:** ~250 MB (5 nodes × 50 MB)
- **Image retention:** ~500 MB (3 days of captures)
- **Total managed:** ~750 MB

This leaves ample space on a 64GB SD card for ROS2 system logs and other data.

---

## Emergency Cleanup Thresholds

| Threshold | Action | Impact |
|-----------|--------|--------|
| > 2 GB free | Normal operation | None |
| < 2 GB free | **WARNING** logged | Warn message every minute |
| < 1 GB free | **CRITICAL** - Emergency cleanup | Delete old logs (> 7 days), Delete old images (> 3 days) |

---

## Testing Recommendations

### Manual Testing
```bash
# 1. Test disk monitor
ros2 run common_utils disk_space_monitor

# 2. In another terminal, watch disk usage
ros2 topic echo /system/disk_usage

# 3. Simulate low disk space (requires sudo)
# Create large file to fill disk
dd if=/dev/zero of=/tmp/fill_disk.img bs=1M count=<size>

# 4. Watch for emergency cleanup in logs
# Monitor should trigger cleanup when < 1GB free
```

### Integration Testing
```bash
# Launch full system with disk monitor
ros2 launch yanthra_move pragati_complete.launch.py

# Verify disk monitor is running
ros2 node list | grep disk_space_monitor

# Check it's publishing
ros2 topic hz /system/disk_usage
```

---

## Future Enhancements (Not in Scope)

- [ ] Compress old logs (gzip) before deletion
- [ ] Upload critical logs to remote server before deletion
- [ ] Configurable cleanup patterns per directory
- [ ] Dashboard/alert integration for disk warnings
- [ ] C++ node logging rotation (currently Python only)

---

## Files Modified/Created

### New Files
- ✅ `src/common_utils/package.xml`
- ✅ `src/common_utils/setup.py`
- ✅ `src/common_utils/common_utils/__init__.py`
- ✅ `src/common_utils/common_utils/pragati_logging.py`
- ✅ `src/common_utils/resource/common_utils`

### Modified Files
- ✅ `src/yanthra_move/launch/pragati_complete.launch.py`
  - Added `log_directory` parameter
  - Added `disk_space_monitor_node`

---

## Success Criteria

- [x] Log rotation implemented with 10MB limit
- [x] Only 5 backup files kept per node
- [x] Disk space monitor publishes to `/system/disk_usage`
- [x] Warning at < 2GB free
- [x] Emergency cleanup at < 1GB free
- [x] Integrated into main launch file
- [x] Package builds successfully
- [x] Configurable via ROS2 parameters
- [ ] 7-day continuous run test (deferred to hardware validation)

---

## Next Steps

### Immediate
1. Update other Python nodes to use `PragatiRotatingLogger`
   - `cotton_detection_ros2`
   - `vehicle_control`
2. Test on Raspberry Pi with limited disk space
3. Monitor disk usage during long-running operations

### Future (Tier 2.2 - Calibration Documentation)
- Document disk space requirements in calibration guide
- Add disk check to pre-flight checklist

---

## Overall Progress

### Tier 1: Core Refactoring
- ✅ **1.1** Remove Dynamixel Messages - **COMPLETE**
- ✅ **1.2** Rename Motor Control Package - **COMPLETE**
- ⏸️  **1.3** Static TF Optimization - **DEFERRED**

### Tier 2: Synchronization, Testing & Documentation
- ⬜ **2.1** ROS2 Pub/Sub Synchronization
- 🔄 **2.2** Unified Calibration Documentation - **NEXT**
- ⬜ **2.3** Integrated Motor+Camera Tests
- 🔄 **2.4** Offline Cotton Detection Testing - **NEXT**

### Tier 3: Operational Robustness
- ✅ **3.1** Log Rotation & Disk Space Protection - **COMPLETE**
- ⬜ **3.2** Motor Tuning Procedures
- ⬜ **3.3** Centralized Error Reporting

**Progress: 3/10 tasks complete (30%)**

---

**Ready for Tier 2.2 (Calibration Documentation) and Tier 2.4 (Offline Cotton Detection)** 🚀
