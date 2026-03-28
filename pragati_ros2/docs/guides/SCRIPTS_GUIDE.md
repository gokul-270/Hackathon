# Pragati ROS2 Scripts Guide

## 📖 Quick Reference

### Build Scripts

**Primary**: `./build.sh`
- Full workspace build: `./build.sh`
- Clean build: `./build.sh --clean`
- Single package: `./build.sh --package yanthra_move`
- Interactive fast build: `./build.sh --fast`
- Parallel build: `./build.sh --jobs 8`
- RPi cross-compile: `./build.sh rpi [-p PKG] [-j N] [--clean]`

### Test Scripts

**Primary**: `./test.sh`
- Quick tests: `./test.sh --quick`
- Full test suite: `./test.sh --complete`
- Specific phase: `./test_suite/run_tests.sh 2`

### Launch Scripts

**Location**: `scripts/launch/`

Choose based on your needs:
- `launch.sh` - Interactive mode selection (recommended for dev)
- `launch_complete_system.sh` - Full system with detailed monitoring
- `launch_production.sh` - Production-grade with error handling
- `launch_robust.sh` - Anti-hang protection
- `launch_minimal.sh` - Minimal system for testing
- `launch_full_system.sh` - Full system with LazyROS integration

**Usage**:
```bash
# Interactive
./scripts/launch/launch.sh

# Direct mode
./scripts/launch/launch_production.sh
```

### Log Management Scripts

**Location**: `scripts/build/ or scripts/monitoring/ or scripts/maintenance/`

Two main tools:
1. `cleanup_logs.sh` - Comprehensive, standalone cleanup
2. `clean_logs.sh` - Advanced features via Python backend

**Usage**:
```bash
# Show log status
./scripts/monitoring/clean_logs.sh status

# Quick cleanup
./scripts/monitoring/cleanup_logs.sh

# Advanced cleanup with options
./scripts/monitoring/clean_logs.sh clean --days 7 --size 100
```

### Validation Scripts

**Location**: `scripts/validation/`

Key validators:
- `comprehensive_parameter_validation.py` - Parameter checks
- `comprehensive_service_validation.py` - Service tests
- `comprehensive_system_verification.py` - System integration
- `quick_validation.sh` - Quick sanity check
- `end_to_end_validation.sh` - Full E2E test

### Upload & Packaging

**Primary**: `scripts/build/create_upload_package.sh`

**Usage**:
```bash
./scripts/build/create_upload_package.sh
```

## 🔄 Migration from Old Scripts

### If you used...
- `scripts/build/fast_build.sh` → use `./build.sh --fast` (symlink retained for compatibility)
- `scripts/build/build.sh` → use `./build.sh` (legacy wrapper removed)
- `scripts/build/create_upload_package.sh` → unchanged

## 📂 Directory Structure

```
pragati_ros2/
├── build.sh                    # ← PRIMARY build script (all modes incl. RPi)
├── test.sh                     # ← PRIMARY test script
├── scripts/
│   ├── build/
│   │   ├── fast_build.sh            # symlink to ../../build.sh
│   │   ├── create_upload_package.sh
│   │   ├── debug_with_lazyros.sh
│   │   ├── explore_system_manual.sh
│   │   └── ros2_explorer.sh
│   ├── launch/                 # Launch variants (keep all)
│   ├── validation/             # Validation tools
│   ├── utils/                  # Utilities (log cleanup, etc.)
│   └── maintenance/            # Maintenance tools
└── tests/
    └── run_tests.sh            # Phase-based test manager
```

## ✅ What Changed

### Consolidated (Phases 1 & 7)
- ✅ Build scripts: 3 → 1 (with symlinks for compatibility)
- ✅ Upload package: 3 → 1 (with symlink)

### Kept As-Is (Documented)
- Launch scripts: All 6 variants kept (each has unique features)
- Log management: Both tools kept (different use cases)
- Validation scripts: All kept (complex, production-critical)
- Test infrastructure: Documented primary entry points

## 🗄️ Archive

All original scripts preserved in:
```
archive/scripts_consolidated_20250930_100349/
```

Can be restored anytime if needed.

## 📞 Need Help?

- Build issues: Check `./build.sh --help`
- Test issues: Check `./test.sh --help`
- Launch issues: Read `scripts/launch/*.sh` headers for descriptions

