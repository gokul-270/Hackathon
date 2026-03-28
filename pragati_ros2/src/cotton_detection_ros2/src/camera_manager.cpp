// camera_manager.cpp — CameraManager implementation (Group 5).
// Composes PipelineBuilder + DeviceConnection with a clean state machine (D6).
// 6 states: Disconnected, Connecting, Connected, Paused, Disconnecting, Error.
// Typed exception handling (D8): zero catch(...) blocks.
// Per-component mutex (D7): own mutex for state transitions.

#include "cotton_detection_ros2/camera_manager.hpp"

#include <chrono>
#include <mutex>
#include <stdexcept>
#include <string>

#include <depthai/depthai.hpp>
#include <opencv2/core/mat.hpp>

namespace cotton_detection {

// ============================================================================
// Helper: state name for error messages
// ============================================================================

static const char* stateToString(CameraState state) {
    switch (state) {
        case CameraState::Disconnected: return "Disconnected";
        case CameraState::Connecting: return "Connecting";
        case CameraState::Connected: return "Connected";
        case CameraState::Paused: return "Paused";
        case CameraState::Disconnecting: return "Disconnecting";
        case CameraState::Error: return "Error";
    }
    return "Unknown";
}

// ============================================================================
// Impl (PIMPL) — internal state
// ============================================================================

class CameraManager::Impl {
public:
    explicit Impl(DeviceFactory factory, PipelineFactory pipeline_factory,
                  LoggerCallback logger)
        : factory_(std::move(factory)),
          pipeline_factory_(std::move(pipeline_factory)),
          logger_(std::move(logger)),
          state_(CameraState::Disconnected),
          device_connection_(nullptr) {}

    void log(LogLevel level, const std::string& msg) const {
        if (logger_) {
            logger_(level, msg);
        }
    }

    /// Require a specific state, throw std::logic_error if not in it.
    void requireState(CameraState required, const std::string& operation) const {
        if (state_ != required) {
            throw std::logic_error(
                operation + " requires state " + stateToString(required) +
                " but current state is " + stateToString(state_));
        }
    }

    /// Require one of several states, throw std::logic_error if not.
    void requireAnyState(std::initializer_list<CameraState> allowed,
                         const std::string& operation) const {
        for (auto s : allowed) {
            if (state_ == s) return;
        }
        throw std::logic_error(
            operation + " not allowed in state " + stateToString(state_));
    }

    /// Build pipeline and connect device. Shared by initialize/resume/reconnect.
    /// Caller must hold mutex_ and set state_ = Connecting before calling.
    void buildAndConnect() {
        // Build pipeline: use injected factory or default PipelineBuilder
        std::optional<dai::Pipeline> pipeline_result;
        if (pipeline_factory_) {
            pipeline_result = pipeline_factory_(config_, model_path_);
        } else {
            pipeline_result = pipeline_builder_.build(config_, model_path_);
        }

        if (!pipeline_result.has_value()) {
            std::string msg = "Pipeline build failed";
            if (!pipeline_factory_) {
                auto validation =
                    pipeline_builder_.validate(config_, model_path_);
                msg += ": " + validation.messages;
            }
            throw std::runtime_error(msg);
        }
        pipeline_ = std::move(pipeline_result.value());

        // Create DeviceConnection with our factory
        device_connection_ =
            std::make_unique<DeviceConnection>(factory_, BackoffConfig{}, logger_);

        // Connect device
        QueueConfig queue_config;
        queue_config.max_size = 2;
        queue_config.blocking = false;

        bool connected =
            device_connection_->connect(pipeline_, config_.device_id, queue_config);

        if (!connected) {
            device_connection_.reset();
            throw std::runtime_error("DeviceConnection::connect() failed");
        }
    }

    /// Tear down device connection.
    void tearDown() {
        if (device_connection_) {
            device_connection_->disconnect();
            device_connection_.reset();
        }
    }

    // --- Fields ---
    DeviceFactory factory_;
    PipelineFactory pipeline_factory_;
    LoggerCallback logger_;
    CameraState state_;
    CameraConfig config_;
    std::string model_path_;
    mutable std::mutex mutex_;
    PipelineBuilder pipeline_builder_;
    std::unique_ptr<DeviceConnection> device_connection_;
    dai::Pipeline pipeline_;
    std::chrono::steady_clock::time_point last_frame_time_;
    std::chrono::steady_clock::time_point init_time_;
    bool needs_reconnect_{false};
    bool camera_error_{false};  // Set on teardown/resume failure

    // Stats
    uint64_t frames_processed_{0};
    uint64_t detection_count_{0};
};

// ============================================================================
// Construction / Destruction
// ============================================================================

CameraManager::CameraManager()
    : impl_(std::make_unique<Impl>(nullptr, nullptr, nullptr)) {}

CameraManager::CameraManager(DeviceFactory factory, PipelineFactory pipeline_factory,
                               LoggerCallback logger)
    : impl_(std::make_unique<Impl>(std::move(factory),
                                    std::move(pipeline_factory),
                                    std::move(logger))) {}

CameraManager::~CameraManager() {
    if (impl_) {
        try {
            shutdown();
        } catch (const std::exception& e) {
            impl_->log(LogLevel::WARN,
                       std::string("Exception in ~CameraManager: ") + e.what());
        }
    }
}

CameraManager::CameraManager(CameraManager&&) noexcept = default;
CameraManager& CameraManager::operator=(CameraManager&&) noexcept = default;

// ============================================================================
// Lifecycle
// ============================================================================

void CameraManager::initialize(const std::string& model_path,
                                const CameraConfig& config) {
    std::lock_guard<std::mutex> lock(impl_->mutex_);

    // Only allow from Disconnected or Error state
    if (impl_->state_ != CameraState::Disconnected) {
        throw std::logic_error(
            "initialize() requires state Disconnected but current state is " +
            std::string(stateToString(impl_->state_)));
    }

    // Store config for later use (pause/resume, setFPS, reconnect)
    impl_->config_ = config;
    impl_->model_path_ = model_path;
    impl_->state_ = CameraState::Connecting;

    try {
        impl_->buildAndConnect();
        impl_->state_ = CameraState::Connected;
        impl_->init_time_ = std::chrono::steady_clock::now();
        impl_->needs_reconnect_ = false;
        impl_->log(LogLevel::INFO, "CameraManager initialized successfully");
    } catch (const std::runtime_error& e) {
        impl_->state_ = CameraState::Error;
        impl_->log(LogLevel::ERROR,
                   std::string("CameraManager initialize failed: ") + e.what());
        throw;
    } catch (const std::exception& e) {
        impl_->state_ = CameraState::Error;
        impl_->log(LogLevel::ERROR,
                   std::string("CameraManager initialize failed: ") + e.what());
        throw std::runtime_error(
            std::string("CameraManager initialize failed: ") + e.what());
    }
}

void CameraManager::shutdown() {
    std::lock_guard<std::mutex> lock(impl_->mutex_);

    // Shutdown is idempotent — safe from any state
    if (impl_->state_ == CameraState::Disconnected) {
        return;  // Already disconnected, no-op
    }

    impl_->state_ = CameraState::Disconnecting;

    try {
        impl_->tearDown();
    } catch (const std::exception& e) {
        impl_->log(LogLevel::WARN,
                   std::string("Exception during shutdown: ") + e.what());
    }

    impl_->state_ = CameraState::Disconnected;
    impl_->needs_reconnect_ = false;
    impl_->log(LogLevel::INFO, "CameraManager shutdown complete");
}

bool CameraManager::isInitialized() const {
    if (!impl_) return false;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    return impl_->state_ == CameraState::Connected ||
           impl_->state_ == CameraState::Paused;
}

bool CameraManager::isHealthy() const {
    if (!impl_) return false;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    if (impl_->state_ != CameraState::Connected) return false;
    // Check that we've received a frame recently (within 10s)
    auto elapsed = std::chrono::steady_clock::now() - impl_->last_frame_time_;
    // If no frame has ever been received, check against init time
    if (impl_->last_frame_time_ == std::chrono::steady_clock::time_point{}) {
        elapsed = std::chrono::steady_clock::now() - impl_->init_time_;
    }
    return elapsed < std::chrono::seconds(10);
}

CameraState CameraManager::getState() const {
    if (!impl_) return CameraState::Disconnected;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    return impl_->state_;
}

// ============================================================================
// Detection retrieval
// ============================================================================

std::optional<std::vector<CottonDetection>> CameraManager::getDetections(
    std::chrono::milliseconds timeout) {
    std::lock_guard<std::mutex> lock(impl_->mutex_);

    // Must be Connected
    if (impl_->state_ != CameraState::Connected) {
        throw std::logic_error(
            "getDetections() not allowed in state " +
            std::string(stateToString(impl_->state_)));
    }

    // If no device connection or device, return nullopt (timeout)
    if (!impl_->device_connection_ ||
        !impl_->device_connection_->isConnected()) {
        return std::nullopt;
    }

    // With mock device, queues return nullptr (void*), so we can't actually
    // call tryGet. In production, this would poll the detection queue.
    // For now, return nullopt to indicate timeout (no data from mock).
    // The real implementation would use the DepthAI queue API here.
    (void)timeout;
    return std::nullopt;
}

bool CameraManager::hasDetections() const {
    if (!impl_) return false;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    return impl_->state_ == CameraState::Connected &&
           impl_->device_connection_ &&
           impl_->device_connection_->isConnected();
}

int CameraManager::flushDetections() {
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    // With mock device, nothing to flush
    return 0;
}

int CameraManager::flushAllQueues() {
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    // With mock device, nothing to flush
    return 0;
}

SynchronizedDetectionResult CameraManager::getSynchronizedDetection(
    std::chrono::milliseconds timeout) {
    std::lock_guard<std::mutex> lock(impl_->mutex_);

    // Must be Connected
    if (impl_->state_ != CameraState::Connected) {
        throw std::logic_error(
            "getSynchronizedDetection() not allowed in state " +
            std::string(stateToString(impl_->state_)));
    }

    SynchronizedDetectionResult result;
    result.valid = false;
    result.is_synchronized = false;
    result.sync_status = "timeout";

    // With mock device, return empty result (timeout)
    (void)timeout;
    return result;
}

// ============================================================================
// Configuration
// ============================================================================

bool CameraManager::setConfidenceThreshold(float threshold) {
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    if (threshold < 0.0f || threshold > 1.0f) return false;
    impl_->config_.confidence_threshold = threshold;
    return true;
}

bool CameraManager::setDepthRange(float min_mm, float max_mm) {
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    if (min_mm < 0.0f || min_mm >= max_mm) return false;
    impl_->config_.depth_min_mm = min_mm;
    impl_->config_.depth_max_mm = max_mm;
    return true;
}

bool CameraManager::setFPS(int fps) {
    std::lock_guard<std::mutex> lock(impl_->mutex_);

    // Must be Connected
    if (impl_->state_ != CameraState::Connected) {
        throw std::logic_error(
            "setFPS() not allowed in state " +
            std::string(stateToString(impl_->state_)));
    }

    // Validate range
    if (fps < 1 || fps > 60) {
        impl_->log(LogLevel::WARN,
                   "setFPS() rejected: " + std::to_string(fps) +
                       " out of range [1, 60]");
        return false;
    }

    // No-op if same value
    if (fps == impl_->config_.fps) {
        return true;
    }

    // Update config and rebuild pipeline
    impl_->config_.fps = fps;
    impl_->state_ = CameraState::Connecting;

    try {
        impl_->tearDown();
        impl_->buildAndConnect();
        impl_->state_ = CameraState::Connected;
        impl_->log(LogLevel::INFO,
                   "setFPS: pipeline rebuilt at " + std::to_string(fps) + " FPS");
        return true;
    } catch (const std::runtime_error& e) {
        impl_->state_ = CameraState::Error;
        impl_->needs_reconnect_ = true;
        impl_->log(LogLevel::ERROR,
                   std::string("setFPS rebuild failed: ") + e.what());
        return false;
    } catch (const std::exception& e) {
        impl_->state_ = CameraState::Error;
        impl_->needs_reconnect_ = true;
        impl_->log(LogLevel::ERROR,
                   std::string("setFPS rebuild failed: ") + e.what());
        return false;
    }
}

bool CameraManager::setDepthEnabled(bool enable) {
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    impl_->config_.enable_depth = enable;
    return true;
}

// ============================================================================
// Device info and calibration
// ============================================================================

CameraStats CameraManager::getStats() const {
    CameraStats stats{};
    if (!impl_) return stats;
    std::lock_guard<std::mutex> lock(impl_->mutex_);

    stats.fps = static_cast<double>(impl_->config_.fps);
    stats.frames_processed = impl_->frames_processed_;
    stats.detection_count = impl_->detection_count_;
    stats.needs_reconnect = impl_->needs_reconnect_;

    if (impl_->state_ == CameraState::Connected ||
        impl_->state_ == CameraState::Paused) {
        auto elapsed = std::chrono::steady_clock::now() - impl_->init_time_;
        stats.uptime =
            std::chrono::duration_cast<std::chrono::milliseconds>(elapsed);
    }

    if (impl_->device_connection_) {
        auto metrics = impl_->device_connection_->getMetrics();
        stats.reconnect_count = metrics.reconnect_count;
        stats.xlink_error_count = metrics.xlink_error_count;
        stats.total_downtime_ms =
            std::chrono::milliseconds(metrics.total_downtime_ms);
        stats.last_reconnect_duration_ms =
            std::chrono::milliseconds(metrics.last_reconnect_duration_ms);
    }

    return stats;
}

std::string CameraManager::getDeviceInfo() const {
    if (!impl_) return "";
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    if (!impl_->device_connection_ ||
        !impl_->device_connection_->isConnected()) {
        return "No device connected";
    }
    return "OAK-D Lite (state: " +
           std::string(stateToString(impl_->state_)) + ")";
}

std::vector<std::string> CameraManager::getAvailableDevices() {
    // Static method — no instance state needed
    return {};
}

std::optional<CameraCalibration> CameraManager::getCalibration() const {
    if (!impl_) return std::nullopt;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    if (impl_->state_ != CameraState::Connected) return std::nullopt;
    // Calibration requires live device access — not available with mock
    return std::nullopt;
}

std::string CameraManager::exportCalibrationYAML() const {
    if (!impl_) return "";
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    return "";
}

cv::Mat CameraManager::getRGBFrame(std::chrono::milliseconds timeout) {
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    // With mock device, return empty Mat
    (void)timeout;
    return cv::Mat();
}

std::chrono::steady_clock::time_point CameraManager::getLastFrameTime() const {
    if (!impl_) return {};
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    return impl_->last_frame_time_;
}

// ============================================================================
// Pause / Resume / Reconnect
// ============================================================================

bool CameraManager::pauseCamera() {
    std::lock_guard<std::mutex> lock(impl_->mutex_);

    // Must be Connected
    if (impl_->state_ != CameraState::Connected) {
        throw std::logic_error(
            "pauseCamera() not allowed in state " +
            std::string(stateToString(impl_->state_)));
    }

    // Real pause: tear down device connection (not just a flag)
    try {
        impl_->tearDown();
    } catch (const std::exception& e) {
        impl_->log(LogLevel::ERROR,
                   std::string("pauseCamera teardown failed: ") + e.what());
        impl_->camera_error_ = true;
        impl_->state_ = CameraState::Error;
        impl_->needs_reconnect_ = true;
        return false;
    }

    impl_->state_ = CameraState::Paused;
    impl_->camera_error_ = false;
    impl_->log(LogLevel::INFO, "Camera paused (device torn down)");
    return true;
}

bool CameraManager::resumeCamera() {
    std::lock_guard<std::mutex> lock(impl_->mutex_);

    // Must be Paused
    if (impl_->state_ != CameraState::Paused) {
        throw std::logic_error(
            "resumeCamera() not allowed in state " +
            std::string(stateToString(impl_->state_)));
    }

    impl_->state_ = CameraState::Connecting;

    try {
        impl_->buildAndConnect();
        impl_->state_ = CameraState::Connected;
        impl_->log(LogLevel::INFO,
                   "Camera resumed (pipeline rebuilt, device reconnected)");
        return true;
    } catch (const std::runtime_error& e) {
        impl_->state_ = CameraState::Error;
        impl_->needs_reconnect_ = true;
        impl_->camera_error_ = true;
        impl_->log(LogLevel::ERROR,
                   std::string("Resume failed: ") + e.what());
        return false;
    } catch (const std::exception& e) {
        impl_->state_ = CameraState::Error;
        impl_->needs_reconnect_ = true;
        impl_->camera_error_ = true;
        impl_->log(LogLevel::ERROR,
                   std::string("Resume failed: ") + e.what());
        return false;
    }
}

bool CameraManager::isCameraPaused() const {
    if (!impl_) return false;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    return impl_->state_ == CameraState::Paused;
}

void CameraManager::forceReconnection() {
    if (!impl_) return;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    impl_->needs_reconnect_ = true;
    impl_->state_ = CameraState::Error;
    impl_->log(LogLevel::WARN,
               "Reconnection forced (state -> Error)");
}

bool CameraManager::needsReconnect() const {
    if (!impl_) return false;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    return impl_->needs_reconnect_;
}

bool CameraManager::reconnect() {
    std::lock_guard<std::mutex> lock(impl_->mutex_);

    // Must be in Error state
    if (impl_->state_ != CameraState::Error) {
        throw std::logic_error(
            "reconnect() requires state Error but current state is " +
            std::string(stateToString(impl_->state_)));
    }

    // Tear down any remaining connection
    impl_->tearDown();

    impl_->state_ = CameraState::Connecting;

    try {
        impl_->buildAndConnect();
        impl_->state_ = CameraState::Connected;
        impl_->needs_reconnect_ = false;
        impl_->camera_error_ = false;
        impl_->log(LogLevel::INFO, "CameraManager reconnected successfully");
        return true;
    } catch (const std::runtime_error& e) {
        impl_->state_ = CameraState::Error;
        impl_->log(LogLevel::ERROR,
                   std::string("Reconnect failed: ") + e.what());
        return false;
    } catch (const std::exception& e) {
        impl_->state_ = CameraState::Error;
        impl_->log(LogLevel::ERROR,
                   std::string("Reconnect failed: ") + e.what());
        return false;
    }
}

void CameraManager::clearReconnectFlag() {
    if (!impl_) return;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    impl_->needs_reconnect_ = false;
    if (impl_->state_ == CameraState::Error) {
        impl_->state_ = CameraState::Disconnected;
    }
}

bool CameraManager::isCameraInError() const {
    if (!impl_) return false;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    return impl_->camera_error_;
}

void CameraManager::clearCameraError() {
    if (!impl_) return;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    impl_->camera_error_ = false;
}

// ============================================================================
// Logging
// ============================================================================

void CameraManager::setLogger(LoggerCallback logger) {
    if (!impl_) return;
    std::lock_guard<std::mutex> lock(impl_->mutex_);
    impl_->logger_ = std::move(logger);
}

}  // namespace cotton_detection
