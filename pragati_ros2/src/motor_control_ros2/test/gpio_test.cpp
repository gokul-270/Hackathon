/*
 * Copyright (c) 2024 Open Source Robotics Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http:  // www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * @file gpio_test.cpp
 * @brief Simple test program for GPIO interface functionality
 * @author GPIO Enhancement
 * @date September 2025
 */

#include "motor_control_ros2/gpio_interface.hpp"
#include <iostream>
#include <chrono>
#include <thread>

int main()
{
    std::cout << "=== GPIO Interface Test ===" << std::endl;


    // Create GPIO interface
    motor_control_ros2::GPIOInterface gpio;

    // Test initialization
    std::cout << "Testing GPIO initialization..." << std::endl;
    if (!gpio.initialize())
    {
        std::cerr << "Failed to initialize GPIO: " << gpio.get_last_error() << std::endl;
        return -1;
    }


    std::cout << "GPIO initialization: SUCCESS" << std::endl;
    std::cout << "GPIO is initialized: " << (gpio.is_initialized() ? "YES" : "NO") << std::endl;

    // Test GPIO reading (simulation/sysfs mode)
    std::cout << "\nTesting GPIO pin reading..." << std::endl;

    // Test common GPIO pins (these would be limit switch pins in real hardware)
    int test_pins[] = {18, 19, 20, 21};  // Common GPIO pins on Raspberry Pi

    for (int pin : test_pins)
    {
        std::cout << "Reading GPIO pin " << pin << "..." << std::endl;


        // Set pin mode to input (if possible)
        if (gpio.set_mode(pin, 0))  // 0 = input mode
        {
            std::cout << "  Set pin " << pin << " to input mode: SUCCESS" << std::endl;
        } else
        {
            std::cout << "  Set pin " << pin << " to input mode: FAILED (" << gpio.get_last_error() << ")" << std::endl;
        }


        // Read pin value
        int value = gpio.read_gpio(pin);
        if (value >= 0)
        {
            std::cout << "  GPIO pin " << pin << " value: " << value << std::endl;
        } else
        {
            std::cout << "  GPIO pin " << pin << " read failed: " << gpio.get_last_error() << std::endl;
        }


        // Small delay
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    // Test multiple reads to see simulation behavior
    std::cout << "\nTesting simulation behavior (if in simulation mode)..." << std::endl;
    for (int i = 0; i < 15; i++)
    {
        int value = gpio.read_gpio(18);
        std::cout << "Read " << i+1 << ": GPIO 18 = " << value << std::endl;
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }


    std::cout << "\n=== GPIO Interface Test Complete ===" << std::endl;
    return 0;
}
