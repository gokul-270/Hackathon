#!/bin/bash
# Monitor motor positions in real-time with formatted output

echo "======================================"
echo "Motor Position Monitor"
echo "======================================"
echo ""
echo "Monitoring /joint_states topic..."
echo "Press Ctrl+C to exit"
echo ""

ros2 topic echo /joint_states --once | while IFS= read -r line; do
    if [[ $line == *"name:"* ]]; then
        echo "Joints: $line"
    elif [[ $line == *"position:"* ]]; then
        echo "Positions (rad): $line"
        
        # Extract position values and convert to degrees
        positions=$(echo "$line" | grep -oP '\[.*\]')
        echo "Positions (deg): [calculated from radians]"
    fi
done

# Alternative: Continuous monitoring
echo ""
echo "Starting continuous monitoring..."
ros2 topic echo /joint_states --field position
