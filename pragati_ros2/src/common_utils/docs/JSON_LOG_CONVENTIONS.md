# JSON Structured Logging Conventions

## Purpose

All Pragati ROS2 nodes emit structured JSON log lines for field-trial instrumentation.
Structured logging gives us:

- **Machine-parseable output** consumed by `scripts/log_analyzer/` for automated
  post-trial analysis (timing regressions, anomaly detection, topology mapping).
- **Consistent field names** across C++ (`json_logging.hpp`) and Python
  (`vehicle_control/utils/logging_utils.py`) so a single parser handles both.
- **Unit-explicit fields** that are self-documenting — no ambiguity about whether a
  duration is seconds or milliseconds.

Every JSON log line is a single `nlohmann::json` (C++) or `dict` (Python) object printed
on one line via `RCLCPP_INFO` / `RCLCPP_WARN` or Python `logging.info`.

---

## Envelope Fields

Every JSON log line **must** include these top-level fields:

| Field    | Type    | Description                                                        |
|----------|---------|--------------------------------------------------------------------|
| `event`  | string  | Event type, `snake_case` (e.g. `detection_frame`, `motor_alert`)   |
| `ts`     | integer | UTC epoch time in **milliseconds**                                 |
| `node`   | string  | ROS2 node name (e.g. `mg6010_controller`, `cotton_detection_node`) |
| `arm_id` | string  | Arm identifier from `ARM_ID` env var; default `"arm_unknown"`      |

**C++ helper** — `pragati::json_envelope(event, node_name, arm_id)` in
`common_utils/include/common_utils/json_logging.hpp` returns a `nlohmann::json`
pre-populated with these four fields.

---

## Common Domain Fields

Use these field names wherever the concept applies. Physical quantities always carry
a **unit suffix** so the meaning is unambiguous.

| Field             | Type          | Unit / Range  | Description                    |
|-------------------|---------------|---------------|--------------------------------|
| `motor_id`        | int           | —             | CAN motor ID                   |
| `joint_id`        | int           | 0-5           | Joint index                    |
| `can_id`          | int           | —             | CAN bus address                |
| `current_a`       | float         | amps          | Motor current draw             |
| `temp_c`          | float         | celsius       | Temperature reading            |
| `duration_ms`     | float         | milliseconds  | Duration / elapsed time        |
| `voltage_v`       | float         | volts         | Voltage reading                |
| `angle_deg`       | float         | degrees       | Angular position or offset     |
| `fps`             | float         | frames/sec    | Camera or processing framerate |
| `confidence`      | float         | 0.0 - 1.0     | Detection confidence score     |

---

## Naming Rules

1. **All field names use `snake_case`.**
   - Good: `motor_id`, `duration_ms`, `from_state`
   - Bad: `motorId`, `Duration_MS`, `fromState`

2. **Physical quantities include a unit suffix.**

   | Suffix  | Unit         | Example        |
   |---------|--------------|----------------|
   | `_a`    | amps         | `current_a`    |
   | `_c`    | celsius      | `temp_c`       |
   | `_ms`   | milliseconds | `duration_ms`  |
   | `_v`    | volts        | `voltage_v`    |
   | `_deg`  | degrees      | `angle_deg`    |
   | `_mps`  | meters/sec   | `velocity_mps` |
   | `_mm`   | millimeters  | `distance_mm`  |

3. **Boolean fields use `is_` prefix.**
   - `is_overtemp`, `is_stalled`, `is_calibrated`

4. **Count fields use `_count` suffix.**
   - `detection_count`, `retry_count`, `error_count`

5. **State / enum fields are plain strings.**
   - `from_state`, `to_state`, `status`, `severity`

---

## Event Types

Known event types and the packages that emit them:

| Event                          | Source Package           | Description                                     |
|--------------------------------|--------------------------|-------------------------------------------------|
| `motor_alert`                  | `motor_control_ros2`     | Safety monitor threshold violation               |
| `motor_health`                 | `motor_control_ros2`     | Periodic motor health snapshot                   |
| `motor_command`                | `vehicle_control`        | Motor command issued (position/velocity)         |
| `interlock_rejection`          | `motor_control_ros2`     | Command rejected by safety interlock             |
| `detection_frame`              | `cotton_detection_ros2`  | Per-frame detection results                      |
| `detection_idle`               | `cotton_detection_ros2`  | Detection node idle (no input frames)            |
| `detection_summary`            | `cotton_detection_ros2`  | Aggregated detection statistics                  |
| `pick_complete`                | `yanthra_move`           | Single cotton pick cycle completed               |
| `cycle_complete`               | `yanthra_move`           | Full pick-and-return motion cycle completed      |
| `pick_cycle_timeout`           | `yanthra_move`           | Pick cycle exceeded time limit                   |
| `invalid_detection_coordinates`| `yanthra_move`           | Detection coordinates failed validation          |
| `state_transition`             | `vehicle_control`        | Vehicle state machine transition                 |
| `timing`                       | `common_utils`           | Generic operation timing measurement             |
| `health_summary`               | `common_utils`           | Component health status report                   |
| `startup_timing`               | (various)                | Node startup duration breakdown                  |
| `shutdown_timing`              | (various)                | Node shutdown duration                           |
| `mqtt`                         | (various)                | MQTT inter-arm message event                     |

> **Adding a new event?** Add a row to this table and follow the envelope + naming rules
> above. Keep event names as `snake_case` verb-noun or noun phrases.

---

## Examples

### C++ — Motor health snapshot

```cpp
#include <common_utils/json_logging.hpp>

auto j = pragati::json_envelope("motor_health", this->get_logger().get_name(), arm_id_);
j["motor_id"] = 1;
j["joint_id"] = 0;
j["temp_c"] = 45.2;
j["current_a"] = 1.8;
j["voltage_v"] = 24.1;
j["is_overtemp"] = false;
RCLCPP_INFO(this->get_logger(), "%s", j.dump().c_str());
```

### C++ — Motor alert (convenience helper)

```cpp
pragati::emit_motor_alert(
    this->get_logger(), "warning", "over_current",
    "J2", "current exceeds threshold", 3.5, 3.0, "reduce_torque");
```

### Python — State transition

```python
import json, time

event = {
    "event": "state_transition",
    "ts": int(time.time() * 1000),
    "node": "vehicle_controller",
    "arm_id": os.environ.get("ARM_ID", "arm_unknown"),
    "from_state": "IDLE",
    "to_state": "AUTONOMOUS",
    "trigger": "start_command",
    "transition_ms": 12.3,
}
self.get_logger().info(json.dumps(event))
```
