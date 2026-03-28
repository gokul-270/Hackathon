#!/usr/bin/env python3
"""
Check all GPIO pins status
Shows which pins are in use and their current state
"""

import sys
try:
    import lgpio
except ImportError:
    print("ERROR: lgpio library not installed")
    sys.exit(1)

def main():
    try:
        h = lgpio.gpiochip_open(0)
        
        # Common GPIO pins on Raspberry Pi (excluding special function pins)
        gpio_pins = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]
        
        print("GPIO Pin Status:")
        print("-" * 50)
        print(f"{'Pin':<8} {'State':<10} {'Status':<20}")
        print("-" * 50)
        
        for pin in gpio_pins:
            try:
                # Try to claim as input to read state
                lgpio.gpio_claim_input(h, pin)
                state = lgpio.gpio_read(h, pin)
                status = "HIGH (Active)" if state == 1 else "LOW (Inactive)"
                print(f"GPIO{pin:<4} {state:<10} {status:<20}")
                lgpio.gpio_free(h, pin)
            except Exception as e:
                # Pin might be in use
                print(f"GPIO{pin:<4} {'N/A':<10} {'In use or unavailable':<20}")
        
        print("-" * 50)
        
        lgpio.gpiochip_close(h)
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
