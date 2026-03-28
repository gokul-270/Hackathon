#!/usr/bin/env bash
# Pre-push validation hook for Pragati ROS2.
# Consolidates all validation checks into a single script to avoid
# per-hook overhead on slow filesystems (e.g. WSL 9p mounts).
#
# Checks performed:
#   1. Trailing whitespace
#   2. End-of-file newline
#   3. YAML syntax
#   4. Large files (>1MB)
#   5. Merge conflict markers
#   6. Mixed line endings
#   7. Flake8 Python linting
#   8. Empty files (0-byte)
#   9. Root folder clutter
#
# Usage: scripts/validation/pre_push_validate.sh <file1> <file2> ...
# Exit 0 = all checks pass, Exit 1 = failures found

set -uo pipefail

errors=0
warnings=0

# Colors (only if terminal supports it)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' NC=''
fi

fail() { echo -e "${RED}FAIL${NC}: $1"; ((errors++)); }
warn() { echo -e "${YELLOW}WARN${NC}: $1"; ((warnings++)); }
pass() { echo -e "${GREEN}OK${NC}: $1"; }

# Get list of files to check: either from args or from staged files
if [ $# -gt 0 ]; then
    files=("$@")
else
    # Get all files that differ between HEAD and the remote tracking branch
    mapfile -t files < <(git diff --name-only --diff-filter=ACMR HEAD 2>/dev/null)
    if [ ${#files[@]} -eq 0 ]; then
        # Fallback: check staged files
        mapfile -t files < <(git diff --cached --name-only --diff-filter=ACMR 2>/dev/null)
    fi
fi

if [ ${#files[@]} -eq 0 ]; then
    echo "No files to validate."
    exit 0
fi

echo "Validating ${#files[@]} file(s)..."
echo ""

# --- Check 1: Trailing whitespace ---
trailing_count=0
for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    # Skip binary files
    file -b --mime-encoding "$f" 2>/dev/null | grep -q binary && continue
    if grep -Pn '[ \t]+$' "$f" >/dev/null 2>&1; then
        ((trailing_count++))
        [ $trailing_count -le 3 ] && warn "trailing whitespace: $f"
    fi
done
if [ $trailing_count -eq 0 ]; then
    pass "no trailing whitespace"
elif [ $trailing_count -gt 3 ]; then
    fail "trailing whitespace in $trailing_count files (showing first 3)"
else
    fail "trailing whitespace in $trailing_count file(s)"
fi

# --- Check 2: End-of-file newline ---
eof_count=0
for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    [ -s "$f" ] || continue
    file -b --mime-encoding "$f" 2>/dev/null | grep -q binary && continue
    if [ "$(tail -c 1 "$f" | wc -l)" -eq 0 ]; then
        ((eof_count++))
        [ $eof_count -le 3 ] && warn "missing final newline: $f"
    fi
done
if [ $eof_count -eq 0 ]; then
    pass "all files end with newline"
else
    fail "missing final newline in $eof_count file(s)"
fi

# --- Check 3: YAML syntax ---
yaml_count=0
yaml_fail=0
for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    case "$f" in *.yaml|*.yml) ;; *) continue ;; esac
    ((yaml_count++))
    if ! python3 -c "import yaml; yaml.safe_load(open('$f'))" 2>/dev/null; then
        ((yaml_fail++))
        fail "invalid YAML: $f"
    fi
done
if [ $yaml_count -gt 0 ] && [ $yaml_fail -eq 0 ]; then
    pass "YAML syntax ($yaml_count files)"
elif [ $yaml_count -eq 0 ]; then
    pass "YAML syntax (no YAML files)"
fi

# --- Check 4: Large files (>1MB) ---
large_count=0
for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo 0)
    if [ "$size" -gt 1048576 ]; then
        ((large_count++))
        fail "large file ($(( size / 1024 ))KB): $f"
    fi
done
[ $large_count -eq 0 ] && pass "no large files (>1MB)"

# --- Check 5: Merge conflict markers ---
conflict_count=0
for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    file -b --mime-encoding "$f" 2>/dev/null | grep -q binary && continue
    if grep -Pn '^(<{7}|>{7}|={7})( |$)' "$f" >/dev/null 2>&1; then
        ((conflict_count++))
        fail "merge conflict markers: $f"
    fi
done
[ $conflict_count -eq 0 ] && pass "no merge conflict markers"

# --- Check 6: Mixed line endings ---
mixed_count=0
for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    file -b --mime-encoding "$f" 2>/dev/null | grep -q binary && continue
    cr=$(tr -cd '\r' < "$f" | wc -c)
    total=$(wc -l < "$f")
    if [ "$cr" -gt 0 ] && [ "$cr" -lt "$total" ]; then
        ((mixed_count++))
        fail "mixed line endings (CRLF+LF): $f"
    fi
done
[ $mixed_count -eq 0 ] && pass "consistent line endings"

# --- Check 7: Flake8 Python linting ---
py_files=()
for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    case "$f" in *.py) py_files+=("$f") ;; esac
done
if [ ${#py_files[@]} -gt 0 ]; then
    if command -v flake8 >/dev/null 2>&1; then
        flake8_output=$(flake8 --max-line-length=100 --extend-ignore=E203,W503 "${py_files[@]}" 2>&1)
        if [ -n "$flake8_output" ]; then
            fail "flake8 errors in Python files:"
            echo "$flake8_output" | head -20
            total_flake8=$(echo "$flake8_output" | wc -l)
            [ "$total_flake8" -gt 20 ] && echo "  ... and $((total_flake8 - 20)) more"
        else
            pass "flake8 lint (${#py_files[@]} Python files)"
        fi
    else
        warn "flake8 not installed, skipping Python lint"
    fi
else
    pass "flake8 lint (no Python files)"
fi

# --- Check 8: Empty files (0-byte) ---
empty_count=0
for f in "${files[@]}"; do
    [ -f "$f" ] || continue
    if [ ! -s "$f" ]; then
        ((empty_count++))
        fail "empty file (0 bytes): $f"
    fi
done
[ $empty_count -eq 0 ] && pass "no empty files"

# --- Check 9: Root folder clutter ---
root_clutter=0
for f in "${files[@]}"; do
    # Only check files directly in root (no / in path)
    case "$f" in */*) continue ;; esac
    case "$f" in
        # Allowed root files
        README.md|CHANGELOG.md|CONTRIBUTING.md|AGENTS.md) continue ;;
        build.sh|sync.sh|setup_*.sh|emergency_motor_stop.sh) continue ;;
        requirements.txt) continue ;;
        # Block stray docs/scripts/Python in root
        *.md|*.sh|*.py|*.txt)
            ((root_clutter++))
            fail "not allowed in root: $f (move to docs/ or scripts/)"
            ;;
    esac
done
[ $root_clutter -eq 0 ] && pass "root folder clean"

# --- Summary ---
echo ""
if [ $errors -gt 0 ]; then
    echo -e "${RED}Validation failed: $errors error(s), $warnings warning(s)${NC}"
    echo "Fix the issues above before pushing."
    exit 1
else
    echo -e "${GREEN}All checks passed${NC} ($warnings warning(s))"
    exit 0
fi
