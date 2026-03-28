# Raspberry Pi Disconnection Fix - Instructions

## Problem Identified

Your Raspberry Pi has **3 additional power management issues** beyond the WiFi power saving you fixed yesterday:

1. **NetworkManager WiFi Power Save = 3** (enabled, overriding your `iw` command)
2. **USB Autosuspend = 2 seconds** (USB devices suspend, causing dropouts)
3. **All USB devices on "auto"** (can be suspended anytime)

## Fix Scripts Transferred

I've created and transferred 3 scripts to your RPi at `/tmp/`:

1. `fix_rpi_power_management.sh` - Main fix script (REQUIRED)
2. `fix_rpi_ssh_keepalive.sh` - SSH keepalive config (OPTIONAL but recommended)
3. `verify_rpi_power_management.sh` - Verification script

## How to Run

### Step 1: SSH into your Raspberry Pi

```bash
ssh ubuntu@192.168.137.253
```

### Step 2: Run the main fix script

```bash
cd /tmp
sudo bash fix_rpi_power_management.sh
```

**What this does:**
- ✅ Fixes NetworkManager WiFi power save (sets to 2 = disabled)
- ✅ Disables USB autosuspend globally
- ✅ Forces all USB devices to stay on
- ✅ Updates `/etc/rc.local` to persist across reboots
- ✅ Adds kernel parameter for USB autosuspend

**Expected output:** You'll see colorful status messages for each step (5 steps total)

### Step 3 (Optional): Configure SSH keepalives

```bash
sudo bash /tmp/fix_rpi_ssh_keepalive.sh
```

This helps keep SSH connections alive over potentially flaky networks.

### Step 4: Reboot

```bash
sudo reboot
```

### Step 5: Verify after reboot

Wait ~30 seconds, then reconnect and verify:

```bash
ssh ubuntu@192.168.137.253
cd /tmp
bash verify_rpi_power_management.sh
```

**Expected result:** All 7 checks should PASS (green ✓)

### Step 6: Stability test (Optional)

Test for 5 minutes:
```bash
ping -i 0.5 -c 600 1.1.1.1
```

Or test for 30 minutes in background:
```bash
nohup sh -c 'date; ping -i 1 -c 1800 1.1.1.1; date' > /tmp/ping_30min.log 2>&1 &
```

Check results later with:
```bash
cat /tmp/ping_30min.log
```

## Quick One-Liner (from your laptop)

If you want to run everything in one go from your laptop:

```bash
ssh -t ubuntu@192.168.137.253 'cd /tmp && sudo bash fix_rpi_power_management.sh && sudo bash fix_rpi_ssh_keepalive.sh && echo "Rebooting in 5 seconds..." && sleep 5 && sudo reboot'
```

Then after ~30 seconds:

```bash
ssh ubuntu@192.168.137.253 'bash /tmp/verify_rpi_power_management.sh'
```

## What Gets Changed

### Files Modified:
- `/etc/NetworkManager/conf.d/default-wifi-powersave-off.conf` (created or updated)
- `/boot/firmware/cmdline.txt` (kernel parameter added)
- `/etc/rc.local` (updated with power management commands)
- `/etc/ssh/sshd_config.d/keepalive.conf` (created, if you run optional script)

### Runtime Changes:
- WiFi power save: OFF
- USB autosuspend: DISABLED (-1)
- All USB devices: FORCED ON

### Backups Created:
- `/etc/NetworkManager/conf.d.bak.<timestamp>`
- `/boot/firmware/cmdline.txt.bak.<timestamp>`
- `/etc/rc.local.bak.<timestamp>`

## Troubleshooting

### If script fails with "permission denied"
Make sure you use `sudo`:
```bash
sudo bash /tmp/fix_rpi_power_management.sh
```

### If still getting disconnections after fix
1. Verify all checks pass:
   ```bash
   bash /tmp/verify_rpi_power_management.sh
   ```

2. Check for other issues:
   ```bash
   # Check WiFi signal strength
   iwconfig wlan0
   
   # Check system logs
   sudo journalctl -u NetworkManager --since "1 hour ago" | tail -50
   
   # Check for thermal throttling
   vcgencmd measure_temp
   ```

3. If on USB WiFi adapter, try a different USB port (preferably USB 2.0)

### If you need to undo changes
All original files are backed up with timestamps. To restore:
```bash
# Example (use actual timestamp from your backup):
sudo cp /etc/NetworkManager/conf.d.bak.2025-10-08-0645/* /etc/NetworkManager/conf.d/
sudo cp /boot/firmware/cmdline.txt.bak.2025-10-08-0645 /boot/firmware/cmdline.txt
sudo cp /etc/rc.local.bak.2025-10-08-0645 /etc/rc.local
```

## Summary

This fix addresses **all known power management issues** that cause RPi disconnections:
- ✅ WiFi power saving (yesterday's fix + NetworkManager override)
- ✅ USB autosuspend
- ✅ USB device power control
- ✅ SSH keepalives

After applying these fixes and rebooting, your RPi should stay connected reliably!

---

**Questions?** Let me know if you encounter any issues during the fix process.
