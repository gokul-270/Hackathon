// Copyright 2025 Pragati Robotics
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include "yanthra_move/transform_cache.hpp"
#include <tf2/exceptions.h>

namespace yanthra_move {

TransformCache::TransformCache(
    std::shared_ptr<rclcpp::Node> node,
    std::shared_ptr<tf2_ros::Buffer> tf_buffer)
: node_(node), tf_buffer_(tf_buffer)
{
    RCLCPP_INFO(node_->get_logger(), 
                "🗺️  TransformCache initialized (Tier 1.3 - Static TF Optimization)");
}

geometry_msgs::msg::TransformStamped TransformCache::getTransform(
    const std::string& target_frame,
    const std::string& source_frame,
    const rclcpp::Duration& timeout)
{
    (void)timeout;  // Timeout not used for static transforms
    std::string cache_key = makeCacheKey(target_frame, source_frame);
    
    // Check cache first (with lock)
    {
        std::lock_guard<std::mutex> lock(cache_mutex_);
        
        auto it = cache_.find(cache_key);
        if (it != cache_.end()) {
            // Cache hit!
            cache_hits_++;
            RCLCPP_DEBUG(node_->get_logger(),
                        "✅ Cache HIT for %s → %s (total hits: %zu)",
                        target_frame.c_str(), source_frame.c_str(), cache_hits_);
            return it->second;
        }
    }
    
    // Cache miss - perform actual TF lookup
    RCLCPP_DEBUG(node_->get_logger(),
                "⏳ Cache MISS for %s → %s, performing TF lookup...",
                target_frame.c_str(), source_frame.c_str());
    
    geometry_msgs::msg::TransformStamped transform;
    
    try {
        // Lookup transform from TF2 buffer
        // Use tf2::TimePointZero for static transforms (get latest available)
        transform = tf_buffer_->lookupTransform(
            target_frame,
            source_frame,
            tf2::TimePointZero);
        
        // Cache the result (with lock)
        {
            std::lock_guard<std::mutex> lock(cache_mutex_);
            cache_[cache_key] = transform;
            cache_misses_++;
            
            RCLCPP_INFO(node_->get_logger(),
                       "💾 Cached transform %s → %s (cache size: %zu, hit rate: %.2f%%)",
                       target_frame.c_str(), source_frame.c_str(),
                       cache_.size(),
                       (cache_hits_ * 100.0) / (cache_hits_ + cache_misses_));
        }
        
        return transform;
        
    } catch (const tf2::TransformException& ex) {
        RCLCPP_ERROR(node_->get_logger(),
                    "❌ Failed to lookup transform %s → %s: %s",
                    target_frame.c_str(), source_frame.c_str(), ex.what());
        
        // Re-throw the exception
        throw;
    }
}

std::optional<geometry_msgs::msg::TransformStamped> TransformCache::getTransformSafe(
    const std::string& target_frame,
    const std::string& source_frame,
    const rclcpp::Duration& timeout)
{
    try {
        return getTransform(target_frame, source_frame, timeout);
    } catch (const tf2::TransformException& ex) {
        RCLCPP_WARN(node_->get_logger(),
                   "⚠️  getTransformSafe failed for %s → %s: %s",
                   target_frame.c_str(), source_frame.c_str(), ex.what());
        return std::nullopt;
    }
}

void TransformCache::clearCache()
{
    std::lock_guard<std::mutex> lock(cache_mutex_);
    
    size_t prev_size = cache_.size();
    cache_.clear();
    
    RCLCPP_INFO(node_->get_logger(),
               "🗑️  Cleared transform cache (removed %zu entries)", prev_size);
}

bool TransformCache::clearTransform(
    const std::string& target_frame,
    const std::string& source_frame)
{
    std::lock_guard<std::mutex> lock(cache_mutex_);
    
    std::string cache_key = makeCacheKey(target_frame, source_frame);
    auto it = cache_.find(cache_key);
    
    if (it != cache_.end()) {
        cache_.erase(it);
        RCLCPP_INFO(node_->get_logger(),
                   "🗑️  Removed cached transform %s → %s",
                   target_frame.c_str(), source_frame.c_str());
        return true;
    }
    
    return false;
}

void TransformCache::getStatistics(
    size_t& cache_hits,
    size_t& cache_misses,
    double& hit_rate) const
{
    std::lock_guard<std::mutex> lock(cache_mutex_);
    
    cache_hits = cache_hits_;
    cache_misses = cache_misses_;
    
    size_t total_requests = cache_hits_ + cache_misses_;
    hit_rate = (total_requests > 0) ? (cache_hits_ * 100.0) / total_requests : 0.0;
}

void TransformCache::printStatistics() const
{
    size_t hits, misses;
    double hit_rate;
    getStatistics(hits, misses, hit_rate);
    
    RCLCPP_INFO(node_->get_logger(),
               "📊 TransformCache Statistics:");
    RCLCPP_INFO(node_->get_logger(),
               "   Cache size: %zu transforms", getCacheSize());
    RCLCPP_INFO(node_->get_logger(),
               "   Cache hits: %zu", hits);
    RCLCPP_INFO(node_->get_logger(),
               "   Cache misses: %zu", misses);
    RCLCPP_INFO(node_->get_logger(),
               "   Hit rate: %.2f%%", hit_rate);
    
    if (hit_rate > 90.0) {
        RCLCPP_INFO(node_->get_logger(),
                   "   ✅ Excellent cache performance!");
    } else if (hit_rate > 70.0) {
        RCLCPP_INFO(node_->get_logger(),
                   "   ⚠️  Moderate cache performance");
    } else {
        RCLCPP_WARN(node_->get_logger(),
                   "   ❌ Low cache performance - consider caching more transforms");
    }
}

size_t TransformCache::getCacheSize() const
{
    std::lock_guard<std::mutex> lock(cache_mutex_);
    return cache_.size();
}

bool TransformCache::isCached(
    const std::string& target_frame,
    const std::string& source_frame) const
{
    std::lock_guard<std::mutex> lock(cache_mutex_);
    
    std::string cache_key = makeCacheKey(target_frame, source_frame);
    return cache_.find(cache_key) != cache_.end();
}

std::string TransformCache::makeCacheKey(
    const std::string& target_frame,
    const std::string& source_frame) const
{
    // Format: "target_frame->source_frame"
    return target_frame + "->" + source_frame;
}

}  // namespace yanthra_move
