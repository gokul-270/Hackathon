#!/usr/bin/env python3
"""Generate a Gazebo Harmonic SDF world file with a cotton plant field.

Produces a complete <sdf version="1.9"> world containing heightmap terrain,
boundary markers, an overhead camera, NavSat spherical coordinates, and a
configurable grid of cotton plant <include> elements with random height
variants, rotation, and scale jitter.

Usage examples:
    # Print to stdout with defaults (9 rows x 20 plants)
    python3 generate_cotton_field.py

    # Write to file with custom grid and fixed seed
    python3 generate_cotton_field.py --rows 12 --plants-per-row 30 \
        --row-spacing 1.0 --plant-spacing 0.60 --seed 42 \
        --output worlds/cotton_field_with_plants.sdf
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import textwrap
from typing import TextIO

# ---------------------------------------------------------------------------
# Plant variant pool (equal probability)
# ---------------------------------------------------------------------------
PLANT_VARIANTS = ["cotton_plant_small", "cotton_plant_medium", "cotton_plant_tall"]

# Scale jitter: +/-15 %
SCALE_MIN = 0.85
SCALE_MAX = 1.15


# ---------------------------------------------------------------------------
# Plant placement
# ---------------------------------------------------------------------------

def generate_plants(
    rows: int,
    plants_per_row: int,
    row_spacing: float,
    plant_spacing: float,
    rng: random.Random,
) -> list[dict]:
    """Return a list of plant dicts with keys: name, variant, x, y, yaw, scale."""

    # Centre the field at the origin
    x_offset = (plants_per_row - 1) * plant_spacing / 2.0
    y_offset = (rows - 1) * row_spacing / 2.0

    plants: list[dict] = []
    for r in range(rows):
        for p in range(plants_per_row):
            x = p * plant_spacing - x_offset
            y = r * row_spacing - y_offset
            yaw = rng.uniform(0, 2 * math.pi)
            scale = rng.uniform(SCALE_MIN, SCALE_MAX)
            variant = rng.choice(PLANT_VARIANTS)
            plants.append(
                {
                    "name": f"cotton_plant_r{r}_p{p}",
                    "variant": variant,
                    "x": x,
                    "y": y,
                    "yaw": yaw,
                    "scale": scale,
                }
            )
    return plants


# ---------------------------------------------------------------------------
# SDF generation helpers
# ---------------------------------------------------------------------------

def _plant_include(plant: dict) -> str:
    return (
        f"    <include>\n"
        f"      <name>{plant['name']}</name>\n"
        f"      <uri>model://{plant['variant']}</uri>\n"
        f"      <pose>{plant['x']:.4f} {plant['y']:.4f} 0 0 0 {plant['yaw']:.4f}</pose>\n"
        f"    </include>"
    )


def generate_world_sdf(plants: list[dict]) -> str:
    """Return the full SDF world XML string."""

    plant_includes = "\n\n".join(_plant_include(p) for p in plants)

    return textwrap.dedent("""\
<?xml version="1.0"?>
<sdf version="1.9">
  <world name="cotton_field">

    <!-- Physics -->
    <physics name="1ms" type="ignored">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>

    <!-- Plugins -->
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
      <render_engine>ogre2</render_engine>
    </plugin>
    <plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu"/>
    <plugin filename="gz-sim-navsat-system" name="gz::sim::systems::NavSat"/>

    <!-- Scene -->
    <scene>
      <ambient>0.8 0.8 0.8 1.0</ambient>
      <background>0.6 0.8 1.0 1</background>
      <sky></sky>
    </scene>

    <!-- Sun -->
    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.9 0.9 0.9 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
      <attenuation>
        <range>1000</range>
        <constant>0.9</constant>
        <linear>0.01</linear>
        <quadratic>0.001</quadratic>
      </attenuation>
      <direction>-0.5 0.1 -0.9</direction>
    </light>

    <!-- Heightmap Terrain (collision only) + visual ground plane -->
    <model name="terrain">
      <static>true</static>
      <link name="terrain_link">
        <collision name="terrain_collision">
          <geometry>
            <heightmap>
              <uri>file://field_heightmap.png</uri>
              <size>30 30 0.5</size>
              <pos>0 0 0</pos>
            </heightmap>
          </geometry>
        </collision>
        <visual name="terrain_visual">
          <geometry>
            <plane>
              <normal>0 0 1</normal>
              <size>30 30</size>
            </plane>
          </geometry>
          <material>
            <ambient>0.45 0.35 0.2 1</ambient>
            <diffuse>0.55 0.42 0.28 1</diffuse>
            <specular>0.1 0.1 0.1 1</specular>
          </material>
        </visual>
      </link>
    </model>

    <!-- Flat Ground Plane (fallback - uncomment if heightmap is unavailable)
    <model name="ground_plane">
      <static>true</static>
      <pose>0 0 0 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry>
            <plane>
              <normal>0 0 1</normal>
              <size>100 100</size>
            </plane>
          </geometry>
          <surface>
            <friction>
              <ode>
                <mu>1.0</mu>
                <mu2>1.0</mu2>
              </ode>
            </friction>
          </surface>
        </collision>
        <visual name="visual">
          <geometry>
            <plane>
              <normal>0 0 1</normal>
              <size>100 100</size>
            </plane>
          </geometry>
          <material>
            <ambient>0.4 0.3 0.2 1</ambient>
            <diffuse>0.5 0.4 0.3 1</diffuse>
            <specular>0.1 0.1 0.1 1</specular>
          </material>
        </visual>
      </link>
    </model>
    -->

    <!-- Field Boundary Markers -->

    <!-- START marker: green pole -->
    <model name="field_marker_start">
      <static>true</static>
      <pose>-10 0 0 0 0 0</pose>
      <link name="pole">
        <visual name="pole_visual">
          <pose>0 0 0.15 0 0 0</pose>
          <geometry>
            <cylinder>
              <radius>0.08</radius>
              <length>0.3</length>
            </cylinder>
          </geometry>
          <material>
            <ambient>0.1 0.7 0.1 1</ambient>
            <diffuse>0.2 0.8 0.2 1</diffuse>
          </material>
        </visual>
      </link>
    </model>

    <!-- END marker: red pole -->
    <model name="field_marker_end">
      <static>true</static>
      <pose>10 0 0 0 0 0</pose>
      <link name="pole">
        <visual name="pole_visual">
          <pose>0 0 0.15 0 0 0</pose>
          <geometry>
            <cylinder>
              <radius>0.08</radius>
              <length>0.3</length>
            </cylinder>
          </geometry>
          <material>
            <ambient>0.7 0.1 0.1 1</ambient>
            <diffuse>0.8 0.2 0.2 1</diffuse>
          </material>
        </visual>
      </link>
    </model>

    <!-- Spherical coordinates for NavSat (Ahmedabad, India) -->
    <spherical_coordinates>
      <surface_model>EARTH_WGS84</surface_model>
      <world_frame_orientation>ENU</world_frame_orientation>
      <latitude_deg>23.0225</latitude_deg>
      <longitude_deg>72.5714</longitude_deg>
      <elevation>53.0</elevation>
      <heading_deg>0</heading_deg>
    </spherical_coordinates>

    <!-- ============================================================ -->
    <!-- Cotton Plants                                                 -->
    <!-- ============================================================ -->

    """) + plant_includes + "\n\n  </world>\n</sdf>\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Gazebo Harmonic SDF cotton-field world."
    )
    parser.add_argument("--rows", type=int, default=9, help="Number of crop rows (default: 9)")
    parser.add_argument("--plants-per-row", type=int, default=20, help="Plants per row (default: 20)")
    parser.add_argument("--row-spacing", type=float, default=0.90, help="Row spacing in metres (default: 0.90)")
    parser.add_argument("--plant-spacing", type=float, default=0.70, help="Plant spacing in metres (default: 0.70)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--output", type=str, default=None, help="Output file path (default: stdout)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    rng = random.Random(args.seed)

    plants = generate_plants(
        rows=args.rows,
        plants_per_row=args.plants_per_row,
        row_spacing=args.row_spacing,
        plant_spacing=args.plant_spacing,
        rng=rng,
    )

    sdf = generate_world_sdf(plants)

    out: TextIO
    if args.output:
        out = open(args.output, "w", encoding="utf-8")
    else:
        out = sys.stdout

    try:
        out.write(sdf)
    finally:
        if out is not sys.stdout:
            out.close()

    if args.output:
        print(f"Wrote {len(plants)} plants to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
