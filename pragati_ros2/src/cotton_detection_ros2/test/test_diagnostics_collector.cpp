// Copyright 2026 Pragati Robotics
// DiagnosticsCollector unit tests — NO depthai::core dependency
// Tests use synthetic string/value inputs per design decision D3.
//
// TDD RED phase: all tests written against the spec before implementation.
// Stub methods return defaults, so tests that assert non-default values will FAIL.

#include <gtest/gtest.h>

#include <memory>
#include <string>
#include <thread>
#include <vector>

#include "cotton_detection_ros2/diagnostics_collector.hpp"

namespace cotton_detection::test {

// =========================================================================
// Task 2.2: captureDeviceState tests
// =========================================================================

class CaptureDeviceStateTest : public ::testing::Test {
protected:
    DiagnosticsCollector dc_;
};

// Spec: "Capture device state with valid readings"
// GIVEN chip temps {avg=45, css=44, mss=46, upa=43, dss=47}, CSS CPU=0.35, MSS CPU=0.60, USB=SUPER
// THEN temperature=45.0, css_cpu=35.0, mss_cpu=60.0, usb_speed="USB3"
TEST_F(CaptureDeviceStateTest, ValidReadings) {
    auto state = dc_.captureDeviceState(45.0, 44.0, 46.0, 43.0, 47.0, 0.35, 0.60, 3);
    EXPECT_DOUBLE_EQ(state.temperature_celsius, 45.0);
    EXPECT_DOUBLE_EQ(state.css_cpu_percent, 35.0);
    EXPECT_DOUBLE_EQ(state.mss_cpu_percent, 60.0);
    EXPECT_EQ(state.usb_speed, "USB3");
}

// Spec: "Capture device state with USB2 speed"
// GIVEN USB speed HIGH (enum=2)
// THEN usb_speed="USB2"
TEST_F(CaptureDeviceStateTest, Usb2Speed) {
    auto state = dc_.captureDeviceState(50.0, 50.0, 50.0, 50.0, 50.0, 0.5, 0.5, 2);
    EXPECT_EQ(state.usb_speed, "USB2");
}

// Spec: "Capture device state with unknown USB speed"
// GIVEN USB speed UNKNOWN or other
// THEN usb_speed="unknown"
TEST_F(CaptureDeviceStateTest, UnknownUsbSpeed) {
    auto state = dc_.captureDeviceState(50.0, 50.0, 50.0, 50.0, 50.0, 0.5, 0.5, 99);
    EXPECT_EQ(state.usb_speed, "unknown");
}

// USB speed LOW/FULL (enum=1) should map to "USB1"
TEST_F(CaptureDeviceStateTest, Usb1Speed) {
    auto state = dc_.captureDeviceState(50.0, 50.0, 50.0, 50.0, 50.0, 0.5, 0.5, 1);
    EXPECT_EQ(state.usb_speed, "USB1");
}

// Temperature is mean of five zones, not just average zone
TEST_F(CaptureDeviceStateTest, TemperatureIsMeanOfFiveZones) {
    // average=50, css=40, mss=60, upa=30, dss=70 → mean = 50.0
    auto state = dc_.captureDeviceState(50.0, 40.0, 60.0, 30.0, 70.0, 0.0, 0.0, 3);
    EXPECT_DOUBLE_EQ(state.temperature_celsius, 50.0);
}

// CPU conversion: fraction → percentage
TEST_F(CaptureDeviceStateTest, CpuFractionToPercentage) {
    auto state = dc_.captureDeviceState(50.0, 50.0, 50.0, 50.0, 50.0, 1.0, 0.0, 3);
    EXPECT_DOUBLE_EQ(state.css_cpu_percent, 100.0);
    EXPECT_DOUBLE_EQ(state.mss_cpu_percent, 0.0);
}

// =========================================================================
// Task 2.3: captureSystemDiagnostics tests
// =========================================================================

class SystemDiagnosticsTest : public ::testing::Test {
protected:
    DiagnosticsCollector dc_;
};

// Spec: "Compute host CPU usage from two successive /proc/stat snapshots"
// GIVEN first line "cpu  100 0 50 800 10 5 5" (total=970, idle=810)
//   AND second line "cpu  200 0 100 1600 20 10 10" (total=1940, idle=1620)
// THEN second call returns ~16.5%
TEST_F(SystemDiagnosticsTest, CpuUsageDelta) {
    std::string snap1 = "cpu  100 0 50 800 10 5 5";
    std::string snap2 = "cpu  200 0 100 1600 20 10 10";
    std::string meminfo = "MemTotal:        3956712 kB\nMemAvailable:     1978356 kB\n";

    // First call — initializes baseline, returns 0%
    auto d1 = dc_.captureSystemDiagnostics(snap1, meminfo);
    EXPECT_DOUBLE_EQ(d1.system_cpu_percent, 0.0);

    // Second call — computes delta
    auto d2 = dc_.captureSystemDiagnostics(snap2, meminfo);
    // delta_total = 1940-970 = 970, delta_idle = 1620-810 = 810
    // cpu% = 100 * (1 - 810/970) = 100 * (160/970) ≈ 16.4948%
    EXPECT_NEAR(d2.system_cpu_percent, 16.4948, 0.1);
}

// Spec: "Compute host memory usage from /proc/meminfo content"
// GIVEN MemTotal=3956712 kB, MemAvailable=1978356 kB
// THEN total_mb=3864, used_mb≈1932, percent≈50%
TEST_F(SystemDiagnosticsTest, MemoryUsage) {
    std::string stat_line = "cpu  100 0 50 800 10 5 5";
    std::string meminfo = "MemTotal:        3956712 kB\nMemAvailable:     1978356 kB\n";

    auto d = dc_.captureSystemDiagnostics(stat_line, meminfo);
    EXPECT_EQ(d.system_memory_total_mb, 3863u);  // 3956712 / 1024 = 3863 (integer truncation)
    EXPECT_NEAR(d.system_memory_used_mb, 1931, 2);  // 3863 - (1978356/1024=1932) = 1931
    EXPECT_NEAR(d.system_memory_percent, 50.0, 1.0);
}

// Spec: "First CPU snapshot returns zero percent (no previous delta)"
TEST_F(SystemDiagnosticsTest, FirstSnapshotReturnsZeroCpu) {
    std::string stat_line = "cpu  100 0 50 800 10 5 5";
    auto d = dc_.captureSystemDiagnostics(stat_line, "");
    EXPECT_DOUBLE_EQ(d.system_cpu_percent, 0.0);
}

// Spec: "Empty or malformed /proc/stat content"
TEST_F(SystemDiagnosticsTest, EmptyStatLine) {
    auto d = dc_.captureSystemDiagnostics("", "");
    EXPECT_DOUBLE_EQ(d.system_cpu_percent, 0.0);
}

TEST_F(SystemDiagnosticsTest, MalformedStatLine) {
    auto d = dc_.captureSystemDiagnostics("garbage data here", "");
    EXPECT_DOUBLE_EQ(d.system_cpu_percent, 0.0);
}

// Memory with missing MemAvailable should still parse MemTotal
TEST_F(SystemDiagnosticsTest, MissingMemAvailable) {
    std::string meminfo = "MemTotal:        3956712 kB\nBuffers: 12345 kB\n";
    auto d = dc_.captureSystemDiagnostics("", meminfo);
    EXPECT_EQ(d.system_memory_total_mb, 3863u);  // 3956712 / 1024 = 3863
    // No MemAvailable → used/percent remain default
    EXPECT_EQ(d.system_memory_used_mb, 0u);
    EXPECT_DOUBLE_EQ(d.system_memory_percent, 0.0);
}

// =========================================================================
// Task 2.4: captureUSBState tests
// =========================================================================

class CaptureUSBStateTest : public ::testing::Test {
protected:
    DiagnosticsCollector dc_;
};

// Spec: "Luxonis device found in configured state"
TEST_F(CaptureUSBStateTest, LuxonisConfigured) {
    std::vector<USBDeviceEntry> entries = {
        {"03e7", "Movidius MyriadX", true, "configured"}
    };
    auto usb = dc_.captureUSBState(entries);
    EXPECT_EQ(usb.usb_device_state, "Active");
    EXPECT_EQ(usb.usb_driver_info, "Movidius MyriadX");
    EXPECT_EQ(usb.usb_error_count, 0);
}

// Spec: "Luxonis device found in error state"
TEST_F(CaptureUSBStateTest, LuxonisErrorState) {
    std::vector<USBDeviceEntry> entries = {
        {"03e7", "Movidius MyriadX", true, "suspended"}
    };
    auto usb = dc_.captureUSBState(entries);
    EXPECT_EQ(usb.usb_device_state, "Error: suspended");
    EXPECT_EQ(usb.usb_error_count, 1);
}

// Spec: "No Luxonis device present" — empty list
TEST_F(CaptureUSBStateTest, NoLuxonisDeviceEmpty) {
    std::vector<USBDeviceEntry> entries;
    auto usb = dc_.captureUSBState(entries);
    EXPECT_EQ(usb.usb_device_state, "unknown");
    EXPECT_EQ(usb.usb_driver_info, "unknown");
}

// Spec: "No Luxonis device present" — other vendors
TEST_F(CaptureUSBStateTest, NoLuxonisDeviceOtherVendors) {
    std::vector<USBDeviceEntry> entries = {
        {"1234", "Generic USB", true, "configured"},
        {"5678", "Another Device", false, "configured"}
    };
    auto usb = dc_.captureUSBState(entries);
    EXPECT_EQ(usb.usb_device_state, "unknown");
}

// Device without urbnum → "Connected" (not "Active")
TEST_F(CaptureUSBStateTest, LuxonisNoUrbnumConnected) {
    std::vector<USBDeviceEntry> entries = {
        {"03e7", "Movidius MyriadX", false, "configured"}
    };
    auto usb = dc_.captureUSBState(entries);
    EXPECT_EQ(usb.usb_device_state, "Connected");
    EXPECT_EQ(usb.usb_driver_info, "Movidius MyriadX");
}

// Multiple error increments across calls
TEST_F(CaptureUSBStateTest, ErrorCountAccumulates) {
    std::vector<USBDeviceEntry> entries1 = {
        {"03e7", "MyriadX", true, "suspended"}
    };
    auto usb1 = dc_.captureUSBState(entries1);
    EXPECT_EQ(usb1.usb_error_count, 1);

    // Second call — error count is per-call (stateless), returns 1 again
    auto usb2 = dc_.captureUSBState(entries1);
    EXPECT_EQ(usb2.usb_error_count, 1);
}

// =========================================================================
// Task 2.5: XLink classification tests
// =========================================================================

class XLinkClassificationTest : public ::testing::Test {};

// Spec: "Classify timeout error"
TEST_F(XLinkClassificationTest, Timeout) {
    EXPECT_EQ(DiagnosticsCollector::classifyXLinkError("XLink operation timeout after 5000ms"),
              XLinkErrorCategory::timeout);
}

// Spec: "Classify communication exception as link_down"
TEST_F(XLinkClassificationTest, LinkDown) {
    EXPECT_EQ(DiagnosticsCollector::classifyXLinkError("Communication exception - X_LINK_ERROR"),
              XLinkErrorCategory::link_down);
}

// Spec: "Classify device misconfiguration as device_removed"
TEST_F(XLinkClassificationTest, DeviceMisconfiguration) {
    EXPECT_EQ(DiagnosticsCollector::classifyXLinkError("device error/misconfiguration detected"),
              XLinkErrorCategory::device_removed);
}

// Spec: device_removed also matches "No available devices"
TEST_F(XLinkClassificationTest, NoAvailableDevices) {
    EXPECT_EQ(DiagnosticsCollector::classifyXLinkError("No available devices"),
              XLinkErrorCategory::device_removed);
}

// Spec: "Classify bare X_LINK_ERROR as pipe_error"
TEST_F(XLinkClassificationTest, PipeError) {
    EXPECT_EQ(DiagnosticsCollector::classifyXLinkError("X_LINK_ERROR in pipeline stream"),
              XLinkErrorCategory::pipe_error);
}

// Spec: "Classify unrecognized error as unknown"
TEST_F(XLinkClassificationTest, Unknown) {
    EXPECT_EQ(DiagnosticsCollector::classifyXLinkError("Segmentation fault in neural network"),
              XLinkErrorCategory::unknown);
}

// Spec: "Priority when message matches multiple patterns" — timeout wins
TEST_F(XLinkClassificationTest, TimeoutWinsOverLinkDown) {
    EXPECT_EQ(
        DiagnosticsCollector::classifyXLinkError("Communication exception - timeout in X_LINK_ERROR"),
        XLinkErrorCategory::timeout);
}

// Case-insensitive timeout matching
TEST_F(XLinkClassificationTest, TimeoutCaseInsensitive) {
    EXPECT_EQ(DiagnosticsCollector::classifyXLinkError("TIMEOUT occurred"),
              XLinkErrorCategory::timeout);
    EXPECT_EQ(DiagnosticsCollector::classifyXLinkError("Timeout after 3s"),
              XLinkErrorCategory::timeout);
}

// Spec: "Classification assumes input is an XLink error" — pure function, deterministic
TEST_F(XLinkClassificationTest, PureFunctionDeterministic) {
    auto r1 = DiagnosticsCollector::classifyXLinkError("X_LINK_ERROR");
    auto r2 = DiagnosticsCollector::classifyXLinkError("X_LINK_ERROR");
    EXPECT_EQ(r1, r2);
    EXPECT_EQ(r1, XLinkErrorCategory::pipe_error);
}

// Spec: "Non-XLink message returns unknown category"
TEST_F(XLinkClassificationTest, NonXLinkReturnsUnknown) {
    EXPECT_EQ(DiagnosticsCollector::classifyXLinkError("out of memory"),
              XLinkErrorCategory::unknown);
}

// =========================================================================
// Task 2.6: buildXLinkReport + parseKernelLogs tests
// =========================================================================

class BuildXLinkReportTest : public ::testing::Test {
protected:
    DiagnosticsCollector dc_;
};

// Spec: "Report with thermal and USB contributing causes"
// GIVEN temperature=87°C, USB="USB2"
// THEN category=pipe_error, causes contain HIGH_TEMPERATURE and REDUCED_USB_SPEED
TEST_F(BuildXLinkReportTest, ThermalAndUsbCauses) {
    DeviceState dev;
    dev.temperature_celsius = 87.0;
    dev.css_cpu_percent = 50.0;
    dev.mss_cpu_percent = 50.0;
    dev.usb_speed = "USB2";

    SystemDiagnostics sys;

    auto report = dc_.buildXLinkReport("X_LINK_ERROR", "getFrame", dev, sys);
    EXPECT_EQ(report.category, XLinkErrorCategory::pipe_error);

    // Check contributing causes
    bool has_high_temp = false, has_reduced_usb = false;
    for (const auto& cause : report.contributing_causes) {
        if (cause == "HIGH_TEMPERATURE") has_high_temp = true;
        if (cause == "REDUCED_USB_SPEED") has_reduced_usb = true;
    }
    EXPECT_TRUE(has_high_temp) << "Expected HIGH_TEMPERATURE cause for 87°C";
    EXPECT_TRUE(has_reduced_usb) << "Expected REDUCED_USB_SPEED cause for USB2";
    EXPECT_FALSE(report.recommended_action.empty());
}

// Spec: "Report with no contributing causes"
// GIVEN temperature=40°C, USB="USB3", all nominal
// THEN contributing_causes is empty
TEST_F(BuildXLinkReportTest, NoCauses) {
    DeviceState dev;
    dev.temperature_celsius = 40.0;
    dev.css_cpu_percent = 50.0;
    dev.mss_cpu_percent = 50.0;
    dev.usb_speed = "USB3";

    SystemDiagnostics sys;
    sys.system_cpu_percent = 50.0;
    sys.system_memory_percent = 50.0;

    auto report = dc_.buildXLinkReport("X_LINK_ERROR", "getFrame", dev, sys);
    EXPECT_TRUE(report.contributing_causes.empty());
    // recommended_action should indicate insufficient data
    EXPECT_FALSE(report.recommended_action.empty());
}

// Spec: "Report with system resource pressure"
// GIVEN CPU=95%, memory=97%, CSS CPU=92%
// THEN causes contain SYSTEM_CPU_OVERLOAD, SYSTEM_MEMORY_LOW, CSS_CPU_OVERLOAD
TEST_F(BuildXLinkReportTest, SystemResourcePressure) {
    DeviceState dev;
    dev.temperature_celsius = 40.0;
    dev.css_cpu_percent = 92.0;
    dev.mss_cpu_percent = 50.0;
    dev.usb_speed = "USB3";

    SystemDiagnostics sys;
    sys.system_cpu_percent = 95.0;
    sys.system_memory_percent = 97.0;

    auto report = dc_.buildXLinkReport("X_LINK_ERROR", "getFrame", dev, sys);

    bool has_sys_cpu = false, has_sys_mem = false, has_css_cpu = false;
    for (const auto& cause : report.contributing_causes) {
        if (cause == "SYSTEM_CPU_OVERLOAD") has_sys_cpu = true;
        if (cause == "SYSTEM_MEMORY_LOW") has_sys_mem = true;
        if (cause == "CSS_CPU_OVERLOAD") has_css_cpu = true;
    }
    EXPECT_TRUE(has_sys_cpu);
    EXPECT_TRUE(has_sys_mem);
    EXPECT_TRUE(has_css_cpu);
}

// Elevated temperature (75-85°C) → ELEVATED_TEMPERATURE
TEST_F(BuildXLinkReportTest, ElevatedTemperature) {
    DeviceState dev;
    dev.temperature_celsius = 78.0;
    dev.usb_speed = "USB3";

    SystemDiagnostics sys;

    auto report = dc_.buildXLinkReport("X_LINK_ERROR", "getFrame", dev, sys);
    bool has_elevated = false;
    for (const auto& cause : report.contributing_causes) {
        if (cause == "ELEVATED_TEMPERATURE") has_elevated = true;
    }
    EXPECT_TRUE(has_elevated);
}

// MSS CPU > 95% → MSS_CPU_OVERLOAD
TEST_F(BuildXLinkReportTest, MssCpuOverload) {
    DeviceState dev;
    dev.temperature_celsius = 40.0;
    dev.mss_cpu_percent = 96.0;
    dev.usb_speed = "USB3";

    SystemDiagnostics sys;

    auto report = dc_.buildXLinkReport("X_LINK_ERROR", "getFrame", dev, sys);
    bool has_mss = false;
    for (const auto& cause : report.contributing_causes) {
        if (cause == "MSS_CPU_OVERLOAD") has_mss = true;
    }
    EXPECT_TRUE(has_mss);
}

// Frame starvation: time_since_last_frame > 5000ms → FRAME_STARVATION
TEST_F(BuildXLinkReportTest, FrameStarvation) {
    DeviceState dev;
    dev.temperature_celsius = 40.0;
    dev.usb_speed = "USB3";

    SystemDiagnostics sys;

    auto report = dc_.buildXLinkReport("X_LINK_ERROR", "getFrame", dev, sys, 6000);
    bool has_starvation = false;
    for (const auto& cause : report.contributing_causes) {
        if (cause == "FRAME_STARVATION") has_starvation = true;
    }
    EXPECT_TRUE(has_starvation);
}

// ---- parseKernelLogs tests ----

class ParseKernelLogsTest : public ::testing::Test {};

// Spec: "Parse dmesg output with USB errors"
TEST_F(ParseKernelLogsTest, UsbErrors) {
    std::string dmesg =
        "[12345.678] usb 1-1: reset high-speed USB device\n"
        "[12345.700] random kernel message\n"
        "[12345.800] usb 1-1: USB disconnect, device number 5\n";

    auto summary = DiagnosticsCollector::parseKernelLogs(dmesg);
    EXPECT_EQ(summary.filtered_lines.size(), 2u);
    EXPECT_TRUE(summary.has_relevant_entries);
}

// Spec: "Parse dmesg output with no relevant entries"
TEST_F(ParseKernelLogsTest, NoRelevantEntries) {
    std::string dmesg =
        "[12345.678] Memory cgroup stats\n"
        "[12345.700] CPU frequency scaling\n";

    auto summary = DiagnosticsCollector::parseKernelLogs(dmesg);
    EXPECT_EQ(summary.filtered_lines.size(), 0u);
    EXPECT_FALSE(summary.has_relevant_entries);
}

// Spec: "Parse empty dmesg output"
TEST_F(ParseKernelLogsTest, EmptyDmesg) {
    auto summary = DiagnosticsCollector::parseKernelLogs("");
    EXPECT_FALSE(summary.has_relevant_entries);
    EXPECT_TRUE(summary.filtered_lines.empty());
}

// Lines containing "error" or "fail" should also match
TEST_F(ParseKernelLogsTest, ErrorAndFailKeywords) {
    std::string dmesg =
        "[1.0] some error happened\n"
        "[2.0] something failed\n"
        "[3.0] all is well\n";

    auto summary = DiagnosticsCollector::parseKernelLogs(dmesg);
    EXPECT_EQ(summary.filtered_lines.size(), 2u);
    EXPECT_TRUE(summary.has_relevant_entries);
}

// Lines containing "reset" or "disconnect" should match
TEST_F(ParseKernelLogsTest, ResetAndDisconnectKeywords) {
    std::string dmesg =
        "[1.0] reset something\n"
        "[2.0] disconnect event\n"
        "[3.0] normal operation\n";

    auto summary = DiagnosticsCollector::parseKernelLogs(dmesg);
    EXPECT_EQ(summary.filtered_lines.size(), 2u);
}

// =========================================================================
// Task 2.7: CPU delta tracking across multiple calls
// =========================================================================

class CpuDeltaTrackingTest : public ::testing::Test {};

// Spec: "CPU delta tracking across multiple calls"
// Three successive calls: first=0%, second and third return correct delta
TEST_F(CpuDeltaTrackingTest, ThreeSuccessiveCalls) {
    DiagnosticsCollector dc;
    std::string meminfo = "";

    // Call 1: baseline (total=970, idle=810), returns 0%
    auto d1 = dc.captureSystemDiagnostics("cpu  100 0 50 800 10 5 5", meminfo);
    EXPECT_DOUBLE_EQ(d1.system_cpu_percent, 0.0);

    // Call 2: delta from call 1 (total=1940, idle=1620)
    // delta_total=970, delta_idle=810, cpu% = 100*(1-810/970) ≈ 16.49%
    auto d2 = dc.captureSystemDiagnostics("cpu  200 0 100 1600 20 10 10", meminfo);
    EXPECT_NEAR(d2.system_cpu_percent, 16.49, 0.1);

    // Call 3: delta from call 2 (total=2910, idle=2430)
    // delta_total=970, delta_idle=810, cpu% same ≈ 16.49%
    auto d3 = dc.captureSystemDiagnostics("cpu  300 0 150 2400 30 15 15", meminfo);
    EXPECT_NEAR(d3.system_cpu_percent, 16.49, 0.1);
}

// Spec: per-instance state, no static/global
TEST_F(CpuDeltaTrackingTest, PerInstanceState) {
    DiagnosticsCollector dc1;
    DiagnosticsCollector dc2;
    std::string meminfo = "";

    // dc1 gets baseline
    dc1.captureSystemDiagnostics("cpu  100 0 50 800 10 5 5", meminfo);

    // dc2 gets baseline — should also return 0%, not inherit dc1's state
    auto d2 = dc2.captureSystemDiagnostics("cpu  100 0 50 800 10 5 5", meminfo);
    EXPECT_DOUBLE_EQ(d2.system_cpu_percent, 0.0);

    // dc1 computes delta
    auto d1 = dc1.captureSystemDiagnostics("cpu  200 0 100 1600 20 10 10", meminfo);
    EXPECT_NEAR(d1.system_cpu_percent, 16.49, 0.1);

    // dc2 computes delta — its own independent delta
    auto d2b = dc2.captureSystemDiagnostics("cpu  200 0 100 1600 20 10 10", meminfo);
    EXPECT_NEAR(d2b.system_cpu_percent, 16.49, 0.1);
}

}  // namespace cotton_detection::test
