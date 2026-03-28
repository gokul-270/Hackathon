# Root Folder Cleanup Plan

**Current State:** 25 markdown files in root  
**Target:** Keep only essential project-level files in root  
**Goal:** Move domain-specific docs to appropriate subdirectories

---

## Files to KEEP in Root (8 files)

These are essential project-level files:

1. ✅ **README.md** - Main project entry point
2. ✅ **CHANGELOG.md** - Version history
3. ✅ **CONTRIBUTING.md** - Contribution guidelines
4. ✅ **MOTOR_DOCS_INDEX.md** - Motor documentation hub (referenced in README)
5. ✅ **DOCUMENTATION_COMPREHENSIVE_REVIEW_2025-10-28.md** - Recent review report
6. ✅ **DOCUMENTATION_IMPROVEMENTS_COMPLETE_2025-10-28.md** - Recent completion report
7. ✅ **BROKEN_LINKS_FIX_SUMMARY.md** - Recent fix summary
8. ✅ **HARDWARE_QUICKSTART.md** - Quick hardware setup guide

**Reason:** These are frequently accessed, project-wide documents.

---

## Files to MOVE (17 files)

### Motor Control → `docs/guides/` (7 files)

1. **MOTOR_CALCULATION_FLOW.md** → `docs/archive/2025-10-28/`
   - *Superseded by MOTOR_CALCULATION_COMPREHENSIVE.md*
   
2. **FINAL_MOTOR_FLOW_CORRECTED.md** → `docs/archive/2025-10-28/`
   - *Superseded by MOTOR_CALCULATION_COMPREHENSIVE.md*
   
3. **MOTOR_INITIALIZATION_EXPLAINED.md** → `docs/guides/`
   - *Active motor guide*
   
4. **MOTOR_CONTROLLER_TEST_GUIDE.md** → `docs/guides/`
   - *Active testing guide*
   
5. **MOTOR_TEST_QUICK_REF.md** → `docs/guides/`
   - *Active quick reference*
   
6. **MOTOR_DEBUG.md** → `docs/guides/`
   - *Active debugging guide*
   
7. **TRANSMISSION_FACTOR_FIX.md** → `docs/guides/` or `docs/_reports/2025-10-28/`
   - *Technical fix documentation*

### Cotton Detection → `docs/guides/` or `docs/_reports/` (3 files)

8. **COTTON_DETECTION_ISSUE_DIAGNOSIS.md** → `docs/_reports/2025-10-28/`
   - *Historical issue report*
   
9. **COTTON_DETECTION_SUMMARY.md** → `docs/guides/`
   - *If active guide, keep in guides*
   
10. **OFFLINE_DETECTION_TEST_REPORT.md** → `docs/_reports/2025-10-28/`
    - *Test report*

### Validation/Testing → `docs/_reports/` (3 files)

11. **FINAL_VALIDATION.md** → `docs/_reports/2025-10-28/`
    - *Historical validation*
    
12. **RPI4_VALIDATION_REPORT.md** → `docs/_reports/2025-10-28/`
    - *Platform validation*
    
13. **VALIDATION_SUMMARY.md** → `docs/_reports/2025-10-28/`
    - *Summary report*

### Launch System → `docs/guides/` (2 files)

14. **LAUNCH_CONSOLIDATION.md** → `docs/guides/`
    - *Launch system documentation*
    
15. **LAUNCH_STATUS.md** → `docs/guides/`
    - *Launch system status*

### Safety → `docs/guides/` (1 file)

16. **EMERGENCY_STOP_README.md** → `docs/guides/`
    - *Safety documentation*

### Testing → `docs/guides/` (1 file)

17. **TEST_WITHOUT_CAMERA.md** → `docs/guides/`
    - *Testing guide*

---

## Recommended Actions

### Phase 1: Archive Superseded Docs
```bash
# Create archive directory
mkdir -p docs/archive/2025-10-28

# Move superseded motor docs
mv MOTOR_CALCULATION_FLOW.md docs/archive/2025-10-28/
mv FINAL_MOTOR_FLOW_CORRECTED.md docs/archive/2025-10-28/
```

### Phase 2: Move Reports
```bash
# Create reports directory if needed
mkdir -p docs/_reports/2025-10-28

# Move validation reports
mv FINAL_VALIDATION.md docs/_reports/2025-10-28/
mv RPI4_VALIDATION_REPORT.md docs/_reports/2025-10-28/
mv VALIDATION_SUMMARY.md docs/_reports/2025-10-28/

# Move diagnostic reports
mv COTTON_DETECTION_ISSUE_DIAGNOSIS.md docs/_reports/2025-10-28/
mv OFFLINE_DETECTION_TEST_REPORT.md docs/_reports/2025-10-28/
```

### Phase 3: Move Active Guides
```bash
# Move motor guides
mv MOTOR_INITIALIZATION_EXPLAINED.md docs/guides/
mv MOTOR_CONTROLLER_TEST_GUIDE.md docs/guides/
mv MOTOR_TEST_QUICK_REF.md docs/guides/
mv MOTOR_DEBUG.md docs/guides/
mv TRANSMISSION_FACTOR_FIX.md docs/guides/

# Move launch system docs
mv LAUNCH_CONSOLIDATION.md docs/guides/
mv LAUNCH_STATUS.md docs/guides/

# Move safety docs
mv EMERGENCY_STOP_README.md docs/guides/

# Move testing docs
mv TEST_WITHOUT_CAMERA.md docs/guides/
mv COTTON_DETECTION_SUMMARY.md docs/guides/
```

---

## Final Root Contents (8 files)

After cleanup:
```
/home/uday/Downloads/pragati_ros2/
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── MOTOR_DOCS_INDEX.md
├── HARDWARE_QUICKSTART.md
├── DOCUMENTATION_COMPREHENSIVE_REVIEW_2025-10-28.md
├── DOCUMENTATION_IMPROVEMENTS_COMPLETE_2025-10-28.md
└── BROKEN_LINKS_FIX_SUMMARY.md
```

---

## Impact Analysis

### Benefits
- **Cleaner root:** Only 8 essential files
- **Better organization:** Guides in guides/, reports in _reports/
- **Easier navigation:** Clear separation of concerns
- **Archived old docs:** Superseded files preserved

### Considerations
- Update MOTOR_DOCS_INDEX.md with new paths
- Update any cross-references in documentation
- Run link checker after moves

---

## Execution Strategy

Would you like me to:
1. **Execute all moves automatically** (full cleanup)
2. **Execute phase by phase** (incremental with verification)
3. **Generate shell script** (you execute manually)

Choose your preferred approach!
