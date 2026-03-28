#!/usr/bin/env python3
"""
Pulse GPIO 24 (Compressor - Physical Pin 18)
"""
import sys, time
try:
    import lgpio
except ImportError:
    print("ERROR: lgpio not installed")
    sys.exit(1)

GPIO_PIN = 24  # Compressor
PULSE_DURATION = 0.5

def main():
    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, GPIO_PIN)
        
        print(f"Pulsing GPIO {GPIO_PIN} (Compressor - Physical Pin 18)...")
        print(f"Setting HIGH for {PULSE_DURATION} seconds...")
        
        lgpio.gpio_write(h, GPIO_PIN, 1)
        print(f"  State: {lgpio.gpio_read(h, GPIO_PIN)} (HIGH)")
        
        time.sleep(PULSE_DURATION)
        
        print(f"Setting LOW...")
        lgpio.gpio_write(h, GPIO_PIN, 0)
        print(f"  State: {lgpio.gpio_read(h, GPIO_PIN)} (LOW)")
        
        print("Pulse complete!")
        
        lgpio.gpiochip_close(h)
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
