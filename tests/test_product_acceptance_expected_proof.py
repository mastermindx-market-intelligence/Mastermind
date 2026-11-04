"""Complete acquired declarations own expected rows; callers cannot choose subsets."""

import copy
import pytest
from common.commission_ref import normalize_commission_ref
from common.product_acceptance_contract import (
    require_complete_product_acceptance_review_proof,
    ProductAcceptanceContractError,
)
from control_plane import agentos_product_acceptance_basis as owner
from tests.test_product_acceptance_basis_continuity import acquired_basis, restamp


def expected(read):
    return owner.expected_product_acceptance_proof(
        read,
        root_objective=read.entry["criteria_objective"],
        execution_commission_ref=normalize_commission_ref(
            read.entry["execution_commission_refs"][0]
        ),
    )


def test_every_literal_source_obligation_reaches_the_review_contract():
    read = acquired_basis()
    second = {
        **read.entry["proof_obligations"][0],
        "label": "Independent second must-have",
        "required_outcome": "The original assigning parent consumes the retained result.",
    }
    read.entry["proof_obligations"].append(second)
    read.entry["proof_obligation_digests"].append(owner._canonical_digest(second))
    restamp(read.entry)
    identities = expected(read)
    proof = {
        "schema": "mastermind.product_acceptance_review_proof.v1",
        "acceptance_basis_digest": identities.basis_digest,
        "criteria": [
            {
                "criterion_digest": d,
                "state": "SATISFIED",
                "evidence_digests": ["9" * 64],
            }
            for d in identities.criterion_digests
        ],
        "obligations": [
            {
                "obligation_digest": d,
                "state": "SATISFIED",
                "evidence_digests": ["8" * 64],
            }
            for d in identities.obligation_digests
        ],
    }
    args = {
        "expected_basis_digest": identities.basis_digest,
        "expected_criterion_digests": identities.criterion_digests,
        "expected_obligation_digests": identities.obligation_digests,
    }
    assert require_complete_product_acceptance_review_proof(proof, **args) == proof
    proof["obligations"].pop()
    with pytest.raises(ProductAcceptanceContractError) as error:
        require_complete_product_acceptance_review_proof(proof, **args)
    assert error.value.repair_identity == identities.obligation_digests[1]
    assert error.value.repair_kind == "MISSING_REQUIRED_PROOF"


@pytest.mark.parametrize(
    "change",
    [
        "digest_subset",
        "digest_reorder",
        "clause_changed",
        "anchor_missing",
        "unassociated",
        "objective_mismatch",
        "unresolved",
        "duplicate_clause",
        "unknown_field",
    ],
)
def test_restamping_a_damaged_record_does_not_establish_a_complete_basis(change):
    read = acquired_basis()
    entry = read.entry
    if change == "digest_subset":
        entry["proof_obligation_digests"] = []
    elif change == "digest_reorder":
        entry["proof_obligation_digests"] = ["0" * 64]
    elif change == "clause_changed":
        entry["proof_obligations"][0]["required_outcome"] = "Weakened clause"
    elif change == "anchor_missing":
        entry["criteria_sources"] = []
    elif change == "unassociated":
        entry["execution_commission_state"] = "EXECUTION_COMMISSION_NOT_ASSOCIATED"
    elif change == "objective_mismatch":
        entry["current_intent_text"] = "A different request"
    elif change == "unresolved":
        entry["correction_state"] = "UNRESOLVED"
    elif change == "duplicate_clause":
        entry["proof_obligations"] *= 2
        entry["proof_obligation_digests"] *= 2
    else:
        entry["invented_override"] = True
    restamp(entry)
    with pytest.raises(owner.ProductAcceptanceBasisUnavailable):
        expected(read)


def test_read_is_detached_and_parser_candidate_remains_unverified():
    read = acquired_basis()
    before = copy.deepcopy(read.entry)
    selected = expected(read)
    assert read.entry == before
    assert len(selected.criterion_digests) == len(selected.obligation_digests) == 1
    assert not hasattr(selected, "accepted")
