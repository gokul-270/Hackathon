#!/usr/bin/env python3
"""
Headless ArUco Marker Detector for OAK-D Camera
Ported from ROS1 OakDTools/aruco_detect.py for ROS2

Detects ArUco markers using OAK-D stereo camera and outputs 3D corner coordinates.
Designed to run as a standalone executable called by yanthra_move.

Exit codes:
  0 - Success (marker detected and centroid.txt written)
  2 - Timeout or no marker detected
  3 - Camera/initialization error
"""

import sys
import os
import argparse
import time
import math

import cv2
import depthai as dai
import numpy as np
from cv2 import aruco

def log_device_temperature(device, tag=""):
    try:
        chip_temp = device.getChipTemperature()

        print(
            f"\033[1m🌡️ OAK-D Temperature | "
            #f"{tag}OAK-D Temperature | "
            #f"CSS: {chip_temp.css:.1f}°C, "
            #f"MSS: {chip_temp.mss:.1f}°C, "
            #f"UPA: {chip_temp.upa:.1f}°C | "
            f"AVG: {chip_temp.average:.1f}°C\033[0m"
        )

    except Exception as e:
        print(f"[TEMP ERROR] {e}", file=sys.stderr)


class HostSpatialsCalc:
    """Calculate 3D spatial coordinates from depth map using pinhole camera model.
    
    Converts 2D pixel coordinates + depth → 3D coordinates (X, Y, Z in mm).
    Uses mono camera FOV and depth averaging for robust measurements.
    """
    def __init__(self, device):
        calibData = device.readCalibration()
        # Use RGB camera FOV for stereo depth calculations (align to RGB)
        self.monoHFOV = np.deg2rad(calibData.getFov(dai.CameraBoardSocket.RGB))
        # Depth thresholds and ROI settings
        self.DELTA = 5
        self.THRESH_LOW = 200  # 20cm minimum
        self.THRESH_HIGH = 30000  # 30m maximum
    
    def setLowerThreshold(self, threshold_low):
        self.THRESH_LOW = threshold_low
    
    def setUpperThreshold(self, threshold_high):
        self.THRESH_HIGH = threshold_high
    
    def setDeltaRoi(self, delta):
        self.DELTA = delta
    
    def _check_input(self, roi, frame):
        """Convert point to ROI if needed, ensure ROI is within frame bounds."""
        if len(roi) == 4:
            return roi
        if len(roi) != 2:
            raise ValueError("You have to pass either ROI (4 values) or point (2 values)!")
        
        # Limit the point so ROI won't be outside the frame
        self.DELTA = 5  # Take 10x10 depth pixels around point for depth averaging
        x = min(max(roi[0], self.DELTA), frame.shape[1] - self.DELTA)
        y = min(max(roi[1], self.DELTA), frame.shape[0] - self.DELTA)
        return (x - self.DELTA, y - self.DELTA, x + self.DELTA, y + self.DELTA)
    
    def _calc_angle(self, frame, offset, axis='x'):
        if axis=="x":
            """Calculate angle from camera center using pinhole camera model."""
            return math.atan(math.tan(self.monoHFOV / 2.0) * offset / (frame.shape[1] / 2.0))
        else:
            vfov=2*math.atan(math.tan(self.monoHFOV / 2.0) * (frame.shape[0] / frame.shape[1]))
            return math.atan(math.tan(vfov / 2.0) * offset / (frame.shape[0] / 2.0))
    
    def calc_spatials(self, depthFrame, roi, averaging_method=np.mean):
        """Calculate 3D spatial coordinates from 2D point/ROI in depth frame.
        
        Args:
            depthFrame: Depth map (numpy array)
            roi: Either (x, y) point or (xmin, ymin, xmax, ymax) ROI
            averaging_method: Function to average depth values (default: np.mean)
        
        Returns:
            tuple: (spatials dict, centroid dict)
                spatials: {'x': mm, 'y': mm, 'z': mm} in RUF camera frame
                centroid: {'x': pixel, 'y': pixel} ROI center
        """
        roi = self._check_input(roi, depthFrame)
        xmin, ymin, xmax, ymax = roi
        
        # Calculate the average depth in the ROI
        depthROI = depthFrame[ymin:ymax, xmin:xmax]
        inRange = (self.THRESH_LOW <= depthROI) & (depthROI <= self.THRESH_HIGH)
        
        averageDepth = averaging_method(depthROI[inRange])
        
        # Get centroid of the ROI
        centroid = {
            'x': int((xmax + xmin) / 2),
            'y': int((ymax + ymin) / 2)
        }
        
        # Calculate position relative to image center
        midW = int(depthFrame.shape[1] / 2)
        midH = int(depthFrame.shape[0] / 2)
        bb_x_pos = centroid['x'] - midW
        bb_y_pos = centroid['y'] - midH
        
        # Calculate angles and 3D coordinates
        angle_x = self._calc_angle(depthFrame, bb_x_pos, axis='x')
        angle_y = self._calc_angle(depthFrame, bb_y_pos, axis='y')
        
        spatials = {
            'z': averageDepth,
            'x': averageDepth * math.tan(angle_x),
            'y': -averageDepth * math.tan(angle_y)
        }
        return spatials, centroid


def create_oakd_pipeline():
    """Create DepthAI pipeline for stereo depth + mono right camera.
    
    Configuration matches ROS1 (ArucoDetectYanthra.py) for lab-grade accuracy.
    Uses HIGH_ACCURACY preset with extensive post-processing filters.
    Expected detection time: ~5-7s (vs ~3-4s without filters).
    """
    pipeline = dai.Pipeline()
    
    # Define mono cameras for depth
    monoLeft = pipeline.createMonoCamera()
    monoRight = pipeline.createMonoCamera()
    stereo = pipeline.createStereoDepth()
    
    # Define RGB camera
    colorCam = pipeline.createColorCamera()
    colorCam.setBoardSocket(dai.CameraBoardSocket.RGB)
    colorCam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    colorCam.setInterleaved(False)
    colorCam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
    
    xoutDepth = pipeline.createXLinkOut()
    xoutRgb = pipeline.createXLinkOut()
    
    xoutDepth.setStreamName("depth")
    xoutRgb.setStreamName('rgb')
    
    # MonoCamera configuration
    monoLeft.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
    monoLeft.setBoardSocket(dai.CameraBoardSocket.LEFT)
    monoRight.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
    monoRight.setBoardSocket(dai.CameraBoardSocket.RIGHT)
    
    # Link mono cameras to stereo node
    monoLeft.out.link(stereo.left)
    monoRight.out.link(stereo.right)
    stereo.depth.link(xoutDepth.input)

    # Link RGB output
    colorCam.video.link(xoutRgb.input)

    # StereoDepth configuration - HIGH QUALITY settings from ROS1
    stereo.setOutputDepth(True)
    stereo.setOutputRectified(True)
    stereo.initialConfig.setConfidenceThreshold(255)
    stereo.setLeftRightCheck(True)
    stereo.setSubpixel(True)
    stereo.setExtendedDisparity(False)
    stereo.initialConfig.setMedianFilter(dai.MedianFilter.KERNEL_7x7)
    stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)

    # Align depth to RGB camera
    stereo.setDepthAlign(dai.CameraBoardSocket.RGB)

    config = stereo.initialConfig.get()
    config.postProcessing.speckleFilter.enable = True
    config.postProcessing.speckleFilter.speckleRange = 50
    config.postProcessing.temporalFilter.enable = True
    config.postProcessing.temporalFilter.persistencyMode = dai.StereoDepthConfig.PostProcessing.TemporalFilter.PersistencyMode.VALID_2_IN_LAST_4
    config.postProcessing.spatialFilter.enable = True
    config.postProcessing.spatialFilter.holeFillingRadius = 2
    config.postProcessing.spatialFilter.numIterations = 5
    config.postProcessing.decimationFilter.decimationFactor = 1
    stereo.initialConfig.set(config)

    return pipeline


def detect_aruco_marker(args):
    """
    Main detection loop - runs until marker detected or timeout.
    
    Returns:
        tuple: (success: bool, corner_spatials: list of 4 dicts or None, debug_frame: np.array or None)
    """
    # Select ArUco dictionary
    aruco_dict_map = {
        '4X4_50': aruco.DICT_4X4_50,
        '4X4_100': aruco.DICT_4X4_100,
        '4X4_250': aruco.DICT_4X4_250,
        '5X5_50': aruco.DICT_5X5_50,
        '5X5_100': aruco.DICT_5X5_100,
        '5X5_250': aruco.DICT_5X5_250,
        '6X6_50': aruco.DICT_6X6_50,
        '6X6_100': aruco.DICT_6X6_100,
        '6X6_250': aruco.DICT_6X6_250,
        '7X7_50': aruco.DICT_7X7_50,
        '7X7_100': aruco.DICT_7X7_100,
        '7X7_250': aruco.DICT_7X7_250,
    }
    
    if args.dict not in aruco_dict_map:
        print(f"ERROR: Unknown ArUco dictionary '{args.dict}'", file=sys.stderr)
        print(f"Available: {', '.join(aruco_dict_map.keys())}", file=sys.stderr)
        return False, None, None
    
    try:
        aruco_dict = aruco.Dictionary_get(aruco_dict_map[args.dict])
        parameters = aruco.DetectorParameters_create()
    except AttributeError:
        # OpenCV 4.7+ uses different API
        aruco_dict = aruco.getPredefinedDictionary(aruco_dict_map[args.dict])
        parameters = aruco.DetectorParameters()
    
    # Initialize OAK-D device and pipeline
    try:
        pipeline = create_oakd_pipeline()
        device = dai.Device(pipeline)
        device.startPipeline()
        
        if not args.quiet:
            print(f"OAK-D device initialized successfully")
            log_device_temperature(device, tag="[INIT] ")
        
    except Exception as e:
        print(f"ERROR: Failed to initialize OAK-D camera: {e}", file=sys.stderr)
        return False, None, None
    
    # Get output queues
    depthQueue = device.getOutputQueue(name="depth", maxSize=4, blocking=False)
    qRgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
    
    # Initialize spatial calculator
    hostSpatials = HostSpatialsCalc(device)
    delta = 2
    hostSpatials.setDeltaRoi(delta)
    
    start_time = time.time()
    target_marker_id = args.id
    
    if not args.quiet:
        print(f"Searching for ArUco marker ID {target_marker_id} (timeout: {args.timeout}s)...")
    
    # Detection loop
    while True:
        # Check timeout
        elapsed = time.time() - start_time
        if elapsed > args.timeout:
            print(f"ERROR: Timeout after {args.timeout}s - no marker detected", file=sys.stderr)
            return False, None, None
        
        # Get frames
        inDepth = depthQueue.get()
        if inDepth is None:
            continue
        depthFrame = inDepth.getFrame()
        inRgb = qRgb.tryGet()
        if inRgb is None:
            continue
        frameRgb = inRgb.getCvFrame()
        
        # Save input frame for debugging (first frame only)
        if args.debug_images and elapsed < 0.5:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            input_img_path = os.path.join(args.debug_dir, f"aruco_input_{timestamp}.jpg")
            try:
                cv2.imwrite(input_img_path, frameRgb)
                if not args.quiet:
                    print(f"✓ Saved input camera frame to: {input_img_path}")
            except Exception as e:
                print(f"WARNING: Failed to save input image: {e}", file=sys.stderr)
        
        # Detect markers
        try:
            corners, ids, rejectedImgPoints = aruco.detectMarkers(
                frameRgb, aruco_dict, parameters=parameters
            )
        except:
            # Handle both old and new OpenCV API
            detector = aruco.ArucoDetector(aruco_dict, parameters)
            corners, ids, rejectedImgPoints = detector.detectMarkers(frameRgb)
        
        if ids is not None and len(corners) > 0:
            ids = ids.flatten()
            
            # Search for target marker ID
            for idx, (markerCorner, markerID) in enumerate(zip(corners, ids)):
                if markerID != target_marker_id:
                    continue
                
                # Found target marker! Extract corners
                corners_2d = markerCorner.reshape((4, 2))
                (topLeft, topRight, bottomRight, bottomLeft) = corners_2d
                
                # Convert to integers
                topLeft = (int(topLeft[0]), int(topLeft[1]))
                topRight = (int(topRight[0]), int(topRight[1]))
                bottomRight = (int(bottomRight[0]), int(bottomRight[1]))
                bottomLeft = (int(bottomLeft[0]), int(bottomLeft[1]))
                
                # Calculate 3D spatial coordinates for each corner
                try:
                    top_left_spatial, _ = hostSpatials.calc_spatials(depthFrame, topLeft)
                    top_right_spatial, _ = hostSpatials.calc_spatials(depthFrame, topRight)
                    bottom_right_spatial, _ = hostSpatials.calc_spatials(depthFrame, bottomRight)
                    bottom_left_spatial, _ = hostSpatials.calc_spatials(depthFrame, bottomLeft)
                except Exception as e:
                    print(f"WARNING: Spatial calculation failed: {e}", file=sys.stderr)
                    continue
                
                # Validate all corners have valid depth
                corner_spatials = [
                    top_left_spatial,
                    top_right_spatial,
                    bottom_right_spatial,
                    bottom_left_spatial
                ]
                
                all_valid = True
                for spatial in corner_spatials:
                    if math.isnan(spatial['x']) or math.isnan(spatial['y']) or math.isnan(spatial['z']):
                        all_valid = False
                        break
                
                if not all_valid:
                    if not args.quiet:
                        print("WARNING: Marker detected but depth invalid, retrying...")
                    continue
                
                # Success! Prepare debug image if requested
                debug_frame = None
                if args.debug_images:
                    debug_frame = frameRgb.copy()
                    # Convert grayscale to BGR for colored annotations
                    if len(debug_frame.shape) == 2:
                        debug_frame = cv2.cvtColor(debug_frame, cv2.COLOR_GRAY2BGR)
                    
                    # Draw marker boundary in bright cyan
                    cv2.polylines(debug_frame, [corners_2d.astype(int)], True, (255, 255, 0), 3)
                    
                    # Draw and label each corner
                    corner_names = ['TL', 'TR', 'BR', 'BL']
                    corner_points = [topLeft, topRight, bottomRight, bottomLeft]
                    corner_colors = [(255, 0, 255), (0, 255, 255), (255, 128, 0), (128, 0, 255)]  # Magenta, Yellow, Orange, Purple
                    
                    # Text offset positions to avoid overlap (outward from marker)
                    text_offsets = [
                        (-150, -20),  # TL: left and up
                        (15, -20),    # TR: right and up  
                        (15, 25),     # BR: right and down
                        (-150, 25)    # BL: left and down
                    ]
                    
                    for i, (pt, name, spatial, color, offset) in enumerate(zip(corner_points, corner_names, corner_spatials, corner_colors, text_offsets)):
                        # Draw larger filled circle with black border for visibility
                        cv2.circle(debug_frame, pt, 8, (0, 0, 0), -1)  # Black border
                        cv2.circle(debug_frame, pt, 6, color, -1)  # Colored center
                        
                        # Draw line from corner to text
                        x_m, y_m, z_m = spatial['x']/1000, spatial['y']/1000, spatial['z']/1000
                        text = f"{name}: ({x_m:.3f},{y_m:.3f},{z_m:.3f})"
                        
                        # Calculate text position with offset
                        text_x = pt[0] + offset[0]
                        text_y = pt[1] + offset[1]
                        
                        # Draw connecting line from corner to text
                        cv2.line(debug_frame, pt, (text_x, text_y), color, 1)
                        
                        # Calculate text size for background rectangle
                        (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                        
                        # Draw black background rectangle with padding
                        cv2.rectangle(debug_frame, 
                                     (text_x - 3, text_y - text_height - 3),
                                     (text_x + text_width + 3, text_y + baseline + 3),
                                     (0, 0, 0), -1)
                        
                        # Draw text in bright color
                        cv2.putText(debug_frame, text, (text_x, text_y), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
                    
                    # Calculate marker center and distance
                    center_x = (topLeft[0] + topRight[0] + bottomRight[0] + bottomLeft[0]) / 4
                    center_y = (topLeft[1] + topRight[1] + bottomRight[1] + bottomLeft[1]) / 4
                    center_pt = (int(center_x), int(center_y))
                    
                    # Calculate average Z distance (distance from camera)
                    avg_z = (corner_spatials[0]['z'] + corner_spatials[1]['z'] + 
                            corner_spatials[2]['z'] + corner_spatials[3]['z']) / 4.0
                    distance_m = avg_z / 1000.0  # Convert mm to meters
                    
                    # Calculate marker size (diagonal distance between opposite corners)
                    diagonal1 = math.sqrt((corner_spatials[0]['x'] - corner_spatials[2]['x'])**2 + 
                                         (corner_spatials[0]['y'] - corner_spatials[2]['y'])**2 + 
                                         (corner_spatials[0]['z'] - corner_spatials[2]['z'])**2) / 1000.0
                    diagonal2 = math.sqrt((corner_spatials[1]['x'] - corner_spatials[3]['x'])**2 + 
                                         (corner_spatials[1]['y'] - corner_spatials[3]['y'])**2 + 
                                         (corner_spatials[1]['z'] - corner_spatials[3]['z'])**2) / 1000.0
                    marker_size = (diagonal1 + diagonal2) / 2.0
                    
                    # Calculate edge distances between adjacent corners
                    edge_distances = []
                    edge_pairs = [(0, 1), (1, 2), (2, 3), (3, 0)]  # TL-TR, TR-BR, BR-BL, BL-TL
                    edge_names = ['Top', 'Right', 'Bottom', 'Left']
                    
                    for i, (idx1, idx2) in enumerate(edge_pairs):
                        dx = corner_spatials[idx1]['x'] - corner_spatials[idx2]['x']
                        dy = corner_spatials[idx1]['y'] - corner_spatials[idx2]['y']
                        dz = corner_spatials[idx1]['z'] - corner_spatials[idx2]['z']
                        dist = math.sqrt(dx*dx + dy*dy + dz*dz) / 1000.0  # Convert to meters
                        edge_distances.append(dist)
                        
                        # Draw distance label on each edge
                        pt1 = corner_points[idx1]
                        pt2 = corner_points[idx2]
                        mid_x = int((pt1[0] + pt2[0]) / 2)
                        mid_y = int((pt1[1] + pt2[1]) / 2)
                        
                        # Offset text position based on edge
                        if i == 0:  # Top edge
                            text_pos = (mid_x - 30, mid_y - 15)
                        elif i == 1:  # Right edge
                            text_pos = (mid_x + 10, mid_y)
                        elif i == 2:  # Bottom edge
                            text_pos = (mid_x - 30, mid_y + 20)
                        else:  # Left edge
                            text_pos = (mid_x - 60, mid_y)
                        
                        dist_text = f"{dist*1000:.1f}mm"
                        (tw, th), _ = cv2.getTextSize(dist_text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                        
                        # Black background
                        cv2.rectangle(debug_frame, 
                                     (text_pos[0] - 2, text_pos[1] - th - 2),
                                     (text_pos[0] + tw + 2, text_pos[1] + 2),
                                     (0, 0, 0), -1)
                        # White text for edge distances
                        cv2.putText(debug_frame, dist_text, text_pos,
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                    
                    # Draw center point
                    cv2.circle(debug_frame, center_pt, 6, (0, 255, 0), -1)  # Green center
                    cv2.circle(debug_frame, center_pt, 8, (0, 0, 0), 2)  # Black outline
                    
                    # Draw diagonal distances
                    diag_text1 = f"D1:{diagonal1*1000:.1f}mm"
                    diag_text2 = f"D2:{diagonal2*1000:.1f}mm"
                    
                    # Position diagonal text near center but offset
                    (tw1, th1), _ = cv2.getTextSize(diag_text1, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                    (tw2, th2), _ = cv2.getTextSize(diag_text2, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                    
                    # Diagonal 1 (TL to BR) - position below center
                    diag1_pos = (center_pt[0] - tw1//2, center_pt[1] + 15)
                    cv2.rectangle(debug_frame, 
                                 (diag1_pos[0] - 2, diag1_pos[1] - th1 - 2),
                                 (diag1_pos[0] + tw1 + 2, diag1_pos[1] + 2),
                                 (0, 0, 0), -1)
                    cv2.putText(debug_frame, diag_text1, diag1_pos,
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
                    
                    # Diagonal 2 (TR to BL) - position above center
                    diag2_pos = (center_pt[0] - tw2//2, center_pt[1] - 8)
                    cv2.rectangle(debug_frame, 
                                 (diag2_pos[0] - 2, diag2_pos[1] - th2 - 2),
                                 (diag2_pos[0] + tw2 + 2, diag2_pos[1] + 2),
                                 (0, 0, 0), -1)
                    cv2.putText(debug_frame, diag_text2, diag2_pos,
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
                    
                    # Add marker ID, distance, and edge measurements info with black background
                    info_texts = [
                        (f"ArUco ID: {target_marker_id}", 20),
                        (f"Dict: {args.dict}", 45),
                        (f"Distance: {distance_m:.3f}m", 70),
                        (f"Edges: T:{edge_distances[0]*1000:.1f} R:{edge_distances[1]*1000:.1f} B:{edge_distances[2]*1000:.1f} L:{edge_distances[3]*1000:.1f}mm", 95),
                        (f"Diagonals: D1:{diagonal1*1000:.1f} D2:{diagonal2*1000:.1f}mm", 120)
                    ]
                    
                    for text, y_pos in info_texts:
                        (text_width, text_height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                        # Black background
                        cv2.rectangle(debug_frame, (5, y_pos - text_height - 5), 
                                     (15 + text_width, y_pos + baseline), (0, 0, 0), -1)
                        # Cyan text
                        cv2.putText(debug_frame, text, (10, y_pos),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                
                if not args.quiet:
                    print(f"✓ ArUco marker ID {target_marker_id} detected with valid depth")
                
                return True, corner_spatials, debug_frame
    
    # Should not reach here due to timeout check
    return False, None, None


def write_centroid_file(corner_spatials, output_path, compat_mode=False):
    """
    Write corner coordinates to centroid.txt.
    
    Args:
        corner_spatials: List of 4 dicts with 'x', 'y', 'z' keys (in mm, RUF format)
        output_path: Primary output file path
        compat_mode: If True, also write to /home/ubuntu/.ros/centroid.txt
    """
    # DepthAI outputs spatial coordinates in RUF (Right-Up-Forward) format:
    #   spatial['x']: +Right / -Left
    #   spatial['y']: +Up / -Down
    #   spatial['z']: +Forward / -Backward (distance from camera)
    # 
    # We need to convert to FLU (Forward-Left-Up) for the arm/ROS:
    #   X_flu = Z_ruf  (Forward comes from camera depth)
    #   Y_flu = -X_ruf (Left is negative of camera right)
    #   Z_flu = Y_ruf  (Up matches camera up)
    # 
    # Convert from millimeters to meters during the transformation:
    lines = []
    for i, spatial in enumerate(corner_spatials):
        # RUF to FLU transformation (used for output file)
        x_flu = spatial['z'] / 1000.0   # Forward (from RUF Z) -> FLU X
        y_flu = -spatial['x'] / 1000.0  # Left (from -RUF X) -> FLU Y
        z_flu = spatial['y'] / 1000.0   # Up (from RUF Y) -> FLU Z
        
        # Also compute RDF (Right-Down-Forward) for debugging/comparison:
        # This is the standard REP-103 optical frame format.
        # RDF conversion from RUF: X_rdf = X_ruf, Y_rdf = -Y_ruf, Z_rdf = Z_ruf
        #x_rdf = spatial['x'] / 1000.0   # Right (same as RUF X)
        #y_rdf = -spatial['y'] / 1000.0  # Down (negative of RUF Y)
        #z_rdf = spatial['z'] / 1000.0   # Forward (same as RUF Z)
        
        lines.append(f"{x_flu} {y_flu} {z_flu}\n")
    
    # Write to primary output
    try:
        with open(output_path, 'w') as f:
            f.writelines(lines)
        print(f"✓ Wrote coordinates to: {output_path}")
        
        # Debug log: print the contents being written
        print("\n=== Centroid.txt Debug Output (FLU coordinates) ===")
        corner_names = ['Top-Left', 'Top-Right', 'Bottom-Right', 'Bottom-Left']
        for i, (spatial, corner_name) in enumerate(zip(corner_spatials, corner_names)):
            x_flu = spatial['z'] / 1000.0
            y_flu = -spatial['x'] / 1000.0
            z_flu = spatial['y'] / 1000.0
            print(f"{corner_name:12s}: FLU({x_flu:7.4f}, {y_flu:7.4f}, {z_flu:7.4f}) m")
            print(f"             RUF({spatial['x']/1000.0:7.4f}, {spatial['y']/1000.0:7.4f}, {spatial['z']/1000.0:7.4f}) m")
        print("===================================================\n")
        
    except Exception as e:
        print(f"ERROR: Failed to write {output_path}: {e}", file=sys.stderr)
        return False
    
    # Compatibility mode: also write to legacy path
    if compat_mode:
        legacy_path = "/home/ubuntu/.ros/centroid.txt"
        try:
            os.makedirs(os.path.dirname(legacy_path), exist_ok=True)
            with open(legacy_path, 'w') as f:
                f.writelines(lines)
            print(f"✓ Also wrote to legacy path: {legacy_path}")
        except Exception as e:
            print(f"WARNING: Failed to write legacy path {legacy_path}: {e}", file=sys.stderr)
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Detect ArUco marker using OAK-D camera and output 3D corner coordinates'
    )
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
                       help='Save annotated debug images (input and output)')
    parser.add_argument('--debug-dir', type=str, default=None,
                       help='Directory for debug images (default: PRAGATI_OUTPUT_DIR/pattern_finder)')
    
    args = parser.parse_args()
    
    # Check for environment variable override
    if 'ARUCO_FINDER_OUTPUT' in os.environ:
        args.output = os.environ['ARUCO_FINDER_OUTPUT']
        if not args.quiet:
            print(f"Using output path from ARUCO_FINDER_OUTPUT: {args.output}")
    
    # Check compatibility mode
    compat_mode = os.environ.get('ARUCO_FINDER_COMPAT_PATHS', '0') == '1'
    
    # Create debug directory if needed
    if args.debug_images:
        # Use PRAGATI_OUTPUT_DIR if available, otherwise current directory
        if args.debug_dir is None:
            base_dir = os.environ.get('PRAGATI_OUTPUT_DIR', './outputs/')
            args.debug_dir = os.path.join(base_dir, 'pattern_finder')
        
        os.makedirs(args.debug_dir, exist_ok=True)
        if not args.quiet:
            print(f"Debug images will be saved to: {args.debug_dir}")
    
    # Run detection
    try:
        success, corner_spatials, debug_frame = detect_aruco_marker(args)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"ERROR: Unexpected error during detection: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(3)
    
    if not success:
        sys.exit(2)  # Timeout/no detection
    
    # Write output file
    if not write_centroid_file(corner_spatials, args.output, compat_mode):
        sys.exit(3)  # Write error
    
    # Save debug images if requested
    if args.debug_images and debug_frame is not None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_img_path = os.path.join(args.debug_dir, f"aruco_detected_{timestamp}.jpg")
        try:
            cv2.imwrite(output_img_path, debug_frame)
            if not args.quiet:
                print(f"✓ Saved annotated image to: {output_img_path}")
        except Exception as e:
            print(f"WARNING: Failed to save debug image: {e}", file=sys.stderr)
    
    if not args.quiet:
        print("✓ ArUco detection completed successfully")
    
    sys.exit(0)


if __name__ == '__main__':
    main()
