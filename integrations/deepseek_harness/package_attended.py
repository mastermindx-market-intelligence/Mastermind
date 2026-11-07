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


def inventory_identity(root):
    """Capture direct file/link/directory identities around the full-byte read."""
    result = {}
    for parent, dirs, files in os.walk(root, followlinks=False):
        for path in [Path(parent), *(Path(parent) / name for name in dirs + files)]:
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            result[relative] = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                                os.readlink(path) if stat.S_ISLNK(info.st_mode) else None)
    return result


QUALIFIED_BUILD_PATH = "integrations/deepseek_harness/attended-build.json"


def protected_build(source_repo, source_sha):
    """Read the accepted build from its one fixed protected source path."""
    raw = subprocess.check_output(["git", "-C", str(source_repo), "show",
                                   source_sha + ":" + QUALIFIED_BUILD_PATH])
    record = json.loads(raw)
    if (type(record) is not dict or record.get("schema") != "mastermind.dsh_attended_build.v1"
            or record.get("donor_sha") != PIN or record.get("installed") is not False
            or record.get("provider_calls") != 0):
        raise ValueError("Protected attended build qualification refused")
    for key in ("package_manifest_sha256", "app_config_sha256", "company_client_sha256",
                "native_client_build_sha256", "index_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", record.get(key, "")):
            raise ValueError("Protected attended build digest refused")
    return raw, record


PUBLICATION_SCHEMA = "mastermind.dsh_attended_publication_bundle.v1"
PUBLICATION_CUSTODY = "root-qualified package snapshot; not a remote signature"


def export_publication(*, release, source_repo, source_sha, out):
    """Verify the complete staged app and capture bounded public asset evidence.

    The existing root publisher owns publication. This export neither starts the
    user app nor installs a service, credential, tunnel, Caddy route or DNS record.
    """
    import sys
    root = HERE.parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from ops.executive_os import os_public_edge_publication as publication
    from ops.executive_os.install_source_policy import validate_acceptance_source
    publication._root()
    source_repo = exact_path(source_repo)
    source_tree = validate_acceptance_source(source_repo=source_repo, expected_sha=source_sha)
    release = exact_path(release)
    out = exact_path(out, exists=False)
    if out.exists() or out.is_relative_to(release):
        raise ValueError("Use a fresh publication export outside the immutable package")
    manifest_path = release / "package-manifest.json"
    if manifest_path.is_symlink() or not 0 < manifest_path.stat().st_size <= 64 * 1024 * 1024:
        raise ValueError("Package manifest custody or budget refused")
    identity = inventory_identity(release)
    manifest_raw = manifest_path.read_bytes()
    build_raw, accepted_build = protected_build(source_repo, source_sha)
    if hashlib.sha256(manifest_raw).hexdigest() != accepted_build["package_manifest_sha256"]:
        raise ValueError("Package manifest differs from protected build qualification")
    # The launcher uses the same manifest. Full verification stays at this
    # qualification boundary, never on every browser launch.
    manifest = json.loads(manifest_raw)
    if (manifest.get("schema") != "mastermind.dsh_attended_package_closure.v1"
            or manifest.get("donor_sha") != PIN or type(manifest.get("files")) is not dict):
        raise ValueError("Full native package manifest required")
    observed = inventory(release)
    observed.pop("package-manifest.json", None)
    if observed != manifest["files"] or manifest_path.read_bytes() != manifest_raw:
        raise ValueError("Full native package closure changed")
    config = json.loads((release / "app.json").read_bytes())
    for name, key in (("app.json", "app_config_sha256"),
                      ("company_plugin/lib/client.js", "company_client_sha256"),
                      ("app/.dsh-build/client-build-environment.json", "native_client_build_sha256"),
                      ("app/apps/web/dist/index.html", "index_sha256")):
        if sha(release / name) != accepted_build[key]:
            raise ValueError("Captured artifact differs from protected build qualification")
    if (config.get("schema") != "mastermind.dsh_attended_package.v1"
            or config.get("release") != str(release) or config.get("donor_sha") != PIN
            or config.get("public_url") != "https://chat.mastermind-x.com/"
            or config.get("port") != 4180 or config.get("relay_port") != 4181
            or config.get("execution") != "native-attended"
            or config.get("company_worker_admission") is not False):
        raise ValueError("Exact attended app publication binding required")
    company = release / "company_plugin/lib"
    build = json.loads((company / "build-manifest.json").read_bytes())
    if (build.get("schema") != "mastermind.dsh.company_build.v1" or build.get("donor_sha") != PIN
            or build.get("client_sha256") != sha(company / "client.js")
            or build["client_sha256"] != config["company_client_sha256"]):
        raise ValueError("Company client qualification differs")
    for name, expected in build["source_sha256"].items():
        if not re.fullmatch(r"src/(?:client/)?[a-z.-]+\.ts", name):
            raise ValueError("Company source path refused")
        raw = subprocess.check_output(["git", "-C", str(source_repo), "show",
            source_sha + ":integrations/deepseek_harness/company_plugin/" + name])
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Company client source differs from protected source")
    launcher = subprocess.check_output(["git", "-C", str(source_repo), "show",
        source_sha + ":integrations/deepseek_harness/launch_attended.mjs"])
    if (release / "launch_attended.mjs").read_bytes() != launcher:
        raise ValueError("Native launcher differs from protected source")
    expected_patch = [{"insert": [{"id": "mastermind-company",
        "name": str(company / "index.js"), "config": {}}]}]
    if (json.loads((release / "company.patch.yml").read_bytes()) != expected_patch
            or sha(release / "company.patch.yml") != config["company_patch_sha256"]
            or sha(release / "app/.dsh-build/client-build-environment.json")
               != config["native_client_build_sha256"]):
        raise ValueError("Native company overlay or client build differs")
    dist = release / "app/apps/web/dist"
    index = (dist / "index.html").read_text()
    captures, rows = {}, []
    for suffix, mime in (("js", "text/javascript"), ("css", "text/css")):
        candidates = set(re.findall(r'["\'](?:\.)?(/assets/index-[A-Za-z0-9_-]+\.' + suffix + r')["\']', index))
        if len(candidates) != 1:
            raise ValueError("Exactly one native index asset per type required")
        url = candidates.pop()
        file = dist / url.removeprefix("/")
        relative = file.relative_to(release).as_posix()
        raw = file.read_bytes()
        expected = manifest["files"].get(relative, {})
        if (not 0 < len(raw) <= publication.MAX_BYTES or
                hashlib.sha256(raw).hexdigest() != expected.get("sha256")):
            raise ValueError("Native public asset differs from full package")
        label = "client." + suffix + ".blob"
        captures[label] = raw
        rows.append({"url": url, "mime": mime, "bytes": len(raw),
                     "sha256": hashlib.sha256(raw).hexdigest(), "capture": label})
    record = {
        "schema": PUBLICATION_SCHEMA, "custody": PUBLICATION_CUSTODY,
        "source": {"sha": source_sha, "tree": source_tree}, "donor_sha": PIN,
        "host": "chat.mastermind-x.com", "native_port": 4180, "relay_port": 4181,
        "package_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "build_qualification_sha256": hashlib.sha256(build_raw).hexdigest(),
        "package_entries": len(manifest["files"]),
        "app_config_sha256": sha(release / "app.json"),
        "company_client_sha256": build["client_sha256"],
        "company_patch_sha256": config["company_patch_sha256"],
        "native_client_build_sha256": config["native_client_build_sha256"],
        "assets": rows, "installed": False, "public_route_qualified": False,
        "provider_calls": 0,
    }
    if (manifest_path.read_bytes() != manifest_raw or inventory_identity(release) != identity
            or validate_acceptance_source(source_repo=source_repo, expected_sha=source_sha) != source_tree):
        raise ValueError("Package or protected source changed during qualification")
    publication._new_directory(out)
    with publication.private(out) as area:
        for name, raw in captures.items():
            area.write(name, raw)
        raw = publication.canonical(record)
        area.write("artifact-receipt.json", raw)
    return {"schema": PUBLICATION_SCHEMA, "state": "EXPORTED", "export": str(out),
            "artifact_digest": publication.digest(raw), "installed": False}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "export-publication":
        parser = argparse.ArgumentParser(description="Qualify and export native public assets")
        for name in ("release", "source-repo", "source-sha", "out"):
            parser.add_argument("--" + name, required=True)
        print(json.dumps(export_publication(**vars(parser.parse_args(sys.argv[2:]))), sort_keys=True))
        raise SystemExit(0)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", required=True)
    parser.add_argument("--pnpm", required=True, help="Absolute installed pnpm 11.28.5 bin/pnpm.cjs")
    parser.add_argument("--release", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--public-url", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--relay-port", required=True, type=int)
    print(json.dumps(stage(parser.parse_args()), sort_keys=True))
