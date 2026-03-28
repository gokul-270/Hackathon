# Obsolete TODOs Archive

**Date:** 2025-10-15  
**Status:** Archived - Obsolete/Deprecated Items  
**Count:** ~600 items (24% of total 2,469)  
**Action:** Removed from active backlog, archived for reference

---

## Archive Purpose

This document archives TODOs that are no longer relevant due to changed requirements, deprecated features, or superseded implementations. These items are preserved for historical context but will not be actioned.

---

## Obsolete Categories

### 1. Legacy ODrive References ❌

**Status:** Obsolete - ODrive Not Used in Current Deployment  
**Count:** ~250 items  
**Reason:** MG6010 is primary controller; ODrive maintained only for legacy compatibility

**Examples of Obsolete TODOs:**
- `TODO: Optimize ODrive CAN parameters` → MG6010 used instead
- `TODO: Test ODrive velocity control` → Not applicable
- `TODO: Document ODrive configuration` → MG6010 docs prioritized
- `TODO: Fix ODrive communication issues` → Using MG6010 protocol
- `TODO: Implement ODrive trajectory following` → ros2_control handles this

**What Replaced Them:**
- MG6010 protocol implementation (LK-TECH CAN Protocol V2.35)
- Generic motor controller abstraction
- Native CAN communication (not CANopen)

**Preserved For:**
- Historical compatibility
- Potential future ODrive hardware
- Reference implementation

**Evidence:**
- ODrive code maintained in `src/motor_control_ros2/` but not actively used
- Documentation notes ODrive as "Legacy - Maintained for Compatibility"

---

### 2. Deprecated Python Wrapper (Cotton Detection) ❌

**Status:** Obsolete - C++ Implementation Complete  
**Count:** ~100 items  
**Reason:** Python wrapper fully replaced by C++ DepthAI integration

**Examples of Obsolete TODOs:**
- `TODO: Fix Python wrapper race conditions` → C++ doesn't have this issue
- `TODO: Optimize Python-C++ serialization` → No longer needed
- `TODO: Debug wrapper memory leaks` → C++ manages memory directly
- `TODO: Improve wrapper error handling` → Native C++ error handling
- `TODO: Test wrapper performance` → C++ is faster by design

**What Replaced Them:**
- Direct C++ DepthAI SDK integration
- Native C++ detection node
- Eliminated Python dependency

**Migration Complete:** September 2025

**Evidence:**
- C++ node: `src/cotton_detection_ros2/src/depthai_manager.cpp`
- Python wrapper deprecated: `scripts/deprecated/`
- Performance improvement: 30-50% faster

---

### 3. File-Based Communication (Cotton Details) ❌

**Status:** Obsolete - ROS2 Topics/Services Used  
**Count:** ~80 items  
**Reason:** Modern ROS2 communication replaced file-based IPC

**Examples of Obsolete TODOs:**
- `TODO: Fix cotton_details.txt race conditions` → Using ROS2 topics now
- `TODO: Add file locking for cotton_details.txt` → Not needed
- `TODO: Handle file permissions` → ROS2 handles permissions
- `TODO: Optimize file read/write` → Topic publishing is faster
- `TODO: Add error recovery for file corruption` → Not applicable

**What Replaced Them:**
- ROS2 topic: `/cotton_detections`
- ROS2 services: `/cotton_detection/next_target`
- Message types: Standard ROS2 messages

**Migration Complete:** August 2025

**Evidence:**
- File communication removed from codebase
- All packages use ROS2 topics/services
- Documented in package READMEs

---

### 4. ROS1 Legacy Patterns ❌

**Status:** Obsolete - Full ROS2 Migration Complete  
**Count:** ~70 items  
**Reason:** ROS2 Jazzy is now standard; ROS1 not supported

**Examples of Obsolete TODOs:**
- `TODO: Replace ros::spinOnce()` → Already done
- `TODO: Migrate to ROS2 executors` → Complete
- `TODO: Convert XML launch files` → All converted to Python
- `TODO: Update message definitions for ROS2` → Complete
- `TODO: Test ROS1 bridge compatibility` → Not needed

**What Replaced Them:**
- ROS2 Jazzy executors
- Python launch files
- ROS2 message/service definitions
- Native ROS2 patterns throughout

**Migration Complete:** September 2025

**Evidence:**
- Zero `ros::` calls in codebase
- All launch files Python format
- Full ROS2 Jazzy compliance

---

### 5. Obsolete Hardware Configurations ❌

**Status:** Obsolete - Hardware Decisions Finalized  
**Count:** ~50 items  
**Reason:** Hardware platform selected; alternatives not pursued

**Examples of Obsolete TODOs:**
- `TODO: Test with alternative motor drivers` → MG6010 selected
- `TODO: Evaluate different camera options` → OAK-D Lite chosen
- `TODO: Consider NVIDIA Jetson platform` → Raspberry Pi 4 selected
- `TODO: Test with different CAN adapters` → MCP2515 standard
- `TODO: Benchmark ARM vs x86` → RPi4 ARM validated

**Final Hardware Selection:**
- **Motors:** MG6010-i6 integrated servos
- **Camera:** OAK-D Lite (Luxonis)
- **Platform:** Raspberry Pi 4 (4GB+)
- **CAN:** MCP2515 SPI adapters
- **Power:** 48V DC

**Decision Date:** July 2025

---

### 6. Superseded Design Approaches ❌

**Status:** Obsolete - Better Approach Implemented  
**Count:** ~50 items  
**Reason:** Original design replaced by improved architecture

**Examples of Obsolete TODOs:**
- `TODO: Implement centralized controller` → Distributed architecture chosen
- `TODO: Add master-slave coordination` → Autonomous arms selected
- `TODO: Create monolithic detection pipeline` → Modular C++ nodes
- `TODO: Use single-threaded event loop` → Multi-threaded ROS2 nodes
- `TODO: Store state in filesystem` → In-memory state management

**New Architecture:**
- Distributed system (5 RPi4: 4 arms + 1 vehicle)
- Autonomous arms with MQTT coordination
- Modular ROS2 nodes
- Multi-threaded executors
- ROS2 topic/service-based state

**Documented In:** [docs/architecture/SYSTEM_ARCHITECTURE.md](../../architecture/SYSTEM_ARCHITECTURE.md)

---

## Statistics

### Obsolescence by Reason

| Reason | Count | Percentage |
|--------|-------|------------|
| Legacy ODrive | ~250 | 42% |
| Python wrapper deprecated | ~100 | 17% |
| File-based communication | ~80 | 13% |
| ROS1 patterns | ~70 | 12% |
| Hardware alternatives | ~50 | 8% |
| Superseded design | ~50 | 8% |
| **Total** | **~600** | **100%** |

### Obsolescence Timeline

| Month | Items Made Obsolete | Reason |
|-------|---------------------|--------|
| July 2025 | ~50 | Hardware finalized |
| August 2025 | ~150 | ROS2 migration, file-based IPC removed |
| September 2025 | ~200 | Python wrapper deprecated, ROS1 complete |
| October 2025 | ~200 | Architecture consolidated, ODrive deprioritized |

---

## Why These Are Archived (Not Deleted)

**Historical Context:**
- Shows evolution of project decisions
- Documents why certain approaches were abandoned
- Valuable for future retrospectives

**Lessons Learned:**
- File-based IPC was brittle → Use ROS2 topics
- Python wrapper added latency → Use C++ directly
- Monolithic design was inflexible → Modular better

**Potential Future Use:**
- ODrive support might be requested by customers
- Alternative hardware could be evaluated later
- Design decisions documented for similar projects

---

## Reference to Full Inventory

**Complete TODO List (2,469 items) available in:**
- CSV Format: [docs/archive/2025-10-audit/2025-10-14/todo_inventory.csv](../2025-10-audit/2025-10-14/todo_inventory.csv)
- Raw Format: [docs/archive/2025-10-audit/2025-10-14/todo_full_raw.txt](../2025-10-audit/2025-10-14/todo_full_raw.txt)
- Consolidated Summary: [docs/TODO_CONSOLIDATED.md](../../TODO_CONSOLIDATED.md)

---

## Archiving Actions Taken

1. ✅ Identified all obsolete items from TODO_CONSOLIDATED.md Category 2
2. ✅ Categorized by reason for obsolescence
3. ✅ Documented replacement implementations
4. ✅ Preserved historical context
5. ✅ Removed from active backlog tracking

---

## What This Means

**For Developers:**
- Don't work on these TODOs
- Focus on active backlog (~1,069 items)
- Consult this archive if considering similar approaches

**For Project Managers:**
- 24% of original backlog eliminated through better design
- Scope reduction without loss of functionality
- Cleaner project roadmap

**For Future Projects:**
- Learn from deprecated approaches
- Reference successful replacements
- Understand architectural evolution

---

## Impact on Backlog

**Before Archiving:**
- Total TODOs: 2,469
- Obsolete: ~600 (24%)

**After Archiving:**
- Active backlog: ~1,869
- Further reduced by "Already Done": ~1,069 remain
- Net reduction: 57% (1,400 removed)

**Result:**
- More focused backlog
- Clearer priorities
- Better project visibility

---

## Next Steps

**Cleanup Actions:**
- ✅ Archive obsolete TODOs (this document)
- ⏳ Remove obsolete code comments
- ⏳ Update documentation to reflect current architecture
- ⏳ Mark deprecated code paths clearly

**Maintenance:**
- Review quarterly for newly obsolete items
- Update this archive as needed
- Ensure new TODOs don't resurrect obsolete approaches

---

**Archive Date:** 2025-10-15  
**Document Version:** 1.0  
**Status:** Archived - Obsolete  
**Related:** [docs/TODO_MASTER.md](../../TODO_MASTER.md), [todos_completed.md](todos_completed.md)
