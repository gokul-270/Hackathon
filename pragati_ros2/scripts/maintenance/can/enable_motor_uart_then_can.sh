#!/bin/bash
# Test: Enable motor via UART, then try CAN commands
# Theory: Motor might need UART "wake up" before CAN works

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║     Enable Motor via UART, then Test CAN                      ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

UART_PORT="/dev/ttyUSB0"
CAN_IF="can0"

# Setup CAN
sudo ip link set $CAN_IF down 2>/dev/null
sudo ip link set $CAN_IF type can bitrate 500000
sudo ip link set $CAN_IF up

echo "Step 1: Send Motor ON command via UART"
echo "─────────────────────────────────────────────────────────────"
# Frame: 3E 88 01 00 (checksum)
# 0x3E = header
# 0x88 = Motor ON
# 0x01 = Motor ID 1
# 0x00 = no data
# Checksum = (0x3E + 0x88 + 0x01 + 0x00) & 0xFF = 0xC7

python3 << 'PYTHON_EOF'
import serial
import time

try:
    ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    
    # Motor ON command
    frame = bytes([0x3E, 0x88, 0x01, 0x00, 0xC7])
    print(f"TX (UART): {' '.join(f'{b:02X}' for b in frame)}")
    ser.write(frame)
    time.sleep(0.2)
    
    if ser.in_waiting > 0:
        response = ser.read(ser.in_waiting)
        print(f"RX (UART): {' '.join(f'{b:02X}' for b in response)}")
        print("✓ Motor responded via UART")
    else:
        print("✗ No UART response")
    
    ser.close()
except Exception as e:
    print(f"UART error: {e}")
PYTHON_EOF

echo ""
echo "Step 2: Now try CAN commands"
echo "─────────────────────────────────────────────────────────────"

# Start CAN monitoring
candump can0 > /tmp/uart_can_test.log 2>&1 &
DUMP_PID=$!
sleep 0.5

# Send Motor ON via CAN
echo "Sending Motor ON via CAN (0x88)..."
cansend can0 141#8800000000000000
sleep 0.5

# Send position read via CAN
echo "Reading position via CAN (0x92)..."
cansend can0 141#9200000000000000
sleep 0.5

# Send position command
echo "Sending position command via CAN (move 100 units)..."
cansend can0 141#A46400000064FFFF
sleep 2

# Read position again
cansend can0 141#9200000000000000
sleep 0.5

kill $DUMP_PID 2>/dev/null

echo ""
echo "CAN traffic:"
cat /tmp/uart_can_test.log

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Analysis:"
echo "═══════════════════════════════════════════════════════════════"

# Check for non-zero responses
NON_ZERO=$(grep "141" /tmp/uart_can_test.log | grep -v "00 00 00 00 00 00 00" | wc -l)

if [ "$NON_ZERO" -gt "0" ]; then
    echo "✓ Got non-zero CAN responses after UART enable!"
    echo ""
    grep "141" /tmp/uart_can_test.log | grep -v "00 00 00 00 00 00 00"
else
    echo "✗ Still getting all zeros from CAN"
    echo ""
    echo "This means UART and CAN are separate - motor needs explicit"
    echo "configuration to switch from UART mode to CAN mode."
fi

echo ""
echo "Did you see/hear the motor shaft move? (y/n)"
