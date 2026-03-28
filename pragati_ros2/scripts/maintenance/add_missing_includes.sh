#!/bin/bash

# Add missing includes flagged by cpplint
echo "🔧 Adding missing includes..."

# Add missing string include to gpio_control_functions.hpp
if ! grep -q "#include <string>" "/home/uday/Downloads/pragati_ros2/src/odrive_control_ros2/include/odrive_control_ros2/gpio_control_functions.hpp"; then
    echo "Adding #include <string> to gpio_control_functions.hpp"
    sed -i '20a #include <string>' "/home/uday/Downloads/pragati_ros2/src/odrive_control_ros2/include/odrive_control_ros2/gpio_control_functions.hpp"
fi

# Add missing utility include to odrive_can_functions.hpp  
if ! grep -q "#include <utility>" "/home/uday/Downloads/pragati_ros2/src/odrive_control_ros2/include/odrive_control_ros2/odrive_can_functions.hpp"; then
    echo "Adding #include <utility> to odrive_can_functions.hpp"
    sed -i '20a #include <utility>' "/home/uday/Downloads/pragati_ros2/src/odrive_control_ros2/include/odrive_control_ros2/odrive_can_functions.hpp"
fi

# Add missing string include to safety_monitor.hpp
if ! grep -q "#include <string>" "/home/uday/Downloads/pragati_ros2/src/odrive_control_ros2/include/odrive_control_ros2/safety_monitor.hpp"; then
    echo "Adding #include <string> to safety_monitor.hpp"
    sed -i '20a #include <string>' "/home/uday/Downloads/pragati_ros2/src/odrive_control_ros2/include/odrive_control_ros2/safety_monitor.hpp"
fi

echo "✅ Missing includes added!"