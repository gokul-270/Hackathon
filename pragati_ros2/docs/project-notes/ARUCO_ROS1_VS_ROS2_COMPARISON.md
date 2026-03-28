# ArUco Detection: Complete ROS1 vs ROS2 Comparison

**Date**: November 17, 2025  
**Purpose**: Comprehensive side-by-side comparison of all differences

---

## File Summary

| Aspect | ROS1 | ROS2 |
|--------|------|------|
| **File** | `ArucoDetectYanthra.py` | `aruco_detect_oakd.py` |
| **Lines** | 181 | 530 |
| **Complexity** | Simple, monolithic | Structured, modular |

---

## 1. Camera Setup & Pipeline

### ROS1 (Lines 22-45)
```python
# Uses RGB + Mono stereo
pipeline = dai.Pipeline()
monoLeft = pipeline.createMonoCamera()
monoRight = pipeline.createMonoCamera()
colorCam = pipeline.createColorCamera()        # ← RGB camera
stereo = pipeline.createStereoDepth()
stereo.setDepthAlign(dai.CameraBoardSocket.RGB)  # ← Aligns to RGB

xoutDepth = pipeline.createXLinkOut()
xoutColor = pipeline.createXLinkOut()           # ← Color output

# RGB Camera config
colorCam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
colorCam.setBoardSocket(dai.CameraBoardSocket.RGB)
colorCam.setInterleaved(False)
colorCam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
colorCam.video.link(xoutColor.input)

# Mono Camera config
monoLeft.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
monoLeft.setBoardSocket(dai.CameraBoardSocket.LEFT)
monoRight.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
monoRight.setBoardSocket(dai.CameraBoardSocket.RIGHT)
```

**Analysis**:
- ✅ Uses RGB camera for marker detection (better for visualization)
- ✅ Depth aligned to RGB frame
- ❌ More complex (3 cameras)
- ❌ Higher bandwidth usage
- ❌ RGB camera not needed for ArUco (mono sufficient)

### ROS2 (Lines 34-67)
```python
# Mono stereo only
pipeline = dai.Pipeline()
monoLeft = pipeline.createMonoCamera()
monoRight = pipeline.createMonoCamera()
stereo = pipeline.createStereoDepth()

xoutDepth = pipeline.createXLinkOut()
xoutRight = pipeline.createXLinkOut()           # ← Only right mono

xoutDepth.setStreamName("depth")
xoutRight.setStreamName('right')

# Mono Camera config only
monoLeft.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
monoLeft.setBoardSocket(dai.CameraBoardSocket.LEFT)
monoRight.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
monoRight.setBoardSocket(dai.CameraBoardSocket.RIGHT)
monoRight.out.link(xoutRight.input)
```

**Analysis**:
- ✅ Simpler (2 cameras only)
- ✅ Lower bandwidth
- ✅ Faster frame acquisition
- ✅ Mono cameras sufficient for ArUco detection
- ❌ Grayscale only (but acceptable)

---

## 2. Stereo Depth Configuration

### ROS1 (Lines 47-65) - **AGGRESSIVE QUALITY**
```python
# StereoDepth with ALL quality features
stereo.initialConfig.setConfidenceThreshold(255)
stereo.setLeftRightCheck(True)              # ✅ Enabled (+20-30ms/frame)
stereo.setSubpixel(True)                    # ✅ Enabled (more precise)
stereo.setExtendedDisparity(False)
stereo.initialConfig.setMedianFilter(dai.MedianFilter.KERNEL_7x7)  # ✅ 7x7 kernel
stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_ACCURACY)

# EXTENSIVE post-processing filters
config = stereo.initialConfig.get()
config.postProcessing.speckleFilter.enable = True
config.postProcessing.speckleFilter.speckleRange = 50
config.postProcessing.temporalFilter.enable = True
config.postProcessing.temporalFilter.persistencyMode = VALID_2_IN_LAST_4
config.postProcessing.spatialFilter.enable = True
config.postProcessing.spatialFilter.holeFillingRadius = 2
config.postProcessing.spatialFilter.numIterations = 5
config.postProcessing.decimationFilter.decimationFactor = 1
stereo.initialConfig.set(config)

# USB 2.0 forced
device = dai.Device(pipeline, usb2Mode=True)
```

**Impact**:
- ✅ Very clean depth maps
- ✅ Removes noise, speckles, holes
- ✅ Temporal smoothing across frames
- ❌ **SLOW** - filters add 50-100ms+ per frame
- ❌ USB 2.0 limits bandwidth

### ROS2 (Lines 56-67) - **MINIMAL FAST**
```python
# StereoDepth with NO frills
stereo.setOutputDepth(True)
stereo.setOutputRectified(False)
stereo.setConfidenceThreshold(255)
stereo.setLeftRightCheck(False)             # ❌ Disabled (faster)
stereo.setSubpixel(False)                   # ❌ Disabled (faster)

# NO median filter
# NO preset mode
# NO post-processing filters
# NOTHING

monoLeft.out.link(stereo.left)
monoRight.out.link(stereo.right)
stereo.depth.link(xoutDepth.input)

# USB 3.0 auto
device = dai.Device(pipeline)
```

**Impact**:
- ✅ **FAST** - minimal processing
- ✅ USB 3.0 full bandwidth
- ✅ Lower latency
- ❌ Noisier depth maps
- ❌ More depth holes/speckles
- ❌ Less reliable in poor conditions

---

## 3. ArUco Detection Frame Source

### ROS1 (Lines 90-105)
```python
# Uses RGB COLOR frame for detection
inColor = qColor.tryGet()

if inColor is not None:
    frameColor = inColor.getCvFrame()        # ← BGR color image
    
    # Detect markers on COLOR frame
    corners, ids, rejectedImgPoints = aruco.detectMarkers(
        frameColor,                          # ← Color frame
        aruco_dict, 
        parameters=parameters
    )
```

**Analysis**:
- ✅ Color image (better visualization)
- ✅ Saves input/output images in color
- ❌ Requires RGB camera (extra hardware)
- ❌ Slightly slower frame rate

### ROS2 (Lines 148-163)
```python
# Uses MONO grayscale frame for detection
inRight = qRight.tryGet()

if inRight is None:
    continue

frameRight = inRight.getCvFrame()            # ← Grayscale mono image

# Detect markers on MONO frame
try:
    corners, ids, rejectedImgPoints = aruco.detectMarkers(
        frameRight,                          # ← Grayscale frame
        aruco_dict, 
        parameters=parameters
    )
except:
    # Handle new OpenCV API
    detector = aruco.ArucoDetector(aruco_dict, parameters)
    corners, ids, rejectedImgPoints = detector.detectMarkers(frameRight)
```

**Analysis**:
- ✅ Grayscale sufficient for ArUco
- ✅ Simpler hardware setup
- ✅ Faster frame rate
- ✅ Handles both old/new OpenCV APIs
- ❌ Debug images are grayscale (but converts to BGR for annotations)

---

## 4. Marker ID Selection

### ROS1 (Lines 117-119)
```python
# Detects ALL markers, uses FIRST one found
if len(corners) > 0:
    ids = ids.flatten()
    for (markerCorner, markerID) in zip(corners, ids):
        # Processes FIRST marker in list
        # No filtering by ID
```

**Analysis**:
- ❌ No target ID selection
- ❌ Processes first marker found
- ❌ Problem if multiple markers present

### ROS2 (Lines 168-171)
```python
# Searches for SPECIFIC target marker ID
for idx, (markerCorner, markerID) in enumerate(zip(corners, ids)):
    if markerID != target_marker_id:      # ← Filters by ID
        continue
    
    # Only processes target marker
```

**Analysis**:
- ✅ Selects specific marker by ID
- ✅ Configurable via CLI (`--id 23`)
- ✅ Ignores other markers
- ✅ Robust in multi-marker environments

---

## 5. Coordinate System Handling

### ROS1 (Lines 144-157)
```python
# Uses "hack" Y-multiplication factor
y_muliplication_factor = -1  # Hack for Coordinate System Unsync between OAK and Yanthra TODO

# Outputs RUF with Y flipped
ContentTxt += "{0:.3f} ".format(top_left_spatial['x'] / 1000)
ContentTxt += "{0:.3f} ".format(top_left_spatial['y'] * y_muliplication_factor / 1000)  # ← Y flip
ContentTxt += "{0:.3f} ".format(top_left_spatial['z'] / 1000) + "\n"
```

**Analysis**:
- ❌ Called a "hack" in comments
- ❌ No documentation of coordinate frames
- ❌ Unclear what coordinate system output is in
- ❌ Just flips Y without explanation

### ROS2 (Lines 390-432)
```python
# FULLY DOCUMENTED coordinate transformation
# DepthAI outputs spatial coordinates in RUF (Right-Up-Forward) format:
#   spatial['x']: +Right / -Left
#   spatial['y']: +Up / -Down
#   spatial['z']: +Forward / -Backward (distance from camera)
# 
# We need to convert to FLU (Forward-Left-Up) for the arm/ROS:
#   X_flu = Z_ruf  (Forward comes from camera depth)
#   Y_flu = -X_ruf (Left is negative of camera right)
#   Z_flu = Y_ruf  (Up matches camera up)

# RUF to FLU transformation
x_flu = spatial['z'] / 1000.0   # Forward (from RUF Z) -> FLU X
y_flu = -spatial['x'] / 1000.0  # Left (from -RUF X) -> FLU Y
z_flu = spatial['y'] / 1000.0   # Up (from RUF Y) -> FLU Z

# Debug output shows BOTH coordinate systems
print(f"{corner_name:12s}: FLU({x_flu:7.4f}, {y_flu:7.4f}, {z_flu:7.4f}) m")
print(f"             RUF({spatial['x']/1000.0:7.4f}, {spatial['y']/1000.0:7.4f}, {spatial['z']/1000.0:7.4f}) m")
```

**Analysis**:
- ✅ Fully documented transformation
- ✅ Explains both coordinate frames
- ✅ Shows formulas with comments
- ✅ Debug output displays both frames
- ✅ Professional, maintainable

---

## 6. Output Files

### ROS1 (Lines 14-19, 159-174)
```python
# Hardcoded file paths
CentroidFilePath = '/home/ubuntu/.ros/centroid.txt'
CottonDetailsTxtFilePath = "/home/ubuntu/pragati/outputs/cotton_details.txt"
ArucoDetectorInputImage = "/home/ubuntu/pragati/inputs/ArucoInputImage.jpg"
ArucoDetectorOutputImage = "/home/ubuntu/pragati/outputs/ArucoDetectorOutput.jpg"

# Opens files at START (before detection)
centroid_file = open(CentroidFilePath, 'w')
CottonDetailsTxtFile = open(CottonDetailsTxtFilePath, 'w')

# Writes TWO output files
centroid_file.write(ContentTxt)              # 4 corners
CottonDetailsTxtFile.write(CottonDetailsTxt)  # 4 corners with "0 0" prefix

# Writes input/output images
cv2.imwrite(ArucoDetectorInputImage, frameColor)
cv2.imwrite(ArucoDetectorOutputImage, frameColor)

centroid_file.close()
CottonDetailsTxtFile.close()
```

**Analysis**:
- ❌ Hardcoded paths (not portable)
- ❌ Files opened early (waste if detection fails)
- ✅ Writes cotton_details.txt (for compatibility)
- ✅ Saves input + output images
- ❌ Always saves images (no option to disable)

### ROS2 (Lines 381-522)
```python
# Configurable paths via CLI or environment
parser.add_argument('--output', type=str, default='centroid.txt')
parser.add_argument('--debug-images', action='store_true')
parser.add_argument('--debug-dir', type=str, default=None)

# Environment variable override
if 'ARUCO_FINDER_OUTPUT' in os.environ:
    args.output = os.environ['ARUCO_FINDER_OUTPUT']

# Compatibility mode for legacy path
compat_mode = os.environ.get('ARUCO_FINDER_COMPAT_PATHS', '0') == '1'

# Writes ONE primary file + optional legacy
def write_centroid_file(corner_spatials, output_path, compat_mode=False):
    # Write to primary output
    with open(output_path, 'w') as f:
        f.writelines(lines)
    
    # Optional: write to legacy path
    if compat_mode:
        legacy_path = "/home/ubuntu/.ros/centroid.txt"
        with open(legacy_path, 'w') as f:
            f.writelines(lines)

# Debug images ONLY if requested
if args.debug_images and debug_frame is not None:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_img_path = os.path.join(args.debug_dir, f"aruco_detected_{timestamp}.jpg")
    cv2.imwrite(output_img_path, debug_frame)
```

**Analysis**:
- ✅ Fully configurable paths
- ✅ CLI arguments + env variables
- ✅ Optional legacy path support
- ✅ Debug images only when requested
- ✅ Timestamped output files
- ✅ Files opened only after successful detection
- ❌ Doesn't write cotton_details.txt (could add as option)

---

## 7. Error Handling & Exit Codes

### ROS1 (Lines 87-112, 177)
```python
# Simple while True loop
while True:
    print("waiting for 5 seconds before capturing image")
    time.sleep(5)                           # ← 5 second delay!
    
    inDepth = depthQueue.get().getFrame()
    inColor = qColor.tryGet()
    
    if inColor is None:
        print("Error: OAK-D not capturing color frames")
        print("Error: Check Camera")
        continue                            # ← Just continues
    
    # ...
    
    if len(corners) <= 0:
        print("ArucoMarkerDetect: Failed to detect corners")
        print("ArucoDetectYanthra.py: Error Exiting Program")
        continue                            # ← Doesn't actually exit!
    
    # ...
    break                                   # Exits on first success

# No exit code
# No proper error handling
# No timeout
```

**Analysis**:
- ❌ 5 second startup delay (wasteful)
- ❌ Infinite loop (no timeout)
- ❌ No exit codes
- ❌ "Error Exiting" but just continues
- ❌ No NaN validation before writing output

### ROS2 (Lines 70-210, 494-510)
```python
# Proper timeout handling
start_time = time.time()

while True:
    # Check timeout
    elapsed = time.time() - start_time
    if elapsed > args.timeout:
        print(f"ERROR: Timeout after {args.timeout}s - no marker detected", file=sys.stderr)
        return False, None, None

# NaN validation BEFORE accepting
all_valid = True
for spatial in corner_spatials:
    if math.isnan(spatial['x']) or math.isnan(spatial['y']) or math.isnan(spatial['z']):
        all_valid = False
        break

if not all_valid:
    if not args.quiet:
        print("WARNING: Marker detected but depth invalid, retrying...")
    continue                                # ← Actually retries

# Global exception handling
try:
    success, corner_spatials, debug_frame = detect_aruco_marker(args)
except KeyboardInterrupt:
    print("\nInterrupted by user", file=sys.stderr)
    sys.exit(130)                           # ← Proper exit code
except Exception as e:
    print(f"ERROR: Unexpected error during detection: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(3)                             # ← Error exit code

if not success:
    sys.exit(2)                             # ← Timeout exit code

# Exit codes:
#   0 - Success
#   2 - Timeout/no detection
#   3 - Camera/initialization error
#   130 - Keyboard interrupt
```

**Analysis**:
- ✅ Configurable timeout (`--timeout 10`)
- ✅ Proper exit codes (0/2/3/130)
- ✅ NaN validation before output
- ✅ Retry logic for invalid depth
- ✅ Global exception handling
- ✅ Immediate startup (no delay)
- ✅ stderr vs stdout separation

---

## 8. Debug Visualization

### ROS1 (Lines 132-142)
```python
# Simple text annotations
text.rectangle(frameColor, (topLeft[0] - delta, topLeft[1] - delta), ...)
text.putText(frameColor, 
    "X: " + ("{:.3f}".format(top_left_spatial['x'] / 1000) if not math.isnan(...) else "--") + 
    " Y: " + ("{:.3f}".format(top_left_spatial['y'] / 1000) if not math.isnan(...) else "--") + 
    " Z: " + ("{:.3f}".format(top_left_spatial['z'] / 1000) if not math.isnan(...) else "--"), 
    (topLeft[0] - 50, topLeft[1] - 30))

# Repeats for all 4 corners
# Always saves output image
```

**Features**:
- ✅ Shows X/Y/Z per corner
- ✅ NaN handling in display
- ✅ Color image
- ❌ No edge measurements
- ❌ No diagonal measurements
- ❌ No marker info header
- ❌ Text may overlap
- ❌ Always runs (no option to disable)

### ROS2 (Lines 214-370)
```python
# Rich professional annotations (ONLY if --debug-images)
if args.debug_images:
    # Convert to BGR
    if len(debug_frame.shape) == 2:
        debug_frame = cv2.cvtColor(debug_frame, cv2.COLOR_GRAY2BGR)
    
    # Marker boundary (cyan)
    cv2.polylines(debug_frame, [corners_2d.astype(int)], True, (255, 255, 0), 3)
    
    # Colored corner markers
    corner_colors = [(255, 0, 255), (0, 255, 255), (255, 128, 0), (128, 0, 255)]
    for pt, name, spatial, color, offset in zip(...):
        # Filled circle with black border
        cv2.circle(debug_frame, pt, 8, (0, 0, 0), -1)
        cv2.circle(debug_frame, pt, 6, color, -1)
        
        # Connecting line from corner to text
        cv2.line(debug_frame, pt, (text_x, text_y), color, 1)
        
        # Text with black background
        cv2.rectangle(debug_frame, ..., (0, 0, 0), -1)
        cv2.putText(debug_frame, f"{name}: ({x_m:.3f},{y_m:.3f},{z_m:.3f})", ...)
    
    # Edge distance measurements (T/R/B/L)
    for idx1, idx2 in edge_pairs:
        dist = math.sqrt(dx*dx + dy*dy + dz*dz) / 1000.0
        cv2.putText(debug_frame, f"{dist*1000:.1f}mm", ...)
    
    # Diagonal measurements
    cv2.putText(debug_frame, f"D1:{diagonal1*1000:.1f}mm", ...)
    cv2.putText(debug_frame, f"D2:{diagonal2*1000:.1f}mm", ...)
    
    # Info header
    info_texts = [
        f"ArUco ID: {target_marker_id}",
        f"Dict: {args.dict}",
        f"Distance: {distance_m:.3f}m",
        f"Edges: T:{...} R:{...} B:{...} L:{...}mm",
        f"Diagonals: D1:{...} D2:{...}mm"
    ]
    
    # Green center point
    cv2.circle(debug_frame, center_pt, 6, (0, 255, 0), -1)
```

**Features**:
- ✅ Optional (only if `--debug-images`)
- ✅ Corner coordinates with unique colors
- ✅ Edge measurements (4 sides)
- ✅ Diagonal measurements (geometry validation)
- ✅ Marker info header (ID, dict, distance)
- ✅ Center point marker
- ✅ Black backgrounds for readability
- ✅ Smart text positioning (no overlap)
- ✅ Connecting lines from corners to labels
- ✅ Professional layout
- ❌ Grayscale source (but converts to BGR for colors)

---

## 9. CLI Arguments & Configuration

### ROS1
```python
# NO command-line arguments
# Everything hardcoded
# - Marker ID: Always detects ANY marker
# - Dictionary: Always DICT_6X6_250
# - Timeout: Infinite (no timeout)
# - Output path: Hardcoded
# - Debug images: Always saved
```

**Analysis**:
- ❌ Zero configurability
- ❌ Must edit code to change settings
- ❌ Not suitable for different scenarios

### ROS2 (Lines 453-491)
```python
# Full CLI argument support
parser = argparse.ArgumentParser(...)
parser.add_argument('--id', type=int, default=23,
                   help='ArUco marker ID to detect (default: 23)')
parser.add_argument('--dict', type=str, default='6X6_250',
                   help='ArUco dictionary (default: 6X6_250)')
parser.add_argument('--timeout', type=int, default=10,
                   help='Detection timeout in seconds (default: 10)')
parser.add_argument('--output', type=str, default='centroid.txt',
                   help='Output file path (default: centroid.txt)')
parser.add_argument('--quiet', action='store_true',
                   help='Suppress info messages')
parser.add_argument('--debug-images', action='store_true',
                   help='Save annotated debug images')
parser.add_argument('--debug-dir', type=str, default=None,
                   help='Directory for debug images')

# Environment variable support
if 'ARUCO_FINDER_OUTPUT' in os.environ:
    args.output = os.environ['ARUCO_FINDER_OUTPUT']

compat_mode = os.environ.get('ARUCO_FINDER_COMPAT_PATHS', '0') == '1'

base_dir = os.environ.get('PRAGATI_OUTPUT_DIR', './outputs/')

# Usage examples:
# /usr/local/bin/aruco_finder --id 23 --timeout 10 --debug-images
# /usr/local/bin/aruco_finder --id 42 --dict 4X4_100 --output /tmp/marker.txt --quiet
```

**Analysis**:
- ✅ Fully configurable via CLI
- ✅ Environment variable support
- ✅ Help text (`--help`)
- ✅ Sensible defaults
- ✅ Flexible for different use cases

---

## 10. Modularity & Code Structure

### ROS1
```python
# Monolithic script (181 lines)
# - Pipeline setup: inline
# - Detection: inline in while loop
# - Output: inline
# - No functions
# - Global variables
# - Everything in main scope
```

**Analysis**:
- ❌ Hard to test
- ❌ Hard to reuse
- ❌ Hard to maintain
- ✅ Simple to understand (if small)

### ROS2
```python
# Modular structure (530 lines)

def create_oakd_pipeline():
    \"\"\"Create DepthAI pipeline for stereo depth + mono right camera.\"\"\"
    # 34 lines of pipeline setup
    return pipeline

def detect_aruco_marker(args):
    \"\"\"Main detection loop - runs until marker detected or timeout.\"\"\"
    # 308 lines of detection logic
    return success, corner_spatials, debug_frame

def write_centroid_file(corner_spatials, output_path, compat_mode=False):
    \"\"\"Write corner coordinates to centroid.txt.\"\"\"
    # 68 lines of file I/O with documentation
    return True/False

def main():
    \"\"\"Parse arguments and orchestrate detection.\"\"\"
    # 78 lines of argument parsing and coordination
    sys.exit(0/2/3)

if __name__ == '__main__':
    main()
```

**Analysis**:
- ✅ Modular functions
- ✅ Clear separation of concerns
- ✅ Easy to test each function
- ✅ Reusable components
- ✅ Comprehensive docstrings
- ✅ Proper main() entry point
- ❌ More code (but better organized)

---

## Summary Table

| Feature | ROS1 | ROS2 | Winner |
|---------|------|------|--------|
| **Camera Setup** | RGB + Mono stereo | Mono stereo only | ROS2 (simpler) |
| **Depth Filters** | Heavy (7 filters) | None | ROS1 (quality) / ROS2 (speed) |
| **LR Check** | Enabled | Disabled | ROS1 (quality) / ROS2 (speed) |
| **Subpixel** | Enabled | Disabled | ROS1 (precision) / ROS2 (speed) |
| **USB Mode** | USB 2.0 forced | USB 3.0 auto | **ROS2** |
| **Detection Frame** | Color RGB | Grayscale mono | ROS2 (sufficient) |
| **Marker Selection** | First found | Target ID | **ROS2** |
| **Coordinates** | "Hack" Y flip | Documented RUF→FLU | **ROS2** |
| **Output Files** | 2 files, hardcoded | 1 file, configurable | **ROS2** |
| **Exit Codes** | None | 0/2/3/130 | **ROS2** |
| **Timeout** | None (infinite) | Configurable | **ROS2** |
| **Error Handling** | Basic | Comprehensive | **ROS2** |
| **NaN Validation** | Display only | Before output | **ROS2** |
| **Debug Images** | Always on | Optional | **ROS2** |
| **Debug Quality** | Basic X/Y/Z | Rich (edges/diagonals) | **ROS2** |
| **CLI Arguments** | None | 7 arguments | **ROS2** |
| **Env Variables** | None | 3 supported | **ROS2** |
| **Code Structure** | Monolithic | Modular | **ROS2** |
| **Documentation** | Minimal | Extensive | **ROS2** |
| **Lines of Code** | 181 | 530 | ROS1 (simpler) |
| **Startup Delay** | 5 seconds | Immediate | **ROS2** |
| **calc.py HFOV Bug** | ✅ Yes | ✅ Yes | **TIE** (both have it) |

---

## Performance Trade-offs

### ROS1: Quality Over Speed
- **Speed**: ~5-7 seconds (estimated, with all filters)
- **Accuracy**: Moderate (HFOV bug limits it)
- **Depth Quality**: High (clean, filtered)
- **Reliability**: High (temporal/spatial smoothing)
- **Use Case**: When depth quality matters more than speed

### ROS2: Speed Over Quality
- **Speed**: ~3-4 seconds
- **Accuracy**: Moderate (same HFOV bug)
- **Depth Quality**: Lower (noisier, more holes)
- **Reliability**: Good (validates NaN, retries)
- **Use Case**: When speed matters, controlled environment

---

## Recommendation

**For Production (Current ROS2)**:
- ✅ Use as-is for now (fast, works)
- ✅ Fix HFOV bug in calc.py (easy accuracy win)
- 🔶 Consider adding optional `--high-quality` flag that enables ROS1-style filters
  - Default: Fast mode (current)
  - With flag: Quality mode (ROS1 filters)
  - Gives flexibility for different scenarios

**Example**:
```bash
# Fast mode (default)
/usr/local/bin/aruco_finder --id 23

# Quality mode (when needed)
/usr/local/bin/aruco_finder --id 23 --high-quality
```

---

## The One Thing Both Have Wrong

**HFOV Bug in calc.py (line 10)**:
```python
# WRONG (both ROS1 and ROS2)
self.monoHFOV = np.deg2rad(calibData.getFov(dai.CameraBoardSocket.RGB))

# FIX (for both)
self.monoHFOV = np.deg2rad(calibData.getFov(dai.CameraBoardSocket.LEFT))
# Or: dai.CameraBoardSocket.RIGHT (same FOV, stereo pair)
```

This bug affects accuracy in BOTH systems, independent of all other differences.
