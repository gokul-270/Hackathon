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

#pragma once

#include <chrono>
#include <cstdint>
#include <geometry_msgs/msg/point.hpp>

namespace yanthra_move { namespace core {

/**
 * @brief Cotton detection data with confidence and timing metadata
 *
 * Carries per-detection information from the vision pipeline through to
 * motion execution and structured JSON logging.
 */
struct CottonDetection {
    geometry_msgs::msg::Point position;
    float confidence = 0.0f;
    int detection_id = -1;
    std::chrono::steady_clock::time_point detection_time;
    int64_t processing_time_ms = 0;
};

}}  // namespace yanthra_move::core
