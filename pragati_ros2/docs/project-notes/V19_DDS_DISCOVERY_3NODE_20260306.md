# V19 DDS Discovery 3-Node Test Report

**Date:** 2026-03-06, 11:44 - 12:33 IST
**Duration:** 48 minutes 37 seconds (2 x 15-min phases + setup/teardown)
**Test script:** `scripts/diagnostics/test_dds_discovery_3node.sh`
**Overall result:** PASS

## Test Environment

| Node    | IP               | Hardware   | OS                  | RMW                  |
|---------|------------------|------------|---------------------|----------------------|
| vehicle | 192.168.137.203  | RPi 4B     | Ubuntu 24.04 ARM64  | rmw_cyclonedds_cpp   |
| arm1    | 192.168.137.12   | RPi 4B     | Ubuntu 24.04 ARM64  | rmw_cyclonedds_cpp   |
| arm2    | 192.168.137.238  | RPi 4B     | Ubuntu 24.04 ARM64  | rmw_cyclonedds_cpp   |

**Network:** Windows Mobile Hotspot (192.168.137.x subnet), Wi-Fi
**ROS2 distribution:** Jazzy
**DDS implementation:** CycloneDDS (no custom XML config)

## Phase 1: Shared-Domain Discovery (15 min)

**Configuration:** All nodes on `ROS_DOMAIN_ID=0`, `ROS_LOCALHOST_ONLY=0`
**Purpose:** Verify DDS can discover topics across all 3 RPis on the same network

Each node publishes a heartbeat topic:
- `/dds_test/vehicle/heartbeat`
- `/dds_test/arm1/heartbeat`
- `/dds_test/arm2/heartbeat`

Every 30 seconds, each node is checked for visibility of all 3 topics.

### Results

| Metric              | Value |
|---------------------|-------|
| Checks performed    | 30    |
| Discovery issues    | 0     |
| **Verdict**         | **PASS** |

All 3 nodes discovered all 3 topics at every single check (30/30), from 15s through 885s.

### Phase 1 Detail Log (topic list per node per check)

```
[vehicle @ 15s] topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[arm1 @ 15s]    topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[arm2 @ 15s]    topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[vehicle @ 45s] topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[arm1 @ 45s]    topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[arm2 @ 45s]    topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[vehicle @ 75s] topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[arm1 @ 75s]    topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[arm2 @ 75s]    topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[vehicle @ 105s] topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[arm1 @ 105s]    topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[arm2 @ 105s]    topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[vehicle @ 135s] topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[arm1 @ 135s]    topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
[arm2 @ 135s]    topics: /dds_test/arm1/heartbeat, /dds_test/arm2/heartbeat, /dds_test/vehicle/heartbeat
... (checks 6-30 identical: all nodes see 3/3 topics at every interval through 885s)
```

**Full detail:** Every check from 15s to 885s showed all 3 nodes discovering all 3 topics.
No discovery timeouts, no missing topics, no transient failures across the entire 15 minutes.

## Phase 2: Production Isolation (15 min)

**Configuration:**
- vehicle: `ROS_DOMAIN_ID=0`, `ROS_LOCALHOST_ONLY=0`
- arm1: `ROS_DOMAIN_ID=1`, `ROS_LOCALHOST_ONLY=1`
- arm2: `ROS_DOMAIN_ID=2`, `ROS_LOCALHOST_ONLY=1`

**Purpose:** Verify production domain isolation prevents cross-domain topic bleed.
Each node should only see its own heartbeat topic (1 topic, not 3).

### Results

| Metric                       | Value |
|------------------------------|-------|
| Checks performed             | 30    |
| Cross-domain bleed events    | 0     |
| Internal discovery failures  | 0     |
| **Verdict**                  | **PASS** |

### Phase 2 Detail Log (topic count per node per check)

```
[15s]  v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[45s]  v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[75s]  v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[105s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[135s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[165s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[195s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[225s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[255s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[285s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[315s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[345s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[375s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[405s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[435s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[465s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[495s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[525s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[555s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[585s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[615s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[645s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[675s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[705s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[735s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[765s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[795s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[825s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[855s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
[885s] v=1(/dds_test/vehicle/heartbeat) a1=1(/dds_test/arm1/heartbeat) a2=1(/dds_test/arm2/heartbeat)
```

Every node saw exactly 1 topic (its own) at every check for the full 15 minutes.
Zero cross-domain bleed. Domain isolation is solid.

## Final Summary

```
Phase 1 (shared-domain):       PASS  (30/30 checks, 0 discovery issues)
Phase 2 (production-isolation): PASS  (30/30 checks, 0 bleed events)

OVERALL: PASS - V19 DDS Discovery 3-Node Test passed
  - Network supports cross-node DDS discovery (Phase 1)
  - Production domain isolation holds without bleed (Phase 2)
```

## Conclusions

1. **CycloneDDS multicast discovery works reliably** across 3 RPi 4Bs on a Wi-Fi hotspot network over 15 continuous minutes with zero failures.
2. **Production isolation (separate ROS_DOMAIN_ID + ROS_LOCALHOST_ONLY=1)** completely prevents cross-domain topic bleed over 15 continuous minutes.
3. **DDS discovery is not a risk for the March field trial.** The network and DDS stack are stable for multi-node operation.
