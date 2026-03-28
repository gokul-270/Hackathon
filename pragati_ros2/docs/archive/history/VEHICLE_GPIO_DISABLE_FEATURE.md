# Vehicle Control GPIO Disable Feature

**Date:** December 10, 2025  
**Purpose:** Safe motor testing without GPIO interference  
**Status:** ✅ Implemented

---

## Problem

During initial motor testing on vehicle hardware:
- GPIO pin assignments may not be verified
- Don't want GPIO operations interfering with motor control
- Need to test motors in isolation first
- GPIO manager initialization might fail without proper setup

---

## Solution

Added `enable_gpio` configuration parameter to safely disable GPIO functionality.

### Configuration Parameter

**File:** `src/vehicle_control/config/production.yaml`

```yaml
vehicle_control:
  ros__parameters:
    # GPIO Configuration
    enable_gpio: false  # CRITICAL: Disable GPIO during initial motor testing
                        # Set to true only after pin assignments are verified
                        # When false: GPIO manager is not initialized (safe)
```

**Default:** `false` (GPIO disabled by default for safety)

---

## Behavior

### When `enable_gpio: false` (Default)

✅ **Safe for Motor Testing:**
- GPIO manager is NOT initialized
- No GPIO pin access attempted
- All GPIO-dependent features gracefully skip
- Motors can be tested without GPIO interference
- Status LEDs commands ignored (no errors)
- Switch inputs unavailable (expected)

**Startup Log:**
```
[WARN] ⚠️  GPIO DISABLED in config (enable_gpio=false)
       This is SAFE for initial motor testing
       Set enable_gpio=true after verifying pin assignments
```

### When `enable_gpio: true`

✅ **Full Functionality:**
- GPIO manager initialized
- All hardware switches operational
- Status LEDs functional
- E-STOP, mode switches, etc. work

**Startup Log:**
```
[INFO] 🔌 GPIO enabled - initializing GPIO manager
[INFO] ✅ GPIO manager initialized
```

---

## Code Changes

### 1. YAML Configuration
Added `enable_gpio` parameter with safety-first default:
```yaml
enable_gpio: false  # Default: disabled for safety
```

### 2. Node Initialization
Conditional GPIO manager creation:
```python
def _initialize_hardware(self):
    enable_gpio = self.config.get('enable_gpio', False)
    if enable_gpio:
        self.logger.info("🔌 GPIO enabled - initializing GPIO manager")
        self.gpio_manager = GPIOManager()
        self.gpio_manager.initialize()
    else:
        self.logger.warn("⚠️  GPIO DISABLED in config")
        self.gpio_manager = None
```

### 3. Safe GPIO Usage
All GPIO manager calls check for None:
```python
# LED control
if self.gpio_manager:
    self.gpio_manager.show_status_led("OK")

# GPIO inputs
if self.gpio_processor is None:
    return  # Skip GPIO processing

# Cleanup
if self.gpio_manager is not None:
    self.gpio_manager.cleanup()
```

---

## Usage Workflow

### Phase 1: Initial Motor Testing (Current)
```yaml
# config/production.yaml
enable_gpio: false  # ✅ Safe mode
```

**Test:**
1. Launch vehicle control node
2. Verify GPIO disabled warning appears
3. Test motors via services/topics
4. No GPIO interference

### Phase 2: Verify GPIO Pins
After motors working correctly:
1. Document actual GPIO pin assignments
2. Update `production.yaml` with correct pins
3. Verify pigpiod service running
4. Test GPIO functionality manually

### Phase 3: Enable GPIO
```yaml
# config/production.yaml
enable_gpio: true  # ✅ Enable after verification
```

**Test:**
1. Launch vehicle control node
2. Verify GPIO initialized successfully
3. Test switches, LEDs, E-STOP
4. Confirm no motor interference

---

## Files Modified

1. **`src/vehicle_control/config/production.yaml`**
   - Added `enable_gpio: false` parameter
   - Added safety comments

2. **`src/vehicle_control/integration/vehicle_control_node.py`**
   - Conditional GPIO initialization
   - None checks before all GPIO operations
   - Added warning logs for disabled mode
   - Default config includes `enable_gpio: False`

---

## Safety Features

✅ **Default Disabled:** GPIO off by default prevents accidental interference  
✅ **Graceful Degradation:** Node runs normally without GPIO  
✅ **Clear Warnings:** Startup logs show GPIO status  
✅ **No Crashes:** All GPIO calls check for None  
✅ **Motor Isolation:** Motors testable without GPIO setup

---

## Testing Checklist

- [x] Node starts with `enable_gpio: false`
- [x] Warning log appears about GPIO disabled
- [x] Motor services work normally
- [x] No GPIO-related errors or crashes
- [x] LED commands silently ignored
- [ ] Node starts with `enable_gpio: true` (after pin verification)
- [ ] GPIO manager initializes successfully
- [ ] Switches and LEDs functional

---

## Field Trial Impact

**December Testing (Motors Only):**
- ✅ Keep `enable_gpio: false`
- Focus on motor validation
- No GPIO pin concerns

**January Field Trial:**
- Verify GPIO pins with hardware team
- Test GPIO functionality separately
- Enable only when fully validated
- Document pin assignments

---

## Recommendations

1. **Current Status:** Leave GPIO disabled until pin verification complete
2. **Documentation:** Update pin assignment documentation before enabling
3. **Testing:** Test GPIO on bench before field deployment
4. **Safety:** Keep E-STOP testing separate from motor testing

---

**Status:** ✅ **Ready for motor testing with GPIO safely disabled**
