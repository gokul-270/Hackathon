# Truth Precedence and Scoring Rubric

**Created:** 2025-10-07  
**Purpose:** Establish authoritative hierarchy for resolving conflicts during documentation audit

---

## Truth Precedence Hierarchy

When documentation conflicts arise, resolve using this hierarchy (highest to lowest authority):

### 1. **Code (Running/Compilable)** - ULTIMATE AUTHORITY
**Weight: 100%**

The code that actually compiles and runs is the ground truth.

**Evidence Types:**
- ✅ Compiles successfully
- ✅ Unit tests pass
- ✅ Integration tests pass
- ✅ Functions/classes/modules exist and are accessible
- ✅ Hardware interfaces are implemented

**Verification:**
```bash
# Build verification
colcon build --packages-select <package_name>

# Test verification  
colcon test --packages-select <package_name>
```

**Scoring:**
- Feature fully implemented + tests pass: **100%**
- Feature implemented, tests failing: **70%**
- Feature stub/placeholder only: **20%**
- Feature not present in code: **0%**

---

### 2. **Tests (Automated)** - SECONDARY AUTHORITY
**Weight: 80-90%**

Tests demonstrate what actually works, not just what exists.

**Evidence Types:**
- Unit tests (`test/*.cpp`, `test/*.py`)
- Integration tests
- Hardware-in-loop tests
- Test results/logs

**Hierarchy within tests:**
1. Hardware tests (if passing) - 90%
2. Integration tests (if passing) - 85%
3. Unit tests (if passing) - 80%
4. Tests exist but fail - 50%
5. Tests referenced but don't exist - 10%

**Verification:**
```bash
colcon test --packages-select <package_name> --event-handlers console_direct+
colcon test-result --verbose
```

---

### 3. **Hardware Validation Results** - OPERATIONAL TRUTH
**Weight: 85-95%**

Real-world hardware testing trumps simulated success.

**Evidence Types:**
- Hardware test logs
- Field deployment reports
- Physical testing documentation
- Video/sensor data from real runs

**Scoring:**
- Verified working on hardware: **95%**
- Partially working on hardware: **70%**
- Simulation only: **50%**
- No hardware testing: **30%**

**Key distinction:** Hardware results validate *deployment readiness*, not just *code correctness*.

---

### 4. **Generated Documentation** - DERIVED TRUTH
**Weight: 30-50%**

AI-generated or auto-generated docs from code.

**Evidence Types:**
- Doxygen output
- README files with auto-generation markers
- API documentation from code comments
- Files with timestamps/generation markers

**Scoring:**
- Generated from current code: **50%**
- Generated but outdated: **30%**
- Contradicts code: **10%**

**Trust factor:** Only as good as the source code it was generated from.

---

### 5. **Manual Documentation** - ASPIRATIONAL TRUTH  
**Weight: 20-40%**

Human-written docs may reflect intentions, not reality.

**Evidence Types:**
- Handwritten README files
- Design documents
- Planning documents
- Status reports

**Scoring:**
- Verified against code: **40%**
- Appears accurate: **30%**
- Outdated or contradicts code: **20%**
- Pure speculation: **10%**

**Trust factor:** Lowest authority - often reflects plans or past state, not current reality.

---

## Conflict Resolution Matrix

| Situation | Resolution | Example |
|-----------|------------|---------|
| Code says 70%, Doc says 100% | **Trust Code** (70%) | Feature partially implemented |
| Test passes, Doc says "not working" | **Trust Test** (update doc) | Outdated documentation |
| Hardware works, Doc says "broken" | **Trust Hardware** (update doc) | Documentation stale |
| Doc says done, no code exists | **Reject Doc** (0%) | Aspirational feature |
| Code exists, tests missing | **Partial** (40-50%) | Implemented but unverified |
| Tests exist, code missing | **Error** - investigate | Usually test file misplaced |

---

## Scoring Rubric by Feature Type

### Feature/Module Completion Score

Combine evidence using weighted formula:

```
Completion % = (
    Code_Status × 0.40 +
    Test_Status × 0.30 +
    Hardware_Status × 0.20 +
    Doc_Accuracy × 0.10
)
```

#### Code Status (40% weight):
- Fully implemented, no TODOs: **100**
- Implemented with minor TODOs: **85**
- Core implemented, gaps exist: **70**
- Stub/skeleton only: **40**
- Mentioned in design but missing: **10**
- Not mentioned anywhere: **0**

#### Test Status (30% weight):
- Comprehensive tests, all passing: **100**
- Tests exist, mostly passing: **80**
- Basic tests, passing: **60**
- Tests exist but failing: **40**
- No tests: **0**

#### Hardware Status (20% weight):
- Validated on hardware: **100**
- Partial hardware validation: **70**
- Simulation validated: **50**
- Untested: **0**

#### Documentation Accuracy (10% weight):
- Accurate and up-to-date: **100**
- Minor inaccuracies: **70**
- Significantly outdated: **40**
- Missing or wrong: **0**

---

## Red Flags (Automatic Audit Triggers)

These patterns indicate documentation vs. reality mismatch:

🚩 **Critical Flags:**
1. Documentation claims 100% but no code exists
2. Tests referenced in docs but missing from repo
3. "Hardware tested" claims with no test logs
4. Recent commits contradict status claims

🚩 **Warning Flags:**
1. No tests for "production ready" code
2. Generated docs older than code
3. Percentage claims without evidence
4. Conflicting percentages across docs
5. "Should work" or "expected to" language

---

## Verification Checklist Per Module

For each module/feature:

- [ ] **Code Check:** Does it compile? Run `colcon build`
- [ ] **Test Check:** Do tests pass? Run `colcon test`
- [ ] **Hardware Check:** Review test logs/evidence
- [ ] **Doc Check:** Compare claims vs. reality
- [ ] **Cross-ref Check:** Verify with cross_reference_matrix.csv
- [ ] **Compute Score:** Apply rubric formula
- [ ] **Flag Issues:** Note any red flags

---

## Example Scoring

### Example 1: "Cotton Detection - 100% Complete"

**Code Reality:**
- ✅ Cotton detection node exists: **100**
- ✅ All core functions implemented: **100**
- ⚠️ Minor TODOs for edge cases: **-10**
- **Code Score: 90**

**Tests:**
- ✅ Unit tests exist and pass: **100**
- ✅ Integration test passes: **100**
- ❌ Hardware test missing: **-20**
- **Test Score: 80**

**Hardware:**
- ⚠️ Simulation only, no field test: **50**
- **Hardware Score: 50**

**Documentation:**
- ✅ Mostly accurate: **80**
- **Doc Score: 80**

**Final Score:**
```
(90 × 0.40) + (80 × 0.30) + (50 × 0.20) + (80 × 0.10)
= 36 + 24 + 10 + 8
= 78%
```

**Verdict:** Not 100% complete. More like **78% complete** - needs hardware validation.

---

### Example 2: "MG Motor Controller - Claims 70%"

**Code Reality:**
- ✅ Placeholder code exists: **40**
- ❌ Most functions are TODOs: **40**
- **Code Score: 40**

**Tests:**
- ❌ No tests written: **0**
- **Test Score: 0**

**Hardware:**
- ❌ Not tested: **0**
- **Hardware Score: 0**

**Documentation:**
- ⚠️ Plans documented, reality unclear: **30**
- **Doc Score: 30**

**Final Score:**
```
(40 × 0.40) + (0 × 0.30) + (0 × 0.20) + (30 × 0.10)
= 16 + 0 + 0 + 3
= 19%
```

**Verdict:** Actual completion is **~20%**, not 70%. Mostly aspirational.

---

## Output Format for Audit

For each module in PROJECT_STATUS_REALITY_CHECK.md:

```markdown
### Module: <name>

**Claimed Status:** XX%  
**Actual Status:** YY%  
**Delta:** ±ZZ%

**Evidence:**
- Code: [Score]/100 - [Details]
- Tests: [Score]/100 - [Details]
- Hardware: [Score]/100 - [Details]
- Docs: [Score]/100 - [Details]

**Red Flags:** [List any]
**Recommendation:** [Action needed]
```

---

## Usage in Audit

1. For each feature/module in the codebase:
   - Gather evidence from all 5 sources
   - Apply scoring rubric
   - Calculate weighted completion percentage
   - Compare to documentation claims
   - Flag discrepancies

2. Prioritize fixes by impact:
   - Critical: >50% delta in completion claims
   - High: Code says done, tests missing
   - Medium: Docs outdated
   - Low: Minor percentage mismatches

3. Update authoritative sources first (code, tests)
4. Then propagate truth to documentation

---

**Next Step:** Apply this rubric to inventory all documentation and extract status claims (Tasks 3-4).
