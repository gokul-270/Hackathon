#pragma once

#include <chrono>
#include <string>
#include <vector>

namespace cotton_detection {

/**
 * @brief Camera statistics and diagnostics
 */
struct CameraStats {
    double fps;                         // Actual frames per second
    double temperature_celsius;         // Device temperature (average across sensors)
    uint64_t frames_processed;          // Total frames processed
    std::chrono::milliseconds uptime;   // Time since initialization
    size_t detection_count;             // Total detections
    std::chrono::milliseconds avg_latency;  // Average detection latency

    // Reliability metrics (for debugging XLink errors)
    uint32_t reconnect_count;           // Number of XLink reconnections
    uint32_t xlink_error_count;         // Total XLink errors encountered
    uint32_t detection_timeout_count;   // Detection queue timeouts
    uint32_t rgb_timeout_count;         // RGB frame queue timeouts
    bool needs_reconnect;               // Currently needs reconnection

    // Downtime tracking (for optimization)
    std::chrono::milliseconds total_downtime_ms{0};     // Cumulative reconnection downtime
    std::chrono::milliseconds last_reconnect_duration_ms{0};  // Duration of last reconnection

    // Extended diagnostics
    double css_cpu_usage_percent;       // Leon CSS CPU usage (%)
    double mss_cpu_usage_percent;       // Leon MSS CPU usage (%)
    double ddr_memory_used_mb;          // DDR memory used (MB)
    double ddr_memory_total_mb;         // DDR memory total (MB)
    double cmx_memory_used_kb;          // CMX memory used (KB)
    double cmx_memory_total_kb;         // CMX memory total (KB)
    std::string usb_speed;              // USB connection speed
    std::string usb_path;               // USB device path (e.g., 1.1.2.1)
    std::string device_mxid;            // Device MxID (serial number for identification)

    // VPU inference timing (Task 7.2)
    double vpu_inference_p50_ms{0.0};
    double vpu_inference_p95_ms{0.0};

    // Exposure metadata (Task 7.3)
    double last_exposure_us{0.0};
    int last_sensitivity_iso{0};
    double avg_exposure_us{0.0};
    double avg_sensitivity_iso{0.0};

    // Frame gap tracking (Task 7.4)
    uint64_t camera_frames_processed{0};
    uint64_t camera_frames_dropped{0};
    double frame_drop_rate_pct{0.0};

    // Depth quality tracking (Task 7.5)
    uint64_t zero_spatial_rejections{0};  // Detections rejected for zero spatial coords

    // Queue depths (Task 7.8)
    int queue_detection_size{-1};  // -1 = unavailable
    int queue_rgb_size{-1};
    int queue_depth_size{-1};
};

/**
 * @brief Camera calibration data
 */
struct CameraCalibration {
    // Intrinsics
    std::vector<float> camera_matrix;   // 3x3 matrix (flattened)
    std::vector<float> distortion;      // Distortion coefficients

    // Image dimensions
    int width;
    int height;

    // Stereo baseline (mm)
    float baseline_mm;

    // Field of view (degrees)
    float fov_horizontal;
    float fov_vertical;
};

}  // namespace cotton_detection
