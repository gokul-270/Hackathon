# Camera FOV Improvement Tasks

**Date:** January 28, 2026  
**Status:** 🟡 In Progress  
**Owner:** Uday, Swetha

**📘 Implementation Plan:** See [FOV_IMPROVEMENT_IMPLEMENTATION_PLAN.md](./FOV_IMPROVEMENT_IMPLEMENTATION_PLAN.md) for detailed implementation tasks, configuration system, safety procedures, and testing protocols for Joint4 multi-position picking.

---

## 1. Current Issues

### 1.1 Vertical Camera Orientation
**Problem:** Camera is currently mounted **vertically**, resulting in:
- Narrow horizontal coverage
- Missing cotton bolls on the sides
- Reduced effective picking area per frame

### 1.2 Fixed Joint4 Position
**Problem:** Joint4 (left/right movement) is currently fixed at **center position (0)**
- Current range: [-0.125, 0.175] meters
- Actual usage: Only at 0.000 meters
- **Result:** Camera cannot scan left/right, limiting effective FOV

---

## 2. Proposed Solutions

### 2.1 Solution A: Horizontal Camera Mount

**Change:** Rotate camera mount 90° to horizontal orientation

| Metric | Vertical (Current) | Horizontal (Proposed) |
|--------|-------------------|----------------------|
| Horizontal FOV | ~45° | **~70°** |
| Vertical FOV | ~70° | ~45° |
| Cotton visible per frame | Limited | **Wider** |
| Good for | Tall plants | **Row scanning** |

#### Tasks for Horizontal Mount
- [ ] **HW-1:** Design/modify camera mount bracket
- [ ] **HW-2:** Install camera in horizontal orientation
- [ ] **HW-3:** Verify mechanical clearance with arm movement
- [ ] **SW-1:** Update URDF camera orientation
- [ ] **SW-2:** Recalibrate camera intrinsics
- [ ] **SW-3:** Update TF transforms
- [ ] **SW-4:** Test detection accuracy after orientation change
- [ ] **VAL-1:** Compare detection coverage: vertical vs horizontal

#### URDF Changes Required
```xml
<!-- File: src/robot_description/urdf/oak_d_lite_camera.xacro -->

<!-- Current (Vertical) -->
<origin xyz="0.02 0 0.01" rpy="0 0 0"/>

<!-- Proposed (Horizontal - rotate 90° around X axis) -->
<origin xyz="0.02 0 0.01" rpy="1.5708 0 0"/>  <!-- π/2 radians = 90° -->
```

#### Camera Info Update
After physical rotation, camera calibration may need update:
```yaml
# File: src/cotton_detection_ros2/config/production.yaml
camera:
  # Add orientation flag if needed
  orientation: "horizontal"  # or "vertical"
```

---

### 2.2 Solution B: Joint4 Multi-Position Picking

**Change:** Move Joint4 to ±100mm positions - detect and pick at EACH position (no merging needed)

**⚠️ IMPLEMENTATION:** This section describes the design rationale and theory. For practical implementation details, configuration system, safety verification procedures, and step-by-step tasks, see [FOV_IMPROVEMENT_IMPLEMENTATION_PLAN.md](./FOV_IMPROVEMENT_IMPLEMENTATION_PLAN.md).

**Current Configuration:**
```yaml
# File: src/yanthra_move/config/production.yaml
joint4:
  min: -0.125  # -125mm (left)
  max: 0.175   # +175mm (right)
  home: 0.000  # center (ALWAYS USED)
```

**Proposed Multi-Position Picking Pattern:**
```
        ←─── 100mm ───→│←─── 100mm ───→
                       │
    [POSITION 1]    [POSITION 2]    [POSITION 3]
        -100mm          0mm          +100mm
           │            │              │
           ▼            ▼              ▼
      [Detect]      [Detect]       [Detect]
           │            │              │
           ▼            ▼              ▼
     [Pick all]   [Pick all]     [Pick all]
      at -100mm    at 0mm         at +100mm
```

**Key Insight:** No merging required! Detect and pick ALL visible cotton at each Joint4 position before moving to next position.

#### ⚠️ SAFETY: Joint4 Movement Limits
**CRITICAL:** Must avoid Joint4 extreme positions that could cause collision with other parts!

```yaml
# Safe operating range (within mechanical limits)
joint4_safe:
  min: -0.100  # -100mm (stay away from -125mm limit)
  max: +0.100  # +100mm (stay away from +175mm limit)
  
# Collision zones to AVOID:
#   < -100mm: Risk of hitting left structure
#   > +100mm: Risk of hitting right structure (check actual clearance)
```

#### Tasks for Joint4 Multi-Position Picking
- [ ] **SW-5:** Add multi-position picking mode to yanthra_move
- [ ] **SW-6:** Implement position sequence: [-100, 0, +100] mm
- [ ] **HW-1:** Verify safe clearance at ±100mm positions
- [ ] **SW-7:** Add collision avoidance checks before Joint4 movement
- [ ] **VAL-2:** Measure coverage improvement with multi-position

#### Implementation Approach (RECOMMENDED: Detect-Pick at Each Position)

```python
def multi_position_picking():
    """
    Detect and pick at multiple Joint4 positions.
    NO MERGING - pick all cotton at each position before moving.
    """
    positions = [-0.100, 0.000, +0.100]  # meters (safe range)
    
    for j4_pos in positions:
        # Safety check before movement
        if not is_position_safe(j4_pos):
            logger.warning(f"Skipping unsafe position {j4_pos}")
            continue
        
        # Move Joint4 to position
        move_joint4(j4_pos)
        wait_for_position()
        
        # Detect cotton at this position
        detections = trigger_detection()
        
        if len(detections) == 0:
            logger.info(f"No cotton at J4={j4_pos}, moving to next position")
            continue
        
        # Pick ALL detected cotton at this position
        for cotton in detections:
            pick_cotton(cotton)  # Pick uses current J4 position
        
        logger.info(f"Picked {len(detections)} cotton at J4={j4_pos}")
    
    # Return to home position
    move_joint4(0.000)
```

**Advantages of Detect-Pick at Each Position:**
- Simpler implementation (no coordinate transformation between positions)
- No duplicate detection issues
- Camera-to-cotton position is always in same frame
- Picking accuracy maintained (no frame conversion errors)

---

### 2.3 Smart Border-Handling with Joint4

**Problem:** Cotton detected at image borders has:
- Partial visibility (incomplete detection)
- Inaccurate centroid (only part of cotton visible)
- May be rejected as `border_skip`

**Solution:** Use Joint4 to shift camera view and re-center border detections.

```
BEFORE (Cotton C at border):          AFTER (J4 shifted +75mm):
┌─────────────────────┐               ┌─────────────────────┐
│  A        B        │C               │        B        C   │
│  ●        ●        │●  ← BORDER     │        ●        ●   │ ← CENTERED!
│                    │                │                     │
└─────────────────────┘               └─────────────────────┘
```

#### Smart Border Detection Algorithm

```python
def smart_border_picking():
    """
    If cotton detected at border, shift J4 toward that border
    to re-center and re-detect before picking.
    """
    BORDER_THRESHOLD = 0.15  # 15% from edge = border zone
    J4_SHIFT = 0.075  # 75mm shift to re-center
    
    # First detection at center
    move_joint4(0)
    detections = trigger_detection()
    
    for cotton in detections:
        # Check if cotton is at border
        if cotton.x_normalized < BORDER_THRESHOLD:  # Left border
            shift_direction = -1  # Move J4 left
        elif cotton.x_normalized > (1 - BORDER_THRESHOLD):  # Right border
            shift_direction = +1  # Move J4 right
        else:
            # Cotton is centered enough - pick directly
            pick_cotton(cotton)
            continue
        
        # Shift J4 to bring border cotton to center
        new_j4 = shift_direction * J4_SHIFT
        if is_position_safe(new_j4):
            move_joint4(new_j4)
            
            # Re-detect with shifted view
            re_detections = trigger_detection()
            
            # Find same cotton (now hopefully centered)
            for re_cotton in re_detections:
                if not is_at_border(re_cotton):
                    pick_cotton(re_cotton)
                    break
        
    # Return to center for next cycle
    move_joint4(0)
```

#### Trial Sequence for Joint4 Distances

**Phase 1: Conservative (Start Here)**
```yaml
trial_1:
  positions: [-50, 0, +50]  # mm
  purpose: "Verify no collisions, measure coverage improvement"
  risk: LOW
  expected_improvement: ~15% more visible area
```

**Phase 2: Balanced (After Phase 1 passes)**
```yaml
trial_2:
  positions: [-75, 0, +75]  # mm
  purpose: "Better border coverage"
  risk: LOW-MEDIUM
  expected_improvement: ~25% more visible area
```

**Phase 3: Maximum Coverage (After mechanical verification)**
```yaml
trial_3:
  positions: [-100, -50, 0, +50, +100]  # mm
  purpose: "Full coverage with intermediate positions"
  risk: MEDIUM (verify clearance first!)
  expected_improvement: ~40% more visible area
```

#### Why This Helps Even with Horizontal Camera

| Camera Orientation | Primary Benefit | J4 Still Helps? |
|-------------------|-----------------|----------------|
| Vertical | Wider horizontal scan | ✅ YES |
| **Horizontal** | Wider horizontal FOV already | ✅ **YES** - still has left/right borders |

Horizontal mount increases FOV but doesn't eliminate borders. Joint4 movement:
1. Reaches cotton always at one edge of field
2. Re-centers border detections for accurate picking
3. Compensates for arm position relative to plant row

---

### 2.3 Combined Approach (BEST COVERAGE)

Implement BOTH horizontal mount AND Joint4 scanning:

```
              Horizontal Camera FOV (~70°)
        ┌─────────────────────────────────────┐
        │                                     │
        │    ┌───────┐                        │
        │    │  J4   │ ← Joint4 scanning      │
        │    │ -100  │   adds lateral         │
        │    └───┬───┘   coverage             │
        │        │                            │
        │    ┌───┴───┐                        │
        │    │  J4   │                        │
        │    │   0   │                        │
        │    └───┬───┘                        │
        │        │                            │
        │    ┌───┴───┐                        │
        │    │  J4   │                        │
        │    │ +100  │                        │
        │    └───────┘                        │
        │                                     │
        └─────────────────────────────────────┘
        
        Effective Coverage: ~120-150% of original
```

---

## 3. Implementation Checklist

### Phase 1: Lab Testing (Before Feb 25)
- [ ] Mount camera horizontally in lab
- [ ] Update URDF orientation parameters
- [ ] Run camera calibration
- [ ] Test detection accuracy
- [ ] Compare coverage metrics

### Phase 2: Joint4 Scanning
- [ ] Implement scan_and_detect() function
- [ ] Add configuration parameters:
  ```yaml
  fov_enhancement:
    scanning_enabled: true
    scan_positions: [-0.100, 0.000, 0.100]
    dedup_threshold: 0.05
  ```
- [ ] Test detection merging logic
- [ ] Measure cycle time impact

### Phase 3: Field Validation (Feb 25)
- [ ] Test horizontal mount in field conditions
- [ ] Verify detection under various lighting
- [ ] Measure picking success rate improvement
- [ ] Document any issues

---

## 4. Metrics to Measure

| Metric | Current | Target |
|--------|---------|--------|
| Horizontal coverage (degrees) | ~45° | ~70° |
| Cotton detected per frame | X | X + 30% |
| Effective scan area (cm²) | TBD | TBD + 50% |
| Detection cycle time (sec) | TBD | < 2× current |

---

## 5. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Horizontal mount reduces height coverage | Acceptable for typical cotton plant heights |
| Joint4 scanning increases cycle time | Only scan when needed (batch mode) |
| Detection duplicates from scanning | Implement robust deduplication |
| Calibration drift after mount change | Recalibrate; add periodic calibration check |

---

## 6. Joint4/Camera Kinematic Analysis

### 6.1 URDF Kinematic Chain

```
base_link
  └─ link1 (Joint1: Base rotation)
       └─ link2 (Joint2: Shoulder)
            └─ link3 (Joint3: Elbow)
                 └─ link4 (Joint4: Linear slide left/right)
                      └─ link5 (Joint5: Linear slide in/out)
                           └─ yanthra_link (Fixed link)
                                └─ camera_link (OAK-D Lite)
                                     └─ gripper_link (End effector)
```

**Key insight:** Camera is a **CHILD** of Joint4 in the kinematic chain. When Joint4 moves, the camera moves WITH it.

### 6.2 Transform Flow

```
When J4 moves from 0 to +100mm:

  BEFORE (J4=0):                    AFTER (J4=+100mm):
  
  base_link                         base_link
      │                                 │
      ▼                                 ▼
  [link4 at X=0]                   [link4 at X=+100mm]
      │                                 │
      ▼                                 ▼
  [camera at X=0]                  [camera at X=+100mm]
      │                                 │
      ▼                                 ▼
  [Cotton C visible               [Cotton C visible
   at pixel (640,360)]             at pixel (320,360)]
       ↑                                ↑
       └─ Same cotton, different pixel position!
```

### 6.3 Why TF System Handles This Correctly

The ROS2 TF2 system automatically updates all transforms when joints move:

```cpp
// In cotton_detection_node.cpp
auto cotton_in_camera = detection_result;  // Cotton position in camera_link frame

// TF2 looks up: camera_link → yanthra_link transform
// This transform ALREADY accounts for current J4 position!
auto cotton_in_robot = tf_buffer->transform(cotton_in_camera, "yanthra_link");
```

**The current code uses `tf2::TimePointZero` (latest transform):**
```cpp
tf_buffer_->transform(point_camera_frame, point_robot_frame, "yanthra_link", tf2::TimePointZero);
```

This is **CORRECT** behavior for single-position detection:
- Gets the most recent transform at time of lookup
- Camera_link → yanthra_link already includes J4's current position
- No manual offset calculation needed

### 6.4 ⚠️ CRITICAL: Multi-Position Picking Requirement

**WRONG approach (DO NOT DO THIS):**
```python
# WRONG! Old detections are invalid after J4 moves!
detections = []  # Accumulated list
for j4_pos in [-100, 0, +100]:
    move_joint4(j4_pos)
    detections += trigger_detection()  # ❌ Mixing different camera positions!

for cotton in detections:  # ❌ Which J4 position were these detected at?
    pick_cotton(cotton)    # ❌ Transforms will be WRONG!
```

**CORRECT approach (MUST RE-DETECT):**
```python
# CORRECT! Detect and pick at EACH position separately
for j4_pos in [-100, 0, +100]:
    move_joint4(j4_pos)
    wait_for_settling(50_ms)  # Let TF stabilize
    
    detections = trigger_detection()  # ✅ Fresh detection at THIS J4 position
    
    for cotton in detections:
        pick_cotton(cotton)  # ✅ Transform uses current J4 position
```

### 6.5 Detection Result Validity

| Scenario | Detection Valid? | Reason |
|----------|-----------------|--------|
| Detect at J4=0, Pick at J4=0 | ✅ YES | Same camera position |
| Detect at J4=0, Pick at J4=+100 | ❌ NO | Camera moved, transform invalid |
| Detect at J4=+100, Pick at J4=+100 | ✅ YES | Same camera position |
| Re-detect after J4 move | ✅ YES | Fresh transform at new position |

### 6.6 Timing Considerations

```
J4 Movement Timeline:

   t=0        t=50ms      t=100ms     t=150ms
    │           │           │           │
    ▼           ▼           ▼           ▼
[J4 move    [J4 arrives  [TF buffer   [Detection
 command     at target]   updated]     triggered]
 sent]                                     │
                                          ▼
                               [Cotton position in
                                yanthra_link frame
                                is NOW VALID]
```

**Recommended settling time:** 50-100ms after J4 reaches position before triggering detection.

### 6.7 Code Verification Checklist

Before implementing multi-position picking, verify:

- [ ] **VER-1:** Detection service returns positions in `camera_link` frame (not `yanthra_link`)
- [ ] **VER-2:** TF transform happens AFTER detection, not before
- [ ] **VER-3:** No caching of old detection results across J4 movements
- [ ] **VER-4:** Add settling delay between J4 move and detection trigger
- [ ] **VER-5:** Clear any pending detection results when J4 starts moving

### 6.8 Post-Pick Re-Detection Requirement

**Related requirement from:** `docs/requirements/COTTON_PICKING_POSITION_ACCURACY_REQUIREMENTS.md` (Section 2.2)

#### Why Re-Detect After Each Pick?

1. **Plant movement from pick action** - picking disturbs the plant, cotton positions shift
2. **Wind effects** - wind may have moved other cotton while arm was picking
3. **Validation** - confirm remaining cotton is still visible and reachable
4. **Position drift correction** - accumulated errors from multiple detections

#### Post-Pick Re-Detection Flow

```
Pick Cycle with Re-Detection:

  [Detect at J4 position]
         │
         ▼
  [Pick cotton #1]  ──────────────────────────────┐
         │                                         │
         ▼                                         │
  [Plant disturbed! Cotton positions shifted]      │
         │                                         │
         ▼                                         │ Wind may also
  [Wait 50-100ms for plant to settle]              │ move cotton
         │                                         │
         ▼                                         │
  [RE-DETECT] ◄────────────────────────────────────┘
         │
         ▼
  [Update remaining cotton positions]
         │
         ▼
  [Pick cotton #2 with FRESH position]
         │
         ▼
  [RE-DETECT again...]
```

#### Implementation Options

**Option A: Re-detect after EVERY pick (safest, slower)**
```python
for cotton in detected_list:
    pick_cotton(cotton)
    wait_for_plant_settling(100_ms)  # Let plant stabilize
    
    # Re-detect for remaining cotton
    detections = trigger_detection()
    if len(detections) == 0:
        break  # No more cotton visible
```

**Option B: Re-detect after N picks (balanced)**
```python
RE_DETECT_INTERVAL = 3  # Re-detect every 3 picks

for i, cotton in enumerate(detected_list):
    pick_cotton(cotton)
    
    if (i + 1) % RE_DETECT_INTERVAL == 0:
        wait_for_plant_settling(100_ms)
        detections = trigger_detection()
        # Update remaining positions from fresh detection
```

**Option C: Re-detect only when confidence low or wind detected (advanced)**
```python
for cotton in detected_list:
    pick_cotton(cotton)
    
    # Check if re-detection needed
    if wind_speed > THRESHOLD or pick_confidence < 0.7:
        wait_for_plant_settling(100_ms)
        detections = trigger_detection()
```

#### Combining with Multi-Position J4 Picking

```python
def multi_position_picking_with_redetect():
    """
    Full algorithm: Multi-J4 positions + re-detection after picks.
    """
    J4_POSITIONS = [-0.100, 0.000, +0.100]  # meters
    
    for j4_pos in J4_POSITIONS:
        move_joint4(j4_pos)
        wait_for_settling(50_ms)  # J4 settling
        
        detections = trigger_detection()  # Fresh detection at this J4
        
        for i, cotton in enumerate(detections):
            pick_cotton(cotton)
            
            # Re-detect after each pick at this J4 position
            # (Don't move J4 yet - still at same position)
            if i < len(detections) - 1:  # More cotton to pick at this position
                wait_for_plant_settling(50_ms)
                detections = trigger_detection()  # Update remaining positions
        
        logger.info(f"Completed J4={j4_pos}, moving to next position")
    
    move_joint4(0.000)  # Return home
```

#### Timing Budget Impact

| Strategy | Time per pick | Notes |
|----------|--------------|-------|
| No re-detection | ~2.0s | Fast but positions drift |
| Re-detect every pick | ~2.3s | +300ms for detection + settling |
| Re-detect every 3 picks | ~2.1s | Balanced approach |
| Re-detect on wind/low-conf | ~2.1s | Adaptive, requires wind sensor |

**Recommendation for Feb trial:** Start with re-detect after every pick (Option A) to gather data on position drift, then optimize based on field results.

### 6.9 Cotton Tracking / Association Problem

**The core question:** After re-detection, how do we know which cotton is "the same" cotton vs new/moved/gone?

#### Can YOLO's Built-in Tracking Help?

**Yes, YOLO has built-in multi-object tracking!** Ultralytics YOLOv11 (which we use) supports:
- **BoT-SORT** (default) - Better re-identification, handles camera motion
- **ByteTrack** - Faster, keeps low-confidence detections for occlusion handling

**Our current setup:**
- Model: `yolov11v2.blob` (2 classes: cotton + not_pickable)
- Runs on: DepthAI Myriad X VPU (OAK-D Lite)
- Input: 416x416 @ 30 FPS

```python
# YOLO tracking mode (continuous video) - Ultralytics Python API
from ultralytics import YOLO
model = YOLO("yolo11n.pt")  # YOLOv11
results = model.track(source="video.mp4", tracker="bytetrack.yaml")

# Output includes persistent track_id!
for result in results:
    for box in result.boxes:
        track_id = box.id  # Persistent across frames!
        confidence = box.conf
        position = box.xywh
```

**However, there's a critical limitation for our use case:**

| Requirement | YOLO Tracking | Our System |
|-------------|---------------|------------|
| Input | Continuous video stream | On-demand detection requests |
| Camera | Stationary or smooth motion | Camera moves WITH arm (J4) |
| Frame rate | 15-30 FPS continuous | ~1 frame per pick (2-3 seconds apart) |
| State persistence | Automatic between frames | Must persist across service calls |
| Motion model | Kalman filter (assumes smooth motion) | Arm movement is discrete/sudden |

**Why YOLO tracking won't work directly:**

1. **Non-continuous frames**: Our detections are 2-5 seconds apart (pick cycle time). Tracking algorithms expect continuous 30 FPS video - a 90-150 frame gap breaks the motion model.

2. **Camera moves with arm**: When J4 moves, the entire camera frame shifts 100-200mm. BoT-SORT has camera motion compensation, but expects gradual camera pan, not sudden discrete jumps.

3. **On-chip vs host tracking**: Our YOLO runs on DepthAI (Myriad X VPU) as a `.blob` file. Built-in tracking runs on host CPU and requires the Ultralytics Python API.

4. **Service-based detection**: Each detection is a fresh service call. YOLO tracking state doesn't persist between calls.

**Could we adapt YOLO tracking?**

```python
# Potential hybrid approach (NOT RECOMMENDED for Phase 1)
# Would require running YOLOv11 on HOST CPU instead of DepthAI VPU
class YOLOTrackerAdapter:
    def __init__(self):
        self.model = YOLO("yolo11n.pt")  # YOLOv11 - would run on CPU, not VPU!
        self.tracker_state = None  # Would need to persist this
    
    def detect_with_tracking(self, image):
        # Problem: track() expects video, not single frames
        # Would need to fake a "video" of detection frames
        results = self.model.track(
            source=image,
            persist=True,  # Persist tracker state
            tracker="bytetrack.yaml"
        )
        return results
```

**Verdict:** For Feb trial, use **spatial proximity matching** (simpler, more robust for our use case). Consider YOLO tracking for Phase 3 if we move to continuous detection mode.

#### Key Insight: Transform to World Frame for Matching

**The core problem:** Camera moves with J4, so pixel coordinates AND camera_link coordinates change between detections.

```
Detection 1 (J4=0):              Detection 2 (J4=+100mm):

camera_link frame:               camera_link frame:
  Cotton A at (0.3, 0.1, 0.5)      Cotton A at (0.3, 0.0, 0.5)  ← DIFFERENT!
  (30cm forward, 10cm left)        (30cm forward, 0cm left)
                                   
BUT in world frame (base_link):  BUT in world frame (base_link):
  Cotton A at (0.8, 0.1, 1.2)      Cotton A at (0.8, 0.1, 1.2)  ← SAME!
```

**Solution: Track in `base_link` (world) frame, not `camera_link`!**

```python
def transform_detection_to_world(detection_camera_frame, j4_position):
    """
    Transform detection from camera_link to base_link.
    This makes positions comparable across different J4 positions.
    """
    # TF2 lookup: camera_link -> base_link
    # Already includes current J4 position!
    transform = tf_buffer.lookup_transform('base_link', 'camera_link', Time(0))
    
    detection_world = tf2_geometry_msgs.do_transform_point(
        detection_camera_frame, transform)
    
    return detection_world


def associate_across_j4_positions(old_detections_world, new_detections_camera):
    """
    Match detections even when J4 has moved.
    
    Args:
        old_detections_world: Previous detections, already in base_link frame
        new_detections_camera: New detections in camera_link frame
    """
    # Transform new detections to world frame
    new_detections_world = [
        transform_detection_to_world(det) for det in new_detections_camera
    ]
    
    # Now we can compare in same coordinate frame!
    return associate_detections(old_detections_world, new_detections_world)
```

**Complete tracking flow with J4 movement:**

```
┌─────────────────────────────────────────────────────────────────┐
│ TRACKING WITH J4 MOVEMENT                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Detection at J4=0                                           │
│     ┌──────────────────────┐                                    │
│     │ camera_link positions │                                   │
│     │ Cotton A: (0.3,0.1)   │                                   │
│     │ Cotton B: (0.2,0.2)   │                                   │
│     └──────────┬───────────┘                                    │
│                │                                                 │
│                ▼ Transform to base_link                         │
│     ┌──────────────────────┐                                    │
│     │ base_link positions   │ ◄── STORE THIS for matching       │
│     │ Cotton A: (0.8,0.1)   │                                   │
│     │ Cotton B: (0.7,0.2)   │                                   │
│     └──────────────────────┘                                    │
│                                                                  │
│  2. Pick Cotton A, then J4 moves to +100mm                      │
│                                                                  │
│  3. Detection at J4=+100mm                                      │
│     ┌──────────────────────┐                                    │
│     │ camera_link positions │ ◄── Different from before!        │
│     │ Cotton B: (0.2,0.1)   │     (camera moved 100mm)          │
│     │ Cotton C: (0.1,0.3)   │     (new cotton visible)          │
│     └──────────┬───────────┘                                    │
│                │                                                 │
│                ▼ Transform to base_link                         │
│     ┌──────────────────────┐                                    │
│     │ base_link positions   │                                   │
│     │ Cotton B: (0.7,0.2)   │ ◄── MATCHES old Cotton B!         │
│     │ Cotton C: (0.6,0.4)   │ ◄── NEW (no match)                │
│     └──────────────────────┘                                    │
│                                                                  │
│  4. Association result:                                         │
│     - Cotton A: PICKED (not in new detection)                   │
│     - Cotton B: MATCHED (same position in base_link)            │
│     - Cotton C: NEW (no previous match)                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Critical implementation note:**
```cpp
struct TrackedCotton {
    uint32_t tracking_id;
    geometry_msgs::msg::PointStamped position_world;  // ALWAYS in base_link!
    // ...
};

void CottonTracker::update_from_detection(
    const std::vector<CottonPosition>& new_detections_camera,
    const std::string& detection_frame  // "camera_link"
) {
    // MUST transform to base_link before matching
    std::vector<geometry_msgs::msg::Point> new_detections_world;
    for (const auto& det : new_detections_camera) {
        auto world_pos = tf_buffer_->transform(
            det.position, "base_link", tf2::TimePointZero);
        new_detections_world.push_back(world_pos);
    }
    
    // Now association works correctly across J4 positions!
    associate(tracked_cotton_, new_detections_world);
}
```

#### Current System Limitation

```cpp
// In cotton_detection_node_publishing.cpp:64
cotton_pos.detection_id = static_cast<int32_t>(i);  // Just array index!
```

**Problem:** `detection_id` is just the array index (0, 1, 2...) for each detection frame. No persistence across frames!

```
Frame 1 Detection:          Frame 2 Detection (after pick):
  ID=0: Cotton A at (0.1, 0.2)    ID=0: Cotton B at (0.15, 0.25)  ← DIFFERENT cotton!
  ID=1: Cotton B at (0.2, 0.3)    ID=1: Cotton C at (0.3, 0.1)    ← NEW cotton!
  ID=2: Cotton C at (0.3, 0.1)    (Cotton A is GONE - picked)
```

#### Why This Matters

| Scenario | Risk Without Tracking |
|----------|----------------------|
| Pick cotton A, re-detect | May try to pick Cotton A again (now at different position) |
| Wind moves Cotton B | May think it's a new cotton, double-count |
| New cotton becomes visible | May confuse with existing cotton |
| Cotton goes out of view | May think it was picked when it wasn't |

#### Association Strategies

**Strategy 1: Spatial Proximity Matching (RECOMMENDED for Phase 1)**

```python
def associate_detections(old_detections, new_detections, threshold_m=0.05):
    """
    Match new detections to old ones based on spatial proximity.
    
    Args:
        old_detections: List of (id, x, y, z) from previous frame
        new_detections: List of (x, y, z) from current frame
        threshold_m: Max distance to consider same cotton (50mm default)
    
    Returns:
        matched: List of (old_id, new_detection) pairs
        new_cotton: List of new_detections that don't match any old
        disappeared: List of old_ids that have no match
    """
    matched = []
    new_cotton = []
    used_old_ids = set()
    
    for new_det in new_detections:
        best_match = None
        best_distance = float('inf')
        
        for old_id, old_det in old_detections:
            if old_id in used_old_ids:
                continue
            
            distance = euclidean_distance(old_det, new_det)
            if distance < threshold_m and distance < best_distance:
                best_match = old_id
                best_distance = distance
        
        if best_match is not None:
            matched.append((best_match, new_det))
            used_old_ids.add(best_match)
        else:
            new_cotton.append(new_det)
    
    disappeared = [old_id for old_id, _ in old_detections 
                   if old_id not in used_old_ids]
    
    return matched, new_cotton, disappeared
```

**Strategy 2: Spatial + Confidence Matching**

```python
def associate_with_confidence(old_dets, new_dets, pos_weight=0.7, conf_weight=0.3):
    """
    Match using both position AND confidence similarity.
    Useful when multiple cotton are close together.
    """
    for new_det in new_dets:
        scores = []
        for old_id, old_det in old_dets:
            pos_score = 1.0 - min(euclidean_distance(old_det.pos, new_det.pos) / 0.1, 1.0)
            conf_score = 1.0 - abs(old_det.confidence - new_det.confidence)
            
            combined = pos_weight * pos_score + conf_weight * conf_score
            scores.append((old_id, combined))
        
        best_match = max(scores, key=lambda x: x[1]) if scores else None
        # ... assign match
```

**Strategy 3: Visual Feature Matching (Advanced - Phase 3)**

```python
def associate_with_visual_features(old_dets, new_dets, image_old, image_new):
    """
    Use visual features (ORB, SIFT) to match cotton appearance.
    More robust to large movements but computationally expensive.
    """
    for old_det in old_dets:
        old_patch = extract_patch(image_old, old_det.bbox)
        old_features = compute_orb_features(old_patch)
        
        for new_det in new_dets:
            new_patch = extract_patch(image_new, new_det.bbox)
            new_features = compute_orb_features(new_patch)
            
            similarity = match_features(old_features, new_features)
            # ... match based on similarity threshold
```

#### Tracking State Machine

```
Cotton Lifecycle:

  [NEW]  ──detect──►  [TRACKED]  ──pick──►  [PICKED]
           │              │                     │
           │              │ (lost from view)    │
           │              ▼                     │
           │         [OCCLUDED]                 │
           │              │                     │
           │              │ (re-detected)       │
           │              ▼                     │
           └──────────[TRACKED]◄────────────────┘
                          │        (pick failed,
                          │         re-detected)
                          │
                     [UNREACHABLE]
                     (out of workspace)
```

#### Implementation for Feb Trial

```cpp
struct TrackedCotton {
    uint32_t tracking_id;           // Persistent ID across frames
    geometry_msgs::msg::Point position;
    float confidence;
    CottonState state;              // NEW, TRACKED, PICKED, OCCLUDED, UNREACHABLE
    int frames_since_seen;          // For timeout/cleanup
    int pick_attempts;              // Track failures
    rclcpp::Time first_detected;
    rclcpp::Time last_seen;
};

class CottonTracker {
    std::map<uint32_t, TrackedCotton> tracked_cotton_;
    uint32_t next_tracking_id_ = 1;
    
    const double ASSOCIATION_THRESHOLD_M = 0.05;  // 50mm
    const int MAX_FRAMES_OCCLUDED = 3;            // Remove after 3 frames not seen
    const int MAX_PICK_ATTEMPTS = 2;              // Give up after 2 failures
    
    void update_from_detection(const std::vector<Detection>& new_detections) {
        // 1. Associate new detections with existing tracked cotton
        auto [matched, new_cotton, disappeared] = associate_detections(
            get_tracked_positions(), new_detections, ASSOCIATION_THRESHOLD_M);
        
        // 2. Update matched cotton positions
        for (auto& [track_id, new_det] : matched) {
            tracked_cotton_[track_id].position = new_det.position;
            tracked_cotton_[track_id].confidence = new_det.confidence;
            tracked_cotton_[track_id].frames_since_seen = 0;
            tracked_cotton_[track_id].last_seen = now();
        }
        
        // 3. Handle disappeared cotton (increment occlusion counter)
        for (auto track_id : disappeared) {
            tracked_cotton_[track_id].frames_since_seen++;
            if (tracked_cotton_[track_id].frames_since_seen > MAX_FRAMES_OCCLUDED) {
                tracked_cotton_[track_id].state = CottonState::OCCLUDED;
            }
        }
        
        // 4. Add new cotton with fresh IDs
        for (auto& new_det : new_cotton) {
            TrackedCotton tc;
            tc.tracking_id = next_tracking_id_++;
            tc.position = new_det.position;
            tc.confidence = new_det.confidence;
            tc.state = CottonState::TRACKED;
            tc.frames_since_seen = 0;
            tc.pick_attempts = 0;
            tc.first_detected = tc.last_seen = now();
            tracked_cotton_[tc.tracking_id] = tc;
        }
        
        // 5. Cleanup old occluded cotton
        cleanup_stale_tracking();
    }
    
    void mark_picked(uint32_t tracking_id) {
        if (tracked_cotton_.contains(tracking_id)) {
            tracked_cotton_[tracking_id].state = CottonState::PICKED;
        }
    }
    
    void mark_pick_failed(uint32_t tracking_id) {
        if (tracked_cotton_.contains(tracking_id)) {
            tracked_cotton_[tracking_id].pick_attempts++;
            if (tracked_cotton_[tracking_id].pick_attempts >= MAX_PICK_ATTEMPTS) {
                tracked_cotton_[tracking_id].state = CottonState::UNREACHABLE;
            }
        }
    }
    
    std::vector<TrackedCotton> get_pickable_cotton() {
        std::vector<TrackedCotton> result;
        for (auto& [id, tc] : tracked_cotton_) {
            if (tc.state == CottonState::TRACKED) {
                result.push_back(tc);
            }
        }
        // Sort by confidence or distance
        std::sort(result.begin(), result.end(), 
                  [](const auto& a, const auto& b) { 
                      return a.confidence > b.confidence; 
                  });
        return result;
    }
};
```

#### Association Threshold Selection

| Threshold | Pros | Cons | Use When |
|-----------|------|------|----------|
| 30mm | Very precise matching | May lose track if wind moves cotton | Calm conditions |
| **50mm** | **Balanced (RECOMMENDED)** | **Good default** | **General use** |
| 75mm | Tolerates more movement | Risk of matching wrong cotton | Windy conditions |
| 100mm | Very tolerant | High risk of mis-association | Not recommended |

**Field calibration needed:** Observe actual cotton movement between picks in Feb trial.

#### Metrics to Log

```yaml
Tracking Metrics (per session):
  total_cotton_tracked: 150
  total_picked: 45
  total_pick_failures: 12
  total_lost_from_view: 20
  total_new_appeared: 35  # Cotton that appeared after J4 move or plant movement
  avg_frames_tracked: 3.2
  association_conflicts: 5  # Times when 2 old matched same new
  
Per-Cotton Metrics:
  tracking_id: 42
  lifetime_frames: 5
  position_drift_cm: 2.3  # Total movement from first detection
  pick_result: SUCCESS | FAIL | SKIPPED
```

### 6.10 Implementation Recommendation

Add state tracking to prevent stale detections:

```cpp
class MultiPositionPicker {
    std::optional<double> last_detection_j4_position_;
    rclcpp::Time last_detection_time_;
    bool pick_occurred_since_detection_ = false;
    
    bool is_detection_valid() {
        // Invalid if J4 moved
        if (!last_detection_j4_position_) return false;
        double current_j4 = get_current_j4_position();
        double j4_delta = std::abs(current_j4 - *last_detection_j4_position_);
        if (j4_delta > 0.005) return false;  // 5mm tolerance
        
        // Invalid if pick occurred (plant may have moved)
        if (pick_occurred_since_detection_) return false;
        
        // Invalid if too old
        auto age = (now() - last_detection_time_).seconds();
        if (age > 1.0) return false;  // 1 second staleness limit
        
        return true;
    }
    
    void on_j4_move_started() {
        last_detection_j4_position_ = std::nullopt;  // Invalidate!
    }
    
    void on_pick_completed() {
        pick_occurred_since_detection_ = true;  // Invalidate!
    }
    
    void on_detection_complete(double j4_at_detection) {
        last_detection_j4_position_ = j4_at_detection;
        last_detection_time_ = now();
        pick_occurred_since_detection_ = false;  // Fresh detection
    }
};
```

---

## 7. Code References

| Component | File |
|-----------|------|
| Camera URDF | `src/robot_description/urdf/oak_d_lite_camera.xacro` |
| Detection node | `src/cotton_detection_ros2/src/cotton_detection_node.cpp` |
| Arm control | `src/yanthra_move/src/yanthra_move_system.cpp` |
| Joint limits | `src/motor_control_ros2/config/production.yaml` |
| Camera config | `src/cotton_detection_ros2/config/production.yaml` |

---

## 7. Dependencies

- [ ] Horizontal mount bracket (hardware)
- [ ] Camera calibration board
- [ ] Access to test setup (arm + camera)
- [ ] Updated URDF merged to main branch

---

**Document Status:** Ready for review
**Last Updated:** January 28, 2026
