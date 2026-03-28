// test_pipeline_builder.cpp — PipelineBuilder unit tests.
// Links against depthai::core (pipeline construction requires DepthAI SDK types).
// RED phase: Tasks 3.2-3.4. GREEN phase validates all pass.

#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>

#include <depthai/depthai.hpp>

#include "cotton_detection_ros2/pipeline_builder.hpp"

namespace cotton_detection::test {

// Helper: default config with a valid (dummy) model path.
// Note: setBlobPath() reads a real file, so build() tests that need a blob
// must provide one.  Validation tests don't need a blob — they only call validate().
static CameraConfig defaultConfig() {
    CameraConfig cfg;
    // Defaults from camera_config.hpp are already valid:
    // 416x416, 30 FPS, 0.5 confidence, 100-5000mm depth, BGR, depth enabled
    return cfg;
}

// =============================================================================
// Task 3.2: Config Validation Tests
// =============================================================================

class ValidationTest : public ::testing::Test {
protected:
    PipelineBuilder builder;
    static constexpr const char* DUMMY_MODEL = "/tmp/dummy_model.blob";
};

// --- Scenario: Valid default config passes validation ---
TEST_F(ValidationTest, ValidDefaultConfigPasses) {
    auto result = builder.validate(defaultConfig(), DUMMY_MODEL);
    EXPECT_TRUE(result.valid) << "Errors: " << result.messages;
    // No error text (warnings OK)
}

// --- Scenario: Confidence threshold below zero is rejected ---
TEST_F(ValidationTest, ConfidenceBelowZeroRejected) {
    auto cfg = defaultConfig();
    cfg.confidence_threshold = -0.1f;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_FALSE(result.valid);
    EXPECT_NE(result.messages.find("confidence"), std::string::npos);
}

// --- Scenario: Confidence threshold above one is rejected ---
TEST_F(ValidationTest, ConfidenceAboveOneRejected) {
    auto cfg = defaultConfig();
    cfg.confidence_threshold = 1.5f;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_FALSE(result.valid);
    EXPECT_NE(result.messages.find("confidence"), std::string::npos);
}

// --- Scenario: FPS below minimum is rejected ---
TEST_F(ValidationTest, FpsZeroRejected) {
    auto cfg = defaultConfig();
    cfg.fps = 0;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_FALSE(result.valid);
    EXPECT_NE(result.messages.find("FPS"), std::string::npos);
}

// --- Scenario: FPS above maximum is rejected ---
TEST_F(ValidationTest, Fps61Rejected) {
    auto cfg = defaultConfig();
    cfg.fps = 61;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_FALSE(result.valid);
    EXPECT_NE(result.messages.find("FPS"), std::string::npos);
}

// --- Scenario: FPS boundary values are accepted ---
TEST_F(ValidationTest, FpsBoundariesAccepted) {
    auto cfg1 = defaultConfig();
    cfg1.fps = 1;
    EXPECT_TRUE(builder.validate(cfg1, DUMMY_MODEL).valid);

    auto cfg60 = defaultConfig();
    cfg60.fps = 60;
    EXPECT_TRUE(builder.validate(cfg60, DUMMY_MODEL).valid);
}

// --- Scenario: Depth min >= depth max is rejected ---
TEST_F(ValidationTest, DepthMinEqualMaxRejected) {
    auto cfg = defaultConfig();
    cfg.depth_min_mm = 5000.0f;
    cfg.depth_max_mm = 5000.0f;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_FALSE(result.valid);
    EXPECT_NE(result.messages.find("depth"), std::string::npos);
}

// --- Scenario: Negative depth min is rejected ---
TEST_F(ValidationTest, NegativeDepthMinRejected) {
    auto cfg = defaultConfig();
    cfg.depth_min_mm = -1.0f;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_FALSE(result.valid);
    EXPECT_NE(result.messages.find("depth"), std::string::npos);
}

// --- Scenario: Depth range exceeding 50m warns but passes ---
TEST_F(ValidationTest, DepthMax60000WarnsButPasses) {
    auto cfg = defaultConfig();
    cfg.depth_max_mm = 60000.0f;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_TRUE(result.valid);
    // Should contain a warning about large depth
    EXPECT_FALSE(result.messages.empty());
}

// --- Scenario: Invalid color order is rejected ---
TEST_F(ValidationTest, InvalidColorOrderRejected) {
    auto cfg = defaultConfig();
    cfg.color_order = "GBR";
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_FALSE(result.valid);
    EXPECT_NE(result.messages.find("color order"), std::string::npos)
        << "Got: " << result.messages;
}

// --- Scenario: Image dimensions not multiples of 16 warn but pass ---
TEST_F(ValidationTest, DimensionsNot16MultiplesWarn) {
    auto cfg = defaultConfig();
    cfg.width = 300;
    cfg.height = 300;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_TRUE(result.valid);
    EXPECT_FALSE(result.messages.empty())
        << "Expected warning about non-16 dimensions";
}

// --- Scenario: Image dimensions out of range are rejected ---
TEST_F(ValidationTest, WidthZeroRejected) {
    auto cfg = defaultConfig();
    cfg.width = 0;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_FALSE(result.valid);
}

TEST_F(ValidationTest, Width5000Rejected) {
    auto cfg = defaultConfig();
    cfg.width = 5000;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_FALSE(result.valid);
}

// --- Scenario: Empty model path is rejected ---
TEST_F(ValidationTest, EmptyModelPathRejected) {
    auto cfg = defaultConfig();
    auto result = builder.validate(cfg, "");
    EXPECT_FALSE(result.valid);
    // Message should indicate model path is required
    EXPECT_NE(result.messages.find("model"), std::string::npos)
        << "Got: " << result.messages;
}

// --- Scenario: Multiple validation errors accumulate ---
TEST_F(ValidationTest, MultipleErrorsAccumulate) {
    auto cfg = defaultConfig();
    cfg.fps = 0;
    cfg.confidence_threshold = -1.0f;
    cfg.depth_min_mm = -5.0f;
    auto result = builder.validate(cfg, DUMMY_MODEL);
    EXPECT_FALSE(result.valid);
    EXPECT_NE(result.messages.find("FPS"), std::string::npos);
    EXPECT_NE(result.messages.find("confidence"), std::string::npos);
    EXPECT_NE(result.messages.find("depth"), std::string::npos);
}

// =============================================================================
// Task 3.3: Pipeline Construction Tests
// =============================================================================

// These tests construct real dai::Pipeline objects (no device needed).
// PipelineBuilder::build() returns std::optional<dai::Pipeline>.
//
// Helper to count nodes of a specific type in a pipeline.
template <typename NodeType>
std::vector<std::shared_ptr<NodeType>> findNodes(dai::Pipeline& pipeline) {
    std::vector<std::shared_ptr<NodeType>> result;
    for (auto& node : pipeline.getAllNodes()) {
        auto typed = std::dynamic_pointer_cast<NodeType>(node);
        if (typed) {
            result.push_back(typed);
        }
    }
    return result;
}

// Helper to find a single XLinkOut by stream name.
std::shared_ptr<dai::node::XLinkOut> findXLinkOut(
    dai::Pipeline& pipeline, const std::string& streamName) {
    for (auto& node : pipeline.getAllNodes()) {
        auto xout = std::dynamic_pointer_cast<dai::node::XLinkOut>(node);
        if (xout && xout->getStreamName() == streamName) {
            return xout;
        }
    }
    return nullptr;
}

// Helper to find a single XLinkIn by stream name.
std::shared_ptr<dai::node::XLinkIn> findXLinkIn(
    dai::Pipeline& pipeline, const std::string& streamName) {
    for (auto& node : pipeline.getAllNodes()) {
        auto xin = std::dynamic_pointer_cast<dai::node::XLinkIn>(node);
        if (xin && xin->getStreamName() == streamName) {
            return xin;
        }
    }
    return nullptr;
}

class PipelineBuildTest : public ::testing::Test {
protected:
    PipelineBuilder builder;

    // Build with default config. No blob file needed — we skip blob path
    // validation by using build() which calls validate() first.
    // For actual pipeline construction tests we need build() to succeed,
    // so we use a dummy path and expect the implementation to handle
    // non-existent blobs gracefully (or we create a real tiny blob).
    //
    // Strategy: Since setBlobPath() throws on non-existent files, our
    // implementation must handle this. Tests that need a pipeline will
    // set model_path to a path that exists (we create a tiny dummy blob).

    // Resolve the path to a real .blob file relative to this test source file.
    // setBlobPath() validates blob content (not just existence), so a dummy
    // file of zeros won't work — we must use an actual OpenVINO blob.
    static std::string resolveBlobPath() {
        // __FILE__ is e.g. .../src/cotton_detection_ros2/test/test_pipeline_builder.cpp
        // Navigate up 2 levels to the package root, then into models/.
        std::filesystem::path test_file(__FILE__);
        auto pkg_root = test_file.parent_path().parent_path();  // .../src/cotton_detection_ros2
        auto blob = pkg_root / "models" / "yolov8.blob";
        if (!std::filesystem::exists(blob)) {
            // Fallback: try yolov11.blob
            blob = pkg_root / "models" / "yolov11.blob";
        }
        return blob.string();
    }

    static inline std::string test_blob_path_;

    static void SetUpTestSuite() {
        test_blob_path_ = resolveBlobPath();
        ASSERT_TRUE(std::filesystem::exists(test_blob_path_))
            << "No blob file found at: " << test_blob_path_;
    }

    static void TearDownTestSuite() {}

    static const std::string& TEST_BLOB_PATH() { return test_blob_path_; }
};

// --- Scenario: Color camera at 1080p with correct FPS/color order ---
TEST_F(PipelineBuildTest, ColorCamera1080pConfig) {
    auto cfg = defaultConfig();
    cfg.fps = 30;
    cfg.color_order = "BGR";
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value()) << "build() returned nullopt";
    auto& pipeline = result.value();

    auto cameras = findNodes<dai::node::ColorCamera>(pipeline);
    ASSERT_EQ(cameras.size(), 1u);
    auto& cam = cameras[0];

    EXPECT_EQ(cam->getResolution(),
              dai::ColorCameraProperties::SensorResolution::THE_1080_P);
    auto [pw, ph] = cam->getPreviewSize();
    EXPECT_EQ(pw, 1920);
    EXPECT_EQ(ph, 1080);
    EXPECT_FLOAT_EQ(cam->getFps(), 30.0f);
    EXPECT_EQ(cam->getColorOrder(),
              dai::ColorCameraProperties::ColorOrder::BGR);
}

// --- Scenario: ImageManip resizes to NN input dimensions ---
TEST_F(PipelineBuildTest, ImageManipResizeToNNDims) {
    auto cfg = defaultConfig();
    cfg.width = 416;
    cfg.height = 416;
    cfg.keep_aspect_ratio = true;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto manips = findNodes<dai::node::ImageManip>(pipeline);
    ASSERT_EQ(manips.size(), 1u);
    auto& manip = manips[0];

    EXPECT_EQ(manip->initialConfig.getResizeWidth(), 416);
    EXPECT_EQ(manip->initialConfig.getResizeHeight(), 416);

    auto fmt = manip->initialConfig.getFormatConfig();
    EXPECT_EQ(fmt.type, dai::RawImgFrame::Type::BGR888p);

    // Max output frame size >= 7MB (for 1920x1080 input)
    EXPECT_GE(manip->properties.outputFrameSize, 7 * 1024 * 1024);
}

// --- Scenario: Auto exposure is configured by default ---
TEST_F(PipelineBuildTest, AutoExposureDefault) {
    auto cfg = defaultConfig();
    cfg.exposure_mode = "auto";
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto cameras = findNodes<dai::node::ColorCamera>(pipeline);
    ASSERT_EQ(cameras.size(), 1u);
    // Auto exposure is the default mode — verify manual exposure time is NOT set
    // (getExposureTime returns 0 when not explicitly configured).
    auto exposure_us = cameras[0]->initialControl.getExposureTime();
    EXPECT_EQ(exposure_us.count(), 0) << "Auto-exposure should not set manual exposure time";
}

// --- Scenario: Manual exposure uses config values ---
TEST_F(PipelineBuildTest, ManualExposureConfig) {
    auto cfg = defaultConfig();
    cfg.exposure_mode = "manual";
    cfg.exposure_time_us = 8000;
    cfg.exposure_iso = 400;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto cameras = findNodes<dai::node::ColorCamera>(pipeline);
    ASSERT_EQ(cameras.size(), 1u);
    auto exposure_us = cameras[0]->initialControl.getExposureTime();
    auto iso = cameras[0]->initialControl.getSensitivity();
    EXPECT_EQ(exposure_us.count(), 8000);
    EXPECT_EQ(iso, 400);
}

// --- Scenario: Camera control XLinkIn is present ---
TEST_F(PipelineBuildTest, CameraControlXLinkInPresent) {
    auto result = builder.build(defaultConfig(), TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto xin = findXLinkIn(pipeline, "colorCamControl");
    ASSERT_NE(xin, nullptr) << "XLinkIn 'colorCamControl' not found";
}

// --- Scenario: Stereo depth nodes created when depth enabled ---
TEST_F(PipelineBuildTest, StereoDepthNodesWhenEnabled) {
    auto cfg = defaultConfig();
    cfg.enable_depth = true;
    cfg.fps = 30;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    // Two mono cameras
    auto monos = findNodes<dai::node::MonoCamera>(pipeline);
    ASSERT_EQ(monos.size(), 2u);

    // Find left (CAM_B) and right (CAM_C)
    std::shared_ptr<dai::node::MonoCamera> left, right;
    for (auto& m : monos) {
        if (m->getBoardSocket() == dai::CameraBoardSocket::CAM_B) left = m;
        if (m->getBoardSocket() == dai::CameraBoardSocket::CAM_C) right = m;
    }
    ASSERT_NE(left, nullptr) << "Left mono (CAM_B) not found";
    ASSERT_NE(right, nullptr) << "Right mono (CAM_C) not found";

    EXPECT_EQ(left->getResolution(),
              dai::MonoCameraProperties::SensorResolution::THE_400_P);
    EXPECT_EQ(right->getResolution(),
              dai::MonoCameraProperties::SensorResolution::THE_400_P);
    EXPECT_FLOAT_EQ(left->getFps(), 30.0f);
    EXPECT_FLOAT_EQ(right->getFps(), 30.0f);

    // StereoDepth node
    auto stereos = findNodes<dai::node::StereoDepth>(pipeline);
    ASSERT_EQ(stereos.size(), 1u);

    auto& stereo = stereos[0];
    // Depth aligned to CAM_A
    EXPECT_EQ(stereo->properties.depthAlignCamera,
              dai::CameraBoardSocket::CAM_A);
}

// --- Scenario: Stereo depth configurable parameters ---
TEST_F(PipelineBuildTest, StereoDepthConfigurableParams) {
    auto cfg = defaultConfig();
    cfg.enable_depth = true;
    cfg.stereo_confidence_threshold = 200;
    cfg.extended_disparity = true;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto stereos = findNodes<dai::node::StereoDepth>(pipeline);
    ASSERT_EQ(stereos.size(), 1u);
    auto& stereo = stereos[0];

    EXPECT_EQ(stereo->initialConfig.getConfidenceThreshold(), 200);

    // Read back via properties.initialConfig (RawStereoDepthConfig)
    auto rawCfg = stereo->properties.initialConfig;
    EXPECT_TRUE(rawCfg.algorithmControl.enableLeftRightCheck);
    EXPECT_FALSE(rawCfg.algorithmControl.enableSubpixel);
    EXPECT_TRUE(rawCfg.algorithmControl.enableExtended);

    EXPECT_EQ(stereo->initialConfig.getMedianFilter(),
              dai::MedianFilter::KERNEL_7x7);
}

// --- Scenario: Mono camera controls present when depth enabled ---
TEST_F(PipelineBuildTest, MonoControlsWhenDepthEnabled) {
    auto cfg = defaultConfig();
    cfg.enable_depth = true;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    EXPECT_NE(findXLinkIn(pipeline, "monoLeftControl"), nullptr);
    EXPECT_NE(findXLinkIn(pipeline, "monoRightControl"), nullptr);
}

// --- Scenario: No stereo nodes when depth disabled ---
TEST_F(PipelineBuildTest, NoStereoNodesWhenDepthDisabled) {
    auto cfg = defaultConfig();
    cfg.enable_depth = false;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    EXPECT_EQ(findNodes<dai::node::MonoCamera>(pipeline).size(), 0u);
    EXPECT_EQ(findNodes<dai::node::StereoDepth>(pipeline).size(), 0u);
    EXPECT_EQ(findXLinkIn(pipeline, "monoLeftControl"), nullptr);
    EXPECT_EQ(findXLinkIn(pipeline, "monoRightControl"), nullptr);
    EXPECT_EQ(findXLinkOut(pipeline, "depth"), nullptr);
}

// --- Scenario: Spatial NN configured with correct model and thresholds ---
TEST_F(PipelineBuildTest, SpatialNNConfig) {
    auto cfg = defaultConfig();
    cfg.confidence_threshold = 0.5f;
    cfg.bbox_scale_factor = 0.5f;
    cfg.enable_depth = true;
    cfg.depth_min_mm = 100.0f;
    cfg.depth_max_mm = 5000.0f;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto nns = findNodes<dai::node::YoloSpatialDetectionNetwork>(pipeline);
    ASSERT_EQ(nns.size(), 1u);
    auto& nn = nns[0];

    EXPECT_FLOAT_EQ(nn->getConfidenceThreshold(), 0.5f);
    EXPECT_FLOAT_EQ(nn->properties.detectedBBScaleFactor, 0.5f);
    EXPECT_EQ(nn->properties.depthThresholds.lowerThreshold, 100u);
    EXPECT_EQ(nn->properties.depthThresholds.upperThreshold, 5000u);
}

// --- Scenario: NN input is non-blocking with small queue ---
TEST_F(PipelineBuildTest, NNInputNonBlocking) {
    auto result = builder.build(defaultConfig(), TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto nns = findNodes<dai::node::YoloSpatialDetectionNetwork>(pipeline);
    ASSERT_EQ(nns.size(), 1u);
    EXPECT_FALSE(nns[0]->input.getBlocking());
    EXPECT_EQ(nns[0]->input.getQueueSize(), 2);
}

// --- Scenario: YOLOv8 configuration includes anchors ---
TEST_F(PipelineBuildTest, Yolov8Anchors) {
    auto cfg = defaultConfig();
    cfg.num_classes = 1;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto nns = findNodes<dai::node::YoloSpatialDetectionNetwork>(pipeline);
    ASSERT_EQ(nns.size(), 1u);
    auto& nn = nns[0];

    EXPECT_EQ(nn->getNumClasses(), 1);
    EXPECT_EQ(nn->getCoordinateSize(), 4);
    EXPECT_FLOAT_EQ(nn->getIouThreshold(), 0.5f);

    // 9 anchor pairs = 18 float values
    auto anchors = nn->getAnchors();
    EXPECT_EQ(anchors.size(), 18u);

    auto masks = nn->getAnchorMasks();
    EXPECT_TRUE(masks.count("side52"));
    EXPECT_TRUE(masks.count("side26"));
    EXPECT_TRUE(masks.count("side13"));
}

// --- Scenario: YOLOv11 configuration is anchor-free ---
TEST_F(PipelineBuildTest, Yolov11AnchorFree) {
    auto cfg = defaultConfig();
    cfg.num_classes = 2;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto nns = findNodes<dai::node::YoloSpatialDetectionNetwork>(pipeline);
    ASSERT_EQ(nns.size(), 1u);
    auto& nn = nns[0];

    EXPECT_EQ(nn->getNumClasses(), 2);
    EXPECT_EQ(nn->getCoordinateSize(), 4);
    EXPECT_FLOAT_EQ(nn->getIouThreshold(), 0.5f);

    // Anchor-free: no anchors or masks set
    EXPECT_TRUE(nn->getAnchors().empty());
    EXPECT_TRUE(nn->getAnchorMasks().empty());
}

// --- Scenario: Depth thresholds not set when depth disabled ---
TEST_F(PipelineBuildTest, NoDepthThresholdsWhenDisabled) {
    auto cfg = defaultConfig();
    cfg.enable_depth = false;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto nns = findNodes<dai::node::YoloSpatialDetectionNetwork>(pipeline);
    ASSERT_EQ(nns.size(), 1u);

    // When depth is disabled, depth thresholds should be at their defaults
    // (0 and 65535), not the config values.
    EXPECT_EQ(nns[0]->properties.depthThresholds.lowerThreshold, 0u);
    EXPECT_EQ(nns[0]->properties.depthThresholds.upperThreshold, 65535u);
}

// --- Scenario: Node linking for full pipeline (depth enabled) ---
TEST_F(PipelineBuildTest, NodeLinkingFullPipeline) {
    auto cfg = defaultConfig();
    cfg.enable_depth = true;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    auto connections = pipeline.getConnections();
    // We expect at minimum these connections:
    // 1. ColorCamera preview -> ImageManip input
    // 2. ImageManip out -> SpatialNN input
    // 3. SpatialNN passthrough -> "rgb" XLinkOut
    // 4. SpatialNN out -> "detections" XLinkOut
    // 5. StereoDepth depth -> SpatialNN inputDepth
    // 6. SpatialNN passthroughDepth -> "depth" XLinkOut
    // 7. MonoLeft out -> StereoDepth left
    // 8. MonoRight out -> StereoDepth right
    // 9. colorCamControl -> ColorCamera inputControl
    // 10. monoLeftControl -> MonoLeft inputControl
    // 11. monoRightControl -> MonoRight inputControl
    EXPECT_GE(connections.size(), 11u)
        << "Expected at least 11 connections for full pipeline";

    // Verify key XLinkOut streams exist
    EXPECT_NE(findXLinkOut(pipeline, "rgb"), nullptr);
    EXPECT_NE(findXLinkOut(pipeline, "detections"), nullptr);
    EXPECT_NE(findXLinkOut(pipeline, "depth"), nullptr);
}

// --- Scenario: Node linking for color-only pipeline (depth disabled) ---
TEST_F(PipelineBuildTest, NodeLinkingColorOnly) {
    auto cfg = defaultConfig();
    cfg.enable_depth = false;
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    ASSERT_TRUE(result.has_value());
    auto& pipeline = result.value();

    // Key XLinkOut streams
    EXPECT_NE(findXLinkOut(pipeline, "rgb"), nullptr);
    EXPECT_NE(findXLinkOut(pipeline, "detections"), nullptr);

    // No depth-related outputs
    EXPECT_EQ(findXLinkOut(pipeline, "depth"), nullptr);
}

// =============================================================================
// Task 3.4: Stateless Operation Tests
// =============================================================================

// --- Scenario: Sequential builds with different FPS produce distinct pipelines ---
TEST_F(PipelineBuildTest, SequentialBuildsDifferentFPS) {
    auto cfg30 = defaultConfig();
    cfg30.fps = 30;
    auto result30 = builder.build(cfg30, TEST_BLOB_PATH());
    ASSERT_TRUE(result30.has_value());

    auto cfg15 = defaultConfig();
    cfg15.fps = 15;
    auto result15 = builder.build(cfg15, TEST_BLOB_PATH());
    ASSERT_TRUE(result15.has_value());

    auto cams30 = findNodes<dai::node::ColorCamera>(result30.value());
    auto cams15 = findNodes<dai::node::ColorCamera>(result15.value());
    ASSERT_EQ(cams30.size(), 1u);
    ASSERT_EQ(cams15.size(), 1u);

    EXPECT_FLOAT_EQ(cams30[0]->getFps(), 30.0f);
    EXPECT_FLOAT_EQ(cams15[0]->getFps(), 15.0f);

    // First pipeline unaffected by second build
    EXPECT_FLOAT_EQ(cams30[0]->getFps(), 30.0f);
}

// --- Scenario: Sequential builds update mono cameras FPS ---
TEST_F(PipelineBuildTest, SequentialBuildsMonoCameraFPS) {
    auto cfg30 = defaultConfig();
    cfg30.fps = 30;
    cfg30.enable_depth = true;
    auto result30 = builder.build(cfg30, TEST_BLOB_PATH());
    ASSERT_TRUE(result30.has_value());

    auto cfg15 = defaultConfig();
    cfg15.fps = 15;
    cfg15.enable_depth = true;
    auto result15 = builder.build(cfg15, TEST_BLOB_PATH());
    ASSERT_TRUE(result15.has_value());

    auto monos30 = findNodes<dai::node::MonoCamera>(result30.value());
    auto monos15 = findNodes<dai::node::MonoCamera>(result15.value());
    ASSERT_EQ(monos30.size(), 2u);
    ASSERT_EQ(monos15.size(), 2u);

    for (auto& m : monos30) EXPECT_FLOAT_EQ(m->getFps(), 30.0f);
    for (auto& m : monos15) EXPECT_FLOAT_EQ(m->getFps(), 15.0f);
}

// --- Scenario: Sequential builds with different confidence ---
TEST_F(PipelineBuildTest, SequentialBuildsDifferentConfidence) {
    auto cfg03 = defaultConfig();
    cfg03.confidence_threshold = 0.3f;
    auto result03 = builder.build(cfg03, TEST_BLOB_PATH());
    ASSERT_TRUE(result03.has_value());

    auto cfg07 = defaultConfig();
    cfg07.confidence_threshold = 0.7f;
    auto result07 = builder.build(cfg07, TEST_BLOB_PATH());
    ASSERT_TRUE(result07.has_value());

    auto nns03 = findNodes<dai::node::YoloSpatialDetectionNetwork>(
        result03.value());
    auto nns07 = findNodes<dai::node::YoloSpatialDetectionNetwork>(
        result07.value());
    ASSERT_EQ(nns03.size(), 1u);
    ASSERT_EQ(nns07.size(), 1u);

    EXPECT_FLOAT_EQ(nns03[0]->getConfidenceThreshold(), 0.3f);
    EXPECT_FLOAT_EQ(nns07[0]->getConfidenceThreshold(), 0.7f);
}

// --- Scenario: Validation failure prevents build ---
TEST_F(PipelineBuildTest, ValidationFailurePreventsPartialBuild) {
    auto cfg = defaultConfig();
    cfg.fps = 0;  // Invalid
    auto result = builder.build(cfg, TEST_BLOB_PATH());
    EXPECT_FALSE(result.has_value())
        << "build() should return nullopt for invalid config";
}

// --- Scenario: Builder has no mutable member state ---
// (Compile-time check: verify build/validate are const methods)
TEST_F(PipelineBuildTest, ConstMethodsCompile) {
    const PipelineBuilder const_builder;
    auto vr = const_builder.validate(defaultConfig(), TEST_BLOB_PATH());
    (void)vr;
    // If this compiles, the methods are const.
    SUCCEED();
}

}  // namespace cotton_detection::test
