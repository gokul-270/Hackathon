# Cotton Detection OOM Fix Plan

> **📍 MOVED:** This content has been consolidated into the Performance Optimization Guide.
> 
> **New Location:** [docs/guides/PERFORMANCE_OPTIMIZATION.md](docs/guides/PERFORMANCE_OPTIMIZATION.md#rpi-build-oom-prevention--implemented)
> 
> This file is preserved for historical reference. For current documentation, please refer to the consolidated guide above.

---

## Problem: RPi OOM with `-j2` During Compilation

**Root Cause**: Large template-heavy library headers in header files
- `#include <depthai/depthai.hpp>` (DepthAI SDK - very large)
- `#include <opencv2/opencv.hpp>` (OpenCV - large templates)
- Both included in `.hpp` files → every `.cpp` that includes them bloats

**Result**: OOM errors during compilation on RPi with `-j2`

---

## Solution Strategy

### Option 1: Move Heavy Includes to .cpp Files (RECOMMENDED) ⭐
**Effort**: Low  
**Impact**: High  
**Risk**: Low

**Steps**:
1. Replace heavy includes in headers with forward declarations
2. Move actual includes to `.cpp` implementation files
3. Use PIMPL idiom for DepthAI/OpenCV types if needed

**Files to modify**:
- `depthai_manager.hpp` - Remove `#include <depthai/depthai.hpp>`
- `cotton_detection_node.hpp` - Remove `#include <opencv2/opencv.hpp>`
- Move includes to corresponding `.cpp` files

**Expected result**: ~50% reduction in memory per compilation unit

---

### Option 2: Split Large Node File (Like yanthra_move)
**Effort**: Medium  
**Impact**: Medium  
**Risk**: Medium

**Would split `cotton_detection_node.cpp` (2,182 lines) into**:
- `cotton_detection_node_core.cpp` (~500 lines) - Core setup
- `cotton_detection_node_parameters.cpp` (~400 lines) - Parameters
- `cotton_detection_node_interfaces.cpp` (~600 lines) - Pub/sub/services
- `cotton_detection_node_callbacks.cpp` (~400 lines) - Callbacks
- `cotton_detection_node_diagnostics.cpp` (~282 lines) - Diagnostics

**Expected result**: Each file compiles faster, but still includes heavy headers

---

### Option 3: Combination Approach (BEST for RPi) ⭐⭐
**Effort**: Medium  
**Impact**: Very High  
**Risk**: Low

**Do both**:
1. Move heavy library includes from headers to .cpp (Option 1)
2. Split main node file into smaller units (Option 2)

**Expected result**: 
- Each compilation unit is small
- Each compilation unit has minimal header dependencies
- Should enable `-j2` or even `-j3` on RPi

---

## Recommended Action Plan

### Phase 1: Quick Win - Fix Header Includes (1-2 hours)
**Priority**: HIGH ⭐

**Steps**:
1. Analyze which headers need forward declarations
2. Move `#include <depthai/depthai.hpp>` from header to .cpp
3. Move `#include <opencv2/opencv.hpp>` to only files that need it
4. Use forward declarations (`class cv::Mat;`) where possible
5. Test build on RPi with `-j2`

**Expected**: This alone might fix OOM

---

### Phase 2: If Still OOM - Split Node File (2-3 hours)
**Priority**: MEDIUM

**Only if Phase 1 doesn't fully solve it**:
1. Split `cotton_detection_node.cpp` using same approach as yanthra_move
2. Logical modules:
   - Core: Node initialization, main loop
   - Parameters: Parameter declaration/handling
   - Interfaces: Publishers, subscribers, services
   - Callbacks: Service and topic callbacks
   - Diagnostics: Diagnostic updater callbacks

**Expected**: Smaller files = less memory per worker

---

## Implementation Details

### Phase 1: Header Include Fixes

#### File 1: `depthai_manager.hpp`
**Current** (causes bloat):
```cpp
#include <depthai/depthai.hpp>  // HUGE library
#include <opencv2/opencv.hpp>   // HUGE library

class DepthAIManager {
    std::shared_ptr<dai::Device> device_;
    std::shared_ptr<dai::DataOutputQueue> queue_;
    // ...
};
```

**Fixed** (forward declarations):
```cpp
// Forward declarations
namespace dai {
    class Device;
    class DataOutputQueue;
    class Pipeline;
}

namespace cv {
    class Mat;
}

class DepthAIManager {
    std::shared_ptr<dai::Device> device_;
    std::shared_ptr<dai::DataOutputQueue> queue_;
    // ...
};
```

#### File 2: `depthai_manager.cpp`
**Add the actual includes here**:
```cpp
#include "cotton_detection_ros2/depthai_manager.hpp"

// NOW include the heavy libraries (only in .cpp)
#include <depthai/depthai.hpp>
#include <opencv2/opencv.hpp>

// Rest of implementation...
```

#### File 3: `cotton_detection_node.hpp`
**Current**:
```cpp
#include <opencv2/opencv.hpp>  // Needed?
#include "cotton_detection_ros2/depthai_manager.hpp"  // Pulls in DepthAI
```

**Fixed**:
```cpp
// Only include what's needed in header
namespace dai { class Device; }  // Forward declaration
namespace cv { class Mat; }      // Forward declaration

// Include lightweight component interfaces
#include "cotton_detection_ros2/cotton_detector.hpp"
#include "cotton_detection_ros2/image_processor.hpp"
// etc...
```

---

## Testing Plan

### Test 1: Build Memory Usage (Before)
```bash
# On RPi - monitor memory
ssh ubuntu@192.168.137.253
cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash

# Build with -j1 (should work but slow)
time colcon build --packages-select cotton_detection_ros2 \
    --parallel-workers 1

# Build with -j2 (likely OOM)
colcon build --packages-select cotton_detection_ros2 \
    --parallel-workers 2
# Expected: OOM error
```

### Test 2: After Phase 1 Fixes
```bash
# Try -j2 again
colcon build --packages-select cotton_detection_ros2 \
    --parallel-workers 2
# Expected: Should work!
```

### Test 3: Runtime Verification
```bash
# Make sure functionality still works
ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py
# Check camera detection, service calls, etc.
```

---

## Expected Results

### Phase 1 Only (Header Fixes)
- **Build time**: Similar (~5-6 min with -j1)
- **Memory per worker**: ~50% reduction
- **`-j2` on RPi**: Should work ✅
- **Risk**: Very low (just moving includes)

### Phase 1 + Phase 2 (Header Fixes + Split)
- **Build time**: ~3-4 min with -j2
- **Memory per worker**: ~70% reduction
- **`-j2` on RPi**: Definitely works ✅
- **`-j3` on RPi**: Might work ✅
- **Risk**: Low (same pattern as yanthra_move)

---

## Recommendation

**Start with Phase 1** (header include fixes):
1. Lower effort
2. Lower risk
3. Likely sufficient to fix OOM
4. Can do Phase 2 later if needed

**Do Phase 2** only if:
- Phase 1 doesn't fully solve OOM
- You want faster build times
- You want better code organization (bonus)

---

## Next Steps

1. ✅ Review this plan
2. ⏸️ Implement Phase 1 (header fixes)
3. ⏸️ Test on RPi with `-j2`
4. ⏸️ If needed, implement Phase 2 (split node)

**Want me to start implementing Phase 1?**
