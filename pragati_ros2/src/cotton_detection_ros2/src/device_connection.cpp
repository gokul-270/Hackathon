// device_connection.cpp — OAK-D device lifecycle management (D5, D7).
// Extracts initialize() (607-754), shutdown() (756-843), reconnect() (2140-2198),
// needsReconnect/clearReconnectFlag/forceReconnection, and isXLinkError from
// depthai_manager.cpp into an independently testable class.

#include "cotton_detection_ros2/device_connection.hpp"

#include <algorithm>
#include <cctype>

namespace cotton_detection {

// --- Constructors / Destructor ---

DeviceConnection::DeviceConnection()
    : DeviceConnection(nullptr, {}, nullptr) {}

DeviceConnection::DeviceConnection(DeviceFactory factory, BackoffConfig backoff,
                                   LoggerCallback logger)
    : factory_(std::move(factory)),
      backoff_config_(backoff),
      logger_(std::move(logger)) {}

DeviceConnection::~DeviceConnection() {
    try {
        cancel_reconnect_ = true;
        reconnect_cv_.notify_all();
        if (reconnect_thread_.joinable()) {
            reconnect_thread_.join();
        }
        disconnect();
    } catch (const std::exception&) {
        // Never throw from destructor
    }
}

// --- Connection ---

bool DeviceConnection::connect(dai::Pipeline& pipeline, const std::string& mxid,
                               const QueueConfig& queue_config) {
    // Only allow connect from Disconnected state
    auto expected = ConnectionState::Disconnected;
    if (!state_.compare_exchange_strong(expected, ConnectionState::Connecting,
                                        std::memory_order_acq_rel)) {
        log(LogLevel::WARN, "connect() rejected: state is not Disconnected");
        return false;
    }

    try {
        if (!factory_) {
            log(LogLevel::ERROR, "connect() failed: no device factory set");
            state_.store(ConnectionState::Disconnected, std::memory_order_release);
            return false;
        }

        // Create device via factory
        auto new_device = factory_(pipeline, mxid);
        if (!new_device) {
            log(LogLevel::ERROR, "connect() failed: factory returned nullptr");
            state_.store(ConnectionState::Disconnected, std::memory_order_release);
            return false;
        }

        // Set up output queues: detections and rgb always, depth if available
        new_device->getOutputQueue("detections", queue_config.max_size,
                                   queue_config.blocking);
        new_device->getOutputQueue("rgb", queue_config.max_size,
                                   queue_config.blocking);

        // Set up input queue for camera control
        new_device->getInputQueue("colorCamControl");

        // Record USB speed
        auto usb_speed = new_device->getUsbSpeed();

        {
            std::lock_guard<std::mutex> lock(mutex_);
            device_ = std::move(new_device);
            metrics_.last_usb_speed = usb_speed;
            metrics_.last_successful_connection_time = std::chrono::steady_clock::now();
        }

        state_.store(ConnectionState::Connected, std::memory_order_release);
        log(LogLevel::INFO, "Connected to device (USB speed: " +
                                std::to_string(usb_speed) + ")");
        return true;

    } catch (const std::exception& e) {
        log(LogLevel::ERROR, std::string("connect() failed: ") + e.what());
        state_.store(ConnectionState::Disconnected, std::memory_order_release);
        return false;
    }
}

void DeviceConnection::disconnect() {
    auto current = state_.load(std::memory_order_acquire);
    if (current == ConnectionState::Disconnected) {
        return;  // Already disconnected — idempotent
    }

    // Cancel any running reconnect
    cancel_reconnect_ = true;
    reconnect_cv_.notify_all();
    if (reconnect_thread_.joinable()) {
        reconnect_thread_.join();
    }

    // Close device with exception safety
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (device_) {
            try {
                device_->close();
            } catch (const std::exception& e) {
                log(LogLevel::WARN,
                    std::string("Exception during device close: ") + e.what());
            }
            device_.reset();
        }
    }

    state_.store(ConnectionState::Disconnected, std::memory_order_release);
    log(LogLevel::INFO, "Disconnected from device");
}

bool DeviceConnection::reconnectAsync(dai::Pipeline& pipeline, const std::string& mxid,
                                       const QueueConfig& queue_config,
                                       ReconnectCallback callback) {
    // Reject if already reconnecting
    auto current = state_.load(std::memory_order_acquire);
    if (current == ConnectionState::Reconnecting) {
        log(LogLevel::WARN, "reconnectAsync() rejected: already reconnecting");
        return false;
    }

    // Set state to Reconnecting
    state_.store(ConnectionState::Reconnecting, std::memory_order_release);
    cancel_reconnect_ = false;

    // Join any previous reconnect thread
    if (reconnect_thread_.joinable()) {
        reconnect_thread_.join();
    }

    // Launch background thread
    reconnect_thread_ = std::thread(&DeviceConnection::reconnectLoop, this,
                                    std::ref(pipeline), mxid, queue_config, callback);
    return true;
}

// --- State queries ---

ConnectionState DeviceConnection::getState() const {
    return state_.load(std::memory_order_acquire);
}

bool DeviceConnection::isConnected() const {
    return getState() == ConnectionState::Connected;
}

IDevice* DeviceConnection::getDevice() const {
    return device_.get();
}

ConnectionMetrics DeviceConnection::getMetrics() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return metrics_;
}

// --- XLink error detection ---

bool DeviceConnection::isXLinkError(const std::string& error_msg) {
    if (error_msg.empty()) return false;

    // Case-insensitive search
    std::string lower = error_msg;
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char c) { return std::tolower(c); });

    return lower.find("xlink") != std::string::npos ||
           lower.find("x_link") != std::string::npos ||
           lower.find("device was disconnected") != std::string::npos ||
           lower.find("couldn't read data from stream") != std::string::npos ||
           lower.find("communication exception") != std::string::npos;
}

void DeviceConnection::handleXLinkError(const std::string& error_msg,
                                        const std::string& context,
                                        dai::Pipeline& pipeline,
                                        const std::string& mxid,
                                        const QueueConfig& queue_config) {
    log(LogLevel::ERROR, "XLink error in " + context + ": " + error_msg);

    {
        std::lock_guard<std::mutex> lock(mutex_);
        metrics_.xlink_error_count++;
    }

    // Trigger async reconnection
    reconnectAsync(pipeline, mxid, queue_config);
}

// --- Internal helpers ---

void DeviceConnection::log(LogLevel level, const std::string& msg) const {
    if (logger_) {
        logger_(level, msg);
    }
}

void DeviceConnection::reconnectLoop(dai::Pipeline& pipeline, const std::string& mxid,
                                     const QueueConfig& queue_config,
                                     ReconnectCallback callback) {
    auto reconnect_start = std::chrono::steady_clock::now();
    uint32_t delay_ms = backoff_config_.initial_ms;
    bool success = false;

    for (uint32_t attempt = 0; attempt < backoff_config_.max_retries; ++attempt) {
        if (cancel_reconnect_.load(std::memory_order_acquire)) {
            log(LogLevel::INFO, "Reconnect cancelled");
            break;
        }

        // Wait with cancellable sleep (condition_variable)
        if (attempt > 0) {
            std::unique_lock<std::mutex> lock(reconnect_mutex_);
            reconnect_cv_.wait_for(lock, std::chrono::milliseconds(delay_ms),
                                   [this] { return cancel_reconnect_.load(); });
            if (cancel_reconnect_.load(std::memory_order_acquire)) {
                log(LogLevel::INFO, "Reconnect cancelled during backoff");
                break;
            }
        }

        // Disconnect current device (if any) before retry
        // Temporarily set to Disconnected for connect() to accept
        state_.store(ConnectionState::Disconnected, std::memory_order_release);
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (device_) {
                try {
                    device_->close();
                } catch (const std::exception&) {
                    // Ignore close errors during reconnect
                }
                device_.reset();
            }
        }

        // Try to connect
        if (connect(pipeline, mxid, queue_config)) {
            success = true;
            log(LogLevel::INFO, "Reconnected after " + std::to_string(attempt + 1) +
                                    " attempt(s)");
            break;
        }

        // Update backoff delay
        delay_ms = std::min(
            static_cast<uint32_t>(static_cast<double>(delay_ms) * backoff_config_.factor),
            backoff_config_.max_ms);

        // Set state back to Reconnecting for next attempt
        state_.store(ConnectionState::Reconnecting, std::memory_order_release);
    }

    auto reconnect_end = std::chrono::steady_clock::now();
    auto duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                           reconnect_end - reconnect_start)
                           .count();

    {
        std::lock_guard<std::mutex> lock(mutex_);
        metrics_.last_reconnect_duration_ms = static_cast<uint64_t>(duration_ms);
        if (success) {
            metrics_.reconnect_count++;
        }
    }

    if (!success) {
        state_.store(ConnectionState::Disconnected, std::memory_order_release);
        log(LogLevel::ERROR, "Reconnection failed after " +
                                 std::to_string(backoff_config_.max_retries) + " retries");
    }

    if (callback) {
        try {
            callback(success, success ? "" : "Max retries exhausted");
        } catch (const std::exception& e) {
            log(LogLevel::WARN,
                std::string("Exception in reconnect callback: ") + e.what());
        }
    }
}

}  // namespace cotton_detection
