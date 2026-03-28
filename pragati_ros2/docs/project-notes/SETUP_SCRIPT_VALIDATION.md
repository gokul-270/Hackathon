# Setup Script Validation Checklist

**Script:** `setup_raspberry_pi.sh`  
**Date:** 2025-11-19  
**Status:** ✅ All items checked and fixed

---

## Items Checked and Fixed

### 1. ✅ pigpio (no installation candidate issue)
**Problem:** On Ubuntu 24.04, `pigpio` may not be available in apt repositories.

**Solution:** Added fallback to build from source
```bash
if sudo apt install -y pigpio python3-pigpio libpigpio-dev 2>/dev/null; then
    # Installed from apt
else
    # Build from source (github.com/joan2937/pigpio)
fi
```

**Lines:** 214-229

---

### 2. ✅ python3-cantools
**Status:** Does NOT exist as an apt package

**Solution:** Installed via pip instead (already correct)
```bash
python3 -m pip install --user cantools
```

**Note:** Added comment explaining this is installed via pip, not apt  
**Lines:** 377-379, 391

---

### 3. ✅ python3-opencv-contrib-python
**Status:** Does NOT exist as an apt package

**Solution:** Correct packages installed:
- **System:** `libopencv-contrib-dev` (C++ headers)
- **Python:** `opencv-contrib-python` via pip

```bash
# System
sudo apt install -y libopencv-contrib-dev

# Python
python3 -m pip install --user opencv-contrib-python
```

**Lines:** 259 (apt), 398 (pip)

---

### 4. ✅ CAN Setup
**Status:** Fully implemented with correct bitrate

**Features:**
- ✅ CAN kernel modules loaded (can, can-raw, can-bcm, mcp251x)
- ✅ Persistent network configuration at `/etc/network/interfaces.d/can0`
- ✅ **Correct bitrate: 500 kbps for MG6010 motors** (NOT 1 Mbps)
- ✅ Modules set to load at boot via `/etc/modules`

```bash
# CAN0 interface configuration for MG6010 motors (500 kbps)
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 500000
    up /sbin/ifconfig can0 up
    down /sbin/ifconfig can0 down
```

**Lines:** 402-431

---

### 5. ✅ rosdep install
**Status:** Fully implemented

**Features:**
- ✅ `rosdep init` (if needed)
- ✅ `rosdep update`
- ✅ `rosdep install --from-paths src --ignore-src -r -y`

**Lines:** 168-172, 491

---

### 6. ✅ sudo apt install -y libpcl-dev
**Status:** Added to OpenCV installation section

```bash
sudo apt install -y \
    libopencv-dev \
    python3-opencv \
    libopencv-contrib-dev \
    libpcl-dev
```

**Lines:** 256-260

---

### 7. ✅ sudo apt install -y libudev-dev
**Status:** Added to hardware dependencies

```bash
sudo apt install -y \
    can-utils \
    i2c-tools \
    python3-smbus \
    python3-serial \
    python3-spidev \
    net-tools \
    build-essential \
    libudev-dev
```

**Lines:** 204-212

---

## Additional Features Added

### 8. ✅ DepthAI Version 2.30.0.0
**Python:**
```bash
python3 -m pip install --user depthai==2.30.0.0 depthai-sdk
```

**C++:**
```bash
git clone --branch v2.30.0 --depth 1 https://github.com/luxonis/depthai-core.git
cmake -S. -Bbuild -D CMAKE_INSTALL_PREFIX=$HOME/.local
cmake --build build --parallel
cmake --install build
```

**Environment variables added to `.bashrc`:**
- `DEPTHAI_INSTALL_DIR=$HOME/.local`
- `CMAKE_PREFIX_PATH=$HOME/.local:$CMAKE_PREFIX_PATH`

**Lines:** 256-293

---

### 9. ✅ GPIO Support Enhanced
**Added:**
- `libgpiod-dev` - Modern GPIO library for RPi 4/5
- `gpiod` - GPIO tools
- `python3-rpi.gpio` - Python GPIO library
- udev rules for GPIO access (`/etc/udev/rules.d/99-gpio.rules`)

**Lines:** 231-245

---

### 10. ✅ Validation Checklist Integration
**Updated next steps to include:**
1. System verification: `scripts/deployment/rpi_verify.sh`
2. CAN testing at correct bitrate (500 kbps)
3. Full validation: `scripts/deployment/validate_rpi_deployment.sh`

**Lines:** 551-565

---

### 11. ✅ Improved Swap Configuration
**Handles both:**
- Raspberry Pi OS (`dphys-swapfile`)
- Ubuntu (manual `/swapfile`)

**Lines:** 433-453

---

## Package Status Summary

| Package | Method | Status | Notes |
|---------|--------|--------|-------|
| **pigpio** | apt or source | ✅ | Fallback to build from source if apt fails |
| **python3-cantools** | N/A | ✅ | Installed via pip as `cantools` |
| **python3-opencv-contrib-python** | N/A | ✅ | Installed via pip as `opencv-contrib-python` |
| **libpcl-dev** | apt | ✅ | Added |
| **libudev-dev** | apt | ✅ | Added |
| **CAN setup** | Script | ✅ | 500 kbps bitrate for MG6010 |
| **rosdep** | Script | ✅ | Fully configured |
| **DepthAI 2.30** | pip + source | ✅ | Both Python and C++ |

---

## Verification Commands

After running the setup script, verify installations:

```bash
# Check pigpio
pigpiod -v

# Check Python packages
python3 -c "import can; print('python-can:', can.__version__)"
python3 -c "import cantools; print('cantools:', cantools.__version__)"
python3 -c "import cv2; print('OpenCV:', cv2.__version__)"
python3 -c "import depthai as dai; print('DepthAI:', dai.__version__)"

# Check system libraries
ldconfig -p | grep pigpio
ldconfig -p | grep pcl
ldconfig -p | grep udev

# Check CAN interface
ip link show can0
cat /etc/network/interfaces.d/can0

# Check environment variables
echo $DEPTHAI_INSTALL_DIR
echo $CMAKE_PREFIX_PATH
```

---

## Known Issues

### Ubuntu 24.04 Package Availability
Some packages may not be available in Ubuntu 24.04 repositories:
- `wiringpi` - May be deprecated, but included for compatibility
- `pigpio` - Falls back to source build if not available

### ROS Jazzy Compatibility
All ROS2 packages are for Jazzy. If using a different ROS2 distribution, update package names:
```bash
ros-jazzy-* → ros-<distro>-*
```

---

## Related Documentation

- **Main script:** `setup_raspberry_pi.sh`
- **Validation checklist:** `RPI_INSTALLATION_VALIDATION_CHECKLIST.md`
- **Deployment guide:** `docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md`
- **Build guide:** `BUILD_GUIDE.md`

---

**Validation completed:** 2025-11-19  
**All items checked:** ✅  
**Ready for deployment:** ✅
