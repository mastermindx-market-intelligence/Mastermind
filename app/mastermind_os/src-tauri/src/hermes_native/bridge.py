"""One-shot local native Hermes client embedded in the authenticated native OS host.
No daemon, provider, store, retry, process activation or remote proxy. Native
session tickets and unprojected RPC replies never cross into the renderer.
"""
from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager, contextmanager
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import urlsplit

SCHEMA = "mastermind.hermes_native_view.v1"
REQUIRED_CAPABILITIES = frozenset({"session-authority-v1", "durable-admission-v1", "event-replay-v1"})
PUBLIC_CAPABILITIES = ["native_chat", "native_history", "admission_recovery"]
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z")
REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z")
METHODS = {"create": "session.create", "send": "prompt.submit", "receipt": "prompt.receipt"}
FIELDS = {"status": {"operation"}, "list": {"operation"},
          "create": {"operation", "role", "requestId"}, "read": {"operation", "sessionId"},
          "send": {"operation", "sessionId", "requestId", "text"},
          "receipt": {"operation", "sessionId", "admissionId"},
          "recover_create": {"operation", "requestId"},
          "recover_send": {"operation", "sessionId", "requestId"}}


class BridgeRefusal(ValueError):
    pass


class OwnerRefusal(ValueError):
    def __init__(self, reason, *, code=None):
        super().__init__(reason)
        self.code = code

    def proves_rejection(self):
        # Qualified native dispatcher/authority refusals before a modifying
        # handler can commit. Storage/internal/unknown and admission-conflict
        # errors are NOT absence evidence, even when the owner sent an error.
        return ((self.code == 4001 and str(self) in {
            "invalid_params", "permission_denied", "profile_mismatch", "runtime_draining"})
            or self.code == -32601 and str(self) == "unknown_method")


class NotSent(ValueError):
    pass


def identifier(value):
    if type(value) is not str or not IDENTIFIER.fullmatch(value):
        raise BridgeRefusal("REQUEST_INVALID")
    return value


def bounded_text(value, maximum=32768, *, blank=False):
    if (type(value) is not str or (not blank and not value.strip())
            or any(ord(c) < 32 and c not in "\n\r\t" for c in value) or "\x7f" in value):
        raise BridgeRefusal("REQUEST_INVALID")
    try:
        if len(value.encode("utf-8", "strict")) > maximum:
            raise BridgeRefusal("RESPONSE_TOO_LARGE")
    except UnicodeError:
        raise BridgeRefusal("REQUEST_INVALID") from None
    return value


def normalize_request(value):
    if type(value) is not dict or type(value.get("operation")) is not str:
        raise BridgeRefusal("REQUEST_INVALID")
    operation = value["operation"]
    if operation not in FIELDS or set(value) != FIELDS[operation]:
        raise BridgeRefusal("REQUEST_INVALID")
    if "requestId" in value and (type(value["requestId"]) is not str
                                or not REQUEST_ID.fullmatch(value["requestId"])):
        raise BridgeRefusal("REQUEST_INVALID")
    session = {"session_id": identifier(value["sessionId"])} if "sessionId" in value else {}
    if operation in {"recover_create", "recover_send"}:
        return operation, {**session, "request_id": value["requestId"]}
    if operation == "create":
        names = {"meta-ceo": "Meta-CEO", "secretary": "Secretary"}
        if type(value["role"]) is not str or value["role"] not in names:
            raise BridgeRefusal("REQUEST_INVALID")
        return operation, {"request_id": value["requestId"], "source": "tool",
            "title": "Mastermind OS · " + names[value["role"]] + " · " + value["requestId"],
            "toolsets": [], "safe_mode": False, "accept_hooks": False, "follow_profile_config": False}
    if operation == "send":
        return operation, {**session, "text": bounded_text(value["text"]),
            "submission_id": value["requestId"], "input_id": value["requestId"],
            "queued": False, "finite": True}
    if operation == "receipt":
        return operation, {**session, "admission_id": identifier(value["admissionId"])}
    if operation == "list":
        return operation, {}
    return operation, session


def qualify_identity(answer, home):
    if (type(answer) is not dict or answer.get("ok") is not True
            or type(answer.get("protocol")) is not int or answer["protocol"] != 1):
        raise BridgeRefusal("NATIVE_PROTOCOL_UNAVAILABLE")
    data = answer.get("result")
    if (type(data) is not dict or data.get("kind") != "hermes-gateway"
            or type(data.get("runtime_protocol")) is not int or data["runtime_protocol"] != 1
            or data.get("state") != "ready" or data.get("hermes_home") != str(home)
            or type(data.get("authority_epoch")) is not int or data["authority_epoch"] < 1
            or type(data.get("capabilities")) is not list
            or any(type(x) is not str for x in data["capabilities"])
            or not REQUIRED_CAPABILITIES <= set(data["capabilities"])):
        raise BridgeRefusal("NATIVE_PROTOCOL_UNAVAILABLE")
    instance = identifier(data.get("instance_id"))
    try:
        origin = urlsplit(data["api_origin"])
        if (origin.scheme != "http" or origin.hostname != "127.0.0.1" or not origin.port
                or origin.username is not None or origin.password is not None
                or origin.path or origin.query or origin.fragment
                or data["api_origin"] != f"http://127.0.0.1:{origin.port}"):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise BridgeRefusal("NATIVE_ORIGIN_INVALID") from None
    endpoint = SimpleNamespace(profile_id=str(home), instance_id=instance,
        authority_epoch=data["authority_epoch"], runtime_protocol=1,
        api_origin=data["api_origin"], capabilities=list(data["capabilities"]), control_home=None)
    revision, version = data.get("code_sha"), data.get("code_version")
    if type(revision) is not str or not re.fullmatch(r"[0-9a-f]{40}", revision):
        revision = None
    if type(version) is not str or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,64}", version):
        version = None
    # Stable namespace for this same-OS-user native attachment. This is a local
    # pending-pointer key, not a cloud principal, credential or permission grant.
    scope = hashlib.sha256(("mastermind.hermes-native.local.v1\0" + str(home) + "\0" + str(os.getuid())).encode()).hexdigest()
    return endpoint, {"protocol": 1, "instanceId": instance, "authorityEpoch": data["authority_epoch"],
                      "version": version, "sourceRevision": revision, "localScope": scope}


def integer(value):
    if type(value) is not int or value < 0:
        raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
    return value


def display(value, limit=240):
    return bounded_text(value, limit, blank=True)


def message_text(value):
    if type(value) is str:
        return bounded_text(value, 65536, blank=True)
    if type(value) is list:
        texts = [part.get("text", "") for part in value
                 if type(part) is dict and part.get("type") == "text"]
        if any(type(text) is not str for text in texts):
            raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
        return bounded_text("\n".join(texts), 65536, blank=True)
    raise BridgeRefusal("NATIVE_RESPONSE_INVALID")


def admission_status(value):
    if type(value) is not str or value not in {"queued", "started", "unknown", "terminal"}:
        raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
    return value


def session_tool_access(info, readonly_capacity=False, readonly_omh=False):
    if type(info) is not dict:
        return "UNQUALIFIED"
    policy = info.get("launch_request")
    frozen = (type(policy) is dict and info.get("source") == "tool"
              and policy.get("toolsets") == [] and policy.get("safe_mode") is False
              and policy.get("accept_hooks") is False and policy.get("follow_profile_config") is False)
    if not frozen:
        return "UNQUALIFIED"
    if info.get("enabled_toolsets") == [] and type(info.get("tool_count")) is int and info["tool_count"] == 0:
        return "NONE"
    tools = info.get("tools")
    if (readonly_capacity and type(info.get("tool_count")) is int and info["tool_count"] == 3
            and tools == {"other": ["tool_search", "tool_describe", "tool_call"]}):
        if info.get("enabled_toolsets") == ["mastermind-fabric-capacity"]:
            return "CAPACITY_READ_ONLY"
        if readonly_omh and info.get("enabled_toolsets") == ["mastermind-fabric-capacity", "mmx_omh"]:
            return "ADVISORY_READ_ONLY"
    return "UNQUALIFIED"


def project_result(operation, value, session_id=None, *, readonly_capacity=False, readonly_omh=False):
    if type(value) is not dict:
        raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
    if operation in {"create", "read"}:
        sid, stored = identifier(value.get("session_id")), identifier(value.get("stored_session_id"))
        if session_id is not None and session_id not in {sid, stored}:
            raise BridgeRefusal("NATIVE_SESSION_MISMATCH")
        info, rows = value.get("info"), value.get("messages")
        if type(info) is not dict or type(rows) is not list or type(value.get("running")) is not bool:
            raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
        messages = []
        for row in rows:
            if type(row) is not dict:
                raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
            if row.get("role") in {"user", "assistant"}:
                messages.append({"role": row["role"], "text": message_text(row.get("content", ""))})
        pending = value.get("pending", [])
        if type(pending) is not list or len(pending) > 1000 or type(value.get("prompts", [])) is not list:
            raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
        projected = [{"id": identifier(item.get("admission_id")), "status": admission_status(item.get("status"))}
                     for item in pending if type(item) is dict]
        if len(projected) != len(pending):
            raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
        return {"session": {"id": sid, "storedId": stored,
            "title": display(info.get("title") or "", 512),
            "requestedModel": display(info.get("model") or "", 160),
            "canSend": session_tool_access(info, readonly_capacity, readonly_omh) != "UNQUALIFIED",
            "toolAccess": session_tool_access(info, readonly_capacity, readonly_omh), "running": value["running"], "executionGeneration": integer(value.get("execution_generation")),
            "messageCount": integer(value.get("message_count")), "messages": messages[-100:],
            "historyTruncated": len(messages) > 100, "pending": projected,
            "promptsPending": bool(value.get("prompts") or value.get("open_requests"))}}
    if operation == "list":
        rows = value.get("sessions")
        if type(rows) is not list or len(rows) > 50:
            raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
        sessions = []
        for row in rows:
            if type(row) is not dict or type(row.get("running")) is not bool:
                raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
            sessions.append({"id": identifier(row.get("session_id")), "title": display(row.get("title") or "", 512),
                "running": row["running"], "messageCount": integer(row.get("message_count"))})
        return {"sessions": sessions}
    if operation in {"send", "receipt"}:
        ref = value.get("ref")
        if type(ref) is not dict or ref.get("session_id") != session_id:
            raise BridgeRefusal("NATIVE_SESSION_MISMATCH")
        outcome = value.get("outcome")
        return {"receipt": {"id": identifier(value.get("admission_id")), "sessionId": identifier(session_id),
            "status": admission_status(value.get("status")), "sequence": integer(value.get("sequence")),
            "outcome": display(outcome, 240) if outcome is not None else None,
            "executionGeneration": integer(value["execution_generation"]) if value.get("execution_generation") is not None else None}}
    raise BridgeRefusal("REQUEST_INVALID")


def envelope(state, **values):
    return {"schema": SCHEMA, "state": state, "capabilities": list(PUBLIC_CAPABILITIES),
            "delegation": "NOT_ENABLED", "retryAllowed": False, **values}


def bound_envelope(request, state, **values):
    # Correlate the public reply to this validated invocation. Successful native
    # identities are separately checked against the existing upstream owner.
    if type(request) is dict and request.get("operation") in {"create", "send", "recover_create", "recover_send"}:
        request_id = request.get("requestId")
        if type(request_id) is str and REQUEST_ID.fullmatch(request_id):
            values["requestId"] = request_id
        if request.get("operation") in {"send", "recover_send"}:
            session_id = request.get("sessionId")
            if type(session_id) is str and IDENTIFIER.fullmatch(session_id):
                values["requestSessionId"] = session_id
    return envelope(state, **values)


async def execute_request(request, runtime):
    mutation_sent = False
    operation = "unknown"
    try:
        operation, params = normalize_request(request)
        endpoint, public = qualify_identity(await runtime.identify(), runtime.home)
        readonly_capacity = bool(getattr(runtime, "readonly_capacity_qualified", lambda: False)())
        # Deferred plugin tools are real scope. Inspect the exact installed source
        # only when a mutation needs live send eligibility; never load/register it.
        readonly_omh = readonly_capacity and operation in {"create", "send"} and bool(
            getattr(runtime, "readonly_omh_qualified", lambda: False)())
        if operation == "status":
            return bound_envelope(request, "READY", operation=operation, runtime=public)
        if operation == "list":
            observed = await asyncio.to_thread(runtime.list_history)
            return bound_envelope(request, "READY", operation=operation, runtime=public, **observed)
        if operation == "read":
            observed = await asyncio.to_thread(runtime.read_history, params["session_id"])
            return bound_envelope(request, "READY", operation=operation, runtime=public, **observed)
        if operation == "recover_create":
            # A deterministic name alone does not prove creation. Read the
            # committed original receipt and history without attaching a viewer.
            target = await asyncio.to_thread(runtime.resolve_original, operation, params)
            observed = await asyncio.to_thread(runtime.read_history, target["session_id"],
                                               expected_request_id=params["request_id"])
            return bound_envelope(request, "OPENED", operation="recover", runtime=public, **observed)
        original_create = None
        if operation in {"create", "send"}:
            await asyncio.to_thread(runtime.require_recovery_source)
            if operation == "create":
                original_create = await asyncio.to_thread(runtime.create_identity, request["requestId"])
        async with runtime.connect(endpoint) as client:
            if operation == "recover_send":
                # Absence, pruning and read failure never prove no effect.
                target = await asyncio.to_thread(runtime.resolve_original, operation, params)
                result = await client.rpc("prompt.receipt", session_id=target["session_id"], admission_id=target["admission_id"])
                projected = project_result("receipt", result, target["session_id"], readonly_capacity=readonly_capacity, readonly_omh=readonly_omh)
                if projected["receipt"]["id"] != target["admission_id"]:
                    raise BridgeRefusal("NATIVE_RECEIPT_MISMATCH")
                return bound_envelope(request, "ADMITTED", operation="recover", runtime=public, **projected)
            if operation == "send":
                # The wire owner requires this connection's subscription before
                # submission. Attach only for the explicit send, omit transcript
                # hydration, and recheck current policy and positive live holds.
                original = await client.rpc("session.resume", session_id=params["session_id"], omit_messages=True)
                observed = project_result("read", original, params["session_id"], readonly_capacity=readonly_capacity, readonly_omh=readonly_omh)
                live = observed["session"]
                if not live["canSend"]:
                    raise BridgeRefusal("NATIVE_SESSION_POLICY_UNQUALIFIED")
                if live["running"] or live["pending"]:
                    raise BridgeRefusal("NATIVE_SESSION_BUSY")
                if live["promptsPending"] or original.get("pending_connection"):
                    raise BridgeRefusal("NATIVE_PROMPT_PENDING")
            mutation_sent = operation in {"create", "send"}
            result = await client.rpc(METHODS[operation], **params)
            expected_session = original_create["session_id"] if original_create else params.get("session_id")
            projected = project_result(operation, result, expected_session, readonly_capacity=readonly_capacity, readonly_omh=readonly_omh)
            if operation == "send":
                original_send = await asyncio.to_thread(runtime.resolve_original, "recover_send",
                    {"session_id": params["session_id"], "request_id": request["requestId"]})
                if projected["receipt"]["id"] != original_send["admission_id"]:
                    raise BridgeRefusal("NATIVE_RECEIPT_MISMATCH")
            if operation == "receipt" and projected["receipt"]["id"] != params["admission_id"]:
                raise BridgeRefusal("NATIVE_RECEIPT_MISMATCH")
            state = {"create": "OPENED", "send": "ADMITTED"}.get(operation, "READY")
            return bound_envelope(request, state, operation=operation, runtime=public, **projected)
    except OwnerRefusal as exc:
        if operation.startswith("recover_"):
            return bound_envelope(request, "EFFECT_UNKNOWN", operation="recover", code="NATIVE_RECOVERY_UNRESOLVED")
        if mutation_sent and not exc.proves_rejection():
            return bound_envelope(request, "EFFECT_UNKNOWN", operation=operation, code="NATIVE_OUTCOME_UNKNOWN")
        reason = str(exc)
        code = reason if re.fullmatch(r"[a-z_]{1,80}", reason) else "NATIVE_REFUSED"
        return bound_envelope(request, "REFUSED", operation=operation, code=code)
    except NotSent:
        if operation.startswith("recover_"):
            return bound_envelope(request, "EFFECT_UNKNOWN", operation="recover", code="NATIVE_RECOVERY_UNRESOLVED")
        return bound_envelope(request, "NOT_SENT", operation=operation, code="NATIVE_NOT_SENT")
    except BridgeRefusal as exc:
        recovering = operation.startswith("recover_")
        return bound_envelope(request, "EFFECT_UNKNOWN" if mutation_sent or recovering else "REFUSED",
                        operation="recover" if recovering else operation, code=str(exc))
    except Exception:
        recovering = operation.startswith("recover_")
        not_sent = operation in {"create", "send"} and not mutation_sent
        return bound_envelope(request, "EFFECT_UNKNOWN" if mutation_sent or recovering else "NOT_SENT" if not_sent else "UNAVAILABLE",
                        operation="recover" if recovering else operation,
                        code="NATIVE_OUTCOME_UNKNOWN" if mutation_sent or recovering else "NATIVE_NOT_SENT" if not_sent else "NATIVE_UNAVAILABLE")


# Qualification of the already-installed read-only Mastermind OMH adapter and
# its actual interpreter dependency. No installer, runtime, registration or grant.
OMH_READONLY_PINS = {
    "release": "58ac65ae47824750cae32c5ab85b58b6f38e6d5e",
    "plugin.yaml": "a426392c03a151903f3376a3343d666372c206cd04a244937291fe263ca64b22",
    "__init__.py": "e72da67dfb64314c849c8b44b44c25e7707e3576f003df7a3ccabf3326a2cb70",
    "descriptor": "7aa738444942825ef223c8af773c7541b678898686a184efa1ca47236ef1bf3b",
    "python": "87d4df53fd91304be5bac391fb204643c36b7df2023c04a0953bcbc7d4fdf634",
    "pyvenv.cfg": "a4b4a334bb8aa27404a11068ba34f3f0f3470a6d5d109f0e6a9587e60422945c",
    "metadata": "b3ac978c27cdbb94a1e17a0ee0035fc54c14c6ccc53fa7879dcb137e6e8fdc1a",
    "dependency": "5178ac807671d0218b7668ebc3cd5d24a2d8fc4459ec245142cabc149afc03e4",
    "dependency_files": 1240,
    "stdlib_sitecustomize": "cbf9d8d0f07943b63ed5e5983e2b33d91fadc54251e66df7eb7c31f1b816b5d6",
    "model_tools": "24850d5ce74f7bcf17e58638fc787d6b955bfb89f4980e74b361d7927de74581",
}


def qualified_source_bytes(path, expected=None, maximum=1024 * 1024):
    """Read bounded pinned source without importing it or following symlinks."""
    import stat
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
    if path.resolve() != path:
        raise ValueError("source link")
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > maximum
                or before.st_mode & 0o022):
            raise ValueError("source file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        if (len(raw) > maximum or
                (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError("source changed")
        if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("source digest")
        return raw
    finally:
        os.close(fd)


class NativeRuntime:
    def __init__(self):
        import pwd
        import sys
        self.home = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".hermes"
        root = self.home / "hermes-agent"
        if root.resolve() != root or not root.is_dir():
            raise BridgeRefusal("NATIVE_INSTALL_UNAVAILABLE")
        os.environ["HERMES_HOME"] = str(self.home)
        sys.path.insert(0, str(root))
        # Reuse the committed upstream dependency owner without prepare_launch,
        # recovery, provisioning or activation. Pin this selected generation only.
        import site
        from pm.environments import committed_venv, site_packages
        from hermes_cli.runtime_state import lease_generation
        environment = committed_venv(root)
        if environment is None:
            raise BridgeRefusal("NATIVE_DEPENDENCIES_UNAVAILABLE")
        release = lease_generation(environment)
        if committed_venv(root) != environment:
            release()
            raise BridgeRefusal("NATIVE_DEPENDENCIES_CHANGED")
        selected = site_packages(environment)
        if not selected.is_dir():
            release()
            raise BridgeRefusal("NATIVE_DEPENDENCIES_UNAVAILABLE")
        site.addsitedir(str(selected))
        sys.path.insert(0, str(selected))

    def require_recovery_source(self):
        root = self.home / "hermes-agent"
        hashes = {
            "hermes_state_keys.py": "46a44bcc9a82552c606fc0eaec275aac76bfe3c5523d7793218377d15cccc676",
            "hermes_state.py": "dd50e9091ce6b9ebd76d157661bf82aa135d9c6bfe56ec57aed02b3cf901c4f2",
            "hermes_state_runtime.py": "6bbcc688799d3ea784545b5227d20e07f8b5ce8f26fcf545825bc8a60462ee3f",
        }
        if getattr(self, "observed_code", None) != "2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19":
            raise BridgeRefusal("NATIVE_RECOVERY_SOURCE_CHANGED")
        for name, expected in hashes.items():
            source = root / name
            if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise BridgeRefusal("NATIVE_RECOVERY_SOURCE_CHANGED")

    def require_history_source(self):
        self.require_recovery_source()
        root = self.home / "hermes-agent"
        hashes = {
            "hermes_state_local.py": "359a03844bab07242c47748e9771fcc5d16a5144d4d099aeff483dc6f0efd1d2",
            "hermes_state_local_lineage.py": "6e644e387f18a54ef1fd3e63dedbc5523ccddc00faab0c7de0f2432f1dce4bd3",
            "hermes_state_local_migration.py": "0d4e2e1aa59e0cdafedcb38abe6ca2f82d24a9ad98b3a0629656e2816c3878bb",
            "hermes_state_sessions.py": "85a4abc342fd0711cd750750d2cbc948f85804af1c433dccc8d2454b1e77c18d",
            "hermes_state_messages.py": "b81c7d272f768a548daa91642bf8283dfad2f592528fbe95c029038a13e7f574",
            "hermes_state_compression.py": "be9cc0bdca5fae8d5cbe8a15ca04cb72005228c290fa4e3d0a100e5e30796d7e",
            "gateway/owner_identity.py": "4cb7810a49a5c3f2ddec645d00ecc90ac7b86edb862e16ea8cf4b039408546be",
            "gateway/session.py": "ea2e48b1313fcb24054dccbbdc631321c7cad5526097588b65d20ab86346a870",
        }
        for name, expected in hashes.items():
            source = root / name
            if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise BridgeRefusal("NATIVE_HISTORY_SOURCE_CHANGED")

    @contextmanager
    def readonly_database(self):
        """Use the incumbent store in mode=ro; never initialize or migrate it."""
        import stat
        from hermes_state import SessionDB
        path = self.home / "state.db"
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_mode & 0o022):
            raise BridgeRefusal("NATIVE_RECOVERY_UNAVAILABLE")
        db = SessionDB(path, read_only=True)
        try:
            yield db
        finally:
            db.close()
        after = path.lstat()
        if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                or not stat.S_ISREG(after.st_mode) or after.st_uid != os.getuid() or after.st_mode & 0o022):
            raise BridgeRefusal("NATIVE_RECOVERY_UNAVAILABLE")

    def create_identity(self, request_id):
        """Expected identity for a NEW create; existence is not required yet."""
        self.require_recovery_source()
        from hermes_state_keys import local_identity
        return {"session_id": local_identity(str(self.home), f"uid:{os.getuid()}", request_id)}

    def owned_history(self, db, session_id, *, expected_request_id=None):
        """Qualify the canonical local receipt, route, origin and physical target."""
        from gateway.config import Platform
        from gateway.owner_identity import same_owner
        from gateway.session import SessionSource, build_session_key
        from hermes_state_keys import local_identity
        from hermes_state_local import local_lineage_owner, local_receipt
        from hermes_state_local_lineage import validate_local_lineage
        from hermes_state_runtime import RuntimeStoreError
        try:
            with db._read_ctx() as conn:
                owner = local_lineage_owner(conn, session_id)
            receipt = local_receipt(db, owner)
            principal = receipt["principal_id"]
            if (receipt["profile_id"] != str(self.home)
                    or not same_owner(principal, f"uid:{os.getuid()}")
                    or receipt["session_id"] != owner
                    or ("legacy_session_id" in receipt and receipt["legacy_session_id"] != owner)
                    or ("legacy_session_id" not in receipt and owner !=
                        local_identity(str(self.home), principal, receipt["request_id"]))
                    or (expected_request_id is not None and receipt["request_id"] != expected_request_id)):
                raise ValueError("foreign receipt")
            # This adapter is fixed to the primary home, whose LOCAL source has no
            # secondary-profile namespace. Use the incumbent pure key builder.
            source = SessionSource(platform=Platform.LOCAL, chat_id=owner, user_id=principal, chat_type="dm")
            route = build_session_key(source)
            entry = receipt["entry"]
            if (receipt["route"] != route or entry["session_key"] != route
                    or entry["origin"] != source.to_dict()):
                raise ValueError("foreign route or origin")
            with db._read_ctx() as conn:
                target = validate_local_lineage(conn, receipt)
            row, logical = db.get_session(target), db.get_session(owner)
            if (row is None or logical is None
                    or (row["session_key"], row["chat_id"], row["user_id"]) != (route, owner, principal)
                    or json.loads(row["origin_json"]) != source.to_dict()):
                raise ValueError("foreign target")
            return owner, receipt, row, logical
        except (KeyError, TypeError, ValueError, RuntimeStoreError):
            raise BridgeRefusal("NATIVE_HISTORY_UNAVAILABLE") from None

    def list_history(self):
        """Bounded enumeration, filtered before projecting any private metadata."""
        self.require_history_source()
        result, seen = [], set()
        with self.readonly_database() as db:
            for offset in range(0, 1000, 200):
                rows = db.list_sessions_rich(sources=["tool", "local", "cli", "gui", "desktop", "tui"],
                    limit=200, offset=offset, order_by_last_active=True, compact_rows=True)
                for candidate in rows:
                    try:
                        owner, receipt, row, _ = self.owned_history(db, candidate["id"])
                    except BridgeRefusal:
                        continue
                    if owner in seen:
                        continue
                    seen.add(owner)
                    count = integer(db.get_resume_message_count(row["id"]))
                    if self.owned_history(db, owner)[1] != receipt:
                        raise BridgeRefusal("NATIVE_HISTORY_CHANGED")
                    result.append({
                        "id": identifier(owner),
                        "title": display(row.get("title") or "", 512),
                        "running": None,
                        "messageCount": count,
                    })
                    if len(result) == 50:
                        break
                if len(result) == 50 or len(rows) < 200:
                    break
        return {"sessions": result}

    def read_history(self, session_id, *, expected_request_id=None):
        """Display stored history without attaching, refreshing policy or firing hooks."""
        self.require_history_source()
        from hermes_state_runtime import list_session_admissions
        with self.readonly_database() as db:
            owner, receipt, row, logical = self.owned_history(db, session_id,
                expected_request_id=expected_request_id)
            # A single bounded owner read avoids shifting newest-relative offsets
            # when messages arrive between separate autocommit queries.
            page = db.get_messages(row["id"], include_compacted=True, include_ancestors=True,
                                   limit=1000, offset=0, latest=True)
            visible = [{"role": item["role"], "text": message_text(item.get("content", ""))}
                       for item in page if item.get("role") in {"user", "assistant"}]
            pending = list_session_admissions(db, session_id=owner)
            if len(pending) > 1000:
                raise BridgeRefusal("NATIVE_RESPONSE_INVALID")
            projected = [{"id": identifier(item["admission_id"]), "status": admission_status(item["status"])}
                         for item in pending]
            count = integer(db.get_resume_message_count(row["id"]))
            if count < len(visible[-100:]) or self.owned_history(db, owner)[1] != receipt:
                raise BridgeRefusal("NATIVE_HISTORY_CHANGED")
            result = {"id": identifier(owner), "storedId": identifier(row["id"]),
                "title": display(row.get("title") or "", 512), "requestedModel": display(row.get("model") or "", 160),
                "canSend": False, "toolAccess": "UNQUALIFIED", "sendCheckRequired": True,
                "running": None, "executionGeneration": integer(logical.get("runtime_generation")),
                "messageCount": count, "messages": visible[-100:],
                "historyTruncated": len(visible) > 100 or len(page) == 1000, "pending": projected,
                "promptsPending": None}
        return {"session": result}

    def resolve_original(self, operation, params):
        """Read the incumbent exact identity/ledger; never replay prompt.submit."""
        self.require_recovery_source()
        principal = f"uid:{os.getuid()}"
        if operation == "recover_create":
            target = self.create_identity(params["request_id"])
            self.require_history_source()
            with self.readonly_database() as db:
                owner, _, _, _ = self.owned_history(db, target["session_id"],
                    expected_request_id=params["request_id"])
            return {"session_id": owner}
        from hermes_state_runtime import find_session_admission
        with self.readonly_database() as db:
            row = find_session_admission(db, principal_id=principal,
                session_id=params["session_id"], request_id=params["request_id"])
        if not row or row.get("principal_id") != principal or row.get("target_session_id") != params["session_id"] or row.get("request_id") != params["request_id"]:
            raise BridgeRefusal("NATIVE_RECOVERY_UNRESOLVED")
        return {"session_id": params["session_id"], "admission_id": identifier(row.get("admission_id"))}

    async def identify(self):
        from hermes_cli.gateway_client import private_control_query
        raw = await asyncio.to_thread(private_control_query, self.home,
            b'{"protocol":1,"id":1,"verb":"identify"}\n', 3)
        answer = json.loads(raw)
        self.observed_code = answer.get("result", {}).get("code_sha")
        return answer

    def readonly_capacity_qualified(self):
        """Qualify the already-installed read-only scope, never enroll or configure it.

        A protocol-compatible upgrade can still connect. Changed tool implementation
        needs a new adapter qualification before this adapter calls it read-only.
        """
        import hashlib
        try:
            if getattr(self, "observed_code", None) != "2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19":
                return False
            root = self.home / "hermes-agent"
            hashes = {
                root / "tools/tool_search.py": "87e06c029304dae1ff1f592fa97f238165a04f1406cbdab68a2e3a0c3fd489a5",
                root / "agent/tool_executor.py": "c85e239d1d56ad415902db2371e9e28c2216f6fd72e29860cff7f97b2e05a0c2",
                self.home / "bridges/fabric_capacity_mcp.py": "4d3f88a1b0ef0cbb501439acacebcbb5aa874cbd84c27755e87becda4b8a245c",
            }
            for path, digest in hashes.items():
                if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    return False
            import hermes_yaml
            config = hermes_yaml.safe_load((self.home / "config.yaml").read_text())
            servers = config.get("mcp_servers")
            if type(servers) is not dict or set(servers) != {"mastermind-fabric-capacity"}:
                return False
            server = servers["mastermind-fabric-capacity"]
            return (type(server) is dict and set(server) <= {"command", "args", "enabled", "connect_timeout"}
                and server.get("enabled") is True and server.get("command") == "/opt/homebrew/bin/python3"
                and server.get("args") == [str(self.home / "bridges/fabric_capacity_mcp.py")])
        except Exception:
            return False

    def readonly_omh_qualified(self):
        """Recognize one installed advisory bridge; never enable another toolset."""
        try:
            if getattr(self, "observed_code", None) != "2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19":
                return False
            pins = OMH_READONLY_PINS
            plugin = self.home / "plugins/mastermind-omh"
            for name in ("plugin.yaml", "__init__.py"):
                qualified_source_bytes(plugin / name, pins[name])
            raw = qualified_source_bytes(plugin / "_runtime.json", pins["descriptor"])
            descriptor = closed_json(raw)
            source = plugin / "_source" / pins["release"]
            venv = self.home.parent / ".local/share/omh/venv"
            expected = {
                "schema": "mastermind.hermes_omh.local_runtime/v1", "release_commit": pins["release"],
                "source_root": str(source), "profile_home": str(self.home),
                "omh_home": str(self.home.parent / ".omh"),
                "python_executable": str(venv / "bin/python"),
            }
            if (type(descriptor) is not dict or set(descriptor) != set(expected) | {"source_files"}
                    or any(descriptor[key] != value for key, value in expected.items())):
                return False
            # The descriptor's whole-file pin fixes this exact adapter closure.
            sources = descriptor["source_files"]
            if type(sources) is not dict or len(sources) != 19:
                return False
            if {path.relative_to(source).as_posix() for path in source.rglob("*.py")} != set(sources):
                return False
            for relative, digest in sources.items():
                path = Path(relative)
                if path.is_absolute() or ".." in path.parts:
                    return False
                qualified_source_bytes(source / path, digest)
            qualified_source_bytes(venv / "pyvenv.cfg", pins["pyvenv.cfg"])
            interpreter = (venv / "bin/python").resolve()
            qualified_source_bytes(interpreter, pins["python"])
            site = venv / "lib/python3.14/site-packages"
            stdlib = interpreter.parent.parent / "lib/python3.14"
            # -I still initializes site. This enrolled venv has no .pth hooks;
            # only the exact Homebrew stdlib customization is present.
            for root, expected_customizations in [(site, set()), (stdlib, {"sitecustomize.py"})]:
                entries = list(root.iterdir())
                if any(path.suffix.lower() == ".pth" for path in entries):
                    return False
                customizations = {path.name for path in entries
                    if path.name.lower().startswith(("sitecustomize", "usercustomize"))}
                if customizations != expected_customizations:
                    return False
            qualified_source_bytes(stdlib / "sitecustomize.py", pins["stdlib_sitecustomize"])
            qualified_source_bytes(site / "oh_my_hermes-4.0.6.dist-info/METADATA", pins["metadata"])
            package = site / "omh"
            if any(path.suffix.lower() in {".so", ".dylib", ".pyd"}
                    for root in (source, package) for path in root.rglob("*")):
                return False
            # Trusted installed-source qualification, not an attestation against
            # a hostile local interpreter or tampered executable bytecode cache.
            paths = []
            for path in package.rglob("*.py"):
                paths.append(path)
                if len(paths) > pins["dependency_files"]:
                    return False
            if len(paths) != pins["dependency_files"]:
                return False
            digest, total = hashlib.sha256(), 0
            for path in sorted(paths):
                raw = qualified_source_bytes(path)
                total += len(raw)
                if total > 32 * 1024 * 1024:
                    return False
                digest.update(path.relative_to(package).as_posix().encode() + b"\0" + hashlib.sha256(raw).digest())
            if digest.hexdigest() != pins["dependency"]:
                return False
            qualified_source_bytes(self.home / "hermes-agent/model_tools.py", pins["model_tools"])
            return True
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return False

    @asynccontextmanager
    async def connect(self, endpoint):
        from hermes_cli.gateway_client import connect_gateway
        # Explicit endpoint prevents upstream ensure/start, including when the service is down.
        async with connect_gateway(endpoint=endpoint, max_size=1024 * 1024) as client:
            class Port:
                async def rpc(self, method, **params):
                    from hermes_cli.gateway_client import GatewayRPCError, GatewayClientError, NOT_SENT
                    try:
                        return await client.rpc(method, _timeout=8, **params)
                    except GatewayRPCError as exc:
                        raise OwnerRefusal(str(exc), code=exc.code) from None
                    except GatewayClientError as exc:
                        if str(exc) == NOT_SENT:
                            raise NotSent() from None
                        raise
            yield Port()


def closed_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BridgeRefusal("REQUEST_INVALID")
            result[key] = value
        return result
    def bad_constant(_):
        raise BridgeRefusal("REQUEST_INVALID")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def main():
    import contextlib
    import sys
    request = None
    operation = "unknown"
    execution_started = False
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise BridgeRefusal("REQUEST_INVALID")
        request = closed_json(raw)
        operation, _ = normalize_request(request)
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            runtime = NativeRuntime()
            execution_started = True
            result = asyncio.run(execute_request(request, runtime))
    except Exception:
        mutating = operation in {"create", "send"}
        recovering = operation.startswith("recover_")
        not_sent = mutating and not execution_started
        result = bound_envelope(request, "NOT_SENT" if not_sent else "EFFECT_UNKNOWN" if mutating or recovering else "UNAVAILABLE",
                          operation="recover" if recovering else operation,
                          code="NATIVE_NOT_SENT" if not_sent else "NATIVE_CLIENT_UNAVAILABLE")
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 1024 * 1024:
        mutating = type(request) is dict and request.get("operation") in {"create", "send"}
        encoded = json.dumps(bound_envelope(request, "EFFECT_UNKNOWN" if mutating or operation.startswith("recover_") else "UNAVAILABLE",
                                      operation="recover" if operation.startswith("recover_") else operation,
                                      code="NATIVE_RESPONSE_TOO_LARGE")).encode()
    sys.stdout.buffer.write(encoded + b"\n")


if __name__ == "__main__":
    main()
