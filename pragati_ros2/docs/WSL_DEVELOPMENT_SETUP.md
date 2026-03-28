# WSL Development Environment Setup

> **Purpose:** Complete setup guide for Pragati ROS2 development in WSL Ubuntu - identical to VM setup
> **Last Updated:** 2026-02-03
> **Tested On:** WSL2 Ubuntu 24.04
> **Note:** This setup provides the SAME development environment as the VM, including cross-compilation

---

## 🎯 Quick Setup (TL;DR)

```bash
# 1. Clone repository
git clone https://zentron-labs.git.beanstalkapp.com/cotton-picker.git pragati_ros2
cd pragati_ros2
git checkout pragati_ros2

# 2. Install all dependencies (ROS2, build tools, cross-compilation toolchain)
sudo apt update && sudo apt upgrade -y

# Install ROS2 Jazzy + all dependencies (automated)
# See detailed steps below or run setup_raspberry_pi.sh for reference

# 3. Install cross-compilation toolchain (for RPi builds)
sudo apt install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu

# 4. Create Python virtual environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Build workspace (same as VM)
source /opt/ros/jazzy/setup.bash
./build.sh --fast

# 6. For cross-compilation to RPi
./build.sh rpi
```

---

## 📋 Detailed Setup Steps

### 1. Prerequisites

**WSL2 Requirements:**
- Windows 11 or Windows 10 (version 2004+)
- WSL2 enabled
- Ubuntu 24.04 LTS installed

```powershell
# Check WSL version (in PowerShell)
wsl --list --verbose
# Should show VERSION 2
```

**System Requirements:**
- RAM: 16 GB recommended (8 GB minimum)
- Disk: 40 GB free space
- CPU: Multi-core recommended (compilation is parallel)

---

### 2. Install ROS2 Jazzy

**Option A: Automated Install (Recommended)**

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install ROS2 Jazzy
sudo apt install software-properties-common -y
sudo add-apt-repository universe
sudo apt update
sudo apt install curl -y

# Add ROS2 repository
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# Install ROS2 Jazzy Desktop
sudo apt update
sudo apt install ros-jazzy-desktop -y

# Install development tools
sudo apt install python3-colcon-common-extensions python3-rosdep -y

# Initialize rosdep
sudo rosdep init
rosdep update
```

**Option B: Manual Install**
Follow official guide: https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html

---

### 3. Install Build Dependencies

**Complete dependency installation (identical to VM):**

```bash
# Core development tools
sudo apt install -y \
    build-essential \
    cmake \
    git \
    python3-pip \
    python3-venv \
    ccache \
    ninja-build \
    wget \
    curl

# ROS2 build tools
sudo apt install -y \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-vcstool

# Cross-compilation toolchain for Raspberry Pi
sudo apt install -y \
    gcc-aarch64-linux-gnu \
    g++-aarch64-linux-gnu \
    binutils-aarch64-linux-gnu

# Hardware libraries (for local testing/development)
sudo apt install -y \
    libopencv-dev \
    python3-opencv \
    can-utils \
    libsocketcan-dev

# Python development tools
sudo apt install -y \
    python3-dev \
    python3-pytest \
    python3-pytest-cov

# Optional but recommended
sudo apt install -y \
    rsync \
    htop \
    tree \
    silversearcher-ag

# VS Code (if not already installed on Windows)
# Install from Windows: https://code.visualstudio.com/download
# Install WSL extension in VS Code
```

**Verify cross-compiler installation:**
```bash
aarch64-linux-gnu-gcc --version
# Should show: aarch64-linux-gnu-gcc (Ubuntu ...) ...
```

---

### 4. Clone and Setup Workspace

```bash
# Clone repository
cd ~/
git clone https://zentron-labs.git.beanstalkapp.com/cotton-picker.git pragati_ros2
cd pragati_ros2
git checkout pragati_ros2

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt  # or config/pyproject.toml if exists

# Install ROS2 package dependencies
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -r -y
```

---

### 5. Configure Build Environment

**Set up ccache (speeds up recompilation):**

```bash
# Configure ccache
ccache --max-size=5G
ccache --set-config=compression=true

# Verify
ccache --show-stats
```

**Add to ~/.bashrc:**

```bash
# Add these lines to ~/.bashrc for automatic setup
echo "# ROS2 Jazzy" >> ~/.bashrc
echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
echo "" >> ~/.bashrc
echo "# Pragati workspace (run after navigating to workspace)" >> ~/.bashrc
echo "# source ~/pragati_ros2/install/setup.bash" >> ~/.bashrc
echo "" >> ~/.bashrc
echo "# Python venv (optional - uncomment if always using)" >> ~/.bashrc
echo "# source ~/pragati_ros2/venv/bin/activate" >> ~/.bashrc

# Apply changes
source ~/.bashrc
```

---

### 6. Build Workspace

**Standard Development Build (same as VM):**

```bash
cd ~/pragati_ros2
source /opt/ros/jazzy/setup.bash
source venv/bin/activate

# Fast build (incremental - only changed packages)
./build.sh --fast

# Full build (all packages)
./build.sh

# Clean build (from scratch)
./build.sh --clean

# Build specific package
./build.sh -p yanthra_move

# Build with more parallel workers (if you have RAM)
./build.sh --parallel-workers 8
```

**Cross-Compilation for Raspberry Pi:**

```bash
# Build all packages for RPi (aarch64)
./build.sh rpi

# Build specific package for RPi
./build.sh rpi -p vehicle_control

# Clean cross-compile build
./build.sh --clean rpi

# Deploy to RPi after build
rsync -avz --delete install_rpi/ ubuntu@<RPI_IP>:~/pragati_ros2/install/
```

**Build Modes (same as VM):**

```bash
# Standard (default)
./build.sh

# Fast mode (only changed packages)
./build.sh --fast

# Full rebuild (audit all)
./build.sh --full

# Specific subsystems
./build.sh --arm      # Only arm/manipulation packages
./build.sh --vehicle  # Only vehicle packages
```

---

### 7. Verify Installation

```bash
# Source the workspace
source install/setup.bash

# Check ROS2 packages
ros2 pkg list | grep -E "(yanthra|vehicle|cotton|motor|pattern)"

# Expected output:
# cotton_detection_cpp
# motor_control_ros2
# pattern_finder
# robo_description
# vehicle_control
# yanthra_move
```

---

## 🔧 Development Tools Setup

### VS Code + Extensions

**InstDevelopment Workflow

### Daily Development (Same as VM)

```bash
# 1. Navigate to workspace
cd ~/pragati_ros2

# 2. Activate environment
source /opt/ros/jazzy/setup.bash
source venv/bin/activate
source install/setup.bash

# 3. Make changes to code

# 4. Build (fast mode - only changed packages)
./build.sh --fast

# 5. Test locally (simulation/unit tests)
colcon test --packages-select <package_name>
colcon test-result --verbose
```

### Cross-Compilation Workflow

**Build for Raspberry Pi and deploy:**

```bash
# 1. Build for RPi
./build.sh rpi

# 2. Deploy to RPi
./sync.sh <RPI_IP>
# Or manually:
# rsync -avz --delete install_rpi/ ubuntu@<RPI_IP>:~/pragati_ros2/install/

# 3. SSH to RPi and test
ssh ubuntu@<RPI_IP>
cd ~/pragati_ros2
source install/setup.bash
ros2 launch <your_launch_file>
```

**For complete cross-compilation setup with sysroot:**
See [docs/CROSS_COMPILATION_GUIDE.md](CROSS_COMPILATION_GUIDE.md)

### Key Documentation

1. **Start Here:** [docs/START_HERE.md](START_HERE.md)
2. **Build System:** [docs/BUILD_SYSTEM.md](BUILD_SYSTEM.md)
3. **Cross-Compilation:** [docs/CROSS_COMPILATION_GUIDE.md](CROSS_COMPILATION_GUIDE.md)
4. **Testing:** [docs/guides/TESTING_AND_OFFLINE_OPERATION.md](guides/TESTING_AND_OFFLINE_OPERATION.md)
5. **RPi Deployment:** [docs/project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md](project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md)
6. **Contributing:** [CONTRIBUTING.md](../CONTRIBUTING.md)

### OpenSpec + GitHub Copilot

When using OpenCode with GitHub Copilot subscription:
- `.agent/`, `.gemini/`, `.opencode/` will auto-generate
- Already gitignored - no manual setup needed
- Provides AI-assisted spec-driven developmentuild.sh --fast

# 5. Test
colcon test --packages-select <package_name>
colcon test-result --verbose
```

### Read Documentation

1. **Start Here:** [docs/START_HERE.md](START_HERE.md)
2. **Build System:** [docs/BUILD_SYSTEM.md](BUILD_SYSTEM.md)
3. **Testing:** [docs/guides/TESTING_AND_OFFLINE_OPERATION.md](guides/TESTING_AND_OFFLINE_OPERATION.md)
4. **Contributing:** [CONTRIBUTING.md](../CONTRIBUTING.md)

### OpenSpec Setup (Optional)

If using spec-driven development:

```bash
# Install openspec (if available)
# It will auto-generate .agent/, .gemini/, .opencode/ configs
# These are gitignored and don't need manual setup
```

---

## 🐛 Troubleshooting

### Build Issues

**Out of memory during compilation:**
```bash
# Reduce parallel workers
./build.sh --parallel-workers 2
```

**ccache not working:**
```bash
# Check ccache status
ccache --show-stats

# Clear ccache if corrupt
ccache --clear
```

### ROS2 Issues

**Package not found:**
```bash
# Re-source workspace
source /opt/ros/jazzy/setup.bash
source install/setup.bash
```

**rosdep errors:**
```bash
# Update rosdep
rosdep update
rosdep install --from-paths src --ignore-src -r -y
```

### Python Issues

**Module not found:**
```bash
### WSL vs VM Equivalence

**WSL2 provides SAME environment as VM:**
- ✅ Full Ubuntu 24.04 environment
- ✅ ROS2 Jazzy with all dependencies
- ✅ Cross-compilation toolchain for RPi
- ✅ Same build scripts and workflow
- ✅ ccache for fast incremental builds
- ✅ All development tools (VS Code, Git, etc.)

**Hardware Access:**
- ❌ WSL cannot directly access GPIO, CAN bus, cameras
- ✅ Develop and build in WSL
- ✅ Cross-compile for RPi in WSL
- ✅ Deploy to RPi for hardware testing
- ✅ Use simulation/unit tests in WSL

**Migration from VM to WSL:**
- Same commands, same scripts, same workflow
- Only difference: hardware testing happens on RPi, not locally
- Cross-compilation setup is identical

### Typical Development Flow

```
┌─────────────────────┐
│   WSL Ubuntu 24.04  │  ← Your development machine
│   - Edit code       │
│   - Build (x86_64)  │
│   - Unit tests      │
│   - Cross-compile   │  → ./build.sh rpi
└──────────┬──────────┘
           │ rsync/sync.sh
           ↓
┌─────────────────────┐
│  Raspberry Pi 4B    │  ← Hardware testing
│  - Deploy binaries  │
│  - Hardware tests   │
│  - Field trials     │
└─────────────────────┘
```

### Hardware Deployment

**For Raspberry Pi setup:**
- [setup_raspberry_pi.sh](../setup_raspberry_pi.sh) - Complete RPi setup from scratch
- [RPI_INSTALLATION_VALIDATION_CHECKLIST.md](project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md) - Validation checklist
- [CROSS_COMPILATION_GUIDE.md](CROSS_COMPILATION_GUIDE.md) - Cross-compilation detailsrial.html
- **Project Documentation:** [docs/INDEX.md](INDEX.md)
- **Deployment to RPi:** [docs/project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md](project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md)

---

## ⚠️ Important Notes

**WSL Limitations:**
- ❌ No direct hardware access (GPIO, CAN bus, cameras)
- ❌ Use simulation mode for development
- ✅ Deploy to Raspberry Pi for hardware testing

**Hardware Testing:**
- Development: WSL (simulation)
- Hardware validation: Raspberry Pi
- Use `setup_raspberry_pi.sh` for RPi deployment

**For hardware deployment, see:**
- [setup_raspberry_pi.sh](../setup_raspberry_pi.sh)
- [RPI_INSTALLATION_VALIDATION_CHECKLIST.md](project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md)
