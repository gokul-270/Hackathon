# Cotton Detection Performance Metrics
# Published periodically to /cotton_detection/metrics

std_msgs/Header header

# Detection Statistics
uint64 frames_processed           # Total frames processed since startup
uint64 detections_total           # Total detections across all frames
uint64 detections_filtered        # Detections filtered by confidence/depth
uint32 detections_current_frame   # Detections in most recent frame

# Pipeline Performance
float32 fps_actual                # Actual frames per second
float32 fps_target                # Target frames per second (configured)
float32 latency_avg_ms            # Average detection latency (milliseconds)
float32 latency_min_ms            # Minimum latency in current window
float32 latency_max_ms            # Maximum latency in current window
float32 latency_p95_ms            # 95th percentile latency

# Queue Health
uint32 queue_detection_size       # Current detection queue depth
uint32 queue_rgb_size             # Current RGB queue depth
uint32 queue_depth_size           # Current depth queue depth
uint32 queue_drops_total          # Total dropped frames (queue overflow)
float32 queue_wait_avg_ms         # Average time waiting on queue

# Resource Utilization
float32 device_temperature_c      # Camera device temperature (Celsius)
float32 cpu_usage_percent         # Estimated CPU usage for detection
float32 memory_mb                 # Approximate memory usage (MB)

# Pipeline Events (since last metrics publish)
uint32 pipeline_reconfig_count    # Number of pipeline reconfigurations
uint32 error_count                # Number of errors/exceptions
uint32 timeout_count              # Number of queue timeouts

# Configuration State
float32 confidence_threshold      # Current confidence threshold
float32 depth_min_mm              # Current minimum depth (mm)
float32 depth_max_mm              # Current maximum depth (mm)
bool depth_enabled                # Depth processing enabled

# Uptime
float64 uptime_seconds            # Time since initialization (seconds)
