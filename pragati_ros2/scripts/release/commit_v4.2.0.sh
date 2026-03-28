#!/bin/bash

# Pragati ROS2 v4.2.0 - Modular Documentation + ODrive Cleanup
# Commit script for version 4.2.0 changes

set -e

echo "═══════════════════════════════════════════════════════════"
echo "📦 Pragati ROS2 v4.2.0 - Commit Preparation"
echo "═══════════════════════════════════════════════════════════"
echo ""

cd /home/uday/Downloads/pragati_ros2

echo "Step 1/5: Adding modified files..."
git add docs/README.md
git add src/motor_control_ros2/launch/hardware_interface.launch.py
echo "✅ Modified files staged"
echo ""

echo "Step 2/5: Adding new documentation modules..."
git add docs/production-system/
git add docs/enhancements/
echo "✅ New module directories staged"
echo ""

echo "Step 3/5: Adding summary documents..."
git add docs/MODULAR_DOCUMENTATION_SUMMARY.md
git add CHANGES_SUMMARY_v4.2.0.md
echo "✅ Summary documents staged"
echo ""

echo "Step 4/5: Adding comprehensive production document (v4.2.0)..."
git add docs/PRODUCTION_SYSTEM_EXPLAINED.md
echo "✅ Comprehensive doc staged"
echo ""

echo "Step 5/5: Review staged changes..."
echo ""
git status --short
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "✅ Files staged and ready to commit!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📊 Summary:"
echo "  - Modified: 2 files (README.md, launch file)"
echo "  - New: 10 documentation modules"
echo "  - New: 2 summary documents"
echo ""
echo "🎯 Commit command ready:"
echo ""
echo "git commit -m \"docs: restructure production docs to modular format + fix ODrive refs

- Split PRODUCTION_SYSTEM_EXPLAINED.md into 9 focused modules
- Add main navigation README with role-based access
- Document multi-cotton detection and pickability classification
- Add Phase 2 roadmap with 12-week timeline
- Fix ODrive legacy references → MG6010 in launch file

BREAKING: Old PRODUCTION_SYSTEM_EXPLAINED.md links need updating
BENEFITS: Easier navigation, better maintainability, cleaner diffs

Version: 4.2.0
Impact: Documentation - High, Code - Low
Files: 12 new/modified (10 docs, 1 launch file, 1 summary)

Co-authored-by: AI Assistant <assistant@pragati-ros2.dev>
\""
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "📝 Next steps:"
echo "  1. Review: git diff --cached"
echo "  2. Commit: Run the command above (or use this script's commit)"
echo "  3. Cleanup: Optionally remove backup files"
echo "═══════════════════════════════════════════════════════════"
echo ""
read -p "Do you want to commit now? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Committing changes..."
    git commit -m "docs: restructure production docs to modular format + fix ODrive refs

- Split PRODUCTION_SYSTEM_EXPLAINED.md into 9 focused modules
- Add main navigation README with role-based access  
- Document multi-cotton detection and pickability classification
- Add Phase 2 roadmap with 12-week timeline
- Fix ODrive legacy references → MG6010 in launch file

BREAKING: Old PRODUCTION_SYSTEM_EXPLAINED.md links need updating
BENEFITS: Easier navigation, better maintainability, cleaner diffs

Version: 4.2.0
Impact: Documentation - High, Code - Low
Files: 12 new/modified (10 docs, 1 launch file, 1 summary)"
    
    echo ""
    echo "✅ Changes committed successfully!"
    echo ""
    echo "📋 Optional cleanup (backup files):"
    echo "  git rm docs/README.md.old"
    echo "  git rm docs/PRODUCTION_SYSTEM_EXPLAINED.md.v4.1.0.backup"
    echo ""
else
    echo "❌ Commit cancelled. Files remain staged."
    echo "   You can commit manually when ready."
fi

