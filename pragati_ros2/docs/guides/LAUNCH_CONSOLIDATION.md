# Launch File Consolidation (2025-10-21)

## Summary
Simplified launch structure by archiving legacy/duplicate launch files and standardizing on production paths.

## Changes Made

### Cotton Detection (`cotton_detection_ros2`)
**Archived:**
- `cotton_detection_wrapper.launch.py` → `launch/archive/phase1/`
- `cotton_detection.launch.xml` → `launch/archive/phase1/`

**Production (Keep):**
- ✅ `cotton_detection_cpp.launch.py` - **Use this for all deployments**

**Migration:**
```bash
# OLD (Phase 1 Python wrapper - archived)
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py

# NEW (Production C++ node)
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
```

See `src/cotton_detection_ros2/launch/archive/phase1/README.md` for detailed migration guide.

### Vehicle Control (`vehicle_control`)
**Archived:**
- `vehicle_control.launch.py` → `launch/archive/`

**Production (Keep):**
- ✅ `vehicle_control_with_params.launch.py` - **Use this for all deployments**

**Migration:**
```bash
# OLD (inline params - archived)
ros2 launch vehicle_control vehicle_control.launch.py

# NEW (YAML config - more flexible)
ros2 launch vehicle_control vehicle_control_with_params.launch.py
```

See `src/vehicle_control/launch/archive/README.md` for details.

### Motor Control (`motor_control_ros2`)
**No changes** - both launches serve different purposes:
- ✅ `hardware_interface.launch.py` - Production/system launch
- ✅ `mg6010_test.launch.py` - Development/testing utility

---

## Final Launch Structure

### Production Launches (7 files)
| Package | Launch File | Purpose |
|---------|-------------|---------|
| cotton_detection_ros2 | `cotton_detection_cpp.launch.py` | Cotton detection (C++) |
| motor_control_ros2 | `hardware_interface.launch.py` | Motor hardware interface |
| motor_control_ros2 | `mg6010_test.launch.py` | Single motor testing |
| vehicle_control | `vehicle_control_with_params.launch.py` | Vehicle control (YAML config) |
| robot_description | `robot_state_publisher.launch.py` | Robot URDF publishing |
| yanthra_move | `pragati_complete.launch.py` | Complete system |
| yanthra_move | `robot_visualization.launch.py` | RViz visualization |

### Archived (3 files)
- `cotton_detection_wrapper.launch.py` (Phase 1 legacy)
- `cotton_detection.launch.xml` (Legacy XML format)
- `vehicle_control.launch.py` (Inline params, less flexible)

---

## Migration for Test Scripts

### Tests Using Archived Launches

**test_suite/hardware/test_phase0_fixes.sh**
- Status: Legacy test for Phase 0 Python wrapper fixes
- Action: Mark as legacy or update to C++ node
- Quick fix: Script can temporarily restore from archive if needed

**scripts/validation/system/run_table_top_validation.sh**
- Status: Uses wrapper launch for hardware validation
- Action: Update to use C++ node
- Migration: Replace `cotton_detection_wrapper.launch.py` with `cotton_detection_cpp.launch.py`

### Updating Scripts

```bash
# Find all references to archived launches
git grep -l "cotton_detection_wrapper.launch"
git grep -l "cotton_detection.launch.xml"
git grep -l "vehicle_control.launch.py"

# Update references to production launches
# Or add note that script uses legacy archived launch
```

---

## Rationale

**Why Consolidate?**
1. **Clarity**: One clear production path per subsystem
2. **Maintainability**: Fewer files to update, test, document
3. **Performance**: C++ node superior to Phase 1 Python wrapper
4. **Standardization**: YAML configs across all packages
5. **Reduced Confusion**: Users know exactly which launch to use

**Why Archive vs Delete?**
- Legacy test scripts may still reference these
- Temporary fallback if issues found with production launches
- Documentation and migration guides available in archive
- Will be deleted in future release after all migrations complete

---

## Next Steps

1. ✅ Archive legacy launches
2. ✅ Update CMakeLists.txt to exclude archives from install
3. ✅ Add migration documentation in archive directories
4. 🔄 Rebuild and validate remaining launches
5. 📋 Update test scripts referencing archived launches
6. 📋 Update root README and documentation

## Testing

```bash
# Rebuild workspace
colcon build --packages-select cotton_detection_ros2 vehicle_control

# Verify only production launches are installed
find install -name "*.launch.py" | grep -v archive

# Test remaining launches
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py --show-args
ros2 launch vehicle_control vehicle_control_with_params.launch.py --show-args
```
