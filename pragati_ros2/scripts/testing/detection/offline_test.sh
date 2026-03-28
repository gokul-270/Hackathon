#!/bin/bash
# Quick offline image testing wrapper
# Usage: ./test_offline_images.sh [image_or_dir] [--visualize]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_SCRIPT="${SCRIPT_DIR}/src/cotton_detection_ros2/scripts/test_with_images.py"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if ROS2 is sourced
if [ -z "$ROS_DISTRO" ]; then
    echo -e "${YELLOW}⚠ ROS2 not sourced. Sourcing...${NC}"
    source "${SCRIPT_DIR}/install/setup.bash"
fi

# Check if detection node is running
if ! ros2 node list 2>/dev/null | grep -q "cotton_detection"; then
    echo -e "${RED}✗ Cotton detection node not running!${NC}"
    echo ""
    echo "Please start it in another terminal:"
    echo "  cd ${SCRIPT_DIR}"
    echo "  source install/setup.bash"
    echo "  ros2 launch cotton_detection_ros2 cotton_detection_cpp.launch.py use_depthai:=false"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Detection node is running${NC}"
echo ""

# Parse arguments
IMAGE_PATH=""
EXTRA_ARGS=()

for arg in "$@"; do
    case $arg in
        --visualize|-v|--output|-o|--timeout|--delay|--display-time)
            EXTRA_ARGS+=("$arg")
            ;;
        *)
            if [ -z "$IMAGE_PATH" ]; then
                IMAGE_PATH="$arg"
            else
                EXTRA_ARGS+=("$arg")
            fi
            ;;
    esac
done

# Default to current directory if no path specified
if [ -z "$IMAGE_PATH" ]; then
    IMAGE_PATH="."
fi

# Check if path exists
if [ ! -e "$IMAGE_PATH" ]; then
    echo -e "${RED}✗ Path not found: $IMAGE_PATH${NC}"
    exit 1
fi

# Determine if it's a file or directory
if [ -f "$IMAGE_PATH" ]; then
    echo "Testing single image: $IMAGE_PATH"
    python3 "$TEST_SCRIPT" --image "$IMAGE_PATH" "${EXTRA_ARGS[@]}"
elif [ -d "$IMAGE_PATH" ]; then
    # Count images in directory
    IMAGE_COUNT=$(find "$IMAGE_PATH" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" -o -iname "*.bmp" \) | wc -l)
    
    if [ "$IMAGE_COUNT" -eq 0 ]; then
        echo -e "${RED}✗ No images found in: $IMAGE_PATH${NC}"
        exit 1
    fi
    
    echo "Testing $IMAGE_COUNT images from: $IMAGE_PATH"
    python3 "$TEST_SCRIPT" --dir "$IMAGE_PATH" "${EXTRA_ARGS[@]}"
else
    echo -e "${RED}✗ Invalid path: $IMAGE_PATH${NC}"
    exit 1
fi
