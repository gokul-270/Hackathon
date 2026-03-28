/**
 * @file async_image_saver.hpp
 * @brief Asynchronous image saver with producer-consumer queue
 * 
 * Allows detection pipeline to continue without blocking on disk I/O.
 * Uses bounded queue with drop-oldest policy to prevent memory buildup.
 * 
 * Author: Cotton Detection Team
 * Date: 2025-11-04
 */

#ifndef COTTON_DETECTION_ROS2__ASYNC_IMAGE_SAVER_HPP_
#define COTTON_DETECTION_ROS2__ASYNC_IMAGE_SAVER_HPP_

#include <opencv2/opencv.hpp>
#include <queue>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <string>
#include <memory>

namespace cotton_detection_ros2
{

/**
 * @brief Asynchronous image saver using producer-consumer pattern
 * 
 * Detection thread posts images to queue (non-blocking).
 * Background worker thread writes images to disk.
 * Zero impact on detection pipeline performance.
 */
class AsyncImageSaver
{
public:
    /**
     * @brief Constructor
     * @param queue_depth Maximum number of images to buffer (3-5 recommended)
     * @param jpeg_quality JPEG compression quality 0-100 (85 recommended)
     */
    explicit AsyncImageSaver(size_t queue_depth = 3, int jpeg_quality = 85);
    
    /**
     * @brief Destructor - stops worker thread and drains queue
     */
    ~AsyncImageSaver();
    
    // Disable copy and move
    AsyncImageSaver(const AsyncImageSaver&) = delete;
    AsyncImageSaver& operator=(const AsyncImageSaver&) = delete;
    AsyncImageSaver(AsyncImageSaver&&) = delete;
    AsyncImageSaver& operator=(AsyncImageSaver&&) = delete;
    
    /**
     * @brief Start the background saver thread
     */
    void start();
    
    /**
     * @brief Stop the background saver thread
     */
    void stop();
    
    /**
     * @brief Queue an image for asynchronous saving
     * @param image Image to save (will be cloned)
     * @param filepath Full path where image should be saved
     * @return true if queued, false if queue full (image dropped)
     * 
     * This method returns immediately - does not block on disk I/O.
     */
    bool save_async(const cv::Mat& image, const std::string& filepath);
    
    /**
     * @brief Get number of images currently in queue
     */
    size_t queue_size() const;
    
    /**
     * @brief Get number of images successfully saved
     */
    size_t get_saved_count() const { return saved_count_.load(); }
    
    /**
     * @brief Get number of images dropped due to full queue
     */
    size_t get_dropped_count() const { return dropped_count_.load(); }

private:
    struct ImageTask {
        cv::Mat image;
        std::string filepath;
    };
    
    /**
     * @brief Worker thread function - processes queue
     */
    void worker_thread();
    
    // Configuration
    size_t max_queue_depth_;
    int jpeg_quality_;
    
    // Queue and synchronization
    std::queue<ImageTask> queue_;
    mutable std::mutex mutex_;
    std::condition_variable cv_;
    
    // Worker thread
    std::thread worker_;
    std::atomic<bool> running_;
    
    // Statistics
    std::atomic<size_t> saved_count_;
    std::atomic<size_t> dropped_count_;
};

}  // namespace cotton_detection_ros2

#endif  // COTTON_DETECTION_ROS2__ASYNC_IMAGE_SAVER_HPP_
