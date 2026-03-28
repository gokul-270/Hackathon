#!/bin/bash
################################################################################
# RPi Communication Wrappers for WSL
# Purpose: Bridge WSL to RPi via Windows SSH (RPi is on Windows hotspot network)
#
# Usage:
#   source ~/pragati_ros2/scripts/rpi-wsl-bridge.sh
#   rpi-ssh hostname
#   rpi-scp local-file ubuntu@192.168.137.238:~/remote-path
################################################################################

# Windows SSH and SCP paths
WINSSH="/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe"
WINSCP="/mnt/c/WINDOWS/System32/OpenSSH/scp.exe"
RPI_USER="ubuntu"
RPI_IP="192.168.137.238"

# SSH wrapper function
rpi-ssh() {
    if [ $# -eq 0 ]; then
        "$WINSSH" "${RPI_USER}@${RPI_IP}"
    else
        "$WINSSH" "${RPI_USER}@${RPI_IP}" "$@"
    fi
}

# SCP wrapper function
rpi-scp() {
    "$WINSCP" "$@"
}

# Create temporary ssh/scp scripts in PATH
create_rpi_ssh_wrappers() {
    local BIN_DIR="/tmp/rpi-bin"
    mkdir -p "$BIN_DIR"

    # Create ssh wrapper
    cat > "$BIN_DIR/ssh" << 'EOF'
#!/bin/bash
# Check if connecting to RPi
if [[ "$*" == *"192.168.137.238"* ]] || [[ "$*" == *"ubuntu@"* ]]; then
    /mnt/c/WINDOWS/System32/OpenSSH/ssh.exe "$@"
else
    /usr/bin/ssh "$@"
fi
EOF
    chmod +x "$BIN_DIR/ssh"

    # Create scp wrapper
    cat > "$BIN_DIR/scp" << 'EOF'
#!/bin/bash
# Check if copying to/from RPi
if [[ "$*" == *"192.168.137.238"* ]] || [[ "$*" == *"ubuntu@"* ]]; then
    /mnt/c/WINDOWS/System32/OpenSSH/scp.exe "$@"
else
    /usr/bin/scp "$@"
fi
EOF
    chmod +x "$BIN_DIR/scp"

    # Add to PATH (prepend so it takes priority)
    export PATH="$BIN_DIR:$PATH"

    echo "✅ RPi SSH/SCP wrappers activated (via Windows SSH)"
}

# Show usage
rpi-bridge-help() {
    cat << 'HELP'
RPi WSL Bridge Helper Functions:

  rpi-ssh [command]         - SSH to RPi via Windows
  rpi-scp <src> <dst>       - SCP to/from RPi via Windows
  create_rpi_ssh_wrappers   - Auto-redirect ssh/scp for RPi connections

Examples:
  rpi-ssh hostname
  rpi-ssh "ls -la ~/pragati_ros2"
  rpi-scp myfile ubuntu@192.168.137.238:~/

  # For sync.sh and other scripts:
  create_rpi_ssh_wrappers   # Run once per terminal session
  ./sync.sh --ip 192.168.137.238 --deploy-cross
HELP
}

# Auto-activate on source (commented out by default)
# create_rpi_ssh_wrappers

echo "RPi WSL Bridge loaded. Run 'rpi-bridge-help' for usage."
