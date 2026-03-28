#!/usr/bin/env python3
"""
Export OAK-D Lite factory calibration to ROS2-compatible YAML files.
Run this script once with the camera connected to generate calibration files.

Usage:
    source venv/bin/activate
    python3 export_calibration.py
"""

import depthai as dai
import yaml
import numpy as np
from datetime import datetime
import sys

def export_calibration():
    """Export factory calibration from OAK-D Lite to YAML files."""
    try:
        print("🔍 Searching for OAK-D Lite camera...")
        with dai.Device() as device:
            print(f"✅ Found device: {device.getMxId()}")
            
            calib = device.readCalibration()
            
            # Get camera intrinsics for different resolutions
            rgb_intrinsics = calib.getCameraIntrinsics(dai.CameraBoardSocket.RGB, 1920, 1080)
            left_intrinsics = calib.getCameraIntrinsics(dai.CameraBoardSocket.LEFT, 640, 400)
            right_intrinsics = calib.getCameraIntrinsics(dai.CameraBoardSocket.RIGHT, 640, 400)
            
            # Get distortion coefficients
            rgb_dist = calib.getDistortionCoefficients(dai.CameraBoardSocket.RGB)
            left_dist = calib.getDistortionCoefficients(dai.CameraBoardSocket.LEFT)
            right_dist = calib.getDistortionCoefficients(dai.CameraBoardSocket.RIGHT)
            
            # Get stereo baseline
            baseline = calib.getBaselineDistance()  # cm
            
            print(f"\n📊 Camera Calibration Info:")
            print(f"   Device MXID: {device.getMxId()}")
            print(f"   Stereo Baseline: {baseline:.2f} cm ({baseline/100.0:.4f} m)")
            print(f"   RGB Focal Length: fx={rgb_intrinsics[0][0]:.2f}, fy={rgb_intrinsics[1][1]:.2f}")
            print(f"   RGB Principal Point: cx={rgb_intrinsics[0][2]:.2f}, cy={rgb_intrinsics[1][2]:.2f}")
            
            # Create RGB camera_info (ROS2 format)
            rgb_info = {
                'image_width': 1920,
                'image_height': 1080,
                'camera_name': 'oak_d_lite_rgb',
                'distortion_model': 'plumb_bob',
                'distortion_coefficients': {
                    'rows': 1,
                    'cols': len(rgb_dist),
                    'data': rgb_dist.tolist()
                },
                'camera_matrix': {
                    'rows': 3,
                    'cols': 3,
                    'data': rgb_intrinsics.flatten().tolist()
                },
                'rectification_matrix': {
                    'rows': 3,
                    'cols': 3,
                    'data': np.eye(3).flatten().tolist()
                },
                'projection_matrix': {
                    'rows': 3,
                    'cols': 4,
                    'data': np.hstack([rgb_intrinsics, [[0], [0], [0]]]).flatten().tolist()
                }
            }
            
            # Create left mono camera_info
            left_info = {
                'image_width': 640,
                'image_height': 400,
                'camera_name': 'oak_d_lite_left',
                'distortion_model': 'plumb_bob',
                'distortion_coefficients': {
                    'rows': 1,
                    'cols': len(left_dist),
                    'data': left_dist.tolist()
                },
                'camera_matrix': {
                    'rows': 3,
                    'cols': 3,
                    'data': left_intrinsics.flatten().tolist()
                },
                'rectification_matrix': {
                    'rows': 3,
                    'cols': 3,
                    'data': np.eye(3).flatten().tolist()
                },
                'projection_matrix': {
                    'rows': 3,
                    'cols': 4,
                    'data': np.hstack([left_intrinsics, [[0], [0], [0]]]).flatten().tolist()
                }
            }
            
            # Create right mono camera_info
            right_info = {
                'image_width': 640,
                'image_height': 400,
                'camera_name': 'oak_d_lite_right',
                'distortion_model': 'plumb_bob',
                'distortion_coefficients': {
                    'rows': 1,
                    'cols': len(right_dist),
                    'data': right_dist.tolist()
                },
                'camera_matrix': {
                    'rows': 3,
                    'cols': 3,
                    'data': right_intrinsics.flatten().tolist()
                },
                'rectification_matrix': {
                    'rows': 3,
                    'cols': 3,
                    'data': np.eye(3).flatten().tolist()
                },
                'projection_matrix': {
                    'rows': 3,
                    'cols': 4,
                    'data': np.hstack([right_intrinsics, [[0], [0], [0]]]).flatten().tolist()
                }
            }
            
            # Save stereo parameters
            stereo_params = {
                'baseline_cm': float(baseline),
                'baseline_m': float(baseline / 100.0),
                'export_date': datetime.now().isoformat(),
                'device_mxid': device.getMxId(),
                'rgb_resolution': '1920x1080',
                'mono_resolution': '640x400'
            }
            
            # Generate timestamp for filenames
            timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            
            # Save to YAML files
            print(f"\n💾 Saving calibration files...")
            
            rgb_filename = f'rgb_camera_info_{timestamp}.yaml'
            with open(rgb_filename, 'w') as f:
                yaml.dump(rgb_info, f, default_flow_style=False, sort_keys=False)
            print(f"   ✅ {rgb_filename}")
            
            left_filename = f'left_camera_info_{timestamp}.yaml'
            with open(left_filename, 'w') as f:
                yaml.dump(left_info, f, default_flow_style=False, sort_keys=False)
            print(f"   ✅ {left_filename}")
            
            right_filename = f'right_camera_info_{timestamp}.yaml'
            with open(right_filename, 'w') as f:
                yaml.dump(right_info, f, default_flow_style=False, sort_keys=False)
            print(f"   ✅ {right_filename}")
            
            stereo_filename = f'stereo_params_{timestamp}.yaml'
            with open(stereo_filename, 'w') as f:
                yaml.dump(stereo_params, f, default_flow_style=False, sort_keys=False)
            print(f"   ✅ {stereo_filename}")
            
            # Also save "current" versions (without timestamp)
            with open('rgb_camera_info.yaml', 'w') as f:
                yaml.dump(rgb_info, f, default_flow_style=False, sort_keys=False)
            print(f"   ✅ rgb_camera_info.yaml (current)")
            
            with open('left_camera_info.yaml', 'w') as f:
                yaml.dump(left_info, f, default_flow_style=False, sort_keys=False)
            print(f"   ✅ left_camera_info.yaml (current)")
            
            with open('right_camera_info.yaml', 'w') as f:
                yaml.dump(right_info, f, default_flow_style=False, sort_keys=False)
            print(f"   ✅ right_camera_info.yaml (current)")
            
            with open('stereo_params.yaml', 'w') as f:
                yaml.dump(stereo_params, f, default_flow_style=False, sort_keys=False)
            print(f"   ✅ stereo_params.yaml (current)")
            
            print(f"\n🎉 Calibration export complete!")
            print(f"\n📝 Summary:")
            print(f"   Files saved:")
            print(f"     - Timestamped: {rgb_filename}, {left_filename}, {right_filename}, {stereo_filename}")
            print(f"     - Current: rgb_camera_info.yaml, left_camera_info.yaml, right_camera_info.yaml, stereo_params.yaml")
            print(f"   Device: {device.getMxId()}")
            print(f"   Baseline: {baseline:.2f} cm ({baseline/100.0:.4f} m)")
            
    except RuntimeError as e:
        print(f"❌ Error: Could not find OAK-D Lite camera")
        print(f"   Details: {e}")
        print(f"\n💡 Troubleshooting:")
        print(f"   1. Ensure OAK-D Lite is connected via USB")
        print(f"   2. Check USB cable and port")
        print(f"   3. Verify DepthAI installation: pip show depthai")
        print(f"   4. Try: lsusb | grep '03e7:2485'  # Check for OAK-D Lite")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 70)
    print("OAK-D Lite Calibration Export Tool")
    print("=" * 70)
    export_calibration()
