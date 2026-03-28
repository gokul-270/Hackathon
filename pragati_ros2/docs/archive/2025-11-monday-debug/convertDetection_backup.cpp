CottonDetection DepthAIManager::Impl::convertDetection(const dai::SpatialImgDetection& det) {
    CottonDetection result;
    
    // Convert detection label and confidence
    result.label = det.label;
    result.confidence = det.confidence;
    
    // Convert normalized bounding box coordinates [0, 1]
    // Apply 90° clockwise rotation transformation
    float old_xmin = det.xmin;
    float old_ymin = det.ymin;
    float old_xmax = det.xmax;
    float old_ymax = det.ymax;
    
    result.x_min = 1.0f - old_ymax;
    result.y_min = old_xmin;
    result.x_max = 1.0f - old_ymin;
    result.y_max = old_xmax;
    
    // Convert spatial coordinates from DepthAI format with 90° CW rotation correction
    // DepthAI calculates spatial coords using ORIGINAL camera intrinsics (1920x1080)
    // before the image rotation happens, so we must:
    // 1. Rotate the 3D coordinates (90° CW: new_x = old_y, new_y = -old_x)
    // 2. Account for principal point shift during image rotation
    //
    // Original DepthAI coordinates (mm, before rotation):
    // - X: positive right, negative left
    // - Y: positive down, negative up
    // - Z: positive forward (distance from camera)
    
    float raw_x = det.spatialCoordinates.x;  // mm
    float raw_y = det.spatialCoordinates.y;  // mm
    float raw_z = det.spatialCoordinates.z;  // mm
    
    // Apply 90° clockwise rotation with DepthAI coordinate system correction
    // DepthAI Y-axis is positive DOWN, so we need: new_x = old_y, new_y = old_x (NO negative)
    // This matches the cv::rotate(ROTATE_90_CLOCKWISE) applied to the RGB frame
    result.spatial_x = raw_y;   // mm
    result.spatial_y = -raw_x;  // mm (NEGATIVE - cottons are below arm, need negative Y)
    result.spatial_z = raw_z;   // mm (depth unchanged)

    
    // Record detection timestamp
    result.timestamp = std::chrono::steady_clock::now();
    
    // Store image dimensions for potential denormalization
    result.image_width = config_.width;
    result.image_height = config_.height;
    
    return result;
}
