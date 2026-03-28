#!/usr/bin/env bash
# Pre-commit hook: Reject docs, scripts, and stray files from repository root.
# Only allowlisted files may live in root. Everything else should go to docs/ or scripts/.
#
# Allowlisted root files:
#   .md:  README.md, CHANGELOG.md, CONTRIBUTING.md
#   .sh:  build.sh, sync.sh, setup_*.sh, emergency_motor_stop.sh
#   .txt: requirements.txt
#   (no .py files allowed in root — test scripts go to scripts/)

set -euo pipefail

blocked=""

for f in "$@"; do
    # Only check files directly in root (no directory separator in path)
    case "$f" in
        */*) continue ;;
    esac

    case "$f" in
        # Allowed root .md files
        README.md|CHANGELOG.md|CONTRIBUTING.md) continue ;;
        # Block all other .md in root
        *.md)
            blocked="${blocked}  ${f} -> move to docs/\n"
            ;;
        # Allowed root .sh files (build tools + setup scripts for easy access)
        build.sh|sync.sh|setup_*.sh|emergency_motor_stop.sh) continue ;;
        # Block all other .sh in root
        *.sh)
            blocked="${blocked}  ${f} -> move to scripts/\n"
            ;;
        # Block all .py in root (test scripts go to scripts/)
        *.py)
            blocked="${blocked}  ${f} -> move to scripts/\n"
            ;;
        # Allowed root .txt files
        requirements.txt) continue ;;
        # Block other .txt in root
        *.txt)
            blocked="${blocked}  ${f} -> move to appropriate directory\n"
            ;;
    esac
done

if [ -n "$blocked" ]; then
    echo "ERROR: Files not allowed in repository root:"
    echo -e "$blocked"
    echo "Move documentation to docs/ and scripts to scripts/"
    exit 1
fi
