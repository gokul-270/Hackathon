# C++ Implementation Project - START HERE

**Date:** October 8, 2025  
**Status:** Ready to Begin  
**Duration:** 7-8 weeks

---

## 📋 Project Overview

We're replacing the Python wrapper with a **production-ready C++ node** that integrates DepthAI directly. The C++ code is **90% complete** - we just need to add DepthAI C++ API integration.

**Why C++ over improving Python:**
- 6-10x faster performance (420ms → 60ms)
- C++ already has 5 detection modes, monitoring, preprocessing
- Python will be deprecated anyway
- Saves 6-7 weeks vs doing Python first then C++

---

## 📁 Key Documents (Read in Order)

1. **This file** - Quick start and overview
2. `TASK_COMPARISON_PYTHON_VS_CPP.md` - Why new tasks, not old 26
3. `CPP_NODE_COMPREHENSIVE_REVIEW_AND_TASKS.md` - Full technical review
4. `CPP_IMPLEMENTATION_TASK_TRACKER.md` - Live task tracking (update this!)
5. `PHASE0_PYTHON_CRITICAL_FIXES.md` - Week 1 implementation details

---

## 🎯 The Plan (7-8 Weeks)

### Week 1 (Oct 8-14): Parallel Tracks
**Track 1 - Python Stability (Phase 0):**
- Fix 5 critical bugs (deadlock, race conditions, atomic writes, auto-restart, simulation mode)
- Keep Python stable while C++ is being developed
- **Time:** 2 days implementation, 1 day testing

**Track 2 - C++ Prep:**
- Install depthai-core library
- Study DepthAI C++ examples
- Design DepthAIManager class
- **Time:** 2-3 days research and design

### Week 2-4 (Phase 1): DepthAI Integration ⭐ **CRITICAL PATH**
- Create DepthAIManager class
- Integrate into CottonDetectionNode
- Hardware testing with OAK-D Lite
- Error handling and stability

### Week 5 (Phase 2): Camera & Transforms
- TF2 transform publisher
- Calibration from DepthAI
- Coordinate validation

### Week 6 (Phase 3): Features & Quality
- Confidence scores
- Diagnostics
- Launch files
- Documentation

### Week 7 (Phase 4): Testing
- Unit tests
- Integration tests
- Performance benchmarking
- 24-hour stability test

### Week 8 (Phase 5): Deployment
- Side-by-side C++ vs Python testing
- Switch to C++ as default
- Deprecate Python wrapper
- Production deployment

---

## ✅ Code Quality Rules

**Keep code simple and maintainable:**

### File Size Limits
- Header files: **Max 300 lines**
- Implementation files: **Max 600 lines**
- Functions: **Max 50 lines** (target: 20 lines)

### When to Refactor
1. File > 600 lines → Split into multiple files
2. Function > 50 lines → Extract helper functions
3. Class > 10 methods → Split responsibilities
4. Cyclomatic complexity > 10 → Simplify logic

### DepthAIManager Structure
**Start Simple:**
```
include/cotton_detection_ros2/
  └── depthai_manager.hpp      (~200 lines)
src/
  └── depthai_manager.cpp      (~500 lines)
```

**If it grows, refactor into:**
```
src/depthai/
  ├── manager.cpp              (Main orchestration)
  ├── pipeline_builder.cpp     (Pipeline setup)
  ├── frame_processor.cpp      (Frame handling)
  └── calibration_handler.cpp  (Calibration)
```

---

## 🚀 Week 1 Action Items

### Phase 0: Python Fixes (Days 1-3)

**File: `cotton_detect_ros2_wrapper.py`**

1. **Fix subprocess deadlock (2 hours)**
   - Line 395: Add log file
   - Lines 401-402: Redirect stdout/stderr to log
   - Line 480: Close log on shutdown

2. **Fix signal race condition (1 hour)**
   - Line 67: Replace bool with `threading.Event()`
   - Line 349: Use `.set()` in handler
   - Lines 414-428: Use `.wait(timeout=...)`

3. **Atomic file writes (2 hours)**
   - Edit `CottonDetect.py`
   - Line 12: Add `import tempfile`
   - Lines 200-225: Add `write_file_atomically()`
   - Lines 439-441: Use atomic write

4. **Auto-restart logic (3 hours)**
   - Lines 67-69: Add restart tracking
   - Lines 439-451: Replace monitor function

5. **Launch file parameter (30 min)**
   - Edit `cotton_detection_wrapper.launch.py`
   - Add `simulation_mode` argument

**See `PHASE0_PYTHON_CRITICAL_FIXES.md` for detailed code!**

### Phase 1 Prep: C++ Research (Days 1-5)

1. **Install depthai-core (Day 1)**
   ```bash
   # Check if installed
   dpkg -l | grep depthai
   
   # If not, install
   sudo apt update
   sudo apt install cmake libusb-1.0-0-dev
   
   # Clone and build depthai-core
   git clone https://github.com/luxonis/depthai-core.git
   cd depthai-core
   mkdir build && cd build
   cmake .. -DBUILD_SHARED_LIBS=ON
   make -j$(nproc)
   sudo make install
   ```

2. **Study DepthAI Examples (Days 2-3)**
   ```bash
   # Find examples
   cd ~/depthai-core/examples
   
   # Key examples to study:
   # - SpatialDetectionNetwork/
   # - ColorCamera/
   # - StereoDepth/
   
   # Build and run spatial detection example
   mkdir build && cd build
   cmake ..
   make
   ./spatial_tiny_yolo
   ```

3. **Design DepthAIManager (Days 4-5)**
   - Sketch class interface
   - List required methods
   - Plan configuration structure
   - Create skeleton header file

---

## 📊 Task Tracking

**Primary Document:** `CPP_IMPLEMENTATION_TASK_TRACKER.md`

**Update weekly with:**
```markdown
**Week 1 Update (Oct 14):**
- **Completed:** Task IDs: 0.1, 0.2, 0.3, 0.4, 0.5
- **In Progress:** Research: depthai-core examples
- **Blocked:** None
- **Next Week:** Tasks 1.1, 1.2 (DepthAIManager header + impl)
- **Risks:** None identified yet
- **Notes:** DepthAI API similar to Python, easier than expected
```

### Task Status Icons
- ⬜ Not Started
- 🏗️ In Progress
- ✅ Complete
- ⚠️ Blocked
- ❌ Cancelled

---

## 🧪 Testing Strategy

### Phase 0 Testing (Week 1)
Run all 5 tests from `PHASE0_PYTHON_CRITICAL_FIXES.md`:
1. 1-hour stability test
2. 10 rapid restarts
3. 20 kill -9 during write
4. 5 subprocess kills (3 restart, 4+ fail)
5. Simulation mode launch

### Continuous Testing (Weeks 2-8)
- **Daily:** Unit tests for new code
- **Weekly:** Integration test with hardware
- **Phase end:** Full regression suite

### Hardware Requirements
- OAK-D Lite camera
- Raspberry Pi 4 (target platform)
- USB 3.0 connection
- Test cotton plants or images

---

## 🔧 Development Environment

### Required Tools
```bash
# ROS2 (already installed)
source /opt/ros/humble/setup.bash

# Build tools
sudo apt install build-essential cmake clang-tidy cppcheck valgrind

# DepthAI
# (Install during Week 1 prep)

# Optional but recommended
sudo apt install ccache  # Faster rebuilds
```

### Build Commands
```bash
# From workspace root
cd /home/uday/Downloads/pragati_ros2

# Build with DepthAI enabled
colcon build --packages-select cotton_detection_ros2 \
  --cmake-args -DHAS_DEPTHAI=ON

# Run tests
colcon test --packages-select cotton_detection_ros2

# Check for memory leaks
valgrind --leak-check=full ros2 run cotton_detection_ros2 cotton_detection_node
```

---

## 📞 Getting Help

### If Stuck on DepthAI API
- Check `depthai-core/examples/` directory
- Read docs: https://docs.luxonis.com/projects/api/
- Search GitHub issues: https://github.com/luxonis/depthai-core/issues

### If Performance Issues
- Profile with `perf` or `gprof`
- Check CPU usage with `htop`
- Verify camera settings (resolution, FPS)

### If Hardware Issues
- Check USB connection: `lsusb | grep Movidius`
- Test with Python script first
- Verify udev rules for OAK-D

---

## 🎯 Success Metrics

### Phase 1 Exit Criteria
- [ ] DepthAIManager compiles without errors
- [ ] Can initialize OAK-D Lite camera
- [ ] Returns spatial coordinates (x,y,z)
- [ ] Detection latency < 100ms
- [ ] No memory leaks (valgrind clean)

### Final Success Criteria (Week 8)
- [ ] Detection latency < 100ms (target: 60ms)
- [ ] FPS > 15 (target: 20)
- [ ] Accuracy within 5% of Python wrapper
- [ ] 24-hour stability test passed
- [ ] All unit/integration tests passing
- [ ] Production deployment successful

---

## 🚨 Risk Management

| Risk | If it happens | Do this |
|------|---------------|---------|
| DepthAI C++ API very different from Python | Can't figure out pipeline setup | Study examples more, ask on Luxonis forum, consider consulting Python wrapper logic |
| Performance not meeting target | Latency > 100ms | Profile code, optimize hot paths, reduce image resolution |
| Code grows too complex | Files > 600 lines | Refactor immediately, split into modules |
| Hardware incompatibility | Works on dev machine but not RPi4 | Test on RPi4 weekly, adjust for ARM differences |
| Python wrapper breaks during dev | Production affected | Roll back to stable version, minimal changes only |

---

## 📝 Weekly Checklist

**Every Monday:**
- [ ] Update task tracker with last week's progress
- [ ] Review risks and blockers
- [ ] Plan this week's tasks
- [ ] Update documentation if needed

**Every Friday:**
- [ ] Run full test suite
- [ ] Commit and push code
- [ ] Update task status
- [ ] Note lessons learned

---

## 🎉 Quick Wins

**If you finish early or need a break:**
- Add more unit tests
- Improve documentation
- Optimize existing code
- Add helpful log messages
- Write usage examples

---

## 📚 Additional Resources

### DepthAI
- Main docs: https://docs.luxonis.com/
- C++ API: https://docs.luxonis.com/projects/api/
- Examples: https://github.com/luxonis/depthai-core/tree/main/examples

### ROS2
- Jazzy docs: https://docs.ros.org/en/jazzy/
- rclcpp API: https://docs.ros2.org/latest/api/rclcpp/

### C++ Best Practices
- Modern C++: https://github.com/cpp-best-practices/cppbestpractices
- Google Style: https://google.github.io/styleguide/cppguide.html

---

## ✨ Let's Go!

You're all set to start! Begin with:

1. **Day 1-2:** Implement Phase 0 fixes (Python stability)
2. **Day 3:** Test Phase 0 thoroughly
3. **Day 4-5:** Install depthai-core and study examples

**Good luck! 🚀**

---

**Last Updated:** October 8, 2025  
**Next Review:** October 15, 2025  
**Questions?** Check the comprehensive review document or task tracker
