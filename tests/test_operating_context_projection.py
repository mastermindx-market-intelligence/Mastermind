import ast
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from control_plane.operating_context_projection import (
        DUPLICATE_IDENTITY,
        INPUT_SHAPE_INVALID,
    MISSION_CONTEXT_MISMATCH,
    OVER_BUDGET,
    RECEIPT_CONTEXT_MISMATCH,
    AcceptedCriteriaFact,
    OperatingContextProjectionError,
    OperatingContextSnapshot,
    OperatingContextProjection,
    SourceDigestFact,
    SuppliedInputReceiptFact,
    project_operating_context,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "operating_context"
ALLOWED_PRODUCTION_IMPORTS = {"dataclasses", "hashlib", "json"}
FORBIDDEN_IMPORTS = {
    "broker",
    "provider",
    "app",
    "runtime",
    "control",
    "ledger",
    "subprocess",
    "pathlib",
    "os",
    "sys",
    "time",
    "random",
    "socket",
}


def _fixture_bytes(name):
    return (FIXTURE_DIR / name).read_bytes()


def _fixture_json(name):
    return json.loads(_fixture_bytes(name))


def _load_operating_context_fixture(name):
    """Test-only fixture loader; production deliberately has no loader."""
    from control_plane.operating_context_projection import (
        AcceptedCriteriaFact,
        ContextBundleFact,
        MissionContextAssociationFact,
        MissionFact,
        MissingnessFact,
        OperatingContextSnapshot,
        SourceDigestFact,
        SuppliedInputReceiptFact,
    )

    payload = _fixture_json(name)
    mission = MissionFact(**payload["mission"])
    criteria = None
    criteria_absent = None
    if payload.get("criteria") is not None:
        criteria = AcceptedCriteriaFact(**payload["criteria"])
    if payload.get("criteria_absent") is not None:
        criteria_absent = MissingnessFact(**payload["criteria_absent"])

    bundle = None
    association = None
    association_absent = None
    if payload.get("context_bundle") is not None:
        bundle_data = payload["context_bundle"]
        bundle = ContextBundleFact(
            context_bundle_id=bundle_data["context_bundle_id"],
            revision=bundle_data["revision"],
            context_digest=bundle_data["context_digest"],
            selected_items=tuple(bundle_data["selected_items"]),
            excluded=tuple(bundle_data["excluded"]),
            omitted_due_to_budget=tuple(bundle_data["omitted_due_to_budget"]),
            degraded=tuple(bundle_data["degraded"]),
        )
    if payload.get("context_association") is not None:
        association = MissionContextAssociationFact(**payload["context_association"])
    if payload.get("context_association_absent") is not None:
        association_absent = MissingnessFact(**payload["context_association_absent"])

    receipts = tuple(SuppliedInputReceiptFact(**item) for item in payload.get("receipts", []))
    receipt_absent = (
        MissingnessFact(**payload["receipt_absent"])
        if payload.get("receipt_absent") is not None
        else None
    )
    missingness = tuple(MissingnessFact(**item) for item in payload.get("missingness", []))
    sources = tuple(SourceDigestFact(**item) for item in payload.get("source_digests", []))
    return OperatingContextSnapshot(
        mission=mission,
        criteria=criteria,
        criteria_absent=criteria_absent,
        context_bundle=bundle,
        context_association=association,
        context_association_absent=association_absent,
        receipts=receipts,
        receipt_absent=receipt_absent,
        missingness=missingness,
        conversation_ref=payload.get("conversation_ref"),
        artifact_ref=payload.get("artifact_ref"),
        review_ref=payload.get("review_ref"),
        source_digests=sources,
    )


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _projection_dict(name):
    return project_operating_context(_load_operating_context_fixture(name)).to_dict()


def _refuses(name, code):
    with pytest.raises(OperatingContextProjectionError) as caught:
        _load_operating_context_fixture(name)
    assert caught.value.code == code


def test_wrong_mission_context_join_refused_not_rendered():
    _refuses("malformed.json", MISSION_CONTEXT_MISMATCH)


def test_selected_without_receipt_never_shown_supplied():
    result = _projection_dict("baseline.json")
    assert result["supply_state"] == "SELECTED_ONLY"
    assert result["receipt_digests"] == []


def test_budget_omission_remains_visible():
    result = _projection_dict("baseline.json")
    assert result["omitted_due_to_budget"] == [_digest("budget-omission-001")]


def test_all_source_digests_are_shown_exactly_once():
    result = _projection_dict("baseline.json")
    source_ids = list(result["source_digests"])
    assert len(source_ids) == len(set(source_ids))
    assert source_ids == ["mission", "context_bundle", "selection_policy"]
    for entry in result["source_digests"].values():
        assert set(entry) == {"digest", "producer_digest"}
        assert len(entry["digest"]) == 64
        assert len(entry["producer_digest"]) == 64


def test_criteria_null_stays_criteria_record_missing():
    result = _projection_dict("baseline.json")
    assert result["criteria_ref"] is None
    assert result["criteria_state"] == "CRITERIA_RECORD_MISSING"
    assert any(
        item["missingness_class"] == "MISSING_PRODUCER"
        and item["target_field"] == "criteria"
        for item in result["missingness"]
    )


def test_adapter_performs_zero_broker_provider_or_control_calls(monkeypatch):
    class AdversarialSnapshot:
        calls = 0

        def __getattr__(self, name):
            type(self).calls += 1
            raise AssertionError(f"forbidden adapter boundary read: {name}")

    attempts = []
    monkeypatch.setattr(
        "builtins.open", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("filesystem"))
    )
    monkeypatch.setattr("time.time", lambda: (_ for _ in ()).throw(AssertionError("clock")))
    monkeypatch.setattr("random.random", lambda: (_ for _ in ()).throw(AssertionError("random")))
    monkeypatch.setattr("os.getenv", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("environment")))
    with pytest.raises(OperatingContextProjectionError) as caught:
        project_operating_context(AdversarialSnapshot())
    assert caught.value.code == INPUT_SHAPE_INVALID
    assert AdversarialSnapshot.calls == 0
    assert attempts == []


def test_oversize_input_is_refused_without_truncation():
    valid = _load_operating_context_fixture("baseline.json")
    oversized_item = "x" * 4097
    with pytest.raises(OperatingContextProjectionError) as caught:
        replace(valid.context_bundle, selected_items=(oversized_item,))
    assert caught.value.code == OVER_BUDGET
    bounded_items = tuple("y" * 4096 for _ in range(64))
    assert len(json.dumps(bounded_items).encode("utf-8")) > 256 * 1024
    with pytest.raises(OperatingContextProjectionError) as total_caught:
        replace(valid, context_bundle=replace(valid.context_bundle, selected_items=bounded_items))
    assert total_caught.value.code == OVER_BUDGET


def test_deterministic_output_bytes_for_identical_inputs():
    fixture_names = ("baseline.json", "supplied.json", "missingness.json", "malformed.json")
    before = {name: _fixture_bytes(name) for name in fixture_names}
    first = _load_operating_context_fixture("supplied.json")
    second = _load_operating_context_fixture("supplied.json")
    kwargs = dict(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    first_bytes = json.dumps(project_operating_context(first).to_dict(), **kwargs).encode("utf-8")
    second_bytes = json.dumps(project_operating_context(second).to_dict(), **kwargs).encode("utf-8")
    assert first_bytes == second_bytes
    assert len(first_bytes) <= 128 * 1024
    assert before == {name: _fixture_bytes(name) for name in fixture_names}


def test_excluded_and_degraded_missingness_are_preserved():
    result = _projection_dict("missingness.json")
    assert result["excluded"] == [_digest("excluded-source-001")]
    assert result["degraded"] == [_digest("degraded-source-001")]
    classes = {item["missingness_class"] for item in result["missingness"]}
    assert classes == {"MISSING_PRODUCER", "NULL_BY_DESIGN", "EXCLUDED", "OMITTED", "DEGRADED"}


def test_receipt_with_wrong_context_digest_is_refused():
    valid = _load_operating_context_fixture("baseline.json")
    assert valid.receipt_absent is None
    wrong = SuppliedInputReceiptFact(
        mission_id="m",
        context_bundle_id="b",
        revision="r",
        context_digest="0" * 64,
        input_digest="1" * 64,
        provider_turn_ref="turn",
        receipt_id="receipt",
        producer="receipt-owner",
        published_at="2026-09-14T00:00:00Z",
    )
    with pytest.raises(OperatingContextProjectionError) as caught:
        replace(valid, receipts=(wrong,), receipt_absent=None)
    assert caught.value.code == RECEIPT_CONTEXT_MISMATCH


def test_duplicate_identity_is_refused():
    valid = _load_operating_context_fixture("baseline.json")
    wrong_criteria = AcceptedCriteriaFact(
        criteria_ref="criteria-wrong",
        mission_id="mission-wrong",
        revision="criteria-revision-wrong",
        producer="accepted-criteria-owner",
    )
    valid = replace(valid, criteria_absent=None)
    with pytest.raises(OperatingContextProjectionError) as identity_error:
        replace(valid, criteria=wrong_criteria)
    assert identity_error.value.code == "CRITERIA_IDENTITY_MISMATCH"
    duplicate = SourceDigestFact(source_id="mission", digest="2" * 64, producer="producer-a")
    with pytest.raises(OperatingContextProjectionError) as caught:
        replace(valid, source_digests=valid.source_digests + (duplicate,))
    assert caught.value.code == DUPLICATE_IDENTITY


def test_optional_conversation_and_artifact_nulls_are_by_design():
    result = _projection_dict("baseline.json")
    assert result["conversation_ref"] is None
    assert result["artifact_ref"] is None
    assert any(
        item["missingness_class"] == "NULL_BY_DESIGN"
        and item["target_field"] in {"conversation_ref", "artifact_ref"}
        for item in result["missingness"]
    )


def test_source_import_allowlist_has_no_forbidden_import():
    source_path = Path(__file__).parents[1] / "control_plane" / "operating_context_projection.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))
    imports = set()
    referenced_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Name):
            referenced_roots.add(node.id)
        elif isinstance(node, ast.Attribute):
            value = node.value
            while isinstance(value, ast.Attribute):
                value = value.value
            if isinstance(value, ast.Name):
                referenced_roots.add(value.id)
    assert imports <= ALLOWED_PRODUCTION_IMPORTS
    assert not (imports | referenced_roots) & FORBIDDEN_IMPORTS
    assert OperatingContextSnapshot.__dataclass_params__.frozen
    assert OperatingContextSnapshot.__slots__
    assert OperatingContextProjection.__dataclass_params__.frozen
    assert OperatingContextProjection.__slots__
