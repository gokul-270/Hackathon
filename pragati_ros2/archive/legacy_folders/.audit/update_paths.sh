#!/usr/bin/env bash
# Script to update all path references after reorganization

set -e

cd "$(git rev-parse --show-toplevel)"

echo "=== Updating path references ==="

# Backup
cp .audit/files.before.txt .audit/replace_targets.txt 2>/dev/null || true

# Update scripts/test/ references
echo "Updating scripts/test/ references..."
git grep -Il 'scripts/test/' 2>/dev/null | xargs -r sed -i 's#scripts/test/#test_suite/hardware/#g'

# Update src/cotton_detection_ros2/scripts/test_ references  
echo "Updating src/cotton_detection_ros2/scripts/test_ references..."
git grep -Il 'src/cotton_detection_ros2/scripts/test_' 2>/dev/null | xargs -r sed -i 's#src/cotton_detection_ros2/scripts/test_#src/cotton_detection_ros2/test/test_#g'

# Update docs/scripts/ references
echo "Updating docs/scripts/ references..."
git grep -Il 'docs/scripts/' 2>/dev/null | xargs -r sed -i 's#docs/scripts/#docs/archive/2025-10-21/scripts/#g'

# Update scripts/utils/ references (if any remain)
echo "Updating scripts/utils/ references..."
git grep -Il 'scripts/utils/' 2>/dev/null | while read -r file; do
  sed -i 's#scripts/utils/\(.*log.*\|.*monitor.*\|.*rotate.*\|performance.*\)#scripts/monitoring/\1#g' "$file"
  sed -i 's#scripts/utils/\(.*clean.*\|.*fix.*\|.*validate.*\|organize.*\)#scripts/maintenance/\1#g' "$file"
  sed -i 's#scripts/utils/\(create_upload.*\|ros2_explorer.*\)#scripts/build/\1#g' "$file"
done

echo "=== Path references updated ==="
echo ""
echo "Checking for any remaining old references..."

# Check for remaining references
echo -n "scripts/test/ references: "
git grep -n 'scripts/test/' 2>/dev/null | wc -l || echo "0"

echo -n "src/cotton_detection_ros2/scripts/test_ references: "
git grep -n 'src/cotton_detection_ros2/scripts/test_' 2>/dev/null | wc -l || echo "0"

echo -n "docs/scripts/ references: "
git grep -n 'docs/scripts/' 2>/dev/null | wc -l || echo "0"

echo -n "scripts/utils/ references: "
git grep -n 'scripts/utils/' 2>/dev/null | wc -l || echo "0"

echo "Done!"
