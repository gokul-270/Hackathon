#!/usr/bin/env python3
"""
Hold GPIO 18 HIGH
Keeps the compressor pin HIGH until Ctrl+C
"""

import sys
import time
import signal
try:
    import lgpio
except ImportError:
    print("ERROR: lgpio library not installed")
    sys.exit(1)

GPIO_PIN = 18
h = None

def cleanup(signum, frame):
    print("\n\nShutting down...")
    if h is not None:
        lgpio.gpio_write(h, GPIO_PIN, 0)
        print("GPIO 18 set to LOW")
        lgpio.gpiochip_close(h)
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def main():
    global h
    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, GPIO_PIN)
        lgpio.gpio_write(h, GPIO_PIN, 1)
        
        print(f"GPIO 18 (Compressor) is now HIGH")
        print("Press Ctrl+C to stop and set LOW")
        
        while True:
            time.sleep(1)
            
    except Exception as e:
        print(f"ERROR: {e}")
        if h is not None:
            lgpio.gpiochip_close(h)
        return 1

if __name__ == "__main__":
    sys.exit(main())
