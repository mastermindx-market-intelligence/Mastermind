from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from control_plane import ceo_intent, ceo_request
from control_plane.executive_runtime import Runtime
from control_plane.executive_service import ExecutiveControlService
from integrations.mastermind_executive_app.web_commission_source import (
    CANONICAL_REPOSITORY,
    COMMISSION_PATH,
    GitHubWebCommissionSourceProvider,
    WebCommissionSourceError,
)
from tests.test_executive_service import _FakeSupervisor, _config, _coo_intent


def _identity(operation_key: str) -> str:
    return ceo_request.automated_intent_id(ceo_request.app_request_ref(operation_key))


def test_provider_resolves_exact_operation_branch_without_workstream_lookup() -> None:
    operation_key = "delegate-research-001"
    intent_id = _identity(operation_key)
    commit = "a" * 40
    content = b"# Complete worker brief\n\nUse the immutable acceptance contract.\n"
    fetches: list[str] = []
    provider = GitHubWebCommissionSourceProvider(
        list_refs=lambda: (
            ("b" * 40, "refs/heads/sol/web-unrelated-operation-001"),
            (commit, f"refs/heads/sol/web-{operation_key}"),
            ("c" * 40, "refs/heads/sol/web-NOT-PUBLIC-OPERATION"),
        ),
        fetch_blob=lambda *, commit: fetches.append(commit) or content,
    )

    source = provider(intent_id, "WS:CEO-DELEGATION")

    assert source == {
        "schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": "WS:CEO-DELEGATION",
        "commission_ref": {
            "repository": CANONICAL_REPOSITORY,
            "commit": commit,
            "path": COMMISSION_PATH,
            "content_sha256": hashlib.sha256(content).hexdigest(),
        },
        "watch_mode": None,
    }
    assert fetches == [commit]


def test_provider_returns_absent_without_fetch_when_no_exact_identity_matches() -> None:
    fetched = False

    def fetch_blob(*, commit: str) -> bytes:
        nonlocal fetched
        fetched = True
        return b"unexpected"

    provider = GitHubWebCommissionSourceProvider(
        list_refs=lambda: (("a" * 40, "refs/heads/sol/web-other-operation-001"),),
        fetch_blob=fetch_blob,
    )

    assert provider(_identity("wanted-operation-001"), "WS:CEO-DELEGATION") is None
    assert fetched is False


def test_provider_refuses_ambiguous_exact_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    target = "auto-" + "1" * 32
    monkeypatch.setattr(ceo_request, "app_request_ref", lambda _operation: "req-x12345678")
    monkeypatch.setattr(ceo_request, "automated_intent_id", lambda _request: target)
    provider = GitHubWebCommissionSourceProvider(
        list_refs=lambda: (
            ("a" * 40, "refs/heads/sol/web-operation-one"),
            ("b" * 40, "refs/heads/sol/web-operation-two"),
        ),
        fetch_blob=lambda **_kwargs: b"never",
    )

    with pytest.raises(WebCommissionSourceError, match="multiple Web commission branches"):
        provider(target, "WS:CEO-DELEGATION")


def test_provider_is_a_real_strict_v2_admission_consumer(tmp_path: Path) -> None:
    config = _config(tmp_path)
    runtime = Runtime.at(config.runtime_root)
    operation_key = "web-commission-admission-001"
    intent_id = _identity(operation_key)
    commit = "d" * 40
    content = b"# CEO commission\n\nDelegate this bounded program.\n"
    observations = 0

    def refs():
        nonlocal observations
        observations += 1
        return ((commit, f"refs/heads/sol/web-{operation_key}"),)

    provider = GitHubWebCommissionSourceProvider(
        list_refs=refs,
        fetch_blob=lambda *, commit: content,
    )
    service = ExecutiveControlService(
        config,
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        ceo_ingress_dialogue_source_provider=provider,
    )
    service.runtime = runtime
    intent = _coo_intent(config, "web-commission-source")
    intent["intent_id"] = intent_id
    intent["workstream"] = "WS:CEO-DELEGATION"

    receipt = service._submit_service_intent(intent)

    event = runtime.store.find_event_by_command_id(ceo_intent.command_id_for(intent_id))
    assert event is not None
    source = event["payload"]["provenance"]["dialogue_source"]
    assert source["commission_ref"]["commit"] == commit
    assert source["commission_ref"]["content_sha256"] == hashlib.sha256(content).hexdigest()
    assert source["work_ref"] == "WS:CEO-DELEGATION"
    assert receipt["job_id"]
    assert observations == 2, "trusted source must be re-observed before first root mutation"


def test_branch_movement_between_reobservations_refuses_zero_job(tmp_path: Path) -> None:
    config = _config(tmp_path)
    runtime = Runtime.at(config.runtime_root)
    operation_key = "web-commission-drift-001"
    intent_id = _identity(operation_key)
    heads = iter(("a" * 40, "b" * 40))
    provider = GitHubWebCommissionSourceProvider(
        list_refs=lambda: ((next(heads), f"refs/heads/sol/web-{operation_key}"),),
        fetch_blob=lambda *, commit: f"# commission {commit}\n".encode(),
    )
    service = ExecutiveControlService(
        config,
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        ceo_ingress_dialogue_source_provider=provider,
    )
    service.runtime = runtime
    intent = _coo_intent(config, "web-commission-drift")
    intent["intent_id"] = intent_id
    intent["workstream"] = "WS:CEO-DELEGATION"

    with pytest.raises(ceo_intent.CeoIntentConflict, match="changed"):
        service._submit_service_intent(intent)

    assert runtime.jobs.list_jobs() == []
    assert runtime.store.find_event_by_command_id(
        ceo_intent.command_id_for(intent_id)
    ) is None


def test_public_app_request_ref_resolves_same_web_branch_into_strict_v2_root(
    tmp_path: Path,
) -> None:
    from control_plane import executive_ceo_ingress as ceo_ingress

    config = _config(tmp_path)
    runtime = Runtime.at(config.runtime_root)
    operation_key = "web-commission-app-roundtrip-001"
    request_ref = ceo_request.app_request_ref(operation_key)
    intent_id = ceo_request.automated_intent_id(request_ref)
    commit = "e" * 40
    content = b"# App-origin commission\n\nExact source-free public round trip.\n"
    provider = GitHubWebCommissionSourceProvider(
        list_refs=lambda: ((commit, f"refs/heads/sol/web-{operation_key}"),),
        fetch_blob=lambda *, commit: content,
    )
    service = ExecutiveControlService(
        config,
        supervisor_factory=lambda opened: _FakeSupervisor(opened),
        ceo_ingress_dialogue_source_provider=provider,
    )
    service.runtime = runtime
    grounding = {
        "mastermind_sha": config.proof_base_sha,
        "macro_sha": "b" * 40,
        "boot_packet_schema": ceo_ingress.BOOT_PACKET_SCHEMA,
    }

    class GroundingProvider:
        def observe(self):
            return dict(grounding)

    frame = {
        "schema": ceo_ingress.SUBMIT_SCHEMA_V2,
        "request_ref": request_ref,
        "observed_grounding": grounding,
        "request": {
            "objective": "Execute the compact Web CEO request from its immutable commission.",
            "department": "executive-infrastructure",
            "priority": 9,
            "execution_profile": "research_only",
            "workstream": "WS:CEO-DELEGATION",
            "attempt_limit": 2,
        },
    }
    assert "operation_key" not in frame["request"]
    assert "dialogue_source" not in frame and "commission_ref" not in frame["request"]

    receipt = __import__("asyncio").run(
        ceo_ingress.handle_frame(
            frame,
            runtime=runtime,
            grounding_provider=GroundingProvider(),
            workspace_root=config.proof_workspace_root,
            service_state="READY",
            ceo_ingress_armed=True,
            strict_v2_admission=True,
            execution_binding_provider=service._require_current_coo_binding,
            dialogue_source_provider=provider,
        )
    )

    assert receipt["intent_id"] == intent_id
    event = runtime.store.find_event_by_command_id(ceo_intent.command_id_for(intent_id))
    assert event is not None
    source = event["payload"]["provenance"]["dialogue_source"]
    assert source["commission_ref"] == {
        "repository": CANONICAL_REPOSITORY,
        "commit": commit,
        "path": COMMISSION_PATH,
        "content_sha256": hashlib.sha256(content).hexdigest(),
    }


def test_remote_ref_observation_is_fixed_noninteractive_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import integrations.mastermind_executive_app.web_commission_source as source_mod

    operation_key = "bounded-remote-observation-001"
    head = "f" * 40
    observed: dict[str, object] = {}

    class Proc:
        returncode = 0
        stdout = f"{head}\trefs/heads/sol/web-{operation_key}\n".encode()
        stderr = b""

    def run(argv, **kwargs):
        observed["argv"] = list(argv)
        observed["kwargs"] = kwargs
        return Proc()

    monkeypatch.setattr(source_mod.subprocess, "run", run)

    assert source_mod.list_web_branch_refs() == (
        (head, f"refs/heads/sol/web-{operation_key}"),
    )
    assert observed["argv"] == [
        "/usr/bin/git",
        "ls-remote",
        "--heads",
        "https://github.com/mastermindx-market-intelligence/Mastermind.git",
        "refs/heads/sol/web-*",
    ]
    kwargs = observed["kwargs"]
    assert kwargs["timeout"] == 10.0
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["env"]["GIT_ASKPASS"] == "/usr/bin/false"
    assert kwargs["env"]["GIT_CONFIG_GLOBAL"] == "/dev/null"


def test_fixed_blob_fetch_cannot_escape_canonical_raw_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import integrations.mastermind_executive_app.web_commission_source as source_mod

    commit = "a" * 40
    content = b"# exact web commission\n"

    class Response:
        headers = {"Content-Length": str(len(content))}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return (
                "https://raw.githubusercontent.com/"
                "mastermindx-market-intelligence/Mastermind/"
                f"{commit}/research/executive_commissions/COMMISSION.md"
            )

        def read(self, limit):
            assert limit == (1 << 19) + 1
            return content

    class Opener:
        def open(self, request, *, timeout):
            assert timeout == 10.0
            assert request.full_url == (
                "https://raw.githubusercontent.com/"
                "mastermindx-market-intelligence/Mastermind/"
                f"{commit}/research/executive_commissions/COMMISSION.md"
            )
            assert request.get_header("User-agent") == "Mastermind-Web-Commission-Source/1"
            return Response()

    monkeypatch.setattr(source_mod.urllib.request, "build_opener", lambda *_: Opener())
    assert source_mod.fetch_commission_blob(commit=commit) == content


@pytest.mark.parametrize(
    "content",
    [b"", b"bad\x00commission", b"bad-utf8-\xff", b"x" * ((1 << 19) + 1)],
)
def test_provider_refuses_noncanonical_commission_bytes(content: bytes) -> None:
    operation_key = "invalid-commission-bytes-001"
    provider = GitHubWebCommissionSourceProvider(
        list_refs=lambda: (("a" * 40, f"refs/heads/sol/web-{operation_key}"),),
        fetch_blob=lambda **_kwargs: content,
    )

    with pytest.raises(WebCommissionSourceError):
        provider(_identity(operation_key), "WS:CEO-DELEGATION")
