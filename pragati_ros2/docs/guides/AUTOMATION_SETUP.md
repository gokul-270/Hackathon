# Automation Setup Guide
## Pragati ROS2

This guide explains how to set up automated tasks for the pragati_ros2 project.

---

## 📋 Table of Contents

1. [CI/CD Pipeline Setup](#cicd-pipeline-setup)
2. [Cron Jobs for Log Management](#cron-jobs-for-log-management)
3. [Git Hooks](#git-hooks)
4. [Linting Configuration](#linting-configuration)

---

## 🔄 CI/CD Pipeline Setup

### GitHub Actions

A CI/CD template has been created at `.github/workflows/pragati_ci.yml.template`.

**To enable:**

```bash
# Create .github/workflows directory
mkdir -p .github/workflows

# Copy and activate the template
cp .github/workflows/pragati_ci.yml.template .github/workflows/pragati_ci.yml

# Commit and push
git add .github/workflows/pragati_ci.yml
git commit -m "ci: Enable CI/CD pipeline"
git push
```

**What it does:**
- ✅ Lints all shell and Python scripts
- ✅ Builds the workspace
- ✅ Runs quick tests
- ✅ Tests package-specific builds
- ✅ Validates launch in simulation
- ✅ Reports log status

### GitLab CI

Create `.gitlab-ci.yml`:

```yaml
stages:
  - lint
  - build
  - test

lint_scripts:
  stage: lint
  script:
    - apt-get update && apt-get install -y shellcheck
    - find . -name "*.sh" -not -path "./archive/*" | xargs shellcheck -x || true
    - pip install black flake8
    - find scripts/ -name "*.py" | xargs black --check || true

build_workspace:
  stage: build
  script:
    - source /opt/ros/jazzy/setup.bash
    - ./install_deps.sh
    - ./build.sh --jobs 4

test_system:
  stage: test
  dependencies:
    - build_workspace
  script:
    - source install/setup.bash
    - ./test.sh --quick
```

---

## ⏰ Cron Jobs for Log Management

### Daily Log Cleanup

**Setup automatic daily log cleanup at 2 AM:**

```bash
# Edit crontab
crontab -e

# Add this line:
0 2 * * * cd /home/uday/Downloads/pragati_ros2 && ./scripts/monitoring/clean_logs.sh clean --days 7 --force >> /home/uday/Downloads/pragati_ros2/logs/cron_cleanup.log 2>&1
```

### Weekly Comprehensive Cleanup

```bash
# Edit crontab
crontab -e

# Add this line (Sundays at 3 AM):
0 3 * * 0 cd /home/uday/Downloads/pragati_ros2 && ./scripts/monitoring/cleanup_logs.sh >> /home/uday/Downloads/pragati_ros2/logs/weekly_cleanup.log 2>&1
```

### Log Rotation

```bash
# Edit crontab
crontab -e

# Add this line (daily at 1 AM):
0 1 * * * cd /home/uday/Downloads/pragati_ros2 && ./scripts/monitoring/rotate_logs.sh >> /home/uday/Downloads/pragati_ros2/logs/rotation.log 2>&1
```

### Complete Cron Setup

Create `setup_cron.sh`:

```bash
#!/bin/bash

WORKSPACE="/home/uday/Downloads/pragati_ros2"

# Create cron entries
(crontab -l 2>/dev/null; cat <<EOF
# Pragati ROS2 Automated Tasks
# Log rotation (daily 1 AM)
0 1 * * * cd $WORKSPACE && ./scripts/monitoring/rotate_logs.sh >> $WORKSPACE/logs/rotation.log 2>&1

# Log cleanup (daily 2 AM)
0 2 * * * cd $WORKSPACE && ./scripts/monitoring/clean_logs.sh clean --days 7 --force >> $WORKSPACE/logs/cron_cleanup.log 2>&1

# Comprehensive cleanup (weekly Sunday 3 AM)
0 3 * * 0 cd $WORKSPACE && ./scripts/monitoring/cleanup_logs.sh >> $WORKSPACE/logs/weekly_cleanup.log 2>&1
EOF
) | crontab -

echo "✅ Cron jobs installed"
crontab -l
```

**Run it:**

```bash
chmod +x setup_cron.sh
./setup_cron.sh
```

---

## 🪝 Git Hooks

### Pre-commit Hook (Linting)

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash

echo "🔍 Running pre-commit checks..."

# Check shell scripts
echo "Checking shell scripts..."
if command -v shellcheck &> /dev/null; then
    changed_sh=$(git diff --cached --name-only --diff-filter=ACM | grep '\.sh$')
    if [ -n "$changed_sh" ]; then
        echo "$changed_sh" | xargs shellcheck -x || {
            echo "❌ Shellcheck failed!"
            exit 1
        }
    fi
else
    echo "⚠️  shellcheck not installed, skipping"
fi

# Check Python scripts
echo "Checking Python scripts..."
if command -v black &> /dev/null; then
    changed_py=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$')
    if [ -n "$changed_py" ]; then
        echo "$changed_py" | xargs black --check || {
            echo "❌ Black formatting check failed!"
            echo "💡 Run: black <file> to fix"
            exit 1
        }
    fi
else
    echo "⚠️  black not installed, skipping"
fi

echo "✅ Pre-commit checks passed"
```

**Enable it:**

```bash
chmod +x .git/hooks/pre-commit
```

### Pre-push Hook (Build Test)

Create `.git/hooks/pre-push`:

```bash
#!/bin/bash

echo "🧪 Running pre-push checks..."

# Quick build test
echo "Testing build..."
if ! ./build.sh --package yanthra_move; then
    echo "❌ Build test failed!"
    echo "💡 Fix build issues before pushing"
    exit 1
fi

echo "✅ Pre-push checks passed"
```

**Enable it:**

```bash
chmod +x .git/hooks/pre-push
```

---

## 🧹 Linting Configuration

### ShellCheck Configuration

Create `.shellcheckrc`:

```bash
# Pragati ROS2 ShellCheck configuration

# Exclude rules
disable=SC1090  # Can't follow non-constant source
disable=SC1091  # Not following sourced file
disable=SC2034  # Variable appears unused
disable=SC2154  # Variable referenced but not assigned

# Enable additional checks
enable=all
```

### Black Configuration

Create `pyproject.toml`:

```toml
[tool.black]
line-length = 120
target-version = ['py310']
include = '\.pyi?$'
extend-exclude = '''
/(
  # directories
  \.eggs
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | build
  | dist
  | archive
)/
'''
```

### Flake8 Configuration

Create `.flake8`:

```ini
[flake8]
max-line-length = 120
exclude = 
    .git,
    __pycache__,
    build,
    install,
    archive,
    .venv
ignore = E203, W503
per-file-ignores =
    __init__.py:F401
```

### Install Linters

```bash
# Shell linter
sudo apt install shellcheck

# Python linters
pip3 install black flake8 pylint

# Optional: shfmt for shell formatting
sudo snap install shfmt
```

---

## 🔧 Systemd Timers (Alternative to Cron)

For more robust scheduling, use systemd timers.

### Create Service

Create `/etc/systemd/system/pragati-log-cleanup.service`:

```ini
[Unit]
Description=Pragati ROS2 Log Cleanup
After=network.target

[Service]
Type=oneshot
User=uday
WorkingDirectory=/home/uday/Downloads/pragati_ros2
ExecStart=/home/uday/Downloads/pragati_ros2/scripts/monitoring/clean_logs.sh clean --days 7 --force
StandardOutput=append:/home/uday/Downloads/pragati_ros2/logs/systemd_cleanup.log
StandardError=append:/home/uday/Downloads/pragati_ros2/logs/systemd_cleanup.log
```

### Create Timer

Create `/etc/systemd/system/pragati-log-cleanup.timer`:

```ini
[Unit]
Description=Daily Pragati ROS2 Log Cleanup
Requires=pragati-log-cleanup.service

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

### Enable Timer

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable and start the timer
sudo systemctl enable pragati-log-cleanup.timer
sudo systemctl start pragati-log-cleanup.timer

# Check status
sudo systemctl status pragati-log-cleanup.timer

# List all timers
systemctl list-timers
```

---

## 📊 Monitoring & Notifications

### Email Notifications

Add to cron jobs:

```bash
# With email notification on failure
0 2 * * * cd $WORKSPACE && ./scripts/monitoring/clean_logs.sh clean --days 7 --force || echo "Log cleanup failed" | mail -s "Pragati Log Cleanup Failed" your-email@example.com
```

### Slack/Discord Webhooks

Create `notify.sh`:

```bash
#!/bin/bash

WEBHOOK_URL="your-webhook-url-here"
MESSAGE="$1"

curl -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"Pragati ROS2: $MESSAGE\"}" \
    "$WEBHOOK_URL"
```

Use in cron:

```bash
0 2 * * * cd $WORKSPACE && ./scripts/monitoring/clean_logs.sh clean --days 7 --force && ./notify.sh "✅ Log cleanup completed" || ./notify.sh "❌ Log cleanup failed"
```

---

## ✅ Quick Setup Checklist

- [ ] Copy CI/CD template to `.github/workflows/pragati_ci.yml`
- [ ] Install linters: `sudo apt install shellcheck && pip3 install black flake8`
- [ ] Create `.shellcheckrc`, `pyproject.toml`, `.flake8`
- [ ] Set up git hooks in `.git/hooks/`
- [ ] Configure cron jobs for log management
- [ ] Test automation: `./build.sh --fast && ./test.sh --quick`
- [ ] Monitor logs: `tail -f logs/cron_cleanup.log`

---

## 📝 Testing Automation

### Test CI/CD Locally

```bash
# Install act (GitHub Actions local runner)
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Run workflows locally
act -l  # List workflows
act push  # Run push workflow
```

### Test Cron Jobs Manually

```bash
# Test log cleanup
./scripts/monitoring/clean_logs.sh clean --days 7 --force

# Check cron logs
tail -f logs/cron_cleanup.log

# Verify cron is running
systemctl status cron
```

### Test Git Hooks

```bash
# Test pre-commit
.git/hooks/pre-commit

# Test pre-push
.git/hooks/pre-push
```

---

## 🔗 Integration with Existing Scripts

All automation uses the consolidated scripts:
- **Build**: `./build.sh` with new flags
- **Test**: `./test.sh --quick` or `--complete`
- **Launch**: `./scripts/launch/launch_minimal.sh` (for CI)
- **Logs**: `./scripts/monitoring/clean_logs.sh` or `cleanup_logs.sh`
- **Validation**: `./scripts/validation/quick_validation.sh`

---

## 📚 Additional Resources

- **CI/CD Template**: `.github/workflows/pragati_ci.yml.template`
- **Scripts Guide**: `SCRIPTS_GUIDE.md`
- **Quick Reference**: `QUICK_REFERENCE.md`
- **Log Management**: `scripts/monitoring/LOG_MANAGEMENT_README.md`

---

**Status**: ✅ Ready to implement  
**Last Updated**: 2025-09-30