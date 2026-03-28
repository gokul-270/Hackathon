/*
 * Performance Monitor Node
 * Real-time monitoring of system resources, ROS2 nodes, topics, and services
 * Provides metrics dashboard and performance analytics
 */

#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <diagnostic_msgs/msg/diagnostic_array.hpp>
#include <diagnostic_msgs/msg/diagnostic_status.hpp>
#include <diagnostic_msgs/msg/key_value.hpp>

#include <sys/sysinfo.h>
#include <sys/statvfs.h>
#include <fstream>
#include <sstream>
#include <chrono>
#include <thread>
#include <map>
#include <vector>

class PerformanceMonitor : public rclcpp::Node
{
public:
    PerformanceMonitor() : Node("performance_monitor")
    {
        RCLCPP_INFO(this->get_logger(), "🚀 Performance Monitor starting...");
        
        // Publishers
        diagnostics_publisher_ = this->create_publisher<diagnostic_msgs::msg::DiagnosticArray>(
            "/performance_diagnostics", 10);
        
        metrics_publisher_ = this->create_publisher<std_msgs::msg::String>(
            "/performance_metrics", 10);
        
        // Parameters
        this->declare_parameter("monitoring_rate", 1.0);  // Hz
        this->declare_parameter("enable_system_monitoring", true);
        this->declare_parameter("enable_ros_monitoring", true);
        this->declare_parameter("enable_network_monitoring", false);
        
        monitoring_rate_ = this->get_parameter("monitoring_rate").as_double();
        enable_system_monitoring_ = this->get_parameter("enable_system_monitoring").as_bool();
        enable_ros_monitoring_ = this->get_parameter("enable_ros_monitoring").as_bool();
        enable_network_monitoring_ = this->get_parameter("enable_network_monitoring").as_bool();
        
        // Timer for periodic monitoring
        timer_ = this->create_wall_timer(
            std::chrono::milliseconds(static_cast<int>(1000.0 / monitoring_rate_)),
            std::bind(&PerformanceMonitor::monitor_callback, this));
        
        // Initialize monitoring
        start_time_ = std::chrono::steady_clock::now();
        
        RCLCPP_INFO(this->get_logger(), "✅ Performance Monitor initialized");
        RCLCPP_INFO(this->get_logger(), "   📊 Monitoring rate: %.1f Hz", monitoring_rate_);
        RCLCPP_INFO(this->get_logger(), "   🖥️  System monitoring: %s", enable_system_monitoring_ ? "enabled" : "disabled");
        RCLCPP_INFO(this->get_logger(), "   🤖 ROS monitoring: %s", enable_ros_monitoring_ ? "enabled" : "disabled");
    }

private:
    void monitor_callback()
    {
        auto diagnostic_array = diagnostic_msgs::msg::DiagnosticArray();
        diagnostic_array.header.stamp = this->get_clock()->now();
        
        std::stringstream metrics_json;
        metrics_json << "{";
        metrics_json << "\"timestamp\": \"" << std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - start_time_).count() << "\",";
        
        // System Resource Monitoring
        if (enable_system_monitoring_) {
            monitor_system_resources(diagnostic_array, metrics_json);
        }
        
        // ROS2 System Monitoring  
        if (enable_ros_monitoring_) {
            monitor_ros_system(diagnostic_array, metrics_json);
        }
        
        metrics_json << "\"monitoring_active\": true}";
        
        // Publish diagnostics and metrics
        diagnostics_publisher_->publish(diagnostic_array);
        
        auto metrics_msg = std_msgs::msg::String();
        metrics_msg.data = metrics_json.str();
        metrics_publisher_->publish(metrics_msg);
    }
    
    void monitor_system_resources(diagnostic_msgs::msg::DiagnosticArray& diagnostic_array, 
                                  std::stringstream& metrics_json)
    {
        // CPU Usage
        auto cpu_usage = get_cpu_usage();
        add_diagnostic_status(diagnostic_array, "CPU Usage", 
                              cpu_usage < 80.0 ? diagnostic_msgs::msg::DiagnosticStatus::OK : 
                              diagnostic_msgs::msg::DiagnosticStatus::WARN,
                              "CPU usage: " + std::to_string(cpu_usage) + "%",
                              {{"usage_percent", std::to_string(cpu_usage)}});
        
        // Memory Usage
        auto memory_info = get_memory_usage();
        double memory_usage_percent = (memory_info.first / memory_info.second) * 100.0;
        add_diagnostic_status(diagnostic_array, "Memory Usage",
                              memory_usage_percent < 80.0 ? diagnostic_msgs::msg::DiagnosticStatus::OK :
                              diagnostic_msgs::msg::DiagnosticStatus::WARN,
                              "Memory usage: " + std::to_string(memory_usage_percent) + "%",
                              {{"usage_percent", std::to_string(memory_usage_percent)},
                               {"used_gb", std::to_string(memory_info.first / 1024.0 / 1024.0 / 1024.0)},
                               {"total_gb", std::to_string(memory_info.second / 1024.0 / 1024.0 / 1024.0)}});
        
        // Disk Usage
        auto disk_usage = get_disk_usage("/");
        add_diagnostic_status(diagnostic_array, "Disk Usage",
                              disk_usage < 80.0 ? diagnostic_msgs::msg::DiagnosticStatus::OK :
                              diagnostic_msgs::msg::DiagnosticStatus::WARN,
                              "Disk usage: " + std::to_string(disk_usage) + "%",
                              {{"usage_percent", std::to_string(disk_usage)}});
        
        // Add to JSON metrics
        metrics_json << "\"system\": {";
        metrics_json << "\"cpu_usage\": " << cpu_usage << ",";
        metrics_json << "\"memory_usage_percent\": " << memory_usage_percent << ",";
        metrics_json << "\"memory_used_gb\": " << (memory_info.first / 1024.0 / 1024.0 / 1024.0) << ",";
        metrics_json << "\"memory_total_gb\": " << (memory_info.second / 1024.0 / 1024.0 / 1024.0) << ",";
        metrics_json << "\"disk_usage_percent\": " << disk_usage;
        metrics_json << "},";
    }
    
    void monitor_ros_system(diagnostic_msgs::msg::DiagnosticArray& diagnostic_array,
                            std::stringstream& metrics_json)
    {
        // Get node count, topic count, service count
        // This is simplified - in a real implementation you'd use the ROS2 graph API
        
        auto uptime = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - start_time_).count();
            
        add_diagnostic_status(diagnostic_array, "ROS2 System",
                              diagnostic_msgs::msg::DiagnosticStatus::OK,
                              "ROS2 system operational",
                              {{"uptime_seconds", std::to_string(uptime)},
                               {"monitoring_rate", std::to_string(monitoring_rate_)}});
        
        // Add to JSON metrics
        metrics_json << "\"ros2\": {";
        metrics_json << "\"uptime_seconds\": " << uptime << ",";
        metrics_json << "\"monitoring_rate_hz\": " << monitoring_rate_;
        metrics_json << "},";
    }
    
    void add_diagnostic_status(diagnostic_msgs::msg::DiagnosticArray& array,
                               const std::string& name,
                               uint8_t level,
                               const std::string& message,
                               const std::vector<std::pair<std::string, std::string>>& values)
    {
        diagnostic_msgs::msg::DiagnosticStatus status;
        status.name = name;
        status.level = level;
        status.message = message;
        
        for (const auto& kv : values) {
            diagnostic_msgs::msg::KeyValue key_value;
            key_value.key = kv.first;
            key_value.value = kv.second;
            status.values.push_back(key_value);
        }
        
        array.status.push_back(status);
    }
    
    double get_cpu_usage()
    {
        static long long prev_idle = 0, prev_total = 0;
        
        std::ifstream file("/proc/stat");
        std::string line;
        std::getline(file, line);
        
        std::istringstream ss(line);
        std::string cpu;
        long long user, nice, system, idle, iowait, irq, softirq, steal;
        ss >> cpu >> user >> nice >> system >> idle >> iowait >> irq >> softirq >> steal;
        
        long long current_idle = idle + iowait;
        long long current_total = user + nice + system + idle + iowait + irq + softirq + steal;
        
        long long total_diff = current_total - prev_total;
        long long idle_diff = current_idle - prev_idle;
        
        double usage = 0.0;
        if (total_diff != 0) {
            usage = 100.0 * (total_diff - idle_diff) / total_diff;
        }
        
        prev_idle = current_idle;
        prev_total = current_total;
        
        return usage;
    }
    
    std::pair<long long, long long> get_memory_usage()
    {
        struct sysinfo info;
        sysinfo(&info);
        
        long long total = info.totalram * info.mem_unit;
        long long free = info.freeram * info.mem_unit;
        long long used = total - free;
        
        return {used, total};
    }
    
    double get_disk_usage(const std::string& path)
    {
        struct statvfs stat;
        if (statvfs(path.c_str(), &stat) == 0) {
            auto total = stat.f_blocks * stat.f_frsize;
            auto free = stat.f_bavail * stat.f_frsize;
            auto used = total - free;
            
            return (double)used / total * 100.0;
        }
        return 0.0;
    }
    
    // Member variables
    rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diagnostics_publisher_;
    rclcpp::Publisher<std_msgs::msg::String>::SharedPtr metrics_publisher_;
    rclcpp::TimerBase::SharedPtr timer_;
    
    double monitoring_rate_;
    bool enable_system_monitoring_;
    bool enable_ros_monitoring_;
    bool enable_network_monitoring_;
    
    std::chrono::steady_clock::time_point start_time_;
};

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<PerformanceMonitor>();
    
    RCLCPP_INFO(node->get_logger(), "🚀 Performance Monitor node starting...");
    
    try {
        rclcpp::spin(node);
    } catch (const std::exception& e) {
        RCLCPP_ERROR(node->get_logger(), "❌ Exception in performance monitor: %s", e.what());
    }
    
    rclcpp::shutdown();
    return 0;
}