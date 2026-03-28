#!/usr/bin/env python3
"""
Generate heightmap for agricultural field terrain with gentle slopes and undulations.
Creates a PNG heightmap that Gazebo can use for realistic ground.
"""

import numpy as np
from PIL import Image

def generate_agricultural_heightmap(width=512, height=512, output_file='field_heightmap.png'):
    """
    Generate heightmap with agricultural terrain features:
    - Gentle slopes (field drainage)
    - Small undulations (natural ground variation)
    - Row furrows (drainage channels between crops)
    """
    
    # Create base terrain with sine waves for natural variation
    heightmap = np.zeros((height, width))
    
    # Generate base undulating terrain using multiple sine waves
    for i in range(height):
        for j in range(width):
            # Multiple frequencies for natural look
            val = (np.sin(i / 30.0) * 0.3 +
                   np.sin(j / 40.0) * 0.3 +
                   np.sin((i + j) / 50.0) * 0.2 +
                   np.sin(i / 15.0) * 0.1 +
                   np.sin(j / 20.0) * 0.1)
            heightmap[i][j] = val
    
    # Add gentle slope for field drainage (2-3 degrees)
    # Slope from left to right
    slope_gradient = np.linspace(0, 0.15, width)
    for i in range(height):
        heightmap[i, :] += slope_gradient
    
    # Add cross-slope (front to back) - very gentle
    cross_slope = np.linspace(0, 0.05, height)
    for j in range(width):
        heightmap[:, j] += cross_slope
    
    # Add subtle furrows between crop rows (drainage channels)
    # Rows at y positions: -1.35, -0.45, 0.45, 1.35, 2.25, 3.15, 4.05
    # Map to heightmap coordinates
    row_positions_m = [-0.675, -0.225, 0.225, 0.675, 1.125, 1.575, 2.025]
    
    # Field spans about -5m to +5m in y, heightmap is 512 pixels
    # Center at 256, scale: 512 pixels / 10m = 51.2 pixels/meter
    pixels_per_meter = 51.2
    center_pixel = height // 2
    
    furrow_width_pixels = int(0.2 * pixels_per_meter)  # 20cm furrows
    furrow_depth = 0.03  # 3cm depression
    
    for row_y_m in row_positions_m:
        row_pixel = int(center_pixel + row_y_m * pixels_per_meter)
        if 0 <= row_pixel < height:
            # Create furrow depression
            start = max(0, row_pixel - furrow_width_pixels // 2)
            end = min(height, row_pixel + furrow_width_pixels // 2)
            for i in range(start, end):
                # Smooth gaussian-like depression
                distance = abs(i - row_pixel)
                factor = 1.0 - (distance / (furrow_width_pixels / 2))
                heightmap[i, :] -= furrow_depth * factor
    
    # Normalize to 0-1 range
    heightmap = heightmap - heightmap.min()
    heightmap = heightmap / heightmap.max()
    
    # Scale to reasonable height variation (0-50cm total)
    max_height_m = 0.5
    heightmap = heightmap * max_height_m
    
    # Convert to 16-bit grayscale for better precision
    # Gazebo heightmaps: white = high, black = low
    heightmap_normalized = (heightmap / max_height_m * 65535).astype(np.uint16)
    
    # Save as 16-bit PNG
    img = Image.fromarray(heightmap_normalized, mode='I;16')
    img.save(output_file)
    
    print(f"✓ Generated heightmap: {output_file}")
    print(f"  Size: {width}x{height} pixels")
    print(f"  Height range: 0 to {max_height_m}m ({max_height_m*100:.0f}cm)")
    print(f"  Features: slopes, undulations, drainage furrows")
    
    # Also save 8-bit preview for viewing
    preview = Image.fromarray((heightmap_normalized / 256).astype(np.uint8))
    preview_file = output_file.replace('.png', '_preview.png')
    preview.save(preview_file)
    print(f"  Preview: {preview_file}")
    
    return output_file


if __name__ == '__main__':
    import os
    
    # Generate in vehicle_control/worlds directory
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'worlds')
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, 'field_heightmap.png')
    generate_agricultural_heightmap(output_file=output_path)
    
    print("\nUsage in Gazebo:")
    print("  The heightmap is automatically loaded by cotton_field.sdf")
    print("  White pixels = higher elevation, Black = lower elevation")
