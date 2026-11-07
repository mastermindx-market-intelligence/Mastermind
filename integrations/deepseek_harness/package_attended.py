#!/usr/bin/env python3
"""Stage the complete attended native app. No launchd, ingress or provider effect."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
from urllib.parse import urlsplit

PIN = "687f282e8625c6b8d11ff58211a90524be2e4317"
HERE = Path(__file__).resolve().parent


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def exact_path(value, *, exists=True):
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=exists) != path or path == Path("/"):
        raise ValueError("Use one canonical absolute path")
    return path


def origin(value):
    url = urlsplit(value)
    if (url.scheme != "https" or url.username or url.password or url.port
            or url.query or url.fragment or url.path not in ("", "/")
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.mastermind-x\.com", url.netloc)
            or url.netloc == "mcp.mastermind-x.com"):
        raise ValueError("A separate owned HTTPS application origin is required")
    return "https://" + url.netloc + "/"


def inventory(root):
    result = {}
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(parent) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                target = path.resolve(strict=True)
                if not target.is_relative_to(root):
                    raise ValueError("External package symlink refused: " + relative)
                result[relative] = {"symlink": os.readlink(path)}
            elif path.is_file():
                result[relative] = {"sha256": sha(path), "mode": stat.S_IMODE(path.stat().st_mode)}
    return result


def stage(args):
    donor = exact_path(args.donor)
    release = exact_path(args.release, exists=False)
    state = exact_path(args.state, exists=False)
    node = Path(shutil.which("node") or "").resolve(strict=True)
    public_url = origin(args.public_url)
    pnpm = exact_path(args.pnpm)
    if (json.loads((pnpm.parent.parent / "package.json").read_text())["version"] != "11.28.5"):
        raise ValueError("Use the accepted installed pnpm 11.28.5 build tool")
    for port in (args.port, args.relay_port):
        if not 1024 <= port <= 65535:
            raise ValueError("Use an explicit unprivileged local/listener port")
    if release.exists() or state.exists() or release.is_relative_to(donor) or state.is_relative_to(donor):
        raise ValueError("Use fresh separate release and state directories")
    if state.is_relative_to(release) or release.is_relative_to(state):
        raise ValueError("Release and persistent state must be independent")
    git = ["git", "-C", str(donor)]
    if (subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip() != PIN
            or subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()):
        raise ValueError("Exact clean full-app donor required")
    for required in ("apps/cli/lib/bin.js", "apps/web/dist/index.html", "node_modules/.pnpm"):
        if not (donor / required).exists():
            raise ValueError("Build the complete donor before packaging")
    company = HERE / "company_plugin"
    build = json.loads((company / "lib/build-manifest.json").read_text())
    if (build["schema"] != "mastermind.dsh.company_build.v1" or build["donor_sha"] != PIN
            or sha(company / "lib/client.js") != build["client_sha256"]):
        raise ValueError("Compiled company plugin identity mismatch")
    for file, digest in build["source_sha256"].items():
        if not re.fullmatch(r"src/(?:client/)?[a-z.-]+\.ts", file) or sha(company / file) != digest:
            raise ValueError("Company plugin changed after compilation")
    # Inspect links before copying. Nothing is copied from a user credential store.
    for parent, dirs, files in os.walk(donor, followlinks=False):
        dirs[:] = [name for name in dirs if name not in (".git", ".cache", ".turbo")]
        for name in dirs + files:
            path = Path(parent) / name
            if path.is_symlink() and not path.resolve(strict=True).is_relative_to(donor):
                raise ValueError("Donor dependency escapes the package: " + str(path.relative_to(donor)))
    release.mkdir(mode=0o700, parents=True)
    shutil.copytree(donor, release / "app", symlinks=True,
                    ignore=shutil.ignore_patterns(".git", ".cache", ".turbo"))
    # Rebuild only this owned copy through the upstream dependency-aware graph.
    # The native title is a build value, not a DOM override or copied UI owner.
    build_env = {key: os.environ[key] for key in ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "SDKROOT", "DEVELOPER_DIR") if key in os.environ}
    build_env.update(CI="true", DSH_CLIENT_TITLE="Mastermind", DSH_CLIENT_COMMIT_HASH=PIN)
    subprocess.run([str(node), str(pnpm), "run", "build:artifacts"],
                   cwd=release / "app", env=build_env, stdin=subprocess.DEVNULL, check=True)
    native_build = release / "app/.dsh-build/client-build-environment.json"
    built = json.loads(native_build.read_text())
    if built["environment"].get("DSH_CLIENT_TITLE") != "Mastermind":
        raise ValueError("Native company title did not reach the complete client build")
    shutil.copytree(company / "lib", release / "company_plugin/lib")
    shutil.copy2(company / "package.json", release / "company_plugin/package.json")
    shutil.copy2(donor / "LICENSE", release / "UPSTREAM-LICENSE")
    shutil.copy2(HERE / "launch_attended.mjs", release / "launch_attended.mjs")
    for child in ("home", "state/profiles/web", "workspace", "logs"):
        (state / child).mkdir(mode=0o700, parents=True)
    state.chmod(0o700)
    patch = [{"insert": [{"id": "mastermind-company",
                         "name": str(release / "company_plugin/lib/index.js"), "config": {}}]}]
    # The immutable company overlay loads after the editable native profile.
    # Models/settings must remain writable and survive app restarts.
    company_patch = release / "company.patch.yml"
    company_patch.write_text(json.dumps(patch, indent=2) + "\n")
    company_patch.chmod(0o600)
    config = {
        "schema": "mastermind.dsh_attended_package.v1", "donor_sha": PIN,
        "release": str(release), "state": str(state),
        "node": str(node), "node_sha256": sha(node),
        "public_url": public_url, "port": args.port, "relay_port": args.relay_port,
        "company_client_sha256": build["client_sha256"],
        "native_client_build_sha256": sha(native_build),
        "pnpm_sha256": sha(pnpm),
        "company_patch_sha256": sha(company_patch),
        "execution": "native-attended", "company_worker_admission": False,
    }
    (release / "app.json").write_text(json.dumps(config, indent=2) + "\n")
    plist = {
        "Label": "com.mastermind.deepseek.web",
        "ProgramArguments": [str(node), str(release / "launch_attended.mjs")],
        "WorkingDirectory": str(state / "workspace"),
        "RunAtLoad": True, "KeepAlive": False,
        "ProcessType": "Interactive", "Umask": 0o077,
        "StandardOutPath": str(state / "logs/native.stdout.log"),
        "StandardErrorPath": str(state / "logs/native.stderr.log"),
    }
    with (release / "com.mastermind.deepseek.web.plist").open("wb") as stream:
        plistlib.dump(plist, stream)
    host = urlsplit(public_url).hostname
    edge = f"""# Candidate for the incumbent public-edge owner; no route is installed here.
{host} {{
  header {{
    ?Content-Security-Policy "frame-ancestors https://mcp.mastermind-x.com"
    Referrer-Policy "no-referrer"
  }}
  reverse_proxy 127.0.0.1:{args.relay_port} {{
    # Preserve public Host and native WebSocket handling.
    header_up -Forwarded
    header_up -X-Forwarded-Host
    header_up -X-Forwarded-Port
    header_up -X-Real-IP
    header_up -CF-Connecting-IP
    header_up -EO-Connecting-IP
    header_down Set-Cookie "(.*)" "$1; Secure"
  }}
}}
"""
    (release / "public-edge.caddy").write_text(edge)
    (release / "os-build.env").write_text("VITE_MM_DSH_APP_URL=" + public_url + "\n")
    closure = inventory(release)
    manifest = {"schema": "mastermind.dsh_attended_package_closure.v1",
                "donor_sha": PIN, "files": closure, "installed": False}
    (release / "package-manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    return {"release": str(release), "state": str(state), "files": len(closure),
            "package_manifest_sha256": sha(release / "package-manifest.json"),
            "installed": False, "public_route_qualified": False, "provider_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", required=True)
    parser.add_argument("--pnpm", required=True, help="Absolute installed pnpm 11.28.5 bin/pnpm.cjs")
    parser.add_argument("--release", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--relay-port", required=True, type=int)
    print(json.dumps(stage(parser.parse_args()), sort_keys=True))
