/**
 * @file async_json_logger.hpp
 * @brief Asynchronous JSON logger with producer-consumer queue
 *
 * Moves structured JSON logging (including expensive getStats() USB calls)
 * off the detection hot path. Detection thread queues log tasks; background
 * worker thread serializes JSON and emits via logger callback.
 *
 * Modeled on AsyncImageSaver — same bounded-queue, drop-oldest pattern.
 *
 * Author: Cotton Detection Team
 * Date: 2026-03-17
 */

#ifndef COTTON_DETECTION_ROS2__ASYNC_JSON_LOGGER_HPP_
#define COTTON_DETECTION_ROS2__ASYNC_JSON_LOGGER_HPP_

#include <atomic>
#include <condition_variable>
#include <functional>
#include <mutex>
#include <queue>
#include <string>
#include <thread>
#include <variant>

#include <nlohmann/json.hpp>

#include "cotton_detection_ros2/logging_types.hpp"

namespace cotton_detection_ros2
{

/**
 * @brief Asynchronous JSON logger using producer-consumer pattern
 *
 * Detection thread posts JSON log tasks to a bounded queue (non-blocking).
 * Background worker thread serializes and emits them via the logger callback.
 * Zero impact on detection pipeline latency.
 *
 * Supports two task types:
 * - Pre-built JSON object: worker calls j.dump() + logger_cb_()
 * - Deferred builder function: worker calls builder() to construct JSON
 *   (allows expensive operations like getStats() to run in background)
 *
 * Thread safety: queue protected by mutex + condition variable.
 * Logger callback (rclcpp macros) is thread-safe.
 */
class AsyncJsonLogger
{
public:
    /// Deferred builder: called on worker thread to construct JSON
    using JsonBuilder = std::function<nlohmann::json()>;

    /**
     * @brief Constructor
     * @param logger_cb Logger callback for emitting serialized JSON
     * @param queue_depth Maximum number of log tasks to buffer
     */
    explicit AsyncJsonLogger(
        cotton_detection::LoggerCallback logger_cb,
        size_t queue_depth = 5);

    /**
     * @brief Destructor — stops worker thread and drains queue
     */
    ~AsyncJsonLogger();

    // Non-copyable, non-movable
    AsyncJsonLogger(const AsyncJsonLogger&) = delete;
    AsyncJsonLogger& operator=(const AsyncJsonLogger&) = delete;
    AsyncJsonLogger(AsyncJsonLogger&&) = delete;
    AsyncJsonLogger& operator=(AsyncJsonLogger&&) = delete;

    /**
     * @brief Start the background worker thread
     */
    void start();

    /**
     * @brief Stop the background worker thread (drains remaining tasks)
     */
    void stop();

    /**
     * @brief Queue a pre-built JSON object for background logging
     * @param j JSON object (moved into queue)
     * @return true if queued, false if not running or dropped
     */
    bool log_async(nlohmann::json j);

    /**
     * @brief Queue a deferred builder function for background logging
     * @param builder Function called on worker thread to produce JSON
     * @return true if queued, false if not running or dropped
     *
     * Use this for expensive operations (e.g., getStats() USB calls)
     * that should not block the detection thread.
     */
    bool log_async(JsonBuilder builder);

    /// Number of tasks currently in queue
    size_t queue_size() const;

    /// Number of log entries successfully emitted
    size_t get_logged_count() const { return logged_count_.load(); }

    /// Number of log tasks dropped due to full queue
    size_t get_dropped_count() const { return dropped_count_.load(); }

private:
    /// A queued log task — either a pre-built JSON or a deferred builder
    using LogTask = std::variant<nlohmann::json, JsonBuilder>;

    /// Worker thread function — processes queue
    void worker_thread();

    // Configuration
    cotton_detection::LoggerCallback logger_cb_;
    size_t max_queue_depth_;

    // Queue and synchronization
    std::queue<LogTask> queue_;
    mutable std::mutex mutex_;
    std::condition_variable cv_;

    // Worker thread
    std::thread worker_;
    std::atomic<bool> running_;

    // Statistics
    std::atomic<size_t> logged_count_;
    std::atomic<size_t> dropped_count_;
};

}  // namespace cotton_detection_ros2

#endif  // COTTON_DETECTION_ROS2__ASYNC_JSON_LOGGER_HPP_
