"""Keep the original ACP lifecycle patch in the complete native application package."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from . import prepare_native_acp as native

PREFIX = "integrations/deepseek_harness/runtime_compat/"
FILES = {"source": PREFIX + "native-acp-source.json", "patch": PREFIX + "native-acp-lifecycle.patch"}
KEY = "native_acp_patch"
IDENTITY_FIELDS = frozenset(("source_sha256", "patch_sha256", "receipt_sha256"))


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate(raw: bytes, patch: bytes) -> dict:
    value = json.loads(raw)
    if (type(value) is not dict or value.get("schema") != "mastermind.dsh_native_acp_source.v1"
            or value.get("donor_sha") != native.PIN or value.get("production_armed") is not False
            or type(value.get("source_sha256")) is not dict or type(value.get("output_sha256")) is not dict
            or set(value["output_sha256"]) != native.CHANGED
            or not native.CHANGED <= set(value["source_sha256"])
            or not 3 <= len(value["source_sha256"]) <= 256
            or digest(patch) != value.get("patch_sha256")):
        raise ValueError("native ACP package source refused")
    for mapping in ("source_sha256", "output_sha256"):
        for name, expected in value[mapping].items():
            path = PurePosixPath(name)
            if (path.is_absolute() or ".." in path.parts
                    or not any(name.startswith(package + "/src/") for package in native.PACKAGES)
                    or path.suffix not in (".ts", ".tsx") or type(expected) is not str
                    or re.fullmatch("[0-9a-f]{64}", expected) is None):
                raise ValueError("native ACP package source path refused")
    lines = patch.decode().splitlines()
    if ({line[6:] for line in lines if line.startswith("+++ b/")} != native.CHANGED
            or {line[6:] for line in lines if line.startswith("--- a/")} != native.CHANGED):
        raise ValueError("native ACP package patch scope refused")
    return value


def qualify_inputs() -> dict:
    raw = {key: (native.ROOT / Path(name).name).read_bytes() for key, name in FILES.items()}
    return validate(raw["source"], raw["patch"])


def receipt(expected: dict) -> dict:
    return {"schema": "mastermind.dsh_native_acp_prepared.v1", "donor_sha": native.PIN,
            "patch_sha256": expected["patch_sha256"], "source_files": len(expected["source_sha256"]),
            "output_sha256": expected["output_sha256"], "installed": False, "provider_calls": 0}


def package(release: Path, donor: Path) -> dict:
    raw = {key: (native.ROOT / Path(name).name).read_bytes() for key, name in FILES.items()}
    expected = validate(raw["source"], raw["patch"])
    observed = native.apply_to_owned_tree(release / "app", donor)
    if (observed != receipt(expected)
            or any((native.ROOT / Path(FILES[key]).name).read_bytes() != before for key, before in raw.items())):
        raise ValueError("native ACP source changed during packaging")
    path = release / "native-acp-receipt.json"
    with path.open("x") as stream:
        stream.write(json.dumps(observed, sort_keys=True) + "\n")
    return {"source_sha256": digest(raw["source"]), "patch_sha256": expected["patch_sha256"],
            "receipt_sha256": native.sha(path)}


def verify(release: Path, config: dict, accepted: dict, source_repo: Path, source_sha: str) -> None:
    if KEY not in config and KEY not in accepted:
        return
    identity = config.get(KEY)
    if (type(identity) is not dict or set(identity) != IDENTITY_FIELDS
            or any(type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None for value in identity.values())
            or identity != accepted.get(KEY)):
        raise ValueError("native ACP package differs from protected build qualification")
    from ops.executive_os.install_source_policy import read_source_blob
    raw = {key: read_source_blob(source_repo, source_sha, name) for key, name in FILES.items()}
    expected = validate(raw["source"], raw["patch"])
    path = release / "native-acp-receipt.json"
    if (path.resolve(strict=True) != path
            or identity["source_sha256"] != digest(raw["source"])
            or identity["patch_sha256"] != expected["patch_sha256"]
            or identity["receipt_sha256"] != native.sha(path)
            or json.loads(path.read_bytes()) != receipt(expected)):
        raise ValueError("native ACP receipt differs from protected source")
    for name, before in expected["source_sha256"].items():
        path = release / "app" / name
        if (path.resolve(strict=True) != path
                or native.sha(path) != expected["output_sha256"].get(name, before)):
            raise ValueError("native ACP package source differs from protected patch")
