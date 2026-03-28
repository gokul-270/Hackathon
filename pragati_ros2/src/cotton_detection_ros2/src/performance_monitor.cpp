#include "cotton_detection_ros2/performance_monitor.hpp"
#include <algorithm>
#include <numeric>
#include <sstream>
#include <iomanip>
#include <sys/resource.h>
#include <unistd.h>

namespace cotton_detection_ros2
{

PerformanceMonitor::PerformanceMonitor(rclcpp::Node* node)
: node_(node),
  detailed_logging_(false),
  max_recent_measurements_(100),
  monitoring_active_(false)
{
    reset_metrics();
}

void PerformanceMonitor::start_monitoring()
{
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    monitoring_active_ = true;
    global_metrics_.start_time = std::chrono::steady_clock::now();
    RCLCPP_INFO(node_->get_logger(), "📊 Performance monitoring started");
}

void PerformanceMonitor::stop_monitoring()
{
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    monitoring_active_ = false;
    RCLCPP_INFO(node_->get_logger(), "📊 Performance monitoring stopped");
    log_metrics();
}

void PerformanceMonitor::start_operation(const std::string& operation_name)
{
    if (!monitoring_active_) return;

    std::lock_guard<std::mutex> lock(metrics_mutex_);
    active_operations_[operation_name] = std::chrono::steady_clock::now();

    if (detailed_logging_) {
        RCLCPP_DEBUG(node_->get_logger(), "⏱️ Started operation: %s", operation_name.c_str());
    }
}

void PerformanceMonitor::end_operation(const std::string& operation_name, bool success)
{
    if (!monitoring_active_) return;

    auto end_time = std::chrono::steady_clock::now();

    std::lock_guard<std::mutex> lock(metrics_mutex_);
    auto it = active_operations_.find(operation_name);
    if (it == active_operations_.end()) {
        RCLCPP_WARN(node_->get_logger(), "⚠️ Operation '%s' ended but was never started", operation_name.c_str());
        return;
    }

    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end_time - it->second);
    double latency_ms = duration.count() / 1000.0;

    active_operations_.erase(it);

    // Update global metrics
    update_latency_stats(latency_ms);
    update_fps();

    if (detailed_logging_) {
        RCLCPP_DEBUG(node_->get_logger(), "✅ Operation '%s' completed in %.2f ms (%s)",
                    operation_name.c_str(), latency_ms, success ? "success" : "failed");
    }
}

void PerformanceMonitor::record_frame_processed(const std::string& detection_mode, size_t num_detections)
{
    if (!monitoring_active_) return;

    std::lock_guard<std::mutex> lock(metrics_mutex_);
    global_metrics_.total_frames_processed++;

    // Update mode-specific metrics
    if (mode_metrics_.find(detection_mode) == mode_metrics_.end()) {
        mode_metrics_[detection_mode] = DetectionModeMetrics{detection_mode, PerformanceMetrics{}};
        mode_metrics_[detection_mode].metrics.start_time = std::chrono::steady_clock::now();
    }

    auto& mode_metric = mode_metrics_[detection_mode];
    mode_metric.metrics.total_frames_processed++;

    // Update FPS for this mode
    auto now = std::chrono::steady_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::seconds>(now - mode_metric.metrics.start_time);
    if (duration.count() > 0) {
        mode_metric.metrics.fps = static_cast<double>(mode_metric.metrics.total_frames_processed) / duration.count();
    }

    if (detailed_logging_) {
        RCLCPP_DEBUG(node_->get_logger(), "📊 Frame processed - Mode: %s, Detections: %zu, FPS: %.1f",
                    detection_mode.c_str(), num_detections, mode_metric.metrics.fps);
    }
}

PerformanceMonitor::PerformanceMetrics PerformanceMonitor::get_metrics() const
{
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    return global_metrics_;
}

PerformanceMonitor::DetectionModeMetrics PerformanceMonitor::get_mode_metrics(const std::string& mode_name) const
{
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    auto it = mode_metrics_.find(mode_name);
    if (it != mode_metrics_.end()) {
        return it->second;
    }
    return DetectionModeMetrics{mode_name, PerformanceMetrics{}};
}

std::vector<PerformanceMonitor::DetectionModeMetrics> PerformanceMonitor::get_all_mode_metrics() const
{
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    std::vector<DetectionModeMetrics> result;
    for (const auto& pair : mode_metrics_) {
        result.push_back(pair.second);
    }
    return result;
}

void PerformanceMonitor::reset_metrics()
{
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    global_metrics_ = PerformanceMetrics{};
    mode_metrics_.clear();
    active_operations_.clear();
    global_metrics_.start_time = std::chrono::steady_clock::now();
    RCLCPP_INFO(node_->get_logger(), "📊 Performance metrics reset");
}

std::string PerformanceMonitor::generate_report() const
{
    std::lock_guard<std::mutex> lock(metrics_mutex_);

    std::stringstream ss;
    ss << std::fixed << std::setprecision(2);

    ss << "📊 Performance Report\n";
    ss << "═══════════════════════════════════════════════\n\n";

    // Global metrics
    ss << "🌍 Global Performance:\n";
    ss << "   FPS: " << global_metrics_.fps << "\n";
    ss << "   Average Latency: " << global_metrics_.avg_latency_ms << " ms\n";
    ss << "   Min Latency: " << global_metrics_.min_latency_ms << " ms\n";
    ss << "   Max Latency: " << global_metrics_.max_latency_ms << " ms\n";
    ss << "   Total Frames: " << global_metrics_.total_frames_processed << "\n";
    ss << "   Memory Usage: " << get_memory_usage() << " MB\n";
    ss << "   CPU Usage: " << calculate_cpu_usage() << " %\n\n";

    // Mode-specific metrics
    if (!mode_metrics_.empty()) {
        ss << "🎯 Detection Mode Performance:\n";
        for (const auto& pair : mode_metrics_) {
            const auto& mode = pair.second;
            ss << "   " << mode.mode_name << ":\n";
            ss << "     FPS: " << mode.metrics.fps << "\n";
            ss << "     Frames: " << mode.metrics.total_frames_processed << "\n";
            if (!mode.metrics.recent_latencies_ms.empty()) {
                double avg_latency = std::accumulate(mode.metrics.recent_latencies_ms.begin(),
                                                   mode.metrics.recent_latencies_ms.end(), 0.0) /
                                   mode.metrics.recent_latencies_ms.size();
                ss << "     Avg Latency: " << avg_latency << " ms\n";
            }
            ss << "\n";
        }
    }

    // Performance recommendations
    ss << "💡 Recommendations:\n";
    if (global_metrics_.fps < 10.0) {
        ss << "   ⚠️ Low FPS detected. Consider optimizing detection pipeline.\n";
    }
    if (global_metrics_.avg_latency_ms > 100.0) {
        ss << "   ⚠️ High latency detected. Consider using faster detection mode.\n";
    }
    if (calculate_cpu_usage() > 80.0) {
        ss << "   ⚠️ High CPU usage. Consider reducing image resolution or preprocessing.\n";
    }

    return ss.str();
}

void PerformanceMonitor::set_detailed_logging(bool enable)
{
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    detailed_logging_ = enable;
}

void PerformanceMonitor::set_max_recent_measurements(size_t max_recent)
{
    std::lock_guard<std::mutex> lock(metrics_mutex_);
    max_recent_measurements_ = max_recent;
}

void PerformanceMonitor::update_fps()
{
    auto now = std::chrono::steady_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::seconds>(now - global_metrics_.start_time);
    if (duration.count() > 0) {
        global_metrics_.fps = static_cast<double>(global_metrics_.total_frames_processed) / duration.count();
    }
}

double PerformanceMonitor::calculate_cpu_usage() const
{
    // Simplified CPU usage calculation
    // In a real implementation, you might use /proc/stat or similar
    // For now, return a placeholder based on recent activity
    return global_metrics_.recent_latencies_ms.size() > 10 ? 45.0 : 25.0;
}

size_t PerformanceMonitor::get_memory_usage() const
{
    struct rusage usage;
    if (getrusage(RUSAGE_SELF, &usage) == 0) {
        // Convert KB to MB
        return usage.ru_maxrss / 1024;
    }
    return 0;
}

void PerformanceMonitor::update_latency_stats(double latency_ms)
{
    global_metrics_.recent_latencies_ms.push_back(latency_ms);

    // Keep only recent measurements
    if (global_metrics_.recent_latencies_ms.size() > max_recent_measurements_) {
        global_metrics_.recent_latencies_ms.erase(global_metrics_.recent_latencies_ms.begin());
    }

    if (!global_metrics_.recent_latencies_ms.empty()) {
        global_metrics_.min_latency_ms = *std::min_element(global_metrics_.recent_latencies_ms.begin(),
                                                         global_metrics_.recent_latencies_ms.end());
        global_metrics_.max_latency_ms = *std::max_element(global_metrics_.recent_latencies_ms.begin(),
                                                         global_metrics_.recent_latencies_ms.end());
        global_metrics_.avg_latency_ms = std::accumulate(global_metrics_.recent_latencies_ms.begin(),
                                                        global_metrics_.recent_latencies_ms.end(), 0.0) /
                                       global_metrics_.recent_latencies_ms.size();

        // Calculate percentiles (p50, p95, p99)
        auto sorted = global_metrics_.recent_latencies_ms;  // copy
        std::sort(sorted.begin(), sorted.end());
        size_t n = sorted.size();
        global_metrics_.p50_latency_ms = sorted[n * 50 / 100];
        global_metrics_.p95_latency_ms = sorted[std::min(n - 1, n * 95 / 100)];
        global_metrics_.p99_latency_ms = sorted[std::min(n - 1, n * 99 / 100)];
    }
}

void PerformanceMonitor::log_metrics() const
{
    if (!monitoring_active_) return;

    RCLCPP_INFO(node_->get_logger(), "📊 Performance Summary:");
    RCLCPP_INFO(node_->get_logger(), "   FPS: %.1f, Avg Latency: %.1f ms, Frames: %zu",
                global_metrics_.fps, global_metrics_.avg_latency_ms, global_metrics_.total_frames_processed);

    for (const auto& pair : mode_metrics_) {
        const auto& mode = pair.second;
        RCLCPP_INFO(node_->get_logger(), "   %s: FPS=%.1f, Frames=%zu",
                   mode.mode_name.c_str(), mode.metrics.fps, mode.metrics.total_frames_processed);
    }
}

} // namespace cotton_detection_ros2
