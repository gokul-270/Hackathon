#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

# Test multiple pins to find which one controls direction
TEST_PINS = [33, 35, 37, 40]

GPIO.setmode(GPIO.BOARD)

for enable_pin in TEST_PINS:
    for dir_pin in TEST_PINS:
        if enable_pin == dir_pin:
            continue
            
        print(f"\n{'='*50}")
        print(f"Testing: ENABLE=Pin{enable_pin}, DIR=Pin{dir_pin}")
        print(f"{'='*50}")
        
        try:
            GPIO.setup(enable_pin, GPIO.OUT)
            GPIO.setup(dir_pin, GPIO.OUT)
            
            # Test forward
            GPIO.output(enable_pin, GPIO.HIGH)
            GPIO.output(dir_pin, GPIO.HIGH)
            print(f"DIR={dir_pin} HIGH - observe motor")
            time.sleep(1.5)
            
            # Stop
            GPIO.output(enable_pin, GPIO.LOW)
            time.sleep(0.5)
            
            # Test reverse
            GPIO.output(enable_pin, GPIO.HIGH)
            GPIO.output(dir_pin, GPIO.LOW)
            print(f"DIR={dir_pin} LOW - observe motor")
            time.sleep(1.5)
            
            # Cleanup this test
            GPIO.output(enable_pin, GPIO.LOW)
            GPIO.cleanup()
            
            response = input("Did direction change? (y/n): ").strip().lower()
            if response == 'y':
                print(f"\n*** FOUND IT! ENABLE=Pin{enable_pin}, DIR=Pin{dir_pin} ***\n")
                break
                
        except Exception as e:
            print(f"Error: {e}")
            GPIO.cleanup()
    else:
        continue
    break

GPIO.cleanup()
print("\nTest complete")
