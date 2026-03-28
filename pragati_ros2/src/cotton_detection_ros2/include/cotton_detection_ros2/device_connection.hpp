#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "cotton_detection_ros2/logging_types.hpp"

// Forward-declare DepthAI types to avoid exposing full SDK in callers
namespace dai {
class Device;
class Pipeline;
enum class UsbSpeed : int32_t;
}  // namespace dai

namespace cotton_detection {

/// Connection state machine states.
enum class ConnectionState { Disconnected, Connecting, Connected, Reconnecting };

/// Configuration for exponential backoff reconnection.
struct BackoffConfig {
    uint32_t initial_ms{1000};
    uint32_t max_ms{30000};
    double factor{2.0};
    uint32_t max_retries{10};
};

/// Queue configuration for device output queues.
struct QueueConfig {
    uint32_t max_size{2};
    bool blocking{false};
};

/// Connection lifecycle metrics.
struct ConnectionMetrics {
    uint32_t reconnect_count{0};
    uint32_t xlink_error_count{0};
    uint64_t total_downtime_ms{0};
    uint64_t last_reconnect_duration_ms{0};
    int32_t last_usb_speed{0};  // dai::UsbSpeed cast to int
    std::chrono::steady_clock::time_point last_successful_connection_time{};
};

/// Abstract device interface for testability (D5).
/// Production uses RealDevice wrapping dai::Device; tests use MockDevice.
class IDevice {
public:
    virtual ~IDevice() = default;

    /// Get an output queue by name. Returns nullptr if not found.
    virtual void* getOutputQueue(const std::string& name, uint32_t max_size,
                                 bool blocking) = 0;

    /// Get an input queue by name. Returns nullptr if not found.
    virtual void* getInputQueue(const std::string& name) = 0;

    /// Get the USB speed of the connection.
    virtual int32_t getUsbSpeed() = 0;

    /// Close the device connection.
    virtual void close() = 0;
};

/// Device factory type: creates an IDevice from a pipeline.
/// The string parameter is an optional MXID for device selection.
using DeviceFactory =
    std::function<std::unique_ptr<IDevice>(dai::Pipeline& pipeline, const std::string& mxid)>;

/// Callback for async reconnection completion.
using ReconnectCallback = std::function<void(bool success, const std::string& error_msg)>;

/// OAK-D device lifecycle management extracted from DepthAIManager.
///
/// Encapsulates dai::Device creation, output/input queue setup, ordered shutdown,
/// and reconnection with exponential backoff. All state transitions are atomic.
/// Owns its own std::mutex for connection state and queues (D7).
class DeviceConnection {
public:
    /// Construct with default (real DepthAI) device factory.
    DeviceConnection();

    /// Construct with custom device factory and backoff config.
    explicit DeviceConnection(DeviceFactory factory,
                              BackoffConfig backoff = {},
                              LoggerCallback logger = nullptr);

    /// Destructor calls disconnect().
    ~DeviceConnection();

    // Non-copyable, non-movable (owns mutex, condition_variable, thread)
    DeviceConnection(const DeviceConnection&) = delete;
    DeviceConnection& operator=(const DeviceConnection&) = delete;
    DeviceConnection(DeviceConnection&&) = delete;
    DeviceConnection& operator=(DeviceConnection&&) = delete;

    /// Connect to a device using the given pipeline.
    /// @param pipeline The DepthAI pipeline to upload.
    /// @param mxid Optional device MXID for targeting a specific device.
    /// @param queue_config Queue configuration for output queues.
    /// @return true on success, false on failure.
    bool connect(dai::Pipeline& pipeline, const std::string& mxid = "",
                 const QueueConfig& queue_config = {});

    /// Disconnect and release all resources in reverse acquisition order.
    void disconnect();

    /// Start async reconnection with exponential backoff.
    /// @param pipeline Pipeline to reconnect with.
    /// @param mxid Optional device MXID.
    /// @param queue_config Queue configuration.
    /// @param callback Invoked on completion (from background thread).
    /// @return true if reconnection was started, false if already reconnecting.
    bool reconnectAsync(dai::Pipeline& pipeline, const std::string& mxid = "",
                        const QueueConfig& queue_config = {},
                        ReconnectCallback callback = nullptr);

    /// Get the current connection state (atomic, thread-safe).
    ConnectionState getState() const;

    /// Convenience: returns true if state is Connected.
    bool isConnected() const;

    /// Get the underlying device. Returns nullptr if not connected.
    IDevice* getDevice() const;

    /// Get connection lifecycle metrics (thread-safe snapshot).
    ConnectionMetrics getMetrics() const;

    /// Detect XLink error from exception message. Static, pure function.
    static bool isXLinkError(const std::string& error_msg);

    /// Handle an XLink error: log, increment counter, trigger reconnect.
    void handleXLinkError(const std::string& error_msg, const std::string& context,
                          dai::Pipeline& pipeline, const std::string& mxid = "",
                          const QueueConfig& queue_config = {});

private:
    void log(LogLevel level, const std::string& msg) const;
    void reconnectLoop(dai::Pipeline& pipeline, const std::string& mxid,
                       const QueueConfig& queue_config, ReconnectCallback callback);

    DeviceFactory factory_;
    BackoffConfig backoff_config_;
    LoggerCallback logger_;

    mutable std::mutex mutex_;
    std::atomic<ConnectionState> state_{ConnectionState::Disconnected};
    std::unique_ptr<IDevice> device_;

    // Metrics (protected by mutex_)
    ConnectionMetrics metrics_;
    std::chrono::steady_clock::time_point downtime_start_;

    // Async reconnection
    std::thread reconnect_thread_;
    std::atomic<bool> cancel_reconnect_{false};
    std::condition_variable reconnect_cv_;
    std::mutex reconnect_mutex_;  // For condition_variable wait
};

}  // namespace cotton_detection
