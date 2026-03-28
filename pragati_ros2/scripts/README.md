# Scripts Directory

Organized collection of specialized scripts for testing, utilities, fixes, and maintenance.

---

## Directory Structure

```
scripts/
├── testing/           # Test scripts for specific components
├── utils/             # Utility scripts for monitoring and simulation
├── fixes/             # One-time fix scripts
└── maintenance/       # Maintenance and tooling scripts
```

---

## Testing Scripts (`testing/`)

Scripts for testing specific components or scenarios:

| Script | Purpose | Usage |
|--------|---------|-------|
| **test_offline_cotton_detection.sh** | Test cotton detection without camera | `./scripts/testing/test_offline_cotton_detection.sh` |
| **test_ros1_cotton_detect.sh** | Test ROS1 cotton detection locally | `./scripts/testing/test_ros1_cotton_detect.sh` |
| **test_ros1_cotton_detect_remote.sh** | Test ROS1 cotton detection remotely | `./scripts/testing/test_ros1_cotton_detect_remote.sh` |
| **test_start_switch.sh** | Test start switch functionality | `./scripts/testing/test_start_switch.sh` |
| **test_cotton_detection_publisher.py** | Publish fake cotton detections | `./scripts/testing/test_cotton_detection_publisher.py` |

---

## Utility Scripts (`utils/`)

Helper scripts for monitoring and simulation:

| Script | Purpose | Usage |
|--------|---------|-------|
| **monitor_motor_positions.sh** | Monitor motor positions in real-time | `./scripts/utils/monitor_motor_positions.sh` |
| **publish_fake_cotton.py** | Publish simulated cotton detection data | `./scripts/utils/publish_fake_cotton.py` |

---

## Fix Scripts (`fixes/`)

One-time scripts to fix specific issues:

| Script | Purpose | Usage |
|--------|---------|-------|
| **fix_simulation_mode_on_pi.sh** | Fix simulation mode configuration on RPi | `./scripts/fixes/fix_simulation_mode_on_pi.sh` |

---

## Maintenance Scripts (`maintenance/`)

Scripts for documentation and codebase maintenance:

| Script | Purpose | Usage |
|--------|---------|-------|
| **fix_broken_links.py** | Fix broken markdown links in docs | `python3 scripts/maintenance/fix_broken_links.py` |

---

## Core Scripts (Root Directory)

Frequently used scripts remain in the project root for easy access:

| Script | Purpose |
|--------|---------|
| **build.sh** | Main build script (includes RPi cross-compile mode) |
| **install_deps.sh** | Install dependencies |
| **test.sh** | Run main test suite |
| **test_complete_system.sh** | Complete system integration test |
| **emergency_motor_stop.sh** | Emergency motor stop (safety) |
| **sync_to_rpi.sh** | Sync codebase to Raspberry Pi |

---

## Usage Guidelines

### Running Scripts from Root

Since scripts are now in subdirectories, use relative paths:

```bash
# Testing scripts
./scripts/testing/test_offline_cotton_detection.sh

# Utility scripts
./scripts/utils/monitor_motor_positions.sh

# Maintenance scripts
python3 scripts/maintenance/fix_broken_links.py
```

### Running Core Scripts

Core scripts remain directly accessible:

```bash
./build.sh
./test.sh
./emergency_motor_stop.sh
```

---

## Adding New Scripts

Follow this organization pattern:

1. **Testing scripts** → `scripts/testing/`
   - Component tests
   - Integration tests
   - Scenario tests

2. **Utility scripts** → `scripts/utils/`
   - Monitoring tools
   - Simulation helpers
   - Data generators

3. **Fix scripts** → `scripts/fixes/`
   - One-time fixes
   - Migration scripts
   - Patch scripts

4. **Maintenance scripts** → `scripts/maintenance/`
   - Documentation tools
   - Code analysis
   - Cleanup utilities

5. **Core operations** → Root directory
   - Build scripts
   - Main test runners
   - Deployment scripts
   - Safety/emergency scripts

---

## Script Conventions

### Naming
- Use descriptive names: `test_<component>_<scenario>.sh`
- Use underscores: `monitor_motor_positions.sh`
- Include language extension: `.sh`, `.py`

### Permissions
- Make scripts executable: `chmod +x script_name.sh`
- Python scripts should have shebang: `#!/usr/bin/env python3`
- Shell scripts should have shebang: `#!/bin/bash`

### Documentation
- Add header comment with purpose and usage
- Include example commands
- Document required dependencies

---

## Migration Notes

**Previous Location:** All scripts were in root directory  
**Current Location:** Organized in `scripts/` subdirectories  
**Migration Date:** 2025-10-28

### What Changed
- 9 specialized scripts moved from root to `scripts/`
- 7 core operational scripts remain in root
- New directory structure created for better organization

### Updating References
If you have scripts or docs that reference moved scripts, update paths:
- Old: `./test_offline_cotton_detection.sh`
- New: `./scripts/testing/test_offline_cotton_detection.sh`

---

## Related Documentation

- **Root README.md** - Main project documentation
- **docs/guides/** - Usage and testing guides
- **MOTOR_DOCS_INDEX.md** - Motor control documentation hub

---

**Last Updated:** 2025-10-28  
**Total Scripts:** 16 (7 core + 9 organized)
