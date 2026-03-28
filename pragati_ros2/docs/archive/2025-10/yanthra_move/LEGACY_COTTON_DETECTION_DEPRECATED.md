# Legacy Cotton Detection Integration - DEPRECATED

## Notice

The following files contain **legacy cotton detection service calls** that are **DEPRECATED** as of 2025-09-30:

- `src/yanthra_move_aruco_detect.cpp`
- `src/yanthra_move_calibrate.cpp`

## Migration Path

### Old Approach (DEPRECATED)
These tools directly called cotton detection services:
- `/cotton_detection/detect_cotton_srv`
- Direct service clients in tool code

### New Approach (RECOMMENDED)
Cotton positions are now available via:
1. **YanthraMoveSystem** subscribes to `/cotton_detection/results`
2. **Internal buffer** stores latest detections thread-safely
3. **getCottonPositionProvider()** callback provides access
4. Tools should query YanthraMoveSystem instead of creating duplicate subscriptions

## Recommendations

1. **For New Code**: Use YanthraMoveSystem's cotton position provider
2. **For Existing Tools**: Refactor to use single source of truth (YanthraMoveSystem)
3. **Service Calls**: Only use for manual triggering/testing, not regular operation

## Single Source of Truth

```
cotton_detection_ros2 → /cotton_detection/results → YanthraMoveSystem (buffer)
                                                            ↓
                                           All tools/components access via provider
```

## Action Items

- [ ] Refactor `yanthra_move_aruco_detect.cpp` to use YanthraMoveSystem provider
- [ ] Refactor `yanthra_move_calibrate.cpp` to use YanthraMoveSystem provider
- [ ] Remove duplicate cotton detection subscriptions
- [ ] Update tool documentation to reflect new architecture

## Contact

For questions about migration, contact the system architect.

**Last Updated:** 2025-09-30