# RPi Process Optimization Guide

Audit date: 2026-03-10
Target: Vehicle RPi @ 192.168.137.203 (Ubuntu 24.04 Desktop on RPi 4B)

## Root Cause

The RPi image is Ubuntu 24.04 **Desktop** (not Server), so it runs a full GNOME desktop
stack, audio subsystem, and various desktop services that are completely unnecessary for a
headless robot controller.

## Current Status

| Service | Action Taken | Date |
|---------|-------------|------|
| PipeWire + WirePlumber + PulseAudio | Killed + globally masked | 2026-03-10 |
| rtkit-daemon | Stopped + disabled | 2026-03-10 |

## Process Inventory

### ESSENTIAL -- Never Kill

| Process | Service | CPU% | Purpose |
|---------|---------|------|---------|
| vehicle_control_node | vehicle_launch.service | ~5% | Core vehicle ROS2 control node |
| mg6010_controller_node | vehicle_launch.service | ~3.5% | Motor control via CAN bus |
| can_watchdog | can-watchdog@can0.service | ~0.6% | CAN bus auto-recovery |
| pigpiod | pigpiod.service | ~7% | GPIO daemon for hardware I/O |
| mosquitto | mosquitto.service | ~0% | MQTT broker for arm-vehicle comms |
| sshd | ssh.service | - | Remote access |
| NetworkManager | NetworkManager.service | - | Network connectivity |
| systemd-journald | systemd-journald.service | ~1.7% | System logging |
| systemd-resolved | systemd-resolved.service | - | DNS resolution |

### USEFUL -- Kill Only If Desperate

| Process | Service | CPU% | Purpose | Recovery |
|---------|---------|------|---------|----------|
| dashboard_server (uvicorn) | pragati-dashboard.service | ~4% | Web monitoring UI | `sudo systemctl start pragati-dashboard` |
| rpi_agent | pragati-agent.service | ~0.5% | Remote management agent | `sudo systemctl start pragati-agent` |
| field-monitor | field-monitor.service | ~0% | Field trial log collection | `sudo systemctl start field-monitor` |
| ros2-daemon | (user process) | ~0.6% | ROS2 CLI discovery cache | `ros2 daemon start` |

### JUNK -- Safe to Kill and Disable

These are desktop services that serve no purpose on a headless robot.

| Process | Service | CPU% | Purpose | How to Disable |
|---------|---------|------|---------|---------------|
| **GDM** | gdm.service | ~0.4% | GNOME login screen | See "Switch to multi-user" below |
| **gnome-shell** | (spawned by GDM) | ~0.4% (4.5% MEM!) | Desktop compositor | Killed with GDM |
| **PipeWire** | pipewire.service (user) | ~3% | Audio server | **DONE** - globally masked |
| **WirePlumber** | wireplumber.service (user) | ~3% | Audio session manager | **DONE** - globally masked |
| **PipeWire-Pulse** | pipewire-pulse.service (user) | ~2% | PulseAudio compat | **DONE** - globally masked |
| **filter-chain** | filter-chain.service (user) | ~0.5% | Audio filter pipeline | **DONE** - globally masked |
| **rtkit-daemon** | rtkit-daemon.service | ~0% | Realtime scheduling for audio | **DONE** - disabled |
| **snapd-desktop-integration** | snap service | spikes to 50%+ | Snap desktop glue | `sudo snap remove snapd-desktop-integration` |
| **colord** | colord.service | ~0% | Color profile management | `sudo systemctl disable colord` |
| **gnome-remote-desktop** | gnome-remote-desktop.service | ~0% | GNOME remote desktop | `sudo systemctl disable gnome-remote-desktop` |
| **fwupd** | fwupd.service | ~0% | Firmware update daemon | `sudo systemctl disable fwupd` |
| **udisks2** | udisks2.service | ~0% | Disk management GUI backend | `sudo systemctl disable udisks2` |
| **upower** | upower.service | ~0% | Power management for desktop | `sudo systemctl disable upower` |
| **power-profiles-daemon** | power-profiles-daemon.service | ~0% | Desktop power profiles | `sudo systemctl disable power-profiles-daemon` |
| **accounts-daemon** | accounts-daemon.service | ~0% | Desktop user account mgmt | `sudo systemctl disable accounts-daemon` |
| **lttng-sessiond** | lttng-sessiond.service | ~0% | Tracing framework (unused) | `sudo systemctl disable lttng-sessiond` |
| **kerneloops** | kerneloops.service | ~0% | Kernel crash reporter | `sudo systemctl disable kerneloops` |
| **xdg-document-portal** | (user process) | spikes | Desktop file portal | Killed with desktop |

## Recommended Actions (Future)

### Option A: Switch to multi-user.target (Recommended)

This disables the entire GNOME desktop stack in one command. Estimated CPU savings: ~15-20%.

```bash
# Switch default boot target from graphical to multi-user (CLI only)
sudo systemctl set-default multi-user.target

# To apply immediately without rebooting:
sudo systemctl isolate multi-user.target

# To revert later:
sudo systemctl set-default graphical.target
```

**Impact:** No desktop, no GDM, no gnome-shell, no audio, no desktop portals.
SSH and all Pragati services continue working normally.

### Option B: Disable Individual Services

If you want to keep the desktop but trim fat:

```bash
# Disable desktop junk one by one
sudo systemctl disable --now colord gnome-remote-desktop fwupd udisks2 upower \
  power-profiles-daemon accounts-daemon lttng-sessiond kerneloops

# Remove snapd desktop integration
sudo snap remove snapd-desktop-integration
```

### Option C: Reinstall with Ubuntu Server

The most thorough solution. Ubuntu Server 24.04 ARM64 doesn't include any desktop
packages. This would require reprovisioning the RPi using `setup_raspberry_pi.sh`.

## Reverting Audio Masking

If audio is ever needed (unlikely):

```bash
sudo systemctl --global unmask pipewire.service pipewire-pulse.service \
  wireplumber.service filter-chain.service pipewire.socket pipewire-pulse.socket
sudo systemctl enable rtkit-daemon.service
# Then reboot or: systemctl --user start pipewire wireplumber pipewire-pulse
```
