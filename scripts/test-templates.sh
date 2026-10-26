#!/usr/bin/env bash
# Validate isolated profile/role renders. Run from any directory; see docs/validation.md for prerequisites.

set -euo pipefail

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$source_dir/scripts/test-templates.py" "$@"
if command -v node >/dev/null 2>&1; then
  node --test "$source_dir/scripts/test-opencode-statusline.mjs"
else
  printf 'skipped test-opencode-statusline.mjs: node not on PATH\n' >&2
fi
