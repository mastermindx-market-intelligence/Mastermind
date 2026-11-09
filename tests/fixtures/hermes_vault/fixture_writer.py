"""Load the unmodified, pinned Hermes VaultStore with disposable OS helpers.

Only its three environment/file helper imports are supplied locally. The donor
add_item, item selection, format serialization and cryptography.Fernet writer
execute unchanged. This is fixture interoperability, not a Hermes installation.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types


def write_login(directory: Path, *, password: str, identifier="fixture@example.test", origin="https://vault.test"):
    def make_user_dir(path, **kwargs):
        Path(path).mkdir(**kwargs)
    def atomic_write_bytes(path, data, *, mode, fsync_dir):
        fd, temporary = tempfile.mkstemp(dir=Path(path).parent)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            if fsync_dir:
                parent = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(parent)
                finally: os.close(parent)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    modules = {}
    for name, attributes in {
        "hermes_dir_acl": {"make_user_dir": make_user_dir},
        "hermes_constants": {"get_hermes_home": lambda: str(directory.parent)},
        "utils": {"atomic_write_bytes": atomic_write_bytes},
    }.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        modules[name] = module
    name = "_pinned_hermes_vault_fixture"
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name("vault_store_upstream.py"))
    donor = importlib.util.module_from_spec(spec)
    modules[name] = donor
    # Restore only our injected environment edges. Rolling back the complete
    # sys.modules dictionary would unload dependencies imported by the real
    # writer while native cryptography type registries still reference them.
    absent = object()
    previous = {key: sys.modules.get(key, absent) for key in modules}
    sys.modules.update(modules)
    try:
        spec.loader.exec_module(donor)
        item = donor.VaultStore(directory).add_item("login", "Synthetic engine qualification", {
            "identifier_type": "email", "identifier": identifier, "password": password,
        }, origin=origin)
    finally:
        for key, value in previous.items():
            if value is absent:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return item
