# Hermes source support through the original APPLICATION owner

This is an exact-source proposal for Macro #10740. It does not change that
active branch, enroll an application, publish a credential, activate a service,
or authorize a provider request. The existing owner consumes it under its
original source/release rules. Macro #10832's unsupported-base CI-authority
result is not bypassed or relabelled by this artifact.

## Missing source declaration

At original Macro `a577dbbf605474f97bbafa4ceeb0daf841292421`, the eight general
AUTO application transports have source support. The five Hermes descriptors
remain source-held. Valid runtime data alone cannot open those descriptors.

The patch changes only `qualified` and `application_allowed` on these existing
entries, plus their explanatory comment:

| Descriptor | Existing service / lane | Existing route |
| --- | --- | --- |
| native_go_hermes_attended_v1 | hermes_attended_fabric / hermes-attended | Fixed glm-5.3-flash;127.0.0.1:50142 |
| native_go_hermes_secretary_v1 | hermes_secretary_fabric / hermes-secretary | Fixed deepseek-v4.1-flash;127.0.0.2:50142 |
| native_go_hermes_meta_v1 | hermes_meta_fabric / hermes-meta-ceo | Fixed deepseek-v4.1-flash;127.0.0.3:50142 |
| native_fabric_hermes_secretary_auto_v1 | Same Secretary identity | Original AUTO/exact contract; same endpoint |
| native_fabric_hermes_meta_auto_v1 | Same meta-CEO identity | Original AUTO/exact contract; same endpoint |

The dataclass defaults remain false. All other descriptors, credential-reference
names, capability IDs, endpoints, fixed models, service relations, workloads,
metadata permissions and inference-only purpose are unchanged. No attended
AUTO relation or worker permission is added.

## Runtime authority stays with the owner

Shipped `application_fabric_modes` stays `{}`. The three Hermes capability IDs
are absent from the shipped manifest; this proposal adds none. Inspect/bind
still refuse before credential resolution or client construction when runtime
configuration is absent, disabled, unqualified, expired, missing its qualification
reference, held by capability policy, or bound to another lane/reference.
Frozen inspections are rechecked. Explicit source revocation still refuses.

The source flags mean supported software, not current account entitlement or
live qualification. The provider owner must still qualify the actual physical
account/product/model/endpoint/configuration, current headroom and enforceable
financial boundary. Existing native admission, original lease/usage settlement
and effect recovery remain unchanged.

## Exact composition and proof

`contract.json` pins the parent commit, patch digest, all four source/test
preimages and postimages, and unchanged client/configuration inputs.
`a577-hermes-source-support.patch` changes the factory, updates the existing
role/attended tests for supported-but-unenrolled software while preserving their
source-revocation assertions, and adds93 focused checks. The original31-case
attended test is already present in a577 under its exact published blob.

The10 positive source-support cases fail against the unchanged a577 descriptors.
The proposed source passes383 cases:93 new,23 primary identity,31 attended
identity,25 shared service identity,168 binding,27 inspection and16 endpoint.
`local-proof.json` preserves the exact counts and source attribution. These are
disposable qualification fixtures, with no installed changes or provider calls.

The existing `qualify_application_owner.py` also covers21 native cases:
Secretary and meta-CEO fixed/AUTO/exact, plus attended fixed; each exercises a
native tool conversation, step-limit refusal and uncertain-followup retention.
With `--source-support-proposal`, `owner_source_support.py` exports the exact
selected committed Macro blobs into a new temporary directory, verifies/applies only
the four declared files, runs the383 original-owner cases and then executes
the native cases. The positive proposal path does not override the source
support flags. Only the disposable endpoint/model and runtime qualification
inputs are synthetic. The unmodified-owner path is reported separately.

The hosted receipts below establish each exact source context. The older12-case
c164 native proof is not relabelled as this21-case proof.

The original-a577 context passed all21 cases on composed d7/173b224 in hosted
job128439397143. Its subsequent proposal preparation failed at `git archive`
with exit128 before applying the patch; captured stderr was not surfaced, so
the underlying archive cause is unproved. Preparation now reads only selected
committed tree/blob objects, verifies their IDs, sizes and regular-file modes,
and refuses missing local blobs without lazy fetch or working-tree substitution.
Three actual local-Git boundary cases pass, covering committed bytes/modes,
link refusal and missing-object refusal with the object still absent afterward.
The exact source/patch contract, original-clean-source readbacks and complete
four-file postimage delta remain mandatory.

Hosted proposal qualification now passes on90fb/2d9acf5 in job128444807247:
383 owner cases in3.63s, then21 actual native APPLICATION/Broker cases in134.653s
without overriding source flags. The original-a577 context also passes21 cases
in133.916s. All have zero failures, errors or skips. The export verifies2538
committed files; the four-file patch yields2539 fixture files. Its original
checkout remains unchanged, and native network/SDK counters are zero.
[The full source-bound receipts](../../../../review_evidence/hermes_primary/source-support-hosted-20261107.json)
retain the distinct source contexts and their fixture/live acceptance boundary.

The three Git boundary cases execute explicitly through
`qualification/verify_source_materialization.py`. They are outside the gateway's
`test_*.py` discovery: its original100-case contract remains unchanged. The
preceding103-case execution passed every case but correctly refused its exact
suite-size contract; renaming the unchanged boundary entry resolves that scope.

## Owner consumption

Reconcile the active Macro head and compare every preimage before applying the
patch once on the original carrier. A changed input requires source composition;
do not force, replace, or move the original operation. Preserve the existing
generic AUTO declarations and all newer source. Run the exact native and runtime
authority checks against the resulting published source, plus required CI.
Only then may the original release/enrollment owners proceed under their
existing controls. No account authentication refusal, runtime hold, or uncertain
effect is cleared by this source-support proposal.
