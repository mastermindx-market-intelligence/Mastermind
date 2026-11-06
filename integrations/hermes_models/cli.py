"""Render provider overlays. Refuses any credential material on argv."""

from __future__ import annotations

import sys

from integrations.hermes_models.contract import CREDENTIAL_POINTER_NAMES
from integrations.hermes_models.profile_config import render_profile


def main(argv: list[str]) -> int:
    if _argv_carries_secret(argv):
        sys.stderr.write("refusing to accept credential material on argv\n")
        return 2
    if argv == ["render"]:
        for profile in ("mmsecretary", "mmmeta"):
            sys.stdout.write(render_profile(profile))
            if profile != "mmmeta":
                sys.stdout.write("---\n")
        return 0
    sys.stderr.write("usage: python -m integrations.hermes_models render\n")
    return 2


def _argv_carries_secret(argv: list[str]) -> bool:
    pointers = {name.lower() for name in CREDENTIAL_POINTER_NAMES}
    for arg in argv:
        lowered = arg.lower()
        if "api-key" in lowered or "api_key" in lowered or lowered.startswith("-k"):
            return True
        if "=" in arg:
            name = arg.split("=", 1)[0].lstrip("-").lower()
            if name in pointers or name.endswith("_api_key") or name.endswith("_key_file"):
                return True
    return False
