# Agricultural Field Terrain - Cotton Field World

## Terrain Features

The cotton field simulation includes **realistic agricultural terrain** with:

### 🌍 Ground Features

1. **Heightmap-based Terrain** (20m × 20m)
   - Height variation: 0 to 50cm (realistic field undulation)
   - 512×512 pixel resolution for smooth terrain

2. **Natural Slopes**
   - Main drainage slope: 2-3° (left to right)
   - Cross-slope: ~1° (front to back)
   - Mimics real field drainage patterns

3. **Undulations**
   - Gentle hills and depressions
   - Created with multi-frequency sine waves
   - Natural ground variation

4. **Drainage Furrows**
   - Small channels between crop rows
   - ~3cm deep, 20cm wide
   - Positioned at each crop row location

### 🌾 Crop Layout

**Row Positions** (0.45m spacing):
- Row 7: y = -0.675m
- Row 6: y = -0.225m
- **Right Wheel**: y = 0.0m 🔵
- **Row 1**: y = 0.225m ⭐ (between right & front wheels)
- **Front Wheel**: y = 0.45m 🔵
- **Row 2**: y = 0.675m ⭐ (between front & left wheels)
- **Left Wheel**: y = 0.9m 🔵
- Row 3: y = 1.125m
- Row 4: y = 1.575m
- Row 5: y = 2.025m

Each row:
- 20m length
- 0.3m wide raised bed
- 0.3m tall green plants

### 🚜 Testing Capabilities

**The terrain tests:**
- ✅ Wheel traction on slopes
- ✅ Stability on uneven ground
- ✅ Steering precision with terrain variation
- ✅ Speed control on inclines
- ✅ Row-following accuracy despite undulations

### 🔧 Customization

**Regenerate heightmap:**
```bash
cd ~/steering\ control/vehicle_control/scripts
python3 generate_field_heightmap.py
```

**Parameters to adjust** (in `generate_field_heightmap.py`):
- `max_height_m`: Total height variation (default: 0.5m)
- `slope_gradient`: Main slope steepness
- `furrow_depth`: Drainage channel depth (default: 3cm)
- Sine wave frequencies: Control undulation pattern

### 📊 Heightmap Details

- **Format**: 16-bit PNG
- **White pixels**: Higher elevation
- **Black pixels**: Lower elevation
- **Location**: `vehicle_control/worlds/field_heightmap.png`
- **Preview**: `field_heightmap_preview.png` (8-bit for viewing)

### 🎮 Launch

```bash
# Build and run
cd ~/steering\ control && colcon build && source install/setup.bash
ros2 launch vehicle_control gazebo.launch.py

# With Ackermann steering
ros2 launch vehicle_control gazebo.launch.py ackermann:=true
```

## Real-World Accuracy

This terrain simulates typical agricultural field conditions:
- **Slope**: 2-3° is standard for field drainage
- **Undulation**: 10-50cm variations common in natural fields
- **Furrows**: Realistic drainage channels between rows
- **Row spacing**: 0.45m matches tighter cotton/vegetable spacing

The robot must handle these challenges just like in real field operations!
