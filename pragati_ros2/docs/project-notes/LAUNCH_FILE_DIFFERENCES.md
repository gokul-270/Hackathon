# Launch File Differences Analysis

## Files Compared
```
Root:   src/yanthra_move/pragati_complete.launch.py
Launch: src/yanthra_move/launch/pragati_complete.launch.py
```

## Key Differences Found

### 1. URDF Filename (CRITICAL)
```diff
Root:   'URDF'                    # Generic name - may not exist!
Launch: 'MG6010_final.urdf'       # Specific URDF - correct ✅
```
**Impact:** Root version will fail to load robot model

---

### 2. MG6010 Config File
```diff
Root:   'mg6010_three_motors.yaml'    # OLD config name
Launch: 'production.yaml'             # NEW config name ✅
```
**Impact:** Root version references non-existent config

---

### 3. Cotton Detection Description
```diff
Root:   'Enable cotton detection node (false for ArUco calibration mode)'
Launch: 'Enable Cotton Detection with ArUco marker tracking'
```
**Impact:** Minor - just description text

---

### 4. Cotton Detection Launch Timing
```diff
Root:   Launches immediately with rest of nodes
Launch: Uses TimerAction with 0.3s delay + conditional launch ✅
```
**Impact:** Launch version is cleaner with proper conditional logic

---

## Recommendation

**DELETE:** `src/yanthra_move/pragati_complete.launch.py` (root version)

**KEEP:** `src/yanthra_move/launch/pragati_complete.launch.py` (launch/ version)

**Reason:**
1. ROS2 `ros2 launch` looks in `launch/` directory by convention
2. Launch/ version has correct URDF and config names
3. Launch/ version has better conditional logic
4. Root version is outdated and will cause errors

**Which one is actually being used?**
The one in `launch/` directory - ROS2 convention
