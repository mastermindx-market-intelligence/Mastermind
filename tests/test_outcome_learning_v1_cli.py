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

CARRIER_REPOSITORY = "mastermindx-market-intelligence/Mastermind"
CARRIER_BRANCH = "sol/outcome-learning-v1-complete-vertical-20260902"
CARRIER_PR_NUMBER = 398


DIRECTIVE_INTENT_ID = "CEO-OLV1-DIRECTIVE-1"
SELECTION_INTENT_ID = "CEO-OLV1-SELECTION-1"


class StepClock:
    def __init__(self, start="2026-09-17T12:00:00+00:00"):
        from datetime import datetime, timedelta

        self._value = datetime.fromisoformat(start)
        self._step = timedelta(seconds=1)

    def now(self):
        value = self._value
        self._value += self._step
        return value


def _accepted_intent_documents(
    *,
    intent_id: str,
    job_id: str,
    objective: dict,
    mastermind_sha: str,
    macro_sha: str,
    created_at_ms: int,
) -> dict[str, dict]:
    canonical_objective = json.dumps(
        objective, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    receipt = {
        "schema": "mastermind.ceo_intent_receipt.v1",
        "intent_id": intent_id,
        "fingerprint": "f" * 64,
        "job_id": job_id,
        "status": "QUEUED",
        "accepted": True,
        "duplicate": False,
        "dispatched": False,
        "authority": {
            "requested": ["READ"],
            "policy_sha256": "a" * 64,
            "authority_level": "A0",
        },
        "grounding": {
            "mastermind_sha": mastermind_sha,
            "macro_sha": macro_sha,
        },
        "created_at_ms": created_at_ms,
    }
    job = {
        "job_id": job_id,
        "objective": canonical_objective,
        "status": "QUEUED",
        "attempt_count": 0,
        "current_attempt_id": None,
        "requested_authorities": ["READ"],
        "authority_policy_hash": "a" * 64,
        "authority_level": "A0",
        "branch": None,
        "worktree": None,
        "allowed_write_paths": [],
        "validation_commands": [],
        "checkpoint": None,
        "result": None,
    }
    return {intent_id: receipt, job_id: job}


def _directive_objective_fixture(operation_key: str = "olv1-cli-test-op") -> dict:
    return {
        "schema": "mastermind.olv1_directive.v1",
        "workstream": "WS:AGENT-EVAL-FABRIC",
        "operation_key": operation_key,
        "carrier_ref": (
            "github:Mastermind:branch:"
            "sol/outcome-learning-v1-complete-vertical-20260902"
        ),
        "expires_at": "2026-10-01T00:00:00Z",
        "authority_ceiling": "COMPOSE_ONLY_NO_EFFECT_NO_PROMOTION",
    }


def _install_intent_documents(runner, documents: dict[str, dict]) -> None:
    target = getattr(runner, "documents", None)
    if target is None:
        target = runner.intent_documents
    target.update(documents)


@pytest.fixture(autouse=True)
def _isolated_host_journal_root(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli, "_CANONICAL_JOURNAL_ROOT", tmp_path / "host-state" / "journals"
    )


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
        carrier_canonical_sha=None,
        carrier_pr_head_sha=None,
        carrier_pr_branch=CARRIER_BRANCH,
        carrier_pr_state="open",
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
        sealed_commit_parents: tuple[str, ...] | None = None,
        sealed_commit_changed_paths: list[str] | None = None,
        intent_documents: dict[str, dict] | None = None,
        ancestor_pairs: set[tuple[str, str]] | None = None,
    ):
        self.mastermind_canonical_sha = mastermind_canonical_sha
        self.carrier_canonical_sha = (
            carrier_canonical_sha
            if carrier_canonical_sha is not None
            else mastermind_canonical_sha
        )
        self.carrier_pr_head_sha = (
            carrier_pr_head_sha
            if carrier_pr_head_sha is not None
            else self.carrier_canonical_sha
        )
        self.carrier_pr_branch = carrier_pr_branch
        self.carrier_pr_state = carrier_pr_state
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
        self.sealed_commit_parents = (
            tuple(sealed_commit_parents)
            if sealed_commit_parents is not None
            else ((sealed_commit_parent,) if sealed_commit_parent is not None else ())
        )
        self.sealed_commit_changed_paths = list(
            sealed_commit_changed_paths
            if sealed_commit_changed_paths is not None
            else [EXPECTATION_REPO_PATH, REQUEST_REPO_PATH]
        )
        self.ancestor_pairs = set(ancestor_pairs or set())
        default_intents = _accepted_intent_documents(
            intent_id=DIRECTIVE_INTENT_ID,
            job_id="JOB-DIRECTIVE-1",
            objective=_directive_objective_fixture(),
            mastermind_sha=self.mastermind_canonical_sha,
            macro_sha=self.macro_canonical_sha,
            created_at_ms= 1789560000000,
        )
        self.intent_documents = dict(
            default_intents if intent_documents is None else intent_documents
        )
        self.calls: list[tuple] = []

    def _blob_id_for(self, path: str) -> str:
        return _sha1(path)

    def run(self, args, *, cwd=None, input=None):
        self.calls.append((tuple(args), cwd, input))

        if args[:2] == ["git", "ls-remote"]:
            url, ref = args[2], args[3]
            if url == cli._CANONICAL_MASTERMIND_URL and ref == "refs/heads/master":
                return cli.RunResult(0, f"{self.mastermind_canonical_sha}\trefs/heads/master\n", "")
            if (
                url == cli._CANONICAL_MASTERMIND_URL
                and ref == f"refs/heads/{CARRIER_BRANCH}"
            ):
                return cli.RunResult(
                    0,
                    f"{self.carrier_canonical_sha}\trefs/heads/{CARRIER_BRANCH}\n",
                    "",
                )
            if url == cli._CANONICAL_MACRO_URL and ref == "refs/heads/main":
                return cli.RunResult(0, f"{self.macro_canonical_sha}\trefs/heads/main\n", "")
            return cli.RunResult(1, "", f"fatal: could not resolve {ref} on {url}")

        if (
            args[:2] == ["gh", "api"]
            and args[2] == f"repos/{CARRIER_REPOSITORY}/pulls/{CARRIER_PR_NUMBER}"
        ):
            payload = {
                "number": CARRIER_PR_NUMBER,
                "state": self.carrier_pr_state,
                "merged": False,
                "head": {
                    "ref": self.carrier_pr_branch,
                    "sha": self.carrier_pr_head_sha,
                    "repo": {"full_name": CARRIER_REPOSITORY},
                },
                "base": {
                    "ref": "master",
                    "repo": {"full_name": CARRIER_REPOSITORY},
                },
            }
            return cli.RunResult(0, json.dumps(payload), "")

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

        if len(args) >= 2 and args[0] == "python3" and args[1] == "scripts/ceo_intent.py":
            target = args[-1]
            value = self.intent_documents.get(target)
            if value is None:
                return cli.RunResult(1, "", f"intent/job {target} unavailable")
            return cli.RunResult(0, json.dumps(value), "")

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

        if args[:4] == ["git", "rev-list", "--parents", "-n"]:
            sealed_commit = args[-1]
            fields = [sealed_commit, *self.sealed_commit_parents]
            return cli.RunResult(0, " ".join(fields) + "\n", "")

        if args[:3] == ["git", "diff", "--name-only"]:
            return cli.RunResult(
                0,
                "".join(f"{path}\n" for path in self.sealed_commit_changed_paths),
                "",
            )

        if args[:2] == ["git", "rev-parse"] and len(args) == 3 and ":" in args[2]:
            _sealed, _, repo_path = args[2].partition(":")
            if repo_path in self.committed_blobs:
                return cli.RunResult(0, self._blob_id_for(repo_path) + "\n", "")
            return cli.RunResult(1, "", f"fatal: path '{repo_path}' does not exist in the given commit")

        if args[:3] == ["git", "merge-base", "--is-ancestor"]:
            ancestor, descendant = args[3], args[4]
            return cli.RunResult(
                0 if (ancestor, descendant) in self.ancestor_pairs else 1,
                "",
                "",
            )

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
        events=None,
        event_actor="olv1-test-operator",
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
        self.events = list(events or [])
        self.event_actor = event_actor
        self._next_event_id = 1000

    def get(self, endpoint):
        self.gets += 1
        if endpoint.endswith("&state=open"):
            if self._selector_prs is not None:
                return 200, self._selector_prs
            return 200, [{"number": self.pr_number}]
        if "/events?per_page=100&page=" in endpoint:
            page = int(endpoint.rsplit("page=", 1)[1])
            start = (page - 1) * 100
            return 200, list(self.events[start:start + 100])
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
        previous_title = self.title
        self.title = payload["title"]
        self._next_event_id += 1
        self.events.append(
            {
                "id": self._next_event_id,
                "event": "renamed",
                "actor": {"login": self.event_actor},
                "created_at": f"2026-09-17T12:30:0{4 + self.patches}Z",
                "rename": {"from": previous_title, "to": self.title},
            }
        )
        return 200, {
            "number": self.pr_number,
            "title": self.title,
            "head": {"sha": self.head_sha},
            "base": {"ref": "master"},
        }


def _journal_path(episode_dir: Path, request: dict) -> Path:
    preflight = json.loads((episode_dir / "preflight.json").read_text())
    path = cli._canonical_journal_path(request, preflight)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


EXPECTATION_REPO_PATH = "research/outcome_learning/OLV1_EXPECTATION_TEST.json"
REQUEST_REPO_PATH = "research/outcome_learning/OLV1_CANARY_REQUEST_TEST.json"


def _compose_and_seal(
    tmp_path: Path, runner: FakeRunner | None = None
) -> tuple[Path, dict, dict]:
    """Compose from a trusted directive, then seal an exact packet-bound choice."""
    runner = runner or FakeRunner()
    episode_dir = tmp_path / "episode"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    compose_args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(episode_dir),
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
            "--operation-key", "olv1-cli-test-op",
        ]
    )
    rc, out = _capture_stdout(
        lambda: cli.cmd_compose(
            compose_args,
            runner=runner,
            clock=StepClock("2026-09-17T12:00:00+00:00"),
        )
    )
    assert rc == 7, f"compose must preserve the incomparable frontier, got: {out}"
    assert "DECISION_REQUIRED" in out
    composition = json.loads((episode_dir / "composition.json").read_text())
    bundle = json.loads((episode_dir / "bundle.json").read_text())
    packet = composition["packet"]
    assert packet["selection_state"] == "MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS"
    assert packet["recommended_option_id"] is None

    selection_objective = {
        "schema": "mastermind.olv1_selection.v1",
        "workstream": "WS:AGENT-EVAL-FABRIC",
        "operation_key": "olv1-cli-test-op",
        "packet_digest": f"sha256:{packet['packet_digest']}",
        "chosen_option_id": cli._OPT_CANARY,
        "carrier_ref": bundle["options"][0]["carrier_ref"],
        "authority_ceiling": "SEAL_ONLY_NO_EFFECT_NO_PROMOTION",
    }
    _install_intent_documents(
        runner,
        _accepted_intent_documents(
            intent_id=SELECTION_INTENT_ID,
            job_id="JOB-SELECTION-1",
            objective=selection_objective,
            mastermind_sha=runner.mastermind_canonical_sha,
            macro_sha=runner.macro_canonical_sha,
            created_at_ms=1789646700000,
        ),
    )
    seal_args = cli._parser().parse_args(
        [
            "seal",
            "--composition", str(episode_dir / "composition.json"),
            "--episode-dir", str(episode_dir),
            "--mastermind-root", "/x",
            "--selection-intent-id", SELECTION_INTENT_ID,
            "--out-expectation", str(outside_dir / "expectation.json"),
            "--out-request", str(outside_dir / "request.json"),
        ]
    )
    rc = cli.cmd_seal(
        seal_args,
        runner=runner,
        clock=StepClock("2026-09-17T12:10:00+00:00"),
    )
    assert rc == 0
    expectation = json.loads((outside_dir / "expectation.json").read_text())
    request = json.loads((outside_dir / "request.json").read_text())
    return outside_dir, expectation, request

def _install_selection_for_episode(runner, episode_dir: Path) -> None:
    composition = json.loads((episode_dir / "composition.json").read_text())
    bundle = json.loads((episode_dir / "bundle.json").read_text())
    packet = composition["packet"]
    objective = {
        "schema": "mastermind.olv1_selection.v1",
        "workstream": "WS:AGENT-EVAL-FABRIC",
        "operation_key": "olv1-cli-test-op",
        "packet_digest": f"sha256:{packet['packet_digest']}",
        "chosen_option_id": cli._OPT_CANARY,
        "carrier_ref": bundle["options"][0]["carrier_ref"],
        "authority_ceiling": "SEAL_ONLY_NO_EFFECT_NO_PROMOTION",
    }
    _install_intent_documents(
        runner,
        _accepted_intent_documents(
            intent_id=SELECTION_INTENT_ID,
            job_id="JOB-SELECTION-1",
            objective=objective,
            mastermind_sha=runner.mastermind_canonical_sha,
            macro_sha=runner.macro_canonical_sha,
            created_at_ms=1789646700000,
        ),
    )


def _preflight_runner_for(outside_dir: Path, *, sealed_commit_parent: str) -> FakeRunner:
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
    args = cli._parser().parse_args(
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
            "--out", str(outside_dir / "preflight.json"),
        ]
    )
    rc = cli.cmd_preflight(
        args,
        runner=runner,
        transport=transport,
        clock=StepClock("2026-09-17T12:20:00+00:00"),
    )
    assert rc == 0
    return json.loads((outside_dir / "preflight.json").read_text())


def _run_canary(
    outside_dir: Path,
    preflight: dict,
    transport: FakeTransport,
    *,
    runner: FakeRunner | None = None,
):
    runner = runner or FakeRunner()
    args = cli._parser().parse_args(
        [
            "canary",
            "--preflight", str(outside_dir / "preflight.json"),
            "--request", str(outside_dir / "request.json"),
            "--mastermind-root", "/x",
        ]
    )
    return cli.cmd_canary(
        args,
        runner=runner,
        transport=transport,
        clock=StepClock("2026-09-17T12:30:00+00:00"),
    )


def _canary_runner_for(outside_dir: Path, request: dict | None = None) -> FakeRunner:
    request = request or json.loads((outside_dir / "request.json").read_text())
    return FakeRunner(
        committed_blobs={
            EXPECTATION_REPO_PATH: (outside_dir / "expectation.json").read_text(encoding="utf-8"),
            REQUEST_REPO_PATH: (outside_dir / "request.json").read_text(encoding="utf-8"),
        },
        sealed_commit_parent=request["expected_parent_head"],
    )

def _run_outcome(
    outside_dir: Path,
    request: dict,
    transport: FakeTransport,
    *,
    runner: FakeRunner | None = None,
    clock: StepClock | None = None,
) -> int:
    runner = runner or _canary_runner_for(outside_dir, request)
    args = cli._parser().parse_args(
        [
            "outcome",
            "--preflight", str(outside_dir / "preflight.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--request", str(outside_dir / "request.json"),
            "--mastermind-root", "/x",
            "--out", str(outside_dir / "outcome.json"),
        ]
    )
    return cli.cmd_outcome(
        args,
        runner=runner,
        transport=transport,
        clock=clock or StepClock("2026-09-17T12:40:00+00:00"),
    )


# --------------------------------------------------------------------------- happy path


def test_end_to_end_seal_through_proof_cross_digests_verify(tmp_path):
    runner = FakeRunner()
    outside_dir, expectation, request = _compose_and_seal(tmp_path, runner)
    assert (
        expectation["assignment"]["method"]
        == "trusted_ceo_intent_selection_from_a1_incomparable_frontier"
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
    assert journal["owner_event_baseline"]["rename_event_ids"] == []
    assert len(journal["effect_calls"]) == 2
    assert journal["reconciliation"] is None
    assert transport.title == "Some PR title"  # restored byte-identically

    rc = _run_outcome(outside_dir, request, transport)
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
            "--out", str(outside_dir / "evaluation.json"),
            "--out-revision", str(outside_dir / "evaluation_revision_1.json"),
        ]
    )
    assert rc == 0
    evaluation = json.loads((outside_dir / "evaluation.json").read_text())
    assert evaluation["outcome_digest"] == canonical_digest(outcome)
    assert evaluation["causal_grade"] == "DESCRIPTIVE_ONLY"
    assert all(evaluation["process_quality"].values())
    initial_revision = json.loads(
        (outside_dir / "evaluation_revision_1.json").read_text()
    )
    assert initial_revision["revision"] == 1
    assert initial_revision["supersedes"] is None
    assert initial_revision["prior_payload_digest"] is None
    assert initial_revision["payload"] == evaluation

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
            "--out", str(outside_dir / "projection.json"),
        ]
    )
    assert rc == 0
    projection = json.loads((outside_dir / "projection.json").read_text())
    assert projection["evaluation_digest"] == canonical_digest(evaluation)
    assert projection["automatic_writes"] is False
    dsc = next(c for c in projection["candidates"] if c["kind"] == "DSC_CANDIDATE")
    assert dsc["key_hint"] == f"OLV1-EPISODE-CONSEQUENCE-{projection['recorded_at'][:10]}"

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
    assert proof_text.startswith("# OL-V1 Local Candidate Proof")
    assert "not a production proof" in proof_text.lower()
    assert "DESCRIPTIVE_ONLY" in proof_text
    assert "What this does NOT prove" in proof_text
    assert "applied, and restored" in proof_text
    assert "MANUAL RESTORATION MAY BE OWED" not in proof_text


# --------------------------------------------------------------------------- carrier/source separation


def test_compose_binds_action_time_carrier_head_separately_from_protected_master(tmp_path):
    protected_sha = SHA40_A
    carrier_sha = "c" * 40
    runner = FakeRunner(
        mastermind_canonical_sha=protected_sha,
        carrier_canonical_sha=carrier_sha,
    )

    outside_dir, _expectation, request = _compose_and_seal(tmp_path, runner)
    episode_dir = Path(str(outside_dir).replace("outside", "episode"))
    bundle = json.loads((episode_dir / "bundle.json").read_text())
    canary = next(
        option for option in bundle["options"] if option["option_id"] == cli._OPT_CANARY
    )

    assert bundle["mastermind_revision_attestation"]["revision"] == protected_sha
    assert canary["expected_head_sha"] == carrier_sha
    assert request["expected_parent_head"] == carrier_sha
    assert request["expected_parent_head"] != protected_sha


def test_compose_refuses_remote_carrier_branch_pr_head_disagreement(tmp_path):
    runner = FakeRunner(
        carrier_canonical_sha="c" * 40,
        carrier_pr_head_sha="d" * 40,
    )
    episode_dir = tmp_path / "episode"
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(episode_dir),
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
            "--operation-key", "olv1-cli-test-op",
        ]
    )

    rc, out = _capture_stdout(
        lambda: cli.cmd_compose(
            args,
            runner=runner,
            clock=StepClock("2026-09-17T12:00:00+00:00"),
        )
    )

    assert rc == 5
    assert "BLOCKER SOURCE_IDENTITY_UNVERIFIED" in out
    assert "carrier" in out.lower()
    assert not (episode_dir / "bundle.json").exists()


def test_runbook_defers_selection_and_seals_directly_on_carrier_tip():
    runbook = (cli._ROOT / "docs/runbooks/outcome-learning-v1.md").read_text(
        encoding="utf-8"
    )
    gate0 = runbook.split("## Gate 0", 1)[1].split("## Step 1", 1)[0]
    step1 = runbook.split("## Step 1", 1)[1].split("## Step 2", 1)[0]
    step3 = runbook.split("## Step 3", 1)[1].split("## Step 4", 1)[0]

    assert "both Executive intents" not in gate0
    assert "selection intent does not exist before compose" in gate0
    assert "accepted selection intent" in step1
    assert "git worktree add --detach" not in step3
    assert "CARRIER_HEAD" in step3
    assert 'rev-parse "$SEALED_COMMIT^"' in step3
    assert '"$CARRIER_HEAD"' in step3


def test_canary_preregistration_holds_carrier_without_forbidding_later_release():
    options = cli._olv1_options(
        "olv1-cli-test-op",
        "c" * 40,
        chairman_source_ref="CEO_INTENT:CEO-OLV1-DIRECTIVE-1:sha256:" + "f" * 64,
    )
    canary = next(item for item in options if item["option_id"] == cli._OPT_CANARY)
    rollback = canary["rollback_plan"]

    assert "never merged" not in rollback
    assert "remains hold throughout the canary" in rollback.lower()
    assert "canary success alone" in rollback.lower()
    assert "ready" in rollback.lower()
    assert "merge" in rollback.lower()


def test_runbook_fail_closes_artifact_paths_and_push_readback():
    runbook = (cli._ROOT / "docs/runbooks/outcome-learning-v1.md").read_text(
        encoding="utf-8"
    )
    step3 = runbook.split("## Step 3", 1)[1].split("## Step 4", 1)[0]
    step6 = runbook.split("## Step 6", 1)[1].split("## Step 7", 1)[0]
    step8 = runbook.split("## Step 8", 1)[1].split("## Step 9", 1)[0]

    assert 'mkdir -p "$MM_ROOT/research/outcome_learning"' in step3
    assert "assert_exact_staged_paths()" in runbook
    assert "push_once_and_reconcile()" in runbook
    assert "set +e" in runbook
    assert "PUSH_RC=$?" in runbook
    assert runbook.count(
        'git -C "$MM_ROOT" push origin "HEAD:refs/heads/$BRANCH"'
    ) == 1

    for section, expected_commit in (
        (step3, "SEALED_COMMIT"),
        (step6, "EVIDENCE_COMMIT"),
        (step8, "MATURATION_COMMIT"),
    ):
        assert "assert_exact_staged_paths" in section
        assert f'push_once_and_reconcile "${expected_commit}"' in section
        assert "git diff --cached --name-only" not in section

    for required in (
        "EXPECTATION_REPO_PATH",
        "REQUEST_REPO_PATH",
        "PREFLIGHT_REPO_PATH",
        "OUTCOME_REPO_PATH",
    ):
        assert f'--artifact "${required}"' in step6

    assert "one-shot mechanism proof" in runbook
    assert "separately preregistered successor" in runbook


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
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
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
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
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
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
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
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
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
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
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
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
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
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
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
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
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
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
            "--operation-key", "olv1-cli-test-op",
        ]
    )
    rc, out = _capture_stdout(
        lambda: cli.cmd_compose(
            args,
            runner=runner,
            clock=StepClock("2026-09-17T12:00:00+00:00"),
        )
    )
    assert rc == 7
    assert "as_of_mode=host_clock_after_acquisition" in out
    assert "DECISION_REQUIRED" in out
def test_compose_stale_explicit_as_of_refused_up_front(tmp_path):
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "compose",
                "--mastermind-root", "/x",
                "--macro-root", "/y",
                "--episode-dir", str(tmp_path / "episode"),
                "--directive-intent-id", DIRECTIVE_INTENT_ID,
                "--operation-key", "olv1-cli-test-op",
                "--as-of", "2020-01-01T00:00:00Z",
            ]
        )
def test_repair_b_operation_key_mismatch_refuses(tmp_path):
    runner = FakeRunner()
    episode_dir = tmp_path / "episode"
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(episode_dir),
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
            "--operation-key", "olv1-cli-test-op",
        ]
    )
    assert (
        cli.cmd_compose(
            args,
            runner=runner,
            clock=StepClock("2026-09-17T12:00:00+00:00"),
        )
        == 7
    )
    _install_selection_for_episode(runner, episode_dir)

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    seal_args = cli._parser().parse_args(
        [
            "seal",
            "--composition", str(episode_dir / "composition.json"),
            "--episode-dir", str(episode_dir),
            "--mastermind-root", "/x",
            "--selection-intent-id", SELECTION_INTENT_ID,
            "--operation-key", "a-completely-different-op",
            "--out-expectation", str(outside_dir / "expectation.json"),
            "--out-request", str(outside_dir / "request.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="does not match the adjudicated"):
        cli.cmd_seal(
            seal_args,
            runner=runner,
            clock=StepClock("2026-09-17T12:10:00+00:00"),
        )
@pytest.mark.parametrize(
    ("runner_kwargs", "message"),
    [
        (
            {"sealed_commit_parents": (SHA40_A, "d" * 40)},
            "exactly one parent",
        ),
        (
            {
                "sealed_commit_parents": (SHA40_A,),
                "sealed_commit_changed_paths": [
                    EXPECTATION_REPO_PATH,
                    REQUEST_REPO_PATH,
                    "control_plane/unrelated.py",
                ],
            },
            "exactly the two preregistration paths",
        ),
    ],
)
def test_preflight_refuses_nonminimal_seal_commit_before_transport(
    tmp_path, runner_kwargs, message
):
    outside_dir, _expectation, request = _compose_and_seal(tmp_path, FakeRunner())
    transport = FakeTransport()
    runner = FakeRunner(
        committed_blobs={
            EXPECTATION_REPO_PATH: (outside_dir / "expectation.json").read_text(),
            REQUEST_REPO_PATH: (outside_dir / "request.json").read_text(),
        },
        sealed_commit_parent=request["expected_parent_head"],
        **runner_kwargs,
    )

    with pytest.raises(cli.OutcomeLearningCliError, match=message):
        _run_preflight(outside_dir, transport, request, runner=runner)
    assert transport.gets == 0
    assert transport.patches == 0


def test_repair_b_parent_head_mismatch_refuses(tmp_path):
    runner = FakeRunner()
    episode_dir = tmp_path / "episode"
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(episode_dir),
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
            "--operation-key", "olv1-cli-test-op",
        ]
    )
    assert (
        cli.cmd_compose(
            args,
            runner=runner,
            clock=StepClock("2026-09-17T12:00:00+00:00"),
        )
        == 7
    )
    _install_selection_for_episode(runner, episode_dir)

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    seal_args = cli._parser().parse_args(
        [
            "seal",
            "--composition", str(episode_dir / "composition.json"),
            "--episode-dir", str(episode_dir),
            "--mastermind-root", "/x",
            "--selection-intent-id", SELECTION_INTENT_ID,
            "--parent-head", "c" * 40,
            "--out-expectation", str(outside_dir / "expectation.json"),
            "--out-request", str(outside_dir / "request.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="does not match the adjudicated"):
        cli.cmd_seal(
            seal_args,
            runner=runner,
            clock=StepClock("2026-09-17T12:10:00+00:00"),
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
            "--out", str(outside_dir / "preflight.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="does not match the sealed request's repository"):
        cli.cmd_preflight(args, runner=preflight_runner, transport=transport)
    assert transport.gets == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expectation_blob_sha", "f" * 40),
        ("expectation_content_sha256", "f" * 64),
        ("expectation_repo_path", "research/outcome_learning/OTHER_EXPECTATION.json"),
        ("request_repo_path", "research/outcome_learning/OTHER_REQUEST.json"),
        ("branch", "a-different-carrier-branch"),
    ],
)
def test_canary_reacquires_full_sealed_episode_before_any_transport(
    tmp_path, field, value
):
    outside_dir, _expectation, request = _compose_and_seal(tmp_path, FakeRunner())
    preflight_transport = FakeTransport()
    preflight = _run_preflight(outside_dir, preflight_transport, request)
    preflight[field] = value
    (outside_dir / "preflight.json").write_text(json.dumps(preflight))

    live_transport = FakeTransport()
    with pytest.raises(cli.OutcomeLearningCliError):
        _run_canary(
            outside_dir,
            preflight,
            live_transport,
            runner=_canary_runner_for(outside_dir, request),
        )
    assert live_transport.gets == 0
    assert live_transport.patches == 0


def test_outcome_refuses_terminal_journal_without_github_owner_events(tmp_path):
    outside_dir, _expectation, request = _compose_and_seal(tmp_path, FakeRunner())
    transport = FakeTransport()
    preflight = _run_preflight(outside_dir, transport, request)
    assert (
        _run_canary(
            outside_dir,
            preflight,
            transport,
            runner=_canary_runner_for(outside_dir, request),
        )
        == 0
    )
    assert len(transport.events) == 2
    transport.events.clear()

    with pytest.raises(cli.OutcomeLearningCliError, match="owner|rename|event"):
        _run_outcome(outside_dir, request, transport)
    assert not (outside_dir / "outcome.json").exists()


def test_outcome_embeds_two_exact_github_owner_rename_events(tmp_path):
    outside_dir, _expectation, request = _compose_and_seal(tmp_path, FakeRunner())
    transport = FakeTransport()
    preflight = _run_preflight(outside_dir, transport, request)
    assert (
        _run_canary(
            outside_dir,
            preflight,
            transport,
            runner=_canary_runner_for(outside_dir, request),
        )
        == 0
    )
    assert _run_outcome(outside_dir, request, transport) == 0
    outcome = json.loads((outside_dir / "outcome.json").read_text())
    evidence = outcome["owner_effect_evidence"]
    assert [item["transition"] for item in evidence] == [
        "TITLE_APPLY",
        "TITLE_RESTORE",
    ]
    assert [item["event_id"] for item in evidence] == [1001, 1002]
    assert all(item["actor_login"] == transport.event_actor for item in evidence)
    assert outcome["effect_edge"]["owner_rename_events_verified"] is True
    assert outcome["effect_edge"]["bindings_verified"] is True


def test_outcome_refuses_unknown_terminal_journal_fields(tmp_path):
    outside_dir, _expectation, request = _compose_and_seal(tmp_path, FakeRunner())
    transport = FakeTransport()
    preflight = _run_preflight(outside_dir, transport, request)
    assert (
        _run_canary(
            outside_dir,
            preflight,
            transport,
            runner=_canary_runner_for(outside_dir, request),
        )
        == 0
    )
    journal_path = _journal_path(outside_dir, request)
    journal = json.loads(journal_path.read_text())
    journal["forged_terminal_claim"] = True
    journal_path.write_text(json.dumps(journal))

    with pytest.raises(cli.OutcomeLearningCliError, match="unknown|journal"):
        _run_outcome(outside_dir, request, transport)
    assert not (outside_dir / "outcome.json").exists()


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
    canary_runner = FakeRunner(
        committed_blobs={
            EXPECTATION_REPO_PATH: (outside_dir / "expectation.json").read_text(),
            REQUEST_REPO_PATH: forged_request,
        },
        sealed_commit_parent=request["expected_parent_head"],
    )
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
    endpoint = f"repos/{request['repository']}/pulls/{preflight['pr_number']}"
    applied_title = "Some PR title " + request["canary_token"]
    attempt = cli._make_attempt(
        1, "TITLE_APPLY", endpoint, applied_title, "2026-09-17T12:30:03Z"
    )
    call = cli._make_call(
        1,
        "TITLE_APPLY",
        endpoint,
        attempt["payload_title_sha256"],
        200,
        {"title": applied_title, "head": {"sha": preflight["sealed_commit_sha"]}},
        requested_at=attempt["requested_at"],
        observed_at="2026-09-17T12:30:04Z",
    )
    journal_path.write_text(
        json.dumps(
            cli._journal_record(
                state="APPLIED_READBACK",
                bound_identity=cli._canonical_journal_identity(request, preflight),
                selector_observation={
                    "observed_at": "2026-09-17T12:30:01Z",
                    "match_count": 1,
                    "matched_pr_number": preflight["pr_number"],
                },
                owner_event_baseline={
                    "observed_at": "2026-09-17T12:30:02.500000Z",
                    "rename_event_ids": [],
                },
                effect_attempts=[attempt],
                effect_calls=[call],
                pre_effect_observation={
                    "observed_head_sha": preflight["sealed_commit_sha"],
                    "observed_title_sha256": preflight["original_title_sha256"],
                    "observed_title_length": preflight["original_title_length"],
                    "observed_at": "2026-09-17T12:30:02Z",
                },
                recorded_at="2026-09-17T12:30:04Z",
            )
        )
    )

    transport = FakeTransport()
    with pytest.raises(cli.OutcomeLearningCliError, match="already exists"):
        _run_canary(outside_dir, preflight, transport, runner=_canary_runner_for(outside_dir))
    assert transport.gets == 0
    assert transport.patches == 0

    with pytest.raises(cli.OutcomeLearningCliError, match="non-terminal state"):
        _run_outcome(outside_dir, request, transport)


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
            cli._journal_record(
                state="PREPARED",
                bound_identity=cli._canonical_journal_identity(request, preflight),
                recorded_at="2026-09-17T12:30:00Z",
            )
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
    identity = {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "branch": "sol/outcome-learning-v1-complete-vertical-20260902",
        "operation_key": "olv1-cli-test-op",
        "expectation_sealed_hash": "sha256:" + "1" * 64,
        "sealed_commit_sha": SHA40_B,
        "expected_parent_head": SHA40_A,
        "preflight_pr_number": 42,
        "canary_token": "[OL-V1-CANARY]",
        "request_digest": "2" * 64,
    }
    record = cli._journal_record(
        state="PREPARED",
        bound_identity=identity,
        recorded_at="2026-09-17T12:30:00Z",
    )
    cli._reserve_journal(path, record)
    with pytest.raises(cli.OutcomeLearningCliError, match="already exists"):
        cli._reserve_journal(path, record)


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

    rc = _run_outcome(outside_dir, request, drifted_transport)
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
    bad["effect_attempts"] = []
    bad["effect_calls"] = []
    bad["owner_event_baseline"] = None
    bad["owner_effect_evidence"] = []
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
    assert _run_outcome(outside_dir, request, transport) == 0
    cli.main(
        [
            "evaluate",
            "--expectation", str(outside_dir / "expectation.json"),
            "--outcome", str(outside_dir / "outcome.json"),
            "--request", str(outside_dir / "request.json"),
            "--out", str(outside_dir / "evaluation.json"),
        ]
    )
    cli.main(
        [
            "self-model",
            "--evaluation", str(outside_dir / "evaluation.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--out", str(outside_dir / "self_model.json"),
        ]
    )
    cli.main(
        [
            "project",
            "--evaluation", str(outside_dir / "evaluation.json"),
            "--expectation", str(outside_dir / "expectation.json"),
            "--outcome", str(outside_dir / "outcome.json"),
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
    incomplete["effect_edge"] = {
        **outcome["effect_edge"],
        "selector_repeated_single_pr": False,
        "bindings_verified": False,
    }
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
    assert journal["reconciliation"] is not None
    assert journal["reconciliation"]["attempted"] is True


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

    rc = _run_outcome(outside_dir, request, transport)
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
            "--out", str(inside_repo_path),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="outside the repository worktree"):
        cli.cmd_preflight(args, runner=FakeRunner(), transport=FakeTransport())


def test_canary_episode_dir_refuses_a_path_inside_the_repository_worktree(tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    inside_repo_dir = cli._ROOT / "research" / "outcome_learning"
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", str(outside_dir / "preflight.json"),
                "--request", str(outside_dir / "request.json"),
                "--mastermind-root", "/x",
                "--episode-dir", str(inside_repo_dir),
            ]
        )
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
    source_ref = "CEO_INTENT:CEO-OLV1-DIRECTIVE-1:sha256:" + "f" * 64
    options = cli._olv1_options(
        "olv1-cli-test-op", SHA40_A, chairman_source_ref=source_ref
    )
    assert all(option["classification_source_ref"] == source_ref for option in options)
    assert all(source_ref in option["source_refs"] for option in options)
    assert not hasattr(cli, "_HOLD_CLASSIFICATION_SOURCE_OWNER")
def _intent_documents(*, intent_id, job_id, objective, mastermind_sha=SHA40_A, macro_sha=SHA40_B, created_at_ms=1789646340000):
    canonical_objective = json.dumps(
        objective, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    receipt = {
        "schema": "mastermind.ceo_intent_receipt.v1",
        "intent_id": intent_id,
        "fingerprint": "f" * 64,
        "job_id": job_id,
        "status": "QUEUED",
        "accepted": True,
        "duplicate": False,
        "dispatched": False,
        "authority": {
            "requested": ["READ"],
            "policy_sha256": "a" * 64,
            "authority_level": "A0",
        },
        "grounding": {
            "mastermind_sha": mastermind_sha,
            "macro_sha": macro_sha,
        },
        "created_at_ms": created_at_ms,
    }
    job = {
        "job_id": job_id,
        "objective": canonical_objective,
        "status": "QUEUED",
        "attempt_count": 0,
        "current_attempt_id": None,
        "requested_authorities": ["READ"],
        "authority_policy_hash": "a" * 64,
        "authority_level": "A0",
        "branch": None,
        "worktree": None,
        "allowed_write_paths": [],
        "validation_commands": [],
        "checkpoint": None,
        "result": None,
    }
    return {intent_id: receipt, job_id: job}


class IntentRunner(FakeRunner):
    def __init__(self, *, documents=None, **kwargs):
        super().__init__(**kwargs)
        self.documents = dict(documents or {})

    def run(self, args, *, cwd=None, input=None):
        if len(args) >= 2 and args[0] == "python3" and args[1] == "scripts/ceo_intent.py":
            target = args[-1]
            value = self.documents.get(target)
            if value is None:
                return cli.RunResult(1, "", f"intent/job {target} unavailable")
            return cli.RunResult(0, json.dumps(value), "")
        return super().run(args, cwd=cwd, input=input)


def _directive_objective(operation_key="olv1-cli-test-op"):
    return {
        "schema": "mastermind.olv1_directive.v1",
        "workstream": "WS:AGENT-EVAL-FABRIC",
        "operation_key": operation_key,
        "carrier_ref": (
            "github:Mastermind:branch:"
            "sol/outcome-learning-v1-complete-vertical-20260902"
        ),
        "expires_at": "2026-10-01T00:00:00Z",
        "authority_ceiling": "COMPOSE_ONLY_NO_EFFECT_NO_PROMOTION",
    }


def _compose_with_directive(tmp_path, runner, *, clock=None):
    args = cli._parser().parse_args(
        [
            "compose",
            "--mastermind-root", "/x",
            "--macro-root", "/y",
            "--episode-dir", str(tmp_path / "episode"),
            "--directive-intent-id", DIRECTIVE_INTENT_ID,
            "--operation-key", "olv1-cli-test-op",
            "--directive-intent-id", "CEO-OLV1-DIRECTIVE-1",
        ]
    )
    return _capture_stdout(
        lambda: cli.cmd_compose(args, runner=runner, clock=clock or StepClock())
    )


def test_compose_refuses_when_canonical_directive_cannot_be_acquired(tmp_path):
    rc, out = _compose_with_directive(tmp_path, IntentRunner())
    assert rc == 5
    assert "DIRECTIVE_SOURCE_UNVERIFIED" in out
    assert not (tmp_path / "episode" / "composition.json").exists()


def test_compose_uses_accepted_intent_and_stops_for_exact_packet_selection(tmp_path):
    documents = _intent_documents(
        intent_id="CEO-OLV1-DIRECTIVE-1",
        job_id="JOB-DIRECTIVE-1",
        objective=_directive_objective(),
    )
    rc, out = _compose_with_directive(
        tmp_path,
        IntentRunner(documents=documents),
    )
    assert rc == 7
    assert "DECISION_REQUIRED" in out
    bundle = json.loads((tmp_path / "episode" / "bundle.json").read_text())
    composition = json.loads((tmp_path / "episode" / "composition.json").read_text())
    source_ref = bundle["chairman_directive"]["source_ref"]
    assert source_ref.startswith("CEO_INTENT:CEO-OLV1-DIRECTIVE-1:")
    assert bundle["delegation_envelope"]["expires_at"] == "2026-10-01T00:00:00Z"
    assert composition["packet"]["selection_state"] == "MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS"


def test_seal_requires_and_verifies_a_selection_intent_bound_to_the_exact_packet(tmp_path):
    directive_documents = _intent_documents(
        intent_id="CEO-OLV1-DIRECTIVE-1",
        job_id="JOB-DIRECTIVE-1",
        objective=_directive_objective(),
    )
    runner = IntentRunner(documents=directive_documents)
    rc, _ = _compose_with_directive(tmp_path, runner)
    assert rc == 7

    episode_dir = tmp_path / "episode"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    composition = json.loads((episode_dir / "composition.json").read_text())
    bundle = json.loads((episode_dir / "bundle.json").read_text())
    packet_digest = "sha256:" + composition["packet"]["packet_digest"]
    selection_objective = {
        "schema": "mastermind.olv1_selection.v1",
        "workstream": "WS:AGENT-EVAL-FABRIC",
        "operation_key": "olv1-cli-test-op",
        "packet_digest": packet_digest,
        "chosen_option_id": cli._OPT_CANARY,
        "carrier_ref": bundle["options"][0]["carrier_ref"],
        "authority_ceiling": "SEAL_ONLY_NO_EFFECT_NO_PROMOTION",
    }
    selection_docs = _intent_documents(
        intent_id="CEO-OLV1-SELECTION-1",
        job_id="JOB-SELECTION-1",
        objective=selection_objective,
        created_at_ms=1789646700000,
    )
    runner.documents.update(selection_docs)

    args = cli._parser().parse_args(
        [
            "seal",
            "--composition", str(episode_dir / "composition.json"),
            "--episode-dir", str(episode_dir),
            "--selection-intent-id", "CEO-OLV1-SELECTION-1",
            "--out-expectation", str(outside_dir / "expectation.json"),
            "--out-request", str(outside_dir / "request.json"),
        ]
    )
    assert cli.cmd_seal(args, runner=runner, clock=StepClock("2026-09-17T12:10:00+00:00")) == 0
    expectation = json.loads((outside_dir / "expectation.json").read_text())
    assert expectation["assignment"]["method"] == (
        "trusted_ceo_intent_selection_from_a1_incomparable_frontier"
    )
    assert any(
        ref.startswith("CEO_INTENT:CEO-OLV1-SELECTION-1:")
        for ref in expectation["context"]["source_refs"]
    )

    forged = dict(selection_objective)
    forged["packet_digest"] = "sha256:" + "0" * 64
    runner.documents.update(
        _intent_documents(
            intent_id="CEO-OLV1-SELECTION-FORGED",
            job_id="JOB-SELECTION-FORGED",
            objective=forged,
            created_at_ms=1789646760000,
        )
    )
    forged_args = cli._parser().parse_args(
        [
            "seal",
            "--composition", str(episode_dir / "composition.json"),
            "--episode-dir", str(episode_dir),
            "--selection-intent-id", "CEO-OLV1-SELECTION-FORGED",
            "--out-expectation", str(outside_dir / "forged-expectation.json"),
            "--out-request", str(outside_dir / "forged-request.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="packet_digest"):
        cli.cmd_seal(
            forged_args,
            runner=runner,
            clock=StepClock("2026-09-17T12:20:00+00:00"),
        )


def test_public_cli_has_no_timestamp_or_journal_root_override():
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "canary",
                "--preflight", "/tmp/p.json",
                "--request", "/tmp/r.json",
                "--mastermind-root", "/x",
                "--recorded-at", "2020-01-01T00:00:00Z",
                "--episode-dir", "/tmp/attacker-chosen",
            ]
        )


def test_canonical_journal_path_is_host_rooted_and_identity_bound(tmp_path):
    request = {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "branch": "sol/outcome-learning-v1-complete-vertical-20260902",
        "operation_key": "olv1-cli-test-op",
        "expectation_sealed_hash": "sha256:" + "1" * 64,
        "expected_parent_head": SHA40_A,
        "canary_token": "OLV1-CANARY",
    }
    preflight = {"sealed_commit_sha": SHA40_B, "pr_number": 42}
    root = tmp_path / "canonical-host-root"
    path = cli._canonical_journal_path(request, preflight, journal_root=root)
    assert path.is_relative_to(root)
    assert "olv1-cli-test-op" in path.parts
    assert SHA40_B in path.parts
    assert "/tmp/attacker-chosen" not in str(path)



class PaginatedIssueEventTransport:
    def __init__(self, pages):
        self.pages = pages
        self.endpoints = []

    def get(self, endpoint):
        self.endpoints.append(endpoint)
        page = int(endpoint.rsplit("page=", 1)[1])
        return 200, list(self.pages.get(page, []))

    def patch(self, endpoint, payload):
        raise AssertionError("owner evidence reconciliation is read-only")


def _rename_event(event_id, *, created_at, before, after):
    return {
        "id": event_id,
        "event": "renamed",
        "actor": {"login": "olv1-test-operator"},
        "created_at": created_at,
        "rename": {"from": before, "to": after},
    }


def test_owner_evidence_uses_baseline_and_paginates_past_first_full_page():
    import hashlib

    original = "Some PR title"
    applied = original + " [OL-V1-CANARY]"
    unrelated = [
        {
            "id": index,
            "event": "commented",
            "actor": {"login": "someone"},
            "created_at": "2026-09-17T12:00:00Z",
        }
        for index in range(1, 101)
    ]
    transport = PaginatedIssueEventTransport(
        {
            1: unrelated,
            2: [
                _rename_event(1001, created_at="2026-09-17T12:30:05Z", before=original, after=applied),
                _rename_event(1002, created_at="2026-09-17T12:30:06Z", before=applied, after=original),
            ],
        }
    )
    attempts = [
        {
            "seq": 1,
            "kind": "TITLE_APPLY",
            "requested_at": "2026-09-17T12:30:05.500000Z",
            "method": "PATCH",
            "endpoint": "repos/o/r/pulls/42",
            "payload_title_sha256": hashlib.sha256(applied.encode()).hexdigest(),
            "payload_title_length": len(applied),
        },
        {
            "seq": 2,
            "kind": "TITLE_RESTORE",
            "requested_at": "2026-09-17T12:30:06.500000Z",
            "method": "PATCH",
            "endpoint": "repos/o/r/pulls/42",
            "payload_title_sha256": hashlib.sha256(original.encode()).hexdigest(),
            "payload_title_length": len(original),
        },
    ]
    evidence = cli._owner_rename_evidence(
        transport=transport,
        preflight={
            "repository": "o/r",
            "pr_number": 42,
            "original_title_sha256": hashlib.sha256(original.encode()).hexdigest(),
            "original_title_length": len(original),
        },
        owner_event_baseline={
            "observed_at": "2026-09-17T12:30:04.900000Z",
            "rename_event_ids": [],
        },
        effect_attempts=attempts,
        effect_calls=[{"kind": "TITLE_APPLY"}, {"kind": "TITLE_RESTORE"}],
        observed_at="2026-09-17T12:30:07Z",
    )
    assert [item["event_id"] for item in evidence] == [1001, 1002]
    assert transport.endpoints == [
        "repos/o/r/issues/42/events?per_page=100&page=1",
        "repos/o/r/issues/42/events?per_page=100&page=2",
    ]


def test_owner_evidence_rejects_an_event_already_present_in_baseline():
    import hashlib

    original = "Some PR title"
    applied = original + " [OL-V1-CANARY]"
    event = _rename_event(1001, created_at="2026-09-17T12:30:05Z", before=original, after=applied)
    transport = PaginatedIssueEventTransport({1: [event]})
    with pytest.raises(cli.OutcomeLearningCliError, match="missing for a completed effect call"):
        cli._owner_rename_evidence(
            transport=transport,
            preflight={
                "repository": "o/r",
                "pr_number": 42,
                "original_title_sha256": hashlib.sha256(original.encode()).hexdigest(),
                "original_title_length": len(original),
            },
            owner_event_baseline={
                "observed_at": "2026-09-17T12:30:04Z",
                "rename_event_ids": [1001],
            },
            effect_attempts=[{
                "seq": 1,
                "kind": "TITLE_APPLY",
                "requested_at": "2026-09-17T12:30:05.500000Z",
                "method": "PATCH",
                "endpoint": "repos/o/r/pulls/42",
                "payload_title_sha256": hashlib.sha256(applied.encode()).hexdigest(),
                "payload_title_length": len(applied),
            }],
            effect_calls=[{"kind": "TITLE_APPLY"}],
            observed_at="2026-09-17T12:30:07Z",
        )


def test_issue_event_pagination_refuses_when_bound_is_exhausted():
    pages = {
        page: [
            {"id": (page - 1) * 100 + index + 1, "event": "commented"}
            for index in range(100)
        ]
        for page in range(1, 11)
    }
    transport = PaginatedIssueEventTransport(pages)
    with pytest.raises(cli.OutcomeLearningCliError, match="pagination bound"):
        cli._fetch_issue_events(transport, "o/r", 42)

# --------------------------------------------------------------------------- 2026-09-17 remote maturation shell


class PublicationTransport:
    def __init__(
        self,
        *,
        branch_sha,
        pr_sha=None,
        check_runs=None,
        check_runs_by_sha=None,
        total_count_by_sha=None,
    ):
        self.branch_sha = branch_sha
        self.pr_sha = pr_sha or branch_sha
        self.check_runs = list(check_runs or [])
        self.check_runs_by_sha = {
            key: list(value) for key, value in (check_runs_by_sha or {}).items()
        }
        self.total_count_by_sha = dict(total_count_by_sha or {})
        self.get_endpoints = []
        self.patches = 0

    def get(self, endpoint):
        self.get_endpoints.append(endpoint)
        if "/git/ref/heads/" in endpoint:
            return 200, {"object": {"sha": self.branch_sha}}
        if "/commits/" in endpoint and "/check-runs" in endpoint:
            commit_sha = endpoint.split("/commits/", 1)[1].split("/", 1)[0]
            runs = self.check_runs_by_sha.get(commit_sha, self.check_runs)
            total_count = self.total_count_by_sha.get(commit_sha, len(runs))
            return 200, {"total_count": total_count, "check_runs": runs}
        if "/check-runs/" in endpoint:
            check_id = int(endpoint.rsplit("/", 1)[1])
            for runs in [*self.check_runs_by_sha.values(), self.check_runs]:
                for run in runs:
                    if run.get("id") == check_id:
                        return 200, run
            raise AssertionError(f"unknown check run id {check_id}")
        if "/pulls/" in endpoint:
            return 200, {"head": {"sha": self.pr_sha}}
        raise AssertionError(f"unexpected publication GET {endpoint}")

    def patch(self, endpoint, payload):
        self.patches += 1
        raise AssertionError("publication/maturation must never PATCH GitHub")


def _write_revision_fixture(tmp_path):
    import tests.test_outcome_learning_v1 as contracts_tests
    from control_plane.outcome_learning_contracts import build_initial_artifact_revision
    from control_plane.outcome_learning_evaluator import evaluate_episode

    expectation, request, outcome = contracts_tests.make_episode()
    evaluation = evaluate_episode(
        expectation,
        outcome,
        request,
        recorded_at=contracts_tests.EVALUATION_AT,
    )
    identity = {
        "operation_key": expectation["operation_key"],
        "carrier_ref": (
            "github:Mastermind:branch:"
            "sol/outcome-learning-v1-complete-vertical-20260902"
        ),
        "expectation_sealed_hash": expectation["sealed_hash"],
        "request_digest": canonical_digest(request),
    }
    revision = build_initial_artifact_revision(
        artifact_kind="EVALUATION",
        episode_identity=identity,
        payload=evaluation,
        owner_evidence=[],
        corrected_at="2026-09-02T12:00:09Z",
    )
    docs = {
        "expectation": expectation,
        "request": request,
        "outcome": outcome,
        "evaluation": evaluation,
        "revision_1": revision,
    }
    for name, doc in docs.items():
        (tmp_path / f"{name}.json").write_text(
            json.dumps(doc, indent=2, sort_keys=True) + "\n"
        )
    return docs


def _json_artifact(path: str, doc: dict, *, blob_sha="d" * 40) -> dict:
    text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    return {
        "path": path,
        "blob_sha": blob_sha,
        "content_digest": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _raw_check(*, check_id: int, name: str, head_sha: str, conclusion="success") -> dict:
    return {
        "id": check_id,
        "name": name,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": conclusion,
    }


def test_capture_publication_reads_exact_remote_heads_and_committed_artifacts(tmp_path):
    docs = _write_revision_fixture(tmp_path)
    target = "b" * 40
    repo_paths = {
        "research/outcome_learning/OLV1_EVALUATION.json": json.dumps(
            docs["evaluation"], sort_keys=True
        ),
        "research/outcome_learning/OLV1_EVALUATION_REVISION_1.json": json.dumps(
            docs["revision_1"], sort_keys=True
        ),
    }
    runner = FakeRunner(committed_blobs=repo_paths)
    transport = PublicationTransport(branch_sha=target)
    args = cli._parser().parse_args(
        [
            "capture-publication",
            "--stage", "EVIDENCE_COMMIT",
            "--expectation", str(tmp_path / "expectation.json"),
            "--request", str(tmp_path / "request.json"),
            "--repo", docs["request"]["repository"],
            "--branch", docs["request"]["branch"],
            "--pr-number", "398",
            "--target-commit", target,
            "--frozen-evidence-commit", target,
            "--artifact", "research/outcome_learning/OLV1_EVALUATION.json",
            "--artifact", "research/outcome_learning/OLV1_EVALUATION_REVISION_1.json",
            "--mastermind-root", "/x",
            "--out", str(tmp_path / "evidence_receipt.json"),
        ]
    )
    assert (
        cli.cmd_capture_publication(
            args,
            runner=runner,
            transport=transport,
            clock=StepClock("2026-09-02T12:00:15+00:00"),
        )
        == 0
    )
    receipt = json.loads((tmp_path / "evidence_receipt.json").read_text())
    assert receipt["stage"] == "EVIDENCE_COMMIT"
    assert receipt["target_commit_sha"] == target
    assert receipt["remote_branch_head_sha"] == target
    assert receipt["remote_pr_head_sha"] == target
    assert len(receipt["artifact_digests"]) == 2
    assert receipt["checks"] == []
    assert transport.patches == 0


def test_capture_publication_refuses_remote_branch_or_pr_drift(tmp_path):
    docs = _write_revision_fixture(tmp_path)
    target = "b" * 40
    path = "research/outcome_learning/OLV1_EVALUATION.json"
    runner = FakeRunner(committed_blobs={path: json.dumps(docs["evaluation"])})
    transport = PublicationTransport(branch_sha="c" * 40, pr_sha=target)
    args = cli._parser().parse_args(
        [
            "capture-publication",
            "--stage", "EVIDENCE_COMMIT",
            "--expectation", str(tmp_path / "expectation.json"),
            "--request", str(tmp_path / "request.json"),
            "--repo", docs["request"]["repository"],
            "--branch", docs["request"]["branch"],
            "--pr-number", "398",
            "--target-commit", target,
            "--frozen-evidence-commit", target,
            "--artifact", path,
            "--mastermind-root", "/x",
            "--out", str(tmp_path / "receipt.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="branch head"):
        cli.cmd_capture_publication(
            args,
            runner=runner,
            transport=transport,
            clock=StepClock("2026-09-02T12:00:15+00:00"),
        )
    assert not (tmp_path / "receipt.json").exists()


def test_mature_evaluation_queries_exact_check_and_appends_without_mutation(tmp_path):
    from control_plane.outcome_learning_contracts import (
        build_remote_publication_receipt,
        validate_revision_chain,
    )

    docs = _write_revision_fixture(tmp_path)
    target = "b" * 40
    artifact = {
        "path": "research/outcome_learning/OLV1_EVALUATION.json",
        "blob_sha": "d" * 40,
        "content_digest": canonical_digest({"evaluation": "bytes"}),
    }
    receipt = build_remote_publication_receipt(
        stage="EVIDENCE_COMMIT",
        repository=docs["request"]["repository"],
        branch=docs["request"]["branch"],
        pr_number=398,
        episode_identity=docs["revision_1"]["episode_identity"],
        target_commit_sha=target,
        frozen_evidence_commit_sha=target,
        remote_branch_head_sha=target,
        remote_pr_head_sha=target,
        artifact_digests=[artifact],
        checks=[],
        observed_at="2026-09-02T12:00:15Z",
    )
    (tmp_path / "evidence_receipt.json").write_text(json.dumps(receipt))
    initial_bytes = (tmp_path / "evaluation.json").read_bytes()
    transport = PublicationTransport(
        branch_sha=target,
        check_runs=[
            {
                "id": 4242,
                "name": "hosted-ci",
                "head_sha": target,
                "status": "completed",
                "conclusion": "success",
            }
        ],
    )
    args = cli._parser().parse_args(
        [
            "mature-evaluation",
            "--expectation", str(tmp_path / "expectation.json"),
            "--request", str(tmp_path / "request.json"),
            "--outcome", str(tmp_path / "outcome.json"),
            "--initial-evaluation", str(tmp_path / "evaluation.json"),
            "--initial-revision", str(tmp_path / "revision_1.json"),
            "--evidence-receipt", str(tmp_path / "evidence_receipt.json"),
            "--check-name", "hosted-ci",
            "--out-evaluation", str(tmp_path / "evaluation_matured.json"),
            "--out-revision", str(tmp_path / "revision_2.json"),
        ]
    )
    assert (
        cli.cmd_mature_evaluation(
            args,
            transport=transport,
            clock=StepClock("2026-09-02T12:00:20+00:00"),
        )
        == 0
    )
    assert (tmp_path / "evaluation.json").read_bytes() == initial_bytes
    matured = json.loads((tmp_path / "evaluation_matured.json").read_text())
    second = json.loads((tmp_path / "revision_2.json").read_text())
    validate_revision_chain([docs["revision_1"], second])
    metric = next(
        item
        for item in matured["forecast"]
        if item["metric_id"] == "ci_green_at_frozen_evidence_commit"
    )
    assert metric["realized"] == 1.0
    assert second["payload"] == matured
    assert second["owner_evidence"][0]["check_run_id"] == 4242
    assert transport.patches == 0


def test_mature_evaluation_refuses_wrong_check_sha_or_ambiguous_name(tmp_path):
    from control_plane.outcome_learning_contracts import build_remote_publication_receipt

    docs = _write_revision_fixture(tmp_path)
    target = "b" * 40
    artifact = {
        "path": "research/outcome_learning/OLV1_EVALUATION.json",
        "blob_sha": "d" * 40,
        "content_digest": canonical_digest({"evaluation": "bytes"}),
    }
    receipt = build_remote_publication_receipt(
        stage="EVIDENCE_COMMIT",
        repository=docs["request"]["repository"],
        branch=docs["request"]["branch"],
        pr_number=398,
        episode_identity=docs["revision_1"]["episode_identity"],
        target_commit_sha=target,
        frozen_evidence_commit_sha=target,
        remote_branch_head_sha=target,
        remote_pr_head_sha=target,
        artifact_digests=[artifact],
        checks=[],
        observed_at="2026-09-02T12:00:15Z",
    )
    (tmp_path / "evidence_receipt.json").write_text(json.dumps(receipt))
    transport = PublicationTransport(
        branch_sha=target,
        check_runs=[
            {
                "id": 1,
                "name": "hosted-ci",
                "head_sha": "c" * 40,
                "status": "completed",
                "conclusion": "success",
            }
        ],
    )
    args = cli._parser().parse_args(
        [
            "mature-evaluation",
            "--expectation", str(tmp_path / "expectation.json"),
            "--request", str(tmp_path / "request.json"),
            "--outcome", str(tmp_path / "outcome.json"),
            "--initial-evaluation", str(tmp_path / "evaluation.json"),
            "--initial-revision", str(tmp_path / "revision_1.json"),
            "--evidence-receipt", str(tmp_path / "evidence_receipt.json"),
            "--check-name", "hosted-ci",
            "--out-evaluation", str(tmp_path / "bad_eval.json"),
            "--out-revision", str(tmp_path / "bad_revision.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="exact evidence commit"):
        cli.cmd_mature_evaluation(
            args,
            transport=transport,
            clock=StepClock("2026-09-02T12:00:20+00:00"),
        )


def _production_proof_fixture(tmp_path):
    import tests.test_outcome_learning_v1 as contracts_tests
    from control_plane.outcome_learning_contracts import (
        build_correction_revision,
        build_github_check_evidence,
        build_remote_publication_receipt,
    )
    from control_plane.outcome_learning_evaluator import (
        build_agentos_projection,
        build_self_model,
        mature_ci_evaluation,
    )

    docs = _write_revision_fixture(tmp_path)
    frozen_sha = "b" * 40
    final_sha = "c" * 40
    owner_check = contracts_tests._success_check(
        commit_sha=frozen_sha, check_name="hosted-ci"
    )
    matured = mature_ci_evaluation(
        docs["expectation"],
        docs["outcome"],
        docs["request"],
        docs["evaluation"],
        evidence_commit_sha=frozen_sha,
        owner_check=owner_check,
        expected_check_name="hosted-ci",
        recorded_at="2026-09-02T12:00:21Z",
    )
    revision_2 = build_correction_revision(
        docs["revision_1"],
        payload=matured,
        correction_reason="DELAYED_OWNER_EVIDENCE_MATURATION",
        owner_evidence=[owner_check],
        corrected_at="2026-09-02T12:00:22Z",
    )
    self_model = build_self_model(
        matured,
        docs["expectation"],
        recorded_at="2026-09-02T12:00:23Z",
    )
    projection = build_agentos_projection(
        matured,
        docs["expectation"],
        docs["outcome"],
        recorded_at="2026-09-02T12:00:24Z",
        key_hint="OLV1-MATURED-CANDIDATE",
    )

    evidence_docs = {
        "research/outcome_learning/OLV1_EXPECTATION.json": docs["expectation"],
        "research/outcome_learning/OLV1_CANARY_REQUEST.json": docs["request"],
        "research/outcome_learning/OLV1_PREFLIGHT.json": docs["outcome"]["preflight"],
        "research/outcome_learning/OLV1_OUTCOME.json": docs["outcome"],
        "research/outcome_learning/OLV1_EVALUATION_V1.json": docs["evaluation"],
        "research/outcome_learning/OLV1_EVALUATION_REVISION_1.json": docs["revision_1"],
    }
    final_docs = {
        "research/outcome_learning/OLV1_EVALUATION_V2.json": matured,
        "research/outcome_learning/OLV1_EVALUATION_REVISION_2.json": revision_2,
        "research/outcome_learning/OLV1_SELF_MODEL_V2.json": self_model,
        "research/outcome_learning/OLV1_AGENTOS_PROJECTION_V2.json": projection,
    }
    repo_docs = {**evidence_docs, **final_docs}
    repo_paths = {
        path: json.dumps(doc, indent=2, sort_keys=True) + "\n"
        for path, doc in repo_docs.items()
    }
    evidence_artifacts = [
        _json_artifact(path, doc, blob_sha=_sha1(path))
        for path, doc in sorted(evidence_docs.items())
    ]
    final_artifacts = [
        _json_artifact(path, doc, blob_sha=_sha1(path))
        for path, doc in sorted(final_docs.items())
    ]
    evidence_receipt = build_remote_publication_receipt(
        stage="EVIDENCE_COMMIT",
        repository=docs["request"]["repository"],
        branch=docs["request"]["branch"],
        pr_number=398,
        episode_identity=docs["revision_1"]["episode_identity"],
        target_commit_sha=frozen_sha,
        frozen_evidence_commit_sha=frozen_sha,
        remote_branch_head_sha=frozen_sha,
        remote_pr_head_sha=frozen_sha,
        artifact_digests=evidence_artifacts,
        checks=[],
        observed_at="2026-09-02T12:00:15Z",
    )
    final_check = build_github_check_evidence(
        repository=docs["request"]["repository"],
        commit_sha=final_sha,
        check_run_id=5252,
        check_name="terminal-ci",
        status="completed",
        conclusion="success",
        observed_at="2026-09-02T12:00:30Z",
    )
    final_receipt = build_remote_publication_receipt(
        stage="MATURATION_COMMIT",
        repository=docs["request"]["repository"],
        branch=docs["request"]["branch"],
        pr_number=398,
        episode_identity=docs["revision_1"]["episode_identity"],
        target_commit_sha=final_sha,
        frozen_evidence_commit_sha=frozen_sha,
        remote_branch_head_sha=final_sha,
        remote_pr_head_sha=final_sha,
        artifact_digests=final_artifacts,
        checks=[final_check],
        observed_at="2026-09-02T12:00:31Z",
    )
    files = {
        "evaluation_matured": matured,
        "revision_2": revision_2,
        "self_model_matured": self_model,
        "projection_matured": projection,
        "evidence_receipt": evidence_receipt,
        "final_receipt": final_receipt,
    }
    for name, doc in files.items():
        (tmp_path / f"{name}.json").write_text(
            json.dumps(doc, indent=2, sort_keys=True) + "\n"
        )

    args = cli._parser().parse_args(
        [
            "proof",
            "--expectation", str(tmp_path / "expectation.json"),
            "--request", str(tmp_path / "request.json"),
            "--outcome", str(tmp_path / "outcome.json"),
            "--evaluation", str(tmp_path / "evaluation_matured.json"),
            "--self-model", str(tmp_path / "self_model_matured.json"),
            "--project", str(tmp_path / "projection_matured.json"),
            "--revision", str(tmp_path / "revision_1.json"),
            "--revision", str(tmp_path / "revision_2.json"),
            "--evidence-receipt", str(tmp_path / "evidence_receipt.json"),
            "--final-publication-receipt", str(tmp_path / "final_receipt.json"),
            "--mastermind-root", "/x",
            "--out", str(tmp_path / "production_proof.md"),
        ]
    )
    runner = FakeRunner(
        committed_blobs=repo_paths,
        ancestor_pairs={(frozen_sha, final_sha)},
    )
    transport = PublicationTransport(
        branch_sha=final_sha,
        check_runs_by_sha={
            frozen_sha: [
                _raw_check(
                    check_id=owner_check["check_run_id"],
                    name=owner_check["check_name"],
                    head_sha=frozen_sha,
                    conclusion=owner_check["conclusion"],
                )
            ],
            final_sha: [
                _raw_check(
                    check_id=final_check["check_run_id"],
                    name=final_check["check_name"],
                    head_sha=final_sha,
                    conclusion=final_check["conclusion"],
                )
            ],
        },
    )
    return args, runner, transport, files


def test_production_proof_requires_revision_chain_and_two_remote_receipts(tmp_path):
    args, runner, transport, _files = _production_proof_fixture(tmp_path)
    assert cli.cmd_proof(args, runner=runner, transport=transport) == 0
    proof = (tmp_path / "production_proof.md").read_text()
    assert proof.startswith("# OL-V1 Production Proof")
    assert "subject commit" in proof.lower()
    assert "cccccccccccccccccccccccccccccccccccccccc" in proof
    assert "frozen evidence commit" in proof.lower()
    assert "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in proof
    assert transport.patches == 0


@pytest.mark.parametrize(
    "missing_path",
    [
        "research/outcome_learning/OLV1_EXPECTATION.json",
        "research/outcome_learning/OLV1_CANARY_REQUEST.json",
        "research/outcome_learning/OLV1_PREFLIGHT.json",
        "research/outcome_learning/OLV1_OUTCOME.json",
    ],
)
def test_production_proof_requires_durable_source_and_outcome_artifacts(
    tmp_path, missing_path
):
    args, runner, transport, files = _production_proof_fixture(tmp_path)
    receipt = dict(files["evidence_receipt"])
    receipt["artifact_digests"] = [
        artifact
        for artifact in receipt["artifact_digests"]
        if artifact["path"] != missing_path
    ]
    (tmp_path / "evidence_receipt.json").write_text(json.dumps(receipt))

    with pytest.raises(
        cli.OutcomeLearningCliError,
        match="evidence publication.*exact committed artifact",
    ):
        cli.cmd_proof(args, runner=runner, transport=transport)
    assert not (tmp_path / "production_proof.md").exists()


def test_production_proof_refuses_receipt_without_exact_artifact_bytes(tmp_path):
    args, runner, transport, files = _production_proof_fixture(tmp_path)
    receipt = dict(files["final_receipt"])
    receipt["artifact_digests"] = [
        {
            "path": "research/outcome_learning/UNRELATED.json",
            "blob_sha": "d" * 40,
            "content_digest": canonical_digest({"unrelated": True}),
        }
    ]
    (tmp_path / "final_receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(cli.OutcomeLearningCliError, match="exact artifact path|exact committed artifact"):
        cli.cmd_proof(args, runner=runner, transport=transport)
    assert not (tmp_path / "production_proof.md").exists()


def test_production_proof_refuses_live_remote_or_owner_check_drift(tmp_path):
    args, runner, drifted, _files = _production_proof_fixture(tmp_path)
    drifted.branch_sha = "e" * 40
    with pytest.raises(cli.OutcomeLearningCliError, match="remote branch head"):
        cli.cmd_proof(args, runner=runner, transport=drifted)


def test_capture_maturation_refuses_incomplete_check_page(tmp_path):
    docs = _write_revision_fixture(tmp_path)
    frozen_sha = "b" * 40
    final_sha = "c" * 40
    path = "research/outcome_learning/OLV1_EVALUATION_V2.json"
    runner = FakeRunner(
        committed_blobs={path: json.dumps(docs["evaluation"], indent=2, sort_keys=True) + "\n"},
        ancestor_pairs={(frozen_sha, final_sha)},
    )
    transport = PublicationTransport(
        branch_sha=final_sha,
        check_runs_by_sha={
            final_sha: [
                _raw_check(check_id=1, name="hosted-ci", head_sha=final_sha)
            ]
        },
        total_count_by_sha={final_sha: 2},
    )
    args = cli._parser().parse_args(
        [
            "capture-publication",
            "--stage", "MATURATION_COMMIT",
            "--expectation", str(tmp_path / "expectation.json"),
            "--request", str(tmp_path / "request.json"),
            "--repo", docs["request"]["repository"],
            "--branch", docs["request"]["branch"],
            "--pr-number", "398",
            "--target-commit", final_sha,
            "--frozen-evidence-commit", frozen_sha,
            "--artifact", path,
            "--mastermind-root", "/x",
            "--out", str(tmp_path / "receipt.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="incomplete check-run page"):
        cli.cmd_capture_publication(
            args,
            runner=runner,
            transport=transport,
            clock=StepClock("2026-09-02T12:00:30+00:00"),
        )


def test_capture_maturation_refuses_non_descendant_final_commit(tmp_path):
    docs = _write_revision_fixture(tmp_path)
    frozen_sha = "b" * 40
    final_sha = "c" * 40
    path = "research/outcome_learning/OLV1_EVALUATION_V2.json"
    runner = FakeRunner(
        committed_blobs={path: json.dumps(docs["evaluation"], indent=2, sort_keys=True) + "\n"}
    )
    transport = PublicationTransport(
        branch_sha=final_sha,
        check_runs_by_sha={
            final_sha: [
                _raw_check(check_id=1, name="hosted-ci", head_sha=final_sha)
            ]
        },
    )
    args = cli._parser().parse_args(
        [
            "capture-publication",
            "--stage", "MATURATION_COMMIT",
            "--expectation", str(tmp_path / "expectation.json"),
            "--request", str(tmp_path / "request.json"),
            "--repo", docs["request"]["repository"],
            "--branch", docs["request"]["branch"],
            "--pr-number", "398",
            "--target-commit", final_sha,
            "--frozen-evidence-commit", frozen_sha,
            "--artifact", path,
            "--mastermind-root", "/x",
            "--out", str(tmp_path / "receipt.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="descend from the frozen evidence commit"):
        cli.cmd_capture_publication(
            args,
            runner=runner,
            transport=transport,
            clock=StepClock("2026-09-02T12:00:30+00:00"),
        )


def test_mature_evaluation_refuses_incomplete_check_page(tmp_path):
    from control_plane.outcome_learning_contracts import build_remote_publication_receipt

    docs = _write_revision_fixture(tmp_path)
    target = "b" * 40
    artifact = _json_artifact(
        "research/outcome_learning/OLV1_EVALUATION_V1.json",
        docs["evaluation"],
    )
    receipt = build_remote_publication_receipt(
        stage="EVIDENCE_COMMIT",
        repository=docs["request"]["repository"],
        branch=docs["request"]["branch"],
        pr_number=398,
        episode_identity=docs["revision_1"]["episode_identity"],
        target_commit_sha=target,
        frozen_evidence_commit_sha=target,
        remote_branch_head_sha=target,
        remote_pr_head_sha=target,
        artifact_digests=[artifact],
        checks=[],
        observed_at="2026-09-02T12:00:15Z",
    )
    (tmp_path / "evidence_receipt.json").write_text(json.dumps(receipt))
    transport = PublicationTransport(
        branch_sha=target,
        check_runs_by_sha={
            target: [_raw_check(check_id=1, name="hosted-ci", head_sha=target)]
        },
        total_count_by_sha={target: 2},
    )
    args = cli._parser().parse_args(
        [
            "mature-evaluation",
            "--expectation", str(tmp_path / "expectation.json"),
            "--request", str(tmp_path / "request.json"),
            "--outcome", str(tmp_path / "outcome.json"),
            "--initial-evaluation", str(tmp_path / "evaluation.json"),
            "--initial-revision", str(tmp_path / "revision_1.json"),
            "--evidence-receipt", str(tmp_path / "evidence_receipt.json"),
            "--check-name", "hosted-ci",
            "--out-evaluation", str(tmp_path / "bad_eval.json"),
            "--out-revision", str(tmp_path / "bad_revision.json"),
        ]
    )
    with pytest.raises(cli.OutcomeLearningCliError, match="incomplete check-run page"):
        cli.cmd_mature_evaluation(
            args,
            transport=transport,
            clock=StepClock("2026-09-02T12:00:20+00:00"),
        )
