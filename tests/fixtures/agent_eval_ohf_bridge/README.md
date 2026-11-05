# EVAL-OHF2 harness-written real-bytes fixture

Review repair MAJOR-2. This directory holds ONE OHF F0 evidence artifact
and its `MANIFEST.json`, produced by calling PR #162's actual
`scripts.ohf.fresh_sol_eval.write_run_artifact()` directly against
hand-built (but otherwise real) `RunObservation`/`ProcedureBundle`/
`CapabilityReceipt`/`CleanupReceipt` dataclasses -- no live App Server, no
fake-client control loop, but the REAL serialization code path: real
`yaml.safe_dump`, real backtick fencing (`_fence_for`), real
`_evidence_metadata`/`write_run_artifact`/manifest bookkeeping. These are
not hand-rendered by this bridge's own tests; they are the harness's own
output bytes, committed verbatim.

`tests/test_agent_eval_ohf_bridge.py`'s
`test_bridges_harness_written_real_bytes_fixture_end_to_end` bridges these
exact committed bytes through the full pipeline (parse -> draft ->
finalize -> store -> scorer -> tree-graph verification), reading the
files from disk exactly as a production caller would.

## Data declaration

Synthetic and `PUBLIC_SAFE`: the prompt/output text, process
identifiers, thread id, and digests are all fabricated for this fixture.
`procedure_commit_sha` is the REAL, frozen `control-1.0.0` Skillpack arm
commit sha (plan record §2 table; also PR #162's own
`MAS136_ARMS["control-1.0.0"]`), since that identity is public and fixed
regardless of which run used it. No real Chairman/company/production
data, no credentials, no real model provider call (the harness path used
here never contacts App Server or any provider).

## Regenerating

Not scripted into the repo (the generator imports PR #162's unmerged
`scripts.ohf.fresh_sol_eval`, which this wave's own production code must
never import -- module docstring, plan record §6). To regenerate: check
out PR #162's branch in a separate worktree, run a small script that
imports `write_run_artifact` and the dataclasses above with
`PYTHONPATH` pointed at that worktree, and copy the resulting
`runs/**/*.md` + `MANIFEST.json` bytes back here.

## Exact R0 verification limitation

Same as `tests/fixtures/agent_eval/README.md`: the bridged run reaches
`SHAPE_VALID` and `EVALUATION_GRAPH_VERIFIED`. R0 never claims
`EVIDENCE_CONTENT_VERIFIED` -- the `artifact_ref` values are sealed
references with a known digest, never resolved or read by R0 itself.
