#!/bin/bash
################################################################################
# Simulated Cotton Detection Publisher - Convenience Wrapper
################################################################################
# Usage: ./simulate_cotton_detection.sh [MODE] [OPTIONS]
#
# Modes:
#   single       - Publish once and exit (default)
#   continuous   - Publish repeatedly
#   custom X Y Z - Publish custom position
#
# Examples:
#   ./simulate_cotton_detection.sh                    # Single detection
#   ./simulate_cotton_detection.sh continuous         # Continuous at 2 Hz
#   ./simulate_cotton_detection.sh continuous 5       # Continuous at 5 Hz
#   ./simulate_cotton_detection.sh custom 0.3 0.0 0.5 # Custom position
################################################################################

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEST_PUBLISHER="$WORKSPACE_ROOT/scripts/testing/test_cotton_detection_publisher.py"

# Check if test publisher exists
if [ ! -f "$TEST_PUBLISHER" ]; then
    echo -e "${RED}Error: Test publisher not found at:${NC}"
    echo "  $TEST_PUBLISHER"
    exit 1
fi

# Source ROS2 setup
if [ -f "$WORKSPACE_ROOT/install/setup.bash" ]; then
    echo -e "${BLUE}Sourcing ROS2 workspace...${NC}"
    source "$WORKSPACE_ROOT/install/setup.bash"
else
    echo -e "${YELLOW}Warning: Workspace not built. Run 'colcon build' first.${NC}"
fi

# Parse command line arguments
MODE="${1:-single}"

case "$MODE" in
    single)
        echo -e "${GREEN}Publishing single detection with 3 cotton positions${NC}"
        python3 "$TEST_PUBLISHER" --single
        ;;
        
    continuous)
        RATE="${2:-2.0}"
        echo -e "${GREEN}Publishing continuously at ${RATE} Hz${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        python3 "$TEST_PUBLISHER" --continuous --rate "$RATE"
        ;;
        
    custom)
        if [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]; then
            echo -e "${RED}Error: Custom mode requires X Y Z coordinates${NC}"
            echo "Usage: $0 custom X Y Z"
            echo "Example: $0 custom 0.3 0.0 0.5"
            exit 1
        fi
        X="$2"
        Y="$3"
        Z="$4"
        echo -e "${GREEN}Publishing custom position: ($X, $Y, $Z)${NC}"
        python3 "$TEST_PUBLISHER" --custom "$X" "$Y" "$Z"
        ;;
        
    help|--help|-h)
        echo "Simulated Cotton Detection Publisher"
        echo ""
        echo "Usage: $0 [MODE] [OPTIONS]"
        echo ""
        echo "Modes:"
        echo "  single              - Publish once and exit (default)"
        echo "  continuous [RATE]   - Publish repeatedly at RATE Hz (default: 2)"
        echo "  custom X Y Z        - Publish custom position (X,Y,Z in meters)"
        echo ""
        echo "Examples:"
        echo "  $0                          # Single detection"
        echo "  $0 single                   # Single detection (explicit)"
        echo "  $0 continuous               # Continuous at 2 Hz"
        echo "  $0 continuous 5             # Continuous at 5 Hz"
        echo "  $0 custom 0.3 0.0 0.5       # Custom position"
        echo ""
        echo "Coordinate System (camera frame):"
        echo "  X: Forward (0.15-0.6m typical)"
        echo "  Y: Right+ / Left- (-0.3 to 0.3m typical)"
        echo "  Z: Up (0.3-0.8m typical)"
        echo ""
        echo "Monitor Results:"
        echo "  ros2 topic echo /cotton_detection/results"
        echo "  ros2 topic hz /cotton_detection/results"
        echo ""
        exit 0
        ;;
        
    *)
        echo -e "${RED}Unknown mode: $MODE${NC}"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac

echo -e "${GREEN}Done${NC}"
