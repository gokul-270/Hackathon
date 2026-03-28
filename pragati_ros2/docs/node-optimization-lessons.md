# Cross-Node Build Optimization Patterns

Lessons learned from optimizing `motor_control_ros2`. Apply these to other packages.

## 1. Header Modularization

**When to split:** Monolithic headers >300 lines with distinct logical groups.

**How:**
1. Map the `#include` dependency DAG for the header.
2. Identify leaf groups (types/enums, forward declarations, config structs).
3. Extract leaves into standalone headers first, then work up the DAG.
4. Provide a forwarding header that `#include`s all fragments — backward compatibility, zero migration cost.

**motor_control_ros2 example:** `motor_abstraction.hpp` (600+ lines) split into 5 headers:
- `motor_types.hpp` — enums, constants, POD structs
- `motor_config.hpp` — configuration structures
- `motor_interface.hpp` — abstract base class
- `motor_state.hpp` — state tracking
- `motor_abstraction.hpp` — forwarding header (includes all four above)

Downstream code that included `motor_abstraction.hpp` required zero changes.

## 2. System Header Isolation

**Rule:** Never include platform-specific system headers (`linux/can.h`, `linux/spi.h`, `linux/i2c-dev.h`) in public (installed) headers. They break cross-compilation and leak platform coupling.

**How:**
- Forward-declare system structs in headers: `struct can_frame;`
- Move the real `#include <linux/can.h>` into `.cpp` files only.
- If a system type appears in a public API signature, wrap it behind a project-owned type or use `void*` + accessor pattern.

**motor_control_ros2 example:** `generic_motor_controller.hpp` replaced `#include <linux/can.h>` with `struct can_frame;` forward declaration. The full include moved to `generic_motor_controller.cpp`.

## 3. CMake Modernization

**Problem:** Global `include_directories()` leaks include paths to every target and every downstream package. Silent cross-package coupling.

**Fix:**
```cmake
# Before (bad)
include_directories(include ${OTHER_PKG_INCLUDE_DIRS})

# After (good)
target_include_directories(my_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_include_directories(my_node PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/src
)
```

**Rules:**
- `PUBLIC` for library targets consumed by other packages.
- `PRIVATE` for executables and internal-only includes.
- Generator expressions (`$<BUILD_INTERFACE:...>`, `$<INSTALL_INTERFACE:...>`) ensure paths are correct for both build-tree and install-tree consumers.
- This catches accidental include leaks immediately — if a target doesn't declare a dependency, compilation fails instead of silently succeeding.

## 4. Precompiled Headers (PCH) — Tested & Reverted

**Status: NOT RECOMMENDED.** PCH was implemented for `motor_control_ros2` (precompiling
`rclcpp/rclcpp.hpp` and `nlohmann/json.hpp`) and measured. Results:

- PCH generation added ~8s upfront cost per target.
- Incremental compilation of individual `.cpp` files was ~1-2s faster per TU.
- **Net effect was negative** — total build time increased because the PCH generation
  cost exceeded the per-TU savings, especially with ccache already caching object files.
- PCH also complicates ccache interaction (cache key includes PCH hash, causing misses
  when any PCH input header changes).

**Conclusion:** With ccache enabled and `-j1` per-package parallelism, PCH provides no
net benefit. The optimization was reverted. Do not apply to other packages.

## 5. Link-Time Optimization (LTO) — Tested & Reverted

**Status: NOT RECOMMENDED.** LTO was implemented for `motor_control_ros2` using
`CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE`. Results:

- LTO identified dead code and enabled cross-TU inlining.
- **Link time increased dramatically** — from ~2s to ~15s per target on x86, worse on
  cross-compile where linking is already the bottleneck (37s for yanthra_move).
- Binary size reduction was negligible (~1-2%) for this project's scale.
- Incompatible with `mold` linker (falls back to `ld`, losing mold's speed advantage).

**Conclusion:** LTO's link-time penalty far exceeds any code-size or runtime benefit
for this project. The optimization was reverted. Do not apply to other packages.

## 6. Include Guard Hygiene

**Problem found:** `gpio_control_functions.hpp` had duplicate/nested include guards — an outer `#ifndef` wrapping an inner `#pragma once`, plus a stale guard from a copy-paste.

**Rule:** Use exactly one mechanism per header:
- `#pragma once` (preferred — simpler, no name collisions), OR
- `#ifndef PROJECT_PACKAGE_FILENAME_HPP` / `#define` / `#endif` guards.

Never both. Never duplicate. Duplicate guards silently mask missing includes.

## 7. Applicability Matrix

| Optimization | motor_control_ros2 | yanthra_move (~9.5k lines) | cotton_detection_ros2 (~6.2k lines) | odrive_control_ros2 (~3.5k lines) | common_utils |
|---|---|---|---|---|---|
| Header split | **Done** | Likely candidate — check for large headers | Probably already modular (pipeline stages) | Small enough — skip | Check shared headers |
| System header isolation | **Done** | Check for `linux/` includes (CAN, GPIO) | Check for `depthai/` in public headers | Check for `linux/can.h` exposure | N/A |
| CMake modernization | **Done** | Check for global `include_directories()` | Check | Check | Check — especially PUBLIC exports |
| PCH | Tested & Reverted | Not recommended | Not recommended | Not recommended | Not recommended |
| LTO | Tested & Reverted | Not recommended | Not recommended | Not recommended | Not recommended |
| Guard hygiene | **Done** | Audit all headers | Audit all headers | Audit all headers | Audit all headers |

## Priority Order for Next Package

1. **CMake modernization** — lowest risk, highest correctness impact.
2. **System header isolation** — fixes cross-compile failures.
3. **Header split** — only if a header is genuinely >300 lines.
4. **Guard hygiene** — quick grep audit: `grep -rn '#ifndef\|#pragma once' include/`.

> **PCH and LTO are not recommended.** Both were tested on motor_control_ros2 and reverted.
> See §4 and §5 above for details.
