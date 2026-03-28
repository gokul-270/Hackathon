#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

# Pin definitions
ENABLE_PIN = 40
DIR_PIN = 33

# Setup
GPIO.setmode(GPIO.BOARD)
GPIO.setup(ENABLE_PIN, GPIO.OUT)
GPIO.setup(DIR_PIN, GPIO.OUT)

try:
    # Disable motor first
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    
    print("Toggling DIR_PIN to verify it's working...")
    print("(Motor should be OFF during this test)")
    
    for i in range(5):
        GPIO.output(DIR_PIN, GPIO.HIGH)
        print(f"Cycle {i+1}: DIR_PIN = HIGH")
        time.sleep(0.5)
        
        GPIO.output(DIR_PIN, GPIO.LOW)
        print(f"Cycle {i+1}: DIR_PIN = LOW")
        time.sleep(0.5)
    
    print("\nNow testing with SWAPPED pins...")
    print("(Maybe ENABLE and DIR are swapped?)")
    
    # Try swapping: Use pin 33 as enable, pin 40 as direction
    GPIO.output(DIR_PIN, GPIO.HIGH)  # Pin 33 as enable
    print("\nUsing Pin 33 as ENABLE, Pin 40 as DIR")
    
    GPIO.output(ENABLE_PIN, GPIO.HIGH)  # Pin 40 HIGH (direction)
    print("Pin 40 = HIGH - observe motor direction")
    time.sleep(2)
    
    GPIO.output(ENABLE_PIN, GPIO.LOW)  # Pin 40 LOW (direction)
    print("Pin 40 = LOW - observe motor direction")
    time.sleep(2)
    
    GPIO.output(DIR_PIN, GPIO.LOW)  # Disable
    print("Motor stopped")

finally:
    # Cleanup
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    GPIO.output(DIR_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("GPIO cleaned up")
