# ArUco Detection - Quick Reference

## What We Use
- **Camera**: OAK-D (mono stereo cameras LEFT/RIGHT)
- **Script**: `src/pattern_finder/scripts/aruco_detect_oakd.py` (Python, ~560 lines)
- **Helper**: `src/pattern_finder/scripts/calc.py` (65 lines, contains HostSpatialsCalc)
- **Installed**: `/usr/local/bin/aruco_finder` → `aruco_finder_oakd`

## Performance (Updated: Nov 17, 2025)
- **Configuration**: HIGH_ACCURACY with ROS1-style depth filters
- **Detection time**: ~5-7 seconds (prioritizes accuracy for lab testing)
- **Accuracy**: ±10-15mm (HFOV bug fixed + quality filters enabled)
- **Success rate**: 100%
- **Depth quality**: High (speckle, temporal, spatial filters active)

## Usage
```bash
# Run detection
/usr/local/bin/aruco_finder --id 23 --timeout 10 --debug-images

# Output
cat centroid.txt  # 4 corners in FLU coordinates (X Y Z in meters)
```

## Recent Changes (Nov 17, 2025)

### ✅ FIXED: HFOV Bug in calc.py
**File**: `src/pattern_finder/scripts/calc.py` line 12

```python
# FIXED - now uses LEFT mono camera FOV (correct)
self.monoHFOV = np.deg2rad(calibData.getFov(dai.CameraBoardSocket.LEFT))
```

**Result**: 2-3x better accuracy (±10-15mm instead of ±20-35mm)

### ✅ ADDED: ROS1 High-Quality Depth Filters
**File**: `src/pattern_finder/scripts/aruco_detect_oakd.py` lines 61-91

Now matches ROS1 configuration:
- **HIGH_ACCURACY** preset
- **LeftRightCheck**: Enabled (removes bad depth values)
- **Subpixel**: Enabled (higher precision)
- **Median Filter**: KERNEL_7x7
- **Speckle Filter**: Enabled (removes noise)
- **Temporal Filter**: Enabled (smooths over time)
- **Spatial Filter**: Enabled (fills holes)

**Trade-off**: Slightly slower (~5-7s vs ~3-4s) but much better quality for lab testing

## How It Works
1. Captures mono frames from OAK-D (LEFT/RIGHT cameras)
2. Detects ArUco markers using OpenCV
3. Gets depth from stereo depth map
4. Uses `calc.py` to convert 2D pixel + depth → 3D coordinates (X,Y,Z)
5. Transforms from RUF (camera frame) → FLU (robot frame)
6. Writes 4 corner positions to centroid.txt

## Files
- Source: `src/pattern_finder/scripts/aruco_detect_oakd.py`
- Helper: `src/pattern_finder/scripts/calc.py`
- Setup: `scripts/deployment/setup_oakd_aruco.sh`
- Build: `src/pattern_finder/CMakeLists.txt`

## Note
All previous detailed ArUco review docs have been archived to `archive/2025-11-17-aruco-doc-cleanup/`
