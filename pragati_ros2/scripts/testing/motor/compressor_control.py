#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

# Pin definitions
COMPRESSOR_PIN = 18  # GPIO pin 18
# Pin 20 is GND (no setup needed)

# Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(COMPRESSOR_PIN, GPIO.OUT)

try:
    # Turn compressor ON
    GPIO.output(COMPRESSOR_PIN, GPIO.HIGH)
    print("Compressor ON")
    time.sleep(5)  # Run for 5 seconds
    
    # Turn compressor OFF
    GPIO.output(COMPRESSOR_PIN, GPIO.LOW)
    print("Compressor OFF")
    time.sleep(2)  # Wait 2 seconds
    
    # Turn compressor ON again
    GPIO.output(COMPRESSOR_PIN, GPIO.HIGH)
    print("Compressor ON")
    time.sleep(5)  # Run for 5 seconds
    
    print("Cycle complete - turning off")

finally:
    # Cleanup
    GPIO.output(COMPRESSOR_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("GPIO cleaned up")
