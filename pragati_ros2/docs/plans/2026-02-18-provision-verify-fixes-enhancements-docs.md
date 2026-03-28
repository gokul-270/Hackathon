# Provision/Verify: Bug Fixes, Enhancements, and Documentation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix bugs in the `--provision`/`--verify` implementation, enhance verification to cover CAN/camera/ROS2/system health, and document the feature across all relevant files.

**Architecture:** All changes are in `sync.sh` (provision/verify functions), the `systemd/*.service` files (dependency fix), and documentation files. No new scripts -- only modifications. Verification enhancements add new checks inside the existing `run_verify()` SSH heredoc and corresponding provisions inside `run_provision()`.

**Tech Stack:** Bash, systemd, SSH, rsync

---

## Part A: Bug Fixes (4 tasks)

### Task 1: Fix pigpiod service naming mismatch

Both `vehicle_launch.service` and `arm_launch.service` reference `pigpiod_custom.service` in their `After=` and `Wants=` directives, but the repo only ships `pigpiod.service`. No `pigpiod_custom.service` exists in the repo or is installed by provisioning.

**Files:**
- Modify: `systemd/vehicle_launch.service:3,5`
- Modify: `systemd/arm_launch.service:3-4`

**Step 1: Fix vehicle_launch.service**

Change lines 3 and 5 from `pigpiod_custom.service` to `pigpiod.service`:

```
After=network-online.target pigpiod.service
...
Wants=network-online.target pigpiod.service
```

**Step 2: Fix arm_launch.service**

Same change -- lines 3-4 from `pigpiod_custom.service` to `pigpiod.service`.

**Step 3: Update run_verify() pigpiod check**

In `sync.sh`, the verify check (around line 869-874) currently checks for both `pigpiod.service` OR `pigpiod_custom.service`. Now that we've standardized, simplify to only check `pigpiod.service` but keep the OR for backward compatibility with RPis that may still have the old name.

No change needed -- the current check is already correct for backward compat.

**Step 4: Verify syntax**

Run: `bash -n sync.sh`

---

### Task 2: Fix can_watchdog.sh not copied during provisioning

The `can-watchdog@.service` has `ConditionPathExists=/usr/local/sbin/can_watchdog.sh`. Provisioning copies the service file but never copies the watchdog script. Without the script, the service refuses to start.

**Files:**
- Modify: `sync.sh` -- `run_provision()` function, service installation heredoc (around line 671-748)

**Step 1: Add can_watchdog.sh copy to the service install heredoc**

Before the `try_install_service "can-watchdog@.service"` line, add:

```bash
# Copy can_watchdog script (required by can-watchdog@.service ConditionPathExists)
CAN_WATCHDOG_SRC="${REPO_DIR}/scripts/maintenance/can/can_watchdog.sh"
if [ -f "$CAN_WATCHDOG_SRC" ]; then
    if sudo cp "$CAN_WATCHDOG_SRC" /usr/local/sbin/can_watchdog.sh && \
       sudo chmod +x /usr/local/sbin/can_watchdog.sh; then
        echo "[OK] Copied can_watchdog.sh to /usr/local/sbin/"
    else
        echo "[FAIL] Could not copy can_watchdog.sh"
        install_fail=$((install_fail + 1))
        errors="${errors}\n  - can_watchdog.sh: copy failed"
    fi
else
    echo "[WARN] can_watchdog.sh not found at $CAN_WATCHDOG_SRC"
fi
```

**Step 2: Verify syntax**

Run: `bash -n sync.sh`

---

### Task 3: Fix SSH keepalive check to verify content, not just existence

Currently the verify check only tests if `/etc/ssh/sshd_config.d/keepalive.conf` exists. An empty or malformed file passes.

**Files:**
- Modify: `sync.sh` -- `run_verify()` SSH heredoc, check #3 (around line 847-851)

**Step 1: Replace existence check with content check**

```bash
# 3. SSH keepalive config
if grep -q "ClientAliveInterval" /etc/ssh/sshd_config.d/keepalive.conf 2>/dev/null; then
    check_fix "SSH keepalive configured (ClientAliveInterval)" "OK"
else
    check_fix "SSH keepalive configured (ClientAliveInterval)" "MISSING"
fi
```

**Step 2: Verify syntax**

Run: `bash -n sync.sh`

---

### Task 4: Fix WiFi power save n/a logic

When `iw dev wlan0 get power_save` returns nothing (no WiFi adapter), the check passes as OK. For headless RPis where WiFi is the backup interface, this masks a real issue. Change to: `n/a` = OK still (Ethernet-primary robots don't need WiFi), but log it as informational, not silent.

**Files:**
- Modify: `sync.sh` -- `run_verify()` SSH heredoc, check #4 (around line 854-859)

**Step 1: Improve WiFi check messaging**

```bash
# 4. WiFi power save off
wifi_ps=$(iw dev wlan0 get power_save 2>/dev/null | awk '{print $NF}' || echo "n/a")
if [ "$wifi_ps" = "off" ]; then
    check_fix "WiFi power save disabled" "OK"
elif [ "$wifi_ps" = "n/a" ]; then
    check_fix "WiFi power save (no WiFi adapter -- N/A)" "OK"
else
    check_fix "WiFi power save disabled (currently: ${wifi_ps})" "MISSING"
fi
```

**Step 2: Verify syntax**

Run: `bash -n sync.sh`

---

## Part B: Verification Enhancements (3 tasks)

### Task 5: Add CAN bus health checks to run_verify()

Add 3 new checks after the existing CAN watchdog service check (#5):

**Files:**
- Modify: `sync.sh` -- `run_verify()` SSH heredoc, after check #6 (pigpiod)

**Step 1: Add CAN verification checks**

Insert after the pigpiod check block:

```bash
# B1. can_watchdog.sh script exists
if [ -x /usr/local/sbin/can_watchdog.sh ]; then
    check_fix "can_watchdog.sh installed at /usr/local/sbin/" "OK"
else
    check_fix "can_watchdog.sh installed at /usr/local/sbin/" "MISSING"
fi

# B2. CAN interface can0 exists
if ip link show can0 &>/dev/null; then
    check_fix "CAN interface can0 exists" "OK"
else
    check_fix "CAN interface can0 exists" "MISSING"
fi

# B3. SPI device exists (required by CAN HAT)
if [ -e /dev/spidev0.1 ]; then
    check_fix "SPI device /dev/spidev0.1 exists" "OK"
else
    check_fix "SPI device /dev/spidev0.1 exists" "MISSING"
fi
```

**Step 2: Verify syntax**

Run: `bash -n sync.sh`

---

### Task 6: Add OAK-D camera and ROS2 checks to run_verify()

**Files:**
- Modify: `sync.sh` -- `run_verify()` SSH heredoc, after the role-specific checks

**Step 1: Add camera and ROS2 checks**

Insert before the `VERIFY_SUMMARY` line:

```bash
# B4. OAK-D udev rules installed
if [ -f /etc/udev/rules.d/80-movidius.rules ]; then
    check_fix "OAK-D camera udev rules installed" "OK"
else
    check_fix "OAK-D camera udev rules installed" "MISSING"
fi

# B5. ROS2 Jazzy installed
if [ -f /opt/ros/jazzy/setup.bash ]; then
    check_fix "ROS2 Jazzy installed" "OK"
else
    check_fix "ROS2 Jazzy installed" "MISSING"
fi

# B6. Workspace built (install/setup.bash exists)
if [ -f "${HOME}/pragati_ros2/install/setup.bash" ]; then
    check_fix "ROS2 workspace built (install/setup.bash)" "OK"
else
    check_fix "ROS2 workspace built (install/setup.bash)" "MISSING"
fi
```

**Step 2: Verify syntax**

Run: `bash -n sync.sh`

---

### Task 7: Add system health checks to run_verify()

**Files:**
- Modify: `sync.sh` -- `run_verify()` SSH heredoc, after the camera/ROS2 checks

**Step 1: Add system health checks**

```bash
# B7. Disk space sufficient (>500MB free on /)
disk_avail_kb=$(df / --output=avail | tail -1 | tr -d ' ')
if [ "$disk_avail_kb" -gt 512000 ] 2>/dev/null; then
    disk_mb=$((disk_avail_kb / 1024))
    check_fix "Disk space available (${disk_mb}MB free)" "OK"
else
    disk_mb=$((disk_avail_kb / 1024))
    check_fix "Disk space available (${disk_mb}MB free, need >500MB)" "MISSING"
fi

# B8. CPU temperature OK (<75C)
cpu_temp_raw=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo "0")
cpu_temp=$((cpu_temp_raw / 1000))
if [ "$cpu_temp" -lt 75 ] 2>/dev/null; then
    check_fix "CPU temperature OK (${cpu_temp}C)" "OK"
else
    check_fix "CPU temperature high (${cpu_temp}C, threshold 75C)" "MISSING"
fi
```

**Step 2: Verify syntax**

Run: `bash -n sync.sh`

---

## Part C: Documentation (3 tasks)

### Task 8: Update sync.sh header comment

**Files:**
- Modify: `sync.sh:8-16`

**Step 1: Add provision/verify to header usage block**

Add after the `--deploy-local` line:

```
#   ./sync.sh --provision        # Apply OS fixes + install/enable systemd services
#   ./sync.sh --verify           # Check fix/service status (read-only)
#   ./sync.sh --no-verify        # Skip automatic post-sync verification
```

---

### Task 9: Update CONFIGURATION_GUIDE.md

**Files:**
- Modify: `docs/CONFIGURATION_GUIDE.md`

**Step 1: Add provisioning section to Quick Command Reference**

At the Quick Command Reference section (around line 696-719), add a new subsection:

```markdown
### Provisioning & Verification

```bash
# Apply OS-level fixes and enable systemd services
./sync.sh --provision

# Provision all configured RPis
./sync.sh --all-profiles --provision

# Check status without making changes (runs automatically after every sync)
./sync.sh --verify

# Skip automatic verification
./sync.sh --no-verify

# Override role detection for first-time provisioning
./sync.sh --provision --role vehicle
```
```

---

### Task 10: Update sync.sh header and README.md deployment section

**Files:**
- Modify: `README.md` -- near line 327 where sync.sh is mentioned

**Step 1: Add provisioning mention to README deployment instructions**

After the existing `./sync.sh --deploy-cross` line (around line 327), add:

```bash
./sync.sh --provision           # First-time: apply OS fixes + enable services
```

---
