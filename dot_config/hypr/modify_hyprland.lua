#!/usr/bin/env python3
"""Build hyprland.lua from Omarchy's installed entrypoint plus our module."""

import os
from pathlib import Path
import sys


ANCHOR = 'require("default.hypr.toggles")'
DEFAULTS_ANCHOR = 'require("default.hypr.omarchy")'
QCONSOLE_OVERRIDE = """-- BEGIN chezmoi qconsole override
-- hypr/qconsole.lua loads a patched copy; two copies fight over the scratchpad size.
package.loaded["default.hypr.qconsole"] = true
-- END chezmoi qconsole override"""
CUSTOM_MODULE = """-- BEGIN chezmoi custom module
require("hypr.chezmoi")
-- END chezmoi custom module"""


omarchy_path = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
upstream_path = omarchy_path / "config/hypr/hyprland.lua"

try:
    upstream = upstream_path.read_text()
except OSError as error:
    sys.exit(f"cannot read Omarchy Hyprland entrypoint {upstream_path}: {error}")

if upstream.count(ANCHOR) != 1:
    sys.exit(
        f"expected exactly one {ANCHOR!r} in {upstream_path}; "
        "Omarchy's entrypoint structure changed"
    )

if upstream.count(DEFAULTS_ANCHOR) != 1:
    sys.exit(
        f"expected exactly one {DEFAULTS_ANCHOR!r} in {upstream_path}; "
        "Omarchy's entrypoint structure changed"
    )

before, after = upstream.split(ANCHOR)
rendered = before + ANCHOR + "\n\n" + CUSTOM_MODULE + after
rendered = rendered.replace(DEFAULTS_ANCHOR, QCONSOLE_OVERRIDE + "\n" + DEFAULTS_ANCHOR)
sys.stdout.write(rendered.rstrip() + "\n")
