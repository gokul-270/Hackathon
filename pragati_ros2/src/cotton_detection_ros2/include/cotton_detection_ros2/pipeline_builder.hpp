#pragma once

#include <optional>
#include <string>

#include "cotton_detection_ros2/camera_config.hpp"

// Forward-declare DepthAI Pipeline to avoid exposing full SDK in callers that
// only need validation.  The build() return type uses dai::Pipeline by value,
// so the full include is in the .cpp file; callers that only validate can skip it.
namespace dai {
class Pipeline;
}  // namespace dai

namespace cotton_detection {

/// Result of PipelineBuilder::validate().
struct ValidationResult {
    bool valid{true};
    std::string messages;  ///< Accumulated errors and warnings.
};

/// Stateless factory for DepthAI pipeline construction (D4).
///
/// All state comes from function parameters — the class has zero mutable
/// members.  `build()` and `validate()` are const methods on a stateless
/// object, enabling safe concurrent use and trivial testability.
class PipelineBuilder {
public:
    /// Validate a CameraConfig + model path before pipeline construction.
    /// Returns a ValidationResult with accumulated errors/warnings.
    ValidationResult validate(const CameraConfig& config,
                              const std::string& model_path) const;

    /// Build a `dai::Pipeline` from the given config and model path.
    /// Calls validate() internally; returns std::nullopt on validation failure.
    /// On success, returns a fully-configured pipeline ready for device upload.
    std::optional<dai::Pipeline> build(const CameraConfig& config,
                                       const std::string& model_path) const;
};

}  // namespace cotton_detection
