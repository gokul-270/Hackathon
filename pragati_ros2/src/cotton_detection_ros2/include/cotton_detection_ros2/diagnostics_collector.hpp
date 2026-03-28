// Copyright 2026 Pragati Robotics
// DiagnosticsCollector — stateless diagnostics extraction (no depthai/rclcpp deps)
#pragma once

#include <cstdint>
#include <mutex>
#include <string>
#include <vector>

namespace cotton_detection {

/// Hardware state snapshot captured from dai::Device values passed by caller.
struct DeviceState {
    double temperature_celsius{0.0};
    double css_cpu_percent{0.0};
    double mss_cpu_percent{0.0};
    std::string usb_speed{"unknown"};
};

/// Host-level diagnostics parsed from /proc content passed by caller.
struct SystemDiagnostics {
    double system_cpu_percent{0.0};
    double system_memory_percent{0.0};
    uint64_t system_memory_used_mb{0};
    uint64_t system_memory_total_mb{0};
};

/// A single USB sysfs device entry provided by the caller.
struct USBDeviceEntry {
    std::string vendor_id;
    std::string product;
    bool has_urbnum{false};
    std::string status;
};

/// USB state result from captureUSBState().
struct USBState {
    std::string usb_device_state{"unknown"};
    std::string usb_driver_info{"unknown"};
    int usb_error_count{0};
};

/// XLink error classification categories (priority order: timeout > link_down > device_removed > pipe_error > unknown).
enum class XLinkErrorCategory {
    timeout,
    link_down,
    device_removed,
    pipe_error,
    unknown
};

/// Structured report for XLink error root-cause analysis.
struct XLinkReport {
    XLinkErrorCategory category{XLinkErrorCategory::unknown};
    std::vector<std::string> contributing_causes;
    std::string recommended_action;
};

/// Parsed kernel log summary.
struct KernelLogSummary {
    std::vector<std::string> filtered_lines;
    bool has_relevant_entries{false};
};

/// Stateless diagnostics collector — all public methods accept value parameters.
/// Only mutable state: CPU delta tracking (cpu_prev_total_, cpu_prev_idle_).
class DiagnosticsCollector {
public:
    DiagnosticsCollector() = default;

    /// Capture device state from parameter values (no dai::Device* access).
    /// @param avg Average thermal zone temperature (°C)
    /// @param css CSS thermal zone temperature (°C)
    /// @param mss MSS thermal zone temperature (°C)
    /// @param upa UPA thermal zone temperature (°C)
    /// @param dss DSS thermal zone temperature (°C)
    /// @param css_cpu CSS CPU usage as fraction (0.0-1.0)
    /// @param mss_cpu MSS CPU usage as fraction (0.0-1.0)
    /// @param usb_speed_enum Integer USB speed enum: 3=SUPER, 2=HIGH, 1=FULL/LOW, else unknown
    DeviceState captureDeviceState(double avg, double css, double mss, double upa, double dss,
                                   double css_cpu, double mss_cpu, int usb_speed_enum) const;

    /// Capture host system diagnostics from pre-read /proc content.
    /// CPU% uses delta between successive calls. First call returns 0%.
    /// @param proc_stat_line First line of /proc/stat (e.g., "cpu  100 0 50 800 10 5 5")
    /// @param proc_meminfo Full content of /proc/meminfo
    SystemDiagnostics captureSystemDiagnostics(const std::string& proc_stat_line,
                                               const std::string& proc_meminfo);

    /// Identify Luxonis device by vendor 03e7 and report USB state.
    USBState captureUSBState(const std::vector<USBDeviceEntry>& entries) const;

    /// Classify an XLink error message into one of five categories (pure function).
    static XLinkErrorCategory classifyXLinkError(const std::string& error_msg);

    /// Build structured XLink diagnostic report.
    /// @param error_msg The XLink error message string
    /// @param operation Name of the failing operation
    /// @param device Device hardware state snapshot
    /// @param sys System diagnostics snapshot
    /// @param time_since_last_frame_ms Milliseconds since last successful frame
    XLinkReport buildXLinkReport(const std::string& error_msg,
                                 const std::string& operation,
                                 const DeviceState& device,
                                 const SystemDiagnostics& sys,
                                 int64_t time_since_last_frame_ms = 0) const;

    /// Parse pre-captured kernel log output, filtering USB/device-related lines.
    static KernelLogSummary parseKernelLogs(const std::string& dmesg_output);

private:
    mutable std::mutex cpu_mutex_;
    long cpu_prev_total_{0};
    long cpu_prev_idle_{0};
};

}  // namespace cotton_detection
