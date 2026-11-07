"""Actual temporary Git; inert grant/Event-permit/PR seams, no live effect.

The exact compiler output shape is exercised here; a separate integration
checks real a5/e4 recipes. These fixtures are not a grant or publication proof.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import workspace_project_git_publisher as p
from control_plane.project_plan_adoption_git import BINDING_SCHEMA, LOOKUP_SCHEMA

spec = importlib.util.spec_from_file_location("adopt_existing_git_fixtures",
    Path(__file__).with_name("test_workspace_project_git_publisher.py"))
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
env, isolated_git_env = old.env, old.isolated_git_env


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def commit_files(env, values):
    for path, content in values.items():
        file = env.seed / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
    old.git(env.seed, "add", ".")
    old.git(env.seed, "commit", "-m", "fixture source")
    old.git(env.seed, "push", "origin", "main")
    old.git(env.clone, "fetch", "origin", "main")
    return old.rev_parse(env.seed, "HEAD")


def case(env, phase="CANDIDATE", *, unchanged=False, predecessor=True):
    ws, prior = "agentos/workstreams/WS-DEMO.md", "agentos/decisions/DEC-FIRST.md"
    candidate = "exact proposed workstream\r\n"
    digest, rid = sha(candidate), "mmos-project-adopt-" + "a" * 40
    artifact = "planning/proposal.candidate-" + digest[:20] + ".md"
    decision = "agentos/decisions/DEC-PLAN-ADOPTION-" + "A" * 40 + ".md"
    baseline = candidate if unchanged else "retained baseline\n"
    base = commit_files(env, {ws: baseline, prior: "prior decision\n"})
    original = base
    if phase == "ADOPTION":
        base = commit_files(env, {artifact: candidate})
    source = lambda path: {"repository": p.REPOSITORY, "commit": original, "path": path, "content_sha256": "b" * 64}
    request = {"schema": "agentos.plan_adoption_request.v1", "request_id": rid,
        "work_ref": "WS:DEMO", "expected_commit": original,
        "expected_adoption": "DEC:FIRST" if predecessor else None,
        "proposal_source": source("planning/proposal.md"), "base_source": source("planning/base.md"),
        "candidate_sha256": digest}
    lookup = {"schema": LOOKUP_SCHEMA, "action": "ADOPT_PLAN", "request_id": rid, "work_ref": "WS:DEMO"}
    edits = [{"path": artifact, "mode": "100644", "expected_sha256": None,
              "content_utf8": candidate, "content_sha256": digest}]
    if phase == "ADOPTION":
        edits = [] if unchanged else [{"path": ws, "mode": "100644", "expected_sha256": sha(baseline),
            "content_utf8": candidate, "content_sha256": digest}]
        edits.append({"path": decision, "mode": "100644", "expected_sha256": None,
                      "content_utf8": "new decision\n", "content_sha256": sha("new decision\n")})
        if predecessor:
            edits.append({"path": prior, "mode": "100644", "expected_sha256": sha("prior decision\n"),
                          "content_utf8": "prior superseded\n", "content_sha256": sha("prior superseded\n")})
    recipe = {"schema": "agentos.plan_adoption_recipe.v1", "status": "PREVIEW_ONLY",
        "phase": "CANDIDATE" if phase == "CANDIDATE" else "ADOPTION_DECISION",
        "request_id": rid, "request_sha256": "c" * 64, "work_ref": "WS:DEMO", "principal_id": "fixture-owner",
        "expected_commit": base, "candidate_path": artifact, "candidate_sha256": digest,
        "decision_ref": "DEC:PLAN-ADOPTION-" + "A" * 40,
        "proposal_source": request["proposal_source"], "base_source": request["base_source"],
        "expected_adoption": request["expected_adoption"], "requires_publication": True,
        "candidate_source": None, "edits": edits, "preview": {}}
    images = [{"path": e["path"], "content_sha256": e["content_sha256"],
               "expected_preimage_sha256": e["expected_sha256"]} for e in edits]
    if phase == "ADOPTION" and unchanged:
        images.insert(0, {"path": ws, "content_sha256": digest, "expected_preimage_sha256": digest})
    scope, stamp = "d" * 64, "e" * 64
    metadata = {"schema": BINDING_SCHEMA, "selection": lookup, "principal_scope": scope,
        "request_sha256": sha(json.dumps(request, sort_keys=True, separators=(",", ":"))),
        "recipe_fingerprint_sha256": recipe["request_sha256"], "permission_binding_digest": stamp,
        "phase": phase, "publication_binding": {"expected_commit": base, "postimages": images, "branch": None}}
    state = SimpleNamespace(authorized=True, permit=object(), metadata=metadata)
    pr = old.InertPullRequestOwner(env.origin)
    binding = p.PublisherBinding(worktree=str(env.clone), expected_origin=str(env.origin),
        default_branch="main", publisher_identity=old.PUBLISHER_IDENTITY)
    publisher = p.FixedProjectGitPublisher(binding, lambda _: pytest.fail("no CREATE compiler"),
        lambda _: False, lambda _: pytest.fail("no CREATE stamp"), old.qualify_publisher, pr,
        principal_scope=lambda _: scope, authorize_plan_adoption=lambda principal, work: state.authorized and work == "WS:DEMO",
        plan_adoption_permission_stamp=lambda principal, work: stamp,
        load_plan_adoption_operation=lambda principal, selected, selected_phase: deepcopy(state.metadata),
        validate_plan_adoption_claim=lambda principal, selected, claim, metadata: claim is state.permit)
    def publish():
        return publisher.publish_plan_adoption(request, recipe, old.AUTHORIZED_PRINCIPAL, phase=phase, claim=state.permit)
    def reconcile():
        return publisher.reconcile_plan_adoption(lookup, old.AUTHORIZED_PRINCIPAL, phase=phase)
    return SimpleNamespace(**locals())


@pytest.mark.parametrize("phase,unchanged,predecessor", [("CANDIDATE", False, True),
    ("ADOPTION", False, True), ("ADOPTION", True, True), ("ADOPTION", False, False)])
def test_distinct_phase_single_publication_then_whole_upstream_readback(env, phase, unchanged, predecessor):
    f = case(env, phase, unchanged=unchanged, predecessor=predecessor)
    result = f.publish()
    assert result["state"] == "PROPOSAL_PUBLISHED", result
    assert result["phase"] == phase and result["retryable"] is False
    branch = result["proposal"]["head_branch"]
    before = old.snapshot(env.clone)
    again = f.publish()
    assert again["state"] == "PROPOSAL_PUBLISHED" and f.pr.create_calls == 1
    assert old.snapshot(env.clone) == before
    if phase == "CANDIDATE":
        assert old.git(env.origin, "show", "main:" + f.ws) == f.baseline
        assert f.decision not in old.git(env.origin, "ls-tree", "-r", "--name-only", branch).splitlines()
    old.git(env.seed, "fetch", "origin", branch)
    old.git(env.seed, "merge", "--ff-only", "FETCH_HEAD")
    old.git(env.seed, "push", "origin", "main")
    before = old.snapshot(env.clone)
    observed = f.reconcile()
    assert observed["state"] == "SOURCE_PUBLISHED", observed
    assert len(observed["source"]["postimages"]) == len(f.images)
    assert f.pr.create_calls == 1 and old.refs(env.clone) == before["refs"]


@pytest.mark.parametrize("mutation", ["claim", "grant", "scope", "fingerprint", "branch", "path", "preimage", "digest"])
def test_invalid_authority_or_exact_binding_writes_nothing(env, mutation):
    f = case(env, "ADOPTION")
    if mutation == "claim":
        f.publisher._plan_adoption.seams["claim"] = lambda *args: False
    elif mutation == "grant": f.state.authorized = False
    elif mutation == "scope": f.metadata["principal_scope"] = "f" * 64
    elif mutation == "fingerprint": f.recipe["request_sha256"] = "f" * 64
    elif mutation == "branch": f.metadata["publication_binding"]["branch"] = "retarget"
    elif mutation == "path": f.recipe["edits"][0]["path"] = "agentos/workstreams/WS-OTHER.md"
    elif mutation == "preimage": f.recipe["edits"][0]["expected_sha256"] = "f" * 64
    elif mutation == "digest": f.recipe["edits"][0]["content_utf8"] += "changed"
    before = old.snapshot(env.clone)
    out = f.publish()
    assert out["state"] in {"NOT_DISPATCHED", "CONFLICT"}, out
    assert f.pr.create_calls == 0 and old.snapshot(env.clone) == before


def test_unknown_original_reconcile_never_claims_builds_or_replays(env, monkeypatch):
    f = case(env)
    before = old.snapshot(env.clone)
    for method in ("_build_knowledge_commit", "_claim_local_branch_knowledge", "_push_knowledge_branch", "_ensure_pull_request_knowledge"):
        monkeypatch.setattr(f.publisher, method, lambda *a, **k: pytest.fail("reconcile wrote"))
    out = f.reconcile()
    assert out["state"] == "EFFECT_UNKNOWN" and f.pr.create_calls == 0
    assert old.snapshot(env.clone) == before


def test_later_auth_loss_after_first_object_write_stays_unknown(env, monkeypatch):
    f = case(env)
    original = f.publisher._git
    def run(args, *a, **kw):
        result = original(args, *a, **kw)
        if args[:2] == ["hash-object", "-w"]: f.state.authorized = False
        return result
    monkeypatch.setattr(f.publisher, "_git", run)
    assert f.publish()["state"] == "EFFECT_UNKNOWN"
    assert f.reconcile()["state"] == "EFFECT_UNKNOWN"
    assert f.pr.create_calls == 0


def test_real_private_permit_not_caller_label_required(env):
    f = case(env)
    before = old.snapshot(env.clone)
    out = f.publisher.publish_plan_adoption(f.request, f.recipe, old.AUTHORIZED_PRINCIPAL,
                                            phase="CANDIDATE", claim=object())
    assert out["state"] == "NOT_DISPATCHED" and out["reason"] == "CLAIM_INVALID"
    assert old.snapshot(env.clone) == before and f.pr.create_calls == 0


def test_actual_preimage_and_stale_upstream_refuse_before_objects(env):
    f = case(env, "ADOPTION")
    f.metadata["publication_binding"]["postimages"][0]["expected_preimage_sha256"] = "f" * 64
    f.recipe["edits"][0]["expected_sha256"] = "f" * 64
    before = old.snapshot(env.clone)
    assert f.publish()["state"] == "CONFLICT"
    assert old.snapshot(env.clone) == before
    commit_files(env, {"unrelated.md": "current source advanced\n"})
    before = old.snapshot(env.clone)
    out = f.publish()
    assert out["state"] == "NOT_DISPATCHED" and out["reason"] == "STALE_EXPECTED_COMMIT"
    assert old.snapshot(env.clone) == before and f.pr.create_calls == 0


def test_unchanged_ws_cannot_be_omitted_from_logical_binding(env):
    f = case(env, "ADOPTION", unchanged=True)
    f.metadata["publication_binding"]["postimages"].pop(0)
    before = old.snapshot(env.clone)
    assert f.publish()["state"] == "NOT_DISPATCHED"
    assert old.snapshot(env.clone) == before and f.pr.create_calls == 0


def test_partial_default_and_local_replace_objects_never_prove_whole_adoption(env):
    f = case(env, "ADOPTION")
    # Only WS changed on real upstream: no matching new DEC/predecessor.
    partial = commit_files(env, {f.ws: f.candidate})
    assert f.reconcile()["state"] == "EFFECT_UNKNOWN"
    # A local replacement containing every desired postimage cannot spoof
    # the actual upstream default, because the incumbent Git bridge disables it.
    fake = commit_files(env, {e["path"]: e["content_utf8"] for e in f.recipe["edits"]})
    old.git(env.seed, "push", "origin", f"{partial}:refs/heads/main", "--force")
    old.git(env.clone, "fetch", "origin", fake)
    old.git(env.clone, "replace", partial, fake)
    assert f.reconcile()["state"] == "EFFECT_UNKNOWN"
    assert f.pr.create_calls == 0


def test_pr_unknown_is_retained_and_same_phase_does_not_create_again(env):
    f = case(env)
    f.pr.create_error = p.PrOwnerUnknownOutcome("inert unknown")
    assert f.publish()["state"] == "EFFECT_UNKNOWN"
    calls = f.pr.create_calls
    f.pr.create_error = None
    assert f.publish()["state"] == "PREPARED"
    assert f.reconcile()["state"] == "PREPARED"
    assert f.pr.create_calls == calls


def test_missing_adopt_seams_never_borrow_create_permission(env):
    base = old.expected_commit_of(env)
    publisher = old.build_publisher(env, base).publisher
    f = case(env)
    before = old.snapshot(env.clone)
    out = publisher.publish_plan_adoption(f.request, f.recipe, old.AUTHORIZED_PRINCIPAL,
                                         phase="CANDIDATE", claim=f.state.permit)
    assert out["state"] == "NOT_DISPATCHED" and out["reason"] == "ADOPTION_SEAMS_ABSENT"
    assert old.snapshot(env.clone) == before
