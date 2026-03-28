#!/bin/bash

# Fix copyright headers for ROS2 packages
# This addresses the 39 copyright test failures

set -e

echo "🔧 Fixing copyright headers for production readiness..."

cd /home/uday/Downloads/pragati_ros2

# Standard copyright header for C++ files
CPP_COPYRIGHT='/*
 * Copyright (c) 2024, Yanthra Technologies
 * All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

'

# Standard copyright header for Python files
PYTHON_COPYRIGHT='# Copyright (c) 2024, Yanthra Technologies
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'

# Function to add copyright to C++ file
add_cpp_copyright() {
    local file=$1
    if ! head -n 5 "$file" | grep -q "Copyright"; then
        echo "$CPP_COPYRIGHT" | cat - "$file" > "$file.tmp" && mv "$file.tmp" "$file"
        echo "✅ Added copyright to $file"
    fi
}

# Function to add copyright to Python file
add_python_copyright() {
    local file=$1
    # Skip shebang line if present
    if head -n 1 "$file" | grep -q "^#!"; then
        if ! head -n 10 "$file" | grep -q "Copyright"; then
            (head -n 1 "$file"; echo "$PYTHON_COPYRIGHT"; tail -n +2 "$file") > "$file.tmp" && mv "$file.tmp" "$file"
            echo "✅ Added copyright to $file"
        fi
    else
        if ! head -n 5 "$file" | grep -q "Copyright"; then
            echo "$PYTHON_COPYRIGHT" | cat - "$file" > "$file.tmp" && mv "$file.tmp" "$file"
            echo "✅ Added copyright to $file"
        fi
    fi
}

# Process C++ header files
echo "📝 Processing C++ header files..."
find src/odrive_control_ros2/include -name "*.hpp" | while read file; do
    add_cpp_copyright "$file"
done

# Process C++ source files
echo "📝 Processing C++ source files..."
find src/odrive_control_ros2/src -name "*.cpp" | while read file; do
    add_cpp_copyright "$file"
done

# Process Python launch files
echo "📝 Processing Python launch files..."
find src/odrive_control_ros2/launch -name "*.py" | while read file; do
    add_python_copyright "$file"
done

# Process Python scripts
echo "📝 Processing Python scripts..."
find src/odrive_control_ros2/scripts -name "*.py" | while read file; do
    add_python_copyright "$file"
done

echo "🎉 Copyright headers fixed! Running test to verify..."
cd /home/uday/Downloads/pragati_ros2
colcon test --packages-select odrive_control_ros2 --event-handlers console_direct+ --ctest-args -R copyright