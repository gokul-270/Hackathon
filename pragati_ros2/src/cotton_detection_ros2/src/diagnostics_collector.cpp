// Copyright 2026 Pragati Robotics
// DiagnosticsCollector implementation — extracted from depthai_manager.cpp lines 193-580.
// Accepts pre-captured string/value inputs (D3). No popen(), no fopen(), no depthai deps.

#include "cotton_detection_ros2/diagnostics_collector.hpp"

#include <algorithm>
#include <cctype>
#include <sstream>

namespace cotton_detection {

// =========================================================================
// captureDeviceState — from depthai_manager.cpp lines 193-214
// =========================================================================
DeviceState DiagnosticsCollector::captureDeviceState(
    double avg, double css, double mss, double upa, double dss,
    double css_cpu, double mss_cpu, int usb_speed_enum) const {
    DeviceState state;
    state.temperature_celsius = (avg + css + mss + upa + dss) / 5.0;
    state.css_cpu_percent = css_cpu * 100.0;
    state.mss_cpu_percent = mss_cpu * 100.0;

    // USB speed enum: 3=SUPER→USB3, 2=HIGH→USB2, 1=FULL/LOW→USB1, else unknown
    switch (usb_speed_enum) {
        case 3:
            state.usb_speed = "USB3";
            break;
        case 2:
            state.usb_speed = "USB2";
            break;
        case 1:
            state.usb_speed = "USB1";
            break;
        default:
            state.usb_speed = "unknown";
            break;
    }
    return state;
}

// =========================================================================
// captureSystemDiagnostics — from depthai_manager.cpp lines 217-260
// =========================================================================
SystemDiagnostics DiagnosticsCollector::captureSystemDiagnostics(
    const std::string& proc_stat_line,
    const std::string& proc_meminfo) {
    SystemDiagnostics diag;

    // Parse /proc/stat first line for CPU delta
    if (!proc_stat_line.empty()) {
        std::istringstream iss(proc_stat_line);
        std::string cpu_label;
        long user = 0, nice = 0, system = 0, idle = 0, iowait = 0, irq = 0, softirq = 0;
        if (iss >> cpu_label >> user >> nice >> system >> idle >> iowait >> irq >> softirq) {
            long total = user + nice + system + idle + iowait + irq + softirq;
            long idle_total = idle + iowait;

            std::lock_guard<std::mutex> lock(cpu_mutex_);
            if (cpu_prev_total_ > 0) {
                long total_diff = total - cpu_prev_total_;
                long idle_diff = idle_total - cpu_prev_idle_;
                if (total_diff > 0) {
                    diag.system_cpu_percent =
                        100.0 * (1.0 - static_cast<double>(idle_diff) / total_diff);
                }
            }
            cpu_prev_total_ = total;
            cpu_prev_idle_ = idle_total;
        }
    }

    // Parse /proc/meminfo content
    if (!proc_meminfo.empty()) {
        std::istringstream memstream(proc_meminfo);
        std::string line;
        while (std::getline(memstream, line)) {
            if (line.find("MemTotal:") == 0) {
                std::istringstream iss(line.substr(9));
                uint64_t total_kb = 0;
                iss >> total_kb;
                diag.system_memory_total_mb = total_kb / 1024;
            } else if (line.find("MemAvailable:") == 0) {
                std::istringstream iss(line.substr(13));
                uint64_t available_kb = 0;
                iss >> available_kb;
                uint64_t available_mb = available_kb / 1024;
                if (diag.system_memory_total_mb > 0) {
                    diag.system_memory_used_mb =
                        diag.system_memory_total_mb - available_mb;
                    diag.system_memory_percent =
                        100.0 * (1.0 - static_cast<double>(available_mb) /
                                           diag.system_memory_total_mb);
                }
                break;
            }
        }
    }

    return diag;
}

// =========================================================================
// captureUSBState — from depthai_manager.cpp lines 322-373
// =========================================================================
USBState DiagnosticsCollector::captureUSBState(
    const std::vector<USBDeviceEntry>& entries) const {
    USBState result;

    for (const auto& entry : entries) {
        if (entry.vendor_id == "03e7") {
            // Found Luxonis device
            result.usb_device_state = "Connected";
            result.usb_driver_info = entry.product;

            if (entry.has_urbnum) {
                result.usb_device_state = "Active";
            }

            if (entry.status != "configured") {
                result.usb_device_state = "Error: " + entry.status;
                result.usb_error_count++;
            }

            break;  // Found our device
        }
    }

    return result;
}

// =========================================================================
// classifyXLinkError — from depthai_manager.cpp lines 522-580 (analyzeXLinkError)
// =========================================================================
XLinkErrorCategory DiagnosticsCollector::classifyXLinkError(
    const std::string& error_msg) {
    // Case-insensitive timeout check (highest priority per spec)
    {
        std::string lower = error_msg;
        std::transform(lower.begin(), lower.end(), lower.begin(),
                       [](unsigned char c) { return std::tolower(c); });
        if (lower.find("timeout") != std::string::npos) {
            return XLinkErrorCategory::timeout;
        }
    }

    // "Communication exception" → link_down
    if (error_msg.find("Communication exception") != std::string::npos) {
        return XLinkErrorCategory::link_down;
    }

    // "device error/misconfiguration" or "No available devices" → device_removed
    if (error_msg.find("device error/misconfiguration") != std::string::npos ||
        error_msg.find("No available devices") != std::string::npos) {
        return XLinkErrorCategory::device_removed;
    }

    // "X_LINK_ERROR" without matching above → pipe_error
    if (error_msg.find("X_LINK_ERROR") != std::string::npos) {
        return XLinkErrorCategory::pipe_error;
    }

    return XLinkErrorCategory::unknown;
}

// =========================================================================
// buildXLinkReport — from depthai_manager.cpp lines 522-580 (analyzeXLinkError)
// =========================================================================
XLinkReport DiagnosticsCollector::buildXLinkReport(
    const std::string& error_msg,
    const std::string& /*operation*/,
    const DeviceState& device,
    const SystemDiagnostics& sys,
    int64_t time_since_last_frame_ms) const {
    XLinkReport report;
    report.category = classifyXLinkError(error_msg);

    // Contributing causes — threshold analysis from spec
    if (device.temperature_celsius > 85.0) {
        report.contributing_causes.push_back("HIGH_TEMPERATURE");
    } else if (device.temperature_celsius > 75.0) {
        report.contributing_causes.push_back("ELEVATED_TEMPERATURE");
    }

    if (device.usb_speed == "USB2" || device.usb_speed == "USB1") {
        report.contributing_causes.push_back("REDUCED_USB_SPEED");
    }

    if (device.css_cpu_percent > 90.0) {
        report.contributing_causes.push_back("CSS_CPU_OVERLOAD");
    }

    if (device.mss_cpu_percent > 95.0) {
        report.contributing_causes.push_back("MSS_CPU_OVERLOAD");
    }

    if (sys.system_cpu_percent > 90.0) {
        report.contributing_causes.push_back("SYSTEM_CPU_OVERLOAD");
    }

    if (sys.system_memory_percent > 95.0) {
        report.contributing_causes.push_back("SYSTEM_MEMORY_LOW");
    }

    if (time_since_last_frame_ms > 5000) {
        report.contributing_causes.push_back("FRAME_STARVATION");
    }

    // Recommended action
    if (report.contributing_causes.empty()) {
        report.recommended_action =
            "Insufficient diagnostic data for root cause analysis";
    } else {
        report.recommended_action = "Investigate: ";
        for (size_t i = 0; i < report.contributing_causes.size(); ++i) {
            if (i > 0) report.recommended_action += ", ";
            report.recommended_action += report.contributing_causes[i];
        }
    }

    return report;
}

// =========================================================================
// parseKernelLogs — from depthai_manager.cpp lines 406-436 (logCapturedKernelLogs)
// =========================================================================
KernelLogSummary DiagnosticsCollector::parseKernelLogs(
    const std::string& dmesg_output) {
    KernelLogSummary summary;

    if (dmesg_output.empty()) {
        return summary;
    }

    std::istringstream iss(dmesg_output);
    std::string line;
    while (std::getline(iss, line)) {
        // Case-sensitive keyword matching per spec (matches current behavior)
        if (line.find("usb") != std::string::npos ||
            line.find("USB") != std::string::npos ||
            line.find("device") != std::string::npos ||
            line.find("error") != std::string::npos ||
            line.find("fail") != std::string::npos ||
            line.find("reset") != std::string::npos ||
            line.find("disconnect") != std::string::npos) {
            summary.filtered_lines.push_back(line);
        }
    }

    summary.has_relevant_entries = !summary.filtered_lines.empty();
    return summary;
}

}  // namespace cotton_detection
