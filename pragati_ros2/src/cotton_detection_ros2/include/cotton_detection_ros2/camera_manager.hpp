#pragma once

// DEPRECATED: CameraManager is not used in the active detection pipeline.
// The production camera backend is DepthAIManager (depthai_manager.hpp).
// CameraManager is retained for future decomposition work. See design.md
// in the restore-depthai-manager change for context.

#include <chrono>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include "cotton_detection_ros2/camera_config.hpp"
#include "cotton_detection_ros2/camera_diagnostics.hpp"
#include "cotton_detection_ros2/detection_types.hpp"
#include "cotton_detection_ros2/device_connection.hpp"
#include "cotton_detection_ros2/logging_types.hpp"
#include "cotton_detection_ros2/pipeline_builder.hpp"

// Forward declaration for OpenCV Mat type
namespace cv {
class Mat;
}  // namespace cv

// Forward declaration for DepthAI Pipeline
namespace dai {
class Pipeline;
}  // namespace dai

namespace cotton_detection {

/// CameraManager state machine states (D6: enum + switch).
enum class CameraState {
    Disconnected,
    Connecting,
    Connected,
    Paused,
    Disconnecting,
    Error
};

/// Pipeline factory type: builds a dai::Pipeline from config and model path.
/// Allows injection of a test-friendly pipeline builder that skips real DepthAI
/// node construction. Returns nullopt on validation failure.
using PipelineFactory = std::function<std::optional<dai::Pipeline>(
    const CameraConfig& config, const std::string& model_path)>;

/// Compose PipelineBuilder + DeviceConnection into a unified camera manager.
///
/// Replaces DepthAIManager with a clean state machine (6 states), typed
/// exception handling (D8), and per-component locking (D7). Owns its own
/// std::mutex for state transitions. Non-copyable, movable.
///
/// ThermalGuard and DiagnosticsCollector are NOT owned by CameraManager —
/// they are owned by CottonDetectionNode (per spec).
class CameraManager {
public:
    /// Construct with default (real DepthAI) device factory.
    CameraManager();

    /// Construct with custom device factory for testing.
    /// @param factory Device factory for creating IDevice instances.
    /// @param pipeline_factory Optional pipeline factory. If null, uses
    ///        PipelineBuilder (production). Provide a custom factory in tests
    ///        to avoid requiring real DepthAI blob files.
    /// @param logger Optional logger callback.
    explicit CameraManager(DeviceFactory factory,
                           PipelineFactory pipeline_factory = nullptr,
                           LoggerCallback logger = nullptr);

    /// Destructor calls shutdown().
    ~CameraManager();

    // Non-copyable
    CameraManager(const CameraManager&) = delete;
    CameraManager& operator=(const CameraManager&) = delete;

    // Movable
    CameraManager(CameraManager&&) noexcept;
    CameraManager& operator=(CameraManager&&) noexcept;

    // =========================================================================
    // Lifecycle
    // =========================================================================

    /// Initialize the camera pipeline.
    /// @throws std::runtime_error on device open failure.
    /// @throws std::logic_error if not in Disconnected state.
    void initialize(const std::string& model_path, const CameraConfig& config);

    /// Shutdown the camera pipeline. Safe to call multiple times.
    void shutdown();

    /// Check if initialized (Connected or Paused).
    bool isInitialized() const;

    /// Check if camera is healthy (Connected and recent frame).
    bool isHealthy() const;

    /// Get current state machine state.
    CameraState getState() const;

    // =========================================================================
    // Detection retrieval
    // =========================================================================

    /// Get detections (blocking with timeout).
    /// @throws std::logic_error if not Connected.
    std::optional<std::vector<CottonDetection>> getDetections(
        std::chrono::milliseconds timeout = std::chrono::milliseconds(1000));

    /// Check if detections are available (non-blocking).
    bool hasDetections() const;

    /// Flush pending detections.
    int flushDetections();

    /// Flush ALL queues (detection, RGB, depth).
    int flushAllQueues();

    /// Get synchronized detection and RGB frame.
    /// @throws std::logic_error if not Connected.
    SynchronizedDetectionResult getSynchronizedDetection(
        std::chrono::milliseconds timeout = std::chrono::milliseconds(200));

    // =========================================================================
    // Configuration
    // =========================================================================

    /// Set confidence threshold.
    bool setConfidenceThreshold(float threshold);

    /// Set depth range.
    bool setDepthRange(float min_mm, float max_mm);

    /// Set FPS — triggers pipeline rebuild if value changed.
    /// @throws std::logic_error if not Connected.
    bool setFPS(int fps);

    /// Enable or disable depth processing.
    bool setDepthEnabled(bool enable);

    // =========================================================================
    // Device info and calibration
    // =========================================================================

    /// Get camera statistics.
    CameraStats getStats() const;

    /// Get device information string.
    std::string getDeviceInfo() const;

    /// Get list of available devices.
    static std::vector<std::string> getAvailableDevices();

    /// Get camera calibration data.
    std::optional<CameraCalibration> getCalibration() const;

    /// Export calibration to YAML string.
    std::string exportCalibrationYAML() const;

    /// Get the latest RGB frame.
    cv::Mat getRGBFrame(
        std::chrono::milliseconds timeout = std::chrono::milliseconds(1000));

    /// Get last successful frame timestamp.
    std::chrono::steady_clock::time_point getLastFrameTime() const;

    // =========================================================================
    // Pause / Resume / Reconnect
    // =========================================================================

    /// Pause camera — tears down pipeline (real pause, not flag).
    /// @throws std::logic_error if not Connected.
    bool pauseCamera();

    /// Resume camera — rebuilds pipeline with stored config.
    /// @throws std::logic_error if not Paused.
    bool resumeCamera();

    /// Check if camera is paused.
    bool isCameraPaused() const;

    /// Force reconnection (sets needs_reconnect flag).
    void forceReconnection();

    /// Check if reconnection is needed.
    bool needsReconnect() const;

    /// Attempt reconnection after error.
    /// @throws std::logic_error if not in Error state.
    bool reconnect();

    /// Clear the reconnection flag.
    void clearReconnectFlag();

    /// Check if camera is in error state (teardown/resume failure).
    bool isCameraInError() const;

    /// Clear camera error flag (e.g., after successful reconnect).
    void clearCameraError();

    // =========================================================================
    // Logging
    // =========================================================================

    /// Set logger callback for ROS2 integration.
    void setLogger(LoggerCallback logger);

private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace cotton_detection
