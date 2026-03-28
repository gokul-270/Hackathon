#!/usr/bin/env python3
"""
Front Camera Cotton Detection Node for Gazebo Simulation

Processes images from the simulated front camera (OAK-D Lite equivalent) mounted
in front of the front wheel and runs cotton detection. In simulation mode, uses
HSV-based color detection (white cotton bolls on green/brown background). 
Architecturally compatible with the production cotton_detection_ros2 C++ node
so results can be consumed by yanthra_move and other downstream systems.

Detection Pipeline:
  1. Subscribe to /front_camera (sensor_msgs/Image from Gazebo)
  2. Convert to OpenCV BGR image
  3. Run detection (HSV color-based for sim, DepthAI blob for real hardware)
  4. Publish DetectionResult to /cotton_detection/result
  5. Provide /cotton_detection/detect service (same as production node)
  6. Publish annotated debug image to /front_camera/cotton_detection/debug_image

Model: cotton_detection_ros2/models/yolov112.blob (2-class: cotton, not_pickable)
       Used on real hardware via DepthAI. Simulation uses HSV fallback.

Topics:
  Subscribes: /front_camera (sensor_msgs/Image)
  Publishes:  /cotton_detection/result (cotton_detection_ros2/DetectionResult)
              /front_camera/cotton_detection/debug_image (sensor_msgs/CompressedImage)
              /front_camera/cotton_detection/markers (visualization_msgs/MarkerArray) [optional]

Services:
  /cotton_detection/detect (cotton_detection_ros2/CottonDetection)

Author: vehicle_control Package (Pragati Robotics)
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CompressedImage
from geometry_msgs.msg import Point
from std_msgs.msg import Header, String as StringMsg
import numpy as np
import math
import time
import os
from typing import List, Tuple, Optional

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    from cv_bridge import CvBridge
    HAS_CV_BRIDGE = True
except ImportError:
    HAS_CV_BRIDGE = False

# Try to import cotton_detection_ros2 messages
# These are available when cotton_detection_ros2 package is built
try:
    from cotton_detection_ros2.msg import CottonPosition, DetectionResult  # type: ignore[import-not-found]
    from cotton_detection_ros2.srv import CottonDetection  # type: ignore[import-not-found]
    HAS_COTTON_MSGS = True
except ImportError:
    HAS_COTTON_MSGS = False


class CottonDetectionResult:
    """Internal detection result structure (used when custom msgs not available)."""
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.confidence = 0.0
        self.label = 0  # 0=cotton, 1=not_pickable
        self.bbox = (0, 0, 0, 0)  # x, y, w, h in pixels


class FrontCameraCottonDetector(Node):
    """
    Cotton detection node for the front camera in Gazebo simulation.

    Processes front camera images to detect cotton plants/bolls in the simulated
    cotton field. Compatible with the production cotton_detection_ros2 pipeline.
    """

    # Detection modes
    MODE_HSV = 'hsv'                    # HSV color-based (simulation)
    MODE_DEPTHAI = 'depthai_direct'     # DepthAI blob model (real hardware)
    MODE_OPENCV_DNN = 'opencv_dnn'      # OpenCV DNN with ONNX/OpenVINO

    # Class labels (matching yolov112.blob 2-class model)
    CLASS_COTTON = 0
    CLASS_NOT_PICKABLE = 1
    CLASS_NAMES = {0: 'cotton', 1: 'not_pickable'}

    def __init__(self):
        super().__init__('front_camera_cotton_detector')

        # ─── Parameter Declaration ───────────────────────────────
        self._declare_parameters()
        self._load_parameters()

        # ─── State ───────────────────────────────────────────────
        self.bridge = CvBridge() if HAS_CV_BRIDGE else None
        self.latest_image = None
        self.latest_image_stamp = None
        self.detection_count = 0
        self.total_processing_time_ms = 0.0
        self.last_detections: List[CottonDetectionResult] = []

        # ─── Camera Intrinsics (matching URDF: 640x480, hfov=1.274 rad) ──
        self.image_width = 640
        self.image_height = 480
        self.hfov = 1.2740903539558606  # horizontal FOV in radians
        self.fx = self.image_width / (2.0 * math.tan(self.hfov / 2.0))
        self.fy = self.fx  # Square pixels
        self.cx = self.image_width / 2.0
        self.cy = self.image_height / 2.0

        # ─── QoS for sensor data ────────────────────────────────
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # ─── Subscribers ────────────────────────────────────────
        self.image_sub = self.create_subscription(
            Image,
            '/front_camera',
            self._image_callback,
            sensor_qos
        )

        # ─── Publishers ─────────────────────────────────────────
        if HAS_COTTON_MSGS:
            self.detection_pub = self.create_publisher(
                DetectionResult,
                '/cotton_detection/result',
                10
            )
        else:
            self.detection_pub = None
            self.get_logger().warn(
                'cotton_detection_ros2 messages not available. '
                'Detection results will only be logged, not published.')

        self.debug_image_pub = self.create_publisher(
            CompressedImage,
            '/front_camera/cotton_detection/debug_image',
            10
        )

        # JSON result publisher (for web UI backend — no custom msg dependency)
        self.result_json_pub = self.create_publisher(
            StringMsg,
            '/cotton_detection/result_json',
            10
        )

        # ─── Service ────────────────────────────────────────────
        if HAS_COTTON_MSGS:
            self.detection_service = self.create_service(
                CottonDetection,
                '/cotton_detection/detect',
                self._handle_detection_service
            )

        # ─── Detection Timer ────────────────────────────────────
        detection_rate = 1.0 / self.max_fps
        self.detection_timer = self.create_timer(detection_rate, self._detection_loop)

        # ─── Stats Timer ────────────────────────────────────────
        self.stats_timer = self.create_timer(10.0, self._log_stats)

        # ─── Startup Info ───────────────────────────────────────
        self.get_logger().info('=' * 60)
        self.get_logger().info('FRONT CAMERA COTTON DETECTOR')
        self.get_logger().info('=' * 60)
        self.get_logger().info(f'Detection mode: {self.detection_mode}')
        self.get_logger().info(f'Model path: {self.model_path}')
        self.get_logger().info(f'Confidence threshold: {self.confidence_threshold}')
        self.get_logger().info(f'Max FPS: {self.max_fps}')
        self.get_logger().info(f'Camera: {self.image_width}x{self.image_height}, '
                               f'HFOV={math.degrees(self.hfov):.1f}°')
        self.get_logger().info(f'OpenCV available: {HAS_OPENCV}')
        self.get_logger().info(f'CvBridge available: {HAS_CV_BRIDGE}')
        self.get_logger().info(f'Cotton msgs available: {HAS_COTTON_MSGS}')
        self.get_logger().info(f'Subscribing to: /front_camera')
        self.get_logger().info(f'Publishing to: /cotton_detection/result')
        self.get_logger().info('Waiting for camera images...')
        self.get_logger().info('=' * 60)

    # ═════════════════════════════════════════════════════════════
    # PARAMETER MANAGEMENT
    # ═════════════════════════════════════════════════════════════

    def _declare_parameters(self):
        """Declare all ROS2 parameters."""
        # Detection mode
        self.declare_parameter('detection_mode', 'hsv')
        self.declare_parameter('simulation_mode', True)

        # Model configuration (for real hardware / OpenCV DNN mode)
        self.declare_parameter('model_path', '')
        self.declare_parameter('num_classes', 2)
        self.declare_parameter('confidence_threshold', 0.5)
        self.declare_parameter('nms_threshold', 0.45)

        # HSV thresholds for cotton (white) detection in simulation
        # Cotton bolls appear as bright white objects
        self.declare_parameter('hsv_white_lower', [0, 0, 200])
        self.declare_parameter('hsv_white_upper', [180, 50, 255])

        # HSV thresholds for not-pickable (brown/dried) cotton
        self.declare_parameter('hsv_brown_lower', [10, 50, 50])
        self.declare_parameter('hsv_brown_upper', [30, 200, 200])

        # Contour filtering
        self.declare_parameter('min_contour_area', 100.0)
        self.declare_parameter('max_contour_area', 50000.0)
        self.declare_parameter('min_circularity', 0.3)

        # Morphological operations
        self.declare_parameter('morph_kernel_size', 5)
        self.declare_parameter('morph_iterations', 2)

        # Performance
        self.declare_parameter('max_fps', 10.0)
        self.declare_parameter('max_detections', 50)

        # Depth estimation (for simulation without real depth sensor)
        # Uses monocular depth estimation based on object apparent size
        self.declare_parameter('estimated_cotton_diameter_m', 0.05)
        self.declare_parameter('default_depth_m', 2.0)

        # Debug
        self.declare_parameter('enable_debug_image', True)
        self.declare_parameter('enable_verbose_logging', False)

    def _load_parameters(self):
        """Load parameters from ROS2 parameter server."""
        self.detection_mode = self.get_parameter('detection_mode').value
        self.simulation_mode = self.get_parameter('simulation_mode').value
        self.model_path = self.get_parameter('model_path').value
        self.num_classes = self.get_parameter('num_classes').value
        self.confidence_threshold = self.get_parameter('confidence_threshold').value
        self.nms_threshold = self.get_parameter('nms_threshold').value

        self.hsv_white_lower = np.array(
            self.get_parameter('hsv_white_lower').value, dtype=np.uint8)
        self.hsv_white_upper = np.array(
            self.get_parameter('hsv_white_upper').value, dtype=np.uint8)
        self.hsv_brown_lower = np.array(
            self.get_parameter('hsv_brown_lower').value, dtype=np.uint8)
        self.hsv_brown_upper = np.array(
            self.get_parameter('hsv_brown_upper').value, dtype=np.uint8)

        self.min_contour_area = self.get_parameter('min_contour_area').value
        self.max_contour_area = self.get_parameter('max_contour_area').value
        self.min_circularity = self.get_parameter('min_circularity').value

        self.morph_kernel_size = self.get_parameter('morph_kernel_size').value
        self.morph_iterations = self.get_parameter('morph_iterations').value

        self.max_fps = self.get_parameter('max_fps').value
        self.max_detections = self.get_parameter('max_detections').value

        self.estimated_cotton_diameter = self.get_parameter('estimated_cotton_diameter_m').value
        self.default_depth = self.get_parameter('default_depth_m').value

        self.enable_debug_image = self.get_parameter('enable_debug_image').value
        self.enable_verbose_logging = self.get_parameter('enable_verbose_logging').value

    # ═════════════════════════════════════════════════════════════
    # IMAGE CALLBACK
    # ═════════════════════════════════════════════════════════════

    def _image_callback(self, msg: Image):
        """Store latest camera image for processing."""
        if not HAS_OPENCV or not HAS_CV_BRIDGE:
            return

        try:
            # Convert ROS Image to OpenCV BGR
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.latest_image = cv_image
            self.latest_image_stamp = msg.header.stamp

            # Update camera dimensions from actual image
            h, w = cv_image.shape[:2]
            if w != self.image_width or h != self.image_height:
                self.image_width = w
                self.image_height = h
                self.fx = self.image_width / (2.0 * math.tan(self.hfov / 2.0))
                self.fy = self.fx
                self.cx = self.image_width / 2.0
                self.cy = self.image_height / 2.0
                self.get_logger().info(
                    f'Camera resolution updated: {w}x{h}')

        except Exception as e:
            self.get_logger().error(f'Image conversion error: {e}')

    # ═════════════════════════════════════════════════════════════
    # DETECTION LOOP
    # ═════════════════════════════════════════════════════════════

    def _detection_loop(self):
        """Main detection loop (called at max_fps rate)."""
        if self.latest_image is None:
            return

        image = self.latest_image.copy()
        stamp = self.latest_image_stamp

        start_time = time.monotonic()

        # Run detection based on mode
        detections = []
        if self.detection_mode == self.MODE_HSV:
            detections = self._detect_hsv(image)
        elif self.detection_mode == self.MODE_OPENCV_DNN:
            detections = self._detect_opencv_dnn(image)
        else:
            # Default to HSV for simulation
            detections = self._detect_hsv(image)

        elapsed_ms = (time.monotonic() - start_time) * 1000.0
        self.total_processing_time_ms += elapsed_ms
        self.detection_count += 1
        self.last_detections = detections

        # Publish results
        self._publish_detection_result(detections, stamp, elapsed_ms)

        # Publish debug image
        if self.enable_debug_image:
            self._publish_debug_image(image, detections)

        if self.enable_verbose_logging and detections:
            self.get_logger().info(
                f'Detected {len(detections)} cotton bolls in {elapsed_ms:.1f}ms')

    # ═════════════════════════════════════════════════════════════
    # HSV-BASED DETECTION (Simulation Mode)
    # ═════════════════════════════════════════════════════════════

    def _detect_hsv(self, image: np.ndarray) -> List[CottonDetectionResult]:
        """
        Detect cotton bolls using HSV color space analysis.

        In the Gazebo simulation, cotton bolls appear as bright white objects
        against the green plant/brown soil background. This method:
        1. Converts to HSV color space
        2. Applies white threshold for cotton, brown threshold for not-pickable
        3. Morphological cleanup (close gaps, remove noise)
        4. Find contours and filter by area/circularity
        5. Estimate 3D position from 2D centroid + apparent size

        Returns:
            List of CottonDetectionResult objects
        """
        if not HAS_OPENCV:
            return []

        detections = []

        # Convert to HSV
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        # ── Detect cotton (white) ────────────────────────────────
        cotton_mask = cv2.inRange(hsv, self.hsv_white_lower, self.hsv_white_upper)

        # ── Detect not-pickable (brown/dried) ────────────────────
        brown_mask = cv2.inRange(hsv, self.hsv_brown_lower, self.hsv_brown_upper)

        # ── Morphological cleanup ────────────────────────────────
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (self.morph_kernel_size, self.morph_kernel_size)
        )

        cotton_mask = cv2.morphologyEx(
            cotton_mask, cv2.MORPH_CLOSE, kernel,
            iterations=self.morph_iterations)
        cotton_mask = cv2.morphologyEx(
            cotton_mask, cv2.MORPH_OPEN, kernel,
            iterations=1)

        brown_mask = cv2.morphologyEx(
            brown_mask, cv2.MORPH_CLOSE, kernel,
            iterations=self.morph_iterations)

        # ── Process cotton detections ────────────────────────────
        cotton_contours, _ = cv2.findContours(
            cotton_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in cotton_contours:
            result = self._process_contour(
                contour, self.CLASS_COTTON, image.shape)
            if result is not None:
                detections.append(result)

        # ── Process not-pickable detections ──────────────────────
        brown_contours, _ = cv2.findContours(
            brown_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in brown_contours:
            result = self._process_contour(
                contour, self.CLASS_NOT_PICKABLE, image.shape)
            if result is not None:
                detections.append(result)

        # Sort by confidence (descending) and limit
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections[:self.max_detections]

    def _process_contour(
        self, contour, label: int, image_shape: tuple
    ) -> Optional[CottonDetectionResult]:
        """
        Process a single contour into a detection result.

        Filters by area and circularity, estimates 3D position from 2D.
        """
        area = cv2.contourArea(contour)
        if area < self.min_contour_area or area > self.max_contour_area:
            return None

        # Circularity check (cotton bolls are roughly circular)
        perimeter = cv2.arcLength(contour, True)
        if perimeter > 0:
            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity < self.min_circularity:
                return None
        else:
            return None

        # Bounding box
        x, y, w, h = cv2.boundingRect(contour)

        # Centroid
        M = cv2.moments(contour)
        if M['m00'] > 0:
            cx = int(M['m10'] / M['m00'])
            cy = int(M['m01'] / M['m00'])
        else:
            cx = x + w // 2
            cy = y + h // 2

        # Estimate confidence from area and circularity
        # Larger, more circular = higher confidence
        area_factor = min(1.0, area / 5000.0)
        circularity_factor = min(1.0, circularity / 0.8)
        confidence = 0.5 * area_factor + 0.5 * circularity_factor
        confidence = max(self.confidence_threshold, min(1.0, confidence))

        if confidence < self.confidence_threshold:
            return None

        # ── Estimate 3D position (monocular) ─────────────────────
        # Use apparent diameter to estimate depth
        apparent_diameter_px = max(w, h)
        if apparent_diameter_px > 0:
            # depth = (real_diameter * focal_length) / apparent_diameter
            depth_m = (self.estimated_cotton_diameter * self.fx) / apparent_diameter_px
            depth_m = max(0.1, min(10.0, depth_m))
        else:
            depth_m = self.default_depth

        # Project 2D pixel to 3D camera coordinates
        # Using pinhole camera model: X = (u - cx) * Z / fx
        x_3d = (cx - self.cx) * depth_m / self.fx
        y_3d = (cy - self.cy) * depth_m / self.fy
        z_3d = depth_m

        # Build result
        result = CottonDetectionResult()
        result.x = z_3d    # camera Z → world forward (X)
        result.y = -x_3d   # camera X → world left (Y), negated for right-hand
        result.z = -y_3d   # camera Y → world up (Z), negated (camera Y is down)
        result.confidence = confidence
        result.label = label
        result.bbox = (x, y, w, h)

        return result

    # ═════════════════════════════════════════════════════════════
    # OPENCV DNN DETECTION (Optional - for ONNX/OpenVINO models)
    # ═════════════════════════════════════════════════════════════

    def _detect_opencv_dnn(self, image: np.ndarray) -> List[CottonDetectionResult]:
        """
        Detect cotton using OpenCV DNN module with ONNX/OpenVINO model.

        This mode allows running a YOLO model without DepthAI hardware,
        using OpenCV's built-in DNN inference. Requires the model in
        ONNX format (convert from .blob/.xml+.bin using OpenVINO tools).

        Note: The yolov112.blob is Myriad X format. For OpenCV DNN,
        convert to ONNX first using: openvino2onnx or export from
        the original training framework.
        """
        if not HAS_OPENCV or not self.model_path:
            self.get_logger().warn_once(
                'OpenCV DNN mode requires model_path parameter. Falling back to HSV.')
            return self._detect_hsv(image)

        # TODO: Implement OpenCV DNN inference when ONNX model is available
        # For now, fall back to HSV detection
        self.get_logger().warn_once(
            'OpenCV DNN inference not yet implemented. Using HSV fallback.')
        return self._detect_hsv(image)

    # ═════════════════════════════════════════════════════════════
    # PUBLISHING
    # ═════════════════════════════════════════════════════════════

    def _publish_detection_result(
        self,
        detections: List[CottonDetectionResult],
        stamp,
        processing_time_ms: float
    ):
        """Publish detection results in cotton_detection_ros2 format + JSON."""
        # Always publish JSON for web UI (no custom msg dependency)
        import json
        cotton_dets = [d for d in detections if d.label == self.CLASS_COTTON]
        not_pickable_dets = [d for d in detections if d.label == self.CLASS_NOT_PICKABLE]
        json_msg = StringMsg()
        json_msg.data = json.dumps({
            'total_count': len(detections),
            'cotton_count': len(cotton_dets),
            'not_pickable_count': len(not_pickable_dets),
            'detection_successful': len(detections) > 0,
            'processing_time_ms': round(processing_time_ms, 1),
            'positions': [
                {
                    'x': round(d.x, 3), 'y': round(d.y, 3), 'z': round(d.z, 3),
                    'confidence': round(d.confidence, 3),
                    'label': d.label,
                    'label_name': self.CLASS_NAMES.get(d.label, f'cls{d.label}'),
                }
                for d in detections
            ],
        })
        self.result_json_pub.publish(json_msg)

        if not HAS_COTTON_MSGS or self.detection_pub is None:
            return

        msg = DetectionResult()
        msg.header = Header()
        msg.header.stamp = stamp if stamp else self.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_optical_link'

        msg.detection_successful = len(detections) > 0
        msg.total_count = len(detections)
        msg.processing_time_ms = processing_time_ms

        for det in detections:
            pos_msg = CottonPosition()
            pos_msg.position = Point()
            pos_msg.position.x = det.x
            pos_msg.position.y = det.y
            pos_msg.position.z = det.z
            pos_msg.confidence = det.confidence
            pos_msg.detection_id = det.label
            msg.positions.append(pos_msg)

        self.detection_pub.publish(msg)

    def _publish_debug_image(
        self,
        image: np.ndarray,
        detections: List[CottonDetectionResult]
    ):
        """Publish annotated debug image with detection overlays."""
        if not HAS_OPENCV or not HAS_CV_BRIDGE:
            return

        debug_img = image.copy()

        # Draw detections
        for i, det in enumerate(detections):
            x, y, w, h = det.bbox
            color = (0, 255, 0) if det.label == self.CLASS_COTTON else (0, 165, 255)
            label_text = self.CLASS_NAMES.get(det.label, f'cls{det.label}')

            # Bounding box
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), color, 2)

            # Label with confidence
            text = f'{label_text} {det.confidence:.2f}'
            text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
            cv2.rectangle(debug_img, (x, y - text_size[1] - 4),
                         (x + text_size[0], y), color, -1)
            cv2.putText(debug_img, text, (x, y - 2),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # 3D position label
            pos_text = f'({det.x:.2f}, {det.y:.2f}, {det.z:.2f})m'
            cv2.putText(debug_img, pos_text, (x, y + h + 15),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Detection summary overlay
        cotton_count = sum(1 for d in detections if d.label == self.CLASS_COTTON)
        np_count = sum(1 for d in detections if d.label == self.CLASS_NOT_PICKABLE)
        summary = f'Cotton: {cotton_count} | Not-pickable: {np_count} | Mode: {self.detection_mode}'
        cv2.putText(debug_img, summary, (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # Encode as JPEG compressed image
        try:
            _, jpeg_data = cv2.imencode('.jpg', debug_img,
                                        [cv2.IMWRITE_JPEG_QUALITY, 80])
            compressed_msg = CompressedImage()
            compressed_msg.header.stamp = self.get_clock().now().to_msg()
            compressed_msg.header.frame_id = 'camera_optical_link'
            compressed_msg.format = 'jpeg'
            compressed_msg.data = jpeg_data.tobytes()
            self.debug_image_pub.publish(compressed_msg)
        except Exception as e:
            self.get_logger().error(f'Debug image publish error: {e}')

    # ═════════════════════════════════════════════════════════════
    # SERVICE HANDLER
    # ═════════════════════════════════════════════════════════════

    def _handle_detection_service(self, request, response):
        """
        Handle cotton detection service request.
        Compatible with cotton_detection_ros2/srv/CottonDetection.

        Commands:
            0 = Stop detection
            1 = Detect cotton (return positions)
            2 = Calibrate (no-op in simulation)
        """
        command = request.detect_command

        if command == 0:
            # Stop
            response.success = True
            response.message = 'Detection stopped'
            response.data = []
            return response

        elif command == 1:
            # Detect
            if self.latest_image is None:
                response.success = False
                response.message = 'No camera image available'
                response.data = []
                return response

            image = self.latest_image.copy()
            start_time = time.monotonic()

            if self.detection_mode == self.MODE_HSV:
                detections = self._detect_hsv(image)
            elif self.detection_mode == self.MODE_OPENCV_DNN:
                detections = self._detect_opencv_dnn(image)
            else:
                detections = self._detect_hsv(image)

            elapsed_ms = (time.monotonic() - start_time) * 1000.0

            # Encode positions as int32 array (matching production format)
            # Format: [n_detections, x1*1000, y1*1000, z1*1000, x2*1000, ...]
            data = [len(detections)]
            for det in detections:
                if det.label == self.CLASS_COTTON:  # Only return pickable cotton
                    data.extend([
                        int(det.x * 1000),
                        int(det.y * 1000),
                        int(det.z * 1000),
                    ])

            # Update first element with actual cotton-only count
            cotton_count = sum(1 for d in detections if d.label == self.CLASS_COTTON)
            data[0] = cotton_count

            response.success = True
            response.message = (
                f'Detected {cotton_count} cotton bolls '
                f'({len(detections)} total) in {elapsed_ms:.1f}ms')
            response.data = data
            return response

        elif command == 2:
            # Calibrate (no-op in simulation)
            response.success = True
            response.message = 'Calibration not needed in simulation mode'
            response.data = []
            return response

        else:
            response.success = False
            response.message = f'Unknown command: {command}'
            response.data = []
            return response

    # ═════════════════════════════════════════════════════════════
    # STATS LOGGING
    # ═════════════════════════════════════════════════════════════

    def _log_stats(self):
        """Periodically log detection performance stats."""
        if self.detection_count == 0:
            if self.latest_image is None:
                self.get_logger().info(
                    'No camera images received yet. '
                    'Ensure /front_camera topic is publishing.')
            return

        avg_time = self.total_processing_time_ms / self.detection_count
        last_count = len(self.last_detections)
        cotton_count = sum(
            1 for d in self.last_detections if d.label == self.CLASS_COTTON)

        self.get_logger().info(
            f'Detection stats: {self.detection_count} frames processed, '
            f'avg {avg_time:.1f}ms/frame, '
            f'last frame: {cotton_count} cotton / {last_count} total detections')


def main(args=None):
    rclpy.init(args=args)

    if not HAS_OPENCV:
        print('[FATAL] OpenCV (cv2) not available. Install with: pip install opencv-python')
        return

    if not HAS_CV_BRIDGE:
        print('[FATAL] cv_bridge not available. Install ros-${ROS_DISTRO}-cv-bridge')
        return

    node = FrontCameraCottonDetector()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('Shutting down Front Camera Cotton Detector...')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
