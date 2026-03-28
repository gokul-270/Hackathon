#!/usr/bin/env python3
import sys, time, lgpio

h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(h, 24)

print("Testing GPIO 24 (current ROS2 setting) for compressor...")
print("Setting HIGH for 5 seconds - WATCH COMPRESSOR")
lgpio.gpio_write(h, 24, 1)
time.sleep(5)
lgpio.gpio_write(h, 24, 0)
print("Set back to LOW")

response = input("Did compressor turn ON? (yes/no): ")
if 'y' in response.lower():
    print("✅ GPIO 24 works - ROS2 code is correct")
else:
    print("❌ GPIO 24 doesn't work - need to find correct pin")
lgpio.gpiochip_close(h)
