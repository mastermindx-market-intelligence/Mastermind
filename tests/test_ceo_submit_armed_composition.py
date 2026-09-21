from __future__ import annotations

import ast
import asyncio
import importlib
import io
import json
import math
import os
import re
import subprocess
import tokenize
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


ROOT = Path(__file__).parents[1]
PHASE1C = ROOT / "scripts" / "executive_os_phase1c.py"
TEMPLATE = ROOT / "ops" / "executive_os" / "control.json.template"


# scripts/executive_os_phase1c.py:453 forces control_uid == os.geteuid(), so the host
# uid is the one identity a fixture cannot pin; the App peer is rejected when it matches
# control_uid (:387-391) or the Operator uid (:474). Consume the other literals the
# admitted fixtures supply through _off_host so a host uid that happens to equal one of
# them cannot join that set and decide the outcome.
_HOST_UID = os.geteuid()


def _off_host(uid: int) -> int:
    """Shift an identity literal that happens to equal the host uid.

    The assertions are about DISTINCTNESS, never about which integers stand in, so a
    collision-only shift changes nothing they prove and removes the last way a host uid
    can decide an outcome. +16 cannot collide with any other literal used here.
    """
    return uid if uid != _HOST_UID else uid + 16


def _raw(tmp_path: Path, **extra: object) -> dict[str, object]:
    uid = os.geteuid()
    raw: dict[str, object] = {
        "schema_version": "mastermind.executive_control_config/v1",
        "runtime_root": str(tmp_path / "runtime"),
        "control_socket_path": str(tmp_path / "control.sock"),
        "launchd_socket_name": "Operator",
        "worker_broker_socket_path": str(tmp_path / "worker.sock"),
        "worker_provider_home": str(tmp_path / "provider-home"),
        "worker_runs_root": str(tmp_path / "runs"),
        "receipts_root": str(tmp_path / "receipts"),
        "proof_source_repository": str(tmp_path / "repo"),
        "proof_workspace_root": str(tmp_path / "workspace"),
        "proof_base_sha": "a" * 40,
        "backup_root": str(tmp_path / "backups"),
        "control_uid": uid,
        "worker_uid": uid + 1,
        "worker_gid": uid + 1,
        "worker_user": "_mastermind_worker",
        "shared_run_gid": uid + 2,
        "allowed_peer_uids": [uid],
        "secret_canary_receipt_path": str(tmp_path / "canary.json"),
        "control_environment_attestation_path": str(tmp_path / "attestation.json"),
    }
    raw.update(extra)
    return raw


def _write(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / "control.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    path.chmod(0o600)
    return path


def _module():
    return importlib.import_module("scripts.executive_os_phase1c")


def _added_line_numbers(path: Path, base: str) -> set[int]:
    diff = subprocess.run(
        ["git", "diff", "--unified=0", base, "--", str(path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    lines: set[int] = set()
    for line in diff.splitlines():
        if not line.startswith("@@"):
            continue
        added = line.split("+")[1].split(" ")[0]
        start, _, count = added.partition(",")
        first = int(start)
        amount = int(count) if count else 1
        lines.update(range(first, first + amount))
    return lines


def _identity_guard_source_path(path: str) -> bool:
    """Keep the identity guard on source/config, not narrative proof records.

    Markdown prose is not Python source. Evidence JSON is routed through the
    structural identity check below, never exempted from identity checking.
    Executable code and all other configuration retain the generic token guard.
    """
    parts = Path(path).parts
    if not parts or Path(path).is_absolute() or ".." in parts:
        return True
    if parts[0] in {"docs", "research"} and Path(path).suffix == ".md":
        return False
    if parts[:2] == ("research", "evidence") and Path(path).suffix == ".json":
        return False
    return True


def _identity_guard_evidence_json_path(path: str) -> bool:
    parts = Path(path).parts
    return (not Path(path).is_absolute() and ".." not in parts
            and parts[:2] == ("research", "evidence") and Path(path).suffix == ".json")


def _scan_evidence_identity_literals(document: str) -> list[str]:
    """Check identity-bearing JSON values without treating all metrics as UIDs.

    This is a bounded literal guard, not whole-program dataflow analysis. Runtime
    admission remains authoritative. Malformed/duplicate-key evidence fails closed.
    """
    assert len(document.encode("utf-8")) <= 1024 * 1024, "evidence JSON exceeds limit"

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError("non-finite JSON value")

    try:
        value = json.loads(document, object_pairs_hook=unique_object,
                           parse_constant=reject_constant)
    except (ValueError, RecursionError) as exc:
        raise AssertionError("evidence JSON is not an unambiguous document") from exc
    assert isinstance(value, dict), "evidence JSON must be an object record"
    identity_words = {"uid", "uids", "gid", "gids", "euid", "egid", "suid", "sgid",
                      "peer", "peers", "account", "accounts", "principal", "principals",
                      "user", "users", "group", "groups", "identity", "identities",
                      "owner", "owners"}
    flagged = []
    pending = [(value, False, 0)]
    visited = 0
    while pending:
        item, identity, depth = pending.pop()
        visited += 1
        assert depth <= 32 and visited <= 10000, "evidence JSON structure exceeds limit"
        if isinstance(item, float):
            assert math.isfinite(item), "evidence JSON contains a non-finite number"
        if isinstance(item, dict):
            for key, child in item.items():
                words = set(re.split(r"[^a-z0-9]+", re.sub(
                    r"(?<=[a-z0-9])(?=[A-Z])", "_", key).lower()))
                child_identity = identity or bool(words & identity_words)
                pending.append((child, child_identity, depth + 1))
                if identity:
                    pending.append((key, True, depth + 1))
        elif isinstance(item, list):
            pending.extend((child, identity, depth + 1) for child in item)
        elif identity and not isinstance(item, bool) and item is not None:
            if isinstance(item, str):
                item = item.strip()
                assert len(item) <= 256, "evidence identity string exceeds limit"
                if item.startswith("_mastermind_"):
                    flagged.append(item)
                    continue
            try:
                if isinstance(item, str):
                    try:
                        number = int(item, 0)
                    except ValueError:
                        # Decimal construction is exact; do not pass through float
                        # or apply context rounding. Bound before integer expansion.
                        decimal_value = Decimal(item)
                        if (not decimal_value.is_finite()
                                or not 400 <= decimal_value <= 999
                                or decimal_value != decimal_value.to_integral_value()):
                            continue
                        number = int(decimal_value)
                elif isinstance(item, (int, float)) and int(item) == item:
                    number = int(item)
                else:
                    continue
            except (ValueError, OverflowError, InvalidOperation):
                continue
            if 400 <= number <= 999:
                flagged.append(str(item))
    return flagged


_NON_PRODUCTION_IDENTITY_FILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
_PERMISSION_MODE_MARKERS = ("chmod", "umask", "st_mode", "dir_mode", "file_mode", "permission")
_HTTP_STATUS_MARKERS = (
    "sendjsonerror(", "err?.status", "http_fallback", "http_code",
    ".status(", "response.status", "statuscode",
)
_COMMENT_PREFIXES = ("#", "//", "/*", "*/", "* ")
_SOURCE_IDENTITY_WORDS = {
    "uid", "uids", "gid", "gids", "euid", "egid", "suid", "sgid",
    "peer", "peers", "account", "accounts", "principal", "principals",
    "user", "users", "group", "groups", "identity", "identities",
    "owner", "owners", "port", "ports", "socket", "sockets",
    "endpoint", "endpoints", "topology",
}
_SOURCE_SYNTAX_NAMES = {
    "as", "class", "const", "def", "else", "false", "from", "function",
    "if", "import", "in", "let", "none", "null", "return", "true", "var",
}


def _is_production_identity_scan_path(path: str) -> bool:
    if not _identity_guard_source_path(path):
        return False
    name = Path(path).name
    if name.startswith("test_") or name.endswith("_test.py") or ".test." in name:
        return False
    if name in _NON_PRODUCTION_IDENTITY_FILES or name.endswith((".lock", ".md", ".rst")):
        return False
    if name.startswith(("README", "CHANGELOG", "LICENSE")):
        return False
    return True


def _semantic_words(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", normalized)
    normalized = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", normalized)
    return {word for word in re.split(r"[^a-z0-9]+", normalized.lower()) if word}


def _source_identifiers(line: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", line)
    return {
        name for name in re.findall(r"[^\W\d]\w*", normalized, flags=re.UNICODE)
        if name.lower() not in _SOURCE_SYNTAX_NAMES
    }


def _line_mentions_identity_name(line: str) -> bool:
    normalized = unicodedata.normalize("NFKC", line)
    return "_mastermind_" in normalized.lower() or bool(
        _semantic_words(normalized) & _SOURCE_IDENTITY_WORDS
    )


def _import_bindings(names: str) -> list[tuple[str, str]]:
    """Return (exported, local) names from a bounded Python/JS named import."""
    bindings: list[tuple[str, str]] = []
    identifier = r"[^\W\d]\w*"
    for item in names.strip().strip("()").split(","):
        match = re.fullmatch(
            rf"\s*({identifier})(?:\s+as\s+({identifier}))?\s*;?\s*",
            unicodedata.normalize("NFKC", item), flags=re.UNICODE,
        )
        if match:
            exported = match.group(1)
            bindings.append((exported, match.group(2) or exported))
    return bindings


def _python_import_edge(line: str) -> tuple[str, list[tuple[str, str]]] | None:
    """Parse one Python ``from`` import with Python's own comment/alias rules."""
    try:
        tree = ast.parse(unicodedata.normalize("NFKC", line).lstrip(), mode="exec")
    except (SyntaxError, ValueError, TypeError):
        return None
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.ImportFrom):
        return None
    node = tree.body[0]
    module = "." * node.level + (node.module or "")
    bindings = [
        (item.name, item.asname or item.name)
        for item in node.names if item.name != "*"
    ]
    return (module, bindings) if module and bindings else None


def _python_import_source_paths(importer: str, module: str) -> tuple[str, ...]:
    """Resolve a Python ``from`` module to its repository source spellings."""
    level = len(module) - len(module.lstrip("."))
    remainder = module[level:]
    if level:
        package = list(Path(importer).parent.parts)
        if level - 1 > len(package):
            return ()
        parts = package[:len(package) - (level - 1)]
    else:
        parts = []
    if remainder:
        parts.extend(remainder.split("."))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return ()
    stem = "/".join(parts)
    # Python resolves a package before a same-named module file.
    return (f"{stem}/__init__.py", f"{stem}.py")


def _js_import_source_paths(importer: str, specifier: str) -> tuple[str, ...]:
    """Resolve a relative named JavaScript import without package aliases."""
    if not specifier.startswith(("./", "../")):
        return ()
    combined = os.path.normpath(os.path.join(os.path.dirname(importer), specifier))
    if combined == ".." or combined.startswith("../") or os.path.isabs(combined):
        return ()
    suffix = Path(combined).suffix.lower()
    extensions = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")
    if suffix:
        return (combined,) if suffix in extensions else ()
    return tuple(
        [combined + extension for extension in extensions]
        + [f"{combined}/index{extension}" for extension in extensions]
    )


def _is_known_non_identity_numeric(line: str, token_text: str, value: int) -> bool:
    stripped = line.lstrip()
    if stripped.startswith(_COMMENT_PREFIXES):
        return True
    if _line_mentions_identity_name(line):
        return False
    lowered = line.lower()
    if (
        token_text.lower().startswith("0o")
        and any(marker in lowered for marker in _PERMISSION_MODE_MARKERS)
    ):
        return True
    if 400 <= value <= 600 and any(marker in lowered for marker in _HTTP_STATUS_MARKERS):
        return True
    return False


def _scan_identity_source_lines(
    lines: list[str], *, path_identity: bool = False, identity_aliases: set[str] | None = None,
) -> list[str]:
    flagged: list[str] = []
    identity_aliases = identity_aliases or set()
    for line in lines:
        normalized = unicodedata.normalize("NFKC", line)
        line_identity = _line_mentions_identity_name(normalized)
        alias_identity = bool(_source_identifiers(normalized) & identity_aliases)
        identity_context = path_identity or line_identity or alias_identity
        try:
            tokens = tokenize.generate_tokens(io.StringIO(normalized + "\n").readline)
            for token in tokens:
                if token.type == tokenize.NUMBER:
                    try:
                        value = int(token.string, 0)
                    except ValueError:
                        continue
                    if (identity_context and 400 <= value <= 999
                            and not _is_known_non_identity_numeric(
                        normalized, token.string, value
                    )):
                        flagged.append(token.string)
                elif token.type in {tokenize.NAME, tokenize.STRING} and "_mastermind_" in token.string:
                    start = token.string.find("_mastermind_")
                    end = start + len("_mastermind_")
                    while end < len(token.string) and (token.string[end].isalnum() or token.string[end] == "_"):
                        end += 1
                    flagged.append(token.string[start:end])
        except (IndentationError, tokenize.TokenError):
            continue
    return flagged


def _scan_added_identity_literals(added_lines: str) -> list[str]:
    """Legacy positive-control helper retained for the evidence classifier tests."""
    flagged: list[str] = []
    for line in added_lines.splitlines():
        try:
            tokens = tokenize.generate_tokens(io.StringIO(line + "\n").readline)
            for token in tokens:
                if token.type == tokenize.NUMBER:
                    try:
                        value = int(token.string, 0)
                    except ValueError:
                        continue
                    if 400 <= value <= 999:
                        flagged.append(token.string)
                elif token.type == tokenize.NAME and token.string.startswith("_mastermind_"):
                    flagged.append(token.string)
        except (IndentationError, tokenize.TokenError):
            continue
    return flagged


def _scan_added_identity_diff(diff: str) -> list[str]:
    """Reject added identity/topology literals without classifying unrelated numbers.

    Numeric literals are security-relevant only when their path, line, or an alias chain
    gives them identity/topology meaning. Alias propagation spans all added production
    files, so moving a generic constant away from its UID/GID/peer/port consumer does not
    bypass the guard. Explicit HTTP-status and permission-mode lines remain semantic
    non-identity contexts unless the line itself names an identity.
    """
    additions_by_path: dict[str, list[str]] = {}
    current_path: str | None = None
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:]
            if target == "/dev/null":
                current_path = None
            elif target.startswith("b/"):
                current_path = target[2:]
                additions_by_path.setdefault(current_path, [])
            else:
                current_path = target
                additions_by_path.setdefault(current_path, [])
            continue
        if current_path is None or not raw.startswith("+") or raw.startswith("+++"):
            continue
        additions_by_path[current_path].append(raw[1:])

    production: dict[str, list[str]] = {
        path: lines for path, lines in additions_by_path.items()
        if _is_production_identity_scan_path(path)
    }

    definitions: dict[str, set[str]] = {path: set() for path in production}
    import_edges: dict[str, dict[str, set[tuple[str, str]]]] = {
        path: {} for path in production
    }
    for path, lines in production.items():
        for line in lines:
            normalized = unicodedata.normalize("NFKC", line)
            left, separator, right = normalized.partition("=")
            if separator:
                definitions[path].update(_source_identifiers(left))
            python_import = _python_import_edge(normalized)
            js_import = re.match(
                r"\s*import\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]",
                normalized,
            )
            if python_import:
                module, bindings = python_import
                candidates = _python_import_source_paths(path, module)
                # The first present candidate follows Python package/module precedence.
                source_path = next((item for item in candidates if item in production), None)
                if source_path:
                    for exported, local in bindings:
                        import_edges[path].setdefault(local, set()).add(
                            (source_path, exported)
                        )
            elif js_import:
                candidates = [
                    item for item in _js_import_source_paths(path, js_import.group(2))
                    if item in production
                ]
                # Extensionless imports are accepted only when the added diff has one
                # unambiguous module target; explicit extensions already yield one path.
                if len(candidates) == 1:
                    for exported, local in _import_bindings(js_import.group(1)):
                        import_edges[path].setdefault(local, set()).add(
                            (candidates[0], exported)
                        )

    imported: dict[str, set[str]] = {
        path: set(edges) for path, edges in import_edges.items()
    }

    aliases: dict[str, set[str]] = {path: set() for path in production}
    for path, lines in production.items():
        for line in lines:
            normalized = unicodedata.normalize("NFKC", line)
            if not _line_mentions_identity_name(normalized):
                continue
            left, separator, right = normalized.partition("=")
            candidates = _source_identifiers(right if separator else normalized)
            aliases[path].update(candidates & (definitions[path] | imported[path]))

    changed = True
    while changed:
        changed = False
        for path, lines in production.items():
            for line in lines:
                normalized = unicodedata.normalize("NFKC", line)
                left, separator, right = normalized.partition("=")
                if not separator or not (_source_identifiers(left) & aliases[path]):
                    continue
                before = len(aliases[path])
                aliases[path].update(
                    _source_identifiers(right) & (definitions[path] | imported[path])
                )
                changed = changed or len(aliases[path]) != before

            # Cross-file taint follows the resolved import module and exported binding;
            # a same-named definition in any other file has no dataflow edge.
            for local_name in aliases[path] & imported[path]:
                for source_path, source_name in import_edges[path][local_name]:
                    if source_name not in definitions[source_path]:
                        continue
                    before = len(aliases[source_path])
                    aliases[source_path].add(source_name)
                    changed = changed or len(aliases[source_path]) != before

    flagged: list[str] = []
    for path, lines in production.items():
        path_identity = bool(_semantic_words(path) & _SOURCE_IDENTITY_WORDS)
        flagged.extend(_scan_identity_source_lines(
            lines, path_identity=path_identity, identity_aliases=aliases[path],
        ))
    return flagged


def test_d1_closed_value_is_loaded_passed_through_and_unarmed(tmp_path, monkeypatch):
    module = _module()
    raw = _raw(tmp_path, ceo_submit_armed=False)
    loaded = module.load_control_config(_write(tmp_path, raw))
    captured: dict[str, object] = {}

    broker = importlib.import_module("control_plane.executive_worker_broker")
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *a, **k: object())
    monkeypatch.setattr(module, "activate_launchd_socket", lambda _name: object())

    class FakeService:
        def __init__(self, config, **kwargs):
            captured["config"] = config
            captured.update(kwargs)

    monkeypatch.setattr(module, "ExecutiveControlService", FakeService)
    module._service_from_config(loaded)
    assert captured["config"].ceo_submit_armed is False
    service_source = (ROOT / "control_plane" / "executive_service.py").read_text(encoding="utf-8")
    assert "and not self.config.ceo_submit_armed" in service_source


def test_d2_peer_admission_precedes_request_body_read(tmp_path, monkeypatch):
    from control_plane.executive_service import ExecutiveControlService
    from tests.test_executive_ceo_ingress import _FakeGrounding, _FakeSupervisor, _config

    class Reader:
        readuntil = AsyncMock()

    class Writer:
        def __init__(self):
            self.writes = []

        def get_extra_info(self, name):
            assert name == "socket"
            return object()

        def write(self, value):
            self.writes.append(value)

        async def drain(self):
            return None

        def close(self):
            return None

        async def wait_closed(self):
            return None

    reader = Reader()
    writer = Writer()
    service = ExecutiveControlService(
        _config(tmp_path, socket_root=tmp_path),
        supervisor_factory=lambda _runtime: _FakeSupervisor(),
        ceo_ingress_socket_path=tmp_path / "ceo.sock",
        ceo_ingress_peer_uid=os.geteuid() + 1,
        ceo_ingress_grounding_provider=_FakeGrounding(),
        ceo_ingress_armed=True,
    )
    monkeypatch.setattr("control_plane.executive_service._peer_uid", lambda _socket: os.geteuid() + 2)

    asyncio.run(service._handle_ceo_ingress_connection(reader, writer))

    assert json.loads(writer.writes[0])["error"]["code"] == "peer_denied"
    reader.readuntil.assert_not_called()
    reader.readuntil.assert_not_awaited()


def test_d3_app_458_is_independent_of_c1_and_submit_arms(tmp_path, monkeypatch):
    module = _module()
    # Same pinning as the D8 cases below, plus _off_host. The admitted literal 458
    # carries no topology meaning here -- its real-topology value is pinned against the
    # tracked template in test_d8_template_topology_and_protected_defaults -- it only
    # means "a genuinely distinct uid", so shifting it off a colliding host uid changes
    # nothing this test proves. Only control_uid stays host-derived, as
    # scripts/executive_os_phase1c.py:453 requires.
    app_peer = _off_host(458)
    base = _raw(
        tmp_path,
        worker_uid=_off_host(451),
        allowed_peer_uids=[450, 501],
        ceo_ingress_socket_path=str(tmp_path / "ingress.sock"),
        ceo_ingress_launchd_socket_name="CeoIngress",
        ceo_ingress_peer_uid=_off_host(452),
        ceo_ingress_app_peer_uid=app_peer,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=str(tmp_path / "macro"),
        ceo_submit_armed=False,
    )
    captured: dict[str, object] = {}

    broker = importlib.import_module("control_plane.executive_worker_broker")
    monkeypatch.setattr(broker, "WorkerBrokerClient", lambda *a, **k: object())
    monkeypatch.setattr(module, "activate_launchd_socket", lambda _name: object())

    class FakeService:
        def __init__(self, config, **kwargs):
            captured["config"] = config
            captured.update(kwargs)

    monkeypatch.setattr(module, "ExecutiveControlService", FakeService)
    module._service_from_config(module.load_control_config(_write(tmp_path, base)))
    assert captured["ceo_ingress_armed"] is False
    assert captured["ceo_ingress_app_binding"].peer_uid == app_peer
    assert captured["ceo_ingress_app_binding"].armed is True

    submit_armed = dict(base, ceo_submit_armed=True)
    captured.clear()
    module._service_from_config(module.load_control_config(_write(tmp_path, submit_armed)))
    assert captured["ceo_ingress_armed"] is False
    assert captured["ceo_ingress_app_binding"].peer_uid == app_peer
    assert captured["ceo_ingress_app_binding"].armed is True
    assert captured["config"].ceo_submit_armed is True

    unarmed_app = dict(submit_armed, ceo_ingress_app_armed=False)
    captured.clear()
    module._service_from_config(module.load_control_config(_write(tmp_path, unarmed_app)))
    assert captured["ceo_ingress_armed"] is False
    assert captured["ceo_ingress_app_binding"].peer_uid == app_peer
    assert captured["ceo_ingress_app_binding"].armed is False


def test_d3_strict_v2_uses_host_providers_for_binding_and_dialogue_source(monkeypatch):
    from control_plane import executive_ceo_ingress as ceo_ingress
    from tests.test_executive_ceo_ingress import (
        GROUNDING_A,
        _FakeGrounding,
        _automated_research_request,
        _submit_v2_bytes,
    )

    binding = {
        "provider": "host-codex",
        "provider_home": "/host/provider-home",
        "credential_home": "/host/credentials",
    }
    source = {
        "schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": "WS:EXECUTIVE-OS",
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "c" * 40,
            "path": "docs/commissions/executive-terminal-return.md",
            "content_sha256": "d" * 64,
        },
        "watch_mode": "turn_watch_v1",
    }
    execution_binding_provider = MagicMock(return_value=binding)
    dialogue_source_provider = MagicMock(return_value=source)
    sink = AsyncMock(return_value={"dispatched": False, "job_id": "JOB-HOST"})
    monkeypatch.setattr(ceo_ingress, "_submit", sink)

    class Store:
        def find_event_by_command_id(self, _command_id):
            return None

    class Runtime:
        store = Store()

    frame = json.loads(
        _submit_v2_bytes(
            observed_grounding=GROUNDING_A,
            request=_automated_research_request(workstream="WS:EXECUTIVE-OS"),
        )
    )
    assert "execution_binding" not in frame
    assert "dialogue_source" not in frame

    result = asyncio.run(
        ceo_ingress.handle_frame(
            frame,
            runtime=Runtime(),
            grounding_provider=_FakeGrounding(),
            workspace_root="/host/workspace",
            service_state="READY",
            ceo_ingress_armed=True,
            strict_v2_admission=True,
            execution_binding_provider=execution_binding_provider,
            dialogue_source_provider=dialogue_source_provider,
        )
    )

    assert result["job_id"] == "JOB-HOST"
    execution_binding_provider.assert_called_once_with()
    assert dialogue_source_provider.call_count == 2
    assert sink.await_count == 1
    assert sink.await_args.kwargs["execution_binding"] == binding
    assert sink.await_args.kwargs["dialogue_source"].to_dict() == source


@pytest.mark.parametrize("value", ["true", 1, 0, None])
def test_d4_submit_arm_is_strict_boolean(tmp_path, value):
    module = _module()
    with pytest.raises(module.ServiceError, match="ceo_submit_armed must be boolean"):
        module.load_control_config(_write(tmp_path, _raw(tmp_path, ceo_submit_armed=value)))


def test_d4_unknown_fields_remain_closed(tmp_path):
    module = _module()
    with pytest.raises(module.ServiceError, match="unknown=.*not_admitted"):
        module.load_control_config(_write(tmp_path, _raw(tmp_path, not_admitted=False)))


def test_d5_existing_sink_retains_fingerprint_reconciliation():
    import subprocess
    import sys

    names = (
        "test_committed_changed_fingerprint_yields_operation_conflict",
        "test_concurrent_identical_winner_yields_exactly_one_job_and_duplicate",
        "test_concurrent_conflicting_winner_yields_one_job_and_operation_conflict",
        "test_v2_concurrent_identical_requests_create_one_job_and_same_canonical_receipt",
    )
    for name in names:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_executive_ceo_ingress.py::" + name,
             "-q", "-p", "no:cacheprovider"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_d6_no_new_transport_and_all_arm_defaults_are_false():
    source = PHASE1C.read_text(encoding="utf-8")
    assert 'ceo_submit_armed: bool = False' in (ROOT / "control_plane" / "executive_service.py").read_text(encoding="utf-8")
    assert '"ceo_submit_armed": false' in TEMPLATE.read_text(encoding="utf-8")
    assert 'ceo_submit_armed=raw.get("ceo_submit_armed", False),' in source
    clients = []
    for path in ROOT.rglob("*.py"):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("class CeoIngressClient"):
                clients.append((path.relative_to(ROOT).as_posix(), line_number))
    assert clients == [("integrations/mastermind_executive_app/gateway.py", 353)]
    tree = ast.parse(source)
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) and any(alias.name == "socket" for alias in node.names) for node in tree.body)


def test_d7_diff_and_module_have_no_dispatch_or_provider_import():
    base = subprocess.run(
        ["git", "merge-base", "origin/master", "HEAD"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    source = PHASE1C.read_text(encoding="utf-8")
    added_lines = _added_line_numbers(PHASE1C, base)
    tree = ast.parse(source)
    forbidden_imports = {
        "subprocess", "control_plane.executive_worker_broker", "control_plane.worker_adapter",
        "control_plane.codex_worker", "control_plane.codex_provider_realm",
        "control_plane.executive_supervisor", "urllib", "http", "requests",
    }
    calls = {"Popen", "dispatch", "spawn", "claim_job", "run"}
    for node in ast.walk(tree):
        if getattr(node, "lineno", None) not in added_lines:
            continue
        if isinstance(node, ast.Import):
            assert not any(alias.name in forbidden_imports for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_imports
        elif isinstance(node, ast.Call):
            name = (
                node.func.id if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute)
                else None
            )
            assert name not in calls


@pytest.mark.parametrize("app_uid", [452, 501])
def test_d8_c1_and_worker_uids_are_not_app_peer(tmp_path, app_uid):
    module = _module()
    # Pin every identity the App-peer distinctness rule reads
    # (scripts/executive_os_phase1c.py:387-391) so the 452 and 501 collisions are
    # forced on any host instead of only where os.geteuid() happens to be 501.
    # control_uid is the one identity that cannot be pinned (:453 requires it to
    # equal os.geteuid()), which is safe: it can only ADD a member to that set,
    # never remove the pinned collisions, and the :453 check runs after :388.
    raw = _raw(
        tmp_path,
        worker_uid=451,
        allowed_peer_uids=[450, 501],
        ceo_ingress_socket_path=str(tmp_path / "ingress.sock"),
        ceo_ingress_launchd_socket_name="CeoIngress",
        ceo_ingress_peer_uid=452,
        ceo_ingress_app_peer_uid=app_uid,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=str(tmp_path / "macro"),
    )
    with pytest.raises(module.ServiceError, match="App peer must be distinct"):
        module.load_control_config(_write(tmp_path, raw))


def test_d8_genuinely_distinct_app_peer_uid_is_admitted(tmp_path):
    module = _module()
    # Same pinned identity set as the raising cases, with _off_host keeping the admitted
    # literals off the host uid: 458 is distinct from control/Operator/C1/worker, so the
    # rule must admit it on any host.
    app_peer = _off_host(458)
    raw = _raw(
        tmp_path,
        worker_uid=_off_host(451),
        allowed_peer_uids=[450, 501],
        ceo_ingress_socket_path=str(tmp_path / "ingress.sock"),
        ceo_ingress_launchd_socket_name="CeoIngress",
        ceo_ingress_peer_uid=_off_host(452),
        ceo_ingress_app_peer_uid=app_peer,
        ceo_ingress_app_armed=True,
        ceo_ingress_app_macro_root=str(tmp_path / "macro"),
    )
    loaded = module.load_control_config(_write(tmp_path, raw))
    assert loaded["ceo_ingress_app_peer_uid"] == app_peer


def test_d8_scanner_rejects_hidden_numeric_aliases_across_production_files():
    diff = "\n".join(
        [
            "diff --git a/control_plane/new_identity.py b/control_plane/new_identity.py",
            "--- /dev/null",
            "+++ b/control_plane/new_identity.py",
            "@@ -0,0 +1,5 @@",
            '+worker_uid = config["worker_uid"]',
            "+DIR_MODE = 0o700",
            '+worker_user = "_mastermind_shadow"',
            "+HTTP_WORKER_UID_CODE = 501",
            "+UID_DIR_MODE = 0o765",
            "diff --git a/common/identity_constants.py b/common/identity_constants.py",
            "--- /dev/null",
            "+++ b/common/identity_constants.py",
            "@@ -0,0 +1,4 @@",
            "+FALLBACK = 501",
            "+ALLOWED = (450, 459)",
            "+OCTAL_ALIAS = 0o765",
            "+peer_uid = 777",
        ]
    )
    assert _scan_added_identity_diff(diff) == [
        "_mastermind_shadow", "501", "0o765", "501", "450", "459", "0o765", "777",
    ]


def test_d8_http_exemption_cannot_hide_identity_shaped_aliases():
    diff = "\n".join(
        [
            "diff --git a/common/identity_status.py b/common/identity_status.py",
            "--- /dev/null",
            "+++ b/common/identity_status.py",
            "@@ -0,0 +1,4 @@",
            "+status_uid = 501",
            "+http_peer_uid = 459",
            "+status_peer = 501",
            "+response_peer = 459",
        ]
    )
    assert _scan_added_identity_diff(diff) == ["501", "459", "501", "459"]


def test_d8_scanner_rejects_mastermind_identity_name_in_unrelated_source():
    diff = "\n".join(
        [
            "diff --git a/integrations/service/runtime.mjs b/integrations/service/runtime.mjs",
            "--- /dev/null",
            "+++ b/integrations/service/runtime.mjs",
            "@@ -0,0 +1 @@",
            '+const serviceUser = "_mastermind_shadow";',
        ]
    )
    assert _scan_added_identity_diff(diff) == ["_mastermind_shadow"]

def test_d8_scanner_ignores_unrelated_protocol_modes_and_nonproduction_paths():
    diff = "\n".join(
        [
            "diff --git a/integrations/service/gateway.mjs b/integrations/service/gateway.mjs",
            "--- /dev/null",
            "+++ b/integrations/service/gateway.mjs",
            "@@ -0,0 +1,4 @@",
            "+sendJsonError(res, 404, 'not found');",
            "+const status = Number(err?.statusCode || 500);",
            "+return sendJsonError(res, status >= 400 && status < 600 ? status : 500);",
            "+res.set('Allow', 'POST, DELETE').status(405).json({});",
            "diff --git a/integrations/service/gateway.py b/integrations/service/gateway.py",
            "--- /dev/null",
            "+++ b/integrations/service/gateway.py",
            "@@ -0,0 +1,2 @@",
            "+# control_uid is unrelated to this HTTP adapter",
            "+HTTP_FALLBACK = 503",
            "diff --git a/integrations/service/private_service.py b/integrations/service/private_service.py",
            "--- /dev/null",
            "+++ b/integrations/service/private_service.py",
            "@@ -0,0 +1 @@",
            "+DIR_MODE = 0o700",
            "diff --git a/integrations/service/gateway.test.mjs b/integrations/service/gateway.test.mjs",
            "--- /dev/null",
            "+++ b/integrations/service/gateway.test.mjs",
            "@@ -0,0 +1 @@",
            "+assert.equal(response.status, 503);",
            "diff --git a/integrations/service/README.md b/integrations/service/README.md",
            "--- /dev/null",
            "+++ b/integrations/service/README.md",
            "@@ -0,0 +1 @@",
            "+Private port 443 remains unchanged.",
        ]
    )
    assert _scan_added_identity_diff(diff) == []


def _d8_frozen_added_diff(entries: list[tuple[str, str]]) -> str:
    """Build a zero-context diff from lines frozen from immutable consumer heads."""
    sections = []
    for index, (path, line) in enumerate(entries, 1):
        sections.extend((
            f"diff --git a/{path} b/{path}",
            f"--- a/{path}",
            f"+++ b/{path}",
            f"@@ -0,0 +{index} @@",
            "+" + line,
        ))
    return "\n".join(sections)


def test_d8_actual_pr882_and_pr887_semantic_numbers_are_not_identity():
    # Frozen from the actual diffs at PR #882 head bf9540a3 and PR #887 head
    # 7f51f780. They are consumer regressions, not exemptions in the classifier.
    entries = [
        ("control_plane/mission_workspace.py",
         "    if text in (None, _REDACTED_TEXT) or len(text) > 512:"),
        ("control_plane/mission_workspace.py",
         "    month_lengths = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,"),
        ("app/mastermind_os/src-tauri/tauri.conf.json",
         '{"app":{"windows":[{"width":1200,"height":820,"minWidth":390,"minHeight":600}]}}'),
        ("app/mastermind_os/src/mission.ts",
         "  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);"),
        ("app/mastermind_os/src/mission.ts", "  len = 512;"),
        ("app/mastermind_os/src/mission.ts", "        v.url.length <= 512 &&"),
        ("app/mastermind_os/src/mission.ts", "    v.items.length > 500 ||"),
        ("app/mastermind_os/src/mission.ts", "  if (!raw || raw.length > 640) return null;"),
        ("app/mastermind_os/src/styles.css", "  font-weight: 750;"),
        ("app/mastermind_os/src/styles.css", "  font-weight: 700;"),
        ("app/mastermind_os/src/styles.css", "  border-radius: 999px;"),
        ("app/mastermind_os/src/styles.css", "  max-width: 760px;"),
        ("app/mastermind_os/src/styles.css", "@media (max-width: 800px) {"),
        ("app/mastermind_os/src/styles.css", "@media (max-width: 420px) {"),
    ]
    assert _scan_added_identity_diff(_d8_frozen_added_diff(entries)) == []


def test_d8_true_identity_topology_and_cross_file_aliases_still_fail_closed():
    diff = _d8_frozen_added_diff([
        ("common/runtime_constants.py", "FALLBACK = 501"),
        ("common/runtime_constants.py", "SECONDARY = FALLBACK"),
        ("control_plane/admission.py", "from common.runtime_constants import SECONDARY"),
        ("control_plane/admission.py", "peer_uid = SECONDARY"),
        ("config/service.json", '{"endpointPort": 684}'),
        ("integrations/service/runtime.ts", "const principalId = 777;"),
        ("integrations/service/runtime.ts", 'const accountUser = "_mastermind_shadow";'),
    ])
    assert _scan_added_identity_diff(diff) == [
        "501", "684", "777", "_mastermind_shadow",
    ]


def test_d8_same_spelling_without_an_import_or_dataflow_edge_does_not_taint():
    diff = _d8_frozen_added_diff([
        ("control_plane/admission.py", 'peer_uid = config["peer_uid"]'),
        ("app/mastermind_os/src/mission.ts", "const config = 512;"),
    ])
    assert _scan_added_identity_diff(diff) == []


def test_d8_import_edges_are_qualified_by_their_python_module_source():
    diff = _d8_frozen_added_diff([
        ("common/defaults.py", "FALLBACK = 501"),
        ("control_plane/credentials.py", "from common.defaults import FALLBACK"),
        ("control_plane/credentials.py", "worker_uid = FALLBACK"),
        ("app/constants.py", "FALLBACK = 512"),
    ])
    assert _scan_added_identity_diff(diff) == ["501"]


@pytest.mark.parametrize("import_line", [
    "from common.defaults import FALLBACK  # documented fallback",
    "from common.defaults import FALLBACK as WORKER  # documented fallback",
])
def test_d8_python_import_edges_preserve_valid_inline_comments(import_line):
    local_name = "WORKER" if " as WORKER" in import_line else "FALLBACK"
    diff = _d8_frozen_added_diff([
        ("common/defaults.py", "FALLBACK = 501"),
        ("control_plane/credentials.py", import_line),
        ("control_plane/credentials.py", f"worker_uid = {local_name}"),
        ("app/constants.py", "FALLBACK = 512"),
    ])
    assert _scan_added_identity_diff(diff) == ["501"]


@pytest.mark.parametrize("entries, expected", [
    ([
        ("common/defaults.py", "FALLBACK = 501"),
        ("common/credentials.py", "from .defaults import FALLBACK as WORKER"),
        ("common/credentials.py", "worker_uid = WORKER"),
        ("app/constants.py", "FALLBACK = 512"),
    ], ["501"]),
    ([
        ("integrations/config/defaults.ts", "export const FALLBACK = 459;"),
        ("integrations/config/credentials.ts",
         "import { FALLBACK as WORKER } from './defaults';"),
        ("integrations/config/credentials.ts", "const peerUid = WORKER;"),
        ("app/constants.ts", "const FALLBACK = 512;"),
    ], ["459"]),
])
def test_d8_relative_import_edges_follow_only_the_resolved_source(entries, expected):
    assert _scan_added_identity_diff(_d8_frozen_added_diff(entries)) == expected


def test_d8_identity_context_normalizes_camelcase_and_unicode_names():
    diff = _d8_frozen_added_diff([
        ("config/service.json", '{"allowedPeerUIDs": [459]}'),
        ("config/service.json", '{"peer\uff3fuid": 501}'),
        ("integrations/service/runtime.ts", "const endpointPort = 684;"),
    ])
    assert _scan_added_identity_diff(diff) == ["459", "501", "684"]

def test_d8_template_topology_and_protected_defaults():
    value = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert value["allowed_peer_uids"] == [450, 501]
    assert value["ceo_ingress_peer_uid"] == 452
    assert value["ceo_ingress_app_peer_uid"] == 458
    assert value["ceo_ingress_app_armed"] is False

    base = subprocess.run(
        ["git", "merge-base", "origin/master", "HEAD"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    changed = subprocess.run(
        ["git", "diff", "--diff-filter=ACMRT", "--name-only", "-z", base, "HEAD", "--", ":!tests/"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout
    source_diffs: list[str] = []
    for path in changed.split("\0"):
        if not path:
            continue
        if _identity_guard_evidence_json_path(path):
            document = subprocess.run(
                ["git", "show", f"HEAD:{path}"], cwd=ROOT,
                check=True, capture_output=True, text=True,
            ).stdout
            assert _scan_evidence_identity_literals(document) == [], path
            continue
        if not _identity_guard_source_path(path):
            continue
        diff = subprocess.run(
            ["git", "diff", "--unified=0", base, "HEAD", "--", path], cwd=ROOT,
            check=True, capture_output=True, text=True,
        ).stdout
        source_diffs.append(diff)
    assert _scan_added_identity_diff("\n".join(source_diffs)) == []


@pytest.mark.parametrize("path,guarded", [
    ("docs/runbooks/browser.md", False),
    ("research/browser-study.md", False),
    ("research/evidence/browser-native.json", False),
    ("scripts/new_account.py", True),
    ("control_plane/new_account.py", True),
    ("ops/executive_os/control.json.template", True),
    ("config/new_identity.json", True),
    ("app/new_identity.py", True),
    ("docs/check_identity.py", True),
    ("research/evidence/check_identity.py", True),
    ("research/evidence/install.sh", True),
    ("research/config/identity.json", True),
    ("research/evidence-lookalike/identity.json", True),
    ("other/research/evidence/identity.json", True),
])
def test_d8_identity_guard_scopes_non_runtime_records(path, guarded):
    assert "_identity_guard_source_path" in globals(), "identity guard lacks file-role classification"
    assert _identity_guard_source_path(path) is guarded


def test_d8_identity_literal_positive_controls_remain_complete():
    added = "peer_uid = 777\n_EXTRA_PEER = 459\nFALLBACK = 501\nALLOWED = (450, 459)"
    assert _scan_added_identity_literals(added) == ["777", "459", "501", "450", "459"]


@pytest.mark.parametrize("path,content,rejected", [
    ("docs/runbooks/browser.md", "HTTP 401; input length 936\n", False),
    ("research/evidence/browser.json", '{"char_count":936}\n', False),
    ("scripts/identity.py", "peer_uid = 777\n", True),
    ("config/identity.json", '{"peer_uid":777}\n', True),
    ("ops/executive_os/identity.template", '{"peer_uid":459}\n', True),
    ("docs/identity.py", "FALLBACK = 501\n", True),
    ("research/evidence/identity.py", "ALLOWED = (450, 459)\n", True),
    ("research/evidence/install.sh", "useradd -u 777 _mastermind_fixture\n", True),
])
def test_d8_real_git_diff_distinguishes_evidence_from_identity_changes(
    tmp_path, monkeypatch, path, content, rejected,
):
    # This disposable Git repository is test data, not a company workspace.
    root = tmp_path / "repo"
    root.mkdir()
    template = root / "control.json.template"
    template.write_bytes(TEMPLATE.read_bytes())
    def git(*args):
        return subprocess.run(
            ["git", "-c", "user.name=IdentityGuardFixture",
             "-c", "user.email=fixture@example.invalid", *args],
            cwd=root, check=True, capture_output=True, text=True,
        )
    git("init", "-q")
    git("add", "--", "control.json.template")
    git("commit", "-q", "-m", "fixture baseline")
    git("update-ref", "refs/remotes/origin/master", "HEAD")
    candidate = root / path
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(content)
    git("add", "--", path)
    git("commit", "-q", "-m", "fixture candidate")
    monkeypatch.setitem(globals(), "ROOT", root)
    monkeypatch.setitem(globals(), "TEMPLATE", template)
    if rejected:
        with pytest.raises(AssertionError):
            test_d8_template_topology_and_protected_defaults()
    else:
        test_d8_template_topology_and_protected_defaults()


def _run_d8_evidence_and_loader_fixture(tmp_path, monkeypatch, payload):
    """Exercise the real guard on committed JSON plus a real source consumer."""
    root = tmp_path / "repo"
    root.mkdir()
    template = root / "control.json.template"
    template.write_bytes(TEMPLATE.read_bytes())
    def git(*args):
        return subprocess.run(
            ["git", "-c", "user.name=IdentityGuardFixture",
             "-c", "user.email=fixture@example.invalid", *args],
            cwd=root, check=True, capture_output=True, text=True,
        )
    git("init", "-q")
    git("add", "--", "control.json.template")
    git("commit", "-q", "-m", "fixture baseline")
    git("update-ref", "refs/remotes/origin/master", "HEAD")
    evidence = root / "research/evidence/identity.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(payload, encoding="utf-8")
    source = root / "control_plane/load_identity.py"
    source.parent.mkdir()
    source.write_text("import json\nfrom pathlib import Path\nCONFIG = json.loads(Path('research/evidence/identity.json').read_text())\n")
    git("add", "--", str(evidence.relative_to(root)), str(source.relative_to(root)))
    git("commit", "-q", "-m", "fixture candidate")
    monkeypatch.setitem(globals(), "ROOT", root)
    monkeypatch.setitem(globals(), "TEMPLATE", template)
    test_d8_template_topology_and_protected_defaults()


@pytest.mark.parametrize("payload", [
    '{"peer_uid":459}',
    '{"nested":{"allowed_peer_uids":[450,459]}}',
    '{"worker_gid":"0x1cb"}',
    '{"account":{"id":"459"}}',
    '{"principal":{"name":"_mastermind_shadow"}}',
    '{"allowedPeerUIDs":[459]}',
    '{"peer_uid":459,"peer_uid":null}',
    '{"peer_uid":459} trailing text',
])
def test_d8_evidence_json_cannot_supply_runtime_identity(tmp_path, monkeypatch, payload):
    with pytest.raises(AssertionError):
        _run_d8_evidence_and_loader_fixture(tmp_path, monkeypatch, payload)


def test_d8_benign_evidence_metrics_remain_accepted_with_a_consumer(tmp_path, monkeypatch):
    _run_d8_evidence_and_loader_fixture(
        tmp_path, monkeypatch,
        '{"http_status":401,"char_count":936,"bytes":777,"sha256":"' + "a" * 64 + '"}',
    )


@pytest.mark.parametrize("document", [
    "459", "[459]", '"_mastermind_shadow"',
    '{"char_count":1e10000}',
])
def test_d8_evidence_requires_finite_object_records(document):
    with pytest.raises(AssertionError):
        _scan_evidence_identity_literals(document)


@pytest.mark.parametrize("document", [
    '{"peer_uid":true,"account":null}',
    '{"http_status":401,"char_count":936,"byte_count":777,"hash":"459"}',
    '{"measurements":[{"status":401},{"bytes":936}],"note":"HTTP 401"}',
])
def test_d8_evidence_non_identity_metrics_are_not_uid_literals(document):
    assert _scan_evidence_identity_literals(document) == []


@pytest.mark.parametrize("document", [
    '{"peer_uid":"0459"}', '{"peer_uid":459.0}',
    '{"groups":{"459":"service"}}', '{"worker-user":"_mastermind_shadow"}',
    '{"accountId":459}', '{"effective_uid":501}',
])
def test_d8_evidence_authority_key_and_value_encodings_are_checked(document):
    assert _scan_evidence_identity_literals(document)


@pytest.mark.parametrize("payload", [
    '{"peer_uid":"4.59e2"}',
    '{"peer_uid":"0459.0"}',
    '{"user":" _mastermind_shadow"}',
])
def test_d8_normalized_identity_loader_is_rejected(tmp_path, monkeypatch, payload):
    with pytest.raises(AssertionError):
        _run_d8_evidence_and_loader_fixture(tmp_path, monkeypatch, payload)


@pytest.mark.parametrize("encoded", [
    "4.59e2", "0459.0", " +4.5900E+2 ", "45900e-2", "0x1cb", "0459",
    "4e2", "9.99e2", "４５９.０", "\t_mastermind_shadow\n",
])
def test_d8_normalized_identity_literals_are_detected(encoded):
    assert _scan_evidence_identity_literals(json.dumps({"peer_uid": encoded}))


@pytest.mark.parametrize("encoded", [
    "399.0", "1000.0", "459.1", "459.0000000000000000000000000001",
    "1e999999", "1e-999999", "NaN", "sNaN", "Infinity", "a_service_label",
])
def test_d8_exact_numeric_normalization_preserves_nonidentity_values(encoded):
    assert _scan_evidence_identity_literals(json.dumps({"peer_uid": encoded})) == []


def test_d8_identity_normalization_is_bounded_before_integer_conversion():
    with pytest.raises(AssertionError, match="identity string"):
        _scan_evidence_identity_literals(json.dumps({"peer_uid": "9" * 257}))
    assert _scan_evidence_identity_literals(json.dumps({"hash": "9" * 257})) == []


def test_d8_decimal_context_cannot_round_fraction_into_an_identity():
    from decimal import Inexact, ROUND_UP, localcontext
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        context.traps[Inexact] = True
        assert _scan_evidence_identity_literals('{"peer_uid":"4.59e2"}')
        assert _scan_evidence_identity_literals(
            '{"peer_uid":"459.0000000000000000000000000001"}') == []
