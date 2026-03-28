#pragma once

#include <string>

namespace cotton_detection {

/**
 * @brief Camera configuration parameters
 */
struct CameraConfig {
    int width{416};                      // Preview/detection width
    int height{416};                     // Preview/detection height
    int fps{30};                         // Frames per second
    int num_classes{1};                 // Number of classes in model (1=YOLOv8, 2=YOLOv11)
    float confidence_threshold{0.5f};    // Detection confidence threshold
    float depth_min_mm{100.0f};         // Minimum depth in millimeters
    float depth_max_mm{5000.0f};        // Maximum depth in millimeters
    std::string color_order{"BGR"};     // Color channel order
    bool enable_depth{true};            // Enable stereo depth
    std::string device_id{""};          // Specific device ID (empty = any)

    // Exposure control
    std::string exposure_mode{"auto"};  // "auto" or "manual"
    int exposure_time_us{8000};          // Manual exposure time in microseconds (1-33000)
    int exposure_iso{400};               // Manual ISO value (100-1600)

    // ImageManip behaviour
    bool keep_aspect_ratio{true};        // true = letterbox; false = stretch to fill NN input

    // Stereo depth pipeline tuning
    int stereo_confidence_threshold{200};  // Stereo depth matching confidence (0-255, lower = stricter)
    float bbox_scale_factor{0.5f};        // Fraction of bounding box sampled for depth (0.3-0.8)
    bool extended_disparity{true};        // Extended disparity for close-range depth (0.15-0.6m)

    // Stereo depth advanced tuning (previously hardcoded)
    std::string spatial_calc_algorithm{"average"};  // "average", "median", "min", "max"
    std::string mono_resolution{"400p"};            // "400p", "480p", "720p", "800p"
    bool lr_check{true};                            // Left-right consistency check
    bool subpixel{false};                           // Subpixel disparity (adds latency)
    std::string median_filter{"7x7"};               // "off", "3x3", "5x5", "7x7"
};

}  // namespace cotton_detection
