#!/bin/bash
cd /home/uday/Downloads/pragati_ros2
source install/setup.bash

# Run the node and pipe enter to it after a delay
echo "Starting yanthra_move_node..."
echo "" | timeout 30 ros2 run yanthra_move yanthra_move_node