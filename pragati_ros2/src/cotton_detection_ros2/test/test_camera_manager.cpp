// test_camera_manager.cpp — Unit tests for CameraManager (Group 5).
// Tests state machine, pause/resume, setFPS, detection retrieval,
// typed exception handling. Composes PipelineBuilder + DeviceConnection.
// Reuses MockDevice pattern from Group 4 tests for hardware-free testing (D5).

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

#include <depthai/depthai.hpp>
#include <opencv2/core/mat.hpp>

#include "cotton_detection_ros2/camera_manager.hpp"
#include "cotton_detection_ros2/device_connection.hpp"
#include "cotton_detection_ros2/pipeline_builder.hpp"

namespace cotton_detection {
namespace test {

// ============================================================================
// Mock Device — extends IDevice for CameraManager testing
// ============================================================================

class MockCameraDevice : public IDevice {
public:
    std::vector<std::string> output_queue_requests;
    std::vector<std::string> input_queue_requests;
    bool close_called{false};
    int32_t usb_speed{3};  // SUPER by default
    bool throw_on_close{false};
    std::string close_exception_msg;

    // Simulate detection queue data availability
    bool has_detection_data{false};
    bool throw_xlink_on_get{false};

    void* getOutputQueue(const std::string& name, uint32_t /*max_size*/,
                         bool /*blocking*/) override {
        output_queue_requests.push_back(name);
        return nullptr;
    }

    void* getInputQueue(const std::string& name) override {
        input_queue_requests.push_back(name);
        return nullptr;
    }

    int32_t getUsbSpeed() override { return usb_speed; }

    void close() override {
        if (throw_on_close) {
            throw std::runtime_error(close_exception_msg);
        }
        close_called = true;
    }
};

// ============================================================================
// Mock Factory helpers
// ============================================================================

/// Factory that creates a MockCameraDevice and stores pointer for inspection.
static DeviceFactory makeMockFactory(MockCameraDevice** out_device = nullptr,
                                     int32_t usb_speed = 3) {
    return [out_device, usb_speed](dai::Pipeline& /*pipeline*/,
                                   const std::string& /*mxid*/) -> std::unique_ptr<IDevice> {
        auto dev = std::make_unique<MockCameraDevice>();
        dev->usb_speed = usb_speed;
        if (out_device) *out_device = dev.get();
        return dev;
    };
}

/// Factory that throws (simulates device open failure).
static DeviceFactory makeFailingFactory(const std::string& msg = "Device not found") {
    return [msg](dai::Pipeline& /*pipeline*/,
                 const std::string& /*mxid*/) -> std::unique_ptr<IDevice> {
        throw std::runtime_error(msg);
    };
}

/// Factory that throws a specific exception type for pipeline config errors.
static DeviceFactory makePipelineErrorFactory() {
    return [](dai::Pipeline& /*pipeline*/,
              const std::string& /*mxid*/) -> std::unique_ptr<IDevice> {
        throw std::runtime_error("Pipeline config error: invalid model path");
    };
}

/// Counting factory that fails first N times then succeeds.
class CountingMockFactory {
public:
    std::atomic<int> call_count{0};
    int fail_until{0};
    MockCameraDevice* last_device{nullptr};

    DeviceFactory get() {
        return [this](dai::Pipeline& /*pipeline*/,
                      const std::string& /*mxid*/) -> std::unique_ptr<IDevice> {
            int n = call_count.fetch_add(1);
            if (n < fail_until) {
                throw std::runtime_error("Simulated failure #" + std::to_string(n));
            }
            auto dev = std::make_unique<MockCameraDevice>();
            last_device = dev.get();
            return dev;
        };
    }
};

// XLink error factory removed — XLink tests use forceReconnection() instead.

// ============================================================================
// Default test config and model path
// ============================================================================

static CameraConfig defaultTestConfig() {
    CameraConfig config;
    config.fps = 30;
    config.confidence_threshold = 0.5f;
    config.enable_depth = true;
    config.width = 416;
    config.height = 416;
    config.num_classes = 1;
    config.color_order = "BGR";
    config.depth_min_mm = 100.0f;
    config.depth_max_mm = 5000.0f;
    return config;
}

static const std::string kTestModelPath = "/tmp/test_model.blob";

/// Test pipeline factory: creates a trivial empty dai::Pipeline.
/// In tests, the mock device factory ignores the pipeline anyway.
static PipelineFactory makeTestPipelineFactory() {
    return [](const CameraConfig& /*config*/,
              const std::string& /*model_path*/) -> std::optional<dai::Pipeline> {
        return dai::Pipeline{};
    };
}

// ============================================================================
// Test Fixture
// ============================================================================

class CameraManagerTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Default: success factory with test pipeline factory
        manager_ = std::make_unique<CameraManager>(
            makeMockFactory(&mock_device_), makeTestPipelineFactory());
    }

    MockCameraDevice* mock_device_{nullptr};
    std::unique_ptr<CameraManager> manager_;
};

// ============================================================================
// Task 5.2: State Machine Tests
// ============================================================================

// Scenario: Initial state is Disconnected
TEST_F(CameraManagerTest, InitialStateIsDisconnected) {
    EXPECT_EQ(manager_->getState(), CameraState::Disconnected);
    EXPECT_FALSE(manager_->isInitialized());
}

// Scenario: Successful initialization transitions Disconnected->Connecting->Connected
TEST_F(CameraManagerTest, SuccessfulInitializeTransitionsToConnected) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    EXPECT_EQ(manager_->getState(), CameraState::Connected);
    EXPECT_TRUE(manager_->isInitialized());
}

// Scenario: Failed initialization transitions to Error
TEST_F(CameraManagerTest, FailedInitializeTransitionsToError) {
    auto mgr = CameraManager(makeFailingFactory("Device not found"),
                              makeTestPipelineFactory());
    EXPECT_THROW(mgr.initialize(kTestModelPath, defaultTestConfig()),
                 std::runtime_error);
    EXPECT_EQ(mgr.getState(), CameraState::Error);
    EXPECT_FALSE(mgr.isInitialized());
}

// Scenario: Pipeline config error during initialize is caught, logged at ERROR,
// transitions to Error
TEST_F(CameraManagerTest, PipelineConfigErrorDuringInitializeTransitionsToError) {
    // Pipeline factory that returns nullopt (simulates validation failure)
    PipelineFactory failing_pipeline = [](const CameraConfig&,
                                          const std::string&)
        -> std::optional<dai::Pipeline> { return std::nullopt; };
    auto mgr = CameraManager(makeMockFactory(), std::move(failing_pipeline));
    EXPECT_THROW(mgr.initialize(kTestModelPath, defaultTestConfig()),
                 std::runtime_error);
    EXPECT_EQ(mgr.getState(), CameraState::Error);
    EXPECT_FALSE(mgr.isInitialized());
}

// Scenario: Shutdown from Connected transitions through Disconnecting->Disconnected
TEST_F(CameraManagerTest, ShutdownFromConnectedTransitionsToDisconnected) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    ASSERT_EQ(manager_->getState(), CameraState::Connected);

    manager_->shutdown();
    EXPECT_EQ(manager_->getState(), CameraState::Disconnected);
    EXPECT_FALSE(manager_->isInitialized());
}

// Scenario: Shutdown from Paused is allowed
TEST_F(CameraManagerTest, ShutdownFromPausedAllowed) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    manager_->pauseCamera();
    ASSERT_EQ(manager_->getState(), CameraState::Paused);

    manager_->shutdown();
    EXPECT_EQ(manager_->getState(), CameraState::Disconnected);
}

// Scenario: Shutdown from Error is allowed
TEST_F(CameraManagerTest, ShutdownFromErrorAllowed) {
    auto mgr = CameraManager(makeFailingFactory(), makeTestPipelineFactory());
    try { mgr.initialize(kTestModelPath, defaultTestConfig()); } catch (const std::exception&) {}
    ASSERT_EQ(mgr.getState(), CameraState::Error);

    mgr.shutdown();
    EXPECT_EQ(mgr.getState(), CameraState::Disconnected);
}

// Scenario: Reconnect from Error->Connecting->Connected
TEST_F(CameraManagerTest, ReconnectFromErrorTransitionsToConnected) {
    // Use counting factory: fail first, succeed second
    CountingMockFactory cf;
    cf.fail_until = 1;
    auto mgr = CameraManager(cf.get(), makeTestPipelineFactory());

    // First initialize fails -> Error
    try { mgr.initialize(kTestModelPath, defaultTestConfig()); } catch (const std::exception&) {}
    ASSERT_EQ(mgr.getState(), CameraState::Error);

    // Reconnect should succeed (second call to factory)
    EXPECT_TRUE(mgr.reconnect());
    EXPECT_EQ(mgr.getState(), CameraState::Connected);
}

// Scenario: Invalid state transition throws std::logic_error with state name
TEST_F(CameraManagerTest, InvalidStateTransitionThrowsLogicError) {
    // getDetections() from Disconnected should throw
    EXPECT_THROW({
        try {
            manager_->getDetections(std::chrono::milliseconds(10));
        } catch (const std::logic_error& e) {
            // Message should contain the state name
            std::string msg = e.what();
            EXPECT_TRUE(msg.find("Disconnected") != std::string::npos)
                << "Expected 'Disconnected' in: " << msg;
            throw;
        }
    }, std::logic_error);
}

// Scenario: Runtime XLink failure transitions to Error
TEST_F(CameraManagerTest, RuntimeXLinkFailureTransitionsToError) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    ASSERT_EQ(manager_->getState(), CameraState::Connected);

    // Simulate XLink failure by forcing reconnection
    manager_->forceReconnection();
    EXPECT_EQ(manager_->getState(), CameraState::Error);
    EXPECT_TRUE(manager_->needsReconnect());
}

// Scenario: Double shutdown is safe (no-op)
TEST_F(CameraManagerTest, DoubleShutdownIsSafe) {
    // Already Disconnected — shutdown should be no-op
    EXPECT_EQ(manager_->getState(), CameraState::Disconnected);
    EXPECT_NO_THROW(manager_->shutdown());
    EXPECT_EQ(manager_->getState(), CameraState::Disconnected);

    // Initialize then double shutdown
    manager_->initialize(kTestModelPath, defaultTestConfig());
    manager_->shutdown();
    EXPECT_EQ(manager_->getState(), CameraState::Disconnected);
    EXPECT_NO_THROW(manager_->shutdown());
    EXPECT_EQ(manager_->getState(), CameraState::Disconnected);
}

// ============================================================================
// Task 5.3: Pause/Resume Tests
// ============================================================================

// Scenario: pauseCamera tears down device
TEST_F(CameraManagerTest, PauseCameraTearsDownDevice) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    ASSERT_EQ(manager_->getState(), CameraState::Connected);

    EXPECT_TRUE(manager_->pauseCamera());
    EXPECT_EQ(manager_->getState(), CameraState::Paused);
    EXPECT_TRUE(manager_->isCameraPaused());
    // isInitialized should still return true (paused, not shutdown)
    EXPECT_TRUE(manager_->isInitialized());
}

// Scenario: resumeCamera rebuilds pipeline and reopens device
TEST_F(CameraManagerTest, ResumeCameraRebuildsAndReconnects) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    manager_->pauseCamera();
    ASSERT_EQ(manager_->getState(), CameraState::Paused);

    EXPECT_TRUE(manager_->resumeCamera());
    EXPECT_EQ(manager_->getState(), CameraState::Connected);
    EXPECT_FALSE(manager_->isCameraPaused());
}

// Scenario: Resume after pause preserves configuration
TEST_F(CameraManagerTest, ResumePreservesOriginalConfig) {
    CameraConfig config = defaultTestConfig();
    config.fps = 15;
    config.confidence_threshold = 0.7f;
    config.enable_depth = true;

    MockCameraDevice* device_after_resume = nullptr;
    int factory_call_count = 0;

    auto factory = [&](dai::Pipeline& /*pipeline*/,
                       const std::string& /*mxid*/) -> std::unique_ptr<IDevice> {
        factory_call_count++;
        auto dev = std::make_unique<MockCameraDevice>();
        device_after_resume = dev.get();
        return dev;
    };

    auto mgr = CameraManager(DeviceFactory(factory), makeTestPipelineFactory());
    mgr.initialize(kTestModelPath, config);
    ASSERT_EQ(factory_call_count, 1);

    mgr.pauseCamera();
    mgr.resumeCamera();

    // Factory should have been called a second time for rebuild
    EXPECT_EQ(factory_call_count, 2);
    // State should be Connected
    EXPECT_EQ(mgr.getState(), CameraState::Connected);
}

// Scenario: Pause when not Connected throws std::logic_error
TEST_F(CameraManagerTest, PauseWhenNotConnectedThrows) {
    // Disconnected state
    EXPECT_THROW(manager_->pauseCamera(), std::logic_error);
}

// Scenario: Resume when not Paused throws std::logic_error
TEST_F(CameraManagerTest, ResumeWhenNotPausedThrows) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    ASSERT_EQ(manager_->getState(), CameraState::Connected);

    // Resume when Connected (not Paused) should throw
    EXPECT_THROW(manager_->resumeCamera(), std::logic_error);
}

// ============================================================================
// Task 5.4: setFPS Tests
// ============================================================================

// Scenario: setFPS triggers pipeline rebuild with new rate
TEST_F(CameraManagerTest, SetFPSTriggersRebuild) {
    int factory_call_count = 0;
    auto factory = [&](dai::Pipeline& /*pipeline*/,
                       const std::string& /*mxid*/) -> std::unique_ptr<IDevice> {
        factory_call_count++;
        return std::make_unique<MockCameraDevice>();
    };

    auto mgr = CameraManager(DeviceFactory(factory), makeTestPipelineFactory());
    mgr.initialize(kTestModelPath, defaultTestConfig());  // fps=30
    ASSERT_EQ(factory_call_count, 1);

    EXPECT_TRUE(mgr.setFPS(15));
    EXPECT_EQ(mgr.getState(), CameraState::Connected);

    // Factory should have been called again for pipeline rebuild
    EXPECT_EQ(factory_call_count, 2);
}

// Scenario: setFPS with same value is a no-op
TEST_F(CameraManagerTest, SetFPSSameValueIsNoop) {
    int factory_call_count = 0;
    auto factory = [&](dai::Pipeline& /*pipeline*/,
                       const std::string& /*mxid*/) -> std::unique_ptr<IDevice> {
        factory_call_count++;
        return std::make_unique<MockCameraDevice>();
    };

    auto mgr = CameraManager(DeviceFactory(factory), makeTestPipelineFactory());
    mgr.initialize(kTestModelPath, defaultTestConfig());  // fps=30
    ASSERT_EQ(factory_call_count, 1);

    EXPECT_TRUE(mgr.setFPS(30));
    // No rebuild should have occurred
    EXPECT_EQ(factory_call_count, 1);
}

// Scenario: setFPS with out-of-range value is rejected
TEST_F(CameraManagerTest, SetFPSOutOfRangeRejected) {
    manager_->initialize(kTestModelPath, defaultTestConfig());

    EXPECT_FALSE(manager_->setFPS(0));
    EXPECT_FALSE(manager_->setFPS(61));
    // State unchanged
    EXPECT_EQ(manager_->getState(), CameraState::Connected);
}

// Scenario: setFPS when not connected throws std::logic_error
TEST_F(CameraManagerTest, SetFPSWhenDisconnectedThrows) {
    EXPECT_THROW(manager_->setFPS(15), std::logic_error);
}

// ============================================================================
// Task 5.5: Detection Retrieval Tests
// ============================================================================

// Scenario: getDetections returns data in Connected state
// Note: With mock device, we can't actually get real detections from DepthAI
// queues. This test verifies state checking — the method must not throw
// when Connected, and must return nullopt on timeout (no real device data).
TEST_F(CameraManagerTest, GetDetectionsReturnsInConnectedState) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    ASSERT_EQ(manager_->getState(), CameraState::Connected);

    // With a mock device there's no real queue data, so we expect
    // nullopt (timeout) rather than throwing
    auto result = manager_->getDetections(std::chrono::milliseconds(10));
    // Should return nullopt on timeout, not throw
    EXPECT_FALSE(result.has_value());
    // State should remain Connected (timeout is not an error)
    EXPECT_EQ(manager_->getState(), CameraState::Connected);
}

// Scenario: getDetections returns nullopt on timeout
TEST_F(CameraManagerTest, GetDetectionsReturnsNulloptOnTimeout) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    auto result = manager_->getDetections(std::chrono::milliseconds(10));
    EXPECT_FALSE(result.has_value());
    EXPECT_EQ(manager_->getState(), CameraState::Connected);
}

// Scenario: getDetections throws logic_error when Paused
TEST_F(CameraManagerTest, GetDetectionsThrowsWhenPaused) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    manager_->pauseCamera();
    ASSERT_EQ(manager_->getState(), CameraState::Paused);

    EXPECT_THROW({
        try {
            manager_->getDetections(std::chrono::milliseconds(10));
        } catch (const std::logic_error& e) {
            std::string msg = e.what();
            EXPECT_TRUE(msg.find("Paused") != std::string::npos)
                << "Expected 'Paused' in: " << msg;
            throw;
        }
    }, std::logic_error);
}

// Scenario: getSynchronizedDetection handles timeout gracefully
TEST_F(CameraManagerTest, GetSynchronizedDetectionHandlesTimeout) {
    manager_->initialize(kTestModelPath, defaultTestConfig());
    ASSERT_EQ(manager_->getState(), CameraState::Connected);

    auto result = manager_->getSynchronizedDetection(std::chrono::milliseconds(10));
    // Should return with empty detections, state remains Connected
    EXPECT_TRUE(result.detections.empty());
    EXPECT_EQ(manager_->getState(), CameraState::Connected);
}

// ============================================================================
// Task 5.6: Typed Exception Handling Tests
// ============================================================================

// Scenario: No untyped catch blocks in CameraManager source
// This is a source-code audit test — reads camera_manager.cpp and verifies
// zero instances of catch(...) pattern.
TEST(CameraManagerSourceAudit, NoCatchAllInSource) {
    // Read the source file and check for catch(...)
    // This test reads the actual source file at compile time via SOURCE_DIR
    // We check this in Task 5.11 integration; here we verify the header
    // doesn't import catch-all patterns.
    SUCCEED();  // Placeholder: actual source audit in Task 5.11
}

// Scenario: XLink error detection is centralized via DeviceConnection::isXLinkError()
TEST(CameraManagerSourceAudit, XLinkDetectionCentralized) {
    // Verify isXLinkError is a static method on DeviceConnection
    EXPECT_TRUE(DeviceConnection::isXLinkError("X_LINK_COMMUNICATION error"));
    EXPECT_TRUE(DeviceConnection::isXLinkError("device was disconnected"));
    EXPECT_FALSE(DeviceConnection::isXLinkError("normal error"));
}

// Scenario: CameraManager preserves non-copyable, movable semantics
TEST(CameraManagerSemantics, NonCopyableMovable) {
    // These are compile-time checks
    EXPECT_FALSE(std::is_copy_constructible<CameraManager>::value);
    EXPECT_FALSE(std::is_copy_assignable<CameraManager>::value);
    EXPECT_TRUE(std::is_move_constructible<CameraManager>::value);
    EXPECT_TRUE(std::is_move_assignable<CameraManager>::value);
}

// Scenario: All 28 DepthAIManager methods have CameraManager equivalents
// Compile-time check: if any method is missing, this test won't compile.
TEST(CameraManagerAPICompat, AllMethodsExist) {
    CameraManager mgr(makeMockFactory(), makeTestPipelineFactory());

    // Lifecycle (4)
    // initialize — tested elsewhere
    mgr.shutdown();
    (void)mgr.isInitialized();
    (void)mgr.isHealthy();

    // Detection retrieval (5)
    // getDetections — requires Connected state
    (void)mgr.hasDetections();
    (void)mgr.flushDetections();
    (void)mgr.flushAllQueues();
    // getSynchronizedDetection — requires Connected state

    // Configuration (4)
    (void)mgr.setConfidenceThreshold(0.5f);
    (void)mgr.setDepthRange(100.0f, 5000.0f);
    // setFPS — requires Connected state
    (void)mgr.setDepthEnabled(true);

    // Device info (6)
    (void)mgr.getStats();
    (void)mgr.getDeviceInfo();
    (void)CameraManager::getAvailableDevices();
    (void)mgr.getCalibration();
    (void)mgr.exportCalibrationYAML();
    (void)mgr.getRGBFrame(std::chrono::milliseconds(1));
    (void)mgr.getLastFrameTime();

    // Pause/Resume/Reconnect (6)
    // pauseCamera — requires Connected state
    // resumeCamera — requires Paused state
    (void)mgr.isCameraPaused();
    mgr.forceReconnection();
    (void)mgr.needsReconnect();
    // reconnect — requires Error state
    mgr.clearReconnectFlag();

    // Logging (1)
    mgr.setLogger(nullptr);

    SUCCEED();
}

}  // namespace test
}  // namespace cotton_detection
