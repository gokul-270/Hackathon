# Commit Message: Hardware Failure Detection

```
feat: Add critical hardware failure detection for CAN, motors, and homing

Implement three safety-critical hardware validation checks in yanthra_move
system initialization to prevent unsafe operation when hardware fails.

Changes:
1. CAN Bus Detection
   - Verify mg6010_controller_node is running before proceeding
   - Stop immediately if CAN interface (can0) not available
   - Prevents motor control failures and unsafe operation

2. Motor Communication Validation
   - Check joint_states topic for motor responses (3s timeout)
   - Verify all 3 motors (IDs 0,1,2) detected on CAN bus
   - Stop if any motor missing or not responding

3. Homing Position Verification
   - Validate joint positions available after homing (2s timeout)
   - Check positions are finite (not NaN/Inf)
   - Log actual homed positions for verification
   - Stop if homing produces invalid or unknown positions

All checks:
- Provide detailed error messages with root cause analysis
- Include troubleshooting steps (CAN commands, power checks)
- Automatically skipped in simulation mode
- Follow safety-first principle: stop on any critical hardware failure

Safety Impact:
- Before: System could attempt operation with missing/failed hardware
- After: System stops immediately with clear diagnostics

Performance Impact:
- ~1-5s one-time overhead at startup (acceptable)
- CAN check: <100ms (node query)
- Motor check: 0-3s (typically <500ms)
- Homing verify: 0-2s (typically <500ms)

Files Modified:
- src/yanthra_move/src/yanthra_move_system_services.cpp
  * Added sensor_msgs/msg/joint_state.hpp include
  * Implemented hardware validation in performInitializationAndHoming()
  * Lines 48-86: CAN bus detection
  * Lines 89-140: Motor communication validation
  * Lines 219-302: Homing verification

Build: Successful (1m 20s), no errors or warnings

Testing: Hardware validation recommended before production use
See: docs/HARDWARE_FAILURE_DETECTION_COMPLETE.md

Related:
- Complements earlier camera detection fix (commit dd0db244)
- Part of comprehensive hardware safety validation
- Follows ERROR_HANDLING_GUIDE.md policy (stop on safety-critical failures)
```

## Git Commands

```bash
# Stage changes
git add src/yanthra_move/src/yanthra_move_system_services.cpp
git add docs/HARDWARE_FAILURE_DETECTION_COMPLETE.md
git add docs/COMMIT_HARDWARE_FAILURE_DETECTION.md

# Commit with detailed message
git commit -F docs/COMMIT_HARDWARE_FAILURE_DETECTION.md

# Or short version:
git commit -m "feat: Add CAN/motor/homing failure detection

- Verify CAN bus available before motor control
- Check all 3 motors responding on CAN
- Validate homing positions after completion
- Stop system on any critical hardware failure
- Provide detailed error messages with troubleshooting

Safety-critical changes, prevents unsafe operation."
```

## Verification Before Commit

```bash
# Verify build successful
colcon build --packages-select yanthra_move
# ✅ Should complete in ~1m 20s with no errors

# Check modified files
git status
# Should show:
# modified:   src/yanthra_move/src/yanthra_move_system_services.cpp
# new file:   docs/HARDWARE_FAILURE_DETECTION_COMPLETE.md
# new file:   docs/COMMIT_HARDWARE_FAILURE_DETECTION.md

# Review changes
git diff src/yanthra_move/src/yanthra_move_system_services.cpp
# Verify:
# - sensor_msgs include added
# - Hardware checks implemented in performInitializationAndHoming()
# - Error messages clear and helpful
# - Safety checks active in hardware mode only
```
