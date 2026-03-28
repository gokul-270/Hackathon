# Scripts Consolidation Analysis
**Generated**: 2025-10-06
**Purpose**: Identify duplicate, obsolete, or consolidatable scripts

## Summary
- **Total Scripts**: 68 files
- **Script Directories**: 10 locations
- **All scripts active**: Modified within last 30 days

---

## 🔧 Category 1: Cleanup Scripts (7 files)

### Potential Duplicates:
| Script | Location | Purpose Guess |
|--------|----------|---------------|
| `cleanup_ros2.sh` | scripts/essential/ | **KEEP** - Core ROS2 cleanup |
| `clean_logs.sh` | scripts/maintenance/ | Log cleanup |
| `cleanup_logs.sh` | scripts/maintenance/ | Log cleanup (duplicate?) |
| `daily_cleanup.sh` | scripts/maintenance/ | Scheduled cleanup |
| `cleanup_scripts.sh` | scripts/maintenance/ | Script cleanup |
| `cleanup_duplicate_scripts.sh` | scripts/utils/ | Duplicate removal |
| `cleanup_launch_system.sh` | scripts/maintenance/ | Launch system specific |

**Recommendation**: 
- Compare `clean_logs.sh` vs `cleanup_logs.sh` - likely identical
- Check if `daily_cleanup.sh` calls other cleanup scripts (orchestrator)
- Consolidate into 3-4 scripts maximum

---

## 🚀 Category 2: Launch Scripts (9 files)

| Script | Location | Size Check Needed |
|--------|----------|-------------------|
| `launch.sh` | scripts/launch/ | Base launcher? |
| `launch_complete_system.sh` | scripts/launch/ | Full system |
| `launch_full_system.sh` | scripts/launch/ | Full system (duplicate?) |
| `launch_minimal.sh` | scripts/launch/ | **KEEP** - Minimal mode |
| `launch_production.sh` | scripts/launch/ | **KEEP** - Production mode |
| `launch_robust.sh` | scripts/launch/ | Robust mode |
| `launch_system.py` | scripts/launch/ | **KEEP** - Python launcher |
| `run_yanthra_with_enter.sh` | scripts/launch/ | Interactive mode |
| `test_launch_simple.sh` | scripts/validation/ | Test launcher |

**Recommendation**:
- Compare `launch_complete_system.sh` vs `launch_full_system.sh` vs `launch_robust.sh`
- Likely 2-3 of these are very similar
- Keep: `launch_production.sh`, `launch_minimal.sh`, `launch_system.py`
- Merge or remove duplicates

---

## ✅ Category 3: Validation/Test Scripts (26 files!)

### High Priority Review:
```
scripts/validation/colleague_workflow_integration_test.py
scripts/validation/comprehensive_parameter_validation.py
scripts/validation/comprehensive_service_validation.py
scripts/validation/comprehensive_system_verification.py
scripts/validation/corrected_flow_validation.py
scripts/validation/critical_integration_validation.py
scripts/validation/end_to_end_validation.sh
scripts/validation/prove_complete_flow.py
scripts/validation/quick_validation.sh
scripts/validation/robust_service_stress_test.py
scripts/validation/runtime_parameter_verification.py
... and 15 more
```

**Issue**: Many scripts have overlapping names suggesting similar functionality
- "comprehensive_X" scripts (3+)
- "validate_X" vs "verify_X" vs "validation_X"
- Multiple "flow" validation scripts

**Recommendation**:
- Review each script header/docstring for purpose
- Create a matrix of what each script tests
- Consolidate into 5-8 core validation scripts covering:
  1. Quick validation
  2. Comprehensive system validation
  3. Parameter validation
  4. Service validation
  5. Integration testing
  6. Stress testing

---

## 🛠️ Category 4: Utils Scripts (17 files)

### Already Flagged as Likely Duplicates:
- Log management: `clean_logs.sh`, `cleanup_logs.sh`, `rotate_logs.sh`, `log_manager.py`
- Cleanup: `cleanup_duplicate_scripts.sh`, `cleanup_scripts.sh`, `daily_cleanup.sh`

### Maintenance/One-time Use:
- `add_copyright_odrive.sh` - One-time fix?
- `add_missing_includes.sh` - One-time fix?
- `fix_header_guards.sh` - One-time fix?
- `fix_tf_migration.sh` - Migration complete?
- `organize_documentation.sh` - Periodic maintenance

**Recommendation**:
- Archive one-time migration/fix scripts
- Consolidate log management into single `log_manager` tool
- Keep: `daily_cleanup.sh`, `performance_dashboard.sh`, `ros2_explorer.sh`

---

## 📦 Category 5: Essential Scripts (4 files) - KEEP ALL

| Script | Purpose |
|--------|---------|
| `auto_log_manager.sh` | Automatic log management |
| `cleanup_ros2.sh` | Core ROS2 cleanup |
| `pragati_commands.sh` | Common commands |
| `SortCottonCoordinates.py` | Cotton sorting logic |

**Status**: ✅ All appear essential - no changes needed

---

## 🔍 Next Steps

### Phase 1: Safe Identification
1. ✅ Compare file sizes and checksums for suspected duplicates
2. ✅ Check script headers/docstrings for declared purposes
3. ✅ Search for script references in other scripts/docs

### Phase 2: Content Analysis
1. For each category, compare script contents
2. Identify true duplicates (100% identical)
3. Identify similar scripts (80%+ overlap)
4. Document which scripts call which other scripts

### Phase 3: Consolidation Plan
1. Create keep/merge/archive decisions
2. Update any references to merged scripts
3. Move archived scripts to `docs/archive_scripts/`

---

## Commands to Run for Detailed Analysis

```bash
# Find duplicate files by content
cd /home/uday/Downloads/pragati_ros2/scripts
find . -type f \( -name "*.sh" -o -name "*.py" \) -exec md5sum {} \; | sort | uniq -w32 -d

# Compare similar script sizes
ls -lh utils/clean*.sh utils/cleanup*.sh

# Check for script references
grep -r "cleanup_logs\|clean_logs" scripts/ --include="*.sh" --include="*.py"
```

---

## Risk Assessment
- **Low Risk**: Utils one-time scripts (can archive safely)
- **Medium Risk**: Cleanup scripts (need to check dependencies)
- **High Risk**: Launch scripts (actively used in production)
- **Critical**: Validation scripts (need careful review - may be used in CI/CD)
