"""Independent Task 2 integration fence; #656 retains its source-file custody.

Explicitly blocked/skipped while the candidate builder is absent from protected
source. Once present, missing/malformed Git identity must fail closed. This is
not proof that a skipped source-grounding dependency is complete.
"""
from __future__ import annotations

import dataclasses
import pytest

from control_plane.executive_runtime import StateConflict
from control_plane.operator_continuation import OperatorContinuationError
from test_operator_continuation_events import _journey


@pytest.fixture
def source_builder():
    return pytest.importorskip(
        "control_plane.operator_continuation_sources",
        reason="SOURCE_GROUNDING_GATE: PR #656 is not integrated",
    )


def _inputs(tmp_path, builder):
    runtime, port, draft = _journey(tmp_path)
    refs = builder.ContinuationExternalRefs(**{
        key: getattr(draft, key) for key in (
            "operation_key", "target_seat", "session_alias", "source_authority_refs",
            "agentos_refs", "github_state", "slack_dialogue_ref", "accepted_ruling_refs",
            "source_revisions",
        )
    })
    return runtime, draft, refs


def test_source_builder_accepts_full_git_identity(tmp_path, source_builder):
    runtime, draft, refs = _inputs(tmp_path, source_builder)
    rebuilt = source_builder.build_current_continuation_draft(
        runtime, source_attempt_id=draft.source_attempt_id,
        target_attempt_id=draft.target_attempt_id, refs=refs,
    )
    assert rebuilt.to_dict() == draft.to_dict()


@pytest.mark.parametrize("github_state", [{}, {"head_sha": "not-a-git-id"}])
def test_source_builder_refuses_missing_or_malformed_git_identity(tmp_path, source_builder, github_state):
    runtime, draft, refs = _inputs(tmp_path, source_builder)
    with pytest.raises((StateConflict, OperatorContinuationError)):
        source_builder.build_current_continuation_draft(
            runtime, source_attempt_id=draft.source_attempt_id,
            target_attempt_id=draft.target_attempt_id,
            refs=dataclasses.replace(refs, github_state=github_state),
        )
