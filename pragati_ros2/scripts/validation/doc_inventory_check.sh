#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
PYTHON_SCRIPT="$ROOT_DIR/scripts/doc_inventory.py"
SNAPSHOT="$ROOT_DIR/docs/doc_inventory_snapshot.json"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
  echo "[doc-inventory] Missing script: $PYTHON_SCRIPT" >&2
  exit 1
fi

if [[ ! -f "$SNAPSHOT" ]]; then
  echo "[doc-inventory] Snapshot not found. Generate one with:" >&2
  echo "  python3 scripts/doc_inventory.py docs --snapshot docs/doc_inventory_snapshot.json" >&2
  exit 1
fi

python3 "$PYTHON_SCRIPT" docs --verify "$SNAPSHOT" >/dev/null

echo "[doc-inventory] Documentation inventory matches snapshot (${SNAPSHOT})."
