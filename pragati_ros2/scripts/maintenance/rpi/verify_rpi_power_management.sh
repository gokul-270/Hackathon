#!/bin/bash
# Verify all power management settings are correctly configured

echo "=========================================="
echo "Raspberry Pi Power Management Verification"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

echo "[1] WiFi Power Save Status:"
WIFI_PS=$(iw dev wlan0 get power_save 2>/dev/null | grep -o 'on\|off' || echo "unknown")
echo "    Current: $WIFI_PS"
if [ "$WIFI_PS" = "off" ]; then
    echo -e "    ${GREEN}✓ PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "    ${RED}✗ FAIL - Should be 'off'${NC}"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "[2] NetworkManager WiFi Power Save Config:"
NM_CONFIG=$(grep -r 'wifi.powersave' /etc/NetworkManager/conf.d/ 2>/dev/null | grep -o 'wifi.powersave *= *[0-9]' | head -1 || echo "not found")
echo "    Config: $NM_CONFIG"
if echo "$NM_CONFIG" | grep -q 'wifi.powersave *= *2'; then
    echo -e "    ${GREEN}✓ PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "    ${RED}✗ FAIL - Should be 'wifi.powersave = 2'${NC}"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "[3] USB Autosuspend:"
USB_AUTO=$(cat /sys/module/usbcore/parameters/autosuspend 2>/dev/null || echo "unknown")
echo "    Current: $USB_AUTO"
if [ "$USB_AUTO" = "-1" ]; then
    echo -e "    ${GREEN}✓ PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "    ${RED}✗ FAIL - Should be '-1'${NC}"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "[4] USB Device Power Control:"
USB_ON=0
USB_AUTO_COUNT=0
for control_file in /sys/bus/usb/devices/*/power/control; do
    if [ -r "$control_file" ]; then
        state=$(cat "$control_file" 2>/dev/null)
        if [ "$state" = "on" ]; then
            USB_ON=$((USB_ON + 1))
        elif [ "$state" = "auto" ]; then
            USB_AUTO_COUNT=$((USB_AUTO_COUNT + 1))
        fi
    fi
done
echo "    Devices 'on': $USB_ON"
echo "    Devices 'auto': $USB_AUTO_COUNT"
if [ $USB_AUTO_COUNT -eq 0 ] && [ $USB_ON -gt 0 ]; then
    echo -e "    ${GREEN}✓ PASS${NC}"
    PASS=$((PASS + 1))
else
    echo -e "    ${YELLOW}⚠ WARNING - Some devices still on 'auto'${NC}"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "[5] Kernel Parameter (cmdline.txt):"
if [ -f /boot/firmware/cmdline.txt ]; then
    if grep -q 'usbcore.autosuspend=-1' /boot/firmware/cmdline.txt; then
        echo "    Kernel parameter: usbcore.autosuspend=-1"
        echo -e "    ${GREEN}✓ PASS${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "    ${RED}✗ FAIL - Parameter not found in cmdline.txt${NC}"
        FAIL=$((FAIL + 1))
    fi
else
    echo -e "    ${RED}✗ FAIL - /boot/firmware/cmdline.txt not found${NC}"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "[6] rc.local Configuration:"
if [ -f /etc/rc.local ] && [ -x /etc/rc.local ]; then
    if grep -q 'iw dev wlan0 set power_save off' /etc/rc.local && \
       grep -q 'sys/bus/usb/devices' /etc/rc.local; then
        echo "    rc.local exists and configured"
        echo -e "    ${GREEN}✓ PASS${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "    ${YELLOW}⚠ WARNING - rc.local exists but incomplete${NC}"
        FAIL=$((FAIL + 1))
    fi
else
    echo -e "    ${RED}✗ FAIL - rc.local not found or not executable${NC}"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "[7] Network Connectivity Test (ping gateway):"
GATEWAY=$(ip route | grep default | awk '{print $3}' | head -1)
if [ -n "$GATEWAY" ]; then
    if ping -c 3 -W 2 "$GATEWAY" >/dev/null 2>&1; then
        echo "    Gateway ($GATEWAY): reachable"
        echo -e "    ${GREEN}✓ PASS${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "    ${RED}✗ FAIL - Cannot ping gateway${NC}"
        FAIL=$((FAIL + 1))
    fi
else
    echo -e "    ${YELLOW}⚠ WARNING - No default gateway found${NC}"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "=========================================="
echo "Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "=========================================="
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All checks passed! Power management is correctly configured.${NC}"
    exit 0
else
    echo -e "${YELLOW}Some checks failed. Review the output above.${NC}"
    exit 1
fi
