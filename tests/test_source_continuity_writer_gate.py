"""RCH-1A stage 1 — technical writer-gate verifier (evidence only).

These tests pin the deterministic classification of one operation branch's
GitHub ref enforcement: `TECHNICAL_WRITER_GATE_ACTIVE` only when active
`update` + `deletion` + `non_fast_forward` rules cover the branch, creation is
not restricted, and the only bypass is the one accepted source-writer
integration. Everything else is `TECHNICAL_WRITER_GATE_UNAVAILABLE` with a
closed defect set, or a fixed refusal. The receipt never authorizes release,
fence, merge or transfer.
"""
from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import quote

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "control_plane" / "source_continuity.py"
CLI_PATH = ROOT / "scripts" / "source_continuity.py"
SESSION_CLOSE_PATH = ROOT / "docs" / "AGENT_DIALOGUE_SESSION_CLOSE_LAW.md"
REVIEW_RETURN_PATH = ROOT / "docs" / "sol_skills" / "REVIEW_RETURN.md"

API_ROOT = "https://api.github.com"
TOKEN = "ghp_writer_gate_probe_token"
OPERATION = "agent-dialogue-checkpoint-abandonment-writer-fence-rch1a-20260903-sol-001"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
ORG = "mastermindx-market-intelligence"
BRANCH = "sol/web-source-continuity-high-churn-semantic-revalidation-20260916-sol-001"
HEAD_SHA = "7bee35e6787ad3001daf99835fa62f8240c2de79"
VERIFIED_AT = "2026-09-16T23:00:00Z"
ACCEPTED_APP = 987654
OTHER_APP = 111111
REPO_RULESET = 22852988
ORG_RULESET = 33333333


def _contract():
    name = "source_continuity_writer_gate_contract_under_test"
    spec = importlib.util.spec_from_file_location(name, CONTRACT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CLI_MODULE_NAME = "source_continuity_writer_gate_cli_under_test"


def _cli_module():
    name = CLI_MODULE_NAME
    spec = importlib.util.spec_from_file_location(name, CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _request(module, **overrides):
    values = {
        "operation_key": OPERATION,
        "repository": REPOSITORY,
        "branch": BRANCH,
        "accepted_integration_id": ACCEPTED_APP,
        "verified_at": VERIFIED_AT,
    }
    values.update(overrides)
    return module.WriterGateRequest(**values)


def _actor(module, *, actor_type="Integration", actor_id=ACCEPTED_APP, bypass_mode="always"):
    return module.BypassActorFact(
        actor_type=actor_type,
        actor_id=actor_id,
        bypass_mode=bypass_mode,
    )


def _ruleset(module, *, ruleset_id=REPO_RULESET, source_type="Repository", enforcement="active", bypass_actors=None):
    return module.RulesetFact(
        ruleset_id=ruleset_id,
        source_type=source_type,
        enforcement=enforcement,
        bypass_actors=(_actor(module),) if bypass_actors is None else bypass_actors,
    )


def _rules(module, *types, ruleset_id=REPO_RULESET, source_type="Repository"):
    return tuple(
        module.BranchRuleFact(
            rule_type=rule_type,
            ruleset_id=ruleset_id,
            ruleset_source_type=source_type,
        )
        for rule_type in types
    )


def _active_facts(module, **overrides):
    values = {
        "repository": REPOSITORY,
        "branch": BRANCH,
        "branch_head_sha": HEAD_SHA,
        "legacy_branch_protected": False,
        "branch_rules": _rules(module, "update", "deletion", "non_fast_forward"),
        "rulesets": (_ruleset(module),),
        "readback_complete": True,
    }
    values.update(overrides)
    return module.WriterGateFacts(**values)


def _verify(module, *, request=None, facts=None):
    return module.verify_technical_writer_gate(
        request or _request(module),
        facts or _active_facts(module),
    )


def _assert_refusal(module, result, code: str, *, exit_code: int):
    assert isinstance(result, module.SourceContinuityRefusal)
    assert result.code is module.RefusalCode[code]
    assert result.exit_code == exit_code
    payload = result.to_dict()
    assert payload == {
        "schema": module.REFUSAL_SCHEMA,
        "ok": False,
        "code": code,
        "message": module.REFUSAL_MESSAGES[module.RefusalCode[code]],
    }


def _assert_unavailable(module, result, *defects: str):
    assert isinstance(result, module.WriterGateReceipt)
    payload = result.to_dict()
    assert payload["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert payload["defects"] == sorted(defects)
    assert payload["authority_effect"] == "NONE"
    assert payload["writer_release_authorized"] is False
    assert payload["fence_authorized"] is False
    assert payload["merge_authorized"] is False
    assert payload["receiver_transfer_authorized"] is False
    return payload


# --- pure verifier ----------------------------------------------------------


def test_active_gate_receipt_binds_identity_without_authority() -> None:
    module = _contract()
    result = _verify(module)

    assert isinstance(result, module.WriterGateReceipt)
    payload = result.to_dict()
    digest = payload.pop("receipt_digest")
    assert payload == {
        "schema": "mastermind.source_continuity_writer_gate/v1",
        "receipt_version": "v1",
        "operation_key": OPERATION,
        "repository": REPOSITORY,
        "branch": BRANCH,
        "branch_head_sha": HEAD_SHA,
        "legacy_branch_protected": False,
        "accepted_integration_id": ACCEPTED_APP,
        "enforcing_ruleset_ids": [REPO_RULESET],
        "rule_types": ["deletion", "non_fast_forward", "update"],
        "bypass_actors": [
            {"actor_type": "Integration", "actor_id": ACCEPTED_APP, "bypass_mode": "always"}
        ],
        "defects": [],
        "state": "TECHNICAL_WRITER_GATE_ACTIVE",
        "verified_at": VERIFIED_AT,
        "authority_effect": "NONE",
        "writer_release_authorized": False,
        "fence_authorized": False,
        "merge_authorized": False,
        "receiver_transfer_authorized": False,
    }
    assert len(digest) == 64 and int(digest, 16) >= 0
    assert result.writer_release_authorized is False
    assert result.fence_authorized is False


def test_receipt_digest_is_canonical_and_input_order_independent() -> None:
    module = _contract()
    forward = _verify(module)
    reordered = _verify(
        module,
        facts=_active_facts(
            module,
            branch_rules=_rules(module, "non_fast_forward", "deletion", "update"),
        ),
    )
    assert isinstance(forward, module.WriterGateReceipt)
    assert isinstance(reordered, module.WriterGateReceipt)
    assert forward.to_dict() == reordered.to_dict()
    payload = forward.to_dict()
    digest = payload.pop("receipt_digest")
    assert digest == module._digest(payload)
    assert json.loads(module.canonical_json(forward.to_dict())) == forward.to_dict()


def test_real_estate_shape_with_no_branch_rules_is_unavailable_rules_absent() -> None:
    # Mirrors the live 2026-09-16 readback of the released #707 branch:
    # protected=false, /rules/branches/<branch> == [].
    module = _contract()
    result = _verify(
        module,
        request=_request(module, accepted_integration_id=None),
        facts=_active_facts(module, branch_rules=(), rulesets=()),
    )
    payload = _assert_unavailable(module, result, "RULES_ABSENT")
    assert payload["enforcing_ruleset_ids"] == []
    assert payload["rule_types"] == []
    assert payload["bypass_actors"] == []
    assert payload["accepted_integration_id"] is None


def test_merge_queue_only_ruleset_does_not_count_as_a_writer_gate() -> None:
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(
            module,
            branch_rules=_rules(module, "merge_queue", "branch_name_pattern"),
            rulesets=(_ruleset(module, bypass_actors=()),),
        ),
    )
    payload = _assert_unavailable(module, result, "RULES_ABSENT")
    assert payload["enforcing_ruleset_ids"] == []
    assert payload["rule_types"] == []


def test_legacy_branch_protection_alone_never_satisfies_the_gate() -> None:
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(
            module,
            legacy_branch_protected=True,
            branch_rules=(),
            rulesets=(),
        ),
    )
    payload = _assert_unavailable(
        module, result, "LEGACY_PROTECTION_PRESENT", "RULES_ABSENT"
    )
    assert payload["legacy_branch_protected"] is True


@pytest.mark.parametrize(
    ("present", "expected"),
    [
        (("update", "deletion"), ("NON_FAST_FORWARD_RULE_MISSING",)),
        (("update", "non_fast_forward"), ("DELETION_RULE_MISSING",)),
        (("deletion", "non_fast_forward"), ("UPDATE_RULE_MISSING",)),
        (("non_fast_forward",), ("UPDATE_RULE_MISSING", "DELETION_RULE_MISSING")),
    ],
)
def test_each_required_rule_is_reported_when_missing(present, expected) -> None:
    module = _contract()
    result = _verify(module, facts=_active_facts(module, branch_rules=_rules(module, *present)))
    _assert_unavailable(module, result, *expected)


def test_force_push_and_delete_only_rules_still_let_every_account_fast_forward() -> None:
    # The RCH-1A freeze: a ruleset that only blocks force-push/deletion is insufficient.
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(module, branch_rules=_rules(module, "deletion", "non_fast_forward")),
    )
    _assert_unavailable(module, result, "UPDATE_RULE_MISSING")


def test_creation_restriction_is_a_defect_because_workers_must_still_open_branches() -> None:
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(
            module,
            branch_rules=_rules(module, "creation", "update", "deletion", "non_fast_forward"),
        ),
    )
    payload = _assert_unavailable(module, result, "CREATION_RESTRICTED")
    assert payload["rule_types"] == ["creation", "deletion", "non_fast_forward", "update"]


@pytest.mark.parametrize("enforcement", ["evaluate", "disabled"])
def test_non_active_enforcement_is_unavailable(enforcement: str) -> None:
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(module, rulesets=(_ruleset(module, enforcement=enforcement),)),
    )
    _assert_unavailable(module, result, "ENFORCEMENT_NOT_ACTIVE")


@pytest.mark.parametrize(
    "extra",
    [
        ("OrganizationAdmin", 1, "always"),
        ("RepositoryRole", 5, "always"),
        ("Team", 4242, "always"),
        ("DeployKey", None, "always"),
        ("Integration", OTHER_APP, "always"),
        ("Integration", OTHER_APP, "pull_request"),
        ("SomethingNew", 7, "always"),
    ],
)
def test_any_bypass_actor_other_than_the_accepted_integration_widens_the_gate(extra) -> None:
    module = _contract()
    actor_type, actor_id, bypass_mode = extra
    result = _verify(
        module,
        facts=_active_facts(
            module,
            rulesets=(
                _ruleset(
                    module,
                    bypass_actors=(
                        _actor(module),
                        _actor(module, actor_type=actor_type, actor_id=actor_id, bypass_mode=bypass_mode),
                    ),
                ),
            ),
        ),
    )
    payload = _assert_unavailable(module, result, "BYPASS_WIDENED")
    assert {"actor_type": actor_type, "actor_id": actor_id, "bypass_mode": bypass_mode} in payload[
        "bypass_actors"
    ]


def test_bypass_actor_list_is_sorted_and_duplicate_free_in_the_receipt() -> None:
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(
            module,
            branch_rules=_rules(module, "update", "deletion", "non_fast_forward")
            + _rules(module, "deletion", ruleset_id=ORG_RULESET, source_type="Organization"),
            rulesets=(
                _ruleset(module),
                _ruleset(module, ruleset_id=ORG_RULESET, source_type="Organization"),
            ),
        ),
    )
    assert isinstance(result, module.WriterGateReceipt)
    payload = result.to_dict()
    assert payload["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
    assert payload["enforcing_ruleset_ids"] == [REPO_RULESET, ORG_RULESET]
    assert payload["bypass_actors"] == [
        {"actor_type": "Integration", "actor_id": ACCEPTED_APP, "bypass_mode": "always"}
    ]


def test_no_accepted_integration_means_owner_mediation_is_absent() -> None:
    module = _contract()
    result = _verify(
        module,
        request=_request(module, accepted_integration_id=None),
        facts=_active_facts(module, rulesets=(_ruleset(module, bypass_actors=()),)),
    )
    _assert_unavailable(module, result, "OWNER_INTEGRATION_ABSENT")


def test_accepted_integration_declared_but_not_bypassing_update_is_absent_mediation() -> None:
    module = _contract()
    result = _verify(module, facts=_active_facts(module, rulesets=(_ruleset(module, bypass_actors=()),)))
    _assert_unavailable(module, result, "OWNER_INTEGRATION_ABSENT")


def test_accepted_integration_with_pull_request_bypass_cannot_mediate_a_fence_push() -> None:
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(
            module,
            rulesets=(_ruleset(module, bypass_actors=(_actor(module, bypass_mode="pull_request"),)),),
        ),
    )
    _assert_unavailable(
        module,
        result,
        "BYPASS_WIDENED",
        "OWNER_INTEGRATION_ABSENT",
    )


def test_accepted_integration_must_bypass_every_ruleset_that_restricts_update() -> None:
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(
            module,
            branch_rules=_rules(module, "update", "deletion", "non_fast_forward")
            + _rules(module, "update", ruleset_id=ORG_RULESET, source_type="Organization"),
            rulesets=(
                _ruleset(module),
                _ruleset(module, ruleset_id=ORG_RULESET, source_type="Organization", bypass_actors=()),
            ),
        ),
    )
    _assert_unavailable(module, result, "OWNER_INTEGRATION_ABSENT")


def test_defects_accumulate_rather_than_short_circuit() -> None:
    module = _contract()
    result = _verify(
        module,
        request=_request(module, accepted_integration_id=None),
        facts=_active_facts(
            module,
            branch_rules=_rules(module, "creation", "non_fast_forward"),
            rulesets=(
                _ruleset(
                    module,
                    enforcement="evaluate",
                    bypass_actors=(_actor(module, actor_type="OrganizationAdmin", actor_id=1),),
                ),
            ),
        ),
    )
    _assert_unavailable(
        module,
        result,
        "UPDATE_RULE_MISSING",
        "DELETION_RULE_MISSING",
        "CREATION_RESTRICTED",
        "ENFORCEMENT_NOT_ACTIVE",
        "BYPASS_WIDENED",
        "OWNER_INTEGRATION_ABSENT",
    )


def test_referenced_ruleset_without_readback_is_an_incomplete_census() -> None:
    module = _contract()
    missing = _verify(module, facts=_active_facts(module, rulesets=()))
    _assert_refusal(module, missing, "REMOTE_CENSUS_INCOMPLETE", exit_code=2)

    flagged = _verify(module, facts=_active_facts(module, readback_complete=False))
    _assert_refusal(module, flagged, "REMOTE_CENSUS_INCOMPLETE", exit_code=2)


def test_identity_mismatch_refuses_before_classification() -> None:
    module = _contract()
    wrong_repo = _verify(module, facts=_active_facts(module, repository="other/repo"))
    _assert_refusal(module, wrong_repo, "REMOTE_IDENTITY_MISMATCH", exit_code=2)
    wrong_branch = _verify(module, facts=_active_facts(module, branch="sol/other"))
    _assert_refusal(module, wrong_branch, "REMOTE_IDENTITY_MISMATCH", exit_code=2)


@pytest.mark.parametrize(
    "overrides",
    [
        {"operation_key": "x"},
        {"operation_key": "bad key with spaces"},
        {"repository": "not-a-repository"},
        {"repository": "a/../b"},
        {"branch": "HEAD"},
        {"branch": "refs/heads/../x"},
        {"accepted_integration_id": 0},
        {"accepted_integration_id": -1},
        {"accepted_integration_id": True},
        {"accepted_integration_id": "987654"},
        {"accepted_integration_id": 2**31},
        {"verified_at": "2026-09-16 23:00:00"},
        {"verified_at": "2026-13-40T00:00:00Z"},
    ],
)
def test_hostile_request_shapes_refuse(overrides) -> None:
    module = _contract()
    result = _verify(module, request=_request(module, **overrides))
    _assert_refusal(module, result, "INVALID_REQUEST", exit_code=2)


def test_non_request_object_refuses() -> None:
    module = _contract()
    result = module.verify_technical_writer_gate(object(), _active_facts(module))
    _assert_refusal(module, result, "INVALID_REQUEST", exit_code=2)


def _hostile_facts_cases(module):
    good_rule = module.BranchRuleFact(
        rule_type="update", ruleset_id=REPO_RULESET, ruleset_source_type="Repository"
    )
    return [
        object(),
        _active_facts(module, branch_head_sha="not-a-sha"),
        _active_facts(module, legacy_branch_protected="false"),
        _active_facts(module, readback_complete=1),
        _active_facts(module, branch_rules=[good_rule]),
        _active_facts(module, branch_rules=(object(),)),
        _active_facts(
            module,
            branch_rules=(
                replace(good_rule, rule_type=""),
                *_rules(module, "deletion", "non_fast_forward"),
            ),
        ),
        _active_facts(
            module,
            branch_rules=(
                replace(good_rule, ruleset_id=0),
                *_rules(module, "deletion", "non_fast_forward"),
            ),
        ),
        _active_facts(
            module,
            branch_rules=(
                replace(good_rule, ruleset_id=True),
                *_rules(module, "deletion", "non_fast_forward"),
            ),
        ),
        _active_facts(
            module,
            branch_rules=(
                replace(good_rule, ruleset_source_type="Enterprise"),
                *_rules(module, "deletion", "non_fast_forward"),
            ),
        ),
        _active_facts(module, branch_rules=_rules(module, "update", "update", "deletion", "non_fast_forward")),
        _active_facts(module, rulesets=[_ruleset(module)]),
        _active_facts(module, rulesets=(_ruleset(module), _ruleset(module))),
        _active_facts(module, rulesets=(_ruleset(module, enforcement="on"),)),
        _active_facts(module, rulesets=(_ruleset(module, source_type="Enterprise"),)),
        _active_facts(module, rulesets=(_ruleset(module, source_type="Organization"),)),
        _active_facts(module, rulesets=(_ruleset(module, bypass_actors=[_actor(module)]),)),
        _active_facts(module, rulesets=(_ruleset(module, bypass_actors=(object(),)),)),
        _active_facts(module, rulesets=(_ruleset(module, bypass_actors=(_actor(module, actor_type=""),)),)),
        _active_facts(module, rulesets=(_ruleset(module, bypass_actors=(_actor(module, actor_id=True),)),)),
        _active_facts(module, rulesets=(_ruleset(module, bypass_actors=(_actor(module, actor_id="1"),)),)),
        _active_facts(module, rulesets=(_ruleset(module, bypass_actors=(_actor(module, bypass_mode="sometimes"),)),)),
        _active_facts(module, rulesets=(_ruleset(module, bypass_actors=(_actor(module), _actor(module))),)),
    ]


def test_hostile_facts_shapes_refuse() -> None:
    module = _contract()
    cases = _hostile_facts_cases(module)
    assert len(cases) == 23
    for facts in cases:
        result = module.verify_technical_writer_gate(_request(module), facts)
        _assert_refusal(module, result, "REMOTE_FACTS_INVALID", exit_code=2)


def test_receipt_digest_moves_when_gate_identity_moves() -> None:
    module = _contract()
    baseline = _verify(module)
    moved_head = _verify(module, facts=_active_facts(module, branch_head_sha="9" * 40))
    moved_bypass = _verify(
        module,
        facts=_active_facts(
            module,
            rulesets=(_ruleset(module, bypass_actors=(_actor(module), _actor(module, actor_id=OTHER_APP))),),
        ),
    )
    digests = {
        result.to_dict()["receipt_digest"]
        for result in (baseline, moved_head, moved_bypass)
    }
    assert len(digests) == 3


# --- adapter ----------------------------------------------------------------


def _rules_endpoint(branch: str = BRANCH) -> str:
    return f"repos/{REPOSITORY}/rules/branches/{quote(branch, safe='')}"


def _branch_endpoint(branch: str = BRANCH) -> str:
    return f"repos/{REPOSITORY}/branches/{quote(branch, safe='')}"


def _protection_endpoint(branch: str = BRANCH) -> str:
    return f"repos/{REPOSITORY}/branches/{quote(branch, safe='')}/protection"


class _MissingResource(Exception):
    """A foreign 404 signal: marked absent, but not the adapter's own class.

    Used for the optional classic-protection readback so the tests also prove
    the marker-attribute protocol admits a transport that raises its own type.
    A required endpoint uses `_cli_missing_error()` instead, because there the
    contract under test is the real transport's.
    """

    source_continuity_resource_missing = True


def _cli_attr(name: str):
    """An attribute of the exact CLI module object under test.

    `_cli_module()` re-executes the module per test, so the fake transport must
    resolve these when it is called, never from an earlier execution.
    """

    return getattr(sys.modules[CLI_MODULE_NAME], name)


def _cli_probe_error() -> type[BaseException]:
    return _cli_attr("_RemoteProbeError")


def _cli_missing_error() -> type[BaseException]:
    return _cli_attr("_RemoteResourceMissing")


class _GateHTTP:
    """Endpoint-keyed fake of authenticated GitHub GETs for the writer gate."""

    def __init__(
        self,
        *,
        rules=None,
        rulesets=None,
        org_rulesets=None,
        branch=None,
        move_rules_on_second_read: bool = False,
        protection=None,
        protection_unreadable: bool = False,
        protection_on_second_read=None,
        protection_absent_on_second_read: bool = False,
        missing_endpoints=(),
    ) -> None:
        self.calls: list[tuple[str, str, float]] = []
        self.rules = [] if rules is None else rules
        self.rulesets = {} if rulesets is None else rulesets
        self.org_rulesets = {} if org_rulesets is None else org_rulesets
        self.branch = branch or {"commit": {"sha": HEAD_SHA}, "protected": False}
        self.move_rules_on_second_read = move_rules_on_second_read
        self.protection = protection
        self.protection_unreadable = protection_unreadable
        self.protection_on_second_read = protection_on_second_read
        self.protection_absent_on_second_read = protection_absent_on_second_read
        self.missing_endpoints = frozenset(missing_endpoints)
        self.rules_reads = 0
        self.protection_reads = 0

    def _classic_protection(self):
        self.protection_reads += 1
        if self.protection_unreadable:
            raise _cli_probe_error()()
        current = self.protection
        if self.protection_reads > 1:
            if self.protection_on_second_read is not None:
                current = self.protection_on_second_read
            elif self.protection_absent_on_second_read:
                current = None
        if current is None:
            raise _MissingResource()
        return current

    def __call__(self, url: str, *, token: str, timeout: float):
        self.calls.append((url, token, timeout))
        assert url.startswith(API_ROOT + "/")
        assert token == TOKEN
        assert TOKEN not in url
        endpoint = url.removeprefix(API_ROOT + "/")
        if endpoint in self.missing_endpoints:
            raise _cli_missing_error()()
        if endpoint == _branch_endpoint():
            return self.branch
        if endpoint == _protection_endpoint():
            return self._classic_protection()
        if endpoint == _rules_endpoint():
            self.rules_reads += 1
            if self.move_rules_on_second_read and self.rules_reads > 1:
                return []
            return self.rules
        for ruleset_id, payload in self.rulesets.items():
            if endpoint == f"repos/{REPOSITORY}/rulesets/{ruleset_id}":
                return payload
        for ruleset_id, payload in self.org_rulesets.items():
            if endpoint == f"orgs/{ORG}/rulesets/{ruleset_id}":
                return payload
        raise AssertionError(f"unexpected HTTP probe endpoint: {endpoint}")


def _rule_row(rule_type: str, ruleset_id: int = REPO_RULESET, source_type: str = "Repository") -> dict:
    return {
        "type": rule_type,
        "ruleset_source_type": source_type,
        "ruleset_source": REPOSITORY if source_type == "Repository" else ORG,
        "ruleset_id": ruleset_id,
    }


def _ruleset_row(
    ruleset_id: int = REPO_RULESET,
    *,
    source_type: str = "Repository",
    enforcement: str = "active",
    bypass_actors=None,
) -> dict:
    return {
        "id": ruleset_id,
        "name": "Operation branch writer gate",
        "target": "branch",
        "source_type": source_type,
        "source": REPOSITORY if source_type == "Repository" else ORG,
        "enforcement": enforcement,
        "conditions": {"ref_name": {"include": ["refs/heads/sol/**"], "exclude": []}},
        "rules": [{"type": "update"}, {"type": "deletion"}, {"type": "non_fast_forward"}],
        "bypass_actors": (
            [{"actor_id": ACCEPTED_APP, "actor_type": "Integration", "bypass_mode": "always"}]
            if bypass_actors is None
            else bypass_actors
        ),
        "current_user_can_bypass": "never",
    }


def _active_http(**overrides) -> _GateHTTP:
    values = {
        "rules": [_rule_row("update"), _rule_row("deletion"), _rule_row("non_fast_forward")],
        "rulesets": {REPO_RULESET: _ruleset_row()},
    }
    values.update(overrides)
    return _GateHTTP(**values)


def _argv(*, accepted: int | None = ACCEPTED_APP, branch: str = BRANCH) -> list[str]:
    argv = [
        "writer-gate",
        "--operation-key",
        OPERATION,
        "--repository",
        REPOSITORY,
        "--branch",
        branch,
    ]
    if accepted is not None:
        argv.extend(("--accepted-integration-id", str(accepted)))
    return argv


def _run(module, argv, *, http=None, environ=None, runner=None):
    def forbidden_runner(*_args, **_kwargs):
        raise AssertionError("writer-gate must not execute local Git")

    return module.main(
        argv,
        runner=runner or forbidden_runner,
        http_get=http if http is not None else _active_http(),
        environ=environ if environ is not None else {"GITHUB_TOKEN": TOKEN},
        clock=lambda: VERIFIED_AT,
    )


def test_cli_active_gate_prints_one_receipt_from_read_only_probes(capsys) -> None:
    module = _cli_module()
    http = _active_http()
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert payload["schema"] == "mastermind.source_continuity_writer_gate/v1"
    assert payload["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
    assert payload["defects"] == []
    assert payload["branch_head_sha"] == HEAD_SHA
    assert payload["legacy_branch_protected"] is False
    assert payload["enforcing_ruleset_ids"] == [REPO_RULESET]
    assert payload["accepted_integration_id"] == ACCEPTED_APP
    assert payload["verified_at"] == VERIFIED_AT
    assert payload["writer_release_authorized"] is False
    assert payload["fence_authorized"] is False
    endpoints = [url.removeprefix(API_ROOT + "/") for url, _, _ in http.calls]
    assert endpoints[:4] == [
        _branch_endpoint(),
        _protection_endpoint(),
        _rules_endpoint(),
        f"repos/{REPOSITORY}/rulesets/{REPO_RULESET}",
    ]
    # Second observation re-reads the same facts; nothing else is touched.
    assert set(endpoints) == set(endpoints[:4])
    assert all(TOKEN not in url for url, _, _ in http.calls)


def test_cli_live_estate_shape_is_unavailable_rules_absent(capsys) -> None:
    module = _cli_module()
    exit_code = _run(module, _argv(accepted=None), http=_GateHTTP())
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert payload["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert payload["defects"] == ["RULES_ABSENT"]
    assert payload["accepted_integration_id"] is None
    assert payload["enforcing_ruleset_ids"] == []


def test_cli_reads_organization_rulesets_from_the_organization_endpoint(capsys) -> None:
    module = _cli_module()
    http = _GateHTTP(
        rules=[
            _rule_row("update", ORG_RULESET, "Organization"),
            _rule_row("deletion", ORG_RULESET, "Organization"),
            _rule_row("non_fast_forward", ORG_RULESET, "Organization"),
        ],
        org_rulesets={ORG_RULESET: _ruleset_row(ORG_RULESET, source_type="Organization")},
    )
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert payload["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
    assert payload["enforcing_ruleset_ids"] == [ORG_RULESET]
    endpoints = {url.removeprefix(API_ROOT + "/") for url, _, _ in http.calls}
    assert f"orgs/{ORG}/rulesets/{ORG_RULESET}" in endpoints


def test_cli_widened_bypass_is_reported_not_refused(capsys) -> None:
    module = _cli_module()
    http = _active_http(
        rulesets={
            REPO_RULESET: _ruleset_row(
                bypass_actors=[
                    {"actor_id": ACCEPTED_APP, "actor_type": "Integration", "bypass_mode": "always"},
                    {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"},
                ]
            )
        }
    )
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert payload["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert payload["defects"] == ["BYPASS_WIDENED"]


def test_cli_refuses_if_branch_rules_move_during_the_same_proof(capsys) -> None:
    module = _cli_module()
    exit_code = _run(module, _argv(), http=_active_http(move_rules_on_second_read=True))
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 1
    assert payload == {
        "schema": "mastermind.source_continuity_refusal/v1",
        "ok": False,
        "code": "REMOTE_PROOF_CHANGED",
        "message": "remote proof changed during verification",
    }


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"branch": {"protected": False}}, "REMOTE_PROBE_FAILED"),
        ({"branch": {"commit": {"sha": "nope"}, "protected": False}}, "REMOTE_PROBE_FAILED"),
        ({"branch": {"commit": {"sha": HEAD_SHA}}}, "REMOTE_PROBE_FAILED"),
        ({"rules": {"type": "update"}}, "REMOTE_PROBE_FAILED"),
        ({"rules": [{"type": "update"}]}, "REMOTE_PROBE_FAILED"),
        ({"rules": [_rule_row("update", REPO_RULESET, "Enterprise")]}, "REMOTE_FACTS_INVALID"),
        ({"rulesets": {REPO_RULESET: []}}, "REMOTE_PROBE_FAILED"),
        ({"rulesets": {REPO_RULESET: _ruleset_row(enforcement=None)}}, "REMOTE_PROBE_FAILED"),
        ({"rulesets": {REPO_RULESET: _ruleset_row(bypass_actors=None) | {"bypass_actors": {}}}}, "REMOTE_PROBE_FAILED"),
        ({"rulesets": {REPO_RULESET: _ruleset_row(bypass_actors=[{"actor_type": "Integration"}])}}, "REMOTE_PROBE_FAILED"),
        ({"rulesets": {REPO_RULESET: _ruleset_row(OTHER_APP)}}, "REMOTE_PROBE_FAILED"),
    ],
)
def test_cli_malformed_remote_payloads_use_fixed_value_free_refusals(kwargs, code, capsys) -> None:
    module = _cli_module()
    exit_code = _run(module, _argv(), http=_active_http(**kwargs))
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 2
    assert payload["code"] == code
    assert payload["ok"] is False
    assert HEAD_SHA not in payload["message"]


def test_cli_missing_token_stops_before_any_probe(capsys) -> None:
    module = _cli_module()
    http = _active_http()
    exit_code = _run(module, _argv(), http=http, environ={})
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 2
    assert payload["code"] == "AUTH_UNAVAILABLE"
    assert http.calls == []


@pytest.mark.parametrize(
    "argv",
    [
        ["writer-gate"],
        ["writer-gate", "--operation-key", OPERATION, "--repository", REPOSITORY],
        ["writer-gate", "--operation-key", "x", "--repository", REPOSITORY, "--branch", BRANCH],
        ["writer-gate", "--operation-key", OPERATION, "--repository", "bad", "--branch", BRANCH],
        ["writer-gate", "--operation-key", OPERATION, "--repository", REPOSITORY, "--branch", "HEAD"],
        _argv(accepted=0),
        _argv() + ["--accepted-integration-id", "abc"],
        _argv() + ["--workspace", "/tmp"],
    ],
)
def test_cli_rejects_invalid_requests_before_any_probe(argv, capsys) -> None:
    module = _cli_module()
    http = _active_http()
    exit_code = _run(module, argv, http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 2
    assert payload["code"] == "INVALID_REQUEST"
    assert http.calls == []


def test_cli_auth_and_transport_failures_stay_fixed(capsys) -> None:
    module = _cli_module()

    def auth_failure(url: str, *, token: str, timeout: float):
        raise module._AuthProbeError()

    exit_code = _run(module, _argv(), http=auth_failure)
    assert exit_code == 2
    assert json.loads(capsys.readouterr().out.strip())["code"] == "AUTH_UNAVAILABLE"

    def transport_failure(url: str, *, token: str, timeout: float):
        raise module._RemoteProbeError()

    exit_code = _run(module, _argv(), http=transport_failure)
    assert exit_code == 2
    assert json.loads(capsys.readouterr().out.strip())["code"] == "REMOTE_PROBE_FAILED"


def test_cli_never_invokes_local_git_for_the_writer_gate() -> None:
    module = _cli_module()
    invoked: list[object] = []

    def recording_runner(*args, **kwargs):
        invoked.append((args, kwargs))
        raise AssertionError("unexpected Git invocation")

    exit_code = _run(module, _argv(), runner=recording_runner)
    assert exit_code == 0
    assert invoked == []


def test_existing_verify_command_is_unchanged_by_the_new_subcommand() -> None:
    module = _cli_module()
    parser = module._build_parser()
    namespace = parser.parse_args(_argv())
    assert namespace.command == "writer-gate"
    assert namespace.accepted_integration_id == ACCEPTED_APP
    with pytest.raises((SystemExit, ValueError)):
        parser.parse_args(["verify", "--kind", "checkpoint"])


# --- source law -------------------------------------------------------------


def test_session_close_law_separates_procedural_release_from_technical_custody() -> None:
    text = SESSION_CLOSE_PATH.read_text(encoding="utf-8")
    assert "### 3.7 Technical writer gate and procedural release" in text
    assert "BRANCH_WRITER_RELEASED is a procedural custody edge" in text
    assert "TECHNICAL_WRITER_GATE_ACTIVE" in text
    assert "TECHNICAL_WRITER_GATE_UNAVAILABLE" in text
    assert "scripts/source_continuity.py writer-gate" in text
    assert "checkpoint abandonment after writer loss is prohibited" in text
    assert "EFFECT_UNKNOWN remains exact-session sticky" in text
    assert "Applicability is closed by exclusion, never by enumeration" in text
    assert "UNKNOWN_APPLICABLE_RULE" in text
    for inert in ("merge_queue", "branch_name_pattern", "tag_name_pattern"):
        assert inert in text
    assert "must leave the\naccepted integration an executable expected-head path" in text


def test_law_inert_and_non_mutating_sets_match_the_verifier_contract() -> None:
    module = _contract()
    assert module._WRITER_GATE_INERT_RULE_TYPES == frozenset(
        {"merge_queue", "branch_name_pattern", "tag_name_pattern"}
    )
    assert module._WRITER_GATE_NON_MUTATING_RULE_TYPES == frozenset(
        {"creation", "deletion", "non_fast_forward"}
    )
    assert module._WRITER_GATE_INERT_RULE_TYPES <= module._WRITER_GATE_KNOWN_RULE_TYPES
    assert module._WRITER_GATE_NON_MUTATING_RULE_TYPES <= module._WRITER_GATE_KNOWN_RULE_TYPES
    assert not (
        module._WRITER_GATE_INERT_RULE_TYPES & module._WRITER_GATE_NON_MUTATING_RULE_TYPES
    )
    assert "lock_branch" in module._WRITER_GATE_KNOWN_RULE_TYPES
    assert "lock_branch" not in module._WRITER_GATE_INERT_RULE_TYPES
    assert "lock_branch" not in module._WRITER_GATE_NON_MUTATING_RULE_TYPES


def test_review_return_release_maintainer_records_the_writer_gate_state() -> None:
    text = REVIEW_RETURN_PATH.read_text(encoding="utf-8")
    assert "### Step 8B — Technical writer-gate evidence for same-PR release" in text
    assert "TECHNICAL_WRITER_GATE_UNAVAILABLE" in text
    assert "does not block a clean RCH-1 same-PR release" in text
    assert "must be recorded in the release commission" in text
    assert "neither state grants" in text
    assert "`legacy_branch_protected` is the branch's own classic branch-protection readback" in text


# --- R1 exact review blockers: lock_branch, unknown rules, bypass modes ------


def test_lock_branch_without_exact_owner_bypass_blocks_active_gate() -> None:
    module = _contract()
    facts = _active_facts(
        module,
        branch_rules=(
            *_rules(module, "update", "deletion", "non_fast_forward"),
            *_rules(
                module,
                "lock_branch",
                ruleset_id=ORG_RULESET,
                source_type="Organization",
            ),
        ),
        rulesets=(
            _ruleset(module),
            _ruleset(
                module,
                ruleset_id=ORG_RULESET,
                source_type="Organization",
                bypass_actors=(),
            ),
        ),
    )
    result = _verify(module, facts=facts)
    payload = _assert_unavailable(module, result, "OWNER_INTEGRATION_ABSENT")
    assert payload["rule_types"] == [
        "deletion",
        "lock_branch",
        "non_fast_forward",
        "update",
    ]
    assert payload["enforcing_ruleset_ids"] == [REPO_RULESET, ORG_RULESET]


def test_lock_branch_with_exact_owner_always_retains_expected_head_mutation_path() -> None:
    module = _contract()
    facts = _active_facts(
        module,
        branch_rules=(
            *_rules(module, "update", "deletion", "non_fast_forward"),
            *_rules(
                module,
                "lock_branch",
                ruleset_id=ORG_RULESET,
                source_type="Organization",
            ),
        ),
        rulesets=(
            _ruleset(module),
            _ruleset(module, ruleset_id=ORG_RULESET, source_type="Organization"),
        ),
    )
    result = _verify(module, facts=facts)
    assert isinstance(result, module.WriterGateReceipt)
    payload = result.to_dict()
    assert payload["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
    assert payload["defects"] == []
    assert payload["rule_types"] == [
        "deletion",
        "lock_branch",
        "non_fast_forward",
        "update",
    ]
    assert payload["enforcing_ruleset_ids"] == [REPO_RULESET, ORG_RULESET]


def test_unknown_applicable_rule_fails_closed_instead_of_disappearing() -> None:
    module = _contract()
    unknown = "future_ref_mutation_guard"
    result = _verify(
        module,
        facts=_active_facts(
            module,
            branch_rules=(
                *_rules(module, "update", "deletion", "non_fast_forward"),
                *_rules(
                    module,
                    unknown,
                    ruleset_id=ORG_RULESET,
                    source_type="Organization",
                ),
            ),
            rulesets=(
                _ruleset(module),
                _ruleset(module, ruleset_id=ORG_RULESET, source_type="Organization"),
            ),
        ),
    )
    payload = _assert_unavailable(module, result, "UNKNOWN_APPLICABLE_RULE")
    assert unknown in payload["rule_types"]
    assert payload["enforcing_ruleset_ids"] == [REPO_RULESET, ORG_RULESET]


def test_same_accepted_integration_pull_request_bypass_is_widened() -> None:
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(
            module,
            rulesets=(
                _ruleset(
                    module,
                    bypass_actors=(
                        _actor(module),
                        _actor(module, bypass_mode="pull_request"),
                    ),
                ),
            ),
        ),
    )
    payload = _assert_unavailable(module, result, "BYPASS_WIDENED")
    assert {
        "actor_type": "Integration",
        "actor_id": ACCEPTED_APP,
        "bypass_mode": "pull_request",
    } in payload["bypass_actors"]


def test_exempt_actor_is_valid_but_widens_the_bypass_set() -> None:
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(
            module,
            rulesets=(
                _ruleset(
                    module,
                    bypass_actors=(
                        _actor(module),
                        _actor(
                            module,
                            actor_type="RepositoryRole",
                            actor_id=5,
                            bypass_mode="exempt",
                        ),
                    ),
                ),
            ),
        ),
    )
    payload = _assert_unavailable(module, result, "BYPASS_WIDENED")
    assert {
        "actor_type": "RepositoryRole",
        "actor_id": 5,
        "bypass_mode": "exempt",
    } in payload["bypass_actors"]


def test_cli_lock_branch_ruleset_is_read_and_can_block_owner_mediation(capsys) -> None:
    module = _cli_module()
    http = _GateHTTP(
        rules=[
            _rule_row("update"),
            _rule_row("deletion"),
            _rule_row("non_fast_forward"),
            _rule_row("lock_branch", ORG_RULESET, "Organization"),
        ],
        rulesets={REPO_RULESET: _ruleset_row()},
        org_rulesets={
            ORG_RULESET: _ruleset_row(
                ORG_RULESET,
                source_type="Organization",
                bypass_actors=[],
            )
        },
    )
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert payload["defects"] == ["OWNER_INTEGRATION_ABSENT"]
    assert payload["enforcing_ruleset_ids"] == [REPO_RULESET, ORG_RULESET]
    assert "lock_branch" in payload["rule_types"]
    endpoints = {url.removeprefix(API_ROOT + "/") for url, _, _ in http.calls}
    assert f"orgs/{ORG}/rulesets/{ORG_RULESET}" in endpoints


def test_cli_exempt_actor_is_widened_not_malformed(capsys) -> None:
    module = _cli_module()
    http = _active_http(
        rulesets={
            REPO_RULESET: _ruleset_row(
                bypass_actors=[
                    {
                        "actor_id": ACCEPTED_APP,
                        "actor_type": "Integration",
                        "bypass_mode": "always",
                    },
                    {
                        "actor_id": 5,
                        "actor_type": "RepositoryRole",
                        "bypass_mode": "exempt",
                    },
                ]
            )
        }
    )
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert payload["defects"] == ["BYPASS_WIDENED"]


def test_cli_unknown_applicable_rule_is_unavailable_not_filtered(capsys) -> None:
    module = _cli_module()
    unknown = "future_ref_mutation_guard"
    http = _GateHTTP(
        rules=[
            _rule_row("update"),
            _rule_row("deletion"),
            _rule_row("non_fast_forward"),
            _rule_row(unknown, ORG_RULESET, "Organization"),
        ],
        rulesets={REPO_RULESET: _ruleset_row()},
        org_rulesets={ORG_RULESET: _ruleset_row(ORG_RULESET, source_type="Organization")},
    )
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())
    assert exit_code == 0
    assert payload["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert payload["defects"] == ["UNKNOWN_APPLICABLE_RULE"]
    assert unknown in payload["rule_types"]


# --- R1 completeness: every applicable write-blocking rule, not only lock_branch


MUTATION_BLOCKING_RULE_TYPES = (
    "pull_request",
    "required_status_checks",
    "required_signatures",
    "required_deployments",
    "required_linear_history",
    "commit_message_pattern",
    "commit_author_email_pattern",
    "committer_email_pattern",
    "workflows",
    "code_scanning",
    "file_path_restriction",
    "max_file_path_length",
    "file_extension_restriction",
    "file_size",
)


def _split_ruleset_facts(module, *, second_rule: str, second_bypass=None):
    """Frozen gate in ruleset 1; one extra rule in a separate org ruleset 2."""

    return _active_facts(
        module,
        branch_rules=(
            *_rules(module, "update", "deletion", "non_fast_forward"),
            *_rules(module, second_rule, ruleset_id=ORG_RULESET, source_type="Organization"),
        ),
        rulesets=(
            _ruleset(module),
            _ruleset(
                module,
                ruleset_id=ORG_RULESET,
                source_type="Organization",
                **({} if second_bypass is None else {"bypass_actors": second_bypass}),
            ),
        ),
    )


@pytest.mark.parametrize("rule_type", MUTATION_BLOCKING_RULE_TYPES)
def test_every_applicable_mutation_rule_requires_the_same_owner_mediation(rule_type: str) -> None:
    # Blocker 1 is not only about lock_branch: any active rule that can block or
    # alter an owner-mediated expected-head update must retain that mediation.
    module = _contract()
    result = _verify(module, facts=_split_ruleset_facts(module, second_rule=rule_type, second_bypass=()))
    payload = _assert_unavailable(module, result, "OWNER_INTEGRATION_ABSENT")
    assert rule_type in payload["rule_types"]
    assert payload["enforcing_ruleset_ids"] == [REPO_RULESET, ORG_RULESET]


@pytest.mark.parametrize("rule_type", MUTATION_BLOCKING_RULE_TYPES)
def test_applicable_mutation_rule_mediated_by_the_accepted_integration_stays_active(rule_type: str) -> None:
    module = _contract()
    result = _verify(module, facts=_split_ruleset_facts(module, second_rule=rule_type))
    assert isinstance(result, module.WriterGateReceipt)
    payload = result.to_dict()
    assert payload["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
    assert payload["defects"] == []
    assert rule_type in payload["rule_types"]


@pytest.mark.parametrize("rule_type", ["deletion", "non_fast_forward", "creation"])
def test_rules_that_cannot_block_a_fast_forward_fence_need_no_owner_bypass(rule_type: str) -> None:
    # A tree-preserving fence commit neither deletes, rewrites history, nor
    # creates a ref, so these rules do not need the owner bypass to be mediated.
    module = _contract()
    result = _verify(module, facts=_split_ruleset_facts(module, second_rule=rule_type, second_bypass=()))
    assert isinstance(result, module.WriterGateReceipt)
    payload = result.to_dict()
    assert "OWNER_INTEGRATION_ABSENT" not in payload["defects"]
    expected = ["CREATION_RESTRICTED"] if rule_type == "creation" else []
    assert payload["defects"] == expected


@pytest.mark.parametrize("rule_type", ["merge_queue", "branch_name_pattern", "tag_name_pattern"])
def test_inert_rule_types_never_form_or_widen_a_writer_gate(rule_type: str) -> None:
    # Preserves the live master reading: a merge-queue ruleset is not custody.
    module = _contract()
    alone = _verify(
        module,
        request=_request(module, accepted_integration_id=None),
        facts=_active_facts(
            module,
            branch_rules=_rules(module, rule_type),
            rulesets=(_ruleset(module, bypass_actors=()),),
        ),
    )
    payload = _assert_unavailable(module, alone, "RULES_ABSENT")
    assert payload["rule_types"] == []
    assert payload["enforcing_ruleset_ids"] == []

    beside = _verify(module, facts=_split_ruleset_facts(module, second_rule=rule_type, second_bypass=()))
    assert isinstance(beside, module.WriterGateReceipt)
    assert beside.to_dict()["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
    assert beside.to_dict()["enforcing_ruleset_ids"] == [REPO_RULESET]


def test_cli_pull_request_rule_in_an_unmediated_ruleset_blocks_the_gate(capsys) -> None:
    module = _cli_module()
    http = _GateHTTP(
        rules=[
            _rule_row("update"),
            _rule_row("deletion"),
            _rule_row("non_fast_forward"),
            _rule_row("pull_request", ORG_RULESET, "Organization"),
        ],
        rulesets={REPO_RULESET: _ruleset_row()},
        org_rulesets={
            ORG_RULESET: _ruleset_row(ORG_RULESET, source_type="Organization", bypass_actors=[])
        },
    )
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert payload["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert payload["defects"] == ["OWNER_INTEGRATION_ABSENT"]
    assert "pull_request" in payload["rule_types"]


def test_accepted_integration_in_exempt_mode_never_proves_owner_mediation() -> None:
    # `exempt` is valid GitHub evidence, but it is not the frozen `always`
    # mediation path, even for the accepted integration itself.
    module = _contract()
    result = _verify(
        module,
        facts=_active_facts(
            module,
            rulesets=(_ruleset(module, bypass_actors=(_actor(module, bypass_mode="exempt"),)),),
        ),
    )
    payload = _assert_unavailable(module, result, "BYPASS_WIDENED", "OWNER_INTEGRATION_ABSENT")
    assert payload["bypass_actors"] == [
        {"actor_type": "Integration", "actor_id": ACCEPTED_APP, "bypass_mode": "exempt"}
    ]


def test_cli_accepted_integration_exempt_mode_is_widened_and_unmediated(capsys) -> None:
    module = _cli_module()
    http = _active_http(
        rulesets={
            REPO_RULESET: _ruleset_row(
                bypass_actors=[
                    {"actor_id": ACCEPTED_APP, "actor_type": "Integration", "bypass_mode": "exempt"}
                ]
            )
        }
    )
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert payload["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert payload["defects"] == ["BYPASS_WIDENED", "OWNER_INTEGRATION_ABSENT"]


# --- R2 exact review blocker: concurrent classic branch protection ----------


def test_legacy_protection_flag_is_load_bearing_in_the_active_predicate() -> None:
    """The exact discriminator from review 5233167865 / ruling 5709838127."""

    module = _contract()
    absent = _verify(module, facts=_active_facts(module, legacy_branch_protected=False))
    present = _verify(module, facts=_active_facts(module, legacy_branch_protected=True))

    assert isinstance(absent, module.WriterGateReceipt)
    assert absent.state is module.WriterGateState.ACTIVE
    assert absent.to_dict()["defects"] == []
    _assert_unavailable(module, present, "LEGACY_PROTECTION_PRESENT")


def test_classic_protection_is_reported_on_the_receipt_face() -> None:
    module = _contract()
    result = _verify(module, facts=_active_facts(module, legacy_branch_protected=True))
    assert isinstance(result, module.WriterGateReceipt)
    payload = result.to_dict()
    assert payload["legacy_branch_protected"] is True
    assert payload["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert payload["merge_authorized"] is False


def test_legacy_protection_defect_is_a_member_of_the_closed_defect_set() -> None:
    module = _contract()
    assert module.WriterGateDefect.LEGACY_PROTECTION_PRESENT.value == "LEGACY_PROTECTION_PRESENT"


_CLASSIC_SHAPES = {
    "lock": {"lock_branch": {"enabled": True}},
    "restricted_apps": {
        "restrictions": {"users": [], "teams": [], "apps": [{"id": ACCEPTED_APP}]}
    },
    "required_pull_request": {
        "required_pull_request_reviews": {"required_approving_review_count": 1}
    },
    "required_status_checks": {"required_status_checks": {"strict": True, "contexts": []}},
    "enforce_admins": {"enforce_admins": {"enabled": True}},
}


def test_cli_probes_classic_protection_separately_from_the_branch_summary() -> None:
    module = _cli_module()
    http = _active_http(branch={"commit": {"sha": HEAD_SHA}, "protected": True})
    _run(module, _argv(), http=http)
    endpoints = {url.removeprefix(API_ROOT + "/") for url, _token, _timeout in http.calls}
    assert _protection_endpoint() in endpoints
    assert _branch_endpoint() in endpoints


def test_cli_ruleset_only_protected_branch_stays_active(capsys) -> None:
    module = _cli_module()
    http = _active_http(branch={"commit": {"sha": HEAD_SHA}, "protected": True})
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert payload["state"] == "TECHNICAL_WRITER_GATE_ACTIVE"
    assert payload["legacy_branch_protected"] is False
    assert payload["defects"] == []


@pytest.mark.parametrize("shape", sorted(_CLASSIC_SHAPES))
def test_cli_concurrent_classic_protection_never_reaches_active(shape, capsys) -> None:
    module = _cli_module()
    http = _active_http(
        branch={"commit": {"sha": HEAD_SHA}, "protected": True},
        protection=_CLASSIC_SHAPES[shape],
    )
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert payload["state"] == "TECHNICAL_WRITER_GATE_UNAVAILABLE"
    assert payload["legacy_branch_protected"] is True
    assert payload["defects"] == ["LEGACY_PROTECTION_PRESENT"]
    assert payload["writer_release_authorized"] is False


def test_cli_unreadable_classic_protection_fails_closed_instead_of_absent(capsys) -> None:
    module = _cli_module()
    http = _active_http(protection_unreadable=True)
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 2
    assert payload["code"] == "REMOTE_PROBE_FAILED"


def test_cli_malformed_classic_protection_payload_fails_closed(capsys) -> None:
    module = _cli_module()
    http = _active_http(protection=["not", "an", "object"])
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 2
    assert payload["code"] == "REMOTE_PROBE_FAILED"


def test_cli_classic_protection_appearing_between_observations_refuses(capsys) -> None:
    module = _cli_module()
    http = _active_http(protection_on_second_read=_CLASSIC_SHAPES["lock"])
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 1
    assert payload["code"] == "REMOTE_PROOF_CHANGED"


def test_cli_classic_protection_disappearing_between_observations_refuses(capsys) -> None:
    module = _cli_module()
    http = _active_http(
        protection=_CLASSIC_SHAPES["lock"],
        protection_absent_on_second_read=True,
    )
    exit_code = _run(module, _argv(), http=http)
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 1
    assert payload["code"] == "REMOTE_PROOF_CHANGED"


def test_session_close_law_pins_the_classic_protection_layer() -> None:
    text = SESSION_CLOSE_PATH.read_text(encoding="utf-8")
    assert "LEGACY_PROTECTION_PRESENT" in text
    assert "branch summary `protected` flag is not a classic-protection observation" in text
    assert "no concurrent classic branch protection" in text


# --- conditional revalidation of an absent optional readback ----------------


class _ConditionalTransport:
    """Real-transport-shaped fake: ETag revalidation plus lawful 404 absence."""

    _source_continuity_conditional = True

    def __init__(self, module, *, missing, appears: bool = False, unreadable: bool = False) -> None:
        self.module = module
        self.missing = missing
        self.appears = appears
        self.unreadable = unreadable
        self.reads: dict[str, int] = {}

    def __call__(self, url, *, token, timeout, if_none_match=None):
        assert token == TOKEN and timeout > 0
        self.reads[url] = self.reads.get(url, 0) + 1
        if url == self.missing:
            if self.unreadable and self.reads[url] > 1:
                raise self.module._RemoteProbeError()
            if not self.appears or self.reads[url] == 1:
                raise self.module._RemoteResourceMissing()
            return self.module._HTTPRepresentation(
                payload={"lock_branch": {"enabled": True}},
                etag='"' + "a" * 32 + '"',
                not_modified=False,
            )
        etag = '"' + f"{abs(hash(url)):032x}"[:32] + '"'
        if if_none_match is None:
            return self.module._HTTPRepresentation(
                payload={"url": url}, etag=etag, not_modified=False
            )
        return self.module._HTTPRepresentation(payload=None, etag=etag, not_modified=True)


_ABSENT_URL = f"{API_ROOT}/repos/{REPOSITORY}/branches/x/protection"
_PRESENT_URL = f"{API_ROOT}/repos/{REPOSITORY}/branches/x"


def _bounded_with_absence(module, **overrides):
    transport = _ConditionalTransport(module, missing=_ABSENT_URL, **overrides)
    bounded = module._BoundedHTTPGet(transport)
    assert bounded(_PRESENT_URL, token=TOKEN, timeout=20.0) == {"url": _PRESENT_URL}
    assert bounded.get_optional(_ABSENT_URL, token=TOKEN, timeout=20.0) is module._MISSING
    return bounded


def test_conditional_validation_accepts_an_optional_resource_that_stays_absent() -> None:
    module = _cli_module()
    bounded = _bounded_with_absence(module)
    assert bounded.validate_unchanged(token=TOKEN) is True


def test_conditional_validation_detects_an_absent_resource_that_appears() -> None:
    module = _cli_module()
    bounded = _bounded_with_absence(module, appears=True)
    assert bounded.validate_unchanged(token=TOKEN) is False


def test_conditional_validation_fails_closed_on_an_unreadable_absence_recheck() -> None:
    module = _cli_module()
    bounded = _bounded_with_absence(module, unreadable=True)
    with pytest.raises(module._RemoteProbeError):
        bounded.validate_unchanged(token=TOKEN)


def test_get_optional_never_swallows_a_real_probe_failure() -> None:
    module = _cli_module()

    def failing(url, *, token, timeout):
        raise module._RemoteProbeError()

    bounded = module._BoundedHTTPGet(failing)
    with pytest.raises(module._RemoteProbeError):
        bounded.get_optional(_ABSENT_URL, token=TOKEN, timeout=20.0)
    assert bounded._missing_observations == []


@pytest.mark.parametrize(
    "endpoint",
    [
        _branch_endpoint(),
        _rules_endpoint(),
        f"repos/{REPOSITORY}/rulesets/{REPO_RULESET}",
    ],
)
def test_cli_absence_of_a_required_endpoint_is_never_read_as_absence(endpoint, capsys) -> None:
    """Only the classic-protection readback may be absent; 404 elsewhere fails closed.

    Raised as the transport's own `_RemoteResourceMissing`, which subclasses
    `_RemoteProbeError` precisely so marking a 404 cannot widen any other probe
    into a lawful absence. Confirmed against live GitHub on a nonexistent
    branch: `REMOTE_PROBE_FAILED`, exit 2.
    """

    module = _cli_module()
    exit_code = _run(module, _argv(), http=_active_http(missing_endpoints=(endpoint,)))
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 2
    assert payload["code"] == "REMOTE_PROBE_FAILED"


def test_resource_missing_is_a_probe_error_subclass() -> None:
    module = _cli_module()
    assert issubclass(module._RemoteResourceMissing, module._RemoteProbeError)
    assert module._is_resource_missing(module._RemoteResourceMissing()) is True
    assert module._is_resource_missing(module._RemoteProbeError()) is False
