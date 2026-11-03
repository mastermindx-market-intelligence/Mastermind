"""Evidence from the exact objects and descriptors consumed during service startup."""
from __future__ import annotations

import hashlib
import json
import os
import stat

from .readiness import config_fingerprint, encoded


def document_fingerprint(value):
    return hashlib.sha256(encoded(value) + b"\n").hexdigest()


def projection(config_sha256, persistent, dependencies):
    return {"config_sha256": config_sha256, "persistent": persistent, "dependencies": dependencies}


class AcquisitionReceipt:
    """Finite comparison to the installed plan; it issues no authority."""

    def __init__(self, expected):
        if (type(expected) is not dict or set(expected) != {"config_sha256", "persistent", "dependencies"}
                or type(expected["persistent"]) is not dict or type(expected["dependencies"]) is not dict
                or set(expected["persistent"]) != {"project_root", "artifact_directory", "audit_directory",
                                                  "browser_fabric_audit_directory", "action_key"}
                or set(expected["dependencies"]) not in (
                    {"policy", "browser_policy", "profiles"}, {"policy", "browser_policy", "profiles", "routes"},
                    {"policy", "browser_policy", "profiles", "routes", "credentials"})):
            raise ValueError("SERVICE_ACQUISITION_EXPECTATION_REFUSED")
        self._expected = json.loads(encoded(expected))
        self._persistent = {}
        self._dependencies = {}
        self.digest = None

    def _record(self, group, observed, name, value):
        if name not in self._expected[group] or self._expected[group][name] != value:
            raise ValueError("SERVICE_ACQUISITION_BINDING_CHANGED")
        if name in observed and observed[name] != value:
            raise ValueError("SERVICE_ACQUISITION_CHANGED_DURING_STARTUP")
        observed[name] = value

    def document(self, name, path, value):
        self._record("dependencies", self._dependencies, name,
                     {"path": path, "sha256": document_fingerprint(value)})

    def directory(self, name, path, descriptor):
        info = os.fstat(descriptor)
        self._record("persistent", self._persistent, name, {
            "path": path, "device": info.st_dev, "inode": info.st_ino,
            "uid": info.st_uid, "mode": stat.S_IMODE(info.st_mode),
        })

    def action_key(self, path, key):
        self._record("persistent", self._persistent, "action_key",
                     {"path": path, "sha256": hashlib.sha256(key).hexdigest()})

    def complete(self, config):
        actual = projection(config_fingerprint(config), self._persistent, self._dependencies)
        if actual != self._expected:
            raise ValueError("SERVICE_ACQUISITION_INCOMPLETE")
        self.digest = document_fingerprint(actual)
        return self.digest
