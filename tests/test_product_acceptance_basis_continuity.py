"""Source continuity is narrower than Runtime issuance or product acceptance."""

import copy
import hashlib

import pytest

from control_plane import agentos_product_acceptance_basis as owner


def acquired_basis():
    source = {
        "repository": "mastermindx-market-intelligence/macro",
        "commit": "a" * 40,
        "path": "agentos/workstreams/WS-FIXTURE.md",
        "content_sha256": "b" * 64,
    }
    original = {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "commit": "c" * 40,
        "path": "research/fixture-intent.md",
        "content_sha256": "d" * 64,
    }
    execution = {**original, "path": "research/executive_commissions/COMMISSION.md"}
    objective = 'Deliver the fixture [MASTERMIND_ACCEPTANCE_CRITERIA_V1:["Exact result consumed"]]'
    obligation = {
        "source_ref": original,
        "section": "15",
        "label": "Rollback",
        "required_outcome": "Pause admissions and preserve in-flight effects and pending consumption.",
    }
    entry = {
        "commission_id": "fixture",
        "commission_ref": original,
        "continuity_ref": source,
        "original_intent_ref": original,
        "original_proof_contract_ref": original,
        "proof_contract_ref": original,
        "current_intent_revision": "initial-v1",
        "correction_state": "NO_CORRECTION_DECLARED_AT_THIS_REVISION",
        "correction_chain": [],
        "criteria_objective": objective,
        "current_intent_text": objective,
        "criteria_objective_sha256": hashlib.sha256(objective.encode()).hexdigest(),
        "criteria_sources": [
            {"criterion_index": 0, "source_ref": original, "locators": ["15"]}
        ],
        "original_source_status": "AUTHENTIC_USER_INPUT_PROTECTED",
        "proof_obligations": [obligation],
        "proof_obligation_digests": [owner._canonical_digest(obligation)],
        "execution_commission_refs": [execution],
        "execution_commission_state": "ASSOCIATED_SOURCE_REFERENCES_ONLY",
        "workstream": "WS:FIXTURE",
        "source_state": "CURRENT",
        "current_intent_ref": source,
        "source_record_ref": source,
        "reference_observation": "DECLARED_REFERENCES_NOT_RETRIEVED_OR_AUTHENTICATED_HERE",
        "snapshot_consistency": "EXISTING_NON_ATOMIC_RECORD_READ",
    }
    entry["acceptance_basis_digest"] = owner._canonical_digest(entry)
    return owner.ProductAcceptanceBasisRead("a" * 40, "sha256:" + "e" * 64, entry)


def restamp(entry):
    entry["acceptance_basis_digest"] = owner._canonical_digest(
        {k: v for k, v in entry.items() if k != "acceptance_basis_digest"}
    )


def test_unrelated_head_and_workstream_progress_preserve_issued_proof_identity():
    issued = acquired_basis()
    before = copy.deepcopy(issued.entry)
    entry = copy.deepcopy(issued.entry)
    source = {
        **entry["source_record_ref"],
        "commit": "f" * 40,
        "content_sha256": "1" * 64,
    }
    entry["source_record_ref"] = source
    entry["current_intent_ref"] = dict(source)
    restamp(entry)
    current = owner.ProductAcceptanceBasisRead("f" * 40, "sha256:" + "2" * 64, entry)
    observed = owner.reconcile_unchanged_acceptance_basis(issued, current)
    assert observed.disposition == "SOURCE_OBSERVATION_CHANGED_DECLARATION_UNCHANGED"
    assert observed.issued_basis_digest == before["acceptance_basis_digest"]
    assert observed.current_basis_digest != observed.issued_basis_digest
    assert issued.entry == before


def test_unchanged_acquisition_is_explicit_without_issuing_a_verdict():
    read = acquired_basis()
    observed = owner.reconcile_unchanged_acceptance_basis(read, read)
    assert observed.disposition == "UNCHANGED_SOURCE"
    assert not hasattr(observed, "accepted")


@pytest.mark.parametrize(
    "change",
    ["obligation", "correction", "association", "criteria", "revision", "new_field"],
)
def test_material_changes_cannot_be_hidden_by_a_fresh_full_basis_digest(change):
    issued = acquired_basis()
    current = copy.deepcopy(issued)
    entry = current.entry
    if change == "obligation":
        entry["proof_obligations"][0]["required_outcome"] = "Only stop the UI"
        entry["proof_obligation_digests"] = [
            owner._canonical_digest(entry["proof_obligations"][0])
        ]
    elif change == "correction":
        entry["correction_state"] = "CORRECTIONS_DECLARED_AT_THIS_REVISION"
        entry["correction_chain"] = [entry["original_intent_ref"]]
    elif change == "association":
        entry["execution_commission_refs"][0]["commit"] = "3" * 40
    elif change == "criteria":
        entry["criteria_sources"][0]["locators"] = ["A weaker source clause"]
    elif change == "revision":
        entry["current_intent_revision"] = "correction-v2"
    else:
        entry["unrecognized_future_semantics"] = True
    restamp(entry)
    with pytest.raises(
        owner.ProductAcceptanceBasisUnavailable,
        match="SOURCE_REVISION_RECONCILIATION_REQUIRED",
    ):
        owner.reconcile_unchanged_acceptance_basis(issued, current)


@pytest.mark.parametrize(
    "damage", ["unreadable", "wrong_source", "stale_digest", "missing_field"]
)
def test_missing_or_inconsistent_observation_requires_reconciliation(damage):
    issued = acquired_basis()
    current = copy.deepcopy(issued)
    if damage == "unreadable":
        current.entry["source_state"] = "DENIED"
        restamp(current.entry)
    elif damage == "wrong_source":
        current.entry["current_intent_ref"] = {
            **current.entry["current_intent_ref"],
            "commit": "4" * 40,
        }
        restamp(current.entry)
    elif damage == "stale_digest":
        current.entry["acceptance_basis_digest"] = "5" * 64
    else:
        del current.entry["proof_obligations"]
        restamp(current.entry)
    with pytest.raises(
        owner.ProductAcceptanceBasisUnavailable,
        match="SOURCE_REVISION_RECONCILIATION_REQUIRED",
    ):
        owner.reconcile_unchanged_acceptance_basis(issued, current)
