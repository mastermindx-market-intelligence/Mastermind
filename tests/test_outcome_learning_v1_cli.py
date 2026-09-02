"""CLI tests for the Outcome Learning V1 (OL-V1) vertical.

Every test injects a Fake transport/runner — this module NEVER invokes real git,
gh, or network I/O. The end-to-end happy path exercises
seal -> preflight -> canary -> outcome -> evaluate -> self-model -> project -> proof
and asserts the artifact cross-digests verify. Kill test #11 (single-shot journal
refusal) lives here because it is a CLI-level behavior, not a contracts-level one.

Principal-review corrections (2026-09-02) added: BLOCKER 1 (failed-restore truth),
BLOCKER 2 (derived, single-shot journal path), BLOCKER 3 (seal re-verifies
composition.json), MAJOR 5 (pre-effect freshness/drift gate), addendum A (--as-of
auto-computation / stale refusal), addendum B (COMPOSITION_INVALID vs
OWNER_SOURCE_NOT_CURRENT), plus coverage tests for guards the adversarial review
found silent.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

import scripts.outcome_learning_v1 as cli
from control_plane.chairman_cognition import ALLOWED_SOURCE_OWNERS, CLASSIFICATION_SOURCE_OWNERS
from control_plane.outcome_learning_contracts import canonical_digest

SHA40_A = "a" * 40
SHA40_B = "b" * 40


def _capture_stdout(fn):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn()
    return rc, buf.getvalue()


def _boot_packet(
    *,
    mastermind_sha=SHA40_A,
    macro_sha=SHA40_B,
    mastermind_branch="master",
    brief_unhealthy=False,
    generated_at="2026-09-02T12:00:00Z",
    constraints_missing=None,
):
    constraints = {
        "autonomous_production_deploy": "prohibited",
        "autonomous_live_capital_execution": "prohibited",
        "duplicate_control_planes": "prohibited",
        "marketing_org_expansion_before_distribution_proof": "prohibited",
        "new_feature_expansion": "constrained",
        "unbounded_autonomous_strategic_modification": "prohibited",
    }
    if constraints_missing:
        del constraints[constraints_missing]
    return {
        "schema": "mastermind.ceo_boot_packet.v1",
        "generated_at": generated_at,
        "mastermind": {"root": "/x", "sha": mastermind_sha, "branch": mastermind_branch},
        "macro": {
            "root": "/y",
            "sha": macro_sha,
            "resolved_via": "sibling",
            "candidates_tried": [],
        },
        "strategic_state": {
            "schema": "mastermind.strategic_state.v1",
            "company_phase": "PRE_REVENUE_MVP_CONVERGENCE",
            "north_star": [],
            "p0": [],
            "constraints": constraints,
        },
        "brief": {
            "schema": "ceo_brief.v1",
            "generated_at": generated_at,
            "since": "2026-09-01T12:00:00Z",
            "since_label": "the last 24h",
            "counts": {"total": 0, "active": 0, "awaiting_ci": 0, "blocked": 0, "done_in_window": 0},
            "inputs": {"active_builds_age_hours": 1.0, "worktrees": 1, "degraded": []},
            "needs_ceo": [],
            "blocked": [],
            "finished": [],
            "running": {
                "active": 0, "awaiting_ci": 0, "awaiting_review": 0, "blocked": 0,
                "proposed": 0, "open_prs": 0, "stale_claims": 0, "claims_without_worktree": 0,
            },
            "readiness": {"schema": "agentos.readiness.v1", "records": [], "degraded": []},
            # A non-empty warnings list makes _agentos_brief_status report the brief
            # unhealthy (control_plane.chairman_cognition_sources), which drives
            # AGENT_OS:ceo_brief to state UNKNOWN even though the checkout shas agree —
            # a fixture, not a real degraded-brief condition.
            "warnings": (
                ["fixture: forcing an unhealthy brief for a compose-gating test"]
                if brief_unhealthy
                else []
            ),
        },
        "handoffs": [],
        "degraded": [],
        "next_recommended_act": "Consult the canonical Improvement Agenda.",
    }


class FakeRunner:
    """Deterministic stand-in for git / ceo_boot_packet.py / agentos.py calls.

    ``boot_macro_sha`` is the sha the (fake) boot packet claims for the macro
    checkout; ``macro_sha`` is what ``git rev-parse HEAD`` reports live for that
    checkout. They default to the same value (a healthy, CURRENT fixture); one
    compose-gating test mismatches them on purpose to force AGENT_OS:ceo_brief into
    CONFLICT, and another sets ``brief_unhealthy`` to force it into UNKNOWN instead —
    neither touches any real git or network state.
    """

    def __init__(
        self,
        *,
        mastermind_sha=SHA40_A,
        macro_sha=SHA40_B,
        boot_macro_sha=None,
        mastermind_branch="master",
        brief_unhealthy=False,
        boot_generated_at="2026-09-02T12:00:00Z",
        constraints_missing=None,
    ):
        self.mastermind_sha = mastermind_sha
        self.macro_sha = macro_sha
        self.boot_macro_sha = boot_macro_sha if boot_macro_sha is not None else macro_sha
        self.mastermind_branch = mastermind_branch
        self.brief_unhealthy = brief_unhealthy
        self.boot_generated_at = boot_generated_at
        self.constraints_missing = constraints_missing
        self.calls: list[tuple] = []

    def run(self, args, *, cwd=None, input=None):
        self.calls.append((tuple(args), cwd, input))
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            sha = self.macro_sha if cwd == "/y" else self.mastermind_sha
            return cli.RunResult(0, sha + "\n", "")
        if args[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return cli.RunResult(0, self.mastermind_branch + "\n", "")
        if args[:2] == ["git", "hash-object"]:
            return cli.RunResult(0, "f" * 40 + "\n", "")
        if len(args) >= 2 and "ceo_boot_packet.py" in args[1]:
            boot = _boot_packet(
                mastermind_sha=self.mastermind_sha,
                macro_sha=self.boot_macro_sha,
                mastermind_branch=self.mastermind_branch,
                brief_unhealthy=self.brief_unhealthy,
                generated_at=self.boot_generated_at,
                constraints_missing=self.constraints_missing,
            )
            return cli.RunResult(0, json.dumps(boot), "")
        if len(args) >= 2 and "agentos.py" in args[1]:
            return cli.RunResult(0, json.dumps({"source_records_digest": "sha256:" + "e" * 64}), "")
        raise AssertionError(f"unexpected FakeRunner call: {args}")


class FakeTransport:
    """Deterministic stand-in for `gh api`: one open PR, PATCH mutates its title.

    Status stays 200 here (MAJOR 7 pins "UNOBSERVED" to the real GhCliTransport only,
    since FakeTransport represents a caller that DOES observe a status)."""

    def __init__(
        self,
        *,
        title="Some PR title",
        head_sha=SHA40_B,
        raise_on_apply=False,
        raise_on_restore=False,
    ):
        self.title = title
        self.head_sha = head_sha
        self.pr_number = 42
        self.gets = 0
        self.patches = 0
        self._raise_on_apply = raise_on_apply
        self._raise_on_restore = raise_on_restore

    def get(self, endpoint):
        self.gets += 1
        if endpoint.endswith("&state=open"):
            return 200, [{"number": self.pr_number}]
        return 200, {
            "number": self.pr_number,
            "html_url": f"https://github.com/mastermindx-market-intelligence/Mastermind/pull/{self.pr_number}",
            "title": self.title,
            "head": {"sha": self.head_sha},
            "base": {"ref": "master"},
        }

    def patch(self, endpoint, payload):
        self.patches += 1
        if self.patches == 1 and self._raise_on_apply:
            raise RuntimeError("simulated transient failure crossing the effect boundary")
        if self.patches == 2 and self._raise_on_restore:
            # The apply already completed and mutated the live title — BLOCKER 1's
            # scenario. The title is left mutated; only a reconciliation GET (not
            # this raised patch) can reveal that.
            raise RuntimeError("simulated transient failure crossing the effect boundary")
        self.title = payload["title"]
        return 200, {
            "number": self.pr_number,
            "title": self.title,
            "head": {"sha": self.head_sha},
            "base": {"ref": "master"},
        }


def _journal_path(episode_dir: Path, request: dict) -> Path:
    name = (
        f"canary_journal.{request['operation_key']}."
        f"{request['expectation_sealed_hash'][7:19]}.json"
    )
    return episode_dir / name


def _compose_and_seal(
    tmp_path: Path, runner: FakeRunner, *, as_of: str | None = "2026-09-02T12:00:00Z"
) -> tuple[Path, dict, dict]:
    """Run compose (honest fixture) then seal. compose's gate is disposition-keyed on
    the canary option alone (principal correction, 2026-09-02): an honest, near-zero-
    cost READ_ONLY HOLD is never Pareto-dominated, so this fixture's
    ``selection_state`` is lawfully ``MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS`` with
    ``recommended_option_id=None`` — that is not a failure, and compose still exits 0
    with ``COMPOSE_OK`` because the canary option itself is
    ``ELIGIBLE_WITHIN_DELEGATION``. seal then picks the truthful
    ``principal_selection_from_a1_incomparable_frontier`` assignment method."""
    episode_dir = tmp_path / "episode"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    compose_argv = [
        "compose",
        "--mastermind-root", "/x",
        "--macro-root", "/y",
        "--episode-dir", str(episode_dir),
        "--operation-key", "olv1-cli-test-op",
    ]
    if as_of is not None:
        compose_argv += ["--as-of", as_of]
    compose_args = cli._parser().parse_args(compose_argv)
    rc, out = _capture_stdout(lambda: cli.cmd_compose(compose_args, runner=runner))
    assert rc == 0, f"compose must succeed against a fully CURRENT fixture, got: {out}"
    assert "COMPOSE_OK canary_disposition=ELIGIBLE_WITHIN_DELEGATION" in out
    composition = json.loads((episode_dir / "composition.json").read_text())
    assert composition["packet"]["selection_state"] == "MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS"
    assert composition["packet"]["recommended_option_id"] is None

    rc = cli.main(
        [
            "seal",
            "--composition", str(episode_dir / "composition.json"),
            "--episode-dir", str(episode_dir),
            "--parent-head", SHA40_A,
            "--recorded-at", "2026-09-02T12:01:00Z",
            "--operation-key", "olv1-cli-test-op",
            "--out-expectation", str(outside_dir / "expectation.json"),
            "--out-request", str(outside_dir / "request.json"),
        ]
    )
    assert rc == 0
    expectation = json.loads((outside_dir / "expectation.json").read_text())
    request = json.loads((outside_dir / "request.json").read_text())
    return outside_dir, expectation, request


def _run_preflight(outside_dir: Path, transport: FakeTransport) -> dict:
    rc = cli.cmd_preflight(
        cli._parser().parse_args(
            [
                "preflight",
                "--repo", "mastermindx-market-intelligence/Mastermind",
                "--branch", "sol/outcome-learning-v1-complete-vertical-20260902",
                "--sealed-commit", transport.head_sha,
                "--expectation", str(outside_dir / "expectation.json"),
                "--request", str(outside_dir / "request.json"),
                "--observed-at", "2026-09-02T12:02:00Z",
                "--out", str(outside_dir / "preflight.json"),
            ]
        ),
        runner=FakeRunner(),
        transport=transport,
    )
    assert rc == 0
    return json.loads((outside_dir / "preflight.json").read_text())


# --------------------------------------------------------------------------- happy path


def test_end_to_end_seal_through_proof_cross_digests_verify(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    assert (
        expectation["assignment"]["method"]
        == "principal_selection_from_a1_incomparable_frontier"
    )
    transport = FakeTransport()
    _run_preflight(outside_dir, transport)

    episode_dir = outside_dir
    rc = cli.cmd_canary(
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", str(outside_dir / "preflight.json"),
                "--request", str(outside_dir / "request.json"),
                "--recorded-at", "2026-09-02T12:03:00Z",
                "--episode-dir", str(episode_dir),
            ]
        ),
        transport=transport,
    )
    assert rc == 0
    journal_path = _journal_path(episode_dir, request)
    assert journal_path.exists()
    journal = json.loads(journal_path.read_text())
    assert journal["effect_state"] == "APPLIED_AND_RESTORED"
    assert len(journal["effect_calls"]) == 2
    assert journal["reconciliation"] is None
    assert transport.title == "Some PR title"  # restored byte-identically

    rc = cli.main(
        [
            "outcome",
            "--journal", str(journal_path),
            "--preflight", str(outside_dir / "preflight.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--request", str(outside_dir / "request.json"),
            "--recorded-at", "2026-09-02T12:04:00Z",
            "--out", str(outside_dir / "outcome.json"),
        ]
    )
    assert rc == 0
    outcome = json.loads((outside_dir / "outcome.json").read_text())
    assert outcome["expectation_sealed_hash"] == expectation["sealed_hash"]
    assert outcome["request_digest"] == canonical_digest(request)
    assert outcome["restoration"]["byte_identical"] is True

    rc = cli.main(
        [
            "evaluate",
            "--expectation", str(outside_dir / "expectation.json"),
            "--outcome", str(outside_dir / "outcome.json"),
            "--request", str(outside_dir / "request.json"),
            "--recorded-at", "2026-09-02T12:05:00Z",
            "--out", str(outside_dir / "evaluation.json"),
        ]
    )
    assert rc == 0
    evaluation = json.loads((outside_dir / "evaluation.json").read_text())
    assert evaluation["outcome_digest"] == canonical_digest(outcome)
    assert evaluation["causal_grade"] == "DESCRIPTIVE_ONLY"
    assert all(evaluation["process_quality"].values())

    # BLOCKER 4: a perfect episode's probability-kind forecasts score small brier and
    # carry no interval-hit/miss nonsense.
    for entry in evaluation["forecast"]:
        if entry["kind"] != "probability":
            continue
        if entry["realized"] is None:
            assert entry["brier_score"] is None
            assert entry["within_interval"] is None
            continue
        assert entry["within_interval"] is None
        assert entry["brier_score"] is not None
        assert entry["brier_score"] < 0.05

    rc = cli.main(
        [
            "self-model",
            "--evaluation", str(outside_dir / "evaluation.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--recorded-at", "2026-09-02T12:06:00Z",
            "--out", str(outside_dir / "self_model.json"),
        ]
    )
    assert rc == 0
    self_model = json.loads((outside_dir / "self_model.json").read_text())
    assert self_model["evaluation_digest"] == canonical_digest(evaluation)
    assert self_model["universal_score"] is None

    rc = cli.main(
        [
            "project",
            "--evaluation", str(outside_dir / "evaluation.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--outcome", str(outside_dir / "outcome.json"),
            "--recorded-at", "2026-09-02T12:07:00Z",
            "--out", str(outside_dir / "projection.json"),
        ]
    )
    assert rc == 0
    projection = json.loads((outside_dir / "projection.json").read_text())
    assert projection["evaluation_digest"] == canonical_digest(evaluation)
    assert projection["automatic_writes"] is False
    dsc = next(c for c in projection["candidates"] if c["kind"] == "DSC_CANDIDATE")
    assert dsc["key_hint"] == "OLV1-EPISODE-CONSEQUENCE-2026-09-02"

    rc = cli.main(
        [
            "proof",
            "--expectation", str(outside_dir / "expectation.json"),
            "--request", str(outside_dir / "request.json"),
            "--outcome", str(outside_dir / "outcome.json"),
            "--evaluation", str(outside_dir / "evaluation.json"),
            "--self-model", str(outside_dir / "self_model.json"),
            "--project", str(outside_dir / "projection.json"),
            "--out", str(outside_dir / "proof.md"),
        ]
    )
    assert rc == 0
    proof_text = (outside_dir / "proof.md").read_text()
    assert expectation["operation_key"] in proof_text
    assert "DESCRIPTIVE_ONLY" in proof_text
    assert "What this does NOT prove" in proof_text
    assert "applied, and restored" in proof_text
    assert "MANUAL RESTORATION MAY BE OWED" not in proof_text


# --------------------------------------------------------------------------- compose gating


def test_compose_gating_fixture_bundle_forced_conflict_blocks(tmp_path):
    # Force AGENT_OS:ceo_brief into CONFLICT by mismatching the live git-observed
    # macro sha against the boot packet's own embedded macro sha — a deliberate
    # fixture, never a real network condition. This drives the canary option's
    # adjudication to REFUSED/SOURCE_NOT_CURRENT, which is compose's own gate.
    runner = FakeRunner(macro_sha=SHA40_B, boot_macro_sha="d" * 40)
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(tmp_path / "episode"),
            "--as-of", "2026-09-02T12:00:00Z",
            "--operation-key", "olv1-cli-test-op",
        ]
    )
    rc, out = _capture_stdout(lambda: cli.cmd_compose(args, runner=runner))
    assert rc == 4
    assert "BLOCKER OWNER_SOURCE_NOT_CURRENT AGENT_OS:ceo_brief=CONFLICT" in out


def test_compose_gating_fixture_bundle_forced_unknown_blocks(tmp_path):
    # Force AGENT_OS:ceo_brief into UNKNOWN via an unhealthy brief (non-empty
    # warnings) — checkout shas agree, but _agentos_brief_status reports the brief
    # itself unreadable, which _agentos_receipt maps to state UNKNOWN. Distinct
    # fixture shape from the CONFLICT test above (a sha mismatch), covering the other
    # non-CURRENT state the compose gate must also block on.
    runner = FakeRunner(brief_unhealthy=True)
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(tmp_path / "episode"),
            "--as-of", "2026-09-02T12:00:00Z",
            "--operation-key", "olv1-cli-test-op",
        ]
    )
    rc, out = _capture_stdout(lambda: cli.cmd_compose(args, runner=runner))
    assert rc == 4
    assert "BLOCKER OWNER_SOURCE_NOT_CURRENT AGENT_OS:ceo_brief=UNKNOWN" in out


def test_compose_composition_invalid_path_exits_5_not_4(tmp_path):
    """Addendum B: an exception raised INSIDE compose_input/evaluate_bundle (here, a
    boot packet missing a load-bearing strategic constraint, which
    control_plane.chairman_cognition_sources._strategic_receipt raises on directly)
    is a COMPOSITION defect, never an owner-source state — it must render as
    BLOCKER COMPOSITION_INVALID and exit 5, NEVER the
    BLOCKER OWNER_SOURCE_NOT_CURRENT template (which presumes a real ref=state pair
    from a successfully-composed packet)."""
    runner = FakeRunner(constraints_missing="new_feature_expansion")
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(tmp_path / "episode"),
            "--as-of", "2026-09-02T12:00:00Z",
            "--operation-key", "olv1-cli-test-op",
        ]
    )
    rc, out = _capture_stdout(lambda: cli.cmd_compose(args, runner=runner))
    assert rc == 5
    assert "BLOCKER COMPOSITION_INVALID" in out
    assert "OWNER_SOURCE_NOT_CURRENT" not in out


def test_compose_as_of_auto_computed_when_omitted(tmp_path):
    """Addendum A: omitting --as-of computes it AFTER acquisition as the later of
    'now' and boot_packet.generated_at, so a slow acquisition can never produce a
    receipt that postdates document.as_of."""
    runner = FakeRunner()
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(tmp_path / "episode"),
            "--operation-key", "olv1-cli-test-op",
        ]
    )
    rc, out = _capture_stdout(lambda: cli.cmd_compose(args, runner=runner))
    assert rc == 0
    assert "as_of_mode=auto(max_observed_at)" in out


def test_compose_stale_explicit_as_of_refused_up_front(tmp_path):
    """Addendum A: an explicit --as-of that predates the boot packet's own
    generated_at is refused BEFORE composing, with a clear message — never allowed to
    surface later as A1's opaque "source receipt cannot postdate document.as_of"."""
    runner = FakeRunner(boot_generated_at="2026-09-02T12:30:00Z")
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(tmp_path / "episode"),
            "--as-of", "2026-09-02T12:00:00Z",  # predates boot_generated_at above
            "--operation-key", "olv1-cli-test-op",
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="predates boot_packet.generated_at"):
        cli.cmd_compose(args, runner=runner)


# --------------------------------------------------------------------------- BLOCKER 3: seal re-verifies


def test_seal_refuses_a_tampered_composition(tmp_path):
    """BLOCKER 3: composition.json is editable on disk between compose and seal.
    Hand-editing a REFUSED disposition to ELIGIBLE_WITHIN_DELEGATION must not sail
    through — seal re-runs evaluate_bundle(bundle.json) and refuses on any digest
    mismatch."""
    runner = FakeRunner(macro_sha=SHA40_B, boot_macro_sha="d" * 40)  # forces REFUSED
    episode_dir = tmp_path / "episode"
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(episode_dir),
            "--as-of", "2026-09-02T12:00:00Z",
            "--operation-key", "olv1-cli-test-op",
        ]
    )
    rc = cli.cmd_compose(args, runner=runner)
    assert rc == 4  # confirms the fixture actually produced a REFUSED canary

    composition_path = episode_dir / "composition.json"
    composition = json.loads(composition_path.read_text())
    for item in composition["packet"]["adjudications"]:
        if item["option_id"] == "OPT-OLV1-PR-TITLE-CANARY":
            item["disposition"] = "ELIGIBLE_WITHIN_DELEGATION"
            item["reason"] = "EXPLICIT_DELEGATION_ENVELOPE"
    composition["packet"]["selection_state"] = "UNIQUE_ACTIONABLE_FRONTIER"
    composition["packet"]["recommended_option_id"] = "OPT-OLV1-PR-TITLE-CANARY"
    composition_path.write_text(json.dumps(composition, indent=2, sort_keys=True))

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    seal_args = [
        "seal",
        "--composition", str(composition_path),
        "--episode-dir", str(episode_dir),
        "--parent-head", SHA40_A,
        "--recorded-at", "2026-09-02T12:01:00Z",
        "--operation-key", "olv1-cli-test-op",
        "--out-expectation", str(outside_dir / "expectation.json"),
        "--out-request", str(outside_dir / "request.json"),
    ]
    with pytest.raises(cli.OutcomeLearningCliError, match="does not match a fresh"):
        cli.cmd_seal(cli._parser().parse_args(seal_args))


# --------------------------------------------------------------------------- MAJOR 5: freshness/drift gate


def test_canary_refuses_with_zero_patches_when_pr_has_drifted(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    # A different title than what preflight observed — simulating drift between
    # preflight and canary.
    transport = FakeTransport(title="Someone changed this title")
    _run_preflight(outside_dir, FakeTransport())  # preflight observes "Some PR title"
    # Overwrite the observed preflight with the ORIGINAL clean title, then hand canary
    # a transport whose live title has since drifted.
    rc = cli.cmd_canary(
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", str(outside_dir / "preflight.json"),
                "--request", str(outside_dir / "request.json"),
                "--recorded-at", "2026-09-02T12:03:00Z",
                "--episode-dir", str(outside_dir),
            ]
        ),
        transport=transport,
    )
    assert rc == 6
    assert transport.patches == 0
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    assert journal["effect_state"] == "INVALIDATED_BEFORE_EFFECT"
    assert journal["effect_calls"] == []


# --------------------------------------------------------------------------- BLOCKER 1: failed-restore truth


def test_apply_succeeds_restore_raises_journals_call1_and_observed_poststate(tmp_path):
    """BLOCKER 1: the apply completed (readback known); the restore PATCH raises.
    The journal must carry call1 (never effect_calls: []), and cmd_outcome's
    restoration.poststate_title_sha256 must come from the reconciliation GET's
    OBSERVED title — here, still the mutated (canary-token-appended) title, never a
    guessed "nothing changed"."""
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport(raise_on_restore=True)
    _run_preflight(outside_dir, transport)

    rc = cli.cmd_canary(
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", str(outside_dir / "preflight.json"),
                "--request", str(outside_dir / "request.json"),
                "--recorded-at", "2026-09-02T12:03:00Z",
                "--episode-dir", str(outside_dir),
            ]
        ),
        transport=transport,
    )
    assert rc == 3
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    assert journal["effect_state"] == "EFFECT_UNKNOWN"
    assert len(journal["effect_calls"]) == 1
    assert journal["effect_calls"][0]["kind"] == "TITLE_APPLY"
    assert journal["reconciliation"]["attempted"] is True
    assert journal["reconciliation"]["observed_title_sha256"] is not None
    # The live title is still the MUTATED one (restore never actually succeeded) —
    # reconciliation observed exactly that, not the original.
    mutated_title_sha = cli._sha256_hex_text(transport.title)
    assert journal["reconciliation"]["observed_title_sha256"] == mutated_title_sha
    assert transport.title != "Some PR title"

    rc = cli.main(
        [
            "outcome",
            "--journal", str(_journal_path(outside_dir, request)),
            "--preflight", str(outside_dir / "preflight.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--request", str(outside_dir / "request.json"),
            "--recorded-at", "2026-09-02T12:04:00Z",
            "--out", str(outside_dir / "outcome.json"),
        ]
    )
    assert rc == 0
    outcome = json.loads((outside_dir / "outcome.json").read_text())
    restoration = outcome["restoration"]
    # The blocker's core assertion: NOT a durable "nothing changed" receipt.
    assert restoration["poststate_title_sha256"] == mutated_title_sha
    assert restoration["byte_identical"] is False
    assert restoration["poststate_title_sha256"] != restoration["prestate_title_sha256"]


def test_apply_raises_and_reconciliation_also_fails_reports_unobserved(tmp_path):
    """The apply itself raises, and even the one reconciliation GET fails — the only
    honest poststate is the literal UNOBSERVED, never a guessed hash."""
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)

    class DeadTransport(FakeTransport):
        def get(self, endpoint):
            if self.gets == 0:
                self.gets += 1
                return super().get(endpoint)
            if self.gets == 1:
                self.gets += 1
                return super().get(endpoint)
            raise RuntimeError("reconciliation GET also failed")

        def patch(self, endpoint, payload):
            raise RuntimeError("apply raised")

    transport = DeadTransport()
    _run_preflight(outside_dir, FakeTransport())

    rc = cli.cmd_canary(
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", str(outside_dir / "preflight.json"),
                "--request", str(outside_dir / "request.json"),
                "--recorded-at", "2026-09-02T12:03:00Z",
                "--episode-dir", str(outside_dir),
            ]
        ),
        transport=transport,
    )
    assert rc == 3
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    assert journal["effect_calls"] == []
    assert journal["reconciliation"]["observed_title_sha256"] is None

    rc = cli.main(
        [
            "outcome",
            "--journal", str(_journal_path(outside_dir, request)),
            "--preflight", str(outside_dir / "preflight.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--request", str(outside_dir / "request.json"),
            "--recorded-at", "2026-09-02T12:04:00Z",
            "--out", str(outside_dir / "outcome.json"),
        ]
    )
    assert rc == 0
    outcome = json.loads((outside_dir / "outcome.json").read_text())
    assert outcome["restoration"]["poststate_title_sha256"] == "UNOBSERVED"
    assert outcome["restoration"]["byte_identical"] is None

    rc = cli.main(
        [
            "evaluate",
            "--expectation", str(outside_dir / "expectation.json"),
            "--outcome", str(outside_dir / "outcome.json"),
            "--request", str(outside_dir / "request.json"),
            "--recorded-at", "2026-09-02T12:05:00Z",
            "--out", str(outside_dir / "evaluation.json"),
        ]
    )
    assert rc == 0
    evaluation = json.loads((outside_dir / "evaluation.json").read_text())
    by_id = {e["assumption_id"]: e["resolution"] for e in evaluation["assumption_resolutions"]}
    # MAJOR 9: A3 confounded on EFFECT_UNKNOWN with unobserved poststate; A4
    # NOT_TESTED since effect_calls is empty.
    assert by_id["OLV1-A3"] == "CONFOUNDED"
    assert by_id["OLV1-A4"] == "NOT_TESTED"

    # MAJOR 12: the proof's per-effect_state bullets must name the unresolved
    # restoration explicitly rather than silently omitting it.
    bullets = cli._proof_effect_state_bullets(outcome)
    assert any("MANUAL RESTORATION MAY BE OWED" in line for line in bullets)


# --------------------------------------------------------------------------- kill test #11


def test_kill_11_single_shot_journal_refuses_second_canary_invocation(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    _run_preflight(outside_dir, transport)

    canary_args = cli._parser().parse_args(
        [
            "canary",
            "--preflight", str(outside_dir / "preflight.json"),
            "--request", str(outside_dir / "request.json"),
            "--recorded-at", "2026-09-02T12:03:00Z",
            "--episode-dir", str(outside_dir),
        ]
    )
    rc = cli.cmd_canary(canary_args, transport=transport)
    assert rc == 0
    assert transport.patches == 2
    assert _journal_path(outside_dir, request).exists()

    with pytest.raises(cli.OutcomeLearningCliError, match="single-shot"):
        cli.cmd_canary(canary_args, transport=transport)
    # No further PATCHes were issued by the refused second invocation.
    assert transport.patches == 2


# --------------------------------------------------------------------------- ambiguity (mismatch, no exception)


def test_ambiguous_readback_mismatch_without_exception_reports_effect_unknown(tmp_path):
    """Both PATCHes complete without raising, but the head_sha in the APPLY's own
    response has moved (a concurrent branch push mid-episode, after the pre-effect
    freshness gate already passed) — an ambiguous result detected by comparison,
    never by exception, and MUST still yield exactly 2 completed calls (no retry) and
    effect_state=EFFECT_UNKNOWN."""
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)

    class DriftMidSequenceTransport(FakeTransport):
        def patch(self, endpoint, payload):
            self.patches += 1
            self.title = payload["title"]
            # Only the APPLY response reports a head that no longer matches
            # preflight.sealed_commit_sha — simulating a concurrent push landing
            # between the freshness check and the apply's own response.
            reported_head = "c" * 40 if self.patches == 1 else self.head_sha
            return 200, {
                "number": self.pr_number,
                "title": self.title,
                "head": {"sha": reported_head},
                "base": {"ref": "master"},
            }

    transport = DriftMidSequenceTransport()
    _run_preflight(outside_dir, transport)

    rc = cli.cmd_canary(
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", str(outside_dir / "preflight.json"),
                "--request", str(outside_dir / "request.json"),
                "--recorded-at", "2026-09-02T12:03:00Z",
                "--episode-dir", str(outside_dir),
            ]
        ),
        transport=transport,
    )
    assert rc == 3
    assert transport.patches == 2  # both calls completed; no retry was ever issued
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    assert journal["effect_state"] == "EFFECT_UNKNOWN"
    assert len(journal["effect_calls"]) == 2
    assert journal["reconciliation"] is None  # no exception, so no reconciliation was needed


# --------------------------------------------------------------------------- outside-repo refusal


def test_preflight_out_refuses_a_path_inside_the_repository_worktree(tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    inside_repo_path = cli._ROOT / "research" / "outcome_learning" / "preflight_should_not_land_here.json"

    args = cli._parser().parse_args(
        [
            "preflight",
            "--repo", "mastermindx-market-intelligence/Mastermind",
            "--branch", "sol/outcome-learning-v1-complete-vertical-20260902",
            "--sealed-commit", SHA40_B,
            "--expectation", str(outside_dir / "expectation.json"),
            "--request", str(outside_dir / "request.json"),
            "--observed-at", "2026-09-02T12:02:00Z",
            "--out", str(inside_repo_path),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="outside the repository worktree"):
        cli.cmd_preflight(args, runner=FakeRunner(), transport=FakeTransport())


def test_canary_episode_dir_refuses_a_path_inside_the_repository_worktree(tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "preflight.json").write_text(
        json.dumps(
            {
                "observed_at": "2026-09-02T12:02:00Z",
                "repository": "mastermindx-market-intelligence/Mastermind",
                "pr_number": 42,
                "pr_url": "https://x/42",
                "head_sha": SHA40_B,
                "base_ref": "master",
                "original_title_sha256": "f" * 64,
                "original_title_length": 5,
                "sealed_commit_sha": SHA40_B,
                "expectation_blob_sha": SHA40_A,
                "request_blob_sha": SHA40_A,
                "expectation_content_sha256": "c" * 64,
                "request_content_sha256": "d" * 64,
                "head_equals_sealed_commit": True,
            }
        )
    )
    (outside_dir / "request.json").write_text(
        json.dumps(
            {
                "repository": "mastermindx-market-intelligence/Mastermind",
                "canary_token": "[OL-V1-CANARY]",
                "operation_key": "op-1",
                "expectation_sealed_hash": "sha256:" + "e" * 64,
            }
        )
    )
    inside_repo_dir = cli._ROOT / "research" / "outcome_learning"

    args = cli._parser().parse_args(
        [
            "canary",
            "--preflight", str(outside_dir / "preflight.json"),
            "--request", str(outside_dir / "request.json"),
            "--recorded-at", "2026-09-02T12:03:00Z",
            "--episode-dir", str(inside_repo_dir),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="outside the repository worktree"):
        cli.cmd_canary(args, transport=FakeTransport())


# --------------------------------------------------------------------------- MINORS: truth-pin


def test_hold_classification_owner_is_a_real_allowed_owner():
    """MINORS truth-pin: the HOLD-option classification receipt's owner must be a
    member of BOTH of control_plane.chairman_cognition's allowed-owner frozensets —
    imported directly here so a future rename of either set fails this test loudly
    instead of failing silently at compose time."""
    assert cli._HOLD_CLASSIFICATION_SOURCE_OWNER in ALLOWED_SOURCE_OWNERS
    assert cli._HOLD_CLASSIFICATION_SOURCE_OWNER in CLASSIFICATION_SOURCE_OWNERS
    assert cli._HOLD_CLASSIFICATION_SOURCE_OWNER != "STEWARD"


# --------------------------------------------------------------------------- COVERAGE: discriminating guards


def test_coverage_preflight_head_matches_sealed_commit(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport(head_sha=SHA40_B)
    preflight = _run_preflight(outside_dir, transport)
    assert preflight["head_sha"] == preflight["sealed_commit_sha"] == SHA40_B
    assert preflight["head_equals_sealed_commit"] is True


def test_coverage_restoration_poststate_and_prestate_equal_original_on_success(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    _run_preflight(outside_dir, transport)
    cli.cmd_canary(
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", str(outside_dir / "preflight.json"),
                "--request", str(outside_dir / "request.json"),
                "--recorded-at", "2026-09-02T12:03:00Z",
                "--episode-dir", str(outside_dir),
            ]
        ),
        transport=transport,
    )
    cli.main(
        [
            "outcome",
            "--journal", str(_journal_path(outside_dir, request)),
            "--preflight", str(outside_dir / "preflight.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--request", str(outside_dir / "request.json"),
            "--recorded-at", "2026-09-02T12:04:00Z",
            "--out", str(outside_dir / "outcome.json"),
        ]
    )
    outcome = json.loads((outside_dir / "outcome.json").read_text())
    original_sha = cli._sha256_hex_text("Some PR title")
    assert outcome["restoration"]["prestate_title_sha256"] == original_sha
    assert outcome["restoration"]["poststate_title_sha256"] == original_sha


def test_coverage_every_readback_head_equals_sealed_commit_on_success(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    _run_preflight(outside_dir, transport)
    cli.cmd_canary(
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", str(outside_dir / "preflight.json"),
                "--request", str(outside_dir / "request.json"),
                "--recorded-at", "2026-09-02T12:03:00Z",
                "--episode-dir", str(outside_dir),
            ]
        ),
        transport=transport,
    )
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    for call in journal["effect_calls"]:
        assert call["readback"]["head_sha"] == transport.head_sha


def test_coverage_call_kind_ordering_is_apply_then_restore(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    _run_preflight(outside_dir, transport)
    cli.cmd_canary(
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", str(outside_dir / "preflight.json"),
                "--request", str(outside_dir / "request.json"),
                "--recorded-at", "2026-09-02T12:03:00Z",
                "--episode-dir", str(outside_dir),
            ]
        ),
        transport=transport,
    )
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    kinds = [c["kind"] for c in journal["effect_calls"]]
    assert kinds == ["TITLE_APPLY", "TITLE_RESTORE"]


def test_coverage_seq_rule_positions_seq_to_index(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    _run_preflight(outside_dir, transport)
    cli.cmd_canary(
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", str(outside_dir / "preflight.json"),
                "--request", str(outside_dir / "request.json"),
                "--recorded-at", "2026-09-02T12:03:00Z",
                "--episode-dir", str(outside_dir),
            ]
        ),
        transport=transport,
    )
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    seqs = [c["seq"] for c in journal["effect_calls"]]
    assert seqs == [1, 2]
