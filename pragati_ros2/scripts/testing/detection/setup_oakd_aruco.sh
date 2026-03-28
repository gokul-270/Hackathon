#!/bin/bash
#
# Complete setup script for OAK-D ArUco Marker Detection (ROS2)
# Replaces RealSense-based detection with OAK-D/DepthAI
#
# Usage: ./setup_oakd_aruco.sh
#

set -e  # Exit on any error

echo "=========================================="
echo "OAK-D ArUco Detection Setup for ROS2"
echo "=========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -d "src/pattern_finder" ]; then
    echo -e "${RED}ERROR: Must run from pragati_ros2 workspace root${NC}"
    echo "Current directory: $(pwd)"
    exit 1
fi

echo -e "${GREEN}✓${NC} Running from workspace root: $(pwd)"
echo ""

# Step 1: Check/Install DepthAI SDK
echo "=========================================="
echo "Step 1: Checking DepthAI SDK"
echo "=========================================="
echo ""

if python3 -c "import depthai" 2>/dev/null; then
    DEPTHAI_VERSION=$(python3 -c "import depthai; print(depthai.__version__)")
    echo -e "${GREEN}✓${NC} DepthAI already installed (version: $DEPTHAI_VERSION)"
    
    # Check if version is sufficient (minimum 2.20.0 for OAK-D support)
    DEPTHAI_MAJOR=$(echo $DEPTHAI_VERSION | cut -d. -f1)
    DEPTHAI_MINOR=$(echo $DEPTHAI_VERSION | cut -d. -f2)
    
    if [ "$DEPTHAI_MAJOR" -ge 2 ] && [ "$DEPTHAI_MINOR" -ge 20 ]; then
        echo -e "${GREEN}✓${NC} DepthAI version is compatible (>= 2.20.0)"
    else
        echo -e "${YELLOW}WARNING:${NC} DepthAI version may be too old (need >= 2.20.0)"
        echo "Consider upgrading: python3 -m pip install --upgrade --break-system-packages depthai"
    fi
else
    echo "DepthAI not found. Installing..."
    echo "Note: Using --break-system-packages for Ubuntu 24.04+ (PEP 668)"
    
    # Try system install first (for Ubuntu desktop)
    if python3 -m pip install --break-system-packages depthai 2>/dev/null; then
        echo -e "${GREEN}✓${NC} DepthAI installed via pip (system)"
    # Fall back to user install (for restricted environments)
    elif python3 -m pip install --user --break-system-packages depthai 2>/dev/null; then
        echo -e "${GREEN}✓${NC} DepthAI installed via pip (user)"
    else
        echo -e "${RED}✗${NC} Failed to install DepthAI via pip"
        echo "Please install manually:"
        echo "  python3 -m pip install --break-system-packages depthai"
        echo "Or on RPi with ROS2, it may already be installed via ros-jazzy-depthai"
        exit 1
    fi
    
    # Verify installation
    if python3 -c "import depthai" 2>/dev/null; then
        DEPTHAI_VERSION=$(python3 -c "import depthai; print(depthai.__version__)")
        echo -e "${GREEN}✓${NC} DepthAI verified (version: $DEPTHAI_VERSION)"
    else
        echo -e "${RED}✗${NC} DepthAI installation failed verification"
        exit 1
    fi
fi
echo ""

# Step 2: Verify Python dependencies
echo "=========================================="
echo "Step 2: Verifying Python dependencies"
echo "=========================================="
echo ""

# Check OpenCV
if python3 -c "import cv2" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} OpenCV installed"
else
    echo "Installing python3-opencv..."
    sudo apt-get update
    sudo apt-get install -y python3-opencv
fi

# Check NumPy
if python3 -c "import numpy" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} NumPy installed"
else
    echo "Installing numpy..."
    python3 -m pip install --break-system-packages numpy 2>/dev/null || sudo apt-get install -y python3-numpy
fi

echo ""

# Step 3: Verify scripts are in place
echo "=========================================="
echo "Step 3: Verifying ArUco detection scripts"
echo "=========================================="
echo ""

if [ ! -f "src/pattern_finder/scripts/aruco_detect_oakd.py" ]; then
    echo -e "${RED}✗${NC} aruco_detect_oakd.py not found"
    exit 1
fi

if [ ! -f "src/pattern_finder/scripts/calc.py" ]; then
    echo -e "${RED}✗${NC} calc.py not found"
    exit 1
fi

if [ ! -f "src/pattern_finder/scripts/utility.py" ]; then
    echo -e "${RED}✗${NC} utility.py not found"
    exit 1
fi

echo -e "${GREEN}✓${NC} All Python scripts present"
echo ""

# Step 4: Build the pattern_finder package
echo "=========================================="
echo "Step 4: Building pattern_finder package"
echo "=========================================="
echo ""

colcon build --packages-select pattern_finder

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Build successful"
else
    echo -e "${RED}✗${NC} Build failed"
    exit 1
fi

echo ""

# Step 5: Source the workspace
echo "=========================================="
echo "Step 5: Sourcing workspace"
echo "=========================================="
echo ""

source install/setup.bash
echo -e "${GREEN}✓${NC} Workspace sourced"
echo ""

# Step 6: Create symlink to /usr/local/bin
echo "=========================================="
echo "Step 6: Creating /usr/local/bin symlink"
echo "=========================================="
echo ""

ARUCO_FINDER_PATH=$(readlink -f install/pattern_finder/lib/pattern_finder/aruco_finder_oakd)

if [ ! -f "$ARUCO_FINDER_PATH" ]; then
    echo -e "${RED}✗${NC} aruco_finder_oakd not found at: $ARUCO_FINDER_PATH"
    echo "Checking install directory contents:"
    ls -la install/pattern_finder/lib/pattern_finder/ 2>/dev/null || echo "Directory not found"
    exit 1
fi

echo "Creating symlink: /usr/local/bin/aruco_finder -> $ARUCO_FINDER_PATH (OAK-D Python version)"
sudo ln -sf "$ARUCO_FINDER_PATH" /usr/local/bin/aruco_finder

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Symlink created successfully"
else
    echo -e "${RED}✗${NC} Failed to create symlink (need sudo access)"
    exit 1
fi

echo ""

# Step 7: Verify installation
echo "=========================================="
echo "Step 7: Verifying installation"
echo "=========================================="
echo ""

if [ -x "/usr/local/bin/aruco_finder" ]; then
    echo -e "${GREEN}✓${NC} /usr/local/bin/aruco_finder exists and is executable"
    
    # Show the actual path
    echo "  Points to: $(readlink -f /usr/local/bin/aruco_finder)"
else
    echo -e "${RED}✗${NC} /usr/local/bin/aruco_finder not executable"
    exit 1
fi

# Test help output
echo ""
echo "Testing aruco_finder --help:"
echo "----------------------------------------"
/usr/local/bin/aruco_finder --help || true
echo "----------------------------------------"
echo ""

# Step 8: Instructions
echo "=========================================="
echo "✓ INSTALLATION COMPLETE!"
echo "=========================================="
echo ""
echo "The OAK-D-based ArUco detector is now installed as:"
echo "  /usr/local/bin/aruco_finder"
echo ""
echo -e "${YELLOW}NEXT STEPS:${NC}"
echo ""
echo "1. Connect your OAK-D camera"
echo ""
echo "2. Test standalone detection:"
echo "   mkdir -p /tmp/aruco_test && cd /tmp/aruco_test"
echo "   /usr/local/bin/aruco_finder --id 23 --timeout 10"
echo "   # Present ArUco marker ID 23 (DICT_6X6_250) to camera"
echo "   # Check: cat centroid.txt"
echo ""
echo "3. Test with yanthra_move:"
echo "   - Make sure YanthraLabCalibrationTesting=true in your config"
echo "   - Launch yanthra_move and it will automatically call aruco_finder"
echo ""
echo "4. Print ArUco marker ID 23:"
echo "   - Use the file: src/pattern_finder/marker_image.jpg"
echo "   - Or generate custom markers online"
echo ""
echo -e "${YELLOW}TROUBLESHOOTING:${NC}"
echo ""
echo "- If camera not found: Check USB connection (USB 3.0 recommended)"
echo "- If timeout: Ensure marker is well-lit and in camera view"
echo "- If depth invalid: Move marker closer (0.3-2m range)"
echo ""
echo "For more details, see: src/pattern_finder/README.md"
echo ""
echo "=========================================="
