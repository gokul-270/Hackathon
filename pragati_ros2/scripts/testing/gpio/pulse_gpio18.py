#!/usr/bin/env python3
"""
Pulse GPIO 18 (Compressor Pin)
Makes it HIGH for 0.5 seconds, then LOW
"""

import sys
import time
try:
    import lgpio
except ImportError:
    print("ERROR: lgpio library not installed")
    sys.exit(1)

GPIO_PIN = 18
PULSE_DURATION = 0.5  # seconds

def main():
    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, GPIO_PIN)
        
        print(f"Pulsing GPIO {GPIO_PIN} (Compressor)...")
        print(f"Setting HIGH for {PULSE_DURATION} seconds...")
        
        # Set HIGH
        lgpio.gpio_write(h, GPIO_PIN, 1)
        state = lgpio.gpio_read(h, GPIO_PIN)
        print(f"  State: {state} (HIGH)")
        
        # Wait
        time.sleep(PULSE_DURATION)
        
        # Set LOW
        print(f"Setting LOW...")
        lgpio.gpio_write(h, GPIO_PIN, 0)
        state = lgpio.gpio_read(h, GPIO_PIN)
        print(f"  State: {state} (LOW)")
        
        print("Pulse complete!")
        
        lgpio.gpiochip_close(h)
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
