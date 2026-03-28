#!/bin/bash
# Configure SSH keepalive to prevent idle disconnections
# This is optional but recommended

set -e

echo "=========================================="
echo "SSH Keepalive Configuration"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo: sudo bash $0"
    exit 1
fi

# Desired SSH keepalive config
KEEPALIVE_CONF="/etc/ssh/sshd_config.d/keepalive.conf"
DESIRED_CONTENT="ClientAliveInterval 60
ClientAliveCountMax 3"

# Check if config already matches desired content
if [ -f "$KEEPALIVE_CONF" ] && echo "$DESIRED_CONTENT" | cmp -s "$KEEPALIVE_CONF" -; then
    echo "SSH keepalive already configured (skipped)"
    echo "  ClientAliveInterval 60"
    echo "  ClientAliveCountMax 3"
    echo ""
    echo "✓ SSH keepalive already correct — no changes needed"
    echo ""
else
    # Create SSH server keepalive config
    echo "$DESIRED_CONTENT" > "$KEEPALIVE_CONF"

    echo "Created: $KEEPALIVE_CONF"
    echo "  ClientAliveInterval 60"
    echo "  ClientAliveCountMax 3"

    # Reload SSH service only when config changed
    echo ""
    echo "Reloading SSH service..."
    systemctl reload ssh

    echo ""
    echo "✓ SSH keepalive configured successfully!"
    echo ""
    echo "This will keep SSH connections alive by:"
    echo "  - Sending keepalive every 60 seconds"
    echo "  - Closing connection after 3 missed keepalives (3 minutes)"
    echo ""
fi
