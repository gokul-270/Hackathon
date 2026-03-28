#!/usr/bin/env python3
"""
Comprehensive EE motor test to understand pin behavior
Tests all combinations to find what works
"""

import RPi.GPIO as GPIO
import time
import sys

# Pin definitions (BCM GPIO numbers that work)
ENABLE_PIN = 12  # BCM GPIO 12 (END_EFFECTOR_DROP_ON / M2 enable)
DIR_PIN = 19  # BCM GPIO 19 (not in gpio_control_functions.hpp - test-only pin)

print("🔧 EE Motor Comprehensive Test")
print("=" * 50)
print(f"ENABLE_PIN = {ENABLE_PIN} (BCM GPIO)")
print(f"DIR_PIN = {DIR_PIN} (BCM GPIO)")
print()

try:
    # Use BCM numbering
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(ENABLE_PIN, GPIO.OUT)
    GPIO.setup(DIR_PIN, GPIO.OUT)

    # CRITICAL: Initialize both pins to LOW state before any test
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    GPIO.output(DIR_PIN, GPIO.LOW)
    time.sleep(0.5)

    print("✅ GPIO setup complete\n")

    # Test 1: Enable HIGH, Dir LOW
    print("Test 1️⃣  Enable=HIGH, Dir=LOW")
    GPIO.output(DIR_PIN, GPIO.LOW)  # Ensure DIR_PIN is LOW first
    time.sleep(0.2)
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    print("   Running for 2 seconds...")
    time.sleep(2)
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    time.sleep(1)
    print("   ✓ Test 1 complete\n")

    # Test 2: Enable HIGH, Dir HIGH
    print("Test 2️⃣  Enable=HIGH, Dir=HIGH")
    GPIO.output(DIR_PIN, GPIO.HIGH)  # Ensure DIR_PIN is HIGH first
    time.sleep(0.2)
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    print("   Running for 2 seconds...")
    time.sleep(2)
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    time.sleep(1)
    print("   ✓ Test 2 complete\n")

    # Test 3: Only Enable, Dir stays LOW
    print("Test 3️⃣  Dir=LOW (stays), Enable toggles")
    GPIO.output(DIR_PIN, GPIO.LOW)
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    print("   Running for 2 seconds...")
    time.sleep(2)
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    time.sleep(1)
    print("   ✓ Test 3 complete\n")

    # Test 4: Only Enable, Dir stays HIGH
    print("Test 4️⃣  Dir=HIGH (stays), Enable toggles")
    GPIO.output(DIR_PIN, GPIO.HIGH)
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    print("   Running for 2 seconds...")
    time.sleep(2)
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    time.sleep(1)
    print("   ✓ Test 4 complete\n")

    print("✅ All tests complete! Check motor behavior above.")
    print("   Which test(s) showed motor rotation?")

except KeyboardInterrupt:
    print("\n⚠️  Test interrupted by user")

except Exception as e:
    print(f"\n❌ Error: {e}")
    sys.exit(1)

finally:
    # Cleanup
    print("\nCleaning up GPIO...")
    GPIO.output(ENABLE_PIN, GPIO.LOW)
    GPIO.output(DIR_PIN, GPIO.LOW)
    GPIO.cleanup()
    print("✅ GPIO cleaned up")
