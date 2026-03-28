# ArUco Detection Optimization
**Goal**: Reduce detection time from 8s to 3-4s, improve accuracy from ±35mm to ±10mm

---

## Current Performance

- **Detection time**: ~8 seconds
- **Accuracy**: ±35mm variation between runs
- **Success rate**: 100% (4/4 corners)
- **Implementation**: Calls `/usr/local/bin/aruco_finder` binary

---

## Implementation

### Files to Modify

**Primary**: `src/pattern_finder/scripts/aruco_detect_oakd.py` OR `src/pattern_finder/src/aruco_finder.cpp`

Let's check which one is active and implement improvements.

### Improvement 1: Increase FPS (15 → 30)

```python
# Find camera FPS setting
camera.setFps(30)  # Change from 15 to 30
```

**Impact**: 2x faster frame acquisition  
**Time saved**: ~2-3 seconds

### Improvement 2: Adaptive Sampling

```python
# Current: Fixed 30 samples
SAMPLES = 30

# New: Adaptive with early termination
MIN_SAMPLES = 10
MAX_SAMPLES = 30
STABILITY_THRESHOLD_MM = 5.0  # Consider stable if <5mm std dev

samples = []
for i in range(MAX_SAMPLES):
    # Detect marker
    corners = detect_aruco_marker(frame)
    if corners is not None:
        samples.append(corners)
    
    # Early termination check
    if len(samples) >= MIN_SAMPLES:
        std_dev = np.std(np.array(samples), axis=0)
        std_dev_mm = np.linalg.norm(std_dev) * 1000  # Convert to mm
        
        if std_dev_mm < STABILITY_THRESHOLD_MM:
            print(f"[ArUco] Stable after {len(samples)} samples (std_dev={std_dev_mm:.1f}mm)")
            break

print(f"[ArUco] Collected {len(samples)} samples")
```

**Impact**: Typically need only 10-15 samples instead of 30  
**Time saved**: ~2-4 seconds

### Improvement 3: Outlier Rejection

```python
def reject_outliers(samples, threshold_sigma=3.0):
    """Remove samples more than threshold*std_dev from median"""
    samples = np.array(samples)
    if len(samples) < 3:
        return samples
    
    # Calculate median and distances
    median = np.median(samples, axis=0)
    distances = np.linalg.norm(samples - median, axis=1)
    
    # Remove outliers (>3 sigma)
    std = np.std(distances)
    if std > 0:
        mask = distances < (threshold_sigma * std)
        filtered = samples[mask]
        
        outliers_removed = len(samples) - len(filtered)
        if outliers_removed > 0:
            print(f"[ArUco] Removed {outliers_removed} outliers")
        
        return filtered
    
    return samples

# Apply before averaging
samples_filtered = reject_outliers(samples)
final_position = np.mean(samples_filtered, axis=0)
```

**Impact**: ±35mm → ±10-15mm accuracy

### Improvement 4: Weighted Averaging

```python
def weighted_average(samples):
    """Recent samples weighted more heavily"""
    samples = np.array(samples)
    n = len(samples)
    
    # Linear weights: 0.5 to 1.0
    weights = np.linspace(0.5, 1.0, n)
    weights = weights / np.sum(weights)  # Normalize
    
    return np.average(samples, axis=0, weights=weights)

# Use instead of simple mean
final_position = weighted_average(samples_filtered)
```

**Impact**: Better tracking of moving targets, faster convergence

### Improvement 5: Confidence Scoring

```python
class DetectionQuality:
    def __init__(self, samples, marker_area_pixels=None):
        self.samples = np.array(samples)
        self.n_samples = len(samples)
        self.std_dev = np.std(samples, axis=0)
        self.std_dev_mm = np.linalg.norm(self.std_dev) * 1000
        self.marker_area = marker_area_pixels
    
    def is_reliable(self):
        """Check if detection meets quality thresholds"""
        checks = []
        
        # Check 1: Enough samples
        checks.append(("samples", self.n_samples >= 10))
        
        # Check 2: Low variation
        checks.append(("variation", self.std_dev_mm < 20.0))
        
        # Check 3: Marker size (if available)
        if self.marker_area is not None:
            checks.append(("marker_size", self.marker_area > 1000))
        
        all_passed = all(check[1] for check in checks)
        
        if not all_passed:
            print(f"[ArUco] Quality checks: {checks}")
        
        return all_passed
    
    def get_summary(self):
        return {
            'samples': self.n_samples,
            'std_dev_mm': round(self.std_dev_mm, 2),
            'marker_area': self.marker_area,
            'reliable': self.is_reliable()
        }

# Use after detection
quality = DetectionQuality(samples_filtered, marker_area)
if quality.is_reliable():
    print(f"[ArUco] High quality detection: {quality.get_summary()}")
    # Use the position
else:
    print(f"[ArUco] Low quality detection: {quality.get_summary()}")
    # Maybe skip or retry
```

---

## Complete Implementation Example

```python
import numpy as np
from typing import Optional, List, Dict
import time

class OptimizedArucoDetector:
    def __init__(self):
        self.MIN_SAMPLES = 10
        self.MAX_SAMPLES = 30
        self.STABILITY_THRESHOLD_MM = 5.0
        self.FPS = 30  # Increased from 15
    
    def detect_marker_corners(self, marker_id: int = 23) -> Optional[List[Dict]]:
        """
        Detect ArUco marker corners with optimizations.
        
        Returns:
            List of corner positions [{x, y, z}, ...] or None if detection failed
        """
        start_time = time.time()
        
        # Initialize camera with higher FPS
        camera = self.init_camera()
        camera.setFps(self.FPS)
        
        samples = []
        frame_count = 0
        
        print(f"[ArUco] Starting detection for marker {marker_id}...")
        
        # Adaptive sampling loop
        for i in range(self.MAX_SAMPLES):
            frame = camera.get_frame()
            frame_count += 1
            
            # Detect marker
            corners = self.detect_in_frame(frame, marker_id)
            
            if corners is not None:
                samples.append(corners)
            
            # Early termination check
            if len(samples) >= self.MIN_SAMPLES:
                if self.is_stable(samples):
                    print(f"[ArUco] Stable after {len(samples)} samples ({frame_count} frames)")
                    break
        
        if not samples:
            print(f"[ArUco] No valid detections")
            return None
        
        # Post-processing
        samples_filtered = self.reject_outliers(samples)
        final_corners = self.weighted_average(samples_filtered)
        
        # Quality check
        quality = DetectionQuality(samples_filtered)
        
        elapsed = time.time() - start_time
        print(f"[ArUco] Detection complete in {elapsed:.2f}s")
        print(f"[ArUco] Quality: {quality.get_summary()}")
        
        if quality.is_reliable():
            return self.format_corners(final_corners)
        else:
            print(f"[ArUco] Warning: Low quality detection")
            return self.format_corners(final_corners)  # Still return but warn
    
    def is_stable(self, samples: List) -> bool:
        """Check if recent samples are stable"""
        if len(samples) < self.MIN_SAMPLES:
            return False
        
        recent = np.array(samples[-self.MIN_SAMPLES:])
        std_dev = np.std(recent, axis=0)
        std_dev_mm = np.linalg.norm(std_dev) * 1000
        
        return std_dev_mm < self.STABILITY_THRESHOLD_MM
    
    def reject_outliers(self, samples, threshold=3.0):
        """Remove outliers using median + std deviation"""
        samples = np.array(samples)
        if len(samples) < 3:
            return samples
        
        median = np.median(samples, axis=0)
        distances = np.linalg.norm(samples - median, axis=1)
        std = np.std(distances)
        
        if std > 0:
            mask = distances < (threshold * std)
            return samples[mask]
        
        return samples
    
    def weighted_average(self, samples):
        """Recent samples weighted more"""
        samples = np.array(samples)
        n = len(samples)
        weights = np.linspace(0.5, 1.0, n)
        weights = weights / np.sum(weights)
        return np.average(samples, axis=0, weights=weights)
    
    def format_corners(self, corners):
        """Convert to output format"""
        # Implementation depends on your format
        return corners
```

---

## Testing Plan

### Step 1: Measure Baseline
```bash
# Time current detection
time /usr/local/bin/aruco_finder

# Run 5 times, note:
# - Average time
# - Position variation
# - Success rate
```

### Step 2: Implement Optimizations
- Start with FPS increase (easiest, biggest impact)
- Add adaptive sampling
- Add outlier rejection
- Add weighted averaging
- Add quality scoring

### Step 3: Validate
```bash
# Time new detection
# Compare:
# - Time: Should be 3-4s (50%+ faster)
# - Accuracy: Should be ±10-15mm (2-3x better)
# - Reliability: Should still be 100%
```

---

## Expected Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Time** | 8s | 3-4s | 50-60% faster |
| **Accuracy** | ±35mm | ±10-15mm | 2-3x better |
| **Samples** | 30 fixed | 10-15 adaptive | 50-67% fewer |
| **FPS** | 15 | 30 | 2x throughput |

---

## Rollback

If optimizations cause issues:
```bash
# Backup current version
cp aruco_detect_oakd.py aruco_detect_oakd.py.before_optimization

# Revert if needed
cp aruco_detect_oakd.py.before_optimization aruco_detect_oakd.py
```

---

**Priority**: HIGH - Most visible performance improvement  
**Risk**: LOW - Early termination has safety checks  
**Testing**: Can test offline without hardware  
**Deploy**: After Phase 1 hardware test succeeds
