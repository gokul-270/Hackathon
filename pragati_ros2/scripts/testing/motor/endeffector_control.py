#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

# Pin definitions
ENABLE_PIN = 21  # BCM GPIO 21 (END_EFFECTOR_ON_PIN / M1 enable)
DIR_PIN = 13  # BCM GPIO 13 (END_EFFECTOR_DIRECTION_PIN / M1 direction)

# Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(ENABLE_PIN, GPIO.OUT)
GPIO.setup(DIR_PIN, GPIO.OUT)

try:
    # Enable the motor
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    GPIO.output(DIR_PIN, GPIO.LOW)

    print("Motor enabled")
    print("forward direction")
    time.sleep(2)  # Run forward for 2 seconds

    GPIO.output(ENABLE_PIN, GPIO.LOW)
    GPIO.output(DIR_PIN, GPIO.HIGH)
    print("backward direction")
    print("Motor enabled")
    time.sleep(2)  # Run forward for 2 seconds
    print("Cycle complete - turning off")

finally:
    # Cleanup
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    GPIO.output(DIR_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("GPIO cleaned up")
