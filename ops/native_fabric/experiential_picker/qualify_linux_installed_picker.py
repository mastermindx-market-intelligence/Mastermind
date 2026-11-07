#!/usr/bin/env python3
"""Exact observed Linux picker forward-port; read-only source qualification.

The upstream sealed picker overlay targets an older generation. This strictly
verified transform retains the installed current router behavior for all other
pools and adds only the exact manual Experiential pin, no AUTO promotion.
It never installs, publishes, creates a native worker or reads provider keys.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("experiential_exact_overlay", HERE / "experiential_manual_route.py")
route = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(route)

OBSERVED_LINUX_PICKER = "bab2bcc1d71d7b8b2a7d5b78247326d5057815c6ed063143c451990b577e13d8"
EXPERIENTIAL_POOL = "experiential"
EXPERIENTIAL_MODEL = "glm-5.3-uncensored"
_ALLOWED_TASKS = frozenset(("mechanical", "fix_build"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_exact(s: str, old: str, new: str) -> str:
    if s.count(old) != 1:
        raise ValueError("installed_picker_preimage_changed")
    return s.replace(old, new)


def forward_port(raw: bytes) -> bytes:
    if sha(raw) != OBSERVED_LINUX_PICKER:
        raise ValueError("installed_picker_preimage_changed")
    s = raw.decode("utf-8")
    s = replace_exact(s,
        '    stem = raw[len("remote-"):] if raw.startswith("remote-") else raw\n'
        '    for fam in _POOL_FAMILIES:\n',
        '    stem = raw[len("remote-"):] if raw.startswith("remote-") else raw\n'
        '    if stem == _EXPERIENTIAL_POOL:\n'
        '        return "glm"  # same model family, distinct provider\n'
        '    for fam in _POOL_FAMILIES:\n')
    s = replace_exact(s,
        'def _subject_ok(pool: str, task_class: str, subject_pool: Optional[str],\n',
        route._EXPERIENTIAL_BLOCK +
        'def _subject_ok(pool: str, task_class: str, subject_pool: Optional[str],\n')
    s = replace_exact(s,
        '    p = canonical_pool(pool) or pool\n'
        '    # Hard boundary independent of optional YAML parsing:',
        '    p = canonical_pool(pool) or pool\n'
        '    if p == _EXPERIENTIAL_POOL:\n'
        '        return False, "experiential manual pin never admitted implicitly"\n'
        '    # Hard boundary independent of optional YAML parsing:')
    s = replace_exact(s,
        '    spec = ((doc or load_pools()).get("pools") or {}).get(pool) or {}\n'
        '    model = spec.get("default_model") or _default_model(pool, task_class)\n',
        '    if pool == _EXPERIENTIAL_POOL:\n'
        '        return (model if model == _EXPERIENTIAL_MODEL else ""), suffix\n'
        '    spec = ((doc or load_pools()).get("pools") or {}).get(pool) or {}\n'
        '    model = spec.get("default_model") or _default_model(pool, task_class)\n')
    s = replace_exact(s,
        '    ladder = escalation_ladder(doc)\n'
        '    p = canonical_pool(pool) or (pool or "")\n',
        '    ladder = escalation_ladder(doc)\n'
        '    p = canonical_pool(pool) or (pool or "")\n'
        '    if p == _EXPERIENTIAL_POOL:\n'
        '        return ""  # manual pool is never an escalation origin\n')
    s = replace_exact(s,
        '    if explicit_model:\n'
        '        models = {str(value).casefold() for value in _glm_models(doc).values()}\n',
        '    experiential_pin = (type(requested_model) is str and\n'
        '                        requested_model == _EXPERIENTIAL_MODEL and\n'
        '                        pool == _EXPERIENTIAL_POOL)\n'
        '    if forced == _EXPERIENTIAL_POOL and not experiential_pin:\n'
        '        return "NONE reason=experiential requires exact pool and model pin"\n'
        '    if (requested_model is not None and\n'
        '            str(requested_model).strip().casefold() == _EXPERIENTIAL_MODEL\n'
        '            and not experiential_pin):\n'
        '        return "NONE reason=experiential model requires exact pool and model pin"\n'
        '    if experiential_pin:\n'
        '        ok, reason = _experiential_manual_affinity(tc, doc)\n'
        '        if not ok:\n'
        '            return f"NONE reason={reason}"\n'
        '    if explicit_model and not experiential_pin:\n'
        '        models = {str(value).casefold() for value in _glm_models(doc).values()}\n')
    s = replace_exact(s,
        '        ok, reason = policy_allows(forced, tc, doc)\n'
        '        if not ok:\n'
        '            return f"NONE reason={reason}"\n'
        '        selected_model = (explicit_model or None) if forced == "glm" else None\n',
        '        if forced == _EXPERIENTIAL_POOL:\n'
        '            allowed_classes = pool_task_classes(forced, doc)\n'
        '            if not allowed_classes or tc not in allowed_classes:\n'
        '                return "NONE reason=experiential pool class policy refused"\n'
        '            ok, reason = _experiential_manual_affinity(tc, doc)\n'
        '        else:\n'
        '            ok, reason = policy_allows(forced, tc, doc)\n'
        '        if not ok:\n'
        '            return f"NONE reason={reason}"\n'
        '        selected_model = (_EXPERIENTIAL_MODEL if forced == _EXPERIENTIAL_POOL\n'
        '                          else (explicit_model or None) if forced == "glm"\n'
        '                          else None)\n')
    s = replace_exact(s,
        '    if normalized_mode not in {"grok", "cursor", "glm", "glm-codex",\n',
        '    if normalized_mode == _EXPERIENTIAL_POOL:\n'
        '        if (requested_model != _EXPERIENTIAL_MODEL or\n'
        '                normalized_task not in _EXPERIENTIAL_ALLOWED_CLASSES or\n'
        '                _experiential_witnesses() is None):\n'
        '            result.update(allowed=False, reason="experiential_manual_unqualified",\n'
        '                          tier="unknown")\n'
        '            return result\n'
        '        result.update(reason="experiential_manual_witnessed",\n'
        '                      tier=model_tier.CLASS_TIER.get(normalized_task, "unknown"))\n'
        '        return result\n'
        '    if normalized_mode not in {"grok", "cursor", "glm", "glm-codex",\n')
    s = replace_exact(s,
        '    "ocfree": ("oc-free",),\n',
        '    "ocfree": ("oc-free",),\n'
        '    "experiential": ("experiential",),  # manual only, placement-gated\n')
    import ast
    ast.parse(s, filename="exact-installed-experiential-picker.py")
    result = s.encode("utf-8")
    if result == raw:
        raise ValueError("no_change")
    return result


def read_installed(path: Path) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 2_000_000:
                raise ValueError("installed_picker_not_regular")
            data = b""
            while len(data) < info.st_size:
                chunk = os.read(fd, info.st_size - len(data))
                if not chunk:
                    raise ValueError("installed_picker_changed_during_read")
                data += chunk
        finally:
            os.close(fd)
        return data
    except OSError as exc:
        raise ValueError("installed_picker_unavailable") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-picker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        preimage = read_installed(args.installed_picker)
        output = forward_port(preimage)
        target = args.output
        # A single new file only, never touching the installed code.
        parent = args.installed_picker.resolve().parent
        dest = target.resolve()
        if dest == args.installed_picker.resolve() or dest == parent or parent in dest.parents:
            raise ValueError("output_overlaps_installed_picker")
        if target.exists() or target.is_symlink():
            raise ValueError("output_not_disposable")
        if not args.verify_only:
            target.write_bytes(output)
        print(json.dumps({
            "state": "QUALIFIED_SOURCE_ONLY_NOT_INSTALLED",
            "preimage_sha256": sha(preimage),
            "postimage_sha256": sha(output),
            "changed_files": ["ext/pick.py"],
            "worker_started": False,
            "admission_granted": False,
            "verify_only": args.verify_only,
        }, sort_keys=True))
        return 0
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
