> **Archived:** 2025-10-21
> **Reason:** Historical document - work completed, superseded by canonical docs
> **See instead:** PRODUCTION_READINESS_GAP.md, CONSOLIDATED_ROADMAP.md, TODO_MASTER_CONSOLIDATED.md

# Pragati ROS2 Refactoring & Enhancement Plan
**Version:** 1.0  
**Date:** October 8, 2025  
**Target Release:** v1.0.0  
**Timeline:** 6 weeks (3 tiers)

---

## Executive Summary

This plan addresses 13 review points identified during the October 2025 code review:

1. ✅ **Dynamixel package removal** - Migrate to standard ROS2 messages
2. ✅ **Publisher/Subscriber synchronization** - Replace file-based workaround with QoS-tuned pub/sub
3. ✅ **Static TF optimization** - Fixed geometry doesn't need dynamic lookups
4. ✅ **Calibration documentation** - Unified workflow guide
5. ✅ **Package rename** - `odrive_control_ros2` → `motor_control_ros2`
6. ✅ **Joint flexibility** - Keep 4 joints for future scaling
7. ✅ **Log rotation** - Disk space protection for RPi
8. ✅ **Calibration process** - Step-by-step procedures
9. ✅ **Motor+Camera tests** - Integrated coordination validation
10. ✅ **Error handling** - Centralized monitoring
11. ✅ **Motor tuning** - Speed/torque/PID procedures
12. ✅ **Offline testing** - Cotton detection without hardware
13. ✅ **Test plan integration** - Motor+camera coordination

**Key Principle:** Reuse existing scripts (`build.sh`, `build_rpi.sh`, `test.sh`) — NO new top-level scripts.

---

## Branching Strategy

### Single Long-Lived Branch: `pragati_ros2`
- **Main branch:** `pragati_ros2` (only branch remaining at project end)
- **Feature branches:** Short-lived, deleted after merge
- **Naming convention:**
  - `feature/t1-remove-dynamixel`
  - `feature/t1-rename-motor-pkg`
  - `feature/t1-static-tf`
  - `feature/t2-qos-sync`
  - `feature/t2-calibration-docs`
  - etc.

### Git Tags for Stable Gates
```bash
v0.9.0-pre-refactor  # Baseline (create NOW)
v0.9.1-tier1         # After Tier 1 completion
v0.9.2-tier2         # After Tier 2 completion
v1.0.0               # Final release
```

### Workflow Example
```bash
# Create baseline tag
git tag -a v0.9.0-pre-refactor -m "Baseline before Oct 2025 refactor"

# Work on a feature
git switch -c feature/t1-remove-dynamixel
# ... make changes, commit ...

# Merge back to main branch
git switch pragati_ros2
git merge --no-ff feature/t1-remove-dynamixel
# or: git merge --squash feature/t1-remove-dynamixel; git commit

# Delete feature branch (locally and remotely)
git branch -d feature/t1-remove-dynamixel
git push origin --delete feature/t1-remove-dynamixel
```

---

## Tier 1: Core Refactoring (Weeks 1-2)

**Goal:** Remove legacy dependencies, standardize naming, optimize fixed transforms

### 1.1) Remove Dynamixel Messages Package

**Current State:**
- Package: `src/dynamixel_msgs/` with 3 custom message types
- Used by: `yanthra_move` package

**Actions:**
```bash
# Find all usage
rg -n "dynamixel_msgs|MotorState|MotorStateList" -g "!build" -g "!install"

# Key files to update:
# - yanthra_move/package.xml (line 38)
# - yanthra_move/include/yanthra_move/joint_move_sensor_msgs.h
# - yanthra_move/CMakeLists.txt
```

**Migration Path:**
- Replace `dynamixel_msgs/JointState` → `sensor_msgs/msg/JointState`
- Motor temps/voltages → `diagnostic_msgs/msg/DiagnosticArray`
- Keep topic names unchanged (just swap message types)

**Validation:**
```bash
./build.sh
./test.sh
ros2 topic echo /joint_states  # Verify standard JointState messages
```

**Success Criteria:**
- ✅ `yanthra_move` builds without dynamixel_msgs dependency
- ✅ All existing tests pass
- ✅ Motion behavior unchanged

---

### 1.2) Rename Motor Control Package

**Current:** `odrive_control_ros2`  
**New:** `motor_control_ros2`

**Actions:**
```bash
# Rename directory
mv src/odrive_control_ros2 src/motor_control_ros2

# Update metadata files:
# - package.xml: <name>motor_control_ros2</name>
# - CMakeLists.txt: project(motor_control_ros2)

# Find and replace namespace
rg -n "odrive_control_ros2" --no-ignore | wc -l  # Check count
# Then replace: odrive_control_ros2:: → motor_control_ros2::

# Update dependent packages:
# - yanthra_move/package.xml
# - yanthra_move/CMakeLists.txt
# - vehicle_control/package.xml
# - vehicle_control/launch/*.launch.py
```

**Legacy Code Handling:**
- Move ODrive-specific implementations to `src/motor_control_ros2/src/odrive_legacy/`
- Add deprecation notices in legacy files
- Keep for reference but mark clearly

**Validation:**
```bash
rg "odrive_control_ros2" -g "!legacy"  # Should return ZERO matches
./build.sh --symlink-install
ros2 pkg list | grep motor_control  # Verify new name
```

**Success Criteria:**
- ✅ All packages build under new name
- ✅ No `odrive_control_ros2` references outside legacy folder
- ✅ Launch files work with renamed package

---

### 1.3) Static TF Optimization

**Problem:** Fixed camera/arm geometry queried dynamically (wasteful)

**Current State:**
```cpp
// coordinate_transforms.cpp (inefficient)
auto transform = tf_buffer.lookupTransform("base_link", "camera_link", tf2::TimePointZero);
// Called repeatedly for STATIC geometry!
```

**Solution:**
1. **Publish static transforms once** (in launch file)
2. **Cache transform on first lookup** (in code)

**Launch File Changes:**
```python
# pragati_complete.launch.py
static_tf_nodes = [
    Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        arguments=['0', '0', '0.55', '0', '0', '0', 'base_link', 'camera_link'],
        name='camera_static_tf'
    ),
    # Add other fixed transforms...
]
```

**Code Changes:**
```cpp
// coordinate_transforms.cpp
class TransformCache {
    std::unordered_map<std::string, geometry_msgs::msg::TransformStamped> cache_;
    
    geometry_msgs::msg::TransformStamped getTransform(
        const std::string& target, const std::string& source) {
        std::string key = target + "_" + source;
        if (cache_.find(key) == cache_.end()) {
            cache_[key] = tf_buffer_->lookupTransform(target, source, tf2::TimePointZero);
        }
        return cache_[key];
    }
};
```

**Validation:**
```bash
# Check TF tree
ros2 run tf2_tools view_frames
# Look for static edges (should be marked as STATIC)

# Check /tf_static topic
ros2 topic echo /tf_static

# Measure CPU before/after
top -p $(pgrep -f yanthra_move)
```

**Expected Improvement:**
- 🎯 **~30% reduction** in transform lookup CPU overhead
- 🎯 Latency reduced from ~5ms → <1ms per transform

**Success Criteria:**
- ✅ All fixed transforms published to `/tf_static` exactly once
- ✅ No repeated lookupTransform() calls for static geometry
- ✅ CPU usage reduced (measured)

---

### Tier 1 Gate: Smoke Test & Tag

**Validation:**
```bash
# Build on both platforms
./build.sh                # Host
./build_rpi.sh           # Raspberry Pi

# Run full test suite
./test.sh

# Launch full stack and verify basics
ros2 launch yanthra_move pragati_complete.launch.py

# Check key indicators:
# - TF tree stable (ros2 run tf2_tools view_frames)
# - Motor node alive (ros2 node list | grep motor)
# - Camera publishes (ros2 topic hz /cotton_detection/results)
```

**Tag & Cleanup:**
```bash
git tag -a v0.9.1-tier1 -m "Tier 1: Core refactoring complete"
git push origin v0.9.1-tier1

# Delete merged feature branches
git branch -d feature/t1-remove-dynamixel
git branch -d feature/t1-rename-motor-pkg
git branch -d feature/t1-static-tf
```

---

## Tier 2: Synchronization, Testing & Documentation (Weeks 3-4)

**Goal:** Replace file-based workarounds, comprehensive testing, calibration docs

### 2.1) ROS2 Pub/Sub Synchronization (Replace File I/O)

**Historical Context:**
- ROS1 had pub/sub sync issues between camera detection and arm movement
- Workaround: Write detections to `cotton_details.txt`, read by arm node
- **Problem:** Unreliable, slow, not suitable for production

**Current File-Based Flow:**
```
CottonDetect.py → writes → cotton_details.txt
                                ↓
yanthra_move    ← reads  ← cotton_details.txt
```

**New ROS2 Flow:**
```
CottonDetect.py → publishes → /cotton_detection/results
                                     ↓ (QoS: Reliable, KeepLast 10)
yanthra_move    ← subscribes ← /cotton_detection/results
```

**Implementation:**

1. **Remove File I/O:**
```bash
# Find and remove cotton_details.txt usage
rg -n "cotton_details\.txt" src/
# Delete file read/write code in both packages
```

2. **QoS Configuration:**
```python
# cotton_detect_ros2_wrapper.py
self.detection_pub_ = self.create_publisher(
    DetectionResult,
    '/cotton_detection/results',
    qos_profile=QoSProfile(
        reliability=QoSReliabilityPolicy.RELIABLE,
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=10
    )
)
```

3. **Buffering & Staleness Filter:**
```cpp
// yanthra_move_system.cpp (already has mutex-protected storage)
class DetectionBuffer {
    std::deque<Detection> buffer_;
    std::mutex mutex_;
    static constexpr auto MAX_AGE = std::chrono::milliseconds(200);
    
    std::optional<Detection> getLatest() {
        std::lock_guard<std::mutex> lock(mutex_);
        auto now = node_->get_clock()->now();
        
        // Remove stale detections
        while (!buffer_.empty() && 
               (now - buffer_.front().timestamp) > MAX_AGE) {
            buffer_.pop_front();
        }
        
        return buffer_.empty() ? std::nullopt : std::make_optional(buffer_.back());
    }
};
```

4. **100ms Processing Timer:**
```cpp
// Timer to process detections at 100ms intervals
processing_timer_ = node_->create_wall_timer(
    std::chrono::milliseconds(100),
    std::bind(&YanthraMoveSystem::processLatestDetection, this)
);
```

5. **Latency Monitoring:**
```cpp
// Publish detection-to-action latency
void publishLatency(const Detection& det) {
    auto latency = node_->get_clock()->now() - det.header.stamp;
    std_msgs::msg::Float32 msg;
    msg.data = latency.seconds() * 1000.0;  // Convert to ms
    latency_pub_->publish(msg);
}
```

**Validation:**
```bash
# Monitor latency
ros2 topic echo /system/detection_latency

# Check for missed detections (should be ZERO)
ros2 topic hz /cotton_detection/results
ros2 topic hz /yanthra_move/pick_attempts

# Ratio should be ~1:1 (one pick per detection)
```

**Success Criteria:**
- ✅ No file-based I/O remains
- ✅ Detection-to-action latency < 200ms (95th percentile)
- ✅ Zero missed detections in normal operation
- ✅ QoS policy documented in README

---

### 2.2) Unified Calibration Documentation

**File:** `docs/CALIBRATION_GUIDE.md`

**Structure:**
```markdown
# Pragati Robot Calibration Guide

## Prerequisites
- ROS2 environment sourced
- Hardware powered and connected
- Safety area clear

## 1. Motor & Encoder Calibration

### 1.1 Homing Procedure
```bash
# Home all joints to zero position
ros2 service call /motor/home_all motor_control_ros2/srv/JointHoming "{}"

# Verify joint positions
ros2 topic echo /joint_states
```

### 1.2 Encoder Zeroing
```bash
# Set current position as zero for joint2
ros2 service call /motor/encoder_calibrate motor_control_ros2/srv/EncoderCalibration \
  "{joint_id: 2, set_zero: true}"
```

### 1.3 Save Calibration
```bash
# Persist calibration data
ros2 param dump /motor_controller --output-dir config/calibration/
```

## 2. Camera Intrinsic Calibration

### 2.1 Verify EEPROM Data
```bash
# Export calibration from OAK-D Lite EEPROM
ros2 service call /cotton_detection/calibrate \
  cotton_detection_ros2/srv/CottonDetection "{detect_command: 2}"

# Check output in ~/.ros/camera_calibration.json
```

### 2.2 Validate Intrinsics
- Expected focal length: ~880 pixels
- Expected distortion: < 0.05
- Matrix should be non-singular

## 3. Hand-Eye Extrinsic Calibration

### 3.1 ArUco Board Capture
```bash
# Launch calibration mode
ros2 launch yanthra_move pragati_complete.launch.py bringup_calibration:=true

# Capture 20+ poses from different angles
# (Interactive GUI will guide you)
```

### 3.2 Update URDF
- Edit `robo_description/urdf/URDF_REP103_EYETOHAND_MASTERCOPY_*.urdf`
- Update `camera_link` to `base_link` transform
- Verify with `ros2 run robot_state_publisher robot_state_publisher --ros-args -p robot_description:=$(cat urdf/...)`

### 3.3 TF Validation
```bash
# Check transform chain
ros2 run tf2_tools view_frames
ros2 run tf2_ros tf2_echo base_link camera_link

# Expected translation: [X, Y, Z] within ±5mm of measured
```

## 4. System Validation

### Checklist
- [ ] All joints reach commanded positions (±0.5°)
- [ ] Camera detects ArUco marker at 0.5m distance
- [ ] Pick accuracy: cotton location error < 10mm
- [ ] No error messages in logs

### Troubleshooting
... (common issues and fixes)
```

**Implementation Changes:**
- Add `bringup_calibration:=true` argument to `pragati_complete.launch.py`
- When true, launch only calibration subset (camera + robot_state_publisher)
- No new scripts - all via `ros2 launch` and `ros2 service call`

**Success Criteria:**
- ✅ A newcomer can follow the guide and complete calibration
- ✅ All commands work as documented
- ✅ Troubleshooting section covers 90% of common issues

---

### 2.3) Integrated Motor+Camera Coordination Tests

**Location:** `test_suite/integration/` within packages

**Test Cases:**

```python
# test/integration/test_pick_coordination.py
import pytest
from geometry_msgs.msg import Point

@pytest.fixture
def known_cotton_positions():
    """Load ground truth positions from YAML"""
    return [
        {"id": 1, "position": Point(x=0.5, y=0.2, z=0.1), "confidence": 0.95},
        {"id": 2, "position": Point(x=0.6, y=-0.1, z=0.15), "confidence": 0.88},
    ]

def test_single_detection_pick(launch_nodes, known_cotton_positions):
    """Test: Single detection triggers correct arm movement"""
    # Publish detection
    publish_detection(known_cotton_positions[0])
    
    # Wait for arm to move
    arm_position = wait_for_joint_state(timeout=2.0)
    
    # Validate pick accuracy
    error = calculate_pick_error(arm_position, known_cotton_positions[0])
    assert error < 0.010, f"Pick error {error}m exceeds 10mm threshold"

def test_multiple_sequential_picks(launch_nodes, known_cotton_positions):
    """Test: Multiple detections handled in sequence"""
    for pos in known_cotton_positions:
        publish_detection(pos)
        assert wait_for_pick_complete(timeout=3.0), "Pick did not complete"
        assert get_success_count() == known_cotton_positions.index(pos) + 1

def test_timeout_handling(launch_nodes):
    """Test: System handles detection timeout gracefully"""
    # Don't publish detection, verify timeout
    with pytest.raises(TimeoutError):
        wait_for_detection(timeout=1.0)
    
    # System should recover and remain operational
    assert is_node_alive('/yanthra_move')

def test_out_of_reach_filtering(launch_nodes):
    """Test: Out-of-reach detections are rejected"""
    unreachable = {"position": Point(x=2.0, y=0, z=0), "confidence": 0.99}
    publish_detection(unreachable)
    
    # Should NOT attempt pick
    time.sleep(1.0)
    assert get_pick_attempts() == 0, "Attempted to pick unreachable cotton"

def test_transform_accuracy(launch_nodes):
    """Test: Camera-to-base transform is accurate"""
    # Publish detection in camera frame
    camera_point = Point(x=0.5, y=0, z=0.3)
    publish_detection({"position": camera_point, "confidence": 0.9})
    
    # Check transformed point in base frame
    base_point = get_transformed_target()
    expected_base = transform_camera_to_base(camera_point)  # Ground truth
    
    error = np.linalg.norm([base_point.x - expected_base.x,
                            base_point.y - expected_base.y,
                            base_point.z - expected_base.z])
    assert error < 0.015, f"Transform error {error}m exceeds 15mm"
```

**Fixtures:**
```yaml
# test/fixtures/known_cotton_positions.yaml
cotton_targets:
  - id: 1
    camera_frame:
      x: 0.45
      y: 0.12
      z: 0.28
    base_frame:
      x: 0.52
      y: 0.15
      z: 0.35
    confidence: 0.95
    
  - id: 2
    camera_frame:
      x: 0.60
      y: -0.08
      z: 0.32
    base_frame:
      x: 0.67
      y: -0.05
      z: 0.39
    confidence: 0.88
```

**Integration with test.sh:**
```bash
# test.sh (enhanced)
#!/bin/bash
set -e

echo "Running unit tests..."
colcon test --packages-select motor_control_ros2 yanthra_move cotton_detection_ros2

echo "Running integration tests..."
colcon test --packages-select yanthra_move \
  --event-handlers console_direct+ \
  --pytest-args -v tests/integration/

echo "Aggregating results..."
colcon test-result --verbose
```

**Success Criteria:**
- ✅ All integration tests pass in simulation mode
- ✅ All integration tests pass on hardware-in-the-loop (RPi)
- ✅ Test execution time < 10 minutes
- ✅ Tests run automatically via `./test.sh`

---

### 2.4) Offline Cotton Detection Testing

**Goal:** Test detection without live camera hardware

**Implementation:**

1. **Add offline_mode parameter:**
```python
# cotton_detect_ros2_wrapper.py
self.declare_parameter('offline_mode', False)
self.declare_parameter('offline_data_dir', '/path/to/test/datasets/cotton_images')

if self.get_parameter('offline_mode').value:
    self.image_loader = ImageLoader(self.get_parameter('offline_data_dir').value)
    # Don't spawn camera subprocess
else:
    self.spawn_camera_subprocess()
```

2. **Batch processing:**
```python
class ImageLoader:
    def __init__(self, data_dir):
        self.images = sorted(glob.glob(f"{data_dir}/*.jpg"))
        self.index = 0
    
    def get_next(self):
        if self.index >= len(self.images):
            return None
        img_path = self.images[self.index]
        self.index += 1
        return cv2.imread(img_path)
```

3. **Ground truth comparison:**
```yaml
# test/datasets/ground_truth.yaml
image_001.jpg:
  detections:
    - bbox: [120, 80, 200, 160]
      position: [0.50, 0.15, 0.30]
      confidence: 0.92
    - bbox: [350, 120, 420, 190]
      position: [0.55, -0.10, 0.28]
      confidence: 0.87

image_002.jpg:
  detections:
    - bbox: [180, 100, 250, 170]
      position: [0.48, 0.20, 0.32]
      confidence: 0.90
```

4. **Accuracy metrics:**
```python
def compute_accuracy(predicted, ground_truth, iou_threshold=0.5):
    """
    Returns: precision, recall, f1_score, avg_position_error
    """
    tp, fp, fn = 0, 0, 0
    position_errors = []
    
    for pred in predicted:
        best_iou = 0
        best_match = None
        for gt in ground_truth:
            iou = compute_iou(pred.bbox, gt.bbox)
            if iou > best_iou:
                best_iou = iou
                best_match = gt
        
        if best_iou >= iou_threshold:
            tp += 1
            position_errors.append(np.linalg.norm(pred.position - best_match.position))
        else:
            fp += 1
    
    fn = len(ground_truth) - tp
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    avg_error = np.mean(position_errors) if position_errors else 0
    
    return precision, recall, f1, avg_error
```

**Launch:**
```bash
# Offline testing mode
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py \
  offline_mode:=true \
  offline_data_dir:=/path/to/test/datasets/cotton_images

# Or via test.sh with environment variable
OFFLINE=1 ./test.sh
```

**Success Criteria:**
- ✅ 100-image batch completes in < 5 minutes on host
- ✅ ≥95% accuracy (F1 score) on curated test set
- ✅ Average position error < 15mm
- ✅ No new scripts created (run via existing launch/test infrastructure)

---

### Tier 2 Gate: Hardware Validation & Documentation Review

**Hardware-in-the-Loop Test (1 hour on RPi):**
```bash
# Run full stack with metrics collection
ros2 launch yanthra_move pragati_complete.launch.py \
  continuous_operation:=true \
  max_runtime_minutes:=60

# Monitor during run:
# - Detection-to-action latency: ros2 topic echo /system/detection_latency
# - Pick success rate: ros2 topic echo /yanthra_move/statistics
# - CPU usage: htop
# - Memory usage: free -h (should remain stable)
```

**Documentation Review:**
- Have a fresh team member follow `CALIBRATION_GUIDE.md`
- Track time to complete and any confusion points
- Update guide based on feedback

**Tag & Cleanup:**
```bash
git tag -a v0.9.2-tier2 -m "Tier 2: Sync, testing, docs complete"
git push origin v0.9.2-tier2
# Delete all feature branches
```

---

## Tier 3: Operational Robustness (Weeks 5-6)

**Goal:** Production readiness - log management, tuning procedures, health monitoring

### 3.1) Log Rotation & Disk Space Protection

**Problem:** RPi has 64GB SD card; logs and images can fill it quickly

**Solution:**

1. **Python nodes - RotatingFileHandler:**
```python
# In each Python node
import logging
from logging.handlers import RotatingFileHandler

def setup_logging(node_name):
    log_dir = node.get_parameter('log_directory').value  # ROS2 param
    log_path = os.path.join(log_dir, f'{node_name}.log')
    
    handler = RotatingFileHandler(
        log_path,
        maxBytes=10*1024*1024,  # 10 MB per file
        backupCount=5           # Keep 5 backups (50 MB total)
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    logger = logging.getLogger(node_name)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
```

2. **System logrotate config:**
```bash
# deploy/logrotate.d/pragati_ros2
/home/ubuntu/.ros/log/pragati/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ubuntu ubuntu
    sharedscripts
    postrotate
        systemctl reload rsyslog > /dev/null 2>&1 || true
    endscript
}
```

**Installation (one-time):**
```bash
sudo cp deploy/logrotate.d/pragati_ros2 /etc/logrotate.d/
sudo logrotate -d /etc/logrotate.d/pragati_ros2  # Test config
```

3. **Image retention policy:**
```python
# In cotton_detection_ros2
self.declare_parameter('max_images', 100)
self.declare_parameter('max_age_days', 7)

def save_detection_image(self, image, timestamp):
    # Save new image
    filename = f"detection_{timestamp}.jpg"
    cv2.imwrite(os.path.join(self.output_dir, filename), image)
    
    # Cleanup old images
    self.cleanup_old_images()

def cleanup_old_images(self):
    max_images = self.get_parameter('max_images').value
    max_age = self.get_parameter('max_age_days').value * 86400  # Convert to seconds
    
    images = sorted(glob.glob(f"{self.output_dir}/*.jpg"), 
                   key=os.path.getmtime)
    
    now = time.time()
    
    # Remove by age
    for img in images:
        if now - os.path.getmtime(img) > max_age:
            os.remove(img)
            self.get_logger().debug(f"Removed old image: {img}")
    
    # Remove by count
    images = sorted(glob.glob(f"{self.output_dir}/*.jpg"), 
                   key=os.path.getmtime)
    if len(images) > max_images:
        for img in images[:len(images)-max_images]:
            os.remove(img)
            self.get_logger().debug(f"Removed excess image: {img}")
```

4. **Disk usage monitor:**
```python
# Add to yanthra_move_system or create tiny system_monitor node
import shutil

class DiskMonitor:
    def __init__(self, node):
        self.node = node
        self.usage_pub = node.create_publisher(Float32, '/system/disk_usage', 10)
        self.timer = node.create_timer(60.0, self.check_disk_usage)  # Every minute
        
    def check_disk_usage(self):
        stat = shutil.disk_usage('/')
        free_gb = stat.free / (1024**3)
        
        msg = Float32()
        msg.data = free_gb
        self.usage_pub.publish(msg)
        
        if free_gb < 2.0:
            self.node.get_logger().warn(f"Low disk space: {free_gb:.2f} GB free")
            if free_gb < 1.0:
                self.node.get_logger().error(f"CRITICAL: Only {free_gb:.2f} GB free! Starting emergency cleanup...")
                self.emergency_cleanup()
    
    def emergency_cleanup(self):
        # Delete old logs beyond 3 days
        # Delete old images beyond 3 days
        # Compress uncompressed logs
        pass
```

**Success Criteria:**
- ✅ Logs capped at ~100 MB total
- ✅ Images capped at ~500 MB total
- ✅ No disk-full incidents during 7-day continuous run
- ✅ Disk usage published to `/system/disk_usage` every minute

---

### 3.2) Motor Tuning Procedures & Service Interface

**Documentation:** `docs/MOTOR_TUNING_GUIDE.md`

**Content:**
```markdown
# Motor Tuning Guide

## Safety First
- Ensure robot is in safe workspace (no obstructions)
- Emergency stop within reach
- Start with conservative limits

## 1. Speed Profile Optimization

### Determine Max Safe Speed
```bash
# Gradually increase speed limit
ros2 param set /motor_controller joint2_max_velocity 1.0  # rad/s
# Test motion, increase if stable:
ros2 param set /motor_controller joint2_max_velocity 2.0
# Continue until vibration or instability observed
# Set to 80% of maximum stable value
```

### Acceleration Limits
```bash
# Set based on load and response time requirements
ros2 param set /motor_controller joint2_max_acceleration 3.0  # rad/s²
```

## 2. Torque Limits Configuration

### Holding Torque
```bash
# Set minimum torque to hold position against gravity
ros2 param set /motor_controller joint2_holding_torque 0.3  # Nm
```

### Peak Torque
```bash
# Set maximum torque (safety limit)
ros2 param set /motor_controller joint2_peak_torque 2.0  # Nm
```

## 3. PID Auto-Tuning

### Automatic Tuning (Recommended)
```bash
# Trigger auto-tuning for joint2 position control
ros2 service call /motor/auto_tune motor_control_ros2/srv/MotorTuning \
  "{joint_id: 2, mode: 'position', method: 'relay_feedback', excite: true}"

# Monitor tuning progress
ros2 topic echo /motor/tuning_status

# Results will be automatically applied and saved
```

### Manual Tuning (Advanced)
- Start with Kp only (Ki=0, Kd=0)
- Increase Kp until steady oscillation
- Set Kp to 50% of oscillation point
- Add Ki to eliminate steady-state error
- Add Kd to reduce overshoot

### Validation
```bash
# Test step response
ros2 service call /motor/test_profile motor_control_ros2/srv/TestMotion \
  "{joint_id: 2, target_position: 0.5, hold_time: 2.0}"

# Check metrics:
# - Rise time: < 0.5s
# - Overshoot: < 5%
# - Settling time: < 1.0s
# - Steady-state error: < 0.01 rad
```

## 4. Save and Load Profiles

### Save Tuned Parameters
```bash
# Save current parameters as "fast_pick" profile
ros2 param dump /motor_controller \
  --output-dir config/motor_profiles/ \
  --print-file motor_profile_fast_pick.yaml
```

### Load Profile
```bash
# Load saved profile
ros2 param load /motor_controller config/motor_profiles/motor_profile_fast_pick.yaml
```

### Pre-defined Profiles
- `motor_profile_safe.yaml` - Conservative, high reliability
- `motor_profile_fast_pick.yaml` - Optimized for speed
- `motor_profile_precision.yaml` - Optimized for accuracy
```

**Service Definition:**
```bash
# srv/MotorTuning.srv
uint8 joint_id
string mode  # 'position', 'velocity', 'torque'
string method  # 'relay_feedback', 'ziegler_nichols', 'manual'
bool excite  # Generate test excitation signal
float64 kp  # Only for manual method
float64 ki
float64 kd
---
bool success
string message
float64 final_kp
float64 final_ki
float64 final_kd
float64 rise_time
float64 overshoot
float64 settling_time
```

**Implementation (reuse existing):**
```cpp
// Expose existing pid_auto_tuner.cpp via service
class MotorTuningService {
    rclcpp::Service<motor_control_ros2::srv::MotorTuning>::SharedPtr service_;
    std::unique_ptr<PIDAutoTuner> tuner_;
    
    void tuning_callback(
        const motor_control_ros2::srv::MotorTuning::Request::SharedPtr request,
        motor_control_ros2::srv::MotorTuning::Response::SharedPtr response) {
        
        if (request->method == "relay_feedback") {
            auto result = tuner_->performRelayFeedbackTest(request->joint_id);
            response->final_kp = result.kp;
            response->final_ki = result.ki;
            response->final_kd = result.kd;
            response->success = true;
        }
        // ... other methods
    }
};
```

**Success Criteria:**
- ✅ Auto-tuning works without manual intervention
- ✅ Tuned profiles significantly better than defaults (measured step response)
- ✅ Parameters persist across reboots via saved YAML files
- ✅ Documentation enables non-expert to tune motors

---

### 3.3) Centralized Error Reporting & Health Monitoring

**Goal:** Unified view of system health across all nodes

**Architecture:**
```
[Motor Node] ----\
[Camera Node] ----> [diagnostics/] topic --> [System Monitor] --> [/system/health] topic
[Arm Node] ------/                                                     |
                                                                       v
                                                              [Dashboard/Alerts]
```

**Implementation:**

1. **Standardize diagnostics in all nodes:**
```cpp
// In each node
#include <diagnostic_msgs/msg/diagnostic_array.hpp>

class MyNode {
    rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diag_pub_;
    
    void publish_diagnostics(const std::string& name, uint8_t level, const std::string& message) {
        diagnostic_msgs::msg::DiagnosticArray array;
        array.header.stamp = this->now();
        
        diagnostic_msgs::msg::DiagnosticStatus status;
        status.name = name;
        status.level = level;  // OK=0, WARN=1, ERROR=2, STALE=3
        status.message = message;
        
        // Add key-value pairs
        diagnostic_msgs::msg::KeyValue kv;
        kv.key = "error_count";
        kv.value = std::to_string(error_count_);
        status.values.push_back(kv);
        
        array.status.push_back(status);
        diag_pub_->publish(array);
    }
};
```

2. **System monitor node:**
```python
# New lightweight node: yanthra_move/src/system_monitor_node.py
class SystemMonitor(Node):
    def __init__(self):
        super().__init__('system_monitor')
        
        # Subscribe to diagnostics from all nodes
        self.diag_sub = self.create_subscription(
            DiagnosticArray,
            '/diagnostics',
            self.diagnostics_callback,
            10
        )
        
        # Publish aggregated health
        self.health_pub = self.create_publisher(DiagnosticStatus, '/system/health', 10)
        
        # Track node health
        self.node_health = {}
        self.error_counts = {}
        self.recovery_counts = {}
        
        # Publish health every 5 seconds
        self.timer = self.create_timer(5.0, self.publish_system_health)
    
    def diagnostics_callback(self, msg):
        for status in msg.status:
            self.node_health[status.name] = status.level
            
            if status.level >= DiagnosticStatus.ERROR:
                self.error_counts[status.name] = self.error_counts.get(status.name, 0) + 1
    
    def publish_system_health(self):
        health = DiagnosticStatus()
        health.name = "system_overall"
        health.hardware_id = "pragati_robot"
        
        # Compute overall status
        if not self.node_health:
            health.level = DiagnosticStatus.STALE
            health.message = "No diagnostics received"
        else:
            max_level = max(self.node_health.values())
            health.level = max_level
            
            if max_level == DiagnosticStatus.OK:
                health.message = f"All systems operational ({len(self.node_health)} nodes)"
            elif max_level == DiagnosticStatus.WARN:
                warnings = [k for k, v in self.node_health.items() if v == DiagnosticStatus.WARN]
                health.message = f"Warnings: {', '.join(warnings)}"
            else:
                errors = [k for k, v in self.node_health.items() if v >= DiagnosticStatus.ERROR]
                health.message = f"Errors: {', '.join(errors)}"
        
        # Add statistics
        health.values.append(KeyValue(key="total_nodes", value=str(len(self.node_health))))
        health.values.append(KeyValue(key="total_errors", value=str(sum(self.error_counts.values()))))
        health.values.append(KeyValue(key="uptime_seconds", value=str(self.get_clock().now().nanoseconds / 1e9)))
        
        self.health_pub.publish(health)
```

3. **Error recovery with backoff:**
```cpp
// In comprehensive_error_handler.cpp (enhance existing)
class ErrorRecovery {
    std::map<std::string, RetryPolicy> policies_;
    
    struct RetryPolicy {
        int max_retries = 3;
        std::vector<double> backoff_seconds = {1.0, 5.0, 15.0};
        int current_attempt = 0;
    };
    
    bool try_recover(const std::string& error_type) {
        auto& policy = policies_[error_type];
        
        if (policy.current_attempt >= policy.max_retries) {
            RCLCPP_ERROR(get_logger(), "Max retries exceeded for %s", error_type.c_str());
            return false;
        }
        
        double wait_time = policy.backoff_seconds[policy.current_attempt];
        RCLCPP_WARN(get_logger(), "Retry %d/%d for %s after %.1fs",
                   policy.current_attempt + 1, policy.max_retries,
                   error_type.c_str(), wait_time);
        
        std::this_thread::sleep_for(std::chrono::duration<double>(wait_time));
        policy.current_attempt++;
        
        // Attempt recovery action
        bool success = attempt_recovery_action(error_type);
        
        if (success) {
            policy.current_attempt = 0;  // Reset on success
            RCLCPP_INFO(get_logger(), "Recovery successful for %s", error_type.c_str());
        }
        
        return success;
    }
};
```

4. **Error injection tests:**
```python
# test/test_error_recovery.py
def test_camera_timeout_recovery():
    """Simulate camera timeout and verify recovery"""
    # Kill camera node
    os.system("ros2 lifecycle set /cotton_detection shutdown")
    
    # System should detect and attempt recovery
    time.sleep(2.0)
    
    # Check diagnostics
    msg = wait_for_message('/diagnostics', DiagnosticArray, timeout=5.0)
    camera_status = [s for s in msg.status if 'camera' in s.name.lower()][0]
    assert camera_status.level == DiagnosticStatus.ERROR
    
    # System monitor should show degraded
    health = wait_for_message('/system/health', DiagnosticStatus, timeout=5.0)
    assert health.level >= DiagnosticStatus.WARN
    
    # Restart camera
    os.system("ros2 run cotton_detection_ros2 cotton_detection_node &")
    
    # Verify recovery
    time.sleep(5.0)
    health = wait_for_message('/system/health', DiagnosticStatus, timeout=5.0)
    assert health.level == DiagnosticStatus.OK

def test_serial_communication_retry():
    """Simulate serial error and verify retry with backoff"""
    # Inject serial error (mock CAN bus disconnect)
    inject_error('/motor_controller', 'serial_timeout')
    
    # Monitor retry attempts
    attempts = []
    def log_callback(msg):
        if 'Retry' in msg.msg:
            attempts.append(time.time())
    
    log_sub = create_subscription(Log, '/rosout', log_callback, 10)
    
    time.sleep(30.0)  # Wait for retries
    
    # Verify exponential backoff
    assert len(attempts) >= 2
    assert attempts[1] - attempts[0] > 3.0  # Backoff working
```

**Success Criteria:**
- ✅ All nodes publish to `/diagnostics` topic
- ✅ System monitor aggregates health to `/system/health`
- ✅ >90% automatic recovery for transient errors (camera disconnect, serial timeout)
- ✅ Error statistics available (total errors, recovery success rate)
- ✅ Error injection tests pass

---

### Cross-Cutting: Script Reuse Policy

**Strict Rule:** Do NOT create new top-level scripts

**Enhancements to Existing Scripts:**

1. **build.sh:**
```bash
#!/bin/bash
# Enhanced to pass through colcon args

# Parse arguments
COLCON_ARGS=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --packages-select)
            COLCON_ARGS="$COLCON_ARGS --packages-select $2"
            shift 2
            ;;
        --symlink-install)
            COLCON_ARGS="$COLCON_ARGS --symlink-install"
            shift
            ;;
        *)
            COLCON_ARGS="$COLCON_ARGS $1"
            shift
            ;;
    esac
done

# Build
colcon build $COLCON_ARGS
```

**Usage:**
```bash
./build.sh --packages-select motor_control_ros2
./build.sh --symlink-install
```

2. **test.sh:**
```bash
#!/bin/bash
# Enhanced to support offline mode and integration tests

# Check for offline mode
if [[ "$OFFLINE" == "1" ]]; then
    export ROS_OFFLINE_MODE=true
    echo "Running in OFFLINE mode"
fi

# Run unit tests
echo "=== Unit Tests ==="
colcon test --packages-select motor_control_ros2 yanthra_move cotton_detection_ros2

# Run integration tests
echo "=== Integration Tests ==="
colcon test --packages-select yanthra_move \
  --event-handlers console_direct+ \
  --pytest-args -v tests/integration/

# Aggregate results
echo "=== Test Results ==="
colcon test-result --verbose
```

**Usage:**
```bash
./test.sh              # Normal mode
OFFLINE=1 ./test.sh    # Offline mode
```

---

## Timeline & Milestones

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  Week 1-2: Tier 1 (Core Refactoring)                          │
│  ├─ Remove dynamixel_msgs                                      │
│  ├─ Rename to motor_control_ros2                              │
│  ├─ Static TF optimization                                     │
│  └─ Gate: v0.9.1-tier1                                        │
│                                                                 │
│  Week 3-4: Tier 2 (Sync, Testing, Docs)                       │
│  ├─ QoS pub/sub (remove file I/O)                             │
│  ├─ Calibration documentation                                  │
│  ├─ Integration tests (motor+camera)                           │
│  ├─ Offline detection testing                                  │
│  └─ Gate: v0.9.2-tier2                                        │
│                                                                 │
│  Week 5-6: Tier 3 (Operational Robustness)                    │
│  ├─ Log rotation & disk protection                             │
│  ├─ Motor tuning procedures                                    │
│  ├─ Error reporting & health monitor                           │
│  └─ Gate: v1.0.0                                              │
│                                                                 │
│  Final: 8-12 hour endurance test → RELEASE                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Time Allocation per Task:**
- Implementation: ~60%
- Testing: ~25%
- Documentation: ~15%

---

## Success Metrics

### Performance Targets
- ✅ Transform lookup latency: **↓30%** (dynamic → static cached)
- ✅ Detection-to-move latency: **<200ms** (95th percentile)
- ✅ Pick accuracy: **<10mm** error
- ✅ CPU usage on RPi: **<60%** average

### Reliability Targets
- ✅ Zero disk-full incidents over 7 days
- ✅ Automatic recovery: **>90%** success rate for transient errors
- ✅ Zero missed detections in normal operation
- ✅ MTBF (Mean Time Between Failures): **>24 hours**

### Quality Targets
- ✅ All tests pass: unit + integration
- ✅ Documentation complete and validated by newcomer
- ✅ No new top-level scripts (reuse existing)
- ✅ Code coverage: **>80%** for new/modified code

---

## Risk Management

### Rollback Strategy
```bash
# If Tier N fails, rollback to previous tag
git switch pragati_ros2
git reset --hard v0.9.1-tier1  # Example: rollback to Tier 1

# Or create hotfix branch from tag
git switch -c hotfix/tier1-fix v0.9.1-tier1
```

### Mitigation
- **Pre-tier tags:** Enable quick rollback
- **Feature branches:** Isolate risk (delete after merge)
- **Legacy folder:** Keep removed code for reference
- **Incremental testing:** Gate at each tier prevents cascading failures

### Contingency
- If auto-tuning fails: Manual tuning fallback documented
- If offline testing infeasible: Skip (mark as future work)
- If log rotation causes issues: Disable and document manual cleanup

---

## Appendix: Quick Reference Commands

### Build & Test
```bash
# Full build
./build.sh

# Selective build
./build.sh --packages-select motor_control_ros2

# Full test suite
./test.sh

# Offline tests
OFFLINE=1 ./test.sh
```

### Git Workflow
```bash
# Create baseline tag (do this NOW)
git tag -a v0.9.0-pre-refactor -m "Baseline before Oct 2025 refactor"

# Work on feature
git switch -c feature/t1-remove-dynamixel
# ... commits ...

# Merge and delete
git switch pragati_ros2
git merge --no-ff feature/t1-remove-dynamixel
git branch -d feature/t1-remove-dynamixel
```

### Monitoring
```bash
# System health
ros2 topic echo /system/health

# Detection latency
ros2 topic echo /system/detection_latency

# Disk usage
ros2 topic echo /system/disk_usage

# TF tree
ros2 run tf2_tools view_frames
```

### Calibration
```bash
# Motor homing
ros2 service call /motor/home_all motor_control_ros2/srv/JointHoming "{}"

# Encoder calibration
ros2 service call /motor/encoder_calibrate motor_control_ros2/srv/EncoderCalibration \
  "{joint_id: 2, set_zero: true}"

# Camera calibration export
ros2 service call /cotton_detection/calibrate \
  cotton_detection_ros2/srv/CottonDetection "{detect_command: 2}"
```

### Motor Tuning
```bash
# Auto-tune
ros2 service call /motor/auto_tune motor_control_ros2/srv/MotorTuning \
  "{joint_id: 2, mode: 'position', method: 'relay_feedback', excite: true}"

# Save profile
ros2 param dump /motor_controller \
  --output-dir config/motor_profiles/ \
  --print-file motor_profile_fast_pick.yaml

# Load profile
ros2 param load /motor_controller config/motor_profiles/motor_profile_fast_pick.yaml
```

---

## Contact & Support

For questions or issues during implementation:
- **Documentation:** Check `docs/CALIBRATION_GUIDE.md` and `docs/MOTOR_TUNING_GUIDE.md`
- **Issues:** Review existing GitHub issues or create new one with [IMPLEMENTATION-PLAN] tag
- **Testing:** All tests in `test_suite/integration/` should be self-documenting

---

**Document Version:** 1.0  
**Last Updated:** October 8, 2025  
**Next Review:** After Tier 1 Gate (v0.9.1-tier1)
