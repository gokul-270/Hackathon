# Emergency Motor Stop Script

## Overview

The `emergency_motor_stop.sh` script provides a safe way to stop all motors after the main Pragati ROS2 system is killed, shut down, or experiences an unexpected failure.

**Location:** `/home/uday/Downloads/pragati_ros2/emergency_motor_stop.sh`

## When to Use

Use this script in the following situations:

1. **After system crash** - If the ROS2 system crashes and motors are still running
2. **After Ctrl+C** - If you stopped the main system but motors didn't shut down properly
3. **Emergency stop** - When you need to immediately stop all motor movement
4. **System cleanup** - Before restarting the system to ensure clean state
5. **Power cycle** - Before powering down the robot completely

## What It Does

The script performs a comprehensive 5-step shutdown sequence:

### Step 1: Stopping ROS2 Processes
- Terminates all `ros2 launch` processes with SIGINT
- Stops `yanthra_move_node` gracefully
- Stops `mg6010_controller` gracefully

### Step 2: Commanding Motors to IDLE State
- Calls `/joint_idle` service for all joints (0, 1, 2, 3)
- Uses ROS2 services to command motors to safe idle state
- Waits for motor controller to acknowledge commands

### Step 3: Stopping MG6010 CAN Motors
- Publishes zero position commands to all joint position topics:
  - `/joint2_position_controller/command`
  - `/joint3_position_controller/command`
  - `/joint4_position_controller/command`
  - `/joint5_position_controller/command`

### Step 4: Hardware-Level Motor Shutdown
- Sends CAN bus emergency stop commands directly to MG6010 motors
- Uses `cansend` to transmit motor OFF command (0x80) to motors 1-4
- CAN IDs: 0x141, 0x142, 0x143, 0x144

### Step 5: Final Cleanup
- Force-kills any remaining motor-related processes (SIGKILL)
- Stops ROS2 daemon to clean up communication layer
- Ensures complete system shutdown

## Usage

### Basic Usage
```bash
# Run from any directory
/home/uday/Downloads/pragati_ros2/emergency_motor_stop.sh

# Or if you're in the workspace directory
./emergency_motor_stop.sh
```

### Quick Access Alias (Recommended)
Add to your `~/.bashrc` for quick access:
```bash
alias emstop='/home/uday/Downloads/pragati_ros2/emergency_motor_stop.sh'
```

Then reload:
```bash
source ~/.bashrc
```

Now you can run it from anywhere:
```bash
emstop
```

### Integration with System Shutdown
To automatically run on system shutdown, create a systemd service:

```bash
sudo nano /etc/systemd/system/pragati-emergency-stop.service
```

Add:
```ini
[Unit]
Description=Pragati Robot Emergency Motor Stop
DefaultDependencies=no
Before=shutdown.target reboot.target halt.target

[Service]
Type=oneshot
ExecStart=/home/uday/Downloads/pragati_ros2/emergency_motor_stop.sh
TimeoutStartSec=30

[Install]
WantedBy=halt.target reboot.target shutdown.target
```

Enable it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pragati-emergency-stop.service
```

## Requirements

### Software Requirements
- ROS2 Humble (or compatible version)
- Workspace built and sourced: `/home/uday/Downloads/pragati_ros2/install/setup.bash`
- `pkill` command (usually pre-installed)

### Optional Requirements
- `cansend` command from `can-utils` package (for hardware CAN control)
  ```bash
  sudo apt install can-utils
  ```
- CAN interface `can0` configured (for hardware motor control)

### Running Without Hardware
The script will safely handle missing hardware:
- If ROS2 services aren't available, it skips service calls
- If CAN interface isn't available, it skips CAN commands
- All steps include fallback handling

## Verification

After running the script, verify motors are stopped:

### 1. Visual Inspection
- Check that all robot joints have stopped moving
- Verify no unusual vibrations or sounds from motors

### 2. Check Motor LED Indicators
- MG6010 motors have LED status indicators
- LEDs should show idle/off state (refer to MG6010 documentation)

### 3. Monitor CAN Bus (if available)
```bash
# Watch for motor activity on CAN bus
candump can0
```
You should see no motor command traffic after the script runs.

### 4. Check Process Status
```bash
# Verify no ROS2 processes running
ps aux | grep ros2

# Verify no motor controller processes
ps aux | grep mg6010
ps aux | grep yanthra_move
```

## Troubleshooting

### Motors Still Running After Script
If motors are still active after running the script:

1. **Run the script again** - Sometimes communication delays require retry
   ```bash
   ./emergency_motor_stop.sh
   ```

2. **Manually power off motor controller** - Use physical power switch if available

3. **Disconnect 24V power supply** - Last resort, disconnect main motor power:
   - Locate 24V power supply for MG6010 motors
   - Safely disconnect power supply or use emergency stop button
   - Wait for motors to fully stop

### Script Fails to Source ROS2
If you see:
```
❌ ERROR: No ROS2 installation found!
```

**Solution:** Edit the script and update the workspace path:
```bash
WORKSPACE_DIR="/your/actual/path/to/pragati_ros2"
```

### CAN Commands Fail
If you see:
```
ℹ️  cansend command not available
```

**Solution:** Install can-utils:
```bash
sudo apt install can-utils
```

If you see:
```
ℹ️  CAN interface can0 not available
```

**Possible causes:**
- CAN interface not configured
- Running in simulation mode (expected)
- Hardware not connected

## Safety Notes

⚠️ **IMPORTANT SAFETY INFORMATION**

1. **Always verify motors are stopped** - Visual inspection is critical
2. **Keep emergency stop button accessible** - Physical e-stop should always be available
3. **Never rely solely on software** - Software can fail; have hardware backup
4. **Test in simulation first** - Test this script in simulation before using with real hardware
5. **Understand your system** - Know your motor controller wiring and power sources

## Log Files

The script outputs detailed logs with timestamps. To save logs:

```bash
./emergency_motor_stop.sh 2>&1 | tee emergency_stop_$(date +%Y%m%d_%H%M%S).log
```

This creates a log file like: `emergency_stop_20251024_120000.log`

## Related Scripts

- `test_start_switch.sh` - Test start switch behavior
- `scripts/cleanup_ros2.sh` - General ROS2 cleanup (if exists)

## Support

If you encounter issues:
1. Check the log output for specific error messages
2. Verify ROS2 workspace is properly built and sourced
3. Ensure motor controller is properly configured
4. Review the MG6010 motor controller documentation

## Version History

- **v1.0** (2025-10-24) - Initial implementation
  - 5-step shutdown sequence
  - ROS2 service-based motor idle
  - CAN bus emergency stop
  - Comprehensive error handling

---

**Maintainer:** Pragati Robotics Team  
**Last Updated:** 2025-10-24
