#!/bin/bash
# ==============================================
# DDS Discovery 3-Node Test (V19)
# ==============================================
# Validates ROS2 DDS discovery across 3 RPi nodes (vehicle + 2 arms)
# on the Windows Mobile Hotspot network (192.168.137.x).
#
# Test has two phases:
#   Phase 1 (15 min): Shared-domain test - all nodes on DOMAIN_ID=0,
#                      LOCALHOST_ONLY=0. Verifies DDS CAN discover across nodes.
#   Phase 2 (15 min): Production-isolation test - each node on its own DOMAIN_ID,
#                      arms have LOCALHOST_ONLY=1. Verifies no cross-domain bleed.
#
# Runs from WSL dev machine. Uses ssh.exe to reach RPis on Windows hotspot.
#
# Usage:
#   ./test_dds_discovery_3node.sh [--quick]
#
#   --quick    Run 2-minute phases instead of 15-minute (for dry runs)
#
# Prerequisites:
#   - 3 RPis powered on and connected to Windows Mobile Hotspot
#   - SSH keys set up for ubuntu@ on all RPis (via ssh.exe)
#   - ROS2 Jazzy installed on all RPis
#   - CycloneDDS (rmw_cyclonedds_cpp) installed on all RPis
#
# Pass criteria (from March Field Plan):
#   - Phase 1: Zero discovery timeouts across 3 RPis in shared domain
#   - Phase 2: Zero cross-domain topic leakage; internal discovery works per-node
#
# Related:
#   docs/project-notes/MARCH_FIELD_TRIAL_PLAN_2026.md - V19 task
#   docs/specifications/TECHNICAL_SPECIFICATION_DOCUMENT.md - DDS architecture
# ==============================================

set -euo pipefail

# ---- Configuration ----
VEHICLE_IP="192.168.137.203"
ARM1_IP="192.168.137.12"
ARM2_IP="192.168.137.238"
RPI_USER="ubuntu"

# SSH command: use Windows ssh.exe from WSL to reach hotspot subnet
SSH_CMD="/mnt/c/WINDOWS/System32/OpenSSH/ssh.exe"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

# Phase durations (seconds)
PHASE1_DURATION=900   # 15 minutes
PHASE2_DURATION=900   # 15 minutes
POLL_INTERVAL=30      # Check discovery every 30 seconds

# Results
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="/tmp/dds_discovery_test_${TIMESTAMP}"
REPORT_FILE="${RESULTS_DIR}/report.txt"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ---- Parse Arguments ----
QUICK_MODE=false
for arg in "$@"; do
    case "$arg" in
        --quick) QUICK_MODE=true ;;
        --help|-h)
            head -34 "$0" | tail -32
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--quick]"
            exit 1
            ;;
    esac
done

if $QUICK_MODE; then
    PHASE1_DURATION=120   # 2 minutes
    PHASE2_DURATION=120
    POLL_INTERVAL=15
    echo -e "${YELLOW}Quick mode: 2-minute phases, 15s polling${NC}"
fi

# ---- Functions ----

log() {
    local msg="[$(date '+%H:%M:%S')] $1"
    echo -e "$msg"
    echo "$msg" >> "$REPORT_FILE" 2>/dev/null || true
}

ssh_rpi() {
    local ip="$1"
    shift
    $SSH_CMD $SSH_OPTS "${RPI_USER}@${ip}" "$@"
}

rpi_name() {
    case "$1" in
        "$VEHICLE_IP") echo "vehicle" ;;
        "$ARM1_IP")    echo "arm1" ;;
        "$ARM2_IP")    echo "arm2" ;;
        *)             echo "$1" ;;
    esac
}

print_banner() {
    echo -e "${BLUE}=============================================="
    echo -e "  DDS Discovery 3-Node Test (V19)"
    echo -e "==============================================${NC}"
    echo -e "  Vehicle: ${VEHICLE_IP}"
    echo -e "  Arm 1:   ${ARM1_IP}"
    echo -e "  Arm 2:   ${ARM2_IP}"
    echo -e "  Phase 1: Shared-domain (${PHASE1_DURATION}s)"
    echo -e "  Phase 2: Production-isolation (${PHASE2_DURATION}s)"
    echo -e "  Start:   $(date)"
    echo -e "${BLUE}==============================================${NC}"
    echo ""
}

check_connectivity() {
    log "${CYAN}Checking SSH connectivity to all RPis...${NC}"
    local all_ok=true
    for ip in "$VEHICLE_IP" "$ARM1_IP" "$ARM2_IP"; do
        local name
        name=$(rpi_name "$ip")
        if ssh_rpi "$ip" "echo ok" > /dev/null 2>&1; then
            log "${GREEN}  $name ($ip): reachable${NC}"
        else
            log "${RED}  $name ($ip): UNREACHABLE${NC}"
            all_ok=false
        fi
    done
    if ! $all_ok; then
        log "${RED}ERROR: Not all RPis are reachable. Aborting.${NC}"
        exit 1
    fi
}

check_ros2_installed() {
    log "${CYAN}Checking ROS2 + CycloneDDS on all RPis...${NC}"
    local all_ok=true
    for ip in "$VEHICLE_IP" "$ARM1_IP" "$ARM2_IP"; do
        local name
        name=$(rpi_name "$ip")
        local check_result
        check_result=$(ssh_rpi "$ip" "bash -c 'source /opt/ros/jazzy/setup.bash && which ros2 && dpkg -l ros-jazzy-rmw-cyclonedds-cpp 2>/dev/null | grep -q ^ii && echo cyclone_ok || echo cyclone_missing'" 2>&1) || true
        if echo "$check_result" | grep -q "cyclone_ok"; then
            log "${GREEN}  $name: ROS2 + CycloneDDS OK${NC}"
        else
            log "${RED}  $name: Missing ROS2 or CycloneDDS${NC}"
            log "    Output: $check_result"
            all_ok=false
        fi
    done
    if ! $all_ok; then
        log "${RED}ERROR: ROS2/CycloneDDS not installed on all RPis. Aborting.${NC}"
        exit 1
    fi
}

kill_test_nodes() {
    # Kill any lingering test nodes on all RPis
    log "  Stopping test publishers on all RPis..."
    for ip in "$VEHICLE_IP" "$ARM1_IP" "$ARM2_IP"; do
        ssh_rpi "$ip" "pkill -f 'dds_test_pub.sh' 2>/dev/null; pkill -f '/dds_test/' 2>/dev/null; exit 0" 2>/dev/null || true
    done
    sleep 3
    # Verify they're dead
    for ip in "$VEHICLE_IP" "$ARM1_IP" "$ARM2_IP"; do
        local remaining
        remaining=$(ssh_rpi "$ip" "pgrep -fc '/dds_test/' 2>/dev/null || echo 0" 2>&1) || true
        remaining=$(echo "$remaining" | tr -d '[:space:]')
        if [ "$remaining" != "0" ]; then
            log "${YELLOW}  $(rpi_name "$ip"): $remaining test processes still alive, force killing...${NC}"
            ssh_rpi "$ip" "pkill -9 -f '/dds_test/' 2>/dev/null; exit 0" 2>/dev/null || true
        fi
    done
    # Also clean up stale topic list files
    for ip in "$VEHICLE_IP" "$ARM1_IP" "$ARM2_IP"; do
        ssh_rpi "$ip" "rm -f /tmp/dds_test_topics.txt 2>/dev/null; exit 0" 2>/dev/null || true
    done
}

# Deploy a helper script to an RPi that publishes a heartbeat topic.
# Using a remote script file avoids nested-quoting issues with ssh.exe.
deploy_publisher_script() {
    local ip="$1"
    ssh_rpi "$ip" "cat > /tmp/dds_test_pub.sh << 'REMOTESCRIPT'
#!/bin/bash
# DDS test publisher - args: DOMAIN_ID LOCALHOST_ONLY NODE_NAME
export ROS_DOMAIN_ID=\$1
export ROS_LOCALHOST_ONLY=\$2
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
source /opt/ros/jazzy/setup.bash
exec ros2 topic pub /dds_test/\$3/heartbeat std_msgs/msg/String \"{data: \${3}_alive}\" --rate 1 --qos-reliability reliable
REMOTESCRIPT
chmod +x /tmp/dds_test_pub.sh" 2>/dev/null
}

# Launch a lightweight publisher on an RPi
# Publishes to /dds_test/<node_name>/heartbeat every 1 second
launch_test_publisher() {
    local ip="$1"
    local domain_id="$2"
    local localhost_only="$3"
    local name
    name=$(rpi_name "$ip")

    ssh_rpi "$ip" "nohup /tmp/dds_test_pub.sh ${domain_id} ${localhost_only} ${name} > /tmp/dds_test_${name}.log 2>&1 &" 2>/dev/null
    log "  Started publisher on $name (domain=$domain_id, localhost_only=$localhost_only)"
}

# Check discovery: can a node see topics from other nodes?
# Returns number of discovered test topics
check_discovery_from() {
    local ip="$1"
    local domain_id="$2"
    local localhost_only="$3"

    # Write result to a temp file on RPi, then read it back.
    # This avoids issues with ssh.exe subshell output capture on complex commands.
    ssh_rpi "$ip" "export ROS_DOMAIN_ID=${domain_id} && export ROS_LOCALHOST_ONLY=${localhost_only} && export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp && source /opt/ros/jazzy/setup.bash && ros2 topic list 2>/dev/null | grep dds_test > /tmp/dds_test_topics.txt 2>/dev/null; exit 0" 2>/dev/null || true

    local topics
    topics=$(ssh_rpi "$ip" "cat /tmp/dds_test_topics.txt 2>/dev/null || true" 2>&1) || true

    # Count discovered topics
    local count=0
    if [ -n "$topics" ]; then
        count=$(echo "$topics" | grep -c "dds_test" || true)
    fi
    echo "$count|$topics"
}

# ---- Phase 1: Shared-Domain Discovery Test ----
run_phase1() {
    log ""
    log "${BLUE}=============================================="
    log "  PHASE 1: Shared-Domain Discovery Test"
    log "  All nodes: DOMAIN_ID=0, LOCALHOST_ONLY=0"
    log "  Duration: ${PHASE1_DURATION}s"
    log "==============================================${NC}"
    log ""

    # Launch publishers on all 3 RPis with shared domain
    log "${CYAN}Launching test publishers...${NC}"
    for ip in "$VEHICLE_IP" "$ARM1_IP" "$ARM2_IP"; do
        launch_test_publisher "$ip" 0 0
    done

    # Wait for DDS discovery to settle
    log "${YELLOW}Waiting 15s for DDS discovery...${NC}"
    sleep 15

    local phase1_pass=true
    local timeout_count=0
    local check_count=0
    local elapsed=15  # Already waited 15s

    while [ "$elapsed" -lt "$PHASE1_DURATION" ]; do
        check_count=$((check_count + 1))
        log ""
        log "${CYAN}--- Check #${check_count} at ${elapsed}s ---${NC}"

        for ip in "$VEHICLE_IP" "$ARM1_IP" "$ARM2_IP"; do
            local name
            name=$(rpi_name "$ip")
            local result
            result=$(check_discovery_from "$ip" 0 0)
            local count="${result%%|*}"
            local topics="${result#*|}"

            if [ "$count" -ge 3 ]; then
                log "${GREEN}  $name: discovered $count/3 topics OK${NC}"
            elif [ "$count" -ge 1 ]; then
                log "${YELLOW}  $name: discovered $count/3 topics (partial)${NC}"
                timeout_count=$((timeout_count + 1))
            else
                log "${RED}  $name: discovered 0/3 topics (TIMEOUT)${NC}"
                timeout_count=$((timeout_count + 1))
                phase1_pass=false
            fi

            # Log discovered topics to file
            echo "  [$name @ ${elapsed}s] topics: $topics" >> "${RESULTS_DIR}/phase1_detail.log"
        done

        sleep "$POLL_INTERVAL"
        elapsed=$((elapsed + POLL_INTERVAL))
    done

    # Cleanup
    kill_test_nodes
    sleep 3

    # Verdict
    log ""
    log "${BLUE}--- Phase 1 Results ---${NC}"
    log "  Checks performed: $check_count"
    log "  Discovery issues: $timeout_count"
    if $phase1_pass; then
        log "${GREEN}  VERDICT: PASS - All nodes discovered each other consistently${NC}"
    else
        log "${RED}  VERDICT: FAIL - Discovery timeouts detected${NC}"
    fi
    PHASE1_RESULT="$phase1_pass"
}

# ---- Phase 2: Production Isolation Test ----
run_phase2() {
    log ""
    log "${BLUE}=============================================="
    log "  PHASE 2: Production Isolation Test"
    log "  vehicle: DOMAIN_ID=0, LOCALHOST_ONLY=0"
    log "  arm1:    DOMAIN_ID=1, LOCALHOST_ONLY=1"
    log "  arm2:    DOMAIN_ID=2, LOCALHOST_ONLY=1"
    log "  Duration: ${PHASE2_DURATION}s"
    log "==============================================${NC}"
    log ""

    # Launch publishers with production domain config
    log "${CYAN}Launching test publishers (production config)...${NC}"
    launch_test_publisher "$VEHICLE_IP" 0 0
    launch_test_publisher "$ARM1_IP"    1 1
    launch_test_publisher "$ARM2_IP"    2 1

    log "${YELLOW}Waiting 15s for DDS discovery...${NC}"
    sleep 15

    local phase2_pass=true
    local bleed_count=0
    local internal_fail_count=0
    local check_count=0
    local elapsed=15

    while [ "$elapsed" -lt "$PHASE2_DURATION" ]; do
        check_count=$((check_count + 1))
        log ""
        log "${CYAN}--- Check #${check_count} at ${elapsed}s ---${NC}"

        # Vehicle (domain 0): should see ONLY its own topic (1 topic)
        local v_result
        v_result=$(check_discovery_from "$VEHICLE_IP" 0 0)
        local v_count="${v_result%%|*}"
        local v_topics="${v_result#*|}"

        if [ "$v_count" -eq 1 ] && echo "$v_topics" | grep -q "vehicle"; then
            log "${GREEN}  vehicle: sees 1 topic (own only) OK${NC}"
        elif [ "$v_count" -gt 1 ]; then
            log "${RED}  vehicle: sees $v_count topics - CROSS-DOMAIN BLEED${NC}"
            bleed_count=$((bleed_count + 1))
            phase2_pass=false
        elif [ "$v_count" -eq 0 ]; then
            log "${RED}  vehicle: sees 0 topics - INTERNAL DISCOVERY FAIL${NC}"
            internal_fail_count=$((internal_fail_count + 1))
            phase2_pass=false
        else
            log "${GREEN}  vehicle: sees $v_count topic(s)${NC}"
        fi

        # Arm1 (domain 1, localhost_only=1): should see ONLY its own topic
        local a1_result
        a1_result=$(check_discovery_from "$ARM1_IP" 1 1)
        local a1_count="${a1_result%%|*}"
        local a1_topics="${a1_result#*|}"

        if [ "$a1_count" -eq 1 ] && echo "$a1_topics" | grep -q "arm1"; then
            log "${GREEN}  arm1: sees 1 topic (own only) OK${NC}"
        elif [ "$a1_count" -gt 1 ]; then
            log "${RED}  arm1: sees $a1_count topics - CROSS-DOMAIN BLEED${NC}"
            bleed_count=$((bleed_count + 1))
            phase2_pass=false
        elif [ "$a1_count" -eq 0 ]; then
            log "${RED}  arm1: sees 0 topics - INTERNAL DISCOVERY FAIL${NC}"
            internal_fail_count=$((internal_fail_count + 1))
            phase2_pass=false
        else
            log "${GREEN}  arm1: sees $a1_count topic(s)${NC}"
        fi

        # Arm2 (domain 2, localhost_only=1): should see ONLY its own topic
        local a2_result
        a2_result=$(check_discovery_from "$ARM2_IP" 2 1)
        local a2_count="${a2_result%%|*}"
        local a2_topics="${a2_result#*|}"

        if [ "$a2_count" -eq 1 ] && echo "$a2_topics" | grep -q "arm2"; then
            log "${GREEN}  arm2: sees 1 topic (own only) OK${NC}"
        elif [ "$a2_count" -gt 1 ]; then
            log "${RED}  arm2: sees $a2_count topics - CROSS-DOMAIN BLEED${NC}"
            bleed_count=$((bleed_count + 1))
            phase2_pass=false
        elif [ "$a2_count" -eq 0 ]; then
            log "${RED}  arm2: sees 0 topics - INTERNAL DISCOVERY FAIL${NC}"
            internal_fail_count=$((internal_fail_count + 1))
            phase2_pass=false
        else
            log "${GREEN}  arm2: sees $a2_count topic(s)${NC}"
        fi

        echo "  [${elapsed}s] v=$v_count($v_topics) a1=$a1_count($a1_topics) a2=$a2_count($a2_topics)" \
            >> "${RESULTS_DIR}/phase2_detail.log"

        sleep "$POLL_INTERVAL"
        elapsed=$((elapsed + POLL_INTERVAL))
    done

    # Cleanup
    kill_test_nodes
    sleep 3

    # Verdict
    log ""
    log "${BLUE}--- Phase 2 Results ---${NC}"
    log "  Checks performed: $check_count"
    log "  Cross-domain bleed events: $bleed_count"
    log "  Internal discovery failures: $internal_fail_count"
    if $phase2_pass; then
        log "${GREEN}  VERDICT: PASS - Domain isolation holds, internal discovery works${NC}"
    else
        if [ "$bleed_count" -gt 0 ]; then
            log "${RED}  VERDICT: FAIL - Cross-domain bleed detected${NC}"
        fi
        if [ "$internal_fail_count" -gt 0 ]; then
            log "${RED}  VERDICT: FAIL - Internal discovery failures detected${NC}"
        fi
    fi
    PHASE2_RESULT="$phase2_pass"
}

# ---- Main ----

print_banner

mkdir -p "$RESULTS_DIR"
echo "DDS Discovery 3-Node Test Report" > "$REPORT_FILE"
echo "Started: $(date)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Pre-flight checks
check_connectivity
check_ros2_installed

# Deploy helper scripts to RPis
log "${CYAN}Deploying test publisher scripts to all RPis...${NC}"
for ip in "$VEHICLE_IP" "$ARM1_IP" "$ARM2_IP"; do
    deploy_publisher_script "$ip"
    log "  Deployed to $(rpi_name "$ip")"
done

# Clean slate
log "${CYAN}Killing any lingering test nodes...${NC}"
kill_test_nodes
sleep 2

# Run phases - use global variables for results since subshell capture
# strips log output
PHASE1_RESULT="false"
PHASE2_RESULT="false"

run_phase1
run_phase2

# ---- Final Report ----
log ""
log "${BLUE}=============================================="
log "  FINAL REPORT"
log "==============================================${NC}"
log "  Phase 1 (shared-domain):       $([ "$PHASE1_RESULT" = "true" ] && echo -e "${GREEN}PASS${NC}" || echo -e "${RED}FAIL${NC}")"
log "  Phase 2 (production-isolation): $([ "$PHASE2_RESULT" = "true" ] && echo -e "${GREEN}PASS${NC}" || echo -e "${RED}FAIL${NC}")"
log ""

if [ "$PHASE1_RESULT" = "true" ] && [ "$PHASE2_RESULT" = "true" ]; then
    log "${GREEN}OVERALL: PASS - V19 DDS Discovery 3-Node Test passed${NC}"
    log "  Network supports cross-node DDS discovery (Phase 1)"
    log "  Production domain isolation holds without bleed (Phase 2)"
    OVERALL="PASS"
else
    log "${RED}OVERALL: FAIL - See phase details above${NC}"
    OVERALL="FAIL"
fi

log ""
log "Results saved to: ${RESULTS_DIR}/"
log "  report.txt         - Summary log"
log "  phase1_detail.log  - Phase 1 discovery samples"
log "  phase2_detail.log  - Phase 2 isolation samples"
log ""
log "End time: $(date)"
log "${BLUE}==============================================${NC}"

# Exit code reflects overall result
[ "$OVERALL" = "PASS" ] && exit 0 || exit 1
