"""Use Agent OS's canonical digest format at both acquisition boundaries."""
import dataclasses

import pytest

from common.commission_ref import normalize_commission_ref
from control_plane import agentos_product_acceptance_basis as owner
from tests.test_product_acceptance_basis_continuity import acquired_basis


# Actual compiler provenance format, verified against protected Macro402b57de.
RECORD_DIGEST = "sha256:b9143527b04bdc452a544dc83c2e6499c16b7f771c8c7289ba30cf47cce5194d"


def select(digest):
    basis = acquired_basis()
    entry = basis.entry
    bundle = {"schema": "context_bundle.v1", "repo_sha": basis.macro_commit,
        "source_records_digest": digest, "target": {"workstream": entry["workstream"]},
        "acceptance_basis": {"schema": "agentos.acceptance_basis.v1", "authoritative": False,
                             "by_commission": {entry["commission_id"]: entry}}}
    return owner.AgentOsProductAcceptanceBasisReader._select(bundle,
        expected_sha=basis.macro_commit, work_ref=entry["workstream"],
        execution_ref=normalize_commission_ref(entry["execution_commission_refs"][0]),
        root_objective=entry["current_intent_text"])


def test_selection_preserves_owner_prefixed_record_digest():
    observed = select(RECORD_DIGEST)
    assert observed.source_records_digest == RECORD_DIGEST


def test_continuity_accepts_the_same_owner_prefixed_record_digest():
    basis = dataclasses.replace(acquired_basis(), source_records_digest=RECORD_DIGEST)
    result = owner.reconcile_unchanged_acceptance_basis(basis, basis)
    assert result.disposition == "UNCHANGED_SOURCE"


@pytest.mark.parametrize("digest", [
    RECORD_DIGEST.removeprefix("sha256:"), "SHA256:" + "b" * 64,
    "sha256:" + "B" * 64, "sha256:" + "b" * 63,
    RECORD_DIGEST + "\n", None,
])
def test_noncanonical_digest_cannot_enter_either_acquisition_boundary(digest):
    with pytest.raises(owner.ProductAcceptanceBasisUnavailable, match="CONTEXT_OWNER_UNAVAILABLE"):
        select(digest)
    basis = dataclasses.replace(acquired_basis(), source_records_digest=digest)
    with pytest.raises(owner.ProductAcceptanceBasisUnavailable,
                       match="SOURCE_REVISION_RECONCILIATION_REQUIRED"):
        owner.reconcile_unchanged_acceptance_basis(basis, basis)
