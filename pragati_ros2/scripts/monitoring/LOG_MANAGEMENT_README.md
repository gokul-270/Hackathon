# Log Management Tools

## Available Tools

### 1. cleanup_logs.sh (Standalone)
**Use when**: You want a simple, no-dependency cleanup
**Features**:
- Comprehensive multi-phase cleanup
- Age-based retention (validation: 7 days, build: 3 days, ROS: 2 days)
- Archive to logs_archive/ directory
- No Python dependencies

**Usage**:
```bash
./scripts/monitoring/cleanup_logs.sh
```

### 2. clean_logs.sh (Advanced)
**Use when**: You need advanced features and reporting
**Features**:
- Wrapper around log_manager.py (Python backend)
- Status reporting
- Dry-run mode
- Custom retention policies
- Emergency cleanup mode

**Usage**:
```bash
# Show status
./scripts/monitoring/clean_logs.sh status

# Standard cleanup
./scripts/monitoring/clean_logs.sh clean

# Quick cleanup (3 days, 50MB limit)
./scripts/monitoring/clean_logs.sh quick-clean

# Dry-run to see what would be cleaned
./scripts/monitoring/clean_logs.sh dry-run

# Emergency cleanup (1 day retention)
./scripts/monitoring/clean_logs.sh emergency --force
```

### 3. log_manager.py (Backend)
Python module used by clean_logs.sh. Can be imported for custom log management.

## Recommendation

- **Daily use**: `cleanup_logs.sh` (simple, fast)
- **Detailed analysis**: `clean_logs.sh status`
- **Custom needs**: `clean_logs.sh` with options

## Configuration

Edit retention policies in the scripts:
- `cleanup_logs.sh`: Lines 34-37
- `clean_logs.sh`: Uses --days and --size flags

