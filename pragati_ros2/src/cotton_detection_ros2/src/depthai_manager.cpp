#include "cotton_detection_ros2/depthai_manager.hpp"

// Heavy library includes (moved from header to reduce compilation memory)
#include <depthai/depthai.hpp>  // DepthAI SDK (unavoidable)

// Only include specific OpenCV modules needed for getRGBFrame()
#include <opencv2/core.hpp>     // cv::Mat, cv::merge
#include <opencv2/imgproc.hpp>  // cv::cvtColor

// Standard library includes
#include <rclcpp/rclcpp.hpp>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <array>
#include <memory>
#include <cstdio>
#include <deque>
#include <algorithm>

namespace cotton_detection {

// ============================================================================
// Implementation class (PImpl pattern)
// ============================================================================

class DepthAIManager::Impl {
public:
    Impl() = default;
    ~Impl() = default;

    // Logger callback for ROS2 integration
    LoggerCallback logger_;

    // Logging helper - uses callback if set, otherwise ROS2 logger
    void log(LogLevel level, const std::string& msg) {
        if (logger_) {
            logger_(level, msg);
        } else {
            auto ros_logger = rclcpp::get_logger("depthai_manager");
            switch (level) {
                case LogLevel::ERROR:
                    RCLCPP_ERROR(ros_logger, "%s", msg.c_str());
                    break;
                case LogLevel::WARN:
                    RCLCPP_WARN(ros_logger, "%s", msg.c_str());
                    break;
                case LogLevel::DEBUG:
                    RCLCPP_DEBUG(ros_logger, "%s", msg.c_str());
                    break;
                default:
                    RCLCPP_INFO(ros_logger, "%s", msg.c_str());
                    break;
            }
        }
    }

    // Device and pipeline
    std::unique_ptr<dai::Device> device_;
    std::shared_ptr<dai::Pipeline> pipeline_;

    // Output queues
    std::shared_ptr<dai::DataOutputQueue> detection_queue_;
    std::shared_ptr<dai::DataOutputQueue> rgb_queue_;
    std::shared_ptr<dai::DataOutputQueue> depth_queue_;

    // Input queues for camera control (pause/resume)
    std::shared_ptr<dai::DataInputQueue> color_control_queue_;
    std::shared_ptr<dai::DataInputQueue> mono_left_control_queue_;
    std::shared_ptr<dai::DataInputQueue> mono_right_control_queue_;

    // Camera pause state
    bool camera_paused_{false};

    // Configuration
    CameraConfig config_;
    std::string model_path_;
    bool initialized_{false};

    // Reconnection state (for X_LINK_ERROR recovery)
    bool needs_reconnect_{false};
    uint32_t reconnect_count_{0};        // Total successful reconnections
    uint32_t xlink_error_count_{0};      // Total XLink errors encountered
    uint32_t detection_timeout_count_{0}; // Detection queue timeouts
    uint32_t rgb_timeout_count_{0};       // RGB frame queue timeouts
    std::string usb_path_;                // USB device path (e.g., 1.1.2.1)

    // Downtime tracking (for optimization)
    std::chrono::milliseconds total_downtime_ms_{0};          // Cumulative reconnection downtime
    std::chrono::milliseconds last_reconnect_duration_ms_{0}; // Duration of last reconnection

    // Helper to detect X_LINK_ERROR from exception message
    static bool isXLinkError(const std::string& error_msg) {
        return error_msg.find("X_LINK_ERROR") != std::string::npos ||
               error_msg.find("Communication exception") != std::string::npos ||
               error_msg.find("device error/misconfiguration") != std::string::npos;
    }

    // Statistics
    std::chrono::steady_clock::time_point init_time_;
    uint64_t frames_processed_{0};
    size_t detection_count_{0};
    std::vector<std::chrono::milliseconds> latencies_;
    size_t frames_with_detections_{0};
    size_t total_detections_in_frame_{0};
    std::chrono::steady_clock::time_point last_stats_update_;

    // Frame delivery tracking (for health monitoring)
    std::chrono::steady_clock::time_point last_frame_time_;
    int64_t last_detection_seq_num_{-1};
    int64_t last_rgb_seq_num_{-1};
    uint64_t sync_mismatches_{0};

    // VPU device timestamp tracking (Task 7.2)
    std::deque<double> vpu_inference_times_ms_;
    static constexpr size_t MAX_VPU_SAMPLES = 100;

    // Exposure metadata tracking (Task 7.3)
    double last_exposure_us_{0.0};
    int last_sensitivity_iso_{0};
    std::deque<double> recent_exposures_us_;
    std::deque<int> recent_sensitivities_;
    static constexpr size_t MAX_EXPOSURE_SAMPLES = 100;

    // Sequence gap tracking (Task 7.4)
    uint64_t seq_frames_processed_{0};
    uint64_t seq_frames_dropped_{0};

    // Depth quality tracking (Task 7.5)
    uint64_t zero_spatial_rejections_{0};

    // Last frame's zero-spatial rejected detections (for diagnostic annotation)
    std::vector<ZeroSpatialInfo> last_zero_spatial_;

    // Thread safety
    mutable std::mutex mutex_;

    // Last known good state (captured before errors for diagnostics)
    double last_temperature_celsius_{0.0};
    double last_css_cpu_usage_{0.0};
    double last_mss_cpu_usage_{0.0};
    std::string last_usb_speed_{"unknown"};
    std::chrono::steady_clock::time_point last_successful_op_time_;

    // System diagnostics for XLink error root cause analysis
    struct SystemDiagnostics {
        // System resources
        double system_cpu_percent{0.0};
        double system_memory_percent{0.0};
        uint64_t system_memory_used_mb{0};
        uint64_t system_memory_total_mb{0};

        // USB diagnostics
        int usb_reset_count{0};
        int usb_error_count{0};
        std::string usb_device_state{"unknown"};
        std::string usb_driver_info{"unknown"};

        // DepthAI device info
        std::string device_serial{"unknown"};
        std::string device_firmware{"unknown"};
        std::string xlink_version{"unknown"};
        std::string device_name{"unknown"};

        // Pipeline state
        int detection_queue_depth{0};
        int rgb_queue_depth{0};
        int depth_queue_depth{0};
        bool pipeline_running{false};

        // Timing diagnostics
        std::chrono::milliseconds time_since_last_frame{0};
        std::chrono::milliseconds time_since_last_detection{0};
        int64_t last_frame_sequence{-1};
        int64_t last_detection_sequence{-1};

        // Power diagnostics (if available)
        double input_voltage{0.0};
        double current_draw_ma{0.0};
    } last_system_diagnostics_;

    // CPU usage tracking for captureSystemDiagnostics() (moved from static locals)
    long cpu_prev_total_{0};
    long cpu_prev_idle_{0};

    // Methods
    bool buildPipeline();
    bool validateConfig(const CameraConfig& config, std::string* error_msg = nullptr);
    std::optional<CottonDetection> convertDetection(const dai::SpatialImgDetection& det);
    void updateStats();

    // Capture device state for diagnostics (call periodically when healthy)
    void captureDeviceState() {
        if (!device_) return;
        try {
            auto chipTemp = device_->getChipTemperature();
            last_temperature_celsius_ = (chipTemp.average + chipTemp.css + chipTemp.mss + chipTemp.upa + chipTemp.dss) / 5.0;

            auto cpuUsage = device_->getLeonCssCpuUsage();
            last_css_cpu_usage_ = cpuUsage.average * 100.0;
            auto mssUsage = device_->getLeonMssCpuUsage();
            last_mss_cpu_usage_ = mssUsage.average * 100.0;

            last_usb_speed_ = device_->getUsbSpeed() == dai::UsbSpeed::SUPER ? "USB3" :
                              device_->getUsbSpeed() == dai::UsbSpeed::HIGH ? "USB2" : "USB1";

            last_successful_op_time_ = std::chrono::steady_clock::now();

            // Capture comprehensive system diagnostics
            captureSystemDiagnostics();
        } catch (const std::exception& e) {
            log(LogLevel::WARN, std::string("captureDeviceState: ") + e.what());
        } catch (...) {
            log(LogLevel::WARN, "captureDeviceState: unknown non-std::exception caught");
        }
    }

    // Capture system-level diagnostics for root cause analysis
    void captureSystemDiagnostics() {
        try {
            // System CPU and memory usage
            std::ifstream stat_file("/proc/stat");
            std::string line;
            if (std::getline(stat_file, line)) {
                std::istringstream iss(line);
                std::string cpu_label;
                long user, nice, system, idle, iowait, irq, softirq;
                iss >> cpu_label >> user >> nice >> system >> idle >> iowait >> irq >> softirq;
                long total = user + nice + system + idle + iowait + irq + softirq;
                long idle_total = idle + iowait;
                if (cpu_prev_total_ > 0) {
                    long total_diff = total - cpu_prev_total_;
                    long idle_diff = idle_total - cpu_prev_idle_;
                    if (total_diff > 0) {
                        last_system_diagnostics_.system_cpu_percent = 100.0 * (1.0 - static_cast<double>(idle_diff) / total_diff);
                    }
                }
                cpu_prev_total_ = total;
                cpu_prev_idle_ = idle_total;
            }

            // System memory
            std::ifstream meminfo("/proc/meminfo");
            std::string mem_line;
            while (std::getline(meminfo, mem_line)) {
                if (mem_line.find("MemTotal:") == 0) {
                    std::istringstream iss(mem_line.substr(9));
                    iss >> last_system_diagnostics_.system_memory_total_mb;
                    last_system_diagnostics_.system_memory_total_mb /= 1024; // Convert to MB
                } else if (mem_line.find("MemAvailable:") == 0) {
                    std::istringstream iss(mem_line.substr(13));
                    long available_kb;
                    iss >> available_kb;
                    available_kb /= 1024; // Convert to MB
                    last_system_diagnostics_.system_memory_used_mb = last_system_diagnostics_.system_memory_total_mb - available_kb;
                    if (last_system_diagnostics_.system_memory_total_mb > 0) {
                        last_system_diagnostics_.system_memory_percent = 100.0 *
                            (1.0 - static_cast<double>(available_kb) / last_system_diagnostics_.system_memory_total_mb);
                    }
                    break;
                }
            }

            // DepthAI device information
            if (device_) {
                try {
                    last_system_diagnostics_.device_serial = device_->getDeviceName();
                    last_system_diagnostics_.device_name = device_->getDeviceName();

                    // Get firmware version if available
                    try {
                        auto bootInfo = device_->getBootloaderVersion();
                        if (bootInfo.has_value()) {
                            last_system_diagnostics_.device_firmware = bootInfo.value().toString();
                        } else {
                            last_system_diagnostics_.device_firmware = "not_bootloader";
                        }
                    } catch (const std::exception& e) {
                        log(LogLevel::WARN, std::string("captureSystemDiagnostics/getBootloaderVersion: ") + e.what());
                        last_system_diagnostics_.device_firmware = "unknown";
                    } catch (...) {
                        log(LogLevel::WARN, "captureSystemDiagnostics/getBootloaderVersion: unknown non-std::exception caught");
                        last_system_diagnostics_.device_firmware = "unknown";
                    }

                    // XLink version - try to get from device info or use placeholder
                    try {
                        // Try to get XLink version from device info if available
                        last_system_diagnostics_.xlink_version = "XLink_unknown";
                    } catch (const std::exception& e) {
                        log(LogLevel::WARN, std::string("captureSystemDiagnostics/getXLinkVersion: ") + e.what());
                        last_system_diagnostics_.xlink_version = "XLink_unknown";
                    } catch (...) {
                        log(LogLevel::WARN, "captureSystemDiagnostics/getXLinkVersion: unknown non-std::exception caught");
                        last_system_diagnostics_.xlink_version = "XLink_unknown";
                    }
                } catch (const std::exception& e) {
                    log(LogLevel::WARN, std::string("captureSystemDiagnostics/getDeviceInfo: ") + e.what());
                    last_system_diagnostics_.device_serial = "unknown";
                    last_system_diagnostics_.device_name = "unknown";
                } catch (...) {
                    log(LogLevel::WARN, "captureSystemDiagnostics/getDeviceInfo: unknown non-std::exception caught");
                    last_system_diagnostics_.device_serial = "unknown";
                    last_system_diagnostics_.device_name = "unknown";
                }
            }

            // Queue depths
            last_system_diagnostics_.detection_queue_depth = detection_queue_ ? detection_queue_->getMaxSize() : 0;
            last_system_diagnostics_.rgb_queue_depth = rgb_queue_ ? rgb_queue_->getMaxSize() : 0;
            last_system_diagnostics_.depth_queue_depth = depth_queue_ ? depth_queue_->getMaxSize() : 0;

            // Pipeline state
            last_system_diagnostics_.pipeline_running = initialized_ && device_ && pipeline_;

            // Timing diagnostics
            auto now = std::chrono::steady_clock::now();
            last_system_diagnostics_.time_since_last_frame = std::chrono::duration_cast<std::chrono::milliseconds>(
                now - last_frame_time_);
            last_system_diagnostics_.time_since_last_detection = std::chrono::duration_cast<std::chrono::milliseconds>(
                now - last_successful_op_time_);
            last_system_diagnostics_.last_frame_sequence = last_rgb_seq_num_;
            last_system_diagnostics_.last_detection_sequence = last_detection_seq_num_;

            // Capture USB diagnostics
            captureUSBState();

        } catch (const std::exception& e) {
            log(LogLevel::WARN, std::string("captureSystemDiagnostics: ") + e.what());
        } catch (...) {
            log(LogLevel::WARN, "captureSystemDiagnostics: unknown non-std::exception caught");
        }
    }

    // Capture USB device state and error counters
    void captureUSBState() {
        try {
            // Try to get USB device information from sysfs
            std::string usb_path = "/sys/bus/usb/devices/";
            std::filesystem::directory_iterator dir_iter(usb_path, std::filesystem::directory_options::skip_permission_denied);

            for (const auto& entry : dir_iter) {
                std::string dev_path = entry.path().string();
                std::string product_file = dev_path + "/product";
                std::string idVendor_file = dev_path + "/idVendor";
                std::string idProduct_file = dev_path + "/idProduct";

                // Check if this is a DepthAI device (Luxonis vendor ID: 03e7)
                std::ifstream vendor_file(idVendor_file);
                std::string vendor_id;
                if (vendor_file >> vendor_id && vendor_id == "03e7") {
                    // Found DepthAI device
                    last_system_diagnostics_.usb_device_state = "Connected";

                    // Get product name
                    std::ifstream product_file_stream(product_file);
                    std::string product_name;
                    if (std::getline(product_file_stream, product_name)) {
                        last_system_diagnostics_.usb_driver_info = product_name;
                    }

                    // Check for USB error counters
                    std::string urb_file = dev_path + "/urbnum";
                    if (std::filesystem::exists(urb_file)) {
                        last_system_diagnostics_.usb_device_state = "Active";
                    }

                    // Look for error indicators
                    std::string status_file = dev_path + "/status";
                    std::ifstream status_stream(status_file);
                    std::string status;
                    if (status_stream >> status) {
                        if (status != "configured") {
                            last_system_diagnostics_.usb_device_state = "Error: " + status;
                            last_system_diagnostics_.usb_error_count++;
                        }
                    }

                    break; // Found our device
                }
            }
        } catch (const std::exception& e) {
            log(LogLevel::WARN, std::string("captureUSBState: ") + e.what());
            last_system_diagnostics_.usb_device_state = "Unknown";
            last_system_diagnostics_.usb_driver_info = "Unknown";
        } catch (...) {
            log(LogLevel::WARN, "captureUSBState: unknown non-std::exception caught");
            last_system_diagnostics_.usb_device_state = "Unknown";
            last_system_diagnostics_.usb_driver_info = "Unknown";
        }
    }

    // Capture recent kernel logs related to USB and device issues
    // NOTE: popen() can block and should not be called under mutex_.
    // captureKernelLogs() stores the result in captured_dmesg_output_ so that
    // logXLinkErrorContext() can call it BEFORE acquiring the lock, then log
    // the result after acquiring the lock.
    std::string captured_dmesg_output_;  // Holds dmesg output captured outside mutex

    void captureKernelLogsToBuffer() {
        try {
            // Get recent dmesg entries (last 50 lines)
            // This call may block — must be called OUTSIDE mutex scope
            std::array<char, 128> buffer;
            std::string result;
            using PipeCloser = int(*)(FILE*);
            std::unique_ptr<FILE, PipeCloser> pipe(popen("dmesg | tail -50", "r"), static_cast<PipeCloser>(pclose));
            if (!pipe) {
                captured_dmesg_output_.clear();
                return;
            }

            while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr) {
                result += buffer.data();
            }
            captured_dmesg_output_ = std::move(result);
        } catch (const std::exception& e) {
            log(LogLevel::WARN, std::string("captureKernelLogsToBuffer: ") + e.what());
            captured_dmesg_output_.clear();
        } catch (...) {
            log(LogLevel::WARN, "captureKernelLogsToBuffer: unknown non-std::exception caught");
            captured_dmesg_output_.clear();
        }
    }

    // Log previously captured kernel log output (safe to call under mutex)
    void logCapturedKernelLogs() {
        if (captured_dmesg_output_.empty()) {
            log(LogLevel::ERROR, "   Kernel logs: Failed to capture dmesg");
            return;
        }

        // Look for USB-related errors in the last few minutes
        log(LogLevel::ERROR, "🔧 RECENT KERNEL LOGS (USB/DEVICE ERRORS):");
        std::istringstream iss(captured_dmesg_output_);
        std::string line;
        bool found_errors = false;

        while (std::getline(iss, line)) {
            // Look for USB, device, or error-related messages
            if (line.find("usb") != std::string::npos ||
                line.find("USB") != std::string::npos ||
                line.find("device") != std::string::npos ||
                line.find("error") != std::string::npos ||
                line.find("fail") != std::string::npos ||
                line.find("reset") != std::string::npos ||
                line.find("disconnect") != std::string::npos) {
                log(LogLevel::ERROR, "   " + line);
                found_errors = true;
            }
        }

        if (!found_errors) {
            log(LogLevel::ERROR, "   No USB/device errors found in recent kernel logs");
        }
        log(LogLevel::ERROR, "");
    }

    // Log comprehensive device and system state at moment of XLink error
    void logXLinkErrorContext(const std::string& error_msg, const std::string& operation) {
        auto time_since_success = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - last_successful_op_time_).count();

        log(LogLevel::ERROR, "🔴 X_LINK_ERROR ROOT CAUSE ANALYSIS:");
        log(LogLevel::ERROR, "═══════════════════════════════════════════════════════════════");
        log(LogLevel::ERROR, "   OPERATION: " + operation);
        log(LogLevel::ERROR, "   ERROR MESSAGE: " + error_msg);
        log(LogLevel::ERROR, "");

        // Capture recent kernel logs for USB/driver issues
        // captureKernelLogsToBuffer() is safe outside mutex; we call it here since
        // logXLinkErrorContext() may already be called under mutex_ by callers.
        // The popen() inside only writes to captured_dmesg_output_ (no shared state).
        captureKernelLogsToBuffer();
        logCapturedKernelLogs();
        log(LogLevel::ERROR, "📱 DEVICE HARDWARE STATE:");
        log(LogLevel::ERROR, "   Device Name: " + last_system_diagnostics_.device_name);
        log(LogLevel::ERROR, "   Serial Number: " + last_system_diagnostics_.device_serial);
        log(LogLevel::ERROR, "   Firmware Version: " + last_system_diagnostics_.device_firmware);
        log(LogLevel::ERROR, "   XLink Protocol: " + last_system_diagnostics_.xlink_version);
        log(LogLevel::ERROR, "   Temperature: " + std::to_string(last_temperature_celsius_) + "°C");
        log(LogLevel::ERROR, "   CSS CPU Usage: " + std::to_string(last_css_cpu_usage_) + "%");
        log(LogLevel::ERROR, "   MSS CPU Usage: " + std::to_string(last_mss_cpu_usage_) + "%");
        log(LogLevel::ERROR, "");

        // USB Connection State
        log(LogLevel::ERROR, "🔌 USB CONNECTION STATE:");
        log(LogLevel::ERROR, "   USB Speed: " + last_usb_speed_);
        log(LogLevel::ERROR, "   USB Path: " + usb_path_);
        log(LogLevel::ERROR, "   USB Device State: " + last_system_diagnostics_.usb_device_state);
        log(LogLevel::ERROR, "   USB Driver: " + last_system_diagnostics_.usb_driver_info);
        log(LogLevel::ERROR, "   USB Reset Count: " + std::to_string(last_system_diagnostics_.usb_reset_count));
        log(LogLevel::ERROR, "   USB Error Count: " + std::to_string(last_system_diagnostics_.usb_error_count));
        log(LogLevel::ERROR, "");

        // System Resources
        log(LogLevel::ERROR, "💻 SYSTEM RESOURCES:");
        log(LogLevel::ERROR, "   System CPU Usage: " + std::to_string(last_system_diagnostics_.system_cpu_percent) + "%");
        log(LogLevel::ERROR, "   System Memory: " + std::to_string(last_system_diagnostics_.system_memory_used_mb) + "/" +
                           std::to_string(last_system_diagnostics_.system_memory_total_mb) + " MB (" +
                           std::to_string(last_system_diagnostics_.system_memory_percent) + "%)");
        log(LogLevel::ERROR, "");

        // Pipeline State
        log(LogLevel::ERROR, "🔧 PIPELINE STATE:");
        log(LogLevel::ERROR, "   Pipeline Running: " + std::string(last_system_diagnostics_.pipeline_running ? "YES" : "NO"));
        log(LogLevel::ERROR, "   Detection Queue Depth: " + std::to_string(last_system_diagnostics_.detection_queue_depth));
        log(LogLevel::ERROR, "   RGB Queue Depth: " + std::to_string(last_system_diagnostics_.rgb_queue_depth));
        log(LogLevel::ERROR, "   Depth Queue Depth: " + std::to_string(last_system_diagnostics_.depth_queue_depth));
        log(LogLevel::ERROR, "");

        // Timing Analysis
        log(LogLevel::ERROR, "⏱️  TIMING ANALYSIS:");
        log(LogLevel::ERROR, "   Time Since Last Success: " + std::to_string(time_since_success) + "ms");
        log(LogLevel::ERROR, "   Time Since Last Frame: " + std::to_string(last_system_diagnostics_.time_since_last_frame.count()) + "ms");
        log(LogLevel::ERROR, "   Time Since Last Detection: " + std::to_string(last_system_diagnostics_.time_since_last_detection.count()) + "ms");
        log(LogLevel::ERROR, "   Last Frame Sequence: " + std::to_string(last_system_diagnostics_.last_frame_sequence));
        log(LogLevel::ERROR, "   Last Detection Sequence: " + std::to_string(last_system_diagnostics_.last_detection_sequence));
        log(LogLevel::ERROR, "");

        // Statistics
        log(LogLevel::ERROR, "📊 STATISTICS:");
        log(LogLevel::ERROR, "   Total Frames Processed: " + std::to_string(frames_processed_));
        log(LogLevel::ERROR, "   Total XLink Errors: " + std::to_string(xlink_error_count_ + 1));
        log(LogLevel::ERROR, "   Total Reconnections: " + std::to_string(reconnect_count_));
        log(LogLevel::ERROR, "");

        // Power Diagnostics (if available)
        if (last_system_diagnostics_.input_voltage > 0.0) {
            log(LogLevel::ERROR, "⚡ POWER DIAGNOSTICS:");
            log(LogLevel::ERROR, "   Input Voltage: " + std::to_string(last_system_diagnostics_.input_voltage) + "V");
            log(LogLevel::ERROR, "   Current Draw: " + std::to_string(last_system_diagnostics_.current_draw_ma) + "mA");
            log(LogLevel::ERROR, "");
        }

        // Root Cause Analysis Hints
        log(LogLevel::ERROR, "🎯 ROOT CAUSE ANALYSIS:");
        std::string hints = analyzeXLinkError(error_msg, operation);
        log(LogLevel::ERROR, "   " + hints);
        log(LogLevel::ERROR, "═══════════════════════════════════════════════════════════════");
    }

    // Analyze XLink error and provide root cause hints
    std::string analyzeXLinkError(const std::string& error_msg, [[maybe_unused]] const std::string& operation) {
        std::vector<std::string> causes;

        // Temperature-related issues
        if (last_temperature_celsius_ > 85.0) {
            causes.push_back("HIGH TEMPERATURE: Device thermal throttling likely");
        } else if (last_temperature_celsius_ > 75.0) {
            causes.push_back("ELEVATED TEMPERATURE: May contribute to instability");
        }

        // USB-related issues
        if (last_usb_speed_ == "USB2" || last_usb_speed_ == "USB1") {
            causes.push_back("USB SPEED: Operating at reduced speed - check cable/port/hub");
        }

        // CPU overload
        if (last_css_cpu_usage_ > 90.0) {
            causes.push_back("CSS CPU OVERLOAD: Camera ISP overloaded");
        }
        if (last_mss_cpu_usage_ > 95.0) {
            causes.push_back("MSS CPU OVERLOAD: Neural network inference overloaded");
        }

        // System resource issues
        if (last_system_diagnostics_.system_cpu_percent > 90.0) {
            causes.push_back("SYSTEM CPU OVERLOAD: Host CPU contention");
        }
        if (last_system_diagnostics_.system_memory_percent > 95.0) {
            causes.push_back("SYSTEM MEMORY LOW: Host memory pressure");
        }

        // Timing issues
        if (last_system_diagnostics_.time_since_last_frame.count() > 5000) {
            causes.push_back("FRAME STARVATION: No frames received for 5+ seconds");
        }

        // Error message analysis
        if (error_msg.find("Communication exception") != std::string::npos) {
            causes.push_back("COMMUNICATION FAILURE: XLink protocol error");
        }
        if (error_msg.find("device error/misconfiguration") != std::string::npos) {
            causes.push_back("DEVICE MISCONFIGURATION: Pipeline or device setup issue");
        }
        if (error_msg.find("timeout") != std::string::npos) {
            causes.push_back("OPERATION TIMEOUT: Device not responding");
        }

        if (causes.empty()) {
            return "UNKNOWN CAUSE: Insufficient diagnostic data for analysis";
        }

        std::string result = "POTENTIAL CAUSES: ";
        for (size_t i = 0; i < causes.size(); ++i) {
            if (i > 0) result += " | ";
            result += causes[i];
        }
        return result;
    }
};

// ============================================================================
// DepthAIManager public interface
// ============================================================================

DepthAIManager::DepthAIManager()
    : pImpl_(std::make_unique<Impl>()) {
}

DepthAIManager::~DepthAIManager() {
    // NOTE: Do NOT call shutdown() in destructor if already called explicitly
    // shutdown() should be called explicitly before destruction to allow proper cleanup
    // If shutdown wasn't called, this is a programming error but we'll try anyway
    if (pImpl_ && pImpl_->initialized_) {
        try {
            shutdown();
        } catch (...) {
            pImpl_->log(LogLevel::WARN, "Exception in destructor during shutdown - suppressing");
        }
    }
}

DepthAIManager::DepthAIManager(DepthAIManager&&) noexcept = default;
DepthAIManager& DepthAIManager::operator=(DepthAIManager&&) noexcept = default;

bool DepthAIManager::initialize(const std::string& model_path, const CameraConfig& config) {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    try {
        // Validate configuration before proceeding
        std::string validation_error;
        if (!pImpl_->validateConfig(config, &validation_error)) {
            pImpl_->log(LogLevel::ERROR, "Invalid configuration: " + validation_error);
            return false;
        }

        pImpl_->log(LogLevel::INFO, "Initializing with model: " + model_path);

        // Store configuration
        pImpl_->model_path_ = model_path;
        pImpl_->config_ = config;

        // Build pipeline
        if (!pImpl_->buildPipeline()) {
            pImpl_->log(LogLevel::ERROR, "Failed to build pipeline");
            return false;
        }

        // Device preflight: enumerate devices so failures are actionable
        // NOTE: this distinguishes "no camera connected" vs "camera connected but busy".
        const auto connected_devices = dai::DeviceBase::getAllConnectedDevices();
        const auto available_devices = dai::DeviceBase::getAllAvailableDevices();

        pImpl_->log(LogLevel::INFO, "DepthAI devices connected: " + std::to_string(connected_devices.size()));
        for (const auto & d : connected_devices) {
            pImpl_->log(LogLevel::INFO, "  - " + d.name + " (mxid=" + d.getMxId() + ")");
        }

        pImpl_->log(LogLevel::INFO, "DepthAI devices available: " + std::to_string(available_devices.size()));
        for (const auto & d : available_devices) {
            pImpl_->log(LogLevel::INFO, "  - " + d.name + " (mxid=" + d.getMxId() + ")");
        }

        auto mxid_in_list = [](const std::vector<dai::DeviceInfo> & list, const std::string & mxid) -> bool {
            for (const auto & d : list) {
                if (d.getMxId() == mxid) return true;
            }
            return false;
        };

        if (!config.device_id.empty()) {
            if (!mxid_in_list(connected_devices, config.device_id)) {
                pImpl_->log(LogLevel::ERROR, "Requested DepthAI device_id not found: " + config.device_id);
                return false;
            }
            if (!mxid_in_list(available_devices, config.device_id)) {
                pImpl_->log(LogLevel::ERROR, "Requested DepthAI device is connected but not available (busy/in use): " + config.device_id);
                return false;
            }
        } else {
            if (connected_devices.empty()) {
                pImpl_->log(LogLevel::ERROR, "No DepthAI devices detected. Check USB connection/power.");
                return false;
            }
            if (available_devices.empty()) {
                pImpl_->log(LogLevel::ERROR, "DepthAI device(s) detected but none are available (busy/in use). Close other camera processes or reboot the device.");
                return false;
            }
        }

        // Connect to device with auto-detected USB speed
        // Use SUPER_PLUS to allow the device to negotiate the best available speed
        // This will use USB 3.0 (5Gbps) if available, otherwise fall back to USB 2.0 (480Mbps)
        pImpl_->log(LogLevel::INFO, "Connecting to device (auto-detect USB speed)...");

        if (!config.device_id.empty()) {
            // Connect to specific device
            pImpl_->log(LogLevel::INFO, "Connecting to device: " + config.device_id);
            dai::DeviceInfo info(config.device_id);
            pImpl_->device_ = std::make_unique<dai::Device>(*pImpl_->pipeline_, info);
            pImpl_->usb_path_ = info.name;  // Store USB path
        } else {
            // Connect to first available device
            pImpl_->log(LogLevel::INFO, "Connecting to first available device");
            pImpl_->device_ = std::make_unique<dai::Device>(*pImpl_->pipeline_);
            // Get USB path from first available device
            if (!available_devices.empty()) {
                pImpl_->usb_path_ = available_devices[0].name;
            }
        }

        // Log the actual USB speed negotiated
        auto usbSpeed = pImpl_->device_->getUsbSpeed();
        std::string speedStr;
        switch (usbSpeed) {
            case dai::UsbSpeed::SUPER_PLUS:
                speedStr = "USB 3.1 (10Gbps)";
                break;
            case dai::UsbSpeed::SUPER:
                speedStr = "USB 3.0 (5Gbps)";
                break;
            case dai::UsbSpeed::HIGH:
                speedStr = "USB 2.0 (480Mbps)";
                break;
            case dai::UsbSpeed::FULL:
                speedStr = "USB 1.1 (12Mbps)";
                break;
            case dai::UsbSpeed::LOW:
                speedStr = "USB 1.0 (1.5Mbps)";
                break;
            default:
                speedStr = "Unknown";
                break;
        }
        pImpl_->log(LogLevel::INFO, "Device connected at " + speedStr);

        // Warn if running at USB 2.0 - may limit performance
        if (usbSpeed == dai::UsbSpeed::HIGH || usbSpeed == dai::UsbSpeed::FULL || usbSpeed == dai::UsbSpeed::LOW) {
            pImpl_->log(LogLevel::WARN, "Running at USB 2.0 speed - consider using USB 3.0 port for better performance");
        }

        // Get output queues with non-blocking mode to prevent indefinite hangs
        // maxSize=2: Small queue since we flush stale frames anyway before each detection
        // blocking=false prevents hangs when camera pipeline stalls (thermal/USB issues)
        // With size 2: max 1 stale frame to flush, then wait ~33ms for fresh frame at 30 FPS
        pImpl_->detection_queue_ = pImpl_->device_->getOutputQueue("detections", 2, false);
        pImpl_->rgb_queue_ = pImpl_->device_->getOutputQueue("rgb", 2, false);
        if (config.enable_depth) {
            pImpl_->depth_queue_ = pImpl_->device_->getOutputQueue("depth", 2, false);
        }

        // Get input queues for camera control (pause/resume)
        // These allow runtime control of camera streaming without pipeline restart
        pImpl_->color_control_queue_ = pImpl_->device_->getInputQueue("colorCamControl");
        if (config.enable_depth) {
            pImpl_->mono_left_control_queue_ = pImpl_->device_->getInputQueue("monoLeftControl");
            pImpl_->mono_right_control_queue_ = pImpl_->device_->getInputQueue("monoRightControl");
        }

        pImpl_->log(LogLevel::INFO, "Output and control queues created");

        // Mark as initialized
        pImpl_->initialized_ = true;
        pImpl_->init_time_ = std::chrono::steady_clock::now();

        pImpl_->log(LogLevel::INFO, "Initialization successful");
        return true;

    } catch (const std::exception& e) {
        pImpl_->log(LogLevel::ERROR, std::string("Initialization failed: ") + e.what());
        return false;
    }
}

void DepthAIManager::shutdown() {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_) {
        return;
    }

    pImpl_->log(LogLevel::INFO, "Shutting down...");

    try {
        // CRITICAL FIX: Proper shutdown sequence to avoid USB thread errors
        // The DepthAI library has internal USB threads that need time to stop

        // Step 1: Drain all queues to prevent threads from blocking
        pImpl_->log(LogLevel::DEBUG, "Draining queues...");
        if (pImpl_->detection_queue_) {
            while (pImpl_->detection_queue_->has<dai::SpatialImgDetections>()) {
                pImpl_->detection_queue_->tryGet<dai::SpatialImgDetections>();
            }
        }
        if (pImpl_->rgb_queue_) {
            while (pImpl_->rgb_queue_->has<dai::ImgFrame>()) {
                pImpl_->rgb_queue_->tryGet<dai::ImgFrame>();
            }
        }
        if (pImpl_->depth_queue_) {
            while (pImpl_->depth_queue_->has<dai::ImgFrame>()) {
                pImpl_->depth_queue_->tryGet<dai::ImgFrame>();
            }
        }

        // Step 2: Release queues first to stop data flow
        pImpl_->log(LogLevel::DEBUG, "Releasing queues...");
        pImpl_->detection_queue_.reset();
        pImpl_->rgb_queue_.reset();
        pImpl_->depth_queue_.reset();
        pImpl_->color_control_queue_.reset();
        pImpl_->mono_left_control_queue_.reset();
        pImpl_->mono_right_control_queue_.reset();

        // Step 3: Wait for queue polling to stop (threads check every 2ms)
        // BLOCKING_SLEEP_OK: device close wait 20ms, executor-thread (caller's callback group) — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(20));

        // Step 4: CRITICAL FIX - Stop device threads BEFORE closing
        if (pImpl_->device_) {
            pImpl_->log(LogLevel::DEBUG, "Stopping device threads...");
            try {
                // This stops all internal DepthAI threads (USB, XLink, etc.)
                if (pImpl_->device_->isClosed() == false) {
                    // Request all threads to stop by closing XLink streams
                    pImpl_->device_->close();
                }
            } catch (const std::exception& e) {
                pImpl_->log(LogLevel::WARN, std::string("Warning during device close: ") + e.what());
            }

            // CRITICAL: Give USB threads time to detect closed state and exit
            // Reduced from 1000ms to 200ms for faster shutdown
            pImpl_->log(LogLevel::DEBUG, "Waiting for USB threads to terminate...");
            // BLOCKING_SLEEP_OK: USB cleanup wait 200ms, executor-thread (caller's callback group) — reviewed 2026-03-14
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
        }

        // Step 5: Finally release device object
        pImpl_->log(LogLevel::DEBUG, "Releasing device object...");
        pImpl_->device_.reset();

        // Step 6: Final wait for complete cleanup (reduced from 100ms to 50ms)
        // BLOCKING_SLEEP_OK: post-close drain 50ms, executor-thread (caller's callback group) — reviewed 2026-03-14
        std::this_thread::sleep_for(std::chrono::milliseconds(50));

        pImpl_->initialized_ = false;
        pImpl_->camera_paused_ = false;

        pImpl_->log(LogLevel::INFO, "Shutdown complete");

    } catch (const std::exception& e) {
        pImpl_->log(LogLevel::ERROR, std::string("Error during shutdown: ") + e.what());
        // Continue with cleanup even if there's an error
        pImpl_->detection_queue_.reset();
        pImpl_->rgb_queue_.reset();
        pImpl_->depth_queue_.reset();
        pImpl_->color_control_queue_.reset();
        pImpl_->mono_left_control_queue_.reset();
        pImpl_->mono_right_control_queue_.reset();
        pImpl_->device_.reset();
        pImpl_->initialized_ = false;
        pImpl_->camera_paused_ = false;
    }
}

bool DepthAIManager::isInitialized() const {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    return pImpl_->initialized_;
}

bool DepthAIManager::isHealthy() const {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_ || !pImpl_->device_) {
        return false;
    }

    // Check if reconnection is needed (X_LINK_ERROR detected)
    if (pImpl_->needs_reconnect_) {
        return false;
    }

    // Check frame delivery - REMOVED time-based check for on-demand system
    // We only rely on X_LINK_ERROR (needs_reconnect_) to detect failures
    // because in idle mode we don't process frames, so time_since_last_frame would naturally grow large.

    return true;
}

std::optional<std::vector<CottonDetection>>
DepthAIManager::getDetections(std::chrono::milliseconds timeout) {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_ || !pImpl_->detection_queue_) {
        return std::nullopt;
    }

    try {
        auto start_time = std::chrono::steady_clock::now();

        // Get detections using polling loop with timeout to prevent infinite hang
        std::shared_ptr<dai::SpatialImgDetections> inDet;

        // Poll the queue with timeout - prevents hanging if camera stops producing frames
        // This is safer than blocking get() which can hang forever
        auto deadline = start_time + timeout;
        while (!inDet && std::chrono::steady_clock::now() < deadline) {
            inDet = pImpl_->detection_queue_->tryGet<dai::SpatialImgDetections>();
            if (!inDet) {
                // Sleep briefly to avoid busy-waiting (2ms optimized from 10ms)
                // BLOCKING_SLEEP_OK: tryGet retry 2ms, executor-thread (detection_group_) — reviewed 2026-03-14
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
            }
        }

        if (!inDet) {
            // No detections available within timeout (not an error)
            // Could be: empty frame, camera busy, or thermal throttling
            return std::vector<CottonDetection>();
        }

        // Task 7.4: Track sequence number gaps for frame drop detection
        {
            int64_t seq = inDet->getSequenceNum();
            pImpl_->seq_frames_processed_++;
            if (pImpl_->last_detection_seq_num_ >= 0) {
                int64_t expected_seq = pImpl_->last_detection_seq_num_ + 1;
                if (seq > expected_seq) {
                    uint64_t dropped = static_cast<uint64_t>(seq - expected_seq);
                    pImpl_->seq_frames_dropped_ += dropped;
                }
            }
            pImpl_->last_detection_seq_num_ = seq;
        }

        // Convert detections
        std::vector<CottonDetection> results;
        results.reserve(inDet->detections.size());
        pImpl_->last_zero_spatial_.clear();  // Reset per-frame rejected list

        for (const auto& det : inDet->detections) {
            auto converted = pImpl_->convertDetection(det);
            if (converted.has_value()) {
                results.push_back(std::move(*converted));
            }
        }

        // Update statistics
        pImpl_->last_frame_time_ = std::chrono::steady_clock::now();
        pImpl_->frames_processed_++;
        pImpl_->detection_count_ += results.size();
        if (!results.empty()) {
            pImpl_->frames_with_detections_++;
            pImpl_->total_detections_in_frame_ += results.size();
        }

        auto end_time = std::chrono::steady_clock::now();
        auto latency = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);
        pImpl_->latencies_.push_back(latency);

        // Keep only last 100 latency measurements
        if (pImpl_->latencies_.size() > 100) {
            pImpl_->latencies_.erase(pImpl_->latencies_.begin());
        }

        return results;

    } catch (const std::exception& e) {
        std::string error_msg = e.what();
        pImpl_->log(LogLevel::ERROR, std::string("Error getting detections: ") + error_msg);

        // Detect X_LINK_ERROR and set reconnection flag
        if (Impl::isXLinkError(error_msg)) {
            pImpl_->logXLinkErrorContext(error_msg, "getDetections");
            pImpl_->needs_reconnect_ = true;
            pImpl_->xlink_error_count_++;
        }
        return std::nullopt;
    }
}

bool DepthAIManager::hasDetections() const {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_ || !pImpl_->detection_queue_) {
        return false;
    }

    // HEALTH CHECK: Detect USB disconnect / device death before touching queues.
    // When USB is physically unplugged, the DepthAI watchdog marks the device closed.
    // Queue operations on a dead device may return garbage silently instead of throwing,
    // so we must check isClosed() explicitly to catch hot-swap disconnects.
    if (pImpl_->device_ && pImpl_->device_->isClosed()) {
        pImpl_->log(LogLevel::ERROR, "Device is closed (USB disconnected?) - triggering reconnect");
        pImpl_->needs_reconnect_ = true;
        pImpl_->xlink_error_count_++;
        return false;
    }

    try {
        return pImpl_->detection_queue_->has<dai::SpatialImgDetections>();
    } catch (const std::exception& e) {
        std::string error_msg = e.what();
        pImpl_->log(LogLevel::ERROR, std::string("Error checking detections: ") + error_msg);

        // Detect X_LINK_ERROR and set reconnection flag
        if (Impl::isXLinkError(error_msg)) {
            pImpl_->logXLinkErrorContext(error_msg, "hasDetections");
            pImpl_->needs_reconnect_ = true;
            pImpl_->xlink_error_count_++;
        }
        return false;
    }
}

int DepthAIManager::flushDetections() {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_ || !pImpl_->detection_queue_) {
        return 0;
    }

    int flushed = 0;
    try {
        // Efficiently flush all pending detections using non-blocking tryGet
        // This is more efficient than the hasDetections() + getDetections() loop
        // because it avoids repeated mutex locks and the 2ms polling sleep
        while (auto det = pImpl_->detection_queue_->tryGet<dai::SpatialImgDetections>()) {
            flushed++;
            // Safety limit to prevent infinite loop in case of unexpected behavior
            if (flushed > 100) {
                pImpl_->log(LogLevel::WARN, "flushDetections: Hit safety limit (100 frames)");
                break;
            }
        }
    } catch (const std::exception& e) {
        std::string error_msg = e.what();
        pImpl_->log(LogLevel::ERROR, std::string("Error flushing detections: ") + error_msg);

        // Detect X_LINK_ERROR and set reconnection flag
        if (Impl::isXLinkError(error_msg)) {
            pImpl_->logXLinkErrorContext(error_msg, "flushDetections");
            pImpl_->needs_reconnect_ = true;
            pImpl_->xlink_error_count_++;
        }
    }

    return flushed;
}

int DepthAIManager::flushAllQueues() {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_) {
        return 0;
    }

    int flushed = 0;
    int detection_flushed = 0;
    int rgb_flushed = 0;
    int depth_flushed = 0;

    try {
        // Flush detection queue
        if (pImpl_->detection_queue_) {
            while (auto det = pImpl_->detection_queue_->tryGet<dai::SpatialImgDetections>()) {
                detection_flushed++;
                if (detection_flushed > 100) break;  // Safety limit
            }
        }

        // Flush RGB queue - CRITICAL for synchronization!
        // Without this, RGB frames can be from different frame than detection
        if (pImpl_->rgb_queue_) {
            while (auto rgb = pImpl_->rgb_queue_->tryGet<dai::ImgFrame>()) {
                rgb_flushed++;
                if (rgb_flushed > 100) break;  // Safety limit
            }
        }

        // Flush depth queue if enabled
        if (pImpl_->depth_queue_) {
            while (auto depth = pImpl_->depth_queue_->tryGet<dai::ImgFrame>()) {
                depth_flushed++;
                if (depth_flushed > 100) break;  // Safety limit
            }
        }

        flushed = detection_flushed + rgb_flushed + depth_flushed;

        if (flushed > 0) {
            pImpl_->log(LogLevel::DEBUG,
                "Flushed all queues: detection=" + std::to_string(detection_flushed) +
                ", rgb=" + std::to_string(rgb_flushed) +
                ", depth=" + std::to_string(depth_flushed));
        }

    } catch (const std::exception& e) {
        std::string error_msg = e.what();
        pImpl_->log(LogLevel::ERROR, std::string("Error flushing queues: ") + error_msg);

        // Detect X_LINK_ERROR and set reconnection flag
        if (Impl::isXLinkError(error_msg)) {
            pImpl_->logXLinkErrorContext(error_msg, "flushAllQueues");
            pImpl_->needs_reconnect_ = true;
            pImpl_->xlink_error_count_++;
        }
    }

    return flushed;
}

SynchronizedDetectionResult DepthAIManager::getSynchronizedDetection(std::chrono::milliseconds timeout) {
    SynchronizedDetectionResult result;
    result.valid = false;
    result.is_synchronized = false;

    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_) {
        result.sync_status = "Not initialized";
        return result;
    }

    try {
        auto start_time = std::chrono::steady_clock::now();
        auto deadline = start_time + timeout;

        // Step 1: Flush ALL queues to ensure fresh data
        int det_flushed = 0, rgb_flushed = 0;
        if (pImpl_->detection_queue_) {
            while (auto det = pImpl_->detection_queue_->tryGet<dai::SpatialImgDetections>()) {
                det_flushed++;
                if (det_flushed > 100) break;
            }
        }
        if (pImpl_->rgb_queue_) {
            while (auto rgb = pImpl_->rgb_queue_->tryGet<dai::ImgFrame>()) {
                rgb_flushed++;
                if (rgb_flushed > 100) break;
            }
        }

        pImpl_->log(LogLevel::DEBUG, "getSynchronizedDetection: Flushed " +
            std::to_string(det_flushed) + " det, " + std::to_string(rgb_flushed) + " rgb frames");

        // Step 2: Get fresh detection with sequence number
        std::shared_ptr<dai::SpatialImgDetections> inDet;
        while (!inDet && std::chrono::steady_clock::now() < deadline) {
            inDet = pImpl_->detection_queue_->tryGet<dai::SpatialImgDetections>();
            if (!inDet) {
                // BLOCKING_SLEEP_OK: sync detection poll 2ms, executor-thread (detection_group_) — reviewed 2026-03-14
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
            }
        }

        if (!inDet) {
            result.sync_status = "Detection timeout";
            pImpl_->log(LogLevel::WARN, "getSynchronizedDetection: Detection timeout");
            return result;
        }

        int64_t target_seq = inDet->getSequenceNum();
        result.detection_seq_num = target_seq;
        pImpl_->last_detection_seq_num_ = target_seq;

        pImpl_->log(LogLevel::DEBUG, "getSynchronizedDetection: Got detection seq=" + std::to_string(target_seq));

        // Step 3: Convert detections
        pImpl_->last_zero_spatial_.clear();  // Reset per-frame rejected list
        for (const auto& det : inDet->detections) {
            auto converted = pImpl_->convertDetection(det);
            if (converted.has_value()) {
                converted->sequence_num = target_seq;
                result.detections.push_back(std::move(*converted));
            }
        }

        // Step 4: Find RGB frame with MATCHING sequence number
        std::shared_ptr<dai::ImgFrame> matchedRgb;
        int search_count = 0;
        int frames_checked = 0;

        while (std::chrono::steady_clock::now() < deadline && search_count < 20) {
            auto rgb = pImpl_->rgb_queue_->tryGet<dai::ImgFrame>();
            if (!rgb) {
                // BLOCKING_SLEEP_OK: sync RGB search 2ms, executor-thread (detection_group_) — reviewed 2026-03-14
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
                search_count++;
                continue;
            }

            frames_checked++;
            int64_t rgb_seq = rgb->getSequenceNum();

            pImpl_->log(LogLevel::DEBUG, "getSynchronizedDetection: Checking RGB seq=" +
                std::to_string(rgb_seq) + " (target=" + std::to_string(target_seq) + ")");

            if (rgb_seq == target_seq) {
                // Perfect match!
                matchedRgb = rgb;
                result.rgb_seq_num = rgb_seq;
                result.is_synchronized = true;
                result.sync_status = "Matched seq=" + std::to_string(target_seq);
                pImpl_->log(LogLevel::INFO, "getSynchronizedDetection: SYNC SUCCESS seq=" + std::to_string(target_seq));
                break;
            } else if (rgb_seq > target_seq) {
                // Passed the target - detection's RGB was dropped
                result.rgb_seq_num = rgb_seq;
                result.is_synchronized = false;
                result.sync_status = "RGB seq " + std::to_string(rgb_seq) + " > detection seq " +
                    std::to_string(target_seq) + " (detection frame dropped)";
                pImpl_->log(LogLevel::WARN, "getSynchronizedDetection: SYNC MISMATCH - " + result.sync_status);
                pImpl_->sync_mismatches_++;
                // Use this frame anyway (closest available)
                matchedRgb = rgb;
                break;
            }
            // rgb_seq < target_seq: keep searching (older frame, discard)
        }

        // Step 5: Convert RGB frame if found
        if (matchedRgb) {
            auto width = matchedRgb->getWidth();
            auto height = matchedRgb->getHeight();
            auto data = matchedRgb->getData();
            auto type = matchedRgb->getType();

            result.rgb_frame = std::make_shared<cv::Mat>();

            if (type == dai::ImgFrame::Type::BGR888p) {
                int channelSize = width * height;
                cv::Mat channels[3];
                channels[0] = cv::Mat(height, width, CV_8UC1, (void*)(data.data()));
                channels[1] = cv::Mat(height, width, CV_8UC1, (void*)(data.data() + channelSize));
                channels[2] = cv::Mat(height, width, CV_8UC1, (void*)(data.data() + 2 * channelSize));
                cv::merge(channels, 3, *result.rgb_frame);
                *result.rgb_frame = result.rgb_frame->clone();
            } else if (type == dai::ImgFrame::Type::BGR888i || type == dai::ImgFrame::Type::RGB888i) {
                *result.rgb_frame = cv::Mat(height, width, CV_8UC3, (void*)data.data()).clone();
                if (type == dai::ImgFrame::Type::RGB888i) {
                    cv::cvtColor(*result.rgb_frame, *result.rgb_frame, cv::COLOR_RGB2BGR);
                }
            }

            result.has_rgb_frame = true;
            pImpl_->last_rgb_seq_num_ = result.rgb_seq_num;

            // Task 7.2: Compute VPU inference duration from device timestamps
            try {
                auto det_ts = inDet->getTimestampDevice();
                auto frame_ts = matchedRgb->getTimestampDevice();
                double vpu_ms = std::chrono::duration<double, std::milli>(det_ts - frame_ts).count();
                if (vpu_ms >= 0.0 && vpu_ms < 1000.0) {  // Sanity check: 0-1000ms
                    pImpl_->vpu_inference_times_ms_.push_back(vpu_ms);
                    if (pImpl_->vpu_inference_times_ms_.size() > Impl::MAX_VPU_SAMPLES) {
                        pImpl_->vpu_inference_times_ms_.pop_front();
                    }
                }
            } catch (const std::exception& e) {
                pImpl_->log(LogLevel::WARN, std::string("getSynchronizedDetection/VPU timing: ") + e.what());
            } catch (...) {
                pImpl_->log(LogLevel::WARN, "getSynchronizedDetection/VPU timing: unknown non-std::exception caught");
            }

            // Task 7.3: Extract per-frame camera exposure metadata
            try {
                auto exposure_time = matchedRgb->getExposureTime();
                auto sensitivity = matchedRgb->getSensitivity();
                pImpl_->last_exposure_us_ = static_cast<double>(
                    std::chrono::duration_cast<std::chrono::microseconds>(exposure_time).count());
                pImpl_->last_sensitivity_iso_ = sensitivity;
                // Rolling averages
                pImpl_->recent_exposures_us_.push_back(pImpl_->last_exposure_us_);
                if (pImpl_->recent_exposures_us_.size() > Impl::MAX_EXPOSURE_SAMPLES) {
                    pImpl_->recent_exposures_us_.pop_front();
                }
                pImpl_->recent_sensitivities_.push_back(pImpl_->last_sensitivity_iso_);
                if (pImpl_->recent_sensitivities_.size() > Impl::MAX_EXPOSURE_SAMPLES) {
                    pImpl_->recent_sensitivities_.pop_front();
                }
            } catch (const std::exception& e) {
                pImpl_->log(LogLevel::WARN, std::string("getSynchronizedDetection/exposure metadata: ") + e.what());
            } catch (...) {
                pImpl_->log(LogLevel::WARN, "getSynchronizedDetection/exposure metadata: unknown non-std::exception caught");
            }
        } else {
            result.sync_status = "RGB frame timeout (checked " + std::to_string(frames_checked) + " frames)";
            pImpl_->log(LogLevel::WARN, "getSynchronizedDetection: " + result.sync_status);
        }

        // Update frame time
        pImpl_->last_frame_time_ = std::chrono::steady_clock::now();
        pImpl_->frames_processed_++;

        result.valid = true;
        return result;

    } catch (const std::exception& e) {
        std::string error_msg = e.what();
        result.sync_status = std::string("Exception: ") + error_msg;
        pImpl_->log(LogLevel::ERROR, "getSynchronizedDetection error: " + error_msg);

        if (Impl::isXLinkError(error_msg)) {
            pImpl_->logXLinkErrorContext(error_msg, "getSynchronizedDetection");
            pImpl_->needs_reconnect_ = true;
            pImpl_->xlink_error_count_++;
        }
        return result;
    }
}

void DepthAIManager::forceReconnection() {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    pImpl_->needs_reconnect_ = true;
    pImpl_->log(LogLevel::WARN, "Reconnection forced (likely due to consecutive timeouts)");
}

std::chrono::steady_clock::time_point DepthAIManager::getLastFrameTime() const {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    return pImpl_->last_frame_time_;
}

bool DepthAIManager::setConfidenceThreshold(float threshold) {
    if (threshold < 0.0f || threshold > 1.0f) {
        pImpl_->log(LogLevel::ERROR, "Invalid threshold: " + std::to_string(threshold));
        return false;
    }

    CameraConfig config_copy;
    std::string model_path;
    bool was_initialized = false;
    {
        std::lock_guard<std::mutex> lock(pImpl_->mutex_);
        if (std::fabs(pImpl_->config_.confidence_threshold - threshold) < 1e-5f) {
            return true;
        }
        pImpl_->config_.confidence_threshold = threshold;
        was_initialized = pImpl_->initialized_;
        config_copy = pImpl_->config_;
        model_path = pImpl_->model_path_;
    }

    if (was_initialized) {
        shutdown();
        if (!initialize(model_path, config_copy)) {
            pImpl_->log(LogLevel::ERROR, "Failed to apply new confidence threshold");
            return false;
        }
    }

    pImpl_->log(LogLevel::INFO, "Confidence threshold set to: " + std::to_string(threshold));
    return true;
}

bool DepthAIManager::setDepthRange(float min_mm, float max_mm) {
    if (min_mm >= max_mm || min_mm < 0) {
        pImpl_->log(LogLevel::ERROR, "Invalid depth range: " + std::to_string(min_mm) + " - " + std::to_string(max_mm));
        return false;
    }

    CameraConfig config_copy;
    std::string model_path;
    bool was_initialized = false;
    {
        std::lock_guard<std::mutex> lock(pImpl_->mutex_);
        if (std::fabs(pImpl_->config_.depth_min_mm - min_mm) < 1e-3f &&
            std::fabs(pImpl_->config_.depth_max_mm - max_mm) < 1e-3f) {
            return true;
        }
        pImpl_->config_.depth_min_mm = min_mm;
        pImpl_->config_.depth_max_mm = max_mm;
        was_initialized = pImpl_->initialized_;
        config_copy = pImpl_->config_;
        model_path = pImpl_->model_path_;
    }

    if (was_initialized) {
        shutdown();
        if (!initialize(model_path, config_copy)) {
            pImpl_->log(LogLevel::ERROR, "Failed to apply new depth range");
            return false;
        }
    }

    pImpl_->log(LogLevel::INFO, "Depth range set to: " + std::to_string(min_mm) + " - " + std::to_string(max_mm) + " mm");
    return true;
}

bool DepthAIManager::setFPS(int fps) {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_) {
        return false;
    }

    if (fps < 1 || fps > 60) {
        pImpl_->log(LogLevel::ERROR, "Invalid FPS: " + std::to_string(fps));
        return false;
    }

    pImpl_->config_.fps = fps;

    // WARNING: setFPS() only updates config_.fps but does NOT reinitialize the pipeline.
    // The OAK-D camera VPU continues producing frames at the original FPS.
    // Thermal FPS throttling via this method is therefore non-functional at runtime.
    // A full pipeline rebuild (shutdown + initialize) would be required for actual FPS change.
    pImpl_->log(LogLevel::WARN, "setFPS: FPS config updated to " + std::to_string(fps) +
        " but pipeline NOT reinitialized - camera VPU still runs at original FPS");
    pImpl_->log(LogLevel::INFO, "FPS set to: " + std::to_string(fps) + " (requires reinitialization to apply)");
    return true;
}

bool DepthAIManager::setDepthEnabled(bool enable) {
    CameraConfig config_copy;
    std::string model_path;
    bool was_initialized = false;
    {
        std::lock_guard<std::mutex> lock(pImpl_->mutex_);
        if (pImpl_->config_.enable_depth == enable) {
            return true;
        }
        pImpl_->config_.enable_depth = enable;
        was_initialized = pImpl_->initialized_;
        config_copy = pImpl_->config_;
        model_path = pImpl_->model_path_;
    }

    if (was_initialized) {
        shutdown();
        if (!initialize(model_path, config_copy)) {
            pImpl_->log(LogLevel::ERROR, "Failed to toggle depth processing");
            return false;
        }
    }

    pImpl_->log(LogLevel::INFO, std::string("Depth processing set to: ") + (enable ? "ENABLED" : "DISABLED"));
    return true;
}

CameraStats DepthAIManager::getStats() const {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    CameraStats stats;

    if (!pImpl_->initialized_) {
        return stats;
    }

    // Calculate uptime
    auto now = std::chrono::steady_clock::now();
    stats.uptime = std::chrono::duration_cast<std::chrono::milliseconds>(
        now - pImpl_->init_time_);

    // FPS: Report the configured camera FPS (what camera is actually running at)
    // Note: frames_processed only counts frames we READ, not frames camera produces
    // The camera runs continuously at config_.fps, we just read on-demand
    stats.fps = static_cast<double>(pImpl_->config_.fps);

    stats.frames_processed = pImpl_->frames_processed_;
    stats.detection_count = pImpl_->detection_count_;

    // Calculate average latency
    if (!pImpl_->latencies_.empty()) {
        auto sum = std::chrono::milliseconds(0);
        for (const auto& lat : pImpl_->latencies_) {
            sum += lat;
        }
        stats.avg_latency = sum / pImpl_->latencies_.size();
    }

    // Get actual device temperature from DepthAI API
    // Note: Temperature sensor available on OAK-D Lite hardware
    try {
        if (pImpl_->device_) {
            auto chipTemp = pImpl_->device_->getChipTemperature();
            stats.temperature_celsius = chipTemp.average;

            // Extended diagnostics - CPU and memory usage
            // These help correlate system load with XLink errors
            try {
                // CSS (Leon CSS) CPU - handles camera ISP and encoding
                auto cssCpu = pImpl_->device_->getLeonCssCpuUsage();
                stats.css_cpu_usage_percent = cssCpu.average * 100.0;

                // MSS (Leon MSS) CPU - handles neural network inference
                auto mssCpu = pImpl_->device_->getLeonMssCpuUsage();
                stats.mss_cpu_usage_percent = mssCpu.average * 100.0;

                // DDR memory (main system memory)
                auto ddrMem = pImpl_->device_->getDdrMemoryUsage();
                stats.ddr_memory_used_mb = static_cast<double>(ddrMem.used) / (1024.0 * 1024.0);
                stats.ddr_memory_total_mb = static_cast<double>(ddrMem.total) / (1024.0 * 1024.0);

                // CMX memory (fast on-chip memory for NN/CV)
                auto cmxMem = pImpl_->device_->getCmxMemoryUsage();
                stats.cmx_memory_used_kb = static_cast<double>(cmxMem.used) / 1024.0;
                stats.cmx_memory_total_kb = static_cast<double>(cmxMem.total) / 1024.0;

                // USB speed
                auto usbSpeed = pImpl_->device_->getUsbSpeed();
                switch (usbSpeed) {
                    case dai::UsbSpeed::SUPER_PLUS:
                        stats.usb_speed = "USB 3.1 (10Gbps)";
                        break;
                    case dai::UsbSpeed::SUPER:
                        stats.usb_speed = "USB 3.0 (5Gbps)";
                        break;
                    case dai::UsbSpeed::HIGH:
                        stats.usb_speed = "USB 2.0 (480Mbps)";
                        break;
                    case dai::UsbSpeed::FULL:
                        stats.usb_speed = "USB 1.1 (12Mbps)";
                        break;
                    case dai::UsbSpeed::LOW:
                        stats.usb_speed = "USB 1.0 (1.5Mbps)";
                        break;
                    default:
                        stats.usb_speed = "Unknown";
                        break;
                }

                // USB path (stored during initialization)
                stats.usb_path = pImpl_->usb_path_;

                // Device MxID (serial number) for identification
                stats.device_mxid = pImpl_->device_->getMxId();

                // Capture device state for XLink error diagnostics
                // This is called periodically (every 30s) so we have recent state info
                pImpl_->captureDeviceState();
            } catch (const std::exception& e) {
                pImpl_->log(LogLevel::WARN, std::string("getStats/extendedDiagnostics: ") + e.what());
                stats.css_cpu_usage_percent = 0.0;
                stats.mss_cpu_usage_percent = 0.0;
                stats.ddr_memory_used_mb = 0.0;
                stats.ddr_memory_total_mb = 0.0;
                stats.cmx_memory_used_kb = 0.0;
                stats.cmx_memory_total_kb = 0.0;
                stats.usb_speed = "N/A";
                stats.usb_path = "N/A";
            } catch (...) {
                pImpl_->log(LogLevel::WARN, "getStats/extendedDiagnostics: unknown non-std::exception caught");
                stats.css_cpu_usage_percent = 0.0;
                stats.mss_cpu_usage_percent = 0.0;
                stats.ddr_memory_used_mb = 0.0;
                stats.ddr_memory_total_mb = 0.0;
                stats.cmx_memory_used_kb = 0.0;
                stats.cmx_memory_total_kb = 0.0;
                stats.usb_speed = "N/A";
                stats.usb_path = "N/A";
            }

            // Reliability metrics (always available, not dependent on device API)
            stats.reconnect_count = pImpl_->reconnect_count_;
            stats.xlink_error_count = pImpl_->xlink_error_count_;
            stats.detection_timeout_count = pImpl_->detection_timeout_count_;
            stats.rgb_timeout_count = pImpl_->rgb_timeout_count_;
            stats.needs_reconnect = pImpl_->needs_reconnect_;

            // Downtime tracking
            stats.total_downtime_ms = pImpl_->total_downtime_ms_;
            stats.last_reconnect_duration_ms = pImpl_->last_reconnect_duration_ms_;

            // Task 7.2: VPU inference timing percentiles
            if (!pImpl_->vpu_inference_times_ms_.empty()) {
                auto sorted_vpu = std::vector<double>(
                    pImpl_->vpu_inference_times_ms_.begin(),
                    pImpl_->vpu_inference_times_ms_.end());
                std::sort(sorted_vpu.begin(), sorted_vpu.end());
                size_t n = sorted_vpu.size();
                stats.vpu_inference_p50_ms = sorted_vpu[n * 50 / 100];
                stats.vpu_inference_p95_ms = sorted_vpu[std::min(n - 1, n * 95 / 100)];
            }

            // Task 7.3: Exposure metadata
            stats.last_exposure_us = pImpl_->last_exposure_us_;
            stats.last_sensitivity_iso = pImpl_->last_sensitivity_iso_;
            if (!pImpl_->recent_exposures_us_.empty()) {
                double sum_exp = 0.0;
                for (double e : pImpl_->recent_exposures_us_) sum_exp += e;
                stats.avg_exposure_us = sum_exp / pImpl_->recent_exposures_us_.size();
            }
            if (!pImpl_->recent_sensitivities_.empty()) {
                double sum_iso = 0.0;
                for (int s : pImpl_->recent_sensitivities_) sum_iso += s;
                stats.avg_sensitivity_iso = sum_iso / pImpl_->recent_sensitivities_.size();
            }

            // Task 7.4: Frame gap stats
            stats.camera_frames_processed = pImpl_->seq_frames_processed_;
            stats.camera_frames_dropped = pImpl_->seq_frames_dropped_;
            if (pImpl_->seq_frames_processed_ > 0) {
                stats.frame_drop_rate_pct = 100.0 * pImpl_->seq_frames_dropped_ /
                    (pImpl_->seq_frames_processed_ + pImpl_->seq_frames_dropped_);
            }

            // Task 7.8: Queue depth snapshots
            // Note: DepthAI DataOutputQueue does not expose current fill level
            // without draining. We report -1 (unavailable) for now.
            stats.queue_detection_size = -1;
            stats.queue_rgb_size = -1;
            stats.queue_depth_size = -1;

            // Task 7.5: Zero spatial rejection count
            stats.zero_spatial_rejections = pImpl_->zero_spatial_rejections_;
        } else {
            stats.temperature_celsius = 0.0;  // Device not available
        }
    } catch (const std::exception& e) {
        // Temperature reading failed (device may not support it or not ready)
        stats.temperature_celsius = 0.0;
        RCLCPP_DEBUG(rclcpp::get_logger("depthai_manager"),
            "Temperature read failed (non-critical): %s", e.what());
    }

    return stats;
}

std::vector<ZeroSpatialInfo> DepthAIManager::getLastZeroSpatialRejections() const {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    return pImpl_->last_zero_spatial_;
}

std::string DepthAIManager::getDeviceInfo() const {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_ || !pImpl_->device_) {
        return "Device not initialized";
    }

    try {
        std::ostringstream oss;
        oss << "Device MxID: " << pImpl_->device_->getMxId();
        oss << ", USB Speed: ";

        auto usbSpeed = pImpl_->device_->getUsbSpeed();
        switch (usbSpeed) {
            case dai::UsbSpeed::SUPER:
                oss << "USB 3.0 (5Gbps)";
                break;
            case dai::UsbSpeed::HIGH:
                oss << "USB 2.0 (480Mbps)";
                break;
            default:
                oss << "Unknown";
                break;
        }

        return oss.str();

    } catch (const std::exception& e) {
        return std::string("Error getting device info: ") + e.what();
    }
}

std::vector<std::string> DepthAIManager::getAvailableDevices() {
    std::vector<std::string> devices;

    try {
        auto deviceInfos = dai::Device::getAllAvailableDevices();

        for (const auto& info : deviceInfos) {
            devices.push_back(info.getMxId());
        }

        // Note: static method, no pImpl_ available for logging
        RCLCPP_INFO(rclcpp::get_logger("depthai_manager"), "Found %zu device(s)", devices.size());

    } catch (const std::exception& e) {
        RCLCPP_ERROR(rclcpp::get_logger("depthai_manager"), "Error enumerating devices: %s", e.what());
    }

    return devices;
}

std::optional<CameraCalibration> DepthAIManager::getCalibration() const {
    // TODO: Implement calibration retrieval from DepthAI EEPROM when hardware available
    // For now, use export_calibration.py script instead
    return std::nullopt;
}

std::string DepthAIManager::exportCalibrationYAML() const {
    // Calibration export handled via Python script (config/cameras/oak_d_lite/export_calibration.py)
    return "";
}

cv::Mat DepthAIManager::getRGBFrame(std::chrono::milliseconds timeout) {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_ || !pImpl_->rgb_queue_) {
        pImpl_->log(LogLevel::ERROR, "getRGBFrame: Not initialized or RGB queue unavailable");
        return cv::Mat();
    }

    try {
        // CRITICAL FIX: Use non-blocking tryGet with timeout instead of blocking get()
        // The blocking get() can hang indefinitely if camera pipeline stalls
        auto start_time = std::chrono::steady_clock::now();
        auto deadline = start_time + timeout;
        std::shared_ptr<dai::ImgFrame> imgFrame;

        while (!imgFrame && std::chrono::steady_clock::now() < deadline) {
            imgFrame = pImpl_->rgb_queue_->tryGet<dai::ImgFrame>();
            if (!imgFrame) {
                // Sleep briefly to avoid busy-waiting (2ms polling)
                // BLOCKING_SLEEP_OK: RGB tryGet retry 2ms, executor-thread (detection_group_) — reviewed 2026-03-14
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
            }
        }

        if (!imgFrame) {
            pImpl_->log(LogLevel::WARN, "getRGBFrame: No frame received");
            return cv::Mat();
        }

        // Manual conversion from DepthAI ImgFrame to cv::Mat
        // DepthAI library on Pi wasn't built with OpenCV support
        auto data = imgFrame->getData();
        int width = imgFrame->getWidth();
        int height = imgFrame->getHeight();
        auto type = imgFrame->getType();

        cv::Mat frame;

        // Handle different image types
        if (type == dai::ImgFrame::Type::BGR888p) {
            // Planar BGR: convert to interleaved
            int channelSize = width * height;
            cv::Mat channels[3];
            channels[0] = cv::Mat(height, width, CV_8UC1, (void*)(data.data()));
            channels[1] = cv::Mat(height, width, CV_8UC1, (void*)(data.data() + channelSize));
            channels[2] = cv::Mat(height, width, CV_8UC1, (void*)(data.data() + 2 * channelSize));
            cv::merge(channels, 3, frame);
        } else if (type == dai::ImgFrame::Type::BGR888i || type == dai::ImgFrame::Type::RGB888i) {
            // Interleaved BGR or RGB
            frame = cv::Mat(height, width, CV_8UC3, (void*)data.data()).clone();
            if (type == dai::ImgFrame::Type::RGB888i) {
                cv::cvtColor(frame, frame, cv::COLOR_RGB2BGR);
            }
        } else {
            pImpl_->log(LogLevel::ERROR, "getRGBFrame: Unsupported image type");
            return cv::Mat();
        }

        if (frame.empty()) {
            pImpl_->log(LogLevel::ERROR, "getRGBFrame: Empty frame after conversion");
            return cv::Mat();
        }

        return frame.clone();  // Return a copy to ensure thread safety

    } catch (const std::exception& e) {
        std::string error_msg = e.what();
        pImpl_->log(LogLevel::ERROR, std::string("getRGBFrame error: ") + error_msg);

        // Detect X_LINK_ERROR and set reconnection flag
        if (Impl::isXLinkError(error_msg)) {
            pImpl_->logXLinkErrorContext(error_msg, "getRGBFrame");
            pImpl_->needs_reconnect_ = true;
            pImpl_->xlink_error_count_++;
        }
        return cv::Mat();
    }
}

bool DepthAIManager::pauseCamera() {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_) {
        pImpl_->log(LogLevel::ERROR, "pauseCamera: Not initialized");
        return false;
    }

    if (pImpl_->camera_paused_) {
        // Already paused, return success
        return true;
    }

    // SOFT PAUSE: Send CameraControl to input queue and set flag.
    // The OAK-D camera VPU may continue producing frames at reduced rate,
    // but callers use isCameraPaused() as a gate to skip frame processing.
    // camera_paused_ is only set to true if the control command is successfully
    // sent to at least one input queue.
    try {
        auto ctrl = std::make_shared<dai::CameraControl>();
        ctrl->setStopStreaming();

        bool sent = false;
        if (pImpl_->color_control_queue_) {
            pImpl_->color_control_queue_->send(ctrl);
            sent = true;
        }
        if (pImpl_->mono_left_control_queue_) {
            pImpl_->mono_left_control_queue_->send(ctrl);
        }
        if (pImpl_->mono_right_control_queue_) {
            pImpl_->mono_right_control_queue_->send(ctrl);
        }

        if (!sent) {
            pImpl_->log(LogLevel::ERROR, "pauseCamera: No control queues available");
            return false;
        }
    } catch (const std::exception& e) {
        pImpl_->log(LogLevel::ERROR, std::string("pauseCamera: Failed to send control command: ") + e.what());
        return false;
    } catch (...) {
        pImpl_->log(LogLevel::ERROR, "pauseCamera: Unknown exception sending control command");
        return false;
    }

    pImpl_->camera_paused_ = true;
    pImpl_->log(LogLevel::INFO, "Camera paused (control command sent to input queues)");
    return true;
}

bool DepthAIManager::resumeCamera() {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);

    if (!pImpl_->initialized_) {
        pImpl_->log(LogLevel::ERROR, "resumeCamera: Not initialized");
        return false;
    }

    if (!pImpl_->camera_paused_) {
        // Already streaming, return success
        return true;
    }

    // Send start streaming command to resume cameras
    try {
        auto ctrl = std::make_shared<dai::CameraControl>();
        ctrl->setStartStreaming();

        if (pImpl_->color_control_queue_) {
            pImpl_->color_control_queue_->send(ctrl);
        }
        if (pImpl_->mono_left_control_queue_) {
            pImpl_->mono_left_control_queue_->send(ctrl);
        }
        if (pImpl_->mono_right_control_queue_) {
            pImpl_->mono_right_control_queue_->send(ctrl);
        }
    } catch (const std::exception& e) {
        pImpl_->log(LogLevel::WARN, std::string("resumeCamera: Exception sending start command: ") + e.what());
        // Continue with flush and flag clear — best effort resume
    } catch (...) {
        pImpl_->log(LogLevel::WARN, "resumeCamera: Unknown exception sending start command");
    }

    // Flush stale frames accumulated during pause
    int flushed = 0;
    try {
        // Flush detection queue
        if (pImpl_->detection_queue_) {
            while (pImpl_->detection_queue_->has() && flushed < 30) {
                pImpl_->detection_queue_->tryGet<dai::SpatialImgDetections>();
                flushed++;
            }
        }
        // Flush RGB queue
        if (pImpl_->rgb_queue_) {
            while (pImpl_->rgb_queue_->has() && flushed < 30) {
                pImpl_->rgb_queue_->tryGet<dai::ImgFrame>();
                flushed++;
            }
        }
    } catch (const std::exception& e) {
        pImpl_->log(LogLevel::WARN, std::string("resumeCamera/flush queues: ") + e.what());
    } catch (...) {
        pImpl_->log(LogLevel::WARN, "resumeCamera/flush queues: unknown non-std::exception caught");
    }

    pImpl_->camera_paused_ = false;
    if (flushed > 0) {
        pImpl_->log(LogLevel::INFO, "Camera resumed (flushed " + std::to_string(flushed) + " stale frames)");
    } else {
        pImpl_->log(LogLevel::INFO, "Camera resumed");
    }
    return true;
}

bool DepthAIManager::isCameraPaused() const {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    return pImpl_->camera_paused_;
}

void DepthAIManager::setLogger(LoggerCallback logger) {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    pImpl_->logger_ = std::move(logger);
}

// ============================================================================
// Private implementation methods
// ============================================================================

bool DepthAIManager::Impl::validateConfig(const CameraConfig& config, std::string* error_msg) {
    std::ostringstream errors;
    bool valid = true;

    // Validate image dimensions
    if (config.width <= 0 || config.width > 4096) {
        errors << "Invalid width: " << config.width << " (must be 1-4096). ";
        valid = false;
    }
    if (config.height <= 0 || config.height > 4096) {
        errors << "Invalid height: " << config.height << " (must be 1-4096). ";
        valid = false;
    }

    // Check for reasonable aspect ratio
    if (config.width > 0 && config.height > 0) {
        double aspect_ratio = static_cast<double>(config.width) / config.height;
        if (aspect_ratio < 0.25 || aspect_ratio > 4.0) {
            errors << "Unusual aspect ratio: " << aspect_ratio << " (width:height). ";
            // Warning only, not an error
        }
    }

    // Validate FPS
    if (config.fps < 1 || config.fps > 60) {
        errors << "Invalid FPS: " << config.fps << " (must be 1-60). ";
        valid = false;
    }

    // Validate confidence threshold
    if (config.confidence_threshold < 0.0f || config.confidence_threshold > 1.0f) {
        errors << "Invalid confidence threshold: " << config.confidence_threshold
               << " (must be 0.0-1.0). ";
        valid = false;
    }

    // Validate depth range
    if (config.depth_min_mm < 0.0f) {
        errors << "Invalid min depth: " << config.depth_min_mm << " (must be >= 0). ";
        valid = false;
    }
    if (config.depth_max_mm <= config.depth_min_mm) {
        errors << "Invalid depth range: [" << config.depth_min_mm << ", "
               << config.depth_max_mm << "] (max must be > min). ";
        valid = false;
    }
    if (config.depth_max_mm > 50000.0f) {  // 50 meters seems reasonable max
        errors << "Unusually large max depth: " << config.depth_max_mm
               << " mm (> 50m, may impact performance). ";
        // Warning only
    }

    // Validate color order
    if (config.color_order != "RGB" && config.color_order != "BGR") {
        errors << "Invalid color order: '" << config.color_order
               << "' (must be 'RGB' or 'BGR'). ";
        valid = false;
    }

    // Check for common configuration issues
    if (config.width % 16 != 0 || config.height % 16 != 0) {
        errors << "Warning: Image dimensions not multiples of 16 ("
               << config.width << "x" << config.height
               << "), may impact performance. ";
        // Warning only, not an error
    }

    if (error_msg) {
        *error_msg = errors.str();
    }

    return valid;
}

bool DepthAIManager::Impl::buildPipeline() {
    log(LogLevel::INFO, "Building pipeline...");

    try {
        // 1. Create pipeline
        pipeline_ = std::make_shared<dai::Pipeline>();

        // 2. Create nodes
        auto colorCam = pipeline_->create<dai::node::ColorCamera>();
        auto monoLeft = pipeline_->create<dai::node::MonoCamera>();
        auto monoRight = pipeline_->create<dai::node::MonoCamera>();
        auto stereo = pipeline_->create<dai::node::StereoDepth>();
        auto spatialNN = pipeline_->create<dai::node::YoloSpatialDetectionNetwork>();
        auto manip = pipeline_->create<dai::node::ImageManip>();  // Add ImageManip for proper resizing
        auto xoutRgb = pipeline_->create<dai::node::XLinkOut>();
        auto xoutNN = pipeline_->create<dai::node::XLinkOut>();
        auto xoutDepth = pipeline_->create<dai::node::XLinkOut>();

        // Create XLinkIn nodes for runtime camera control (pause/resume)
        auto colorCamControl = pipeline_->create<dai::node::XLinkIn>();
        colorCamControl->setStreamName("colorCamControl");
        colorCamControl->out.link(colorCam->inputControl);

        // Set stream names
        xoutRgb->setStreamName("rgb");
        xoutNN->setStreamName("detections");
        xoutDepth->setStreamName("depth");

        log(LogLevel::DEBUG, "Nodes created (including camera control)");

        // 3. Configure camera - use high resolution like Python wrapper
        colorCam->setPreviewSize(1920, 1080);  // Match Python wrapper: high res preview
        colorCam->setResolution(dai::ColorCameraProperties::SensorResolution::THE_1080_P);
        colorCam->setInterleaved(false);

        // Set color order
        if (config_.color_order == "BGR") {
            colorCam->setColorOrder(dai::ColorCameraProperties::ColorOrder::BGR);
        } else if (config_.color_order == "RGB") {
            colorCam->setColorOrder(dai::ColorCameraProperties::ColorOrder::RGB);
        }

        colorCam->setFps(config_.fps);

        // Exposure control
        if (config_.exposure_mode == "manual") {
            // Manual exposure: fixed values for consistent lighting
            colorCam->initialControl.setManualExposure(config_.exposure_time_us, config_.exposure_iso);
            log(LogLevel::INFO, "Exposure: MANUAL (" + std::to_string(config_.exposure_time_us) +
                " µs, ISO " + std::to_string(config_.exposure_iso) + ")");
        } else {
            // Auto exposure: camera adjusts to lighting conditions
            colorCam->initialControl.setAutoExposureEnable();
            log(LogLevel::INFO, "Exposure: AUTO");
        }

        // 3b. Configure ImageManip to resize to NN input size
        // IMPORTANT: Use setResize and setFrameType to ensure planar (CHW) output for YOLO
        manip->initialConfig.setResize(config_.width, config_.height);
        manip->initialConfig.setKeepAspectRatio(config_.keep_aspect_ratio);
        manip->initialConfig.setFrameType(dai::ImgFrame::Type::BGR888p);  // Planar format required by YOLO
        manip->inputConfig.setWaitForMessage(false);  // Use initial config immediately (no runtime config required)

        // CRITICAL FIX: Set max output frame size to handle 1920x1080 images
        // Default is 1MB, but 1920x1080x3 = 6.2MB, so we need at least 7MB
        manip->setMaxOutputFrameSize(7 * 1024 * 1024);  // 7MB buffer

        log(LogLevel::INFO, "ColorCamera configured: 1920x1080 @ " + std::to_string(config_.fps) + " FPS");
        log(LogLevel::DEBUG, "ImageManip resize: " + std::to_string(config_.width) + "x" + std::to_string(config_.height));

        // 4. Configure mono cameras and stereo depth (if enabled)
        if (config_.enable_depth) {
            // Configure left and right mono cameras
            // Mono resolution: configurable via config_.mono_resolution
            auto mono_res = dai::MonoCameraProperties::SensorResolution::THE_400_P;
            if (config_.mono_resolution == "480p") {
                mono_res = dai::MonoCameraProperties::SensorResolution::THE_480_P;
            } else if (config_.mono_resolution == "720p") {
                mono_res = dai::MonoCameraProperties::SensorResolution::THE_720_P;
            } else if (config_.mono_resolution == "800p") {
                mono_res = dai::MonoCameraProperties::SensorResolution::THE_800_P;
            }
            monoLeft->setResolution(mono_res);
            monoLeft->setBoardSocket(dai::CameraBoardSocket::CAM_B);  // Updated from deprecated LEFT
            monoLeft->setFps(config_.fps);

            monoRight->setResolution(mono_res);
            monoRight->setBoardSocket(dai::CameraBoardSocket::CAM_C);  // Updated from deprecated RIGHT
            monoRight->setFps(config_.fps);

            // Configure stereo depth - Using DEFAULT preset (replaces deprecated HIGH_ACCURACY)
            // DEFAULT provides same balanced performance as HIGH_ACCURACY with better thermal characteristics
            stereo->setDefaultProfilePreset(dai::node::StereoDepth::PresetMode::DEFAULT);
            stereo->setDepthAlign(dai::CameraBoardSocket::CAM_A);  // Updated from deprecated RGB
            stereo->setOutputSize(config_.width, config_.height);

            // Stereo advanced settings — all configurable via ROS2 params
            stereo->setLeftRightCheck(config_.lr_check);
            stereo->setSubpixel(config_.subpixel);
            stereo->setExtendedDisparity(config_.extended_disparity);

            // Confidence and median filter
            stereo->initialConfig.setConfidenceThreshold(config_.stereo_confidence_threshold);

            // Median filter: configurable via config_.median_filter
            auto median_f = dai::MedianFilter::KERNEL_7x7;
            if (config_.median_filter == "off") {
                median_f = dai::MedianFilter::MEDIAN_OFF;
            } else if (config_.median_filter == "3x3") {
                median_f = dai::MedianFilter::KERNEL_3x3;
            } else if (config_.median_filter == "5x5") {
                median_f = dai::MedianFilter::KERNEL_5x5;
            }
            stereo->initialConfig.setMedianFilter(median_f);

            // Create XLinkIn nodes for mono camera control (pause/resume)
            auto monoLeftControl = pipeline_->create<dai::node::XLinkIn>();
            monoLeftControl->setStreamName("monoLeftControl");
            monoLeftControl->out.link(monoLeft->inputControl);

            auto monoRightControl = pipeline_->create<dai::node::XLinkIn>();
            monoRightControl->setStreamName("monoRightControl");
            monoRightControl->out.link(monoRight->inputControl);

            // Link mono cameras to stereo depth
            monoLeft->out.link(stereo->left);
            monoRight->out.link(stereo->right);

            log(LogLevel::DEBUG, "MonoCameras, StereoDepth, and camera controls configured");
        }

        // 5. Configure spatial detection network
        spatialNN->setBlobPath(model_path_);
        spatialNN->setConfidenceThreshold(config_.confidence_threshold);

        // CRITICAL: Use pooling mode to process frames continuously at camera FPS
        // setBlocking(false) means "skip frames if processing is slow" (drops frames but keeps pipeline running)
        // This ensures that camera runs at full 30 FPS even if we don't read every frame
        spatialNN->input.setBlocking(false);  // Non-blocking = drop frames if slow (good for real-time)
        spatialNN->input.setQueueSize(2);     // Small queue to minimize latency

        spatialNN->setBoundingBoxScaleFactor(config_.bbox_scale_factor);

        // Spatial calculation algorithm: configurable via config_.spatial_calc_algorithm
        // AVERAGE (default), MEDIAN (more robust to depth holes), MIN, MAX
        if (config_.spatial_calc_algorithm == "median") {
            spatialNN->setSpatialCalculationAlgorithm(
                dai::SpatialLocationCalculatorAlgorithm::MEDIAN);
        } else if (config_.spatial_calc_algorithm == "min") {
            spatialNN->setSpatialCalculationAlgorithm(
                dai::SpatialLocationCalculatorAlgorithm::MIN);
        } else if (config_.spatial_calc_algorithm == "max") {
            spatialNN->setSpatialCalculationAlgorithm(
                dai::SpatialLocationCalculatorAlgorithm::MAX);
        }
        // "average" is the DepthAI default — no explicit call needed

        // YOLO-specific parameters (match Python wrapper configuration)
        spatialNN->setNumClasses(config_.num_classes);  // Dynamic: 1 for YOLOv8, 2 for YOLOv11
        spatialNN->setCoordinateSize(4);
        spatialNN->setIouThreshold(0.5);

        // YOLOv11 is anchor-free - don't set anchors for YOLOv11
        if (config_.num_classes == 1) {
            // YOLOv8 anchors (only for YOLOv8)
            spatialNN->setAnchors({10,13, 16,30, 33,23, 30,61, 62,45, 59,119, 116,90, 156,198, 373,326});
            spatialNN->setAnchorMasks({{"side52", {0,1,2}}, {"side26", {3,4,5}}, {"side13", {6,7,8}}});
        } else {
            // YOLOv11 - anchor-free, don't set anchors
            log(LogLevel::INFO, "YOLOv11 detected: using anchor-free configuration");
        }

        if (config_.enable_depth) {
            spatialNN->setDepthLowerThreshold(config_.depth_min_mm);
            spatialNN->setDepthUpperThreshold(config_.depth_max_mm);
        }

        log(LogLevel::INFO, "SpatialNN configured: model=" + model_path_ + ", confidence=" + std::to_string(config_.confidence_threshold));
        log(LogLevel::INFO, "Configuration summary: input_size=" + std::to_string(config_.width) + "x" + std::to_string(config_.height) +
                   ", num_classes=" + std::to_string(config_.num_classes) +
                   ", blocking=false, queue_size=2");

        // 6. Link nodes - use ImageManip for proper preprocessing
        colorCam->preview.link(manip->inputImage);
        manip->out.link(spatialNN->input);
        spatialNN->passthrough.link(xoutRgb->input);
        spatialNN->out.link(xoutNN->input);

        if (config_.enable_depth) {
            stereo->depth.link(spatialNN->inputDepth);
            spatialNN->passthroughDepth.link(xoutDepth->input);
        }

        log(LogLevel::DEBUG, "Nodes linked");
        log(LogLevel::INFO, "Pipeline build SUCCESS");

        return true;

    } catch (const std::exception& e) {
        log(LogLevel::ERROR, std::string("Pipeline build failed: ") + e.what());
        return false;
    }
}

std::optional<CottonDetection> DepthAIManager::Impl::convertDetection(const dai::SpatialImgDetection& det) {
    // Reject detections where stereo depth failed (all spatial coordinates zero).
    // DepthAI explicitly sets spatialCoordinates to {0,0,0} on stereo failure —
    // these are integer zeros cast to float, not computed values, so exact
    // comparison is correct (no epsilon needed).
    if (det.spatialCoordinates.x == 0.0f && det.spatialCoordinates.y == 0.0f && det.spatialCoordinates.z == 0.0f) {
        char buf[256];
        std::snprintf(buf, sizeof(buf),
            "Dropping detection: zero spatial coordinates (stereo depth failed) "
            "label=%d confidence=%.4f xmin=%.4f ymin=%.4f xmax=%.4f ymax=%.4f",
            det.label, det.confidence, det.xmin, det.ymin, det.xmax, det.ymax);
        log(LogLevel::WARN, buf);

        // Collect rejected detection data for diagnostic image annotation
        ZeroSpatialInfo info;
        info.x_min = det.xmin;
        info.y_min = det.ymin;
        info.x_max = det.xmax;
        info.y_max = det.ymax;
        info.confidence = det.confidence;
        info.label = det.label;
        last_zero_spatial_.push_back(info);

        ++zero_spatial_rejections_;  // Task 7.5: Track rejections for telemetry
        return std::nullopt;
    }

    CottonDetection result;

    // Convert detection label and confidence
    result.label = det.label;
    result.confidence = det.confidence;

    // Convert normalized bounding box coordinates [0, 1]
    result.x_min = det.xmin;
    result.y_min = det.ymin;
    result.x_max = det.xmax;
    result.y_max = det.ymax;

    // Convert spatial coordinates from DepthAI format to millimeters
    // DepthAI provides coordinates in millimeters relative to camera center:
    // - X: positive right, negative left
    // - Y: positive up, negative down
    // - Z: positive forward (distance from camera)
    result.spatial_x = det.spatialCoordinates.x;  // mm
    result.spatial_y = det.spatialCoordinates.y;  // mm
    result.spatial_z = det.spatialCoordinates.z;  // mm

    // Record detection timestamp
    result.timestamp = std::chrono::steady_clock::now();

    // Store image dimensions for potential denormalization
    result.image_width = config_.width;
    result.image_height = config_.height;

    return result;
}

void DepthAIManager::Impl::updateStats() {
    // Statistics are updated inline during getDetections() for performance
    // This method can be used for periodic background statistics updates if needed

    // Update timestamp for potential rate calculations
    last_stats_update_ = std::chrono::steady_clock::now();

    // Additional statistics tracking can be added here:
    // - Average detections per frame: detection_count_ / frames_processed_
    // - Detection success rate: frames_with_detections_ / frames_processed_
    // - Average detections per positive frame: total_detections_in_frame_ / frames_with_detections_
    // - FPS calculation based on time delta
    // - Memory usage tracking
    // - Queue depth monitoring
}

// ============================================================================
// Reconnection methods (for X_LINK_ERROR recovery)
// ============================================================================

bool DepthAIManager::needsReconnect() const {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    return pImpl_->needs_reconnect_;
}

bool DepthAIManager::reconnect() {
    // Track reconnection start time for downtime measurement
    auto reconnect_start = std::chrono::steady_clock::now();

    // Get current config before shutdown (need to copy outside lock)
    CameraConfig config_copy;
    std::string model_path_copy;
    {
        std::lock_guard<std::mutex> lock(pImpl_->mutex_);
        if (!pImpl_->needs_reconnect_) {
            pImpl_->log(LogLevel::INFO, "reconnect() called but no reconnection needed");
            return true;  // Already healthy
        }
        config_copy = pImpl_->config_;
        model_path_copy = pImpl_->model_path_;
    }

    pImpl_->log(LogLevel::WARN, "🔄 Attempting to reconnect DepthAI device...");

    // Step 1: Shutdown existing connection
    pImpl_->log(LogLevel::INFO, "Step 1/3: Shutting down existing connection...");
    shutdown();

    // Step 2: Wait for USB re-enumeration
    // USB devices need time to properly disconnect and re-enumerate
    pImpl_->log(LogLevel::INFO, "Step 2/3: Waiting for USB re-enumeration (2 seconds)...");
    // BLOCKING_SLEEP_OK: USB re-enumeration wait 2s, executor-thread (caller's callback group) — reviewed 2026-03-14
    std::this_thread::sleep_for(std::chrono::seconds(2));

    // Step 3: Reinitialize
    pImpl_->log(LogLevel::INFO, "Step 3/3: Reinitializing device...");
    bool success = initialize(model_path_copy, config_copy);

    // Calculate reconnection duration
    auto reconnect_end = std::chrono::steady_clock::now();
    auto reconnect_duration = std::chrono::duration_cast<std::chrono::milliseconds>(
        reconnect_end - reconnect_start);

    if (success) {
        // Clear the reconnect flag on success and update downtime stats
        std::lock_guard<std::mutex> lock(pImpl_->mutex_);
        pImpl_->needs_reconnect_ = false;
        pImpl_->reconnect_count_++;
        pImpl_->last_reconnect_duration_ms_ = reconnect_duration;
        pImpl_->total_downtime_ms_ += reconnect_duration;
        pImpl_->log(LogLevel::INFO, "✅ Reconnection successful! (duration: " +
                    std::to_string(reconnect_duration.count()) + "ms, total reconnects: " +
                    std::to_string(pImpl_->reconnect_count_) + ", total downtime: " +
                    std::to_string(pImpl_->total_downtime_ms_.count()) + "ms)");
    } else {
        // Still track downtime for failed attempts
        std::lock_guard<std::mutex> lock(pImpl_->mutex_);
        pImpl_->last_reconnect_duration_ms_ = reconnect_duration;
        pImpl_->total_downtime_ms_ += reconnect_duration;
        pImpl_->log(LogLevel::ERROR, "❌ Reconnection failed after " +
                    std::to_string(reconnect_duration.count()) + "ms - device may be unavailable");
    }

    return success;
}

void DepthAIManager::clearReconnectFlag() {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    pImpl_->needs_reconnect_ = false;
    pImpl_->log(LogLevel::INFO, "Reconnection flag cleared");
}

}  // namespace cotton_detection
