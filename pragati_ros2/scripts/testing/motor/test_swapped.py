#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

# Pin definitions - SWAPPED
ENABLE_PIN = 33  # Was 40
DIR_PIN = 40     # Was 33

# Setup
GPIO.setmode(GPIO.BOARD)
GPIO.setup(ENABLE_PIN, GPIO.OUT)
GPIO.setup(DIR_PIN, GPIO.OUT)

try:
    print("Testing with SWAPPED pins (33=ENABLE, 40=DIR)")
    
    # Enable the motor
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    print("Motor enabled")
    
    # Forward direction
    GPIO.output(DIR_PIN, GPIO.HIGH)
    print("\nDirection: HIGH - observe direction")
    time.sleep(2)
    
    # Stop motor before changing direction
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    print("Motor stopped")
    time.sleep(1)
    
    # Re-enable motor
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    print("Motor enabled")
    
    # Reverse direction
    GPIO.output(DIR_PIN, GPIO.LOW)
    print("\nDirection: LOW - observe direction (should be different)")
    time.sleep(2)
    
    print("\nTest complete")

finally:
    # Cleanup
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("GPIO cleaned up")
