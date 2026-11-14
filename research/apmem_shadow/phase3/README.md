# Functional entry-risk research (phase3)

Original research with no automatic ranking, sizing, trading, alerting or scheduled execution. Start with RESULTS.md, FUNCTIONAL_DESIGN.md and PROTOCOL.md. Phase2 scientific modules are a source dependency; PR2476 remains the original release owner. The phase3 source is genuinely stacked, not a duplicate replacement.

## Source and inputs

The canonical Macro gate is pinned to6bbc4b0fc694c847077661ff5bf4c19ea41e4e81; the actual Mastermind entry assessor is pinned to8323d7a774a72da20d0e4db21c9080398da185e7. Exact per-file hashes, source captures and task chronology are in the evidence manifest. Raw vendor histories are not published. Reproduction requires lawfully accessible exact captures matching the recorded hashes, not freshly downloaded data silently substituted for the original vintage.

The private run root uses source/ for the verified Macro snapshot, consumer_source/ for the existing assessor snapshot, code/ for this repository's source, private/ for licensed captures and qualified panels, and separate immutable result directories. Use the existing approved provider readers; no credentials are included or created. Honor the preserved detailed-corporate-action endpoint refusal and the conservative receivable accounting convention.

## Verification and reproduction

From the repository root with its declared scientific dependencies:

```bash
python -m unittest discover -s tests -p 'test_apmem_phase3*.py'
```

Each runner refuses to overwrite a result directory. Inspect its --help and supply the exact source commit and private input/qualification paths. The order is canonical-prefix replay, run_risk, run_events, run_portfolios; run_expansions, run_etf_transfer and run_information are separately identified extensions. Prior accepted phase2 forecasts are reused by the ETF transfer runner, not refitted. The forward runner is one attended observation, not a daemon.

```bash
python -m research.apmem_shadow.phase3.run_risk --help
python -m research.apmem_shadow.phase3.run_events --help
python -m research.apmem_shadow.phase3.run_portfolios --help
python -m research.apmem_shadow.phase3.run_expansions --help
python -m research.apmem_shadow.phase3.run_etf_transfer --help
python -m research.apmem_shadow.phase3.run_information --help
python -m research.apmem_shadow.phase3.forward --help
```

For native replay and the real consumer witness, add the independently verified immutable Macro/consumer snapshot roots to PYTHONPATH; never point historical replay at an unverified current worktree or default-current vendor artifact. `native.verify_source` checks the required Macro files before the observation. Supply exact prefix data and disable peer-waiver/current-data defaults. `replay.replay` is a pure per-instrument routine; its observed-prefix records are not the old tier_stream approximation.

## Evidence and authority

Complete aggregate metrics and all contrast results are under research/evidence/apmem_shadow_phase3/. Primary, exploratory, transfer, forward and release facts are labeled separately. Research counts are not independent sample counts. The consumer's unchanged incumbent decision is verifiable; research probabilities cannot upgrade it. `forward.score_captured_outcomes` binds immutable forecast bytes to a later same-provider capture, checks input revisions, and scores only matured horizons. No background collector, scheduler, autonomous portfolio or trade process is installed.

Normal source review is author self-review under attended Web policy, not independent approval. All repository protections and the existing parent release dependency remain binding. Fabric was unavailable; multiprocessing used for numerical work is not an LLM subagent team.
