#!/usr/bin/env python3
"""
MG60 Motor Serial Communication Test Script
Sends basic CAN commands through USB-UART converter using SLCAN protocol
"""

import argparse
import binascii
import sys
import time

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Install with: pip3 install pyserial")
    sys.exit(1)


def build_slcan_frame(arbitration_id, data_bytes):
    """Build an SLCAN (LAWICEL) format CAN frame string"""
    if not (0 <= arbitration_id <= 0x7FF):
        raise ValueError("Standard 11-bit CAN ID required (0..0x7FF)")
    if len(data_bytes) != 8:
        raise ValueError("Data must be exactly 8 bytes")
    
    # SLCAN format: t<ID:3 hex><DLC:1 hex><DATA:2*DLC hex>\r
    # Example: t1418800000000000000\r for ID 0x141, 8 bytes, data 88 00 00 00 00 00 00 00
    frame = "t{ID:03X}8{DATA}\r".format(
        ID=arbitration_id,
        DATA="".join(f"{b:02X}" for b in data_bytes)
    )
    return frame.encode("ascii")


def parse_slcan_line(bline):
    """Parse an SLCAN response line"""
    try:
        s = bline.decode("ascii", errors="replace").strip()
        if not s:
            return None
        
        # Standard frame: t<ID:3><DLC:1><DATA>
        # Extended frame: T<ID:8><DLC:1><DATA>
        if s[0] == "t":
            arbid = int(s[1:4], 16)
            dlc = int(s[4], 16)
            data_hex = s[5:5 + dlc * 2]
        elif s[0] == "T":
            arbid = int(s[1:9], 16)
            dlc = int(s[9], 16)
            data_hex = s[10:10 + dlc * 2]
        else:
            # Not a CAN frame (could be status like 'z' or '\r')
            return {"type": "status", "raw": s}
        
        data = bytes(int(data_hex[i:i+2], 16) for i in range(0, len(data_hex), 2))
        return {"type": "can", "id": arbid, "dlc": dlc, "data": data, "raw": s}
    except Exception as e:
        return {"type": "error", "raw": str(bline), "error": str(e)}


def read_slcan_lines(ser, timeout_sec=0.3):
    """Read SLCAN lines within timeout period"""
    end = time.time() + timeout_sec
    buf = b""
    lines = []
    
    while time.time() < end:
        chunk = ser.read(256)
        if chunk:
            buf += chunk
            # Split on \r
            while True:
                idx = buf.find(b"\r")
                if idx < 0:
                    break
                line = buf[:idx]
                buf = buf[idx+1:]
                if line:
                    lines.append(line)
        else:
            time.sleep(0.01)
    
    return lines


def slcan_init(ser, can_speed_code="8"):
    """Initialize SLCAN adapter"""
    print("\nInitializing SLCAN adapter...")
    
    # Commands:
    # C - Close CAN channel
    # S8 - Set CAN speed to 1 Mbps (S0=10k, S1=20k, S2=50k, S3=100k, S4=125k, S5=250k, S6=500k, S7=800k, S8=1M)
    # O - Open CAN channel
    
    # SLCAN speed codes: S0=10k, S1=20k, S2=50k, S3=100k, S4=125k, S5=250k, S6=500k, S7=800k, S8=1M
    speed_map = {"0": "10k", "1": "20k", "2": "50k", "3": "100k", "4": "125k", 
                 "5": "250k", "6": "500k", "7": "800k", "8": "1M"}
    speed_name = speed_map.get(can_speed_code, "Unknown")
    
    commands = [
        (b"C\r", "Close channel"),
        (f"S{can_speed_code}\r".encode("ascii"), f"Set CAN speed to {speed_name}bps"),
        (b"O\r", "Open channel")
    ]
    
    for cmd, desc in commands:
        print(f"  Sending: {cmd.decode('ascii').strip()} ({desc})")
        ser.write(cmd)
        ser.flush()
        time.sleep(0.05)
        
        # Try to read response (some adapters respond with \r or 'z')
        response = ser.read(10)
        if response:
            print(f"    Response: {response}")


def send_and_print(ser, arbid, data, rx_timeout, title=""):
    """Send a CAN frame and print TX/RX details"""
    frame = build_slcan_frame(arbid, data)
    ascii_line = frame.decode("ascii").strip()
    raw_hex = " ".join(f"{b:02X}" for b in frame)
    
    print(f"\n{'='*70}")
    print(f"{'=== ' + title + ' ===' if title else '=== TX ==='}")
    print(f"{'='*70}")
    print(f"TX (SLCAN ASCII): {ascii_line}")
    print(f"TX (raw bytes):   {raw_hex}")
    print(f"CAN Frame: ID=0x{arbid:03X} Data=[{' '.join(f'{b:02X}' for b in data)}]")
    
    # Send frame
    ser.write(frame)
    ser.flush()
    
    # Wait for responses
    lines = read_slcan_lines(ser, timeout_sec=rx_timeout)
    
    if not lines:
        print(f"\n❌ RX: No data within {rx_timeout:.2f}s timeout")
        return False
    
    print(f"\n✓ RX: Received {len(lines)} line(s) within {rx_timeout:.2f}s")
    
    got_can_frame = False
    for i, ln in enumerate(lines, 1):
        parsed = parse_slcan_line(ln)
        
        if parsed and parsed.get("type") == "can":
            data_hex = " ".join(f"{b:02X}" for b in parsed["data"])
            print(f"  [{i}] CAN Frame:")
            print(f"      ID=0x{parsed['id']:03X} DLC={parsed['dlc']} DATA=[{data_hex}]")
            print(f"      RAW: '{parsed['raw']}'")
            got_can_frame = True
        elif parsed and parsed.get("type") == "status":
            print(f"  [{i}] Status: '{parsed['raw']}'")
        else:
            # Show raw bytes if parsing failed
            try:
                print(f"  [{i}] RAW: '{ln.decode('ascii', errors='replace')}'")
            except Exception:
                print(f"  [{i}] RAW bytes: {binascii.hexlify(ln).decode()}")
    
    return got_can_frame


def main():
    parser = argparse.ArgumentParser(
        description="MG60 Motor Communication Test via USB-UART (SLCAN)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic test with default settings
  python3 mg60_serial_test.py
  
  # Test with different motor ID
  python3 mg60_serial_test.py --node-id 2
  
  # Test with longer timeout
  python3 mg60_serial_test.py --rx-timeout 0.5
  
Note: Motor must be powered and connected via USB-UART converter to /dev/ttyUSB0
      UART baud rate: 115200 (fixed)
      CAN bus speed: 1 Mbps (configurable via --can-speed-code)
        """
    )
    
    parser.add_argument("--port", default="/dev/ttyUSB0",
                        help="Serial port (default: /dev/ttyUSB0)")
    parser.add_argument("--serial-baud", type=int, default=115200,
                        help="UART baud rate (default: 115200)")
    parser.add_argument("--node-id", type=int, default=1,
                        help="Motor node ID 1..32 (default: 1)")
    parser.add_argument("--rx-timeout", type=float, default=0.30,
                        help="RX timeout per command in seconds (default: 0.30)")
    parser.add_argument("--can-speed-code", default="8",
                        help="SLCAN speed code - S8=1Mbps (default: 8)")
    
    args = parser.parse_args()
    
    # Validate node ID
    if args.node_id < 1 or args.node_id > 32:
        print("ERROR: node-id must be between 1 and 32", file=sys.stderr)
        sys.exit(1)
    
    # Calculate CAN arbitration ID
    arbid = 0x140 + args.node_id
    
    # Display CAN speed mapping
    speed_map = {"0": "10k", "1": "20k", "2": "50k", "3": "100k", "4": "125k", 
                 "5": "250k", "6": "500k", "7": "800k", "8": "1M"}
    speed_name = speed_map.get(args.can_speed_code, "Unknown")
    
    print("="*70)
    print("MG60 Motor Serial Communication Test")
    print("="*70)
    print(f"Serial Port:      {args.port}")
    print(f"UART Baud Rate:   {args.serial_baud}")
    print(f"Motor Node ID:    {args.node_id}")
    print(f"CAN Arb ID:       0x{arbid:03X} (decimal {arbid})")
    print(f"RX Timeout:       {args.rx_timeout}s")
    print(f"CAN Speed:        S{args.can_speed_code} = {speed_name}bps")
    print("="*70)
    
    # Open serial port
    print(f"\nOpening {args.port} @ {args.serial_baud} baud...")
    try:
        ser = serial.Serial(
            port=args.port,
            baudrate=args.serial_baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
            write_timeout=0.2,
        )
        print(f"✓ Serial port opened successfully")
    except Exception as e:
        print(f"❌ Failed to open serial port: {e}", file=sys.stderr)
        print("\nTroubleshooting:")
        print("  1. Check if device exists: ls -l /dev/ttyUSB*")
        print("  2. Check permissions: sudo usermod -aG dialout $USER")
        print("  3. Reconnect USB cable and try again")
        sys.exit(2)
    
    success_count = 0
    total_tests = 4
    
    try:
        # Initialize SLCAN
        slcan_init(ser, can_speed_code=args.can_speed_code)
        
        # Test commands (from manufacturer reference)
        commands = [
            ("Motor OFF (0x80)", [0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
            ("Motor STOP (0x81)", [0x81, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
            ("Motor ON (0x88)", [0x88, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
            ("Read Status (0x9A)", [0x9A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
        ]
        
        print("\n" + "="*70)
        print("Starting Motor Communication Tests")
        print("="*70)
        
        for title, data in commands:
            if send_and_print(ser, arbid, data, rx_timeout=args.rx_timeout, title=title):
                success_count += 1
            time.sleep(0.15)  # Small delay between commands
        
        # Summary
        print("\n" + "="*70)
        print("Test Summary")
        print("="*70)
        print(f"Tests Passed: {success_count}/{total_tests}")
        
        if success_count == 0:
            print("\n⚠️  WARNING: No responses received from motor!")
            print("\nTroubleshooting steps:")
            print("  1. Check motor power supply is ON")
            print("  2. Verify USB-UART converter is connected correctly")
            print("  3. Check CANH/CANL wiring to motor")
            print("  4. Verify CAN bus termination (120Ω resistors)")
            print("  5. Confirm motor node ID matches --node-id parameter")
            print("  6. Try different CAN speed: --can-speed-code 6 (500kbps)")
            print("  7. Check if your adapter supports SLCAN protocol")
        elif success_count < total_tests:
            print(f"\n⚠️  WARNING: Only {success_count} out of {total_tests} tests got responses")
            print("Some commands may not be supported or motor may be in wrong state")
        else:
            print("\n✅ SUCCESS: All tests received responses!")
            print("Motor communication is working correctly.")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ Error during test: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        # Clean shutdown
        try:
            print("\nClosing SLCAN channel...")
            ser.write(b"C\r")
            ser.flush()
            time.sleep(0.05)
        except Exception:
            pass
        
        ser.close()
        print("Serial port closed.")
        print("\nTest completed.")


if __name__ == "__main__":
    main()
