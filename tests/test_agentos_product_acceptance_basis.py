"""Refusal/source-data checks; these do not enroll or qualify an installed host."""

import hashlib
import subprocess
from types import SimpleNamespace

import pytest

from common.commission_ref import normalize_commission_ref
from control_plane import agentos_product_acceptance_basis as owner


def execution_ref():
    return normalize_commission_ref(
        {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "a" * 40,
            "path": "research/executive_commissions/COMMISSION.md",
            "content_sha256": "b" * 64,
        }
    )


def declaration(*, associated=True):
    source = {
        "repository": "mastermindx-market-intelligence/macro",
        "commit": "c" * 40,
        "path": "agentos/workstreams/CHAIRMAN-CONTROL-ROOM.md",
        "content_sha256": "d" * 64,
    }
    entry = {
        "commission_id": "r2-test",
        "workstream": "WS:CHAIRMAN-CONTROL-ROOM",
        "source_state": "CURRENT",
        "execution_commission_refs": [execution_ref().to_dict()] if associated else [],
        "current_intent_text": "The actual objective",
        "criteria_objective": "The actual objective",
        "criteria_objective_sha256": hashlib.sha256(
            b"The actual objective"
        ).hexdigest(),
        "source_record_ref": source,
        "current_intent_ref": dict(source),
    }
    entry["acceptance_basis_digest"] = owner._canonical_digest(entry)
    return {
        "schema": "context_bundle.v1",
        "repo_sha": "c" * 40,
        "source_records_digest": "sha256:" + "e" * 64,
        "target": {"workstream": "WS:CHAIRMAN-CONTROL-ROOM"},
        "acceptance_basis": {
            "schema": "agentos.acceptance_basis.v1",
            "authoritative": False,
            "by_commission": {"r2-test": entry},
        },
    }


def test_identical_text_cannot_replace_an_explicit_execution_association():
    with pytest.raises(
        owner.ProductAcceptanceBasisUnavailable,
        match="EXECUTION_COMMISSION_NOT_ASSOCIATED",
    ):
        owner.AgentOsProductAcceptanceBasisReader._select(
            declaration(associated=False),
            expected_sha="c" * 40,
            work_ref="WS:CHAIRMAN-CONTROL-ROOM",
            execution_ref=execution_ref(),
            root_objective="The actual objective",
        )


def test_wrong_original_ask_is_rejected_even_for_a_matching_commission_ref():
    with pytest.raises(
        owner.ProductAcceptanceBasisUnavailable, match="BASIS_CURRENT_INTENT_UNPROVEN"
    ):
        owner.AgentOsProductAcceptanceBasisReader._select(
            declaration(),
            expected_sha="c" * 40,
            work_ref="WS:CHAIRMAN-CONTROL-ROOM",
            execution_ref=execution_ref(),
            root_objective="A replacement ask",
        )


def test_unpublished_source_declaration_is_not_a_current_basis():
    value = declaration()
    entry = value["acceptance_basis"]["by_commission"]["r2-test"]
    entry["source_state"] = "UNKNOWN"
    entry["acceptance_basis_digest"] = owner._canonical_digest(
        {k: v for k, v in entry.items() if k != "acceptance_basis_digest"}
    )
    with pytest.raises(
        owner.ProductAcceptanceBasisUnavailable, match="BASIS_CURRENT_INTENT_UNPROVEN"
    ):
        owner.AgentOsProductAcceptanceBasisReader._select(
            value,
            expected_sha="c" * 40,
            work_ref="WS:CHAIRMAN-CONTROL-ROOM",
            execution_ref=execution_ref(),
            root_objective="The actual objective",
        )


def test_unqualified_sealed_context_profile_stops_before_helper(monkeypatch, tmp_path):
    reader = owner.AgentOsProductAcceptanceBasisReader(macro_root=tmp_path)
    before = sorted(tmp_path.rglob("*"))

    def forbidden(*args, **kwargs):
        raise AssertionError("unqualified profile reached source helper")

    monkeypatch.setattr(owner, "git_sha", forbidden)
    monkeypatch.setattr(owner, "bounded_subprocess_runner", forbidden)
    monkeypatch.setattr(
        owner, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1, no_site=1))
    )
    with pytest.raises(
        owner.ProductAcceptanceBasisUnavailable, match="CONTEXT_RUNTIME_UNQUALIFIED"
    ):
        reader.read(
            work_ref="WS:CHAIRMAN-CONTROL-ROOM",
            execution_commission_ref=execution_ref(),
            root_objective="The actual objective",
        )
    assert sorted(tmp_path.rglob("*")) == before


def test_actual_legacy_cli_cannot_substitute_an_orientation_packet(tmp_path):
    # A tiny source fixture supplies a real HEAD. The actual protected CLI has
    # no --workstream API; it must not fall back to its ordinary fail-open brief.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "read-only source fixture",
        ],
        check=True,
    )
    before = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    reader = owner.AgentOsProductAcceptanceBasisReader(macro_root=tmp_path)
    with pytest.raises(
        owner.ProductAcceptanceBasisUnavailable, match="CONTEXT_OWNER_UNAVAILABLE"
    ):
        reader.read(
            work_ref="WS:CHAIRMAN-CONTROL-ROOM",
            execution_commission_ref=execution_ref(),
            root_objective="The actual objective",
        )
    assert {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    } == before
