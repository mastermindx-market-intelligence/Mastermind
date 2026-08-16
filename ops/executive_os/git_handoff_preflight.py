"""One-shot distinct-UID macOS Gate B for Executive Git shared-handoff.

This diagnostic creates one unique proof workspace as the control principal,
observes it through the production service Git observer, then runs the
production worker Git preflight as the worker principal.  It is not a daemon,
does not allocate Codex, and must not race live Executive LaunchDaemons.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pwd
import grp
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "mastermind.executive_git_handoff_preflight/v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_PROBE_ID_RE = re.compile(r"^gate-b-[0-9a-f]{12}$")
_PYTHON_RUNTIME_RECEIPT = Path(
    "/Library/Application Support/MastermindExecutive/python-runtime.json"
)
_REFUSAL_DETAIL_LIMIT = 300


def _acceptance_module():
    existing = sys.modules.get("executive_acceptance")
    if existing is not None:
        return existing
    path = Path(__file__).with_name("acceptance.py")
    spec = importlib.util.spec_from_file_location("executive_acceptance", path)
    if spec is None or spec.loader is None:
        raise PreflightError("acceptance identity module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PreflightError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def bounded_text(value: str, *, limit: int = _REFUSAL_DETAIL_LIMIT) -> str:
    acceptance = _acceptance_module()
    return acceptance._sanitize_refusal_fragment(value, secrets_to_redact=())


def require_probe_id(value: str) -> str:
    probe_id = str(value).strip()
    if _PROBE_ID_RE.fullmatch(probe_id) is None:
        raise PreflightError("unsafe generated probe id")
    return probe_id


def new_probe_id() -> str:
    return require_probe_id(f"gate-b-{secrets.token_hex(6)}")


def require_darwin_root() -> None:
    if sys.platform != "darwin":
        raise PreflightError("Gate B requires darwin")
    if os.geteuid() != 0:
        raise PreflightError("Gate B requires euid 0")


def require_distinct_identities(*, control_user: str, worker_user: str) -> dict[str, Any]:
    control = pwd.getpwnam(control_user)
    worker = pwd.getpwnam(worker_user)
    if control.pw_uid == worker.pw_uid:
        raise PreflightError("control and worker UIDs must differ")
    if control.pw_gid == worker.pw_gid and control.pw_uid == worker.pw_uid:
        raise PreflightError("control and worker identities must differ")
    return {
        "control": {
            "user": control_user,
            "uid": int(control.pw_uid),
            "gid": int(control.pw_gid),
            "home": control.pw_dir,
        },
        "worker": {
            "user": worker_user,
            "uid": int(worker.pw_uid),
            "gid": int(worker.pw_gid),
            "home": worker.pw_dir,
            "supplementary_gids": sorted(
                {int(group.gr_gid) for group in grp.getgrall() if worker_user in group.gr_mem}
                | {int(worker.pw_gid)}
            ),
        },
    }


def require_release_sha(release_root: Path, expected_sha: str) -> Path:
    sha = str(expected_sha).strip().lower()
    if _SHA_RE.fullmatch(sha) is None:
        raise PreflightError("release SHA must be a 40-character lowercase hex object id")
    root = Path(release_root).resolve(strict=False)
    if root.name != sha:
        raise PreflightError("release directory is not the exact expected SHA")
    if not root.is_dir() or root.is_symlink():
        raise PreflightError("release directory must be a real directory")
    return root


def require_workspace_root_metadata(path: Path, *, control_uid: int) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise PreflightError("proof workspace root is unavailable") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != int(control_uid)
        or stat.S_IMODE(info.st_mode) & 0o007
        or stat.S_IMODE(info.st_mode) & 0o020
    ):
        raise PreflightError("unsafe workspace-root refusal")


def snapshot_workspace_root(path: Path) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    for name in sorted(os.listdir(path)):
        child = path / name
        info = child.lstat()
        children.append(
            {
                "name": name,
                "device": int(info.st_dev),
                "inode": int(info.st_ino),
                "uid": int(info.st_uid),
                "gid": int(info.st_gid),
                "mode": stat.S_IMODE(info.st_mode),
                "symlink": bool(stat.S_ISLNK(info.st_mode)),
            }
        )
    return children


def workspace_root_restored(
    before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> bool:
    return before == after


def file_content_sha256(path: Path) -> str:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PreflightError("persistent Git config must be a regular file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_metadata(path: Path) -> dict[str, Any]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise PreflightError(".git/index must be a regular non-symlink file")
    return {
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "uid": int(info.st_uid),
        "gid": int(info.st_gid),
        "mode": stat.S_IMODE(info.st_mode),
        "size": int(info.st_size),
        "mtime_ns": int(info.st_mtime_ns),
        "nlink": int(info.st_nlink),
        "sha256": file_content_sha256(path),
    }


def index_handoff_ok(meta: Mapping[str, Any], *, control_uid: int, shared_gid: int) -> bool:
    mode = int(meta["mode"])
    return (
        int(meta["uid"]) == int(control_uid)
        and int(meta["gid"]) == int(shared_gid)
        and bool(mode & stat.S_IRGRP)
        and not mode & stat.S_IWGRP
        and not mode & stat.S_IRWXO
        and int(meta.get("nlink", 1)) == 1
    )


def index_observation_stable(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> bool:
    return all(before.get(key) == after.get(key) for key in before)


def persistent_config_unchanged(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> bool:
    return before == after


def config_identity(path: Path) -> dict[str, Any]:
    info = path.lstat()
    return {
        "sha256": file_content_sha256(path),
        "uid": int(info.st_uid),
        "gid": int(info.st_gid),
        "mode": stat.S_IMODE(info.st_mode),
    }


def cleanup_plan(
    *,
    workspace: Path,
    workspace_root: Path,
    supervisor_home_existed: bool,
    supervisor_home: Path,
) -> dict[str, Any]:
    return {
        "workspace": str(workspace.name),
        "remove_workspace": True,
        "touch_supervisor_home": not supervisor_home_existed,
        "supervisor_home": supervisor_home.name,
        "workspace_root": str(workspace_root),
    }


def validate_worker_preflight_receipt(payload: Mapping[str, Any], *, expected_sha: str) -> None:
    if payload.get("passed") is not True:
        raise PreflightError("worker preflight did not pass")
    if str(payload.get("head") or "").lower() != expected_sha.lower():
        raise PreflightError("worker preflight HEAD is not the expected SHA")
    if int(payload.get("remote_count", -1)) != 0:
        raise PreflightError("worker preflight observed remotes")
    if payload.get("launch_clean") is not True:
        raise PreflightError("worker preflight was not launch-clean")
    if payload.get("persistent_trust_changed") is True:
        raise PreflightError("worker preflight changed persistent Git trust")


def failure_receipt(*, release_sha: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": False,
        "observed_at": now_iso(),
        "release_sha": release_sha,
        "error": bounded_text(reason),
    }


def validate_receipt(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise PreflightError("receipt schema is not Gate B v1")
    if not isinstance(payload.get("passed"), bool):
        raise PreflightError("receipt passed flag is missing")
    if payload.get("passed") is True:
        for key in (
            "release_sha",
            "control",
            "worker",
            "workspace",
            "index_before_service_observation",
            "index_after_service_observation",
            "index_after_worker_preflight",
            "git",
            "persistent_config_unchanged",
            "worker_preflight_passed",
            "workspace_root_restored",
            "stimulus_used",
        ):
            if key not in payload:
                raise PreflightError(f"receipt missing {key}")


def _load_json(path: Path) -> dict[str, Any]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PreflightError(f"unsafe JSON file: {path.name}")
    try:
        value = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"invalid JSON file: {path.name}") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"JSON file is not an object: {path.name}")
    return value


def _installed_python(release: Path) -> Path:
    receipt = _load_json(_PYTHON_RUNTIME_RECEIPT)
    binary = Path(str(receipt.get("python_binary") or ""))
    if not binary.is_file() or binary.is_symlink():
        raise PreflightError("installed Python binary is unavailable")
    return binary


def _launchd_loaded(label: str) -> bool:
    completed = subprocess.run(
        ["/bin/launchctl", "print", f"system/{label}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=15,
    )
    return completed.returncode == 0


def _require_services_stopped(acceptance: Any) -> None:
    loaded = [
        label
        for label in (acceptance.CONTROL_LABEL, acceptance.WORKER_LABEL)
        if _launchd_loaded(label)
    ]
    if loaded:
        raise PreflightError(
            "Executive LaunchDaemons must be stopped before Gate B: " + ",".join(loaded)
        )


def _service_environment(user: str, home: Path) -> list[str]:
    return [
        "/usr/bin/sudo",
        "-u",
        user,
        "/usr/bin/env",
        "-i",
        f"HOME={home}",
        "PYTHONDONTWRITEBYTECODE=1",
        "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "TZ=UTC",
    ]


def _child_json(
    *,
    python: Path,
    release: Path,
    user: str,
    home: Path,
    code: str,
    args: list[str],
    timeout: float,
    label: str,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            *_service_environment(user, home),
            os.fspath(python),
            "-I",
            "-S",
            "-B",
            "-c",
            "import sys; sys.path.insert(0,sys.argv.pop(1)); " + code,
            os.fspath(release),
            *args,
        ],
        cwd=os.fspath(release),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = bounded_text(
            (completed.stderr or completed.stdout).decode("utf-8", errors="replace")
        )
        raise PreflightError(f"{label} failed with exit {completed.returncode}: {detail}")
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"{label} did not emit JSON") from exc
    if not isinstance(payload, dict):
        raise PreflightError(f"{label} JSON was not an object")
    return payload


def _cleanup(
    *,
    workspace: Path | None,
    workspace_root: Path,
    supervisor_home: Path,
    supervisor_home_existed: bool,
    before: list[dict[str, Any]],
    control_uid: int,
) -> bool:
    if workspace is not None and workspace.exists():
        shutil.rmtree(workspace, ignore_errors=False)
    if not supervisor_home_existed:
        if supervisor_home.exists():
            info = supervisor_home.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != int(control_uid)
                or stat.S_IMODE(info.st_mode) != 0o700
                or os.listdir(supervisor_home)
            ):
                raise PreflightError(
                    "probe-created supervisor home is not a private empty directory"
                )
            supervisor_home.rmdir()
    after = snapshot_workspace_root(workspace_root)
    if not workspace_root_restored(before, after):
        raise PreflightError("workspace root was not restored after Gate B cleanup")
    return True


def run_preflight(*, expected_sha: str) -> dict[str, Any]:
    require_darwin_root()
    acceptance = _acceptance_module()
    identities = require_distinct_identities(
        control_user=acceptance.CONTROL_USER,
        worker_user=acceptance.WORKER_USER,
    )
    grp.getgrnam(acceptance.CONTROL_GROUP)
    grp.getgrnam(acceptance.WORKER_GROUP)
    grp.getgrnam(acceptance.OPS_GROUP)
    release = require_release_sha(
        acceptance.SYSTEM_ROOT / "releases" / expected_sha, expected_sha
    )
    config = _load_json(acceptance.CONTROL_CONFIG)
    if str(config.get("proof_base_sha") or "").lower() != expected_sha.lower():
        raise PreflightError("installed control config proof SHA is not the expected SHA")
    source = Path(str(config["proof_source_repository"])).resolve(strict=True)
    workspace_root = Path(str(config["proof_workspace_root"])).resolve(strict=True)
    require_workspace_root_metadata(
        workspace_root, control_uid=identities["control"]["uid"]
    )
    if source.name != expected_sha:
        raise PreflightError("proof source repository is not the exact expected source")
    _require_services_stopped(acceptance)
    python = _installed_python(release)
    probe_id = new_probe_id()
    branch = f"codex/{probe_id}"
    supervisor_home = workspace_root / ".supervisor-home"
    supervisor_home_existed = supervisor_home.exists()
    before = snapshot_workspace_root(workspace_root)
    workspace: Path | None = None
    try:
        control_payload = _run_control_child(
            python=python,
            release=release,
            user=acceptance.CONTROL_USER,
            home=Path(identities["control"]["home"]),
            source=source,
            workspace_root=workspace_root,
            probe_id=probe_id,
            base_sha=expected_sha,
            branch=branch,
            shared_gid=int(config["shared_run_gid"]),
            runtime_root=Path(str(config["runtime_root"])),
            socket_path=Path(str(config["control_socket_path"])),
        )
        workspace = Path(control_payload["workspace"])
        git_config = workspace / ".git" / "config"
        config_before = config_identity(git_config)
        worker_home_gitconfig = Path(identities["worker"]["home"]) / ".gitconfig"
        worker_home_gitconfig_existed = worker_home_gitconfig.exists()
        worker_payload = _run_worker_child(
            python=python,
            release=release,
            user=acceptance.WORKER_USER,
            home=Path(identities["worker"]["home"]),
            workspace=workspace,
            expected_sha=expected_sha,
        )
        validate_worker_preflight_receipt(worker_payload, expected_sha=expected_sha)
        config_after = config_identity(git_config)
        if worker_home_gitconfig.exists() != worker_home_gitconfig_existed:
            raise PreflightError("worker probe created a persistent ~/.gitconfig")
        index_after_worker = index_metadata(workspace / ".git" / "index")
        before_index = control_payload["index_before_service_observation"]
        after_index = control_payload["index_after_service_observation"]
        if not index_handoff_ok(
            before_index,
            control_uid=identities["control"]["uid"],
            shared_gid=int(config["shared_run_gid"]),
        ) or not index_handoff_ok(
            after_index,
            control_uid=identities["control"]["uid"],
            shared_gid=int(config["shared_run_gid"]),
        ) or not index_handoff_ok(
            index_after_worker,
            control_uid=identities["control"]["uid"],
            shared_gid=int(config["shared_run_gid"]),
        ):
            raise PreflightError("shared index DAC is not worker-readable after observation")
        if not index_observation_stable(before_index, after_index):
            raise PreflightError("service observation mutated .git/index metadata")
        if (workspace / ".git" / "index.lock").exists():
            raise PreflightError(".git/index.lock exists after Gate B")
        observed = control_payload["observed"]
        restored = _cleanup(
            workspace=workspace,
            workspace_root=workspace_root,
            supervisor_home=supervisor_home,
            supervisor_home_existed=supervisor_home_existed,
            before=before,
            control_uid=identities["control"]["uid"],
        )
        workspace = None
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "passed": True,
            "observed_at": now_iso(),
            "release_sha": expected_sha,
            "control": identities["control"],
            "worker": identities["worker"],
            "workspace": {
                "path": Path(control_payload["workspace"]).name,
                "uid": observed["uid"],
                "gid": observed["gid"],
                "mode": observed["mode"],
            },
            "index_before_service_observation": before_index,
            "index_after_service_observation": after_index,
            "index_after_worker_preflight": index_after_worker,
            "git": {
                "head": observed["head"],
                "branch": observed["branch"],
                "remote_count": observed["remote_count"],
                "status_dirty": observed["status_dirty"],
                "all_untracked_dirty": observed["all_untracked_dirty"],
                "launch_clean": observed["launch_clean"],
            },
            "persistent_config_unchanged": persistent_config_unchanged(
                config_before, config_after
            ),
            "worker_preflight_passed": True,
            "workspace_root_restored": restored,
            "stimulus_used": control_payload.get(
                "stimulus_used", "natural-post-share-stat-cache"
            ),
        }
        if receipt["persistent_config_unchanged"] is not True:
            raise PreflightError("workspace .git/config changed during Gate B")
        validate_receipt(receipt)
        return receipt
    except Exception:
        try:
            _cleanup(
                workspace=workspace,
                workspace_root=workspace_root,
                supervisor_home=supervisor_home,
                supervisor_home_existed=supervisor_home_existed,
                before=before,
                control_uid=identities["control"]["uid"],
            )
        except Exception as cleanup_exc:
            raise PreflightError(
                f"cleanup failed closed: {bounded_text(str(cleanup_exc))}"
            ) from cleanup_exc
        raise

def _run_control_child(
    *,
    python: Path,
    release: Path,
    user: str,
    home: Path,
    source: Path,
    workspace_root: Path,
    probe_id: str,
    base_sha: str,
    branch: str,
    shared_gid: int,
    runtime_root: Path,
    socket_path: Path,
) -> dict[str, Any]:
    code = (
        "import importlib.util,json,os,sys; "
        "from pathlib import Path; "
        "os.umask(0o077); "
        "mod_path=Path(sys.path[0])/'ops'/'executive_os'/'git_handoff_preflight.py'; "
        "spec=importlib.util.spec_from_file_location('git_handoff_preflight', mod_path); "
        "helpers=importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers); "
        "from control_plane.executive_service import ExecutiveControlService, ServiceConfig; "
        "from control_plane.executive_workspace import prepare_credentialless_clone; "
        "source,root,job_id,base_sha,branch,shared_gid,runtime_root,socket_path=sys.argv[1:9]; "
        "receipt=prepare_credentialless_clone(source,root,job_id=job_id,base_sha=base_sha,"
        "branch=branch,shared_gid=int(shared_gid)); "
        "workspace=Path(receipt.workspace_path); "
        "index=workspace/'.git'/'index'; "
        "before=helpers.index_metadata(index); "
        "config=ServiceConfig(runtime_root=Path(runtime_root),socket_path=Path(socket_path),"
        "proof_source_repository=Path(source),proof_workspace_root=Path(root),"
        "proof_base_sha=base_sha,proof_branch='codex/phase1c-a-proof',"
        "proof_shared_gid=int(shared_gid)); "
        "service=ExecutiveControlService(config); "
        "observed=service._workspace_observation(workspace,require_fresh=True,"
        "expected_branch=branch); "
        "after=helpers.index_metadata(index); "
        "print(json.dumps({'workspace':str(workspace),'observed':observed,"
        "'index_before_service_observation':before,"
        "'index_after_service_observation':after,"
        "'stimulus_used':'natural-post-share-stat-cache'},"
        "sort_keys=True,separators=(',',':')))"
    )
    return _child_json(
        python=python,
        release=release,
        user=user,
        home=home,
        code=code,
        args=[
            os.fspath(source),
            os.fspath(workspace_root),
            probe_id,
            base_sha,
            branch,
            str(shared_gid),
            os.fspath(runtime_root),
            os.fspath(socket_path),
        ],
        timeout=180.0,
        label="control UID workspace creation and service observation",
    )


def _run_worker_child(
    *,
    python: Path,
    release: Path,
    user: str,
    home: Path,
    workspace: Path,
    expected_sha: str,
) -> dict[str, Any]:
    code = (
        "import json,sys; "
        "from pathlib import Path; "
        "from control_plane.executive_workspace import observe_launch_cleanliness; "
        "from control_plane.codex_worker import _git_snapshot, _git_command; "
        "workspace=Path(sys.argv[1]); expected=sys.argv[2]; "
        "snapshot=_git_snapshot(workspace, require_clean=True); "
        "remote=_git_command(workspace,'remote'); "
        "clean=observe_launch_cleanliness(lambda arguments: _git_command(workspace, *arguments)); "
        "print(json.dumps({'passed':True,'head':snapshot.head,'expected_head':expected,"
        "'remote_count':len([line for line in remote.decode('utf-8').splitlines() if line]),"
        "'status_dirty':bool(clean.status),'all_untracked_dirty':bool(clean.all_untracked),"
        "'launch_clean':not clean.dirty,'persistent_trust_changed':False},"
        "sort_keys=True,separators=(',',':')))"
    )
    return _child_json(
        python=python,
        release=release,
        user=user,
        home=home,
        code=code,
        args=[os.fspath(workspace), expected_sha],
        timeout=90.0,
        label="worker UID Git preflight",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Executive OS distinct-UID Git handoff Gate B probe."
    )
    parser.add_argument("--expected-sha", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        receipt = run_preflight(expected_sha=args.expected_sha)
    except PreflightError as exc:
        json.dump(
            failure_receipt(release_sha=str(args.expected_sha), reason=str(exc)),
            sys.stdout,
            sort_keys=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return 2
    except Exception as exc:
        json.dump(
            failure_receipt(
                release_sha=str(args.expected_sha),
                reason=f"{type(exc).__name__}: {exc}",
            ),
            sys.stdout,
            sort_keys=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return 2
    json.dump(receipt, sys.stdout, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
