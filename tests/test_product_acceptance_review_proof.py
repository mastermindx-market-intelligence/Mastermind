"""Structural proof consistency is neither issuance nor a product verdict."""

import copy
import pytest

from common.product_acceptance_contract import (
    ProductAcceptanceContractError,
    validate_product_acceptance_review_proof,
    require_complete_product_acceptance_review_proof,
)


def proof():
    return {
        "schema": "mastermind.product_acceptance_review_proof.v1",
        "acceptance_basis_digest": "a" * 64,
        "criteria": [
            {
                "criterion_digest": "b" * 64,
                "state": "SATISFIED",
                "evidence_digests": ["c" * 64],
            }
        ],
        "obligations": [
            {
                "obligation_digest": "d" * 64,
                "state": "SATISFIED",
                "evidence_digests": ["c" * 64],
            },
            {
                "obligation_digest": "e" * 64,
                "state": "SATISFIED",
                "evidence_digests": ["f" * 64],
            },
        ],
    }


def complete(value):
    return require_complete_product_acceptance_review_proof(
        value,
        expected_basis_digest="a" * 64,
        expected_criterion_digests=("b" * 64,),
        expected_obligation_digests=("d" * 64, "e" * 64),
    )


def test_complete_structural_proof_is_detached_without_a_verdict():
    original = proof()
    value = complete(original)
    assert value == original
    value["criteria"][0]["evidence_digests"].clear()
    assert original["criteria"][0]["evidence_digests"] == ["c" * 64]
    assert "accepted" not in value


@pytest.mark.parametrize("state", ["UNPROVEN", "UNSATISFIED"])
def test_declared_non_satisfaction_is_valid_data_but_not_complete(state):
    value = proof()
    value["obligations"][1]["state"] = state
    assert validate_product_acceptance_review_proof(value) == value
    with pytest.raises(ProductAcceptanceContractError):
        complete(value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(accepted=True),
        lambda p: p.update(acceptance_basis_digest=True),
        lambda p: p["criteria"][0].update(state="APPROVED"),
        lambda p: p["criteria"][0].update(evidence_digests=[]),
        lambda p: p["criteria"].append(copy.deepcopy(p["criteria"][0])),
        lambda p: p["obligations"][0].update(obligation_digest="forged"),
        lambda p: p["obligations"][0].update(evidence_digests=["c" * 64, "c" * 64]),
        lambda p: p["obligations"][0].update(accepted=True),
        lambda p: p["obligations"].clear(),
    ],
)
def test_malformed_or_verdict_bearing_proof_is_refused(mutation):
    value = proof()
    mutation(value)
    with pytest.raises(ProductAcceptanceContractError):
        validate_product_acceptance_review_proof(value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["obligations"].pop(),
        lambda p: p["obligations"].reverse(),
        lambda p: p.update(acceptance_basis_digest="9" * 64),
        lambda p: p["criteria"][0].update(criterion_digest="9" * 64),
    ],
)
def test_missing_must_have_wrong_basis_or_wrong_identity_cannot_be_complete(mutation):
    value = proof()
    mutation(value)
    assert validate_product_acceptance_review_proof(value)
    with pytest.raises(ProductAcceptanceContractError):
        complete(value)


def test_full_46_source_obligations_require_individual_evidence():
    value = proof()
    digests = tuple(f"{i:064x}" for i in range(46))
    criterion_digests = tuple(f"{100+i:064x}" for i in range(6))
    value["criteria"] = [
        {
            "criterion_digest": digest,
            "state": "SATISFIED",
            "evidence_digests": ["f" * 64],
        }
        for digest in criterion_digests
    ]
    value["obligations"] = [
        {
            "obligation_digest": digest,
            "state": "SATISFIED",
            "evidence_digests": ["f" * 64],
        }
        for digest in digests
    ]
    assert (
        require_complete_product_acceptance_review_proof(
            value,
            expected_basis_digest="a" * 64,
            expected_criterion_digests=criterion_digests,
            expected_obligation_digests=digests,
        )
        == value
    )
    value["obligations"][30]["state"] = "UNPROVEN"
    with pytest.raises(ProductAcceptanceContractError) as failed:
        require_complete_product_acceptance_review_proof(
            value,
            expected_basis_digest="a" * 64,
            expected_criterion_digests=criterion_digests,
            expected_obligation_digests=digests,
        )
    assert failed.value.repair_identity == digests[30]
    assert failed.value.repair_kind == "UNPROVEN"
