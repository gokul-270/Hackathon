# WSL2 Networking Setup for RPi Access

## Problem

By default, WSL2 uses NAT networking (172.x.x.x virtual network) which cannot reach devices on Windows hotspot (192.168.137.x).

## Solution: Mirrored Networking Mode

Windows 11 (Build 22H2+) supports mirrored networking mode, which gives WSL direct access to the physical network.

## Prerequisites

- Windows 11 22H2 or later (Build 22621+)
- WSL2 (not WSL1)
- Raspberry Pi on Windows Mobile Hotspot (192.168.137.x)

## Setup Steps

### 1. Create WSL Configuration File

From **Windows PowerShell** (not WSL):

```powershell
# Create .wslconfig
$wslConfig = @"
[wsl2]
networkingMode=mirrored
dnsTunneling=true
localhostForwarding=true
firewall=true
"@

$wslConfig | Out-File -FilePath "$env:USERPROFILE\.wslconfig" -Encoding ASCII

# Verify file was created
Get-Content "$env:USERPROFILE\.wslconfig"
```

### 2. Restart WSL

```powershell
# Shutdown WSL completely
wsl --shutdown

# Wait 10 seconds, then reopen WSL terminal
```

### 3. Verify Mirrored Mode

From **WSL terminal**:

```bash
# Check IP address (should be on physical network now)
ip addr show eth2 | grep "inet "
# Should show 192.168.1.x or similar (not 172.x.x.x)

# Test RPi connectivity
ping -c 3 192.168.137.238
```

## RPi on Windows Hotspot

The Raspberry Pi is connected via Windows Mobile Hotspot:
- **Hotspot network:** 192.168.137.0/24
- **Windows IP on hotspot:** 192.168.137.1
- **RPi IP:** 192.168.137.238

### WSL → Windows → RPi Bridge

Even with mirrored networking, WSL might not directly access the hotspot network. We use Windows SSH as a bridge:

```bash
# Load RPi bridge helpers
source ~/pragati_ros2/scripts/rpi-wsl-bridge.sh

# Create SSH/SCP wrappers that route through Windows
create_rpi_ssh_wrappers

# Now standard SSH commands work
ssh ubuntu@192.168.137.238 "hostname"
```

## How It Works

1. **Mirrored networking** gives WSL access to the main network (192.168.1.x)
2. **Windows SSH bridge** uses Windows OpenSSH (`/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe`) to reach the hotspot
3. **Wrapper scripts** automatically detect RPi connections and route through Windows

## Configuration File Details

### ~/.ssh/config (WSL)

```bash
# Simple config (doesn't use proxy)
Host rpi
    HostName 192.168.137.238
    User ubuntu
```

### rpi-wsl-bridge.sh

The bridge script creates temporary wrappers in `/tmp/rpi-bin` that:
- Check if destination is RPi (192.168.137.238)
- Route through Windows SSH if yes
- Use native Linux SSH otherwise

## Verification

### Check Mirrored Mode Active

```bash
# WSL should have IP on physical network
ip addr show | grep "inet 192"

# Should NOT show 172.x.x.x on eth0
ip addr show eth0
```

### Test Windows SSH

From PowerShell:
```powershell
# Should work without password (after ssh-copy-id)
ssh ubuntu@192.168.137.238 "hostname"
```

### Test WSL → RPi

From WSL:
```bash
# Load bridge
source scripts/rpi-wsl-bridge.sh
create_rpi_ssh_wrappers

# Test
ssh ubuntu@192.168.137.238 "hostname"
# Should print: ubuntu-desktop
```

## Troubleshooting

### WSL Still on 172.x.x.x

**Cause:** .wslconfig not applied or WSL not restarted
**Fix:**
```powershell
# Verify file exists
Get-Content "$env:USERPROFILE\.wslconfig"

# Hard restart
wsl --shutdown
# Wait 10 seconds
wsl
```

### Cannot SSH to RPi from Windows

**Cause:** SSH keys not set up
**Fix:**
```powershell
# Generate key (if needed)
ssh-keygen -t ed25519

# Copy to RPi
type "$env:USERPROFILE\.ssh\id_ed25519.pub" | ssh ubuntu@192.168.137.238 "cat >> ~/.ssh/authorized_keys"
```

### WSL SSH Hangs

**Cause:** Bridge not loaded
**Fix:**
```bash
source ~/pragati_ros2/scripts/rpi-wsl-bridge.sh
create_rpi_ssh_wrappers
export PATH="/tmp/rpi-bin:$PATH"
```

### "localhostForwarding has no effect" Warning

**This is normal!** The warning just means `localhostForwarding` is redundant with mirrored mode. It doesn't affect functionality.

## Alternative: Connect RPi to Main Network

Instead of hotspot, connect RPi to the same WiFi as your PC (192.168.1.x):

1. On RPi: `sudo nmtui` → Connect to WiFi
2. Note new IP address
3. Update `sync.sh` and scripts with new IP
4. No bridge needed - WSL can reach directly

## Automation

Add to ~/.bashrc (WSL):
```bash
# Auto-load RPi bridge for Pragati project
if [ -f "$HOME/pragati_ros2/scripts/rpi-wsl-bridge.sh" ]; then
    source "$HOME/pragati_ros2/scripts/rpi-wsl-bridge.sh"
    create_rpi_ssh_wrappers &>/dev/null
fi
```

## References

- [WSL Networking Documentation](https://learn.microsoft.com/en-us/windows/wsl/networking)
- [Mirrored Mode Announcement](https://devblogs.microsoft.com/commandline/windows-subsystem-for-linux-september-2023-update/)
