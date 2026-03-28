# Raspberry Pi Deployment Guide - OAK-D ArUco Detection

## ✅ Compatibility Confirmed

Your Raspberry Pi setup is **fully compatible** with the OAK-D ArUco detection system.

### Current RPi Configuration
- **DepthAI Version**: 2.28.0.0 (installed in `/home/ubuntu/.local/lib/python3.12/site-packages`)
- **ROS2 DepthAI**: C++ version 2.30.0 via `ros-jazzy-depthai`
- **Python Version**: 3.12
- **Status**: ✅ **Ready to use - no changes needed**

## Deployment Steps on RPi

### 1. Transfer Files to RPi

From your development machine, sync the workspace to RPi:

```bash
# On your dev machine
cd /home/uday/Downloads/pragati_ros2
rsync -avz --exclude 'build/' --exclude 'install/' --exclude 'log/' \
  . ubuntu@<RPI_IP>:/home/ubuntu/pragati_ros2/
```

### 2. Run Setup Script on RPi

```bash
# On RPi
cd /home/ubuntu/pragati_ros2
./setup_oakd_aruco.sh
```

**Expected output:**
```
✓ DepthAI already installed (version: 2.28.0.0)
✓ DepthAI version is compatible (>= 2.20.0)
```

The script will:
- ✅ Detect existing DepthAI (skip installation)
- ✅ Verify Python dependencies
- ✅ Build pattern_finder package
- ✅ Create `/usr/local/bin/aruco_finder` symlink

### 3. Test on RPi

```bash
# Connect OAK-D camera to RPi USB 3.0 port (blue)

# Test standalone
mkdir -p /tmp/aruco_test && cd /tmp/aruco_test
/usr/local/bin/aruco_finder --id 23 --timeout 10

# Present ArUco marker ID 23 to camera
# Check output
cat centroid.txt
```

## API Compatibility

Both DepthAI 2.28 (RPi) and 3.1 (dev machine) are compatible:

| API Component | Status |
|---------------|--------|
| `dai.Pipeline` | ✅ Compatible |
| `dai.Device` | ✅ Compatible |
| `dai.CameraBoardSocket` | ✅ Compatible |
| `dai.MonoCameraProperties` | ✅ Compatible |
| Stereo depth pipeline | ✅ Compatible |
| Queue operations | ✅ Compatible |

**No code changes needed between versions 2.28 and 3.1.**

## Performance Notes for RPi

### USB Connection
- **Recommended**: USB 3.0 (blue port) for best performance
- **Works on**: USB 2.0 (will be slower)

### Timeout Settings
On RPi, you may want to increase timeout due to slower processing:

```bash
/usr/local/bin/aruco_finder --id 23 --timeout 15
```

Or set environment variable before running yanthra_move:
```bash
export ARUCO_DETECTION_TIMEOUT=15
```

### Temperature Considerations
- RPi may throttle under heavy load
- Ensure adequate cooling/ventilation
- Consider heatsink + fan for continuous operation

## Integration with yanthra_move

No changes needed! The C++ code in `yanthra_move_aruco_detect.cpp`:
- Calls `/usr/local/bin/aruco_finder` (same path on both systems)
- Reads `centroid.txt` from current directory (same behavior)
- Expects 4 lines of `x y z` coordinates in meters (same format)

## Troubleshooting on RPi

### Issue: "Device not found"
```bash
# Check USB connection
lsusb | grep "03e7"  # Should show Luxonis device

# Check permissions
sudo usermod -aG plugdev $USER
# Log out and back in
```

### Issue: "Timeout" during detection
- Increase timeout: `--timeout 20`
- Check lighting (ArUco markers need good contrast)
- Verify marker is DICT_6X6_250, ID 23
- Try moving marker closer (0.5-1.5m range)

### Issue: "Invalid depth"
- Marker too close (< 0.3m) or too far (> 2.5m)
- Poor lighting or reflective surface
- Camera lenses dirty

### Issue: Python module not found
```bash
# Verify DepthAI is accessible
python3 -c "import depthai; print(depthai.__version__)"

# If not found, reinstall
python3 -m pip install --user --break-system-packages depthai
```

## Performance Expectations

| Metric | RPi 4/5 | Desktop |
|--------|---------|---------|
| Detection time | 1-3s | 0.5-1s |
| Frame rate | 15-30 FPS | 30+ FPS |
| Depth accuracy | ±10-20mm | ±10mm |

## Maintenance

### Update DepthAI (if needed)
```bash
python3 -m pip install --upgrade --break-system-packages depthai
```

### Rebuild after code changes
```bash
cd /home/ubuntu/pragati_ros2
colcon build --packages-select pattern_finder
source install/setup.bash
```

### Check logs
```bash
# yanthra_move logs
ros2 run yanthra_move yanthra_move_aruco_detect 2>&1 | tee aruco_debug.log

# Standalone test with verbose output
/usr/local/bin/aruco_finder --id 23 --timeout 10 2>&1 | tee aruco_test.log
```

## Summary

✅ **Your RPi is ready to use with OAK-D ArUco detection**
- DepthAI 2.28 is fully compatible
- No code changes required
- Setup script handles everything automatically
- Performance will be slightly slower than desktop but fully functional

Just run `./setup_oakd_aruco.sh` on the RPi and you're done!
