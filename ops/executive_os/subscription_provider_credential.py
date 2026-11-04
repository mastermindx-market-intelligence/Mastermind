"""Secret-owning enrollment for reviewed subscription provider worker realms.

This ceremony extends the existing Executive provider-home trust boundary. It
never grants readiness, capacity, route authority, or autonomous execution.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from control_plane.codex_provider_realm import (
    PROVIDER_CREDENTIAL_FILENAME,
    CodexProviderRealm,
    ProviderRealmError,
    validate_provider_credential_format,
)
from control_plane.executive_ambient_process import (
    AmbientProcessClassifier,
    DarwinDistnotedClassifier,
)
from control_plane.fs_security import FilesystemSecurityError, has_macos_acl

MAX_CREDENTIAL_BYTES = 4096


class SubscriptionCredentialError(RuntimeError):
    """Bounded refusal at the subscription credential mutation boundary."""


class SubscriptionCredentialEffectUnknown(SubscriptionCredentialError):
    """The credential replacement may have landed and must be reconciled."""


def _has_macos_acl(
    path: Path,
    *,
    expected_identity: os.stat_result | None = None,
    descriptor: int | None = None,
) -> bool:
    try:
        return has_macos_acl(
            path,
            expected_identity=expected_identity,
            descriptor=descriptor,
        )
    except SubscriptionCredentialError:
        raise
    except FilesystemSecurityError:
        raise SubscriptionCredentialError("credential filesystem metadata unavailable")


def _require_provider_home(config: Mapping[str, Any]) -> Path:
    home = Path(str(config["provider_home"]))
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | os.O_DIRECTORY
    )
    try:
        info = home.lstat()
    except OSError:
        raise SubscriptionCredentialError("provider home is unavailable") from None
    try:
        descriptor = os.open(home, flags)
    except OSError:
        raise SubscriptionCredentialError("provider home is unavailable") from None
    try:
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != int(config["worker_uid"])
            or info.st_gid != int(config["worker_gid"])
            or stat.S_IMODE(info.st_mode) != 0o700
            or _has_macos_acl(
                home,
                expected_identity=info,
                descriptor=descriptor,
            )
        ):
            raise SubscriptionCredentialError("provider home metadata is unsafe")
    except (OSError, SubscriptionCredentialError) as exc:
        if isinstance(exc, SubscriptionCredentialError):
            raise
        raise SubscriptionCredentialError("provider home metadata is unsafe") from None
    finally:
        os.close(descriptor)
    return home


def _open_regular_credential(
    path: Path,
    before: os.stat_result,
    *,
    worker_uid: int,
    worker_gid: int,
) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(path, flags)
    try:
        observed = os.fstat(descriptor)
        if (
            observed.st_dev != before.st_dev
            or observed.st_ino != before.st_ino
            or stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != int(worker_uid)
            or observed.st_gid != int(worker_gid)
            or stat.S_IMODE(observed.st_mode) != 0o600
            or observed.st_nlink != 1
            or observed.st_size < 1
            or observed.st_size > MAX_CREDENTIAL_BYTES
        ):
            raise SubscriptionCredentialError("provider credential metadata is unsafe")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _credential_metadata(path: Path, *, worker_uid: int, worker_gid: int) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError:
        raise SubscriptionCredentialError("provider credential is unavailable") from None
    try:
        descriptor = _open_regular_credential(
            path,
            info,
            worker_uid=worker_uid,
            worker_gid=worker_gid,
        )
    except OSError:
        raise SubscriptionCredentialError("provider credential is unavailable") from None
    try:
        if _has_macos_acl(
            path,
            expected_identity=info,
            descriptor=descriptor,
        ):
            raise SubscriptionCredentialError("provider credential metadata is unsafe")
    except (OSError, SubscriptionCredentialError) as exc:
        if isinstance(exc, SubscriptionCredentialError):
            raise
        raise SubscriptionCredentialError("provider credential metadata is unsafe") from None
    finally:
        os.close(descriptor)
    return info


def _worker_pids(worker_uid: int) -> tuple[int, ...]:
    try:
        completed = subprocess.run(
            ["/usr/bin/pgrep", "-U", str(int(worker_uid))],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        raise SubscriptionCredentialError("worker process state is unavailable") from None
    if completed.returncode == 1:
        return ()
    if completed.returncode != 0:
        raise SubscriptionCredentialError("worker process state is unavailable")
    try:
        return tuple(sorted({int(line) for line in completed.stdout.splitlines() if line.strip()}))
    except ValueError:
        raise SubscriptionCredentialError("worker process state is malformed") from None


def _assert_worker_quiescent(
    worker_uid: int,
    *,
    ambient_classifier: AmbientProcessClassifier | None = None,
    process_lister: Callable[[int], tuple[int, ...]] = _worker_pids,
) -> None:
    observed = set(process_lister(worker_uid))
    if not observed:
        return
    classifier = ambient_classifier or DarwinDistnotedClassifier()
    ambient = classifier.classify(worker_uid=int(worker_uid))
    if ambient.status == "failed_closed":
        raise SubscriptionCredentialError("worker principal is not quiescent")
    reviewed = {identity.pid for identity in ambient.identities}
    if observed - reviewed:
        raise SubscriptionCredentialError("worker principal is not quiescent")


def _read_stdin_credential(
    realm: CodexProviderRealm | AttendedProfileCredentialFormat,
    *,
    stream=None,
) -> bytes:
    source = stream if stream is not None else sys.stdin.buffer
    if hasattr(source, "isatty") and source.isatty():
        raise SubscriptionCredentialError("provider credential requires non-terminal stdin")
    raw = source.read(MAX_CREDENTIAL_BYTES + 2)
    if not isinstance(raw, (bytes, bytearray)):
        raise SubscriptionCredentialError("provider credential input is invalid")
    value = bytes(raw)
    if value.endswith(b"\r\n"):
        value = value[:-2]
    elif value.endswith(b"\n"):
        value = value[:-1]
    if not value or len(value) > MAX_CREDENTIAL_BYTES or b"\x00" in value:
        raise SubscriptionCredentialError("provider credential input is invalid")
    if b"\n" in value or b"\r" in value:
        raise SubscriptionCredentialError("provider credential input is invalid")
    try:
        text = value.decode("utf-8", errors="strict")
        if text != text.strip():
            raise ProviderRealmError("provider credential is unavailable")
        reviewed = realm.validate_credential(text)
        if reviewed != text:
            raise ProviderRealmError("provider credential is unavailable")
    except (UnicodeDecodeError, ProviderRealmError):
        raise SubscriptionCredentialError("provider credential input is invalid") from None
    return reviewed.encode("utf-8")


def _write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        try:
            written = os.write(descriptor, value[offset:])
        except OSError:
            raise SubscriptionCredentialError("provider credential write failed") from None
        if written <= 0:
            raise SubscriptionCredentialError("provider credential write failed")
        offset += written


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def install_provider_credential(
    config: Mapping[str, Any],
    realm: CodexProviderRealm | AttendedProfileCredentialFormat,
    *,
    credential: bytes,
    replace_existing: bool,
) -> Path:
    home = _require_provider_home(config)
    path = home / PROVIDER_CREDENTIAL_FILENAME
    exists = path.exists() or path.is_symlink()
    if exists:
        _credential_metadata(
            path,
            worker_uid=int(config["worker_uid"]),
            worker_gid=int(config["worker_gid"]),
        )
        if not replace_existing:
            raise SubscriptionCredentialError(
                "provider credential exists; explicit replacement is required"
            )
    elif replace_existing:
        raise SubscriptionCredentialError("provider credential replacement target is absent")
    try:
        text = credential.decode("utf-8", errors="strict")
        if text != text.strip() or realm.validate_credential(text) != text:
            raise ProviderRealmError("provider credential is unavailable")
    except (UnicodeDecodeError, ProviderRealmError):
        raise SubscriptionCredentialError("provider credential input is invalid") from None
    temporary = home / f".{PROVIDER_CREDENTIAL_FILENAME}.new.{os.getpid()}"
    if temporary.exists() or temporary.is_symlink():
        raise SubscriptionCredentialError("provider credential staging path is occupied")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = -1
    replaced = False
    try:
        descriptor = os.open(temporary, flags, 0o600)
        os.fchown(
            descriptor,
            int(config["worker_uid"]),
            int(config["worker_gid"]),
        )
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, credential)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        if _has_macos_acl(temporary):
            raise SubscriptionCredentialError("provider credential staging metadata is unsafe")
        os.replace(temporary, path)
        replaced = True
        _fsync_directory(home)
    except (OSError, SubscriptionCredentialError) as exc:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if not replaced:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise SubscriptionCredentialError(
                "provider credential enrollment failed"
            ) from None
        raise SubscriptionCredentialEffectUnknown(
            "provider credential effect requires reconciliation"
        ) from exc
    try:
        _credential_metadata(
            path,
            worker_uid=int(config["worker_uid"]),
            worker_gid=int(config["worker_gid"]),
        )
    except SubscriptionCredentialError as exc:
        raise SubscriptionCredentialEffectUnknown(
            "provider credential effect requires reconciliation"
        ) from exc
    return path


def verify_provider_credential(config: Mapping[str, Any]) -> Path:
    """Verify only credential metadata; never open or read the secret bytes."""

    home = _require_provider_home(config)
    path = home / PROVIDER_CREDENTIAL_FILENAME
    _credential_metadata(
        path,
        worker_uid=int(config["worker_uid"]),
        worker_gid=int(config["worker_gid"]),
    )
    return path


_FINITE_ATTENDED_ADAPTER = "claude-compatible-subscription"
_FINITE_ATTENDED_HARNESS = "claude-code"
_FINITE_ATTENDED_PROTOCOL = "anthropic"


@dataclasses.dataclass(frozen=True)
class AttendedProfileCredentialFormat:
    """Credential-format authority for the reviewed attended profile target.

    The finite attended Anthropic subscription never resolves through
    ``CodexProviderRealm`` and is never reinterpreted as a Codex responses
    realm. It carries only the reviewed binding/profile identity and the
    shared provider-neutral credential format boundary: no secret bytes,
    provider response interpretation, login verdict, readiness, capacity, or
    route authority.
    """

    binding_id: str
    profile_id: str

    def validate_credential(self, value: str) -> str:
        return validate_provider_credential_format(value)


def _resolve_attended_profile_credential(
    binding: Any,
    finite_binding_id: str,
) -> AttendedProfileCredentialFormat:
    """Actual reviewed-profile checks for the finite attended Anthropic target."""
    profile_id = getattr(binding, "profile_id", None)
    autonomous = getattr(binding, "autonomous_allowed", None)
    if (
        getattr(binding, "binding_id", None) != finite_binding_id
        or getattr(binding, "adapter_id", None) != _FINITE_ATTENDED_ADAPTER
        or getattr(binding, "harness_id", None) != _FINITE_ATTENDED_HARNESS
        or getattr(binding, "protocol", None) != _FINITE_ATTENDED_PROTOCOL
        or type(autonomous) is not bool
        or autonomous
        or getattr(binding, "implementation_state", None) == "SPEC_ONLY"
        or not isinstance(profile_id, str)
        or not profile_id
        or profile_id != profile_id.strip()
    ):
        raise SubscriptionCredentialError(
            "attended subscription credential target profile is not reviewed"
        )
    return AttendedProfileCredentialFormat(
        binding_id=str(binding.binding_id),
        profile_id=profile_id,
    )


def _load_reviewed_target_config(
    path: Path,
) -> tuple[dict[str, Any], CodexProviderRealm | AttendedProfileCredentialFormat]:
    try:
        from scripts.executive_os_phase1c_worker import (
            SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
            _FINITE_ATTENDED_BINDING,
            _load_config,
            _resolve_subscription_binding,
            _resolve_subscription_realm,
        )

        config = _load_config(path, require_root_owner=True)
        if config.get("schema_version") != SUBSCRIPTION_CONFIG_SCHEMA_VERSION:
            raise SubscriptionCredentialError(
                "subscription credential target must use worker config v5"
            )
        binding = _resolve_subscription_binding(config.get("harness_binding_id"))
        # Codex bindings keep their exact reviewed CodexProviderRealm. The
        # finite attended Anthropic binding resolves to its reviewed profile
        # authority instead and is never reinterpreted as a Codex realm.
        authority: CodexProviderRealm | AttendedProfileCredentialFormat
        if binding.adapter_id == "codex-cli":
            authority = _resolve_subscription_realm(binding)
        else:
            authority = _resolve_attended_profile_credential(
                binding, _FINITE_ATTENDED_BINDING
            )
    except SubscriptionCredentialError:
        raise
    except Exception:
        raise SubscriptionCredentialError(
            "subscription credential target config is not reviewed"
        ) from None
    return config, authority


def _assert_global_autonomy_disarmed() -> None:
    try:
        from ops.executive_os.credential_rotation_interlock import (
            assert_credential_mutation_disarmed,
        )

        assert_credential_mutation_disarmed()
    except Exception:
        raise SubscriptionCredentialError(
            "credential mutation requires verified autonomy disarm"
        ) from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Enroll or verify one reviewed subscription provider credential."
    )
    parser.add_argument("--config", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--enroll", action="store_true")
    mode.add_argument("--verify-only", action="store_true")
    parser.add_argument("--replace-existing", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if os.geteuid() != 0:
            raise SubscriptionCredentialError(
                "subscription credential ceremony requires root"
            )
        if args.replace_existing and not args.enroll:
            raise SubscriptionCredentialError(
                "replacement is valid only with explicit enrollment"
            )
        config, realm = _load_reviewed_target_config(args.config)
        if args.verify_only:
            verify_provider_credential(config)
            print(
                "subscription provider credential metadata passed; "
                "provider inference canary not run; not READY"
            )
            return 0

        _assert_global_autonomy_disarmed()
        _assert_worker_quiescent(int(config["worker_uid"]))
        credential = _read_stdin_credential(realm)
        install_provider_credential(
            config,
            realm,
            credential=credential,
            replace_existing=bool(args.replace_existing),
        )
        print(
            "subscription provider credential enrolled; "
            "provider inference canary not run; not READY"
        )
        return 0
    except SubscriptionCredentialEffectUnknown:
        print(
            "subscription provider credential effect unknown; reconcile metadata before retry; "
            "no readiness or route changed",
            file=sys.stderr,
        )
        return 3
    except Exception:
        print(
            "subscription provider credential refused; no readiness or route changed",
            file=sys.stderr,
        )
        return 2


__all__ = [
    "MAX_CREDENTIAL_BYTES",
    "AttendedProfileCredentialFormat",
    "SubscriptionCredentialEffectUnknown",
    "SubscriptionCredentialError",
    "install_provider_credential",
    "main",
    "verify_provider_credential",
]


if __name__ == "__main__":
    raise SystemExit(main())
