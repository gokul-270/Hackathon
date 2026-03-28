#!/usr/bin/env python3
"""
Control GPIO 18 (Compressor Pin)
Sets GPIO 18 HIGH or LOW
"""

import sys
import time
try:
    import lgpio
except ImportError:
    print("ERROR: lgpio library not installed")
    sys.exit(1)

GPIO_PIN = 18  # Compressor control pin

def main():
    if len(sys.argv) < 2:
        print("Usage: sudo python3 set_gpio18.py [high|low|on|off]")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command in ['high', 'on', '1']:
        target_state = 1
        action = "HIGH (ON)"
    elif command in ['low', 'off', '0']:
        target_state = 0
        action = "LOW (OFF)"
    else:
        print(f"Invalid command: {command}")
        print("Usage: sudo python3 set_gpio18.py [high|low|on|off]")
        sys.exit(1)
    
    try:
        # Open GPIO chip
        h = lgpio.gpiochip_open(0)
        
        # Set pin as output
        lgpio.gpio_claim_output(h, GPIO_PIN)
        
        # Set pin state
        lgpio.gpio_write(h, GPIO_PIN, target_state)
        
        # Read back to verify
        time.sleep(0.1)
        actual_state = lgpio.gpio_read(h, GPIO_PIN)
        
        print(f"GPIO 18 (Compressor) Control:")
        print(f"  Pin: GPIO{GPIO_PIN}")
        print(f"  Command: {action}")
        print(f"  Actual State: {actual_state}")
        print(f"  Status: {'✓ SUCCESS' if actual_state == target_state else '✗ FAILED'}")
        
        # Cleanup
        lgpio.gpiochip_close(h)
        
        return 0 if actual_state == target_state else 1
        
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
