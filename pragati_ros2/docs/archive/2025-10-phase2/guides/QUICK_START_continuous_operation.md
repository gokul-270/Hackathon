# Quick Start: Enable Continuous Operation

## TL;DR - Just Make It Work!

```bash
# 1. Edit the config
nano src/yanthra_move/config/production.yaml

# 2. Change these THREE lines:
#    Line 8:  continuous_operation: true
#    Line 14: max_runtime_minutes: -1
#    Line 18: start_switch.enable_wait: false

# 3. Launch (no rebuild!)
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

## Common Scenarios

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

## Troubleshooting

### "It still stops after 5 seconds!"
✅ **Fix**: Set `start_switch.enable_wait: false`

### "It says continuous_operation: disabled"
✅ **Fix**: The launch file was fixed. Rebuild:
```bash
colcon build --packages-select yanthra_move
source install/setup.bash
```

### "I want it to run for exactly 2 hours"
✅ **Fix**: Set `max_runtime_minutes: 120`

---

## Files You Modified

- ✅ `src/yanthra_move/launch/pragati_complete.launch.py` - Fixed parameter precedence
- ✅ `src/yanthra_move/config/production.yaml` - Your settings go here

---

## Verify It's Working

```bash
# Check parameters while running
ros2 param get /yanthra_move continuous_operation  # Should be: true
ros2 param get /yanthra_move start_switch.enable_wait  # Should be: false

# Watch the cycles
ros2 launch ... 2>&1 | grep "Starting operational cycle"
# Should show: #1, #2, #3, #4, ...
```

---

**Need More Details?** See `FINAL_FIX_continuous_operation.md`
