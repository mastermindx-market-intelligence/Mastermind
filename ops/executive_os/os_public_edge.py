"""Inert, closed-route public OS edge staging; never installs or reloads Caddy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from integrations.mastermind_executive_app.os_assets import os_asset_mimes

HOST = "mcp.mastermind-x.com"
POST_ROUTES = ("/os/executive/context", "/os/executive/submit", "/os/executive/status")
GET_ROUTES = (
    "/os/", "/os/auth/callback", "/workspace/programs/current",
    "/workspace/work/current", "/workspace/mission/current",
    "/workspace/mission/v3/current", "/workspace/result/current",
    "/workspace/window/current",
)
_TEMPLATE = Path(__file__).with_name("os_public_edge.caddy.template")


def asset_routes(manifest: object) -> tuple[str, ...]:
    if (type(manifest) is not dict or set(manifest) != {"schema", "files"}
            or manifest["schema"] != "mastermind.os_assets.v1"
            or type(manifest["files"]) is not list):
        raise ValueError("OS edge manifest refused")
    files = manifest["files"]
    if any(type(item) is not dict or set(item) != {"path", "byte_count", "sha256", "mime"}
           or type(item["path"]) is not str for item in files):
        raise ValueError("OS edge manifest entry refused")
    # One owner of the 3/9-file topology, exact names and MIME types. In
    # particular, no arbitrary path can become executable Caddy syntax.
    mimes = os_asset_mimes([item["path"] for item in files])
    for item in files:
        if (type(item["byte_count"]) is not int or not 0 < item["byte_count"] <= 4 * 1024 * 1024
                or type(item["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                or item["mime"] != mimes[item["path"]]):
            raise ValueError("OS edge manifest metadata refused")
    return tuple(sorted("/os/" if item["path"] == "index.html" else "/os/" + item["path"] for item in files))


def render(manifest: object, relay_port: int) -> str:
    if type(relay_port) is not int or not 49152 <= relay_port <= 50200:
        raise ValueError("OS edge relay port refused")
    routes = asset_routes(manifest)
    template = _TEMPLATE.read_text(encoding="utf-8")
    if template.count("__ASSET_PATHS__") != 1 or template.count("__RELAY_PORT__") != 2:
        raise ValueError("OS edge template differs")
    return template.replace("__ASSET_PATHS__", " ".join(routes)).replace("__RELAY_PORT__", str(relay_port))


def stage(*, manifest: object, relay_port: int, output: Path) -> dict:
    content = render(manifest, relay_port).encode("utf-8")
    parent = output.parent
    info = parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022 or parent.resolve() != parent:
        raise ValueError("OS edge output directory refused")
    # Exclusive creation preserves any existing artifact, including dangling
    # symlinks. No replace/reload is part of this inert staging capability.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # A failed write stays visible for reconciliation; never silently
        # delete an artifact after an uncertain filesystem effect.
        raise
    return {
        "schema": "mastermind.os_public_edge.stage.v1",
        "sha256": hashlib.sha256(content).hexdigest(),
        "relay_port": relay_port,
        "routes": {"get": sorted(set(GET_ROUTES) | set(asset_routes(manifest))), "post": list(POST_ROUTES)},
        "installed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--relay-port", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    from ops.executive_os.executive_mcp_entry import build_os_asset_manifest
    actual = build_os_asset_manifest(args.source)
    supplied = json.loads((args.source / "app/mastermind_os/dist/asset-manifest.json").read_bytes())
    if supplied != actual:
        raise ValueError("OS edge source manifest differs from built bytes")
    print(json.dumps(stage(manifest=actual, relay_port=args.relay_port, output=args.out), sort_keys=True))


if __name__ == "__main__":
    main()
