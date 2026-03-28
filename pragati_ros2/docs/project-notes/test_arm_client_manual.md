# ARM Client Manual Testing Guide

Since yanthra_move requires motor_control node in production, we'll test the ARM client components separately.

## Test 1: MQTT Broker Connectivity

```bash
# Terminal 1: Subscribe to ARM status topic
mosquitto_sub -h localhost -t "topic/ArmStatus_arm5" -v

# Terminal 2: Publish test commands
mosquitto_pub -h localhost -t "topic/start_switch_input_" -m "1"
mosquitto_pub -h localhost -t "topic/shutdown_switch_input" -m "1"
```

## Test 2: ROS-2 Topics (Without yanthra_move)

Test that ARM_client.py can publish to ROS-2 topics:

```bash
# Terminal 1: Monitor ROS-2 topics
ros2 topic echo /start_switch/command &
ros2 topic echo /shutdown_switch/command &

# Terminal 2: Start ARM client (will fail to connect to service, that's OK)
source install/setup.bash
python3 launch/ARM_client.py

# Terminal 3: Send MQTT commands
mosquitto_pub -h localhost -t "topic/start_switch_input_" -m "1"
# Check Terminal 1 - should see Bool message with data: true
```

## Test 3: Complete System (With motor_control)

If you have access to the physical robot or motor_control simulator:

```bash
# Terminal 1: Start motor_control node
ros2 run motor_control motor_control_node --ros-args --params-file src/yanthra_move/config/production.yaml

# Terminal 2: Start yanthra_move
ros2 run yanthra_move yanthra_move_node --ros-args --params-file src/yanthra_move/config/production.yaml

# Terminal 3: Start ARM client
python3 launch/ARM_client.py

# Terminal 4: Monitor ARM status
watch -n 1 'ros2 service call /yanthra_move/current_arm_status yanthra_move/srv/ArmStatus "{}"'

# Terminal 5: Send commands via MQTT
mosquitto_pub -h localhost -t "topic/start_switch_input_" -m "1"
```

## Expected Behavior

**MQTT → ROS-2 Flow:**
1. MQTT command received on `topic/start_switch_input_`
2. ARM_client.py publishes to `/start_switch/command` (ROS-2)
3. yanthra_move receives start command
4. yanthra_move updates `arm_status_` (ready → busy → ready)
5. ARM_client.py polls service and publishes status to MQTT
6. Vehicle host receives status on `topic/ArmStatus_arm5`

**Status Lifecycle:**
- `UNINITIALISED` → ARM client starting
- `ready` → System ready for operation
- `ACK` → Command acknowledged (brief state)
- `busy` → Operation in progress
- `error` → Shutdown or error state

## Quick Validation (No Hardware)

Just verify the code builds and ARM_client.py can start:

```bash
# Build
colcon build --packages-select yanthra_move

# Test imports
python3 -c "from yanthra_move.srv import ArmStatus; import paho.mqtt.client; print('✓ All imports OK')"

# Check MQTT broker
mosquitto_pub -h localhost -t "test" -m "hello" && echo "✓ MQTT broker OK"

# Check ARM_client syntax
python3 -m py_compile launch/ARM_client.py && echo "✓ ARM_client.py syntax OK"
```

## Production Deployment

When deploying to the actual robot at `10.42.0.10`:

1. Edit `launch/ARM_client.py` line 47-48:
   ```python
   MQTT_ADDRESS = '10.42.0.10'  # Production broker
   # MQTT_ADDRESS = 'localhost'  # Local testing broker
   ```

2. Ensure all nodes start in order:
   - motor_control
   - yanthra_move
   - ARM_client.py

3. Monitor logs for any connection issues
