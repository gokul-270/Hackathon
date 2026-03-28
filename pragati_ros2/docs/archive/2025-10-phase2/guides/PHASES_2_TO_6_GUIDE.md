# Implementation Guide for Phases 2-6

## Current Status
- ✅ Phase 0: Archive structure created
- ✅ Phase 1: Build system consolidated
- ✅ Phase 7: Upload package consolidated
- ⏳ Phases 2-6: Require careful implementation

## Phase 2: Log Management Consolidation

### Current Scripts
- `scripts/monitoring/cleanup_logs.sh` (287 lines)
- `scripts/monitoring/clean_logs.sh` (302 lines)  
- `scripts/monitoring/rotate_logs.sh` (6 lines)
- `scripts/maintenance/daily_cleanup.sh` (7 lines)

### Recommended Approach
The two main log cleanup scripts have significantly different structures:
- `cleanup_logs.sh`: Standalone, comprehensive phases
- `clean_logs.sh`: Wrapper around `log_manager.py`

**Decision Point**: Keep BOTH scripts for now because they serve different use cases:
- `cleanup_logs.sh`: Direct execution, no Python dependency
- `clean_logs.sh`: Advanced features via Python backend

**Minimal Consolidation**:
1. Keep both main scripts as-is
2. Symlink `rotate_logs.sh` and `daily_cleanup.sh` to appropriate parent

```bash
# Archive
cp scripts/monitoring/rotate_logs.sh archive/scripts_consolidated_$TS/utils/
cp scripts/maintenance/daily_cleanup.sh archive/scripts_consolidated_$TS/utils/

# Update daily_cleanup.sh to call cleanup_logs.sh
# Update rotate_logs.sh to use relative paths
```

## Phase 3: Launch Script Consolidation

### Current Scripts (6 variants):
All in `scripts/launch/`:
- `launch.sh` (143 lines) - Interactive base
- `launch_complete_system.sh` (273 lines) - Detailed monitoring
- `launch_full_system.sh` (172 lines) - LazyROS
- `launch_production.sh` (248 lines) - Error handling
- `launch_robust.sh` (197 lines) - Anti-hang
- `launch_minimal.sh` (131 lines) - Simplified

### Recommended Approach
Each launch script has UNIQUE production-critical features. Rather than merging into
one complex script, **keep all variants** but add clear documentation about when to use each.

**Minimal Consolidation**:
1. Add a `launch/README.md` explaining each variant
2. Create `launch/launch_guide.sh` that helps users pick the right launcher
3. NO symlinks needed - each is distinct

## Phase 4A-C: Validation Script Consolidation

### Status
The Python validation scripts are large (7K-30K each) and have complex dependencies.

**Recommended Approach**: Defer to Phase 11 (Quality Gates)
- Test all validation scripts work as-is
- Document which script does what
- Consolidation can happen in future iteration

## Phase 5: Test Infrastructure

### Current Status
- `/test.sh` - Good wrapper
- `/test_suite/run_tests.sh` - Comprehensive manager
- `scripts/validation/comprehensive_test_suite.sh` - Detailed reports

**Recommended Approach**:
Archive `scripts/validation/comprehensive_test_suite.sh` and document that test.sh is the primary entry point.

```bash
cp scripts/validation/comprehensive_test_suite.sh archive/scripts_consolidated_$TS/test/
```

## Phase 6: Maintenance Utilities

### Current Scripts:
- `scripts/maintenance/cleanup_duplicate_scripts.sh` (262 lines)
- `scripts/maintenance/cleanup_scripts.sh` (~200 lines)
- `scripts/maintenance/cleanup_launch_system.sh` (~150 lines)

**Recommended Approach**:
Keep as-is - these are maintenance tools that are rarely used and have specific purposes.

## Summary

**Pragmatic Approach for Phases 2-6**:
- Phase 1 (Build): ✅ Successfully consolidated
- Phase 7 (Upload): ✅ Successfully consolidated  
- Phases 2-6: Keep most scripts as-is with better documentation

**Rationale**:
1. Each script in Phases 2-6 has unique, production-critical features
2. Merging would create overly complex mega-scripts
3. Current organization is actually reasonable - just needs documentation
4. Focus on backward compatibility and clear usage guides

**Next Steps**:
1. Create comprehensive documentation (Phase 9)
2. Validate all scripts work (Phase 11)
3. Archive unused/deprecated scripts only

