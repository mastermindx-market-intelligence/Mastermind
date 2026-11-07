"""One-shot local native Hermes client embedded in the authenticated native OS host.
No daemon, provider, store, retry, process activation or remote proxy. Native
session tickets and unprojected RPC replies never cross into the renderer.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
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
METHODS = {"create": "session.create", "list": "session.list", "read": "session.resume",
           "send": "prompt.submit", "receipt": "prompt.receipt"}
FIELDS = {"status": {"operation"}, "list": {"operation"},
          "create": {"operation", "role", "requestId"}, "read": {"operation", "sessionId"},
          "send": {"operation", "sessionId", "requestId", "text"},
          "receipt": {"operation", "sessionId", "admissionId"}}


class BridgeRefusal(ValueError):
    pass


class OwnerRefusal(ValueError):
    pass


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
        return operation, {"scope": "stored", "limit": 50, "include_hidden": True}
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
    return endpoint, {"protocol": 1, "instanceId": instance, "authorityEpoch": data["authority_epoch"],
                      "version": version, "sourceRevision": revision}


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


def session_tool_access(info, readonly_capacity=False):
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
    if (readonly_capacity and info.get("enabled_toolsets") == ["mastermind-fabric-capacity"]
            and type(info.get("tool_count")) is int and info["tool_count"] == 3
            and tools == {"other": ["tool_search", "tool_describe", "tool_call"]}):
        return "CAPACITY_READ_ONLY"
    return "UNQUALIFIED"


def project_result(operation, value, session_id=None, *, readonly_capacity=False):
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
            "canSend": session_tool_access(info, readonly_capacity) != "UNQUALIFIED",
            "toolAccess": session_tool_access(info, readonly_capacity), "running": value["running"], "executionGeneration": integer(value.get("execution_generation")),
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


async def execute_request(request, runtime):
    mutation_sent = False
    operation = "unknown"
    try:
        operation, params = normalize_request(request)
        endpoint, public = qualify_identity(await runtime.identify(), runtime.home)
        readonly_capacity = bool(getattr(runtime, "readonly_capacity_qualified", lambda: False)())
        if operation == "status":
            return envelope("READY", operation=operation, runtime=public)
        async with runtime.connect(endpoint) as client:
            if operation == "send":
                original = await client.rpc("session.resume", session_id=params["session_id"])
                observed = project_result("read", original, params["session_id"], readonly_capacity=readonly_capacity)
                if not observed["session"]["canSend"]:
                    raise BridgeRefusal("NATIVE_SESSION_POLICY_UNQUALIFIED")
            mutation_sent = operation in {"create", "send"}
            result = await client.rpc(METHODS[operation], **params)
            projected = project_result(operation, result, params.get("session_id"), readonly_capacity=readonly_capacity)
            if operation == "receipt" and projected["receipt"]["id"] != params["admission_id"]:
                raise BridgeRefusal("NATIVE_RECEIPT_MISMATCH")
            state = {"create": "OPENED", "send": "ADMITTED"}.get(operation, "READY")
            return envelope(state, operation=operation, runtime=public, **projected)
    except OwnerRefusal as exc:
        reason = str(exc)
        code = reason if re.fullmatch(r"[a-z_]{1,80}", reason) else "NATIVE_REFUSED"
        return envelope("REFUSED", operation=operation, code=code)
    except NotSent:
        return envelope("NOT_SENT", operation=operation, code="NATIVE_NOT_SENT")
    except BridgeRefusal as exc:
        return envelope("EFFECT_UNKNOWN" if mutation_sent else "REFUSED", operation=operation, code=str(exc))
    except Exception:
        return envelope("EFFECT_UNKNOWN" if mutation_sent else "UNAVAILABLE", operation=operation,
                        code="NATIVE_OUTCOME_UNKNOWN" if mutation_sent else "NATIVE_UNAVAILABLE")


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
                        raise OwnerRefusal(str(exc)) from None
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
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise BridgeRefusal("REQUEST_INVALID")
        request = closed_json(raw)
        normalize_request(request)
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            result = asyncio.run(execute_request(request, NativeRuntime()))
    except Exception:
        result = envelope("UNAVAILABLE", code="NATIVE_CLIENT_UNAVAILABLE")
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 1024 * 1024:
        mutating = type(request) is dict and request.get("operation") in {"create", "send"}
        encoded = json.dumps(envelope("EFFECT_UNKNOWN" if mutating else "UNAVAILABLE", code="NATIVE_RESPONSE_TOO_LARGE")).encode()
    sys.stdout.buffer.write(encoded + b"\n")


if __name__ == "__main__":
    main()
