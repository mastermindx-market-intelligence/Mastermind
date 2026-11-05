#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd -P)"
if [ "$#" -ne 4 ]; then
  echo "usage: $0 RUNTIME_ROOT CACHE_ROOT EXACT_NODE EXACT_NPM_CLI" >&2
  exit 64
fi
runtime_root="$1"
cache_root="$2"
node_candidate="$3"
npm_cli_candidate="$4"

case "$runtime_root" in
  /Volumes/Mastermind/worker-browser-b1/runtime) ;;
  *) echo "refusing non-canonical Worker Browser runtime root" >&2; exit 64 ;;
esac
case "$cache_root" in
  /Volumes/Mastermind/*) ;;
  *) echo "refusing npm cache outside /Volumes/Mastermind" >&2; exit 64 ;;
esac
case "$node_candidate" in
  /*) ;;
  *) echo "refusing non-absolute Node executable" >&2; exit 64 ;;
esac
case "$npm_cli_candidate" in
  /*) ;;
  *) echo "refusing non-absolute npm CLI" >&2; exit 64 ;;
esac

runtime_container="/Volumes/Mastermind/worker-browser-b1"
if [ -L "$runtime_container" ] || [ -L "$runtime_root" ]; then
  echo "refusing symlinked runtime container" >&2
  exit 64
fi
if [ ! -e "$runtime_container" ]; then
  /usr/bin/install -d -m 0700 "$runtime_container"
fi
if [ ! -e "$runtime_container/artifacts" ]; then
  /usr/bin/install -d -m 0700 "$runtime_container/artifacts"
fi
if [ ! -e "$runtime_root" ]; then
  /usr/bin/install -d -m 0700 "$runtime_root"
fi
tmp_install="$runtime_root/tmp-install"
tmp_identity="$(
  /usr/bin/env -i \
    HOME="$runtime_root" \
    LANG=C \
    LC_ALL=C \
    PATH=/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    /usr/bin/python3 -I -S -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from control_plane.worker_browser_b1 import prepare_runtime_install_tmp
device, inode = prepare_runtime_install_tmp(Path(sys.argv[2]))
print(f"{device}:{inode}")
' "$repo_root" "$runtime_root"
)"
case "$tmp_identity" in
  *:*) ;;
  *) echo "refusing invalid runtime install TMPDIR identity" >&2; exit 64 ;;
esac
tmp_device="${tmp_identity%%:*}"
tmp_inode="${tmp_identity##*:}"

cleanup_install_tmp() {
  cleanup_status="$?"
  trap - EXIT
  if ! /usr/bin/env -i \
    HOME="$runtime_root" \
    LANG=C \
    LC_ALL=C \
    PATH=/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR="$tmp_install" \
    /usr/bin/python3 -I -S -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from control_plane.worker_browser_b1 import cleanup_runtime_install_tmp
cleanup_runtime_install_tmp(Path(sys.argv[2]), (int(sys.argv[3]), int(sys.argv[4])))
' "$repo_root" "$runtime_root" "$tmp_device" "$tmp_inode"; then
    exit 70
  fi
  exit "$cleanup_status"
}
trap cleanup_install_tmp EXIT

node_executable="$(
  /usr/bin/env -i \
    HOME="$runtime_root" \
    LANG=C \
    LC_ALL=C \
    PATH=/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR="$tmp_install" \
    /usr/bin/python3 -I -S -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$node_candidate"
)"
npm_cli="$(
  /usr/bin/env -i \
    HOME="$runtime_root" \
    LANG=C \
    LC_ALL=C \
    PATH=/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR="$tmp_install" \
    /usr/bin/python3 -I -S -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$npm_cli_candidate"
)"
if [ "$node_candidate" != "$node_executable" ] || [ ! -f "$node_executable" ] || [ ! -x "$node_executable" ] || [ -L "$node_executable" ]; then
  echo "refusing unresolved, mutable, or non-executable Node identity" >&2
  exit 64
fi
if [ "$npm_cli_candidate" != "$npm_cli" ] || [ ! -f "$npm_cli" ] || [ ! -r "$npm_cli" ] || [ -L "$npm_cli" ]; then
  echo "refusing unresolved or unreadable npm CLI identity" >&2
  exit 64
fi

/usr/bin/install -d -m 0700 \
  "$runtime_root/bin" \
  "$runtime_root/lib" \
  "$runtime_root/home" \
  "$cache_root"
if [ -e "$runtime_root/bin/libnode.147.dylib" ] || [ -L "$runtime_root/bin/libnode.147.dylib" ]; then
  echo "refusing loader-path Node dynamic library shadow" >&2
  exit 64
fi
# Node's executable has one relative Mach-O dependency.  Keep that exact
# execution-critical libnode beside the copied executable under the same sealed
# runtime.  Absolute Homebrew/macOS dylib dependencies remain the explicit
# trusted-host-base assumption for the later real-runtime ratification gate.
# The validator requires exactly @rpath/libnode.147.dylib and the two reviewed
# loader search paths before any copied Node byte is executed.
case "$node_executable" in
  /opt/homebrew/Cellar/node/*/bin/node) ;;
  *) echo "refusing Node outside an exact Homebrew Cellar identity" >&2; exit 64 ;;
esac
node_cellar_root="${node_executable%/bin/node}"
node_library_source="$node_cellar_root/lib/libnode.147.dylib"
if [ ! -f "$node_library_source" ] || [ ! -r "$node_library_source" ] || [ -L "$node_library_source" ]; then
  echo "refusing unavailable or linked Node dynamic library" >&2
  exit 64
fi
validate_node_macho_pair() {
  local validated_node="$1"
  local validated_library="$2"
  local validated_node_dependencies
  local validated_node_load_commands
  local validated_library_dependencies
  validated_node_dependencies="$(
    /usr/bin/env -i LANG=C LC_ALL=C PATH=/usr/bin:/bin \
      /usr/bin/otool -L "$validated_node"
  )"
  validated_node_load_commands="$(
    /usr/bin/env -i LANG=C LC_ALL=C PATH=/usr/bin:/bin \
      /usr/bin/otool -l "$validated_node"
  )"
  validated_library_dependencies="$(
    /usr/bin/env -i LANG=C LC_ALL=C PATH=/usr/bin:/bin \
      /usr/bin/otool -L "$validated_library"
  )"
  /usr/bin/env -i \
    HOME="$runtime_root" \
    LANG=C \
    LC_ALL=C \
    PATH=/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR="$tmp_install" \
    /usr/bin/python3 -I -S -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from control_plane.worker_browser_b1 import validate_node_macho_dependency_closure
validate_node_macho_dependency_closure(
    node_path=Path(sys.argv[2]),
    library_path=Path(sys.argv[3]),
    node_dependencies=sys.argv[4],
    node_load_commands=sys.argv[5],
    library_dependencies=sys.argv[6],
)
' "$repo_root" \
    "$validated_node" \
    "$validated_library" \
    "$validated_node_dependencies" \
    "$validated_node_load_commands" \
    "$validated_library_dependencies"
}
validate_node_macho_pair "$node_executable" "$node_library_source"
browser_root="$runtime_root/browsers"
/usr/bin/install -d -m 0700 "$browser_root"
/usr/bin/install -m 0600 \
  "$repo_root/integrations/worker_browser_runtime/package.json" \
  "$runtime_root/package.json"
/usr/bin/install -m 0600 \
  "$repo_root/integrations/worker_browser_runtime/package-lock.json" \
  "$runtime_root/package-lock.json"

/usr/bin/env -i \
  HOME="$runtime_root/home" \
  LANG=C \
  LC_ALL=C \
  PATH=/usr/bin:/bin \
  PLAYWRIGHT_BROWSERS_PATH="$runtime_root/browsers" \
  TMPDIR="$tmp_install" \
  "$node_executable" "$npm_cli" ci \
    --prefix "$runtime_root" \
    --cache "$cache_root" \
    --ignore-scripts \
    --no-audit \
    --no-fund

/usr/bin/env -i \
  HOME="$runtime_root/home" \
  LANG=C \
  LC_ALL=C \
  PATH=/usr/bin:/bin \
  PLAYWRIGHT_BROWSERS_PATH="$runtime_root/browsers" \
  TMPDIR="$tmp_install" \
  "$node_executable" "$runtime_root/node_modules/playwright/cli.js" install chromium

version="$(
  /usr/bin/env -i \
    HOME="$runtime_root/home" \
    LANG=C \
    LC_ALL=C \
    PATH=/usr/bin:/bin \
    PLAYWRIGHT_BROWSERS_PATH="$runtime_root/browsers" \
    TMPDIR="$tmp_install" \
    "$node_executable" "$runtime_root/node_modules/@playwright/mcp/cli.js" --version
)"
if [ "$version" != "Version 0.0.79" ]; then
  echo "refusing unexpected Playwright MCP version: $version" >&2
  exit 65
fi
browser_executable="$(
  /usr/bin/env -i \
    HOME="$runtime_root/home" \
    LANG=C \
    LC_ALL=C \
    PATH=/usr/bin:/bin \
    PLAYWRIGHT_BROWSERS_PATH="$runtime_root/browsers" \
    TMPDIR="$tmp_install" \
    "$node_executable" -e "const p=require('$runtime_root/node_modules/playwright-core'); process.stdout.write(p.chromium.executablePath())"
)"
case "$browser_executable" in
  "$browser_root"/chromium-1237/*) ;;
  *) echo "refusing unexpected Chromium revision path" >&2; exit 66 ;;
esac
if [ ! -x "$browser_executable" ] || [ -L "$browser_executable" ]; then
  echo "refusing unsafe Chromium executable" >&2
  exit 66
fi
browser_sha256="$(
  /usr/bin/env -i \
    HOME="$runtime_root" \
    LANG=C \
    LC_ALL=C \
    PATH=/usr/bin:/bin \
    TMPDIR="$tmp_install" \
    /usr/bin/shasum -a 256 "$browser_executable" | /usr/bin/awk '{print $1}'
)"

launcher="$runtime_root/bin/worker-browser-b1-launcher"
/usr/bin/env -i \
  HOME="$runtime_root" \
  LANG=C \
  LC_ALL=C \
  PATH=/usr/bin:/bin \
  PYTHONDONTWRITEBYTECODE=1 \
  TMPDIR="$tmp_install" \
  /usr/bin/python3 -I -S - "$launcher" "$runtime_root/worker-browser-b1-install-manifest.json" <<'PY'
import json
import os
import sys
from pathlib import Path

launcher = Path(sys.argv[1])
manifest_path = os.path.realpath(sys.argv[2])
template = r'''#!/bin/sh
set -eu
if [ "$#" -ne 0 ]; then
  echo "refusing unbound Worker Browser launcher invocation" >&2
  exit 64
fi
exec /usr/bin/env -i \
  HOME="${MASTERMIND_BROWSER_ARTIFACT_DIR:?}/home" \
  LANG=C \
  LC_ALL=C \
  MASTERMIND_BROWSER_ARTIFACT_DIR="${MASTERMIND_BROWSER_ARTIFACT_DIR:?}" \
  MASTERMIND_BROWSER_FIXTURE_A_URL="${MASTERMIND_BROWSER_FIXTURE_A_URL:?}" \
  MASTERMIND_BROWSER_FIXTURE_B_URL="${MASTERMIND_BROWSER_FIXTURE_B_URL:?}" \
  MASTERMIND_BROWSER_FIXTURE_NONCE="${MASTERMIND_BROWSER_FIXTURE_NONCE:?}" \
  MASTERMIND_BROWSER_ORIGIN="${MASTERMIND_BROWSER_ORIGIN:?}" \
  MASTERMIND_BROWSER_PROXY_URL="${MASTERMIND_BROWSER_PROXY_URL:?}" \
  MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD="${MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD:?}" \
  MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH="${MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH:?}" \
  MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256="${MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256:?}" \
  MASTERMIND_BROWSER_RUNTIME_ROOT="${MASTERMIND_BROWSER_RUNTIME_ROOT:?}" \
  MASTERMIND_BROWSER_WORKSPACE_PATH="${MASTERMIND_BROWSER_WORKSPACE_PATH:?}" \
  PATH=/usr/bin:/bin \
  PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:?}" \
  /usr/bin/python3 -I -S -c '
import hashlib
import json
import os
import runpy
import stat
import sys
from pathlib import Path

container_fd_text = os.environ["MASTERMIND_BROWSER_RUNTIME_CONTAINER_FD"]
manifest = Path(os.environ["MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH"])
expected_digest = os.environ["MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256"]
logical_launcher = Path(bytes.fromhex("__LAUNCHER_PATH_HEX__").decode("utf-8"))
no_follow = getattr(os, "O_NOFOLLOW", None)
if type(no_follow) is not int or no_follow == 0:
    raise SystemExit("runtime launcher requires O_NOFOLLOW support")
try:
    container_fd = int(container_fd_text)
    container_info = os.fstat(container_fd)
    cwd_info = os.stat(".", follow_symlinks=False)
except (OSError, TypeError, ValueError) as exc:
    raise SystemExit("runtime container descriptor unavailable") from exc
if container_fd < 3 or not os.get_inheritable(container_fd):
    raise SystemExit("runtime container descriptor is not inherited")
if manifest != Path(bytes.fromhex("__MANIFEST_PATH_HEX__").decode("utf-8")) or len(expected_digest) != 64:
    raise SystemExit("runtime manifest binding is not exact")
try:
    descriptor = os.open(
        "runtime/worker-browser-b1-install-manifest.json",
        os.O_RDONLY | no_follow,
        dir_fd=container_fd,
    )
    try:
        info = os.fstat(descriptor)
        payload = b""
        while len(payload) <= 4194304:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            payload += chunk
        final_info = os.fstat(descriptor)
    finally:
        os.close(descriptor)
except OSError as exc:
    raise SystemExit("runtime manifest unavailable") from exc
if (
    not stat.S_ISREG(info.st_mode)
    or info.st_nlink != 1
    or info.st_uid != os.geteuid()
    or stat.S_IMODE(info.st_mode) != 0o400
    or not 0 < len(payload) <= 4194304
    or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    != (final_info.st_dev, final_info.st_ino, final_info.st_size, final_info.st_mtime_ns)
    or hashlib.sha256(payload).hexdigest() != expected_digest
):
    raise SystemExit("runtime manifest pre-import attestation failed")
try:
    value = json.loads(payload.decode("utf-8"))
    container_row = value["runtime_container"]
    launcher_row = value["launcher"]
    launcher_descriptor = os.open(
        "runtime/bin/worker-browser-b1-launcher",
        os.O_RDONLY | no_follow,
        dir_fd=container_fd,
    )
    try:
        launcher_info = os.fstat(launcher_descriptor)
        launcher_payload = b""
        while len(launcher_payload) <= 65536:
            chunk = os.read(launcher_descriptor, 65536)
            if not chunk:
                break
            launcher_payload += chunk
        launcher_final_info = os.fstat(launcher_descriptor)
    finally:
        os.close(launcher_descriptor)
except (KeyError, OSError, UnicodeError, ValueError) as exc:
    raise SystemExit("launcher identity unavailable") from exc
if (
    payload != json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
    or set(container_row) != {"device", "gid", "inode", "mode", "uid"}
    or any(type(container_row[key]) is not int for key in container_row)
    or container_row
    != {
        "device": container_info.st_dev,
        "gid": container_info.st_gid,
        "inode": container_info.st_ino,
        "mode": stat.S_IMODE(container_info.st_mode),
        "uid": container_info.st_uid,
    }
    or container_info.st_uid != os.geteuid()
    or stat.S_IMODE(container_info.st_mode) != 0o500
    or (cwd_info.st_dev, cwd_info.st_ino)
    != (container_info.st_dev, container_info.st_ino)
    or set(launcher_row) != {"gid", "mode", "path", "sha256", "uid"}
    or Path(launcher_row["path"]) != logical_launcher
    or not stat.S_ISREG(launcher_info.st_mode)
    or launcher_info.st_nlink != 1
    or not 0 < len(launcher_payload) <= 65536
    or (
        launcher_info.st_dev,
        launcher_info.st_ino,
        launcher_info.st_size,
        launcher_info.st_mtime_ns,
    )
    != (
        launcher_final_info.st_dev,
        launcher_final_info.st_ino,
        launcher_final_info.st_size,
        launcher_final_info.st_mtime_ns,
    )
    or launcher_info.st_uid != os.geteuid()
    or launcher_info.st_uid != launcher_row["uid"]
    or launcher_info.st_gid != launcher_row["gid"]
    or stat.S_IMODE(launcher_info.st_mode) != 0o500
    or launcher_row["mode"] != 0o500
    or hashlib.sha256(launcher_payload).hexdigest() != launcher_row["sha256"]
):
    raise SystemExit("launcher pre-import attestation failed")
workspace = Path(os.environ["MASTERMIND_BROWSER_WORKSPACE_PATH"]).resolve(strict=True)
os.chdir(workspace)
if workspace != Path.cwd().resolve(strict=True):
    raise SystemExit("workspace binding drifted")
os.set_inheritable(container_fd, True)
sys.path.insert(0, os.fspath(workspace))
sys.argv = [
    "control_plane.worker_browser_b1",
    "launch-mcp-from-attempt-env",
]
runpy.run_module("control_plane.worker_browser_b1", run_name="__main__")
'
'''
source = template.replace(
    "__MANIFEST_PATH_HEX__", manifest_path.encode("utf-8").hex()
).replace(
    "__LAUNCHER_PATH_HEX__", os.fspath(launcher).encode("utf-8").hex()
).encode("utf-8")
launcher.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
temporary = launcher.with_name(f".{launcher.name}.{os.getpid()}.tmp")
no_follow = getattr(os, "O_NOFOLLOW", None)
directory_flag = getattr(os, "O_DIRECTORY", None)
if (
    type(no_follow) is not int
    or no_follow == 0
    or type(directory_flag) is not int
    or directory_flag == 0
):
    raise SystemExit("runtime installer requires no-follow directory support")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | no_follow
descriptor = os.open(temporary, flags, 0o500)
try:
    with os.fdopen(descriptor, "wb", closefd=True) as handle:
        handle.write(source)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o500)
    os.replace(temporary, launcher)
    parent_descriptor = os.open(
        launcher.parent,
        os.O_RDONLY | directory_flag | no_follow,
    )
    try:
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)
finally:
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
PY

mcp_executable="$(
  /usr/bin/env -i \
    HOME="$runtime_root" \
    LANG=C \
    LC_ALL=C \
    PATH=/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR="$tmp_install" \
    /usr/bin/python3 -I -S -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$runtime_root/node_modules/@playwright/mcp/cli.js"
)"
/bin/chmod 0500 "$mcp_executable" "$browser_executable"
/bin/chmod 0400 "$runtime_root/package-lock.json"

# Installation uses only the exact externally attested Homebrew Node and its
# explicit trusted-host dynamic-library base.  The governed runtime copy is
# created only after every install-time Node invocation and after the launcher
# exists.  Nothing executes the copied Node until the manifest writer has
# sealed bin/, lib/, runtime/, and the runtime container against replacement.
/usr/bin/install -m 0500 "$node_executable" "$runtime_root/bin/node"
if ! /usr/bin/cmp -s "$node_executable" "$runtime_root/bin/node"; then
  echo "refusing inexact sealed Node copy" >&2
  exit 64
fi
/usr/bin/install -m 0400 "$node_library_source" \
  "$runtime_root/lib/libnode.147.dylib"
node_library="$runtime_root/lib/libnode.147.dylib"
if ! /usr/bin/cmp -s "$node_library_source" "$node_library"; then
  echo "refusing inexact sealed Node dynamic library copy" >&2
  exit 64
fi

runtime_manifest="$runtime_root/worker-browser-b1-install-manifest.json"
# write_runtime_install_manifest records tmp_install_postcondition=absent only
# after removing the exact TMPDIR inode captured above.
runtime_manifest_sha256="$(
  /usr/bin/env -i \
    HOME="$runtime_root" \
    LANG=C \
    LC_ALL=C \
    PATH=/usr/bin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR="$tmp_install" \
    /usr/bin/python3 -I -S -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from control_plane.worker_browser_b1 import write_runtime_install_manifest
print(
    write_runtime_install_manifest(
        manifest_path=Path(sys.argv[2]),
        runtime_root=Path(sys.argv[3]),
        launcher=Path(sys.argv[4]),
        node=Path(sys.argv[5]),
        node_library=Path(sys.argv[6]),
        mcp=Path(sys.argv[7]),
        package_lock=Path(sys.argv[8]),
        browser=Path(sys.argv[9]),
        tmp_identity=(int(sys.argv[10]), int(sys.argv[11])),
    )
)
' "$repo_root" \
    "$runtime_manifest" \
    "$runtime_root" \
    "$launcher" \
    "$runtime_root/bin/node" \
    "$node_library" \
    "$mcp_executable" \
    "$runtime_root/package-lock.json" \
    "$browser_executable" \
    "$tmp_device" \
    "$tmp_inode"
)"
trap - EXIT

# Revalidate the copied Mach-O pair only after the full execution-bearing
# parent chain is sealed, then verify the entire closed runtime receipt without
# executing any copied runtime component.  The governed Attempt is the first
# consumer allowed to execute runtime/bin/node.
validate_node_macho_pair "$runtime_root/bin/node" "$node_library"
/usr/bin/env -i \
  HOME="$runtime_root" \
  LANG=C \
  LC_ALL=C \
  PATH=/usr/bin:/bin \
  PYTHONDONTWRITEBYTECODE=1 \
  TMPDIR="$tmp_install" \
  /usr/bin/python3 -I -S -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from control_plane.worker_browser_b1 import load_runtime_install_attestation
load_runtime_install_attestation(
    Path(sys.argv[2]),
    manifest_path=Path(sys.argv[3]),
    expected_manifest_digest=sys.argv[4],
)
' "$repo_root" \
    "$runtime_root" \
    "$runtime_manifest" \
    "$runtime_manifest_sha256"

echo "WORKER_BROWSER_B1_RUNTIME_READY package=@playwright/mcp version=0.0.79 browser=chromium revision=1237 browser_sha256=$browser_sha256 runtime_manifest=$runtime_manifest runtime_manifest_sha256=$runtime_manifest_sha256 root=$runtime_root"
