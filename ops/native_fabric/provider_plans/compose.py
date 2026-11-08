"""Compose the provider-plan integration over the exact selected native source.

This is offline source assembly. Publication and CAS selection remain owned by
the existing native_generation publisher; this module cannot select a release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def digest(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("source must be a regular file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose(base, output, *, profile_name="provider-plans"):
    if profile_name == "provider-plans":
        profile_root = HERE
    elif profile_name == "current116-maintenance-guard":
        profile_root = HERE / "maintenance_guard"
    elif profile_name == "current116-remote-placement":
        profile_root = HERE / "remote_placement"
    else:
        raise ValueError("unknown native source profile")
    profile = json.loads((profile_root / "profile.json").read_text())
    release = json.loads((base / "RELEASE.json").read_text())
    if (release.get("digest") != profile["base_selection"]["generation"]
            or release.get("files") != profile["base_files"]):
        raise ValueError("selected native base changed; recompose against its actual source")
    if output.exists() or output.is_symlink():
        raise ValueError("composition output must be new")
    for relative, expected in profile["base_files"].items():
        if digest(base / relative) != expected:
            raise ValueError("native preimage mismatch: " + relative)
    for name, row in profile["patches"].items():
        if (row["before"] != profile["base_files"].get(name)
                or row["after"] != profile["files"].get(name)):
            raise ValueError("patch metadata differs from verified file closure")
        if digest(HERE / row["patch"]) != row["patch_sha256"]:
            raise ValueError("source patch changed")
    for relative, source in profile["source_map"].items():
        if digest(REPO / source) != profile["files"][relative]:
            raise ValueError("canonical dependency changed: " + source)
    output.mkdir(mode=0o700)
    (output / "ext").mkdir(mode=0o700)
    for relative in profile["base_files"]:
        shutil.copyfile(base / relative, output / relative)
    for row in profile["patches"].values():
        patch = str(HERE / row["patch"])
        subprocess.run(["git", "apply", "--check", patch], cwd=output, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "apply", patch], cwd=output, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for relative, source in profile["source_map"].items():
        shutil.copyfile(REPO / source, output / relative)
    for relative, expected in profile["files"].items():
        if digest(output / relative) != expected:
            raise ValueError("native postimage mismatch: " + relative)
    (output / "FILES.json").write_text(json.dumps(profile["files"], sort_keys=True, indent=2)+"\n")
    return {"state": "SOURCE_COMPOSED", "source": str(output),
            "base_generation": release["digest"], "files": len(profile["files"]),
            "publication_performed": False, "selection_performed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("provider-plans", "current116-maintenance-guard", "current116-remote-placement"),
                        default="provider-plans")
    args = parser.parse_args()
    print(json.dumps(compose(args.base, args.output, profile_name=args.profile), sort_keys=True))


if __name__ == "__main__":
    main()
