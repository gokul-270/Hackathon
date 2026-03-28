#!/bin/bash

# Fix header guards to match ROS2 conventions exactly
# ROS2 convention: PACKAGE_NAME__HEADER_NAME_HPP_

BASE_DIR="/home/uday/Downloads/pragati_ros2/src"

echo "🔧 Fixing header guard naming conventions..."

# Fix ODrive Control ROS2 header guards
find "$BASE_DIR/odrive_control_ros2/include" -name "*.hpp" | while read -r file; do
    echo "Processing $file"
    
    # Extract relative path and convert to guard name
    rel_path=$(echo "$file" | sed "s|$BASE_DIR/odrive_control_ros2/include/||")
    guard_name=$(echo "$rel_path" | tr '/' '_' | tr '[:lower:]' '[:upper:]' | sed 's/\.HPP$/_HPP_/')
    
    # Fix the specific issue: should be ODRIVE_CONTROL_ROS2__DEBUG_PRINT_HPP_
    guard_name=$(echo "$guard_name" | sed 's/ODRIVE_CONTROL_ROS2_/ODRIVE_CONTROL_ROS2__/')
    
    echo "  Guard name: $guard_name"
    
    # Fix #ifndef line
    sed -i "s|#ifndef [A-Z_]*$|#ifndef $guard_name|" "$file"
    sed -i "s|#ifndef [A-Z_][A-Z_]*$|#ifndef $guard_name|" "$file"
    
    # Fix #define line  
    sed -i "s|#define [A-Z_]*$|#define $guard_name|" "$file"
    sed -i "s|#define [A-Z_][A-Z_]*$|#define $guard_name|" "$file"
    
    # Fix #endif line
    sed -i "s|#endif.*|#endif  // $guard_name|" "$file"
done

# Fix Yanthra Move header guards
find "$BASE_DIR/yanthra_move/include" -name "*.h" | while read -r file; do
    echo "Processing $file"
    
    # Extract relative path and convert to guard name
    rel_path=$(echo "$file" | sed "s|$BASE_DIR/yanthra_move/include/||")
    guard_name=$(echo "$rel_path" | tr '/' '_' | tr '[:lower:]' '[:upper:]' | sed 's/\.H$/_H_/')
    
    echo "  Guard name: $guard_name"
    
    # Fix #ifndef line
    sed -i "s|#ifndef [A-Z_]*$|#ifndef $guard_name|" "$file"
    sed -i "s|#ifndef [A-Z_][A-Z_]*$|#ifndef $guard_name|" "$file"
    
    # Fix #define line
    sed -i "s|#define [A-Z_]*$|#define $guard_name|" "$file"  
    sed -i "s|#define [A-Z_][A-Z_]*$|#define $guard_name|" "$file"
    
    # Fix #endif line
    sed -i "s|#endif.*|#endif  // $guard_name|" "$file"
done

echo "✅ Header guards fixed!"