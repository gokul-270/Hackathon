# Ubuntu Development Setup Guide

## Quick Start

```bash
# 1. Clone repository
git clone <repo-url> ~/pragati_ros2
cd ~/pragati_ros2

# 2. Run setup (takes ~2 hours)
./setup_ubuntu_dev.sh

# 3. Test build
source /opt/ros/jazzy/setup.bash
source install/setup.bash
./build.sh pkg yanthra_move

# 4. Cross-compile for RPi
./build.sh rpi

# 5. Deploy to RPi
./sync.sh --deploy-cross
```

## Prerequisites

- **OS:** Ubuntu 24.04 LTS (Noble Numbat)
- **System:** Native Ubuntu, WSL2, or Raspberry Pi 5
- **Disk Space:** ~10GB for ROS2 + dependencies
- **Network:** Internet connection for package downloads

## WSL2 Users

If using WSL2, you need mirrored networking to reach RPi on hotspot:

1. Create `C:\Users\<Username>\.wslconfig`:
   ```ini
   [wsl2]
   networkingMode=mirrored
   dnsTunneling=true
   localhostForwarding=true
   firewall=true
   ```

2. Restart WSL: `wsl --shutdown` (from PowerShell)

3. See [WSL_NETWORKING_SETUP.md](WSL_NETWORKING_SETUP.md) for details

## Installation Steps

### 1. System Preparation
```bash
./setup_ubuntu_dev.sh --dry-run  # Preview what will be done
./setup_ubuntu_dev.sh            # Execute (takes ~2 hours)
```

The setup script installs:
- ROS2 Jazzy Jalisco
- Build tools (colcon, cmake, gcc)
- Cross-compiler (ARM64) for dev machines
- Vision libraries (OpenCV, v4l-utils)
- Python dependencies from requirements.txt

### 2. Skip ROS2 (if already installed)
```bash
./setup_ubuntu_dev.sh --skip-ros2
```

### 3. Verify Installation
```bash
# Check ROS2
ros2 --version

# Check cross-compiler (dev machines only)
aarch64-linux-gnu-gcc --version

# Check Python packages
source venv/bin/activate
python3 -c "import depthai; print(depthai.__version__)"
```

## Building the Workspace

### Native Build (for testing on x86)
```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

### Cross-Compile for RPi
```bash
./build.sh rpi
# Output: install_rpi/ directory with ARM binaries
```

## Deploying to RPi

### Setup SSH Access
```bash
# From Windows (if RPi on hotspot):
ssh-keygen -t ed25519
type %USERPROFILE%\.ssh\id_ed25519.pub | ssh ubuntu@192.168.137.238 "cat >> ~/.ssh/authorized_keys"

# From WSL/Linux:
ssh-copy-id ubuntu@192.168.137.238
```

### Deploy
```bash
./sync.sh --ip 192.168.137.238 --deploy-cross
```

## Version Management

### Capture RPi Configuration
```bash
./scripts/rpi_config_snapshot.sh rpi
# Output: log/rpi_snapshot_YYYYMMDD_HHMMSS.txt
```

### Validate Python Dependencies
```bash
# Check syntax
./scripts/validate_python_deps.sh

# Compare with RPi
./scripts/validate_requirements_vs_rpi.sh log/rpi_snapshot_*.txt
```

### Check RPi Status
```bash
./scripts/rpi_status.sh rpi
```

## Common Issues

### Cannot Reach RPi from WSL
- Ensure mirrored networking is enabled (see WSL section above)
- Verify RPi is on hotspot: `ping 192.168.137.238` from Windows
- Use wrapper: `source scripts/rpi-wsl-bridge.sh && create_rpi_ssh_wrappers`

### ROS2 Build Fails
- Source ROS2: `source /opt/ros/jazzy/setup.bash`
- Install missing deps: `rosdep install --from-paths src --ignore-src -r -y`
- Check Python venv: `source venv/bin/activate`

### Cross-Compile Fails
- Verify cross-compiler: `aarch64-linux-gnu-gcc --version`
- Check toolchain file exists: `toolchain_aarch64.cmake`
- Ensure ROS2 sourced first

## Directory Structure

```
pragati_ros2/
├── src/                    # ROS2 packages
├── install/                # Native x86 build output
├── install_rpi/            # Cross-compiled ARM build output
├── venv/                   # Python virtual environment
├── log/                    # RPi snapshots, logs
├── scripts/
│   ├── setup/
│   │   ├── common.sh       # Shared functions
│   │   └── modules/        # Setup modules 00-07
│   ├── validate_*.sh       # Validation scripts
│   ├── rpi_*.sh            # RPi management tools
│   └── rpi-wsl-bridge.sh   # WSL network bridge
├── docs/                   # Documentation
├── requirements.txt        # Python dependencies (single source of truth)
├── setup_ubuntu_dev.sh     # Main setup script
├── build.sh                # Build wrapper
└── sync.sh                 # Deploy to RPi
```

## Next Steps

1. Test multi-position J4 scanning (commit e3a7916)
2. Run field trial preparation
3. Optimize Python dependencies (remove unused packages)
4. Document hardware setup procedures

## Support

- Report issues in project GitHub
- Check `docs/` for additional guides
- Review `.opencode/plans/` for planning documents
