# Root Scripts & Files Cleanup Plan

**Current State:** 18 scripts/config files + 2 other files in root  
**Analysis:** Which to keep, which to move  

---

## Files Analysis

### ✅ KEEP in Root (11 files)

**Build & Setup Scripts (3):**
1. ✅ `build.sh` - Main build script (frequently used)
2. ✅ `build_rpi.sh` - RPi-specific build
3. ✅ `install_deps.sh` - Dependency installation

**Test Scripts (2):**
4. ✅ `test.sh` - Main test script
5. ✅ `test_complete_system.sh` - Full system test

**Critical Operational Scripts (2):**
6. ✅ `emergency_motor_stop.sh` - Safety critical
7. ✅ `sync_to_rpi.sh` - Deployment script

**Project Config Files (4):**
8. ✅ `colcon.meta` - Build configuration
9. ✅ `cyclone_config.xml` - DDS configuration
10. ✅ `Doxyfile` - Documentation generation
11. ✅ `BASELINE_VERSION.txt` - Version tracking

**Total to keep:** 11 files

---

### 🔄 MOVE to scripts/ (7 scripts)

**Testing Utilities:**
1. `test_offline_cotton_detection.sh` → `scripts/testing/`
2. `test_ros1_cotton_detect.sh` → `scripts/testing/`
3. `test_ros1_cotton_detect_remote.sh` → `scripts/testing/`
4. `test_start_switch.sh` → `scripts/testing/`
5. `test_cotton_detection_publisher.py` → `scripts/testing/`

**Utility Scripts:**
6. `monitor_motor_positions.sh` → `scripts/utils/`
7. `publish_fake_cotton.py` → `scripts/utils/`

**Fix Scripts:**
8. `fix_simulation_mode_on_pi.sh` → `scripts/fixes/`

**Reason:** These are domain-specific utility scripts, not core project operations.

---

### 📦 Special Case (1 file)

**Recently Created:**
- `fix_broken_links.py` → Keep temporarily or move to `scripts/maintenance/`

**Decision:** Move to scripts/maintenance/ (one-time use script)

---

## Recommended Actions

### Phase 1: Create Directory Structure
```bash
mkdir -p scripts/testing
mkdir -p scripts/utils
mkdir -p scripts/fixes
mkdir -p scripts/maintenance
```

### Phase 2: Move Test Scripts
```bash
mv test_offline_cotton_detection.sh scripts/testing/
mv test_ros1_cotton_detect.sh scripts/testing/
mv test_ros1_cotton_detect_remote.sh scripts/testing/
mv test_start_switch.sh scripts/testing/
mv test_cotton_detection_publisher.py scripts/testing/
```

### Phase 3: Move Utility Scripts
```bash
mv monitor_motor_positions.sh scripts/utils/
mv publish_fake_cotton.py scripts/utils/
```

### Phase 4: Move Fix Scripts
```bash
mv fix_simulation_mode_on_pi.sh scripts/fixes/
```

### Phase 5: Move Maintenance Scripts
```bash
mv fix_broken_links.py scripts/maintenance/
```

---

## Final Root Contents

### After Cleanup:

**Scripts (7):**
1. build.sh
2. build_rpi.sh
3. install_deps.sh
4. test.sh
5. test_complete_system.sh
6. emergency_motor_stop.sh
7. sync_to_rpi.sh

**Config Files (4):**
1. colcon.meta
2. cyclone_config.xml
3. Doxyfile
4. BASELINE_VERSION.txt

**Total:** 11 files (down from 20)

---

## Directory Structure After Cleanup

```
pragati_ros2/
├── build.sh                    # Main build
├── build_rpi.sh               # RPi build
├── install_deps.sh            # Dependencies
├── test.sh                    # Main test
├── test_complete_system.sh    # Full test
├── emergency_motor_stop.sh    # Safety
├── sync_to_rpi.sh             # Deploy
├── colcon.meta                # Build config
├── cyclone_config.xml         # DDS config
├── Doxyfile                   # Docs config
├── BASELINE_VERSION.txt       # Version
│
├── scripts/
│   ├── testing/
│   │   ├── test_offline_cotton_detection.sh
│   │   ├── test_ros1_cotton_detect.sh
│   │   ├── test_ros1_cotton_detect_remote.sh
│   │   ├── test_start_switch.sh
│   │   └── test_cotton_detection_publisher.py
│   │
│   ├── utils/
│   │   ├── monitor_motor_positions.sh
│   │   └── publish_fake_cotton.py
│   │
│   ├── fixes/
│   │   └── fix_simulation_mode_on_pi.sh
│   │
│   └── maintenance/
│       └── fix_broken_links.py
```

---

## Benefits

### Organization
- **Frequently used scripts in root:** build, test, emergency, deploy
- **Specialized scripts organized:** testing/, utils/, fixes/
- **Clear purpose:** Root = essential operations, scripts/ = utilities

### Discoverability
- **Root stays clean:** Only 11 essential files
- **Related scripts grouped:** All test scripts together
- **Easy to find:** Logical categorization

### Maintenance
- **Clear ownership:** Core vs. utility scripts
- **Future-proof:** New scripts have clear home
- **Documentation-friendly:** Easier to document organized structure

---

## Impact Analysis

### Before
- 20 scripts/config files mixed in root
- Hard to distinguish core vs. utility

### After
- 11 essential files in root
- 8 utility scripts organized in subdirs
- 45% reduction in root files

---

## Considerations

### Existing References
Need to check if any docs reference moved scripts:
- `test_offline_cotton_detection.sh` - Check OFFLINE_DETECTION_TEST_REPORT.md
- `test_start_switch.sh` - Check testing docs
- `emergency_motor_stop.sh` - **Keep in root** (safety critical, widely referenced)

### Script Dependencies
Some scripts may reference others - check:
- Relative path imports
- Source statements
- Script calls

---

## Execution Decision

**Recommendation:** Move specialized scripts to organized subdirectories.

**Rationale:**
1. Root should contain only frequently-used core operations
2. Utility scripts benefit from categorization
3. Matches industry best practices
4. Improves overall project organization

---

Would you like me to:
1. **Execute the moves** (recommended)
2. **Create scripts/README.md** first (document new structure)
3. **Check for references** before moving (safer but slower)

Choose your preferred approach!
