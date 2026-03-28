# Archived Launch Files - Phase 1 Legacy

**Date Archived:** 2025-10-21  
**Reason:** Launch file consolidation - migrate to production C++ implementation

## Archived Files

### cotton_detection_wrapper.launch.py
**Status:** Phase 1 Legacy (Python wrapper)  
**Use Instead:** `cotton_detection_cpp.launch.py` (production C++ node)

```bash
# OLD (legacy)
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py

# NEW (production)
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
```

**Why Changed:**
- C++ node is production-ready with better performance
- No subprocess/file I/O bottlenecks
- Native DepthAI integration
- Continuous detection vs trigger-based
- See `src/cotton_detection_ros2/README.md` for migration guide

### cotton_detection.launch.xml
**Status:** Legacy XML format with signal bridge  
**Use Instead:** `cotton_detection_cpp.launch.py`

```bash
# OLD (legacy XML)
ros2 launch cotton_detection_ros2 cotton_detection.launch.xml

# NEW (Python launch format)
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
```

**Why Changed:**
- Standardize on Python launch files (.launch.py)
- Legacy signal bridge no longer needed with C++ node
- Better parameter validation and documentation

## Migration Resources

- Full migration guide: `src/cotton_detection_ros2/README.md#migration-from-python-wrapper`
- C++ node documentation: `src/cotton_detection_ros2/README.md`
- System integration: `docs/ROS2_INTERFACE_SPECIFICATION.md`

## Legacy Test Scripts

If your tests still reference these archived launches:

1. **Update to C++ node** (recommended):
   ```bash
   ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py \
       simulation_mode:=true
   ```

2. **Restore from archive** (temporary only):
   ```bash
   # Copy back to launch/ directory
   cp archive/phase1/cotton_detection_wrapper.launch.py ../
   ```

**Note:** Wrapper will be fully removed in a future release after all legacy automation is migrated.
