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
    print("Testing pin states...")
    
    # Test 1: DIR HIGH
    print("\n=== Test 1: Direction HIGH (should be forward) ===")
    GPIO.output(DIR_PIN, GPIO.HIGH)
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    print(f"DIR_PIN: HIGH, ENABLE_PIN: LOW")
    time.sleep(1)
    
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    print(f"DIR_PIN: HIGH, ENABLE_PIN: HIGH - Motor should run FORWARD")
    time.sleep(3)
    
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    print("Motor stopped")
    time.sleep(2)
    
    # Test 2: DIR LOW
    print("\n=== Test 2: Direction LOW (should be reverse) ===")
    GPIO.output(DIR_PIN, GPIO.LOW)
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    print(f"DIR_PIN: LOW, ENABLE_PIN: LOW")
    time.sleep(1)
    
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    print(f"DIR_PIN: LOW, ENABLE_PIN: HIGH - Motor should run REVERSE")
    time.sleep(3)
    
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    print("Motor stopped")
    
    print("\n=== Tests complete ===")

finally:
    # Cleanup
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("GPIO cleaned up")
