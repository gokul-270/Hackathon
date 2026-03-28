#!/usr/bin/env python3
"""
Test if BCM GPIO 18 is connected to the compressor
Holds GPIO 18 HIGH for 5 seconds and asks user if compressor turns on
"""

import sys
import time
try:
    import lgpio
except ImportError:
    print("ERROR: lgpio library not installed")
    sys.exit(1)

GPIO_PIN = 18
TEST_DURATION = 5  # seconds

def main():
    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, GPIO_PIN)
        
        print("=" * 60)
        print(f"Testing if BCM GPIO 18 is connected to the compressor")
        print("=" * 60)
        
        # Initial state
        print(f"\n1. Setting GPIO 18 to LOW (OFF)...")
        lgpio.gpio_write(h, GPIO_PIN, 0)
        time.sleep(1)
        print(f"   Current state: {lgpio.gpio_read(h, GPIO_PIN)} (LOW)")
        input("   Press Enter to continue...")
        
        # Turn HIGH
        print(f"\n2. Setting GPIO 18 to HIGH (ON) for {TEST_DURATION} seconds...")
        print(f"   👀 WATCH THE COMPRESSOR - does it turn ON?")
        lgpio.gpio_write(h, GPIO_PIN, 1)
        print(f"   Current state: {lgpio.gpio_read(h, GPIO_PIN)} (HIGH)")
        
        # Countdown
        for i in range(TEST_DURATION, 0, -1):
            print(f"   Holding HIGH... {i} seconds remaining", end='\r')
            time.sleep(1)
        print()
        
        # Turn LOW
        print(f"\n3. Setting GPIO 18 to LOW (OFF)...")
        lgpio.gpio_write(h, GPIO_PIN, 0)
        print(f"   Current state: {lgpio.gpio_read(h, GPIO_PIN)} (LOW)")
        
        # Ask user
        print("\n" + "=" * 60)
        response = input("Did the compressor turn ON during the test? (yes/no): ").strip().lower()
        print("=" * 60)
        
        if response in ['yes', 'y']:
            print("\n✅ CONFIRMED: BCM GPIO 18 IS connected to the compressor")
            print("   Action needed: Update COMPRESSOR_PIN from 24 to 18 in code")
        elif response in ['no', 'n']:
            print("\n❌ CONFIRMED: BCM GPIO 18 is NOT connected to the compressor")
            print("   The compressor must be on a different GPIO pin")
            print("   Current code uses GPIO 24 - that should be correct")
        else:
            print("\n⚠️  Invalid response")
        
        lgpio.gpiochip_close(h)
        return 0
        
    except Exception as e:
        print(f"\nERROR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
