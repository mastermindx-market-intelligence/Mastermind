# Agent Evaluation H1/H2 Provider-Free Vertical

## Outcome

Replace the obsolete historical-E1 execution path with one prospective, provider-free vertical that produces two reusable artifacts through existing Agent Evaluation v1 seams:

1. an opaque private-holdout commitment;
2. an owner-proven environment manifest bound by `configuration.capabilities.environment_digest` and consumable as scorer-pass `input_evidence`.

Historical E1 remains immutable and unexecuted. No provider/model call belongs to this slice.

## Files

- `scripts/agent_eval/harness_convergence.py`
- `tests/test_agent_eval_harness_convergence.py`

## Authority ceiling

The artifacts are structural/provenance evidence only. They cannot rank or route workers, originate or size trades, promote policy, authorize provider execution, or prove model/harness causality from system-realistic observations.

## TDD acceptance

- opaque commitment never serializes holdout contents or filesystem paths;
- exposed/burned holdout refuses confirmatory use;
- environment digest mismatch refuses rather than substituting a fixture;
- copied digest with changed configuration refuses on snapshot mismatch;
- factor-locked claims require owner-proven provider-principal evidence;
- system-realistic evidence remains descriptive;
- grader provenance must be an artifact pair, not self-reported text;
- all provenance lists reuse the canonical Agent Evaluation artifact-list validator and refuse duplicate refs or digests;
- unseeded/unknown RNG requires preregistered replicates;
- output evidence uses the existing scorer-pass artifact-pair shape;
- authority and promotion remain `NONE`.
