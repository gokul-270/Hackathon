/**
 * @file async_image_saver.cpp
 * @brief Implementation of asynchronous image saver
 *
 * Author: Cotton Detection Team
 * Date: 2025-11-04
 */

#include "cotton_detection_ros2/async_image_saver.hpp"
#include <rclcpp/rclcpp.hpp>
#include <iostream>
#include <filesystem>

namespace cotton_detection_ros2
{

AsyncImageSaver::AsyncImageSaver(size_t queue_depth, int jpeg_quality)
    : max_queue_depth_(queue_depth)
    , jpeg_quality_(jpeg_quality)
    , running_(false)
    , saved_count_(0)
    , dropped_count_(0)
{
    if (jpeg_quality_ < 0 || jpeg_quality_ > 100) {
        RCLCPP_WARN(rclcpp::get_logger("async_image_saver"), "Invalid JPEG quality %d, clamping to 85", jpeg_quality_);
        jpeg_quality_ = 85;
    }

    RCLCPP_INFO(rclcpp::get_logger("async_image_saver"), "Created with queue_depth=%zu, jpeg_quality=%d", max_queue_depth_, jpeg_quality_);
}

AsyncImageSaver::~AsyncImageSaver()
{
    stop();
}

void AsyncImageSaver::start()
{
    if (running_.load()) {
        RCLCPP_WARN(rclcpp::get_logger("async_image_saver"), "Already running");
        return;
    }

    running_.store(true);
    worker_ = std::thread(&AsyncImageSaver::worker_thread, this);

    RCLCPP_INFO(rclcpp::get_logger("async_image_saver"), "Worker thread started");
}

void AsyncImageSaver::stop()
{
    if (!running_.load()) {
        return;
    }

    RCLCPP_INFO(rclcpp::get_logger("async_image_saver"), "Stopping worker thread...");

    // Signal worker to stop
    running_.store(false);
    cv_.notify_all();

    // Wait for worker to finish
    if (worker_.joinable()) {
        worker_.join();
    }

    // Drain remaining queue
    {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!queue_.empty()) {
            RCLCPP_INFO(rclcpp::get_logger("async_image_saver"), "Draining %zu remaining images...", queue_.size());
        }
        while (!queue_.empty()) {
            queue_.pop();
        }
    }

    RCLCPP_INFO(rclcpp::get_logger("async_image_saver"), "Stopped. Stats: saved=%zu, dropped=%zu",
                static_cast<size_t>(saved_count_.load()), static_cast<size_t>(dropped_count_.load()));
}

bool AsyncImageSaver::save_async(const cv::Mat& image, const std::string& filepath)
{
    if (!running_.load()) {
        RCLCPP_WARN(rclcpp::get_logger("async_image_saver"), "Not running - cannot save image");
        return false;
    }

    if (image.empty()) {
        RCLCPP_WARN(rclcpp::get_logger("async_image_saver"), "Empty image - skipping save");
        return false;
    }

    {
        std::lock_guard<std::mutex> lock(mutex_);

        // Drop oldest if queue full (bounded queue with drop policy)
        if (queue_.size() >= max_queue_depth_) {
            queue_.pop();  // Drop oldest
            dropped_count_.fetch_add(1);
            RCLCPP_WARN(rclcpp::get_logger("async_image_saver"), "Queue full - dropped oldest image (total dropped: %zu)",
                         static_cast<size_t>(dropped_count_.load()));
        }

        // Clone image and push to queue
        ImageTask task;
        task.image = image.clone();
        task.filepath = filepath;
        queue_.push(std::move(task));
    }

    // Wake up worker
    cv_.notify_one();

    return true;
}

size_t AsyncImageSaver::queue_size() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return queue_.size();
}

void AsyncImageSaver::worker_thread()
{
    RCLCPP_DEBUG(rclcpp::get_logger("async_image_saver"), "Worker thread running");

    // JPEG compression parameters
    std::vector<int> compression_params;
    compression_params.push_back(cv::IMWRITE_JPEG_QUALITY);
    compression_params.push_back(jpeg_quality_);

    while (running_.load() || !queue_.empty()) {
        ImageTask task;

        {
            std::unique_lock<std::mutex> lock(mutex_);

            // Wait for work or stop signal
            cv_.wait_for(lock, std::chrono::milliseconds(10), [this]() {
                return !queue_.empty() || !running_.load();
            });

            if (queue_.empty()) {
                continue;
            }

            // Pop task from queue
            task = std::move(queue_.front());
            queue_.pop();
        }

        // Write to disk (outside lock - this is the slow part)
        try {
            // Ensure parent directory exists
            std::filesystem::path filepath(task.filepath);
            std::filesystem::path parent = filepath.parent_path();

            if (!parent.empty() && !std::filesystem::exists(parent)) {
                std::filesystem::create_directories(parent);
            }

            // Write JPEG with compression
            bool success = cv::imwrite(task.filepath, task.image, compression_params);

            if (success) {
                saved_count_.fetch_add(1);
                // Debug logging disabled for performance - only log errors
            } else {
                RCLCPP_ERROR(rclcpp::get_logger("async_image_saver"), "Failed to write: %s", task.filepath.c_str());
            }
        } catch (const std::exception& e) {
            RCLCPP_ERROR(rclcpp::get_logger("async_image_saver"), "Exception writing %s: %s", task.filepath.c_str(), e.what());
        }
    }

    RCLCPP_INFO(rclcpp::get_logger("async_image_saver"), "Worker thread exiting. Final stats: saved=%zu, dropped=%zu",
                static_cast<size_t>(saved_count_.load()), static_cast<size_t>(dropped_count_.load()));
}

}  // namespace cotton_detection_ros2
