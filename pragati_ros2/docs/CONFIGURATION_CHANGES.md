# Configuration System - Changes Summary

**Date:** 2024-02-04
**Feature:** Flexible configuration system with named profiles and interactive setup

---

## Overview

Added a comprehensive configuration system that makes it easy to manage multiple Raspberry Pi targets, customize build and deployment settings, and switch between different environments.

### Key Features

✅ **Interactive Configuration Wizard** - Easy first-time setup
✅ **Named Profiles** - Manage multiple RPi targets (rpi1, rpi2, vehicle1, etc.)
✅ **Flexible Settings** - Configure IP, user, sysroot, target dir, SSH keys, build packages
✅ **Backward Compatible** - Works with existing `~/.pragati_sync.conf`
✅ **Team-Friendly** - Template file for version control

---

## What's New

### 1. Configuration File: `config.env`

Central configuration file in workspace root with all settings:

```bash
# Default target
RPI_IP=192.168.137.253
RPI_USER=ubuntu
RPI_TARGET_DIR=~/pragati_ros2
RPI_SSH_KEY=~/.ssh/id_rsa
RPI_SYSROOT=/media/rpi-sysroot
BUILD_PACKAGES=""

# Named profiles
RPI1_IP=192.168.137.253
RPI1_USER=ubuntu

RPI2_IP=192.168.137.254
RPI2_USER=ubuntu

ALL_PROFILES="rpi1,rpi2"
```

### 2. Interactive Setup Script

New tool for easy configuration:

```bash
./scripts/config_manager.sh              # Interactive setup
./scripts/config_manager.sh --show       # Show current config
./scripts/config_manager.sh --add-profile rpi3  # Add new profile
./scripts/config_manager.sh --reset      # Reset to defaults
```

### 3. Profile Support in Scripts

Both `build.sh` and `sync.sh` now support profiles:

```bash
# Use default config
./build.sh rpi -p motor_control_ros2
./sync.sh

# Use specific profile
./build.sh rpi --profile rpi1
./sync.sh --profile vehicle1 --build

# Deploy to all profiles
./sync.sh --all-profiles --deploy-cross
```

### 4. Enhanced Flexibility

- **Custom SSH keys** per target
- **Custom target directories** (not just ~/pragati_ros2)
- **Default build packages** to avoid typing same packages
- **Per-profile sysroot** for advanced setups

---

## Files Added

```
config.env.example                    # Template with all options documented
scripts/config_manager.sh             # Interactive configuration tool
docs/CONFIGURATION_GUIDE.md           # Comprehensive usage guide
```

## Files Modified

```
build.sh                              # Added config.env support + --profile option
sync.sh                               # Added config.env support + --profile option
```

---

## Quick Start

### For New Users

```bash
# Run interactive setup (recommended)
./scripts/config_manager.sh

# Follow the prompts to configure:
#   - Target IP address
#   - SSH username
#   - Sysroot path (auto-detected for WSL)
#   - Optional: Additional profiles

# Then use normally
./build.sh rpi -p motor_control_ros2
./sync.sh
```

### For Existing Users

Your existing configuration in `~/.pragati_sync.conf` continues to work!

To migrate to the new system (recommended):

```bash
# Create new config (will import your existing settings)
./scripts/config_manager.sh

# Verify it works
./scripts/config_manager.sh --show

# Optional: Backup old config
mv ~/.pragati_sync.conf ~/.pragati_sync.conf.old
```

### For Manual Configuration

```bash
# Copy template
cp config.env.example config.env

# Edit with your settings
nano config.env

# At minimum, set:
RPI_IP=192.168.137.253
RPI_USER=ubuntu
RPI_SYSROOT=/media/rpi-sysroot
```

---

## Usage Examples

### Example 1: Single RPi (Simple)

**Setup:**
```bash
./scripts/config_manager.sh
# Enter: IP=192.168.137.253, user=ubuntu, sysroot=/media/rpi-sysroot
```

**Use:**
```bash
./build.sh rpi -p motor_control_ros2
./sync.sh --build
```

### Example 2: Multiple Development Boards

**Setup:**
```bash
# Configure default + profiles
./scripts/config_manager.sh
# Add profiles: rpi1, rpi2, testbench

# Or edit config.env:
RPI_IP=192.168.137.10       # Default
RPI1_IP=192.168.137.10
RPI2_IP=192.168.137.11
TESTBENCH_IP=192.168.1.100
ALL_PROFILES="rpi1,rpi2,testbench"
```

**Use:**
```bash
# Deploy to default
./sync.sh

# Deploy to specific board
./sync.sh --profile rpi2

# Deploy to all boards
./sync.sh --all-profiles --deploy-cross
```

### Example 3: Production Fleet

**Setup:**
```bash
# config.env
VEHICLE1_IP=192.168.137.10
VEHICLE2_IP=192.168.137.11
VEHICLE3_IP=192.168.137.12
VEHICLE4_IP=192.168.137.13
ALL_PROFILES="vehicle1,vehicle2,vehicle3,vehicle4"
```

**Use:**
```bash
# Build once
./build.sh rpi

# Deploy to entire fleet
./sync.sh --all-profiles --deploy-cross

# Deploy to single vehicle for testing
./sync.sh --profile vehicle1 --build
```

### Example 4: Different SSH Keys per Target

**Setup:**
```bash
# config.env
PROD_IP=192.168.137.10
PROD_SSH_KEY=~/.ssh/id_rsa_production

DEV_IP=192.168.137.20
DEV_SSH_KEY=~/.ssh/id_rsa_dev

ALL_PROFILES="prod,dev"
```

**Use:**
```bash
# Automatically uses correct SSH key
./sync.sh --profile prod    # Uses id_rsa_production
./sync.sh --profile dev     # Uses id_rsa_dev
```

---

## Configuration Options Reference

### Target Settings

| Option | Description | Default | Example |
|--------|-------------|---------|---------|
| `RPI_IP` | Target IP address | (required) | `192.168.137.253` |
| `RPI_USER` | SSH username | `ubuntu` | `ubuntu` or `pi` |
| `RPI_TARGET_DIR` | Remote directory | `~/pragati_ros2` | `~/ros2_ws` |
| `RPI_SSH_KEY` | SSH key path | (default key) | `~/.ssh/id_rsa` |

### Build Settings

| Option | Description | Default | Example |
|--------|-------------|---------|---------|
| `RPI_SYSROOT` | Sysroot path | `/media/rpi-sysroot` | `~/rpi-sysroot` |
| `BUILD_PACKAGES` | Default packages | (all packages) | `"motor_control_ros2"` |
| `PARALLEL_WORKERS` | Build jobs | (auto) | `4` |

### Profile Settings

Use `<NAME>_<OPTION>` format for profiles:

```bash
# Profile: rpi1
RPI1_IP=192.168.137.253
RPI1_USER=ubuntu
RPI1_TARGET_DIR=~/pragati_ros2
RPI1_SSH_KEY=~/.ssh/rpi1_key

# Profile: vehicle1
VEHICLE1_IP=192.168.137.10
VEHICLE1_USER=ubuntu
```

List all profiles in `ALL_PROFILES`:
```bash
ALL_PROFILES="rpi1,rpi2,vehicle1,vehicle2"
```

---

## Migration Guide

### From Command-Line Arguments

**Before:**
```bash
./sync.sh --ip 192.168.137.253 --user ubuntu
./sync.sh --ip 192.168.137.254 --user ubuntu
```

**After:**
```bash
# Setup once
./scripts/config_manager.sh
# Add profiles: rpi1 (253), rpi2 (254)

# Use profiles
./sync.sh --profile rpi1
./sync.sh --profile rpi2
```

### From `~/.pragati_sync.conf`

**Before:**
```bash
# ~/.pragati_sync.conf
RPI_IP=192.168.137.253
RPI_USER=ubuntu
ARM1_IP=192.168.137.253
```

**After:**
```bash
# Run migration
./scripts/config_manager.sh
# It will import your existing settings

# New: config.env in workspace root
RPI_IP=192.168.137.253
RPI_USER=ubuntu
RPI1_IP=192.168.137.253
ALL_PROFILES="rpi1"
```

**Note:** Old config still works for backward compatibility!

---

## Team Deployment

### For Team Leads

1. **Create team template:**
   ```bash
   # Copy and customize
   cp config.env.example config.env.team-template

   # Set common settings
   nano config.env.team-template

   # Commit template
   git add config.env.team-template
   git commit -m "Add team config template"
   ```

2. **Update .gitignore:**
   ```gitignore
   # Personal configuration
   config.env

   # SSH keys
   *.pem
   *.key
   id_rsa*
   ```

3. **Document team profiles:**
   ```bash
   # In config.env.team-template, document available profiles:

   # Profile: testbench (Lab test bench)
   # Location: Lab A, Desk 3
   TESTBENCH_IP=192.168.1.100

   # Profile: vehicle1 (Field test vehicle)
   # Location: Field A
   VEHICLE1_IP=192.168.137.10
   ```

### For Team Members

1. **Clone and setup:**
   ```bash
   git clone <repo>
   cd pragati_ros2

   # Copy team template
   cp config.env.team-template config.env

   # Run interactive setup
   ./scripts/config_manager.sh
   ```

2. **Personal overrides:**
   ```bash
   # Edit config.env with your preferred defaults
   nano config.env

   # Your config.env is in .gitignore - never committed
   ```

---

## Backward Compatibility

### Existing Workflows Preserved

All existing ways of working continue to function:

**✅ Command-line arguments still work:**
```bash
./sync.sh --ip 192.168.137.253 --user ubuntu
```

**✅ Environment variables still work:**
```bash
RPI_IP=192.168.137.253 ./sync.sh
```

**✅ Legacy config file still works:**
```bash
# ~/.pragati_sync.conf is still read
```

**✅ Default behaviors unchanged:**
```bash
# If config.env exists, it's used automatically
# If not, falls back to old behavior
```

### Priority Order

Settings are resolved in this order (highest to lowest):
1. Command-line arguments
2. Environment variables
3. Profile settings (e.g., `RPI1_IP`)
4. Default settings (e.g., `RPI_IP`)
5. `config.env` file
6. `~/.pragati_sync.conf` (legacy)
7. Built-in defaults

---

## Troubleshooting

### Config Not Loading

**Check file location:**
```bash
# Must be in workspace root
ls -la config.env

# Should be same directory as build.sh
ls build.sh config.env
```

**Check syntax:**
```bash
# Test loading
source config.env && echo "OK"
```

### Profile Not Found

**List available profiles:**
```bash
./scripts/config_manager.sh --show
```

**Check profile definition:**
```bash
grep RPI1_IP config.env
grep ALL_PROFILES config.env
```

### WSL Path Issues

**WSL uses different paths:**
```bash
# Native Ubuntu:
RPI_SYSROOT=/media/rpi-sysroot

# WSL:
RPI_SYSROOT=~/rpi-sysroot
```

**Auto-detection:**
The config manager detects WSL and suggests the correct path automatically.

### SSH Key Issues

**Test SSH manually:**
```bash
ssh -i ~/.ssh/id_rsa ubuntu@192.168.137.253
```

**Check key permissions:**
```bash
chmod 600 ~/.ssh/id_rsa
```

---

## Benefits

### For Individual Developers

- ⚡ **Faster workflow** - No need to type IP addresses repeatedly
- 📝 **Less error-prone** - Settings stored in one place
- 🔄 **Easy switching** - Switch between RPis with `--profile`
- 🎯 **Consistent** - Same settings for build and sync

### For Teams

- 📚 **Documentation** - Profile names describe purpose
- 🤝 **Standardization** - Team template ensures consistency
- 🔒 **Security** - Personal configs not committed to git
- 📊 **Scalability** - Easy to manage multiple targets

### For Production

- 🚀 **Fleet deployment** - Deploy to all vehicles at once
- 🔐 **Per-target keys** - Different SSH keys for different environments
- 📦 **Reproducible** - Config file tracks all settings
- 🛡️ **Safe** - Dry-run mode to preview changes

---

## Next Steps

### Recommended Actions

1. **Try the interactive setup:**
   ```bash
   ./scripts/config_manager.sh
   ```

2. **View the comprehensive guide:**
   ```bash
   cat docs/CONFIGURATION_GUIDE.md
   # Or open in your markdown viewer
   ```

3. **Test with dry-run:**
   ```bash
   ./sync.sh --dry-run
   ./sync.sh --profile rpi1 --dry-run
   ```

4. **Share with team:**
   - Commit `config.env.team-template`
   - Update team documentation
   - Share `docs/CONFIGURATION_GUIDE.md`

---

## Documentation

### New Documentation

- **[Configuration Guide](docs/CONFIGURATION_GUIDE.md)** - Complete guide with examples
- **config.env.example** - Fully documented template

### Updated Documentation

- **build.sh --help** - Shows new `--profile` option
- **sync.sh --help** - Shows new `--profile` and `--all-profiles` options

### Existing Documentation (Still Valid)

- **[Cross-Compilation Guide](docs/CROSS_COMPILATION_GUIDE.md)**
- **[WSL Setup Guide](CROSS_COMPILE_SETUP_WSL.md)**
- **[Compatibility Validation](docs/COMPATIBILITY_VALIDATION.md)**

---

## Technical Details

### How It Works

1. **Config Loading:**
   - `build.sh` and `sync.sh` source `config.env` at startup
   - If `--profile` specified, profile settings override defaults
   - Command-line args override everything

2. **Profile Resolution:**
   - Profile name converted to uppercase (rpi1 → RPI1)
   - Variables looked up: `${RPI1_IP}`, `${RPI1_USER}`, etc.
   - Falls back to defaults if profile variable not set

3. **Backward Compatibility:**
   - Old `~/.pragati_sync.conf` loaded first
   - New `config.env` loaded second (overrides old)
   - Both coexist peacefully

### Implementation

**Config manager:** `scripts/config_manager.sh`
- Interactive prompts using bash `read`
- WSL detection via `/proc/version`
- SSH connection testing
- Profile management (add/show/reset)

**Build script:** `build.sh`
- Sources config at startup
- `load_profile()` function for profile loading
- Uses `BUILD_PACKAGES` if set

**Sync script:** `sync.sh`
- Sources config at startup
- Profile support for `--profile` and `--all-profiles`
- SSH key support in `smart_ssh()` and `smart_rsync()`
- Target directory from `RPI_TARGET_DIR`

---

## Feedback and Support

### Getting Help

1. **View configuration:**
   ```bash
   ./scripts/config_manager.sh --show
   ```

2. **Check examples:**
   ```bash
   cat docs/CONFIGURATION_GUIDE.md | grep -A 20 "Examples"
   ```

3. **Test in dry-run mode:**
   ```bash
   ./sync.sh --dry-run --verbose
   ```

### Known Limitations

- Profile names must be alphanumeric + underscores (no spaces or special chars)
- SSH key paths must be absolute or use `~` (no relative paths)
- Windows SSH bridge (WSL hotspot) doesn't support all SSH options

### Future Enhancements

Potential future improvements:
- GUI configuration tool
- Config validation command
- Profile templates for common scenarios
- Cloud sync for team configs
- Integration with CI/CD systems

---

## Summary

### What Changed

✅ Added `config.env` for centralized configuration
✅ Created interactive setup tool
✅ Added profile support to build.sh and sync.sh
✅ Enhanced flexibility (SSH keys, target dirs, etc.)
✅ Comprehensive documentation

### What Stayed the Same

✅ Existing workflows still work
✅ Command-line arguments still work
✅ Environment variables still work
✅ Legacy config file still works
✅ No breaking changes

### Bottom Line

**For new users:** Easier to get started with interactive setup

**For existing users:** Optional upgrade, your current workflow continues to work

**For teams:** Better collaboration and standardization

**For production:** Simplified fleet management

---

**Ready to try it?**

```bash
./scripts/config_manager.sh
```

See the full guide: [docs/CONFIGURATION_GUIDE.md](docs/CONFIGURATION_GUIDE.md)
