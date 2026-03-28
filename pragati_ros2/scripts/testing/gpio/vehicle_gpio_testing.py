#!/usr/bin/env python3
"""
Standalone GPIO Test Script
Tests all GPIO pins configured for the vehicle control system

Requirements:
- pigpiod daemon must be running: sudo systemctl start pigpiod
- No root access needed (pigpio uses daemon)

Usage:
    python3 test_gpio_standalone.py
"""

import pigpio
import time
import sys

# GPIO Pin Configuration (BCM numbering)
INPUT_PINS = {
    16: "Direction Left",
    21: "Direction Right",
    20: "Automatic Mode Switch",
    6: "Start Button",
    5: "Shutdown Button",
    4: "Reboot Button",
}

OUTPUT_PINS = {
    22: "Software Status LED (Green)",
    27: "Yellow/Orange LED",
    17: "Raspberry Pi Power LED (Red)",
}


def test_outputs(pi):
    """Test all output pins by blinking them"""
    print("\n" + "=" * 60)
    print("TESTING OUTPUT PINS")
    print("=" * 60)

    # Setup output pins
    for pin, name in OUTPUT_PINS.items():
        pi.set_mode(pin, pigpio.OUTPUT)
        pi.write(pin, 0)  # Start LOW
        print(f"✓ GPIO {pin:2d} ({name}) configured as OUTPUT")

    print("\n--- Blinking each LED 3 times (1 second on/off) ---")

    for pin, name in OUTPUT_PINS.items():
        print(f"\nTesting GPIO {pin} - {name}")
        for i in range(3):
            print(f"  Cycle {i+1}/3: ON", end="", flush=True)
            pi.write(pin, 1)  # HIGH
            time.sleep(1)
            print(" → OFF", flush=True)
            pi.write(pin, 0)  # LOW
            time.sleep(1)

    print("\n--- Testing all LEDs ON simultaneously ---")
    for pin in OUTPUT_PINS.keys():
        pi.write(pin, 1)
    print("All LEDs should be ON now (waiting 3 seconds)...")
    time.sleep(3)

    print("Turning all LEDs OFF...")
    for pin in OUTPUT_PINS.keys():
        pi.write(pin, 0)

    print("\n✅ Output pin test complete!")

    # Leave GPIO 22 (Software Status LED) ON to indicate script is running
    pi.write(22, 1)
    print("ℹ️  GPIO 22 (Software Status LED) left ON")

    # Leave GPIO 17 (Pi Power LED) ON to indicate Pi is powered
    pi.write(17, 1)
    print("ℹ️  GPIO 17 (Pi Power LED) left ON")


def test_inputs(pi):
    """Test all input pins by reading their states"""
    print("\n" + "=" * 60)
    print("TESTING INPUT PINS")
    print("=" * 60)

    # Setup input pins with pull-down resistors
    for pin, name in INPUT_PINS.items():
        if pin in [4, 5, 6]:  # Buttons might need pull-up
            pi.set_mode(pin, pigpio.INPUT)
            pi.set_pull_up_down(pin, pigpio.PUD_DOWN)
        else:
            pi.set_mode(pin, pigpio.INPUT)
            pi.set_pull_up_down(pin, pigpio.PUD_DOWN)
        print(f"✓ GPIO {pin:2d} ({name}) configured as INPUT")

    print("\n--- Reading input states (press buttons/flip switches to test) ---")
    print("Will read for 10 seconds. Press Ctrl+C to stop early.\n")

    try:
        start_time = time.time()
        last_states = {}

        while (time.time() - start_time) < 10:
            for pin, name in INPUT_PINS.items():
                state = pi.read(pin)

                # Print only on state change
                if pin not in last_states or last_states[pin] != state:
                    state_str = "HIGH (pressed/on)" if state else "LOW (released/off)"
                    print(f"GPIO {pin:2d} ({name:30s}): {state_str}")

                    last_states[pin] = state

            time.sleep(0.1)  # Poll every 100ms

    except KeyboardInterrupt:
        print("\n\nInput test interrupted by user")

    print("\n--- Final input states ---")
    for pin, name in INPUT_PINS.items():
        state = pi.read(pin)
        state_str = "HIGH" if state else "LOW"
        print(f"GPIO {pin:2d} ({name:30s}): {state_str}")

    print("\n✅ Input pin test complete!")


def main():
    """Main test function"""
    print("=" * 60)
    print("VEHICLE CONTROL GPIO TEST SCRIPT")
    print("=" * 60)
    print("\nThis script will test:")
    print("  • 6 input pins (buttons and switches)")
    print("  • 3 output pins (LEDs)")
    print("\nBCM GPIO numbering is used (not BOARD/physical pin numbers)")

    # Connect to pigpiod daemon
    print("\n--- Connecting to pigpiod daemon ---")

    pi = pigpio.pi()

    if not pi.connected:
        print("❌ ERROR: Could not connect to pigpiod daemon!")
        print("\nTroubleshooting:")
        print("  1. Check if pigpiod is running:")
        print("     sudo systemctl status pigpiod")
        print("  2. Start pigpiod if needed:")
        print("     sudo systemctl start pigpiod")
        print("  3. Enable pigpiod to start on boot:")
        print("     sudo systemctl enable pigpiod")
        sys.exit(1)

    print("✅ Connected to pigpiod daemon")
    print(f"   pigpio version: {pi.get_pigpio_version()}")
    print(f"   Hardware revision: {pi.get_hardware_revision()}")

    try:
        # Test outputs first (visual feedback)
        # test_outputs(pi)
        for i in range(10):
            # Test inputs (interactive)
            test_inputs(pi)

        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETE!")
        print("=" * 60)
        print("\n✅ GPIO 22 (Software Status LED) is ON")
        print("✅ GPIO 17 (Pi Power LED) is ON")
        print("\nThese will stay on until you run:")
        print(
            "  python3 -c 'import pigpio; pi=pigpio.pi(); pi.write(22,0); pi.write(17,0); pi.stop()'"
        )

    except Exception as e:
        print(f"\n❌ ERROR during testing: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Clean up (but leave status LEDs on)
        print("\n--- Cleaning up GPIO ---")
        # Turn off yellow/orange LED
        pi.write(27, 0)
        print("✓ GPIO 27 (Yellow/Orange LED) turned OFF")

        # Disconnect
        pi.stop()
        print("✓ Disconnected from pigpiod")


if __name__ == "__main__":
    main()
