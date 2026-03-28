CottonDetection DepthAIManager::Impl::convertDetection(const dai::SpatialImgDetection& det) {
    CottonDetection result;
    
    // Convert detection label and confidence
    result.label = det.label;
    result.confidence = det.confidence;
    
    // Convert normalized bounding box coordinates [0, 1]
    result.x_min = det.xmin;
    result.y_min = det.ymin;
    result.x_max = det.xmax;
    result.y_max = det.ymax;
    
    // Convert spatial coordinates from DepthAI format to millimeters
    // DepthAI provides coordinates in millimeters relative to camera center:
    // - X: positive right, negative left
    // - Y: positive up, negative down  
    // - Z: positive forward (distance from camera)
    result.spatial_x = det.spatialCoordinates.x;  // mm
    result.spatial_y = det.spatialCoordinates.y;  // mm
    result.spatial_z = det.spatialCoordinates.z;  // mm
    
    // Record detection timestamp
    result.timestamp = std::chrono::steady_clock::now();
    
    // Store image dimensions for potential denormalization
    result.image_width = config_.width;
    result.image_height = config_.height;
    
    return result;
}
