from __future__ import annotations

import ast
import asyncio
import importlib
import io
import json
import os
import subprocess
import tokenize
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


_NON_PRODUCTION_IDENTITY_DIRS = {
    ".superpowers", "docs", "fixtures", "research", "review_evidence", "tests",
}
_NON_PRODUCTION_IDENTITY_FILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
_PERMISSION_MODE_MARKERS = ("chmod", "umask", "st_mode", "dir_mode", "file_mode", "permission")
_HTTP_STATUS_MARKERS = (
    "sendjsonerror(", "err?.status", "http_fallback", "http_code",
    ".status(", "response.status", "statuscode",
)
_COMMENT_PREFIXES = ("#", "//", "/*", "*/", "* ")


def _is_production_identity_scan_path(path: str) -> bool:
    parts = tuple(part for part in path.split("/") if part)
    if not parts:
        return False
    name = parts[-1]
    if any(part in _NON_PRODUCTION_IDENTITY_DIRS for part in parts):
        return False
    if name.startswith("test_") or name.endswith("_test.py") or ".test." in name:
        return False
    if name in _NON_PRODUCTION_IDENTITY_FILES or name.endswith((".lock", ".md", ".rst")):
        return False
    if name.startswith(("README", "CHANGELOG", "LICENSE")):
        return False
    return True


def _line_mentions_identity_name(line: str) -> bool:
    try:
        for token in tokenize.generate_tokens(io.StringIO(line + "\n").readline):
            if token.type not in {tokenize.NAME, tokenize.STRING}:
                continue
            text = token.string.lower()
            if "_mastermind_" in text:
                return True
            if token.type == tokenize.NAME and (
                {"uid", "uids", "gid", "gids", "peer", "peers"} & set(text.split("_"))
            ):
                return True
    except (IndentationError, tokenize.TokenError):
        pass
    return False


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


def _scan_identity_source_lines(lines: list[str]) -> list[str]:
    flagged: list[str] = []
    for line in lines:
        try:
            tokens = tokenize.generate_tokens(io.StringIO(line + "\n").readline)
            for token in tokens:
                if token.type == tokenize.NUMBER:
                    try:
                        value = int(token.string, 0)
                    except ValueError:
                        continue
                    if 400 <= value <= 999 and not _is_known_non_identity_numeric(
                        line, token.string, value
                    ):
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


def _scan_added_identity_diff(diff: str) -> list[str]:
    """Keep the D8 identity ratchet repo-wide without banning unrelated protocol numbers.

    Added production source still fails on every unexplained 400-999 literal and every
    `_mastermind_*` identity name, including generic aliases moved into a separate file.
    The only numeric exemptions are semantics that are provably outside the topology
    plane on the added line itself: explicit HTTP-status handling and octal permission
    modes. Tests, fixtures, docs/research, and generated dependency locks are not
    production identity authority and are excluded from this source-only discriminator.
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

    flagged: list[str] = []
    for path, lines in additions_by_path.items():
        if not _is_production_identity_scan_path(path):
            continue
        flagged.extend(_scan_identity_source_lines(lines))
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
    assert clients == [("integrations/mastermind_executive_app/gateway.py", 321)]
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
    diff = subprocess.run(
        ["git", "diff", "--unified=0", base, "HEAD", "--", ":!tests/"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout
    assert _scan_added_identity_diff(diff) == []
