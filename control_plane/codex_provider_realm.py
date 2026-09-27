"""Secret-free provider realms and root-config native identity observations.

A realm selects Codex's standard OpenAI-compatible provider transport. It owns
no lifecycle, credential bytes, routing decision, or retry policy. Executive OS
remains the Job/Attempt authority and CodexWorkerAdapter remains the process
boundary.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import os
import pwd
import re
import stat
import sys
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from control_plane.fs_security import FilesystemSecurityError, has_macos_acl


_REALM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SECRET_SHAPE_RE = re.compile(r"(?i)(?:sk-[a-z0-9_-]{12,}|bearer\s+[a-z0-9._-]{12,})")
CODEX_WIRE_API_RESPONSES = "responses"
_WIRE_APIS = frozenset({CODEX_WIRE_API_RESPONSES})
PROVIDER_CREDENTIAL_FILENAME = "provider-credential"


class ProviderRealmError(ValueError):
    """A provider realm or credential observation is unsafe or malformed."""


@dataclasses.dataclass(frozen=True)
class CodexProviderRealm:
    realm_id: str
    provider_alias: str
    display_name: str
    base_url: str
    env_key: str
    wire_api: str
    requires_codex_auth_file: bool = False
    interactive_subscription_only: bool = True
    request_max_retries: int = 0
    stream_max_retries: int = 0
    def __post_init__(self) -> None:
        for field_name in ("realm_id", "provider_alias"):
            value = str(getattr(self, field_name) or "").strip().lower()
            if _REALM_ID_RE.fullmatch(value) is None:
                raise ProviderRealmError(f"{field_name} is invalid")
            object.__setattr__(self, field_name, value)
        name = str(self.display_name or "").strip()
        if not name or len(name) > 96 or _SECRET_SHAPE_RE.search(name):
            raise ProviderRealmError("display_name is invalid")
        object.__setattr__(self, "display_name", name)
        endpoint = str(self.base_url or "").strip().rstrip("/")
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ProviderRealmError("base_url must be a credential-free HTTPS endpoint")
        if parsed.query or parsed.fragment or _SECRET_SHAPE_RE.search(endpoint):
            raise ProviderRealmError("base_url contains forbidden material")
        object.__setattr__(self, "base_url", endpoint)
        env_key = str(self.env_key or "").strip()
        if _ENV_KEY_RE.fullmatch(env_key) is None:
            raise ProviderRealmError("env_key is invalid")
        object.__setattr__(self, "env_key", env_key)
        wire_api = str(self.wire_api or "").strip().lower()
        if wire_api not in _WIRE_APIS:
            raise ProviderRealmError(
                'wire_api is unsupported: Codex requires wire_api = "responses"'
            )
        object.__setattr__(self, "wire_api", wire_api)
        for field_name in ("request_max_retries", "stream_max_retries"):
            value = getattr(self, field_name)
            if type(value) is not int or value != 0:
                raise ProviderRealmError(f"{field_name} must remain zero")
        if self.interactive_subscription_only is not True:
            raise ProviderRealmError("subscription realms must remain interactive-only")

    @property
    def codex_provider_id(self) -> str:
        return "mastermind_" + self.realm_id.replace("-", "_").replace(".", "_")

    def config_overrides(self) -> tuple[str, ...]:
        provider_id = self.codex_provider_id
        prefix = f"model_providers.{provider_id}"
        return (
            f"model_provider={json.dumps(provider_id)}",
            f"{prefix}.name={json.dumps(self.display_name)}",
            f"{prefix}.base_url={json.dumps(self.base_url)}",
            f"{prefix}.env_key={json.dumps(self.env_key)}",
            f"{prefix}.wire_api={json.dumps(self.wire_api)}",
            f"{prefix}.request_max_retries=0",
            f"{prefix}.stream_max_retries=0",
        )

    def validate_credential(self, value: str) -> str:
        if not isinstance(value, str):
            raise ProviderRealmError("provider credential is unavailable")
        credential = value.strip()
        if not credential or len(credential) > 4096 or any(ch in credential for ch in "\r\n\x00"):
            raise ProviderRealmError("provider credential is unavailable")
        return credential

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
    except FilesystemSecurityError:
        raise ProviderRealmError("provider credential is unavailable")


def _require_provider_home(
    home: Path,
    *,
    expected_uid: int,
    expected_gid: int,
) -> None:
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
        raise ProviderRealmError("provider credential is unavailable") from None
    descriptor = os.open(home, flags)
    try:
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != int(expected_uid)
            or info.st_gid != int(expected_gid)
            or stat.S_IMODE(info.st_mode) != 0o700
            or _has_macos_acl(
                home,
                expected_identity=info,
                descriptor=descriptor,
            )
        ):
            raise ProviderRealmError("provider credential is unavailable")
    except OSError:
        raise ProviderRealmError("provider credential is unavailable") from None
    except ProviderRealmError:
        raise
    finally:
        os.close(descriptor)


def _open_regular_credential(
    path: Path,
    before: os.stat_result,
    *,
    expected_uid: int,
    expected_gid: int,
) -> tuple[int, os.stat_result]:
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
            or not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != int(expected_uid)
            or observed.st_gid != int(expected_gid)
            or stat.S_IMODE(observed.st_mode) != 0o600
            or observed.st_nlink != 1
            or observed.st_size < 1
            or observed.st_size > 4096
        ):
            raise ProviderRealmError("provider credential is unavailable")
        return descriptor, observed
    except BaseException:
        os.close(descriptor)
        raise


def load_private_provider_credential(
    provider_home: Path | str,
    *,
    expected_uid: int,
    expected_gid: int,
) -> str:
    """Read one worker-private opaque provider key from the existing provider home."""

    home = Path(provider_home)
    path = home / PROVIDER_CREDENTIAL_FILENAME
    try:
        _require_provider_home(home, expected_uid=expected_uid, expected_gid=expected_gid)
        before = path.lstat()
        descriptor, observed = _open_regular_credential(
            path,
            before,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
    except (OSError, ProviderRealmError):
        raise ProviderRealmError("provider credential is unavailable") from None
    try:
        if _has_macos_acl(
            path,
            expected_identity=before,
            descriptor=descriptor,
        ):
            raise ProviderRealmError("provider credential is unavailable")
        try:
            raw = os.read(descriptor, 4097)
        except OSError:
            raise ProviderRealmError("provider credential is unavailable") from None
        if len(raw) != observed.st_size:
            raise ProviderRealmError("provider credential is unavailable")
    finally:
        os.close(descriptor)
    try:
        credential = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ProviderRealmError("provider credential is unavailable") from None
    if (
        not credential
        or credential != credential.strip()
        or any(ch in credential for ch in "\r\n\x00")
    ):
        raise ProviderRealmError("provider credential is unavailable")
    return credential


def provider_home_credential_loader(
    provider_home: Path | str,
    realm: CodexProviderRealm,
    *,
    expected_uid: int,
    expected_gid: int,
) -> ProviderCredentialLoader:
    """Bind a reviewed realm to the canonical worker-private provider-home secret."""

    home = Path(provider_home)

    def load() -> str:
        value = load_private_provider_credential(
            home, expected_uid=expected_uid, expected_gid=expected_gid
        )
        return realm.validate_credential(value)

    return load


MINIMAX_TOKEN_PLAN = CodexProviderRealm(
    realm_id="minimax-token-plan",
    provider_alias="minimax",
    display_name="MiniMax Token Plan",
    base_url="https://api.minimax.io/v1",
    env_key="MINIMAX_TOKEN_PLAN_KEY",
    wire_api="responses",
)

OPENCODE_GO_TOKEN_PLAN = CodexProviderRealm(
    realm_id="opencode-go",
    provider_alias="opencode-go",
    display_name="OpenCode Go (Zen)",
    base_url="https://opencode.ai/zen/go/v1",
    env_key="OPENCODE_GO_KEY",
    wire_api="responses",
)

ALIBABA_TOKEN_PLAN = CodexProviderRealm(
    realm_id="alibaba-token-plan-sg",
    provider_alias="alibaba",
    display_name="Alibaba Model Studio Token Plan",
    base_url="https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
    env_key="ALIBABA_TOKEN_PLAN_KEY",
    wire_api="responses",
)

REVIEWED_CODEX_PROVIDER_REALMS = {
    realm.realm_id: realm for realm in (MINIMAX_TOKEN_PLAN, ALIBABA_TOKEN_PLAN,)
}

CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY = {
    realm.realm_id: realm for realm in (OPENCODE_GO_TOKEN_PLAN,)
}

# MiniMax Token Plan was promoted out of quarantine by the exact-head native
# transport proof recorded in the secret-free, reviewable repository artifact:
# review_evidence/provider_realms/minimax_codex_responses_20260915.json
# (source receipt SHA-256
# 84771422af5ef24e12f6ec0e82a2b107763fceaca77f1c7c7915493802bee3dd).
# It records codex-cli 0.154.0, rc 0, MiniMax-M3 and wire_api "responses"
# without credential fingerprints, credential type tags or host-local paths.
# The observed helper used the existing `minimax` pool; the candidate
# `minimax-codex` binding was not executed. The artifact therefore proves only
# transport reachability -- not a governed-path canary, capacity observation,
# usage-policy decision or autonomous-routing grant -- so
# this realm is reviewed for transport and no worker binding is armed by the
# promotion. The binding it enables (minimax-token-plan.codex-responses) stays
# BUILT_NOT_PROVEN with autonomous_allowed false, and a live lane still requires
# every per-binding enrollment, capacity, canary and usage-policy gate.
#
# The OpenCode Go realm remains SPEC-ONLY and quarantined: kit-side Responses
# transport was proven only for some upstream models (see kit GO_PROOF_LEDGER)
# and promotion requires the reviewed exact-head native execution proof; no
# worker binding is authorized from it.

ProviderCredentialLoader = Callable[[], str]


def _make_provider_realm_owner_seam() -> Any:
    """Build a closure-held realm-owner HMAC and enrollment seam.

    The keyed seal protects realm receipts from cross-boundary substitution
    and accidental mutation. It is not a boundary against an attacker already
    executing arbitrary Python in this process; a real owner boundary would
    require a separate process or OS capability.
    """

    key_bytes: bytes | None = None
    enrollment_state: str | None = None

    class _OwnerSeam:
        __slots__ = ()

        @staticmethod
        def enrollment() -> str | None:
            return enrollment_state

        @staticmethod
        def seal(payload: Mapping[str, Any]) -> bytes:
            canonical = json.dumps(
                dict(payload),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("utf-8")
            if key_bytes is None:
                raise ProviderRealmError("provider-realm owner key is not available")
            return hmac.new(key_bytes, canonical, hashlib.sha256).digest()

        @staticmethod
        def verify(payload: Mapping[str, Any], digest: bytes) -> bool:
            try:
                return isinstance(digest, bytes) and hmac.compare_digest(
                    _OwnerSeam.seal(payload), digest
                )
            except (TypeError, ValueError):
                return False

        @staticmethod
        @contextmanager
        def install_test_key(key: bytes | None):
            """Install fixture HMAC state only while pytest owns this test."""

            nonlocal key_bytes
            if "pytest" not in sys.modules or os.environ.get(
                "PYTEST_CURRENT_TEST"
            ) is None:
                raise ProviderRealmError("provider-realm owner test key is test-only")
            if key is not None and (
                not isinstance(key, (bytes, bytearray)) or len(key) < 16
            ):
                raise ProviderRealmError("provider-realm owner test key is invalid")
            previous = key_bytes
            key_bytes = bytes(key) if key is not None else None
            try:
                yield
            finally:
                key_bytes = previous

        @staticmethod
        @contextmanager
        def install_test_enrollment(value: str | None):
            """Install fixture enrollment only while pytest owns this test."""

            nonlocal enrollment_state
            if "pytest" not in sys.modules or os.environ.get(
                "PYTEST_CURRENT_TEST"
            ) is None:
                raise ProviderRealmError("provider-realm test enrollment is test-only")
            if value is not None and value not in _VALID_ENROLLMENT_STATES:
                raise ProviderRealmError("enrollment_state is invalid")
            previous = enrollment_state
            enrollment_state = value
            try:
                yield
            finally:
                enrollment_state = previous

    return _OwnerSeam()


_VALID_ENROLLMENT_STATES = frozenset({"enrolled", "unenrolled"})
_PROVIDER_REALM_OWNER_SEAM = _make_provider_realm_owner_seam()


def set_provider_realm_test_key(key: bytes | None) -> None:
    """Refuse direct injection; use the fixture-only closure seam instead."""

    del key
    raise ProviderRealmError("provider-realm owner test key is test-only")


def set_provider_realm_test_enrollment(enrollment_state: str | None) -> None:
    """Refuse direct injection; use the fixture-only closure seam instead."""

    del enrollment_state
    raise ProviderRealmError("provider-realm test enrollment is test-only")


def _realm_receipt_payload(
    *,
    receipt_id: str,
    binding_id: str,
    profile_id: str,
    adapter_id: str,
    generation: int,
    enrollment_state: str,
    catalog_digest: str,
) -> dict[str, Any]:
    return {
        "adapter_id": adapter_id,
        "binding_id": binding_id,
        "catalog_digest": catalog_digest,
        "enrollment_state": enrollment_state,
        "generation": generation,
        "profile_id": profile_id,
        "receipt_id": receipt_id,
    }


def _realm_receipt_seal(payload: Mapping[str, Any]) -> str:
    return _PROVIDER_REALM_OWNER_SEAM.seal(payload).hex()


def issue_provider_realm_enrollment_receipt(
    *,
    binding_id: str,
    bindings_document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
    generation: int,
) -> Any:
    """Mint one keyed-sealed realm receipt. Enrollment is owner-observed."""

    from control_plane.subscription_catalog import compose_catalog_digest, get_binding
    from ops.executive_os.provider_realm_facts import (
        ProviderRealmEnrollmentReceipt,
        ProviderRealmFactError,
    )

    if type(generation) is not int or generation < 1:
        raise ProviderRealmFactError("realm generation is invalid")
    enrollment_state = _PROVIDER_REALM_OWNER_SEAM.enrollment()
    if enrollment_state not in _VALID_ENROLLMENT_STATES:
        raise ProviderRealmFactError(
            "enrollment_state is not observed by the provider-realm owner"
        )
    binding = get_binding(
        binding_id,
        document=bindings_document,
        profiles_document=profiles_document,
    )
    catalog_digest = compose_catalog_digest(
        bindings_document=bindings_document,
        profiles_document=profiles_document,
    )
    receipt_id = f"provider-realm:{binding.binding_id}:{generation}"
    payload = _realm_receipt_payload(
        receipt_id=receipt_id,
        binding_id=binding.binding_id,
        profile_id=binding.profile_id,
        adapter_id=binding.adapter_id,
        generation=generation,
        enrollment_state=enrollment_state,
        catalog_digest=catalog_digest,
    )
    digest = _PROVIDER_REALM_OWNER_SEAM.seal(payload).hex()
    return ProviderRealmEnrollmentReceipt(
        receipt_id=receipt_id,
        receipt_digest=digest,
        binding_id=binding.binding_id,
        profile_id=binding.profile_id,
        adapter_id=binding.adapter_id,
        generation=generation,
        enrollment_state=enrollment_state,
        catalog_digest=catalog_digest,
        _seal=digest,
    )


def verify_provider_realm_enrollment_receipt(receipt: Any) -> None:
    """Re-verify the owner HMAC and the owner-composed receipt_id."""

    from ops.executive_os.provider_realm_facts import (
        ProviderRealmEnrollmentReceipt,
        ProviderRealmFactError,
    )

    if type(receipt) is not ProviderRealmEnrollmentReceipt:
        raise ProviderRealmFactError("realm_receipt is not an owner-minted instance")
    expected_id = f"provider-realm:{receipt.binding_id}:{receipt.generation}"
    if receipt.receipt_id != expected_id:
        raise ProviderRealmFactError("receipt_id is not owner-issued")
    payload = _realm_receipt_payload(
        receipt_id=receipt.receipt_id,
        binding_id=receipt.binding_id,
        profile_id=receipt.profile_id,
        adapter_id=receipt.adapter_id,
        generation=receipt.generation,
        enrollment_state=receipt.enrollment_state,
        catalog_digest=receipt.catalog_digest,
    )
    digest = receipt.receipt_digest
    try:
        digest_ok = isinstance(digest, str) and _PROVIDER_REALM_OWNER_SEAM.verify(
            payload, bytes.fromhex(digest)
        )
        seal = object.__getattribute__(receipt, "_seal")
        seal_ok = isinstance(seal, str) and _PROVIDER_REALM_OWNER_SEAM.verify(
            payload, bytes.fromhex(seal)
        )
    except (TypeError, ValueError):
        digest_ok = False
        seal_ok = False
    if not digest_ok or not seal_ok:
        raise ProviderRealmFactError(
            "realm_receipt seal does not match receipt_id, receipt_digest, "
            "enrollment_state, generation"
        )


__all__ = [
    "ALIBABA_TOKEN_PLAN",
    "MINIMAX_TOKEN_PLAN",
    "OPENCODE_GO_TOKEN_PLAN",
    "CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY",
    "CODEX_WIRE_API_RESPONSES",
    "REVIEWED_CODEX_PROVIDER_REALMS",
    "CodexProviderRealm",
    "PROVIDER_CREDENTIAL_FILENAME",
    "ProviderCredentialLoader",
    "ProviderRealmError",
    "NATIVE_REALM_ENROLLMENT_SCHEMA",
    "NativeRealmIdentityOwner",
    "issue_provider_realm_enrollment_receipt",
    "load_private_provider_credential",
    "load_native_realm_owner",
    "provider_home_credential_loader",
    "set_provider_realm_test_enrollment",
    "set_provider_realm_test_key",
    "verify_provider_realm_enrollment_receipt",
]


# Native enrollment is a stanza in the existing root-owned Worker Broker
# configuration. No separate identity registry, credential store or HMAC key
# file is introduced. Legacy custom-provider receipt minting above is unchanged.
NATIVE_REALM_ENROLLMENT_SCHEMA = "mastermind.native_provider_realm_enrollment/v1"
_NATIVE_ENROLLMENT_FIELDS = frozenset({
    "schema_version", "slot_id", "host_ref", "os_principal_ref",
    "config_custody_ref", "generation", "enrollment_state",
    "provider_binary_sha256",
})
_NATIVE_SHA = re.compile(r"^[0-9a-f]{64}$")
_NATIVE_PRINCIPAL = re.compile(r"^principal-[0-9a-f]{64}$")
_NATIVE_CUSTODY = re.compile(r"^custody-[0-9a-f]{64}$")
_NATIVE_OWNER_SEAL = object()


def _native_refuse() -> None:
    # Fixed diagnostics: no paths, account identifiers, credentials or raw
    # filesystem/provider errors cross the caller boundary.
    raise ProviderRealmError("NATIVE_REALM_IDENTITY_UNAVAILABLE")


def _native_path(value: object) -> Path:
    if not isinstance(value, (str, Path)):
        _native_refuse()
    raw = str(value)
    path = Path(raw)
    if not path.is_absolute() or str(path) != raw or ".." in path.parts:
        _native_refuse()
    return path


def _native_canonical_home(path: Path) -> Path:
    # /var is the OS-owned macOS alias. Do not resolve arbitrary caller paths.
    if sys.platform == "darwin" and path.parts[:2] == ("/", "var"):
        return Path("/private") / path.relative_to("/")
    return path


def _native_stat_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _native_open(path: Path, *, directory: bool = False,
                 private_uid: int | None = None):
    """Walk every component with held no-follow descriptors and ACL checks."""
    path = _native_path(path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    odirectory = getattr(os, "O_DIRECTORY", 0)
    if not nofollow or not odirectory:
        _native_refuse()
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    # Darwin sys/fcntl.h defines O_SEARCH as O_EXEC (0x40000000) |
    # O_DIRECTORY; CPython does not expose it on every supported release.
    # O_RDONLY and O_EVTONLY incorrectly require listing permission on the
    # installed root-owned 0711 traversal directories. Search-only descriptors
    # retain no-follow, fstat and descriptor-bound ACL observations.
    search = (getattr(os, "O_SEARCH", 0x40000000 | odirectory)
              if sys.platform == "darwin" else getattr(os, "O_PATH", os.O_RDONLY))
    directory_flags = search | nofollow | odirectory | getattr(os, "O_CLOEXEC", 0)
    descriptors: list[int] = []
    try:
        parent = os.open("/", directory_flags)
        descriptors.append(parent)
        current = Path("/")
        for index, part in enumerate(path.parts[1:]):
            final = index == len(path.parts) - 2
            is_directory = not final or directory
            descriptor = os.open(part, directory_flags if is_directory else
                                 flags | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
            descriptors.append(descriptor)
            current /= part
            info = os.fstat(descriptor)
            expected_type = stat.S_ISDIR if is_directory else stat.S_ISREG
            if (not expected_type(info.st_mode)
                    or info.st_uid not in ({0, private_uid} if is_directory else {0})
                    or stat.S_IMODE(info.st_mode) & 0o022
                    or (not is_directory and info.st_nlink != 1)
                    or has_macos_acl(current, expected_identity=info, descriptor=descriptor)):
                _native_refuse()
            parent = descriptor
        if len(descriptors) < 2:
            _native_refuse()
        before = os.fstat(parent)
        yield parent, before
        # Detect replacement of the named leaf while its old inode stayed open.
        after = os.fstat(parent)
        if (_native_stat_identity(before) != _native_stat_identity(after)
                or _native_stat_identity(os.stat(path, follow_symlinks=False)) != _native_stat_identity(after)):
            _native_refuse()
    except (OSError, FilesystemSecurityError):
        raise ProviderRealmError("NATIVE_REALM_IDENTITY_UNAVAILABLE") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _native_read_config(path: Path, expected_digest: str) -> dict[str, Any]:
    if type(expected_digest) is not str or not _NATIVE_SHA.fullmatch(expected_digest):
        _native_refuse()
    with _native_open(path) as (descriptor, before):
        if not 0 < before.st_size <= 65536:
            _native_refuse()
        raw = bytearray()
        while len(raw) <= 65536:
            chunk = os.read(descriptor, min(8192, 65537 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        if (len(raw) != before.st_size
                or _native_stat_identity(before) != _native_stat_identity(os.fstat(descriptor))
                or hashlib.sha256(raw).hexdigest() != expected_digest):
            _native_refuse()
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                _native_refuse()
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: _native_refuse())
    except (UnicodeDecodeError, ValueError):
        raise ProviderRealmError("NATIVE_REALM_IDENTITY_UNAVAILABLE") from None
    if type(value) is not dict:
        _native_refuse()
    return value


def _native_enrollment(config: Mapping[str, Any]):
    from control_plane.executive_host_pressure import HOST_REF_RE
    from ops.executive_os.provider_worker_slots import get_slot, SlotCatalogError
    enrollment = config.get("native_realm_enrollment")
    if type(enrollment) is not dict or set(enrollment) != _NATIVE_ENROLLMENT_FIELDS:
        _native_refuse()
    if (enrollment["schema_version"] != NATIVE_REALM_ENROLLMENT_SCHEMA
            or enrollment["enrollment_state"] != "enrolled"
            or type(enrollment["generation"]) is not int
            or not 1 <= enrollment["generation"] < 2**63):
        _native_refuse()
    for key, pattern in (("host_ref", HOST_REF_RE),
                         ("os_principal_ref", _NATIVE_PRINCIPAL),
                         ("config_custody_ref", _NATIVE_CUSTODY),
                         ("provider_binary_sha256", _NATIVE_SHA)):
        if type(enrollment[key]) is not str or not pattern.fullmatch(enrollment[key]):
            _native_refuse()
    try:
        slot = get_slot(enrollment["slot_id"])
    except (SlotCatalogError, TypeError):
        raise ProviderRealmError("NATIVE_REALM_IDENTITY_UNAVAILABLE") from None
    if (type(config.get("worker_uid")) is not int
            or type(config.get("worker_gid")) is not int
            or config["worker_uid"] != slot.worker_uid
            or config["worker_gid"] != slot.worker_gid
            or config.get("worker_user") != slot.worker_user
            or _native_canonical_home(_native_path(config.get("provider_home")))
               != _native_canonical_home(slot.provider_home)):
        _native_refuse()
    return enrollment, slot


@dataclasses.dataclass(frozen=True, repr=False)
class NativeRealmIdentityOwner:
    """Revalidating composition capability, never a serialized auth assertion.

    The caller pins the already admitted broker configuration's SHA-256. The
    root configuration owner assigns opaque references and generation once;
    hostname, UID, home path and provider login cannot invent enrollment.
    This checks identity, not provider login, quota or WORKER_BROKER context.
    """
    _config_path: Path
    _config_sha256: str
    _seal: object = dataclasses.field(repr=False, compare=False)

    def observe(self):
        from ops.executive_os.provider_realm_facts import NativeRealmIdentityObservation
        if self._seal is not _NATIVE_OWNER_SEAL:
            _native_refuse()
        config = _native_read_config(self._config_path, self._config_sha256)
        enrollment, slot = _native_enrollment(config)
        home = _native_canonical_home(slot.provider_home)
        try:
            principal = pwd.getpwuid(os.geteuid())
        except KeyError:
            _native_refuse()
        if (os.geteuid() != slot.worker_uid or os.getuid() != slot.worker_uid
                or os.getegid() != slot.worker_gid or os.getgid() != slot.worker_gid
                or principal.pw_name != slot.worker_user
                or principal.pw_gid != slot.worker_gid
                or _native_canonical_home(_native_path(principal.pw_dir)) != home):
            _native_refuse()
        allowed_groups = config.get("allowed_supplementary_gids")
        if (type(allowed_groups) is not list
                or any(type(gid) is not int or gid <= 0 for gid in allowed_groups)
                or not set(os.getgroups()).issubset(set(allowed_groups) | {slot.worker_gid})):
            _native_refuse()
        config_dir = home / ".claude" if slot.provider_family == "anthropic" else home
        if _native_canonical_home(_native_path(os.environ.get("HOME"))) != home:
            _native_refuse()
        environment_key = "CLAUDE_CONFIG_DIR" if slot.provider_family == "anthropic" else "CODEX_HOME"
        if _native_canonical_home(_native_path(os.environ.get(environment_key))) != config_dir:
            _native_refuse()
        for path in (home, config_dir):
            with _native_open(path, directory=True, private_uid=slot.worker_uid) as (_, info):
                if (info.st_uid != slot.worker_uid or info.st_gid != slot.worker_gid
                        or stat.S_IMODE(info.st_mode) != 0o700):
                    _native_refuse()
        # The factory owns provider selection and signature/version attestation;
        # the identity join independently pins the exact current executable bytes.
        binary_key = "claude_binary" if slot.provider_family == "anthropic" else "codex_binary"
        binary = _native_path(config.get(binary_key))
        with _native_open(binary) as (descriptor, before):
            if not 0 < before.st_size <= 512 * 1024 * 1024 or not before.st_mode & 0o111:
                _native_refuse()
            digest = hashlib.sha256()
            remaining = before.st_size
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    _native_refuse()
                digest.update(chunk)
                remaining -= len(chunk)
            if (digest.hexdigest() != enrollment["provider_binary_sha256"]
                    or _native_stat_identity(before) != _native_stat_identity(os.fstat(descriptor))):
                _native_refuse()
        # Revocation/config drift during observation invalidates this observation.
        _native_read_config(self._config_path, self._config_sha256)
        return NativeRealmIdentityObservation(
            slot_id=slot.slot_id, host_ref=enrollment["host_ref"],
            os_principal_ref=enrollment["os_principal_ref"],
            config_custody_ref=enrollment["config_custody_ref"],
            generation=enrollment["generation"],
            source_config_sha256=self._config_sha256,
            provider_binary_sha256=enrollment["provider_binary_sha256"],
        )

    def require_current_identity(self, host_ref: str, os_principal_ref: str) -> None:
        observation = self.observe()
        if (host_ref != observation.host_ref
                or os_principal_ref != observation.os_principal_ref):
            _native_refuse()
        return None


def load_native_realm_owner(config_path: Path, *, expected_config_sha256: str) -> NativeRealmIdentityOwner:
    """Load from the existing root config, never request JSON or an environment tag."""
    path = _native_path(config_path)
    config = _native_read_config(path, expected_config_sha256)
    _native_enrollment(config)
    return NativeRealmIdentityOwner(path, expected_config_sha256, _NATIVE_OWNER_SEAL)
