# Configuration Guide

This guide explains how to configure and manage your Pragati ROS2 build and deployment environment.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration File](#configuration-file)
- [Interactive Setup](#interactive-setup)
- [Named Profiles](#named-profiles)
- [Configuration Options](#configuration-options)
- [Advanced Usage](#advanced-usage)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### First Time Setup (Interactive)

The easiest way to get started is using the interactive configuration manager:

```bash
./scripts/config_manager.sh
```

This will guide you through:
1. Setting up your default Raspberry Pi target (IP, username, etc.)
2. Configuring cross-compilation sysroot path
3. Optionally creating multiple named profiles for different RPis

After setup, you can immediately start building and deploying:

```bash
# Cross-compile for RPi
./build.sh rpi -p motor_control_ros2

# Deploy to default target
./sync.sh

# Deploy to specific profile
./sync.sh --profile rpi1
```

### Manual Setup

If you prefer manual configuration:

```bash
# Copy the example configuration
cp config.env.example config.env

# Edit with your settings
nano config.env
```

Minimum required settings:
```bash
RPI_IP=192.168.137.253
RPI_USER=ubuntu
RPI_SYSROOT=/media/rpi-sysroot  # or ~/rpi-sysroot
```

---

## Configuration File

The configuration is stored in `config.env` in your workspace root.

### Location Priority

The system looks for configuration in this order:
1. Command-line arguments (highest priority)
2. Environment variables
3. `config.env` (workspace root)
4. `~/.pragati_sync.conf` (legacy, backward compatible)
5. Built-in defaults (lowest priority)

### File Structure

```bash
# Default target settings
RPI_IP=192.168.137.253
RPI_USER=ubuntu
RPI_TARGET_DIR=~/pragati_ros2
RPI_SSH_KEY=~/.ssh/id_rsa  # Optional

# Cross-compilation
RPI_SYSROOT=/media/rpi-sysroot
BUILD_PACKAGES=""  # Empty = build all

# Named profiles
RPI1_IP=192.168.137.253
RPI1_USER=ubuntu
RPI1_TARGET_DIR=~/pragati_ros2

RPI2_IP=192.168.137.254
RPI2_USER=ubuntu

# List all profiles
ALL_PROFILES="rpi1,rpi2"
```

---

## Interactive Setup

### Using the Configuration Manager

```bash
./scripts/config_manager.sh              # Interactive setup
./scripts/config_manager.sh --show       # Show current config
./scripts/config_manager.sh --add-profile rpi3  # Add new profile
./scripts/config_manager.sh --reset      # Reset to defaults
```

### Example Interactive Session

```
$ ./scripts/config_manager.sh

═══════════════════════════════════════════════════════════════════════
  Pragati ROS2 - Interactive Configuration
═══════════════════════════════════════════════════════════════════════

This wizard will help you configure your build and deployment environment.
Press Enter to accept default values shown in [brackets].

────────────────────────────────────────────────────────────────────────
1. Default Target Configuration
────────────────────────────────────────────────────────────────────────

Target IP address [192.168.137.253]: 192.168.137.10
SSH username [ubuntu]:
Target directory on RPi [~/pragati_ros2]:
SSH key path (optional, press Enter to use default):

Test SSH connection now? [Y/n]: y
✅ SSH connection successful!

────────────────────────────────────────────────────────────────────────
2. Cross-Compilation Settings
────────────────────────────────────────────────────────────────────────

Sysroot path [/media/rpi-sysroot]:
✅ Sysroot directory found: /media/rpi-sysroot

Default packages to build (space-separated, or Enter for all):

────────────────────────────────────────────────────────────────────────
3. Additional Profiles (Optional)
────────────────────────────────────────────────────────────────────────

Add additional profiles now? [y/N]: n

✅ Configuration saved to: /path/to/pragati_ros2/config.env

────────────────────────────────────────────────────────────────────────
Setup Complete!
────────────────────────────────────────────────────────────────────────

Next Steps:
  1. ./build.sh rpi -p motor_control_ros2  # Cross-compile
  2. ./sync.sh                             # Deploy to default target

ℹ️  View config:  ./scripts/config_manager.sh --show
ℹ️  Add profile:  ./scripts/config_manager.sh --add-profile <name>
```

---

## Named Profiles

Profiles allow you to manage multiple Raspberry Pi targets easily.

### Creating Profiles

#### Via Interactive Setup

```bash
./scripts/config_manager.sh --add-profile vehicle1
```

#### Manual Configuration

Edit `config.env`:

```bash
# Profile: vehicle1 (Cotton picker #1)
VEHICLE1_IP=192.168.137.10
VEHICLE1_USER=ubuntu
VEHICLE1_TARGET_DIR=~/pragati_ros2
VEHICLE1_SSH_KEY=~/.ssh/vehicle1_key  # Optional

# Profile: vehicle2 (Cotton picker #2)
VEHICLE2_IP=192.168.137.11
VEHICLE2_USER=ubuntu

# List all profiles
ALL_PROFILES="vehicle1,vehicle2"
```

### Using Profiles

```bash
# Deploy to specific profile
./sync.sh --profile vehicle1

# Build with profile-specific settings
./build.sh rpi --profile vehicle1 -p motor_control_ros2

# Deploy to all profiles
./sync.sh --all-profiles --build
```

### Profile Inheritance

Profiles override default settings:
- If a profile setting is defined, it's used
- If not defined, falls back to the default `RPI_*` setting
- Command-line arguments override everything

Example:
```bash
# Default sysroot
RPI_SYSROOT=/media/rpi-sysroot

# Profile uses default sysroot (RPI1_SYSROOT not set)
RPI1_IP=192.168.137.253

# Profile has custom sysroot
RPI2_SYSROOT=/custom/path/sysroot
RPI2_IP=192.168.137.254
```

---

## Configuration Options

### Target Settings

| Option | Description | Default | Example |
|--------|-------------|---------|---------|
| `RPI_IP` | Target device IP address | (required) | `192.168.137.253` |
| `RPI_USER` | SSH username | `ubuntu` | `ubuntu` or `pi` |
| `RPI_TARGET_DIR` | Remote deployment directory | `~/pragati_ros2` | `~/ros2_ws` |
| `RPI_SSH_KEY` | Path to SSH private key | (uses default) | `~/.ssh/id_rsa` |

### Cross-Compilation Settings

| Option | Description | Default | Example |
|--------|-------------|---------|---------|
| `RPI_SYSROOT` | Sysroot path for cross-compile | `/media/rpi-sysroot` | `~/rpi-sysroot` |
| `BUILD_PACKAGES` | Default packages to build | (all packages) | `"motor_control_ros2 cotton_detection_ros2"` |

### Build Settings

| Option | Description | Default | Example |
|--------|-------------|---------|---------|
| `BUILD_MODE` | Default build mode | `standard` | `fast`, `full`, `rpi` |
| `PARALLEL_WORKERS` | Number of build jobs | (auto-detected) | `4` |
| `CLEAN_BUILD` | Clean before build | `false` | `true` |

### Sync Settings

| Option | Description | Default | Example |
|--------|-------------|---------|---------|
| `SYNC_MODE` | Default sync mode | `default` | `all`, `source`, `quick` |
| `SYNC_EXCLUDE` | Rsync exclude patterns | (none) | `"*.log *.tmp build/"` |

### WSL Settings

| Option | Description | Default | Example |
|--------|-------------|---------|---------|
| `FORCE_WSL` | Force WSL mode | (auto-detected) | `true` |
| `WINDOWS_SSH_PATH` | Windows SSH executable | (auto-detected) | `/mnt/c/Windows/System32/OpenSSH/ssh.exe` |

---

## Advanced Usage

### Multiple Workspace Setups

If you work on different projects or branches:

```bash
# Create separate configs
cp config.env config.env.production
cp config.env config.env.development

# Switch between them
ln -sf config.env.production config.env  # Use production config
ln -sf config.env.development config.env # Use development config
```

### Team Configuration Management

For team environments, you can version control a template:

```bash
# .gitignore
config.env           # Don't commit actual config

# Commit template instead
git add config.env.team-template
```

Team members copy the template:
```bash
cp config.env.team-template config.env
# Edit config.env with personal settings
```

### Environment-Specific Overrides

Override config for a single command:

```bash
# Use different IP for this run only
RPI_IP=192.168.1.100 ./sync.sh

# Use different sysroot
RPI_SYSROOT=/custom/sysroot ./build.sh rpi
```

### Profile per Branch Strategy

Useful for multi-vehicle testing:

```bash
# config.env
MAIN_IP=192.168.137.10    # Production vehicle
MAIN_USER=ubuntu

DEV_IP=192.168.137.20     # Development test bench
DEV_USER=ubuntu

TEST_IP=192.168.137.30    # Integration test vehicle
TEST_USER=ubuntu

ALL_PROFILES="main,dev,test"
```

Then in your workflow:
```bash
# Deploy stable code to production
git checkout main
./sync.sh --profile main

# Deploy experimental code to dev
git checkout feature-new-sensor
./sync.sh --profile dev

# Run integration tests
./sync.sh --profile test --build
```

---

## Troubleshooting

### Configuration Not Loading

**Symptom:** Settings from `config.env` are not being used

**Solutions:**
1. Check file location: Must be in workspace root (same directory as `build.sh`)
2. Check file permissions: `chmod 644 config.env`
3. Check syntax: No spaces around `=`, use quotes for values with spaces
4. Verify it's being sourced: Add `echo "Config loaded"` to top of `config.env`

### Profile Not Found

**Symptom:** `Error: Profile 'rpi1' not found`

**Solutions:**
1. Check profile is defined in `config.env`:
   ```bash
   grep RPI1_IP config.env
   ```
2. Check profile is listed in `ALL_PROFILES`:
   ```bash
   grep ALL_PROFILES config.env
   ```
3. View all profiles:
   ```bash
   ./scripts/config_manager.sh --show
   ```

### WSL Sysroot Path Issues

**Symptom:** Cross-compilation fails with "sysroot not found"

**Solutions:**
1. WSL uses different path than native Ubuntu:
   - WSL: `~/rpi-sysroot`
   - Ubuntu: `/media/rpi-sysroot`

2. Set correct path in `config.env`:
   ```bash
   # For WSL
   RPI_SYSROOT=~/rpi-sysroot

   # For Native Ubuntu
   RPI_SYSROOT=/media/rpi-sysroot
   ```

3. Auto-detection: The config manager detects WSL and suggests the correct path

### SSH Key Not Working

**Symptom:** SSH connection fails when using custom key

**Solutions:**
1. Check key path is correct:
   ```bash
   ls -l ~/.ssh/id_rsa
   ```
2. Check key permissions:
   ```bash
   chmod 600 ~/.ssh/id_rsa
   ```
3. Test SSH manually:
   ```bash
   ssh -i ~/.ssh/id_rsa ubuntu@192.168.137.253
   ```
4. Add key to ssh-agent:
   ```bash
   eval $(ssh-agent)
   ssh-add ~/.ssh/id_rsa
   ```

### Config Conflicts

**Symptom:** Unexpected behavior due to conflicting configs

**Solutions:**
1. Check for old config: `~/.pragati_sync.conf` (legacy)
2. Check environment variables:
   ```bash
   env | grep RPI_
   ```
3. Use command-line override to test:
   ```bash
   RPI_IP=192.168.137.253 ./sync.sh --dry-run
   ```
4. Reset to clean state:
   ```bash
   ./scripts/config_manager.sh --reset
   ```

### Multi-Profile Deployment Failures

**Symptom:** Some profiles work, others fail

**Solutions:**
1. Check individual profile settings:
   ```bash
   ./scripts/config_manager.sh --show
   ```
2. Test profiles individually:
   ```bash
   ./sync.sh --profile rpi1 --dry-run
   ./sync.sh --profile rpi2 --dry-run
   ```
3. Check network connectivity for each:
   ```bash
   ping 192.168.137.253  # rpi1
   ping 192.168.137.254  # rpi2
   ```

---

## Best Practices

### 1. Version Control Strategy

**Do commit:**
- `config.env.example` (template for team)
- `config.env.team-template` (team defaults)

**Don't commit:**
- `config.env` (personal settings)
- SSH keys

**Setup `.gitignore`:**
```gitignore
# Personal configuration
config.env

# SSH keys
*.pem
*.key
id_rsa*

# Backups
*.backup
```

### 2. Profile Naming Conventions

Use descriptive, consistent names:

```bash
# Good: Describes purpose/location
VEHICLE1_IP=...      # Physical vehicle #1
TESTBENCH_IP=...     # Lab test bench
PRODUCTION_IP=...    # Production deployment

# Avoid: Generic names
RPI_IP=...           # Which one?
TEST_IP=...          # Test what?
```

### 3. Documentation

Document your profiles in comments:

```bash
# Profile: vehicle1 (Cotton picker #1)
# Location: Field A, GPS: 12.345, 67.890
# Hardware: RPi4 8GB + Camera Module v3
# Last updated: 2024-02-04
VEHICLE1_IP=192.168.137.10
VEHICLE1_USER=ubuntu
```

### 4. Security

```bash
# Use SSH keys, not passwords
RPI_SSH_KEY=~/.ssh/id_rsa_pragati

# Restrict key permissions
chmod 600 ~/.ssh/id_rsa_pragati

# Use different keys per profile for critical systems
PRODUCTION_SSH_KEY=~/.ssh/id_rsa_production
DEV_SSH_KEY=~/.ssh/id_rsa_dev
```

### 5. Testing

Always test configuration changes:

```bash
# Dry run first
./sync.sh --dry-run

# Test SSH separately
./scripts/config_manager.sh --add-profile test_new
ssh ubuntu@192.168.137.253  # Manual test

# Then deploy
./sync.sh --profile test_new
```

---

## Examples

### Example 1: Single RPi Development

```bash
# config.env
RPI_IP=192.168.137.253
RPI_USER=ubuntu
RPI_SYSROOT=/media/rpi-sysroot
```

Usage:
```bash
./build.sh rpi -p motor_control_ros2
./sync.sh --build
```

### Example 2: Multiple Development Boards

```bash
# config.env
# Default: Main test board
RPI_IP=192.168.137.10
RPI_USER=ubuntu
RPI_SYSROOT=/media/rpi-sysroot

# Profile: rpi2 (Backup board)
RPI2_IP=192.168.137.11
RPI2_USER=ubuntu

# Profile: bench (Test bench)
BENCH_IP=192.168.1.100
BENCH_USER=pi
BENCH_TARGET_DIR=~/ros2_ws

ALL_PROFILES="rpi2,bench"
```

Usage:
```bash
# Deploy to default (rpi1)
./sync.sh

# Deploy to backup board
./sync.sh --profile rpi2

# Deploy to all
./sync.sh --all-profiles
```

### Example 3: Production Fleet

```bash
# config.env
# Fleet of cotton pickers
VEHICLE1_IP=192.168.137.10
VEHICLE1_USER=ubuntu

VEHICLE2_IP=192.168.137.11
VEHICLE2_USER=ubuntu

VEHICLE3_IP=192.168.137.12
VEHICLE3_USER=ubuntu

VEHICLE4_IP=192.168.137.13
VEHICLE4_USER=ubuntu

ALL_PROFILES="vehicle1,vehicle2,vehicle3,vehicle4"

# Production sysroot
RPI_SYSROOT=/media/rpi-sysroot-stable
```

Usage:
```bash
# Build once
./build.sh rpi

# Deploy to all vehicles
./sync.sh --all-profiles --deploy-cross

# Or deploy individually
./sync.sh --profile vehicle1 --deploy-cross
```

### Example 4: WSL Development

```bash
# config.env (WSL-specific paths)
RPI_IP=192.168.137.253
RPI_USER=ubuntu
RPI_SYSROOT=~/rpi-sysroot  # WSL path
```

The system auto-detects WSL and uses Windows SSH for hotspot connectivity.

---

## Migration Guide

### From Legacy Config (`~/.pragati_sync.conf`)

The new system is backward compatible, but migration is recommended:

**Old format:**
```bash
# ~/.pragati_sync.conf
RPI_IP=192.168.137.253
RPI_USER=ubuntu
ARM1_IP=192.168.137.253
ARM1_USER=ubuntu
ALL_ARMS="arm1"
```

**New format:**
```bash
# config.env (workspace root)
RPI_IP=192.168.137.253
RPI_USER=ubuntu

# Profiles replace ARM targets
RPI1_IP=192.168.137.253
RPI1_USER=ubuntu

ALL_PROFILES="rpi1"
```

**Migration steps:**
1. Run config manager: `./scripts/config_manager.sh`
2. Set up your default target (uses old config as defaults)
3. Re-create profiles if needed
4. Backup old config: `mv ~/.pragati_sync.conf ~/.pragati_sync.conf.old`

---

## Reference

### Quick Command Reference

```bash
# Configuration management
./scripts/config_manager.sh              # Interactive setup
./scripts/config_manager.sh --show       # Show current config
./scripts/config_manager.sh --add-profile <name>
./scripts/config_manager.sh --reset

# Building with profiles
./build.sh rpi                           # Use default config
./build.sh rpi --profile rpi1            # Use profile
./build.sh rpi -p motor_control_ros2     # Build specific package

# Syncing with profiles
./sync.sh                                # Default profile
./sync.sh --profile rpi1                 # Specific profile
./sync.sh --all-profiles                 # All profiles
./sync.sh --dry-run                      # Preview

# Provisioning & verification
./sync.sh --provision                    # Apply OS fixes + enable services
./sync.sh --all-profiles --provision     # Provision all RPis
./sync.sh --provision --role vehicle     # Override role detection
./sync.sh --verify                       # Check status (runs by default)
./sync.sh --no-verify                    # Skip post-sync verification

# Override config
RPI_IP=192.168.1.100 ./sync.sh          # One-time override
```

### Configuration Hierarchy

```
Command-line args          (Highest priority)
    ↓
Environment variables
    ↓
Profile settings (e.g., RPI1_IP)
    ↓
Default settings (e.g., RPI_IP)
    ↓
config.env file
    ↓
~/.pragati_sync.conf       (Legacy, backward compat)
    ↓
Built-in defaults          (Lowest priority)
```

---

## See Also

- [Cross-Compilation Guide](CROSS_COMPILATION_GUIDE.md) - Setup cross-compilation environment
- [Cross-Compile Setup for WSL](CROSS_COMPILE_SETUP_WSL.md) - WSL-specific workflow
- [Compatibility Validation](COMPATIBILITY_VALIDATION.md) - Platform compatibility matrix
- Main README - General project information
