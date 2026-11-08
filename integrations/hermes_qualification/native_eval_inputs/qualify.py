"""Verify/apply the pinned patch in a disposable tree; never change the donor.

This is a source qualification utility for the existing release owner. It does
not install Hermes, import its plugins, run a driver, or confer runtime access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from typing import Mapping

ROOT = Path(__file__).resolve().parent
PATHS = ('hermes_state_mutation_retirement.py', 'gateway/session_authority.py', 'agent/agent_init.py', 'agent/memory_caller_scope.py', 'agent/redact.py', 'hermes_cli/mcp_config.py', 'tools/mcp_oauth_manager.py', 'tools/mcp_oauth_provider.py', 'tools/mcp_tool_errors.py', 'tools/mcp_tool_server_run.py', 'tools/mcp_tool_transport.py', 'hermes_state_common.py', 'hermes_state_runtime.py', 'hermes_state_schema.py')
MAX_SOURCE_BYTES = 128 * 1024
ERROR = "NATIVE_EVAL_SOURCE_QUALIFICATION_FAILED"


class QualificationError(ValueError):
    """A closed source error; raw process output is never reflected."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular(path: Path, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
                raise QualificationError("DONOR_SOURCE_INVALID")
            data = handle.read(maximum + 1)
    except (OSError, ValueError):
        raise QualificationError("DONOR_SOURCE_INVALID") from None
    if len(data) > maximum:
        raise QualificationError("DONOR_SOURCE_INVALID")
    return data


def manifest() -> dict:
    try:
        value = json.loads(_read_regular(ROOT / "manifest.json", 16 * 1024))
    except (ValueError, UnicodeError):
        raise QualificationError("MANIFEST_INVALID") from None
    if (type(value) is not dict or value.get("schema") != "mastermind.hermes_native_eval_inputs_patch.v1"
            or set(value.get("files", {})) != set(PATHS)):
        raise QualificationError("MANIFEST_INVALID")
    return value


def prepare_sources(sources: Mapping[str, bytes]) -> dict[str, bytes]:
    """Return patched source bytes after exact preimage, patch and postimage checks.

    Only the temporary copy is modified. A changed/already-patched source is a
    refusal, not an invitation to weaken the preimage or force a patch.
    """
    if type(sources) is not dict or set(sources) != set(PATHS):
        raise QualificationError("SOURCE_SET_INVALID")
    policy = manifest()
    for name in PATHS:
        source = sources[name]
        if (type(source) is not bytes or len(source) > MAX_SOURCE_BYTES
                or digest(source) != policy["files"][name]["before_sha256"]):
            raise QualificationError("DONOR_PREIMAGE_MISMATCH")
    patch = _read_regular(ROOT / "guard.patch", 128 * 1024)
    if digest(patch) != policy["patch_sha256"]:
        raise QualificationError("PATCH_DIGEST_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="hermes-native-eval-qualification-") as temporary:
        tree = Path(temporary)
        for name in PATHS:
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(sources[name])
        env = {"PATH": os.defpath, "LANG": "C",
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        for options in (("--check",), ()):
            try:
                result = subprocess.run(
                    ["git", "apply", *options, "--whitespace=error-all", "-"],
                    input=patch, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=tree, env=env, timeout=10, check=False,
                )
            except (OSError, subprocess.SubprocessError):
                raise QualificationError("PATCH_VERIFICATION_UNAVAILABLE") from None
            if result.returncode != 0:
                raise QualificationError("PATCH_APPLICATION_REFUSED")
        output = {name: _read_regular(tree / name, MAX_SOURCE_BYTES) for name in PATHS}
    for name in PATHS:
        if digest(output[name]) != policy["files"][name]["after_sha256"]:
            raise QualificationError("PATCH_POSTIMAGE_MISMATCH")
    return output


def qualify_root(donor_root: Path) -> dict:
    sources = {name: _read_regular(Path(donor_root) / name, MAX_SOURCE_BYTES) for name in PATHS}
    output = prepare_sources(sources)
    return {
        "schema": "mastermind.hermes_native_eval_inputs_qualification.v1",
        "status": "EXACT_SOURCE_PATCH_VERIFIED",
        "before_sha256": {name: digest(sources[name]) for name in PATHS},
        "after_sha256": {name: digest(output[name]) for name in PATHS},
        "patch_sha256": manifest()["patch_sha256"],
        "donor_modified": False, "driver_started": False,
        "runtime_ready": False, "installed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = qualify_root(args.donor_root)
    except QualificationError as error:
        print(json.dumps({"status": "REFUSED", "reason": str(error)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
