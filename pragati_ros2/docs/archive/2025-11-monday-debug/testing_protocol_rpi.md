# RPi Testing Protocol - Friday Morning

**Purpose**: A/B test current vs backup workspace to choose Monday demo configuration  
**Duration**: ~2-3 hours  
**Location**: RPi hardware setup  
**Constraint**: NO CODE CHANGES - run-only testing

---

## Pre-Flight Checklist

### Safety
- [ ] Robot workspace clear of obstacles
- [ ] E-stop button accessible and tested
- [ ] Compressor lines secured and safe
- [ ] Team members aware of testing in progress
- [ ] Fire extinguisher location confirmed

### Hardware
- [ ] RPi powered on and accessible (SSH or direct)
- [ ] OAK-D camera connected (USB3, blue port preferred)
- [ ] RealSense D435i connected (separate USB port)
- [ ] Both cameras detected: `lsusb` shows Intel and Luxonis devices
- [ ] Motor controllers powered and responsive
- [ ] End effector and compressor functional

### Software
- [ ] ROS2 environment: `export ROS_DOMAIN_ID=0`
- [ ] Current workspace built: `cd ~/pragati_ros2 && colcon build`
- [ ] Backup workspace available: `ls ~/pragati_ros2_backup_rpi_20251113_205121`
- [ ] Cameras streaming: `v4l2-ctl --list-devices`

### Materials
- [ ] Ruler or measuring tape (for ground truth)
- [ ] ArUco marker (ID 23, 800mm size)
- [ ] Cotton samples (or test targets)
- [ ] Notepad for manual observations
- [ ] Camera/phone for photos of setup

---

## Test 1: Current Workspace - Cotton Detection Baseline

**Purpose**: Establish baseline performance with current (no rotation) code

### Setup
```bash
cd /home/ubuntu/pragati_ros2
source install/setup.bash
export ROS_DOMAIN_ID=0
```

### Execution
1. Place cotton/target at **known position**:
   - Distance: 400mm forward from camera
   - Lateral: Centered (0mm offset)
   - Vertical: 100mm below camera

2. Launch cotton detection:
```bash
ros2 launch cotton_detection_ros2 detection.launch.py
```

3. In separate terminal, monitor detections:
```bash
ros2 topic echo /cotton_detection/results --once
```

4. Record 5 measurements (reposition target each time):

| Attempt | Actual Position (mm) | Detected X | Detected Y | Detected Z | Notes |
|---------|---------------------|------------|------------|------------|-------|
| 1 | (0, 0, 400) | | | | |
| 2 | (50, 0, 400) | | | | |
| 3 | (-50, 0, 400) | | | | |
| 4 | (0, 50, 400) | | | | |
| 5 | (0, -50, 400) | | | | |

### Expected Observations
- ❌ X and Y coordinates SWAPPED (e.g., X=0 reported as Y=0, Y=50 reported as X=50)
- ❌ Sign errors (e.g., left/right reversed)
- ✅ Z (depth) approximately correct

### Acceptance Criteria
- [ ] Detections received (not empty)
- [ ] Coordinates stable (not jittering wildly)
- [ ] Systematic pattern visible (rotation/swap)

### Stop Conditions
- Camera not detected
- Node crashes repeatedly
- Complete coordinate chaos (no pattern)

---

## Test 2: ArUco Detection - Ground Truth Baseline

**Purpose**: Establish accurate ground truth with RealSense/ArUco

### Setup
```bash
# Use same terminal as Test 1, or new terminal
cd /home/ubuntu/pragati_ros2
source install/setup.bash
```

### Execution
1. Place ArUco marker at **same positions as Test 1**:
   - Use ruler to verify: 400mm forward, centered

2. Run ArUco finder:
```bash
/usr/local/bin/aruco_finder
```

3. Read output:
```bash
cat /tmp/centroid.txt  # Or wherever it saves - check BACKUP_INFO.txt
```

4. Record 3 measurements:

| Attempt | Ruler Position (mm) | ArUco X | ArUco Y | ArUco Z | Error (mm) |
|---------|-------------------|---------|---------|---------|------------|
| 1 | (0, 0, 400) | | | | |
| 2 | (50, 0, 400) | | | | |
| 3 | (0, -50, 400) | | | | |

### Expected Observations
- ✅ Coordinates match ruler within ±10mm
- ✅ X/Y/Z all make sense relative to camera
- ✅ No swap or sign errors

### Acceptance Criteria
- [ ] Marker detected successfully
- [ ] Coordinates reasonable (not NaN or huge values)
- [ ] Accuracy ≤10mm vs ruler measurement

### ArUco as Ground Truth
**IF Test 2 passes**: Use ArUco coordinates as reference for Test 3 comparison

---

## Test 3: Coordinate Comparison - ArUco vs Cotton (Current)

**Purpose**: Directly compare cotton and ArUco at same physical location

### Setup
Use same physical location for both tests - **DO NOT MOVE TARGET**

### Execution
1. Place target (cotton OR ArUco marker) at: **(0mm, 0mm, 400mm)**

2. Run ArUco:
```bash
/usr/local/bin/aruco_finder
cat /tmp/centroid.txt
```
Record: ArUco_X = ____, ArUco_Y = ____, ArUco_Z = ____

3. **WITHOUT MOVING CAMERA OR TARGET**, run cotton detection:
```bash
# Kill ArUco first if using same camera
ros2 launch cotton_detection_ros2 detection.launch.py
ros2 topic echo /cotton_detection/results --once
```
Record: Cotton_X = ____, Cotton_Y = ____, Cotton_Z = ____

4. Calculate delta:
```
Delta_X = Cotton_X - ArUco_X = ____mm
Delta_Y = Cotton_Y - ArUco_Y = ____mm
Delta_Z = Cotton_Z - ArUco_Z = ____mm
```

### Expected Results (Hypothesis)
If rotation hypothesis is correct:
- `Cotton_X ≈ ArUco_Y` (swapped)
- `Cotton_Y ≈ -ArUco_X` (swapped + sign flip)
- `Cotton_Z ≈ ArUco_Z` (depth OK)

### Analysis
- [ ] **X/Y swap detected**: YES / NO
- [ ] **Sign error detected**: YES / NO
- [ ] **Matches hypothesis**: YES / NO

**If YES**: Rotation hypothesis CONFIRMED - backup should fix this

---

## Test 4: Visual Orientation Check

**Purpose**: Verify if image rotation visually matches physical orientation

### Execution
1. Launch cotton detection with debug visualization (if available):
```bash
ros2 launch cotton_detection_ros2 detection.launch.py debug_viz:=true
# Or check if there's an rqt_image_view parameter
```

2. View image output:
```bash
ros2 run rqt_image_view rqt_image_view
# Select /cotton_detection/debug_image or similar topic
```

3. Compare:
   - Physical camera orientation (is it rotated 90°?)
   - Image orientation on screen
   - Are they aligned?

### Record
- **Physical camera rotated**: YES / NO
- **Image orientation matches**: YES / NO
- **Comment**: ___________________________

**Expected**: Image NOT rotated (shows raw camera output), mismatched with physical mount

---

## Test 5: Backup Workspace - Cotton Detection (With Rotation)

**Purpose**: Test if backup rotation fix resolves coordinate issues

### Setup
```bash
cd /home/ubuntu/pragati_ros2_backup_rpi_20251113_205121
source install/setup.bash
export ROS_DOMAIN_ID=0
```

### Execution
1. Place cotton at **SAME position as Test 1**:
   - (0mm, 0mm, 400mm)

2. Launch backup detection:
```bash
ros2 launch cotton_detection_ros2 detection.launch.py
```

3. Monitor results:
```bash
ros2 topic echo /cotton_detection/results --once
```

4. Record 5 measurements (same positions as Test 1):

| Attempt | Actual Position | Backup X | Backup Y | Backup Z | Error vs ArUco (mm) |
|---------|----------------|----------|----------|----------|---------------------|
| 1 | (0, 0, 400) | | | | |
| 2 | (50, 0, 400) | | | | |
| 3 | (-50, 0, 400) | | | | |
| 4 | (0, 50, 400) | | | | |
| 5 | (0, -50, 400) | | | | |

### Expected Observations (If Fix Works)
- ✅ X and Y NO LONGER swapped
- ✅ Signs correct (left is negative, right is positive)
- ✅ Matches ArUco within ±10mm
- ✅ Image visually rotated (if debug viz available)

### Acceptance Criteria for Monday Demo
- [ ] Coordinates match ArUco ≤10mm error
- [ ] No swap or sign errors
- [ ] Stable detection (no crashes for 10+ minutes)
- [ ] No weird artifacts or issues

### Critical Checks
1. **System Stability**: Run for 30 minutes continuous
   ```bash
   # Let it run, monitor for crashes
   watch -n 5 'ros2 topic hz /cotton_detection/results'
   ```
   - [ ] No crashes
   - [ ] Consistent Hz
   - [ ] No memory leaks (check `htop`)

2. **Shutdown Behavior**: Press Ctrl+C
   - [ ] Clean shutdown (no hangs)
   - [ ] No USB errors (or harmless as noted in code comments)
   - [ ] Can restart immediately

---

## Test 6 (Optional): Pick Success A/B Test

**Only if time permits and robot is safe to operate**

### Setup
Place 5-10 cotton targets at various positions

### Execution
1. **Current Workspace**: Run picking sequence
   ```bash
   cd ~/pragati_ros2
   source install/setup.bash
   ros2 launch yanthra_move system.launch.py
   ```
   Record success rate: __/10 successful picks

2. **Backup Workspace**: Same targets, same sequence
   ```bash
   cd ~/pragati_ros2_backup_rpi_20251113_205121
   source install/setup.bash
   ros2 launch yanthra_move system.launch.py
   ```
   Record success rate: __/10 successful picks

### Comparison
- Current: __% success
- Backup: __% success
- **Improvement**: __% (backup - current)

**Threshold**: Backup must be ≥20% better to justify risk

---

## Decision Matrix

Fill this out after completing tests:

| Criterion | Weight | Current Score (1-5) | Backup Score (1-5) | Winner |
|-----------|--------|--------------------|--------------------|--------|
| **Coordinate Accuracy** | 🔥🔥🔥 High | | | |
| **System Stability** | 🔥🔥🔥 High | | | |
| **Pick Success Rate** | 🔥🔥 Medium | | | |
| **Visual Alignment** | 🔥 Low | | | |
| **Shutdown Behavior** | 🔥🔥 Medium | | | |

**Scoring**:
- 5 = Excellent (meets all expectations)
- 4 = Good (minor issues, acceptable)
- 3 = Fair (noticeable issues, marginal)
- 2 = Poor (significant issues, risky)
- 1 = Failed (unusable)

### Weighted Decision
- **If Backup scores ≥4 on Accuracy + Stability**: RECOMMEND BACKUP
- **If Backup scores 3 on either**: HYBRID (prepare both)
- **If Backup scores ≤2 on either**: STICK WITH CURRENT

---

## Final Recommendation

### Test Results Summary
- **Test 1 (Current Baseline)**: PASS / FAIL
- **Test 2 (ArUco Ground Truth)**: PASS / FAIL  
- **Test 3 (Coordinate Comparison)**: Hypothesis CONFIRMED / REJECTED
- **Test 5 (Backup Rotation Fix)**: PASS / FAIL
- **Test 6 (Pick Success)**: Current __%, Backup __%

### Monday Demo Configuration

**RECOMMENDATION**: 🟢 USE BACKUP / 🟡 HYBRID / 🔴 USE CURRENT

**Rationale**:
_________________________________
_________________________________
_________________________________

**Confidence Level**: HIGH / MEDIUM / LOW

**Risks Identified**:
1. ___________________________
2. ___________________________
3. ___________________________

**Mitigation Plan**:
- Plan A: ___________________________
- Plan B: ___________________________
- Rollback procedure: < __ minutes

### Sign-off
- **Tester**: _____________ (name)
- **Date/Time**: _____________
- **Next Action**: _____________

---

## Troubleshooting

### Camera Not Detected
```bash
lsusb | grep -E "(Intel|Luxonis)"
# Should show both cameras

# If missing:
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### ROS2 Node Won't Start
```bash
# Check for existing processes
ps aux | grep ros2

# Kill if necessary
pkill -9 -f ros2

# Re-source
source install/setup.bash
```

### Coordinates are NaN or Crazy Values
- Check camera focus (cotton too close?)
- Check lighting (too bright/dark?)
- Verify depth quality: `realsense-viewer` or DepthAI viewer

### Build Errors
```bash
# Clean build
cd ~/pragati_ros2
rm -rf build install log
colcon build --packages-select cotton_detection_ros2
```

---

## Data to Save

### For Analysis Later
1. ROS2 bag files (if recorded):
   ```bash
   ls ~/test*.bag
   ```

2. Screenshots of coordinate outputs

3. Photos of physical setup with ruler

4. This document with all blanks filled in!

---

## Post-Testing Cleanup

- [ ] Power down robot safely
- [ ] Disconnect cameras
- [ ] Save all data to backup location
- [ ] Update README.md with test results
- [ ] Send summary to team
- [ ] Schedule Saturday decision meeting

---

**Good luck with testing! 🚀**

Remember: The goal is to gather DATA, not to make it work perfectly. Even "failed" tests give us valuable information for Monday's demo plan.
