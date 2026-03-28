# Version Alignment Procedure

## Purpose

Maintain consistent package versions across multiple Raspberry Pi devices and development machines to prevent "works on my machine" issues.

## Problem Solved

In multi-device deployments, package version drift causes:
- Features work on one RPi but fail on another
- Difficult debugging ("why does RPi-ARM1 work but RPi-Old1 doesn't?")
- Unpredictable behavior in field trials
- Time wasted tracking down version mismatches

## Solution: Version Tracking System

1. **Single source of truth:** `/pragati_ros2/requirements.txt`
2. **Regular snapshots:** Capture actual installed versions from each device
3. **Automated validation:** Scripts check alignment before deployment
4. **Version tracking table:** Document known-good versions across fleet

## Workflow

### 1. Initial Baseline (One-Time Setup)

Capture configuration from your **known-working** RPi:

```bash
# On dev machine (or RPi)
./scripts/rpi_config_snapshot.sh rpi

# Output: log/rpi_snapshot_YYYYMMDD_HHMMSS.txt
```

Extract critical package versions:

```bash
./scripts/extract_rpi_versions.sh log/rpi_snapshot_*.txt
```

Update `requirements.txt` to match the baseline.

### 2. Adding a New RPi Device

When adding a new Raspberry Pi to the fleet:

**Step 1: Capture current state (before changes)**

```bash
./scripts/rpi_config_snapshot.sh ubuntu@<new_rpi_ip>
# Save as: log/rpi_snapshot_NewDevice_YYYYMMDD.txt
```

**Step 2: Compare with requirements**

```bash
./scripts/validate_requirements_vs_rpi.sh log/rpi_snapshot_NewDevice_*.txt
```

Expected output:
```
Package              Required           RPi Version     Status
------------------------------------------------------------
depthai              ==2.30.0.0         2.28.0.0        ❌ MISMATCH
opencv-python        >=4.11.0,<5.0      4.8.1.78        ❌ MISMATCH
numpy                >=1.26.0,<2.0      1.24.3          ⚠️  WARN
```

**Step 3: Align versions**

Option A - Update new RPi to match requirements (recommended):
```bash
# On new RPi
pip3 install -r ~/pragati_ros2/requirements.txt
```

Option B - Update requirements to match new RPi (if newer versions are acceptable):
```bash
# Update requirements.txt to allow both versions
# Then test thoroughly before deploying to fleet
```

**Step 4: Verify alignment**

```bash
./scripts/rpi_config_snapshot.sh ubuntu@<new_rpi_ip>
./scripts/validate_requirements_vs_rpi.sh log/rpi_snapshot_NewDevice_*.txt

# Should show all ✅ OK
```

**Step 5: Update version tracking table**

Edit `requirements.txt`, update the version table at the bottom:

```python
# Package       | requirements.txt  | RPi-ARM1   | RPi-New  | Status
# --------------|-------------------|------------|----------|--------
# depthai       | ==2.30.0.0        | 2.30.0.0   | 2.30.0.0 | ✅ OK
# opencv-python | >=4.11.0,<5.0     | 4.11.0.86  | 4.11.0.86| ✅ OK
```

### 3. Regular Audits

Perform quarterly or after major updates:

```bash
# Capture from all devices
./scripts/rpi_config_snapshot.sh rpi-arm1
./scripts/rpi_config_snapshot.sh rpi-arm2
./scripts/rpi_config_snapshot.sh rpi-old1

# Validate each
for snapshot in log/rpi_snapshot_*.txt; do
    echo "Checking $snapshot"
    ./scripts/validate_requirements_vs_rpi.sh "$snapshot"
done
```

### 4. Before Field Trials

**Critical:** Verify all devices are aligned before deployment:

```bash
# 1. Capture snapshots from all RPis in fleet
# 2. Validate against requirements.txt
# 3. Fix any mismatches
# 4. Commit snapshot files to git for audit trail
```

## Version Pinning Strategy

### Strict Pinning (==X.Y.Z.W)

Use for:
- **API-sensitive packages** (e.g., depthai camera SDK)
- Packages where minor version changes break code
- Hardware-specific libraries

Example:
```python
depthai==2.30.0.0  # Camera API changes between versions
```

### Relaxed Pinning (>=X.Y,<Z)

Use for:
- **Stable packages** (e.g., numpy, opencv)
- Libraries following semantic versioning
- Packages where patch updates are safe

Example:
```python
opencv-python>=4.11.0,<5.0  # Allow 4.11.x, block 5.0
numpy>=1.26.0,<2.0          # Allow 1.26.x, block 2.x
```

### Range Pinning (>=X,<Y)

Use for:
- Development dependencies
- Optional features
- Testing tools

## Multi-Device Scenarios

### Scenario 1: Upgrading All Devices

When a package needs upgrading across the fleet:

1. **Test on one device first**
   ```bash
   # On test RPi
   pip3 install depthai==2.31.0.0
   # Run full test suite
   ```

2. **Update requirements.txt if test passes**
   ```python
   depthai==2.31.0.0  # Updated from 2.30.0.0
   ```

3. **Deploy to remaining devices**
   ```bash
   for rpi in rpi-arm1 rpi-arm2; do
       ssh $rpi "pip3 install -r ~/pragati_ros2/requirements.txt"
   done
   ```

4. **Capture new snapshots**
   ```bash
   ./scripts/rpi_config_snapshot.sh rpi-arm1
   ./scripts/rpi_config_snapshot.sh rpi-arm2
   ```

### Scenario 2: Heterogeneous Fleet

If some devices must run different versions:

1. **Create device-specific requirements**
   ```
   requirements.txt           # Base requirements
   requirements-old-rpi.txt   # Overrides for older devices
   ```

2. **Document in version table**
   ```python
   # Package   | Base      | RPi-ARM1 (new) | RPi-Old1 (legacy) | Status
   # depthai   | ==2.30.0  | 2.30.0         | 2.28.0 (⚠️ legacy)| ⚠️  MIXED
   ```

3. **Test compatibility layer**
   - Ensure code works with both versions
   - Use feature detection instead of version checks

## Automation

### Pre-Deployment Check Hook

Add to `.git/hooks/pre-push`:

```bash
#!/bin/bash
echo "Validating Python dependencies..."
./scripts/validate_python_deps.sh || {
    echo "❌ Python dependency validation failed"
    exit 1
}
```

### Continuous Monitoring

Create a cron job on each RPi:

```bash
# Check weekly if versions match requirements
0 2 * * 0 /home/ubuntu/pragati_ros2/scripts/validate_requirements_vs_rpi.sh
```

## Version Tracking Table Format

Maintain in `requirements.txt` at bottom:

```python
################################################################################
# VERSION ALIGNMENT TRACKING
################################################################################
# Last Updated: YYYY-MM-DD HH:MM:SS
# Snapshot Source: log/rpi_snapshot_YYYYMMDD_HHMMSS.txt
#
# Package       | requirements.txt  | RPi-ARM1   | RPi-ARM2 | RPi-Old1 | Status
# --------------|-------------------|------------|----------|----------|--------
# depthai       | ==2.30.0.0        | 2.30.0.0   | 2.30.0.0 | 2.28.0   | ⚠️  OLD1
# opencv-python | >=4.11.0,<5.0     | 4.11.0.86  | 4.11.0.86| 4.8.1    | ⚠️  OLD1
# numpy         | >=1.26.0,<2.0     | 1.26.4     | 1.26.4   | 1.26.4   | ✅ OK
# pillow        | >=10.2.0,<11.0    | 10.2.0     | 10.2.0   | 10.2.0   | ✅ OK
#
# Status Legend:
#   ✅ OK - All devices aligned
#   ⚠️  WARN - Some devices outdated but functional
#   ❌ FAIL - Critical mismatch, needs immediate fix
################################################################################
```

## Best Practices

1. **Capture before changing:** Always snapshot before upgrading packages
2. **Test individually:** Test upgrades on one device before fleet rollout
3. **Document exceptions:** If devices must differ, document why in table
4. **Regular audits:** Check alignment quarterly or before major events
5. **Commit snapshots:** Keep snapshot history in git for audit trail
6. **Automate validation:** Run checks in CI/CD pipeline

## Troubleshooting

### Package Not Found in Snapshot

**Cause:** Package installed via apt, not pip  
**Solution:** Add to snapshot script or document in requirements.txt comments

### Version Validation False Positive

**Cause:** Simple string comparison doesn't handle all version formats  
**Solution:** Update `validate_requirements_vs_rpi.sh` with python-semver

### Cannot Update Old Device

**Cause:** Hardware limitations, old OS  
**Solution:** Mark as "legacy" in table, ensure code has compatibility layer

## Summary

The version alignment procedure ensures:
- ✅ Predictable behavior across devices
- ✅ Easier debugging (eliminate version drift as variable)
- ✅ Faster deployment (no "works on my machine" issues)
- ✅ Audit trail for compliance/troubleshooting
- ✅ Confidence in field trials
