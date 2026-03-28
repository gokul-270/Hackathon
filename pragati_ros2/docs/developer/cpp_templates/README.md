# C++ Templates - ROS2 Best Practices

Reference implementations demonstrating ROS2 C++ patterns used in Pragati.

## Templates

### cpp_publisher_example.cpp

**Purpose:** Publisher node with optimized message handling

**Demonstrates:**
- QoS configuration (reliable vs best-effort)
- Parameter-based configuration
- High-frequency publishing (100+ Hz)
- Pre-allocated messages for real-time performance
- Rate limiting and timing control

**Use Cases:**
- Sensor data publishing
- Joint state broadcasting
- Status updates

---

### cpp_subscriber_example.cpp

**Purpose:** Subscriber node with robust message handling

**Demonstrates:**
- Type-safe callback handling
- QoS matching with publishers
- Message buffering strategies
- Lifecycle management
- Performance monitoring

**Use Cases:**
- Sensor data processing
- Command reception
- State monitoring

---

### cpp_service_client_example.cpp

**Purpose:** Service client with error handling

**Demonstrates:**
- Synchronous and asynchronous service calls
- Timeout handling
- Connection monitoring
- Retry logic
- Error recovery patterns

**Use Cases:**
- Request/response interactions
- Configuration changes
- Remote procedure calls

---

## Usage

### Copy and Customize

```bash
# Copy template to your package
cp docs/developer/cpp_templates/cpp_publisher_example.cpp \
   src/my_package/src/my_node.cpp

# Modify for your needs:
# 1. Change class name
# 2. Update message types
# 3. Adjust QoS settings
# 4. Add custom logic
```

### Integration into CMakeLists.txt

```cmake
add_executable(my_node src/my_node.cpp)
ament_target_dependencies(my_node
  rclcpp
  std_msgs
  sensor_msgs
)
install(TARGETS my_node
  DESTINATION lib/${PROJECT_NAME}
)
```

---

## Best Practices

### QoS Selection

- **Real-time data:** `best_effort()` with small queue (1-5)
- **Commands:** `reliable()` with moderate queue (10)
- **Persistent state:** `transient_local()` durability

### Memory Management

- Pre-allocate messages in constructors
- Reuse message objects in hot loops
- Use `std::move()` for large messages

### Error Handling

- Always check service availability before calling
- Implement timeouts for blocking operations
- Log errors at appropriate levels

### Performance

- Profile publishing rates with `ros2 topic hz`
- Monitor CPU usage with `top` or `htop`
- Use `best_effort` QoS for high-frequency (>50Hz)

---

## Related Examples

- **User Examples:** [../../../examples/](../../../examples/) - Python examples for operators
- **Motor Control:** [../../../src/motor_control_ros2/](../../../src/motor_control_ros2/) - Production implementation
- **Cotton Detection:** [../../../src/cotton_detection_ros2/](../../../src/cotton_detection_ros2/) - Computer vision node

---

## References

- [ROS2 C++ Client Library](https://docs.ros.org/en/rolling/Tutorials/Beginner-Client-Libraries/Writing-A-Simple-Cpp-Publisher-And-Subscriber.html)
- [ROS2 QoS](https://docs.ros.org/en/rolling/Concepts/About-Quality-of-Service-Settings.html)
- [rclcpp API Docs](http://docs.ros2.org/latest/api/rclcpp/)

---

**Last Updated:** 2025-10-21  
**Status:** Reference templates - not compiled as standalone
