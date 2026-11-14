"""Atomic read/validate/adopt of the router's existing local route document.

No file writer, service, watcher or configuration registry is introduced. A malformed
or conflicting new document refuses new inference; accepted responses keep their
original route and resource. The on-disk document remains the single configuration.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import stat
import time
from pathlib import Path

from .model_policy import ModelPolicyState

MAX_CONFIG_BYTES = 1024 * 1024


def read_document(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_mode & 0o022 or before.st_nlink != 1
                or not 0 < before.st_size <= MAX_CONFIG_BYTES):
            raise ValueError("unsafe route document metadata")
        data = bytearray()
        while len(data) <= MAX_CONFIG_BYTES:
            chunk = os.read(fd, min(65536, MAX_CONFIG_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        if (len(data) != before.st_size or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            raise ValueError("route document changed during read")
    finally:
        os.close(fd)
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate route document key")
            value[key] = item
        return value
    document = json.loads(data, object_pairs_hook=unique)
    if not isinstance(document, dict) or not isinstance(document.get("routes"), list):
        raise ValueError("invalid route document")
    return document, hashlib.sha256(data).hexdigest()


def binding(route):
    row = dataclasses.asdict(route)
    for key in ("weight", "priority", "model_priority", "model_weight", "model_params", "notes", "models",
                "max_in_flight", "group_max_in_flight"):
        row.pop(key, None)
    return row


class ConfigRefresh:
    def __init__(self, path, digest=None):
        self.path = Path(path) if path else None
        self.digest = digest
        self.error = None
        self.last_check = 0.0
        self.changed_at = None
        self.updates = 0
        self.stat_tag = None

    def refresh(self, app, route_parser, *, force=False):
        if self.path is None:
            return True
        now = time.monotonic()
        try:
            st = self.path.lstat()
            tag = (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        except OSError:
            self.error = "FABRIC_CONFIG_INVALID_OR_ACTIVE_BINDING"
            return False
        if not force and tag == self.stat_tag and now - self.last_check < 0.25:
            return self.error is None
        self.last_check = now
        try:
            document, digest = read_document(self.path)
            self.stat_tag = tag
            if digest == self.digest:
                self.error = None
                return True
            previous = app.state.model_policy
            if previous.policy.get("version") and document.get("model_routing", {}).get("version") != previous.policy["version"]:
                raise ValueError("required live model policy removed or changed")
            routes = route_parser(document)
            aliases = tuple((key, tuple(value)) for key, value in document.get("aliases", {}).items())
            labels = tuple(document.get("model_labels", {}).items())
            settings = dataclasses.replace(app.state.settings, routes=routes,
                aliases=aliases, model_labels=labels, model_routing=document.get("model_routing") or {})
            previous = app.state.model_policy
            candidate = ModelPolicyState(routes, aliases, settings.model_routing,
                previous.window, previous.route_state)
            for rid, rule in candidate.resources.items():
                for key, value in previous.observed_limits.get(rule.get("key", rid), {}).items():
                    if key in rule:
                        rule[key] = min(rule[key], value)
            for admission in previous.active.values():
                old = previous.routes.get(admission.route_id)
                new = candidate.routes.get(admission.route_id)
                if new is None or old is None or binding(new) != binding(old):
                    raise ValueError("active route binding change requires drain")
                old_resource, old_rule = previous.resource(old)
                new_resource, new_rule = candidate.resource(new)
                if (old_resource != new_resource or old_rule.get("input_basis", "total") !=
                        new_rule.get("input_basis", "total")):
                    raise ValueError("active native resource change requires drain")
            # Preserve provider-observed lower limits across unrelated config writes.
            # Explicit operator revisions may change limits only after a safe drained update.
            for rid, rule in candidate.resources.items():
                observed = previous.observed_limits.get(rule.get("key", rid), {})
                for key, value in observed.items():
                    if key in rule:
                        rule[key] = min(rule[key], value)
            previous.routes, previous.aliases = candidate.routes, candidate.aliases
            previous.concurrency_limits = candidate.concurrency_limits
            previous.policy, previous.groups = candidate.policy, candidate.groups
            previous.resources, previous.metered = candidate.resources, candidate.metered
            previous.allow_metered = candidate.allow_metered
            app.state.settings = settings
            observer = getattr(app.state, "capacity_observer", None)
            if observer is not None:
                observer.known_models = frozenset([model for route in routes for model in route.models] + list(dict(aliases)))
            self.digest, self.error = digest, None
            self.changed_at, self.updates = time.time(), self.updates + 1
            previous.changed.set()
            previous.checkpoint()
            return True
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            self.error = "FABRIC_CONFIG_INVALID_OR_ACTIVE_BINDING"
            return False

    def snapshot(self):
        return {"sha256": self.digest, "updates": self.updates,
                "changed_at": self.changed_at, "error": self.error,
                "hot_reload": True, "scope": "future_admissions_only"}
