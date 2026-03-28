#!/bin/bash

# Copyright notice to add
COPYRIGHT='// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

'

# Find all .h and .hpp files and add copyright
find /home/uday/Downloads/pragati_ros2/src/yanthra_move/include -name "*.h" -o -name "*.hpp" | while read file; do
    # Check if file already has copyright
    if ! grep -q "Copyright.*Pragati Robotics" "$file"; then
        echo "Adding copyright to $file"
        # Create temporary file with copyright + original content
        echo "$COPYRIGHT" > temp_file
        cat "$file" >> temp_file
        mv temp_file "$file"
    fi
done

# Fix header guards
find /home/uday/Downloads/pragati_ros2/src/yanthra_move/include -name "*.h" | while read file; do
    filename=$(basename "$file" .h)
    dirname=$(dirname "$file")
    relpath=${dirname##*/include/}
    guard=$(echo "${relpath}__${filename}_H_" | tr '[:lower:]' '[:upper:]' | tr '/' '_' | sed 's/-/_/g')
    
    if ! grep -q "#ifndef.*$guard" "$file"; then
        echo "Fixing header guard for $file -> $guard"
        # Add header guard after copyright
        sed -i "/Licensed under the Apache License/a\\
\\
#ifndef $guard\\
#define $guard" "$file"
        
        # Add closing guard at end
        echo "" >> "$file"
        echo "#endif  // $guard" >> "$file"
    fi
done

echo "Header fixes completed"