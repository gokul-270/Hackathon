# START_SWITCH Timeout Guide

## Overview

The `start_switch.timeout_sec` parameter controls how long the system waits for a START signal before timing out.

**NEW FEATURE**: You can now set it to `-1` for **infinite wait** (perfect for production!)

---

## Parameter Values

| Value | Behavior | Use Case |
|-------|----------|----------|
| `-1` | **Infinite wait** - never timeout | ✅ Production with operator button |
| `0` | Invalid (will be treated as 1 second) | ❌ Don't use |
| `> 0` | Timeout after specified seconds | ✅ Automated testing, development |

---

## Configuration Examples

### 🏭 Production: Infinite Wait for Operator

**Best for:** Real robot in the field with human operator

```yaml
# production.yaml
continuous_operation: true
start_switch.enable_wait: true       # Wait for button
start_switch.timeout_sec: -1         # WAIT FOREVER! ⏳∞
start_switch.prefer_topic: false     # Use physical GPIO button
max_runtime_minutes: 480             # 8 hour shift
simulation_mode: false
```

**Behavior:**
```
[INFO] Starting main operation loop
[INFO] ⏳ Waiting for START_SWITCH signal...
[INFO] ⏳ Waiting infinitely for START_SWITCH (timeout disabled with -1)
(waits here indefinitely until operator presses button)
[INFO] 🎯 START_SWITCH GPIO pressed! Beginning cotton detection
[INFO] 🔄 Starting operational cycle #1
```

**Operator workflow:**
1. Robot powers on and initializes
2. System waits patiently for operator
3. Operator can take their time getting ready
4. When ready, operator presses START button
5. Robot immediately begins picking
6. **No timeout worries!**

---

### 🧪 Testing: Short Timeout

**Best for:** Automated testing, CI/CD, development

```yaml
# production.yaml
continuous_operation: true
start_switch.enable_wait: true       # Wait for signal
start_switch.timeout_sec: 10.0       # Timeout after 10 seconds
start_switch.prefer_topic: true      # Use ROS2 topic
max_runtime_minutes: -1
simulation_mode: true
```

**Behavior:**
```
[INFO] ⏳ Waiting for START_SWITCH signal...
[INFO] ⏳ Will timeout after 10.0 seconds if no START_SWITCH signal
(waits up to 10 seconds)
[ERROR] ⏰ START_SWITCH timeout after 10.0 seconds! Entering safe idle state.
```

**Use case:**
- Catch configuration errors quickly
- Prevent hanging in CI/CD pipelines
- Development debugging

---

### ⚡ Development: Skip Wait Entirely

**Best for:** Rapid development iteration

```yaml
# production.yaml
continuous_operation: true
start_switch.enable_wait: false      # Skip the wait entirely!
start_switch.timeout_sec: 5.0        # Doesn't matter (not used)
max_runtime_minutes: -1
simulation_mode: true
```

**Behavior:**
```
[INFO] ⏳ Waiting for START_SWITCH signal...
[INFO] 💡 START_SWITCH wait disabled - proceeding directly to operation
[INFO] 🔄 Starting operational cycle #1
(no waiting at all!)
```

---

### 🌐 Remote Trigger: Moderate Timeout

**Best for:** Remote operation via MQTT/network

```yaml
# production.yaml
continuous_operation: true
start_switch.enable_wait: true       # Wait for signal
start_switch.timeout_sec: 120.0      # 2 minutes (network delays)
start_switch.prefer_topic: true      # Use ROS2 topic
max_runtime_minutes: -1
simulation_mode: false
```

**Trigger remotely:**
```bash
ros2 topic pub /start_switch/state std_msgs/Bool "data: true" --once
```

---

## Decision Matrix

### When to use each value:

#### Use `-1` (Infinite Wait):
- ✅ Production environment with human operator
- ✅ Physical START button on robot
- ✅ Operator may need time to prepare
- ✅ Safety-critical: won't start without confirmation
- ✅ No network/automation - pure manual control

#### Use `30-300 seconds`:
- ✅ Remote/automated triggering
- ✅ Network might have delays
- ✅ Want some timeout protection
- ✅ Operator should respond within timeframe

#### Use `5-15 seconds`:
- ✅ Automated testing
- ✅ CI/CD pipelines
- ✅ Development debugging
- ✅ Want to catch misconfigurations quickly

#### Use `enable_wait: false`:
- ✅ Pure automated testing
- ✅ No operator, no remote trigger
- ✅ Simulation mode
- ✅ Rapid development iteration

---

## Common Scenarios

### Scenario 1: Field Robot - Morning Startup
```yaml
continuous_operation: true
start_switch.enable_wait: true
start_switch.timeout_sec: -1         # ← Infinite wait!
start_switch.prefer_topic: false
max_runtime_minutes: 480
```

**Timeline:**
- 7:00 AM: Robot powers on
- 7:05 AM: System ready, waiting for operator
- 7:30 AM: Operator arrives, performs inspection
- 7:45 AM: Operator presses START button
- 7:45 AM - 3:45 PM: Robot picks cotton (8 hours)
- **No timeout issues!**

---

### Scenario 2: Automated Nightly Test
```yaml
continuous_operation: true
start_switch.enable_wait: true
start_switch.timeout_sec: 60.0       # ← 1 minute timeout
start_switch.prefer_topic: true
max_runtime_minutes: 30
```

**Timeline:**
- 2:00 AM: Test script starts robot
- 2:00 AM: System initializes
- 2:01 AM: Test script sends START topic
- 2:01 AM - 2:31 AM: Robot runs test
- If START topic fails: timeout at 2:02 AM (safety!)

---

### Scenario 3: Development - Rapid Testing
```yaml
continuous_operation: false          # Single cycle
start_switch.enable_wait: false      # ← Skip wait!
max_runtime_minutes: 0
```

**Timeline:**
- Start node → Immediately runs → Exits
- Perfect for testing fixes

---

## Implementation Details

### How It Works

**Code logic:**
```cpp
if (start_switch_timeout_sec < 0) {
    // Infinite wait - never timeout
    while (!button_pressed) {
        check_button();
        check_shutdown_signal();
        // Loop forever until button or shutdown
    }
} else {
    // Timed wait - timeout after specified seconds
    while (!button_pressed && !timeout) {
        check_button();
        check_shutdown_signal();
        check_timeout();
    }
}
```

**Safety features:**
- ✅ Shutdown signal (Ctrl+C) always works, even with infinite wait
- ✅ Emergency stop always works
- ✅ System remains responsive during wait
- ✅ ROS2 callbacks processed during wait

---

## Upgrading from Previous Version

**Old behavior (before this feature):**
- Timeout was always enforced
- Production deployments needed very long timeouts
- No true "wait forever" option

**New behavior (with `-1` support):**
- Can truly wait forever for operator
- More intuitive for production use
- Backwards compatible (positive values work same as before)

**Migration:**
```yaml
# Old way (workaround with large value)
start_switch.timeout_sec: 86400.0    # 24 hours (hacky!)

# New way (proper infinite wait)
start_switch.timeout_sec: -1         # Infinite (clean!)
```

---

## Testing the Feature

### Test Infinite Wait:
```yaml
# Config
start_switch.enable_wait: true
start_switch.timeout_sec: -1
```

```bash
# Terminal 1: Launch robot
ros2 launch yanthra_move pragati_complete.launch.py

# Watch logs - should show:
# "⏳ Waiting infinitely for START_SWITCH (timeout disabled with -1)"

# Terminal 2: Send trigger (after any delay)
ros2 topic pub /start_switch/state std_msgs/Bool "data: true" --once

# Robot should start immediately!
```

### Test Timeout:
```yaml
# Config
start_switch.enable_wait: true
start_switch.timeout_sec: 10.0
```

```bash
# Launch and wait - should timeout after 10 seconds
ros2 launch yanthra_move pragati_complete.launch.py

# Watch logs - should show timeout error after 10 seconds
```

---

## Quick Reference

| What You Want | Configuration |
|---------------|---------------|
| **Operator button, wait forever** | `enable_wait: true`, `timeout_sec: -1` |
| **Operator button, 5 min max** | `enable_wait: true`, `timeout_sec: 300` |
| **Remote trigger, 2 min max** | `enable_wait: true`, `timeout_sec: 120`, `prefer_topic: true` |
| **Automated test, 10 sec max** | `enable_wait: true`, `timeout_sec: 10` |
| **No wait, auto-start** | `enable_wait: false` |

---

## Troubleshooting

### "System times out too quickly in production"
✅ **Solution**: Set `timeout_sec: -1` for infinite wait

### "System hangs forever in testing"
✅ **Solution**: Use a reasonable timeout like `10.0` or `60.0` seconds

### "I want different timeouts for different environments"
✅ **Solution**: Create separate YAML config files:
- `production.yaml` → `timeout_sec: -1`
- `testing.yaml` → `timeout_sec: 10.0`

### "Infinite wait, but robot still stops"
✅ **Check**: Are you hitting the `max_runtime_minutes` timeout instead?
✅ **Solution**: Set `max_runtime_minutes: -1` for no runtime limit

---

**Feature Added**: 2025-10-06  
**Backwards Compatible**: Yes  
**Recommended for Production**: `start_switch.timeout_sec: -1`
