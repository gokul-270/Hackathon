# Continuous Operation Guide

**Last Updated:** October 21, 2025  
**Consolidated From:** QUICK_START_continuous_operation.md, FINAL_FIX_continuous_operation.md

---

## TL;DR - Quick Start

```bash
# 1. Edit the config
nano src/yanthra_move/config/production.yaml

# 2. Change these THREE lines:
#    Line 8:  continuous_operation: true
#    Line 14: max_runtime_minutes: -1
#    Line 18: start_switch.enable_wait: false

# 3. Launch (no rebuild needed!)
ros2 launch yanthra_move pragati_complete.launch.py

# 4. Watch it run continuous cycles!
```

---

## What Each Setting Does

| Parameter | Value | What It Does |
|-----------|-------|--------------|
| `continuous_operation` | `true` | Keeps running cycles instead of stopping after one |
| `max_runtime_minutes` | `-1` | No timeout (infinite operation) |
| `start_switch.enable_wait` | `false` | Skip waiting for START button (auto-start) |

---

## Configuration Scenarios

### For Testing (No Hardware)
```yaml
continuous_operation: true
start_switch.enable_wait: false
max_runtime_minutes: -1
simulation_mode: true
```

### For Production (With Physical Button)
```yaml
continuous_operation: true
start_switch.enable_wait: true    # Wait for button press
max_runtime_minutes: 480         # 8 hours
simulation_mode: false
```

### For Single Test Cycle
```yaml
continuous_operation: false      # One cycle only
start_switch.enable_wait: false
max_runtime_minutes: 0
```

---

## Technical Background: The Launch File Fix

### Problem: YAML Values Were Being Overridden

The launch file was overriding YAML values with launch argument defaults.

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

In ROS2, when you pass parameters like `[config_file, {dict}]`, the dictionary **overrides** values from the config file.

### Solution: Parameter Precedence Fixed

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
- Removed the override dictionary
- Now **only** the YAML file is used for parameters
- Launch arguments no longer override YAML values by default

---

## Usage Methods

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

### Method 2: Command-Line Override

**Note**: With the current fix, launch arguments don't override YAML. Use `ros2 run` for CLI overrides:

```bash
ros2 run yanthra_move yanthra_move_node --ros-args \
    --params-file src/yanthra_move/config/production.yaml \
    -p continuous_operation:=true \
    -p start_switch.enable_wait:=false
```

---

## Production Scenarios

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

## Troubleshooting

### "It still stops after 5 seconds!"
✅ **Fix**: Set `start_switch.enable_wait: false`

The system is waiting for a START_SWITCH signal and timing out. Disable the wait for automated testing.

### "It says continuous_operation: disabled"
✅ **Fix**: The launch file was fixed. If you're using an old build:
```bash
colcon build --packages-select yanthra_move
source install/setup.bash
```

### "I want it to run for exactly 2 hours"
✅ **Fix**: Set `max_runtime_minutes: 120`

### "Launch arguments don't work anymore"
✅ **Expected**: After the fix, launch arguments don't override YAML by default.
- ❌ `ros2 launch ... continuous_operation:=true` → **IGNORED**
- ✅ Edit YAML file → **WORKS**
- ✅ `ros2 run ... -p continuous_operation:=true` → **WORKS**

---

## Verification Commands

```bash
# Check parameters while running
ros2 param get /yanthra_move continuous_operation  # Should be: true
ros2 param get /yanthra_move start_switch.enable_wait  # Should be: false

# Watch the cycles
ros2 launch ... 2>&1 | grep "Starting operational cycle"
# Should show: #1, #2, #3, #4, ...
```

---

## Important Notes

### 1. YAML Changes Take Effect Immediately
- No rebuild needed after editing `production.yaml`
- The install directory has a symlink to the source file
- Just relaunch to pick up changes

### 2. Two Parameters Required for Continuous Operation
You must set **both** of these for fully automated continuous operation:
- `continuous_operation: true` - Enables continuous mode
- `start_switch.enable_wait: false` - Skips button wait (for testing)

If you only set `continuous_operation: true` but leave `start_switch.enable_wait: true`, the system will wait for a START_SWITCH signal.

### 3. Files Modified
- ✅ `src/yanthra_move/launch/pragati_complete.launch.py` - Fixed parameter precedence
- ✅ `src/yanthra_move/config/production.yaml` - Your settings go here

---

## Related Guides

- **START_SWITCH_TIMEOUT_GUIDE.md** - Configure timeout behavior including infinite wait (`-1`)
- **SIMULATION_MODE_GUIDE.md** - Running without hardware
- **TROUBLESHOOTING.md** - General troubleshooting procedures

---

**Status:** ✅ Fixed and validated (October 6, 2025)  
**Consolidated:** October 21, 2025  
**Archival Note:** Original quick start and detailed fix guides archived to `docs/archive/2025-10-phase2/`
