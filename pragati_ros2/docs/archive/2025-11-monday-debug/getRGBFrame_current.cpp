cv::Mat DepthAIManager::getRGBFrame(std::chrono::milliseconds timeout) {
    std::lock_guard<std::mutex> lock(pImpl_->mutex_);
    
    if (!pImpl_->initialized_ || !pImpl_->rgb_queue_) {
        std::cerr << "[DepthAIManager] getRGBFrame: Not initialized or RGB queue unavailable" << std::endl;
        return cv::Mat();
    }
    
    try {
        // CRITICAL FIX: Use non-blocking tryGet with timeout instead of blocking get()
        // The blocking get() can hang indefinitely if camera pipeline stalls
        auto start_time = std::chrono::steady_clock::now();
        auto deadline = start_time + timeout;
        std::shared_ptr<dai::ImgFrame> imgFrame;
        
        while (!imgFrame && std::chrono::steady_clock::now() < deadline) {
            imgFrame = pImpl_->rgb_queue_->tryGet<dai::ImgFrame>();
            if (!imgFrame) {
                // Sleep briefly to avoid busy-waiting (2ms polling)
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
            }
        }
        
        if (!imgFrame) {
            std::cerr << "[DepthAIManager] getRGBFrame: No frame received" << std::endl;
            return cv::Mat();
        }
        
        // Manual conversion from DepthAI ImgFrame to cv::Mat
        // DepthAI library on Pi wasn't built with OpenCV support
        auto data = imgFrame->getData();
        int width = imgFrame->getWidth();
        int height = imgFrame->getHeight();
        auto type = imgFrame->getType();
        
        cv::Mat frame;
        
        // Handle different image types
        if (type == dai::ImgFrame::Type::BGR888p) {
            // Planar BGR: convert to interleaved
            int channelSize = width * height;
            cv::Mat channels[3];
            channels[0] = cv::Mat(height, width, CV_8UC1, (void*)(data.data()));
            channels[1] = cv::Mat(height, width, CV_8UC1, (void*)(data.data() + channelSize));
            channels[2] = cv::Mat(height, width, CV_8UC1, (void*)(data.data() + 2 * channelSize));
            cv::merge(channels, 3, frame);
        } else if (type == dai::ImgFrame::Type::BGR888i || type == dai::ImgFrame::Type::RGB888i) {
            // Interleaved BGR or RGB
            frame = cv::Mat(height, width, CV_8UC3, (void*)data.data()).clone();
            if (type == dai::ImgFrame::Type::RGB888i) {
                cv::cvtColor(frame, frame, cv::COLOR_RGB2BGR);
            }
        } else {
            std::cerr << "[DepthAIManager] getRGBFrame: Unsupported image type" << std::endl;
            return cv::Mat();
        }
        
        if (frame.empty()) {
            std::cerr << "[DepthAIManager] getRGBFrame: Empty frame after conversion" << std::endl;
            return cv::Mat();
        }
        
        return frame.clone();  // Return a copy to ensure thread safety
        
    } catch (const std::exception& e) {
        std::cerr << "[DepthAIManager] getRGBFrame error: " << e.what() << std::endl;
        return cv::Mat();
    }
}
