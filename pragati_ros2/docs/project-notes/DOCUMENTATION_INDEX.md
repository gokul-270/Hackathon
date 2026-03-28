# CAN Auto-Recovery & Oscillator Detection - Documentation Index

**Last Updated:** 2025-11-09  
**Status:** ✅ Complete & Production Ready

---

## 📚 All Documentation Files

### **1. Main Technical Documentation** (32 KB)
**File:** `docs/guides/CAN_AUTO_RECOVERY.md`

**Contents:**
- ✅ Overview and problem description
- ✅ **Understanding CAN Error States** (NEW! 325+ lines)
  - All 6 states explained (ERROR-ACTIVE, WARNING, ERROR-PASSIVE, BUS-OFF, DOWN, MISSING)
  - State transition diagrams
  - Error counter behavior (TEC/REC)
  - Industry standards comparison
  - Watchdog coverage summary
- ✅ Solution architecture with diagrams
- ✅ Installation for PC and Raspberry Pi
- ✅ Configuration reference
- ✅ Usage and monitoring
- ✅ Raspberry Pi specifics
- ✅ Future C++ integration plans
- ✅ Technical details

**Who Should Read:** Everyone (comprehensive reference)

---

### **2. Quick Reference Summary** (18 KB)
**File:** `CAN_AUTO_RECOVERY_IMPLEMENTATION_SUMMARY.md`

**Contents:**
- ✅ What was implemented (file list)
- ✅ Quick start commands
- ✅ Key features summary
- ✅ Configuration examples
- ✅ **Oscillator Auto-Detection** (NEW!)
- ✅ **MCP2515 Clock Display Behavior** (NEW!)
- ✅ **Understanding CAN Error States (Education)** (NEW!)
  - Quick reference table
  - Simple explanations
  - Common causes & fixes
- ✅ **Optional: WARNING State Monitoring** (NEW!)
  - How to enable
  - When to use
  - Example scenarios
- ✅ Troubleshooting

**Who Should Read:** Quick reference during development/testing

---

### **3. File Locations Guide** (10 KB)
**File:** `CAN_IMPLEMENTATION_FILES.md`

**Contents:**
- ✅ File structure diagram
- ✅ Quick start commands
- ✅ Installed file locations
- ✅ Development file locations
- ✅ Verification commands
- ✅ Key features list
- ✅ Troubleshooting steps

**Who Should Read:** When looking for specific files

---

## 🔧 Implementation Files

### **4. Watchdog Script** (18 KB, ~570 lines)
**File:** `scripts/maintenance/can/can_watchdog.sh`

**Features:**
- ✅ Auto-recovery (BUS-OFF, ERROR-PASSIVE, DOWN, MISSING)
- ✅ **WARNING monitoring** (NEW! optional, disabled by default)
- ✅ Rate limiting and safety
- ✅ Multi-interface support
- ✅ User-independent
- ✅ Configurable polling (0.5s - 5s)

---

### **5. Oscillator Auto-Detection** (10 KB, ~291 lines)
**File:** `scripts/maintenance/can/auto_detect_mcp2515_oscillator.sh`

**Features:**
- ✅ Tests 8/12/16 MHz automatically
- ✅ **Understands clock = oscillator / 2** (NEW!)
- ✅ Updates config.txt
- ✅ Safe backups
- ✅ Works at 500 kbps

---

### **6. Installer** (10 KB, ~290 lines)
**File:** `scripts/maintenance/can/install_can_watchdog.sh`

**Features:**
- ✅ One-command installation
- ✅ System-wide paths
- ✅ Default configs with **WARNING options** (NEW!)
- ✅ Service enablement
- ✅ RPi detection

---

### **7. Systemd Service** (1.5 KB)
**File:** `systemd/can-watchdog@.service`

**Features:**
- ✅ Runs as root (user-independent)
- ✅ Auto-starts at boot
- ✅ Wide PATH for compatibility
- ✅ Environment file support

---

## 📊 Documentation Coverage

### **CAN Error States (Complete)**
| State | Documented | Code | Config |
|-------|-----------|------|--------|
| ERROR-ACTIVE | ✅ Full | ✅ Yes | N/A |
| WARNING | ✅ Full | ✅ **NEW!** | ✅ Optional |
| ERROR-PASSIVE | ✅ Full | ✅ Yes | ✅ Yes |
| BUS-OFF | ✅ Full | ✅ Yes | ✅ Yes |
| DOWN | ✅ Full | ✅ Yes | ✅ Yes |
| MISSING | ✅ Full | ✅ Yes | ✅ Yes |
| RX Overrun | ✅ Explained | ❌ No | N/A |
| TX Timeout | ✅ Explained | ⚠️ Partial | N/A |
| ACK Error | ✅ Explained | ⚠️ Indirect | N/A |
| Bit Stuffing | ✅ Explained | ⚠️ Indirect | N/A |

---

### **Topics Covered**

**✅ Error States & Recovery:**
- All 6 CAN states fully explained
- Transition diagrams
- Error counter behavior (TEC/REC)
- Recovery procedures
- Industry standards

**✅ Oscillator Issues:**
- 8/12/16 MHz detection
- Clock display behavior (÷2)
- Automatic fixing
- RPi-specific guidance

**✅ Configuration:**
- Global settings
- Per-interface overrides
- Polling intervals
- WARNING monitoring (optional)
- Rate limiting

**✅ Hardware:**
- Raspberry Pi setup
- MCP2515 overlays
- Termination (120Ω)
- Cable requirements

**✅ Troubleshooting:**
- Common problems
- Diagnostic commands
- Log analysis
- Hardware checks

---

## 🎯 What's New (This Session)

### **Documentation Additions:**
1. ✅ **CAN Error States section** (325+ lines)
   - Complete technical explanation
   - State transition diagrams
   - Industry comparison
   
2. ✅ **WARNING Monitoring** (80+ lines)
   - Optional feature documented
   - Configuration examples
   - Use cases explained
   
3. ✅ **Oscillator Clock Behavior** (60+ lines)
   - Explains clock = oscillator / 2
   - Prevents confusion
   
4. ✅ **Educational Quick Reference**
   - Simple tables
   - Common causes & fixes
   - When to use features

### **Code Additions:**
1. ✅ **WARNING monitoring in watchdog**
   - Optional, disabled by default
   - Configurable threshold
   - Rate-limited logging
   
2. ✅ **Oscillator clarification in script**
   - Comments explain clock behavior
   - Tests functionality, not values

---

## 📖 Reading Guide

**If you're new to CAN:**
1. Start: `CAN_AUTO_RECOVERY_IMPLEMENTATION_SUMMARY.md`
2. Read: "Understanding CAN Error States (Education)" section
3. Then: `docs/guides/CAN_AUTO_RECOVERY.md` for full details

**If you're setting up:**
1. Read: `CAN_IMPLEMENTATION_FILES.md` (file locations)
2. Follow: Quick start commands
3. Reference: Configuration sections as needed

**If you're troubleshooting:**
1. Check: Troubleshooting sections in summary
2. Read: Specific error state in main doc
3. Enable: WARNING monitoring if needed

**If you're on Raspberry Pi:**
1. Run: `auto_detect_mcp2515_oscillator.sh`
2. Read: "Raspberry Pi Specifics" section
3. Understand: Clock display behavior

---

## ✅ Verification Checklist

- [x] All CAN states documented
- [x] WARNING monitoring implemented and documented
- [x] Oscillator detection explained
- [x] Clock display behavior clarified
- [x] Configuration examples provided
- [x] Troubleshooting guides complete
- [x] Quick reference tables added
- [x] Use cases and examples included
- [x] Industry standards referenced
- [x] RPi-specific guidance provided

---

## 📝 Quick Links

**Installation:**
```bash
cd /home/uday/Downloads/pragati_ros2
sudo bash scripts/maintenance/can/install_can_watchdog.sh can0
```

**Enable WARNING monitoring:**
```bash
sudo nano /etc/default/can-watchdog-can0
# Set: MONITOR_WARNING_STATE=yes
sudo systemctl restart can-watchdog@can0.service
```

**View logs:**
```bash
sudo journalctl -u can-watchdog@can0.service -f
```

**Check CAN state:**
```bash
ip -details link show can0
ip -s link show can0  # With statistics
```

---

**Total Documentation:** ~68 KB, 1000+ lines  
**Implementation:** ~110 KB total (code + docs)  
**Coverage:** Complete - all critical CAN states and issues  
**Status:** Production Ready ✅
