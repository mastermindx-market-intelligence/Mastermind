"""Build a non-installed HAE candidate in a NEW directory from pinned source.

Only effort.py and the exact-route request guard are patched; HAE remains the sole middleware and scorer owner.
The native Hermes plugin installer/activation owner must consume the result.
This builder never modifies a live profile, starts Hermes, or calls a provider.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

UPSTREAM = "c84f1389670cdd5ec4607b13bd32c4809878c415"
EFFORT_BLOB = "f8b63e02f868ec7354027384585ba91ddf389738"
MIDDLEWARE_BLOB = "0dfb76d4f8a63c61e0f5dc28dba604e3da6b2bcb"
MANIFEST_BLOB = "4c989330a925086955a55e5bdd4eff838ed76ed2"
ANCHOR = '''    provider_name = (provider or "").strip().lower()
    api = (api_mode or "").strip().lower()
    model_id = (model or "").strip().lower()
    bare = model_id.rsplit("/", 1)[-1]
    levels: Sequence[str] = ()'''
INSERTION = '''    # Mastermind compatibility extension; same HAE middleware and scorer.
    from .mastermind_zai import direct_zai_levels
    direct_levels = direct_zai_levels(provider, model, api_mode, base_url)
    if direct_levels:
        return direct_levels
'''


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def patched_effort(raw: bytes) -> bytes:
    if blob(raw) != EFFORT_BLOB:
        raise ValueError("HAE_EFFORT_REVISION_MISMATCH")
    text = raw.decode("utf-8")
    if text.count(ANCHOR) != 1:
        raise ValueError("HAE_EFFORT_ANCHOR_MISMATCH")
    return text.replace(ANCHOR, INSERTION + ANCHOR, 1).encode("utf-8")


def patched_middleware(raw: bytes) -> bytes:
    if blob(raw) != MIDDLEWARE_BLOB:
        raise ValueError("HAE_MIDDLEWARE_REVISION_MISMATCH")
    anchor = 'def _handle(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:\n'
    guard = ('    from .mastermind_zai import direct_zai_request_allowed\n'
             '    if not direct_zai_request_allowed(kwargs.get("provider"), kwargs.get("model"),\n'
             '                                      kwargs.get("api_mode"), kwargs.get("base_url")):\n'
             '        return None\n')
    text = raw.decode("utf-8")
    if text.count(anchor) != 1:
        raise ValueError("HAE_MIDDLEWARE_ANCHOR_MISMATCH")
    return text.replace(anchor, anchor + guard, 1).encode("utf-8")


def stage(source: Path, output: Path) -> dict:
    source = source.resolve(strict=True)
    if not source.is_dir() or output.exists() or output.is_symlink():
        raise ValueError("NEW_STAGE_DIRECTORY_REQUIRED")
    target = output.resolve(strict=False)
    if source == target or source in target.parents:
        raise ValueError("STAGE_MUST_NOT_BE_INSIDE_SOURCE")
    for parent in target.parents:
        if (parent / "config.yaml").exists() and (parent / "plugins").is_dir():
            raise ValueError("STAGE_MUST_NOT_BE_INSIDE_HERMES_PROFILE")
    # This is a build input, not a credential or profile source. Refuse symlinks
    # and profile-state filenames so they cannot accidentally enter the payload.
    for entry in source.rglob("*"):
        if entry.is_symlink():
            raise ValueError("SOURCE_SYMLINK_NOT_SUPPORTED")
        if entry.name in (".env", "auth.json", "config.yaml", "gateway.lock"):
            raise ValueError("PROFILE_DATA_NOT_BUILD_INPUT")
    manifest = (source / "plugin.yaml").read_bytes()
    if blob(manifest) != MANIFEST_BLOB:
        raise ValueError("HAE_MANIFEST_REVISION_MISMATCH")
    replacement = patched_effort((source / "effort.py").read_bytes())
    middleware = patched_middleware((source / "middleware.py").read_bytes())
    extension = Path(__file__).with_name("hae_zai_extension.py").read_bytes()
    shutil.copytree(source, output, ignore=shutil.ignore_patterns(
        ".git", ".github", "__pycache__", ".pytest_cache", ".venv", ".worktrees"))
    # Only the new, non-serving build directory is changed. A partial build is
    # left for inspection on error; never overwrite/retry an existing stage.
    (output / "effort.py").write_bytes(replacement)
    (output / "middleware.py").write_bytes(middleware)
    (output / "mastermind_zai.py").write_bytes(extension)
    receipt = {
        "schema": "mastermind.hermes_omh.hae_candidate/v1",
        "state": "BUILT_NOT_INSTALLED", "upstream_commit": UPSTREAM,
        "extension": "direct-zai-glm-5.3-named-choices-v1",
        "upstream_effort_blob": EFFORT_BLOB,
        "manifest_blob": MANIFEST_BLOB,
        "upstream_middleware_blob": MIDDLEWARE_BLOB,
        "patched_middleware_sha256": hashlib.sha256(middleware).hexdigest(),
        "patched_effort_sha256": hashlib.sha256(replacement).hexdigest(),
        "extension_sha256": hashlib.sha256(extension).hexdigest(),
        "installed": False, "activated": False, "provider_proven": False,
        "note": "Changed-file preimages are verified; this is not a signed full-tree attestation.",
    }
    (output / "MMX_BUILD.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = stage(args.source, args.output)
    except (OSError, ValueError, UnicodeError):
        print(json.dumps({"state": "BUILD_FAILED_OR_REFUSED", "installed": False, "partial_stage_may_exist": True}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
