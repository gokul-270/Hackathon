# CottonSim vs Pragati: Detailed Comparison

**Date**: 2026-02-12
**Paper**: "CottonSim: A vision-guided autonomous robotic system for cotton harvesting in Gazebo simulation"
**Published in**: Computers and Electronics in Agriculture, Volume 239, Part C, December 2025
**DOI**: https://doi.org/10.1016/j.compag.2025.110963
**Authors**: Thayananthan et al., University of Georgia / Mississippi State University
**Code**: https://github.com/imtheva/CottonSim

---

## Executive Summary

Both systems target **autonomous cotton harvesting** using **ROS + computer vision + YOLO**, but represent fundamentally different approaches:
- **CottonSim**: Simulation-first research framework with strong navigation but **zero picking capability**
- **Pragati**: Hardware-first production system with sophisticated picking but **navigation under development**

The two projects are almost perfectly complementary. CottonSim's biggest future work item (picking) is Pragati's biggest strength, and CottonSim's biggest strength (autonomous navigation) is Pragati's current development focus.

---

## 1. Robot Platform & Hardware

| Aspect | CottonSim | Pragati |
|--------|-----------|---------|
| **Base platform** | Clearpath Husky A200 (commercial UGV, ~$20k+) | Custom-built vehicle (cost-effective) |
| **Dimensions** | 990 x 670 x 390 mm, 75kg payload | Custom chassis |
| **Drive system** | 4 high-torque motors (differential/skid-steer) | Ackermann/three-wheel steering |
| **Robotic arm** | UR5e (6-DOF, 5kg payload, 850mm reach, ~$35k) | Custom 5-DOF arm (MG6010-i6 motors, CAN bus) |
| **End effector** | **Not implemented** (planned for future work) | **Vacuum-based capture** with GPIO-controlled compressor |
| **Battery** | 24V 20Ah sealed lead acid (3-5 hrs) | Not specified |
| **Compute** | Dell Precision 7920 workstation (Xeon Gold, RTX A6000, 187GB RAM) | **Raspberry Pi 4** (edge deployment) |
| **Estimated hardware cost** | ~$60k+ (Husky + UR5e + Velodyne + 3x RealSense + Vision-RTK) | Significantly lower (custom build) |

**Key insight**: CottonSim uses expensive commercial hardware but only in simulation. Pragati uses low-cost custom hardware and actually runs on it. CottonSim explicitly states the **cotton-picking algorithm is planned for future study** -- they cannot actually pick cotton yet, even in simulation.

---

## 2. Sensor Suite

| Sensor | CottonSim | Pragati |
|--------|-----------|---------|
| **RGB-D cameras** | 3x Intel RealSense (front, left, right) | 1x OAK-D Lite (front-facing) |
| **3D LIDAR** | Velodyne VLP-16 (~$4k) | None currently |
| **GPS/GNSS** | Fixposition Vision-RTK (RTK-GNSS + CV + IMU fusion) | RTK-GPS available (integration planned for autonomous stage) |
| **IMU** | Yes (integrated in Husky) | Available, interface coded (integration planned) |
| **Neural inference** | GPU-based (RTX A6000) | **On-device Myriad X VPU** (30 FPS, edge inference) |
| **Motor feedback** | Simulated joint states | Real CAN bus: position, velocity, torque, temperature |

**Notes**: Pragati has RTK-GPS and IMU hardware available for the upcoming autonomous navigation phase. The sensor gap is smaller than it initially appears.

### Improvement opportunities:
- Add at least one side-facing camera for bilateral cotton detection while traversing rows (CottonSim's 3-camera approach covers both sides)
- Integrate RTK-GPS and IMU into the ROS 2 pipeline for the autonomous stage
- Consider adding a 2D LIDAR (e.g., RPLidar A1, ~$100) for obstacle detection and SLAM

---

## 3. Computer Vision & AI

| Aspect | CottonSim | Pragati |
|--------|-----------|---------|
| **Detection model** | YOLOv8n (3.2M params) | YOLOv11 (compiled to .blob for VPU) |
| **Task type** | Object detection (cotton bolls) + Instance segmentation (scene) | Object detection only (2 classes: cotton, not_pickable) |
| **Scene segmentation** | YOLOv8n-seg (3 classes: sky, ground, cotton plants) | None |
| **Segmentation use** | Navigation assistance -- computing row center from mask intersection lines | N/A |
| **Detection dataset** | 40 images (26 train, 6 val, 8 test) -- simulation only | Real-world data (size not formally reported) |
| **Segmentation dataset** | 80 images -> 193 after augmentation (173 train, 16 val, 4 test) | N/A |
| **Inference speed** | ~126.8 ms/image (GPU workstation) | ~134 ms service latency (VPU edge device, 30 FPS) |
| **Input resolution** | Not specified | 416x416 pixels |
| **Spatial accuracy** | Not reported | ±10mm at 0.6m (stereo depth) |
| **Detection metrics** | mAP 92.7%, Precision 94.8%, Recall 87.2% (cotton bolls) | Not formally benchmarked |
| **Segmentation metrics** | mAP 85.2%, Precision 93.0%, Recall 88.9% (all classes) | N/A |

**Key insight**: CottonSim's datasets are extremely small (40 images for detection, 80 for segmentation) and entirely from simulated environments. Their high metrics are partly because the virtual environment is uniform -- they acknowledge real-world conditions would be far harder. Pragati trains on real-world images, which is inherently more challenging but more valuable.

### Improvement opportunities:
1. **Add scene segmentation** for navigation -- CottonSim's most innovative contribution. Train a YOLOv11-seg model on 3 classes (sky, ground, cotton plants) and use mask intersections to compute row center for autonomous steering
2. **Formally benchmark** detection performance (mAP, precision, recall, F1) on a held-out test set -- essential for any publication
3. **Consider instance segmentation** for cotton -- masks give better grasp point estimation than bounding boxes
4. **Publish real-world dataset** -- far more valuable than CottonSim's simulated images

---

## 4. Navigation System

| Aspect | CottonSim | Pragati |
|--------|-----------|---------|
| **GPS navigation** | GPS -> UTM -> map coordinate conversion, 100% CR | RTK-GPS available, integration planned |
| **Map-based navigation** | SLAM (gmapping) + AMCL + move_base, 96.7% CR | Planned for autonomous stage |
| **Global path planner** | navfn/NavfnROS | Planned (Nav2) |
| **Local path planner** | DWA (dwa_local_planner) | Planned (Nav2) |
| **Costmap** | costmap_2d with LIDAR data | Planned |
| **Visual guidance** | Segmentation-based row centering (sky/ground mask intersection -> steering correction, max 5° turn) | None for navigation currently |
| **Obstacle avoidance** | LIDAR-based costmap | Planned |
| **Autonomous traversal** | Full farm traversal: enter row -> traverse -> exit -> turn -> next row | Fixed forward/backward distance in current auto mode |
| **Speed** | 1.8 km/hr average | Not reported |
| **Traversal time** | GPS: 20m42s, Map: 31m07s for entire 9-row farm | N/A |
| **Navigation metrics** | AE, RMSE, Completion Rate (formally defined with equations) | Not yet defined |

**This is the primary development focus for the next stage.** CottonSim has a complete autonomous navigation stack. With the RTK-GPS and IMU hardware already available, Pragati is well-positioned to close this gap.

### CottonSim's navigation approach (for reference):
1. **GPS-based**: GPS coords (lat/lon) -> UTM conversion -> map frame transform -> move_base goals
2. **Map-based**: gmapping SLAM -> AMCL localization -> move_base with navfn + DWA
3. **Visual guidance**: YOLOv8n-seg segments sky/ground/plants -> mask intersection computes row center -> steering correction (max 5°)
4. **Traversal pattern**: Start at SE corner -> serpentine through all rows (E to W) -> end at SW corner

### Implementation plan for Pragati:
1. Integrate RTK-GPS into ROS 2 topic pipeline (navsat_transform_node)
2. Integrate IMU for odometry fusion (robot_localization package)
3. Implement Nav2 stack (equivalent to move_base in ROS 2)
4. Add vision-based row centering using segmentation
5. Define formal evaluation metrics (CR, AE, RMSE)

---

## 5. Arm Control & Picking Strategy

| Aspect | CottonSim | Pragati |
|--------|-----------|---------|
| **Arm DOF** | 6-DOF (UR5e) | 5-DOF (custom MG6010) |
| **Picking algorithm** | **NOT IMPLEMENTED** ("planned for future study") | **Fully implemented** with multiple strategies |
| **Picking strategies** | None | NEAREST_FIRST, PHI_SWEEP, HIERARCHICAL, RASTER_SCAN |
| **Energy optimization** | None | Weighted joint energy costs (J3=10x, J4=3x, J5=1x) |
| **Multi-position scanning** | None | J4 scans 5 lateral positions [-100mm to +100mm] for 60% more FoV coverage |
| **Coordinate transforms** | None (arm just sits on robot) | Full pipeline: camera -> yanthra_origin -> link3/4/5 frames |
| **Reachability checking** | None | Yes, verified before motion execution |
| **Phi compensation** | None | 3-zone piecewise linear correction for mechanical error |
| **End effector** | Not designed | Vacuum-based capture with GPIO-controlled compressor |
| **Safety systems** | Simulation (no physical safety needed) | Temperature (70°C), current (15A), position limits, e-stop, watchdogs |

**Pragati is dramatically ahead in picking capability.** CottonSim acknowledges this is their biggest limitation -- they explicitly state the picking mechanism is future work. Pragati's cotton picking optimizer with energy-efficient path planning, multi-position scanning, and phi-angle compensation is novel and publishable.

---

## 6. Simulation Environment

| Aspect | CottonSim | Pragati |
|--------|-----------|---------|
| **Virtual farm** | Full 3D cotton field (9 rows x 20 plants, 1233.97 m² farm area) | Basic Gazebo launch files, no cotton field model |
| **Plant models** | Detailed 3D meshes from CGTrader, imported via Blender | None |
| **Row spacing study** | Tested 10 spacings (1.0m to 1.9m), settled on 1.80m | N/A |
| **Collision modeling** | Branch, leaf, dead-leaf collision elements with friction (μ1=100, μ2=50) | N/A |
| **Sensor simulation** | Full camera, LIDAR, GPS, IMU simulation in Gazebo | `use_simulation:=true` with mock hardware fallbacks |

### Improvement opportunities:
- Build a virtual cotton field in Gazebo with realistic cotton plant models for testing the full detection -> picking pipeline
- Simulate the OAK-D Lite camera in Gazebo for end-to-end vision testing
- Test navigation algorithms in simulation before deploying to hardware

---

## 7. Software Engineering & Deployment

| Aspect | CottonSim | Pragati |
|--------|-----------|---------|
| **ROS version** | ROS 1 Noetic (EOL, final ROS 1 release) | **ROS 2 Jazzy** (modern, actively maintained) |
| **Build system** | catkin_make | colcon + ament_cmake/python + CMakePresets |
| **Testing** | Not mentioned | **218 unit tests**, 100% pass rate |
| **CI/CD** | Not mentioned | **GitHub Actions** workflows |
| **Pre-commit hooks** | Not mentioned | Yes, code quality tools |
| **Web dashboard** | None | **FastAPI + WebSocket** real-time monitoring |
| **Remote control** | None | **MQTT bridge** + web dashboard |
| **Deployment target** | Desktop workstation only | **Raspberry Pi 4** + systemd services |
| **Cross-compilation** | Not applicable | Supported for Pi 4 |
| **Git commits** | 10 total | Active development |

**Pragati is significantly more mature** in software engineering practices.

---

## 8. Research & Publication Readiness

| Aspect | CottonSim | Pragati |
|--------|-----------|---------|
| **Publication** | Peer-reviewed journal (Computers & Electronics in Agriculture, IF ~8.3) | None yet |
| **Formal evaluation** | Defined metrics with quantitative results | Metrics not formally reported |
| **Open-source** | BSD-3-Clause, public GitHub | Private repository |
| **Datasets released** | Yes (detection + segmentation) | No |
| **Trained weights** | Yes | No |
| **Reproducibility** | Full instructions, launch files, datasets | Not publicly available |

### For future publication, Pragati's unique contributions:
1. Real-hardware edge deployment (Pi 4 + Myriad X VPU) vs. expensive workstation simulation
2. Full cotton picking pipeline with multi-strategy optimizer
3. Energy-efficient path optimization for battery-constrained agricultural robots
4. Vacuum-based end effector with real-world cotton capture
5. 218 unit tests + CI/CD on ROS 2 (software engineering rigor)
6. Real-world detection data vs. simulated environments

---

## Prioritized Improvement Roadmap

### Tier 1 -- Critical (Close the gap with CottonSim, enable publication)

| # | Improvement | Effort | Impact |
|---|-------------|--------|--------|
| 1 | **Autonomous navigation stack** (RTK-GPS + IMU + Nav2 + row following) | High | Enables field-scale autonomy -- our primary current gap |
| 2 | **Formal detection benchmarks** (mAP, precision, recall on test set) | Low | Required for any publication |
| 3 | **Vision-based row centering** (scene segmentation -> steering correction) | Medium | Novel approach adaptable from CottonSim |

### Tier 2 -- Important (Exceed CottonSim)

| # | Improvement | Effort | Impact |
|---|-------------|--------|--------|
| 4 | **Integrate RTK-GPS** into ROS 2 pipeline | Medium | Enables GPS waypoint navigation |
| 5 | **Enable IMU** in ROS 2 pipeline | Low | Better odometry and heading |
| 6 | **Add side-facing camera** for bilateral detection | Medium | Covers both sides of row |
| 7 | **Gazebo virtual cotton field** for simulation testing | Medium | Safe testing of navigation + picking pipeline |

### Tier 3 -- Differentiators (Unique strengths to highlight in publications)

| # | Strength | Publication angle |
|---|----------|-------------------|
| 8 | Real hardware on edge device (Pi 4 + Myriad X VPU) | vs. CottonSim's ~$60k+ workstation simulation |
| 9 | Full picking pipeline with optimizer | CottonSim has zero picking capability |
| 10 | Energy-efficient path optimization (HIERARCHICAL strategy) | Novel for battery-constrained agricultural robots |
| 11 | 218 unit tests + CI/CD on ROS 2 | Software engineering rigor for agricultural robotics |
| 12 | Vacuum-based end effector with real field data | Physical cotton capture mechanism |

---

## CottonSim's Own Acknowledged Limitations

From their Discussion and Future Work sections:
1. **No picking algorithm** -- "The cotton-picking algorithm for this robot is planned to be implemented in our future study"
2. **Simulation-only validation** -- "real-farm conditions would introduce additional complexities"
3. **Small datasets** -- 40 images for detection, 80 for segmentation (simulated only)
4. **Uniform virtual environment** -- "plant arrangement was kept uniformly spaced, which reduced realism"
5. **Odometry/GPS drift issues** -- "waypoint positions had to be manually estimated"
6. **High computational demands** -- Requires RTX A6000 GPU workstation
7. **No real-world testing** -- Physical robot shown in field photos but not tested autonomously
8. **ROS 1 only** -- Using Noetic (EOL), no ROS 2 support

---

## Conclusion

**Pragati should implement autonomous navigation (GPS + Nav2 + vision-based row centering) to become a superset of CottonSim** -- everything they can do (navigate) plus everything they can't (actually pick cotton), on real hardware instead of simulation, using modern ROS 2 instead of EOL ROS 1.

With RTK-GPS and IMU hardware already available, the autonomous navigation stage is well-positioned for success. The complementary strengths suggest that combining CottonSim's navigation approach with Pragati's picking capabilities would create a truly complete autonomous cotton harvesting system.
