# EVAL-R0 test fixtures

This directory is a placeholder for standalone fixture files if a future
wave needs them. EVAL-R0's own tests build all fixture data in-process via
`tests/agent_eval_factories.py` rather than reading files from here.

## Data declaration

Every scenario, configuration, experiment, run, scorer pass, and evidence
reference produced by `tests/agent_eval_factories.py` (and by
`tests/test_agent_eval_cli.py`'s synthetic journey) is **synthetic and
`PUBLIC_SAFE`**:

- no real repository content — all `artifact_ref` values are synthetic
  `git:mastermindx-market-intelligence/Mastermind@<sha>#...` references over
  a fabricated commit SHA (`"a" * 40` / `"b" * 40`), not a real commit;
- no real Chairman/company/production data of any kind;
- no real credentials, tokens, or private identifiers;
- no real model provider calls — `execution.model_requested` /
  `model_served` are plain strings, never dispatched to any provider.

## Exact R0 verification limitation

Every artifact this fixture set produces is, at most, `SHAPE_VALID` and
`EVALUATION_GRAPH_VERIFIED`. **R0 never claims `EVIDENCE_CONTENT_VERIFIED`.**
The `artifact_ref` values above are sealed references with a known digest;
R0 never resolves or reads the bytes they point to. A reviewer reproducing
the synthetic two-arm journey (`tests/test_agent_eval_cli.py`) sees exactly
this scope honestly reported by every CLI command and every evidence
reference's `verification_scopes` field.
