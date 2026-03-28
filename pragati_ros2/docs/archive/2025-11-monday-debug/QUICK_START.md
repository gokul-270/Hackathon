# Quick Start Guide - Monday Demo Debug Package

**For**: Uday  
**Created**: 2025-11-13  
**Purpose**: Navigate the debug documentation efficiently

---

## 🚀 Start Here

### If you have 5 minutes
Read: **[README.md](README.md)** - Executive summary and decision framework

### If you have 15 minutes
Read in order:
1. **[README.md](README.md)** - Overview
2. **[camera_rotation_analysis.md](camera_rotation_analysis.md)** - The core issue
3. **[aruco_vs_cotton.md](aruco_vs_cotton.md)** - Why one works, one doesn't

### If you have 30 minutes
Add:
4. **[testing_protocol_rpi.md](testing_protocol_rpi.md)** - Print this for tomorrow!

---

## 📁 Files in This Package

### Essential Documents (Read These)
| File | Size | Purpose | Priority |
|------|------|---------|----------|
| `README.md` | 11KB | Master document, decision matrix | 🔥🔥🔥 |
| `camera_rotation_analysis.md` | 13KB | Code diffs + math explanation | 🔥🔥🔥 |
| `aruco_vs_cotton.md` | 15KB | Why different cameras behave differently | 🔥🔥🔥 |
| `testing_protocol_rpi.md` | 12KB | **PRINT THIS** - step-by-step tests tomorrow | 🔥🔥🔥 |

### Reference Materials (Browse As Needed)
| File | Size | Purpose |
|------|------|---------|
| `getRGBFrame.diff` | 584B | Image rotation diff |
| `convertDetection.diff` | 2.5KB | Coordinate transform diff |
| `getRGBFrame_current.cpp` | 3.0KB | Extracted function (current) |
| `getRGBFrame_backup.cpp` | 3.1KB | Extracted function (backup) |
| `convertDetection_current.cpp` | 1.2KB | Extracted function (current) |
| `convertDetection_backup.cpp` | 2.1KB | Extracted function (backup) |

---

## 🎯 What You Need to Know NOW

### The Problem
Your current workspace (Nov 9 code) **lacks 90° camera rotation transforms**. This causes cotton picking coordinate errors (~150mm lateral miss).

### The Solution (Maybe)
Backup workspace (Nov 13 code from RPi) **has rotation transforms**. Expected to reduce error to ~5-10mm.

### Why ArUco Still Works
ArUco uses **different camera** (RealSense) with different pipeline. Unaffected by OAK-D rotation logic.

### What You Need to Decide
**By Saturday**: Use current (safe, familiar, lower accuracy) OR backup (risky, untested locally, potentially much better)?

### How to Decide
**Tomorrow morning**: Run `testing_protocol_rpi.md` on RPi hardware. Tests take ~2-3 hours.

---

## 📋 Tomorrow's Checklist

### Before You Start
- [ ] Print `testing_protocol_rpi.md`
- [ ] Bring ruler, ArUco marker, notepad
- [ ] Charge camera battery (if applicable)
- [ ] Schedule 3 hours of uninterrupted time

### During Testing
- [ ] Follow protocol step-by-step (Tests 1-5)
- [ ] Record ALL measurements (even weird ones!)
- [ ] Take photos of setup
- [ ] Fill in decision matrix

### After Testing
- [ ] Update `README.md` with results
- [ ] Send summary to team
- [ ] Make preliminary recommendation
- [ ] Schedule Saturday decision meeting

---

## 🔑 Key Formulas (For Reference)

### Rotation Transform (90° CW)
```
Bounding Box:
  x_min' = 1.0 - y_max
  y_min' = x_min
  
Spatial Coordinates:
  x' =  y
  y' = -x
  z' =  z
```

### Expected Error
- **Without rotation**: ~150mm lateral error
- **With rotation**: ~5-10mm error
- **Improvement factor**: 15-30x

---

## 📞 Questions?

### "What if both configs work about the same?"
→ Use current workspace (lower risk, familiar)

### "What if backup is clearly better but has minor issues?"
→ Hybrid approach: prepare both, decide Saturday

### "What if backup crashes or is unstable?"
→ Use current workspace, plan ArUco-based demo

### "What if I can't test tomorrow?"
→ Use current workspace by default (it's stable)

---

## 🎬 Monday Demo Options

### Option A: Conservative
- Use current workspace
- Lower pick success rate (~30-50%)
- Demo focuses on system architecture
- Have manual override ready

### Option B: Aggressive  
- Use backup workspace
- Higher pick success rate (expected 80-95%)
- Demo shows improved accuracy
- Requires Friday testing to pass

### Option C: Hybrid (Recommended)
- Test both Friday
- Decide Saturday
- Prepare switching procedure (<5 min)
- Have both ready Monday morning

---

## 📦 Package Contents Summary

```
docs/monday_demo_debug/
├── README.md                    ← START HERE
├── QUICK_START.md               ← You are here
├── camera_rotation_analysis.md  ← Core technical analysis
├── aruco_vs_cotton.md           ← Why systems differ
├── testing_protocol_rpi.md      ← PRINT THIS for tomorrow
├── getRGBFrame.diff             ← Image rotation change
├── convertDetection.diff        ← Coordinate transform change
└── *.cpp files                  ← Extracted code snippets
```

**Total Size**: ~80KB (all text files, easily shareable)

---

## ⏱️ Time Estimates

| Activity | Duration | When |
|----------|----------|------|
| Read README | 5-10 min | Tonight |
| Read camera_rotation_analysis | 10-15 min | Tonight |
| Read aruco_vs_cotton | 10-15 min | Tonight |
| Print testing_protocol | 2 min | Tonight |
| **RPi Testing (all tests)** | **2-3 hours** | **Friday AM** |
| Analyze results | 30 min | Friday PM |
| Team decision meeting | 30 min | Saturday |
| Practice demo | 1-2 hours | Saturday/Sunday |

---

## 🏁 Success Criteria

### For Backup to Win
✅ Coordinates match ArUco within ±10mm  
✅ Pick success rate ≥80%  
✅ Stable operation for 30+ minutes  
✅ Clean shutdown behavior  

### For Current to Win (Default)
✅ Backup doesn't meet above criteria  
OR  
✅ Team prefers lower-risk option  
OR  
✅ No time for adequate backup testing  

---

## 🔒 Safety Notes

- ✅ No code changes made to current workspace
- ✅ Backup workspace remains separate
- ✅ Can switch between configs in <5 minutes
- ✅ Rollback procedure documented
- ✅ Current workspace always available as fallback

---

**You're all set!** 

Tomorrow morning, grab your printed testing protocol and a cup of coffee. Follow the tests step-by-step, record everything, and you'll have the data you need to make a confident decision for Monday's demo.

Good luck! 🚀
