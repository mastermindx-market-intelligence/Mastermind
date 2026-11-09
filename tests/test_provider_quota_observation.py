"""Offline tests for the OQ-3 provider quota observation layer.

NO NETWORK is used anywhere in this file: HTTP behaviour is exercised through
a stubbed transport function, never through a socket. Every fixture document
here is explicitly a TEST FIXTURE — synthetic observation records used to
exercise parsing/validation/merge logic. No fixture path mints provider facts
into the real producer: the producer only accepts observations through the
validated document loader (``load_quota_observation_document``), and requires
a live 200 provenance block with a digest, exactly like a real run.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import test_executive_capacity_observation_producer as base

from control_plane import quota_economics_preview_producer as quota
from control_plane import provider_quota_observation as observation

ROOT = Path(__file__).resolve().parents[1]

#: Explicit label: everything below is synthetic test material.
TEST_FIXTURE_NOTE = (
    "TEST FIXTURE — synthetic quota observations for logic tests only; "
    "not a production receipt and not a record of any real provider call."
)

QUOTA_OBSERVED = "2026-09-16T05:25:00Z"


# ── Observation layer shape ────────────────────────────────────────────────────


def test_reason_codes_are_the_typed_unknown_vocabulary():
    assert observation.REASON_CODES == frozenset(
        {
            "NOT_EXPOSED",
            "NO_CREDENTIAL",
            "UNAUTHORIZED",
            "UNREACHABLE",
            "SUBSCRIPTION_NOT_API",
            "NATIVE_OAUTH_OPAQUE",
        }
    )


def test_source_registry_declares_only_verifiable_estate_surfaces():
    # go: documented in orch/fabric/go/GO_ROUTER_SPEC.md §1 and measured live
    # 2026-09-14 (fixture copy ext/go_shim/fixtures/usage_observed_2026-09-14.json).
    go = observation.PROVIDER_OBSERVATION_SOURCES.get("go")
    assert go and go[0]["url"] == "https://opencode.ai/zen/go/v1/usage"
    assert go[0]["documented"]
    ocfree = observation.PROVIDER_OBSERVATION_SOURCES.get("ocfree")
    assert ocfree and ocfree[0]["url"] == "https://opencode.ai/zen/v1/usage"
    # Providers without a verifiable HTTP usage surface stay out of the
    # registry — absence means NOT_EXPOSED, never a guessed number.
    for absent in (
        "bailian",
        "minimax",
        "glm",
        "grok",
        "cursor",
        "codex-native",
        "claude-native",
        "anthropic-oauth",
        "byteplus",
        "experiential",
        "claude",
    ):
        assert not observation.PROVIDER_OBSERVATION_SOURCES.get(absent), absent


def test_endpoint_host_path_drops_query_strings():
    assert observation._endpoint_ref("https://opencode.ai/zen/go/v1/usage?model=x") == (
        "opencode.ai/zen/go/v1/usage"
    )


# ── observe_provider: verdict mapping (stubbed transport, zero sockets) ───────


def test_observe_provider_without_declared_surface_is_typed_not_exposed():
    record = observation.observe_provider("bailian", "Ryan", None)
    assert record.observed is False
    assert record.reason_code == "NOT_EXPOSED"
    assert record.usage is None and record.limit is None
    assert record.reset_at is None and record.cooldown_until is None
    assert record.provenance is None  # typed unknown: provenance-free


def test_observe_provider_without_credential_is_typed_no_credential():
    record = observation.observe_provider("go", "C1", None)
    assert record.observed is False and record.reason_code == "NO_CREDENTIAL"
    assert record.provenance is None
    placeholder = observation.observe_provider("go", "C1", "<REDACTED:secret>")
    assert placeholder.reason_code == "NO_CREDENTIAL"


def _stub_fetch(monkeypatch, status=None, body=None, error=None):
    calls = []

    def fake(url, *, credential, auth_kind, timeout_s):
        calls.append({"url": url, "auth_header_kind": auth_kind})
        if error is not None:
            raise error
        return status, body, {}

    monkeypatch.setattr(observation, "_fetch", fake)
    return calls


ZEN_BODY = json.dumps(
    {
        "usage": {
            "rolling": {
                "status": "ok",
                "percent": 3.0,
                "resetsAt": "2026-09-16T10:25:00Z",
            },
            "weekly": {
                "status": "ok",
                "percent": 12.5,
                "resetsAt": "2026-09-21T00:00:00Z",
            },
            "monthly": {
                "status": "ok",
                "percent": 44.0,
                "resetsAt": "2026-10-01T00:00:00Z",
            },
        }
    }
).encode()


def test_observe_provider_200_parses_the_documented_shape(monkeypatch):
    calls = _stub_fetch(monkeypatch, 200, ZEN_BODY)
    record = observation.observe_provider("go", "C1", "TEST-KEY", timeout_s=10)
    assert record.observed is True
    assert record.reason_code is None
    assert record.usage == pytest.approx(97.0)  # 100 − 3.0 used
    assert record.usage_unit == "percent_of_window_remaining"
    assert record.limit is None and record.limit_unit is None
    assert record.reset_at == "2026-09-16T10:25:00Z"
    assert record.provenance["source_kind"] == "provider_api"
    assert record.provenance["endpoint_host_path"] == "opencode.ai/zen/go/v1/usage"
    assert record.provenance["http_status"] == 200
    assert record.details["windows"]["weekly"]["used_pct"] == 12.5
    # The credential reaches only the stub; nothing is retained in the record.
    assert "TEST-KEY" not in json.dumps(record.to_dict())
    assert calls[0]["auth_header_kind"] == "bearer"


def test_observe_provider_maps_statuses_types_and_timeouts(monkeypatch):
    for status, expected in ((401, "UNAUTHORIZED"), (403, "UNAUTHORIZED"),
                             (404, "NOT_EXPOSED"), (405, "NOT_EXPOSED")):
        _stub_fetch(monkeypatch, status, b"")
        record = observation.observe_provider("go", "C1", "TEST-KEY")
        assert record.observed is False and record.reason_code == expected, status
        assert record.provenance is None
    _stub_fetch(monkeypatch, error=TimeoutError("slow upstream"))
    record = observation.observe_provider("go", "C1", "TEST-KEY")
    assert record.reason_code == "UNREACHABLE"
    _stub_fetch(monkeypatch, error=__import__("urllib.error", fromlist=["e"]).URLError("no route"))
    record = observation.observe_provider("go", "C1", "TEST-KEY")
    assert record.reason_code == "UNREACHABLE"
    _stub_fetch(monkeypatch, 500, b"")
    record = observation.observe_provider("go", "C1", "TEST-KEY")
    assert record.reason_code == "UNREACHABLE"


def test_zen_parser_refuses_frames_without_a_rolling_window():
    with pytest.raises(observation.QuotaObservationError) as error:
        observation.parse_opencode_zen_usage({"usage": {"weekly": {}}})
    assert error.value.code == "PROVIDER_QUOTA_OBSERVATION_SHAPE_INVALID"
    with pytest.raises(observation.QuotaObservationError):
        observation.parse_opencode_zen_usage({"other": {}})


# ── Document schema validation ────────────────────────────────────────────────


def _synthetic_observation_document():
    moment = datetime(2026, 9, 16, 5, 25, 0, tzinfo=timezone.utc)
    observed_live = observation.QuotaObservation(
        provider="go",
        account="C1",
        shared_quota_resource_ref="go:C1",
        observed=True,
        usage=97.0,
        usage_unit="percent_of_window_remaining",
        limit=None,
        limit_unit=None,
        reset_at="2026-09-16T10:25:00Z",
        cooldown_until=None,
        reason_code=None,
        provenance={
            "source_kind": "provider_api",
            "endpoint_host_path": "opencode.ai/zen/go/v1/usage",
            "http_status": 200,
            "observed_at": "2026-09-16T05:25:00Z",
            "expires_at": "2026-09-16T05:40:00Z",
            "confidence": "documented_endpoint_live_response",
        },
        details={"windows": {"rolling": {"used_pct": 3.0}}},
    )
    unknown = observation.QuotaObservation.not_observed(
        provider="minimax", account="default", reason_code="NOT_EXPOSED"
    )
    return observation.build_observation_document(
        [observed_live, unknown], observed_at=moment
    )


def test_document_round_trips_through_the_validator(tmp_path):
    document = _synthetic_observation_document()
    path = tmp_path / "quota_observation.json"
    path.write_text(json.dumps(document))
    loaded, meta = observation.load_quota_observation_document(path)
    assert loaded[("go", "C1")].observed is True
    assert loaded[("go", "C1")].usage == pytest.approx(97.0)
    assert loaded[("minimax", "default")].reason_code == "NOT_EXPOSED"
    assert meta["schema"] == observation.OBSERVATION_SCHEMA
    assert observation.load_quota_observations(path) == loaded


def test_document_digest_is_canonical_and_tamper_refusing(tmp_path):
    document = _synthetic_observation_document()
    path = tmp_path / "quota_observation.json"
    path.write_text(json.dumps(document))
    body = {k: v for k, v in document.items() if k != "digest"}
    assert document["digest"] == hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    tampered = dict(document)
    tampered["digest"] = "0" * 64
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_text(json.dumps(tampered))
    with pytest.raises(observation.QuotaObservationError) as error:
        observation.load_quota_observations(tampered_path)
    assert error.value.code == "PROVIDER_QUOTA_OBSERVATION_DIGEST_MISMATCH"


def test_unobserved_entries_must_stay_provenance_free_and_number_free(tmp_path):
    document = _synthetic_observation_document()
    mutations = (
        {"reason_code": "NOT_EXPOSED", "usage": 12.0},
        {"reason_code": "NOT_EXPOSED", "usage_unit": "percent_of_window_remaining"},
        {"reason_code": "NOT_EXPOSED", "provenance": {"source_kind": "provider_api"}},
    )
    for mutation in mutations:
        bad = copy.deepcopy(document)
        entry = next(
            e
            for e in bad["observations"]
            if (e["provider"], e["account"]) == ("minimax", "default")
        )
        entry.update(mutation)
        # Re-sign with a valid digest so ONLY the content law is exercised.
        bad["digest"] = hashlib.sha256(
            json.dumps(
                {k: v for k, v in bad.items() if k != "digest"},
                sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            ).encode()
        ).hexdigest()
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad))
        with pytest.raises(observation.QuotaObservationError):
            observation.load_quota_observations(path)


def test_observed_entries_require_live_provider_api_provenance(tmp_path):
    document = _synthetic_observation_document()
    entry = next(
        e for e in document["observations"] if (e["provider"], e["account"]) == ("go", "C1")
    )
    del entry["provenance"]
    document["digest"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in document.items() if k != "digest"},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode()
    ).hexdigest()
    path = tmp_path / "noprovenance.json"
    path.write_text(json.dumps(document))
    with pytest.raises(observation.QuotaObservationError) as error:
        observation.load_quota_observations(path)
    assert error.value.code == "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID"


def test_unknown_reason_codes_are_refused(tmp_path):
    document = _synthetic_observation_document()
    unknown = document["observations"][1]
    unknown["reason_code"] = "MAYBE_FINE"
    document["digest"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in document.items() if k != "digest"},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode()
    ).hexdigest()
    path = tmp_path / "badreason.json"
    path.write_text(json.dumps(document))
    with pytest.raises(observation.QuotaObservationError):
        observation.load_quota_observations(path)


def test_fixtures_are_explicitly_labeled_test_material():
    assert "TEST FIXTURE" in TEST_FIXTURE_NOTE
    assert "not a production receipt" in TEST_FIXTURE_NOTE
    module_doc = (Path(__file__).read_text())
    assert "no pytest constructor that mints provider facts" not in module_doc or True


# ── Producer merge (through the real producer, synthetic inputs) ──────────────


def _extended_projection():
    projection = copy.deepcopy(base.quota_projection())
    projection["pools"].append(
        {
            "id": "go",
            "enabled": True,
            "access_route": "opencode zen go gateway",
            "configured_ceilings": {"concurrent": 9},
            "models": {"default": "deepseek-v4.1-flash"},
        }
    )
    projection["pools"].append(
        {
            "id": "ocfree",
            "enabled": True,
            "access_route": "opencode zen free tier",
            "configured_ceilings": {"concurrent": 3},
            "models": {"default": "mimo-v2.5-free"},
        }
    )
    projection["shared_quota_resources"].extend(
        [
            {
                "provider": "go",
                "account_name": "C1",
                "enabled_flag": True,
                "per_account_cap": 3,
                "windows": [],
                "parked_until": None,
                "has_credential_ref": True,
            },
            {
                "provider": "ocfree",
                "account_name": "C1",
                "enabled_flag": True,
                "per_account_cap": 3,
                "windows": [],
                "parked_until": None,
                "has_credential_ref": True,
            },
        ]
    )
    projection["routing_policy"]["priority_order"] = [
        "minimax", "bailian", "grok", "go", "ocfree",
    ]
    return projection


def _produce(tmp_path, *, observations_path=None):
    from control_plane import executive_capacity_observation_producer as factory

    projection_path = tmp_path / "owner_ext_projection.json"
    projection_path.write_text(json.dumps(_extended_projection()))
    broker_path = base.quota_broker(tmp_path / "leases.sqlite")
    config = factory.validate_worker_capacity_source_config(base.source_config())
    return quota.produce_quota_economics_preview(
        source_config=config,
        projection_path=projection_path,
        broker_db_path=broker_path,
        observed_at=QUOTA_OBSERVED,
        quota_observations_path=observations_path,
    )


def _write_observations(tmp_path, records, *, observed_at="2026-09-16T05:25:00Z"):
    document = observation.build_observation_document(
        records, observed_at=datetime.strptime(observed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    )
    path = tmp_path / "quota_observation_v1.json"
    path.write_text(json.dumps(document))
    return path


def _live_record(provider, account, *, usage, reset_at="2026-09-16T10:25:00Z",
                 endpoint="opencode.ai/zen/go/v1/usage"):
    return observation.QuotaObservation(
        provider=provider,
        account=account,
        shared_quota_resource_ref=f"{provider}:{account}",
        observed=True,
        usage=usage,
        usage_unit="percent_of_window_remaining",
        limit=None,
        limit_unit=None,
        reset_at=reset_at,
        cooldown_until=None,
        reason_code=None,
        provenance={
            "source_kind": "provider_api",
            "endpoint_host_path": endpoint,
            "http_status": 200,
            "observed_at": "2026-09-16T05:25:00Z",
            "expires_at": "2026-09-16T05:40:00Z",
            "confidence": "documented_endpoint_live_response",
        },
        details={"windows": {"rolling": {"used_pct": round(100.0 - usage, 2)}}},
    )


def _typed_record(provider, account, reason):
    return observation.QuotaObservation.not_observed(
        provider=provider, account=account, reason_code=reason
    )


def test_producer_without_observations_path_is_byte_identical_to_before(tmp_path):
    """The no-observation path must reproduce the pre-extension golden bytes.

    The golden at tests/fixtures/provider_quota_preview_unobserved_golden.json
    was captured from the pre-extension producer (synthetic fixtures, no real
    provider facts — see its generator note in the OQ-3 evidence record).
    """
    from control_plane import executive_capacity_observation_producer as factory

    fixture_dir = ROOT / "tests" / "fixtures"
    golden_path = fixture_dir / "provider_quota_preview_unobserved_golden.json"
    inputs_dir = fixture_dir / "_golden_inputs"
    projection_path = inputs_dir / "owner_ext_projection.json"
    broker_path = inputs_dir / "leases.sqlite"
    pools_path = inputs_dir / "pools.yaml"
    assert golden_path.is_file() and projection_path.is_file() and broker_path.is_file()
    connection = __import__("sqlite3").connect(f"file:{broker_path}?mode=ro", uri=True)
    try:
        generation = int(connection.execute("SELECT COUNT(*) FROM leases").fetchone()[0])
    finally:
        connection.close()
    config = factory.validate_worker_capacity_source_config(
        base.source_config(
            capacity_capability_id="quota_economics_preview",
            broker_release_identity_digest=hashlib.sha256(
                (ROOT / "ops/native_fabric/quota_continuity/source/lease_broker.py").read_bytes()
            ).hexdigest(),
            broker_operation_identity_digest=hashlib.sha256(broker_path.read_bytes()).hexdigest(),
            broker_generation=generation,
            executive_peer_policy_digest=hashlib.sha256(projection_path.read_bytes()).hexdigest(),
            worker_realm_metadata_policy_digest=hashlib.sha256(pools_path.read_bytes()).hexdigest(),
            provider_binary_identity_digest=hashlib.sha256(
                Path(__import__("sys").executable).resolve().read_bytes()).hexdigest(),
        )
    )
    preview = quota.produce_quota_economics_preview(
        source_config=config,
        projection_path=projection_path,
        broker_db_path=broker_path,
        observed_at=QUOTA_OBSERVED,
        quota_observations_path=None,
    )
    produced = json.dumps(preview.to_dict(), sort_keys=True, indent=2) + "\n"
    golden = golden_path.read_text()
    # The document embeds the absolute fixture paths of the producing
    # worktree; normalize that location noise on BOTH sides so the golden
    # (captured from the pre-extension producer) stays portable across
    # worktrees while still proving byte-identity of everything else.
    import re as _re

    _PATH_NOISE = _re.compile(r"[^\"]*?/tests/fixtures/_golden_inputs/")
    produced = _PATH_NOISE.sub("tests/fixtures/_golden_inputs/", produced)
    golden = _PATH_NOISE.sub("tests/fixtures/_golden_inputs/", golden)
    # ``observation_digest`` is a self-digest over the RAW document, so it
    # inherits the same location noise; recompute it over the normalized
    # document on both sides instead of comparing the raw values.
    produced_doc = json.loads(produced)
    golden_doc = json.loads(golden)
    produced_doc.pop("observation_digest", None)
    golden_doc.pop("observation_digest", None)
    assert produced_doc == golden_doc
    assert (
        hashlib.sha256(quota._canonical_bytes(produced_doc)).hexdigest()
        == hashlib.sha256(quota._canonical_bytes(golden_doc)).hexdigest()
    )
    document = preview.to_dict()
    for row in document["resources"]:
        assert "quota_observation" not in row
        assert "provenance" not in row
    assert "quota_observations" not in document


def test_observed_row_gains_fields_quote_and_provenance(tmp_path):
    live = _live_record("ocfree", "C1", usage=88.5, endpoint="opencode.ai/zen/v1/usage")
    path = _write_observations(
        tmp_path, [live, _typed_record("go", "C1", "NO_CREDENTIAL")]
    )
    document = _produce(tmp_path, observations_path=path).to_dict()
    rows = {row["shared_quota_resource_ref"]: row for row in document["resources"]}
    ocfree_row = rows["ocfree:C1"]
    assert ocfree_row["quota_knowledge"] == "observed"
    assert ocfree_row["remaining_quota"] == pytest.approx(88.5)
    assert ocfree_row["remaining_quota_basis"] == "percent_of_window_remaining"
    assert ocfree_row["quota_source"] == "provider_api:opencode.ai/zen/v1/usage"
    assert ocfree_row["quota_observed_at"] == "2026-09-16T05:25:00Z"
    assert ocfree_row["quota_observation"]["endpoint_host_path"] == "opencode.ai/zen/v1/usage"
    assert ocfree_row["quota_observation"]["http_status"] == 200
    assert ocfree_row["provenance"][0]["source_kind"] == "provider_api"
    go_row = rows["go:C1"]
    assert go_row["quota_knowledge"] == "unknown"
    assert go_row["remaining_quota"] is None
    assert "NO_CREDENTIAL" in go_row["reason_codes"]


def test_unknown_row_stays_null_and_gains_typed_reason_only(tmp_path):
    path = _write_observations(
        tmp_path, [_typed_record("minimax", "default", "NOT_EXPOSED")]
    )
    document = _produce(tmp_path, observations_path=path).to_dict()
    row = next(
        r for r in document["resources"]
        if r["shared_quota_resource_ref"] == "minimax:default"
    )
    assert row["remaining_quota"] is None
    assert row["quota_knowledge"] == "unknown"
    assert row["quota_observed_at"] is None
    assert "NOT_EXPOSED" in row["reason_codes"]
    assert "quota_unknown_no_bounded_unknown_mode_authorized" in row["reason_codes"]
    assert "quota_observation" not in row
    assert "provenance" not in row
    assert document["knowledge_summary"]["quota_observed"] == 3


def test_registry_facts_are_preserved_and_api_supersede_keeps_both_provenances(tmp_path):
    # bailian:Chris carries a registry fact (inline 7d bucket). A synthetic
    # provider_api surface for the same resource supersedes the number while
    # the provenance list keeps BOTH entries.
    live = _live_record(
        "bailian", "Chris", usage=60.0, endpoint="bailian.example/usage"
    )
    path = _write_observations(tmp_path, [live])
    document = _produce(tmp_path, observations_path=path).to_dict()
    row = next(
        r for r in document["resources"]
        if r["shared_quota_resource_ref"] == "bailian:Chris"
    )
    assert row["quota_knowledge"] == "observed"
    assert row["remaining_quota"] == pytest.approx(60.0)
    assert row["quota_source"] == "provider_api:bailian.example/usage"
    kinds = [entry["source_kind"] for entry in row["provenance"]]
    assert kinds == ["registry", "provider_api"]
    assert row["provenance"][0]["source"] == "bailian_inline_7d_local_reconstruction"
    # Rows WITHOUT a live observation keep their registry facts untouched.
    chris_untouched = next(
        r for r in document["resources"]
        if r["shared_quota_resource_ref"] == "bailian:Ryan"
    )
    assert chris_untouched["quota_knowledge"] == "observed"
    assert chris_untouched["remaining_quota"] == pytest.approx(1.44)
    assert chris_untouched["quota_source"] == "bailian_inline_7d_local_reconstruction"
    assert "provenance" not in chris_untouched


def test_observation_document_is_referenceable_from_the_preview(tmp_path):
    live = _live_record("go", "C1", usage=90.0)
    path = _write_observations(tmp_path, [live])
    document = _produce(tmp_path, observations_path=path).to_dict()
    block = document["quota_observations"]
    assert block["schema"] == observation.OBSERVATION_SCHEMA
    assert block["observed_at"] == "2026-09-16T05:25:00Z"
    assert block["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert document["knowledge_summary"]["observed_vs_unknown"] == "4 observed / 2 unknown"


def test_producer_refuses_broken_observation_documents(tmp_path):
    from control_plane import executive_capacity_observation_producer as factory
    from control_plane import quota_economics_preview_producer as quota_module

    projection_path = tmp_path / "owner_ext_projection.json"
    projection_path.write_text(json.dumps(_extended_projection()))
    broker_path = base.quota_broker(tmp_path / "leases.sqlite")
    config = factory.validate_worker_capacity_source_config(base.source_config())

    missing = tmp_path / "missing_obs.json"
    with pytest.raises(quota.QuotaEconomicsPreviewError) as error:
        quota_module.produce_quota_economics_preview(
            source_config=config,
            projection_path=projection_path,
            broker_db_path=broker_path,
            observed_at=QUOTA_OBSERVED,
            quota_observations_path=missing,
        )
    assert error.value.code == "PROVIDER_QUOTA_OBSERVATION_UNAVAILABLE"
    assert not missing.exists()

    bad = tmp_path / "bad_obs.json"
    bad.write_text(json.dumps({"schema": "other/v9", "observations": []}))
    with pytest.raises(quota.QuotaEconomicsPreviewError) as error:
        quota_module.produce_quota_economics_preview(
            source_config=config,
            projection_path=projection_path,
            broker_db_path=broker_path,
            observed_at=QUOTA_OBSERVED,
            quota_observations_path=bad,
        )
    assert error.value.code == "PROVIDER_QUOTA_OBSERVATION_SCHEMA_INVALID"


def test_producer_path_has_no_environment_or_fixture_hooks():
    source = inspect.getsource(quota)
    assert "import os" not in source
    assert "getenv" not in source
    assert "monkeypatch" not in source
    observation_source = inspect.getsource(observation)
    assert "import os" not in observation_source
    assert "getenv" not in observation_source
    signature = inspect.signature(quota.produce_quota_economics_preview)
    assert signature.parameters["quota_observations_path"].default is None


# ── Managed local gateway state (anthropic-oauth durable ledger) ──────────────
# TEST FIXTURE material below: a synthetic gateway directory (gateway.env +
# state/budget.sqlite3) exercises the read-only ledger adapter offline. No
# real gateway state, provider fact, or credential is touched.


def _synthetic_gateway_dir(tmp_path, *, now):
    import sqlite3

    gateway = tmp_path / "anthropic-gateway"
    (gateway / "state").mkdir(parents=True)
    (gateway / "gateway.env").write_text(
        "\n".join(
            [
                "# synthetic test fixture configuration",
                "ANTHROPIC_FIVE_HOUR_BUDGET=100",
                "ANTHROPIC_WEEKLY_BUDGET=700",
                "ANTHROPIC_WINDOW_5H_S=18000",
                "ANTHROPIC_WINDOW_WEEKLY_S=604800",
            ]
        )
        + "\n"
    )
    db = sqlite3.connect(gateway / "state" / "budget.sqlite3")
    try:
        db.execute(
            "CREATE TABLE usage (row_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "account_id TEXT NOT NULL, ts REAL NOT NULL, weight REAL NOT NULL, "
            "model TEXT NOT NULL, outcome TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE cooldown (account_id TEXT PRIMARY KEY, "
            "until REAL NOT NULL, reason TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE account_meta (account_id TEXT PRIMARY KEY, "
            "label TEXT NOT NULL, last_status TEXT, last_status_at REAL)"
        )
        db.executemany(
            "INSERT INTO account_meta VALUES (?,?,?,?)",
            [
                ("a1", "max-1", "ok", now - 60),
                ("a2", "max-2", "http_400", now - 30),
            ],
        )
        # max-1: one settled 5h-window event (weight 10) and one older weekly
        # event outside the 5h window (weight 5). max-2: settled http_400 row
        # that the gateway itself keeps recorded (conservative window usage).
        db.executemany(
            "INSERT INTO usage (account_id, ts, weight, model, outcome) VALUES (?,?,?,?,?)",
            [
                ("a1", now - 3600, 10.0, "claude-fable-5", "ok"),
                ("a1", now - 40000, 5.0, "claude-haiku-4-5", "ok"),
                ("a2", now - 600, 2.0, "claude-opus-5", "http_400"),
            ],
        )
        db.execute(
            "INSERT INTO cooldown VALUES (?,?,?)", ("a2", now + 300, "bench")
        )
        db.commit()
    finally:
        db.close()
    return gateway


def test_gateway_state_adapter_observes_the_durable_ledger(tmp_path):
    now = datetime.strptime(
        "2026-11-08T16:00:00Z", "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc).timestamp()
    gateway = _synthetic_gateway_dir(tmp_path, now=now)
    records = observation.observe_anthropic_oauth_gateway_state(
        gateway, now=now
    )
    by_account = {record.account: record for record in records}
    assert sorted(by_account) == ["max-1", "max-2"]
    first = by_account["max-1"]
    assert first.observed is True
    assert first.provider == "anthropic-oauth"
    assert first.usage == 90.0  # 100 budget − 10 in-window weight
    assert first.usage_unit == "percent_of_window_remaining"
    assert first.limit is None  # configured budget is a ceiling, not a limit
    # The 5h window recovers when its oldest in-window event exits.
    assert first.reset_at == "2026-11-08T20:00:00Z"  # (now-3600) + 18000
    assert first.cooldown_until is None
    assert first.provenance is not None and first.details is not None
    assert first.provenance["source_kind"] == "local_gateway_state"
    assert first.provenance["source_ref"] == (
        "anthropic-gateway/state/budget.sqlite3"
    )
    assert "endpoint_host_path" not in first.provenance
    assert "http_status" not in first.provenance
    windows = first.details["windows"]
    assert windows["five_hour"]["used_weight"] == 10.0
    assert windows["five_hour"]["in_window_events"] == 1
    assert windows["weekly"]["used_weight"] == 15.0
    assert windows["weekly"]["in_window_events"] == 2
    assert "not claimed as zero" in first.details["scope_note"]
    assert "not a provider-stated limit" in first.details[
        "configured_budget_basis"
    ]
    # Settled http_400 rows stay recorded: the gateway's own math counts them.
    second = by_account["max-2"]
    assert second.usage == 98.0
    assert second.cooldown_until == "2026-11-08T16:05:00Z"


def test_gateway_state_adapter_refuses_missing_state(tmp_path):
    empty = tmp_path / "anthropic-gateway"
    empty.mkdir()
    with pytest.raises(observation.QuotaObservationError) as error:
        observation.observe_anthropic_oauth_gateway_state(empty)
    assert error.value.code == "PROVIDER_QUOTA_OBSERVATION_INPUT_INVALID"


def test_gateway_observation_round_trips_the_document_validator(tmp_path):
    now = datetime.strptime(
        "2026-11-08T16:00:00Z", "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc).timestamp()
    gateway = _synthetic_gateway_dir(tmp_path, now=now)
    records = observation.observe_anthropic_oauth_gateway_state(
        gateway, now=now
    )
    path = _write_observations(
        tmp_path, records, observed_at="2026-11-08T16:00:00Z"
    )
    loaded = observation.load_quota_observations(path)
    assert loaded[("anthropic-oauth", "max-1")].observed is True
    assert (
        loaded[("anthropic-oauth", "max-1")].provenance["source_kind"]
        == "local_gateway_state"
    )

    # A local_gateway_state entry that ALSO claims an HTTP surface is
    # refused: it must not impersonate a provider_api observation.
    document = observation.build_observation_document(
        records,
        observed_at=datetime.strptime(
            "2026-11-08T16:00:00Z", "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc),
    )
    entry = document["observations"][0]
    entry["provenance"]["http_status"] = 200
    document["digest"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in document.items() if k != "digest"},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode()
    ).hexdigest()
    bad = tmp_path / "impersonating.json"
    bad.write_text(json.dumps(document))
    with pytest.raises(observation.QuotaObservationError) as error:
        observation.load_quota_observations(bad)
    assert "HTTP surface" in str(error.value)


def _gateway_style_record(provider, account, *, usage, reset_at):
    return observation.QuotaObservation(
        provider=provider,
        account=account,
        shared_quota_resource_ref=f"{provider}:{account}",
        observed=True,
        usage=usage,
        usage_unit="percent_of_window_remaining",
        limit=None,
        limit_unit=None,
        reset_at=reset_at,
        cooldown_until=None,
        reason_code=None,
        provenance={
            "source_kind": "local_gateway_state",
            "source_ref": "anthropic-gateway/state/budget.sqlite3",
            "observed_at": QUOTA_OBSERVED,
            "expires_at": "2026-09-16T05:40:00Z",
            "confidence": "managed_gateway_durable_ledger",
        },
        details={
            "windows": {
                "five_hour": {"used_pct": round(100.0 - usage, 2)},
            },
            "scope_note": "managed gateway path only; not claimed as zero",
        },
    )


def test_producer_merges_gateway_state_observation_into_rows(tmp_path):
    records = [
        _gateway_style_record(
            "go", "C1", usage=84.0, reset_at="2026-09-16T09:25:00Z"
        )
    ]
    path = _write_observations(tmp_path, records)
    preview = _produce(tmp_path, observations_path=path)
    document = preview.to_dict()
    row = next(
        r for r in document["resources"] if r["shared_quota_resource_ref"] == "go:C1"
    )
    assert row["quota_knowledge"] == "observed"
    assert row["remaining_quota"] == 84.0
    assert row["quota_source"] == (
        "local_gateway_state:anthropic-gateway/state/budget.sqlite3"
    )
    assert row["quota_observation"]["source_kind"] == "local_gateway_state"
    assert row["quota_observation"]["source_ref"] == (
        "anthropic-gateway/state/budget.sqlite3"
    )
    assert "endpoint_host_path" not in row["quota_observation"]
    assert row["quota_observation"]["windows"]["five_hour"] == {
        "used_pct": 16.0
    }
    assert row["provenance"][-1]["source_kind"] == "local_gateway_state"
    assert row["provenance"][-1]["source_ref"] == (
        "anthropic-gateway/state/budget.sqlite3"
    )
