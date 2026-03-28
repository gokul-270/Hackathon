/**
 * @file async_json_logger.cpp
 * @brief Implementation of asynchronous JSON logger
 *
 * Background worker thread for structured JSON logging, keeping
 * expensive operations (getStats USB calls, JSON serialization)
 * off the detection hot path.
 *
 * Author: Cotton Detection Team
 * Date: 2026-03-17
 */

#include "cotton_detection_ros2/async_json_logger.hpp"

#include <rclcpp/rclcpp.hpp>

namespace cotton_detection_ros2
{

AsyncJsonLogger::AsyncJsonLogger(
    cotton_detection::LoggerCallback logger_cb,
    size_t queue_depth)
    : logger_cb_(std::move(logger_cb))
    , max_queue_depth_(queue_depth)
    , running_(false)
    , logged_count_(0)
    , dropped_count_(0)
{
    RCLCPP_INFO(rclcpp::get_logger("async_json_logger"),
        "Created with queue_depth=%zu", max_queue_depth_);
}

AsyncJsonLogger::~AsyncJsonLogger()
{
    stop();
}

void AsyncJsonLogger::start()
{
    if (running_.load()) {
        RCLCPP_WARN(rclcpp::get_logger("async_json_logger"), "Already running");
        return;
    }

    running_.store(true);
    worker_ = std::thread(&AsyncJsonLogger::worker_thread, this);

    RCLCPP_INFO(rclcpp::get_logger("async_json_logger"), "Worker thread started");
}

void AsyncJsonLogger::stop()
{
    if (!running_.load()) {
        return;
    }

    RCLCPP_INFO(rclcpp::get_logger("async_json_logger"), "Stopping worker thread...");

    running_.store(false);
    cv_.notify_all();

    if (worker_.joinable()) {
        worker_.join();
    }

    // Drain remaining queue (worker_thread loop should have handled them,
    // but this is a safety net)
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!queue_.empty()) {
            RCLCPP_INFO(rclcpp::get_logger("async_json_logger"),
                "Draining %zu remaining tasks...", queue_.size());
        }
        while (!queue_.empty()) {
            queue_.pop();
        }
    }

    RCLCPP_INFO(rclcpp::get_logger("async_json_logger"),
        "Stopped. Stats: logged=%zu, dropped=%zu",
        static_cast<size_t>(logged_count_.load()),
        static_cast<size_t>(dropped_count_.load()));
}

bool AsyncJsonLogger::log_async(nlohmann::json j)
{
    if (!running_.load()) {
        RCLCPP_WARN(rclcpp::get_logger("async_json_logger"),
            "Not running - cannot log");
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(mutex_);

        // Drop oldest if queue full (bounded queue with drop policy)
        if (queue_.size() >= max_queue_depth_) {
            queue_.pop();
            dropped_count_.fetch_add(1);
            RCLCPP_WARN(rclcpp::get_logger("async_json_logger"),
                "Queue full - dropped oldest task (total dropped: %zu)",
                static_cast<size_t>(dropped_count_.load()));
        }

        queue_.push(LogTask(std::move(j)));
    }

    cv_.notify_one();
    return true;
}

bool AsyncJsonLogger::log_async(JsonBuilder builder)
{
    if (!running_.load()) {
        RCLCPP_WARN(rclcpp::get_logger("async_json_logger"),
            "Not running - cannot log");
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(mutex_);

        if (queue_.size() >= max_queue_depth_) {
            queue_.pop();
            dropped_count_.fetch_add(1);
            RCLCPP_WARN(rclcpp::get_logger("async_json_logger"),
                "Queue full - dropped oldest task (total dropped: %zu)",
                static_cast<size_t>(dropped_count_.load()));
        }

        queue_.push(LogTask(std::move(builder)));
    }

    cv_.notify_one();
    return true;
}

size_t AsyncJsonLogger::queue_size() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return queue_.size();
}

void AsyncJsonLogger::worker_thread()
{
    RCLCPP_DEBUG(rclcpp::get_logger("async_json_logger"), "Worker thread running");

    while (running_.load() || !queue_.empty()) {
        LogTask task;

        {
            std::unique_lock<std::mutex> lock(mutex_);

            cv_.wait_for(lock, std::chrono::milliseconds(10), [this]() {
                return !queue_.empty() || !running_.load();
            });

            if (queue_.empty()) {
                continue;
            }

            task = std::move(queue_.front());
            queue_.pop();
        }

        // Process task outside lock
        try {
            nlohmann::json j;

            if (std::holds_alternative<nlohmann::json>(task)) {
                j = std::move(std::get<nlohmann::json>(task));
            } else {
                // Deferred builder — call it on this (worker) thread
                auto& builder = std::get<JsonBuilder>(task);
                j = builder();
            }

            logger_cb_(cotton_detection::LogLevel::INFO, j.dump());
            logged_count_.fetch_add(1);

        } catch (const std::exception& e) {
            RCLCPP_ERROR(rclcpp::get_logger("async_json_logger"),
                "Exception processing log task: %s", e.what());
        }
    }

    RCLCPP_INFO(rclcpp::get_logger("async_json_logger"),
        "Worker thread exiting. Final stats: logged=%zu, dropped=%zu",
        static_cast<size_t>(logged_count_.load()),
        static_cast<size_t>(dropped_count_.load()));
}

}  // namespace cotton_detection_ros2
