#!/usr/bin/env python3
"""
MG6010 UART Communication Test
Run this directly on the Raspberry Pi to test motor UART connection
"""

import serial
import time
import sys

def test_uart(port='/dev/ttyUSB0', baudrate=115200):
    """Test UART communication with MG6010 motor"""
    
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║          MG6010 UART Communication Test                       ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print()
    
    print(f"Testing {port} at {baudrate} bps...")
    
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0
        )
        
        print(f"✓ Opened {port} successfully")
        print()
        
        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        # Listen for any spontaneous data
        print("Listening for spontaneous data (5 seconds)...")
        time.sleep(5)
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            print(f"  ✓ Received spontaneous data: {data.hex()}")
        else:
            print("  ✗ No spontaneous data")
        print()
        
        # Try different command formats
        print("Testing command formats...")
        print("─────────────────────────────────────────────────────────────")
        
        test_commands = [
            # Format 1: Custom protocol (3E header)
            (b'\x3E\x01\x9A\x00\x9B', "Custom protocol - Read status"),
            
            # Format 2: Simple hex command
            (b'\x9A\x00', "Simple status query"),
            
            # Format 3: Modbus RTU-like
            (b'\x01\x03\x00\x00\x00\x01\x84\x0A', "Modbus-like query"),
            
            # Format 4: ASCII command
            (b'READ_STATUS\r\n', "ASCII command"),
        ]
        
        for i, (cmd, desc) in enumerate(test_commands, 1):
            print(f"\n{i}. {desc}")
            print(f"   Command: {cmd.hex()}")
            
            ser.reset_input_buffer()
            ser.write(cmd)
            time.sleep(0.2)
            
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting)
                print(f"   ✓ Response ({len(response)} bytes): {response.hex()}")
                print("   ✓✓✓ UART COMMUNICATION WORKING! ✓✓✓")
                ser.close()
                return True
            else:
                print(f"   ✗ No response")
        
        ser.close()
        return False
        
    except serial.SerialException as e:
        print(f"✗ Serial port error: {e}")
        print("\nTroubleshooting:")
        print("  1. Check if /dev/ttyUSB0 exists: ls -la /dev/ttyUSB*")
        print("  2. Add user to dialout group: sudo usermod -a -G dialout $USER")
        print("  3. Check UART wiring (TX/RX)")
        print("  4. Verify motor power (48V)")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_all_baud_rates(port='/dev/ttyUSB0'):
    """Test UART at multiple baud rates"""
    
    baud_rates = [9600, 19200, 38400, 57600, 115200]
    
    print("\nTesting multiple baud rates...")
    print("═══════════════════════════════════════════════════════════════")
    
    for baud in baud_rates:
        print(f"\n--- Testing {baud} bps ---")
        if test_uart(port, baud):
            print(f"\n✓✓✓ SUCCESS AT {baud} BPS! ✓✓✓")
            return True
        time.sleep(0.5)
    
    return False

if __name__ == "__main__":
    print("\nMG6010 Motor UART Test")
    print("Make sure:")
    print("  1. Motor is connected via USB-UART adapter")
    print("  2. Motor has 48V power")
    print("  3. TX/RX are connected correctly")
    print("\nPress Enter to start...")
    input()
    
    if not test_all_baud_rates():
        print("\n═══════════════════════════════════════════════════════════════")
        print("NO UART RESPONSE FROM MOTOR")
        print("═══════════════════════════════════════════════════════════════")
        print("\nPossible issues:")
        print("  1. TX and RX wires might be swapped")
        print("  2. Motor baud rate different than tested")
        print("  3. Motor might be in CAN-only mode")
        print("  4. Motor needs 48V power to respond")
        print("  5. UART adapter voltage level mismatch (3.3V vs 5V)")
        print("\nWhat worked in Windows app:")
        print("  - Check the baud rate used in Windows app")
        print("  - Note any special initialization sequence")
        print("  - Check if motor sends data continuously or on request")
    else:
        print("\n═══════════════════════════════════════════════════════════════")
        print("NEXT STEPS:")
        print("═══════════════════════════════════════════════════════════════")
        print("\n1. We can now send commands to enable CAN mode")
        print("2. Configure Node ID (1, 2, or 3)")
        print("3. Set CAN bitrate to 250kbps")
        print("4. Save to EEPROM and reboot motor")
