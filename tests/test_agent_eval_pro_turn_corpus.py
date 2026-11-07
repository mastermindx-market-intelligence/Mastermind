"""Public conformance data exercised by existing Agent Eval consumers; no model run."""
from pathlib import Path
import json
import shutil
import subprocess
from scripts.agent_eval import corpus
from scripts.agent_eval.tc3_protocol_compliance import score_submission

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus/agent_eval_pro_turns"
CASES = {
    "healthy_chunk", "valid_short_completion", "redundant_confirmation", "new_spend_gate",
    "lane_local_blocker", "no_delta_loop", "unknown_context_meter", "soft_output_target",
    "oversized_result", "required_authority_read", "unusable_session", "checkpoint_then_continue",
    "unknown_effect", "generic_failure", "same_chat_summary", "dirty_writer_hold",
    "delivered_not_started", "milestone_gaming", "unobserved_model", "scarce_principal_wait",
}

def cases():
    paths = sorted(CORPUS.glob("scenarios/*/*/v1/scenario.json"))
    assert {p.parent.parent.name for p in paths} == CASES
    for path in paths:
        yield path, json.loads(path.read_text()), json.loads((path.parent / "fixtures/input.json").read_text()), json.loads((path.parent / "fixtures/expected.json").read_text())

def test_corpus_is_complete_and_verified():
    assert len(list(cases())) == 20
    report = corpus.verify_corpus_tree_consistency(CORPUS, ROOT)
    assert report.result == "CONSISTENT", report.defects
    assert (report.scenario_count, report.holdout_count) == (20, 0)

def test_existing_tc3_scorer_rejects_every_wrong_action():
    for _, _, given, gold in cases():
        assert len(set(given["candidate_actions"])) == 3
        assert gold["answer"] in given["candidate_actions"]
        for action in given["candidate_actions"]:
            dimensions = score_submission(gold, given, {"selected_action": action, "rationale": "A fluent explanation cannot excuse the wrong action."})
            by_name = {d["dimension"]: d["status"] for d in dimensions}
            assert by_name["correctness"] == ("PASS" if action == gold["answer"] else "FAIL")
            assert by_name["rubric_residue"] == "UNKNOWN"
        wrong = score_submission(gold, given, {"selected_action": gold["answer"].lower(), "rationale": "Same words, wrong exact protocol."})
        assert wrong[0]["status"] == "FAIL"

def test_gold_is_separate_and_policy_is_effect_free():
    for _, scenario, given, _ in cases():
        assert set(given) == {"question", "situation", "candidate_actions", "policy_sources"}
        assert scenario["privacy"]["model_visible_artifact_refs"] == [scenario["input_fixture"]["artifact_ref"]]
        assert scenario["source_policy"]["solution_refs_hidden"] == [scenario["expected_contract"]["artifact_ref"]]
        assert scenario["effect_policy"] == {"mode": "NO_EFFECT_ONLY", "allowed_operation_refs": []}
        assert scenario["capability_policy"]["allowed_capability_ids"] == []
        assert scenario["execution_policy"]["network_policy"] == "DENY_ALL"
        assert scenario["authorship"]["author_ref"] != scenario["authorship"]["independent_reviewer_ref"]
        assert "mastermind.tc3_protocol_compliance.v1" in scenario["scoring_policy"]["required_scorers"]

def test_fixture_tampering_is_refused(tmp_path):
    copied = tmp_path / "corpus/agent_eval_pro_turns"
    shutil.copytree(CORPUS, copied)
    fixture = next(copied.glob("scenarios/*/*/v1/fixtures/expected.json"))
    fixture.write_text(fixture.read_text() + " ")
    assert corpus.verify_corpus_tree_consistency(copied, tmp_path).result == "INCONSISTENT"

def test_fixture_references_exist_at_their_exact_immutable_anchor():
    for _, scenario, _, _ in cases():
        for field in ("input_fixture", "expected_contract"):
            ref = scenario[field]["artifact_ref"]
            revision, relative = ref.split("#", 1)
            sha = revision.rsplit("@", 1)[1]
            observed = subprocess.run(["git", "show", f"{sha}:{relative}"], cwd=ROOT, check=True, capture_output=True).stdout
            assert corpus.file_digest(observed) == scenario[field]["digest"]

def test_original_frozen_corpus_stays_valid():
    assert corpus.verify_corpus_tree_consistency(ROOT / "corpus/agent_eval", ROOT).result == "CONSISTENT"

def test_existing_cli_consumes_the_new_explicit_corpus_root():
    from scripts.agent_eval import cli
    assert cli.main(["corpus-verify", "--corpus-root", str(CORPUS), "--repo-root", str(ROOT)]) == 0

def test_correct_answer_positions_are_balanced():
    counts = [0, 0, 0]
    for _, _, given, gold in cases():
        counts[given["candidate_actions"].index(gold["answer"])] += 1
    assert max(counts) - min(counts) <= 1, counts
