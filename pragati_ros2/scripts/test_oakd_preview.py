#!/usr/bin/env python3
"""
Simple OAK-D Lite Camera Preview Test
Tests camera functionality and displays live preview with resolution and depth info
Press 'q' to quit
"""

import sys
import cv2
import depthai as dai
import numpy as np
import time

def main():
    print("🎥 OAK-D Lite Camera Preview Test (RGB + Depth)")
    print("=" * 50)
    
    # Create pipeline
    pipeline = dai.Pipeline()
    
    # Create RGB camera node
    cam_rgb = pipeline.createColorCamera()
    cam_rgb.setPreviewSize(1920, 1080)
    cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    cam_rgb.setInterleaved(False)
    cam_rgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
    cam_rgb.setFps(30)
    
    # Create mono cameras for stereo depth
    mono_left = pipeline.createMonoCamera()
    mono_right = pipeline.createMonoCamera()
    stereo = pipeline.createStereoDepth()
    
    # Configure mono cameras
    mono_left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
    mono_left.setBoardSocket(dai.CameraBoardSocket.CAM_B)
    mono_left.setFps(30)
    
    mono_right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
    mono_right.setBoardSocket(dai.CameraBoardSocket.CAM_C)
    mono_right.setFps(30)
    
    # Configure stereo depth
    stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
    stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)  # Align to RGB camera
    stereo.setOutputSize(1920, 1080)
    stereo.setLeftRightCheck(True)
    stereo.setExtendedDisparity(False)
    stereo.setSubpixel(False)
    
    # Link mono cameras to stereo
    mono_left.out.link(stereo.left)
    mono_right.out.link(stereo.right)
    
    # Create outputs
    xout_rgb = pipeline.createXLinkOut()
    xout_rgb.setStreamName("rgb")
    cam_rgb.preview.link(xout_rgb.input)
    
    xout_depth = pipeline.createXLinkOut()
    xout_depth.setStreamName("depth")
    stereo.depth.link(xout_depth.input)
    
    print("\n📋 Camera Configuration:")
    print(f"   RGB: 1920x1080 @ 30 FPS")
    print(f"   Stereo: 400p mono @ 30 FPS")
    print(f"   Depth: Aligned to RGB")
    print(f"   Format: BGR")
    
    # Connect to device
    try:
        print("\n🔌 Connecting to OAK-D Lite...")
        device = dai.Device(pipeline)
        device.startPipeline()
        
        # Get device info
        print(f"\n✅ Device Connected!")
        print(f"   MX ID: {device.getMxId()}")
        print(f"   USB Speed: {device.getUsbSpeed().name}")
        
        # Get camera queues
        queue_rgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
        queue_depth = device.getOutputQueue(name="depth", maxSize=4, blocking=False)
        
        print("\n📸 Preview Window Controls:")
        print("   Press 'q' to quit")
        print("   Press 's' to save snapshot")
        print("   Press 'd' to toggle depth colormap")
        print("   Click on image to see depth at that point")
        print("\n🎬 Starting preview...\n")
        
        frame_count = 0
        start_time = time.time()
        last_fps_time = start_time
        fps = 0.0
        snapshot_count = 0
        show_depth_colormap = False
        mouse_x, mouse_y = -1, -1
        
        # Mouse callback to get depth at clicked point
        def mouse_callback(event, x, y, flags, param):
            nonlocal mouse_x, mouse_y
            if event == cv2.EVENT_LBUTTONDOWN:
                mouse_x, mouse_y = x, y
        
        cv2.namedWindow("OAK-D Lite Preview")
        cv2.setMouseCallback("OAK-D Lite Preview", mouse_callback)
        
        while True:
            # Get RGB frame
            in_rgb = queue_rgb.get()
            if in_rgb is None:
                continue
            
            frame = in_rgb.getCvFrame()
            
            # Get depth frame
            in_depth = queue_depth.get()
            depth_frame = None
            depth_data = None
            if in_depth is not None:
                depth_frame = in_depth.getFrame()
                depth_data = depth_frame.copy()
            
            frame_count += 1
            
            # Calculate FPS
            current_time = time.time()
            if current_time - last_fps_time >= 1.0:
                fps = frame_count / (current_time - last_fps_time)
                frame_count = 0
                last_fps_time = current_time
            
            # Choose display: RGB or depth colormap
            if show_depth_colormap and depth_frame is not None:
                # Convert depth to colormap
                depth_normalized = cv2.normalize(depth_frame, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                display_frame = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_JET)
            else:
                display_frame = frame.copy()
            
            # Add overlay information
            height, width = display_frame.shape[:2]
            
            # Semi-transparent black background for text
            overlay = display_frame.copy()
            cv2.rectangle(overlay, (0, 0), (450, 180), (0, 0, 0), -1)
            display_frame = cv2.addWeighted(overlay, 0.6, display_frame, 0.4, 0)
            
            # Get depth at mouse click or center
            depth_value = "N/A"
            if depth_data is not None:
                if mouse_x >= 0 and mouse_y >= 0 and mouse_x < width and mouse_y < height:
                    depth_mm = depth_data[mouse_y, mouse_x]
                    depth_value = f"{depth_mm:.0f} mm ({depth_mm/1000:.2f} m)"
                    # Draw crosshair at clicked point
                    cv2.drawMarker(display_frame, (mouse_x, mouse_y), (0, 255, 0), 
                                 cv2.MARKER_CROSS, 20, 2)
                else:
                    # Show center depth
                    center_x, center_y = width // 2, height // 2
                    depth_mm = depth_data[center_y, center_x]
                    depth_value = f"{depth_mm:.0f} mm (center)"
            
            # Display info
            mode = "DEPTH" if show_depth_colormap else "RGB"
            info_texts = [
                f"Mode: {mode}",
                f"Resolution: {width}x{height}",
                f"FPS: {fps:.1f}",
                f"Depth: {depth_value}",
                f"Controls: q=quit s=save d=depth",
                f"Click to measure depth"
            ]
            
            y_pos = 25
            for text in info_texts:
                cv2.putText(display_frame, text, (10, y_pos),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                y_pos += 25
            
            # Display frame
            cv2.imshow("OAK-D Lite Preview", display_frame)
            
            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("\n👋 Exiting...")
                break
            elif key == ord('s'):
                # Save snapshot
                snapshot_count += 1
                timestamp = int(time.time())
                rgb_filename = f"oakd_rgb_{snapshot_count}_{timestamp}.jpg"
                cv2.imwrite(rgb_filename, frame)
                print(f"💾 Saved RGB: {rgb_filename}")
                
                if depth_data is not None:
                    depth_filename = f"oakd_depth_{snapshot_count}_{timestamp}.png"
                    cv2.imwrite(depth_filename, depth_frame)
                    print(f"💾 Saved Depth: {depth_filename}")
            elif key == ord('d'):
                # Toggle depth colormap
                show_depth_colormap = not show_depth_colormap
                mode = "DEPTH" if show_depth_colormap else "RGB"
                print(f"🔄 Switched to {mode} mode")
        
        # Cleanup
        cv2.destroyAllWindows()
        device.close()
        
        # Summary
        total_time = time.time() - start_time
        print("\n📊 Test Summary:")
        print(f"   Total Runtime: {total_time:.1f}s")
        print(f"   Average FPS: {fps:.1f}")
        print(f"   Snapshots Saved: {snapshot_count}")
        print("\n✅ Camera test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n🔍 Troubleshooting:")
        print("   1. Check USB cable connection")
        print("   2. Verify OAK-D Lite is powered on")
        print("   3. Try different USB port (USB 3.0 preferred)")
        print("   4. Run: lsusb | grep 03e7")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
