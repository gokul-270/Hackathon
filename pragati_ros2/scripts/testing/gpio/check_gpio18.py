#!/usr/bin/env python3
"""
Check GPIO 18 (Compressor Pin) Status
Reads the current state of GPIO 18 and displays it
"""

import sys
try:
    import lgpio
except ImportError:
    print("ERROR: lgpio library not installed")
    print("Install with: sudo apt install python3-lgpio")
    sys.exit(1)

# GPIO Configuration
GPIO_PIN = 18  # Compressor control pin

def main():
    try:
        # Open GPIO chip
        h = lgpio.gpiochip_open(0)
        
        # Set pin as input to read current state
        lgpio.gpio_claim_input(h, GPIO_PIN)
        
        # Read pin state
        state = lgpio.gpio_read(h, GPIO_PIN)
        
        print(f"GPIO 18 (Compressor) Status:")
        print(f"  Pin: GPIO{GPIO_PIN}")
        print(f"  State: {state}")
        print(f"  Status: {'HIGH (ON/Active)' if state == 1 else 'LOW (OFF/Inactive)'}")
        
        # Cleanup
        lgpio.gpiochip_close(h)
        
        return 0
        
    except Exception as e:
        print(f"ERROR reading GPIO: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
