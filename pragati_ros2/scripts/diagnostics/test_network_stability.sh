#!/bin/bash
# ==============================================
# Network Stability Test Script
# ==============================================
# Tests network connection stability to identify problematic RPi units.
# Run this on each RPi to determine which one has connectivity issues.
#
# Usage:
#   ./test_network_stability.sh [ROUTER_IP] [DURATION_SECONDS]
#
# Default router IP: 192.168.1.1
# Default duration: 300 seconds (5 minutes)
#
# Interpretation of Results:
#   < 1%  packet loss: Normal, RPi network is healthy
#   1-5%  packet loss: Monitor, may have minor issues
#   > 5%  packet loss: Problem RPi, investigate hardware/driver
#   > 20% packet loss: Critical issue, likely hardware fault
#
# Related Documentation:
#   docs/guides/TROUBLESHOOTING.md - "Network & Connectivity Issues"
#   docs/guides/hardware/RPi_POWER_MGMT_FIX_SUMMARY.md - Power management fixes
# ==============================================

set -e  # Exit on error

# Configuration
ROUTER_IP="${1:-192.168.1.1}"  # Default to 192.168.1.1 if not provided
DURATION="${2:-300}"            # Default to 5 minutes if not provided
PING_COUNT=$DURATION            # One ping per second
PING_INTERVAL=1                 # 1 second between pings
RESULTS_FILE="/tmp/network_stability_results.txt"
SUMMARY_FILE="/tmp/network_stability_summary.txt"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# ==============================================
# Functions
# ==============================================

print_header() {
    echo "=============================================="
    echo "Network Stability Test"
    echo "=============================================="
    echo "Target: $ROUTER_IP"
    echo "Duration: $DURATION seconds ($PING_COUNT pings)"
    echo "Start time: $(date)"
    echo "=============================================="
    echo ""
}

check_dependencies() {
    if ! command -v ping &> /dev/null; then
        echo "ERROR: ping command not found"
        exit 1
    fi
    
    if ! command -v bc &> /dev/null; then
        echo "ERROR: bc command not found. Install with: sudo apt install bc"
        exit 1
    fi
}

run_ping_test() {
    echo "Running ping test to $ROUTER_IP..."
    echo "This will take approximately $DURATION seconds..."
    echo ""
    
    # Run ping with progress updates every 10%
    local progress_interval=$((PING_COUNT / 10))
    
    ping -c $PING_COUNT -i $PING_INTERVAL -W 2 $ROUTER_IP 2>&1 | tee $RESULTS_FILE | \
    awk -v interval=$progress_interval '
        BEGIN { count = 0 }
        /icmp_seq/ { 
            count++;
            if (count % interval == 0) {
                printf "\rProgress: %d%%", (count * 100 / '$PING_COUNT');
                fflush();
            }
        }
        /packet loss/ { print "\n" $0; }
        /rtt/ { print $0; }
    '
}

analyze_results() {
    echo ""
    echo "=============================================="
    echo "Results Analysis"
    echo "=============================================="
    
    # Extract packet loss percentage
    PACKET_LOSS=$(grep "packet loss" $RESULTS_FILE | awk '{print $6}' | tr -d '%')
    
    # Extract RTT statistics if available
    RTT_LINE=$(grep "rtt min/avg/max/mdev" $RESULTS_FILE || echo "")
    
    # Get system information
    HOSTNAME=$(hostname)
    IP_ADDR=$(hostname -I | awk '{print $1}')
    WIFI_INTERFACE=$(iwconfig 2>/dev/null | grep -o "^wlan[0-9]" | head -1)
    
    # WiFi signal strength (if applicable)
    if [ -n "$WIFI_INTERFACE" ]; then
        SIGNAL_INFO=$(iwconfig $WIFI_INTERFACE 2>/dev/null | grep "Signal level" || echo "N/A")
        POWER_MGMT=$(iwconfig $WIFI_INTERFACE 2>/dev/null | grep "Power Management" || echo "N/A")
    else
        SIGNAL_INFO="N/A (Ethernet or WiFi not detected)"
        POWER_MGMT="N/A"
    fi
    
    # Create summary
    {
        echo "Test Date: $(date)"
        echo "Hostname: $HOSTNAME"
        echo "IP Address: $IP_ADDR"
        echo "Target: $ROUTER_IP"
        echo "Duration: $DURATION seconds"
        echo "Packet Loss: ${PACKET_LOSS}%"
        echo "RTT Statistics: $RTT_LINE"
        echo "WiFi Signal: $SIGNAL_INFO"
        echo "Power Management: $POWER_MGMT"
    } | tee $SUMMARY_FILE
    
    echo ""
    echo "=============================================="
    echo "Verdict"
    echo "=============================================="
    
    # Determine health status using bc for floating point comparison
    if (( $(echo "$PACKET_LOSS < 1" | bc -l) )); then
        echo -e "${GREEN}✅ HEALTHY${NC}: Network stability is excellent (< 1% loss)"
        echo "This RPi has no connectivity issues."
        VERDICT="HEALTHY"
    elif (( $(echo "$PACKET_LOSS >= 1 && $PACKET_LOSS <= 5" | bc -l) )); then
        echo -e "${YELLOW}⚠️  MONITOR${NC}: Minor packet loss detected (1-5% loss)"
        echo "This RPi may have intermittent connectivity issues."
        echo "Recommendation: Monitor over time, check WiFi signal strength"
        VERDICT="MONITOR"
    elif (( $(echo "$PACKET_LOSS > 5 && $PACKET_LOSS <= 20" | bc -l) )); then
        echo -e "${RED}❌ PROBLEM${NC}: High packet loss detected (5-20% loss)"
        echo "This RPi has significant connectivity issues."
        echo "Recommendation: Check power management, WiFi driver, signal strength"
        VERDICT="PROBLEM"
    else
        echo -e "${RED}🔥 CRITICAL${NC}: Very high packet loss detected (> 20% loss)"
        echo "This RPi has severe connectivity issues - likely hardware fault."
        echo "Recommendation: Replace RPi or WiFi adapter, check hardware"
        VERDICT="CRITICAL"
    fi
    
    echo "Packet Loss: ${PACKET_LOSS}%"
    echo ""
    
    # Add verdict to summary file
    echo "Verdict: $VERDICT" >> $SUMMARY_FILE
    echo "Packet Loss: ${PACKET_LOSS}%" >> $SUMMARY_FILE
}

print_troubleshooting_steps() {
    echo "=============================================="
    echo "Troubleshooting Steps"
    echo "=============================================="
    
    if (( $(echo "$PACKET_LOSS > 1" | bc -l) )); then
        echo "1. Check WiFi Power Management (should be OFF):"
        echo "   iwconfig wlan0 | grep 'Power Management'"
        echo ""
        echo "2. Check WiFi signal strength:"
        echo "   iwconfig wlan0 | grep Signal"
        echo ""
        echo "3. Check for WiFi errors in system logs:"
        echo "   dmesg | grep -i 'wlan\|wifi\|firmware' | tail -20"
        echo ""
        echo "4. Review network configuration:"
        echo "   cat /etc/network/interfaces.d/wlan0"
        echo ""
        echo "5. Test with Ethernet cable (if available) to isolate WiFi issue"
        echo ""
        echo "See docs/guides/TROUBLESHOOTING.md for detailed troubleshooting."
    fi
}

save_results() {
    # Save detailed results to a timestamped file
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    HOSTNAME=$(hostname)
    FINAL_REPORT="/tmp/network_test_${HOSTNAME}_${TIMESTAMP}.txt"
    
    {
        cat $SUMMARY_FILE
        echo ""
        echo "=============================================="
        echo "Detailed Ping Results"
        echo "=============================================="
        cat $RESULTS_FILE
    } > $FINAL_REPORT
    
    echo ""
    echo "Full report saved to: $FINAL_REPORT"
    echo "Summary saved to: $SUMMARY_FILE"
}

# ==============================================
# Main Script
# ==============================================

print_header
check_dependencies
run_ping_test
analyze_results
print_troubleshooting_steps
save_results

echo ""
echo "=============================================="
echo "Test Complete"
echo "End time: $(date)"
echo "=============================================="
