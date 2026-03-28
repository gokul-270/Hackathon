#!/usr/bin/env bash
#
# Setup Offline Testing - Copy Test Images
# =========================================
#
# This script helps you set up offline image-based testing
# by copying your cotton test images to the inputs/ folder.
#
# Usage:
#   bash scripts/validation/system/setup_offline_testing.sh /path/to/image.jpg
#   bash scripts/validation/system/setup_offline_testing.sh /path/to/folder/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${PRAGATI_WORKSPACE:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
INPUTS_DIR="$WORK_DIR/inputs"

echo "Setting up offline testing..."
echo ""

if [[ ! -d "$INPUTS_DIR" ]]; then
    echo "Creating inputs directory: $INPUTS_DIR"
    mkdir -p "$INPUTS_DIR"
fi

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <image_file_or_directory>"
    echo ""
    echo "Examples:"
    echo "  $0 /path/to/cotton.jpg          # Copy single image"
    echo "  $0 /path/to/image/folder/       # Copy all images from folder"
    echo ""
    echo "Current inputs directory: $INPUTS_DIR"
    if ls "$INPUTS_DIR"/*.{jpg,jpeg,png,JPG,JPEG,PNG} 2>/dev/null | head -1 >/dev/null 2>&1; then
        echo ""
        echo "Existing test images:"
        ls -lh "$INPUTS_DIR"/*.{jpg,jpeg,png,JPG,JPEG,PNG} 2>/dev/null || true
    else
        echo ""
        echo "No test images found in $INPUTS_DIR"
    fi
    exit 1
fi

SOURCE="$1"

if [[ ! -e "$SOURCE" ]]; then
    echo "Error: $SOURCE does not exist"
    exit 1
fi

if [[ -f "$SOURCE" ]]; then
    echo "Copying image file: $(basename "$SOURCE")"
    cp "$SOURCE" "$INPUTS_DIR/"
    echo "✓ Image copied to: $INPUTS_DIR/$(basename "$SOURCE")"
elif [[ -d "$SOURCE" ]]; then
    echo "Copying images from directory: $SOURCE"
    IMAGE_COUNT=$(find "$SOURCE" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) | wc -l)
    if [[ $IMAGE_COUNT -eq 0 ]]; then
        echo "No image files found in $SOURCE"
        exit 1
    fi
    echo "Found $IMAGE_COUNT image(s)"
    find "$SOURCE" -maxdepth 1 -type f \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) -exec cp {} "$INPUTS_DIR/" \;
    echo "✓ $IMAGE_COUNT image(s) copied to: $INPUTS_DIR"
else
    echo "Error: $SOURCE is neither a file nor a directory"
    exit 1
fi

echo ""
echo "Offline testing setup complete!"
echo ""
echo "Test images in inputs/:"
ls -lh "$INPUTS_DIR"/*.{jpg,jpeg,png,JPG,JPEG,PNG} 2>/dev/null || echo "  (none)"
echo ""
echo "Now run the validation script to test with these images:"
echo "  cd $WORK_DIR"
echo "  bash scripts/validation/system/run_table_top_validation.sh"
