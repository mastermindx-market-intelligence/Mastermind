from __future__ import annotations

import asyncio

import pytest

from integrations.mastermind_secretary_mcp.adapter import (
    GroundingFact,
    GroundingSource,
    SecretaryGroundingGateway,
    StewardGrounding,
)
from integrations.mastermind_secretary_mcp.schemas import (
    SCHEMA_SNAPSHOT_SHA256,
    TOOL_SCHEMA_DIGEST,
)
from integrations.mastermind_secretary_mcp.server import SecretaryGroundingContractServer
from integrations.mastermind_steward_app.research import (
    CITATION_URL_SURFACE_MISSING,
    RESEARCH_SCHEMA_SNAPSHOT_SHA256,
    RESEARCH_TOOL_SCHEMA_DIGEST,
    ResearchError,
    StewardResearchGateway,
    assert_research_contract_integrity,
    research_schema_snapshot_sha256,
    research_tool_schema_digest,
)


SUBJECT = "responsibility:alpha"
WORK_REF = "WS:ALPHA"


def _source(
    owner: str = "agent_os",
    source_ref: str = WORK_REF,
) -> tuple[GroundingSource, ...]:
    return (
        GroundingSource(
            owner=owner,
            source_ref=source_ref,
            observed_at="2026-10-03T06:00:00Z",
        ),
    )


def _fact(
    predicate: str,
    value,
    *,
    freshness: str = "FRESH",
    sources: tuple[GroundingSource, ...] | None = None,
) -> GroundingFact:
    return GroundingFact(
        subject_ref=SUBJECT,
        predicate=predicate,
        value=value,
        freshness=freshness,
        sources=sources or _source(),
    )


def _responsibility_facts(title: str) -> tuple[GroundingFact, ...]:
    return (
        _fact("responsibility.identity", WORK_REF),
        _fact("responsibility.title", title),
        _fact("responsibility.next_action", "Inspect the current exact gate."),
        _fact("responsibility.state", "ACTIVE"),
    )


class _Port:
    def __init__(self, *, title: str = "Terminal capability") -> None:
        self.title = title
        self.calls: list[tuple[str, str | None]] = []

    def _record(self, name: str, subject: str | None = None) -> None:
        self.calls.append((name, subject))

    async def list_responsibilities(self) -> StewardGrounding:
        self._record("list_responsibilities")
        return StewardGrounding(
            state="FACTS",
            facts=_responsibility_facts(self.title),
            reason_codes=(),
        )

    async def get_responsibility(self, responsibility_ref: str) -> StewardGrounding:
        self._record("get_responsibility", responsibility_ref)
        # Current Steward has no authoritative objective. Keep the gap visible.
        return StewardGrounding(
            state="DEGRADED",
            facts=_responsibility_facts(self.title),
            reason_codes=("NO_SOURCE",),
        )

    async def get_attention(self) -> StewardGrounding:
        self._record("get_attention")
        return StewardGrounding(
            state="DEGRADED",
            facts=(
                _fact(
                    "attention.ref",
                    "EXEC:alpha",
                    sources=_source(
                        "executive_inbox",
                        "executive-inbox:alpha",
                    ),
                ),
                _fact(
                    "attention.reason",
                    "Review the bounded decision.",
                    sources=_source(
                        "executive_inbox",
                        "executive-inbox:alpha",
                    ),
                ),
                _fact(
                    "attention.state",
                    "SOL_REQUIRED",
                    sources=_source(
                        "executive_inbox",
                        "executive-inbox:alpha",
                    ),
                ),
            ),
            # Current Steward has no authoritative requested_action.
            reason_codes=("NO_SOURCE",),
        )

    async def get_current_runtime(self, responsibility_ref: str) -> StewardGrounding:
        self._record("get_current_runtime", responsibility_ref)
        return StewardGrounding(
            state="DEGRADED",
            facts=(
                _fact(
                    "runtime.state",
                    "UNKNOWN",
                    freshness="STALE",
                    sources=_source(
                        "executive_os",
                        "executive-runtime:alpha",
                    ),
                ),
                _fact(
                    "runtime.effect_state",
                    "EFFECT_UNKNOWN",
                    freshness="STALE",
                    sources=_source(
                        "executive_os",
                        "executive-runtime:alpha",
                    ),
                ),
            ),
            reason_codes=("EFFECT_UNKNOWN", "RUNTIME_UNKNOWN", "STALE_SOURCE"),
        )

    async def explain_blocker(self, responsibility_ref: str) -> StewardGrounding:
        self._record("explain_blocker", responsibility_ref)
        return StewardGrounding(
            state="FACTS",
            facts=(
                _fact("blocker.present", True),
                _fact("blocker.kind", "citation_surface"),
                _fact(
                    "blocker.explanation",
                    "No authenticated user-openable evidence URL is proven.",
                ),
            ),
            reason_codes=(),
        )

    async def resolve_surface(self, responsibility_ref: str) -> StewardGrounding:
        self._record("resolve_surface", responsibility_ref)
        return StewardGrounding(
            state="DEGRADED",
            facts=(
                _fact(
                    "surface.locator_kind",
                    "UNKNOWN",
                    sources=_source(
                        "surface_bindings",
                        "surface-binding:alpha",
                    ),
                ),
                _fact(
                    "surface.review_state",
                    "UNKNOWN",
                    sources=_source(
                        "surface_bindings",
                        "surface-binding:alpha",
                    ),
                ),
                _fact(
                    "surface.health",
                    "UNKNOWN",
                    sources=_source(
                        "surface_bindings",
                        "surface-binding:alpha",
                    ),
                ),
            ),
            reason_codes=("SURFACE_UNKNOWN",),
        )


def _gateway(port: _Port) -> StewardResearchGateway:
    return StewardResearchGateway(
        SecretaryGroundingContractServer(SecretaryGroundingGateway(port))
    )


def test_research_contract_is_digest_pinned_without_changing_secretary_digests():
    assert SCHEMA_SNAPSHOT_SHA256 == (
        "324afb44a0183987cce4ef48ff7946ca34557071f8ac5c36da96f78a382e8cb1"
    )
    assert TOOL_SCHEMA_DIGEST == (
        "cde13b7d678427a230cfe40159be1d7aa0807df00324995a40d89b2b79c12047"
    )
    assert research_schema_snapshot_sha256() == RESEARCH_SCHEMA_SNAPSHOT_SHA256
    assert research_tool_schema_digest() == RESEARCH_TOOL_SCHEMA_DIGEST
    assert_research_contract_integrity()


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        {},
        {"query": ""},
        {"query": " leading"},
        {"query": "trailing "},
        {"query": "x", "other": "y"},
        {"query": "x" * 513},
        {"query": "safe\u202eevil"},
        {"query": "safe\x00evil"},
        {"query": "\ud800"},
    ],
)
def test_malformed_or_hostile_search_query_fails_before_source_access(arguments):
    port = _Port()
    gateway = _gateway(port)

    with pytest.raises(ResearchError) as caught:
        asyncio.run(gateway.search(arguments))

    assert caught.value.code == "INVALID_REQUEST"
    assert port.calls == []


def test_search_is_deterministic_bounded_and_truthful_about_missing_citation_url():
    port = _Port()
    gateway = _gateway(port)

    first = asyncio.run(gateway.search({"query": "Terminal runtime capability"}))
    second = asyncio.run(gateway.search({"query": "Terminal runtime capability"}))

    assert first == second
    assert first["results"]
    result = first["results"][0]
    assert result["id"].startswith("steward:research:v1:")
    assert result["title"] == "Terminal capability"
    assert result["url"] == ""
    assert port.calls == [
        ("list_responsibilities", None),
        ("list_responsibilities", None),
    ]


def test_stable_document_id_does_not_change_when_title_changes():
    port = _Port(title="Terminal capability")
    gateway = _gateway(port)

    before = asyncio.run(gateway.search({"query": "Terminal capability"}))
    before_id = next(
        row["id"] for row in before["results"] if row["title"] == "Terminal capability"
    )
    port.title = "Terminal capability renamed"
    after = asyncio.run(gateway.search({"query": "Terminal capability renamed"}))
    after_id = next(
        row["id"]
        for row in after["results"]
        if row["title"] == "Terminal capability renamed"
    )

    assert before_id == after_id


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        {},
        {"id": ""},
        {"id": "steward:research:v1:not-a-hash"},
        {"id": "steward:research:v1:" + "0" * 64, "other": "x"},
    ],
)
def test_malformed_fetch_id_fails_before_source_access(arguments):
    port = _Port()
    gateway = _gateway(port)

    with pytest.raises(ResearchError) as caught:
        asyncio.run(gateway.fetch(arguments))

    assert caught.value.code == "INVALID_REQUEST"
    assert port.calls == []


def test_well_formed_unknown_fetch_id_fails_closed_after_catalog_only():
    port = _Port()
    gateway = _gateway(port)

    with pytest.raises(ResearchError) as caught:
        asyncio.run(
            gateway.fetch({"id": "steward:research:v1:" + "0" * 64})
        )

    assert caught.value.code == "DOCUMENT_NOT_FOUND"
    assert port.calls == [("list_responsibilities", None)]


def test_fetch_reconstructs_current_evidence_and_preserves_known_truth_gaps():
    port = _Port()
    gateway = _gateway(port)
    search = asyncio.run(gateway.search({"query": "Terminal capability"}))
    document_id = next(
        row["id"] for row in search["results"] if row["title"] == "Terminal capability"
    )
    port.calls.clear()

    fetched = asyncio.run(gateway.fetch({"id": document_id}))

    assert fetched["id"] == document_id
    assert fetched["title"] == "Terminal capability"
    assert fetched["url"] == ""
    assert fetched["metadata"] == {
        "citation_status": CITATION_URL_SURFACE_MISSING,
        "document_kind": "responsibility",
        "research_generation": 1,
        "secretary_server_version": "2.0.0",
    }
    text = fetched["text"]
    assert "citation_status: CITATION_URL_SURFACE_MISSING" in text
    assert "responsibility" in text
    assert "blocker.present = true" in text
    assert "runtime.effect_state = \"EFFECT_UNKNOWN\"" in text
    assert "freshness=STALE" in text
    assert "SURFACE_UNKNOWN" in text
    assert "NO_SOURCE" in text
    assert "responsibility.objective" not in text
    assert "attention.requested_action" not in text
    assert port.calls == [
        ("list_responsibilities", None),
        ("get_responsibility", SUBJECT),
        ("explain_blocker", SUBJECT),
        ("get_current_runtime", SUBJECT),
        ("resolve_surface", SUBJECT),
        ("get_attention", None),
    ]


def test_attention_document_uses_only_global_attention_read_after_catalog():
    port = _Port()
    gateway = _gateway(port)
    search = asyncio.run(gateway.search({"query": "executive attention"}))
    attention = next(
        row for row in search["results"] if row["title"] == "Mastermind executive attention"
    )
    port.calls.clear()

    fetched = asyncio.run(gateway.fetch({"id": attention["id"]}))

    assert fetched["metadata"]["document_kind"] == "attention"
    assert "## attention" in fetched["text"]
    assert port.calls == [
        ("list_responsibilities", None),
        ("get_attention", None),
    ]


@pytest.mark.parametrize(
    "private_value",
    [
        "Bearer: supersecret",
        "https://private.example.test/evidence",
        "/Users/chriswong/private/evidence",
        "provider=chatgpt",
        "account_id=opaque-account",
    ],
)
def test_private_or_secret_shaped_source_value_is_refused_before_research_output(
    private_value: str,
):
    port = _Port(title=private_value)
    gateway = _gateway(port)

    with pytest.raises(ResearchError) as caught:
        asyncio.run(gateway.search({"query": "Mastermind"}))

    assert caught.value.code == "RESPONSE_REFUSED"
    assert port.calls == [("list_responsibilities", None)]


class _ExplodingPort(_Port):
    async def list_responsibilities(self) -> StewardGrounding:
        self._record("list_responsibilities")
        raise RuntimeError(
            "private exception /Users/chriswong secret-token transcript payload"
        )


def test_source_exception_text_is_never_projected_into_research_error():
    port = _ExplodingPort()
    gateway = _gateway(port)

    with pytest.raises(ResearchError) as caught:
        asyncio.run(gateway.search({"query": "Mastermind"}))

    assert caught.value.code == "RESPONSE_REFUSED"
    assert str(caught.value) == "RESPONSE_REFUSED"
    assert port.calls == [("list_responsibilities", None)]


def test_no_search_or_fetch_method_can_create_a_write_effect():
    port = _Port()
    gateway = _gateway(port)
    search = asyncio.run(gateway.search({"query": "Terminal capability"}))
    document_id = next(
        row["id"] for row in search["results"] if row["title"] == "Terminal capability"
    )
    asyncio.run(gateway.fetch({"id": document_id}))

    assert {name for name, _ in port.calls} <= {
        "list_responsibilities",
        "get_responsibility",
        "get_attention",
        "get_current_runtime",
        "explain_blocker",
        "resolve_surface",
    }
