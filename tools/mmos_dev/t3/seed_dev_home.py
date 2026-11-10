#!/usr/bin/env python3
"""Seed an isolated T3 dev home for MMOS lane T1 (PROGRAM_PLAN_V4).

Copies the Capacity Fabric provider definition file-to-file from the real T3
settings into the dev home, without ever printing secret values. The fabric
route credentials are written to DEV_ROOT/fabric.env (mode 0600) from this
process's environment; the provider's `environment` block stays empty because
the claude child inherits the server process environment (ClaudeHome.ts
mergeClaudeProcessEnvironment). Never prints values.
"""
import json
import os
import sys

DEV_ROOT = os.path.expanduser("~/.mastermind/mmos-dev/t3")
REAL_SETTINGS = os.path.expanduser("~/.t3/userdata/settings.json")
SOURCE_INSTANCE = "capacity_fabric"
PASS_THROUGH_ENV = [
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
]


def main() -> int:
    for sub in ("home/userdata", "claude-home", "scratch-project", "run"):
        os.makedirs(os.path.join(DEV_ROOT, sub), exist_ok=True)

    real = json.load(open(REAL_SETTINGS))
    src = real["providerInstances"][SOURCE_INSTANCE]
    config = dict(src.get("config") or {})
    config["homePath"] = os.path.join(DEV_ROOT, "claude-home")
    dev_instance = {
        "driver": src["driver"],
        "displayName": "Capacity Fabric (dev)",
        "enabled": True,
        "environment": [],  # route env comes from the server process, not settings
        "config": config,  # carries customModels (model slugs only, no secrets)
    }
    settings = {
        "providerInstances": {SOURCE_INSTANCE: dev_instance},
        "defaultModelSelection": {
            "instanceId": SOURCE_INSTANCE,
            "model": os.environ.get("MMOS_T3_DEV_MODEL", "glm-5.3"),
        },
    }
    path = os.path.join(DEV_ROOT, "home", "userdata", "settings.json")
    with open(path, "w") as fh:
        json.dump(settings, fh, indent=2)
    os.chmod(path, 0o600)

    missing = [n for n in PASS_THROUGH_ENV if not os.environ.get(n)]
    if missing:
        print("MISSING_ENV", ",".join(missing))
    envpath = os.path.join(DEV_ROOT, "fabric.env")
    with open(envpath, "w") as fh:
        for name in PASS_THROUGH_ENV:
            value = os.environ.get(name, "")
            fh.write(f"{name}={value}\n")
    os.chmod(envpath, 0o600)
    print("SEEDED", path, "and", envpath, "(mode 0600)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
