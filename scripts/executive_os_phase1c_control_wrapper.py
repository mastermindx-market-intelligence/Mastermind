"""Inject one private control-only canary before execing the control service."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import stat
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.codex_worker import ProcessInspector  # noqa: E402


SCHEMA_VERSION = "mastermind.executive_control_environment_attestation/v1"
SENTINEL_NAME = "EXECUTIVE_CONTROL_CANARY_VALUE"
_VALUE_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_IDENTITY_TEXT_BYTES = 256
_MAX_EXECUTABLE_PATH_BYTES = 4096


# W1H3F R13 (Sol R80, PR #677 comment 5704046553): the closed field sets are
# owned by THIS module and nowhere else.  H3 must NOT restate them.  They are
# derived from the document ``attest_current_service_environment`` constructs.
ATTESTATION_FIELDS = frozenset(
    {
        "schema_version",
        "observed_at",
        "process_identity",
        "config_sha256",
        "release_manifest_sha256",
        "release_commit_sha",
        "python_executable_path",
        "python_executable_sha256",
        "sentinel_name_sha256",
        "sentinel_value_sha256",
        "sentinel_present",
    }
)
PROCESS_IDENTITY_FIELDS = frozenset(
    {
        "pid",
        "pgid",
        "session_id",
        "start_identity",
        "boot_id",
        "effective_uid",
        "effective_gid",
        "real_uid",
        "real_gid",
    }
)


class ControlWrapperError(RuntimeError):
    pass


def _contains_control_character(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _bounded_identity_integer(
    value: object, *, name: str, minimum: int
) -> int:
    if type(value) is not int or not (minimum <= value <= 2**31 - 1):
        raise ControlWrapperError(
            f"attestation process identity fact {name} is not a bounded integer"
        )
    return value


def _bounded_identity_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ControlWrapperError(
            f"attestation process identity fact {name} is not a non-empty string"
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ControlWrapperError(
            f"attestation process identity fact {name} is not valid UTF-8"
        ) from exc
    if (
        len(encoded) > _MAX_IDENTITY_TEXT_BYTES
        or _contains_control_character(value)
    ):
        raise ControlWrapperError(
            f"attestation process identity fact {name} is not bounded safe text"
        )
    return value


def _canonical_executable_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ControlWrapperError(
            "attestation python_executable_path is not a canonical absolute POSIX path"
        )
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ControlWrapperError(
            "attestation python_executable_path is not valid UTF-8"
        ) from exc
    if (
        len(encoded) > _MAX_EXECUTABLE_PATH_BYTES
        or _contains_control_character(value)
        or not os.path.isabs(value)
        or value.startswith("//")
        or os.path.normpath(value) != value
        or not Path(value).name
    ):
        raise ControlWrapperError(
            "attestation python_executable_path is not a canonical absolute POSIX path"
        )
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _private_file(
    path: Path,
    *,
    owner_uid: int,
    group_gid: int,
    exact_mode: int,
    maximum: int,
) -> bytes:
    if not path.is_absolute():
        raise ControlWrapperError("private input path must be absolute")
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != owner_uid
        or info.st_gid != group_gid
        or stat.S_IMODE(info.st_mode) != exact_mode
        or info.st_size > maximum
    ):
        raise ControlWrapperError("private input file does not match the installed policy")
    with path.open("rb") as handle:
        value = handle.read(maximum + 1)
    if len(value) > maximum:
        raise ControlWrapperError("private input file exceeds its size limit")
    return value


def _write_attestation(path: Path, value: dict[str, object]) -> None:
    if not path.is_absolute():
        raise ControlWrapperError("attestation path must be absolute")
    parent = path.parent.resolve(strict=True)
    parent_info = parent.lstat()
    if (
        stat.S_ISLNK(parent_info.st_mode)
        or not stat.S_ISDIR(parent_info.st_mode)
        or parent_info.st_uid != os.geteuid()
        or stat.S_IMODE(parent_info.st_mode) & 0o077
    ):
        raise ControlWrapperError("attestation directory is not control-owned and private")
    temporary = parent / f".{path.name}.{os.getpid()}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o400,
    )
    try:
        payload = (
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode("utf-8")
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short control attestation write")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(temporary, 0o400)
    os.replace(temporary, path)


def validate_control_environment_attestation(
    document: object,
    *,
    expected_config_sha256: str,
    expected_release_commit_sha: str,
    expected_pid: int,
    inspector: ProcessInspector,
) -> dict[str, object]:
    """Wrapper-owned fail-closed validator for the post-restart attestation.

    Sol R80 (PR #677 comment 5704046553): the fixed label + fixed socket +
    AWAITING_CANARY probe proves LIVENESS only -- it does NOT prove the
    restarted process consumed the exact candidate/restored control bytes.
    Disk agreement cannot close that gap after a no-effect ``kickstart -k``.
    The validator below is the wrapper's smallest lawful repair: ONE pure,
    import-safe, fail-closed validator that the CEO-admission probe in H3
    consumes before it returns ``True``.

    It raises :class:`ControlWrapperError` on ANY failure and returns the
    validated document on success.  It does NOT read the filesystem,
    spawn processes, or mutate ``document``; the inspector is the only
    injection point (tests inject a fake, production passes a real
    :class:`control_plane.codex_worker.ProcessInspector`).
    """

    if not isinstance(document, dict):
        raise ControlWrapperError("attestation document must be a dict")
    if set(document) != ATTESTATION_FIELDS:
        raise ControlWrapperError("attestation field set is not the exact closed set")
    if document["schema_version"] != SCHEMA_VERSION:
        raise ControlWrapperError("attestation schema_version is not the live wrapper schema")
    observed_at = document["observed_at"]
    if not isinstance(observed_at, str):
        raise ControlWrapperError("attestation observed_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(observed_at)
    except ValueError as exc:
        raise ControlWrapperError("attestation observed_at is not parseable ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ControlWrapperError("attestation observed_at is not a UTC timestamp")
    identity = document["process_identity"]
    if not isinstance(identity, dict) or set(identity) != PROCESS_IDENTITY_FIELDS:
        raise ControlWrapperError("attestation process_identity is not the exact closed set")
    pid = _bounded_identity_integer(identity["pid"], name="pid", minimum=1)
    for integer_name in ("pgid", "session_id"):
        _bounded_identity_integer(identity[integer_name], name=integer_name, minimum=1)
    for integer_name in ("effective_uid", "effective_gid", "real_uid", "real_gid"):
        _bounded_identity_integer(identity[integer_name], name=integer_name, minimum=0)
    for text_name in ("start_identity", "boot_id"):
        _bounded_identity_text(identity[text_name], name=text_name)
    if pid != expected_pid:
        raise ControlWrapperError("attestation pid does not match the live process pid")
    try:
        observed = inspector.inspect(pid)
        boot_id = inspector.boot_session_id()
    except Exception as exc:  # inspector is the ONLY injection point
        raise ControlWrapperError(
            "attestation fresh observation is unavailable"
        ) from exc
    identity_facts = {
        "pgid": observed.pgid,
        "session_id": observed.session_id,
        "start_identity": observed.start_identity,
        "effective_uid": observed.effective_uid,
        "effective_gid": observed.effective_gid,
        "real_uid": observed.real_uid,
        "real_gid": observed.real_gid,
    }
    for fact_name, observed_value in identity_facts.items():
        if identity[fact_name] != observed_value:
            raise ControlWrapperError(
                f"attestation process identity fact {fact_name} is stale"
            )
    if identity["boot_id"] != boot_id:
        raise ControlWrapperError("attestation boot identity is stale")
    if (
        not isinstance(expected_config_sha256, str)
        or _VALUE_RE.fullmatch(expected_config_sha256) is None
        or document["config_sha256"] != expected_config_sha256
    ):
        raise ControlWrapperError("attestation config_sha256 is not the live config digest")
    if (
        not isinstance(expected_release_commit_sha, str)
        or _COMMIT_RE.fullmatch(expected_release_commit_sha) is None
        or not isinstance(document["release_commit_sha"], str)
        or _COMMIT_RE.fullmatch(document["release_commit_sha"]) is None
        or document["release_commit_sha"] != expected_release_commit_sha
    ):
        raise ControlWrapperError(
            "attestation release_commit_sha is not the live release sha"
        )
    for digest_field in (
        "release_manifest_sha256",
        "python_executable_sha256",
        "sentinel_name_sha256",
        "sentinel_value_sha256",
    ):
        digest_value = document[digest_field]
        if (
            not isinstance(digest_value, str)
            or _VALUE_RE.fullmatch(digest_value) is None
        ):
            raise ControlWrapperError(
                f"attestation {digest_field} is not 64 lowercase hex"
            )
    _canonical_executable_path(document["python_executable_path"])
    if document["sentinel_present"] is not True:
        raise ControlWrapperError("attestation sentinel_present is not exactly True")
    return document


def attest_current_service_environment(
    *,
    config_path: Path,
    attestation_path: Path,
    release: Path,
    sentinel: str,
) -> dict[str, object]:
    """Write the post-exec positive observation for the live service process."""

    config = json.loads(config_path.read_text(encoding="utf-8"))
    manifest = release / ".executive-release-manifest.json"
    manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
    inspector = ProcessInspector()
    identity = inspector.inspect(os.getpid())
    executable = Path(sys.executable).resolve(strict=True)
    attestation: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "observed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "process_identity": {
            "pid": os.getpid(),
            "pgid": identity.pgid,
            "session_id": identity.session_id,
            "start_identity": identity.start_identity,
            "boot_id": inspector.boot_session_id(),
            "effective_uid": identity.effective_uid,
            "effective_gid": identity.effective_gid,
            "real_uid": identity.real_uid,
            "real_gid": identity.real_gid,
        },
        "config_sha256": _sha256(config_path),
        "release_manifest_sha256": _sha256(manifest),
        "release_commit_sha": manifest_value["commit_sha"],
        "python_executable_path": os.fspath(executable),
        "python_executable_sha256": _sha256(executable),
        "sentinel_name_sha256": hashlib.sha256(SENTINEL_NAME.encode()).hexdigest(),
        "sentinel_value_sha256": hashlib.sha256(sentinel.encode()).hexdigest(),
        "sentinel_present": True,
    }
    if config.get("control_uid") != os.geteuid():
        raise ControlWrapperError("live service config principal differs")
    validate_control_environment_attestation(
        attestation,
        expected_config_sha256=_sha256(config_path),
        expected_release_commit_sha=manifest_value["commit_sha"],
        expected_pid=os.getpid(),
        inspector=inspector,
    )
    _write_attestation(attestation_path, attestation)
    return attestation


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--sentinel-file", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    return parser


def _post_exec_main() -> int:
    """Attest the injected environment, then enter the fixed control service.

    The canary key is assembled after exec so the live process argv contains
    neither its name nor its value.  The worker-principal probe may inspect the
    argv; it must not fail merely because the bootstrap source named the key.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--post-exec", action="store_true", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    args = parser.parse_args()
    release = args.release_root.resolve(strict=True)
    if release != _ROOT or Path.cwd().resolve(strict=True) != release:
        raise ControlWrapperError("post-exec service is outside its installed release")
    sentinel_name = "EXECUTIVE" + "_CONTROL" + "_CANARY" + "_VALUE"
    sentinel = os.environ.get(sentinel_name)
    if not isinstance(sentinel, str) or _VALUE_RE.fullmatch(sentinel) is None:
        raise ControlWrapperError("post-exec control canary is unavailable")
    attest_current_service_environment(
        config_path=args.config,
        attestation_path=args.attestation,
        release=release,
        sentinel=sentinel,
    )
    from scripts.executive_os_phase1c import main as service_main

    return int(
        service_main(
            [
        "serve",
        "--config",
        os.fspath(args.config),
            ]
        )
    )


def main() -> int:
    args = _parser().parse_args()
    try:
        release = args.release_root.resolve(strict=True)
        if release != _ROOT or Path.cwd().resolve(strict=True) != release:
            raise ControlWrapperError("wrapper is not running from its installed release")
        account = pwd.getpwuid(os.geteuid())
        if os.geteuid() == 0 or os.getuid() != os.geteuid():
            raise ControlWrapperError("control wrapper requires one non-root real/effective UID")
        if os.getgid() != os.getegid() or os.getegid() != account.pw_gid:
            raise ControlWrapperError("control wrapper requires its primary real/effective GID")

        config_info = args.config.lstat()
        if (
            stat.S_ISLNK(config_info.st_mode)
            or not stat.S_ISREG(config_info.st_mode)
            or config_info.st_uid != 0
            or config_info.st_gid != account.pw_gid
            or stat.S_IMODE(config_info.st_mode) != 0o440
        ):
            raise ControlWrapperError("control config is not root/control 0440")
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or config.get("control_uid") != os.geteuid():
            raise ControlWrapperError("control config principal does not match the wrapper")
        configured_attestation = config.get("control_environment_attestation_path")
        if configured_attestation != os.fspath(args.attestation):
            raise ControlWrapperError("control attestation path differs from config")

        sentinel_bytes = _private_file(
            args.sentinel_file,
            owner_uid=0,
            group_gid=account.pw_gid,
            exact_mode=0o440,
            maximum=128,
        )
        sentinel = sentinel_bytes.decode("ascii", errors="strict").strip()
        if _VALUE_RE.fullmatch(sentinel) is None:
            raise ControlWrapperError("control canary value is not a nonempty 64-hex sentinel")
        if SENTINEL_NAME in os.environ:
            raise ControlWrapperError("control canary was present before the wrapper boundary")

        manifest = release / ".executive-release-manifest.json"
        manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
        release_info = release.lstat()
        if (
            not isinstance(manifest_value, dict)
            or manifest_value.get("commit_sha") != config.get("proof_base_sha")
            or release_info.st_uid != 0
            or stat.S_IMODE(release_info.st_mode) & 0o022
        ):
            raise ControlWrapperError("release manifest and configured exact SHA differ")
        manifest_info = manifest.lstat()
        if (
            stat.S_ISLNK(manifest_info.st_mode)
            or not stat.S_ISREG(manifest_info.st_mode)
            or manifest_info.st_uid != 0
            or stat.S_IMODE(manifest_info.st_mode) & 0o022
        ):
            raise ControlWrapperError("release manifest file is not root-owned and immutable")
        executable = Path(sys.executable).resolve(strict=True)
        executable_info = executable.lstat()
        if (
            stat.S_ISLNK(executable_info.st_mode)
            or not stat.S_ISREG(executable_info.st_mode)
            or executable_info.st_uid != 0
            or stat.S_IMODE(executable_info.st_mode) & 0o022
        ):
            raise ControlWrapperError("Python executable is not root-owned and immutable")
        environment = {
            "HOME": account.pw_dir,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "NO_COLOR": "1",
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "TZ": "UTC",
            SENTINEL_NAME: sentinel,
        }
        argv = [
            os.fspath(executable),
            "-I",
            "-S",
            "-B",
            os.fspath(Path(__file__).resolve(strict=True)),
            "--post-exec",
            "--config",
            os.fspath(args.config),
            "--attestation",
            os.fspath(args.attestation),
            "--release-root",
            os.fspath(release),
        ]
        os.execve(argv[0], argv, environment)
    except (ControlWrapperError, KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"control wrapper error: {type(exc).__name__}", file=sys.stderr)
        return 2
    raise AssertionError("execve returned")


if __name__ == "__main__":
    raise SystemExit(_post_exec_main() if "--post-exec" in sys.argv[1:] else main())
