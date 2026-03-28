# Phase 0: Python Wrapper Critical Fixes

**Date:** October 8, 2025  
**Duration:** 1 week (parallel with Phase 1 prep)  
**Files:** `cotton_detect_ros2_wrapper.py`, `cotton_detection_wrapper.launch.py`

---

## Overview

These 5 critical fixes prevent crashes and race conditions in the Python wrapper while we develop the C++ implementation. Each fix is **small, focused, and low-risk**.

---

## Fix 0.1: Subprocess STDOUT/STDERR Deadlock (CRITICAL)

**Problem:** Lines 399-406  
Currently pipes are created but NEVER consumed → OS buffer fills → deadlock

```python
# CURRENT (BROKEN)
self.detection_process = subprocess.Popen(
    ['python3', cotton_detect_script, blob_path],
    stdout=subprocess.PIPE,  # ❌ Created but never read!
    stderr=subprocess.PIPE,  # ❌ Will cause deadlock
    ...
)
```

**Fix:** Redirect to log file (simplest, most reliable)

```python
# NEW (FIXED) - Add after line 395
log_file_path = '/tmp/CottonDetect_subprocess.log'
self.log_file = open(log_file_path, 'w')
self.get_logger().info(f'Subprocess logs redirected to: {log_file_path}')

# Update subprocess launch (lines 399-406)
self.detection_process = subprocess.Popen(
    ['python3', cotton_detect_script, blob_path],
    stdout=self.log_file,        # ✅ Write to file
    stderr=subprocess.STDOUT,    # ✅ Merge stderr into stdout
    env=self._get_cotton_detect_env()
)
```

**Also update _terminate_subprocess (add at line 480):**
```python
# Close log file
if hasattr(self, 'log_file') and self.log_file:
    try:
        self.log_file.close()
        self.get_logger().debug('Closed subprocess log file')
    except Exception as e:
        self.get_logger().warn(f'Error closing log file: {e}')
```

**Lines to modify:**
- Line 395: Add `log_file_path` and `self.log_file`
- Lines 401-402: Change to `stdout=self.log_file, stderr=subprocess.STDOUT`
- Line 404-405: Remove `bufsize=1, universal_newlines=True` (not needed for file)
- Line 480: Add log file cleanup

**Test:** Run for 1 hour with verbose CottonDetect.py output

---

## Fix 0.2: Signal Handler Race Condition (CRITICAL)

**Problem:** Lines 346-349, 414  
Plain boolean `self.camera_ready` is not thread-safe with signals

```python
# CURRENT (BROKEN)
# Line 67 in __init__
self.camera_ready = False  # ❌ Not atomic

# Line 349 in signal handler
self.camera_ready = True   # ❌ Race condition

# Line 414 in main thread
while not self.camera_ready:  # ❌ May never see True
    time.sleep(0.1)
```

**Fix:** Use threading.Event (thread-safe, proper memory barriers)

```python
# Line 67 - Replace boolean with Event
self.camera_ready_event = threading.Event()

# Line 349 - Signal handler (replace line)
def sigusr2_handler(signum, frame):
    \"\"\"Handler for SIGUSR2 signal indicating camera ready.\"\"\"
    self.get_logger().info('Received SIGUSR2 from CottonDetect - Camera ready!')
    self.camera_ready_event.set()  # ✅ Thread-safe

# Line 414-428 - Replace while loop
startup_timeout = self.get_parameter('startup_timeout').value
if not self.camera_ready_event.wait(timeout=startup_timeout):
    self.get_logger().error('CottonDetect startup timeout')
    self._terminate_subprocess()
    raise TimeoutError('CottonDetect failed to send ready signal')

self.get_logger().info('CottonDetect.py initialized successfully!')

# Line 449 - Update monitor (replace line)
self.camera_ready_event.clear()

# Line 692 - Update check (replace line)
if not self.camera_ready_event.is_set():
```

**Lines to modify:**
- Line 67: `self.camera_ready_event = threading.Event()`
- Line 349: `self.camera_ready_event.set()`
- Lines 414-428: Replace while loop with `camera_ready_event.wait(timeout=...)`
- Line 449: `self.camera_ready_event.clear()`
- Line 692: `if not self.camera_ready_event.is_set():`

**Test:** Run with ThreadSanitizer or repeated rapid restarts

---

## Fix 0.3: Atomic File Writes (HIGH)

**Problem:** CottonDetect.py lines 439-441 (in subprocess)  
Non-atomic write → crash during write → corrupt file

```python
# CURRENT in CottonDetect.py (BROKEN)
file2 = open(COTTONDETAILSTXTFILEPATH, "w+")
file2.write(txt)  # ❌ If crash here, file is truncated
file2.close()
```

**Fix:** Use tempfile + atomic rename

**File:** `src/cotton_detection_ros2/scripts/OakDTools/CottonDetect.py`

```python
# Add at top (after line 12)
import tempfile

# Replace lines 439-441 with atomic write
# Create helper function (add around line 200, before HostSync class)
def write_file_atomically(filepath, content):
    \"\"\"Write file atomically using temp file + rename.
    
    This ensures file is never in a half-written state.
    If process crashes during write, old file remains intact.
    \"\"\"
    dir_path = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    
    # Write to temp file in same directory (ensures same filesystem)
    with tempfile.NamedTemporaryFile(
        mode='w',
        dir=dir_path,
        prefix=f'.{filename}.',
        suffix='.tmp',
        delete=False
    ) as tmp_file:
        tmp_file.write(content)
        tmp_file.flush()
        os.fsync(tmp_file.fileno())  # Force to disk
        temp_path = tmp_file.name
    
    # Atomic rename (POSIX guarantee)
    os.replace(temp_path, filepath)
    # If crash before this: old file still exists
    # If crash after this: new file exists
    # Never see partial file!

# Replace line 439-441
write_file_atomically(COTTONDETAILSTXTFILEPATH, txt)
print(f"Wrote to file : {COTTONDETAILSTXTFILEPATH}\\n")
```

**Lines to modify in CottonDetect.py:**
- Line 12: Add `import tempfile`
- Lines 200-225: Add `write_file_atomically()` function
- Lines 439-441: Replace with single call to `write_file_atomically()`

**Test:** Kill process with `kill -9` during write repeatedly

---

## Fix 0.4: Subprocess Auto-Restart (HIGH)

**Problem:** Lines 439-451  
TODO comment, no implementation → permanent failure if subprocess crashes

```python
# CURRENT (BROKEN)
def monitor_process():
    while self.running:
        if self.detection_process and self.detection_process.poll() is not None:
            self.get_logger().error('CottonDetect process died unexpectedly!')
            self.camera_ready = False
```

**Fix:** Add restart logic with exponential backoff

```python
# Add at top of __init__ (after line 67)
self.restart_attempts = []  # Track restart timestamps
self.max_restarts = 3
self.restart_window_s = 60

# Replace lines 439-451 (entire monitor_process function)
def monitor_process():
    \"\"\"Monitor subprocess and restart on crash.\"\"\"
    while self.running:
        if self.detection_process and self.detection_process.poll() is not None:
            exit_code = self.detection_process.returncode
            self.get_logger().error(
                f'CottonDetect died with exit code {exit_code}'
            )
            
            # Log last output
            if hasattr(self, 'log_file') and self.log_file:
                try:
                    with open(self.log_file.name, 'r') as f:
                        lines = f.readlines()
                        last_lines = ''.join(lines[-20:])  # Last 20 lines
                        self.get_logger().error(f'Last output:\\n{last_lines}')
                except Exception as e:
                    self.get_logger().warn(f'Could not read log: {e}')
            
            # Check restart budget
            now = time.time()
            # Remove old restart attempts outside window
            self.restart_attempts = [
                t for t in self.restart_attempts 
                if now - t < self.restart_window_s
            ]
            
            if len(self.restart_attempts) >= self.max_restarts:
                self.get_logger().fatal(
                    f'CottonDetect crashed {self.max_restarts} times in '
                    f'{self.restart_window_s}s. Giving up. Manual restart required.'
                )
                self.camera_ready_event.clear()
                break
            
            # Attempt restart
            self.restart_attempts.append(now)
            restart_num = len(self.restart_attempts)
            self.get_logger().warn(
                f'Attempting restart {restart_num}/{self.max_restarts}...'
            )
            
            self.camera_ready_event.clear()
            
            try:
                # Brief cooldown (exponential backoff)
                cooldown = 2.0 ** (restart_num - 1)  # 1s, 2s, 4s
                time.sleep(cooldown)
                
                # Re-launch subprocess
                self._launch_cotton_detect_subprocess()
                self.get_logger().info('CottonDetect restarted successfully')
            except Exception as e:
                self.get_logger().error(f'Restart failed: {e}')
                # Will try again on next iteration if within budget
        
        time.sleep(1.0)
```

**Lines to modify:**
- Lines 67-69: Add restart tracking variables
- Lines 439-451: Replace entire `monitor_process` function (30 new lines)

**Test:** Kill subprocess 5 times, verify first 3 restart, 4th+ fails

---

## Fix 0.5: Expose simulation_mode in Launch File (LOW)

**Problem:** Parameter exists (line 152) but not in launch file  
Cannot easily test without hardware

```python
# EXISTS in node (line 152)
self.declare_parameter('simulation_mode', False)

# MISSING in launch file
```

**Fix:** Add to launch file

**File:** `launch/cotton_detection_wrapper.launch.py`

Find the DeclareLaunchArgument section and add:

```python
# Add after line ~40 (after other DeclareLaunchArgument calls)
DeclareLaunchArgument(
    'simulation_mode',
    default_value='false',
    description='Run in simulation mode without hardware (generates synthetic detections)'
),
```

Then add to node parameters (around line 120):

```python
# In Node parameters dict
'simulation_mode': LaunchConfiguration('simulation_mode'),
```

**Test:**
```bash
# With hardware
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py simulation_mode:=false

# Without hardware (simulation)
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py simulation_mode:=true
```

---

## Implementation Checklist

### Fix 0.1: Subprocess Deadlock
- [ ] Open log file before subprocess launch
- [ ] Change stdout/stderr to use log file
- [ ] Remove bufsize and universal_newlines
- [ ] Add log file close in _terminate_subprocess
- [ ] Test: 1 hour run with verbose output

### Fix 0.2: Signal Race Condition
- [ ] Import threading if not already
- [ ] Replace `camera_ready` bool with `camera_ready_event`
- [ ] Update signal handler to use `.set()`
- [ ] Replace while loop with `.wait(timeout=...)`
- [ ] Update monitor to use `.clear()`
- [ ] Update detection check to use `.is_set()`
- [ ] Test: Rapid restarts (10 times)

### Fix 0.3: Atomic File Writes
- [ ] Add `import tempfile` to CottonDetect.py
- [ ] Add `write_file_atomically()` function
- [ ] Replace file write with atomic version
- [ ] Test: Kill -9 during write (20 times)

### Fix 0.4: Auto-Restart
- [ ] Add restart tracking variables to __init__
- [ ] Replace monitor_process function
- [ ] Test: Kill subprocess 5 times
- [ ] Verify: First 3 restart, 4th+ fails gracefully

### Fix 0.5: Simulation Mode
- [ ] Add DeclareLaunchArgument to launch file
- [ ] Add parameter to Node config
- [ ] Test: Launch with simulation_mode:=true
- [ ] Test: Launch with simulation_mode:=false

---

## Testing Plan

### Test 1: Subprocess Stability (1 hour)
```bash
# Terminal 1: Launch node
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py

# Terminal 2: Monitor log
tail -f /tmp/CottonDetect_subprocess.log

# Terminal 3: Trigger detections repeatedly
for i in {1..360}; do
    ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
    sleep 10
done

# Verify: No deadlocks, all detections work
```

### Test 2: Signal Race Condition
```bash
# Test rapid restarts
for i in {1..10}; do
    ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py &
    LAUNCH_PID=$!
    sleep 5
    kill $LAUNCH_PID
    wait $LAUNCH_PID
    echo "Restart $i complete"
done

# Verify: All startups succeed, no hangs
```

### Test 3: Atomic Writes
```bash
# Terminal 1: Run detection loop
while true; do
    ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"
    sleep 1
done

# Terminal 2: Kill subprocess repeatedly
for i in {1..20}; do
    sleep 3
    pkill -9 -f CottonDetect.py
    echo "Kill $i"
done

# Terminal 3: Check file integrity
watch -n 0.5 'wc -l /home/ubuntu/pragati/outputs/cotton_details.txt && cat /home/ubuntu/pragati/outputs/cotton_details.txt'

# Verify: File never corrupted, always valid format
```

### Test 4: Auto-Restart
```bash
# Launch node
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py

# In another terminal, kill subprocess 5 times
for i in {1..5}; do
    sleep 5
    echo "Kill attempt $i"
    pkill -9 -f CottonDetect.py
done

# Verify logs show:
# - Attempts 1-3: "Attempting restart X/3..." then "restarted successfully"
# - Attempt 4+: "Giving up. Manual restart required."
```

### Test 5: Simulation Mode
```bash
# Test simulation
ros2 launch cotton_detection_ros2 cotton_detection_wrapper.launch.py simulation_mode:=true

# Call detection
ros2 service call /cotton_detection/detect cotton_detection_ros2/srv/CottonDetection "{detect_command: 1}"

# Verify: Returns synthetic data without camera
```

---

## Exit Criteria

- [x] All 5 fixes implemented
- [ ] All 5 tests pass
- [ ] No deadlocks in 1-hour test
- [ ] No race conditions in 10 rapid restarts
- [ ] File writes atomic (verified 20 kills)
- [ ] Auto-restart works (3 successful, 4th fails gracefully)
- [ ] Simulation mode accessible via launch

---

## Risk Assessment

| Fix | Risk | Mitigation |
|-----|------|------------|
| 0.1 | Log file grows large | Can add logrotate later if needed |
| 0.2 | Event vs bool behavior different | Thoroughly test all code paths |
| 0.3 | Temp file permissions | Use same directory for temp file |
| 0.4 | Restart loop if persistent issue | Limit to 3 attempts per minute |
| 0.5 | None | Simple parameter addition |

---

**Estimated Total Time:** 
- Implementation: 8-10 hours
- Testing: 4-6 hours  
- **Total: 12-16 hours (~2 days)**

**Status:** ⬜ Not Started  
**Assigned:** TBD  
**Target Completion:** October 11, 2025
