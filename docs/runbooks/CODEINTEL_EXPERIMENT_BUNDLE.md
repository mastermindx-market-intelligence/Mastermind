# Code Intelligence experiment bundle — B0 held runbook

## Status and authority

This is a **source-only B0 experiment** for
`mastermind-codeintel-b0-hosted-tool-bundle-forge-20260902-sol-001`. It creates
neither a production tool install nor a runtime control-plane change. The only
workflow trigger is manual `workflow_dispatch`; it accepts exactly the selected
consumer mode (`C0` or `Z0`), a 40-character consumer commit, its exact tree,
and the fixed operation key. It accepts no repository, URL, command, executable,
path, runner, image, credential, cache, or arbitrary argument.

Running this workflow is a separate governed decision. B0 source validation,
passing tests, a Draft/Hold PR, and an uploaded handoff marker are not a Ready,
dispatch, merge, deployment, installation, or production-proof receipt.

## Supply boundary

`research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json`
is the only toolchain authority. It locks the verified source commit/tree,
dependency-lock blob where a source build has dependencies, license/notices,
publisher artifact checksum where an artifact is staged, deterministic build
recipe hash, and the initial `linux-x64` operating-system/architecture boundary.

The preflight validator refuses the whole lock when any identity is absent,
malformed, on an unsupported platform, or inconsistent with the lock digest.
That is intentionally distinct from Phase-P supply evidence: after a future
hosted retriever resolves exact commits/trees, reads blobs, and hashes staged
bytes, it must call `verify_phase_p_evidence` to compare every observation to
the reviewed lock. A self-consistent edited lock is not retrieval proof. The
current held workflow deliberately has no retriever and cannot emit that proof.

The workflow has no cache action and has only full-SHA action pins. Package
manager, ambient binary, mutable tag, global install, and caller-selected
download surfaces are outside the contract.

## Phase boundary

Phase P is the only network-permitted future hosted phase. It checks out the B0
source at the workflow commit, validates the closed dispatch and lock **before**
the consumer SHA reaches the checkout action, then checks out that exact
consumer commit and proves its tree. The source has no local invocation that
retrieves, builds, installs, or executes the external bundle.

Phase E is a distinct sealed job. It receives only the short immutable identity
handoff, first proves that `unshare -n` itself can create a namespace, then
requires a direct network probe to fail inside that namespace. Failure to create
the namespace or a successful connection both fail the job. It then selects one
fixed mode command; that command is not caller parameterized. If a future hosted
implementation emits a bundle, it must verify a bounded artifact digest before
and after Phase E and write only the receipt schema below.

## Receipts and replay

The sole receipt schema is `mastermind.codeintel_experiment_bundle.v1`. Its
closed fields are operation key, mode, consumer commit/tree, lock digest, bundle
SHA-256, effect, and reason codes. The effect vocabulary is exactly
`NOT_APPLIED`, `APPLIED`, or `EFFECT_UNKNOWN`; no paths, URLs, tokens, commands,
credentials, host IDs, or unbounded logs belong in the receipt.

`EFFECT_UNKNOWN` blocks retry. A new execution requires a fresh separately
authorized operation rather than replaying a possibly applied effect.
`retry_allowed` validates the entire closed receipt—including schema, identity,
checksums, exact fields, and normalized reason codes—before it can permit only a
proven `NOT_APPLIED` retry.
