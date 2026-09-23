"""Secret-free custom-provider realms for the hardened Codex worker.

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
    "issue_provider_realm_enrollment_receipt",
    "load_private_provider_credential",
    "provider_home_credential_loader",
    "set_provider_realm_test_enrollment",
    "set_provider_realm_test_key",
    "verify_provider_realm_enrollment_receipt",
]
