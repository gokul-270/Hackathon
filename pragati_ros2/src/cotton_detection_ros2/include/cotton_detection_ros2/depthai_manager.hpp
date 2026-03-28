#pragma once

// Sub-headers: extracted types for reduced compilation dependencies
#include "cotton_detection_ros2/logging_types.hpp"
#include "cotton_detection_ros2/camera_config.hpp"
#include "cotton_detection_ros2/detection_types.hpp"
#include "cotton_detection_ros2/camera_diagnostics.hpp"

// Standard library includes needed by DepthAIManager class
#include <memory>
#include <vector>
#include <string>
#include <mutex>
#include <optional>
#include <chrono>

// Note: DepthAI types (dai::Device, dai::Pipeline, etc.) are fully encapsulated
// in the Impl class using PIMPL pattern, so no forward declarations needed here

// Forward declaration for OpenCV (also in detection_types.hpp, but needed here for getRGBFrame)
namespace cv {
    class Mat;
}

namespace cotton_detection {

/**
 * @brief Main DepthAI manager class
 *
 * This class encapsulates all DepthAI API interactions for cotton detection.
 * It uses the PImpl (Pointer to Implementation) pattern to hide DepthAI
 * implementation details and reduce compilation dependencies.
 *
 * Thread-safe: All public methods can be called from multiple threads.
 */
class DepthAIManager {
public:
    /**
     * @brief Constructor
     */
    DepthAIManager();

    /**
     * @brief Destructor
     */
    ~DepthAIManager();

    // Non-copyable
    DepthAIManager(const DepthAIManager&) = delete;
    DepthAIManager& operator=(const DepthAIManager&) = delete;

    // Movable
    DepthAIManager(DepthAIManager&&) noexcept;
    DepthAIManager& operator=(DepthAIManager&&) noexcept;

    /**
     * @brief Initialize the DepthAI pipeline
     *
     * @param model_path Path to YOLO .blob model file
     * @param config Camera configuration
     * @return true if initialization successful, false otherwise
     *
     * @note This method must be called before any other operations.
     * @note Throws std::runtime_error on critical failures.
     */
    bool initialize(const std::string& model_path, const CameraConfig& config);

    /**
     * @brief Shutdown the DepthAI pipeline
     *
     * Safely closes all connections and releases resources.
     * Can be called multiple times safely.
     */
    void shutdown();

    /**
     * @brief Check if manager is initialized
     *
     * @return true if initialized and ready, false otherwise
     */
    bool isInitialized() const;

    /**
     * @brief Check if camera is healthy
     *
     * @return true if camera is responding, false otherwise
     */
    bool isHealthy() const;

    /**
     * @brief Get detections (blocking with timeout)
     *
     * @param timeout Maximum time to wait for detections
     * @return Vector of detections if available, std::nullopt if timeout or error
     *
     * @note This method blocks until detections are available or timeout occurs.
     */
    std::optional<std::vector<CottonDetection>>
        getDetections(std::chrono::milliseconds timeout = std::chrono::milliseconds(1000));

    /**
     * @brief Check if detections are available (non-blocking)
     *
     * @return true if detections are ready to be retrieved
     */
    bool hasDetections() const;

    /**
     * @brief Flush all pending detections from the queue (non-blocking)
     *
     * Efficiently discards all stale detections without CPU-intensive polling.
     * Use this before getDetections() to ensure you get a fresh frame.
     *
     * @return Number of frames flushed
     *
     * @note This only flushes the detection queue. For synchronized detection+RGB,
     *       use flushAllQueues() instead.
     */
    int flushDetections();

    /**
     * @brief Flush ALL queues (detection, RGB, depth) for synchronized fresh data
     *
     * CRITICAL: Use this method instead of flushDetections() when you need both
     * detection results AND RGB images. This ensures both come from the same frame.
     *
     * Pipeline synchronization:
     * - SpatialNN outputs detection AND passthrough RGB from same input frame
     * - Both outputs have same sequence number
     * - Flushing both queues ensures next data from each is from same frame
     *
     * @return Total number of frames flushed across all queues
     */
    int flushAllQueues();

    /**
     * @brief Set confidence threshold
     *
     * @param threshold New confidence threshold [0.0, 1.0]
    * @return true if accepted/applied, false if out of range or reinitialization failed
     */
    bool setConfidenceThreshold(float threshold);

    /**
     * @brief Set depth range
     *
     * @param min_mm Minimum depth in millimeters
     * @param max_mm Maximum depth in millimeters
    * @return true if accepted/applied, false if invalid range or reinitialization failed
     */
    bool setDepthRange(float min_mm, float max_mm);

    /**
     * @brief Set frames per second
     *
     * @param fps Target frames per second [1, 60]
     * @return true if successful, false if out of range or not initialized
     */
    bool setFPS(int fps);

    /**
     * @brief Enable or disable depth processing at runtime
     *
     * @param enable True to enable depth-based spatial calculations
    * @return true if request accepted/applied, false if reinitialization failed
     */
    bool setDepthEnabled(bool enable);

    /**
     * @brief Get camera statistics
     *
     * @return Current camera statistics
     */
    CameraStats getStats() const;

    /**
     * @brief Get zero-spatial rejected detections from last getDetections() call
     *
     * Returns bounding box and confidence data for detections rejected because
     * stereo depth returned (0,0,0).  Used for diagnostic image annotation.
     * The vector is cleared at the start of each getDetections() or
     * getSynchronizedDetection() call.
     *
     * @return Vector of ZeroSpatialInfo with normalized bbox coordinates
     */
    std::vector<ZeroSpatialInfo> getLastZeroSpatialRejections() const;

    /**
     * @brief Get device information
     *
     * @return Device info string (MxID, name, etc.)
     */
    std::string getDeviceInfo() const;

    /**
     * @brief Get list of available devices
     *
     * @return Vector of device MxIDs
     */
    static std::vector<std::string> getAvailableDevices();

    /**
     * @brief Get camera calibration data
     *
     * @return Camera calibration if available, std::nullopt otherwise
     */
    std::optional<CameraCalibration> getCalibration() const;

    /**
     * @brief Export calibration to YAML string
     *
     * @return YAML string with calibration data, empty if not available
     */
    std::string exportCalibrationYAML() const;

    /**
     * @brief Get the latest RGB frame (blocking with timeout)
     *
     * @param timeout Maximum time to wait for frame
     * @return cv::Mat containing BGR image, empty if timeout or error
     *
     * @note Returns empty Mat if not initialized or queue unavailable
     * @note For synchronized detection+RGB, use getSynchronizedDetection() instead
     */
    cv::Mat getRGBFrame(std::chrono::milliseconds timeout = std::chrono::milliseconds(1000));

    /**
     * @brief Get synchronized detection and RGB frame (RECOMMENDED)
     *
     * This method ensures that detection results and RGB frame are from the SAME
     * camera frame by matching sequence numbers. This is critical for:
     * - Accurate arm positioning (detection matches actual cotton position)
     * - Correct image saving (saved image shows what was detected)
     *
     * Algorithm:
     * 1. Flush all queues (detection + RGB + depth)
     * 2. Get fresh detection with sequence number N
     * 3. Search RGB queue for frame with matching sequence number N
     * 4. If mismatch, log warning and retry (auto-sync)
     *
     * @param timeout Maximum time to wait for synchronized data
     * @return SynchronizedDetectionResult with matched detection and RGB
     *
     * @note This is slower than separate getDetections()+getRGBFrame() but guarantees sync
     * @note Check result.is_synchronized to verify sequence numbers matched
     */
    SynchronizedDetectionResult getSynchronizedDetection(
        std::chrono::milliseconds timeout = std::chrono::milliseconds(200));

    /**
     * @brief Force reconnection (for external timeout detection)
     *
     * Use this when consecutive frame timeouts indicate degraded camera state
     * even without X_LINK_ERROR exception. This sets the needs_reconnect flag
     * which will trigger reconnection on the next detection request.
     *
     * Typical usage:
     * - Track consecutive getRGBFrame() or getDetections() timeouts
     * - After 3+ consecutive timeouts, call forceReconnection()
     * - Next getDetections() call will trigger reconnection sequence
     */
    void forceReconnection();

    /**
     * @brief Get last successful frame timestamp
     *
     * @return Timestamp of last successfully retrieved frame (detection or RGB)
     *
     * @note Used by isHealthy() to check frame delivery
     */
    std::chrono::steady_clock::time_point getLastFrameTime() const;

    /**
     * @brief Pause all cameras (Color + MonoLeft + MonoRight)
     *
     * Stops streaming from all cameras using setStopStreaming() control command.
     * This reduces thermal load while keeping the pipeline active (~10ms resume latency).
     * Temperature monitoring remains functional while paused.
     *
     * @return true if pause command sent successfully, false if not initialized or error
     *
     * @note Use during cotton picking cycle when camera is not needed (arm movement, etc.)
     * @note Expected thermal improvement: ~96°C active → ~75-80°C paused (needs verification)
     */
    bool pauseCamera();

    /**
     * @brief Resume all cameras (Color + MonoLeft + MonoRight)
     *
     * Restarts streaming from all cameras using setStartStreaming() control command.
     * Resume latency is approximately 10ms (vs 1-2 sec for full pipeline restart).
     *
     * @return true if resume command sent successfully, false if not initialized or error
     *
     * @note Call before detection is needed for next cotton boll
     */
    bool resumeCamera();

    /**
     * @brief Check if cameras are currently paused
     *
     * @return true if cameras are paused, false if streaming or not initialized
     */
    bool isCameraPaused() const;

    /**
     * @brief Set logger callback for ROS2 integration
     *
     * If set, all log messages will be routed through this callback.
     * If not set, messages go to stdout/stderr.
     */
    void setLogger(LoggerCallback logger);

    /**
     * @brief Check if reconnection is needed due to X_LINK_ERROR
     *
     * X_LINK_ERROR occurs when USB communication fails (cable, power, driver issues).
     * When detected, the device needs full reinitialization.
     *
     * @return true if reconnection is needed, false otherwise
     */
    bool needsReconnect() const;

    /**
     * @brief Attempt to reconnect after X_LINK_ERROR
     *
     * Performs full shutdown and reinitialization sequence:
     * 1. Shutdown existing connection
     * 2. Wait for USB re-enumeration (2 seconds)
     * 3. Reinitialize with same configuration
     *
     * @return true if reconnection successful, false otherwise
     *
     * @note Takes approximately 4-5 seconds total
     * @note Call this when needsReconnect() returns true
     */
    bool reconnect();

    /**
     * @brief Clear the reconnection flag without reconnecting
     *
     * Use this if you want to handle reconnection externally or skip it.
     */
    void clearReconnectFlag();

private:
    // Forward declaration of implementation class
    class Impl;

    // PImpl idiom: hide implementation details
    std::unique_ptr<Impl> pImpl_;
};

}  // namespace cotton_detection
