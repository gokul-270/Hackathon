#!/usr/bin/env python3
import sys, time, lgpio

# Test these likely GPIO pins
test_pins = [17, 22, 23, 24, 25, 26, 27]

h = lgpio.gpiochip_open(0)

print("Testing multiple GPIO pins to find compressor...")
print("Watch the compressor and note which pin activates it\n")

for pin in test_pins:
    try:
        lgpio.gpio_claim_output(h, pin)
        print(f"GPIO {pin}: Setting HIGH for 2 seconds...")
        lgpio.gpio_write(h, pin, 1)
        time.sleep(2)
        lgpio.gpio_write(h, pin, 0)
        lgpio.gpio_free(h, pin)
        
        response = input(f"  Did compressor turn ON with GPIO {pin}? (y/n/q to quit): ")
        if 'q' in response.lower():
            break
        if 'y' in response.lower():
            print(f"\n✅ FOUND IT! Compressor is on GPIO {pin}")
            break
        print()
    except Exception as e:
        print(f"  Skipped GPIO {pin}: {e}\n")

lgpio.gpiochip_close(h)
