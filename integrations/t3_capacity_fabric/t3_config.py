"""Idempotent, backup-first writes into T3 Code's local configuration.

T3 keeps providers in ``~/.t3/userdata/settings.json`` (JSON, two-space
indent, live-watched). Environment values are plain strings in that file; the
``secrets/provider-env-*.bin`` store belongs to the T3 UI's Keychain-backed
migration and is never hand-authored here. This module mirrors exactly the
settings surface and nothing else: no T3 process is restarted, no other
provider entry is touched, and every write is preceded by a timestamped
backup. The file is tightened to 0600 because it carries gateway tokens.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

_DEFAULT_USERDATA = Path.home() / ".t3" / "userdata"


def settings_path(userdata: Path = _DEFAULT_USERDATA) -> Path:
    return userdata / "settings.json"


def read_settings(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def backup_file(path: Path, *, backup_dir: Path | None = None) -> Path:
    directory = backup_dir if backup_dir is not None else path.parent / "capacity-fabric-backups"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = directory / f"{path.name}.{stamp}.bak"
    counter = 0
    while target.exists():
        counter += 1
        target = directory / f"{path.name}.{stamp}-{counter}.bak"
    shutil.copy2(path, target)
    return target


def upsert_provider_instance(settings: dict, instance_id: str, instance: dict) -> bool:
    """Insert or replace exactly one providerInstances entry by instance id.

    Unknown keys the app may have added to an existing fabric entry are
    preserved; owned keys are replaced wholesale. Returns True when the stored
    settings changed.
    """
    instances = settings.setdefault("providerInstances", {})
    if not isinstance(instances, dict):
        raise ValueError("providerInstances is not an object")
    existing = instances.get(instance_id)
    if existing == instance:
        return False
    if isinstance(existing, dict):
        merged = {**existing, **instance}
    else:
        merged = dict(instance)
    instances[instance_id] = merged
    return True


def write_settings(path: Path, settings: dict) -> None:
    """Atomic two-space-indent write with a timestamped backup first."""
    backup_file(path)
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
