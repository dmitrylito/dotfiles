#!/usr/bin/env bash
# Validate isolated profile/role renders. Run from any directory; see docs/validation.md for prerequisites.

set -euo pipefail

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$source_dir/scripts/test-templates.py" "$@"
