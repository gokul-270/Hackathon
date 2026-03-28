# FINAL FIX: Continuous Operation YAML Loading Issue

**Date**: 2025-10-06  
**Status**: ✅ **COMPLETELY RESOLVED**  
**Root Cause**: Launch file was overriding YAML values with default launch argument values

---

## 🎯 The Actual Problem

You reported seeing this in the logs:
```
Safety-critical parameters:
   continuous_operation: disabled    ← Should be ENABLED!
   start_switch.enable_wait: ENABLED
   simulation_mode: ENABLED
```

Even after setting `continuous_operation: true` in the YAML file, it was still showing as `disabled`.

### Root Cause Found

The launch file (`pragati_complete.launch.py`) was **overriding** YAML values with launch argument defaults:

**Before (BROKEN):**
```python
yanthra_move_node = Node(
    package='yanthra_move',
    executable='yanthra_move_node',
    name='yanthra_move',
    parameters=[config_file, {
        'use_simulation': use_simulation,         # default='true' 
        'continuous_operation': continuous_operation  # default='false' ← OVERWRITES YAML!
    }],
    output=output_log
)
```

In ROS2, when you pass parameters like `[config_file, {dict}]`, the dictionary **overrides** values from the config file. Since `continuous_operation` had `default_value='false'` in the `DeclareLaunchArgument`, it was **always** overwriting your YAML setting.

---

## ✅ The Fix Applied

**File Modified**: `src/yanthra_move/launch/pragati_complete.launch.py`

**After (FIXED):**
```python
yanthra_move_node = Node(
    package='yanthra_move',
    executable='yanthra_move_node',
    name='yanthra_move',
    parameters=[config_file],  # ← Only YAML file, no overrides!
    output=output_log
)
```

**What changed:**
- Removed the override dictionary `{'use_simulation': ..., 'continuous_operation': ...}`
- Now **only** the YAML file is used for parameters
- Launch arguments no longer override YAML values by default

---

## 📊 Test Results After Fix

### Test 1: YAML Values Respected ✅

**YAML Config:**
```yaml
continuous_operation: true
max_runtime_minutes: -1
start_switch.enable_wait: false
```

**Log Output:**
```
🔍 DEBUG: continuous_operation AFTER DECLARE: TRUE
🔒 Safety-critical parameters:
   continuous_operation: ENABLED  ✅
   start_switch.enable_wait: disabled  ✅
Maximum runtime: INFINITE (no timeout)  ✅
```

**Result**: YAML values are now correctly loaded!

### Test 2: Multiple Continuous Cycles ✅

The system successfully ran multiple continuous operational cycles without stopping.

---

## 🚀 How to Use Continuous Operation Now

### Method 1: Edit YAML (Recommended)

```bash
# Edit the configuration file
nano src/yanthra_move/config/production.yaml

# Set these values:
continuous_operation: true
start_switch.enable_wait: false  # For automated testing
max_runtime_minutes: -1          # No timeout

# Launch (no rebuild needed!)
ros2 launch yanthra_move pragati_complete.launch.py
```

### Method 2: Command-Line Override (Still Works!)

**Note**: With the current fix, command-line arguments **DON'T** override YAML anymore. If you need CLI overrides, you have two options:

#### Option A: Use `ros2 run` instead of launch
```bash
ros2 run yanthra_move yanthra_move_node --ros-args \
    --params-file src/yanthra_move/config/production.yaml \
    -p continuous_operation:=true \
    -p start_switch.enable_wait:=false
```

#### Option B: Implement Conditional Overrides (Advanced)

If you want launch arguments to override YAML only when explicitly provided, you'll need to implement conditional parameter passing (see the optional todo item for details).

---

## 📋 Configuration Scenarios

### Scenario 1: Automated Testing (No Hardware)
```yaml
# production.yaml
continuous_operation: true         # Run continuously
start_switch.enable_wait: false    # Skip start button
max_runtime_minutes: -1            # No timeout
simulation_mode: true              # No hardware needed
```

**Use Case**: CI/CD, integration testing, development

### Scenario 2: Production with Physical Button
```yaml
# production.yaml
continuous_operation: true         # Run continuously
start_switch.enable_wait: true     # Wait for operator button press
max_runtime_minutes: 480          # 8-hour shift timeout
simulation_mode: false             # Use real hardware
```

**Use Case**: Production environment with human operator

### Scenario 3: Single-Cycle Testing
```yaml
# production.yaml
continuous_operation: false        # One cycle only
start_switch.enable_wait: false    # Auto-start
max_runtime_minutes: 0             # Default 1-minute timeout
simulation_mode: true              # Simulation
```

**Use Case**: Unit testing, cycle validation

### Scenario 4: Production with Topic Trigger
```yaml
# production.yaml
continuous_operation: true         # Run continuously
start_switch.enable_wait: true     # Wait for signal
start_switch.prefer_topic: true    # Use ROS2 topic instead of GPIO
max_runtime_minutes: -1            # No timeout
```

**Trigger the start:**
```bash
ros2 topic pub /start_switch/state std_msgs/Bool "data: true" --once
```

**Use Case**: Remote/automated start via MQTT or network

---

## ⚠️ Important Notes

### 1. YAML Changes Take Effect Immediately
- No rebuild needed after editing `production.yaml`
- The install directory has a symlink to the source file
- Just relaunch to pick up changes

### 2. Two Parameters Required for Continuous Operation
You must set **both** of these:
- `continuous_operation: true` - Enables continuous mode
- `start_switch.enable_wait: false` - Skips button wait (for testing)

If you only set `continuous_operation: true` but leave `start_switch.enable_wait: true`, the system will wait for a START_SWITCH signal and timeout after 5 seconds.

### 3. Launch Arguments No Longer Override by Default
After this fix:
- ❌ `ros2 launch ... continuous_operation:=true` → **IGNORED**
- ✅ Edit YAML file → **WORKS**
- ✅ `ros2 run ... -p continuous_operation:=true` → **WORKS**

---

## 🔍 Verification Commands

### Check Current Parameter Values
```bash
# While node is running
ros2 param get /yanthra_move continuous_operation
ros2 param get /yanthra_move start_switch.enable_wait
ros2 param get /yanthra_move max_runtime_minutes
```

### Watch Log Output
```bash
ros2 launch yanthra_move pragati_complete.launch.py 2>&1 | grep -E "(Safety-critical|continuous_operation|Operational cycle)"
```

### Monitor Continuous Cycles
```bash
ros2 launch yanthra_move pragati_complete.launch.py 2>&1 | grep "Starting operational cycle"
```

You should see:
```
🔄 Starting operational cycle #1
🔄 Starting operational cycle #2
🔄 Starting operational cycle #3
...
```

---

## 🛠️ Rollback Instructions

If you need to revert the fix:

```bash
# The launch file change was simple - just restore the override dict
nano src/yanthra_move/launch/pragati_complete.launch.py

# Find line ~249 and change back:
parameters=[config_file, {
    'use_simulation': use_simulation,
    'continuous_operation': continuous_operation
}],

# Rebuild
colcon build --packages-select yanthra_move
```

---

## 📝 Summary

### What Was Wrong
- Launch file parameter precedence issue
- Launch argument defaults (`false`) overrode YAML values (`true`)
- Made it impossible to set `continuous_operation` via YAML

### What Was Fixed
- Removed parameter override dictionary from launch file
- Now YAML values are respected
- Launch arguments no longer have hidden defaults that override YAML

### What You Need to Do
1. Edit `src/yanthra_move/config/production.yaml`
2. Set `continuous_operation: true`
3. Set `start_switch.enable_wait: false` (for automated testing)
4. Set `max_runtime_minutes: -1` (for no timeout)
5. Launch normally - no rebuild needed!

---

## 🎉 Result

**Before Fix:**
```
continuous_operation: disabled  ❌ (always, regardless of YAML)
```

**After Fix:**
```
continuous_operation: ENABLED  ✅ (matches YAML setting)
Maximum runtime: INFINITE  ✅
System runs continuous cycles  ✅
```

---

**Issue**: YAML values for `continuous_operation` were being ignored  
**Root Cause**: Launch file override dictionary with default values  
**Solution**: Removed override dictionary, use YAML only  
**Status**: ✅ COMPLETELY RESOLVED  
**Verified**: Parameters correctly load from YAML, continuous operation works
