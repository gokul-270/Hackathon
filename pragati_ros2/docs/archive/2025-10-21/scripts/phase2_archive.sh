#!/bin/bash
# Phase 2: Archive old/outdated documentation

cd /home/uday/Downloads/pragati_ros2

echo "Phase 2: Archiving old documentation"
echo "===================================="
echo ""

# Archive entire outdated folders
echo "1. Archiving analysis folder..."
git mv docs/analysis docs/archive/2025-10-analysis 2>/dev/null || echo "   (already moved or doesn't exist)"

echo "2. Archiving audit folder..."
git mv docs/audit docs/archive/2025-10-audit 2>/dev/null || echo "   (already moved or doesn't exist)"

echo "3. Archiving reports folder..."
git mv docs/reports docs/archive/2025-10-reports 2>/dev/null || echo "   (already moved or doesn't exist)"

echo "4. Archiving artifacts..."
git mv docs/artifacts docs/archive/2025-10-artifacts 2>/dev/null || echo "   (already moved or doesn't exist)"

echo "5. Archiving generated content..."
git mv docs/_generated docs/archive/2025-10-generated 2>/dev/null || echo "   (already moved or doesn't exist)"

echo "6. Archiving comparison..."
git mv docs/comparison docs/archive/2025-10-comparison 2>/dev/null || echo "   (already moved or doesn't exist)"

echo "7. Archiving validation..."
git mv docs/validation docs/archive/2025-10-validation 2>/dev/null || echo "   (already moved or doesn't exist)"

echo ""
echo "✓ Archive phase complete"
echo ""
echo "Status: git status"
