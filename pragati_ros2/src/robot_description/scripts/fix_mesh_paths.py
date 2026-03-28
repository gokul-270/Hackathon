#!/usr/bin/env python3
"""
Fix mesh paths in URDF for Gazebo Harmonic

Gazebo Harmonic doesn't properly resolve package:// URIs, so we need to
convert them to file:// URIs with absolute paths.
"""
import sys
import os
import re


def fix_mesh_paths(urdf_content, package_name, install_path):
    """
    Replace package:// URIs with file:// URIs
    
    Args:
        urdf_content: URDF XML string
        package_name: Name of the package (e.g., 'robot_description')
        install_path: Absolute path to the package install directory
    
    Returns:
        Modified URDF string with fixed paths
    """
    # Pattern to match: package://robot_description/meshes/filename.STL
    pattern = f'package://{package_name}/(meshes/[^"]+)'
    
    def replace_path(match):
        relative_path = match.group(1)
        absolute_path = os.path.join(install_path, relative_path)
        return f'file://{absolute_path}'
    
    fixed_urdf = re.sub(pattern, replace_path, urdf_content)
    return fixed_urdf


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: fix_mesh_paths.py <urdf_file> <package_name> <install_path>")
        sys.exit(1)
    
    urdf_file = sys.argv[1]
    package_name = sys.argv[2]
    install_path = sys.argv[3]
    
    # Read URDF
    with open(urdf_file, 'r') as f:
        urdf_content = f.read()
    
    # Fix paths
    fixed_urdf = fix_mesh_paths(urdf_content, package_name, install_path)
    
    # Output to stdout (can be redirected)
    print(fixed_urdf)
