#pragma once

#include <chrono>
#include <memory>
#include <string>
#include <vector>

// Forward declaration for OpenCV Mat type
namespace cv {
    class Mat;
}

namespace cotton_detection {

/**
 * @brief Cotton detection result structure
 */
struct CottonDetection {
    uint32_t label;                     // Class ID
    float confidence;                   // Detection confidence [0, 1]

    // Normalized bounding box [0, 1]
    float x_min;
    float y_min;
    float x_max;
    float y_max;

    // Spatial coordinates (millimeters)
    float spatial_x;                    // Left(-) / Right(+) from camera center
    float spatial_y;                    // Down(-) / Up(+) from camera center
    float spatial_z;                    // Distance from camera

    // Timestamp
    std::chrono::steady_clock::time_point timestamp;

    // Optional: Raw image size (for denormalization)
    int image_width{0};
    int image_height{0};

    // Sequence number for synchronization verification
    int64_t sequence_num{-1};
};

/**
 * @brief Info for a detection rejected due to zero spatial coordinates.
 *
 * Lightweight struct carrying only the data needed for diagnostic logging
 * and image annotation.  Bounding box is normalized [0, 1] as received
 * from the DepthAI SpatialImgDetection struct.
 */
struct ZeroSpatialInfo {
    float x_min{0.0f};
    float y_min{0.0f};
    float x_max{0.0f};
    float y_max{0.0f};
    float confidence{0.0f};
    int label{0};
};

/**
 * @brief Synchronized detection result with RGB frame
 *
 * This struct guarantees that detection and RGB are from the SAME camera frame,
 * verified by matching sequence numbers.
 *
 * Note: rgb_frame is a shared_ptr because cv::Mat is only forward-declared in this header.
 * Check has_rgb_frame flag instead of checking the pointer directly.
 */
struct SynchronizedDetectionResult {
    std::vector<CottonDetection> detections;  // Detection results
    std::shared_ptr<cv::Mat> rgb_frame;        // Synchronized RGB frame (shared_ptr due to forward decl)
    int64_t detection_seq_num{-1};             // Detection sequence number
    int64_t rgb_seq_num{-1};                   // RGB frame sequence number
    bool is_synchronized{false};               // True if seq nums match
    bool valid{false};                         // True if detection succeeded
    bool has_rgb_frame{false};                 // True if rgb_frame contains valid data
    std::string sync_status;                   // Human-readable sync status
};

}  // namespace cotton_detection
