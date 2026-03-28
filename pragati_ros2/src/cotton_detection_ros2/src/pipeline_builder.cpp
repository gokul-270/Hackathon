// pipeline_builder.cpp — Stateless DepthAI pipeline factory (D4).
// Extracts validateConfig() (lines 1827-1899) and buildPipeline() (lines 1901-2070)
// from depthai_manager.cpp into a hardware-decoupled, independently testable class.

#include "cotton_detection_ros2/pipeline_builder.hpp"

#include <optional>
#include <sstream>

#include <depthai/depthai.hpp>

namespace cotton_detection {

ValidationResult PipelineBuilder::validate(const CameraConfig& config,
                                           const std::string& model_path) const {
    std::ostringstream errors;
    bool valid = true;

    // Validate model path
    if (model_path.empty()) {
        errors << "Empty model path: a .blob model file is required. ";
        valid = false;
    }

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
    if (config.depth_max_mm > 50000.0f) {
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

    return {valid, errors.str()};
}

std::optional<dai::Pipeline> PipelineBuilder::build(const CameraConfig& config,
                                                    const std::string& model_path) const {
    // Validate first
    auto validation = validate(config, model_path);
    if (!validation.valid) {
        return std::nullopt;
    }

    try {
        dai::Pipeline pipeline;

        // --- Create nodes ---
        auto colorCam = pipeline.create<dai::node::ColorCamera>();
        auto manip = pipeline.create<dai::node::ImageManip>();
        auto spatialNN = pipeline.create<dai::node::YoloSpatialDetectionNetwork>();
        auto xoutRgb = pipeline.create<dai::node::XLinkOut>();
        auto xoutNN = pipeline.create<dai::node::XLinkOut>();

        // Camera control XLinkIn (for runtime pause/resume)
        auto colorCamControl = pipeline.create<dai::node::XLinkIn>();
        colorCamControl->setStreamName("colorCamControl");
        colorCamControl->out.link(colorCam->inputControl);

        // Set stream names
        xoutRgb->setStreamName("rgb");
        xoutNN->setStreamName("detections");

        // --- Configure color camera: 1080p with config FPS ---
        colorCam->setPreviewSize(1920, 1080);
        colorCam->setResolution(dai::ColorCameraProperties::SensorResolution::THE_1080_P);
        colorCam->setInterleaved(false);

        if (config.color_order == "BGR") {
            colorCam->setColorOrder(dai::ColorCameraProperties::ColorOrder::BGR);
        } else if (config.color_order == "RGB") {
            colorCam->setColorOrder(dai::ColorCameraProperties::ColorOrder::RGB);
        }

        colorCam->setFps(config.fps);

        // Exposure control
        if (config.exposure_mode == "manual") {
            colorCam->initialControl.setManualExposure(config.exposure_time_us, config.exposure_iso);
        } else {
            colorCam->initialControl.setAutoExposureEnable();
        }

        // --- Configure ImageManip to resize to NN input size ---
        manip->initialConfig.setResize(config.width, config.height);
        manip->initialConfig.setKeepAspectRatio(config.keep_aspect_ratio);
        manip->initialConfig.setFrameType(dai::ImgFrame::Type::BGR888p);
        manip->inputConfig.setWaitForMessage(false);
        manip->setMaxOutputFrameSize(7 * 1024 * 1024);  // 7MB for 1920x1080

        // --- Stereo depth (conditional) ---
        std::shared_ptr<dai::node::StereoDepth> stereo;
        std::shared_ptr<dai::node::XLinkOut> xoutDepth;

        if (config.enable_depth) {
            auto monoLeft = pipeline.create<dai::node::MonoCamera>();
            auto monoRight = pipeline.create<dai::node::MonoCamera>();
            stereo = pipeline.create<dai::node::StereoDepth>();
            xoutDepth = pipeline.create<dai::node::XLinkOut>();
            xoutDepth->setStreamName("depth");

            // Configure mono cameras
            auto mono_res = dai::MonoCameraProperties::SensorResolution::THE_400_P;
            if (config.mono_resolution == "480p") {
                mono_res = dai::MonoCameraProperties::SensorResolution::THE_480_P;
            } else if (config.mono_resolution == "720p") {
                mono_res = dai::MonoCameraProperties::SensorResolution::THE_720_P;
            } else if (config.mono_resolution == "800p") {
                mono_res = dai::MonoCameraProperties::SensorResolution::THE_800_P;
            }
            monoLeft->setResolution(mono_res);
            monoLeft->setBoardSocket(dai::CameraBoardSocket::CAM_B);
            monoLeft->setFps(config.fps);

            monoRight->setResolution(mono_res);
            monoRight->setBoardSocket(dai::CameraBoardSocket::CAM_C);
            monoRight->setFps(config.fps);

            // Configure stereo depth
            stereo->setDefaultProfilePreset(dai::node::StereoDepth::PresetMode::DEFAULT);
            stereo->setDepthAlign(dai::CameraBoardSocket::CAM_A);
            stereo->setOutputSize(config.width, config.height);
            stereo->setLeftRightCheck(config.lr_check);
            stereo->setSubpixel(config.subpixel);
            stereo->setExtendedDisparity(config.extended_disparity);
            stereo->initialConfig.setConfidenceThreshold(config.stereo_confidence_threshold);

            // Median filter: configurable via config.median_filter
            auto median_f = dai::MedianFilter::KERNEL_7x7;
            if (config.median_filter == "off") {
                median_f = dai::MedianFilter::MEDIAN_OFF;
            } else if (config.median_filter == "3x3") {
                median_f = dai::MedianFilter::KERNEL_3x3;
            } else if (config.median_filter == "5x5") {
                median_f = dai::MedianFilter::KERNEL_5x5;
            }
            stereo->initialConfig.setMedianFilter(median_f);

            // Mono camera control XLinkIn nodes
            auto monoLeftControl = pipeline.create<dai::node::XLinkIn>();
            monoLeftControl->setStreamName("monoLeftControl");
            monoLeftControl->out.link(monoLeft->inputControl);

            auto monoRightControl = pipeline.create<dai::node::XLinkIn>();
            monoRightControl->setStreamName("monoRightControl");
            monoRightControl->out.link(monoRight->inputControl);

            // Link mono cameras to stereo
            monoLeft->out.link(stereo->left);
            monoRight->out.link(stereo->right);
        }

        // --- Configure spatial detection network ---
        spatialNN->setBlobPath(model_path);
        spatialNN->setConfidenceThreshold(config.confidence_threshold);
        spatialNN->input.setBlocking(false);
        spatialNN->input.setQueueSize(2);
        spatialNN->setBoundingBoxScaleFactor(config.bbox_scale_factor);

        // Spatial calculation algorithm: configurable via config.spatial_calc_algorithm
        if (config.spatial_calc_algorithm == "median") {
            spatialNN->setSpatialCalculationAlgorithm(
                dai::SpatialLocationCalculatorAlgorithm::MEDIAN);
        } else if (config.spatial_calc_algorithm == "min") {
            spatialNN->setSpatialCalculationAlgorithm(
                dai::SpatialLocationCalculatorAlgorithm::MIN);
        } else if (config.spatial_calc_algorithm == "max") {
            spatialNN->setSpatialCalculationAlgorithm(
                dai::SpatialLocationCalculatorAlgorithm::MAX);
        }

        // YOLO-specific parameters
        spatialNN->setNumClasses(config.num_classes);
        spatialNN->setCoordinateSize(4);
        spatialNN->setIouThreshold(0.5f);

        // YOLOv8 anchors (num_classes == 1); YOLOv11 is anchor-free
        if (config.num_classes == 1) {
            spatialNN->setAnchors({10, 13, 16, 30, 33, 23, 30, 61, 62, 45, 59, 119, 116, 90, 156, 198, 373, 326});
            spatialNN->setAnchorMasks({{"side52", {0, 1, 2}}, {"side26", {3, 4, 5}}, {"side13", {6, 7, 8}}});
        }

        // Depth thresholds (only when depth enabled)
        if (config.enable_depth) {
            spatialNN->setDepthLowerThreshold(config.depth_min_mm);
            spatialNN->setDepthUpperThreshold(config.depth_max_mm);
        }

        // --- Link nodes ---
        colorCam->preview.link(manip->inputImage);
        manip->out.link(spatialNN->input);
        spatialNN->passthrough.link(xoutRgb->input);
        spatialNN->out.link(xoutNN->input);

        if (config.enable_depth && stereo && xoutDepth) {
            stereo->depth.link(spatialNN->inputDepth);
            spatialNN->passthroughDepth.link(xoutDepth->input);
        }

        return pipeline;

    } catch (const std::exception&) {
        return std::nullopt;
    }
}

}  // namespace cotton_detection
