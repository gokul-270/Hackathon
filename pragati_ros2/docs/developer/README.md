# Developer Resources

This directory contains resources for developers working on Pragati ROS2.

## Contents

### cpp_templates/

C++ code templates demonstrating ROS2 best practices:

- **cpp_publisher_example.cpp** - Publisher patterns with QoS configuration
- **cpp_subscriber_example.cpp** - Subscriber patterns with error handling
- **cpp_service_client_example.cpp** - Service client patterns with timeouts

**Purpose:** Reference implementations for common ROS2 patterns  
**Audience:** C++ developers writing new nodes or packages

**Usage:**
```bash
# Copy template and modify for your use case
cp docs/developer/cpp_templates/cpp_publisher_example.cpp src/my_package/src/
```

---

## Related Documentation

- **User Examples:** [../examples/](../../examples/) - Runnable Python examples for operators
- **API Documentation:** [../api/](../api/) - Generated API docs (if available)
- **Guides:** [../guides/](../guides/) - Step-by-step tutorials
- **Architecture:** [../architecture/](../architecture/) - System design documents

---

## Contributing

When adding developer resources:

1. Keep templates generic and reusable
2. Document all patterns and best practices
3. Include usage examples in comments
4. Test templates before committing
5. Update this README with new additions

---

**Last Updated:** 2025-10-21  
**Maintainer:** Development Team
