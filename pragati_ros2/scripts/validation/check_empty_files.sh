#!/usr/bin/env bash
# Pre-commit hook: Reject empty (0-byte) files from being committed.
# Empty files are almost always accidental and clutter the repository.

set -euo pipefail

status=0
for f in "$@"; do
    if [ ! -s "$f" ]; then
        echo "ERROR: Empty file detected: $f (remove it or add content)"
        status=1
    fi
done

exit $status
