#!/bin/bash

echo "Starting comprehensive code style fixes..."

# Fix all files in yanthra_move package
YANTHRA_DIR="/home/uday/Downloads/pragati_ros2/src/yanthra_move"

# Function to fix common formatting issues
fix_file() {
    local file="$1"
    echo "Fixing $file..."
    
    # Remove trailing whitespace
    sed -i 's/[[:space:]]*$//' "$file"
    
    # Fix comment spacing (add space after //)
    sed -i 's|//\([^/[:space:]]\)|// \1|g' "$file"
    
    # Fix long lines by breaking them appropriately
    # This is more complex and needs careful handling per file type
}

# Fix all header files
find "$YANTHRA_DIR/include" -name "*.h" -o -name "*.hpp" | while read file; do
    fix_file "$file"
done

# Fix all source files  
find "$YANTHRA_DIR/src" -name "*.cpp" -o -name "*.c" | while read file; do
    fix_file "$file"
done

echo "Basic formatting fixes completed."

# Now let's fix specific long line issues in joint_move.h
echo "Fixing long lines in joint_move.h..."

JOINT_MOVE_H="$YANTHRA_DIR/include/yanthra_move/joint_move.h"

# Fix long lines by breaking them appropriately
sed -i 's/static rclcpp::Client<odrive_control_ros2::srv::JointHoming>::SharedPtr joint_homing_service;/static rclcpp::Client<odrive_control_ros2::srv::JointHoming>::SharedPtr\n    joint_homing_service;/' "$JOINT_MOVE_H"

sed -i 's/static rclcpp::Client<odrive_control_ros2::srv::JointHoming>::SharedPtr joint_idle_service;/static rclcpp::Client<odrive_control_ros2::srv::JointHoming>::SharedPtr\n    joint_idle_service;/' "$JOINT_MOVE_H"

sed -i 's/static rclcpp::Client<odrive_control_ros2::srv::JointPositionCommand>::SharedPtr joint_position_service;/static rclcpp::Client<odrive_control_ros2::srv::JointPositionCommand>::SharedPtr\n    joint_position_service;/' "$JOINT_MOVE_H"

echo "Code style fixes completed!"