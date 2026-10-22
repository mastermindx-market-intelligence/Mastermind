"""Explicit, bounded outgoing-token maintenance for fixed Workbench routes.

The existing service calls one finite pass. This module creates no scheduler,
lease, account, browser action or retry/failover path. It publishes only the
credential artifact already consumed by WorkbenchHostTransport.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import stat

from control_plane.fs_security import has_macos_acl
from integrations.business_mcp_auth.claims import client_ref_digest
from integrations.business_mcp_auth.client_credentials import acquire_client_credentials, token_endpoint, validate_client_id
from integrations.business_mcp_auth.contracts import load_resource_policy, validate_resource_policy
from integrations.business_mcp_auth.jwks import BoundedJwksCache, HttpxJwksFetcher
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.studio_direct_mcp import private_service as file_owner
from integrations.studio_direct_mcp import workbench_host_service as custody
from .workbench_transport import CREDENTIAL_SCHEMA, MAX_HOST_ROUTES, WorkbenchHostRoute

ENROLLMENT_SCHEMA = "mastermind.browser_workbench_credentials.v1"
ATTEMPT_TIMEOUT_SECONDS = 5.0
PASS_TIMEOUT_SECONDS = 22.0
MAX_CONCURRENCY = 4


class CredentialError(RuntimeError):
    def __init__(self, code="CREDENTIAL_UNAVAILABLE"):
        super().__init__(code)


def _path(value):
    if (type(value) is not str or not value or len(value) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise CredentialError()
    path = Path(value)
    if not path.is_absolute() or str(path) != value or ".." in path.parts:
        raise CredentialError()
    return path


def _lock_path(path):
    return path.with_name(path.name + ".refresh.lock")


@dataclass(frozen=True)
class CredentialEnrollment:
    route: WorkbenchHostRoute
    client_id: str
    client_secret_file: Path
    policy: object

    def __post_init__(self):
        if type(self.route) is not WorkbenchHostRoute or not isinstance(self.client_secret_file, Path):
            raise CredentialError()
        self.route.__post_init__()
        _path(str(self.client_secret_file))
        policy = validate_resource_policy(self.policy)
        validate_client_id(self.client_id)
        token_endpoint(policy)
        if (policy.resource != self.route.resource or policy.required_scopes != ("workbench.action",)
                or policy.allowed_subject_digests != (self.route.broker_subject_digest,)
                or client_ref_digest(issuer=policy.issuer, client_id=self.client_id) != self.route.broker_client_ref):
            raise CredentialError()


def parse_enrollment(document, *, routes, enrollment_file):
    if (type(document) is not dict or set(document) != {"schema", "credentials"}
            or document["schema"] != ENROLLMENT_SCHEMA or type(document["credentials"]) is not list
            or not 1 <= len(document["credentials"]) <= MAX_HOST_ROUTES
            or type(routes) is not tuple or any(type(route) is not WorkbenchHostRoute for route in routes)):
        raise CredentialError()
    selected = {route.host_ref: route for route in routes}
    if len(selected) != len(routes):
        raise CredentialError()
    rows = []
    for raw in document["credentials"]:
        if (type(raw) is not dict or set(raw) != {"host_ref", "client_id", "client_secret_file", "policy"}
                or type(raw["host_ref"]) is not str or raw["host_ref"] not in selected):
            raise CredentialError()
        rows.append(CredentialEnrollment(selected[raw["host_ref"]], raw["client_id"],
                                         _path(raw["client_secret_file"]), load_resource_policy(raw["policy"])))
    outputs = [route.credential_file for route in routes]
    locks = [_lock_path(row.route.credential_file) for row in rows]
    secret_inputs = {row.client_secret_file for row in rows}
    fixed_input = _path(str(enrollment_file))
    if (len({row.route.host_ref for row in rows}) != len(rows) or len(set(outputs)) != len(outputs)
            or set(outputs) & set(locks) or (set(outputs) | set(locks)) & (secret_inputs | {fixed_input})
            or fixed_input in secret_inputs):
        raise CredentialError()
    return tuple(rows)


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _output(path):
    custody._guard(path)
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None, None
    raw = custody._bytes(path, maximum=65536)
    after = path.lstat()
    if _stamp(before) != _stamp(after):
        raise CredentialError()
    return raw, _stamp(after)


def _artifact(raw, route):
    if raw is None:
        return None
    value = custody._decode(raw)
    if (set(value) != {"schema", "resource", "access_token", "expires_at"}
            or value["schema"] != CREDENTIAL_SCHEMA or value["resource"] != route.resource
            or type(value["access_token"]) is not str or not value["access_token"]
            or len(value["access_token"]) > 16 * 1024
            or type(value["expires_at"]) is not int or not 0 < value["expires_at"] < 2**63):
        raise CredentialError()
    return value


def _secret(path):
    raw = custody._bytes(path, maximum=4097)
    value = raw.decode("ascii").removesuffix("\n")
    if not 1 <= len(value) <= 4096 or any(not 33 <= ord(c) <= 126 for c in value):
        raise CredentialError()
    return value


def _parent_current(path, descriptor):
    custody._guard(path)
    current = path.parent.lstat()
    held = os.fstat(descriptor)
    if (not stat.S_ISDIR(held.st_mode) or (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino)
            or held.st_uid != os.geteuid() or stat.S_IMODE(held.st_mode) != 0o700
            or os.get_inheritable(descriptor) or has_macos_acl(path.parent, expected_identity=current)):
        raise CredentialError()


def _publish(path, data, *, parent_fd, prior, ensure_current, publication):
    """Short synchronous transaction; no cancellation or lock release mid-write."""
    _parent_current(path, parent_fd)
    if _output(path) != prior:
        raise CredentialError()
    temporary = "." + path.name + "." + secrets.token_hex(16) + ".tmp"
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=parent_fd)
        os.fchmod(descriptor, 0o600)
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise CredentialError()
            remaining = remaining[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        ensure_current()
        _parent_current(path, parent_fd)
        if _output(path) != prior:
            raise CredentialError()
        os.replace(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        publication["replaced"] = True
        try:
            os.fsync(parent_fd)
        except OSError:
            # The new complete artifact may already be visible. Never restore
            # an older token or report this as a known pre-publication failure.
            raise CredentialError("CREDENTIAL_PUBLICATION_UNCERTAIN") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not publication["replaced"]:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass


class WorkbenchCredentialPublisher:
    """A finite maintenance pass over explicitly enrolled route identities."""

    def __init__(self, *, enrollments, now, monotonic, ensure_current,
                 authenticator_factory=None, acquire=acquire_client_credentials):
        if (type(enrollments) is not tuple or not 1 <= len(enrollments) <= MAX_HOST_ROUTES
                or not all(callable(value) for value in (now, monotonic, ensure_current, acquire))):
            raise CredentialError()
        if any(type(row) is not CredentialEnrollment for row in enrollments):
            raise CredentialError()
        outputs = [row.route.credential_file for row in enrollments]
        locks = {_lock_path(path) for path in outputs}
        inputs = {row.client_secret_file for row in enrollments}
        if (len(set(outputs)) != len(outputs) or set(outputs) & locks or (set(outputs) | locks) & inputs):
            raise CredentialError()
        self._rows = enrollments
        self._now, self._monotonic, self._ensure_current, self._acquire = now, monotonic, ensure_current, acquire
        self._auth = {}
        self._next = {}
        for row in enrollments:
            if type(row) is not CredentialEnrollment:
                raise CredentialError()
            row.__post_init__()
            if row.route.host_ref in self._auth:
                raise CredentialError()
            self._auth[row.route.host_ref] = (
                authenticator_factory(row) if authenticator_factory is not None else JwtAuthenticator(
                    policy=row.policy, jwks_cache=BoundedJwksCache(
                        policy=row.policy, fetcher=HttpxJwksFetcher(row.policy), monotonic=monotonic)))

    def _admit(self):
        if self._ensure_current() is not True:
            raise CredentialError("CREDENTIAL_ADMISSION_CLOSED")

    async def _verified(self, row, token):
        principal = await self._auth[row.route.host_ref].verify_token(token, now=self._now())
        if (principal.resource != row.route.resource
                or principal.subject_digest != row.route.broker_subject_digest
                or principal.client_ref != row.route.broker_client_ref
                or principal.scopes != ("workbench.action",)
                or principal.expires_at <= self._now() + row.policy.clock_skew_seconds + 15):
            raise CredentialError()
        return principal

    async def _refresh(self, row):
        publication = {"replaced": False}
        try:
            return await self._refresh_owned(row, publication)
        except (Exception, SystemExit):
            # Parent/lock descriptor cleanup happens after the token transaction.
            # A cleanup failure must retain its already-issued publication fact.
            if publication["replaced"]:
                raise CredentialError("CREDENTIAL_PUBLICATION_UNCERTAIN") from None
            raise

    async def _refresh_owned(self, row, publication):
        self._admit()
        output = row.route.credential_file
        lock = _lock_path(output)
        custody._guard(output)
        with file_owner._owned_lifecycle_mutex(lock, subject="Browser credential") as held_lock_current:
            parent_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                def still_current():
                    self._admit()
                    held_lock_current()
                    lock_info = lock.lstat()
                    if has_macos_acl(lock, expected_identity=lock_info):
                        raise CredentialError()
                    _parent_current(output, parent_fd)
                still_current()
                os.fsync(parent_fd)  # Persist a newly created lock before issuance.
                prior = _output(output)
                previous = _artifact(prior[0], row.route)
                margin = max(30, min(120, row.policy.max_token_lifetime_seconds // 5),
                             row.policy.clock_skew_seconds + 15)
                if previous is not None and previous["expires_at"] > self._now() + margin:
                    principal = await self._verified(row, previous["access_token"])
                    if principal.expires_at != previous["expires_at"]:
                        raise CredentialError()
                    still_current()
                    if _output(output) != prior:
                        raise CredentialError()
                    return "REUSED"
                still_current()
                secret = _secret(row.client_secret_file)
                try:
                    token = await self._acquire(policy=row.policy, client_id=row.client_id, client_secret=secret)
                finally:
                    secret = None
                principal = await self._verified(row, token)
                still_current()
                value = {"schema": CREDENTIAL_SCHEMA, "resource": row.route.resource,
                         "access_token": token, "expires_at": principal.expires_at}
                data = (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
                def commit_current():
                    still_current()
                    if principal.expires_at <= self._now() + row.policy.clock_skew_seconds + 15:
                        raise CredentialError()
                _publish(output, data, parent_fd=parent_fd, prior=prior, ensure_current=commit_current,
                         publication=publication)
                return "PUBLISHED"
            finally:
                os.close(parent_fd)

    async def refresh(self):
        permits = asyncio.Semaphore(MAX_CONCURRENCY)
        async def one(row):
            host = row.route.host_ref
            if self._monotonic() < self._next.get(host, 0):
                return {"host_ref": host, "status": "DEFERRED"}
            async with permits:
                try:
                    async with asyncio.timeout(ATTEMPT_TIMEOUT_SECONDS):
                        status = await self._refresh(row)
                    self._next.pop(host, None)
                except asyncio.CancelledError:
                    raise
                except SystemExit as error:
                    status = "BUSY" if isinstance(error.__cause__, BlockingIOError) else "UNAVAILABLE"
                except CredentialError as error:
                    status = {"CREDENTIAL_ADMISSION_CLOSED": "INACTIVE",
                              "CREDENTIAL_PUBLICATION_UNCERTAIN": "UNCERTAIN"}.get(str(error), "UNAVAILABLE")
                except Exception:
                    status = "UNAVAILABLE"
                if status not in {"REUSED", "PUBLISHED"}:
                    self._next[host] = self._monotonic() + max(10, row.policy.fetch_failure_backoff_seconds)
                return {"host_ref": host, "status": status}
        jobs = [asyncio.create_task(one(row)) for row in self._rows]
        try:
            async with asyncio.timeout(PASS_TIMEOUT_SECONDS):
                return tuple(await asyncio.gather(*jobs))
        except TimeoutError:
            result = []
            for row, job in zip(self._rows, jobs):
                if job.done() and not job.cancelled():
                    result.append(job.result())
                else:
                    self._next[row.route.host_ref] = self._monotonic() + max(10, row.policy.fetch_failure_backoff_seconds)
                    result.append({"host_ref": row.route.host_ref, "status": "UNAVAILABLE"})
            return tuple(result)
        finally:
            for job in jobs:
                if not job.done():
                    job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
