# Launch Scripts Guide

## Quick Decision Tree

**Choose your launcher based on your needs:**

### For Development
→ Use `launch.sh` (interactive mode selection)

### For Production
→ Use `launch_production.sh` (error handling, health monitoring)

### For Testing
→ Use `launch_minimal.sh` (lightweight, fast startup)

### For Debugging Issues
→ Use `launch_robust.sh` (anti-hang protection, timeouts)

### For Full System Exploration
→ Use `launch_full_system.sh` (includes LazyROS)

### For Complete System with Monitoring
→ Use `launch_complete_system.sh` (detailed status, verification)

---

## Detailed Comparison

| Feature | launch.sh | complete | full | production | robust | minimal |
|---------|-----------|----------|------|------------|--------|---------|
| Interactive | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Simulation | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| RMW Config | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ |
| Health Monitor | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ |
| LazyROS | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ |
| Timeout Protection | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ |
| Error Recovery | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| Status Verification | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## Usage Examples

### Interactive Development
```bash
./scripts/launch/launch.sh
# Choose mode interactively
```

### Production Deployment
```bash
./scripts/launch/launch_production.sh
# Production-grade error handling
# Health monitoring every 15s
# Graceful shutdown handling
```

### Quick Testing
```bash
./scripts/launch/launch_minimal.sh
# Minimal system
# Fast startup
# Good for unit testing
```

### Debugging Hangs
```bash
./scripts/launch/launch_robust.sh
# Timeouts on all operations
# Progressive node startup
# Anti-hang protection
```

### System Exploration
```bash
./scripts/launch/launch_full_system.sh
# Launches LazyROS for exploration
# Full system introspection
```

### Complete System Launch
```bash
./scripts/launch/launch_complete_system.sh
# Detailed node monitoring
# Service verification
# Complete status reporting
```

---

## Environment Variables

### RMW Selection
```bash
# CycloneDDS (required - all launchers use this)
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
# Shared memory must be disabled on RPi 4B/ARM64 (iceoryx broken)
export CYCLONEDDS_URI="file:///path/to/config/cyclonedds.xml"
```

### Simulation Mode
```bash
# Used by launch.sh
use_simulation:=true
```

---

## Troubleshooting

**Problem**: System hangs on startup
**Solution**: Use `launch_robust.sh` or `launch_minimal.sh`

**Problem**: Need to debug node communication
**Solution**: Use `launch_full_system.sh` with LazyROS

**Problem**: Production deployment
**Solution**: Use `launch_production.sh` with proper environment

**Problem**: RCL/RMW errors
**Solution**: Use `launch_production.sh` (has cleanup handling)

---

## When to Use Each

- **launch.sh**: Daily development, quick tests
- **launch_production.sh**: Production servers, critical systems
- **launch_complete_system.sh**: Integration testing, verification
- **launch_full_system.sh**: System exploration, debugging
- **launch_robust.sh**: Systems with known hang issues
- **launch_minimal.sh**: Unit testing, CI/CD pipelines

