# Data Folders Consolidation Plan
**Generated**: 2025-10-06
**Goal**: Move `inputs/` and `outputs/` into `data/` directory and update all references

---

## Current Structure

```
pragati_ros2/
├── inputs/          (real directory - 4 files, ~1.2MB)
├── outputs/         (real directory - 9 files, ~884KB)
└── data/
    ├── inputs -> ../inputs    (symlink)
    └── outputs -> ../outputs  (symlink)
```

---

## Proposed Structure

```
pragati_ros2/
└── data/
    ├── inputs/      (moved from root)
    ├── outputs/     (moved from root)
    └── frames/      (already exists)
```

---

## Files to Update (12 references found)

### 1. **test_suite/hardware/test_hsv_detection.py** (2 references)
- Line 84: `/home/uday/Downloads/pragati_ros2/inputs/ArucoInputImage.jpg`
- Line 85: `/home/uday/Downloads/pragati_ros2/inputs/img100.jpg`

**Change to**:
```python
"/home/uday/Downloads/pragati_ros2/data/inputs/ArucoInputImage.jpg"
"/home/uday/Downloads/pragati_ros2/data/inputs/img100.jpg"
```

---

### 2. **scripts/launch/launch_complete_system.sh** (1 reference)
- Line 143: `YANTHRA_WORKING_CONFIG="/home/uday/Downloads/pragati_ros2/outputs/yanthra_move_ros2_working.yaml"`

**Change to**:
```bash
YANTHRA_WORKING_CONFIG="/home/uday/Downloads/pragati_ros2/data/outputs/yanthra_move_ros2_working.yaml"
```

---

### 3. **scripts/essential/SortCottonCoordinates.py** (4 references)
**Note**: Uses `/home/ubuntu/pragati/outputs/` (different path - ROS1 legacy?)

- Line 15: `InputFile = "/home/ubuntu/pragati/outputs/cotton_details.txt"`
- Line 16: `OutputFile = "/home/ubuntu/pragati/outputs/output.txt"`
- Line 17: `LogFile = "/home/ubuntu/pragati/outputs/aruco_points.log"`

**Decision needed**: 
- Is this script still used?
- Should it point to pragati_ros2 or is it for ROS1 compatibility?
- If updating: change to `/home/uday/Downloads/pragati_ros2/data/outputs/`

---

### 4. **scripts/validation/test_launch_simple.sh** (5 references)
- Line 67: `cp /home/uday/Downloads/pragati/outputs/Cotton*.txt /home/uday/Downloads/pragati_ros2/outputs/`
- Line 68: `cp /home/uday/Downloads/pragati/outputs/cotton_details.txt /home/uday/Downloads/pragati_ros2/outputs/`
- Line 69: `cp /home/uday/Downloads/pragati/outputs/aruco_points.log /home/uday/Downloads/pragati_ros2/outputs/`
- Line 74: `if [ -f "/home/uday/Downloads/pragati_ros2/outputs/$file" ]; then`
- Line 85: `YANTHRA_CONFIG="/home/uday/Downloads/pragati_ros2/outputs/yanthra_move_ros2_working.yaml"`

**Change all `pragati_ros2/outputs/` to `pragati_ros2/data/outputs/`**

---

## Migration Steps

### Step 1: Backup Current State
```bash
# Create backup of current data structure
tar -czf ~/pragati_ros2_data_backup_$(date +%Y%m%d).tar.gz inputs/ outputs/ data/
```

### Step 2: Remove Symlinks
```bash
cd /home/uday/Downloads/pragati_ros2
rm data/inputs data/outputs
```

### Step 3: Move Directories
```bash
mv inputs/ data/inputs/
mv outputs/ data/outputs/
```

### Step 4: Update All References
Apply the file changes listed above using sed or manual edits.

### Step 5: Verify
```bash
# Check all references are updated
grep -r "pragati_ros2/inputs" . --exclude-dir=build --exclude-dir=install --exclude-dir=log
grep -r "pragati_ros2/outputs" . --exclude-dir=build --exclude-dir=install --exclude-dir=log
# Should only show the updated paths with data/ in them
```

---

## Risk Assessment

**Low Risk**:
- Only ~12 hardcoded references to update
- All files are in test/validation scripts (not production code)
- Data files are small (~2MB total)
- Easy to rollback by reversing the steps

**Benefits**:
- Cleaner root directory structure
- Logical grouping of all data in one place
- Consistent path structure

---

## Files That Need Updates Summary

1. ✅ `test_suite/hardware/test_hsv_detection.py` - Update 2 paths
2. ✅ `scripts/launch/launch_complete_system.sh` - Update 1 path
3. ⚠️ `scripts/essential/SortCottonCoordinates.py` - Needs clarification (ROS1 paths)
4. ✅ `scripts/validation/test_launch_simple.sh` - Update 5 paths

**Total**: 8 clear updates + 3 uncertain (SortCottonCoordinates.py)

---

## Rollback Plan

If issues arise:
```bash
cd /home/uday/Downloads/pragati_ros2
mv data/inputs ./inputs
mv data/outputs ./outputs
cd data
ln -s ../inputs inputs
ln -s ../outputs outputs
# Revert file changes
git checkout test_suite/hardware/test_hsv_detection.py scripts/launch/launch_complete_system.sh scripts/validation/test_launch_simple.sh
```
