# Script Organization Guidelines

## ⚠️ DO NOT Add Scripts to Root Directory

The root directory should **only** contain essential operational scripts. All other scripts must be organized by purpose.

## ✅ Allowed Root Scripts (Whitelisted)

Only these scripts are permitted in the root directory:

```
pragati_ros2/
├── build.sh                  # Main workspace build
├── build_rpi.sh              # Raspberry Pi build
├── launch_all.sh             # Launch complete system
├── stop_all.sh               # Stop all nodes
├── emergency_motor_stop.sh   # Safety: Emergency motor stop
├── capture_and_view.sh       # Quick camera view
└── capture_view.sh           # Direct camera capture
```

**Rationale**: These are frequently-used operational commands that need quick access.

---

## Where to Place New Scripts

### 🧪 Testing Scripts

#### Integration Tests → `scripts/testing/integration/`
For tests that validate the complete system (detection + motors + control):
- Full pipeline tests
- Automated cycle tests
- End-to-end workflows

#### Detection Tests → `scripts/testing/detection/`
For cotton detection, camera, and vision-related tests:
- Single detection tests
- Latency measurements
- Camera diagnostics
- Offline image tests

#### Motor Tests → `scripts/testing/motor/`
For motor controller and movement tests:
- Motor communication tests
- Position command tests
- Motor diagnostics

#### Stress & Performance Tests → `scripts/testing/stress/`
For endurance, thermal, and performance testing:
- Thermal monitoring
- Long-duration tests
- Load tests

---

### 🛠️ Utility Scripts → `scripts/utils/`
For diagnostic, monitoring, and helper utilities:
- Log analyzers
- Status checkers
- Monitors
- Debug helpers

---

### 📦 Deployment & Setup Scripts
- `scripts/deployment/` - For RPI sync, deployment, verification
- `scripts/setup/` - For dependency installation, environment setup

---

## Git Pre-Commit Hook (Automatic Enforcement)

A pre-commit hook is installed that **automatically blocks** commits that add new scripts to root:

```bash
# If you try to add a script to root:
git add my_new_test.sh
git commit -m "Add test"

# Output:
❌ COMMIT BLOCKED: New script(s) in root directory

The following scripts should NOT be added to root:
  • my_new_test.sh

📂 Please place scripts in appropriate directories:
   • Integration tests:    scripts/testing/integration/
   • Detection tests:      scripts/testing/detection/
   ...
```

---

## Quick Decision Tree

```
New script to add?
│
├─ Is it for daily operations? (build/launch/stop)
│  └─ YES → Add to root (requires approval & whitelist update)
│
├─ Is it a test?
│  ├─ Full system integration? → scripts/testing/integration/
│  ├─ Detection/camera related? → scripts/testing/detection/
│  ├─ Motor related? → scripts/testing/motor/
│  └─ Stress/performance? → scripts/testing/stress/
│
├─ Is it a utility/diagnostic?
│  └─ scripts/utils/
│
└─ Is it for deployment/setup?
   └─ scripts/deployment/ or scripts/setup/
```

---

## Naming Conventions

### Test Scripts
- Descriptive: `test_feature_name.sh` or `feature_test.sh`
- Python: `test_feature.py` or `feature_test.py`

### Utility Scripts
- Action-oriented: `check_system.sh`, `analyze_logs.sh`
- Avoid generic: `util.sh`, `helper.sh`

### Deployment Scripts
- Prefix with target: `rpi_deploy_feature.sh`
- Or action: `sync.sh`, `setup_raspberry_pi.sh`

---

## Adding to Root Whitelist (Rare)

If you have a **legitimate operational script** that must be in root:

1. **Justify** why it can't go in `scripts/`
2. **Update** `.git/hooks/pre-commit` whitelist:
   ```bash
   ALLOWED_ROOT_SCRIPTS=(
       "build.sh"
       "launch_all.sh"
       # ... existing ...
       "your_new_script.sh"  # Add here with comment
   )
   ```
3. **Document** in this file
4. **Get approval** from team
5. **Commit** hook change with your script

---

## Testing Your Placement

```bash
# Verify structure
tree scripts/

# Test hook (should block)
touch test_bad.sh
git add test_bad.sh
git commit -m "test"  # Blocked ✅

# Correct placement
git reset HEAD test_bad.sh
mv test_bad.sh scripts/testing/integration/
git add scripts/testing/integration/test_bad.sh
git commit -m "Add integration test"  # Succeeds ✅
```

---

## References

- See `CLEANUP_PLAN.md` for organization rationale
- See `scripts/testing/QUICK_REFERENCE.md` for existing commands
- Hook location: `.git/hooks/pre-commit`

---

## Summary

**Rule**: 
- **Daily operations** → Root (with approval)
- **Everything else** → Organized in `scripts/`

This keeps the workspace clean! 🎯
