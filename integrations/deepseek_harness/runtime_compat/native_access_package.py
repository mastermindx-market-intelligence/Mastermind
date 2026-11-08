"""Package the original host admission and scoped native owner access together."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from . import prepare_native_access as access
from . import prepare_native_host as host

PREFIX = "integrations/deepseek_harness/runtime_compat/"
FILES = {
    "access_source": PREFIX + "native-access-source.json",
    "access_patch": PREFIX + "native-owner-access.patch",
    "host_source": PREFIX + "native-host-source.json",
    "host_patch": PREFIX + "native-host-admission.patch",
    "session_source": PREFIX + "native-session-source.json",
    "session_patch": PREFIX + "native-session-generation.patch",
}
IDENTITY_FIELDS = frozenset(("source_sha256", "patch_sha256", "host_source_sha256",
                            "host_patch_sha256", "receipt_sha256"))

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _host_record(raw: bytes, patch: bytes, expected: dict, session: dict | None) -> dict:
    value = json.loads(raw)
    if (type(value) is not dict or value.get("schema") != "mastermind.dsh_native_host_source.v1"
            or value.get("donor_sha") != access.PIN or value.get("production_armed") is not False
            or digest(raw) != expected["host_manifest_sha256"]
            or digest(patch) != expected["host_patch_sha256"]
            or value.get("patch_sha256") != expected["host_patch_sha256"]
            or type(value.get("source_sha256")) is not dict
            or type(value.get("output_sha256")) is not dict
            or set(value["output_sha256"]) != host.CHANGED
            or not host.CHANGED <= set(value["source_sha256"])
            or not 3 <= len(value["source_sha256"]) <= 256):
        raise ValueError("native owner package host composition refused")
    for mapping in ("source_sha256", "output_sha256"):
        for name, value_digest in value[mapping].items():
            if (not host.source_path_allowed(name)
                    or type(value_digest) is not str or not re.fullmatch("[0-9a-f]{64}", value_digest)):
                raise ValueError("native owner package host source path refused")
    headers = patch.decode().splitlines()
    if ({line[6:] for line in headers if line.startswith("+++ b/")} != host.CHANGED
            or {line[6:] for line in headers if line.startswith("--- a/")} != host.CHANGED):
        raise ValueError("native owner package host patch scope refused")
    outputs = {**value["output_sha256"], **(session["output_sha256"] if session else {})}
    if expected["base_sha256"] != {
        name: outputs.get(name, before)
        for name, before in expected["source_sha256"].items()
    }:
        raise ValueError("native owner package access base differs")
    return value

def _inputs(raw: dict[str, bytes]) -> tuple[dict, dict]:
    expected = access.validate_manifest(json.loads(raw["access_source"]), raw["access_patch"])
    session = None
    if expected["schema"] != "mastermind.dsh_native_access_source.v1":
        session = access.native_session.validate_manifest(json.loads(raw["session_source"]), raw["session_patch"])
        if (digest(raw["session_source"]) != expected["session_manifest_sha256"]
                or session["patch_sha256"] != expected["session_patch_sha256"]
                or any(expected["source_sha256"].get(name) != before
                       for name, before in session["source_sha256"].items())):
            raise ValueError("native owner package session composition refused")
    native_host = _host_record(raw["host_source"], raw["host_patch"], expected, session)
    return expected, native_host

def qualify_inputs() -> tuple[dict, dict]:
    raw = {key: (access.ROOT / Path(name).name).read_bytes() for key, name in FILES.items()}
    return _inputs(raw)

def _host_receipt(expected: dict) -> dict:
    return {"schema": "mastermind.dsh_native_host_prepared.v1", "donor_sha": access.PIN,
            "patch_sha256": expected["patch_sha256"], "source_files": len(expected["source_sha256"]),
            "output_sha256": expected["output_sha256"], "installed": False, "provider_calls": 0}

def receipt(expected: dict, native_host: dict) -> dict:
    return {"schema": "mastermind.dsh_native_owner_package.v1",
            "host": _host_receipt(native_host), "access": access.prepared_receipt(expected),
            "installed": False, "provider_calls": 0}

def package(release: Path, donor: Path) -> dict:
    """Apply both exact patches once to the packager's original owned app tree."""
    raw = {key: (access.ROOT / Path(name).name).read_bytes() for key, name in FILES.items()}
    expected, native_host = _inputs(raw)
    host_receipt = host.apply_to_owned_tree(release / "app", donor)
    access_receipt = access.apply_to_owned_tree(release / "app", donor)
    value = receipt(expected, native_host)
    if (value["host"] != host_receipt or value["access"] != access_receipt
            or any((access.ROOT / Path(FILES[key]).name).read_bytes() != before for key, before in raw.items())):
        raise ValueError("native owner source changed during packaging")
    target = release / "native-owner-access-receipt.json"
    with target.open("x") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
    return {"source_sha256": digest(raw["access_source"]), "patch_sha256": expected["patch_sha256"],
            "host_source_sha256": digest(raw["host_source"]), "host_patch_sha256": native_host["patch_sha256"],
            "receipt_sha256": access.sha(target)}

def verify(release: Path, config: dict, accepted: dict, source_repo: Path, source_sha: str) -> dict[str, str]:
    # Historical accepted packages retain their original source qualification.
    if "native_owner_access" not in config and "native_owner_access" not in accepted:
        return {}
    identity = config.get("native_owner_access")
    if (type(identity) is not dict or set(identity) != IDENTITY_FIELDS
            or any(type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value) for value in identity.values())
            or identity != accepted.get("native_owner_access")):
        raise ValueError("native owner access differs from protected build qualification")
    from ops.executive_os.install_source_policy import read_source_blob
    raw = {key: read_source_blob(source_repo, source_sha, name)
           for key, name in FILES.items()}
    expected, native_host = _inputs(raw)
    target = release / "native-owner-access-receipt.json"
    if (identity["source_sha256"] != digest(raw["access_source"])
            or identity["patch_sha256"] != expected["patch_sha256"]
            or identity["host_source_sha256"] != digest(raw["host_source"])
            or identity["host_patch_sha256"] != native_host["patch_sha256"]
            or target.resolve(strict=True) != target or access.sha(target) != identity["receipt_sha256"]
            or json.loads(target.read_bytes()) != receipt(expected, native_host)):
        raise ValueError("native owner package receipt differs from protected source")
    final = {**native_host["source_sha256"], **native_host["output_sha256"],
             **expected["base_sha256"], **expected["output_sha256"]}
    for name, expected_digest in final.items():
        path = release / "app" / name
        if path.resolve(strict=True) != path or access.sha(path) != expected_digest:
            raise ValueError("native owner package source differs from protected patch")
    return final
