#!/usr/bin/env python3
"""
Simple test script to verify cotton detection functionality
"""

import cv2
import numpy as np
import sys
import os

def test_hsv_detection(image_path):
    """Test HSV-based cotton detection on an image"""
    print(f"Testing HSV detection on: {image_path}")

    # Load image
    image = cv2.imread(image_path)
    if image is None:
        print(f"❌ Failed to load image: {image_path}")
        return False

    print(f"📷 Image loaded: {image.shape}")

    # Convert to HSV
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Define HSV range for cotton (white/light colors)
    lower_bound = np.array([0, 0, 180])  # Low saturation, high value (white)
    upper_bound = np.array([180, 40, 255])  # Full hue range, some saturation, full value

    # Create mask
    mask = cv2.inRange(hsv, lower_bound, upper_bound)

    # Apply morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter contours by area
    min_area = 50
    max_area = 5000
    valid_contours = []
    centers = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if min_area <= area <= max_area:
            valid_contours.append(contour)
            # Calculate center
            M = cv2.moments(contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                centers.append((cx, cy))

    # Draw results
    result_image = image.copy()
    cv2.drawContours(result_image, valid_contours, -1, (0, 255, 0), 2)

    for center in centers:
        cv2.circle(result_image, center, 5, (0, 0, 255), -1)
        cv2.putText(result_image, f"({center[0]}, {center[1]})", (center[0] + 10, center[1]),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

    print(f"🎯 Detected {len(centers)} cotton positions")
    print(f"   HSV Range: {lower_bound} to {upper_bound}")
    print(f"   Contour Area Range: {min_area} - {max_area}")

    # Save result
    output_path = image_path.replace('.jpg', '_detected.jpg')
    cv2.imwrite(output_path, result_image)
    print(f"💾 Result saved to: {output_path}")

    return len(centers) > 0

def main():
    print("🧪 Cotton Detection Test Script")
    print("=" * 40)

    # Test images
    test_images = [
        "/home/uday/Downloads/pragati_ros2/data/inputs/ArucoInputImage.jpg",
        "/home/uday/Downloads/pragati_ros2/data/inputs/img100.jpg"
    ]

    success_count = 0
    for image_path in test_images:
        if os.path.exists(image_path):
            if test_hsv_detection(image_path):
                success_count += 1
            print()
        else:
            print(f"⚠️  Test image not found: {image_path}")

    print("=" * 40)
    print(f"✅ Test completed: {success_count}/{len(test_images)} images processed successfully")

    if success_count == len(test_images):
        print("🎉 All tests passed! HSV detection is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())