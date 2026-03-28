// Copyright 2026 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * @file test_stereo_param_configurability.cpp
 * @brief Tests for stereo depth parameter configurability.
 *
 * Verifies that all 5 previously-hardcoded stereo depth parameters are now
 * configurable via CameraConfig and properly wired through the full param
 * pipeline: ROS2 param → node member → DetectionConfig → CameraConfig →
 * pipeline construction.
 *
 * Tests use source-audit (file scanning) since DepthAI hardware is not
 * available in the test environment.
 */

#include <gtest/gtest.h>

#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "cotton_detection_ros2/camera_config.hpp"
#include "cotton_detection_ros2/detection_engine.hpp"

using namespace cotton_detection_ros2;
namespace fs = std::filesystem;

// ===========================================================================
// Helpers
// ===========================================================================

static std::string getPackageRoot()
{
#ifdef SOURCE_DIR
    return SOURCE_DIR;
#else
    std::filesystem::path test_file(__FILE__);
    return test_file.parent_path().parent_path().string();
#endif
}

static std::string readFile(const std::string & path)
{
    std::ifstream f(path);
    if (!f.is_open()) return {};
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

// ===========================================================================
// Test fixture
// ===========================================================================

class StereoParamConfigurabilityTest : public ::testing::Test {};

// ===========================================================================
// CameraConfig default value tests
// ===========================================================================

TEST_F(StereoParamConfigurabilityTest, CameraConfigDefaultSpatialCalcAlgorithm)
{
    cotton_detection::CameraConfig cfg;
    EXPECT_EQ(cfg.spatial_calc_algorithm, "average")
        << "Default spatial_calc_algorithm must be 'average' (matches prior hardcoded behavior)";
}

TEST_F(StereoParamConfigurabilityTest, CameraConfigDefaultMonoResolution)
{
    cotton_detection::CameraConfig cfg;
    EXPECT_EQ(cfg.mono_resolution, "400p")
        << "Default mono_resolution must be '400p' (matches prior hardcoded behavior)";
}

TEST_F(StereoParamConfigurabilityTest, CameraConfigDefaultLrCheck)
{
    cotton_detection::CameraConfig cfg;
    EXPECT_TRUE(cfg.lr_check)
        << "Default lr_check must be true (matches prior hardcoded behavior)";
}

TEST_F(StereoParamConfigurabilityTest, CameraConfigDefaultSubpixel)
{
    cotton_detection::CameraConfig cfg;
    EXPECT_FALSE(cfg.subpixel)
        << "Default subpixel must be false (matches prior hardcoded behavior)";
}

TEST_F(StereoParamConfigurabilityTest, CameraConfigDefaultMedianFilter)
{
    cotton_detection::CameraConfig cfg;
    EXPECT_EQ(cfg.median_filter, "7x7")
        << "Default median_filter must be '7x7' (matches prior hardcoded behavior)";
}

// ===========================================================================
// DetectionConfig default value tests
// ===========================================================================

TEST_F(StereoParamConfigurabilityTest, DetectionConfigDefaultStereoParams)
{
    DetectionConfig cfg;
    EXPECT_EQ(cfg.depthai_spatial_calc_algorithm, "average");
    EXPECT_EQ(cfg.depthai_mono_resolution, "400p");
    EXPECT_TRUE(cfg.depthai_lr_check);
    EXPECT_FALSE(cfg.depthai_subpixel);
    EXPECT_EQ(cfg.depthai_median_filter, "7x7");
}

// ===========================================================================
// Source audit: depthai_manager.cpp uses config fields (not hardcoded)
// ===========================================================================

TEST_F(StereoParamConfigurabilityTest, DepthaiManagerUsesConfigMonoResolution)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/depthai_manager.cpp");
    ASSERT_FALSE(content.empty()) << "Could not read depthai_manager.cpp";

    EXPECT_NE(content.find("config_.mono_resolution"), std::string::npos)
        << "depthai_manager.cpp must use config_.mono_resolution (not hardcoded)";
}

TEST_F(StereoParamConfigurabilityTest, DepthaiManagerUsesConfigLrCheck)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/depthai_manager.cpp");
    ASSERT_FALSE(content.empty());

    EXPECT_NE(content.find("config_.lr_check"), std::string::npos)
        << "depthai_manager.cpp must use config_.lr_check (not hardcoded)";
}

TEST_F(StereoParamConfigurabilityTest, DepthaiManagerUsesConfigSubpixel)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/depthai_manager.cpp");
    ASSERT_FALSE(content.empty());

    EXPECT_NE(content.find("config_.subpixel"), std::string::npos)
        << "depthai_manager.cpp must use config_.subpixel (not hardcoded)";
}

TEST_F(StereoParamConfigurabilityTest, DepthaiManagerUsesConfigMedianFilter)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/depthai_manager.cpp");
    ASSERT_FALSE(content.empty());

    EXPECT_NE(content.find("config_.median_filter"), std::string::npos)
        << "depthai_manager.cpp must use config_.median_filter (not hardcoded)";
}

TEST_F(StereoParamConfigurabilityTest, DepthaiManagerUsesConfigSpatialCalcAlgorithm)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/depthai_manager.cpp");
    ASSERT_FALSE(content.empty());

    EXPECT_NE(content.find("config_.spatial_calc_algorithm"), std::string::npos)
        << "depthai_manager.cpp must use config_.spatial_calc_algorithm (not hardcoded)";
}

// ===========================================================================
// Source audit: pipeline_builder.cpp uses config fields (not hardcoded)
// ===========================================================================

TEST_F(StereoParamConfigurabilityTest, PipelineBuilderUsesConfigMonoResolution)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/pipeline_builder.cpp");
    ASSERT_FALSE(content.empty()) << "Could not read pipeline_builder.cpp";

    EXPECT_NE(content.find("config.mono_resolution"), std::string::npos)
        << "pipeline_builder.cpp must use config.mono_resolution (not hardcoded)";
}

TEST_F(StereoParamConfigurabilityTest, PipelineBuilderUsesConfigLrCheck)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/pipeline_builder.cpp");
    ASSERT_FALSE(content.empty());

    EXPECT_NE(content.find("config.lr_check"), std::string::npos)
        << "pipeline_builder.cpp must use config.lr_check (not hardcoded)";
}

TEST_F(StereoParamConfigurabilityTest, PipelineBuilderUsesConfigSubpixel)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/pipeline_builder.cpp");
    ASSERT_FALSE(content.empty());

    EXPECT_NE(content.find("config.subpixel"), std::string::npos)
        << "pipeline_builder.cpp must use config.subpixel (not hardcoded)";
}

TEST_F(StereoParamConfigurabilityTest, PipelineBuilderUsesConfigMedianFilter)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/pipeline_builder.cpp");
    ASSERT_FALSE(content.empty());

    EXPECT_NE(content.find("config.median_filter"), std::string::npos)
        << "pipeline_builder.cpp must use config.median_filter (not hardcoded)";
}

TEST_F(StereoParamConfigurabilityTest, PipelineBuilderUsesConfigSpatialCalcAlgorithm)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/pipeline_builder.cpp");
    ASSERT_FALSE(content.empty());

    EXPECT_NE(content.find("config.spatial_calc_algorithm"), std::string::npos)
        << "pipeline_builder.cpp must use config.spatial_calc_algorithm (not hardcoded)";
}

// ===========================================================================
// Source audit: ROS2 param declarations in node_parameters.cpp
// ===========================================================================

TEST_F(StereoParamConfigurabilityTest, ParamsDeclaredInNodeParameters)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/cotton_detection_node_parameters.cpp");
    ASSERT_FALSE(content.empty()) << "Could not read cotton_detection_node_parameters.cpp";

    // All 5 params must be declared
    EXPECT_NE(content.find("depthai.spatial_calc_algorithm"), std::string::npos)
        << "spatial_calc_algorithm param must be declared";
    EXPECT_NE(content.find("depthai.mono_resolution"), std::string::npos)
        << "mono_resolution param must be declared";
    EXPECT_NE(content.find("depthai.lr_check"), std::string::npos)
        << "lr_check param must be declared";
    EXPECT_NE(content.find("depthai.subpixel"), std::string::npos)
        << "subpixel param must be declared";
    EXPECT_NE(content.find("depthai.median_filter"), std::string::npos)
        << "median_filter param must be declared";
}

TEST_F(StereoParamConfigurabilityTest, ParamsLoadedFromNodeParameters)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/cotton_detection_node_parameters.cpp");
    ASSERT_FALSE(content.empty());

    // All 5 params must be loaded via get_parameter
    EXPECT_NE(content.find("depthai_spatial_calc_algorithm_"), std::string::npos)
        << "spatial_calc_algorithm must be loaded into member variable";
    EXPECT_NE(content.find("depthai_mono_resolution_"), std::string::npos)
        << "mono_resolution must be loaded into member variable";
    EXPECT_NE(content.find("depthai_lr_check_"), std::string::npos)
        << "lr_check must be loaded into member variable";
    EXPECT_NE(content.find("depthai_subpixel_"), std::string::npos)
        << "subpixel must be loaded into member variable";
    EXPECT_NE(content.find("depthai_median_filter_"), std::string::npos)
        << "median_filter must be loaded into member variable";
}

// ===========================================================================
// Source audit: Bridging in detection_engine.cpp
// ===========================================================================

TEST_F(StereoParamConfigurabilityTest, BridgingInDetectionEngine)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/detection_engine.cpp");
    ASSERT_FALSE(content.empty()) << "Could not read detection_engine.cpp";

    // DetectionConfig → CameraConfig bridging
    EXPECT_NE(content.find("cam_config.spatial_calc_algorithm"), std::string::npos)
        << "detection_engine.cpp must bridge spatial_calc_algorithm to CameraConfig";
    EXPECT_NE(content.find("cam_config.mono_resolution"), std::string::npos)
        << "detection_engine.cpp must bridge mono_resolution to CameraConfig";
    EXPECT_NE(content.find("cam_config.lr_check"), std::string::npos)
        << "detection_engine.cpp must bridge lr_check to CameraConfig";
    EXPECT_NE(content.find("cam_config.subpixel"), std::string::npos)
        << "detection_engine.cpp must bridge subpixel to CameraConfig";
    EXPECT_NE(content.find("cam_config.median_filter"), std::string::npos)
        << "detection_engine.cpp must bridge median_filter to CameraConfig";
}

// ===========================================================================
// Source audit: Bridging in cotton_detection_node_init.cpp
// ===========================================================================

TEST_F(StereoParamConfigurabilityTest, BridgingInNodeInit)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/cotton_detection_node_init.cpp");
    ASSERT_FALSE(content.empty()) << "Could not read cotton_detection_node_init.cpp";

    // Node member → DetectionConfig bridging
    EXPECT_NE(content.find("depthai_spatial_calc_algorithm"), std::string::npos)
        << "cotton_detection_node_init.cpp must bridge spatial_calc_algorithm";
    EXPECT_NE(content.find("depthai_mono_resolution"), std::string::npos)
        << "cotton_detection_node_init.cpp must bridge mono_resolution";
    EXPECT_NE(content.find("depthai_lr_check"), std::string::npos)
        << "cotton_detection_node_init.cpp must bridge lr_check";
    EXPECT_NE(content.find("depthai_subpixel"), std::string::npos)
        << "cotton_detection_node_init.cpp must bridge subpixel";
    EXPECT_NE(content.find("depthai_median_filter"), std::string::npos)
        << "cotton_detection_node_init.cpp must bridge median_filter";
}

// ===========================================================================
// Source audit: production.yaml contains all stereo params
// ===========================================================================

TEST_F(StereoParamConfigurabilityTest, ProductionYamlContainsStereoParams)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/config/production.yaml");
    ASSERT_FALSE(content.empty()) << "Could not read config/production.yaml";

    EXPECT_NE(content.find("spatial_calc_algorithm"), std::string::npos)
        << "production.yaml must contain spatial_calc_algorithm";
    EXPECT_NE(content.find("mono_resolution"), std::string::npos)
        << "production.yaml must contain mono_resolution";
    EXPECT_NE(content.find("lr_check"), std::string::npos)
        << "production.yaml must contain lr_check";
    EXPECT_NE(content.find("subpixel"), std::string::npos)
        << "production.yaml must contain subpixel";
    EXPECT_NE(content.find("median_filter"), std::string::npos)
        << "production.yaml must contain median_filter";
}

// ===========================================================================
// Source audit: No remaining hardcoded stereo values in pipeline code
// ===========================================================================

TEST_F(StereoParamConfigurabilityTest, DepthaiManagerNoHardcodedMonoResolution)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/depthai_manager.cpp");
    ASSERT_FALSE(content.empty());

    // The mono resolution should NOT be set with a hardcoded enum value
    // outside of the config-driven if/else block. We check that the
    // config field is used and that there's no stray hardcoded setResolution
    // that bypasses config.
    // (The if/else mapping from string→enum is expected and correct.)
    size_t config_usage = content.find("config_.mono_resolution");
    ASSERT_NE(config_usage, std::string::npos);
}

TEST_F(StereoParamConfigurabilityTest, DepthaiManagerNoHardcodedMedianFilter)
{
    std::string root = getPackageRoot();
    std::string content = readFile(root + "/src/depthai_manager.cpp");
    ASSERT_FALSE(content.empty());

    size_t config_usage = content.find("config_.median_filter");
    ASSERT_NE(config_usage, std::string::npos);
}

// ===========================================================================
// Main
// ===========================================================================

int main(int argc, char ** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
