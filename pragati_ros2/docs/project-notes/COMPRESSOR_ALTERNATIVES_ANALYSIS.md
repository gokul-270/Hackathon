# Compressor Alternatives Analysis
**Goal:** Eliminate generator dependency by using 12V/battery-powered compressor
**Created:** January 28, 2026
**Status:** Evaluation

---

## 1. Understanding the Actual Requirement

### 1.1 Key Insight: Intermittent Use, NOT Continuous
The end effector (EE) only needs air during cotton **extraction/ejection** - a brief burst per pick.

**Pick Cycle Breakdown:**
| Phase | Duration | Air Needed? |
|-------|----------|-------------|
| Detection trigger | 0.1s | ❌ No |
| Camera capture | 0.3s | ❌ No |
| Detection processing | 0.3-0.5s | ❌ No |
| Cotton selection | 0.1s | ❌ No |
| Arm movement to cotton | 2-4s | ❌ No |
| EE approach | 0.5-1s | ❌ No |
| **EE extraction (air burst)** | **0.5-1s** | **✅ YES** |
| Arm retract | 1-2s | ❌ No |
| **Total cycle** | **~5-10s** | **~1s air** |

**Duty Cycle:** ~10-20% (1s air per 5-10s cycle)

### 1.2 Air Consumption Estimate
| Parameter | Value | Notes |
|-----------|-------|-------|
| EE burst duration | 0.5-1.0 sec | Per pick |
| Operating pressure | 6-8 bar | Current system |
| Estimated burst consumption | 2-5 L per pick | Based on solenoid valve Cv |
| Picks per minute (max) | 6-10 | Assuming 6-10s cycle |
| Air consumption rate | 12-50 L/min peak | Only during active picking |
| **Average consumption** | **~5-15 L/min** | With recovery time |

---

## 2. Compressor Options Comparison

### 2.1 Current Setup
**Dongcheng DEQ1200X2 / 50L**
| Spec | Value |
|------|-------|
| Type | AC Oil-Free (220V) |
| Power | Dual 1200W (~2400W total) |
| Tank | 50L |
| Flow Rate | ~160-200 L/min |
| Max Pressure | 7-8 bar |
| Weight | ~37-45 kg |
| **Requires** | **Generator** |

**Problems:**
- Heavy (37-45 kg)
- Needs generator (adds weight, noise, fuel)
- Restart-under-pressure failed in January field trial
- Not vehicle-battery compatible

### 2.2 Option A: XLNT Cordless (XTC) - 1.5L Tank
| Spec | Value |
|------|-------|
| Type | Cordless (Li-ion battery) |
| Power | 350W |
| Tank | **1.5L** |
| Max Pressure | 8 bar (~116 PSI) |
| Flow Rate | ~25-35 L/min (estimated) |
| Battery | 20V Li-ion (typical) |
| Weight | ~3-5 kg (estimated) |

**Analysis:**
| Metric | Calculation | Result |
|--------|-------------|--------|
| Tank capacity at 8 bar | 1.5L × 8 = 12L atmospheric equivalent | 12L |
| Picks per tank fill | 12L ÷ 3L per pick = 4 picks | ~4 picks |
| Refill time (corrected) | 12L ÷ 30 L/min = 0.4 min = **24 sec** | 24 sec |
| Recovery between picks | 5-10 sec | Partial refill |

**Verdict:** ⚠️ Marginal - may struggle during rapid consecutive picks

### 2.2B Option A2: Ingco 40V Cordless (CACLI2003) - 6L Tank ⭐ RECOMMENDED
| Spec | Value |
|------|-------|
| Type | Cordless (Li-ion battery) |
| Model | Ingco CACLI2003 |
| Power | 40V (2x20V batteries) |
| Tank | **6L** ✅ |
| Max Pressure | **9 bar (135 PSI)** ✅ |
| Flow Rate | **98 LPM** ✅ |
| Weight | 10 kg |
| Price | ₹18,500 |
| Features | Digital display, LED light, cordless |

**Analysis:**
| Metric | Calculation | Result |
|--------|-------------|--------|
| Tank capacity at 8 bar | 6L × 8 = 48L atmospheric equivalent | **48L** |
| Picks per tank fill | 48L ÷ 3L per pick | **~16 picks** |
| Refill time (full) | 48L ÷ 98 LPM = 0.5 min | **~30 sec** |
| Recovery between picks | 5-10 sec available | **Full recovery** |
| Can keep up? | 98 LPM > 15 LPM avg demand | **✅ Yes easily** |

**Verdict:** ✅ **BEST OPTION** - All-in-one cordless with adequate tank and flow

### 2.3 Option B: Eastman EAC-60150N (12V DC)
| Spec | Value |
|------|-------|
| Type | 12V DC (vehicle battery) |
| Power | 12V, 15-25A (~180-300W) |
| Tank | ❌ None (direct) |
| Flow Rate | **60 L/min** |
| Max Pressure | 150 PSI (~10 bar) |
| Current Draw | 15-25A |
| Weight | ~5-8 kg |

**Analysis:**
| Metric | Calculation | Result |
|--------|-------------|--------|
| Can it supply peak demand? | 60 L/min vs 12-50 L/min needed | ✅ Yes |
| Continuous runtime | Vehicle battery dependent | Hours |
| No tank = no buffer | Must run during pick | ⚠️ Noisy during pick |

**Verdict:** ✅ Viable - but needs external tank for buffer

### 2.4 Option C: Eastman 12V + External 5-10L Tank
| Spec | Value |
|------|-------|
| Compressor | Eastman EAC-60150N |
| External Tank | 5-10L portable air tank |
| Combined Flow | 60 L/min |
| Buffer | 40-80L atmospheric equivalent |
| Power | Vehicle 12V battery |

**Analysis:**
| Metric | Calculation | Result |
|--------|-------------|--------|
| Tank capacity at 8 bar | 10L × 8 = 80L atmospheric | 80L |
| Picks per tank | 80L ÷ 3L = 26 picks | **~25 picks** |
| Refill time (full) | 80L ÷ 60 L/min = 1.3 min | 80 sec |
| Continuous picking? | Yes, compressor keeps up | ✅ Yes |

**Verdict:** ✅ **Recommended** - Best balance of portability and performance

### 2.5 Option D: XLNT 3L Tank (AC Powered)
| Spec | Value |
|------|-------|
| Type | AC Oil-Free (220V) |
| Power | 1700W |
| Tank | 3L |
| Flow Rate | **150 L/min** |
| Max Pressure | 8 bar |

**Analysis:**
- High flow rate (150 L/min) can keep up with demand
- Small 3L tank = frequent cycling but adequate
- Still needs AC power (generator)

**Verdict:** ❌ Still needs generator - defeats purpose

---

## 3. Recommended Solution

### ⭐ PRIMARY Recommendation: Ingco 40V Cordless (CACLI2003)

**Why this is the best option:**
1. ✅ **6L tank** = 16 picks buffer (no external tank needed)
2. ✅ **98 LPM flow** = fast recovery, keeps up with demand
3. ✅ **9 bar max** = adequate for 6-8 bar EE operation
4. ✅ **Truly cordless** = no vehicle wiring, no generator
5. ✅ **10 kg** = portable, easy to move
6. ✅ **All-in-one** = no assembly of external components

**Cost:** ₹18,500 (higher but includes everything)

**Recommendation:** Buy 1-2 spare battery packs for extended operation.

---

### ALTERNATIVE Recommendation: Eastman 12V + External Tank
*(If Ingco budget not approved, or need vehicle-powered backup)*

**Configuration:**
```
┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
│ Vehicle 12V     │───►│ Eastman 12V  │───►│ 5-10L Tank  │───► EE Solenoid
│ Battery         │    │ Compressor   │    │ (portable)  │
└─────────────────┘    └──────────────┘    └─────────────┘
                            │
                       Pressure Switch
                       (auto on/off)
```

**Components Needed:**
| Item | Est. Cost | Notes |
|------|-----------|-------|
| Eastman EAC-60150N | ₹5,200 | 12V, 60 L/min |
| Portable air tank (5-10L) | ₹1,500-3,000 | With pressure gauge |
| Pressure switch | ₹500-1,000 | Auto on at 6 bar, off at 8 bar |
| Fittings & hose | ₹500 | Quick connects |
| Inline fuse (30A) | ₹100 | Safety |
| **Total** | **₹8,000-10,000** | |

**Benefits:**
1. ✅ No generator needed
2. ✅ Runs from vehicle 12V battery
3. ✅ 60 L/min flow handles peak demand
4. ✅ Tank provides buffer during picks
5. ✅ Lightweight (~10-15 kg total vs 45+ kg)
6. ✅ Pressure switch = automatic operation
7. ✅ Can run continuously from vehicle battery

**Power Budget:**
| Consumer | Current | Notes |
|----------|---------|-------|
| Compressor (running) | 15-25A | Intermittent |
| Compressor (idle) | 0A | Pressure switch off |
| Vehicle battery | 45-65 Ah typical | Hours of runtime |

---

## 4. Alternative: XLNT Cordless as Backup

Keep the XLNT cordless (350W, 1.5L tank) as a **portable backup** for:
- Quick testing without vehicle
- Lab testing
- Emergency field use

But don't rely on it for full field trial due to:
- Limited battery life
- Small tank buffer
- Lower flow rate

---

## 5. Comparison Summary

| Factor | Dongcheng 50L | XLNT 1.5L | **Ingco 6L** | Eastman + Tank |
|--------|---------------|-----------|--------------|----------------|
| Generator needed | ✅ Yes | ❌ No | **❌ No** | ❌ No |
| Vehicle battery | ❌ No | ❌ No | **❌ No** | ✅ Yes |
| Weight | 45 kg | 5 kg | **10 kg** | 15 kg |
| Flow rate | 180 L/min | 30 L/min | **98 L/min** | 60 L/min |
| Tank buffer | 50L | 1.5L | **6L** | 5-10L |
| Picks per fill | Many | ~4 | **~16** | ~25 |
| Continuous picking | ✅ Yes | ⚠️ Marginal | **✅ Yes** | ✅ Yes |
| Portability | ❌ Poor | ✅ Excellent | **✅ Excellent** | ✅ Good |
| External parts | Generator | None | **None** | Tank+switch |
| Cost | Already owned | ~₹8,000 | **₹18,500** | ~₹9,000 |
| **Recommendation** | Backup | Testing only | **⭐ PRIMARY** | Alternative |

---

## 6. Action Items

### Option 1: Ingco 40V (Recommended)
- [ ] **Purchase Ingco CACLI2003** (₹18,500) - includes compressor + tank
- [ ] **Buy 1-2 spare 20V battery packs** (for extended runtime)
- [ ] **Test in lab** - verify 98 LPM meets EE demand
- [ ] **Measure battery life** during continuous pick cycles

### Option 2: Eastman 12V + Tank (Alternative/Backup)
- [ ] Purchase Eastman EAC-60150N (₹5,200)
- [ ] Source 5-10L portable air tank with gauge
- [ ] Get pressure switch (6-8 bar range)
- [ ] Test in lab - verify flow meets EE demand
- [ ] Measure actual current draw from vehicle battery

### Testing Protocol (Either Option)
1. Connect to power source (battery or 12V)
2. Run EE pick cycles continuously for 30 min
3. Monitor: pressure stability, tank recovery, power consumption
4. Count picks achieved before pressure drops below 6 bar

### Integration
- [ ] Mount compressor on vehicle (secure location, accessible)
- [ ] Connect to existing EE pneumatic line
- [ ] Add manual pressure gauge for field monitoring
- [ ] Keep Dongcheng as backup (in support vehicle if needed)

---

## 7. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Compressor can't keep up | Test extensively before field; keep Dongcheng as backup |
| Battery drain | Monitor voltage; vehicle can charge while running |
| Compressor overheating | Verify duty cycle specs; add cooling if needed |
| Pressure fluctuation | Tank provides buffer; pressure switch maintains range |

---

## Appendix: January 2026 Compressor Issue

**Problem:** Dongcheng compressor failed to restart at 6 bar; generator showed overload.

**Root Cause Hypothesis:**
- Unloader valve not releasing head pressure
- High inrush current at restart with back-pressure
- Generator capacity marginal for compressor startup

**Why 12V avoids this:**
- Vehicle battery can handle high inrush current
- Pressure switch prevents restart under load
- Tank buffer reduces compressor cycling

---

**Document Status:** Ready for team review
**Decision Needed:** Approve purchase of Eastman 12V + tank setup
**Deadline:** January 30, 2026 (to allow testing before Feb trial)
