#!/usr/bin/env bash
# Pre-commit hook: auto-format staged files.
# Consolidated into one script to avoid per-tool environment overhead
# on slow filesystems (e.g. WSL 9p mounts).
#
# Actions:
#   1. Strip trailing whitespace from all text files
#   2. Ensure final newline on all text files
#   3. Auto-format Python files with isort + black
#
# Usage: scripts/validation/pre_commit_format.sh <file1> <file2> ...
# Exit 0 = success (files may have been reformatted)

set -uo pipefail

[ $# -eq 0 ] && exit 0

# --- Step 1 & 2: Fix whitespace in all text files ---
for f in "$@"; do
    [ -f "$f" ] || continue
    # Skip binary files
    file -b --mime-encoding "$f" 2>/dev/null | grep -q binary && continue

    # Strip trailing whitespace
    if grep -Pq '[ \t]+$' "$f" 2>/dev/null; then
        sed -i 's/[[:space:]]*$//' "$f"
    fi

    # Ensure final newline (if file is non-empty)
    if [ -s "$f" ] && [ -n "$(tail -c1 "$f")" ]; then
        echo "" >> "$f"
    fi
done

# --- Step 3: Auto-format Python files with isort + black ---
py_files=()
for f in "$@"; do
    case "$f" in *.py) [ -f "$f" ] && py_files+=("$f") ;; esac
done

if [ ${#py_files[@]} -gt 0 ]; then
    # Run isort then black (black gets final say on formatting)
    if command -v isort >/dev/null 2>&1; then
        isort --profile black --quiet "${py_files[@]}" 2>/dev/null
    fi

    if command -v black >/dev/null 2>&1; then
        black --quiet "${py_files[@]}" 2>/dev/null
    fi
fi
