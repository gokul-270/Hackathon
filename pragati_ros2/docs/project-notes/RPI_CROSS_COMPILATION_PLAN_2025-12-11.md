# RPi Cross-Compilation Plan (Draft)

**Date:** 2025-12-11  
**Status:** Draft – implementation in progress, opt-in only (does not affect existing builds)

## 1. Goals and Constraints

- Build aarch64 (Raspberry Pi) binaries on x86 dev machine.
- Deploy to RPi without compiling heavy C++ (DepthAI, cotton_detection, yanthra_move) on the Pi.
- **Do not break** existing native builds:
  - x86 builds using `build.sh` and `colcon` must behave exactly as before.
  - RPi native builds using `build.sh arm` / `build.sh vehicle` must keep working.
- Cross-compilation is an **optimization only** – if it fails, we must still be able to:
  - Build on PC natively for x86.
  - Build on RPi natively with `./build.sh arm` / `./build.sh vehicle`.

## 2. High-Level Design

### 2.1 Toolchain and Sysroot

We will use a standard GCC aarch64 cross-compiler on the x86 dev machine, plus a sysroot copied from the RPi:

- **Toolchain:** `aarch64-linux-gnu-gcc`, `aarch64-linux-gnu-g++` (Ubuntu packages).
- **Sysroot:** Mirror of Pi libraries and headers, including:
  - `/usr` and `/lib` from the Pi
  - `/opt/ros/jazzy` from the Pi (target ROS installation)
  - Any additional libs needed by DepthAI, pigpio, etc.

The sysroot will live on the dev machine at:

- Default: `/opt/rpi-sysroot`  
- Overridable via `RPI_SYSROOT` environment variable.

### 2.2 CMake Toolchain File

We introduce a **single, opt-in** CMake toolchain file:

- Path: `cmake/toolchains/rpi-aarch64.cmake`
- Only used when explicitly passed via `-DCMAKE_TOOLCHAIN_FILE=...`.
- Responsibilities:
  - Tell CMake we are targeting `Linux` + `aarch64`.
  - Point C and C++ compilers to `aarch64-linux-gnu-gcc/g++`.
  - Point include/library resolution to the RPi sysroot.
  - Set **portable** optimization flags (no `-march=native`).

This file will **not** be referenced from any existing `CMakeLists.txt` or default presets, so native builds are unaffected.

### 2.3 Cross-Build Output Layout

To keep architectures separated:

- Native x86 builds continue to use the default `build/` and `install/` directories.
- Cross builds will be directed to a dedicated install prefix, e.g. `install_rpi/`.

This avoids mixing x86 and aarch64 artifacts inside the same `install/` tree.

### 2.4 Deployment to RPi

Deployment is a separate, explicit step using `rsync` or `scp`:

- From x86 dev machine:
  - Sync `install_rpi/` to `~/pragati_ros2/install/` on the RPi.
- On the RPi:
  - `source install/setup.bash`
  - Run existing launch files as usual.

This reuses the same runtime layout as native builds; only the origin of the binaries changes.

## 3. Detailed Steps

### 3.1 Prepare Sysroot (One-Time / Occasional)

On x86 dev machine (run once, update when RPi packages change):

1. Create base directory:
   ```bash
   sudo mkdir -p /opt/rpi-sysroot
   sudo chown "$USER" /opt/rpi-sysroot
   ```

2. From the RPi (replace `<PI_IP>` with actual IP):
   ```bash
   # On x86 dev machine
   RSYNC_PI="ubuntu@<PI_IP>"
   SYSROOT="/opt/rpi-sysroot"

   rsync -a --delete $RSYNC_PI:/usr/  $SYSROOT/usr/
   rsync -a --delete $RSYNC_PI:/lib/  $SYSROOT/lib/
   rsync -a --delete $RSYNC_PI:/opt/ros/jazzy/ $SYSROOT/opt/ros/jazzy/
   ```

3. Optionally export `RPI_SYSROOT` in your shell profile:
   ```bash
   export RPI_SYSROOT=/opt/rpi-sysroot
   ```

> Note: These commands **do not run on the Pi** – they are run from x86, pulling files over SSH.

### 3.2 Install Cross Toolchain on x86

On x86 dev machine:

```bash
sudo apt-get update
sudo apt-get install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu
```

This should not affect native builds; it only installs extra compilers.

### 3.3 CMake Toolchain File Usage

Once `cmake/toolchains/rpi-aarch64.cmake` is in place (see separate section), cross-build is opt-in:

```bash
cd ~/Downloads/pragati_ros2
source /opt/ros/jazzy/setup.bash   # x86 ROS, for colcon/ament tools only

colcon build \
  --install-base install_rpi \
  --merge-install \
  --cmake-args \
    -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/rpi-aarch64.cmake \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS="-O3 -DNDEBUG"
```

Key properties:

- Does **not** change default `build.sh` behavior.
- Only runs when explicitly invoked with the toolchain flag.

### 3.4 Deploy Cross-Built Artifacts to RPi

On x86 dev machine, after a successful cross build:

```bash
cd ~/Downloads/pragati_ros2
rsync -avz --delete install_rpi/ ubuntu@<PI_IP>:/home/ubuntu/pragati_ros2/install/
```

On the RPi:

```bash
ssh ubuntu@<PI_IP>
cd ~/pragati_ros2
source install/setup.bash

# Then run existing launch commands, e.g.:
ros2 launch yanthra_move pragati_complete.launch.py use_simulation:=false continuous_operation:=true
```

This should behave exactly like a native build from the Pi’s point of view.

## 4. Safety and Non-Regression

To avoid breaking anything that currently works:

- We **do not** modify:
  - Any existing `CMakeLists.txt` files.
  - The default behavior of `build.sh` on x86 or RPi.
  - The layout of `build/` and `install/` for native builds.
- We **only add**:
  - A new toolchain file: `cmake/toolchains/rpi-aarch64.cmake`.
  - This planning document.
- All cross-build commands are **opt-in**:
  - If they fail, you can immediately fall back to:
    - `./build.sh arm` / `./build.sh vehicle` on RPi.
    - `./build.sh fast` / `./build.sh full` on x86.

## 5. Implementation Checklist

1. [x] Document high-level plan (this file).
2. [ ] Add `cmake/toolchains/rpi-aarch64.cmake` with safe defaults (no -march=native).
3. [ ] Manually test cross-build for a **single small package** (e.g. `common_utils`) before touching cotton_detection.
4. [ ] Cross-build full ARM stack (`motor_control_ros2`, `cotton_detection_ros2`, `yanthra_move`) into `install_rpi/`.
5. [ ] Deploy to RPi and verify runtime against existing launch flows.
6. [ ] If stable, optionally add small helper commands (documentation-only or minimal wrapper) for convenience.

## 6. Notes / Open Questions

- Sysroot synchronization frequency: how often will the Pi’s libraries change?  
  For now, assume **manual refresh when packages are upgraded on the Pi**.
- CI integration: once stable, we may add a CI job that runs the same cross-build command on a clean sysroot.
- RPi5 support: same toolchain and sysroot approach should work, but we will validate on current RPi model first.
