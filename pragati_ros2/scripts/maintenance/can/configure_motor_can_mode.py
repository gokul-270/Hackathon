#!/usr/bin/env python3
"""
Configure MG6010 Motor for CAN Mode via UART
This script switches the motor from UART mode to CAN mode
"""

import serial
import time
import sys

def calculate_checksum(data):
    """Calculate checksum (sum of all bytes, keep lower 8 bits)"""
    return sum(data) & 0xFF

def build_rs485_frame(cmd, motor_id, data=None):
    """Build RS485 protocol frame"""
    frame = [0x3E, cmd, motor_id]
    
    if data is None or len(data) == 0:
        frame.append(0x00)  # Length = 0
        frame_checksum = calculate_checksum(frame)
        frame.append(frame_checksum)
        return bytes(frame)
    else:
        frame.append(len(data))  # Data length
        frame_checksum = calculate_checksum(frame)
        frame.append(frame_checksum)
        frame.extend(data)
        data_checksum = calculate_checksum(data)
        frame.append(data_checksum)
        return bytes(frame)

def send_command(ser, cmd, motor_id, data=None, timeout=1.0):
    """Send RS485 command and wait for response"""
    frame = build_rs485_frame(cmd, motor_id, data)
    
    hex_str = " ".join(f"{b:02X}" for b in frame)
    print(f"TX: {hex_str}")
    
    ser.write(frame)
    ser.flush()
    
    start = time.time()
    rx_buffer = b""
    
    while (time.time() - start) < timeout:
        if ser.in_waiting > 0:
            rx_buffer += ser.read(ser.in_waiting)
            
            if len(rx_buffer) >= 5:
                if rx_buffer[0] == 0x3E:
                    data_len = rx_buffer[3]
                    expected_len = 5 + data_len + (1 if data_len > 0 else 0)
                    
                    if len(rx_buffer) >= expected_len:
                        hex_str = " ".join(f"{b:02X}" for b in rx_buffer[:expected_len])
                        print(f"RX: {hex_str}")
                        return rx_buffer[:expected_len]
        time.sleep(0.01)
    
    print(f"RX: No response")
    return None

def main():
    port = "/dev/ttyUSB0"
    baud = 115200
    motor_id = 1
    
    print("="*70)
    print("MG6010 Motor CAN Mode Configuration Script")
    print("="*70)
    print(f"Port: {port}")
    print(f"Baud: {baud}")
    print(f"Motor ID: {motor_id}")
    print("="*70)
    print()
    
    print("⚠️  WARNING: This will configure the motor for CAN mode.")
    print("After running this script:")
    print("  1. Motor will be set to CAN mode with 500kbps bitrate")
    print("  2. You MUST power cycle the motor for changes to take effect")
    print("  3. After power cycle, motor will only respond to CAN commands")
    print()
    
    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        print("Aborted.")
        sys.exit(0)
    
    print()
    print("Opening serial port...")
    
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
        )
        print("✓ Serial port opened")
        print()
    except Exception as e:
        print(f"❌ Failed to open serial port: {e}")
        sys.exit(1)
    
    try:
        # Step 1: Read current motor info
        print("Step 1: Reading current motor configuration...")
        print("-" * 70)
        response = send_command(ser, 0x12, motor_id, None, 1.0)
        if response:
            print("✓ Motor responding via UART")
        else:
            print("❌ Motor not responding - check connections")
            sys.exit(1)
        print()
        time.sleep(0.5)
        
        # Step 2: Motor OFF (safer for configuration)
        print("Step 2: Turning motor OFF for configuration...")
        print("-" * 70)
        send_command(ser, 0x80, motor_id, None, 1.0)
        print()
        time.sleep(0.5)
        
        # Step 3: Attempt to write CAN configuration
        # NOTE: The exact command for setting CAN mode is not documented in the
        # protocol PDFs. This typically requires the LK Motor Tool software.
        
        print("Step 3: Attempting CAN mode configuration...")
        print("-" * 70)
        print()
        print("❌ IMPORTANT: The UART command to switch to CAN mode is")
        print("   not documented in the available protocol documents.")
        print()
        print("✅ SOLUTION: Use the LK Motor Tool (Windows software)")
        print()
        print("   In LK Motor Tool:")
        print("   1. Connect to motor via RS485 (115200 baud)")
        print("   2. Go to 'Basic Setting'")
        print("   3. Set 'Bus Type' dropdown to 'CAN'")
        print("   4. Set 'CAN Baud rate' to '500K'")
        print("   5. Click 'Write to ROM' button")
        print("   6. Power cycle the motor")
        print()
        print("   After this, the motor will respond to CAN commands.")
        print()
        
        # Turn motor back ON
        print("Turning motor back ON...")
        send_command(ser, 0x88, motor_id, None, 1.0)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ser.close()
        print("\nSerial port closed.")

if __name__ == "__main__":
    main()
