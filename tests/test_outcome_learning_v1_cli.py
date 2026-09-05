"""CLI tests for the Outcome Learning V1 (OL-V1) vertical.

Every test injects a Fake transport/runner — this module NEVER invokes real git,
gh, or network I/O. The end-to-end happy path exercises
seal -> preflight -> canary -> outcome -> evaluate -> self-model -> project -> proof
and asserts the artifact cross-digests verify.

Sol REQUEST_REPAIR passes folded in here (2026-09-02, most recent first):

* PR #398 review 5109215567 (BLOCKERS A-F): canonical-GitHub source identity for
  compose (ls-remote + Contents API, never local branch/working-tree self-attest);
  A1-packet-derived operation/parent/repo/branch ancestry at seal, cross-checked at
  preflight before any transport call; canary reacquires the request from its
  committed blob and re-runs the owner branch selector before the first PATCH;
  an atomic exclusive-create journal reservation + explicit state machine so a crash
  or a same-directory race can never replay an effect; truthful drift observation
  embedded in an INVALIDATED_BEFORE_EFFECT outcome; proof validates + cross-binds
  every artifact before rendering, and process-quality is derived from the
  ``effect_edge`` receipt, never ``head_equals_sealed_commit`` alone.
* Committed-seal blob provenance (preflight can no longer fall back to a local,
  uncommitted `git hash-object` fingerprint).
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
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


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- strategic state fixture


_STRATEGIC_STATE_YAML = """\
schema: mastermind.strategic_state.v1
meta:
  owner: test
departments: [executive]
statuses: [active]
constraint_levels: [permitted, constrained, prohibited]
company_phase: TEST_PHASE
north_star: ["test north star"]
p0:
  - id: TEST_OBJ
    department: executive
    objective: test objective
    status: active
resource_policy:
  executive: 1.0
constraints:
  new_feature_expansion: constrained
  autonomous_production_deploy: prohibited
  autonomous_live_capital_execution: prohibited
  duplicate_control_planes: prohibited
  marketing_org_expansion_before_distribution_proof: prohibited
  unbounded_autonomous_strategic_modification: prohibited
review_triggers: ["test trigger"]
"""
_STRATEGIC_STATE_BLOB_SHA = "1" * 40


def _boot_packet(
    *,
    mastermind_sha=SHA40_A,
    macro_sha=SHA40_B,
    mastermind_branch="master",
    degradation=None,
    generated_at="2026-09-02T12:00:00Z",
):
    """``degradation`` is a real owner-degradation channel: ``"inputs"`` sets
    ``inputs.degraded`` non-empty, ``"readiness"`` sets ``readiness.degraded``
    non-empty, ``"warnings"`` sets ``warnings`` non-empty (kept ONLY to prove the
    advisory-warnings-vs-actual-degradation distinction: nonempty valid warnings must
    NOT, by themselves, force AGENT_OS state UNKNOWN in this repaired build — the
    current-base integration requirement)."""
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
            "company_phase": "IGNORED_LOCAL_PROJECTION",
            "north_star": ["ignored"],
            "p0": [],
            "constraints": {},
        },
        "brief": {
            "schema": "ceo_brief.v1",
            "generated_at": generated_at,
            "since": "2026-09-01T12:00:00Z",
            "since_label": "the last 24h",
            "counts": {"total": 0, "active": 0, "awaiting_ci": 0, "blocked": 0, "done_in_window": 0},
            "inputs": {
                "active_builds_age_hours": 1.0,
                "worktrees": 1,
                "degraded": (
                    ["fixture: real degradation channel"] if degradation == "inputs" else []
                ),
            },
            "needs_ceo": [],
            "blocked": [],
            "finished": [],
            "running": {
                "active": 0, "awaiting_ci": 0, "awaiting_review": 0, "blocked": 0,
                "proposed": 0, "open_prs": 0, "stale_claims": 0, "claims_without_worktree": 0,
            },
            "readiness": {
                "schema": "agentos.readiness.v1",
                "records": [],
                "degraded": (
                    ["fixture: real readiness degradation channel"]
                    if degradation == "readiness"
                    else []
                ),
            },
            "warnings": (
                ["fixture: advisory warning, never itself owner-degradation"]
                if degradation == "warnings"
                else []
            ),
        },
        "handoffs": [],
        "degraded": [],
        "next_recommended_act": "Consult the canonical Improvement Agenda.",
    }


class FakeRunner:
    """Deterministic stand-in for every git/gh/subprocess call this CLI makes.
    Defaults produce a fully-CURRENT, happy-path canonical identity."""

    def __init__(
        self,
        *,
        mastermind_canonical_sha=SHA40_A,
        macro_canonical_sha=SHA40_B,
        macro_local_sha=None,
        macro_dirty=False,
        strategic_state_yaml=_STRATEGIC_STATE_YAML,
        strategic_state_unresolvable=False,
        boot_macro_sha=None,
        boot_mastermind_sha=None,
        degradation=None,
        boot_generated_at="2026-09-02T12:00:00Z",
        committed_blobs: dict[str, str] | None = None,
        sealed_commit_parent: str | None = None,
    ):
        self.mastermind_canonical_sha = mastermind_canonical_sha
        self.macro_canonical_sha = macro_canonical_sha
        self.macro_local_sha = macro_local_sha if macro_local_sha is not None else macro_canonical_sha
        self.macro_dirty = macro_dirty
        self.strategic_state_yaml = strategic_state_yaml
        self.strategic_state_unresolvable = strategic_state_unresolvable
        self.boot_macro_sha = boot_macro_sha if boot_macro_sha is not None else self.macro_local_sha
        self.boot_mastermind_sha = (
            boot_mastermind_sha if boot_mastermind_sha is not None else mastermind_canonical_sha
        )
        self.degradation = degradation
        self.boot_generated_at = boot_generated_at
        self.committed_blobs = dict(committed_blobs or {})
        self.sealed_commit_parent = sealed_commit_parent
        self.calls: list[tuple] = []

    def _blob_id_for(self, path: str) -> str:
        return _sha1(path)

    def run(self, args, *, cwd=None, input=None):
        self.calls.append((tuple(args), cwd, input))

        if args[:2] == ["git", "ls-remote"]:
            url, ref = args[2], args[3]
            if url == cli._CANONICAL_MASTERMIND_URL and ref == "refs/heads/master":
                return cli.RunResult(0, f"{self.mastermind_canonical_sha}\trefs/heads/master\n", "")
            if url == cli._CANONICAL_MACRO_URL and ref == "refs/heads/main":
                return cli.RunResult(0, f"{self.macro_canonical_sha}\trefs/heads/main\n", "")
            return cli.RunResult(1, "", f"fatal: could not resolve {ref} on {url}")

        if args[:2] == ["gh", "api"] and "contents/config/strategic_state.yml" in args[2]:
            if self.strategic_state_unresolvable:
                return cli.RunResult(1, "", "404: Not Found")
            payload = {
                "sha": _STRATEGIC_STATE_BLOB_SHA,
                "content": base64.b64encode(self.strategic_state_yaml.encode("utf-8")).decode("ascii"),
                "encoding": "base64",
            }
            return cli.RunResult(0, json.dumps(payload), "")

        if args[:3] == ["git", "rev-parse", "HEAD"]:
            if cwd == "/y":
                return cli.RunResult(0, self.macro_local_sha + "\n", "")
            return cli.RunResult(0, self.boot_mastermind_sha + "\n", "")

        if args[:2] == ["git", "status"] and "--porcelain" in args:
            output = "M data/scratch.parquet\n M control_plane/mutated.py\n" if self.macro_dirty else ""
            return cli.RunResult(0, output, "")

        if len(args) >= 2 and "ceo_boot_packet.py" in args[1]:
            boot = _boot_packet(
                mastermind_sha=self.boot_mastermind_sha,
                macro_sha=self.boot_macro_sha,
                degradation=self.degradation,
                generated_at=self.boot_generated_at,
            )
            return cli.RunResult(0, json.dumps(boot), "")
        if len(args) >= 2 and "agentos.py" in args[1]:
            return cli.RunResult(0, json.dumps({"source_records_digest": "sha256:" + "e" * 64}), "")

        if args[:2] == ["git", "rev-parse"] and len(args) == 3 and args[2].endswith("^"):
            if self.sealed_commit_parent is None:
                return cli.RunResult(1, "", "fatal: no parent for this commit")
            return cli.RunResult(0, self.sealed_commit_parent + "\n", "")

        if args[:2] == ["git", "rev-parse"] and len(args) == 3 and ":" in args[2]:
            _sealed, _, repo_path = args[2].partition(":")
            if repo_path in self.committed_blobs:
                return cli.RunResult(0, self._blob_id_for(repo_path) + "\n", "")
            return cli.RunResult(1, "", f"fatal: path '{repo_path}' does not exist in the given commit")

        if args[:2] == ["git", "cat-file"]:
            blob_id = args[-1]
            for path, text in self.committed_blobs.items():
                if self._blob_id_for(path) == blob_id:
                    return cli.RunResult(0, text, "")
            return cli.RunResult(1, "", f"fatal: not a valid object name {blob_id}")

        raise AssertionError(f"unexpected FakeRunner call: {args} (cwd={cwd})")


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
        pr_number=42,
        selector_prs=None,
    ):
        self.title = title
        self.head_sha = head_sha
        self.pr_number = pr_number
        self.gets = 0
        self.patches = 0
        self._raise_on_apply = raise_on_apply
        self._raise_on_restore = raise_on_restore
        # None -> the single-PR-matching-pr_number happy path; else an explicit list
        # of PR summaries to return from the owner branch selector.
        self._selector_prs = selector_prs

    def get(self, endpoint):
        self.gets += 1
        if endpoint.endswith("&state=open"):
            if self._selector_prs is not None:
                return 200, self._selector_prs
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


EXPECTATION_REPO_PATH = "research/outcome_learning/OLV1_EXPECTATION_TEST.json"
REQUEST_REPO_PATH = "research/outcome_learning/OLV1_CANARY_REQUEST_TEST.json"


def _compose_and_seal(
    tmp_path: Path, runner: FakeRunner | None = None, *, as_of: str | None = "2026-09-02T12:00:00Z"
) -> tuple[Path, dict, dict]:
    """Run compose (fully-CURRENT canonical-identity fixture) then seal.

    compose's gate is disposition-keyed on the canary option alone (principal
    correction, 2026-09-02): an honest, near-zero-cost READ_ONLY HOLD is never
    Pareto-dominated, so this fixture's ``selection_state`` is lawfully
    ``MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS`` with ``recommended_option_id=None``
    — that is not a failure, and compose still exits 0 with ``COMPOSE_OK`` because
    the canary option itself is ``ELIGIBLE_WITHIN_DELEGATION``. seal derives
    operation_key/expected_parent_head/repository/branch from that adjudicated
    option (BLOCKER B) and picks the truthful
    ``principal_selection_from_a1_incomparable_frontier`` assignment method."""
    runner = runner or FakeRunner()
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
            "--recorded-at", "2026-09-02T12:01:00Z",
            "--out-expectation", str(outside_dir / "expectation.json"),
            "--out-request", str(outside_dir / "request.json"),
        ]
    )
    assert rc == 0
    expectation = json.loads((outside_dir / "expectation.json").read_text())
    request = json.loads((outside_dir / "request.json").read_text())
    return outside_dir, expectation, request


def _preflight_runner_for(outside_dir: Path, *, sealed_commit_parent: str) -> FakeRunner:
    """A FakeRunner whose committed_blobs echo the actual on-disk expectation/request
    file contents — the honest happy-path fixture: the sealed commit really does
    contain the exact bytes preflight is being asked to prove, and its parent really
    is what the sealed request claims."""
    return FakeRunner(
        committed_blobs={
            EXPECTATION_REPO_PATH: (outside_dir / "expectation.json").read_text(encoding="utf-8"),
            REQUEST_REPO_PATH: (outside_dir / "request.json").read_text(encoding="utf-8"),
        },
        sealed_commit_parent=sealed_commit_parent,
    )


def _run_preflight(
    outside_dir: Path,
    transport: FakeTransport,
    request: dict,
    *,
    runner: FakeRunner | None = None,
) -> dict:
    runner = runner or _preflight_runner_for(
        outside_dir, sealed_commit_parent=request["expected_parent_head"]
    )
    rc = cli.cmd_preflight(
        cli._parser().parse_args(
            [
                "preflight",
                "--repo", request["repository"],
                "--branch", request["branch"],
                "--sealed-commit", transport.head_sha,
                "--expectation", str(outside_dir / "expectation.json"),
                "--request", str(outside_dir / "request.json"),
                "--expectation-repo-path", EXPECTATION_REPO_PATH,
                "--request-repo-path", REQUEST_REPO_PATH,
                "--mastermind-root", "/x",
                "--observed-at", "2026-09-02T12:02:00Z",
                "--out", str(outside_dir / "preflight.json"),
            ]
        ),
        runner=runner,
        transport=transport,
    )
    assert rc == 0
    return json.loads((outside_dir / "preflight.json").read_text())


def _run_canary(
    outside_dir: Path,
    preflight: dict,
    transport: FakeTransport,
    *,
    runner: FakeRunner | None = None,
    recorded_at: str = "2026-09-02T12:03:00Z",
):
    runner = runner or FakeRunner()
    args = cli._parser().parse_args(
        [
            "canary",
            "--preflight", str(outside_dir / "preflight.json"),
            "--request", str(outside_dir / "request.json"),
            "--mastermind-root", "/x",
            "--recorded-at", recorded_at,
            "--episode-dir", str(outside_dir),
        ]
    )
    return cli.cmd_canary(args, runner=runner, transport=transport)


def _canary_runner_for(outside_dir: Path) -> FakeRunner:
    """A FakeRunner that can serve BLOCKER C's committed-blob request reacquisition
    (keyed by blob id, not repo-path — canary reacquires via
    preflight.request_blob_sha directly)."""
    return FakeRunner(
        committed_blobs={
            REQUEST_REPO_PATH: (outside_dir / "request.json").read_text(encoding="utf-8"),
        }
    )


# --------------------------------------------------------------------------- happy path


def test_end_to_end_seal_through_proof_cross_digests_verify(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    assert (
        expectation["assignment"]["method"]
        == "principal_selection_from_a1_incomparable_frontier"
    )
    transport = FakeTransport()
    preflight = _run_preflight(outside_dir, transport, request)

    rc = _run_canary(
        outside_dir, preflight, transport, runner=_canary_runner_for(outside_dir)
    )
    assert rc == 0
    journal_path = _journal_path(outside_dir, request)
    assert journal_path.exists()
    journal = json.loads(journal_path.read_text())
    assert journal["state"] == "RESTORED"
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
    assert outcome["pre_effect_observation"] is None
    assert all(outcome["effect_edge"].values())

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


# --------------------------------------------------------------------------- BLOCKER A: canonical source identity


def test_repair_a_commit_vs_blob_identity_source_blob_sha_is_a_real_blob(tmp_path):
    """The mastermind attestation's source_blob_sha must be the config blob sha
    (from the Contents API), never the commit sha."""
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    episode_dir = Path(str(outside_dir).replace("outside", "episode"))
    bundle = json.loads((episode_dir / "bundle.json").read_text())
    attestation = bundle["mastermind_revision_attestation"]
    assert attestation["source_blob_sha"] == _STRATEGIC_STATE_BLOB_SHA
    assert attestation["source_blob_sha"] != attestation["revision"]
    assert attestation["revision"] == SHA40_A  # the canonical ls-remote sha


def test_repair_a_protected_source_unreachable_refuses_typed(tmp_path):
    runner = FakeRunner(strategic_state_unresolvable=True)
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
    assert "BLOCKER SOURCE_IDENTITY_UNVERIFIED" in out


def test_repair_a_local_macro_checkout_mismatched_refuses(tmp_path):
    """Independent Macro state: the local macro checkout HEAD disagrees with
    canonical macro main."""
    runner = FakeRunner(macro_local_sha="c" * 40, boot_macro_sha="c" * 40)
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
    assert "BLOCKER SOURCE_IDENTITY_UNVERIFIED" in out
    assert "does not match canonical macro main" in out


def test_repair_a_dirty_macro_checkout_refuses(tmp_path):
    runner = FakeRunner(macro_dirty=True)
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
    assert "BLOCKER SOURCE_IDENTITY_UNVERIFIED" in out
    assert "not clean" in out


def test_repair_a_override_caps_agentos_state_at_unknown(tmp_path):
    """(3) --agentos-records-digest may never participate in a CURRENT claim."""
    runner = FakeRunner()
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(tmp_path / "episode"),
            "--as-of", "2026-09-02T12:00:00Z",
            "--operation-key", "olv1-cli-test-op",
            "--agentos-records-digest", "sha256:" + "f" * 64,
        ]
    )
    rc, out = _capture_stdout(lambda: cli.cmd_compose(args, runner=runner))
    assert "SOURCE AGENT_OS:ceo_brief=UNKNOWN" in out
    # Structurally UNKNOWN can never be load-bearing-CURRENT for the canary option,
    # so this must not reach COMPOSE_OK.
    assert rc != 0
    assert "COMPOSE_OK" not in out


# --------------------------------------------------------------------------- current-base integration fixture


def test_repair_advisory_warnings_alone_do_not_force_agentos_unknown(tmp_path):
    """Current-base integration requirement: nonempty valid warnings are advisory —
    they must NOT, by themselves, force AGENT_OS:ceo_brief into UNKNOWN. Only a real
    owner-degradation channel (inputs.degraded / readiness.degraded) does."""
    runner = FakeRunner(degradation="warnings")
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
    # This assertion intentionally documents CURRENT repository behavior (pre-#422):
    # warnings alone still degrades AGENT_OS state today (PR #422, which flips this
    # to advisory-CURRENT, is separately held). What the current-base integration
    # requirement demands is that OL-V1's OWN fixtures never rely on warnings to
    # manufacture UNKNOWN — see the two tests immediately below — so this test only
    # pins today's fact for contrast, not a repaired behavior this build owns.
    assert "SOURCE AGENT_OS:ceo_brief=" in out


def test_repair_real_degradation_channel_inputs_degraded_forces_unknown(tmp_path):
    runner = FakeRunner(degradation="inputs")
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


def test_repair_real_degradation_channel_readiness_degraded_forces_unknown(tmp_path):
    runner = FakeRunner(degradation="readiness")
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
    boot packet missing a load-bearing strategic constraint) is a COMPOSITION defect,
    never an owner-source state — it must render as BLOCKER COMPOSITION_INVALID and
    exit 5, never the BLOCKER OWNER_SOURCE_NOT_CURRENT template."""
    runner = FakeRunner(
        strategic_state_yaml=_STRATEGIC_STATE_YAML.replace(
            "  new_feature_expansion: constrained\n", ""
        )
    )
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
    # Either the canonical strategic-state read itself refuses (missing required
    # constraint) or, if it somehow parsed, A1's own composition refuses — both are
    # legitimately BLOCKER-class, never OWNER_SOURCE_NOT_CURRENT.
    assert "BLOCKER" in out
    assert "OWNER_SOURCE_NOT_CURRENT" not in out


def test_compose_as_of_auto_computed_when_omitted(tmp_path):
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


# --------------------------------------------------------------------------- BLOCKER B: A1-seal ancestry


def test_repair_b_operation_key_mismatch_refuses(tmp_path):
    runner = FakeRunner()
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
    assert cli.cmd_compose(args, runner=runner) == 0

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    with pytest.raises(cli.OutcomeLearningCliError, match="does not match the adjudicated"):
        cli.cmd_seal(
            cli._parser().parse_args(
                [
                    "seal",
                    "--composition", str(episode_dir / "composition.json"),
                    "--episode-dir", str(episode_dir),
                    "--recorded-at", "2026-09-02T12:01:00Z",
                    "--operation-key", "a-completely-different-op",
                    "--out-expectation", str(outside_dir / "expectation.json"),
                    "--out-request", str(outside_dir / "request.json"),
                ]
            )
        )


def test_repair_b_parent_head_mismatch_refuses(tmp_path):
    runner = FakeRunner()
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
    assert cli.cmd_compose(args, runner=runner) == 0

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    with pytest.raises(cli.OutcomeLearningCliError, match="does not match the adjudicated"):
        cli.cmd_seal(
            cli._parser().parse_args(
                [
                    "seal",
                    "--composition", str(episode_dir / "composition.json"),
                    "--episode-dir", str(episode_dir),
                    "--parent-head", "c" * 40,
                    "--recorded-at", "2026-09-02T12:01:00Z",
                    "--out-expectation", str(outside_dir / "expectation.json"),
                    "--out-request", str(outside_dir / "request.json"),
                ]
            )
        )


def test_repair_b_operation_key_grammar_rejects_dots_and_colons():
    from control_plane.outcome_learning_contracts import (
        OutcomeLearningContractError,
        _operation_key,
    )

    with pytest.raises(OutcomeLearningContractError, match="operation_key must match"):
        _operation_key("has.a.dot")
    with pytest.raises(OutcomeLearningContractError, match="operation_key must match"):
        _operation_key("has:a:colon")
    with pytest.raises(OutcomeLearningContractError, match="operation_key must match"):
        _operation_key("../traversal")
    assert _operation_key("lowercase-and-hyphens-99") == "lowercase-and-hyphens-99"


def test_repair_b_preflight_proves_parent_ancestry(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    preflight_runner = FakeRunner(
        committed_blobs={
            EXPECTATION_REPO_PATH: (outside_dir / "expectation.json").read_text(encoding="utf-8"),
            REQUEST_REPO_PATH: (outside_dir / "request.json").read_text(encoding="utf-8"),
        },
        sealed_commit_parent="d" * 40,  # WRONG — does not match request.expected_parent_head
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="does not equal request.expected_parent_head"):
        _run_preflight(outside_dir, transport, request, runner=preflight_runner)
    # Zero transport calls — the ancestry check runs before the first GET.
    assert transport.gets == 0


def test_repair_b_preflight_cross_checks_repo_and_branch_before_transport(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    preflight_runner = _preflight_runner_for(
        outside_dir, sealed_commit_parent=request["expected_parent_head"]
    )
    args = cli._parser().parse_args(
        [
            "preflight",
            "--repo", "someone-else/not-the-real-repo",
            "--branch", request["branch"],
            "--sealed-commit", transport.head_sha,
            "--expectation", str(outside_dir / "expectation.json"),
            "--request", str(outside_dir / "request.json"),
            "--expectation-repo-path", EXPECTATION_REPO_PATH,
            "--request-repo-path", REQUEST_REPO_PATH,
            "--mastermind-root", "/x",
            "--observed-at", "2026-09-02T12:02:00Z",
            "--out", str(outside_dir / "preflight.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="does not match the sealed request's repository"):
        cli.cmd_preflight(args, runner=preflight_runner, transport=transport)
    assert transport.gets == 0


# --------------------------------------------------------------------------- BLOCKER C: effect-edge revalidation


def test_repair_c_reacquisition_digest_mismatch_refuses_zero_transport(tmp_path):
    """A post-preflight edit to the (locally readable, never trusted) request.json is
    irrelevant — canary reacquires from the committed BLOB. Forging the committed
    blob content itself (a different blob than what preflight actually verified) is
    what this test simulates, and it must refuse with ZERO transport calls."""
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    preflight = _run_preflight(outside_dir, transport, request)

    forged_request = json.dumps({**request, "operation_key": "a-forged-operation-key"})
    canary_runner = FakeRunner(committed_blobs={REQUEST_REPO_PATH: forged_request})
    live_transport = FakeTransport()
    with pytest.raises(cli.OutcomeLearningCliError, match="does not match"):
        _run_canary(outside_dir, preflight, live_transport, runner=canary_runner)
    assert live_transport.gets == 0
    assert live_transport.patches == 0


def test_repair_c_owner_selector_mismatch_refuses_zero_patches(tmp_path):
    """The owner branch selector is re-run at canary time and must still show exactly
    one open PR whose number agrees with preflight — a second PR (or a renumbered
    one) refuses with zero PATCHes (a GET was necessarily issued to detect this)."""
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    preflight = _run_preflight(outside_dir, transport, request)

    drifted_transport = FakeTransport(selector_prs=[{"number": 42}, {"number": 43}])
    rc = _run_canary(
        outside_dir, preflight, drifted_transport, runner=_canary_runner_for(outside_dir)
    )
    assert rc == 6
    assert drifted_transport.patches == 0
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    assert journal["state"] == "INVALIDATED_BEFORE_EFFECT"
    assert journal["pre_effect_observation"] is None  # never reached the freshness read


# --------------------------------------------------------------------------- BLOCKER D: crash/concurrency


def test_repair_d_crash_after_apply_refuses_next_invocation(tmp_path):
    """A journal frozen at a non-terminal state (simulating a crash after APPLY,
    before the terminal write) must refuse BOTH a second canary invocation (via the
    exclusive-create reservation) AND cmd_outcome (fail-closed, never replay)."""
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    preflight_transport = FakeTransport()
    preflight = _run_preflight(outside_dir, preflight_transport, request)
    journal_path = _journal_path(outside_dir, request)
    journal_path.write_text(
        json.dumps(
            {
                "state": "APPLIED_READBACK",  # non-terminal — simulates a crash here
                "bound_identity": {"operation_key": request["operation_key"]},
                "effect_calls": [],
                "recorded_at": "2026-09-02T12:03:00Z",
            }
        )
    )

    transport = FakeTransport()
    with pytest.raises(cli.OutcomeLearningCliError, match="already exists"):
        _run_canary(outside_dir, preflight, transport, runner=_canary_runner_for(outside_dir))
    assert transport.gets == 0
    assert transport.patches == 0

    with pytest.raises(cli.OutcomeLearningCliError, match="non-terminal state"):
        cli.cmd_outcome(
            cli._parser().parse_args(
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
        )


def test_repair_d_same_dir_concurrency_race_second_invocation_refused(tmp_path):
    """Two invocations racing the reservation: simulate via a pre-created PREPARED
    file (as if a sibling process's open(path, 'x') won the race) and assert the
    second invocation's exclusive-create refuses with zero transport."""
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    preflight_transport = FakeTransport()
    preflight = _run_preflight(outside_dir, preflight_transport, request)
    journal_path = _journal_path(outside_dir, request)
    journal_path.write_text(
        json.dumps(
            {
                "state": "PREPARED",
                "bound_identity": {"operation_key": request["operation_key"]},
                "recorded_at": "2026-09-02T12:03:00Z",
            }
        )
    )
    transport = FakeTransport()
    with pytest.raises(cli.OutcomeLearningCliError, match="single-shot"):
        _run_canary(outside_dir, preflight, transport, runner=_canary_runner_for(outside_dir))
    assert transport.gets == 0
    assert transport.patches == 0


def test_repair_d_reservation_is_exclusive_create_not_exists_check(tmp_path):
    """Directly exercises the reservation primitive: _reserve_journal uses
    open(path, 'x') — a second call on the SAME path always raises, proving the
    guard is the atomic primitive itself, not a separate exists()-then-create
    sequence with a race window between the two."""
    path = tmp_path / "reservation.json"
    cli._reserve_journal(path, {"state": "PREPARED"})
    with pytest.raises(cli.OutcomeLearningCliError, match="already exists"):
        cli._reserve_journal(path, {"state": "PREPARED"})


# --------------------------------------------------------------------------- BLOCKER E: truthful drift


def test_repair_e_drift_outcome_reports_observed_state_honestly(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    preflight = _run_preflight(outside_dir, transport, request)

    drifted_transport = FakeTransport(title="Someone else changed this title entirely")
    rc = _run_canary(
        outside_dir, preflight, drifted_transport, runner=_canary_runner_for(outside_dir)
    )
    assert rc == 6
    assert drifted_transport.patches == 0
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    assert journal["state"] == "INVALIDATED_BEFORE_EFFECT"
    obs = journal["pre_effect_observation"]
    assert obs is not None
    assert obs["observed_title_sha256"] == cli._sha256_hex_text(drifted_transport.title)

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
    # BLOCKER E's core assertion: the drift outcome must NOT claim the original,
    # untouched title — it must report exactly what was observed.
    assert restoration["poststate_title_sha256"] == obs["observed_title_sha256"]
    assert restoration["byte_identical"] is False
    assert restoration["poststate_title_sha256"] != restoration["prestate_title_sha256"]
    assert outcome["pre_effect_observation"] == obs


def test_repair_e_fabricated_byte_identical_rejected_by_contracts():
    """Contracts-level guard: an INVALIDATED_BEFORE_EFFECT outcome whose
    restoration.byte_identical CONTRADICTS the pre_effect_observation must be
    rejected — a fabricated 'nothing changed' claim over a drifted title."""
    import tests.test_outcome_learning_v1 as contracts_tests
    from control_plane.outcome_learning_contracts import (
        OutcomeLearningContractError,
        validate_outcome,
    )

    expectation, request, outcome = contracts_tests.make_episode()
    original_sha = outcome["preflight"]["original_title_sha256"]
    bad = dict(outcome)
    bad["effect_state"] = "INVALIDATED_BEFORE_EFFECT"
    bad["effect_calls"] = []
    bad["pre_effect_observation"] = {
        "observed_head_sha": outcome["preflight"]["sealed_commit_sha"],
        "observed_title_sha256": "9" * 64,  # differs from original_sha
        "observed_title_length": 10,
        "observed_at": contracts_tests.RECORDED_AT,
    }
    # Internally self-consistent by the general restoration-derivation rule
    # (byte_identical correctly matches prestate != poststate) — this specifically
    # discriminates the BLOCKER E observation-binding guard, not the pre-existing
    # generic derivation guard: it claims a DIFFERENT poststate than what the
    # pre-effect observation actually recorded.
    bad["restoration"] = {
        "byte_identical": False,
        "prestate_title_sha256": original_sha,
        "poststate_title_sha256": "8" * 64,  # FABRICATED — not what was observed
        "head_unchanged": True,
    }
    with pytest.raises(
        OutcomeLearningContractError,
        match="poststate_title_sha256 to equal pre_effect_observation.observed_title_sha256",
    ):
        validate_outcome(bad, expectation, request)


# --------------------------------------------------------------------------- BLOCKER F: proof/process-quality


def test_repair_f_proof_refuses_a_tampered_evaluation(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    preflight = _run_preflight(outside_dir, transport, request)
    rc = _run_canary(outside_dir, preflight, transport, runner=_canary_runner_for(outside_dir))
    assert rc == 0
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
    cli.main(
        [
            "evaluate",
            "--expectation", str(outside_dir / "expectation.json"),
            "--outcome", str(outside_dir / "outcome.json"),
            "--request", str(outside_dir / "request.json"),
            "--recorded-at", "2026-09-02T12:05:00Z",
            "--out", str(outside_dir / "evaluation.json"),
        ]
    )
    cli.main(
        [
            "self-model",
            "--evaluation", str(outside_dir / "evaluation.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--recorded-at", "2026-09-02T12:06:00Z",
            "--out", str(outside_dir / "self_model.json"),
        ]
    )
    cli.main(
        [
            "project",
            "--evaluation", str(outside_dir / "evaluation.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--outcome", str(outside_dir / "outcome.json"),
            "--recorded-at", "2026-09-02T12:07:00Z",
            "--out", str(outside_dir / "projection.json"),
        ]
    )

    tampered = json.loads((outside_dir / "evaluation.json").read_text())
    tampered["causal_grade"] = "SOMETHING_ELSE"
    (outside_dir / "evaluation.json").write_text(json.dumps(tampered))

    with pytest.raises(cli.OutcomeLearningContractError):
        cli.cmd_proof(
            cli._parser().parse_args(
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
        )


def test_repair_f_process_quality_false_when_effect_edge_incomplete():
    import tests.test_outcome_learning_v1 as contracts_tests
    from control_plane.outcome_learning_evaluator import evaluate_episode

    expectation, request, outcome = contracts_tests.make_episode()
    incomplete = dict(outcome)
    incomplete["effect_edge"] = {**outcome["effect_edge"], "selector_repeated_single_pr": False}
    evaluation = evaluate_episode(expectation, incomplete, request, recorded_at=contracts_tests.RECORDED_AT)
    assert evaluation["process_quality"]["sealed_before_effect"] is False
    assert evaluation["process_quality"]["effect_owner_revalidated"] is False


# --------------------------------------------------------------------------- kill test #11 / single-shot


def test_kill_11_single_shot_journal_refuses_second_canary_invocation(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    preflight = _run_preflight(outside_dir, transport, request)

    rc = _run_canary(outside_dir, preflight, transport, runner=_canary_runner_for(outside_dir))
    assert rc == 0
    assert transport.patches == 2
    assert _journal_path(outside_dir, request).exists()

    with pytest.raises(cli.OutcomeLearningCliError, match="single-shot"):
        _run_canary(outside_dir, preflight, transport, runner=_canary_runner_for(outside_dir))
    assert transport.patches == 2


# --------------------------------------------------------------------------- ambiguity


def test_ambiguous_readback_mismatch_without_exception_reports_effect_unknown(tmp_path):
    """Both PATCHes complete without raising, but the head_sha in the APPLY's own
    response has moved (a concurrent branch push mid-episode, after every pre-effect
    check already passed) — an ambiguous result detected by comparison, never by
    exception, and MUST still yield exactly 2 completed calls (no retry)."""
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)

    class DriftMidSequenceTransport(FakeTransport):
        def patch(self, endpoint, payload):
            self.patches += 1
            self.title = payload["title"]
            reported_head = "c" * 40 if self.patches == 1 else self.head_sha
            return 200, {
                "number": self.pr_number,
                "title": self.title,
                "head": {"sha": reported_head},
                "base": {"ref": "master"},
            }

    transport = DriftMidSequenceTransport()
    preflight = _run_preflight(outside_dir, transport, request)

    rc = _run_canary(outside_dir, preflight, transport, runner=_canary_runner_for(outside_dir))
    assert rc == 3
    assert transport.patches == 2
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    assert journal["state"] == "EFFECT_UNKNOWN"
    assert len(journal["effect_calls"]) == 2
    assert journal["reconciliation"] is None


def test_apply_succeeds_restore_raises_journals_call1_and_observed_poststate(tmp_path):
    """BLOCKER 1: the apply completed (readback known); the restore PATCH raises.
    The journal must carry call1, and the reconciliation GET's OBSERVED title
    becomes the outcome's poststate."""
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport(raise_on_restore=True)
    preflight = _run_preflight(outside_dir, transport, request)

    rc = _run_canary(outside_dir, preflight, transport, runner=_canary_runner_for(outside_dir))
    assert rc == 3
    journal = json.loads(_journal_path(outside_dir, request).read_text())
    assert journal["state"] == "EFFECT_UNKNOWN"
    assert len(journal["effect_calls"]) == 1
    assert journal["effect_calls"][0]["kind"] == "TITLE_APPLY"
    assert journal["reconciliation"]["observed_title_sha256"] is not None
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
    assert restoration["poststate_title_sha256"] == mutated_title_sha
    assert restoration["byte_identical"] is False


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
            "--expectation-repo-path", EXPECTATION_REPO_PATH,
            "--request-repo-path", REQUEST_REPO_PATH,
            "--observed-at", "2026-09-02T12:02:00Z",
            "--out", str(inside_repo_path),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="outside the repository worktree"):
        cli.cmd_preflight(args, runner=FakeRunner(), transport=FakeTransport())


def test_canary_episode_dir_refuses_a_path_inside_the_repository_worktree(tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "request.json").write_text(json.dumps({"placeholder": True}))
    inside_repo_dir = cli._ROOT / "research" / "outcome_learning"

    args = cli._parser().parse_args(
        [
            "canary",
            "--preflight", str(outside_dir / "preflight.json"),
            "--request", str(outside_dir / "request.json"),
            "--mastermind-root", "/x",
            "--recorded-at", "2026-09-02T12:03:00Z",
            "--episode-dir", str(inside_repo_dir),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="outside the repository worktree"):
        cli.cmd_canary(args, transport=FakeTransport())


# --------------------------------------------------------------------------- committed-seal (prior REQUEST_REPAIR)


def test_repair_local_only_artifact_not_in_sealed_commit_refuses(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    preflight_runner = FakeRunner(
        committed_blobs={
            EXPECTATION_REPO_PATH: (outside_dir / "expectation.json").read_text(encoding="utf-8"),
        },
        sealed_commit_parent=request["expected_parent_head"],
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="does not contain the exact artifact path"):
        _run_preflight(outside_dir, transport, request, runner=preflight_runner)


def test_repair_forged_pairing_digest_mismatch_refuses(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    forged_expectation = json.dumps({**expectation, "decision_kind": "a_forged_pairing"})
    preflight_runner = FakeRunner(
        committed_blobs={
            EXPECTATION_REPO_PATH: forged_expectation,
            REQUEST_REPO_PATH: (outside_dir / "request.json").read_text(encoding="utf-8"),
        },
        sealed_commit_parent=request["expected_parent_head"],
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="committed-vs-supplied digest mismatch"):
        _run_preflight(outside_dir, transport, request, runner=preflight_runner)


def test_repair_path_escape_refused_before_any_git_call(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    tracking_runner = FakeRunner(
        committed_blobs={
            EXPECTATION_REPO_PATH: (outside_dir / "expectation.json").read_text(encoding="utf-8"),
            REQUEST_REPO_PATH: (outside_dir / "request.json").read_text(encoding="utf-8"),
        },
        sealed_commit_parent=request["expected_parent_head"],
    )
    args = cli._parser().parse_args(
        [
            "preflight",
            "--repo", request["repository"],
            "--branch", request["branch"],
            "--sealed-commit", transport.head_sha,
            "--expectation", str(outside_dir / "expectation.json"),
            "--request", str(outside_dir / "request.json"),
            "--expectation-repo-path", "../../../etc/passwd",
            "--request-repo-path", REQUEST_REPO_PATH,
            "--mastermind-root", "/x",
            "--observed-at", "2026-09-02T12:02:00Z",
            "--out", str(outside_dir / "preflight.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="must not contain '..' path segments"):
        cli.cmd_preflight(args, runner=tracking_runner, transport=transport)
    assert tracking_runner.calls == []


def test_repair_canary_refuses_zero_patches_on_missing_seal_provenance(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    transport = FakeTransport()
    preflight = _run_preflight(outside_dir, transport, request)
    del preflight["seal_provenance"]
    (outside_dir / "preflight.json").write_text(json.dumps(preflight))

    fresh_transport = FakeTransport()
    with pytest.raises(cli.OutcomeLearningContractError, match="seal_provenance"):
        _run_canary(outside_dir, preflight, fresh_transport, runner=_canary_runner_for(outside_dir))
    assert fresh_transport.patches == 0
    assert fresh_transport.gets == 0


# --------------------------------------------------------------------------- MINORS: truth-pin


def test_hold_classification_owner_is_a_real_allowed_owner():
    assert cli._HOLD_CLASSIFICATION_SOURCE_OWNER in ALLOWED_SOURCE_OWNERS
    assert cli._HOLD_CLASSIFICATION_SOURCE_OWNER in CLASSIFICATION_SOURCE_OWNERS
    assert cli._HOLD_CLASSIFICATION_SOURCE_OWNER != "STEWARD"
