#!/usr/bin/env python3
"""
MG6010 CAN Message Comparison Tool

Compares CAN messages from different implementations to verify protocol compatibility.
Parses candump log files and analyzes arbitration IDs, DLC, and payload data.

Usage:
    python3 compare_can_messages.py <log1> <log2>
    python3 compare_can_messages.py <log_file>  # Analyze single log

Example:
    python3 compare_can_messages.py /tmp/mg6010_test/candump.log /path/to/colleague/candump.log
"""

import sys
import re
from collections import defaultdict
from typing import Dict, List, Tuple, Set

class CANMessage:
    """Represents a single CAN message"""
    def __init__(self, timestamp: float, interface: str, arb_id: str, data: List[int]):
        self.timestamp = timestamp
        self.interface = interface
        self.arb_id = arb_id
        self.data = data
        self.dlc = len(data)
        
    def __repr__(self):
        data_str = ' '.join(f'{b:02X}' for b in self.data)
        return f"{self.arb_id}#{data_str} (DLC={self.dlc})"
    
    def matches_pattern(self, other: 'CANMessage', ignore_dynamic=True) -> bool:
        """Check if two messages match, optionally ignoring dynamic fields"""
        if self.arb_id != other.arb_id:
            return False
        if self.dlc != other.dlc:
            return False
        
        # Command byte (first byte) must match
        if len(self.data) > 0 and len(other.data) > 0:
            if self.data[0] != other.data[0]:
                return False
        
        if ignore_dynamic:
            # For many commands, only the command byte matters for verification
            # Dynamic fields like temperature, encoder position vary
            return True
        else:
            return self.data == other.data

def parse_candump_log(file_path: str) -> List[CANMessage]:
    """Parse a candump log file and extract CAN messages"""
    messages = []
    
    # candump format: (timestamp) interface arbitration_id#data
    # Example: (1696876543.123456) can0 141#8801020304050607
    pattern = re.compile(r'\((\d+\.\d+)\)\s+(\w+)\s+([0-9A-Fa-f]+)#([0-9A-Fa-f]*)')
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                match = pattern.match(line.strip())
                if match:
                    timestamp = float(match.group(1))
                    interface = match.group(2)
                    arb_id = match.group(3).upper()
                    data_str = match.group(4)
                    
                    # Parse data bytes
                    data = []
                    for i in range(0, len(data_str), 2):
                        data.append(int(data_str[i:i+2], 16))
                    
                    messages.append(CANMessage(timestamp, interface, arb_id, data))
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
        sys.exit(1)
    
    return messages

def group_messages_by_command(messages: List[CANMessage]) -> Dict[int, List[CANMessage]]:
    """Group messages by command byte (first data byte)"""
    grouped = defaultdict(list)
    for msg in messages:
        if msg.data:
            cmd = msg.data[0]
            grouped[cmd].append(msg)
    return dict(grouped)

def analyze_single_log(messages: List[CANMessage]) -> None:
    """Analyze and print statistics for a single log file"""
    print(f"\nTotal messages: {len(messages)}")
    
    # Group by arbitration ID
    by_id = defaultdict(list)
    for msg in messages:
        by_id[msg.arb_id].append(msg)
    
    print(f"\nMessages by Arbitration ID:")
    for arb_id in sorted(by_id.keys()):
        msgs = by_id[arb_id]
        print(f"  {arb_id}: {len(msgs)} messages")
        
        # Show command distribution for this ID
        by_cmd = defaultdict(int)
        for msg in msgs:
            if msg.data:
                by_cmd[msg.data[0]] += 1
        
        if by_cmd:
            print(f"    Commands:")
            for cmd in sorted(by_cmd.keys()):
                print(f"      0x{cmd:02X}: {by_cmd[cmd]} messages")
    
    # Show command code mapping
    print(f"\nCommand Codes Detected:")
    cmd_names = {
        0x80: "MOTOR_OFF",
        0x81: "MOTOR_STOP",
        0x88: "MOTOR_ON",
        0xA1: "TORQUE_CTRL",
        0xA2: "SPEED_CTRL",
        0xA3: "MULTI_LOOP_ANGLE_1",
        0xA4: "MULTI_LOOP_ANGLE_2",
        0xA5: "SINGLE_LOOP_ANGLE_1",
        0xA6: "SINGLE_LOOP_ANGLE_2",
        0xA7: "INCREMENT_ANGLE_1",
        0xA8: "INCREMENT_ANGLE_2",
        0x30: "READ_PID",
        0x31: "WRITE_PID_RAM",
        0x32: "WRITE_PID_ROM",
        0x33: "READ_ACCEL",
        0x34: "WRITE_ACCEL_RAM",
        0x90: "READ_ENCODER",
        0x91: "WRITE_ENCODER_OFFSET_ROM",
        0x92: "READ_MULTI_TURN_ANGLE",
        0x94: "READ_SINGLE_TURN_ANGLE",
        0x19: "SET_ZERO_ROM",
        0x9A: "READ_STATUS_1",
        0x9B: "CLEAR_ERRORS",
        0x9C: "READ_STATUS_2",
        0x9D: "READ_STATUS_3",
    }
    
    grouped = group_messages_by_command(messages)
    for cmd in sorted(grouped.keys()):
        cmd_name = cmd_names.get(cmd, "UNKNOWN")
        count = len(grouped[cmd])
        print(f"  0x{cmd:02X} ({cmd_name}): {count} messages")

def compare_logs(messages1: List[CANMessage], messages2: List[CANMessage], 
                 label1: str, label2: str) -> None:
    """Compare two sets of CAN messages"""
    print(f"\n{'='*60}")
    print(f"Comparison: {label1} vs {label2}")
    print(f"{'='*60}")
    
    # Compare message counts
    print(f"\nMessage Counts:")
    print(f"  {label1}: {len(messages1)}")
    print(f"  {label2}: {len(messages2)}")
    
    # Compare arbitration IDs
    ids1 = set(msg.arb_id for msg in messages1)
    ids2 = set(msg.arb_id for msg in messages2)
    
    print(f"\nArbitration IDs:")
    print(f"  {label1}: {sorted(ids1)}")
    print(f"  {label2}: {sorted(ids2)}")
    
    only_in_1 = ids1 - ids2
    only_in_2 = ids2 - ids1
    common_ids = ids1 & ids2
    
    if only_in_1:
        print(f"  Only in {label1}: {sorted(only_in_1)}")
    if only_in_2:
        print(f"  Only in {label2}: {sorted(only_in_2)}")
    print(f"  Common: {sorted(common_ids)}")
    
    # Compare command codes
    cmds1 = set(msg.data[0] for msg in messages1 if msg.data)
    cmds2 = set(msg.data[0] for msg in messages2 if msg.data)
    
    print(f"\nCommand Codes:")
    print(f"  {label1}: {sorted(f'0x{c:02X}' for c in cmds1)}")
    print(f"  {label2}: {sorted(f'0x{c:02X}' for c in cmds2)}")
    
    only_cmds_1 = cmds1 - cmds2
    only_cmds_2 = cmds2 - cmds1
    common_cmds = cmds1 & cmds2
    
    if only_cmds_1:
        print(f"  Only in {label1}: {sorted(f'0x{c:02X}' for c in only_cmds_1)}")
    if only_cmds_2:
        print(f"  Only in {label2}: {sorted(f'0x{c:02X}' for c in only_cmds_2)}")
    print(f"  Common: {sorted(f'0x{c:02X}' for c in common_cmds)}")
    
    # Detailed payload comparison for common commands
    if common_cmds:
        print(f"\nPayload Comparison for Common Commands:")
        
        grouped1 = group_messages_by_command(messages1)
        grouped2 = group_messages_by_command(messages2)
        
        for cmd in sorted(common_cmds):
            msgs1 = grouped1.get(cmd, [])
            msgs2 = grouped2.get(cmd, [])
            
            print(f"\n  Command 0x{cmd:02X}:")
            print(f"    {label1}: {len(msgs1)} messages")
            print(f"    {label2}: {len(msgs2)} messages")
            
            # Show first message of each as example
            if msgs1 and msgs2:
                print(f"    Example from {label1}: {msgs1[0]}")
                print(f"    Example from {label2}: {msgs2[0]}")
                
                # Check if patterns match
                if msgs1[0].matches_pattern(msgs2[0]):
                    print(f"    ✓ Patterns match")
                else:
                    print(f"    ✗ Patterns differ")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"{'='*60}")
    
    if ids1 == ids2 and cmds1 == cmds2:
        print("✓ Both implementations use identical arbitration IDs and command codes")
    else:
        print("⚠ Implementations have differences:")
        if ids1 != ids2:
            print("  - Different arbitration IDs detected")
        if cmds1 != cmds2:
            print("  - Different command codes detected")
    
    print()

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    log_file_1 = sys.argv[1]
    
    print("MG6010 CAN Message Comparison Tool")
    print("="*60)
    
    # Parse first log
    print(f"\nParsing: {log_file_1}")
    messages1 = parse_candump_log(log_file_1)
    
    if len(sys.argv) == 2:
        # Single log analysis
        print(f"\nAnalyzing single log file...")
        analyze_single_log(messages1)
    else:
        # Two log comparison
        log_file_2 = sys.argv[2]
        print(f"Parsing: {log_file_2}")
        messages2 = parse_candump_log(log_file_2)
        
        label1 = "Log 1"
        label2 = "Log 2"
        
        # Try to extract meaningful labels from filenames
        if "test" in log_file_1.lower():
            label1 = "New Implementation"
        if "colleague" in log_file_2.lower() or "tested" in log_file_2.lower():
            label2 = "Tested Implementation"
        
        compare_logs(messages1, messages2, label1, label2)

if __name__ == "__main__":
    main()
