# Migration Notice: deploy_to_rpi.sh → sync.sh

**Date:** 2026-02-03  
**Status:** COMPLETED  
**Impact:** Low - Simple command replacement

---

## Summary

The redundant `scripts/deployment/deploy_to_rpi.sh` has been **removed** to simplify the deployment workflow. All deployment operations should now use the unified `sync.sh` script.

---

## What Changed

### Before (Old Way - DEPRECATED)
```bash
# Old deployment script (REMOVED)
./scripts/deployment/deploy_to_rpi.sh
./scripts/deployment/deploy_to_rpi.sh --build
./scripts/deployment/deploy_to_rpi.sh --clean --build
```

### After (New Way - CURRENT)
```bash
# Unified deployment script (USE THIS)
./sync.sh --build
./sync.sh --all --build
./sync.sh --deploy-cross  # For cross-compiled binaries
```

---

## Why This Change?

### Problem
- **Confusion:** Two deployment scripts (`deploy_to_rpi.sh` and `sync.sh`) doing similar things
- **Duplication:** Maintenance burden - updates needed in two places
- **Inconsistency:** Team members using different workflows

### Solution
- **Single tool:** `sync.sh` handles all deployment scenarios
- **More features:** Multi-target, cross-compile support, better options
- **Clearer workflow:** One obvious way to deploy

---

## Migration Guide

### For Development Teams

If you were using `deploy_to_rpi.sh`, here's the mapping:

| Old Command | New Command | Notes |
|-------------|-------------|-------|
| `./scripts/deployment/deploy_to_rpi.sh` | `./sync.sh` | Deploy source code |
| `./scripts/deployment/deploy_to_rpi.sh --build` | `./sync.sh --build` | Deploy + build on RPi |
| `./scripts/deployment/deploy_to_rpi.sh --clean --build` | `./sync.sh --all --build` | Full sync + build |
| N/A | `./sync.sh --deploy-cross` | Deploy pre-compiled binaries |
| N/A | `./sync.sh --all-arms --build` | Deploy to multiple RPis |

### First Time Setup

```bash
# Configure your RPi target (one time only)
./sync.sh --ip 192.168.137.253 --user ubuntu --save

# Now just use:
./sync.sh --build
```

### For Scripts/Automation

If you have scripts or CI/CD that referenced `deploy_to_rpi.sh`, update them:

```bash
# OLD (won't work)
bash scripts/deployment/deploy_to_rpi.sh

# NEW
./sync.sh --build
```

---

## Updated Documentation

The following documentation files have been updated:

1. ✅ `scripts/testing/QUICK_REFERENCE.md` - Updated deployment section
2. ✅ `docs/project-notes/RPI_INSTALLATION_VALIDATION_CHECKLIST.md` - Updated script execution order
3. ✅ `docs/project-notes/CLEANUP_PLAN.md` - Removed old script reference
4. ✅ `docs/project-notes/SCRIPT_GUIDELINES.md` - Updated examples
5. ✅ `docs/archive/2025-10-30-pre-breakthrough/DEPLOYMENT_QUICK_START.md` - Updated for historical reference

---

## Benefits of sync.sh

The unified `sync.sh` provides:

### ✅ **Better Features**
- Multi-target deployment (`--all-arms`)
- Named targets (`--target arm1`)
- Cross-compilation support (`--deploy-cross`)
- Dry-run mode (`--dry-run`)
- Verbose logging (`--verbose`)

### ✅ **Flexible Workflows**
```bash
# Quick code sync (fastest)
./sync.sh

# Sync + build on RPi
./sync.sh --build

# Cross-compile on PC + deploy (fastest builds)
./build.sh rpi
./sync.sh --deploy-cross

# Deploy to all RPis at once
./sync.sh --all-arms --build
```

### ✅ **Better Configuration**
- Saved targets in `~/.pragati_sync.conf`
- No more environment variables
- Easy multi-device management

---

## Need Help?

### Common Issues

**Q: "I get 'command not found' for deploy_to_rpi.sh"**  
A: This is expected - the script was removed. Use `./sync.sh --build` instead.

**Q: "How do I set my RPi IP?"**  
A: Run `./sync.sh --ip <your-rpi-ip> --save` once, then just use `./sync.sh`.

**Q: "Can I still use environment variables?"**  
A: Yes! `sync.sh` respects `RPI_IP` and `RPI_USER` environment variables.

**Q: "I have a custom deployment script that calls deploy_to_rpi.sh"**  
A: Update it to call `./sync.sh --build` instead. See migration table above.

### Documentation

- **Full sync.sh guide:** Run `./sync.sh --help`
- **Deployment guide:** `docs/guides/RASPBERRY_PI_DEPLOYMENT_GUIDE.md`
- **Quick reference:** `scripts/testing/QUICK_REFERENCE.md`
- **Getting started:** `docs/guides/GETTING_STARTED.md` (if exists)

### Support

- Check documentation: `docs/INDEX.md`
- Review examples: `./sync.sh --help`
- Ask team in #pragati-help Slack channel

---

## Technical Details

### What Was Removed

- **File:** `scripts/deployment/deploy_to_rpi.sh` (9.5KB, 200+ lines)
- **Reason:** Redundant functionality already in `sync.sh`
- **Replaced by:** `sync.sh` with enhanced features

### What sync.sh Does Better

1. **Multi-device support** - Deploy to 1 or many RPis
2. **Named targets** - Save devices with friendly names
3. **Cross-compile workflow** - Optimized build pipeline
4. **Better rsync control** - More granular sync options
5. **Dry-run mode** - Preview changes before deploying
6. **Build strategies** - Native vs cross-compile clearly documented

---

## Rollback (If Needed)

If you absolutely need the old script back temporarily:

```bash
# Retrieve from git history
git show HEAD~1:scripts/deployment/deploy_to_rpi.sh > /tmp/deploy_to_rpi.sh
chmod +x /tmp/deploy_to_rpi.sh
/tmp/deploy_to_rpi.sh
```

**But please update to `sync.sh` instead - it's the supported path forward.**

---

## Timeline

- **2026-02-03:** Script removed, documentation updated
- **2026-02-10:** (1 week) Check-in - any issues?
- **2026-02-17:** (2 weeks) Migration considered complete
- **2026-03-03:** (1 month) Remove this migration notice

---

## Feedback

If you encounter issues with this migration, please:
1. Check this document first
2. Try `./sync.sh --help`
3. Report issues to the team
4. Document any edge cases we missed

---

**Last Updated:** 2026-02-03  
**Maintained By:** Pragati Development Team
