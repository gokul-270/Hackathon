#!/bin/bash
################################################################################
# RPi SSH Wrapper - Uses Windows SSH to reach RPi on hotspot network
# Usage: ssh-rpi [command]
################################################################################

WINSSH="/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe"
RPI_USER="ubuntu"
RPI_IP="192.168.137.238"

if [ $# -eq 0 ]; then
    # Interactive shell
    "$WINSSH" "${RPI_USER}@${RPI_IP}"
else
    # Run command
    "$WINSSH" "${RPI_USER}@${RPI_IP}" "$@"
fi
