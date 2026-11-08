"""Existing selected-generation owner -> Portfolio parsers -> actual MCP serializer.

All generation publication is synthetic and confined to pytest temporary roots.
The captured preview provenance is beside the fixture. No live stores, network,
credentials, SDK turns or execution authority are involved. The installed Macro
source must provide its existing native contract and publication facade.
"""
from __future__ import annotations

import asyncio
import builtins
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import bot  # noqa: F401 -- existing Macro library bootstrap
import pytest

from brain import autonomous_mcp, portfolio_intelligence as pi

FIXTURE = Path(__file__).parent / "fixtures/sector_generation.captured.preview.v1.json"
SOURCE = "2026-11-03"
PUBLISHED = datetime(2026, 11, 3, 23, 0, 21, tzinfo=UTC)


@pytest.mark.parametrize("order", ["mastermind_first", "macro_first"])
def test_installed_native_owners_resolve_without_ambient_package_discovery(tmp_path, order):
    root = Path(__file__).resolve().parent.parent
    ambient = tmp_path / "ambient"
    (ambient / "scripts").mkdir(parents=True)
    (ambient / "scripts/__init__.py").write_text("raise AssertionError('ambient scripts executed')\n")
    code = """
import sys, json
from pathlib import Path
root, ambient, order = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
vendor = root / 'vendor/macro'
sys.path[:0] = [str(root), str(ambient)]
if order == 'macro_first':
    sys.path.insert(0, str(vendor))
import scripts
if order == 'mastermind_first':
    assert Path(scripts.__file__).resolve() == root / 'scripts/__init__.py'
    assert list(scripts.__path__) == [str(root / 'scripts'), str(vendor / 'scripts')]
import bot
from lib import sector_generation_contract
from scripts import vps_live_orchestrator, check_sector_intelligence_freshness
for module in (vps_live_orchestrator, check_sector_intelligence_freshness):
    assert Path(module.__file__).resolve().parent == (vendor / 'scripts').resolve()
assert all(str(ambient) not in path for path in scripts.__path__)
print(json.dumps({'order':order, 'native_owners':'installed_macro', 'ambient_admitted':False}))
"""
    run = subprocess.run([sys.executable, "-c", code, str(root), str(ambient), order],
                         cwd=tmp_path, capture_output=True, text=True, timeout=20,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["ambient_admitted"] is False


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode()


def packet(arguments):
    response = asyncio.run(autonomous_mcp.get_sector_rotation.handler(arguments))
    text = response["content"][0]["text"]
    result = json.loads(text)
    assert len(text) <= 7200 and len(text.encode()) <= 7200
    assert "_transport_truncated" not in result
    assert result["context_only"] is True
    if "authority" in result:
        assert all(value is False for value in result["authority"].values())
    return result


@pytest.fixture
def native(tmp_path, monkeypatch):
    # Import the actual existing owners, including their normal package names.
    # A missing dependency is a qualification failure, not a successful skip.
    from lib import sector_generation_contract as contract
    from lib import sector_generation_wire as wire
    from scripts import vps_live_orchestrator as publisher

    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "88afd1917b710a8db2cb14ffa0d0b3283f13ee57725154a17b6b38175c035dac"
    captured = json.loads(raw)
    central = deepcopy(captured["projection"]["data"]["core"])
    central.pop("dated_context", None)
    central.pop("captured_classification", None)
    central["measured_read"]["cohort"]["horizon"] = "rs_63d"
    # Preview intentionally excludes these raw Central fields. They prove the
    # incumbent legacy consumer uses captured Central, not the narrower core.
    central["market"] = {"risk_on": False, "headline_en": "SYNTHETIC_CAPTURE_ONE"}
    central["baskets"] = [{"id": "fixture-basket", "ticker": "IGV", "name": "Synthetic basket",
                           "kind": "basket", "rotation": {"rank": 1, "score": 12}}]
    baskets = {"as_of": SOURCE, "theme_intel": {"as_of": SOURCE}}
    documents = [central, deepcopy(captured["projection"]["data"]["history"]), baskets,
                 {"theme_context": {"as_of": SOURCE, "leadership": {
                     "state": "rotating", "days_in_state": 3, "stance_en": "synthetic-one",
                     "strength": [{"id": "us_sector_health", "name": "Health Care"}]}}},
                 {"schema": "sector_intelligence_action_board.v1", "as_of": SOURCE,
                  "action_board": {lane: [] for lane in
                                   ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid")},
                  "baskets_sha256": hashlib.sha256(encoded(baskets)).hexdigest()}]
    # The incumbent owner correctly rejects an empty action board. Supply one
    # explicitly synthetic display row without inventing any trade authority.
    documents[-1]["action_board"]["hold"] = [
        {"ticker": "fixture-0", "name": "Synthetic display context", "kind": "theme",
         "href": "basket/fixture-0.html"}]
    members = dict(zip(contract.SECTOR_GENERATION_MEMBERS, map(encoded, documents)))
    identity = {"sector_view": {"schema": "sector.view_inputs.v1", "source_session": SOURCE,
                               "input_version": "portfolio-synthetic-native-v1", "baseline_session": None,
                               "source_qualification": "accepted"}}
    clock = [PUBLISHED]

    class FrozenClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)

    monkeypatch.setattr(pi, "datetime", FrozenClock)
    monkeypatch.setattr(pi, "_read_vendor", lambda *a, **kw: pytest.fail("static fallback was consulted"))
    root = tmp_path / "state/generations"
    monkeypatch.setenv("MACRO_SECTOR_GENERATIONS_ROOT", str(root))

    def publish(raw_members=None, *, generation_id="g1", expected=None, source_identity=None,
                retained_fixture=False):
        raw_members = members if raw_members is None else raw_members
        sources = {}
        for name, data in raw_members.items():
            path = tmp_path / "sources" / generation_id / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            sources[name] = path
        request = contract.prepare_sector_generation_request(
            sources=sources, input_identity=source_identity or identity, generation_id=generation_id,
            source_revision="synthetic-portfolio-qualification", lane="snapshot")
        if retained_fixture:
            # The semantic publisher correctly refuses new degraded selections.
            # Only this explicit retained-snapshot control uses the incumbent
            # generic byte publisher, as Macro's own reader qualification does.
            # The real consumer still performs its complete semantic projection.
            assert identity["sector_view"]["source_qualification"] == "degraded"
            request = publisher.GenerationRequest(
                generation_id=generation_id, domain="sector", lane="snapshot",
                source_revision="synthetic-retained-degraded", input_identity=identity,
                artifacts=tuple(publisher.GenerationArtifact(name=name, source=path,
                    validator=lambda captured: None) for name, path in sources.items()))
        owner = publisher.Orchestrator(live_dir=tmp_path / "public/live", state_dir=tmp_path / "state",
                                       data_dir=tmp_path / "data", now=PUBLISHED)
        result = owner.publish_generation(request, expected_current_content_id=expected)
        assert result.status == "published", result.detail
        return result

    return SimpleNamespace(contract=contract, wire=wire, publisher=publisher, root=root,
                           clock=clock, central=central, members=members, identity=identity, publish=publish)


def expected_receipt(native, generation="g1"):
    # Qualification reference over the same explicit fixture bytes. It does not
    # reread the live selected pointer or borrow a separate generation's receipt.
    return native.contract.project_sector_bundle(
        member_bytes=native.members, input_identity=native.identity,
        generation_id=generation, published_at=PUBLISHED.isoformat(),
        now=native.clock[0], audience="preview", preview_rows=3)["receipt"]


def test_real_capture_reaches_all_three_incumbent_mcp_projections(native):
    native.publish()
    receipt = expected_receipt(native)
    legacy = packet({"projection": "legacy", "limit": 6})
    assert legacy["market"]["headline_en"] == "SYNTHETIC_CAPTURE_ONE"
    assert legacy["market"]["risk_on"] is False
    assert legacy["baskets"][0]["ticker"] == "IGV"
    assert legacy["health"]["native_receipt"] == receipt
    assert legacy["health"]["execution_authority"] is False
    assert len(legacy["sectors"]) == 6

    dossier = packet({"projection": "sector_dossiers"})
    assert dossier["consumer_reason"] is None
    assert dossier["windows_sessions"] == [21, 63]
    assert len(dossier["groups"]) == 11
    assert dossier["artifact_health"]["native_receipt"] == receipt
    originals = {row["group_id"]: row for row in native.central["measured_read"]["sector_dossiers"]["groups"]}
    for row in dossier["groups"]:
        assert row["relative_wealth_pct"] == [originals[row["group_id"]]["relative_wealth_pct"][key]
                                              for key in ("rs_21d", "rs_63d")]

    companion = native.central["measured_read"]["sector_window_measurements"]
    for source in companion["groups"]:
        result = packet({"projection": "sector_windows", "sector": source["group_id"]})
        assert result["consumer_reason"] is None
        assert result["windows_sessions"] == [5, 20, 63] and len(result["groups"]) == 11
        assert result["artifact_health"]["native_receipt"] == receipt
        assert result["clocks"] == companion["clocks"]
        for key in ("absolute_return_pct", "relative_wealth_pct"):
            assert result["selected"][key] == [source["windows"][window][key] for window in ("5", "20", "63")]


def test_pointer_replacement_after_capture_cannot_mix_raw_central_and_receipt(native, monkeypatch):
    first = native.publish()
    changed = dict(native.members)
    central = deepcopy(native.central)
    central["market"]["headline_en"] = "SYNTHETIC_CAPTURE_TWO"
    changed[pi._PSL_NATIVE_MEMBER] = encoded(central)
    original = native.publisher.read_selected_generation
    calls = []

    def capture(**kwargs):
        calls.append(kwargs)
        snapshot = original(**kwargs)
        native.publish(changed, generation_id="g2", expected=first.content_id)
        return snapshot

    monkeypatch.setattr(native.publisher, "read_selected_generation", capture)
    result = packet({})
    assert len(calls) == 1
    assert calls[0] == {"generations_root": native.root, "domain": "sector",
                        "members": native.contract.SECTOR_GENERATION_MEMBERS}
    assert result["market"]["headline_en"] == "SYNTHETIC_CAPTURE_ONE"
    assert result["health"]["native_receipt"]["generation_id"] == "g1"
    monkeypatch.setattr(native.publisher, "read_selected_generation", original)
    second = packet({})
    assert second["market"]["headline_en"] == "SYNTHETIC_CAPTURE_TWO"
    assert second["health"]["native_receipt"]["generation_id"] == "g2"


def test_capture_uses_verified_bytes_and_next_read_withdraws_corruption(native, monkeypatch):
    native.publish()
    original = native.publisher.read_selected_generation

    def capture(**kwargs):
        snapshot = original(**kwargs)
        (native.root / "sector/g1" / pi._PSL_NATIVE_MEMBER).write_bytes(b'{"corrupt":true}')
        return snapshot

    monkeypatch.setattr(native.publisher, "read_selected_generation", capture)
    assert packet({})["market"]["headline_en"] == "SYNTHETIC_CAPTURE_ONE"
    monkeypatch.setattr(native.publisher, "read_selected_generation", original)
    result = packet({"projection": "sector_windows", "sector": "XLU"})
    assert result["consumer_reason"] == "window_companion_not_supplied"
    assert result["artifact_health"]["source_reason"] == "native_generation_unavailable"
    assert "native_receipt" not in result["artifact_health"]


@pytest.mark.parametrize("configured,reason", [
    (None, "native_generation_not_configured"),
    ("", "native_generation_configuration_invalid"),
    ("relative", "native_generation_configuration_invalid"),
    ("/", "native_generation_configuration_invalid"),
    (" /private/root", "native_generation_configuration_invalid"),
    ("/private/../root", "native_generation_configuration_invalid"),
])
def test_configuration_refusal_never_initializes_a_store_or_reads_static(monkeypatch, tmp_path, configured, reason):
    if configured is None:
        monkeypatch.delenv("MACRO_SECTOR_GENERATIONS_ROOT", raising=False)
    else:
        monkeypatch.setenv("MACRO_SECTOR_GENERATIONS_ROOT", configured)
    monkeypatch.setattr(pi, "_read_vendor", lambda *a, **kw: pytest.fail("static fallback"))
    before = set(tmp_path.rglob("*"))
    result = packet({"projection": "sector_dossiers"})
    assert result["artifact_health"]["source_reason"] == reason
    assert result["artifact_health"]["stale"] is None
    assert len(result["groups"]) == 11
    assert set(tmp_path.rglob("*")) == before


def test_unselected_store_is_unavailable_and_read_does_not_create_it(native):
    assert not native.root.exists()
    result = packet({"projection": "sector_dossiers"})
    assert result["artifact_health"]["source_reason"] in (
        "native_generation_not_selected", "native_generation_unavailable")
    assert not native.root.exists()


def test_missing_native_dependency_is_a_sanitized_unavailable_read(monkeypatch, tmp_path):
    monkeypatch.setenv("MACRO_SECTOR_GENERATIONS_ROOT", str(tmp_path / "absent"))
    original = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "lib.sector_generation_contract":
            raise ImportError("PRIVATE_DEPENDENCY_DETAIL")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    result = packet({})
    assert result["health"]["source_reason"] == "native_generation_reader_unavailable"
    assert "PRIVATE_DEPENDENCY_DETAIL" not in json.dumps(result)
    assert result["sectors"] == []


@pytest.mark.parametrize("qualification,age,status,stale", [
    ("accepted", 0, "fresh", False), ("accepted", 3, "stale", True),
    ("degraded", 0, "unknown", None),
])
def test_owner_qualification_keeps_degradation_distinct_from_temporal_staleness(
        native, qualification, age, status, stale):
    native.identity["sector_view"]["source_qualification"] = qualification
    native.publish(retained_fixture=qualification == "degraded")
    native.clock[0] = PUBLISHED + timedelta(days=age)
    before = {str(p.relative_to(native.root)): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in native.root.rglob("*") if p.is_file()}
    result = packet({"projection": "sector_dossiers"})
    health = result["artifact_health"]
    assert health["status"] == status and health["stale"] is stale
    assert health["native_receipt"]["qualification"] == ("stale" if age else qualification)
    assert health["native_receipt"]["published_at"] == PUBLISHED.isoformat()
    assert {str(p.relative_to(native.root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in native.root.rglob("*") if p.is_file()} == before


def test_oversized_legacy_fields_withdraw_the_whole_packet_before_serializer(native):
    central = deepcopy(native.central)
    central["market"]["headline_en"] = "界" * 4000
    native.members[pi._PSL_NATIVE_MEMBER] = encoded(central)
    native.publish()
    result = packet({})
    assert result["health"]["source_reason"] == "native_legacy_transport_budget_exceeded"
    assert result["health"]["available"] is False
    assert result["health"]["native_receipt"]["generation_id"] == "g1"
    assert result["as_of"] is None and result["sectors"] == result["baskets"] == []
    assert all(value is None for value in result["market"].values())


@pytest.mark.parametrize("failure", ["size", "semantic", "storage"])
def test_owner_refusals_never_disclose_private_details_or_fall_back(native, monkeypatch, failure):
    native.publish()

    def refuse(*args, **kwargs):
        if failure == "size":
            raise native.wire.SectorGenerationTooLarge("PRIVATE_SOURCE_PATH")
        if failure == "semantic":
            raise native.contract.SectorGenerationContractError("PRIVATE_SOURCE_PATH")
        raise OSError("PRIVATE_SOURCE_PATH")

    if failure == "size":
        monkeypatch.setattr(native.wire, "encode_sector_generation", refuse)
    elif failure == "semantic":
        monkeypatch.setattr(native.contract, "project_sector_bundle", refuse)
    else:
        monkeypatch.setattr(native.publisher, "read_selected_generation", refuse)
    result = packet({"projection": "sector_dossiers"})
    assert result["consumer_reason"] == "dossier_not_supplied"
    assert result["artifact_health"]["source_reason"] == {
        "size": "native_generation_too_large", "semantic": "native_generation_contract_invalid",
        "storage": "native_generation_unavailable"}[failure]
    assert "PRIVATE_SOURCE_PATH" not in json.dumps(result)
    assert "native_receipt" not in result["artifact_health"]
