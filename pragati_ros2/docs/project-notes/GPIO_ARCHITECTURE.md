# Pragati ROS2 - GPIO Architecture & Consolidation Guide
**Last Updated**: 2025-11-17  
**Status**: Current implementation working, consolidation recommended for maintainability

---

## Overview

The Pragati ROS2 workspace currently uses GPIO in **3 separate packages** with **2 different libraries**. While functionally working, this creates potential for pin conflicts and maintenance challenges.

**Purpose of this document**:
- Document current GPIO usage across the workspace
- Explain why consolidation is recommended (but not urgent)
- Provide migration path if/when team decides to consolidate

---

## Current GPIO Usage

### Summary Table

| Package | Library | Language | Purpose | Pin Usage |
|---------|---------|----------|---------|-----------|
| **motor_control_ros2** | pigpiod_if2 | C++ | Motor control, encoders, sensors | Multiple GPIO pins |
| **yanthra_move** | pigpio.h (headers only) | C++ | ❓ Unclear - no GPIO code found | None (legacy includes?) |
| **vehicle_control** | RPi.GPIO | Python | Vehicle-level GPIO control | TBD (analyze code) |

---

## Package-by-Package Analysis

### 1. motor_control_ros2 (Primary GPIO Interface)

**Library**: `pigpiod_if2`  
**Implementation**: C++ via pigpio daemon  
**Status**: ✅ Production-ready, actively used

**Usage**:
```cpp
#include <pigpiod_if2.h>

// Daemon-based GPIO (requires pigpiod running)
int pi = pigpio_start(NULL, NULL);
gpio_write(pi, pin, value);
gpio_read(pi, pin);
```

**Advantages**:
- ✅ **Non-root access** - Runs as regular user (pigpiod handles root)
- ✅ **Network-capable** - Can control GPIO over network
- ✅ **Thread-safe** - Multiple clients can connect
- ✅ **Real-time safe** - Daemon runs with high priority
- ✅ **Already integrated** - Working production code

**CMake Configuration**:
```cmake
find_library(PIGPIO_IF2_LIBRARY NAMES pigpiod_if2)
target_link_libraries(motor_control_node ${PIGPIO_IF2_LIBRARY})
```

**Dependencies**:
```bash
sudo apt-get install pigpio libpigpio-dev
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

---

### 2. yanthra_move (Legacy Includes Only?)

**Library**: `pigpio.h` (direct GPIO, NOT daemon)  
**Status**: ⚠️ Included but apparently unused

**Includes Found**:
```cpp
#include <pigpio.h>  // Found in headers, but no GPIO code?
```

**Analysis**:
```bash
# Search for actual pigpio usage in yanthra_move
grep -r "gpioInitialise\|gpioWrite\|gpioRead" src/yanthra_move/
# Result: No actual GPIO function calls found
```

**Hypothesis**: 
- Headers included for future GPIO features?
- Legacy code from earlier implementation?
- Copy-paste from motor_control?

**Recommendation**: 
- ✅ **Remove pigpio includes** from yanthra_move if not used
- ✅ **Use motor_control services** for any GPIO needs
- ✅ **Avoid direct GPIO access** from yanthra_move

**Rationale**:
- yanthra_move is high-level motion planning
- GPIO should be abstracted through motor_control services
- Separation of concerns = cleaner architecture

---

### 3. vehicle_control (Python GPIO)

**Library**: `RPi.GPIO`  
**Language**: Python  
**Status**: ✅ Standard Python GPIO library

**Typical Usage Pattern**:
```python
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setup(pin, GPIO.OUT)
GPIO.output(pin, GPIO.HIGH)
```

**Advantages**:
- ✅ **Python-native** - No C++ interop needed
- ✅ **Simple API** - Easy to use for vehicle-level logic
- ✅ **Well-documented** - Standard library

**Disadvantages**:
- ⚠️ **Requires root** - Must run with sudo (or pigpio overlay)
- ⚠️ **No coordination** with pigpiod - Can conflict with motor_control

**Recommendation**: 
- ✅ **Keep RPi.GPIO for Python code** - Don't force C++ interop
- ⚠️ **Coordinate pin assignments** - Avoid overlap with motor_control
- ✅ **Consider ROS services** - Call motor_control for shared pins

---

## GPIO Library Comparison

### pigpiod_if2 (C++ Daemon Client) vs pigpio (C++ Direct)

| Feature | pigpiod_if2 (motor_control) | pigpio.h (yanthra_move?) |
|---------|----------------------------|--------------------------|
| **Root required** | ❌ NO (daemon handles it) | ✅ YES (gpioInitialise needs root) |
| **Multi-process safe** | ✅ YES | ❌ NO |
| **Network GPIO** | ✅ YES | ❌ NO |
| **Performance** | ~10μs latency | ~1μs latency |
| **Setup complexity** | Medium (daemon) | Low (direct) |
| **Production ready** | ✅ Best choice | ⚠️ Use for single-process only |

**Why motor_control uses pigpiod_if2**:
- ROS2 nodes don't run as root (security)
- Multiple nodes may need GPIO access
- Network GPIO useful for debugging

---

## Potential Pin Conflicts

### Risk Assessment

**Current Risk**: ⚠️ **MEDIUM** - No coordination mechanism between packages

**Scenarios**:
1. **motor_control + vehicle_control use same pin**
   - Result: Undefined behavior, possible hardware damage
   - Mitigation: Manual pin assignment coordination

2. **yanthra_move calls GPIO directly** (if implemented)
   - Result: Conflicts with motor_control daemon
   - Mitigation: Remove direct GPIO access from yanthra_move

3. **Python RPi.GPIO + pigpiod both access pin**
   - Result: Race conditions, pin state corruption
   - Mitigation: Exclusive pin ownership documentation

---

## Recommended Architecture

### Option A: Status Quo (Current - Working)

```
┌─────────────────┐     ┌─────────────────┐
│ motor_control   │     │ vehicle_control │
│ (pigpiod_if2)   │     │ (RPi.GPIO)      │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
    GPIO pins A              GPIO pins B
     (coordinated manually)
```

**Pros**:
- ✅ Already working
- ✅ No migration needed
- ✅ Python stays in Python, C++ stays in C++

**Cons**:
- ⚠️ Manual pin coordination required
- ⚠️ No conflict detection
- ⚠️ Duplicate GPIO logic

---

### Option B: Centralized GPIO (Recommended Long-term)

```
┌─────────────────┐     ┌─────────────────┐
│ yanthra_move    │     │ vehicle_control │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │ ROS services          │ ROS services
         ▼                       ▼
    ┌────────────────────────────────┐
    │     motor_control_ros2         │
    │      (pigpiod_if2)             │
    │  - GPIO allocation tracking    │
    │  - Pin conflict detection      │
    │  - Unified GPIO services       │
    └───────────────┬────────────────┘
                    │
                    ▼
              All GPIO pins
```

**Pros**:
- ✅ Single source of truth for GPIO
- ✅ Automatic conflict detection
- ✅ Centralized pin mapping
- ✅ Easier debugging (all GPIO in one place)

**Cons**:
- ⚠️ Requires service definitions
- ⚠️ Migration effort for vehicle_control
- ⚠️ Adds latency (ROS service calls)

---

### Option C: Hybrid (Pragmatic Middle Ground)

```
┌─────────────────┐     ┌─────────────────┐
│ yanthra_move    │     │ vehicle_control │
│ (no GPIO)       │     │ (RPi.GPIO)      │
└─────────────────┘     └────────┬────────┘
         │                       │
         │ ROS services          │ Direct GPIO
         ▼                       │ (non-overlapping pins)
    ┌────────────────┐           │
    │ motor_control  │           │
    │ (pigpiod_if2)  │           │
    └────────┬───────┘           │
             │                   │
             ▼                   ▼
        GPIO pins A         GPIO pins B
         (motors)          (vehicle control)
```

**Pros**:
- ✅ No migration needed for vehicle_control
- ✅ Clear separation: motors vs vehicle
- ✅ Python code stays simple
- ✅ Minimal changes required

**Cons**:
- ⚠️ Still requires manual pin coordination
- ⚠️ Two GPIO paradigms to maintain

**Verdict**: **This is the recommended approach for now**

---

## Pin Allocation Strategy

### Recommended Pin Assignment (Example)

| Pin Range | Owner | Purpose | Library |
|-----------|-------|---------|---------|
| **GPIO 2-3** | motor_control | I2C (reserved) | pigpiod_if2 |
| **GPIO 4-11** | motor_control | Motor control, encoders | pigpiod_if2 |
| **GPIO 12-19** | motor_control | Sensors, limit switches | pigpiod_if2 |
| **GPIO 20-27** | vehicle_control | Vehicle-level control | RPi.GPIO |

**How to Implement**:
1. Create `docs/PIN_MAPPING.md` with allocation table
2. Add pin conflict checks to motor_control (optional)
3. Document in each package README which pins are used

---

## Migration Guide (If Consolidating)

### Step 1: Audit Current Pin Usage

```bash
# Search for GPIO pin assignments
grep -r "GPIO\|gpio\|pigpio" src/ --include="*.cpp" --include="*.py"

# Check motor_control configuration
cat src/motor_control_ros2/config/motor_config.yaml

# Check vehicle_control code
cat src/vehicle_control/vehicle_control/*.py
```

### Step 2: Document Pin Assignments

Create `docs/PIN_MAPPING.md`:
```markdown
# GPIO Pin Allocation

## Motor Control (GPIO 4-19)
- GPIO 4: Left motor PWM
- GPIO 5: Left motor direction
- ...

## Vehicle Control (GPIO 20-27)
- GPIO 20: Brake signal
- GPIO 21: Emergency stop
- ...
```

### Step 3: Add GPIO Services to motor_control

```cpp
// Add to motor_control_ros2/srv/
GPIOControl.srv:
---
uint8 pin
bool value
---
bool success
string message
```

### Step 4: Migrate Python Code (If Needed)

```python
# Before (direct GPIO)
import RPi.GPIO as GPIO
GPIO.output(20, GPIO.HIGH)

# After (ROS service)
from motor_control_ros2.srv import GPIOControl
gpio_client = node.create_client(GPIOControl, '/gpio/control')
gpio_client.call(GPIOControl.Request(pin=20, value=True))
```

---

## Action Items

### Immediate (Do Now)

1. ✅ **Document current pin usage** in each package README
2. ✅ **Create PIN_MAPPING.md** with allocation table
3. ✅ **Remove unused pigpio includes** from yanthra_move (if confirmed unused)

### Short-term (Next Sprint)

4. ⚠️ **Add pin conflict detection** to motor_control (optional)
5. ⚠️ **Standardize GPIO initialization** error handling
6. ⚠️ **Document RPi.GPIO + pigpiod coexistence** rules

### Long-term (Future Consideration)

7. 🔮 **Evaluate full GPIO consolidation** if conflicts occur
8. 🔮 **Implement centralized GPIO service** if needed
9. 🔮 **Add GPIO resource locking** for multi-node safety

---

## FAQ

### Q: Should we consolidate GPIO now?

**A**: **No, not urgent**. Current architecture works. Consolidate only if:
- Pin conflicts start occurring
- Team wants unified GPIO management
- Adding new GPIO-heavy features

### Q: Why does yanthra_move include pigpio.h?

**A**: Unclear - no actual GPIO code found. Likely legacy includes or preparation for future features. Safe to remove if unused.

### Q: Can RPi.GPIO and pigpiod coexist?

**A**: **Yes, with care**:
- Different pins: ✅ Safe
- Same pins: ❌ Conflicts
- Coordination required through documentation

### Q: Which library should new code use?

**A**: 
- **C++ code**: Use motor_control services (or pigpiod_if2 if new package)
- **Python code**: RPi.GPIO is fine (simpler for Python)
- **High-performance**: Direct pigpiod_if2 in C++

### Q: Do we need root access for GPIO?

**A**: 
- **pigpiod_if2**: ❌ No (daemon runs as root)
- **pigpio.h**: ✅ Yes (direct hardware access)
- **RPi.GPIO**: ✅ Yes (unless using pigpio overlay)

**Solution**: Use pigpiod for all C++ GPIO

---

## Summary

### Current State
- ✅ **motor_control**: Production-ready with pigpiod_if2
- ⚠️ **yanthra_move**: Includes pigpio but doesn't use it (remove?)
- ✅ **vehicle_control**: Python RPi.GPIO (keep as-is)

### Recommended Actions
1. **Keep current architecture** (works fine)
2. **Document pin allocations** (prevent conflicts)
3. **Remove unused includes** from yanthra_move
4. **Consolidate only if needed** (future decision)

### Key Principles
- ✅ **motor_control owns hardware GPIO** via pigpiod
- ✅ **yanthra_move uses ROS services** (no direct GPIO)
- ✅ **vehicle_control can use RPi.GPIO** (non-overlapping pins)
- ✅ **Manual coordination** via documentation (for now)

---

**Document prepared**: 2025-11-17  
**Architecture status**: ✅ Functional, consolidation optional  
**Next review**: If GPIO conflicts reported
