# API Documentation Generation Guide

## Overview

This project uses Doxygen to auto-generate API documentation from code comments. The documentation includes class hierarchies, call graphs, dependency diagrams, and detailed function/class descriptions.

## Prerequisites

```bash
sudo apt-get install doxygen graphviz
```

## Generating Documentation

### Local Generation

Generate documentation locally:

```bash
cd /home/uday/Downloads/pragati_ros2
doxygen Doxyfile
```

Output will be in `docs/api/html/`. Open `docs/api/html/index.html` in your browser.

### CI/CD Generation

Documentation is automatically generated on every push via GitHub Actions (see `.github/workflows/ci.yml`).

## Documentation Standards

### C++ Header Comments

```cpp
/**
 * @brief Brief description of the class
 * 
 * Detailed description providing context about the class purpose,
 * usage patterns, and important considerations.
 * 
 * @example
 * ```cpp
 * MotorController controller;
 * controller.initialize(config);
 * controller.set_position(1.5);
 * ```
 */
class MotorController
{
public:
    /**
     * @brief Initialize the motor controller
     * 
     * @param config Motor configuration parameters
     * @param can_interface Shared CAN interface pointer
     * @return true if initialization succeeded, false otherwise
     * 
     * @throws std::runtime_error if CAN interface is null
     */
    bool initialize(const MotorConfiguration& config,
                   std::shared_ptr<CANInterface> can_interface);
                   
    /**
     * @brief Set target position
     * 
     * @param position Target position in radians
     * @param velocity Optional feedforward velocity (default: 0.0)
     * @param torque Optional feedforward torque (default: 0.0)
     * @return true if command accepted, false if out of limits
     * 
     * @note Position is checked against configured safety limits
     * @warning Ensure motor is enabled before calling this function
     * @see set_enabled()
     */
    bool set_position(double position, double velocity = 0.0, double torque = 0.0);
    
private:
    //! CAN interface for motor communication
    std::shared_ptr<CANInterface> can_interface_;
    
    //! Current motor configuration
    MotorConfiguration config_;
};
```

### Python Docstrings

```python
class CottonDetector:
    """
    Cotton detection using YOLO deep learning model.
    
    This class provides real-time cotton detection from camera images,
    with configurable confidence thresholds and Non-Maximum Suppression.
    
    Attributes:
        model_path (str): Path to YOLO model weights
        confidence_threshold (float): Minimum confidence for detections (0-1)
        nms_threshold (float): IoU threshold for NMS (0-1)
    
    Example:
        >>> detector = CottonDetector('/path/to/model.onnx')
        >>> detections = detector.detect(image)
        >>> print(f"Found {len(detections)} cotton bolls")
    """
    
    def detect(self, image: np.ndarray) -> List[Detection]:
        """
        Detect cotton in the provided image.
        
        Args:
            image: Input image as numpy array (height, width, 3)
        
        Returns:
            List of Detection objects with bounding boxes and confidences
        
        Raises:
            ValueError: If image is empty or invalid format
            RuntimeError: If model not initialized
        
        Note:
            Image is automatically resized to model input size
        """
        pass
```

## Doxygen Special Commands

### Common Tags

- `@brief`: Short description (one line)
- `@param`: Parameter description
- `@return`: Return value description
- `@throws` / `@exception`: Exceptions that may be thrown
- `@note`: Additional notes
- `@warning`: Important warnings
- `@see`: Cross-reference to related items
- `@example`: Code example
- `@deprecated`: Mark deprecated functions
- `@todo`: Mark incomplete functionality

### Code Blocks

````markdown
```cpp
// C++ code example
```

```python
# Python code example
```
````

### Lists

```cpp
/**
 * @brief Process motor commands
 * 
 * Processing steps:
 * -# Validate input parameters
 * -# Apply safety limits
 * -# Send CAN message
 * -# Wait for acknowledgment
 */
```

### Links

```cpp
/**
 * @brief Motor controller
 * 
 * See @ref MotorConfiguration for configuration options
 * See @ref SafetyMonitor for safety features
 */
```

## Viewing Generated Documentation

### Locally

```bash
# Generate docs
doxygen Doxyfile

# Open in browser
xdg-open docs/api/html/index.html  # Linux
open docs/api/html/index.html      # macOS
start docs/api/html/index.html     # Windows
```

### From CI/CD

Documentation artifacts are published as part of the GitHub Actions workflow and can be downloaded from the Actions tab.

## Configuration

The Doxyfile is located at the project root. Key configuration options:

| Option | Value | Purpose |
|--------|-------|---------|
| `PROJECT_NAME` | "Pragati ROS2" | Project title |
| `OUTPUT_DIRECTORY` | docs/api | Output location |
| `RECURSIVE` | YES | Scan subdirectories |
| `EXTRACT_ALL` | YES | Document everything |
| `HAVE_DOT` | YES | Generate diagrams |
| `CALL_GRAPH` | YES | Function call graphs |
| `UML_LOOK` | YES | UML-style diagrams |

## Troubleshooting

### Missing Diagrams

Install graphviz:
```bash
sudo apt-get install graphviz
```

### Incomplete Documentation

Ensure `EXTRACT_ALL = YES` in Doxyfile to document even undocumented code.

### Build Failures

Check for:
- Invalid doxygen syntax in comments
- Missing closing comment markers
- Unsupported special characters

View warnings in doxygen output for details.

## Best Practices

1. **Document public APIs**: All public functions, classes, and important members
2. **Brief + detailed**: Use `@brief` for summaries, paragraphs for details
3. **Document parameters**: Every parameter should have `@param`
4. **Examples**: Include `@example` for complex functions
5. **Keep updated**: Update docs when changing function signatures
6. **Link related items**: Use `@see` to cross-reference
7. **Warn users**: Use `@warning` for dangerous operations
8. **Mark TODOs**: Use `@todo` for incomplete functionality

## Integration with IDE

### VS Code

Install "Doxygen Documentation Generator" extension for auto-completion.

### CLion / Qt Creator

Built-in Doxygen support - hover over functions to see docs.

## CI/CD Integration

Documentation is built automatically on every push. See `.github/workflows/ci.yml`:

```yaml
- name: Generate API Documentation
  run: |
    sudo apt-get install -y doxygen graphviz
    doxygen Doxyfile

- name: Upload Documentation
  uses: actions/upload-artifact@v3
  with:
    name: api-documentation
    path: docs/api/html
```

## Publishing

For public documentation hosting:

1. **GitHub Pages**: Push docs to `gh-pages` branch
2. **Read the Docs**: Configure `.readthedocs.yml`
3. **Doxygen Awesome**: Use modern CSS theme

## Additional Resources

- [Doxygen Manual](https://www.doxygen.nl/manual/)
- [Documenting C++ Code](https://www.doxygen.nl/manual/docblocks.html)
- [Doxygen Awesome CSS](https://jothepro.github.io/doxygen-awesome-css/)

---

**Last Updated:** 2025-10-21
