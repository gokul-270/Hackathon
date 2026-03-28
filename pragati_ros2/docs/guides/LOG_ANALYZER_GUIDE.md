# ROS2 Log Analyzer Tool

A comprehensive log analysis tool for Pragati robot ROS2 logs. Automatically parses log files, detects issues, extracts performance metrics, and provides actionable recommendations.

## Features

- **🔍 Issue Detection**: Automatically detects errors, warnings, and known issue patterns
- **📊 Performance Metrics**: Extracts timing data (FPS, detection time, latency)
- **🤖 Per-Node Statistics**: Shows health status of each ROS2 node
- **💡 Recommendations**: Provides actionable suggestions based on detected issues
- **📈 Visual Reports**: Color-coded terminal output with severity indicators
- **📄 JSON Export**: Machine-readable output for CI/CD integration

## Quick Start

```bash
# From workspace root
./analyze_logs.sh /path/to/log/directory

# Or directly with Python
python3 scripts/log_analyzer.py /path/to/log/directory
```

## Usage Examples

### Full Analysis (Default)
```bash
./analyze_logs.sh ~/Downloads/2025-12-18-09-03-56-102269-ubuntu-desktop-3541/
```

### Quick Summary Only
```bash
./analyze_logs.sh /path/to/logs --summary
```

### JSON Output (for scripting/CI)
```bash
./analyze_logs.sh /path/to/logs --json > analysis_report.json
```

### Save Report to File
```bash
./analyze_logs.sh /path/to/logs --output report.txt
```

### Watch Mode (Live Monitoring)
```bash
./analyze_logs.sh /path/to/logs --watch
```

## Understanding the Output

### Issue Severity Levels

| Icon | Severity | Description |
|------|----------|-------------|
| 🔴 | Critical | System crashes, OOM, device disconnections |
| 🟠 | High | Errors, timeouts, motor issues |
| 🟡 | Medium | Performance issues, USB 2.0, calibration |
| 🔵 | Low | Default parameters, deprecation warnings |
| ⚪ | Info | Informational (fallbacks, no detections) |

### Node Health Status

| Icon | Status |
|------|--------|
| ✅ | Healthy (no errors/warnings) |
| ⚠️ | Has warnings but no fatal errors |
| ❌ | Has fatal errors |

## Detected Issue Categories

The analyzer detects these issue categories:

- **crash**: Segmentation faults, core dumps
- **memory**: OOM, allocation failures
- **hardware**: Device disconnections, USB issues
- **communication**: Timeouts, message drops
- **motor**: CAN bus errors, motor failures
- **tf**: Transform lookup failures
- **performance**: Queue overflows, high latency
- **config**: Missing files, default parameters
- **thermal**: Temperature warnings
- **detection**: No detections, low confidence

## Performance Metrics Extracted

- `detection_time`: Time to run object detection (ms)
- `total_processing_time`: End-to-end processing time (ms)
- `frame_time`: Camera frame acquisition time (ms)
- `fps`: Frames per second
- `latency`: End-to-end latency (ms)
- `temperature`: Device temperature (°C)

## Integration with CI/CD

```yaml
# Example GitHub Actions / CI usage
- name: Analyze Test Logs
  run: |
    python3 scripts/log_analyzer.py ${{ github.workspace }}/test_logs --json > report.json
    
- name: Check for Critical Issues
  run: |
    if grep -q '"severity": "critical"' report.json; then
      echo "Critical issues found!"
      exit 1
    fi
```

## Extending the Analyzer

### Adding New Issue Patterns

Edit `log_analyzer.py` and add to `ISSUE_PATTERNS`:

```python
{
    'pattern': r'your regex pattern here',
    'severity': 'high',  # critical, high, medium, low, info
    'category': 'your_category',
    'title': 'Human Readable Title',
    'recommendation': 'What the user should do'
},
```

### Adding Performance Metrics

Edit `PERF_PATTERNS` to extract new metrics:

```python
(r'your_metric[:\s]*(\d+\.?\d*)\s*ms', 'metric_name'),
```

## Log File Locations

Common log directories:
- Launch logs: `~/.ros/log/<timestamp>-<hostname>-<pid>/`
- Downloaded logs: `~/Downloads/<timestamp>-*/`
- Test logs: `<workspace>/test_output/`

## Troubleshooting

### "No log files found"
- Check the path is correct
- Ensure files have `.log` extension
- Try passing a specific log file instead of directory

### Slow analysis
- Large logs (>100MB) may take time
- Use `--summary` for quick results
- Consider filtering logs before analysis

## Requirements

- Python 3.8+
- No external dependencies (uses standard library only)

## Future Improvements

- [ ] HTML report generation
- [ ] Trend analysis over multiple runs
- [ ] Integration with Grafana/Prometheus
- [ ] Anomaly detection using ML
- [ ] Email/Slack alerts for critical issues
