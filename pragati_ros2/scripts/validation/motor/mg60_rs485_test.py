#!/usr/bin/env python3
"""
MG60 Motor RS485 Protocol Test Script
Uses RS485 protocol over UART (not CAN protocol)
Baud rate: 115200
"""

import argparse
import sys
import time

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Install with: pip3 install pyserial")
    sys.exit(1)


def calculate_checksum(data):
    """Calculate checksum (sum of all bytes, keep lower 8 bits)"""
    return sum(data) & 0xFF


def build_rs485_frame(cmd, motor_id, data=None):
    """
    Build RS485 protocol frame
    Format: [0x3E][CMD][ID][LEN][CHECKSUM][DATA...][DATA_CHECKSUM]
    """
    frame = [0x3E, cmd, motor_id]
    
    if data is None or len(data) == 0:
        # No data
        frame.append(0x00)  # Length = 0
        frame_checksum = calculate_checksum(frame)
        frame.append(frame_checksum)
        return bytes(frame)
    else:
        # With data
        frame.append(len(data))  # Data length
        frame_checksum = calculate_checksum(frame)
        frame.append(frame_checksum)
        frame.extend(data)
        data_checksum = calculate_checksum(data)
        frame.append(data_checksum)
        return bytes(frame)


def parse_rs485_response(data):
    """Parse RS485 response frame"""
    if len(data) < 5:
        return None
    
    if data[0] != 0x3E:
        return None
    
    cmd = data[1]
    motor_id = data[2]
    data_len = data[3]
    frame_checksum = data[4]
    
    # Verify frame checksum
    calculated_checksum = calculate_checksum(data[0:4])
    if calculated_checksum != frame_checksum:
        return {"error": "Frame checksum mismatch"}
    
    response = {
        "cmd": cmd,
        "motor_id": motor_id,
        "data_len": data_len,
        "frame_checksum": frame_checksum,
    }
    
    if data_len > 0 and len(data) >= 5 + data_len + 1:
        response["data"] = data[5:5+data_len]
        response["data_checksum"] = data[5+data_len]
        
        # Verify data checksum
        calculated_data_checksum = calculate_checksum(response["data"])
        if calculated_data_checksum != response["data_checksum"]:
            response["error"] = "Data checksum mismatch"
    
    return response


def send_command(ser, cmd, motor_id, data=None, timeout=0.5):
    """Send RS485 command and wait for response"""
    frame = build_rs485_frame(cmd, motor_id, data)
    
    # Display TX
    hex_str = " ".join(f"{b:02X}" for b in frame)
    print(f"\nTX: {hex_str}")
    print(f"    Frame: [HEAD=0x3E] [CMD=0x{cmd:02X}] [ID={motor_id}] [LEN={len(data) if data else 0}]")
    
    # Send
    ser.write(frame)
    ser.flush()
    
    # Wait for response
    start = time.time()
    rx_buffer = b""
    
    while (time.time() - start) < timeout:
        if ser.in_waiting > 0:
            rx_buffer += ser.read(ser.in_waiting)
            
            # Check if we have a complete frame
            if len(rx_buffer) >= 5:
                if rx_buffer[0] == 0x3E:
                    data_len = rx_buffer[3]
                    expected_len = 5 + data_len + (1 if data_len > 0 else 0)
                    
                    if len(rx_buffer) >= expected_len:
                        # We have a complete frame
                        hex_str = " ".join(f"{b:02X}" for b in rx_buffer[:expected_len])
                        print(f"RX: {hex_str}")
                        
                        parsed = parse_rs485_response(rx_buffer[:expected_len])
                        if parsed:
                            print(f"    Response: CMD=0x{parsed['cmd']:02X} ID={parsed['motor_id']}")
                            if "data" in parsed:
                                data_hex = " ".join(f"{b:02X}" for b in parsed["data"])
                                print(f"    Data: [{data_hex}]")
                            if "error" in parsed:
                                print(f"    ⚠️  {parsed['error']}")
                            else:
                                print(f"    ✓ Checksums valid")
                            return parsed
                        return None
        time.sleep(0.01)
    
    print(f"RX: ❌ No response within {timeout:.2f}s")
    return None


def main():
    parser = argparse.ArgumentParser(
        description="MG60 Motor RS485 Protocol Test via UART",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic test
  python3 mg60_rs485_test.py
  
  # Test with different motor ID
  python3 mg60_rs485_test.py --motor-id 2
  
Note: Motor must be connected via UART/RS485 port (not CAN port)
      UART baud rate: 115200
        """
    )
    
    parser.add_argument("--port", default="/dev/ttyUSB0",
                        help="Serial port (default: /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200,
                        help="UART baud rate (default: 115200)")
    parser.add_argument("--motor-id", type=int, default=1,
                        help="Motor ID 1-32 (default: 1)")
    parser.add_argument("--timeout", type=float, default=0.5,
                        help="Response timeout in seconds (default: 0.5)")
    
    args = parser.parse_args()
    
    if args.motor_id < 1 or args.motor_id > 32:
        print("ERROR: motor-id must be between 1 and 32", file=sys.stderr)
        sys.exit(1)
    
    print("="*70)
    print("MG60 Motor RS485 Protocol Test")
    print("="*70)
    print(f"Serial Port:  {args.port}")
    print(f"Baud Rate:    {args.baud}")
    print(f"Motor ID:     {args.motor_id}")
    print(f"Timeout:      {args.timeout}s")
    print("="*70)
    
    # Open serial port
    print(f"\nOpening {args.port} @ {args.baud} baud...")
    try:
        ser = serial.Serial(
            port=args.port,
            baudrate=args.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
        )
        print("✓ Serial port opened successfully")
    except Exception as e:
        print(f"❌ Failed to open serial port: {e}", file=sys.stderr)
        sys.exit(2)
    
    success_count = 0
    total_tests = 0
    
    try:
        print("\n" + "="*70)
        print("Starting Motor Communication Tests")
        print("="*70)
        
        # Test commands (RS485 protocol)
        commands = [
            ("Read driver and motor type (0x12)", 0x12, None),
            ("Read motor status 1 (0x9A)", 0x9A, None),
            ("Motor OFF (0x80)", 0x80, None),
            ("Motor STOP (0x81)", 0x81, None),
            ("Motor ON (0x88)", 0x88, None),
            ("Read motor status 1 again (0x9A)", 0x9A, None),
            ("Read multi-turn angle (0x92)", 0x92, None),
            ("Read single-turn angle (0x94)", 0x94, None),
            ("Read encoder (0x90)", 0x90, None),
        ]
        
        for title, cmd, data in commands:
            print(f"\n{'='*70}")
            print(f"=== {title} ===")
            print(f"{'='*70}")
            
            response = send_command(ser, cmd, args.motor_id, data, args.timeout)
            total_tests += 1
            
            if response and "error" not in response:
                success_count += 1
                print("✓ Success")
            else:
                print("❌ Failed")
            
            time.sleep(0.2)  # Small delay between commands
        
        # Summary
        print("\n" + "="*70)
        print("Test Summary")
        print("="*70)
        print(f"Tests Passed: {success_count}/{total_tests}")
        
        if success_count == 0:
            print("\n⚠️  WARNING: No responses received from motor!")
            print("\nTroubleshooting:")
            print("  1. Check motor power supply is ON")
            print("  2. Verify UART TX/RX wiring to motor")
            print("  3. Confirm motor ID matches --motor-id parameter")
            print("  4. Ensure motor is in UART/RS485 mode (not CAN mode)")
        elif success_count < total_tests:
            print(f"\n⚠️  WARNING: Only {success_count} out of {total_tests} tests passed")
        else:
            print("\n✅ SUCCESS: All tests passed!")
            print("Motor communication is working correctly via RS485 protocol.")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ Error during test: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        ser.close()
        print("\nSerial port closed.")
        print("Test completed.")


if __name__ == "__main__":
    main()
