#!/usr/bin/env python3
"""
Still-Capture Thermal Test
==========================
Tests whether using still-capture mode (triggered) reduces thermal load
compared to continuous preview streaming.

This script creates a pipeline that ONLY uses the 'still' output,
meaning frames are only captured when explicitly triggered.

Usage:
    # Run still-capture test (triggered every 5 seconds)
    python3 test_still_capture_thermal.py --mode still --interval 5 --duration 300

    # Run continuous test for comparison
    python3 test_still_capture_thermal.py --mode continuous --duration 300

    # Quick test (2 minutes)
    python3 test_still_capture_thermal.py --mode still --duration 120

Output:
    - Temperature readings every 5 seconds
    - Detection latency per trigger
    - CSV log file for analysis
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import depthai as dai
import numpy as np

# Default blob path (same as production)
DEFAULT_BLOB_PATH = "/home/uday/Downloads/pragati_ros2/data/models/yolov8v2.blob"


def create_still_capture_pipeline(blob_path: str, enable_depth: bool = False):
    """
    Create a pipeline using ONLY still output (no continuous streaming).
    
    This should reduce thermal load when idle since the sensor/ISP
    only processes frames when triggered.
    
    Pipeline: ColorCamera.still (NV12) -> ImageManip (BGR, 416x416) -> YOLO NN
    """
    pipeline = dai.Pipeline()
    
    # Color camera - configured for still capture
    colorCam = pipeline.create(dai.node.ColorCamera)
    colorCam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    colorCam.setInterleaved(False)
    colorCam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
    # Set still size to full resolution, we'll resize in ImageManip
    colorCam.setStillSize(1920, 1080)
    # NOTE: We do NOT set FPS - the camera will only capture on trigger
    
    # XLinkIn for camera control (to send still capture triggers)
    controlIn = pipeline.create(dai.node.XLinkIn)
    controlIn.setStreamName("control")
    controlIn.out.link(colorCam.inputControl)
    
    # ImageManip to convert NV12 still output to BGR and resize to NN input size
    manip = pipeline.create(dai.node.ImageManip)
    manip.initialConfig.setResize(416, 416)
    manip.initialConfig.setFrameType(dai.ImgFrame.Type.BGR888p)  # Planar BGR for NN
    manip.initialConfig.setKeepAspectRatio(False)  # Stretch to exact size
    manip.setMaxOutputFrameSize(416 * 416 * 3)  # BGR = 3 bytes per pixel
    manip.inputImage.setBlocking(False)
    manip.inputImage.setQueueSize(1)
    
    # Link still -> ImageManip
    colorCam.still.link(manip.inputImage)
    
    # Neural network (YOLO)
    nn = pipeline.create(dai.node.YoloDetectionNetwork)
    nn.setBlobPath(blob_path)
    nn.setConfidenceThreshold(0.5)
    nn.setNumClasses(1)  # Cotton only
    nn.setCoordinateSize(4)
    nn.setAnchors([])  # YOLOv8 is anchor-free
    nn.setAnchorMasks({})
    nn.setIouThreshold(0.5)
    nn.input.setBlocking(False)
    nn.input.setQueueSize(1)
    
    # Link ImageManip output to NN (now in correct BGR format)
    manip.out.link(nn.input)
    
    # XLinkOut for detections
    nnOut = pipeline.create(dai.node.XLinkOut)
    nnOut.setStreamName("detections")
    nn.out.link(nnOut.input)
    
    # XLinkOut for processed image (for debugging/verification)
    stillOut = pipeline.create(dai.node.XLinkOut)
    stillOut.setStreamName("still")
    manip.out.link(stillOut.input)
    
    return pipeline


def create_continuous_pipeline(blob_path: str, fps: int = 30, enable_depth: bool = False):
    """
    Create a continuous pipeline (current approach) for comparison.
    """
    pipeline = dai.Pipeline()
    
    # Color camera - continuous streaming
    colorCam = pipeline.create(dai.node.ColorCamera)
    colorCam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    colorCam.setInterleaved(False)
    colorCam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
    colorCam.setPreviewSize(416, 416)  # NN input size
    colorCam.setFps(fps)
    
    # Neural network (YOLO)
    nn = pipeline.create(dai.node.YoloDetectionNetwork)
    nn.setBlobPath(blob_path)
    nn.setConfidenceThreshold(0.5)
    nn.setNumClasses(1)
    nn.setCoordinateSize(4)
    nn.setAnchors([])
    nn.setAnchorMasks({})
    nn.setIouThreshold(0.5)
    nn.input.setBlocking(False)
    nn.input.setQueueSize(1)
    
    # Link preview (continuous) to NN
    colorCam.preview.link(nn.input)
    
    # XLinkOut for detections
    nnOut = pipeline.create(dai.node.XLinkOut)
    nnOut.setStreamName("detections")
    nn.out.link(nnOut.input)
    
    return pipeline


def run_still_capture_test(device, control_queue, detection_queue, still_queue, 
                           interval_sec: float, duration_sec: float, csv_writer,
                           save_images: bool = False):
    """Run still-capture mode test."""
    print(f"\n{'='*60}")
    print("STILL-CAPTURE MODE TEST")
    print(f"Interval: {interval_sec}s, Duration: {duration_sec}s")
    if save_images:
        print("Saving images to /tmp/still_capture_*.jpg")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    trigger_count = 0
    last_seq_num = -1
    
    while (time.time() - start_time) < duration_sec:
        # Get temperature
        try:
            temps = device.getChipTemperature()
            chip_temp = temps.average
        except:
            chip_temp = -1
        
        # Trigger still capture
        trigger_start = time.time()
        ctrl = dai.CameraControl()
        ctrl.setCaptureStill(True)
        control_queue.send(ctrl)
        
        # Wait for detection result
        latency_ms = -1
        num_detections = 0
        frame_seq = -1
        frame_ts = -1
        
        try:
            # Wait up to 2 seconds for result (poll since get(timeout) not supported)
            det_data = None
            deadline = time.time() + 2.0
            while time.time() < deadline:
                det_data = detection_queue.tryGet()
                if det_data is not None:
                    break
                time.sleep(0.01)  # 10ms polling
            
            if det_data is not None:
                latency_ms = (time.time() - trigger_start) * 1000
                num_detections = len(det_data.detections)
                trigger_count += 1
            else:
                print(f"  Warning: No detection received within timeout")
        except Exception as e:
            print(f"  Warning: Detection error: {e}")
        
        # Get the still image to verify freshness (sequence number & timestamp)
        try:
            still_frame = still_queue.tryGet()
            if still_frame is not None:
                frame_seq = still_frame.getSequenceNum()
                frame_ts = still_frame.getTimestamp().total_seconds()
                
                # Check if sequence number increased (proves fresh frame)
                if last_seq_num >= 0 and frame_seq <= last_seq_num:
                    print(f"  ⚠️  WARNING: Frame seq {frame_seq} <= last {last_seq_num} - might be stale!")
                last_seq_num = frame_seq
                
                # Optionally save image
                if save_images:
                    try:
                        import cv2
                        img = still_frame.getCvFrame()
                        filename = f"/tmp/still_capture_{trigger_count:03d}.jpg"
                        cv2.imwrite(filename, img)
                    except Exception as e:
                        print(f"  Warning: Could not save image: {e}")
        except:
            pass
        
        elapsed = time.time() - start_time
        
        # Show frame sequence to prove freshness
        seq_info = f"Seq: {frame_seq}" if frame_seq >= 0 else "Seq: -"
        print(f"[{elapsed:6.1f}s] Temp: {chip_temp:.1f}°C | Latency: {latency_ms:.0f}ms | Detections: {num_detections} | {seq_info}")
        
        # Log to CSV
        csv_writer.writerow({
            'timestamp': datetime.now().isoformat(),
            'elapsed_sec': elapsed,
            'mode': 'still',
            'temperature_c': chip_temp,
            'latency_ms': latency_ms,
            'num_detections': num_detections,
            'trigger_count': trigger_count,
            'frame_seq': frame_seq,
            'frame_ts': frame_ts
        })
        
        # Wait for next interval
        time.sleep(interval_sec)
    
    print(f"\nCompleted {trigger_count} triggers")
    print(f"Frame sequences: {last_seq_num - trigger_count + 1} -> {last_seq_num} (should increment each trigger)")
    return chip_temp


def run_continuous_test(device, detection_queue, interval_sec: float, duration_sec: float, csv_writer):
    """Run continuous mode test for comparison."""
    print(f"\n{'='*60}")
    print("CONTINUOUS MODE TEST")
    print(f"Duration: {duration_sec}s")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    sample_count = 0
    
    while (time.time() - start_time) < duration_sec:
        # Get temperature
        try:
            temps = device.getChipTemperature()
            chip_temp = temps.average
        except:
            chip_temp = -1
        
        # Get latest detection (non-blocking drain then blocking get)
        latency_ms = -1
        num_detections = 0
        
        try:
            # Flush stale
            while detection_queue.has():
                detection_queue.tryGet()
            
            # Get fresh (poll since get(timeout) not supported)
            get_start = time.time()
            det_data = None
            deadline = time.time() + 1.0
            while time.time() < deadline:
                det_data = detection_queue.tryGet()
                if det_data is not None:
                    break
                time.sleep(0.01)
            
            if det_data is not None:
                latency_ms = (time.time() - get_start) * 1000
                num_detections = len(det_data.detections)
                sample_count += 1
        except Exception as e:
            print(f"  Warning: {e}")
        
        elapsed = time.time() - start_time
        print(f"[{elapsed:6.1f}s] Temp: {chip_temp:.1f}°C | Latency: {latency_ms:.0f}ms | Detections: {num_detections}")
        
        # Log to CSV
        csv_writer.writerow({
            'timestamp': datetime.now().isoformat(),
            'elapsed_sec': elapsed,
            'mode': 'continuous',
            'temperature_c': chip_temp,
            'latency_ms': latency_ms,
            'num_detections': num_detections,
            'trigger_count': sample_count
        })
        
        # Sample every interval
        time.sleep(interval_sec)
    
    return chip_temp


def main():
    parser = argparse.ArgumentParser(description="Test still-capture vs continuous mode thermal")
    parser.add_argument("--mode", choices=["still", "continuous", "both"], default="still",
                        help="Test mode: still (triggered), continuous, or both")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Seconds between triggers/samples (default: 5)")
    parser.add_argument("--duration", type=float, default=300.0,
                        help="Test duration in seconds (default: 300 = 5 min)")
    parser.add_argument("--blob", type=str, default=DEFAULT_BLOB_PATH,
                        help="Path to YOLO blob file")
    parser.add_argument("--fps", type=int, default=30,
                        help="FPS for continuous mode (default: 30)")
    parser.add_argument("--output", type=str, default="",
                        help="Output CSV file (default: auto-generated)")
    parser.add_argument("--save-images", action="store_true",
                        help="Save captured images to verify freshness")
    args = parser.parse_args()
    
    # Check blob exists
    if not Path(args.blob).exists():
        # Try alternate path
        alt_path = Path("/home/uday/Downloads/pragati_ros2/data/models/yolov8v2.blob")
        if alt_path.exists():
            args.blob = str(alt_path)
        else:
            print(f"ERROR: Blob file not found: {args.blob}")
            print("Please provide path with --blob option")
            return 1
    
    print(f"Using blob: {args.blob}")
    
    # Setup output CSV
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"/tmp/thermal_test_{args.mode}_{timestamp}.csv"
    
    csv_file = open(args.output, 'w', newline='')
    csv_writer = csv.DictWriter(csv_file, fieldnames=[
        'timestamp', 'elapsed_sec', 'mode', 'temperature_c', 
        'latency_ms', 'num_detections', 'trigger_count', 'frame_seq', 'frame_ts'
    ])
    csv_writer.writeheader()
    
    print(f"Logging to: {args.output}")
    
    modes_to_run = [args.mode] if args.mode != "both" else ["still", "continuous"]
    
    for mode in modes_to_run:
        print(f"\n{'#'*60}")
        print(f"# STARTING {mode.upper()} MODE TEST")
        print(f"{'#'*60}")
        
        if mode == "still":
            pipeline = create_still_capture_pipeline(args.blob)
        else:
            pipeline = create_continuous_pipeline(args.blob, args.fps)
        
        try:
            with dai.Device(pipeline) as device:
                print(f"Connected to device: {device.getMxId()}")
                
                # Get initial temperature
                try:
                    temps = device.getChipTemperature()
                    print(f"Initial temperature: {temps.average:.1f}°C")
                except:
                    print("Warning: Could not read temperature")
                
                if mode == "still":
                    control_queue = device.getInputQueue("control")
                    detection_queue = device.getOutputQueue("detections", maxSize=4, blocking=False)
                    still_queue = device.getOutputQueue("still", maxSize=1, blocking=False)
                    
                    final_temp = run_still_capture_test(
                        device, control_queue, detection_queue, still_queue,
                        args.interval, args.duration, csv_writer, args.save_images
                    )
                else:
                    detection_queue = device.getOutputQueue("detections", maxSize=4, blocking=False)
                    
                    final_temp = run_continuous_test(
                        device, detection_queue,
                        args.interval, args.duration, csv_writer
                    )
                
                print(f"\n{'='*60}")
                print(f"Final temperature ({mode}): {final_temp:.1f}°C")
                print(f"{'='*60}")
                
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        # Cool down between tests
        if args.mode == "both" and mode == "still":
            print("\nCooling down for 60 seconds before continuous test...")
            time.sleep(60)
    
    csv_file.close()
    print(f"\n✅ Results saved to: {args.output}")
    print("\nTo analyze results:")
    print(f"  cat {args.output}")
    
    return 0


if __name__ == "__main__":
    exit(main())
